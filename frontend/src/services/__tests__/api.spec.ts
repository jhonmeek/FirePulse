import { describe, expect, it, vi } from 'vitest'
import {
  USE_MOCKS,
  fetchAnomalies,
  fetchCalendar,
  fetchRegions,
  toSearchParams,
} from '@/services/api'

describe('toSearchParams', () => {
  it('sérialise région + période + filter_static', () => {
    expect(
      toSearchParams({
        region: 'GA',
        start: '2024-01',
        end: '2024-12',
        filter_static: true,
      }).toString(),
    ).toBe('region=GA&start=2024-01&end=2024-12&filter_static=true')
  })

  it('applique la priorité backend polygon > bbox > region', () => {
    const polygon = {
      type: 'Polygon' as const,
      coordinates: [
        [
          [10.5, -3],
          [12.5, -3],
          [12.5, -1],
          [10.5, -3],
        ],
      ],
    }
    const p = toSearchParams({ region: 'GA', bbox: [9, -2, 11, 0], polygon, filter_static: false })
    expect(p.has('region')).toBe(false)
    expect(p.has('bbox')).toBe(false)
    expect(JSON.parse(p.get('polygon')!)).toEqual(polygon)

    const b = toSearchParams({ region: 'GA', bbox: [9, -2, 11, 0], filter_static: true })
    expect(b.get('bbox')).toBe('9,-2,11,0')
    expect(b.has('region')).toBe(false)
  })
})

describe('mode mocks', () => {
  it('est actif en test (dev)', () => {
    expect(USE_MOCKS).toBe(true)
  })

  it('filtre la période comme le backend', async () => {
    const cal = await fetchCalendar({
      region: 'GA',
      start: '2024-06',
      end: '2024-09',
      filter_static: true,
    })
    expect(cal.series.map((p) => p.month)).toEqual(['2024-06', '2024-07', '2024-08', '2024-09'])
    expect(cal.period).toEqual({ start: '2024-06', end: '2024-09' })
  })

  it('bascule de série selon filter_static', async () => {
    const a = await fetchCalendar({ region: 'GA', filter_static: true })
    const b = await fetchCalendar({ region: 'GA', filter_static: false })
    expect(a.method?.name).toBe('power_law_log1p_static_masked')
    expect(b.method?.name).toBe('power_law_log1p_unfiltered')
  })

  it('renvoie une série vide (forme backend) hors GA, avec avertissement', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    const cal = await fetchCalendar({ bbox: [9, -2, 11, 0], filter_static: true })
    expect(cal.series).toEqual([])
    expect(cal.period).toEqual({ start: null, end: null })
    expect(cal.method).toBeNull()
    expect(warn).toHaveBeenCalledOnce()
    warn.mockRestore()
  })

  it('limite top_n et allège les régions sans géométrie', async () => {
    const anom = await fetchAnomalies('GA', true, 3)
    expect(anom.top_positive).toHaveLength(3)
    expect(anom.monthly_baselines).toHaveLength(12)
    const regions = await fetchRegions(false)
    expect(regions.regions.every((r) => r.geometry === null)).toBe(true)
  })
})
