<script setup lang="ts">
import { computed } from 'vue'
import type { CalendarPoint } from '@/types/api'
import type { ChartView } from '@/utils/chart'
import {
  COVERAGE_LABELS,
  MONTHS_LONG,
  RAW_SENSOR_LABELS,
  REGIME_LABELS,
  formatAnomaly,
  formatCount,
  isProvisional,
  monthLabel,
  rawEraValue,
} from '@/utils/calendar'

const props = defineProps<{
  point: CalendarPoint | null
  rank: { rank: number; total: number } | null
  /** true = mois épinglé par clic ; false = aperçu au survol. */
  pinned: boolean
  /** true = aucun mois choisi : affichage par défaut du dernier mois disponible. */
  latest?: boolean
  /** Vue Avant : la valeur brute du capteur d'époque passe au premier plan. */
  view: ChartView
}>()

const emit = defineEmits<{ unpin: [] }>()

const p = computed(() => props.point)
const monthName = computed(() => (p.value ? (MONTHS_LONG[+p.value.month.slice(5) - 1] ?? '') : ''))
const deMonth = computed(() =>
  /^[aeiou]/.test(monthName.value) ? `d'${monthName.value}` : `de ${monthName.value}`,
)
const raw = computed(() => (p.value ? rawEraValue(p.value) : null))
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
  <!-- Verre dépoli : panneau clé, collant à côté du calendrier. -->
  <section aria-live="polite" class="glass rounded-2xl p-4 text-sm sm:p-5">
    <template v-if="p">
      <header class="flex items-start justify-between gap-2">
        <div>
          <p class="text-xs uppercase tracking-wide text-stone-600">
            {{ pinned ? 'Mois sélectionné' : latest ? 'Dernier mois disponible' : 'Aperçu' }}
          </p>
          <h2 class="text-lg font-semibold capitalize text-stone-900">
            {{ monthLabel(p.month) }}
            <span
              v-if="isProvisional(p.coverage_status)"
              class="ml-1 align-middle rounded bg-amber-100 px-1.5 py-0.5 text-xs font-normal normal-case text-amber-900"
              >provisoire</span
            >
          </h2>
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
        <template v-if="view === 'before' && raw">
          <p class="mt-3">
            <span class="text-3xl font-semibold tabular-nums text-stone-900">{{
              formatCount(raw.value)
            }}</span>
            <span class="ml-1 text-stone-600"
              >points de feu bruts {{ RAW_SENSOR_LABELS[raw.sensor] }}</span
            >
          </p>
          <p class="text-stone-700">
            Données corrigées :
            <strong class="tabular-nums">{{ formatCount(p.harmonized_value) }}</strong>
          </p>
        </template>
        <p v-else class="mt-3">
          <span class="text-3xl font-semibold tabular-nums text-stone-900">{{
            formatCount(p.harmonized_value)
          }}</span>
          <span class="ml-1 text-stone-600">points de feu détectés</span>
        </p>
        <p v-if="!observed && p.ci_low !== null" class="text-stone-600">
          Estimation recalculée : probablement entre {{ formatCount(p.ci_low) }} et
          {{ formatCount(p.ci_high) }}
        </p>
        <p v-else-if="observed" class="text-stone-600">Compté directement par le satellite</p>
        <p v-else class="text-stone-600">Marge d'erreur non disponible pour cette zone</p>

        <dl class="mt-4 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5">
          <dt class="text-stone-600">Un mois {{ deMonth }} normal</dt>
          <dd class="tabular-nums">
            {{ formatCount(p.baseline_median) }}
            <span v-if="p.baseline_iqr" class="text-stone-600">
              (souvent entre {{ formatCount(p.baseline_iqr[0]) }} et
              {{ formatCount(p.baseline_iqr[1]) }})
            </span>
          </dd>
          <dt class="text-stone-600">Écart à la normale</dt>
          <dd :class="['font-semibold tabular-nums', anomalyTone]">{{ formatAnomaly(p) }}</dd>
          <template v-if="rank">
            <dt class="text-stone-600">Classement</dt>
            <dd>
              {{ rank.rank === 1 ? '1er' : `${rank.rank}e` }} {{ monthName }} le plus actif sur
              {{ rank.total }} (2001–2025)
            </dd>
          </template>
        </dl>
      </template>
      <p v-else class="mt-3 text-stone-600">Aucune donnée exploitable pour ce mois.</p>

      <!-- Détail technique : un clic plus loin. -->
      <details class="mt-4">
        <summary class="cursor-pointer text-stone-700">Détails techniques</summary>
        <dl class="mt-2 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5">
          <dt class="text-stone-600">Satellite</dt>
          <dd>{{ REGIME_LABELS[p.sensor_regime] }}</dd>
          <dt class="text-stone-600">Couverture</dt>
          <dd>{{ COVERAGE_LABELS[p.coverage_status] }}</dd>
          <template v-if="p.harmonized_value !== null">
            <dt class="text-stone-600">Unité</dt>
            <dd>Détections équivalentes VIIRS 375 m</dd>
            <template v-if="!observed && p.ci_low !== null">
              <dt class="text-stone-600">Intervalle 80 %</dt>
              <dd class="tabular-nums">
                {{ formatCount(p.ci_low) }} – {{ formatCount(p.ci_high) }} (intervalle conforme)
              </dd>
            </template>
            <template v-else-if="p.ci_low === null && !observed">
              <dt class="text-stone-600">Intervalle</dt>
              <dd>Intervalle d'incertitude non disponible</dd>
            </template>
          </template>
        </dl>
        <p class="mt-3 font-medium text-stone-700">Détections brutes par capteur</p>
        <table class="mt-1 w-full text-left">
          <tbody>
            <tr v-for="r in rawRows" :key="r.label" class="border-t border-stone-100">
              <th scope="row" class="py-1 font-normal text-stone-600">{{ r.label }}</th>
              <td class="py-1 text-right tabular-nums">
                {{ r.value === null ? 'capteur non actif' : formatCount(r.value) }}
              </td>
            </tr>
          </tbody>
        </table>
        <p v-if="p.uncertainty_note" class="mt-3 text-xs text-stone-600">
          {{ p.uncertainty_note }}
        </p>
      </details>

      <p v-if="!pinned" class="mt-3 text-xs text-stone-600">
        Survolez le calendrier pour voir un autre mois ; cliquez pour le garder affiché.
      </p>
    </template>

    <p v-else class="text-stone-600">
      Survolez ou parcourez le calendrier au clavier pour afficher le détail d'un mois ; cliquez (ou
      Entrée) pour l'épingler.
    </p>
  </section>
</template>
