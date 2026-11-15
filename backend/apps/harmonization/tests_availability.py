"""Missing months must stay missing instead of being turned into recorded zeros."""

from datetime import date

from django.test import SimpleTestCase

from apps.harmonization.management.commands.build_baseline_series import (
    _build_series_from_params,
    _month_bounds,
    _month_is_covered,
    _paired_series,
)

PARAMS = {
    "power_law_p": 1.0,
    "power_law_q": 0.0,
    "terra_only_p": 1.0,
    "terra_only_q": 0.0,
    "conformal_q80_log": 0.25,
    "conformal_q80_terra_log": 0.25,
    "noaa20_to_snpp_ratio": 1.0,
}


class MonthCoverageTests(SimpleTestCase):
    def test_month_bounds_handles_december(self):
        self.assertEqual(
            _month_bounds(date(2012, 12, 15)),
            (date(2012, 12, 1), date(2012, 12, 31)),
        )

    def test_month_is_covered_on_span_boundaries(self):
        coverage = {"viirs-snpp": [(date(2012, 2, 1), date(2012, 4, 30))]}
        self.assertTrue(_month_is_covered(coverage, "viirs-snpp", date(2012, 2, 1)))
        self.assertTrue(_month_is_covered(coverage, "viirs-snpp", date(2012, 4, 1)))
        self.assertFalse(_month_is_covered(coverage, "viirs-snpp", date(2012, 5, 1)))
        self.assertFalse(_month_is_covered(coverage, "modis", date(2012, 3, 1)))

    def test_no_coverage_information_keeps_previous_behaviour(self):
        self.assertTrue(_month_is_covered(None, "modis", date(2012, 3, 1)))


class PairedSeriesCoverageTests(SimpleTestCase):
    months = [date(2012, 2, 1), date(2012, 3, 1), date(2012, 4, 1), date(2012, 5, 1)]

    def setUp(self):
        self.counts = {
            date(2012, 2, 1): {"modis_count": 10, "viirs_snpp_count": 40},
            date(2012, 3, 1): {"modis_count": 20, "viirs_snpp_count": 80},
            date(2012, 4, 1): {"modis_count": 30, "viirs_snpp_count": 120},
        }

    def test_uncovered_month_is_not_paired_as_zero(self):
        coverage = {
            "modis": [(date(2012, 2, 1), date(2012, 4, 30))],
            "viirs-snpp": [(date(2012, 2, 1), date(2012, 4, 30))],
        }
        xs, ys = _paired_series(
            self.counts,
            self.months,
            "modis_count",
            "viirs_snpp_count",
            coverage=coverage,
            x_source="modis",
            y_source="viirs-snpp",
        )
        self.assertEqual(xs, [10.0, 20.0, 30.0])
        self.assertEqual(ys, [40.0, 80.0, 120.0])

    def test_without_coverage_absent_month_still_yields_zero(self):
        xs, _ = _paired_series(
            self.counts, self.months, "modis_count", "viirs_snpp_count"
        )
        self.assertEqual(len(xs), 4)
        self.assertEqual(xs[-1], 0.0)


class BuildSeriesMissingMonthTests(SimpleTestCase):
    counts = {
        date(2012, 2, 1): {"modis_count": 10, "viirs_snpp_count": 40},
        date(2012, 3, 1): {"modis_count": 20, "viirs_snpp_count": 80},
        date(2012, 4, 1): {"modis_count": 30, "viirs_snpp_count": 120},
        date(2012, 6, 1): {"modis_count": 40, "viirs_snpp_count": 160},
    }

    def _by_month(self, series):
        return {item["month"]: item for item in series}

    def test_covered_month_without_detection_is_a_recorded_zero(self):
        coverage = {
            "modis": [(date(2012, 2, 1), date(2012, 6, 30))],
            "viirs-snpp": [(date(2012, 2, 1), date(2012, 6, 30))],
        }
        series = self._by_month(
            _build_series_from_params(self.counts, PARAMS, coverage=coverage)
        )
        may = series[date(2012, 5, 1)]
        self.assertEqual(may["viirs_snpp_count"], 0)
        self.assertEqual(may["harmonized_value"], 0.0)
        self.assertEqual(may["coverage_status"], "complete_sp")

    def test_uncovered_month_stays_missing(self):
        coverage = {
            "modis": [(date(2012, 2, 1), date(2012, 4, 30))],
            "viirs-snpp": [(date(2012, 2, 1), date(2012, 4, 30))],
        }
        series = self._by_month(
            _build_series_from_params(self.counts, PARAMS, coverage=coverage)
        )
        may = series[date(2012, 5, 1)]
        self.assertIsNone(may["viirs_snpp_count"])
        self.assertIsNone(may["harmonized_value"])
        self.assertIsNone(may["ci_low"])
        self.assertIsNone(may["ci_high"])
        self.assertEqual(may["coverage_status"], "no_data")
        self.assertEqual(may["sensor_regime"], "missing")
        self.assertIn("No loaded product covers this month", may["uncertainty_note"])

    def test_june_still_reconstructs_after_a_gap(self):
        coverage = {
            "modis": [(date(2012, 2, 1), date(2012, 4, 30)), (date(2012, 6, 1), date(2012, 6, 30))],
            "viirs-snpp": [
                (date(2012, 2, 1), date(2012, 4, 30)),
                (date(2012, 6, 1), date(2012, 6, 30)),
            ],
        }
        series = self._by_month(
            _build_series_from_params(self.counts, PARAMS, coverage=coverage)
        )
        self.assertIsNone(series[date(2012, 5, 1)]["harmonized_value"])
        self.assertEqual(series[date(2012, 6, 1)]["harmonized_value"], 160.0)
