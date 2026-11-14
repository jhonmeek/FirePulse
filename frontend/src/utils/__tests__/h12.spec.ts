import { describe, expect, it } from 'vitest'
import type { CalendarResponse, MethodologyResponse } from '@/types/api'
import calStatic from '@/mocks/calendar_GA_static.json'
import calAll from '@/mocks/calendar_GA_all.json'
import methStatic from '@/mocks/methodology_GA_static.json'
import { BREAKS, buildComparisonOption, inRange, snppModisRatio } from '@/utils/chart'
import { maskedSummary, rankAnomalies, seasonalBaselines } from '@/utils/anomalies'
import { benchmarkRows, conformalFactor, maeGain } from '@/utils/methodology'

const filtered = calStatic as unknown as CalendarResponse
const unfiltered = calAll as unknown as CalendarResponse
const series = filtered.series
const meth = methStatic as unknown as MethodologyResponse

type Series = {
  name: string
  data: unknown[]
  stack?: string
  markLine?: { data: { xAxis: string }[] }
}
const seriesOf = (o: ReturnType<typeof buildComparisonOption>) => o.series as Series[]

describe('buildComparisonOption', () => {
  const points = inRange(series, [2001, 2025])

  it('vue « avant » : uniquement les 3 capteurs bruts', () => {
    const names = seriesOf(buildComparisonOption(points, 'before', null)).map((s) => s.name)
    expect(names).toEqual(['MODIS brut (Terra + Aqua)', 'VIIRS S-NPP brut', 'VIIRS NOAA-20 brut'])
  })

  it('vue « après » : ajoute la bande empilée et la série harmonisée', () => {
    const s = seriesOf(buildComparisonOption(points, 'after', null))
    const band = s.filter((x) => x.stack === 'ci')
    expect(band).toHaveLength(2)
    const harmonized = s.find((x) => x.name.startsWith('Harmonisé'))!
    expect(harmonized.data).toHaveLength(points.length)
    // Bande = ci_low + (ci_high − ci_low) : reconstitue ci_high
    const i = points.findIndex((p) => p.month === '2005-08')
    const p = points[i]!
    expect((band[0]!.data[i] as number) + (band[1]!.data[i] as number)).toBeCloseTo(p.ci_high!, 6)
  })

  it('remplace null par "-" (trou dans la courbe, pas zéro)', () => {
    const s = seriesOf(buildComparisonOption(points, 'before', null))
    const snpp = s.find((x) => x.name === 'VIIRS S-NPP brut')!
    expect(snpp.data[0]).toBe('-') // 2001-01 : S-NPP pas encore lancé
  })

  it('pose les repères de rupture et le mois sélectionné', () => {
    const marks = seriesOf(buildComparisonOption(points, 'after', '2024-01'))[0]!.markLine!.data
    expect(marks.map((m) => m.xAxis)).toEqual([...BREAKS.map((b) => b.month), '2024-01'])
  })

  it('omet les repères hors de la plage affichée', () => {
    const marks = seriesOf(
      buildComparisonOption(inRange(series, [2015, 2020]), 'after', '2001-01'),
    )[0]!.markLine!.data
    expect(marks).toEqual([])
  })
})

it('snppModisRatio mesure le saut instrumental (~×4 au Gabon)', () => {
  const r = snppModisRatio(series, '2012-02', '2019-12')!
  expect(r).toBeGreaterThan(3.5)
  expect(r).toBeLessThan(4.5)
  expect(snppModisRatio(series, '2001-01', '2005-12')).toBeNull() // pas de S-NPP
})

describe('anomalies', () => {
  it('seasonalBaselines : 12 mois, pic juillet–août', () => {
    const b = seasonalBaselines(series)
    expect(b.map((x) => x.month)).toEqual([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12])
    const top2 = [...b]
      .sort((x, y) => y.median - x.median)
      .slice(0, 2)
      .map((x) => x.month)
    expect(top2.sort()).toEqual([7, 8])
  })

  it('rankAnomalies : tri décroissant / croissant, borné', () => {
    const { positive, negative } = rankAnomalies(series, 3)
    expect(positive).toHaveLength(3)
    expect(positive[0]!.month).toBe('2007-01')
    expect(positive[0]!.anomaly_percent!).toBeGreaterThanOrEqual(positive[1]!.anomaly_percent!)
    expect(negative[0]!.anomaly_percent!).toBeLessThanOrEqual(negative[1]!.anomaly_percent!)
  })

  it('maskedSummary : détections retirées par le filtre, sur la plage', () => {
    const all = maskedSummary(unfiltered, filtered, [2000, 2025])!
    expect(all.masked).toBeGreaterThan(0)
    expect(all.share).toBeGreaterThan(0.3)
    expect(all.share).toBeLessThan(0.45)
    const part = maskedSummary(unfiltered, filtered, [2020, 2020])!
    expect(part.total).toBeLessThan(all.total)
    expect(maskedSummary(null, filtered, [2000, 2025])).toBeNull()
  })
})

describe('methodology', () => {
  const run = meth.active_run!
  const rows = benchmarkRows(run.metrics.models_out_of_sample!, run.params, run.method_name)

  it('ordonne les modèles et marque un seul modèle retenu', () => {
    expect(rows.map((r) => r.key)).toEqual([
      'naive',
      'global_ratio',
      'ols_linear',
      'power_law_log1p',
      'terra_only_power_law',
    ])
    expect(rows.filter((r) => r.selected).map((r) => r.key)).toEqual(['power_law_log1p'])
  })

  it('écrit les formules avec les paramètres calibrés', () => {
    expect(rows.find((r) => r.key === 'power_law_log1p')!.formula).toMatch(
      /^V = exp\(0,94\d · ln\(M\+1\) \+ 1,65\d?\) − 1$/,
    )
  })

  it('calcule le gain de MAE du modèle retenu', () => {
    const vsNaive = maeGain(rows, 'naive')!
    const vsRatio = maeGain(rows, 'global_ratio')!
    expect(vsNaive).toBeGreaterThan(0.6)
    expect(vsRatio).toBeGreaterThan(0.1)
    expect(maeGain(rows, 'inconnu')).toBeNull()
  })

  it('convertit le quantile conforme log en facteur multiplicatif', () => {
    expect(conformalFactor(0)).toBe(1)
    expect(conformalFactor(Math.log(2))).toBeCloseTo(2)
  })
})
