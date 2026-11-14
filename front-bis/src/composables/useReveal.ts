import { onBeforeUnmount, onMounted } from 'vue'

/**
 * Révèle les éléments `.reveal` à l'entrée dans le viewport.
 * Un MutationObserver couvre les éléments ajoutés après le montage.
 */
export function useReveal() {
  let observer: IntersectionObserver | null = null
  let mutation: MutationObserver | null = null

  const observe = (root: ParentNode = document) => {
    root.querySelectorAll<HTMLElement>('.reveal:not(.is-visible)').forEach((el) => {
      observer?.observe(el)
    })
  }

  onMounted(() => {
    observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            entry.target.classList.add('is-visible')
            observer?.unobserve(entry.target)
          }
        }
      },
      { rootMargin: '0px 0px -8% 0px', threshold: 0.08 },
    )
    observe()
    mutation = new MutationObserver(() => observe())
    mutation.observe(document.body, { childList: true, subtree: true })
  })

  onBeforeUnmount(() => {
    observer?.disconnect()
    mutation?.disconnect()
  })
}
