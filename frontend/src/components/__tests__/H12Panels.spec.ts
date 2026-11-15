import { beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h } from 'vue'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import AnomaliesPanel from '@/components/AnomaliesPanel.vue'
import ComparisonChart from '@/components/ComparisonChart.vue'
import ControlBar from '@/components/ControlBar.vue'
import MethodologyPanel from '@/components/MethodologyPanel.vue'
import { useFiltersStore } from '@/stores/filters'
import type { CalendarResponse } from '@/types/api'
import calStatic from '@/mocks/calendar_GA_static.json'

const series = (calStatic as unknown as CalendarResponse).series

/** ECharts a besoin d'un canvas (absent de jsdom) : on remplace VChart par un double. */
/**
 * Double d'ECharts : expose `getOption()` (fenêtre de zoom courante) et émet `datazoom`
 * quand on simule un zoom, comme le vrai composant.
 */
let stubZoom: { startValue: number; endValue: number } | null = null
const VChartStub = defineComponent({
  props: { option: Object },
  emits: ['click', 'datazoom'],
  setup(props, { emit, expose }) {
    expose({ getOption: () => ({ dataZoom: [stubZoom ?? {}] }) })
    return () =>
      h('div', {
        'data-testid': 'chart',
        'data-zoom': JSON.stringify(
          (props.option as { dataZoom?: { startValue?: string }[] })?.dataZoom?.[0]?.startValue ??
            null,
        ),
        onClick: () => emit('click', { name: '2010-08' }),
        onDblclick: () => emit('datazoom'),
      })
  },
})

describe('ComparisonChart', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    stubZoom = null
  })
  const mountChart = () =>
    mount(ComparisonChart, {
      props: { series, yearRange: [2001, 2025], selectedMonth: null },
      // Nom déclaré par vue-echarts 8 : « Echarts ».
      global: { stubs: { Echarts: VChartStub } },
    })

  it('affiche le saut instrumental mesuré et bascule avant / après', async () => {
    const w = mountChart()
    expect(w.text()).toMatch(/VIIRS S-NPP détecte ×\d,\d plus que MODIS/)
    expect(w.text()).toContain('intervalle conforme 80 %')
    await w.get('input[value="before"]').setValue(true)
    expect(w.text()).toContain('rupture')
    expect(useFiltersStore().harmonizationView).toBe('before')
  })

  it('conserve le zoom en basculant avant / après (revue UX)', async () => {
    const w = mountChart()
    // Zoom simulé sur les index 108..179 de 2001-01..2025-12 = 2010-01..2015-12
    stubZoom = { startValue: 108, endValue: 179 }
    await w.get('[data-testid="chart"]').trigger('dblclick')
    expect(useFiltersStore().chartWindow).toEqual({ start: '2010-01', end: '2015-12' })
    expect(w.get('[data-testid="chart"]').attributes('data-zoom')).toBe('"2010-01"')
    await w.get('input[value="before"]').setValue(true)
    expect(w.get('[data-testid="chart"]').attributes('data-zoom')).toBe('"2010-01"')
    expect(w.text()).toContain('Zoom conservé : janvier 2010 - décembre 2015')
    await w.get('input[value="after"]').setValue(true)
    expect(w.get('[data-testid="chart"]').attributes('data-zoom')).toBe('"2010-01"')
    await w.get('button.btn-ghost').trigger('click')
    expect(useFiltersStore().chartWindow).toBeNull()
  })

  it('ramène le zoom dans une plage d’années réduite', async () => {
    useFiltersStore().chartWindow = { start: '2010-01', end: '2015-12' }
    const w = mount(ComparisonChart, {
      props: { series, yearRange: [2014, 2020], selectedMonth: null },
      global: { stubs: { Echarts: VChartStub } },
    })
    expect(w.get('[data-testid="chart"]').attributes('data-zoom')).toBe('"2014-01"')
  })

  it('émet select au clic sur un mois du graphe', async () => {
    const w = mountChart()
    await w.get('[data-testid="chart"]').trigger('click')
    expect(w.emitted('select')).toEqual([['2010-08']])
  })
})

describe('AnomaliesPanel', () => {
  it('liste les mois atypiques de la plage et émet select', async () => {
    const w = mount(AnomaliesPanel, {
      props: { series, yearRange: [2001, 2025], selectedMonth: '2024-08' },
    })
    expect(w.findAll('ol[aria-label="Médiane mensuelle de référence"] li')).toHaveLength(12)
    const first = w.findAll('button')[0]!
    expect(first.text()).toMatch(/janvier 2007\s*\+\d/i)
    await first.trigger('click')
    expect(w.emitted('select')).toEqual([['2007-01']])
    expect(w.text()).toContain('Pointillés : août 2024')
  })

  it('respecte la plage d’années pour le classement', () => {
    const w = mount(AnomaliesPanel, {
      props: { series, yearRange: [2015, 2016], selectedMonth: null },
    })
    const months = w.findAll('button').map((b) => b.text())
    expect(months.every((t) => /201[56]/.test(t))).toBe(true)
  })
})

describe('ControlBar', () => {
  it('affiche le compteur de détections retirées, sa période et sa définition', async () => {
    setActivePinia(createPinia())
    const w = mount(ControlBar, {
      props: {
        regions: [],
        availableYears: [2024, 2025],
        masked: { total: 1000, masked: 384, share: 0.384 },
      },
    })
    expect(w.get('#filter-static-count').text()).toBe(
      '384 détections retirées (38,4 % du total, 2001–2025)',
    )
    expect(w.get('#filter-static-help').text()).toContain(
      'type FIRMS ≠ 0 ou site industriel persistant',
    )
    await w.get('input[type="checkbox"]').setValue(false)
    expect(w.get('#filter-static-count').text()).toBe(
      '384 détections que le filtre retirerait (38,4 % du total, 2001–2025)',
    )
  })

  it('n’affiche plus « masquées » (terme ambigu relevé en revue M1)', () => {
    setActivePinia(createPinia())
    const w = mount(ControlBar, {
      props: { regions: [], availableYears: [], masked: { total: 10, masked: 4, share: 0.4 } },
    })
    expect(w.text()).not.toMatch(/masquées/)
  })
})

describe('MethodologyPanel', () => {
  it('rend le benchmark hors échantillon depuis /methodology/', async () => {
    const w = mount(MethodologyPanel, {
      props: { region: 'GA', filterStatic: true, customArea: false },
    })
    // Le mock JSON est importé dynamiquement : plusieurs ticks avant le rendu.
    await vi.waitFor(() => expect(w.text()).toContain('Évaluation hors échantillon'))
    const text = w.text()
    expect(text).toContain('protocole en revue scientifique (M1)')
    expect(text).toMatch(/erreur moyenne inférieure de \d+ %/)
    // Réserves de la revue M1 (PR #9) affichées tant que le protocole n'est pas validé.
    expect(text).toContain('calibré sur les résidus de la période test')
    expect(text).toContain('même fenêtre test')
    expect(text).toContain('test comprise')
    expect(text).not.toMatch(/validation hors échantillon|validé/i)
    expect(w.findAll('tbody tr')).toHaveLength(5)
    expect(w.get('tbody tr.bg-orange-50').text()).toContain('Loi de puissance log1p')
    expect(text).toContain('183 cellules')
  })

  it('signale la calibration nationale sur zone dessinée', async () => {
    const w = mount(MethodologyPanel, {
      props: { region: 'GA', filterStatic: true, customArea: true },
    })
    await vi.waitFor(() => expect(w.text()).toContain('la courbe nationale (Gabon) est appliquée'))
  })
})
