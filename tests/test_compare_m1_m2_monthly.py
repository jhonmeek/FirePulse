import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from pipeline.compare_m1_m2_monthly import compare


class ComparisonTests(unittest.TestCase):
    def test_preserves_missing_and_compares_unfiltered_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            calendar=root/"calendar.json"; manifest=root/"monthly.json"; export=root/"m2.csv"; metadata=root/"m2.json"
            rows=[{"month":"2020-01","source":"modis","satellite":"Terra","status":"observed_detections_recorded","count_raw":10}, {"month":"2020-02","source":"modis","satellite":"Terra","status":"missing_input","count_raw":None}]
            calendar.write_text(json.dumps({"rows":rows}),encoding="utf-8")
            manifest.write_text(json.dumps({"calendar_sha256":hashlib.sha256(calendar.read_bytes()).hexdigest()}),encoding="utf-8")
            with export.open("w",encoding="utf-8",newline="") as f:
                writer=csv.DictWriter(f,fieldnames=["region","filter_static","month","modis_terra_count"]); writer.writeheader()
                writer.writerow({"region":"GA","filter_static":"false","month":"2020-01","modis_terra_count":"7"})
                writer.writerow({"region":"GA","filter_static":"true","month":"2020-01","modis_terra_count":"4"})
                writer.writerow({"region":"GA","filter_static":"false","month":"2020-02","modis_terra_count":"0"})
            metadata.write_text(json.dumps({"artifact_kind":"firepulse-m2-calibration-series","csv_sha256":hashlib.sha256(export.read_bytes()).hexdigest()}),encoding="utf-8")
            result=compare(calendar,manifest,export,metadata)
            self.assertEqual(result["rows"][0]["difference"],3)
            self.assertIsNone(result["rows"][1]["difference"])
            self.assertEqual(result["totals"]["modis_outside_or_difference"],3)
            export.write_bytes(export.read_bytes()+b"x")
            with self.assertRaisesRegex(ValueError,"checksum"):
                compare(calendar,manifest,export,metadata)


if __name__ == "__main__": unittest.main()
