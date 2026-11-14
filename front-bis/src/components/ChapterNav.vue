<script setup lang="ts">
defineProps<{
  chapters: { id: string; label: string }[]
  active: string
}>()

const emit = defineEmits<{ navigate: [id: string] }>()
</script>

<template>
  <nav class="chapter-nav" aria-label="Chapitres de l'histoire">
    <button
      v-for="chapter in chapters"
      :key="chapter.id"
      type="button"
      :class="{ 'is-active': active === chapter.id }"
      :aria-label="chapter.label"
      :aria-current="active === chapter.id ? 'step' : undefined"
      @click="emit('navigate', chapter.id)"
    >
      <span class="nav-label">{{ chapter.label }}</span>
      <span class="nav-dot"></span>
    </button>
  </nav>
</template>
