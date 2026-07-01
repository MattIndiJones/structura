<template>
  <div class="flex flex-col gap-4">
    <!-- Header + controls -->
    <div class="card">
      <div class="flex items-center gap-3 flex-wrap mb-3">
        <div class="text-xs font-bold text-slate-400 uppercase tracking-wider">🗺️ Mark to Future</div>
        <div class="ml-auto">
          <button class="btn-primary text-xs px-4" :disabled="store.loading || !store.result" @click="launch">
            <span v-if="store.loading" class="w-3 h-3 border border-white border-t-transparent rounded-full animate-spin inline-block mr-1"></span>
            ▶ Lancer
          </button>
        </div>
      </div>

      <div class="text-xs text-slate-400 leading-relaxed bg-slate-800/50 border-l-2 border-blue-500 rounded-lg px-3 py-2 mb-4">
        <strong class="text-slate-200">Nested Monte Carlo risque-neutre.</strong>
        Pour chaque date MTM, N<sub>outer</sub> scénarios de marché sont simulés (GBM, paramètres gelés à
        aujourd'hui), puis le produit résiduel est re-pricé sous le modèle choisi avec N<sub>inner</sub> chemins.
        Résultat : la <em>distribution future des valeurs mark-to-model</em> du produit — pas une prévision
        économique.
      </div>

      <div class="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs mb-2">
        <div>
          <label class="label">N outer</label>
          <SensitiveValue mode="input"><input v-model.number="form.n_outer" type="number" step="50" min="20" max="2000" class="input" /></SensitiveValue>
        </div>
        <div>
          <label class="label">N inner</label>
          <SensitiveValue mode="input"><input v-model.number="form.n_inner" type="number" step="100" min="50" max="5000" class="input" /></SensitiveValue>
        </div>
        <div>
          <label class="label">Dates MTM</label>
          <SensitiveValue mode="input"><input v-model.number="form.n_dates" type="number" step="1" min="2" max="12" class="input" /></SensitiveValue>
        </div>
        <div>
          <label class="label">Seed</label>
          <SensitiveValue mode="input"><input v-model.number="form.seed" type="number" class="input" /></SensitiveValue>
        </div>
      </div>
      <div class="text-xs text-slate-600">
        <SensitiveValue>
          Coût ≈ N<sub>outer</sub> × N<sub>dates</sub> × N<sub>inner</sub> évaluations de pricer
          ({{ (form.n_outer * form.n_dates * form.n_inner).toLocaleString() }} au total).
        </SensitiveValue>
      </div>
      <div v-if="!store.result" class="text-xs text-amber-500 mt-2">
        Lancez d'abord un pricing (▶ Pricer) pour fixer le prix de référence P₀.
      </div>
    </div>

    <!-- Empty state -->
    <div v-if="!store.mtf" class="flex flex-col items-center justify-center h-52 text-slate-600 gap-2">
      <div class="text-3xl">🗺️</div>
      <div class="text-sm font-medium">Configurez les paramètres et lancez le Mark to Future</div>
      <div class="text-xs">Distribution des valeurs futures du produit sous mesure risque-neutre</div>
    </div>

    <template v-else>
      <!-- Fan chart -->
      <div class="card">
        <div class="text-xs font-bold text-slate-500 uppercase tracking-wide mb-3">
          Distribution future du prix (% notionnel) — bandes P05/P95 et P25/P75
        </div>
        <SensitiveChart>
          <div style="height:280px;position:relative;">
            <canvas ref="fanCanvas"></canvas>
          </div>
        </SensitiveChart>
      </div>

      <!-- Scalar sanity tiles (last MTM date) -->
      <div class="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div v-for="s in scalarTiles" :key="s.label" class="stat-box">
          <div class="text-xs text-slate-500 mb-1">{{ s.label }}</div>
          <div class="text-lg font-bold" :class="s.cls"><SensitiveValue>{{ s.val }}</SensitiveValue></div>
        </div>
      </div>

      <!-- Stats table -->
      <div class="card overflow-x-auto">
        <div class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3">Statistiques par date MTM</div>
        <table class="w-full text-xs border-collapse">
          <thead>
            <tr class="border-b border-slate-700 text-slate-500">
              <th class="text-left py-1.5 pr-3 font-semibold">Date</th>
              <th class="text-right py-1.5 pr-3 font-semibold">E(MTM)</th>
              <th class="text-right py-1.5 pr-3 font-semibold">σ</th>
              <th class="text-right py-1.5 pr-3 font-semibold">P05</th>
              <th class="text-right py-1.5 pr-3 font-semibold">P25</th>
              <th class="text-right py-1.5 pr-3 font-semibold">P50</th>
              <th class="text-right py-1.5 pr-3 font-semibold">P75</th>
              <th class="text-right py-1.5 pr-3 font-semibold">P95</th>
              <th class="text-right py-1.5 pr-3 font-semibold whitespace-nowrap">P(&gt;100%)</th>
              <th class="text-right py-1.5 font-semibold whitespace-nowrap">P(&ge;P&#8320;)</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in store.mtf.results" :key="r.t" class="border-b border-slate-800/50">
              <td class="py-1.5 pr-3 text-slate-300 font-semibold whitespace-nowrap">{{ r.t.toFixed(2) }}Y</td>
              <td class="py-1.5 pr-3 text-right font-mono text-blue-400"><SensitiveValue>{{ pf(r.stats.mean) }}</SensitiveValue></td>
              <td class="py-1.5 pr-3 text-right font-mono text-slate-400"><SensitiveValue>{{ pf(r.stats.std) }}</SensitiveValue></td>
              <td class="py-1.5 pr-3 text-right font-mono text-red-400"><SensitiveValue>{{ pf(r.stats.p05) }}</SensitiveValue></td>
              <td class="py-1.5 pr-3 text-right font-mono text-slate-300"><SensitiveValue>{{ pf(r.stats.p25) }}</SensitiveValue></td>
              <td class="py-1.5 pr-3 text-right font-mono text-slate-200 font-semibold"><SensitiveValue>{{ pf(r.stats.p50) }}</SensitiveValue></td>
              <td class="py-1.5 pr-3 text-right font-mono text-slate-300"><SensitiveValue>{{ pf(r.stats.p75) }}</SensitiveValue></td>
              <td class="py-1.5 pr-3 text-right font-mono text-green-400"><SensitiveValue>{{ pf(r.stats.p95) }}</SensitiveValue></td>
              <td class="py-1.5 pr-3 text-right font-mono"
                  :class="r.stats.p_above_100 >= 50 ? 'text-green-400' : 'text-red-400'">
                <SensitiveValue>{{ r.stats.p_above_100.toFixed(1) }}%</SensitiveValue>
              </td>
              <td class="py-1.5 text-right font-mono"
                  :class="r.stats.p_above_p0 >= 50 ? 'text-green-400' : 'text-red-400'">
                <SensitiveValue>{{ r.stats.p_above_p0.toFixed(1) }}%</SensitiveValue>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- CSV export -->
      <div class="flex gap-2">
        <button class="btn-secondary text-xs" @click="exportCsv('summary')">⬇ Summary CSV</button>
        <button class="btn-secondary text-xs" @click="exportCsv('runs')">⬇ Runs CSV</button>
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
  Chart, LineElement, LineController, PointElement,
  CategoryScale, LinearScale, Filler, Tooltip, Legend,
} from 'chart.js'

Chart.register(LineElement, LineController, PointElement, CategoryScale, LinearScale, Filler, Tooltip, Legend)

const store = usePricingStore()
const demo = useDemoModeStore()
const fanCanvas = ref(null)
let fanChart = null

const form = ref({ n_outer: 200, n_inner: 500, n_dates: 5, seed: 42 })

function launch() {
  store.runMtf({ ...form.value })
}

const pf = v => v.toFixed(2) + '%'

// Sanity-check tiles for the furthest MTM date — the 4 diagnostics a quant would
// check first: tail risk above par, probability of beating the entry price, and
// the two expectation-based metrics (should track the forward price under
// no-arbitrage).
const scalarTiles = computed(() => {
  const res = store.mtf?.results
  if (!res?.length) return []
  const last = res[res.length - 1]
  const lbl = last.t.toFixed(1) + 'Y'
  return [
    { label: `P(MTM>100%) @ ${lbl}`, val: last.stats.p_above_100.toFixed(1) + '%',
      cls: last.stats.p_above_100 >= 50 ? 'text-green-400' : 'text-red-400' },
    { label: `P(MTM≥P₀) @ ${lbl}`, val: last.stats.p_above_p0.toFixed(1) + '%',
      cls: last.stats.p_above_p0 >= 50 ? 'text-green-400' : 'text-red-400' },
    { label: `E(MTM) @ ${lbl}`, val: pf(last.stats.e_mtm), cls: 'text-blue-400' },
    { label: `E(max(MTM-100,0)) @ ${lbl}`, val: pf(last.stats.e_upside), cls: 'text-green-400' },
  ]
})

async function renderChart() {
  await nextTick()
  if (!store.mtf || !fanCanvas.value) return
  if (fanChart) { fanChart.destroy(); fanChart = null }

  const p0 = store.mtf.main_price ?? 100
  const results = store.mtf.results
  const labels = ['t₀', ...results.map(r => r.t.toFixed(2) + 'Y')]
  const mk = key => [p0, ...results.map(r => r.stats[key])]

  // Dataset order matters for fill:'-1' (fills toward the previous dataset).
  fanChart = new Chart(fanCanvas.value, {
    type: 'line',
    data: {
      labels,
      datasets: [
        { label: 'P95', data: mk('p95'), fill: false, borderColor: 'rgba(59,130,246,.25)', borderWidth: 1, pointRadius: 0, tension: .3, borderDash: [3, 3] },
        { label: 'P05', data: mk('p05'), fill: '-1', backgroundColor: 'rgba(59,130,246,.08)', borderColor: 'rgba(59,130,246,.25)', borderWidth: 1, pointRadius: 0, tension: .3, borderDash: [3, 3] },
        { label: 'P75', data: mk('p75'), fill: false, borderColor: 'rgba(59,130,246,.5)', borderWidth: 1.5, pointRadius: 0, tension: .3 },
        { label: 'P25', data: mk('p25'), fill: '-1', backgroundColor: 'rgba(59,130,246,.16)', borderColor: 'rgba(59,130,246,.5)', borderWidth: 1.5, pointRadius: 0, tension: .3 },
        { label: 'Médiane', data: mk('p50'), fill: false, borderColor: '#3b82f6', borderWidth: 2.5, pointRadius: 3, pointBackgroundColor: '#3b82f6', tension: .3 },
        { label: 'Moyenne', data: mk('mean'), fill: false, borderColor: '#f59e0b', borderWidth: 1.5, pointRadius: 0, tension: .3, borderDash: [5, 3] },
        { label: 'P99', data: mk('p99'), fill: false, borderColor: 'rgba(239,68,68,.35)', borderWidth: 1, pointRadius: 0, tension: .3, borderDash: [2, 4] },
        { label: 'P01', data: mk('p01'), fill: false, borderColor: 'rgba(239,68,68,.35)', borderWidth: 1, pointRadius: 0, tension: .3, borderDash: [2, 4] },
      ],
    },
    options: demoChartOptions({
      responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { position: 'bottom', labels: { color: '#94a3b8', font: { size: 10 }, boxWidth: 12 } },
        tooltip: {
          mode: 'index', intersect: false,
          callbacks: { label: it => `${it.dataset.label}: ${it.raw?.toFixed?.(2)}%` },
        },
      },
      scales: {
        x: { ticks: { color: '#475569', font: { size: 10 } }, grid: { color: '#1e293b' } },
        y: { ticks: { color: '#475569', font: { size: 9 }, callback: v => v + '%' }, grid: { color: '#1e293b' } },
      },
      animation: { duration: 250 },
    }, demo.enabled),
  })
}

function exportCsv(type) {
  if (!store.mtf) return
  const { results } = store.mtf
  let csv, filename

  if (type === 'runs') {
    const lines = ['scenario,date_mtm_y,pv_pct']
    results.forEach(r => r.pvs.forEach((pv, i) => lines.push(`${i},${r.t.toFixed(4)},${pv.toFixed(4)}`)))
    csv = lines.join('\n'); filename = 'mtf_runs.csv'
  } else {
    const lines = ['date_mtm_y,e_mtm,std,p01,p05,p25,p50,p75,p95,p99,p_above_100pct,p_above_p0,e_upside']
    results.forEach(r => {
      const s = r.stats
      lines.push([r.t, s.mean, s.std, s.p01, s.p05, s.p25, s.p50, s.p75, s.p95, s.p99,
        s.p_above_100 / 100, s.p_above_p0 / 100, s.e_upside].map(v => v.toFixed(4)).join(','))
    })
    csv = lines.join('\n'); filename = 'mtf_summary.csv'
  }

  const a = Object.assign(document.createElement('a'), {
    href: URL.createObjectURL(new Blob([csv], { type: 'text/csv' })),
    download: filename,
  })
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
}

watch(() => store.mtf, renderChart)
watch(() => demo.enabled, renderChart)
onMounted(renderChart)
onUnmounted(() => { if (fanChart) fanChart.destroy() })
</script>
