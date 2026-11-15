# Scientific and Technical Limitations

## What the Data Support

Source files contain thermal anomaly detections observed from orbit. Detection counts do **not** measure distinct fires, burned area in hectares, or exhaustive ground activity. Zero detections does not prove the absence of fire on the ground.

## Spatial Coverage & Geography

- Les CSV de détections et leurs empreintes ne suffisent pas à mesurer tous les passages exploitables, les nuages ou les pertes de données. La couverture d'observation reste inconnue dans les agrégats M1 de préparation.
- La disponibilité mensuelle du backend est déduite des bornes `min_date`/`max_date` des lots importés : un mois sans détection à l'intérieur d'un lot est un zéro recensé, un mois hors de toute borne reste une entrée manquante (`null`, régime `missing`) et n'est plus transformé en zéro. Ces bornes ne prouvent pas une couverture satellite complète du mois.
- Les archives initiales s'arrêtent à 2025. Aucune donnée 2026 n'est ajoutée implicitement, et aucun comptage récent n'est extrapolé pour remplir cette année.
- La sélection nationale M1 reprend le fichier pays fourni. Le découpage par provinces ou polygones personnalisés demande des frontières versionnées et une règle de sélection spatiale ; il n'est pas validé par ce lot.
- Une cellule préagrégée intersectant un polygone ne permet pas de connaître exactement le nombre de points dans la portion intersectée.
- Raw FIRMS CSVs and file manifests cannot capture every satellite overpass, heavy cloud obstruction, dense smoke plume, or telemetry gap. Observation completeness remains `unknown` in M1 preparation aggregates.
- Standard archive files stop at December 2025 (`2025-12`). No 2026 observations are fabricated or extrapolated to fill incomplete years. The NOAA-20 bridge is calibrated over shared historical overlap but not yet validated on live 2026 detections; post-2026 continuity must be clearly framed as a calibrated projection rather than already-observed 2026 telemetry.
- Country-level M1 counts rely on NASA country CSV extracts (`GA` scope), whereas M2 PostGIS API endpoints apply exact administrative polygon boundaries (`gabon_adm0.geojson`, `gabon_adm1.geojson`).
- A pre-aggregated `0.25°` grid cell intersecting a custom polygon or provincial boundary cannot exactly resolve sub-cell point allocations without querying underlying point records.

## Satellite Products & Filtering

- Spatial resolutions, spectral bands, orbital overpass times, and detection algorithms differ between MODIS and VIIRS; aligning column names does not equalize physical radiometry.
- Original confidence ratings are preserved, but a "nominal" detection in MODIS is not probabilistically identical to a "nominal" detection in VIIRS.
- FIRMS `hotspot_type = 0` denotes presumed vegetation/other thermal anomalies from upstream product classification, not ground-truthed validation. Not all persistent sources are oil flares, and spatial masks can exclude nearby vegetation fires.
- A June 15, 2025 NASA FIRMS outage/processing notice affects `0`/`2` classification labels on certain VIIRS Collection 2 processing versions (1/2 vs reprocessed v3); rows are preserved as delivered without heuristic label overrides.
- When evaluated retrospectively across `2000–2025`, the `0.05°` mask flags `183` persistent candidate cells. Within national PostGIS `GA` borders (`285,013` detections), the `38.4%` excluded share (`109,513` detections) combines `57,934` type-2/3 detections (`20.3%`) and `51,579` type-0 detections falling inside those `183` persistent cells (`18.1%`). These `183` cells represent `0.05°` spatial grids (~5.5 km) rather than individually ground-verified industrial facilities.
- M1 scripts follow the CSV country perimeter while M2 applies exact PostGIS border geometries; minor count differences (`292,589` raw rows vs `285,013` strict interior `GA` detections) reflect near-border / offshore coastal geometry filtering.

## Harmonization & Uncertainty

- Conformal prediction intervals derived directly from the test window (`v2.0` live baseline) conflate interval calibration with evaluation (`79.2%` leaky empirical coverage). The independent validation protocol in `front-bis/scripts/validate_harmonization.py` addresses this explicitly by freezing the candidate-source mask on `2000–2019`, calibrating `q80` on `2018–2019`, and measuring true blind coverage (`63.9%`) on `2020–2025`.
- User-drawn custom polygons (`bbox` / `polygon`) display `baseline_iqr` `[p25, p75]` over `2001–2025`, while predictive uncertainty bands remain `null` until region-specific spatial interval calibration is evaluated.

## Operational Scope

- All pipelines run deterministically on local CSV archives without authenticating to private endpoints or committing NASA API keys.
- Prototype outputs serve as reproducible decision-support visualizations; future releases aim to integrate physical Fire Radiative Power (`FRP`), MCD64A1/VNP64A1 burned-area products, and periodic mask updates.

References: [`methodology.md`](methodology.md), [`m1-data-audit.md`](m1-data-audit.md), [`m1-normalization.md`](m1-normalization.md), and [NASA FIRMS Outages & Notices](https://firms.modaps.eosdis.nasa.gov/content/notifications/firms/outages.html).
