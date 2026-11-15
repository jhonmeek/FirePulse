"""Integration tests for PostGIS models, FIRMS ingestion helpers, and API v1 endpoints."""

import csv
import hashlib
import json
import tempfile
from datetime import date, datetime, timedelta, timezone
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.contrib.gis.geos import MultiPolygon, Point, Polygon
from django.core.cache import cache
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import DatabaseError, IntegrityError
from django.test import TestCase, override_settings
from django.urls import resolve
from rest_framework.test import APIClient

from apps.api.cache import invalidate_api_cache
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

    def test_recent_unknown_nrt_detections_are_separate_from_filtered_points(self) -> None:
        now = datetime(2026, 11, 15, 12, 0, tzinfo=timezone.utc)
        def add(suffix, *, days=0, hotspot_type=None, inside=True, canonical=True, nrt=True):
            return HotspotObservation.objects.create(
                batch=self.batch, source="viirs-noaa20", satellite="N20", instrument="VIIRS",
                acquired_at=now - timedelta(days=days),
                position=Point(11.5 if inside else 30, -1.5, srid=4326),
                confidence_raw="n", confidence_tier="nominal", daynight="D",
                hotspot_type=hotspot_type, product_version="2.0NRT", is_nrt=nrt,
                counts_in_aggregates=canonical, original_hash=suffix * 64,
            )
        wanted = add("1")
        add("2", days=3)
        add("3", hotspot_type=0)
        add("4", inside=False)
        add("5", canonical=False)
        add("6", nrt=False)
        with patch("apps.api.views.timezone.now", return_value=now):
            res = self.client.get("/api/v1/recent-unknown-detections/?region=GA&days=2&limit=10")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["type"], "FeatureCollection")
        self.assertEqual([f["properties"]["id"] for f in body["features"]], [wanted.id])
        self.assertEqual(body["features"][0]["properties"]["hotspot_type"], None)
        self.assertEqual(body["features"][0]["properties"]["processing_level"], "NRT")
        self.assertIn("not confirmed wildfires", body["caution"])
        self.assertIn("filtered", body["provenance"])
        self.assertEqual(res["Cache-Control"], "no-store")
        filtered = self.client.get("/api/v1/hotspots/?mode=points&month=2026-11&region=GA&filter_static=true")
        self.assertEqual(filtered.status_code, 200)
        self.assertEqual(len(filtered.json()["features"]), 1)
        self.assertEqual(filtered.json()["features"][0]["properties"]["hotspot_type"], 0)

    def test_recent_unknown_detections_reject_unbounded_requests(self) -> None:
        for query in ("days=0", "days=6", "days=x", "limit=0", "limit=1001", "region=ZZ"):
            self.assertEqual(self.client.get(f"/api/v1/recent-unknown-detections/?{query}").status_code, 400)

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
        self.assertTrue(
            any(
                "0.05° candidate cells" in item
                and "not individually ground-verified industrial facilities" in item
                for item in meth.json()["limitations"]
            )
        )

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

    def test_api_response_cache_hits_and_signal_invalidation(self) -> None:
        cache.clear()
        invalidate_api_cache()

        first = self.client.get("/api/v1/calendar/?region=GA")
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first["X-FirePulse-Cache"], "MISS")
        self.assertIn("public", first["Cache-Control"])

        second = self.client.get("/api/v1/calendar/?region=GA")
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second["X-FirePulse-Cache"], "HIT")
        self.assertEqual(second.json(), first.json())

        row = HarmonizedMonthSeries.objects.get(
            region=self.region,
            calibration_run=self.run,
            month=date(2024, 8, 1),
        )
        row.uncertainty_note = "Updated note invalidates cache"
        row.save()

        third = self.client.get("/api/v1/calendar/?region=GA")
        self.assertEqual(third.status_code, 200)
        self.assertEqual(third["X-FirePulse-Cache"], "MISS")
        self.assertEqual(third.json()["series"][0]["uncertainty_note"], "Updated note invalidates cache")

        bad = self.client.get("/api/v1/calendar/?bbox=invalid")
        self.assertEqual(bad.status_code, 400)
        self.assertEqual(bad["X-FirePulse-Cache"], "BYPASS")
        self.assertEqual(bad["Cache-Control"], "no-store")

    def test_hotspots_points_and_regions_include_geom_flag(self) -> None:
        pts = self.client.get("/api/v1/hotspots/?mode=points&month=2024-08&limit=10")
        self.assertEqual(pts.status_code, 200)
        features = pts.json()["features"]
        self.assertEqual(len(features), 1)
        self.assertEqual(features[0]["properties"]["layer"], "hotspot_point")
        self.assertEqual(features[0]["geometry"]["type"], "Point")

        no_geom = self.client.get("/api/v1/regions/?include_geom=false")
        self.assertEqual(no_geom.status_code, 200)
        self.assertIsNone(no_geom.json()["regions"][0]["geometry"])

        with_geom = self.client.get("/api/v1/regions/?include_geom=true")
        self.assertEqual(with_geom.status_code, 200)
        self.assertEqual(with_geom.json()["regions"][0]["geometry"]["type"], "MultiPolygon")

    def test_missing_firms_type_is_visible_only_in_raw_point_api(self) -> None:
        unknown = HotspotObservation.objects.create(
            batch=self.batch,
            source="viirs-noaa20",
            satellite="N20",
            instrument="VIIRS",
            acquired_at=datetime(2024, 8, 16, 13, 0, tzinfo=timezone.utc),
            position=Point(11.6, -1.6, srid=4326),
            confidence_raw="n",
            confidence_tier="nominal",
            daynight="D",
            hotspot_type=None,
            is_static_masked=False,
            product_version="2.0NRT",
            is_nrt=True,
            original_hash="c" * 64,
        )
        self.assertIsNone(unknown.hotspot_type)
        for hotspot_type, is_static_masked, observation_hash in (
            (0, True, "d" * 64),
            (2, False, "e" * 64),
        ):
            HotspotObservation.objects.create(
                batch=self.batch,
                source="viirs-noaa20",
                satellite="N20",
                instrument="VIIRS",
                acquired_at=datetime(2024, 8, 17, 13, hotspot_type, tzinfo=timezone.utc),
                position=Point(11.7 + hotspot_type / 100, -1.7, srid=4326),
                confidence_raw="n",
                confidence_tier="nominal",
                daynight="D",
                hotspot_type=hotspot_type,
                is_static_masked=is_static_masked,
                product_version="2.0NRT",
                is_nrt=True,
                original_hash=observation_hash,
            )

        url = "/api/v1/hotspots/?mode=points&region=GA&month=2024-08&limit=10"
        raw = self.client.get(f"{url}&filter_static=false")
        self.assertEqual(raw.status_code, 200)
        raw_types = [feature["properties"]["hotspot_type"] for feature in raw.json()["features"]]
        self.assertCountEqual(raw_types, [None, 0, 0, 2])

        filtered = self.client.get(f"{url}&filter_static=true")
        self.assertEqual(filtered.status_code, 200)
        self.assertEqual(
            [feature["properties"]["hotspot_type"] for feature in filtered.json()["features"]],
            [0],
        )

        export_url = "/api/v1/export/?dataset=points&region=GA&month=2024-08"
        raw_export = self.client.get(f"{export_url}&filter_static=false")
        self.assertEqual(raw_export.status_code, 200)
        raw_rows = list(csv.DictReader(StringIO(raw_export.content.decode("utf-8"))))
        self.assertCountEqual([row["hotspot_type"] for row in raw_rows], ["", "0", "0", "2"])

        filtered_export = self.client.get(f"{export_url}&filter_static=true")
        self.assertEqual(filtered_export.status_code, 200)
        filtered_rows = list(csv.DictReader(StringIO(filtered_export.content.decode("utf-8"))))
        self.assertEqual([row["hotspot_type"] for row in filtered_rows], ["0"])

    def test_health_returns_503_json_on_database_error(self) -> None:
        with patch("apps.api.views.connection.cursor", side_effect=DatabaseError("db offline")):
            res = self.client.get("/api/v1/health/")
        self.assertEqual(res.status_code, 503)
        self.assertEqual(res.json()["status"], "error")
        self.assertEqual(res.json()["database"], "disconnected")
        self.assertEqual(res["Cache-Control"], "no-store")

    def test_nrt_and_mixed_coverage_status_on_2026_observations(self) -> None:
        batch_nrt = ImportBatch.objects.create(
            source="viirs-snpp",
            processing_level="NRT",
            product_version="2.0NRT",
            file_name="viirs-snpp_2026_nrt.csv",
            file_sha256="c" * 64,
            row_count=2,
            min_date=date(2026, 9, 1),
            max_date=date(2026, 9, 20),
        )
        HotspotObservation.objects.create(
            batch=batch_nrt,
            source="viirs-snpp",
            satellite="N",
            instrument="VIIRS",
            acquired_at=datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc),
            position=Point(11.5, -1.5, srid=4326),
            frp=9.0,
            brightness_mir=330.0,
            brightness_tir=295.0,
            confidence_raw="n",
            confidence_tier="nominal",
            daynight="D",
            hotspot_type=0,
            is_static_masked=False,
            product_version="2",
            is_nrt=False,
            original_hash="d" * 64,
        )
        HotspotObservation.objects.create(
            batch=batch_nrt,
            source="viirs-snpp",
            satellite="N",
            instrument="VIIRS",
            acquired_at=datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc),
            position=Point(11.6, -1.6, srid=4326),
            frp=11.0,
            brightness_mir=332.0,
            brightness_tir=296.0,
            confidence_raw="n",
            confidence_tier="nominal",
            daynight="D",
            hotspot_type=0,
            is_static_masked=False,
            product_version="2.0NRT",
            is_nrt=True,
            original_hash="e" * 64,
        )
        HotspotObservation.objects.create(
            batch=batch_nrt,
            source="viirs-noaa20",
            satellite="N20",
            instrument="VIIRS",
            acquired_at=datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc),
            position=Point(11.5, -1.5, srid=4326),
            frp=13.0,
            brightness_mir=334.0,
            brightness_tir=297.0,
            confidence_raw="n",
            confidence_tier="nominal",
            daynight="D",
            hotspot_type=0,
            is_static_masked=False,
            product_version="2.0NRT",
            is_nrt=True,
            original_hash="f" * 64,
        )

        call_command("build_baseline_series", stdout=StringIO())

        mixed_row = HarmonizedMonthSeries.objects.get(
            region=self.region,
            filter_static=True,
            calibration_run__is_active=True,
            month=date(2026, 9, 1),
        )
        self.assertEqual(mixed_row.coverage_status, CoverageStatusChoices.MIXED_SP_NRT)
        self.assertEqual(mixed_row.sensor_regime, SensorRegimeChoices.VIIRS_SNPP_OBSERVED)

        bridge_row = HarmonizedMonthSeries.objects.get(
            region=self.region,
            filter_static=True,
            calibration_run__is_active=True,
            month=date(2026, 11, 1),
        )
        self.assertEqual(bridge_row.coverage_status, CoverageStatusChoices.NRT_ONLY)
        self.assertEqual(bridge_row.sensor_regime, SensorRegimeChoices.VIIRS_NOAA20_BRIDGE)

    def test_export_demo_snapshot_writes_verified_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            call_command("export_demo_snapshot", output=tmpdir, stdout=StringIO())
            out = Path(tmpdir)
            manifest_path = out / "snapshot_manifest.json"
            self.assertTrue(manifest_path.exists())
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["artifact_kind"], "firepulse-demo-snapshot")
            self.assertIn("GA", manifest["regions"])
            exported_names = {entry["file"] for entry in manifest["files"]}
            for expected_file in (
                "calendar_GA_static.json",
                "anomalies_GA_static.json",
                "methodology_GA_static.json",
                "hotspots_grid_cell_GA_static.json",
                "hotspots_grid_monthly_static.json",
                "hotspots_grid_monthly_raw.json",
                "hotspots_static_mask_GA.json",
            ):
                self.assertIn(expected_file, exported_names)
            for entry in manifest["files"]:
                fpath = out / entry["file"]
                self.assertTrue(fpath.exists(), f"Missing snapshot file {entry['file']}")
                self.assertEqual(
                    hashlib.sha256(fpath.read_bytes()).hexdigest(),
                    entry["sha256"],
                )

            call_command("export_demo_snapshot", output=tmpdir, verify=True, stdout=StringIO())
            (out / "coverage.json").write_text('{"corrupted": true}\n', encoding="utf-8")
            with self.assertRaises(CommandError):
                call_command("export_demo_snapshot", output=tmpdir, verify=True, stdout=StringIO())

    def test_export_calibration_series_writes_verified_csv_and_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "m2_calibration_monthly_series.csv"
            sha_path = Path(f"{csv_path}.sha256")
            call_command(
                "export_calibration_series",
                output=str(csv_path),
                source_commit="deadbeef",
                db_source="test-postgis",
                stdout=StringIO(),
            )
            manifest_path = Path(tmpdir) / "manifest.json"
            self.assertTrue(csv_path.exists())
            self.assertTrue(sha_path.exists())
            self.assertTrue(manifest_path.exists())

            raw_bytes = csv_path.read_bytes()
            expected_sha = hashlib.sha256(raw_bytes).hexdigest()
            self.assertNotIn(b"\r\n", raw_bytes)
            self.assertEqual(sha_path.read_text(encoding="utf-8"), f"{expected_sha}  {csv_path.name}\n")
            with csv_path.open("r", encoding="utf-8", newline="") as fh:
                rows = list(csv.DictReader(fh))
            self.assertEqual(len(rows), HarmonizedMonthSeries.objects.filter(calibration_run__is_active=True).count())
            first = rows[0]
            self.assertEqual(first["region"], "GA")
            self.assertIn(first["filter_static"], {"true", "false"})
            self.assertIn("modis_terra_count", first)
            self.assertIn("modis_aqua_count", first)
            self.assertIn("calibration_split", first)

            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["artifact_kind"], "firepulse-m2-calibration-series")
            self.assertEqual(manifest["source_commit"], "deadbeef")
            self.assertEqual(manifest["db_provenance"]["db_source"], "test-postgis")
            self.assertEqual(manifest["csv_sha256"], expected_sha)
            self.assertEqual(manifest["row_count"], len(rows))
            self.assertTrue(manifest["runs"])
            self.assertIn("params", manifest["runs"][0])

            call_command("export_calibration_series", output=str(csv_path), verify=True, stdout=StringIO())
            csv_path.write_text("tampered\n", encoding="utf-8")
            with self.assertRaises(CommandError):
                call_command("export_calibration_series", output=str(csv_path), verify=True, stdout=StringIO())

    def test_offline_snapshot_fallback_serves_api_without_database(self) -> None:
        live_csv = self.client.get("/api/v1/export/?dataset=series&region=GA")
        self.assertEqual(live_csv.status_code, 200)
        live_csv_text = live_csv.content.decode("utf-8")

        GridCellMonth.objects.create(
            cell_id="-4.00_5.00",
            geom=Polygon.from_bbox((5.0, -4.0, 5.25, -3.75)),
            centroid=Point(5.125, -3.875, srid=4326),
            month=date(2024, 8, 1),
            filter_static=True,
            modis_count=5,
            viirs_snpp_count=9,
        )
        online_ga_cells = {
            f["properties"]["cell_id"]
            for f in self.client.get(
                "/api/v1/hotspots/?region=GA&start=2001-01&end=2025-12&filter_static=true&mode=grid&agg=cell&include_static_cells=true&limit=5000"
            ).json()["features"]
        }
        self.assertNotIn("-4.00_5.00", online_ga_cells)
        online_no_region_cells = {
            f["properties"]["cell_id"]
            for f in self.client.get(
                "/api/v1/hotspots/?month=2024-08&filter_static=true&mode=grid&agg=month"
            ).json()["features"]
        }
        self.assertIn("-4.00_5.00", online_no_region_cells)

        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir)
            call_command("export_demo_snapshot", output=tmpdir, stdout=StringIO())
            cache.clear()
            invalidate_api_cache()

            with override_settings(DEMO_SNAPSHOT_DIR=out, FORCE_SNAPSHOT_FALLBACK=True):
                health = self.client.get("/api/v1/health/")
                self.assertEqual(health.status_code, 200)
                self.assertEqual(health["X-FirePulse-Fallback"], "ready")

                with self.assertNumQueries(0):
                    reg_no_geom = self.client.get("/api/v1/regions/?include_geom=false")
                    self.assertEqual(reg_no_geom.status_code, 200)
                    self.assertEqual(reg_no_geom["X-FirePulse-Cache"], "FALLBACK")
                    self.assertIsNone(reg_no_geom.json()["regions"][0]["geometry"])

                    cov = self.client.get("/api/v1/coverage/?region=GA")
                    self.assertEqual(cov.status_code, 200)
                    self.assertEqual(cov["X-FirePulse-Cache"], "FALLBACK")

                    cal = self.client.get("/api/v1/calendar/?region=GA&start=2024-08&end=2024-08")
                    self.assertEqual(cal.status_code, 200)
                    self.assertEqual(cal["X-FirePulse-Cache"], "FALLBACK")
                    self.assertEqual(cal.json()["period"], {"start": "2024-08", "end": "2024-08"})

                    anom = self.client.get("/api/v1/anomalies/?region=GA&start=2024-08&end=2024-08&top_n=1")
                    self.assertEqual(anom.status_code, 200)
                    self.assertEqual(anom["X-FirePulse-Cache"], "FALLBACK")
                    self.assertEqual(len(anom.json()["top_positive"]), 1)

                    meth = self.client.get("/api/v1/methodology/?region=GA&filter_static=true")
                    self.assertEqual(meth.status_code, 200)
                    self.assertEqual(meth["X-FirePulse-Cache"], "FALLBACK")

                    spots = self.client.get("/api/v1/hotspots/?mode=grid&agg=cell&region=GA&include_static_cells=true")
                    self.assertEqual(spots.status_code, 200)
                    self.assertEqual(spots["X-FirePulse-Cache"], "FALLBACK")
                    layers = {f["properties"]["layer"] for f in spots.json()["features"]}
                    self.assertIn("grid_cell_summary", layers)
                    self.assertIn("static_flare_mask", layers)

                    spots_range = self.client.get(
                        "/api/v1/hotspots/?region=GA&start=2001-01&end=2025-12&filter_static=true&mode=grid&agg=cell&include_static_cells=true&limit=5000"
                    )
                    self.assertEqual(spots_range.status_code, 200)
                    self.assertEqual(spots_range["X-FirePulse-Cache"], "FALLBACK")
                    spots_range_data = spots_range.json()
                    self.assertEqual(spots_range_data["mode"], "grid")
                    self.assertEqual(spots_range_data["agg"], "cell")
                    range_layers = {f["properties"]["layer"] for f in spots_range_data["features"]}
                    self.assertIn("grid_cell_summary", range_layers)
                    self.assertIn("static_flare_mask", range_layers)
                    range_cids = {f["properties"]["cell_id"] for f in spots_range_data["features"]}
                    self.assertIn("-1.50_11.50", range_cids)
                    self.assertNotIn("-4.00_5.00", range_cids)

                    spots_month = self.client.get(
                        "/api/v1/hotspots/?region=GA&month=2024-08&filter_static=true&mode=grid&agg=cell&include_static_cells=true"
                    )
                    self.assertEqual(spots_month.status_code, 200)
                    self.assertEqual(spots_month["X-FirePulse-Cache"], "FALLBACK")
                    grid_features = [
                        f for f in spots_month.json()["features"] if f["properties"]["layer"] == "grid_cell_summary"
                    ]
                    self.assertEqual(len(grid_features), 1)
                    self.assertEqual(grid_features[0]["properties"]["cell_id"], "-1.50_11.50")
                    self.assertEqual(grid_features[0]["properties"]["viirs_snpp_count"], 42)

                    spots_agg_month = self.client.get(
                        "/api/v1/hotspots/?region=GA&start=2024-08&end=2024-08&filter_static=true&mode=grid&agg=month"
                    )
                    self.assertEqual(spots_agg_month.status_code, 200)
                    self.assertEqual(spots_agg_month["X-FirePulse-Cache"], "FALLBACK")
                    agg_month_features = spots_agg_month.json()["features"]
                    self.assertEqual(len(agg_month_features), 1)
                    self.assertEqual(agg_month_features[0]["properties"]["cell_id"], "-1.50_11.50")
                    self.assertEqual(agg_month_features[0]["properties"]["layer"], "grid_cell_month")
                    self.assertEqual(agg_month_features[0]["properties"]["month"], "2024-08")

                    spots_no_region = self.client.get(
                        "/api/v1/hotspots/?month=2024-08&filter_static=true&mode=grid&agg=month"
                    )
                    self.assertEqual(spots_no_region.status_code, 200)
                    self.assertEqual(spots_no_region["X-FirePulse-Cache"], "FALLBACK")
                    self.assertEqual(
                        {f["properties"]["cell_id"] for f in spots_no_region.json()["features"]},
                        {"-1.50_11.50", "-4.00_5.00"},
                    )

                    spots_bbox = self.client.get(
                        "/api/v1/hotspots/?bbox=11.0,-2.0,12.0,-1.0&start=2024-08&end=2024-08&filter_static=true&mode=grid&agg=cell&include_static_cells=true"
                    )
                    self.assertEqual(spots_bbox.status_code, 200)
                    self.assertEqual(spots_bbox["X-FirePulse-Cache"], "FALLBACK")
                    bbox_cell_ids = {f["properties"]["cell_id"] for f in spots_bbox.json()["features"]}
                    self.assertIn("-1.50_11.50", bbox_cell_ids)
                    self.assertNotIn("-1.95_9.85", bbox_cell_ids)

                    csv_fb = self.client.get("/api/v1/export/?dataset=series&region=GA")
                    self.assertEqual(csv_fb.status_code, 200)
                    self.assertEqual(csv_fb["X-FirePulse-Cache"], "FALLBACK")
                    self.assertEqual(csv_fb.content.decode("utf-8"), live_csv_text)

                    pts_503 = self.client.get("/api/v1/export/?dataset=points&region=GA&month=2024-08")
                    self.assertEqual(pts_503.status_code, 503)
                    self.assertEqual(pts_503["X-FirePulse-Cache"], "BYPASS")

                    poly_geojson = json.dumps(
                        {
                            "type": "Polygon",
                            "coordinates": [[[11.0, -2.0], [12.0, -2.0], [12.0, -1.0], [11.0, -1.0], [11.0, -2.0]]],
                        }
                    )
                    csv_bbox_503 = self.client.get(
                        "/api/v1/export/?dataset=series&bbox=11.0,-2.0,12.0,-1.0"
                    )
                    self.assertEqual(csv_bbox_503.status_code, 503)
                    self.assertEqual(csv_bbox_503["X-FirePulse-Cache"], "BYPASS")
                    self.assertIn("no-store", csv_bbox_503["Cache-Control"])
                    self.assertIn("error", csv_bbox_503.json())

                    csv_poly_503 = self.client.get(
                        "/api/v1/export/",
                        {"dataset": "series", "polygon": poly_geojson},
                    )
                    self.assertEqual(csv_poly_503.status_code, 503)
                    self.assertEqual(csv_poly_503["X-FirePulse-Cache"], "BYPASS")
                    self.assertIn("no-store", csv_poly_503["Cache-Control"])
                    self.assertIn("error", csv_poly_503.json())

            cache.clear()
            invalidate_api_cache()
            with override_settings(DEMO_SNAPSHOT_DIR=out, FORCE_SNAPSHOT_FALLBACK=False):
                with patch(
                    "apps.api.views.Region.objects.filter",
                    side_effect=DatabaseError("db offline"),
                ), patch(
                    "apps.api.views.HarmonizedMonthSeries.objects.filter",
                    side_effect=DatabaseError("db offline"),
                ):
                    cal_err = self.client.get("/api/v1/calendar/?region=GA")
                    self.assertEqual(cal_err.status_code, 200)
                    self.assertEqual(cal_err["X-FirePulse-Cache"], "FALLBACK")
                    self.assertIn("no-store", cal_err["Cache-Control"])

                    csv_err = self.client.get("/api/v1/export/?dataset=series&region=GA")
                    self.assertEqual(csv_err.status_code, 200)
                    self.assertEqual(csv_err["X-FirePulse-Cache"], "FALLBACK")

                    bad_region = self.client.get("/api/v1/calendar/?region=../../etc/passwd")
                    self.assertEqual(bad_region.status_code, 503)
                    self.assertEqual(bad_region["X-FirePulse-Cache"], "BYPASS")

                with patch("apps.api.views.compute_custom_area_series", side_effect=DatabaseError("db offline")):
                    bbox_err = self.client.get("/api/v1/calendar/?bbox=11.0,-2.0,12.0,-1.0")
                    self.assertEqual(bbox_err.status_code, 503)
                    self.assertEqual(bbox_err["Cache-Control"], "no-store")

                    csv_bbox_err = self.client.get(
                        "/api/v1/export/?dataset=series&bbox=11.0,-2.0,12.0,-1.0"
                    )
                    self.assertEqual(csv_bbox_err.status_code, 503)
                    self.assertEqual(csv_bbox_err["X-FirePulse-Cache"], "BYPASS")
                    self.assertIn("no-store", csv_bbox_err["Cache-Control"])
                    self.assertIn("error", csv_bbox_err.json())

                    csv_poly_err = self.client.get(
                        "/api/v1/export/",
                        {
                            "dataset": "series",
                            "polygon": json.dumps(
                                {
                                    "type": "Polygon",
                                    "coordinates": [[[11.0, -2.0], [12.0, -2.0], [12.0, -1.0], [11.0, -1.0], [11.0, -2.0]]],
                                }
                            ),
                        },
                    )
                    self.assertEqual(csv_poly_err.status_code, 503)
                    self.assertEqual(csv_poly_err["X-FirePulse-Cache"], "BYPASS")
                    self.assertIn("no-store", csv_poly_err["Cache-Control"])
                    self.assertIn("error", csv_poly_err.json())

                (out / "coverage.json").write_text('{"tampered": true}\n', encoding="utf-8")
                with patch("apps.api.views.connection.cursor", side_effect=DatabaseError("db offline")), patch(
                    "apps.api.views.ImportBatch.objects.values",
                    side_effect=DatabaseError("db offline"),
                ):
                    health_tampered = self.client.get("/api/v1/health/")
                    self.assertEqual(health_tampered.status_code, 503)
                    self.assertEqual(health_tampered["X-FirePulse-Fallback"], "none")
                    self.assertFalse(health_tampered.json()["offline_snapshot_ready"])

                    cov_tampered = self.client.get("/api/v1/coverage/?region=GA")
                    self.assertEqual(cov_tampered.status_code, 503)
                    self.assertEqual(cov_tampered["X-FirePulse-Cache"], "BYPASS")

                (out / "hotspots_static_mask_GA.json").unlink()
                with patch("apps.api.views.Region.objects.filter", side_effect=DatabaseError("db offline")), patch(
                    "apps.api.views.GridCellMonth.objects.filter",
                    side_effect=DatabaseError("db offline"),
                ):
                    spots_missing_mask = self.client.get(
                        "/api/v1/hotspots/?mode=grid&agg=cell&region=GA&include_static_cells=true"
                    )
                    self.assertEqual(spots_missing_mask.status_code, 503)
                    self.assertEqual(spots_missing_mask["X-FirePulse-Cache"], "BYPASS")

    def test_offline_snapshot_rejects_truncated_duplicate_and_mismatched_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir)
            call_command("export_demo_snapshot", output=tmpdir, stdout=StringIO())
            manifest_path = out / "snapshot_manifest.json"
            original_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

            with override_settings(DEMO_SNAPSHOT_DIR=out, FORCE_SNAPSHOT_FALLBACK=False):
                # Warm _VERIFIED_FILE_SIGNATURES with a valid export first.
                with patch("apps.api.views.connection.cursor", side_effect=DatabaseError("db offline")):
                    ready = self.client.get("/api/v1/health/")
                    self.assertEqual(ready.status_code, 503)
                    self.assertEqual(ready["X-FirePulse-Fallback"], "ready")
                    self.assertTrue(ready.json()["offline_snapshot_ready"])

                def _assert_manifest_rejected(candidate: dict) -> None:
                    cache.clear()
                    invalidate_api_cache()
                    manifest_path.write_text(json.dumps(candidate), encoding="utf-8")
                    with patch("apps.api.views.connection.cursor", side_effect=DatabaseError("db offline")):
                        health = self.client.get("/api/v1/health/")
                        self.assertEqual(health.status_code, 503)
                        self.assertEqual(health["X-FirePulse-Fallback"], "none")
                        self.assertFalse(health.json()["offline_snapshot_ready"])
                    with patch("apps.api.views.Region.objects.order_by", side_effect=DatabaseError("db offline")):
                        regs = self.client.get("/api/v1/regions/?include_geom=false")
                        self.assertEqual(regs.status_code, 503)
                        self.assertEqual(regs["X-FirePulse-Cache"], "BYPASS")
                    with patch("apps.api.views.ImportBatch.objects.values", side_effect=DatabaseError("db offline")):
                        cov = self.client.get("/api/v1/coverage/?region=GA")
                        self.assertEqual(cov.status_code, 503)
                        self.assertEqual(cov["X-FirePulse-Cache"], "BYPASS")
                    with self.assertRaises(CommandError):
                        call_command("export_demo_snapshot", output=tmpdir, verify=True, stdout=StringIO())

                # 1. Valid JSON manifest truncated down to health.json only.
                _assert_manifest_rejected(
                    {
                        **original_manifest,
                        "files": [e for e in original_manifest["files"] if e["file"] == "health.json"],
                    }
                )

                # 2. Valid JSON manifest missing a single required endpoint file (coverage.json).
                _assert_manifest_rejected(
                    {
                        **original_manifest,
                        "files": [e for e in original_manifest["files"] if e["file"] != "coverage.json"],
                    }
                )

                # 3. Valid JSON manifest with full coverage set plus a duplicate filename entry.
                _assert_manifest_rejected(
                    {
                        **original_manifest,
                        "files": [*original_manifest["files"], dict(original_manifest["files"][0])],
                    }
                )

                # 4. Modified regions.json advertising GA-1 absent from manifest["regions"] / files.
                regions_path = out / "regions.json"
                regions_payload = json.loads(regions_path.read_text(encoding="utf-8"))
                regions_payload["regions"].append({**regions_payload["regions"][0], "code": "GA-1", "name": "Estuaire"})
                regions_bytes = (json.dumps(regions_payload) + "\n").encode("utf-8")
                regions_path.write_bytes(regions_bytes)
                regions_sha = hashlib.sha256(regions_bytes).hexdigest()
                rehashed_files = [
                    {"file": "regions.json", "bytes": len(regions_bytes), "sha256": regions_sha}
                    if e["file"] == "regions.json"
                    else e
                    for e in original_manifest["files"]
                ]
                _assert_manifest_rejected({**original_manifest, "files": rehashed_files})
