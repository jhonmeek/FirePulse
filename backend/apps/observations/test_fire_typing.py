"""Unit tests for hotspot type classification (pure Python, no database)."""

import unittest

from apps.observations.fire_typing import (
    CAUSE_UNKNOWN,
    LandCoverSample,
    classify_hotspot,
    classify_observation,
    select_land_cover_year,
)


def sample(igbp, year=2018, fraction=None):
    return LandCoverSample(igbp_class=igbp, year=year, dominant_fraction=fraction)


class ThermalTypeTests(unittest.TestCase):
    def test_volcano_static_and_offshore_are_not_landscape_classified(self):
        for code, thermal in ((1, "presumed_volcanic"), (2, "other_static_land_source"), (3, "offshore_or_water")):
            result = classify_hotspot(code, sample(2))
            self.assertEqual(result.thermal_type, thermal)
            self.assertEqual(result.thermal_type_status, "provided")
            self.assertEqual(result.landscape, "not_applicable")
            self.assertEqual(result.status, "not_applicable")
            self.assertEqual(result.cause, CAUSE_UNKNOWN)

    def test_missing_type_is_never_replaced_by_vegetation(self):
        result = classify_hotspot(None, sample(9))
        self.assertEqual(result.thermal_type, "unavailable")
        self.assertEqual(result.thermal_type_status, "unavailable")
        self.assertEqual(result.landscape, "savanna")
        self.assertEqual(result.status, "inferred")
        self.assertIn("thermal_type_unavailable", result.flags)

    def test_invalid_type_is_rejected(self):
        for bad in (4, -1, "0", True, 1.0):
            with self.assertRaises(ValueError):
                classify_hotspot(bad, sample(2))


class LandscapeTests(unittest.TestCase):
    def test_igbp_classes_map_to_landscapes(self):
        expected = {
            1: "forest", 2: "tropical_forest", 3: "forest", 4: "forest", 5: "forest",
            6: "shrubland", 7: "shrubland", 8: "savanna", 9: "savanna", 10: "grassland",
            11: "wetland", 12: "cropland", 13: "urban", 14: "cropland_mosaic",
        }
        for igbp, landscape in expected.items():
            result = classify_hotspot(0, sample(igbp))
            self.assertEqual(result.landscape, landscape, igbp)
            self.assertEqual(result.status, "inferred", igbp)
            self.assertEqual(result.land_cover["igbp_class"], igbp)

    def test_vegetation_fire_on_non_burnable_cover_is_indeterminate(self):
        for igbp, landscape in ((15, "snow_ice"), (16, "barren"), (17, "water")):
            result = classify_hotspot(0, sample(igbp))
            self.assertEqual(result.landscape, landscape)
            self.assertEqual(result.status, "indeterminate")
            self.assertIn("land_cover_inconsistent_with_thermal_type", result.flags)

    def test_missing_or_unclassified_land_cover_is_unavailable(self):
        for lc in (None, sample(255), sample(0)):
            result = classify_hotspot(0, lc)
            self.assertEqual(result.landscape, "unknown")
            self.assertEqual(result.status, "unavailable")

    def test_invalid_igbp_class_is_rejected(self):
        for bad in (18, -3, 254, "2"):
            with self.assertRaises(ValueError):
                classify_hotspot(0, sample(bad))

    def test_heterogeneous_neighbourhood_is_mixed(self):
        result = classify_hotspot(0, sample(2, fraction=0.5))
        self.assertEqual(result.landscape, "mixed")
        self.assertEqual(result.status, "indeterminate")
        self.assertEqual(result.land_cover["category"], "tropical_forest")
        homogeneous = classify_hotspot(0, sample(2, fraction=0.9))
        self.assertEqual(homogeneous.landscape, "tropical_forest")
        self.assertEqual(classify_hotspot(0, sample(2, fraction=0.5), mixed_threshold=0.4).landscape, "tropical_forest")

    def test_invalid_fraction_is_rejected(self):
        for bad in (-0.1, 1.5, float("nan")):
            with self.assertRaises(ValueError):
                classify_hotspot(0, sample(2, fraction=bad))


class PersistenceAndYearTests(unittest.TestCase):
    def test_persistent_cell_without_type_is_indeterminate(self):
        result = classify_hotspot(None, sample(2), in_persistent_cell=True)
        self.assertEqual(result.status, "indeterminate")
        self.assertIn("persistent_thermal_cell", result.flags)
        self.assertTrue(result.in_persistent_cell)

    def test_persistent_cell_is_flag_only_when_type_is_vegetation(self):
        result = classify_hotspot(0, sample(2), in_persistent_cell=True)
        self.assertEqual(result.status, "inferred")
        self.assertIn("persistent_thermal_cell", result.flags)

    def test_year_offset_is_flagged(self):
        result = classify_hotspot(0, sample(2, year=2023), detection_year=2026)
        self.assertEqual(result.land_cover["year_offset"], -3)
        self.assertIn("land_cover_year_mismatch", result.flags)
        same = classify_hotspot(0, sample(2, year=2018), detection_year=2018)
        self.assertNotIn("land_cover_year_mismatch", same.flags)

    def test_select_land_cover_year(self):
        years = [2001, 2002, 2010, 2023]
        self.assertEqual(select_land_cover_year(2010, years), 2010)
        self.assertEqual(select_land_cover_year(2026, years), 2023)
        self.assertEqual(select_land_cover_year(2005, years), 2002)
        self.assertEqual(select_land_cover_year(2000, years), 2001)
        self.assertIsNone(select_land_cover_year(2010, []))


class ObservationAdapterTests(unittest.TestCase):
    def test_classifies_nrt_observation_dict_with_lookup(self):
        calls = []

        def lookup(lat, lon, year):
            calls.append((lat, lon, year))
            return sample(8, year=2023)

        observation = {"latitude": -1.5, "longitude": 11.2, "acquired_at": "2026-11-14T00:41:00Z", "type_nasa": None}
        payload = classify_observation(observation, lookup)
        self.assertEqual(calls, [(-1.5, 11.2, 2026)])
        self.assertEqual(payload["thermal_type"], "unavailable")
        self.assertEqual(payload["land_cover"]["category"], "savanna")
        self.assertEqual(payload["land_cover"]["source"], "NASA MCD12Q1 C6.1 LC_Type1 (IGBP)")
        self.assertEqual(payload["classification"]["cause"], "unknown")
        self.assertEqual(payload["classification"]["method"], "firms_type_and_land_cover_overlay")
        self.assertEqual(payload["classification"]["label"], "Point chaud en savane")

    def test_reads_hotspot_type_key_and_handles_missing_lookup_result(self):
        payload = classify_observation(
            {"latitude": 0, "longitude": 10, "acquired_at": "2018-08-15", "hotspot_type": 0},
            lambda lat, lon, year: None,
        )
        self.assertEqual(payload["thermal_type"], "presumed_vegetation_fire")
        self.assertEqual(payload["classification"]["status"], "unavailable")
        self.assertIsNone(payload["land_cover"])


if __name__ == "__main__":
    unittest.main()
