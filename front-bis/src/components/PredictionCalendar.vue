<script setup lang="ts">
import { computed } from 'vue'
import { locale, t } from '@/lib/i18n'
import {
  predictionProvinceRow,
  probabilityClass,
  type PredictionProvinceRow,
} from '@/lib/prediction'

const props = withDefaults(
  defineProps<{
    provinceCode: string
    provinceName: string
    years: number[]
    selectedYear: number
    selectedMonth: number
    mode?: 'probability' | 'relative'
  }>(),
  { mode: 'probability' },
)

defineEmits<{
  (event: 'select', year: number, month: number): void
  (event: 'hover', year: number | null, month: number | null): void
  (event: 'update:mode', value: 'probability' | 'relative'): void
}>()

const months = [
  { num: 1, short: 'Jan', long: 'Janvier' },
  { num: 2, short: 'Fév', long: 'Février' },
  { num: 3, short: 'Mar', long: 'Mars' },
  { num: 4, short: 'Avr', long: 'Avril' },
  { num: 5, short: 'Mai', long: 'Mai' },
  { num: 6, short: 'Juin', long: 'Juin' },
  { num: 7, short: 'Juil', long: 'Juillet' },
  { num: 8, short: 'Août', long: 'Août' },
  { num: 9, short: 'Sep', long: 'Septembre' },
  { num: 10, short: 'Oct', long: 'Octobre' },
  { num: 11, short: 'Nov', long: 'Novembre' },
  { num: 12, short: 'Déc', long: 'Décembre' },
]

const rows = computed(() =>
  props.years.map((year) => {
    const values = months.map((month) => {
      const row = predictionProvinceRow(props.provinceCode, year, month.num)
      return { ...month, year, row }
    })
    const mean =
      values.reduce((sum, item) => sum + (item.row?.meanProbability ?? 0), 0) /
      Math.max(1, values.length)
    return { year, values, mean }
  }),
)

function cellColor(row: PredictionProvinceRow | undefined, mean: number): string {
  if (!row) return '#0b111a'
  if (props.mode === 'relative') {
    const relative = mean > 0 ? row.meanProbability / mean : 1
    if (relative >= 1.8) return 'rgba(255, 122, 61, 0.95)'
    if (relative >= 1.2) return 'rgba(255, 196, 107, 0.8)'
    if (relative >= 0.8) return 'rgba(244, 241, 232, 0.12)'
    if (relative >= 0.5) return 'rgba(94, 234, 212, 0.35)'
    return 'rgba(94, 234, 212, 0.18)'
  }
  const probability = row.meanProbability
  return probabilityClass(probability).color
}

function cellOpacity(row: PredictionProvinceRow | undefined, mean: number): number {
  if (!row) return 0.2
  if (props.mode === 'relative') return 0.95
  return row.meanProbability >= 0.5
    ? 0.95
    : row.meanProbability >= 0.25
      ? 0.82
      : row.meanProbability >= 0.1
        ? 0.62
        : 0.35
}

function cellLabel(row: PredictionProvinceRow | undefined, year: number, month: string): string {
  if (!row) return `${month} ${year}`
  const label = probabilityClass(row.meanProbability)
  return `${month} ${year} · ${Math.round(row.meanProbability * 100)}% · ${t('risque', 'risk')} ${
    locale.value === 'en' ? label.labelEn : label.labelFr
  }`
}

function cellText(row: PredictionProvinceRow | undefined, mean: number): string {
  if (!row) return '—'
  if (props.mode === 'relative') {
    const relative = mean > 0 ? row.meanProbability / mean : 1
    return `×${relative.toFixed(1)}`
  }
  return `${Math.round(row.meanProbability * 100)}`
}

function cellTextColor(row: PredictionProvinceRow | undefined, mean: number): string {
  if (!row) return 'var(--dim)'
  if (props.mode === 'relative') {
    const relative = mean > 0 ? row.meanProbability / mean : 1
    return relative >= 1.2 ? '#05070b' : 'var(--ink)'
  }
  return row.meanProbability >= 0.1 ? '#05070b' : 'var(--ink)'
}
</script>

<template>
  <div class="prediction-calendar">
    <div class="prediction-calendar-head">
      <div>
        <span class="prediction-calendar-eyebrow">{{ t('Calendrier futur', 'Future calendar') }}</span>
        <h4>{{ provinceName }} · {{ years[0] }}–{{ years[years.length - 1] }}</h4>
      </div>
      <div class="prediction-calendar-modes" role="group" :aria-label="t('Mode du calendrier', 'Calendar mode')">
        <button
          type="button"
          class="prediction-calendar-mode"
          :class="{ active: mode === 'probability' }"
          @click="$emit('update:mode', 'probability')"
        >
          {{ t('Probabilité', 'Probability') }}
        </button>
        <button
          type="button"
          class="prediction-calendar-mode"
          :class="{ active: mode === 'relative' }"
          @click="$emit('update:mode', 'relative')"
        >
          {{ t('Risque relatif', 'Relative risk') }}
        </button>
      </div>
    </div>

    <div class="prediction-calendar-grid" role="table" :aria-label="t('Calendrier des risques futurs', 'Future risk calendar')">
      <div class="prediction-calendar-corner" aria-hidden="true"></div>
      <div v-for="month in months" :key="`head-${month.num}`" class="prediction-calendar-month" role="columnheader">
        {{ month.short }}
      </div>
      <template v-for="row in rows" :key="row.year">
        <div class="prediction-calendar-year" role="rowheader">{{ row.year }}</div>
        <button
          v-for="item in row.values"
          :key="`${row.year}-${item.num}`"
          type="button"
          class="prediction-calendar-cell"
          :class="{
            'is-selected': row.year === selectedYear && item.num === selectedMonth,
          }"
          :style="{
            background: cellColor(item.row, row.mean),
            opacity: cellOpacity(item.row, row.mean),
            color: cellTextColor(item.row, row.mean),
          }"
          :aria-label="cellLabel(item.row, row.year, item.long)"
          role="cell"
          @mouseenter="$emit('hover', row.year, item.num)"
          @mouseleave="$emit('hover', null, null)"
          @focus="$emit('hover', row.year, item.num)"
          @blur="$emit('hover', null, null)"
          @click="$emit('select', row.year, item.num)"
        >
          <span>{{ cellText(item.row, row.mean) }}</span>
        </button>
      </template>
    </div>

    <div class="prediction-calendar-legend">
      <template v-if="mode === 'probability'">
        <span class="prediction-calendar-legend-label">{{ t('Probabilité', 'Probability') }}</span>
        <span class="prediction-calendar-legend-item"><i style="background: #637080"></i>0–10 %</span>
        <span class="prediction-calendar-legend-item"><i style="background: #5eead4"></i>10–25 %</span>
        <span class="prediction-calendar-legend-item"><i style="background: #ffc46b"></i>25–50 %</span>
        <span class="prediction-calendar-legend-item"><i style="background: #ff7a3d"></i>≥ 50 %</span>
      </template>
      <template v-else>
        <span class="prediction-calendar-legend-label">{{ t('Risque relatif', 'Relative risk') }}</span>
        <span class="prediction-calendar-legend-item"><i style="background: rgba(94, 234, 212, 0.35)"></i>{{ t('sous la moyenne', 'below average') }}</span>
        <span class="prediction-calendar-legend-item"><i style="background: rgba(244, 241, 232, 0.18)"></i>{{ t('proche de la moyenne', 'near average') }}</span>
        <span class="prediction-calendar-legend-item"><i style="background: rgba(255, 196, 107, 0.8)"></i>{{ t('au-dessus', 'above') }}</span>
        <span class="prediction-calendar-legend-item"><i style="background: rgba(255, 122, 61, 0.95)"></i>{{ t('très au-dessus', 'well above') }}</span>
      </template>
    </div>
  </div>
</template>

<style scoped>
.prediction-calendar {
  display: grid;
  gap: 12px;
  min-width: 0;
}

.prediction-calendar-head {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  justify-content: space-between;
  gap: 8px 14px;
}

.prediction-calendar-eyebrow {
  display: block;
  font-family: var(--font-mono);
  font-size: 0.6rem;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--dim);
}

.prediction-calendar-head h4 {
  margin: 3px 0 0;
  font-family: var(--font-display);
  font-size: clamp(1.05rem, 1.5vw, 1.3rem);
  font-weight: 400;
  color: var(--ink);
}

.prediction-calendar-modes {
  display: inline-flex;
  flex-wrap: wrap;
  gap: 3px;
  padding: 3px;
  border: 1px solid var(--line-strong);
  border-radius: 9px;
  background: rgba(244, 241, 232, 0.03);
}

.prediction-calendar-mode {
  padding: 5px 9px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: var(--muted);
  font-size: 0.66rem;
  cursor: pointer;
}

.prediction-calendar-mode.active {
  background: var(--ink);
  color: #05070b;
  font-weight: 600;
}

.prediction-calendar-grid {
  display: grid;
  grid-template-columns: 46px repeat(12, minmax(0, 1fr));
  gap: 3px;
  align-items: stretch;
}

.prediction-calendar-corner {
  min-height: 1px;
}

.prediction-calendar-month,
.prediction-calendar-year {
  display: flex;
  align-items: center;
  justify-content: center;
  font-family: var(--font-mono);
  font-size: 0.58rem;
  color: var(--dim);
}

.prediction-calendar-year {
  justify-content: flex-start;
  padding-left: 2px;
  color: var(--ink);
  font-weight: 600;
}

.prediction-calendar-cell {
  min-height: 34px;
  padding: 0;
  border: 1px solid rgba(5, 7, 11, 0.5);
  border-radius: 4px;
  color: #05070b;
  font-family: var(--font-mono);
  font-size: 0.58rem;
  font-weight: 700;
  cursor: pointer;
  transition:
    border-color 0.15s ease,
    transform 0.15s ease;
}

.prediction-calendar-cell:hover,
.prediction-calendar-cell:focus-visible {
  border-color: var(--ink);
  transform: translateY(-1px);
  outline: none;
}

.prediction-calendar-cell.is-selected {
  border-color: var(--gold);
  box-shadow: 0 0 0 1px var(--gold);
}

.prediction-calendar-legend {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 5px 10px;
  font-size: 0.64rem;
  color: var(--muted);
}

.prediction-calendar-legend-label {
  font-family: var(--font-mono);
  font-size: 0.56rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--dim);
}

.prediction-calendar-legend-item {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.prediction-calendar-legend-item i {
  width: 8px;
  height: 8px;
  border-radius: 2px;
  display: block;
}

@media (max-width: 760px) {
  .prediction-calendar-grid {
    grid-template-columns: 38px repeat(12, minmax(0, 1fr));
    gap: 2px;
  }

  .prediction-calendar-cell {
    min-height: 28px;
    font-size: 0.5rem;
  }

  .prediction-calendar-month {
    font-size: 0.5rem;
  }
}
</style>
