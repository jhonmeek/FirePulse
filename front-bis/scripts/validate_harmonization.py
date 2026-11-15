"""FirePulse — protocole de validation renforcé de l'harmonisation MODIS → VIIRS.

Ce script ne modifie aucune donnée. Il relit les 48 CSV FIRMS du Gabon et produit
un artefact JSON reproductible pour la preuve scientifique :

1. masque statique 0,05° **gelé sur 2000–2017** (avant calibration et test) ;
2. split en trois temps : train 2012-02 → 2017-12, calibration 2018-01 → 2019-12,
   test 2020-01 → 2025-12 ;
3. comparaison de modèles : naïf, ratio global, ratio saisonnier, OLS,
   power-law log1p, baseline saisonnière ;
4. métriques sur les comptages bruts **et sur les anomalies** (le R² brut est gonflé
   par la saisonnalité) ;
5. intervalle conforme 80 % calibré sur 2018–2019, couverture mesurée sur 2020–2025 ;
6. validation sur un capteur tenu à l'écart : NOAA-20 (ratio calibré sur 2018–2019) ;
7. transfert de plateforme : modèle Terra → S-NPP appliqué à Aqua ;
8. sensibilité du masque (10/24, 20/48, 30/72) et delta « masque gelé vs all-years ».

Usage (depuis la racine du dépôt) :
    python front-bis/scripts/validate_harmonization.py

Sortie :
    front-bis/src/data/validation.json
    front-bis/src/data/validation_series.csv

Dépendances : bibliothèque standard uniquement (Python 3.10+).
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw" / "gabon"
DEFAULT_OUT = ROOT / "front-bis" / "src" / "data" / "validation.json"
DEFAULT_SERIES = ROOT / "front-bis" / "src" / "data" / "validation_series.csv"

GRID_DEG = 0.05
GRID_SCALE = 20

TRAIN = ("2012-02", "2017-12")
CALIBRATION = ("2018-01", "2019-12")
TEST = ("2020-01", "2025-12")
MASK_MAX_YEAR = 2017
ALL_MAX_YEAR = 2025

SENSOR_FILES = (
    ("modis", "modis"),
    ("viirs-snpp", "snpp"),
    ("viirs-jpss1", "noaa20"),
)


# --------------------------------------------------------------------- utils


def month_range(start: str, end: str) -> list[str]:
    start_year, start_month = (int(part) for part in start.split("-"))
    end_year, end_month = (int(part) for part in end.split("-"))
    months: list[str] = []
    year, month = start_year, start_month
    while (year, month) <= (end_year, end_month):
        months.append(f"{year:04d}-{month:02d}")
        month += 1
        if month > 12:
            month = 1
            year += 1
    return months


def month_of_year(month: str) -> int:
    return int(month[5:7])


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def variance(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mu = mean(values)
    return sum((value - mu) ** 2 for value in values) / len(values)


def covariance(xs: list[float], ys: list[float]) -> float:
    if len(xs) < 2 or len(xs) != len(ys):
        return 0.0
    mx, my = mean(xs), mean(ys)
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / len(xs)


def quantile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * q
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def split_conformal_quantile(values: list[float], coverage: float) -> float:
    """Finite-sample order statistic; no time-series coverage guarantee is implied."""
    if not values or not 0 < coverage < 1 or any(not math.isfinite(v) or v < 0 for v in values):
        raise ValueError("Expected nonempty finite nonnegative scores and coverage between 0 and 1")
    rank = math.ceil((len(values) + 1) * coverage)
    if rank > len(values):
        raise ValueError("Not enough calibration scores for requested nominal coverage")
    return sorted(values)[rank - 1]


def metrics(observed: list[float], predicted: list[float]) -> dict:
    if not observed:
        return {"n": 0, "mae": None, "rmse": None, "bias": None, "r2": None}
    errors = [pred - obs for obs, pred in zip(observed, predicted)]
    ss_res = sum((obs - pred) ** 2 for obs, pred in zip(observed, predicted))
    mu = mean(observed)
    ss_tot = sum((obs - mu) ** 2 for obs in observed)
    return {
        "n": len(observed),
        "mae": sum(abs(error) for error in errors) / len(errors),
        "rmse": math.sqrt(ss_res / len(observed)),
        "bias": mean(errors),
        "r2": 1 - ss_res / ss_tot if ss_tot > 0 else None,
    }


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# --------------------------------------------------------------------- data


def load_observations() -> tuple[list[tuple], list[dict]]:
    """Retourne (observations, inputs). Observation = (mois, année, capteur, type, cellule)."""
    # La présence d'un fichier annuel ne prouve pas la couverture mensuelle.
    # Un fichier manquant ne doit cependant jamais être converti en zéros.
    expected = {
        *(f"modis_{year}_Gabon.csv" for year in range(2000, 2026)),
        *(f"viirs-snpp_{year}_Gabon.csv" for year in range(2012, 2026)),
        *(f"viirs-jpss1_{year}_Gabon.csv" for year in range(2018, 2026)),
    }
    actual = {path.name for prefix, _ in SENSOR_FILES for path in RAW.glob(f"{prefix}_*_Gabon.csv")}
    if actual != expected:
        raise ValueError(f"FIRMS input files mismatch: missing={sorted(expected - actual)}, unexpected={sorted(actual - expected)}")
    observations: list[tuple] = []
    inputs: list[dict] = []
    for prefix, source in SENSOR_FILES:
        for path in sorted(RAW.glob(f"{prefix}_*_Gabon.csv")):
            inputs.append(
                {
                    "file": path.name,
                    "sha256": sha256(path),
                    "source": source,
                }
            )
            with path.open(encoding="utf-8", newline="") as stream:
                reader = csv.DictReader(stream)
                required = {"latitude", "longitude", "type", "acq_date", "satellite"}
                if not reader.fieldnames or not required.issubset(reader.fieldnames):
                    raise ValueError(f"Missing required columns: {path.name}")
                for row in reader:
                    try:
                        lat = float(row["latitude"])
                        lon = float(row["longitude"])
                        hotspot_type = int(row["type"])
                    except (KeyError, TypeError, ValueError) as exc:
                        raise ValueError(f"Invalid required fields: {path.name}, line {reader.line_num}") from exc
                    try:
                        acquired = datetime.strptime(row.get("acq_date") or "", "%Y-%m-%d")
                    except ValueError as exc:
                        raise ValueError(f"Invalid date: {path.name}, line {reader.line_num}") from exc
                    if acquired.year != int(path.name.split("_")[1]):
                        raise ValueError(f"Date outside file year: {path.name}, line {reader.line_num}")
                    month = acquired.strftime("%Y-%m")
                    satellite = row.get("satellite") or ""
                    if source == "modis":
                        if satellite not in ("Terra", "Aqua"):
                            raise ValueError(f"Unknown MODIS satellite: {path.name}, line {reader.line_num}")
                        sensor = "terra" if satellite == "Terra" else "aqua"
                    elif source == "snpp":
                        sensor = "snpp"
                    else:
                        sensor = "noaa20"
                    cell = (math.floor(lat * GRID_SCALE), math.floor(lon * GRID_SCALE))
                    observations.append((month, int(month[:4]), sensor, hotspot_type, cell))
    return observations, inputs


def build_mask(
    observations: list[tuple],
    max_year: int,
    type23_min: int = 20,
    snpp_months_min: int = 48,
) -> set[tuple[int, int]]:
    """Masque 0,05° construit uniquement sur les années <= max_year."""
    type23 = defaultdict(int)
    snpp_months: dict[tuple[int, int], set[str]] = defaultdict(set)
    for month, year, sensor, hotspot_type, cell in observations:
        if year > max_year:
            continue
        if hotspot_type in (2, 3):
            type23[cell] += 1
        if sensor == "snpp":
            snpp_months[cell].add(month)
    cells = set(type23) | set(snpp_months)
    return {
        cell
        for cell in cells
        if type23[cell] >= type23_min or len(snpp_months[cell]) >= snpp_months_min
    }


def aggregate_monthly(
    observations: list[tuple],
    mask: set[tuple[int, int]],
    start: str = "2012-02",
    end: str = "2025-12",
) -> dict[str, dict[str, int]]:
    """Comptages mensuels type 0 hors masque, par capteur."""
    months = {
        month: {"terra": 0, "aqua": 0, "snpp": 0, "noaa20": 0}
        for month in month_range(start, end)
    }
    for month, _year, sensor, hotspot_type, cell in observations:
        if month < start or month > end:
            continue
        if hotspot_type != 0 or cell in mask:
            continue
        row = months.get(month)
        if row is None:
            continue
        row[sensor] += 1
    for row in months.values():
        row["modis"] = row["terra"] + row["aqua"]
    return months


def month_rows(months: dict[str, dict[str, int]], ordered: list[str]) -> list[dict]:
    rows = []
    for month in ordered:
        row = months.get(month, {"terra": 0, "aqua": 0, "snpp": 0, "noaa20": 0, "modis": 0})
        rows.append(
            {
                "month": month,
                "modis": row["modis"],
                "terra": row["terra"],
                "aqua": row["aqua"],
                "snpp": row["snpp"],
                "noaa20": row["noaa20"],
            }
        )
    return rows


# --------------------------------------------------------------------- models


def fit_power_law(xs: list[float], ys: list[float]) -> tuple[float, float]:
    us = [math.log1p(x) for x in xs]
    vs = [math.log1p(y) for y in ys]
    denominator = variance(us)
    p = covariance(us, vs) / denominator if denominator else 0.0
    q = mean(vs) - p * mean(us)
    return p, q


def predict_power_law(x: float, p: float, q: float) -> float:
    return max(0.0, math.expm1(p * math.log1p(max(0.0, x)) + q))


def fit_ols(xs: list[float], ys: list[float]) -> tuple[float, float]:
    denominator = variance(xs)
    slope = covariance(xs, ys) / denominator if denominator else 0.0
    intercept = mean(ys) - slope * mean(xs)
    return slope, intercept


def fit_seasonal_ratio(
    xs: list[float],
    ys: list[float],
    months: list[str],
) -> dict[int, float]:
    global_ratio = sum(ys) / sum(xs) if sum(xs) else 0.0
    by_month: dict[int, tuple[float, float]] = defaultdict(lambda: (0.0, 0.0))
    for x, y, month in zip(xs, ys, months):
        sx, sy = by_month[month_of_year(month)]
        by_month[month_of_year(month)] = (sx + x, sy + y)
    return {
        month: (sy / sx if sx else global_ratio)
        for month, (sx, sy) in by_month.items()
    }


def fit_seasonal_baseline(ys: list[float], months: list[str]) -> dict[int, float]:
    buckets: dict[int, list[float]] = defaultdict(list)
    for y, month in zip(ys, months):
        buckets[month_of_year(month)].append(y)
    return {month: statistics.median(values) for month, values in buckets.items()}


def predict_seasonal_ratio(xs: list[float], months: list[str], ratios: dict[int, float]) -> list[float]:
    return [x * ratios.get(month_of_year(month), 0.0) for x, month in zip(xs, months)]


def predict_seasonal_baseline(months: list[str], baselines: dict[int, float]) -> list[float]:
    return [baselines.get(month_of_year(month), 0.0) for month in months]


def anomaly_metrics(
    observed: list[float],
    predicted: list[float],
    months: list[str],
    baseline: dict[int, float],
) -> dict:
    observed_anomaly = [obs - baseline.get(month_of_year(month), 0.0) for obs, month in zip(observed, months)]
    predicted_anomaly = [pred - baseline.get(month_of_year(month), 0.0) for pred, month in zip(predicted, months)]
    return metrics(observed_anomaly, predicted_anomaly)


def require_recorded_months(observations: list[tuple], months: list[str]) -> set[tuple[str, str]]:
    """Reject missing sensor-months; observed detections still do not prove complete coverage."""
    present = {(month, sensor) for month, _year, sensor, _kind, _cell in observations}
    missing = [(month, sensor) for month in months for sensor in ("terra", "aqua", "snpp") if (month, sensor) not in present]
    if missing:
        raise ValueError(f"No detections recorded for sensor-months; cannot distinguish a true zero from missing coverage: {missing}")
    return present


# --------------------------------------------------------------------- validation


def validate() -> dict:
    observations, inputs = load_observations()
    ordered = month_range("2012-02", "2025-12")
    train_months = month_range(*TRAIN)
    calibration_months = month_range(*CALIBRATION)
    test_months = month_range(*TEST)

    present = require_recorded_months(observations, ordered)

    frozen_mask = build_mask(observations, MASK_MAX_YEAR)
    all_mask = build_mask(observations, ALL_MAX_YEAR)
    later_cells = all_mask - frozen_mask
    test_observations = [item for item in observations if TEST[0] <= item[0] <= TEST[1]]
    residual_mask_diagnostics = {
        "test_type23_outside_frozen_mask": sum(1 for _, _, _, kind, cell in test_observations if kind in (2, 3) and cell not in frozen_mask),
        "test_type0_in_later_mask_cells": sum(1 for _, _, _, kind, cell in test_observations if kind == 0 and cell in later_cells),
        "note": "Retrospective descriptive counts, not confirmed industrial sources or causal contamination.",
    }
    for label, sensors in (("all", {"terra", "aqua", "snpp", "noaa20"}), ("snpp", {"snpp"})):
        type0 = [item for item in test_observations if item[2] in sensors and item[3] == 0]
        affected = sum(1 for item in type0 if item[4] in later_cells)
        residual_mask_diagnostics[f"{label}_type0_total"] = len(type0)
        residual_mask_diagnostics[f"{label}_type0_in_later_mask_cells"] = affected
        residual_mask_diagnostics[f"{label}_type0_fraction_in_later_mask_cells"] = affected / len(type0) if type0 else None
    all_months = aggregate_monthly(observations, frozen_mask)
    rows = month_rows(all_months, ordered)
    by_month = {row["month"]: row for row in rows}
    for row in rows:
        if (row["month"], "noaa20") not in present:
            row["noaa20"] = None

    train_rows = [by_month[month] for month in train_months]
    calibration_rows = [by_month[month] for month in calibration_months]
    test_rows = [by_month[month] for month in test_months]

    x_train = [row["modis"] for row in train_rows]
    y_train = [row["snpp"] for row in train_rows]
    x_cal = [row["modis"] for row in calibration_rows]
    y_cal = [row["snpp"] for row in calibration_rows]
    x_test = [row["modis"] for row in test_rows]
    y_test = [row["snpp"] for row in test_rows]

    # Baselines saisonnières apprises sur le train uniquement.
    seasonal_baseline = fit_seasonal_baseline(y_train, train_months)
    seasonal_ratio = fit_seasonal_ratio(x_train, y_train, train_months)
    global_ratio = sum(y_train) / sum(x_train) if sum(x_train) else 0.0
    slope, intercept = fit_ols(x_train, y_train)
    p, q = fit_power_law(x_train, y_train)

    predictions = {
        "naive": {
            "test": x_test,
            "calibration": x_cal,
        },
        "global_ratio": {
            "test": [x * global_ratio for x in x_test],
            "calibration": [x * global_ratio for x in x_cal],
        },
        "seasonal_ratio": {
            "test": predict_seasonal_ratio(x_test, test_months, seasonal_ratio),
            "calibration": predict_seasonal_ratio(x_cal, calibration_months, seasonal_ratio),
        },
        "ols_linear": {
            "test": [max(0.0, slope * x + intercept) for x in x_test],
            "calibration": [max(0.0, slope * x + intercept) for x in x_cal],
        },
        "power_law_log1p": {
            "test": [predict_power_law(x, p, q) for x in x_test],
            "calibration": [predict_power_law(x, p, q) for x in x_cal],
        },
        "seasonal_baseline": {
            "test": predict_seasonal_baseline(test_months, seasonal_baseline),
            "calibration": predict_seasonal_baseline(calibration_months, seasonal_baseline),
        },
    }

    model_results = {}
    for name, prediction in predictions.items():
        model_results[name] = {
            "raw": metrics(y_test, prediction["test"]),
            "anomaly": anomaly_metrics(y_test, prediction["test"], test_months, seasonal_baseline),
        }

    # Intervalle conforme : quantiles appris sur 2018–2019, couverture mesurée sur 2020–2025.
    power_cal = predictions["power_law_log1p"]["calibration"]
    power_test = predictions["power_law_log1p"]["test"]
    log_residuals_cal = [
        math.log1p(y) - math.log1p(pred) for y, pred in zip(y_cal, power_cal)
    ]
    log_residuals_test = [
        math.log1p(y) - math.log1p(pred) for y, pred in zip(y_test, power_test)
    ]
    q80 = split_conformal_quantile([abs(value) for value in log_residuals_cal], 0.80)
    q90 = split_conformal_quantile([abs(value) for value in log_residuals_cal], 0.90)
    q80_test = quantile([abs(value) for value in log_residuals_test], 0.80)

    def coverage(ys: list[float], predictions_: list[float], quantile_value: float) -> float:
        covered = 0
        for y, pred in zip(ys, predictions_):
            low = max(0.0, math.expm1(math.log1p(max(0.0, pred)) - quantile_value))
            high = math.expm1(math.log1p(max(0.0, pred)) + quantile_value)
            if low <= y <= high:
                covered += 1
        return covered / len(ys) if ys else 0.0

    conformal = {
        "nominal": 0.80,
        "q80_calibration": q80,
        "coverage_test_q80_calibration": coverage(y_test, power_test, q80),
        "q90_calibration": q90,
        "coverage_test_q90_calibration": coverage(y_test, power_test, q90),
        "q80_test_leaky": q80_test,
        "coverage_test_q80_leaky": coverage(y_test, power_test, q80_test),
        "note": (
            "Le quantile q80 est appris sur 2018–2019 puis appliqué à 2020–2025. "
            "La couverture q80_test_leaky est donnée uniquement pour comparaison : "
            "elle est tautologique et ne doit pas être présentée comme une validation. "
            "Le rang fini-échantillon ne garantit pas la couverture en séries temporelles ; "
            "la couverture des observations est inconnue."
        ),
    }

    # Capteur tenu à l'écart : NOAA-20. Ratio calibré sur 2018–2019, test sur 2020–2025.
    noaa20_calibration = [
        (row["snpp"], row["noaa20"])
        for row in calibration_rows
        if row["noaa20"] is not None and row["snpp"] > 0
    ]
    noaa20_ratio = (
        sum(observed for _, observed in noaa20_calibration)
        / sum(snpp for snpp, _ in noaa20_calibration)
        if noaa20_calibration
        else None
    )
    noaa20_test_rows = [row for row in test_rows if row["noaa20"] is not None]
    noaa20_observed = [row["noaa20"] for row in noaa20_test_rows]
    noaa20_predicted = (
        [predict_power_law(row["modis"], p, q) * noaa20_ratio for row in noaa20_test_rows]
        if noaa20_ratio is not None else []
    )
    noaa20_months = [row["month"] for row in noaa20_test_rows]
    noaa20_baseline = {
        month: value * noaa20_ratio for month, value in seasonal_baseline.items()
    } if noaa20_ratio is not None else {}
    held_out_noaa20 = {
        "role": "capteur tenu à l'écart (non utilisé pour entraîner le power-law)",
        "ratio_noaa20_to_snpp_calibration": noaa20_ratio,
        "calibration_months": len(noaa20_calibration),
        "raw": metrics(noaa20_observed, noaa20_predicted) if noaa20_ratio is not None else None,
        "anomaly": (
            anomaly_metrics(noaa20_observed, noaa20_predicted, noaa20_months, noaa20_baseline)
            if noaa20_ratio is not None else None
        ),
        "limitation": (
            "Ratio indisponible : aucun mois de calibration avec S-NPP positif."
            if noaa20_ratio is None else
            "Ratio estimé sur la calibration ; la couverture mensuelle des observations est inconnue."
        ),
    }

    # Transfert de plateforme : modèle Terra → S-NPP appliqué à Aqua.
    terra_train = [(row["terra"], row["snpp"]) for row in train_rows if row["terra"] > 0]
    terra_p, terra_q = fit_power_law(
        [x for x, _ in terra_train], [y for _, y in terra_train]
    )
    aqua_test_rows = [row for row in test_rows if row["aqua"] > 0]
    aqua_observed = [row["snpp"] for row in aqua_test_rows]
    aqua_predicted = [
        predict_power_law(row["aqua"], terra_p, terra_q) for row in aqua_test_rows
    ]
    aqua_months = [row["month"] for row in aqua_test_rows]
    held_out_terra_aqua = {
        "role": "transfert de plateforme : modèle appris sur Terra, appliqué à Aqua",
        "raw": metrics(aqua_observed, aqua_predicted),
        "anomaly": anomaly_metrics(
            aqua_observed, aqua_predicted, aqua_months, seasonal_baseline
        ),
    }

    # Métriques par saison pour le modèle retenu.
    high_season = [6, 7, 8, 9, 10]
    groups = {
        "haute_saison_juin_octobre": [
            (index, row)
            for index, row in enumerate(test_rows)
            if month_of_year(row["month"]) in high_season
        ],
        "basse_saison_nov_mai": [
            (index, row)
            for index, row in enumerate(test_rows)
            if month_of_year(row["month"]) not in high_season
        ],
    }
    by_season = {}
    for label, entries in groups.items():
        ys = [y_test[index] for index, _row in entries]
        preds = [power_test[index] for index, _row in entries]
        months = [row["month"] for _index, row in entries]
        by_season[label] = {
            "raw": metrics(ys, preds),
            "anomaly": anomaly_metrics(ys, preds, months, seasonal_baseline),
        }

    # Delta masque gelé vs masque all-years.
    all_mask_months = aggregate_monthly(observations, all_mask)
    all_rows = month_rows(all_mask_months, ordered)
    all_by_month = {row["month"]: row for row in all_rows}
    all_train = [all_by_month[month] for month in train_months]
    all_test = [all_by_month[month] for month in test_months]
    all_p, all_q = fit_power_law(
        [row["modis"] for row in all_train], [row["snpp"] for row in all_train]
    )
    all_power_test = [
        predict_power_law(row["modis"], all_p, all_q) for row in all_test
    ]
    mask_freeze_delta = {
        "frozen_on": f"2000–{MASK_MAX_YEAR}",
        "all_years": "2000–2025",
        "cells_frozen": len(frozen_mask),
        "cells_all": len(all_mask),
        "delta_cells": len(all_mask) - len(frozen_mask),
        "frozen_power_law": metrics(y_test, power_test),
        "all_years_power_law": metrics(
            [row["snpp"] for row in all_test], all_power_test
        ),
        "note": (
            "Le masque all-years utilise des observations de calibration et de test : "
            "cette comparaison est une expérience rétrospective avec fuite temporelle, "
            "pas une estimation indépendante de performance."
        ),
    }

    # Sensibilité du masque gelé.
    sensitivity = {}
    for label, (type23_min, snpp_min) in {
        "permissif_10_24": (10, 24),
        "reference_20_48": (20, 48),
        "strict_30_72": (30, 72),
    }.items():
        mask = build_mask(observations, MASK_MAX_YEAR, type23_min, snpp_min)
        counts = aggregate_monthly(observations, mask)
        rows_ = month_rows(counts, ordered)
        rows_by_month = {row["month"]: row for row in rows_}
        train_ = [rows_by_month[month] for month in train_months]
        test_ = [rows_by_month[month] for month in test_months]
        px, pq = fit_power_law(
            [row["modis"] for row in train_], [row["snpp"] for row in train_]
        )
        preds = [predict_power_law(row["modis"], px, pq) for row in test_]
        local_baseline = fit_seasonal_baseline([row["snpp"] for row in train_], train_months)
        sensitivity[label] = {
            "type23_min": type23_min,
            "snpp_months_min": snpp_min,
            "cells": len(mask),
            "raw": metrics([row["snpp"] for row in test_], preds),
            "anomaly": anomaly_metrics(
                [row["snpp"] for row in test_],
                preds,
                [row["month"] for row in test_],
                local_baseline,
            ),
        }

    test_series = []
    for row, pred, pred_seasonal, pred_ratio in zip(
        test_rows,
        power_test,
        predictions["seasonal_baseline"]["test"],
        predictions["seasonal_ratio"]["test"],
    ):
        test_series.append(
            {
                "month": row["month"],
                "observed": row["snpp"],
                "power_law": round(pred, 3),
                "seasonal_baseline": round(pred_seasonal, 3),
                "seasonal_ratio": round(pred_ratio, 3),
                "noaa20_observed": row["noaa20"],
            }
        )

    result = {
        "schema_version": 2,
        "artifact_kind": "firepulse-harmonization-validation",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "raw_dir": "data/raw/gabon",
            "scope": "48 CSV pays Gabon, 2000–2025 ; géométrie non rejoint, comme M1",
            "inputs": inputs,
        },
        "split": {
            "train": list(TRAIN),
            "calibration": list(CALIBRATION),
            "test": list(TEST),
            "n_train": len(train_months),
            "n_calibration": len(calibration_months),
            "n_test": len(test_months),
        },
        "mask": {
            "grid_deg": GRID_DEG,
            "frozen_on": f"2000–{MASK_MAX_YEAR}",
            "type23_min": 20,
            "snpp_months_min": 48,
            "cells_frozen": len(frozen_mask),
            "cells_all_years": len(all_mask),
        },
        "params": {
            "global_ratio": global_ratio,
            "ols_slope": slope,
            "ols_intercept": intercept,
            "power_law_p": p,
            "power_law_q": q,
            "terra_to_snpp_p": terra_p,
            "terra_to_snpp_q": terra_q,
            "noaa20_to_snpp_ratio": noaa20_ratio,
        },
        "models": model_results,
        "conformal": conformal,
        "held_out": {
            "noaa20": held_out_noaa20,
            "terra_to_aqua": held_out_terra_aqua,
        },
        "by_season": by_season,
        "mask_freeze_delta": mask_freeze_delta,
        "residual_mask_diagnostics": residual_mask_diagnostics,
        "sensitivity": sensitivity,
        "test_series": test_series,
        "experiments": [
            "La comparaison du masque toutes années est rétrospective et utilise les données de test.",
            "Les comparaisons de modèles, saisons et seuils sur le même test sont exploratoires.",
            "Le transfert Terra vers Aqua est une expérience de plateforme ; NOAA-20 utilise un ratio calibré.",
        ],
        "limitations": [
            "La couverture mensuelle des observations est inconnue : une détection enregistrée ne garantit pas une couverture complète. Les mois MODIS/S-NPP sans détection interrompent le calcul ; NOAA-20 absent est indisponible.",
            "La couverture conforme en séries temporelles n'est pas garantie ; la couverture mesurée dépend du jeu de test.",
            "Une sélection fondée sur ces expériences nécessite une nouvelle évaluation indépendante.",
        ],
        "notes": [
            "Les comptages mesurent des détections thermiques, pas des incendies distincts.",
            "Le cycle saisonnier peut gonfler le R² brut ; les métriques d'anomalie sont complémentaires.",
            "Le masque est gelé sur 2000–2017 ; 2018–2019 sert à la calibration, 2020–2025 au test.",
            "L'intervalle conforme est calibré sur 2018–2019 ; la couverture est mesurée sur 2020–2025.",
            "NOAA-20 est un capteur tenu à l'écart : le ratio est calibré sur 2018–2019, pas sur le test.",
            "Le transfert Terra → Aqua teste la robustesse inter-plateformes, pas un nouveau capteur.",
            "Le pont NOAA-20 post-2026 reste une projection, pas une validation.",
            "La présence des fichiers et de détections ne prouve pas une couverture mensuelle complète ; un zéro après filtrage reste distinct d'une absence de fichier ou d'observation.",
            "Les comparaisons entre modèles, saisons et seuils sur le même test sont exploratoires ; elles ne constituent pas une évaluation indépendante après sélection.",
        ],
    }
    return result


def write_series(result: dict, path: Path) -> None:
    """Écrit la série de test et les prédictions pour le frontend."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=[
                "month",
                "observed",
                "power_law",
                "seasonal_baseline",
                "seasonal_ratio",
                "noaa20_observed",
            ],
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(result["test_series"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--series", type=Path, default=DEFAULT_SERIES)
    args = parser.parse_args(argv)

    result = validate()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    write_series(result, args.series)

    print(json.dumps({
        "split": result["split"],
        "mask": result["mask"],
        "power_law": result["models"]["power_law_log1p"],
        "seasonal_ratio": result["models"]["seasonal_ratio"],
        "conformal": result["conformal"],
        "held_out_noaa20": result["held_out"]["noaa20"]["raw"],
        "held_out_terra_aqua": result["held_out"]["terra_to_aqua"]["raw"],
        "mask_freeze_delta": result["mask_freeze_delta"],
    }, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
