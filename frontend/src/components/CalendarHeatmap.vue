<script setup lang="ts">
import { computed, nextTick, ref, useTemplateRef, watch } from 'vue'
import type { CalendarPoint, YearMonth } from '@/types/api'
import type { ChartView } from '@/utils/chart'
import {
  COVERAGE_LABELS,
  RAW_SENSOR_LABELS,
  RAW_SWITCH,
  MONTHS_LONG,
  MONTHS_SHORT,
  buildMatrix,
  cellColor,
  formatAnomaly,
  formatCount,
  isProvisional,
  legendStops,
  monthLabel,
  rawEraValue,
  valueMax,
  type CalendarCell,
  type ColorMode,
} from '@/utils/calendar'
import { seasonalBaselines } from '@/utils/anomalies'

const props = defineProps<{
  series: CalendarPoint[]
  yearRange: [number, number]
  colorMode: ColorMode
  selectedMonth: YearMonth | null
  /** Avant harmonisation (brut du capteur d'époque) ou après (série harmonisée). */
  view: ChartView
}>()

const emit = defineEmits<{
  select: [month: YearMonth]
  /** Survol / focus : null quand le pointeur quitte la grille. */
  preview: [month: YearMonth | null]
}>()

const rows = computed(() => buildMatrix(props.series, props.yearRange[0], props.yearRange[1]))
const flat = computed(() => rows.value.flat())

/** Échelle commune à toute la plage affichée (comparaison inter-années juste). */
const max = computed(() => {
  const [from, to] = props.yearRange
  return valueMax(
    props.series.filter((p) => +p.month.slice(0, 4) >= from && +p.month.slice(0, 4) <= to),
  )
})
const before = computed(() => props.view === 'before')
/** En vue Avant, l'anomalie n'a pas de sens sur du brut : légende d'intensité. */
const legend = computed(() => legendStops(before.value ? 'value' : props.colorMode, max.value))
const legendTitle = computed(() =>
  before.value
    ? 'Points de feu (données brutes)'
    : props.colorMode === 'value'
      ? 'Points de feu par mois'
      : 'Par rapport à la normale',
)

/**
 * Ligne de référence « Médiane 2001-2025 » : même échelle que les années, pour comparer
 * chaque ligne à l'année type. En mode anomalie elle vaut 0 % (couleur neutre) par définition.
 */
const baselineRow = computed(() => {
  const byMonth = new Map(seasonalBaselines(props.series).map((b) => [b.month, b]))
  return MONTHS_LONG.map((name, i) => {
    const b = byMonth.get(i + 1)
    const pseudo = b ? ({ harmonized_value: b.median, anomaly_percent: 0 } as CalendarPoint) : null
    return {
      key: name,
      label: b
        ? `Mois normal de ${name} (médiane 2001-2025, données corrigées) : ${formatCount(b.median)} points de feu`
        : `${name} : normale indisponible`,
      // Référence commune aux deux vues : toujours la médiane harmonisée, en intensité en vue Avant.
      color: cellColor(pseudo, before.value ? 'value' : props.colorMode, max.value),
    }
  })
})

// ---- focus mobile (roving tabindex) : une seule cellule tabulable à la fois
const active = ref<YearMonth | null>(null)
const grid = useTemplateRef<HTMLElement>('grid')

watch(
  [flat, () => props.selectedMonth],
  () => {
    const months = flat.value.map((c) => c.month)
    if (props.selectedMonth && months.includes(props.selectedMonth))
      active.value = props.selectedMonth
    else if (!active.value || !months.includes(active.value)) {
      const lastWithData = [...flat.value].reverse().find((c) => c.point?.harmonized_value != null)
      active.value = lastWithData?.month ?? months[0] ?? null
    }
  },
  { immediate: true },
)

async function moveTo(index: number) {
  const cell = flat.value[Math.max(0, Math.min(flat.value.length - 1, index))]
  if (!cell) return
  active.value = cell.month
  await nextTick()
  grid.value?.querySelector<HTMLButtonElement>(`[data-month="${cell.month}"]`)?.focus()
}

function onKeydown(e: KeyboardEvent) {
  const i = flat.value.findIndex((c) => c.month === active.value)
  if (i < 0) return
  const col = i % 12
  const moves: Record<string, number> = {
    ArrowRight: i + 1,
    ArrowLeft: i - 1,
    ArrowDown: i + 12,
    ArrowUp: i - 12,
    Home: i - col,
    End: i - col + 11,
    PageUp: col,
    PageDown: flat.value.length - 12 + col,
  }
  const target = moves[e.key]
  if (target === undefined) return
  e.preventDefault()
  moveTo(target)
}

function cellLabel(c: CalendarCell): string {
  const p = c.point
  if (!p || p.harmonized_value === null) return `${monthLabel(c.month)} : aucune donnée`
  if (before.value) {
    const raw = rawEraValue(p)
    return [
      raw.value === null
        ? `${monthLabel(c.month)} : capteur ${RAW_SENSOR_LABELS[raw.sensor]} sans donnée`
        : `${monthLabel(c.month)} : ${formatCount(raw.value)} points de feu bruts ${RAW_SENSOR_LABELS[raw.sensor]}`,
      `${formatCount(p.harmonized_value)} après correction`,
      isProvisional(p.coverage_status) ? COVERAGE_LABELS[p.coverage_status] : null,
    ]
      .filter(Boolean)
      .join(', ')
  }
  const parts = [
    `${monthLabel(c.month)} : ${formatCount(p.harmonized_value)} points de feu`,
    p.baseline_median !== null ? `${formatAnomaly(p)} par rapport à la normale` : null,
    isProvisional(p.coverage_status) ? COVERAGE_LABELS[p.coverage_status] : null,
  ]
  return parts.filter(Boolean).join(', ')
}

const HATCH =
  'repeating-linear-gradient(135deg, rgb(255 255 255 / 0.75) 0 2px, transparent 2px 6px)'

function cellStyle(c: CalendarCell) {
  const color = cellColor(c.point, props.colorMode, max.value, props.view)
  const provisional = c.point && isProvisional(c.point.coverage_status)
  return {
    backgroundColor: color ?? undefined,
    backgroundImage: provisional ? HATCH : undefined,
  }
}
</script>

<template>
  <div>
    <div
      ref="grid"
      role="grid"
      aria-label="Calendrier des points de feu, années en lignes, mois en colonnes"
      aria-describedby="calendar-help"
      class="grid grid-cols-[3.25rem_repeat(12,minmax(0,1fr))] gap-px text-xs"
      @keydown="onKeydown"
      @mouseleave="emit('preview', null)"
    >
      <div role="row" class="contents">
        <!-- Cellule d'angle réelle : un élément sr-only (absolu) sortirait de la grille. -->
        <span role="columnheader"><span class="sr-only">Année</span></span>
        <span
          v-for="(m, i) in MONTHS_SHORT"
          :key="m"
          role="columnheader"
          :aria-label="MONTHS_LONG[i]"
          class="pb-1 text-center text-[0.7rem] font-medium text-stone-600"
        >
          <!-- Initiale sur mobile : les abréviations se chevauchent sous ~640 px. -->
          <span class="sm:hidden" aria-hidden="true">{{ m[0]!.toUpperCase() }}</span>
          <span class="hidden sm:inline" aria-hidden="true">{{ m }}</span>
        </span>
      </div>
      <div v-for="row in rows" :key="row[0]!.year" role="row" class="contents">
        <span role="rowheader" class="pr-2 text-right leading-5 tabular-nums text-stone-700">{{
          row[0]!.year
        }}</span>
        <span v-for="c in row" :key="c.month" role="gridcell" class="block">
          <button
            type="button"
            :data-month="c.month"
            :tabindex="c.month === active ? 0 : -1"
            :aria-label="cellLabel(c)"
            :aria-pressed="c.month === selectedMonth"
            :class="[
              'block h-5 w-full rounded-[2px] focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-stone-900',
              c.point?.harmonized_value == null
                ? 'border border-dashed border-stone-300 bg-stone-50'
                : '',
              c.month === selectedMonth ? 'ring-2 ring-stone-900 ring-offset-1' : '',
              // Vue Avant : trait du passage MODIS → VIIRS S-NPP (février 2012).
              before && c.month === RAW_SWITCH ? 'shadow-[inset_3px_0_0_#1c1917]' : '',
            ]"
            :style="cellStyle(c)"
            @click="emit('select', c.month)"
            @focus="((active = c.month), emit('preview', c.month))"
            @mouseenter="emit('preview', c.month)"
          />
        </span>
      </div>

      <!-- Série de comparaison : l'année type, séparée des années observées. -->
      <div role="row" class="contents">
        <span
          role="rowheader"
          class="mt-2 block border-t border-stone-300 pt-1 pr-1 text-right text-xs font-semibold leading-5 text-stone-800"
        >
          Normale
        </span>
        <span
          v-for="c in baselineRow"
          :key="c.key"
          role="gridcell"
          class="mt-2 block border-t border-stone-300 pt-1"
          :aria-label="c.label"
          :title="c.label"
        >
          <span
            class="block h-5 w-full rounded-[2px] ring-1 ring-inset ring-stone-900/15"
            :class="c.color ? '' : 'border border-dashed border-stone-300 bg-stone-50'"
            :style="{ backgroundColor: c.color ?? undefined }"
          />
        </span>
      </div>
    </div>

    <p id="calendar-help" class="sr-only">
      Flèches pour se déplacer, Début et Fin pour aller en début ou fin d'année, Page précédente et
      Page suivante pour la première ou la dernière année, Entrée pour afficher le détail du mois.
      La dernière ligne, Normale, donne le mois médian 2001-2025 (données corrigées) pour
      comparaison. En données brutes, chaque mois montre les points de feu vus par le satellite de
      l'époque : MODIS jusqu'à janvier 2012, VIIRS S-NPP à partir de février 2012.
    </p>

    <div class="mt-3 flex flex-wrap items-center gap-x-6 gap-y-2 text-xs text-stone-700">
      <div class="flex items-center gap-2">
        <span class="font-medium">{{ legendTitle }}</span>
        <ol class="flex" aria-label="Légende des couleurs">
          <li v-for="s in legend" :key="s.label" class="flex flex-col items-center">
            <span class="block h-3 w-10" :style="{ backgroundColor: s.color }" aria-hidden="true" />
            <span class="mt-0.5 tabular-nums">{{ s.label }}</span>
          </li>
        </ol>
      </div>
      <span class="flex items-center gap-1.5">
        <span
          class="block size-3 rounded-[2px] bg-amber-300"
          :style="{ backgroundImage: HATCH }"
          aria-hidden="true"
        />
        Mois incomplet ou provisoire
      </span>
      <span class="flex items-center gap-1.5">
        <span
          class="block size-3 rounded-[2px] border border-dashed border-stone-300 bg-stone-50"
          aria-hidden="true"
        />
        Aucune donnée
      </span>
      <span>
        <strong class="font-semibold text-stone-800">Normale</strong> : valeur habituelle du mois
        (médiane 2001-2025)
      </span>
      <span v-if="before" class="flex items-center gap-1.5">
        <span class="block h-3 w-1 rounded-sm bg-stone-900" aria-hidden="true" />
        Changement de satellite : MODIS → VIIRS (février 2012)
      </span>
    </div>
  </div>
</template>
