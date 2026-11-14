<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { fetchCalendar, USE_MOCKS } from '@/services/api'
import { useFiltersStore } from '@/stores/filters'
import type { CalendarResponse } from '@/types/api'

// Coquille H0–H3 : vérifie la chaîne store → service → mocks/API.
// Le calendrier, le graphique et la carte arrivent en H3–H12.
const filters = useFiltersStore()
const calendar = ref<CalendarResponse | null>(null)
const error = ref<string | null>(null)

let requestId = 0

async function load() {
  const id = ++requestId
  error.value = null
  try {
    const data = await fetchCalendar(filters.query)
    // Ignore une réponse arrivée après une requête plus récente (toggles rapides).
    if (id === requestId) calendar.value = data
  } catch (e) {
    if (id === requestId) error.value = e instanceof Error ? e.message : String(e)
  }
}

onMounted(load)
watch(() => filters.query, load, { deep: true })
</script>

<template>
  <main class="mx-auto max-w-3xl p-6 font-sans text-slate-900">
    <h1 class="text-2xl font-semibold">FirePulse — Gabon</h1>
    <p class="mt-1 text-sm text-slate-600">
      Indicateur harmonisé d'activité des points chauds (échelle VIIRS 375 m)
    </p>

    <label class="mt-6 flex items-center gap-2 text-sm">
      <input v-model="filters.filterStatic" type="checkbox" />
      Exclure torchères / sources statiques
    </label>

    <p v-if="error" role="alert" class="mt-4 text-red-700">{{ error }}</p>
    <dl v-else-if="calendar" class="mt-4 grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
      <dt class="text-slate-600">Méthode</dt>
      <dd>{{ calendar.method ? `${calendar.method.name} (${calendar.method.version})` : '—' }}</dd>
      <dt class="text-slate-600">Période</dt>
      <dd>{{ calendar.period.start ?? '—' }} → {{ calendar.period.end ?? '—' }}</dd>
      <dt class="text-slate-600">Source</dt>
      <dd>{{ USE_MOCKS ? 'mocks locaux (src/mocks)' : 'API Django /api/v1' }}</dd>
      <dt class="text-slate-600">Mois chargés</dt>
      <dd>{{ calendar.series.length }}</dd>
    </dl>
    <p v-else class="mt-4 text-sm text-slate-600">Chargement…</p>
  </main>
</template>
