<script setup lang="ts">
import { computed, defineAsyncComponent, ref } from 'vue'
import { storeToRefs } from 'pinia'
import AnomaliesPanel from '@/components/AnomaliesPanel.vue'
import CalendarHeatmap from '@/components/CalendarHeatmap.vue'
import ControlBar from '@/components/ControlBar.vue'
import MethodologyPanel from '@/components/MethodologyPanel.vue'
import MonthDetail from '@/components/MonthDetail.vue'
import RegimeTimeline from '@/components/RegimeTimeline.vue'
import { useCalendar } from '@/composables/useCalendar'
import { useRegions } from '@/composables/useRegions'
import { USE_MOCKS } from '@/services/api'
import { useFiltersStore } from '@/stores/filters'
import type { YearMonth } from '@/types/api'
import { maskedSummary } from '@/utils/anomalies'
import { historicalRank } from '@/utils/calendar'
import type { ChartView } from '@/utils/chart'

// ECharts (~600 Ko) en chunk séparé : le calendrier s'affiche sans l'attendre.
const ComparisonChart = defineAsyncComponent(() => import('@/components/ComparisonChart.vue'))

const filters = useFiltersStore()
const { yearRange, colorMode, selectedMonth, region, filterStatic, bbox } = storeToRefs(filters)
const { regions } = useRegions()
const { data, filtered, unfiltered, loading, error, reload } = useCalendar()

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
const masked = computed(() => maskedSummary(unfiltered.value, filtered.value, yearRange.value))

const preview = ref<YearMonth | null>(null)
const shownMonth = computed(() => selectedMonth.value ?? preview.value)
const shownPoint = computed(() => series.value.find((p) => p.month === shownMonth.value) ?? null)
const shownRank = computed(() =>
  shownMonth.value ? historicalRank(series.value, shownMonth.value) : null,
)

/** Calendrier : un second clic sur le même mois le désélectionne. */
function toggle(month: YearMonth) {
  selectedMonth.value = selectedMonth.value === month ? null : month
}
/** Graphe et classement : épinglent toujours le mois choisi. */
function pin(month: YearMonth) {
  selectedMonth.value = month
}

const chartView = ref<ChartView>('after')

// ---- onglets (motif ARIA tabs, flèches gauche/droite)
const tabs = [
  { id: 'explore', label: 'Explorer' },
  { id: 'method', label: 'Méthodologie & preuve' },
] as const
type TabId = (typeof tabs)[number]['id']
const tab = ref<TabId>('explore')
function onTabKey(e: KeyboardEvent) {
  if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return
  const i = tabs.findIndex((t) => t.id === tab.value)
  const next = tabs[(i + (e.key === 'ArrowRight' ? 1 : tabs.length - 1)) % tabs.length]!
  tab.value = next.id
  document.getElementById(`tab-${next.id}`)?.focus()
}
</script>

<template>
  <div class="min-h-screen bg-stone-50 font-sans text-stone-900">
    <header class="border-b border-stone-200 bg-white">
      <div class="mx-auto flex max-w-7xl flex-wrap items-baseline justify-between gap-2 px-4 pt-4">
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
      <div
        role="tablist"
        aria-label="Vues"
        class="mx-auto mt-3 flex max-w-7xl gap-1 px-4"
        @keydown="onTabKey"
      >
        <button
          v-for="t in tabs"
          :id="`tab-${t.id}`"
          :key="t.id"
          role="tab"
          type="button"
          :aria-selected="tab === t.id"
          :aria-controls="`panel-${t.id}`"
          :tabindex="tab === t.id ? 0 : -1"
          :class="[
            '-mb-px border-b-2 px-3 py-2 text-sm focus-visible:outline-2 focus-visible:outline-orange-600',
            tab === t.id
              ? 'border-orange-600 font-semibold text-stone-900'
              : 'border-transparent text-stone-600 hover:text-stone-900',
          ]"
          @click="tab = t.id"
        >
          {{ t.label }}
        </button>
      </div>
    </header>

    <main class="mx-auto max-w-7xl space-y-5 px-4 py-5">
      <section aria-label="Filtres" class="rounded-lg border border-stone-200 bg-white p-4">
        <ControlBar :regions="regions" :available-years="availableYears" :masked="masked" />
        <div class="mt-4">
          <RegimeTimeline :year-range="yearRange" />
        </div>
      </section>

      <div v-if="error" role="alert" class="rounded-md bg-red-50 p-3 text-sm text-red-800">
        Impossible de charger les données : {{ error }}
        <button type="button" class="ml-2 underline" @click="reload">Réessayer</button>
      </div>

      <div
        v-show="tab === 'explore'"
        id="panel-explore"
        role="tabpanel"
        aria-labelledby="tab-explore"
        class="space-y-5"
      >
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

            <p v-if="loading && !series.length" class="py-10 text-center text-sm text-stone-600">
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
              @select="toggle"
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

        <template v-if="series.length">
          <section
            aria-labelledby="chart-title"
            class="rounded-lg border border-stone-200 bg-white p-4"
          >
            <h2 id="chart-title" class="mb-3 text-base font-semibold">
              Séries comparées : capteurs bruts et série harmonisée
            </h2>
            <ComparisonChart
              v-model:view="chartView"
              :series="series"
              :year-range="yearRange"
              :selected-month="selectedMonth"
              @select="pin"
            />
          </section>

          <section
            aria-labelledby="anom-title"
            class="rounded-lg border border-stone-200 bg-white p-4"
          >
            <h2 id="anom-title" class="mb-3 text-base font-semibold">
              Anomalies par rapport à la médiane du même mois
            </h2>
            <AnomaliesPanel
              :series="series"
              :year-range="yearRange"
              :selected-month="selectedMonth"
              @select="pin"
            />
          </section>
        </template>
      </div>

      <section
        v-if="tab === 'method'"
        id="panel-method"
        role="tabpanel"
        aria-labelledby="tab-method"
        class="rounded-lg border border-stone-200 bg-white p-4"
      >
        <MethodologyPanel
          :region="bbox ? 'GA' : region"
          :filter-static="filterStatic"
          :custom-area="bbox !== null"
        />
      </section>
    </main>
  </div>
</template>
