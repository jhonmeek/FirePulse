<script setup lang="ts">
import { computed } from 'vue'
import { formatDecimal } from '@/lib/data'
import { locale, t } from '@/lib/i18n'
import {
  probabilityClass,
  type PredictionCell,
  type PredictionProvinceRow,
  type PredictionValue,
} from '@/lib/prediction'

const props = withDefaults(
  defineProps<{
    mode: 'cell' | 'province'
    provinceName: string
    year: number
    month: number
    monthName: string
    cell?: PredictionCell | null
    value?: PredictionValue | null
    provinceRow?: PredictionProvinceRow | null
    pinned?: boolean
  }>(),
  {
    cell: null,
    value: null,
    provinceRow: null,
    pinned: false,
  },
)

const probability = computed(() => {
  if (props.mode === 'cell') return props.value?.[1] ?? 0
  return props.provinceRow?.meanProbability ?? 0
})

const baseProbability = computed(() => {
  if (props.mode === 'cell') return props.value?.[2] ?? 0
  return props.provinceRow?.meanProbability ?? 0
})

const trendFactor = computed(() => {
  if (baseProbability.value <= 0) return 1
  return probability.value / baseProbability.value
})

const classification = computed(() => {
  const item = probabilityClass(probability.value)
  return locale.value === 'en' ? item.labelEn : item.labelFr
})

const title = computed(() => `${props.monthName} ${props.year} · ${props.provinceName}`)
</script>

<template>
  <aside class="prediction-detail" :class="{ 'is-pinned': pinned }" aria-live="polite">
    <div class="prediction-detail-head">
      <span class="prediction-detail-eyebrow">
        {{ mode === 'cell' ? t('Cellule 0,25°', '0.25° cell') : t('Province', 'Province') }}
        <template v-if="pinned">· {{ t('épinglé', 'pinned') }}</template>
      </span>
      <span class="prediction-detail-class">{{ classification }}</span>
    </div>

    <h5>{{ title }}</h5>

    <div class="prediction-detail-probability">
      <strong>{{ Math.round(probability * 100) }}%</strong>
      <span>{{ t('probabilité de feu forestier', 'forest fire probability') }}</span>
    </div>

    <div class="prediction-detail-bar" aria-hidden="true">
      <i :style="{ width: `${Math.max(2, Math.min(100, probability * 100))}%` }"></i>
    </div>

    <dl v-if="mode === 'cell' && cell && value" class="prediction-detail-list">
      <div>
        <dt>{{ t('Climatologie 2012–2025', '2012–2025 climatology') }}</dt>
        <dd>{{ Math.round(baseProbability * 100) }}%</dd>
      </div>
      <div>
        <dt>{{ t('Tendance projetée', 'Projected trend') }}</dt>
        <dd>×{{ formatDecimal(trendFactor, 2) }}</dd>
      </div>
      <div>
        <dt>{{ t('Années avec feu en', 'Fire years in') }} {{ monthName.toLowerCase() }}</dt>
        <dd>{{ value[3] }} / {{ value[4] }}</dd>
      </div>
      <div>
        <dt>{{ t('Forêt / cultures / bâti', 'Forest / crops / built-up') }}</dt>
        <dd>
          {{ Math.round(cell.forest * 100) }}% · {{ Math.round(cell.cropland * 100) }}% ·
          {{ Math.round(cell.builtup * 100) }}%
        </dd>
      </div>
    </dl>

    <dl v-else-if="mode === 'province' && provinceRow" class="prediction-detail-list">
      <div>
        <dt>{{ t('Cellules forestières', 'Forest cells') }}</dt>
        <dd>{{ provinceRow.cells }}</dd>
      </div>
      <div>
        <dt>{{ t('Cellules attendues avec feu', 'Expected fire cells') }}</dt>
        <dd>{{ formatDecimal(provinceRow.expectedFireCellsMonth, 1) }}</dd>
      </div>
      <div>
        <dt>{{ t('Part à risque élevé', 'High-risk share') }}</dt>
        <dd>{{ Math.round(provinceRow.highRiskShare * 100) }}%</dd>
      </div>
      <div>
        <dt>{{ t('Année : mois attendus avec feu', 'Year: expected fire months') }}</dt>
        <dd>{{ formatDecimal(provinceRow.expectedFireMonths, 1) }}</dd>
      </div>
    </dl>

    <p class="prediction-detail-note">
      {{
        t(
          'Probabilité climatologique, pas une prévision météo. Une cellule à 40 % ne brûlera pas forcément : environ 4 années comparables sur 10 ont connu un feu.',
          'Climatological probability, not a weather forecast. A 40% cell will not necessarily burn: about 4 comparable years out of 10 had a fire.',
        )
      }}
    </p>
  </aside>
</template>

<style scoped>
.prediction-detail {
  position: absolute;
  top: 72px;
  right: 14px;
  z-index: 4;
  width: min(286px, calc(100% - 28px));
  padding: 14px 15px;
  border: 1px solid rgba(255, 196, 107, 0.35);
  border-radius: 13px;
  background: rgba(7, 11, 18, 0.92);
  box-shadow: 0 18px 50px rgba(0, 0, 0, 0.45);
  backdrop-filter: blur(12px);
  display: grid;
  gap: 8px;
  pointer-events: none;
}

.prediction-detail.is-pinned {
  border-color: rgba(255, 196, 107, 0.7);
}

.prediction-detail-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.prediction-detail-eyebrow {
  font-family: var(--font-mono);
  font-size: 0.55rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--dim);
}

.prediction-detail-class {
  font-family: var(--font-mono);
  font-size: 0.56rem;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--gold);
}

.prediction-detail h5 {
  margin: 0;
  font-family: var(--font-display);
  font-size: 1.02rem;
  font-weight: 400;
  line-height: 1.25;
  color: var(--ink);
}

.prediction-detail-probability {
  display: flex;
  align-items: baseline;
  gap: 8px;
}

.prediction-detail-probability strong {
  font-family: var(--font-display);
  font-size: 2rem;
  font-weight: 400;
  line-height: 1;
  color: var(--gold);
}

.prediction-detail-probability span {
  font-size: 0.66rem;
  line-height: 1.3;
  color: var(--muted);
}

.prediction-detail-bar {
  height: 5px;
  border-radius: 999px;
  background: rgba(244, 241, 232, 0.1);
  overflow: hidden;
}

.prediction-detail-bar i {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, #5eead4, #ffc46b, #ff7a3d);
}

.prediction-detail-list {
  margin: 2px 0 0;
  display: grid;
  gap: 4px;
  font-size: 0.68rem;
}

.prediction-detail-list > div {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
}

.prediction-detail-list dt {
  color: var(--dim);
}

.prediction-detail-list dd {
  margin: 0;
  font-family: var(--font-mono);
  color: var(--ink);
  text-align: right;
}

.prediction-detail-note {
  margin: 4px 0 0;
  font-size: 0.63rem;
  line-height: 1.45;
  color: var(--dim);
}

@media (max-width: 760px) {
  .prediction-detail {
    position: static;
    width: 100%;
    margin-top: 10px;
    order: 3;
  }
}
</style>
