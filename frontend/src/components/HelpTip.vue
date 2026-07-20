<template>
  <span
    ref="triggerEl"
    class="relative inline-flex items-center justify-center w-3.5 h-3.5 rounded-full bg-slate-700 text-slate-300 text-[9px] font-bold cursor-help align-middle"
    @mouseenter="show" @mouseleave="hide"
  >?</span>
  <Teleport to="body">
    <div v-if="visible"
      class="fixed pointer-events-none bg-slate-900 border border-slate-700 text-slate-300 text-[10px] leading-relaxed rounded-lg p-2.5 z-[9999] shadow-2xl whitespace-normal text-left font-normal normal-case tracking-normal"
      :class="width"
      :style="panelStyle"
    ><slot>{{ text }}</slot></div>
  </Teleport>
</template>

<script setup>
import { ref, computed } from 'vue'

const props = defineProps({
  text: { type: String, default: '' },
  width: { type: String, default: 'w-64' },   // tailwind width class — literal so JIT scanning still finds it at call sites
  align: { type: String, default: 'left' },   // 'left' | 'right' — which edge the panel hangs from
})

// Teleported to <body> and positioned via getBoundingClientRect(), not CSS
// absolute+group-hover — the badge sits inside several overflow-x-auto
// table containers, which per the CSS spec also clip the vertical axis,
// silently cutting off any absolutely-positioned popover that tries to
// escape upward. Fixed positioning computed fresh on each hover sidesteps
// that entirely, regardless of which scrollable ancestor the badge is in.
const triggerEl = ref(null)
const visible = ref(false)
const anchor = ref({ top: 0, left: 0, right: 0 })

function show() {
  const r = triggerEl.value.getBoundingClientRect()
  anchor.value = { top: r.top, left: r.left, right: window.innerWidth - r.right }
  visible.value = true
}
function hide() {
  visible.value = false
}

const panelStyle = computed(() => {
  const style = { bottom: `${window.innerHeight - anchor.value.top + 6}px` }
  if (props.align === 'right') style.right = `${anchor.value.right}px`
  else style.left = `${anchor.value.left}px`
  return style
})
</script>
