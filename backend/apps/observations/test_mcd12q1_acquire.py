"""Unit tests for MCD12Q1 acquisition/cleaning logic (pure Python)."""

import unittest

from apps.observations.mcd12q1_acquire import (
    CELL_SIZE_M, GRID_X0, GRID_Y0, HALF_PX, Block, Mosaic, Window,
    build_mosaics, inverse_sinusoidal, parse_subset, plan_centers, subset_url,
    window_for_bbox, year_chunks,
)
from apps.observations.land_cover import project_sinusoidal


def payload(col0, row0, nrows, ncols, years_values, band="LC_Type1", cell=CELL_SIZE_M):
    return {
        "xllcorner": str(GRID_X0 + col0 * cell),
        "yllcorner": str(GRID_Y0 - (row0 + nrows) * cell),
        "cellsize": cell, "nrows": nrows, "ncols": ncols,
        "subset": [{"modis_date": f"A{y}001", "band": band, "data": list(v)} for y, v in years_values],
    }


class GeometryTests(unittest.TestCase):
    def test_inverse_sinusoidal_roundtrip(self):
        for lat, lon in ((0.39, 9.45), (-3.9, 14.5), (2.3, 8.7)):
            back = inverse_sinusoidal(*project_sinusoidal(lat, lon))
            self.assertAlmostEqual(back[0], lat, places=9)
            self.assertAlmostEqual(back[1], lon, places=9)

    def test_window_covers_bbox_corners(self):
        bbox = (8.57, -4.1, 14.67, 2.47)
        w = window_for_bbox(*bbox)
        for lat in (bbox[1], 0.0, bbox[3]):
            for lon in (bbox[0], bbox[2]):
                x, y = project_sinusoidal(lat, lon)
                col = int((x - GRID_X0) // CELL_SIZE_M)
                row = int((GRID_Y0 - y) // CELL_SIZE_M)
                self.assertTrue(w.col0 <= col < w.col0 + w.ncols and w.row0 <= row < w.row0 + w.nrows)
        with self.assertRaises(ValueError):
            window_for_bbox(10, 0, 9, 1)

    def test_plan_centers_overlap_and_cover(self):
        w = Window(1000, 2000, 1500, 1600)
        centres = plan_centers(w)
        cols = sorted({round((project_sinusoidal(*c)[0] - GRID_X0) / CELL_SIZE_M - 0.5) for c in centres})
        rows = sorted({round((GRID_Y0 - project_sinusoidal(*c)[1]) / CELL_SIZE_M - 0.5) for c in centres})
        self.assertEqual(len(centres), len(cols) * len(rows))
        for axis, start, count in ((cols, w.col0, w.ncols), (rows, w.row0, w.nrows)):
            self.assertLessEqual(axis[0] - HALF_PX, start)
            self.assertGreaterEqual(axis[-1] + HALF_PX, start + count - 1)
            for a, b in zip(axis, axis[1:]):
                self.assertLess(b - HALF_PX, a + HALF_PX)  # overlap

    def test_year_chunks_and_url(self):
        self.assertEqual(year_chunks(range(2001, 2026)), [list(range(2001, 2011)), list(range(2011, 2021)), list(range(2021, 2026))])
        url = subset_url(-0.5, 11.5, [2018, 2019])
        self.assertIn("band=LC_Type1", url)
        self.assertIn("startDate=A2018001&endDate=A2019001", url)
        self.assertIn("kmAboveBelow=100&kmLeftRight=100", url)


class ParseTests(unittest.TestCase):
    def test_parse_valid_subset(self):
        blocks = parse_subset(payload(10, 20, 2, 3, [(2018, [2, 2, 9, 17, 255, 13])]))
        self.assertEqual(blocks, [Block(2018, 10, 20, 3, 2, bytes([2, 2, 9, 17, 255, 13]))])

    def test_rejects_invalid_inputs(self):
        cases = [
            payload(0, 0, 1, 2, [(2018, [2, 18])]),
            payload(0, 0, 1, 2, [(2018, [2])]),
            payload(0, 0, 1, 2, [(2018, [2, 2])], band="LC_Type2"),
            payload(0, 0, 1, 2, [(2018, [2, 2])], cell=500.0),
        ]
        misaligned = payload(0, 0, 1, 2, [(2018, [2, 2])])
        misaligned["xllcorner"] = str(GRID_X0 + 100.0)
        cases.append(misaligned)
        for case in cases:
            with self.assertRaises(ValueError):
                parse_subset(case)


class MosaicTests(unittest.TestCase):
    def test_overlapping_blocks_fill_window(self):
        w = Window(0, 0, 4, 2)
        left = Block(2018, -1, 0, 3, 2, bytes([1, 2, 2, 1, 9, 9]))
        right = Block(2018, 1, -1, 3, 3, bytes([5, 5, 5, 2, 8, 8, 9, 7, 7]))
        mosaic = build_mosaics(w, [2018], [left, right])[2018]
        self.assertEqual(bytes(mosaic.data), bytes([2, 2, 8, 8, 9, 9, 7, 7]))
        self.assertEqual(mosaic.histogram(), {2: 2, 7: 2, 8: 2, 9: 2})

    def test_disagreeing_overlap_is_rejected(self):
        mosaic = Mosaic(Window(0, 0, 2, 1), 2018)
        mosaic.add(Block(2018, 0, 0, 2, 1, bytes([2, 2])))
        with self.assertRaises(ValueError):
            mosaic.add(Block(2018, 1, 0, 1, 1, bytes([9])))

    def test_incomplete_coverage_is_rejected(self):
        with self.assertRaises(ValueError):
            build_mosaics(Window(0, 0, 3, 1), [2018], [Block(2018, 0, 0, 2, 1, bytes([2, 2]))])

    def test_value_at(self):
        w = Window(45000, 21000, 10, 10)
        mosaic = build_mosaics(w, [2018], [Block(2018, 45000, 21000, 10, 10, bytes([2] * 99 + [13]))])[2018]
        lat, lon = inverse_sinusoidal(GRID_X0 + 45009.5 * CELL_SIZE_M, GRID_Y0 - 21009.5 * CELL_SIZE_M)
        self.assertEqual(mosaic.value_at(lat, lon), 13)
        self.assertIsNone(mosaic.value_at(lat + 1, lon))


if __name__ == "__main__":
    unittest.main()
