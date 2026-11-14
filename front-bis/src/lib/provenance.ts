/**
 * Métadonnées vérifiées directement contre PostgreSQL/PostGIS (`firepulse`)
 * et les 48 fichiers FIRMS SP ingérés pour le Gabon (archive 2000-11 → 2025-12).
 *
 * Distinction stricte des deux périmètres géographiques :
 * 1) Archive ingérée (48 CSV SP, BBox Gabon) : 292 589 détections.
 * 2) Polygone officiel Natural Earth `GA` (`ST_Within`, base de `/calendar/` & `/methodology/`) :
 *    285 013 détections (7 576 détections côtières/frontalières hors polygone `GA`),
 *    dont 175 500 retenues avec `filter_static=true` et 109 513 écartées (`type != 0` ou masque 0,05°).
 *
 * Les séries calendaires, métriques hors échantillon, grille 0,25°, couverture capteurs et
 * santé base sont chargées dynamiquement depuis `/api/v1/` avec repli sur le snapshot DB v2.0.
 */
export const provenance = {
  files: 48,
  regions: 10,
  maskedCells: 183,
  gaGridCells: 352,
  totalGridCells: 355,
  gridCellMonths: 42_482,
  gridCellMonthsFiltered: 18_775,
  gridCellMonthsRaw: 23_707,
  harmonizedMonthsRows: 6_011,
  gridDeg: 0.25,
  staticGridDeg: 0.05,
  archiveStart: '2000-11',
  archiveEnd: '2025-12',
  snppOperationalEndDate: '2026-11-02',
  archive: {
    totalDetections: 292_589,
    modisDetections: 59_282,
    modisTerraDetections: 23_907,
    modisAquaDetections: 35_375,
    snppDetections: 147_745,
    noaa20Detections: 85_562,
    filteredTotal: 110_276,
    type23Total: 58_223,
    snppType23Count: 31_298,
    snppType23Share: 21.2,
    noaa20Type23Count: 20_267,
    noaa20Type23Share: 23.7,
    modisType23Count: 6_658,
    modisType23Share: 11.2,
    confHigh: 16_953,
    confNominal: 266_240,
    confLow: 9_396,
  },
  ga: {
    totalDetections: 285_013,
    cleanDetections: 175_500,
    filteredTotal: 109_513,
    modisDetections: 57_732,
    snppDetections: 143_894,
    noaa20Detections: 83_387,
    snppFilteredCount: 57_178,
    snppType23Count: 31_110,
    snppType0InMaskCount: 26_068,
    noaa20Type23Count: 20_171,
    modisType23Count: 6_653,
    totalType23Count: 57_934,
    totalType0InMaskCount: 51_579,
    modis2017Type23Count: 0,
    confHigh: 16_442,
    confNominal: 259_545,
    confLow: 9_026,
  },
} as const
