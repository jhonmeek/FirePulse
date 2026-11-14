<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, useTemplateRef } from 'vue'
import { gsap } from '@/lib/motion'

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
const current = ref(0)
let observer: IntersectionObserver | null = null

const formatter = new Intl.NumberFormat('fr-FR', {
  maximumFractionDigits: props.decimals,
  minimumFractionDigits: props.decimals,
})

function display(value: number): string {
  return `${props.prefix}${formatter.format(value)}${props.suffix}`
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
  if (props.reducedMotion || !el.value) {
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
