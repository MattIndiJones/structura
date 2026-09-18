<template>
  <div class="flex-1 flex flex-col min-h-0">
    <main class="flex-1 p-6 max-w-7xl w-full mx-auto flex flex-col gap-4">
      <div class="page-header">
        <div>
          <h1 class="page-title">Générateur UAT</h1>
          <p class="page-subtitle">
            Crée des Products synthétiques puis les fait passer par les parcours réels du Pricer,
            des RFQ, du booking, des fixings, des valorisations et du risque.
          </p>
        </div>
        <div class="page-actions">
          <RouterLink to="/admin" class="btn-ghost btn-sm">← Administration</RouterLink>
          <button class="btn-secondary text-xs px-3 py-1.5" :disabled="loading" @click="loadAll">
            Actualiser
          </button>
        </div>
      </div>

      <AlertMessage v-if="error" kind="error">{{ error }}</AlertMessage>
      <AlertMessage v-if="notice" kind="success" dismissible @dismiss="notice = ''">{{ notice }}</AlertMessage>
      <AlertMessage kind="warning">
        Données de test uniquement : chaque objet porte le lot UAT qui l'a créé.
        La suppression cible ce rattachement explicite et ne touche jamais les données ordinaires.
      </AlertMessage>

      <LoadingSpinner v-if="loading" class="py-12" />
      <template v-else>
        <div class="grid grid-cols-1 xl:grid-cols-[minmax(0,1.7fr)_minmax(320px,0.8fr)] gap-4 items-start">
          <section class="card flex flex-col gap-5">
            <div>
              <h2 class="font-bold text-sm">1. Périmètre du lot</h2>
              <p class="text-xs mt-1" style="color: var(--subtle);">
                Le Product est créé au premier acte persistant, reste interne sauf conservation
                volontaire, puis garde la même identité dans tous les modules.
              </p>
            </div>

            <div class="grid grid-cols-1 md:grid-cols-3 gap-3">
              <label>
                <span class="label">Compte destinataire</span>
                <select v-model.number="form.target_user_id" class="select">
                  <option v-for="user in config.users" :key="user.id" :value="user.id">
                    {{ user.username }} · {{ roleLabel(user.role) }}
                  </option>
                </select>
              </label>
              <label>
                <span class="label">Chaîne testée</span>
                <select v-model="form.mode" class="select">
                  <option value="FULL_CHAIN">RFQ → Product interne → Pricer → Booking → Risk</option>
                  <option value="PRICER_RFQ_CHAIN">Pricer → Product interne → RFQ → Pricer → Booking → Risk</option>
                  <option value="SAVED_PRODUCT_RFQ_CHAIN">Pricer → Product conservé → RFQ → Pricer → Booking → Risk</option>
                  <option value="BOOKED_ONLY">Pricer → Product interne → Booking direct → Risk</option>
                  <option value="RFQ_ONLY">RFQ → Product interne (non traitée)</option>
                </select>
              </label>
              <label>
                <span class="label">Nombre</span>
                <input v-model.number="form.count" class="input" type="number" min="1" max="100" />
              </label>
            </div>

            <label>
              <span class="label">Libellé du lot</span>
              <input v-model="form.label" class="input" maxlength="120"
                     placeholder="Ex. Non-régression booking août" />
            </label>

            <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
              <fieldset class="rounded-xl p-3 border" style="border-color: var(--border);">
                <legend class="label px-1">Familles de produits</legend>
                <div class="grid grid-cols-1 sm:grid-cols-2 gap-2">
                  <label v-for="product in config.products" :key="product.key"
                         class="flex items-center gap-2 text-xs cursor-pointer">
                    <input v-model="form.product_types" type="checkbox" :value="product.key" />
                    <span>{{ product.label }}</span>
                  </label>
                </div>
              </fieldset>

              <fieldset class="rounded-xl p-3 border" style="border-color: var(--border);">
                <legend class="label px-1">Univers sous-jacents</legend>
                <div class="grid grid-cols-1 sm:grid-cols-2 gap-2 max-h-28 overflow-y-auto">
                  <label v-for="underlying in config.underlyings" :key="underlying.ticker"
                         class="flex items-center gap-2 text-xs cursor-pointer">
                    <input v-model="form.underlying_tickers" type="checkbox" :value="underlying.ticker" />
                    <span>{{ underlying.name }} <span class="font-mono text-[10px]" style="color: var(--subtle);">{{ underlying.ticker }}</span></span>
                  </label>
                </div>
              </fieldset>
            </div>

            <div class="grid grid-cols-2 md:grid-cols-4 gap-3">
              <label>
                <span class="label">Sous-jacents min.</span>
                <select v-model.number="form.min_underlyings" class="select">
                  <option v-for="n in Math.min(config.underlyings.length, 12)" :key="n" :value="n">{{ n }}</option>
                </select>
              </label>
              <label>
                <span class="label">Sous-jacents max.</span>
                <select v-model.number="form.max_underlyings" class="select">
                  <option v-for="n in Math.min(config.underlyings.length, 12)" :key="n" :value="n">{{ n }}</option>
                </select>
              </label>
              <label>
                <span class="label">Maturité min. (ans)</span>
                <input v-model.number="form.maturity_min_years" class="input" type="number" min="0.25" max="10" step="0.25" />
              </label>
              <label>
                <span class="label">Maturité max. (ans)</span>
                <input v-model.number="form.maturity_max_years" class="input" type="number" min="0.25" max="10" step="0.25" />
              </label>
            </div>

            <div class="grid grid-cols-1 md:grid-cols-5 gap-3">
              <label>
                <span class="label">Nominal min.</span>
                <input v-model.number="form.nominal_min" class="input" type="number" min="1" step="10000" />
              </label>
              <label>
                <span class="label">Nominal max.</span>
                <input v-model.number="form.nominal_max" class="input" type="number" min="1" step="10000" />
              </label>
              <label>
                <span class="label">Source des fixings</span>
                <div class="input flex items-center text-xs" style="color: var(--text);">
                  Fournisseur automatique
                </div>
              </label>
              <label>
                <span class="label">Profil historique / lifecycle</span>
                <select v-model="form.lifecycle_profile" class="select">
                  <option value="COMPLETE_MIX">Matrice complète (8 cas)</option>
                  <option v-for="profile in config.lifecycle_profiles" :key="profile.key" :value="profile.key">
                    {{ profile.label }}
                  </option>
                </select>
              </label>
              <fieldset>
                <legend class="label">Devises</legend>
                <div class="h-[38px] flex items-center gap-3">
                  <label v-for="ccy in ['EUR', 'USD', 'CHF']" :key="ccy" class="flex items-center gap-1.5 text-xs cursor-pointer">
                    <input v-model="form.currencies" type="checkbox" :value="ccy" /> {{ ccy }}
                  </label>
                </div>
              </fieldset>
            </div>

            <div v-if="form.mode !== 'BOOKED_ONLY'" class="rounded-xl p-3 border flex flex-col gap-3"
                 style="border-color: var(--border); background: var(--surface2);">
              <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
                <label>
                  <span class="label">Quotes par RFQ</span>
                  <select v-model.number="form.quotes_per_rfq" class="select">
                    <option v-for="n in 5" :key="n" :value="n">{{ n }}</option>
                  </select>
                </label>
                <label v-if="form.mode === 'RFQ_ONLY'">
                  <span class="label">Profil RFQ</span>
                  <select v-model="form.rfq_profile" class="select">
                    <option value="EXECUTABLE">Toutes exécutables</option>
                    <option value="CONTROL_MIX">Mix contrôles / blocages</option>
                  </select>
                </label>
              </div>
              <fieldset>
                <legend class="label">Fournisseurs sollicités</legend>
                <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
                  <label v-for="provider in config.providers" :key="provider.id"
                         class="flex items-center gap-2 text-xs cursor-pointer">
                    <input v-model="form.provider_ids" type="checkbox" :value="provider.id" />
                    <span>{{ provider.label }} <span style="color: var(--subtle);">→ {{ provider.counterparty }}</span></span>
                  </label>
                </div>
              </fieldset>
            </div>

            <div class="rounded-xl p-3 border flex flex-col gap-3"
                 style="border-color: var(--border); background: var(--surface2);">
              <div>
                <div class="label">Calculs conservés</div>
                <p class="text-[11px] mt-1" style="color: var(--subtle);">
                  Les calculs Product conservent chacun leur marché. Les MTM datés alimentent
                  l'historique du deal ; les Greeks rendent le deal exploitable dans Risk.
                </p>
              </div>
              <div class="grid grid-cols-1 md:grid-cols-3 gap-3">
                <label v-if="form.mode !== 'RFQ_ONLY'">
                  <span class="label">Pricings par Product</span>
                  <select v-model.number="form.product_calculations" class="select">
                    <option v-for="n in 5" :key="n" :value="n">{{ n }}</option>
                  </select>
                </label>
                <label v-if="form.mode !== 'RFQ_ONLY'">
                  <span class="label">Dates de MTM par deal</span>
                  <select v-model.number="form.mtm_history_count" class="select">
                    <option :value="0">Aucune</option>
                    <option v-for="n in 5" :key="n" :value="n">{{ n }}</option>
                  </select>
                </label>
                <label v-if="form.mode !== 'RFQ_ONLY'" class="flex items-center gap-2 pt-5 text-xs cursor-pointer">
                  <input v-model="form.compute_greeks" type="checkbox" />
                  <span>Calculer les Greeks pour Risk</span>
                </label>
              </div>
            </div>

            <div class="flex items-center justify-between gap-3 pt-1 border-t" style="border-color: var(--border);">
              <p class="text-[11px]" style="color: var(--subtle);">
                Une prévisualisation valide est obligatoire avant génération.
              </p>
              <div class="flex gap-2">
                <button class="btn-secondary text-xs px-3 py-2" :disabled="previewing || generating" @click="previewBatch">
                  {{ previewing ? 'Calcul…' : 'Prévisualiser' }}
                </button>
                <button class="btn-primary text-xs px-3 py-2" :disabled="!preview || generating" @click="generateBatch">
                  {{ generating ? 'Génération…' : 'Générer le lot UAT' }}
                </button>
              </div>
            </div>
          </section>

          <aside class="card flex flex-col gap-4 xl:sticky xl:top-4">
            <div>
              <h2 class="font-bold text-sm">2. Prévisualisation</h2>
              <p class="text-xs mt-1" style="color: var(--subtle);">
                Aucun enregistrement n'est créé à cette étape.
              </p>
            </div>
            <div v-if="!preview" class="rounded-xl p-6 text-xs text-center" style="background: var(--surface2); color: var(--subtle);">
              Configurez le lot puis lancez la prévisualisation.
            </div>
            <template v-else>
              <div class="grid grid-cols-2 sm:grid-cols-3 gap-2">
                <div class="stat-box"><div class="label">Products</div><div class="font-mono text-lg">{{ preview.product_count }}</div></div>
                <div class="stat-box"><div class="label">Pricings</div><div class="font-mono text-lg">{{ preview.calculation_count }}</div></div>
                <div class="stat-box"><div class="label">RFQ</div><div class="font-mono text-lg">{{ preview.rfq_count }}</div></div>
                <div class="stat-box"><div class="label">Deals</div><div class="font-mono text-lg">{{ preview.deal_count }}</div></div>
                <div v-if="preview.deal_count" class="stat-box"><div class="label">MTM max.</div><div class="font-mono text-lg">{{ preview.valuation_count_estimate }}</div></div>
                <div v-if="preview.deal_count" class="stat-box"><div class="label">Risk max.</div><div class="font-mono text-lg">{{ preview.risk_count_estimate }}</div></div>
              </div>
              <div v-if="Object.keys(preview.profile_counts || {}).length" class="flex flex-wrap gap-1.5">
                <span v-for="(count, profile) in preview.profile_counts" :key="profile" class="badge badge-muted">
                  {{ lifecycleLabel(profile) }} · {{ count }}
                </span>
              </div>
              <div v-if="preview.pricing_scenarios?.length > 1" class="rounded-xl p-3 text-[11px] border"
                   style="border-color: var(--border); background: var(--surface2);">
                <div class="label mb-1.5">Marchés des pricings conservés</div>
                <div v-for="scenario in preview.pricing_scenarios" :key="scenario.index" class="mt-1">
                  <span class="font-mono">P{{ scenario.index }}</span> · {{ scenario.label }}
                </div>
              </div>
              <template v-if="preview.warnings?.length">
                <AlertMessage v-for="warning in preview.warnings" :key="warning" kind="warning">{{ warning }}</AlertMessage>
              </template>
              <AlertMessage v-else-if="preview.warning" kind="warning">{{ preview.warning }}</AlertMessage>
              <div class="flex flex-col gap-2">
                <div v-for="sample in preview.samples" :key="sample.name" class="rounded-xl p-3 text-xs border"
                     style="border-color: var(--border);">
                  <div class="font-semibold">{{ sample.name }}</div>
                  <div class="mt-1 flex flex-wrap gap-x-2 gap-y-1" style="color: var(--subtle);">
                    <span class="font-medium" style="color: var(--text);">{{ sample.lifecycle_profile_label }}</span>
                    <span>{{ sample.underlyings.join(' / ') }}</span>
                    <span>{{ fmtMoney(sample.nominal, sample.currency) }}</span>
                    <span>{{ fixingLabel(sample.fixing_policy) }}</span>
                  </div>
                  <div class="mt-1 font-mono text-[10px]" style="color: var(--subtle);">
                    AO {{ sample.ao_date }} → trade {{ sample.trade_date }} → strike {{ sample.strike_date }} → maturité {{ sample.maturity_date }}
                  </div>
                  <div v-if="sample.rfq_scenario && sample.rfq_scenario !== 'EXECUTABLE'" class="mt-1 text-amber-600">
                    Contrôle : {{ scenarioLabel(sample.rfq_scenario) }}
                  </div>
                </div>
              </div>
              <p v-if="form.count > preview.samples.length" class="text-[11px] text-center" style="color: var(--subtle);">
                + {{ form.count - preview.samples.length }} objets selon la même configuration
              </p>
            </template>
          </aside>
        </div>

        <section class="card overflow-x-auto">
          <div class="flex items-center justify-between mb-3">
            <div>
              <h2 class="font-bold text-sm">3. Historique des lots</h2>
              <p class="text-xs mt-1" style="color: var(--subtle);">Les lots supprimés restent visibles pour l'audit.</p>
            </div>
          </div>
          <p v-if="batches.length === 0" class="text-xs py-6 text-center" style="color: var(--subtle);">Aucun lot UAT.</p>
          <table v-else class="w-full text-xs">
            <thead>
              <tr class="text-left border-b" style="color: var(--subtle); border-color: var(--border);">
                <th class="py-2 pr-3 font-medium">Lot</th>
                <th class="py-2 pr-3 font-medium">Compte</th>
                <th class="py-2 pr-3 font-medium">Mode</th>
                <th class="py-2 pr-3 font-medium">Objets</th>
                <th class="py-2 pr-3 font-medium">Statut</th>
                <th class="py-2 pr-3 font-medium">Créé le</th>
                <th class="py-2 font-medium"></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="batch in batches" :key="batch.id" class="border-b" style="border-color: var(--border);">
                <td class="py-2 pr-3">
                  <div class="font-semibold">{{ batch.label }}</div>
                  <div class="font-mono text-[10px]" style="color: var(--subtle);">{{ batch.batch_key }}</div>
                </td>
                <td class="py-2 pr-3">{{ batch.target_user }}</td>
                <td class="py-2 pr-3">{{ modeLabel(batch.mode) }}</td>
                <td class="py-2 pr-3 font-mono whitespace-nowrap">
                  {{ batch.product_count }} Product{{ batch.product_count === 1 ? '' : 's' }} ·
                  {{ batch.rfq_count }} RFQ · {{ dealCountLabel(batch.deal_count) }}
                  <div v-if="batch.valuation_count || batch.risk_count" class="text-[10px] mt-0.5" style="color: var(--subtle);">
                    {{ batch.valuation_count }} MTM · {{ batch.risk_count }} calcul{{ batch.risk_count === 1 ? '' : 's' }} Risk
                  </div>
                  <div v-if="batch.result?.calculation_errors?.length" class="text-[10px] mt-0.5 text-amber-600">
                    {{ batch.result.calculation_errors.length }} calcul{{ batch.result.calculation_errors.length === 1 ? '' : 's' }} non produit{{ batch.result.calculation_errors.length === 1 ? '' : 's' }}
                  </div>
                  <div v-if="batch.calculation_skip_count" class="text-[10px] mt-0.5" style="color: var(--subtle);">
                    {{ batch.calculation_skip_count }} calcul{{ batch.calculation_skip_count === 1 ? '' : 's' }} non applicable{{ batch.calculation_skip_count === 1 ? '' : 's' }} au statut du deal
                  </div>
                  <details v-if="batch.result?.calculation_errors?.length || batch.result?.calculation_skips?.length"
                           class="mt-1 max-w-lg whitespace-normal">
                    <summary class="cursor-pointer text-[10px]" style="color: var(--accent);">Voir le diagnostic</summary>
                    <div class="mt-1 flex flex-col gap-1 text-[10px]">
                      <div v-for="item in batch.result.calculation_errors || []" :key="`error-${item.deal_reference}-${item.kind}-${item.valuation_date}`" class="text-red-600">
                        {{ item.deal_reference }} · {{ item.kind }}<span v-if="item.valuation_date"> · {{ item.valuation_date }}</span> : {{ item.reason }}
                      </div>
                      <div v-for="item in batch.result.calculation_skips || []" :key="`skip-${item.deal_reference}-${item.kind}`" style="color: var(--subtle);">
                        {{ item.deal_reference }} · {{ item.kind }} : {{ item.reason }}
                      </div>
                    </div>
                  </details>
                </td>
                <td class="py-2 pr-3"><span class="badge" :class="batchStatusClass(batch.status)">{{ batchStatusLabel(batch.status) }}</span></td>
                <td class="py-2 pr-3 font-mono whitespace-nowrap" style="color: var(--subtle);">{{ fmtDate(batch.created_at) }}</td>
                <td class="py-2 text-right">
                  <button v-if="batch.status !== 'DELETED'" class="icon-btn-danger" title="Supprimer ce lot UAT"
                          :disabled="batch.busy" @click="deleteBatch(batch)">🗑</button>
                </td>
              </tr>
            </tbody>
          </table>
        </section>
      </template>
    </main>
  </div>
</template>

<script setup>
import { reactive, ref, onMounted, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { apiFetch } from '../utils/api.js'
import { confirmer } from '../composables/useConfirm.js'
import AlertMessage from '../components/ui/AlertMessage.vue'
import LoadingSpinner from '../components/ui/LoadingSpinner.vue'
import { formatDateTime } from '../utils/format.js'

const config = reactive({ users: [], providers: [], products: [], underlyings: [], lifecycle_profiles: [], limits: {} })
const batches = ref([])
const loading = ref(true)
const previewing = ref(false)
const generating = ref(false)
const error = ref('')
const notice = ref('')
const preview = ref(null)
let initializing = true

const form = reactive({
  target_user_id: null,
  mode: 'FULL_CHAIN',
  count: 8,
  // Internal reproducibility parameter; the pricing engine seed stays global.
  seed: 42,
  label: '',
  product_types: [],
  underlying_tickers: [],
  min_underlyings: 1,
  max_underlyings: 2,
  maturity_min_years: 1,
  maturity_max_years: 5,
  nominal_min: 100000,
  nominal_max: 2000000,
  currencies: ['EUR'],
  fixing_policy: 'AUTO_YAHOO',
  quotes_per_rfq: 2,
  provider_ids: [],
  rfq_profile: 'EXECUTABLE',
  product_calculations: 3,
  mtm_history_count: 3,
  compute_greeks: true,
  lifecycle_profile: 'COMPLETE_MIX',
})

watch(form, () => {
  if (!initializing) preview.value = null
}, { deep: true })

function detailText(data, fallback) {
  const detail = data?.detail
  if (typeof detail === 'string') return detail
  if (detail?.message) return detail.message
  return fallback
}

async function loadAll() {
  loading.value = true
  error.value = ''
  try {
    const [configRes, batchesRes] = await Promise.all([
      apiFetch('/api/admin/uat-generator/config'),
      apiFetch('/api/admin/uat-generator/batches'),
    ])
    const configData = await configRes.json().catch(() => ({}))
    const batchData = await batchesRes.json().catch(() => ([]))
    if (!configRes.ok) throw new Error(detailText(configData, 'Erreur de chargement de la configuration UAT'))
    if (!batchesRes.ok) throw new Error(detailText(batchData, 'Erreur de chargement des lots UAT'))
    Object.assign(config, configData)
    batches.value = batchData.map(batch => ({ ...batch, busy: false }))
    if (!form.target_user_id && config.users.length) {
      form.target_user_id = (config.users.find(user => user.role === 'user') || config.users[0]).id
    }
    if (!form.product_types.length) form.product_types = config.products.map(product => product.key)
    if (!form.underlying_tickers.length) form.underlying_tickers = config.underlyings.map(item => item.ticker)
    if (!form.provider_ids.length) form.provider_ids = config.providers.map(provider => provider.id)
  } catch (e) {
    error.value = e.message
  } finally {
    initializing = false
    loading.value = false
  }
}

function payload() {
  return JSON.parse(JSON.stringify(form))
}

async function previewBatch() {
  previewing.value = true
  error.value = ''
  notice.value = ''
  try {
    const res = await apiFetch('/api/admin/uat-generator/preview', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload()),
    })
    const data = await res.json().catch(() => ({}))
    if (!res.ok) throw new Error(detailText(data, 'Prévisualisation impossible'))
    preview.value = data
  } catch (e) {
    error.value = e.message
  } finally {
    previewing.value = false
  }
}

async function generateBatch() {
  if (!preview.value) return
  if (!await confirmer({ titre: 'Générer ce jeu de test ?',
                       message: `${preview.value.product_count} Products, ${preview.value.rfq_count} RFQ et `
                              + `${dealCountLabel(preview.value.deal_count)} seront créés sur ce compte.`,
                       confirmer: 'Générer' })) return
  generating.value = true
  error.value = ''
  notice.value = ''
  try {
    const res = await apiFetch('/api/admin/uat-generator/batches', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload()),
    })
    const data = await res.json().catch(() => ({}))
    if (!res.ok) throw new Error(detailText(data, 'Génération impossible'))
    batches.value.unshift({ ...data, busy: false })
    notice.value = `Lot ${data.batch_key} créé : ${data.product_count} Products, ${data.rfq_count} RFQ et ${dealCountLabel(data.deal_count)}.`
    preview.value = null
  } catch (e) {
    error.value = e.message
    await refreshBatches()
  } finally {
    generating.value = false
  }
}

async function refreshBatches() {
  const res = await apiFetch('/api/admin/uat-generator/batches')
  if (res.ok) batches.value = (await res.json()).map(batch => ({ ...batch, busy: false }))
}

async function deleteBatch(batch) {
  if (!await confirmer({ titre: `Supprimer le lot ${batch.batch_key} ?`,
                       message: `${batch.product_count} Products, ${batch.rfq_count} RFQ et `
                              + `${dealCountLabel(batch.deal_count)} de ce lot seulement.`,
                       confirmer: 'Supprimer le lot', danger: true })) return
  batch.busy = true
  error.value = ''
  notice.value = ''
  try {
    const res = await apiFetch(`/api/admin/uat-generator/batches/${batch.id}`, { method: 'DELETE' })
    const data = await res.json().catch(() => ({}))
    if (!res.ok) throw new Error(detailText(data, 'Suppression impossible'))
    batch.status = 'DELETED'
    batch.deleted_at = new Date().toISOString()
    notice.value = `Lot supprimé : ${data.deleted_products} Products, ${data.deleted_rfqs} RFQ, ${dealCountLabel(data.deleted_deals)}.`
  } catch (e) {
    error.value = e.message
  } finally {
    batch.busy = false
  }
}

const fmtDate = formatDateTime
const fmtMoney = (value, currency) => new Intl.NumberFormat('fr-FR', { style: 'currency', currency, maximumFractionDigits: 0 }).format(value)
const dealCountLabel = count => `${count} ${count === 1 ? 'deal' : 'deals'}`
const roleLabel = role => ({ admin: 'Admin', user: 'Utilisateur', ops_maker: 'Ops Maker', checker: 'Checker' }[role] || role)
const fixingLabel = value => ({ AUTO_YAHOO: 'Fournisseur auto' }[value] || value)
const lifecycleLabel = value => config.lifecycle_profiles.find(profile => profile.key === value)?.label || value
const scenarioLabel = value => ({ EXPIRED: 'quote expirée', INDICATIVE: 'quote indicative', NO_SELECTION: 'aucune quote sélectionnée' }[value] || value)
const modeLabel = value => ({
  FULL_CHAIN: 'RFQ → Product interne → Pricer → Booking → Risk',
  PRICER_RFQ_CHAIN: 'Pricer → Product interne → RFQ → Pricer → Booking → Risk',
  SAVED_PRODUCT_RFQ_CHAIN: 'Pricer → Product conservé → RFQ → Pricer → Booking → Risk',
  BOOKED_ONLY: 'Pricer → Product interne → Booking direct → Risk',
  RFQ_ONLY: 'RFQ → Product interne (non traitée)',
}[value] || value)
const batchStatusLabel = value => ({ RUNNING: 'En cours', COMPLETED: 'Terminé', FAILED: 'Échec', DELETED: 'Supprimé' }[value] || value)
const batchStatusClass = value => ({ RUNNING: 'badge-accent', COMPLETED: 'badge-positive', FAILED: 'badge-negative', DELETED: 'badge-muted' }[value] || 'badge-muted')

onMounted(loadAll)
</script>
