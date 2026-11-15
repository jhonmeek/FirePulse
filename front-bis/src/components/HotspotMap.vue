<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, useTemplateRef, watch } from 'vue'
import {
  Map as MlMap,
  Marker,
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
  dataSourceMode,
  findProvinceName,
  formatCount,
  loadHotspotsGrid,
  provinceFeatures,
  provinceSummaries,
} from '@/lib/data'
import { t } from '@/lib/i18n'
import { HEAT_STOPS, HEAT_GRADIENT } from '@/lib/heatScale'
import { provenance } from '@/lib/provenance'
import type { GridBundle } from '@/lib/types'

setWorkerUrl(workerUrl)

const props = defineProps<{ reducedMotion?: boolean }>()

const container = useTemplateRef<HTMLDivElement>('container')
const selectedRegion = ref('GA')
const yearStart = ref(2000)
const yearEnd = ref(2025)
const filterStatic = ref(true)
const showStatic = ref(true)
const scrollZoomEnabled = ref(false)
const showScrollHint = ref(false)
const mapReady = ref(false)
const loadingLive = ref(false)
const gridSource = ref<'live' | 'snapshot'>('snapshot')
const stats = ref({ cells: 0, total: 0, max: 1 })
const showMaritime = ref(false)
const maritimeStatus = ref<'idle' | 'loading' | 'ready' | 'missing' | 'error'>('idle')
const maritimeCount = ref(0)
const maritimePeriod = ref('')
const maritimeUrl = `${import.meta.env.BASE_URL.replace(/\/?$/, '/')}data/gabon-maritime-observations.geojson`
const maritimeLayers = ['maritime-zone', 'maritime-point']
const maritimeZoneWms = 'https://geo.vliz.be/geoserver/MarineRegions/wms?SERVICE=WMS&VERSION=1.1.1&REQUEST=GetMap&LAYERS=eez&STYLES=&CQL_FILTER=mrgid%3D8476&TRANSPARENT=TRUE&SRS=EPSG:3857&BBOX={bbox-epsg-3857}&WIDTH=256&HEIGHT=256&FORMAT=image/png'
let maritimeAbort: AbortController | null = null

let map: MlMap | null = null
let popup: Popup | null = null
let resizeObserver: ResizeObserver | null = null
let bundle: GridBundle | null = null
let markers: Marker[] = []
let unmounted = false
let loadSeq = 0
let scrollHintTimer: ReturnType<typeof setTimeout> | null = null
let wheelTarget: HTMLElement | null = null
let onContainerWheel: ((e: WheelEvent) => void) | null = null

const START_OPTIONS = YEARS.filter((y) => y <= 2024)
const END_OPTIONS = YEARS.filter((y) => y >= 2001)

const GABON_BOUNDS: [[number, number], [number, number]] = [
  [6.7, -6.7],
  [14.7, 2.45],
]

const periodLabel = computed(() =>
  `${yearStart.value === 2000 ? '11' : '01'}/${yearStart.value} → 12/${yearEnd.value}`,
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
  const expression: unknown[] = ['interpolate', ['linear'], ['sqrt', ['get', 'count']]]
  for (const [position, rgb] of HEAT_STOPS) {
    expression.push(position * Math.sqrt(Math.max(1, max)), `rgb(${rgb.join(', ')})`)
  }
  return expression as never
}

function applyBundle(nextBundle: GridBundle) {
  if (!map || !mapReady.value || unmounted) return
  bundle = nextBundle
  stats.value = { cells: nextBundle.cells, total: nextBundle.total, max: nextBundle.max }
  ;(map.getSource('grid') as GeoJSONSource | undefined)?.setData(nextBundle.grid)
  ;(map.getSource('static') as GeoJSONSource | undefined)?.setData(nextBundle.statics)
  if (map.getLayer('grid-fill')) {
    map.setPaintProperty('grid-fill', 'fill-color', gridColorExpression(nextBundle.max))
  }
}

async function updateData() {
  if (!map || !mapReady.value || unmounted) return
  if (yearStart.value > yearEnd.value) yearEnd.value = yearStart.value
  const currentSeq = ++loadSeq

  applyBundle(buildGrid(yearStart.value, yearEnd.value, filterStatic.value))
  gridSource.value = 'snapshot'
  loadingLive.value = true

  const liveBundle = await loadHotspotsGrid(yearStart.value, yearEnd.value, filterStatic.value)
  if (currentSeq !== loadSeq || !map || !mapReady.value || unmounted) return
  loadingLive.value = false
  gridSource.value = liveBundle.source
  if (liveBundle.source === 'live') {
    applyBundle(liveBundle)
  }
}

function focusRegion(code: string) {
  selectedRegion.value = code
  if (!map || !mapReady.value) return
  if (map.getLayer('province-active')) {
    map.setFilter('province-active', ['==', ['get', 'code'], code === 'GA' ? '__none__' : code])
  }
  for (const m of markers) {
    const el = m.getElement()
    el.classList.toggle('is-active', el.dataset.code === code)
  }
  if (code === 'GA') {
    map.fitBounds(GABON_BOUNDS, { padding: 48, duration: props.reducedMotion ? 0 : 1000, pitch: 24, bearing: -6 })
    return
  }
  const match = provinceSummaries.value.find((p) => p.code === code)
  if (match && match.bbox.length >= 4) {
    const [w, s, e, n] = match.bbox
    map.fitBounds(
      [
        [w!, s!],
        [e!, n!],
      ],
      { padding: 54, duration: props.reducedMotion ? 0 : 1000, pitch: 24, bearing: -4 },
    )
  }
}

function renderProvinceMarkers() {
  for (const m of markers) m.remove()
  markers = []
  if (!map) return
  for (const p of provinceSummaries.value) {
    const el = document.createElement('button')
    el.type = 'button'
    el.className = 'fp-province-pin'
    el.dataset.code = p.code
    el.textContent = p.name
    if (selectedRegion.value === p.code) el.classList.add('is-active')
    el.addEventListener('click', () => {
      focusRegion(selectedRegion.value === p.code ? 'GA' : p.code)
    })
    const marker = new Marker({ element: el, anchor: 'center' }).setLngLat(p.center).addTo(map)
    markers.push(marker)
  }
}

function escapeHtml(value: string): string {
  return value.replace(/[&<>"']/g, (character) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  })[character]!)
}

function popupHtml(title: string, badge: string, rows: [string, string][], badgeTone: 'hot' | 'cool' = 'hot'): string {
  return `
    <div class="fp-popup">
      <div class="fp-popup-head">
        <span class="fp-popup-badge ${badgeTone}">${escapeHtml(badge)}</span>
        <p class="fp-popup-title">${escapeHtml(title)}</p>
      </div>
      <dl>
        ${rows.map(([k, v]) => `<div><dt>${escapeHtml(k)}</dt><dd>${escapeHtml(v)}</dd></div>`).join('')}
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
    months: number
  }
  const { lat, lon } = cellCentroid(p.cell_id, provenance.gridDeg)
  const province = findProvinceName(lon, lat)
  popup
    ?.setLngLat(event.lngLat)
    .setHTML(
      popupHtml(
        `${t('Zone de feux', 'Fire zone')} · ${province}`,
        t('Carré ~28 km', '~28 km grid'),
        [
          [`${t('Détections non harmonisées', 'Unharmonized detections')} (${periodLabel.value})`, formatCount(p.count)],
          [
            t('Fréquence', 'Frequency'),
            t(`Actif sur ${formatCount(p.months)} mois`, `Active across ${formatCount(p.months)} months`),
          ],
          [
            t('Dominante', 'Dominant activity'),
            filterStatic.value
              ? t('Type 0 hors sources persistantes', 'Type 0 outside persistent sources')
              : t('Type 0 + sources candidates mélangés', 'Type 0 + candidate sources mixed'),
          ],
        ],
        'hot',
      ),
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
    activeMonths: number
  }
  const { lat, lon } = cellCentroid(p.cell_id, provenance.staticGridDeg)
  const province = findProvinceName(lon, lat)
  popup
    ?.setLngLat(event.lngLat)
    .setHTML(
      popupHtml(
        `${t('Source de chaleur persistante candidate', 'Candidate persistent heat source')} · ${province}`,
        t('Cellule candidate (~5 km)', 'Candidate cell (~5 km)'),
        [
          [t('Nature', 'Type'), t('Source fixe ou industrielle candidate, pas une torchère confirmée', 'Candidate fixed or industrial source, not a confirmed flare')],
          [
            t('Persistance', 'Persistence'),
            t(`Actif ${formatCount(p.activeMonths)} mois entre 2012 et 2025`, `Active ${formatCount(p.activeMonths)} months (2012–2025)`),
          ],
          [t('Traitement', 'Filtering'), t('Cellule écartée par le filtre complet', 'Cell excluded by the full filter')],
        ],
        'cool',
      ),
    )
    .addTo(map)
}

function showMaritimePopup(event: MapMouseEvent & { features?: MapGeoJSONFeature[] }) {
  if (!map || !event.features?.[0]) return
  map.getCanvas().style.cursor = 'pointer'
  const properties = event.features[0].properties ?? {}
  const value = (key: string) => properties[key] == null || properties[key] === ''
    ? 'Non renseigné'
    : String(properties[key])
  const rawTime = value('acq_time_utc')
  const paddedTime = /^\d{1,4}$/.test(rawTime) ? rawTime.padStart(4, '0') : ''
  const time = paddedTime && Number(paddedTime.slice(0, 2)) < 24 && Number(paddedTime.slice(2)) < 60
    ? `${paddedTime.slice(0, 2)}:${paddedTime.slice(2)} UTC`
    : rawTime
  popup?.setLngLat(event.lngLat).setHTML(popupHtml(
    t('Point thermique maritime (exploratoire)', 'Maritime thermal point (exploratory)'),
    'NOAA-20 NRT',
    [
      [t('Date', 'Date'), value('acq_date')],
      [t('Heure', 'Time'), time],
      ['FRP', value('frp') === 'Non renseigné' ? t('Non renseigné', 'Unavailable') : `${value('frp')} MW`],
    ],
    'cool',
  )).addTo(map)
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

function toggleScrollZoom() {
  scrollZoomEnabled.value = !scrollZoomEnabled.value
  showScrollHint.value = false
  if (!map) return
  if (scrollZoomEnabled.value) map.scrollZoom.enable()
  else map.scrollZoom.disable()
}

async function toggleMaritime() {
  showMaritime.value = !showMaritime.value
  if (!map || !mapReady.value) return
  for (const layer of maritimeLayers) {
    map.setLayoutProperty(layer, 'visibility', showMaritime.value ? 'visible' : 'none')
  }
  if (!showMaritime.value || maritimeStatus.value === 'ready' || maritimeStatus.value === 'loading') return

  maritimeStatus.value = 'loading'
  maritimeAbort = new AbortController()
  try {
    const response = await fetch(maritimeUrl, { signal: maritimeAbort.signal })
    // Les serveurs SPA peuvent renvoyer index.html avec un statut 200 pour un fichier absent.
    if (response.status === 404 || (response.ok && response.headers.get('content-type')?.includes('text/html'))) {
      maritimeStatus.value = 'missing'
      return
    }
    if (!response.ok) throw new Error('Chargement impossible')
    const data: unknown = await response.json()
    if (!data || typeof data !== 'object' || !('type' in data) || data.type !== 'FeatureCollection' ||
        !('features' in data) || !Array.isArray(data.features) ||
        !data.features.every((feature: unknown) => feature && typeof feature === 'object' &&
          'type' in feature && feature.type === 'Feature' && 'geometry' in feature &&
          feature.geometry && typeof feature.geometry === 'object' &&
          'type' in feature.geometry && feature.geometry.type === 'Point' &&
          'coordinates' in feature.geometry && Array.isArray(feature.geometry.coordinates) &&
          feature.geometry.coordinates.length >= 2 &&
          feature.geometry.coordinates.every((coordinate: unknown) => typeof coordinate === 'number' && Number.isFinite(coordinate)) &&
          Math.abs(feature.geometry.coordinates[0]) <= 180 && Math.abs(feature.geometry.coordinates[1]) <= 90)) {
      throw new Error('GeoJSON invalide')
    }
    if (unmounted || !map) return
    ;(map.getSource('maritime') as GeoJSONSource).setData(data as FeatureCollection)
    maritimeCount.value = data.features.length
    if ('metadata' in data && data.metadata && typeof data.metadata === 'object' &&
        'period_start' in data.metadata && 'period_end' in data.metadata &&
        typeof data.metadata.period_start === 'string' && typeof data.metadata.period_end === 'string') {
      maritimePeriod.value = `${data.metadata.period_start} → ${data.metadata.period_end}`
    }
    maritimeStatus.value = 'ready'
  } catch (error) {
    if (unmounted || (error instanceof DOMException && error.name === 'AbortError')) return
    maritimeStatus.value = 'error'
  }
}

function resetView() {
  focusRegion('GA')
}

onMounted(() => {
  const el = container.value
  if (!el) return

  map = new MlMap({
    container: el,
    style: STYLE,
    bounds: GABON_BOUNDS,
    fitBoundsOptions: { padding: 48 },
    pitch: 24,
    bearing: -6,
    scrollZoom: false,
    attributionControl: false,
    maxPitch: 55,
  })
  onContainerWheel = (event: WheelEvent) => {
    if (!map) return
    if (event.ctrlKey || event.metaKey || scrollZoomEnabled.value) {
      map.scrollZoom.enable()
      showScrollHint.value = false
    } else {
      map.scrollZoom.disable()
      showScrollHint.value = true
      if (scrollHintTimer) clearTimeout(scrollHintTimer)
      scrollHintTimer = setTimeout(() => {
        showScrollHint.value = false
      }, 1800)
    }
  }
  wheelTarget = el
  el.addEventListener('wheel', onContainerWheel, { capture: true, passive: true })
  map.addControl(new NavigationControl({ showCompass: false }), 'top-right')
  map.addControl(new ScaleControl({ unit: 'metric' }), 'bottom-left')
  popup = new Popup({ closeButton: false, closeOnClick: false, offset: 14, className: 'fp-popup-wrap' })

  map.on('load', () => {
    if (unmounted || !map) return
    const regions = {
      type: 'FeatureCollection' as const,
      features: [countryFeature.value, ...provinceFeatures.value].filter(Boolean),
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

    map.addSource('maritime', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } })
    map.addSource('maritime-zone-wms', {
      type: 'raster',
      tiles: [maritimeZoneWms],
      tileSize: 256,
      bounds: [6.9, -6.5, 11.2, 1.1],
      attribution: 'Marine Regions / VLIZ - World EEZ v12 (2023)',
    })

    map.addLayer({
      id: 'graticule',
      type: 'line',
      source: 'graticule',
      paint: { 'line-color': '#2f7b89', 'line-width': 0.5, 'line-opacity': 0.14 },
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
      paint: { 'fill-color': gridColorExpression(1), 'fill-opacity': 0.9 },
    })
    map.addLayer({
      id: 'grid-line',
      type: 'line',
      source: 'grid',
      paint: { 'line-color': '#3b2016', 'line-width': 0.55, 'line-opacity': 0.42 },
    })
    map.addLayer({
      id: 'province-line',
      type: 'line',
      source: 'regions',
      filter: ['!=', ['get', 'region_type'], 'country'],
      paint: {
        'line-color': '#94a3b8',
        'line-width': 0.8,
        'line-opacity': 0.38,
        'line-dasharray': [2, 2],
      },
    })
    map.addLayer({
      id: 'province-active',
      type: 'line',
      source: 'regions',
      filter: ['==', ['get', 'code'], '__none__'],
      paint: { 'line-color': '#ffc46b', 'line-width': 2.2, 'line-opacity': 0.95 },
    })
    map.addLayer({
      id: 'country-glow',
      type: 'line',
      source: 'regions',
      filter: ['==', ['get', 'region_type'], 'country'],
      paint: { 'line-color': '#5eead4', 'line-width': 7, 'line-blur': 6, 'line-opacity': 0.22 },
    })
    map.addLayer({
      id: 'country-line',
      type: 'line',
      source: 'regions',
      filter: ['==', ['get', 'region_type'], 'country'],
      paint: { 'line-color': '#8ef7e4', 'line-width': 1.5, 'line-opacity': 0.95 },
    })
    map.addLayer({
      id: 'static-fill',
      type: 'fill',
      source: 'static',
      paint: { 'fill-color': '#22d3ee', 'fill-opacity': 0.95 },
    })
    map.addLayer({
      id: 'static-line',
      type: 'line',
      source: 'static',
      paint: { 'line-color': '#ecfeff', 'line-width': 1, 'line-opacity': 0.95 },
    })

    map.addLayer({
      id: 'maritime-zone', type: 'raster', source: 'maritime-zone-wms',
      layout: { visibility: 'none' },
      paint: { 'raster-opacity': 0.35 },
    })
    map.addLayer({
      id: 'maritime-point', type: 'circle', source: 'maritime',
      layout: { visibility: 'none' },
      paint: { 'circle-radius': 7, 'circle-color': '#c084fc', 'circle-stroke-color': '#fff', 'circle-stroke-width': 2 },
    })

    map.on('mousemove', 'maritime-point', showMaritimePopup)
    map.on('click', 'maritime-point', showMaritimePopup)
    map.on('mouseleave', 'maritime-point', onLeave)
    map.on('mousemove', 'grid-fill', onGridHover)
    map.on('click', 'grid-fill', onGridHover)
    map.on('mouseleave', 'grid-fill', onLeave)
    map.on('mousemove', 'static-fill', onStaticHover)
    map.on('click', 'static-fill', onStaticHover)
    map.on('mouseleave', 'static-fill', onLeave)

    mapReady.value = true
    renderProvinceMarkers()
    updateData()
    // The published maritime snapshot is a separate exploratory layer. Load it
    // when the map becomes ready so its points are visible without a hidden toggle.
    void toggleMaritime()
  })

  resizeObserver = new ResizeObserver(() => map?.resize())
  resizeObserver.observe(el)
})

onBeforeUnmount(() => {
  unmounted = true
  maritimeAbort?.abort()
  if (wheelTarget && onContainerWheel) {
    wheelTarget.removeEventListener('wheel', onContainerWheel, { capture: true })
  }
  if (scrollHintTimer) clearTimeout(scrollHintTimer)
  resizeObserver?.disconnect()
  popup?.remove()
  for (const m of markers) m.remove()
  markers = []
  map?.remove()
  map = null
})

watch([yearStart, yearEnd, filterStatic], updateData)
watch(yearStart, (value) => {
  if (value > yearEnd.value) yearEnd.value = value
})
watch([countryFeature, provinceFeatures], () => {
  if (!map || !mapReady.value || unmounted) return
  const regions = {
    type: 'FeatureCollection' as const,
    features: [countryFeature.value, ...provinceFeatures.value].filter(Boolean),
  }
  ;(map.getSource('regions') as GeoJSONSource | undefined)?.setData(regions as never)
  renderProvinceMarkers()
})
</script>

<template>
  <div class="map-frame">
    <!-- Barre de filtres au-dessus de la carte pour laisser toute la carte libre et immersive -->
    <div class="map-bar">
      <div class="map-bar-group">
        <label class="map-label" for="region-select">{{ t('Territoire', 'Territory') }}</label>
        <select
          id="region-select"
          :value="selectedRegion"
          class="map-select"
          @change="focusRegion(($event.target as HTMLSelectElement).value)"
        >
          <option value="GA">{{ t('Tout le Gabon', 'All of Gabon') }}</option>
          <option v-for="p in provinceSummaries" :key="p.code" :value="p.code">
            {{ p.name }}
          </option>
        </select>
      </div>

      <div class="map-bar-group">
        <label class="map-label" for="year-start">{{ t('Période', 'Period') }}</label>
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
        {{
          filterStatic
            ? t('Détections thermiques · Type 0 hors sources persistantes (exploratoire)', 'Thermal detections · Type 0 outside persistent sources (exploratory)')
            : t('Toutes détections thermiques (catégories exploratoires mélangées)', 'All thermal detections (mixed exploratory categories)')
        }}
      </button>

      <button
        type="button"
        class="map-toggle"
        :class="{ active: showStatic }"
        :aria-pressed="showStatic"
        @click="toggleStatic"
      >
        <span class="toggle-dot cool"></span>
        {{ t('Sources persistantes candidates (bleu)', 'Candidate persistent sources (blue)') }}
      </button>

      <button
        type="button"
        class="map-toggle"
        :class="{ active: showMaritime }"
        :aria-pressed="showMaritime"
        :disabled="!mapReady"
        @click="toggleMaritime"
      >
        <span class="toggle-dot maritime-dot"></span>
        {{ t('ZEE et points maritimes (exploratoire)', 'EEZ and maritime points (exploratory)') }}
      </button>

      <button
        type="button"
        class="map-toggle"
        :class="{ active: scrollZoomEnabled }"
        :aria-pressed="scrollZoomEnabled"
        @click="toggleScrollZoom"
      >
        <span class="toggle-dot"></span>
        {{ scrollZoomEnabled ? t('Zoom molette : activé', 'Scroll zoom: on') : t('Zoom molette : verrouillé', 'Scroll zoom: locked') }}
      </button>

      <button v-if="selectedRegion !== 'GA'" type="button" class="map-reset-inline" @click="resetView">
        {{ t('Revenir à tout le Gabon', 'Back to full Gabon') }}
      </button>
    </div>

    <div v-show="showMaritime" class="maritime-status">
      <p>
        {{
          t(
            `Instantané NASA FIRMS (NOAA-20 NRT demandé), ${maritimePeriod || 'période non renseignée'} — indépendant de la période terrestre. Couverture inconnue. Détections thermiques non classifiées (catégorie exploratoire) : elles ne confirment ni un feu ni une torchère. Le polygone EEZ Marine Regions utilisé exclut la mer territoriale ; son périmètre est indicatif, non juridique.`,
            `NASA FIRMS snapshot (NOAA-20 NRT requested), ${maritimePeriod || 'period unavailable'} — independent of the terrestrial period. Coverage unknown. Unclassified thermal detections (exploratory category): they confirm neither a fire nor a flare. The Marine Regions EEZ polygon excludes territorial waters and is indicative rather than legal.`,
          )
        }}
      </p>
      <p>
        {{ t('ZEE indicative : tuiles Marine Regions accessibles avec une connexion réseau. Ce périmètre exclut la mer territoriale. Source :', 'Indicative EEZ: Marine Regions tiles require a network connection. This area excludes territorial waters. Source:') }}
        <a href="https://www.marineregions.org/gazetteer.php?p=details&amp;id=8476" target="_blank" rel="noopener noreferrer">Marine Regions - Gabon EEZ</a>.
      </p>
      <div role="status" aria-live="polite">
        <template v-if="maritimeStatus === 'loading'">
          {{ t('Chargement des observations…', 'Loading observations…') }}
        </template>
        <template v-else-if="maritimeStatus === 'missing'">
          {{ t(`Fichier absent : ${maritimeUrl}.`, `Missing file: ${maritimeUrl}.`) }}
        </template>
        <template v-else-if="maritimeStatus === 'error'">
          {{
            t(
              `Fichier inaccessible ou GeoJSON invalide : ${maritimeUrl}. Désactivez puis réactivez pour réessayer.`,
              `Unavailable file or invalid GeoJSON: ${maritimeUrl}. Toggle off and on to retry.`,
            )
          }}
        </template>
        <template v-else-if="maritimeStatus === 'ready'">
          {{ t(`${maritimeCount} point(s) thermique(s) non classifié(s).`, `${maritimeCount} unclassified thermal point(s).`) }}
        </template>
      </div>
    </div>

    <p class="map-data-note" role="status">
      <strong>{{ t('Cumul observé non harmonisé', 'Observed, unharmonized total') }} · {{ periodLabel }}</strong>
      {{ t(
        'MODIS + S-NPP + NOAA-20, avec le filtre sélectionné. Comme dans le calendrier : clair = peu, sombre = beaucoup. Ici, les couleurs comparent les cumuls par cellule sur la période choisie ; elles ne représentent pas les valeurs mensuelles harmonisées du calendrier. Une cellule absente ne prouve pas l’absence de feu.',
        'MODIS + S-NPP + NOAA-20, with the selected filter. As in the calendar: light = low, dark = high. Here, colors compare cell totals over the selected period; they do not represent the calendar’s harmonized monthly values. An absent cell does not prove the absence of fire.',
      ) }}
    </p>

    <div class="map-wrap">
      <div
        ref="container"
        class="map-canvas"
        role="img"
        :aria-label="t('Carte interactive des détections thermiques et sources persistantes candidates au Gabon', 'Interactive map of thermal detections and candidate persistent sources in Gabon')"
      ></div>
      <div class="map-glow" aria-hidden="true"></div>

      <div class="map-scroll-hint" :class="{ visible: showScrollHint && !scrollZoomEnabled }" aria-live="polite">
        {{ t('Utilisez Ctrl + molette (ou activez « Zoom molette ») pour zoomer sur la carte', 'Use Ctrl + scroll (or enable "Scroll zoom") to zoom the map') }}
      </div>

      <div class="map-legend">
        <div class="map-legend-head">
          <span class="tiny-label">{{ t('Détections cumulées / cellule', 'Cumulative detections / cell') }}</span>
          <span class="mono">{{ periodLabel }}</span>
        </div>
        <div class="map-legend-scale" :style="{ background: HEAT_GRADIENT }" aria-hidden="true"></div>
        <div class="map-legend-values">
          <span>{{ t('0 (clair)', '0 (light)') }}</span>
          <span>{{ formatCount(stats.max) }} {{ t('(sombre)', '(dark)') }}</span>
        </div>
      </div>

      <div class="map-stats">
        <div>
          <span class="map-stat-value">{{ formatCount(stats.cells) }}</span>
          <span class="map-stat-label">{{ t('zones actives (~28 km)', 'active zones (~28 km)') }}</span>
        </div>
        <div>
          <span class="map-stat-value">{{ formatCount(stats.total) }}</span>
          <span class="map-stat-label">{{ t('points chauds', 'hotspots') }}</span>
        </div>
        <button type="button" class="map-reset" @click="resetView">
          {{ t('Recentrer', 'Reset view') }}
        </button>
      </div>
    </div>

    <!-- Explication simple des deux formes visibles sur la carte -->
    <div class="map-guide">
      <div class="guide-item">
        <span class="guide-box hot"></span>
        <p>
          <strong>{{ t('Carrés clairs à bordeaux sombre (~28 km)', 'Light to dark crimson squares (~28 km)') }}</strong> —
          {{
            t(
              'Zones de détections type 0 (forêt, savane, brûlis présumés). Survolez ou cliquez un carré pour connaître sa province et son activité.',
              'Type-0 detection zones (forest, savanna, presumed clearing). Hover or click any square to see its province and activity.',
            )
          }}
        </p>
      </div>
      <div class="guide-item">
        <span class="guide-box cool"></span>
        <p>
          <strong>{{ t('Cellules bleues (~5 km)', 'Blue cells (~5 km)') }}</strong> —
          {{
            t(
              'Sources de chaleur persistantes candidates (Port-Gentil, côte d’Ogooué-Maritime et en mer). Le masque signale des cellules, pas des torchères confirmées une par une.',
              'Candidate persistent heat sources (Port-Gentil, Ogooué-Maritime coast, and offshore). The mask flags cells, not individually confirmed flares.',
            )
          }}
        </p>
      </div>
      <span class="guide-source">
        {{
          loadingLive
            ? t('Mise à jour en direct…', 'Syncing live data…')
            : gridSource === 'live' && dataSourceMode === 'live'
              ? t('Données reçues de l’API (provenance à vérifier)', 'API data received (verify provenance)')
              : t('Instantané local SP', 'Local SP snapshot')
        }}
      </span>
    </div>
  </div>
</template>

<style scoped>
.map-data-note {
  margin: 0;
  color: var(--muted);
  font-size: 0.85rem;
  line-height: 1.6;
}

.map-data-note strong {
  display: block;
  color: var(--ink);
}

.map-frame {
  display: grid;
  gap: 12px;
}

.map-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 10px;
}

.map-bar-group {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 7px 11px;
  border: 1px solid var(--line-strong);
  border-radius: 10px;
  background: rgba(244, 241, 232, 0.035);
}

.map-label {
  font-family: var(--font-mono);
  font-size: 0.58rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--dim);
}

.map-select,
.year-selects select {
  border: 0;
  background: transparent;
  color: var(--ink);
  font-family: var(--font-sans);
  font-size: 0.82rem;
  font-weight: 500;
  cursor: pointer;
}

.map-select option,
.year-selects select option {
  background: #0b111a;
  color: #f4f1e8;
}

.year-selects {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: var(--muted);
}

.year-selects select {
  font-family: var(--font-mono);
  font-size: 0.78rem;
}

.map-toggle {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border: 1px solid var(--line-strong);
  border-radius: 10px;
  background: rgba(244, 241, 232, 0.03);
  color: var(--muted);
  font-size: 0.78rem;
  font-weight: 500;
  cursor: pointer;
  transition:
    color 0.2s ease,
    border-color 0.2s ease,
    background 0.2s ease;
}

.map-toggle:hover {
  color: var(--ink);
  border-color: var(--muted);
}

.map-toggle.active {
  color: var(--ink);
  border-color: rgba(255, 196, 107, 0.45);
  background: rgba(255, 196, 107, 0.09);
}

.toggle-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--ember);
  opacity: 0.4;
}

.map-toggle.active .toggle-dot {
  opacity: 1;
  box-shadow: 0 0 8px var(--ember);
}

.toggle-dot.cool {
  background: var(--cyan);
}

.map-toggle.active .toggle-dot.cool {
  box-shadow: 0 0 8px var(--cyan);
}

.map-reset-inline {
  padding: 8px 12px;
  border: 1px solid rgba(94, 234, 212, 0.4);
  border-radius: 10px;
  background: rgba(94, 234, 212, 0.08);
  color: var(--teal);
  font-size: 0.76rem;
  font-weight: 500;
  cursor: pointer;
}

.map-wrap {
  position: relative;
  overflow: hidden;
  border: 1px solid var(--line);
  border-radius: var(--radius);
  background: #05080d;
  min-height: 600px;
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
  background: radial-gradient(ellipse 52% 48% at 50% 48%, rgba(255, 94, 26, 0.11), transparent 68%);
  mix-blend-mode: screen;
}

.map-scroll-hint {
  position: absolute;
  top: 14px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 6;
  padding: 7px 14px;
  border: 1px solid rgba(255, 196, 107, 0.45);
  border-radius: 999px;
  background: rgba(5, 8, 13, 0.9);
  color: #f4f1e8;
  font-size: 0.76rem;
  font-weight: 500;
  white-space: nowrap;
  pointer-events: none;
  opacity: 0;
  transition: opacity 0.2s ease;
  backdrop-filter: blur(10px);
}

.map-scroll-hint.visible {
  opacity: 1;
}

.toggle-dot.maritime-dot {
  background: #c084fc;
}

.map-toggle.active .toggle-dot.maritime-dot {
  box-shadow: 0 0 8px #c084fc;
}

.maritime-status {
  padding: 10px 14px;
  border: 1px solid rgba(192, 132, 252, 0.45);
  border-radius: 12px;
  background: rgba(16, 12, 24, 0.92);
  color: #f4eaff;
  font-size: 0.76rem;
  line-height: 1.5;
}

.maritime-status p {
  margin: 0 0 4px;
}
.map-legend {
  position: absolute;
  right: 14px;
  bottom: 14px;
  z-index: 4;
  width: 235px;
  padding: 10px 12px;
  border: 1px solid var(--line-strong);
  border-radius: 10px;
  background: rgba(5, 7, 11, 0.86);
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
  font-size: 0.68rem;
  color: var(--gold);
}

.map-legend-scale {
  height: 12px;
  border-radius: 4px;
  display: flex;
  height: 8px;
  border-radius: 4px;
  overflow: hidden;
}

.legend-swatch {
  flex: 1;
}

.map-legend-values {
  display: flex;
  justify-content: space-between;
  margin-top: 6px;
  font-family: var(--font-mono);
  font-size: 0.74rem;
  color: #dce5f0;
}

.map-stats {
  position: absolute;
  left: 14px;
  bottom: 14px;
  z-index: 4;
  display: flex;
  align-items: flex-end;
  gap: 18px;
  padding: 10px 14px;
  border: 1px solid var(--line-strong);
  border-radius: 10px;
  background: rgba(5, 7, 11, 0.86);
  backdrop-filter: blur(12px);
}

.map-stats > div {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.map-stat-value {
  font-family: var(--font-display);
  font-variant-numeric: tabular-nums;
  font-size: 1.2rem;
  line-height: 1;
  color: var(--ink);
}

.map-stat-label {
  font-size: 0.64rem;
  color: var(--muted);
}

.map-reset {
  padding: 5px 10px;
  border: 1px solid var(--line-strong);
  border-radius: 7px;
  background: transparent;
  color: var(--ink);
  font-size: 0.7rem;
  cursor: pointer;
}

.map-reset:hover {
  border-color: var(--gold);
  color: var(--gold);
}

.map-guide {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 12px 24px;
  padding: 12px 16px;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: rgba(244, 241, 232, 0.025);
}

.guide-item {
  display: flex;
  align-items: center;
  gap: 10px;
  flex: 1 1 280px;
}

.guide-item p {
  font-size: 0.78rem;
  line-height: 1.45;
  color: var(--muted);
}

.guide-item strong {
  color: var(--ink);
}

.guide-box {
  width: 14px;
  height: 14px;
  flex: none;
  border-radius: 3px;
}

.guide-box.hot {
  background: linear-gradient(135deg, #f7efe2, #db7a3b 52%, #2a0606);
  border: 1px solid rgba(247, 239, 226, 0.55);
}

.guide-box.cool {
  background: #22d3ee;
  border: 1px solid #ecfeff;
}

.guide-source {
  font-family: var(--font-mono);
  font-size: 0.62rem;
  color: var(--dim);
}

@media (max-width: 760px) {
  .map-wrap {
    min-height: 500px;
  }
  .map-scroll-hint {
    max-width: calc(100% - 24px);
    white-space: normal;
    text-align: center;
    font-size: 0.7rem;
  }
  .map-legend {
    width: 185px;
  }
  .map-stats {
    gap: 12px;
  }
}
</style>

<style>
.fp-province-pin {
  padding: 2px 7px;
  border: 1px solid rgba(244, 241, 232, 0.16);
  border-radius: 999px;
  background: rgba(5, 8, 13, 0.72);
  color: #cbd5e1;
  font-family: 'Roboto Variable', 'Roboto', system-ui, sans-serif;
  font-size: 11px;
  font-weight: 500;
  white-space: nowrap;
  cursor: pointer;
  backdrop-filter: blur(6px);
  transition:
    color 0.2s ease,
    border-color 0.2s ease,
    background 0.2s ease;
}

.fp-province-pin:hover,
.fp-province-pin.is-active {
  color: #05070b;
  background: #ffc46b;
  border-color: #ffc46b;
  font-weight: 600;
}

.fp-popup-wrap .maplibregl-popup-content {
  padding: 0;
  background: transparent;
  box-shadow: none;
}

.fp-popup {
  min-width: 220px;
  max-width: 280px;
  padding: 12px 14px;
  border: 1px solid rgba(244, 241, 232, 0.24);
  border-radius: 12px;
  background: rgba(7, 11, 18, 0.96);
  color: #f4f1e8;
  font-family: 'Roboto Variable', 'Roboto', system-ui, sans-serif;
  box-shadow: 0 18px 40px -16px rgba(0, 0, 0, 0.92);
}

.fp-popup-head {
  margin-bottom: 9px;
}

.fp-popup-badge {
  display: inline-block;
  margin-bottom: 4px;
  padding: 2px 7px;
  border-radius: 999px;
  font-size: 0.62rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.fp-popup-badge.hot {
  background: rgba(255, 122, 61, 0.18);
  color: #ffb37a;
}

.fp-popup-badge.cool {
  background: rgba(34, 211, 238, 0.18);
  color: #67e8f9;
}

.fp-popup-title {
  margin: 0;
  font-size: 0.86rem;
  font-weight: 600;
  line-height: 1.3;
  color: #f4f1e8;
}

.fp-popup dl {
  display: grid;
  gap: 6px;
  margin: 0;
}

.fp-popup dl > div {
  display: flex;
  flex-direction: column;
  gap: 1px;
}

.fp-popup dt {
  font-size: 0.66rem;
  color: #9ba8b7;
}

.fp-popup dd {
  margin: 0;
  font-size: 0.78rem;
  color: #f4f1e8;
  font-weight: 500;
}

.fp-popup-wrap .maplibregl-popup-tip {
  border-top-color: rgba(7, 11, 18, 0.96);
}
</style>
