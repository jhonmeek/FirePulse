<script setup lang="ts">
import { computed, defineAsyncComponent, ref } from 'vue'
import { storeToRefs } from 'pinia'
import AnomaliesPanel from '@/components/AnomaliesPanel.vue'
import CalendarHeatmap from '@/components/CalendarHeatmap.vue'
import ControlBar from '@/components/ControlBar.vue'
import ExportButton from '@/components/ExportButton.vue'
import HarmonizationToggle from '@/components/HarmonizationToggle.vue'
import MethodologyPanel from '@/components/MethodologyPanel.vue'
import MonthDetail from '@/components/MonthDetail.vue'
import RegimeTimeline from '@/components/RegimeTimeline.vue'
import SummaryBanner from '@/components/SummaryBanner.vue'
import { useCalendar } from '@/composables/useCalendar'
import { useRegions } from '@/composables/useRegions'
import { DEMO_MODE, USE_MOCKS, servedFromFallback } from '@/services/api'
import { useFiltersStore } from '@/stores/filters'
import type { YearMonth } from '@/types/api'
import { maskedSummary } from '@/utils/anomalies'
import { historicalRank } from '@/utils/calendar'
import { snppModisRatio } from '@/utils/chart'
import { lastDataMonth } from '@/utils/summary'

// ECharts (~600 Ko) en chunk séparé : le calendrier s'affiche sans l'attendre.
const ComparisonChart = defineAsyncComponent(() => import('@/components/ComparisonChart.vue'))
// MapLibre (~800 Ko) idem : chargé quand la section carte est rendue.
const MapExplorer = defineAsyncComponent(() => import('@/components/MapExplorer.vue'))

const filters = useFiltersStore()
const {
  yearRange,
  colorMode,
  selectedMonth,
  region,
  filterStatic,
  bbox,
  query,
  harmonizationView,
} = storeToRefs(filters)
const { regions } = useRegions()
const { data, filtered, unfiltered, loading, error, reload } = useCalendar()

const series = computed(() => data.value?.series ?? [])
const availableYears = computed(() => {
  const years = [...new Set(series.value.map((p) => +p.month.slice(0, 4)))]
  return years.length ? years : Array.from({ length: 25 }, (_, i) => 2001 + i)
})
const regionName = computed(() => {
  if (bbox.value) {
    const [w, s, e, n] = bbox.value.map((v) => v.toLocaleString('fr-FR'))
    return `zone dessinée (lon ${w} → ${e}, lat ${s} → ${n})`
  }
  return (
    regions.value.find((r) => r.code === region.value)?.name ??
    data.value?.region.name ??
    region.value
  )
})
const masked = computed(() => maskedSummary(unfiltered.value, filtered.value, yearRange.value))

/** Saut instrumental 2012 arrondi (« environ 4 fois »), même fenêtre que le graphe. */
const jumpFactor = computed(() => {
  const r = snppModisRatio(series.value, '2012-02', '2019-12')
  return r && r >= 1.5 ? Math.round(r) : null
})

const preview = ref<YearMonth | null>(null)
/** Par défaut, la colonne de droite montre le dernier mois disponible de la plage affichée. */
const latestMonth = computed(() => lastDataMonth(series.value, yearRange.value[1]))
const shownMonth = computed(() => selectedMonth.value ?? preview.value ?? latestMonth.value)
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

// ---- onglets (motif ARIA tabs, flèches gauche/droite)
const tabs = [
  { id: 'explore', label: 'Explorer' },
  { id: 'method', label: 'Méthodologie & évaluation' },
] as const
type TabId = (typeof tabs)[number]['id']
const tab = ref<TabId>('explore')
/** « Comment c'est calculé ? » : ouvre l'onglet Méthodologie et y place le focus. */
function openMethod() {
  tab.value = 'method'
  document.getElementById('tab-method')?.focus()
  window.scrollTo({ top: 0 })
}
function onTabKey(e: KeyboardEvent) {
  if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return
  const i = tabs.findIndex((t) => t.id === tab.value)
  const next = tabs[(i + (e.key === 'ArrowRight' ? 1 : tabs.length - 1)) % tabs.length]!
  tab.value = next.id
  document.getElementById(`tab-${next.id}`)?.focus()
}
</script>

<template>
  <div class="min-h-dvh font-sans text-stone-900">
    <a
      href="#main"
      class="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:rounded-lg focus:bg-white focus:px-3 focus:py-2 focus:shadow"
      >Aller au contenu</a
    >
    <!-- En-tête collant en verre dépoli : reste lisible au-dessus des graphes en défilement. -->
    <header class="glass sticky top-0 z-30 border-x-0 border-t-0">
      <div
        class="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-x-6 gap-y-2 px-4 pt-3"
      >
        <div class="flex items-center gap-3">
          <span
            class="grid size-9 place-items-center rounded-xl bg-gradient-to-br from-orange-500 to-red-700 text-white shadow-sm"
            aria-hidden="true"
          >
            <svg
              viewBox="0 0 24 24"
              class="size-5"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
              stroke-linecap="round"
              stroke-linejoin="round"
            >
              <path
                d="M12 3c1.5 3 4.5 4.6 4.5 8.6A4.5 4.5 0 0 1 12 16a4.5 4.5 0 0 1-4.5-4.4c0-2.2 1.3-3.4 2.3-4.6.3 1.7 1.2 2.6 2.2 2.6 0-2.5-.6-4.6 0-6.6Z"
              />
              <path d="M5 21h14" />
            </svg>
          </span>
          <div>
            <h1 class="text-lg font-semibold leading-tight tracking-tight">FirePulse</h1>
            <p
              class="text-xs text-stone-700"
              title="Indicateur harmonisé d'activité des points chauds - échelle VIIRS 375 m (MODIS 2000-2012 reconstitué)"
            >
              Les feux vus par satellite, mois par mois depuis 2001
            </p>
          </div>
        </div>
        <!-- Provenance des données : visible pendant la démo, annoncée aux lecteurs d'écran. -->
        <span
          v-if="DEMO_MODE"
          role="status"
          class="rounded-full bg-sky-100 px-2.5 py-0.5 text-xs font-medium text-sky-900"
          title="Build de démonstration autonome : données FIRMS du Gabon embarquées, aucun serveur requis"
          >Démo hors ligne · Gabon</span
        >
        <span
          v-else-if="USE_MOCKS"
          class="rounded-full bg-amber-100 px-2.5 py-0.5 text-xs font-medium text-amber-900"
          title="Données générées localement depuis les CSV FIRMS (src/mocks)"
          >Mode mocks</span
        >
        <span
          v-else-if="servedFromFallback"
          role="status"
          class="rounded-full bg-amber-100 px-2.5 py-0.5 text-xs font-medium text-amber-900"
          title="Base de données indisponible : l'API sert l'instantané de secours vérifié (SHA-256)"
          >Données de secours</span
        >
      </div>
      <div
        role="tablist"
        aria-label="Vues"
        class="mx-auto mt-2 flex max-w-7xl gap-1 px-4"
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
            '-mb-px min-h-10 cursor-pointer border-b-2 px-3 py-2 text-sm transition-colors duration-150 focus-visible:outline-2',
            tab === t.id
              ? 'border-orange-600 font-semibold text-stone-900'
              : 'border-transparent text-stone-700 hover:text-stone-900',
          ]"
          @click="tab = t.id"
        >
          {{ t.label }}
        </button>
      </div>
    </header>

    <main id="main" tabindex="-1" class="mx-auto max-w-7xl space-y-5 px-4 py-5 outline-none">
      <SummaryBanner
        v-if="tab === 'explore' && series.length"
        :series="series"
        :year-range="yearRange"
        :region-name="regionName"
      />

      <section aria-label="Filtres" class="card">
        <ControlBar
          :regions="regions"
          :available-years="availableYears"
          :masked="masked"
          :hide-calendar-controls="tab !== 'explore'"
        />
        <!-- Détail technique replié : utile aux curieux, pas nécessaire pour lire la page. -->
        <details class="group mt-4">
          <summary
            class="cursor-pointer text-sm text-stone-700 hover:text-stone-900 focus-visible:outline-2 focus-visible:outline-orange-600"
          >
            Quels satellites ont observé ?
            <span class="text-stone-600">MODIS jusqu'en 2012, VIIRS ensuite</span>
          </summary>
          <div class="mt-3">
            <RegimeTimeline :year-range="yearRange" />
          </div>
        </details>
      </section>

      <div
        v-if="error"
        role="alert"
        class="rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-800"
      >
        Impossible de charger les données : {{ error }}
        <button type="button" class="btn-ghost ml-2 underline" @click="reload">Réessayer</button>
      </div>

      <div
        v-show="tab === 'explore'"
        id="panel-explore"
        role="tabpanel"
        aria-labelledby="tab-explore"
        class="space-y-5"
      >
        <div class="grid gap-5 lg:grid-cols-[minmax(0,1fr)_22rem]">
          <section aria-labelledby="calendar-title" class="card">
            <div class="mb-3 flex flex-wrap items-baseline justify-between gap-2">
              <h2 id="calendar-title" class="card-title">
                Points de feu chaque mois - {{ regionName }}
              </h2>
              <div class="flex items-center gap-3">
                <button
                  type="button"
                  class="btn-ghost text-xs underline"
                  :title="
                    data?.method ? `Méthode ${data.method.name} (${data.method.version})` : undefined
                  "
                  @click="openMethod"
                >
                  Comment c'est calculé ?
                </button>
                <ExportButton :query="query" :data="data" />
              </div>
            </div>
            <!-- Même bascule que le graphe (état partagé) : basculer ici bascule aussi le graphe. -->
            <div class="mb-3 space-y-1.5">
              <HarmonizationToggle name="calendar-view" />
              <p class="max-w-prose text-xs text-stone-700">
                <template v-if="harmonizationView === 'before'">
                  Chaque mois tel que vu par le satellite de l'époque. En 2012, un satellite plus
                  précis (VIIRS) a remplacé l'ancien (MODIS)<template v-if="jumpFactor">
                    : il repère environ {{ jumpFactor }} fois plus de points de feu</template
                  >. La hausse brutale de 2012 vient de ce changement d'instrument, pas des feux.
                </template>
                <template v-else>
                  Les années avant 2012 sont recalculées comme si le satellite actuel les avait
                  observées : toutes les années se comparent entre elles.
                </template>
              </p>
            </div>
            <p
              v-if="bbox"
              class="mb-3 rounded-lg border border-amber-200 bg-amber-50 p-2 text-xs text-amber-900"
              title="Série agrégée depuis la grille 0,25° avec la courbe nationale ; pas d'intervalle d'incertitude propre à la zone."
            >
              Zone dessinée : estimation à partir de carrés d'environ 28 km de côté ; pas de marge
              d'erreur propre à cette zone.
            </p>

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
              :view="harmonizationView"
              @select="toggle"
              @preview="preview = $event"
            />
          </section>

          <!-- Décalé sous l'en-tête collant (≈ 7 rem). -->
          <aside class="lg:sticky lg:top-28 lg:self-start">
            <MonthDetail
              :point="shownPoint"
              :rank="shownRank"
              :pinned="selectedMonth !== null && shownMonth === selectedMonth"
              :latest="selectedMonth === null && preview === null"
              :view="harmonizationView"
              @unpin="selectedMonth = null"
            />
          </aside>
        </div>

        <section aria-labelledby="map-title" class="card">
          <h2 id="map-title" class="card-title mb-3">Carte : où sont repérés les points de feu</h2>
          <MapExplorer />
        </section>

        <template v-if="series.length">
          <section aria-labelledby="chart-title" class="card">
            <h2 id="chart-title" class="card-title mb-3">
              Évolution mois par mois : données brutes et corrigées
            </h2>
            <ComparisonChart
              :series="series"
              :year-range="yearRange"
              :selected-month="selectedMonth"
              @select="pin"
            />
          </section>

          <section aria-labelledby="anom-title" class="card">
            <h2 id="anom-title" class="card-title mb-3">
              Mois inhabituels : écart à la normale du même mois
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
        class="card"
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
