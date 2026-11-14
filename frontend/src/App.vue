<script setup lang="ts">
import { computed, ref } from 'vue'
import { storeToRefs } from 'pinia'
import CalendarHeatmap from '@/components/CalendarHeatmap.vue'
import ControlBar from '@/components/ControlBar.vue'
import MonthDetail from '@/components/MonthDetail.vue'
import RegimeTimeline from '@/components/RegimeTimeline.vue'
import { useCalendar } from '@/composables/useCalendar'
import { useRegions } from '@/composables/useRegions'
import { USE_MOCKS } from '@/services/api'
import { useFiltersStore } from '@/stores/filters'
import type { YearMonth } from '@/types/api'
import { historicalRank } from '@/utils/calendar'

const filters = useFiltersStore()
const { yearRange, colorMode, selectedMonth, region } = storeToRefs(filters)
const { regions } = useRegions()
const { data, loading, error, reload } = useCalendar()

const series = computed(() => data.value?.series ?? [])
const availableYears = computed(() => {
  const years = [...new Set(series.value.map((p) => +p.month.slice(0, 4)))]
  return years.length ? years : Array.from({ length: 25 }, (_, i) => 2001 + i)
})
const regionName = computed(
  () =>
    regions.value.find((r) => r.code === region.value)?.name ??
    data.value?.region.name ??
    region.value,
)

const preview = ref<YearMonth | null>(null)
const shownMonth = computed(() => selectedMonth.value ?? preview.value)
const shownPoint = computed(() => series.value.find((p) => p.month === shownMonth.value) ?? null)
const shownRank = computed(() =>
  shownMonth.value ? historicalRank(series.value, shownMonth.value) : null,
)

function select(month: YearMonth) {
  selectedMonth.value = selectedMonth.value === month ? null : month
}
</script>

<template>
  <div class="min-h-screen bg-stone-50 font-sans text-stone-900">
    <header class="border-b border-stone-200 bg-white">
      <div class="mx-auto flex max-w-7xl flex-wrap items-baseline justify-between gap-2 px-4 py-4">
        <div>
          <h1 class="text-xl font-semibold">FirePulse</h1>
          <p class="text-sm text-stone-600">
            Indicateur harmonisé d'activité des points chauds — échelle VIIRS 375 m (MODIS 2000–2012
            reconstitué)
          </p>
        </div>
        <span
          v-if="USE_MOCKS"
          class="rounded bg-amber-100 px-2 py-0.5 text-xs text-amber-900"
          title="Données générées localement depuis les CSV FIRMS (src/mocks)"
          >Mode mocks</span
        >
      </div>
    </header>

    <main class="mx-auto max-w-7xl space-y-5 px-4 py-5">
      <section aria-label="Filtres" class="rounded-lg border border-stone-200 bg-white p-4">
        <ControlBar :regions="regions" :available-years="availableYears" />
        <div class="mt-4">
          <RegimeTimeline :year-range="yearRange" />
        </div>
      </section>

      <div class="grid gap-5 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <section
          aria-labelledby="calendar-title"
          class="rounded-lg border border-stone-200 bg-white p-4"
        >
          <div class="mb-3 flex flex-wrap items-baseline justify-between gap-2">
            <h2 id="calendar-title" class="text-base font-semibold">
              Calendrier d'activité — {{ regionName }}
            </h2>
            <p v-if="data?.method" class="text-xs text-stone-500">
              Méthode {{ data.method.name }} ({{ data.method.version }})
            </p>
          </div>

          <div v-if="error" role="alert" class="rounded-md bg-red-50 p-3 text-sm text-red-800">
            Impossible de charger les données : {{ error }}
            <button type="button" class="ml-2 underline" @click="reload">Réessayer</button>
          </div>
          <p v-else-if="loading && !series.length" class="py-10 text-center text-sm text-stone-600">
            Chargement…
          </p>
          <p v-else-if="!series.length" class="py-10 text-center text-sm text-stone-600">
            Aucune série disponible pour cette zone{{
              USE_MOCKS ? ' en mode mocks (seul le Gabon entier est fourni)' : ''
            }}.
          </p>
          <CalendarHeatmap
            v-else
            :class="{ 'opacity-60 transition-opacity': loading }"
            :aria-busy="loading"
            :series="series"
            :year-range="yearRange"
            :color-mode="colorMode"
            :selected-month="selectedMonth"
            @select="select"
            @preview="preview = $event"
          />
        </section>

        <aside class="lg:sticky lg:top-4 lg:self-start">
          <MonthDetail
            :point="shownPoint"
            :rank="shownRank"
            :pinned="selectedMonth !== null && shownMonth === selectedMonth"
            @unpin="selectedMonth = null"
          />
        </aside>
      </div>
    </main>
  </div>
</template>
