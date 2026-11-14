import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import type { CalendarResponse } from '@/types/api'
import calStatic from '@/mocks/calendar_GA_static.json'
import HarmonizationToggle from '@/components/HarmonizationToggle.vue'
import { createPinia, setActivePinia } from 'pinia'
import { useFiltersStore } from '@/stores/filters'
import { cellColor, displayValue, rawEraValue, valueMax } from '@/utils/calendar'
import { SERIES_COLORS, buildComparisonOption, clampWindow, inRange } from '@/utils/chart'

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

describe('vue Avant : capteur d’époque', () => {
  const at = (m: string) => series.find((p) => p.month === m)!

  it('MODIS jusqu’à janvier 2012, VIIRS S-NPP à partir de février 2012', () => {
    expect(rawEraValue(at('2011-12'))).toEqual({
      value: at('2011-12').modis_count,
      sensor: 'modis',
    })
    expect(rawEraValue(at('2012-01'))).toEqual({
      value: at('2012-01').modis_count,
      sensor: 'modis',
    })
    expect(rawEraValue(at('2012-02'))).toEqual({
      value: at('2012-02').viirs_snpp_count,
      sensor: 'snpp',
    })
  })

  it('valeur affichée selon la vue, null si le capteur manque', () => {
    expect(displayValue(at('2005-08'), 'after')).toBe(at('2005-08').harmonized_value)
    expect(displayValue(at('2005-08'), 'before')).toBe(at('2005-08').modis_count)
    expect(displayValue({ ...at('2015-08'), viirs_snpp_count: null }, 'before')).toBeNull()
    expect(displayValue(null, 'before')).toBeNull()
  })

  it('même échelle : un mois MODIS paraît plus pâle avant qu’après harmonisation (rupture visible)', () => {
    const lum = (c: string) =>
      c
        .match(/\d+/g)!
        .slice(0, 3)
        .map(Number)
        .reduce((a, b) => a + b, 0)
    const max = valueMax(inRange(series, [2001, 2025]))
    const p = at('2005-08')
    expect(lum(cellColor(p, 'value', max, 'before')!)).toBeGreaterThan(
      lum(cellColor(p, 'value', max, 'after')!),
    )
    // Mois S-NPP observé : brut = harmonisé, même couleur.
    const q = at('2015-08')
    expect(cellColor(q, 'value', max, 'before')).toBe(cellColor(q, 'value', max, 'after'))
    // Le mode anomalie est ignoré en vue Avant.
    expect(cellColor(p, 'anomaly', max, 'before')).toBe(cellColor(p, 'value', max, 'before'))
  })
})

describe('HarmonizationToggle', () => {
  it('deux bascules (calendrier, graphe) partagent la même vue', async () => {
    setActivePinia(createPinia())
    const a = mount(HarmonizationToggle, { props: { name: 'calendar-view' } })
    const b = mount(HarmonizationToggle, { props: { name: 'chart-view' } })
    await a.get('input[value="before"]').setValue(true)
    expect(useFiltersStore().harmonizationView).toBe('before')
    expect((b.get('input[value="before"]').element as HTMLInputElement).checked).toBe(true)
    await b.get('input[value="after"]').setValue(true)
    expect((a.get('input[value="after"]').element as HTMLInputElement).checked).toBe(true)
    expect(a.get('input').attributes('name')).not.toBe(b.get('input').attributes('name'))
  })
})
