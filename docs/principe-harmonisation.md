# Principe de l'harmonisation MODIS → VIIRS (FirePulse)

En deux mots : **on traduit 25 ans d'observations prises par des caméras satellitaires différentes dans une seule « unité commune »**, afin de savoir si l'activité des feux augmente ou diminue réellement — au lieu de mesurer un changement de capteur.

---

## 1. Le problème de départ

La NASA a utilisé plusieurs générations de capteurs qui n'ont pas la même finesse spatiale :

- **MODIS (`1 km/pixel`)** : Terra seul à partir de `2000-11`, puis Terra + Aqua à partir de `2002-07`. Sa résolution plus grossière laisse passer une grande partie des petits feux.
- **VIIRS S-NPP (`375 m/pixel`, depuis `2012-02`)** : beaucoup plus sensible — au Gabon (avec filtre des sources fixes), il détecte en moyenne **~3,93 fois** plus de points chauds que MODIS (`global_ratio_alpha = 3.9328`).
- **VIIRS NOAA-20 (depuis `2018-04`)** : assure la continuité après la coupure S-NPP annoncée le **`2026-11-02`**.

Sans harmonisation, un graphique brut fait apparaître une explosion artificielle en 2012 alors qu'il s'agit d'un changement d'instrument — sans compter les torchères et sites industriels fixes qui génèrent des détections thermiques toute l'année.

---

## 2. Comment fonctionne l'harmonisation dans FirePulse

Dans l'implémentation baseline actuelle ([`build_baseline_series.py`](../backend/apps/harmonization/management/commands/build_baseline_series.py)), on choisit **VIIRS S-NPP `375 m` comme échelle de référence unique** (`VIIRS_375m_SNPP_equiv`), et on exploite la période de recouvrement où **MODIS et VIIRS observent ensemble** (`2012–2025`) pour apprendre la fonction de conversion.

### Étape 1 — Filtrer les sources fixes (`filter_static=true`)
On conserve les feux probables (`hotspot_type = 0`) et on exclut **`183`** cellules persistantes de `0.05°` (torchères/sites industriels, identifiés par `type23_count >= 20` ou `active_months_snpp >= 48`).

> Sans ce filtre au Gabon, même le modèle par ratio global décroche sur `2020–2025` (`R² = 0.726` sans filtre contre `0.8781` avec filtre).

### Étape 2 — Apprendre sur le recouvrement et évaluer après
On ajuste les modèles sur **`2012-02` → `2019-12`** (`95` mois d'apprentissage) et on calcule des métriques sur **`2020-01` → `2025-12`** (`72` mois de test). Ces résultats historiques sont exploratoires : la période de test a servi à d'autres choix et ne constitue pas une validation indépendante.

Au lieu de simplement multiplier MODIS par un facteur constant (`3,93`), ce qui surestime ou sous-estime selon les saisons (basse saison vs pic sec), FirePulse ajuste une **loi de puissance en échelle logarithmique** (`power_law_log1p`) :

$$
\hat{y} = \exp\big(p \cdot \ln(1 + x) + q\big) - 1
$$

Chiffres historiques exploratoires au Gabon (`GA`, `filter_static=true`, `v2.0`) :
- **MODIS Terra + Aqua (`power_law_log1p`) :** `p = 0.9438`, `q = 1.6529`
- **MODIS Terra seul (`terra_only_power_law`, avant `2002-07`) :** `p = 0.691`, `q = 3.6809`
- **Évaluation `2020–2025` (`GA`, `filter_static=true`) :** l'erreur moyenne (`MAE`) passe de **`355.72`** (`naive`, `R² = 0.1426`) à **`100.87`** (`power_law_log1p`, **`R² = 0.9189`**).

### Étape 3 — Tracer une bande d'incertitude nominale à 80 %
Pour le passé reconstruit depuis MODIS (`2000–2012`), on quantifie l'écart résiduel en log (`conformal_q80_log = 0.5309`, `conformal_q80_terra_log = 0.6445`) afin de tracer une bande d'incertitude `[ci_low, ci_high]` autour de la courbe estimée. Dans la baseline historique, le quantile utilise les résidus de la période de test : la couverture indépendante n'est pas démontrée. Une cible nominale de 80 % ne garantit pas une couverture de 80 %, notamment pour des séries temporelles.

### Étape 4 — Recoller la chronologie (`2000` → `2026+`) et calculer les anomalies
1. `2000-11` → `2002-06` : MODIS Terra seul → converti en équivalent S-NPP (`terra_only_power_law` + bande 80 %).
2. `2002-07` → `2012-01` : MODIS Terra + Aqua → converti en équivalent S-NPP (`power_law_log1p` + bande 80 %).
3. `2012-02` → `2026-10` : VIIRS S-NPP direct (aucune conversion, c'est l'échelle de référence).
4. `2026-11+` : VIIRS NOAA-20 divisé par le ratio inter-capteurs mesuré sur `2019–2025` (`noaa20_to_snpp_ratio = 1.0381`, avec bande d'incertitude `±10 %`).

Une fois les 25+ années exprimées dans la même unité, chaque mois est comparé à sa **médiane historique `2001–2025` du même mois calendaire** (par exemple août comparé aux 25 mois d'août de référence) pour calculer les **anomalies** (`%` et absolues).

---

## 3. Statut scientifique (`v2.0` vs validation M1)

La version `v2.0` présente dans Django constitue le socle baseline de démonstration. L'équipe M1 audite ces éléments (voir [`methodology.md`](methodology.md), [`limitations.md`](limitations.md) et [`HANDOFF.md`](HANDOFF.md)) : calibration du quantile conforme sur la fenêtre de test, seuils du masque statique, et comportement sur les provinces à faible signal. L'export consolidé produit par [`export_calibration_series.py`](../backend/apps/harmonization/management/commands/export_calibration_series.py) (et déposé localement dans `data/backups/m1-benchmark-validation/`) fournit les séries mensuelles exactes pour cet audit.
