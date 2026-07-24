<!--
  Indicateur de chargement standard — remplace les textes "Chargement…" nus
  et les divs animate-spin ad-hoc dispersés dans les vues.
-->
<template>
  <div class="loading-spinner" :class="inline ? 'loading-spinner-inline' : 'loading-spinner-block'">
    <span class="spinner" :style="{ width: size + 'px', height: size + 'px' }"></span>
    <span v-if="label" class="spinner-label">{{ label }}</span>
  </div>
</template>

<script setup>
defineProps({
  label: { type: String, default: 'Chargement…' },
  size: { type: Number, default: 16 },
  inline: { type: Boolean, default: false },
})
</script>

<style scoped>
.loading-spinner { display: flex; align-items: center; gap: .6rem; color: var(--muted); font-size: .8rem; }
.loading-spinner-block { justify-content: center; padding: 1.5rem; }
.loading-spinner-inline { display: inline-flex; }
.spinner {
  display: inline-block;
  border: 2px solid var(--border2);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: spinner-rotate .7s linear infinite;
  flex-shrink: 0;
}
@keyframes spinner-rotate { to { transform: rotate(360deg); } }
@media (prefers-reduced-motion: reduce) {
  .spinner { animation-duration: 1.6s; }
}
</style>
