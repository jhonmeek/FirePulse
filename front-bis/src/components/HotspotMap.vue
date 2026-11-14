<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, useTemplateRef, watch } from 'vue'
import {
  Map as MlMap,
  NavigationControl,
  Popup,
  ScaleControl,
  setWorkerUrl,
  type GeoJSONSource,
  type MapGeoJSONFeature,
  type MapMouseEvent,
  type StyleSpecification,
} from 'maplibre-gl'
import type { Feature, FeatureCollection, LineString } from 'geojson'
import 'maplibre-gl/dist/maplibre-gl.css'
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?url'
import {
  YEARS,
  buildGrid,
  cellCentroid,
  countryFeature,
  formatCount,
  provinceFeatures,
} from '@/lib/data'
import { provenance } from '@/lib/provenance'
import type { GridBundle } from '@/lib/types'

setWorkerUrl(workerUrl)

const props = defineProps<{ reducedMotion?: boolean }>()

const container = useTemplateRef<HTMLDivElement>('container')
const yearStart = ref(2000)
const yearEnd = ref(2025)
const filterStatic = ref(true)
const mapReady = ref(false)
const stats = ref({ cells: 0, total: 0, max: 1 })
const showStatic = ref(true)

let map: MlMap | null = null
let popup: Popup | null = null
let resizeObserver: ResizeObserver | null = null
let bundle: GridBundle | null = null
let unmounted = false

const START_OPTIONS = YEARS.filter((y) => y <= 2024)
const END_OPTIONS = YEARS.filter((y) => y >= 2001)

const periodLabel = computed(() =>
  yearStart.value === 2000 && yearEnd.value === 2025
    ? '2000 → 2025'
    : `${yearStart.value} → ${yearEnd.value}`,
)

const STYLE: StyleSpecification = {
  version: 8,
  sources: {},
  layers: [{ id: 'bg', type: 'background', paint: { 'background-color': '#05080d' } }],
}

function buildGraticule(): FeatureCollection<LineString> {
  const features: Feature<LineString>[] = []
  for (let lon = 6; lon <= 17; lon += 1) {
    features.push({
      type: 'Feature',
      geometry: {
        type: 'LineString',
        coordinates: [
          [lon, -5],
          [lon, 3],
        ],
      },
      properties: {},
    })
  }
  for (let lat = -5; lat <= 3; lat += 1) {
    features.push({
      type: 'Feature',
      geometry: {
        type: 'LineString',
        coordinates: [
          [6, lat],
          [17, lat],
        ],
      },
      properties: {},
    })
  }
  return { type: 'FeatureCollection', features }
}

function gridColorExpression(max: number) {
  const stops: [number, string][] = [
    [0, '#24110e'],
    [Math.sqrt(max * 0.05), '#4d1f15'],
    [Math.sqrt(max * 0.18), '#8a2f17'],
    [Math.sqrt(max * 0.38), '#c7471c'],
    [Math.sqrt(max * 0.62), '#ef6a2b'],
    [Math.sqrt(max * 0.82), '#ff9e53'],
    [Math.sqrt(max), '#ffe0a3'],
  ]
  const expression: unknown[] = ['interpolate', ['linear'], ['sqrt', ['get', 'count']]]
  for (const [stop, color] of stops) expression.push(stop, color)
  return expression as never
}

function updateData() {
  if (!map || !mapReady.value) return
  if (yearStart.value > yearEnd.value) yearEnd.value = yearStart.value
  bundle = buildGrid(yearStart.value, yearEnd.value, filterStatic.value)
  stats.value = { cells: bundle.cells, total: bundle.total, max: bundle.max }
  ;(map.getSource('grid') as GeoJSONSource | undefined)?.setData(bundle.grid)
  ;(map.getSource('static') as GeoJSONSource | undefined)?.setData(bundle.statics)
  if (map.getLayer('grid-fill')) {
    map.setPaintProperty('grid-fill', 'fill-color', gridColorExpression(bundle.max))
  }
  updateLegend()
}

const legendColors = computed(() => {
  const max = stats.value.max || 1
  return [0, 0.18, 0.38, 0.62, 0.82, 1].map((t) => {
    const stops: [number, [number, number, number]][] = [
      [0, [36, 17, 14]],
      [0.18, [138, 47, 23]],
      [0.38, [199, 71, 28]],
      [0.62, [239, 106, 43]],
      [0.82, [255, 158, 83]],
      [1, [255, 224, 163]],
    ]
    const value = Math.sqrt(max * t * t)
    // Interpolation simple pour la légende (même logique que la carte).
    const s = Math.sqrt(value / max)
    let c0 = stops[0]!
    let c1 = stops[stops.length - 1]!
    for (let i = 1; i < stops.length; i++) {
      if (s <= stops[i]![0]) {
        c0 = stops[i - 1]!
        c1 = stops[i]!
        break
      }
    }
    const local = Math.max(0, Math.min(1, (s - c0[0]) / Math.max(0.0001, c1[0] - c0[0])))
    const rgb = c0[1].map((v, i) => Math.round(v + (c1[1][i]! - v) * local))
    return `rgb(${rgb.join(', ')})`
  })
})

function updateLegend() {
  // La légende est réactive via `stats`; ce hook est conservé pour MapLibre.
}

function popupHtml(title: string, rows: [string, string][]): string {
  return `
    <div class="fp-popup">
      <p class="fp-popup-title">${title}</p>
      <dl>
        ${rows.map(([k, v]) => `<div><dt>${k}</dt><dd>${v}</dd></div>`).join('')}
      </dl>
    </div>
  `
}

function onGridHover(event: MapMouseEvent & { features?: MapGeoJSONFeature[] }) {
  if (!map) return
  map.getCanvas().style.cursor = 'pointer'
  const feature = event.features?.[0]
  if (!feature) return
  const p = feature.properties as {
    cell_id: string
    count: number
    modis: number
    snpp: number
    noaa20: number
    months: number
  }
  const { lat, lon } = cellCentroid(p.cell_id, 0.25)
  popup
    ?.setLngLat(event.lngLat)
    .setHTML(
      popupHtml(`Cellule 0,25° — ${lat.toFixed(2)}, ${lon.toFixed(2)}`, [
        ['Détections', formatCount(p.count)],
        ['MODIS', formatCount(p.modis)],
        ['VIIRS S-NPP', formatCount(p.snpp)],
        ['NOAA-20', formatCount(p.noaa20)],
        ['Mois actifs', formatCount(p.months)],
      ]),
    )
    .addTo(map)
}

function onStaticHover(event: MapMouseEvent & { features?: MapGeoJSONFeature[] }) {
  if (!map) return
  map.getCanvas().style.cursor = 'pointer'
  const feature = event.features?.[0]
  if (!feature) return
  const p = feature.properties as {
    cell_id: string
    type23: number
    activeMonths: number
    reason: string
  }
  popup
    ?.setLngLat(event.lngLat)
    .setHTML(
      popupHtml('Site statique 0,05°', [
        ['Type 2/3', formatCount(p.type23)],
        ['Mois actifs S-NPP', formatCount(p.activeMonths)],
        ['Motif', p.reason.replaceAll('_', ' ')],
      ]),
    )
    .addTo(map)
}

function onLeave() {
  if (!map) return
  map.getCanvas().style.cursor = ''
  popup?.remove()
}

function toggleStatic() {
  showStatic.value = !showStatic.value
  if (!map || !mapReady.value) return
  map.setLayoutProperty('static-fill', 'visibility', showStatic.value ? 'visible' : 'none')
  map.setLayoutProperty('static-line', 'visibility', showStatic.value ? 'visible' : 'none')
}

function resetView() {
  if (!map || !mapReady.value) return
  map.fitBounds(
    [
      [8.7, -4.0],
      [14.6, 2.4],
    ],
    { padding: 44, duration: props.reducedMotion ? 0 : 1200, pitch: 26, bearing: -8 },
  )
}

onMounted(() => {
  const el = container.value
  if (!el) return

  map = new MlMap({
    container: el,
    style: STYLE,
    bounds: [
      [8.7, -4.0],
      [14.6, 2.4],
    ],
    fitBoundsOptions: { padding: 44 },
    pitch: 26,
    bearing: -8,
    attributionControl: false,
    maxPitch: 60,
  })
  if (import.meta.env.DEV) {
    ;(window as unknown as { __fpMap?: MlMap }).__fpMap = map
  }
  map.addControl(new NavigationControl({ showCompass: false }), 'top-right')
  map.addControl(new ScaleControl({ unit: 'metric' }), 'bottom-left')
  popup = new Popup({ closeButton: false, closeOnClick: false, offset: 12, className: 'fp-popup-wrap' })

  map.on('load', () => {
    if (unmounted || !map) return
    const regions = {
      type: 'FeatureCollection' as const,
      features: [countryFeature, ...provinceFeatures].filter(Boolean),
    }

    map.addSource('graticule', { type: 'geojson', data: buildGraticule() })
    map.addSource('regions', { type: 'geojson', data: regions as never })
    map.addSource('grid', {
      type: 'geojson',
      data: { type: 'FeatureCollection', features: [] },
    })
    map.addSource('static', {
      type: 'geojson',
      data: { type: 'FeatureCollection', features: [] },
    })

    map.addLayer({
      id: 'graticule',
      type: 'line',
      source: 'graticule',
      paint: {
        'line-color': '#2f7b89',
        'line-width': 0.5,
        'line-opacity': 0.14,
      },
    })
    map.addLayer({
      id: 'country-fill',
      type: 'fill',
      source: 'regions',
      filter: ['==', ['get', 'region_type'], 'country'],
      paint: { 'fill-color': '#071a18', 'fill-opacity': 0.65 },
    })
    map.addLayer({
      id: 'grid-fill',
      type: 'fill',
      source: 'grid',
      paint: {
        'fill-color': gridColorExpression(1),
        'fill-opacity': 0.82,
      },
    })
    map.addLayer({
      id: 'grid-line',
      type: 'line',
      source: 'grid',
      paint: {
        'line-color': '#ffe0a3',
        'line-width': 0.3,
        'line-opacity': 0.22,
      },
    })
    map.addLayer({
      id: 'province-line',
      type: 'line',
      source: 'regions',
      filter: ['!=', ['get', 'region_type'], 'country'],
      paint: {
        'line-color': '#94a3b8',
        'line-width': 0.7,
        'line-opacity': 0.32,
        'line-dasharray': [2, 2],
      },
    })
    map.addLayer({
      id: 'country-glow',
      type: 'line',
      source: 'regions',
      filter: ['==', ['get', 'region_type'], 'country'],
      paint: {
        'line-color': '#5eead4',
        'line-width': 7,
        'line-blur': 6,
        'line-opacity': 0.22,
      },
    })
    map.addLayer({
      id: 'country-line',
      type: 'line',
      source: 'regions',
      filter: ['==', ['get', 'region_type'], 'country'],
      paint: {
        'line-color': '#8ef7e4',
        'line-width': 1.4,
        'line-opacity': 0.95,
      },
    })
    map.addLayer({
      id: 'static-fill',
      type: 'fill',
      source: 'static',
      paint: { 'fill-color': '#22d3ee', 'fill-opacity': 0.9 },
    })
    map.addLayer({
      id: 'static-line',
      type: 'line',
      source: 'static',
      paint: { 'line-color': '#cffafe', 'line-width': 0.8, 'line-opacity': 0.9 },
    })

    map.on('mousemove', 'grid-fill', onGridHover)
    map.on('mouseleave', 'grid-fill', onLeave)
    map.on('mousemove', 'static-fill', onStaticHover)
    map.on('mouseleave', 'static-fill', onLeave)

    mapReady.value = true
    updateData()

    if (!props.reducedMotion) {
      map.fitBounds(
        [
          [8.7, -4.0],
          [14.6, 2.4],
        ],
        { padding: 44, duration: 1900, pitch: 26, bearing: -8 },
      )
    }
  })

  resizeObserver = new ResizeObserver(() => map?.resize())
  resizeObserver.observe(el)
})

onBeforeUnmount(() => {
  unmounted = true
  resizeObserver?.disconnect()
  popup?.remove()
  map?.remove()
  map = null
})

watch([yearStart, yearEnd, filterStatic], updateData)
watch(yearStart, (value) => {
  if (value > yearEnd.value) yearEnd.value = value
})
</script>

<template>
  <div class="map-wrap">
    <div ref="container" class="map-canvas" role="img" aria-label="Carte des points chauds du Gabon"></div>
    <div class="map-glow" aria-hidden="true"></div>

    <div class="map-controls">
      <div class="map-control-group">
        <label class="map-label" for="year-start">Période</label>
        <div class="year-selects">
          <select id="year-start" v-model.number="yearStart">
            <option v-for="year in START_OPTIONS" :key="year" :value="year">{{ year }}</option>
          </select>
          <span>→</span>
          <select v-model.number="yearEnd">
            <option v-for="year in END_OPTIONS" :key="year" :value="year">{{ year }}</option>
          </select>
        </div>
      </div>

      <button
        type="button"
        class="map-toggle"
        :class="{ active: filterStatic }"
        :aria-pressed="filterStatic"
        @click="filterStatic = !filterStatic"
      >
        <span class="toggle-dot"></span>
        {{ filterStatic ? 'Feux de végétation' : 'Toutes anomalies' }}
      </button>

      <button
        type="button"
        class="map-toggle"
        :class="{ active: showStatic }"
        :aria-pressed="showStatic"
        @click="toggleStatic"
      >
        <span class="toggle-dot cool"></span>
        Sites statiques
      </button>
    </div>

    <div class="map-legend">
      <div class="map-legend-head">
        <span class="tiny-label">Détections / cellule</span>
        <span class="mono">{{ periodLabel }}</span>
      </div>
      <div class="map-legend-scale">
        <span
          v-for="(color, index) in legendColors"
          :key="index"
          class="legend-swatch"
          :style="{ background: color }"
        ></span>
      </div>
      <div class="map-legend-values">
        <span>0</span>
        <span>{{ formatCount(stats.max) }}</span>
      </div>
    </div>

    <div class="map-stats">
      <div>
        <span class="map-stat-value">{{ formatCount(stats.cells) }}</span>
        <span class="map-stat-label">cellules actives</span>
      </div>
      <div>
        <span class="map-stat-value">{{ formatCount(stats.total) }}</span>
        <span class="map-stat-label">détections</span>
      </div>
      <button type="button" class="map-reset" @click="resetView">Recentrer</button>
    </div>

    <p class="map-caption">
      Agrégat {{ String(provenance.gridDeg).replace('.', ',') }}° sur la période. Une cellule
      colorée n'est pas un incendie unique. Les sites statiques (bleu) sont des torchères ou des
      sources industrielles persistantes.
    </p>
  </div>
</template>

<style scoped>
.map-wrap {
  position: relative;
  overflow: hidden;
  border: 1px solid var(--line);
  border-radius: var(--radius);
  background: #05080d;
  min-height: 560px;
  box-shadow:
    0 1px 0 rgba(255, 255, 255, 0.04) inset,
    0 40px 100px -50px rgba(0, 0, 0, 0.9);
}

.map-canvas {
  position: absolute;
  inset: 0;
}

.map-glow {
  position: absolute;
  inset: 0;
  pointer-events: none;
  background:
    radial-gradient(ellipse 50% 45% at 52% 48%, rgba(255, 94, 26, 0.14), transparent 65%),
    radial-gradient(ellipse 60% 40% at 50% 100%, rgba(5, 7, 11, 0.8), transparent 70%);
  mix-blend-mode: screen;
}

.map-controls {
  position: absolute;
  top: 14px;
  left: 14px;
  z-index: 4;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  max-width: calc(100% - 90px);
}

.map-control-group {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 7px 10px;
  border: 1px solid var(--line-strong);
  border-radius: 10px;
  background: rgba(5, 7, 11, 0.78);
  backdrop-filter: blur(12px);
}

.map-label {
  font-family: var(--font-mono);
  font-size: 0.54rem;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--dim);
}

.year-selects {
  display: flex;
  align-items: center;
  gap: 4px;
  font-family: var(--font-mono);
  font-size: 0.68rem;
  color: var(--muted);
}

.year-selects select {
  border: 0;
  background: transparent;
  color: var(--ink);
  font-family: var(--font-mono);
  font-size: 0.68rem;
  padding: 2px 1px;
  cursor: pointer;
}

.year-selects select:focus-visible {
  outline: 1px solid var(--gold);
}

.map-toggle {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 8px 10px;
  border: 1px solid var(--line-strong);
  border-radius: 10px;
  background: rgba(5, 7, 11, 0.78);
  color: var(--muted);
  font-family: var(--font-mono);
  font-size: 0.58rem;
  letter-spacing: 0.04em;
  cursor: pointer;
  backdrop-filter: blur(12px);
  transition:
    color 0.25s ease,
    border-color 0.25s ease,
    background 0.25s ease;
}

.map-toggle:hover {
  color: var(--ink);
  border-color: var(--muted);
}

.map-toggle.active {
  color: var(--ink);
  border-color: rgba(255, 196, 107, 0.45);
  background: rgba(255, 196, 107, 0.08);
}

.toggle-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--ember);
  box-shadow: 0 0 8px var(--ember);
  opacity: 0.4;
  transition: opacity 0.25s ease;
}

.map-toggle.active .toggle-dot {
  opacity: 1;
}

.toggle-dot.cool {
  background: var(--cyan);
  box-shadow: 0 0 8px var(--cyan);
}

.map-legend {
  position: absolute;
  right: 14px;
  bottom: 14px;
  z-index: 4;
  width: 190px;
  padding: 10px 12px;
  border: 1px solid var(--line-strong);
  border-radius: 10px;
  background: rgba(5, 7, 11, 0.82);
  backdrop-filter: blur(12px);
}

.map-legend-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 7px;
}

.map-legend-head .mono {
  font-size: 0.54rem;
  color: var(--gold);
}

.map-legend-scale {
  display: flex;
  height: 7px;
  border-radius: 4px;
  overflow: hidden;
}

.legend-swatch {
  flex: 1;
}

.map-legend-values {
  display: flex;
  justify-content: space-between;
  margin-top: 4px;
  font-family: var(--font-mono);
  font-size: 0.52rem;
  color: var(--dim);
}

.map-stats {
  position: absolute;
  left: 14px;
  bottom: 14px;
  z-index: 4;
  display: flex;
  align-items: flex-end;
  gap: 18px;
  padding: 9px 12px;
  border: 1px solid var(--line-strong);
  border-radius: 10px;
  background: rgba(5, 7, 11, 0.82);
  backdrop-filter: blur(12px);
}

.map-stats > div {
  display: flex;
  flex-direction: column;
  gap: 1px;
}

.map-stat-value {
  font-family: var(--font-display);
  font-variant-numeric: tabular-nums;
  font-size: 1.1rem;
  line-height: 1;
}

.map-stat-label {
  font-family: var(--font-mono);
  font-size: 0.48rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--dim);
}

.map-reset {
  padding: 4px 8px;
  border: 1px solid var(--line);
  border-radius: 6px;
  background: transparent;
  color: var(--muted);
  font-family: var(--font-mono);
  font-size: 0.52rem;
  letter-spacing: 0.04em;
  cursor: pointer;
  transition:
    color 0.2s ease,
    border-color 0.2s ease;
}

.map-reset:hover {
  color: var(--ink);
  border-color: var(--muted);
}

.map-caption {
  position: absolute;
  top: 70px;
  left: 16px;
  z-index: 3;
  max-width: 340px;
  padding: 8px 10px;
  border-left: 2px solid rgba(255, 196, 107, 0.45);
  background: linear-gradient(90deg, rgba(5, 7, 11, 0.82), transparent);
  font-size: 0.64rem;
  line-height: 1.55;
  color: var(--muted);
  pointer-events: none;
}

@media (max-width: 760px) {
  .map-wrap {
    min-height: 480px;
  }
  .map-controls {
    max-width: calc(100% - 24px);
  }
  .map-caption {
    display: none;
  }
  .map-legend {
    width: 150px;
  }
  .map-stats {
    gap: 12px;
  }
}
</style>

<style>
.fp-popup-wrap .maplibregl-popup-content {
  padding: 0;
  background: transparent;
  box-shadow: none;
}

.fp-popup {
  min-width: 170px;
  padding: 10px 12px;
  border: 1px solid rgba(244, 241, 232, 0.22);
  border-radius: 10px;
  background: rgba(7, 11, 18, 0.95);
  color: #f4f1e8;
  font-family: 'Inter Variable', system-ui, sans-serif;
  box-shadow: 0 18px 40px -18px rgba(0, 0, 0, 0.9);
}

.fp-popup-title {
  margin: 0 0 7px;
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  font-size: 0.56rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #ffc46b;
}

.fp-popup dl {
  display: grid;
  gap: 3px;
  margin: 0;
}

.fp-popup dl > div {
  display: flex;
  justify-content: space-between;
  gap: 14px;
}

.fp-popup dt {
  font-size: 0.64rem;
  color: #9ba8b7;
}

.fp-popup dd {
  margin: 0;
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  font-size: 0.64rem;
  color: #f4f1e8;
}

.fp-popup-wrap .maplibregl-popup-tip {
  border-top-color: rgba(7, 11, 18, 0.95);
}
</style>
