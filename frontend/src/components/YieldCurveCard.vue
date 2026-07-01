<template>
  <div class="card mt-4">
    <!-- Header -->
    <div class="flex items-center gap-3 mb-3">
      <label class="flex items-center gap-2 cursor-pointer select-none">
        <div class="relative w-9 h-5">
          <input type="checkbox" class="sr-only" :checked="store.yieldCurve.enabled"
            @change="store.yieldCurve.enabled = !store.yieldCurve.enabled" />
          <div class="w-9 h-5 rounded-full transition-colors"
            :class="store.yieldCurve.enabled ? 'bg-blue-600' : 'bg-slate-700'"></div>
          <div class="absolute top-0.5 left-0.5 w-4 h-4 bg-white rounded-full shadow transition-transform"
            :class="store.yieldCurve.enabled ? 'translate-x-4' : 'translate-x-0'"></div>
        </div>
        <span class="text-xs font-bold text-slate-400 uppercase tracking-wider">Courbe de taux</span>
      </label>

      <!-- Key rates chips (shown when enabled) -->
      <template v-if="store.yieldCurve.enabled">
        <div class="ml-auto flex gap-1.5">
          <span v-for="k in keyRates" :key="k.label"
            class="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full bg-slate-800 border border-slate-700">
            <span class="text-slate-500">{{ k.label }}</span>
            <span class="text-blue-400 font-mono font-semibold"><SensitiveValue>{{ k.rate.toFixed(2) }}%</SensitiveValue></span>
          </span>
        </div>
      </template>

      <!-- Flat rate info when disabled -->
      <span v-else class="ml-auto text-xs text-slate-600">
        Taux plat r&nbsp;=&nbsp;<span class="text-slate-400"><SensitiveValue>{{ store.globalParams.r }}%</SensitiveValue></span>
      </span>
    </div>

    <template v-if="store.yieldCurve.enabled">
      <!-- Scenario presets -->
      <div class="flex gap-1.5 mb-3 flex-wrap">
        <button v-for="s in SCENARIOS" :key="s.label"
          @click="applyScenario(s)"
          class="text-xs px-2.5 py-1 rounded border transition-colors hover:border-blue-500 hover:text-blue-400"
          :class="activeScenario === s.label
            ? 'bg-blue-600/20 border-blue-500 text-blue-400'
            : 'bg-slate-800 border-slate-700 text-slate-400'">
          {{ s.label }}
        </button>
      </div>

      <!-- 11 pillar inputs -->
      <div class="grid grid-cols-11 gap-1 mb-3">
        <div v-for="p in store.yieldCurve.pillars" :key="p.label"
          class="flex flex-col items-center gap-0.5">
          <label class="text-xs text-slate-600 leading-none">{{ p.label }}</label>
          <SensitiveValue mode="input" placeholder="••">
            <div class="relative w-full">
              <input type="number" step="0.05" min="0" max="20"
                :value="p.rate"
                @input="onPillarInput(p, $event); activeScenario = null"
                class="w-full text-center text-xs bg-slate-900 border border-slate-700 rounded
                       px-0 py-1 text-slate-200 focus:border-blue-500 focus:outline-none"
                style="padding-right:10px" />
              <span class="absolute right-0.5 top-1/2 -translate-y-1/2 text-slate-600 text-xs pointer-events-none">%</span>
            </div>
          </SensitiveValue>
        </div>
      </div>

      <!-- Yield curve chart -->
      <SensitiveChart>
        <div style="height:88px;position:relative;">
          <canvas ref="ycCanvas"></canvas>
        </div>
      </SensitiveChart>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, watch, nextTick, onMounted, onUnmounted } from 'vue'
import { usePricingStore } from '../stores/pricing.js'
import { useDemoModeStore } from '../stores/demoMode.js'
import { demoChartOptions } from '../composables/useSensitiveChart.js'
import SensitiveValue from './SensitiveValue.vue'
import SensitiveChart from './SensitiveChart.vue'
import {
  Chart, LineElement, LineController, PointElement,
  LinearScale, Filler, Tooltip,
} from 'chart.js'

Chart.register(LineElement, LineController, PointElement, LinearScale, Filler, Tooltip)

const store = usePricingStore()
const demo = useDemoModeStore()
const ycCanvas = ref(null)
let ycChart = null
const activeScenario = ref('Normale')

const SCENARIOS = [
  {
    label: 'Normale',
    rates: [3.10, 3.30, 3.55, 3.80, 3.95, 4.10, 4.20, 4.30, 4.35, 4.40, 4.45],
  },
  {
    label: 'Inversée',
    rates: [4.80, 4.60, 4.30, 4.00, 3.80, 3.55, 3.40, 3.25, 3.15, 3.05, 2.95],
  },
  {
    label: 'Plate',
    rates: [3.75, 3.80, 3.85, 3.85, 3.85, 3.85, 3.85, 3.85, 3.85, 3.85, 3.85],
  },
  {
    label: 'Bosse',
    rates: [3.20, 3.60, 4.10, 4.50, 4.65, 4.60, 4.45, 4.25, 4.05, 3.90, 3.75],
  },
  {
    label: 'US 2024',
    rates: [5.30, 5.20, 4.95, 4.60, 4.40, 4.25, 4.20, 4.18, 4.20, 4.22, 4.25],
  },
]

const keyRates = computed(() => {
  const ps = store.yieldCurve.pillars
  return ['1Y', '5Y', '10Y', '30Y'].map(lbl => ({
    label: lbl,
    rate: ps.find(p => p.label === lbl)?.rate ?? 0,
  }))
})

function applyScenario(s) {
  s.rates.forEach((r, i) => {
    if (store.yieldCurve.pillars[i]) store.yieldCurve.pillars[i].rate = r
  })
  activeScenario.value = s.label
}

function onPillarInput(p, evt) {
  const v = parseFloat(evt.target.value)
  if (!isNaN(v)) p.rate = Math.max(0, Math.min(20, v))
}

async function renderChart() {
  if (!store.yieldCurve.enabled) {
    if (ycChart) { ycChart.destroy(); ycChart = null }
    return
  }
  await nextTick()
  await new Promise(r => requestAnimationFrame(r))
  if (!ycCanvas.value) return
  if (ycChart) { ycChart.destroy(); ycChart = null }

  const pillars = store.yieldCurve.pillars
  const Ts   = pillars.map(p => p.T)
  const data = pillars.map(p => ({ x: p.T, y: p.rate }))

  ycChart = new Chart(ycCanvas.value, {
    type: 'line',
    data: {
      datasets: [{
        data,
        borderColor: '#3b82f6',
        backgroundColor: 'rgba(59,130,246,0.07)',
        borderWidth: 1.8,
        pointRadius: 3,
        pointBackgroundColor: '#3b82f6',
        tension: 0.35,
        fill: true,
      }],
    },
    options: demoChartOptions({
      responsive: true, maintainAspectRatio: false,
      animation: { duration: 80 },
      parsing: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: { label: it => `${it.raw.y.toFixed(2)}% @ ${it.raw.x}Y` },
        },
      },
      scales: {
        x: {
          type: 'linear', min: 0, max: 30,
          ticks: { color: '#475569', font: { size: 8 }, callback: v => v + 'Y',
                   values: [0.25, 0.5, 1, 2, 3, 5, 7, 10, 15, 20, 30] },
          grid: { color: '#1e293b' },
        },
        y: {
          ticks: { color: '#475569', font: { size: 8 }, callback: v => v + '%' },
          grid: { color: '#1e293b' },
        },
      },
    }, demo.enabled),
  })
}

const chartKey = computed(() => {
  if (!store.yieldCurve.enabled) return null
  return store.yieldCurve.pillars.map(p => p.rate).join(',')
})

watch(chartKey, renderChart)
watch(() => store.yieldCurve.enabled, v => { if (v) renderChart() })
watch(() => demo.enabled, renderChart)
onMounted(() => { if (store.yieldCurve.enabled) renderChart() })
onUnmounted(() => { if (ycChart) ycChart.destroy() })
</script>
