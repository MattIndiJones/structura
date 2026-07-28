<template>
  <div class="flex-1 flex flex-col min-h-0">

    <!-- ── Barre d'outils : statut de pricing + actions ─────────── -->
    <div class="sticky top-0 z-30 border-b px-5 py-2.5 flex items-center gap-4 shrink-0"
         style="background: rgba(255,255,255,.95); backdrop-filter: blur(6px); border-color: var(--border);">

      <RouterLink :to="{ path: '/', query: { category: 'pricing' } }" class="btn-secondary text-xs px-3 py-1.5 shrink-0">← Retour</RouterLink>

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
      </div>

      <div class="flex items-center gap-2 shrink-0">
        <button v-if="store.result && store.selectedGreeks.length > 0"
          class="btn-secondary text-xs px-3 py-1.5"
          :disabled="store.loading"
          @click="store.runGreeks()">
          ∂ Greeks
        </button>
        <button
          class="btn-primary flex items-center gap-2 text-sm"
          :disabled="store.loading || !!store.parseError"
          @click="store.runPricing()">
          <span v-if="store.loading" class="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin"></span>
          {{ store.loading ? 'Calcul…' : '▶ Pricer' }}
        </button>
      </div>
    </div>

    <!-- ── Main 2-col ──────────────────────────────────────────── -->
    <main class="flex-1 min-h-0 grid grid-cols-1 lg:grid-cols-2 gap-0 items-stretch">

      <!-- LEFT: Script + Params tabs -->
      <div class="border-r border-slate-800 flex flex-col">
        <div class="flex gap-1 border-b border-slate-800 bg-slate-900/50 px-2 py-1.5">
          <button
            v-for="tab in leftTabs" :key="tab.id"
            class="tab-btn" :class="{ active: store.leftTab === tab.id }"
            @click="store.leftTab = tab.id">
            {{ tab.label }}
          </button>
        </div>
        <div class="flex-1 overflow-y-auto p-5 flex flex-col gap-5">
          <PayScriptEditor v-show="store.leftTab === 'script'" />
          <MarketParams    v-show="store.leftTab === 'params'" />
          <DealTab         v-if="store.leftTab === 'deal'" @go-events="goToEvents" />
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
import PayScriptEditor from '../components/PayScriptEditor.vue'
import MarketParams    from '../components/MarketParams.vue'
import DealTab         from '../components/DealTab.vue'
import EventsTab       from '../components/EventsTab.vue'
import ResultsPanel    from '../components/ResultsPanel.vue'
import KidPanel        from '../components/KidPanel.vue'
import EmtPanel        from '../components/EmtPanel.vue'
import SensitiveValue  from '../components/SensitiveValue.vue'
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { usePricingStore } from '../stores/pricing.js'
import { useDealsStore } from '../stores/deals.js'
import { useDemoModeStore } from '../stores/demoMode.js'

const store = usePricingStore()
const dealsStore = useDealsStore()
const demo = useDemoModeStore()
const route = useRoute()

const eventsInitialDealId = ref(null)

function goToEvents(dealId) {
  eventsInitialDealId.value = dealId
  store.leftTab = 'events'
}

// Deep link from the Booking view (/pricer?dealId=…) — reload that deal's
// exact frozen state (script + params + underlyings) into every tab, not
// just Events, then jump straight there instead of landing on Script.
onMounted(async () => {
  const dealId = route.query.dealId
  if (!dealId) return
  const deal = await dealsStore.selectDeal(Number(dealId))
  if (deal) await store.loadFromDeal(deal)
  goToEvents(Number(dealId))
})

const leftTabs = [
  { id: 'script', label: '✏️ Script PayScript' },
  { id: 'deal',   label: '📋 Deal' },
  { id: 'params', label: '⚙️ Marché & Paramètres' },
  { id: 'events', label: '📅 Events' },
]
const rightTabs = [
  { id: 'results',  label: '📊 Résultats' },
  { id: 'flux',     label: '💰 Flux' },
  { id: 'greeks',   label: '∂ Greeks' },
  { id: 'profile',  label: '📈 Profil Payoff' },
  { id: 'paths',    label: '🔀 Chemins MC' },
  { id: 'proba',    label: '🎲 Probabilités' },
  { id: 'backtest', label: '📋 Backtest' },
  { id: 'mtf',      label: '🗺️ Mark to Future' },
  { id: 'simulation', label: '🧮 Simulation' },
  { id: 'scenarios', label: '🎯 Scénarios' },
  { id: 'kid',       label: '⚖️ KID PRIIPs' },
  { id: 'emt',       label: '🎯 EMT / Marché cible' },
]
</script>
