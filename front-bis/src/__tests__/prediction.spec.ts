import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import PredictionExplorer from '@/components/PredictionExplorer.vue'
import { setLocale } from '@/lib/i18n'

describe('PredictionExplorer', () => {
  it('renders the future calendar and updates the floating detail card', async () => {
    setLocale('fr', true)
    const wrapper = mount(PredictionExplorer)

    expect(wrapper.text()).toContain('Calendrier futur')
    expect(wrapper.text()).toContain('Fiche de confiance')
    expect(wrapper.text()).toContain('Projection climatologique')

    const cells = wrapper.findAll('.prediction-calendar-cell')
    expect(cells).toHaveLength(120)

    await cells[0]!.trigger('click')
    expect(wrapper.find('.prediction-detail').text()).toContain('Janvier 2026')
    expect(wrapper.find('.prediction-detail').text()).toContain('Gabon')
  })

  it('filters the map and calendar by province', async () => {
    setLocale('fr', true)
    const wrapper = mount(PredictionExplorer)
    const select = wrapper.find('select')
    await select.setValue('GA-2')

    const mapCells = wrapper.findAll('.prediction-cell')
    expect(mapCells.length).toBeGreaterThan(0)
    expect(mapCells.length).toBeLessThan(322)
    expect(wrapper.text()).toContain('Haut-Ogooué')
  })
})
