<template>
  <div class="flex-1 flex flex-col min-h-0">

    <!-- ── Barre d'outils : statut de pricing + actions ─────────── -->
    <div class="sticky top-0 z-30 border-b px-5 py-2.5 flex items-center gap-4 shrink-0"
         style="background: rgba(250,249,246,.90); backdrop-filter: blur(10px); border-color: var(--border); box-shadow: 0 4px 14px rgba(11,26,49,.025);">

      <BackLink :fallback="{ path: '/', query: { category: 'pricing' } }" />

      <!-- Progress bar / résumé prix / erreur -->
      <div class="flex-1 min-w-0">
        <div v-if="store.progress > 0" class="progress-track">
          <div class="progress-fill" :style="{ width: store.progress + '%' }"></div>
        </div>
        <div v-else-if="store.result" class="hidden sm:flex items-center gap-3 text-xs" style="color: var(--muted);">
          <span class="font-bold text-sm" style="color: var(--accent);">
            <SensitiveValue>{{ (store.result.price * 100).toFixed(2) }}%</SensitiveValue>
          </span>
          <span>
            IC 95% [<SensitiveValue>{{ (store.result.ic95[0]*100).toFixed(2) }}%, {{ (store.result.ic95[1]*100).toFixed(2) }}%</SensitiveValue>]
          </span>
          <span v-if="!demo.linkedinMode" style="color: var(--subtle);">
            <SensitiveValue>{{ store.result.elapsed_ms.toFixed(0) }} ms · {{ store.result.n_eff.toLocaleString() }} chemins</SensitiveValue>
          </span>
        </div>
        <!-- Error display -->
        <div v-if="store.error" class="text-xs truncate" style="color: var(--negative);">⚠ {{ store.error }}</div>
        <div v-else-if="store.marketDataLoading" class="text-xs truncate" style="color: var(--accent);">
          ↻ Mise à jour du marché à la date de valorisation…
        </div>
      </div>

      <div class="flex items-center gap-2 shrink-0">
        <span class="hidden md:inline-flex text-[10px] font-mono px-2 py-1 rounded border"
          :class="estimateClass(store.pricingEstimate)"
          :title="estimateTitle(store.pricingEstimate, 'Prix')">
          Est. {{ formatWork(store.pricingEstimate.workUnits) }} · {{ formatMemory(store.pricingEstimate.estimatedPeakMb) }}
        </span>
        <button v-if="store.result && store.selectedGreeks.length > 0"
          class="btn-secondary text-xs px-3 py-1.5"
          :disabled="store.loading"
          :title="estimateTitle(store.greeksEstimate, 'Prix + Greeks')"
          @click="store.runGreeks()">
          ∂ Greeks
        </button>
        <button
          class="btn-primary flex items-center gap-2 text-sm"
          :disabled="store.loading || store.marketDataLoading || (!!store.parseError && !store.scriptDirty)"
          @click="store.runPricing()">
          <span v-if="store.loading" class="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin"></span>
          {{ store.marketDataLoading ? 'Marché…' : store.loading ? 'Calcul…' : '▶ Pricer' }}
        </button>
      </div>
    </div>

    <ProductContextBar />

    <!-- Les déclinaisons du deal, juste sous la barre d'outils : ce qu'on
         regarde doit se lire avant ce qu'on lit. -->
    <VariantBar />

    <div v-if="store.contractTermsLocked"
         class="mx-5 mt-3 rounded-lg border px-3 py-2 shrink-0"
         style="border-color: var(--border); background: var(--surface2); color: var(--text);">
      <div class="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs">
        <span class="inline-flex h-6 w-6 items-center justify-center rounded-full"
              style="background: color-mix(in srgb, var(--accent) 12%, transparent);" aria-hidden="true">🔒</span>
        <span class="font-semibold">{{ store.openedDeal ? 'Contrat booké' : 'Produit conservé' }}</span>
        <DealReferenceLink v-if="store.openedDeal"
                           :deal-id="store.openedDeal.id" :reference="store.openedDeal.reference"
                           class="font-mono font-semibold" style="color: var(--accent);" />
        <span v-else class="font-mono font-semibold" style="color: var(--accent);">
          {{ store.currentProduct?.reference }}
        </span>
        <span style="color: var(--muted);">
          Payoff, panier et dates figés. Marché, modèle et date de valorisation restent modifiables pour le repricing.
        </span>
      </div>
    </div>

    <!-- ── Main 2-col ──────────────────────────────────────────── -->
    <main class="flex-1 min-h-0 grid grid-cols-1 lg:grid-cols-2 gap-0 items-stretch">

      <!-- LEFT: définition produit, marché, booking et cycle de vie -->
      <div class="border-r border-slate-800 flex flex-col">
        <div class="flex gap-1 border-b border-slate-800 bg-slate-900/50 px-2 py-1.5 overflow-x-auto">
          <button
            v-for="tab in leftTabs" :key="tab.id"
            class="tab-btn shrink-0 whitespace-nowrap" :class="{ active: store.leftTab === tab.id }"
            @click="store.leftTab = tab.id">
            {{ tab.label }}
          </button>
        </div>
        <div class="flex-1 overflow-y-auto p-5 flex flex-col gap-5">
          <PayScriptEditor v-show="store.leftTab === 'script'" />
          <EconomicsTab    v-show="store.leftTab === 'economics'" />
          <MarketParams    v-show="store.leftTab === 'params'" />
          <!-- v-show, PAS v-if : les economics vivent dans le store, mais les
               champs commerciaux de Deal restent locaux au composant. Le
               détruire à chaque changement d'onglet ferait perdre le sens,
               la contrepartie et le prix traité. -->
          <DealTab         v-show="store.leftTab === 'deal'" @go-events="goToEvents" />
          <EventsTab       v-if="store.leftTab === 'events'" :initial-deal-id="eventsInitialDealId" />
        </div>
      </div>

      <!-- RIGHT: Results tabs -->
      <div class="flex flex-col">
        <div class="flex gap-1 border-b border-slate-800 bg-slate-900/50 overflow-x-auto px-2 py-1.5">
          <button
            v-for="tab in rightTabs" :key="tab.id"
            class="tab-btn whitespace-nowrap text-xs px-3 py-1.5" :class="{ active: store.rightTab === tab.id }"
            @click="store.rightTab = tab.id">
            {{ tab.label }}
          </button>
        </div>
        <div class="flex-1 overflow-y-auto p-5">
          <ResultsPanel v-show="store.rightTab !== 'kid' && store.rightTab !== 'emt'" />
          <KidPanel     v-if="store.rightTab === 'kid'" />
          <EmtPanel     v-if="store.rightTab === 'emt'" />
        </div>
      </div>
    </main>
  </div>
</template>

<script setup>
import BackLink from '../components/ui/BackLink.vue'
import PayScriptEditor from '../components/PayScriptEditor.vue'
import EconomicsTab    from '../components/EconomicsTab.vue'
import VariantBar      from '../components/VariantBar.vue'
import MarketParams    from '../components/MarketParams.vue'
import DealTab         from '../components/DealTab.vue'
import EventsTab       from '../components/EventsTab.vue'
import ResultsPanel    from '../components/ResultsPanel.vue'
import KidPanel        from '../components/KidPanel.vue'
import EmtPanel        from '../components/EmtPanel.vue'
import SensitiveValue  from '../components/SensitiveValue.vue'
import ProductContextBar from '../components/ProductContextBar.vue'
import DealReferenceLink from '../components/DealReferenceLink.vue'
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { usePricingStore } from '../stores/pricing.js'
import { useDealsStore } from '../stores/deals.js'
import { useRfqStore } from '../stores/rfq.js'
import { useProductsStore } from '../stores/products.js'
import { useDemoModeStore } from '../stores/demoMode.js'
import { findProductModel } from '../utils/productModels.js'

const store = usePricingStore()
const dealsStore = useDealsStore()
const rfqStore = useRfqStore()
const productsStore = useProductsStore()
const demo = useDemoModeStore()
const route = useRoute()

const eventsInitialDealId = ref(null)

function formatWork(value) {
  if (value >= 1e9) return `${(value / 1e9).toFixed(1)} Md u.`
  if (value >= 1e6) return `${(value / 1e6).toFixed(1)} M u.`
  if (value >= 1e3) return `${(value / 1e3).toFixed(0)} k u.`
  return `${value} u.`
}

function formatMemory(value) {
  return value >= 1024 ? `${(value / 1024).toFixed(1)} Go` : `${value.toFixed(0)} Mo`
}

function estimateClass(estimate) {
  if (estimate.blocked) return 'border-red-300 bg-red-50 text-red-700'
  if (estimate.warnings.length) return 'border-amber-300 bg-amber-50 text-amber-700'
  return 'border-slate-300 bg-white/60 text-slate-500'
}

function estimateTitle(estimate, label) {
  const details = [...estimate.reasons, ...estimate.warnings]
  return `${label} : ${formatWork(estimate.workUnits)}, pic mémoire ${formatMemory(estimate.estimatedPeakMb)}`
    + (details.length ? ` — ${details.join(' · ')}` : '')
}

function goToEvents(dealId) {
  eventsInitialDealId.value = dealId
  store.leftTab = 'events'
}

// Deep link from the Booking view (/pricer?dealId=…) — reload that deal's
// exact frozen state (script + params + underlyings) into every tab. Callers
// can name the landing tab; legacy links still open the lifecycle events.
onMounted(async () => {
  const dealId = route.query.dealId
  if (dealId) {
    const deal = await dealsStore.selectDeal(Number(dealId))
    if (deal) {
      await store.loadFromDeal(deal)
      if (!deal.product_id) {
        store.error = 'Ce deal ne possède pas de Product canonique.'
        return
      }
      const loaded = await productsStore.fetchOne(deal.product_id)
      if (!loaded) {
        store.error = 'Le Product canonique de ce deal ne peut pas être chargé.'
        return
      }
      store.currentProduct = loaded.product
    }
    if (route.query.tab === 'script') store.leftTab = 'script'
    else goToEvents(Number(dealId))
    return
  }

  // Deep link from RfqView.vue's "Booker cette réponse" (/pricer?fromRfq=…)
  // — pre-fill script/underlyings/params from the RFQ and contrepartie/
  // price_traded from its retained quote, then land straight on Deal so
  // the only thing left to do is complete dates/sens and book.
  const fromRfq = route.query.fromRfq
  if (fromRfq) {
    const rfqObj = await rfqStore.fetchOne(Number(fromRfq))
    if (rfqObj) {
      await store.loadFromRfq(rfqObj)
      if (!rfqObj.product_id) {
        store.error = 'Cette RFQ ne possède pas de Product canonique.'
        return
      }
      const loaded = await productsStore.fetchOne(rfqObj.product_id)
      if (loaded) store.currentProduct = loaded.product
    }
    store.leftTab = 'deal'
    return
  }

  // Opened from « Modèles de produits » (/pricer?modele=…&sousJacents=…&tenor=…):
  // the same mechanism as the RFQ deep link, the screen itself is unchanged.
  // An ephemeral session — nothing is kept without an explicit action.
  const model = findProductModel(route.query.modele)
  if (model) {
    await store.loadFromProductModel(model, {
      underlyingCount: route.query.sousJacents ? Number(route.query.sousJacents) : null,
      tenorCode: route.query.tenor || null,
    })
    store.leftTab = 'script'
  }
})

const leftTabs = [
  { id: 'script', label: '✏️ Script PayScript' },
  { id: 'economics', label: '💶 Economics' },
  { id: 'params', label: '⚙️ Marché & Paramètres' },
  { id: 'deal',   label: '📋 Deal' },
  { id: 'events', label: '📅 Events' },
]
const rightTabs = [
  { id: 'results',  label: '📊 Résultats' },
  { id: 'summary',  label: '📝 Résumé' },
  { id: 'flux',     label: '💰 Flux' },
  { id: 'greeks',   label: '∂ Greeks' },
  { id: 'profile',  label: '📈 Profil Payoff' },
  { id: 'paths',    label: '🔀 Chemins MC' },
  { id: 'proba',    label: '🎲 Probabilités' },
  { id: 'backtest', label: '📋 Backtest' },
  { id: 'mtf',      label: '🗺️ Mark to Future' },
  { id: 'simulation', label: '🧮 Simulation' },
  { id: 'scenarios', label: '🎯 Scénarios' },
  { id: 'variants',  label: '⑂ Déclinaisons' },
  { id: 'kid',       label: '⚖️ KID PRIIPs' },
  { id: 'emt',       label: '🎯 EMT / Marché cible' },
]
</script>
