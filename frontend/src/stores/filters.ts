import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import type { AreaQuery, BBox, YearMonth } from '@/types/api'
import type { ColorMode } from '@/utils/calendar'
import type { ChartView, ChartWindow } from '@/utils/chart'

export const YEAR_MIN = 2000
export const YEAR_MAX = 2026

/** Filtres partagés par le calendrier, le graphique et la carte. */
export const useFiltersStore = defineStore('filters', () => {
  /** `GA` ou `GA-1`..`GA-9`. */
  const region = ref<string>('GA')
  const bbox = ref<BBox | null>(null)
  const yearRange = ref<[number, number]>([2001, 2025])
  /** Activé par défaut : feux de végétation uniquement (torchères exclues). */
  const filterStatic = ref(true)
  /** Coloration du calendrier (et plus tard de la carte) : intensité ou anomalie. */
  const colorMode = ref<ColorMode>('value')
  /** Mois épinglé (clic / Entrée dans le calendrier). */
  const selectedMonth = ref<YearMonth | null>(null)
  /**
   * Vue d'harmonisation partagée par le calendrier et le graphe : `before` = capteurs bruts
   * (rupture 2012 visible), `after` = série harmonisée. Une seule bascule pour les deux vues.
   */
  const harmonizationView = ref<ChartView>('after')
  /** Fenêtre de zoom du graphe : conservée entre bascules et changements de filtre. */
  const chartWindow = ref<ChartWindow | null>(null)

  const start = computed<YearMonth>(() => `${yearRange.value[0]}-01`)
  const end = computed<YearMonth>(() => `${yearRange.value[1]}-12`)

  /** Une bbox dessinée remplace la région sélectionnée. */
  const query = computed<AreaQuery>(() => ({
    ...(bbox.value ? { bbox: bbox.value } : { region: region.value }),
    start: start.value,
    end: end.value,
    filter_static: filterStatic.value,
  }))

  function selectRegion(code: string) {
    region.value = code
    bbox.value = null
    selectedMonth.value = null
  }

  function selectBBox(value: BBox) {
    const [w, s, e, n] = value
    const valid = w < e && s < n && w >= -180 && e <= 180 && s >= -90 && n <= 90
    if (!valid) throw new RangeError(`bbox invalide : ${value.join(',')}`)
    bbox.value = value
  }

  function setYearRange(from: number, to: number) {
    const lo = Math.max(YEAR_MIN, Math.min(from, to))
    const hi = Math.min(YEAR_MAX, Math.max(from, to))
    yearRange.value = [lo, hi]
  }

  return {
    region,
    bbox,
    yearRange,
    filterStatic,
    colorMode,
    selectedMonth,
    harmonizationView,
    chartWindow,
    start,
    end,
    query,
    selectRegion,
    selectBBox,
    setYearRange,
  }
})
