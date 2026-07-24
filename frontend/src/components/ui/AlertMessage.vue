<!--
  Bandeau d'alerte inline — canonicalise les divs
  "bg-red-950/60 border-red-800 text-red-300" dispersés dans les vues.
-->
<template>
  <div class="alert-message" :class="`alert-${kind}`" role="alert">
    <span class="alert-icon">{{ icon }}</span>
    <span class="alert-text"><slot /></span>
    <button v-if="dismissible" class="alert-dismiss" aria-label="Fermer" @click="$emit('dismiss')">✕</button>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  kind: { type: String, default: 'error' }, // success | error | warning | info
  dismissible: { type: Boolean, default: false },
})
defineEmits(['dismiss'])

const icon = computed(() => ({ success: '✓', error: '⚠', warning: '⚠', info: 'ℹ' }[props.kind] || 'ℹ'))
</script>

<style scoped>
.alert-message {
  display: flex;
  align-items: flex-start;
  gap: .6rem;
  border-radius: var(--radius-sm);
  border: 1px solid;
  padding: .6rem .85rem;
  font-size: .8rem;
  line-height: 1.4;
}
.alert-icon { flex-shrink: 0; font-weight: 700; }
.alert-text { flex: 1; min-width: 0; }
.alert-dismiss { flex-shrink: 0; font-size: .7rem; opacity: .7; }
.alert-dismiss:hover { opacity: 1; }

.alert-success { background: var(--positive-light); border-color: rgba(26, 122, 74, .3); color: var(--positive); }
.alert-error   { background: var(--negative-light); border-color: rgba(192, 57, 43, .3); color: var(--negative); }
.alert-warning { background: var(--gold-light); border-color: rgba(184, 134, 11, .3); color: var(--gold); }
.alert-info    { background: var(--accent-light); border-color: rgba(26, 95, 160, .3); color: var(--accent); }
</style>
