"""Reproduction and provenance checks for the M1 benchmark audit."""
import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from pipeline.benchmark_audit import audit


class BenchmarkAuditTests(unittest.TestCase):
    def _fixture(self, root: Path):
        rows = []
        for year, split in ((2012, "train"), (2020, "test")):
            for month in range(1, 13):
                x = 10 + month
                y = round(2 * x + 3)
                rows.append({"region":"GA","filter_static":"false","month":f"{year}-{month:02d}","calibration_split":split,"modis_count":str(x),"viirs_snpp_count":str(y),"ci_low":str(y),"ci_high":str(y)})
        path = root / "series.csv"
        with path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=rows[0].keys(), lineterminator="\n")
            writer.writeheader(); writer.writerows(rows)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        manifest = root / "manifest.json"
        manifest.write_text(json.dumps({"csv_sha256":digest,"runs":[{"region":"GA","filter_static":False,"params":{"power_law_p":1,"power_law_q":0,"conformal_q80_log":0},"metrics":{"models_out_of_sample":{"power_law_log1p":{"mae":0,"rmse":0,"bias":0,"r2":1}}}}]}), encoding="utf-8")
        return path, manifest

    def test_recalculates_split_metrics_and_marks_interval_non_independent(self):
        with tempfile.TemporaryDirectory() as temp:
            csv_path, manifest = self._fixture(Path(temp))
            result = audit(csv_path, manifest)["results"][0]
            self.assertEqual((result["train_months"], result["test_months"]), (12, 12))
            self.assertLessEqual(result["recomputed_test_metrics"]["mae"], 0.05)
            self.assertEqual(result["test_interval_coverage"], 0.0)
            self.assertFalse(result["interval_coverage_is_independent"])

    def test_rejects_csv_checksum_mismatch(self):
        with tempfile.TemporaryDirectory() as temp:
            csv_path, manifest = self._fixture(Path(temp))
            csv_path.write_text(csv_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                audit(csv_path, manifest)


if __name__ == "__main__":
    unittest.main()
