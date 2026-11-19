<template>

  <AlertMessage v-if="portfolioError" kind="error" dismissible
    @dismiss="portfolioError = ''">{{ portfolioError }}</AlertMessage>
  <AlertMessage v-if="portfolioNotice" kind="success" dismissible
    @dismiss="portfolioNotice = ''">{{ portfolioNotice }}</AlertMessage>

  <!-- Création & gestion -->
  <div class="flex flex-col gap-2">
    <div class="text-xs font-bold text-slate-400 uppercase tracking-wider">Création & gestion</div>
    <div class="max-w-md">
      <label v-if="authStore.isAdmin" for="new-portfolio-owner" class="label">Compte propriétaire</label>
      <select v-if="authStore.isAdmin" id="new-portfolio-owner" v-model.number="newPortfolioUserId"
        class="select text-xs py-1.5 w-full mt-1 mb-2" :disabled="creatingPortfolio">
        <option v-for="owner in portfolioOwners" :key="owner.id" :value="owner.id">
          {{ owner.username }}{{ owner.entity ? ` · ${owner.entity}` : '' }}
        </option>
      </select>
      <label for="new-portfolio-name" class="label">Nom du portefeuille</label>
      <div class="flex gap-1.5 mt-1">
        <input id="new-portfolio-name" v-model="newPortfolioName" type="text"
          placeholder="Ex. Produits structurés EUR" class="input text-xs py-1.5 flex-1 min-w-0"
          :disabled="creatingPortfolio" autocomplete="off" @keyup.enter="createPortfolio" />
        <button class="btn-primary text-xs px-3 py-1.5 shrink-0"
          :disabled="creatingPortfolio || !newPortfolioName.trim()" @click="createPortfolio">
          {{ creatingPortfolio ? 'Création…' : '＋ Créer' }}
        </button>
      </div>
      <p class="text-[10px] mt-1" style="color: var(--subtle);">
        Saisissez un nom : le bouton Créer s’active dès que le champ n’est plus vide.
      </p>
    </div>
    <div class="flex flex-col gap-1 max-w-md">
      <div v-for="p in pf.portfolios" :key="p.id"
        class="flex items-center gap-2 px-2.5 py-1.5 rounded-lg border border-slate-800 group">
        <span class="text-sm shrink-0">📁</span>
        <span class="flex-1 min-w-0 text-xs text-slate-300">
          <span class="block truncate">{{ p.name }}</span>
          <span v-if="authStore.isAdmin" class="block truncate text-[9px] text-slate-600">
            {{ p.owner_username }}{{ p.owner_entity_name ? ` · ${p.owner_entity_name}` : '' }}
          </span>
        </span>
        <span class="text-[10px] font-mono px-1.5 py-0.5 rounded-full bg-slate-800 text-slate-400 shrink-0">{{ p.deal_count }} deal(s)</span>
        <button class="text-slate-600 hover:text-slate-300 text-xs px-1 shrink-0"
          title="Renommer" aria-label="Renommer le portefeuille" @click="renamePortfolio(p)">✎</button>
        <button class="text-slate-600 hover:text-red-400 text-xs px-1 shrink-0"
          title="Supprimer le portefeuille (les deals et leurs calculs sont conservés)"
          aria-label="Supprimer le portefeuille" @click="deletePortfolio(p)">✕</button>
      </div>
    </div>
  </div>

  <!-- Composition de la sélection -->
  <div class="text-xs font-bold text-slate-400 uppercase tracking-wider pt-2 border-t border-slate-800">
    Composition — {{ pf.view === 'global' ? 'Tous portefeuilles' : pf.label }}
    <span class="ml-2 font-normal normal-case text-slate-500">
      {{ pf.riskMembers.length }} actif(s) à la date sur {{ pf.allMembers.length }} deal(s)
    </span>
  </div>
  <div v-if="!pf.allMembers.length" class="text-xs text-slate-500">
    Aucun deal dans cette sélection.
  </div>
  <div v-else class="overflow-x-auto table-shell" tabindex="0" role="region">
    <table class="w-full text-xs border-collapse">
      <thead>
        <tr class="border-b border-slate-700 text-slate-500">
          <th class="text-left py-1.5 pr-3 font-semibold">Réf</th>
          <th class="text-left py-1.5 pr-3 font-semibold">Contrepartie</th>
          <th class="text-left py-1.5 pr-3 font-semibold">Type</th>
          <th class="text-left py-1.5 pr-3 font-semibold">État au {{ pf.valuationDate }}</th>
          <th class="text-right py-1.5 pr-3 font-semibold num">Nominal</th>
          <th class="text-left py-1.5 pr-3 font-semibold">Portefeuilles
            <HelpTip text="Un deal peut appartenir à plusieurs portefeuilles. Cochez toutes les vues de risque qui doivent le contenir." /></th>
          <th class="text-left py-1.5 font-semibold">Greeks à la date
            <HelpTip text="Disponibilité d'un calcul dont la date de valorisation correspond exactement à la date d’analyse. La date d’exécution technique peut être postérieure. Cliquez la ligne pour ouvrir la fiche dans Booking." /></th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="d in pf.allMembers" :key="d.id"
          class="border-b border-slate-800/50 hover:bg-slate-800/20 transition-colors cursor-pointer"
          :class="riskState(d).active ? '' : 'opacity-45 grayscale bg-slate-900/40'"
          @click="openDealDetail(d.id)">
          <td class="py-1.5 pr-3 font-mono font-semibold text-blue-400"><DealReferenceLink :deal-id="d.id" :reference="d.reference" /></td>
          <td class="py-1.5 pr-3 text-slate-300">{{ d.contrepartie }}</td>
          <td class="py-1.5 pr-3 text-slate-500 text-[10px]">{{ d.product_type || '—' }}</td>
          <td class="py-1.5 pr-3 text-[10px]"
            :class="riskState(d).active ? 'text-emerald-400' : 'text-slate-500'">
            {{ riskState(d).reason }}
          </td>
          <td class="py-1.5 pr-3 text-right font-mono num text-slate-300">{{ formatNominal(d.nominal) }} {{ d.devise }}</td>
          <td class="py-1.5 pr-3" @click.stop>
            <ActionMenu :label="dealPortfolioLabel(d)" :title="dealPortfolioLabel(d)" class="max-w-sm">
                <label v-for="p in portfoliosForDeal(d)" :key="p.id"
                  class="flex items-center gap-2 px-2 py-1.5 rounded hover:bg-slate-800 text-[10px] text-slate-300 cursor-pointer">
                  <input type="checkbox" :checked="dealHasPortfolio(d, p.id)"
                    :disabled="portfolioAssigning[d.id]"
                    @change="togglePortfolioMembership(d, p.id, $event.target.checked)" />
                  <span>{{ p.name }}</span>
                </label>
                <div v-if="!portfoliosForDeal(d).length" class="px-2 py-1 text-[10px] text-slate-500">
                  Aucun portefeuille pour ce compte.
                </div>
            </ActionMenu>
          </td>
          <td class="py-1.5 text-slate-500">
            <span v-if="greeksMatchSelectedDate(d)" class="text-emerald-400"
              :title="greekExecutionTitle(d)">
              disponibles
            </span>
            <span v-else-if="riskState(d).active" class="text-amber-400">absents à cette date</span>
            <span v-else>hors périmètre</span>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup>
// Extracted from RiskManagementView.vue (P1-10, U3). The state stays in the
// view; this panel reads it through useRiskContext().
import ActionMenu from '../../components/ui/ActionMenu.vue'
import AlertMessage from '../../components/ui/AlertMessage.vue'
import DealReferenceLink from '../../components/DealReferenceLink.vue'
import HelpTip from '../../components/HelpTip.vue'
import { dealHasPortfolio, dealPortfolioLabel } from './riskLabels.js'
import { useRiskContext } from './context.js'

const {
  authStore, createPortfolio, creatingPortfolio, deletePortfolio, formatNominal,
  greekExecutionTitle, greeksMatchSelectedDate, newPortfolioName, newPortfolioUserId,
  openDealDetail, pf, portfolioAssigning, portfolioError, portfolioNotice, portfolioOwners,
  portfoliosForDeal, renamePortfolio, riskState, togglePortfolioMembership,
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
