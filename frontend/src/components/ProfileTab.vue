<template>
  <div class="flex flex-col gap-4">
    <!-- Header card -->
    <div class="card">
      <div class="flex items-center gap-3 flex-wrap">
        <div>
          <div class="text-xs font-bold text-slate-400 uppercase tracking-wider">📈 Profil de Payoff</div>
          <div class="text-xs text-slate-600 mt-0.5 italic">Chemin déterministe — spot balayé de 40% à 200%</div>
        </div>
        <div class="ml-auto">
          <button class="btn-primary text-xs px-4" :disabled="store.loading" @click="store.runProfile()">
            <span v-if="store.loading" class="w-3 h-3 border border-white border-t-transparent rounded-full animate-spin inline-block mr-1"></span>
            ▶ Calculer
          </button>
        </div>
      </div>
    </div>

    <!-- Empty state -->
    <div v-if="!store.profile" class="flex flex-col items-center justify-center h-52 text-slate-600 gap-2">
      <div class="text-3xl">📈</div>
      <div class="text-sm font-medium">Cliquez "Calculer" pour voir le profil de payoff</div>
      <div class="text-xs">Balayage déterministe du spot de 40% à 200%</div>
    </div>

    <!-- Chart + stats -->
    <div v-else class="card">
      <SensitiveChart>
        <div style="height:280px;position:relative;">
          <canvas ref="chartCanvas"></canvas>
        </div>
      </SensitiveChart>
      <div class="flex gap-4 flex-wrap mt-3 pt-3 border-t border-slate-800 text-xs text-slate-500">
        <span>ATM: <strong class="text-slate-300"><SensitiveValue>{{ atmPayoff }}%</SensitiveValue></strong></span>
        <span>Min: <strong class="text-slate-300"><SensitiveValue>{{ minPayoff }}%</SensitiveValue></strong></span>
        <span>Max: <strong class="text-slate-300"><SensitiveValue>{{ maxPayoff }}%</SensitiveValue></strong></span>
        <span v-if="store.result">Prix MC: <strong class="text-blue-400"><SensitiveValue>{{ pricePct }}%</SensitiveValue></strong></span>
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
  CategoryScale, LinearScale, Tooltip, Legend
} from 'chart.js'

Chart.register(LineElement, LineController, PointElement, CategoryScale, LinearScale, Tooltip, Legend)

const store = usePricingStore()
const demo = useDemoModeStore()
const chartCanvas = ref(null)
let chartInstance = null

const atmPayoff = computed(() => {
  if (!store.profile) return '—'
  const idx = store.profile.levels.indexOf(100)
  return idx >= 0 ? store.profile.payoffs[idx].toFixed(2) : '—'
})
const minPayoff = computed(() => store.profile ? Math.min(...store.profile.payoffs).toFixed(2) : '—')
const maxPayoff = computed(() => store.profile ? Math.max(...store.profile.payoffs).toFixed(2) : '—')
const pricePct  = computed(() => store.result ? (store.result.price * 100).toFixed(2) : null)

async function renderChart() {
  await nextTick()
  if (!chartCanvas.value || !store.profile) return
  if (chartInstance) { chartInstance.destroy(); chartInstance = null }

  const { levels, payoffs } = store.profile
  const priceLine = store.result ? store.result.price * 100 : null

  const datasets = [{
    label: 'Payoff',
    data: payoffs,
    borderColor: '#3b82f6',
    backgroundColor: 'rgba(59,130,246,0.08)',
    borderWidth: 2.5,
    pointRadius: levels.map(l => l === 100 ? 5 : 0),
    pointBackgroundColor: '#3b82f6',
    fill: true,
    tension: 0.3,
  }]

  if (priceLine !== null) {
    datasets.push({
      label: 'Prix MC',
      data: levels.map(() => priceLine),
      borderColor: 'rgba(100,116,139,0.5)',
      borderWidth: 1.5,
      borderDash: [5, 4],
      pointRadius: 0,
      fill: false,
    })
  }

  chartInstance = new Chart(chartCanvas.value, {
    type: 'line',
    data: { labels: levels.map(l => l + '%'), datasets },
    options: demoChartOptions({
      responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          mode: 'index', intersect: false,
          callbacks: {
            title: items => `Spot final: ${items[0].label}`,
            label: item => item.datasetIndex === 0
              ? `Payoff: ${item.raw.toFixed(2)}%`
              : `Prix MC: ${item.raw.toFixed(2)}%`,
          },
        },
      },
      scales: {
        x: {
          title: { display: true, text: 'Niveau spot (% du niveau initial)', font: { size: 9 } },
          ticks: { maxTicksLimit: 10, font: { size: 9 }, color: '#475569' },
          grid: { color: '#1e293b' },
        },
        y: {
          title: { display: true, text: 'Payoff (%)', font: { size: 9 } },
          ticks: { callback: v => v + '%', font: { size: 9 }, color: '#475569' },
          grid: { color: '#1e293b' },
        },
      },
      animation: { duration: 200 },
    }, demo.enabled),
  })
}

watch(() => store.profile, renderChart)
watch(() => demo.enabled, renderChart)
onMounted(renderChart)
onUnmounted(() => { if (chartInstance) chartInstance.destroy() })
</script>
