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
   - **Zones dessinées (`bbox` / `polygon`) :** dans [views.py](../backend/apps/api/views.py), [services.py](../backend/apps/api/services.py) agrège `GridCellMonth`, calcule désormais les médianes + `baseline_iqr` `[p25, p75]` sur `2001–2025`, et applique la courbe nationale `GA`, mais laisse **`ci_low: null`** et **`ci_high: null`**. Définir la formule d'incertitude adaptée (et le rôle du modèle spatial sur cellules actives `0.25°`).
   - **Seuils de masque statique & `B=0` :** vérifier `>= 20` / `>= 48` mois et les cas de mois sans feu historique (`baseline_median = 0`).
3. **Documentation jury :**
   - Rédiger `docs/methodology.md` et `docs/limitations.md`.
4. **Livraison directe vers PostGIS (`--from-pipeline`) :**
   - Le chargeur [build_baseline_series.py](../backend/apps/harmonization/management/commands/build_baseline_series.py) accepte désormais **deux formats** :
     1. **Artefacts mensuels M1 actuels (`/data/processed/monthly`)** : dossier, `manifest.json` (`firepulse-monthly` avec vérification SHA-256), `calendar.json` (`firepulse-monthly-calendar`), ou `monthly_counts.csv`. Pivote `count_type0_candidate` (`filter_static=True`) et `count_raw` (`filter_static=False`), conserve les `null` (`not_available` / `missing_input`) sans les transformer en `0`, calibre si `harmonized_value` est `null` et journalise la provenance exacte dans `metrics_json.m1_provenance` (y compris l'absence de masque statique `0.05°`).
     2. **Bundle calibré M1 JSON (`/data/processed/calibration/pipeline_bundle.json`)** :

```json
{
  "method_name": "m1_validated_power_law",
  "method_version": "v2.1-m1",
  "reference_scale": "VIIRS_375m_SNPP_equiv",
  "regions": [
    {
      "region": "GA",
      "filter_static": true,
      "params": {"power_law_p": 0.9438, "power_law_q": 1.6529},
      "metrics": {"test_months": 72, "models_out_of_sample": {"power_law_log1p": {"r2": 0.92}}},
      "baselines": [{"month_num": 8, "baseline_median": 1704.48, "iqr_p25": 1119.5, "iqr_p75": 2187.59, "reference_years_count": 25}],
      "series": [{"month": "2024-08", "harmonized_value": 3049.0, "ci_low": 2900.0, "ci_high": 3200.0, "sensor_regime": "viirs_snpp_observed", "coverage_status": "complete_sp"}]
    }
  ]
}
```
   - Si `"series"` est omis, le backend reconstruit les séries à partir des comptages PostGIS + tes `"params"` ; si `"series"` (et optionnellement `"baselines"`) est fourni, tes valeurs exactes remplacent la baseline provisoire dans une transaction atomique.

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

# Anomalies et médianes de référence par mois (region, bbox ou polygon)
curl "http://localhost:8000/api/v1/anomalies/?region=GA&top_n=10"
curl "http://localhost:8000/api/v1/anomalies/?bbox=10.5,-3.0,12.5,-1.0&top_n=5"

# Grille GeoJSON 0.25° : par mois OU agrégée par cellule (agg=cell) sur une plage de dates
curl "http://localhost:8000/api/v1/hotspots/?mode=grid&month=2024-08&include_static_cells=true"
curl "http://localhost:8000/api/v1/hotspots/?mode=grid&agg=cell&start=2024-06&end=2024-09&bbox=10.5,-3.0,12.5,-1.0"

# Points bruts zoomés (exige month, start/end, bbox ou polygon ; limit max 5000)
curl "http://localhost:8000/api/v1/hotspots/?mode=points&month=2024-08&bbox=10.5,-3.0,12.5,-1.0&limit=500"

# Onglet Méthodologie (paramètres + métriques out-of-sample + limites)
curl "http://localhost:8000/api/v1/methodology/?region=GA"

# Téléchargement CSV (séries régionales/custom ou points filtrés)
curl "http://localhost:8000/api/v1/export/?region=GA&start=2024-01&end=2024-12"
curl "http://localhost:8000/api/v1/export/?bbox=10.5,-3.0,12.5,-1.0"
curl "http://localhost:8000/api/v1/export/?dataset=points&region=GA&month=2024-08&limit=1000"
```

### Particularités et limites actuelles à connaître côté UI
1. **`/calendar/?bbox=...` ou `?polygon=...` :**
   - `baseline_iqr` (`[p25, p75]`) est maintenant calculé sur `2001–2025`, mais `ci_low` et `ci_high` restent **`null`** en zone custom (prévoir de masquer gracieusement le ruban d'incertitude ou afficher `uncertainty_note`).
   - Les codes d'identification retournés sont `region.id = "CUSTOM_BBOX"` ou `"CUSTOM_POLYGON"`.
2. **`/hotspots/` :**
   - `mode=grid&agg=month` (défaut) renvoie une feature **par `(cell_id, month)`** : passer `month=YYYY-MM` pour une carte mensuelle rapide.
   - `mode=grid&agg=cell` agrège par cellule `0.25°` (`layer = "grid_cell_summary"`) sur une fenêtre (`start`/`end` ou `month`) : idéal pour charger tout le Gabon ou une saison en un seul appel (`< 500` cellules).
   - `mode=points` renvoie une erreur `400` si ni `month`/`start`/`end` ni `bbox`/`polygon` n'est fourni.
   - Si `include_static_cells=true`, la réponse mélange `layer = "grid_cell_month"` / `"grid_cell_summary"` / `"hotspot_point"` et `"static_flare_mask"` : filtrer sur `properties.layer` côté MapLibre.
3. **`/export/` :**
   - `dataset=series` (défaut) et `dataset=points` supportent tous deux `region`, `bbox` et `polygon`. `dataset=points` exige au moins un filtre temporel (`month` / `start` / `end`) ou spatial (`bbox` / `polygon`), plafonné à `limit <= 50000`.
4. **`/methodology/` :**
   - Les métriques comparatives (`naive`, `global_ratio`, `ols_linear`, `power_law_log1p`, `terra_only_power_law`) se trouvent sous `active_run.metrics.models_out_of_sample` (ou `null` si la sous-région a hérité du modèle national).

---

## Pour M2 — Backend / Geo / Infra

- **Port DB hôte :** `5433` dans `.env.example` (conteneur `db:5432`).
- **Commandes clés :**
  - `load_regions.py` : charge [data/boundaries/gabon_adm0.geojson](../data/boundaries/gabon_adm0.geojson) + [gabon_adm1.geojson](../data/boundaries/gabon_adm1.geojson) (avec `.strip()` sur les noms contenant des tabulations comme `Ogooué-Ivindo`).
  - `import_firms.py` : déduplication fichier (`ImportBatch.file_sha256`) + ligne (`HotspotObservation.original_hash`) et détection NRT par colonne `version` en plus du nom de fichier. Attention côté SQL : `ROUND()` Postgres exige un cast `::numeric`.
  - `build_baseline_series.py` : conserve `2012-01` en régime `modis_terra_aqua` (`SNPP_START = 2012-02-01`) et supporte `--from-pipeline <bundle.json>` pour ingérer les sorties M1.
- **Chantiers H24–H34 M2 (en place) :**
  - Cache API v1 avec invalidation inter-processus (`apps/api/cache.py`), compression `GZipMiddleware`, requêtes `AsGeoJSON` PostGIS (`views.py`), détection `mixed_sp_nrt` / `nrt_only` 2026 (`build_baseline_series.py`) et `/health/` structuré (`503` si DB indisponible).
  - Déploiement HTTPS (`docker-compose.prod.yml`, `deploy/Caddyfile`, `gunicorn` par défaut dans `backend/Dockerfile`).
  - Plan de secours démo : `python manage.py export_demo_snapshot`, `scripts/db_backup.sh` et `scripts/db_restore.sh`.
