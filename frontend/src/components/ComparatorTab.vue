<template>
  <div class="flex flex-col gap-4">
    <div v-if="Object.keys(store.comparator?.excluded_universe || {}).length" class="card text-xs text-amber-400">
      Univers réduit pour cette exploration :
      <SensitiveValue>{{ Object.values(store.comparator.excluded_universe).map(row => `${row.ticker} (${row.reason})`).join(', ') }}</SensitiveValue>.
      Ces exclusions ne qualifient pas un calcul du panier complet.
    </div>
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
          <input v-model="form.start_date" type="date" class="input" aria-label="Date de début du comparateur" @input="history.manualStart.value = true" />
          <button v-if="history.manualStart.value" class="underline mt-1" @click="history.useSuggestedStart">Utiliser le début commun</button>
        </div>
        <div>
          <label class="label">Date de fin</label>
          <input v-model="form.end_date" type="date" class="input" aria-label="Date de fin du comparateur" />
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
        <div>
          <label class="label">Cours absent</label>
          <select v-model="form.history_mode" class="select" aria-label="Convention du comparateur">
            <option value="following">Following — prochain cours commun</option>
            <option value="strict">Strict — aucun remplacement</option>
          </select>
        </div>
        <div>
          <label class="label">Décalage maximal (jours calendaires)</label>
          <input v-model.number="form.max_delay_days" type="number" min="0" max="31" step="1" class="input"
            aria-label="Décalage maximal du comparateur" :disabled="form.history_mode === 'strict'" />
        </div>
      </div>
      <p v-if="history.loading.value" class="text-xs mb-2" role="status">Recherche du début commun local…</p>
      <p v-else-if="history.error.value" class="text-xs text-amber-600 mb-2" role="status">{{ history.error.value }} Le début automatique sera recherché au lancement.</p>
      <p v-else-if="history.suggestedStart.value" class="text-xs text-slate-500 mb-2">Début commun local provisoire : {{ formatDate(history.suggestedStart.value) }}. Au lancement, recherche de l’historique maximal Yahoo et conservation pour les prochains calculs.</p>
      <p v-else class="text-xs text-slate-500 mb-2">Sans début commun local connu, laissez la date vide pour un début automatique au lancement.</p>
      <p class="text-xs text-slate-500 mb-3">Les candidats sont comparés sur les mêmes dates communes de l’univers exploitable. Following décale la constatation et son paiement du même nombre de jours calendaires.</p>
      <div class="flex justify-end">
        <button class="btn-primary text-xs px-5" :disabled="store.comparatorLoading || history.loading.value || !canRun" @click="launch">
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
      <BacktestHistoryDetails :result="store.comparator" />
      <div v-if="store.comparator.shortlist && basketSize > 1" class="text-xs text-slate-500">
        Shortlist retenue pour les combinaisons : {{ store.comparator.shortlist.map(labelFor).join(', ') }}
      </div>

      <div class="card overflow-x-auto">
        <table class="text-xs w-full border-collapse whitespace-nowrap">
          <thead class="whitespace-nowrap">
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
              <th class="text-right text-slate-500 font-medium py-1">Actions</th>
            </tr>
          </thead>
          <tbody>
            <template v-for="(row, i) in store.comparator.results" :key="rowKey(row)">
            <tr class="border-b border-slate-800 cursor-pointer transition-colors"
                :class="selectedRow && rowKey(selectedRow) === rowKey(row) ? 'bg-blue-100 hover:bg-blue-100' : 'hover:bg-blue-50'"
                tabindex="0" :aria-selected="selectedRow && rowKey(selectedRow) === rowKey(row)"
                @click="selectResult(row)" @keydown.enter.self="selectResult(row)" @keydown.space.self.prevent="selectResult(row)">
              <td class="py-1.5 pr-3 text-slate-200 font-medium">
                <button class="text-left hover:underline" :aria-label="`Voir le backtest de ${namesFor(row)}`"
                  @click.stop="selectResult(row)"><span :class="i === 0 ? 'text-amber-400' : ''">{{ i === 0 ? '🏆 ' : '' }}{{ namesFor(row) }}</span></button>
              </td>
              <td class="py-1.5 pr-3 text-right font-mono text-green-400">{{ formatPercent(row.median_irr * 100, 2) }}</td>
              <td class="py-1.5 pr-3 text-right font-mono text-slate-300">{{ formatPercent(row.mean_irr * 100, 2) }}</td>
              <td class="py-1.5 pr-3 text-right font-mono" :class="row.worst_irr < 0 ? 'text-red-400' : 'text-slate-400'">
                {{ formatPercent(row.p10_irr * 100, 2) }} / {{ formatPercent(row.worst_irr * 100, 2) }}
              </td>
              <td class="py-1.5 pr-3 text-right text-slate-400">{{ formatPercent(row.pct_positive, 1) }}</td>
              <td class="py-1.5 pr-3 text-right text-slate-400">{{ formatPercent(row.early_recall_pct, 1) }}</td>
              <td class="py-1.5 pr-3 text-right text-slate-500">{{ formatInt(row.n_windows) }}
                <div v-if="row.n_excluded" class="text-amber-600 text-[10px]">{{ row.n_excluded }} fenêtre(s) exclue(s)</div>
              </td>
              <td class="py-1.5 text-right whitespace-nowrap">
                <button class="text-[10px] px-2 py-1 bg-slate-700 hover:bg-slate-600 text-slate-200 rounded mr-1"
                        :disabled="rowState(row).pricing" :aria-label="`Prix indicatif de ${namesFor(row)}`" @click.stop="quotePrice(row)">
                  <span v-if="rowState(row).pricing">…</span>
                  <span v-else-if="rowState(row).price != null">{{ formatPercent(rowState(row).price * 100, 2) }}</span>
                  <span v-else>💰 Prix indicatif</span>
                </button>
                <button class="text-[10px] px-2 py-1 bg-blue-700 hover:bg-blue-600 text-white rounded"
                        :disabled="rowState(row).adopting || store.contractTermsLocked"
                        :title="store.contractTermsLocked ? 'Panier figé au booking' : ''"
                        @click.stop="adopt(row)">
                  {{ rowState(row).adopted ? '✓ Adopté' : '✓ Adopter ce panier' }}
                </button>
              </td>
            </tr>
            <tr v-if="rowState(row).error"><td colspan="8" class="text-xs text-red-600 py-2 whitespace-normal break-words" role="alert">{{ rowState(row).error }}</td></tr>
            <tr v-if="rowState(row).price != null && rowState(row).assumptions"><td colspan="8" class="text-xs text-slate-500 py-2 whitespace-normal">
              Prix indicatif au {{ formatDate(rowState(row).asof) }} ·
              <SensitiveValue>{{ rowState(row).assumptions.map(input => `${input.ticker} : vol. réalisée ${formatPercent(input.sigma * 100, 2)}, dividende historique ${formatPercent(input.q * 100, 2)}`).join(' ; ') }}</SensitiveValue>
            </td></tr>
            </template>
          </tbody>
        </table>
        <p class="text-xs text-slate-500 mt-3 whitespace-normal">Sélectionnez une ligne pour afficher son backtest détaillé. Le prix indicatif utilise les hypothèses de marché datées ; la volatilité chargée est une estimation réalisée.</p>
      </div>
      <section v-if="selectedRow" ref="detailPanel" class="space-y-3" aria-live="polite">
        <div class="card text-sm font-semibold">Détail du backtest — {{ namesFor(selectedRow) }}</div>
        <p v-if="detailLoading" role="status" class="text-xs">Chargement des fenêtres de la comparaison…</p>
        <p v-else-if="detailError" role="alert" class="card text-xs text-red-600">{{ detailError }}</p>
        <BacktestResults v-else-if="selectedDetail" :result="selectedDetail" />
      </section>
    </template>
  </div>
</template>

<script setup>
import { reactive, ref, computed, watch, nextTick, onMounted, onUnmounted } from 'vue'
import { usePricingStore } from '../stores/pricing.js'
import { apiFetch, apiErrorMessage } from '../utils/api.js'
import { fractionToPercentExact } from '../utils/underlyingDefaults.js'
import { recordMarketReference, marketProvenanceFields } from '../utils/marketProvenance.js'
import { underlyingGroups, ensureUnderlyings, catalogInstrument } from '../data/commonUnderlyings.js'
import { formatPercent, formatInt, formatDate } from '../utils/format.js'
import { useBacktestHistory } from '../composables/useBacktestHistory.js'
import BacktestHistoryDetails from './BacktestHistoryDetails.vue'
import BacktestResults from './BacktestResults.vue'
import HelpTip from './HelpTip.vue'
import SensitiveValue from './SensitiveValue.vue'

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
const form = ref({
  shortlist_n: 8,
  start_date: '',
  end_date: today,
  freq: 21,
  invest_pct: 100,
  rf_rate: 2.0,
  history_mode: 'following',
  max_delay_days: 10,
})
const history = useBacktestHistory({
  get underlyings() { return pool.value.filter(candidate => candidate.ticker?.trim()) },
  get backtest() { return store.comparator },
}, form)

function launch() {
  const candidates = pool.value
    .map(c => ({ ticker: c.ticker?.trim().toUpperCase() || '', name: labelFor(c.ticker?.trim().toUpperCase() || '') }))
    .filter(c => c.ticker)
  const context = JSON.stringify([pool.value, form.value, basketSize.value])
  store.runBacktestCompare(candidates, { ...form.value, start_date: history.manualStart.value ? form.value.start_date : null, basket_size: basketSize.value },
    () => context === JSON.stringify([pool.value, form.value, basketSize.value]))
}

function rowKey(row) {
  return row.tickers.join('|')
}
function namesFor(row) { return (row.names?.length === row.tickers.length ? row.names : row.tickers.map(labelFor)).join(' / ') }

const selectedRow = ref(null), selectedDetail = ref(null), detailLoading = ref(false), detailError = ref(''), detailPanel = ref(null)
const detailCache = new Map()
let detailSequence = 0, detailController
watch(() => store.comparator, () => {
  detailSequence++; detailController?.abort(); detailCache.clear()
  selectedRow.value = null; selectedDetail.value = null; detailLoading.value = false; detailError.value = ''
  for (const key of Object.keys(rowStates)) delete rowStates[key]
})
onUnmounted(() => { detailSequence++; detailController?.abort() })
async function selectResult(row) {
  const comparison = store.comparator, sequence = ++detailSequence
  detailController?.abort(); detailController = new AbortController()
  selectedRow.value = row; selectedDetail.value = null; detailError.value = ''; detailLoading.value = false
  const context = comparison?.comparison_context
  if (!context) { detailError.value = 'Relancez la comparaison pour disposer de son contexte de replay.'; return }
  const cached = detailCache.get(rowKey(row))
  if (cached) { selectedDetail.value = cached; return }
  detailLoading.value = true
  await nextTick()
  detailPanel.value?.scrollIntoView?.({ behavior: 'smooth', block: 'start' })
  try {
    const response = await apiFetch('/api/backtest/compare/detail', { method: 'POST',
      headers: { 'Content-Type': 'application/json' }, signal: detailController.signal,
      body: JSON.stringify({ comparison: context.request, tickers: row.tickers, history_hash: context.history_hash }) })
    const data = await response.json()
    if (sequence !== detailSequence || comparison !== store.comparator) return
    if (!response.ok) throw new Error(apiErrorMessage(data))
    detailCache.set(rowKey(row), data); selectedDetail.value = data
  } catch (failure) {
    if (sequence === detailSequence && comparison === store.comparator && failure.name !== 'AbortError') detailError.value = failure.message
  } finally { if (sequence === detailSequence) detailLoading.value = false }
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
  const comparison = store.comparator
  let isCurrent = () => comparison === store.comparator
  if (!(await store.ensureScriptValidated())) {
    st.error = 'Le script ne valide pas : corrigez-le dans l’onglet Script.'
    return
  }
  st.pricing = true; st.error = ''; st.price = null; st.assumptions = null
  try {
    const body = store.pricingBody()
    const signature = JSON.stringify(body)
    isCurrent = () => comparison === store.comparator && signature === JSON.stringify(store.pricingBody())
    const asof = store.globalParams.valuation_date || today
    const res = await apiFetch(`/api/finance/hist_vol?tickers=${encodeURIComponent(row.tickers.join(','))}&period=1y&asof=${encodeURIComponent(asof)}&session_aware=true`)
    const vol = await res.json()
    if (!isCurrent()) return
    if (!res.ok) throw new Error(apiErrorMessage(vol))
    if (vol.error) throw new Error(vol.error)

    const underlyings = row.tickers.map(tk => {
      const sigma = vol.vols?.[tk], q = vol.dividend_profiles?.[tk]?.ok === false ? null : vol.div_yields?.[tk]
      if (sigma == null || !Number.isFinite(sigma) || q == null || !Number.isFinite(q))
        throw new Error(`${tk} : volatilité ou dividende inconnu ; hypothèse explicite requise dans le Pricer.`)
      const existing = body.underlyings.find(underlying => underlying.ticker?.trim().toUpperCase() === tk)
      const ccy = catalogInstrument(tk)?.ccy || existing?.ccy
      if (!ccy) throw new Error(`${tk} : devise inconnue ; adoptez le panier pour la renseigner dans le Pricer.`)
      if ((!existing && body.model !== 'constant') || (!existing && (ccy !== body.settlement_ccy || body.sigma_r > 0)))
        throw new Error(`${tk} : adoptez le panier pour qualifier les paramètres du modèle ou du risque de change propres à ce titre.`)
      const editable = {ticker:tk, sigma:fractionToPercentExact(sigma), q:fractionToPercentExact(q)}
      recordMarketReference(editable, vol, tk)
      return {...existing, name:labelFor(tk), ticker:tk, ccy, sigma, q, ...marketProvenanceFields(editable)}
    })
    const correlation = row.tickers.map((a, i) => row.tickers.map((b, j) => i === j ? 1 : vol.corr?.[a]?.[b]))
    if (!correlation.every(line => line.every(Number.isFinite))) throw new Error('Corrélations de marché datées indisponibles pour ce panier.')

    const priceRes = await apiFetch('/api/price', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        ...body,
        underlyings,
        corr_matrix: correlation,
        N: 8000,
      }),
    })
    const data = await priceRes.json()
    if (!isCurrent()) return
    if (!priceRes.ok) throw new Error(apiErrorMessage(data))
    if (!Number.isFinite(data.price)) throw new Error('Réponse de prix invalide.')
    st.price = data.price
    st.asof = vol.requested_asof || asof
    st.assumptions = underlyings.map(({ ticker, sigma, q }) => ({ ticker, sigma, q }))
  } catch (e) {
    if (isCurrent()) st.error = e.message || 'Erreur de pricing'
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
