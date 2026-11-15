<script setup lang="ts">
import { locale, setLocale, t } from '@/lib/i18n'

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
          <span class="brand-sub">{{ t('Gabon · 2000–2025', 'Gabon · 2000–2025') }}</span>
        </span>
      </a>

      <div class="topbar-actions">
        <a class="topbar-link" href="#problem" @click.prevent="emit('navigate', 'problem')">
          {{ t('Le piège', 'The trap') }}
        </a>
        <a class="topbar-link" href="#calendar" @click.prevent="emit('navigate', 'calendar')">
          {{ t('Le calendrier', 'Calendar') }}
        </a>
        <a class="topbar-link" href="#map" @click.prevent="emit('navigate', 'map')">
          {{ t('La carte', 'Map') }}
        </a>
        <a class="topbar-link" href="#proof" @click.prevent="emit('navigate', 'proof')">
          {{ t('La preuve', 'Proof') }}
        </a>

        <div
          class="lang-switch"
          role="group"
          :data-locale="locale"
          :title="t('Langue adaptée à votre région (cliquer pour changer)', 'Language matched to your region (click to switch)')"
          :aria-label="t('Langue', 'Language')"
        >
          <button
            type="button"
            class="lang-btn"
            :class="{ active: locale === 'fr' }"
            :aria-pressed="locale === 'fr'"
            @click="setLocale('fr')"
          >
            FR
          </button>
          <button
            type="button"
            class="lang-btn"
            :class="{ active: locale === 'en' }"
            :aria-pressed="locale === 'en'"
            @click="setLocale('en')"
          >
            EN
          </button>
        </div>

        <a class="btn btn-ghost btn-small" href="#calendar" @click.prevent="emit('navigate', 'calendar')">
          {{ t('Explorer le Gabon', 'Explore Gabon') }}
        </a>
      </div>
    </div>
  </header>
</template>
