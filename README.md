# FirePulse — *One Planet. One Fire History.*

Plateforme d'harmonisation multi-capteurs des détections de points chauds **NASA FIRMS** (**MODIS C6.1 Terra/Aqua**, **VIIRS Suomi-NPP 375m**, **VIIRS NOAA-20 375m**) sur le **Gabon (2000–2025+)**, réalisée dans le cadre du défi **NASA Space Apps 2026 — Harmonization of MODIS and VIIRS Hot Spots**.

> **Important :** ce dépôt sépare strictement **Data & Science (`pipeline/` — M1)**, **Backend / PostGIS / API (`backend/` — M2)** et **Frontend (`frontend/` — M3)**. Voir [docs/HANDOFF.md](docs/HANDOFF.md) pour savoir exactement où chacun doit intervenir.

---

## État actuel du dépôt (jalon M2 Backend / Geo)

- **Base PostgreSQL 16 + PostGIS 3.4** opérationnelle via Docker Compose (`firepulse_db`).
- **48 fichiers NASA FIRMS du Gabon (2000–2025)** ingérés de façon idempotente : `292 589` détections (`modis`, `viirs-snpp`, `viirs-noaa20`).
- **10 régions chargées** depuis [data/boundaries/](data/boundaries/) : `GA` (Gabon entier) et `GA-1` à `GA-9` (9 provinces).
- **Grille spatiale `0.25°` (`42 482` lignes)** + **masque statique torchères `0.05°` (`183` cellules)** + **séries harmonisées (`6 011` lignes)** disponibles via **8 endpoints REST `/api/v1/`**.

---

## Démarrage rapide (Backend + PostGIS)

### 1. Préparer les variables d'environnement locales

```bash
cp .env.example .env
```

> **Note port PostgreSQL :** `.env.example` expose PostgreSQL sur le port hôte **`5433`** (`POSTGRES_HOST_PORT=5433` → conteneur `5432`) pour éviter tout conflit avec un PostgreSQL déjà installé localement. Modifie `POSTGRES_HOST_PORT` uniquement dans ton `.env` local. **Ne jamais commiter de clés `FIRMS_MAP_KEY` ou `EARTHDATA_TOKEN`.**

### 2. Lancer PostgreSQL/PostGIS + Django

```bash
docker compose up -d --build
```

Les migrations Django (`observations`, `harmonization`) s'appliquent automatiquement au démarrage du conteneur `backend` sur `http://localhost:8000`.

### 3. Charger les frontières, les données FIRMS et les séries baseline

```bash
docker compose exec backend python manage.py load_regions
docker compose exec backend python manage.py import_firms
docker compose exec backend python manage.py build_baseline_series
```

Options utiles de `import_firms` :
- `python manage.py import_firms` : importe uniquement les nouveaux CSV (idempotent via SHA-256).
- `python manage.py import_firms --rebuild-only` : recalcule uniquement le masque statique `0.05°` et la grille `0.25°`.
- `python manage.py import_firms --data-dir /data/raw/<dossier>` : pointe vers un autre dossier monté dans `./data`.

### 4. Vérifier que tout tourne

```bash
docker compose exec backend python manage.py test -v 2
curl http://localhost:8000/api/v1/health/
```

Réponse attendue sur `/api/v1/health/` : `"status": "ok"`, `"database": "connected"` et les compteurs (`regions: 10`, `hotspots: 292589`, `grid_cell_months: 42482`, `harmonized_months: 6011`).

---

## Qui touche à quoi ? (Frontières d'équipe)

| Rôle | Dossiers dédiés | Périmètre | Guide détaillé |
| :--- | :--- | :--- | :--- |
| **M1 — Data & Science** | `pipeline/`, `data/processed/`, `docs/methodology.md`, `docs/limitations.md` | Données **2026 YTD / NRT**, pont NOAA-20 post-`2026-11-02`, validation scientifique, provinces bruitées, incertitude `bbox`/`polygon` | [Section M1](docs/HANDOFF.md#pour-m1--data--science) |
| **M2 — Backend / Geo / Infra** | `backend/`, `docker-compose.yml`, `data/boundaries/`, `docs/api-contract.json` | Modèles PostGIS, ETL idempotent, API `/api/v1/*`, requêtes spatiales, export CSV, déploiement/backup | [Section M2](docs/HANDOFF.md#pour-m2--backend--geo--infra) |
| **M3 — Frontend / UX / Pitch** | `frontend/` | UI Vue 3/TypeScript/Vite/Tailwind/Pinia, calendrier heatmap accessible, graphes comparatifs ECharts, carte MapLibre, pitch | [Section M3](docs/HANDOFF.md#pour-m3--frontend--ux) |

---

## Arborescence utile

```text
modis_viirs/
├── data/
│   ├── raw/gabon/               # 48 CSV NASA FIRMS 2000–2025 + AttributesReadme.txt
│   ├── boundaries/              # gabon_adm0.geojson (GA) + gabon_adm1.geojson (GA-1..GA-9)
│   └── processed/               # Sorties scientifiques propres (espace de livraison M1 -> M2)
├── backend/
│   ├── config/                  # Settings Django + CORS (localhost:5173) + URLs (/api/v1/)
│   └── apps/
│       ├── observations/        # Modèles Region, ImportBatch, HotspotObservation, StaticFlareMaskCell, GridCellMonth
│       │                        # + commandes load_regions, import_firms
│       ├── harmonization/       # Modèles CalibrationRun, MonthlyBaseline, HarmonizedMonthSeries
│       │                        # + commande build_baseline_series
│       └── api/                 # Endpoints REST v1 (views.py, urls.py) + tests (tests.py)
├── docs/
│   ├── api-contract.json        # Contrat API v1 synchronisé avec backend/apps/api/views.py
│   └── HANDOFF.md               # Fiche d'intervention M1 / M3 / M2 + limites actuelles
├── docker-compose.yml           # PostGIS 16-3.4 (hôte 5433) + Django (:8000)
├── .env.example                 # Modèle de configuration locale
└── Guide_FirePulse_NASA_Space_Apps_2026_v2.md
```

---

## Endpoints API v1 (`http://localhost:8000/api/v1/`)

| Endpoint | Rôle |
| :--- | :--- |
| `GET /api/v1/health/` | État DB, version PostGIS et compteurs |
| `GET /api/v1/regions/` | Liste des régions (`GA`, `GA-1`..`GA-9`), `bbox` et GeoJSON (`?include_geom=true\|false`) |
| `GET /api/v1/coverage/` | Disponibilité temporelle et niveaux (`SP` / `NRT`) par capteur + coupure S-NPP `2026-11-02` |
| `GET /api/v1/calendar/` | Séries brutes vs harmonisées, médianes & anomalies (`?region=`, `?bbox=`, `?polygon=`, `?start=`, `?end=`, `?filter_static=`) |
| `GET /api/v1/anomalies/` | Médianes mensuelles `[p25, p75]` et top anomalies positives/négatives (`?region=`, `?filter_static=`, `?top_n=`) |
| `GET /api/v1/hotspots/` | FeatureCollection GeoJSON grille `0.25°` (`mode=grid`) ou points (`mode=points`) + cellules statiques (`include_static_cells=true`) |
| `GET /api/v1/methodology/` | Paramètres calibrés, métriques hors échantillon `2020–2025`, stats masque statique, limites |
| `GET /api/v1/export/` | Export CSV téléchargeable avec métadonnées de régime et couverture |

Contrat détaillé : [docs/api-contract.json](docs/api-contract.json).

## Pipeline M1 — inventaire et qualité

Pipeline scientifique pour l'analyse et l'harmonisation des détections de points chauds MODIS et VIIRS au Gabon.

## État du développement

Le premier lot implémente l'inventaire reproductible et les contrôles de qualité des CSV présents dans `data/raw/gabon`. Les données brutes restent inchangées. Les coefficients et benchmarks du guide v2 ne sont pas encore validés par ce pipeline.

## Prérequis

Python 3.10 ou plus récent. Le lot d'inventaire utilise uniquement la bibliothèque standard, sans installation de dépendance ni clé NASA.

Depuis la racine du dépôt :

```powershell
python -m unittest discover -s tests -v
python -m pipeline.inventory --input data/raw/gabon --output data/processed/audit
```

Le manifeste et le rapport qualité JSON sont des résultats d'audit, pas des séries harmonisées utilisables comme résultats scientifiques finaux. Voir `docs/m1-data-audit.md` pour les contrôles, formats, limites et instructions de reproduction.

## Sources et limites

- Données fournies dans le dépôt, accompagnées de `data/raw/gabon/AttributesReadme.txt`.
- [NASA FIRMS — documentation et ressources](https://firms.modaps.eosdis.nasa.gov/).
- [NASA FIRMS — différences entre produits et disponibilité](https://firms.modaps.eosdis.nasa.gov/content/academy/data_api/firms_api_use.html).
- [NASA FIRMS — anomalies connues et interruptions](https://firms.modaps.eosdis.nasa.gov/content/notifications/firms/outages.html).

La présence de détections ne permet pas de déduire une couverture d'observation complète. Le fichier pays ne remplace pas une validation des frontières géographiques. Un point chaud n'est pas nécessairement un incendie distinct.

## Contributions M1

Travail sur `m1/data-science`, contrôles et revue des changements avant proposition d'intégration dans `main`. Les artefacts d'audit sont séparés des fichiers bruts. Les étapes suivantes sont la normalisation, les agrégations mensuelles et l'évaluation de l'harmonisation.
