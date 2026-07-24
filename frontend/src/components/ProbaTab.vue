<template>
  <div class="flex flex-col gap-4">
    <!-- Header -->
    <div class="card">
      <div class="flex items-center gap-3 flex-wrap">
        <div>
          <div class="text-xs font-bold text-slate-400 uppercase tracking-wider">🎲 Analyse Probabiliste
            <HelpTip text="Lance sa propre simulation à 5 000 chemins, indépendante du N configuré dans Marché &amp; Paramètres pour le pricing principal — un échantillon dédié pour ces statistiques, pas un recyclage du dernier pricing." />
          </div>
          <div v-if="store.proba" class="text-xs text-slate-600 mt-0.5 italic">
            <SensitiveValue>{{ store.proba.total.toLocaleString() }} chemins analysés</SensitiveValue>
          </div>
        </div>
        <div class="ml-auto">
          <button class="btn-primary text-xs px-4" :disabled="store.loading" @click="store.runProba()">
            <span v-if="store.loading" class="w-3 h-3 border border-white border-t-transparent rounded-full animate-spin inline-block mr-1"></span>
            ▶ Analyser
          </button>
        </div>
      </div>
    </div>

    <!-- Empty state -->
    <div v-if="!store.proba" class="flex flex-col items-center justify-center h-52 text-slate-600 gap-2">
      <div class="text-3xl">🎲</div>
      <div class="text-sm font-medium">Cliquez "Analyser" pour la décomposition probabiliste</div>
    </div>

    <template v-else>
      <!-- Charts 2-col -->
      <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <!-- Donut -->
        <div class="card">
          <div class="text-xs font-bold text-slate-500 uppercase tracking-wide mb-3">
            {{ store.proba.has_autocall ? 'Répartition des scénarios' : 'ITM vs OTM' }}
            <HelpTip :text="store.proba.has_autocall
              ? 'Chaque chemin classé dans exactement une catégorie : rappelé à telle date, arrivé à échéance sans perte, ou perte en capital — les tranches somment à 100% des chemins.'
              : 'Part des chemins où le payoff final est positif (ITM) vs nul (OTM), sur cet échantillon dédié de 5 000 chemins.'" />
          </div>
          <SensitiveChart>
            <div style="height:200px;position:relative;">
              <canvas ref="donutCanvas"></canvas>
            </div>
          </SensitiveChart>
        </div>
        <!-- Bar -->
        <div class="card">
          <div class="text-xs font-bold text-slate-500 uppercase tracking-wide mb-3">
            {{ store.proba.has_autocall ? 'P(rappel) par date' : 'Distribution du spot final' }}
            <HelpTip :text="store.proba.has_autocall
              ? 'Probabilité de rappel à CHAQUE date d\'observation prise isolément (pas cumulée) — la somme de ces barres plus la probabilité de non-rappel/perte ne fait pas nécessairement 100% de façon lisible directement ici, voir le donut à gauche pour la répartition cumulée.'
              : 'Histogramme du niveau du sous-jacent (ou du pire, si worst-of) au moment où le payoff se déclenche, parmi les chemins in-the-money uniquement.'" />
          </div>
          <SensitiveChart>
            <div style="height:200px;position:relative;">
              <canvas ref="barCanvas"></canvas>
            </div>
          </SensitiveChart>
        </div>
      </div>

      <!-- Stats tiles -->
      <div class="flex flex-wrap gap-2">
        <template v-if="store.proba.has_autocall">
          <div v-for="s in acStats" :key="s.label" class="stat-box min-w-28">
            <div class="text-xs text-slate-500 mb-1">{{ s.label }}
              <HelpTip v-if="s.tip" :text="s.tip" />
            </div>
            <div class="text-lg font-bold" :class="s.cls || 'text-slate-200'"><SensitiveValue>{{ s.val }}</SensitiveValue></div>
          </div>
        </template>
        <template v-else>
          <div v-for="s in vanillaStats" :key="s.label" class="stat-box min-w-28">
            <div class="text-xs text-slate-500 mb-1">{{ s.label }}
              <HelpTip v-if="s.tip" :text="s.tip" />
            </div>
            <div class="text-lg font-bold" :class="s.cls || 'text-slate-200'"><SensitiveValue>{{ s.val }}</SensitiveValue></div>
          </div>
        </template>
      </div>

      <!-- Percentiles -->
      <div class="card">
        <div class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3">Percentiles du payoff</div>
        <div class="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
          <div class="text-center p-2 bg-red-950/30 rounded-lg border border-red-900/30">
            <div class="text-red-400 font-bold text-slate-500 mb-1">P5</div>
            <div class="text-red-400 font-bold text-base"><SensitiveValue>{{ store.proba.percentiles.p5 }}%</SensitiveValue></div>
          </div>
          <div class="text-center p-2 bg-slate-800/50 rounded-lg border border-slate-700">
            <div class="text-slate-500 mb-1">P25</div>
            <div class="text-slate-300 font-bold text-base"><SensitiveValue>{{ store.proba.percentiles.p25 }}%</SensitiveValue></div>
          </div>
          <div class="text-center p-2 bg-slate-800/50 rounded-lg border border-slate-700">
            <div class="text-slate-500 mb-1">P75</div>
            <div class="text-slate-300 font-bold text-base"><SensitiveValue>{{ store.proba.percentiles.p75 }}%</SensitiveValue></div>
          </div>
          <div class="text-center p-2 bg-green-950/30 rounded-lg border border-green-900/30">
            <div class="text-slate-500 mb-1">P95</div>
            <div class="text-green-400 font-bold text-base"><SensitiveValue>{{ store.proba.percentiles.p95 }}%</SensitiveValue></div>
          </div>
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
import { chartTheme, applyChartTheme } from '../charts/theme.js'
import SensitiveValue from './SensitiveValue.vue'
import SensitiveChart from './SensitiveChart.vue'
import HelpTip from './HelpTip.vue'
import {
  Chart, DoughnutController, ArcElement,
  BarElement, BarController,
  CategoryScale, LinearScale, Tooltip, Legend
} from 'chart.js'

Chart.register(DoughnutController, ArcElement, BarElement, BarController,
               CategoryScale, LinearScale, Tooltip, Legend)
applyChartTheme(Chart)

const store = usePricingStore()
const demo = useDemoModeStore()
const donutCanvas = ref(null)
const barCanvas   = ref(null)
let donutChart = null
let barChart   = null

function pct(n, total) {
  return total > 0 ? (n / total * 100).toFixed(1) : '0'
}

const acStats = computed(() => {
  if (!store.proba) return []
  const { autocall_count, ki_count, normal_count, total, expected_life } = store.proba
  return [
    { label: 'P(rappel autocall)', val: pct(autocall_count, total) + '%', cls: 'text-green-400',
      tip: "Fraction des chemins où le produit a été rappelé anticipativement à l'une des dates d'observation (condition d'autocall remplie avant l'échéance)." },
    { label: 'P(KI / perte)',      val: pct(ki_count, total) + '%',       cls: 'text-red-400',
      tip: "Fraction des chemins qui atteignent l'échéance ET franchissent la barrière de perte en capital (jamais rappelés avant, barrière KI touchée)." },
    { label: 'P(remb. normal)',    val: pct(normal_count, total) + '%',   cls: 'text-slate-300',
      tip: "Fraction des chemins qui atteignent l'échéance sans jamais avoir été rappelés ni avoir franchi la barrière de perte — remboursement du capital sans coupon additionnel à ce stade." },
    { label: 'Durée espérée',      val: expected_life.toFixed(2) + ' Y',  cls: 'text-blue-400',
      tip: "Même quantité que le Fugit affiché dans l'onglet Résultats (E[τ]) — durée de vie moyenne pondérée par probabilité, ici recalculée sur l'échantillon dédié à 5 000 chemins de cet onglet." },
    { label: 'Chemins',            val: total.toLocaleString(),            cls: 'text-slate-400' },
  ]
})

const vanillaStats = computed(() => {
  if (!store.proba) return []
  const { normal_count, ki_count, total, price } = store.proba
  return [
    { label: 'P(ITM)', val: pct(normal_count, total) + '%', cls: 'text-green-400',
      tip: "Fraction des chemins où le payoff final est strictement positif (in-the-money à l'échéance)." },
    { label: 'P(OTM)', val: pct(ki_count, total) + '%',     cls: 'text-slate-400',
      tip: "Fraction des chemins où le payoff final est nul (out-of-the-money à l'échéance — perte totale de la prime pour une option vanille)." },
    { label: 'Prix MC', val: (price * 100).toFixed(2) + '%', cls: 'text-blue-400',
      tip: "Prix recalculé sur l'échantillon dédié de cet onglet (5 000 chemins) — peut différer légèrement du prix de référence de l'onglet Résultats (bruit MC, échantillon différent)." },
    { label: 'Chemins', val: total.toLocaleString(),          cls: 'text-slate-400' },
  ]
})

async function renderCharts() {
  await nextTick()
  if (!store.proba || !donutCanvas.value || !barCanvas.value) return

  if (donutChart) { donutChart.destroy(); donutChart = null }
  if (barChart)   { barChart.destroy();   barChart   = null }

  const { has_autocall, autocall_count, ki_count, normal_count, total,
          obs_times, event_counts, final_wofs } = store.proba

  // JSON keys from Python float dict come as "1.0", "2.0" → JS lookup by number fails
  // Normalize: parseFloat("1.0") = 1, stored under key "1" → ec[t] works for t=1
  const ec = Object.fromEntries(
    Object.entries(event_counts).map(([k, v]) => [parseFloat(k), v])
  )

  if (has_autocall) {
    // Donut: per-date autocall + ki + normal
    const acColors = ['#14603a','#1a7a4a','#2f9d61','#4cb883','#7fd0a5','#a8e0c2']
    const acLabels = obs_times.map(t => `Rappel T=${t.toFixed(1)}Y`)
    const acData   = obs_times.map(t => ec[t] || 0)

    donutChart = new Chart(donutCanvas.value, {
      type: 'doughnut',
      data: {
        labels: [...acLabels, 'Remboursement normal', 'Perte en capital'],
        datasets: [{
          data: [...acData, normal_count, ki_count],
          backgroundColor: [...acColors.slice(0, obs_times.length), chartTheme.ticks, chartTheme.negative],
          borderWidth: 1.5, borderColor: chartTheme.surface,
        }],
      },
      options: demoChartOptions({
        responsive: true, maintainAspectRatio: false, cutout: '62%',
        plugins: {
          legend: { position: 'right', labels: { font: { size: 10 }, boxWidth: 12 } },
          tooltip: { callbacks: {
            label: it => `${it.label}: ${(it.raw/total*100).toFixed(1)}% (${it.raw})`,
          }},
        },
        animation: { duration: 250 },
      }, demo.enabled),
    })

    const barData = obs_times.map(t => +((ec[t] || 0) / total * 100).toFixed(2))
    barChart = new Chart(barCanvas.value, {
      type: 'bar',
      data: {
        labels: obs_times.map(t => `T=${t.toFixed(1)}Y`),
        datasets: [{ label: 'P(rappel)', data: barData, backgroundColor: acColors, borderRadius: 4 }],
      },
      options: demoChartOptions({
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false },
          tooltip: { callbacks: { label: it => `${it.raw.toFixed(1)}%` } } },
        scales: {
          x: { ticks: { font: { size: 10 } } },
          y: { ticks: { font: { size: 9 }, callback: v => v + '%' }, min: 0 },
        },
        animation: { duration: 200 },
      }, demo.enabled),
    })
  } else {
    // Vanilla product: ITM vs OTM donut
    donutChart = new Chart(donutCanvas.value, {
      type: 'doughnut',
      data: {
        labels: ['ITM (payoff > 0)', 'OTM (payoff nul)'],
        datasets: [{ data: [normal_count, ki_count],
          backgroundColor: [chartTheme.positive, chartTheme.ticks], borderWidth: 1.5, borderColor: chartTheme.surface }],
      },
      options: demoChartOptions({
        responsive: true, maintainAspectRatio: false, cutout: '62%',
        plugins: {
          legend: { position: 'right', labels: { font: { size: 11 }, boxWidth: 14 } },
          tooltip: { callbacks: { label: it => `${it.label}: ${(it.raw/total*100).toFixed(1)}% (${it.raw})` } },
        },
        animation: { duration: 250 },
      }, demo.enabled),
    })

    // Bar: distribution of final spot levels
    const edges = [0.5,0.6,0.7,0.8,0.9,1.0,1.1,1.2,1.3,1.4,1.5,1.75,2.0]
    const lbls  = edges.slice(0,-1).map((v,i) => `${(v*100).toFixed(0)}–${(edges[i+1]*100).toFixed(0)}%`)
    const bdata = new Array(lbls.length).fill(0)
    const fw = (final_wofs || []).filter(v => v > 0)
    fw.forEach(s => {
      for (let b = 0; b < edges.length-1; b++) {
        if (s/100 >= edges[b] && s/100 < edges[b+1]) { bdata[b]++; break }
      }
    })
    const bpct   = bdata.map(c => fw.length > 0 ? +(c/fw.length*100).toFixed(1) : 0)
    const bcolors = edges.slice(0,-1).map(v => v < 1 ? 'rgba(192,57,43,.65)' : 'rgba(26,122,74,.65)')
    barChart = new Chart(barCanvas.value, {
      type: 'bar',
      data: { labels: lbls, datasets: [{ data: bpct, backgroundColor: bcolors, borderRadius: 4 }] },
      options: demoChartOptions({
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false },
          tooltip: { callbacks: { label: it => `${it.raw.toFixed(1)}% des chemins` } } },
        scales: {
          x: { ticks: { font: { size: 9 }, maxRotation: 45 } },
          y: { ticks: { font: { size: 9 }, callback: v => v + '%' }, min: 0 },
        },
        animation: { duration: 200 },
      }, demo.enabled),
    })
  }
}

watch(() => store.proba, renderCharts)
watch(() => demo.enabled, renderCharts)
onMounted(renderCharts)
onUnmounted(() => {
  if (donutChart) donutChart.destroy()
  if (barChart)   barChart.destroy()
})
</script>
