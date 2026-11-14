import { interpolateYlOrRd } from 'd3-scale-chromatic'
import type { BBox, GridCellSummaryProps, StaticFlareMaskProps } from '@/types/api'
import { formatCount } from '@/utils/calendar'

export type MapMetric = 'snpp' | 'modis' | 'noaa20'

export const MAP_METRICS: Record<
  MapMetric,
  { key: keyof GridCellSummaryProps & `${string}_count`; label: string; since: number }
> = {
  snpp: { key: 'viirs_snpp_count', label: 'VIIRS S-NPP', since: 2012 },
  modis: { key: 'modis_count', label: 'MODIS (Terra + Aqua)', since: 2000 },
  noaa20: { key: 'viirs_noaa20_count', label: 'VIIRS NOAA-20', since: 2018 },
}

/** S-NPP par défaut ; MODIS si la plage s'arrête avant 2012 (S-NPP n'existe pas encore). */
export const defaultMetric = ([, to]: [number, number]): MapMetric => (to < 2012 ? 'modis' : 'snpp')

/** Le comptage brut d'un seul capteur n'est comparable qu'à lui-même : pas de mélange MODIS/VIIRS. */
export const metricCoversRange = (m: MapMetric, [from]: [number, number]) =>
  from >= MAP_METRICS[m].since

const FLOOR = 0.08

/**
 * Paliers de la palette de la grille : même échelle racine carrée et même YlOrRd que le
 * calendrier (mode intensité), pour une lecture cohérente des deux vues.
 */
export function gridStops(
  max: number,
  steps = 6,
): { value: number; color: string; label: string }[] {
  return Array.from({ length: steps }, (_, i) => {
    const t = i / (steps - 1)
    const value = t * t * Math.max(1, max)
    return {
      value,
      color: interpolateYlOrRd(FLOOR + (1 - FLOOR) * t),
      label: formatCount(Math.round(value)),
    }
  })
}

/** Expression MapLibre `fill-color` : interpolation linéaire entre les paliers racine carrée. */
export function gridColorExpression(metric: MapMetric, max: number): unknown[] {
  const stops = gridStops(max, 8)
  const expr: unknown[] = ['interpolate', ['linear'], ['get', MAP_METRICS[metric].key]]
  for (const s of stops) expr.push(s.value, s.color)
  return expr
}

export function maxMetric(
  features: { properties: GridCellSummaryProps }[],
  metric: MapMetric,
): number {
  const key = MAP_METRICS[metric].key
  return features.reduce((m, f) => Math.max(m, f.properties[key] as number), 0)
}

/**
 * Rectangle dessiné → bbox [ouest, sud, est, nord] normalisée, arrondie à 0,01°
 * (≈ 1 km, sous la résolution de la grille). null si la zone est trop petite.
 */
export function bboxFromCorners(
  a: { lng: number; lat: number },
  b: { lng: number; lat: number },
  minSpan = 0.05,
): BBox | null {
  const r = (v: number) => Math.round(v * 100) / 100
  const w = r(Math.min(a.lng, b.lng))
  const e = r(Math.max(a.lng, b.lng))
  const s = r(Math.min(a.lat, b.lat))
  const n = r(Math.max(a.lat, b.lat))
  if (e - w < minSpan || n - s < minSpan) return null
  return [w, s, e, n]
}

export function bboxPolygon([w, s, e, n]: BBox) {
  return {
    type: 'Polygon' as const,
    coordinates: [
      [
        [w, s],
        [e, s],
        [e, n],
        [w, n],
        [w, s],
      ],
    ],
  }
}

export const STATIC_REASON_LABELS: Record<StaticFlareMaskProps['reason'], string> = {
  persistent_type23_and_snpp_frequency: 'Source statique déclarée (type 2/3) et active en continu',
  type23_static_threshold: 'Source statique déclarée par FIRMS (type 2/3)',
  snpp_high_persistence_48m: 'Active au moins 48 mois en VIIRS S-NPP',
}

/** Texte d'info-bulle d'une cellule de grille (FR, comptages bruts). */
export function gridCellSummary(p: GridCellSummaryProps): string[] {
  const [lat, lon] = p.cell_id.split('_').map(Number) as [number, number]
  const f = (v: number) =>
    v.toLocaleString('fr-FR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  return [
    `Cellule ${f(lat)}° ; ${f(lon)}° (0,25°)`,
    `VIIRS S-NPP : ${formatCount(p.viirs_snpp_count)}`,
    `MODIS : ${formatCount(p.modis_count)}`,
    `VIIRS NOAA-20 : ${formatCount(p.viirs_noaa20_count)}`,
    `${p.months_count} mois avec détection`,
  ]
}
