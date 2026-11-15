"""Unit tests for the MCD12Q1 land-cover lookup (pure Python + optional GDAL)."""

import math
import tempfile
import unittest
from pathlib import Path

from apps.observations.fire_typing import classify_observation
from apps.observations.land_cover import (
    MCD12Q1Lookup,
    RasterGrid,
    modis_tile,
    project_sinusoidal,
    year_from_filename,
)


class FakeSource:
    """In-memory raster: ``rows`` is a list of lists of IGBP codes."""

    def __init__(self, rows, geotransform, crs_kind="geographic", nodata=255):
        self.rows = rows
        self.grid = RasterGrid(geotransform, len(rows[0]), len(rows), crs_kind, nodata)
        self.reads = 0

    def read(self, col, row, cols, nrows):
        self.reads += 1
        return [r[col:col + cols] for r in self.rows[row:row + nrows]]


# 5x5 grid, 0.01 deg pixels, upper-left corner at (lon 10.0, lat 0.0)
GEO = (10.0, 0.01, 0.0, 0.0, 0.0, -0.01)
FOREST = [[2] * 5 for _ in range(5)]


def point(col, row):
    """Centre of pixel (col, row) in GEO as (lat, lon)."""
    return -(row + 0.5) * 0.01, 10.0 + (col + 0.5) * 0.01


class ProjectionTests(unittest.TestCase):
    def test_sinusoidal_matches_modis_grid_constants(self):
        self.assertEqual(project_sinusoidal(0, 0), (0.0, 0.0))
        x, _ = project_sinusoidal(0, 180)
        self.assertAlmostEqual(x, 20015109.354, places=2)
        x, y = project_sinusoidal(10, 0)
        self.assertAlmostEqual(y, 1111950.5197, places=3)  # one MODIS tile height
        x, _ = project_sinusoidal(60, 10)
        self.assertAlmostEqual(x, 1111950.5197 / 2, places=3)

    def test_modis_tiles_over_gabon(self):
        self.assertEqual(modis_tile(0.39, 9.45), "h18v08")  # Libreville
        self.assertEqual(modis_tile(-1.63, 13.58), "h19v09")  # Franceville

    def test_rotated_raster_is_rejected(self):
        with self.assertRaises(ValueError):
            RasterGrid((10.0, 0.01, 0.001, 0.0, 0.0, -0.01), 5, 5, "geographic", 255)
        with self.assertRaises(ValueError):
            RasterGrid(GEO, 5, 5, "mercator", 255)


class SamplingTests(unittest.TestCase):
    def test_homogeneous_window(self):
        lookup = MCD12Q1Lookup({2018: [FakeSource(FOREST, GEO)]})
        sample = lookup(*point(2, 2), 2018)
        self.assertEqual(sample.igbp_class, 2)
        self.assertEqual(sample.year, 2018)
        self.assertEqual(sample.dominant_fraction, 1.0)

    def test_fraction_counts_centre_class_over_valid_neighbours(self):
        rows = [r[:] for r in FOREST]
        rows[1][1] = rows[1][2] = 9   # two savanna cells in the 3x3 window
        rows[3][3] = 255               # nodata ignored in the denominator
        sample = MCD12Q1Lookup({2018: [FakeSource(rows, GEO)]})(*point(2, 2), 2018)
        self.assertEqual(sample.igbp_class, 2)
        self.assertAlmostEqual(sample.dominant_fraction, 6 / 8)

    def test_window_is_clipped_at_raster_edge(self):
        rows = [r[:] for r in FOREST]
        rows[0][1] = 12
        sample = MCD12Q1Lookup({2018: [FakeSource(rows, GEO)]})(*point(0, 0), 2018)
        self.assertAlmostEqual(sample.dominant_fraction, 3 / 4)

    def test_radius_zero_gives_no_fraction(self):
        sample = MCD12Q1Lookup({2018: [FakeSource(FOREST, GEO)]}, radius=0)(*point(2, 2), 2018)
        self.assertIsNone(sample.dominant_fraction)

    def test_nodata_centre_returns_sample_without_class(self):
        rows = [r[:] for r in FOREST]
        rows[2][2] = 255
        sample = MCD12Q1Lookup({2018: [FakeSource(rows, GEO)]})(*point(2, 2), 2018)
        self.assertIsNone(sample.igbp_class)
        self.assertEqual(sample.year, 2018)

    def test_custom_nodata_value(self):
        rows = [r[:] for r in FOREST]
        rows[2][2] = 254
        sample = MCD12Q1Lookup({2018: [FakeSource(rows, GEO, nodata=254)]})(*point(2, 2), 2018)
        self.assertIsNone(sample.igbp_class)

    def test_unexpected_value_is_rejected(self):
        rows = [r[:] for r in FOREST]
        rows[2][3] = 42
        with self.assertRaises(ValueError):
            MCD12Q1Lookup({2018: [FakeSource(rows, GEO)]})(*point(2, 2), 2018)

    def test_outside_every_raster_returns_none(self):
        lookup = MCD12Q1Lookup({2018: [FakeSource(FOREST, GEO)]})
        self.assertIsNone(lookup(1.0, 10.02, 2018))
        self.assertIsNone(lookup(-0.02, 9.99, 2018))
        self.assertIsNone(lookup(-0.02, 10.05, 2018))  # right edge is exclusive

    def test_invalid_coordinates_are_rejected(self):
        lookup = MCD12Q1Lookup({2018: [FakeSource(FOREST, GEO)]})
        for lat, lon in ((91, 0), (0, 181), (math.nan, 0)):
            with self.assertRaises(ValueError):
                lookup(lat, lon, 2018)

    def test_year_selection_and_tiles(self):
        west = FakeSource([[9] * 5 for _ in range(5)], GEO)
        east = FakeSource(FOREST, (10.05, 0.01, 0.0, 0.0, 0.0, -0.01))
        lookup = MCD12Q1Lookup({2010: [FakeSource([[12] * 5] * 5, GEO)], 2023: [west, east]})
        self.assertEqual(lookup(*point(1, 1), 2026).year, 2023)   # latest earlier year
        self.assertEqual(lookup(*point(1, 1), 2026).igbp_class, 9)
        self.assertEqual(lookup(-0.015, 10.065, 2026).igbp_class, 2)  # second tile
        self.assertEqual(lookup(*point(1, 1), 2005).year, 2010)    # earliest later year
        self.assertEqual(lookup(*point(1, 1), 2010).igbp_class, 12)
        self.assertIsNone(MCD12Q1Lookup({})(*point(1, 1), 2010))

    def test_sinusoidal_source(self):
        # 3x3 MODIS pixels centred on lat 0 / lon 0
        px = 463.312716528
        source = FakeSource([[9, 9, 9], [9, 8, 9], [9, 9, 9]], (-1.5 * px, px, 0.0, 1.5 * px, 0.0, -px), "sinusoidal")
        sample = MCD12Q1Lookup({2018: [source]})(0.0, 0.0, 2018)
        self.assertEqual(sample.igbp_class, 8)
        self.assertAlmostEqual(sample.dominant_fraction, 1 / 9)

    def test_plugs_into_classify_observation(self):
        lookup = MCD12Q1Lookup({2018: [FakeSource(FOREST, GEO)]})
        lat, lon = point(2, 2)
        payload = classify_observation({"latitude": lat, "longitude": lon, "acquired_at": "2018-08-15", "hotspot_type": 0}, lookup)
        self.assertEqual(payload["land_cover"]["category"], "tropical_forest")
        self.assertEqual(payload["classification"]["status"], "inferred")


class DirectoryTests(unittest.TestCase):
    def test_year_from_filename(self):
        self.assertEqual(year_from_filename("MCD12Q1.061_LC_Type1_doy2018001_aid0001.tif"), 2018)
        self.assertEqual(year_from_filename("MCD12Q1.A2019001.h19v09.061.2022169161028.tif"), 2019)
        self.assertEqual(year_from_filename("lc_type1_2021.tif"), 2021)
        for bad in ("landcover.tif", "lc_2018_2019.tif"):
            with self.assertRaises(ValueError):
                year_from_filename(bad)

    def test_from_directory_groups_by_year_and_opens_lazily(self):
        opened = []

        def opener(path):
            opened.append(path.name)
            return FakeSource(FOREST, GEO)

        with tempfile.TemporaryDirectory() as tmp:
            for name in ("lc_2018_h18v08.tif", "lc_2018_h19v09.tif", "lc_2020.tiff", "notes.txt"):
                (Path(tmp) / name).write_bytes(b"")
            lookup = MCD12Q1Lookup.from_directory(tmp, opener=opener)
            self.assertEqual(lookup.years, [2018, 2020])
            self.assertEqual(opened, [])
            lookup(*point(2, 2), 2018)
            lookup(*point(2, 2), 2018)
            self.assertEqual(sorted(opened), ["lc_2018_h18v08.tif"])  # first tile matched, cached

    def test_from_directory_requires_rasters(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(FileNotFoundError):
                MCD12Q1Lookup.from_directory(tmp, opener=lambda p: None)
            with self.assertRaises(FileNotFoundError):
                MCD12Q1Lookup.from_directory(Path(tmp) / "missing", opener=lambda p: None)


def _gdal_available():
    try:
        from django.contrib.gis.gdal import GDALRaster  # noqa: F401
        from django.contrib.gis.gdal.libgdal import gdal_version  # noqa: F401
        gdal_version()
        return True
    except Exception:
        return False


@unittest.skipUnless(_gdal_available(), "GDAL/GeoDjango not available")
class GdalGeoTiffTests(unittest.TestCase):
    def _write(self, directory, name, srid, origin, scale, data, width=3, height=3):
        from django.contrib.gis.gdal import GDALRaster

        path = Path(directory) / name
        GDALRaster({
            "driver": "GTiff", "name": str(path), "srid": srid, "width": width, "height": height,
            "origin": origin, "scale": scale, "datatype": 1,
            "bands": [{"data": data, "nodata_value": 255}],
        })
        return path

    def test_reads_geographic_geotiff(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._write(tmp, "MCD12Q1.061_LC_Type1_doy2018001_aid0001.tif", 4326, (10.0, 0.0), (0.01, -0.01),
                        [9, 9, 9, 9, 2, 9, 9, 9, 255])
            sample = MCD12Q1Lookup.from_directory(tmp)(-0.015, 10.015, 2018)
            self.assertEqual(sample.igbp_class, 2)
            self.assertAlmostEqual(sample.dominant_fraction, 1 / 8)
            self.assertIsNone(MCD12Q1Lookup.from_directory(tmp)(-0.025, 10.025, 2018).igbp_class)

    def test_rejects_unsupported_projection(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._write(tmp, "lc_2018.tif", 3857, (0.0, 0.0), (500.0, -500.0), [2] * 9)
            with self.assertRaises(ValueError):
                MCD12Q1Lookup.from_directory(tmp)(-0.001, 0.001, 2018)


if __name__ == "__main__":
    unittest.main()
