import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import SummaryBanner from '@/components/SummaryBanner.vue'
import MonthDetail from '@/components/MonthDetail.vue'
import type { CalendarPoint, CalendarResponse } from '@/types/api'
import calStatic from '@/mocks/calendar_GA_static.json'
import { seasonalBaselines } from '@/utils/anomalies'
import { deltaPhrase, lastDataMonth, roughCount, yearSummary } from '@/utils/summary'

const series = (calStatic as unknown as CalendarResponse).series

describe('yearSummary', () => {
  it('résume la dernière année complète face à la somme des médianes mensuelles', () => {
    const s = yearSummary(series, 2025)!
    expect(s.year).toBe(2025)
    const total = series
      .filter((p) => p.month.startsWith('2025'))
      .reduce((a, p) => a + p.harmonized_value!, 0)
    expect(s.total).toBeCloseTo(total)
    const normal = seasonalBaselines(series).reduce((a, b) => a + b.median, 0)
    expect(s.normal).toBeCloseTo(normal)
    expect(s.deltaPercent).toBeCloseTo((100 * (total - normal)) / normal)
    const peak = seasonalBaselines(series).reduce((a, b) => (b.median > a.median ? b : a))
    expect(s.peakMonth).toBe(peak.month)
  })

  it('borne l’année à la plage choisie et ignore les années incomplètes', () => {
    expect(yearSummary(series, 2015)!.year).toBe(2015)
    const holed: CalendarPoint[] = series.map((p) =>
      p.month === '2025-06' ? { ...p, harmonized_value: null } : p,
    )
    expect(yearSummary(holed, 2025)!.year).toBe(2024)
    expect(yearSummary([], 2025)).toBeNull()
  })

  it('dernier mois renseigné, arrondi lisible et phrase d’écart', () => {
    expect(lastDataMonth(series)).toBe('2025-12')
    expect(lastDataMonth(series, 2010)).toBe('2010-12')
    expect(roughCount(12_345)).toBe(12_300)
    expect(roughCount(456)).toBe(460)
    expect(deltaPhrase(8.4)).toBe("8 % de plus qu'une année normale")
    expect(deltaPhrase(-12)).toBe("12 % de moins qu'une année normale")
    expect(deltaPhrase(3)).toBe("proche d'une année normale (+3 %)")
    expect(deltaPhrase(null)).toBe('sans référence normale disponible')
  })
})

describe('SummaryBanner', () => {
  it('donne la réponse en une phrase, sans jargon technique', () => {
    const w = mount(SummaryBanner, {
      props: { series, yearRange: [2001, 2025], regionName: 'Gabon' },
    })
    const text = w.text()
    expect(text).toContain('En bref - Gabon')
    expect(text).toMatch(/En 2025, environ [\d\s]+ points de feu détectés par satellite/)
    expect(text).toMatch(/année normale/)
    expect(text).toMatch(/La saison des feux culmine en \p{L}+/u)
    expect(text).toContain('Données jusqu\'à décembre 2025')
    expect(text).not.toMatch(/VIIRS|MODIS|harmonis/)
  })

  it('invite à élargir la plage sans année complète', () => {
    const w = mount(SummaryBanner, {
      props: { series: series.slice(0, 5), yearRange: [2001, 2025], regionName: 'Gabon' },
    })
    expect(w.text()).toContain("Pas d'année complète")
  })
})

describe('MonthDetail - affichage par défaut', () => {
  it('annonce le dernier mois disponible et replie le détail technique', () => {
    const p = series.find((x) => x.month === '2025-12')!
    const w = mount(MonthDetail, {
      props: { point: p, rank: null, pinned: false, latest: true, view: 'after' },
    })
    expect(w.text()).toContain('Dernier mois disponible')
    expect(w.text()).toContain('points de feu détectés')
    expect(w.get('details').attributes('open')).toBeUndefined()
    expect(w.get('details').text()).toContain('VIIRS S-NPP')
  })
})
