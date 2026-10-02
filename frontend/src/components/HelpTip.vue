<template>
  <span
    ref="triggerEl"
    class="relative inline-flex items-center justify-center w-3.5 h-3.5 rounded-full bg-slate-700 text-slate-300 text-[9px] font-bold cursor-help align-middle"
    role="button" tabindex="0" aria-label="Afficher l’explication" :aria-expanded="visible" :aria-describedby="visible ? tooltipId : undefined"
    @mouseenter="show" @mouseleave="leave" @focus="show" @blur="hide"
    @click.stop.prevent="show" @keydown.enter.stop.prevent="toggle" @keydown.space.stop.prevent="toggle" @keydown.esc.stop="hide"
  >?</span>
  <Teleport to="body">
    <div v-if="visible" ref="panelEl" :id="tooltipId" role="tooltip"
      class="fixed pointer-events-none bg-slate-900 border border-slate-700 text-slate-300 text-xs leading-relaxed rounded-lg p-2.5 z-[9999] shadow-2xl whitespace-normal text-left font-normal normal-case tracking-normal"
      :class="width"
      :style="panelStyle"
    ><slot>{{ text }}</slot></div>
  </Teleport>
</template>

<script setup>
import { ref, nextTick, watch, onBeforeUnmount, getCurrentInstance } from 'vue'

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
const panelEl = ref(null)
const tooltipId = `help-tip-${getCurrentInstance().uid}`
const panelStyle = ref({})

async function show() {
  visible.value = true
  await nextTick()
  if (!visible.value || !triggerEl.value || !panelEl.value) return
  const r = triggerEl.value.getBoundingClientRect()
  const p = panelEl.value.getBoundingClientRect()
  const margin = 8
  const left = props.align === 'right' ? r.right - p.width : r.left
  const top = r.top >= p.height + margin ? r.top - p.height - margin : r.bottom + margin
  panelStyle.value = {
    left: `${Math.max(margin, Math.min(left, window.innerWidth - p.width - margin))}px`,
    top: `${Math.max(margin, Math.min(top, window.innerHeight - p.height - margin))}px`,
    maxWidth: 'calc(100vw - 16px)',
  }
}
function hide() { visible.value = false }
function leave() { if (document.activeElement !== triggerEl.value) hide() }
function toggle() { visible.value ? hide() : show() }
function removeListeners() {
  window.removeEventListener('scroll', hide, true)
  window.removeEventListener('resize', hide)
}
watch(visible, open => {
  removeListeners()
  if (open) {
    window.addEventListener('scroll', hide, true)
    window.addEventListener('resize', hide)
  }
})
onBeforeUnmount(removeListeners)
</script>
