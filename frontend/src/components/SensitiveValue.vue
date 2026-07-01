<!--
  Drop-in wrapper for any value that shouldn't appear in a shared screenshot
  or public demo: prices, Greeks, vols, seeds, param values, etc.

    Demo OFF -> <SensitiveValue>{{ price }}%</SensitiveValue>  renders 97.96%
    Demo ON  -> same markup                                    renders ••••••

  Pure presentation: never touches the underlying value, so nothing else in
  the app needs to know demo mode exists.

  mode="mask"  (default) — replaces the slot entirely with a placeholder.
  mode="input" — for an editable <input>/<select> in the slot: shows a
                 read-only block styled like the app's .input class instead,
                 so editable param/market fields look masked-but-native
                 rather than vanishing or staying live (demo capture isn't a
                 live-editing moment — toggle off, adjust, toggle back on).
  mode="blur"  — keeps the slot's shape on screen (layout, chart, code) but
                 makes it illegible via a CSS blur. Use this where hiding the
                 element entirely would look broken (e.g. the script editor).
-->
<template>
  <template v-if="!demo.enabled"><slot /></template>
  <span v-else-if="mode === 'mask'" class="sv-mask" :title="label || 'Masqué — Mode démo'">{{ placeholder }}</span>
  <div v-else-if="mode === 'input'" class="input sv-input-mask" :title="label || 'Masqué — Mode démo'">{{ placeholder }}</div>
  <div v-else class="sv-blur"><slot /></div>
</template>

<script setup>
import { useDemoModeStore } from '../stores/demoMode.js'

defineProps({
  mode: { type: String, default: 'mask' },        // 'mask' | 'blur'
  placeholder: { type: String, default: '••••••' },
  label: { type: String, default: '' },
})

const demo = useDemoModeStore()
</script>

<style scoped>
.sv-mask {
  font-family: ui-monospace, monospace;
  letter-spacing: 0.05em;
  opacity: 0.65;
  user-select: none;
}
.sv-blur {
  filter: blur(6px);
  user-select: none;
  pointer-events: none;
}
.sv-input-mask {
  display: flex;
  align-items: center;
  background: rgba(30, 41, 59, 0.4);
  color: #64748b;
  cursor: not-allowed;
  user-select: none;
  font-family: ui-monospace, monospace;
  letter-spacing: 0.05em;
}
</style>
