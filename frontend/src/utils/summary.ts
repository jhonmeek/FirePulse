import type { CalendarPoint, YearMonth } from '@/types/api'
import { seasonalBaselines } from '@/utils/anomalies'
import { isProvisional } from '@/utils/calendar'

/** Résumé « en bref » affiché en tête de page (lecture grand public). */
export interface YearSummary {
  year: number
  /** Somme des 12 mois harmonisés de l'année. */
  total: number
  /** Année normale = somme des 12 médianes mensuelles 2001-2025 (même référence que la ligne « Normale »). */
  normal: number
  /** Écart de l'année à la normale, en % (null si normale nulle). */
  deltaPercent: number | null
  /** Mois (1..12) dont la médiane est la plus haute : pic de la saison des feux. */
  peakMonth: number
  /** Au moins un mois de l'année est provisoire ou incomplet. */
  provisional: boolean
}

/**
 * Dernière année complète (12 mois renseignés) jusqu'à `maxYear` inclus, comparée à l'année
 * normale. null si aucune année complète ou si les médianes mensuelles manquent.
 */
export function yearSummary(series: CalendarPoint[], maxYear: number): YearSummary | null {
  const baselines = seasonalBaselines(series)
  if (baselines.length !== 12) return null
  const normal = baselines.reduce((s, b) => s + b.median, 0)
  const peakMonth = baselines.reduce((a, b) => (b.median > a.median ? b : a)).month

  const byYear = new Map<number, CalendarPoint[]>()
  for (const p of series) {
    const y = +p.month.slice(0, 4)
    if (y > maxYear || p.harmonized_value === null) continue
    byYear.set(y, [...(byYear.get(y) ?? []), p])
  }
  const year = [...byYear.keys()]
    .filter((y) => byYear.get(y)!.length === 12)
    .sort((a, b) => b - a)[0]
  if (year === undefined) return null

  const months = byYear.get(year)!
  const total = months.reduce((s, p) => s + p.harmonized_value!, 0)
  return {
    year,
    total,
    normal,
    deltaPercent: normal > 0 ? (100 * (total - normal)) / normal : null,
    peakMonth,
    provisional: months.some((p) => isProvisional(p.coverage_status)),
  }
}

/** Dernier mois renseigné de la série, éventuellement borné à une année maximale. */
export function lastDataMonth(series: CalendarPoint[], maxYear = Infinity): YearMonth | null {
  let last: YearMonth | null = null
  for (const p of series) {
    if (p.harmonized_value === null || +p.month.slice(0, 4) > maxYear) continue
    if (!last || p.month > last) last = p.month
  }
  return last
}

/** Arrondi lisible : centaine au-delà de 1 000, dizaine en dessous. */
export function roughCount(v: number): number {
  const step = v >= 1000 ? 100 : v >= 100 ? 10 : 1
  return Math.round(v / step) * step
}

/** « 8 % de plus qu'une année normale », « proche d'une année normale (+3 %) »… */
export function deltaPhrase(delta: number | null): string {
  if (delta === null) return 'sans référence normale disponible'
  const pct = Math.round(Math.abs(delta))
  if (pct < 5) return `proche d'une année normale (${delta >= 0 ? '+' : '-'}${pct} %)`
  return `${pct} % de ${delta > 0 ? 'plus' : 'moins'} qu'une année normale`
}
