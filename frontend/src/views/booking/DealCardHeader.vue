<template>
  <div class="deal-card__header cursor-pointer select-none"
    @click="toggleDetail(d.id)">
    <div class="deal-card__identity">
      <div class="flex items-center gap-2 min-w-0">
        <span class="text-slate-500 text-xs shrink-0">{{ expanded[d.id] ? '▾' : '▸' }}</span>
        <button type="button"
          class="font-mono font-semibold text-blue-400 hover:underline whitespace-nowrap"
          :title="`Ouvrir le booking du deal ${d.reference}`"
          @click.stop="openDealDetail(d.id)">{{ d.reference }}</button>
        <button type="button"
          class="text-slate-500 hover:text-blue-300 shrink-0 transition-colors"
          :class="copiedReference === d.reference ? 'text-emerald-400' : ''"
          :title="copiedReference === d.reference ? 'Référence copiée' : 'Copier la référence du deal'"
          :aria-label="`Copier la référence ${d.reference}`"
          @click.stop="copyDealReference(d.reference)">
          {{ copiedReference === d.reference ? '✓' : '⧉' }}
        </button>
      </div>
      <div class="deal-card__identity-meta">
        <span v-if="d.product_type" class="font-medium text-slate-400">
          {{ productTypeLabel(d.product_type) }}
        </span>
        <span v-if="d.product_type && d.contrepartie" class="text-slate-600">·</span>
        <span v-if="dealPayoffFamily(d)" class="text-[10px] border rounded px-1.5 py-0.5"
          style="border-color: var(--border); color: var(--muted);">
          {{ dealPayoffFamily(d) }}
        </span>
        <span class="text-slate-300">{{ d.contrepartie }}</span>
        <span v-if="d.legal_identity_exception && !d.counterparty_id" class="text-[10px] text-amber-300"
          :title="d.legal_identity_exception.reason">Exception administrateur · juridique à qualifier · crédit non évalué</span>
        <span class="text-[10px] border rounded px-1.5 py-0.5"
          style="border-color: var(--border); background: var(--surface2); color: var(--accent);">
          Fixings automatiques
        </span>
        <span :class="statusClass(d.status)" class="badge">
          {{ statusLabel(d.status) }}
        </span>
      </div>
    </div>
    <div class="deal-card__actions" @click.stop>
      <template v-if="canAssignPortfolio(d)">
        <ActionMenu :label="dealPortfolioLabel(d)" class="deal-card__portfolio"
          :title="`${dealPortfolioLabel(d)} — un deal peut alimenter plusieurs vues de risque`" @click.stop>
            <label v-for="p in portfoliosForDeal(d)" :key="p.id"
              class="flex items-center gap-2 px-2 py-1.5 text-[10px] cursor-pointer hover:bg-slate-800 rounded">
              <input type="checkbox" :checked="dealHasPortfolio(d, p.id)"
                :disabled="portfolioAssigning[d.id]"
                @change="toggleDealPortfolio(d, p.id, $event.target.checked)" />
              <span>{{ p.name }}</span>
            </label>
            <div v-if="!portfoliosForDeal(d).length" class="px-2 py-1 text-[10px] text-slate-500">
              Aucun portefeuille pour ce compte.
            </div>
        </ActionMenu>
        <span v-if="portfolioAssignmentStatus[d.id]" class="text-[10px] max-w-40"
          :class="portfolioAssignmentStatus[d.id].startsWith('⚠') ? 'text-red-500' : 'text-emerald-600'">
          {{ portfolioAssignmentStatus[d.id] }}
        </span>
      </template>
      <span v-else class="deal-card__portfolio-label"
        :title="`${dealPortfolioLabel(d)} — modification réservée au propriétaire`">
        {{ dealPortfolioLabel(d) }}
      </span>
      <button v-if="d.status === 'actif'" class="btn-secondary text-xs px-3 py-1.5"
        :disabled="greeksLoading[d.id]" @click.stop="runGreeks(d.id)"
        title="Greeks du deal (bump-and-reprice CRN) : delta/gamma/vega par sous-jacent, theta, rho — mêmes hypothèses de marché que le mode MtM sélectionné">
        <span v-if="greeksLoading[d.id]"
          class="w-3 h-3 border-2 border-slate-400 border-t-transparent rounded-full animate-spin inline-block mr-1"></span>
        Δ Greeks
      </button>
      <button v-if="d.status === 'actif'" class="btn-secondary text-xs px-3 py-1.5"
        @click.stop="toggleShockPanel(d.id)"
        title="Choc de marché (full reprice, pas une approximation linéaire) : spot/vol/taux/corrélation, sur ce deal seul">
        ⚡ Choc
      </button>
      <button class="btn-secondary text-xs px-3 py-1.5" :disabled="refreshingId === d.id"
        @click.stop="refresh(d.id)">
        <span v-if="refreshingId === d.id"
          class="w-3 h-3 border-2 border-slate-400 border-t-transparent rounded-full animate-spin inline-block mr-1"></span>
        ↻ Refresh
      </button>
      <ActionMenu label="→ Ouvrir" @click.stop>
          <RouterLink
            :to="{ path: '/pricer', query: { dealId: d.id, tab: 'script' } }"
            class="deal-open-menu__item">
            Ouvrir ici
          </RouterLink>
          <RouterLink
            :to="{ path: '/pricer', query: { dealId: d.id, tab: 'script' } }"
            class="deal-open-menu__item" target="_blank" rel="noopener noreferrer">
            Ouvrir dans un nouvel onglet ↗
          </RouterLink>
      </ActionMenu>
    </div>
  </div>
</template>

<script setup>
// Extracted from BookingView.vue (P1-10, U3). The state stays in the
// view; this panel reads it through useBookingContext().
import ActionMenu from '../../components/ui/ActionMenu.vue'
import { RouterLink } from 'vue-router'
import { dealHasPortfolio, dealPayoffFamily, statusClass, statusLabel } from './dealLabels.js'
import { productTypeLabel } from '../../data/payscriptTemplates.js'
import { useBookingContext } from './context.js'

defineProps({ d: { required: true } })
const {
  canAssignPortfolio, copiedReference, copyDealReference, dealPortfolioLabel, expanded,
  greeksLoading, openDealDetail, portfolioAssigning, portfolioAssignmentStatus, portfoliosForDeal,
  refresh, refreshingId, runGreeks, toggleDealPortfolio, toggleDetail, toggleShockPanel,
} = useBookingContext()
</script>

<style scoped>
.watchlist-heading__content > :last-child {
  flex-shrink: 0;
}

.deal-card__header {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  gap: 0.75rem;
}

.deal-card__identity {
  flex: 1 1 22rem;
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 0.3rem;
}

.deal-card__identity-meta {
  display: flex;
  min-height: 1.35rem;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
  padding-left: 1.25rem;
  font-size: 0.75rem;
}

.deal-card__actions {
  display: flex;
  flex: 0 1 auto;
  flex-wrap: wrap;
  align-items: flex-start;
  justify-content: flex-end;
  gap: 0.5rem;
  min-width: 0;
  max-width: 100%;
  margin-left: auto;
}

.deal-card__actions > button {
  flex: 0 0 auto;
  min-height: 2rem;
  white-space: nowrap;
}

.deal-open-menu__item {
  white-space: nowrap;
  border: 1px solid var(--border);
  border-radius: 0.375rem;
  background: var(--surface);
  padding: 0.375rem 0.55rem;
  color: var(--text);
  font-size: 0.6875rem;
  font-weight: 600;
}

.deal-open-menu__item:hover {
  border-color: var(--accent);
  color: var(--accent);
}

.deal-card__portfolio,
.deal-card__portfolio-label {
  max-width: min(22rem, 100%);
}

.deal-card__portfolio-label {
  min-width: 0;
  white-space: normal;
  overflow-wrap: anywhere;
  border: 1px solid var(--border);
  border-radius: 0.375rem;
  padding: 0.375rem 0.65rem;
  color: var(--muted);
  font-size: 0.75rem;
}

.deal-figures > div {
  min-width: 0;
  padding: 0.5rem 0.65rem;
}

.deal-figures > div:nth-child(odd) {
  border-right: 1px solid var(--border);
}

.deal-figures > div:nth-child(n + 3) {
  border-top: 1px solid var(--border);
}

.deal-perf.tone-pos { background: var(--positive-light); }

.deal-perf.tone-neg { background: var(--negative-light); }

.deal-barriers > * + * {
  border-top: 1px solid var(--border);
}

.barrier-gauge__caption span:first-child {
  overflow: hidden;
  color: #3d382f;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.barrier-gauge__caption span:last-child {
  flex: 0 0 auto;
  color: var(--subtle);
  font-size: 0.625rem;
}

.barrier-gauge__mark--ki { background: var(--negative); }

.barrier-gauge__mark--autocall { background: var(--positive); }

.barrier-gauge__mark span,
.barrier-gauge__cursor span {
  position: absolute;
  left: 50%;
  transform: translateX(-50%);
  font-family: 'JetBrains Mono', 'Fira Code', Consolas, monospace;
  font-size: 0.625rem;
  font-weight: 700;
  line-height: 1;
  white-space: nowrap;
}

.barrier-gauge__mark span { bottom: calc(100% + 0.2rem); }

.barrier-gauge__mark--ki span { color: var(--negative); }

.barrier-gauge__mark--autocall span { color: var(--positive); }

.barrier-gauge__cursor span {
  top: calc(100% + 0.25rem);
  color: var(--text);
}

.deal-barrier-row__tick--ki { background: var(--negative); }

.deal-barrier-row__tick--autocall { background: var(--positive); }

.deal-panel__select.select,
.deal-panel__select.input {
  border-color: var(--panel-edge);
  background-color: var(--surface);
  color: var(--text);
  font-weight: 600;
}

.deal-panel__select.select:hover,
.deal-panel__select.select:focus,
.deal-panel__select.input:hover,
.deal-panel__select.input:focus {
  border-color: var(--panel-accent);
}

.deal-best-case span {
  color: #8a6508;
  font-weight: 600;
}

.deal-result-empty > span {
  color: #57524a;
  font-size: 0.75rem;
  line-height: 1.4;
}

/* Couleurs de signe en dernier, sous le panneau : elles doivent l'emporter
   sur toutes les couleurs de base ci-dessus. */

.deal-panel .tone-pos { color: var(--positive); }

.deal-panel .tone-neg { color: var(--negative); }

@media (max-width: 900px) {
  .deal-card__actions {
    flex-basis: 100%;
    justify-content: flex-start;
    margin-left: 0;
  }
}
</style>
