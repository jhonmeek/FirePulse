# M1 — Normalization and Monthly Aggregation Contract

## Reproduction & Outputs

From repository root using Python standard library (zero external dependencies):

```sh
python -m pipeline.normalize --input data/raw/gabon --output data/processed/normalized
python -m pipeline.aggregate_monthly --input data/processed/normalized --output data/processed/monthly
```

`pipeline.normalize` emits one CSV per source input (`*_normalized.csv`) plus a deterministic `manifest.json`. `pipeline.aggregate_monthly` emits `monthly_counts.csv`, `calendar.json`, and `manifest.json`. Manifests trace input/output pairs, SHA-256 digests, row counts, duplicate diagnostics, and code hashes without mutating raw inputs.

Versioned deliverables include the normalization manifest and compact monthly summaries (`monthly_counts.csv`, `calendar.json`, monthly `manifest.json`), while bulky normalized annual exports stay local and deterministically rebuildable. Unrecognized CSV schemas or colliding file basenames fail fast before overwriting published artifacts.

## Normalized Row Contract

- `source` preserves `MODIS` and `S-NPP`, mapping `JPSS-1` to `NOAA-20`.
- `satellite` normalizes to `Terra`, `Aqua`, `N`, or `N20`, while `instrument_original` and `satellite_original` preserve verbatim upstream labels.
- `brightness_mir` and `brightness_tir` align column names without claiming physical radiometric equivalence across sensor bands.
- Confidence ratings preserve `confidence_raw` verbatim while transcribing MODIS `0–100` (`<30`, `30–<80`, `>=80`) and VIIRS `L/N/H` classes separately to `low`, `nominal`, and `high` descriptors.
- `is_nrt` is `true` strictly when `version` contains `nrt` (case-insensitive).
- `observation_hash` computes a deterministic SHA-256 over core observation fields (`acq_date`/`acq_time` UTC, coordinates, sensor attributes) excluding file provenance. Invalid coordinates, non-finite numerics, invalid timestamps, mismatched platform/instrument pairs, or missing required fields reject the batch before replacing prior outputs.

## Monthly Aggregation Contract (`GA` Preparation Scope)

- Regional scope is `GA` with `dataset_scope=country_file_unverified_geometry` (country CSV extract, pre-PostGIS clipping).
- Counts track `(month, source, satellite)` distinctly without merging Aqua/Terra or S-NPP/NOAA-20, leaving `harmonized_value = null` in preparation tables.
- `count_type0_candidate` counts `type = 0` product flags prior to spatial flare masking (unlike Django's `filter_static=true` `0.05°` mask).
- Dense calendar timeline spans `2000-11` through `2025-12` (`302` months × `4` platforms = `1,208` rows). Pre-launch windows (MODIS/Terra `< 2000-11-01`, Aqua `< 2002-07`, S-NPP `< 2012-01-20`, NOAA-20 `< 2018-04-01`) store `null` (empty string in CSV) with `status = "not_available"`. January 2012 S-NPP carries `partial_period`; missing annual CSVs yield `missing_input`; present CSVs with zero detections in a month yield `0` with `no_detections_recorded` and `observation_coverage = "unknown"`.

## Backend Handoff & Integrity Verification

Do not pass normalized CSVs into `import_firms --data-dir` (which expects raw FIRMS schemas with `acq_date`/`acq_time`). Backend ingestion of M1 preparation summaries uses `build_baseline_series --from-pipeline /data/processed/monthly`, preserving `not_available`/`missing_input` nulls rather than coercing missing history into zeros.

Verified totals across the 48 country CSVs: **292,589** normalized rows retained (`234,366` labeled `type 0`), generating **1,208** monthly calendar rows (`844` active observation rows, `1` S-NPP partial start month in `2012-01`, `363` pre-launch rows), with all 13 Python unit/integration tests passing.

## References

Variable semantics follow `data/raw/gabon/AttributesReadme.txt` and official [NASA FIRMS Documentation](https://firms.modaps.eosdis.nasa.gov/).
