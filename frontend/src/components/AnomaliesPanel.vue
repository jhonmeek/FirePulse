<script setup lang="ts">
import { computed } from 'vue'
import type { CalendarPoint, YearMonth } from '@/types/api'
import { rankAnomalies, seasonalBaselines } from '@/utils/anomalies'
import { inRange } from '@/utils/chart'
import { MONTHS_LONG, MONTHS_SHORT, formatAnomaly, formatCount, monthLabel } from '@/utils/calendar'

const props = defineProps<{
  series: CalendarPoint[]
  yearRange: [number, number]
  selectedMonth: YearMonth | null
}>()
const emit = defineEmits<{ select: [month: YearMonth] }>()

const baselines = computed(() => seasonalBaselines(props.series))
const scaleMax = computed(() => Math.max(1, ...baselines.value.map((b) => b.iqr?.[1] ?? b.median)))
const pct = (v: number) => `${(100 * v) / scaleMax.value}%`

/** Mois calendaire du mois sélectionné, pour le surligner dans la saisonnalité. */
const selectedCal = computed(() => (props.selectedMonth ? +props.selectedMonth.slice(5) : null))
const selectedValue = computed(
  () => props.series.find((p) => p.month === props.selectedMonth)?.harmonized_value ?? null,
)

/** Classement limité à la plage affichée (comme /anomalies/?start=&end=). */
const ranked = computed(() => rankAnomalies(inRange(props.series, props.yearRange), 5))
</script>

<template>
  <div class="grid gap-6 md:grid-cols-2">
    <figure>
      <figcaption class="mb-2 text-sm font-medium text-stone-800">
        Saisonnalité de référence 2001–2025
        <span class="block text-xs font-normal text-stone-500">
          Médiane (barre) et intervalle interquartile (trait) par mois
        </span>
      </figcaption>
      <ol class="flex h-36 items-end gap-1" aria-label="Médiane mensuelle de référence">
        <li
          v-for="b in baselines"
          :key="b.month"
          class="relative flex h-full flex-1 flex-col justify-end"
          :aria-label="`${MONTHS_LONG[b.month - 1]} : médiane ${formatCount(b.median)}${
            b.iqr ? `, IQR ${formatCount(b.iqr[0])} à ${formatCount(b.iqr[1])}` : ''
          }`"
        >
          <span
            v-if="b.iqr"
            class="absolute left-1/2 w-px -translate-x-1/2 bg-stone-500"
            :style="{ bottom: pct(b.iqr[0]), height: pct(b.iqr[1] - b.iqr[0]) }"
            aria-hidden="true"
          />
          <span
            :class="[
              'block w-full rounded-t-sm',
              selectedCal === b.month ? 'bg-orange-600' : 'bg-stone-300',
            ]"
            :style="{ height: pct(b.median) }"
            aria-hidden="true"
          />
          <span
            v-if="selectedCal === b.month && selectedValue !== null"
            class="absolute left-0 right-0 border-t-2 border-dashed border-stone-900"
            :style="{ bottom: pct(Math.min(selectedValue, scaleMax)) }"
            :title="`${monthLabel(selectedMonth!)} : ${formatCount(selectedValue)}`"
            aria-hidden="true"
          />
        </li>
      </ol>
      <div class="mt-1 flex gap-1 text-center text-[0.65rem] text-stone-600" aria-hidden="true">
        <span v-for="b in baselines" :key="b.month" class="flex-1">{{
          MONTHS_SHORT[b.month - 1]![0]!.toUpperCase()
        }}</span>
      </div>
      <p v-if="selectedMonth && selectedValue !== null" class="mt-1 text-xs text-stone-600">
        Pointillés : {{ monthLabel(selectedMonth) }} ({{ formatCount(selectedValue) }}).
      </p>
    </figure>

    <div class="grid grid-cols-2 gap-4 text-sm">
      <section v-for="side in ['positive', 'negative'] as const" :key="side">
        <h3 class="mb-2 font-medium text-stone-800">
          {{ side === 'positive' ? 'Mois les plus au-dessus' : 'Mois les plus en dessous' }}
        </h3>
        <ol class="space-y-1">
          <li v-for="p in ranked[side]" :key="p.month">
            <button
              type="button"
              :aria-pressed="p.month === selectedMonth"
              :class="[
                'flex w-full items-baseline justify-between gap-2 rounded px-2 py-1 text-left hover:bg-stone-100 focus-visible:outline-2 focus-visible:outline-orange-600',
                p.month === selectedMonth ? 'bg-stone-100 ring-1 ring-stone-400' : '',
              ]"
              @click="emit('select', p.month)"
            >
              <span class="capitalize">{{ monthLabel(p.month) }}</span>
              <span
                :class="[
                  'tabular-nums font-semibold',
                  side === 'positive' ? 'text-orange-800' : 'text-purple-800',
                ]"
                >{{ formatAnomaly(p) }}</span
              >
            </button>
          </li>
          <li v-if="!ranked[side].length" class="text-stone-500">Aucun mois sur la période.</li>
        </ol>
      </section>
    </div>
  </div>
</template>
