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

const activeMonth = computed(() => selected.value ?? hovered.value ?? '2024-08')
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

function select(point: CalendarPoint) {
  selected.value = selected.value === point.month ? null : point.month
}

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
  if (props.reducedMotion) return
  await nextTick()
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
                @mouseenter="hovered = monthId(year, month)"
                @mouseleave="hovered = null"
                @focus="hovered = monthId(year, month)"
                @blur="hovered = null"
                @click="cell(monthId(year, month)) && select(cell(monthId(year, month))!)"
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

      <aside class="detail panel" aria-live="polite">
        <!-- En-tête : Mois sélectionné & statut -->
        <div class="detail-head">
          <div>
            <div class="detail-status-row">
              <span class="detail-status-pill" :class="{ pinned: isPinned }">
                {{ isPinned ? t('📌 Mois épinglé', '📌 Pinned month') : t('👁️ Survol en direct', '👁️ Live preview') }}
              </span>
              <span class="detail-mode-pill">{{ activeModeDetails.shortName }}</span>
            </div>
            <h3 class="detail-month">{{ monthNames[Number(active.month.slice(5, 7)) - 1] }}</h3>
            <p class="detail-year">{{ active.month.slice(0, 4) }}</p>
          </div>
          <span
            v-if="active.anomaly_percent !== null"
            class="anomaly-badge"
            :class="{
              negative: active.anomaly_percent < 0,
              extreme: active.anomaly_percent > 50,
              warm: active.anomaly_percent >= 25 && active.anomaly_percent <= 50,
            }"
            :title="t('Écart par rapport à la médiane historique de ce mois', 'Deviation from the historical median of this month')"
          >
            {{ formatPercent(active.anomaly_percent) }}
          </span>
        </div>

        <!-- Valeur principale affichée -->
        <div class="detail-value">
          <span class="stat">{{ formatCount(activeValue) }}</span>
          <span class="detail-unit">
            {{
              scaleMode === 'harmonized'
                ? t('points chauds (échelle unifiée équiv. VIIRS 375 m)', 'hotspots (unified VIIRS 375m scale)')
                : t('détections brutes satellites (non harmonisées)', 'raw satellite detections (unharmonized)')
            }}
          </span>
        </div>

        <!-- BLOC 1 : Documentation pédagogique du pourcentage d'anomalie -->
        <div v-if="active.anomaly_percent !== null" class="detail-block anomaly-doc-block">
          <div class="block-header">
            <span class="block-title">{{ t('Écart à la normale saisonnière', 'Seasonal baseline deviation') }}</span>
            <span class="block-badge" :class="{ 'is-high': active.anomaly_percent > 25, 'is-calm': active.anomaly_percent < 0 }">
              {{ formatPercent(active.anomaly_percent) }}
            </span>
          </div>

          <p class="anomaly-benchmark-text">
            {{
              t(
                `Ce pourcentage compare l’activité d’${monthNames[Number(active.month.slice(5, 7)) - 1]} ${active.month.slice(0, 4)} à la normale historique de tous les mois de ${monthNames[Number(active.month.slice(5, 7)) - 1]} sur 25 ans (médiane 2001–2025).`,
                `This percentage compares ${monthNames[Number(active.month.slice(5, 7)) - 1]} ${active.month.slice(0, 4)} activity to the 25-year historical normal for all ${monthNames[Number(active.month.slice(5, 7)) - 1]}s (2001–2025 median).`,
              )
            }}
          </p>

          <div class="anomaly-benchmark-grid">
            <div class="anom-stat-item">
              <span class="anom-stat-lbl">{{ t('Ce mois-ci', 'This month') }}</span>
              <span class="anom-stat-num">{{ formatCount(activeHarmonizedValue) }}</span>
            </div>
            <div class="anom-stat-item">
              <span class="anom-stat-lbl">{{ t('Normale 25 ans', '25-yr normal') }}</span>
              <span class="anom-stat-num">{{ formatCount(activeBaselineMedian) }}</span>
            </div>
            <div class="anom-stat-item">
              <span class="anom-stat-lbl">{{ t('Écart net', 'Net gap') }}</span>
              <span class="anom-stat-num" :class="(activeAnomalyDiff ?? 0) >= 0 ? 'text-fire' : 'text-cool'">
                {{ (activeAnomalyDiff ?? 0) > 0 ? '+' : '' }}{{ formatCount(activeAnomalyDiff) }}
              </span>
            </div>
          </div>

          <p class="detail-verdict" :class="activeInterpretation.tone">
            {{ activeInterpretation.text }}
          </p>

          <div class="detail-bar" aria-hidden="true">
            <i
              class="detail-bar-value"
              :style="{ width: `${Math.min(100, ((active.harmonized_value ?? 0) / maxValue) * 100)}%` }"
            ></i>
            <i
              class="detail-bar-median"
              :style="{ left: `${Math.min(100, ((active.baseline_median ?? 0) / maxValue) * 100)}%` }"
            ></i>
          </div>
          <div class="detail-bar-labels">
            <span><i class="label-swatch value"></i>{{ t('ce mois', 'this month') }}</span>
            <span><i class="label-swatch median"></i>{{ t('normale 2001–2025 :', '2001–2025 normal:') }} {{ formatCount(active.baseline_median) }}</span>
          </div>
        </div>

        <!-- BLOC 2 : NOUVEAU - Décomposition par type de feux pour ce mois -->
        <div class="detail-block breakdown-block">
          <div class="block-header">
            <span class="block-title">{{ t('Décomposition des détections thermiques (catégories exploratoires)', 'Thermal detections breakdown (exploratory categories)') }}</span>
            <span class="block-subtitle">{{ active.month }}</span>
          </div>

          <!-- Jauge visuelle proportionnelle -->
          <div class="type-ratio-bar" aria-hidden="true">
            <div
              class="ratio-segment veg"
              :style="{ width: `${monthVegShare ?? 0}%` }"
              :title="`Type 0 hors sources : ${monthVegShare ?? '—'}%`"
            ></div>
            <div
              class="ratio-segment flare"
              :style="{ width: `${monthFlareShare ?? 0}%` }"
              :title="`Détections écartées : ${monthFlareShare ?? '—'}%`"
            ></div>
          </div>

          <div class="type-rows">
            <!-- Type 0 hors sources -->
            <div class="type-row">
              <div class="type-info">
                <span class="type-bullet veg"></span>
                <div>
                  <div class="type-name-line">
                    <span class="type-name">{{ t('Type 0 hors sources persistantes (exploratoire)', 'Type 0 outside persistent sources (exploratory)') }}</span>
                    <span class="type-badge-veg">{{ monthVegShare !== null ? `${monthVegShare} %` : '—' }}</span>
                  </div>
                  <p class="type-desc">{{ t('Détections thermiques type 0 hors des 183 cellules candidates du masque 0,05°.', 'Type-0 thermal detections outside the 183 candidate 0.05° mask cells.') }}</p>
                </div>
              </div>
              <div class="type-numbers">
                <span class="type-count">{{ formatCount(monthVegCount) }}</span>
              </div>
            </div>

            <!-- Détections écartées -->
            <div class="type-row">
              <div class="type-info">
                <span class="type-bullet flare"></span>
                <div>
                  <div class="type-name-line">
                    <span class="type-name">{{ t('Détections écartées par le filtre (exploratoire)', 'Detections excluded by filter (exploratory)') }}</span>
                    <span class="type-badge-flare">{{ monthFlareShare !== null ? `${monthFlareShare} %` : '—' }}</span>
                  </div>
                  <p class="type-desc">{{ t('Différence de séries (types 2/3 + type 0 dans les cellules du masque ; pas toutes des torchères confirmées).', 'Series difference (types 2/3 + type 0 inside mask cells; not all confirmed gas flares).') }}</p>
                </div>
              </div>
              <div class="type-numbers">
                <span class="type-count">{{ formatCount(monthFlareCount) }}</span>
              </div>
            </div>

            <!-- Total combiné brut -->
            <div class="type-row total">
              <div class="type-info">
                <span class="type-bullet total"></span>
                <div>
                  <span class="type-name">{{ t('Total détections thermiques', 'Total thermal detections') }}</span>
                </div>
              </div>
              <div class="type-numbers">
                <span class="type-count total-val">{{ formatCount(monthTotalCount) }}</span>
              </div>
            </div>
          </div>
        </div>

        <!-- BLOC 3 : NOUVEAU - Statut d'harmonisation & Capteurs satellites -->
        <div class="detail-block harmonization-block" :class="isHarmonizedPeriod ? 'era-model' : 'era-viirs'">
          <div class="block-header">
            <span class="harm-era-badge">
              <i class="harm-icon">{{ isHarmonizedPeriod ? '🔬' : '🛰️' }}</i>
              {{ isHarmonizedPeriod ? t('Période harmonisée par modèle (M2)', 'Model-harmonized period (M2)') : t('Observation satellite directe', 'Direct satellite observation') }}
            </span>
            <span class="harm-sensor-tag">{{ isHarmonizedPeriod ? 'MODIS 1 km → VIIRS' : 'VIIRS 375 m' }}</span>
          </div>

          <p class="harm-body-text">
            {{
              isHarmonizedPeriod
                ? t(
                    `En ${active.month.slice(0, 4)}, seul MODIS (1 km) était en orbite (${formatCount(active.modis_count)} détections brutes). Pour comparer équitablement avec les années récentes sans le faux bond ×4, notre modèle Power-Law log1p reconstruit l’équivalent VIIRS 375 m (IC 95 % : [${formatCount(active.ci_low)} – ${formatCount(active.ci_high)}]).`,
                    `In ${active.month.slice(0, 4)}, only MODIS (1 km) was operational (${formatCount(active.modis_count)} raw detections). To compare fairly with recent years without the artificial ×4 jump, our Power-Law log1p model reconstructs the VIIRS 375m equivalent (95% CI: [${formatCount(active.ci_low)} – ${formatCount(active.ci_high)}]).`,
                  )
                : t(
                    `Observé directement par le capteur étalon haute résolution VIIRS Suomi-NPP (375 m). Aucune estimation par modèle nécessaire : c’est la mesure physique directe (${formatCount(active.viirs_snpp_count)} détections).`,
                    `Directly observed by high-resolution reference sensor VIIRS Suomi-NPP (375 m). No model estimation needed: this is the direct physical measurement (${formatCount(active.viirs_snpp_count)} detections).`,
                  )
            }}
          </p>

          <div class="sensor-raw-pills">
            <div v-if="active.modis_count !== null" class="sensor-pill">
              <span class="sp-name">MODIS (1 km) :</span>
              <span class="sp-val">{{ formatCount(active.modis_count) }}</span>
            </div>
            <div v-if="active.viirs_snpp_count !== null" class="sensor-pill">
              <span class="sp-name">VIIRS S-NPP (375 m) :</span>
              <span class="sp-val">{{ formatCount(active.viirs_snpp_count) }}</span>
            </div>
            <div v-if="active.viirs_noaa20_count !== null" class="sensor-pill">
              <span class="sp-name">NOAA-20 :</span>
              <span class="sp-val">{{ formatCount(active.viirs_noaa20_count) }}</span>
            </div>
          </div>
        </div>

        <dl class="detail-grid">
          <div>
            <dt>{{ t('Rang sur 25 ans', '25-year rank') }}</dt>
            <dd>
              {{ ordinal(rankInfo.rank) }} / {{ rankInfo.total }}
            </dd>
          </div>
          <div>
            <dt>{{ t('Couverture satellite', 'Satellite coverage') }}</dt>
            <dd>{{ coverageLabel(active.coverage_status) }}</dd>
          </div>
        </dl>

        <p class="detail-note">
          {{
            isPinned
              ? t('Cliquez à nouveau sur la case pour libérer la sélection.', 'Click the cell again to unpin.')
              : t('Cliquez sur une case pour figer ce mois.', 'Click any cell to pin that month.')
          }}
        </p>
      </aside>
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
  grid-template-columns: minmax(0, 1fr) 360px;
  gap: 22px;
  align-items: start;
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
</style>
