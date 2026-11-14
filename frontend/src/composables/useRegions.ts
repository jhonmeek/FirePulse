import { onMounted, ref, shallowRef } from 'vue'
import { fetchRegions } from '@/services/api'
import type { Region } from '@/types/api'

/** Liste légère des régions (sans géométrie) pour le sélecteur de zone. */
export function useRegions() {
  const regions = shallowRef<Region[]>([])
  const error = ref<string | null>(null)

  onMounted(async () => {
    try {
      regions.value = (await fetchRegions(false)).regions
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e)
    }
  })

  return { regions, error }
}
