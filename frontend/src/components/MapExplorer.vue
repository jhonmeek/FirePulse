<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, shallowRef, useTemplateRef, watch } from 'vue'
import { storeToRefs } from 'pinia'
import {
  Map as MlMap,
  NavigationControl,
  Popup,
  ScaleControl,
  type GeoJSONSource,
  type LngLat,
  setWorkerUrl,
  type MapMouseEvent,
  type StyleSpecification,
} from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
// MapLibre 6 + bundler : le worker doit être fourni explicitement. Vite 8 (Rolldown) : `?url`
// (doc MapLibre, exemples bundler) ; `?worker&url` y produit un module qui échoue en worker,
// sinon « Worker failed to load » et aucune couche ne s'affiche.
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?url'

setWorkerUrl(workerUrl)
import { fetchHotspots, fetchRegions } from '@/services/api'
import { useFiltersStore } from '@/stores/filters'
import type {
  BBox,
  GridCellSummaryProps,
  HotspotsResponse,
  Region,
  StaticFlareMaskProps,
} from '@/types/api'
import {
  MAP_METRICS,
  STATIC_REASON_LABELS,
  bboxFromCorners,
  bboxPolygon,
  defaultMetric,
  gridCellSummary,
  gridColorExpression,
  gridStops,
  maxMetric,
  metricCoversRange,
  type MapMetric,
} from '@/utils/map'
import { formatCount } from '@/utils/calendar'

const filters = useFiltersStore()
const { region, bbox, yearRange, filterStatic, start, end } = storeToRefs(filters)

// ---------------------------------------------------------------- données
const regions = shallowRef<Region[]>([])
const hotspots = shallowRef<HotspotsResponse | null>(null)
const loading = ref(false)
const error = ref<string | null>(null)
let requestId = 0

const query = computed(() => ({
  ...(bbox.value ? { bbox: bbox.value } : { region: region.value }),
  start: start.value,
  end: end.value,
  filter_static: filterStatic.value,
}))

async function loadHotspots() {
  const id = ++requestId
  loading.value = true
  error.value = null
  try {
    const res = await fetchHotspots(query.value)
    if (id === requestId) hotspots.value = res
  } catch (e) {
    if (id === requestId) error.value = e instanceof Error ? e.message : String(e)
  } finally {
    if (id === requestId) loading.value = false
  }
}
watch(query, loadHotspots, { deep: true, immediate: true })

const grid = computed(
  () =>
    (hotspots.value?.features ?? []).filter((f) => f.properties.layer === 'grid_cell_summary') as {
      type: 'Feature'
      geometry: GeoJSON.Polygon
      properties: GridCellSummaryProps
    }[],
)
const statics = computed(() =>
  (hotspots.value?.features ?? []).filter((f) => f.properties.layer === 'static_flare_mask'),
)

// ---------------------------------------------------------------- réglages d'affichage
const metric = ref<MapMetric>(defaultMetric(yearRange.value))
watch(yearRange, (r) => (metric.value = defaultMetric(r)))
const max = computed(() => maxMetric(grid.value, metric.value))
const legend = computed(() => gridStops(max.value))
const showStatic = ref(true)
const showBasemap = ref(true)
const partialMetric = computed(() => !metricCoversRange(metric.value, yearRange.value))

// ---------------------------------------------------------------- carte
const container = useTemplateRef<HTMLDivElement>('container')
let map: MlMap | null = null
const mapReady = ref(false)

const EMPTY = { type: 'FeatureCollection' as const, features: [] }

/**
 * Fond de carte OpenFreeMap (sans clé ni inscription ; CARTO exige désormais une clé).
 * Récupéré avec un délai court : hors ligne, la carte démarre sur un fond uni et la
 * grille, les sites statiques et les contours (servis par l'API) restent affichés.
 */
const BASEMAP_STYLE_URL = 'https://tiles.openfreemap.org/styles/positron'
const FALLBACK_STYLE: StyleSpecification = {
  version: 8,
  sources: {},
  layers: [{ id: 'bg', type: 'background', paint: { 'background-color': '#f5f5f4' } }],
}
const basemapAvailable = ref(true)
/** Couches du fond (toutes celles du style d'origine), pour le bouton « Fond de carte ». */
let basemapLayerIds: string[] = []

async function loadBasemapStyle(): Promise<StyleSpecification> {
  try {
    const res = await fetch(BASEMAP_STYLE_URL, { signal: AbortSignal.timeout(4000) })
    if (!res.ok) throw new Error(String(res.status))
    return (await res.json()) as StyleSpecification
  } catch {
    basemapAvailable.value = false
    return FALLBACK_STYLE
  }
}

let unmounted = false

onMounted(async () => {
  const el = container.value
  if (!el) return
  const style = await loadBasemapStyle()
  // Le composant a pu être démonté pendant le chargement du style (navigation, HMR).
  if (unmounted || !el.isConnected) return
  const m = new MlMap({
    container: el,
    style,
    bounds: [8.7, -4.0, 14.6, 2.4],
    fitBoundsOptions: { padding: 20 },
    // L'attribution OpenFreeMap / OpenMapTiles / OSM est fournie par les sources du style.
    attributionControl: { compact: true },
  })
  basemapLayerIds = (style.layers ?? []).map((l) => l.id).filter((id) => id !== 'bg')
  map = m
  m.addControl(new NavigationControl({ showCompass: false }), 'top-right')
  m.addControl(new ScaleControl({ unit: 'metric' }), 'bottom-left')

  m.on('load', () => {
    m.addSource('regions', { type: 'geojson', data: EMPTY })
    m.addSource('grid', { type: 'geojson', data: EMPTY })
    m.addSource('static', { type: 'geojson', data: EMPTY })
    m.addSource('zone', { type: 'geojson', data: EMPTY })
    m.addLayer({
      id: 'grid-fill',
      type: 'fill',
      source: 'grid',
      paint: { 'fill-color': '#fde68a', 'fill-opacity': 0.78 },
    })
    m.addLayer({
      id: 'grid-line',
      type: 'line',
      source: 'grid',
      paint: { 'line-color': '#ffffff', 'line-width': 0.4, 'line-opacity': 0.6 },
    })
    m.addLayer({
      id: 'regions-line',
      type: 'line',
      source: 'regions',
      paint: {
        'line-color': '#44403c',
        'line-width': ['case', ['==', ['get', 'region_type'], 'country'], 1.6, 0.6],
        'line-dasharray': [
          'case',
          ['==', ['get', 'region_type'], 'country'],
          ['literal', [1]],
          ['literal', [2, 2]],
        ],
      },
    })
    // Bleu Okabe-Ito : distinct de la palette YlOrRd pour les daltoniens.
    m.addLayer({
      id: 'static-fill',
      type: 'fill',
      source: 'static',
      paint: { 'fill-color': '#0072B2', 'fill-opacity': 0.85 },
    })
    m.addLayer({
      id: 'zone-line',
      type: 'line',
      source: 'zone',
      paint: { 'line-color': '#1c1917', 'line-width': 2, 'line-dasharray': [3, 2] },
    })
    mapReady.value = true
    refreshAll()
  })

  m.on('click', onMapClick)
  m.on('mousedown', onDrawStart)
  m.on('mousemove', onDrawMove)
  m.on('mouseup', onDrawEnd)
  for (const layer of ['grid-fill', 'static-fill']) {
    m.on('mouseenter', layer, () => !drawing.value && (m.getCanvas().style.cursor = 'pointer'))
    m.on('mouseleave', layer, () => !drawing.value && (m.getCanvas().style.cursor = ''))
  }

  try {
    regions.value = (await fetchRegions(true)).regions
  } catch {
    // Les contours sont un confort : la grille reste lisible sans eux.
  }
})

onBeforeUnmount(() => {
  unmounted = true
  map?.remove()
  map = null
})

function setData(id: string, data: unknown) {
  ;(map?.getSource(id) as GeoJSONSource | undefined)?.setData(data as GeoJSON.GeoJSON)
}

function refreshAll() {
  if (!map || !mapReady.value) return
  setData('regions', {
    type: 'FeatureCollection',
    features: regions.value
      .filter((r) => r.geometry)
      .map((r) => ({
        type: 'Feature',
        geometry: r.geometry,
        properties: { code: r.code, region_type: r.region_type },
      })),
  })
  setData('grid', { type: 'FeatureCollection', features: grid.value })
  setData('static', { type: 'FeatureCollection', features: statics.value })
  setData(
    'zone',
    bbox.value ? { type: 'Feature', geometry: bboxPolygon(bbox.value), properties: {} } : EMPTY,
  )
  map.setPaintProperty(
    'grid-fill',
    'fill-color',
    gridColorExpression(metric.value, max.value) as never,
  )
  map.setLayoutProperty('static-fill', 'visibility', showStatic.value ? 'visible' : 'none')
  for (const id of basemapLayerIds) {
    map.setLayoutProperty(id, 'visibility', showBasemap.value ? 'visible' : 'none')
  }
}
watch([regions, grid, statics, metric, max, showStatic, showBasemap, bbox], refreshAll)

/** Cadre la zone : bbox dessinée, sinon emprise de la région choisie. */
function fitArea() {
  if (!map) return
  const target: BBox | undefined =
    bbox.value ?? regions.value.find((r) => r.code === region.value)?.bbox
  if (target)
    map.fitBounds(
      [
        [target[0], target[1]],
        [target[2], target[3]],
      ],
      { padding: 24, duration: 600 },
    )
}
watch([region, bbox, regions], fitArea)

// ---------------------------------------------------------------- info-bulles (contenu en texte, pas de HTML injecté)
let popup: Popup | null = null
function showPopup(at: LngLat, lines: string[]) {
  const el = document.createElement('div')
  el.className = 'text-xs leading-5 text-stone-800'
  for (const [i, line] of lines.entries()) {
    const p = document.createElement('p')
    if (i === 0) p.className = 'font-semibold'
    p.textContent = line
    el.appendChild(p)
  }
  popup?.remove()
  popup = new Popup({ closeButton: true, maxWidth: '260px' })
    .setLngLat(at)
    .setDOMContent(el)
    .addTo(map!)
}

function onMapClick(e: MapMouseEvent) {
  if (drawing.value || !map) return
  const hit = map.queryRenderedFeatures(e.point, { layers: ['static-fill', 'grid-fill'] })[0]
  if (!hit) return
  if (hit.layer.id === 'static-fill') {
    const p = hit.properties as StaticFlareMaskProps
    showPopup(e.lngLat, [
      'Site statique exclu (cellule 0,05°)',
      STATIC_REASON_LABELS[p.reason] ?? p.reason,
      `${formatCount(p.type23_count)} détections type 2/3`,
      `${p.active_months_snpp} mois actifs en S-NPP`,
    ])
  } else {
    showPopup(e.lngLat, gridCellSummary(hit.properties as GridCellSummaryProps))
  }
}

// ---------------------------------------------------------------- dessin d'une zone (rectangle)
const drawing = ref(false)
let drawStart: LngLat | null = null

function toggleDrawing() {
  drawing.value = !drawing.value
  if (!map) return
  map.getCanvas().style.cursor = drawing.value ? 'crosshair' : ''
  if (drawing.value) {
    map.dragPan.disable()
    popup?.remove()
  } else {
    map.dragPan.enable()
    drawStart = null
    setData(
      'zone',
      bbox.value ? { type: 'Feature', geometry: bboxPolygon(bbox.value), properties: {} } : EMPTY,
    )
  }
}

function onDrawStart(e: MapMouseEvent) {
  if (drawing.value) drawStart = e.lngLat
}
function onDrawMove(e: MapMouseEvent) {
  if (!drawing.value || !drawStart) return
  const live = bboxFromCorners(drawStart, e.lngLat, 0)
  if (live) setData('zone', { type: 'Feature', geometry: bboxPolygon(live), properties: {} })
}
function onDrawEnd(e: MapMouseEvent) {
  if (!drawing.value || !drawStart) return
  const box = bboxFromCorners(drawStart, e.lngLat)
  drawStart = null
  toggleDrawing()
  if (box) applyBBox(box)
  else formError.value = 'Zone trop petite (minimum 0,05° de côté).'
}
function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape' && drawing.value) toggleDrawing()
}

// ---------------------------------------------------------------- saisie lat/lon (alternative clavier au dessin)
const form = ref({ w: '', s: '', e: '', n: '' })
const formError = ref<string | null>(null)
watch(
  bbox,
  (b) => {
    if (b) form.value = { w: String(b[0]), s: String(b[1]), e: String(b[2]), n: String(b[3]) }
  },
  { immediate: true },
)

function applyBBox(box: BBox) {
  formError.value = null
  try {
    filters.selectBBox(box)
    filters.selectedMonth = null
  } catch (err) {
    formError.value = err instanceof Error ? err.message : String(err)
  }
}
function submitForm() {
  const vals = [form.value.w, form.value.s, form.value.e, form.value.n].map((v) =>
    Number(String(v).replace(',', '.')),
  )
  if (vals.some((v) => !Number.isFinite(v))) {
    formError.value = 'Saisir quatre nombres (degrés décimaux).'
    return
  }
  const [w, s, e, n] = vals as BBox
  if (!(w < e && s < n)) {
    formError.value = 'L’ouest doit être inférieur à l’est, et le sud inférieur au nord.'
    return
  }
  applyBBox(vals as BBox)
}
function clearZone() {
  filters.selectRegion(region.value)
  formError.value = null
}

const summary = computed(() => {
  if (!hotspots.value) return ''
  const total = grid.value.reduce(
    (s, f) => s + (f.properties[MAP_METRICS[metric.value].key] as number),
    0,
  )
  return `${grid.value.length} cellules de 0,25° · ${formatCount(total)} détections ${MAP_METRICS[metric.value].label} (${yearRange.value[0]}–${yearRange.value[1]}) · ${statics.value.length} sites statiques exclus`
})
</script>

<template>
  <div @keydown="onKeydown">
    <div class="mb-3 flex flex-wrap items-end gap-x-5 gap-y-3 text-sm">
      <label class="flex flex-col gap-1">
        <span class="font-medium text-stone-700">Capteur affiché</span>
        <select v-model="metric" class="field">
          <option v-for="(m, k) in MAP_METRICS" :key="k" :value="k">{{ m.label }}</option>
        </select>
      </label>
      <label class="flex items-center gap-2 pb-1.5">
        <input v-model="showStatic" type="checkbox" class="size-4 accent-sky-700" />
        Sites statiques exclus
      </label>
      <label class="flex items-center gap-2 pb-1.5">
        <input
          v-model="showBasemap"
          type="checkbox"
          class="size-4 accent-stone-700"
          :disabled="!basemapAvailable"
        />
        {{ basemapAvailable ? 'Fond de carte' : 'Fond de carte (hors ligne)' }}
      </label>
      <div class="flex gap-2 pb-0.5">
        <button
          type="button"
          :aria-pressed="drawing"
          :class="drawing ? 'btn-primary' : 'btn'"
          @click="toggleDrawing"
        >
          {{ drawing ? 'Annuler le dessin (Échap)' : 'Dessiner une zone' }}
        </button>
        <button v-if="bbox" type="button" class="btn" @click="clearZone">Effacer la zone</button>
      </div>
    </div>

    <p v-if="drawing" class="mb-2 text-xs text-stone-700" role="status">
      Cliquez-glissez sur la carte pour tracer un rectangle.
    </p>
    <p v-if="partialMetric" class="mb-2 text-xs text-amber-900">
      {{ MAP_METRICS[metric].label }} ne couvre la période qu'à partir de
      {{ MAP_METRICS[metric].since }}.
    </p>

    <div class="relative">
      <div
        ref="container"
        class="h-[28rem] w-full overflow-hidden rounded-xl border border-stone-200"
        role="region"
        aria-label="Carte des détections par cellule de 0,25° et des sites statiques exclus"
      />
      <p
        v-if="loading"
        class="absolute left-2 top-2 rounded bg-white/90 px-2 py-1 text-xs text-stone-700 shadow-sm"
        role="status"
      >
        Chargement de la grille…
      </p>
      <p
        v-if="error"
        role="alert"
        class="absolute inset-x-2 top-2 rounded bg-red-50 p-2 text-xs text-red-800"
      >
        Grille indisponible : {{ error }}
      </p>
    </div>

    <div class="mt-2 flex flex-wrap items-center gap-x-6 gap-y-2 text-xs text-stone-700">
      <div class="flex items-center gap-2">
        <span class="font-medium">Détections brutes {{ MAP_METRICS[metric].label }}</span>
        <ol class="flex" aria-label="Légende de la grille">
          <li v-for="s in legend" :key="s.label" class="flex flex-col items-center">
            <span class="block h-3 w-10" :style="{ backgroundColor: s.color }" aria-hidden="true" />
            <span class="mt-0.5 tabular-nums">{{ s.label }}</span>
          </li>
        </ol>
      </div>
      <span class="flex items-center gap-1.5">
        <span class="block size-3 bg-[#0072B2]" aria-hidden="true" />
        Site statique exclu par le filtre (0,05°)
      </span>
    </div>
    <p class="mt-1 text-xs text-stone-600" aria-live="polite">{{ summary }}</p>
    <p class="mt-1 text-xs text-stone-500">
      Comptages bruts d'un seul capteur (non harmonisés) : la grille montre l'empreinte spatiale, le
      calendrier et le graphe portent la série harmonisée.
    </p>

    <details class="mt-3 text-sm">
      <summary class="cursor-pointer text-stone-700">
        Saisir une zone en coordonnées (lat/lon)
      </summary>
      <form class="mt-2 flex flex-wrap items-end gap-3" @submit.prevent="submitForm">
        <label
          v-for="f in [
            ['w', 'Ouest (lon)'],
            ['s', 'Sud (lat)'],
            ['e', 'Est (lon)'],
            ['n', 'Nord (lat)'],
          ] as const"
          :key="f[0]"
          class="flex flex-col gap-1"
        >
          <span class="text-xs text-stone-600">{{ f[1] }}</span>
          <input v-model="form[f[0]]" inputmode="decimal" class="field w-24 tabular-nums" />
        </label>
        <button type="submit" class="btn-primary">Appliquer</button>
      </form>
    </details>
    <p v-if="formError" role="alert" class="mt-2 text-xs text-red-800">{{ formError }}</p>
  </div>
</template>
