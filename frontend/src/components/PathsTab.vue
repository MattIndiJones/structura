<template>
  <div class="flex flex-col gap-4">
    <!-- Header -->
    <div class="card">
      <div class="flex items-center gap-3 flex-wrap">
        <div>
          <div class="text-xs font-bold text-slate-400 uppercase tracking-wider">🔀 Chemins Monte Carlo
            <HelpTip width="w-72" text="Simulation dédiée et indépendante du pricing principal : 500 chemins tirés pour ce visuel (pas les N chemins de l'onglet Résultats), dont seulement 50 sont affichés pour rester lisible. Les % de la légende sont calculés sur les 500, pas sur les 50 dessinés — mais restent un échantillon plus petit que le pricing principal, donc à lire comme indicatif, pas comme la probabilité de référence (voir onglet Probabilités pour ça)." />
          </div>
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
      <LocalVolWingNotice :wings="store.paths.local_vol_wings" />
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
          <strong :style="{ color: lg.solid }"><SensitiveValue>{{ formatPercent(lg.pct, 1) }}</SensitiveValue></strong>
          <span class="text-slate-600"><SensitiveValue>({{ lg.count }}/{{ store.paths.total }})</SensitiveValue></span>
        </span>
      </div>
    </div>

    <section v-if="store.paths && 'local_vol_trace' in store.paths" class="card">
      <div class="text-xs font-bold uppercase tracking-wider">Dupire · Passage sous 60 %</div>
      <p v-if="!localVolTrace" class="mt-2 text-sm text-slate-600">
        Aucun franchissement sous 60 % avant la sortie du produit dans cette simulation.
      </p>
      <template v-else>
        <p class="mt-2 text-xs text-slate-600">
          Trajectoire choisie dans la simulation de cet onglet. La vol locale est lue au spot de début du pas.
          Le pas suivant utilise la vol locale au nouveau spot.
        </p>
        <div class="table-shell overflow-x-auto mt-3">
          <table>
            <thead><tr>
              <th>Pas</th><th>Temps (années)</th><th>Spot début (% réf.)</th>
              <th>Vol locale utilisée</th><th>Spot fin (% réf.)</th>
            </tr></thead>
            <tbody>
              <tr v-for="row in visibleTraceSteps" :key="row.step"
                :class="{ 'bg-amber-100': row.step === localVolTrace.crossing_step }">
                <td>{{ row.step }}<span v-if="row.step === localVolTrace.crossing_step"> · Franchissement</span></td>
                <td>{{ formatTraceTime(row.start_time) }} → {{ formatTraceTime(row.end_time) }}</td>
                <td><SensitiveValue>{{ formatPercent(row.start_spot * 100, 2) }}</SensitiveValue></td>
                <td><SensitiveValue>{{ formatPercent(row.local_vol * 100, 2) }}</SensitiveValue></td>
                <td><SensitiveValue>{{ formatPercent(row.end_spot * 100, 2) }}</SensitiveValue></td>
              </tr>
            </tbody>
          </table>
        </div>
        <button v-if="showFullTrace || visibleTraceSteps.length < localVolTrace.steps.length"
          type="button" class="btn-secondary text-xs mt-3"
          :aria-expanded="showFullTrace" @click="showFullTrace = !showFullTrace">
          {{ showFullTrace ? 'Revenir autour du franchissement' : 'Afficher tous les pas' }}
        </button>
      </template>
    </section>
  </div>
</template>

<script setup>
import { ref, computed, watch, nextTick, onMounted, onUnmounted } from 'vue'
import { usePricingStore } from '../stores/pricing.js'
import { useDemoModeStore } from '../stores/demoMode.js'
import { demoChartOptions } from '../composables/useSensitiveChart.js'
import { applyChartTheme, axisNumber, chartTheme } from '../charts/theme.js'
import SensitiveValue from './SensitiveValue.vue'
import LocalVolWingNotice from './LocalVolWingNotice.vue'
import SensitiveChart from './SensitiveChart.vue'
import HelpTip from './HelpTip.vue'
import { formatPercent } from '../utils/format.js'
import {
  Chart, LineElement, LineController, PointElement,
  LinearScale, Tooltip
} from 'chart.js'

Chart.register(LineElement, LineController, PointElement, LinearScale, Tooltip)
applyChartTheme(Chart)

const store = usePricingStore()
const demo = useDemoModeStore()
const chartCanvas = ref(null)
const showFullTrace = ref(false)
const localVolTrace = computed(() => store.paths?.local_vol_trace)
const visibleTraceSteps = computed(() => {
  const trace = localVolTrace.value
  if (!trace) return []
  if (showFullTrace.value) return trace.steps
  return trace.steps.filter(row => Math.abs(row.step - trace.crossing_step) <= 5)
})
const formatTraceTime = value => value.toLocaleString('fr-FR', { maximumFractionDigits: 3 })
let chartInstance = null

const yAxisLabel = computed(() => {
  const uls = store.underlyings
  if (!uls || uls.length === 0) return 'WOF (% initial)'
  if (uls.length === 1) return `${demo.underlyingLabel(uls[0].name, 0)} (% initial)`
  const names = uls.map((u, i) => demo.underlyingLabel(u.name, i)).join(', ')
  return `WOF [${names}] (% initial)`
})

const COLORS = {
  autocall: { stroke: 'rgba(26,122,74,0.35)', solid: chartTheme.positive, label: 'Rappel autocall' },
  ki:       { stroke: 'rgba(192,57,43,0.35)', solid: chartTheme.negative, label: 'KI / Perte en capital' },
  normal:   { stroke: 'rgba(122,116,105,0.30)', solid: chartTheme.ticks, label: 'Remboursement normal' },
}


const legend = computed(() => {
  if (!store.paths) return []
  const { autocall_count, ki_count, normal_count, total } = store.paths
  const pct = n => total > 0 ? n / total * 100 : 0
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
    const col = COLORS[p.outcome]?.stroke || 'rgba(122,116,105,0.3)'
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
      borderColor: chartTheme.gold, borderWidth: 1.5, borderDash: [6, 4],
      pointRadius: 0, fill: false, label: `AC_BAR ${(up.AC_BAR*100).toFixed(0)}%`,
    })
  }
  if (up.KI_BAR != null) {
    datasets.push({
      data: [{ x: 0, y: up.KI_BAR * 100 }, { x: T, y: up.KI_BAR * 100 }],
      borderColor: chartTheme.negative, borderWidth: 1.5, borderDash: [6, 4],
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
          callbacks: {
            label: it => `${it.raw.y.toLocaleString('fr-FR', { minimumFractionDigits: 1, maximumFractionDigits: 1 })} % à T=${it.raw.x.toLocaleString('fr-FR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} an`,
          },
        },
      },
      scales: {
        x: {
          type: 'linear', min: 0, max: T,
          title: { display: true, text: 'Temps (années)', font: { size: 9 } },
          ticks: {
            autoSkip: true,
            maxTicksLimit: 7,
            maxRotation: 0,
            font: { size: 9 },
            callback: (value, _index, ticks) => axisNumber(value, ticks, 2),
          },
        },
        y: {
          title: { display: true, text: yAxisLabel.value, font: { size: 9 } },
          ticks: {
            maxTicksLimit: 7,
            font: { size: 9 },
            callback: (value, _index, ticks) => `${axisNumber(value, ticks)} %`,
          },
        },
      },
    }, demo.enabled),
  })
}

watch(() => store.paths, () => {
  showFullTrace.value = false
  renderChart()
})
watch(() => demo.enabled, renderChart)
onMounted(renderChart)
onUnmounted(() => { if (chartInstance) chartInstance.destroy() })
</script>
