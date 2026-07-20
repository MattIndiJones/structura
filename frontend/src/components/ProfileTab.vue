<template>
  <div class="flex flex-col gap-4">
    <!-- Header card -->
    <div class="card">
      <div class="flex items-center gap-3 flex-wrap">
        <div>
          <div class="text-xs font-bold text-slate-400 uppercase tracking-wider">📈 Profil de Payoff
            <HelpTip width="w-72" text="Pas une simulation : à chaque niveau testé, le sous-jacent est fixé à ce niveau constant sur TOUTE la durée de vie (toutes les dates d'observation à la fois) — pas un vrai chemin de marché qui bouge dans le temps. Utile pour lire la forme du payoff (barrières, paliers, effet de levier) indépendamment du bruit Monte Carlo, mais ne remplace pas les chemins MC (onglet Chemins MC) pour juger d'un scénario réaliste." />
          </div>
          <div class="text-xs text-slate-600 mt-0.5 italic">Chemin déterministe — spot balayé de 40% à 200%</div>
        </div>
        <div v-if="store.profile" class="flex items-center gap-1 text-[10px] border border-slate-700 rounded overflow-hidden shrink-0">
          <button :class="['px-2 py-1 transition-colors', viewMode === 'payoff' ? 'bg-slate-700 text-slate-200 font-semibold' : 'text-slate-500 hover:text-slate-400']"
                  @click="viewMode = 'payoff'">Payoff brut</button>
          <button :class="['px-2 py-1 transition-colors', viewMode === 'annualized' ? 'bg-blue-900/80 text-blue-300 font-semibold' : 'text-slate-500 hover:text-slate-400']"
                  @click="viewMode = 'annualized'">Coupon annualisé</button>
          <HelpTip width="w-72" text="Coupon annualisé = (payoff − 100%) / temps jusqu'au déclenchement (autocall) ou maturité. Utile pour un coupon « mémoire » (paie tous les coupons accumulés au déclenchement) : le payoff brut fait un saut selon la date de déclenchement, alors que le taux annualisé reste constant — c'est le vrai taux facial du produit, indépendant du moment où ça se déclenche." />
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
        <span>ATM: <strong class="text-slate-300"><SensitiveValue>{{ atmValue }}{{ unit }}</SensitiveValue></strong></span>
        <span>Min: <strong class="text-slate-300"><SensitiveValue>{{ minValue }}{{ unit }}</SensitiveValue></strong></span>
        <span>Max: <strong class="text-slate-300"><SensitiveValue>{{ maxValue }}{{ unit }}</SensitiveValue></strong></span>
        <span v-if="store.result && viewMode === 'payoff'">Prix MC: <strong class="text-blue-400"><SensitiveValue>{{ pricePct }}%</SensitiveValue></strong>
          <HelpTip text="Ligne pointillée horizontale sur le graphique — le prix équitable actualisé issu du dernier pricing MC, pour comparer visuellement où se situe le payoff déterministe par rapport au prix réel du produit." />
        </span>
      </div>

      <!-- Numeric table — mirrors the chart exactly, same store.profile data -->
      <div class="mt-3 pt-3 border-t border-slate-800">
        <div class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-2">Valeurs numériques</div>
        <div class="max-h-64 overflow-y-auto border border-slate-800 rounded">
          <table class="w-full text-xs border-collapse">
            <thead class="sticky top-0 bg-slate-900">
              <tr class="border-b border-slate-700">
                <th class="text-left py-1 px-2 text-slate-500 font-semibold text-[10px] uppercase">Spot</th>
                <th class="text-right py-1 px-2 text-slate-500 font-semibold text-[10px] uppercase">{{ viewMode === 'payoff' ? 'Payoff' : 'Coupon annualisé' }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in tableRows" :key="row.level"
                  :class="['border-b border-slate-800/60', row.level === 100 ? 'bg-slate-800/50' : '']">
                <td class="py-1 px-2 font-mono text-slate-400">{{ row.level.toFixed(1) }}%</td>
                <td class="py-1 px-2 font-mono text-right text-slate-300">{{ row.value.toFixed(2) }}{{ unit }}</td>
              </tr>
            </tbody>
          </table>
        </div>
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
import HelpTip from './HelpTip.vue'
import {
  Chart, LineElement, LineController, PointElement,
  CategoryScale, LinearScale, Tooltip, Legend
} from 'chart.js'

Chart.register(LineElement, LineController, PointElement, CategoryScale, LinearScale, Tooltip, Legend)

const store = usePricingStore()
const demo = useDemoModeStore()
const chartCanvas = ref(null)
let chartInstance = null

const viewMode = ref('payoff')   // 'payoff' | 'annualized'
const unit = computed(() => viewMode.value === 'payoff' ? '%' : '%/an')
const activeSeries = computed(() => {
  if (!store.profile) return []
  return viewMode.value === 'payoff' ? store.profile.payoffs : store.profile.annualized_coupons
})

const atmValue = computed(() => {
  if (!store.profile) return '—'
  const idx = store.profile.levels.indexOf(100)
  return idx >= 0 ? activeSeries.value[idx].toFixed(2) : '—'
})
const minValue = computed(() => activeSeries.value.length ? Math.min(...activeSeries.value).toFixed(2) : '—')
const maxValue = computed(() => activeSeries.value.length ? Math.max(...activeSeries.value).toFixed(2) : '—')
const tableRows = computed(() => {
  if (!store.profile) return []
  return store.profile.levels.map((level, i) => ({ level, value: activeSeries.value[i] }))
})
const pricePct  = computed(() => store.result ? (store.result.price * 100).toFixed(2) : null)

async function renderChart() {
  await nextTick()
  if (!chartCanvas.value || !store.profile) return
  if (chartInstance) { chartInstance.destroy(); chartInstance = null }

  const { levels } = store.profile
  const series = activeSeries.value
  const isPayoff = viewMode.value === 'payoff'
  const seriesLabel = isPayoff ? 'Payoff' : 'Coupon annualisé'
  const priceLine = (isPayoff && store.result) ? store.result.price * 100 : null

  const datasets = [{
    label: seriesLabel,
    data: series,
    borderColor: '#3b82f6',
    backgroundColor: 'rgba(59,130,246,0.08)',
    borderWidth: 2.5,
    pointRadius: levels.map(l => l === 100 ? 5 : 0),
    pointBackgroundColor: '#3b82f6',
    fill: true,
    tension: 0,
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
              ? `${seriesLabel}: ${item.raw.toFixed(2)}${unit.value}`
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
          title: { display: true, text: `${seriesLabel} (${unit.value})`, font: { size: 9 } },
          ticks: { callback: v => v + unit.value, font: { size: 9 }, color: '#475569' },
          grid: { color: '#1e293b' },
        },
      },
      animation: { duration: 200 },
    }, demo.enabled),
  })
}

watch(() => store.profile, renderChart)
watch(viewMode, renderChart)
watch(() => demo.enabled, renderChart)
onMounted(renderChart)
onUnmounted(() => { if (chartInstance) chartInstance.destroy() })
</script>
