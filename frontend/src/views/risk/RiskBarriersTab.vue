<template>
  <div class="flex items-center gap-3 flex-wrap">
    <div class="text-sm font-bold text-slate-100">
      📍 Proximité aux barrières — {{ pf.view === 'global' ? 'Tous portefeuilles' : pf.label }}
      <HelpTip width="w-80" text="Classe tous les deals actifs de la sélection par écart entre le worst-of actuel et leur prochaine barrière (autocall, KI) détectée dans le script — pour repérer en un coup d'œil ce qui mérite un suivi cette semaine. Réutilise la même détection que la Surveillance de Booking (convention PARAM M_)." />
    </div>
    <button class="btn-secondary text-xs px-3 py-1.5 ml-auto" :disabled="calculationActive || !pf.members.length"
      @click="pf.loadBarriers">
      <span v-if="pf.barriersLoading"
        class="w-3 h-3 border-2 border-slate-400 border-t-transparent rounded-full animate-spin inline-block mr-1"></span>
      🔄 Actualiser
    </button>
  </div>

  <div v-if="!pf.barriers && !pf.barriersLoading" class="text-xs text-slate-500 text-center py-8">
    <button class="btn-primary text-xs px-4 py-1.5" :disabled="calculationActive || !pf.members.length" @click="pf.loadBarriers">
      ▶ Charger la proximité aux barrières
    </button>
    <div v-if="!pf.members.length" class="mt-2 text-slate-600">Aucun deal actif dans cette sélection.</div>
  </div>

  <div v-else-if="pf.barriersLoading" class="text-xs text-slate-500 text-center py-8">
    Calcul en cours — un appel de marché par deal, cela peut prendre quelques secondes…
  </div>

  <template v-else-if="pf.barriers">
    <div class="grid grid-cols-2 sm:grid-cols-3 gap-3">
      <div class="stat-box">
        <div class="text-xs text-slate-500 mb-1">Critique — ≤ 5 pts (KI)</div>
        <div class="text-lg font-bold font-mono text-red-400">{{ pf.barriers.counts.critique }}</div>
        <div class="text-[10px] text-slate-600">deal(s)</div>
      </div>
      <div class="stat-box">
        <div class="text-xs text-slate-500 mb-1">Attention — zone intermédiaire</div>
        <div class="text-lg font-bold font-mono text-amber-400">{{ pf.barriers.counts.attention }}</div>
        <div class="text-[10px] text-slate-600">deal(s)</div>
      </div>
      <div class="stat-box">
        <div class="text-xs text-slate-500 mb-1">Sous contrôle</div>
        <div class="text-lg font-bold font-mono text-emerald-400">{{ pf.barriers.counts.ok }}</div>
        <div class="text-[10px] text-slate-600">deal(s)</div>
      </div>
    </div>

    <div v-if="pf.barriers.errors.length"
      class="text-xs text-amber-400 bg-amber-950/30 border border-amber-900/50 rounded-lg px-3 py-2">
      ⚠ Deal(s) non évalués (erreur marché) :
      <span v-for="(e, i) in pf.barriers.errors" :key="e.deal_id">
        {{ i > 0 ? ' · ' : '' }}<DealReferenceLink :deal-id="e.deal_id"
          :reference="e.reference" class="font-mono text-blue-400" /> <span class="text-amber-600">({{ e.error }})</span>
      </span>
    </div>

    <div v-if="!pf.barriers.rows.length" class="text-xs text-slate-500">
      Aucune barrière PARAM (convention M_) détectée sur les deals actifs de cette sélection.
    </div>

    <div v-else class="overflow-x-auto table-shell" tabindex="0" role="region">
      <table class="w-full text-xs border-collapse">
        <thead>
          <tr class="border-b border-slate-700 text-slate-500">
            <th class="text-left py-1.5 pr-3 font-semibold">Deal</th>
            <th class="text-left py-1.5 pr-3 font-semibold">Sous-jacent</th>
            <th class="text-left py-1.5 pr-3 font-semibold">Prochaine obs</th>
            <th class="text-right py-1.5 pr-3 font-semibold num">WOF</th>
            <th class="text-left py-1.5 pr-3 font-semibold">Barrières</th>
            <th class="text-right py-1.5 font-semibold num">Nominal</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="w in pf.barriers.rows" :key="w.deal_id"
            class="border-b border-slate-800/50 hover:bg-slate-800/20 transition-colors cursor-pointer"
            @click="openDealDetail(w.deal_id)">
            <td class="py-2 pr-3 font-mono font-semibold text-blue-400 whitespace-nowrap"><DealReferenceLink :deal-id="w.deal_id" :reference="w.reference" /></td>
            <td class="py-2 pr-3 text-slate-400 whitespace-nowrap">
              {{ (w.underlyings || []).map(u => u.ticker || u.name).join(' / ') || '—' }}
            </td>
            <td class="py-2 pr-3 font-mono whitespace-nowrap">
              <template v-if="w.next_event">
                <span class="text-slate-300">{{ w.next_event.date }}</span>
                <span class="ml-1.5 text-[10px]" :class="w.days_to_next <= 30 ? 'text-amber-400 font-semibold' : 'text-slate-500'">
                  J−{{ w.days_to_next }}
                </span>
              </template>
              <span v-else class="text-slate-600">—</span>
            </td>
            <td class="py-2 pr-3 font-mono num whitespace-nowrap text-right">
              <template v-if="w.wof != null">
                <span :class="w.wof >= 1 ? 'text-emerald-400' : 'text-red-400'">{{ formatPercent(w.wof * 100, 1) }}</span>
              </template>
              <span v-else class="text-slate-600" title="S₀ manquant">n/d</span>
            </td>
            <td class="py-2 pr-3">
              <div class="flex gap-1.5 flex-wrap">
                <span v-for="b in w.barriers" :key="b.name"
                  :class="barrierChipClass(b)"
                  class="px-1.5 py-0.5 rounded text-[10px] font-mono font-semibold whitespace-nowrap">
                  {{ b.name }} {{ formatPercent(b.level * 100, 0) }}<template v-if="b.observable && b.observable !== 'WOF'"> vs {{ b.observable }}</template> · {{ barrierGapLabel(b) }}
                </span>
              </div>
            </td>
            <td class="py-2 text-right font-mono num text-slate-300 whitespace-nowrap">{{ formatNominal(w.nominal) }} {{ w.devise }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </template>
</template>

<script setup>
// Extracted from RiskManagementView.vue (P1-10, U3). The state stays in the
// view; this panel reads it through useRiskContext().
import DealReferenceLink from '../../components/DealReferenceLink.vue'
import HelpTip from '../../components/HelpTip.vue'
import { barrierChipClass, barrierGapLabel } from '../../utils/barriers.js'
import { formatPercent } from '../../utils/format.js'
import { useRiskContext } from './context.js'

const {
  calculationActive, formatNominal, openDealDetail, pf,
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
