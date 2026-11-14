import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import type { CalendarResponse } from '@/types/api'
import calStatic from '@/mocks/calendar_GA_static.json'
import YearComparison from '@/components/YearComparison.vue'
import { SERIES_COLORS, buildComparisonOption, clampWindow, inRange } from '@/utils/chart'
import { compareYear, defaultCompareYear } from '@/utils/comparison'

const series = (calStatic as unknown as CalendarResponse).series
const months = (from: number, to: number) => inRange(series, [from, to]).map((p) => p.month)

describe('clampWindow (zoom conservé)', () => {
  it('garde une fenêtre incluse dans la plage', () => {
    expect(clampWindow({ start: '2010-01', end: '2015-12' }, months(2001, 2025))).toEqual({
      start: '2010-01',
      end: '2015-12',
    })
  })
  it('la ramène dans une plage réduite', () => {
    expect(clampWindow({ start: '2010-01', end: '2015-12' }, months(2014, 2020))).toEqual({
      start: '2014-01',
      end: '2015-12',
    })
  })
  it('l’oublie si elle sort de la plage ou la couvre entièrement', () => {
    expect(clampWindow({ start: '2001-01', end: '2005-12' }, months(2015, 2020))).toBeNull()
    expect(clampWindow({ start: '1990-01', end: '2030-12' }, months(2015, 2020))).toBeNull()
    expect(clampWindow(null, months(2015, 2020))).toBeNull()
  })
  it('est appliquée aux deux zooms ECharts, quelle que soit la vue', () => {
    for (const view of ['before', 'after'] as const) {
      const o = buildComparisonOption(inRange(series, [2001, 2025]), view, null, {
        start: '2010-01',
        end: '2015-12',
      })
      const dz = o.dataZoom as { startValue?: string; endValue?: string }[]
      expect(dz.map((d) => [d.startValue, d.endValue])).toEqual([
        ['2010-01', '2015-12'],
        ['2010-01', '2015-12'],
      ])
    }
  })
})

it('NOAA-20 n’a plus la même teinte que S-NPP (ancien bleu ciel : même teinte ≈ 201°)', () => {
  const hue = (h: string) => {
    const [r, g, b] = [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16) / 255) as [
      number,
      number,
      number,
    ]
    const max = Math.max(r, g, b)
    const d = max - Math.min(r, g, b)
    const raw = max === r ? ((g - b) / d) % 6 : max === g ? (b - r) / d + 2 : (r - g) / d + 4
    return (raw * 60 + 360) % 360
  }
  expect(Math.abs(hue('#56B4E9') - hue(SERIES_COLORS.snpp))).toBeLessThan(5) // le défaut corrigé
  expect(Math.abs(hue(SERIES_COLORS.noaa20) - hue(SERIES_COLORS.snpp))).toBeGreaterThan(30)
})

describe('comparaison année / médiane', () => {
  it('cumule uniquement les mois disponibles et calcule l’écart', () => {
    const c = compareYear(series, 2024)
    expect(c.months).toHaveLength(12)
    const expected = c.months.reduce((s, m) => s + (m.value ?? 0), 0)
    expect(c.total).toBeCloseTo(expected, 6)
    expect(c.deltaPercent).toBeCloseTo((100 * (c.total - c.medianTotal)) / c.medianTotal, 6)
    expect(c.peak).not.toBeNull()
  })
  it('année partielle (2000 : nov.-déc.) : seulement 2 mois comptés', () => {
    const c = compareYear(series, 2000)
    expect(c.months.filter((m) => m.value !== null)).toHaveLength(2)
  })
  it('année par défaut : celle du mois sélectionné, sinon la dernière complète', () => {
    expect(defaultCompareYear(series, [2001, 2025], '2007-01')).toBe(2007)
    expect(defaultCompareYear(series, [2001, 2025], null)).toBe(2025)
    expect(defaultCompareYear(series, [2001, 2010], '2024-01')).toBe(2010)
  })
})

describe('YearComparison', () => {
  it('affiche les indicateurs, un graphe accessible et une table pour lecteur d’écran', async () => {
    const w = mount(YearComparison, { props: { series, years: [2023, 2024], year: 2024 } })
    expect(w.text()).toContain('Écart cumulé')
    expect(w.get('svg[role="img"]').attributes('aria-label')).toMatch(/^2024 comparé à la médiane/)
    expect(w.findAll('table tbody tr')).toHaveLength(12)
    await w.get('select').setValue('2023')
    expect(w.emitted('update:year')).toEqual([[2023]])
  })
})
