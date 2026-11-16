<script setup lang="ts">
import { heatColor, HEAT_GRADIENT } from '@/lib/heatScale'
import { computed, nextTick, onMounted, ref, useTemplateRef } from 'vue'
import { gsap, ScrollTrigger } from '@/lib/motion'
import {
  MONTH_NAMES,
  MONTH_NAMES_EN,
  MONTH_SHORT,
  MONTH_SHORT_EN,
  YEARS,
  allSeries,
  composition,
  flareSeries,
  formatCount,
  formatPercent,
  isPartialCoverage,
  median,
  monthNumber,
  staticSeries,
  yearOf,
} from '@/lib/data'
import { locale, t } from '@/lib/i18n'
import type { CalendarPoint } from '@/lib/types'
import provinceMonthlyJson from '@/data/province-monthly.json'
import provinceSvgPathsJson from '@/data/province-svg-paths.json'

interface ProvinceSvg {
  code: string
  name: string
  d: string
  center: number[]
}

const PROVINCE_CODES = ['GA-1', 'GA-2', 'GA-3', 'GA-4', 'GA-5', 'GA-6', 'GA-7', 'GA-8', 'GA-9']
const provincesList = Object.values(provinceSvgPathsJson as Record<string, ProvinceSvg>)

interface ProvinceGeometry {
  polygon: Array<[number, number]>
  minX: number
  maxX: number
  minY: number
  maxY: number
  center: [number, number]
}

interface MapHotspotDot {
  id: string
  x: number
  y: number
  province: string
  kind: 'veg' | 'flare'
  color: string
}

const MAX_RENDERED_MAP_DOTS = 2000

function parseSvgPolygon(d: string): Array<[number, number]> {
  const coords = d.match(/-?\d+(?:\.\d+)?/g)
  if (!coords) return []
  const pts: Array<[number, number]> = []
  for (let i = 0; i + 1 < coords.length; i += 2) {
    pts.push([Number(coords[i]), Number(coords[i + 1])])
  }
  return pts
}

function pointInPolygon(x: number, y: number, poly: Array<[number, number]>): boolean {
  let inside = false
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const [xi, yi] = poly[i]!
    const [xj, yj] = poly[j]!
    const intersect = (yi > y) !== (yj > y) && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi
    if (intersect) inside = !inside
  }
  return inside
}

function createMulberry32(seed: number): () => number {
  let a = seed >>> 0
  return () => {
    a |= 0
    a = (a + 0x6d2b79f5) | 0
    let t = Math.imul(a ^ (a >>> 15), 1 | a)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

function hashStringSeed(input: string): number {
  let h = 2166136261
  for (let i = 0; i < input.length; i++) {
    h ^= input.charCodeAt(i)
    h = Math.imul(h, 16777619)
  }
  return h >>> 0
}

const provinceGeometryMap: Record<string, ProvinceGeometry> = (() => {
  const out: Record<string, ProvinceGeometry> = {}
  for (const prov of provincesList) {
    const polygon = parseSvgPolygon(prov.d)
    let minX = Infinity
    let maxX = -Infinity
    let minY = Infinity
    let maxY = -Infinity
    for (const [x, y] of polygon) {
      if (x < minX) minX = x
      if (x > maxX) maxX = x
      if (y < minY) minY = y
      if (y > maxY) maxY = y
    }
    out[prov.code] = {
      polygon,
      minX: Number.isFinite(minX) ? minX : (prov.center[0] ?? 180) - 10,
      maxX: Number.isFinite(maxX) ? maxX : (prov.center[0] ?? 180) + 10,
      minY: Number.isFinite(minY) ? minY : (prov.center[1] ?? 200) - 10,
      maxY: Number.isFinite(maxY) ? maxY : (prov.center[1] ?? 200) + 10,
      center: [prov.center[0] ?? 180, prov.center[1] ?? 200],
    }
  }
  return out
})()

const provincePointPoolCache = new Map<string, { pts: Array<[number, number]>; rand: () => number }>()

function getProvinceSamplePoints(code: string, kind: 'veg' | 'flare', count: number): Array<[number, number]> {
  if (count <= 0) return []
  const cacheKey = `${code}:${kind}`
  let entry = provincePointPoolCache.get(cacheKey)
  if (!entry) {
    entry = { pts: [], rand: createMulberry32(hashStringSeed(cacheKey)) }
    provincePointPoolCache.set(cacheKey, entry)
  }
  const geom = provinceGeometryMap[code]
  if (!geom || geom.polygon.length < 3) return []
  if (entry.pts.length < count) {
    const spanX = Math.max(1, geom.maxX - geom.minX)
    const spanY = Math.max(1, geom.maxY - geom.minY)
    let attempts = 0
    const maxAttempts = (count - entry.pts.length) * 36 + 120
    while (entry.pts.length < count && attempts < maxAttempts) {
      attempts++
      const x = geom.minX + entry.rand() * spanX
      const y = geom.minY + entry.rand() * spanY
      if (pointInPolygon(x, y, geom.polygon)) {
        entry.pts.push([Math.round(x * 10) / 10, Math.round(y * 10) / 10])
      }
    }
    while (entry.pts.length < count) {
      entry.pts.push([
        Math.round((geom.center[0] + (entry.rand() - 0.5) * 8) * 10) / 10,
        Math.round((geom.center[1] + (entry.rand() - 0.5) * 8) * 10) / 10,
      ])
    }
  }
  return entry.pts.slice(0, count)
}

function allocateCountsToTarget(
  rawCounts: Record<string, number>,
  targetTotal: number | null,
): Record<string, number> {
  if (targetTotal === null || targetTotal < 0) return { ...rawCounts }
  const rawSum = PROVINCE_CODES.reduce((acc, code) => acc + (rawCounts[code] ?? 0), 0)
  if (rawSum <= 0 || targetTotal === 0) {
    return Object.fromEntries(PROVINCE_CODES.map((code) => [code, 0]))
  }
  const roundedTarget = Math.round(targetTotal)
  const exacts = PROVINCE_CODES.map((code) => {
    const raw = rawCounts[code] ?? 0
    const exact = (raw / rawSum) * roundedTarget
    const floorVal = Math.floor(exact)
    return { code, raw, floorVal, remainder: exact - floorVal }
  })
  const out: Record<string, number> = {}
  let allocated = 0
  for (const item of exacts) {
    out[item.code] = item.floorVal
    allocated += item.floorVal
  }
  const remaining = roundedTarget - allocated
  if (remaining > 0) {
    exacts
      .filter((item) => item.raw > 0)
      .sort((a, b) => b.remainder - a.remainder || b.raw - a.raw)
      .slice(0, remaining)
      .forEach((item) => {
        out[item.code] = (out[item.code] ?? 0) + 1
      })
  }
  return out
}

// Médianes historiques 2001-2025 par province pour chaque mois (1 à 12)
const provinceMediansByMonth = (() => {
  const data = provinceMonthlyJson as Record<string, { veg?: Record<string, number>; flare?: Record<string, number> }>
  const medians: Record<string, number[]> = {}
  for (const code of PROVINCE_CODES) {
    medians[code] = Array.from({ length: 12 }, (_, i) => {
      const mNum = i + 1
      const vals: number[] = []
      for (let y = 2001; y <= 2025; y++) {
        const mKey = `${y}-${String(mNum).padStart(2, '0')}`
        const v = data[mKey]?.veg?.[code]
        if (typeof v === 'number') vals.push(v)
      }
      return median(vals)
    })
  }
  return medians
})()

type CalendarMode = 'veg' | 'anomalies' | 'flare' | 'all'
type ScaleMode = 'harmonized' | 'raw'

const props = defineProps<{ reducedMotion?: boolean }>()

const calendarMode = ref<CalendarMode>('veg')
const scaleMode = ref<ScaleMode>('harmonized')
const monthNames = computed(() => (locale.value === 'en' ? MONTH_NAMES_EN : MONTH_NAMES))
const monthShort = computed(() => (locale.value === 'en' ? MONTH_SHORT_EN : MONTH_SHORT))

const activeSeries = computed<CalendarPoint[]>(() => {
  if (calendarMode.value === 'flare') return flareSeries.value
  if (calendarMode.value === 'all') return allSeries.value
  return staticSeries.value
})

const byMonth = computed(() => new Map(activeSeries.value.map((p) => [p.month, p])))

function getPointRaw(p: CalendarPoint | undefined): number | null {
  if (!p) return null
  const y = yearOf(p.month)
  if (y < 2012) {
    return p.modis_count ?? null
  }
  return p.viirs_snpp_count ?? p.modis_count ?? null
}

function getPointValue(
  p: CalendarPoint | undefined,
  scale: ScaleMode = scaleMode.value,
): number | null {
  if (!p) return null
  if (scale === 'raw') return getPointRaw(p)
  return p.harmonized_value ?? null
}

const maxValue = computed(() => {
  const vals = activeSeries.value
    .map((p) => getPointValue(p))
    .filter((v): v is number => v !== null)
  return Math.max(...vals, 1)
})

const activeMedians = computed(() =>
  Array.from({ length: 12 }, (_, idx) => {
    const calMonth = idx + 1
    if (scaleMode.value === 'harmonized') {
      const sample = activeSeries.value.find(
        (p) => yearOf(p.month) >= 2001 && monthNumber(p.month) === calMonth && p.baseline_median !== null,
      )
      if (sample?.baseline_median !== null && sample?.baseline_median !== undefined) {
        return sample.baseline_median
      }
    }
    const vals = activeSeries.value
      .filter((p) => yearOf(p.month) >= 2001 && monthNumber(p.month) === calMonth)
      .map((p) => getPointValue(p))
      .filter((v): v is number => v !== null)
    return median(vals)
  }),
)
const maxMedian = computed(() => Math.max(...activeMedians.value, 1))

const hovered = ref<string | null>(null)
const selected = ref<string | null>('2024-08')
const grid = useTemplateRef<HTMLDivElement>('grid')

const modeButtons = computed(() => [
  {
    id: 'veg' as CalendarMode,
    label: t(
      `Détections thermiques · Type 0 hors sources persistantes (${formatCount(composition.value.gaClean)})`,
      `Thermal detections · Type 0 outside persistent sources (${formatCount(composition.value.gaClean)})`,
    ),
  },
  {
    id: 'anomalies' as CalendarMode,
    label: t(
      'Brûlis habituels vs Flambées anormales (catégories exploratoires)',
      'Routine burning vs Abnormal surges (exploratory categories)',
    ),
  },
  {
    id: 'flare' as CalendarMode,
    label: t(
      `Détections écartées (${formatCount(composition.value.gaExcluded)} · catégorie exploratoire)`,
      `Excluded detections (${formatCount(composition.value.gaExcluded)} · exploratory category)`,
    ),
  },
  {
    id: 'all' as CalendarMode,
    label: t(
      `Toutes détections thermiques (${formatCount(composition.value.gaTotal)})`,
      `All thermal detections (${formatCount(composition.value.gaTotal)})`,
    ),
  },
])

const activeModeDetails = computed(() => {
  switch (calendarMode.value) {
    case 'veg':
      return {
        shortName: t('Type 0 hors masque', 'Type 0 outside mask'),
        title: t(
          'Détections thermiques · Type 0 hors sources persistantes (catégorie exploratoire)',
          'Thermal detections · Type 0 outside persistent sources (exploratory category)',
        ),
        countText: `${formatCount(composition.value.gaClean)} ${t('détections thermiques', 'thermal detections')}`,
        description: t(
          'Retient les détections thermiques NASA type 0 hors des 183 cellules candidates (0,05°) de sources persistantes. Il s’agit de candidats feux de végétation (catégorie exploratoire), sans validation causale terrain.',
          'Retains NASA type-0 thermal detections outside the 183 candidate persistent-source cells (0.05°). These are vegetation fire candidates (exploratory category), without causal field validation.',
        ),
      }
    case 'anomalies':
      return {
        shortName: t('Écarts saisonniers (exploratoire)', 'Seasonal deviations (exploratory)'),
        title: t(
          'Catégories exploratoires : Brûlis habituels vs Flambées anormales (écarts à la médiane)',
          'Exploratory categories: Routine burning vs Abnormal surges (deviations from median)',
        ),
        countText: t('Écart statistique à la médiane 2001–2025', 'Statistical deviation vs 2001–2025 median'),
        description: t(
          'Colore chaque mois selon l’écart statistique des détections thermiques à la médiane mensuelle 2001–2025. Ces seuils (+15 %, +25 %, +50 %) sont des catégories exploratoires de lecture statistique et ne constituent pas une classification causale des feux.',
          'Colors each month by the statistical deviation of thermal detections from the 2001–2025 monthly median. These thresholds (+15%, +25%, +50%) are exploratory statistical reading categories, not a causal classification of fire origin.',
        ),
      }
    case 'flare':
      return {
        shortName: t('Détections écartées (exploratoire)', 'Excluded detections (exploratory)'),
        title: t(
          'Détections thermiques écartées (catégorie exploratoire : différence de séries)',
          'Excluded thermal detections (exploratory category: series difference)',
        ),
        countText: `${formatCount(composition.value.gaExcluded)} ${t('détections écartées', 'excluded detections')}`,
        description: t(
          'Série exploratoire calculée par différence max(0, allSeries − staticSeries). Elle regroupe les types 2/3 de la NASA et les détections type 0 situées dans les 183 cellules candidates du masque 0,05° : elles ne sont pas toutes des torchères confirmées.',
          'Exploratory series computed by difference max(0, allSeries − staticSeries). It combines NASA type 2/3 detections and type-0 detections inside the 183 candidate 0.05° mask cells: they are not all confirmed gas flares.',
        ),
      }
    case 'all':
      return {
        shortName: t('Toutes détections thermiques', 'All thermal detections'),
        title: t(
          'Toutes détections thermiques confondues (sans filtre statique)',
          'All thermal detections combined (without static filter)',
        ),
        countText: `${formatCount(composition.value.gaTotal)} ${t('détections thermiques', 'thermal detections')}`,
        description: t(
          'Somme brute de toutes les détections thermiques satellitaires (type 0, type 2/3 et cellules candidates confondus) avant application du filtre des sources persistantes.',
          'Raw sum of all satellite thermal detections (type 0, type 2/3, and candidate cells combined) before applying the persistent-source filter.',
        ),
      }
  }
})

function coverageLabel(value: string): string {
  switch (value) {
    case 'complete_sp':
      return t('Complète (archive SP)', 'Complete (SP archive)')
    case 'partial_sp':
      return t('Mois incomplet', 'Partial month')
    case 'mixed_sp_nrt':
      return t('Mixte archive + temps réel', 'Mixed archive + near real-time')
    case 'nrt_only':
      return t('Temps quasi réel', 'Near real-time')
    case 'no_data':
      return t('Aucune donnée', 'No data')
    default:
      return value.replaceAll('_', ' ')
  }
}

function ordinal(value: number): string {
  if (locale.value === 'en') {
    const mod100 = value % 100
    if (mod100 >= 11 && mod100 <= 13) return `${value}th`
    const mod10 = value % 10
    if (mod10 === 1) return `${value}st`
    if (mod10 === 2) return `${value}nd`
    if (mod10 === 3) return `${value}rd`
    return `${value}th`
  }
  return value === 1 ? '1er' : `${value}e`
}

// Le survol du calendrier anime instantanément le mois actif, avec repli sur le mois épinglé ou 2024-08
const activeMonth = computed(() => hovered.value ?? selected.value ?? '2024-08')
const fallbackPoint = computed(
  () => activeSeries.value.find((p) => p.month === '2024-08') ?? activeSeries.value[activeSeries.value.length - 1]!,
)
const active = computed<CalendarPoint>(() => byMonth.value.get(activeMonth.value) ?? fallbackPoint.value)

const cleanPoint = computed<CalendarPoint | undefined>(() =>
  staticSeries.value.find((p) => p.month === activeMonth.value),
)
const allPoint = computed<CalendarPoint | undefined>(() =>
  allSeries.value.find((p) => p.month === activeMonth.value),
)
const flarePoint = computed<CalendarPoint | undefined>(() =>
  flareSeries.value.find((p) => p.month === activeMonth.value),
)

const activeValue = computed(() => getPointValue(active.value))

const monthVegCount = computed<number | null>(() =>
  scaleMode.value === 'raw'
    ? getPointValue(cleanPoint.value, 'raw')
    : (cleanPoint.value?.harmonized_value ?? null),
)
const monthFlareCount = computed<number | null>(() => {
  if (scaleMode.value === 'raw') {
    const allVal = getPointValue(allPoint.value, 'raw')
    const vegVal = getPointValue(cleanPoint.value, 'raw')
    if (allVal === null || vegVal === null || allVal < vegVal) return null
    return allVal - vegVal
  }
  return flarePoint.value?.harmonized_value ?? null
})
const monthTotalCount = computed<number | null>(() =>
  scaleMode.value === 'raw'
    ? getPointValue(allPoint.value, 'raw')
    : (allPoint.value?.harmonized_value ?? null),
)
const monthVegShare = computed<number | null>(() => {
  const tot = monthTotalCount.value
  const veg = monthVegCount.value
  return tot !== null && tot > 0 && veg !== null ? Math.round((veg / tot) * 1000) / 10 : null
})
const monthFlareShare = computed<number | null>(() => {
  const tot = monthTotalCount.value
  const flare = monthFlareCount.value
  return tot !== null && tot > 0 && flare !== null ? Math.round((flare / tot) * 1000) / 10 : null
})

const activeHarmonizedValue = computed(() => active.value.harmonized_value)
const activeBaselineMedian = computed(() => active.value.baseline_median)
const activeAnomalyDiff = computed(() =>
  active.value.baseline_median !== null && active.value.harmonized_value !== null
    ? Math.round((active.value.harmonized_value - active.value.baseline_median) * 10) / 10
    : null,
)

const isHarmonizedPeriod = computed(() => yearOf(active.value.month) < 2012)
const sensorRegimeLabel = computed(() => {
  const regime = active.value.sensor_regime
  switch (regime) {
    case 'partial_year':
      return t('Démarrage partiel (Terra seul)', 'Partial launch (Terra only)')
    case 'modis_terra_only':
      return t('Satellite Terra seul (MODIS 1 km)', 'Terra satellite only (MODIS 1km)')
    case 'modis_terra_aqua':
      return t('Satellites Terra + Aqua (MODIS 1 km)', 'Terra + Aqua satellites (MODIS 1km)')
    case 'viirs_snpp_observed':
      return t('Satellite Suomi-NPP (VIIRS 375 m)', 'Suomi-NPP satellite (VIIRS 375m)')
    default:
      return regime ? regime.replaceAll('_', ' ') : t('Observation satellite', 'Satellite observation')
  }
})

const rankInfo = computed(() => {
  const pt = active.value
  const m = monthNumber(pt.month)
  const sameMonth = activeSeries.value
    .filter((p) => monthNumber(p.month) === m && p.harmonized_value !== null)
    .sort((a, b) => (b.harmonized_value ?? 0) - (a.harmonized_value ?? 0))
  const rank = Math.max(1, sameMonth.findIndex((p) => p.month === pt.month) + 1)
  const years = sameMonth.map((p) => yearOf(p.month))
  return {
    rank,
    total: sameMonth.length,
    minYear: years.length ? Math.min(...years) : 2001,
    maxYear: years.length ? Math.max(...years) : 2025,
  }
})

const activeInterpretation = computed(() => {
  if (calendarMode.value === 'flare') {
    if (getPointValue(active.value) === null) {
      return {
        text: t(
          'Différence écartée indisponible (valeur harmonisée manquante ou écart négatif)',
          'Excluded difference unavailable (missing harmonized value or negative delta)',
        ),
        tone: 'neutral',
      }
    }
    return {
      text: t(
        'Détections écartées (types 2/3 + masque 0,05° · catégorie exploratoire)',
        'Excluded detections (type 2/3 + 0.05° mask · exploratory category)',
      ),
      tone: 'cool',
    }
  }
  const pct = active.value.anomaly_percent
  if (pct === null || pct === undefined) {
    return { text: t('Mois partiel (2000)', 'Partial start month (2000)'), tone: 'neutral' }
  }
  if (pct > 50) {
    return {
      text: t(
        'Excédent statistique > +50 % (flambée anormale · catégorie exploratoire)',
        'Statistical surplus > +50% (abnormal surge · exploratory category)',
      ),
      tone: 'extreme',
    }
  }
  if (pct >= 25) {
    return { text: t('Au-dessus de la médiane saisonnière', 'Above seasonal median'), tone: 'warm' }
  }
  if (pct <= -20) {
    return { text: t('Mois plus calme que d’habitude', 'Quieter than normal'), tone: 'cool' }
  }
  return {
    text: t(
      'Proche de la médiane saisonnière (catégorie exploratoire)',
      'Near seasonal median (exploratory category)',
    ),
    tone: 'neutral',
  }
})

const isPinned = computed(() => selected.value !== null && selected.value === active.value.month)

function cell(month: string): CalendarPoint | undefined {
  return byMonth.value.get(month)
}

function monthId(year: number, month: number): string {
  return `${year}-${String(month).padStart(2, '0')}`
}

function colorForIntensity(value: number | null | undefined): string {
  if (value === null || value === undefined) return 'rgba(59, 42, 34, 0.08)'
  return heatColor(value, maxValue.value)
}

function colorForAnomaly(point: CalendarPoint | undefined): string {
  const pct = point?.anomaly_percent
  if (pct === null || pct === undefined) return 'rgba(59, 42, 34, 0.08)'
  if (pct <= 15) return 'rgb(245, 235, 218)' // Brûlis habituels / calme -> beige clair
  if (pct <= 25) return 'rgb(232, 185, 118)' // Léger excédent -> sable doré
  if (pct <= 50) return 'rgb(185, 53, 27)' // +25 % à +50 % -> rouge braise
  return 'rgb(42, 6, 6)' // > +50 % -> bordeaux-noir très sombre
}

function cellStyle(point: CalendarPoint | undefined) {
  if (calendarMode.value === 'anomalies') {
    return { backgroundColor: colorForAnomaly(point) }
  }
  return { backgroundColor: colorForIntensity(getPointValue(point)) }
}

function ariaLabel(point: CalendarPoint | undefined, year: number, month: number): string {
  const mName = monthNames.value[month - 1]
  if (!point) return `${mName} ${year} — ${t('aucune donnée', 'no data')}`
  const value = formatCount(getPointValue(point))
  const anomaly =
    point.anomaly_percent !== null
      ? `, ${t('écart à la normale', 'vs normal')} ${formatPercent(point.anomaly_percent)}`
      : ''
  const coverage = isPartialCoverage(point)
    ? `, ${t('couverture partielle', 'partial coverage')}`
    : ''
  return `${mName} ${year} : ${value} ${t('points chauds', 'hotspots')}${anomaly}${coverage}`
}

// Données provinciales calculées pour le mois actif selon le filtre et l'échelle sélectionnés
const rawActiveMonthProvincial = computed(() => {
  const mData = (provinceMonthlyJson as Record<string, { veg?: Record<string, number>; flare?: Record<string, number> }>)[activeMonth.value]
  const veg: Record<string, number> = {}
  const flare: Record<string, number> = {}
  for (const code of PROVINCE_CODES) {
    veg[code] = mData?.veg?.[code] ?? 0
    flare[code] = mData?.flare?.[code] ?? 0
  }
  return { veg, flare }
})

const scaledProvincialBreakdown = computed(() => {
  const raw = rawActiveMonthProvincial.value
  if (scaleMode.value !== 'harmonized') {
    return raw
  }
  return {
    veg: allocateCountsToTarget(raw.veg, monthVegCount.value),
    flare: allocateCountsToTarget(raw.flare, monthFlareCount.value),
  }
})

const activeProvinceCounts = computed<Record<string, number>>(() => {
  const { veg, flare } = scaledProvincialBreakdown.value
  const res: Record<string, number> = {}
  for (const code of PROVINCE_CODES) {
    if (calendarMode.value === 'flare') {
      res[code] = flare[code] ?? 0
    } else if (calendarMode.value === 'all') {
      res[code] = (veg[code] ?? 0) + (flare[code] ?? 0)
    } else {
      // veg and anomalies modes
      res[code] = veg[code] ?? 0
    }
  }
  return res
})

function getProvinceCount(code: string): number {
  return activeProvinceCounts.value[code] ?? 0
}

const maxProvinceMonthCount = computed(() => {
  const vals = Object.values(activeProvinceCounts.value)
  return Math.max(...vals, 1)
})

const activeMonthTotalFires = computed(() => {
  return Object.values(activeProvinceCounts.value).reduce((a, b) => a + b, 0)
})

const mapHotspotState = computed<{
  dots: MapHotspotDot[]
  vegShown: number
  flareShown: number
  totalSourceCount: number
  ratioPerDot: number
}>(() => {
  const { veg, flare } = scaledProvincialBreakdown.value
  const includeVeg = calendarMode.value !== 'flare'
  const includeFlare = calendarMode.value === 'flare' || calendarMode.value === 'all'

  const rawEntries: Array<{ code: string; kind: 'veg' | 'flare'; count: number }> = []
  let totalSourceCount = 0

  for (const code of PROVINCE_CODES) {
    if (includeVeg) {
      const c = veg[code] ?? 0
      if (c > 0) {
        rawEntries.push({ code, kind: 'veg', count: c })
        totalSourceCount += c
      }
    }
    if (includeFlare) {
      const c = flare[code] ?? 0
      if (c > 0) {
        rawEntries.push({ code, kind: 'flare', count: c })
        totalSourceCount += c
      }
    }
  }

  if (totalSourceCount <= 0 || rawEntries.length === 0) {
    return { dots: [], vegShown: 0, flareShown: 0, totalSourceCount: 0, ratioPerDot: 1 }
  }

  const budget = Math.min(totalSourceCount, MAX_RENDERED_MAP_DOTS)
  const scaleDown = totalSourceCount > MAX_RENDERED_MAP_DOTS
  const allocatedCounts = scaleDown
    ? (() => {
        const exacts = rawEntries.map((e) => {
          const exact = (e.count / totalSourceCount) * budget
          const floorVal = Math.floor(exact)
          return { ...e, floorVal, remainder: exact - floorVal }
        })
        let allocated = exacts.reduce((acc, e) => acc + e.floorVal, 0)
        // Garantir au moins 1 point pour les provinces non nulles quand possible
        for (const e of exacts) {
          if (e.floorVal === 0 && allocated < budget) {
            e.floorVal = 1
            allocated++
          }
        }
        const rem = budget - allocated
        if (rem > 0) {
          exacts
            .slice()
            .sort((a, b) => b.remainder - a.remainder || b.count - a.count)
            .slice(0, rem)
            .forEach((e) => {
              e.floorVal++
            })
        }
        return exacts.map((e) => ({ code: e.code, kind: e.kind, drawCount: e.floorVal }))
      })()
    : rawEntries.map((e) => ({ code: e.code, kind: e.kind, drawCount: e.count }))

  const dots: MapHotspotDot[] = []
  let vegShown = 0
  let flareShown = 0

  for (const entry of allocatedCounts) {
    if (entry.drawCount <= 0) continue
    const pts = getProvinceSamplePoints(entry.code, entry.kind, entry.drawCount)
    const color = entry.kind === 'flare' ? '#38bdf8' : '#ff7828'
    if (entry.kind === 'veg') vegShown += pts.length
    else flareShown += pts.length

    for (let i = 0; i < pts.length; i++) {
      const [x, y] = pts[i]!
      dots.push({
        id: `${entry.code}-${entry.kind}-${i}`,
        x,
        y,
        province: entry.code,
        kind: entry.kind,
        color,
      })
    }
  }

  // Entrelacer légèrement les types pour éviter qu'une série ne masque l'autre en mode 'all'
  if (includeVeg && includeFlare && dots.length > 1) {
    dots.sort((a, b) => ((a.x * 13 + a.y * 7) % 11) - ((b.x * 13 + b.y * 7) % 11))
  }

  const ratioPerDot = dots.length > 0 ? Math.max(1, Math.round(totalSourceCount / dots.length)) : 1
  return { dots, vegShown, flareShown, totalSourceCount, ratioPerDot }
})

function getProvinceFill(code: string): string {
  const count = activeProvinceCounts.value[code] ?? 0
  if (count === 0) return 'rgba(255, 255, 255, 0.05)'

  if (calendarMode.value === 'anomalies') {
    const mNum = Number(activeMonth.value.slice(5, 7))
    const rawCount = rawActiveMonthProvincial.value.veg[code] ?? 0
    const med = provinceMediansByMonth[code]?.[mNum - 1] ?? 0
    const pct = med > 0 ? ((rawCount - med) / med) * 100 : 0
    if (pct <= 15) return 'rgb(245, 235, 218)' // Beige clair - brûlis habituels normaux
    if (pct <= 25) return 'rgb(232, 185, 118)' // Sable doré - léger excédent
    if (pct <= 50) return 'rgb(215, 75, 30)'  // Rouge braise - forte activité
    return 'rgb(160, 20, 15)'                 // Bordeaux-noir - flambée anormale (> +50%)
  }

  return heatColor(count, maxProvinceMonthCount.value)
}

const topProvincesList = computed(() => {
  const total = activeMonthTotalFires.value
  return provincesList
    .map((p) => {
      const count = activeProvinceCounts.value[p.code] ?? 0
      const share = total > 0 ? Math.round((count / total) * 1000) / 10 : 0
      return {
        code: p.code,
        name: p.name,
        count,
        share,
        center: p.center,
      }
    })
    .sort((a, b) => b.count - a.count)
    .slice(0, 4)
})

const topProvince = computed(() => topProvincesList.value[0] ?? null)

function getProvinceAbbrev(name: string): string {
  switch (name) {
    case 'Estuaire': return 'EST'
    case 'Haut-Ogooué': return 'H-OG'
    case 'Moyen-Ogooué': return 'M-OG'
    case 'Ngounié': return 'NGO'
    case 'Nyanga': return 'NYA'
    case 'Ogooué-Ivindo': return 'O-IV'
    case 'Ogooué-Lolo': return 'O-LO'
    case 'Ogooué-Maritime': return 'O-MA'
    case 'Woleu-Ntem': return 'W-NT'
    default: return name.slice(0, 3).toUpperCase()
  }
}

const hoveredProvince = ref<string | null>(null)
const hoveredProvinceData = computed(() => {
  if (!hoveredProvince.value) return null
  const code = hoveredProvince.value
  const p = (provinceSvgPathsJson as Record<string, ProvinceSvg>)[code]
  if (!p) return null
  const count = activeProvinceCounts.value[code] ?? 0
  const total = activeMonthTotalFires.value
  const share = total > 0 ? Math.round((count / total) * 1000) / 10 : 0
  const mNum = Number(activeMonth.value.slice(5, 7))
  const rawVeg = rawActiveMonthProvincial.value.veg[code] ?? 0
  const med = provinceMediansByMonth[code]?.[mNum - 1] ?? 0
  const anomaly = med > 0 ? Math.round(((rawVeg - med) / med) * 10) / 10 : null
  return {
    code,
    name: p.name,
    count,
    share,
    anomaly,
  }
})

const calendarModeLabel = computed(() => {
  switch (calendarMode.value) {
    case 'veg': return t('Feux de végétation', 'Vegetation fires')
    case 'anomalies': return t('Écarts à la normale', 'Seasonal anomalies')
    case 'flare': return t('Torchères & industrie', 'Flaring & industry')
    case 'all': return t('Toutes détections', 'All detections')
  }
})

const dynamicMapContextNote = computed(() => {
  const mNum = Number(activeMonth.value.slice(5, 7))
  const top = topProvince.value
  if (calendarMode.value === 'flare') {
    return t(
      'Torchères industrielles : concentrées quasi exclusivement sur la côte atlantique et offshore (Ogooué-Maritime).',
      'Industrial flaring: heavily concentrated along the Atlantic coast and offshore (Ogooué-Maritime).',
    )
  }
  if (calendarMode.value === 'anomalies') {
    if (top && top.count > 0) {
      return t(
        `Mode anomalies : ${top.name} concentre la majorité de l’excédent thermique ce mois-ci (${top.share} % du total national).`,
        `Anomalies mode: ${top.name} concentrates most of the thermal excess this month (${top.share}% of national total).`,
      )
    }
    return t(
      'Mode anomalies : compare chaque province à sa propre médiane historique sur 25 ans.',
      'Anomalies mode: compares each province against its own 25-year historical median.',
    )
  }
  if (mNum >= 6 && mNum <= 9) {
    return t(
      `Grande saison sèche (juin–septembre) : forte activité sur les savanes et plateaux du sud-est (${top?.name ?? 'Haut-Ogooué'}).`,
      `Major dry season (June–September): high activity across southeastern savannas and plateaus (${top?.name ?? 'Haut-Ogooué'}).`,
    )
  }
  return t(
    'Saison des pluies : couverture nuageuse dense et feux de végétation très dispersés.',
    'Rainy season: dense cloud cover and sparsely distributed vegetation fires.',
  )
})

const mapLegendGradientStyle = computed(() => {
  if (calendarMode.value === 'anomalies') {
    return {
      background: 'linear-gradient(to right, rgb(245, 235, 218), rgb(232, 185, 118), rgb(215, 75, 30), rgb(160, 20, 15))',
    }
  }
  return {
    background: 'linear-gradient(to right, #05080d, #1a2a3a, #8a4020, #e65c00, #ffba3b)',
  }
})

// Gestion du Popover Flottant au niveau de la cellule active
const calendarColRef = useTemplateRef<HTMLDivElement>('calendarColRef')
const popoverPos = ref({ top: 120, left: 160, placement: 'right' as 'right' | 'left' })

function updatePopoverPosition(cellEl: HTMLElement) {
  if (!cellEl || !calendarColRef.value) return
  const colRect = calendarColRef.value.getBoundingClientRect()
  const cellRect = cellEl.getBoundingClientRect()

  const cellLeft = cellRect.left - colRect.left
  const cellTop = cellRect.top - colRect.top

  const popoverWidth = 320
  let left = 0
  let placement: 'right' | 'left' = 'right'

  if (cellLeft + cellRect.width + popoverWidth + 14 > colRect.width) {
    left = Math.max(10, cellLeft - popoverWidth - 10)
    placement = 'left'
  } else {
    left = cellLeft + cellRect.width + 10
    placement = 'right'
  }

  const popoverEstimatedHeight = 250
  let top = cellTop - 30
  if (top + popoverEstimatedHeight > colRect.height && cellTop > popoverEstimatedHeight) {
    top = Math.max(10, cellTop - popoverEstimatedHeight + cellRect.height)
  }
  if (top < 10) top = 10
  popoverPos.value = { top, left, placement }
}

function onCellEnter(mId: string, ev: Event) {
  hovered.value = mId
  updatePopoverPosition(ev.currentTarget as HTMLElement)
}

function onCellLeave() {
  hovered.value = null
  if (selected.value) {
    const el = grid.value?.querySelector<HTMLElement>(`[data-cell="${selected.value}"]`)
    if (el) updatePopoverPosition(el)
  }
}

function onCellClick(mId: string, ev: MouseEvent) {
  if (selected.value === mId) {
    selected.value = null
  } else {
    selected.value = mId
    updatePopoverPosition(ev.currentTarget as HTMLElement)
  }
}

function unpin() {
  selected.value = null
}

const showPopover = computed(() => Boolean(hovered.value || selected.value))

const popoverStyle = computed(() => ({
  top: `${popoverPos.value.top}px`,
  left: `${popoverPos.value.left}px`,
  pointerEvents: isPinned.value ? ('auto' as const) : ('none' as const),
}))

function onKeydown(event: KeyboardEvent) {
  const target = event.target as HTMLElement
  const month = target?.dataset?.cell
  if (!month) return
  const [year, m] = month.split('-').map(Number) as [number, number]
  let nextYear = year
  let nextMonth = m
  if (event.key === 'ArrowLeft') nextMonth = m === 1 ? 12 : m - 1
  else if (event.key === 'ArrowRight') nextMonth = m === 12 ? 1 : m + 1
  else if (event.key === 'ArrowUp') nextYear = year - 1
  else if (event.key === 'ArrowDown') nextYear = year + 1
  else if (event.key === 'Home') nextMonth = 1
  else if (event.key === 'End') nextMonth = 12
  else return
  if (event.key === 'ArrowLeft' && m === 1) nextYear = year - 1
  if (event.key === 'ArrowRight' && m === 12) nextYear = year + 1
  if (nextYear < 2000 || nextYear > 2025) return
  const targetId = monthId(nextYear, nextMonth)
  const next = grid.value?.querySelector<HTMLButtonElement>(`[data-cell="${targetId}"]`)
  if (next) {
    event.preventDefault()
    next.focus()
    hovered.value = targetId
  }
}

onMounted(async () => {
  await nextTick()
  const defaultCell = grid.value?.querySelector<HTMLElement>('[data-cell="2024-08"]')
  if (defaultCell) {
    updatePopoverPosition(defaultCell)
  }
  if (props.reducedMotion) return
  const cells = grid.value?.querySelectorAll('.cell')
  if (!cells?.length) return
  gsap.from(cells, {
    opacity: 0,
    scale: 0.86,
    duration: 0.5,
    ease: 'power2.out',
    stagger: { each: 0.002, from: 'start' },
    immediateRender: false,
    scrollTrigger: { trigger: grid.value, start: 'top 84%', once: true },
  })
  ScrollTrigger.refresh()
})
</script>

<template>
  <div class="calendar">
    <!-- Sélecteur de type de points chauds -->
    <div class="calendar-modes" role="group" :aria-label="t('Filtrer le calendrier par type de points chauds', 'Filter calendar by hotspot type')">
      <button
        v-for="btn in modeButtons"
        :key="btn.id"
        type="button"
        class="cal-mode-btn"
        :class="{ active: calendarMode === btn.id }"
        @click="calendarMode = btn.id"
      >
        {{ btn.label }}
      </button>
    </div>

    <!-- Bannière contextuelle expliquant la pertinence du filtre sélectionné -->
    <div class="filter-context-banner" :class="calendarMode">
      <div class="filter-context-header">
        <span class="filter-context-pill">{{ activeModeDetails.title }}</span>
        <span class="filter-context-count">{{ activeModeDetails.countText }}</span>
      </div>
      <p class="filter-context-desc">{{ activeModeDetails.description }}</p>
    </div>

    <!-- Encart pédagogique : catégories exploratoires & clarification du code "Type 0" -->
    <div class="burner-callout">
      <strong>
        {{
          t(
            'Que signifient ces catégories exploratoires (« brûlis habituels », « flambées anormales », « détections écartées » et « Type 0 ») ?',
            'What do these exploratory categories ("routine burning", "abnormal surges", "excluded detections", and "Type 0") mean?',
          )
        }}
      </strong>
      <p>
        {{
          t(
            'Depuis l’espace, un satellite mesure des détections thermiques sans observer directement la cause d’un feu. La NASA attribue le code produit « Type 0 » aux anomalies thermiques compatibles avec la végétation, par opposition aux codes « Types 2 et 3 » (sources fixes ou offshore). Les libellés « brûlis habituels » et « flambées anormales » sont des catégories exploratoires fondées uniquement sur l’écart statistique à la médiane mensuelle 2001–2025 (comme août 2024 à +79 %) et non des preuves causales. De même, les « détections écartées » (différence de séries) regroupent des types 2/3 et des type 0 situés dans les 183 cellules candidates du masque 0,05° : elles ne sont pas toutes des torchères confirmées.',
            'From space, satellites measure thermal detections without directly observing what ignited a fire. NASA assigns product code "Type 0" to vegetation-compatible thermal anomalies, as opposed to "Types 2 & 3" (fixed or offshore sources). The labels "routine burning" and "abnormal surges" are exploratory categories based strictly on statistical deviation from the 2001–2025 monthly median (such as August 2024 at +79%), not causal proof. Likewise, "excluded detections" (series difference) combine NASA types 2/3 and type-0 detections inside the 183 candidate 0.05° mask cells: they are not all confirmed gas flares.',
          )
        }}
      </p>
    </div>

    <!-- Barre de superposition d'échelle : Harmonisé vs Brut -->
    <div class="scale-superposition-bar">
      <div class="scale-label-group">
        <span class="scale-title">{{ t('Superposition d’échelle :', 'Scale overlay:') }}</span>
        <span class="scale-subtitle">{{ t('Harmonisation multi-capteurs MODIS ↔ VIIRS', 'Multi-sensor MODIS ↔ VIIRS harmonization') }}</span>
      </div>
      <div class="scale-toggle-group" role="radiogroup" :aria-label="t('Choisir l’échelle des données', 'Choose data scale')">
        <button
          type="button"
          class="scale-toggle-btn"
          :class="{ active: scaleMode === 'harmonized' }"
          @click="scaleMode = 'harmonized'"
        >
          <span class="toggle-indicator"></span>
          <span class="toggle-text">{{ t('Échelle unifiée harmonisée (équiv. VIIRS 375 m)', 'Unified harmonized scale (VIIRS 375m equiv.)') }}</span>
          <span class="toggle-badge-rec">{{ t('Recommandé', 'Recommended') }}</span>
        </button>
        <button
          type="button"
          class="scale-toggle-btn"
          :class="{ active: scaleMode === 'raw' }"
          @click="scaleMode = 'raw'"
        >
          <span class="toggle-indicator"></span>
          <span class="toggle-text">{{ t('Données brutes des satellites (non harmonisées)', 'Raw satellite data (unharmonized)') }}</span>
        </button>
      </div>
    </div>

    <!-- Alerte pédagogique quand le mode brut est activé -->
    <div v-if="scaleMode === 'raw'" class="raw-alert-banner">
      <span class="alert-icon">⚠️</span>
      <p>
        {{
          t(
            'Mode brut actif : les années 2000–2011 apparaissent artificiellement 4× plus claires que 2012–2025. Cette rupture visuelle n’est pas due au climat mais au passage du capteur MODIS (1 km) à VIIRS (375 m). Activez l’Échelle unifiée harmonisée pour comparer les années sans ce biais.',
            'Raw mode active: years 2000–2011 appear artificially 4× paler than 2012–2025. This visual discontinuity reflects sensor physics (MODIS 1km to VIIRS 375m upgrade), not wildfire changes. Switch to Unified harmonized scale to compare years fairly.',
          )
        }}
      </p>
    </div>

    <div class="calendar-top">
      <div class="season-strip" aria-hidden="true">
        <span class="season-caption">
          {{ t('Profil moyen sur 12 mois (médiane 2001–2025)', 'Average 12-month profile (2001–2025 median)') }}
          <span class="scale-hint">({{ scaleMode === 'harmonized' ? t('échelle unifiée VIIRS 375 m', 'unified VIIRS 375m scale') : t('comptes bruts non alignés', 'unaligned raw counts') }})</span>
        </span>
        <div class="season-bars">
          <div
            v-for="(value, index) in activeMedians"
            :key="index"
            class="season-bar"
            :class="{
              main: calendarMode !== 'flare' && [7, 8, 9].includes(index + 1),
              secondary: calendarMode !== 'flare' && [2, 3].includes(index + 1),
            }"
          >
            <i :style="{ height: `${Math.max(6, (value / maxMedian) * 100)}%` }"></i>
            <span>{{ monthShort[index] }}</span>
          </div>
        </div>
      </div>

      <div v-if="calendarMode === 'anomalies'" class="legend legend-anomalies" aria-hidden="true">
        <span class="tiny-label">{{ t('Lecture : brûlis vs flambée', 'Reading: routine vs surge') }}</span>
        <div class="anomaly-swatches">
          <span><i style="background: rgb(245, 235, 218)"></i>{{ t('Habituel (≤ +15 %)', 'Routine (≤ +15%)') }}</span>
          <span><i style="background: rgb(232, 185, 118)"></i>{{ t('Tend (+15 à +25 %)', 'Elevated (+15–25%)') }}</span>
          <span><i style="background: rgb(185, 53, 27)"></i>{{ t('Fort (+25 à +50 %)', 'High (+25–50%)') }}</span>
          <span><i style="background: rgb(42, 6, 6)"></i>{{ t('Flambée (> +50 %)', 'Surge (> +50%)') }}</span>
        </div>
      </div>

      <div v-else class="legend" aria-hidden="true">
        <span class="tiny-label">{{ t('Plus c’est sombre, plus c’est intense', 'Darker = higher fire intensity') }}</span>
        <div class="legend-scale">
          <span class="legend-min">{{ t('0 (clair)', '0 (light)') }}</span>
          <span class="legend-gradient" :style="{ background: HEAT_GRADIENT }"></span>
          <span class="legend-max">{{ formatCount(maxValue) }} {{ t('(sombre)', '(dark)') }}</span>
        </div>
      </div>
    </div>

    <div class="calendar-layout">
      <!-- Colonne Gauche : Calendrier + Popover Flottant -->
      <div class="calendar-col-left" ref="calendarColRef">
        <div class="calendar-scroll">
          <!-- Légende des régimes de satellites le long des années -->
          <div class="calendar-era-legend">
            <span class="era-tag era-modis">{{ t('2000–2011 : MODIS 1 km (Reconstruit à l’échelle VIIRS)', '2000–2011: MODIS 1km (Reconstructed to VIIRS scale)') }}</span>
            <span class="era-tag era-viirs">{{ t('2012–2025 : VIIRS 375 m (Observation satellite directe)', '2012–2025: VIIRS 375m (Direct satellite observation)') }}</span>
          </div>

          <div class="calendar-grid" ref="grid" @keydown="onKeydown">
            <div class="grid-corner"></div>
            <div v-for="month in monthShort" :key="month" class="month-head">
              {{ month }}
            </div>

            <template v-for="year in YEARS" :key="year">
              <div class="year-head" :class="{ 'is-modis-era': year < 2012, 'is-viirs-era': year >= 2012 }">
                <span class="year-text">{{ year }}</span>
                <span class="year-era-dot" :title="year < 2012 ? t('Période MODIS 1 km (harmonisée)', 'MODIS 1km period (harmonized)') : t('Période VIIRS 375 m (directe)', 'VIIRS 375m period (direct)')"></span>
              </div>
              <template v-for="month in 12" :key="`${year}-${month}`">
                <div
                  v-if="year === 2000 && month < 11"
                  class="cell is-empty"
                  aria-hidden="true"
                ></div>
                <button
                  v-else
                  type="button"
                  class="cell"
                  :class="{
                    'is-selected': selected === monthId(year, month),
                    'is-active': activeMonth === monthId(year, month),
                    'is-partial': cell(monthId(year, month))
                      ? isPartialCoverage(cell(monthId(year, month))!)
                      : false,
                    'is-missing': !cell(monthId(year, month)),
                  }"
                  :style="cellStyle(cell(monthId(year, month)))"
                  :data-cell="monthId(year, month)"
                  :aria-label="ariaLabel(cell(monthId(year, month)), year, month)"
                  :aria-pressed="selected === monthId(year, month)"
                  @mouseenter="onCellEnter(monthId(year, month), $event)"
                  @mouseleave="onCellLeave"
                  @focus="onCellEnter(monthId(year, month), $event)"
                  @blur="onCellLeave"
                  @click="cell(monthId(year, month)) && onCellClick(monthId(year, month), $event)"
                >
                  <span
                    class="cell-dot"
                    v-if="cell(monthId(year, month)) && isPartialCoverage(cell(monthId(year, month))!)"
                  ></span>
                </button>
              </template>
            </template>
          </div>
        </div>

        <!-- Popover Flottant compact sans ascenseur, ancré sur la cellule active -->
        <transition name="popover-fade">
          <div
            v-if="showPopover && active"
            class="floating-popover"
            :class="{ 'is-pinned': isPinned, [`placement-${popoverPos.placement}`]: true }"
            :style="popoverStyle"
            role="dialog"
            aria-live="polite"
          >
            <!-- En-tête : Mois, statut et étiquette de mode -->
            <div class="popover-head">
              <div class="popover-title-row">
                <span class="popover-month">{{ monthNames[Number(active.month.slice(5, 7)) - 1] }} {{ active.month.slice(0, 4) }}</span>
                <span v-if="isPinned" class="popover-pin-badge">
                  📌 {{ t('Épinglé', 'Pinned') }}
                  <button type="button" class="popover-unpin-btn" @click.stop="unpin" :title="t('Libérer l’épinglage', 'Unpin')">✕</button>
                </span>
                <span v-else class="popover-live-badge">👁️ {{ t('Aperçu', 'Preview') }}</span>
              </div>
              <div class="popover-sub-row">
                <span class="popover-mode-tag">{{ activeModeDetails.shortName }}</span>
                <span class="popover-era-tag">{{ isHarmonizedPeriod ? '🔬 ' + t('Modèle M2', 'M2 Model') : '🛰️ VIIRS 375 m' }}</span>
              </div>
            </div>

            <!-- Chiffre principal & Anomaly Badge UNIQUE (pas de répétition) -->
            <div class="popover-stat-row">
              <div class="popover-main-metric">
                <span class="popover-number">{{ formatCount(activeValue) }}</span>
                <span class="popover-unit">
                  {{
                    scaleMode === 'harmonized'
                      ? t('points chauds (équiv. VIIRS)', 'hotspots (VIIRS equiv.)')
                      : t('détections brutes', 'raw detections')
                  }}
                </span>
              </div>
              <span
                v-if="active.anomaly_percent !== null"
                class="popover-anomaly-badge"
                :class="activeInterpretation.tone"
                :title="t('Écart à la normale historique sur 25 ans', 'Deviation from 25-yr normal')"
              >
                {{ formatPercent(active.anomaly_percent) }}
              </span>
            </div>

            <!-- Contexte d'écart vs normale 25 ans -->
            <div v-if="active.anomaly_percent !== null" class="popover-baseline-row">
              <span class="p-baseline-lbl">
                {{ t('Normale 25 ans :', '25-yr normal:') }} <strong>{{ formatCount(activeBaselineMedian) }}</strong>
              </span>
              <span class="p-baseline-gap" :class="(activeAnomalyDiff ?? 0) >= 0 ? 'text-fire' : 'text-cool'">
                ({{ (activeAnomalyDiff ?? 0) > 0 ? '+' : '' }}{{ formatCount(activeAnomalyDiff) }})
              </span>
            </div>

            <p class="popover-verdict" :class="activeInterpretation.tone">
              {{ activeInterpretation.text }}
            </p>

            <!-- Décomposition par type de feu : Végétation vs Torchères -->
            <div class="popover-breakdown">
              <div class="popover-bar">
                <div class="p-bar-veg" :style="{ width: `${monthVegShare}%` }"></div>
                <div class="p-bar-flare" :style="{ width: `${monthFlareShare}%` }"></div>
              </div>
              <div class="popover-types-grid">
                <div class="p-type-item veg">
                  <span class="p-dot veg"></span>
                  <span class="p-type-lbl">{{ t('Végétation', 'Vegetation') }}</span>
                  <span class="p-type-val">{{ formatCount(monthVegCount) }} ({{ monthVegShare }}%)</span>
                </div>
                <div class="p-type-item flare">
                  <span class="p-dot flare"></span>
                  <span class="p-type-lbl">{{ t('Torchères & industrie', 'Flaring & industry') }}</span>
                  <span class="p-type-val">{{ formatCount(monthFlareCount) }} ({{ monthFlareShare }}%)</span>
                </div>
              </div>
            </div>

            <!-- Pied de popover -->
            <div class="popover-foot">
              <span class="p-rank">{{ ordinal(rankInfo.rank) }} / {{ rankInfo.total }} {{ t('sur 25 ans', 'in 25 yrs') }}</span>
              <span class="p-instruction">
                {{ isPinned ? t('Cliquer pour libérer', 'Click to unpin') : t('Cliquer pour figer', 'Click cell to pin') }}
              </span>
            </div>
          </div>
        </transition>
      </div>

      <!-- Colonne Droite : Carte du Gabon synchronisée -->
      <div class="calendar-map-panel" aria-label="Carte provinciale du Gabon synchronisée">
        <div class="map-panel-header">
          <div>
            <div class="map-status-badge">
              <span class="pulse-dot"></span>
              <span class="map-status-text">{{ t('SYNCHRONISÉ AU CALENDRIER', 'SYNCHRONIZED WITH CALENDAR') }}</span>
            </div>
            <h3 class="map-panel-title">
              {{ monthNames[Number(activeMonth.slice(5, 7)) - 1] }} {{ activeMonth.slice(0, 4) }}
            </h3>
            <p class="map-panel-subtitle">
              {{ activeModeDetails.shortName }} · {{ formatCount(activeMonthTotalFires) }}
              {{ scaleMode === 'harmonized' ? t('points chauds (équiv. VIIRS)', 'hotspots (VIIRS equiv.)') : t('détections provinciales', 'provincial detections') }}
            </p>
          </div>
          <span class="map-badge-mode">{{ calendarModeLabel }}</span>
        </div>

        <!-- Carte SVG interactive du Gabon -->
        <div class="map-svg-container">
          <svg
            viewBox="0 0 360 410"
            class="gabon-svg-map"
            role="img"
            :aria-label="t('Carte du Gabon et intensité provinciale des feux', 'Gabon map and provincial fire intensity')"
          >
            <!-- Décor océan Atlantique à l'ouest -->
            <g class="map-ocean-decor" aria-hidden="true">
              <text x="16" y="270" class="ocean-text" transform="rotate(-90, 16, 270)">
                OCÉAN ATLANTIQUE
              </text>
            </g>

            <!-- Tracé des 9 provinces du Gabon -->
            <g class="provinces-group">
              <path
                v-for="prov in provincesList"
                :key="prov.code"
                :d="prov.d"
                :fill="getProvinceFill(prov.code)"
                :stroke="hoveredProvince === prov.code ? '#ffb347' : 'rgba(255, 255, 255, 0.22)'"
                :stroke-width="hoveredProvince === prov.code ? 2.5 : 1"
                class="province-path"
                :class="{ 'is-hovered': hoveredProvince === prov.code }"
                @mouseenter="hoveredProvince = prov.code"
                @mouseleave="hoveredProvince = null"
              >
                <title>{{ prov.name }} : {{ formatCount(getProvinceCount(prov.code)) }} {{ t('points chauds', 'hotspots') }}</title>
              </path>
            </g>

            <!-- Points chauds distribués dans les provinces selon leur type -->
            <g class="province-hotspot-dots" aria-hidden="true">
              <circle
                v-for="dot in mapHotspotState.dots"
                :key="dot.id"
                :cx="dot.x"
                :cy="dot.y"
                r="1.75"
                :fill="dot.color"
                class="hotspot-dot"
                :class="{
                  'is-dimmed': hoveredProvince !== null && hoveredProvince !== dot.province,
                  'is-highlighted': hoveredProvince === dot.province,
                }"
              />
            </g>

            <!-- Beacons d'activité au centre des provinces -->
            <g class="province-markers" aria-hidden="true">
              <template v-for="prov in provincesList" :key="`beacon-${prov.code}`">
                <!-- Beacon spécial pulsant sur la province #1 du mois -->
                <g
                  v-if="topProvince && topProvince.code === prov.code && topProvince.count > 0"
                  class="top-beacon-group"
                  :transform="`translate(${prov.center[0]}, ${prov.center[1]})`"
                >
                  <circle r="14" class="beacon-pulse-ring" />
                  <circle r="7" class="beacon-core-ring" />
                  <circle r="3.5" class="beacon-dot" />
                </g>
                <!-- Label court de la province -->
                <text
                  :x="prov.center[0]"
                  :y="prov.center[1] + 3"
                  class="province-label-text"
                  :class="{ 'label-top': topProvince?.code === prov.code }"
                >
                  {{ getProvinceAbbrev(prov.name) }}
                </text>
              </template>
            </g>
          </svg>

          <!-- Infobulle interactive survol province -->
          <div v-if="hoveredProvinceData" class="province-hover-card">
            <span class="phc-name">{{ hoveredProvinceData.name }}</span>
            <span class="phc-val">{{ formatCount(hoveredProvinceData.count) }} {{ t('feux', 'fires') }}</span>
            <span class="phc-pct">({{ hoveredProvinceData.share }}% {{ t('du Gabon', 'of Gabon') }})</span>
            <span v-if="calendarMode === 'anomalies' && hoveredProvinceData.anomaly !== null" class="phc-anom" :class="hoveredProvinceData.anomaly >= 0 ? 'text-fire' : 'text-cool'">
              {{ hoveredProvinceData.anomaly > 0 ? '+' : '' }}{{ hoveredProvinceData.anomaly }}%
            </span>
          </div>
        </div>

        <!-- Légende des points chauds par type -->
        <div v-if="mapHotspotState.dots.length > 0" class="map-dots-legend">
          <div class="map-dots-items">
            <span v-if="mapHotspotState.vegShown > 0" class="map-dot-chip">
              <span class="p-dot veg"></span>
              <span>{{ t('Végétation', 'Vegetation') }}</span>
            </span>
            <span v-if="mapHotspotState.flareShown > 0" class="map-dot-chip">
              <span class="p-dot flare"></span>
              <span>{{ t('Torchères & écartées', 'Flaring & excluded') }}</span>
            </span>
          </div>
          <span class="map-dots-scale">
            {{
              mapHotspotState.ratioPerDot > 1
                ? t(`1 pt ≈ ${mapHotspotState.ratioPerDot} détections`, `1 pt ≈ ${mapHotspotState.ratioPerDot} detections`)
                : `${formatCount(mapHotspotState.dots.length)} ${t('pts (1:1)', 'pts (1:1)')}`
            }}
          </span>
        </div>

        <!-- Mini légende thermique -->
        <div class="map-legend-row">
          <span class="map-legend-lbl">0</span>
          <div class="map-legend-gradient" :style="mapLegendGradientStyle"></div>
          <span class="map-legend-lbl">{{ formatCount(maxProvinceMonthCount) }} max</span>
        </div>

        <!-- Classement des provinces les plus actives du mois -->
        <div class="map-leaderboard">
          <div class="leaderboard-head">
            <span class="lb-title">{{ t('Provinces les plus actives ce mois', 'Most active provinces this month') }}</span>
            <span class="lb-period">{{ monthNames[Number(activeMonth.slice(5, 7)) - 1] }} {{ activeMonth.slice(0, 4) }}</span>
          </div>

          <div class="leaderboard-list">
            <div
              v-for="(item, idx) in topProvincesList"
              :key="item.code"
              class="lb-item"
              :class="{ 'is-hovered': hoveredProvince === item.code }"
              @mouseenter="hoveredProvince = item.code"
              @mouseleave="hoveredProvince = null"
            >
              <span class="lb-rank">#{{ idx + 1 }}</span>
              <span class="lb-name">{{ item.name }}</span>
              <div class="lb-bar-wrap">
                <div class="lb-bar-fill" :style="{ width: `${item.share}%`, background: getProvinceFill(item.code) }"></div>
              </div>
              <span class="lb-count">{{ formatCount(item.count) }}</span>
              <span class="lb-share">{{ item.share }}%</span>
            </div>
          </div>
        </div>

        <p class="map-context-note">
          <i class="note-icon">💡</i>
          <span>{{ dynamicMapContextNote }}</span>
        </p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.calendar {
  width: 100%;
  display: grid;
  gap: 16px;
}

.calendar-modes {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.cal-mode-btn {
  padding: 9px 14px;
  border: 1px solid var(--line-strong);
  border-radius: 999px;
  background: rgba(244, 241, 232, 0.03);
  color: var(--muted);
  font-size: 0.8rem;
  font-weight: 500;
  cursor: pointer;
  transition:
    background 0.2s ease,
    border-color 0.2s ease,
    color 0.2s ease;
}

.cal-mode-btn:hover {
  color: var(--ink);
  border-color: var(--muted);
}

.cal-mode-btn.active {
  background: var(--ink);
  border-color: var(--ink);
  color: #05070b;
  font-weight: 600;
}

/* Bannière d'explication du filtre actif */
.filter-context-banner {
  padding: 12px 16px;
  border-radius: 10px;
  border: 1px solid rgba(255, 196, 107, 0.25);
  background: rgba(255, 196, 107, 0.05);
  display: flex;
  flex-direction: column;
  gap: 6px;
  transition: all 0.2s ease;
}

.filter-context-banner.anomalies {
  border-color: rgba(255, 90, 95, 0.3);
  background: rgba(255, 90, 95, 0.06);
}

.filter-context-banner.flare {
  border-color: rgba(34, 211, 238, 0.3);
  background: rgba(34, 211, 238, 0.05);
}

.filter-context-banner.all {
  border-color: rgba(244, 241, 232, 0.2);
  background: rgba(244, 241, 232, 0.04);
}

.filter-context-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 8px;
}

.filter-context-pill {
  font-size: 0.82rem;
  font-weight: 600;
  color: var(--ink);
}

.filter-context-count {
  font-family: var(--font-mono);
  font-size: 0.74rem;
  color: var(--gold);
}

.filter-context-desc {
  font-size: 0.77rem;
  line-height: 1.5;
  color: var(--muted);
  margin: 0;
}

/* Encart d'échelle en superposition */
.scale-superposition-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
  padding: 10px 14px;
  border-radius: 10px;
  background: rgba(14, 18, 27, 0.55);
  border: 1px solid var(--line);
}

.scale-label-group {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.scale-title {
  font-family: var(--font-mono);
  font-size: 0.74rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--ink);
}

.scale-subtitle {
  font-size: 0.72rem;
  color: var(--dim);
}

.scale-toggle-group {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.scale-toggle-btn {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  border-radius: 8px;
  border: 1px solid var(--line-strong);
  background: rgba(244, 241, 232, 0.03);
  color: var(--muted);
  font-size: 0.75rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
}

.scale-toggle-btn:hover {
  color: var(--ink);
  border-color: var(--muted);
}

.scale-toggle-btn.active {
  background: rgba(255, 196, 107, 0.12);
  border-color: var(--gold);
  color: var(--ink);
}

.toggle-indicator {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--line-strong);
  transition: background 0.2s ease;
}

.scale-toggle-btn.active .toggle-indicator {
  background: var(--gold);
  box-shadow: 0 0 6px var(--gold);
}

.toggle-badge-rec {
  padding: 1px 6px;
  border-radius: 4px;
  background: rgba(34, 197, 94, 0.16);
  border: 1px solid rgba(34, 197, 94, 0.35);
  color: #86efac;
  font-family: var(--font-mono);
  font-size: 0.65rem;
  font-weight: 600;
  text-transform: uppercase;
}

/* Alerte du mode brut */
.raw-alert-banner {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 10px 14px;
  border-radius: 8px;
  border-left: 3px solid #f59e0b;
  background: rgba(245, 158, 11, 0.08);
}

.alert-icon {
  font-size: 1rem;
  line-height: 1.2;
}

.raw-alert-banner p {
  margin: 0;
  font-size: 0.76rem;
  line-height: 1.5;
  color: #fde68a;
}

.scale-hint {
  font-weight: normal;
  text-transform: none;
  color: var(--dim);
}

.burner-callout {
  padding: 12px 16px;
  border-left: 3px solid var(--gold);
  border-radius: 0 10px 10px 0;
  background: rgba(255, 196, 107, 0.06);
}

.burner-callout strong {
  display: block;
  font-size: 0.84rem;
  color: var(--ink);
}

.burner-callout p {
  margin-top: 4px;
  font-size: 0.78rem;
  line-height: 1.55;
  color: var(--muted);
}

.calendar-top {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  justify-content: space-between;
  gap: 18px 24px;
}

.season-strip {
  flex: 1;
  min-width: 240px;
}

.season-caption {
  display: block;
  margin-bottom: 7px;
  font-family: var(--font-mono);
  font-size: 0.76rem;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: #cbd5e1;
}

.season-bars {
  display: grid;
  grid-template-columns: repeat(12, minmax(0, 1fr));
  gap: 4px;
  align-items: end;
  height: 64px;
}

.season-bar {
  position: relative;
  display: flex;
  flex-direction: column;
  justify-content: flex-end;
  gap: 5px;
  height: 100%;
  min-width: 0;
}

.season-bar i {
  display: block;
  width: 100%;
  min-height: 3px;
  border-radius: 2px 2px 0 0;
  background: rgba(244, 241, 232, 0.16);
}

.season-bar.main i {
  background: linear-gradient(180deg, #ffb347, #a32a19);
}

.season-bar.secondary i {
  background: linear-gradient(180deg, #ffc46b, #8b3e1b);
  opacity: 0.8;
}

.season-bar span {
  font-family: var(--font-mono);
  font-size: 0.8rem;
  font-weight: 500;
  text-align: center;
  color: #dce5f0;
}

.season-bar.main span {
  color: var(--gold);
  font-weight: 600;
}

.legend {
  flex: none;
  min-width: 245px;
}

.legend-scale {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 6px;
}

.legend-gradient {
  flex: 1;
  min-width: 100px;
  height: 10px;
  border-radius: 5px;
  border: 1px solid var(--line-strong);
  background: linear-gradient(90deg, rgb(247, 239, 226), rgb(236, 204, 162), rgb(219, 122, 59), rgb(163, 42, 25), rgb(42, 6, 6));
}

.legend-min,
.legend-max {
  font-family: var(--font-mono);
  font-size: 0.78rem;
  color: #dce5f0;
}

.anomaly-swatches {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 14px;
  margin-top: 6px;
  font-size: 0.78rem;
  color: #dce5f0;
}

.anomaly-swatches span {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.anomaly-swatches i {
  width: 12px;
  height: 12px;
  border-radius: 3px;
  border: 1px solid rgba(255, 255, 255, 0.2);
}

.calendar-layout {
  display: grid;
  grid-template-columns: minmax(0, 1.32fr) minmax(340px, 400px);
  gap: 24px;
  align-items: start;
  position: relative;
  z-index: 50;
}

.calendar-col-left {
  position: relative;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 16px;
  z-index: 60;
}

.calendar-scroll {
  overflow-x: auto;
  padding: 16px;
  border-radius: 14px;
  background: #f4ece0;
  border: 1px solid rgba(244, 241, 232, 0.35);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.65);
  scrollbar-width: thin;
}

.calendar-era-legend {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
  padding: 6px 10px;
  background: rgba(59, 42, 34, 0.08);
  border-radius: 6px;
}

.era-tag {
  font-family: var(--font-mono);
  font-size: 0.68rem;
  font-weight: 600;
}

.era-modis {
  color: #1e3a8a;
}

.era-viirs {
  color: #9a3412;
}

.calendar-grid {
  display: grid;
  grid-template-columns: 3.8rem repeat(12, minmax(0, 1fr));
  gap: 4px;
  min-width: 640px;
}

.grid-corner {
  height: 26px;
}

.month-head,
.year-head {
  font-family: var(--font-mono);
  font-size: 0.84rem;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: #362218;
}

.month-head {
  display: flex;
  align-items: flex-end;
  justify-content: center;
  height: 26px;
}

.year-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-right: 8px;
}

.year-text {
  font-size: 0.84rem;
}

.year-era-dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: rgba(59, 42, 34, 0.25);
}

.year-head.is-modis-era .year-era-dot {
  background: #2563eb;
}

.year-head.is-viirs-era .year-era-dot {
  background: #ea580c;
}

.cell {
  position: relative;
  aspect-ratio: 1.6;
  min-height: 22px;
  padding: 0;
  border: 1px solid rgba(59, 42, 34, 0.14);
  border-radius: 4px;
  cursor: pointer;
  transition:
    transform 0.2s var(--ease-out),
    box-shadow 0.2s ease,
    outline-color 0.2s ease;
}

.cell:hover,
.cell:focus-visible {
  transform: scale(1.12);
  z-index: 3;
  outline: 2px solid #2a0606;
  outline-offset: 1px;
}

.cell.is-active {
  outline: 2px solid #7c2d12;
  outline-offset: 1px;
}

.cell.is-selected {
  outline: 2.5px solid #120605;
  outline-offset: 2px;
  box-shadow: 0 0 0 4px #ffc46b;
  z-index: 4;
}

.cell.is-empty {
  background: transparent;
  border-color: transparent;
  cursor: default;
}

.cell.is-missing {
  border-style: dashed;
  border-color: rgba(59, 42, 34, 0.25);
}

.cell.is-partial::after {
  content: '';
  position: absolute;
  inset: 0;
  border-radius: inherit;
  background-image: repeating-linear-gradient(
    135deg,
    transparent 0 4px,
    rgba(42, 6, 6, 0.16) 4px 6px
  );
  pointer-events: none;
}

.cell-dot {
  position: absolute;
  top: 3px;
  right: 3px;
  width: 4px;
  height: 4px;
  border-radius: 50%;
  background: rgba(42, 6, 6, 0.5);
  pointer-events: none;
}

.detail {
  padding: 20px;
  position: sticky;
  top: 80px;
  max-height: calc(100vh - 100px);
  overflow-y: auto;
  scrollbar-width: thin;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.detail-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.detail-status-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 4px;
}

.detail-status-pill {
  padding: 2px 7px;
  border-radius: 999px;
  font-family: var(--font-mono);
  font-size: 0.66rem;
  font-weight: 500;
  background: rgba(244, 241, 232, 0.08);
  border: 1px solid var(--line);
  color: var(--muted);
}

.detail-status-pill.pinned {
  background: rgba(255, 196, 107, 0.15);
  border-color: var(--gold);
  color: var(--gold);
  font-weight: 600;
}

.detail-mode-pill {
  padding: 2px 7px;
  border-radius: 999px;
  font-family: var(--font-mono);
  font-size: 0.66rem;
  background: rgba(255, 255, 255, 0.05);
  color: var(--dim);
}

.detail-month {
  margin-top: 4px;
  font-family: var(--font-display);
  font-size: 1.7rem;
  font-weight: 400;
  line-height: 1;
}

.detail-year {
  margin-top: 3px;
  font-family: var(--font-mono);
  font-size: 0.78rem;
  color: var(--muted);
}

.anomaly-badge {
  display: inline-flex;
  align-items: center;
  padding: 5px 10px;
  border-radius: 999px;
  background: rgba(255, 196, 107, 0.14);
  border: 1px solid rgba(255, 196, 107, 0.4);
  color: var(--gold);
  font-family: var(--font-mono);
  font-size: 0.72rem;
  font-weight: 600;
  white-space: nowrap;
}

.anomaly-badge.negative {
  background: rgba(96, 165, 250, 0.14);
  border-color: rgba(96, 165, 250, 0.35);
  color: #93c5fd;
}

.anomaly-badge.extreme {
  background: rgba(255, 90, 95, 0.18);
  border-color: rgba(255, 90, 95, 0.45);
  color: #fda4af;
}

.anomaly-badge.warm {
  background: rgba(255, 122, 61, 0.18);
  border-color: rgba(255, 122, 61, 0.45);
  color: #fed7aa;
}

.detail-value {
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin: 0;
}

.detail-unit {
  font-size: 0.78rem;
  color: var(--muted);
}

/* Blocs généraux de détails */
.detail-block {
  padding: 14px;
  border-radius: 12px;
  background: rgba(244, 241, 232, 0.03);
  border: 1px solid var(--line);
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.block-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.block-title {
  font-family: var(--font-mono);
  font-size: 0.72rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--ink);
}

.block-subtitle {
  font-family: var(--font-mono);
  font-size: 0.68rem;
  color: var(--dim);
}

.block-badge {
  padding: 2px 6px;
  border-radius: 4px;
  font-family: var(--font-mono);
  font-size: 0.7rem;
  font-weight: 600;
}

.block-badge.is-high {
  background: rgba(239, 68, 68, 0.18);
  border: 1px solid rgba(239, 68, 68, 0.35);
  color: #fca5a5;
}

.block-badge.is-calm {
  background: rgba(59, 130, 246, 0.15);
  border: 1px solid rgba(59, 130, 246, 0.3);
  color: #93c5fd;
}

.anomaly-benchmark-text {
  font-size: 0.73rem;
  line-height: 1.45;
  color: var(--muted);
  margin: 0;
}

.anomaly-benchmark-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 6px;
  padding: 8px;
  border-radius: 8px;
  background: rgba(0, 0, 0, 0.2);
  border: 1px solid rgba(244, 241, 232, 0.05);
}

.anom-stat-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  text-align: center;
}

.anom-stat-lbl {
  font-family: var(--font-mono);
  font-size: 0.58rem;
  text-transform: uppercase;
  color: var(--dim);
}

.anom-stat-num {
  font-family: var(--font-mono);
  font-size: 0.82rem;
  font-weight: 600;
  color: var(--ink);
}

.text-fire {
  color: #f87171 !important;
}

.text-cool {
  color: #38bdf8 !important;
}

/* Styles Décomposition par type de feu */
.breakdown-block {
  border-color: rgba(255, 180, 100, 0.15);
  background: rgba(255, 180, 100, 0.02);
}

.type-ratio-bar {
  display: flex;
  height: 8px;
  width: 100%;
  border-radius: 4px;
  overflow: hidden;
  background: rgba(255, 255, 255, 0.06);
}

.ratio-segment.veg {
  background: linear-gradient(90deg, #f97316, #ef4444);
  transition: width 0.3s ease;
}

.ratio-segment.flare {
  background: linear-gradient(90deg, #0ea5e9, #6366f1);
  transition: width 0.3s ease;
}

.type-rows {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.type-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
  padding: 6px 8px;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.02);
}

.type-row.total {
  border-top: 1px solid var(--line);
  padding-top: 8px;
  background: transparent;
}

.type-info {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  flex: 1;
}

.type-bullet {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  margin-top: 4px;
  flex-shrink: 0;
}

.type-bullet.veg {
  background: #f97316;
  box-shadow: 0 0 6px rgba(249, 115, 22, 0.6);
}

.type-bullet.flare {
  background: #38bdf8;
  box-shadow: 0 0 6px rgba(56, 189, 248, 0.6);
}

.type-bullet.total {
  background: var(--muted);
}

.type-name-line {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.type-name {
  font-size: 0.76rem;
  font-weight: 600;
  color: var(--ink);
}

.type-badge-veg {
  padding: 0 5px;
  border-radius: 3px;
  background: rgba(249, 115, 22, 0.15);
  color: #fb923c;
  font-family: var(--font-mono);
  font-size: 0.65rem;
  font-weight: 600;
}

.type-badge-flare {
  padding: 0 5px;
  border-radius: 3px;
  background: rgba(56, 189, 248, 0.15);
  color: #7dd3fc;
  font-family: var(--font-mono);
  font-size: 0.65rem;
  font-weight: 600;
}

.type-desc {
  margin: 2px 0 0;
  font-size: 0.68rem;
  line-height: 1.35;
  color: var(--dim);
}

.type-numbers {
  text-align: right;
  flex-shrink: 0;
}

.type-count {
  font-family: var(--font-mono);
  font-size: 0.82rem;
  font-weight: 600;
  color: var(--ink);
}

.total-val {
  color: var(--gold);
}

/* Styles Harmonisation */
.harmonization-block.era-model {
  border-color: rgba(99, 102, 241, 0.25);
  background: rgba(99, 102, 241, 0.04);
}

.harmonization-block.era-viirs {
  border-color: rgba(34, 197, 94, 0.25);
  background: rgba(34, 197, 94, 0.04);
}

.harm-era-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-family: var(--font-mono);
  font-size: 0.72rem;
  font-weight: 600;
  color: var(--ink);
}

.harm-sensor-tag {
  padding: 1px 6px;
  border-radius: 4px;
  background: rgba(255, 255, 255, 0.07);
  font-family: var(--font-mono);
  font-size: 0.65rem;
  color: var(--muted);
}

.harm-body-text {
  margin: 0;
  font-size: 0.72rem;
  line-height: 1.45;
  color: var(--muted);
}

.sensor-raw-pills {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 4px;
}

.sensor-pill {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 7px;
  border-radius: 6px;
  background: rgba(0, 0, 0, 0.2);
  border: 1px solid rgba(255, 255, 255, 0.06);
  font-family: var(--font-mono);
  font-size: 0.68rem;
}

.sp-name {
  color: var(--dim);
}

.sp-val {
  color: var(--ink);
  font-weight: 600;
}

.detail-verdict {
  margin-top: 6px;
  padding: 8px 10px;
  border-radius: 8px;
  font-size: 0.76rem;
  font-weight: 500;
  background: rgba(244, 241, 232, 0.05);
  color: var(--ink);
}

.detail-verdict.extreme {
  background: rgba(255, 90, 95, 0.14);
  color: #fecdd3;
}

.detail-verdict.warm {
  background: rgba(255, 122, 61, 0.14);
  color: #fed7aa;
}

.detail-verdict.cool {
  background: rgba(34, 211, 238, 0.12);
  color: #a5f3fc;
}

.detail-bar {
  position: relative;
  height: 7px;
  margin-top: 14px;
  border-radius: 4px;
  background: rgba(244, 241, 232, 0.1);
}

.detail-bar-value {
  position: absolute;
  inset: 0 auto 0 0;
  border-radius: 4px;
  background: var(--grad-heat);
}

.detail-bar-median {
  position: absolute;
  top: -3px;
  width: 2.5px;
  height: 13px;
  background: var(--teal);
  box-shadow: 0 0 8px rgba(94, 234, 212, 0.7);
}

.detail-bar-labels {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-top: 7px;
  font-family: var(--font-mono);
  font-size: 0.6rem;
  color: var(--muted);
}

.detail-bar-labels span {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}

.label-swatch {
  display: inline-block;
  width: 12px;
  height: 3px;
  border-radius: 2px;
}

.label-swatch.value {
  background: var(--grad-heat);
}

.label-swatch.median {
  width: 2.5px;
  height: 9px;
  border-radius: 0;
  background: var(--teal);
}

.detail-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px 14px;
  margin: 18px 0 0;
  padding-top: 14px;
  border-top: 1px solid var(--line);
}

.detail-grid dt {
  font-family: var(--font-mono);
  font-size: 0.56rem;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--dim);
}

.detail-grid dd {
  margin: 3px 0 0;
  font-size: 0.8rem;
  color: var(--ink);
}

.detail-note {
  margin-top: 16px;
  font-size: 0.72rem;
  color: var(--dim);
}

@media (max-width: 1020px) {
  .calendar-layout {
    grid-template-columns: minmax(0, 1fr);
  }
  .detail {
    position: static;
  }
}

@media (max-width: 700px) {
  .calendar-scroll {
    padding: 10px;
  }
  .calendar-grid {
    min-width: 0;
    grid-template-columns: 2.8rem repeat(12, minmax(0, 1fr));
    gap: 2px;
  }
  .month-head,
  .year-head {
    font-size: 0.7rem;
    letter-spacing: 0.02em;
  }
  .cell {
    border-radius: 3px;
    min-height: 18px;
  }
}

/* =====================================================================
   POPOVER FLOTTANT (SANS ASCENSEUR / ULTRA ACCESSIBLE)
   ===================================================================== */
.floating-popover {
  position: absolute;
  z-index: 9999;
  width: 320px;
  background: rgba(14, 20, 30, 0.98);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  border: 1px solid rgba(255, 140, 50, 0.38);
  box-shadow: 0 16px 36px rgba(0, 0, 0, 0.6), 0 0 20px rgba(255, 120, 40, 0.15);
  border-radius: 14px;
  padding: 14px 16px;
  display: flex;
  flex-direction: column;
  gap: 9px;
  transition: transform 0.18s cubic-bezier(0.16, 1, 0.3, 1), opacity 0.18s ease;
  overflow: visible;
}

.floating-popover.is-pinned {
  border-color: rgba(255, 175, 75, 0.75);
  box-shadow: 0 18px 42px rgba(0, 0, 0, 0.7), 0 0 28px rgba(255, 140, 40, 0.28);
}

.popover-fade-enter-active,
.popover-fade-leave-active {
  transition: opacity 0.15s ease, transform 0.15s ease;
}
.popover-fade-enter-from,
.popover-fade-leave-to {
  opacity: 0;
  transform: scale(0.96) translateY(4px);
}

.popover-head {
  display: flex;
  flex-direction: column;
  gap: 4px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  padding-bottom: 8px;
}

.popover-title-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.popover-month {
  font-family: var(--font-display, inherit);
  font-size: 1.15rem;
  font-weight: 700;
  color: #fff;
}

.popover-pin-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-family: var(--font-mono, monospace);
  font-size: 0.66rem;
  font-weight: 700;
  color: #ffb852;
  background: rgba(255, 184, 82, 0.15);
  border: 1px solid rgba(255, 184, 82, 0.35);
  padding: 2px 7px;
  border-radius: 999px;
}

.popover-unpin-btn {
  background: transparent;
  border: none;
  color: #ffb852;
  cursor: pointer;
  padding: 0 2px;
  font-size: 0.8rem;
  line-height: 1;
}

.popover-unpin-btn:hover {
  color: #fff;
}

.popover-live-badge {
  font-family: var(--font-mono, monospace);
  font-size: 0.65rem;
  color: var(--dim, #8898aa);
  background: rgba(255, 255, 255, 0.06);
  padding: 2px 7px;
  border-radius: 999px;
}

.popover-sub-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 0.68rem;
}

.popover-mode-tag {
  color: #ff9e42;
  font-weight: 600;
}

.popover-era-tag {
  font-family: var(--font-mono, monospace);
  color: var(--dim, #8898aa);
}

.popover-stat-row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 10px;
}

.popover-main-metric {
  display: flex;
  align-items: baseline;
  gap: 6px;
}

.popover-number {
  font-family: var(--font-display, inherit);
  font-size: 1.85rem;
  font-weight: 700;
  line-height: 1;
  color: #fff;
  letter-spacing: -0.02em;
}

.popover-unit {
  font-size: 0.74rem;
  color: var(--dim, #9aa6b8);
}

.popover-anomaly-badge {
  padding: 3px 8px;
  border-radius: 999px;
  font-family: var(--font-mono, monospace);
  font-size: 0.78rem;
  font-weight: 700;
}

.popover-anomaly-badge.extreme {
  background: rgba(220, 38, 38, 0.25);
  border: 1px solid rgba(239, 68, 68, 0.6);
  color: #fca5a5;
}

.popover-anomaly-badge.warm {
  background: rgba(234, 88, 12, 0.25);
  border: 1px solid rgba(249, 115, 22, 0.6);
  color: #fdba74;
}

.popover-anomaly-badge.cool {
  background: rgba(14, 165, 233, 0.25);
  border: 1px solid rgba(56, 189, 248, 0.6);
  color: #7dd3fc;
}

.popover-baseline-row {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 0.74rem;
  color: var(--dim, #9aa6b8);
}

.p-baseline-gap {
  font-weight: 700;
}

.popover-verdict {
  margin: 0;
  font-size: 0.74rem;
  line-height: 1.35;
  padding: 6px 9px;
  border-radius: 6px;
}

.popover-verdict.extreme {
  background: rgba(220, 38, 38, 0.12);
  border-left: 3px solid #ef4444;
  color: #fecaca;
}

.popover-verdict.warm {
  background: rgba(234, 88, 12, 0.12);
  border-left: 3px solid #f97316;
  color: #fed7aa;
}

.popover-verdict.cool {
  background: rgba(14, 165, 233, 0.12);
  border-left: 3px solid #38bdf8;
  color: #bae6fd;
}

.popover-breakdown {
  display: flex;
  flex-direction: column;
  gap: 6px;
  background: rgba(255, 255, 255, 0.03);
  border-radius: 8px;
  padding: 8px 10px;
}

.popover-bar {
  display: flex;
  height: 5px;
  border-radius: 3px;
  overflow: hidden;
  background: rgba(255, 255, 255, 0.08);
}

.p-bar-veg {
  background: #ff7828;
  transition: width 0.3s ease;
}

.p-bar-flare {
  background: #38bdf8;
  transition: width 0.3s ease;
}

.popover-types-grid {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.p-type-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 0.72rem;
}

.p-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}
.p-dot.veg { background: #ff7828; }
.p-dot.flare { background: #38bdf8; }

.p-type-lbl {
  color: var(--text-high, #fff);
  flex: 1;
}

.p-type-val {
  font-family: var(--font-mono, monospace);
  color: var(--dim, #9aa6b8);
  font-size: 0.7rem;
}

.popover-foot {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-family: var(--font-mono, monospace);
  font-size: 0.66rem;
  color: var(--dim, #7e8c9f);
  border-top: 1px solid rgba(255, 255, 255, 0.06);
  padding-top: 6px;
}

/* =====================================================================
   PANEL CARTE DU GABON SYNCHRONISÉE
   ===================================================================== */
.calendar-map-panel {
  display: flex;
  flex-direction: column;
  gap: 13px;
  background: rgba(14, 20, 30, 0.88);
  border: 1px solid var(--line-subtle, rgba(255, 255, 255, 0.12));
  border-radius: 16px;
  padding: 18px;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.05), 0 12px 32px rgba(0, 0, 0, 0.45);
  position: sticky;
  top: 80px;
}

.map-panel-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 10px;
}

.map-status-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-family: var(--font-mono, monospace);
  font-size: 0.65rem;
  letter-spacing: 0.07em;
  color: #ff9e42;
  text-transform: uppercase;
  margin-bottom: 2px;
}

.pulse-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #ff7828;
  box-shadow: 0 0 8px #ff7828;
  animation: pulseDot 1.6s infinite ease-in-out;
}

@keyframes pulseDot {
  0% { transform: scale(0.9); opacity: 0.8; }
  50% { transform: scale(1.4); opacity: 1; box-shadow: 0 0 12px #ff9e42; }
  100% { transform: scale(0.9); opacity: 0.8; }
}

.map-panel-title {
  font-size: 1.25rem;
  font-weight: 700;
  color: var(--text-high, #fff);
  margin: 0;
  line-height: 1.2;
}

.map-panel-subtitle {
  font-size: 0.76rem;
  color: var(--dim, #9aa6b8);
  margin: 2px 0 0;
}

.map-badge-mode {
  padding: 4px 10px;
  border-radius: 999px;
  font-size: 0.68rem;
  font-weight: 600;
  background: rgba(255, 120, 40, 0.12);
  color: #ff9e42;
  border: 1px solid rgba(255, 120, 40, 0.28);
  white-space: nowrap;
}

.map-svg-container {
  position: relative;
  width: 100%;
  aspect-ratio: 360 / 390;
  background: radial-gradient(circle at 65% 55%, rgba(25, 38, 56, 0.45) 0%, rgba(7, 11, 18, 0.85) 100%);
  border-radius: 12px;
  overflow: hidden;
  border: 1px solid rgba(255, 255, 255, 0.07);
  display: flex;
  align-items: center;
  justify-content: center;
}

.gabon-svg-map {
  width: 100%;
  height: 100%;
  display: block;
}

.province-path {
  cursor: pointer;
  transition: fill 0.22s cubic-bezier(0.16, 1, 0.3, 1), stroke 0.18s ease, stroke-width 0.18s ease, filter 0.18s ease;
}

.province-path:hover,
.province-path.is-hovered {
  stroke: #ffca66 !important;
  stroke-width: 2.5px !important;
  filter: drop-shadow(0 0 6px rgba(255, 140, 0, 0.65));
}

.ocean-text {
  font-size: 8px;
  font-family: var(--font-mono, monospace);
  letter-spacing: 0.2em;
  fill: rgba(140, 180, 220, 0.2);
  font-weight: 600;
}

.province-label-text {
  font-family: var(--font-mono, monospace);
  font-size: 8px;
  font-weight: 700;
  fill: rgba(255, 255, 255, 0.82);
  text-anchor: middle;
  dominant-baseline: middle;
  pointer-events: none;
  text-shadow: 0 1px 3px rgba(0, 0, 0, 0.95);
}

.province-label-text.label-top {
  fill: #fff;
  font-weight: 800;
  text-shadow: 0 0 6px rgba(255, 100, 20, 0.9), 0 1px 3px rgba(0, 0, 0, 1);
}

.province-hotspot-dots {
  pointer-events: none;
}

.hotspot-dot {
  stroke: rgba(6, 10, 18, 0.72);
  stroke-width: 0.55;
  opacity: 0.92;
  transition: opacity 0.15s ease;
}

.hotspot-dot.is-dimmed {
  opacity: 0.22;
}

.hotspot-dot.is-highlighted {
  opacity: 1;
  stroke: #ffffff;
  stroke-width: 0.55;
}

.map-dots-legend {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  flex-wrap: wrap;
  font-size: 0.69rem;
  color: var(--dim, #9aa6b8);
  padding: 4px 8px;
  border-radius: 7px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.06);
}

.map-dots-items {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.map-dot-chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  color: var(--text-high, #e6edf7);
  font-weight: 500;
}

.map-dots-scale {
  font-family: var(--font-mono, monospace);
  font-size: 0.65rem;
  color: var(--dim, #8898aa);
}

.top-beacon-group {
  pointer-events: none;
}

.beacon-pulse-ring {
  fill: none;
  stroke: #ff7828;
  stroke-width: 1.5;
  animation: beaconPulse 1.8s infinite cubic-bezier(0.2, 0.6, 0.35, 1);
  transform-origin: center;
}

.beacon-core-ring {
  fill: rgba(255, 120, 40, 0.35);
  stroke: #ffaa55;
  stroke-width: 1;
}

.beacon-dot {
  fill: #fff;
}

@keyframes beaconPulse {
  0% { transform: scale(0.4); opacity: 1; }
  70% { transform: scale(2.2); opacity: 0.1; }
  100% { transform: scale(2.6); opacity: 0; }
}

.province-hover-card {
  position: absolute;
  bottom: 8px;
  left: 8px;
  right: 8px;
  background: rgba(10, 15, 24, 0.92);
  backdrop-filter: blur(8px);
  border: 1px solid rgba(255, 140, 50, 0.45);
  border-radius: 8px;
  padding: 5px 10px;
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 0.74rem;
  z-index: 10;
  pointer-events: none;
}

.phc-name {
  font-weight: 700;
  color: #fff;
}
.phc-val {
  color: #ff9e42;
  font-weight: 600;
}
.phc-pct {
  color: var(--dim, #8898aa);
}
.phc-anom {
  margin-left: auto;
  font-weight: 700;
  font-size: 0.72rem;
}

.map-legend-row {
  display: flex;
  align-items: center;
  gap: 10px;
  font-family: var(--font-mono, monospace);
  font-size: 0.68rem;
  color: var(--dim, #8898aa);
}

.map-legend-gradient {
  flex: 1;
  height: 7px;
  border-radius: 4px;
  border: 1px solid rgba(255, 255, 255, 0.1);
}

.map-leaderboard {
  display: flex;
  flex-direction: column;
  gap: 6px;
  background: rgba(255, 255, 255, 0.02);
  border-radius: 10px;
  padding: 9px 11px;
  border: 1px solid rgba(255, 255, 255, 0.05);
}

.leaderboard-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 0.7rem;
  font-weight: 600;
  color: var(--dim, #8898aa);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.leaderboard-list {
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.lb-item {
  display: grid;
  grid-template-columns: 20px 88px 1fr 48px 34px;
  align-items: center;
  gap: 6px;
  font-size: 0.74rem;
  padding: 3px 6px;
  border-radius: 6px;
  cursor: pointer;
  transition: background 0.15s ease;
}

.lb-item:hover,
.lb-item.is-hovered {
  background: rgba(255, 140, 50, 0.12);
}

.lb-rank {
  color: var(--dim, #6e7d91);
  font-weight: 700;
  font-size: 0.66rem;
}

.lb-name {
  color: var(--text-high, #fff);
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.lb-bar-wrap {
  height: 5px;
  background: rgba(255, 255, 255, 0.06);
  border-radius: 3px;
  overflow: hidden;
}

.lb-bar-fill {
  height: 100%;
  border-radius: 3px;
  transition: width 0.3s cubic-bezier(0.16, 1, 0.3, 1);
}

.lb-count {
  font-family: var(--font-mono, monospace);
  font-weight: 700;
  color: #ff9e42;
  text-align: right;
  font-size: 0.7rem;
}

.lb-share {
  font-family: var(--font-mono, monospace);
  color: var(--dim, #8898aa);
  font-size: 0.66rem;
  text-align: right;
}

.map-context-note {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  font-size: 0.72rem;
  line-height: 1.4;
  color: var(--dim, #9aa6b8);
  margin: 0;
  padding: 8px 10px;
  background: rgba(255, 140, 50, 0.06);
  border-radius: 8px;
  border: 1px solid rgba(255, 140, 50, 0.14);
}

.note-icon {
  font-style: normal;
  font-size: 0.85rem;
  flex-shrink: 0;
}

@media (max-width: 1060px) {
  .calendar-layout {
    grid-template-columns: minmax(0, 1fr);
  }
  .calendar-map-panel {
    position: static;
  }
  .floating-popover {
    position: fixed;
    bottom: 20px;
    left: 50% !important;
    transform: translateX(-50%);
    width: min(92vw, 360px);
    z-index: 100;
  }
}

</style>
