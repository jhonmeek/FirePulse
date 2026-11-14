"""Shared parsing, spatial aggregation, and custom-area harmonization helpers for API v1."""

import json
import math
import statistics
from datetime import date

from django.contrib.gis.geos import GEOSGeometry, Polygon
from django.db.models import Sum
from rest_framework import status
from rest_framework.response import Response

from apps.harmonization.models import CalibrationRun
from apps.observations.models import GridCellMonth


def parse_bool(value: str | None, default: bool = True) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def parse_month(value: str | None) -> date | None:
    if not value:
        return None
    try:
        year_s, month_s = value.strip().split("-", 1)
        return date(int(year_s), int(month_s), 1)
    except ValueError as exc:
        raise ValueError(f"Invalid YYYY-MM month format: {value!r}") from exc


def next_month(d: date) -> date:
    if d.month == 12:
        return date(d.year + 1, 1, 1)
    return date(d.year, d.month + 1, 1)


def parse_bbox(value: str | None) -> Polygon | None:
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


def parse_polygon(value: str | None) -> GEOSGeometry | None:
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


def bad_request(message: str) -> Response:
    return Response({"error": message}, status=status.HTTP_400_BAD_REQUEST)


def parse_area_geometry(request) -> tuple[GEOSGeometry | None, str, str]:
    """Parse polygon (highest priority) or bbox from query params."""
    bbox_poly = parse_bbox(request.query_params.get("bbox"))
    custom_poly = parse_polygon(request.query_params.get("polygon"))
    if custom_poly is not None:
        return custom_poly, "CUSTOM_POLYGON", "Custom Polygon"
    if bbox_poly is not None:
        return bbox_poly, "CUSTOM_BBOX", "Custom BBox"
    return None, "", ""


def compute_quartiles(values: list[float]) -> tuple[float, float, float]:
    ordered = sorted(values)
    med = statistics.median(ordered)
    if len(ordered) >= 4:
        qs = statistics.quantiles(ordered, n=4)
        return med, qs[0], qs[2]
    return med, ordered[0], ordered[-1]


def compute_custom_area_series(
    custom_geom: GEOSGeometry,
    filter_static: bool,
) -> tuple[CalibrationRun | None, list[dict], list[dict]]:
    """Aggregate 0.25 deg GridCellMonth counts for a custom geometry and compute 2001-2025 baselines."""
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
    p_pow = float(params.get("power_law_p", 1.0))
    q_pow = float(params.get("power_law_q", 0.0))
    pt_pow = float(params.get("terra_only_p", p_pow))
    qt_pow = float(params.get("terra_only_q", q_pow))
    n20_ratio = float(params.get("noaa20_to_snpp_ratio", 1.0)) or 1.0

    by_cal_month: dict[int, list[float]] = {m: [] for m in range(1, 13)}
    interim: list[tuple[dict, float, str]] = []
    for row in agg:
        m_date = row["month"]
        mod = row["modis_count"] or 0
        terra = row["modis_terra_count"] or 0
        snpp = row["viirs_snpp_count"] or 0
        n20 = row["viirs_noaa20_count"] or 0

        if m_date < date(2001, 1, 1):
            regime = "partial_year"
            hval = max(0.0, math.expm1(pt_pow * math.log1p(terra) + qt_pow)) if ga_run else float(terra)
        elif m_date < date(2002, 7, 1):
            regime = "modis_terra_only"
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

    baselines_by_month: dict[int, tuple[float, float, float, int]] = {}
    monthly_baselines: list[dict] = []
    for cal_m in range(1, 13):
        vals = by_cal_month[cal_m]
        if not vals:
            continue
        med, p25, p75 = compute_quartiles(vals)
        med_r, p25_r, p75_r = round(med, 2), round(p25, 2), round(p75, 2)
        baselines_by_month[cal_m] = (med_r, p25_r, p75_r, len(vals))
        monthly_baselines.append(
            {
                "month_num": cal_m,
                "median": med_r,
                "iqr_p25": p25_r,
                "iqr_p75": p75_r,
                "reference_years_count": len(vals),
                "reference_period": "2001-2025",
            }
        )

    series: list[dict] = []
    for row, hval, regime in interim:
        m_date = row["month"]
        b = baselines_by_month.get(m_date.month)
        med, p25, p75 = (b[0], b[1], b[2]) if b else (None, None, None)
        anom_abs = round(hval - med, 2) if med is not None else None
        anom_pct = round(100.0 * (hval - med) / med, 2) if (med is not None and med > 0) else None
        series.append(
            {
                "month_date": m_date,
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
                "baseline_iqr": [p25, p75] if p25 is not None and p75 is not None else None,
                "anomaly_percent": anom_pct,
                "anomaly_absolute": anom_abs,
                "sensor_regime": regime,
                "coverage_status": "partial_sp" if m_date.year < 2001 else "complete_sp",
                "uncertainty_note": "Custom area aggregated from 0.25 deg grid using national GA curve.",
            }
        )

    return ga_run, monthly_baselines, series
