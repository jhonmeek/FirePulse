<script setup lang="ts">
import { computed } from 'vue'
import type { CalendarPoint } from '@/types/api'
import {
  COVERAGE_LABELS,
  MONTHS_LONG,
  REGIME_LABELS,
  formatAnomaly,
  formatCount,
  isProvisional,
  monthLabel,
} from '@/utils/calendar'

const props = defineProps<{
  point: CalendarPoint | null
  rank: { rank: number; total: number } | null
  /** true = mois épinglé par clic ; false = aperçu au survol. */
  pinned: boolean
}>()

const emit = defineEmits<{ unpin: [] }>()

const p = computed(() => props.point)
const observed = computed(
  () => p.value && p.value.ci_low !== null && p.value.ci_low === p.value.ci_high,
)
const anomalyTone = computed(() => {
  const a = p.value?.anomaly_percent ?? p.value?.anomaly_absolute ?? 0
  return a > 0 ? 'text-orange-800' : a < 0 ? 'text-purple-800' : 'text-stone-800'
})
const rawRows = computed(() =>
  p.value
    ? [
        { label: 'MODIS Terra', value: p.value.modis_terra_count },
        { label: 'MODIS Aqua', value: p.value.modis_aqua_count },
        { label: 'VIIRS S-NPP', value: p.value.viirs_snpp_count },
        { label: 'VIIRS NOAA-20', value: p.value.viirs_noaa20_count },
      ]
    : [],
)
</script>

<template>
  <section aria-live="polite" class="rounded-lg border border-stone-200 bg-white p-4 text-sm">
    <template v-if="p">
      <header class="flex items-start justify-between gap-2">
        <div>
          <p class="text-xs uppercase tracking-wide text-stone-500">
            {{ pinned ? 'Mois sélectionné' : 'Aperçu' }}
          </p>
          <h2 class="text-lg font-semibold capitalize text-stone-900">{{ monthLabel(p.month) }}</h2>
        </div>
        <button
          v-if="pinned"
          type="button"
          class="rounded px-2 py-1 text-xs text-stone-600 hover:bg-stone-100 focus-visible:outline-2 focus-visible:outline-orange-600"
          @click="emit('unpin')"
        >
          Désélectionner
        </button>
      </header>

      <template v-if="p.harmonized_value !== null">
        <p class="mt-3">
          <span class="text-3xl font-semibold tabular-nums text-stone-900">{{
            formatCount(p.harmonized_value)
          }}</span>
          <span class="ml-1 text-stone-600">détections équivalentes VIIRS 375 m</span>
        </p>
        <p v-if="!observed && p.ci_low !== null" class="text-stone-600">
          Intervalle 80 % : {{ formatCount(p.ci_low) }} – {{ formatCount(p.ci_high) }}
        </p>
        <p v-else-if="observed" class="text-stone-600">
          Valeur observée directement (sans reconstitution)
        </p>
        <p v-else class="text-stone-600">Intervalle d'incertitude non disponible pour cette zone</p>

        <dl class="mt-4 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5">
          <dt class="text-stone-600">Médiane de {{ MONTHS_LONG[+p.month.slice(5) - 1] }}</dt>
          <dd class="tabular-nums">
            {{ formatCount(p.baseline_median) }}
            <span v-if="p.baseline_iqr" class="text-stone-500">
              (IQR {{ formatCount(p.baseline_iqr[0]) }} – {{ formatCount(p.baseline_iqr[1]) }})
            </span>
          </dd>
          <dt class="text-stone-600">Anomalie</dt>
          <dd :class="['font-semibold tabular-nums', anomalyTone]">{{ formatAnomaly(p) }}</dd>
          <template v-if="rank">
            <dt class="text-stone-600">Rang historique</dt>
            <dd>
              {{ rank.rank === 1 ? '1er' : `${rank.rank}e` }} plus élevé sur {{ rank.total }}
              {{ MONTHS_LONG[+p.month.slice(5) - 1] }} (2001–2025)
            </dd>
          </template>
          <dt class="text-stone-600">Régime capteur</dt>
          <dd>{{ REGIME_LABELS[p.sensor_regime] }}</dd>
          <dt class="text-stone-600">Couverture</dt>
          <dd>
            {{ COVERAGE_LABELS[p.coverage_status] }}
            <span
              v-if="isProvisional(p.coverage_status)"
              class="ml-1 rounded bg-amber-100 px-1.5 py-0.5 text-xs text-amber-900"
              >provisoire</span
            >
          </dd>
        </dl>
      </template>
      <p v-else class="mt-3 text-stone-600">Aucune donnée exploitable pour ce mois.</p>

      <details class="mt-4">
        <summary class="cursor-pointer text-stone-700">Détections brutes par capteur</summary>
        <table class="mt-2 w-full text-left">
          <tbody>
            <tr v-for="r in rawRows" :key="r.label" class="border-t border-stone-100">
              <th scope="row" class="py-1 font-normal text-stone-600">{{ r.label }}</th>
              <td class="py-1 text-right tabular-nums">
                {{ r.value === null ? 'capteur non actif' : formatCount(r.value) }}
              </td>
            </tr>
          </tbody>
        </table>
      </details>

      <p v-if="p.uncertainty_note" class="mt-3 text-xs text-stone-500">{{ p.uncertainty_note }}</p>
    </template>

    <p v-else class="text-stone-600">
      Survolez ou parcourez le calendrier au clavier pour afficher le détail d'un mois ; cliquez (ou
      Entrée) pour l'épingler.
    </p>
  </section>
</template>
