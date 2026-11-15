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
    def test_calibration_order_statistic(self):
        self.assertEqual(module.split_conformal_quantile(list(range(1, 25)), .8), 20)
        self.assertEqual(module.split_conformal_quantile(list(range(1, 25)), .9), 23)
        self.assertEqual(module.split_conformal_quantile([1, 1, 2, 2], .6), 2)
        for scores, level in (([], .8), ([1], .99), ([1], 1), ([float('nan')], .5)):
            with self.subTest(scores=scores, level=level), self.assertRaises(ValueError):
                module.split_conformal_quantile(scores, level)

    def test_power_law_does_not_predict_negative_counts(self):
        self.assertEqual(module.predict_power_law(0, 1, -1), 0)
        self.assertAlmostEqual(module.predict_power_law(2, 1, 0), 2)

    def test_mask_excludes_calibration_and_test_observations(self):
        cell = (1, 2)
        observations = [("2017-12", 2017, "terra", 2, cell)] * 19
        observations += [("2018-01", 2018, "terra", 2, cell)]
        self.assertEqual(module.MASK_MAX_YEAR, 2017)
        self.assertNotIn(cell, module.build_mask(observations, module.MASK_MAX_YEAR))
        self.assertIn(cell, module.build_mask(observations, 2018))

    def test_missing_sensor_month_is_not_treated_as_zero(self):
        observations = [("2017-01", 2017, "terra", 0, (1, 1))]
        with self.assertRaisesRegex(ValueError, "Missing recorded sensor-months"):
            module.require_recorded_months(observations, ["2017-01"])

    def test_missing_noaa_calibration_does_not_invent_ratio(self):
        observations = [
            ("2017-01", 2017, "terra", 0, (1, 1)),
            ("2017-01", 2017, "snpp", 0, (1, 1)),
            ("2020-01", 2020, "noaa20", 0, (1, 1)),
        ]
        with patch.object(module, "load_observations", return_value=(observations, [])), patch.object(module, "require_recorded_months", return_value={(x[0], x[2]) for x in observations}):
            result = module.validate()
        noaa = result["held_out"]["noaa20"]
        self.assertIsNone(result["params"]["noaa20_to_snpp_ratio"])
        self.assertIsNone(noaa["raw"])
        self.assertIsNone(noaa["anomaly"])
        self.assertIn("indisponible", noaa["limitation"])
        self.assertEqual(result["mask"]["frozen_on"], "2000–2017")

    def test_noaa_ratio_uses_calibration_not_test(self):
        observations = [
            ("2018-01", 2018, "snpp", 0, (1, 1)),
            ("2018-01", 2018, "noaa20", 0, (1, 1)),
            ("2018-01", 2018, "noaa20", 0, (1, 1)),
        ] + [("2020-01", 2020, "noaa20", 0, (1, 1))] * 5
        with patch.object(module, "load_observations", return_value=(observations, [])), patch.object(module, "require_recorded_months", return_value={(x[0], x[2]) for x in observations}):
            result = module.validate()
        self.assertEqual(result["params"]["noaa20_to_snpp_ratio"], 2)
        self.assertEqual(result["held_out"]["noaa20"]["calibration_months"], 1)
        self.assertIsNotNone(result["held_out"]["noaa20"]["raw"])

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
