<!--
  Modale générique — remplace les overlays "fixed inset-0" ad-hoc dispersés
  dans les vues. Fermeture : Escape, clic sur le fond, ou bouton ✕.
  Le focus est piégé à l'intérieur tant que la modale est ouverte.
-->
<template>
  <Teleport to="body">
    <Transition name="modal">
      <div v-if="modelValue" class="modal-overlay" @mousedown.self="close" @keydown.esc="close">
        <div ref="panelEl" class="modal-panel" :style="{ maxWidth: maxWidth }"
             role="dialog" aria-modal="true" :aria-label="title" tabindex="-1" @keydown.tab="onTab">
          <div v-if="title" class="modal-header">
            <h2 class="modal-title">{{ title }}</h2>
            <button class="modal-close" aria-label="Fermer" @click="close">✕</button>
          </div>
          <div class="modal-body">
            <slot />
          </div>
          <div v-if="$slots.footer" class="modal-footer">
            <slot name="footer" />
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup>
import { ref, watch, nextTick } from 'vue'

const props = defineProps({
  modelValue: { type: Boolean, required: true },
  title: { type: String, default: '' },
  maxWidth: { type: String, default: '420px' },
})
const emit = defineEmits(['update:modelValue', 'close'])

const panelEl = ref(null)

function close() {
  emit('update:modelValue', false)
  emit('close')
}

function focusableEls() {
  if (!panelEl.value) return []
  return [...panelEl.value.querySelectorAll(
    'a[href], button:not([disabled]), textarea, input, select, [tabindex]:not([tabindex="-1"])'
  )]
}

function onTab(e) {
  const els = focusableEls()
  if (!els.length) return
  const first = els[0]
  const last = els[els.length - 1]
  if (e.shiftKey && document.activeElement === first) {
    e.preventDefault(); last.focus()
  } else if (!e.shiftKey && document.activeElement === last) {
    e.preventDefault(); first.focus()
  }
}

watch(() => props.modelValue, async (open) => {
  if (!open) return
  await nextTick()
  const els = focusableEls()
  ;(els[0] || panelEl.value)?.focus()
})
</script>

<style scoped>
.modal-overlay {
  position: fixed;
  inset: 0;
  z-index: 60;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 1rem;
  background: rgba(20, 18, 14, .55);
  backdrop-filter: blur(4px);
}
.modal-panel {
  width: 100%;
  background: var(--surface);
  border: 1px solid var(--border2);
  border-radius: var(--radius);
  box-shadow: var(--shadow-lg);
  padding: 1.5rem;
  max-height: 88vh;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 1rem;
}
.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
}
.modal-title {
  font-family: 'Fraunces', serif;
  font-weight: 700;
  font-size: 1.1rem;
  color: var(--text);
}
.modal-close {
  flex-shrink: 0;
  width: 28px;
  height: 28px;
  border-radius: 8px;
  background: var(--surface2);
  border: 1px solid var(--border);
  color: var(--muted);
  font-size: .8rem;
  transition: all .15s;
}
.modal-close:hover { background: var(--negative-light); border-color: var(--negative); color: var(--negative); }
.modal-footer { display: flex; gap: .5rem; justify-content: flex-end; }

.modal-enter-active, .modal-leave-active { transition: opacity .18s ease; }
.modal-enter-from, .modal-leave-to { opacity: 0; }
.modal-enter-active .modal-panel, .modal-leave-active .modal-panel { transition: transform .18s ease, opacity .18s ease; }
.modal-enter-from .modal-panel, .modal-leave-to .modal-panel { transform: scale(.96) translateY(6px); opacity: 0; }

@media (prefers-reduced-motion: reduce) {
  .modal-enter-active, .modal-leave-active,
  .modal-enter-active .modal-panel, .modal-leave-active .modal-panel { transition: opacity 1ms linear; }
  .modal-enter-from .modal-panel, .modal-leave-to .modal-panel { transform: none; }
}
</style>
