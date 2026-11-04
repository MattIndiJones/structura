<template>
  <details v-if="wings?.length" class="my-2 text-xs text-amber-700">
    <summary class="cursor-pointer">Dupire · prolongement à 300 % dans les ailes extrêmes</summary>
    <ul class="mt-1 space-y-1">
      <li v-for="wing in wings" :key="wing.underlying_index + wing.side">
        <SensitiveValue>
          {{ wing.underlying }} · aile {{ wing.side === 'left' ? 'gauche' : 'droite' }} ·
          {{ wing.steps.length }} pas entre {{ formatNumber(wing.steps[0].t, 4) }}
          et {{ formatNumber(wing.steps.at(-1).t, 4) }} an ·
          borne du prolongement {{ formatPercent(boundary(wing) * 100, 1) }} du forward
        </SensitiveValue>
      </li>
    </ul>
  </details>
</template>

<script setup>
import SensitiveValue from './SensitiveValue.vue'
import { formatNumber, formatPercent } from '../utils/format.js'

defineProps({ wings: Array })

function boundary(wing) {
  const levels = wing.steps.map(step => step.boundary_forward)
  return wing.side === 'left' ? Math.max(...levels) : Math.min(...levels)
}
</script>
