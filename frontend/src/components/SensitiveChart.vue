<!--
  Wraps a chart canvas to add the small "DEMO" corner badge required by the
  demo-mode visual layer (req. 7). The actual hiding of axis ticks/tooltips
  happens in each chart's own Chart.js options via demoChartOptions() (see
  composables/useSensitiveChart.js) — that's imperative chart construction,
  this component only adds the decorative overlay, it doesn't touch the
  chart itself.
-->
<template>
  <div class="relative">
    <slot />
    <div v-if="demo.enabled" class="sv-chart-badge">DEMO</div>
  </div>
</template>

<script setup>
import { useDemoModeStore } from '../stores/demoMode.js'
const demo = useDemoModeStore()
</script>

<style scoped>
.sv-chart-badge {
  position: absolute;
  top: 4px;
  right: 4px;
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 0.08em;
  color: rgba(148, 163, 184, 0.6);
  background: rgba(15, 23, 42, 0.6);
  border: 1px solid rgba(100, 116, 139, 0.4);
  border-radius: 4px;
  padding: 1px 5px;
  pointer-events: none;
  user-select: none;
}
</style>
