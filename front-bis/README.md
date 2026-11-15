# FirePulse — front-bis

Diagnostic exploratoire 2020–2025 sur les fichiers pays, avec masque gelé en 2017 : 21 199 / 111 719 détections type 0 (19,0 %), dont 9 206 / 48 075 S-NPP (19,1 %), sont dans des cellules ajoutées au masque rétrospectif 2000–2025. Ces proportions décrivent des détections situées dans des cellules, pas des torchères confirmées, des taux d'erreur ou une contamination causale ; le masque rétrospectif utilise les données de test et la couverture demeure inconnue.

> **État scientifique : en revue.** Les chiffres et descriptions de la section « validation renforcée » ci-dessous décrivent l'artefact historique, antérieur aux corrections du script. Ils ne constituent pas une validation indépendante ni une garantie de couverture. Le masque de cet ancien artefact utilise les données de calibration, la couverture mensuelle des observations est inconnue, et la période de test a déjà été examinée. Ne pas utiliser ces chiffres comme résultats de la méthode corrigée ; une régénération versionnée et une revue M1/M2/M3 restent nécessaires.

Une expérience narrative immersive (3D + motion design) autour du calendrier
harmonisé des points chauds du Gabon, pour le défi NASA Space Apps 2026
« Harmonization of MODIS and VIIRS Hot Spots ».

## Lancer

```bash
cd front-bis
npm install
npm run dev
```

L'application tourne sur `http://localhost:5174`.

## Construire

```bash
npm run build
npm run preview
```

## Ce qu'il y a dedans

- **Globe 3D** en Three.js : étoiles, graticule, orbites des capteurs, contour du Gabon,
  points chauds en particules additives.
- **Récit scrollé** en 6 temps (ouverture + 5 étapes) : le saut de 2012, les sources
  persistantes, la traduction MODIS → VIIRS, le calendrier, la carte, puis la preuve
  renforcée et le relais 2026.
- **Graphiques SVG animés** : vues par capteur (MODIS, S-NPP, NOAA-20), série harmonisée
  expérimentale, bande d'incertitude 80 %, annotations 2012 et août 2024.
- **Calendrier Années × Mois** accessible au clavier, avec détail du mois, rang historique,
  composition et export CSV.
- **Carte MapLibre** sans fond de carte externe : grille 0,25°, contours du Gabon et des
  provinces, cellules candidates 0,05°, sélecteur de période et toggle sources persistantes.
- **Fiche de confiance** sous les séries et la carte, et version complète dans la section
  preuve : source, période, capteur, protocole, couverture et limites.
- **Motion design** : GSAP + ScrollTrigger + Lenis, révélations au scroll, compteurs animés,
  respect de `prefers-reduced-motion`.
- **Typographie** : Roboto (texte et titres) + Roboto Mono (labels), via `@fontsource`
  (Google Fonts), donc aucun appel réseau pour les polices.

## Données et connexion API

`front-bis` consomme directement l'API Django / PostgreSQL / PostGIS (`/api/v1/`) via le
proxy Vite (`localhost:8000`) et bascule automatiquement vers des instantanés locaux
(`src/data/*.json`) si le backend est indisponible ou si
`VITE_USE_MOCKS=true` est défini. Leur synchronisation avec la base et la provenance
des réponses doivent être vérifiées pour chaque exécution :

- `/api/v1/health/` (`health.json`) : état PostGIS et compteurs globaux en base.
- `/api/v1/calendar/` (`calendar-static.json` / `calendar-all.json`) : séries mensuelles
  harmonisées (`filter_static=true` et `false`) et médianes de référence `2001–2025`.
- `/api/v1/hotspots/?mode=grid&agg=cell` (`hotspots-static.json` / `hotspots-all.json`) :
  grille `0,25°` et masque des `183` cellules candidates `0,05°`.
- `/api/v1/methodology/` (`methodology.json` / `methodology-raw.json`) : paramètres
  et métriques historiques `2020–2025`, pour une période déjà examinée.
- `/api/v1/coverage/` (`coverage.json`) : couverture temporelle des capteurs ingérés.
- `/api/v1/regions/` (`regions.json`) : Gabon (`GA`) + `9` provinces (GeoJSON).
- `/api/v1/export/` : export CSV aux colonnes exactes du contrat API (avec repli client
  conforme hors-ligne).

La carte ne charge pas de fond de carte externe : elle utilise un « fond de données » sombre
avec graticule et contours administratifs issus de PostGIS.

## Provenance des chiffres

Les chiffres ci-dessous décrivent un état historique de la base et de ses calculs.
Ils ne prouvent pas la provenance des données affichées lors d'une exécution actuelle :
l'API peut être partielle et le front peut utiliser des instantanés locaux. Les deux
périmètres géographiques historiques sont :

- **Archive FIRMS SP ingérée (BBox Gabon, 48 fichiers, 2000-11 → 2025-12)** : `292 589`
  détections (`59 282` MODIS, `147 745` VIIRS S-NPP, `85 562` VIIRS NOAA-20), `10` régions,
  `42 482` cellules-mois (`18 775` filtrées + `23 707` brutes), `6 011` lignes mensuelles
  harmonisées, `183` cellules candidates `0,05°`, `352` cellules actives `0,25°` dans `GA`
  (`355` au total dans la BBox).
- **Polygone officiel Gabon `GA` (`ST_Within`, base de `/calendar/` et `/methodology/`)** :
  `285 013` détections (`57 732` MODIS, `143 894` VIIRS S-NPP, `83 387` NOAA-20), dont
  `175 500` détections `type 0` hors cellules candidates retenues (`filter_static=true`,
  `61,6 %`) et `109 513` écartées (`38,4 %`). Cette exclusion se décompose en `57 934`
  détections `type 2/3` (`20,3 %`) et `51 579` détections `type 0` dans les `183` cellules
  candidates `0,05°` (`18,1 %`). Ce sont des cellules candidates, pas des torchères
  confirmées une par une.
- **Évaluation historique exploratoire (`GA`, `filter_static=true`, méthode `v2.0`)** : entraînement
  `2012-02 → 2019-12` (`95` mois, ratio global `×3,93` hors statiques / `×4,65` en brut),
  test `2020-01 → 2025-12` (`72` mois) : Naïf MAE `355,7` (`R² 0,143`) → Power-law `log1p`
  MAE `100,9` (`R² 0,919`, biais `+41,8`).
- **Validation renforcée** : les chiffres de `validation.json` sont calculés sur les 48 CSV
  pays selon le protocole historique décrit ci-dessous. Ce sont des résultats exploratoires,
  sans validation indépendante ; ils ne décrivent pas le résultat du script corrigé.

## Analyse exploratoire historique et protocole corrigé

Le script `scripts/validate_harmonization.py` relit les **48 CSV FIRMS pays** et produit
`src/data/validation.json` + `src/data/validation_series.csv`. Le protocole corrigé vise à
traiter plusieurs limites du benchmark DB `v2.0` :

1. **masque de cellules candidates gelé sur `2000–2017`** — avant la calibration et le test ;
   le masque all-years sert à explorer l'effet du look-ahead ;
2. **split en trois temps** — entraînement `2012-02 → 2017-12` (`71` mois), calibration
   `2018-01 → 2019-12` (`24` mois), test `2020-01 → 2025-12` (`72` mois) ;
3. **évaluation sur les anomalies** — le R² brut est gonflé par la saisonnalité ; on ajoute
   une baseline saisonnière et un capteur tenu à l'écart (NOAA-20), plus un contrôle négatif
   Terra → Aqua.

```bash
# depuis la racine du dépôt
python front-bis/scripts/validate_harmonization.py
```

Résultats de l'artefact historique, antérieur aux corrections du script : ils sont
exploratoires et ne constituent pas les résultats d'un nouveau run du protocole corrigé.
Son masque inclut la période de calibration et le test a déjà été examiné :

| Question | Résultat |
|---|---|
| Power-law vs OLS sur les anomalies (test) | R² **0,788** vs **0,733** |
| Power-law vs ratio global / ratio saisonnier | R² **0,788** vs 0,671 / 0,640 |
| Power-law vs naïf | MAE **120,8** vs **460,3** · R² brut 0,918 vs 0,079 |
| Couverture 80 % nominale, calibrée sur 2018–2019 | **63,9 %** sur 2020–2025 (la couverture « leaky » 79,2 % est tautologique) |
| Masque gelé vs all-years | **61** vs **183** cellules · MAE **120,8** vs **96,7** (+24,1 de look-ahead) |
| Capteur tenu à l'écart NOAA-20 | MAE **100,1** · R² brut **0,956** · R² anomalies **0,867** |
| Contrôle négatif Terra → Aqua | MAE **428,7** · R² anomalies **−0,241** |
| Haute saison (juin–octobre) vs basse saison | R² anomalies **0,797** vs **0,549** |
| Sensibilité du masque (10/24, 20/48, 30/72) | R² anomalies **0,860 / 0,788 / 0,792** |

Ce que cela change dans le discours :

- **On ne dit plus « R² = 0,92 »** sans préciser que c'est le R² brut, gonflé par la saison.
  Le résultat historique exploratoire pour l'anomalie est **0,79**.
- **On ne dit plus « intervalle 80 % »** sans dire que la couverture empirique est **63,9 %**.
  C'est une limite, pas un argument de vente.
- **On ne dit plus « le masque est statique »** sans dire qu'un masque gelé coûte **+24 MAE**
  et qu'il doit être rafraîchi en production.
- **On assume le contrôle négatif** Terra → Aqua : le transfert de plateforme n'est pas
  gratuit, donc on ne le revendique pas.

## Ce qui nous démarque

- **Un protocole en revue** : 3 temps, masque gelé, calibration séparée,
  couverture mesurée, baseline saisonnière.
- **Les résultats négatifs sont publiés** : Terra → Aqua échoue, la couverture est de 63,9 %,
  le masque all-years flatte la MAE. Ces résultats restent exploratoires et à réévaluer.
- **Un produit complet** : calendrier accessible, carte 0,25°, anomalies, CSV, API
  Django/PostGIS, mode snapshot hors-ligne, et fiche de confiance par résultat.
- **Des pistes de transfert à évaluer** : Bassin du Congo, FRP, NOAA-21, surface brûlée.

## Notes

- Le benchmark DB `v2.0` (MAE `100,9`, R² `0,919`, masque all-years) et la validation
  renforcée (MAE `120,8`, R² anomalies `0,788`, masque gelé) ne partagent pas le même
  protocole. Les deux sont historiques et exploratoires ; aucun ne constitue une preuve
  indépendante ni ne garantit les résultats d'une exécution actuelle.
- La provenance des chiffres affichés dépend des réponses API et des replis locaux et doit
  être vérifiée. L'artefact historique utilise les CSV pays sans jointure géométrique,
  contrairement au périmètre `GA` du benchmark historique : ces résultats ne sont pas
  directement comparables et l'ampleur des écarts n'est pas établie.
- Le projet est un **prototype de preuve de concept**, pas un produit opérationnel.
- NASA n'endosse pas ce projet.
