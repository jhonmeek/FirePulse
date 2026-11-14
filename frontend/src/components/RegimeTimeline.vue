<script setup lang="ts">
import { computed } from 'vue'
import type { SensorRegime } from '@/types/api'
import { REGIME_LABELS } from '@/utils/calendar'

/**
 * Bandeau de transparence capteurs (guide v2 §6.2) : les régimes successifs
 * sur l'axe du temps, avec la plage d'années affichée mise en évidence.
 */
const props = defineProps<{ yearRange: [number, number] }>()

const START = 2000 + 10 / 12 // 2000-11
const END = 2027

const segments: { regime: SensorRegime; from: number; to: number; tone: string; short: string }[] =
  [
    {
      regime: 'modis_terra_only',
      from: START,
      to: 2002.5,
      tone: 'bg-stone-300',
      short: 'Terra seul',
    },
    {
      regime: 'modis_terra_aqua',
      from: 2002.5,
      to: 2012 + 1 / 12,
      tone: 'bg-stone-400',
      short: 'MODIS reconstitué',
    },
    {
      regime: 'viirs_snpp_observed',
      from: 2012 + 1 / 12,
      to: 2026 + 10 / 12,
      tone: 'bg-amber-200',
      short: 'VIIRS S-NPP',
    },
    {
      regime: 'viirs_noaa20_bridge',
      from: 2026 + 10 / 12,
      to: END,
      tone: 'bg-amber-400',
      short: 'NOAA-20',
    },
  ]

const pct = (y: number) => ((y - START) / (END - START)) * 100

const highlight = computed(() => ({
  left: `${pct(Math.max(START, props.yearRange[0]))}%`,
  width: `${pct(props.yearRange[1] + 1) - pct(Math.max(START, props.yearRange[0]))}%`,
}))

const ticks = [2001, 2005, 2010, 2015, 2020, 2025]
</script>

<template>
  <figure class="text-xs text-stone-700">
    <figcaption class="mb-1 font-medium text-stone-800">Régimes d'observation</figcaption>
    <div class="relative h-7 overflow-hidden rounded-md">
      <div
        v-for="s in segments"
        :key="s.regime"
        :class="[
          'absolute inset-y-0 flex items-center justify-center truncate border-r border-white px-1',
          s.tone,
        ]"
        :style="{ left: `${pct(s.from)}%`, width: `${pct(s.to) - pct(s.from)}%` }"
        :title="REGIME_LABELS[s.regime]"
      >
        <span class="truncate">{{ s.short }}</span>
      </div>
      <div
        class="pointer-events-none absolute inset-y-0 rounded-sm ring-2 ring-stone-900 ring-inset"
        :style="highlight"
        aria-hidden="true"
      />
    </div>
    <div class="relative h-4" aria-hidden="true">
      <span
        v-for="t in ticks"
        :key="t"
        class="absolute -translate-x-1/2 tabular-nums"
        :style="{ left: `${pct(t)}%` }"
        >{{ t }}</span
      >
    </div>
    <p class="sr-only">
      De novembre 2000 à juin 2002 : MODIS Terra seul. De juillet 2002 à janvier 2012 : MODIS Terra
      et Aqua, reconstitué à l'échelle VIIRS. De février 2012 à octobre 2026 : VIIRS Suomi-NPP
      observé. À partir de novembre 2026 : pont VIIRS NOAA-20.
    </p>
  </figure>
</template>
