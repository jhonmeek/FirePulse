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

### Frontend (M3) - jalon H34-H42 (démo reproductible)

- **Vue 3 + TypeScript + Vite + Tailwind 4 + Pinia + ECharts + MapLibre GL** dans [frontend/](frontend/). ECharts et MapLibre sont chargés en différé (chunks séparés) : le bundle principal reste à ~165 Ko.
- **Démo reproductible sans réseau** : build autonome `npm run build:demo` (données FIRMS du Gabon embarquées, aucun backend), badge de provenance dans l'en-tête (*Démo hors ligne* / *Mode mocks* / *Données de secours* quand l'API M2 sert son instantané `X-FirePulse-Cache: FALLBACK`), parcours complet testé par Playwright avec Internet coupé, audit d'accessibilité axe-core WCAG 2.1 AA sans violation, captures du pitch dans [docs/demo/](docs/demo/).
- **Types TypeScript** ([frontend/src/types/api.ts](frontend/src/types/api.ts)) alignés sur [docs/api-contract.json](docs/api-contract.json) v2.2.0.
- **Flux réel bout-en-bout vérifié** : UI branchée sur l'API locale (`GA` + 9 provinces, bascule torchères), requêtes `/api/v1/*` en 200.
- **Lecture grand public (deux niveaux)** : vocabulaire courant à l'écran (« points de feu », « données brutes / corrigées », « normale », « écart à la normale »), termes techniques conservés en infobulle, pour les lecteurs d'écran et dans des replis *Détails techniques* ; l'onglet *Méthodologie & évaluation* reste le niveau expert, accessible via « Comment c'est calculé ? ».
- **Onglet *Explorer*** :
  - **« En bref »** en tête de page : une phrase calculée sur la série chargée - dernière année complète de la plage, total arrondi, écart à l'année normale (somme des 12 médianes mensuelles), mois de pic de la saison, date des dernières données, mention « provisoire » si besoin ;
  - barre de contrôle : zone (Gabon / provinces), plage d'années, *Colorer le calendrier selon* *Nombre de points de feu* / *Écart à la normale* (masqué sur l'onglet Méthodologie, où il est sans effet), toggle « Exclure les sources industrielles (torchères) » avec **compteur de détections retirées par le filtre** (type FIRMS ≠ 0 ou cellule statique `0.05°`, dans la zone, sur la période affichée — écart entre les séries `/calendar/` sans et avec filtre ; à ne pas confondre avec le nombre de détections situées dans les cellules candidates, cf. revue M1 de la PR #9). Les deux séries sont chargées ensemble : bascule instantanée ;
  - bandeau des régimes capteurs (Terra seul → MODIS reconstitué → VIIRS S-NPP → pont NOAA-20) avec la plage affichée en surbrillance, replié sous « Quels satellites ont observé ? » ;
  - **calendrier Années × Mois accessible** : palettes adaptées aux daltoniens (YlOrRd en racine carrée pour l'intensité, PuOr divergente pour l'anomalie, orange = au-dessus de la médiane), mois provisoires/NRT hachurés, mois sans donnée en pointillés, navigation clavier complète, libellé lecteur d'écran par cellule ; ligne de référence *Normale* (médiane 2001-2025 de la série harmonisée, même échelle) sous les années ; **bascule *Données brutes / Données corrigées*** (avant / après harmonisation) partagée avec le graphe (basculer l'un bascule l'autre), expliquée en une phrase sous la bascule (saut instrumental arrondi, « environ 4 fois plus ») : en *Données brutes*, chaque mois montre le brut du capteur en service (MODIS Terra + Aqua jusqu'à janvier 2012, VIIRS S-NPP dès février 2012, trait noir sur la frontière) sur la même échelle que la vue harmonisée, ce qui rend la rupture de 2012 visible ; le mode *Anomalie* y est désactivé (calculé sur la série harmonisée) puis rétabli au retour en *Après* ; le panneau de détail met alors la valeur brute au premier plan ;
  - **panneau détail du mois** (par défaut le dernier mois disponible de la plage ; survol/focus = aperçu, clic/Entrée = épinglé) : nombre de points de feu et fourchette probable (intervalle 80 %), mois normal et IQR (« souvent entre »), écart à la normale (% ou écart absolu si médiane nulle), classement 2001–2025 ; régime capteur, couverture, unité et détections brutes par capteur dans un repli *Détails techniques* ;
  - **graphe comparatif ECharts** : MODIS / VIIRS S-NPP / NOAA-20 bruts, série harmonisée et **bande d'incertitude conforme 80 %**, bouton *Avant / Après harmonisation* qui **conserve la vue et le zoom** (fenêtre mémorisée, ramenée dans la plage d'années, bouton de réinitialisation), NOAA-20 en vert bleuté pointillé (teinte distincte de S-NPP),, repères des ruptures (Aqua 2002, VIIRS 2012), saut S-NPP/MODIS mesuré (≈ ×3,9 au Gabon), clic = sélection du mois. ECharts est chargé en différé (chunk séparé) ;
  - **anomalies** : saisonnalité de référence (médiane + IQR par mois, mois sélectionné en pointillés) et mois les plus au-dessus / en dessous de la médiane sur la plage affichée, cliquables ;
  - **carte MapLibre** (`/api/v1/hotspots/?mode=grid&agg=cell`) : grille `0.25°` colorée par détections brutes d'un capteur (S-NPP par défaut, MODIS avant 2012, NOAA-20), même échelle racine carrée que le calendrier, **sites statiques exclus** (cellules `0.05°`, bleu) avec info-bulle (motif, détections type 2/3, mois actifs), contours Gabon et provinces, fond de carte OpenFreeMap (sans clé ; attribution OpenMapTiles/OSM affichée), désactivable ; hors ligne, la carte démarre sur fond uni et la grille reste affichée ;
  - **zone libre** : bouton *Dessiner une zone* (cliquer-glisser un rectangle, Échap pour annuler) ou saisie lat/lon au clavier. La bbox remplace la région pour le calendrier, le graphe, les anomalies, la carte et l'export (série `CUSTOM_BBOX` agrégée par M2 depuis la grille ; pas d'intervalle propre à la zone, signalé dans l'UI) ;
  - **Export CSV** (`/api/v1/export/?dataset=series`) de la zone et de la période affichées. En mode mocks, le même CSV est construit côté client (identique octet pour octet à l'export Django sur la série GA sans filtre).
- **Finitions UI** : en-tête collant et panneau de détail du mois en verre dépoli (seules surfaces vitrées, repli opaque sans `backdrop-filter` ou avec `prefers-reduced-transparency`), cartes et contrôles harmonisés (tokens dans `src/assets/main.css`), lien d'évitement « Aller au contenu », mouvements de 150-200 ms désactivés avec `prefers-reduced-motion`, tiret simple `-` à la place du tiret cadratin dans toute l'interface.
- **Onglet *Méthodologie & évaluation*** (critère H24 « moteur scientifique évalué hors échantillon visible dans l'UI », **protocole en revue M1**) : évaluation `2020–2025` des 5 modèles ajustés sur `2012-02–2019-12` (MAE, RMSE, biais, R², formules avec paramètres calibrés), écart du modèle retenu sur la période test (au Gabon : −72 % de MAE vs naïf, −16 % vs ratio global, R² = 0,919). L'UI affiche les réserves de la revue : intervalle 80 % calibré sur les résidus de test, choix du modèle fait sur la même fenêtre, masque construit avec la période test. Également : facteurs d'incertitude conformes, pont NOAA-20, masque torchères, limites documentées — le tout lu depuis `/api/v1/methodology/`.
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
- Flux FIRMS NRT planifié (profil Docker opt-in) : voir [docs/nrt-celery.md](docs/nrt-celery.md).
- `python manage.py build_baseline_series --from-pipeline /data/processed/monthly` : ingère directement les artefacts mensuels M1 (`calendar.json` ou `monthly_counts.csv` + vérification SHA-256 `manifest.json`) ou un bundle calibré M1 JSON (`regions`).

### 4. Vérifier que tout tourne

```bash
docker compose exec backend python manage.py test -v 2
curl http://localhost:8000/api/v1/health/
```

Réponse attendue sur `/api/v1/health/` : `"status": "ok"`, `"database": "connected"` et les compteurs (`regions: 10`, `hotspots: 292589`, `grid_cell_months: 42482`, `harmonized_months: 6011`).

Le workflow GitHub Actions ([.github/workflows/ci.yml](.github/workflows/ci.yml)) exécute automatiquement à chaque PR/push les tests Backend PostGIS (`manage.py test -v 2`), le pipeline M1 (`unittest`) et le build/tests Frontend (`type-check`, `vitest`, `vite build`).

### 5. Production HTTPS, preflight & plan de secours démo (`H24–H48` M2)

- **Stack production HTTPS (Gunicorn + Caddy) :** [docker-compose.prod.yml](docker-compose.prod.yml) + [deploy/Caddyfile](deploy/Caddyfile) (`cd frontend && npm ci && npm run build`, puis `DJANGO_SECRET_KEY=... docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build`). Pour une démo locale en navigateur sans alerte sur le certificat interne autosigné, passer `FIREPULSE_DOMAIN=http://localhost` (`http://localhost/`).
- **Backup PostGIS + snapshot JSON hors ligne (`86` fichiers `GA` + `GA-1..GA-9`) :**
  - `./scripts/db_backup.sh` : dump PostgreSQL/PostGIS (`pg_dump -Fc` + SHA-256), export des `86` réponses JSON (`/api/v1/regions`, `coverage`, `calendar`, `anomalies`, `hotspots` grille mensuelle + cellulaire + masque statique, `methodology`, `export`) via `python manage.py export_demo_snapshot` et contrôle d'intégrité (`--verify`) dans `data/backups/demo_snapshot`.
  - `./scripts/db_restore.sh data/backups/<fichier>.dump` : vérification SHA-256, `pg_restore` et contrôle `/api/v1/health/`.
  - `./scripts/preflight_demo.sh` : vérification pré-démo recommandée (`db` + `backend` healthy, `manage.py check`, `makemigrations --check`, `export_demo_snapshot --verify`, `export_calibration_series --verify`, compteurs `/api/v1/health/`, routes UI `/api/v1/*`, et MIME JS `.mjs`/`.js` sur Caddy si actif) ; non obligatoire au runtime.
- **Fallback serveur sans base PostGIS :** activé par défaut (`API_SNAPSHOT_FALLBACK=true`, ou simulable via `FORCE_SNAPSHOT_FALLBACK=true`), sert automatiquement les endpoints régionaux/nationaux (y compris la carte MapLibre `/api/v1/hotspots/?mode=grid&start=...&end=...` filtrée avec la géométrie exacte de `GA`, `GA-1..GA-9` ou `bbox`/`polygon`) depuis `DEMO_SNAPSHOT_DIR` (`/data/backups/demo_snapshot`) avec l'en-tête `X-FirePulse-Cache: FALLBACK` (et signale `X-FirePulse-Fallback: ready|none` sur `/api/v1/health/`). À l'exécution, chaque lecture valide l'unicité, la complétude (`86` fichiers attendus) et le SHA-256 du manifeste `snapshot_manifest.json` (et `/api/v1/health/` vérifie la présence, l'empreinte des `86` fichiers et la cohérence des codes régions avec `regions.json`) : tout fichier manquant, dupliqué, tronqué ou modifié après le préflight fait basculer `/api/v1/health/` sur `X-FirePulse-Fallback: none` et renvoie `503` (`X-FirePulse-Cache: BYPASS`).
- **Export mensuel de calibration pour M1 :** `docker compose exec -T backend python manage.py export_calibration_series` (+ `--verify`) génère `data/backups/m1-benchmark-validation/m2_calibration_monthly_series.csv`, son checksum `.sha256` et `manifest.json` (provenance base/commit, comptes `modis_count`, `modis_terra_count`, `modis_aqua_count`, `viirs_snpp_count`, `viirs_noaa20_count`, `region`, `filter_static` et split `train`/`test`).

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
| **Mocks** (défaut en dev) | rien à faire | `frontend/src/mocks/*.json` — région `GA` ; une bbox fonctionne pour la carte (grille resommée côté client) mais pas pour les séries ; provinces : série vide |
| **API Django** | créer `frontend/.env.local` avec `VITE_USE_MOCKS=false` | `/api/v1` relayé par le proxy Vite vers `http://localhost:8000` (backend lancé, voir ci-dessus) |
| **Démo autonome** | `npm run build:demo` puis `npm run preview:demo` | build statique `dist-demo/` avec les mocks embarqués : fonctionne sans Docker, sans API et sans Internet (fond de carte remplacé par un fond uni) |

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
npm run test:e2e
```

`npm run test:e2e` (Playwright, Chrome installé sur la machine) construit le build de démo, coupe tout accès réseau hors serveur local et rejoue le parcours d'un utilisateur naïf sur desktop (1440 px) et mobile (Pixel 7) : découverte, mois atypique, calendrier avant/après synchronisé avec le graphe, filtres, clavier, zoom conservé à la bascule avant/après, carte hors ligne, export CSV, méthodologie, absence de défilement horizontal. Il lance aussi un **audit axe-core WCAG 2.1 AA** (contrastes compris) sur les deux onglets ; les contrastes sur verre dépoli, qu'axe ne sait pas calculer, ont été vérifiés par calcul au pire cas (texte ≥ 5,4:1 même au-dessus d'un fond noir).

Captures du pitch (1440×900, densité ×2) régénérables depuis `frontend/` :

```bash
CAPTURE=1 npx playwright test capture
```

Les tests comparent les mocks aux clés et énumérations de `docs/api-contract.json` : toute évolution du contrat par M2 sans mise à jour de `src/types/api.ts` et des mocks fait échouer la suite. Ils couvrent aussi les utilitaires (palettes, rang, options du graphe, bande d'incertitude, classement des anomalies, compteur, benchmark, bbox dessinée, échelle de la grille, export CSV) et la grille mock, comparée aux chiffres de l'API (352 cellules et 183 sites au Gabon ; 79 cellules et 27 sites sur une bbox de test), et les composants (navigation clavier, sélection, hachures, bascule avant/après, méthodologie ; ECharts est remplacé par un double car jsdom n'a pas de canvas). Ils tournent toujours en mode mocks, même si `.env.local` pointe vers l'API.

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
│       ├── utils/               # calendar.ts (matrice, palettes, rang), chart.ts (options ECharts), summary.ts (« En bref »),
│       │                        # anomalies.ts, methodology.ts, map.ts
│       ├── components/          # SummaryBanner, ControlBar, RegimeTimeline, CalendarHeatmap, MonthDetail,
│       │                        # HarmonizationToggle, ComparisonChart, AnomaliesPanel, MethodologyPanel, MapExplorer, ExportButton
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
