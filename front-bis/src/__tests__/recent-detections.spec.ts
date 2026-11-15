import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import RecentDetections from '@/components/RecentDetections.vue'

const fetchRecent = vi.hoisted(() => vi.fn())
vi.mock('@/lib/api', () => ({ USE_MOCKS: false, fetchRecentUnknownDetections: fetchRecent }))

const mounted: Array<ReturnType<typeof mount>> = []
beforeEach(() => fetchRecent.mockReset())
afterEach(() => {
  mounted.splice(0).forEach((wrapper) => wrapper.unmount())
})

function show() {
  const wrapper = mount(RecentDetections)
  mounted.push(wrapper)
  return wrapper
}

describe('recent NRT detections panel', () => {
  it('shows provenance, acquisition time and unknown type without claiming a wildfire', async () => {
    fetchRecent.mockResolvedValue({
      features: [{
        type: 'Feature', geometry: { type: 'Point', coordinates: [10.5, 0.5] },
        properties: { id: 7, source: 'viirs-noaa20', satellite: 'N20', acquired_at: new Date().toISOString(), frp: 3.5, hotspot_type: null, processing_level: 'NRT', product_version: '2.0NRT' },
      }],
    })
    const wrapper = show()
    await flushPromises()
    expect(fetchRecent).toHaveBeenCalledWith(2, 200)
    expect(wrapper.text()).toContain('NASA FIRMS NRT')
    expect(wrapper.text()).toContain('N20')
    expect(wrapper.text()).toContain('FRP 3.5 MW')
    expect(wrapper.text()).toContain('UTC')
    expect(wrapper.text()).toMatch(/inconnu|unknown/)
  })

  it('distinguishes an empty response from verified absence of fire', async () => {
    fetchRecent.mockResolvedValue({ features: [] })
    const wrapper = show()
    await flushPromises()
    expect(wrapper.text()).toMatch(/Aucun point reçu|No points received/)
    expect(wrapper.text()).toMatch(/couverture complète|complete coverage/)
  })

  it('shows API failure and lets the user retry', async () => {
    fetchRecent.mockRejectedValueOnce(new Error('offline')).mockResolvedValueOnce({ features: [] })
    const wrapper = show()
    await flushPromises()
    expect(wrapper.text()).toMatch(/API indisponible|API unavailable/)
    await wrapper.find('button').trigger('click')
    await flushPromises()
    expect(fetchRecent).toHaveBeenCalledTimes(2)
    expect(wrapper.text()).toMatch(/Aucun point reçu|No points received/)
  })
})
