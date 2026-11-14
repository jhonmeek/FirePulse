import { describe, expect, it } from 'vitest'
import type { CalendarPoint, CalendarResponse } from '@/types/api'
import calStatic from '@/mocks/calendar_GA_static.json'
import {
  ANOMALY_CLAMP,
  buildMatrix,
  cellColor,
  formatAnomaly,
  historicalRank,
  legendStops,
  monthLabel,
  valueMax,
} from '@/utils/calendar'

const series = (calStatic as unknown as CalendarResponse).series

const rgb = (c: string) => c.match(/\d+/g)!.map(Number) as [number, number, number]

function point(overrides: Partial<CalendarPoint>): CalendarPoint {
  return {
    month: '2024-01',
    modis_count: null,
    modis_terra_count: null,
    modis_aqua_count: null,
    viirs_snpp_count: null,
    viirs_noaa20_count: null,
    harmonized_value: 100,
    ci_low: 100,
    ci_high: 100,
    baseline_median: 100,
    baseline_iqr: null,
    anomaly_percent: 0,
    anomaly_absolute: 0,
    sensor_regime: 'viirs_snpp_observed',
    coverage_status: 'complete_sp',
    uncertainty_note: '',
    ...overrides,
  }
}

describe('buildMatrix', () => {
  it('produit années × 12 mois, avec null pour les mois absents', () => {
    const rows = buildMatrix(series, 2000, 2001)
    expect(rows).toHaveLength(2)
    expect(rows.every((r) => r.length === 12)).toBe(true)
    expect(rows[0]![0]!.point).toBeNull() // 2000-01 : avant MODIS
    expect(rows[0]![10]!.point?.month).toBe('2000-11')
    expect(rows[1]![7]!.month).toBe('2001-08')
  })
})

describe('formatAnomaly', () => {
  it('affiche le pourcentage signé en français', () => {
    expect(formatAnomaly({ anomaly_percent: 298.7, anomaly_absolute: 310 })).toBe('+298,7 %')
    expect(formatAnomaly({ anomaly_percent: -42.25, anomaly_absolute: -5 })).toBe('−42,3 %')
  })

  it('bascule sur l’écart absolu quand la médiane est nulle', () => {
    expect(formatAnomaly({ anomaly_percent: null, anomaly_absolute: 30 })).toMatch(
      /^\+30 \(écart absolu/,
    )
    expect(formatAnomaly({ anomaly_percent: null, anomaly_absolute: null })).toBe('—')
  })
})

describe('cellColor', () => {
  it('orange au-dessus de la médiane, violet en dessous (convention de la légende)', () => {
    const [r1, , b1] = rgb(cellColor(point({ anomaly_percent: 120 }), 'anomaly', 1)!)
    const [r2, , b2] = rgb(cellColor(point({ anomaly_percent: -80 }), 'anomaly', 1)!)
    expect(r1).toBeGreaterThan(b1)
    expect(b2).toBeGreaterThan(r2)
  })

  it('borne l’anomalie à ±ANOMALY_CLAMP', () => {
    expect(cellColor(point({ anomaly_percent: 900 }), 'anomaly', 1)).toBe(
      cellColor(point({ anomaly_percent: ANOMALY_CLAMP }), 'anomaly', 1),
    )
  })

  it('renvoie null sans valeur harmonisée ou sans anomalie en %', () => {
    expect(cellColor(null, 'value', 10)).toBeNull()
    expect(cellColor(point({ harmonized_value: null }), 'value', 10)).toBeNull()
    expect(cellColor(point({ anomaly_percent: null }), 'anomaly', 10)).toBeNull()
  })

  it('assombrit les valeurs élevées en mode intensité', () => {
    const lum = (c: string) => rgb(c).reduce((a, b) => a + b, 0)
    const low = cellColor(point({ harmonized_value: 50 }), 'value', 5000)!
    const high = cellColor(point({ harmonized_value: 5000 }), 'value', 5000)!
    expect(lum(high)).toBeLessThan(lum(low))
  })
})

describe('legendStops', () => {
  it('couvre 0 → max en intensité et −clamp → +clamp en anomalie', () => {
    const v = legendStops('value', 5000)
    expect(v[0]!.label).toBe('0')
    // fr-FR sépare les milliers par une espace fine insécable (U+202F).
    expect(v[v.length - 1]!.label).toBe('5 000')
    const a = legendStops('anomaly', 0)
    expect(a[0]!.label).toBe('≤ −150 %')
    expect(a[a.length - 1]!.label).toBe('≥ +150 %')
  })
})

describe('historicalRank', () => {
  it('classe le mois parmi le même mois calendaire 2001–2025', () => {
    expect(historicalRank(series, '2007-01')).toEqual({ rank: 1, total: 25 })
    expect(historicalRank(series, '2024-01')).toEqual({ rank: 2, total: 25 })
  })

  it('renvoie null hors période de référence ou mois inconnu', () => {
    expect(historicalRank(series, '2000-11')).toBeNull()
    expect(historicalRank(series, '1999-01')).toBeNull()
  })
})

it('monthLabel et valueMax', () => {
  expect(monthLabel('2024-08')).toBe('août 2024')
  expect(monthLabel('2024-08', false)).toBe('août 2024')
  expect(valueMax(series)).toBeGreaterThan(3000)
})
