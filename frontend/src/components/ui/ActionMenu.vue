<template>
  <details class="action-menu">
    <summary class="btn-secondary action-menu__trigger" :title="title">
      <span class="action-menu__label">{{ label }}</span>
      <span class="action-menu__chevron" aria-hidden="true">▾</span>
    </summary>
    <div class="action-menu__panel"><slot /></div>
  </details>
</template>

<script setup>
defineProps({ label: { type: String, required: true }, title: String })
</script>

<style scoped>
.action-menu { min-width: 0; max-width: 100%; width: fit-content; }
.action-menu__trigger {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: .5rem;
  min-height: 2rem;
  padding: .375rem .65rem;
  font-size: .75rem;
  line-height: 1.4;
  list-style: none;
  cursor: pointer;
}
.action-menu__trigger::-webkit-details-marker { display: none; }
.action-menu__label { min-width: 0; white-space: normal; overflow-wrap: anywhere; }
.action-menu__chevron { flex: 0 0 auto; }
/* Keep options in flow: scrollable table/card ancestors must not clip them. */
.action-menu__panel {
  display: flex;
  flex-direction: column;
  gap: .25rem;
  margin-top: .375rem;
  padding: .5rem;
  border: 1px solid var(--border);
  border-radius: .5rem;
  background: var(--surface);
  box-shadow: var(--shadow-sm);
  overflow-wrap: anywhere;
}
</style>
