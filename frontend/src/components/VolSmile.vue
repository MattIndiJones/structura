<template>
  <div v-if="showSmile" class="mt-3 pt-3 border-t border-slate-700">
    <div class="flex items-center justify-between mb-1">
      <span class="text-xs font-bold text-slate-400 uppercase tracking-wide">{{ title }}</span>
      <span class="text-xs text-slate-600"><SensitiveValue>60%–140% · {{ tsLabel }}</SensitiveValue></span>
    </div>
    <SensitiveChart>
      <div style="height:180px;position:relative;">
        <canvas ref="canvas"></canvas>
      </div>
    </SensitiveChart>
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
import {
  Chart, LineElement, LineController, PointElement,
  LinearScale, CategoryScale, Tooltip, Legend,
} from 'chart.js'

Chart.register(LineElement, LineController, PointElement, LinearScale, CategoryScale, Tooltip, Legend)
applyChartTheme(Chart)

const props = defineProps({ idx: { type: Number, required: true } })
const store = usePricingStore()
const demo = useDemoModeStore()
const canvas = ref(null)
let chart = null

const showSmile = computed(() =>
  ['localvol', 'heston', 'sabr', 'lsv'].includes(store.globalParams.model)
)

const title = computed(() => {
  const m = store.globalParams.model
  return m === 'localvol' ? 'DUPIRE SMILE Σ(K)'
    : m === 'lsv' ? 'DUPIRE SMILE Σ(K) — cible de calibration LSV'
    : m === 'heston' ? 'HESTON SMILE Σ(K) — approx.'
    : 'SABR SMILE Σ(K) — Hagan 2002'
})

const tsLabel = computed(() => {
  const T = store.globalParams.T
  const ts = buildTs(T)
  return ts.map(t => `T=${t}Y`).join(', ')
})

function buildTs(Tmax) {
  const raw = [0.5, 1, 2, 3].filter(t => t < Tmax)
  raw.push(Tmax)
  return [...new Set(raw)].sort((a, b) => a - b).slice(0, 4)
}

// ── SABR Hagan 2002 ─────────────────────────────────────────────────
function sabrVol(K, T, alpha, beta, rho, nu) {
  if (T <= 0 || alpha <= 0 || K <= 0) return alpha
  const F = 1.0, eps = 1e-8
  const logFK = Math.log(F / K)
  const a1 = (1 - beta) ** 2 / 24 * alpha ** 2
  const a3 = (2 - 3 * rho ** 2) / 24 * nu ** 2
  if (Math.abs(logFK) < eps) {
    const Fb = Math.pow(F, 1 - beta)
    const a2 = 0.25 * rho * beta * nu * alpha / Fb
    return Math.max(0.001, alpha / Fb * (1 + (a1 / (Fb * Fb) + a2 + a3) * T))
  }
  const FK = F * K
  const FKp = Math.pow(FK, (1 - beta) / 2)
  const z = nu / alpha * FKp * logFK
  const disc = Math.sqrt(Math.max(0, 1 - 2 * rho * z + z ** 2))
  const xz = Math.log(Math.max(eps, (disc + z - rho) / (1 - rho)))
  const A = alpha / (FKp * (1 + (1 - beta) ** 2 / 24 * logFK ** 2 + (1 - beta) ** 4 / 1920 * logFK ** 4))
  const B = Math.abs(xz) > eps ? z / xz : 1
  const FK1b = Math.pow(FK, 1 - beta)
  const a2 = 0.25 * rho * beta * nu * alpha / FKp
  return Math.max(0.001, A * B * (1 + (a1 / FK1b + a2 + a3) * T))
}

// ── Heston first-order approximation ────────────────────────────────
function hestonVol(K, T, v0, kappa, theta, xi, rho_h) {
  const kt = kappa * Math.max(T, 0.01)
  const vbar = kt > 1e-6 ? theta + (v0 - theta) * (1 - Math.exp(-kt)) / kt : v0
  const vSafe = Math.max(1e-6, vbar)
  const sigATM = Math.sqrt(vSafe)
  const logK = Math.log(Math.max(K, 1e-6))
  const skewH = rho_h * xi / 2
  const curvH = xi ** 2 * (1 - rho_h ** 2) / (4 * vSafe)
  return Math.max(0.001, sigATM + skewH * logK + curvH * logK ** 2)
}

const COLORS = chartTheme.series.slice(0, 4)

function computeData() {
  const u = store.underlyings[props.idx]
  if (!u) return null
  const model = store.globalParams.model
  const Tmax = store.globalParams.T
  const Ts = buildTs(Tmax)

  const nK = 41
  const moneyness = Array.from({ length: nK }, (_, i) => 0.60 + i * 0.80 / (nK - 1))
  const labels = moneyness.map(k => (k * 100).toFixed(0) + '%')

  const datasets = Ts.map((T, ti) => ({
    label: `T=${T}Y`,
    data: moneyness.map(K => {
      let v
      if (model === 'localvol' || model === 'lsv') {
        const sig0 = u.sigma / 100
        const sk   = u.skew / 100
        const cv   = u.curvature / 100
        v = Math.max(0.001, sig0 + sk * Math.log(K) + cv * Math.log(K) ** 2)
      } else if (model === 'sabr') {
        v = sabrVol(K, T, u.alpha / 100, u.beta / 100, u.rho / 100, u.nu / 100)
      } else {
        v = hestonVol(K, T, u.v0 / 100, u.kappa, u.theta / 100, u.xi / 100, u.rho_h / 100)
      }
      return +(v * 100).toFixed(2)
    }),
    borderColor: COLORS[ti],
    backgroundColor: 'transparent',
    borderWidth: ti === 0 ? 2.2 : 1.5,
    pointRadius: moneyness.map(k => Math.abs(k - 1) < 0.015 ? 4 : 0),
    pointBackgroundColor: COLORS[ti],
    tension: 0.35,
    fill: false,
  }))

  return { labels, datasets }
}

async function renderChart() {
  if (!showSmile.value) { if (chart) { chart.destroy(); chart = null }; return }
  await nextTick()
  // Wait for browser layout pass (canvas has no size until paint)
  await new Promise(r => requestAnimationFrame(r))
  if (!canvas.value) return
  if (chart) { chart.destroy(); chart = null }
  const d = computeData()
  if (!d) return

  chart = new Chart(canvas.value, {
    type: 'line',
    data: { labels: d.labels, datasets: d.datasets },
    options: demoChartOptions({
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: 150 },
      plugins: {
        legend: {
          display: d.datasets.length > 1,
          position: 'top',
          labels: { font: { size: 9 }, boxWidth: 16, padding: 6 },
        },
        tooltip: {
          mode: 'index',
          intersect: false,
          callbacks: { label: it => `${it.dataset.label}: ${it.raw.toFixed(1).replace('.', ',')}%` },
        },
      },
      scales: {
        x: {
          title: { display: true, text: 'Moneyness K/F', font: { size: 8 } },
          ticks: { font: { size: 8 }, maxTicksLimit: 9 },
        },
        y: {
          title: { display: true, text: 'Vol implicite (%)', font: { size: 8 } },
          ticks: { font: { size: 9 }, callback: v => v + '%' },
        },
      },
    }, demo.enabled),
  })
}

// Reactive key — triggers redraw when any relevant param changes
const smileKey = computed(() => {
  const model = store.globalParams.model
  const T = store.globalParams.T
  const u = store.underlyings[props.idx]
  if (!u || !showSmile.value) return null
  if (model === 'localvol' || model === 'lsv')
    return `lv|${u.sigma}|${u.skew}|${u.curvature}|${T}`
  if (model === 'heston')
    return `h|${u.v0}|${u.kappa}|${u.theta}|${u.xi}|${u.rho_h}|${T}`
  return `s|${u.alpha}|${u.beta}|${u.rho}|${u.nu}|${T}`
})

// Watch param changes (within same model)
watch(smileKey, renderChart)
// Watch model switch: showSmile goes false→true, need DOM to mount first
watch(showSmile, (val) => { if (val) renderChart() })
watch(() => demo.enabled, renderChart)
onMounted(renderChart)
onUnmounted(() => { if (chart) chart.destroy() })
</script>
