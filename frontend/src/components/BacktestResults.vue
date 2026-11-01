<template>
  <div class="flex flex-col gap-4">
    <BacktestHistoryDetails :result="result" />
      <!-- Stats tiles -->
      <div class="flex flex-wrap gap-2">
        <div v-for="s in stats" :key="s.label" class="stat-box min-w-28">
          <div class="text-xs text-slate-500 mb-1">{{ s.label }}
            <HelpTip width="w-72" :text="s.tip" />
          </div>
          <div class="text-lg font-bold" :class="s.cls || 'text-slate-200'"><SensitiveValue>{{ s.val }}</SensitiveValue></div>
          <div v-if="s.warn" class="text-[9px] text-amber-500 mt-0.5">⚠ {{ s.warn }}</div>
        </div>
      </div>

      <!-- IRR histogram -->
      <div class="card">
        <div class="text-xs font-bold text-slate-500 uppercase tracking-wide mb-3">Distribution des TRI (%)</div>
        <SensitiveChart>
          <div style="height:240px;position:relative;">
            <canvas ref="histCanvas" role="img" aria-label="Distribution des TRI"></canvas>
          </div>
        </SensitiveChart>
      </div>

      <!-- IRR vs time chart -->
      <div class="card">
        <div class="text-xs font-bold text-slate-500 uppercase tracking-wide mb-3">TRI par date de départ</div>
        <SensitiveChart>
          <div style="height:200px;position:relative;">
            <canvas ref="lineCanvas" role="img" aria-label="TRI par date de départ"></canvas>
          </div>
        </SensitiveChart>
      </div>

      <!-- Raw table (collapsible) -->
      <div class="card">
        <button class="text-xs text-slate-500 hover:text-slate-300" @click="showTable = !showTable">
          {{ showTable ? '▲' : '▼' }} Détail des {{ result.n_windows }} fenêtres
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
              <tr v-for="row in result.rows" :key="row.date"
                  class="border-b border-slate-800 hover:bg-slate-800/40 transition-colors">
                <td class="py-1 pr-3 text-slate-400">{{ formatDate(row.date) }}</td>
                <td class="py-1 pr-3 text-right font-mono"
                    :class="row.irr > 0 ? 'text-green-400' : row.irr < 0 ? 'text-red-400' : 'text-slate-400'">
                  <SensitiveValue>{{ row.irr != null ? formatPercent(row.irr * 100, 2) : '—' }}</SensitiveValue>
                </td>
                <td class="py-1 pr-3 text-right text-slate-400"><SensitiveValue>{{ formatNumber(row.T_actual, 2) }}</SensitiveValue></td>
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
  </div>
</template>
<script setup>
import { ref, computed, watch, nextTick, onMounted, onUnmounted } from 'vue'
import { useDemoModeStore } from '../stores/demoMode.js'
import { demoChartOptions } from '../composables/useSensitiveChart.js'
import { applyChartTheme, axisTick, chartTheme } from '../charts/theme.js'
import SensitiveValue from './SensitiveValue.vue'
import SensitiveChart from './SensitiveChart.vue'
import HelpTip from './HelpTip.vue'
import BacktestHistoryDetails from './BacktestHistoryDetails.vue'
import { formatPercent, formatNumber, formatInt, formatDate } from '../utils/format.js'
import { Chart, BarElement, BarController, LineElement, LineController, PointElement,
  CategoryScale, LinearScale, Tooltip, Legend } from 'chart.js'

Chart.register(BarElement, BarController, LineElement, LineController, PointElement,
  CategoryScale, LinearScale, Tooltip, Legend)
applyChartTheme(Chart)
const props = defineProps({ result: { type: Object, required: true } })
const demo = useDemoModeStore()
const histCanvas = ref(null), lineCanvas = ref(null), showTable = ref(false)
let histChart = null, lineChart = null
const stats = computed(() => {
  if (!props.result) return []
  const { mean_irr, median_irr, sharpe, p10, p90, pct_positive, n_windows, overlap_pct } = props.result
  const fmt = v => v != null ? formatPercent(v * 100, 2) : '—'
  const sharpeOverlapWarn = overlap_pct != null && overlap_pct >= 50
  return [
    { label: 'TRI moyen', val: fmt(mean_irr), cls: mean_irr > 0 ? 'text-green-400' : 'text-red-400',
      tip: "Moyenne arithmétique du TRI sur toutes les fenêtres — sensible aux valeurs extrêmes (une fenêtre en perte totale pèse autant qu'une fenêtre rappelée)." },
    { label: 'TRI médian', val: fmt(median_irr), cls: median_irr > 0 ? 'text-green-300' : 'text-red-300',
      tip: "Valeur centrale (50e percentile) — plus robuste que la moyenne aux fenêtres extrêmes." },
    { label: 'P10 / P90', val: `${fmt(p10)} / ${fmt(p90)}`, cls: 'text-slate-300',
      tip: "10e et 90e percentiles du TRI — l'intervalle qui contient 80% des fenêtres." },
    { label: 'Sharpe (vs Rf)', val: sharpe != null ? formatNumber(sharpe, 2) : '—', cls: 'text-blue-400',
      tip: "(TRI moyen − taux sans risque) ÷ écart-type des TRI entre fenêtres. À lire avec précaution : les fenêtres se chevauchent (elles rejouent en grande partie le même historique) donc ne sont pas des observations indépendantes, et un payoff à barrières digitales (pas de participation continue) ne prend que quelques valeurs discrètes — les deux effets compriment artificiellement l'écart-type et gonflent ce Sharpe. Ce n'est pas un Sharpe de trajectoire de marché comparable à un actif coté."
        + (overlap_pct != null ? ` Chevauchement estimé des fenêtres : ${overlap_pct}%.` : ''),
      warn: sharpeOverlapWarn ? `Fenêtres chevauchées à ${overlap_pct}% — Sharpe peu fiable, à ne pas comparer à un actif coté` : null },
    { label: '% TRI positif', val: pct_positive != null ? formatPercent(pct_positive, 1) : '—', cls: 'text-slate-300',
      tip: "Part des fenêtres où le TRI est strictement positif (rappel anticipé avec coupon, ou remboursement à l'échéance avec gain)." },
    { label: 'Fenêtres', val: formatInt(n_windows), cls: 'text-slate-500',
      tip: "Nombre de dates de départ testées entre la date de début et (date de fin − maturité du produit), espacées de la fréquence de relance choisie." },
  ]
})

async function renderCharts() {
  await nextTick()
  if (!props.result) return

  if (histChart) { histChart.destroy(); histChart = null }
  if (lineChart) { lineChart.destroy(); lineChart = null }

  if (!histCanvas.value || !lineCanvas.value) return

  const rows = props.result.rows || []
  const irrs = rows.map(r => r.irr).filter(v => v != null)
  if (!irrs.length) return

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
  const bcolors = bins.map(v => v >= 0 ? chartTheme.positive : chartTheme.negative)
  const blabels = bins.map(v => (v * 100).toFixed(1).replace('.', ',') + '%')

  histChart = new Chart(histCanvas.value, {
    type: 'bar',
    data: { labels: blabels, datasets: [{ data: counts, backgroundColor: bcolors, borderRadius: 3 }] },
    options: demoChartOptions({
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false },
        tooltip: { callbacks: { label: it => `${it.raw} fenêtres` } } },
      scales: {
        x: { ticks: { font: { size: 8 }, maxRotation: 45 } },
        y: { ticks: { font: { size: 9 } }, min: 0 },
      },
      animation: { duration: 200 },
    }, demo.enabled),
  })

  // TRI over time
  const lineDates = rows.filter(r => r.irr != null).map(r => formatDate(r.date))
  const lineIrrs  = rows.filter(r => r.irr != null).map(r => +(r.irr * 100).toFixed(3))

  lineChart = new Chart(lineCanvas.value, {
    type: 'line',
    data: {
      labels: lineDates,
      datasets: [{
        label: 'TRI (%)',
        data: lineIrrs,
        borderColor: chartTheme.primary,
        backgroundColor: chartTheme.primarySoft,
        borderWidth: 1.5,
        pointRadius: 0,
        fill: true,
        tension: 0.2,
      }, {
        label: 'TRI=0',
        data: lineDates.map(() => 0),
        borderColor: 'rgba(192,57,43,.4)',
        borderWidth: 1,
        borderDash: [5, 4],
        pointRadius: 0,
        fill: false,
      }],
    },
    options: demoChartOptions({
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false },
        tooltip: { callbacks: { label: it => `TRI: ${it.raw.toFixed(2).replace('.', ',')}%` } } },
      scales: {
        x: { ticks: { font: { size: 8 }, maxTicksLimit: 8, maxRotation: 30 } },
        y: { ticks: { font: { size: 9 }, callback: axisTick('%') } },
      },
      animation: { duration: 200 },
    }, demo.enabled),
  })
}

watch(() => props.result, renderCharts)
watch(() => demo.enabled, renderCharts)
onMounted(renderCharts)
onUnmounted(() => {
  histChart?.destroy()
  lineChart?.destroy()
})
</script>
