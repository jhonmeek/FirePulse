# Guide d'intervention équipe — FirePulse (`M1 / M2 / M3`)

Ce document explique **ce que le backend fait déjà**, **ce qui est volontairement provisoire**, et **où M1 et M3 doivent intervenir** sans marcher sur le code backend.

---

## Pour M1 — Data & Science

### Ce qui existe déjà côté backend (socle provisoire de déblocage)
Pour que la base PostGIS et l'API servent de vraies données dès H12, M2 a intégré une **première version fonctionnelle** dans deux commandes Django :

1. [backend/apps/observations/management/commands/import_firms.py](../backend/apps/observations/management/commands/import_firms.py)
   - Normalise `MODIS`, `VIIRS S-NPP` et `VIIRS NOAA-20` (`brightness_mir`, `brightness_tir`, `confidence_tier`, `hotspot_type`, `is_nrt`, hash SHA-256).
   - Construit le masque statique `0.05°` (`StaticFlareMaskCell`) : règle actuelle `type23_count >= 20 OR active_months_snpp >= 48` (`183` cellules détectées au Gabon).
   - Agrège `GridCellMonth` (`0.25°`) pour `filter_static=True` (`hotspot_type = 0 AND NOT is_static_masked`) et `filter_static=False`.
2. [backend/apps/harmonization/management/commands/build_baseline_series.py](../backend/apps/harmonization/management/commands/build_baseline_series.py)
   - Train `2012-02` → `2019-12`, Test hors échantillon `2020-01` → `2025-12` (`72` mois).
   - Compare `naive`, `global_ratio`, `ols_linear`, `power_law_log1p`, `terra_only_power_law` et calcule `conformal_q80_log` / `conformal_q80_terra_log` + ratio pont `noaa20_to_snpp_ratio` (`2019–2025`).
   - Reconstitue les séries selon 4 régimes : `partial_year` (`2000-11/12`), `modis_terra_only` (`2001-01..2002-06`), `modis_terra_aqua` (`2002-07..2012-01`), `viirs_snpp_observed` (`2012-02..2026-10`), `viirs_noaa20_bridge` (`2026-11+`).
   - Calcule les médianes + IQR (`2001–2025`) et anomalies `%` / absolues.

> **Tu gardes la main scientifique totale :** considère ces scripts Django comme un *baseline de démonstration* sur `2000–2025`, pas comme une vérité figée.

### Où M1 doit intervenir en priorité
Tu travailles dans **`pipeline/`** et **`data/processed/`** (sans avoir besoin de modifier les vues Django) :

1. **Complément 2026 YTD + NRT (absent de la base actuelle) :**
   - Aujourd'hui seuls les 48 CSV `2000–2025` sont dans `data/raw/gabon/`.
   - Récupérer janvier–octobre 2026 + les fichiers récents NRT (`NOAA-20` post-coupure S-NPP du `2026-11-02`), vérifier le format de nommage (`modis_*`, `viirs-snpp_*`, `viirs-jpss1_*` / `viirs-noaa20_*`, inclure `nrt` dans le nom ou `version` pour marquer `is_nrt=true`) afin que `import_firms` les ingère proprement.
2. **Validation scientifique & cas limites :**
   - **Provinces à faible signal / bruitées :** ex. sur `GA-6` avec masque statique, `power_law_log1p` atteint `R² = 0.6876` (contre `0.9189` au national `GA`), et les sous-régions avec `< 24` paires actives sur le train héritent automatiquement des paramètres nationaux `GA`. Valider si une calibration hiérarchique ou nationale est préférable pour certaines provinces.
   - **Zones dessinées (`bbox` / `polygon`) :** dans [views.py](../backend/apps/api/views.py), `_custom_area_calendar` agrège `GridCellMonth` et applique la courbe nationale `GA`, mais laisse **`ci_low: null`**, **`ci_high: null`** et **`baseline_iqr: null`**. Définir la formule d'incertitude adaptée (et le rôle du modèle spatial sur cellules actives `0.25°`).
   - **Seuils de masque statique & `B=0` :** vérifier `>= 20` / `>= 48` mois et les cas de mois sans feu historique (`baseline_median = 0`).
3. **Documentation jury :**
   - Rédiger `docs/methodology.md` et `docs/limitations.md`.
4. **Livraison vers M2 :**
   - Déposer tes paramètres finaux / séries validées dans `data/processed/` (JSON/CSV) et prévenir M2 pour brancher l'import (`--from-pipeline`) dans `build_baseline_series.py`.

---

## Pour M3 — Frontend / UX

### Accès direct à l'API locale (aucun Python à toucher)
- **URL de base :** `http://localhost:8000/api/v1/`
- **CORS :** déjà autorisé pour `http://localhost:5173` et `http://127.0.0.1:5173`.
- **Contrat exact :** voir [docs/api-contract.json](api-contract.json) (mis à jour pour coller ligne pour ligne aux réponses réelles de [views.py](../backend/apps/api/views.py)).

### Commandes de test rapides (`curl`)

```bash
# Liste des régions (code: "GA", "GA-1".."GA-9") - ajouter ?include_geom=false pour menu léger
curl "http://localhost:8000/api/v1/regions/?include_geom=false"

# Série mensuelle Gabon entier (avec masque torchères actif)
curl "http://localhost:8000/api/v1/calendar/?region=GA&filter_static=true"

# Zone libre BBox (médianes 2001-2025 conservées même si start/end sont filtrés)
curl "http://localhost:8000/api/v1/calendar/?bbox=10.5,-3.0,12.5,-1.0&start=2024-06&end=2024-09"

# Zone libre Polygone GeoJSON (URL-encodé)
curl -G "http://localhost:8000/api/v1/calendar/" --data-urlencode 'polygon={"type":"Polygon","coordinates":[[[10.5,-3.0],[12.5,-3.0],[12.5,-1.0],[10.5,-1.0],[10.5,-3.0]]]}'

# Anomalies et médianes de référence par mois (1..12)
curl "http://localhost:8000/api/v1/anomalies/?region=GA&top_n=10"

# Grille GeoJSON 0.25° pour un mois donné + cellules statiques masquées
curl "http://localhost:8000/api/v1/hotspots/?mode=grid&month=2024-08&include_static_cells=true"

# Points bruts zoomés (exige month OU bbox, limit max 5000)
curl "http://localhost:8000/api/v1/hotspots/?mode=points&month=2024-08&bbox=10.5,-3.0,12.5,-1.0&limit=500"

# Onglet Méthodologie (paramètres + métriques out-of-sample + limites)
curl "http://localhost:8000/api/v1/methodology/?region=GA"

# Téléchargement CSV
curl "http://localhost:8000/api/v1/export/?region=GA&start=2024-01&end=2024-12"
```

### Particularités et limites actuelles à connaître côté UI
1. **`/calendar/?bbox=...` ou `?polygon=...` :**
   - `ci_low`, `ci_high` et `baseline_iqr` sont actuellement **`null`** (prévoir de masquer gracieusement le ruban d'incertitude sur zone custom en attendant M1, ou d'afficher `uncertainty_note`).
   - Les codes d'identification retournés sont `region.id = "CUSTOM_BBOX"` ou `"CUSTOM_POLYGON"`.
2. **`/hotspots/` :**
   - `mode=grid` renvoie une feature **par `(cell_id, month)`**. **Toujours passer `month=YYYY-MM`** (ou un `bbox` + `month`) pour afficher la carte d'un mois donné sans atteindre le plafond `limit` (`2000` par défaut, max `5000`).
   - `mode=points` renvoie une erreur `400` si ni `month` ni `bbox` n'est fourni.
   - Si `include_static_cells=true`, la réponse mélange des features `properties.layer = "grid_cell_month"` (ou `"hotspot_point"`) et `"static_flare_mask"` : filtrer sur `properties.layer` côté MapLibre.
3. **`/anomalies/` et `/export/` :**
   - Supportent uniquement `region` (`GA`, `GA-1`..`GA-9`) à ce stade. Si M3 a besoin d'exporter ou classer les anomalies d'un `bbox`/`polygon` ou d'exporter `dataset=points`, demander à M2 (évolution prévue en H12–H24).
4. **`/methodology/` :**
   - Les métriques comparatives (`naive`, `global_ratio`, `ols_linear`, `power_law_log1p`, `terra_only_power_law`) se trouvent sous `active_run.metrics.models_out_of_sample` (ou `null` si la sous-région a hérité du modèle national).

---

## Pour M2 — Backend / Geo / Infra

- **Port DB hôte :** `5433` dans `.env.example` (conteneur `db:5432`).
- **Commandes clés :**
  - `load_regions.py` : charge [data/boundaries/gabon_adm0.geojson](../data/boundaries/gabon_adm0.geojson) + [gabon_adm1.geojson](../data/boundaries/gabon_adm1.geojson) (avec `.strip()` sur les noms contenant des tabulations comme `Ogooué-Ivindo`).
  - `import_firms.py` : déduplication fichier (`ImportBatch.file_sha256`) + ligne (`HotspotObservation.original_hash`). Attention côté SQL : `ROUND()` Postgres exige un cast `::numeric`.
  - `build_baseline_series.py` : conserve `2012-01` en régime `modis_terra_aqua` (`SNPP_START = 2012-02-01`) tout en affichant le `viirs_snpp_count` brut présent dans le CSV 2012.
- **Chantiers H12–H24 purement M2 :**
  - Support `bbox` / `polygon` (+ `dataset=points` éventuel) sur `/api/v1/export/` et `/api/v1/anomalies/`.
  - Option `--from-pipeline` dans `build_baseline_series.py` pour ingérer les sorties `data/processed/` validées par M1.
  - Cache / indexation si besoin + configuration production (`gunicorn`, `ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS`, snapshot DB).
