# FIREPULSE — Guide Définitif de Réalisation (v2 — Équipe de 3)

**One Planet. One Fire History.**  
**Défi NASA Space Apps 2026 :** *Harmonization of MODIS and VIIRS Hot Spots*  
**Format :** Sprint 48 heures · Équipe de **3 développeurs** · Données réelles **NASA FIRMS**

> Ce guide v2 remplace et corrige le plan initial [Guide_FirePulse_NASA_Space_Apps_2026.pdf](Guide_FirePulse_NASA_Space_Apps_2026.pdf) pour l'aligner sur :
> 1. Une équipe de **3 personnes** (au lieu de 5) en mode *vibecoding* avec contrats stricts.
> 2. Les **données réelles NASA FIRMS du Gabon (2000–2025)** déjà téléchargées et analysées dans `data/raw/gabon/`.
> 3. La **réalité opérationnelle de novembre 2026** : l'arrêt de livraison de **Suomi NPP VIIRS** au **2 novembre 2026 (13:00 UTC)** et la transition officielle vers **NOAA-20 VIIRS** (`viirs-jpss1`).

---

## Synthèse des Paramètres Retenus

| Paramètre | Périmètre v2 Définitif |
| :--- | :--- |
| **Durée** | 48 heures (jalons stricts à H12, H24, H34, H42) |
| **Équipe** | **3 personnes** : `M1 Data & Science`, `M2 Backend/Geo/Infra`, `M3 Frontend/UX/Pitch` |
| **Territoire principal** | **Gabon** (national + grille `0.25°` + sous-régions/provinces + zone libre dessinée / `lat-lon`) |
| **Zone de contrôle (option P1)** | 1 territoire contrasté (ex. Mato Grosso / Portugal / Californie) si le P0 Gabon est verrouillé avant H24 |
| **Période** | **2001–2025** (archives complètes) + **2000-11/12** (signalé partiel) + **2026 YTD** (`SP` + `NRT`) |
| **Capteurs** | **MODIS** (Terra + Aqua, C6.1) + **VIIRS S-NPP** (2012–nov. 2026) + **VIIRS NOAA-20** (pont 2018–présent) |
| **Livrable** | Application web sans compte + calendrier accessible + pipeline d'harmonisation évalué hors échantillon + export CSV |
| **Stack** | Django / DRF + PostgreSQL / PostGIS + Python scientifique (`pandas`/`numpy`/`scipy`) + React / TypeScript / Vite / Tailwind + MapLibre GL JS + Recharts |

---

## 1. Vision, Proposition de Valeur & Positionnement Jury

FirePulse transforme 25+ ans d'observations hétérogènes de points chauds (MODIS 1 km et VIIRS 375 m) en un **calendrier historique continu, traçable et interprétable**.

### Questions métier auxquelles répond l'application
1. **Saisonnalité :** À quels mois les détections sont-elles habituellement maximales dans la zone choisie ?
2. **Anomalie :** Le mois sélectionné (ou courant) est-il atypique par rapport à la **médiane historique** du même mois ?
3. **Continuité intercapteurs :** Les ruptures liées au passage MODIS → VIIRS (2012), à l'époque **Terra seul** (2000–juin 2002) et à l'arrêt de **VIIRS S-NPP** (2 nov. 2026 → NOAA-20) sont-elles corrigées et documentées ?
4. **Fiabilité :** Les sources thermiques industrielles/pétrolières persistantes (*gas flares*) sont-elles séparées des feux de végétation, et quelle est l'incertitude du modèle ?

> **Règle de formulation scientifique :** toujours parler d'**« indicateur harmonisé d'activité des points chauds »** (ou détections équivalentes VIIRS 375 m), jamais de « nombre réel d'incendies ».

---

## 2. Périmètre MVP (Priorisation Stricte pour 3 Personnes)

| Priorité | Fonctionnalité | Définition exacte |
| :--- | :--- | :--- |
| **P0** | **Sélection de zone** | Gabon entier + sous-régions / provinces précalculées |
| **P0** | **Séries comparatives** | MODIS brut / VIIRS S-NPP brut / VIIRS NOAA-20 brut / Série harmonisée + bande d'incertitude |
| **P0** | **Calendrier Années × Mois** | Heatmap interactive accessible (palette daltonien-compatible + valeurs au survol/focus) |
| **P0** | **Anomalies & Couverture** | Écart % (ou absolu si médiane = 0) vs médiane historique du même mois + badge couverture/régime |
| **P0** | **Filtre Torchères (`type=0` + masque statique)** | Toggle UI : *Feux de végétation (nettoyé)* vs *Toutes anomalies thermiques (incl. torchères/industrie)* |
| **P0** | **Onglet Méthodologie & Preuve** | Métriques hors échantillon (Naïf vs Ratio v1 vs Power-Law v2), graphes de rupture 2012, limites |
| **P1** | **Carte interactive + Zone libre** | Grille `0.25°` GeoJSON + points zoomés + dessin polygone / saisie `bbox lat/lon` |
| **P1** | **Export CSV métadonné** | Téléchargement des séries brutes + harmonisées + médianes + statut couverture/méthode |
| **P2** | **Zone de contrôle / Rapport PDF** | Uniquement si tout P0 + P1 est stable et testé à H34 |

**Hors périmètre :** prévision météo des feux, IA générative décorative, création de compte utilisateur, application mobile native, ingestion globale mondiale temps réel.

---

## 3. Architecture Technique & Stratégie Données NASA FIRMS

### 3.1 Flux réel des données (corrigé post-audit)

```text
[1] Archives Pays Annuelles FIRMS (2000–2025, sans clé)
    └── https://firms.modaps.eosdis.nasa.gov/data/country/{inst}/{year}/{file}
        • modis (2000–2025) • viirs-snpp (2012–2025) • viirs-jpss1 / NOAA-20 (2018–2025)

[2] Complément 2026 YTD (janv. 2026 → aujourd'hui)
    ├── Janv.–oct. 2026 : FIRMS Archive Download (https://firms.modaps.eosdis.nasa.gov/download/)
    ├── 60 derniers jours (NRT) : nrt3.modaps.eosdis.nasa.gov (Bearer Earthdata après acceptation EULA LANCE)
    └── 7 derniers jours / live (sans clé) : /api/active_fire_files/all?format=json
        ou Area API (/api/area/csv/{MAP_KEY}/{source}/...)

            │
            ▼  scripts Python (normalize + static_mask + grid_agg + calibrate + validate)
            │
[3] PostgreSQL + PostGIS (observations filtrées + grille mensuelle 0.25° + séries régionales)
            │
            ▼  Django + Django REST Framework (endpoints JSON + GeoJSON + export CSV)
            │
[4] React + TypeScript + Vite + Tailwind + MapLibre GL JS + Recharts
```

### 3.2 Ce qui est déjà vérifié dans `data/raw/gabon/`

Les **48 fichiers CSV officiels du Gabon (2000–2025, 21.89 Mo)** sont déjà téléchargés localement :
* **`modis` (2000–2025) :** `59 282` détections (`2000` ne contient que nov.–déc.).
* **`viirs-snpp` (2012–2025) :** `147 745` détections.
* **`viirs-jpss1` / NOAA-20 (2018–2025) :** `85 562` détections (`2018` démarre en avril, 9 mois).

> **Important (2026) :** Sur `nrt3.modaps.eosdis.nasa.gov`, l'acceptation unique de la licence/EULA LANCE dans le profil Earthdata (`303 -> /profiles/licenses/...`) débloque les fichiers quotidiens `NRT` des ~60 derniers jours (`MODIS_C6_1` et `J1_VIIRS_C2`), tandis que les flux `active_fire` 24h/48h/72h/7d sont téléchargeables directement sans clé pour `modis`, `noaa20`, `noaa21`.

### 3.3 Arborescence cible du dépôt

```text
modis_viirs/
├── data/
│   ├── raw/gabon/               # CSV annuels FIRMS + AttributesReadme.txt
│   └── processed/               # Parquet/CSV propres + tables précalculées de secours
├── backend/
│   ├── config/
│   ├── apps/
│   │   ├── observations/        # Modèles HotspotObservation, GridCellMonth, ImportBatch
│   │   ├── harmonization/       # Calibration, validation hors échantillon, médianes, anomalies
│   │   └── api/                 # Endpoints REST v1 + export CSV
│   ├── pipeline/                # Scripts reproductibles (ingest.py, mask_flares.py, calibrate.py)
│   └── tests/
├── frontend/
│   └── src/
│       ├── types/api.ts         # Contrats TypeScript verrouillés à H2
│       ├── services/
│       ├── components/          # CalendarHeatmap, ComparisonChart, MapExplorer, MethodologyPanel
│       └── mocks/               # Jeu JSON réaliste pour dev parallèle H2–H12
├── docs/
│   ├── methodology.md
│   ├── limitations.md
│   └── api-contract.json
└── docker-compose.yml
```

---

## 4. Méthodologie Scientifique Révisée (Validée sur Données Réelles du Gabon)

Les analyses exploratoires sur les **292 589 détections réelles du Gabon (2000–2025)** ont mis en évidence **4 phénomènes critiques** absents du guide initial.

### 4.1 Normalisation des schémas MODIS vs VIIRS

| Champ interne | MODIS (`C6.1`) | VIIRS (`S-NPP / NOAA-20 C2`) | Règle d'unification |
| :--- | :--- | :--- | :--- |
| `brightness_mir` | `brightness` (K) | `bright_ti4` (K) | Renommage explicite dans une colonne commune |
| `brightness_tir` | `bright_t31` (K) | `bright_ti5` (K) | Renommage explicite |
| `confidence_raw` / `tier` | `0–100` (`<30` low, `30–79` nom, `≥80` high) | `l` / `n` / `h` | Conserver `confidence_raw` + mapper vers `confidence_tier` (`low`/`nominal`/`high`) |
| `satellite` | `Terra` / `Aqua` | `N` (S-NPP) / `N20` (NOAA-20) | **Ne jamais fusionner Terra et Aqua sans traçabilité** (critique pour 2000–2002) |
| `product_version` | `6.2`, `6.03`, `61.03` (+ `NRT`) | `2` (+ `NRT`) | Tracer `version` et séparer `SP` vs `NRT` |
| `type` | `0, 2` | `0, 2, 3` | Conserver systématiquement pour le filtrage industriel |

### 4.2 Découverte #1 — Le piège des torchères (*Gas Flares*) & fuite de classification

* **Constat réel au Gabon :** les détections `type=2` (sources terrestres statiques) et `type=3` (offshore) représentent **11.2%** des détections MODIS (`6 658`), **21.2%** des détections VIIRS S-NPP (`31 298`) et **23.7%** des détections VIIRS NOAA-20 (`20 267`), concentrées sur les zones pétrolières (ex. `(-1.96, 9.87)`, `(-1.52, 9.95)`) et quelques sites industriels intérieurs (ex. `(-0.74, 12.97)` actif 167 mois).
* **Piège caché :** dans MODIS, le tag `type=2` varie fortement selon les versions (`0` détection `type=2` en **2017**, seulement `27` en **2023** !), laissant fuir des torchères dans `type=0`.
* **Solution retenue (Masque Statique Uniforme) :**
  1. Filtrer `type == 0`.
  2. Construire un **masque spatial statique `0.05° × 0.05°`** (~5.5 km) identifiant toute cellule comptant `≥ 20` détections `type ∈ {2,3}` ou active `≥ 48` mois dans VIIRS S-NPP (`178` cellules sur `2 754` au Gabon, soit **6.5%** des cellules).
  3. Appliquer ce masque **uniformément à MODIS, S-NPP et NOAA-20** (tout en offrant un toggle UI permettant au jury de comparer avec/sans masque).
  * *Effet mesuré :* le ratio `S-NPP / MODIS` se stabilise immédiatement en **2017 (`3.97`)** et **2023 (`4.03`)**.

### 4.3 Découverte #2 — Les 4 régimes historiques d'observation à modéliser

1. **`2000-11` → `2000-12` (`partial_year`) :** Seuls 2 mois MODIS existent ; ne pas comparer à des totaux annuels complets.
2. **`2001-01` → `2002-06` (`modis_terra_only`) :** **MODIS Aqua n'a démarré qu'en juillet 2002** (`Aqua = 0` jusqu'en `2002-06`). Appliquer un modèle `Terra+Aqua` avant juillet 2002 sous-estime l'activité d'un facteur ~2 et crée de fausses anomalies de `-78%` à `-95%`.
   * *Solution :* calibrer un modèle dédié **`MODIS Terra-only → VIIRS`** sur `2012–2019` (`p = 0.712, q = 3.626`, `R² = 0.877`, `MAE = 127.4` hors échantillon) et l'appliquer uniquement à `2000-11..2002-06` (ce qui remet **2001 à `7 487`** détections équivalentes, cohérent avec `2003+`).
3. **`2002-07` → `2012-01` (`modis_terra_aqua`) :** Reconstitution rétrospective sur l'échelle VIIRS S-NPP par le modèle principal.
4. **`2012-02` → `2026-11-02` (`viirs_snpp_observed`)** puis **`2026-11-03+` (`viirs_noaa20_bridge`) :**
   * Suomi NPP cesse de livrer de nouvelles données FIRMS le **2 novembre 2026 à 13:00 UTC**.
   * Sur la période de recouvrement nettoyée (`2019–2025`), le ratio annuel **NOAA-20 / S-NPP** au Gabon vaut **`0.98` à `1.12`** (moyenne ~`1.03`), confirmant que **NOAA-20** assure la continuité directe post-novembre 2026 (à calibrer/tracer avec un facteur léger `beta_n20` si un écart régional existe).

### 4.4 Benchmark réel d'harmonisation (Gabon, Train `2012-02..2019-12` → Test `2020–2025`, `N = 72` mois)

Sur données réelles nettoyées (`type=0` + masque statique) :

| Modèle testé (comptages mensuels) | MAE (test) | RMSE (test) | Biais (test) | R² (test) | Commentaire |
| :--- | :---: | :---: | :---: | :---: | :--- |
| **0. Naïf** (`V_est = M`) | `376.7` | `583.0` | `-376.7` | `0.142` | Cassure artificielle massive en 2012 |
| **1. Ratio global v1** (`3.927 × M`) | `122.1` | `216.0` | `+53.7` | `0.882` | Baseline du guide v1 |
| **2. Régression OLS** (`3.781 × M + 21.2`) | `112.0` | `198.2` | `+53.5` | `0.901` | Corrige le biais des mois calmes |
| **3. Power-Law `log1p`** (`exp(0.953·ln(M+1)+1.606)−1`) | **`103.1`** | **`179.7`** | **`+41.2`** | **`0.918`** | **Meilleur modèle retenu (-15.6% MAE vs v1)** |

* **Indicateur spatial complémentaire (Cellules actives `0.25° × 0.25°`) :**
  * Naïf : `MAE = 35.8`, `R² = -0.055`, `MAPE(≥50) = 45.7%`
  * **OLS sur cellules actives (`1.332 × C + 24.3`) :** **`MAE = 11.2`**, **`RMSE = 14.3`**, **`R² = 0.855`**, **`MAPE(≥50) = 11.7%`** — idéal pour estimer l'empreinte spatiale des feux et alimenter la carte + les zones dessinées par l'utilisateur.

### 4.5 Incertitude honnête, Médiane & Anomalies

* **Bandes d'incertitude :** Les intervalles gaussiens sur résidus logarithmiques sous-estiment l'erreur lors des années post-2020 (`59.7%` de couverture empirique pour un intervalle nominal `80%` dû à une légère dérive de sensibilité). Utiliser des **quantiles empiriques conformes (split-conformal)** des résidus hors échantillon `|V − V_est|` pour garantir une couverture réelle de `80%` / `90%`.
* **Médiane historique `B(r,m)` :** Calculée mois par mois (`m = 1..12`) sur la série harmonisée `2001–2025` (au Gabon, régime bimodal : pic principal **juillet `1 429` – août `1 789`**, pic secondaire **février `289` – mars `380`**, creux **novembre `47.9` – décembre `59.0`**).
* **Anomalie mensuelle :** `A(r,t) = 100 × [H(r,t) − B(r,m)] / B(r,m)`. Si `B(r,m) = 0`, basculer automatiquement sur l'écart absolu `H(r,t) − B(r,m)` (jamais de division par zéro).

---

## 5. Contrats API & Modèles de Données (Verrouillés à H2)

### 5.1 Endpoints REST (`/api/v1/`)

| Méthode | Endpoint | Rôle & Paramètres |
| :--- | :--- | :--- |
| `GET` | `/api/v1/regions` | Liste Gabon + provinces/sous-régions précalculées (GeoJSON simplifié + bbox) |
| `GET` | `/api/v1/coverage` | Plages disponibles par capteur (`SP` vs `NRT`, coupure S-NPP 2 nov. 2026, mois incomplets) |
| `GET` | `/api/v1/calendar` | Matrice années × mois + séries MODIS/S-NPP/NOAA-20/Harmonisé + intervalle incertitude (`?region=&bbox=&polygon=&filter_static=true`) |
| `GET` | `/api/v1/anomalies` | Médianes mensuelles `B(r,m)`, IQR `[p25, p75]`, anomalies `%` et top mois atypiques |
| `GET` | `/api/v1/hotspots` | Agrégats grille `0.25°` (défaut rapide) ou points GeoJSON si zoom/mois filtré (`limit` plafonné) |
| `GET` | `/api/v1/methodology` | Coefficients (`alpha`, `power-law`, `terra_only`), benchmark hors échantillon (`MAE/RMSE/R²`), stats masque statique |
| `GET` | `/api/v1/export` | Export CSV complet incluant colonnes `source_regime`, `coverage_status`, `ci_low`, `ci_high`, `filter_static` |

### 5.2 Contrat JSON type (`/api/v1/calendar`)

```json
{
  "region": {"id": "GA", "name": "Gabon", "filter_static": true},
  "period": {"start": "2001-01", "end": "2026-10"},
  "method": {
    "name": "power_law_log1p_static_masked",
    "version": "v2.0",
    "reference_scale": "VIIRS_375m_SNPP_equiv",
    "bridge_after_2026_11_02": "VIIRS_NOAA20"
  },
  "series": [
    {
      "month": "2024-08",
      "modis_count": 698,
      "viirs_snpp_count": 3150,
      "viirs_noaa20_count": 3420,
      "harmonized_value": 3150.0,
      "ci_low": 3150.0,
      "ci_high": 3150.0,
      "baseline_median": 1789.0,
      "baseline_iqr": [1111.6, 2313.7],
      "anomaly_percent": 76.1,
      "sensor_regime": "viirs_snpp_observed",
      "coverage_status": "complete_sp"
    }
  ]
}
```

### 5.3 Modèles Django / PostGIS clés

* **`Region`** (`code`, `name`, `geom MultiPolygonField srid=4326`, `is_custom_supported`)
* **`HotspotObservation`** (`source`, `satellite`, `acquired_at`, `position PointField`, `frp`, `brightness_mir`, `brightness_tir`, `confidence_raw`, `confidence_tier`, `daynight`, `hotspot_type`, `is_static_masked`, `product_version`, `is_nrt`, `original_hash` unique)
* **`GridCellMonth`** (`cell_id`, `geom PolygonField 0.25°`, `month`, `filter_static`, `modis_count`, `modis_terra_count`, `viirs_snpp_count`, `viirs_noaa20_count`, `frp_sum_*`) → **clé de performance** pour recalculer instantanément n'importe quelle boîte `lat/lon` ou polygone dessiné côté UI !
* **`HarmonizedMonthSeries`** (`region`, `month`, `filter_static`, `harmonized_value`, `ci_low`, `ci_high`, `baseline_median`, `anomaly_percent`, `sensor_regime`, `coverage_status`, `method_version`)
* **`CalibrationRun`** (`region`, `method_name`, `train_window`, `test_window`, `params_json`, `metrics_json`, `created_at`)

---

## 6. Design UI/UX & Accessibilité

Parcours en **1 écran principal + tiroir/onglet Méthodologie**, utilisable **sans connexion** :

1. **Barre de contrôle supérieure :** Zone (Gabon / Province / *Dessiner sur la carte* / *Lat-Lon*) · Plage d'années · Toggle **« Exclure torchères / sources statiques »** (activé par défaut avec compteur des détections masquées).
2. **Bandeau de transparence capteurs :** Timeline visuelle montrant les 4 régimes (`2000–2002 Terra seul` · `2002–2012 MODIS reconstitué` · `2012–nov. 2026 VIIRS S-NPP` · `nov. 2026+ Pont NOAA-20 + NRT`).
3. **Calendrier d'activité (Années × Mois) :**
   * Palette **accessible aux daltoniens** (ex. *Viridis* ou *Cividis* ou *YlOrRd* à fort contraste, jamais rouge/vert pur) + bordure/hachure distincte pour les mois partiels ou `NRT`.
   * Clic sur une cellule = affichage du détail du mois (valeur harmonisée vs médiane du même mois, rang historique, anomalie `+X%`, statut couverture).
4. **Graphique comparatif multi-courbes (Recharts) :**
   * Courbe MODIS brut, VIIRS brut (S-NPP + NOAA-20), et courbe **Harmonisée** avec **ruban d'incertitude** sur 2001–2011.
   * Bouton « Vue Avant / Après harmonisation » pour le storytelling immédiat face au jury.
5. **Carte interactive (MapLibre GL JS) :**
   * Grille `0.25°` colorée par intensité ou anomalie + localisation cliquable des sites statiques masqués (`type=2/3`) + outil de tracé bbox/polygone.
6. **Onglet Méthodologie & Limites + Bouton Export CSV.**

---

## 7. Planning 48 Heures Synchronisé (Équipe de 3)

| Fenêtre | M1 — Data & Science | M2 — Backend / Geo / Infra | M3 — Frontend / UX / Pitch | Critère de sortie |
| :--- | :--- | :--- | :--- | :--- |
| **H0–H3** | Compléter acquisition 2026 (`download/` + EULA `nrt3`), figer `api-contract.json` avec M2/M3. | Init repo, `docker-compose.yml` (PostGIS + Django), modèles Django + migrations. | Init React/Vite/Tailwind, génération `mocks/` fidèles au contrat H2. | Contrat JSON figé, Docker up, données 2000–2025 prêtes. |
| **H3–H12** *(Jalon 1)* | Script `pipeline/` (`normalize`, `static_mask`, `grid_025`), export JSON/CSV propres Gabon. | Chargeur DB idempotent + endpoints `/regions`, `/coverage`, `/calendar` v1. | Squelette UI + Calendrier heatmap branché sur mock puis sur API locale. | **Flux réel bout-en-bout sur le Gabon affiché dans React.** |
| **H12–H24** *(Jalon 2)* | Calibration Power-Law + `Terra-only` + pont NOAA-20 + intervalles conformes + benchmark `MAE/RMSE/R²`. | Endpoints `/anomalies`, `/methodology`, `/export` CSV + requête spatiale sur `GridCellMonth`. | Graphe 3 courbes + bande incertitude + toggle torchères + panneau anomalie. | **Moteur scientifique validé hors échantillon visible dans l'UI.** |
| **H24–H34** *(Jalon 3)* | Vérif cas limites (`B=0`, `2000-11/12`, `2026 NRT`), rédaction `methodology.md` & `limitations.md`. | Endpoint `/hotspots` GeoJSON optimisé + cache/précalcul + déploiement HTTPS. | Carte MapLibre grille + dessin zone/bbox + onglet Méthodologie + Export CSV. | **Tout P0 + P1 fonctionnel et déployé en ligne.** |
| **H34–H42** | Relecture scientifique des chiffres affichés à l'écran (zéro divergence UI/scripts). | Snapshot base / JSON précalculés de secours (démo hors-ligne prête). | Tests parcours complet (utilisateur naïf), accessibilité contrastes, capture démo. | **Démo reproductible même sans réseau NASA.** |
| **H42–H48** | Gel total à H42. Préparation Q&A scientifique jury. | Gel code à H42. Vérif README reproductible + logs/santé prod. | Enregistrement vidéo pitch (3 min max) + soumission officielle Space Apps. | **Livrables soumis et vérifiés.** |

---

## 8. Matrice des Risques & Plans de Secours

| Risque | Probabilité / Impact | Réponse opérationnelle |
| :--- | :---: | :--- |
| **Lenteur ou panne API FIRMS lors du jury** | Élevée / Critique | Toutes les séries Gabon 2000–2025 + 2026 YTD préchargées dans PostGIS + fallback JSON statique côté serveur. |
| **Rupture S-NPP au 2 nov. 2026** | Certaine / Élevée | Pont documenté et activé vers **VIIRS NOAA-20** (`viirs-jpss1`) + badge explicite dans l'UI. |
| **Torchères pétrolières faussant la médiane** | Certaine / Élevée | Masque spatial statique `0.05°` + `type=0`, avec toggle transparent dans l'UI. |
| **Fausse anomalie 2001–2002 (Terra seul)** | Certaine / Élevée | Modèle `Terra-only` calibré séparément pour `2000-11..2002-06`. |
| **Carte lente sur gros volumes** | Moyenne / Moyenne | Affichage par défaut sur grille pré-agrégée `0.25°` (`< 3 000` cellules-mois) ; points bruts uniquement à zoom/mois ciblé. |
| **Conflits Git / retard intégration à 3** | Moyenne / Élevée | Contrat JSON figé à H2, dossiers séparés (`pipeline/`, `backend/`, `frontend/`), PR courtes toutes les 4–6h. |

---

## 9. Script du Pitch Jury (3 Minutes)

* **0:00–0:30 — Le Problème :** « 25 ans de données feux NASA existent, mais les capteurs ne parlent pas la même langue : en 2012, passer de MODIS (1 km) à VIIRS (375 m) crée un saut artificiel de **×4** dans les détections ; en 2001–2002, Terra volait seul ; et le **2 novembre 2026**, Suomi NPP a cessé de livrer de nouvelles données ! » *(À l'écran : courbe brute avec la cassure 2012 et le bruit des torchères.)*
* **0:30–1:15 — La Solution FirePulse :** « FirePulse nettoie d'abord les sources industrielles persistantes (21% des détections VIIRS au Gabon sont des torchères !), modélise séparément Terra seul, calibre MODIS sur VIIRS par loi de puissance, et assure le pont vers NOAA-20. » *(À l'écran : bascule du toggle torchères + activation de l'harmonisation avec ruban d'incertitude.)*
* **1:15–2:00 — Démonstration du Calendrier & des Anomalies :** Sélection du Gabon (ou zone dessinée), identification immédiate du régime bimodal (pic juillet–août) et d'un mois atypique réel (ex. janvier 2024 à `+323%` vs médiane ou octobre 2025 à `+151%`).
* **2:00–2:30 — La Preuve Scientifique :** Onglet *Méthodologie* — validation hors échantillon `2020–2025` montrant le gain réel (`MAE` réduit de `376.7` naïf → `122.1` ratio simple → **`103.1`** Power-Law, **`R² = 0.918`** ; et `MAPE = 11.7%` sur grille `0.25°`).
* **2:30–3:00 — Impact & Ouverture :** Export CSV complet prêt pour chercheurs/pompiers, dépôt open source reproductible.

---

## 10. Checklist Finale Avant Soumission (H42)

* [ ] Données réelles 2000–2025 + 2026 YTD intégrées (aucune donnée fictive non étiquetée)
* [ ] Masque statique torchères fonctionnel et documenté
* [ ] Régime `Terra-only` (2000–juin 2002) et pont `NOAA-20` (nov. 2026+) actifs et expliqués
* [ ] Évaluation hors échantillon `2020–2025` affichée dans l'UI avec limites assumées
* [ ] Calendrier accessible (daltoniens + gestion `médiane = 0` + mois partiels)
* [ ] Export CSV avec métadonnées opérationnel
* [ ] Démo locale de secours + URL HTTPS publique + vidéo 3 min + `README.md` reproductible
