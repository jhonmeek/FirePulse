<script setup lang="ts">
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

const props = defineProps<{ reducedMotion?: boolean }>()

const calendarMode = ref<CalendarMode>('veg')
const monthNames = computed(() => (locale.value === 'en' ? MONTH_NAMES_EN : MONTH_NAMES))
const monthShort = computed(() => (locale.value === 'en' ? MONTH_SHORT_EN : MONTH_SHORT))

const activeSeries = computed<CalendarPoint[]>(() => {
  if (calendarMode.value === 'flare') return flareSeries.value
  if (calendarMode.value === 'all') return allSeries.value
  return staticSeries.value
})

const byMonth = computed(() => new Map(activeSeries.value.map((p) => [p.month, p])))
const maxValue = computed(() =>
  Math.max(...activeSeries.value.map((p) => p.harmonized_value ?? 0), 1),
)

const activeMedians = computed(() =>
  Array.from({ length: 12 }, (_, idx) => {
    const calMonth = idx + 1
    const sample = activeSeries.value.find(
      (p) => yearOf(p.month) >= 2001 && monthNumber(p.month) === calMonth && p.baseline_median !== null,
    )
    if (sample?.baseline_median !== null && sample?.baseline_median !== undefined) {
      return sample.baseline_median
    }
    const vals = activeSeries.value
      .filter((p) => yearOf(p.month) >= 2001 && monthNumber(p.month) === calMonth)
      .map((p) => p.harmonized_value)
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
      `Type 0 hors sources persistantes (${formatCount(composition.value.gaClean)})`,
      `Type 0 outside persistent sources (${formatCount(composition.value.gaClean)})`,
    ),
  },
  {
    id: 'anomalies' as CalendarMode,
    label: t('Brûlis habituels vs Flambées anormales', 'Routine burning vs Abnormal surges'),
  },
  {
    id: 'flare' as CalendarMode,
    label: t(
      `Détections écartées (${formatCount(composition.value.gaExcluded)})`,
      `Detections excluded (${formatCount(composition.value.gaExcluded)})`,
    ),
  },
  {
    id: 'all' as CalendarMode,
    label: t(
      `Toutes détections (${formatCount(composition.value.gaTotal)})`,
      `All detections (${formatCount(composition.value.gaTotal)})`,
    ),
  },
])

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
    return {
      text: t('Site industriel continu (hors saison)', 'Year-round industrial flaring'),
      tone: 'cool',
    }
  }
  const pct = active.value.anomaly_percent
  if (pct === null || pct === undefined) {
    return { text: t('Mois partiel (2000)', 'Partial start month (2000)'), tone: 'neutral' }
  }
  if (pct > 50) {
    return { text: t('Flambée anormale — alerte sécheresse / forêt', 'Abnormal surge — severe wildfire risk'), tone: 'extreme' }
  }
  if (pct >= 25) {
    return { text: t('Au-dessus de la normale saisonnière', 'Above seasonal normal'), tone: 'warm' }
  }
  if (pct <= -20) {
    return { text: t('Mois plus calme que d’habitude', 'Quieter than normal'), tone: 'cool' }
  }
  return { text: t('Activité habituelle (brûlis & savane)', 'Routine seasonal activity (clearing & savanna)'), tone: 'neutral' }
})

const isPinned = computed(() => selected.value !== null && selected.value === active.value.month)

function cell(month: string): CalendarPoint | undefined {
  return byMonth.value.get(month)
}

function monthId(year: number, month: number): string {
  return `${year}-${String(month).padStart(2, '0')}`
}

// Échelle inversée : 0 = beige très clair → intense = bordeaux/noir très sombre.
const STOPS_DARK_INTENSE: [number, [number, number, number]][] = [
  [0, [247, 239, 226]],
  [0.18, [236, 204, 162]],
  [0.42, [219, 122, 59]],
  [0.72, [163, 42, 25]],
  [1, [42, 6, 6]],
]

function mix(a: [number, number, number], b: [number, number, number], ratio: number) {
  return a.map((v, i) => Math.round(v + (b[i]! - v) * ratio)) as [number, number, number]
}

function colorForIntensity(value: number | null | undefined): string {
  if (value === null || value === undefined) return 'rgba(59, 42, 34, 0.08)'
  const normalized = Math.sqrt(Math.max(0, Math.min(1, value / maxValue.value)))
  for (let i = 1; i < STOPS_DARK_INTENSE.length; i++) {
    const [p1, c1] = STOPS_DARK_INTENSE[i]!
    const [p0, c0] = STOPS_DARK_INTENSE[i - 1]!
    if (normalized <= p1) {
      const local = (normalized - p0) / (p1 - p0)
      return `rgb(${mix(c0, c1, local).join(', ')})`
    }
  }
  return `rgb(${STOPS_DARK_INTENSE[STOPS_DARK_INTENSE.length - 1]![1].join(', ')})`
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
  return { backgroundColor: colorForIntensity(point?.harmonized_value) }
}

function ariaLabel(point: CalendarPoint | undefined, year: number, month: number): string {
  const mName = monthNames.value[month - 1]
  if (!point) return `${mName} ${year} — ${t('aucune donnée', 'no data')}`
  const value = formatCount(point.harmonized_value)
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

    <!-- Encart pédagogique : Brûlis volontaires vs Feux de forêt anormaux -->
    <div class="burner-callout">
      <strong>{{ t('Comment distinguer les brûlis habituels des feux anormaux ?', 'How do we tell routine clearing fires apart from abnormal wildfires?') }}</strong>
      <p>
        {{
          t(
            'Depuis l’espace, un satellite mesure la chaleur sans voir qui a allumé le feu. Mais sur 25 ans, les brûlis et feux de végétation présumés reviennent chaque année aux mêmes mois (la normale saisonnière). Quand un mois bondit très au-dessus de sa normale — comme août 2024 (+79 %) —, cela signale une sécheresse inhabituelle où les départs gagnent la forêt. Le type 0 reste une classification du produit, pas une validation terrain.',
            'From space, sensors detect heat without knowing who started it. Over 25 years, routine clearing and presumed vegetation fires repeat at the same time each year (the seasonal normal). When a month jumps sharply above its normal — such as August 2024 (+79%) — it flags unusual drought where fires escape toward forest edges. Type 0 remains a product classification, not field validation.',
          )
        }}
      </p>
    </div>

    <div class="calendar-top">
      <div class="season-strip" aria-hidden="true">
        <span class="season-caption">{{ t('Profil moyen sur 12 mois (médiane 2001–2025)', 'Average 12-month profile (2001–2025 median)') }}</span>
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
          <span class="legend-gradient"></span>
          <span class="legend-max">{{ formatCount(maxValue) }} {{ t('(sombre)', '(dark)') }}</span>
        </div>
      </div>
    </div>

    <div class="calendar-layout">
      <div class="calendar-scroll">
        <div class="calendar-grid" ref="grid" @keydown="onKeydown">
          <div class="grid-corner"></div>
          <div v-for="month in monthShort" :key="month" class="month-head">
            {{ month }}
          </div>

          <template v-for="year in YEARS" :key="year">
            <div class="year-head">{{ year }}</div>
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
        <div class="detail-head">
          <div>
            <p class="tiny-label">
              {{ isPinned ? t('Mois sélectionné', 'Selected month') : t('Survol en direct', 'Live preview') }}
            </p>
            <h3 class="detail-month">{{ monthNames[Number(active.month.slice(5, 7)) - 1] }}</h3>
            <p class="detail-year">{{ active.month.slice(0, 4) }}</p>
          </div>
          <span
            v-if="active.anomaly_percent !== null"
            class="anomaly-badge"
            :class="{
              negative: active.anomaly_percent < 0,
              extreme: active.anomaly_percent > 50,
            }"
          >
            {{ formatPercent(active.anomaly_percent) }}
          </span>
        </div>

        <div class="detail-value">
          <span class="stat">{{ formatCount(active.harmonized_value) }}</span>
          <span class="detail-unit">{{ t('points chauds (échelle unifiée)', 'hotspots (unified scale)') }}</span>
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

        <dl class="detail-grid">
          <div>
            <dt>{{ t('Rang sur 25 ans', '25-year rank') }}</dt>
            <dd>
              {{ ordinal(rankInfo.rank) }} / {{ rankInfo.total }}
            </dd>
          </div>
          <div>
            <dt>{{ t('Fiabilité', 'Data completeness') }}</dt>
            <dd>{{ coverageLabel(active.coverage_status) }}</dd>
          </div>
          <div>
            <dt>MODIS ({{ t('brut', 'raw') }})</dt>
            <dd>{{ formatCount(active.modis_count) }}</dd>
          </div>
          <div>
            <dt>VIIRS S-NPP ({{ t('brut', 'raw') }})</dt>
            <dd>{{ formatCount(active.viirs_snpp_count) }}</dd>
          </div>
          <div>
            <dt>VIIRS NOAA-20 ({{ t('brut', 'raw') }})</dt>
            <dd>{{ formatCount(active.viirs_noaa20_count) }}</dd>
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
  grid-template-columns: minmax(0, 1fr) 310px;
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
  padding-right: 8px;
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
  top: 90px;
}

.detail-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
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

.detail-value {
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin-top: 18px;
}

.detail-unit {
  font-size: 0.78rem;
  color: var(--muted);
}

.detail-verdict {
  margin-top: 10px;
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
