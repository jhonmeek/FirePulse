import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from pipeline.compare_postgis_direct import compare
from pipeline.temporal_experiment import month_range


class DirectPostGISTests(unittest.TestCase):
    def test_complete_synthetic_calendar_reconciles_both_geographies(self):
        rows=[]; direct_rows=[]
        for index, month in enumerate(month_range("2012-02", "2025-12")):
            for source,satellite in (("modis","Terra"),("modis","Aqua"),("viirs-snpp","N")):
                count=20+index%12
                rows.append({"month":month,"source":source,"satellite":satellite,"count_raw":count,"status":"observed_detections_recorded"})
                direct_rows.append(f"{month},{source},{satellite},{count},{count-2}\n")
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); calendar=root/"calendar.json"; manifest=root/"manifest.json"; direct=root/"direct.csv"
            calendar.write_text(json.dumps({"rows":rows}),encoding="utf-8")
            manifest.write_text(json.dumps({"calendar_sha256":hashlib.sha256(calendar.read_bytes()).hexdigest()}),encoding="utf-8")
            direct.write_text("month,source,satellite,country_count,ga_count\n"+"".join(direct_rows),encoding="utf-8")
            result=compare(calendar,manifest,direct)
            self.assertEqual(result["direct_rows"],len(rows))
            self.assertEqual(result["country_mismatches"],0)
            self.assertEqual(result["postgis_csv_sha256"],hashlib.sha256(direct.read_bytes()).hexdigest())
            self.assertEqual(sum(result["outside_ga_by_source"].values()),2*len(rows))
            self.assertEqual(result["ga_experiment"]["eligible_months"],result["country_experiment"]["eligible_months"])
            self.assertEqual(result["ga_experiment"]["eligible_months"],{"train":59,"select":36,"calibrate":36,"evaluate":36})
            self.assertIn("ST_Within",result["ga_experiment"]["limitations"][0])
            self.assertIn("Country file",result["country_experiment"]["limitations"][0])
            rows.append(rows[0])
            calendar.write_text(json.dumps({"rows":rows}),encoding="utf-8")
            manifest.write_text(json.dumps({"calendar_sha256":hashlib.sha256(calendar.read_bytes()).hexdigest()}),encoding="utf-8")
            with self.assertRaisesRegex(ValueError,"duplicate calendar"):
                compare(calendar,manifest,direct)

    def test_country_mismatch_fails_before_model_evaluation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); calendar=root/"calendar.json"; manifest=root/"manifest.json"; direct=root/"direct.csv"
            calendar.write_text(json.dumps({"rows":[{"month":"2020-01","source":"modis","satellite":"Terra","count_raw":10}]}),encoding="utf-8")
            manifest.write_text(json.dumps({"calendar_sha256":hashlib.sha256(calendar.read_bytes()).hexdigest()}),encoding="utf-8")
            direct.write_text("month,source,satellite,country_count,ga_count\n2020-01,modis,Terra,9,8\n",encoding="utf-8")
            with self.assertRaisesRegex(ValueError,"does not match PostGIS"):
                compare(calendar,manifest,direct)


if __name__ == "__main__": unittest.main()
