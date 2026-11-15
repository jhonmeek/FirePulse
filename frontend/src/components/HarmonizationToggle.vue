<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { useFiltersStore } from '@/stores/filters'

/**
 * Bascule « Données brutes / Données corrigées » (avant / après harmonisation) partagée :
 * calendrier et graphe lisent la même valeur du store, donc basculer l'un bascule l'autre.
 * `name` distinct par instance : deux groupes radio de même nom s'excluraient mutuellement.
 */
const props = defineProps<{ name: string }>()

const { harmonizationView: view } = storeToRefs(useFiltersStore())

const options = [
  {
    value: 'before',
    label: 'Données brutes',
    title: "Avant harmonisation : chaque mois tel que vu par le satellite de l'époque",
  },
  {
    value: 'after',
    label: 'Données corrigées',
    title: "Après harmonisation : toutes les années ramenées à l'échelle VIIRS 375 m",
  },
] as const
</script>

<template>
  <div
    role="radiogroup"
    aria-label="Données brutes ou corrigées (harmonisation des satellites)"
    class="segmented"
  >
    <label v-for="o in options" :key="o.value" class="segmented-item" :title="o.title">
      <input v-model="view" class="sr-only" type="radio" :name="props.name" :value="o.value" />
      {{ o.label }}
    </label>
  </div>
</template>
