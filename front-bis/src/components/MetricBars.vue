<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, useTemplateRef } from 'vue'
import { formatCount } from '@/lib/data'

interface MetricItem {
  key: string
  label: string
  value: number
  note?: string
  accent?: boolean
}

const props = withDefaults(
  defineProps<{
    items: MetricItem[]
    reducedMotion?: boolean
    max?: number
  }>(),
  { reducedMotion: false, max: undefined },
)

const wrapper = useTemplateRef<HTMLDivElement>('wrapper')
const visible = ref(false)
let observer: IntersectionObserver | null = null
const maxValue = props.max ?? Math.max(...props.items.map((i) => i.value)) * 1.06

onMounted(() => {
  if (props.reducedMotion || !wrapper.value) {
    visible.value = true
    return
  }
  observer = new IntersectionObserver(
    (entries) => {
      if (entries.some((entry) => entry.isIntersecting)) {
        visible.value = true
        observer?.disconnect()
      }
    },
    { threshold: 0.2 },
  )
  observer.observe(wrapper.value)
})

onBeforeUnmount(() => observer?.disconnect())
</script>

<template>
  <div ref="wrapper" class="metrics" :class="{ 'is-visible': visible }">
    <div
      v-for="(item, index) in items"
      :key="item.key"
      class="metric"
      :class="{ accent: item.accent }"
    >
      <div class="metric-head">
        <span class="metric-label">{{ item.label }}</span>
        <span class="metric-value">{{ formatCount(item.value) }}</span>
      </div>
      <div class="metric-track">
        <span
          class="metric-fill"
          :style="{
            width: `${Math.min(100, (item.value / maxValue) * 100)}%`,
            transitionDelay: `${index * 110}ms`,
          }"
        ></span>
      </div>
      <p v-if="item.note" class="metric-note">{{ item.note }}</p>
    </div>
  </div>
</template>

<style scoped>
.metrics {
  display: grid;
  gap: 18px;
}

.metric {
  display: grid;
  gap: 7px;
}

.metric-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 16px;
}

.metric-label {
  font-size: 0.78rem;
  color: var(--muted);
}

.metric-value {
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  font-size: 0.82rem;
  color: var(--ink);
}

.metric-track {
  height: 8px;
  border-radius: 4px;
  background: rgba(244, 241, 232, 0.07);
  overflow: hidden;
}

.metric-fill {
  display: block;
  height: 100%;
  border-radius: 4px;
  background: rgba(244, 241, 232, 0.22);
  transform: scaleX(0);
  transform-origin: left center;
  transition: transform 1.2s var(--ease-out);
}

.metrics.is-visible .metric-fill {
  transform: scaleX(1);
}

.metric.accent .metric-label {
  color: var(--ink);
  font-weight: 600;
}

.metric.accent .metric-value {
  color: var(--gold);
}

.metric.accent .metric-fill {
  background: var(--grad-heat);
  box-shadow: 0 0 18px rgba(255, 122, 61, 0.35);
}

.metric-note {
  font-family: var(--font-mono);
  font-size: 0.54rem;
  letter-spacing: 0.04em;
  color: var(--dim);
}
</style>
