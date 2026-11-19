<template>
  <div class="text-sm font-bold text-slate-100">
    📉 VaR/ES — {{ pf.view === 'global' ? 'Tous portefeuilles' : pf.label }}
    <HelpTip width="w-80" text="Rejoue le book sous des centaines de scénarios de marché (historique ET paramétrique, affichés côte à côte, jamais fusionnés en un seul chiffre) via le module de calcul générique — asynchrone : rien ne s'exécute tant que le worker de calcul n'est pas démarré (voir l'avertissement ci-dessous)." />
  </div>

  <div class="text-xs text-amber-400 bg-amber-950/30 border border-amber-900/50 rounded-lg px-3 py-2">
    ⚠ Nécessite que <code class="font-mono">backend\scripts\run_compute_worker.py</code> tourne en parallèle du serveur — sinon l'étude reste "en attente" indéfiniment.
  </div>

  <div class="flex flex-wrap gap-3 items-end">
    <label class="flex flex-col gap-0.5 text-[10px] text-slate-500">Méthode
      <select v-model="varForm.method" class="select text-xs py-1 w-32">
        <option value="both">Les deux</option>
        <option value="historical">Historique</option>
        <option value="parametric">Paramétrique</option>
      </select>
    </label>
    <label class="flex flex-col gap-0.5 text-[10px] text-slate-500">Confiance
      <select v-model.number="varForm.confidence" class="select text-xs py-1 w-24">
        <option :value="0.95">95%</option>
        <option :value="0.99">99%</option>
        <option :value="0.90">90%</option>
      </select>
    </label>
    <label class="flex flex-col gap-0.5 text-[10px] text-slate-500">Horizon (j)
      <input v-model.number="varForm.horizon_days" type="number" min="1" class="input text-xs py-1 w-20" />
    </label>
    <label class="flex flex-col gap-0.5 text-[10px] text-slate-500">Lookback (ans)
      <input v-model.number="varForm.lookback_years" type="number" min="0.5" step="0.5" class="input text-xs py-1 w-20" />
    </label>
    <button class="text-[10px] text-slate-500 hover:text-slate-300 underline self-end pb-1"
      @click="varAdvancedOpen = !varAdvancedOpen">
      {{ varAdvancedOpen ? 'masquer' : 'options avancées' }}
    </button>
    <button class="btn-primary text-xs px-4 py-1.5 self-end" :disabled="calculationActive"
      @click="launchVarStudy">
      <span v-if="pf.varLaunching || pf.varPolling"
        class="w-3 h-3 border-2 border-white border-t-transparent rounded-full animate-spin inline-block mr-1"></span>
      Lancer l'étude
    </button>
  </div>

  <div v-if="varLaunchError" class="text-xs text-red-400 bg-red-950/30 border border-red-900/50 rounded-lg px-3 py-2">
    ⚠ {{ varLaunchError }}
  </div>

  <div v-if="varAdvancedOpen" class="flex flex-wrap gap-3">
    <label class="flex flex-col gap-0.5 text-[10px] text-slate-500">Tirages paramétriques
      <input v-model.number="varForm.n_parametric" type="number" min="100" step="100" class="input text-xs py-1 w-28" />
    </label>
    <label class="flex flex-col gap-0.5 text-[10px] text-slate-500">Paths / scénario
      <HelpTip text="Moins de précision par scénario qu'un choc unique (défaut du panneau Chocs : 20000) — le bruit se moyenne sur des centaines de scénarios, contrairement à un choc isolé où on veut la précision max." />
      <input v-model.number="varForm.n_paths_per_scenario" type="number" min="1000" step="500" class="input text-xs py-1 w-28" />
    </label>
    <label class="flex flex-col gap-0.5 text-[10px] text-slate-500">Workers parallèles
      <input v-model.number="varForm.max_workers" type="number" min="1" max="4" class="input text-xs py-1 w-20" />
    </label>
  </div>

  <template v-if="pf.varStudy">
    <p class="text-xs text-slate-400">Étude conservée : {{ riskScopeLabel(pf.varStudy.data_scope) }}.</p>
    <div v-if="pf.varStudy.status === 'queued' || pf.varStudy.status === 'running'"
      class="flex flex-col gap-1.5">
      <div class="text-xs text-slate-400">
        {{ pf.varStudy.status === 'queued' ? 'En file d\'attente…' : 'En cours…' }}
        {{ pf.varStudy.completed_jobs + pf.varStudy.failed_jobs }} / {{ pf.varStudy.total_jobs }} valorisation(s)
      </div>
      <div class="w-full h-1.5 bg-slate-800 rounded-full overflow-hidden">
        <div class="h-full bg-blue-500 transition-all"
          :style="{ width: (pf.varStudy.total_jobs ? (pf.varStudy.completed_jobs + pf.varStudy.failed_jobs) / pf.varStudy.total_jobs * 100 : 0) + '%' }"></div>
      </div>
    </div>

    <template v-else>
      <div v-if="pf.varStudy.result?.global_status === 'incomplete'"
        class="text-xs text-red-300 bg-red-950/30 border border-red-900/50 rounded-lg px-3 py-2">
        <div class="font-semibold">VaR du portefeuille demandé indisponible.</div>
        <div class="mt-1 text-red-300/80">
          Couverture {{ pf.varStudy.result.coverage?.included_deals ?? 0 }}/{{ pf.varStudy.result.coverage?.requested_deals ?? 0 }} deal(s).
          Aucune VaR ni aucun ES global n'est publié.
        </div>
      </div>

      <div v-if="varPublishedScope" class="text-xs text-slate-400">
        <span class="font-semibold text-slate-200">{{ varPublishedScopeLabel }}</span>
        <span v-if="pf.varStudy.result?.global_status === 'incomplete'">
          — univers fixe après exclusion de {{ varExcludedDeals.length }} deal(s) dans tous les scénarios.
        </span>
      </div>

      <div v-if="pf.varStudy.params?.market_data"
        class="text-[10px] text-slate-500 font-mono">
        Source : {{ pf.varStudy.params.market_data.provider === 'YAHOO_FINANCE'
          ? 'Yahoo Finance' : pf.varStudy.params.market_data.provider }} ·
        clôtures ajustées · date effective
        {{ pf.varStudy.params.market_data.asof_effective || 'indisponible' }}
        <span v-if="pf.varStudy.params.market_data.warnings?.length"
          class="text-amber-400"> · ⚠ données anciennes</span>
      </div>

      <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div v-for="m in ['historical', 'parametric']" :key="m" v-show="varPublishedScope?.[m]"
          class="card flex flex-col gap-2">
          <div class="text-xs font-bold text-slate-300 uppercase tracking-wider">
            {{ m === 'historical' ? 'Historique' : 'Paramétrique' }}
            <span class="text-slate-600 font-normal normal-case">— {{ varPublishedScope?.[m]?.n_scenarios }} scénario(s)</span>
          </div>
          <div class="grid grid-cols-2 gap-2">
            <div class="stat-box">
              <div class="text-xs text-slate-500 mb-1">VaR {{ Math.round((pf.varStudy.params.confidence ?? 0.95) * 100) }}%</div>
              <div class="text-lg font-bold font-mono text-red-400">{{ formatNominal(varPublishedScope?.[m]?.var_eur) }}</div>
              <div class="text-[10px] text-slate-600">EUR</div>
            </div>
            <div class="stat-box">
              <div class="text-xs text-slate-500 mb-1">Expected Shortfall
                <HelpTip text="Perte moyenne au-delà du seuil VaR — la queue au-delà du pire (confiance)%, pas juste le point de coupure." /></div>
              <div class="text-lg font-bold font-mono text-red-400">{{ formatNominal(varPublishedScope?.[m]?.es_eur) }}</div>
              <div class="text-[10px] text-slate-600">EUR</div>
            </div>
          </div>
          <div class="text-[10px] text-slate-500 font-mono flex flex-wrap gap-x-3">
            <span v-for="(v, p) in varPublishedScope?.[m]?.distribution_summary" :key="p">{{ p }}: {{ formatNominal(v) }}</span>
          </div>
        </div>
      </div>

      <div v-if="varPublishedScope?.worst_scenarios?.length" class="overflow-x-auto table-shell" tabindex="0" role="region">
        <div class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-1 mt-1">Pires scénarios</div>
        <table class="w-full text-xs border-collapse">
          <thead>
            <tr class="border-b border-slate-700 text-slate-500">
              <th class="text-left py-1.5 pr-3 font-semibold">Scénario</th>
              <th class="text-left py-1.5 pr-3 font-semibold">Méthode</th>
              <th class="text-right py-1.5 font-semibold">ΔMtM (EUR)</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="w in varPublishedScope.worst_scenarios" :key="w.scenario_key"
              class="border-b border-slate-800/50">
              <td class="py-1 pr-3 font-mono text-slate-300">{{ w.scenario_key }}</td>
              <td class="py-1 pr-3 text-slate-500">{{ w.method === 'historical' ? 'Historique' : 'Paramétrique' }}</td>
              <td class="py-1 text-right font-mono text-red-400">{{ formatNominal(w.delta_eur) }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div v-if="varExcludedDeals.length" class="text-xs text-slate-500 flex flex-col gap-1">
        <div class="font-semibold text-slate-400">Deals exclus du périmètre calculable</div>
        <div v-for="deal in varExcludedDeals" :key="`${deal.phase}-${deal.deal_id}`">
          <DealReferenceLink :deal-id="deal.deal_id" :reference="deal.reference"
                             class="font-mono text-blue-400" />
          — {{ deal.reason }}
        </div>
      </div>
    </template>
  </template>

  <!-- Études passées -->
  <div class="pt-2 border-t border-slate-800">
    <div class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-2">Études passées</div>
    <div v-if="!pf.varHistory.length" class="text-xs text-slate-500">Aucune étude VaR lancée pour l'instant.</div>
    <div v-else class="overflow-x-auto table-shell" tabindex="0" role="region">
      <table class="w-full text-xs border-collapse">
        <tbody>
          <tr v-for="b in pf.varHistory" :key="b.id" class="border-b border-slate-800/50 hover:bg-slate-800/20 cursor-pointer"
            @click="pf.openVarBatch(b.id)">
            <td class="py-1 pr-3 text-slate-500 whitespace-nowrap">{{ formatDateTime(runTimestamp(b.created_at)) }}</td>
            <td class="py-1 pr-3 text-slate-300">{{ b.label }} · {{ riskScopeLabel(b.data_scope) }}</td>
            <td class="py-1 pr-3 text-slate-500">{{ b.completed_jobs }}/{{ b.total_jobs }}</td>
            <td class="py-1 text-right"
              :class="{ completed: 'text-emerald-500', completed_with_failures: 'text-amber-500', failed: 'text-red-500', running: 'text-blue-400', queued: 'text-slate-500' }[b.status]">
              {{ b.status }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup>
// Extracted from RiskManagementView.vue (P1-10, U3). The state stays in the
// view; this panel reads it through useRiskContext().
import DealReferenceLink from '../../components/DealReferenceLink.vue'
import HelpTip from '../../components/HelpTip.vue'
import { formatDateTime } from '../../utils/format.js'
import { riskScopeLabel } from '../../utils/riskScope.js'
import { runTimestamp } from '../../composables/useBookingMtm.js'
import { useRiskContext } from './context.js'

const {
  calculationActive, formatNominal, launchVarStudy, pf, varAdvancedOpen, varExcludedDeals, varForm,
  varLaunchError, varPublishedScope, varPublishedScopeLabel,
} = useRiskContext()
</script>

<style scoped>
/* Keep every heading directly above its values, including nested detail tables. */

.risk-management-view table th,
.risk-management-view table td {
  text-align: center;
  vertical-align: middle;
}

.risk-management-view table td > .flex {
  justify-content: center;
}
</style>
