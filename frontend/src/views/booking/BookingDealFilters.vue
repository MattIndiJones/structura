<template>
  <div class="card flex flex-wrap gap-3 items-end">
    <div class="flex flex-col gap-1 min-w-[140px]">
      <label class="text-[10px] text-slate-500 uppercase tracking-wider">Contrepartie</label>
      <input v-model="filters.contrepartie" type="text" placeholder="Filtrer…"
        class="bg-slate-800 border border-slate-700 rounded px-2.5 py-1.5 text-xs text-slate-200 placeholder-slate-600 focus:outline-none focus:border-blue-600" />
    </div>
    <div class="flex flex-col gap-1">
      <label class="text-[10px] text-slate-500 uppercase tracking-wider">Sous-jacent</label>
      <select v-model="filters.ticker" class="select text-xs py-1.5 min-w-[120px]">
        <option value="">Tous</option>
        <option v-for="t in tickerOptions" :key="t" :value="t">{{ t }}</option>
      </select>
    </div>
    <div class="flex flex-col gap-1">
      <label class="text-[10px] text-slate-500 uppercase tracking-wider">Type</label>
      <select v-model="filters.productType" class="select text-xs py-1.5 min-w-[140px]">
        <option value="">Tous</option>
        <option v-for="p in productTypeOptions" :key="p" :value="p">{{ p }}</option>
      </select>
    </div>
    <div class="flex flex-col gap-1">
      <label class="text-[10px] text-slate-500 uppercase tracking-wider">Famille de payoff</label>
      <select v-model="filters.payoffFamily" class="select text-xs py-1.5 min-w-[140px]">
        <option value="">Toutes</option>
        <option v-for="family in payoffFamilyOptions" :key="family" :value="family">{{ family }}</option>
      </select>
    </div>
    <div class="flex flex-col gap-1">
      <label class="text-[10px] text-slate-500 uppercase tracking-wider">Statut</label>
      <select v-model="filters.status" class="select text-xs py-1.5">
        <option value="">Tous</option>
        <option v-for="s in statusOptions" :key="s" :value="s">{{ s }}</option>
      </select>
    </div>
    <div class="flex flex-col gap-1">
      <label class="text-[10px] text-slate-500 uppercase tracking-wider">Portefeuille</label>
      <select v-model="filters.portfolioId" class="select text-xs py-1.5 booking-portfolio-filter">
        <option value="">Tous</option>
        <option v-for="p in portfolios" :key="p.id" :value="String(p.id)">
          {{ p.name }}
        </option>
      </select>
    </div>
    <div class="flex flex-col gap-1">
      <label class="text-[10px] text-slate-500 uppercase tracking-wider">Trier par</label>
      <div class="flex items-center gap-1">
        <select v-model="sortBy" class="select text-xs py-1.5">
          <option value="status">Statut</option>
          <option value="maturity_date">Maturité</option>
          <option value="reference">Référence</option>
        </select>
        <button class="btn-secondary text-xs px-2 py-1.5" @click="toggleSortDir"
          :title="sortDir === 'asc' ? 'Croissant' : 'Décroissant'">
          {{ sortDir === 'asc' ? '↑' : '↓' }}
        </button>
      </div>
    </div>
    <button v-if="hasActiveFilters" class="btn-secondary text-xs px-3 py-1.5 self-end" @click="resetFilters">
      ✕ Réinitialiser
    </button>
  </div>
</template>

<script setup>
// Extracted from BookingView.vue (P1-10, U3). The state stays in the
// view; this panel reads it through useBookingContext().
import { statusOptions } from './dealLabels.js'
import { useBookingContext } from './context.js'

const {
  filters, hasActiveFilters, payoffFamilyOptions, portfolios, productTypeOptions, resetFilters,
  sortBy, sortDir, tickerOptions, toggleSortDir,
} = useBookingContext()
</script>

<style scoped>
.watchlist-heading__content > :last-child {
  flex-shrink: 0;
}

.deal-card__actions > button {
  flex: 0 0 auto;
  min-height: 2rem;
  white-space: nowrap;
}

.booking-portfolio-filter {
  width: auto;
  min-width: min(14rem, 100%);
  max-width: 100%;
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

.barrier-gauge__mark--ki { background: var(--negative); }

.barrier-gauge__mark--autocall { background: var(--positive); }

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

/* Couleurs de signe en dernier, sous le panneau : elles doivent l'emporter
   sur toutes les couleurs de base ci-dessus. */

.deal-panel .tone-pos { color: var(--positive); }

.deal-panel .tone-neg { color: var(--negative); }
</style>
