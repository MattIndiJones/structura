<template>
  <div class="flex flex-col gap-4">
    <InLifeNotAlignedBanner />
    <!-- Sub-tabs -->
    <div class="flex gap-2">
      <button v-for="t in subTabs" :key="t.id"
        class="px-3 py-1.5 text-xs font-semibold rounded-lg border transition-colors"
        :class="subTab === t.id
          ? 'bg-blue-600 border-blue-500 text-white'
          : 'bg-slate-800 border-slate-700 text-slate-400 hover:text-slate-200'"
        @click="subTab = t.id">
        {{ t.label }}
      </button>
    </div>

    <ComparatorTab v-if="subTab === 'comparator'" />

    <template v-else>
    <!-- Header + controls -->
    <div class="card">
      <div class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-4">📋 Backtest MTF — Rejouer sur historique</div>
      <div class="grid grid-cols-2 sm:grid-cols-3 gap-3 text-xs mb-4">
        <div>
          <label class="label">Date de début
            <HelpTip text="Par défaut, tout l’historique Yahoo disponible est utilisé et conservé. La date locale affichée est provisoire : le début commun sera déterminé au lancement depuis les cours non ajustés de tous les titres. Une date saisie manuellement reste votre choix." />
          </label>
          <input v-model="form.start_date" type="date" class="input" aria-label="Date de début du backtest" @input="history.manualStart.value = true" />
          <button v-if="history.manualStart.value" class="text-xs underline mt-1" @click="history.useSuggestedStart">Utiliser le début commun</button>
        </div>
        <div>
          <label class="label">Date de fin
            <HelpTip text="Fin de l'historique chargé. Détermine la dernière fenêtre possible : il faut qu'il reste au moins T années d'historique après une date de départ pour que sa fenêtre soit exploitable." />
          </label>
          <input v-model="form.end_date" type="date" class="input" />
        </div>
        <div>
          <label class="label">Fréquence relance (j ouvrés)
            <HelpTip width="w-72" text="Pas entre deux dates de départ de fenêtre glissante — pas le pas d'observation du produit lui-même (ça, c'est AT 1,2,3 dans le script). Plus la fréquence est fine par rapport à la maturité du produit, plus les fenêtres voisines se recouvrent et partagent le même historique — leurs TRI ne sont alors plus des observations indépendantes, ce qui fausse à la hausse le Sharpe ci-dessous." />
          </label>
          <select v-model.number="form.freq" class="select">
            <option :value="1">Quotidien (1j)</option>
            <option :value="5">Hebdo (5j)</option>
            <option :value="21">Mensuel (21j)</option>
            <option :value="63">Trimestriel (63j)</option>
            <option :value="126">Semestriel (126j)</option>
          </select>
        </div>
        <div>
          <label class="label">Montant investi (%)
            <HelpTip text="Base du flux à t=0 (le -100% habituel) utilisée pour le calcul du TRI de chaque fenêtre. Modifier ceci change le TRI (effet de levier sur le flux d'entrée) mais pas les flux de sortie du produit lui-même." />
          </label>
          <SensitiveValue mode="input"><input v-model.number="form.invest_pct" type="number" step="10" min="10" max="200" class="input" /></SensitiveValue>
        </div>
        <div>
          <label class="label">Taux sans risque (%/an)
            <HelpTip text="Utilisé uniquement pour le Sharpe (TRI en excès du taux sans risque, divisé par l'écart-type des TRI) — n'affecte ni les flux ni le TRI de chaque fenêtre." />
          </label>
          <SensitiveValue mode="input"><input v-model.number="form.rf_rate" type="number" step="0.1" class="input" /></SensitiveValue>
        </div>
        <div>
          <label class="label">Cours absent
            <HelpTip text="Following recherche la prochaine date de cours valide commune au panier. Le décalage effectif et chaque titre concerné sont conservés avec le résultat. Strict refuse toute substitution nécessaire. Cette convention est propre au backtest." />
          </label>
          <select v-model="form.history_mode" class="select" aria-label="Convention des cours absents">
            <option value="following">Following — prochain cours commun</option>
            <option value="strict">Strict — aucun remplacement</option>
          </select>
        </div>
        <div>
          <label class="label">Décalage maximal (jours calendaires)</label>
          <input v-model.number="form.max_delay_days" type="number" min="0" max="31" step="1" class="input"
                 aria-label="Décalage maximal du backtest" :disabled="form.history_mode === 'strict'" />
        </div>
      </div>
      <p v-if="history.loading.value" class="text-xs mb-2" role="status">Recherche du début commun dans l’historique local…</p>
      <p v-else-if="history.error.value" class="text-xs text-amber-600 mb-2" role="status">{{ history.error.value }} Le début automatique pourra être déterminé au lancement.</p>
      <p v-else-if="!history.suggestedStart.value" class="text-xs text-slate-500 mb-2">Sans début commun local connu, laissez la date vide : elle sera déterminée au chargement de l’historique.</p>
      <p v-else class="text-xs text-slate-500 mb-2">Début commun local provisoire : {{ formatDate(history.suggestedStart.value) }}. Au lancement, recherche de l’historique maximal Yahoo et conservation pour les prochains calculs.</p>
      <p v-if="form.history_mode === 'following'" class="text-xs text-slate-500 mb-3">Une substitution décale la constatation et son paiement du même nombre de jours calendaires. Le résultat peut différer du contrat initial.</p>
      <div class="flex justify-end">
        <button class="btn-primary text-xs px-5" :disabled="store.loading || history.loading.value || !canRun" @click="launchBacktest">
          <span v-if="store.loading" class="w-3 h-3 border border-white border-t-transparent rounded-full animate-spin inline-block mr-1"></span>
          ▶ Lancer le backtest
        </button>
      </div>
      <div v-if="!canRun" class="text-xs text-amber-500 mt-2">
        Renseignez les tickers dans "Marché &amp; Paramètres" pour activer le backtest historique.
      </div>
    </div>

    <!-- Empty state -->
    <div v-if="!store.backtest" class="flex flex-col items-center justify-center h-52 text-slate-600 gap-2">
      <div class="text-3xl">📋</div>
      <div class="text-sm font-medium">Configurez les paramètres et lancez le backtest</div>
      <div class="text-xs">Prix Yahoo Finance réels · TRI calculé sur chaque fenêtre</div>
    </div>

    <BacktestResults v-else :result="store.backtest" />
    </template>
  </div>
</template>

<script setup>
import InLifeNotAlignedBanner from './InLifeNotAlignedBanner.vue'
import { ref, computed } from 'vue'
import { usePricingStore } from '../stores/pricing.js'
import ComparatorTab from './ComparatorTab.vue'
import HelpTip from './HelpTip.vue'
import SensitiveValue from './SensitiveValue.vue'
import BacktestResults from './BacktestResults.vue'
import { useBacktestHistory } from '../composables/useBacktestHistory.js'
import { formatDate } from '../utils/format.js'

const store = usePricingStore()
const subTab = ref('backtest')
const subTabs = [
  { id: 'backtest', label: '📋 Backtest' },
  { id: 'comparator', label: '🔎 Comparateur de sous-jacents' },
]
const today = new Date().toISOString().slice(0, 10)
const form = ref({
  start_date: '',
  end_date: today,
  freq: 21,
  invest_pct: 100,
  rf_rate: 2.0,
  history_mode: 'following',
  max_delay_days: 10,
})

const history = useBacktestHistory(store, form)
const canRun = computed(() => store.underlyings.length > 0 && store.underlyings.every(u => u.ticker?.trim()))

function launchBacktest() {
  store.runBacktest({ ...form.value, start_date: history.manualStart.value ? form.value.start_date : null })
}

</script>
