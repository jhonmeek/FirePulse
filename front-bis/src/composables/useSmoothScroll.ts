import { onBeforeUnmount, onMounted } from 'vue'
import Lenis from 'lenis'
import { gsap, ScrollTrigger } from '@/lib/motion'

/**
 * Smooth scrolling + ScrollTrigger. Désactivé si l'utilisateur préfère
 * les mouvements réduits. Le ticker GSAP pilote Lenis pour éviter deux boucles.
 */
export function useSmoothScroll() {
  let lenis: Lenis | null = null
  let ticker: ((time: number) => void) | null = null
  let media: MediaQueryList | null = null
  let active = false

  const start = () => {
    if (active || media?.matches) return
    active = true
    lenis = new Lenis({
      duration: 1.05,
      smoothWheel: true,
      wheelMultiplier: 0.95,
      touchMultiplier: 1.2,
    })
    lenis.on('scroll', ScrollTrigger.update)
    ticker = (time: number) => lenis?.raf(time * 1000)
    gsap.ticker.add(ticker)
    gsap.ticker.lagSmoothing(0)
  }

  const stop = () => {
    if (!active) return
    active = false
    if (ticker) gsap.ticker.remove(ticker)
    ticker = null
    lenis?.destroy()
    lenis = null
  }

  onMounted(() => {
    media = window.matchMedia('(prefers-reduced-motion: reduce)')
    start()
    media.addEventListener('change', (e) => (e.matches ? stop() : start()))
  })

  onBeforeUnmount(() => {
    media = null
    stop()
  })
}
