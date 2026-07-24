<!--
  État vide standard — remplace les cartes pointillées / emoji ad-hoc.
  Slot par défaut : contenu libre pour un CTA (bouton, lien…).
-->
<template>
  <div class="empty-state">
    <div class="empty-icon">{{ icon }}</div>
    <div class="empty-title">{{ title }}</div>
    <p v-if="hint" class="empty-hint">{{ hint }}</p>
    <div v-if="$slots.default" class="empty-cta">
      <slot />
    </div>
  </div>
</template>

<script setup>
defineProps({
  icon: { type: String, default: '📄' },
  title: { type: String, required: true },
  hint: { type: String, default: '' },
})
</script>

<style scoped>
.empty-state { text-align: center; padding: 3rem 1.5rem; }
.empty-icon { font-size: 2.4rem; opacity: .35; margin-bottom: .75rem; }
.empty-title { font-size: .9rem; font-weight: 600; color: var(--muted); }
.empty-hint { font-size: .8rem; color: var(--subtle); margin-top: .35rem; max-width: 32rem; margin-left: auto; margin-right: auto; }
.empty-cta { margin-top: 1rem; display: flex; justify-content: center; }
</style>
