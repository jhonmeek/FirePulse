# FirePulse — `front-bis`

> **Exploratory Diagnostic (`2020–2025`, Country CSVs, Mask Frozen on `2000–2017`)**: `21,199 / 111,719` type-0 thermal detections (`19.0%`), including `9,206 / 48,075` VIIRS S-NPP (`19.1%`), fall inside cells added by the retrospective `2000–2025` mask. These proportions describe detections located inside mask cells, **not** confirmed gas flares, error rates, or causal contamination; the retrospective mask uses test-period data and monthly completeness remains unknown.
>
> **Scientific Status — Under Review**: Figures in the exploratory validation section below reflect the initial historical artifact prior to ongoing script updates. They do not constitute independent validation or a formal coverage guarantee. Please await versioned regeneration and joint M1/M2/M3 review before citing them as finalized performance benchmarks.

An interactive 3D and motion-design narrative around Gabon's harmonized fire calendar (`2000–2025` archive; `2026+` NOAA-20 relay prepared), built for the **NASA Space Apps Challenge 2026 — "Harmonization of MODIS and VIIRS Hot Spots"**.

---

## Launch & Build

Requires **Node.js `^22.18` or `>=24.12`**. From `front-bis/`:

```bash
npm ci                 # Install dependencies
npm run dev            # Development server on http://localhost:5174 (/api proxied to :8000)
npm run type-check     # TypeScript verification (vue-tsc --noEmit)
npm run test:unit -- --run   # Unit tests (i18n, derived series, M1 labels, M2 contract)
npm run build          # Type-check + Vite production bundle
npm run preview        # Local preview on http://localhost:5174
```

---

## What Is Inside

- **3D Globe (`Three.js`)**: Starfield, geographic graticule, orbital paths, Gabon polygon boundary, and additive hotspot particles.
- **Scroll-Driven Story (`7` chapters)**: Opening globe, the 2012 sensor break (`FlareSplit`), MODIS-to-VIIRS translation (`LineChart`), accessible 25-year seasonal calendar (`CalendarHeatmap`), interactive PostGIS/MapLibre map (`HotspotMap`), exploratory protocol review + 2026 relay (`ValidationProof`, `SeasonTimeline`), and a calibrated 2026–2035 forest-fire outlook (`PredictionExplorer`).
- **Animated SVG Charts (`LineChart`)**: Per-sensor views (MODIS, VIIRS S-NPP, VIIRS NOAA-20), experimental harmonized series, nominal 80% uncertainty band, and enlarged axis labels (`16.5px`) for legible presentation.
- **Accessible Year × Month Calendar (`CalendarHeatmap`)**: Inverted light-to-dark intensity ramp (`#f7efe2` → `#2a0606`), keyboard navigation, month detail inspector, historical rank, composition breakdown, and CSV export.
- **Interactive Gabon & Maritime Map (`HotspotMap`)**: Dark data-first MapLibre canvas (`0.25°` grid, Gabon & 9 province outlines, `183` candidate `0.05°` persistent-source cells). The four-point exploratory NOAA-20 NRT maritime snapshot from `public/data/gabon-maritime-observations.geojson` loads automatically, and the initial view includes these offshore points. An indicative Gabon EEZ overlay loads from Marine Regions WMS when online; the polygon is not embedded and excludes territorial waters. The provider is linked below the map. `Ctrl/Meta + wheel` / `"Scroll zoom: locked / on"` protects against accidental page-scroll zooming.
- **Recent NRT detections (`RecentDetections`)**: Separate panel below the map for unclassified thermal points in Gabon from the last 48 hours. It shows satellite, UTC acquisition/check times, age, coordinates and FRP; refreshes every five minutes and supports manual retry. Empty, API error and offline demo states remain explicit. These points are not added to the historical filtered fire series.
- **Regional Auto-Localization (`FR / EN`)**: Browser timezone + language detection (`Africa/Libreville`, Francophone countries, bilingual fallbacks) with optional `/cdn-cgi/trace` enhancement when deployed behind Cloudflare (fails gracefully offline / non-Cloudflare) and strict session priority (`sessionStorage`) for manual `FR` / `EN` switches.
- **Confidence Cards (`ConfidenceCard`)**: Explicit data source, period, satellite, protocol, empirical coverage, and scientific caveats below every visual.
- **Future Risk Outlook (`PredictionExplorer`)**: Province-filtered `2026–2035` × month calendar, `0.25°` forest-fire probability map, floating cell/province detail card on hover/click, and a validation/calibration note. Climatological projection, not a weather forecast; forest mask from ESA WorldCover 2021; target is `type 0` outside candidate persistent cells.

---

## Data Connection & Offline Fallback

`front-bis` queries the Django / PostgreSQL / PostGIS API (`/api/v1/`) via Vite proxy (`localhost:8000`) and automatically falls back to local JSON snapshots (`src/data/*.json`) when the backend is offline or when `VITE_USE_MOCKS=true`:

| Endpoint | Snapshot File | Purpose |
| :--- | :--- | :--- |
| `/api/v1/health/` | `health.json` | PostGIS status & database record counts |
| `/api/v1/calendar/` | `calendar-static.json`, `calendar-all.json` | Harmonized monthly series (`filter_static=true/false`) & `2001–2025` reference medians |
| `/api/v1/hotspots/?mode=grid&agg=cell` | `hotspots-static.json`, `hotspots-all.json` | `0.25°` grid & `183` candidate `0.05°` persistent-source cells |
| `/api/v1/methodology/` | `methodology.json`, `methodology-raw.json` | Calibrated parameters & historical `2020–2025` metrics |
| `/api/v1/coverage/` | `coverage.json` | Sensor temporal availability & S-NPP / NOAA-20 status |
| `/api/v1/regions/` | `regions.json` | Gabon (`GA`) & `9` provinces (`GA-1`–`GA-9`) GeoJSON |
| `/api/v1/export/` | Client CSV fallback (`buildSeriesCsvFallback`) | Schema-exact CSV export conforming to `docs/api-contract.json` |
| Static prediction artifact | `prediction.json` | `2026–2035` forest-fire outlook (MVP climatology + province trend) |
| `/api/v1/recent-unknown-detections/` | None (unavailable in offline demo) | Last 48 h NRT thermal points with unknown FIRMS type; live PostGIS required |

Response provenance should always be verified per runtime (`live` API vs `snapshot` fallback).

---

## Derived Exploratory Display Series & Categories (`M1 Review Alignment`)

To avoid conflating raw series differences or anomaly thresholds with causal classifications:

- **`staticSeries`** (`filter_static=true`): `type = 0` thermal detections outside candidate `0.05°` persistent-source cells (`175,500` summed GA detections across MODIS, S-NPP, and NOAA-20 in `calendar-static.json`, `61.6%` of `285,013`).
- **`allSeries`** (`filter_static=false`): all thermal detections (`type 0`, `2`, `3`, all cells; `285,013` summed GA detections in `calendar-all.json`).
- **`flareSeries` / `computeExcludedSeries(allPoints, cleanPoints)` (*Excluded thermal detections — exploratory category*)**:
  Computed month-by-month in `src/lib/data.ts` as the exact residual difference (`allPoints - cleanPoints`) only when both inputs exist and the difference is non-negative (`>= 0`):
  $$\Delta c_{t,s} = c_{t,s}^{\text{all}} - c_{t,s}^{\text{static}} \;\; (\text{or } \text{null} \text{ if } < 0 \text{ or input missing}), \qquad \Delta h_t = \text{round}((h_t^{\text{all}} - h_t^{\text{static}}) \times 10) / 10 \;\; (\text{or } \text{null} \text{ if } < 0 \text{ or } h \text{ missing})$$
  Missing harmonized inputs or absent months do **not** fall back to `modis + snpp`, and negative deltas are **not** clamped to `0`: affected points return `null` (unavailable) and flag `uncertainty_note` (`missing_clean_month`, `missing_sensor_input:*`, `missing_harmonized_input:harmonized_value`, `negative_series_delta:*`). Pre-launch both-`null` sensor entries remain `null`.
- **`composition` (`excludedBySensorPartition` vs `provenanceAudit`)**:
  Dynamic series differences (`gaExcluded = 109,513` across the GA snapshot) are partitioned exclusively by instrument and active observation period (`MODIS 2000-11 → 2025-12`, `VIIRS S-NPP 2012-01 → 2025-12`, `VIIRS NOAA-20 2018-04 → 2025-12`). Static FIRMS `type` counts over the ingested PostGIS SP archive (`285,013` GA rows; `57,934` type `2/3` = `20.3%` and `51,579` type `0` inside `183` candidate `0.05°` cells = `18.1%`) are exposed separately in `provenanceAudit` (`isIndependentStaticAudit: true`) and never mixed into the dynamic delta denominator.
- **Calendar Seasonal Regime Labels (*Routine activity vs Abnormal surges*)**:
  Visual anomaly highlights compare harmonized monthly values against `2001–2025` `baseline_median` values (`> +50%` statistical surplus highlighted as exploratory surges). They represent exploratory statistical regimes of thermal detections, not causal ground truth.

---

## Exploratory Analysis vs Live DB `v2.0` Protocol

[`scripts/validate_harmonization.py`](scripts/validate_harmonization.py) reads the **48 country FIRMS CSVs** and writes [`src/data/validation.json`](src/data/validation.json) + `src/data/validation_series.csv`:

1. **Pre-calibration frozen mask (`2000–2017`)** — isolates candidate cells strictly prior to calibration and testing (`61` frozen cells vs `183` all-years cells).
2. **Three-way temporal split** — training `2012-02 → 2017-12` (`71` months), calibration `2018-01 → 2019-12` (`24` months), evaluation `2020-01 → 2025-12` (`72` months).
3. **Anomaly & negative-control evaluation** — reports both raw seasonal `R²` (`0.918`) and seasonality-adjusted anomaly `R²` (`0.788`), nominal `80%` empirical coverage (`63.9%`), look-ahead delta (`+24.1` MAE between frozen and all-years masks), NOAA-20 bridge behavior, and the Terra → Aqua negative control (`anomaly R² = -0.241`).

| Metric / Comparison | Historical Exploratory Artifact Result |
| :--- | :--- |
| Power-law vs OLS on test anomalies | Anomaly `R²` **0.788** vs **0.733** |
| Power-law vs global / seasonal ratio | Anomaly `R²` **0.788** vs `0.671` / `0.640` |
| Power-law vs naive baseline | MAE **120.8** vs **460.3** · Raw `R²` `0.918` vs `0.079` |
| Nominal `80%` coverage (calibrated `2018–2019`) | **63.9%** over `2020–2025` (illustrative indicator, not a guarantee) |
| Frozen vs all-years mask | `61` vs `183` cells · MAE `120.8` vs `96.7` (`+24.1` MAE look-ahead gap) |
| Held-out NOAA-20 evaluation | MAE `100.1` · Raw `R²` `0.956` · Anomaly `R²` `0.867` (independence limited by mask/ratio) |
| Negative control (Terra → Aqua) | MAE `428.7` · Anomaly `R²` `-0.241` |
| High dry season (`Jun–Oct`) vs low season (`Nov–May`) | Anomaly `R²` `0.797` vs `0.549` |
| Mask threshold sensitivity (`10/24`, `20/48`, `30/72`) | Anomaly `R²` `0.860` / `0.788` / `0.792` |

> **Important**: Live DB `v2.0` (`GA` polygon, `all-years` `183`-cell mask, `MAE 100.9`, `R² 0.919`) and this exploratory CSV artifact (`61` cells frozen pre-test, `MAE 120.8`, anomaly `R² 0.788`) use different spatial boundaries and protocols and are not directly interchangeable. FirePulse is an independent research **proof-of-concept prototype** and is neither affiliated with nor endorsed by NASA.

---

## AI / Super Intelligence (SI) Disclosure

In accordance with NASA Space Apps Challenge Super Intelligence rules, AI assistants (**Gemini 4 Hydrogen**, **Gemini 4 Argon**, **Deepseek 4.1 Flash 1017**, **Claude Opus 5.5**, **GPT 6 Luna**, and **GPT 6 Terra**) assisted with UI/UX engineering, TypeScript/Vue components, and bilingual EN/FR localization. All observations (`292,589` CSV rows) come strictly from authentic open **NASA FIRMS** archives; zero NASA branding assets are included.
