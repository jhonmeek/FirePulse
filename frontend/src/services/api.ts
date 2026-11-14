import type {
  AnomaliesResponse,
  AreaQuery,
  CalendarResponse,
  CalendarPoint,
  CoverageResponse,
  GridCellSummaryProps,
  HotspotsResponse,
  MethodologyResponse,
  RegionsResponse,
  StaticFlareMaskProps,
} from '@/types/api'
import type { Feature, Polygon } from 'geojson'

/** Mocks par défaut en dev (désactiver avec VITE_USE_MOCKS=false), jamais en production. */
export const USE_MOCKS = import.meta.env.DEV && import.meta.env.VITE_USE_MOCKS !== 'false'
const API_BASE = import.meta.env.VITE_API_BASE ?? '/api/v1'

/** Seule la région nationale est disponible en mock (provinces et zones libres : API réelle). */
const MOCK_REGION = 'GA'

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly url: string,
    public readonly detail?: string,
  ) {
    super(`API ${status} sur ${url}${detail ? ` : ${detail}` : ''}`)
  }
}

export function toSearchParams(query: AreaQuery): URLSearchParams {
  const params = new URLSearchParams()
  // Même priorité que le backend : polygon > bbox > region.
  if (query.polygon) params.set('polygon', JSON.stringify(query.polygon))
  else if (query.bbox) params.set('bbox', query.bbox.join(','))
  else if (query.region) params.set('region', query.region)
  if (query.start) params.set('start', query.start)
  if (query.end) params.set('end', query.end)
  params.set('filter_static', String(query.filter_static))
  return params
}

/** Les routes Django finissent par `/` : sans lui, GET part en redirection 301. */
async function getJson<T>(path: string, params?: URLSearchParams): Promise<T> {
  const url = `${API_BASE}/${path}/${params && params.toString() ? `?${params}` : ''}`
  const res = await fetch(url, { headers: { Accept: 'application/json' } })
  if (!res.ok) {
    const body = await res.json().catch(() => null)
    throw new ApiError(res.status, url, body?.detail ?? body?.error)
  }
  return (await res.json()) as T
}

/** Les JSON importés ont des tableaux typés `number[]` (pas des tuples) : la conformité
 * au contrat est garantie par `src/__tests__/mocks.spec.ts`, pas par l'inférence TS. */
const fromMock = <T>(mod: { default: unknown }): T => mod.default as T

const isMockArea = (q: AreaQuery) =>
  !q.polygon && !q.bbox && (q.region ?? MOCK_REGION) === MOCK_REGION

function warnMockGap(what: string) {
  console.warn(`[mocks] ${what} non disponible en mock : lancer le backend et VITE_USE_MOCKS=false`)
}

// Les mocks sont chargés à la demande et éliminés du build de production.
const mocks = {
  calendar: (s: boolean) =>
    s ? import('@/mocks/calendar_GA_static.json') : import('@/mocks/calendar_GA_all.json'),
  anomalies: (s: boolean) =>
    s ? import('@/mocks/anomalies_GA_static.json') : import('@/mocks/anomalies_GA_all.json'),
  methodology: (s: boolean) =>
    s ? import('@/mocks/methodology_GA_static.json') : import('@/mocks/methodology_GA_all.json'),
  hotspots: (s: boolean) =>
    s ? import('@/mocks/hotspots_GA_static.json') : import('@/mocks/hotspots_GA_all.json'),
  regions: () => import('@/mocks/regions.json'),
  coverage: () => import('@/mocks/coverage.json'),
}

export async function fetchCalendar(query: AreaQuery): Promise<CalendarResponse> {
  if (!USE_MOCKS) return getJson('calendar', toSearchParams(query))

  if (!isMockArea(query)) {
    warnMockGap('zone autre que GA')
    // Même forme que le backend pour une région sans données.
    return {
      region: {
        id: query.region ?? 'CUSTOM',
        name: query.region ?? 'Custom',
        filter_static: query.filter_static,
      },
      period: { start: null, end: null },
      method: null,
      series: [],
    }
  }
  const full = fromMock<CalendarResponse>(await mocks.calendar(query.filter_static))
  const series = full.series.filter(
    (p) => (!query.start || p.month >= query.start) && (!query.end || p.month <= query.end),
  )
  return {
    ...full,
    period: { start: series[0]?.month ?? null, end: series[series.length - 1]?.month ?? null },
    series,
  }
}

export async function fetchAnomalies(
  region: string,
  filterStatic: boolean,
  topN = 10,
): Promise<AnomaliesResponse> {
  if (!USE_MOCKS) {
    const params = new URLSearchParams({
      region,
      filter_static: String(filterStatic),
      top_n: String(topN),
    })
    return getJson('anomalies', params)
  }
  if (region !== MOCK_REGION) {
    warnMockGap(`anomalies ${region}`)
    return {
      region,
      filter_static: filterStatic,
      monthly_baselines: [],
      top_positive: [],
      top_negative: [],
    }
  }
  const data = fromMock<AnomaliesResponse>(await mocks.anomalies(filterStatic))
  return {
    ...data,
    top_positive: data.top_positive.slice(0, topN),
    top_negative: data.top_negative.slice(0, topN),
  }
}

export async function fetchMethodology(
  region: string,
  filterStatic: boolean,
): Promise<MethodologyResponse> {
  if (!USE_MOCKS)
    return getJson(
      'methodology',
      new URLSearchParams({ region, filter_static: String(filterStatic) }),
    )
  if (region !== MOCK_REGION) warnMockGap(`méthodologie ${region}`)
  return fromMock<MethodologyResponse>(await mocks.methodology(filterStatic))
}

export async function fetchRegions(includeGeom = true): Promise<RegionsResponse> {
  if (!USE_MOCKS)
    return getJson('regions', new URLSearchParams({ include_geom: String(includeGeom) }))
  const data = fromMock<RegionsResponse>(await mocks.regions())
  return includeGeom ? data : { regions: data.regions.map((r) => ({ ...r, geometry: null })) }
}

export async function fetchCoverage(region = MOCK_REGION): Promise<CoverageResponse> {
  if (!USE_MOCKS) return getJson('coverage', new URLSearchParams({ region }))
  return fromMock<CoverageResponse>(await mocks.coverage())
}

// ---------------------------------------------------------------- /hotspots/ (carte)

/** Polygone d'une cellule à partir de son `cell_id` (`lat0_lon0`, coin sud-ouest). */
export function cellPolygon(cellId: string, size: number): Polygon {
  const [lat, lon] = cellId.split('_').map(Number) as [number, number]
  return {
    type: 'Polygon',
    coordinates: [
      [
        [lon, lat],
        [lon + size, lat],
        [lon + size, lat + size],
        [lon, lat + size],
        [lon, lat],
      ],
    ],
  }
}

type GridYearlyRow = [string, number, number, number, number, number, number, number, number]
interface HotspotsMock {
  grid_yearly: GridYearlyRow[]
  static_cells: [string, number, number, StaticFlareMaskProps['reason']][]
}

/**
 * Grille 0.25° agrégée sur la plage (`agg=cell`) + sites statiques 0.05°.
 * Mock : resomme les agrégats annuels sur les années de start..end et filtre la bbox
 * par intersection, comme `geom__intersects` côté backend.
 */
export async function fetchHotspots(query: AreaQuery): Promise<HotspotsResponse> {
  if (!USE_MOCKS) {
    const params = toSearchParams(query)
    params.set('mode', 'grid')
    params.set('agg', 'cell')
    params.set('include_static_cells', 'true')
    params.set('limit', '5000')
    return getJson('hotspots', params)
  }
  if (query.polygon || (!query.bbox && (query.region ?? MOCK_REGION) !== MOCK_REGION)) {
    warnMockGap('grille hors GA / bbox')
    return { type: 'FeatureCollection', mode: 'grid', agg: 'cell', features: [] }
  }
  const data = fromMock<HotspotsMock>(await mocks.hotspots(query.filter_static))
  const y0 = query.start ? +query.start.slice(0, 4) : 0
  const y1 = query.end ? +query.end.slice(0, 4) : 9999
  const intersects = (cellId: string, size: number) => {
    if (!query.bbox) return true
    const [lat, lon] = cellId.split('_').map(Number) as [number, number]
    const [w, s, e, n] = query.bbox
    return lon <= e && lon + size >= w && lat <= n && lat + size >= s
  }
  const sums = new Map<string, number[]>()
  for (const [cell, year, ...vals] of data.grid_yearly) {
    if (year < y0 || year > y1 || !intersects(cell, 0.25)) continue
    const acc = sums.get(cell) ?? [0, 0, 0, 0, 0, 0, 0]
    vals.forEach((v, i) => (acc[i]! += v))
    sums.set(cell, acc)
  }
  const grid: Feature<Polygon, GridCellSummaryProps>[] = [...sums].map(([cell_id, v]) => ({
    type: 'Feature',
    geometry: cellPolygon(cell_id, 0.25),
    properties: {
      layer: 'grid_cell_summary',
      cell_id,
      months_count: v[0]!,
      modis_count: v[1]!,
      viirs_snpp_count: v[2]!,
      viirs_noaa20_count: v[3]!,
      frp_sum_modis: Math.round(v[4]! * 100) / 100,
      frp_sum_snpp: Math.round(v[5]! * 100) / 100,
      frp_sum_noaa20: Math.round(v[6]! * 100) / 100,
    },
  }))
  // Comme le backend : seuls les sites statiques qui intersectent la zone.
  const statics: Feature<Polygon, StaticFlareMaskProps>[] = data.static_cells
    .filter(([cell_id]) => intersects(cell_id, 0.05))
    .map(([cell_id, type23_count, active_months_snpp, reason]) => ({
      type: 'Feature',
      geometry: cellPolygon(cell_id, 0.05),
      properties: { layer: 'static_flare_mask', cell_id, type23_count, active_months_snpp, reason },
    }))
  return { type: 'FeatureCollection', mode: 'grid', agg: 'cell', features: [...grid, ...statics] }
}

// ---------------------------------------------------------------- /export/

/** URL de téléchargement CSV des séries (`dataset=series`) pour la zone et la période. */
export function exportSeriesUrl(query: AreaQuery): string {
  const params = toSearchParams(query)
  params.set('dataset', 'series')
  return `${API_BASE}/export/?${params}`
}

export const SERIES_CSV_COLUMNS = [
  'region',
  'month',
  'filter_static',
  'modis_count',
  'viirs_snpp_count',
  'viirs_noaa20_count',
  'harmonized_value',
  'ci_low',
  'ci_high',
  'baseline_median',
  'anomaly_percent',
  'anomaly_absolute',
  'sensor_regime',
  'coverage_status',
  'method_version',
] as const

/**
 * CSV des séries construit côté client, mêmes colonnes que `/export/?dataset=series`
 * (booléens Python `True`/`False`, null → cellule vide). Sert au mode mocks.
 */
export function seriesToCsv(
  series: CalendarPoint[],
  region: string,
  filterStatic: boolean,
  methodVersion: string,
): string {
  const cell = (v: unknown) => (v === null || v === undefined ? '' : String(v))
  // Colonnes FloatField côté Django : Python écrit `414.0`, JavaScript écrirait `414`.
  const float = (v: number | null) => (v === null ? '' : Number.isInteger(v) ? `${v}.0` : String(v))
  const lines = series.map((p) =>
    [
      cell(region),
      cell(p.month),
      filterStatic ? 'True' : 'False',
      cell(p.modis_count),
      cell(p.viirs_snpp_count),
      cell(p.viirs_noaa20_count),
      float(p.harmonized_value),
      float(p.ci_low),
      float(p.ci_high),
      float(p.baseline_median),
      float(p.anomaly_percent),
      float(p.anomaly_absolute),
      cell(p.sensor_regime),
      cell(p.coverage_status),
      cell(methodVersion),
    ].join(','),
  )
  return [SERIES_CSV_COLUMNS.join(','), ...lines].join('\n') + '\n'
}
