"""Calibrate MODIS->VIIRS harmonization models, baselines, and anomalies into PostGIS."""

import math
import statistics
from datetime import date

from django.core.management.base import BaseCommand
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
    train_months = [m for m in _month_range(TRAIN_START, TRAIN_END)]
    test_months = [m for m in _month_range(TEST_START, TEST_END)]

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

    # Evaluate out-of-sample 2020-2025
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

    n20_months = [m for m in _month_range(date(2019, 1, 1), TEST_END)]
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


class Command(BaseCommand):
    """Build CalibrationRun, MonthlyBaseline, and HarmonizedMonthSeries for all regions."""

    help = "Calibrate MODIS->VIIRS models and populate harmonized series & baselines."

    def handle(self, *args, **options) -> None:
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

                min_m = min(counts.keys())
                max_m = max(counts.keys())
                all_months = _month_range(min_m, max_m)

                p_pow = params["power_law_p"]
                q_pow = params["power_law_q"]
                pt_pow = params["terra_only_p"]
                qt_pow = params["terra_only_q"]
                q80 = params["conformal_q80_log"]
                q80_t = params["conformal_q80_terra_log"]
                n20_ratio = params["noaa20_to_snpp_ratio"] or 1.0

                reconstructed: list[dict] = []
                for m_date in all_months:
                    row = counts.get(m_date, {})
                    mod = row.get("modis_count", 0) if m_date >= date(2000, 11, 1) else None
                    terra = row.get("modis_terra_count", 0) if m_date >= date(2000, 11, 1) else None
                    aqua = row.get("modis_aqua_count", 0) if m_date >= TERRA_ONLY_CUTOFF else None
                    snpp = row.get("viirs_snpp_count", 0) if date(2012, 1, 1) <= m_date <= SNPP_END else None
                    n20 = row.get("viirs_noaa20_count", 0) if m_date >= date(2018, 4, 1) else None

                    row_note = note
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
                            "uncertainty_note": row_note,
                        }
                    )

                # Baselines computed across complete reference years 2001..2025
                by_cal_month: dict[int, list[float]] = {m: [] for m in range(1, 13)}
                for item in reconstructed:
                    if 2001 <= item["month"].year <= 2025 and item["harmonized_value"] is not None:
                        by_cal_month[item["month"].month].append(item["harmonized_value"])

                baselines_map: dict[int, tuple[float, float, float, int]] = {}
                for cal_m, vals in by_cal_month.items():
                    if vals:
                        med, p25, p75 = _quartiles(vals)
                        baselines_map[cal_m] = (round(med, 2), round(p25, 2), round(p75, 2), len(vals))

                with transaction.atomic():
                    CalibrationRun.objects.filter(
                        region=region, filter_static=filter_static, is_active=True
                    ).update(is_active=False)

                    run = CalibrationRun.objects.create(
                        region=region,
                        filter_static=filter_static,
                        method_name="power_law_log1p_static_masked" if filter_static else "power_law_log1p_unfiltered",
                        method_version="v2.0",
                        reference_scale="VIIRS_375m_SNPP_equiv",
                        train_start=TRAIN_START,
                        train_end=TRAIN_END,
                        test_start=TEST_START,
                        test_end=TEST_END,
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
                                reference_period="2001-2025",
                            )
                            for cal_m, (med, p25, p75, ny) in baselines_map.items()
                        ]
                    )

                    series_objs = []
                    for item in reconstructed:
                        b = baselines_map.get(item["month"].month)
                        med, p25, p75 = (b[0], b[1], b[2]) if b else (None, None, None)
                        hval = item["harmonized_value"]
                        anom_abs = round(hval - med, 2) if (hval is not None and med is not None) else None
                        anom_pct = round(100.0 * (hval - med) / med, 2) if (hval is not None and med and med > 0) else None
                        series_objs.append(
                            HarmonizedMonthSeries(
                                region=region,
                                calibration_run=run,
                                month=item["month"],
                                filter_static=filter_static,
                                modis_count=item["modis_count"],
                                modis_terra_count=item["modis_terra_count"],
                                modis_aqua_count=item["modis_aqua_count"],
                                viirs_snpp_count=item["viirs_snpp_count"],
                                viirs_noaa20_count=item["viirs_noaa20_count"],
                                harmonized_value=hval,
                                ci_low=item["ci_low"],
                                ci_high=item["ci_high"],
                                baseline_median=med,
                                baseline_iqr_p25=p25,
                                baseline_iqr_p75=p75,
                                anomaly_percent=anom_pct,
                                anomaly_absolute=anom_abs,
                                sensor_regime=item["sensor_regime"],
                                coverage_status=item["coverage_status"],
                                method_version="v2.0",
                                uncertainty_note=item["uncertainty_note"],
                            )
                        )
                    HarmonizedMonthSeries.objects.bulk_create(series_objs)

                self.stdout.write(
                    f"Built {region.code} (filter_static={filter_static}): "
                    f"{len(reconstructed)} months, test R2={metrics.get('models_out_of_sample', {}).get('power_law_log1p', {}).get('r2')}"
                )

        self.stdout.write(self.style.SUCCESS("Harmonization & baseline generation complete."))
