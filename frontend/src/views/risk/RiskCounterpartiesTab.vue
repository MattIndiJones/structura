<template>
  <div class="text-[10px] text-slate-500 -mt-1">
    Exposition par contrepartie sur les deals actifs et les remboursements en attente — pas de recalcul Monte Carlo.
    <HelpTip text="Avant maturité, la base est le nominal. Entre maturité et paiement, la base devient le remboursement contractuel connu encore dû par l'émetteur." />
  </div>

  <div v-if="pf.exposureLoading" class="text-xs text-slate-500">Chargement…</div>

  <template v-else-if="pf.exposure">
    <p v-if="pf.exposure.deals_missing_fx?.length" class="text-xs text-amber-300">
      {{ pf.exposure.deals_missing_fx.length }} dossier(s) sans conversion FX : total EUR partiel,
      indicateurs de concentration incomplets et limites concernées à contrôler.
    </p>
    <p v-if="pf.exposure.deals_requiring_qualification?.length" class="text-xs text-amber-300">
      {{ pf.exposure.deals_requiring_qualification.length }} dossier(s) à qualifier juridiquement,
      y compris les exceptions administrateur. Leur exposition reste affichée ; limites non évaluées et indicateurs de concentration incomplets.
    </p>
    <div v-if="!pf.exposure.by_counterparty.length" class="text-xs text-slate-500">
      Aucun deal actif ou en attente de règlement dans cette sélection.
    </div>

    <template v-else>
      <div class="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div class="stat-box">
          <div class="text-xs text-slate-500 mb-1">Exposition totale
            <HelpTip text="Somme des nominaux actifs et des remboursements connus non réglés, convertis en EUR." /></div>
          <div class="text-lg font-bold font-mono text-slate-200">{{ formatNominal(pf.exposure.nominal_total_eur) }}</div>
          <div class="text-[10px] text-slate-600">EUR</div>
        </div>
        <div class="stat-box">
          <div class="text-xs text-slate-500 mb-1">Groupes de contreparties
            <HelpTip text="Regroupement par identifiant juridique. Les dossiers sans identifiant restent dans des groupes descriptifs à qualifier ; ils ne certifient pas un nombre de banques distinctes." /></div>
          <div class="text-lg font-bold font-mono text-slate-200">{{ pf.exposure.by_counterparty.length }}</div>
        </div>
        <div class="stat-box">
          <div class="text-xs text-slate-500 mb-1">N effectif (1/HHI)
            <HelpTip text="Indice de concentration Herfindahl-Hirschman (Σ part²) retourné en 'nombre de contreparties équivalent' — un book réparti sur 10 banques à parts égales donne 10 ; un book concentré sur 2-3 banques donne un chiffre bas même s'il y a nominalement plus de 10 contreparties au total." /></div>
          <div class="text-lg font-bold font-mono"
            :class="pf.exposure.effective_n != null && pf.exposure.effective_n < 3 ? 'text-amber-400' : 'text-slate-200'">
            {{ pf.exposure.effective_n ?? '—' }}
          </div>
        </div>
        <div class="stat-box">
          <div class="text-xs text-slate-500 mb-1">Top 3 contreparties
            <HelpTip text="Part du nominal total portée par les 3 plus grosses contreparties de cette sélection." /></div>
          <div class="text-lg font-bold font-mono text-slate-200">
            {{ pf.exposure.top3_pct != null ? Math.round(pf.exposure.top3_pct * 100) + '%' : '—' }}
          </div>
        </div>
      </div>

      <div class="overflow-x-auto table-shell" tabindex="0" role="region">
        <table class="w-full text-xs border-collapse">
          <thead>
            <tr class="border-b border-slate-700 text-slate-500">
              <th class="text-left py-1.5 pr-3 font-semibold">Contrepartie</th>
              <th class="text-right py-1.5 pr-3 font-semibold">Nominal (EUR)</th>
              <th class="text-right py-1.5 pr-3 font-semibold">% du book</th>
              <th class="text-right py-1.5 pr-3 font-semibold">Deals</th>
              <th class="text-right py-1.5 pr-3 font-semibold">Limite (EUR)
                <HelpTip align="right" text="Limite de suivi du nominal EUR, configurée dans Administration → Contreparties. Ce suivi est distinct des limites CCR bloquantes. Sans identité qualifiée, la limite n’est pas évaluée." /></th>
              <th class="text-left py-1.5 font-semibold"></th>
            </tr>
          </thead>
          <tbody>
            <template v-for="c in pf.exposure.by_counterparty" :key="c.identity_key">
              <tr class="border-b border-slate-800/50 hover:bg-slate-800/20 transition-colors cursor-pointer"
                @click="expandedCounterparty = expandedCounterparty === c.identity_key ? null : c.identity_key">
                <td class="py-1.5 pr-3 text-slate-300 font-semibold">
                  <span class="text-slate-600 mr-1">{{ expandedCounterparty === c.identity_key ? '▾' : '▸' }}</span>{{ c.contrepartie }}
                  <span v-if="c.identity_status === 'INACTIVE'" class="ml-1 text-[10px] text-amber-300">inactive · exposition conservée</span>
                </td>
                <td class="py-1.5 pr-3 text-right font-mono text-slate-200">{{ formatNominal(c.nominal_eur) }}</td>
                <td class="py-1.5 pr-3 text-right font-mono text-slate-400">{{ c.pct_of_book != null ? Math.round(c.pct_of_book * 100) + '%' : '—' }}</td>
                <td class="py-1.5 pr-3 text-right font-mono text-slate-400">{{ c.deal_count }}</td>
                <td class="py-1.5 pr-3 text-right font-mono" :class="c.limit_breached ? 'text-red-400 font-bold' : 'text-slate-500'">
                  {{ c.limit_eur != null ? formatNominal(c.limit_eur) : '—' }}
                </td>
                <td class="py-1.5 text-right">
                  <span v-if="c.limit_breached" class="text-[10px] text-red-400 bg-red-950/40 border border-red-900/50 rounded-full px-2 py-0.5">⚠ limite dépassée</span>
                  <span v-else-if="c.limit_status === 'UNQUALIFIED'" class="text-[10px] text-amber-300">juridique à qualifier · limite non évaluée</span>
                  <span v-else-if="c.limit_status === 'INCOMPLETE'" class="text-[10px] text-amber-300">conversion FX manquante · contrôle incomplet</span>
                </td>
              </tr>
              <tr v-if="expandedCounterparty === c.identity_key" class="bg-slate-900/60">
                <td colspan="6" class="py-2 pl-6 pr-3">
                  <table class="w-full text-[11px] border-collapse">
                    <thead>
                      <tr class="text-slate-600">
                        <th class="text-left py-1 pr-3 font-medium">Deal</th>
                        <th class="text-right py-1 font-medium">Nominal (EUR)</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="dl in c.deals" :key="dl.id"
                        class="hover:bg-slate-800/40 cursor-pointer" @click.stop="openDealDetail(dl.id)">
                        <td class="py-1 pr-3 font-mono font-semibold text-blue-400"><DealReferenceLink :deal-id="dl.id" :reference="dl.reference" />
                          <span v-if="dl.contrepartie !== c.contrepartie" class="ml-2 text-slate-500">{{ dl.contrepartie }} au contrat</span>
                        </td>
                        <td class="py-1 text-right font-mono text-slate-400">{{ formatNominal(dl.nominal_eur) }}</td>
                      </tr>
                    </tbody>
                  </table>
                </td>
              </tr>
            </template>
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
  expandedCounterparty, formatNominal, openDealDetail, pf,
} = useRiskContext()
</script>

<style scoped>
/* Keep every heading directly above its values, including nested detail tables. */

.risk-management-view table th,
.risk-management-view table td {
  text-align: center;
  vertical-align: middle;
}
</style>
