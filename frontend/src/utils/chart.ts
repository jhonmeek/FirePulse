import type { EChartsCoreOption } from 'echarts/core'
import type { CalendarPoint, YearMonth } from '@/types/api'
import { formatCount, monthLabel } from '@/utils/calendar'

/** `before` = capteurs bruts seuls (rupture 2012 visible) ; `after` = + série harmonisée et bande. */
export type ChartView = 'before' | 'after'

/** Fenêtre de zoom du graphe, en mois (conservée entre vues et filtres). */
export interface ChartWindow {
  start: YearMonth
  end: YearMonth
}

/**
 * Ramène une fenêtre de zoom dans les mois affichés ; null si elle n'y tombe plus
 * (ou si elle couvre toute la plage : inutile de la mémoriser).
 */
export function clampWindow(win: ChartWindow | null, months: YearMonth[]): ChartWindow | null {
  if (!win || !months.length) return null
  const first = months[0]!
  const last = months[months.length - 1]!
  const start = win.start < first ? first : win.start
  const end = win.end > last ? last : win.end
  if (start > end || (start === first && end === last)) return null
  return { start, end }
}

/**
 * Palette Okabe-Ito (daltonien-compatible) + gris foncé pour l'harmonisé.
 * NOAA-20 en vert bleuté (et pointillés) : le bleu ciel se confondait avec le bleu S-NPP.
 */
export const SERIES_COLORS = {
  modis: '#D55E00',
  snpp: '#0072B2',
  noaa20: '#009E73',
  harmonized: '#1c1917',
  band: 'rgba(28, 25, 23, 0.16)',
} as const

/** Ruptures instrumentales signalées sur l'axe du temps. */
export const BREAKS: { month: YearMonth; label: string }[] = [
  { month: '2002-07', label: 'Aqua démarre' },
  { month: '2012-02', label: 'VIIRS S-NPP' },
]

const nullable = (v: number | null) => (v === null ? '-' : v)

export function inRange(series: CalendarPoint[], [from, to]: [number, number]): CalendarPoint[] {
  return series.filter((p) => {
    const y = +p.month.slice(0, 4)
    return y >= from && y <= to
  })
}

/**
 * Options ECharts du graphe comparatif. Fonction pure : testée sans rendu canvas.
 * La bande d'incertitude = deux séries empilées (ci_low invisible, puis ci_high − ci_low remplie).
 */
export function buildComparisonOption(
  points: CalendarPoint[],
  view: ChartView,
  selectedMonth: YearMonth | null,
  zoomWindow: ChartWindow | null = null,
): EChartsCoreOption {
  const months = points.map((p) => p.month)
  const zoom = clampWindow(zoomWindow, months)
  const zoomRange = zoom ? { startValue: zoom.start, endValue: zoom.end } : {}
  const after = view === 'after'
  const raw = (key: 'modis_count' | 'viirs_snpp_count' | 'viirs_noaa20_count') =>
    points.map((p) => nullable(p[key]))

  const series: Record<string, unknown>[] = [
    {
      name: 'MODIS brut (Terra + Aqua)',
      type: 'line',
      data: raw('modis_count'),
      showSymbol: false,
      lineStyle: { width: 1.25, opacity: after ? 0.55 : 1 },
      color: SERIES_COLORS.modis,
    },
    {
      name: 'VIIRS S-NPP brut',
      type: 'line',
      data: raw('viirs_snpp_count'),
      showSymbol: false,
      lineStyle: { width: 1.25, opacity: after ? 0.55 : 1 },
      color: SERIES_COLORS.snpp,
    },
    {
      name: 'VIIRS NOAA-20 brut',
      type: 'line',
      data: raw('viirs_noaa20_count'),
      showSymbol: false,
      lineStyle: { width: 1.5, type: [5, 3], opacity: after ? 0.6 : 1 },
      color: SERIES_COLORS.noaa20,
    },
  ]

  const marks = BREAKS.filter((b) => months.includes(b.month)).map((b) => ({
    xAxis: b.month,
    label: { formatter: b.label, position: 'insideEndTop', color: '#57534e', fontSize: 11 },
    lineStyle: { color: '#a8a29e', type: 'dashed' },
  }))
  if (selectedMonth && months.includes(selectedMonth)) {
    marks.push({
      xAxis: selectedMonth,
      label: {
        formatter: monthLabel(selectedMonth),
        position: 'insideEndTop',
        color: '#1c1917',
        fontSize: 11,
      },
      lineStyle: { color: '#1c1917', type: 'solid' },
    })
  }
  // Les repères sont portés par la première série, toujours présente.
  series[0]!.markLine = { symbol: 'none', silent: true, data: marks }

  if (after) {
    series.push(
      {
        name: 'ci-base',
        type: 'line',
        stack: 'ci',
        data: points.map((p) => nullable(p.ci_low)),
        lineStyle: { opacity: 0 },
        showSymbol: false,
        silent: true,
        tooltip: { show: false },
      },
      {
        name: 'Intervalle 80 %',
        type: 'line',
        stack: 'ci',
        data: points.map((p) =>
          p.ci_low === null || p.ci_high === null ? '-' : Math.max(0, p.ci_high - p.ci_low),
        ),
        lineStyle: { opacity: 0 },
        areaStyle: { color: SERIES_COLORS.band },
        color: SERIES_COLORS.band,
        showSymbol: false,
        silent: true,
      },
      {
        name: 'Harmonisé (équiv. VIIRS 375 m)',
        type: 'line',
        data: points.map((p) => nullable(p.harmonized_value)),
        showSymbol: false,
        lineStyle: { width: 2.25 },
        color: SERIES_COLORS.harmonized,
        z: 5,
      },
    )
  }

  return {
    animation: false,
    aria: {
      enabled: true,
      label: {
        description: after
          ? 'Séries mensuelles brutes MODIS, VIIRS S-NPP et NOAA-20, et série harmonisée à l’échelle VIIRS avec son intervalle 80 %.'
          : 'Séries mensuelles brutes MODIS, VIIRS S-NPP et NOAA-20 avant harmonisation : saut d’environ ×4 en 2012.',
      },
    },
    grid: { left: 56, right: 16, top: 40, bottom: 64 },
    textStyle: { fontFamily: 'inherit' },
    legend: {
      top: 0,
      data: series.map((s) => s.name as string).filter((n) => n !== 'ci-base'),
      textStyle: { fontSize: 11 },
    },
    tooltip: {
      trigger: 'axis',
      valueFormatter: (v: unknown) => (typeof v === 'number' ? formatCount(Math.round(v)) : '-'),
    },
    xAxis: {
      type: 'category',
      data: months,
      axisLabel: {
        formatter: (m: string) => (m.endsWith('-01') ? m.slice(0, 4) : ''),
        interval: 0,
        hideOverlap: true,
      },
      axisTick: { show: false },
    },
    yAxis: {
      type: 'value',
      name: 'Détections / mois',
      nameTextStyle: { align: 'left', fontSize: 11 },
      axisLabel: { formatter: (v: number) => formatCount(v), color: '#78716c' },
      splitLine: { lineStyle: { color: '#e7e5e4' } },
    },
    // Fenêtre réappliquée à chaque reconstruction (vue avant/après, sélection, filtres).
    dataZoom: [
      { type: 'inside', filterMode: 'none', ...zoomRange },
      {
        type: 'slider',
        height: 18,
        bottom: 8,
        filterMode: 'none',
        borderColor: 'transparent',
        backgroundColor: 'rgba(120, 113, 108, 0.08)',
        fillerColor: 'rgba(234, 88, 12, 0.14)',
        handleStyle: { color: '#ffffff', borderColor: '#a8a29e' },
        moveHandleStyle: { color: '#d6d3d1' },
        dataBackground: {
          lineStyle: { color: '#a8a29e' },
          areaStyle: { color: 'rgba(168, 162, 158, 0.25)' },
        },
        labelFormatter: (_: number, value: string) => value,
        ...zoomRange,
      },
    ],
    series,
  }
}

/**
 * Ratio moyen VIIRS S-NPP / MODIS sur une fenêtre (chiffre du storytelling « saut ×4 »).
 * null si aucun mois exploitable.
 */
export function snppModisRatio(
  points: CalendarPoint[],
  from: YearMonth,
  to: YearMonth,
): number | null {
  let snpp = 0
  let modis = 0
  for (const p of points) {
    if (p.month < from || p.month > to || p.viirs_snpp_count === null || p.modis_count === null)
      continue
    snpp += p.viirs_snpp_count
    modis += p.modis_count
  }
  return modis > 0 ? snpp / modis : null
}
