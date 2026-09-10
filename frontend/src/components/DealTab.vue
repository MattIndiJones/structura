<template>
  <div class="flex flex-col gap-5">

    <!-- No pricing result warning -->
    <div v-if="!store.result" class="card border-amber-800/50 bg-amber-950/20">
      <p class="text-amber-400 text-sm">
        ⚠ Lancez d'abord un pricing (▶ Pricer) pour pré-remplir le fair value et les temps d'observation.
      </p>
    </div>

    <div v-if="store.currentRfqId"
         :class="['text-[10px] border rounded-lg px-3 py-1.5 w-fit',
                  (fairValueFromRfq || rfqUnmatchedProvider) ? 'border-amber-700/60 bg-amber-950/20 text-amber-300' : 'border-slate-700 text-slate-500']">
      📨 Pré-rempli depuis la RFQ #{{ store.currentRfqId }} — contrepartie et prix traité repris de la réponse retenue.
      <template v-if="form.commercial_context?.client">
        <br />
        👤 {{ form.commercial_context.client.name }}
        <template v-if="form.commercial_context.mandate">
          · {{ form.commercial_context.mandate.name }}
        </template>
        <template v-if="form.commercial_context.opportunity">
          · {{ form.commercial_context.opportunity.reference }}
        </template>
      </template>
      <template v-if="rfqUnmatchedProvider">
        <br />
        ⚠ Le fournisseur <b>{{ rfqUnmatchedProvider }}</b> ne correspond à aucune contrepartie éligible —
        choisissez-la ci-dessous, ou rattachez-la une fois pour toutes dans
        <b>Administration → Fournisseurs RFQ</b>.
      </template>
      <template v-if="fairValueFromRfq">
        <br />
        ⚠ La fair value affichée est le prix modèle figé sur la RFQ<span v-if="rfqPriceAgeDays > 0"> (calculé il y a {{ rfqPriceAgeDays }} j)</span> —
        lancez <b>▶ Pricer</b> pour la recalculer aux conditions du jour avant de booker.
      </template>
    </div>

    <!-- ── Identité du deal ─────────────────────────────────── -->
    <div class="card">
      <h2 class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-4">Identité</h2>
      <div class="grid grid-cols-2 gap-3">
        <div class="col-span-2">
          <label class="label">Sens du deal</label>
          <div class="flex gap-2">
            <button v-for="s in ['vente', 'achat']" :key="s"
              @click="form.sens = s"
              :class="[
                'flex-1 py-2 rounded-lg text-xs font-bold border transition-colors',
                form.sens === s
                  ? s === 'vente'
                    ? 'bg-blue-900/50 border-blue-500 text-blue-300'
                    : 'bg-emerald-900/50 border-emerald-500 text-emerald-300'
                  : 'border-slate-700 text-slate-500 hover:border-slate-500'
              ]">
              <!-- Les DEUX côtés, toujours. Le deal se note du point de vue de
                   la contrepartie, l'AO du nôtre : un appel d'offres où « nous
                   achetons » se booke donc en « la banque vend ». C'est juste,
                   mais illisible tant qu'un seul des deux est écrit — on ne
                   sait plus qui est qui, et la marge en dépend. -->
              {{ s === 'vente' ? '↑ Vente — la banque vend, nous achetons'
                               : '↓ Achat — la banque achète, nous vendons' }}
            </button>
          </div>
        </div>

        <div class="col-span-2">
          <label class="label">Contrepartie <span class="text-red-400">*</span>
            <HelpTip text="Liste des contreparties éligibles, gérée dans Administration → Contreparties deals. Seules les banques actives de ce catalogue peuvent faire face à un deal." />
          </label>
          <select v-model="form.contrepartie" class="select">
            <option value="">— Choisir une contrepartie —</option>
            <option v-for="c in counterparties" :key="c.id" :value="c.name">
              {{ c.name }}{{ c.country ? ` (${c.country})` : '' }}
            </option>
          </select>
          <p v-if="errors.contrepartie" class="text-red-400 text-xs mt-1">{{ errors.contrepartie }}</p>
        </div>

        <div class="col-span-2">
          <label class="label">Type de produit
            <HelpTip text="Libre — sert à classer et filtrer dans la page Booking (par famille de produit). Pas de lien automatique avec les tags du script sauvegardé." />
          </label>
          <input v-model="form.product_type" type="text" class="input" list="product-type-suggestions"
            placeholder="ex: Autocall Athena, Reverse Convertible…" />
          <datalist id="product-type-suggestions">
            <option value="Autocall" /><option value="Options" />
            <option value="Produits à capital" /><option value="Sharks" />
          </datalist>
        </div>

        <div>
          <label class="label">Format juridique</label>
          <input v-model="form.transaction_format" class="input" list="deal-formats"
                 placeholder="EMTN, BMTN, OTC…" />
          <datalist id="deal-formats">
            <option value="EMTN" /><option value="BMTN" /><option value="OTC" />
          </datalist>
        </div>
        <div>
          <label class="label">Instrument</label>
          <input v-model="form.instrument_family" class="input" list="deal-instruments"
                 placeholder="Note, Swap…" />
          <datalist id="deal-instruments">
            <option value="Note" /><option value="Certificat" />
            <option value="Swap" /><option value="Option" />
          </datalist>
        </div>
        <div class="col-span-2">
          <label class="label">Famille de payoff</label>
          <input v-model="form.payoff_family" class="input"
                 placeholder="Phoenix, Autocall, Swap…" />
        </div>
        <div class="col-span-2">
          <label class="label">Description du payoff</label>
          <textarea v-model="form.payoff_description" class="input" rows="2"
                    placeholder="Précisions contractuelles utiles"></textarea>
        </div>
        <div class="col-span-2">
          <label class="label">Référence documentaire</label>
          <input v-model="form.documentation_reference" class="input"
                 placeholder="Term sheet / ISDA / confirmation" />
        </div>

        <div v-if="!store.currentRfqId" class="col-span-2 rounded-lg border p-3 flex flex-col gap-3"
             style="border-color: var(--border); background: var(--surface2)">
          <div class="flex items-center justify-between gap-3">
            <div>
              <div class="text-xs font-semibold">Attribution Client facultative</div>
              <p class="text-[10px] mt-0.5" style="color: var(--subtle)">
                Désactivée : le Deal reste un Deal Produit autonome normal.
              </p>
            </div>
            <button class="btn-ghost btn-sm" @click="toggleDirectClient">
              {{ directClientEnabled ? 'Retirer le contexte' : 'Rattacher à un Client' }}
            </button>
          </div>
          <div v-if="directClientEnabled" class="grid grid-cols-2 gap-2">
            <div class="col-span-2">
              <label class="label">Client</label>
              <select v-model="form.client_id" class="select" @change="onDirectDealClientChange">
                <option :value="null">— Choisir —</option>
                <option v-for="client in directDealClients" :key="client.id" :value="client.id">
                  {{ client.name }}
                </option>
              </select>
            </div>
            <div>
              <label class="label">Mandat / périmètre</label>
              <select v-model="form.mandate_id" class="select" :disabled="!form.client_id">
                <option :value="null">— Obligatoire —</option>
                <option v-for="mandat in directDealMandates" :key="mandat.id" :value="mandat.id">
                  {{ mandat.name }}
                </option>
              </select>
            </div>
            <div>
              <label class="label">Opportunity éventuelle</label>
              <select v-model="form.opportunity_id" class="select"
                      :disabled="!form.client_id" @change="onDirectDealOpportunityChange">
                <option :value="null">— Aucune —</option>
                <option v-for="opp in directDealOpportunities" :key="opp.id" :value="opp.id">
                  {{ opp.title || opp.reference }}
                </option>
              </select>
            </div>
            <div class="col-span-2">
              <label class="label">Contact principal éventuel</label>
              <select v-model="form.primary_affiliation_id" class="select"
                      :disabled="!form.client_id">
                <option :value="null">— Aucun —</option>
                <option v-for="contact in directDealContacts" :key="contact.affiliation_id"
                        :value="contact.affiliation_id">
                  {{ contact.first_name }} {{ contact.last_name }}
                </option>
              </select>
            </div>
            <div v-if="form.client_id && !form.opportunity_id" class="col-span-2">
              <label class="label">Motif du rattachement direct</label>
              <textarea v-model="form.commercial_reason" class="input" rows="2"
                        placeholder="Pourquoi ce Deal est rattaché directement, sans RFQ ni Opportunity"></textarea>
            </div>
          </div>
          <p v-if="errors.commercial" class="text-red-400 text-xs">{{ errors.commercial }}</p>
        </div>

        <div class="col-span-2">
          <label class="label">Traitement des constatations
            <HelpTip width="w-80" text="Classique : la clôture Yahoo non ajustée devient automatiquement le fixing de référence si tous les contrôles passent. Contrôlé : chaque fixing suit le workflow Ops Maker / Ops Checker. La politique est figée au booking." />
          </label>
          <select v-model="form.fixing_policy" class="select">
            <option value="AUTO_YAHOO">Classique — Yahoo automatique</option>
            <option value="FOUR_EYES">Produit contrôlé — validation à quatre yeux</option>
          </select>
          <p class="text-[10px] text-slate-500 mt-1">
            Une anomalie Yahoo bascule toujours la constatation en contrôle manuel, sans écraser le dernier fixing officiel.
          </p>
        </div>

        <div>
          <label class="label">Entité (vous)</label>
          <input :value="entityLabel" type="text"
            class="input bg-slate-800/40 text-slate-500 cursor-not-allowed" readonly />
        </div>
      </div>
    </div>

    <!-- ── Conditions de transaction ───────────────────────── -->
    <div class="card">
      <h2 class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-4">Conditions de transaction</h2>
      <div class="grid grid-cols-2 gap-3">
        <div class="col-span-2">
          <label class="label">Trade date
            <HelpTip text="Date d'accord commercial entre les parties. Les dates économiques du produit — strike, valeur, maturité et paiement — sont définies dans Economics." />
          </label>
          <input v-model="form.trade_date" type="date" class="input" />
        </div>

        <div>
          <label class="label">Fair Value (%) <span class="text-red-400">*</span>
            <HelpTip text="Prix théorique issu du dernier pricing Monte Carlo (onglet ▶ Pricer) — pas nécessairement le prix auquel le deal est traité. Modifiable ici si vous voulez figer une valeur différente du dernier run. Sert de base au P&L du deal : un deal ne peut pas être booké à 0." />
          </label>
          <input v-model.number="form.fair_value" type="number" step="0.01" class="input"
            :class="!store.result ? 'border-amber-700/50' : ''" />
          <p v-if="errors.fair_value" class="text-red-400 text-xs mt-1">{{ errors.fair_value }}</p>
          <p v-else-if="!store.result" class="text-amber-500 text-[10px] mt-0.5">
            {{ fairValueFromRfq ? 'Prix modèle de la RFQ — à recalculer' : 'Issu du dernier pricing' }}
          </p>
        </div>
        <div>
          <label class="label">Prix traité (%) <span class="text-red-400">*</span>
            <HelpTip text="Le prix réellement négocié avec la contrepartie — peut différer de la fair value (commission, négociation, contraintes de cotation). C'est ce prix qui sert de référence pour le suivi de P&L du deal." />
          </label>
          <input v-model.number="form.price_traded" type="number" step="0.01" class="input" />
          <p v-if="errors.price_traded" class="text-red-400 text-xs mt-1">{{ errors.price_traded }}</p>
        </div>

        <div class="col-span-2">
          <div class="flex items-center justify-between bg-slate-800/60 rounded-lg px-4 py-2.5">
            <span class="text-xs text-slate-400">Marge
              <HelpTip text="NOTRE marge sur ce deal, dans notre sens. Quand nous achetons, c'est fair value − prix traité : payer 98 un produit qui en vaut 100 nous fait gagner 2. Quand nous vendons, c'est l'inverse. Le sens affiché plus haut décrit la contrepartie ; nous sommes de l'autre côté. Indépendant de la performance future du produit." />
            </span>
            <span class="font-mono font-bold text-sm"
              :class="margin >= 0 ? 'text-emerald-400' : 'text-red-400'">
              {{ margin >= 0 ? '+' : '' }}{{ formatPercent(margin, 2) }}
              <span class="text-slate-500 font-normal ml-1 text-xs">
                ({{ store.globalParams.nominal > 0 ? formatCcy(store.globalParams.nominal * margin / 100) : '–' }})
              </span>
            </span>
          </div>
        </div>
      </div>
    </div>

    <!-- ── Booking ─────────────────────────────────────────── -->
    <div class="card">
      <div v-if="errors.nominal || errors.economics"
           class="bg-amber-950/30 border border-amber-700/50 rounded-lg px-4 py-3 mb-3 text-amber-300 text-sm">
        <p>{{ errors.nominal || errors.economics }}</p>
        <button class="text-xs underline mt-1" @click="store.leftTab = 'economics'">
          Ouvrir Economics
        </button>
      </div>
      <!-- Le portillon renvoie TOUS les contrôles en échec d'un coup : la
           liste existe pour qu'une seule tentative suffise à savoir quoi
           corriger. Recollés en une phrase, ils se lisaient bout à bout. -->
      <div v-if="bookingError"
        class="bg-red-900/30 border border-red-700/50 rounded-lg px-4 py-3 mb-3 text-red-300 text-sm">
        <p class="font-semibold">⚠ {{ bookingError }}</p>
        <ul v-if="bookingFailures.length" class="mt-2 space-y-1 list-disc pl-5 text-[13px]">
          <li v-for="(echec, i) in bookingFailures" :key="i">{{ echec }}</li>
        </ul>
      </div>
      <div v-if="bookedDeal"
        class="bg-emerald-900/30 border border-emerald-700/50 rounded-lg px-4 py-3 mb-3">
        <p class="text-emerald-400 font-semibold text-sm">✓ Deal booké — {{ bookedDeal.reference }}</p>
        <p class="text-slate-400 text-xs mt-1">
          Rendez-vous dans l'onglet Events pour renseigner les spots initiaux (S₀) et suivre les constatations.
        </p>
        <button class="btn-secondary text-xs mt-2 px-3 py-1"
          @click="$emit('go-events', bookedDeal.id)">
          → Voir les Events
        </button>
      </div>
      <!-- Une fois le deal booké, le bouton de booking disparaît : re-cliquer
           créait un second deal identique sous une nouvelle référence, sans
           rien pour le signaler. Booker deux fois le même produit reste
           légitime (deux clients), d'où le lien de réarmement explicite
           plutôt qu'un blocage. -->
      <template v-if="existingDeal">
        <RouterLink :to="`/booking?deal=${existingDeal.id}`"
          class="btn-primary w-full py-3 text-sm font-bold block text-center">
          📋 Voir le deal {{ existingDeal.reference }}
        </RouterLink>
        <button class="text-[11px] text-slate-500 hover:text-slate-300 underline mt-2 w-full text-center"
          @click="rearmBooking">
          Booker un autre deal à partir de ce pricing
        </button>
      </template>
      <button v-else class="btn-primary w-full py-3 text-sm font-bold"
        :disabled="dealsStore.loading"
        @click="book">
        <span v-if="dealsStore.loading"
          class="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin inline-block mr-2"></span>
        {{ dealsStore.loading ? 'Booking en cours…' : '📋 Booker le deal' }}
      </button>
    </div>

  </div>
</template>

<script setup>
import { ref, reactive, computed, watch, onMounted } from 'vue'
import { RouterLink } from 'vue-router'
import { usePricingStore } from '../stores/pricing.js'
import { useDealsStore } from '../stores/deals.js'
import { useAuthStore } from '../stores/auth.js'
import { apiFetch } from '../utils/api.js'
import HelpTip from './HelpTip.vue'
import { formatPercent, formatMoneyRound } from '../utils/format.js'

const emit = defineEmits(['go-events'])

const store = usePricingStore()
const dealsStore = useDealsStore()
const auth = useAuthStore()

const today = new Date().toISOString().split('T')[0]

// Eligible counterparties (admin-managed catalog, active only)
const counterparties = ref([])
onMounted(async () => {
  try {
    const res = await apiFetch('/api/deals/counterparties')
    if (res.ok) counterparties.value = await res.json()
  } catch { /* list stays empty — the select just shows the placeholder */ }
})

const form = reactive({
  sens: 'vente',
  contrepartie: '',
  product_type: '',
  transaction_format: '',
  instrument_family: '',
  payoff_family: '',
  payoff_description: '',
  documentation_reference: '',
  client_id: null,
  mandate_id: null,
  opportunity_id: null,
  primary_affiliation_id: null,
  commercial_context: null,
  commercial_reason: '',
  fixing_policy: 'AUTO_YAHOO',
  fair_value: 0,
  price_traded: 0,
  trade_date: store.globalParams.trade_date || today,
})
const directClientEnabled = ref(false)
const directDealClients = ref([])
const directDealMandates = ref([])
const directDealOpportunities = ref([])
const directDealContacts = ref([])

async function toggleDirectClient() {
  directClientEnabled.value = !directClientEnabled.value
  if (!directClientEnabled.value) {
    Object.assign(form, {
      client_id: null, mandate_id: null, opportunity_id: null,
      primary_affiliation_id: null, commercial_reason: '', commercial_context: null,
    })
    directDealMandates.value = []
    directDealOpportunities.value = []
    directDealContacts.value = []
    return
  }
  if (!directDealClients.value.length) {
    const response = await apiFetch('/api/clients')
    if (response.ok) directDealClients.value = await response.json()
  }
}

async function loadDirectDealOptions(clientId) {
  directDealMandates.value = []
  directDealOpportunities.value = []
  directDealContacts.value = []
  if (!clientId) return
  const [mandates, opportunities, contacts] = await Promise.all([
    apiFetch(`/api/clients/${clientId}/mandates`),
    apiFetch(`/api/opportunities?client_id=${clientId}&open_only=true`),
    apiFetch(`/api/clients/${clientId}/contacts`),
  ])
  if (mandates.ok) directDealMandates.value = await mandates.json()
  if (opportunities.ok) directDealOpportunities.value = await opportunities.json()
  if (contacts.ok) directDealContacts.value = await contacts.json()
}

async function onDirectDealClientChange() {
  Object.assign(form, {
    mandate_id: null, opportunity_id: null,
    primary_affiliation_id: null, commercial_reason: '',
  })
  await loadDirectDealOptions(form.client_id)
}

function onDirectDealOpportunityChange() {
  const selected = directDealOpportunities.value.find(opp => opp.id === form.opportunity_id)
  if (!selected) return
  form.mandate_id = selected.mandate_id ?? null
  form.primary_affiliation_id = selected.primary_contact?.affiliation_id ?? null
  form.transaction_format ||= selected.transaction_format || ''
  form.instrument_family ||= selected.instrument_family || ''
  form.payoff_family ||= selected.payoff_family || ''
  form.payoff_description ||= selected.payoff_description || ''
  form.commercial_reason = ''
}

watch(() => store.result, (r) => {
  if (r) {
    form.fair_value = parseFloat((r.price * 100).toFixed(4))
    if (!form.price_traded) form.price_traded = form.fair_value
  }
}, { immediate: true })

watch(() => store.globalParams.trade_date, (value) => {
  if (value && form.trade_date !== value) form.trade_date = value
}, { immediate: true })
watch(() => form.trade_date, (value) => {
  if (value && store.globalParams.trade_date !== value) store.globalParams.trade_date = value
})

// Handoff from RfqView.vue's "Booker cette réponse" (see pricing.js:
// loadFromRfq). Les economics sont recopiés dans le store partagé ; ce
// composant ne garde localement que les termes commerciaux du deal.
//
// A watch, not a read at setup: this component is v-if'd on store.leftTab,
// which survives navigation. If the Deal tab was already open, DealTab is
// created BEFORE Pricer.vue's async onMounted has even fetched the RFQ, so a
// setup-time read finds nothing and the prefill is silently lost. immediate
// covers the opposite order (prefill already waiting when we mount), and
// nulling it after applying keeps it from being replayed onto a later deal.
const rfqPrefillAt = ref(null)
// Provider whose quote won, when no eligible counterparty could be resolved
// from it — the field stays empty and the banner names the provider so the
// desk knows what to pick instead of facing a blank required select.
const rfqUnmatchedProvider = ref('')
watch(() => store.pendingDealPrefill, (prefill) => {
  if (!prefill) return
  const {
    nominal, strike_date, value_date, payment_date,
    fair_value_at, rfq_provider_label, ...formFields
  } = prefill
  Object.assign(form, formFields)
  Object.assign(store.globalParams, {
    ...(nominal != null ? { nominal } : {}),
    ...(strike_date ? { strike_date } : {}),
    ...(value_date ? { value_date } : {}),
    ...(payment_date ? { payment_date } : {}),
  })
  rfqPrefillAt.value = fair_value_at || null
  rfqUnmatchedProvider.value = (rfq_provider_label && !formFields.contrepartie)
    ? rfq_provider_label : ''
  store.pendingDealPrefill = null
}, { immediate: true })

// True while fair_value is still the RFQ's stored model price rather than a
// price computed here — cleared by the store.result watch above on the first
// ▶ Pricer. Drives the "à revérifier" warning in the RFQ banner.
const fairValueFromRfq = computed(() => !!rfqPrefillAt.value && !store.result)
const rfqPriceAgeDays = computed(() => {
  if (!rfqPrefillAt.value) return 0
  return Math.floor((Date.now() - new Date(rfqPrefillAt.value)) / 86400000)
})

function formatCcy(val) {
  return formatMoneyRound(val, store.globalParams.deal_ccy)
}

// ── Computed ─────────────────────────────────────────────
/**
 * Notre marge, du côté qui est le NÔTRE.
 *
 * Elle se calculait `prix traité − fair value` quel que soit le sens. Juste
 * quand nous vendons — encaisser plus que la valeur théorique est un gain —
 * mais de signe inverse quand nous achetons : payer 98 un produit qui en vaut
 * 100 nous fait gagner 2, et l'écran affichait −2.
 *
 * `form.sens` décrit la CONTREPARTIE (« la banque vend »), donc nous sommes de
 * l'autre côté : `vente` veut dire que nous achetons.
 */
const nousAchetons = computed(() => form.sens === 'vente')
const margin = computed(() => {
  const traite = form.price_traded || 0
  const juste = form.fair_value || 0
  return nousAchetons.value ? juste - traite : traite - juste
})

const entityLabel = computed(() => auth.user?.entity_id ? `Entité #${auth.user.entity_id}` : 'N/A')

const observationTimes = computed(() => {
  if (!store.result?.flux_table) return []
  return [...new Set(Object.values(store.result.flux_table).map(e => e.t))].sort((a, b) => a - b)
})

// ── Validation & booking ──────────────────────────────────
const errors = reactive({})
const bookingError = ref(null)
const bookingFailures = ref([])
const bookedDeal = ref(null)

// Le deal existe déjà — soit on vient de le booker, soit on a rouvert un deal
// booké (store.openedDeal, voir pricing.js:loadFromDeal). Dans les deux cas le
// bouton de booking créerait un doublon sous une nouvelle référence.
const existingDeal = computed(() => bookedDeal.value || store.openedDeal)

// Rebooker le même produit reste légitime (deux clients, deux trades) — mais
// ça doit être un geste explicite.
function rearmBooking() {
  bookedDeal.value = null
  store.openedDeal = null
}

function validate() {
  Object.keys(errors).forEach(k => delete errors[k])
  if (!form.contrepartie.trim()) errors.contrepartie = 'Contrepartie requise'
  if (!store.globalParams.nominal || store.globalParams.nominal <= 0) {
    errors.nominal = 'Nominal requis dans Economics'
  }
  if (!(store.globalParams.strike_date && store.globalParams.value_date
        && store.maturityDate && store.globalParams.payment_date)) {
    errors.economics = 'Complétez les dates économiques avant le booking'
  }
  if (!form.price_traded) errors.price_traded = 'Prix traité requis'
  // A zero fair value is never a real product — it means nothing has been
  // priced in this session (the RFQ→booking path arrives with the results
  // cleared). Booking it would set the deal's whole P&L baseline to 0.
  if (!form.fair_value) errors.fair_value = 'Fair value requise — lancez ▶ Pricer, ou saisissez-la'
  if (form.client_id && !form.mandate_id) {
    errors.commercial = 'Sélectionnez le mandat ou périmètre du Client.'
  } else if (form.client_id && !form.opportunity_id
             && form.commercial_reason.trim().length < 10) {
    errors.commercial = 'Expliquez le rattachement direct (10 caractères minimum).'
  }
  return Object.keys(errors).length === 0
}

async function book() {
  bookingError.value = null
  bookingFailures.value = []
  bookedDeal.value = null
  if (!validate()) return

  const underlyings = store.underlyings.map(u => ({
    name: u.name,
    ticker: u.ticker || '',
    ccy: u.ccy,
  }))

  const marketSnapshot = {
    r: store.globalParams.r,
    T: store.globalParams.T,
    model: store.globalParams.model,
    antithetic: store.globalParams.antithetic,
    deal_ccy: store.globalParams.deal_ccy,
    rateModel: store.globalParams.rateModel,
    sigma_r: store.globalParams.sigma_r,
    a_r: store.globalParams.a_r,
    yieldCurve: store.yieldCurve.enabled ? store.yieldCurve.pillars : [],
    // Full underlying objects (not just name/ticker/sigma/q/ccy) so a smile
    // model (Heston/SABR/Local Vol/quanto) survives a reopen — see
    // pricing.js:loadFromDeal and reprice_inputs' "still alive" branch.
    underlyings: store.underlyings.map(u => ({
      ...u,
      // Freeze both the generating assumptions and the exact annual nodes.
      // Lifecycle replay consumes the nodes; q/decay explain how they arose.
      dividendCurve: store.buildDividendCurve(u),
    })),
    corrMatrix: store.corrMatrix,
    // PARAM overrides frozen in STORED units (fractions), same shape the
    // pricing API takes — the lifecycle replay and the watchlist read these,
    // so a deal booked with a degressive M_AC_BAR keeps its real barrier
    // schedule instead of falling back to the script's seed default.
    user_params: store.buildUserParams(),
    // CONSTAT calendar values frozen at booking (raw dates/frequencies, same
    // shape /api/price takes) — without them an expert-mode deal can never be
    // replayed (lifecycle) or residual-MtM'd: the script alone has no dates.
    constats: store.buildConstats(),
  }

  try {
    const deal = await dealsStore.bookDeal({
      sens: form.sens,
      contrepartie: form.contrepartie.trim(),
      devise: store.globalParams.deal_ccy,
      product_type: form.product_type.trim(),
      fixing_policy: form.fixing_policy,
      nominal: store.globalParams.nominal,
      fair_value: form.fair_value,
      price_traded: form.price_traded,
      trade_date: form.trade_date,
      strike_date: store.globalParams.strike_date,
      value_date: store.globalParams.value_date,
      maturity_date: store.maturityDate,
      payment_date: store.globalParams.payment_date,
      T: store.globalParams.T,
      underlyings,
      observation_times: observationTimes.value,
      script_snapshot: store.script,
      script_id: store.currentScriptId || null,
      market_snapshot: marketSnapshot,
      indicative_id: store.currentIndicativeId || null,
      rfq_id: store.currentRfqId || null,
      client_id: form.client_id,
      mandate_id: form.mandate_id,
      opportunity_id: form.opportunity_id,
      primary_affiliation_id: form.primary_affiliation_id,
      transaction_format: form.transaction_format || null,
      instrument_family: form.instrument_family || null,
      payoff_family: form.payoff_family || null,
      payoff_description: form.payoff_description || null,
      documentation_reference: form.documentation_reference || null,
      commercial_reason: form.commercial_reason || null,
    })
    bookedDeal.value = deal
  } catch (e) {
    bookingError.value = e.message
    bookingFailures.value = e.failures || []
  }
}
</script>
