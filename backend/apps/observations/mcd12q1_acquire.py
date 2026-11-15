"""Acquire and clean MCD12Q1 C6.1 LC_Type1 (IGBP) over a bounding box.

Source: NASA ORNL DAAC MODIS/VIIRS web service (no account required),
https://modis.ornl.gov/data/modis_webservice.html. Each request returns a
401 x 401 pixel subset (about 186 km) on the native MODIS sinusoidal grid for at
most 10 annual dates. Subsets are placed on that grid without resampling.

Cleaning rules (any violation aborts, nothing is silently fixed):
- cell size and corner must fall on the native 463.3127 m grid;
- band must be LC_Type1 and every value an IGBP class (1-17) or fill (255);
- overlapping subsets must agree pixel by pixel;
- the requested window must be fully covered for every year.
Fill value 255 is kept as nodata; no gap filling, no reclassification.

Pure Python (stdlib only); GeoTIFF writing is done by the management command.
"""
from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from apps.observations.fire_typing import IGBP_CLASSES
from apps.observations.land_cover import MODIS_GRID_HALF_WIDTH_M, MODIS_SPHERE_RADIUS_M, project_sinusoidal

ORNL_API = "https://modis.ornl.gov/rst/api/v1"
PRODUCT = "MCD12Q1"
BAND = "LC_Type1"
CELL_SIZE_M = 463.312716528
GRID_X0 = -MODIS_GRID_HALF_WIDTH_M
GRID_Y0 = 10007554.677
FILL = 255
VALID_VALUES = frozenset(IGBP_CLASSES) | {FILL}
HALF_KM = 100            # kmAboveBelow / kmLeftRight -> 401 pixels
HALF_PX = 200
MAX_DATES_PER_REQUEST = 10
SINUSOIDAL_PROJ4 = f"+proj=sinu +lon_0=0 +x_0=0 +y_0=0 +R={MODIS_SPHERE_RADIUS_M} +units=m +no_defs"


def inverse_sinusoidal(x: float, y: float) -> tuple[float, float]:
    lat = math.degrees(y / MODIS_SPHERE_RADIUS_M)
    lon = math.degrees(x / (MODIS_SPHERE_RADIUS_M * math.cos(math.radians(lat))))
    return lat, lon


@dataclass(frozen=True)
class Window:
    """Rectangle of the global MODIS 500 m grid (global column/row indices)."""

    col0: int
    row0: int
    ncols: int
    nrows: int

    @property
    def geotransform(self) -> tuple[float, float, float, float, float, float]:
        return (GRID_X0 + self.col0 * CELL_SIZE_M, CELL_SIZE_M, 0.0,
                GRID_Y0 - self.row0 * CELL_SIZE_M, 0.0, -CELL_SIZE_M)


def window_for_bbox(west: float, south: float, east: float, north: float) -> Window:
    if not (west < east and south < north):
        raise ValueError("invalid bounding box")
    lats = [south, north] + ([0.0] if south < 0 < north else [])
    xs = [project_sinusoidal(lat, lon)[0] for lat in lats for lon in (west, east)]
    col0 = math.floor((min(xs) - GRID_X0) / CELL_SIZE_M)
    col1 = math.floor((max(xs) - GRID_X0) / CELL_SIZE_M)
    row0 = math.floor((GRID_Y0 - project_sinusoidal(north, 0)[1]) / CELL_SIZE_M)
    row1 = math.floor((GRID_Y0 - project_sinusoidal(south, 0)[1]) / CELL_SIZE_M)
    return Window(col0, row0, col1 - col0 + 1, row1 - row0 + 1)


def plan_centers(window: Window, step_px: int = 360) -> list[tuple[float, float]]:
    """Lat/lon request centres whose 401 px subsets overlap and cover the window."""
    if not 0 < step_px <= 2 * HALF_PX - 20:
        raise ValueError("step must leave an overlap between subsets")

    def axis(start: int, count: int) -> list[int]:
        first, last = start + HALF_PX - 10, start + count - 1
        centres = [first]
        while centres[-1] + HALF_PX - 10 < last:
            centres.append(centres[-1] + step_px)
        return centres

    points = []
    for row in axis(window.row0, window.nrows):
        for col in axis(window.col0, window.ncols):
            x = GRID_X0 + (col + 0.5) * CELL_SIZE_M
            y = GRID_Y0 - (row + 0.5) * CELL_SIZE_M
            lat, lon = inverse_sinusoidal(x, y)
            points.append((round(lat, 6), round(lon, 6)))
    return points


def year_chunks(years: Sequence[int]) -> list[list[int]]:
    ordered = sorted(set(years))
    return [ordered[i:i + MAX_DATES_PER_REQUEST] for i in range(0, len(ordered), MAX_DATES_PER_REQUEST)]


def subset_url(lat: float, lon: float, years: Sequence[int]) -> str:
    return (f"{ORNL_API}/{PRODUCT}/subset?latitude={lat}&longitude={lon}&band={BAND}"
            f"&startDate=A{min(years)}001&endDate=A{max(years)}001"
            f"&kmAboveBelow={HALF_KM}&kmLeftRight={HALF_KM}")


@dataclass(frozen=True)
class Block:
    year: int
    col0: int
    row0: int
    ncols: int
    nrows: int
    data: bytes  # row-major, north row first


def _grid_index(value: float, origin: float, label: str) -> int:
    index = (value - origin) / CELL_SIZE_M
    if abs(index - round(index)) > 1e-3:
        raise ValueError(f"{label} is not aligned on the MODIS grid: {value}")
    return round(index)


def parse_subset(payload: dict) -> list[Block]:
    """Validate one ORNL subset response and split it into yearly blocks."""
    if abs(float(payload["cellsize"]) - CELL_SIZE_M) > 1e-6:
        raise ValueError(f"unexpected cell size {payload['cellsize']}")
    nrows, ncols = int(payload["nrows"]), int(payload["ncols"])
    col0 = _grid_index(float(payload["xllcorner"]), GRID_X0, "xllcorner")
    bottom = _grid_index(GRID_Y0 - float(payload["yllcorner"]), 0.0, "yllcorner")
    row0 = bottom - nrows
    blocks = []
    for item in payload["subset"]:
        if item["band"] != BAND:
            raise ValueError(f"unexpected band {item['band']}")
        date = item["modis_date"]
        if len(date) != 8 or not date.startswith("A") or not date.endswith("001"):
            raise ValueError(f"unexpected date {date}")
        values = item["data"]
        if len(values) != nrows * ncols:
            raise ValueError(f"{date}: {len(values)} values for {nrows}x{ncols}")
        bad = {v for v in values if v not in VALID_VALUES}
        if bad:
            raise ValueError(f"{date}: values outside LC_Type1 domain {sorted(bad)[:5]}")
        blocks.append(Block(int(date[1:5]), col0, row0, ncols, nrows, bytes(values)))
    return blocks


class Mosaic:
    """One year of LC_Type1 over a window, assembled from overlapping blocks."""

    def __init__(self, window: Window, year: int):
        self.window, self.year = window, year
        size = window.ncols * window.nrows
        self.data = bytearray([FILL]) * size
        self.covered = bytearray(size)
        self.blocks = 0

    def add(self, block: Block) -> None:
        if block.year != self.year:
            raise ValueError("block year mismatch")
        w = self.window
        c_start, c_end = max(block.col0, w.col0), min(block.col0 + block.ncols, w.col0 + w.ncols)
        r_start, r_end = max(block.row0, w.row0), min(block.row0 + block.nrows, w.row0 + w.nrows)
        if c_start >= c_end or r_start >= r_end:
            return
        width = c_end - c_start
        for row in range(r_start, r_end):
            src = (row - block.row0) * block.ncols + (c_start - block.col0)
            dst = (row - w.row0) * w.ncols + (c_start - w.col0)
            incoming = block.data[src:src + width]
            if any(self.covered[dst:dst + width]):
                current, cov = self.data[dst:dst + width], self.covered[dst:dst + width]
                for i in range(width):
                    if cov[i] and current[i] != incoming[i]:
                        raise ValueError(f"{self.year}: overlapping subsets disagree at row {row}, col {c_start + i}")
            self.data[dst:dst + width] = incoming
            self.covered[dst:dst + width] = b"\x01" * width
        self.blocks += 1

    def uncovered(self) -> int:
        return self.covered.count(0)

    def histogram(self) -> dict[int, int]:
        return {v: n for v in sorted(VALID_VALUES) if (n := self.data.count(v))}

    def value_at(self, lat: float, lon: float) -> int | None:
        x, y = project_sinusoidal(lat, lon)
        col = math.floor((x - GRID_X0) / CELL_SIZE_M) - self.window.col0
        row = math.floor((GRID_Y0 - y) / CELL_SIZE_M) - self.window.row0
        if 0 <= col < self.window.ncols and 0 <= row < self.window.nrows:
            return self.data[row * self.window.ncols + col]
        return None


def build_mosaics(window: Window, years: Iterable[int], blocks: Iterable[Block]) -> dict[int, Mosaic]:
    mosaics = {year: Mosaic(window, year) for year in years}
    for block in blocks:
        if block.year in mosaics:
            mosaics[block.year].add(block)
    for year, mosaic in mosaics.items():
        missing = mosaic.uncovered()
        if missing:
            raise ValueError(f"{year}: {missing} pixels of the window are not covered")
    return mosaics
