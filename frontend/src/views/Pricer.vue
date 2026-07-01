<template>
  <div class="min-h-screen flex flex-col bg-slate-950">

    <!-- ── Header ───────────────────────────────────────────────── -->
    <header class="border-b border-slate-800 px-5 py-3 flex items-center gap-4 bg-slate-950/95 backdrop-blur sticky top-0 z-20">
      <RouterLink to="/" class="flex items-center gap-2.5 shrink-0 hover:opacity-80 transition-opacity">
        <img src="/tp_logo.png" alt="TP Advisory" class="h-7 w-7 rounded-sm bg-white object-contain p-0.5">
        <span class="font-bold text-slate-100 tracking-tight">Structura</span>
        <span class="text-slate-600 text-xs hidden sm:block">— Pricing Engine</span>
      </RouterLink>

      <!-- Progress bar -->
      <div class="flex-1 min-w-0">
        <div v-if="store.progress > 0" class="h-1 bg-slate-800 rounded-full overflow-hidden">
          <div class="h-full bg-blue-500 rounded-full transition-all duration-100"
               :style="{ width: store.progress + '%' }"></div>
        </div>
        <div v-else-if="store.result" class="hidden sm:flex items-center gap-3 text-xs text-slate-500">
          <span class="text-blue-400 font-bold text-sm">
            <SensitiveValue>{{ (store.result.price * 100).toFixed(2) }}%</SensitiveValue>
          </span>
          <span>
            IC 95% [<SensitiveValue>{{ (store.result.ic95[0]*100).toFixed(2) }}%, {{ (store.result.ic95[1]*100).toFixed(2) }}%</SensitiveValue>]
          </span>
          <span v-if="!demo.linkedinMode" class="text-slate-600">
            <SensitiveValue>{{ store.result.elapsed_ms.toFixed(0) }} ms · {{ store.result.n_eff.toLocaleString() }} chemins</SensitiveValue>
          </span>
        </div>
        <!-- Error display -->
        <div v-if="store.error" class="text-xs text-red-400 truncate">⚠ {{ store.error }}</div>
      </div>

      <div class="flex items-center gap-2 shrink-0">
        <DemoModeToggle />
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
    </header>

    <!-- ── Main 2-col ──────────────────────────────────────────── -->
    <main class="flex-1 grid grid-cols-1 lg:grid-cols-2 gap-0 items-stretch">

      <!-- LEFT: Script + Params tabs -->
      <div class="border-r border-slate-800 flex flex-col">
        <div class="flex border-b border-slate-800 bg-slate-900/50">
          <button
            v-for="tab in leftTabs" :key="tab.id"
            class="px-5 py-3 text-sm font-semibold transition-colors border-b-2 -mb-px"
            :class="store.leftTab === tab.id
              ? 'text-blue-400 border-blue-500'
              : 'text-slate-500 border-transparent hover:text-slate-300'"
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
        <div class="flex border-b border-slate-800 bg-slate-900/50 overflow-x-auto">
          <button
            v-for="tab in rightTabs" :key="tab.id"
            class="px-4 py-3 text-xs font-semibold transition-colors border-b-2 -mb-px whitespace-nowrap"
            :class="store.rightTab === tab.id
              ? 'text-blue-400 border-blue-500'
              : 'text-slate-500 border-transparent hover:text-slate-300'"
            @click="store.rightTab = tab.id">
            {{ tab.label }}
          </button>
        </div>
        <div class="flex-1 overflow-y-auto p-5">
          <ResultsPanel v-show="store.rightTab !== 'kid'" />
          <KidPanel     v-if="store.rightTab === 'kid'" />
        </div>
      </div>
    </main>
  </div>
</template>

<script setup>
import { RouterLink } from 'vue-router'
import PayScriptEditor from '../components/PayScriptEditor.vue'
import MarketParams    from '../components/MarketParams.vue'
import DealTab         from '../components/DealTab.vue'
import EventsTab       from '../components/EventsTab.vue'
import ResultsPanel    from '../components/ResultsPanel.vue'
import KidPanel        from '../components/KidPanel.vue'
import SensitiveValue  from '../components/SensitiveValue.vue'
import DemoModeToggle  from '../components/DemoModeToggle.vue'
import { ref } from 'vue'
import { usePricingStore } from '../stores/pricing.js'
import { useDemoModeStore } from '../stores/demoMode.js'

const store = usePricingStore()
const demo = useDemoModeStore()

const eventsInitialDealId = ref(null)

function goToEvents(dealId) {
  eventsInitialDealId.value = dealId
  store.leftTab = 'events'
}

const leftTabs = [
  { id: 'script', label: '✏️ Script PayScript' },
  { id: 'params', label: '⚙️ Marché & Paramètres' },
  { id: 'deal',   label: '📋 Deal' },
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
]
</script>
