# Engineering Handoff Guide — FirePulse (`M1 / M2 / M3`)

This document describes module ownership across **M1 (Data & Science)**, **M2 (Backend / PostGIS / Infrastructure)**, and **M3 (Frontend / UX — `front-bis/`)**, plus quick verification commands.

---

## 1. M1 — Data & Science (`pipeline/`, `data/processed/`)

### Existing Backend Baseline (`backend/`)
To serve live data early, M2 implemented an operational baseline in two Django management commands:
1. [`import_firms.py`](../backend/apps/observations/management/commands/import_firms.py): Normalizes `MODIS`, `VIIRS S-NPP`, and `VIIRS NOAA-20` (`brightness_mir`, `brightness_tir`, `confidence_tier`, `hotspot_type`, `is_nrt`, SHA-256 hash), constructs the `0.05°` candidate persistent-cell mask (`StaticFlareMaskCell`: `type23_count >= 20 OR active_months_snpp >= 48` → `183` candidate cells in Gabon), and aggregates `GridCellMonth` (`0.25°`).
2. [`build_baseline_series.py`](../backend/apps/harmonization/management/commands/build_baseline_series.py): Trains on `2012-02`→`2019-12` (`95` months), tests on `2020-01`→`2025-12` (`72` months), compares `naive`, `global_ratio`, `ols_linear`, `power_law_log1p`, and `terra_only_power_law`, computes conformal uncertainty (`conformal_q80_log`), and tracks post-2026 NOAA-20 ratios.
3. [`export_calibration_series.py`](../backend/apps/harmonization/management/commands/export_calibration_series.py): Exports `6,011` active series rows (`GA`, `GA-1`–`GA-9` × `filter_static`) to `data/backups/m1-benchmark-validation/m2_calibration_monthly_series.csv` with SHA-256 manifest verification.

### M1 Integration Contract (`--from-pipeline`)
[`build_baseline_series.py`](../backend/apps/harmonization/management/commands/build_baseline_series.py) accepts either:
1. Monthly preparation artifacts (`/data/processed/monthly`: `manifest.json` + `calendar.json` or `monthly_counts.csv`), preserving `not_available` / `missing_input` nulls cleanly; or
2. A calibrated bundle JSON (`/data/processed/calibration/pipeline_bundle.json`) specifying `method_name`, `method_version`, `reference_scale`, per-region `params`, `metrics`, `baselines`, and `series` for atomic replacement in PostGIS.

Priority research extensions: `2026 YTD / NRT` NOAA-20 ingestion past `2026-11-02` (not yet ingested; the demo archive stops at `2025-12` and the relay is not yet validated on 2026 data), hierarchical provincial calibration for noisy low-count provinces (`GA-6`), physical Fire Radiative Power (`FRP`), and custom-polygon interval bounds.

### Predictive Outlook (`pipeline/prediction/`)

The MVP outlook is an M1 artifact consumed by M3; it does not touch the M2 API.

```bash
python -m pip install -r pipeline/requirements-prediction.txt
python -m pipeline.prediction.build_forest_mask   # ESA WorldCover 2021 -> forest_cells.csv
python -m pipeline.prediction.build_climatology   # smoothed monthly climatology + trend
```

- **Target**: `type 0` outside candidate persistent cells, forest cells only (`forest_fraction >= 0.30`).
- **Model**: smoothed monthly frequency `Beta(1, 4)` over `2012–2025` (VIIRS) + conservative province trend `2026–2035`.
- **Validation**: train `2012–2019`, test `2020–2025`; ROC-AUC `0.898`, PR-AUC `0.755`, Brier `0.098`, top `10%` capture `41.6%`.
- **Outputs**: `data/processed/prediction/*` and the compact `front-bis/src/data/prediction.json`.
- **Limits**: climatological projection, not a weather forecast; no ignition cause; static forest mask; FIRMS coverage not exhaustive. See [`pipeline/prediction/README.md`](../pipeline/prediction/README.md).

---

## 2. M3 — Frontend / UX (`front-bis/`)

### Live API & Proxy Access
- **Backend Base URL**: `http://localhost:8000/api/v1/`
- **Frontend Ports (`front-bis/vite.config.ts`)**: Dev server on **`5174`** (`npm run dev`), compiled preview on **`5176`** (`npm run preview`), both proxying `/api` to `http://127.0.0.1:8000` (same-origin requests via `API_BASE = '/api/v1'`).
- **CORS Allowed Origins (`backend/config/settings.py`)**: `localhost:5173`, `127.0.0.1:5173`, `localhost:5174`, `127.0.0.1:5174`.
- **Full REST Schema**: [`docs/api-contract.json`](api-contract.json) (`v2.2.0`).

### Quick API Verification (`curl`)

```bash
# List regions (GA + 9 provinces; ?include_geom=false for lightweight menus)
curl "http://localhost:8000/api/v1/regions/?include_geom=false"

# National Gabon monthly time series (candidate persistent-cell mask enabled)
curl "http://localhost:8000/api/v1/calendar/?region=GA&filter_static=true"

# Custom bounding box query
curl "http://localhost:8000/api/v1/calendar/?bbox=10.5,-3.0,12.5,-1.0&start=2024-06&end=2024-09"

# Custom GeoJSON polygon (URL-encoded)
curl -G "http://localhost:8000/api/v1/calendar/" --data-urlencode 'polygon={"type":"Polygon","coordinates":[[[10.5,-3.0],[12.5,-3.0],[12.5,-1.0],[10.5,-1.0],[10.5,-3.0]]]}'

# Monthly medians & anomalies
curl "http://localhost:8000/api/v1/anomalies/?region=GA&top_n=10"

# 0.25° GeoJSON grid (aggregated by cell + candidate 0.05° layer)
curl "http://localhost:8000/api/v1/hotspots/?mode=grid&agg=cell&start=2024-06&end=2024-09&include_static_cells=true"

# Validation & methodology metrics
curl "http://localhost:8000/api/v1/methodology/?region=GA"

# CSV export
curl "http://localhost:8000/api/v1/export/?region=GA&start=2024-01&end=2024-12"
```

### UI Integration Notes
1. **`bbox` / `polygon` responses**: Compute `2001–2025` `baseline_iqr` `[p25, p75]`, returning `region.id = "CUSTOM_BBOX"` or `"CUSTOM_POLYGON"` with `ci_low: null` and `ci_high: null`.
2. **`/hotspots/` layers**: With `include_static_cells=true`, responses include both `grid_cell_summary`/`grid_cell_month` features (`~28 km` grids) and `static_flare_mask` candidate-cell features (`~5 km` coastal/offshore candidate persistent sources), separated cleanly in `front-bis/src/components/HotspotMap.vue`.
3. **Automatic Regional Language Detection (`front-bis/src/lib/i18n.ts`)**: Initializes **EN / FR** synchronously via browser timezone (`Intl`), refines via Cloudflare edge geo-header (`/cdn-cgi/trace`), and synchronizes the header toggle (`TopBar.vue`) and `<html lang>` / `<title>`.
4. **Prediction section (`#prediction`)**: Lazy-loaded `PredictionExplorer` reads the static `front-bis/src/data/prediction.json` (no API dependency), offers a province filter, a `2026–2035` × month calendar, a `0.25°` SVG probability map, and a floating detail card. Keep the distinction between projection, climatology, and observed series visible; do not present the outlook as a weather forecast.

---

## 3. M2 — Backend / Geo / Infrastructure (`backend/`, `scripts/`, `deploy/`)

- **PostgreSQL Host Port**: `5433` in `.env.example` (maps to container `db:5432`).
- **Key Management Commands**: `load_regions` (with `.strip()` handling tab characters on province names such as `Ogooué-Ivindo`), `import_firms` (SHA-256 deduplication and `version` NRT detection), `build_baseline_series`, and `export_demo_snapshot --verify` (`86` offline JSON files).
- **Production & Demo Resilience**: Gunicorn + Caddy HTTPS stack ([`docker-compose.prod.yml`](../docker-compose.prod.yml), [`deploy/Caddyfile`](../deploy/Caddyfile)), `GZipMiddleware`, PostGIS `AsGeoJSON` queries, fail-closed SHA-256 snapshot fallback (`apps/api/fallback.py`, `X-FirePulse-Cache: FALLBACK`), and preflight/backup scripts (`scripts/preflight_demo.sh`, `scripts/db_backup.sh`, `scripts/db_restore.sh`).
- **Scientific Explainer**: [`docs/principe-harmonisation.md`](principe-harmonisation.md).
