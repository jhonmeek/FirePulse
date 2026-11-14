<script setup lang="ts">
import { computed } from 'vue'
import { USE_MOCKS, exportSeriesUrl, seriesToCsv } from '@/services/api'
import type { AreaQuery, CalendarResponse } from '@/types/api'

/**
 * Export CSV des séries mensuelles de la zone et de la période affichées.
 * API : lien direct vers `/export/?dataset=series` (le backend envoie le fichier).
 * Mocks : même CSV construit côté client à partir de la série chargée.
 */
const props = defineProps<{
  query: AreaQuery
  data: CalendarResponse | null
}>()

const href = computed(() => exportSeriesUrl(props.query))
const fileName = computed(() => {
  const area = props.query.bbox ? 'zone' : (props.query.region ?? 'GA')
  return `firepulse_${area}_${props.query.start ?? 'debut'}_${props.query.end ?? 'fin'}_${
    props.query.filter_static ? 'filtre' : 'brut'
  }.csv`
})

function downloadMock() {
  if (!props.data) return
  const { start, end } = props.query
  const series = props.data.series.filter(
    (p) => (!start || p.month >= start) && (!end || p.month <= end),
  )
  const csv = seriesToCsv(
    series,
    props.data.region.id,
    props.query.filter_static,
    props.data.method?.version ?? '',
  )
  const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }))
  const a = document.createElement('a')
  a.href = url
  a.download = fileName.value
  a.click()
  URL.revokeObjectURL(url)
}

const cls =
  'inline-flex items-center gap-1.5 rounded-md border border-stone-300 bg-white px-3 py-1.5 text-sm hover:bg-stone-100 focus-visible:outline-2 focus-visible:outline-orange-600'
</script>

<template>
  <button
    v-if="USE_MOCKS"
    type="button"
    :class="cls"
    :disabled="!data?.series.length"
    @click="downloadMock"
  >
    Exporter CSV
  </button>
  <a v-else :class="cls" :href="href" :download="fileName">Exporter CSV</a>
</template>
