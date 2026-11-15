import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import CalendarHeatmap from '@/components/CalendarHeatmap.vue'
import FlareSplit from '@/components/FlareSplit.vue'
import ValidationProof from '@/components/ValidationProof.vue'
import calendarAllJson from '@/data/calendar-all.json'
import calendarStaticJson from '@/data/calendar-static.json'
import coverageJson from '@/data/coverage.json'
import healthJson from '@/data/health.json'
import methodologyJson from '@/data/methodology.json'
import regionsJson from '@/data/regions.json'
import {
  allSeries,
  buildSeriesCsvFallback,
  composition,
  computeExcludedSeries,
  flareSeries,
  monthlyMedians,
  staticSeries,
} from '@/lib/data'
import type { CalendarPoint } from '@/lib/types'
import {
  MANUAL_SESSION_KEY,
  detectRegionFromEdge,
  locale,
  localeForCountry,
  resolveLocaleFromSignals,
  setLocale,
  t,
  toggleLocale,
} from '@/lib/i18n'

const ROOT_DIR = resolve(__dirname, '../../..')
const apiContract = JSON.parse(
  readFileSync(resolve(ROOT_DIR, 'docs/api-contract.json'), 'utf-8'),
) as {
  endpoints: Record<string, { description?: string; response_example?: Record<string, unknown> }>
}

describe('i18n real-world conditions (timezone, browser, /cdn-cgi/trace, manual priority)', () => {
  beforeEach(() => {
    window.sessionStorage.clear()
    setLocale('fr', false)
  })

  it('defaults to French for Africa/Libreville even with an English browser language', () => {
    expect(
      resolveLocaleFromSignals({
        timeZone: 'Africa/Libreville',
        languages: ['en-US', 'en'],
      }),
    ).toBe('fr')
  })

  it('defaults to English for an English browser outside Francophone timezones', () => {
    expect(
      resolveLocaleFromSignals({
        timeZone: 'America/New_York',
        languages: ['en-US', 'en'],
      }),
    ).toBe('en')
  })

  it('defaults to French for a French browser in Europe/Paris', () => {
    expect(
      resolveLocaleFromSignals({
        timeZone: 'Europe/Paris',
        languages: ['fr-FR', 'fr'],
      }),
    ).toBe('fr')
  })

  it('respects browser preference inside bilingual timezones and countries', () => {
    expect(
      resolveLocaleFromSignals({
        timeZone: 'America/Toronto',
        languages: ['fr-CA', 'en-CA'],
      }),
    ).toBe('fr')
    expect(
      resolveLocaleFromSignals({
        timeZone: 'America/Toronto',
        languages: ['en-CA', 'en'],
      }),
    ).toBe('en')
    expect(localeForCountry('CA', ['fr-CA'])).toBe('fr')
    expect(localeForCountry('CA', ['en-CA'])).toBe('en')
    expect(localeForCountry('GA', ['en-US'])).toBe('fr')
    expect(localeForCountry('US', ['en-US'])).toBe('en')
  })

  it('gives strict session priority to manual FR/EN choice over signals and /cdn-cgi/trace', async () => {
    setLocale('en', true)
    expect(window.sessionStorage.getItem(MANUAL_SESSION_KEY)).toBe('en')
    expect(
      resolveLocaleFromSignals({
        manualSessionLocale: window.sessionStorage.getItem(MANUAL_SESSION_KEY),
        timeZone: 'Africa/Libreville',
        languages: ['fr-FR'],
      }),
    ).toBe('en')

    const fetchSpy = vi.fn(async () => new Response('loc=GA\n', { status: 200 }))
    await detectRegionFromEdge(fetchSpy as unknown as typeof fetch)
    expect(fetchSpy).not.toHaveBeenCalled()
    expect(locale.value).toBe('en')

    toggleLocale()
    expect(locale.value).toBe('fr')
    expect(window.sessionStorage.getItem(MANUAL_SESSION_KEY)).toBe('fr')
    expect(t('français', 'English')).toBe('français')
  })

  it('does not overwrite a manual switch clicked while /cdn-cgi/trace is still in flight', async () => {
    setLocale('fr', false)
    let resolveTrace!: (value: Response) => void
    const pendingFetch = vi.fn(
      () =>
        new Promise<Response>((resolve) => {
          resolveTrace = resolve
        }),
    )

    const edgePromise = detectRegionFromEdge(pendingFetch as unknown as typeof fetch)
    setLocale('en', true)
    resolveTrace(new Response('loc=GA\n', { status: 200 }))
    await edgePromise

    expect(locale.value).toBe('en')
  })

  it('fails gracefully outside Cloudflare, on HTTP errors, or offline without throwing', async () => {
    setLocale('fr', false)

    const networkFailure = vi.fn(async () => {
      throw new Error('offline')
    })
    await expect(
      detectRegionFromEdge(networkFailure as unknown as typeof fetch),
    ).resolves.toBeUndefined()
    expect(locale.value).toBe('fr')

    const htmlFallback = vi.fn(
      async () => new Response('<html>SPA fallback</html>', { status: 200 }),
    )
    await expect(
      detectRegionFromEdge(htmlFallback as unknown as typeof fetch),
    ).resolves.toBeUndefined()
    expect(locale.value).toBe('fr')

    const edgeUs = vi.fn(async () => new Response('fl=12\nloc=US\n', { status: 200 }))
    await detectRegionFromEdge(edgeUs as unknown as typeof fetch)
    expect(locale.value).toBe('en')
  })
})

describe('Derived series calculations and M1 scientific wording', () => {
  it('computes flareSeries exact deltas, preserves pre-launch nulls, and partitions composition cleanly', () => {
    expect(flareSeries.value.length).toBe(allSeries.value.length)
    const staticByMonth = new Map(staticSeries.value.map((p) => [p.month, p]))

    for (const point of flareSeries.value) {
      const allPt = allSeries.value.find((p) => p.month === point.month)!
      const cleanPt = staticByMonth.get(point.month)
      const expectDiff = (a: number | null | undefined, b: number | null | undefined) => {
        if (a == null && b == null) return null
        if (a == null || b == null || a < b) return null
        return a - b
      }
      expect(point.modis_count).toBe(expectDiff(allPt.modis_count, cleanPt?.modis_count))
      expect(point.viirs_snpp_count).toBe(
        expectDiff(allPt.viirs_snpp_count, cleanPt?.viirs_snpp_count),
      )
      expect(point.viirs_noaa20_count).toBe(
        expectDiff(allPt.viirs_noaa20_count, cleanPt?.viirs_noaa20_count),
      )
      if (point.month < '2012-01') {
        expect(point.viirs_snpp_count).toBeNull()
      }
      if (point.month < '2018-04') {
        expect(point.viirs_noaa20_count).toBeNull()
      }
      if (point.harmonized_value !== null) {
        expect(point.harmonized_value).toBeGreaterThanOrEqual(0)
      }
    }

    expect(monthlyMedians.value).toHaveLength(12)
    expect(composition.value.gaTotal).toBe(285013)
    expect(composition.value.gaClean).toBe(175500)
    expect(composition.value.gaExcluded).toBe(109513)

    const partitionSum = composition.value.excludedBySensorPartition.reduce(
      (acc, item) => acc + (item.excluded ?? 0),
      0,
    )
    expect(composition.value.excludedBySensorPartition).toHaveLength(3)
    expect(partitionSum).toBe(composition.value.gaExcluded)
    expect(composition.value.provenanceAudit.isIndependentStaticAudit).toBe(true)
    expect(composition.value.provenanceAudit.scopeTotal).toBe(285013)
    expect(
      composition.value.provenanceAudit.type23Count +
        composition.value.provenanceAudit.type0InMaskCount,
    ).toBe(109513)
  })

  it('marks missing harmonized inputs and negative deltas unavailable without fallback or zero clamping', () => {
    const mkPoint = (month: string, overrides: Partial<CalendarPoint> = {}): CalendarPoint => ({
      month,
      modis_count: 20,
      modis_terra_count: 10,
      modis_aqua_count: 10,
      viirs_snpp_count: 80,
      viirs_noaa20_count: 75,
      harmonized_value: 80,
      ci_low: null,
      ci_high: null,
      baseline_median: null,
      baseline_iqr: null,
      anomaly_percent: null,
      anomaly_absolute: null,
      sensor_regime: 'viirs_snpp_observed',
      coverage_status: 'complete_sp',
      uncertainty_note: '',
      ...overrides,
    })

    const excluded = computeExcludedSeries(
      [
        mkPoint('2023-08', { modis_count: 25, viirs_snpp_count: 90, harmonized_value: null }),
        mkPoint('2024-08', { modis_count: 15, viirs_snpp_count: 70, harmonized_value: 60 }),
        mkPoint('2025-08', { modis_count: 30, viirs_snpp_count: 100, harmonized_value: 100 }),
      ],
      [
        mkPoint('2023-08', { modis_count: 20, viirs_snpp_count: 80, harmonized_value: 70 }),
        mkPoint('2024-08', { modis_count: 25, viirs_snpp_count: 60, harmonized_value: 80 }),
      ],
    )

    const missingHarm = excluded[0]!
    expect(missingHarm.modis_count).toBe(5)
    expect(missingHarm.viirs_snpp_count).toBe(10)
    expect(missingHarm.harmonized_value).toBeNull()
    expect(missingHarm.baseline_median).toBeNull()
    expect(missingHarm.anomaly_absolute).toBeNull()
    expect(missingHarm.anomaly_percent).toBeNull()
    expect(missingHarm.uncertainty_note).toContain('missing_harmonized_input:harmonized_value')

    const negativeDelta = excluded[1]!
    expect(negativeDelta.modis_count).toBeNull()
    expect(negativeDelta.viirs_snpp_count).toBe(10)
    expect(negativeDelta.harmonized_value).toBeNull()
    expect(negativeDelta.uncertainty_note).toContain('negative_series_delta:modis_count')
    expect(negativeDelta.uncertainty_note).toContain('negative_series_delta:harmonized_value')

    const missingMonth = excluded[2]!
    expect(missingMonth.harmonized_value).toBeNull()
    expect(missingMonth.modis_count).toBeNull()
    expect(missingMonth.uncertainty_note).toContain('missing_clean_month')
    expect(missingMonth.uncertainty_note).toContain('missing_harmonized_input:harmonized_value')
  })

  it('explicitly renders exploratory thermal detection caveats in FR UI views', () => {
    setLocale('fr', true)
    const calendarFr = mount(CalendarHeatmap, {
      global: { stubs: { LineChart: true } },
    })
    expect(calendarFr.text().toLowerCase()).toContain('détections thermiques')
    expect(calendarFr.text().toLowerCase()).toContain('catégories exploratoires')
    expect(calendarFr.text().toLowerCase()).toContain('pas toutes des torchères confirmées')
    calendarFr.unmount()

    const splitFr = mount(FlareSplit)
    expect(splitFr.text().toLowerCase()).toContain('détections thermiques')
    expect(splitFr.text().toLowerCase()).toContain('catégorie exploratoire')
    splitFr.unmount()

    const proofFr = mount(ValidationProof, {
      global: { stubs: { LineChart: true } },
    })
    expect(proofFr.text().toLowerCase()).toContain('résultats exploratoires')
    proofFr.unmount()
  }, 30000)

  it('explicitly renders exploratory thermal detection caveats in EN UI views and App copy', () => {
    setLocale('en', true)
    const calendarEn = mount(CalendarHeatmap, {
      global: { stubs: { LineChart: true } },
    })
    expect(calendarEn.text().toLowerCase()).toContain('thermal detections')
    expect(calendarEn.text().toLowerCase()).toContain('exploratory categories')
    expect(calendarEn.text().toLowerCase()).toContain('not all confirmed gas flares')
    calendarEn.unmount()

    const splitEn = mount(FlareSplit)
    expect(splitEn.text().toLowerCase()).toContain('thermal detections')
    expect(splitEn.text().toLowerCase()).toContain('exploratory category')
    splitEn.unmount()

    const hotspotMapSource = readFileSync(
      resolve(__dirname, '../components/HotspotMap.vue'),
      'utf-8',
    )
    expect(hotspotMapSource.toLowerCase()).toContain('détections thermiques')
    expect(hotspotMapSource.toLowerCase()).toContain('thermal detections')
    expect(hotspotMapSource.toLowerCase()).toContain('catégories exploratoires')

    const appSource = readFileSync(resolve(__dirname, '../App.vue'), 'utf-8').toLowerCase()
    expect(appSource).not.toContain('vraie saison des feux')
    expect(appSource).not.toContain('true fire season')
    expect(appSource).not.toContain('brûlis agricoles')
    expect(appSource).not.toContain('feux de lisière')
    expect(appSource).not.toContain('farm clearing')
  }, 30000)
})

describe('M2 API contract alignment across snapshots and CSV fallback', () => {
  it('matches top-level contract keys across health, calendar, coverage, regions, methodology', () => {
    expect(Object.keys(apiContract.endpoints).length).toBeGreaterThanOrEqual(7)
    expect(healthJson).toHaveProperty('status')
    expect(healthJson).toHaveProperty('database')
    expect(healthJson).toHaveProperty('counts')

    expect(calendarStaticJson.region.id).toBe('GA')
    expect(calendarStaticJson.region.filter_static).toBe(true)
    expect(calendarAllJson.region.filter_static).toBe(false)
    expect(calendarStaticJson.series.length).toBeGreaterThan(250)

    expect(coverageJson).toHaveProperty('region', 'GA')
    expect(coverageJson).toHaveProperty('sensors')
    expect(regionsJson).toHaveProperty('regions')
    expect(methodologyJson).toHaveProperty('active_run')
  })

  it('emits BOM CSV with exact API column header', () => {
    const csv = buildSeriesCsvFallback(staticSeries.value.slice(0, 2), 'GA', true)
    const lines = csv.replace(/^\uFEFF/, '').split('\n')
    expect(lines[0]).toBe(
      'region,month,filter_static,modis_count,viirs_snpp_count,viirs_noaa20_count,harmonized_value,ci_low,ci_high,baseline_median,anomaly_percent,anomaly_absolute,sensor_regime,coverage_status,method_version',
    )
    expect(lines).toHaveLength(3)
  })
})
