<script setup lang="ts">
import { computed, nextTick, onMounted, ref, useTemplateRef } from 'vue'
import { gsap, ScrollTrigger } from '@/lib/motion'
import { formatCount } from '@/lib/data'
import { provenance } from '@/lib/provenance'

const props = withDefaults(
  defineProps<{
    share: number
    staticCount: number
    totalCount: number
    reducedMotion?: boolean
  }>(),
  { reducedMotion: false },
)

const filtered = ref(false)
const wrapper = useTemplateRef<HTMLDivElement>('wrapper')
const staticCount = Math.round((props.share / 100) * 100)

// 21 points cyan répartis de façon déterministe parmi les 100 points.
const staticFlags = Array.from(
  { length: 100 },
  (_, index) => (index * 37 + 11) % 100 < staticCount,
)

const removed = computed(() => (filtered.value ? 0 : props.staticCount))
const visibleShare = computed(() => (filtered.value ? 0 : props.share))

onMounted(async () => {
  if (props.reducedMotion) return
  await nextTick()
  const dots = wrapper.value?.querySelectorAll('.dot.cool')
  if (!dots?.length) return
  gsap.from(dots, {
    opacity: 0,
    scale: 0.4,
    duration: 0.45,
    ease: 'back.out(1.7)',
    stagger: { each: 0.008, from: 'random' },
    immediateRender: false,
    scrollTrigger: { trigger: wrapper.value, start: 'top 82%', once: true },
  })
  ScrollTrigger.refresh()
})
</script>

<template>
  <div ref="wrapper" class="flare">
    <div class="flare-top">
      <div class="flare-number">
        <span class="stat">{{ visibleShare.toFixed(1).replace('.', ',') }}<small>%</small></span>
        <span class="flare-caption">des détections VIIRS S-NPP<br />sont des sources statiques</span>
      </div>
      <button
        type="button"
        class="flare-toggle"
        :class="{ active: filtered }"
        :aria-pressed="filtered"
        @click="filtered = !filtered"
      >
        <span class="flare-toggle-track"><i></i></span>
        {{ filtered ? 'Torchères retirées' : 'Retirer les torchères' }}
      </button>
    </div>

    <div class="dot-grid" :class="{ filtered }" aria-hidden="true">
      <span
        v-for="n in 100"
        :key="n"
        class="dot"
        :class="staticFlags[n - 1] ? 'cool' : 'hot'"
        :style="{ transitionDelay: `${(n % 10) * 18}ms` }"
      ></span>
    </div>

    <div class="flare-legend">
      <span class="legend-item">
        <i class="swatch hot"></i>
        Feux de végétation
        <strong>{{ formatCount(totalCount - removed) }}</strong>
      </span>
      <span class="legend-item">
        <i class="swatch cool"></i>
        Sources statiques
        <strong>{{ formatCount(removed) }}</strong>
      </span>
    </div>

    <p class="flare-note">
      Le type FIRMS ne suffit pas : en 2017, MODIS n'a signalé aucune source type 2 au Gabon.
      D'où un masque spatial de
      {{ String(provenance.staticGridDeg).replace('.', ',') }}° basé sur la persistance, appliqué
      à tous les capteurs.
    </p>
  </div>
</template>

<style scoped>
.flare {
  display: grid;
  gap: 22px;
}

.flare-top {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  justify-content: space-between;
  gap: 18px;
}

.flare-number {
  display: flex;
  align-items: flex-end;
  gap: 18px;
}

.flare-number .stat small {
  font-size: 0.42em;
  color: var(--gold);
}

.flare-caption {
  max-width: 220px;
  padding-bottom: 8px;
  font-size: 0.76rem;
  line-height: 1.45;
  color: var(--muted);
}

.flare-toggle {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  border: 1px solid var(--line-strong);
  border-radius: 999px;
  background: transparent;
  color: var(--muted);
  font-family: var(--font-mono);
  font-size: 0.58rem;
  letter-spacing: 0.04em;
  cursor: pointer;
  transition:
    color 0.25s ease,
    border-color 0.25s ease,
    background 0.25s ease;
}

.flare-toggle:hover,
.flare-toggle.active {
  color: var(--ink);
  border-color: rgba(255, 196, 107, 0.45);
  background: rgba(255, 196, 107, 0.06);
}

.flare-toggle-track {
  display: inline-flex;
  align-items: center;
  width: 28px;
  height: 15px;
  padding: 2px;
  border-radius: 999px;
  background: rgba(244, 241, 232, 0.14);
  transition: background 0.25s ease;
}

.flare-toggle-track i {
  width: 11px;
  height: 11px;
  border-radius: 50%;
  background: var(--muted);
  transition:
    transform 0.25s var(--ease-out),
    background 0.25s ease;
}

.flare-toggle.active .flare-toggle-track {
  background: rgba(34, 211, 238, 0.24);
}

.flare-toggle.active .flare-toggle-track i {
  transform: translateX(13px);
  background: var(--cyan);
  box-shadow: 0 0 8px var(--cyan);
}

.dot-grid {
  display: grid;
  grid-template-columns: repeat(20, minmax(0, 1fr));
  gap: 5px;
  max-width: 520px;
}

.dot {
  aspect-ratio: 1;
  border-radius: 50%;
  transition:
    opacity 0.5s ease,
    transform 0.5s var(--ease-out),
    background 0.5s ease;
}

.dot.hot {
  background: rgba(255, 122, 61, 0.72);
  box-shadow: 0 0 6px rgba(255, 94, 26, 0.22);
}

.dot.cool {
  background: rgba(34, 211, 238, 0.8);
  box-shadow: 0 0 7px rgba(34, 211, 238, 0.4);
}

.dot-grid.filtered .dot.cool {
  opacity: 0.12;
  transform: scale(0.55);
  background: rgba(244, 241, 232, 0.3);
  box-shadow: none;
}

.flare-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 12px 26px;
  padding-top: 14px;
  border-top: 1px solid var(--line);
}

.legend-item {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 0.7rem;
  color: var(--muted);
}

.legend-item strong {
  margin-left: 4px;
  font-family: var(--font-mono);
  font-size: 0.68rem;
  color: var(--ink);
  font-weight: 500;
}

.swatch {
  width: 7px;
  height: 7px;
  border-radius: 50%;
}

.swatch.hot {
  background: var(--ember);
}

.swatch.cool {
  background: var(--cyan);
  box-shadow: 0 0 7px rgba(34, 211, 238, 0.5);
}

.flare-note {
  font-size: 0.7rem;
  line-height: 1.6;
  color: var(--dim);
  max-width: 62ch;
}

@media (max-width: 640px) {
  .dot-grid {
    grid-template-columns: repeat(10, minmax(0, 1fr));
  }
  .flare-number {
    align-items: flex-start;
    flex-direction: column;
    gap: 6px;
  }
  .flare-caption {
    padding-bottom: 0;
  }
}
</style>
