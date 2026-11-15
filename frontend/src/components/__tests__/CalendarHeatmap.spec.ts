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
    props: {
      series,
      yearRange: [2001, 2025],
      colorMode: 'value',
      selectedMonth: null,
      view: 'after',
      ...props,
    },
    attachTo: document.body,
  })
}

describe('CalendarHeatmap', () => {
  it('rend une cellule par mois, avec années en en-têtes de ligne', () => {
    const w = mountHeatmap()
    expect(w.findAll('button[data-month]')).toHaveLength(25 * 12)
    const headers = w.findAll('[role="rowheader"]').map((h) => h.text())
    expect(headers[0]).toBe('2001')
    expect(headers[headers.length - 2]).toBe('2025')
    // Série de comparaison : la ligne de référence vient après les années.
    expect(headers[headers.length - 1]).toBe('Normale')
    w.unmount()
  })

  it('ajoute la ligne Normale (12 mois, non tabulable) et des années en texte simple', () => {
    const w = mountHeatmap()
    const rows = w.findAll('[role="row"]')
    const baseline = rows[rows.length - 1]!
    const cells = baseline.findAll('[role="gridcell"]')
    expect(cells).toHaveLength(12)
    expect(cells[7]!.attributes('aria-label')).toMatch(
      /^Mois normal de août \(médiane 2001-2025, données corrigées\) : [\d\s]+ points de feu/,
    )
    expect(baseline.findAll('button')).toHaveLength(0)
    // Plus de raccourci « comparer » sur les années (comparateur supprimé).
    expect(w.findAll('[role="rowheader"] button')).toHaveLength(0)
    w.unmount()
  })

  it('vue Avant : brut du capteur d’époque, repère 2012, médiane conservée', () => {
    const w = mountHeatmap({ view: 'before', colorMode: 'anomaly' })
    expect(w.get('[data-month="2005-08"]').attributes('aria-label')).toMatch(
      /^août 2005 : [\d\s]+ points de feu bruts MODIS \(Terra \+ Aqua\), [\d\s]+ après correction/,
    )
    expect(w.get('[data-month="2012-01"]').attributes('aria-label')).toContain('bruts MODIS')
    expect(w.get('[data-month="2013-08"]').attributes('aria-label')).toContain('bruts VIIRS S-NPP')
    expect(w.get('[data-month="2012-02"]').classes().join(' ')).toContain(
      'shadow-[inset_3px_0_0_#1c1917]',
    )
    expect(w.text()).toContain('Changement de satellite : MODIS → VIIRS (février 2012)')
    // Mode anomalie ignoré sur du brut : légende d'intensité.
    expect(w.text()).toContain('Points de feu (données brutes)')
    expect(w.text()).not.toContain('Par rapport à la normale')
    const rows = w.findAll('[role="row"]')
    expect(rows[rows.length - 1]!.findAll('[role="gridcell"]')).toHaveLength(12)
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
      /^janvier 2024 : 414 points de feu, \+\d+,\d % par rapport à la normale/,
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
      props: { point: p, rank: historicalRank(series, '2005-08'), pinned: true, view: 'after' },
    })
    const text = w.text()
    expect(text).toContain('août 2005')
    expect(text).toContain('Intervalle 80 %')
    expect(text).toMatch(/août le plus actif sur 25/)
    expect(text).toContain('MODIS Terra + Aqua reconstitué')
    expect(text).toContain('capteur non actif') // VIIRS avant 2012
  })

  it('gère la médiane nulle (écart absolu) et l’absence d’intervalle', () => {
    const p = edge.find((x) => x.month === '2026-11')!
    const w = mount(MonthDetail, {
      props: {
        point: { ...p, ci_low: null, ci_high: null },
        rank: null,
        pinned: false,
        view: 'after',
      },
    })
    expect(w.text()).toContain('écart absolu, médiane nulle')
    expect(w.text()).toContain("Intervalle d'incertitude non disponible")
    expect(w.text()).toContain('provisoire')
  })
})

describe('MonthDetail - vue Avant', () => {
  it('met la valeur brute du capteur d’époque au premier plan', () => {
    const p = series.find((x) => x.month === '2005-08')!
    const w = mount(MonthDetail, { props: { point: p, rank: null, pinned: true, view: 'before' } })
    expect(w.text()).toContain('points de feu bruts MODIS (Terra + Aqua)')
    expect(w.text()).toContain('Données corrigées')
    expect(w.get('.text-3xl').text()).toBe(
      String(p.modis_count).replace(/\B(?=(\d{3})+(?!\d))/g, ' '),
    )
  })
})
