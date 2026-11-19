<template>
  <div class="text-sm font-bold text-slate-100">
    ⚡ Choc — {{ pf.view === 'global' ? 'Tous portefeuilles' : pf.label }}
    <HelpTip width="w-72" text="Full reprice Monte Carlo sous le scénario choqué, deal par deal — pas une approximation par les Greeks (les payoffs à barrière sont trop non-linéaires pour ça). Chaque run est conservé en historique." />
  </div>

  <div class="flex items-center gap-2">
    <select class="select text-xs py-1.5" @change="applyShockPreset($event.target.value)">
      <option value="">Preset…</option>
      <option v-for="p in shockPresets" :key="p.label" :value="p.label">{{ p.label }}</option>
    </select>
  </div>
  <div class="flex flex-wrap gap-3">
    <label class="flex flex-col gap-0.5 text-[10px] text-slate-500">Spot %
      <input v-model.number="shockForm.spot_shock_pct" type="number" step="1" class="input text-xs py-1 w-24" />
    </label>
    <label class="flex flex-col gap-0.5 text-[10px] text-slate-500">Vol (pts)
      <input v-model.number="shockForm.vol_shock_pts" type="number" step="1" class="input text-xs py-1 w-24" />
    </label>
    <label class="flex flex-col gap-0.5 text-[10px] text-slate-500">Taux (bp)
      <input v-model.number="shockForm.rate_shock_bp" type="number" step="10" class="input text-xs py-1 w-24" />
    </label>
    <label class="flex flex-col gap-0.5 text-[10px] text-slate-500">Corr (pts)
      <input v-model.number="shockForm.corr_shock_pts" type="number" step="5" class="input text-xs py-1 w-24" />
    </label>
    <button class="btn-primary text-xs px-4 py-1.5 self-end" :disabled="calculationActive"
      @click="runPortfolioShock">
      <span v-if="shockLoading"
        class="w-3 h-3 border-2 border-white border-t-transparent rounded-full animate-spin inline-block mr-1"></span>
      Lancer le choc
    </button>
  </div>

  <template v-if="shockResult">
    <div v-if="shockResult.error" class="text-xs text-amber-400">⚠ {{ shockResult.error }}</div>
    <template v-else>
      <div class="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div class="stat-box">
          <div class="text-xs text-slate-500 mb-1">ΔMtM total</div>
          <div class="text-lg font-bold font-mono" :class="shockResult.total_delta_eur >= 0 ? 'text-emerald-400' : 'text-red-400'">
            {{ formatNominal(shockResult.total_delta_eur) }}
          </div>
          <div class="text-[10px] text-slate-600">EUR</div>
        </div>
        <div class="stat-box">
          <div class="text-xs text-slate-500 mb-1">Impact / nominal
            <HelpTip text="ΔMtM total ÷ nominal total (EUR) du périmètre choqué — même dénominateur que la tuile Nominal total du sous-onglet Greeks (inclut les deals ignorés/en erreur, pas seulement ceux effectivement repricés)." /></div>
          <div class="text-lg font-bold font-mono" :class="(shockResult.pct_impact ?? 0) >= 0 ? 'text-emerald-400' : 'text-red-400'">
            {{ shockResult.pct_impact != null ? shockResult.pct_impact.toFixed(2) + '%' : '—' }}
          </div>
          <div class="text-[10px] text-slate-600">vs {{ formatNominal(shockResult.nominal_total_eur) }} EUR</div>
        </div>
        <div class="stat-box">
          <div class="text-xs text-slate-500 mb-1">Deals choqués</div>
          <div class="text-lg font-bold font-mono text-slate-200">{{ shockResult.contributions.length }}</div>
        </div>
        <div class="stat-box">
          <div class="text-xs text-slate-500 mb-1">Ignorés / erreurs</div>
          <div class="text-lg font-bold font-mono text-slate-200">
            {{ shockResult.skipped.length }} / {{ shockResult.errors.length }}
          </div>
        </div>
      </div>

      <div v-if="shockResult.skipped.length || shockResult.errors.length"
        class="text-xs text-amber-400 bg-amber-950/30 border border-amber-900/50 rounded-lg px-3 py-2">
        ⚠ {{ [...shockResult.skipped.map(s => s.reference), ...shockResult.errors.map(e => e.reference)].join(', ') }}
        — deal(s) non choqués (résolution en attente ou erreur de pricing)
      </div>

      <div class="overflow-x-auto table-shell" tabindex="0" role="region">
        <table class="w-full text-xs border-collapse">
          <thead>
            <tr class="border-b border-slate-700 text-slate-500">
              <th class="text-left py-1.5 pr-3 font-semibold">Deal</th>
              <th class="text-right py-1.5 pr-3 font-semibold num">MtM avant</th>
              <th class="text-right py-1.5 pr-3 font-semibold num">MtM après</th>
              <th class="text-right py-1.5 font-semibold num">ΔMtM (EUR)</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="c in shockResult.contributions" :key="c.deal_id"
              class="border-b border-slate-800/50 hover:bg-slate-800/20 transition-colors cursor-pointer"
              @click="openDealDetail(c.deal_id)">
              <td class="py-1.5 pr-3 font-mono font-semibold text-blue-400"><DealReferenceLink :deal-id="c.deal_id" :reference="c.reference" /></td>
              <td class="py-1.5 pr-3 text-right font-mono text-slate-400">{{ (c.mtm_before * 100).toFixed(2) }}%</td>
              <td class="py-1.5 pr-3 text-right font-mono text-slate-400">{{ (c.mtm_after * 100).toFixed(2) }}%</td>
              <td class="py-1.5 text-right font-mono" :class="c.delta_eur >= 0 ? 'text-emerald-400' : 'text-red-400'">
                {{ formatNominal(c.delta_eur) }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
  </template>

  <!-- Historique -->
  <div class="pt-2 border-t border-slate-800">
    <div class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-2">Historique · {{ pf.historyLabel }}</div>
    <div v-if="!pf.currentShockHistory.length" class="text-xs text-slate-500">Aucun choc joué sur cette sélection.</div>
    <div v-else class="overflow-x-auto table-shell" tabindex="0" role="region">
    <table class="w-full text-xs border-collapse">
      <tbody>
        <tr v-for="h in pf.currentShockHistory" :key="h.id" class="border-b border-slate-800/50">
          <td class="py-1 pr-3 text-slate-500 whitespace-nowrap">{{ formatDateTime(runTimestamp(h.created_at)) }}</td>
          <td class="py-1 pr-3 text-slate-300">{{ h.label }} · {{ riskScopeLabel(h.data_scope) }} · {{ h.params?.portfolio_name || h.scope }}</td>
          <td class="py-1 pr-3 text-right font-mono" :class="(h.result.total_delta_eur ?? 0) >= 0 ? 'text-emerald-500' : 'text-red-500'">
            {{ formatNominal(h.result.total_delta_eur) }} EUR
          </td>
          <td class="py-1 text-right font-mono" :class="(h.result.pct_impact ?? 0) >= 0 ? 'text-emerald-500' : 'text-red-500'">
            {{ h.result.pct_impact != null ? h.result.pct_impact.toFixed(2) + '%' : '—' }}
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
import { shockPresets } from '../../stores/portfolios.js'
import { useRiskContext } from './context.js'

const {
  applyShockPreset, calculationActive, formatNominal, openDealDetail, pf, runPortfolioShock,
  shockForm, shockLoading, shockResult,
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
