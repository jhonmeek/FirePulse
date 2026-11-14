import { interpolatePuOr, interpolateYlOrRd } from 'd3-scale-chromatic'
import type { CalendarPoint, CoverageStatus, SensorRegime, YearMonth } from '@/types/api'

export type ColorMode = 'value' | 'anomaly'

export const MONTHS_SHORT = [
  'janv.',
  'févr.',
  'mars',
  'avr.',
  'mai',
  'juin',
  'juil.',
  'août',
  'sept.',
  'oct.',
  'nov.',
  'déc.',
] as const

export const MONTHS_LONG = [
  'janvier',
  'février',
  'mars',
  'avril',
  'mai',
  'juin',
  'juillet',
  'août',
  'septembre',
  'octobre',
  'novembre',
  'décembre',
] as const

export const REGIME_LABELS: Record<SensorRegime, string> = {
  partial_year: 'MODIS Terra seul (année partielle)',
  modis_terra_only: 'MODIS Terra seul',
  modis_terra_aqua: 'MODIS Terra + Aqua reconstitué',
  viirs_snpp_observed: 'VIIRS S-NPP observé',
  viirs_noaa20_bridge: 'Pont VIIRS NOAA-20',
  missing: 'Aucune source',
}

export const COVERAGE_LABELS: Record<CoverageStatus, string> = {
  complete_sp: 'Mois complet (produit standard)',
  partial_sp: 'Mois incomplet (produit standard)',
  mixed_sp_nrt: 'Mixte standard / temps quasi réel',
  nrt_only: 'Temps quasi réel (provisoire)',
  no_data: 'Aucune donnée',
}

/** Statuts affichés hachurés : valeur provisoire ou incomplète. */
export const isProvisional = (s: CoverageStatus) =>
  s === 'partial_sp' || s === 'mixed_sp_nrt' || s === 'nrt_only'

const nf0 = new Intl.NumberFormat('fr-FR', { maximumFractionDigits: 0 })
const nf1 = new Intl.NumberFormat('fr-FR', { maximumFractionDigits: 1 })

export const formatCount = (v: number | null) => (v === null ? '—' : nf0.format(v))

export function monthLabel(month: YearMonth, long = true): string {
  const [y, m] = month.split('-')
  const idx = Number(m) - 1
  return `${(long ? MONTHS_LONG : MONTHS_SHORT)[idx]} ${y}`
}

/** Anomalie lisible : % si médiane > 0, sinon écart absolu (cas B = 0 du guide). */
export function formatAnomaly(
  p: Pick<CalendarPoint, 'anomaly_percent' | 'anomaly_absolute'>,
): string {
  if (p.anomaly_percent !== null) {
    const sign = p.anomaly_percent > 0 ? '+' : p.anomaly_percent < 0 ? '−' : ''
    return `${sign}${nf1.format(Math.abs(p.anomaly_percent))} %`
  }
  if (p.anomaly_absolute !== null) {
    const sign = p.anomaly_absolute > 0 ? '+' : p.anomaly_absolute < 0 ? '−' : ''
    return `${sign}${nf0.format(Math.abs(p.anomaly_absolute))} (écart absolu, médiane nulle)`
  }
  return '—'
}

export interface CalendarCell {
  month: YearMonth
  year: number
  monthIndex: number
  point: CalendarPoint | null
}

/** Matrice années × 12 mois ; un mois absent de la série donne `point: null`. */
export function buildMatrix(
  series: CalendarPoint[],
  fromYear: number,
  toYear: number,
): CalendarCell[][] {
  const byMonth = new Map(series.map((p) => [p.month, p]))
  const rows: CalendarCell[][] = []
  for (let year = fromYear; year <= toYear; year++) {
    rows.push(
      Array.from({ length: 12 }, (_, i) => {
        const month = `${year}-${String(i + 1).padStart(2, '0')}`
        return { month, year, monthIndex: i, point: byMonth.get(month) ?? null }
      }),
    )
  }
  return rows
}

/** Bornes de l'échelle : max des valeurs harmonisées affichées. */
export function valueMax(series: CalendarPoint[]): number {
  return series.reduce((m, p) => Math.max(m, p.harmonized_value ?? 0), 0)
}

/** Plus bas de la palette (évite un jaune quasi blanc confondu avec le fond). */
const VALUE_FLOOR = 0.08
const valueT = (v: number, max: number) => (max > 0 ? Math.sqrt(Math.max(0, v) / max) : 0)

/** d3 PuOr : t = 0 violet foncé, t = 1 orange foncé → orange = au-dessus de la médiane. */
const anomalyColor = (pct: number) => interpolatePuOr(0.5 + pct / (2 * ANOMALY_CLAMP))

/** Anomalie bornée à ±ANOMALY_CLAMP % pour la palette divergente. */
export const ANOMALY_CLAMP = 150

/**
 * Couleur d'une cellule.
 * - `value` : YlOrRd sur échelle racine carrée (distribution asymétrique 0 → ~6 000 ;
 *   le log écrasait les contrastes entre mois calmes et pics).
 * - `anomaly` : PuOr divergente centrée sur 0 (violet = sous la médiane, orange = au-dessus).
 * Ces deux palettes restent lisibles pour les principales formes de daltonisme.
 */
export function cellColor(p: CalendarPoint | null, mode: ColorMode, max: number): string | null {
  if (!p || p.harmonized_value === null) return null
  if (mode === 'value') {
    return interpolateYlOrRd(VALUE_FLOOR + (1 - VALUE_FLOOR) * valueT(p.harmonized_value, max))
  }
  if (p.anomaly_percent === null) return null
  const clamped = Math.max(-ANOMALY_CLAMP, Math.min(ANOMALY_CLAMP, p.anomaly_percent))
  return anomalyColor(clamped)
}

/** Valeurs de la légende (`steps` couleurs) pour le mode courant. */
export function legendStops(
  mode: ColorMode,
  max: number,
  steps = 6,
): { color: string; label: string }[] {
  return Array.from({ length: steps }, (_, i) => {
    const t = i / (steps - 1)
    if (mode === 'value') {
      const v = t * t * max
      return {
        color: interpolateYlOrRd(VALUE_FLOOR + (1 - VALUE_FLOOR) * t),
        label: formatCount(Math.round(v)),
      }
    }
    const pct = -ANOMALY_CLAMP + t * 2 * ANOMALY_CLAMP
    const sign = pct > 0 ? '+' : pct < 0 ? '−' : ''
    const edge = i === 0 ? '≤ ' : i === steps - 1 ? '≥ ' : ''
    return { color: anomalyColor(pct), label: `${edge}${sign}${nf0.format(Math.abs(pct))} %` }
  })
}

/**
 * Rang du mois parmi le même mois calendaire sur 2001–2025 (1 = le plus élevé).
 * Calculé sur la série complète, pas sur la plage d'années affichée.
 */
export function historicalRank(
  series: CalendarPoint[],
  month: YearMonth,
): { rank: number; total: number } | null {
  const target = series.find((p) => p.month === month)
  if (!target || target.harmonized_value === null) return null
  const mm = month.slice(5)
  const peers = series.filter(
    (p) =>
      p.month.slice(5) === mm &&
      p.month >= '2001' &&
      p.month < '2026' &&
      p.harmonized_value !== null,
  )
  if (!peers.some((p) => p.month === month)) return null
  const rank = 1 + peers.filter((p) => p.harmonized_value! > target.harmonized_value!).length
  return { rank, total: peers.length }
}
