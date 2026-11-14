<script setup lang="ts">
import { computed, nextTick, ref, useTemplateRef, watch } from 'vue'
import type { CalendarPoint, YearMonth } from '@/types/api'
import {
  COVERAGE_LABELS,
  MONTHS_LONG,
  MONTHS_SHORT,
  REGIME_LABELS,
  buildMatrix,
  cellColor,
  formatAnomaly,
  formatCount,
  isProvisional,
  legendStops,
  monthLabel,
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
  /** Année mise en regard de la médiane (comparateur sous le calendrier). */
  compareYear: number | null
}>()

const emit = defineEmits<{
  select: [month: YearMonth]
  /** Clic sur une année : la placer dans le comparateur. */
  compare: [year: number]
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
const legend = computed(() => legendStops(props.colorMode, max.value))

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
        ? `Médiane de ${name} 2001-2025 : ${formatCount(b.median)} détections équivalentes VIIRS`
        : `${name} : médiane indisponible`,
      color: cellColor(pseudo, props.colorMode, max.value),
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
  const parts = [
    `${monthLabel(c.month)} : ${formatCount(p.harmonized_value)} détections équivalentes VIIRS`,
    p.baseline_median !== null ? `${formatAnomaly(p)} par rapport à la médiane` : null,
    REGIME_LABELS[p.sensor_regime],
    isProvisional(p.coverage_status) ? COVERAGE_LABELS[p.coverage_status] : null,
  ]
  return parts.filter(Boolean).join(', ')
}

const HATCH =
  'repeating-linear-gradient(135deg, rgb(255 255 255 / 0.75) 0 2px, transparent 2px 6px)'

function cellStyle(c: CalendarCell) {
  const color = cellColor(c.point, props.colorMode, max.value)
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
      aria-label="Calendrier d'activité des points chauds, années en lignes, mois en colonnes"
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
        <span role="rowheader" class="block pr-1 text-right">
          <!-- Raccourci souris vers le comparateur ; au clavier, le sélecteur d'année suffit. -->
          <button
            type="button"
            tabindex="-1"
            :aria-pressed="row[0]!.year === compareYear"
            :title="`Comparer ${row[0]!.year} à la médiane`"
            :class="[
              'w-full rounded px-1 text-right leading-5 tabular-nums transition-colors duration-150',
              row[0]!.year === compareYear
                ? 'bg-orange-100 font-semibold text-orange-900'
                : 'text-stone-600 hover:bg-stone-100 hover:text-stone-900',
            ]"
            @click="emit('compare', row[0]!.year)"
          >
            {{ row[0]!.year }}
          </button>
        </span>
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
          Médiane
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
      La dernière ligne, Médiane, donne le mois type 2001-2025 pour comparaison.
    </p>

    <div class="mt-3 flex flex-wrap items-center gap-x-6 gap-y-2 text-xs text-stone-700">
      <div class="flex items-center gap-2">
        <span class="font-medium">{{
          colorMode === 'value' ? 'Détections équivalentes VIIRS' : 'Écart à la médiane'
        }}</span>
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
        Mois incomplet ou provisoire (NRT)
      </span>
      <span class="flex items-center gap-1.5">
        <span
          class="block size-3 rounded-[2px] border border-dashed border-stone-300 bg-stone-50"
          aria-hidden="true"
        />
        Aucune donnée
      </span>
    </div>
  </div>
</template>
