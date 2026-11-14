import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import CalendarHeatmap from '@/components/CalendarHeatmap.vue'
import MonthDetail from '@/components/MonthDetail.vue'
import type { CalendarResponse } from '@/types/api'
import calStatic from '@/mocks/calendar_GA_static.json'
import calEdge from '@/mocks/calendar_edge_cases.json'
import { historicalRank } from '@/utils/calendar'

const series = (calStatic as unknown as CalendarResponse).series
const edge = (calEdge as unknown as CalendarResponse).series

function mountHeatmap(props: Partial<InstanceType<typeof CalendarHeatmap>['$props']> = {}) {
  return mount(CalendarHeatmap, {
    props: { series, yearRange: [2001, 2025], colorMode: 'value', selectedMonth: null, ...props },
    attachTo: document.body,
  })
}

describe('CalendarHeatmap', () => {
  it('rend une cellule par mois, avec années en en-têtes de ligne', () => {
    const w = mountHeatmap()
    expect(w.findAll('button[data-month]')).toHaveLength(25 * 12)
    const headers = w.findAll('[role="rowheader"]').map((h) => h.text())
    expect(headers[0]).toBe('2001')
    expect(headers[headers.length - 1]).toBe('2025')
    w.unmount()
  })

  it('n’a qu’une cellule tabulable (roving tabindex), sur le dernier mois avec données', () => {
    const w = mountHeatmap()
    const tabbable = w.findAll('button[tabindex="0"]')
    expect(tabbable).toHaveLength(1)
    expect(tabbable[0]!.attributes('data-month')).toBe('2025-12')
    w.unmount()
  })

  it('se déplace au clavier et déplace le focus', async () => {
    const w = mountHeatmap({ selectedMonth: '2024-01' })
    const grid = w.get('[role="grid"]')
    await grid.trigger('keydown', { key: 'ArrowRight' })
    expect(document.activeElement?.getAttribute('data-month')).toBe('2024-02')
    await grid.trigger('keydown', { key: 'ArrowUp' })
    expect(document.activeElement?.getAttribute('data-month')).toBe('2023-02')
    await grid.trigger('keydown', { key: 'End' })
    expect(document.activeElement?.getAttribute('data-month')).toBe('2023-12')
    await grid.trigger('keydown', { key: 'PageUp' })
    expect(document.activeElement?.getAttribute('data-month')).toBe('2001-12')
    w.unmount()
  })

  it('émet select au clic et marque la cellule sélectionnée', async () => {
    const w = mountHeatmap({ selectedMonth: '2024-08' })
    expect(w.get('[data-month="2024-08"]').attributes('aria-pressed')).toBe('true')
    await w.get('[data-month="2007-01"]').trigger('click')
    expect(w.emitted('select')).toEqual([['2007-01']])
    w.unmount()
  })

  it('décrit chaque cellule pour les lecteurs d’écran', () => {
    const w = mountHeatmap()
    expect(w.get('[data-month="2024-01"]').attributes('aria-label')).toMatch(
      /^janvier 2024 : 414 détections équivalentes VIIRS, \+\d+,\d % par rapport à la médiane/,
    )
    w.unmount()
  })

  it('hachure les mois provisoires et signale les mois sans donnée', () => {
    const w = mountHeatmap({ series: edge, yearRange: [2026, 2026] })
    const nrt = w.get('[data-month="2026-11"]')
    expect(nrt.attributes('style')).toContain('repeating-linear-gradient')
    expect(nrt.attributes('aria-label')).toContain('Temps quasi réel')
    expect(w.get('[data-month="2026-12"]').attributes('aria-label')).toBe(
      'décembre 2026 : aucune donnée',
    )
    w.unmount()
  })
})

describe('MonthDetail', () => {
  it('affiche valeur, anomalie, rang et capteurs inactifs', () => {
    const p = series.find((x) => x.month === '2005-08')!
    const w = mount(MonthDetail, {
      props: { point: p, rank: historicalRank(series, '2005-08'), pinned: true },
    })
    const text = w.text()
    expect(text).toContain('août 2005')
    expect(text).toContain('Intervalle 80 %')
    expect(text).toMatch(/plus élevé sur 25 août/)
    expect(text).toContain('MODIS Terra + Aqua reconstitué')
    expect(text).toContain('capteur non actif') // VIIRS avant 2012
  })

  it('gère la médiane nulle (écart absolu) et l’absence d’intervalle', () => {
    const p = edge.find((x) => x.month === '2026-11')!
    const w = mount(MonthDetail, {
      props: { point: { ...p, ci_low: null, ci_high: null }, rank: null, pinned: false },
    })
    expect(w.text()).toContain('écart absolu, médiane nulle')
    expect(w.text()).toContain("Intervalle d'incertitude non disponible")
    expect(w.text()).toContain('provisoire')
  })
})
