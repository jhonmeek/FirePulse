# FirePulse — Gabon Fire History (2000–2025 archive; 2026 relay prepared)

Multi-sensor **NASA FIRMS** thermal hotspot harmonization platform (**MODIS Collection 6.1 Terra/Aqua**, **VIIRS Suomi-NPP 375 m**, **VIIRS NOAA-20 375 m**) focused on **Gabon and its 9 provinces** (`GA`, `GA-1`–`GA-9`), built for the **NASA Space Apps Challenge 2026 — Harmonization of MODIS and VIIRS Hot Spots**.

> **Submission & Engineering Docs**: See [docs/SPACE_APPS_SUBMISSION.md](docs/SPACE_APPS_SUBMISSION.md) for the Global Award submission kit (7-slide script, 30s video script, project details, and Super Intelligence / AI disclosure) and [docs/HANDOFF.md](docs/HANDOFF.md) for architecture and component boundaries (`pipeline/`, `backend/`, `front-bis/`).

---

## Project Overview

### Why Raw Satellite Counts Mislead Over Gabon
Comparing raw NASA thermal hotspot detections across 25 years creates two severe distortions over Gabon:
1. **Sensor resolution jump in 2012**: Switching from **MODIS (~1 km/pixel)** to **VIIRS (375 m/pixel)** causes an apparent **×3.9** surge in raw hotspot counts even when landscape fire activity has not exploded.
2. **Persistent heat sources**: Out of **285,013** thermal detections recorded inside Gabon borders (`2000-11` through `2025-12`), **38.4% (109,513 detections)** are excluded by the full filter: **57,934 type 2/3 detections** (`20.3%`, fixed or offshore sources) and **51,579 type-0 detections inside 183 candidate `0.05°` cells** (`18.1%`, primarily coastal Ogooué-Maritime and offshore). These cells are candidates, not individually confirmed flares.

### How FirePulse Works
- **Separates candidate persistent sources from type-0 detections**: Retains **175,500 type-0 detections outside candidate cells (61.6%)** while masking **183 candidate `0.05°` cells** on both national series and the interactive map. Type 0 is a product classification, not field validation.
- **Harmonizes 25 years onto one continuous VIIRS scale**: Learns a `power-law log1p` calibration across the **2012–2019** sensor overlap and blind-tests strictly out-of-sample over **72 unseen months (2020–2025)** — cutting average monthly error by **74%** compared to the naive baseline (MAE `460.3` → `120.8`; raw seasonal `R² = 0.918`, anomaly `R² = 0.788`, q80 empirical coverage `63.9%`). See [docs/principe-harmonisation.md](docs/principe-harmonisation.md) and [front-bis/src/data/validation.json](front-bis/src/data/validation.json).
- **Prepares the post-2026 relay**: **VIIRS Suomi-NPP** operational delivery ended on **November 2, 2026**. FirePulse prepares the **NOAA-20** bridge (operating since 2018; held-out calibration ratio `0.940`, ~`6.0%` average difference), but the relay is **not yet validated on 2026 data**; the demo archive stops in December 2025.

### Reading the Numbers
- **Scope**: `285,013` detections inside `GA`; `175,500` type-0 detections outside candidate cells (`61.6%`); `109,513` excluded by the full filter (`38.4%`) = `57,934` type 2/3 (`20.3%`) + `51,579` type 0 inside `183` candidate cells (`18.1%`).
- **Two validation protocols**: the live database `v2.0` (all-years mask, `183` cells, MAE `100.9`, raw `R² 0.919`) and the reinforced validation (mask frozen on `2000–2019`, `61` cells, 3-way split, MAE `460.3 → 120.8`, raw `R² 0.918`, anomaly `R² 0.788`, q80 coverage `63.9%`). They are not directly comparable without stating which applies.
- **Vocabulary**: type 0 is a product classification, not field validation. The `183` cells are **candidate** persistent sources, not individually confirmed flares.
- **Status**: SP archive `2000-11 → 2025-12`; no 2026 or NRT data in the demo. The NOAA-20 relay is calibrated, not yet validated on 2026.
- **Interactive storytelling (`front-bis/`)**: Features a scroll-guided 3D Earth (`Three.js`), yearly and monthly filterable line charts with separate MODIS / S-NPP / NOAA-20 views, an inverted light-to-dark 25-year seasonal calendar (distinguishing routine dry-season burning from unusual spikes), an interactive 9-province map (`MapLibre GL` + PostgreSQL/PostGIS), automatic regional language adaptation (**EN / FR**), and a confidence note under the series and the map.
- **Legacy dashboard (`frontend/`, M3 milestone H34–H42)**: Vue 3 + TypeScript + Vite + Tailwind 4 + Pinia + ECharts + MapLibre explorer (calendar, comparison chart, anomalies, map, drawn zone, CSV export), offline demo build with embedded Gabon FIRMS data, Playwright journey and axe-core WCAG 2.1 AA audit, TypeScript types aligned with [docs/api-contract.json](docs/api-contract.json) v2.2.0. See its quick start below.

---

## Repository Architecture

```text
FirePulse/
├── backend/                     # Django REST Framework + PostGIS backend
│   ├── config/                  # Settings (PostGIS, CORS, GZip) & URL routing (/api/v1/)
│   └── apps/
│       ├── observations/        # Region, ImportBatch, HotspotObservation, StaticFlareMaskCell, GridCellMonth
│       ├── harmonization/       # CalibrationRun, MonthlyBaseline, HarmonizedMonthSeries
│       └── api/                 # REST v1 endpoints, PostGIS GeoJSON queries & JSON snapshot fallback
├── data/
│   ├── boundaries/              # gabon_adm0.geojson (GA) + gabon_adm1.geojson (GA-1..GA-9)
│   ├── raw/gabon/               # 48 raw NASA FIRMS CSV files (2000–2025) + AttributesReadme.txt
│   └── processed/               # Reproducible M1 audit, normalized & monthly outputs
├── docs/
│   ├── SPACE_APPS_SUBMISSION.md # Official Global Award submission text & demo scripts
│   ├── api-contract.json        # Open API v1 response contract (v2.2.0)
│   ├── methodology.md           # M1 scientific protocol & expectations
│   ├── limitations.md           # Known constraints, assumptions & boundaries
│   ├── principe-harmonisation.md# Harmonization math & 2020–2025 blind validation notes
│   ├── m1-data-audit.md         # Inventory & quality audit of the 48 FIRMS CSVs
│   ├── m1-normalization.md      # Normalized dataset schema & monthly aggregation contract
│   └── HANDOFF.md               # Module ownership & quick-test curl commands
├── front-bis/                   # Main web application (Vue 3, TypeScript, Vite, Three.js, MapLibre GL)
├── pipeline/                    # Standard-library Python ETL & audit modules (M1)
├── scripts/                     # Backup, restore & demo preflight scripts
├── tests/                       # Python pipeline unit/integration tests
├── docker-compose.yml           # PostgreSQL 16 / PostGIS 3.4 (:5433) + Django (:8000)
└── docker-compose.prod.yml      # Production Gunicorn + Caddy HTTPS stack
```

---

## Quick Start

### 1. Backend + PostGIS (Docker Compose)

Configure local environment variables:

```bash
cp .env.example .env
```

> **Note**: `.env.example` maps PostgreSQL to host port `5433` (`POSTGRES_HOST_PORT=5433` → container `5432`) to avoid conflicts with local PostgreSQL instances. Never commit `FIRMS_MAP_KEY` or `EARTHDATA_TOKEN` secrets.

Start PostgreSQL/PostGIS and Django, then ingest boundaries, FIRMS data, and baseline series:

```bash
docker compose up -d --build
docker compose exec backend python manage.py load_regions
docker compose exec backend python manage.py import_firms
docker compose exec backend python manage.py build_baseline_series
```

Verify backend health and test suite:

```bash
docker compose exec backend python manage.py test -v 2
curl http://localhost:8000/api/v1/health/
```

Expected `/api/v1/health/` metrics: `"status": "ok"`, `"database": "connected"`, `regions: 10`, `hotspots: 292589`, `grid_cell_months: 42482`, `harmonized_months: 6011`.

### 2. Frontend (`front-bis/`)

Requires **Node.js `^22.18` or `>=24.12`**. From [front-bis/](front-bis/):

```bash
npm install
npm run dev      # Development server on http://localhost:5174 (/api proxied to :8000)
```

Production type-check, build, and local preview (`http://127.0.0.1:5176`):

```bash
npm run build    # vue-tsc --noEmit -p tsconfig.json && vite build
npm run preview
```

### 2b. Legacy dashboard (`frontend/`)

Requires **Node.js `^22.18` or `>=24.12`**. From [frontend/](frontend/):

```bash
npm install
npm run dev      # http://localhost:5173
```

| Mode | How to enable | Data source |
| :--- | :--- | :--- |
| **Mocks** (dev default) | nothing to do | `frontend/src/mocks/*.json` (region `GA`) |
| **Django API** | create `frontend/.env.local` with `VITE_USE_MOCKS=false` | `/api/v1` proxied by Vite to `http://localhost:8000` |
| **Standalone demo** | `npm run build:demo` then `npm run preview:demo` | static `dist-demo/` build with embedded mocks: works without Docker, API or Internet |

Regenerate mocks after a change in `data/raw/gabon/` or the baseline chain (needs `pandas`, `numpy`, `matplotlib`): `py -3.12 scripts/generate_mocks.py` then `npm run format`. Checks:

```bash
npm run lint
npm run test:unit -- --run
npm run build
npm run test:e2e
```

### 3. M1 Data Pipeline & Validation (Python `3.10+`)

From repository root (uses Python standard library only):

```bash
python -m unittest discover -s tests -v
python -m pipeline.inventory --input data/raw/gabon --output data/processed/audit
python -m pipeline.normalize --input data/raw/gabon --output data/processed/normalized
python -m pipeline.aggregate_monthly --input data/processed/normalized --output data/processed/monthly
python front-bis/scripts/validate_harmonization.py
```

---

## REST API v1 Endpoints (`http://localhost:8000/api/v1/`)

| Endpoint | Purpose |
| :--- | :--- |
| `GET /api/v1/health/` | Database status, PostGIS version, record counts, fallback readiness |
| `GET /api/v1/regions/` | Gabon (`GA`) + 9 provinces (`GA-1`–`GA-9`), bounding boxes & GeoJSON |
| `GET /api/v1/coverage/` | Temporal availability, product versions, `SP`/`NRT` status & `2026-11-02` S-NPP note |
| `GET /api/v1/calendar/` | Raw vs harmonized series, medians & anomalies (`region`, `bbox`, `polygon`, `filter_static`) |
| `GET /api/v1/anomalies/` | Monthly medians `[p25, p75]` & top positive/negative anomalies |
| `GET /api/v1/hotspots/` | `0.25°` GeoJSON grid (`agg=month\|cell`) or points + optional `static_flare_mask` layer |
| `GET /api/v1/methodology/` | Calibrated parameters, out-of-sample `2020–2025` metrics, mask statistics & limitations |
| `GET /api/v1/export/` | CSV export (`dataset=series\|points`) filtered by region, bbox/polygon, dates & flare filter |

Offline fallback snapshots (`86` verified SHA-256 JSON files in `data/backups/demo_snapshot`) keep the API functional via `X-FirePulse-Cache: FALLBACK` even if PostgreSQL is offline. Full contract: [docs/api-contract.json](docs/api-contract.json).

---

## AI / Super Intelligence (SI) Disclosure — NASA Space Apps 2026

In accordance with official NASA Space Apps Challenge **Super Intelligence (SI)** rules:

- **Where AI models were used**: Large Language Models and AI coding assistants (**Gemini 4 Hydrogen**, **Gemini 4 Argon**, **Deepseek 4.1 Flash 1017**, **Claude Opus 5.5**, **GPT 6 Luna**, and **GPT 6 Terra**) assisted with software engineering, data harmonization pipeline structuring (`pipeline/` & `backend/`), frontend UI/UX refinement (`front-bis/`), and bilingual EN/FR documentation and interface localization.
- **Data Authenticity**: All fire detections (`292,589` total CSV rows; `285,013` within Gabon borders) and statistical evaluations come strictly from authentic open **NASA FIRMS** satellite archives (**MODIS Collection 6.1**, **VIIRS S-NPP**, **VIIRS NOAA-20**). No synthetic hotspot observations or AI-generated images/video/audio assets are shipped in the application.
- **NASA Branding Compliance**: This project uses **zero NASA logos, flags, emblems, or mission identifiers**, and is an independent NASA Space Apps prototype neither affiliated with nor endorsed by NASA.
