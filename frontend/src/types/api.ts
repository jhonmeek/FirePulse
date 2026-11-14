/**
 * Contrat API FirePulse v1 — miroir TypeScript de `docs/api-contract.json` (v2.1.0),
 * vérifié ligne à ligne contre `backend/apps/api/views.py`.
 * Toute évolution passe d'abord par M2 (contrat + vues), puis ici.
 *
 * Conventions :
 * - Mois au format `YYYY-MM`, dates au format `YYYY-MM-DD`.
 * - `null` = capteur absent / pas de donnée ce mois-là. `0` = capteur actif, zéro détection.
 * - Valeurs harmonisées en « détections équivalentes VIIRS 375 m S-NPP ».
 */

import type { Feature, FeatureCollection, MultiPolygon, Polygon, Point } from 'geojson'

export const CONTRACT_VERSION = '2.1.0'

export type YearMonth = string
export type IsoDate = string

/** Bbox WGS84 : [ouest, sud, est, nord]. */
export type BBox = [number, number, number, number]

export type SensorRegime =
  | 'partial_year' // 2000-11..2000-12 : MODIS Terra seul, année incomplète
  | 'modis_terra_only' // 2001-01..2002-06 : avant le démarrage d'Aqua
  | 'modis_terra_aqua' // 2002-07..2012-01 : reconstitution MODIS → échelle VIIRS
  | 'viirs_snpp_observed' // 2012-02..2026-10 : VIIRS S-NPP observé
  | 'viirs_noaa20_bridge' // 2026-11+ : pont VIIRS NOAA-20
  | 'missing' // aucune source exploitable

export type CoverageStatus = 'complete_sp' | 'partial_sp' | 'mixed_sp_nrt' | 'nrt_only' | 'no_data'

export type SourceCode = 'modis' | 'viirs-snpp' | 'viirs-noaa20' | 'viirs-noaa21'

export type RegionType = 'country' | 'province' | 'study_area' | 'custom'

// ---------------------------------------------------------------- Requêtes

/** Zone d'étude : priorité backend polygon > bbox > region. */
export interface AreaQuery {
  /** `GA` ou `GA-1`..`GA-9`. */
  region?: string
  bbox?: BBox
  /** Polygon / MultiPolygon / Feature GeoJSON (envoyé URL-encodé). */
  polygon?: Polygon | MultiPolygon | Feature<Polygon | MultiPolygon>
  start?: YearMonth
  end?: YearMonth
  /** true (défaut backend) = type 0 hors cellules statiques 0.05° ; false = toutes anomalies thermiques. */
  filter_static: boolean
}

// ---------------------------------------------------------------- /health/

export interface HealthResponse {
  status: string
  database: string
  postgis_version: string
  counts: { regions: number; hotspots: number; grid_cell_months: number; harmonized_months: number }
}

// ---------------------------------------------------------------- /regions/

export interface Region {
  code: string
  name: string
  region_type: RegionType
  bbox: BBox
  is_custom_supported: boolean
  /** null si `include_geom=false`. */
  geometry: MultiPolygon | null
}

export interface RegionsResponse {
  regions: Region[]
}

// ---------------------------------------------------------------- /coverage/

export interface SensorCoverage {
  source: SourceCode
  label: string
  min_date: IsoDate | null
  max_date: IsoDate | null
  /** Fin opérationnelle (ex. S-NPP : 2026-11-02), sinon null. */
  operational_end_date: IsoDate | null
  processing_levels: ('SP' | 'NRT')[]
  notes: string
}

export interface CoverageResponse {
  region: string
  sensors: SensorCoverage[]
}

// ---------------------------------------------------------------- /calendar/

export interface MethodInfo {
  name: string
  version: string
  reference_scale: string
  bridge_after_2026_11_02: string
}

export interface CalendarPoint {
  month: YearMonth
  /** Terra + Aqua. */
  modis_count: number | null
  modis_terra_count: number | null
  modis_aqua_count: number | null
  viirs_snpp_count: number | null
  viirs_noaa20_count: number | null
  harmonized_value: number | null
  /** Intervalle conforme 80 % ; = valeur si observée directement ; null sur zone custom. */
  ci_low: number | null
  ci_high: number | null
  /** Médiane historique B(r,m) du même mois calendaire (2001–2025). */
  baseline_median: number | null
  /** [p25, p75] ; null sur zone custom. */
  baseline_iqr: [number, number] | null
  /** null si médiane = 0 (ou absente) : utiliser `anomaly_absolute`. */
  anomaly_percent: number | null
  anomaly_absolute: number | null
  sensor_regime: SensorRegime
  coverage_status: CoverageStatus
  uncertainty_note: string
}

export interface CalendarResponse {
  /** `id` vaut `CUSTOM_BBOX` / `CUSTOM_POLYGON` pour une zone libre. */
  region: { id: string; name: string; filter_static: boolean }
  /** null si la série est vide (région inconnue, filtre hors période). */
  period: { start: YearMonth | null; end: YearMonth | null }
  method: MethodInfo | null
  series: CalendarPoint[]
}

// ---------------------------------------------------------------- /anomalies/

export interface MonthlyBaseline {
  month_num: number
  median: number
  iqr_p25: number
  iqr_p75: number
  reference_years_count: number
  reference_period: string
}

export interface RankedAnomaly {
  month: YearMonth
  harmonized_value: number
  baseline_median: number
  anomaly_percent: number
  anomaly_absolute: number
  sensor_regime: SensorRegime
}

export interface AnomaliesResponse {
  region: string
  filter_static: boolean
  monthly_baselines: MonthlyBaseline[]
  top_positive: RankedAnomaly[]
  top_negative: RankedAnomaly[]
}

// ---------------------------------------------------------------- /hotspots/

export interface GridCellMonthProps {
  layer: 'grid_cell_month'
  cell_id: string
  month: YearMonth
  modis_count: number
  viirs_snpp_count: number
  viirs_noaa20_count: number
}

export interface HotspotPointProps {
  layer: 'hotspot_point'
  [key: string]: unknown
}

export interface StaticFlareMaskProps {
  layer: 'static_flare_mask'
  [key: string]: unknown
}

/** Filtrer sur `properties.layer` côté MapLibre (réponse mixte si include_static_cells=true). */
export type HotspotsResponse = FeatureCollection<
  Polygon | Point,
  GridCellMonthProps | HotspotPointProps | StaticFlareMaskProps
> & { mode: 'grid' | 'points' }

// ---------------------------------------------------------------- /methodology/

export interface OutOfSampleMetrics {
  mae: number
  rmse: number
  bias: number
  r2: number
}

export interface CalibrationParams {
  global_ratio_alpha: number
  ols_slope: number
  ols_intercept: number
  power_law_p: number
  power_law_q: number
  terra_only_p: number
  terra_only_q: number
  conformal_q80_log: number
  conformal_q80_terra_log: number
  noaa20_to_snpp_ratio: number
}

export interface MethodologyResponse {
  region: string
  filter_static: boolean
  active_run: {
    method_name: string
    method_version: string
    reference_scale: string
    train_window: [IsoDate, IsoDate]
    test_window: [IsoDate, IsoDate]
    params: CalibrationParams
    metrics: {
      train_months: number
      test_months: number
      /** null si la sous-région hérite du modèle national. */
      models_out_of_sample: Record<string, OutOfSampleMetrics> | null
    }
  } | null
  static_mask_summary: { grid_deg: number; masked_cells_count: number }
  limitations: string[]
}
