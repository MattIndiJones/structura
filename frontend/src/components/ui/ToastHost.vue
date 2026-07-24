<!--
  Hôte de notifications global — monté une seule fois dans App.vue.
  Empile les toasts en bas à droite, façon italian_app.
-->
<template>
  <Teleport to="body">
    <div class="toast-host" role="status" aria-live="polite">
      <TransitionGroup name="toast">
        <div v-for="t in toasts.items" :key="t.id" class="toast-item" :class="`toast-${t.kind}`">
          <span class="toast-icon">{{ icon(t.kind) }}</span>
          <span class="toast-text">{{ t.text }}</span>
          <button class="toast-close" aria-label="Fermer" @click="toasts.dismiss(t.id)">✕</button>
        </div>
      </TransitionGroup>
    </div>
  </Teleport>
</template>

<script setup>
import { useToastsStore } from '../../stores/toasts.js'

const toasts = useToastsStore()

function icon(kind) {
  return { success: '✓', error: '✕', warning: '⚠', info: 'ℹ' }[kind] || 'ℹ'
}
</script>

<style scoped>
.toast-host {
  position: fixed;
  bottom: 1.5rem;
  right: 1.5rem;
  z-index: 100;
  display: flex;
  flex-direction: column;
  gap: .5rem;
  max-width: 360px;
}
.toast-item {
  display: flex;
  align-items: center;
  gap: .6rem;
  background: var(--surface);
  border: 1.5px solid var(--border2);
  border-radius: var(--radius-sm);
  padding: .7rem 1rem;
  font-size: .8rem;
  font-weight: 600;
  color: var(--text);
  box-shadow: var(--shadow);
}
.toast-icon { flex-shrink: 0; font-weight: 800; }
.toast-text { flex: 1; min-width: 0; }
.toast-close {
  flex-shrink: 0;
  color: var(--subtle);
  font-size: .7rem;
  line-height: 1;
  padding: .2rem;
}
.toast-close:hover { color: var(--text); }

.toast-success { border-color: rgba(26, 122, 74, .35); }
.toast-success .toast-icon { color: var(--positive); }
.toast-error   { border-color: rgba(192, 57, 43, .35); }
.toast-error   .toast-icon { color: var(--negative); }
.toast-warning { border-color: rgba(184, 134, 11, .35); }
.toast-warning .toast-icon { color: var(--gold); }
.toast-info    .toast-icon { color: var(--accent); }

.toast-enter-active,
.toast-leave-active { transition: opacity .25s ease, transform .25s ease; }
.toast-enter-from,
.toast-leave-to { opacity: 0; transform: translateY(8px); }
.toast-leave-active { position: absolute; }

@media (prefers-reduced-motion: reduce) {
  .toast-enter-active,
  .toast-leave-active { transition: opacity 1ms linear; }
  .toast-enter-from,
  .toast-leave-to { transform: none; }
}
</style>
