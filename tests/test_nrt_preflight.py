import tempfile
import unittest
from pathlib import Path
from pipeline.nrt_preflight import inspect_csv


class NrtPreflightTests(unittest.TestCase):
    def test_missing_type_is_unavailable_not_zero(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/"nrt.csv"
            path.write_text("latitude,longitude,acq_date,acq_time,version\n0,10,2026-11-14,45,2NRT\n",encoding="utf-8")
            report=inspect_csv(path)
            self.assertFalse(report["type_column_present"])
            self.assertEqual(report["counts"]["type_unavailable"],1)
            self.assertNotIn("type_0",report["counts"])
            self.assertEqual(report["first_date"],"2026-11-14")
            self.assertEqual(report["years"],{"2026":1})
            self.assertEqual(report["invalid"],{})

    def test_invalid_coordinates_and_type_are_reported(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/"nrt.csv"
            path.write_text("latitude,longitude,acq_date,acq_time,version,type\nnan,10,2026-11-14,2460,2NRT,9\n",encoding="utf-8")
            report=inspect_csv(path)
            self.assertEqual(report["invalid"],{"coordinates":1,"time":1,"type":1})


if __name__ == "__main__": unittest.main()
