import type { CalendarPoint, CalendarResponse } from '@/types/api'

export interface SeasonalBaseline {
  /** 1..12 */
  month: number
  median: number
  iqr: [number, number] | null
}

/**
 * Médiane + IQR par mois calendaire, lues dans la série (le backend les répète sur
 * chaque mois de même rang). Évite un appel /anomalies/ redondant.
 */
export function seasonalBaselines(series: CalendarPoint[]): SeasonalBaseline[] {
  const out = new Map<number, SeasonalBaseline>()
  for (const p of series) {
    const m = +p.month.slice(5)
    if (out.has(m) || p.baseline_median === null) continue
    out.set(m, { month: m, median: p.baseline_median, iqr: p.baseline_iqr })
  }
  return [...out.values()].sort((a, b) => a.month - b.month)
}

/** Mêmes règles que /api/v1/anomalies/ : anomalie en % non nulle, classée, bornée à topN. */
export function rankAnomalies(series: CalendarPoint[], topN = 5) {
  const ranked = series.filter((p) => p.anomaly_percent !== null && p.harmonized_value !== null)
  const byPct = (dir: 1 | -1) => (a: CalendarPoint, b: CalendarPoint) =>
    dir * (a.anomaly_percent! - b.anomaly_percent!)
  return {
    positive: [...ranked].sort(byPct(-1)).slice(0, topN),
    negative: [...ranked].sort(byPct(1)).slice(0, topN),
  }
}

export interface MaskedSummary {
  /** Détections brutes (MODIS + S-NPP + NOAA-20) sans filtre. */
  total: number
  /** Détections retirées par le filtre (type ≠ 0 ou cellule statique 0.05°). */
  masked: number
  share: number
}

/**
 * Détections retirées par le filtre torchères sur la période affichée :
 * différence entre la série « toutes anomalies » et la série filtrée.
 */
export function maskedSummary(
  all: CalendarResponse | null,
  filtered: CalendarResponse | null,
  [from, to]: [number, number],
): MaskedSummary | null {
  if (!all || !filtered) return null
  const sum = (c: CalendarResponse) =>
    c.series.reduce((s, p) => {
      const y = +p.month.slice(0, 4)
      if (y < from || y > to) return s
      return s + (p.modis_count ?? 0) + (p.viirs_snpp_count ?? 0) + (p.viirs_noaa20_count ?? 0)
    }, 0)
  const total = sum(all)
  const masked = total - sum(filtered)
  return { total, masked, share: total > 0 ? masked / total : 0 }
}
