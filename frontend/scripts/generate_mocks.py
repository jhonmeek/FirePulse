"""Génère les mocks frontend (src/mocks/*.json) à partir des CSV FIRMS réels du Gabon.

Usage (depuis frontend/) :  py -3.12 scripts/generate_mocks.py

Réplique hors Docker la chaîne baseline de M2 pour la région nationale `GA` :
- masque statique 0.05° (`import_firms.rebuild_static_mask_and_flag`) ;
- calibration + intervalles conformes + médianes (`build_baseline_series`) ;
- formes de réponse de `backend/apps/api/views.py` (contrat docs/api-contract.json v2.2.0).

Comme le backend (`ST_Within(position, region.geom)`), seules les détections situées dans la
frontière ADM0 comptent pour `GA` (l'offshore est exclu), mais le masque statique est calculé
sur toutes les détections. Écart connu : provinces `GA-1..9` dans /regions mais sans série mock.
Le fichier `calendar_edge_cases.json` est SYNTHÉTIQUE (cas limites UI).
"""

from __future__ import annotations

import json
import math
import statistics
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
from matplotlib.path import Path as GeoPath

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw" / "gabon"
BOUNDARIES = ROOT / "data" / "boundaries"
OUT = Path(__file__).resolve().parents[1] / "src" / "mocks"

# Constantes de build_baseline_series.py
TRAIN = ("2012-02", "2019-12")
TEST = ("2020-01", "2025-12")
TERRA_ONLY_CUTOFF = "2002-07"
SNPP_START, SNPP_END = "2012-02", "2026-10"
SNPP_FIRST_COUNT, N20_FIRST_COUNT = "2012-01", "2018-04"

SENSOR_META = {
    "modis": ("MODIS (Terra + Aqua)", None, ["6.03", "6.2", "61.03"], "Terra-only from 2000-11 to 2002-06; Aqua starts 2002-07."),
    "viirs-noaa20": ("VIIRS NOAA-20 375m", None, ["2"], "Official drop-in continuation after S-NPP retirement."),
    "viirs-snpp": ("VIIRS Suomi-NPP 375m", "2026-11-02", ["2"], "Operational FIRMS delivery ended 2026-11-02 13:00 UTC."),
}
LIMITATIONS = [
    "Hotspot counts measure thermal detections, not distinct individual wildfire events.",
    "MODIS Terra operated without Aqua from 2000-11 through 2002-06; calibrated separately.",
    "Suomi-NPP VIIRS operational FIRMS delivery ended 2026-11-02; NOAA-20 VIIRS provides continuity.",
    "Persistent industrial/oil gas flares (~21-24% of raw VIIRS in Gabon) are filtered when filter_static=true.",
    "NASA FIRMS June 15, 2025 notice: some VIIRS Vxx14IMGML Collection 2 files had type 0/2 differences between versions 1/2 and reprocessed version 3.",
]


# ---------------------------------------------------------------- chargement + masque


def load_observations() -> pd.DataFrame:
    frames = []
    for prefix, source in (("modis", "modis"), ("viirs-snpp", "viirs-snpp"), ("viirs-jpss1", "viirs-noaa20")):
        for f in sorted(RAW.glob(f"{prefix}_*_Gabon.csv")):
            df = pd.read_csv(f, usecols=["latitude", "longitude", "acq_date", "satellite", "type", "frp"])
            df["source"] = source
            frames.append(df)
    obs = pd.concat(frames, ignore_index=True)
    obs["month"] = obs["acq_date"].str.slice(0, 7)
    return obs


def static_cell_stats(obs: pd.DataFrame) -> pd.DataFrame:
    """Statistiques par cellule 0.05° (index = (lat×20, lon×20) entiers) + colonne `flagged`."""
    lat_i = np.floor(obs["latitude"].to_numpy() * 20.0).astype(int)
    lon_i = np.floor(obs["longitude"].to_numpy() * 20.0).astype(int)
    cells = pd.DataFrame({"lat": lat_i, "lon": lon_i, "t23": obs["type"].isin([2, 3]).to_numpy()})
    cells["snpp_month"] = obs["month"].where(obs["source"] == "viirs-snpp").to_numpy()
    g = cells.groupby(["lat", "lon"]).agg(t23=("t23", "sum"), active=("snpp_month", "nunique"))
    g["flagged"] = (g["t23"] >= 20) | (g["active"] >= 48)
    return g


def static_mask(obs: pd.DataFrame) -> tuple[pd.Series, int]:
    """Cellules 0.05° : type∈{2,3} ≥ 20 OU ≥ 48 mois actifs S-NPP. ST_Intersects inclut les bords."""
    lat_i = np.floor(obs["latitude"].to_numpy() * 20.0).astype(int)
    lon_i = np.floor(obs["longitude"].to_numpy() * 20.0).astype(int)
    g = static_cell_stats(obs)
    flagged = set(g[g["flagged"]].index)

    # Un point posé exactement sur un bord touche aussi la cellule voisine (sud / ouest).
    lat_edge = np.isclose(obs["latitude"].to_numpy() * 20.0, lat_i)
    lon_edge = np.isclose(obs["longitude"].to_numpy() * 20.0, lon_i)
    masked = np.zeros(len(obs), dtype=bool)
    for dlat, dlon in ((0, 0), (-1, 0), (0, -1), (-1, -1)):
        applies = np.ones(len(obs), dtype=bool)
        if dlat:
            applies &= lat_edge
        if dlon:
            applies &= lon_edge
        hit = np.fromiter(((a, b) in flagged for a, b in zip(lat_i + dlat, lon_i + dlon)), bool, len(obs))
        masked |= applies & hit
    return pd.Series(masked, index=obs.index), len(flagged)


def within_gabon(obs: pd.DataFrame) -> np.ndarray:
    geom = json.loads((BOUNDARIES / "gabon_adm0.geojson").read_text(encoding="utf-8"))["features"][0]["geometry"]
    rings = geom["coordinates"] if geom["type"] == "Polygon" else [r for poly in geom["coordinates"] for r in poly]
    pts = obs[["longitude", "latitude"]].to_numpy()
    inside = GeoPath(rings[0]).contains_points(pts)
    for hole in rings[1:]:
        inside &= ~GeoPath(hole).contains_points(pts)
    return inside


def monthly_counts(obs: pd.DataFrame, filter_static: bool) -> dict[str, dict[str, int]]:
    obs = obs[obs["in_ga"]]
    df = obs[(obs["type"] == 0) & ~obs["masked"]] if filter_static else obs
    out: dict[str, dict[str, int]] = {}
    for (month, source, sat), n in df.groupby(["month", "source", "satellite"]).size().items():
        row = out.setdefault(month, {"modis": 0, "terra": 0, "aqua": 0, "snpp": 0, "n20": 0})
        if source == "modis":
            row["modis"] += n
            row["terra" if sat == "Terra" else "aqua"] += n
        else:
            row["snpp" if source == "viirs-snpp" else "n20"] += n
    return out


# ---------------------------------------------------------------- calibration (port de build_baseline_series)


def months(start: str, end: str) -> list[str]:
    return [p.strftime("%Y-%m") for p in pd.period_range(start, end, freq="M")]


def fit_linear(xs: list[float], ys: list[float]) -> tuple[float, float]:
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    denom = sum((x - mx) ** 2 for x in xs)
    if denom == 0:
        return 1.0, 0.0
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / denom
    return slope, my - slope * mx


def eval_metrics(preds: list[float], actuals: list[float]) -> dict[str, float]:
    errs = [p - a for p, a in zip(preds, actuals)]
    mean_a = sum(actuals) / len(actuals)
    sst = sum((a - mean_a) ** 2 for a in actuals)
    sse = sum(e * e for e in errs)
    return {
        "mae": round(sum(abs(e) for e in errs) / len(errs), 2),
        "rmse": round(math.sqrt(sse / len(errs)), 2),
        "bias": round(sum(errs) / len(errs), 2),
        "r2": round(1.0 - sse / sst if sst > 0 else 0.0, 4),
    }


def conformal(res: list[float], level: float = 0.80) -> float:
    if not res:
        return 0.25
    ordered = sorted(res)
    return ordered[max(0, min(len(ordered) - 1, math.ceil((len(ordered) + 1) * level) - 1))]


def calibrate(counts: dict[str, dict[str, int]]) -> tuple[dict, dict]:
    def col(ms: list[str], key: str) -> list[float]:
        return [float(counts.get(m, {}).get(key, 0)) for m in ms]

    tr, te = months(*TRAIN), months(*TEST)
    x_tr, xt_tr, y_tr = col(tr, "modis"), col(tr, "terra"), col(tr, "snpp")
    x_te, xt_te, y_te = col(te, "modis"), col(te, "terra"), col(te, "snpp")

    alpha = sum(y_tr) / sum(x_tr) if sum(x_tr) > 0 else 1.0
    ols_a, ols_b = fit_linear(x_tr, y_tr)
    p, q = fit_linear([math.log1p(x) for x in x_tr], [math.log1p(y) for y in y_tr])
    pt, qt = fit_linear([math.log1p(x) for x in xt_tr], [math.log1p(y) for y in y_tr])

    q80 = conformal([abs(math.log1p(y) - (p * math.log1p(x) + q)) for x, y in zip(x_te, y_te)])
    q80_t = conformal([abs(math.log1p(y) - (pt * math.log1p(x) + qt)) for x, y in zip(xt_te, y_te)])

    bridge = months("2019-01", TEST[1])
    snpp_sum, n20_sum = sum(col(bridge, "snpp")), sum(col(bridge, "n20"))
    params = {
        "global_ratio_alpha": round(alpha, 4),
        "ols_slope": round(ols_a, 4),
        "ols_intercept": round(ols_b, 2),
        "power_law_p": round(p, 4),
        "power_law_q": round(q, 4),
        "terra_only_p": round(pt, 4),
        "terra_only_q": round(qt, 4),
        "conformal_q80_log": round(q80, 4),
        "conformal_q80_terra_log": round(q80_t, 4),
        "noaa20_to_snpp_ratio": round(n20_sum / snpp_sum if snpp_sum > 0 and n20_sum > 0 else 1.0, 4),
    }
    metrics = {
        "train_months": len(tr),
        "test_months": len(te),
        "models_out_of_sample": {
            "naive": eval_metrics(x_te, y_te),
            "global_ratio": eval_metrics([alpha * x for x in x_te], y_te),
            "ols_linear": eval_metrics([max(0.0, ols_a * x + ols_b) for x in x_te], y_te),
            "power_law_log1p": eval_metrics([max(0.0, math.expm1(p * math.log1p(x) + q)) for x in x_te], y_te),
            "terra_only_power_law": eval_metrics(
                [max(0.0, math.expm1(pt * math.log1p(x) + qt)) for x in xt_te], y_te
            ),
        },
    }
    return params, metrics


def quartiles(values: list[float]) -> tuple[float, float, float]:
    ordered = sorted(values)
    med = statistics.median(ordered)
    if len(ordered) >= 4:
        qs = statistics.quantiles(ordered, n=4)
        return med, qs[0], qs[2]
    return med, ordered[0], ordered[-1]


def reconstruct(counts: dict[str, dict[str, int]], params: dict) -> tuple[list[dict], dict[int, tuple]]:
    p, q = params["power_law_p"], params["power_law_q"]
    pt, qt = params["terra_only_p"], params["terra_only_q"]
    q80, q80_t = params["conformal_q80_log"], params["conformal_q80_terra_log"]
    n20_ratio = params["noaa20_to_snpp_ratio"] or 1.0

    rows = []
    for m in months(min(counts), max(counts)):
        c = counts.get(m, {})
        mod, terra = c.get("modis", 0), c.get("terra", 0)
        aqua = c.get("aqua", 0) if m >= TERRA_ONLY_CUTOFF else None
        snpp = c.get("snpp", 0) if SNPP_FIRST_COUNT <= m <= SNPP_END else None
        n20 = c.get("n20", 0) if m >= N20_FIRST_COUNT else None

        if m < SNPP_START:
            if m < TERRA_ONLY_CUTOFF:
                regime = "partial_year" if m < "2001-01" else "modis_terra_only"
                mu, half = pt * math.log1p(terra) + qt, q80_t
            else:
                regime, mu, half = "modis_terra_aqua", p * math.log1p(mod) + q, q80
            cov = "partial_sp" if m < "2001-01" else "complete_sp"
            h, lo, hi = (max(0.0, math.expm1(v)) for v in (mu, mu - half, mu + half))
        elif snpp is not None:
            regime, cov, h = "viirs_snpp_observed", "complete_sp", float(snpp)
            lo = hi = h
        elif n20 is not None:
            regime = "viirs_noaa20_bridge"
            cov = "nrt_only" if m >= "2026-01" else "complete_sp"
            h = n20 / n20_ratio
            lo, hi = h * 0.9, h * 1.1
        else:
            regime, cov, h, lo, hi = "missing", "no_data", None, None, None

        rows.append(
            {
                "month": m,
                "modis_count": mod,
                "modis_terra_count": terra,
                "modis_aqua_count": aqua,
                "viirs_snpp_count": snpp,
                "viirs_noaa20_count": n20,
                "harmonized_value": None if h is None else round(h, 2),
                "ci_low": None if lo is None else round(lo, 2),
                "ci_high": None if hi is None else round(hi, 2),
                "sensor_regime": regime,
                "coverage_status": cov,
            }
        )

    by_month: dict[int, list[float]] = {i: [] for i in range(1, 13)}
    for r in rows:
        if "2001" <= r["month"][:4] <= "2025" and r["harmonized_value"] is not None:
            by_month[int(r["month"][5:])].append(r["harmonized_value"])
    baselines = {
        k: (*(round(v, 2) for v in quartiles(vals)), len(vals)) for k, vals in by_month.items() if vals
    }
    return rows, baselines


def calendar_series(rows: list[dict], baselines: dict[int, tuple]) -> list[dict]:
    series = []
    for r in rows:
        med, p25, p75, _ = baselines.get(int(r["month"][5:]), (None, None, None, 0))
        h = r["harmonized_value"]
        series.append(
            {
                **{k: r[k] for k in list(r)[:9]},
                "baseline_median": med,
                "baseline_iqr": [p25, p75] if p25 is not None and p75 is not None else None,
                "anomaly_percent": round(100.0 * (h - med) / med, 2) if h is not None and med else None,
                "anomaly_absolute": round(h - med, 2) if h is not None and med is not None else None,
                "sensor_regime": r["sensor_regime"],
                "coverage_status": r["coverage_status"],
                "uncertainty_note": "",
            }
        )
    return series


# ---------------------------------------------------------------- réponses API


def method_info(filter_static: bool) -> dict:
    return {
        "name": "power_law_log1p_static_masked" if filter_static else "power_law_log1p_unfiltered",
        "version": "v2.0",
        "reference_scale": "VIIRS_375m_SNPP_equiv",
        "bridge_after_2026_11_02": "VIIRS_NOAA20",
    }


def regions_response() -> dict:
    def to_multi(geom: dict) -> dict:
        coords = [geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"]
        return {"type": "MultiPolygon", "coordinates": coords}

    def bbox(geom: dict) -> list[float]:
        pts = [pt for poly in geom["coordinates"] for ring in poly for pt in ring]
        xs, ys = [x for x, _ in pts], [y for _, y in pts]
        return [round(min(xs), 5), round(min(ys), 5), round(max(xs), 5), round(max(ys), 5)]

    regions = []
    for fname, rtype in (("gabon_adm0.geojson", "country"), ("gabon_adm1.geojson", "province")):
        for feat in json.loads((BOUNDARIES / fname).read_text(encoding="utf-8"))["features"]:
            props, geom = feat["properties"], to_multi(feat["geometry"])
            code = "GA" if rtype == "country" else props["shapeISO"]
            regions.append(
                {
                    "code": code,
                    "name": props["shapeName"].strip(),
                    "region_type": rtype,
                    "bbox": bbox(geom),
                    "is_custom_supported": True,
                    "geometry": geom,
                }
            )
    regions.sort(key=lambda r: (r["region_type"], r["code"]))
    return {"regions": regions}


def coverage_response(obs: pd.DataFrame) -> dict:
    sensors = []
    for src in sorted(obs["source"].unique()):
        dates = obs.loc[obs["source"] == src, "acq_date"]
        label, end, versions, notes = SENSOR_META[src]
        sensors.append(
            {
                "source": src,
                "label": label,
                "min_date": dates.min(),
                "max_date": dates.max(),
                "operational_end_date": end,
                "processing_levels": ["SP"],
                "product_versions": versions,
                "notes": notes,
            }
        )
    return {"region": "GA", "sensors": sensors}


def anomalies_response(series: list[dict], baselines: dict[int, tuple], filter_static: bool, top_n=10) -> dict:
    ranked = [s for s in series if s["anomaly_percent"] is not None]

    def ser(s: dict) -> dict:
        keys = ("month", "harmonized_value", "baseline_median", "anomaly_percent", "anomaly_absolute", "sensor_regime")
        return {k: s[k] for k in keys}

    return {
        "region": "GA",
        "filter_static": filter_static,
        "monthly_baselines": [
            {"month_num": k, "median": med, "iqr_p25": p25, "iqr_p75": p75,
             "reference_years_count": n, "reference_period": "2001-2025"}
            for k, (med, p25, p75, n) in sorted(baselines.items())
        ],
        "top_positive": [ser(s) for s in sorted(ranked, key=lambda s: -s["anomaly_percent"])[:top_n]],
        "top_negative": [ser(s) for s in sorted(ranked, key=lambda s: s["anomaly_percent"])[:top_n]],
    }


def methodology_response(params: dict, metrics: dict, filter_static: bool, masked_cells: int) -> dict:
    return {
        "region": "GA",
        "filter_static": filter_static,
        "active_run": {
            "method_name": method_info(filter_static)["name"],
            "method_version": "v2.0",
            "reference_scale": "VIIRS_375m_SNPP_equiv",
            "train_window": [f"{TRAIN[0]}-01", f"{TRAIN[1]}-01"],
            "test_window": [f"{TEST[0]}-01", f"{TEST[1]}-01"],
            "params": params,
            "metrics": metrics,
        },
        "static_mask_summary": {"grid_deg": 0.05, "masked_cells_count": masked_cells},
        "limitations": LIMITATIONS,
    }


def static_cells_response(obs: pd.DataFrame) -> list[list]:
    """Sites statiques : [cell_id, type23_count, active_months_snpp, reason] (règle d'import_firms)."""
    g = static_cell_stats(obs)
    out = []
    for (la, lo), r in g[g["flagged"]].iterrows():
        both = r["t23"] >= 20 and r["active"] >= 48
        reason = (
            "persistent_type23_and_snpp_frequency" if both
            else "type23_static_threshold" if r["t23"] >= 20 else "snpp_high_persistence_48m"
        )
        out.append([f"{la / 20:.2f}_{lo / 20:.2f}", int(r["t23"]), int(r["active"]), reason])
    return sorted(out)


def cells_intersecting_gabon(cell_ids: set[str]) -> set[str]:
    """Cellules 0.25° qui intersectent l'ADM0 (comme `geom__intersects` de /hotspots/?region=GA) :
    un coin de cellule dans le polygone, ou un sommet du polygone dans la cellule."""
    geom = json.loads((BOUNDARIES / "gabon_adm0.geojson").read_text(encoding="utf-8"))["features"][0]["geometry"]
    ring = np.array(geom["coordinates"][0] if geom["type"] == "Polygon" else geom["coordinates"][0][0])
    path = GeoPath(ring)
    keep = set()
    for cid in cell_ids:
        la, lo = (float(v) for v in cid.split("_"))
        corners = [(lo, la), (lo + 0.25, la), (lo, la + 0.25), (lo + 0.25, la + 0.25), (lo + 0.125, la + 0.125)]
        vertex_in = ((ring[:, 0] >= lo) & (ring[:, 0] <= lo + 0.25) & (ring[:, 1] >= la) & (ring[:, 1] <= la + 0.25)).any()
        if vertex_in or path.contains_points(corners).any():
            keep.add(cid)
    return keep


def grid_yearly(obs: pd.DataFrame, filter_static: bool) -> list[list]:
    """
    Grille 0.25° (règle de GridCellMonth) agrégée par cellule et par année, pour que le service
    mock puisse resommer n'importe quelle plage d'années comme `/hotspots/?agg=cell`.
    Ligne : [cell_id, année, mois actifs, modis, snpp, noaa20, frp_modis, frp_snpp, frp_noaa20].
    Toutes les détections (pas de découpe ADM0) comme GridCellMonth, cellules intersectant GA.
    """
    df = obs[(obs["type"] == 0) & ~obs["masked"]] if filter_static else obs
    df = df.assign(
        lat0=np.floor(df["latitude"] * 4.0) / 4.0,
        lon0=np.floor(df["longitude"] * 4.0) / 4.0,
        year=df["month"].str.slice(0, 4).astype(int),
    )
    rows = []
    for (la, lo, yr), d in df.groupby(["lat0", "lon0", "year"]):
        by = d.groupby("source")
        n = by.size()
        frp = by["frp"].sum()
        rows.append([
            f"{la:.2f}_{lo:.2f}", int(yr), int(d["month"].nunique()),
            int(n.get("modis", 0)), int(n.get("viirs-snpp", 0)), int(n.get("viirs-noaa20", 0)),
            round(float(frp.get("modis", 0.0)), 2), round(float(frp.get("viirs-snpp", 0.0)), 2),
            round(float(frp.get("viirs-noaa20", 0.0)), 2),
        ])
    keep = cells_intersecting_gabon({r[0] for r in rows})
    return [r for r in rows if r[0] in keep]


def edge_cases() -> dict:
    """Cas limites SYNTHÉTIQUES (non issus des données) pour tester l'UI."""
    base = {"modis_count": None, "modis_terra_count": None, "modis_aqua_count": None,
            "viirs_snpp_count": None, "viirs_noaa20_count": None, "uncertainty_note": ""}
    series = [
        {**base, "month": "2026-10", "viirs_snpp_count": 210, "viirs_noaa20_count": 225,
         "harmonized_value": 210.0, "ci_low": 210.0, "ci_high": 210.0, "baseline_median": 120.0,
         "baseline_iqr": [90.0, 160.0], "anomaly_percent": 75.0, "anomaly_absolute": 90.0,
         "sensor_regime": "viirs_snpp_observed", "coverage_status": "mixed_sp_nrt"},
        {**base, "month": "2026-11", "viirs_noaa20_count": 31, "harmonized_value": 30.0,
         "ci_low": 27.0, "ci_high": 33.0, "baseline_median": 0.0, "baseline_iqr": [0.0, 4.0],
         "anomaly_percent": None, "anomaly_absolute": 30.0,
         "sensor_regime": "viirs_noaa20_bridge", "coverage_status": "nrt_only"},
        {**base, "month": "2026-12", "harmonized_value": None, "ci_low": None, "ci_high": None,
         "baseline_median": 59.0, "baseline_iqr": [40.0, 80.0], "anomaly_percent": None,
         "anomaly_absolute": None, "sensor_regime": "missing", "coverage_status": "no_data"},
    ]
    return {
        "region": {"id": "GA", "name": "Gabon", "filter_static": True},
        "period": {"start": "2026-10", "end": "2026-12"},
        "method": method_info(True),
        "series": series,
    }


def write(name: str, data: dict) -> None:
    path = OUT / name
    path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"  {name}: {path.stat().st_size // 1024} Ko")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*.json"):
        old.unlink()

    obs = load_observations()
    obs["masked"], masked_cells = static_mask(obs)
    obs["in_ga"] = within_gabon(obs)
    print(f"Détections : {len(obs)} (dans GA : {int(obs['in_ga'].sum())}) ; cellules statiques 0.05° : {masked_cells} ; masquées : {int(obs['masked'].sum())}")

    for filter_static, suffix in ((True, "static"), (False, "all")):
        counts = monthly_counts(obs, filter_static)
        params, metrics = calibrate(counts)
        rows, baselines = reconstruct(counts, params)
        series = calendar_series(rows, baselines)
        write(f"calendar_GA_{suffix}.json", {
            "region": {"id": "GA", "name": "Gabon", "filter_static": filter_static},
            "period": {"start": series[0]["month"], "end": series[-1]["month"]},
            "method": method_info(filter_static),
            "series": series,
        })
        write(f"anomalies_GA_{suffix}.json", anomalies_response(series, baselines, filter_static))
        write(f"methodology_GA_{suffix}.json", methodology_response(params, metrics, filter_static, masked_cells))
        if filter_static:
            p = params
            print(f"  params GA static : p={p['power_law_p']} q={p['power_law_q']} q80={p['conformal_q80_log']}"
                  f" n20/snpp={p['noaa20_to_snpp_ratio']} ; R² power-law="
                  f"{metrics['models_out_of_sample']['power_law_log1p']['r2']}")

    static_cells = static_cells_response(obs)
    for filter_static, suffix in ((True, "static"), (False, "all")):
        write(f"hotspots_GA_{suffix}.json", {
            "_format": "grid_yearly: [cell_id, year, months, modis, snpp, noaa20, frp_modis, frp_snpp, frp_noaa20]",
            "grid_yearly": grid_yearly(obs, filter_static),
            "static_cells": static_cells,
        })

    write("regions.json", regions_response())
    write("coverage.json", coverage_response(obs))
    write("calendar_edge_cases.json", edge_cases())


if __name__ == "__main__":
    main()
