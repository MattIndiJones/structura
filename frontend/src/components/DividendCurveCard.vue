<template>
  <div class="card mt-4">
    <div class="flex items-center gap-3 mb-3">
      <label v-if="activeUnderlying" class="flex items-center gap-2 cursor-pointer select-none">
        <div class="relative w-9 h-5">
          <input type="checkbox" class="sr-only"
            :checked="activeUnderlying.dividendCurveEnabled"
            @change="activeUnderlying.dividendCurveEnabled = !activeUnderlying.dividendCurveEnabled" />
          <div class="w-9 h-5 rounded-full transition-colors"
            :class="activeUnderlying.dividendCurveEnabled ? 'bg-blue-600' : 'bg-slate-700'"></div>
          <div class="absolute top-0.5 left-0.5 w-4 h-4 bg-white rounded-full shadow transition-transform"
            :class="activeUnderlying.dividendCurveEnabled ? 'translate-x-4' : 'translate-x-0'"></div>
        </div>
        <span class="text-xs font-bold text-slate-400 uppercase tracking-wider">
          Courbe de dividende
        </span>
        <HelpTip width="w-80"
          text="Courbe de rendement de dividende par sous-jacent. q₁ est constant sur la première année puis chaque bucket annuel décroît du pourcentage choisi. Le moteur applique la dernière année au prorata si la maturité n'est pas entière." />
      </label>

      <span v-if="activeUnderlying && !activeUnderlying.dividendCurveEnabled"
        class="ml-auto text-xs text-slate-600">
        Dividende plat q&nbsp;=&nbsp;
        <span class="text-slate-400"><SensitiveValue>{{ formatRate(activeUnderlying.q) }}</SensitiveValue></span>
      </span>
      <div v-else-if="activeUnderlying" class="ml-auto flex gap-1.5">
        <span class="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full bg-slate-800 border border-slate-700">
          <span class="text-slate-500">1A</span>
          <span class="text-blue-400 font-mono font-semibold"><SensitiveValue>{{ formatRate(activeUnderlying.q) }}</SensitiveValue></span>
        </span>
        <span class="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full bg-slate-800 border border-slate-700">
          <span class="text-slate-500">Échéance</span>
          <span class="text-blue-400 font-mono font-semibold"><SensitiveValue>{{ formatRate(lastRate) }}</SensitiveValue></span>
        </span>
      </div>
    </div>

    <div v-if="paniers.length > 1" class="flex gap-1 mb-3 flex-wrap">
      <button v-for="(u, index) in paniers" :key="index"
        class="text-xs px-2.5 py-1 rounded border transition-colors"
        :class="index === actif
          ? 'bg-blue-600/20 border-blue-500 text-blue-400'
          : 'bg-slate-800 border-slate-700 text-slate-400 hover:border-blue-500'"
        @click="choisir(index)">
        {{ demo.underlyingLabel(u.name, index) }}
      </button>
    </div>

    <template v-if="activeUnderlying?.dividendCurveEnabled">
      <div class="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-3">
        <div class="rounded-lg border border-slate-700 bg-slate-800/50 px-3 py-2">
          <div class="text-[10px] uppercase tracking-wider text-slate-500 mb-1">q première année — valeur utilisée</div>
          <div class="font-mono text-sm font-semibold text-slate-200">
            <SensitiveValue>{{ formatRate(activeUnderlying.q) }}</SensitiveValue>
          </div>
          <div class="text-[10px] text-slate-600 mt-1">Modifiable dans la calibration du sous-jacent ci-dessus.</div>
        </div>
        <div>
          <label class="label">Décroissance annuelle (%)
            <HelpTip width="w-72"
              text="Pourcentage relatif retranché chaque année : avec q₁ = 4 % et une décroissance de 10 %, q₂ = 3,60 %, q₃ = 3,24 %. Une valeur de 0 % reproduit exactement un dividende plat." />
          </label>
          <SensitiveValue mode="input">
            <div class="relative">
              <input type="number" min="0" max="100" step="1" class="input pr-7"
                :value="activeUnderlying.dividendDecay"
                @input="setDecay($event.target.value)" />
              <span class="absolute right-2 top-1/2 -translate-y-1/2 text-xs text-slate-500 pointer-events-none">%</span>
            </div>
          </SensitiveValue>
        </div>
      </div>

      <div class="overflow-x-auto mb-3">
        <div class="flex gap-1 min-w-max">
          <div v-for="node in nodes" :key="node.T"
            class="min-w-[58px] rounded border border-slate-700 bg-slate-900 px-2 py-1 text-center">
            <div class="text-[10px] text-slate-600">{{ node.label }}</div>
            <div class="text-xs text-slate-300 font-mono"><SensitiveValue>{{ formatRate(node.rate) }}</SensitiveValue></div>
          </div>
        </div>
      </div>

      <SensitiveChart>
        <div style="height:88px;position:relative;">
          <canvas ref="curveCanvas"></canvas>
        </div>
      </SensitiveChart>

      <div class="text-[10px] text-slate-600 mt-2">
        Buckets constants : (0,1A], (1A,2A], etc. · qₙ = q₁ × (1 − décroissance)ⁿ⁻¹
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import {
  Chart, LineController, LineElement, LinearScale, PointElement, Tooltip,
} from 'chart.js'
import { usePricingStore } from '../stores/pricing.js'
import { courbeDividende } from '../composables/useDividendCurve.js'
import { useDemoModeStore } from '../stores/demoMode.js'
import { demoChartOptions } from '../composables/useSensitiveChart.js'
import { applyChartTheme, axisTick, chartTheme } from '../charts/theme.js'
import HelpTip from './HelpTip.vue'
import SensitiveChart from './SensitiveChart.vue'
import SensitiveValue from './SensitiveValue.vue'

Chart.register(LineController, LineElement, PointElement, LinearScale, Tooltip)
applyChartTheme(Chart)

const props = defineProps({
  // Le panier à éditer. Absent, celui du Pricer : les usages existants ne
  // changent pas, et l'appel d'offres passe le sien sans partager d'état.
  sousJacents: { type: Array, default: null },
  indexActif: { type: Number, default: null },
  // Horizon de la courbe, en années. C'est lui qui fixe le nombre de nœuds.
  horizon: { type: Number, default: null },
})
const emit = defineEmits(['update:indexActif'])

const store = usePricingStore()
const paniers = computed(() => props.sousJacents ?? store.underlyings)
const actif = computed(() => props.indexActif ?? store.activeUnderlyingIdx)
const horizonAns = computed(() => props.horizon ?? store.globalParams.T)

function choisir(i) {
  if (props.sousJacents) emit('update:indexActif', i)
  else store.activeUnderlyingIdx = i
}
const demo = useDemoModeStore()
const curveCanvas = ref(null)
let chart = null

const activeUnderlying = computed(() =>
  paniers.value[actif.value] ?? paniers.value[0])
const nodes = computed(() => courbeDividende(activeUnderlying.value, horizonAns.value))
const lastRate = computed(() => nodes.value.at(-1)?.rate ?? activeUnderlying.value?.q ?? 0)

function formatRate(value) {
  const number = Number(value) || 0
  return `${number.toFixed(2).replace('.', ',')}%`
}

function setDecay(rawValue) {
  const value = Number(rawValue)
  if (Number.isFinite(value)) activeUnderlying.value.dividendDecay = Math.max(0, Math.min(100, value))
}

async function renderChart() {
  if (!activeUnderlying.value?.dividendCurveEnabled) {
    if (chart) { chart.destroy(); chart = null }
    return
  }
  await nextTick()
  await new Promise(resolve => requestAnimationFrame(resolve))
  if (!curveCanvas.value) return
  if (chart) { chart.destroy(); chart = null }

  const horizon = Math.max(1, Number(horizonAns.value) || 1)
  const data = []
  nodes.value.forEach((node, index) => {
    const start = index
    if (start < horizon) {
      data.push({ x: start, y: node.rate })
      data.push({ x: Math.min(node.T, horizon), y: node.rate })
    }
  })

  chart = new Chart(curveCanvas.value, {
    type: 'line',
    data: {
      datasets: [{
        data,
        borderColor: chartTheme.primary,
        backgroundColor: chartTheme.primarySoft,
        borderWidth: 1.8,
        pointRadius: 2,
        pointBackgroundColor: chartTheme.primary,
        fill: false,
      }],
    },
    options: demoChartOptions({
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: 80 },
      parsing: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: item => `${item.raw.y.toFixed(2).replace('.', ',')}% @ ${item.raw.x.toFixed(2).replace('.', ',')}A`,
          },
        },
      },
      scales: {
        x: {
          type: 'linear', min: 0, max: horizon,
          ticks: { font: { size: 8 }, callback: axisTick('A', 0) },
        },
        y: {
          beginAtZero: true,
          ticks: { font: { size: 8 }, callback: axisTick('%') },
        },
      },
    }, demo.enabled),
  })
}

const chartKey = computed(() => {
  const u = activeUnderlying.value
  if (!u?.dividendCurveEnabled) return null
  return [actif.value, u.q, u.dividendDecay, horizonAns.value].join('|')
})

watch(chartKey, renderChart)
watch(() => activeUnderlying.value?.dividendCurveEnabled, renderChart)
watch(() => demo.enabled, renderChart)
onMounted(renderChart)
onUnmounted(() => { if (chart) chart.destroy() })
</script>
