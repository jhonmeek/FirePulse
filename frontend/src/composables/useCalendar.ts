import { computed, ref, shallowRef, watch } from 'vue'
import { fetchCalendar } from '@/services/api'
import { useFiltersStore } from '@/stores/filters'
import type { AreaQuery, CalendarResponse } from '@/types/api'

/**
 * Série calendrier de la zone courante.
 * On charge l'historique complet (sans start/end) : le rang historique et la médiane
 * restent justes quand l'utilisateur réduit la plage d'années, filtrée côté client.
 */
export function useCalendar() {
  const filters = useFiltersStore()
  const data = shallowRef<CalendarResponse | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)
  let requestId = 0

  const areaQuery = computed<AreaQuery>(() =>
    filters.bbox
      ? { bbox: filters.bbox, filter_static: filters.filterStatic }
      : { region: filters.region, filter_static: filters.filterStatic },
  )

  async function load(query: AreaQuery) {
    const id = ++requestId
    loading.value = true
    error.value = null
    try {
      const res = await fetchCalendar(query)
      // Ignore une réponse arrivée après une requête plus récente.
      if (id === requestId) data.value = res
    } catch (e) {
      if (id === requestId) error.value = e instanceof Error ? e.message : String(e)
    } finally {
      if (id === requestId) loading.value = false
    }
  }

  watch(areaQuery, load, { immediate: true, deep: true })

  return { data, loading, error, reload: () => load(areaQuery.value) }
}
