<script setup lang="ts">
import { computed, useTemplateRef } from 'vue'
import { storeToRefs } from 'pinia'
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
import HarmonizationToggle from '@/components/HarmonizationToggle.vue'
import { useFiltersStore } from '@/stores/filters'
import type { CalendarPoint, YearMonth } from '@/types/api'
import { buildComparisonOption, clampWindow, inRange, snppModisRatio } from '@/utils/chart'
import { monthLabel } from '@/utils/calendar'

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

// Vue et zoom vivent dans le store : ils survivent à la bascule avant/après,
// à la sélection d'un mois et aux changements de zone ou de filtre torchères.
const { harmonizationView: view, chartWindow } = storeToRefs(useFiltersStore())

const points = computed(() => inRange(props.series, props.yearRange))
const months = computed(() => points.value.map((p) => p.month))
/** Fenêtre effective : la fenêtre mémorisée, ramenée dans la plage d'années affichée. */
const activeWindow = computed(() => clampWindow(chartWindow.value, months.value))
const option = computed(() =>
  buildComparisonOption(points.value, view.value, props.selectedMonth, activeWindow.value),
)

/** Saut instrumental mesuré sur la période de recouvrement 2012-2019 (données affichées). */
const ratio = computed(() => snppModisRatio(props.series, '2012-02', '2019-12'))
const ratioLabel = computed(() =>
  ratio.value === null
    ? null
    : `×${ratio.value.toLocaleString('fr-FR', { maximumFractionDigits: 1 })}`,
)

const chart = useTemplateRef<InstanceType<typeof VChart>>('chart')

/** Mémorise la fenêtre choisie au curseur, à la molette ou au pincement. */
function onDataZoom() {
  const dz = (
    chart.value?.getOption() as { dataZoom?: { startValue?: number; endValue?: number }[] }
  )?.dataZoom?.[0]
  if (!dz || dz.startValue === undefined || dz.endValue === undefined) return
  const start = months.value[dz.startValue]
  const end = months.value[dz.endValue]
  if (start && end) chartWindow.value = clampWindow({ start, end }, months.value)
}

function onClick(e: { name?: string }) {
  if (e.name && /^\d{4}-\d{2}$/.test(e.name)) emit('select', e.name)
}
</script>

<template>
  <div>
    <div class="mb-3 flex flex-wrap items-center justify-between gap-3">
      <HarmonizationToggle name="chart-view" />
      <p v-if="ratioLabel" class="text-xs text-stone-600">
        VIIRS S-NPP détecte <strong class="tabular-nums text-stone-900">{{ ratioLabel }}</strong>
        plus que MODIS sur 2012-2019 (même zone, mêmes mois).
      </p>
    </div>

    <!-- La hauteur est portée par le parent : le CSS (hors @layer) de vue-echarts impose
         height: 100 % et l'emporte sur les utilitaires Tailwind 4 (dans @layer utilities). -->
    <div class="h-80">
      <VChart
        ref="chart"
        :option="option"
        :update-options="{ notMerge: true }"
        autoresize
        @click="onClick"
        @datazoom="onDataZoom"
      />
    </div>

    <div class="mt-2 flex flex-wrap items-center justify-between gap-2 text-xs text-stone-600">
      <p aria-live="polite">
        <template v-if="activeWindow">
          Zoom conservé : {{ monthLabel(activeWindow.start) }} - {{ monthLabel(activeWindow.end) }}
        </template>
        <template v-else>Période complète {{ yearRange[0] }}-{{ yearRange[1] }}</template>
      </p>
      <button v-if="activeWindow" type="button" class="btn-ghost" @click="chartWindow = null">
        Réinitialiser le zoom
      </button>
    </div>

    <p class="mt-1 text-xs text-stone-700">
      <template v-if="view === 'before'">
        Sans correction, le changement de satellite en 2012 (MODIS, pixels de 1 km → VIIRS, pixels
        de 375 m) crée une rupture artificielle : la courbe saute alors que les feux, eux, n'ont pas
        changé d'un coup.
      </template>
      <template v-else>
        La courbe « Harmonisé » donne des chiffres comparables d'une année à l'autre. Zone grisée :
        fourchette probable pour les années recalculées (avant 2012). Cliquez sur le graphe pour
        choisir un mois.
      </template>
    </p>
    <details class="mt-1 text-xs text-stone-600">
      <summary class="cursor-pointer text-stone-700">Détails techniques</summary>
      <p class="mt-1">
        Série harmonisée = MODIS converti à l’échelle VIIRS (2000-2012, loi de puissance log1p ;
        modèle Terra seul avant juillet 2002), puis VIIRS S-NPP observé. Zone grisée : intervalle
        conforme 80 % (absent quand la valeur est observée).
      </p>
    </details>
  </div>
</template>
