import type {
  CalendarResponse,
  CoverageResponse,
  HealthResponse,
  HotspotsApiResponse,
  MethodologyResponse,
  RegionsResponse,
} from './types'

export const API_BASE = import.meta.env.VITE_API_BASE || '/api/v1'
export const USE_MOCKS = String(import.meta.env.VITE_USE_MOCKS ?? 'false').toLowerCase() === 'true'

export interface RecentUnknownFeature {
  type: 'Feature'
  geometry: { type: 'Point'; coordinates: [number, number] }
  properties: {
    id: number
    source: string
    satellite: string
    acquired_at: string
    frp: number | null
    hotspot_type: null
    processing_level: 'NRT'
    product_version: string
  }
}

export interface RecentUnknownResponse {
  type: 'FeatureCollection'
  features: RecentUnknownFeature[]
  region: string
  since: string
  days: number
  provenance: string
  caution: string
}

async function getJson<T>(path: string, timeoutMs = 25_000): Promise<T> {
  const controller = new AbortController()
  const timer = globalThis.setTimeout(() => controller.abort(), timeoutMs)
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      headers: { Accept: 'application/json' },
      signal: controller.signal,
    })
    if (!res.ok) {
      throw new Error(`API ${path} -> HTTP ${res.status}`)
    }
    return (await res.json()) as T
  } finally {
    globalThis.clearTimeout(timer)
  }
}

export function fetchHealth(): Promise<HealthResponse> {
  return getJson<HealthResponse>('/health/')
}

export function fetchCalendar(opts: { region: string; filterStatic: boolean }): Promise<CalendarResponse> {
  const q = new URLSearchParams({
    region: opts.region,
    filter_static: String(opts.filterStatic),
  })
  return getJson<CalendarResponse>(`/calendar/?${q.toString()}`)
}

export function fetchMethodology(opts: {
  region: string
  filterStatic: boolean
}): Promise<MethodologyResponse> {
  const q = new URLSearchParams({
    region: opts.region,
    filter_static: String(opts.filterStatic),
  })
  return getJson<MethodologyResponse>(`/methodology/?${q.toString()}`)
}

export function fetchRegions(): Promise<RegionsResponse> {
  return getJson<RegionsResponse>('/regions/')
}

export function fetchCoverage(region = 'GA'): Promise<CoverageResponse> {
  const q = new URLSearchParams({ region })
  return getJson<CoverageResponse>(`/coverage/?${q.toString()}`)
}

export function fetchRecentUnknownDetections(days = 2, limit = 200): Promise<RecentUnknownResponse> {
  const q = new URLSearchParams({ region: 'GA', days: String(days), limit: String(limit) })
  return getJson<RecentUnknownResponse>(`/recent-unknown-detections/?${q.toString()}`, 15_000)
}

export function fetchHotspotsGrid(opts: {
  region: string
  filterStatic: boolean
  includeStaticCells: boolean
  start: string
  end: string
  limit?: number
}): Promise<HotspotsApiResponse> {
  const q = new URLSearchParams({
    mode: 'grid',
    agg: 'cell',
    region: opts.region,
    filter_static: String(opts.filterStatic),
    include_static_cells: String(opts.includeStaticCells),
    start: opts.start,
    end: opts.end,
    limit: String(opts.limit ?? 5000),
  })
  return getJson<HotspotsApiResponse>(`/hotspots/?${q.toString()}`, 35_000)
}

export function exportSeriesEndpoint(region = 'GA', filterStatic = true): string {
  const q = new URLSearchParams({
    dataset: 'series',
    region,
    filter_static: String(filterStatic),
  })
  return `${API_BASE}/export/?${q.toString()}`
}
