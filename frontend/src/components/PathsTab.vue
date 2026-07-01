<template>
  <div class="flex flex-col gap-4">
    <!-- Header -->
    <div class="card">
      <div class="flex items-center gap-3 flex-wrap">
        <div>
          <div class="text-xs font-bold text-slate-400 uppercase tracking-wider">🔀 Chemins Monte Carlo</div>
          <div class="text-xs text-slate-600 mt-0.5 italic">50 chemins colorés par scénario de sortie</div>
        </div>
        <div class="ml-auto">
          <button class="btn-primary text-xs px-4" :disabled="store.loading" @click="store.runPaths()">
            <span v-if="store.loading" class="w-3 h-3 border border-white border-t-transparent rounded-full animate-spin inline-block mr-1"></span>
            ▶ Simuler
          </button>
        </div>
      </div>
    </div>

    <!-- Empty state -->
    <div v-if="!store.paths" class="flex flex-col items-center justify-center h-52 text-slate-600 gap-2">
      <div class="text-3xl">🔀</div>
      <div class="text-sm font-medium">Cliquez "Simuler" pour visualiser les chemins MC</div>
      <div class="text-xs">50 chemins · colorés par résultat (autocall / KI / normal)</div>
    </div>

    <!-- Chart -->
    <div v-else class="card">
      <SensitiveChart>
        <div style="height:340px;position:relative;">
          <canvas ref="chartCanvas"></canvas>
        </div>
      </SensitiveChart>
      <!-- Legend -->
      <div class="flex gap-4 flex-wrap mt-3 pt-3 border-t border-slate-800 text-xs">
        <span v-for="lg in legend" :key="lg.key" class="inline-flex items-center gap-1.5">
          <span class="w-4 h-0.5 inline-block rounded" :style="{ background: lg.solid }"></span>
          <span class="text-slate-400">{{ lg.label }}</span>
          <strong :style="{ color: lg.solid }"><SensitiveValue>{{ lg.pct }}%</SensitiveValue></strong>
          <span class="text-slate-600"><SensitiveValue>({{ lg.count }}/{{ store.paths.total }})</SensitiveValue></span>
        </span>
      </div>
    </div>
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
  LinearScale, Tooltip
} from 'chart.js'

Chart.register(LineElement, LineController, PointElement, LinearScale, Tooltip)

const store = usePricingStore()
const demo = useDemoModeStore()
const chartCanvas = ref(null)
let chartInstance = null

const yAxisLabel = computed(() => {
  const uls = store.underlyings
  if (!uls || uls.length === 0) return 'WOF (% initial)'
  if (uls.length === 1) return `${demo.underlyingLabel(uls[0].name, 0)} (% initial)`
  const names = uls.map((u, i) => demo.underlyingLabel(u.name, i)).join(', ')
  return `WOF [${names}] (% initial)`
})

const COLORS = {
  autocall: { stroke: 'rgba(34,197,94,0.35)',  solid: '#16a34a', label: 'Rappel autocall' },
  ki:       { stroke: 'rgba(239,68,68,0.35)',   solid: '#dc2626', label: 'KI / Perte en capital' },
  normal:   { stroke: 'rgba(148,163,184,0.30)', solid: '#64748b', label: 'Remboursement normal' },
}

const legend = computed(() => {
  if (!store.paths) return []
  const { autocall_count, ki_count, normal_count, total } = store.paths
  const pct = n => total > 0 ? (n / total * 100).toFixed(1) : '0'
  return [
    { key: 'autocall', ...COLORS.autocall, count: autocall_count, pct: pct(autocall_count) },
    { key: 'ki',       ...COLORS.ki,       count: ki_count,       pct: pct(ki_count) },
    { key: 'normal',   ...COLORS.normal,   count: normal_count,   pct: pct(normal_count) },
  ]
})

async function renderChart() {
  await nextTick()
  if (!chartCanvas.value || !store.paths) return
  if (chartInstance) { chartInstance.destroy(); chartInstance = null }

  const { path_data, T_max, user_params } = store.paths
  const datasets = []

  path_data.forEach(p => {
    const col = COLORS[p.outcome]?.stroke || 'rgba(100,116,139,0.3)'
    datasets.push({
      data: p.times.map((t, i) => ({ x: t, y: p.wof[i] * 100 })),
      borderColor: col,
      backgroundColor: 'transparent',
      borderWidth: 1.2,
      pointRadius: 0,
      fill: false,
      tension: 0.1,
    })
  })

  // Barrier lines from user_params
  const up = user_params || {}
  const T = T_max || store.globalParams.T
  if (up.AC_BAR != null) {
    datasets.push({
      data: [{ x: 0, y: up.AC_BAR * 100 }, { x: T, y: up.AC_BAR * 100 }],
      borderColor: '#f59e0b', borderWidth: 1.5, borderDash: [6, 4],
      pointRadius: 0, fill: false, label: `AC_BAR ${(up.AC_BAR*100).toFixed(0)}%`,
    })
  }
  if (up.KI_BAR != null) {
    datasets.push({
      data: [{ x: 0, y: up.KI_BAR * 100 }, { x: T, y: up.KI_BAR * 100 }],
      borderColor: '#ef4444', borderWidth: 1.5, borderDash: [6, 4],
      pointRadius: 0, fill: false, label: `KI_BAR ${(up.KI_BAR*100).toFixed(0)}%`,
    })
  }

  chartInstance = new Chart(chartCanvas.value, {
    type: 'line',
    data: { datasets },
    options: demoChartOptions({
      responsive: true, maintainAspectRatio: false, parsing: false,
      animation: { duration: 0 },
      plugins: {
        legend: { display: false },
        tooltip: {
          mode: 'nearest', intersect: false,
          callbacks: { label: it => `${it.raw.y.toFixed(1)}% à T=${it.raw.x.toFixed(2)}Y` },
        },
      },
      scales: {
        x: {
          type: 'linear', min: 0, max: T,
          title: { display: true, text: 'Temps (années)', font: { size: 9 } },
          ticks: { color: '#475569', font: { size: 9 }, callback: v => v + 'Y' },
          grid: { color: '#1e293b' },
        },
        y: {
          title: { display: true, text: yAxisLabel.value, font: { size: 9 } },
          ticks: { color: '#475569', font: { size: 9 }, callback: v => v + '%' },
          grid: { color: '#1e293b' },
        },
      },
    }, demo.enabled),
  })
}

watch(() => store.paths, renderChart)
watch(() => demo.enabled, renderChart)
onMounted(renderChart)
onUnmounted(() => { if (chartInstance) chartInstance.destroy() })
</script>
