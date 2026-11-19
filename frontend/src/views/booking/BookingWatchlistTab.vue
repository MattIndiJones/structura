<template>
  <EmptyState v-if="commercialScope.active && !watchlistLoading && !watchlist.length && !watchlistError"
              icon="✓" title="Aucun deal actif sur ce périmètre"
              hint="Les transactions importées restent dans Clients : elles ne sont pas des positions du book et n'ont pas de Life Cycle." />

  <!-- ── Watchlist barrières (deals actifs) ───────────── -->
  <div v-if="watchlist.length || watchlistError" class="card">
    <h2 class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3">
      Watchlist — proximité barrières
      <HelpTip width="w-72" text="Deals actifs triés par défaut par prochaine observation, puis par proximité de barrière à date égale. Cliquez sur un en-tête pour choisir le tri, puis recliquez pour inverser son sens. Détection par convention de nommage des PARAM (AC_BAR, KI_BAR…) — un script aux noms inhabituels peut passer à travers. Les niveaux sont ceux réellement figés au booking ; le défaut du script n'est utilisé qu'en l'absence de surcharge." />
    </h2>

    <div v-if="watchlistError" class="text-xs text-amber-400">⚠ {{ watchlistError }}</div>

    <template v-else>
    <DataFilterBar v-if="watchlist.length" class="border-0 p-0 bg-transparent mb-3"
                   :fields="wlFilterFields" :state="wlFilter.state"
                   :field-options="wlFilter.fieldOptions.value"
                   :has-active-filters="wlFilter.hasActiveFilters.value"
                   :sorts="wlSorts" :sort-by="wlFilter.sortBy.value" :sort-dir="wlFilter.sortDir.value"
                   :count="sortedWatchlist.length" :total="watchlist.length" noun="deal(s)"
                   @update:sort-by="wlFilter.sortBy.value = $event"
                   @toggle-dir="wlFilter.toggleSortDir()" @reset="wlFilter.reset()" />

    <div class="overflow-x-auto table-shell" tabindex="0" role="region">
      <table class="w-full text-xs border-collapse">
        <thead>
          <tr class="border-b border-slate-700">
            <th v-for="column in wlColumns" :key="column.key" scope="col"
              class="watchlist-heading" :class="{ num: column.key === 'wof' }"
              :aria-sort="wlFilter.sortBy.value === column.key
                ? (wlFilter.sortDir.value === 'asc' ? 'ascending' : 'descending') : 'none'">
              <div class="watchlist-heading__content" :class="{ 'justify-end': column.key === 'wof' }">
                <button type="button" class="watchlist-heading__sort"
                  :class="{ 'watchlist-heading__sort--active': wlFilter.sortBy.value === column.key }"
                  :title="watchlistSortTitle(column)" :aria-label="watchlistSortTitle(column)"
                  @click="sortWatchlistBy(column.key)">
                  <span>{{ column.heading || column.label }}</span>
                  <span aria-hidden="true" class="watchlist-heading__arrow">{{ wlFilter.sortBy.value === column.key ? (wlFilter.sortDir.value === 'asc' ? '↑' : '↓') : '↕' }}</span>
                </button>
                <HelpTip width="w-72" :text="column.help" />
              </div>
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="w in sortedWatchlist" :key="w.deal_id"
            class="border-b border-slate-800/50 hover:bg-slate-800/20 transition-colors">
            <td class="py-2 pr-3">
              <div class="flex items-center gap-1.5">
                <button type="button"
                  class="font-mono font-semibold text-blue-400 hover:underline whitespace-nowrap"
                  @click="openDealDetail(w.deal_id)">
                  {{ w.reference }}
                </button>
                <button type="button"
                  class="text-slate-500 hover:text-blue-300 shrink-0 transition-colors"
                  :class="copiedReference === w.reference ? 'text-emerald-400' : ''"
                  :title="copiedReference === w.reference ? 'Référence copiée' : 'Copier la référence du deal'"
                  :aria-label="`Copier la référence ${w.reference}`"
                  @click.stop="copyDealReference(w.reference)">
                  {{ copiedReference === w.reference ? '✓' : '⧉' }}
                </button>
                <RouterLink :to="`/pricer?dealId=${w.deal_id}`"
                  class="text-slate-500 hover:text-slate-300 shrink-0" title="Ouvrir dans le Pricer">
                  ⇥
                </RouterLink>
              </div>
            </td>
            <td class="py-2 pr-3 text-slate-300">{{ w.contrepartie }}</td>
            <td class="py-2 pr-3 text-slate-400 whitespace-nowrap">
              {{ (w.underlyings || []).map(u => u.ticker || u.name).join(' / ') || '—' }}
            </td>
            <td class="py-2 pr-3 text-slate-300">
              {{ watchlistProductName(w) || '—' }}
            </td>
            <td class="py-2 pr-3 whitespace-nowrap">
              <span v-if="w.product_type" class="text-slate-500 text-[10px] border border-slate-700 rounded px-1.5 py-0.5">
                {{ productTypeLabel(w.product_type) }}
              </span>
              <span v-else class="text-slate-600">—</span>
            </td>
            <td class="py-2 pr-3 font-mono whitespace-nowrap">
              <template v-if="w.next_event">
                <span class="text-slate-300">{{ w.next_event.date }}</span>
                <span class="ml-1.5 text-[10px]"
                  :class="w.days_to_next <= 30 ? 'text-amber-400 font-semibold' : 'text-slate-500'">
                  J−{{ w.days_to_next }}
                </span>
              </template>
              <span v-else class="text-slate-600">—</span>
            </td>
            <td class="py-2 pr-3 font-mono num whitespace-nowrap">
              <template v-if="w.wof != null">
                <span :class="w.wof >= 1 ? 'text-emerald-400' : 'text-red-400'">
                  {{ (w.wof * 100).toFixed(1) }}%
                </span>
                <span v-if="w.wof_min != null" class="text-slate-600 text-[10px] ml-1">
                  (min {{ (w.wof_min * 100).toFixed(1) }}%)
                </span>
              </template>
              <span v-else-if="w.next_event && w.strike_pending" class="text-slate-600"
                    title="Le strike n'a pas encore eu lieu — aucun niveau de strike n'est fixé, donc aucune performance ne peut être mesurée">
                avant strike
              </span>
              <span v-else class="text-slate-600" title="Niveau de strike manquant — lancez un Refresh sur ce deal">n/d</span>
            </td>
            <td class="py-2">
              <div class="flex gap-1.5 flex-wrap">
                <span v-for="b in w.barriers" :key="b.name"
                  :class="barrierChipClass(b)"
                  class="px-1.5 py-0.5 rounded text-[10px] font-mono font-semibold whitespace-nowrap">
                  {{ b.name }} {{ (b.level * 100).toFixed(0) }}%<template v-if="b.observable && b.observable !== 'WOF'"> vs {{ b.observable }}</template> · {{ barrierGapLabel(b) }}
                </span>
                <span v-if="!w.barriers.length" class="text-slate-600 text-[10px]">aucune dans le script</span>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    </template>
  </div>
</template>

<script setup>
// Extracted from BookingView.vue (P1-10, U3). The state stays in the
// view; this panel reads it through useBookingContext().
import DataFilterBar from '../../components/ui/DataFilterBar.vue'
import EmptyState from '../../components/ui/EmptyState.vue'
import HelpTip from '../../components/HelpTip.vue'
import { RouterLink } from 'vue-router'
import { barrierChipClass, barrierGapLabel } from '../../utils/barriers.js'
import { productTypeLabel } from '../../data/payscriptTemplates.js'
import { watchlistProductName, wlColumns, wlFilterFields } from './dealLabels.js'
import { useBookingContext } from './context.js'

const {
  commercialScope, copiedReference, copyDealReference, openDealDetail, sortWatchlistBy,
  sortedWatchlist, watchlist, watchlistError, watchlistLoading, watchlistSortTitle, wlFilter,
  wlSorts,
} = useBookingContext()
</script>

<style scoped>
.watchlist-heading {
  vertical-align: middle;
  white-space: nowrap;
}

.watchlist-heading__content {
  display: flex;
  align-items: center;
  gap: 0.25rem;
}

.watchlist-heading__content > :last-child {
  flex-shrink: 0;
}

.watchlist-heading__sort {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  min-height: 1.75rem;
  color: inherit;
  font: inherit;
  letter-spacing: inherit;
  text-transform: inherit;
  white-space: nowrap;
  cursor: pointer;
}

.watchlist-heading__sort:hover,
.watchlist-heading__sort--active {
  color: var(--accent);
}

.watchlist-heading__sort:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 3px;
  border-radius: 3px;
}

.watchlist-heading__arrow {
  width: 0.7rem;
  text-align: center;
}

.deal-card__actions > button {
  flex: 0 0 auto;
  min-height: 2rem;
  white-space: nowrap;
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
</style>
