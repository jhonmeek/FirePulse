import csv
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from pipeline.terra_early_audit import MONTHS, audit


class TerraAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.raw = self.root / "raw"
        self.raw.mkdir()
        self.monthly = self.root / "monthly.csv"
        self.raw_rows = {
            2000: [["2000-11-01", "Terra", "MODIS", "0"], ["2000-12-01", "Terra", "MODIS", "2"]],
            2001: [["2001-01-01", "Terra", "MODIS", "0"]],
            2002: [["2002-07-01", "Terra", "MODIS", "0"], ["2002-07-01", "Aqua", "MODIS", "0"]],
        }
        self.monthly_rows = [["GA", "country_file_unverified_geometry", m, "modis", "Terra",
                              "1" if m in ("2000-11", "2000-12", "2001-01", "2002-07") else "0",
                              "1" if m in ("2000-11", "2001-01", "2002-07") else "0"] for m in MONTHS]
        self.write_raw()
        self.write_monthly()

    def write_raw(self):
        for year, rows in self.raw_rows.items():
            with (self.raw / f"modis_{year}_Gabon.csv").open("w", newline="", encoding="utf-8") as stream:
                writer = csv.writer(stream)
                writer.writerow(["acq_date", "satellite", "instrument", "type"])
                writer.writerows(rows)

    def write_monthly(self):
        with self.monthly.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.writer(stream)
            writer.writerow(["region", "dataset_scope", "month", "source", "satellite", "count_raw", "count_type0_candidate"])
            writer.writerows(self.monthly_rows)

    def test_counts_aqua_excluded_zero_month_and_hashes(self):
        result = audit(self.raw, self.monthly)
        self.assertEqual(result["status"], "match")
        self.assertEqual(result["totals"], {"raw_terra": 4, "raw_type0": 3, "months": 26, "mismatched_months": 0})
        july = next(row for row in result["months"] if row["month"] == "2002-07")
        self.assertEqual((july["raw_terra"], july["raw_type0"]), (1, 1))
        self.assertEqual(result["months"][2]["raw_terra"], 1)
        self.assertEqual(result["months"][3]["raw_terra"], 0)
        self.assertEqual(result["input_sha256"][str(self.monthly)], hashlib.sha256(self.monthly.read_bytes()).hexdigest())
        self.assertEqual(len(result["input_sha256"]), 4)

    def test_detection_status_distinguishes_terra_rows_from_coverage(self):
        # Aqua alone does not constitute a Terra detection; type 2 does.
        self.raw_rows[2001].append(["2001-02-01", "Aqua", "MODIS", "0"])
        self.write_raw()
        result = audit(self.raw, self.monthly)
        months = {row["month"]: row for row in result["months"]}
        for month in ("2001-02", "2001-03"):
            self.assertEqual(months[month]["detection_status"], "no_detections_recorded")
            self.assertEqual(months[month]["raw_terra"], 0)
            self.assertTrue(months[month]["match"])
        self.assertEqual(months["2000-12"]["detection_status"], "detections_recorded")
        self.assertEqual(months["2000-12"]["raw_type0"], 0)
        self.assertTrue(all(row["observation_coverage"] == "unknown" for row in result["months"]))
        self.assertEqual(result["totals"]["raw_terra"], 4)

    def test_no_detection_status_survives_monthly_mismatch(self):
        self.monthly_rows[3][5] = "1"
        self.write_monthly()
        result = audit(self.raw, self.monthly)
        month = result["months"][3]
        self.assertEqual(month["detection_status"], "no_detections_recorded")
        self.assertEqual(month["observation_coverage"], "unknown")
        self.assertEqual((month["raw_terra"], month["monthly_terra"], month["difference_terra"]), (0, 1, -1))
        self.assertFalse(month["match"])

    def test_strict_missing_duplicate_and_invalid_inputs(self):
        missing = self.raw / "modis_2001_Gabon.csv"
        missing.unlink()
        with self.assertRaisesRegex(ValueError, "cannot read"):
            audit(self.raw, self.monthly)
        self.write_raw()
        self.raw_rows[2000].append(self.raw_rows[2000][0][:])
        self.write_raw()
        self.monthly_rows[0][5:7] = ["2", "2"]
        self.write_monthly()
        result = audit(self.raw, self.monthly)
        self.assertEqual(result["status"], "match")
        self.assertEqual(result["duplicate_exact_rows"], 1)
        self.raw_rows[2000].pop()
        self.raw_rows[2000][0][0] = "2001-01-01"
        self.write_raw()
        with self.assertRaisesRegex(ValueError, "outside expected"):
            audit(self.raw, self.monthly)

    def test_normalized_satellite_instrument_and_whitespace(self):
        self.raw_rows[2000][0] = [" 2000-11-01 ", " terra ", " modis ", " 0 "]
        self.write_raw()
        self.assertEqual(audit(self.raw, self.monthly)["status"], "match")

    def test_monthly_missing_duplicate_invalid_and_scope(self):
        first = self.monthly_rows.pop(0)
        self.write_monthly()
        with self.assertRaisesRegex(ValueError, "missing monthly"):
            audit(self.raw, self.monthly)
        self.monthly_rows.insert(0, first)
        self.monthly_rows.append(first[:])
        self.write_monthly()
        with self.assertRaisesRegex(ValueError, "duplicate monthly"):
            audit(self.raw, self.monthly)
        self.monthly_rows.pop()
        self.monthly_rows[0][5] = ""
        self.write_monthly()
        with self.assertRaisesRegex(ValueError, "invalid count_raw"):
            audit(self.raw, self.monthly)
        self.monthly_rows[0][5] = "1"
        self.monthly_rows[0][1] = "other"
        self.write_monthly()
        with self.assertRaisesRegex(ValueError, "dataset scope"):
            audit(self.raw, self.monthly)

    def test_cli_mismatch_report_and_no_overwrite(self):
        self.monthly_rows[0][5] = "2"
        self.write_monthly()
        output = self.root / "result.json"
        command = [sys.executable, "-B", "-m", "pipeline.terra_early_audit", "--raw-dir", str(self.raw),
                   "--monthly", str(self.monthly), "--output", str(output)]
        completed = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(completed.returncode, 1, completed.stderr)
        payload = output.read_bytes()
        report = json.loads(payload)
        self.assertEqual(report["status"], "mismatch")
        self.assertEqual(report["months"][0]["difference_terra"], -1)
        self.assertEqual(report["totals"]["mismatched_months"], 1)
        again = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(again.returncode, 2)
        self.assertEqual(output.read_bytes(), payload)


if __name__ == "__main__":
    unittest.main()
