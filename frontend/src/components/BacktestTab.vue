<template>
  <div class="flex flex-col gap-4">
    <InLifeNotAlignedBanner />
    <!-- Sub-tabs -->
    <div class="flex gap-2">
      <button v-for="t in subTabs" :key="t.id"
        class="px-3 py-1.5 text-xs font-semibold rounded-lg border transition-colors"
        :class="subTab === t.id
          ? 'bg-blue-600 border-blue-500 text-white'
          : 'bg-slate-800 border-slate-700 text-slate-400 hover:text-slate-200'"
        @click="subTab = t.id">
        {{ t.label }}
      </button>
    </div>

    <ComparatorTab v-if="subTab === 'comparator'" />

    <template v-else>
    <!-- Header + controls -->
    <div class="card">
      <div class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-4">📋 Backtest MTF — Rejouer sur historique</div>
      <div class="grid grid-cols-2 sm:grid-cols-3 gap-3 text-xs mb-4">
        <div>
          <label class="label">Date de début
            <HelpTip text="Début de l'historique de prix chargé depuis Yahoo Finance. La première fenêtre de backtest démarre à cette date ; les fenêtres suivantes glissent jusqu'à ce qu'il ne reste plus assez d'historique avant la date de fin pour couvrir la maturité du produit." />
          </label>
          <input v-model="form.start_date" type="date" class="input" />
        </div>
        <div>
          <label class="label">Date de fin
            <HelpTip text="Fin de l'historique chargé. Détermine la dernière fenêtre possible : il faut qu'il reste au moins T années d'historique après une date de départ pour que sa fenêtre soit exploitable." />
          </label>
          <input v-model="form.end_date" type="date" class="input" />
        </div>
        <div>
          <label class="label">Fréquence relance (j ouvrés)
            <HelpTip width="w-72" text="Pas entre deux dates de départ de fenêtre glissante — pas le pas d'observation du produit lui-même (ça, c'est AT 1,2,3 dans le script). Plus la fréquence est fine par rapport à la maturité du produit, plus les fenêtres voisines se recouvrent et partagent le même historique — leurs TRI ne sont alors plus des observations indépendantes, ce qui fausse à la hausse le Sharpe ci-dessous." />
          </label>
          <select v-model.number="form.freq" class="select">
            <option :value="1">Quotidien (1j)</option>
            <option :value="5">Hebdo (5j)</option>
            <option :value="21">Mensuel (21j)</option>
            <option :value="63">Trimestriel (63j)</option>
            <option :value="126">Semestriel (126j)</option>
          </select>
        </div>
        <div>
          <label class="label">Montant investi (%)
            <HelpTip text="Base du flux à t=0 (le -100% habituel) utilisée pour le calcul du TRI de chaque fenêtre. Modifier ceci change le TRI (effet de levier sur le flux d'entrée) mais pas les flux de sortie du produit lui-même." />
          </label>
          <SensitiveValue mode="input"><input v-model.number="form.invest_pct" type="number" step="10" min="10" max="200" class="input" /></SensitiveValue>
        </div>
        <div>
          <label class="label">Taux sans risque (%/an)
            <HelpTip text="Utilisé uniquement pour le Sharpe (TRI en excès du taux sans risque, divisé par l'écart-type des TRI) — n'affecte ni les flux ni le TRI de chaque fenêtre." />
          </label>
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
    </template>
    </template>
  </div>
</template>

<script setup>
import InLifeNotAlignedBanner from './InLifeNotAlignedBanner.vue'
import { ref, computed, watch, nextTick, onMounted, onUnmounted } from 'vue'
import { usePricingStore } from '../stores/pricing.js'
import { useDemoModeStore } from '../stores/demoMode.js'
import { demoChartOptions } from '../composables/useSensitiveChart.js'
import { applyChartTheme, axisTick, chartTheme } from '../charts/theme.js'
import SensitiveValue from './SensitiveValue.vue'
import SensitiveChart from './SensitiveChart.vue'
import ComparatorTab from './ComparatorTab.vue'
import HelpTip from './HelpTip.vue'
import { formatPercent, formatNumber, formatInt, formatDate } from '../utils/format.js'
import {
  Chart, BarElement, BarController, LineElement, LineController, PointElement,
  CategoryScale, LinearScale, Tooltip, Legend
} from 'chart.js'

Chart.register(BarElement, BarController, LineElement, LineController, PointElement,
               CategoryScale, LinearScale, Tooltip, Legend)
applyChartTheme(Chart)

const store = usePricingStore()
const demo = useDemoModeStore()

const subTab = ref('backtest')
const subTabs = [
  { id: 'backtest',   label: '📋 Backtest' },
  { id: 'comparator', label: '🔎 Comparateur de sous-jacents' },
]
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
  const { mean_irr, median_irr, sharpe, p10, p90, pct_positive, n_windows, overlap_pct } = store.backtest
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

watch(() => store.backtest, renderCharts)
watch(() => demo.enabled, renderCharts)
onMounted(renderCharts)
onUnmounted(() => {
  if (histChart) histChart.destroy()
  if (lineChart) lineChart.destroy()
})
</script>
