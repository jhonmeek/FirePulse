<script setup lang="ts">
import { computed, ref, shallowRef, watch } from 'vue'
import { fetchMethodology } from '@/services/api'
import type { MethodologyResponse } from '@/types/api'
import { benchmarkRows, conformalFactor, maeGain } from '@/utils/methodology'
import { formatCount } from '@/utils/calendar'

const props = defineProps<{
  /** Région calibrée (une zone libre utilise la calibration nationale GA). */
  region: string
  filterStatic: boolean
  customArea: boolean
}>()

const data = shallowRef<MethodologyResponse | null>(null)
const error = ref<string | null>(null)
let requestId = 0

watch(
  () => [props.region, props.filterStatic] as const,
  async ([region, filterStatic]) => {
    const id = ++requestId
    error.value = null
    try {
      const res = await fetchMethodology(region, filterStatic)
      if (id === requestId) data.value = res
    } catch (e) {
      if (id === requestId) error.value = e instanceof Error ? e.message : String(e)
    }
  },
  { immediate: true },
)

const run = computed(() => data.value?.active_run ?? null)
const rows = computed(() =>
  run.value?.metrics.models_out_of_sample
    ? benchmarkRows(run.value.metrics.models_out_of_sample, run.value.params, run.value.method_name)
    : [],
)
const maxMae = computed(() => Math.max(1, ...rows.value.map((r) => r.mae)))
const gainNaive = computed(() => maeGain(rows.value, 'naive'))
const gainRatio = computed(() => maeGain(rows.value, 'global_ratio'))
const selected = computed(() => rows.value.find((r) => r.selected) ?? null)

const pct = (v: number) => `${Math.round(v * 100)} %`
const nf = (v: number, d = 2) => v.toLocaleString('fr-FR', { maximumFractionDigits: d })
const month = (iso: string) => iso.slice(0, 7)
</script>

<template>
  <div class="space-y-6 text-sm">
    <p v-if="error" role="alert" class="rounded-md bg-red-50 p-3 text-red-800">
      Impossible de charger la méthodologie : {{ error }}
    </p>
    <p v-else-if="!data" class="text-stone-600">Chargement…</p>
    <p v-else-if="!run" class="text-stone-600">Aucune calibration active pour cette région.</p>

    <template v-else>
      <p v-if="customArea" class="rounded-md bg-amber-50 p-3 text-amber-900">
        Zone dessinée : la courbe nationale (Gabon) est appliquée ; pas d’intervalle d’incertitude
        propre à la zone.
      </p>

      <section aria-labelledby="proof-title">
        <h3
          id="proof-title"
          class="flex flex-wrap items-center gap-2 text-base font-semibold text-stone-900"
        >
          Évaluation hors échantillon
          <span class="rounded bg-amber-100 px-1.5 py-0.5 text-xs font-medium text-amber-900"
            >protocole en revue scientifique (M1)</span
          >
        </h3>
        <p class="mt-1 text-stone-600">
          Paramètres ajustés sur {{ month(run.train_window[0]) }} →
          {{ month(run.train_window[1]) }}
          <template v-if="run.metrics.train_months">({{ run.metrics.train_months }} mois)</template
          >, erreurs mesurées sur {{ month(run.test_window[0]) }} → {{ month(run.test_window[1]) }}
          <template v-if="run.metrics.test_months"
            >({{ run.metrics.test_months }} mois non utilisés pour l’ajustement)</template
          >. Cible : comptages VIIRS S-NPP observés ; entrée : MODIS du même mois.
        </p>

        <p
          v-if="selected && gainNaive !== null"
          class="mt-3 rounded-md bg-stone-100 p-3 text-stone-800"
        >
          Sur la période test, le modèle retenu (<strong>{{ selected.label }}</strong
          >) présente une erreur moyenne inférieure de <strong>{{ pct(gainNaive) }}</strong> à
          l’absence de correction<template v-if="gainRatio !== null">
            et de <strong>{{ pct(gainRatio) }}</strong> au ratio global</template
          >, avec R² = <strong>{{ nf(selected.r2, 3) }}</strong
          >.
        </p>

        <div class="mt-3 rounded-md border border-amber-200 bg-amber-50 p-3 text-amber-950">
          <p class="font-medium">Points en cours de revue avant validation</p>
          <ul class="mt-1 list-disc space-y-1 pl-5">
            <li>
              L’intervalle 80 % est calibré sur les résidus de la période test : sa couverture n’est
              pas évaluée de façon indépendante.
            </li>
            <li>
              Le choix du modèle retenu s’appuie sur un benchmark réalisé sur la même fenêtre test :
              son score peut être légèrement optimiste.
            </li>
            <li>
              Le masque torchères est construit avec les détections de toute la période, test
              comprise.
            </li>
          </ul>
        </div>

        <p v-if="run.metrics.note" class="mt-3 text-stone-600">{{ run.metrics.note }}</p>

        <div v-if="rows.length" class="mt-3 overflow-x-auto">
          <table class="w-full min-w-[36rem] text-left">
            <caption class="sr-only">
              Erreurs hors échantillon par modèle (détections par mois)
            </caption>
            <thead class="border-b border-stone-300 text-xs uppercase tracking-wide text-stone-500">
              <tr>
                <th scope="col" class="py-2 pr-3">Modèle</th>
                <th scope="col" class="py-2 pr-3">MAE</th>
                <th scope="col" class="py-2 pr-3 text-right">RMSE</th>
                <th scope="col" class="py-2 pr-3 text-right">Biais</th>
                <th scope="col" class="py-2 text-right">R²</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="r in rows"
                :key="r.key"
                :class="['border-b border-stone-100', r.selected ? 'bg-orange-50' : '']"
              >
                <th scope="row" class="py-2 pr-3 font-normal">
                  <span :class="r.selected ? 'font-semibold' : ''">{{ r.label }}</span>
                  <span
                    v-if="r.selected"
                    class="ml-1 rounded bg-orange-200 px-1.5 text-xs text-orange-900"
                    >retenu</span
                  >
                  <span class="block font-mono text-xs text-stone-500">{{ r.formula }}</span>
                </th>
                <td class="py-2 pr-3">
                  <span class="flex items-center gap-2">
                    <span
                      class="block h-2 rounded-sm"
                      :class="r.selected ? 'bg-orange-600' : 'bg-stone-400'"
                      :style="{ width: `${(6 * r.mae) / maxMae}rem` }"
                      aria-hidden="true"
                    />
                    <span class="tabular-nums">{{ nf(r.mae, 1) }}</span>
                  </span>
                </td>
                <td class="py-2 pr-3 text-right tabular-nums">{{ nf(r.rmse, 1) }}</td>
                <td class="py-2 pr-3 text-right tabular-nums">{{ nf(r.bias, 1) }}</td>
                <td class="py-2 text-right tabular-nums">{{ nf(r.r2, 3) }}</td>
              </tr>
            </tbody>
          </table>
          <p class="mt-1 text-xs text-stone-500">
            MAE / RMSE en détections par mois sur la période test ; biais &gt; 0 = surestimation.
          </p>
        </div>
      </section>

      <section aria-labelledby="params-title" class="grid gap-4 md:grid-cols-3">
        <h3 id="params-title" class="sr-only">Paramètres et traitements</h3>
        <div class="rounded-md border border-stone-200 p-3">
          <p class="text-xs uppercase tracking-wide text-stone-500">Incertitude (conforme 80 %)</p>
          <p class="mt-1">
            Facteur ×{{ nf(conformalFactor(run.params.conformal_q80_log)) }} (MODIS Terra + Aqua),
            ×{{ nf(conformalFactor(run.params.conformal_q80_terra_log)) }} (Terra seul) autour de la
            valeur reconstituée.
          </p>
        </div>
        <div class="rounded-md border border-stone-200 p-3">
          <p class="text-xs uppercase tracking-wide text-stone-500">Pont NOAA-20</p>
          <p class="mt-1">
            NOAA-20 / S-NPP = {{ nf(run.params.noaa20_to_snpp_ratio, 3) }} sur 2019–2025 :
            continuité après l’arrêt de S-NPP (2 nov. 2026).
          </p>
        </div>
        <div class="rounded-md border border-stone-200 p-3">
          <p class="text-xs uppercase tracking-wide text-stone-500">Masque torchères</p>
          <p class="mt-1">
            {{ formatCount(data!.static_mask_summary.masked_cells_count) }} cellules de
            {{ nf(data!.static_mask_summary.grid_deg) }}° exclues (sources industrielles
            persistantes), en plus des détections de type ≠ 0.
          </p>
        </div>
      </section>

      <section aria-labelledby="limits-title">
        <h3 id="limits-title" class="text-base font-semibold text-stone-900">
          Limites documentées
        </h3>
        <ul class="mt-2 list-disc space-y-1 pl-5 text-stone-700" lang="en">
          <li v-for="l in data!.limitations" :key="l">{{ l }}</li>
        </ul>
      </section>
    </template>
  </div>
</template>
