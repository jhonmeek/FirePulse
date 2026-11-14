# FirePulse — *One Planet. One Fire History.*

Plateforme d'harmonisation multi-capteurs des détections de points chauds **NASA FIRMS** (**MODIS C6.1 Terra/Aqua**, **VIIRS Suomi-NPP 375m**, **VIIRS NOAA-20 375m**) sur le **Gabon (2000–2025+)**, réalisée dans le cadre du défi **NASA Space Apps 2026 — Harmonization of MODIS and VIIRS Hot Spots**.

> **Important :** ce dépôt sépare strictement **Data & Science (`pipeline/` — M1)**, **Backend / PostGIS / API (`backend/` — M2)** et **Frontend (`frontend/` — M3)**. Voir [docs/HANDOFF.md](docs/HANDOFF.md) pour savoir exactement où chacun doit intervenir.

---

## État actuel du dépôt

### Backend / Geo (M2)

- **Base PostgreSQL 16 + PostGIS 3.4** opérationnelle via Docker Compose (`firepulse_db`).
- **48 fichiers NASA FIRMS du Gabon (2000–2025)** ingérés de façon idempotente : `292 589` détections (`modis`, `viirs-snpp`, `viirs-noaa20`).
- **10 régions chargées** depuis [data/boundaries/](data/boundaries/) : `GA` (Gabon entier) et `GA-1` à `GA-9` (9 provinces).
- **Grille spatiale `0.25°` (`42 482` lignes)** + **masque statique torchères `0.05°` (`183` cellules)** + **séries harmonisées (`6 011` lignes)** disponibles via **8 endpoints REST `/api/v1/`**.

### Frontend (M3) — jalon H12–H24

- **Vue 3 + TypeScript + Vite + Tailwind 4 + Pinia + ECharts** dans [frontend/](frontend/) ; `maplibre-gl` installé pour la carte (H24–H34).
- **Types TypeScript** ([frontend/src/types/api.ts](frontend/src/types/api.ts)) alignés sur [docs/api-contract.json](docs/api-contract.json) v2.2.0.
- **Flux réel bout-en-bout vérifié** : UI branchée sur l'API locale (`GA` + 9 provinces, bascule torchères), requêtes `/api/v1/*` en 200.
- **Onglet *Explorer*** :
  - barre de contrôle : zone (Gabon / provinces), plage d'années, couleur *Intensité* / *Anomalie*, toggle « Exclure torchères » avec **compteur de détections masquées** (les deux séries, avec et sans filtre, sont chargées ensemble : bascule instantanée) ;
  - bandeau des régimes capteurs (Terra seul → MODIS reconstitué → VIIRS S-NPP → pont NOAA-20) avec la plage affichée en surbrillance ;
  - **calendrier Années × Mois accessible** : palettes adaptées aux daltoniens (YlOrRd en racine carrée pour l'intensité, PuOr divergente pour l'anomalie, orange = au-dessus de la médiane), mois provisoires/NRT hachurés, mois sans donnée en pointillés, navigation clavier complète, libellé lecteur d'écran par cellule ;
  - **panneau détail du mois** (survol/focus = aperçu, clic/Entrée = épinglé) : valeur harmonisée ± intervalle 80 %, médiane et IQR du même mois, anomalie (% ou écart absolu si médiane nulle), rang historique 2001–2025, régime, couverture, détections brutes par capteur ;
  - **graphe comparatif ECharts** : MODIS / VIIRS S-NPP / NOAA-20 bruts, série harmonisée et **bande d'incertitude conforme 80 %**, bouton *Avant / Après harmonisation*, repères des ruptures (Aqua 2002, VIIRS 2012), saut S-NPP/MODIS mesuré (≈ ×3,9 au Gabon), clic = sélection du mois. ECharts est chargé en différé (chunk séparé) ;
  - **anomalies** : saisonnalité de référence (médiane + IQR par mois, mois sélectionné en pointillés) et mois les plus au-dessus / en dessous de la médiane sur la plage affichée, cliquables.
- **Onglet *Méthodologie & preuve*** (critère H24 « moteur scientifique validé hors échantillon visible dans l'UI ») : benchmark hors échantillon `2020–2025` des 5 modèles (MAE, RMSE, biais, R², formules avec paramètres calibrés), gain du modèle retenu (au Gabon : −72 % de MAE vs naïf, −16 % vs ratio global, R² = 0,919), facteurs d'incertitude conformes, pont NOAA-20, masque torchères, limites documentées — le tout lu depuis `/api/v1/methodology/`.
- **Mode mocks** pour développer sans backend : générés depuis les CSV FIRMS réels en rejouant la chaîne baseline de M2. Comparés à l'API locale : identiques sans filtre ; avec filtre torchères, 37 comptages bruts diffèrent (bord de cellule du masque `0.05°`), écart harmonisé max 1,5 %.

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

Options utiles :
- `python manage.py import_firms` : importe uniquement les nouveaux CSV (idempotent via SHA-256).
- `python manage.py import_firms --rebuild-only` : recalcule uniquement le masque statique `0.05°` et la grille `0.25°`.
- `python manage.py import_firms --data-dir /data/raw/<dossier>` : pointe vers un autre dossier monté dans `./data`.
- `python manage.py build_baseline_series --from-pipeline /data/processed/monthly` : ingère directement les artefacts mensuels M1 (`calendar.json` ou `monthly_counts.csv` + vérification SHA-256 `manifest.json`) ou un bundle calibré M1 JSON (`regions`).

### 4. Vérifier que tout tourne

```bash
docker compose exec backend python manage.py test -v 2
curl http://localhost:8000/api/v1/health/
```

Réponse attendue sur `/api/v1/health/` : `"status": "ok"`, `"database": "connected"` et les compteurs (`regions: 10`, `hotspots: 292589`, `grid_cell_months: 42482`, `harmonized_months: 6011`).

Le workflow GitHub Actions ([.github/workflows/ci.yml](.github/workflows/ci.yml)) exécute automatiquement à chaque PR/push les tests Backend PostGIS (`manage.py test -v 2`), le pipeline M1 (`unittest`) et le build/tests Frontend (`type-check`, `vitest`, `vite build`).

### 5. Production HTTPS & plan de secours démo (`H24–H34` M2)

- **Stack production HTTPS (Gunicorn + Caddy) :** [docker-compose.prod.yml](docker-compose.prod.yml) + [deploy/Caddyfile](deploy/Caddyfile) (`DJANGO_SECRET_KEY=... docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build`).
- **Backup PostGIS + snapshot JSON hors ligne :**
  - `./scripts/db_backup.sh` : dump PostgreSQL/PostGIS (`pg_dump -Fc` + SHA-256) et export complet des réponses `/api/v1/` via `python manage.py export_demo_snapshot` dans `data/backups/`.
  - `./scripts/db_restore.sh data/backups/<fichier>.dump` : restauration vérifiée + contrôle `/api/v1/health/`.

---

## Démarrage rapide (Frontend)

Prérequis : **Node.js `^22.18` ou `>=24.12`**. Depuis `frontend/` :

```bash
npm install
npm run dev
```

L'application tourne sur `http://localhost:5173`.

### Mocks ou API réelle

| Mode | Activation | Source des données |
| :--- | :--- | :--- |
| **Mocks** (défaut en dev) | rien à faire | `frontend/src/mocks/*.json` — région `GA` uniquement ; provinces et zones libres renvoient une série vide |
| **API Django** | créer `frontend/.env.local` avec `VITE_USE_MOCKS=false` | `/api/v1` relayé par le proxy Vite vers `http://localhost:8000` (backend lancé, voir ci-dessus) |

Le build de production (`npm run build`) utilise toujours l'API réelle ; les mocks n'y sont pas inclus. Modèle de configuration : [frontend/.env.example](frontend/.env.example).

### Régénérer les mocks

Après une évolution des CSV de `data/raw/gabon/` ou de la chaîne baseline (nécessite `pandas`, `numpy`, `matplotlib`) :

```bash
py -3.12 scripts/generate_mocks.py
```

Puis reformater (le générateur écrit du JSON compact, les mocks versionnés sont formatés par Prettier) :

```bash
npm run format
```

`src/mocks/calendar_edge_cases.json` est **synthétique** (NRT, pont NOAA-20, médiane nulle, mois sans donnée) et sert uniquement à tester l'UI.

### Vérifications

```bash
npm run lint
npm run test:unit -- --run
npm run build
```

Les tests comparent les mocks aux clés et énumérations de `docs/api-contract.json` : toute évolution du contrat par M2 sans mise à jour de `src/types/api.ts` et des mocks fait échouer la suite. Ils couvrent aussi les utilitaires (palettes, rang, options du graphe, bande d'incertitude, classement des anomalies, compteur masqué, benchmark) et les composants (navigation clavier, sélection, hachures, bascule avant/après, méthodologie ; ECharts est remplacé par un double car jsdom n'a pas de canvas). Ils tournent toujours en mode mocks, même si `.env.local` pointe vers l'API.

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
FirePulse/
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
│       └── api/                 # Endpoints REST v1 (views.py, services.py, urls.py) + tests (tests.py)
├── pipeline/                    # Scripts scientifiques M1 (inventory.py, ...)
├── frontend/
│   ├── scripts/generate_mocks.py  # Mocks fidèles à l'API, générés depuis data/raw/gabon
│   └── src/
│       ├── types/api.ts         # Miroir TypeScript de docs/api-contract.json
│       ├── services/api.ts      # Client API + bascule mocks / API (VITE_USE_MOCKS)
│       ├── stores/filters.ts    # Pinia : zone, bbox, années, filtre torchères, couleur, mois sélectionné
│       ├── composables/         # useCalendar (historique complet, anti-réponse obsolète), useRegions
│       ├── utils/               # calendar.ts (matrice, palettes, rang), chart.ts (options ECharts),
│       │                        # anomalies.ts (saisonnalité, classement, compteur masqué), methodology.ts
│       ├── components/          # ControlBar, RegimeTimeline, CalendarHeatmap, MonthDetail,
│       │                        # ComparisonChart, AnomaliesPanel, MethodologyPanel
│       ├── mocks/               # JSON générés (GA) + cas limites synthétiques
│       └── __tests__/           # Validation des mocks contre le contrat
├── docs/
│   ├── api-contract.json        # Contrat API v1 synchronisé avec backend/apps/api/views.py
│   ├── HANDOFF.md               # Fiche d'intervention M1 / M3 / M2 + limites actuelles
│   └── m1-data-audit.md         # Lot M1 #1 — inventaire et contrôles qualité FIRMS
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
| `GET /api/v1/coverage/` | Disponibilité temporelle, versions (`product_versions`) et niveaux (`SP` / `NRT`) par capteur + coupure S-NPP `2026-11-02` |
| `GET /api/v1/calendar/` | Séries brutes vs harmonisées, médianes & anomalies (`?region=`, `?bbox=`, `?polygon=`, `?start=`, `?end=`, `?filter_static=`) |
| `GET /api/v1/anomalies/` | Médianes mensuelles `[p25, p75]` et top anomalies (`?region=`, `?bbox=`, `?polygon=`, `?start=`, `?end=`, `?filter_static=`, `?top_n=`) |
| `GET /api/v1/hotspots/` | FeatureCollection GeoJSON grille `0.25°` (`mode=grid`, `agg=month\|cell`) ou points (`mode=points`) sur `region`/`bbox`/`polygon` + `include_static_cells=true` |
| `GET /api/v1/methodology/` | Paramètres calibrés, métriques hors échantillon `2020–2025`, stats masque statique, limites |
| `GET /api/v1/export/` | Export CSV `dataset=series\|points` (`region`, `bbox`, `polygon`, filtres de dates) avec métadonnées complètes |

Contrat détaillé : [docs/api-contract.json](docs/api-contract.json).

## Pipeline M1 — inventaire et qualité

Pipeline scientifique pour l'analyse et l'harmonisation des détections de points chauds MODIS et VIIRS au Gabon.

## État du développement

Le pipeline M1 couvre l'inventaire, les contrôles de qualité, la normalisation et les comptages mensuels des CSV présents dans `data/raw/gabon`. Les données brutes restent inchangées. Les coefficients et benchmarks du guide v2 ne sont pas encore validés par ce pipeline.

## Prérequis

Python 3.10 ou plus récent. Le lot d'inventaire utilise uniquement la bibliothèque standard, sans installation de dépendance ni clé NASA.

Depuis la racine du dépôt :

```powershell
python -m unittest discover -s tests -v
python -m pipeline.inventory --input data/raw/gabon --output data/processed/audit
python -m pipeline.normalize --input data/raw/gabon --output data/processed/normalized
python -m pipeline.aggregate_monthly --input data/processed/normalized --output data/processed/monthly
```

Le manifeste et le rapport qualité JSON sont des résultats d'audit, pas des séries harmonisées utilisables comme résultats scientifiques finaux. Voir `docs/m1-data-audit.md` pour les contrôles, formats, limites et instructions de reproduction.

La normalisation est reproductible depuis les CSV bruts : les gros exports d'observations sont conservés localement et exclus de Git. Leurs manifestes et les petites sorties mensuelles sont versionnés pour le raccordement avec M2. Voir [le contrat M1](docs/m1-normalization.md), [la méthode](docs/methodology.md) et [les limites](docs/limitations.md). Les fichiers mensuels sont des comptages bruts et des statuts de disponibilité, pas des séries harmonisées. L'import DB correspondant reste à raccorder par M2.

## Sources et limites

- Données fournies dans le dépôt, accompagnées de `data/raw/gabon/AttributesReadme.txt`.
- [NASA FIRMS — documentation et ressources](https://firms.modaps.eosdis.nasa.gov/).
- [NASA FIRMS — différences entre produits et disponibilité](https://firms.modaps.eosdis.nasa.gov/content/academy/data_api/firms_api_use.html).
- [NASA FIRMS — anomalies connues et interruptions](https://firms.modaps.eosdis.nasa.gov/content/notifications/firms/outages.html).

La présence de détections ne permet pas de déduire une couverture d'observation complète. Le fichier pays ne remplace pas une validation des frontières géographiques. Un point chaud n'est pas nécessairement un incendie distinct.

## Contributions M1

Travail sur `m1/data-science`, contrôles et revue des changements avant proposition d'intégration dans `main`. Les artefacts d'audit et les résultats de préparation sont séparés des fichiers bruts. Les étapes suivantes sont l'évaluation du filtrage des sources statiques, la calibration et les extensions 2026.
