"""REST API v1 views for FirePulse (aligned with docs/api-contract.json)."""

import csv
import json
import math
import statistics
from datetime import date

from django.contrib.gis.geos import GEOSGeometry, Polygon
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


def _parse_polygon(value: str | None) -> GEOSGeometry | None:
    if not value:
        return None
    try:
        payload = json.loads(value)
        if payload.get("type") == "Feature":
            payload = payload["geometry"]
        geom = GEOSGeometry(json.dumps(payload), srid=4326)
        if geom.geom_type not in {"Polygon", "MultiPolygon"} or not geom.valid:
            raise ValueError
        return geom
    except (ValueError, KeyError, TypeError) as exc:
        raise ValueError("polygon must be a valid GeoJSON Polygon, MultiPolygon, or Feature.") from exc


def _bad_request(message: str) -> Response:
    return Response({"error": message}, status=status.HTTP_400_BAD_REQUEST)


def _custom_area_calendar(
    custom_geom: GEOSGeometry,
    area_id: str,
    area_name: str,
    filter_static: bool,
    start_month: date | None,
    end_month: date | None,
) -> dict:
    """Aggregate 0.25 deg GridCellMonth counts for any custom bbox/polygon and harmonize."""
    qs = GridCellMonth.objects.filter(filter_static=filter_static, geom__intersects=custom_geom)

    agg = list(
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

    ga_run = CalibrationRun.objects.filter(
        region__code="GA", filter_static=filter_static, is_active=True
    ).first()
    params = ga_run.params_json if ga_run else {}
    p_pow = params.get("power_law_p", 1.0)
    q_pow = params.get("power_law_q", 0.0)
    pt_pow = params.get("terra_only_p", 1.0)
    qt_pow = params.get("terra_only_q", 0.0)
    n20_ratio = params.get("noaa20_to_snpp_ratio", 1.0) or 1.0

    interim = []
    by_cal_month: dict[int, list[float]] = {m: [] for m in range(1, 13)}
    for row in agg:
        m_date = row["month"]
        mod = row["modis_count"] or 0
        terra = row["modis_terra_count"] or 0
        snpp = row["viirs_snpp_count"] or 0
        n20 = row["viirs_noaa20_count"] or 0

        if m_date < date(2002, 7, 1):
            regime = "partial_year" if m_date.year < 2001 else "modis_terra_only"
            hval = max(0.0, math.expm1(pt_pow * math.log1p(terra) + qt_pow)) if ga_run else float(terra)
        elif m_date < date(2012, 2, 1):
            regime = "modis_terra_aqua"
            hval = max(0.0, math.expm1(p_pow * math.log1p(mod) + q_pow)) if ga_run else float(mod)
        elif m_date <= date(2026, 10, 1):
            regime = "viirs_snpp_observed"
            hval = float(snpp)
        else:
            regime = "viirs_noaa20_bridge"
            hval = float(n20) / n20_ratio

        if 2001 <= m_date.year <= 2025:
            by_cal_month[m_date.month].append(hval)

        interim.append((row, round(hval, 2), regime))

    medians = {m: round(statistics.median(vals), 2) for m, vals in by_cal_month.items() if vals}
    series = []
    for row, hval, regime in interim:
        m_date = row["month"]
        if (start_month and m_date < start_month) or (end_month and m_date > end_month):
            continue
        med = medians.get(m_date.month)
        anom_abs = round(hval - med, 2) if med is not None else None
        anom_pct = round(100.0 * (hval - med) / med, 2) if (med is not None and med > 0) else None
        series.append(
            {
                "month": m_date.strftime("%Y-%m"),
                "modis_count": row["modis_count"],
                "modis_terra_count": row["modis_terra_count"],
                "modis_aqua_count": row["modis_aqua_count"],
                "viirs_snpp_count": row["viirs_snpp_count"],
                "viirs_noaa20_count": row["viirs_noaa20_count"],
                "harmonized_value": hval,
                "ci_low": None,
                "ci_high": None,
                "baseline_median": med,
                "baseline_iqr": None,
                "anomaly_percent": anom_pct,
                "anomaly_absolute": anom_abs,
                "sensor_regime": regime,
                "coverage_status": "partial_sp" if m_date.year < 2001 else "complete_sp",
                "uncertainty_note": "Custom area aggregated from 0.25 deg grid using national GA curve.",
            }
        )

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
        for reg in Region.objects.order_by("region_type", "code")
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
                "notes": meta.get("notes", ""),
            }
        )
    return Response({"region": region_code, "sensors": sensors})


@api_view(["GET"])
def calendar_view(request):
    """Return raw vs harmonized monthly series for a region, custom bbox, or polygon."""
    region_code = request.query_params.get("region", "GA")
    filter_static = _parse_bool(request.query_params.get("filter_static"), default=True)
    try:
        start_month = _parse_month(request.query_params.get("start"))
        end_month = _parse_month(request.query_params.get("end"))
        bbox_poly = _parse_bbox(request.query_params.get("bbox"))
        custom_poly = _parse_polygon(request.query_params.get("polygon"))
    except ValueError as exc:
        return _bad_request(str(exc))

    custom_geom = custom_poly or bbox_poly
    if custom_geom is not None:
        area_id = "CUSTOM_POLYGON" if custom_poly else "CUSTOM_BBOX"
        area_name = "Custom Polygon" if custom_poly else "Custom BBox"
        return Response(
            _custom_area_calendar(custom_geom, area_id, area_name, filter_static, start_month, end_month)
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
    region_code = request.query_params.get("region")
    filter_static = _parse_bool(request.query_params.get("filter_static"), default=True)
    include_static_cells = _parse_bool(request.query_params.get("include_static_cells"), default=False)

    try:
        month_date = _parse_month(request.query_params.get("month"))
        bbox_poly = _parse_bbox(request.query_params.get("bbox"))
        limit = max(1, min(5000, int(request.query_params.get("limit", "2000"))))
    except ValueError as exc:
        return _bad_request(str(exc))

    region_geom = None
    if region_code:
        reg = Region.objects.filter(code=region_code).first()
        if reg:
            region_geom = reg.geom

    spatial_filter_geom = bbox_poly or region_geom
    features: list[dict] = []

    if mode == "points":
        if month_date is None and bbox_poly is None:
            return _bad_request("mode=points requires at least 'month' (YYYY-MM) or 'bbox'.")
        qs = HotspotObservation.objects.all()
        if filter_static:
            qs = qs.filter(hotspot_type=0, is_static_masked=False)
        if month_date:
            qs = qs.filter(acquired_at__year=month_date.year, acquired_at__month=month_date.month)
        if spatial_filter_geom:
            qs = qs.filter(position__within=spatial_filter_geom)
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
        if spatial_filter_geom:
            qs = qs.filter(geom__intersects=spatial_filter_geom)
        for cell in qs.order_by("cell_id", "month")[:limit]:
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
        if spatial_filter_geom:
            static_qs = static_qs.filter(geom__intersects=spatial_filter_geom)
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
