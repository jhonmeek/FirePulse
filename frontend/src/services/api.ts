import type {
  AnomaliesResponse,
  AreaQuery,
  CalendarResponse,
  CoverageResponse,
  MethodologyResponse,
  RegionsResponse,
} from '@/types/api'

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
