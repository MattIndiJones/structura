<template>
  <div v-if="alerts.length" class="card border-amber-800/60">
    <div class="flex items-center mb-3">
      <h2 class="text-xs font-bold text-amber-400 uppercase tracking-wider flex items-center gap-2">
        <span class="inline-block w-2 h-2 rounded-full bg-red-500 pulse-ring"></span>
        🔔 Alertes non lues ({{ alerts.length }})
        <HelpTip width="w-72" text="Alertes levées par le refresh quotidien (23h) ou par le bouton Rafraîchir le book : rappel/échéance/KI détecté sur un deal, ou franchissement d'une barrière surveillée (M_). Chaque fait n'alerte qu'une seule fois." />
      </h2>
      <button class="ml-auto btn-secondary text-[10px] px-2 py-1" :disabled="markingAll || markingAlerts.size > 0" @click="markAllRead">✓ Tout marquer lu</button>
    </div>
    <div class="flex flex-col gap-1.5">
      <div v-for="a in alerts" :key="a.id" class="flex items-start gap-2 text-xs">
        <span :class="alertChipClass(a.kind)" class="px-1.5 py-0.5 rounded text-[10px] font-semibold shrink-0 whitespace-nowrap">
          {{ alertKindLabel(a.kind) }}
        </span>
        <span class="text-slate-300 flex-1">{{ a.message }}</span>
        <span class="text-slate-600 text-[10px] shrink-0">{{ a.created_at.slice(0, 10) }}</span>
        <button class="text-slate-500 hover:text-emerald-400 shrink-0" title="Marquer lu" :disabled="markingAll || markingAlerts.has(a.id)" @click="markRead(a)">✓</button>
      </div>
    </div>
  </div>

  <AlertMessage v-if="alertError" kind="error" role="alert">{{ alertError }}</AlertMessage>
  <!-- ── Stats agrégées (sur la sélection filtrée) ───────── -->
  <div class="card kpi-tile">
    <div class="flex flex-wrap gap-x-6 gap-y-3 relative">
      <div>
        <div class="stat-value num" style="font-size:1.4rem;">{{ stats.total }}</div>
        <div class="stat-label">Deals</div>
      </div>
      <div>
        <div class="stat-value num" style="font-size:1.4rem;">{{ formatNominal(stats.nominalTotal) }}</div>
        <div class="stat-label">Nominal total</div>
      </div>
      <div>
        <div class="text-slate-500 text-[10px] uppercase tracking-wider mb-0.5">Par statut</div>
        <div class="flex gap-1.5 flex-wrap">
          <span v-for="s in statusOptions" :key="s"
            v-show="stats.byStatus[s]"
            :class="statusClass(s)" class="badge">
            {{ s }} {{ stats.byStatus[s] }} ({{ pct(stats.byStatus[s], stats.total) }})
          </span>
        </div>
      </div>
      <div v-if="stats.byPayoffFamily.length">
        <div class="text-slate-500 text-[10px] uppercase tracking-wider mb-0.5">Par famille de payoff</div>
        <div class="flex gap-1.5 flex-wrap">
          <span v-for="[family, count] in stats.byPayoffFamily" :key="family" class="badge badge-muted">
            {{ family }} {{ count }} ({{ pct(count, stats.total) }})
          </span>
        </div>
      </div>
      <div v-if="stats.resolved">
        <div class="text-slate-500 text-[10px] uppercase tracking-wider mb-0.5">
          Hit ratio — {{ stats.resolved }} deal(s) résolu(s)
          <HelpTip text="Répartition des deals arrivés au bout de leur vie (callé, ou échu à maturité en KI ou en remboursement normal). Les deals encore actifs ne comptent pas dans ce ratio." />
        </div>
        <div class="flex gap-1.5 flex-wrap">
          <span v-if="stats.byOutcome.callé" class="badge badge-gold">
            callé {{ stats.byOutcome.callé }} ({{ pct(stats.byOutcome.callé, stats.resolved) }})
          </span>
          <span v-if="stats.byOutcome.final" class="badge badge-positive">
            final {{ stats.byOutcome.final }} ({{ pct(stats.byOutcome.final, stats.resolved) }})
          </span>
          <span v-if="stats.byOutcome.ki" class="badge badge-negative">
            ki {{ stats.byOutcome.ki }} ({{ pct(stats.byOutcome.ki, stats.resolved) }})
          </span>
        </div>
      </div>
      <div v-if="stats.avgRealizedPayout != null">
        <div class="stat-value num" style="font-size:1.4rem;">{{ formatPercent(stats.avgRealizedPayout * 100, 1) }}</div>
        <div class="stat-label">Remboursement moyen réalisé</div>
      </div>
    </div>
  </div>
</template>

<script setup>
// Extracted from BookingView.vue (P1-10, U3). The state stays in the
// view; this panel reads it through useBookingContext().
import AlertMessage from '../../components/ui/AlertMessage.vue'
import HelpTip from '../../components/HelpTip.vue'
import { alertChipClass, alertKindLabel, pct, statusClass, statusOptions } from './dealLabels.js'
import { formatPercent } from '../../utils/format.js'
import { useBookingContext } from './context.js'

const {
  alertError, alerts, formatNominal, markAllRead, markRead, markingAlerts, markingAll, stats,
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
