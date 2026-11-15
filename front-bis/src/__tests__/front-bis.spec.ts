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
  flareSeries,
  monthlyMedians,
  staticSeries,
} from '@/lib/data'
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
  it('computes non-negative flareSeries as max(0, allSeries - staticSeries)', () => {
    expect(flareSeries.value.length).toBe(allSeries.value.length)
    const staticByMonth = new Map(staticSeries.value.map((p) => [p.month, p]))

    for (const point of flareSeries.value) {
      const allPt = allSeries.value.find((p) => p.month === point.month)!
      const cleanPt = staticByMonth.get(point.month)
      expect(point.modis_count).toBe(
        Math.max(0, (allPt.modis_count ?? 0) - (cleanPt?.modis_count ?? 0)),
      )
      expect(point.viirs_snpp_count).toBe(
        Math.max(0, (allPt.viirs_snpp_count ?? 0) - (cleanPt?.viirs_snpp_count ?? 0)),
      )
      expect(point.viirs_noaa20_count).toBe(
        Math.max(0, (allPt.viirs_noaa20_count ?? 0) - (cleanPt?.viirs_noaa20_count ?? 0)),
      )
      expect(point.harmonized_value).toBeGreaterThanOrEqual(0)
    }

    expect(monthlyMedians.value).toHaveLength(12)
    expect(composition.value.gaTotal).toBe(285013)
    expect(composition.value.gaClean).toBe(175500)
    expect(composition.value.gaExcluded).toBe(109513)
    expect(
      composition.value.gaType23Count + composition.value.gaType0InMaskCount,
    ).toBe(composition.value.gaExcluded)
  })

  it('explicitly renders exploratory thermal detection caveats in FR and EN UI views', () => {
    setLocale('fr', true)
    const calendarFr = mount(CalendarHeatmap, {
      global: { stubs: { LineChart: true } },
    })
    expect(calendarFr.text().toLowerCase()).toContain('détections thermiques')
    expect(calendarFr.text().toLowerCase()).toContain('catégories exploratoires')
    expect(calendarFr.text().toLowerCase()).toContain('pas toutes des torchères confirmées')

    const splitFr = mount(FlareSplit)
    expect(splitFr.text().toLowerCase()).toContain('détections thermiques')
    expect(splitFr.text().toLowerCase()).toContain('catégorie exploratoire')

    const proofFr = mount(ValidationProof, {
      global: { stubs: { LineChart: true } },
    })
    expect(proofFr.text().toLowerCase()).toContain('résultats exploratoires')

    setLocale('en', true)
    const calendarEn = mount(CalendarHeatmap, {
      global: { stubs: { LineChart: true } },
    })
    expect(calendarEn.text().toLowerCase()).toContain('thermal detections')
    expect(calendarEn.text().toLowerCase()).toContain('exploratory categories')
    expect(calendarEn.text().toLowerCase()).toContain('not all confirmed gas flares')

    const splitEn = mount(FlareSplit)
    expect(splitEn.text().toLowerCase()).toContain('thermal detections')
    expect(splitEn.text().toLowerCase()).toContain('exploratory category')

    const hotspotMapSource = readFileSync(
      resolve(__dirname, '../components/HotspotMap.vue'),
      'utf-8',
    )
    expect(hotspotMapSource.toLowerCase()).toContain('détections thermiques')
    expect(hotspotMapSource.toLowerCase()).toContain('thermal detections')
    expect(hotspotMapSource.toLowerCase()).toContain('catégories exploratoires')
  })
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
