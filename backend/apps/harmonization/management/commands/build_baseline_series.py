"""Calibrate MODIS->VIIRS harmonization models, baselines, and anomalies into PostGIS."""

import json
import math
import statistics
from datetime import date
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from apps.harmonization.models import (
    CalibrationRun,
    CoverageStatusChoices,
    HarmonizedMonthSeries,
    MonthlyBaseline,
    SensorRegimeChoices,
)
from apps.observations.models import Region

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
    mx = sum(xs) / len(xs)
    my = sum(ys) / len(ys)
    denom = sum((x - mx) ** 2 for x in xs)
    if denom == 0:
        return 1.0, 0.0
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / denom
    intercept = my - slope * mx
    return slope, intercept


def _eval_metrics(preds: list[float], actuals: list[float]) -> dict[str, float]:
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
                COUNT(*) FILTER (WHERE o.source = 'viirs-noaa20') AS viirs_noaa20_count
            FROM observations_hotspotobservation o
            JOIN observations_region r ON r.id = %s
            WHERE ST_Within(o.position, r.geom)
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
        }
        for row in rows
    }


def _calibrate_models(
    counts: dict[date, dict[str, int]],
    fallback_params: dict | None,
) -> tuple[dict, dict, str]:
    train_months = list(_month_range(TRAIN_START, TRAIN_END))
    test_months = list(_month_range(TEST_START, TEST_END))

    x_tr = [float(counts.get(m, {}).get("modis_count", 0)) for m in train_months]
    xt_tr = [float(counts.get(m, {}).get("modis_terra_count", 0)) for m in train_months]
    y_tr = [float(counts.get(m, {}).get("viirs_snpp_count", 0)) for m in train_months]

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
    pt_pow, qt_pow = _fit_linear([math.log1p(x) for x in xt_tr], [math.log1p(y) for y in y_tr])

    x_te = [float(counts.get(m, {}).get("modis_count", 0)) for m in test_months]
    xt_te = [float(counts.get(m, {}).get("modis_terra_count", 0)) for m in test_months]
    y_te = [float(counts.get(m, {}).get("viirs_snpp_count", 0)) for m in test_months]

    pred_ratio = [alpha * x for x in x_te]
    pred_ols = [max(0.0, ols_a * x + ols_b) for x in x_te]
    pred_pow = [max(0.0, math.expm1(p_pow * math.log1p(x) + q_pow)) for x in x_te]
    pred_terra = [max(0.0, math.expm1(pt_pow * math.log1p(x) + qt_pow)) for x in xt_te]

    res_log_main = [
        abs(math.log1p(y) - (p_pow * math.log1p(x) + q_pow)) for x, y in zip(x_te, y_te)
    ]
    res_log_terra = [
        abs(math.log1p(y) - (pt_pow * math.log1p(x) + qt_pow)) for x, y in zip(xt_te, y_te)
    ]
    q80_log = _conformal_quantile(res_log_main, 0.80)
    q80_terra_log = _conformal_quantile(res_log_terra, 0.80)

    n20_months = list(_month_range(date(2019, 1, 1), TEST_END))
    snpp_sum = sum(counts.get(m, {}).get("viirs_snpp_count", 0) for m in n20_months)
    n20_sum = sum(counts.get(m, {}).get("viirs_noaa20_count", 0) for m in n20_months)
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
        "train_months": len(train_months),
        "test_months": len(test_months),
        "models_out_of_sample": {
            "naive": _eval_metrics(x_te, y_te),
            "global_ratio": _eval_metrics(pred_ratio, y_te),
            "ols_linear": _eval_metrics(pred_ols, y_te),
            "power_law_log1p": _eval_metrics(pred_pow, y_te),
            "terra_only_power_law": _eval_metrics(pred_terra, y_te),
        },
    }
    return params, metrics, ""


def _build_series_from_params(
    counts: dict[date, dict[str, int]],
    params: dict,
    note: str = "",
) -> list[dict]:
    """Reconstruct monthly series from observed counts and calibrated model parameters."""
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

    reconstructed: list[dict] = []
    for m_date in all_months:
        row = counts.get(m_date, {})
        mod = row.get("modis_count", 0) if m_date >= date(2000, 11, 1) else None
        terra = row.get("modis_terra_count", 0) if m_date >= date(2000, 11, 1) else None
        aqua = row.get("modis_aqua_count", 0) if m_date >= TERRA_ONLY_CUTOFF else None
        snpp = row.get("viirs_snpp_count", 0) if date(2012, 1, 1) <= m_date <= SNPP_END else None
        n20 = row.get("viirs_noaa20_count", 0) if m_date >= date(2018, 4, 1) else None

        if m_date < date(2001, 1, 1):
            regime = SensorRegimeChoices.PARTIAL_YEAR
            cov = CoverageStatusChoices.PARTIAL_SP
            mu = pt_pow * math.log1p(terra or 0) + qt_pow
            hval = max(0.0, math.expm1(mu))
            ci_lo = max(0.0, math.expm1(mu - q80_t))
            ci_hi = max(0.0, math.expm1(mu + q80_t))
        elif m_date < TERRA_ONLY_CUTOFF:
            regime = SensorRegimeChoices.MODIS_TERRA_ONLY
            cov = CoverageStatusChoices.COMPLETE_SP
            mu = pt_pow * math.log1p(terra or 0) + qt_pow
            hval = max(0.0, math.expm1(mu))
            ci_lo = max(0.0, math.expm1(mu - q80_t))
            ci_hi = max(0.0, math.expm1(mu + q80_t))
        elif m_date < SNPP_START:
            regime = SensorRegimeChoices.MODIS_TERRA_AQUA
            cov = CoverageStatusChoices.COMPLETE_SP
            mu = p_pow * math.log1p(mod or 0) + q_pow
            hval = max(0.0, math.expm1(mu))
            ci_lo = max(0.0, math.expm1(mu - q80))
            ci_hi = max(0.0, math.expm1(mu + q80))
        elif m_date <= SNPP_END and snpp is not None:
            regime = SensorRegimeChoices.VIIRS_SNPP_OBSERVED
            cov = CoverageStatusChoices.COMPLETE_SP
            hval = float(snpp)
            ci_lo = hval
            ci_hi = hval
        elif n20 is not None:
            regime = SensorRegimeChoices.VIIRS_NOAA20_BRIDGE
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
                "uncertainty_note": note,
            }
        )
    return reconstructed


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


def _ingest_pipeline_bundle(bundle_path: Path, stdout, style) -> None:
    """Import an M1-validated calibration JSON bundle into PostGIS."""
    if not bundle_path.exists():
        raise CommandError(f"Pipeline bundle not found: {bundle_path}")
    try:
        bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CommandError(f"Failed to read pipeline bundle {bundle_path}: {exc}") from exc

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

    help = "Calibrate MODIS->VIIRS models or load M1 validated pipeline JSON outputs."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--from-pipeline",
            default=None,
            help="Optional path to an M1 JSON calibration bundle (e.g. /data/processed/calibration/bundle.json)",
        )

    def handle(self, *args, **options) -> None:
        pipeline_path = options.get("from_pipeline")
        if pipeline_path:
            _ingest_pipeline_bundle(Path(pipeline_path), self.stdout, self.style)
            return

        regions = list(Region.objects.order_by("region_type", "code"))
        if not regions:
            self.stdout.write(self.style.WARNING("No Region records found; run load_regions first."))
            return

        for filter_static in (True, False):
            national_params: dict | None = None
            for region in regions:
                counts = _fetch_region_monthly_counts(region.id, filter_static)
                if not counts:
                    continue

                params, metrics, note = _calibrate_models(counts, national_params)
                if region.code == "GA":
                    national_params = params

                reconstructed = _build_series_from_params(counts, params, note)
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

        self.stdout.write(self.style.SUCCESS("Harmonization & baseline generation complete."))
