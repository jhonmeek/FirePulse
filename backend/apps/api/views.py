"""REST API v1 views for FirePulse (aligned with docs/api-contract.json)."""

import csv
import json
from datetime import date

from django.contrib.gis.geos import Polygon
from django.db import connection
from django.db.models import Max, Min, Sum
from django.http import HttpResponse
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

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

DOCUMENTED_LIMITATIONS = [
    "Hotspot counts measure thermal detections, not distinct individual wildfire events.",
    "MODIS Terra operated without Aqua from 2000-11 through 2002-06; calibrated separately.",
    "Suomi-NPP VIIRS operational FIRMS delivery ended 2026-11-02; NOAA-20 VIIRS provides continuity.",
    "Persistent industrial/oil gas flares (~21-24% of raw VIIRS in Gabon) are filtered when filter_static=true.",
]


def _parse_bool(value: str | None, default: bool = True) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _parse_month(value: str | None) -> date | None:
    if not value:
        return None
    try:
        year_s, month_s = value.strip().split("-", 1)
        return date(int(year_s), int(month_s), 1)
    except ValueError as exc:
        raise ValueError(f"Invalid YYYY-MM month format: {value!r}") from exc


def _parse_bbox(value: str | None) -> Polygon | None:
    if not value:
        return None
    try:
        parts = [float(p.strip()) for p in value.split(",")]
        if len(parts) != 4:
            raise ValueError
        west, south, east, north = parts
        if west >= east or south >= north:
            raise ValueError
        return Polygon.from_bbox((west, south, east, north))
    except ValueError as exc:
        raise ValueError("bbox must be 'west,south,east,north' with west<east and south<north") from exc


def _bad_request(message: str) -> Response:
    return Response({"error": message}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["GET"])
def health_view(request):
    """Verify PostgreSQL connection and PostGIS extension readiness."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT PostGIS_Version();")
        postgis_version = cursor.fetchone()[0]

    return Response(
        {
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
    )


@api_view(["GET"])
def regions_view(request):
    """Return available precomputed regions with GeoJSON geometries."""
    include_geom = _parse_bool(request.query_params.get("include_geom"), default=True)
    regions = [
        {
            "code": reg.code,
            "name": reg.name,
            "region_type": reg.region_type,
            "bbox": reg.bbox_json,
            "is_custom_supported": reg.is_custom_supported,
            "geometry": json.loads(reg.geom.geojson) if include_geom else None,
        }
        for reg in Region.objects.all()
    ]
    return Response({"regions": regions})


@api_view(["GET"])
def coverage_view(request):
    """Return temporal availability and processing level (SP/NRT) per ingested source."""
    region_code = request.query_params.get("region", "GA")
    batches = (
        ImportBatch.objects.values("source")
        .annotate(min_date=Min("min_date"), max_date=Max("max_date"))
        .order_by("source")
    )
    levels_by_src: dict[str, set[str]] = {}
    for src, lvl in ImportBatch.objects.values_list("source", "processing_level"):
        levels_by_src.setdefault(src, set()).add(lvl)

    sensors = [
        {
            "source": row["source"],
            "min_date": row["min_date"].isoformat() if row["min_date"] else None,
            "max_date": row["max_date"].isoformat() if row["max_date"] else None,
            "processing_levels": sorted(levels_by_src.get(row["source"], set())),
        }
        for row in batches
    ]
    return Response({"region": region_code, "sensors": sensors})


@api_view(["GET"])
def calendar_view(request):
    """Return raw vs harmonized monthly series for a region or custom bbox."""
    region_code = request.query_params.get("region", "GA")
    filter_static = _parse_bool(request.query_params.get("filter_static"), default=True)
    try:
        start_month = _parse_month(request.query_params.get("start"))
        end_month = _parse_month(request.query_params.get("end"))
        bbox_poly = _parse_bbox(request.query_params.get("bbox"))
    except ValueError as exc:
        return _bad_request(str(exc))

    if bbox_poly is not None:
        qs = GridCellMonth.objects.filter(
            filter_static=filter_static,
            geom__intersects=bbox_poly,
        )
        if start_month:
            qs = qs.filter(month__gte=start_month)
        if end_month:
            qs = qs.filter(month__lte=end_month)
        agg = (
            qs.values("month")
            .annotate(
                modis_count=Sum("modis_count"),
                modis_terra_count=Sum("modis_terra_count"),
                modis_aqua_count=Sum("modis_aqua_count"),
                viirs_snpp_count=Sum("viirs_snpp_count"),
                viirs_noaa20_count=Sum("viirs_noaa20_count"),
            )
            .order_by("month")
        )
        series = [
            {
                "month": row["month"].strftime("%Y-%m"),
                "modis_count": row["modis_count"],
                "modis_terra_count": row["modis_terra_count"],
                "modis_aqua_count": row["modis_aqua_count"],
                "viirs_snpp_count": row["viirs_snpp_count"],
                "viirs_noaa20_count": row["viirs_noaa20_count"],
                "harmonized_value": None,
                "ci_low": None,
                "ci_high": None,
                "baseline_median": None,
                "baseline_iqr": None,
                "anomaly_percent": None,
                "anomaly_absolute": None,
                "sensor_regime": "custom_bbox_raw",
                "coverage_status": "complete_sp",
                "uncertainty_note": "Custom bbox aggregation from 0.25 deg grid.",
            }
            for row in agg
        ]
        return Response(
            {
                "region": {"id": "CUSTOM_BBOX", "name": "Custom Area", "filter_static": filter_static},
                "period": {
                    "start": series[0]["month"] if series else None,
                    "end": series[-1]["month"] if series else None,
                },
                "method": None,
                "series": series,
            }
        )

    region = Region.objects.filter(code=region_code).first()
    if not region:
        return Response(
            {
                "region": {"id": region_code, "name": region_code, "filter_static": filter_static},
                "period": {"start": None, "end": None},
                "method": None,
                "series": [],
            }
        )

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
    return Response(
        {
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
    )


@api_view(["GET"])
def anomalies_view(request):
    """Return monthly historical baselines (median + IQR) and ranked anomalies."""
    region_code = request.query_params.get("region", "GA")
    filter_static = _parse_bool(request.query_params.get("filter_static"), default=True)
    try:
        top_n = max(1, min(50, int(request.query_params.get("top_n", "10"))))
    except ValueError:
        return _bad_request("top_n must be an integer.")

    region = Region.objects.filter(code=region_code).first()
    if not region:
        return Response(
            {
                "region": region_code,
                "filter_static": filter_static,
                "monthly_baselines": [],
                "top_positive": [],
                "top_negative": [],
            }
        )

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
    return Response(
        {
            "region": region.code,
            "filter_static": filter_static,
            "monthly_baselines": baselines,
            "top_positive": top_positive,
            "top_negative": top_negative,
        }
    )


@api_view(["GET"])
def hotspots_view(request):
    """Return GeoJSON FeatureCollection of 0.25 deg grid cells or filtered detections."""
    mode = request.query_params.get("mode", "grid").lower()
    filter_static = _parse_bool(request.query_params.get("filter_static"), default=True)
    include_static_cells = _parse_bool(request.query_params.get("include_static_cells"), default=False)

    try:
        month_date = _parse_month(request.query_params.get("month"))
        bbox_poly = _parse_bbox(request.query_params.get("bbox"))
        limit = max(1, min(5000, int(request.query_params.get("limit", "2000"))))
    except ValueError as exc:
        return _bad_request(str(exc))

    features: list[dict] = []

    if mode == "points":
        if month_date is None and bbox_poly is None:
            return _bad_request("mode=points requires at least 'month' (YYYY-MM) or 'bbox'.")
        qs = HotspotObservation.objects.all()
        if filter_static:
            qs = qs.filter(hotspot_type=0, is_static_masked=False)
        if month_date:
            qs = qs.filter(acquired_at__year=month_date.year, acquired_at__month=month_date.month)
        if bbox_poly:
            qs = qs.filter(position__within=bbox_poly)
        for obs in qs.order_by("-acquired_at")[:limit]:
            features.append(
                {
                    "type": "Feature",
                    "geometry": json.loads(obs.position.geojson),
                    "properties": {
                        "layer": "hotspot_point",
                        "source": obs.source,
                        "satellite": obs.satellite,
                        "acquired_at": obs.acquired_at.isoformat(),
                        "frp": obs.frp,
                        "confidence_tier": obs.confidence_tier,
                        "hotspot_type": obs.hotspot_type,
                        "is_static_masked": obs.is_static_masked,
                    },
                }
            )
    elif mode == "grid":
        qs = GridCellMonth.objects.filter(filter_static=filter_static)
        if month_date:
            qs = qs.filter(month=month_date)
        if bbox_poly:
            qs = qs.filter(geom__intersects=bbox_poly)
        for cell in qs.order_by("cell_id")[:limit]:
            features.append(
                {
                    "type": "Feature",
                    "geometry": json.loads(cell.geom.geojson),
                    "properties": {
                        "layer": "grid_cell_month",
                        "cell_id": cell.cell_id,
                        "month": cell.month.strftime("%Y-%m"),
                        "modis_count": cell.modis_count,
                        "viirs_snpp_count": cell.viirs_snpp_count,
                        "viirs_noaa20_count": cell.viirs_noaa20_count,
                    },
                }
            )
    else:
        return _bad_request("mode must be 'grid' or 'points'.")

    if include_static_cells:
        static_qs = StaticFlareMaskCell.objects.all()
        if bbox_poly:
            static_qs = static_qs.filter(geom__intersects=bbox_poly)
        for cell in static_qs[:1000]:
            features.append(
                {
                    "type": "Feature",
                    "geometry": json.loads(cell.geom.geojson),
                    "properties": {
                        "layer": "static_flare_mask",
                        "cell_id": cell.cell_id,
                        "type23_count": cell.type23_count,
                        "active_months_snpp": cell.active_months_snpp,
                        "reason": cell.reason,
                    },
                }
            )

    return Response({"type": "FeatureCollection", "mode": mode, "features": features})


@api_view(["GET"])
def methodology_view(request):
    """Return active calibration parameters, out-of-sample metrics, and limitations."""
    region_code = request.query_params.get("region", "GA")
    filter_static = _parse_bool(request.query_params.get("filter_static"), default=True)

    run = CalibrationRun.objects.filter(
        region__code=region_code,
        filter_static=filter_static,
        is_active=True,
    ).first()

    return Response(
        {
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
    )


@api_view(["GET"])
def export_view(request):
    """Export monthly harmonized series as CSV with full provenance metadata."""
    region_code = request.query_params.get("region", "GA")
    filter_static = _parse_bool(request.query_params.get("filter_static"), default=True)
    try:
        start_month = _parse_month(request.query_params.get("start"))
        end_month = _parse_month(request.query_params.get("end"))
    except ValueError as exc:
        return _bad_request(str(exc))

    qs = HarmonizedMonthSeries.objects.filter(
        region__code=region_code,
        filter_static=filter_static,
        calibration_run__is_active=True,
    ).order_by("month")
    if start_month:
        qs = qs.filter(month__gte=start_month)
    if end_month:
        qs = qs.filter(month__lte=end_month)

    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="firepulse_{region_code}_series.csv"'
    writer = csv.writer(response)
    writer.writerow(
        [
            "region",
            "month",
            "filter_static",
            "modis_count",
            "viirs_snpp_count",
            "viirs_noaa20_count",
            "harmonized_value",
            "ci_low",
            "ci_high",
            "baseline_median",
            "anomaly_percent",
            "anomaly_absolute",
            "sensor_regime",
            "coverage_status",
            "method_version",
        ]
    )
    for row in qs:
        writer.writerow(
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
        )
    return response
