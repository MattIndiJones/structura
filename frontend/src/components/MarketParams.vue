<template>
  <div class="flex flex-col gap-5">

    <!-- ── Yahoo Finance loader ──────────────────────────────────── -->
    <div class="card">
      <div class="flex items-center gap-3 mb-3 flex-wrap">
        <h2 class="text-xs font-bold text-slate-400 uppercase tracking-wider mr-auto">Données Yahoo Finance</h2>
        <button class="btn-secondary text-xs px-3" :disabled="store.loading" @click="store.loadYfAll()">
          📡 Charger vols &amp; corr.
        </button>
      </div>
      <div v-if="store.yfStatus" class="text-xs mt-1 leading-relaxed"
           :class="store.yfStatus.startsWith('⚠') ? 'text-amber-400' : 'text-green-400'">
        <SensitiveValue placeholder="Données chargées">{{ store.yfStatus }}</SensitiveValue>
      </div>
      <div v-else class="text-xs text-slate-600 italic">
        Renseignez les tickers puis cliquez "Charger" pour auto-remplir σ, q et la corrélation.
      </div>
    </div>

    <!-- ── Paramètres globaux ─────────────────────────────────────── -->
    <div class="card">
      <h2 class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-4">Paramètres Monte Carlo</h2>
      <div class="grid grid-cols-2 sm:grid-cols-3 gap-3">
        <div>
          <label class="label">Taux sans risque (%)</label>
          <SensitiveValue mode="input">
            <input v-model.number="store.globalParams.r" type="number" step="0.1" class="input" />
          </SensitiveValue>
        </div>
        <div>
          <label class="label">Maturité (Y)
            <span v-if="store.scriptConstats.length > 0" class="text-slate-600 font-normal"
                  title="Le script utilise CONSTAT — la maturité réelle est dictée par le calendrier (la date la plus tardive parmi les événements résolus), pas par ce champ.">?</span>
          </label>
          <div v-if="store.scriptConstats.length > 0"
               class="input bg-slate-800/40 text-slate-500 cursor-not-allowed flex items-center justify-between">
            <span>Calendrier (CONSTAT)</span>
            <span v-if="store.result?.t_max_effective" class="font-mono text-slate-400">
              {{ store.result.t_max_effective.toFixed(2) }} Y
            </span>
          </div>
          <input v-else v-model.number="store.globalParams.T" type="number" step="0.25" class="input" />
        </div>
        <div>
          <label class="label">N simulations</label>
          <select v-model.number="store.globalParams.N" class="select">
            <option :value="5000">5 000</option>
            <option :value="10000">10 000</option>
            <option :value="20000">20 000</option>
            <option :value="50000">50 000</option>
            <option :value="100000">100 000</option>
          </select>
        </div>
        <div>
          <label class="label">Modèle vol</label>
          <select v-model="store.globalParams.model" class="select">
            <option value="constant">Constant (GBM)</option>
            <option value="heston">Heston QE</option>
            <option value="sabr">SABR (Hagan)</option>
            <option value="localvol">Local Vol (Dupire)</option>
          </select>
        </div>
        <div>
          <label class="label">Devise deal</label>
          <select v-model="store.globalParams.deal_ccy" class="select">
            <option>EUR</option><option>USD</option><option>GBP</option>
            <option>JPY</option><option>CHF</option><option>SGD</option>
          </select>
        </div>
        <div>
          <label class="label">Value date
            <span class="text-slate-600 font-normal" title="Date d'échange du nominal — t=0 du pricing. Les flux sont actualisés depuis cette date.">?</span>
          </label>
          <input v-model="store.globalParams.value_date" type="date" class="input" />
        </div>
        <div>
          <label class="label">Seed</label>
          <SensitiveValue mode="input">
            <input v-model.number="store.globalParams.seed" type="number" step="1" class="input" />
          </SensitiveValue>
        </div>
        <div>
          <label class="label">Modèle de taux</label>
          <select v-model="store.globalParams.rateModel" class="select">
            <option value="deterministic">Déterministe (r constant)</option>
            <option value="abm">Stochastique ABM (corrélé actions)</option>
            <option value="hull_white">Hull-White (mean-reverting)</option>
          </select>
        </div>
        <template v-if="store.globalParams.rateModel !== 'deterministic'">
          <div>
            <label class="label">σ taux (%/an)
              <span class="text-slate-600 font-normal" title="Vol du facteur de taux stochastique, partagé par tous les sous-jacents. La corrélation taux-spot par actif se règle via ρ(r,S) sur chaque sous-jacent.">?</span>
            </label>
            <SensitiveValue mode="input">
              <input v-model.number="store.globalParams.sigma_r" type="number" step="0.1" min="0" class="input" />
            </SensitiveValue>
          </div>
          <div v-if="store.globalParams.rateModel === 'hull_white'">
            <label class="label">a (retour à la moyenne)
              <span class="text-slate-600 font-normal" title="Vitesse de retour à la moyenne du taux court (Hull-White). Plus a est grand, plus le taux revient vite vers la courbe forward. Demi-vie ≈ ln(2)/a.">?</span>
            </label>
            <SensitiveValue mode="input">
              <input v-model.number="store.globalParams.a_r" type="number" step="0.05" min="0" class="input" />
            </SensitiveValue>
          </div>
        </template>
      </div>
      <div class="mt-3">
        <label class="flex items-center gap-2 text-xs text-slate-300 cursor-pointer w-fit">
          <input type="checkbox" v-model="store.globalParams.antithetic" class="accent-blue-500" />
          Variantes antithétiques (variance réduite)
        </label>
      </div>
    </div>

    <!-- ── Greeks ─────────────────────────────────────────────────── -->
    <div class="card">
      <h2 class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3">
        Greeks (CRN bump-and-reprice)
        <span class="font-normal text-slate-600 ml-1">— cochez puis "∂ Greeks"</span>
      </h2>
      <div class="flex flex-wrap gap-2">
        <label v-for="g in greekOptions" :key="g.key"
          class="greek-chk"
          :class="{ 'greek-chk-on': store.greekSel[g.key] }">
          <input type="checkbox" v-model="store.greekSel[g.key]" class="accent-blue-500" />
          <span v-html="g.label"></span>
          <span class="text-slate-600 text-xs ml-1" :title="g.tip">?</span>
        </label>
      </div>
    </div>

    <!-- ── Sous-jacents ───────────────────────────────────────────── -->
    <div class="card">
      <div class="flex items-center justify-between mb-3">
        <h2 class="text-xs font-bold text-slate-400 uppercase tracking-wider">Sous-jacents</h2>
        <button class="btn-secondary text-xs" @click="onAdd">+ Ajouter</button>
      </div>

      <!-- Liste des sous-jacents (toujours visible) -->
      <div class="flex gap-1 mb-3 flex-wrap items-center">
        <button v-for="(u, i) in store.underlyings" :key="i"
          @click="activeIdx = i"
          :class="[
            'px-2.5 py-1 rounded-md text-xs font-medium transition-colors border',
            activeIdx === i
              ? 'bg-blue-900/50 border-blue-600 text-blue-300'
              : 'bg-slate-800 border-slate-700 text-slate-400 hover:border-slate-500 hover:text-slate-200'
          ]">
          <span class="font-semibold">{{ demo.underlyingLabel(u.name, i) }}</span>
          <span v-if="u.ticker" class="ml-1.5 opacity-50 font-mono text-[10px]">
            <SensitiveValue placeholder="···">{{ u.ticker }}</SensitiveValue>
          </span>
        </button>
      </div>

      <!-- Card du sous-jacent actif -->
      <div v-if="au" class="bg-slate-800/60 border border-slate-700 rounded-lg p-4">

        <!-- Nom + supprimer -->
        <div class="flex items-center justify-between mb-3">
          <span v-if="demo.enabled" class="text-sm font-semibold text-slate-300 border-b border-slate-600 pb-1">
            {{ demo.underlyingLabel(au.name, activeIdx) }}
          </span>
          <input v-else v-model="au.name"
            class="input w-auto text-sm font-semibold bg-transparent border-0 border-b border-slate-600 rounded-none px-0 pb-1 focus:border-blue-500" />
          <button v-if="store.underlyings.length > 1"
            class="text-slate-600 hover:text-red-400 text-xs ml-2"
            @click="onRemove">✕</button>
        </div>

        <!-- Ticker + YF -->
        <div class="mb-1">
          <label class="label">Ticker Yahoo Finance</label>
          <SensitiveValue mode="input">
          <div class="flex gap-2 items-center">
            <!-- Menu déroulant des tickers courants -->
            <select class="select text-xs flex-1"
              :value="au.ticker"
              @change="au.ticker = $event.target.value">
              <option value="">— Choisir un sous-jacent —</option>
              <optgroup label="Indices Europe">
                <option value="^STOXX50E">Euro Stoxx 50</option>
                <option value="^FCHI">CAC 40</option>
                <option value="^GDAXI">DAX 40</option>
                <option value="^FTSE">FTSE 100</option>
                <option value="^IBEX">IBEX 35</option>
                <option value="^SSMI">SMI</option>
              </optgroup>
              <optgroup label="Indices US">
                <option value="^GSPC">S&amp;P 500</option>
                <option value="^NDX">Nasdaq 100</option>
                <option value="^DJI">Dow Jones</option>
                <option value="^RUT">Russell 2000</option>
              </optgroup>
              <optgroup label="Indices Asie">
                <option value="^N225">Nikkei 225</option>
                <option value="^HSI">Hang Seng</option>
                <option value="000300.SS">CSI 300</option>
              </optgroup>
              <optgroup label="Actions FR (CAC)">
                <option value="MC.PA">LVMH</option>
                <option value="TTE.PA">TotalEnergies</option>
                <option value="SAN.PA">Sanofi</option>
                <option value="BNP.PA">BNP Paribas</option>
                <option value="AXA.PA">AXA</option>
                <option value="OR.PA">L'Oréal</option>
                <option value="AIR.PA">Airbus</option>
              </optgroup>
              <optgroup label="Actions US">
                <option value="AAPL">Apple</option>
                <option value="MSFT">Microsoft</option>
                <option value="NVDA">Nvidia</option>
                <option value="AMZN">Amazon</option>
                <option value="GOOGL">Alphabet</option>
                <option value="META">Meta</option>
                <option value="TSLA">Tesla</option>
              </optgroup>
              <optgroup label="ETF / Matières premières">
                <option value="GLD">GLD (Or)</option>
                <option value="SLV">SLV (Argent)</option>
                <option value="USO">USO (Pétrole WTI)</option>
                <option value="SPY">SPY (S&amp;P 500 ETF)</option>
                <option value="QQQ">QQQ (Nasdaq ETF)</option>
                <option value="EEM">EEM (Émergents)</option>
              </optgroup>
            </select>
            <!-- Bouton chargement -->
            <button class="btn-secondary text-lg px-3 flex-shrink-0" title="Charger σ, q depuis Yahoo Finance"
              :disabled="store.loading || !au.ticker" @click="store.loadYfOne(activeIdx)">📡</button>
          </div>
          <!-- Saisie manuelle -->
          <input v-model="au.ticker" class="input font-mono mt-1 text-xs"
            placeholder="ou saisir manuellement ex: ^STOXX50E"
            @blur="au.ticker = au.ticker.trim().toUpperCase()" />
          </SensitiveValue>
        </div>
        <!-- YF status inline -->
        <div v-if="store.yfStatus" class="text-xs mb-2 leading-relaxed"
             :class="store.yfStatus.startsWith('⚠') ? 'text-amber-400' : 'text-green-400'">
          <SensitiveValue placeholder="Données chargées">{{ store.yfStatus }}</SensitiveValue>
        </div>

        <!-- Paramètres de base -->
        <div class="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs mb-2">
          <div>
            <label class="label">CCY</label>
            <select v-model="au.ccy" class="select">
              <option>EUR</option><option>USD</option><option>GBP</option>
              <option>JPY</option><option>CHF</option><option>SGD</option>
            </select>
          </div>
          <div>
            <label class="label">σ (%)</label>
            <SensitiveValue mode="input"><input v-model.number="au.sigma" type="number" step="0.5" class="input" /></SensitiveValue>
          </div>
          <div>
            <label class="label">q (%/an)</label>
            <SensitiveValue mode="input"><input v-model.number="au.q" type="number" step="0.1" class="input" /></SensitiveValue>
          </div>

          <!-- Heston params -->
          <template v-if="store.globalParams.model === 'heston'">
            <div><label class="label">V₀ (%)</label>
              <SensitiveValue mode="input"><input v-model.number="au.v0" type="number" step="0.5" class="input" /></SensitiveValue></div>
            <div><label class="label">κ (mean-rev.)</label>
              <SensitiveValue mode="input"><input v-model.number="au.kappa" type="number" step="0.1" class="input" /></SensitiveValue></div>
            <div><label class="label">θ long-term (%)</label>
              <SensitiveValue mode="input"><input v-model.number="au.theta" type="number" step="0.5" class="input" /></SensitiveValue></div>
            <div><label class="label">ξ vol-of-vol (%)</label>
              <SensitiveValue mode="input"><input v-model.number="au.xi" type="number" step="1" class="input" /></SensitiveValue></div>
            <div><label class="label">ρ_h corr (%)</label>
              <SensitiveValue mode="input"><input v-model.number="au.rho_h" type="number" step="1" class="input" /></SensitiveValue></div>
          </template>

          <!-- SABR params -->
          <template v-if="store.globalParams.model === 'sabr'">
            <div><label class="label">α ATM vol (%)</label>
              <SensitiveValue mode="input"><input v-model.number="au.alpha" type="number" step="0.5" class="input" /></SensitiveValue></div>
            <div><label class="label">β (%)</label>
              <SensitiveValue mode="input"><input v-model.number="au.beta" type="number" step="5" class="input" /></SensitiveValue></div>
            <div><label class="label">ρ (%)</label>
              <SensitiveValue mode="input"><input v-model.number="au.rho" type="number" step="1" class="input" /></SensitiveValue></div>
            <div><label class="label">ν vol-of-vol (%)</label>
              <SensitiveValue mode="input"><input v-model.number="au.nu" type="number" step="1" class="input" /></SensitiveValue></div>
          </template>

          <!-- Dupire local vol params -->
          <template v-if="store.globalParams.model === 'localvol'">
            <div>
              <label class="label">Skew <span class="text-slate-600 font-normal">(%/ln(K/F))</span></label>
              <SensitiveValue mode="input"><input v-model.number="au.skew" type="number" step="1" class="input" placeholder="-10" /></SensitiveValue>
            </div>
            <div>
              <label class="label">Convexité <span class="text-slate-600 font-normal">(%)</span></label>
              <SensitiveValue mode="input"><input v-model.number="au.curvature" type="number" step="0.5" class="input" placeholder="5" /></SensitiveValue>
            </div>
          </template>

          <!-- Rate-spot correlation (only meaningful once a rate model is active) -->
          <div v-if="store.globalParams.rateModel !== 'deterministic'">
            <label class="label">ρ(r,S) (%) <span class="text-slate-600 font-normal">corr taux-spot</span></label>
            <SensitiveValue mode="input"><input v-model.number="au.rho_rS" type="number" step="5" min="-100" max="100" class="input" /></SensitiveValue>
          </div>
        </div>

        <!-- Vol smile chart (Dupire / SABR / Heston) -->
        <VolSmile :idx="activeIdx" />

        <!-- Quanto / CCY -->
        <button class="text-xs text-slate-500 hover:text-blue-400 transition-colors mt-1"
                @click="au.showQuanto = !au.showQuanto">
          {{ au.showQuanto ? '▲' : '▼' }}
          Quanto / CCY
          <span v-if="au.ccy !== store.globalParams.deal_ccy" class="text-amber-500 ml-1">⚠ CCY ≠ deal</span>
        </button>

        <div v-if="au.showQuanto" class="grid grid-cols-2 sm:grid-cols-3 gap-2 text-xs mt-2 pt-2 border-t border-slate-700">
          <div>
            <label class="label">σ<sub>FX</sub> (%) <span class="text-slate-600 font-normal">vol FX</span></label>
            <SensitiveValue mode="input"><input v-model.number="au.sigma_fx" type="number" step="0.5" class="input" /></SensitiveValue>
          </div>
          <div>
            <label class="label">ρ(S,FX) (%) <span class="text-slate-600 font-normal">corr</span></label>
            <SensitiveValue mode="input"><input v-model.number="au.rho_sfx" type="number" step="1" min="-100" max="100" class="input" /></SensitiveValue>
          </div>
          <div>
            <label class="label">Basis CCYH (bp) <span class="text-slate-600 font-normal">spread</span></label>
            <SensitiveValue mode="input"><input v-model.number="au.ccyh" type="number" step="5" class="input" /></SensitiveValue>
          </div>
        </div>
      </div>
    </div>

    <!-- ── Courbe de taux ───────────────────────────────────────────── -->
    <YieldCurveCard />

    <!-- ── Matrice corrélation ────────────────────────────────────── -->
    <div v-if="store.underlyings.length > 1" class="card">
      <h2 class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3">Matrice de corrélation</h2>
      <div class="overflow-x-auto">
        <table class="text-xs border-collapse">
          <thead>
            <tr>
              <th class="w-20"></th>
              <th v-for="(u, j) in store.underlyings" :key="j"
                  class="text-slate-400 font-medium pb-1 px-2 text-center">
                {{ demo.underlyingLabel(u.name, j).slice(0, 7) }}
              </th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(u, i) in store.underlyings" :key="i">
              <td class="text-slate-400 font-medium pr-2 py-1 whitespace-nowrap">{{ demo.underlyingLabel(u.name, i).slice(0, 7) }}</td>
              <td v-for="(_, j) in store.underlyings" :key="j" class="px-1 py-0.5">
                <SensitiveValue v-if="i !== j" mode="input" placeholder="·.··">
                  <input type="number" step="0.05" min="-1" max="1"
                    :value="store.corrMatrix[i]?.[j] ?? 0"
                    @input="setCorr(i, j, $event.target.value)"
                    class="input w-16 text-center text-xs" />
                </SensitiveValue>
                <span v-else class="block text-center text-slate-600 w-16">1.00</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { usePricingStore } from '../stores/pricing.js'
import { useDemoModeStore } from '../stores/demoMode.js'
import VolSmile from './VolSmile.vue'
import YieldCurveCard from './YieldCurveCard.vue'
import SensitiveValue from './SensitiveValue.vue'

const store = usePricingStore()
const demo = useDemoModeStore()

// Active underlying selector
const activeIdx = ref(0)
const au = computed(() => store.underlyings[activeIdx.value] ?? store.underlyings[0])

function onAdd() {
  store.addUnderlying()
  activeIdx.value = store.underlyings.length - 1
}

function onRemove() {
  const i = activeIdx.value
  store.removeUnderlying(i)
  activeIdx.value = Math.min(i, store.underlyings.length - 1)
}

const greekOptions = [
  { key: 'delta', label: '&Delta; Delta',  tip: 'Sensibilité au spot (+1% bump centré)' },
  { key: 'gamma', label: '&Gamma; Gamma',  tip: 'Convexité au spot (±3% bump)' },
  { key: 'vega',  label: '&nu; Vega',      tip: 'Sensibilité à la vol (+1% bump)' },
  { key: 'theta', label: '&Theta; Theta',  tip: 'Décroissance temporelle (1j)' },
  { key: 'rho',   label: '&rho; Rho',      tip: 'Sensibilité aux taux (+100bp)' },
  { key: 'corr',  label: '&rho;<sub>ij</sub> Corr', tip: 'Sensibilité corrélation (+5%, multi-actifs)' },
]

function setCorr(i, j, val) {
  const v = Math.max(-1, Math.min(1, parseFloat(val) || 0))
  if (!store.corrMatrix[i]) store.corrMatrix[i] = []
  store.corrMatrix[i][j] = v
  store.corrMatrix[j][i] = v
}
</script>

<style scoped>
.greek-chk {
  @apply inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border border-slate-700
         text-xs font-semibold text-slate-400 cursor-pointer bg-slate-800/50
         hover:border-blue-600 hover:text-blue-400 transition-colors select-none;
}
.greek-chk-on {
  @apply border-blue-600 bg-blue-950/50 text-blue-400;
}
</style>
