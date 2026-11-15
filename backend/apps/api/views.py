"""REST API v1 views for FirePulse (aligned with docs/api-contract.json)."""

import csv
import json
from datetime import date, timedelta

from django.conf import settings
from django.contrib.gis.db.models.functions import AsGeoJSON
from django.db import DatabaseError, connection
from django.db.models import Count, Max, Min, Sum
from django.http import HttpResponse
from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.response import Response

from apps.api.cache import cached_api_response, offline_unavailable_response
from apps.api.fallback import (
    fallback_anomalies,
    fallback_calendar,
    fallback_coverage,
    fallback_export_series_csv,
    fallback_hotspots,
    fallback_methodology,
    fallback_regions,
    has_offline_snapshot,
    render_series_csv_response,
)
from apps.api.services import (
    bad_request,
    compute_custom_area_series,
    next_month,
    parse_area_geometry,
    parse_bool,
    parse_month,
)
from apps.harmonization.models import (
    CalibrationRun,
    HarmonizedMonthSeries,
    MonthlyBaseline,
)
from apps.observations.models import (
    GridCellMonth,
    HotspotObservation,
    ImportBatch,
    Region,
    StaticFlareMaskCell,
)

SENSOR_META = {
    "modis": {
        "label": "MODIS (Terra + Aqua)",
        "operational_end_date": None,
        "notes": "Terra-only from 2000-11 to 2002-06; Aqua starts 2002-07.",
    },
    "viirs-snpp": {
        "label": "VIIRS Suomi-NPP 375m",
        "operational_end_date": "2026-11-02",
        "notes": "Operational FIRMS delivery ended 2026-11-02 13:00 UTC.",
    },
    "viirs-noaa20": {
        "label": "VIIRS NOAA-20 375m",
        "operational_end_date": None,
        "notes": "Official drop-in continuation after S-NPP retirement.",
    },
    "viirs-noaa21": {
        "label": "VIIRS NOAA-21 375m",
        "operational_end_date": None,
        "notes": "Secondary operational VIIRS continuity sensor.",
    },
}

DOCUMENTED_LIMITATIONS = [
    "Hotspot counts measure thermal detections, not distinct individual wildfire events.",
    "MODIS Terra operated without Aqua from 2000-11 through 2002-06; calibrated separately.",
    "Suomi-NPP VIIRS operational FIRMS delivery ended 2026-11-02; NOAA-20 VIIRS provides continuity.",
    "When filter_static=true, type 2/3 detections and type 0 detections inside 183 persistent 0.05° candidate cells (~5.5 km grids, ~21-24% of raw VIIRS in Gabon; not individually ground-verified industrial facilities) are excluded.",
    "NASA FIRMS June 15, 2025 notice: some VIIRS Vxx14IMGML Collection 2 files had type 0/2 differences between versions 1/2 and reprocessed version 3.",
]


def _serialize_series_item(item: dict) -> dict:
    return {k: v for k, v in item.items() if k != "month_date"}


def _in_month_window(m_date: date, start_month: date | None, end_month: date | None) -> bool:
    if start_month and m_date < start_month:
        return False
    if end_month and m_date > end_month:
        return False
    return True


@api_view(["GET"])
def recent_unknown_detections_view(request):
    """Expose recent raw NRT detections with unknown FIRMS type, outside filtered series."""
    try:
        days = int(request.query_params.get("days", "2"))
        limit = int(request.query_params.get("limit", "200"))
    except ValueError:
        return bad_request("days and limit must be integers.")
    if not 1 <= days <= 5 or not 1 <= limit <= 1000:
        return bad_request("days must be 1..5 and limit must be 1..1000.")
    region_code = request.query_params.get("region", "GA")

    try:
        region = Region.objects.filter(code=region_code).only("geom").first()
        if region is None:
            return bad_request("Unknown region.")
        since = timezone.now() - timedelta(days=days)
        rows = (
            HotspotObservation.objects.filter(
                is_nrt=True, hotspot_type__isnull=True, counts_in_aggregates=True,
                acquired_at__gte=since, position__within=region.geom,
            )
            .annotate(geojson_text=AsGeoJSON("position"))
            .values("id", "geojson_text", "source", "satellite", "acquired_at", "frp",
                    "confidence_tier", "product_version", "is_static_masked")
            .order_by("-acquired_at", "-id")[:limit]
        )
        features = [
            {
                "type": "Feature",
                "geometry": json.loads(row["geojson_text"]),
                "properties": {
                    "id": row["id"], "source": row["source"],
                    "satellite": row["satellite"],
                    "acquired_at": row["acquired_at"].isoformat(),
                    "frp": row["frp"], "confidence_tier": row["confidence_tier"],
                    "hotspot_type": None, "is_static_masked": row["is_static_masked"],
                    "processing_level": "NRT", "product_version": row["product_version"],
                    "interpretation": "thermal_detection_type_unknown",
                },
            }
            for row in rows
        ]
    except DatabaseError:
        return offline_unavailable_response("Recent NRT detections require the live PostGIS database.")
    response = Response({
        "type": "FeatureCollection", "features": features,
        "region": region_code, "since": since.isoformat(), "days": days,
        "provenance": "NASA FIRMS NRT raw observations; type unavailable; not part of the filtered vegetation-fire series.",
        "caution": "Thermal detections are not confirmed wildfires; NRT records may be revised.",
    })
    response["Cache-Control"] = "no-store"
    return response


@api_view(["GET"])
def health_view(request):
    """Verify PostgreSQL connection and PostGIS extension readiness."""
    snapshot_ready = has_offline_snapshot()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT PostGIS_Version();")
            postgis_version = cursor.fetchone()[0]
        payload = {
            "status": "ok",
            "database": "connected",
            "postgis_version": postgis_version,
            "counts": {
                "regions": Region.objects.count(),
                "hotspots": HotspotObservation.objects.count(),
                "grid_cell_months": GridCellMonth.objects.count(),
                "harmonized_months": HarmonizedMonthSeries.objects.count(),
            },
        }
        res = Response(payload)
    except DatabaseError as exc:
        res = Response(
            {
                "status": "error",
                "database": "disconnected",
                "offline_snapshot_ready": snapshot_ready,
                "detail": str(exc),
            },
            status=503,
        )
    res["X-FirePulse-Fallback"] = "ready" if snapshot_ready else "none"
    res["Cache-Control"] = "no-store"
    return res


@api_view(["GET"])
def regions_view(request):
    """Return available precomputed regions with GeoJSON geometries."""
    include_geom = parse_bool(request.query_params.get("include_geom"), default=True)

    def _produce() -> dict:
        qs = Region.objects.order_by("region_type", "code")
        fields = ("code", "name", "region_type", "bbox_json", "is_custom_supported")
        if include_geom:
            rows = qs.values(*fields).annotate(geojson_text=AsGeoJSON("geom"))
            regions = [
                {
                    "code": row["code"],
                    "name": row["name"],
                    "region_type": row["region_type"],
                    "bbox": row["bbox_json"],
                    "is_custom_supported": row["is_custom_supported"],
                    "geometry": json.loads(row["geojson_text"]),
                }
                for row in rows
            ]
        else:
            rows = qs.values(*fields)
            regions = [
                {
                    "code": row["code"],
                    "name": row["name"],
                    "region_type": row["region_type"],
                    "bbox": row["bbox_json"],
                    "is_custom_supported": row["is_custom_supported"],
                    "geometry": None,
                }
                for row in rows
            ]
        return {"regions": regions}

    return cached_api_response(
        "regions",
        request,
        _produce,
        fallback=lambda: fallback_regions(include_geom),
    )


@api_view(["GET"])
def coverage_view(request):
    """Return temporal availability, versions, and processing level (SP/NRT) per source."""
    region_code = request.query_params.get("region", "GA")

    def _produce() -> dict:
        batches = (
            ImportBatch.objects.values("source")
            .annotate(min_date=Min("min_date"), max_date=Max("max_date"))
            .order_by("source")
        )
        levels_by_src: dict[str, set[str]] = {}
        versions_by_src: dict[str, set[str]] = {}
        for src, lvl, ver in ImportBatch.objects.values_list("source", "processing_level", "product_version"):
            levels_by_src.setdefault(src, set()).add(lvl)
            for token in (ver or "").split(","):
                tok = token.strip()
                if tok:
                    versions_by_src.setdefault(src, set()).add(tok)

        sensors = []
        for row in batches:
            src = row["source"]
            meta = SENSOR_META.get(src, {})
            sensors.append(
                {
                    "source": src,
                    "label": meta.get("label", src),
                    "min_date": row["min_date"].isoformat() if row["min_date"] else None,
                    "max_date": row["max_date"].isoformat() if row["max_date"] else None,
                    "operational_end_date": meta.get("operational_end_date"),
                    "processing_levels": sorted(levels_by_src.get(src, set())),
                    "product_versions": sorted(versions_by_src.get(src, set())),
                    "notes": meta.get("notes", ""),
                }
            )
        return {"region": region_code, "sensors": sensors}

    return cached_api_response(
        "coverage",
        request,
        _produce,
        fallback=lambda: fallback_coverage(region_code),
    )


@api_view(["GET"])
def calendar_view(request):
    """Return raw vs harmonized monthly series for a region, custom bbox, or polygon."""
    region_code = request.query_params.get("region", "GA")
    filter_static = parse_bool(request.query_params.get("filter_static"), default=True)
    try:
        start_month = parse_month(request.query_params.get("start"))
        end_month = parse_month(request.query_params.get("end"))
        custom_geom, area_id, area_name = parse_area_geometry(request)
    except ValueError as exc:
        return bad_request(str(exc))

    def _produce() -> dict:
        if custom_geom is not None:
            ga_run, _, full_series = compute_custom_area_series(custom_geom, filter_static)
            series = [
                _serialize_series_item(item)
                for item in full_series
                if _in_month_window(item["month_date"], start_month, end_month)
            ]
            return {
                "region": {"id": area_id, "name": area_name, "filter_static": filter_static},
                "period": {
                    "start": series[0]["month"] if series else None,
                    "end": series[-1]["month"] if series else None,
                },
                "method": (
                    {
                        "name": ga_run.method_name,
                        "version": ga_run.method_version,
                        "reference_scale": ga_run.reference_scale,
                        "bridge_after_2026_11_02": "VIIRS_NOAA20",
                    }
                    if ga_run
                    else None
                ),
                "series": series,
            }

        region = Region.objects.filter(code=region_code).first()
        if not region:
            return {
                "region": {"id": region_code, "name": region_code, "filter_static": filter_static},
                "period": {"start": None, "end": None},
                "method": None,
                "series": [],
            }

        qs = HarmonizedMonthSeries.objects.filter(
            region=region,
            filter_static=filter_static,
            calibration_run__is_active=True,
        )
        if start_month:
            qs = qs.filter(month__gte=start_month)
        if end_month:
            qs = qs.filter(month__lte=end_month)

        rows = list(qs.select_related("calibration_run").order_by("month"))
        active_run = rows[0].calibration_run if rows else CalibrationRun.objects.filter(
            region=region, filter_static=filter_static, is_active=True
        ).first()
        series = [
            {
                "month": r.month.strftime("%Y-%m"),
                "modis_count": r.modis_count,
                "modis_terra_count": r.modis_terra_count,
                "modis_aqua_count": r.modis_aqua_count,
                "viirs_snpp_count": r.viirs_snpp_count,
                "viirs_noaa20_count": r.viirs_noaa20_count,
                "harmonized_value": r.harmonized_value,
                "ci_low": r.ci_low,
                "ci_high": r.ci_high,
                "baseline_median": r.baseline_median,
                "baseline_iqr": (
                    [r.baseline_iqr_p25, r.baseline_iqr_p75]
                    if r.baseline_iqr_p25 is not None and r.baseline_iqr_p75 is not None
                    else None
                ),
                "anomaly_percent": r.anomaly_percent,
                "anomaly_absolute": r.anomaly_absolute,
                "sensor_regime": r.sensor_regime,
                "coverage_status": r.coverage_status,
                "uncertainty_note": r.uncertainty_note,
            }
            for r in rows
        ]
        return {
            "region": {"id": region.code, "name": region.name, "filter_static": filter_static},
            "period": {
                "start": series[0]["month"] if series else None,
                "end": series[-1]["month"] if series else None,
            },
            "method": (
                {
                    "name": active_run.method_name,
                    "version": active_run.method_version,
                    "reference_scale": active_run.reference_scale,
                    "bridge_after_2026_11_02": "VIIRS_NOAA20",
                }
                if active_run
                else None
            ),
            "series": series,
        }

    return cached_api_response(
        "calendar",
        request,
        _produce,
        fallback=lambda: fallback_calendar(region_code, filter_static, start_month, end_month, custom_geom),
    )


@api_view(["GET"])
def anomalies_view(request):
    """Return monthly historical baselines (median + IQR) and ranked anomalies."""
    region_code = request.query_params.get("region", "GA")
    filter_static = parse_bool(request.query_params.get("filter_static"), default=True)
    try:
        top_n = max(1, min(50, int(request.query_params.get("top_n", "10"))))
        start_month = parse_month(request.query_params.get("start"))
        end_month = parse_month(request.query_params.get("end"))
        custom_geom, area_id, _ = parse_area_geometry(request)
    except ValueError as exc:
        return bad_request(str(exc))

    def _produce() -> dict:
        if custom_geom is not None:
            _, baselines, full_series = compute_custom_area_series(custom_geom, filter_static)
            valid = [
                item
                for item in full_series
                if item["anomaly_percent"] is not None
                and _in_month_window(item["month_date"], start_month, end_month)
            ]
            serialize_custom = lambda item: {
                "month": item["month"],
                "harmonized_value": item["harmonized_value"],
                "baseline_median": item["baseline_median"],
                "anomaly_percent": item["anomaly_percent"],
                "anomaly_absolute": item["anomaly_absolute"],
                "sensor_regime": item["sensor_regime"],
            }
            top_positive = [
                serialize_custom(item)
                for item in sorted(valid, key=lambda x: x["anomaly_percent"], reverse=True)[:top_n]
            ]
            top_negative = [
                serialize_custom(item)
                for item in sorted(valid, key=lambda x: x["anomaly_percent"])[:top_n]
            ]
            return {
                "region": area_id,
                "filter_static": filter_static,
                "monthly_baselines": baselines,
                "top_positive": top_positive,
                "top_negative": top_negative,
            }

        region = Region.objects.filter(code=region_code).first()
        if not region:
            return {
                "region": region_code,
                "filter_static": filter_static,
                "monthly_baselines": [],
                "top_positive": [],
                "top_negative": [],
            }

        baselines = [
            {
                "month_num": b.month_num,
                "median": b.baseline_median,
                "iqr_p25": b.iqr_p25,
                "iqr_p75": b.iqr_p75,
                "reference_years_count": b.reference_years_count,
                "reference_period": b.reference_period,
            }
            for b in MonthlyBaseline.objects.filter(
                region=region,
                filter_static=filter_static,
                calibration_run__is_active=True,
            ).order_by("month_num")
        ]
        series_qs = HarmonizedMonthSeries.objects.filter(
            region=region,
            filter_static=filter_static,
            calibration_run__is_active=True,
            anomaly_percent__isnull=False,
        )
        if start_month:
            series_qs = series_qs.filter(month__gte=start_month)
        if end_month:
            series_qs = series_qs.filter(month__lte=end_month)

        serialize_anom = lambda r: {
            "month": r.month.strftime("%Y-%m"),
            "harmonized_value": r.harmonized_value,
            "baseline_median": r.baseline_median,
            "anomaly_percent": r.anomaly_percent,
            "anomaly_absolute": r.anomaly_absolute,
            "sensor_regime": r.sensor_regime,
        }
        top_positive = [serialize_anom(r) for r in series_qs.order_by("-anomaly_percent")[:top_n]]
        top_negative = [serialize_anom(r) for r in series_qs.order_by("anomaly_percent")[:top_n]]
        return {
            "region": region.code,
            "filter_static": filter_static,
            "monthly_baselines": baselines,
            "top_positive": top_positive,
            "top_negative": top_negative,
        }

    return cached_api_response(
        "anomalies",
        request,
        _produce,
        fallback=lambda: fallback_anomalies(
            region_code, filter_static, top_n, start_month, end_month, custom_geom
        ),
    )


@api_view(["GET"])
def hotspots_view(request):
    """Return GeoJSON FeatureCollection of 0.25 deg grid cells or filtered detections."""
    mode = request.query_params.get("mode", "grid").lower()
    agg = request.query_params.get("agg", "month").lower()
    region_code = request.query_params.get("region")
    filter_static = parse_bool(request.query_params.get("filter_static"), default=True)
    include_static_cells = parse_bool(request.query_params.get("include_static_cells"), default=False)

    if agg not in {"month", "cell"}:
        return bad_request("agg must be 'month' or 'cell'.")
    if mode not in {"grid", "points"}:
        return bad_request("mode must be 'grid' or 'points'.")

    try:
        month_date = parse_month(request.query_params.get("month"))
        start_month = parse_month(request.query_params.get("start"))
        end_month = parse_month(request.query_params.get("end"))
        custom_geom, _, _ = parse_area_geometry(request)
        limit = max(1, min(5000, int(request.query_params.get("limit", "2000"))))
    except ValueError as exc:
        return bad_request(str(exc))

    if mode == "points" and not any([month_date, start_month, end_month]) and custom_geom is None:
        return bad_request("mode=points requires at least 'month', 'start'/'end', 'bbox', or 'polygon'.")

    def _produce() -> dict:
        region_geom = None
        if region_code:
            reg = Region.objects.filter(code=region_code).only("geom").first()
            if reg:
                region_geom = reg.geom

        spatial_filter_geom = custom_geom or region_geom
        features: list[dict] = []

        if mode == "points":
            qs = HotspotObservation.objects.filter(counts_in_aggregates=True)
            if filter_static:
                qs = qs.filter(hotspot_type=0, is_static_masked=False)
            if month_date:
                qs = qs.filter(acquired_at__year=month_date.year, acquired_at__month=month_date.month)
            else:
                if start_month:
                    qs = qs.filter(acquired_at__gte=start_month)
                if end_month:
                    qs = qs.filter(acquired_at__lt=next_month(end_month))
            if spatial_filter_geom:
                qs = qs.filter(position__within=spatial_filter_geom)
            rows = (
                qs.annotate(geojson_text=AsGeoJSON("position"))
                .values(
                    "geojson_text",
                    "source",
                    "satellite",
                    "acquired_at",
                    "frp",
                    "confidence_tier",
                    "hotspot_type",
                    "is_static_masked",
                )
                .order_by("-acquired_at")[:limit]
            )
            for obs in rows:
                features.append(
                    {
                        "type": "Feature",
                        "geometry": json.loads(obs["geojson_text"]),
                        "properties": {
                            "layer": "hotspot_point",
                            "source": obs["source"],
                            "satellite": obs["satellite"],
                            "acquired_at": obs["acquired_at"].isoformat(),
                            "frp": obs["frp"],
                            "confidence_tier": obs["confidence_tier"],
                            "hotspot_type": obs["hotspot_type"],
                            "is_static_masked": obs["is_static_masked"],
                        },
                    }
                )
        else:
            qs = GridCellMonth.objects.filter(filter_static=filter_static)
            if month_date:
                qs = qs.filter(month=month_date)
            else:
                if start_month:
                    qs = qs.filter(month__gte=start_month)
                if end_month:
                    qs = qs.filter(month__lte=end_month)
            if spatial_filter_geom:
                qs = qs.filter(geom__intersects=spatial_filter_geom)

            if agg == "cell":
                grouped = (
                    qs.values("cell_id")
                    .annotate(
                        geojson_text=Max(AsGeoJSON("geom")),
                        modis_count=Sum("modis_count"),
                        viirs_snpp_count=Sum("viirs_snpp_count"),
                        viirs_noaa20_count=Sum("viirs_noaa20_count"),
                        frp_sum_modis=Sum("frp_sum_modis"),
                        frp_sum_snpp=Sum("frp_sum_snpp"),
                        frp_sum_noaa20=Sum("frp_sum_noaa20"),
                        months_count=Count("month"),
                    )
                    .order_by("-viirs_snpp_count", "-modis_count", "cell_id")[:limit]
                )
                for cell in grouped:
                    features.append(
                        {
                            "type": "Feature",
                            "geometry": json.loads(cell["geojson_text"]),
                            "properties": {
                                "layer": "grid_cell_summary",
                                "cell_id": cell["cell_id"],
                                "months_count": cell["months_count"],
                                "modis_count": cell["modis_count"],
                                "viirs_snpp_count": cell["viirs_snpp_count"],
                                "viirs_noaa20_count": cell["viirs_noaa20_count"],
                                "frp_sum_modis": round(cell["frp_sum_modis"] or 0.0, 2),
                                "frp_sum_snpp": round(cell["frp_sum_snpp"] or 0.0, 2),
                                "frp_sum_noaa20": round(cell["frp_sum_noaa20"] or 0.0, 2),
                            },
                        }
                    )
            else:
                rows = (
                    qs.annotate(geojson_text=AsGeoJSON("geom"))
                    .values(
                        "geojson_text",
                        "cell_id",
                        "month",
                        "modis_count",
                        "viirs_snpp_count",
                        "viirs_noaa20_count",
                    )
                    .order_by("cell_id", "month")[:limit]
                )
                for cell in rows:
                    features.append(
                        {
                            "type": "Feature",
                            "geometry": json.loads(cell["geojson_text"]),
                            "properties": {
                                "layer": "grid_cell_month",
                                "cell_id": cell["cell_id"],
                                "month": cell["month"].strftime("%Y-%m"),
                                "modis_count": cell["modis_count"],
                                "viirs_snpp_count": cell["viirs_snpp_count"],
                                "viirs_noaa20_count": cell["viirs_noaa20_count"],
                            },
                        }
                    )

        if include_static_cells:
            static_qs = StaticFlareMaskCell.objects.all()
            if spatial_filter_geom:
                static_qs = static_qs.filter(geom__intersects=spatial_filter_geom)
            static_rows = static_qs.annotate(geojson_text=AsGeoJSON("geom")).values(
                "geojson_text",
                "cell_id",
                "type23_count",
                "active_months_snpp",
                "reason",
            )[:1000]
            for cell in static_rows:
                features.append(
                    {
                        "type": "Feature",
                        "geometry": json.loads(cell["geojson_text"]),
                        "properties": {
                            "layer": "static_flare_mask",
                            "cell_id": cell["cell_id"],
                            "type23_count": cell["type23_count"],
                            "active_months_snpp": cell["active_months_snpp"],
                            "reason": cell["reason"],
                        },
                    }
                )

        return {"type": "FeatureCollection", "mode": mode, "agg": agg, "features": features}

    return cached_api_response(
        "hotspots",
        request,
        _produce,
        fallback=lambda: fallback_hotspots(
            mode,
            agg,
            region_code,
            filter_static,
            include_static_cells,
            limit,
            month_date,
            start_month,
            end_month,
            custom_geom,
        ),
    )


@api_view(["GET"])
def methodology_view(request):
    """Return active calibration parameters, out-of-sample metrics, and limitations."""
    region_code = request.query_params.get("region", "GA")
    filter_static = parse_bool(request.query_params.get("filter_static"), default=True)

    def _produce() -> dict:
        run = CalibrationRun.objects.filter(
            region__code=region_code,
            filter_static=filter_static,
            is_active=True,
        ).first()

        return {
            "region": region_code,
            "filter_static": filter_static,
            "active_run": (
                {
                    "method_name": run.method_name,
                    "method_version": run.method_version,
                    "reference_scale": run.reference_scale,
                    "train_window": [run.train_start.isoformat(), run.train_end.isoformat()],
                    "test_window": [run.test_start.isoformat(), run.test_end.isoformat()],
                    "params": run.params_json,
                    "metrics": run.metrics_json,
                }
                if run
                else None
            ),
            "static_mask_summary": {
                "grid_deg": 0.05,
                "masked_cells_count": StaticFlareMaskCell.objects.count(),
            },
            "limitations": DOCUMENTED_LIMITATIONS,
        }

    return cached_api_response(
        "methodology",
        request,
        _produce,
        fallback=lambda: fallback_methodology(region_code, filter_static),
    )


def _export_series_csv(request, region_code: str, filter_static: bool, start_month: date | None, end_month: date | None):
    custom_geom, area_id, _ = parse_area_geometry(request)
    export_id = area_id if custom_geom is not None else region_code

    if getattr(settings, "FORCE_SNAPSHOT_FALLBACK", False):
        fb = fallback_export_series_csv(region_code, filter_static, start_month, end_month, custom_geom)
        if fb is not None:
            return fb
        return offline_unavailable_response(
            "Requested export scope is unavailable in offline snapshot fallback mode."
        )

    try:
        if custom_geom is not None:
            ga_run, _, full_series = compute_custom_area_series(custom_geom, filter_static)
            method_version = ga_run.method_version if ga_run else "v2.0"
            csv_rows = [
                [
                    export_id,
                    item["month"],
                    filter_static,
                    item["modis_count"],
                    item["viirs_snpp_count"],
                    item["viirs_noaa20_count"],
                    item["harmonized_value"],
                    item["ci_low"],
                    item["ci_high"],
                    item["baseline_median"],
                    item["anomaly_percent"],
                    item["anomaly_absolute"],
                    item["sensor_regime"],
                    item["coverage_status"],
                    method_version,
                ]
                for item in full_series
                if _in_month_window(item["month_date"], start_month, end_month)
            ]
        else:
            qs = HarmonizedMonthSeries.objects.filter(
                region__code=region_code,
                filter_static=filter_static,
                calibration_run__is_active=True,
            ).order_by("month")
            if start_month:
                qs = qs.filter(month__gte=start_month)
            if end_month:
                qs = qs.filter(month__lte=end_month)
            csv_rows = [
                [
                    region_code,
                    row.month.strftime("%Y-%m"),
                    row.filter_static,
                    row.modis_count,
                    row.viirs_snpp_count,
                    row.viirs_noaa20_count,
                    row.harmonized_value,
                    row.ci_low,
                    row.ci_high,
                    row.baseline_median,
                    row.anomaly_percent,
                    row.anomaly_absolute,
                    row.sensor_regime,
                    row.coverage_status,
                    row.method_version,
                ]
                for row in qs
            ]
    except DatabaseError as exc:
        if getattr(settings, "API_SNAPSHOT_FALLBACK", True):
            fb = fallback_export_series_csv(region_code, filter_static, start_month, end_month, custom_geom)
            if fb is not None:
                return fb
        return offline_unavailable_response(str(exc))

    return render_series_csv_response(export_id, csv_rows)


def _export_points_csv(
    request,
    region_code: str,
    filter_static: bool,
    month_date: date | None,
    start_month: date | None,
    end_month: date | None,
):
    custom_geom, area_id, _ = parse_area_geometry(request)
    limit = max(1, min(50000, int(request.query_params.get("limit", "10000"))))

    has_time = any([month_date, start_month, end_month])
    if not has_time and custom_geom is None:
        return bad_request("dataset=points requires at least 'month', 'start'/'end', 'bbox', or 'polygon'.")

    if getattr(settings, "FORCE_SNAPSHOT_FALLBACK", False):
        return offline_unavailable_response("Offline snapshot mode forced; point-level export requires PostgreSQL.")

    export_id = area_id if custom_geom is not None else region_code
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="firepulse_{export_id}_points.csv"'
    writer = csv.writer(response)
    writer.writerow(
        [
            "region",
            "source",
            "satellite",
            "instrument",
            "acquired_at",
            "latitude",
            "longitude",
            "frp",
            "brightness_mir",
            "brightness_tir",
            "confidence_raw",
            "confidence_tier",
            "daynight",
            "hotspot_type",
            "is_static_masked",
            "product_version",
            "is_nrt",
        ]
    )

    try:
        reg = None
        if custom_geom is None:
            reg = Region.objects.filter(code=region_code).first()
            if reg is None:
                return response

        spatial_geom = custom_geom or reg.geom
        qs = HotspotObservation.objects.filter(counts_in_aggregates=True)
        if filter_static:
            qs = qs.filter(hotspot_type=0, is_static_masked=False)
        if month_date:
            qs = qs.filter(acquired_at__year=month_date.year, acquired_at__month=month_date.month)
        else:
            if start_month:
                qs = qs.filter(acquired_at__gte=start_month)
            if end_month:
                qs = qs.filter(acquired_at__lt=next_month(end_month))
        if spatial_geom is not None:
            qs = qs.filter(position__within=spatial_geom)

        for obs in (
            qs.only(
                "source",
                "satellite",
                "instrument",
                "acquired_at",
                "position",
                "frp",
                "brightness_mir",
                "brightness_tir",
                "confidence_raw",
                "confidence_tier",
                "daynight",
                "hotspot_type",
                "is_static_masked",
                "product_version",
                "is_nrt",
            )
            .order_by("-acquired_at")[:limit]
            .iterator(chunk_size=2000)
        ):
            writer.writerow(
                [
                    export_id,
                    obs.source,
                    obs.satellite,
                    obs.instrument,
                    obs.acquired_at.isoformat(),
                    round(obs.position.y, 5),
                    round(obs.position.x, 5),
                    obs.frp,
                    obs.brightness_mir,
                    obs.brightness_tir,
                    obs.confidence_raw,
                    obs.confidence_tier,
                    obs.daynight,
                    obs.hotspot_type,
                    obs.is_static_masked,
                    obs.product_version,
                    obs.is_nrt,
                ]
            )
    except DatabaseError as exc:
        return offline_unavailable_response(str(exc))

    return response


@api_view(["GET"])
def export_view(request):
    """Export monthly harmonized series or bounded raw detections as CSV."""
    dataset = request.query_params.get("dataset", "series").lower()
    if dataset not in {"series", "points"}:
        return bad_request("dataset must be 'series' or 'points'.")

    region_code = request.query_params.get("region", "GA")
    filter_static = parse_bool(request.query_params.get("filter_static"), default=True)
    try:
        month_date = parse_month(request.query_params.get("month"))
        start_month = parse_month(request.query_params.get("start"))
        end_month = parse_month(request.query_params.get("end"))
        if dataset == "points":
            return _export_points_csv(request, region_code, filter_static, month_date, start_month, end_month)
        return _export_series_csv(request, region_code, filter_static, start_month, end_month)
    except ValueError as exc:
        return bad_request(str(exc))
