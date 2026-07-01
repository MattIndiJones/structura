<template>
  <div class="flex flex-col gap-6 p-1">

    <!-- Pas de résultat -->
    <div v-if="!store.result" class="text-center py-12 text-slate-600">
      <p class="text-sm">Lancez un pricing (▶ Pricer) pour calculer le KID.</p>
    </div>

    <template v-else>

      <!-- ── Paramètres KID ─────────────────────────────────── -->
      <div class="card">
        <h3 class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3">Paramètres KID</h3>
        <div class="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <div>
            <label class="label">CRM (risque crédit)</label>
            <select v-model.number="params.crm" class="select text-xs">
              <option :value="1">1 — AAA</option>
              <option :value="2">2 — AA</option>
              <option :value="3">3 — A / BBB (défaut)</option>
              <option :value="4">4 — BB</option>
              <option :value="5">5 — B</option>
              <option :value="6">6 — CCC et moins</option>
            </select>
          </div>
          <div>
            <label class="label">Frais d'entrée (%)</label>
            <input v-model.number="params.cost_entry" type="number" step="0.1" min="0" max="10" class="input text-xs" />
          </div>
          <div>
            <label class="label">Frais de sortie (%)</label>
            <input v-model.number="params.cost_exit" type="number" step="0.1" min="0" max="10" class="input text-xs" />
          </div>
          <div>
            <label class="label">Frais courants (% / an)</label>
            <input v-model.number="params.cost_ongoing" type="number" step="0.01" min="0" max="5" class="input text-xs" />
          </div>
        </div>
        <div class="flex items-center gap-3 mt-3">
          <button class="btn-primary text-xs px-4 py-2" @click="compute" :disabled="loading">
            <span v-if="loading"
              class="w-3 h-3 border-2 border-white border-t-transparent rounded-full animate-spin inline-block mr-1.5"></span>
            {{ loading ? 'Calcul KID…' : '⚖ Calculer le KID PRIIPs' }}
          </button>
          <span v-if="error" class="text-xs text-red-400">⚠ {{ error }}</span>
        </div>
      </div>

      <!-- ── SRI ───────────────────────────────────────────── -->
      <div v-if="kid" class="card">
        <h3 class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-4">
          Indicateur Synthétique de Risque (SRI)
        </h3>
        <div class="flex items-center gap-6">
          <!-- Gauge 1-7 -->
          <div class="flex gap-1">
            <div v-for="n in 7" :key="n"
              class="flex flex-col items-center gap-1">
              <div class="w-9 h-9 rounded flex items-center justify-center text-sm font-black transition-all"
                :class="n === kid.sri
                  ? 'scale-110 ring-2 ring-white text-white ' + sriColorBg(n)
                  : 'opacity-30 text-slate-500 ' + sriColorBg(n)">
                {{ n }}
              </div>
              <div class="text-[8px] text-slate-600 text-center leading-tight hidden sm:block" style="width:36px">
                {{ sriLabel(n) }}
              </div>
            </div>
          </div>

          <!-- Détails -->
          <div class="flex flex-col gap-1.5">
            <div class="flex items-center gap-2 text-xs">
              <span class="text-slate-500 w-36">Risque marché (MRM)</span>
              <span class="font-mono font-bold text-slate-200">{{ kid.mrm }} / 7</span>
            </div>
            <div class="flex items-center gap-2 text-xs">
              <span class="text-slate-500 w-36">Risque crédit (CRM)</span>
              <span class="font-mono font-bold text-slate-200">{{ kid.crm }} / 6</span>
            </div>
            <div class="flex items-center gap-2 text-xs">
              <span class="text-slate-500 w-36">VEV (équiv. vol)</span>
              <span class="font-mono font-bold text-slate-200">{{ kid.vev.toFixed(1) }}%</span>
            </div>
            <div class="flex items-center gap-2 text-xs">
              <span class="text-slate-500 w-36">Durée recommandée</span>
              <span class="font-mono font-bold text-slate-200">{{ kid.T_rhp.toFixed(1) }} ans</span>
            </div>
          </div>
        </div>

        <p class="text-[10px] text-slate-600 mt-4 pt-3 border-t border-slate-800">
          L'indicateur de risque part de l'hypothèse que vous conservez le produit {{ kid.T_rhp.toFixed(1) }} an(s).
          Si vous le vendez avant cette date, le risque réel peut être très différent.
          PRIIPs Règlement (UE) 1286/2014 — calcul interne MC, non officiel.
        </p>
      </div>

      <!-- ── Scénarios de performance ───────────────────────── -->
      <div v-if="kid" class="card">
        <div class="flex items-center justify-between mb-4">
          <h3 class="text-xs font-bold text-slate-400 uppercase tracking-wider">
            Scénarios de performance
          </h3>
          <span class="text-[10px] text-slate-600 italic">Pour un investissement de 10 000 €</span>
        </div>

        <div class="overflow-x-auto">
          <table class="w-full text-xs border-collapse">
            <thead>
              <tr class="border-b border-slate-700">
                <th class="text-left text-slate-500 font-medium pb-2 pr-4">Scénario</th>
                <th v-for="h in kid.horizons" :key="h.T"
                  class="text-right text-slate-500 font-medium pb-2 px-3 whitespace-nowrap">
                  {{ h.T >= kid.T_rhp ? 'Maturité' : h.T.toFixed(0) + ' an' + (h.T > 1 ? 's' : '') }}
                  <span class="block font-normal text-slate-600">{{ h.T.toFixed(2) }}Y</span>
                </th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="sc in scenarios" :key="sc.key"
                class="border-b border-slate-800/60 hover:bg-slate-800/20">
                <td class="py-3 pr-4">
                  <div class="flex items-center gap-2">
                    <div class="w-2 h-2 rounded-full shrink-0" :class="sc.dot"></div>
                    <div>
                      <div :class="sc.labelClass" class="font-semibold">{{ sc.label }}</div>
                      <div class="text-[10px] text-slate-600">{{ sc.sub }}</div>
                    </div>
                  </div>
                </td>
                <td v-for="h in kid.horizons" :key="h.T" class="py-3 px-3 text-right">
                  <div class="font-mono font-bold text-sm"
                    :class="h[sc.key].amount >= 10000 ? 'text-slate-200' : 'text-red-400'">
                    {{ fmtAmount(h[sc.key].amount) }} €
                  </div>
                  <div class="font-mono text-[10px] mt-0.5"
                    :class="h[sc.key].ann_return >= 0 ? 'text-emerald-400' : 'text-red-400'">
                    {{ h[sc.key].ann_return >= 0 ? '+' : '' }}{{ h[sc.key].ann_return.toFixed(2) }}% / an
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <p class="text-[10px] text-slate-600 mt-3 pt-3 border-t border-slate-800">
          Les scénarios défavorable / modéré / favorable correspondent aux percentiles P10 / P50 / P90 de la
          distribution Monte Carlo. Le scénario stress correspond au P1. Les horizons intermédiaires utilisent
          une approximation de la valeur de continuation (prix équitable au rachat anticipé).
        </p>
      </div>

      <!-- ── Coûts ──────────────────────────────────────────── -->
      <div v-if="kid" class="card">
        <h3 class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3">Composition des coûts</h3>
        <div class="grid grid-cols-3 gap-4 text-xs">
          <div class="bg-slate-800/40 rounded-lg px-4 py-3 text-center">
            <div class="text-slate-500 mb-1">Frais d'entrée</div>
            <div class="font-mono font-bold text-slate-200 text-sm">{{ kid.costs.entry.toFixed(2) }}%</div>
            <div class="text-slate-600 text-[10px] mt-1">{{ fmtAmount(10000 * kid.costs.entry / 100) }} € / 10 k€</div>
          </div>
          <div class="bg-slate-800/40 rounded-lg px-4 py-3 text-center">
            <div class="text-slate-500 mb-1">Frais courants / an</div>
            <div class="font-mono font-bold text-slate-200 text-sm">{{ kid.costs.ongoing.toFixed(2) }}%</div>
            <div class="text-slate-600 text-[10px] mt-1">{{ fmtAmount(10000 * kid.costs.ongoing / 100) }} € / 10 k€</div>
          </div>
          <div class="bg-slate-800/40 rounded-lg px-4 py-3 text-center">
            <div class="text-slate-500 mb-1">Frais de sortie</div>
            <div class="font-mono font-bold text-slate-200 text-sm">{{ kid.costs.exit.toFixed(2) }}%</div>
            <div class="text-slate-600 text-[10px] mt-1">{{ fmtAmount(10000 * kid.costs.exit / 100) }} € / 10 k€</div>
          </div>
        </div>
        <div class="flex items-center justify-between mt-3 pt-3 border-t border-slate-800 text-xs">
          <span class="text-slate-500">Impact total des coûts sur la durée recommandée</span>
          <span class="font-mono font-bold text-amber-400">
            {{ totalCostImpact }}
          </span>
        </div>
      </div>

      <!-- ── Bouton générer PDF ──────────────────────────────── -->
      <div v-if="kid" class="flex gap-3">
        <button class="btn-secondary text-xs px-4 py-2 flex-1" @click="printKid">
          🖨️ Imprimer / Exporter PDF
        </button>
        <button class="btn-secondary text-xs px-4 py-2" @click="goToDoc">
          📁 Enregistrer dans Documentation
        </button>
      </div>

    </template>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { usePricingStore } from '../stores/pricing.js'
import { apiFetch } from '../utils/api.js'

const store = usePricingStore()

const loading = ref(false)
const error   = ref('')
const kid     = ref(null)

const params = ref({
  crm: 3,
  cost_entry: 0,
  cost_exit: 0,
  cost_ongoing: 0,
})

// ── Scenarios metadata ────────────────────────────────────
const scenarios = [
  { key: 'stress',      label: 'Stress',      sub: 'Percentile 1%',  dot: 'bg-red-600',    labelClass: 'text-red-400' },
  { key: 'defavorable', label: 'Défavorable', sub: 'Percentile 10%', dot: 'bg-orange-500', labelClass: 'text-orange-400' },
  { key: 'modere',      label: 'Modéré',      sub: 'Percentile 50%', dot: 'bg-slate-400',  labelClass: 'text-slate-300' },
  { key: 'favorable',   label: 'Favorable',   sub: 'Percentile 90%', dot: 'bg-emerald-500',labelClass: 'text-emerald-400' },
]

// ── SRI helpers ──────────────────────────────────────────
function sriColorBg(n) {
  const map = {
    1: 'bg-emerald-700', 2: 'bg-green-600', 3: 'bg-yellow-600',
    4: 'bg-amber-500',   5: 'bg-orange-600', 6: 'bg-red-600', 7: 'bg-red-800',
  }
  return map[n] || 'bg-slate-700'
}

function sriLabel(n) {
  const map = { 1: 'Très faible', 2: 'Faible', 3: 'Moyen-faible', 4: 'Moyen', 5: 'Moyen-élevé', 6: 'Élevé', 7: 'Très élevé' }
  return map[n] || ''
}

// ── Formatting ───────────────────────────────────────────
function fmtAmount(n) {
  return Math.round(n).toLocaleString('fr-FR')
}

const totalCostImpact = computed(() => {
  if (!kid.value) return '—'
  const T = kid.value.T_rhp
  const c = kid.value.costs
  const impact = (c.entry + c.exit) / 100 + c.ongoing / 100 * T
  return `-${(impact * 100).toFixed(2)}%`
})

// ── Compute KID ──────────────────────────────────────────
async function compute() {
  if (!store.result) return
  loading.value = true
  error.value = ''
  kid.value = null

  try {
    const res = await apiFetch('/api/kid/compute', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        ...store.pricingBody(),
        crm: params.value.crm,
        cost_entry: params.value.cost_entry,
        cost_exit: params.value.cost_exit,
        cost_ongoing: params.value.cost_ongoing,
      }),
    })
    if (!res.ok) {
      const text = await res.text()
      try { const err = JSON.parse(text); throw new Error(err.detail || 'Erreur KID') }
      catch { throw new Error(`Erreur ${res.status}: ${text.slice(0, 300)}`) }
    }
    kid.value = await res.json()
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

// ── Actions ──────────────────────────────────────────────
function printKid() {
  window.print()
}

function goToDoc() {
  // TODO: ouvre la page Documentation avec le KID pré-rempli
  window.open('#/documentation', '_blank')
}
</script>
