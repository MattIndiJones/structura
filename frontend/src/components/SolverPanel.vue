<template>
  <div class="card">
    <div class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3">
      🎯 Solveur — trouver un paramètre pour un prix cible
    </div>

    <div v-if="!store.scriptParams.length" class="text-xs text-amber-500">
      Aucun PARAM détecté dans le script — ajoutez au moins un <code>PARAM</code> pour utiliser le solveur.
    </div>

    <template v-else>
      <div class="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs mb-3">
        <div>
          <label class="label">Paramètre à résoudre
            <HelpTip text="Le PARAM du script dont on cherche la valeur — un seul à la fois. Le solveur relance un pricing MC complet à chaque itération en ne faisant varier que celui-ci, tous les autres restent à leur valeur courante." />
          </label>
          <select v-model="form.param_name" class="select" @change="prefillBounds">
            <option v-for="p in store.scriptParams" :key="p.name" :value="p.name">{{ p.name }}</option>
          </select>
        </div>
        <div>
          <label class="label">Prix cible (%)
            <HelpTip text="Le prix (% du notionnel) que le solveur cherche à atteindre en ajustant le paramètre — typiquement 100% pour trouver le coupon/la barrière qui rend le produit 'zéro-coût' à l'émission." />
          </label>
          <SensitiveValue mode="input"><input v-model.number="form.target_price_pct" type="number" step="0.5" class="input" /></SensitiveValue>
        </div>
        <div>
          <label class="label">Borne basse{{ unitSuffix }}
            <HelpTip text="Borne inférieure de la recherche (méthode de bissection — il faut que la solution soit encadrée). Si le solveur répond 'non bracketé', élargissez cette borne : le prix cible n'est atteignable dans aucune valeur de l'intervalle actuel." />
          </label>
          <SensitiveValue mode="input"><input v-model.number="form.lo" type="number" step="0.1" class="input" /></SensitiveValue>
        </div>
        <div>
          <label class="label">Borne haute{{ unitSuffix }}
            <HelpTip text="Borne supérieure de la recherche — même logique que la borne basse. Les deux bornes sont pré-remplies à 0,5x/1,5x la valeur par défaut du paramètre, à ajuster si le prix cible sort de cette plage." />
          </label>
          <SensitiveValue mode="input"><input v-model.number="form.hi" type="number" step="0.1" class="input" /></SensitiveValue>
        </div>
      </div>

      <details class="mb-3">
        <summary class="text-xs text-slate-500 cursor-pointer hover:text-slate-300">Options avancées</summary>
        <div class="grid grid-cols-3 gap-3 text-xs mt-2">
          <div>
            <label class="label">N chemins
              <HelpTip text="Nombre de chemins Monte Carlo utilisés à CHAQUE itération du solveur — un seul réglage global, pas un raffinement progressif. Plus il est bas, plus le solveur est rapide mais plus le bruit MC peut le faire osciller ou stagner avant convergence." />
            </label>
            <SensitiveValue mode="input"><input v-model.number="form.N" type="number" step="1000" min="1000" max="50000" class="input" /></SensitiveValue>
          </div>
          <div>
            <label class="label">Tolérance (prix)
              <HelpTip text="Écart de prix (en fraction du notionnel) en-dessous duquel le solveur considère avoir convergé et s'arrête. Trop serré par rapport au bruit MC (voir N chemins) et le solveur n'atteindra jamais la tolérance avant max_iter." />
            </label>
            <input v-model.number="form.tol" type="number" step="0.0001" class="input" />
          </div>
          <div>
            <label class="label">Itérations max
              <HelpTip text="Nombre maximum d'itérations de bissection avant abandon, même si la tolérance n'est pas atteinte — un garde-fou, pas un objectif à viser." />
            </label>
            <input v-model.number="form.max_iter" type="number" step="1" min="5" max="100" class="input" />
          </div>
        </div>
      </details>

      <div class="flex justify-end mb-4">
        <button class="btn-primary text-xs px-5" :disabled="store.loading" @click="launch">
          <span v-if="store.loading" class="w-3 h-3 border border-white border-t-transparent rounded-full animate-spin inline-block mr-1"></span>
          ▶ Résoudre
        </button>
      </div>

      <div v-if="!store.solver" class="text-xs text-slate-600 text-center py-6">
        Choisissez un paramètre, un prix cible et des bornes, puis lancez le solveur.
      </div>

      <template v-else>
        <div class="flex flex-wrap gap-2 mb-3">
          <div class="stat-box min-w-32">
            <div class="text-xs text-slate-500 mb-1">{{ store.solver.param_name }} résolu</div>
            <div class="text-xl font-bold text-blue-400"><SensitiveValue>{{ displaySolved }}</SensitiveValue></div>
          </div>
          <div class="stat-box min-w-28">
            <div class="text-xs text-slate-500 mb-1">Prix atteint
              <HelpTip text="Prix effectivement obtenu avec la valeur résolue du paramètre — à comparer au prix cible. Un écart résiduel est normal si la tolérance ou N chemins sont larges." />
            </div>
            <div class="text-lg font-bold text-slate-200"><SensitiveValue>{{ (store.solver.achieved_price * 100).toFixed(3) }}%</SensitiveValue></div>
          </div>
          <div class="stat-box min-w-28">
            <div class="text-xs text-slate-500 mb-1">Itérations
              <HelpTip text="Nombre d'évaluations de pricing effectuées par la bissection avant arrêt (convergence ou max_iter atteint)." />
            </div>
            <div class="text-lg font-bold text-slate-300">{{ store.solver.iterations }}</div>
          </div>
          <div class="stat-box min-w-28">
            <div class="text-xs text-slate-500 mb-1">Convergence
              <HelpTip text="Oui si l'écart au prix cible est passé sous la tolérance avant max_iter. Non signifie que le résultat affiché est la meilleure approximation trouvée, pas une solution exacte — vérifiez le message d'avertissement." />
            </div>
            <div class="text-lg font-bold" :class="store.solver.converged ? 'text-green-400' : 'text-red-400'">
              {{ store.solver.converged ? '✓ Oui' : '✗ Non' }}
            </div>
          </div>
        </div>

        <div v-if="store.solver.message" class="text-xs text-amber-500 mb-3">⚠ {{ store.solver.message }}</div>

        <SensitiveChart>
          <div style="height:180px;position:relative;">
            <canvas ref="traceCanvas"></canvas>
          </div>
        </SensitiveChart>
      </template>
    </template>
  </div>
</template>

<script setup>
import { reactive, ref, computed, watch, nextTick, onMounted, onUnmounted } from 'vue'
import { usePricingStore } from '../stores/pricing.js'
import { useDemoModeStore } from '../stores/demoMode.js'
import { demoChartOptions } from '../composables/useSensitiveChart.js'
import { chartTheme, applyChartTheme } from '../charts/theme.js'
import SensitiveValue from './SensitiveValue.vue'
import SensitiveChart from './SensitiveChart.vue'
import HelpTip from './HelpTip.vue'
import {
  Chart, LineElement, LineController, PointElement,
  CategoryScale, LinearScale, Tooltip, Legend,
} from 'chart.js'

Chart.register(LineElement, LineController, PointElement, CategoryScale, LinearScale, Tooltip, Legend)
applyChartTheme(Chart)

const store = usePricingStore()
const demo = useDemoModeStore()
const traceCanvas = ref(null)
let traceChart = null

const form = reactive({
  param_name: store.scriptParams[0]?.name || '',
  target_price_pct: store.result ? +(store.result.price * 100).toFixed(2) : 100,
  lo: 0, hi: 0,
  N: 8000, tol: 0.0001, max_iter: 40,
})

const unitSuffix = computed(() => store.paramIsPct(form.param_name) ? ' (%)' : '')

// Seed the search bracket from the param's own default — half to 1.5x, a
// reasonable starting range the user can widen if the solver reports
// "not bracketed".
function prefillBounds() {
  const p = store.scriptParams.find(p => p.name === form.param_name)
  if (!p) return
  const d = p.raw_default
  form.lo = +(d * 0.5).toFixed(4)
  form.hi = +(d > 0 ? d * 1.5 : d + 1).toFixed(4)
}
if (form.param_name) prefillBounds()

function launch() {
  store.runSolver({ ...form })
}

const displaySolved = computed(() => {
  if (!store.solver) return '—'
  const v = store.fromStoredUnits(store.solver.param_name, store.solver.param_value)
  return v.toFixed(4) + (store.paramIsPct(store.solver.param_name) ? '%' : '')
})

async function renderTrace() {
  await nextTick()
  if (!store.solver || !traceCanvas.value) return
  if (traceChart) { traceChart.destroy(); traceChart = null }

  const trace = store.solver.trace
  const labels = trace.map(t => t.iter)
  const prices = trace.map(t => +(t.price * 100).toFixed(4))
  const target = store.solver.target_price * 100

  traceChart = new Chart(traceCanvas.value, {
    type: 'line',
    data: {
      labels,
      datasets: [
        { label: 'Prix testé', data: prices, borderColor: chartTheme.primary, backgroundColor: chartTheme.primarySoft,
          borderWidth: 1.5, pointRadius: 3, tension: 0.15 },
        { label: 'Cible', data: labels.map(() => target), borderColor: chartTheme.negative,
          borderWidth: 1, borderDash: [5, 4], pointRadius: 0 },
      ],
    },
    options: demoChartOptions({
      responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { position: 'bottom', labels: { font: { size: 10 }, boxWidth: 12 } },
        tooltip: { callbacks: { label: it => `${it.dataset.label}: ${it.raw.toFixed(3)}%` } },
      },
      scales: {
        x: { title: { display: true, text: 'Itération', font: { size: 9 } },
             ticks: { font: { size: 9 } } },
        y: { ticks: { font: { size: 9 }, callback: v => v + '%' } },
      },
      animation: { duration: 200 },
    }, demo.enabled),
  })
}

watch(() => store.solver, renderTrace)
watch(() => demo.enabled, renderTrace)
onMounted(renderTrace)
onUnmounted(() => { if (traceChart) traceChart.destroy() })
</script>
