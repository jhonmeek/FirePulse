<script setup lang="ts">
import { computed } from 'vue'
import type { Feature, MultiPolygon } from 'geojson'
import type { PredictionCell, PredictionValue } from '@/lib/prediction'
import { probabilityClass } from '@/lib/prediction'
import { t } from '@/lib/i18n'

type ProvinceFeature = Feature<MultiPolygon, { code: string; name: string }>

const props = withDefaults(
  defineProps<{
    cells: PredictionCell[]
    monthValues: Map<number, PredictionValue>
    provinceFeatures: ProvinceFeature[]
    selectedProvince: string
    selectedYear: number
    selectedMonth: number
    hoveredCellIndex?: number | null
    selectedCellIndex?: number | null
    mode?: 'probability' | 'climatology'
  }>(),
  {
    hoveredCellIndex: null,
    selectedCellIndex: null,
    mode: 'probability',
  },
)

const emit = defineEmits<{
  (event: 'hover-cell', index: number | null): void
  (event: 'select-cell', index: number): void
  (event: 'update:mode', value: 'probability' | 'climatology'): void
}>()

const W = 620
const H = 680
const PAD = 18

const visibleCells = computed(() =>
  props.cells
    .map((cell, index) => ({ cell, index }))
    .filter(
      ({ cell }) =>
        props.selectedProvince === 'GA' || cell.province === props.selectedProvince,
    ),
)

const bounds = computed(() => {
  if (!visibleCells.value.length) {
    return { west: 8.4, south: -4.2, east: 14.6, north: 2.6 }
  }
  let west = Infinity
  let south = Infinity
  let east = -Infinity
  let north = -Infinity
  for (const { cell } of visibleCells.value) {
    west = Math.min(west, cell.lon)
    south = Math.min(south, cell.lat)
    east = Math.max(east, cell.lon + 0.25)
    north = Math.max(north, cell.lat + 0.25)
  }
  const padLon = Math.max(0.12, (east - west) * 0.06)
  const padLat = Math.max(0.12, (north - south) * 0.06)
  return {
    west: west - padLon,
    south: south - padLat,
    east: east + padLon,
    north: north + padLat,
  }
})

const projection = computed(() => {
  const b = bounds.value
  const spanX = b.east - b.west
  const spanY = b.north - b.south
  const scale = Math.min((W - PAD * 2) / spanX, (H - PAD * 2) / spanY)
  const offsetX = (W - spanX * scale) / 2
  const offsetY = (H - spanY * scale) / 2
  return { scale, offsetX, offsetY, b }
})

function project(lon: number, lat: number): [number, number] {
  const { scale, offsetX, offsetY, b } = projection.value
  return [offsetX + (lon - b.west) * scale, offsetY + (b.north - lat) * scale]
}

function ringPath(ring: number[][]): string {
  return ring
    .map(([lon, lat], index) => `${index ? 'L' : 'M'}${project(lon!, lat!).map((v) => v.toFixed(2)).join(',')}`)
    .join('')
}

function polygonPath(polygon: number[][][]): string {
  return `${polygon.map(ringPath).join(' ')}Z`
}

function featurePath(feature: ProvinceFeature): string {
  return feature.geometry.coordinates.map(polygonPath).join(' ')
}

const cellRects = computed(() => {
  const { scale } = projection.value
  const cellSize = 0.25 * scale
  return visibleCells.value.map(({ cell, index }) => {
    const [x, y] = project(cell.lon, cell.lat + 0.25)
    const value = props.monthValues.get(index)
    const probability = value?.[props.mode === 'climatology' ? 2 : 1] ?? 0
    return {
      index,
      cell,
      x,
      y,
      size: cellSize,
      probability,
      baseProbability: value?.[2] ?? 0,
      positives: value?.[3] ?? 0,
      years: value?.[4] ?? 0,
      fill: probabilityClass(probability).color,
      opacity:
        probability >= 0.5
          ? 0.95
          : probability >= 0.25
            ? 0.8
            : probability >= 0.1
              ? 0.6
              : 0.35,
    }
  })
})

const selectedFeature = computed(() =>
  props.provinceFeatures.find((feature) => feature.properties.code === props.selectedProvince),
)

const hoveredCell = computed(() => {
  if (props.hoveredCellIndex === null || props.hoveredCellIndex === undefined) return null
  return cellRects.value.find((item) => item.index === props.hoveredCellIndex) ?? null
})
</script>

<template>
  <div class="prediction-map">
    <div class="prediction-map-head">
      <div>
        <span class="prediction-map-eyebrow">
          {{ t('Carte du risque', 'Risk map') }}
        </span>
        <h4>
          {{
            selectedProvince === 'GA'
              ? t('Gabon entier', 'All of Gabon')
              : selectedFeature?.properties.name ?? selectedProvince
          }}
          · {{ selectedMonth }}/{{ selectedYear }}
        </h4>
      </div>
      <div class="prediction-map-tools">
        <div class="prediction-map-modes" role="group" :aria-label="t('Mode de la carte', 'Map mode')">
          <button
            type="button"
            class="prediction-map-mode"
            :class="{ active: mode === 'probability' }"
            @click="$emit('update:mode', 'probability')"
          >
            {{ t('Projection', 'Projection') }}
          </button>
          <button
            type="button"
            class="prediction-map-mode"
            :class="{ active: mode === 'climatology' }"
            @click="$emit('update:mode', 'climatology')"
          >
            {{ t('Climatologie', 'Climatology') }}
          </button>
        </div>
        <span class="prediction-map-hint">
          {{ t('Survolez ou cliquez une cellule', 'Hover or click a cell') }}
        </span>
      </div>
    </div>

    <svg
      class="prediction-map-svg"
      :viewBox="`0 0 ${W} ${H}`"
      role="img"
      :aria-label="t('Carte de probabilité de feu forestier', 'Forest fire probability map')"
    >
      <defs>
        <radialGradient :id="`prediction-map-bg`" cx="50%" cy="42%" r="62%">
          <stop offset="0%" stop-color="#111b26" />
          <stop offset="100%" stop-color="#05070b" />
        </radialGradient>
      </defs>
      <rect :width="W" :height="H" :fill="`url(#prediction-map-bg)`" rx="18" />

      <g class="prediction-provinces">
        <path
          v-for="feature in provinceFeatures"
          :key="feature.properties.code"
          :d="featurePath(feature)"
          class="prediction-province"
          :class="{ 'is-selected': feature.properties.code === selectedProvince }"
        />
      </g>

      <g class="prediction-cells">
        <rect
          v-for="item in cellRects"
          :key="item.cell.id"
          :x="item.x"
          :y="item.y"
          :width="item.size + 0.4"
          :height="item.size + 0.4"
          :fill="item.fill"
          :fill-opacity="item.opacity"
          class="prediction-cell"
          :class="{
            'is-hovered': hoveredCell?.index === item.index,
            'is-selected': selectedCellIndex === item.index,
          }"
          tabindex="0"
          role="button"
          :aria-label="`${item.cell.provinceName}, ${selectedMonth}/${selectedYear} : ${Math.round(item.probability * 100)}%`"
          @mouseenter="emit('hover-cell', item.index)"
          @mouseleave="emit('hover-cell', null)"
          @focus="emit('hover-cell', item.index)"
          @blur="emit('hover-cell', null)"
          @click="emit('select-cell', item.index)"
          @keydown.enter.prevent="emit('select-cell', item.index)"
        >
          <title>
            {{ item.cell.provinceName }} · {{ selectedMonth }}/{{ selectedYear }} ·
            {{ Math.round(item.probability * 100) }}%
          </title>
        </rect>
      </g>

      <g v-if="selectedFeature && selectedProvince !== 'GA'" class="prediction-selected-outline">
        <path :d="featurePath(selectedFeature)" />
      </g>
    </svg>

    <div class="prediction-map-legend">
      <span class="prediction-legend-label">{{ t('Probabilité', 'Probability') }}</span>
      <span class="prediction-legend-item"><i style="background: #637080"></i>0–10 %</span>
      <span class="prediction-legend-item"><i style="background: #5eead4"></i>10–25 %</span>
      <span class="prediction-legend-item"><i style="background: #ffc46b"></i>25–50 %</span>
      <span class="prediction-legend-item"><i style="background: #ff7a3d"></i>≥ 50 %</span>
    </div>
  </div>
</template>

<style scoped>
.prediction-map {
  position: relative;
  display: grid;
  gap: 10px;
  min-width: 0;
}

.prediction-map-head {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  justify-content: space-between;
  gap: 8px 16px;
}

.prediction-map-eyebrow {
  display: block;
  font-family: var(--font-mono);
  font-size: 0.6rem;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--dim);
}

.prediction-map-head h4 {
  margin: 3px 0 0;
  font-family: var(--font-display);
  font-size: clamp(1.1rem, 1.6vw, 1.35rem);
  font-weight: 400;
  color: var(--ink);
}

.prediction-map-tools {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 12px;
}

.prediction-map-modes {
  display: inline-flex;
  gap: 3px;
  padding: 3px;
  border: 1px solid var(--line-strong);
  border-radius: 8px;
  background: rgba(244, 241, 232, 0.03);
}

.prediction-map-mode {
  padding: 4px 8px;
  border: 0;
  border-radius: 5px;
  background: transparent;
  color: var(--muted);
  font-size: 0.62rem;
  cursor: pointer;
}

.prediction-map-mode.active {
  background: var(--ink);
  color: #05070b;
  font-weight: 600;
}

.prediction-map-hint {
  font-size: 0.7rem;
  color: var(--dim);
}

.prediction-map-svg {
  width: 100%;
  height: auto;
  border-radius: 18px;
  border: 1px solid var(--line);
  background: #05070b;
  overflow: hidden;
}

.prediction-province {
  fill: rgba(244, 241, 232, 0.025);
  stroke: rgba(244, 241, 232, 0.18);
  stroke-width: 1;
  vector-effect: non-scaling-stroke;
}

.prediction-province.is-selected {
  fill: rgba(255, 196, 107, 0.035);
  stroke: rgba(255, 196, 107, 0.55);
  stroke-width: 1.6;
}

.prediction-cell {
  stroke: rgba(5, 7, 11, 0.55);
  stroke-width: 0.5;
  cursor: pointer;
  transition:
    fill-opacity 0.2s ease,
    stroke 0.2s ease;
  vector-effect: non-scaling-stroke;
}

.prediction-cell:hover,
.prediction-cell.is-hovered,
.prediction-cell.is-selected {
  stroke: var(--ink);
  stroke-width: 1.4;
}

.prediction-cell.is-selected {
  stroke: var(--gold);
  stroke-width: 1.8;
}

.prediction-selected-outline path {
  fill: none;
  stroke: rgba(255, 196, 107, 0.85);
  stroke-width: 2;
  pointer-events: none;
  vector-effect: non-scaling-stroke;
}

.prediction-map-legend {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px 12px;
  font-size: 0.68rem;
  color: var(--muted);
}

.prediction-legend-label {
  font-family: var(--font-mono);
  font-size: 0.58rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--dim);
}

.prediction-legend-item {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}

.prediction-legend-item i {
  width: 9px;
  height: 9px;
  border-radius: 2px;
  display: block;
}
</style>
