import { computed, ref, shallowRef, watch } from 'vue'
import { fetchCalendar } from '@/services/api'
import { useFiltersStore } from '@/stores/filters'
import type { AreaQuery, CalendarResponse } from '@/types/api'

type AreaOnly = Omit<AreaQuery, 'filter_static' | 'start' | 'end'>

/**
 * Séries calendrier de la zone courante, **avec et sans** filtre torchères :
 * - le toggle bascule instantanément (pas de requête) ;
 * - la différence des deux donne le nombre de détections retirées par le filtre.
 * L'historique complet est chargé (sans start/end) : rang et médiane restent justes
 * quand la plage d'années est réduite, filtrée côté client.
 */
export function useCalendar() {
  const filters = useFiltersStore()
  const filtered = shallowRef<CalendarResponse | null>(null)
  const unfiltered = shallowRef<CalendarResponse | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)
  let requestId = 0

  const area = computed<AreaOnly>(() =>
    filters.bbox ? { bbox: filters.bbox } : { region: filters.region },
  )

  async function load(q: AreaOnly) {
    const id = ++requestId
    loading.value = true
    error.value = null
    try {
      const [withFilter, without] = await Promise.all([
        fetchCalendar({ ...q, filter_static: true }),
        fetchCalendar({ ...q, filter_static: false }),
      ])
      // Ignore une réponse arrivée après une requête plus récente.
      if (id !== requestId) return
      filtered.value = withFilter
      unfiltered.value = without
    } catch (e) {
      if (id === requestId) error.value = e instanceof Error ? e.message : String(e)
    } finally {
      if (id === requestId) loading.value = false
    }
  }

  watch(area, load, { immediate: true, deep: true })

  const data = computed(() => (filters.filterStatic ? filtered.value : unfiltered.value))

  return { data, filtered, unfiltered, loading, error, reload: () => load(area.value) }
}
