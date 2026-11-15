"""Land-cover lookup for hotspots from NASA MCD12Q1 C6.1 ``LC_Type1`` (IGBP) rasters.

Expected input: one or more single-band GeoTIFF per year in a directory, either
- AppEEARS area extract (product MCD12Q1.061, layer LC_Type1, GeoTIFF, geographic
  or native projection), e.g. ``MCD12Q1.061_LC_Type1_doy2018001_aid0001.tif``;
- native sinusoidal tiles converted from HDF4 (Gabon: h18v08, h19v08, h18v09,
  h19v09), e.g. ``MCD12Q1.A2018001.h19v09.061.<prod>.tif``.

Only north-up rasters in WGS84 geographic coordinates or the MODIS sinusoidal
grid are accepted: categorical data must not be resampled. If a reprojection is
required, use nearest-neighbour resampling.

The lookup returns the IGBP class of the pixel containing the detection and the
share of that class among valid pixels of the surrounding window (3x3 by
default, i.e. about 1.5 km for 500 m pixels). That share feeds the ``mixed``
rule of ``fire_typing.classify_hotspot``.
"""
from __future__ import annotations

import math
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from apps.observations.fire_typing import (
    IGBP_CLASSES,
    NO_DATA_CLASSES,
    LandCoverSample,
    select_land_cover_year,
)

MODIS_SPHERE_RADIUS_M = 6371007.181
MODIS_TILE_SIZE_M = 1111950.5197665233
MODIS_GRID_HALF_WIDTH_M = 20015109.354
CRS_KINDS = {"geographic", "sinusoidal"}
RASTER_SUFFIXES = {".tif", ".tiff"}


def project_sinusoidal(lat: float, lon: float) -> tuple[float, float]:
    """WGS84 lat/lon (degrees) -> MODIS sinusoidal x/y (metres)."""
    phi, lam = math.radians(lat), math.radians(lon)
    return MODIS_SPHERE_RADIUS_M * lam * math.cos(phi), MODIS_SPHERE_RADIUS_M * phi


def modis_tile(lat: float, lon: float) -> str:
    """MODIS sinusoidal tile (``hHHvVV``) containing a point, to know which tiles to download."""
    x, y = project_sinusoidal(lat, lon)
    h = math.floor((x + MODIS_GRID_HALF_WIDTH_M) / MODIS_TILE_SIZE_M)
    v = math.floor((MODIS_TILE_SIZE_M * 9 - y) / MODIS_TILE_SIZE_M)
    return f"h{h:02d}v{v:02d}"


@dataclass(frozen=True)
class RasterGrid:
    """GDAL-style geotransform of a north-up raster."""

    geotransform: tuple[float, float, float, float, float, float]
    width: int
    height: int
    crs_kind: str
    nodata: int | None

    def __post_init__(self):
        gt = tuple(self.geotransform)
        if len(gt) != 6 or gt[2] != 0 or gt[4] != 0 or gt[1] <= 0 or gt[5] >= 0:
            raise ValueError("only north-up, non-rotated rasters are supported")
        if self.width <= 0 or self.height <= 0:
            raise ValueError("raster must not be empty")
        if self.crs_kind not in CRS_KINDS:
            raise ValueError(f"unsupported CRS kind: {self.crs_kind!r}")

    def pixel_of(self, lat: float, lon: float) -> tuple[int, int] | None:
        x, y = (lon, lat) if self.crs_kind == "geographic" else project_sinusoidal(lat, lon)
        ox, pw, _, oy, _, ph = self.geotransform
        col, row = math.floor((x - ox) / pw), math.floor((y - oy) / ph)
        if 0 <= col < self.width and 0 <= row < self.height:
            return col, row
        return None


class RasterSource(Protocol):
    grid: RasterGrid

    def read(self, col: int, row: int, cols: int, rows: int) -> Sequence[Sequence[int]]:
        """Return ``rows`` lists of ``cols`` pixel values starting at (col, row)."""


def year_from_filename(name: str) -> int:
    match = re.search(r"(?:doy|\.A)(\d{4})\d{3}", name)
    if match:
        return int(match.group(1))
    years = re.findall(r"(?<!\d)(20\d{2})(?!\d)", name)
    if len(years) != 1:
        raise ValueError(f"cannot infer a single land-cover year from {name!r}")
    return int(years[0])


class MCD12Q1Lookup:
    """Callable ``(lat, lon, year) -> LandCoverSample | None`` for ``classify_observation``.

    ``sources`` maps a land-cover year to the rasters (tiles or one mosaic) of that
    year. The raster year is chosen with ``select_land_cover_year``. ``None`` means
    the point is outside every raster of that year (or no year is available).
    """

    def __init__(
        self,
        sources: Mapping[int, Sequence[RasterSource | Callable[[], RasterSource]]],
        *,
        radius: int = 1,
    ):
        if not isinstance(radius, int) or radius < 0:
            raise ValueError("radius must be a non-negative integer")
        self._sources = {int(year): list(items) for year, items in sources.items()}
        self.radius = radius

    @property
    def years(self) -> list[int]:
        return sorted(self._sources)

    @classmethod
    def from_directory(
        cls,
        directory: str | Path,
        *,
        opener: Callable[[Path], RasterSource] | None = None,
        radius: int = 1,
    ) -> MCD12Q1Lookup:
        """Index GeoTIFFs by year from their file names; files are opened on first use."""
        root = Path(directory)
        if not root.is_dir():
            raise FileNotFoundError(f"land-cover directory not found: {root}")
        open_raster = opener or open_gdal_raster
        grouped: dict[int, list[Callable[[], RasterSource]]] = {}
        for path in sorted(p for p in root.iterdir() if p.is_file() and p.suffix.lower() in RASTER_SUFFIXES):
            grouped.setdefault(year_from_filename(path.name), []).append(_LazySource(path, open_raster))
        if not grouped:
            raise FileNotFoundError(f"no GeoTIFF land-cover raster in {root}")
        return cls(grouped, radius=radius)

    def __call__(self, lat: float, lon: float, year: int) -> LandCoverSample | None:
        if not (math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180):
            raise ValueError(f"invalid coordinates: {lat!r}, {lon!r}")
        chosen = select_land_cover_year(year, self._sources)
        if chosen is None:
            return None
        for item in self._sources[chosen]:
            source = item() if isinstance(item, _LazySource) else item
            pixel = source.grid.pixel_of(lat, lon)
            if pixel is not None:
                return _sample(source, pixel, chosen, self.radius)
        return None


class _LazySource:
    def __init__(self, path: Path, opener: Callable[[Path], RasterSource]):
        self.path, self._opener, self._source = path, opener, None

    def __call__(self) -> RasterSource:
        if self._source is None:
            self._source = self._opener(self.path)
        return self._source


def _class_or_none(value, nodata: int | None) -> int | None:
    value = int(value)
    if value == nodata or value in NO_DATA_CLASSES:
        return None
    if value not in IGBP_CLASSES:
        raise ValueError(f"unexpected LC_Type1 value: {value}")
    return value


def _sample(source: RasterSource, pixel: tuple[int, int], year: int, radius: int) -> LandCoverSample:
    grid = source.grid
    col, row = pixel
    c0, r0 = max(0, col - radius), max(0, row - radius)
    c1, r1 = min(grid.width - 1, col + radius), min(grid.height - 1, row + radius)
    window = source.read(c0, r0, c1 - c0 + 1, r1 - r0 + 1)
    values = [_class_or_none(v, grid.nodata) for line in window for v in line]
    centre = _class_or_none(window[row - r0][col - c0], grid.nodata)
    fraction = None
    if radius > 0 and centre is not None:
        valid = [v for v in values if v is not None]
        fraction = sum(v == centre for v in valid) / len(valid)
    return LandCoverSample(igbp_class=centre, year=year, dominant_fraction=fraction)


class GdalRasterSource:
    """GeoTIFF reader based on GeoDjango's GDAL bindings (already required by the backend)."""

    def __init__(self, path: str | Path):
        from django.contrib.gis.gdal import GDALRaster

        self._raster = GDALRaster(str(path))
        if len(self._raster.bands) != 1:
            raise ValueError(f"{path}: expected a single LC_Type1 band")
        self._band = self._raster.bands[0]
        srs = self._raster.srs
        if srs is None:
            raise ValueError(f"{path}: raster has no spatial reference")
        if srs.geographic:
            kind = "geographic"
        elif "sinusoidal" in srs.wkt.lower() and abs(srs.semi_major - MODIS_SPHERE_RADIUS_M) < 1:
            kind = "sinusoidal"
        else:
            raise ValueError(f"{path}: unsupported projection, expected WGS84 geographic or MODIS sinusoidal")
        nodata = self._band.nodata_value
        self.grid = RasterGrid(
            tuple(self._raster.geotransform), self._raster.width, self._raster.height,
            kind, None if nodata is None else int(nodata),
        )

    def read(self, col: int, row: int, cols: int, rows: int) -> list[list[int]]:
        data = self._band.data(offset=(col, row), size=(cols, rows))
        flat = data.ravel().tolist() if hasattr(data, "ravel") else list(data)
        return [flat[i * cols:(i + 1) * cols] for i in range(rows)]


def open_gdal_raster(path: Path) -> RasterSource:
    return GdalRasterSource(path)
