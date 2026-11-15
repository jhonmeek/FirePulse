# Principe de l'harmonisation MODIS → VIIRS (FirePulse)

> **Version** : baseline `v2.0` (produit live) + **validation renforcée** (novembre 2026).  
> **En deux mots** : on traduit 25 ans d'observations prises par des caméras satellitaires différentes dans une seule « unité commune », afin de savoir si l'activité des feux augmente ou diminue réellement — au lieu de mesurer un changement de capteur.

---

## 0. Deux protocoles, deux usages

FirePulse distingue désormais deux choses :

| | **Baseline `v2.0`** | **Validation renforcée** |
|---|---|---|
| **Usage** | Calendrier live, API, carte, CSV | Preuve scientifique, audit, pitch |
| **Masque statique** | `183` cellules, construit sur `2000–2025` | `61` cellules, **gelé sur `2000–2019`** |
| **Apprentissage** | `2012-02 → 2019-12` (`95` mois) | `2012-02 → 2017-12` (`71` mois) |
| **Calibration** | — | `2018-01 → 2019-12` (`24` mois) |
| **Test** | `2020-01 → 2025-12` (`72` mois) | `2020-01 → 2025-12` (`72` mois) |
| **Intervalle conforme** | q80 appris sur les résidus de test | q80 appris sur `2018–2019`, couverture mesurée sur `2020–2025` |
| **Artefact** | `methodology.json` / API | [`validation.json`](../front-bis/src/data/validation.json) |
| **Statut** | Référence du produit live | Protocole de preuve |

Le calendrier et la carte restent sur la **baseline `v2.0`** pour rester cohérents avec l'existant. La validation renforcée est un **artefact séparé** : elle ne modifie pas les séries affichées, elle mesure ce que la baseline ne pouvait pas prouver.

---

## 1. Le problème de départ

La NASA a utilisé plusieurs générations de capteurs qui n'ont pas la même finesse spatiale :

- **MODIS (`1 km/pixel`)** : Terra seul à partir de `2000-11`, puis Terra + Aqua à partir de `2002-07`. Sa résolution plus grossière laisse passer une grande partie des petits feux.
- **VIIRS S-NPP (`375 m/pixel`, depuis `2012-02`)** : beaucoup plus sensible — au Gabon (avec filtre des sources fixes), il détecte en moyenne **~3,93 fois** plus de points chauds que MODIS (`global_ratio_alpha = 3.9328`).
- **VIIRS NOAA-20 (depuis `2018-04`)** : assure la continuité après l'arrêt de livraison **S-NPP** du **`2026-11-02`**.

Sans harmonisation, un graphique brut fait apparaître une explosion artificielle en 2012 alors qu'il s'agit d'un changement d'instrument — sans compter les torchères et sites industriels fixes qui génèrent des détections thermiques toute l'année.

---

## 2. La baseline `v2.0` — le produit live

Dans l'implémentation baseline actuelle ([`build_baseline_series.py`](../backend/apps/harmonization/management/commands/build_baseline_series.py)), on choisit **VIIRS S-NPP `375 m` comme échelle de référence unique** (`VIIRS_375m_SNPP_equiv`), et on apprend la conversion sur la période de recouvrement `2012–2019`. Les années `2020–2025` sont tenues à l'écart pour l'évaluation.

### Étape 1 — Filtrer les sources fixes (`filter_static=true`)

On conserve les feux probables (`hotspot_type = 0`) et on exclut **`183`** cellules persistantes de `0.05°` (torchères/sites industriels, identifiés par `type23_count >= 20` ou `active_months_snpp >= 48`).

> Sans ce filtre au Gabon, même le modèle par ratio global décroche sur `2020–2025` (`R² ≈ 0,73` sans filtre contre `≈ 0,88` avec filtre).

### Étape 2 — Apprendre sur le recouvrement et évaluer après

On ajuste les modèles sur **`2012-02` → `2019-12`** (`95` mois d'apprentissage) et on mesure leur performance hors échantillon sur **`2020-01` → `2025-12`** (`72` mois de test).

Au lieu de simplement multiplier MODIS par un facteur constant (`3,93`), ce qui surestime ou sous-estime selon les saisons (basse saison vs pic sec), FirePulse ajuste une **loi de puissance en échelle logarithmique** (`power_law_log1p`) :

$$
\hat{y} = \exp\big(p \cdot \ln(1 + x) + q\big) - 1
$$

Chiffres de la baseline `v2.0` au Gabon (`GA`, `filter_static=true`, export `methodology.json`) :

- **MODIS Terra + Aqua (`power_law_log1p`) :** `p ≈ 0,944`, `q ≈ 1,653`
- **MODIS Terra seul (`terra_only_power_law`, avant `2002-07`) :** `p ≈ 0,691`, `q ≈ 3,681`
- **Évaluation `2020–2025` :** MAE `≈ 355,6` (`naive`, `R² ≈ 0,143`) → `≈ 100,8` (`power_law_log1p`, `R² ≈ 0,919`, biais `≈ +41,8`).

> Le doc historique indiquait `355,72 → 100,87`, `R² 0,1426 → 0,9189`, `q80 = 0,5309`. L'export `methodology.json` actuel donne `355,6 → 100,81`, `R² 0,1428 → 0,9189`, `q80 = 0,5239`. Les écarts sont des arrondis/versions ; c'est l'export qui fait foi pour le produit.

### Étape 3 — Ajouter la marge d'erreur (intervalle conforme 80 %)

Pour le passé reconstruit depuis MODIS (`2000–2012`), on quantifie l'écart résiduel en log (`conformal_q80_log ≈ 0,524`, `conformal_q80_terra_log = 0,6445`) afin de tracer une bande d'incertitude `[ci_low, ci_high]` autour de la courbe estimée.

**Limite de la `v2.0` :** ce quantile est calibré sur les résidus de la fenêtre de test. La couverture de 80 % est donc tautologique sur cette fenêtre. C'est précisément ce que la validation renforcée corrige.

### Étape 4 — Recoller la chronologie (`2000` → `2026+`) et calculer les anomalies

1. `2000-11` → `2002-06` : MODIS Terra seul → converti en équivalent S-NPP (`terra_only_power_law` + bande 80 %).
2. `2002-07` → `2012-01` : MODIS Terra + Aqua → converti en équivalent S-NPP (`power_law_log1p` + bande 80 %).
3. `2012-02` → `2026-10` : VIIRS S-NPP direct (aucune conversion, c'est l'échelle de référence).
4. `2026-11+` : VIIRS NOAA-20 divisé par le ratio inter-capteurs mesuré sur `2019–2025` (`noaa20_to_snpp_ratio = 1.0381`, avec bande d'incertitude `±10 %`).

Une fois les 25+ années exprimées dans la même unité, chaque mois est comparé à sa **médiane historique `2001–2025` du même mois calendaire** (par exemple août comparé aux 25 mois d'août de référence) pour calculer les **anomalies** (`%` et absolues).

---

## 3. La validation renforcée — le protocole de preuve

Cette validation est produite par [`validate_harmonization.py`](../front-bis/scripts/validate_harmonization.py) et publiée dans [`validation.json`](../front-bis/src/data/validation.json). Elle ne remplace pas la baseline `v2.0` : elle vérifie si la conversion tient **hors échantillon**, sans look-ahead.

### 3.1 Masque statique gelé sur `2000–2019`

Le masque de la `v2.0` est construit sur toute l'archive `2000–2025` : il connaît donc les torchères de `2020–2025`. Pour la validation, il est reconstruit **uniquement sur `2000–2019`**, puis appliqué au test.

| | Masque gelé | Masque all-years |
|---|---:|---:|
| Cellules `0,05°` | **61** | **183** |
| MAE test `2020–2025` | **120,8** | **96,7** |
| Coût du look-ahead | — | **+24,1 MAE** |

C'est la preuve que le masque all-years flatte la performance. En production, le masque doit être **rafraîchi régulièrement** ; un masque figé une fois pour toutes n'est pas suffisant.

### 3.2 Split en trois temps

| Étape | Période | Mois |
|---|---|---:|
| Entraînement | `2012-02` → `2017-12` | `71` |
| Calibration | `2018-01` → `2019-12` | `24` |
| Test | `2020-01` → `2025-12` | `72` |

Le quantile conforme est appris sur `2018–2019`, jamais sur `2020–2025`. Le test reste intact.

### 3.3 Résultats par modèle

Test `2020–2025`, masque gelé, métriques sur les comptages et sur les **anomalies** (écart à la baseline saisonnière apprise sur `2012–2017`) :

| Modèle | MAE | R² brut | R² anomalies |
|---|---:|---:|---:|
| Naïf (`V = M`) | 460,3 | 0,08 | −1,37 |
| Ratio global | 147,4 | 0,87 | 0,67 |
| Ratio saisonnier | 147,1 | 0,86 | 0,64 |
| OLS linéaire | 133,1 | 0,90 | 0,73 |
| **Power-law log1p** | **120,8** | **0,92** | **0,79** |
| Baseline saisonnière | 238,8 | 0,61 | 0,00 |

**Lecture :** le R² brut est gonflé par le cycle saisonnier, que les deux capteurs voient de toute façon. Le **R² anomalies** est le vrai test : le power-law (0,79) bat l'OLS (0,73), le ratio global (0,67) et le ratio saisonnier (0,64). La baseline saisonnière a un R² anomalies nul par construction : elle ne capte que la saison, pas les écarts interannuels.

### 3.4 Intervalle conforme : le résultat honnête

| Quantile | Valeur | Couverture test |
|---|---:|---:|
| q80 calibré sur `2018–2019` | 0,310 | **63,9 %** |
| q90 calibré sur `2018–2019` | 0,360 | **66,7 %** |
| q80 « leaky », calibré sur le test | 0,439 | 79,2 % (tautologique) |

Le nominal de 80 % **n'est pas atteint hors échantillon** : la couverture réelle est `63,9 %`. Les résidus de `2020–2025` sont plus larges que ceux de `2018–2019`. La couverture « leaky » de 79,2 % est donnée uniquement pour comparaison ; elle ne doit pas être présentée comme une validation.

**Conséquence produit :** la bande du calendrier live reste celle de la `v2.0` (choix de cohérence avec l'existant). La validation montre qu'elle est **trop étroite** ; c'est affiché dans la section « Preuve » de l'application.

### 3.5 Capteur tenu à l'écart : NOAA-20

Le power-law est entraîné sur MODIS → S-NPP. NOAA-20 n'est **pas** utilisé pour l'entraînement. Le ratio NOAA-20 / S-NPP est calibré sur `2018–2019`, puis appliqué au test `2020–2025`.

| Indicateur | Valeur |
|---|---:|
| MAE NOAA-20 | **100,1** |
| R² brut | **0,956** |
| R² anomalies | **0,867** |

C'est la validation inter-capteurs la plus convaincante : le modèle généralise à un capteur qu'il n'a jamais vu.

### 3.6 Contrôle négatif : Terra → Aqua

On apprend un modèle sur Terra → S-NPP, puis on l'applique à Aqua → S-NPP. Résultat :

| Indicateur | Valeur |
|---|---:|
| MAE | **428,7** |
| R² brut | 0,518 |
| R² anomalies | **−0,241** |

Le transfert de plateforme **échoue**. C'est un résultat négatif assumé : il montre que les deux plateformes MODIS ne sont pas interchangeables et que la calibration doit rester explicite. Il ne remet pas en cause le modèle principal (MODIS Terra + Aqua combiné), mais il interdit de revendiquer une transférabilité gratuite.

### 3.7 Par saison et sensibilité du masque

| Saison | MAE | R² anomalies |
|---|---:|---:|
| Haute saison (juin–octobre) | 200,3 | **0,797** |
| Basse saison (novembre–mai) | 63,9 | **0,549** |

Le modèle est plus faible en basse saison : les anomalies de saison sèche sont plus faciles à détecter que les mois calmes.

| Seuils du masque | Cellules | MAE | R² anomalies |
|---|---:|---:|---:|
| Permissif `10 / 24` | 258 | 88,5 | 0,860 |
| Référence `20 / 48` | 61 | 120,8 | 0,788 |
| Strict `30 / 72` | 57 | 120,3 | 0,792 |

Le permissif est meilleur sur le test, mais le choisir **sur le test** serait une faute méthodologique. Cette table est une sensibilité, pas une sélection.

### 3.8 Ce que la validation prouve — et ce qu'elle ne prouve pas

**Ce qu'elle prouve :**

- le power-law bat les baselines sur les **anomalies** (0,79 vs 0,73 / 0,67 / 0,64) ;
- il généralise à **NOAA-20** (0,87) ;
- le signal est stable quand on change les seuils du masque (0,79–0,86) ;
- le protocole est reproductible : masque gelé, split 3 temps, calibration séparée, couverture mesurée.

**Ce qu'elle ne prouve pas :**

- le nominal 80 % n'est pas atteint (couverture `63,9 %`) ;
- le masque gelé coûte `+24,1 MAE` par rapport à un masque qui connaît le futur ;
- Terra → Aqua échoue (R² anomalies `−0,241`) ;
- le pont NOAA-20 post-2026 reste une **projection**, pas une validation ;
- les comptages ne sont pas une mesure physique : la FRP et la surface brûlée sont les prochaines étapes ;
- la calibration reste nationale ; les provinces à faible signal ne sont pas calibrées séparément.

---

## 4. Statut scientifique et prochaines étapes

La `v2.0` est un **socle de démonstration** pour le produit live. Ses limites sont connues : intervalle conforme calibré sur le test, masque construit sur toute l'archive, choix de modèle appuyé sur la fenêtre `2020–2025`. L'équipe M1 audite ces éléments (voir [`methodology.md`](methodology.md), [`limitations.md`](limitations.md) et [`HANDOFF.md`](HANDOFF.md)).

La **validation renforcée** répond à trois de ces limites : masque gelé, split 3 temps, calibration séparée. Elle ajoute une baseline saisonnière, un capteur tenu à l'écart et un contrôle négatif. Elle reste un travail de validation **interne** : pas encore de NOAA-21, pas encore de surface brûlée, pas encore de FRP.

Prochaines étapes :

1. **NOAA-21** (2023+) comme second capteur tenu à l'écart.
2. **Surface brûlée** MCD64A1 / VNP64A1 pour une validation indépendante des comptages.
3. **FRP** (fire radiative power) comme métrique physique complémentaire.
4. **Bassin du Congo** : 6–10 pays, même protocole, validation régionale.
5. **Masque opérationnel** rafraîchi périodiquement, avec une version probabiliste plutôt que binaire.
6. **Modèle hiérarchique** pour les provinces à faible signal.

L'export consolidé [`export_calibration_series.py`](../backend/apps/harmonization/management/commands/export_calibration_series.py) et les fichiers de `data/backups/m1-benchmark-validation/` fournissent les séries mensuelles exactes pour l'audit M1.

---

## 5. Reproduction

Depuis la racine du dépôt :

```bash
python front-bis/scripts/validate_harmonization.py
```

Sorties :

- [`front-bis/src/data/validation.json`](../front-bis/src/data/validation.json) — résultats complets (split, masque, modèles, conformité, capteurs tenus à l'écart, saisons, sensibilité, SHA-256 des 48 CSV) ;
- [`front-bis/src/data/validation_series.csv`](../front-bis/src/data/validation_series.csv) — série de test observée et prédictions.

Le script ne modifie aucune donnée source. Il utilise uniquement la bibliothèque standard Python (`3.10+`) et les 48 CSV FIRMS pays du Gabon.
