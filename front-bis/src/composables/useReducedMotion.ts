import { onBeforeUnmount, onMounted, ref } from 'vue'

export function useReducedMotion() {
  const reduced = ref(false)
  let media: MediaQueryList | null = null
  const update = () => {
    reduced.value = media?.matches ?? false
  }
  onMounted(() => {
    media = window.matchMedia('(prefers-reduced-motion: reduce)')
    update()
    media.addEventListener('change', update)
  })
  onBeforeUnmount(() => media?.removeEventListener('change', update))
  return reduced
}
