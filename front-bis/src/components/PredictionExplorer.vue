<script setup lang="ts">
import { computed, ref } from 'vue'
import PredictionMap from '@/components/PredictionMap.vue'
import PredictionCalendar from '@/components/PredictionCalendar.vue'
import PredictionDetailCard from '@/components/PredictionDetailCard.vue'
import PredictionConfidence from '@/components/PredictionConfidence.vue'
import { MONTH_NAMES, MONTH_NAMES_EN, provinceFeatures } from '@/lib/data'
import { locale, t } from '@/lib/i18n'
import {
  prediction,
  predictionCells,
  predictionMetrics,
  predictionMonthValues,
  predictionProvinceOptions,
  predictionProvinceRow,
  predictionYears,
  type PredictionValue,
} from '@/lib/prediction'

const selectedProvince = ref('GA')
const selectedYear = ref(predictionYears.includes(2027) ? 2027 : predictionYears[0]!)
const selectedMonth = ref(8)
const calendarMode = ref<'probability' | 'relative'>('probability')
const mapMode = ref<'probability' | 'climatology'>('probability')
const hoveredCellIndex = ref<number | null>(null)
const selectedCellIndex = ref<number | null>(null)
const hoveredCalendar = ref<{ year: number; month: number } | null>(null)

const provinceName = computed(
  () =>
    predictionProvinceOptions.find((item) => item.code === selectedProvince.value)?.name ??
    selectedProvince.value,
)

const monthNames = computed(() => (locale.value === 'en' ? MONTH_NAMES_EN : MONTH_NAMES))
const selectedMonthName = computed(() => monthNames.value[selectedMonth.value - 1] ?? '')

const monthValues = computed(() =>
  predictionMonthValues(selectedYear.value, selectedMonth.value),
)

const selectedProvinceRow = computed(() =>
  predictionProvinceRow(selectedProvince.value, selectedYear.value, selectedMonth.value),
)

const detailYear = computed(() =>
  hoveredCalendar.value ? hoveredCalendar.value.year : selectedYear.value,
)
const detailMonth = computed(() =>
  hoveredCalendar.value ? hoveredCalendar.value.month : selectedMonth.value,
)
const detailMonthName = computed(() => monthNames.value[detailMonth.value - 1] ?? '')

const detailCellIndex = computed(() => hoveredCellIndex.value ?? selectedCellIndex.value)
const detailMode = computed<'cell' | 'province'>(() => {
  if (hoveredCalendar.value) return 'province'
  return detailCellIndex.value !== null ? 'cell' : 'province'
})
const detailCell = computed(() =>
  detailMode.value === 'cell' && detailCellIndex.value !== null
    ? (predictionCells[detailCellIndex.value] ?? null)
    : null,
)
const detailValue = computed<PredictionValue | null>(() => {
  if (detailMode.value !== 'cell' || detailCellIndex.value === null) return null
  return predictionMonthValues(detailYear.value, detailMonth.value).get(detailCellIndex.value) ?? null
})
const detailProvinceRow = computed(() =>
  predictionProvinceRow(
    selectedProvince.value,
    detailYear.value,
    detailMonth.value,
  ),
)

const detailPinned = computed(() => selectedCellIndex.value !== null && !hoveredCellIndex.value)

function onProvinceChange() {
  selectedCellIndex.value = null
  hoveredCellIndex.value = null
  hoveredCalendar.value = null
}

function onSelectCell(index: number) {
  selectedCellIndex.value = selectedCellIndex.value === index ? null : index
  const cell = predictionCells[index]
  if (cell && selectedProvince.value !== 'GA' && cell.province !== selectedProvince.value) {
    selectedProvince.value = 'GA'
  }
}

function onSelectCalendar(year: number, month: number) {
  selectedYear.value = year
  selectedMonth.value = month
  selectedCellIndex.value = null
}

function onHoverCalendar(year: number | null, month: number | null) {
  hoveredCalendar.value = year !== null && month !== null ? { year, month } : null
}

function resetPeriod() {
  selectedYear.value = predictionYears.includes(2027) ? 2027 : predictionYears[0]!
  selectedMonth.value = 8
  selectedCellIndex.value = null
}
</script>

<template>
  <div class="prediction-explorer">
    <div class="prediction-controls">
      <label class="prediction-control">
        <span>{{ t('Province', 'Province') }}</span>
        <select v-model="selectedProvince" @change="onProvinceChange">
          <option v-for="item in predictionProvinceOptions" :key="item.code" :value="item.code">
            {{ item.name }}
          </option>
        </select>
      </label>

      <div class="prediction-period">
        <span class="prediction-period-label">{{ t('Période sélectionnée', 'Selected period') }}</span>
        <strong>{{ selectedMonthName }} {{ selectedYear }}</strong>
        <span class="prediction-period-hint">{{ t('Cliquez une case du calendrier pour changer', 'Click a calendar cell to change') }}</span>
      </div>

      <button type="button" class="prediction-reset" @click="resetPeriod">
        {{ t('Revenir à août 2027', 'Back to August 2027') }}
      </button>
    </div>

    <div class="prediction-layout">
      <div class="prediction-map-column">
        <PredictionMap
          v-model:mode="mapMode"
          :cells="predictionCells"
          :month-values="monthValues"
          :province-features="provinceFeatures"
          :selected-province="selectedProvince"
          :selected-year="selectedYear"
          :selected-month="selectedMonth"
          :hovered-cell-index="hoveredCellIndex"
          :selected-cell-index="selectedCellIndex"
          @hover-cell="hoveredCellIndex = $event"
          @select-cell="onSelectCell"
        />
        <PredictionDetailCard
          :mode="detailMode"
          :province-name="detailMode === 'cell' && detailCell ? detailCell.provinceName : provinceName"
          :year="detailYear"
          :month="detailMonth"
          :month-name="detailMonthName"
          :cell="detailCell"
          :value="detailValue"
          :province-row="detailProvinceRow"
          :pinned="detailPinned"
        />
      </div>

      <PredictionCalendar
        v-model:mode="calendarMode"
        :province-code="selectedProvince"
        :province-name="provinceName"
        :years="predictionYears"
        :selected-year="selectedYear"
        :selected-month="selectedMonth"
        @select="onSelectCalendar"
        @hover="onHoverCalendar"
      />
    </div>

    <p class="prediction-read-note">
      {{
        t(
          'Chaque case du calendrier représente la probabilité qu’au moins un feu forestier soit détecté dans la province pendant ce mois. La carte montre la répartition spatiale pour le mois sélectionné. Survolez ou cliquez une cellule pour ouvrir la fiche flottante.',
          'Each calendar cell is the probability that at least one forest fire is detected in the province during that month. The map shows the spatial pattern for the selected month. Hover or click a cell to open the floating note.',
        )
      }}
    </p>

    <PredictionConfidence :metrics="predictionMetrics" :generated-at="prediction.generatedAt" />
  </div>
</template>

<style scoped>
.prediction-explorer {
  display: grid;
  gap: 18px;
}

.prediction-controls {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  gap: 14px 22px;
  padding: 14px 16px;
  border: 1px solid var(--line);
  border-radius: 13px;
  background: rgba(244, 241, 232, 0.025);
}

.prediction-control {
  display: grid;
  gap: 5px;
}

.prediction-control span,
.prediction-period-label {
  font-family: var(--font-mono);
  font-size: 0.58rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--dim);
}

.prediction-control select {
  min-width: 190px;
  padding: 8px 10px;
  border: 1px solid var(--line-strong);
  border-radius: 8px;
  background: rgba(5, 7, 11, 0.6);
  color: var(--ink);
  font-size: 0.78rem;
}

.prediction-period {
  display: grid;
  gap: 3px;
}

.prediction-period strong {
  font-family: var(--font-display);
  font-size: 1.2rem;
  font-weight: 400;
  color: var(--ink);
}

.prediction-period-hint {
  font-size: 0.66rem;
  color: var(--dim);
}

.prediction-reset {
  margin-left: auto;
  padding: 7px 11px;
  border: 1px solid var(--line-strong);
  border-radius: 8px;
  background: transparent;
  color: var(--muted);
  font-size: 0.68rem;
  cursor: pointer;
}

.prediction-reset:hover {
  color: var(--ink);
  border-color: var(--gold);
}

.prediction-layout {
  display: grid;
  grid-template-columns: minmax(0, 1.08fr) minmax(0, 0.92fr);
  gap: 18px;
  align-items: start;
}

.prediction-map-column {
  position: relative;
  min-width: 0;
}

.prediction-read-note {
  margin: -2px 0 0;
  font-size: 0.74rem;
  line-height: 1.55;
  color: var(--dim);
}

@media (max-width: 980px) {
  .prediction-layout {
    grid-template-columns: 1fr;
  }
}
</style>
