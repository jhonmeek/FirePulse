"""MVP fire-risk climatology for FirePulse.

Target
------
For every forest 0.25-degree cell and calendar month, estimate the probability
of at least one ``type 0`` detection outside candidate persistent cells.

Method
------
- Build a complete cell-month panel (zeros included) for 2012-02..2025-12.
- Smooth the monthly occurrence frequency with a Beta(1, 4) prior.
- Validate on 2020-2025 using a climatology learned on 2012-2019.
- Project 2026-2035 with a conservative province-level trend factor.

Outputs
-------
- data/processed/prediction/prediction_cells.csv
- data/processed/prediction/prediction_monthly.csv
- data/processed/prediction/prediction_annual.csv
- data/processed/prediction/prediction_provinces.csv
- data/processed/prediction/prediction_metrics.json
- data/processed/prediction/prediction_manifest.json
- front-bis/src/data/prediction.json (compact frontend artifact)
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    log_loss,
    roc_auc_score,
)

GRID_DEG = 0.25
FOREST_THRESHOLD = 0.30
START_MONTH = "2012-02"
END_MONTH = "2025-12"
TRAIN_END = "2019-12"
TEST_START = "2020-01"
FUTURE_YEARS = list(range(2026, 2036))
ALPHA = 1.0
BETA = 4.0
TREND_SHRINK = 0.5
TREND_CLIP = (0.75, 1.25)
JANUARY_FIRST_YEAR = 2013  # S-NPP starts on 2012-01-20; January 2012 is partial.


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_cells(path: Path) -> pd.DataFrame:
    cells = pd.read_csv(path, dtype={"cell_id": str, "province_code": str})
    cells["lat0"] = cells["lat0"].round(2)
    cells["lon0"] = cells["lon0"].round(2)
    cells["province_name"] = cells["province_name"].astype(str).str.strip()
    cells = cells[cells["is_forest"].astype(str).str.lower().isin({"true", "1"})].copy()
    return cells.reset_index(drop=True)


def build_panel(cells: pd.DataFrame, grid_csv: Path) -> pd.DataFrame:
    raw = pd.read_csv(
        grid_csv,
        usecols=["month", "lat0", "lon0", "count_type0_unmasked"],
        dtype={"month": str},
    )
    raw = raw[(raw["month"] >= START_MONTH) & (raw["month"] <= END_MONTH)].copy()
    raw["lat0"] = raw["lat0"].round(2)
    raw["lon0"] = raw["lon0"].round(2)
    grouped = (
        raw.groupby(["month", "lat0", "lon0"], as_index=False)["count_type0_unmasked"]
        .sum()
        .rename(columns={"count_type0_unmasked": "count"})
    )
    months = pd.DataFrame({"month": sorted(grouped["month"].unique())})
    panel = months.assign(_key=1).merge(
        cells[["cell_id", "lat0", "lon0", "province_code", "province_name", "forest_fraction"]].assign(_key=1),
        on="_key",
    ).drop(columns="_key")
    panel = panel.merge(grouped, on=["month", "lat0", "lon0"], how="left")
    panel["count"] = panel["count"].fillna(0).astype(int)
    panel["positive"] = (panel["count"] > 0).astype(int)
    panel["year"] = panel["month"].str[:4].astype(int)
    panel["month_num"] = panel["month"].str[5:7].astype(int)
    return panel


def smoothed_probability(positives: int, years: int) -> float:
    return (positives + ALPHA) / (years + ALPHA + BETA)


def climatology_table(panel: pd.DataFrame, end_month: str) -> pd.DataFrame:
    data = panel[panel["month"] <= end_month]
    rows = []
    for month_num in range(1, 13):
        subset = data[data["month_num"] == month_num]
        if month_num == 1:
            subset = subset[subset["year"] >= JANUARY_FIRST_YEAR]
        grouped = subset.groupby("cell_id")["positive"].agg(["sum", "count"])
        for cell_id, row in grouped.iterrows():
            years = int(row["count"])
            positives = int(row["sum"])
            rows.append(
                {
                    "cell_id": cell_id,
                    "month_num": month_num,
                    "years": years,
                    "positives": positives,
                    "probability": smoothed_probability(positives, years),
                }
            )
    return pd.DataFrame(rows)


def trend_factors(panel: pd.DataFrame) -> pd.DataFrame:
    """Conservative province-level trend on annual fire-month counts."""
    annual = (
        panel.groupby(["province_code", "year"], as_index=False)["positive"]
        .sum()
        .rename(columns={"positive": "fire_months"})
    )
    rows = []
    for province, group in annual.groupby("province_code"):
        group = group.sort_values("year")
        x = group["year"].to_numpy(dtype=float)
        y = group["fire_months"].to_numpy(dtype=float)
        if len(group) < 4 or y.mean() == 0:
            slope = 0.0
            intercept = y.mean()
        else:
            slope, intercept = np.polyfit(x, y, 1)
        mean_y = y.mean()
        for year in FUTURE_YEARS:
            predicted = intercept + slope * year
            raw_factor = predicted / mean_y if mean_y > 0 else 1.0
            factor = 1.0 + TREND_SHRINK * (raw_factor - 1.0)
            factor = float(np.clip(factor, *TREND_CLIP))
            rows.append(
                {
                    "province_code": province,
                    "year": year,
                    "trend_factor": round(factor, 4),
                    "trend_slope": round(float(slope), 4),
                    "trend_mean_fire_months": round(float(mean_y), 3),
                }
            )
    return pd.DataFrame(rows)


def monthly_predictions(
    cells: pd.DataFrame, climatology: pd.DataFrame, trends: pd.DataFrame
) -> pd.DataFrame:
    rows = []
    for year in FUTURE_YEARS:
        for _, cell in cells.iterrows():
            province = cell["province_code"]
            trend = trends[(trends["province_code"] == province) & (trends["year"] == year)]
            factor = float(trend["trend_factor"].iloc[0]) if len(trend) else 1.0
            for month_num in range(1, 13):
                base = climatology[
                    (climatology["cell_id"] == cell["cell_id"])
                    & (climatology["month_num"] == month_num)
                ]
                p = float(base["probability"].iloc[0]) if len(base) else 0.0
                positives = int(base["positives"].iloc[0]) if len(base) else 0
                years = int(base["years"].iloc[0]) if len(base) else 0
                p = float(np.clip(p * factor, 0.001, 0.999))
                rows.append(
                    {
                        "cell_id": cell["cell_id"],
                        "lat0": cell["lat0"],
                        "lon0": cell["lon0"],
                        "province_code": province,
                        "province_name": cell["province_name"],
                        "year": year,
                        "month_num": month_num,
                        "probability": round(p, 6),
                        "base_probability": round(float(base["probability"].iloc[0]) if len(base) else 0.0, 6),
                        "positive_years": positives,
                        "observed_years": years,
                        "trend_factor": factor,
                    }
                )
    return pd.DataFrame(rows)


def annual_predictions(monthly: pd.DataFrame) -> pd.DataFrame:
    grouped = monthly.groupby(["cell_id", "year"], as_index=False)
    rows = []
    for (cell_id, year), group in grouped:
        p = group["probability"].to_numpy(dtype=float)
        annual = 1.0 - np.prod(1.0 - p)
        rows.append(
            {
                "cell_id": cell_id,
                "year": int(year),
                "annual_probability": round(float(annual), 6),
                "expected_fire_months": round(float(p.sum()), 3),
                "peak_month": int(group.loc[group["probability"].idxmax(), "month_num"]),
                "peak_probability": round(float(p.max()), 6),
            }
        )
    return pd.DataFrame(rows)


def province_predictions(
    monthly: pd.DataFrame, annual: pd.DataFrame
) -> pd.DataFrame:
    monthly_agg = (
        monthly.groupby(["province_code", "province_name", "year", "month_num"], as_index=False)
        .agg(
            mean_probability=("probability", "mean"),
            median_probability=("probability", "median"),
            high_risk_share=("probability", lambda s: float((s >= 0.5).mean())),
            expected_fire_cells_month=("probability", "sum"),
            cells=("probability", "size"),
        )
    )
    annual_agg = (
        annual.merge(
            monthly[["cell_id", "province_code"]].drop_duplicates(),
            on="cell_id",
            how="left",
        )
        .groupby(["province_code", "year"], as_index=False)
        .agg(
            mean_annual_probability=("annual_probability", "mean"),
            high_annual_risk_share=("annual_probability", lambda s: float((s >= 0.5).mean())),
            expected_fire_cells_year=("annual_probability", "sum"),
            expected_fire_months=("expected_fire_months", "sum"),
            cells_year=("annual_probability", "size"),
        )
    )
    result = monthly_agg.merge(annual_agg, on=["province_code", "year"], how="left")

    national_monthly = (
        monthly.groupby(["year", "month_num"], as_index=False)
        .agg(
            mean_probability=("probability", "mean"),
            median_probability=("probability", "median"),
            high_risk_share=("probability", lambda s: float((s >= 0.5).mean())),
            expected_fire_cells_month=("probability", "sum"),
            cells=("probability", "size"),
        )
        .assign(province_code="GA", province_name="Gabon")
    )
    national_annual = (
        annual.groupby("year", as_index=False)
        .agg(
            mean_annual_probability=("annual_probability", "mean"),
            high_annual_risk_share=("annual_probability", lambda s: float((s >= 0.5).mean())),
            expected_fire_cells_year=("annual_probability", "sum"),
            expected_fire_months=("expected_fire_months", "sum"),
            cells_year=("annual_probability", "size"),
        )
        .assign(province_code="GA")
    )
    national = national_monthly.merge(national_annual, on=["province_code", "year"], how="left")
    return pd.concat([national, result], ignore_index=True)


def calibration_table(y_true: np.ndarray, y_prob: np.ndarray, bins: int = 10) -> list[dict]:
    edges = np.linspace(0.0, 1.0, bins + 1)
    rows = []
    for index in range(bins):
        low, high = float(edges[index]), float(edges[index + 1])
        mask = (y_prob >= low) & (y_prob < high if index < bins - 1 else y_prob <= high)
        if not mask.any():
            continue
        rows.append(
            {
                "bin": f"{low:.1f}-{high:.1f}",
                "n": int(mask.sum()),
                "predicted_mean": round(float(y_prob[mask].mean()), 4),
                "observed_rate": round(float(y_true[mask].mean()), 4),
            }
        )
    return rows


def top_k_capture(y_true: np.ndarray, y_prob: np.ndarray, k: float) -> dict:
    count = max(1, int(round(len(y_prob) * k)))
    order = np.argsort(-y_prob)
    selected = order[:count]
    positives = int(y_true.sum())
    captured = int(y_true[selected].sum())
    return {
        "k": k,
        "selected": count,
        "positives": positives,
        "captured": captured,
        "capture_rate": round(captured / positives, 4) if positives else 0.0,
        "precision": round(captured / count, 4) if count else 0.0,
    }


def metrics_block(y_true: np.ndarray, y_prob: np.ndarray) -> dict:
    y_true = np.asarray(y_true, dtype=int)
    y_prob = np.asarray(y_prob, dtype=float)
    result = {
        "n": int(len(y_true)),
        "positives": int(y_true.sum()),
        "base_rate": round(float(y_true.mean()), 4),
        "brier": round(float(brier_score_loss(y_true, y_prob)), 5),
        "log_loss": round(float(log_loss(y_true, np.clip(y_prob, 1e-6, 1 - 1e-6))), 5),
    }
    if len(np.unique(y_true)) > 1:
        result["roc_auc"] = round(float(roc_auc_score(y_true, y_prob)), 4)
        result["average_precision"] = round(float(average_precision_score(y_true, y_prob)), 4)
    else:
        result["roc_auc"] = None
        result["average_precision"] = None
    result["calibration"] = calibration_table(y_true, y_prob)
    result["top_k"] = [top_k_capture(y_true, y_prob, k) for k in (0.05, 0.1, 0.2)]
    return result


def evaluate(panel: pd.DataFrame) -> dict:
    train_clim = climatology_table(panel, TRAIN_END)
    test = panel[(panel["month"] >= TEST_START) & (panel["month"] <= END_MONTH)].copy()
    test = test.merge(
        train_clim.rename(columns={"probability": "predicted"}),
        on=["cell_id", "month_num"],
        how="left",
    )
    test["predicted"] = test["predicted"].fillna(ALPHA / (ALPHA + BETA))
    monthly = metrics_block(test["positive"].to_numpy(), test["predicted"].to_numpy())

    annual_test = (
        test.groupby(["cell_id", "year"], as_index=False)
        .agg(
            observed=("positive", "max"),
            predicted_annual=("predicted", lambda s: 1.0 - np.prod(1.0 - s.to_numpy(dtype=float))),
        )
    )
    annual = metrics_block(annual_test["observed"].to_numpy(), annual_test["predicted_annual"].to_numpy())

    provinces = {}
    for province, group in test.groupby("province_code"):
        provinces[province] = {
            "monthly": metrics_block(group["positive"].to_numpy(), group["predicted"].to_numpy()),
            "cells": int(group["cell_id"].nunique()),
            "months": int(group["month"].nunique()),
        }
    return {
        "protocol": {
            "train": f"{START_MONTH}..{TRAIN_END}",
            "test": f"{TEST_START}..{END_MONTH}",
            "target": "at least one type-0 detection outside candidate persistent cells",
            "forest_threshold": FOREST_THRESHOLD,
            "smoothing": {"alpha": ALPHA, "beta": BETA},
        },
        "monthly": monthly,
        "annual": annual,
        "provinces": provinces,
    }


def build(cells_path: Path, grid_csv: Path, output_dir: Path, frontend_path: Path) -> dict:
    cells = read_cells(cells_path)
    panel = build_panel(cells, grid_csv)
    metrics = evaluate(panel)

    full_clim = climatology_table(panel, END_MONTH)
    trends = trend_factors(panel)
    monthly = monthly_predictions(cells, full_clim, trends)
    annual = annual_predictions(monthly)
    provinces = province_predictions(monthly, annual)

    output_dir.mkdir(parents=True, exist_ok=True)
    cells_out = cells[
        [
            "cell_id",
            "lat0",
            "lon0",
            "province_code",
            "province_name",
            "forest_fraction",
            "cropland_fraction",
            "builtup_fraction",
        ]
    ].copy()
    cells_out.to_csv(output_dir / "prediction_cells.csv", index=False, lineterminator="\n")
    monthly.to_csv(output_dir / "prediction_monthly.csv", index=False, lineterminator="\n")
    annual.to_csv(output_dir / "prediction_annual.csv", index=False, lineterminator="\n")
    provinces.to_csv(output_dir / "prediction_provinces.csv", index=False, lineterminator="\n")

    metrics_payload = {
        "schema_version": 1,
        "artifact_kind": "firepulse-prediction-metrics",
        "generated_at_utc": pd.Timestamp.now(tz="UTC").isoformat(),
        "model": "smoothed monthly climatology + conservative province trend",
        "cells": int(len(cells)),
        "panel_rows": int(len(panel)),
        "future_years": FUTURE_YEARS,
        "trend": {
            "shrink": TREND_SHRINK,
            "clip": list(TREND_CLIP),
            "method": "linear trend on annual province fire-month counts, extrapolated 2026-2035",
        },
        "metrics": metrics,
    }
    (output_dir / "prediction_metrics.json").write_text(
        json.dumps(metrics_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    manifest = {
        "schema_version": 1,
        "artifact_kind": "firepulse-prediction-climatology",
        "model": metrics_payload["model"],
        "target": metrics["protocol"]["target"],
        "grid_deg": GRID_DEG,
        "forest_threshold": FOREST_THRESHOLD,
        "start_month": START_MONTH,
        "end_month": END_MONTH,
        "train_end": TRAIN_END,
        "test_start": TEST_START,
        "future_years": FUTURE_YEARS,
        "cells": int(len(cells)),
        "monthly_rows": int(len(monthly)),
        "annual_rows": int(len(annual)),
        "cells_sha256": sha256(cells_path),
        "grid_sha256": sha256(grid_csv),
        "monthly_sha256": sha256(output_dir / "prediction_monthly.csv"),
        "annual_sha256": sha256(output_dir / "prediction_annual.csv"),
        "provinces_sha256": sha256(output_dir / "prediction_provinces.csv"),
        "metrics_sha256": sha256(output_dir / "prediction_metrics.json"),
        "notes": [
            "Climatological risk, not a weather forecast.",
            "Forest mask is ESA WorldCover 2021 (static).",
            "Natural ignition cause is not observable in FIRMS; this is a forest-associated proxy.",
            "Absent FIRMS rows are treated as zero detections; observation coverage is not exhaustive.",
        ],
    }
    (output_dir / "prediction_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    write_frontend_artifact(cells, monthly, annual, provinces, metrics, frontend_path)

    return manifest


def write_frontend_artifact(
    cells: pd.DataFrame,
    monthly: pd.DataFrame,
    annual: pd.DataFrame,
    provinces: pd.DataFrame,
    metrics: dict,
    frontend_path: Path,
) -> None:
    cell_index = {cell_id: index for index, cell_id in enumerate(cells["cell_id"])}
    cell_rows = [
        {
            "id": row.cell_id,
            "lat": float(row.lat0),
            "lon": float(row.lon0),
            "province": row.province_code,
            "provinceName": str(row.province_name).strip(),
            "forest": round(float(row.forest_fraction), 4),
            "cropland": round(float(row.cropland_fraction), 4),
            "builtup": round(float(row.builtup_fraction), 4),
        }
        for row in cells.itertuples(index=False)
    ]
    values = {}
    for row in monthly.itertuples(index=False):
        year_key = str(int(row.year))
        values.setdefault(year_key, {})
        values[year_key].setdefault(str(int(row.month_num)), []).append(
            [
                cell_index[row.cell_id],
                round(float(row.probability), 4),
                round(float(row.base_probability), 4),
                int(row.positive_years),
                int(row.observed_years),
            ]
        )
    annual_values = {}
    for row in annual.itertuples(index=False):
        year_key = str(int(row.year))
        annual_values.setdefault(year_key, []).append(
            [
                cell_index[row.cell_id],
                round(float(row.annual_probability), 4),
                round(float(row.expected_fire_months), 2),
                int(row.peak_month),
            ]
        )
    province_rows = []
    for row in provinces.itertuples(index=False):
        province_rows.append(
            {
                "code": row.province_code,
                "name": str(row.province_name).strip(),
                "year": int(row.year),
                "month": int(row.month_num),
                "meanProbability": round(float(row.mean_probability), 4),
                "highRiskShare": round(float(row.high_risk_share), 4),
                "expectedFireCellsMonth": round(float(row.expected_fire_cells_month), 2),
                "meanAnnualProbability": round(float(row.mean_annual_probability), 4),
                "highAnnualRiskShare": round(float(row.high_annual_risk_share), 4),
                "expectedFireCellsYear": round(float(row.expected_fire_cells_year), 2),
                "expectedFireMonths": round(float(row.expected_fire_months), 2),
                "cells": int(row.cells),
            }
        )
    payload = {
        "schemaVersion": 1,
        "artifactKind": "firepulse-prediction-frontend",
        "generatedAt": pd.Timestamp.now(tz="UTC").isoformat(),
        "model": "smoothed monthly climatology + conservative province trend",
        "futureYears": FUTURE_YEARS,
        "forestThreshold": FOREST_THRESHOLD,
        "cells": cell_rows,
        "values": values,
        "annual": annual_values,
        "provinces": province_rows,
        "metrics": metrics,
        "limits": [
            "Probabilité climatologique, pas une prévision météo.",
            "Le type 0 est une classification produit, pas une validation terrain.",
            "Le masque forêt est statique (ESA WorldCover 2021).",
            "L'origine naturelle d'un feu n'est pas observable dans FIRMS.",
            "La couverture satellite n'est pas exhaustive (nuages, fumée, canopée).",
        ],
    }
    frontend_path.parent.mkdir(parents=True, exist_ok=True)
    frontend_path.write_text(
        json.dumps(payload, separators=(",", ":"), ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cells",
        type=Path,
        default=Path("data/processed/prediction/forest_cells.csv"),
    )
    parser.add_argument(
        "--grid",
        type=Path,
        default=Path("data/processed/grid-025/grid_025_monthly.csv"),
    )
    parser.add_argument("--output", type=Path, default=Path("data/processed/prediction"))
    parser.add_argument(
        "--frontend",
        type=Path,
        default=Path("front-bis/src/data/prediction.json"),
    )
    args = parser.parse_args(argv)
    print(json.dumps(build(args.cells, args.grid, args.output, args.frontend), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
