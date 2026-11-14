import type { Feature, FeatureCollection, MultiPolygon, Polygon } from 'geojson'

export interface CalendarPoint {
  month: string
  modis_count: number | null
  modis_terra_count: number | null
  modis_aqua_count: number | null
  viirs_snpp_count: number | null
  viirs_noaa20_count: number | null
  harmonized_value: number | null
  ci_low: number | null
  ci_high: number | null
  baseline_median: number | null
  baseline_iqr: [number, number] | null
  anomaly_percent: number | null
  anomaly_absolute: number | null
  sensor_regime: string
  coverage_status: string
  uncertainty_note: string
}

export interface CalendarResponse {
  region: { id: string; name: string; filter_static: boolean }
  period: { start: string | null; end: string | null }
  method: {
    name: string
    version: string
    reference_scale: string
    bridge_after_2026_11_02: string
  } | null
  series: CalendarPoint[]
}

export interface OutOfSampleMetrics {
  mae: number
  rmse: number
  bias: number
  r2: number
}

export interface MethodologyResponse {
  region: string
  filter_static: boolean
  active_run: {
    method_name: string
    method_version: string
    reference_scale: string
    train_window: [string, string]
    test_window: [string, string]
    params: Record<string, number>
    metrics: {
      train_months?: number
      test_months?: number
      models_out_of_sample?: Record<string, OutOfSampleMetrics> | null
      note?: string
    }
  } | null
  static_mask_summary: { grid_deg: number; masked_cells_count: number }
  limitations: string[]
}

export interface Region {
  code: string
  name: string
  region_type: string
  bbox: [number, number, number, number]
  is_custom_supported: boolean
  geometry: MultiPolygon | null
}

export interface RegionsResponse {
  regions: Region[]
}

export type GridYearlyRow = [
  string,
  number,
  number,
  number,
  number,
  number,
  number,
  number,
  number,
]

export type StaticCellRow = [
  string,
  number,
  number,
  string,
]

export interface HotspotsMock {
  _format: string
  grid_yearly: GridYearlyRow[]
  static_cells: StaticCellRow[]
}

export interface GridCellFeatureProps {
  layer: 'grid'
  cell_id: string
  count: number
  modis: number
  snpp: number
  noaa20: number
  months: number
  frp: number
}

export interface StaticCellFeatureProps {
  layer: 'static'
  cell_id: string
  type23: number
  activeMonths: number
  reason: string
}

export type GridFeature = Feature<Polygon, GridCellFeatureProps>
export type StaticFeature = Feature<Polygon, StaticCellFeatureProps>

export interface GridBundle {
  grid: FeatureCollection<Polygon, GridCellFeatureProps>
  statics: FeatureCollection<Polygon, StaticCellFeatureProps>
  cells: number
  total: number
  max: number
}

export interface GlobePoint {
  lat: number
  lon: number
  weight: number
}

export interface RegionFeatureProps {
  code: string
  name: string
  region_type: string
}

export type RegionFeature = Feature<MultiPolygon, RegionFeatureProps>

export type DataSourceMode = 'live' | 'snapshot'

export interface HealthResponse {
  status: string
  database: string
  postgis_version: string
  counts: {
    regions: number
    hotspots: number
    grid_cell_months: number
    harmonized_months: number
  }
}

export interface CoverageSensor {
  source: string
  label: string
  min_date: string | null
  max_date: string | null
  operational_end_date: string | null
  processing_levels: string[]
  product_versions: string[]
  notes: string
}

export interface CoverageResponse {
  region: string
  sensors: CoverageSensor[]
}

export interface HotspotApiGridCellProps {
  layer: 'grid_cell_summary'
  cell_id: string
  months_count: number
  modis_count: number
  viirs_snpp_count: number
  viirs_noaa20_count: number
  frp_sum_modis: number
  frp_sum_snpp: number
  frp_sum_noaa20: number
}

export interface HotspotApiStaticMaskProps {
  layer: 'static_flare_mask'
  cell_id: string
  type23_count: number
  active_months_snpp: number
  reason: string
}

export interface HotspotsApiResponse {
  type: 'FeatureCollection'
  mode: string
  agg: string
  features: Array<Feature<Polygon, HotspotApiGridCellProps | HotspotApiStaticMaskProps>>
}
