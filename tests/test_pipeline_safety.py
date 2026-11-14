"""Integration checks for output preservation, repeatability and satellite aliases."""
import json
import tempfile
import unittest
from pathlib import Path

from pipeline.aggregate_monthly import aggregate
from pipeline.normalize import normalize

HEADER = "latitude,longitude,brightness,scan,track,acq_date,acq_time,satellite,instrument,confidence,version,bright_t31,frp,daynight,type\n"
ROW = "0,10,300,1,1,2020-01-01,0,Terra,MODIS,50,6.1,290,2,D,0\n"


def snapshot(directory):
    return {p.name: p.read_bytes() for p in directory.iterdir() if p.is_file()}


class PipelineSafetyTests(unittest.TestCase):
    def test_valid_input_cannot_replace_unmanaged_output(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            raw = root / "raw"
            raw.mkdir()
            (raw / "modis_2020_Gabon.csv").write_text(HEADER + ROW, encoding="utf-8")
            output = root / "output"
            output.mkdir()
            (output / "keep.txt").write_text("existing user content", encoding="utf-8")
            before = snapshot(output)
            with self.assertRaises(ValueError):
                normalize(raw, output)
            self.assertEqual(snapshot(output), before)

    def test_failed_rerun_preserves_published_outputs(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            raw = root / "raw"
            raw.mkdir()
            source = raw / "modis_2020_Gabon.csv"
            source.write_text(HEADER + ROW, encoding="utf-8")
            normal = root / "normalized"
            monthly = root / "monthly"
            normalize(raw, normal)
            aggregate(normal, monthly)
            before_normal = snapshot(normal)
            before_monthly = snapshot(monthly)
            source.write_text(HEADER + ROW.replace(",50,", ",invalid,"), encoding="utf-8")
            with self.assertRaises(ValueError):
                normalize(raw, normal)
            self.assertEqual(snapshot(normal), before_normal)
            # A changed normalized input must not replace a previous monthly export.
            normalized_file = normal / "modis_2020_Gabon_normalized.csv"
            normalized_file.write_bytes(normalized_file.read_bytes() + b"\n")
            with self.assertRaises(ValueError):
                aggregate(normal, monthly)
            self.assertEqual(snapshot(monthly), before_monthly)

    def test_repeated_pipeline_and_alias_preserve_counts(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            raw = root / "raw"
            raw.mkdir()
            viirs_header = HEADER.replace("brightness", "bright_ti4").replace("bright_t31", "bright_ti5")
            row = "0,10,300,1,1,2012-01-20,5,Suomi-NPP,VIIRS,n,2,290,2,N,0\n"
            (raw / "viirs-snpp_2012_Gabon.csv").write_text(viirs_header + row, encoding="utf-8")
            normal = root / "normalized"
            monthly = root / "monthly"
            normalize(raw, normal)
            aggregate(normal, monthly)
            first_normal, first_monthly = snapshot(normal), snapshot(monthly)
            normalize(raw, normal)
            aggregate(normal, monthly)
            self.assertEqual(snapshot(normal), first_normal)
            self.assertEqual(snapshot(monthly), first_monthly)
            calendar = json.loads((monthly / "calendar.json").read_text(encoding="utf-8"))
            january = next(r for r in calendar["rows"] if r["month"] == "2012-01" and r["source"] == "viirs-snpp")
            self.assertEqual(january["satellite"], "N")
            self.assertEqual(january["count_raw"], 1)
            self.assertEqual(january["status"], "partial_period")


if __name__ == "__main__":
    unittest.main()
