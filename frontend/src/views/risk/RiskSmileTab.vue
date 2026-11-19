<template>
  <div class="flex flex-col gap-1">
    <div class="text-sm font-bold text-slate-100">
      〰 Risque de smile — {{ pf.view === 'global' ? 'Tous les deals actifs' : pf.label }}
    </div>
    <div class="text-[10px] text-slate-500 max-w-4xl">
      Repricing complet avec les mêmes termes, la même date de valorisation et le même marché de base.
      Les paramètres restent propres au modèle : σ/skew/courbure pour Local Vol, α/ρ/ν pour SABR,
      v0/θ/ρ/ξ pour Heston. Aucun mapping implicite n’est appliqué entre ces modèles.
    </div>
  </div>

  <div class="grid grid-cols-1 lg:grid-cols-3 gap-3">
    <div class="rounded-lg border border-slate-800 p-3 flex flex-col gap-2">
      <div class="text-xs font-semibold text-slate-300">Surface locale</div>
      <div class="grid grid-cols-3 gap-2">
        <label class="text-[10px] text-slate-500">ATM (pts)
          <input v-model.number="smileForm.atm_vol_pts" type="number" step="1" class="input mt-1 w-full text-xs" />
        </label>
        <label class="text-[10px] text-slate-500">Skew (pts)
          <input v-model.number="smileForm.skew_pts" type="number" step="1" class="input mt-1 w-full text-xs" />
        </label>
        <label class="text-[10px] text-slate-500">Courbure (pts)
          <input v-model.number="smileForm.curvature_pts" type="number" step="1" class="input mt-1 w-full text-xs" />
        </label>
      </div>
      <div class="text-[9px] text-slate-600">ATM : modèles constants et Local Vol · skew/courbure : Local Vol et LSV.</div>
    </div>

    <div class="rounded-lg border border-slate-800 p-3 flex flex-col gap-2">
      <div class="text-xs font-semibold text-slate-300">SABR natif</div>
      <div class="grid grid-cols-3 gap-2">
        <label class="text-[10px] text-slate-500">α (pts)
          <input v-model.number="smileForm.sabr_alpha_pts" type="number" step="1" class="input mt-1 w-full text-xs" />
        </label>
        <label class="text-[10px] text-slate-500">ρ (pts)
          <input v-model.number="smileForm.sabr_rho_pts" type="number" step="1" class="input mt-1 w-full text-xs" />
        </label>
        <label class="text-[10px] text-slate-500">ν (pts)
          <input v-model.number="smileForm.sabr_nu_pts" type="number" step="1" class="input mt-1 w-full text-xs" />
        </label>
      </div>
    </div>

    <div class="rounded-lg border border-slate-800 p-3 flex flex-col gap-2">
      <div class="text-xs font-semibold text-slate-300">Heston / LSV natif</div>
      <div class="grid grid-cols-4 gap-2">
        <label class="text-[10px] text-slate-500">v0 (pts)
          <input v-model.number="smileForm.heston_v0_pts" type="number" step="1" class="input mt-1 w-full text-xs" />
        </label>
        <label class="text-[10px] text-slate-500">θ (pts)
          <input v-model.number="smileForm.heston_theta_pts" type="number" step="1" class="input mt-1 w-full text-xs" />
        </label>
        <label class="text-[10px] text-slate-500">ρ (pts)
          <input v-model.number="smileForm.heston_rho_pts" type="number" step="1" class="input mt-1 w-full text-xs" />
        </label>
        <label class="text-[10px] text-slate-500">ξ (pts)
          <input v-model.number="smileForm.heston_xi_pts" type="number" step="1" class="input mt-1 w-full text-xs" />
        </label>
      </div>
    </div>
  </div>

  <div class="flex items-center gap-3 flex-wrap">
    <label class="text-[10px] text-slate-500">Sous-jacent ciblé
      <select v-model="smileTarget" class="select ml-2 text-xs min-w-48">
        <option value="all">Tous les sous-jacents</option>
        <option v-for="u in smileUnderlyings" :key="u.key" :value="u.key">
          {{ u.label }}
        </option>
      </select>
    </label>
    <label class="text-[10px] text-slate-500">Nom du scénario
      <input v-model="smileForm.label" type="text" placeholder="Ex. Stress skew actions" class="input ml-2 text-xs w-56" />
    </label>
    <button class="btn-primary text-xs px-4 py-1.5 ml-auto"
      :disabled="calculationActive || !pf.members.length || !smileHasShock"
      @click="runSmile">
      <span v-if="pf.smileLoading"
        class="w-3 h-3 border-2 border-white/60 border-t-transparent rounded-full animate-spin inline-block mr-1"></span>
      Repricer le smile
    </button>
  </div>

  <AlertMessage v-if="smileError" kind="error" dismissible @dismiss="smileError = ''">
    {{ smileError }}
  </AlertMessage>

  <template v-if="pf.smileResult">
    <div class="grid grid-cols-2 sm:grid-cols-4 gap-3">
      <div class="stat-box">
        <div class="text-xs text-slate-500 mb-1">Impact total</div>
        <div class="text-lg font-bold font-mono" :class="pf.smileResult.total_delta_eur >= 0 ? 'text-emerald-400' : 'text-red-400'">
          {{ formatNominal(pf.smileResult.total_delta_eur) }} EUR
        </div>
      </div>
      <div class="stat-box">
        <div class="text-xs text-slate-500 mb-1">Impact / nominal</div>
        <div class="text-lg font-bold font-mono text-slate-200">{{ pf.smileResult.pct_impact ?? '—' }}%</div>
      </div>
      <div class="stat-box">
        <div class="text-xs text-slate-500 mb-1">Couverture repricée</div>
        <div class="text-lg font-bold font-mono text-blue-300">{{ pf.smileResult.coverage_pct ?? '—' }}%</div>
      </div>
      <div class="stat-box">
        <div class="text-xs text-slate-500 mb-1">Deals repricés</div>
        <div class="text-lg font-bold font-mono text-slate-200">{{ pf.smileResult.contributions.length }}</div>
      </div>
    </div>

    <div v-if="pf.smileResult.skipped.length || pf.smileResult.errors.length"
      class="text-xs text-amber-400 bg-amber-950/30 border border-amber-900/50 rounded-lg px-3 py-2">
      {{ pf.smileResult.skipped.length }} non applicable(s) · {{ pf.smileResult.errors.length }} erreur(s).
      <span v-for="row in pf.smileResult.skipped" :key="`skip-${row.deal_id}`" class="block mt-1">
        <DealReferenceLink :deal-id="row.deal_id" :reference="row.reference"
                           class="font-mono text-blue-400" /> — {{ row.reason }}
      </span>
      <span v-for="row in pf.smileResult.errors" :key="`err-${row.deal_id}`" class="block mt-1">
        <DealReferenceLink :deal-id="row.deal_id" :reference="row.reference"
                           class="font-mono text-blue-400" /> — {{ row.error }}
      </span>
    </div>

    <div v-if="pf.smileResult.contributions.length" class="overflow-x-auto table-shell" tabindex="0" role="region">
      <table class="w-full text-xs border-collapse">
        <thead>
          <tr class="border-b border-slate-700 text-slate-500">
            <th class="text-left py-1.5 pr-3 font-semibold">Deal</th>
            <th class="text-left py-1.5 pr-3 font-semibold">Modèle</th>
            <th class="text-left py-1.5 pr-3 font-semibold">Paramètres déplacés</th>
            <th class="text-right py-1.5 pr-3 font-semibold">Avant</th>
            <th class="text-right py-1.5 pr-3 font-semibold">Après</th>
            <th class="text-right py-1.5 font-semibold">Impact EUR</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in pf.smileResult.contributions" :key="row.deal_id"
            class="border-b border-slate-800/50 hover:bg-slate-800/20 cursor-pointer"
            @click="openDealDetail(row.deal_id)">
            <td class="py-2 pr-3 font-mono font-semibold text-blue-400"><DealReferenceLink :deal-id="row.deal_id" :reference="row.reference" /></td>
            <td class="py-2 pr-3 uppercase text-[10px] text-slate-400">{{ row.model }}</td>
            <td class="py-2 pr-3 text-[10px] text-slate-400">
              <span v-for="u in row.parameter_changes" :key="u.ticker || u.name" class="block">
                {{ u.ticker || u.name }} : {{ u.changes.map(c => `${c.parameter} ${c.shift_pts > 0 ? '+' : ''}${c.shift_pts}pt`).join(', ') }}
              </span>
            </td>
            <td class="py-2 pr-3 text-right font-mono text-slate-400">{{ Number(row.mtm_before).toFixed(3) }}</td>
            <td class="py-2 pr-3 text-right font-mono text-slate-300">{{ Number(row.mtm_after).toFixed(3) }}</td>
            <td class="py-2 text-right font-mono font-semibold" :class="row.delta_eur >= 0 ? 'text-emerald-400' : 'text-red-400'">
              {{ formatNominal(row.delta_eur) }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </template>

  <div v-if="pf.currentSmileHistory.length" class="pt-2 border-t border-slate-800">
    <div class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-2">Historique des scénarios</div>
    <div class="grid grid-cols-1 md:grid-cols-2 gap-2">
      <div v-for="run in pf.currentSmileHistory" :key="run.id"
        class="rounded-lg border border-slate-800 px-3 py-2 flex items-center gap-3">
        <div class="min-w-0 flex-1">
          <div class="text-xs text-slate-300 truncate">{{ run.label }} · {{ riskScopeLabel(run.data_scope) }} · {{ run.params?.portfolio_name || run.scope }}</div>
          <div class="text-[9px] text-slate-600">{{ formatDateTime(runTimestamp(run.created_at)) }}</div>
        </div>
        <div class="font-mono text-xs font-semibold"
          :class="run.result.total_delta_eur >= 0 ? 'text-emerald-400' : 'text-red-400'">
          {{ formatNominal(run.result.total_delta_eur) }} EUR
        </div>
        <div class="font-mono text-[10px] text-slate-500">{{ run.result.coverage_pct ?? '—' }}%</div>
      </div>
    </div>
  </div>
</template>

<script setup>
// Extracted from RiskManagementView.vue (P1-10, U3). The state stays in the
// view; this panel reads it through useRiskContext().
import AlertMessage from '../../components/ui/AlertMessage.vue'
import DealReferenceLink from '../../components/DealReferenceLink.vue'
import { formatDateTime } from '../../utils/format.js'
import { riskScopeLabel } from '../../utils/riskScope.js'
import { runTimestamp } from '../../composables/useBookingMtm.js'
import { useRiskContext } from './context.js'

const {
  calculationActive, formatNominal, openDealDetail, pf, runSmile, smileError, smileForm,
  smileHasShock, smileTarget, smileUnderlyings,
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
