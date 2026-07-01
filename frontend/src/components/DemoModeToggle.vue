<!--
  Global demo-mode control, dropped into the app header so it's reachable
  from anywhere: a switch (req. 1), the "DEMO MODE" visual layer (req. 7),
  and the "Préparer pour LinkedIn" bonus button (req. 11).
-->
<template>
  <div class="flex items-center gap-2">
    <span v-if="demo.enabled" class="demo-banner" :class="{ 'demo-banner-linkedin': demo.linkedinMode }">
      {{ demo.linkedinMode ? 'PUBLIC DEMONSTRATION VERSION' : 'DEMO MODE' }}
    </span>

    <button
      class="btn-secondary text-xs px-2 py-1"
      title="Active le mode démo et réduit les détails techniques affichés — prêt pour une capture LinkedIn"
      @click="demo.prepareForLinkedIn()">
      📤 LinkedIn
    </button>

    <label class="demo-switch" title="Mode démonstration — masque prix, paramètres, Greeks et identités des sous-jacents">
      <input type="checkbox" :checked="demo.enabled" class="sr-only" @change="demo.toggle()" />
      <span class="demo-switch-track" :class="{ 'demo-switch-track-on': demo.enabled }">
        <span class="demo-switch-thumb" :class="{ 'demo-switch-thumb-on': demo.enabled }"></span>
      </span>
      <span class="text-xs font-semibold" :class="demo.enabled ? 'text-amber-400' : 'text-slate-500'">
        Mode Démo
      </span>
    </label>
  </div>
</template>

<script setup>
import { useDemoModeStore } from '../stores/demoMode.js'
const demo = useDemoModeStore()
</script>

<style scoped>
.demo-banner {
  font-size: 10px;
  font-weight: 800;
  letter-spacing: 0.1em;
  color: #fbbf24;
  background: rgba(120, 53, 15, 0.4);
  border: 1px solid rgba(217, 119, 6, 0.5);
  border-radius: 5px;
  padding: 3px 8px;
  white-space: nowrap;
  animation: demo-pulse 2.5s ease-in-out infinite;
}
.demo-banner-linkedin {
  color: #38bdf8;
  background: rgba(7, 89, 133, 0.4);
  border-color: rgba(14, 165, 233, 0.5);
}
@keyframes demo-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.6; }
}

.demo-switch {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  user-select: none;
}
.demo-switch-track {
  width: 30px;
  height: 16px;
  border-radius: 999px;
  background: #334155;
  border: 1px solid #475569;
  position: relative;
  transition: background-color 0.15s ease;
  flex-shrink: 0;
}
.demo-switch-track-on {
  background: #b45309;
  border-color: #d97706;
}
.demo-switch-thumb {
  position: absolute;
  top: 1px;
  left: 1px;
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: #cbd5e1;
  transition: transform 0.15s ease;
}
.demo-switch-thumb-on {
  transform: translateX(14px);
  background: #fef3c7;
}
</style>
