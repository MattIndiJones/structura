<template>
  <!-- ── Tabs sans pricing requis ─────────────────────────────── -->
  <ProfileTab  v-if="tab === 'profile'" />
  <PathsTab    v-else-if="tab === 'paths'" />
  <ProbaTab    v-else-if="tab === 'proba'" />
  <BacktestTab   v-else-if="tab === 'backtest'" />
  <MtfTab        v-else-if="tab === 'mtf'" />
  <SimulationTab v-else-if="tab === 'simulation'" />
  <ScenarioGrid  v-else-if="tab === 'scenarios'" />

  <!-- ── Pas encore de résultat ───────────────────────────────── -->
  <div v-else-if="!store.result"
       class="flex flex-col items-center justify-center h-64 text-slate-600 gap-3">
    <div class="text-4xl">📊</div>
    <div class="text-sm font-medium">Lancez un pricing pour voir les résultats</div>
    <div class="text-xs text-slate-700">▶ Pricer → résultats en moins d'une seconde</div>
  </div>

  <!-- ── Résultats ─────────────────────────────────────────────── -->
  <div v-else-if="tab === 'results'" class="flex flex-col gap-4">
    <!-- Prix -->
    <div class="rounded-xl border border-blue-800/50 bg-blue-950/30 p-5">
      <div class="text-xs font-bold text-blue-400/70 uppercase tracking-wider mb-1">Prix équitable</div>
      <div class="flex items-baseline gap-4 flex-wrap">
        <span class="text-4xl font-black text-blue-400"><SensitiveValue>{{ f2(store.result.price) }}%</SensitiveValue></span>
        <span class="text-sm text-slate-500">
          IC 95% [<SensitiveValue>{{ f2(store.result.ic95[0]) }}%, {{ f2(store.result.ic95[1]) }}%</SensitiveValue>]
          &nbsp;±<SensitiveValue>{{ f2((store.result.ic95[1] - store.result.ic95[0]) / 2) }}%</SensitiveValue>
        </span>
      </div>
    </div>

    <!-- Tuiles stats -->
    <div class="grid grid-cols-2 sm:grid-cols-3 gap-3">
      <div class="stat-box">
        <div class="text-xs text-slate-500 mb-1">Médiane</div>
        <div class="text-xl font-bold text-slate-200"><SensitiveValue>{{ f2(store.result.median) }}%</SensitiveValue></div>
      </div>
      <div class="stat-box">
        <div class="text-xs text-slate-500 mb-1">VaR 5%</div>
        <div class="text-xl font-bold text-amber-400"><SensitiveValue>{{ f2(store.result.var5) }}%</SensitiveValue></div>
      </div>
      <div class="stat-box">
        <div class="text-xs text-slate-500 mb-1">P(retour &gt; 100%)</div>
        <div class="text-xl font-bold text-green-400"><SensitiveValue>{{ f1(store.result.prob_gt100) }}%</SensitiveValue></div>
      </div>
      <div class="stat-box">
        <div class="text-xs text-slate-500 mb-1">N chemins</div>
        <div class="text-lg font-semibold text-slate-300"><SensitiveValue>{{ store.result.n_eff?.toLocaleString() }}</SensitiveValue></div>
      </div>
      <div class="stat-box">
        <div class="text-xs text-slate-500 mb-1">Temps calcul</div>
        <div class="text-lg font-semibold text-slate-300"><SensitiveValue>{{ store.result.elapsed_ms?.toFixed(0) }} ms</SensitiveValue></div>
      </div>
      <div class="stat-box">
        <div class="text-xs text-slate-500 mb-1">Spread P75–P25</div>
        <div class="text-lg font-semibold text-slate-300"><SensitiveValue>{{ spreadP75P25 }}</SensitiveValue></div>
      </div>
    </div>

    <!-- Histogramme -->
    <div class="card">
      <div class="flex items-baseline gap-2 mb-3">
        <div class="text-xs font-bold text-slate-400 uppercase tracking-wider">Distribution des payoffs</div>
        <div class="text-xs text-slate-600 italic">
          <SensitiveValue>
            valeurs nominales non actualisées · {{ store.result.payoffs?.length?.toLocaleString() }} chemins
            <template v-if="store.result.payoffs?.length">
              · min {{ (store.result.payoffs[0] * 100).toFixed(1) }}% / max {{ (store.result.payoffs[store.result.payoffs.length - 1] * 100).toFixed(1) }}%
            </template>
          </SensitiveValue>
        </div>
      </div>
      <SensitiveChart>
        <canvas ref="histCanvas" style="max-height:220px"></canvas>
      </SensitiveChart>
    </div>

    <!-- Résumé market data — ce qui a produit CE prix -->
    <div v-if="inputs" class="card flex flex-col gap-5">
      <div class="text-xs font-bold text-slate-400 uppercase tracking-wider">
        Données utilisées pour ce pricing
      </div>

      <!-- ── Sous-jacent(s) ───────────────────────────────────────── -->
      <div class="flex flex-col gap-2">
        <div class="text-[10px] font-bold text-slate-600 uppercase tracking-widest">Sous-jacent(s)</div>
        <div class="flex flex-col gap-2">
          <div v-for="(u, i) in inputs.underlyings" :key="i"
               class="flex flex-wrap items-center gap-x-4 gap-y-1 bg-slate-800/50 rounded-lg px-3 py-2">
            <span class="font-semibold text-slate-200 text-sm min-w-[80px]">
              <SensitiveValue placeholder="SJ">{{ demo.underlyingLabel(u.name, i) }}</SensitiveValue>
            </span>
            <span v-if="u.ticker" class="font-mono text-xs text-blue-400">
              <SensitiveValue>{{ u.ticker }}</SensitiveValue>
            </span>
            <span class="text-xs text-slate-400">
              σ <span class="font-mono font-semibold text-slate-200"><SensitiveValue>{{ u.sigma.toFixed(1) }}%</SensitiveValue></span>
            </span>
            <span class="text-xs text-slate-400">
              q <span class="font-mono font-semibold text-slate-200"><SensitiveValue>{{ u.q.toFixed(2) }}%</SensitiveValue></span>
            </span>
            <span v-if="showRhoRS" class="text-xs text-slate-400">
              ρ(r,S) <span class="font-mono font-semibold text-slate-200"><SensitiveValue>{{ u.rho_rS }}%</SensitiveValue></span>
            </span>
            <span class="text-xs text-slate-600">{{ u.ccy }}</span>
          </div>
        </div>
        <!-- Corrélation multi-actifs -->
        <div v-if="inputs.underlyings.length > 1" class="flex flex-wrap gap-2 text-xs">
          <template v-for="(row, i) in inputs.corrMatrix" :key="i">
            <template v-for="(v, j) in row" :key="j">
              <span v-if="j > i" class="bg-slate-800 border border-slate-700 rounded px-2 py-0.5 font-mono text-slate-400">
                ρ({{ demo.underlyingLabel(inputs.underlyings[i].name, i) }},{{ demo.underlyingLabel(inputs.underlyings[j].name, j) }})
                = <SensitiveValue class="text-slate-200">{{ v.toFixed(2) }}</SensitiveValue>
              </span>
            </template>
          </template>
        </div>
      </div>

      <!-- ── Caractéristiques économiques ────────────────────────── -->
      <div class="flex flex-col gap-2">
        <div class="text-[10px] font-bold text-slate-600 uppercase tracking-widest">Caractéristiques économiques</div>
        <div class="grid grid-cols-2 sm:grid-cols-3 gap-2 text-xs">

          <!-- Maturité -->
          <div class="bg-slate-800/50 rounded-lg px-3 py-2">
            <div class="text-slate-500 mb-1">Maturité</div>
            <div class="font-mono font-bold text-slate-100 text-base">
              <SensitiveValue>{{ (store.result.t_max_effective ?? inputs.T).toFixed(2) }} Y</SensitiveValue>
            </div>
            <div v-if="store.result.t_max_effective && Math.abs(store.result.t_max_effective - inputs.T) > 0.01"
                 class="text-amber-500 text-[10px] mt-0.5">
              ↗ depuis <SensitiveValue>{{ inputs.T }} Y</SensitiveValue> (CONSTAT)
            </div>
          </div>

          <!-- Fugit — seulement si le script a un STOP -->
          <div v-if="inputs.hasStop && store.result.fugit != null" class="bg-slate-800/50 rounded-lg px-3 py-2">
            <div class="text-slate-500 mb-1">Fugit <span class="text-slate-600 font-normal">(durée moy.)</span></div>
            <div class="font-mono font-bold text-amber-300 text-base">
              <SensitiveValue>{{ store.result.fugit.toFixed(2) }} Y</SensitiveValue>
            </div>
            <div class="text-[10px] text-slate-600 mt-0.5">E[τ] sur {{ store.result.n_eff?.toLocaleString() }} chemins</div>
          </div>

          <!-- Taux / courbe -->
          <div class="bg-slate-800/50 rounded-lg px-3 py-2"
               :class="inputs.yieldCurvePillars?.length ? 'col-span-2 sm:col-span-1' : ''">
            <div class="text-slate-500 mb-1">
              Taux
              <span :class="inputs.yieldCurvePillars?.length ? 'text-green-500' : 'text-slate-600'"
                    class="text-[10px] font-semibold ml-1">
                {{ inputs.yieldCurvePillars?.length ? '● Courbe' : '● Plat' }}
              </span>
            </div>
            <!-- Taux plat -->
            <template v-if="!inputs.yieldCurvePillars?.length">
              <div class="font-mono font-bold text-slate-100 text-base">
                <SensitiveValue>{{ inputs.r.toFixed(2) }}%</SensitiveValue>
              </div>
            </template>
            <!-- Courbe de taux : points clés -->
            <template v-else>
              <div class="flex flex-col gap-1 text-xs">
                <div class="flex items-center justify-between gap-3">
                  <span class="text-slate-500">Court terme</span>
                  <span class="font-mono font-semibold text-slate-200">
                    <SensitiveValue>{{ interpRate(inputs.yieldCurvePillars[0].T, inputs.yieldCurvePillars).toFixed(2) }}%</SensitiveValue>
                    <span class="text-slate-600 text-[10px] ml-1">{{ inputs.yieldCurvePillars[0].label }}</span>
                  </span>
                </div>
                <div v-if="inputs.hasStop && store.result.fugit != null"
                     class="flex items-center justify-between gap-3">
                  <span class="text-amber-400/80">Fugit</span>
                  <span class="font-mono font-semibold text-amber-300">
                    <SensitiveValue>{{ interpRate(store.result.fugit, inputs.yieldCurvePillars).toFixed(2) }}%</SensitiveValue>
                    <span class="text-slate-600 text-[10px] ml-1">{{ store.result.fugit.toFixed(2) }}Y</span>
                  </span>
                </div>
                <div class="flex items-center justify-between gap-3">
                  <span class="text-slate-500">Maturité</span>
                  <span class="font-mono font-semibold text-slate-200">
                    <SensitiveValue>{{ interpRate(store.result.t_max_effective ?? inputs.T, inputs.yieldCurvePillars).toFixed(2) }}%</SensitiveValue>
                    <span class="text-slate-600 text-[10px] ml-1">{{ (store.result.t_max_effective ?? inputs.T).toFixed(2) }}Y</span>
                  </span>
                </div>
              </div>
            </template>
          </div>

          <!-- Modèle vol -->
          <div class="bg-slate-800/50 rounded-lg px-3 py-2">
            <div class="text-slate-500 mb-1">Modèle vol</div>
            <div class="font-mono font-semibold text-slate-200 text-sm">{{ modelLabel(inputs.model) }}</div>
          </div>

          <!-- Modèle taux -->
          <div class="bg-slate-800/50 rounded-lg px-3 py-2">
            <div class="text-slate-500 mb-1">Modèle taux</div>
            <div class="font-mono font-semibold text-slate-200 text-sm"><SensitiveValue>{{ rateModelLabel(inputs) }}</SensitiveValue></div>
          </div>

        </div>
      </div>

      <!-- ── Simulation ───────────────────────────────────────────── -->
      <div class="flex flex-col gap-2">
        <div class="text-[10px] font-bold text-slate-600 uppercase tracking-widest">Simulation</div>
        <div class="flex flex-wrap gap-2 text-xs">
          <span class="bg-slate-800 border border-slate-700 rounded px-2.5 py-1 text-slate-400">
            N <span class="font-mono font-semibold text-slate-200 ml-1"><SensitiveValue>{{ inputs.N.toLocaleString() }}</SensitiveValue></span>
          </span>
          <span class="bg-slate-800 border border-slate-700 rounded px-2.5 py-1 text-slate-400">
            Seed <span class="font-mono font-semibold text-slate-200 ml-1"><SensitiveValue>{{ inputs.seed }}</SensitiveValue></span>
          </span>
          <span class="bg-slate-800 border border-slate-700 rounded px-2.5 py-1"
                :class="inputs.antithetic ? 'text-green-400 border-green-900' : 'text-slate-500'">
            {{ inputs.antithetic ? '✓ Antithétique' : 'Sans antithétique' }}
          </span>
        </div>
      </div>

      <!-- ── Paramètres du script ─────────────────────────────────── -->
      <div v-if="inputs.paramsUsed.length" class="flex flex-col gap-2">
        <div class="text-[10px] font-bold text-slate-600 uppercase tracking-widest">Paramètres du script</div>
        <div class="flex flex-wrap gap-2">
          <span v-for="p in inputs.paramsUsed" :key="p.name"
                class="font-mono bg-slate-800 border border-slate-700 rounded px-2.5 py-1 text-xs">
            <span class="text-slate-500">{{ p.name }}</span>
            <span class="text-slate-100 font-bold ml-1">=<SensitiveValue>{{ p.value }}{{ p.is_pct ? '%' : '' }}</SensitiveValue></span>
          </span>
        </div>
      </div>
    </div>
  </div>

  <!-- ── Flux ──────────────────────────────────────────────────── -->
  <div v-else-if="tab === 'flux'" class="flex flex-col gap-4">
    <div v-if="fluxGroups.length === 0"
         class="flex flex-col items-center justify-center py-16 gap-2 text-slate-600">
      <div class="text-3xl">💰</div>
      <div class="text-sm font-medium">Aucun flux — vérifiez les instructions PAY dans le script</div>
    </div>
    <template v-else>
      <!-- Résumé -->
      <div class="flex flex-wrap gap-2">
        <div class="stat-box min-w-28">
          <div class="text-xs text-slate-500 mb-1">Prix MC (PV Σ)</div>
          <div class="text-xl font-bold text-blue-400"><SensitiveValue>{{ f2(store.result.price) }}%</SensitiveValue></div>
        </div>
        <div class="stat-box min-w-28">
          <div class="text-xs text-slate-500 mb-1">Dates de flux</div>
          <div class="text-xl font-bold text-slate-200">{{ fluxGroups.length }}</div>
        </div>
        <div class="stat-box min-w-28">
          <div class="text-xs text-slate-500 mb-1">N chemins</div>
          <div class="text-xl font-bold text-slate-300"><SensitiveValue>{{ store.result.n_eff?.toLocaleString() }}</SensitiveValue></div>
        </div>
      </div>

      <!-- Table -->
      <div class="card overflow-x-auto">
        <div class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-1">
          💰 Décomposition des flux — PV par composante
        </div>
        <div class="text-xs text-slate-600 mb-4">
          Date · Expression PAY · P(actif) · E[CF] brut · DF · Contribution PV actualisée
        </div>
        <table class="w-full text-xs border-collapse">
          <thead>
            <tr class="bg-slate-800/60 border-b-2 border-slate-700">
              <th class="text-left py-1.5 px-2 text-slate-500 font-semibold text-[10px] uppercase tracking-wide whitespace-nowrap">Date</th>
              <th class="text-left py-1.5 px-2 text-slate-500 font-semibold text-[10px] uppercase tracking-wide">Expression</th>
              <th class="text-right py-1.5 px-2 text-slate-500 font-semibold text-[10px] uppercase tracking-wide whitespace-nowrap">P(actif)</th>
              <th class="text-right py-1.5 px-2 text-slate-500 font-semibold text-[10px] uppercase tracking-wide whitespace-nowrap">E[CF]</th>
              <th class="text-right py-1.5 px-2 text-slate-500 font-semibold text-[10px] uppercase tracking-wide whitespace-nowrap">DF</th>
              <th class="text-right py-1.5 px-2 text-slate-500 font-semibold text-[10px] uppercase tracking-wide whitespace-nowrap">Contrib. PV</th>
            </tr>
          </thead>
          <tbody>
            <template v-for="grp in fluxGroups" :key="grp.tKey">
              <tr v-for="(row, ri) in grp.rows" :key="row.key"
                  :class="[
                    ri < grp.rows.length - 1 ? 'border-b border-slate-800' : 'border-b-2 border-slate-700',
                    row.pv < 0 ? 'bg-red-950/20' : ''
                  ]">
                <td class="py-1.5 px-2 font-bold text-slate-300 whitespace-nowrap align-top text-[10px]">
                  <span v-if="ri === 0">{{ grp.label }}</span>
                </td>
                <td class="py-1.5 px-2 font-mono text-[11px]"
                    :class="row.pv < 0 ? 'text-red-400' : 'text-slate-500'">{{ row.lbl }}</td>
                <td class="py-1.5 px-2 text-right text-slate-400"><SensitiveValue>{{ row.pAct }}%</SensitiveValue></td>
                <td class="py-1.5 px-2 text-right font-semibold font-mono"
                    :class="row.eCF >= 0 ? 'text-slate-300' : 'text-red-400'">
                  <SensitiveValue>{{ row.eCF >= 0 ? '+' : '' }}{{ row.eCFStr }}%</SensitiveValue>
                </td>
                <td class="py-1.5 px-2 text-right font-mono text-slate-400">
                  <SensitiveValue>{{ row.dfStr }}</SensitiveValue>
                </td>
                <td class="py-1.5 px-2 text-right font-bold font-mono"
                    :class="row.pv >= 0 ? 'text-green-400' : 'text-red-400'">
                  <SensitiveValue>{{ row.pv >= 0 ? '+' : '' }}{{ row.pvStr }}%</SensitiveValue>
                </td>
              </tr>
            </template>
          </tbody>
          <tfoot>
            <tr class="bg-slate-800/60 border-t-2 border-slate-600">
              <td colspan="5" class="py-2 px-2 font-black text-slate-200">= Prix total</td>
              <td class="py-2 px-2 text-right font-black text-blue-400 text-sm">
                <SensitiveValue>{{ fluxTotal.toFixed(2) }}%</SensitiveValue>
              </td>
            </tr>
          </tfoot>
        </table>
      </div>
    </template>
  </div>

  <!-- ── Greeks ────────────────────────────────────────────────── -->
  <div v-else-if="tab === 'greeks'" class="flex flex-col gap-4">
    <div v-if="!hasGreeks"
         class="flex flex-col items-center justify-center py-16 gap-3 text-slate-600">
      <div class="text-3xl">∂</div>
      <div class="text-sm font-medium">Cliquez "∂ Greeks" dans le header</div>
      <div class="text-xs">Cochez les Greeks dans l'onglet Paramètres puis relancez</div>
      <button class="btn-secondary text-xs mt-2" :disabled="store.loading" @click="store.runGreeks()">
        Calculer les Greeks
      </button>
    </div>
    <template v-else>
      <div class="card">
        <div class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-4">
          Greeks — CRN bump-and-reprice (seed <SensitiveValue>{{ store.globalParams.seed }}</SensitiveValue>)
        </div>
        <div class="grid grid-cols-2 sm:grid-cols-3 gap-3">
          <div v-for="(val, name) in store.result.greeks" :key="name" class="stat-box">
            <div class="text-xs text-slate-500 mb-1 font-mono">{{ gLabel(name) }}</div>
            <div class="text-base font-bold font-mono"
                 :class="val > 0 ? 'text-green-400' : val < 0 ? 'text-red-400' : 'text-slate-400'">
              <SensitiveValue>{{ fmtG(val) }}</SensitiveValue>
            </div>
            <div class="text-xs text-slate-600 mt-0.5">{{ gUnit(name) }}</div>
          </div>
        </div>
      </div>
      <div class="card overflow-x-auto">
        <table class="w-full text-xs">
          <thead>
            <tr class="border-b border-slate-700 text-slate-500">
              <th class="pb-2 pr-4 text-left font-semibold">Greek</th>
              <th class="pb-2 pr-4 text-right font-semibold">Valeur</th>
              <th class="pb-2 text-left font-semibold">Interprétation</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(val, name) in store.result.greeks" :key="name"
                class="border-b border-slate-800/50">
              <td class="py-1.5 pr-4 font-mono font-semibold text-slate-300">{{ gLabel(name) }}</td>
              <td class="py-1.5 pr-4 font-mono text-right"
                  :class="val > 0 ? 'text-green-400' : val < 0 ? 'text-red-400' : 'text-slate-400'">
                <SensitiveValue>{{ fmtG(val) }}</SensitiveValue>
              </td>
              <td class="py-1.5 text-slate-500"><SensitiveValue>{{ gInterp(name, val) }}</SensitiveValue></td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
  </div>

  <!-- ── Fallback (tab inconnu) ─────────────────────────────────── -->
  <div v-else class="flex flex-col items-center justify-center h-64 text-slate-600 gap-2">
    <div class="text-4xl">📊</div>
    <div class="text-sm">Sélectionnez un onglet</div>
  </div>
</template>

<script setup>
import { ref, computed, watch, nextTick, onMounted, onUnmounted } from 'vue'
import { usePricingStore } from '../stores/pricing.js'
import { useDemoModeStore } from '../stores/demoMode.js'
import { demoChartOptions } from '../composables/useSensitiveChart.js'
import { Chart, BarElement, BarController, CategoryScale, LinearScale, Tooltip } from 'chart.js'
import ProfileTab  from './ProfileTab.vue'
import PathsTab    from './PathsTab.vue'
import ProbaTab    from './ProbaTab.vue'
import BacktestTab from './BacktestTab.vue'
import MtfTab      from './MtfTab.vue'
import SimulationTab from './SimulationTab.vue'
import ScenarioGrid from './ScenarioGrid.vue'
import SensitiveValue from './SensitiveValue.vue'
import SensitiveChart from './SensitiveChart.vue'

Chart.register(BarElement, BarController, CategoryScale, LinearScale, Tooltip)

const store = usePricingStore()
const demo = useDemoModeStore()
const histCanvas = ref(null)
let histChart = null

const tab = computed(() => store.rightTab)

// ── Helpers format ────────────────────────────────────────────────
const f2 = v => v != null ? (v * 100).toFixed(2) : '—'
const f1 = v => v != null ? (v * 100).toFixed(1) : '—'

const spreadP75P25 = computed(() => {
  const p = store.result?.payoffs
  if (!p || p.length < 4) return '—'
  const p25 = p[Math.floor(p.length * 0.25)]
  const p75 = p[Math.floor(p.length * 0.75)]
  return ((p75 - p25) * 100).toFixed(2) + '%'
})

// ── Résumé market data (snapshot pris au moment du pricing) ───────
const inputs = computed(() => store.result?._inputs ?? null)
const showRhoRS = computed(() => inputs.value?.rateModel !== 'deterministic')

const MODEL_LABELS = { constant: 'Constant (GBM)', heston: 'Heston QE', sabr: 'SABR (Hagan)', localvol: 'Local Vol (Dupire)' }
const modelLabel = m => MODEL_LABELS[m] || m

function rateModelLabel(inp) {
  if (inp.rateModel === 'deterministic') return 'Déterministe'
  if (inp.rateModel === 'abm') return `ABM (σ=${inp.sigma_r}%)`
  return `Hull-White (σ=${inp.sigma_r}%, a=${inp.a_r})`
}

function interpRate(t, pillars) {
  if (!pillars || pillars.length === 0) return 0
  if (t <= pillars[0].T) return pillars[0].rate
  if (t >= pillars[pillars.length - 1].T) return pillars[pillars.length - 1].rate
  for (let i = 0; i < pillars.length - 1; i++) {
    if (t >= pillars[i].T && t <= pillars[i + 1].T) {
      const frac = (t - pillars[i].T) / (pillars[i + 1].T - pillars[i].T)
      return pillars[i].rate + frac * (pillars[i + 1].rate - pillars[i].rate)
    }
  }
  return pillars[pillars.length - 1].rate
}

// ── Histogramme ───────────────────────────────────────────────────
async function drawHist() {
  if (tab.value !== 'results') return
  await nextTick()
  if (!histCanvas.value || !store.result?.payoffs?.length) return
  if (histChart) { histChart.destroy(); histChart = null }

  const arr = store.result.payoffs.map(p => p * 100)
  const mn = arr.reduce((a, b) => Math.min(a, b), Infinity)
  const mx = arr.reduce((a, b) => Math.max(a, b), -Infinity)
  const bins = 40
  const w = (mx - mn) / bins || 1
  const counts = new Array(bins).fill(0)
  // labels = left edge of each bin
  const labels = Array.from({ length: bins }, (_, i) => ((mn + i * w).toFixed(1) + '%'))
  arr.forEach(v => { counts[Math.min(bins - 1, Math.floor((v - mn) / w))]++ })
  const price = store.result.price * 100

  histChart = new Chart(histCanvas.value, {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        data: counts,
        backgroundColor: labels.map(l => parseFloat(l) + w >= price ? 'rgba(59,130,246,.55)' : 'rgba(100,116,139,.35)'),
        borderColor:     labels.map(l => parseFloat(l) + w >= price ? 'rgba(59,130,246,.9)'  : 'rgba(100,116,139,.5)'),
        borderWidth: 1, borderRadius: 2,
      }],
    },
    options: demoChartOptions({
      responsive: true, maintainAspectRatio: true,
      plugins: { legend: { display: false },
        tooltip: { callbacks: {
          title: i => {
            const left = parseFloat(i[0].label)
            return `Payoff: ${left.toFixed(1)}% — ${(left + w).toFixed(1)}%`
          },
          label: i => `${i.raw} chemins`,
        } } },
      scales: {
        x: { ticks: { color: '#475569', maxTicksLimit: 8, font: { size: 10 } }, grid: { color: '#1e293b' } },
        y: { ticks: { color: '#475569', font: { size: 10 } }, grid: { color: '#1e293b' } },
      },
    }, demo.enabled),
  })
}

watch(() => store.result, drawHist)
watch(tab, t => { if (t === 'results') drawHist() })
watch(() => demo.enabled, drawHist)   // instant — re-render axes/tooltip on toggle
onMounted(() => { if (tab.value === 'results') drawHist() })
onUnmounted(() => { if (histChart) histChart.destroy() })

// ── Flux ──────────────────────────────────────────────────────────
function tToCalDate(t) {
  if (t < 0.005) return "Auj."
  const ms = Date.now() + t * 365.25 * 24 * 3600 * 1000
  return new Date(ms).toLocaleDateString('fr-FR', { day: '2-digit', month: '2-digit', year: 'numeric' })
}

const fluxGroups = computed(() => {
  const ft = store.result?.flux_table
  if (!ft) return []
  const N = store.result.n_eff || store.result.n_paths || 1
  const byDate = new Map()

  for (const [key, d] of Object.entries(ft)) {
    if (!d || typeof d.t !== 'number') continue
    const tKey = d.t.toFixed(6)
    if (!byDate.has(tKey)) {
      const t = d.t
      byDate.set(tKey, { t, tKey, label: tToCalDate(t), rows: [] })
    }
    const pvRaw = typeof d.pv === 'number' ? d.pv : (d.sum ?? 0)
    const eCF   = (d.sum ?? 0) / N * 100
    const pv    = pvRaw / N * 100
    byDate.get(tKey).rows.push({
      key,
      lbl:    d.lbl ?? key,
      n:      d.n ?? 0,
      pAct:   ((d.n ?? 0) / N * 100).toFixed(1),
      eCF,
      eCFStr: eCF.toFixed(2),
      pv,
      pvStr:  pv.toFixed(3),
      df:     typeof d.df === 'number' ? d.df : null,
      dfStr:  typeof d.df === 'number' ? d.df.toFixed(4) : '—',
    })
  }

  return [...byDate.values()]
    .sort((a, b) => a.t - b.t)
    .map(g => ({ ...g, rows: [...g.rows].sort((a, b) => b.pv - a.pv) }))
})

const fluxTotal = computed(() =>
  fluxGroups.value.reduce((s, g) => s + g.rows.reduce((rs, r) => rs + r.pv, 0), 0)
)

// ── Greeks ────────────────────────────────────────────────────────
const hasGreeks = computed(() => {
  const g = store.result?.greeks
  return g && Object.keys(g).length > 0
})

const fmtG = v => v == null ? '—' : Math.abs(v) < 0.0001 ? v.toExponential(2) : v.toFixed(4)

const GREEK_SYM = { delta: 'Δ', gamma: 'Γ', vega: 'ν', theta: 'Θ', rho: 'ρ', corr: 'ρᵢⱼ' }
const gLabel = name => {
  const m = name.match(/^([a-z]+)_(\d+)$/)
  if (!m) return name
  const sym = GREEK_SYM[m[1]] || m[1]
  const idx = +m[2] - 1   // backend keys are 1-indexed (delta_1 = underlying 0)
  const ul  = store.underlyings[idx]
  return ul ? `${sym} ${demo.underlyingLabel(ul.name, idx)}` : name
}

const gUnit = name => {
  if (name.startsWith('delta')) return '% / +1% spot'
  if (name.startsWith('gamma')) return '% Δ pour ±3% spot'
  if (name.startsWith('vega'))  return '% / +1% vol'
  if (name === 'theta')          return '% / jour'
  if (name === 'rho')            return '% / +100bp'
  if (name.startsWith('corr'))  return '% / +5% corr'
  return ''
}

const gInterp = (name, val) => {
  const v = (val * 100).toFixed(2)
  if (name.startsWith('delta')) return `+1% spot → P&L ${v}%`
  if (name.startsWith('vega'))  return `+1% vol → P&L ${v}%`
  if (name === 'theta')          return `1 jour → P&L ${v}%`
  if (name === 'rho')            return `+100bp → P&L ${v}%`
  return ''
}
</script>
