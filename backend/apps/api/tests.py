"""Integration tests for PostGIS models, FIRMS ingestion helpers, and API v1 endpoints."""

import json
from datetime import date, datetime, timezone

from django.contrib.gis.geos import MultiPolygon, Point, Polygon
from django.db import IntegrityError
from django.test import TestCase
from rest_framework.test import APIClient

from apps.harmonization.models import (
    CalibrationRun,
    CoverageStatusChoices,
    HarmonizedMonthSeries,
    MonthlyBaseline,
    SensorRegimeChoices,
)
from apps.observations.management.commands.import_firms import (
    _infer_source,
    _normalize_confidence,
)
from apps.observations.models import (
    GridCellMonth,
    HotspotObservation,
    ImportBatch,
    Region,
    StaticFlareMaskCell,
)


class FirePulseModelsAndApiTests(TestCase):
    """Verify PostGIS geometries, uniqueness constraints, and API v1 endpoints."""

    def setUp(self) -> None:
        self.client = APIClient()
        gabon_poly = Polygon.from_bbox((8.5, -4.0, 14.6, 2.4))
        self.region = Region.objects.create(
            code="GA",
            name="Gabon",
            region_type="country",
            geom=MultiPolygon(gabon_poly),
            bbox_json=[8.5, -4.0, 14.6, 2.4],
        )
        self.batch = ImportBatch.objects.create(
            source="viirs-snpp",
            processing_level="SP",
            product_version="2",
            file_name="viirs-snpp_2024_Gabon.csv",
            file_sha256="a" * 64,
            row_count=1,
            min_date=date(2024, 8, 1),
            max_date=date(2024, 8, 31),
        )
        self.obs = HotspotObservation.objects.create(
            batch=self.batch,
            source="viirs-snpp",
            satellite="N",
            instrument="VIIRS",
            acquired_at=datetime(2024, 8, 15, 13, 0, tzinfo=timezone.utc),
            position=Point(11.5, -1.5, srid=4326),
            frp=14.2,
            brightness_mir=335.1,
            brightness_tir=294.8,
            confidence_raw="n",
            confidence_tier="nominal",
            daynight="D",
            hotspot_type=0,
            is_static_masked=False,
            product_version="2",
            is_nrt=False,
            original_hash="b" * 64,
        )
        cell_poly = Polygon.from_bbox((11.5, -1.5, 11.75, -1.25))
        self.grid_cell = GridCellMonth.objects.create(
            cell_id="-1.50_11.50",
            geom=cell_poly,
            centroid=Point(11.625, -1.375, srid=4326),
            month=date(2024, 8, 1),
            filter_static=True,
            modis_count=10,
            viirs_snpp_count=42,
        )
        self.static_cell = StaticFlareMaskCell.objects.create(
            cell_id="-1.95_9.85",
            geom=Polygon.from_bbox((9.85, -1.95, 9.90, -1.90)),
            type23_count=1695,
            active_months_snpp=163,
            reason="persistent_flare_site",
        )
        self.run = CalibrationRun.objects.create(
            region=self.region,
            filter_static=True,
            method_name="power_law_log1p_static_masked",
            train_start=date(2012, 2, 1),
            train_end=date(2019, 12, 31),
            test_start=date(2020, 1, 1),
            test_end=date(2025, 12, 31),
            params_json={"power_law_p": 0.953, "power_law_q": 1.606},
            metrics_json={"r2": 0.918, "mae": 103.1},
        )
        MonthlyBaseline.objects.create(
            region=self.region,
            calibration_run=self.run,
            month_num=8,
            filter_static=True,
            baseline_median=1789.0,
            iqr_p25=1111.6,
            iqr_p75=2313.7,
            reference_years_count=25,
        )
        HarmonizedMonthSeries.objects.create(
            region=self.region,
            calibration_run=self.run,
            month=date(2024, 8, 1),
            filter_static=True,
            modis_count=698,
            viirs_snpp_count=3150,
            harmonized_value=3150.0,
            ci_low=3150.0,
            ci_high=3150.0,
            baseline_median=1789.0,
            baseline_iqr_p25=1111.6,
            baseline_iqr_p75=2313.7,
            anomaly_percent=76.1,
            anomaly_absolute=1361.0,
            sensor_regime=SensorRegimeChoices.VIIRS_SNPP_OBSERVED,
            coverage_status=CoverageStatusChoices.COMPLETE_SP,
        )

    def test_postgis_spatial_query(self) -> None:
        self.assertTrue(
            HotspotObservation.objects.filter(position__within=self.region.geom).exists()
        )

    def test_unique_observation_hash_enforced(self) -> None:
        with self.assertRaises(IntegrityError):
            HotspotObservation.objects.create(
                batch=self.batch,
                source="viirs-snpp",
                satellite="N",
                instrument="VIIRS",
                acquired_at=datetime(2024, 8, 15, 13, 0, tzinfo=timezone.utc),
                position=Point(11.5, -1.5, srid=4326),
                confidence_raw="n",
                confidence_tier="nominal",
                daynight="D",
                product_version="2",
                original_hash="b" * 64,
            )

    def test_ingestion_normalization_helpers(self) -> None:
        self.assertEqual(_infer_source("viirs-jpss1_2025_Gabon.csv"), "viirs-noaa20")
        self.assertEqual(_infer_source("modis_2024_Gabon.csv"), "modis")
        self.assertEqual(_normalize_confidence("modis", "85"), "high")
        self.assertEqual(_normalize_confidence("modis", "20"), "low")
        self.assertEqual(_normalize_confidence("viirs-snpp", "n"), "nominal")

    def test_health_and_contract_endpoints(self) -> None:
        health = self.client.get("/api/v1/health/")
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.json()["database"], "connected")
        self.assertEqual(health.json()["counts"]["regions"], 1)

        self.assertEqual(self.client.get("/api/v1/regions/").status_code, 200)

        cov = self.client.get("/api/v1/coverage/")
        self.assertEqual(cov.status_code, 200)
        self.assertEqual(cov.json()["sensors"][0]["operational_end_date"], "2026-11-02")

        cal = self.client.get("/api/v1/calendar/?region=GA")
        self.assertEqual(cal.status_code, 200)
        self.assertEqual(cal.json()["series"][0]["month"], "2024-08")

        bbox_cal = self.client.get("/api/v1/calendar/?bbox=11.0,-2.0,12.0,-1.0")
        self.assertEqual(bbox_cal.status_code, 200)
        self.assertEqual(bbox_cal.json()["series"][0]["viirs_snpp_count"], 42)
        self.assertEqual(bbox_cal.json()["series"][0]["harmonized_value"], 42.0)

        poly_geojson = json.dumps(
            {
                "type": "Polygon",
                "coordinates": [[[11.0, -2.0], [12.0, -2.0], [12.0, -1.0], [11.0, -1.0], [11.0, -2.0]]],
            }
        )
        poly_cal = self.client.get("/api/v1/calendar/", {"polygon": poly_geojson})
        self.assertEqual(poly_cal.status_code, 200)
        self.assertEqual(poly_cal.json()["region"]["id"], "CUSTOM_POLYGON")

        self.assertEqual(self.client.get("/api/v1/anomalies/?region=GA").status_code, 200)

        hotspots = self.client.get("/api/v1/hotspots/?mode=grid&include_static_cells=true")
        self.assertEqual(hotspots.status_code, 200)
        self.assertEqual(len(hotspots.json()["features"]), 2)

        meth = self.client.get("/api/v1/methodology/?region=GA")
        self.assertEqual(meth.status_code, 200)
        self.assertEqual(meth.json()["static_mask_summary"]["masked_cells_count"], 1)

        export = self.client.get("/api/v1/export/?region=GA")
        self.assertEqual(export.status_code, 200)
        self.assertIn("text/csv", export["Content-Type"])
        self.assertIn("2024-08", export.content.decode())

    def test_custom_area_calendar_baseline_ignores_start_end_filter(self) -> None:
        GridCellMonth.objects.create(
            cell_id="-1.50_11.50",
            geom=self.grid_cell.geom,
            centroid=self.grid_cell.centroid,
            month=date(2023, 8, 1),
            filter_static=True,
            modis_count=5,
            viirs_snpp_count=20,
        )
        res = self.client.get("/api/v1/calendar/?bbox=11.0,-2.0,12.0,-1.0&start=2024-08&end=2024-08")
        self.assertEqual(res.status_code, 200)
        payload = res.json()
        self.assertEqual(payload["period"], {"start": "2024-08", "end": "2024-08"})
        self.assertEqual(len(payload["series"]), 1)
        self.assertEqual(payload["series"][0]["month"], "2024-08")
        self.assertEqual(payload["series"][0]["harmonized_value"], 42.0)
        self.assertEqual(payload["series"][0]["baseline_median"], 31.0)
        self.assertAlmostEqual(payload["series"][0]["anomaly_percent"], 35.48, places=2)
