import { computed, ref } from 'vue'
import healthJson from '@/data/health.json'
import calendarStaticJson from '@/data/calendar-static.json'
import calendarAllJson from '@/data/calendar-all.json'
import methodologyJson from '@/data/methodology.json'
import methodologyRawJson from '@/data/methodology-raw.json'
import regionsJson from '@/data/regions.json'
import coverageJson from '@/data/coverage.json'
import hotspotsStaticJson from '@/data/hotspots-static.json'
import hotspotsAllJson from '@/data/hotspots-all.json'
import type { Polygon } from 'geojson'
import {
  USE_MOCKS,
  fetchCalendar,
  fetchCoverage,
  fetchHealth,
  fetchHotspotsGrid,
  fetchMethodology,
  fetchRegions,
} from './api'
import { locale } from './i18n'
import { provenance } from './provenance'
import type {
  CalendarPoint,
  CalendarResponse,
  CoverageResponse,
  DataSourceMode,
  GlobePoint,
  GridBundle,
  GridFeature,
  GridYearlyRow,
  HealthResponse,
  HotspotApiGridCellProps,
  HotspotApiStaticMaskProps,
  HotspotsMock,
  MethodologyResponse,
  Region,
  RegionFeature,
  RegionFeatureProps,
  RegionsResponse,
  StaticFeature,
} from './types'

export const healthState = ref<HealthResponse>(healthJson as unknown as HealthResponse)
export const calendarStaticState = ref<CalendarResponse>(
  calendarStaticJson as unknown as CalendarResponse,
)
export const calendarAllState = ref<CalendarResponse>(
  calendarAllJson as unknown as CalendarResponse,
)
export const methodologyState = ref<MethodologyResponse>(
  methodologyJson as unknown as MethodologyResponse,
)
export const methodologyRawState = ref<MethodologyResponse>(
  methodologyRawJson as unknown as MethodologyResponse,
)
export const regionsState = ref<Region[]>(
  (regionsJson as unknown as RegionsResponse).regions ?? [],
)
export const coverageState = ref<CoverageResponse>(coverageJson as unknown as CoverageResponse)

export const hotspotsStatic = hotspotsStaticJson as unknown as HotspotsMock
export const hotspotsAll = hotspotsAllJson as unknown as HotspotsMock

export const dataSourceMode = ref<DataSourceMode>('snapshot')
export const apiError = ref<string | null>(null)
export const isHydrating = ref(false)
export const lastSyncedAt = ref<string | null>(null)

let hydrationPromise: Promise<void> | null = null

export async function initLiveData(force = false): Promise<void> {
  if (USE_MOCKS) {
    dataSourceMode.value = 'snapshot'
    return
  }
  if (hydrationPromise && !force) return hydrationPromise

  isHydrating.value = true
  hydrationPromise = (async () => {
    try {
      const [
        healthRes,
        calStaticRes,
        calAllRes,
        methRes,
        methRawRes,
        regionsRes,
        coverageRes,
      ] = await Promise.allSettled([
        fetchHealth(),
        fetchCalendar({ region: 'GA', filterStatic: true }),
        fetchCalendar({ region: 'GA', filterStatic: false }),
        fetchMethodology({ region: 'GA', filterStatic: true }),
        fetchMethodology({ region: 'GA', filterStatic: false }),
        fetchRegions(),
        fetchCoverage('GA'),
      ])

      let liveSuccessCount = 0
      if (healthRes.status === 'fulfilled') {
        healthState.value = healthRes.value
        liveSuccessCount += 1
      }
      if (calStaticRes.status === 'fulfilled') {
        calendarStaticState.value = calStaticRes.value
        liveSuccessCount += 1
      }
      if (calAllRes.status === 'fulfilled') {
        calendarAllState.value = calAllRes.value
        liveSuccessCount += 1
      }
      if (methRes.status === 'fulfilled') {
        methodologyState.value = methRes.value
        liveSuccessCount += 1
      }
      if (methRawRes.status === 'fulfilled') {
        methodologyRawState.value = methRawRes.value
      }
      if (regionsRes.status === 'fulfilled' && Array.isArray(regionsRes.value.regions)) {
        regionsState.value = regionsRes.value.regions
      }
      if (coverageRes.status === 'fulfilled') {
        coverageState.value = coverageRes.value
      }

      if (liveSuccessCount >= 3) {
        dataSourceMode.value = 'live'
        apiError.value = null
        lastSyncedAt.value = new Date().toISOString()
      } else {
        dataSourceMode.value = 'snapshot'
        apiError.value = 'API Django indisponible : bascule sur les instantanés DB.'
      }
    } catch (err) {
      dataSourceMode.value = 'snapshot'
      apiError.value = err instanceof Error ? err.message : 'API hors ligne'
    } finally {
      isHydrating.value = false
    }
  })()

  return hydrationPromise
}

export const MONTH_NAMES = [
  'Janvier',
  'Février',
  'Mars',
  'Avril',
  'Mai',
  'Juin',
  'Juillet',
  'Août',
  'Septembre',
  'Octobre',
  'Novembre',
  'Décembre',
]

export const MONTH_NAMES_EN = [
  'January',
  'February',
  'March',
  'April',
  'May',
  'June',
  'July',
  'August',
  'September',
  'October',
  'November',
  'December',
]

export const MONTH_SHORT = [
  'Jan',
  'Fév',
  'Mar',
  'Avr',
  'Mai',
  'Juin',
  'Juil',
  'Août',
  'Sep',
  'Oct',
  'Nov',
  'Déc',
]

export const MONTH_SHORT_EN = [
  'Jan',
  'Feb',
  'Mar',
  'Apr',
  'May',
  'Jun',
  'Jul',
  'Aug',
  'Sep',
  'Oct',
  'Nov',
  'Dec',
]

export const YEARS = Array.from({ length: 26 }, (_, i) => 2000 + i)

/**
 * Somme MODIS + VIIRS S-NPP.
 * Attention : après 2012, les deux capteurs observent les mêmes feux. Cette somme
 * n'est donc pas un nombre physique de feux ; elle sert uniquement de vue « tout brut ».
 */
export function rawCount(p: CalendarPoint): number {
  return (p.modis_count ?? 0) + (p.viirs_snpp_count ?? 0)
}

/** Toutes les détections disponibles en base sur le mois (MODIS + S-NPP + NOAA-20). */
export function allRawCount(p: CalendarPoint): number {
  return (p.modis_count ?? 0) + (p.viirs_snpp_count ?? 0) + (p.viirs_noaa20_count ?? 0)
}

export function monthNumber(month: string): number {
  return Number(month.slice(5, 7))
}

export function yearOf(month: string): number {
  return Number(month.slice(0, 4))
}

export function monthLabel(month: string): string {
  const m = monthNumber(month)
  const names = locale.value === 'en' ? MONTH_NAMES_EN : MONTH_NAMES
  return `${names[m - 1]} ${yearOf(month)}`
}

export function monthShortLabel(month: string): string {
  const names = locale.value === 'en' ? MONTH_SHORT_EN : MONTH_SHORT
  return `${names[monthNumber(month) - 1]} ${String(yearOf(month)).slice(2)}`
}

export function formatCount(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  const loc = locale.value === 'en' ? 'en-US' : 'fr-FR'
  return new Intl.NumberFormat(loc).format(Math.round(value))
}

export function formatDecimal(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  const loc = locale.value === 'en' ? 'en-US' : 'fr-FR'
  return new Intl.NumberFormat(loc, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(value)
}

export function formatPercent(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  const sign = value > 0 ? '+' : ''
  const isEn = locale.value === 'en'
  const formatted = new Intl.NumberFormat(isEn ? 'en-US' : 'fr-FR', {
    maximumFractionDigits: digits,
    minimumFractionDigits: digits,
  }).format(value)
  return isEn ? `${sign}${formatted}%` : `${sign}${formatted} %`
}

export function median(values: number[]): number {
  if (!values.length) return 0
  const sorted = [...values].sort((a, b) => a - b)
  const mid = Math.floor(sorted.length / 2)
  return sorted.length % 2 ? sorted[mid]! : (sorted[mid - 1]! + sorted[mid]!) / 2
}

export const staticSeries = computed(() => calendarStaticState.value.series)
export const allSeries = computed(() => calendarAllState.value.series)
export const methodology = computed(() => methodologyState.value)
export const methodologyRaw = computed(() => methodologyRawState.value)
export const metrics = computed(
  () => methodologyState.value.active_run?.metrics.models_out_of_sample ?? {},
)
export const metricsRaw = computed(
  () => methodologyRawState.value.active_run?.metrics.models_out_of_sample ?? {},
)
export const params = computed(() => methodologyState.value.active_run?.params)
export const maskedCellsCount = computed(
  () => methodologyState.value.static_mask_summary?.masked_cells_count ?? provenance.maskedCells,
)
export const regionsCount = computed(
  () => healthState.value.counts?.regions ?? (regionsState.value.length || provenance.regions),
)
export const totalDetectionsDb = computed(
  () => healthState.value.counts?.hotspots ?? provenance.archive.totalDetections,
)
export const gridCellMonthsDb = computed(
  () => healthState.value.counts?.grid_cell_months ?? provenance.gridCellMonths,
)
export const harmonizedMonthsDb = computed(
  () => healthState.value.counts?.harmonized_months ?? provenance.harmonizedMonthsRows,
)

/**
 * Médianes saisonnières officielles (fenêtre 2001–2025, table MonthlyBaseline).
 * Utilise directement baseline_median fourni par l'API pour garantir 100 % de cohérence
 * avec les anomalies du panneau de détail.
 */
export const monthlyMedians = computed(() =>
  Array.from({ length: 12 }, (_, i) => {
    const calMonth = i + 1
    const sample = staticSeries.value.find(
      (p) =>
        yearOf(p.month) >= 2001 &&
        monthNumber(p.month) === calMonth &&
        p.baseline_median !== null,
    )
    if (sample?.baseline_median !== null && sample?.baseline_median !== undefined) {
      return sample.baseline_median
    }
    const values = staticSeries.value
      .filter((p) => yearOf(p.month) >= 2001 && monthNumber(p.month) === calMonth)
      .map((p) => p.harmonized_value)
      .filter((v): v is number => v !== null)
    return median(values)
  }),
)

/** Saison principale : les mois dont la médiane dépasse 500 détections équiv. S-NPP. */
export const mainSeason = computed(() =>
  monthlyMedians.value
    .map((value, index) => ({ month: index + 1, value }))
    .filter((d) => d.value >= 500)
    .map((d) => d.month),
)

/** Second épisode : médiane entre 250 et 500 détections équiv. S-NPP. */
export const secondarySeason = computed(() =>
  monthlyMedians.value
    .map((value, index) => ({ month: index + 1, value }))
    .filter((d) => d.value >= 250 && d.value < 500)
    .map((d) => d.month),
)

function diffSensorCount(
  allVal: number | null | undefined,
  cleanVal: number | null | undefined,
  field: string,
  issues: string[],
): number | null {
  if (allVal == null && cleanVal == null) {
    return null
  }
  if (allVal == null || cleanVal == null) {
    issues.push(`missing_sensor_input:${field}`)
    return null
  }
  const diff = allVal - cleanVal
  if (diff < 0) {
    issues.push(`negative_series_delta:${field}`)
    return null
  }
  return diff
}

/**
 * Série mensuelle des détections écartées (différence exploratoire `allPoints - cleanPoints`).
 * Aucune valeur manquante n'est remplacée par MODIS + S-NPP et aucun écart négatif n'est écrêté à 0 :
 * ces cas deviennent indisponibles (`null`) et sont signalés dans `uncertainty_note`.
 */
export function computeExcludedSeries(
  allPoints: CalendarPoint[],
  cleanPoints: CalendarPoint[],
): CalendarPoint[] {
  const cleanByMonth = new Map(cleanPoints.map((p) => [p.month, p]))
  const rawDiffs = allPoints.map((allPt) => {
    const cleanPt = cleanByMonth.get(allPt.month)
    const issues: string[] = []
    if (!cleanPt) {
      issues.push('missing_clean_month')
    }

    const modis = diffSensorCount(allPt.modis_count, cleanPt?.modis_count, 'modis_count', issues)
    const terra = diffSensorCount(
      allPt.modis_terra_count,
      cleanPt?.modis_terra_count,
      'modis_terra_count',
      issues,
    )
    const aqua = diffSensorCount(
      allPt.modis_aqua_count,
      cleanPt?.modis_aqua_count,
      'modis_aqua_count',
      issues,
    )
    const snpp = diffSensorCount(
      allPt.viirs_snpp_count,
      cleanPt?.viirs_snpp_count,
      'viirs_snpp_count',
      issues,
    )
    const noaa20 = diffSensorCount(
      allPt.viirs_noaa20_count,
      cleanPt?.viirs_noaa20_count,
      'viirs_noaa20_count',
      issues,
    )

    let harm: number | null = null
    if (allPt.harmonized_value != null && cleanPt?.harmonized_value != null) {
      const diff = Math.round((allPt.harmonized_value - cleanPt.harmonized_value) * 10) / 10
      if (diff < 0) {
        issues.push('negative_series_delta:harmonized_value')
      } else {
        harm = diff
      }
    } else {
      issues.push('missing_harmonized_input:harmonized_value')
    }

    return { allPt, modis, terra, aqua, snpp, noaa20, harm, issues }
  })

  const medians = Array.from({ length: 12 }, (_, idx) => {
    const calMonth = idx + 1
    const vals = rawDiffs
      .filter((d) => yearOf(d.allPt.month) >= 2001 && monthNumber(d.allPt.month) === calMonth)
      .map((d) => d.harm)
      .filter((v): v is number => v !== null)
    return vals.length ? median(vals) : null
  })

  return rawDiffs.map(({ allPt, modis, terra, aqua, snpp, noaa20, harm, issues }) => {
    const base = medians[monthNumber(allPt.month) - 1] ?? null
    const baseRounded = base !== null ? Math.round(base * 10) / 10 : null
    const abs = harm !== null && base !== null ? Math.round((harm - base) * 10) / 10 : null
    const pct =
      harm !== null && base !== null && base > 0 ? Math.round((abs! / base) * 1000) / 10 : null
    const uncertaintyNote = issues.length
      ? [allPt.uncertainty_note, ...issues].filter(Boolean).join('; ')
      : allPt.uncertainty_note

    return {
      ...allPt,
      modis_count: modis,
      modis_terra_count: terra,
      modis_aqua_count: aqua,
      viirs_snpp_count: snpp,
      viirs_noaa20_count: noaa20,
      harmonized_value: harm,
      ci_low: null,
      ci_high: null,
      baseline_median: baseRounded,
      anomaly_absolute: abs,
      anomaly_percent: pct,
      uncertainty_note: uncertaintyNote,
    }
  })
}

/** Série mensuelle des détections écartées par le filtre complet (différence entre tout confondu et type 0 hors sources persistantes). */
export const flareSeries = computed<CalendarPoint[]>(() =>
  computeExcludedSeries(allSeries.value, staticSeries.value),
)

/** Profil mensuel moyen (médiane 2001–2025) comparant type 0 hors sources persistantes et détections écartées. */
export const monthlySeasonComparison = computed(() =>
  Array.from({ length: 12 }, (_, index) => {
    const calMonth = index + 1
    const flareVals = flareSeries.value
      .filter((p) => yearOf(p.month) >= 2001 && monthNumber(p.month) === calMonth)
      .map((p) => p.harmonized_value)
      .filter((v): v is number => v !== null)
    return {
      monthNum: calMonth,
      veg: monthlyMedians.value[index] ?? 0,
      flare: median(flareVals),
    }
  }),
)

export function isPartialCoverage(point: CalendarPoint): boolean {
  return point.coverage_status !== 'complete_sp'
}

export function findMonth(month: string): CalendarPoint | undefined {
  return staticSeries.value.find((p) => p.month === month)
}

/** Août 2024 : le mois raconté dans l'histoire. */
export const featuredMonth = computed(
  () => findMonth('2024-08') ?? staticSeries.value[staticSeries.value.length - 1]!,
)

export interface HistoricalRankInfo {
  rank: number
  total: number
  minYear: number
  maxYear: number
}

/** Rang historique du mois dans son mois calendaire sur toute la série observée (1 = plus actif). */
export function historicalRank(point: CalendarPoint): HistoricalRankInfo {
  const m = monthNumber(point.month)
  const sameMonth = staticSeries.value
    .filter((p) => monthNumber(p.month) === m && p.harmonized_value !== null)
    .sort((a, b) => (b.harmonized_value ?? 0) - (a.harmonized_value ?? 0))
  const rank = Math.max(1, sameMonth.findIndex((p) => p.month === point.month) + 1)
  const years = sameMonth.map((p) => yearOf(p.month))
  return {
    rank,
    total: sameMonth.length,
    minYear: years.length ? Math.min(...years) : 2001,
    maxYear: years.length ? Math.max(...years) : 2025,
  }
}

/** Cellule 0,25° ou 0,05° : identifiant `lat_lon` = coin sud-ouest. */
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

export function cellCentroid(cellId: string, size: number): { lat: number; lon: number } {
  const [lat, lon] = cellId.split('_').map(Number) as [number, number]
  return { lat: lat + size / 2, lon: lon + size / 2 }
}

function parseYear(row: GridYearlyRow): number {
  return row[1]
}

function rowValues(row: GridYearlyRow) {
  return {
    months: row[2],
    modis: row[3],
    snpp: row[4],
    noaa20: row[5],
    frpModis: row[6],
    frpSnpp: row[7],
    frpNoaa20: row[8],
  }
}

export function buildGrid(
  yearStart = 2000,
  yearEnd = 2025,
  filterStatic = true,
): GridBundle {
  const source = filterStatic ? hotspotsStatic : hotspotsAll
  const sums = new Map<
    string,
    { months: number; modis: number; snpp: number; noaa20: number; frp: number }
  >()

  for (const row of source.grid_yearly) {
    const year = parseYear(row)
    if (year < yearStart || year > yearEnd) continue
    const values = rowValues(row)
    const current = sums.get(row[0]) ?? { months: 0, modis: 0, snpp: 0, noaa20: 0, frp: 0 }
    current.months += values.months
    current.modis += values.modis
    current.snpp += values.snpp
    current.noaa20 += values.noaa20
    current.frp += values.frpModis + values.frpSnpp + values.frpNoaa20
    sums.set(row[0], current)
  }

  const gridFeatures: GridFeature[] = [...sums.entries()]
    .map(([cellId, value]) => {
      const count = value.modis + value.snpp + value.noaa20
      return {
        type: 'Feature' as const,
        geometry: cellPolygon(cellId, 0.25),
        properties: {
          layer: 'grid' as const,
          cell_id: cellId,
          count,
          modis: value.modis,
          snpp: value.snpp,
          noaa20: value.noaa20,
          months: value.months,
          frp: Math.round(value.frp * 10) / 10,
        },
      }
    })
    .filter((f) => f.properties.count > 0)

  const staticFeatures: StaticFeature[] = source.static_cells.map(
    ([cellId, type23, activeMonths, reason]) => ({
      type: 'Feature' as const,
      geometry: cellPolygon(cellId, 0.05),
      properties: {
        layer: 'static' as const,
        cell_id: cellId,
        type23,
        activeMonths,
        reason,
      },
    }),
  )

  const total = gridFeatures.reduce((acc, f) => acc + f.properties.count, 0)
  const max = gridFeatures.reduce((acc, f) => Math.max(acc, f.properties.count), 1)

  return {
    grid: { type: 'FeatureCollection', features: gridFeatures },
    statics: { type: 'FeatureCollection', features: staticFeatures },
    cells: gridFeatures.length,
    total,
    max,
  }
}

export async function loadHotspotsGrid(
  yearStart = 2000,
  yearEnd = 2025,
  filterStatic = true,
): Promise<GridBundle & { source: DataSourceMode }> {
  if (USE_MOCKS) {
    return { ...buildGrid(yearStart, yearEnd, filterStatic), source: 'snapshot' }
  }
  try {
    const startMonth = yearStart <= 2000 ? '2000-11' : `${yearStart}-01`
    const endMonth = `${yearEnd}-12`
    const res = await fetchHotspotsGrid({
      region: 'GA',
      filterStatic,
      includeStaticCells: true,
      start: startMonth,
      end: endMonth,
      limit: 5000,
    })

    const gridFeatures: GridFeature[] = []
    const staticFeatures: StaticFeature[] = []

    for (const feature of res.features) {
      if (feature.properties.layer === 'grid_cell_summary') {
        const p = feature.properties as HotspotApiGridCellProps
        const count = (p.modis_count ?? 0) + (p.viirs_snpp_count ?? 0) + (p.viirs_noaa20_count ?? 0)
        if (count <= 0) continue
        const frp =
          (p.frp_sum_modis ?? 0) + (p.frp_sum_snpp ?? 0) + (p.frp_sum_noaa20 ?? 0)
        gridFeatures.push({
          type: 'Feature',
          geometry: feature.geometry ?? cellPolygon(p.cell_id, 0.25),
          properties: {
            layer: 'grid',
            cell_id: p.cell_id,
            count,
            modis: p.modis_count ?? 0,
            snpp: p.viirs_snpp_count ?? 0,
            noaa20: p.viirs_noaa20_count ?? 0,
            months: p.months_count ?? 0,
            frp: Math.round(frp * 10) / 10,
          },
        })
      } else if (feature.properties.layer === 'static_flare_mask') {
        const p = feature.properties as HotspotApiStaticMaskProps
        staticFeatures.push({
          type: 'Feature',
          geometry: feature.geometry ?? cellPolygon(p.cell_id, 0.05),
          properties: {
            layer: 'static',
            cell_id: p.cell_id,
            type23: p.type23_count ?? 0,
            activeMonths: p.active_months_snpp ?? 0,
            reason: p.reason ?? '',
          },
        })
      }
    }

    const total = gridFeatures.reduce((acc, f) => acc + f.properties.count, 0)
    const max = gridFeatures.reduce((acc, f) => Math.max(acc, f.properties.count), 1)
    return {
      grid: { type: 'FeatureCollection', features: gridFeatures },
      statics: { type: 'FeatureCollection', features: staticFeatures },
      cells: gridFeatures.length,
      total,
      max,
      source: 'live',
    }
  } catch {
    return { ...buildGrid(yearStart, yearEnd, filterStatic), source: 'snapshot' }
  }
}

/** Points du globe : centroïdes de cellules 0,25° + jitter proportionnel à l'intensité. */
export function buildGlobePoints(bundle?: GridBundle): GlobePoint[] {
  const { grid } = bundle ?? buildGrid(2000, 2025, true)
  const points: GlobePoint[] = []
  let seed = 42
  const random = () => {
    seed = (seed * 1664525 + 1013904223) % 4294967296
    return seed / 4294967296
  }
  for (const feature of grid.features) {
    const { cell_id, count } = feature.properties
    const { lat, lon } = cellCentroid(cell_id, 0.25)
    const n = Math.max(1, Math.min(14, Math.round(Math.sqrt(count) / 7)))
    points.push({ lat, lon, weight: count })
    for (let i = 1; i < n; i++) {
      points.push({
        lat: lat + (random() - 0.5) * 0.24,
        lon: lon + (random() - 0.5) * 0.24,
        weight: count / n,
      })
    }
  }
  return points
}

export const regionFeatures = computed<RegionFeature[]>(() =>
  regionsState.value
    .filter((r): r is typeof r & { geometry: NonNullable<typeof r.geometry> } => !!r.geometry)
    .map((r) => ({
      type: 'Feature' as const,
      geometry: r.geometry,
      properties: {
        code: r.code,
        name: r.name,
        region_type: r.region_type,
      } satisfies RegionFeatureProps,
    })),
)

export const countryFeature = computed(() =>
  regionFeatures.value.find((f) => f.properties.region_type === 'country'),
)

export const provinceFeatures = computed(() =>
  regionFeatures.value.filter((f) => f.properties.region_type !== 'country'),
)

function pointInRing(lon: number, lat: number, ring: number[][]): boolean {
  let inside = false
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const xi = ring[i]![0]!
    const yi = ring[i]![1]!
    const xj = ring[j]![0]!
    const yj = ring[j]![1]!
    const intersect = yi > lat !== yj > lat && lon < ((xj - xi) * (lat - yi)) / (yj - yi) + xi
    if (intersect) inside = !inside
  }
  return inside
}

function pointInPolygonRings(lon: number, lat: number, rings: number[][][]): boolean {
  if (!rings.length || !pointInRing(lon, lat, rings[0]!)) return false
  for (let i = 1; i < rings.length; i++) {
    if (pointInRing(lon, lat, rings[i]!)) return false
  }
  return true
}

/** Retourne le nom de la province gabonaise contenant (lon, lat), ou la côte/province la plus proche. */
export function findProvinceName(lon: number, lat: number): string {
  for (const feature of provinceFeatures.value) {
    for (const poly of feature.geometry.coordinates) {
      if (pointInPolygonRings(lon, lat, poly)) {
        return feature.properties.name
      }
    }
  }
  if (lon < 9.8 && lat < -0.2) {
    return 'Ogooué-Maritime (Offshore)'
  }
  let bestName = 'Gabon'
  let bestDist = Infinity
  for (const region of regionsState.value) {
    if (region.region_type === 'country' || region.bbox.length < 4) continue
    const [w, s, e, n] = region.bbox
    const cx = (w! + e!) / 2
    const cy = (s! + n!) / 2
    const dist = (lon - cx) ** 2 + (lat - cy) ** 2
    if (dist < bestDist) {
      bestDist = dist
      bestName = region.name
    }
  }
  return bestName
}

/** Liste des provinces (hors Gabon national) avec leur centre approximatif pour l'étiquetage carte. */
export const provinceSummaries = computed(() =>
  regionsState.value
    .filter((r) => r.region_type !== 'country' && r.bbox.length >= 4)
    .map((r) => ({
      code: r.code,
      name: r.name,
      bbox: r.bbox,
      center: [(r.bbox[0]! + r.bbox[2]!) / 2, (r.bbox[1]! + r.bbox[3]!) / 2] as [number, number],
    })),
)

function sumSensors(series: CalendarPoint[]) {
  let modis = 0
  let snpp = 0
  let noaa20 = 0
  for (const p of series) {
    modis += p.modis_count ?? 0
    snpp += p.viirs_snpp_count ?? 0
    noaa20 += p.viirs_noaa20_count ?? 0
  }
  return { modis, snpp, noaa20, total: modis + snpp + noaa20 }
}

function diffAggregate(allVal: number, cleanVal: number): number | null {
  const diff = allVal - cleanVal
  return diff >= 0 ? diff : null
}

function shareOf(part: number | null, total: number | null): number | null {
  if (part === null || total === null || total <= 0) return null
  return Math.round((part / total) * 1000) / 10
}

function sensorPeriod(
  series: CalendarPoint[],
  key: 'modis_count' | 'viirs_snpp_count' | 'viirs_noaa20_count',
): [string | null, string | null] {
  const months = series.filter((p) => p[key] !== null).map((p) => p.month)
  return months.length ? [months[0]!, months[months.length - 1]!] : [null, null]
}

/**
 * Composition chiffrée calculée en direct depuis les séries DB (polygone Gabon `GA`)
 * avec une partition exclusive par capteur et période d'observation, distincte de
 * l'audit statique indépendant des tags FIRMS `type` sur les détections sources SP.
 */
export const composition = computed(() => {
  const gaAll = sumSensors(allSeries.value)
  const gaClean = sumSensors(staticSeries.value)
  const gaExcluded = diffAggregate(gaAll.total, gaClean.total)
  const modisExcluded = diffAggregate(gaAll.modis, gaClean.modis)
  const snppExcluded = diffAggregate(gaAll.snpp, gaClean.snpp)
  const noaa20Excluded = diffAggregate(gaAll.noaa20, gaClean.noaa20)

  const excludedBySensorPartition = [
    {
      id: 'modis' as const,
      label: 'MODIS (Terra + Aqua · 1 km)',
      period: sensorPeriod(allSeries.value, 'modis_count'),
      all: gaAll.modis,
      clean: gaClean.modis,
      excluded: modisExcluded,
      shareOfAll: shareOf(modisExcluded, gaAll.modis),
      shareOfExcluded: shareOf(modisExcluded, gaExcluded),
    },
    {
      id: 'snpp' as const,
      label: 'VIIRS S-NPP (375 m)',
      period: sensorPeriod(allSeries.value, 'viirs_snpp_count'),
      all: gaAll.snpp,
      clean: gaClean.snpp,
      excluded: snppExcluded,
      shareOfAll: shareOf(snppExcluded, gaAll.snpp),
      shareOfExcluded: shareOf(snppExcluded, gaExcluded),
    },
    {
      id: 'noaa20' as const,
      label: 'VIIRS NOAA-20 (375 m)',
      period: sensorPeriod(allSeries.value, 'viirs_noaa20_count'),
      all: gaAll.noaa20,
      clean: gaClean.noaa20,
      excluded: noaa20Excluded,
      shareOfAll: shareOf(noaa20Excluded, gaAll.noaa20),
      shareOfExcluded: shareOf(noaa20Excluded, gaExcluded),
    },
  ]

  // Audit indépendant sur les lignes PostGIS ingérées (archive SP 2000-11 -> 2025-12) :
  // ses parts sont calculées sur `provenance.ga.totalDetections`, jamais sur la série dynamique.
  const provenanceAudit = {
    isIndependentStaticAudit: true as const,
    period: [provenance.archiveStart, provenance.archiveEnd] as const,
    scopeTotal: provenance.ga.totalDetections,
    filteredTotal: provenance.ga.filteredTotal,
    type23Count: provenance.ga.totalType23Count,
    type23ShareOfScope:
      Math.round((provenance.ga.totalType23Count / provenance.ga.totalDetections) * 1000) / 10,
    type0InMaskCount: provenance.ga.totalType0InMaskCount,
    type0InMaskShareOfScope:
      Math.round((provenance.ga.totalType0InMaskCount / provenance.ga.totalDetections) * 1000) / 10,
  }

  return {
    archiveTotal: totalDetectionsDb.value,
    archiveFiles: provenance.files,
    gaTotal: gaAll.total,
    gaClean: gaClean.total,
    gaExcluded,
    gaExcludedShare: shareOf(gaExcluded, gaAll.total),
    gaCleanShare: shareOf(gaClean.total, gaAll.total),

    excludedBySensorPartition,
    provenanceAudit,
    // Alias plats utilisés par la fiche de confiance et les cartes de composition.
    gaType23Count: provenanceAudit.type23Count,
    gaType23Share: provenanceAudit.type23ShareOfScope,
    gaType0InMaskCount: provenanceAudit.type0InMaskCount,
    gaType0InMaskShare: provenanceAudit.type0InMaskShareOfScope,

    modisTotal: gaAll.modis,
    modisClean: gaClean.modis,
    modisExcluded,
    modisExcludedShare: shareOf(modisExcluded, gaAll.modis),

    snppTotal: gaAll.snpp,
    snppClean: gaClean.snpp,
    snppExcluded,
    snppExcludedShare: shareOf(snppExcluded, gaAll.snpp),

    noaa20Total: gaAll.noaa20,
    noaa20Clean: gaClean.noaa20,
    noaa20Excluded,
    noaa20ExcludedShare: shareOf(noaa20Excluded, gaAll.noaa20),

    snppType23Count: provenance.ga.snppType23Count,
    snppType23Share:
      Math.round((provenance.ga.snppType23Count / provenance.ga.snppDetections) * 1000) / 10,
    snppType0MaskedCount: provenance.ga.snppType0InMaskCount,
    archiveSnppType23Count: provenance.archive.snppType23Count,
    archiveSnppType23Share: provenance.archive.snppType23Share,
    gaModisType23Count2017: provenance.ga.modis2017Type23Count,

    maskedCells: maskedCellsCount.value,
    gaGridCells: provenance.gaGridCells,
    gridCellMonths: gridCellMonthsDb.value,
  }
})

export function buildSeriesCsvFallback(
  series: CalendarPoint[],
  regionId = 'GA',
  filterStatic = true,
): string {
  const header =
    'region,month,filter_static,modis_count,viirs_snpp_count,viirs_noaa20_count,harmonized_value,ci_low,ci_high,baseline_median,anomaly_percent,anomaly_absolute,sensor_regime,coverage_status,method_version'
  const methodVersion = methodologyState.value.active_run?.method_version ?? 'v2.0'
  const rows = series.map((p) =>
    [
      regionId,
      p.month,
      String(filterStatic),
      p.modis_count ?? '',
      p.viirs_snpp_count ?? '',
      p.viirs_noaa20_count ?? '',
      p.harmonized_value ?? '',
      p.ci_low ?? '',
      p.ci_high ?? '',
      p.baseline_median ?? '',
      p.anomaly_percent ?? '',
      p.anomaly_absolute ?? '',
      p.sensor_regime,
      p.coverage_status,
      methodVersion,
    ].join(','),
  )
  return `\uFEFF${[header, ...rows].join('\n')}`
}
