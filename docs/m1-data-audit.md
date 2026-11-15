# M1 Lot 1 — Inventory and Data Quality Audit

Reproducible CLI command from repository root:

```powershell
python -m pipeline.inventory --input data/raw/gabon --output data/processed/audit
```

Using Python's standard library only, `pipeline.inventory` generates `data_manifest.json`, `quality_report.json`, and a Markdown summary. The manifest logs relative paths, byte sizes, SHA-256 hashes, column schemas, row counts, date spans, observed months, sensors, processing versions, and thermal types. The quality report checks missing required columns, malformed CSV rows, invalid/unpadded dates or times, out-of-bounds WGS84 coordinates, non-finite numbers, confidence/type domain compliance, exact duplicates, and filename-vs-date mismatches without ever mutating raw inputs.

Schema checks follow NASA FIRMS `AttributesReadme.txt` inside `data/raw/gabon/`: required numeric columns are `brightness`, `bright_t31`, `scan`, `track`, and `frp` for MODIS, and `bright_ti4`, `bright_ti5`, `scan`, `track`, and `frp` for VIIRS. Confidence checks enforce MODIS numeric `0–100` and VIIRS categorical `l` / `n` / `h`. Standard (`SP`) vs near-real-time (`NRT`) distinction comes from FIRMS metadata and `version` attributes rather than filenames alone.

Source coordinates use WGS84 geographic projection. Without external polygon clipping, M1 checks strictly verify valid latitude/longitude bounds, keeping unobserved months flagged as `unknown` rather than asserting complete observation coverage or zero fire activity.

Note that NASA FIRMS issued a June 15, 2025 notice regarding type `0`/`2` classification on specific VIIRS `Vxx14IMGML` Collection 2 processing versions (1/2 vs reprocessed version 3); `pipeline.inventory` retains original values transparently without speculative re-classification. Source: [NASA FIRMS Outage Notice](https://firms.modaps.eosdis.nasa.gov/content/notifications/firms/outages.html).

JSON outputs are deterministically sorted with no machine-specific execution timestamps or absolute paths.

## Initial Archive Audit Results

Executed across **48 CSV files (`292,589` total rows)**:
- **MODIS**: `59,282` detections (`26` annual CSVs, `2000–2025`)
- **VIIRS S-NPP**: `147,745` detections (`14` annual CSVs, `2012–2025`)
- **VIIRS NOAA-20**: `85,562` detections (`8` annual CSVs, `2018–2025`)

All totals matched independent CSV verification: zero missing required columns, zero empty required values, zero malformed CSV lines, zero invalid coordinates or non-finite numerics, zero out-of-domain confidence/type/daynight flags, zero year mismatches, and zero exact intra/inter-file duplicates detected. SHA-256 checksums across all 48 source files remained unchanged before and after processing.

Unit tests (`python -m unittest discover -s tests -v`) pass and verify empty/missing inputs, product schemas, confidence ranges, duplicates, non-finite floats, unpadded `HHMM` times, raw folder write-protection, and deterministic outputs.
