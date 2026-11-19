<template>
  <div class="text-sm font-bold text-slate-100">
    P&L explain — {{ pf.view === 'global' ? 'Tous portefeuilles' : pf.label }}
    <HelpTip width="w-72" text="Waterfall temps et état réalisé / spot / dividendes / volatilité / corrélation entre deux dates, calculé deal par deal à graine identique puis agrégé en EUR sur la sélection. Comptez plusieurs secondes par deal." />
  </div>

  <div class="flex flex-wrap gap-3 items-end">
    <label class="flex flex-col gap-0.5 text-[10px] text-slate-500">Date 1
      <input v-model="pnlD1" type="date" class="input text-xs py-1"
        title="Vide = chaque deal part de sa propre date de valeur (P&L depuis l'origine)" />
    </label>
    <label class="flex flex-col gap-0.5 text-[10px] text-slate-500">Date 2
      <input v-model="pnlD2" type="date" class="input text-xs py-1" />
    </label>
    <button class="btn-primary text-xs px-4 py-1.5" :disabled="calculationActive || !pf.members.length"
      @click="runPnl">
      <span v-if="pnlLoading"
        class="w-3 h-3 border-2 border-white border-t-transparent rounded-full animate-spin inline-block mr-1"></span>
      {{ pnlLoading ? 'Calcul en cours…' : 'Expliquer le P&L' }}
    </button>
    <span v-if="pnlLoading" class="text-[10px] text-slate-500">
      Full reprice × {{ pf.members.length }} deal(s) — cela peut prendre plusieurs minutes.
    </span>
  </div>

  <template v-if="pnlResult">
    <div v-if="pnlResult.error" class="text-xs text-amber-400">⚠ {{ pnlResult.error }}</div>
    <template v-else>
      <div class="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div class="stat-box">
          <div class="text-xs text-slate-500 mb-1">P&L total
            <HelpTip text="Variation de valeur (ΔMtM) + cash contractuel à échéance sur la période, en EUR, sommés sur les deals expliqués. Les dates contractuelles ne prouvent pas un virement bancaire." /></div>
          <div class="text-lg font-bold font-mono" :class="pnlResult.pnl_total_eur >= 0 ? 'text-emerald-400' : 'text-red-400'">
            {{ formatNominal(pnlResult.pnl_total_eur) }}
          </div>
          <div class="text-[10px] text-slate-600">EUR</div>
        </div>
        <div class="stat-box">
          <div class="text-xs text-slate-500 mb-1">ΔMtM / Flux</div>
          <div class="text-sm font-bold font-mono text-slate-200">
            {{ formatNominal(pnlResult.delta_mtm_eur) }} / {{ formatNominal(pnlResult.flows_total_eur) }}
          </div>
          <div class="text-[10px] text-slate-600">EUR</div>
        </div>
        <div class="stat-box">
          <div class="text-xs text-slate-500 mb-1">P&L / nominal
            <HelpTip text="P&L total ÷ nominal total (EUR) de la sélection — le nominal inclut aussi les deals ignorés/en erreur, même dénominateur que les tuiles Risque et Chocs." /></div>
          <div class="text-lg font-bold font-mono" :class="(pnlResult.pct_impact ?? 0) >= 0 ? 'text-emerald-400' : 'text-red-400'">
            {{ pnlResult.pct_impact != null ? pnlResult.pct_impact.toFixed(2) + '%' : '—' }}
          </div>
          <div class="text-[10px] text-slate-600">vs {{ formatNominal(pnlResult.nominal_total_eur) }} EUR</div>
        </div>
        <div class="stat-box">
          <div class="text-xs text-slate-500 mb-1">Expliqués / ignorés / erreurs</div>
          <div class="text-lg font-bold font-mono text-slate-200">
            {{ pnlResult.contributions.length }} / {{ pnlResult.skipped.length }} / {{ pnlResult.errors.length }}
          </div>
        </div>
      </div>

      <div v-if="pnlResult.skipped.length || pnlResult.errors.length"
        class="text-xs text-amber-400 bg-amber-950/30 border border-amber-900/50 rounded-lg px-3 py-2">
        ⚠ Deal(s) non expliqués :
        <span v-for="(s, i) in [...pnlResult.skipped, ...pnlResult.errors]" :key="s.deal_id">
          {{ i > 0 ? ' · ' : '' }}<DealReferenceLink :deal-id="s.deal_id"
            :reference="s.reference" class="font-mono text-blue-400" /> <span class="text-amber-600">({{ s.reason || s.error }})</span>
        </span>
      </div>

      <!-- Waterfall agrégé -->
      <div class="overflow-x-auto table-shell" tabindex="0" role="region">
        <table class="w-full text-xs border-collapse max-w-xl">
          <tbody>
            <tr v-for="st in pnlResult.steps" :key="st.key" class="border-b border-slate-800/50">
              <td class="py-1.5 pr-3 text-slate-300">{{ st.label }}</td>
              <td class="py-1.5 text-right font-mono" :class="st.delta_eur >= 0 ? 'text-emerald-400' : 'text-red-400'">
                {{ formatNominal(st.delta_eur) }} EUR
              </td>
            </tr>
            <tr class="border-b border-slate-800/50">
              <td class="py-1.5 pr-3 text-slate-500">Résidu
                <HelpTip text="Ce qui échappe à la chaîne temps/état, spot, dividendes, volatilité et corrélation reste non attribué. Un résidu élevé signale un facteur non capturé." /></td>
              <td class="py-1.5 text-right font-mono text-slate-400">{{ formatNominal(pnlResult.residual_eur) }} EUR</td>
            </tr>
            <tr class="border-b border-slate-800/50">
              <td class="py-1.5 pr-3 text-slate-500">{{ pnlResult.cash_basis === 'CONTRACTUAL_PAYMENT_DATE' ? 'Cash contractuel à échéance' : 'Flux détachés — ancien calcul' }}</td>
              <td class="py-1.5 text-right font-mono text-slate-400">{{ formatNominal(pnlResult.flows_total_eur) }} EUR</td>
            </tr>
            <tr>
              <td class="py-1.5 pr-3 font-bold text-slate-200">P&L total</td>
              <td class="py-1.5 text-right font-mono font-bold" :class="pnlResult.pnl_total_eur >= 0 ? 'text-emerald-400' : 'text-red-400'">
                {{ formatNominal(pnlResult.pnl_total_eur) }} EUR
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Contributions par deal -->
      <p v-if="pnlResult.cash_basis === 'CONTRACTUAL_PAYMENT_DATE'" class="text-[10px] text-slate-500">
        Cash selon les dates contractuelles de paiement sur ]date 1, date 2] ; aucune preuve de virement bancaire.
      </p>
      <div class="overflow-x-auto table-shell" tabindex="0" role="region">
        <table class="w-full text-xs border-collapse">
          <thead>
            <tr class="border-b border-slate-700 text-slate-500">
              <th class="text-left py-1.5 pr-3 font-semibold">Deal</th>
              <th class="text-left py-1.5 pr-3 font-semibold">Période</th>
              <th class="text-right py-1.5 pr-3 font-semibold num">Temps</th>
              <th class="text-right py-1.5 pr-3 font-semibold num">Spot</th>
              <th class="text-right py-1.5 pr-3 font-semibold num">Vol</th>
              <th v-if="pnlHasCorr" class="text-right py-1.5 pr-3 font-semibold num">Corr</th>
              <th class="text-right py-1.5 pr-3 font-semibold num">Flux</th>
              <th class="text-right py-1.5 font-semibold num">P&L (EUR)</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="c in pnlResult.contributions" :key="c.deal_id"
              class="border-b border-slate-800/50 hover:bg-slate-800/20 transition-colors cursor-pointer"
              @click="openDealDetail(c.deal_id)">
              <td class="py-1.5 pr-3 font-mono font-semibold text-blue-400"><DealReferenceLink :deal-id="c.deal_id" :reference="c.reference" /></td>
              <td class="py-1.5 pr-3 text-slate-500 whitespace-nowrap">{{ c.date1 }} → {{ c.date2 }}</td>
              <td class="py-1.5 pr-3 text-right font-mono text-slate-400">{{ formatNominal(c.steps_eur.temps ?? 0) }}</td>
              <td class="py-1.5 pr-3 text-right font-mono text-slate-400">{{ formatNominal(c.steps_eur.spot ?? 0) }}</td>
              <td class="py-1.5 pr-3 text-right font-mono text-slate-400">{{ formatNominal(c.steps_eur.vol ?? 0) }}</td>
              <td v-if="pnlHasCorr" class="py-1.5 pr-3 text-right font-mono text-slate-400">{{ formatNominal(c.steps_eur.corr ?? 0) }}</td>
              <td class="py-1.5 pr-3 text-right font-mono text-slate-400">{{ formatNominal(c.flows_eur) }}</td>
              <td class="py-1.5 text-right font-mono" :class="c.pnl_eur >= 0 ? 'text-emerald-400' : 'text-red-400'">
                {{ formatNominal(c.pnl_eur) }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
  </template>
</template>

<script setup>
// Extracted from RiskManagementView.vue (P1-10, U3). The state stays in the
// view; this panel reads it through useRiskContext().
import DealReferenceLink from '../../components/DealReferenceLink.vue'
import HelpTip from '../../components/HelpTip.vue'
import { useRiskContext } from './context.js'

const {
  calculationActive, formatNominal, openDealDetail, pf, pnlD1, pnlD2, pnlHasCorr, pnlLoading,
  pnlResult, runPnl,
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
