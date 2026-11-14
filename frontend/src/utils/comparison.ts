import type { CalendarPoint } from '@/types/api'
import { seasonalBaselines } from '@/utils/anomalies'

export interface ComparisonMonth {
  /** 1..12 */
  month: number
  value: number | null
  median: number | null
  iqr: [number, number] | null
}

export interface YearComparison {
  year: number
  months: ComparisonMonth[]
  /** Somme des mois disponibles de l'année, et des médianes de ces mêmes mois. */
  total: number
  medianTotal: number
  /** Écart cumulé en %, null si la médiane cumulée est nulle. */
  deltaPercent: number | null
  /** Mois le plus au-dessus de sa médiane (écart absolu), null si aucun. */
  peak: ComparisonMonth | null
  /** Nombre de mois au-dessus du 3e quartile (activité inhabituellement forte). */
  aboveIqr: number
}

/**
 * Met une année en regard de l'année type (médiane + IQR par mois, 2001-2025).
 * Le cumul ne porte que sur les mois disponibles pour éviter de comparer une année
 * partielle à douze médianes.
 */
export function compareYear(series: CalendarPoint[], year: number): YearComparison {
  const baselines = new Map(seasonalBaselines(series).map((b) => [b.month, b]))
  const byMonth = new Map(
    series.filter((p) => p.month.startsWith(`${year}-`)).map((p) => [+p.month.slice(5), p]),
  )
  const months: ComparisonMonth[] = Array.from({ length: 12 }, (_, i) => {
    const b = baselines.get(i + 1)
    return {
      month: i + 1,
      value: byMonth.get(i + 1)?.harmonized_value ?? null,
      median: b?.median ?? null,
      iqr: b?.iqr ?? null,
    }
  })
  const available = months.filter((m) => m.value !== null && m.median !== null)
  const total = available.reduce((s, m) => s + m.value!, 0)
  const medianTotal = available.reduce((s, m) => s + m.median!, 0)
  const peak = available.reduce<ComparisonMonth | null>(
    (best, m) => (!best || m.value! - m.median! > best.value! - best.median! ? m : best),
    null,
  )
  return {
    year,
    months,
    total,
    medianTotal,
    deltaPercent: medianTotal > 0 ? (100 * (total - medianTotal)) / medianTotal : null,
    peak: peak && peak.value! > peak.median! ? peak : null,
    aboveIqr: available.filter((m) => m.iqr && m.value! > m.iqr[1]).length,
  }
}

/** Année proposée par défaut : celle du mois sélectionné, sinon la dernière complète affichée. */
export function defaultCompareYear(
  series: CalendarPoint[],
  [from, to]: [number, number],
  selectedMonth: string | null,
): number | null {
  if (selectedMonth) {
    const y = +selectedMonth.slice(0, 4)
    if (y >= from && y <= to) return y
  }
  const counts = new Map<number, number>()
  for (const p of series) {
    const y = +p.month.slice(0, 4)
    if (y >= from && y <= to && p.harmonized_value !== null) counts.set(y, (counts.get(y) ?? 0) + 1)
  }
  const full = [...counts].filter(([, n]) => n === 12).map(([y]) => y)
  const any = [...counts.keys()]
  return full.length ? Math.max(...full) : any.length ? Math.max(...any) : null
}
