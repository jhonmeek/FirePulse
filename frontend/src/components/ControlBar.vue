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
  /** Réglage de couleur du calendrier : masqué sur l'onglet Méthodologie (sans effet). */
  hideCalendarControls?: boolean
}>()

/**
 * Libellé du compteur. Définition explicite (revue M1, PR #9) : ce n'est pas le nombre de
 * détections situées dans les cellules statiques, mais l'écart entre les séries `/calendar/`
 * sans et avec filtre - type ≠ 0 OU cellule statique 0.05°, dans la zone, sur la période.
 */
const maskedLabel = computed(() => {
  const m = props.masked
  if (!m) return null
  const n = m.masked.toLocaleString('fr-FR')
  const share = (100 * m.share).toLocaleString('fr-FR', { maximumFractionDigits: 1 })
  const [from, to] = yearRange.value
  const period = from === to ? `${from}` : `${from}–${to}`
  return filterStatic.value
    ? `${n} détections retirées (${share} % du total, ${period})`
    : `${n} détections que le filtre retirerait (${share} % du total, ${period})`
})

const filters = useFiltersStore()
const { region, bbox, filterStatic, colorMode, yearRange, harmonizationView } = storeToRefs(filters)

/**
 * Vue Avant (brut) : l'anomalie est calculée sur la série harmonisée, donc indisponible.
 * La préférence `colorMode` est conservée et réappliquée au retour en vue Après.
 */
const rawView = computed(() => harmonizationView.value === 'before')
const effectiveMode = computed<ColorMode>(() => (rawView.value ? 'value' : colorMode.value))

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
  { value: 'value', label: 'Nombre de points de feu' },
  { value: 'anomaly', label: 'Écart à la normale' },
]
</script>

<template>
  <form class="flex flex-wrap items-end gap-x-6 gap-y-3" @submit.prevent>
    <label class="flex flex-col gap-1 text-sm">
      <span class="font-medium text-stone-700">Zone</span>
      <select class="field" :value="bbox ? 'CUSTOM' : region" @change="onRegion">
        <option v-if="bbox" value="CUSTOM" disabled>Zone dessinée</option>
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
          class="field"
          :value="yearRange[0]"
          @change="onYear(0, $event)"
        >
          <option v-for="y in availableYears" :key="y" :value="y">{{ y }}</option>
        </select>
        <span aria-hidden="true">→</span>
        <select
          aria-label="Année de fin"
          class="field"
          :value="yearRange[1]"
          @change="onYear(1, $event)"
        >
          <option v-for="y in availableYears" :key="y" :value="y">{{ y }}</option>
        </select>
      </div>
    </fieldset>

    <fieldset v-if="!hideCalendarControls" class="flex flex-col gap-1 text-sm">
      <legend class="font-medium text-stone-700">Colorer le calendrier selon</legend>
      <div class="segmented">
        <label
          v-for="m in modes"
          :key="m.value"
          class="segmented-item"
          :title="
            rawView && m.value === 'anomaly'
              ? 'Indisponible sur les données brutes : l’écart à la normale se calcule sur les données corrigées'
              : undefined
          "
        >
          <input
            class="sr-only"
            type="radio"
            name="color-mode"
            :value="m.value"
            :checked="effectiveMode === m.value"
            :disabled="rawView && m.value === 'anomaly'"
            @change="colorMode = m.value"
          />
          {{ m.label }}
        </label>
      </div>
      <p v-if="rawView" class="text-xs text-stone-600">
        Écart à la normale : données corrigées uniquement
      </p>
    </fieldset>

    <div class="flex flex-col gap-0.5 pb-0.5 text-sm">
      <label class="flex items-center gap-2">
        <input
          v-model="filterStatic"
          type="checkbox"
          class="size-4 accent-orange-700"
          aria-describedby="filter-static-help filter-static-count"
        />
        <span class="font-medium text-stone-800">Exclure les sources industrielles (torchères)</span>
      </label>
      <p
        id="filter-static-count"
        class="pl-6 text-xs tabular-nums text-stone-600"
        aria-live="polite"
      >
        {{ maskedLabel ?? '' }}
      </p>
      <p v-if="maskedLabel" id="filter-static-help" class="pl-6 text-xs text-stone-500">
        Chaleur permanente qui n'est pas un feu : torchères pétrolières, sites industriels. Critère :
        type FIRMS ≠ 0 ou site industriel persistant (cellule 0,05°), dans la zone affichée.
      </p>
    </div>
  </form>
</template>
