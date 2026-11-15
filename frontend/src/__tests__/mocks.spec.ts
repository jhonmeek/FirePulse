import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import type {
  AnomaliesResponse,
  CalendarResponse,
  CoverageResponse,
  MethodologyResponse,
  RegionsResponse,
  SensorRegime,
} from '@/types/api'
import { CONTRACT_VERSION } from '@/types/api'
import calStatic from '@/mocks/calendar_GA_static.json'
import calAll from '@/mocks/calendar_GA_all.json'
import calEdge from '@/mocks/calendar_edge_cases.json'
import anomStatic from '@/mocks/anomalies_GA_static.json'
import methStatic from '@/mocks/methodology_GA_static.json'
import regionsMock from '@/mocks/regions.json'
import coverageMock from '@/mocks/coverage.json'

/** Contrat source de vérité, maintenu par M2 (racine vitest = frontend/). */
const contract = JSON.parse(
  readFileSync(resolve(process.cwd(), '../docs/api-contract.json'), 'utf-8'),
)
const ep = contract.endpoints
const example = (path: string) => ep[`GET /api/v1/${path}/`].response_example
const keys = (o: object) => Object.keys(o).sort()

const cast = <T>(x: unknown) => x as T
const calendars = {
  static: cast<CalendarResponse>(calStatic),
  all: cast<CalendarResponse>(calAll),
  edge: cast<CalendarResponse>(calEdge),
}

it('types/api.ts suit la version du contrat', () => {
  expect(CONTRACT_VERSION).toBe(contract.contract_version)
})

describe('formes de réponse identiques au contrat', () => {
  it('calendar', () => {
    const ex = example('calendar')
    for (const cal of Object.values(calendars)) {
      expect(keys(cal)).toEqual(keys(ex))
      expect(keys(cal.region)).toEqual(keys(ex.region))
      expect(keys(cal.method!)).toEqual(keys(ex.method))
      for (const p of cal.series) expect(keys(p)).toEqual(keys(ex.series[0]))
    }
  })

  it('regions, coverage, anomalies, methodology', () => {
    const regions = cast<RegionsResponse>(regionsMock)
    expect(keys(regions.regions[0]!)).toEqual(keys(example('regions').regions[0]))

    const coverage = cast<CoverageResponse>(coverageMock)
    expect(keys(coverage)).toEqual(keys(example('coverage')))
    expect(keys(coverage.sensors[0]!)).toEqual(keys(example('coverage').sensors[0]))

    const anom = cast<AnomaliesResponse>(anomStatic)
    const exA = example('anomalies')
    expect(keys(anom)).toEqual(keys(exA))
    expect(keys(anom.monthly_baselines[0]!)).toEqual(keys(exA.monthly_baselines[0]))
    expect(keys(anom.top_positive[0]!)).toEqual(keys(exA.top_positive[0]))

    const meth = cast<MethodologyResponse>(methStatic)
    const exM = example('methodology')
    expect(keys(meth)).toEqual(keys(exM))
    expect(keys(meth.active_run!)).toEqual(keys(exM.active_run))
    expect(keys(meth.active_run!.params)).toEqual(keys(exM.active_run.params))
    expect(keys(meth.active_run!.metrics.models_out_of_sample!)).toEqual(
      keys(exM.active_run.metrics.models_out_of_sample),
    )
  })

  it('n’utilise que les valeurs d’énumération du contrat', () => {
    for (const cal of Object.values(calendars)) {
      for (const p of cal.series) {
        expect(contract.enums.sensor_regime).toContain(p.sensor_regime)
        expect(contract.enums.coverage_status).toContain(p.coverage_status)
      }
    }
    for (const s of cast<CoverageResponse>(coverageMock).sensors) {
      expect(contract.enums.source).toContain(s.source)
    }
  })
})

function expectedRegime(month: string): SensorRegime {
  if (month < '2001-01') return 'partial_year'
  if (month < '2002-07') return 'modis_terra_only'
  if (month < '2012-02') return 'modis_terra_aqua'
  return 'viirs_snpp_observed'
}

describe.each(Object.entries(calendars))('mock calendrier %s', (name, cal) => {
  it('a des mois uniques et triés, cohérents avec period', () => {
    const months = cal.series.map((p) => p.month)
    expect(months).toEqual([...new Set(months)].sort())
    expect(cal.period.start).toBe(months[0])
    expect(cal.period.end).toBe(months[months.length - 1])
  })

  it('respecte ci_low ≤ valeur ≤ ci_high', () => {
    const bad = cal.series.filter(
      (p) =>
        p.harmonized_value !== null &&
        !(p.ci_low! <= p.harmonized_value && p.harmonized_value <= p.ci_high!),
    )
    expect(bad.map((p) => p.month)).toEqual([])
  })

  it('calcule les anomalies comme le backend (jamais de division par zéro)', () => {
    const incoherent = cal.series
      .filter((p) => p.harmonized_value !== null && p.baseline_median !== null)
      .filter((p) => {
        const h = p.harmonized_value!
        const b = p.baseline_median!
        const absOk = Math.abs(p.anomaly_absolute! - (h - b)) < 0.02
        const pctOk =
          b > 0
            ? Math.abs(p.anomaly_percent! - (100 * (h - b)) / b) < 0.02
            : p.anomaly_percent === null
        return !(absOk && pctOk)
      })
      .map((p) => p.month)
    expect(incoherent).toEqual([])
  })

  if (name === 'edge') return

  it('suit les régimes capteurs du backend', () => {
    const wrong = cal.series.filter((p) => p.sensor_regime !== expectedRegime(p.month))
    expect(wrong.map((p) => p.month)).toEqual([])
  })

  it('distingue capteur absent (null) et zéro détection', () => {
    for (const p of cal.series) {
      expect(p.modis_aqua_count === null).toBe(p.month < '2002-07')
      expect(p.viirs_snpp_count === null).toBe(p.month < '2012-01')
      expect(p.viirs_noaa20_count === null).toBe(p.month < '2018-04')
    }
  })

  it('MODIS = Terra + Aqua', () => {
    const bad = cal.series.filter(
      (p) => p.modis_count !== (p.modis_terra_count ?? 0) + (p.modis_aqua_count ?? 0),
    )
    expect(bad.map((p) => p.month)).toEqual([])
  })

  it('utilise la valeur S-NPP observée à partir de 2012-02', () => {
    const observed = cal.series.filter((p) => p.sensor_regime === 'viirs_snpp_observed')
    expect(observed.length).toBeGreaterThan(100)
    expect(observed.every((p) => p.harmonized_value === p.viirs_snpp_count)).toBe(true)
    expect(observed.every((p) => p.ci_low === p.ci_high)).toBe(true)
  })
})

it('reproduit l’exemple 2024-08 du contrat (comptages bruts identiques)', () => {
  const ex = example('calendar').series[0]
  const p = calendars.static.series.find((x) => x.month === ex.month)!
  const rawKeys = [
    'modis_count',
    'modis_terra_count',
    'modis_aqua_count',
    'viirs_snpp_count',
    'viirs_noaa20_count',
  ] as const
  const pick = (o: Record<string, unknown>) => Object.fromEntries(rawKeys.map((k) => [k, o[k]]))
  expect(pick(p as unknown as Record<string, unknown>)).toEqual(pick(ex))
  // Médiane : écart < 0,1 % (quelques points en bordure de frontière / de cellule).
  expect(Math.abs(p.baseline_median! - ex.baseline_median) / ex.baseline_median).toBeLessThan(0.001)
})

it('le filtre torchères réduit les comptages bruts', () => {
  const sum = (c: CalendarResponse) => c.series.reduce((s, p) => s + (p.viirs_snpp_count ?? 0), 0)
  expect(sum(calendars.static)).toBeLessThan(sum(calendars.all))
  expect(calendars.static.region.filter_static).toBe(true)
  expect(calendars.all.region.filter_static).toBe(false)
})

it('couvre les cas limites UI (NRT, pont NOAA-20, médiane nulle, sans donnée)', () => {
  const s = calendars.edge.series
  expect(s.some((p) => p.coverage_status === 'nrt_only')).toBe(true)
  expect(s.some((p) => p.coverage_status === 'mixed_sp_nrt')).toBe(true)
  expect(s.some((p) => p.sensor_regime === 'viirs_noaa20_bridge')).toBe(true)
  expect(s.some((p) => p.baseline_median === 0 && p.anomaly_percent === null)).toBe(true)
  expect(s.some((p) => p.sensor_regime === 'missing' && p.harmonized_value === null)).toBe(true)
})

it('expose GA et les 9 provinces', () => {
  const codes = cast<RegionsResponse>(regionsMock).regions.map((r) => r.code)
  expect(codes).toEqual(['GA', ...Array.from({ length: 9 }, (_, i) => `GA-${i + 1}`)])
})
