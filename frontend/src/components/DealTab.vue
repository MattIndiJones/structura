<template>
  <div class="flex flex-col gap-5">

    <!-- No pricing result warning -->
    <div v-if="!store.result" class="card border-amber-800/50 bg-amber-950/20">
      <p class="text-amber-400 text-sm">
        ⚠ Lancez d'abord un pricing (▶ Pricer) pour pré-remplir le fair value et les temps d'observation.
      </p>
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
              {{ s === 'vente' ? '↑ Vente (banque vend)' : '↓ Achat (banque achète)' }}
            </button>
          </div>
        </div>

        <div class="col-span-2">
          <label class="label">Contrepartie <span class="text-red-400">*</span></label>
          <input v-model="form.contrepartie" type="text" class="input"
            placeholder="Nom du client / contrepartie" />
          <p v-if="errors.contrepartie" class="text-red-400 text-xs mt-1">{{ errors.contrepartie }}</p>
        </div>

        <div>
          <label class="label">Entité (vous)</label>
          <input :value="entityLabel" type="text"
            class="input bg-slate-800/40 text-slate-500 cursor-not-allowed" readonly />
        </div>
        <div>
          <label class="label">Devise</label>
          <input :value="store.globalParams.deal_ccy" type="text"
            class="input bg-slate-800/40 text-slate-500 cursor-not-allowed" readonly />
        </div>
      </div>
    </div>

    <!-- ── Économique ──────────────────────────────────────── -->
    <div class="card">
      <h2 class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-4">Économique</h2>
      <div class="grid grid-cols-2 gap-3">
        <div class="col-span-2">
          <label class="label">Nominal <span class="text-red-400">*</span></label>
          <input v-model="nominalRaw" @blur="formatNominal" @focus="unformatNominal"
            type="text" inputmode="numeric" class="input font-mono"
            placeholder="1 000 000" />
          <p v-if="errors.nominal" class="text-red-400 text-xs mt-1">{{ errors.nominal }}</p>
        </div>

        <div>
          <label class="label">Fair Value (%)</label>
          <input v-model.number="form.fair_value" type="number" step="0.01" class="input"
            :class="!store.result ? 'border-amber-700/50' : ''" />
          <p v-if="!store.result" class="text-amber-500 text-[10px] mt-0.5">Issu du dernier pricing</p>
        </div>
        <div>
          <label class="label">Prix traité (%) <span class="text-red-400">*</span></label>
          <input v-model.number="form.price_traded" type="number" step="0.01" class="input" />
          <p v-if="errors.price_traded" class="text-red-400 text-xs mt-1">{{ errors.price_traded }}</p>
        </div>

        <div class="col-span-2">
          <div class="flex items-center justify-between bg-slate-800/60 rounded-lg px-4 py-2.5">
            <span class="text-xs text-slate-400">Marge</span>
            <span class="font-mono font-bold text-sm"
              :class="margin >= 0 ? 'text-emerald-400' : 'text-red-400'">
              {{ margin >= 0 ? '+' : '' }}{{ margin.toFixed(2) }}%
              <span class="text-slate-500 font-normal ml-1 text-xs">
                ({{ nominalValue > 0 ? formatCcy(nominalValue * margin / 100) : '–' }})
              </span>
            </span>
          </div>
        </div>
      </div>
    </div>

    <!-- ── Dates ───────────────────────────────────────────── -->
    <div class="card">
      <h2 class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-4">Dates</h2>
      <div class="grid grid-cols-2 gap-3">
        <div>
          <label class="label">Trade date</label>
          <input v-model="form.trade_date" type="date" class="input" />
        </div>
        <div>
          <label class="label">Strike date <span class="text-slate-600 font-normal">(fixing S₀)</span></label>
          <input v-model="form.strike_date" type="date" class="input" />
        </div>
        <div>
          <label class="label">Value date
            <span class="text-slate-600 font-normal"
              title="t=0 pour l'actualisation. Généralement strike + 2j ouvrés.">?</span>
          </label>
          <input v-model="form.value_date" type="date" class="input"
            @change="store.globalParams.value_date = form.value_date" />
        </div>
        <div>
          <label class="label">Maturité</label>
          <input :value="maturityDate" type="date"
            class="input bg-slate-800/40 text-slate-500 cursor-not-allowed" readonly
            title="Calculée automatiquement : value date + T" />
        </div>
      </div>
    </div>

    <!-- ── Aperçu des constatations ──────────────────────── -->
    <div class="card">
      <h2 class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3">
        Structure des constatations
      </h2>

      <div v-if="!store.result" class="text-xs text-slate-600 italic py-2">
        Lancez un pricing (▶ Pricer) pour visualiser le tableau des constatations.
      </div>

      <div v-else>
        <div class="overflow-x-auto">
          <table class="w-full text-xs border-collapse">
            <thead>
              <tr class="border-b border-slate-700">
                <th class="text-left text-slate-500 font-medium pb-2 pr-3">#</th>
                <th class="text-left text-slate-500 font-medium pb-2 pr-3 whitespace-nowrap">Label</th>
                <th class="text-left text-slate-500 font-medium pb-2 pr-3 whitespace-nowrap">Date</th>
                <th class="text-left text-slate-500 font-medium pb-2 pr-3 whitespace-nowrap">T (Y)</th>
                <th v-for="u in store.underlyings" :key="u.name"
                  class="text-left text-slate-500 font-medium pb-2 pr-2 whitespace-nowrap">
                  {{ u.ticker || u.name }}
                  <span class="text-slate-600 font-normal">S₀</span>
                </th>
                <th class="text-left text-slate-500 font-medium pb-2">Statut</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(ev, i) in previewEvents" :key="i"
                :class="[
                  'border-b border-slate-800/50',
                  ev.t === 0 ? 'bg-amber-950/20' : '',
                  ev.isFuture && ev.t !== 0 ? 'opacity-50' : '',
                ]">
                <td class="py-1.5 pr-3 text-slate-500">{{ i + 1 }}</td>
                <td class="py-1.5 pr-3 whitespace-nowrap"
                  :class="ev.t === 0 ? 'text-amber-400 font-semibold' : 'text-slate-300'">
                  {{ ev.label }}
                </td>
                <td class="py-1.5 pr-3 font-mono text-slate-300 whitespace-nowrap">{{ ev.date }}</td>
                <td class="py-1.5 pr-3 font-mono text-slate-400">{{ ev.t.toFixed(2) }}</td>
                <td v-for="u in store.underlyings" :key="u.name" class="py-1.5 pr-2">
                  <span class="text-slate-600 font-mono text-[10px]">–</span>
                </td>
                <td class="py-1.5">
                  <span class="text-[10px]"
                    :class="ev.isFuture ? 'text-slate-600' : 'text-amber-400'">
                    {{ ev.isFuture ? 'futur' : 'à observer' }}
                  </span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <p class="text-[10px] text-slate-600 mt-2">
          {{ previewEvents.length }} constatation(s) · {{ store.underlyings.length }} sous-jacent(s) ·
          Les spots S₀ se saisissent dans Events après booking.
        </p>
      </div>
    </div>

    <!-- ── Booking ─────────────────────────────────────────── -->
    <div class="card">
      <div v-if="bookingError"
        class="bg-red-900/30 border border-red-700/50 rounded-lg px-4 py-3 mb-3 text-red-300 text-sm">
        ⚠ {{ bookingError }}
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
      <button class="btn-primary w-full py-3 text-sm font-bold"
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
import { usePricingStore } from '../stores/pricing.js'
import { useDealsStore } from '../stores/deals.js'
import { useAuthStore } from '../stores/auth.js'

const emit = defineEmits(['go-events'])

const store = usePricingStore()
const dealsStore = useDealsStore()
const auth = useAuthStore()

const today = new Date().toISOString().split('T')[0]

function addBizDays(isoDate, n) {
  const d = new Date(isoDate)
  let added = 0
  while (added < n) {
    d.setDate(d.getDate() + 1)
    if (d.getDay() !== 0 && d.getDay() !== 6) added++
  }
  return d.toISOString().split('T')[0]
}

const form = reactive({
  sens: 'vente',
  contrepartie: '',
  fair_value: 0,
  price_traded: 0,
  trade_date: today,
  strike_date: today,
  value_date: addBizDays(today, 2),
})

watch(() => store.result, (r) => {
  if (r) {
    form.fair_value = parseFloat((r.price * 100).toFixed(4))
    if (!form.price_traded) form.price_traded = form.fair_value
  }
}, { immediate: true })

watch(() => store.globalParams.value_date, (v) => {
  if (v) form.value_date = v
}, { immediate: true })

// ── Nominal formatting ────────────────────────────────────
const nominalRaw = ref('1 000 000')
const nominalValue = computed(() => {
  return parseFloat(nominalRaw.value.replace(/\s/g, '').replace(',', '.')) || 0
})

function formatNominal() {
  const n = nominalValue.value
  if (n) nominalRaw.value = n.toLocaleString('fr-FR').replace(/,/g, ' ')
}
function unformatNominal() {
  nominalRaw.value = String(nominalValue.value || '')
}
onMounted(() => formatNominal())

function formatCcy(val) {
  return val.toLocaleString('fr-FR', {
    style: 'currency', currency: store.globalParams.deal_ccy, maximumFractionDigits: 0,
  })
}

// ── Computed ─────────────────────────────────────────────
const margin = computed(() => (form.price_traded || 0) - (form.fair_value || 0))

const maturityDate = computed(() => {
  if (!form.value_date || !store.globalParams.T) return ''
  const d = new Date(form.value_date)
  d.setDate(d.getDate() + Math.round(store.globalParams.T * 365.25))
  return d.toISOString().split('T')[0]
})

const entityLabel = computed(() => auth.user?.entity_id ? `Entité #${auth.user.entity_id}` : 'N/A')

const observationTimes = computed(() => {
  if (!store.result?.flux_table) return []
  return [...new Set(Object.values(store.result.flux_table).map(e => e.t))].sort((a, b) => a - b)
})

function addDays(isoDate, days) {
  const d = new Date(isoDate)
  d.setDate(d.getDate() + Math.round(days))
  return d.toISOString().split('T')[0]
}

const previewEvents = computed(() => {
  if (!store.result) return []
  const todayStr = new Date().toISOString().split('T')[0]
  const events = []

  // Ligne 0 : strike date (fixing S₀)
  events.push({
    label: 'Strike / Fixing S₀',
    date: form.strike_date || todayStr,
    t: 0,
    isFuture: (form.strike_date || todayStr) > todayStr,
  })

  // Constatations dérivées des flux
  observationTimes.value.forEach((t, idx) => {
    const date = addDays(form.value_date || todayStr, t * 365.25)
    const isLast = idx === observationTimes.value.length - 1
    events.push({
      label: isLast ? 'Maturité' : `Obs. ${idx + 1} (${t.toFixed(2)}Y)`,
      date,
      t,
      isFuture: date > todayStr,
    })
  })

  return events
})

// ── Validation & booking ──────────────────────────────────
const errors = reactive({})
const bookingError = ref(null)
const bookedDeal = ref(null)

function validate() {
  Object.keys(errors).forEach(k => delete errors[k])
  if (!form.contrepartie.trim()) errors.contrepartie = 'Contrepartie requise'
  if (!nominalValue.value || nominalValue.value <= 0) errors.nominal = 'Nominal requis'
  if (!form.price_traded) errors.price_traded = 'Prix traité requis'
  return Object.keys(errors).length === 0
}

async function book() {
  bookingError.value = null
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
    underlyings: store.underlyings.map(u => ({
      name: u.name, ticker: u.ticker, sigma: u.sigma, q: u.q, ccy: u.ccy,
    })),
    corrMatrix: store.corrMatrix,
  }

  try {
    const deal = await dealsStore.bookDeal({
      sens: form.sens,
      contrepartie: form.contrepartie.trim(),
      devise: store.globalParams.deal_ccy,
      nominal: nominalValue.value,
      fair_value: form.fair_value,
      price_traded: form.price_traded,
      trade_date: form.trade_date,
      strike_date: form.strike_date,
      value_date: form.value_date,
      maturity_date: maturityDate.value,
      T: store.globalParams.T,
      underlyings,
      observation_times: observationTimes.value,
      script_snapshot: store.script,
      script_id: store.currentScriptId || null,
      market_snapshot: marketSnapshot,
    })
    bookedDeal.value = deal
  } catch (e) {
    bookingError.value = e.message
  }
}
</script>
