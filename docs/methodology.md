# M1 Methodology — Observation Preparation

Status: data preparation pipeline and raw monthly counts. Full cross-sensor harmonization and predictive intervals remain distinct from the M1 preparation modules. The Django demonstration baseline runs as a separate workflow.

The `front-bis` product also publishes a **separate strengthened validation** ([`front-bis/scripts/validate_harmonization.py`](../front-bis/scripts/validate_harmonization.py)), computed across all 48 country CSV files: candidate-source mask frozen on `2000–2019`, three-way train/calibration/test split, and empirical conformal coverage measurement. It serves as methodological proof and does not replace M1 pipeline preparation or the live Django baseline. Its out-of-sample figures (MAE `460.3 → 120.8`, anomaly R² `0.788`, `q80` test coverage `63.9%`) must not be conflated with the live product baseline (`v2.0`, all-years mask, MAE `100.9`).

## Sources and Scope

Inputs are the Gabon country files located in `data/raw/gabon`, accompanied by `AttributesReadme.txt`. The initial archive contains 48 CSV files: 26 MODIS, 14 VIIRS S-NPP, and 8 VIIRS NOAA-20 (`viirs-jpss1` file prefix). Row counts are 59,282, 147,745, and 85,562 respectively (`292,589` total rows). These counts represent thermal hotspot detections, not distinct landscape fires.

This preparation batch uses the country-level CSV boundaries without running a polygon spatial join. The national identifier `GA` is a dataset label, not proof that identical point sets match M2 PostGIS polygon intersections. Counts should be reconciled before comparing aggregates across systems.

## Input Quality Audit

`pipeline.inventory` generates a file and SHA-256 manifest along with checks for CSV schemas, dates/times, WGS84 coordinates, confidence domains, numeric validity, and exact duplicates. The audit report never alters raw input files and does not constitute a full proof of satellite observation coverage.

## Normalization Principles

- Preserve acquisition timestamps in UTC and explicitly zero-pad `HHMM` hours lacking a leading zero.
- Preserve platform provenance: Terra and Aqua remain separate; S-NPP and NOAA-20 are never merged into a single synthetic instrument.
- Standardize export column names without claiming physical equivalence across different instrument thermal bands.
- Retain original confidence levels; nominal classes (`low`, `nominal`, `high`) do not represent identical calibrated probabilities across sensors.
- Preserve thermal hotspot types, product versions, and near-real-time (`NRT`) flags; missing values are never coerced into `type 0`, `nominal`, or daytime defaults.
- Trace every output row back to its source filename, line index, and deterministic `observation_hash` as documented in [`m1-normalization.md`](m1-normalization.md).
- Invalid values must trigger explicit rejection or pipeline failure rather than silent partial outputs.

## Monthly Aggregation

Aggregate counts separately by source, satellite platform, UTC month, and selection policy. The "all detections" view preserves all input thermal types. When delivered, a `type = 0` subset reflects candidate vegetation hotspots tagged by the FIRMS product—it is not equivalent to Django's candidate persistent-cell mask and does not certify fire vs flare ground truth on every pixel.

File availability, detection counts, and observation coverage are three distinct dimensions. A zero count within a present annual CSV implies zero recorded rows, while observation continuity/cloud obstruction remains `unknown`. A missing expected annual CSV produces a `missing_input` status and unavailable (`null`) count rather than zero.

Instrument start boundaries must be explicitly represented: in this archive, MODIS starts on November 1, 2000, S-NPP on January 20, 2012, and NOAA-20 on April 1, 2018 (with Aqua beginning July 2002). Truncated initial years must not label unrelated future months as partial.

Preparation outputs never fabricate harmonized values or confidence bands. See [`m1-normalization.md`](m1-normalization.md) for the exact export contract.

## Validation Criteria Required Prior to Operational Harmonization

1. Reconcile counts end-to-end (`source CSV → normalized → monthly aggregate`) and verify input/output checksums.
2. Specify geographic applicability and filter settings per model; never generalize a national calibration blindly to small polygons without dedicated evaluation.
3. Freeze learned transformations (especially persistence/flare masks) prior to the independent evaluation period.
4. Separate training, model selection, conformal interval calibration, and blind testing windows; report MAE, bias, and seasonal/regime breakdowns.
5. Verify inter-platform continuity and real product availability before bridging sensor streams, particularly for post-2026 operations.

No heuristic gain or guide ratio is assumed without validation. Experimental runs remain strictly reproducible and raw series remain accessible.

## Primary References

- `data/raw/gabon/AttributesReadme.txt` (FIRMS schema accompanying raw CSV inputs).
- [NASA FIRMS — Products, Versions & Data Availability](https://firms.modaps.eosdis.nasa.gov/content/academy/data_api/firms_api_use.html).
- [NASA FIRMS — Outages & Known Notifications](https://firms.modaps.eosdis.nasa.gov/content/notifications/firms/outages.html).
- [NASA MODIS — Mission & Platform History](https://modis-images.gsfc.nasa.gov/).

## Interface with Backend (M2)

M1 outputs reside under `data/processed/`. They can be ingested via a versioned M2 import command; a generated file on disk does not imply database ingestion. Any import must preserve statuses, SHA-256 provenance, filter policies, and processing versions, then reconcile `CSV → DB → API → export`. See [`HANDOFF.md`](HANDOFF.md) for ownership boundaries.

## 0.05° Static Mask and 0.25° Grid Audit

`python -m pipeline.static_mask_audit` reproduces the M2 `0.05°` cell persistence rule (`FLOOR(coordinate × 20)`, threshold `>= 20` type-2/3 detections or S-NPP activity across at least `48` distinct months). When run retrospectively across all `2000–2025` inputs, it flags candidate cells in `static_mask_audit.json` and `static_mask_cells.csv` without modifying source rows.

`python -m pipeline.grid_025` aggregates detections by month, source, satellite, and `0.25°` cell across four views: raw detections, `type 0`, `type 0` outside candidate cells, and all detections inside candidate cells (`grid_025_monthly.csv`, `grid_025_monthly.json`, and `manifest.json`). Across the full 2000–2025 archive (`292,589` rows), the retrospective mask flags `183` cells out of `3,227` active cells (`109,876` total detections inside flagged cells, including `52,023` type-0 detections, or `22.20%` of `234,366` type-0 rows). The `0.25°` grid contains `41,957` month-source-satellite-cell rows computed directly from Gabon country files without administrative geometry clipping.

## Independent Reproduction of the M2 Benchmark (H12–H24)

`python -m pipeline.benchmark_audit --csv data/backups/m1-benchmark-validation/m2_calibration_monthly_series.csv --manifest data/backups/m1-benchmark-validation/manifest.json --output data/processed/benchmark-audit/m1-benchmark-audit.json` verifies the SHA-256 checksum of the M2 export, refits the power-law regression on `train` rows, and recomputes MAE, RMSE, bias, and `R²` on `test` rows for Gabon with and without the candidate static mask.

Reproduction of the November 14, 2026 M2 export (CSV SHA-256 `56ff9a9ab63780a21014d1b7c6c4be1a8529bbd8ef814595a6a9bd55484dadcd`):
- Without mask: `p = 0.7916`, `q = 2.6733`, `MAE = 129.71`, `RMSE = 205.47`, `bias = 19.69`, `R² = 0.9165`.
- With mask: `p = 0.9438`, `q = 1.6529`, `MAE = 100.87`, `RMSE = 169.12`, `bias = 41.77`, `R² = 0.9189`.
- The `95` training months and `72` test months match the M2 manifest. Bounds reconstructed from MODIS, the exported parameters, and the quantile cover `59/72` months without mask and `58/72` months with mask. This coverage is descriptive rather than independent because the quantile was estimated from residuals of the same test period; reproduction does not independently validate model selection or interval coverage.

## Derived Exploratory Display Series (`front-bis`)

To separate seasonal vegetation patterns from persistent heat sources in the UI without mutating API payloads, `front-bis/src/lib/data.ts` computes the following derived display series directly from `/api/v1/calendar/` responses (or their matching offline database snapshots):

1. **Filtered Vegetation-Candidate Series (`staticSeries`)**:
   `/api/v1/calendar/?region=GA&filter_static=true` — NASA `type = 0` thermal detections outside the `183` candidate `0.05°` persistent-source cells (`86,882` raw MODIS + S-NPP + NOAA-20 detections summed across loaded `GA` series points).
2. **Unfiltered Total Series (`allSeries`)**:
   `/api/v1/calendar/?region=GA&filter_static=false` — all thermal detections (`type 0`, `2`, `3`, all cells; `144,060` summed detections across loaded `GA` series points).
3. **Excluded Thermal Detections Series (`flareSeries`, exploratory category)**:
   Derived month-by-month as a non-negative residual difference:
   - Raw per-sensor delta: $\Delta c_{t,s} = \max(0,\, c_{t,s}^{\text{all}} - c_{t,s}^{\text{static}})$ for MODIS (Terra + Aqua), VIIRS S-NPP, and VIIRS NOAA-20.
   - Harmonized delta: $\Delta h_t = \max(0,\, \text{round}((h_t^{\text{all}} - h_t^{\text{static}}) \times 10) / 10)$ when both harmonized values are non-null (otherwise $\Delta c_{t,\text{modis}} + \Delta c_{t,\text{snpp}}$).
   - Monthly baseline & anomaly: $\text{median}_{2001\text{–}2025}(\Delta h_t)$ per calendar month, $\text{abs\_anomaly}_t = \Delta h_t - \text{median}$, and $\text{pct\_anomaly}_t = (\text{abs\_anomaly}_t / \text{median}) \times 100$.
   - **Scientific caveat**: `flareSeries` (`57,178` summed detections across `calendar-all` minus `calendar-static`) combines both NASA `type 2/3` thermal anomalies (`31,110`) and `type 0` detections located inside candidate `0.05°` mask cells (`26,068`). It represents an exploratory series difference of spatial-persistence detections, **not** a census of confirmed gas flares.
4. **Exploratory Thermal Regime Categories (`CalendarHeatmap.vue`)**:
   - **Routine seasonal activity** vs **Abnormal surges**: purely statistical display thresholds comparing each month's harmonized value against its 2001–2025 calendar-month `baseline_median` (`pct >= +25%` with delta `>= 80`, or ratio `>= 1.35×` for surges). These labels highlight inter-annual thermal surges as exploratory indicators rather than causal fire classifications.

## Predictive Outlook (MVP, separate artifact)

`pipeline/prediction/` is an exploratory extension, not part of the observation pipeline or the Django baseline. It estimates a monthly probability of at least one `type 0` detection outside candidate persistent cells for `0.25°` forest cells, using a smoothed monthly climatology over `2012–2025` (VIIRS, homogeneous sensor) and a conservative province trend for `2026–2035`. The forest mask is ESA WorldCover 2021 (tree cover + mangroves, `30%` threshold). Validation is temporal (`2012–2019` train, `2020–2025` test): ROC-AUC `0.898`, PR-AUC `0.755`, Brier `0.098`; the top `10%` of cell-months capture `41.6%` of positives. The target is **forest-associated `type 0` detections**, not natural fires; the outlook is a climatological projection, not a weather forecast. See [`pipeline/prediction/README.md`](../pipeline/prediction/README.md).
