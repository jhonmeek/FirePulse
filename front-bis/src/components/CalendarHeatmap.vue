<script setup lang="ts">
import { computed, nextTick, onMounted, ref, useTemplateRef } from 'vue'
import { gsap, ScrollTrigger } from '@/lib/motion'
import {
  MONTH_NAMES,
  MONTH_SHORT,
  YEARS,
  featuredMonth,
  formatCount,
  formatPercent,
  historicalRank,
  isPartialCoverage,
  mainSeason,
  monthlyMedians,
  secondarySeason,
  staticSeries,
} from '@/lib/data'
import type { CalendarPoint } from '@/lib/types'

const props = defineProps<{ reducedMotion?: boolean }>()

const byMonth = computed(() => new Map(staticSeries.value.map((p) => [p.month, p])))
const maxValue = computed(() =>
  Math.max(...staticSeries.value.map((p) => p.harmonized_value ?? 0), 1),
)
const maxMedian = computed(() => Math.max(...monthlyMedians.value, 1))

const hovered = ref<string | null>(null)
const selected = ref<string | null>(featuredMonth.value.month)
const grid = useTemplateRef<HTMLDivElement>('grid')

const REGIME_LABELS: Record<string, string> = {
  partial_year: 'Année partielle',
  modis_terra_only: 'MODIS Terra seul',
  modis_terra_aqua: 'MODIS Terra + Aqua',
  viirs_snpp_observed: 'VIIRS S-NPP observé',
  viirs_noaa20_bridge: 'Pont NOAA-20',
  missing: 'Donnée manquante',
}

const COVERAGE_LABELS: Record<string, string> = {
  complete_sp: 'Complète (SP)',
  partial_sp: 'Partielle (SP)',
  mixed_sp_nrt: 'Mixte SP + NRT',
  nrt_only: 'NRT seulement',
  no_data: 'Aucune donnée',
}

function regimeLabel(value: string): string {
  return REGIME_LABELS[value] ?? value.replaceAll('_', ' ')
}

function coverageLabel(value: string): string {
  return COVERAGE_LABELS[value] ?? value.replaceAll('_', ' ')
}

function ordinal(value: number): string {
  return value === 1 ? '1er' : `${value}e`
}

const activeMonth = computed(() => selected.value ?? hovered.value ?? featuredMonth.value.month)
const active = computed<CalendarPoint>(
  () => byMonth.value.get(activeMonth.value) ?? featuredMonth.value,
)
const rankInfo = computed(() => historicalRank(active.value))
const isPinned = computed(() => selected.value !== null && selected.value === active.value.month)

function cell(month: string): CalendarPoint | undefined {
  return byMonth.value.get(month)
}

function monthId(year: number, month: number): string {
  return `${year}-${String(month).padStart(2, '0')}`
}

const STOPS: [number, [number, number, number]][] = [
  [0, [24, 17, 14]],
  [0.12, [48, 25, 20]],
  [0.3, [104, 40, 22]],
  [0.52, [180, 63, 26]],
  [0.72, [235, 96, 40]],
  [0.88, [255, 158, 83]],
  [1, [255, 224, 163]],
]

function mix(a: [number, number, number], b: [number, number, number], t: number) {
  return a.map((v, i) => Math.round(v + (b[i]! - v) * t)) as [number, number, number]
}

function colorFor(value: number | null | undefined): string {
  if (value === null || value === undefined) return 'rgba(244, 241, 232, 0.04)'
  const t = Math.sqrt(Math.max(0, Math.min(1, value / maxValue.value)))
  for (let i = 1; i < STOPS.length; i++) {
    const [p1, c1] = STOPS[i]!
    const [p0, c0] = STOPS[i - 1]!
    if (t <= p1) {
      const local = (t - p0) / (p1 - p0)
      return `rgb(${mix(c0, c1, local).join(', ')})`
    }
  }
  return `rgb(${STOPS[STOPS.length - 1]![1].join(', ')})`
}

function cellStyle(point: CalendarPoint | undefined) {
  return { backgroundColor: colorFor(point?.harmonized_value) }
}

function ariaLabel(point: CalendarPoint | undefined, year: number, month: number): string {
  if (!point) return `${MONTH_NAMES[month - 1]} ${year} — aucune donnée`
  const value = formatCount(point.harmonized_value)
  const anomaly =
    point.anomaly_percent !== null ? `, anomalie ${formatPercent(point.anomaly_percent)}` : ''
  const coverage = isPartialCoverage(point) ? ', couverture partielle' : ''
  return `${MONTH_NAMES[month - 1]} ${year} : ${value} détections équivalentes VIIRS${anomaly}${coverage}`
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
    scale: 0.82,
    duration: 0.55,
    ease: 'power2.out',
    stagger: { each: 0.0022, from: 'start' },
    immediateRender: false,
    scrollTrigger: { trigger: grid.value, start: 'top 82%', once: true },
  })
  ScrollTrigger.refresh()
})
</script>

<template>
  <div class="calendar">
    <div class="calendar-top">
      <div class="season-strip" aria-hidden="true">
        <span class="season-caption">Médiane mensuelle</span>
        <div class="season-bars">
          <div
            v-for="(value, index) in monthlyMedians"
            :key="index"
            class="season-bar"
            :class="{
              main: mainSeason.includes(index + 1),
              secondary: secondarySeason.includes(index + 1),
            }"
          >
            <i :style="{ height: `${Math.max(6, (value / maxMedian) * 100)}%` }"></i>
            <span>{{ MONTH_SHORT[index] }}</span>
          </div>
        </div>
      </div>
      <div class="legend" aria-hidden="true">
        <span class="tiny-label">Intensité</span>
        <div class="legend-scale">
          <span class="legend-gradient"></span>
          <span class="legend-min">0</span>
          <span class="legend-max">{{ formatCount(maxValue) }}</span>
        </div>
      </div>
    </div>

    <div class="calendar-layout">
      <div class="calendar-scroll">
        <div class="calendar-grid" ref="grid" @keydown="onKeydown">
          <div class="grid-corner"></div>
          <div v-for="month in MONTH_SHORT" :key="month" class="month-head">
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
            <p class="tiny-label">{{ isPinned ? 'Mois épinglé' : 'Aperçu' }}</p>
            <h3 class="detail-month">{{ MONTH_NAMES[Number(active.month.slice(5, 7)) - 1] }}</h3>
            <p class="detail-year">{{ active.month.slice(0, 4) }}</p>
          </div>
          <span
            v-if="active.anomaly_percent !== null"
            class="anomaly-badge"
            :class="{ negative: active.anomaly_percent < 0 }"
          >
            {{ formatPercent(active.anomaly_percent) }}
          </span>
        </div>

        <div class="detail-value">
          <span class="stat">{{ formatCount(active.harmonized_value) }}</span>
          <span class="detail-unit">détections équivalentes VIIRS S-NPP</span>
        </div>

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
          <span><i class="label-swatch value"></i>valeur</span>
          <span><i class="label-swatch median"></i>médiane {{ formatCount(active.baseline_median) }}</span>
        </div>

        <dl class="detail-grid">
          <div>
            <dt>Rang historique</dt>
            <dd>
              {{ ordinal(rankInfo.rank) }} / {{ rankInfo.total }} ({{ rankInfo.minYear }}–{{ rankInfo.maxYear }})
            </dd>
          </div>
          <div>
            <dt>Régime</dt>
            <dd>{{ regimeLabel(active.sensor_regime) }}</dd>
          </div>
          <div>
            <dt>MODIS</dt>
            <dd>{{ formatCount(active.modis_count) }}</dd>
          </div>
          <div>
            <dt>VIIRS S-NPP</dt>
            <dd>{{ formatCount(active.viirs_snpp_count) }}</dd>
          </div>
          <div>
            <dt>VIIRS NOAA-20</dt>
            <dd>{{ formatCount(active.viirs_noaa20_count) }}</dd>
          </div>
          <div>
            <dt>Couverture</dt>
            <dd>{{ coverageLabel(active.coverage_status) }}</dd>
          </div>
        </dl>

        <p class="detail-note">
          {{ isPinned ? 'Cliquez à nouveau pour désépingler.' : 'Cliquez pour épingler ce mois.' }}
        </p>
      </aside>
    </div>
  </div>
</template>

<style scoped>
.calendar {
  width: 100%;
}

.calendar-top {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 24px;
  margin-bottom: 16px;
}

.season-strip {
  flex: 1;
  min-width: 0;
}

.season-caption {
  display: block;
  margin-bottom: 7px;
  font-family: var(--font-mono);
  font-size: 0.54rem;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--dim);
}

.season-bars {
  display: grid;
  grid-template-columns: repeat(12, minmax(0, 1fr));
  gap: 3px;
  align-items: end;
  height: 46px;
}

.season-bar {
  position: relative;
  display: flex;
  flex-direction: column;
  justify-content: flex-end;
  gap: 4px;
  height: 100%;
  min-width: 0;
}

.season-bar i {
  display: block;
  width: 100%;
  min-height: 3px;
  border-radius: 2px 2px 0 0;
  background: rgba(244, 241, 232, 0.12);
  transition: background 0.3s ease;
}

.season-bar.main i {
  background: linear-gradient(180deg, #ffc46b, #e24e1b);
}

.season-bar.secondary i {
  background: linear-gradient(180deg, #ffc46b, #7c2d12);
  opacity: 0.75;
}

.season-bar span {
  font-family: var(--font-mono);
  font-size: 0.5rem;
  letter-spacing: 0.05em;
  text-align: center;
  color: var(--dim);
}

.season-bar.main span {
  color: var(--gold);
}

.legend {
  flex: none;
  width: 180px;
}

.legend-scale {
  position: relative;
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 6px;
}

.legend-gradient {
  flex: 1;
  height: 8px;
  border-radius: 4px;
  background: linear-gradient(90deg, #18110e, #68301a, #b43f1a, #eb6028, #ff9e53, #ffe0a3);
}

.legend-min,
.legend-max {
  font-family: var(--font-mono);
  font-size: 0.54rem;
  color: var(--dim);
}

.calendar-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 292px;
  gap: 22px;
  align-items: start;
}

.calendar-scroll {
  overflow-x: auto;
  padding-bottom: 6px;
  scrollbar-width: thin;
  scrollbar-color: var(--line-strong) transparent;
}

.calendar-grid {
  display: grid;
  grid-template-columns: 3.2rem repeat(12, minmax(0, 1fr));
  gap: 3px;
  min-width: 660px;
}

.grid-corner {
  height: 18px;
}

.month-head,
.year-head {
  font-family: var(--font-mono);
  font-size: 0.54rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--dim);
}

.month-head {
  display: flex;
  align-items: flex-end;
  justify-content: center;
  height: 18px;
}

.year-head {
  display: flex;
  align-items: center;
  padding-right: 8px;
}

.cell {
  position: relative;
  aspect-ratio: 1.55;
  min-height: 20px;
  padding: 0;
  border: 1px solid rgba(5, 7, 11, 0.45);
  border-radius: 4px;
  cursor: pointer;
  transition:
    transform 0.25s var(--ease-out),
    outline-color 0.25s ease,
    filter 0.25s ease;
}

.cell:hover,
.cell:focus-visible {
  transform: scale(1.14);
  z-index: 3;
  outline: 1px solid rgba(255, 224, 163, 0.85);
  outline-offset: 1px;
  filter: brightness(1.16);
}

.cell.is-active {
  outline: 1.5px solid var(--gold);
  outline-offset: 1px;
}

.cell.is-selected {
  outline: 2px solid var(--ink);
  outline-offset: 2px;
  z-index: 2;
}

.cell.is-empty {
  background: transparent;
  border-color: transparent;
  cursor: default;
}

.cell.is-missing {
  border-style: dashed;
  border-color: var(--line);
}

.cell.is-partial::after {
  content: '';
  position: absolute;
  inset: 0;
  border-radius: inherit;
  background-image: repeating-linear-gradient(
    135deg,
    transparent 0 4px,
    rgba(5, 7, 11, 0.35) 4px 6px
  );
  pointer-events: none;
}

.cell-dot {
  position: absolute;
  top: 3px;
  right: 3px;
  width: 3px;
  height: 3px;
  border-radius: 50%;
  background: rgba(244, 241, 232, 0.55);
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
  font-size: 1.65rem;
  font-weight: 400;
  line-height: 1;
  letter-spacing: -0.02em;
}

.detail-year {
  margin-top: 2px;
  font-family: var(--font-mono);
  font-size: 0.7rem;
  color: var(--dim);
}

.anomaly-badge {
  display: inline-flex;
  align-items: center;
  padding: 4px 9px;
  border-radius: 999px;
  background: rgba(255, 196, 107, 0.14);
  border: 1px solid rgba(255, 196, 107, 0.35);
  color: var(--gold);
  font-family: var(--font-mono);
  font-size: 0.66rem;
  white-space: nowrap;
}

.anomaly-badge.negative {
  background: rgba(96, 165, 250, 0.12);
  border-color: rgba(96, 165, 250, 0.3);
  color: #93c5fd;
}

.detail-value {
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin-top: 22px;
}

.detail-unit {
  font-size: 0.72rem;
  color: var(--muted);
}

.detail-bar {
  position: relative;
  height: 6px;
  margin-top: 16px;
  border-radius: 3px;
  background: rgba(244, 241, 232, 0.08);
}

.detail-bar-value {
  position: absolute;
  inset: 0 auto 0 0;
  border-radius: 3px;
  background: var(--grad-heat);
}

.detail-bar-median {
  position: absolute;
  top: -3px;
  width: 2px;
  height: 12px;
  background: var(--teal);
  box-shadow: 0 0 8px rgba(94, 234, 212, 0.6);
}

.detail-bar-labels {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-top: 6px;
  font-family: var(--font-mono);
  font-size: 0.52rem;
  letter-spacing: 0.04em;
  color: var(--dim);
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
  width: 2px;
  height: 8px;
  border-radius: 0;
  background: var(--teal);
  box-shadow: 0 0 6px rgba(94, 234, 212, 0.6);
}

.detail-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px 14px;
  margin: 20px 0 0;
  padding-top: 16px;
  border-top: 1px solid var(--line);
}

.detail-grid dt {
  font-family: var(--font-mono);
  font-size: 0.5rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--dim);
}

.detail-grid dd {
  margin: 3px 0 0;
  font-size: 0.76rem;
  color: var(--ink);
}

.detail-note {
  margin-top: 18px;
  font-size: 0.66rem;
  color: var(--dim);
}

@media (max-width: 1000px) {
  .calendar-layout {
    grid-template-columns: minmax(0, 1fr);
  }
  .detail {
    position: static;
  }
  .legend {
    width: 140px;
  }
}

@media (max-width: 700px) {
  .calendar-grid {
    min-width: 0;
    grid-template-columns: 2.3rem repeat(12, minmax(0, 1fr));
    gap: 2px;
  }
  .month-head,
  .year-head {
    font-size: 0.46rem;
    letter-spacing: 0.02em;
  }
  .cell {
    border-radius: 3px;
    min-height: 17px;
  }
}

@media (max-width: 640px) {
  .calendar-top {
    flex-direction: column;
    align-items: stretch;
    gap: 12px;
  }
  .legend {
    width: 100%;
  }
}
</style>
