<script setup lang="ts">
import { computed } from 'vue'
import type { CalendarPoint } from '@/types/api'
import { compareYear } from '@/utils/comparison'
import { MONTHS_LONG, MONTHS_SHORT, formatCount } from '@/utils/calendar'

/**
 * Série de comparaison du calendrier : une année face à l'année type (médiane 2001-2025
 * et intervalle interquartile). SVG léger (pas d'ECharts) : rendu immédiat, aucun chunk.
 */
const props = defineProps<{
  series: CalendarPoint[]
  years: number[]
}>()
const year = defineModel<number>('year', { required: true })

const cmp = computed(() => compareYear(props.series, year.value))

// Géométrie (viewBox fixe, mise à l'échelle par le navigateur : pas de recalcul au resize)
const W = 600
const H = 160
const PAD = { l: 8, r: 8, t: 10, b: 4 }
const slot = (W - PAD.l - PAD.r) / 12
const yMax = computed(() =>
  Math.max(
    1,
    ...cmp.value.months.map((m) => Math.max(m.value ?? 0, m.iqr?.[1] ?? 0, m.median ?? 0)),
  ),
)
const y = (v: number) => PAD.t + (H - PAD.t - PAD.b) * (1 - v / yMax.value)
const cx = (i: number) => PAD.l + slot * (i + 0.5)

const bandPath = computed(() => {
  const pts = cmp.value.months
    .map((m, i) => (m.iqr ? { i, lo: m.iqr[0], hi: m.iqr[1] } : null))
    .filter((p): p is { i: number; lo: number; hi: number } => p !== null)
  if (pts.length < 2) return ''
  const top = pts.map((p) => `${cx(p.i)},${y(p.hi)}`).join(' L')
  const bottom = [...pts]
    .reverse()
    .map((p) => `${cx(p.i)},${y(p.lo)}`)
    .join(' L')
  return `M${top} L${bottom} Z`
})
const medianPath = computed(() =>
  cmp.value.months
    .map((m, i) => (m.median === null ? null : `${cx(i)},${y(m.median)}`))
    .filter(Boolean)
    .map((p, i) => `${i ? 'L' : 'M'}${p}`)
    .join(' '),
)

const deltaLabel = computed(() => {
  const d = cmp.value.deltaPercent
  if (d === null) return null
  const sign = d > 0 ? '+' : d < 0 ? '−' : ''
  return `${sign}${Math.abs(d).toLocaleString('fr-FR', { maximumFractionDigits: 0 })} %`
})
const deltaTone = computed(() =>
  (cmp.value.deltaPercent ?? 0) > 0 ? 'text-orange-800' : 'text-purple-800',
)
</script>

<template>
  <section aria-labelledby="compare-title" class="mt-5 border-t border-stone-200 pt-4">
    <div class="flex flex-wrap items-end justify-between gap-3">
      <div>
        <h3 id="compare-title" class="text-sm font-semibold text-stone-900">
          Comparaison avec l'année type
        </h3>
        <p class="text-xs text-stone-600">
          Barres : année choisie · trait : médiane · bande : 50 % central (IQR)
        </p>
      </div>
      <label class="flex items-center gap-2 text-sm">
        <span class="text-stone-600">Année</span>
        <select v-model.number="year" class="field">
          <option v-for="yy in years" :key="yy" :value="yy">{{ yy }}</option>
        </select>
      </label>
    </div>

    <dl class="mt-3 grid grid-cols-3 gap-2 text-center">
      <div class="rounded-lg bg-stone-50 px-2 py-2">
        <dt class="text-[0.7rem] uppercase tracking-wide text-stone-500">Écart cumulé</dt>
        <dd :class="['text-lg font-semibold tabular-nums', deltaTone]">{{ deltaLabel ?? '-' }}</dd>
      </div>
      <div class="rounded-lg bg-stone-50 px-2 py-2">
        <dt class="text-[0.7rem] uppercase tracking-wide text-stone-500">Mois > 3e quartile</dt>
        <dd class="text-lg font-semibold tabular-nums text-stone-900">{{ cmp.aboveIqr }} / 12</dd>
      </div>
      <div class="rounded-lg bg-stone-50 px-2 py-2">
        <dt class="text-[0.7rem] uppercase tracking-wide text-stone-500">Plus fort écart</dt>
        <dd class="text-lg font-semibold capitalize text-stone-900">
          {{ cmp.peak ? MONTHS_LONG[cmp.peak.month - 1] : '-' }}
        </dd>
      </div>
    </dl>

    <svg
      :viewBox="`0 0 ${W} ${H}`"
      class="mt-3 h-40 w-full"
      preserveAspectRatio="none"
      role="img"
      :aria-label="`${year} comparé à la médiane 2001-2025 : écart cumulé ${deltaLabel ?? 'indisponible'}`"
    >
      <path v-if="bandPath" :d="bandPath" class="fill-stone-300/50" />
      <g>
        <rect
          v-for="(m, i) in cmp.months"
          v-show="m.value !== null"
          :key="m.month"
          :x="cx(i) - slot * 0.28"
          :width="slot * 0.56"
          :y="y(m.value ?? 0)"
          :height="Math.max(0, H - PAD.b - y(m.value ?? 0))"
          rx="2"
          :class="
            m.value !== null && m.iqr && m.value > m.iqr[1] ? 'fill-orange-600' : 'fill-orange-300'
          "
        >
          <title>
            {{ MONTHS_LONG[i] }} {{ year }} : {{ formatCount(m.value) }} - médiane
            {{ formatCount(m.median) }}
          </title>
        </rect>
      </g>
      <path
        :d="medianPath"
        fill="none"
        class="stroke-stone-900"
        stroke-width="2"
        stroke-linejoin="round"
        vector-effect="non-scaling-stroke"
      />
    </svg>
    <!-- Libellés hors SVG : preserveAspectRatio="none" étirerait le texte. -->
    <div class="flex px-[1.33%] text-center text-[0.7rem] text-stone-500" aria-hidden="true">
      <span v-for="m in MONTHS_SHORT" :key="m" class="flex-1">{{ m[0]!.toUpperCase() }}</span>
    </div>

    <!-- sr-only sur un <div> : appliqué à une <table>, il ne réduit pas sa largeur (débordement mobile). -->
    <div class="sr-only">
      <table>
        <caption>
          {{
            year
          }}
          comparé à la médiane 2001-2025, détections équivalentes VIIRS par mois
        </caption>
        <thead>
          <tr>
            <th scope="col">Mois</th>
            <th scope="col">{{ year }}</th>
            <th scope="col">Médiane</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(m, i) in cmp.months" :key="m.month">
            <th scope="row">{{ MONTHS_LONG[i] }}</th>
            <td>{{ formatCount(m.value) }}</td>
            <td>{{ formatCount(m.median) }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>
