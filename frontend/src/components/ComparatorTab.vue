<template>
  <div class="flex flex-col gap-4">
    <!-- Header + controls -->
    <div class="card">
      <div class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-1">
        🔎 Comparateur de sous-jacents — quel candidat aurait le mieux backtesté ?
      </div>
      <div class="text-xs text-slate-500 mb-4">
        Taille de panier requise par le produit :
        <span class="font-mono font-bold text-slate-200">{{ basketSize }}</span>
        <span class="text-slate-600">{{ basketSize > 1 ? ` (worst-of ${basketSize} — d'après le nombre de sous-jacents dans "Marché & Paramètres")` : ' (mono-sous-jacent)' }}</span>
      </div>

      <!-- Candidate pool -->
      <div class="mb-4">
        <div class="flex items-center justify-between mb-2">
          <label class="label mb-0">Univers candidat à tester</label>
          <button class="text-xs px-2 py-1 bg-slate-700 hover:bg-slate-600 text-slate-200 rounded" @click="addCandidate">+ Ajouter</button>
        </div>
        <div class="flex flex-col gap-2">
          <div v-for="(c, i) in pool" :key="i" class="flex gap-2 items-center">
            <select class="select text-xs flex-1" :value="c.ticker" @change="c.ticker = $event.target.value">
              <option value="">— Choisir un sous-jacent —</option>
              <optgroup v-for="g in underlyingGroups" :key="g.group" :label="g.group">
                <option v-for="it in g.items" :key="it.ticker" :value="it.ticker">{{ it.label }}</option>
              </optgroup>
            </select>
            <input v-model="c.ticker" class="input font-mono text-xs w-32"
              placeholder="ou saisir un ticker" @blur="c.ticker = c.ticker.trim().toUpperCase()" />
            <button class="text-slate-600 hover:text-red-400 text-xs px-1" :disabled="pool.length <= 1" @click="pool.splice(i, 1)">✕</button>
          </div>
        </div>
      </div>

      <div class="grid grid-cols-2 sm:grid-cols-3 gap-3 text-xs mb-4">
        <div v-if="basketSize > 1">
          <label class="label">Shortlist (candidats retenus)
            <HelpTip width="w-72" text="Étape 1 : chaque candidat est backtesté seul et classé. Étape 2 : les combinaisons ne sont formées qu'à partir des N meilleurs de ce classement — un candidat faible seul a peu de chances de sauver un panier worst-of (c'est le pire qui compte)." />
          </label>
          <input v-model.number="form.shortlist_n" type="number" min="2" max="20" class="input" />
        </div>
        <div>
          <label class="label">Date de début</label>
          <input v-model="form.start_date" type="date" class="input" />
        </div>
        <div>
          <label class="label">Fréquence relance (j ouvrés)</label>
          <select v-model.number="form.freq" class="select">
            <option :value="1">Quotidien (1j)</option>
            <option :value="5">Hebdo (5j)</option>
            <option :value="21">Mensuel (21j)</option>
            <option :value="63">Trimestriel (63j)</option>
            <option :value="126">Semestriel (126j)</option>
          </select>
        </div>
        <div>
          <label class="label">Montant investi (%)</label>
          <input v-model.number="form.invest_pct" type="number" step="10" min="10" max="200" class="input" />
        </div>
      </div>
      <div class="flex justify-end">
        <button class="btn-primary text-xs px-5" :disabled="store.comparatorLoading || !canRun" @click="launch">
          <span v-if="store.comparatorLoading" class="w-3 h-3 border border-white border-t-transparent rounded-full animate-spin inline-block mr-1"></span>
          ▶ Lancer la comparaison
        </button>
      </div>
      <div v-if="!canRun" class="text-xs text-amber-500 mt-2">
        Il faut au moins {{ basketSize }} candidat(s) distinct(s) avec ticker renseigné pour tester un panier de cette taille.
      </div>
      <div v-if="store.comparatorError" class="text-xs text-red-400 mt-2">⚠ {{ store.comparatorError }}</div>
    </div>

    <!-- Empty state -->
    <div v-if="!store.comparator" class="flex flex-col items-center justify-center h-40 text-slate-600 gap-2">
      <div class="text-3xl">🔎</div>
      <div class="text-sm font-medium">Configurez l'univers candidat et lancez la comparaison</div>
    </div>

    <template v-else>
      <div v-if="store.comparator.shortlist && basketSize > 1" class="text-xs text-slate-500">
        Shortlist retenue pour les combinaisons : {{ store.comparator.shortlist.map(labelFor).join(', ') }}
      </div>

      <div class="card overflow-x-auto">
        <table class="text-xs w-full border-collapse">
          <thead>
            <tr class="border-b border-slate-700">
              <th class="text-left text-slate-500 font-medium py-1 pr-3">Sous-jacent(s)</th>
              <th class="text-right text-slate-500 font-medium py-1 pr-3">TRI médian</th>
              <th class="text-right text-slate-500 font-medium py-1 pr-3">TRI moyen</th>
              <th class="text-right text-slate-500 font-medium py-1 pr-3">
                P10 / pire
                <HelpTip align="right" text="Un médian/moyen correct peut cacher une queue de perte réelle (payoff worst-of asymétrique) — regardez cette colonne avant d'adopter un panier, pas seulement le TRI médian." />
              </th>
              <th class="text-right text-slate-500 font-medium py-1 pr-3">% positif</th>
              <th class="text-right text-slate-500 font-medium py-1 pr-3">% rappel</th>
              <th class="text-right text-slate-500 font-medium py-1 pr-3">Fenêtres</th>
              <th class="text-right text-slate-500 font-medium py-1"></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(row, i) in store.comparator.results" :key="rowKey(row)"
                class="border-b border-slate-800 hover:bg-slate-800/40 transition-colors">
              <td class="py-1.5 pr-3 text-slate-200 font-medium">
                <span :class="i === 0 ? 'text-amber-400' : ''">{{ i === 0 ? '🏆 ' : '' }}{{ row.tickers.map(labelFor).join(' / ') }}</span>
              </td>
              <td class="py-1.5 pr-3 text-right font-mono text-green-400">{{ formatPercent(row.median_irr * 100, 2) }}</td>
              <td class="py-1.5 pr-3 text-right font-mono text-slate-300">{{ formatPercent(row.mean_irr * 100, 2) }}</td>
              <td class="py-1.5 pr-3 text-right font-mono" :class="row.worst_irr < 0 ? 'text-red-400' : 'text-slate-400'">
                {{ formatPercent(row.p10_irr * 100, 2) }} / {{ formatPercent(row.worst_irr * 100, 2) }}
              </td>
              <td class="py-1.5 pr-3 text-right text-slate-400">{{ formatPercent(row.pct_positive, 1) }}</td>
              <td class="py-1.5 pr-3 text-right text-slate-400">{{ formatPercent(row.early_recall_pct, 1) }}</td>
              <td class="py-1.5 pr-3 text-right text-slate-500">{{ formatInt(row.n_windows) }}</td>
              <td class="py-1.5 text-right whitespace-nowrap">
                <button class="text-[10px] px-2 py-1 bg-slate-700 hover:bg-slate-600 text-slate-200 rounded mr-1"
                        :disabled="rowState(row).pricing" @click="quotePrice(row)">
                  <span v-if="rowState(row).pricing">…</span>
                  <span v-else-if="rowState(row).price != null">{{ formatPercent(rowState(row).price * 100, 2) }}</span>
                  <span v-else>💰 Prix indicatif</span>
                </button>
                <button class="text-[10px] px-2 py-1 bg-blue-700 hover:bg-blue-600 text-white rounded"
                        :disabled="rowState(row).adopting" @click="adopt(row)">
                  {{ rowState(row).adopted ? '✓ Adopté' : '✓ Adopter ce panier' }}
                </button>
                <div v-if="rowState(row).error" class="text-[10px] text-red-400 mt-0.5">{{ rowState(row).error }}</div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
  </div>
</template>

<script setup>
import { reactive, ref, computed, onMounted } from 'vue'
import { usePricingStore } from '../stores/pricing.js'
import { apiFetch } from '../utils/api.js'
import { underlyingGroups, ensureUnderlyings } from '../data/commonUnderlyings.js'
import { formatPercent, formatInt } from '../utils/format.js'
import HelpTip from './HelpTip.vue'

// Catalogue de sous-jacents : chargé depuis la base au montage.
onMounted(ensureUnderlyings)

const store = usePricingStore()

// The product's required basket size is not a choice — it's however many
// underlyings are currently configured for pricing in Marché & Paramètres.
const basketSize = computed(() => Math.max(1, store.underlyings.filter(u => u.ticker?.trim()).length))

// Candidate pool — independent from store.underlyings, drawn from the
// shared catalog (commonUnderlyings.js) also used by DealTab/RfqView, so
// tickers/labels stay consistent everywhere.
// Calculee, et non figee au chargement du module : le catalogue arrive de
// la base apres le montage.
const tickerLabels = computed(() =>
  Object.fromEntries(underlyingGroups.flatMap(g => g.items.map(it => [it.ticker, it.label]))))
function labelFor(ticker) {
  return tickerLabels.value[ticker] || ticker
}

const pool = ref([{ ticker: '' }, { ticker: '' }, { ticker: '' }])
function addCandidate() {
  pool.value.push({ ticker: '' })
}

const canRun = computed(() => {
  const distinct = new Set(pool.value.map(c => c.ticker?.trim()).filter(Boolean))
  return distinct.size >= basketSize.value
})

const today = new Date().toISOString().slice(0, 10)
const form = reactive({
  shortlist_n: 8,
  start_date: '2010-01-01',
  end_date: today,
  freq: 21,
  invest_pct: 100,
  rf_rate: 2.0,
})

function launch() {
  const candidates = pool.value
    .map(c => ({ ticker: c.ticker?.trim().toUpperCase() || '', name: labelFor(c.ticker?.trim().toUpperCase() || '') }))
    .filter(c => c.ticker)
  store.runBacktestCompare(candidates, { ...form, basket_size: basketSize.value })
}

function rowKey(row) {
  return row.tickers.join('|')
}

// Per-row UI state (price quote / adopt), keyed by the same row key.
const rowStates = reactive({})
function rowState(row) {
  const k = rowKey(row)
  if (!rowStates[k]) rowStates[k] = { pricing: false, price: null, adopting: false, adopted: false, error: '' }
  return rowStates[k]
}

async function quotePrice(row) {
  const st = rowState(row)
  st.pricing = true; st.error = ''
  try {
    const res = await apiFetch(`/api/finance/hist_vol?tickers=${encodeURIComponent(row.tickers.join(','))}&period=1y`)
    const vol = await res.json()
    if (vol.error) throw new Error(vol.error)

    const underlyings = row.tickers.map(tk => ({
      name: labelFor(tk), ticker: tk, ccy: 'EUR',
      sigma: vol.vols?.[tk] ?? 0.20,
      q: vol.div_yields?.[tk] ?? 0,
    }))

    const priceRes = await apiFetch('/api/price', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        script: store.script,
        underlyings,
        corr_matrix: row.corr_matrix,
        r: store.globalParams.r / 100,
        T: store.globalParams.T,
        N: 8000,
        seed: store.globalParams.seed,
        model: store.globalParams.model,
        user_params: store.pricingBody().user_params,
        constats: store.pricingBody().constats,
      }),
    })
    if (!priceRes.ok) {
      const err = await priceRes.json().catch(() => ({}))
      throw new Error(err.detail || `Erreur ${priceRes.status}`)
    }
    const data = await priceRes.json()
    st.price = data.price
  } catch (e) {
    st.error = e.message || 'Erreur de pricing'
  } finally {
    st.pricing = false
  }
}

async function adopt(row) {
  const st = rowState(row)
  st.adopting = true; st.error = ''
  try {
    await store.adoptBasket(row.tickers, row.tickers.map(labelFor), row.corr_matrix)
    st.adopted = true
    store.leftTab = 'params'
  } catch (e) {
    st.error = e.message || "Erreur lors de l'adoption"
  } finally {
    st.adopting = false
  }
}
</script>
