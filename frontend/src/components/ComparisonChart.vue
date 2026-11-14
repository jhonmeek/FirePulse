<script setup lang="ts">
import { computed } from 'vue'
import VChart from 'vue-echarts'
// Requis en v8 : sans lui, l'élément <x-vue-echarts> est inline et sa hauteur vaut 0.
import 'vue-echarts/style.css'
import { use } from 'echarts/core'
import { LineChart } from 'echarts/charts'
import {
  AriaComponent,
  DataZoomComponent,
  GridComponent,
  LegendComponent,
  MarkLineComponent,
  TooltipComponent,
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import type { CalendarPoint, YearMonth } from '@/types/api'
import { buildComparisonOption, inRange, snppModisRatio, type ChartView } from '@/utils/chart'

// Import modulaire : seuls les modules utilisés entrent dans le bundle.
use([
  LineChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  DataZoomComponent,
  MarkLineComponent,
  AriaComponent,
  CanvasRenderer,
])

const props = defineProps<{
  series: CalendarPoint[]
  yearRange: [number, number]
  selectedMonth: YearMonth | null
}>()

const emit = defineEmits<{ select: [month: YearMonth] }>()

const view = defineModel<ChartView>('view', { default: 'after' })

const points = computed(() => inRange(props.series, props.yearRange))
const option = computed(() => buildComparisonOption(points.value, view.value, props.selectedMonth))

/** Saut instrumental mesuré sur la période de recouvrement 2012–2019 (données affichées). */
const ratio = computed(() => snppModisRatio(props.series, '2012-02', '2019-12'))
const ratioLabel = computed(() =>
  ratio.value === null
    ? null
    : `×${ratio.value.toLocaleString('fr-FR', { maximumFractionDigits: 1 })}`,
)

function onClick(e: { name?: string }) {
  if (e.name && /^\d{4}-\d{2}$/.test(e.name)) emit('select', e.name)
}
</script>

<template>
  <div>
    <div class="mb-2 flex flex-wrap items-center justify-between gap-2">
      <div
        role="radiogroup"
        aria-label="Vue du graphe"
        class="inline-flex rounded-md border border-stone-300 bg-white p-0.5 text-sm"
      >
        <label
          v-for="v in [
            { value: 'before', label: 'Avant harmonisation' },
            { value: 'after', label: 'Après harmonisation' },
          ] as const"
          :key="v.value"
          class="cursor-pointer rounded px-3 py-1 has-[:checked]:bg-stone-800 has-[:checked]:text-white has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-orange-600"
        >
          <input v-model="view" class="sr-only" type="radio" name="chart-view" :value="v.value" />
          {{ v.label }}
        </label>
      </div>
      <p v-if="ratioLabel" class="text-xs text-stone-600">
        VIIRS S-NPP détecte {{ ratioLabel }} plus que MODIS sur 2012–2019 (même zone, mêmes mois).
      </p>
    </div>

    <!-- La hauteur est portée par le parent : le CSS (hors @layer) de vue-echarts impose
         height: 100 % et l'emporte sur les utilitaires Tailwind 4 (dans @layer utilities). -->
    <div class="h-80">
      <VChart :option="option" :update-options="{ notMerge: true }" autoresize @click="onClick" />
    </div>

    <p class="mt-1 text-xs text-stone-500">
      <template v-if="view === 'before'">
        Sans correction, le passage MODIS (1 km) → VIIRS (375 m) en 2012 crée une rupture
        artificielle dans la série.
      </template>
      <template v-else>
        Série harmonisée = MODIS converti à l’échelle VIIRS (2000–2012, loi de puissance log1p ;
        modèle Terra seul avant juillet 2002), puis VIIRS S-NPP observé. Zone grisée : intervalle
        conforme 80 % (absent quand la valeur est observée). Clic sur le graphe = choisir le mois.
      </template>
    </p>
  </div>
</template>
