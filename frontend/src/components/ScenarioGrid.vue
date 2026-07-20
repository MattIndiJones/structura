<template>
  <div class="card">
    <div class="flex items-center gap-3 flex-wrap mb-3">
      <div class="text-xs font-bold text-slate-400 uppercase tracking-wider">🎯 Scénarios — stress spot × vol</div>
      <div class="ml-auto">
        <button class="btn-primary text-xs px-4" :disabled="store.loading || !store.result" @click="launch">
          <span v-if="store.loading" class="w-3 h-3 border border-white border-t-transparent rounded-full animate-spin inline-block mr-1"></span>
          ▶ Calculer
        </button>
      </div>
    </div>

    <div class="text-xs text-slate-400 leading-relaxed bg-slate-800/50 border-l-2 border-blue-500 rounded-lg px-3 py-2 mb-4">
      Reprice complet du produit pour chaque combinaison de choc spot (multiplicatif) et vol (additif, en points
      de %), avec le même seed que le pricing principal (chemins communs) pour une grille comparable cellule à cellule.
    </div>

    <div class="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs mb-3">
      <div>
        <label class="label">Chocs spot (%, séparés par virgule)
          <HelpTip text="Chocs MULTIPLICATIFS sur le spot : -10 veut dire spot × 0,90. Ne pas confondre avec les chocs vol ci-contre, qui sont additifs — les deux se lisent différemment." />
        </label>
        <input v-model="spotInput" type="text" class="input" />
      </div>
      <div>
        <label class="label">Chocs vol (pts de %, séparés par virgule)
          <HelpTip text="Chocs ADDITIFS sur la vol, en points de %: +5 sur une vol de 20% donne 25% (pas 20%×1,05). C'est l'inverse de la convention des chocs spot à gauche, qui sont multiplicatifs." />
        </label>
        <input v-model="volInput" type="text" class="input" />
      </div>
      <div>
        <label class="label">N chemins / cellule
          <HelpTip text="Chemins MC par cellule — chaque cellule est un reprice indépendant, avec le même seed que le pricing principal (chemins communs entre cellules) pour que les écarts observés reflètent le choc, pas juste du bruit d'échantillonnage différent." />
        </label>
        <SensitiveValue mode="input"><input v-model.number="N" type="number" step="500" min="300" max="20000" class="input" /></SensitiveValue>
      </div>
    </div>

    <div v-if="!store.result" class="text-xs text-amber-500 mb-3">
      Lancez d'abord un pricing (▶ Pricer) pour fixer le scénario de base.
    </div>

    <div v-if="!store.scenarios" class="text-xs text-slate-600 text-center py-6">
      Configurez les chocs et lancez le calcul.
    </div>

    <div v-else class="overflow-x-auto">
      <table class="border-collapse text-xs mx-auto">
        <thead>
          <tr>
            <th class="p-1 text-right text-slate-500 font-semibold whitespace-nowrap pr-2">Δvol \ Δspot
              <HelpTip text="Lignes = choc de vol (additif, pts de %), colonnes = choc de spot (multiplicatif, %). Le prix sous chaque pourcentage est l'écart en points de prix (pp) par rapport à la cellule encadrée en bleu (scénario de base, sans choc)." />
            </th>
            <th v-for="(s, i) in store.scenarios.spot_shocks" :key="'hx' + i"
                class="p-1 text-center text-slate-400 font-semibold whitespace-nowrap">
              <SensitiveValue>{{ fmtPct(s) }}</SensitiveValue>
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(v, j) in store.scenarios.vol_shocks" :key="'row' + j">
            <th class="p-1 text-right text-slate-400 font-semibold whitespace-nowrap pr-2"><SensitiveValue>{{ fmtPp(v) }}</SensitiveValue></th>
            <td v-for="(s, i) in store.scenarios.spot_shocks" :key="'cell' + i + '-' + j" class="p-0.5 text-center">
              <!-- Color (the heatmap "shape") stays visible even in demo mode — only the exact digits hide. -->
              <div class="w-[70px] h-11 flex flex-col items-center justify-center rounded-sm text-slate-100"
                   :class="isBase(s, v) ? 'ring-2 ring-blue-400' : ''"
                   :style="{ background: cellColor(store.scenarios.prices[j][i]) }"
                   :title="demo.enabled ? '' : `Δspot=${fmtPct(s)} · Δvol=${fmtPp(v)} -> ${(store.scenarios.prices[j][i] * 100).toFixed(2)}%`">
                <div class="font-mono font-bold text-[11px]"><SensitiveValue>{{ (store.scenarios.prices[j][i] * 100).toFixed(1) }}%</SensitiveValue></div>
                <div class="font-mono text-[10px]" :class="deltaCls(store.scenarios.prices[j][i])">
                  <SensitiveValue>{{ fmtDelta(store.scenarios.prices[j][i]) }}</SensitiveValue>
                </div>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
      <div class="text-xs text-slate-600 mt-3 text-center">
        Base (cadre bleu) : <strong class="text-slate-300"><SensitiveValue>{{ (store.scenarios.base_price * 100).toFixed(2) }}%</SensitiveValue></strong>
        · N = <SensitiveValue>{{ N }}</SensitiveValue> chemins/cellule · même seed que le pricing principal
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { usePricingStore } from '../stores/pricing.js'
import { useDemoModeStore } from '../stores/demoMode.js'
import SensitiveValue from './SensitiveValue.vue'
import HelpTip from './HelpTip.vue'

const store = usePricingStore()
const demo = useDemoModeStore()

const spotInput = ref('-30,-20,-10,-5,0,5,10,20,30')
const volInput = ref('10,5,0,-5,-10')
const N = ref(2000)

function parseList(str) {
  return str.split(',').map(s => parseFloat(s.trim())).filter(v => !isNaN(v))
}

function launch() {
  store.runScenarios({
    spot_shocks_pct: parseList(spotInput.value),
    vol_shocks_pct: parseList(volInput.value),
    N: N.value,
  })
}

const fmtPct = v => (v >= 0 ? '+' : '') + Math.round(v * 100) + '%'
const fmtPp = v => (v > 0 ? '+' : '') + Math.round(v * 100) + 'pp'

function isBase(s, v) { return s === 0 && v === 0 }

const basePrice = computed(() => store.scenarios?.base_price ?? 1.0)
const delta = price => price - basePrice.value

function fmtDelta(price) {
  const d = delta(price) * 100
  return (d >= 0 ? '+' : '') + d.toFixed(1) + 'pp'
}
function deltaCls(price) {
  const d = delta(price)
  return d > 0 ? 'text-green-300' : d < 0 ? 'text-red-300' : 'text-slate-400'
}

// Same visual language as PriceGridHeatmap: diverging red/green centered on
// the base (unshocked) price, intensity scaled so a 15pp move is "full color".
function cellColor(price) {
  const d = delta(price)
  const intensity = Math.min(1, Math.abs(d) / 0.15)
  if (d > 0) return `rgba(34,197,94,${0.12 + intensity * 0.58})`
  if (d < 0) return `rgba(239,68,68,${0.12 + intensity * 0.58})`
  return 'rgba(100,116,139,.25)'
}
</script>
