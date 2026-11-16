# FirePulse — prévision MVP (climatologie)

Ce dossier produit la couche « Prévision » de `front-bis/` : une probabilité
mensuelle de détection d'au moins un feu de végétation en zone forestière,
par cellule `0,25°`, pour le Gabon et ses 9 provinces.

## Ce que le modèle fait

- **Cible** : `P(au moins une détection type 0 hors sources persistantes dans la
  cellule pendant le mois)`, restreinte aux cellules forestières.
- **Période** : `2012-02 → 2025-12` (VIIRS, capteur homogène). La série MODIS
  2000–2011 n'entre pas dans le modèle de probabilité à cause de la rupture de
  capteur ; elle reste la référence historique affichée dans le reste du produit.
- **Modèle** : fréquence mensuelle lissée `Beta(1, 4)` par cellule et mois
  calendaire, puis facteur de tendance provinciale conservateur
  (`2026–2035`, pente linéaire sur les mois-feu annuels, retrait de 50 %,
  borné à `0,75–1,25`).
- **Validation** : entraînement `2012–2019`, test `2020–2025`.
  - ROC-AUC mensuel : `0,898`
  - PR-AUC : `0,755`
  - Brier : `0,098`
  - Top 10 % des cellules-mois : `41,6 %` des positifs capturés
  - Top 20 % : `68,7 %`
- **Naturel** : FIRMS ne donne pas la cause d'ignition. La cible est
  « feu de végétation en zone forestière », pas « feu naturel ». Le masque
  forêt est un proxy statique.

## Données

### Masque forêt

Source : **ESA WorldCover 2021 v200**, 10 m, tuiles
`N00E009`, `N00E012`, `S03E009`, `S03E012`, `S06E009`, `S06E012`.

```powershell
$dir = "$env:TEMP\worldcover"
New-Item -ItemType Directory -Force $dir | Out-Null
foreach ($t in @('N00E009','N00E012','S03E009','S03E012','S06E009','S06E012')) {
  curl.exe -L --retry 3 -o "$dir\ESA_WorldCover_10m_2021_v200_${t}_Map.tif" `
    "https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/ESA_WorldCover_10m_2021_v200_${t}_Map.tif"
}
gdalbuildvrt -overwrite "$dir\worldcover_gabon.vrt" "$dir\ESA_WorldCover_10m_2021_v200_*_Map.tif"
gdalwarp -overwrite -t_srs EPSG:4326 -te 8.0 -4.5 15.0 3.0 -tr 0.0025 0.0025 `
  -r mode -ot Byte -srcnodata 0 -dstnodata 0 "$dir\worldcover_gabon.vrt" `
  "$dir\worldcover_gabon_250m.tif"
```

`build_forest_mask.py` agrège les pixels `250 m` en cellules `0,25°` :

- `forest_fraction` = part des pixels valides en classe `10` (tree cover) ou
  `95` (mangroves) ;
- `cropland_fraction` (classe `40`) et `builtup_fraction` (classe `50`) sont
  conservées pour un futur proxy « forêt peu anthropisée » ;
- seules les cellules dont le centroïde est dans le Gabon sont gardées ;
- le seuil `forest_fraction >= 0,30` définit les cellules forestières
  (`322` cellules sur `340`).

### Comptages de feux

`data/processed/grid-025/grid_025_monthly.csv`, colonne
`count_type0_unmasked`, agrégée par mois et cellule. Les mois sans ligne sont
traités comme zéro détection, avec la limite explicite : la couverture
d'observation FIRMS n'est pas exhaustive.

## Exécution

```bash
python -m pip install -r pipeline/requirements-prediction.txt
python -m pipeline.prediction.build_forest_mask
python -m pipeline.prediction.build_climatology
```

Sorties :

- `data/processed/prediction/forest_cells.csv`
- `data/processed/prediction/forest_manifest.json`
- `data/processed/prediction/prediction_cells.csv`
- `data/processed/prediction/prediction_monthly.csv`
- `data/processed/prediction/prediction_annual.csv`
- `data/processed/prediction/prediction_provinces.csv`
- `data/processed/prediction/prediction_metrics.json`
- `data/processed/prediction/prediction_manifest.json`
- `front-bis/src/data/prediction.json` (artefact compact pour l'interface)

## Limites

- Probabilité **climatologique**, pas une prévision météo : aucune pluie,
  température ou foudre n'est prédite.
- `type 0` = classification produit, pas validation terrain.
- Le masque forêt est statique (`2021`) : les changements de couvert ne sont
  pas modélisés.
- La couverture satellite n'est pas exhaustive (nuages, fumée, canopée).
- La tendance provinciale est un scénario conservateur, pas une prévision
  année par année.
- Les provinces à faible signal ont une incertitude plus large ; les métriques
  par province sont dans `prediction_metrics.json`.

## Interface

La section `#prediction` de `front-bis/` charge
`front-bis/src/data/prediction.json` de façon paresseuse. Elle propose :

- un calendrier `2026–2035` × `12 mois`, filtrable par province ;
- une carte SVG `0,25°` pour le mois sélectionné ;
- une fiche flottante au survol/clic d'une cellule ou d'une case du calendrier ;
- une fiche de confiance avec validation, calibration et limites.
