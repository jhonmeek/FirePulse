import calendarStaticJson from '@/data/calendar-static.json'
import calendarAllJson from '@/data/calendar-all.json'
import methodologyJson from '@/data/methodology.json'
import regionsJson from '@/data/regions.json'
import hotspotsStaticJson from '@/data/hotspots-static.json'
import hotspotsAllJson from '@/data/hotspots-all.json'
import type { Polygon } from 'geojson'
import { provenance } from './provenance'
import type {
  CalendarPoint,
  CalendarResponse,
  GlobePoint,
  GridBundle,
  GridFeature,
  GridYearlyRow,
  HotspotsMock,
  MethodologyResponse,
  RegionFeature,
  RegionFeatureProps,
  RegionsResponse,
  StaticCellFeatureProps,
  StaticFeature,
} from './types'

export const calendarStatic = calendarStaticJson as unknown as CalendarResponse
export const calendarAll = calendarAllJson as unknown as CalendarResponse
export const methodology = methodologyJson as unknown as MethodologyResponse
export const regions = (regionsJson as unknown as RegionsResponse).regions
export const hotspotsStatic = hotspotsStaticJson as unknown as HotspotsMock
export const hotspotsAll = hotspotsAllJson as unknown as HotspotsMock

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

export const YEARS = Array.from({ length: 26 }, (_, i) => 2000 + i)

/** Détections brutes MODIS + VIIRS S-NPP : les deux capteurs du défi, sans double comptage NOAA-20. */
export function rawCount(p: CalendarPoint): number {
  return (p.modis_count ?? 0) + (p.viirs_snpp_count ?? 0)
}

/** Toutes les détections disponibles, y compris NOAA-20 (utile pour la carte). */
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
  return `${MONTH_NAMES[m - 1]} ${yearOf(month)}`
}

export function monthShortLabel(month: string): string {
  return `${MONTH_SHORT[monthNumber(month) - 1]} ${String(yearOf(month)).slice(2)}`
}

export function formatCount(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  return new Intl.NumberFormat('fr-FR').format(Math.round(value))
}

export function formatPercent(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  const sign = value > 0 ? '+' : ''
  return `${sign}${new Intl.NumberFormat('fr-FR', {
    maximumFractionDigits: digits,
    minimumFractionDigits: digits,
  }).format(value)} %`
}

export function median(values: number[]): number {
  if (!values.length) return 0
  const sorted = [...values].sort((a, b) => a - b)
  const mid = Math.floor(sorted.length / 2)
  return sorted.length % 2 ? sorted[mid]! : (sorted[mid - 1]! + sorted[mid]!) / 2
}

export const staticSeries = calendarStatic.series
export const allSeries = calendarAll.series

/** Médianes historiques 2001–2025, par mois calendaire. */
export const monthlyMedians = Array.from({ length: 12 }, (_, i) => {
  const values = staticSeries
    .filter((p) => yearOf(p.month) >= 2001 && monthNumber(p.month) === i + 1)
    .map((p) => p.harmonized_value)
    .filter((v): v is number => v !== null)
  return median(values)
})

/** Saison principale : les mois dont la médiane dépasse 500 détections. */
export const mainSeason = monthlyMedians
  .map((value, index) => ({ month: index + 1, value }))
  .filter((d) => d.value >= 500)
  .map((d) => d.month)

/** Second épisode : médiane entre 250 et 500 détections. */
export const secondarySeason = monthlyMedians
  .map((value, index) => ({ month: index + 1, value }))
  .filter((d) => d.value >= 250 && d.value < 500)
  .map((d) => d.month)

export function isPartialCoverage(point: CalendarPoint): boolean {
  return point.coverage_status !== 'complete_sp'
}

export function findMonth(month: string): CalendarPoint | undefined {
  return staticSeries.find((p) => p.month === month)
}

/** Août 2024 : le mois raconté dans l'histoire. */
export const featuredMonth = findMonth('2024-08') ?? staticSeries[staticSeries.length - 1]!

/** Janvier 2024 : le mois le plus atypique de la décennie. */
export const anomalyMonth = findMonth('2024-01')

export const topAnomalies = [...staticSeries]
  .filter((p) => p.anomaly_percent !== null)
  .sort((a, b) => (b.anomaly_percent ?? 0) - (a.anomaly_percent ?? 0))
  .slice(0, 6)

/** Rang historique du mois dans son mois calendaire (1 = plus actif). */
export function historicalRank(point: CalendarPoint): number {
  const sameMonth = staticSeries
    .filter(
      (p) =>
        monthNumber(p.month) === monthNumber(point.month) &&
        p.harmonized_value !== null &&
        yearOf(p.month) >= 2001,
    )
    .sort((a, b) => (b.harmonized_value ?? 0) - (a.harmonized_value ?? 0))
  return sameMonth.findIndex((p) => p.month === point.month) + 1
}

/** Cellule 0,25° : identifiant `lat_lon` = coin sud-ouest. */
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

/** Points du globe : centroïdes de cellules + jitter proportionnel à l'intensité. */
export function buildGlobePoints(): GlobePoint[] {
  const { grid } = buildGrid(2000, 2025, true)
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

export function buildRegionFeatures(): RegionFeature[] {
  return regions
    .filter((r): r is typeof r & { geometry: NonNullable<typeof r.geometry> } => !!r.geometry)
    .map((r) => ({
      type: 'Feature' as const,
      geometry: r.geometry,
      properties: {
        code: r.code,
        name: r.name,
        region_type: r.region_type,
      } satisfies RegionFeatureProps,
    }))
}

export const regionFeatures = buildRegionFeatures()
export const countryFeature = regionFeatures.find((f) => f.properties.region_type === 'country')
export const provinceFeatures = regionFeatures.filter((f) => f.properties.region_type !== 'country')

/** Composition documentée (audit M1/M2, 2000–2025). */
export const composition = {
  snppStaticShare: provenance.snppStaticShare,
  noaa20StaticShare: provenance.noaa20StaticShare,
  modisStaticShare: provenance.modisStaticShare,
  snppStaticCount: provenance.snppStaticCount,
  noaa20StaticCount: provenance.noaa20StaticCount,
  modisStaticCount: provenance.modisStaticCount,
  maskedCells: provenance.maskedCells,
  gridCells: provenance.gridCells,
  gridCellMonths: provenance.gridCellMonths,
  detections: provenance.totalDetections,
  modisDetections: provenance.modisDetections,
  snppDetections: provenance.snppDetections,
  noaa20Detections: provenance.noaa20Detections,
}

export const metrics = methodology.active_run?.metrics.models_out_of_sample ?? {}
