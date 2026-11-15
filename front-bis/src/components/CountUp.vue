<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, useTemplateRef } from 'vue'
import { gsap } from '@/lib/motion'
import { locale } from '@/lib/i18n'

const props = withDefaults(
  defineProps<{
    to: number
    duration?: number
    decimals?: number
    prefix?: string
    suffix?: string
    reducedMotion?: boolean
  }>(),
  { duration: 1.8, decimals: 0, prefix: '', suffix: '', reducedMotion: false },
)

const el = useTemplateRef<HTMLSpanElement>('el')
// Affiche la valeur finale tant que l'animation d'intersection n'a pas démarré :
// le chiffre reste correct si le navigateur ou la démo n'exécute pas GSAP.
const current = ref(props.to)
let observer: IntersectionObserver | null = null

function display(value: number): string {
  const loc = locale.value === 'en' ? 'en-US' : 'fr-FR'
  const formatted = new Intl.NumberFormat(loc, {
    maximumFractionDigits: props.decimals,
    minimumFractionDigits: props.decimals,
  }).format(value)
  return `${props.prefix}${formatted}${props.suffix}`
}

function animate() {
  const state = { value: 0 }
  gsap.to(state, {
    value: props.to,
    duration: props.duration,
    ease: 'power2.out',
    onUpdate: () => (current.value = state.value),
  })
}

onMounted(() => {
  if (props.reducedMotion || !el.value || typeof IntersectionObserver === 'undefined') {
    current.value = props.to
    return
  }
  observer = new IntersectionObserver(
    (entries) => {
      if (entries.some((entry) => entry.isIntersecting)) {
        current.value = 0
        observer?.disconnect()
        animate()
      }
    },
    { threshold: 0.4 },
  )
  observer.observe(el.value)
})

onBeforeUnmount(() => observer?.disconnect())
</script>

<template>
  <span ref="el" class="countup">{{ display(current) }}</span>
</template>

<style scoped>
.countup {
  font-variant-numeric: tabular-nums;
}
</style>
