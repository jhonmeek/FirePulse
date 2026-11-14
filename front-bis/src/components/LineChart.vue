<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, useId, useTemplateRef } from 'vue'
import { gsap } from '@/lib/motion'
import { formatCount, formatPercent, monthLabel } from '@/lib/data'

interface ChartPoint {
  month: string
  raw: number
  harm: number | null
  lo: number | null
  hi: number | null
  anomaly: number | null
}

const props = withDefaults(
  defineProps<{
    points: ChartPoint[]
    showRaw?: boolean
    showHarmonized?: boolean
    showBand?: boolean
    highlight2012?: boolean
    markMonth?: string | null
    yMax?: number
    reducedMotion?: boolean
    rawLabel?: string
    harmLabel?: string
    title?: string
  }>(),
  {
    showRaw: true,
    showHarmonized: false,
    showBand: false,
    highlight2012: false,
    markMonth: null,
    yMax: undefined,
    reducedMotion: false,
    rawLabel: 'Détections brutes MODIS + S-NPP',
    harmLabel: 'Série harmonisée (équivalent VIIRS)',
    title: undefined,
  },
)

const uid = useId()
const W = 1000
const H = 420
const PAD = { top: 28, right: 24, bottom: 42, left: 62 }
const innerW = W - PAD.left - PAD.right
const innerH = H - PAD.top - PAD.bottom

const wrapper = useTemplateRef<HTMLDivElement>('wrapper')
const svg = useTemplateRef<SVGSVGElement>('svg')
const rawPath = useTemplateRef<SVGPathElement>('rawPath')
const harmPath = useTemplateRef<SVGPathElement>('harmPath')
const bandPath = useTemplateRef<SVGPathElement>('bandPath')
const areaPath = useTemplateRef<SVGPathElement>('areaPath')

const hovered = ref<number | null>(null)

const n = computed(() => props.points.length)
const maxValue = computed(() => {
  let max = 0
  for (const p of props.points) {
    if (props.showRaw) max = Math.max(max, p.raw)
    if (props.showHarmonized) max = Math.max(max, p.harm ?? 0, p.hi ?? 0)
  }
  return props.yMax ?? Math.max(1, max * 1.08)
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
  props.points.forEach((p, i) => {
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
  props.points.forEach((p, i) => {
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
  if (!props.showHarmonized) return ''
  const points = props.points
    .map((p, i) => ({ p, i }))
    .filter(({ p }) => p.harm !== null)
  if (points.length < 2) return ''
  const base = y(0)
  const first = points[0]!
  const last = points[points.length - 1]!
  const top = points
    .map(({ p, i }, index) => `${index ? 'L' : 'M'}${x(i).toFixed(2)},${y(p.harm!).toFixed(2)}`)
    .join('')
  return `${top}L${x(last.i).toFixed(2)},${base.toFixed(2)}L${x(first.i).toFixed(2)},${base.toFixed(2)}Z`
})

const yearTicks = computed(() => {
  const points = props.points
  if (!points.length) return []
  const firstYear = Number(points[0]!.month.slice(0, 4))
  const lastYear = Number(points[points.length - 1]!.month.slice(0, 4))
  const span = lastYear - firstYear
  const step = span > 15 ? 5 : span > 8 ? 2 : 1
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
    .filter((t): t is { year: number; i: number; x: number } => t !== null)
})

const gridTicks = computed(() => {
  const values = [0, 0.25, 0.5, 0.75, 1].map((f) => f * maxValue.value)
  return values.map((value) => ({ value, y: y(value) }))
})

const index2012 = computed(() => props.points.findIndex((p) => p.month.startsWith('2012')))
const markIndex = computed(() =>
  props.markMonth ? props.points.findIndex((p) => p.month === props.markMonth) : -1,
)
const markPoint = computed(() => {
  if (markIndex.value < 0) return null
  const p = props.points[markIndex.value]
  if (!p || p.harm === null) return null
  return { x: x(markIndex.value), y: y(p.harm), point: p, i: markIndex.value }
})

const hoverPoint = computed(() => {
  if (hovered.value === null) return null
  const p = props.points[hovered.value]
  if (!p) return null
  const value = p.harm ?? p.raw
  return {
    x: x(hovered.value),
    y: y(value),
    point: p,
    left: `${(x(hovered.value) / W) * 100}%`,
    top: `${(y(value) / H) * 100}%`,
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

function onKey(event: KeyboardEvent) {
  if (hovered.value === null) hovered.value = n.value - 1
  if (event.key === 'ArrowLeft') hovered.value = Math.max(0, hovered.value - 1)
  if (event.key === 'ArrowRight') hovered.value = Math.min(n.value - 1, hovered.value + 1)
  if (event.key === 'Escape') hovered.value = null
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
      duration: 2.1,
      ease: 'power2.inOut',
      onComplete: () => gsap.set(el, { clearProps: 'strokeDasharray,strokeDashoffset' }),
    })
  }
  if (bandPath.value) {
    gsap.fromTo(bandPath.value, { opacity: 0 }, { opacity: 1, duration: 1.4, delay: 0.5, ease: 'power2.out' })
  }
  if (areaPath.value) {
    gsap.fromTo(areaPath.value, { opacity: 0 }, { opacity: 1, duration: 1.2, delay: 0.3, ease: 'power2.out' })
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
          <i class="legend-line raw"></i>{{ rawLabel }}
        </span>
        <span v-if="showHarmonized" class="legend-item">
          <i class="legend-line harm"></i>{{ harmLabel }}
        </span>
        <span v-if="showBand" class="legend-item">
          <i class="legend-band"></i>Incertitude 80 %
        </span>
      </div>
    </div>

    <svg
      ref="svg"
      class="chart-svg"
      :viewBox="`0 0 ${W} ${H}`"
      role="img"
      :aria-label="title ?? 'Série temporelle des détections de points chauds'"
      tabindex="0"
      @pointermove="onMove"
      @pointerleave="onLeave"
      @keydown="onKey"
    >
      <defs>
        <linearGradient :id="`rawStroke-${uid}`" x1="0" x2="1" y1="0" y2="0">
          <stop offset="0%" stop-color="#60a5fa" stop-opacity="0.55" />
          <stop offset="55%" stop-color="#60a5fa" stop-opacity="0.85" />
          <stop offset="100%" stop-color="#f4f1e8" stop-opacity="0.7" />
        </linearGradient>
        <linearGradient :id="`harmStroke-${uid}`" x1="0" x2="1" y1="0" y2="0">
          <stop offset="0%" stop-color="#5eead4" />
          <stop offset="55%" stop-color="#ffc46b" />
          <stop offset="100%" stop-color="#ff7a3d" />
        </linearGradient>
        <linearGradient :id="`harmArea-${uid}`" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stop-color="#ff7a3d" stop-opacity="0.22" />
          <stop offset="100%" stop-color="#ff7a3d" stop-opacity="0" />
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
        2012 · VIIRS
      </text>

      <g class="x-axis">
        <text
          v-for="tick in yearTicks"
          :key="tick.year"
          :x="tick.x"
          :y="H - 14"
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

      <g v-if="markPoint" class="mark">
        <line
          :x1="markPoint.x"
          :x2="markPoint.x"
          :y1="PAD.top"
          :y2="PAD.top + innerH"
          class="mark-line"
        />
        <circle :cx="markPoint.x" :cy="markPoint.y" r="5" class="mark-dot" />
        <text
          :x="markPoint.x > W - 180 ? markPoint.x - 12 : markPoint.x + 12"
          :y="Math.max(PAD.top + 16, markPoint.y - 14)"
          :text-anchor="markPoint.x > W - 180 ? 'end' : 'start'"
          class="mark-label"
        >
          {{ monthLabel(markPoint.point.month) }}
        </text>
      </g>

      <g v-if="hoverPoint" class="hover">
        <line
          :x1="hoverPoint.x"
          :x2="hoverPoint.x"
          :y1="PAD.top"
          :y2="PAD.top + innerH"
        />
        <circle :cx="hoverPoint.x" :cy="hoverPoint.y" r="4.5" />
      </g>

      <rect
        :x="PAD.left"
        :y="PAD.top"
        :width="innerW"
        :height="innerH"
        fill="transparent"
      />
    </svg>

    <div
      v-if="hoverPoint"
      class="chart-tooltip"
      :style="{ left: hoverPoint.left, top: hoverPoint.top }"
    >
      <p class="tooltip-month">{{ monthLabel(hoverPoint.point.month) }}</p>
      <dl>
        <div>
          <dt>Brut</dt>
          <dd>{{ formatCount(hoverPoint.point.raw) }}</dd>
        </div>
        <div v-if="showHarmonized">
          <dt>Harmonisé</dt>
          <dd>{{ formatCount(hoverPoint.point.harm) }}</dd>
        </div>
        <div v-if="hoverPoint.point.anomaly !== null">
          <dt>Anomalie</dt>
          <dd :class="{ positive: hoverPoint.point.anomaly > 0 }">
            {{ formatPercent(hoverPoint.point.anomaly) }}
          </dd>
        </div>
      </dl>
    </div>
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
  gap: 10px 24px;
  margin-bottom: 10px;
}

.chart-title {
  font-size: 0.82rem;
  font-weight: 500;
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
  gap: 7px;
  font-family: var(--font-mono);
  font-size: 0.56rem;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--dim);
}

.legend-line {
  width: 20px;
  height: 2px;
  display: block;
  border-radius: 2px;
}

.legend-line.raw {
  background: #60a5fa;
  opacity: 0.7;
}

.legend-line.harm {
  background: linear-gradient(90deg, #5eead4, #ff7a3d);
}

.legend-band {
  width: 20px;
  height: 8px;
  display: block;
  border-radius: 2px;
  background: rgba(94, 234, 212, 0.18);
  border: 1px solid rgba(94, 234, 212, 0.35);
}

.chart-svg {
  width: 100%;
  height: auto;
  overflow: visible;
  touch-action: none;
}

.grid line {
  stroke: rgba(244, 241, 232, 0.09);
  stroke-width: 1;
}

.grid text,
.x-axis text {
  fill: var(--dim);
  font-family: var(--font-mono);
  font-size: 11px;
  letter-spacing: 0.02em;
}

.x-axis text.strong {
  fill: var(--gold);
}

.year-2012 {
  stroke: rgba(255, 122, 61, 0.5);
  stroke-width: 1;
  stroke-dasharray: 3 5;
}

.year-2012-label {
  fill: var(--ember);
  font-family: var(--font-mono);
  font-size: 10px;
  letter-spacing: 0.08em;
}

.line {
  fill: none;
  stroke-linecap: round;
  stroke-linejoin: round;
  vector-effect: non-scaling-stroke;
}

.line.raw {
  stroke-width: 1.4;
  stroke-dasharray: 4 3;
  opacity: 0.72;
}

.line.harm {
  stroke-width: 2.4;
  filter: drop-shadow(0 0 8px rgba(255, 122, 61, 0.35));
}

.mark-line {
  stroke: rgba(255, 196, 107, 0.35);
  stroke-width: 1;
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
  font-size: 10px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}

.hover line {
  stroke: rgba(244, 241, 232, 0.35);
  stroke-width: 1;
}

.hover circle {
  fill: var(--ink);
  stroke: var(--bg);
  stroke-width: 2;
}

.chart-tooltip {
  position: absolute;
  z-index: 5;
  min-width: 148px;
  padding: 10px 12px;
  border: 1px solid var(--line-strong);
  border-radius: 10px;
  background: rgba(7, 11, 18, 0.94);
  box-shadow: 0 18px 40px -18px rgba(0, 0, 0, 0.9);
  pointer-events: none;
  transform: translate(-50%, -112%);
  backdrop-filter: blur(10px);
}

.tooltip-month {
  font-family: var(--font-mono);
  font-size: 0.6rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--gold);
}

.chart-tooltip dl {
  margin: 7px 0 0;
  display: grid;
  gap: 3px;
}

.chart-tooltip dl > div {
  display: flex;
  justify-content: space-between;
  gap: 14px;
}

.chart-tooltip dt {
  font-size: 0.68rem;
  color: var(--dim);
}

.chart-tooltip dd {
  margin: 0;
  font-family: var(--font-mono);
  font-size: 0.68rem;
  color: var(--ink);
}

.chart-tooltip dd.positive {
  color: var(--gold);
}
</style>
