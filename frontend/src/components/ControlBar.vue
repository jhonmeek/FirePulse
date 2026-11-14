<script setup lang="ts">
import { computed } from 'vue'
import { storeToRefs } from 'pinia'
import { useFiltersStore } from '@/stores/filters'
import type { Region } from '@/types/api'
import type { ColorMode } from '@/utils/calendar'
import type { MaskedSummary } from '@/utils/anomalies'

const props = defineProps<{
  regions: Region[]
  /** Années disponibles dans la série chargée. */
  availableYears: number[]
  /** Détections retirées par le filtre torchères sur la période affichée. */
  masked: MaskedSummary | null
}>()

const maskedLabel = computed(() => {
  const m = props.masked
  if (!m) return null
  const n = m.masked.toLocaleString('fr-FR')
  const share = (100 * m.share).toLocaleString('fr-FR', { maximumFractionDigits: 1 })
  return filterStatic.value
    ? `${n} détections masquées (${share} % du brut)`
    : `${n} détections de sources statiques incluses (${share} %)`
})

const filters = useFiltersStore()
const { region, filterStatic, colorMode, yearRange } = storeToRefs(filters)

const country = computed(() => props.regions.filter((r) => r.region_type === 'country'))
const provinces = computed(() => props.regions.filter((r) => r.region_type === 'province'))

function onRegion(e: Event) {
  filters.selectRegion((e.target as HTMLSelectElement).value)
}
function onYear(which: 0 | 1, e: Event) {
  const v = Number((e.target as HTMLSelectElement).value)
  const [from, to] = yearRange.value
  if (which === 0) filters.setYearRange(v, Math.max(v, to))
  else filters.setYearRange(Math.min(from, v), v)
}

const modes: { value: ColorMode; label: string }[] = [
  { value: 'value', label: 'Intensité' },
  { value: 'anomaly', label: 'Anomalie' },
]
</script>

<template>
  <form class="flex flex-wrap items-end gap-x-6 gap-y-3" @submit.prevent>
    <label class="flex flex-col gap-1 text-sm">
      <span class="font-medium text-stone-700">Zone</span>
      <select
        class="rounded-md border border-stone-300 bg-white px-2 py-1.5 text-stone-900 focus-visible:outline-2 focus-visible:outline-orange-600"
        :value="region"
        @change="onRegion"
      >
        <option v-if="!regions.length" value="GA">Gabon</option>
        <option v-for="r in country" :key="r.code" :value="r.code">{{ r.name }}</option>
        <optgroup v-if="provinces.length" label="Provinces">
          <option v-for="r in provinces" :key="r.code" :value="r.code">{{ r.name }}</option>
        </optgroup>
      </select>
    </label>

    <fieldset class="flex flex-col gap-1 text-sm">
      <legend class="font-medium text-stone-700">Années</legend>
      <div class="flex items-center gap-2">
        <select
          aria-label="Année de début"
          class="rounded-md border border-stone-300 bg-white px-2 py-1.5 focus-visible:outline-2 focus-visible:outline-orange-600"
          :value="yearRange[0]"
          @change="onYear(0, $event)"
        >
          <option v-for="y in availableYears" :key="y" :value="y">{{ y }}</option>
        </select>
        <span aria-hidden="true">→</span>
        <select
          aria-label="Année de fin"
          class="rounded-md border border-stone-300 bg-white px-2 py-1.5 focus-visible:outline-2 focus-visible:outline-orange-600"
          :value="yearRange[1]"
          @change="onYear(1, $event)"
        >
          <option v-for="y in availableYears" :key="y" :value="y">{{ y }}</option>
        </select>
      </div>
    </fieldset>

    <fieldset class="flex flex-col gap-1 text-sm">
      <legend class="font-medium text-stone-700">Couleur du calendrier</legend>
      <div class="inline-flex rounded-md border border-stone-300 bg-white p-0.5">
        <label
          v-for="m in modes"
          :key="m.value"
          class="cursor-pointer rounded px-3 py-1 has-[:checked]:bg-stone-800 has-[:checked]:text-white has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-orange-600"
        >
          <input
            v-model="colorMode"
            class="sr-only"
            type="radio"
            name="color-mode"
            :value="m.value"
          />
          {{ m.label }}
        </label>
      </div>
    </fieldset>

    <div class="flex flex-col gap-0.5 pb-0.5 text-sm">
      <label class="flex items-center gap-2">
        <input
          v-model="filterStatic"
          type="checkbox"
          class="size-4 accent-orange-700"
          aria-describedby="filter-static-help filter-static-count"
        />
        <span class="font-medium text-stone-800">Exclure torchères / sources statiques</span>
      </label>
      <p
        id="filter-static-count"
        class="pl-6 text-xs tabular-nums text-stone-600"
        aria-live="polite"
      >
        {{ maskedLabel ?? '' }}
      </p>
    </div>
    <p id="filter-static-help" class="sr-only">
      Activé : feux de végétation uniquement (détections de type 0 hors cellules industrielles
      persistantes). Désactivé : toutes les anomalies thermiques.
    </p>
  </form>
</template>
