"""Integration tests for PostGIS models, FIRMS ingestion helpers, and API v1 endpoints."""

import hashlib
import json
import tempfile
from datetime import date, datetime, timezone
from io import StringIO
from pathlib import Path

from django.conf import settings
from django.contrib.gis.geos import MultiPolygon, Point, Polygon
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError
from django.test import TestCase
from django.urls import resolve
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

    def test_anomalies_supports_bbox_and_polygon(self) -> None:
        GridCellMonth.objects.create(
            cell_id="-1.50_11.50",
            geom=self.grid_cell.geom,
            centroid=self.grid_cell.centroid,
            month=date(2023, 8, 1),
            filter_static=True,
            modis_count=5,
            viirs_snpp_count=20,
        )
        res_bbox = self.client.get("/api/v1/anomalies/?bbox=11.0,-2.0,12.0,-1.0&top_n=5")
        self.assertEqual(res_bbox.status_code, 200)
        data = res_bbox.json()
        self.assertEqual(data["region"], "CUSTOM_BBOX")
        self.assertEqual(data["monthly_baselines"][0]["median"], 31.0)
        self.assertEqual(data["top_positive"][0]["month"], "2024-08")
        self.assertAlmostEqual(data["top_positive"][0]["anomaly_percent"], 35.48, places=2)

        poly_geojson = json.dumps(
            {
                "type": "Polygon",
                "coordinates": [[[11.0, -2.0], [12.0, -2.0], [12.0, -1.0], [11.0, -1.0], [11.0, -2.0]]],
            }
        )
        res_poly = self.client.get("/api/v1/anomalies/", {"polygon": poly_geojson})
        self.assertEqual(res_poly.status_code, 200)
        self.assertEqual(res_poly.json()["region"], "CUSTOM_POLYGON")

    def test_export_supports_bbox_polygon_and_points(self) -> None:
        exp_bbox = self.client.get("/api/v1/export/?bbox=11.0,-2.0,12.0,-1.0")
        self.assertEqual(exp_bbox.status_code, 200)
        self.assertIn("CUSTOM_BBOX,2024-08", exp_bbox.content.decode())

        exp_pts = self.client.get("/api/v1/export/?dataset=points&region=GA&month=2024-08")
        self.assertEqual(exp_pts.status_code, 200)
        body = exp_pts.content.decode()
        self.assertIn("latitude,longitude", body)
        self.assertIn("GA,viirs-snpp", body)

        bad_pts = self.client.get("/api/v1/export/?dataset=points&region=GA")
        self.assertEqual(bad_pts.status_code, 400)

    def test_hotspots_supports_polygon_start_end_and_agg_cell(self) -> None:
        GridCellMonth.objects.create(
            cell_id="-1.50_11.50",
            geom=self.grid_cell.geom,
            centroid=self.grid_cell.centroid,
            month=date(2023, 8, 1),
            filter_static=True,
            modis_count=5,
            viirs_snpp_count=20,
        )
        poly_geojson = json.dumps(
            {
                "type": "Polygon",
                "coordinates": [[[11.0, -2.0], [12.0, -2.0], [12.0, -1.0], [11.0, -1.0], [11.0, -2.0]]],
            }
        )
        res = self.client.get(
            "/api/v1/hotspots/",
            {
                "mode": "grid",
                "agg": "cell",
                "start": "2023-08",
                "end": "2024-08",
                "polygon": poly_geojson,
            },
        )
        self.assertEqual(res.status_code, 200)
        features = res.json()["features"]
        self.assertEqual(len(features), 1)
        self.assertEqual(features[0]["properties"]["layer"], "grid_cell_summary")
        self.assertEqual(features[0]["properties"]["months_count"], 2)
        self.assertEqual(features[0]["properties"]["modis_count"], 15)
        self.assertEqual(features[0]["properties"]["viirs_snpp_count"], 62)

    def test_coverage_exposes_product_versions(self) -> None:
        cov = self.client.get("/api/v1/coverage/")
        self.assertEqual(cov.status_code, 200)
        self.assertEqual(cov.json()["sensors"][0]["product_versions"], ["2"])

    def test_build_baseline_series_from_pipeline_bundle(self) -> None:
        bundle = {
            "method_name": "m1_validated_power_law",
            "method_version": "v2.1-m1",
            "reference_scale": "VIIRS_375m_SNPP_equiv",
            "regions": [
                {
                    "region": "GA",
                    "filter_static": True,
                    "params": {"power_law_p": 0.94, "power_law_q": 1.65},
                    "metrics": {"test_months": 72, "models_out_of_sample": {"power_law_log1p": {"r2": 0.92}}},
                    "baselines": [
                        {
                            "month_num": 8,
                            "baseline_median": 1700.0,
                            "iqr_p25": 1100.0,
                            "iqr_p75": 2200.0,
                            "reference_years_count": 25,
                            "reference_period": "2001-2025",
                        }
                    ],
                    "series": [
                        {
                            "month": "2024-08",
                            "modis_count": 900,
                            "modis_terra_count": 270,
                            "modis_aqua_count": 630,
                            "viirs_snpp_count": 3000,
                            "viirs_noaa20_count": 2800,
                            "harmonized_value": 3000.0,
                            "ci_low": 2800.0,
                            "ci_high": 3200.0,
                            "baseline_median": 1700.0,
                            "sensor_regime": "viirs_snpp_observed",
                            "coverage_status": "complete_sp",
                        }
                    ],
                }
            ],
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            bundle_path = Path(tmpdir) / "pipeline_bundle.json"
            bundle_path.write_text(json.dumps(bundle), encoding="utf-8")
            call_command("build_baseline_series", from_pipeline=str(bundle_path), stdout=StringIO())

        meth = self.client.get("/api/v1/methodology/?region=GA")
        self.assertEqual(meth.status_code, 200)
        self.assertEqual(meth.json()["active_run"]["method_version"], "v2.1-m1")

        cal = self.client.get("/api/v1/calendar/?region=GA")
        self.assertEqual(cal.status_code, 200)
        self.assertEqual(cal.json()["series"][0]["harmonized_value"], 3000.0)
        self.assertAlmostEqual(cal.json()["series"][0]["anomaly_percent"], 76.47, places=2)

    def test_api_contract_routes_resolve_and_respond(self) -> None:
        contract_path = next(
            (
                p
                for p in (
                    Path(settings.BASE_DIR).parent / "docs" / "api-contract.json",
                    Path("/docs/api-contract.json"),
                )
                if p.exists()
            ),
            None,
        )
        self.assertIsNotNone(contract_path, "docs/api-contract.json must exist")
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
        endpoints = contract["endpoints"]
        self.assertGreaterEqual(len(endpoints), 8)

        sample_queries = {
            "/api/v1/regions/": {"include_geom": "false"},
            "/api/v1/calendar/": {"region": "GA", "start": "2024-08", "end": "2024-08"},
            "/api/v1/anomalies/": {"region": "GA", "top_n": "1"},
            "/api/v1/hotspots/": {"mode": "grid", "month": "2024-08", "limit": "1"},
            "/api/v1/methodology/": {"region": "GA"},
            "/api/v1/export/": {"region": "GA", "start": "2024-08", "end": "2024-08"},
        }

        for endpoint_key in endpoints:
            method, path = endpoint_key.split(" ", 1)
            self.assertEqual(method, "GET")
            match = resolve(path)
            self.assertIsNotNone(match)
            res = self.client.get(path, sample_queries.get(path, {}))
            self.assertEqual(res.status_code, 200, f"Unexpected status for {path}: {res.content}")

    def test_build_baseline_series_from_m1_directory_csv_and_checksum(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            mdir = Path(tmpdir)
            csv_path = mdir / "monthly_counts.csv"
            csv_path.write_text(
                "\n".join(
                    [
                        "region,dataset_scope,month,source,satellite,count_raw,count_type0_candidate,harmonized_value,status,observation_coverage",
                        "GA,country_file_unverified_geometry,2000-11,modis,Terra,37,10,,observed_detections_recorded,unknown",
                        "GA,country_file_unverified_geometry,2000-11,modis,Aqua,,,,not_available,unknown",
                        "GA,country_file_unverified_geometry,2000-11,viirs-snpp,N,,,,not_available,unknown",
                        "GA,country_file_unverified_geometry,2012-01,modis,Terra,50,20,,observed_detections_recorded,unknown",
                        "GA,country_file_unverified_geometry,2012-01,modis,Aqua,60,30,,observed_detections_recorded,unknown",
                        "GA,country_file_unverified_geometry,2012-01,viirs-snpp,N,12,10,,partial_period,unknown",
                        "GA,country_file_unverified_geometry,2024-08,modis,Terra,100,80,,observed_detections_recorded,unknown",
                        "GA,country_file_unverified_geometry,2024-08,modis,Aqua,200,120,,observed_detections_recorded,unknown",
                        "GA,country_file_unverified_geometry,2024-08,viirs-snpp,N,400,320,,observed_detections_recorded,unknown",
                        "GA,country_file_unverified_geometry,2024-08,viirs-noaa20,N20,390,300,,observed_detections_recorded,unknown",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            csv_sha = hashlib.sha256(csv_path.read_bytes()).hexdigest()
            manifest_path = mdir / "manifest.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "artifact_kind": "firepulse-monthly",
                        "schema_version": 1,
                        "scope": "GA country-file; geometry unverified",
                        "monthly_csv_sha256": csv_sha,
                    }
                ),
                encoding="utf-8",
            )

            call_command("build_baseline_series", from_pipeline=str(mdir), stdout=StringIO())

            run_filt = CalibrationRun.objects.get(region=self.region, filter_static=True, is_active=True)
            self.assertEqual(run_filt.method_name, "m1_monthly_type0_candidate_power_law")
            self.assertEqual(run_filt.metrics_json["m1_provenance"]["static_flare_mask_applied"], False)
            self.assertEqual(run_filt.metrics_json["m1_provenance"]["input_sha256"], csv_sha)

            row_aug = HarmonizedMonthSeries.objects.get(
                region=self.region,
                calibration_run=run_filt,
                month=date(2024, 8, 1),
            )
            self.assertEqual(row_aug.viirs_snpp_count, 320)
            self.assertEqual(row_aug.harmonized_value, 320.0)

            manifest_path.write_text(
                json.dumps(
                    {
                        "artifact_kind": "firepulse-monthly",
                        "schema_version": 1,
                        "monthly_csv_sha256": "0" * 64,
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaises(CommandError):
                call_command("build_baseline_series", from_pipeline=str(mdir), stdout=StringIO())

    def test_build_baseline_series_from_repo_m1_monthly_dir(self) -> None:
        monthly_dir = next(
            (
                p
                for p in (
                    Path(settings.BASE_DIR).parent / "data" / "processed" / "monthly",
                    Path("/data/processed/monthly"),
                )
                if p.exists()
            ),
            None,
        )
        if monthly_dir is None:
            self.skipTest("data/processed/monthly not mounted in this test environment")

        call_command("build_baseline_series", from_pipeline=str(monthly_dir), stdout=StringIO())

        run_filt = CalibrationRun.objects.get(region=self.region, filter_static=True, is_active=True)
        run_raw = CalibrationRun.objects.get(region=self.region, filter_static=False, is_active=True)
        self.assertEqual(run_filt.method_name, "m1_monthly_type0_candidate_power_law")
        self.assertEqual(run_raw.method_name, "m1_monthly_raw_power_law")
        self.assertEqual(
            HarmonizedMonthSeries.objects.filter(region=self.region, calibration_run=run_filt).count(),
            302,
        )
        cal = self.client.get("/api/v1/calendar/?region=GA&start=2000-11&end=2025-12")
        self.assertEqual(cal.status_code, 200)
        self.assertEqual(len(cal.json()["series"]), 302)
        meth = self.client.get("/api/v1/methodology/?region=GA")
        self.assertEqual(meth.status_code, 200)
        self.assertFalse(meth.json()["active_run"]["metrics"]["m1_provenance"]["static_flare_mask_applied"])
