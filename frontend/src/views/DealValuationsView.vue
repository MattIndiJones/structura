<template>
  <div class="valuation-page">
    <main class="valuation-shell">
      <header class="valuation-header">
        <div class="valuation-header__identity">
          <BackLink :fallback="{ path: '/booking', query: { deal: dealId } }" />
          <div>
            <div class="valuation-eyebrow">Life Cycle · Historique des MtM</div>
            <h1><DealReferenceLink v-if="deal" :deal-id="deal.id"
                                   :reference="deal.reference" />
              <span v-else>{{ `Deal #${dealId}` }}</span></h1>
            <p v-if="deal">
              {{ deal.product_type || 'Produit structuré' }} · {{ deal.contrepartie || 'Contrepartie non renseignée' }}
            </p>
          </div>
        </div>
        <div class="valuation-header__actions">
          <RouterLink :to="{ path: '/booking', query: { deal: dealId } }" class="btn-secondary text-xs">
            Revenir au deal
          </RouterLink>
          <RouterLink :to="{ path: '/pricer', query: { dealId, tab: 'script' } }" class="btn-primary text-xs">
            Ouvrir le script
          </RouterLink>
        </div>
      </header>

      <LoadingSpinner v-if="loading" class="py-16" />

      <div v-else-if="error" class="valuation-error" role="alert">
        <strong>Historique indisponible</strong>
        <span>{{ error }}</span>
      </div>

      <template v-else>
        <section v-if="deal" class="deal-strip">
          <div><span>Nominal</span><strong>{{ formatInt(deal.nominal) }} {{ deal.devise }}</strong></div>
          <div><span>Prix traité</span><strong>{{ formatPercent(deal.price_traded) }}</strong></div>
          <div><span>Trade</span><strong>{{ formatDate(deal.trade_date) }}</strong></div>
          <div><span>Strike</span><strong>{{ formatDate(deal.strike_date) }}</strong></div>
          <div><span>Maturité</span><strong>{{ formatDate(deal.maturity_date) }}</strong></div>
          <div><span>Statut</span><strong>{{ statusLabel(deal.status) }}</strong></div>
        </section>

        <section v-if="runs.length" class="valuation-kpis">
          <article>
            <span>Dernier MtM</span>
            <strong><SensitiveValue>{{ formatFractionAsPercent(mtmValue(runs[0])) }}</SensitiveValue></strong>
            <small>valorisation au {{ formatDate(valuationDate(runs[0])) }}</small>
          </article>
          <article>
            <span>Mouvement</span>
            <strong :class="movementTone(movementAt(0))">
              {{ formatMovement(movementAt(0)) }}
            </strong>
            <small>par rapport au calcul précédent</small>
          </article>
          <article>
            <span>Calculs conservés</span>
            <strong>{{ runs.length }}</strong>
            <small>preuves immuables</small>
          </article>
          <article>
            <span>Dernier calcul</span>
            <strong class="valuation-kpis__date">{{ formatDateTime(runs[0].created_at) }}</strong>
            <small>{{ basisLabel(runs[0]) }}</small>
          </article>
        </section>

        <PriceComparisonPanel v-if="comparisonOpen && selectedRuns.length >= 2" id="comparison-workspace"
          :items="dealComparisonItems" :groups="comparisonGroups" :warnings="comparisonWarningsList"
          :reference-price="deal?.price_traded" price-label="MtM"
          title="Évolution du MtM entre les dates sélectionnées"
          @close="comparisonOpen = false" />

        <section class="history-card">
          <header class="history-card__header">
            <div>
              <h2>Calculs de MtM enregistrés</h2>
              <p>Chaque ligne correspond aux données et hypothèses réellement utilisées par le moteur.</p>
            </div>
            <div class="history-filters">
              <label>
                <span>Base</span>
                <select v-model="basisFilter" class="select">
                  <option value="">Toutes</option>
                  <option value="realized">Marché actualisé</option>
                  <option value="booking">Paramètres du booking</option>
                </select>
              </label>
              <label>
                <span>Du</span>
                <input v-model="dateFrom" type="date" class="input" />
              </label>
              <label>
                <span>Au</span>
                <input v-model="dateTo" type="date" class="input" />
              </label>
            </div>
          </header>

          <div v-if="!runs.length" class="history-empty">
            <strong>Aucun MtM enregistré</strong>
            <span>Le premier calcul lancé depuis la page Booking apparaîtra ici.</span>
            <RouterLink :to="{ path: '/booking', query: { deal: dealId } }" class="btn-primary text-xs">
              Revenir au deal
            </RouterLink>
          </div>

          <div v-else-if="!filteredRuns.length" class="history-empty">
            <strong>Aucun calcul ne correspond aux filtres</strong>
            <button class="btn-secondary text-xs" @click="resetFilters">Réinitialiser</button>
          </div>

          <div v-else class="history-table-wrap">
            <table class="history-table">
              <thead>
                <tr>
                  <th class="history-select-column" aria-label="Sélectionner"></th>
                  <th>Date de calcul</th>
                  <th>Date de valorisation</th>
                  <th class="is-number">MtM</th>
                  <th class="is-number">Mouvement</th>
                  <th>Base</th>
                  <th>Modèle</th>
                  <th>Source</th>
                  <th aria-label="Détail"></th>
                </tr>
              </thead>
              <tbody>
                <template v-for="run in filteredRuns" :key="run.id">
                  <tr class="history-row" :class="{ 'history-row--open': expandedRunId === run.id }"
                    @click="toggleRun(run.id)">
                    <td class="history-select-column" @click.stop>
                      <input type="checkbox" class="history-checkbox"
                        :checked="isSelected(run.id)"
                        :aria-label="`Sélectionner le MtM du ${formatDate(valuationDate(run))}`"
                        @change="toggleSelection(run.id)" />
                    </td>
                    <td class="is-mono">{{ formatDateTime(run.created_at) }}</td>
                    <td class="is-mono">{{ formatDate(valuationDate(run)) }}</td>
                    <td class="is-number history-mtm">
                      <SensitiveValue>{{ formatFractionAsPercent(mtmValue(run)) }}</SensitiveValue>
                    </td>
                    <td class="is-number" :class="movementTone(movementFor(run))">
                      {{ formatMovement(movementFor(run)) }}
                    </td>
                    <td><span class="history-badge">{{ basisLabel(run) }}</span></td>
                    <td>{{ modelLabel(run) }}</td>
                    <td>{{ providerLabel(run) }}</td>
                    <td class="history-chevron">{{ expandedRunId === run.id ? '▾' : '▸' }}</td>
                  </tr>
                  <tr v-if="expandedRunId === run.id" class="history-detail-row">
                    <td :colspan="9">
                      <div class="history-detail">
                        <section>
                          <h3>Marché utilisé</h3>
                          <div class="market-grid">
                            <article v-for="underlying in underlyingRows(run)" :key="underlying.name">
                              <strong>{{ underlying.name }}</strong>
                              <dl>
                                <div><dt>Cours</dt><dd>{{ formatNumber(underlying.spot, 4) }}</dd></div>
                                <div><dt>% du strike</dt><dd>{{ formatFractionAsPercent(underlying.normalizedSpot) }}</dd></div>
                                <div><dt>Volatilité</dt><dd>{{ formatPercent(underlying.sigma) }}</dd></div>
                                <div><dt>Dividende</dt><dd>{{ formatPercent(underlying.q) }}</dd></div>
                              </dl>
                            </article>
                          </div>
                        </section>

                        <section>
                          <h3>Hypothèses du run</h3>
                          <dl class="assumption-grid">
                            <div><dt>Modèle</dt><dd>{{ modelLabel(run) }}</dd></div>
                            <div><dt>Taux</dt><dd>{{ formatPercent(marketUsed(run).r, 4) }}</dd></div>
                            <div><dt>Funding</dt><dd>{{ fundingLabel(run) }}</dd></div>
                            <div><dt>Chemins</dt><dd>{{ formatInt(run.n_paths) }}</dd></div>
                            <div><dt>Observations passées</dt><dd>{{ run.result?.obs_passees ?? '—' }}</dd></div>
                            <div><dt>Vie restante</dt><dd>{{ formatNumber(run.result?.T_remaining, 2) }} an(s)</dd></div>
                          </dl>
                          <div v-if="correlationRows(run).length" class="correlation-list">
                            <span v-for="pair in correlationRows(run)" :key="pair.label">
                              {{ pair.label }} · {{ formatPercent(pair.value * 100, 1) }}
                            </span>
                          </div>
                        </section>

                        <section class="audit-section">
                          <h3>Traçabilité</h3>
                          <dl class="audit-grid">
                            <div><dt>Run</dt><dd>VR-{{ run.id }}</dd></div>
                            <div><dt>Contrat</dt><dd>v{{ run.contract_version }}</dd></div>
                            <div><dt>Moteur</dt><dd :title="run.engine_version">{{ shortValue(run.engine_version) }}</dd></div>
                            <div><dt>Empreinte</dt><dd :title="run.context_hash">{{ shortValue(run.context_hash) }}</dd></div>
                          </dl>
                        </section>
                      </div>
                    </td>
                  </tr>
                </template>
              </tbody>
            </table>
          </div>
        </section>

        <div v-if="selectedRuns.length" class="comparison-dock">
          <div class="comparison-dock__selection">
            <strong>{{ selectedRuns.length }} sélectionné{{ selectedRuns.length > 1 ? 's' : '' }}</strong>
            <div class="comparison-dock__chips">
              <button v-for="run in selectedRuns" :key="run.id" @click="toggleSelection(run.id)"
                :title="`Retirer le run VR-${run.id}`">
                {{ formatDate(valuationDate(run)) }} · {{ formatFractionAsPercent(mtmValue(run)) }} ×
              </button>
            </div>
          </div>
          <div class="comparison-dock__actions">
            <button class="btn-ghost text-xs" @click="clearSelection">Effacer</button>
            <button class="btn-primary text-xs" :disabled="selectedRuns.length < 2" @click="showComparison">
              Comparer {{ selectedRuns.length >= 2 ? `(${selectedRuns.length})` : '' }}
            </button>
            <RouterLink v-if="selectedRuns.length === 2" class="btn-secondary text-xs"
              :to="{ path: '/valo-explain', query: { deal: dealId, run: selectedRuns[0].id, run2: selectedRuns[1].id, auto: '1' } }">
              Rédiger l’explication
            </RouterLink>
          </div>
        </div>
      </template>
    </main>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import BackLink from '../components/ui/BackLink.vue'
import LoadingSpinner from '../components/ui/LoadingSpinner.vue'
import SensitiveValue from '../components/SensitiveValue.vue'
import PriceComparisonPanel from '../components/PriceComparisonPanel.vue'
import DealReferenceLink from '../components/DealReferenceLink.vue'
import { apiFetch } from '../utils/api.js'
import {
  formatDate, formatDateTime, formatFractionAsPercent, formatInt,
  formatNumber, formatPercent,
} from '../utils/format.js'
import {
  mtmValue, sortValuationRuns, valuationDate,
} from '../utils/valuationComparison.js'

const route = useRoute()
const router = useRouter()
const dealId = Number(route.params.dealId)
const deal = ref(null)
const runs = ref([])
const loading = ref(true)
const error = ref('')
const expandedRunId = ref(null)
const basisFilter = ref('')
const dateFrom = ref('')
const dateTo = ref('')
const selectedRunIds = ref(
  String(route.query.compare || '').split(',').map(Number).filter(Number.isInteger),
)
const comparisonOpen = ref(selectedRunIds.value.length >= 2)

function basisCode(run) {
  return run?.diagnostics?.request?.recalibrate === 'none' ? 'booking' : 'realized'
}

function basisLabel(run) {
  return basisCode(run) === 'booking' ? 'Paramètres booking' : 'Marché actualisé'
}

function basisShortLabel(run) {
  return basisCode(run) === 'booking' ? 'Booking' : 'Marché'
}

function marketUsed(run) {
  return run?.result?.market_used || run?.market_data?.market_used || {}
}

function modelLabel(run) {
  const model = String(marketUsed(run).model || '').toLowerCase()
  return {
    constant: 'GBM', gbm: 'GBM', heston: 'Heston', sabr: 'SABR',
    local_vol: 'Vol locale', localvol: 'Vol locale', lsv: 'LSV', deterministic_cashflow: 'Flux déterministe',
  }[model] || model || '—'
}

function providerLabel(run) {
  const provider = marketUsed(run).data?.provider
  if (provider === 'YAHOO_FINANCE' || provider === 'YAHOO') return 'Yahoo Finance'
  return provider || '—'
}

function movementAt(index) {
  if (index < 0 || index >= runs.value.length - 1) return null
  const current = mtmValue(runs.value[index])
  const previous = mtmValue(runs.value[index + 1])
  if (!Number.isFinite(current) || !Number.isFinite(previous)) return null
  return (current - previous) * 100
}

const selectedRuns = computed(() => sortValuationRuns(
  runs.value.filter(run => selectedRunIds.value.includes(run.id)),
))

const comparisonWarningsList = computed(() => {
  const bases = new Set(selectedRuns.value.map(basisCode))
  return bases.size > 1
    ? ['Les calculs mélangent marché actualisé et paramètres du booking.']
    : []
})

const dealComparisonItems = computed(() => selectedRuns.value.map(run => ({
  id: run.id,
  calculatedAt: run.created_at,
  valuationDate: valuationDate(run),
  price: mtmValue(run) * 100,
  basis: basisShortLabel(run),
  version: run.contract_version,
})))

function movementFor(run) {
  return movementAt(runs.value.findIndex(item => item.id === run.id))
}

function movementTone(value) {
  if (value == null || value === 0) return 'tone-neutral'
  return value > 0 ? 'tone-positive' : 'tone-negative'
}

function formatMovement(value) {
  if (value == null) return '—'
  return `${value > 0 ? '+' : ''}${formatNumber(value, 2)} pts`
}

function underlyingRows(run) {
  const used = marketUsed(run)
  const observations = run.market_data?.observations || []
  const names = new Set([
    ...Object.keys(used.sigma || {}),
    ...Object.keys(used.q || {}),
    ...observations.map(item => item.name),
  ])
  return [...names].map(name => {
    const observation = observations.find(item => item.name === name) || {}
    return {
      name,
      spot: observation.effective_spot,
      normalizedSpot: observation.normalized_spot,
      sigma: used.sigma?.[name],
      q: used.q?.[name],
    }
  })
}

function correlationRows(run) {
  const names = underlyingRows(run).map(item => item.name)
  const corr = marketUsed(run).corr || []
  const rows = []
  for (let i = 0; i < corr.length; i++) {
    for (let j = i + 1; j < corr.length; j++) {
      rows.push({ label: `${names[i] || i + 1} / ${names[j] || j + 1}`, value: corr[i][j] })
    }
  }
  return rows
}

function valueRow(key, label, unit, decimals, getter) {
  return {
    key, label, unit, decimals,
    values: selectedRuns.value.map(getter),
  }
}

const comparisonGroups = computed(() => {
  const priceRows = [
    valueRow('mtm', 'MtM', '%', 2, run => mtmValue(run) * 100),
    valueRow('ic-low', 'Intervalle 95% · borne basse', '%', 2, run => run.result?.ic95?.[0] * 100),
    valueRow('ic-high', 'Intervalle 95% · borne haute', '%', 2, run => run.result?.ic95?.[1] * 100),
    valueRow('remaining', 'Vie restante', 'an', 2, run => run.result?.T_remaining),
    valueRow('observations', 'Observations passées', '', 0, run => run.result?.obs_passees),
  ]

  const underlyingNames = new Set(selectedRuns.value.flatMap(run =>
    underlyingRows(run).map(item => item.name)))
  const underlyingRowsList = [...underlyingNames].flatMap(name => [
    valueRow(`spot-${name}`, `${name} · cours`, '', 4,
      run => underlyingRows(run).find(item => item.name === name)?.spot),
    valueRow(`performance-${name}`, `${name} · niveau / strike`, '%', 2,
      run => underlyingRows(run).find(item => item.name === name)?.normalizedSpot * 100),
    valueRow(`sigma-${name}`, `${name} · volatilité`, '%', 2,
      run => underlyingRows(run).find(item => item.name === name)?.sigma),
    valueRow(`q-${name}`, `${name} · dividende`, '%', 2,
      run => underlyingRows(run).find(item => item.name === name)?.q),
  ])

  const marketRows = [
    valueRow('rate', 'Taux', '%', 4, run => marketUsed(run).r),
    valueRow('funding', 'Funding', '%', 4, run => marketUsed(run).funding_spread),
  ]
  const correlationLabels = new Set(selectedRuns.value.flatMap(run =>
    correlationRows(run).map(item => item.label)))
  for (const label of correlationLabels) {
    marketRows.push(valueRow(`corr-${label}`, `Corrélation · ${label}`, '%', 1,
      run => correlationRows(run).find(item => item.label === label)?.value * 100))
  }

  return [
    { label: 'Prix et cycle de vie', rows: priceRows },
    { label: 'Sous-jacents', rows: underlyingRowsList },
    { label: 'Marché global', rows: marketRows },
  ].map(group => ({
    ...group,
    rows: group.rows.filter(row => row.values.some(Number.isFinite)),
  })).filter(group => group.rows.length)
})

function fundingLabel(run) {
  const used = marketUsed(run)
  if (used.funding_curve?.length) return `Courbe · ${used.funding_curve.length} piliers`
  return formatPercent(used.funding_spread, 4)
}

function shortValue(value) {
  if (!value) return '—'
  return value.length > 14 ? `${value.slice(0, 12)}…` : value
}

function statusLabel(status) {
  return {
    actif: 'En cours', en_reglement: 'En règlement', 'callé': 'Rappelé',
    'échu': 'Échu', 'résilié': 'Résilié',
  }[status] || status || '—'
}

const filteredRuns = computed(() => runs.value.filter(run => {
  const valueDate = valuationDate(run)
  if (basisFilter.value && basisCode(run) !== basisFilter.value) return false
  if (dateFrom.value && valueDate < dateFrom.value) return false
  if (dateTo.value && valueDate > dateTo.value) return false
  return true
}))

function isSelected(id) {
  return selectedRunIds.value.includes(id)
}

function toggleSelection(id) {
  selectedRunIds.value = isSelected(id)
    ? selectedRunIds.value.filter(runId => runId !== id)
    : [...selectedRunIds.value, id]
  if (selectedRunIds.value.length < 2) comparisonOpen.value = false
}

function clearSelection() {
  selectedRunIds.value = []
  comparisonOpen.value = false
}

async function showComparison() {
  if (selectedRuns.value.length < 2) return
  comparisonOpen.value = true
  await nextTick()
  document.getElementById('comparison-workspace')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

watch(selectedRunIds, ids => {
  const query = { ...route.query }
  if (ids.length) query.compare = ids.join(',')
  else delete query.compare
  router.replace({ query })
}, { deep: true })

function resetFilters() {
  basisFilter.value = ''
  dateFrom.value = ''
  dateTo.value = ''
}

function toggleRun(id) {
  expandedRunId.value = expandedRunId.value === id ? null : id
}

async function load() {
  if (!Number.isInteger(dealId) || dealId <= 0) {
    error.value = 'Identifiant de deal invalide.'
    loading.value = false
    return
  }
  try {
    const [dealResponse, runsResponse] = await Promise.all([
      apiFetch(`/api/deals/${dealId}`),
      apiFetch(`/api/deals/${dealId}/valuation-runs?run_type=MTM&include_payload=true`),
    ])
    if (!dealResponse.ok) throw new Error((await dealResponse.json()).detail || 'Deal introuvable')
    if (!runsResponse.ok) throw new Error((await runsResponse.json()).detail || 'Historique indisponible')
    deal.value = await dealResponse.json()
    const summaries = await runsResponse.json()
    // Compatibilité avec un backend déjà lancé avant l'ajout de
    // include_payload : son endpoint ignore le paramètre et renvoie les mêmes
    // résumés légers. La page explicite d'historique peut compléter ces lignes
    // en parallèle ; après redémarrage, aucun appel supplémentaire n'est fait.
    runs.value = summaries.some(run => !run.result)
      ? await Promise.all(summaries.map(async run => {
          const response = await apiFetch(`/api/deals/valuation-runs/${run.id}`)
          return response.ok ? response.json() : run
        }))
      : summaries
    const availableIds = new Set(runs.value.map(run => run.id))
    selectedRunIds.value = selectedRunIds.value.filter(id => availableIds.has(id))
    comparisonOpen.value = selectedRunIds.value.length >= 2
  } catch (exception) {
    error.value = typeof exception.message === 'string' ? exception.message : 'Chargement impossible.'
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.valuation-page { flex: 1; overflow-y: auto; background: var(--bg); color: var(--text); }
.valuation-shell { width: min(1500px, 100%); margin: 0 auto; padding: 1.5rem; display: flex; flex-direction: column; gap: 1rem; }
.valuation-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 1rem; }
.valuation-header__identity, .valuation-header__actions { display: flex; align-items: center; gap: .75rem; }
.valuation-header__identity h1 { margin: .15rem 0; font-size: 1.4rem; font-weight: 750; }
.valuation-header__identity p { color: var(--muted); font-size: .75rem; }
.valuation-eyebrow { color: var(--accent); font-size: .65rem; font-weight: 700; letter-spacing: .1em; text-transform: uppercase; }
.deal-strip, .valuation-kpis, .history-card { border: 1px solid var(--border); border-radius: 14px; background: var(--surface); box-shadow: 0 2px 9px rgba(26,24,20,.05); }
.deal-strip { display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); padding: .8rem 1rem; }
.deal-strip > div { padding: .25rem .75rem; border-right: 1px solid var(--border); }
.deal-strip > div:last-child { border-right: 0; }
.deal-strip span, .valuation-kpis span { display: block; color: var(--muted); font-size: .62rem; letter-spacing: .05em; text-transform: uppercase; }
.deal-strip strong { display: block; margin-top: .2rem; font-size: .75rem; }
.valuation-kpis { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); overflow: hidden; }
.valuation-kpis article { padding: .9rem 1rem; border-right: 1px solid var(--border); }
.valuation-kpis article:last-child { border-right: 0; }
.valuation-kpis strong { display: block; margin: .25rem 0 .15rem; color: var(--accent); font-family: 'JetBrains Mono', Consolas, monospace; font-size: 1.3rem; }
.valuation-kpis strong.valuation-kpis__date { color: var(--text); font-size: .88rem; }
.valuation-kpis small { color: var(--muted); font-size: .68rem; }
.history-card { overflow: hidden; }
.history-card__header { display: flex; align-items: flex-end; justify-content: space-between; gap: 1rem; padding: 1rem; border-bottom: 1px solid var(--border); }
.history-card__header h2 { font-size: .9rem; font-weight: 750; }
.history-card__header p { margin-top: .2rem; color: var(--muted); font-size: .7rem; }
.history-filters { display: flex; align-items: flex-end; gap: .5rem; }
.history-filters label { display: flex; flex-direction: column; gap: .2rem; color: var(--muted); font-size: .62rem; }
.history-filters .select, .history-filters .input { min-width: 8.5rem; padding: .4rem .5rem; font-size: .7rem; }
.history-table-wrap { overflow-x: auto; }
.history-table { width: 100%; border-collapse: collapse; font-size: .72rem; }
.history-table th { padding: .65rem .75rem; background: var(--surface2); color: var(--muted); font-size: .61rem; font-weight: 700; letter-spacing: .04em; text-align: left; text-transform: uppercase; white-space: nowrap; }
.history-table td { padding: .72rem .75rem; border-top: 1px solid var(--border); vertical-align: middle; }
.history-row { cursor: pointer; transition: background 120ms ease; }
.history-row:hover, .history-row--open { background: color-mix(in srgb, var(--accent) 5%, var(--surface)); }
.is-number { text-align: right !important; font-variant-numeric: tabular-nums; white-space: nowrap; }
.is-mono, .history-mtm { font-family: 'JetBrains Mono', Consolas, monospace; }
.history-mtm { color: var(--accent); font-size: .82rem; font-weight: 750; }
.history-badge { display: inline-flex; border: 1px solid var(--border); border-radius: 999px; padding: .2rem .45rem; background: var(--surface2); white-space: nowrap; }
.history-chevron { width: 2rem; color: var(--muted); text-align: center; }
.history-select-column { width: 2.6rem; text-align: center !important; }
.history-checkbox { width: 1rem; height: 1rem; accent-color: var(--accent); cursor: pointer; }
.history-detail-row > td { padding: 0; background: var(--surface2); }
.history-detail { display: grid; grid-template-columns: 1.3fr 1fr .65fr; gap: 1rem; padding: 1rem 1.25rem 1.2rem; border-top: 2px solid color-mix(in srgb, var(--accent) 25%, var(--border)); }
.history-detail h3 { margin-bottom: .55rem; color: var(--text); font-size: .66rem; font-weight: 750; letter-spacing: .06em; text-transform: uppercase; }
.market-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(12rem, 1fr)); gap: .5rem; }
.market-grid article { border: 1px solid var(--border); border-radius: 9px; background: var(--surface); padding: .65rem; }
.market-grid article > strong { font-size: .75rem; }
.market-grid dl, .assumption-grid, .audit-grid { margin-top: .45rem; display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: .35rem .75rem; }
.market-grid dl div, .assumption-grid div, .audit-grid div { min-width: 0; }
.history-detail dt { color: var(--muted); font-size: .6rem; }
.history-detail dd { margin-top: .1rem; overflow: hidden; color: var(--text); font-family: 'JetBrains Mono', Consolas, monospace; font-size: .69rem; text-overflow: ellipsis; white-space: nowrap; }
.correlation-list { display: flex; flex-wrap: wrap; gap: .3rem; margin-top: .65rem; }
.correlation-list span { border-radius: 5px; background: var(--surface); padding: .25rem .4rem; color: var(--muted); font-size: .62rem; }
.audit-section { border-left: 1px solid var(--border); padding-left: 1rem; }
.audit-grid { grid-template-columns: 1fr; }
.history-empty, .valuation-error { min-height: 14rem; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: .5rem; padding: 2rem; color: var(--muted); text-align: center; }
.history-empty strong, .valuation-error strong { color: var(--text); font-size: .85rem; }
.history-empty span, .valuation-error span { font-size: .72rem; }
.valuation-error { min-height: 10rem; border: 1px solid #efb4ad; border-radius: 12px; background: #fff3f1; color: #9f3328; }
.tone-positive { color: var(--positive) !important; }
.tone-negative { color: var(--negative) !important; }
.tone-neutral { color: var(--muted) !important; }

.comparison-dock { position: sticky; z-index: 20; bottom: 1rem; display: flex; align-items: center; justify-content: space-between; gap: 1rem; margin: 0 auto; width: min(1050px, calc(100% - 2rem)); border: 1px solid #afc8e5; border-radius: 13px; background: rgba(255,255,255,.96); padding: .65rem .75rem; box-shadow: 0 18px 45px -20px rgba(20,54,92,.55); backdrop-filter: blur(10px); }
.comparison-dock__selection { display: flex; min-width: 0; align-items: center; gap: .65rem; }
.comparison-dock__selection > strong { flex: 0 0 auto; font-size: .72rem; }
.comparison-dock__chips { display: flex; min-width: 0; gap: .3rem; overflow-x: auto; }
.comparison-dock__chips button { flex: 0 0 auto; border: 1px solid var(--border); border-radius: 999px; background: var(--surface2); padding: .25rem .45rem; color: var(--muted); font-size: .62rem; }
.comparison-dock__chips button:hover { border-color: var(--accent); color: var(--accent); }
.comparison-dock__actions { display: flex; flex: 0 0 auto; align-items: center; gap: .4rem; }

@media (max-width: 1000px) {
  .deal-strip { grid-template-columns: repeat(3, minmax(0, 1fr)); }
  .deal-strip > div:nth-child(3) { border-right: 0; }
  .valuation-kpis { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .valuation-kpis article:nth-child(2) { border-right: 0; }
  .history-detail { grid-template-columns: 1fr; }
  .audit-section { border-left: 0; border-top: 1px solid var(--border); padding: .8rem 0 0; }
}

@media (max-width: 700px) {
  .valuation-shell { padding: .85rem; }
  .valuation-header, .history-card__header { align-items: stretch; flex-direction: column; }
  .valuation-header__actions, .history-filters { flex-wrap: wrap; }
  .deal-strip, .valuation-kpis { grid-template-columns: 1fr 1fr; }
  .comparison-dock { align-items: stretch; flex-direction: column; width: calc(100% - 1rem); }
  .comparison-dock__actions { justify-content: flex-end; }
  .deal-strip > div, .valuation-kpis article { border-right: 0; border-bottom: 1px solid var(--border); }
}
</style>
