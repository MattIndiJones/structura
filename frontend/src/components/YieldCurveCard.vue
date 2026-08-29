<template>
  <div class="card mt-4">
    <!-- Header -->
    <div class="flex items-center gap-3 mb-3">
      <label class="flex items-center gap-2 cursor-pointer select-none">
        <div class="relative w-9 h-5">
          <input type="checkbox" class="sr-only" :checked="courbe.enabled"
            @change="courbe.enabled = !courbe.enabled" />
          <div class="w-9 h-5 rounded-full transition-colors"
            :class="courbe.enabled ? 'bg-blue-600' : 'bg-slate-700'"></div>
          <div class="absolute top-0.5 left-0.5 w-4 h-4 bg-white rounded-full shadow transition-transform"
            :class="courbe.enabled ? 'translate-x-4' : 'translate-x-0'"></div>
        </div>
        <span class="text-xs font-bold text-slate-400 uppercase tracking-wider">Courbe de taux</span>
      </label>

      <!-- Key rates chips (shown when enabled) -->
      <template v-if="courbe.enabled">
        <div class="ml-auto flex gap-1.5">
          <span v-for="k in keyRates" :key="k.label"
            class="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full bg-slate-800 border border-slate-700">
            <span class="text-slate-500">{{ k.label }}</span>
            <span class="text-blue-400 font-mono font-semibold"><SensitiveValue>{{ formatPercent(k.rate, 2) }}</SensitiveValue></span>
          </span>
        </div>
      </template>

      <!-- Flat rate info when disabled -->
      <span v-else class="ml-auto text-xs text-slate-600">
        Taux plat r&nbsp;=&nbsp;<span class="text-slate-400"><SensitiveValue>{{ tauxPlat }}%</SensitiveValue></span>
      </span>
    </div>

    <template v-if="courbe.enabled">
      <!-- Scenario presets -->
      <div class="flex gap-1.5 mb-3 flex-wrap">
        <button v-for="s in SCENARIOS" :key="s.label"
          @click="applyScenario(s)"
          class="text-xs px-2.5 py-1 rounded border transition-colors hover:border-blue-500 hover:text-blue-400"
          :class="activeScenario === s.label
            ? 'bg-blue-600/20 border-blue-500 text-blue-400'
            : 'bg-slate-800 border-slate-700 text-slate-400'">
          {{ s.label }}
        </button>

        <!-- L'ancrage est un mode EN PLUS, pas un remplacement : les scénarios
             restent des niveaux absolus et gardent leur comportement. -->
        <span class="w-px self-stretch bg-slate-700 mx-0.5"></span>
        <button @click="courbe.ancree = !courbe.ancree"
          class="text-xs px-2.5 py-1 rounded border transition-colors hover:border-blue-500 hover:text-blue-400"
          :class="courbe.ancree
            ? 'bg-blue-600/20 border-blue-500 text-blue-400'
            : 'bg-slate-800 border-slate-700 text-slate-400'">
          Ancrée sur r
        </button>
      </div>

      <!-- Les deux paramètres de la pente amortie -->
      <div v-if="courbe.ancree" class="flex items-end gap-3 flex-wrap mb-3">
        <div>
          <label class="label">Taux court — ancre
            <HelpTip width="w-80" text="Repris du champ « Taux sans risque » de la calibration ci-dessus. La courbe part de ce niveau : le modifier là-haut déplace toute la courbe." />
          </label>
          <div class="input bg-slate-800/40 text-slate-400 font-mono w-24 cursor-not-allowed">
            <SensitiveValue>{{ formatNumber(tauxPlat, 2) }} %</SensitiveValue>
          </div>
        </div>
        <div>
          <label class="label">Prime de terme
            <HelpTip width="w-96" text="Écart total entre le taux court et le très long terme, en points de base. Il est atteint asymptotiquement, pas à un pilier donné. Négatif, il donne une courbe inversée — inutile de passer par un scénario." />
          </label>
          <div class="relative w-28">
            <input type="number" step="10" min="-500" max="500" v-model.number="courbe.ecart"
                   class="input pr-10 font-mono" />
            <span class="absolute right-2 top-1/2 -translate-y-1/2 text-slate-600 text-xs pointer-events-none">bps</span>
          </div>
        </div>
        <div>
          <label class="label">Vitesse τ
            <HelpTip width="w-96" text="Nombre d'années pour parcourir les deux tiers de la prime de terme. τ court = pentification rapide puis courbe plate ; τ long = pente étalée. Une pente additive en bps par an aurait donné un 30 ans à deux chiffres sur un taux court à 3 % — elle n'est pas proposée." />
          </label>
          <div class="relative w-28">
            <input type="number" step="0.5" min="0.05" max="30" v-model.number="courbe.tau"
                   class="input pr-8 font-mono" />
            <span class="absolute right-2 top-1/2 -translate-y-1/2 text-slate-600 text-xs pointer-events-none">ans</span>
          </div>
        </div>
        <p class="text-[10px] text-slate-600 mb-1.5 flex-1 min-w-40">
          r(T) = r + écart × (1 − e<sup>−T/τ</sup>). Les piliers se recalculent
          et ne se saisissent plus tant que l'ancrage est actif.
        </p>
      </div>

      <!-- 11 pillar inputs -->
      <div class="grid grid-cols-11 gap-1 mb-3">
        <div v-for="p in courbe.pillars" :key="p.label"
          class="flex flex-col items-center gap-0.5">
          <label class="text-xs text-slate-600 leading-none">{{ p.label }}</label>
          <SensitiveValue mode="input" placeholder="••">
            <div class="relative w-full">
              <input type="number" step="0.05" min="0" max="20"
                :value="formatPillar(p.rate)" :readonly="courbe.ancree"
                @input="onPillarInput(p, $event); activeScenario = null"
                class="w-full text-center text-xs border rounded px-0 py-1
                       focus:border-blue-500 focus:outline-none"
                :class="courbe.ancree
                  ? 'bg-slate-800/40 border-slate-800 text-slate-500 cursor-not-allowed'
                  : 'bg-slate-900 border-slate-700 text-slate-200'"
                style="padding-right:10px" />
              <span class="absolute right-0.5 top-1/2 -translate-y-1/2 text-slate-600 text-xs pointer-events-none">%</span>
            </div>
          </SensitiveValue>
        </div>
      </div>

      <!-- Yield curve chart -->
      <SensitiveChart>
        <div style="height:88px;position:relative;">
          <canvas ref="ycCanvas"></canvas>
        </div>
      </SensitiveChart>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, watch, nextTick, onMounted, onUnmounted } from 'vue'
import { usePricingStore } from '../stores/pricing.js'
import { useDemoModeStore } from '../stores/demoMode.js'
import { demoChartOptions } from '../composables/useSensitiveChart.js'
import { applyChartTheme, axisTick, chartTheme } from '../charts/theme.js'
import SensitiveValue from './SensitiveValue.vue'
import SensitiveChart from './SensitiveChart.vue'
import { formatNumber, formatPercent } from '../utils/format.js'
import { lierAuTauxCourt } from '../composables/useYieldCurveAnchor.js'
import HelpTip from './HelpTip.vue'
import {
  Chart, LineElement, LineController, PointElement,
  LinearScale, Filler, Tooltip,
} from 'chart.js'

Chart.register(LineElement, LineController, PointElement, LinearScale, Filler, Tooltip)
applyChartTheme(Chart)

const props = defineProps({
  // La courbe à éditer, forme {enabled, pillars:[{label,T,rate}]}. Absente, on
  // prend celle du Pricer : les usages existants n'ont rien à changer, et
  // l'écran d'appel d'offres passe la sienne sans partager d'état avec lui.
  courbe: { type: Object, default: null },
  // Le taux plat rappelé quand la courbe est désactivée, en %.
  tauxPlat: { type: Number, default: null },
})

const store = usePricingStore()
const courbe = computed(() => props.courbe ?? store.yieldCurve)
const tauxPlat = computed(() => props.tauxPlat ?? store.globalParams.r)
const demo = useDemoModeStore()
const ycCanvas = ref(null)
let ycChart = null
const activeScenario = ref('Normale')

const SCENARIOS = [
  {
    label: 'Normale',
    rates: [3.10, 3.30, 3.55, 3.80, 3.95, 4.10, 4.20, 4.30, 4.35, 4.40, 4.45],
  },
  {
    label: 'Inversée',
    rates: [4.80, 4.60, 4.30, 4.00, 3.80, 3.55, 3.40, 3.25, 3.15, 3.05, 2.95],
  },
  {
    label: 'Plate',
    rates: [3.75, 3.80, 3.85, 3.85, 3.85, 3.85, 3.85, 3.85, 3.85, 3.85, 3.85],
  },
  {
    label: 'Bosse',
    rates: [3.20, 3.60, 4.10, 4.50, 4.65, 4.60, 4.45, 4.25, 4.05, 3.90, 3.75],
  },
  {
    label: 'US 2024',
    rates: [5.30, 5.20, 4.95, 4.60, 4.40, 4.25, 4.20, 4.18, 4.20, 4.22, 4.25],
  },
]

const keyRates = computed(() => {
  const ps = courbe.value.pillars
  return ['1Y', '5Y', '10Y', '30Y'].map(lbl => ({
    label: lbl,
    rate: ps.find(p => p.label === lbl)?.rate ?? 0,
  }))
})

function applyScenario(s) {
  s.rates.forEach((r, i) => {
    if (courbe.value.pillars[i]) courbe.value.pillars[i].rate = r
  })
  activeScenario.value = s.label
}

// Deux décimales à l'affichage : la dérivation rend des taux à six, qui
// remplissaient les cases de chiffres illisibles sans rien apporter. La valeur
// utilisée pour le prix reste la valeur pleine.
function formatPillar(rate) {
  return courbe.value.ancree ? Math.round(rate * 100) / 100 : rate
}

// Le lien avec le champ « Taux sans risque » de l'écran vit dans le
// composable : il s'y teste, alors qu'ici il faudrait monter la carte — avec
// Chart.js, un canvas et un store — pour vérifier cinq lignes.
lierAuTauxCourt(courbe, tauxPlat, () => { activeScenario.value = null })

function onPillarInput(p, evt) {
  if (courbe.value.ancree) return
  const v = parseFloat(evt.target.value)
  if (!isNaN(v)) p.rate = Math.max(0, Math.min(20, v))
}

async function renderChart() {
  if (!courbe.value.enabled) {
    if (ycChart) { ycChart.destroy(); ycChart = null }
    return
  }
  await nextTick()
  await new Promise(r => requestAnimationFrame(r))
  if (!ycCanvas.value) return
  if (ycChart) { ycChart.destroy(); ycChart = null }

  const pillars = courbe.value.pillars
  const Ts   = pillars.map(p => p.T)
  const data = pillars.map(p => ({ x: p.T, y: p.rate }))

  ycChart = new Chart(ycCanvas.value, {
    type: 'line',
    data: {
      datasets: [{
        data,
        borderColor: chartTheme.primary,
        backgroundColor: chartTheme.primarySoft,
        borderWidth: 1.8,
        pointRadius: 3,
        pointBackgroundColor: chartTheme.primary,
        tension: 0.35,
        fill: true,
      }],
    },
    options: demoChartOptions({
      responsive: true, maintainAspectRatio: false,
      animation: { duration: 80 },
      parsing: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: { label: it => `${it.raw.y.toFixed(2).replace('.', ',')}% @ ${it.raw.x}Y` },
        },
      },
      scales: {
        x: {
          type: 'linear', min: 0, max: 30,
          // Piliers IRREGULIERS explicites : la regle par pas donnerait
          // « 0,25Y  0,50Y  1,00Y » — plus verbeux pour rien. On garde la
          // valeur telle quelle, avec le separateur decimal de l'interface.
          ticks: { font: { size: 8 },
                   callback: v => `${Number(v).toLocaleString('fr-FR', { maximumFractionDigits: 2 })}Y`,
                   values: [0.25, 0.5, 1, 2, 3, 5, 7, 10, 15, 20, 30] },
        },
        y: {
          ticks: { font: { size: 8 }, callback: axisTick('%') },
        },
      },
    }, demo.enabled),
  })
}

const chartKey = computed(() => {
  if (!courbe.value.enabled) return null
  return courbe.value.pillars.map(p => p.rate).join(',')
})

watch(chartKey, renderChart)
watch(() => courbe.value.enabled, v => { if (v) renderChart() })
watch(() => demo.enabled, renderChart)
onMounted(() => { if (courbe.value.enabled) renderChart() })
onUnmounted(() => { if (ycChart) ycChart.destroy() })
</script>
