"""Calibrate MODIS->VIIRS harmonization models, baselines, and anomalies into PostGIS."""

import csv
import hashlib
import json
import math
import statistics
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from apps.api.cache import invalidate_api_cache
from apps.harmonization.models import (
    CalibrationRun,
    CoverageStatusChoices,
    HarmonizedMonthSeries,
    MonthlyBaseline,
    SensorRegimeChoices,
)
from apps.observations.models import ImportBatch, Region

TRAIN_START = date(2012, 2, 1)
TRAIN_END = date(2019, 12, 1)
TEST_START = date(2020, 1, 1)
TEST_END = date(2025, 12, 1)
TERRA_ONLY_CUTOFF = date(2002, 7, 1)
SNPP_START = date(2012, 2, 1)
SNPP_END = date(2026, 10, 1)


def _next_month(d: date) -> date:
    if d.month == 12:
        return date(d.year + 1, 1, 1)
    return date(d.year, d.month + 1, 1)


def _month_range(start: date, end: date) -> list[date]:
    out = []
    cur = start
    while cur <= end:
        out.append(cur)
        cur = _next_month(cur)
    return out


def _parse_iso_month(value: str) -> date:
    parts = value.strip().split("-")
    return date(int(parts[0]), int(parts[1]), int(parts[2]) if len(parts) > 2 else 1)


def _fit_linear(xs: list[float], ys: list[float]) -> tuple[float, float]:
    if not xs or not ys or len(xs) != len(ys):
        return 1.0, 0.0
    mx = sum(xs) / len(xs)
    my = sum(ys) / len(ys)
    denom = sum((x - mx) ** 2 for x in xs)
    if denom == 0:
        return 1.0, 0.0
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / denom
    intercept = my - slope * mx
    return slope, intercept


def _eval_metrics(preds: list[float], actuals: list[float]) -> dict[str, float]:
    if not actuals or len(preds) != len(actuals):
        return {"mae": 0.0, "rmse": 0.0, "bias": 0.0, "r2": 0.0}
    errs = [p - a for p, a in zip(preds, actuals)]
    mae = sum(abs(e) for e in errs) / len(errs)
    rmse = math.sqrt(sum(e * e for e in errs) / len(errs))
    bias = sum(errs) / len(errs)
    mean_a = sum(actuals) / len(actuals)
    sst = sum((a - mean_a) ** 2 for a in actuals)
    sse = sum(e * e for e in errs)
    r2 = 1.0 - sse / sst if sst > 0 else 0.0
    return {
        "mae": round(mae, 2),
        "rmse": round(rmse, 2),
        "bias": round(bias, 2),
        "r2": round(r2, 4),
    }


def _conformal_quantile(abs_residuals: list[float], level: float = 0.80) -> float:
    if not abs_residuals:
        return 0.25
    ordered = sorted(abs_residuals)
    idx = min(len(ordered) - 1, math.ceil((len(ordered) + 1) * level) - 1)
    return ordered[max(0, idx)]


def _quartiles(values: list[float]) -> tuple[float, float, float]:
    ordered = sorted(values)
    med = statistics.median(ordered)
    if len(ordered) >= 4:
        qs = statistics.quantiles(ordered, n=4)
        return med, qs[0], qs[2]
    return med, ordered[0], ordered[-1]


def _fetch_region_monthly_counts(region_id: int, filter_static: bool) -> dict[date, dict[str, int]]:
    static_sql = "AND o.hotspot_type = 0 AND NOT o.is_static_masked" if filter_static else ""
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT
                DATE_TRUNC('month', o.acquired_at)::date AS month,
                COUNT(*) FILTER (WHERE o.source = 'modis') AS modis_count,
                COUNT(*) FILTER (WHERE o.source = 'modis' AND o.satellite = 'Terra') AS modis_terra_count,
                COUNT(*) FILTER (WHERE o.source = 'modis' AND o.satellite = 'Aqua') AS modis_aqua_count,
                COUNT(*) FILTER (WHERE o.source = 'viirs-snpp') AS viirs_snpp_count,
                COUNT(*) FILTER (WHERE o.source = 'viirs-noaa20') AS viirs_noaa20_count,
                COUNT(*) FILTER (WHERE o.source = 'viirs-snpp' AND o.is_nrt) AS viirs_snpp_nrt_count,
                COUNT(*) FILTER (WHERE o.source = 'viirs-noaa20' AND o.is_nrt) AS viirs_noaa20_nrt_count
            FROM observations_hotspotobservation o
            JOIN observations_region r ON r.id = %s
            WHERE ST_Within(o.position, r.geom)
            AND o.counts_in_aggregates
            {static_sql}
            GROUP BY 1
            ORDER BY 1;
            """,
            [region_id],
        )
        rows = cursor.fetchall()
    return {
        row[0]: {
            "modis_count": row[1],
            "modis_terra_count": row[2],
            "modis_aqua_count": row[3],
            "viirs_snpp_count": row[4],
            "viirs_noaa20_count": row[5],
            "viirs_snpp_nrt_count": row[6],
            "viirs_noaa20_nrt_count": row[7],
        }
        for row in rows
    }


def _month_bounds(month: date) -> tuple[date, date]:
    """Return the first and last day of the calendar month containing ``month``."""
    first = month.replace(day=1)
    next_first = date(month.year + (month.month == 12), (month.month % 12) + 1, 1)
    return first, next_first - timedelta(days=1)


def _fetch_source_coverage() -> dict[str, list[tuple[date, date]]]:
    """Return the date span actually loaded for each FIRMS source.

    The spans come from ``ImportBatch.min_date``/``max_date``, i.e. the first and
    last observation of each loaded product. A month inside a span without any
    detection is a recorded zero; a month outside every span is a missing input and
    must not be turned into a fabricated zero.
    """
    coverage: dict[str, list[tuple[date, date]]] = defaultdict(list)
    for source, min_date, max_date in ImportBatch.objects.values_list(
        "source", "min_date", "max_date"
    ):
        if min_date and max_date:
            coverage[source].append((min_date, max_date))
    return dict(coverage)


def _month_is_covered(
    coverage: dict[str, list[tuple[date, date]]] | None, source: str, month: date
) -> bool:
    """True when at least one loaded batch overlaps the given calendar month."""
    if coverage is None:
        return True
    month_start, month_end = _month_bounds(month)
    return any(
        start <= month_end and end >= month_start for start, end in coverage.get(source, ())
    )


def _source_month_available(
    row: dict[str, int | None],
    key: str,
    coverage: dict[str, list[tuple[date, date]]] | None,
    source: str,
    month: date,
) -> bool:
    """True when a source has a recorded count for the month or a loaded product covering it.

    A recorded count (even zero) proves the product was processed for that month. The
    batch spans only add months where the region has no count at all, so that a missing
    product is never confused with an absence of detection.
    """
    return row.get(key) is not None or _month_is_covered(coverage, source, month)


def _count_or_none(row: dict[str, int | None], key: str) -> float | None:
    """Return float count when observed, 0.0 when key is omitted (PostGIS), or None when explicit null."""
    if key not in row:
        return 0.0
    val = row[key]
    return float(val) if val is not None else None


def _paired_series(
    counts: dict[date, dict[str, int | None]],
    months: list[date],
    x_key: str,
    y_key: str,
    *,
    coverage: dict[str, list[tuple[date, date]]] | None = None,
    x_source: str | None = None,
    y_source: str | None = None,
) -> tuple[list[float], list[float]]:
    xs: list[float] = []
    ys: list[float] = []
    for m in months:
        row = counts.get(m, {})
        if x_source is not None and not _source_month_available(
            row, x_key, coverage, x_source, m
        ):
            continue
        if y_source is not None and not _source_month_available(
            row, y_key, coverage, y_source, m
        ):
            continue
        xv = _count_or_none(row, x_key)
        yv = _count_or_none(row, y_key)
        if xv is not None and yv is not None:
            xs.append(xv)
            ys.append(yv)
    return xs, ys


def _calibrate_models(
    counts: dict[date, dict[str, int | None]],
    fallback_params: dict | None,
    coverage: dict[str, list[tuple[date, date]]] | None = None,
) -> tuple[dict, dict, str]:
    train_months = list(_month_range(TRAIN_START, TRAIN_END))
    test_months = list(_month_range(TEST_START, TEST_END))

    x_tr, y_tr = _paired_series(
        counts,
        train_months,
        "modis_count",
        "viirs_snpp_count",
        coverage=coverage,
        x_source="modis",
        y_source="viirs-snpp",
    )
    xt_tr, yt_tr = _paired_series(
        counts,
        train_months,
        "modis_terra_count",
        "viirs_snpp_count",
        coverage=coverage,
        x_source="modis",
        y_source="viirs-snpp",
    )

    active_pairs = sum(1 for x, y in zip(x_tr, y_tr) if x > 0 and y > 0)
    if active_pairs < 24 and fallback_params is not None:
        return (
            fallback_params,
            {"note": "Inherited national GA calibration parameters due to sparse sub-region sample."},
            "Inherited national GA calibration parameters (sparse sub-region sample).",
        )

    alpha = sum(y_tr) / sum(x_tr) if sum(x_tr) > 0 else 1.0
    ols_a, ols_b = _fit_linear(x_tr, y_tr)
    p_pow, q_pow = _fit_linear([math.log1p(x) for x in x_tr], [math.log1p(y) for y in y_tr])
    pt_pow, qt_pow = _fit_linear([math.log1p(x) for x in xt_tr], [math.log1p(y) for y in yt_tr])

    x_te, y_te = _paired_series(
        counts,
        test_months,
        "modis_count",
        "viirs_snpp_count",
        coverage=coverage,
        x_source="modis",
        y_source="viirs-snpp",
    )
    xt_te, yt_te = _paired_series(
        counts,
        test_months,
        "modis_terra_count",
        "viirs_snpp_count",
        coverage=coverage,
        x_source="modis",
        y_source="viirs-snpp",
    )

    pred_ratio = [alpha * x for x in x_te]
    pred_ols = [max(0.0, ols_a * x + ols_b) for x in x_te]
    pred_pow = [max(0.0, math.expm1(p_pow * math.log1p(x) + q_pow)) for x in x_te]
    pred_terra = [max(0.0, math.expm1(pt_pow * math.log1p(x) + qt_pow)) for x in xt_te]

    res_log_main = [
        abs(math.log1p(y) - (p_pow * math.log1p(x) + q_pow)) for x, y in zip(x_te, y_te)
    ]
    res_log_terra = [
        abs(math.log1p(y) - (pt_pow * math.log1p(x) + qt_pow)) for x, y in zip(xt_te, yt_te)
    ]
    q80_log = _conformal_quantile(res_log_main, 0.80)
    q80_terra_log = _conformal_quantile(res_log_terra, 0.80)

    n20_months = list(_month_range(date(2019, 1, 1), TEST_END))
    snpp_pairs, n20_pairs = _paired_series(
        counts,
        n20_months,
        "viirs_snpp_count",
        "viirs_noaa20_count",
        coverage=coverage,
        x_source="viirs-snpp",
        y_source="viirs-noaa20",
    )
    snpp_sum = sum(snpp_pairs)
    n20_sum = sum(n20_pairs)
    bridge_n20_over_snpp = (n20_sum / snpp_sum) if snpp_sum > 0 and n20_sum > 0 else 1.0

    params = {
        "global_ratio_alpha": round(alpha, 4),
        "ols_slope": round(ols_a, 4),
        "ols_intercept": round(ols_b, 2),
        "power_law_p": round(p_pow, 4),
        "power_law_q": round(q_pow, 4),
        "terra_only_p": round(pt_pow, 4),
        "terra_only_q": round(qt_pow, 4),
        "conformal_q80_log": round(q80_log, 4),
        "conformal_q80_terra_log": round(q80_terra_log, 4),
        "noaa20_to_snpp_ratio": round(bridge_n20_over_snpp, 4),
    }
    metrics = {
        "train_months": len(x_tr),
        "test_months": len(x_te),
        "models_out_of_sample": {
            "naive": _eval_metrics(x_te, y_te),
            "global_ratio": _eval_metrics(pred_ratio, y_te),
            "ols_linear": _eval_metrics(pred_ols, y_te),
            "power_law_log1p": _eval_metrics(pred_pow, y_te),
            "terra_only_power_law": _eval_metrics(pred_terra, yt_te),
        },
    }
    return params, metrics, ""


def _build_series_from_params(
    counts: dict[date, dict[str, int | None]],
    params: dict,
    note: str = "",
    partial_snpp_months: set[date] | None = None,
    coverage: dict[str, list[tuple[date, date]]] | None = None,
) -> list[dict]:
    """Reconstruct monthly series from observed counts and calibrated model parameters.

    ``coverage`` distinguishes a month whose product was loaded (a zero really means
    "no detection recorded") from a month with no loaded product (``None``, never 0).
    """
    min_m = min(counts.keys())
    max_m = max(counts.keys())
    all_months = _month_range(min_m, max_m)

    p_pow = float(params.get("power_law_p", 1.0))
    q_pow = float(params.get("power_law_q", 0.0))
    pt_pow = float(params.get("terra_only_p", p_pow))
    qt_pow = float(params.get("terra_only_q", q_pow))
    q80 = float(params.get("conformal_q80_log", 0.25))
    q80_t = float(params.get("conformal_q80_terra_log", q80))
    n20_ratio = float(params.get("noaa20_to_snpp_ratio", 1.0)) or 1.0
    partial_snpp = partial_snpp_months or set()

    reconstructed: list[dict] = []
    for m_date in all_months:
        row = counts.get(m_date, {})
        mod = (
            row.get("modis_count", 0)
            if m_date >= date(2000, 11, 1)
            and _source_month_available(row, "modis_count", coverage, "modis", m_date)
            else None
        )
        terra = (
            row.get("modis_terra_count", 0)
            if m_date >= date(2000, 11, 1)
            and _source_month_available(
                row, "modis_terra_count", coverage, "modis", m_date
            )
            else None
        )
        aqua = (
            row.get("modis_aqua_count", 0)
            if m_date >= TERRA_ONLY_CUTOFF
            and _source_month_available(
                row, "modis_aqua_count", coverage, "modis", m_date
            )
            else None
        )
        snpp = (
            row.get("viirs_snpp_count", 0)
            if date(2012, 1, 1) <= m_date <= SNPP_END
            and _source_month_available(
                row, "viirs_snpp_count", coverage, "viirs-snpp", m_date
            )
            else None
        )
        n20 = (
            row.get("viirs_noaa20_count", 0)
            if m_date >= date(2018, 4, 1)
            and _source_month_available(
                row, "viirs_noaa20_count", coverage, "viirs-noaa20", m_date
            )
            else None
        )
        month_note = note

        if m_date < date(2001, 1, 1) and terra is not None:
            regime = SensorRegimeChoices.PARTIAL_YEAR
            cov = CoverageStatusChoices.PARTIAL_SP
            mu = pt_pow * math.log1p(terra) + qt_pow
            hval = max(0.0, math.expm1(mu))
            ci_lo = max(0.0, math.expm1(mu - q80_t))
            ci_hi = max(0.0, math.expm1(mu + q80_t))
        elif date(2001, 1, 1) <= m_date < TERRA_ONLY_CUTOFF and terra is not None:
            regime = SensorRegimeChoices.MODIS_TERRA_ONLY
            cov = CoverageStatusChoices.COMPLETE_SP
            mu = pt_pow * math.log1p(terra) + qt_pow
            hval = max(0.0, math.expm1(mu))
            ci_lo = max(0.0, math.expm1(mu - q80_t))
            ci_hi = max(0.0, math.expm1(mu + q80_t))
        elif TERRA_ONLY_CUTOFF <= m_date < SNPP_START and mod is not None:
            regime = SensorRegimeChoices.MODIS_TERRA_AQUA
            cov = CoverageStatusChoices.COMPLETE_SP
            mu = p_pow * math.log1p(mod) + q_pow
            hval = max(0.0, math.expm1(mu))
            ci_lo = max(0.0, math.expm1(mu - q80))
            ci_hi = max(0.0, math.expm1(mu + q80))
        elif SNPP_START <= m_date <= SNPP_END and snpp is not None:
            regime = SensorRegimeChoices.VIIRS_SNPP_OBSERVED
            snpp_nrt = row.get("viirs_snpp_nrt_count", 0) or 0
            if m_date in partial_snpp:
                cov = CoverageStatusChoices.PARTIAL_SP
            elif snpp > 0 and snpp_nrt >= snpp:
                cov = CoverageStatusChoices.NRT_ONLY
            elif snpp_nrt > 0:
                cov = CoverageStatusChoices.MIXED_SP_NRT
            else:
                cov = CoverageStatusChoices.COMPLETE_SP
            hval = float(snpp)
            ci_lo = hval
            ci_hi = hval
        elif n20 is not None:
            regime = SensorRegimeChoices.VIIRS_NOAA20_BRIDGE
            n20_nrt = row.get("viirs_noaa20_nrt_count", 0) or 0
            if n20 > 0 and n20_nrt >= n20:
                cov = CoverageStatusChoices.NRT_ONLY
            elif n20_nrt > 0:
                cov = CoverageStatusChoices.MIXED_SP_NRT
            else:
                cov = CoverageStatusChoices.NRT_ONLY if m_date.year >= 2026 else CoverageStatusChoices.COMPLETE_SP
            hval = float(n20) / n20_ratio
            ci_lo = hval * 0.90
            ci_hi = hval * 1.10
        else:
            regime = SensorRegimeChoices.MISSING
            cov = CoverageStatusChoices.NO_DATA
            hval = None
            ci_lo = None
            ci_hi = None
            month_note = _missing_month_note(m_date, coverage, note)

        reconstructed.append(
            {
                "month": m_date,
                "modis_count": mod,
                "modis_terra_count": terra,
                "modis_aqua_count": aqua,
                "viirs_snpp_count": snpp,
                "viirs_noaa20_count": n20,
                "harmonized_value": round(hval, 2) if hval is not None else None,
                "ci_low": round(ci_lo, 2) if ci_lo is not None else None,
                "ci_high": round(ci_hi, 2) if ci_hi is not None else None,
                "sensor_regime": regime,
                "coverage_status": cov,
                "uncertainty_note": month_note,
            }
        )
    return reconstructed


def _missing_month_note(
    month: date,
    coverage: dict[str, list[tuple[date, date]]] | None,
    note: str,
) -> str:
    """Explain why a month has no reconstructed value (missing product vs no detection)."""
    if coverage is None:
        return note
    expected: list[str] = []
    if date(2000, 11, 1) <= month <= date(2025, 12, 1):
        expected.append("modis")
    if date(2012, 1, 1) <= month <= SNPP_END:
        expected.append("viirs-snpp")
    if month >= date(2018, 4, 1):
        expected.append("viirs-noaa20")
    missing = [src for src in expected if not _month_is_covered(coverage, src, month)]
    if not missing:
        return note
    detail = f"No loaded product covers this month for: {', '.join(missing)}."
    return f"{note} {detail}".strip()


def _compute_baselines_map(reconstructed: list[dict]) -> dict[int, tuple[float, float, float, int, str]]:
    by_cal_month: dict[int, list[float]] = {m: [] for m in range(1, 13)}
    for item in reconstructed:
        m_date = item["month"]
        if 2001 <= m_date.year <= 2025 and item.get("harmonized_value") is not None:
            by_cal_month[m_date.month].append(float(item["harmonized_value"]))

    baselines_map: dict[int, tuple[float, float, float, int, str]] = {}
    for cal_m, vals in by_cal_month.items():
        if vals:
            med, p25, p75 = _quartiles(vals)
            baselines_map[cal_m] = (round(med, 2), round(p25, 2), round(p75, 2), len(vals), "2001-2025")
    return baselines_map


def _persist_region_calibration(
    *,
    region: Region,
    filter_static: bool,
    method_name: str,
    method_version: str,
    reference_scale: str,
    train_start: date,
    train_end: date,
    test_start: date,
    test_end: date,
    params: dict,
    metrics: dict,
    baselines_map: dict[int, tuple[float, float, float, int, str]],
    reconstructed: list[dict],
) -> None:
    """Atomically deactivate previous active runs and persist calibration, baselines, and series."""
    with transaction.atomic():
        CalibrationRun.objects.filter(
            region=region, filter_static=filter_static, is_active=True
        ).update(is_active=False)

        run = CalibrationRun.objects.create(
            region=region,
            filter_static=filter_static,
            method_name=method_name,
            method_version=method_version,
            reference_scale=reference_scale,
            train_start=train_start,
            train_end=train_end,
            test_start=test_start,
            test_end=test_end,
            params_json=params,
            metrics_json=metrics,
            is_active=True,
        )

        MonthlyBaseline.objects.bulk_create(
            [
                MonthlyBaseline(
                    region=region,
                    calibration_run=run,
                    month_num=cal_m,
                    filter_static=filter_static,
                    baseline_median=med,
                    iqr_p25=p25,
                    iqr_p75=p75,
                    reference_years_count=ny,
                    reference_period=ref_period,
                )
                for cal_m, (med, p25, p75, ny, ref_period) in sorted(baselines_map.items())
            ]
        )

        series_objs = []
        for item in reconstructed:
            b = baselines_map.get(item["month"].month)
            med = item.get("baseline_median")
            p25 = item.get("baseline_iqr_p25")
            p75 = item.get("baseline_iqr_p75")
            if med is None and b is not None:
                med, p25, p75 = b[0], b[1], b[2]

            hval = item.get("harmonized_value")
            anom_abs = item.get("anomaly_absolute")
            anom_pct = item.get("anomaly_percent")
            if hval is not None and med is not None:
                if anom_abs is None:
                    anom_abs = round(float(hval) - float(med), 2)
                if anom_pct is None and med > 0:
                    anom_pct = round(100.0 * (float(hval) - float(med)) / float(med), 2)

            series_objs.append(
                HarmonizedMonthSeries(
                    region=region,
                    calibration_run=run,
                    month=item["month"],
                    filter_static=filter_static,
                    modis_count=item.get("modis_count"),
                    modis_terra_count=item.get("modis_terra_count"),
                    modis_aqua_count=item.get("modis_aqua_count"),
                    viirs_snpp_count=item.get("viirs_snpp_count"),
                    viirs_noaa20_count=item.get("viirs_noaa20_count"),
                    harmonized_value=hval,
                    ci_low=item.get("ci_low"),
                    ci_high=item.get("ci_high"),
                    baseline_median=med,
                    baseline_iqr_p25=p25,
                    baseline_iqr_p75=p75,
                    anomaly_percent=anom_pct,
                    anomaly_absolute=anom_abs,
                    sensor_regime=item["sensor_regime"],
                    coverage_status=item["coverage_status"],
                    method_version=method_version,
                    uncertainty_note=item.get("uncertainty_note", ""),
                )
            )
        HarmonizedMonthSeries.objects.bulk_create(series_objs)


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _parse_m1_int(value) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise CommandError(f"Invalid integer count in M1 artifact: {value!r}") from exc


def _parse_m1_float(value) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise CommandError(f"Invalid numeric value in M1 artifact: {value!r}") from exc


def _verify_manifest_checksum(data_path: Path, manifest: dict | None, key: str) -> str:
    actual = _sha256_file(data_path)
    if manifest and key in manifest:
        expected = manifest[key]
        if actual != expected:
            raise CommandError(
                f"SHA-256 mismatch for {data_path.name}: expected {expected}, got {actual}."
            )
    return actual


def _load_json_object(path: Path, label: str) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CommandError(f"Failed to read {label} {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise CommandError(f"Expected JSON object in {path}.")
    return payload


def _resolve_pipeline_input(
    bundle_path: Path,
) -> tuple[str, Path, dict | None, str | None, dict | None]:
    """Identify calibrated bundle JSON vs M1 monthly artifact (dir, manifest, calendar JSON, or CSV)."""
    if not bundle_path.exists():
        raise CommandError(f"Pipeline artifact not found: {bundle_path}")

    if bundle_path.is_dir():
        manifest_path = bundle_path / "manifest.json"
        if manifest_path.exists():
            return _resolve_pipeline_input(manifest_path)
        for name, kind in (
            ("calendar.json", "m1_calendar_json"),
            ("monthly_counts.csv", "m1_monthly_csv"),
            ("pipeline_bundle.json", "bundle"),
            ("bundle.json", "bundle"),
        ):
            candidate = bundle_path / name
            if candidate.exists():
                return _resolve_pipeline_input(candidate)
        raise CommandError(
            f"Directory {bundle_path} contains neither manifest.json, calendar.json, "
            "monthly_counts.csv, nor a calibrated bundle JSON."
        )

    if bundle_path.suffix.lower() == ".csv":
        sibling_manifest = bundle_path.parent / "manifest.json"
        manifest = None
        manifest_sha = None
        if sibling_manifest.exists():
            parsed = _load_json_object(sibling_manifest, "manifest")
            if parsed.get("artifact_kind") == "firepulse-monthly":
                manifest = parsed
                manifest_sha = _sha256_file(sibling_manifest)
        return "m1_monthly_csv", bundle_path, manifest, manifest_sha, None

    payload = _load_json_object(bundle_path, "pipeline artifact")
    kind = payload.get("artifact_kind")

    if kind == "firepulse-monthly":
        manifest_sha = _sha256_file(bundle_path)
        cal_path = bundle_path.parent / "calendar.json"
        csv_path = bundle_path.parent / "monthly_counts.csv"
        if cal_path.exists():
            return "m1_calendar_json", cal_path, payload, manifest_sha, None
        if csv_path.exists():
            return "m1_monthly_csv", csv_path, payload, manifest_sha, None
        raise CommandError(
            f"M1 manifest {bundle_path} found, but neither calendar.json nor monthly_counts.csv "
            f"exists in {bundle_path.parent}."
        )

    if kind == "firepulse-monthly-calendar":
        sibling_manifest = bundle_path.parent / "manifest.json"
        manifest = None
        manifest_sha = None
        if sibling_manifest.exists():
            parsed = _load_json_object(sibling_manifest, "manifest")
            if parsed.get("artifact_kind") == "firepulse-monthly":
                manifest = parsed
                manifest_sha = _sha256_file(sibling_manifest)
        return "m1_calendar_json", bundle_path, manifest, manifest_sha, payload

    return "bundle", bundle_path, None, None, payload


def _read_m1_rows(
    source_kind: str,
    source_path: Path,
    manifest: dict | None,
    cached_payload: dict | None,
) -> tuple[list[dict], str, str]:
    """Read and checksum-verify M1 calendar.json or monthly_counts.csv rows."""
    if source_kind == "m1_calendar_json":
        input_sha = _verify_manifest_checksum(source_path, manifest, "calendar_sha256")
        payload = cached_payload or _load_json_object(source_path, "M1 calendar")
        rows = payload.get("rows")
        if not isinstance(rows, list) or not rows:
            raise CommandError(f"M1 calendar {source_path} must contain a non-empty 'rows' list.")
        normalized = [
            {
                "region": str(r.get("region", "")).strip(),
                "dataset_scope": str(r.get("dataset_scope", "")).strip(),
                "month": str(r.get("month", "")).strip(),
                "source": str(r.get("source", "")).strip(),
                "satellite": str(r.get("satellite", "")).strip(),
                "count_raw": _parse_m1_int(r.get("count_raw")),
                "count_type0_candidate": _parse_m1_int(r.get("count_type0_candidate")),
                "harmonized_value": _parse_m1_float(r.get("harmonized_value")),
                "status": str(r.get("status", "")).strip(),
                "observation_coverage": str(r.get("observation_coverage", "unknown")).strip(),
            }
            for r in rows
        ]
        return normalized, "firepulse-monthly-calendar", input_sha

    input_sha = _verify_manifest_checksum(source_path, manifest, "monthly_csv_sha256")
    with source_path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        required = {"region", "month", "source", "satellite", "count_raw", "count_type0_candidate"}
        fieldnames = set(reader.fieldnames or [])
        missing = sorted(required - fieldnames)
        if missing:
            raise CommandError(
                f"M1 monthly CSV {source_path} is missing required columns: {', '.join(missing)}"
            )
        normalized = [
            {
                "region": str(r.get("region", "")).strip(),
                "dataset_scope": str(r.get("dataset_scope", "")).strip(),
                "month": str(r.get("month", "")).strip(),
                "source": str(r.get("source", "")).strip(),
                "satellite": str(r.get("satellite", "")).strip(),
                "count_raw": _parse_m1_int(r.get("count_raw")),
                "count_type0_candidate": _parse_m1_int(r.get("count_type0_candidate")),
                "harmonized_value": _parse_m1_float(r.get("harmonized_value")),
                "status": str(r.get("status", "")).strip(),
                "observation_coverage": str(r.get("observation_coverage", "unknown")).strip(),
            }
            for r in reader
        ]
    if not normalized:
        raise CommandError(f"M1 monthly CSV {source_path} contains no data rows.")
    return normalized, "firepulse-monthly-csv", input_sha


def _pivot_m1_rows_by_region(rows: list[dict], count_field: str) -> dict[str, dict]:
    """Pivot long M1 (region, month, source, satellite) rows into monthly sensor counts per region."""
    by_region_month: dict[str, dict[date, dict]] = defaultdict(dict)
    scopes_by_region: dict[str, set[str]] = defaultdict(set)
    cov_by_region: dict[str, set[str]] = defaultdict(set)
    partial_snpp_by_region: dict[str, set[date]] = defaultdict(set)
    pre_harmonized_by_region: dict[str, dict[date, float]] = defaultdict(dict)

    for row in rows:
        reg = row["region"]
        if not reg or not row["month"]:
            continue
        m_date = _parse_iso_month(row["month"])
        bucket = by_region_month[reg].setdefault(
            m_date,
            {
                "modis_terra_count": None,
                "modis_aqua_count": None,
                "modis_count": None,
                "viirs_snpp_count": None,
                "viirs_noaa20_count": None,
            },
        )
        val = row[count_field]
        src = row["source"]
        sat = row["satellite"]
        if src == "modis" and sat == "Terra":
            bucket["modis_terra_count"] = val
        elif src == "modis" and sat == "Aqua":
            bucket["modis_aqua_count"] = val
        elif src == "viirs-snpp" and sat in ("N", "S-NPP", ""):
            bucket["viirs_snpp_count"] = val
            if row["status"] == "partial_period":
                partial_snpp_by_region[reg].add(m_date)
        elif src == "viirs-noaa20" and sat in ("N20", "NOAA-20", ""):
            bucket["viirs_noaa20_count"] = val

        if row["dataset_scope"]:
            scopes_by_region[reg].add(row["dataset_scope"])
        if row["observation_coverage"]:
            cov_by_region[reg].add(row["observation_coverage"])
        if row["harmonized_value"] is not None:
            pre_harmonized_by_region[reg][m_date] = float(row["harmonized_value"])

    pivoted: dict[str, dict] = {}
    for reg, month_map in by_region_month.items():
        for bucket in month_map.values():
            terra = bucket["modis_terra_count"]
            aqua = bucket["modis_aqua_count"]
            if terra is not None or aqua is not None:
                bucket["modis_count"] = (terra or 0) + (aqua or 0)
        pivoted[reg] = {
            "counts": month_map,
            "partial_snpp": partial_snpp_by_region[reg],
            "pre_harmonized": pre_harmonized_by_region[reg],
            "scopes": sorted(scopes_by_region[reg]),
            "coverages": sorted(cov_by_region[reg]),
        }
    return pivoted


def _ingest_m1_monthly(
    *,
    source_kind: str,
    source_path: Path,
    manifest: dict | None,
    manifest_sha: str | None,
    cached_payload: dict | None,
    stdout,
    style,
) -> None:
    """Import M1 monthly calendar/CSV artifacts, preserving scientific provenance and caveats."""
    rows, artifact_kind, input_sha = _read_m1_rows(source_kind, source_path, manifest, cached_payload)
    loaded = 0

    for filter_static, count_field in (
        (True, "count_type0_candidate"),
        (False, "count_raw"),
    ):
        by_region = _pivot_m1_rows_by_region(rows, count_field)
        national_params: dict | None = None
        for region_code, reg_data in by_region.items():
            region = Region.objects.filter(code=region_code).first()
            if not region:
                stdout.write(style.WARNING(f"Skipping unknown region in M1 artifact: {region_code!r}"))
                continue

            counts = reg_data["counts"]
            if not counts:
                continue

            params, metrics, note = _calibrate_models(counts, national_params)
            if region.code == "GA":
                national_params = params

            caveat = (
                "Source: M1 monthly counts (type=0 candidates without 0.05 deg static flare mask; "
                "harmonized on M2 power-law)."
                if filter_static
                else "Source: M1 raw monthly counts (all FIRMS types, unfiltered; harmonized on M2 power-law)."
            )
            full_note = f"{note} {caveat}".strip()
            reconstructed = _build_series_from_params(
                counts,
                params,
                full_note,
                partial_snpp_months=reg_data["partial_snpp"],
            )
            pre_harm = reg_data["pre_harmonized"] if filter_static else {}
            for item in reconstructed:
                if item["month"] in pre_harm:
                    item["harmonized_value"] = round(pre_harm[item["month"]], 2)

            baselines_map = _compute_baselines_map(reconstructed)
            metrics["m1_provenance"] = {
                "artifact_kind": artifact_kind,
                "source_file": source_path.name,
                "count_field": count_field,
                "input_sha256": input_sha,
                "manifest_sha256": manifest_sha,
                "manifest_scope": manifest.get("scope") if manifest else None,
                "dataset_scopes": reg_data["scopes"],
                "observation_coverages": reg_data["coverages"],
                "static_flare_mask_applied": False,
                "precomputed_harmonized_months": len(pre_harm),
            }

            _persist_region_calibration(
                region=region,
                filter_static=filter_static,
                method_name=(
                    "m1_monthly_type0_candidate_power_law"
                    if filter_static
                    else "m1_monthly_raw_power_law"
                ),
                method_version="v2.0-m1-monthly",
                reference_scale="VIIRS_375m_SNPP_equiv",
                train_start=TRAIN_START,
                train_end=TRAIN_END,
                test_start=TEST_START,
                test_end=TEST_END,
                params=params,
                metrics=metrics,
                baselines_map=baselines_map,
                reconstructed=reconstructed,
            )
            loaded += 1
            stdout.write(
                f"Loaded M1 monthly run for {region.code} (filter_static={filter_static}, "
                f"field={count_field}, source={source_path.name}): {len(reconstructed)} months."
            )

    if loaded == 0:
        raise CommandError(
            "No matching Region rows found in database for M1 artifact regions; run load_regions first."
        )
    stdout.write(style.SUCCESS(f"M1 monthly artifact import complete ({loaded} region-runs updated)."))


def _ingest_pipeline_bundle(bundle_path: Path, stdout, style) -> None:
    """Import an M1-validated calibration bundle JSON or M1 monthly artifact into PostGIS."""
    source_kind, resolved_path, manifest, manifest_sha, cached_payload = _resolve_pipeline_input(
        bundle_path
    )
    if source_kind != "bundle":
        _ingest_m1_monthly(
            source_kind=source_kind,
            source_path=resolved_path,
            manifest=manifest,
            manifest_sha=manifest_sha,
            cached_payload=cached_payload,
            stdout=stdout,
            style=style,
        )
        return

    bundle = cached_payload or _load_json_object(resolved_path, "pipeline bundle")
    entries = bundle.get("regions")
    if not isinstance(entries, list) or not entries:
        raise CommandError("Pipeline bundle must contain a non-empty 'regions' list.")

    default_name = bundle.get("method_name", "power_law_log1p_static_masked")
    default_version = bundle.get("method_version", "v2.0")
    default_scale = bundle.get("reference_scale", "VIIRS_375m_SNPP_equiv")

    loaded = 0
    for entry in entries:
        region_code = entry.get("region")
        region = Region.objects.filter(code=region_code).first()
        if not region:
            stdout.write(style.WARNING(f"Skipping unknown region in pipeline bundle: {region_code!r}"))
            continue

        filter_static = bool(entry.get("filter_static", True))
        params = entry.get("params", {})
        metrics = entry.get("metrics", {})
        method_name = entry.get("method_name", default_name)
        method_version = entry.get("method_version", default_version)
        reference_scale = entry.get("reference_scale", default_scale)
        train_start = _parse_iso_month(entry.get("train_start", TRAIN_START.isoformat()))
        train_end = _parse_iso_month(entry.get("train_end", TRAIN_END.isoformat()))
        test_start = _parse_iso_month(entry.get("test_start", TEST_START.isoformat()))
        test_end = _parse_iso_month(entry.get("test_end", TEST_END.isoformat()))

        raw_series = entry.get("series")
        if raw_series:
            reconstructed = []
            for row in raw_series:
                iqr = row.get("baseline_iqr")
                p25 = row.get("baseline_iqr_p25", iqr[0] if isinstance(iqr, list) and len(iqr) == 2 else None)
                p75 = row.get("baseline_iqr_p75", iqr[1] if isinstance(iqr, list) and len(iqr) == 2 else None)
                reconstructed.append(
                    {
                        **row,
                        "month": _parse_iso_month(row["month"]),
                        "baseline_iqr_p25": p25,
                        "baseline_iqr_p75": p75,
                    }
                )
        else:
            counts = _fetch_region_monthly_counts(region.id, filter_static)
            if not counts:
                stdout.write(style.WARNING(f"No observations for {region.code}; skipping."))
                continue
            reconstructed = _build_series_from_params(counts, params, entry.get("uncertainty_note", ""))

        raw_baselines = entry.get("baselines")
        if raw_baselines:
            baselines_map = {
                int(b["month_num"]): (
                    float(b["baseline_median"]),
                    b.get("iqr_p25"),
                    b.get("iqr_p75"),
                    int(b.get("reference_years_count", 0)),
                    b.get("reference_period", "2001-2025"),
                )
                for b in raw_baselines
            }
        else:
            baselines_map = _compute_baselines_map(reconstructed)

        _persist_region_calibration(
            region=region,
            filter_static=filter_static,
            method_name=method_name,
            method_version=method_version,
            reference_scale=reference_scale,
            train_start=train_start,
            train_end=train_end,
            test_start=test_start,
            test_end=test_end,
            params=params,
            metrics=metrics,
            baselines_map=baselines_map,
            reconstructed=reconstructed,
        )
        loaded += 1
        stdout.write(
            f"Loaded pipeline run for {region.code} (filter_static={filter_static}, "
            f"version={method_version}): {len(reconstructed)} months."
        )

    stdout.write(style.SUCCESS(f"Pipeline bundle import complete ({loaded} region-runs updated)."))


class Command(BaseCommand):
    """Build CalibrationRun, MonthlyBaseline, and HarmonizedMonthSeries for all regions."""

    help = "Calibrate MODIS->VIIRS models or load M1 monthly artifacts / calibration bundles."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--from-pipeline",
            default=None,
            help=(
                "Optional path to M1 monthly directory/calendar.json/monthly_counts.csv/manifest.json "
                "(e.g. /data/processed/monthly) or a calibrated JSON bundle"
            ),
        )

    def handle(self, *args, **options) -> None:
        pipeline_path = options.get("from_pipeline")
        if pipeline_path:
            _ingest_pipeline_bundle(Path(pipeline_path), self.stdout, self.style)
            invalidate_api_cache()
            return

        regions = list(Region.objects.order_by("region_type", "code"))
        if not regions:
            self.stdout.write(self.style.WARNING("No Region records found; run load_regions first."))
            return

        coverage = _fetch_source_coverage()

        for filter_static in (True, False):
            national_params: dict | None = None
            for region in regions:
                counts = _fetch_region_monthly_counts(region.id, filter_static)
                if not counts:
                    continue

                params, metrics, note = _calibrate_models(counts, national_params, coverage)
                if region.code == "GA":
                    national_params = params

                reconstructed = _build_series_from_params(counts, params, note, coverage=coverage)
                baselines_map = _compute_baselines_map(reconstructed)
                _persist_region_calibration(
                    region=region,
                    filter_static=filter_static,
                    method_name=(
                        "power_law_log1p_static_masked"
                        if filter_static
                        else "power_law_log1p_unfiltered"
                    ),
                    method_version="v2.0",
                    reference_scale="VIIRS_375m_SNPP_equiv",
                    train_start=TRAIN_START,
                    train_end=TRAIN_END,
                    test_start=TEST_START,
                    test_end=TEST_END,
                    params=params,
                    metrics=metrics,
                    baselines_map=baselines_map,
                    reconstructed=reconstructed,
                )

                self.stdout.write(
                    f"Built {region.code} (filter_static={filter_static}): "
                    f"{len(reconstructed)} months, "
                    f"test R2={metrics.get('models_out_of_sample', {}).get('power_law_log1p', {}).get('r2')}"
                )

        invalidate_api_cache()
        self.stdout.write(self.style.SUCCESS("Harmonization & baseline generation complete."))
