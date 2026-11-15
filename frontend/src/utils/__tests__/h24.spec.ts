import { describe, expect, it } from 'vitest'
import type { CalendarPoint, GridCellSummaryProps } from '@/types/api'
import {
  SERIES_CSV_COLUMNS,
  cellPolygon,
  exportSeriesUrl,
  fetchHotspots,
  seriesToCsv,
} from '@/services/api'
import {
  bboxFromCorners,
  bboxPolygon,
  defaultMetric,
  gridCellSummary,
  gridColorExpression,
  gridStops,
  maxMetric,
  metricCoversRange,
} from '@/utils/map'

describe('utilitaires carte', () => {
  it('normalise un rectangle dessiné dans n’importe quel sens, arrondi à 0,01°', () => {
    expect(bboxFromCorners({ lng: 12.537, lat: -1.004 }, { lng: 10.501, lat: -2.996 })).toEqual([
      10.5, -3, 12.54, -1,
    ])
  })

  it('refuse une zone trop petite (clic sans glisser)', () => {
    expect(bboxFromCorners({ lng: 10, lat: 0 }, { lng: 10.01, lat: 0.01 })).toBeNull()
  })

  it('ferme le polygone de la bbox', () => {
    const ring = bboxPolygon([1, 2, 3, 4]).coordinates[0]!
    expect(ring[0]).toEqual(ring[ring.length - 1])
    expect(ring).toHaveLength(5)
  })

  it('choisit MODIS avant 2012 et signale une couverture partielle', () => {
    expect(defaultMetric([2001, 2010])).toBe('modis')
    expect(defaultMetric([2001, 2025])).toBe('snpp')
    expect(metricCoversRange('snpp', [2001, 2025])).toBe(false)
    expect(metricCoversRange('snpp', [2012, 2025])).toBe(true)
  })

  it('partage l’échelle racine carrée du calendrier (paliers croissants, 0 → max)', () => {
    const stops = gridStops(3446)
    expect(stops[0]!.value).toBe(0)
    expect(stops[stops.length - 1]!.value).toBeCloseTo(3446)
    expect(stops.every((s, i) => i === 0 || s.value > stops[i - 1]!.value)).toBe(true)
    const expr = gridColorExpression('snpp', 3446)
    expect(expr.slice(0, 3)).toEqual(['interpolate', ['linear'], ['get', 'viirs_snpp_count']])
  })

  it('résume une cellule en français', () => {
    const p: GridCellSummaryProps = {
      layer: 'grid_cell_summary',
      cell_id: '-2.00_14.00',
      months_count: 205,
      modis_count: 1576,
      viirs_snpp_count: 3446,
      viirs_noaa20_count: 1845,
      frp_sum_modis: 0,
      frp_sum_snpp: 0,
      frp_sum_noaa20: 0,
    }
    expect(gridCellSummary(p)[0]).toBe('Cellule -2,00° ; 14,00° (0,25°)')
    expect(maxMetric([{ properties: p }], 'snpp')).toBe(3446)
  })

  it('reconstruit le polygone d’une cellule depuis son identifiant', () => {
    expect(cellPolygon('-2.00_14.00', 0.25).coordinates[0]![2]).toEqual([14.25, -1.75])
  })
})

describe('fetchHotspots (mocks)', () => {
  it('Gabon 2001–2025 : 352 cellules et 183 sites statiques, comme l’API', async () => {
    const r = await fetchHotspots({
      region: 'GA',
      start: '2001-01',
      end: '2025-12',
      filter_static: true,
    })
    const layers = r.features.map((f) => f.properties.layer)
    expect(layers.filter((l) => l === 'grid_cell_summary')).toHaveLength(352)
    expect(layers.filter((l) => l === 'static_flare_mask')).toHaveLength(183)
    expect(r.agg).toBe('cell')
  })

  it('bbox 10,5/-3/12,5/-1 sur 2020–2024 : 79 cellules et 27 sites, comme l’API', async () => {
    const r = await fetchHotspots({
      bbox: [10.5, -3, 12.5, -1],
      start: '2020-01',
      end: '2024-12',
      filter_static: true,
    })
    const grid = r.features.filter((f) => f.properties.layer === 'grid_cell_summary')
    const statics = r.features.filter((f) => f.properties.layer === 'static_flare_mask')
    expect(grid).toHaveLength(79)
    expect(statics).toHaveLength(27)
    // API : 7 625 détections S-NPP (écart masque connu ≤ 1 %).
    const snpp = grid.reduce(
      (s, f) => s + (f.properties as GridCellSummaryProps).viirs_snpp_count,
      0,
    )
    expect(Math.abs(snpp - 7625) / 7625).toBeLessThan(0.01)
  })

  it('resomme uniquement les années de la plage', async () => {
    const all = await fetchHotspots({
      region: 'GA',
      start: '2001-01',
      end: '2025-12',
      filter_static: false,
    })
    const one = await fetchHotspots({
      region: 'GA',
      start: '2024-01',
      end: '2024-12',
      filter_static: false,
    })
    const total = (r: typeof all) =>
      r.features.reduce(
        (s, f) => s + (f.properties.layer === 'grid_cell_summary' ? f.properties.months_count : 0),
        0,
      )
    expect(total(one)).toBeLessThan(total(all))
    expect(
      one.features.every(
        (f) => f.properties.layer !== 'grid_cell_summary' || f.properties.months_count <= 12,
      ),
    ).toBe(true)
  })
})

describe('export CSV', () => {
  const point = (o: Partial<CalendarPoint>): CalendarPoint => ({
    month: '2024-01',
    modis_count: 106,
    modis_terra_count: 30,
    modis_aqua_count: 76,
    viirs_snpp_count: 414,
    viirs_noaa20_count: 385,
    harmonized_value: 414,
    ci_low: 414,
    ci_high: 414,
    baseline_median: 103.83,
    baseline_iqr: [76, 192.5],
    anomaly_percent: 298.73,
    anomaly_absolute: 310.17,
    sensor_regime: 'viirs_snpp_observed',
    coverage_status: 'complete_sp',
    uncertainty_note: '',
    ...o,
  })

  it('reproduit le format de /export/ (ligne réelle de l’API, décimaux Python)', () => {
    const [header, line] = seriesToCsv([point({})], 'GA', true, 'v2.0')
      .trim()
      .split('\n')
    expect(header).toBe(SERIES_CSV_COLUMNS.join(','))
    // Ligne copiée de GET /api/v1/export/?region=GA&start=2024-01&end=2024-01
    expect(line).toBe(
      'GA,2024-01,True,106,414,385,414.0,414.0,414.0,103.83,298.73,310.17,viirs_snpp_observed,complete_sp,v2.0',
    )
  })

  it('rend null par une cellule vide', () => {
    const line = seriesToCsv(
      [point({ ci_low: null, anomaly_percent: null, viirs_snpp_count: null })],
      'CUSTOM_BBOX',
      false,
      'v2.0',
    )
      .trim()
      .split('\n')[1]!
    expect(line.split(',')).toEqual([
      'CUSTOM_BBOX',
      '2024-01',
      'False',
      '106',
      '',
      '385',
      '414.0',
      '',
      '414.0',
      '103.83',
      '',
      '310.17',
      'viirs_snpp_observed',
      'complete_sp',
      'v2.0',
    ])
  })

  it('construit l’URL d’export avec zone, période et dataset=series', () => {
    const url = exportSeriesUrl({
      bbox: [10.5, -3, 12.5, -1],
      start: '2020-01',
      end: '2024-12',
      filter_static: true,
    })
    expect(url).toBe(
      '/api/v1/export/?bbox=10.5%2C-3%2C12.5%2C-1&start=2020-01&end=2024-12&filter_static=true&dataset=series',
    )
  })
})
