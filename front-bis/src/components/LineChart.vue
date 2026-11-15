<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, useId, useTemplateRef, watch } from 'vue'
import { gsap } from '@/lib/motion'
import { formatCount, formatPercent, median, monthLabel } from '@/lib/data'
import { t } from '@/lib/i18n'

export interface ChartPoint {
  month: string
  raw: number
  harm: number | null
  lo: number | null
  hi: number | null
  anomaly: number | null
}

export type ChartDatasetId = 'veg' | 'flare' | 'all' | 'modis' | 'snpp' | 'noaa20'

export interface ChartDatasetOption {
  id: ChartDatasetId
  label: string
  points: ChartPoint[]
}

const props = withDefaults(
  defineProps<{
    points?: ChartPoint[]
    datasets?: ChartDatasetOption[]
    initialDatasetId?: ChartDatasetId
    showRaw?: boolean
    showHarmonized?: boolean
    showBand?: boolean
    showAnomaly?: boolean
    highlight2012?: boolean
    markMonth?: string | null
    yMax?: number
    reducedMotion?: boolean
    rawLabel?: string
    harmLabel?: string
    title?: string
    interactive?: boolean
    defaultGranularity?: 'year' | 'month'
  }>(),
  {
    points: () => [],
    datasets: () => [],
    initialDatasetId: 'veg',
    showRaw: true,
    showHarmonized: false,
    showBand: false,
    showAnomaly: true,
    highlight2012: false,
    markMonth: null,
    yMax: undefined,
    reducedMotion: false,
    rawLabel: undefined,
    harmLabel: undefined,
    title: undefined,
    interactive: true,
    defaultGranularity: 'year',
  },
)

const uid = useId()
const W = 1000
const H = 410
const PAD = { top: 28, right: 24, bottom: 44, left: 68 }
const innerW = W - PAD.left - PAD.right
const innerH = H - PAD.top - PAD.bottom

const wrapper = useTemplateRef<HTMLDivElement>('wrapper')
const svg = useTemplateRef<SVGSVGElement>('svg')
const rawPath = useTemplateRef<SVGPathElement>('rawPath')
const harmPath = useTemplateRef<SVGPathElement>('harmPath')
const bandPath = useTemplateRef<SVGPathElement>('bandPath')
const areaPath = useTemplateRef<SVGPathElement>('areaPath')

const granularity = ref<'year' | 'month'>(props.defaultGranularity)
const selectedDatasetId = ref<ChartDatasetId>(props.initialDatasetId)
const hovered = ref<number | null>(null)
const pinned = ref<number | null>(null)

watch(
  () => props.initialDatasetId,
  (val) => {
    selectedDatasetId.value = val
    pinned.value = null
  },
)

const activeSourcePoints = computed<ChartPoint[]>(() => {
  if (props.datasets.length) {
    return (
      props.datasets.find((d) => d.id === selectedDatasetId.value)?.points ??
      props.datasets[0]?.points ??
      []
    )
  }
  return props.points
})

const hasFullYearlySpan = computed(() => activeSourcePoints.value.length > 90)

interface DisplayPoint extends ChartPoint {
  isYear: boolean
  label: string
}

const displayPoints = computed<DisplayPoint[]>(() => {
  const src = activeSourcePoints.value
  if (granularity.value === 'month' || !hasFullYearlySpan.value) {
    return src.map((p) => ({
      ...p,
      isYear: false,
      label: monthLabel(p.month),
    }))
  }

  // Agrégation sur les années complètes (2001–2025) pour éviter la chute artificielle de 2000 (2 mois).
  const byYear = new Map<
    number,
    { raw: number; harmSum: number; harmCount: number; loSum: number; hiSum: number; hasBand: boolean; months: number }
  >()

  for (const p of src) {
    const year = Number(p.month.slice(0, 4))
    if (year < 2001) continue
    const bucket = byYear.get(year) ?? {
      raw: 0,
      harmSum: 0,
      harmCount: 0,
      loSum: 0,
      hiSum: 0,
      hasBand: false,
      months: 0,
    }
    bucket.raw += p.raw
    bucket.months += 1
    if (p.harm !== null && p.harm !== undefined) {
      bucket.harmSum += p.harm
      bucket.harmCount += 1
      if (p.lo !== null && p.hi !== null) {
        bucket.loSum += p.lo
        bucket.hiSum += p.hi
        bucket.hasBand = true
      } else {
        bucket.loSum += p.harm
        bucket.hiSum += p.harm
      }
    }
    byYear.set(year, bucket)
  }

  const years = [...byYear.keys()].sort((a, b) => a - b)
  const totals = years
    .map((yr) => {
      const b = byYear.get(yr)!
      return props.showHarmonized && b.harmCount > 0 ? b.harmSum : b.raw
    })
    .filter((v) => v > 0)
  const medYear = median(totals)

  return years.map((yr) => {
    const b = byYear.get(yr)!
    const harmVal = b.harmCount > 0 ? Math.round(b.harmSum) : null
    const refVal = props.showHarmonized && harmVal !== null ? harmVal : b.raw
    const anomaly =
      props.showAnomaly && medYear > 0
        ? Math.round(((refVal - medYear) / medYear) * 1000) / 10
        : null
    return {
      month: `${yr}-01`,
      raw: Math.round(b.raw),
      harm: harmVal,
      lo: b.hasBand ? Math.round(b.loSum) : null,
      hi: b.hasBand ? Math.round(b.hiSum) : null,
      anomaly,
      isYear: true,
      label: String(yr),
    }
  })
})

const n = computed(() => displayPoints.value.length)
const maxValue = computed(() => {
  let max = 0
  for (const p of displayPoints.value) {
    if (props.showRaw) max = Math.max(max, p.raw)
    if (props.showHarmonized) max = Math.max(max, p.harm ?? 0, p.hi ?? 0)
  }
  return props.yMax ?? Math.max(1, max * 1.1)
})

function x(i: number): number {
  return PAD.left + (i / Math.max(1, n.value - 1)) * innerW
}

function y(value: number): number {
  return PAD.top + innerH - (value / maxValue.value) * innerH
}

function linePath(key: 'raw' | 'harm'): string {
  let d = ''
  let started = false
  displayPoints.value.forEach((p, i) => {
    const value = p[key]
    if (value === null || value === undefined) {
      started = false
      return
    }
    d += `${started ? 'L' : 'M'}${x(i).toFixed(2)},${y(value).toFixed(2)}`
    started = true
  })
  return d
}

const rawD = computed(() => (props.showRaw ? linePath('raw') : ''))
const harmD = computed(() => (props.showHarmonized ? linePath('harm') : ''))

const bandD = computed(() => {
  if (!props.showBand) return ''
  const top: [number, number][] = []
  const bottom: [number, number][] = []
  displayPoints.value.forEach((p, i) => {
    if (p.lo === null || p.hi === null || p.harm === null) return
    top.push([x(i), y(p.hi)])
    bottom.push([x(i), y(p.lo)])
  })
  if (top.length < 2) return ''
  const topD = top.map(([px, py], i) => `${i ? 'L' : 'M'}${px.toFixed(2)},${py.toFixed(2)}`).join('')
  const bottomD = bottom
    .slice()
    .reverse()
    .map(([px, py]) => `L${px.toFixed(2)},${py.toFixed(2)}`)
    .join('')
  return `${topD}${bottomD}Z`
})

const areaD = computed(() => {
  const key: 'harm' | 'raw' = props.showHarmonized ? 'harm' : 'raw'
  const pts = displayPoints.value
    .map((p, i) => ({ val: p[key], i }))
    .filter((d): d is { val: number; i: number } => d.val !== null && d.val !== undefined)
  if (pts.length < 2) return ''
  const base = y(0)
  const first = pts[0]!
  const last = pts[pts.length - 1]!
  const top = pts
    .map(({ val, i }, index) => `${index ? 'L' : 'M'}${x(i).toFixed(2)},${y(val).toFixed(2)}`)
    .join('')
  return `${top}L${x(last.i).toFixed(2)},${base.toFixed(2)}L${x(first.i).toFixed(2)},${base.toFixed(2)}Z`
})

const yearTicks = computed(() => {
  const points = displayPoints.value
  if (!points.length) return []
  const firstYear = Number(points[0]!.month.slice(0, 4))
  const lastYear = Number(points[points.length - 1]!.month.slice(0, 4))
  const span = lastYear - firstYear
  const step = span > 15 ? 4 : span > 8 ? 2 : 1
  const years = new Set<number>()
  for (let year = firstYear; year <= lastYear; year += step) years.add(year)
  years.add(lastYear)
  if (props.highlight2012 && firstYear <= 2012 && lastYear >= 2012) years.add(2012)
  return [...years]
    .sort((a, b) => a - b)
    .map((year) => {
      const i = points.findIndex((p) => Number(p.month.slice(0, 4)) >= year)
      return i === -1 ? null : { year, i, x: x(i) }
    })
    .filter((item): item is { year: number; i: number; x: number } => item !== null)
})

const gridTicks = computed(() => {
  const values = [0, 0.25, 0.5, 0.75, 1].map((f) => f * maxValue.value)
  return values.map((value) => ({ value, y: y(value) }))
})

const index2012 = computed(() => displayPoints.value.findIndex((p) => p.month.startsWith('2012')))

const markIndex = computed(() => {
  if (!props.markMonth) return -1
  if (granularity.value === 'year' && hasFullYearlySpan.value) {
    const yr = props.markMonth.slice(0, 4)
    return displayPoints.value.findIndex((p) => p.month.startsWith(yr))
  }
  return displayPoints.value.findIndex((p) => p.month === props.markMonth)
})

const markPoint = computed(() => {
  if (markIndex.value < 0) return null
  const p = displayPoints.value[markIndex.value]
  if (!p) return null
  const val = props.showHarmonized ? (p.harm ?? p.raw) : p.raw
  return {
    x: x(markIndex.value),
    y: y(val),
    point: p,
    i: markIndex.value,
    caption: p.isYear ? p.label : monthLabel(p.month),
  }
})

const peakIndex = computed(() => {
  let bestIdx = 0
  let bestVal = -Infinity
  displayPoints.value.forEach((p, i) => {
    const val = props.showHarmonized ? (p.harm ?? p.raw) : p.raw
    if (val > bestVal) {
      bestVal = val
      bestIdx = i
    }
  })
  return displayPoints.value.length ? bestIdx : null
})

const activeIndex = computed(() => hovered.value ?? pinned.value ?? (markIndex.value >= 0 ? markIndex.value : peakIndex.value))

const activePoint = computed(() => {
  if (activeIndex.value === null) return null
  const p = displayPoints.value[activeIndex.value]
  if (!p) return null
  const val = props.showHarmonized ? (p.harm ?? p.raw) : p.raw
  return {
    index: activeIndex.value,
    x: x(activeIndex.value),
    y: y(val),
    rawY: y(p.raw),
    point: p,
    isHovered: hovered.value !== null || pinned.value !== null,
  }
})

function onMove(event: PointerEvent) {
  const el = svg.value
  if (!el) return
  const rect = el.getBoundingClientRect()
  const vx = ((event.clientX - rect.left) / rect.width) * W
  const index = Math.round(((vx - PAD.left) / innerW) * (n.value - 1))
  hovered.value = Math.max(0, Math.min(n.value - 1, index))
}

function onLeave() {
  hovered.value = null
}

function onClick() {
  if (hovered.value === null) return
  pinned.value = pinned.value === hovered.value ? null : hovered.value
}

function onKey(event: KeyboardEvent) {
  const curr = hovered.value ?? pinned.value ?? Math.max(0, n.value - 1)
  if (event.key === 'ArrowLeft') {
    event.preventDefault()
    hovered.value = Math.max(0, curr - 1)
  } else if (event.key === 'ArrowRight') {
    event.preventDefault()
    hovered.value = Math.min(n.value - 1, curr + 1)
  } else if (event.key === 'Enter' || event.key === ' ') {
    event.preventDefault()
    pinned.value = pinned.value === curr ? null : curr
  } else if (event.key === 'Escape') {
    hovered.value = null
    pinned.value = null
  }
}

let observer: IntersectionObserver | null = null

function animate() {
  const targets = [rawPath.value, harmPath.value].filter((el): el is SVGPathElement => !!el)
  for (const el of targets) {
    const length = el.getTotalLength()
    if (!length) continue
    gsap.set(el, { strokeDasharray: length, strokeDashoffset: length })
    gsap.to(el, {
      strokeDashoffset: 0,
      duration: 1.4,
      ease: 'power2.inOut',
      onComplete: () => gsap.set(el, { clearProps: 'strokeDasharray,strokeDashoffset' }),
    })
  }
  if (bandPath.value) {
    gsap.fromTo(bandPath.value, { opacity: 0 }, { opacity: 1, duration: 0.9, delay: 0.3, ease: 'power2.out' })
  }
  if (areaPath.value) {
    gsap.fromTo(areaPath.value, { opacity: 0 }, { opacity: 1, duration: 0.9, delay: 0.2, ease: 'power2.out' })
  }
}

onMounted(() => {
  if (props.reducedMotion || !wrapper.value) return
  observer = new IntersectionObserver(
    (entries) => {
      if (entries.some((entry) => entry.isIntersecting)) {
        observer?.disconnect()
        animate()
      }
    },
    { threshold: 0.12 },
  )
  observer.observe(wrapper.value)
})

onBeforeUnmount(() => observer?.disconnect())
</script>

<template>
  <div ref="wrapper" class="chart">
    <div v-if="title || showRaw || showHarmonized" class="chart-head">
      <p v-if="title" class="chart-title">{{ title }}</p>
      <div class="chart-legend">
        <span v-if="showRaw" class="legend-item">
          <i class="legend-line raw"></i>{{ rawLabel ?? t('Mesures brutes des satellites', 'Raw satellite detections') }}
        </span>
        <span v-if="showHarmonized" class="legend-item">
          <i class="legend-line harm"></i>{{ harmLabel ?? t('Série remise à niveau', 'Harmonized series') }}
        </span>
        <span v-if="showBand && granularity === 'year'" class="legend-item">
          <i class="legend-band"></i>{{ t('Marge d’incertitude', 'Uncertainty band') }}
        </span>
        <span v-else-if="showBand" class="legend-item">
          <i class="legend-band"></i>{{ t('Marge d’incertitude (80 %)', 'Uncertainty band (80%)') }}
        </span>
      </div>
    </div>

    <div v-if="interactive && (hasFullYearlySpan || datasets.length > 1)" class="chart-toolbar">
      <div v-if="hasFullYearlySpan" class="chart-pills" role="group" :aria-label="t('Échelle de temps', 'Time scale')">
        <button
          type="button"
          class="chart-pill"
          :class="{ active: granularity === 'year' }"
          @click="granularity = 'year'; pinned = null"
        >
          {{ t('Par année (2001–2025)', 'By year (2001–2025)') }}
        </button>
        <button
          type="button"
          class="chart-pill"
          :class="{ active: granularity === 'month' }"
          @click="granularity = 'month'; pinned = null"
        >
          {{ t('Par mois (saisons)', 'By month (seasons)') }}
        </button>
      </div>

      <div v-if="datasets.length > 1" class="chart-pills" role="group" :aria-label="t('Type de points chauds', 'Hotspot type')">
        <button
          v-for="ds in datasets"
          :key="ds.id"
          type="button"
          class="chart-pill"
          :class="{ active: selectedDatasetId === ds.id }"
          @click="selectedDatasetId = ds.id; pinned = null"
        >
          {{ ds.label }}
        </button>
      </div>
    </div>

    <div v-if="activePoint" class="chart-readout" aria-live="polite">
      <div class="readout-period">
        <span class="readout-tag">
          {{ activePoint.isHovered ? t('Sélection', 'Selected') : t('Repère clé', 'Key highlight') }}
        </span>
        <strong>{{ activePoint.point.label }}</strong>
      </div>
      <div class="readout-metrics">
        <span v-if="showRaw" class="readout-metric raw">
          {{ t('Brut', 'Raw') }} : <strong>{{ formatCount(activePoint.point.raw) }}</strong>
        </span>
        <span v-if="showHarmonized && activePoint.point.harm !== null" class="readout-metric harm">
          {{ t('Série harmonisée', 'Harmonized') }} : <strong>{{ formatCount(activePoint.point.harm) }}</strong>
        </span>
        <span
          v-if="activePoint.point.anomaly !== null"
          class="readout-metric"
          :class="{ hot: activePoint.point.anomaly > 20 }"
        >
          {{ t('Écart à la normale', 'Vs normal') }} : <strong>{{ formatPercent(activePoint.point.anomaly) }}</strong>
        </span>
      </div>
    </div>

    <svg
      ref="svg"
      class="chart-svg"
      :viewBox="`0 0 ${W} ${H}`"
      role="img"
      :aria-label="title ?? t('Évolution des détections au Gabon', 'Detections timeline in Gabon')"
      tabindex="0"
      @pointermove="onMove"
      @pointerleave="onLeave"
      @click="onClick"
      @keydown="onKey"
    >
      <defs>
        <linearGradient :id="`rawStroke-${uid}`" x1="0" x2="1" y1="0" y2="0">
          <stop offset="0%" stop-color="#60a5fa" stop-opacity="0.85" />
          <stop offset="55%" stop-color="#93c5fd" stop-opacity="0.95" />
          <stop offset="100%" stop-color="#e2e8f0" stop-opacity="0.85" />
        </linearGradient>
        <linearGradient :id="`harmStroke-${uid}`" x1="0" x2="1" y1="0" y2="0">
          <stop offset="0%" stop-color="#5eead4" />
          <stop offset="55%" stop-color="#ffc46b" />
          <stop offset="100%" stop-color="#ff7a3d" />
        </linearGradient>
        <linearGradient :id="`harmArea-${uid}`" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" :stop-color="showHarmonized ? '#ff7a3d' : '#60a5fa'" stop-opacity="0.2" />
          <stop offset="100%" :stop-color="showHarmonized ? '#ff7a3d' : '#60a5fa'" stop-opacity="0.01" />
        </linearGradient>
        <linearGradient :id="`bandFill-${uid}`" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stop-color="#5eead4" stop-opacity="0.22" />
          <stop offset="100%" stop-color="#5eead4" stop-opacity="0.03" />
        </linearGradient>
      </defs>

      <g class="grid">
        <line
          v-for="tick in gridTicks"
          :key="tick.value"
          :x1="PAD.left"
          :x2="W - PAD.right"
          :y1="tick.y"
          :y2="tick.y"
        />
        <text
          v-for="tick in gridTicks"
          :key="`label-${tick.value}`"
          :x="PAD.left - 12"
          :y="tick.y + 4"
          text-anchor="end"
        >
          {{ formatCount(tick.value) }}
        </text>
      </g>

      <line
        v-if="highlight2012 && index2012 >= 0"
        class="year-2012"
        :x1="x(index2012)"
        :x2="x(index2012)"
        :y1="PAD.top"
        :y2="PAD.top + innerH"
      />
      <text
        v-if="highlight2012 && index2012 >= 0"
        class="year-2012-label"
        :x="x(index2012) + 8"
        :y="PAD.top + 14"
      >
        {{ t('2012 · Arrivée du satellite VIIRS', '2012 · VIIRS satellite launch') }}
      </text>

      <g class="x-axis">
        <text
          v-for="tick in yearTicks"
          :key="tick.year"
          :x="tick.x"
          :y="H - 12"
          text-anchor="middle"
          :class="{ strong: tick.year === 2012 }"
        >
          {{ tick.year }}
        </text>
      </g>

      <path v-if="bandD" ref="bandPath" class="band" :d="bandD" :fill="`url(#bandFill-${uid})`" />
      <path v-if="areaD" ref="areaPath" class="area" :d="areaD" :fill="`url(#harmArea-${uid})`" />
      <path
        v-if="rawD"
        ref="rawPath"
        class="line raw"
        :class="{ solid: !showHarmonized }"
        :d="rawD"
        :stroke="`url(#rawStroke-${uid})`"
      />
      <path
        v-if="harmD"
        ref="harmPath"
        class="line harm"
        :d="harmD"
        :stroke="`url(#harmStroke-${uid})`"
      />

      <!-- Points visibles en vue annuelle pour faciliter la lecture -->
      <g v-if="granularity === 'year' && hasFullYearlySpan" class="year-dots">
        <template v-for="(pt, idx) in displayPoints" :key="pt.month">
          <circle
            v-if="showRaw"
            :cx="x(idx)"
            :cy="y(pt.raw)"
            r="3.2"
            class="dot-raw"
          />
          <circle
            v-if="showHarmonized && pt.harm !== null"
            :cx="x(idx)"
            :cy="y(pt.harm)"
            r="3.6"
            class="dot-harm"
          />
        </template>
      </g>

      <g v-if="markPoint" class="mark">
        <line
          :x1="markPoint.x"
          :x2="markPoint.x"
          :y1="PAD.top"
          :y2="PAD.top + innerH"
          class="mark-line"
        />
        <circle :cx="markPoint.x" :cy="markPoint.y" r="5.5" class="mark-dot" />
        <text
          :x="markPoint.x > W - 180 ? markPoint.x - 12 : markPoint.x + 12"
          :y="Math.max(PAD.top + 16, markPoint.y - 12)"
          :text-anchor="markPoint.x > W - 180 ? 'end' : 'start'"
          class="mark-label"
        >
          {{ markPoint.caption }}
        </text>
      </g>

      <g v-if="activePoint" class="hover">
        <line
          :x1="activePoint.x"
          :x2="activePoint.x"
          :y1="PAD.top"
          :y2="PAD.top + innerH"
        />
        <circle v-if="showRaw" :cx="activePoint.x" :cy="activePoint.rawY" r="4.5" class="hover-raw" />
        <circle v-if="showHarmonized && activePoint.point.harm !== null" :cx="activePoint.x" :cy="activePoint.y" r="5.5" />
      </g>

      <rect
        :x="PAD.left"
        :y="PAD.top"
        :width="innerW"
        :height="innerH"
        fill="transparent"
        style="cursor: crosshair"
      />
    </svg>

    <p v-if="interactive" class="chart-hint">
      {{
        t(
          'Passez la souris ou cliquez sur la courbe pour comparer chaque période (flèches gauche/droite au clavier).',
          'Hover or click anywhere along the curve to inspect each period (or use left/right arrow keys).',
        )
      }}
    </p>
  </div>
</template>

<style scoped>
.chart {
  position: relative;
  width: 100%;
}

.chart-head {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px 20px;
  margin-bottom: 14px;
}

.chart-title {
  font-size: 0.96rem;
  font-weight: 600;
  color: var(--ink);
}

.chart-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 18px;
}

.legend-item {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 0.76rem;
  color: #cbd5e1;
}

.legend-line {
  width: 22px;
  height: 2.5px;
  display: block;
  border-radius: 2px;
}

.legend-line.raw {
  background: #60a5fa;
}

.legend-line.harm {
  background: linear-gradient(90deg, #5eead4, #ff7a3d);
}

.legend-band {
  width: 20px;
  height: 10px;
  display: block;
  border-radius: 2px;
  background: rgba(94, 234, 212, 0.22);
  border: 1px solid rgba(94, 234, 212, 0.45);
}

.chart-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 12px;
}

.chart-pills {
  display: inline-flex;
  flex-wrap: wrap;
  gap: 4px;
  padding: 3px;
  border: 1px solid var(--line-strong);
  border-radius: 10px;
  background: rgba(244, 241, 232, 0.03);
}

.chart-pill {
  padding: 6px 11px;
  border: 0;
  border-radius: 7px;
  background: transparent;
  color: var(--muted);
  font-size: 0.74rem;
  font-weight: 500;
  cursor: pointer;
  transition:
    background 0.2s ease,
    color 0.2s ease;
}

.chart-pill:hover {
  color: var(--ink);
}

.chart-pill.active {
  background: var(--ink);
  color: #05070b;
  font-weight: 600;
}

.chart-readout {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 10px 18px;
  margin-bottom: 10px;
  padding: 10px 14px;
  border: 1px solid var(--line);
  border-radius: 10px;
  background: rgba(244, 241, 232, 0.04);
}

.readout-period {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  font-size: 0.9rem;
  color: var(--ink);
}

.readout-tag {
  font-family: var(--font-mono);
  font-size: 0.64rem;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--gold);
}

.readout-metrics {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 18px;
  font-size: 0.8rem;
  color: var(--muted);
}

.readout-metric strong {
  font-family: var(--font-mono);
  color: var(--ink);
}

.readout-metric.raw strong {
  color: #93c5fd;
}

.readout-metric.harm strong,
.readout-metric.hot strong {
  color: var(--gold);
}

.chart-svg {
  width: 100%;
  height: auto;
  overflow: visible;
  touch-action: none;
}

.grid line {
  stroke: rgba(244, 241, 232, 0.11);
  stroke-width: 1;
}

.grid text,
.x-axis text {
  fill: #b8c4d0;
  font-family: var(--font-mono);
  font-size: 12px;
  letter-spacing: 0.01em;
}

.x-axis text.strong {
  fill: var(--gold);
  font-weight: 600;
}

.year-2012 {
  stroke: rgba(255, 168, 96, 0.65);
  stroke-width: 1.5;
  stroke-dasharray: 4 4;
}

.year-2012-label {
  fill: #ffb37a;
  font-family: var(--font-mono);
  font-size: 11px;
  font-weight: 600;
}

.line {
  fill: none;
  stroke-linecap: round;
  stroke-linejoin: round;
  vector-effect: non-scaling-stroke;
}

.line.raw {
  stroke-width: 2;
  stroke-dasharray: 5 4;
  opacity: 0.9;
}

.line.raw.solid {
  stroke-dasharray: none;
  stroke-width: 2.5;
}

.line.harm {
  stroke-width: 2.8;
  filter: drop-shadow(0 0 8px rgba(255, 122, 61, 0.35));
}

.dot-raw {
  fill: #93c5fd;
  stroke: var(--bg);
  stroke-width: 1.5;
}

.dot-harm {
  fill: #ffc46b;
  stroke: var(--bg);
  stroke-width: 1.5;
}

.mark-line {
  stroke: rgba(255, 196, 107, 0.45);
  stroke-width: 1.2;
  stroke-dasharray: 2 4;
}

.mark-dot {
  fill: var(--gold);
  stroke: var(--bg);
  stroke-width: 2;
}

.mark-label {
  fill: var(--gold);
  font-family: var(--font-mono);
  font-size: 11px;
  font-weight: 600;
}

.hover line {
  stroke: rgba(244, 241, 232, 0.42);
  stroke-width: 1;
}

.hover circle {
  fill: var(--gold);
  stroke: var(--bg);
  stroke-width: 2;
}

.hover circle.hover-raw {
  fill: #60a5fa;
}

.chart-hint {
  margin-top: 8px;
  font-size: 0.74rem;
  color: var(--dim);
}
</style>
