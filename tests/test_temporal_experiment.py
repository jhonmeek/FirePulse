"""Checks for chronological splits, integrity and model evaluation."""
import json
import tempfile
import unittest
from pathlib import Path

from pipeline.temporal_experiment import fit, metrics, month_range, run


class TemporalExperimentTests(unittest.TestCase):
    def test_windows_include_leap_year_and_year_boundaries(self):
        self.assertEqual(list(month_range("2019-12", "2020-03")), ["2019-12", "2020-01", "2020-02", "2020-03"])

    def test_power_fit_and_metrics(self):
        p, q = fit([1, 2, 3], [1, 2, 3])
        self.assertAlmostEqual(p, 1.0)
        self.assertAlmostEqual(q, 0.0)
        result = metrics([1, 2, 3], [1, 2, 4])
        self.assertAlmostEqual(result["mae"], 1 / 3)
        self.assertAlmostEqual(result["bias"], -1 / 3)

    def test_rejects_changed_calendar(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "calendar.json").write_text("{}", encoding="utf-8")
            (root / "manifest.json").write_text(json.dumps({"calendar_sha256": "0" * 64}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "checksum"):
                run(root / "calendar.json", root / "manifest.json")


if __name__ == "__main__":
    unittest.main()
