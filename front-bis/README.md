# FirePulse — front-bis

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
- **Récit scrollé** en 8 chapitres : le saut de 2012, le piège des torchères, la traduction
  MODIS → VIIRS, le calendrier, la carte, la preuve, le pont 2026 et l'explorateur.
- **Graphiques SVG animés** : série brute, série harmonisée, bande d'incertitude 80 %,
  annotations 2012 et août 2024.
- **Calendrier Années × Mois** accessible au clavier, avec détail du mois, rang historique,
  composition et export CSV.
- **Carte MapLibre** sans fond de carte externe : grille 0,25°, contours du Gabon et des
  provinces, sites statiques 0,05°, sélecteur de période et toggle torchères.
- **Motion design** : GSAP + ScrollTrigger + Lenis, révélations au scroll, compteurs animés,
  respect de `prefers-reduced-motion`.
- **Typographie** : Roboto (texte et titres) + Roboto Mono (labels), via `@fontsource`
  (Google Fonts), donc aucun appel réseau pour les polices.

## Données

Les données sont des **mocks réels** copiés depuis `frontend/src/mocks/` (eux-mêmes générés
depuis les CSV NASA FIRMS du Gabon) :

- `calendar-static.json` / `calendar-all.json` : séries mensuelles harmonisées.
- `hotspots-static.json` / `hotspots-all.json` : agrégats annuels de la grille 0,25° et
  cellules statiques 0,05°.
- `methodology.json` : paramètres et métriques hors échantillon.
- `regions.json` : Gabon + 9 provinces (GeoJSON).

Aucun appel réseau n'est nécessaire pour la démo. La carte ne charge pas de fond de carte
externe : elle est volontairement un « fond de données » sombre, pour rester disponible
hors ligne et pour mettre la grille en valeur.

## Provenance des chiffres

Aucun chiffre n'est inventé. La provenance est double :

- **Calculé dans l'application** depuis les JSON : séries mensuelles, médianes par mois
  calendaire, rangs historiques, anomalies, valeurs d'août 2024, statistiques de la carte,
  MAE/R² (`methodology.json`), points du globe et polygones de la carte.
- **Repris de la documentation du projet** (README, guide v2, audit M1/M2) et codés dans
  l'interface : `292 589` détections, `48` fichiers, `10` régions, saut `×3,9`,
  `21,2 %` de sources statiques VIIRS S-NPP, `31 298` détections statiques, `183` cellules
  masquées, `352` cellules actives, `42 482` cellules-mois et la résolution `0,25°`.

Les séries sont des **mocks reproductibles** : ils rejouent la chaîne baseline M2
(`filter_static`, power-law, intervalle conforme) à partir des CSV FIRMS réels du Gabon.
Ils ne sont pas un flux live. Le backend Django/PostGIS expose les mêmes endpoints ;
`front-bis` ne les appelle pas encore. Le port `5174` a été ajouté aux origines CORS du
backend (`settings.py`, `.env.example`, `docker-compose.yml`) pour préparer ce mode.

## Notes

- Les chiffres affichés proviennent de la baseline harmonisée `v2.0`, encore en revue M1.
- Le projet est un **prototype de preuve de concept**, pas un produit opérationnel.
- NASA n'endosse pas ce projet.
