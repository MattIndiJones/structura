<template>
  <div class="flex flex-col gap-4">
    <!-- Header + controls -->
    <div class="card">
      <div class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-4">📋 Backtest MTF — Rejouer sur historique</div>
      <div class="grid grid-cols-2 sm:grid-cols-3 gap-3 text-xs mb-4">
        <div>
          <label class="label">Date de début</label>
          <input v-model="form.start_date" type="date" class="input" />
        </div>
        <div>
          <label class="label">Date de fin</label>
          <input v-model="form.end_date" type="date" class="input" />
        </div>
        <div>
          <label class="label">Fréquence relance (j ouvrés)</label>
          <select v-model.number="form.freq" class="select">
            <option :value="5">Hebdo (5j)</option>
            <option :value="21">Mensuel (21j)</option>
            <option :value="63">Trimestriel (63j)</option>
            <option :value="126">Semestriel (126j)</option>
          </select>
        </div>
        <div>
          <label class="label">Montant investi (%)</label>
          <SensitiveValue mode="input"><input v-model.number="form.invest_pct" type="number" step="10" min="10" max="200" class="input" /></SensitiveValue>
        </div>
        <div>
          <label class="label">Taux sans risque (%/an)</label>
          <SensitiveValue mode="input"><input v-model.number="form.rf_rate" type="number" step="0.1" class="input" /></SensitiveValue>
        </div>
      </div>
      <div class="flex justify-end">
        <button class="btn-primary text-xs px-5" :disabled="store.loading || !canRun" @click="launchBacktest">
          <span v-if="store.loading" class="w-3 h-3 border border-white border-t-transparent rounded-full animate-spin inline-block mr-1"></span>
          ▶ Lancer le backtest
        </button>
      </div>
      <div v-if="!canRun" class="text-xs text-amber-500 mt-2">
        Renseignez les tickers dans "Marché &amp; Paramètres" pour activer le backtest historique.
      </div>
    </div>

    <!-- Empty state -->
    <div v-if="!store.backtest" class="flex flex-col items-center justify-center h-52 text-slate-600 gap-2">
      <div class="text-3xl">📋</div>
      <div class="text-sm font-medium">Configurez les paramètres et lancez le backtest</div>
      <div class="text-xs">Prix Yahoo Finance réels · TRI calculé sur chaque fenêtre</div>
    </div>

    <template v-else>
      <!-- Stats tiles -->
      <div class="flex flex-wrap gap-2">
        <div v-for="s in stats" :key="s.label" class="stat-box min-w-28">
          <div class="text-xs text-slate-500 mb-1">{{ s.label }}</div>
          <div class="text-lg font-bold" :class="s.cls || 'text-slate-200'"><SensitiveValue>{{ s.val }}</SensitiveValue></div>
        </div>
      </div>

      <!-- IRR histogram -->
      <div class="card">
        <div class="text-xs font-bold text-slate-500 uppercase tracking-wide mb-3">Distribution des TRI (%)</div>
        <SensitiveChart>
          <div style="height:240px;position:relative;">
            <canvas ref="histCanvas"></canvas>
          </div>
        </SensitiveChart>
      </div>

      <!-- IRR vs time chart -->
      <div class="card">
        <div class="text-xs font-bold text-slate-500 uppercase tracking-wide mb-3">TRI par date de départ</div>
        <SensitiveChart>
          <div style="height:200px;position:relative;">
            <canvas ref="lineCanvas"></canvas>
          </div>
        </SensitiveChart>
      </div>

      <!-- Raw table (collapsible) -->
      <div class="card">
        <button class="text-xs text-slate-500 hover:text-slate-300" @click="showTable = !showTable">
          {{ showTable ? '▲' : '▼' }} Détail des {{ store.backtest.n_windows }} fenêtres
        </button>
        <div v-if="showTable" class="overflow-x-auto mt-3">
          <table class="text-xs w-full border-collapse">
            <thead>
              <tr class="border-b border-slate-700">
                <th class="text-left text-slate-500 font-medium py-1 pr-3">Date départ</th>
                <th class="text-right text-slate-500 font-medium py-1 pr-3">TRI (%)</th>
                <th class="text-right text-slate-500 font-medium py-1 pr-3">Durée (Y)</th>
                <th class="text-left text-slate-500 font-medium py-1">Sortie</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in store.backtest.rows" :key="row.date"
                  class="border-b border-slate-800 hover:bg-slate-800/40 transition-colors">
                <td class="py-1 pr-3 text-slate-400">{{ row.date }}</td>
                <td class="py-1 pr-3 text-right font-mono"
                    :class="row.irr > 0 ? 'text-green-400' : row.irr < 0 ? 'text-red-400' : 'text-slate-400'">
                  <SensitiveValue>{{ row.irr != null ? (row.irr * 100).toFixed(2) + '%' : '—' }}</SensitiveValue>
                </td>
                <td class="py-1 pr-3 text-right text-slate-400"><SensitiveValue>{{ row.T_actual?.toFixed(2) ?? '—' }}</SensitiveValue></td>
                <td class="py-1">
                  <span class="px-1.5 py-0.5 rounded text-xs font-medium"
                        :class="row.early_recall
                          ? 'bg-green-900/40 text-green-400'
                          : 'bg-slate-800 text-slate-500'">
                    {{ row.early_recall ? 'Rappel anticipé' : 'Maturité' }}
                  </span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
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
  Chart, BarElement, BarController, LineElement, LineController, PointElement,
  CategoryScale, LinearScale, Tooltip, Legend
} from 'chart.js'

Chart.register(BarElement, BarController, LineElement, LineController, PointElement,
               CategoryScale, LinearScale, Tooltip, Legend)

const store = usePricingStore()
const demo = useDemoModeStore()
const histCanvas = ref(null)
const lineCanvas = ref(null)
let histChart = null
let lineChart = null
const showTable = ref(false)

const today = new Date().toISOString().slice(0, 10)
const form = ref({
  start_date: '2010-01-01',
  end_date: today,
  freq: 21,
  invest_pct: 100,
  rf_rate: 2.0,
})

const canRun = computed(() => store.underlyings.some(u => u.ticker?.trim()))

function launchBacktest() {
  store.runBacktest({ ...form.value })
}

const stats = computed(() => {
  if (!store.backtest) return []
  const { mean_irr, median_irr, sharpe, p10, p90, pct_positive, n_windows } = store.backtest
  const fmt = v => v != null ? (v * 100).toFixed(2) + '%' : '—'
  return [
    { label: 'TRI moyen', val: fmt(mean_irr), cls: mean_irr > 0 ? 'text-green-400' : 'text-red-400' },
    { label: 'TRI médian', val: fmt(median_irr), cls: median_irr > 0 ? 'text-green-300' : 'text-red-300' },
    { label: 'P10 / P90', val: `${fmt(p10)} / ${fmt(p90)}`, cls: 'text-slate-300' },
    { label: 'Sharpe (vs Rf)', val: sharpe != null ? sharpe.toFixed(2) : '—', cls: 'text-blue-400' },
    { label: '% TRI positif', val: pct_positive != null ? pct_positive.toFixed(1) + '%' : '—', cls: 'text-slate-300' },
    { label: 'Fenêtres', val: n_windows?.toLocaleString() ?? '—', cls: 'text-slate-500' },
  ]
})

async function renderCharts() {
  await nextTick()
  if (!store.backtest) return

  if (histChart) { histChart.destroy(); histChart = null }
  if (lineChart) { lineChart.destroy(); lineChart = null }

  if (!histCanvas.value || !lineCanvas.value) return

  const rows = store.backtest.rows || []
  const irrs = rows.map(r => r.irr).filter(v => v != null)

  // Histogram bins
  const binCount = 20
  const minV = Math.min(...irrs)
  const maxV = Math.max(...irrs)
  const bw    = (maxV - minV) / binCount || 0.01
  const bins  = Array.from({ length: binCount }, (_, i) => minV + i * bw)
  const counts = new Array(binCount).fill(0)
  irrs.forEach(v => {
    const b = Math.min(binCount - 1, Math.floor((v - minV) / bw))
    counts[b]++
  })
  const bcolors = bins.map(v => v >= 0 ? 'rgba(16,185,129,.7)' : 'rgba(239,68,68,.7)')
  const blabels = bins.map(v => (v * 100).toFixed(1) + '%')

  histChart = new Chart(histCanvas.value, {
    type: 'bar',
    data: { labels: blabels, datasets: [{ data: counts, backgroundColor: bcolors, borderRadius: 3 }] },
    options: demoChartOptions({
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false },
        tooltip: { callbacks: { label: it => `${it.raw} fenêtres` } } },
      scales: {
        x: { ticks: { color: '#475569', font: { size: 8 }, maxRotation: 45 }, grid: { color: '#1e293b' } },
        y: { ticks: { color: '#475569', font: { size: 9 } }, grid: { color: '#1e293b' }, min: 0 },
      },
      animation: { duration: 200 },
    }, demo.enabled),
  })

  // TRI over time
  const lineDates = rows.filter(r => r.irr != null).map(r => r.date)
  const lineIrrs  = rows.filter(r => r.irr != null).map(r => +(r.irr * 100).toFixed(3))

  lineChart = new Chart(lineCanvas.value, {
    type: 'line',
    data: {
      labels: lineDates,
      datasets: [{
        label: 'TRI (%)',
        data: lineIrrs,
        borderColor: 'rgba(59,130,246,.8)',
        backgroundColor: 'rgba(59,130,246,.08)',
        borderWidth: 1.5,
        pointRadius: 0,
        fill: true,
        tension: 0.2,
      }, {
        label: 'TRI=0',
        data: lineDates.map(() => 0),
        borderColor: 'rgba(239,68,68,.4)',
        borderWidth: 1,
        borderDash: [5, 4],
        pointRadius: 0,
        fill: false,
      }],
    },
    options: demoChartOptions({
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false },
        tooltip: { callbacks: { label: it => `TRI: ${it.raw.toFixed(2)}%` } } },
      scales: {
        x: { ticks: { color: '#475569', font: { size: 8 }, maxTicksLimit: 8, maxRotation: 30 }, grid: { color: '#1e293b' } },
        y: { ticks: { color: '#475569', font: { size: 9 }, callback: v => v + '%' }, grid: { color: '#1e293b' } },
      },
      animation: { duration: 200 },
    }, demo.enabled),
  })
}

watch(() => store.backtest, renderCharts)
watch(() => demo.enabled, renderCharts)
onMounted(renderCharts)
onUnmounted(() => {
  if (histChart) histChart.destroy()
  if (lineChart) lineChart.destroy()
})
</script>
