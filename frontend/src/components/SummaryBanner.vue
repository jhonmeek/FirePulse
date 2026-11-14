<script setup lang="ts">
import { computed } from 'vue'
import type { CalendarPoint } from '@/types/api'
import { MONTHS_LONG, formatCount, monthLabel } from '@/utils/calendar'
import { deltaPhrase, lastDataMonth, roughCount, yearSummary } from '@/utils/summary'

/**
 * « En bref » : la réponse en une phrase, avant tout graphique, pour un visiteur non spécialiste.
 * Calculée sur la série chargée (zone et filtre torchères courants), jusqu'à la fin de la plage.
 */
const props = defineProps<{
  series: CalendarPoint[]
  yearRange: [number, number]
  regionName: string
}>()

const s = computed(() => yearSummary(props.series, props.yearRange[1]))
const last = computed(() => lastDataMonth(props.series))
const tone = computed(() => {
  const d = s.value?.deltaPercent ?? 0
  return d >= 5 ? 'text-orange-800' : d <= -5 ? 'text-purple-800' : 'text-stone-900'
})
</script>

<template>
  <section aria-labelledby="summary-title" class="card">
    <h2 id="summary-title" class="text-xs font-semibold uppercase tracking-wide text-stone-600">
      En bref - {{ regionName }}
    </h2>
    <p v-if="s" class="mt-1 text-lg leading-snug text-stone-900 sm:text-xl">
      En {{ s.year }}, environ
      <strong class="tabular-nums">{{ formatCount(roughCount(s.total)) }}</strong>
      points de feu détectés par satellite,
      <strong :class="tone">{{ deltaPhrase(s.deltaPercent) }}</strong
      >. La saison des feux culmine en <strong>{{ MONTHS_LONG[s.peakMonth - 1] }}</strong
      >.
    </p>
    <p v-else class="mt-1 text-stone-700">
      Pas d'année complète sur la période choisie : élargissez la plage d'années.
    </p>
    <p class="mt-2 text-xs text-stone-600">
      Un point de feu est une zone de chaleur repérée par un satellite lors d'un passage ; un grand
      feu en produit plusieurs.
      <template v-if="last"> Données jusqu'à {{ monthLabel(last) }}.</template>
      <template v-if="s?.provisional"> Chiffres {{ s.year }} encore provisoires.</template>
      <span v-if="s" class="sr-only">
        Année normale : {{ formatCount(roughCount(s.normal)) }} points de feu (somme des médianes
        mensuelles 2001-2025).
      </span>
    </p>
  </section>
</template>
