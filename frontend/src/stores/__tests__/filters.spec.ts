import { beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useFiltersStore } from '@/stores/filters'

describe('store filters', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('démarre sur le Gabon 2001–2025, torchères exclues', () => {
    const f = useFiltersStore()
    expect(f.query).toEqual({ region: 'GA', start: '2001-01', end: '2025-12', filter_static: true })
  })

  it('une bbox remplace la région, et sélectionner une région efface la bbox', () => {
    const f = useFiltersStore()
    f.selectBBox([9, -2, 11, 0])
    expect(f.query.bbox).toEqual([9, -2, 11, 0])
    expect(f.query.region).toBeUndefined()
    f.selectRegion('GA-3')
    expect(f.bbox).toBeNull()
    expect(f.query.region).toBe('GA-3')
  })

  it('rejette une bbox inversée ou hors WGS84', () => {
    const f = useFiltersStore()
    expect(() => f.selectBBox([11, -2, 9, 0])).toThrow(RangeError)
    expect(() => f.selectBBox([9, -2, 200, 0])).toThrow(RangeError)
    expect(f.bbox).toBeNull()
  })

  it('borne et ordonne la plage d’années, et la répercute sur start/end', () => {
    const f = useFiltersStore()
    f.setYearRange(2030, 1990)
    expect(f.yearRange).toEqual([2000, 2026])
    f.setYearRange(2012, 2014)
    expect(f.query.start).toBe('2012-01')
    expect(f.query.end).toBe('2014-12')
  })
})
