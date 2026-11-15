"""Validate input failures before producing front-bis science artifacts."""
import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "front-bis/scripts/validate_harmonization.py"
SPEC = importlib.util.spec_from_file_location("front_bis_validation", SCRIPT)
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


class InputValidationTests(unittest.TestCase):
    def test_missing_files_stop_before_results(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(module, "RAW", Path(directory)):
            with self.assertRaisesRegex(ValueError, "missing=.*modis_2000"):
                module.load_observations()

    def test_invalid_and_out_of_year_dates_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for prefix, start in (("modis", 2000), ("viirs-snpp", 2012), ("viirs-jpss1", 2018)):
                for year in range(start, 2026):
                    (root / f"{prefix}_{year}_Gabon.csv").write_text("latitude,longitude,type,acq_date,satellite\n", encoding="utf-8")
            source = root / "modis_2000_Gabon.csv"
            with patch.object(module, "RAW", root):
                for date in ("invalid", "2001-01-01"):
                    source.write_text(f"latitude,longitude,type,acq_date,satellite\n0,10,0,{date},Terra\n", encoding="utf-8")
                    with self.subTest(date=date), self.assertRaises(ValueError):
                        module.load_observations()


if __name__ == "__main__":
    unittest.main()
