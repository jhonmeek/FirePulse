/**
 * Chiffres de cadrage repris de la documentation du projet — pas des valeurs inventées.
 *
 * Sources :
 * - README.md (racine) : 292 589 détections, 48 fichiers, 10 régions,
 *   42 482 cellules-mois, 183 cellules statiques, 352 cellules actives.
 * - Guide_FirePulse_NASA_Space_Apps_2026_v2.md : saut ×3,9, 21,2 % de sources
 *   statiques VIIRS S-NPP, 31 298 détections statiques S-NPP.
 * - data/raw/gabon : 59 282 MODIS, 147 745 S-NPP, 85 562 NOAA-20.
 * - backend : baseline harmonisée v2.0 (power-law, masque 0,05°, grille 0,25°).
 *
 * Les séries, médianes, rangs, anomalies et métriques MAE/R² ne sont PAS codés ici :
 * ils sont lus dans les JSON générés depuis les CSV FIRMS (voir src/lib/data.ts).
 */
export const provenance = {
  totalDetections: 292_589,
  modisDetections: 59_282,
  snppDetections: 147_745,
  noaa20Detections: 85_562,
  files: 48,
  regions: 10,
  sensorJump: '×3,9',
  snppStaticShare: 21.2,
  noaa20StaticShare: 23.7,
  modisStaticShare: 11.2,
  snppStaticCount: 31_298,
  noaa20StaticCount: 20_267,
  modisStaticCount: 6_658,
  maskedCells: 183,
  gridCells: 352,
  gridCellMonths: 42_482,
  gridDeg: 0.25,
  staticGridDeg: 0.05,
} as const
