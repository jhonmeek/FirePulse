<script setup lang="ts">
import { nextTick, onMounted, useTemplateRef } from 'vue'
import { gsap, ScrollTrigger } from '@/lib/motion'

const props = withDefaults(defineProps<{ reducedMotion?: boolean }>(), { reducedMotion: false })

const wrapper = useTemplateRef<HTMLDivElement>('wrapper')

const regimes = [
  {
    id: 'terra',
    label: 'MODIS Terra seul',
    range: '2000-11 → 2002-06',
    width: 6.5,
    tone: 'gold',
    note: 'Aqua n’est pas encore là.',
  },
  {
    id: 'modis',
    label: 'MODIS Terra + Aqua',
    range: '2002-07 → 2012-01',
    width: 38,
    tone: 'ember',
    note: 'Reconstitué sur l’échelle VIIRS.',
  },
  {
    id: 'snpp',
    label: 'VIIRS S-NPP',
    range: '2012-02 → 2026-11-02',
    width: 39,
    tone: 'teal',
    note: 'L’échelle de référence.',
  },
  {
    id: 'noaa20',
    label: 'Pont NOAA-20',
    range: '2026-11-03 → …',
    width: 16.5,
    tone: 'cyan',
    note: 'La continuité après S-NPP.',
  },
]

onMounted(async () => {
  if (props.reducedMotion) return
  await nextTick()
  const line = wrapper.value?.querySelector('.timeline-progress')
  if (line) {
    gsap.from(line, {
      scaleX: 0,
      transformOrigin: 'left center',
      duration: 1.6,
      ease: 'power2.inOut',
      immediateRender: false,
      scrollTrigger: { trigger: wrapper.value, start: 'top 82%', once: true },
    })
  }
  ScrollTrigger.refresh()
})
</script>

<template>
  <div ref="wrapper" class="timeline">
    <div class="timeline-head">
      <span class="tiny-label">Quatre régimes, une seule chronologie</span>
      <span class="timeline-cut">2 nov. 2026 · arrêt S-NPP</span>
    </div>

    <div class="timeline-track">
      <div class="timeline-progress"></div>
      <div
        v-for="regime in regimes"
        :key="regime.id"
        class="timeline-segment"
        :class="regime.tone"
        :style="{ flexGrow: regime.width }"
      >
        <span class="segment-bar"></span>
        <span class="segment-label">{{ regime.label }}</span>
        <span class="segment-range">{{ regime.range }}</span>
        <span class="segment-note">{{ regime.note }}</span>
      </div>
      <div class="timeline-marker" aria-hidden="true">
        <span class="marker-pulse"></span>
        <span class="marker-label">S-NPP</span>
      </div>
    </div>

    <div class="timeline-legend">
      <span><i class="dot gold"></i>Terra seul</span>
      <span><i class="dot ember"></i>MODIS reconstitué</span>
      <span><i class="dot teal"></i>VIIRS observé</span>
      <span><i class="dot cyan"></i>Pont NOAA-20</span>
    </div>
  </div>
</template>

<style scoped>
.timeline {
  display: grid;
  gap: 18px;
}

.timeline-head {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px 20px;
}

.timeline-cut {
  font-family: var(--font-mono);
  font-size: 0.56rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--ember);
}

.timeline-track {
  position: relative;
  display: flex;
  gap: 5px;
  min-height: 168px;
  padding: 18px 0 10px;
}

.timeline-progress {
  position: absolute;
  top: 8px;
  left: 0;
  right: 0;
  height: 1px;
  background: linear-gradient(90deg, var(--gold), var(--ember) 38%, var(--teal) 68%, var(--cyan));
  opacity: 0.7;
}

.timeline-segment {
  position: relative;
  display: flex;
  flex-direction: column;
  justify-content: flex-end;
  gap: 4px;
  min-width: 0;
  padding: 12px 10px 10px;
  border-top: 2px solid transparent;
  background: linear-gradient(180deg, rgba(244, 241, 232, 0.04), transparent);
  transition:
    background 0.3s ease,
    border-color 0.3s ease;
}

.timeline-segment:hover {
  background: rgba(244, 241, 232, 0.07);
}

.timeline-segment.gold {
  border-color: var(--gold);
}
.timeline-segment.ember {
  border-color: var(--ember);
}
.timeline-segment.teal {
  border-color: var(--teal);
}
.timeline-segment.cyan {
  border-color: var(--cyan);
}

.segment-bar {
  position: absolute;
  left: 10px;
  right: 10px;
  bottom: 88px;
  height: 3px;
  border-radius: 2px;
  background: currentColor;
  opacity: 0.7;
}

.gold .segment-bar {
  color: var(--gold);
}
.ember .segment-bar {
  color: var(--ember);
}
.teal .segment-bar {
  color: var(--teal);
}
.cyan .segment-bar {
  color: var(--cyan);
}

.segment-label {
  font-size: 0.76rem;
  font-weight: 600;
  line-height: 1.25;
  color: var(--ink);
}

.segment-range {
  font-family: var(--font-mono);
  font-size: 0.54rem;
  letter-spacing: 0.03em;
  color: var(--gold);
}

.segment-note {
  margin-top: 2px;
  font-size: 0.64rem;
  line-height: 1.4;
  color: var(--dim);
}

.timeline-marker {
  position: absolute;
  top: 0;
  left: 77%;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 5px;
  transform: translateX(-50%);
  pointer-events: none;
}

.marker-pulse {
  position: relative;
  width: 9px;
  height: 9px;
  border-radius: 50%;
  background: var(--ember);
  box-shadow: 0 0 0 0 rgba(255, 122, 61, 0.45);
  animation: pulse 2.4s var(--ease-in-out) infinite;
}

.marker-label {
  font-family: var(--font-mono);
  font-size: 0.5rem;
  letter-spacing: 0.08em;
  color: var(--ember);
}

@keyframes pulse {
  0% {
    box-shadow: 0 0 0 0 rgba(255, 122, 61, 0.5);
  }
  70% {
    box-shadow: 0 0 0 12px rgba(255, 122, 61, 0);
  }
  100% {
    box-shadow: 0 0 0 0 rgba(255, 122, 61, 0);
  }
}

.timeline-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 10px 22px;
  padding-top: 12px;
  border-top: 1px solid var(--line);
  font-family: var(--font-mono);
  font-size: 0.54rem;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: var(--dim);
}

.timeline-legend span {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
}

.dot.gold {
  background: var(--gold);
}
.dot.ember {
  background: var(--ember);
}
.dot.teal {
  background: var(--teal);
}
.dot.cyan {
  background: var(--cyan);
}

@media (max-width: 900px) {
  .timeline-track {
    flex-direction: column;
    gap: 6px;
    min-height: 0;
  }
  .timeline-progress {
    display: none;
  }
  .timeline-segment {
    padding: 10px 12px;
  }
  .segment-bar {
    position: static;
    width: 22px;
    height: 3px;
    margin-bottom: 4px;
  }
  .segment-note {
    display: none;
  }
  .timeline-marker {
    display: none;
  }
}
</style>
