<script setup lang="ts">
defineProps<{
  scrolled: boolean
  progress: number
}>()

const emit = defineEmits<{ navigate: [id: string] }>()
</script>

<template>
  <div class="progress-line" :style="{ '--progress': `${progress}%` }" aria-hidden="true"></div>

  <header class="topbar" :class="{ 'is-scrolled': scrolled }">
    <div class="shell topbar-inner">
      <a class="brand" href="#top" @click.prevent="emit('navigate', 'top')">
      <span class="brand-mark" aria-hidden="true">
        <svg viewBox="0 0 32 32" fill="none">
          <circle cx="16" cy="16" r="13" stroke="rgba(244,241,232,.22)" stroke-width=".8" />
          <path
            d="M16 5.5c3.2 4.2 4.8 7.2 4.8 10.1 0 3.1-2.1 5.4-4.8 5.4s-4.8-2.3-4.8-5.4c0-1.5.6-2.9 1.8-4.4.2 1.3.9 2.2 1.8 2.6-.4-3 .2-5.6 1.2-8.3Z"
            fill="url(#flame)"
          />
          <circle cx="16" cy="23.8" r="2.2" fill="#ffc46b" opacity=".85" />
          <defs>
            <linearGradient id="flame" x1="12" y1="6" x2="21" y2="21" gradientUnits="userSpaceOnUse">
              <stop stop-color="#ffe0a3" />
              <stop offset=".5" stop-color="#ff9e53" />
              <stop offset="1" stop-color="#e24e1b" />
            </linearGradient>
          </defs>
        </svg>
      </span>
      <span>
        <span class="brand-name">FirePulse</span>
        <span class="brand-sub">One fire history</span>
      </span>
    </a>

    <div class="topbar-actions">
      <a class="topbar-link" href="#problem" @click.prevent="emit('navigate', 'problem')">Le problème</a>
      <a class="topbar-link" href="#proof" @click.prevent="emit('navigate', 'proof')">La preuve</a>
      <a class="topbar-link" href="#explorer" @click.prevent="emit('navigate', 'explorer')">Explorer</a>
      <a class="btn btn-ghost btn-small" href="#calendar" @click.prevent="emit('navigate', 'calendar')">
        Voir le calendrier
      </a>
      </div>
    </div>
  </header>
</template>
