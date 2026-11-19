<template>
  <!-- ── Fiche détail dépliable ─────────────────────── -->
  <div v-if="expanded[d.id]" class="pt-3 border-t border-slate-800 flex flex-col gap-4">
    <div v-if="detailErrors[d.id]" role="alert" class="text-xs text-red-600">
      {{ detailErrors[d.id] }}
      <button class="btn-secondary" @click="loadDetail(d.id)">Réessayer le détail</button>
    </div>
    <div v-else-if="!details[d.id]" class="text-xs text-slate-600">Chargement du détail…</div>
    <template v-else>

      <!-- Barre de vie du produit -->
      <div>
        <div class="flex items-center justify-between text-[10px] text-slate-500 mb-1">
          <span>{{ formatDate(d.value_date) }}</span>
          <span v-if="lifePct(d) !== null" class="text-slate-400">
            {{ formatPercent(lifePct(d), 0) }} écoulé
          </span>
          <span>{{ formatDate(d.maturity_date) }}</span>
        </div>
        <div class="relative h-2.5 bg-slate-800 rounded-full">
          <div class="absolute inset-y-0 left-0 rounded-full"
            :class="d.status === 'callé' ? 'bg-amber-700/60' : d.status === 'échu' ? 'bg-slate-600' : 'bg-blue-800/70'"
            :style="{ width: (lifePct(d) ?? 0) + '%' }"></div>
          <!-- Aujourd'hui -->
          <div v-if="d.status === 'actif' && lifePct(d) !== null"
            class="absolute -top-1 -bottom-1 w-0.5 bg-amber-400"
            :style="{ left: lifePct(d) + '%' }" title="Aujourd'hui"></div>
          <!-- Constatations -->
          <!-- Liseré blanc : un point bleu reste lisible sur le remplissage bleu. -->
          <div v-for="ev in obsEvents(d.id)" :key="ev.id"
            class="absolute top-1/2 -translate-y-1/2 -translate-x-1/2 w-2.5 h-2.5 rounded-full border ring-2 ring-white"
            :class="eventDotClass(ev)"
            :style="{ left: eventPct(d, ev) + '%' }"
            :title="`${displayEventLabel(ev.label)} — ${ev.event_date} (${ev.status})`"></div>
        </div>
        <div class="flex gap-3 mt-1.5 text-[10px] text-slate-600 flex-wrap">
          <span><span class="inline-block w-2 h-2 rounded-full bg-blue-500 border border-blue-400 mr-1"></span>observé</span>
          <span><span class="inline-block w-2 h-2 rounded-full bg-amber-500 border border-amber-400 mr-1"></span>callé</span>
          <span><span class="inline-block w-2 h-2 rounded-full bg-emerald-500 border border-emerald-400 mr-1"></span>final</span>
          <span><span class="inline-block w-2 h-2 rounded-full bg-red-500 border border-red-400 mr-1"></span>KI</span>
          <span><span class="inline-block w-2 h-2 rounded-full bg-slate-900 border border-slate-600 mr-1"></span>futur</span>
          <span><span class="inline-block w-2 h-2 rounded-full bg-slate-700 border border-slate-600 mr-1 opacity-50"></span>annulé</span>
        </div>
      </div>

      <!-- Constatations (lecture seule) -->
      <div>
        <div class="flex items-center justify-between gap-3 mb-1.5">
          <div class="text-[10px] font-semibold text-slate-500 uppercase tracking-wider">
            Constatations ({{ compterConstatations(details[d.id].events) }})<template
              v-if="compterReleves(details[d.id].events)"> · {{ compterReleves(details[d.id].events) }} relevé(s)</template>
          </div>
          <button v-if="autoExceptionEvents(d.id).length"
            class="btn-secondary text-[10px] px-2 py-1 text-red-300 border-red-800/60"
            @click="openAutoException(d, autoExceptionEvents(d.id)[0])">
            Traiter {{ autoExceptionEvents(d.id).length }} exception(s)
          </button>
        </div>
        <div v-if="autoExceptionEvents(d.id).length"
          class="mb-2 rounded-lg border border-red-800/50 bg-red-950/25 px-3 py-2 text-xs text-red-300 flex items-center justify-between gap-3">
          <span>
            <strong>{{ autoExceptionEvents(d.id).length }} constatation(s) bloquent le lifecycle.</strong>
            L’utilisateur du deal doit choisir la valeur retenue et motiver sa décision.
          </span>
          <button class="btn-secondary text-[10px] px-2 py-1 shrink-0"
            @click="openAutoException(d, autoExceptionEvents(d.id)[0])">
            Traiter maintenant
          </button>
        </div>
        <div class="overflow-x-auto table-shell" tabindex="0" role="region">
          <table class="w-full text-xs border-collapse">
            <thead>
              <tr class="border-b border-slate-700 text-left text-slate-500">
                <th class="pb-1.5 pr-3 font-medium">#</th>
                <th class="pb-1.5 pr-3 font-medium whitespace-nowrap">Label</th>
                <th class="pb-1.5 pr-3 font-medium whitespace-nowrap">Date</th>
                <th v-for="u in details[d.id].underlyings" :key="u.name"
                  class="pb-1.5 pr-3 font-medium whitespace-nowrap">{{ u.ticker || u.name }}</th>
                <th class="pb-1.5 pr-3 font-medium whitespace-nowrap">Fixing</th>
                <th class="pb-1.5 pr-3 font-medium">Statut</th>
                <th class="pb-1.5 font-medium">Action</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="ev in ordonnerEvenements(details[d.id].events)" :key="ev.id"
                class="border-b border-slate-800/50"
                :class="ev.status === 'annulé' ? 'opacity-40' : ev.status === 'futur' ? 'opacity-60' : ''">
                <!-- Un relevé alimente la constatation au-dessus de lui : ni
                     numéroté, ni au même niveau (utils/dealEvents.js). -->
                <td class="py-1.5 pr-3 text-slate-500">{{ rangConstatation(details[d.id].events, ev) ?? '' }}</td>
                <td class="py-1.5 pr-3 whitespace-nowrap"
                  :class="estReleve(ev) ? 'text-slate-500 pl-6 text-[11px]' : 'text-slate-300'">
                  <span v-if="estReleve(ev)" class="text-slate-700 mr-1">↳</span>{{ displayEventLabel(ev.label) }}
                  <span v-if="ev.reduction"
                    class="ml-1.5 text-[9px] rounded px-1 py-0.5 border border-blue-800/60 text-blue-400"
                    :title="`Niveau constaté : ${libelleReduction(ev.reduction)} des cours de ses relevés, sous-jacent par sous-jacent.`">{{ ev.reduction }}</span>
                </td>
                <td class="py-1.5 pr-3 font-mono text-slate-300 whitespace-nowrap">{{ ev.event_date }}</td>
                <td v-for="u in details[d.id].underlyings" :key="u.name" class="py-1.5 pr-3 font-mono">
                  <template v-if="ev.spots[u.name]">
                    <span class="text-slate-200">{{ formatSpot(ev.spots[u.name]) }}</span>
                    <span v-if="ev.t_years > 0 && s0For(d.id, u.name)"
                      class="text-[10px] ml-1"
                      :class="ev.spots[u.name] >= s0For(d.id, u.name) ? 'text-emerald-400' : 'text-red-400'">
                      {{ ((ev.spots[u.name] / s0For(d.id, u.name) - 1) * 100) >= 0 ? '+' : '' }}{{ ((ev.spots[u.name] / s0For(d.id, u.name) - 1) * 100).toFixed(1) }}%
                    </span>
                  </template>
                  <span v-else class="text-slate-600">–</span>
                </td>
                <td class="py-1.5 pr-3">
                  <span :class="fixingStatusClass(ev.fixing_status)"
                    class="px-1.5 py-0.5 rounded text-[10px] font-medium whitespace-nowrap">
                    {{ fixingStatusLabel(ev.fixing_status) }}
                  </span>
                </td>
                <td class="py-1.5 pr-3">
                  <span :class="operationalEventClass(ev)"
                    class="px-1.5 py-0.5 rounded text-[10px] font-medium whitespace-nowrap">
                    {{ operationalEventLabel(ev) }}
                  </span>
                </td>
                <td class="py-1.5">
                  <button v-if="canResolveAutoException(d, ev)"
                    class="btn-secondary text-[10px] px-2 py-1 whitespace-nowrap"
                    @click="openAutoException(d, ev)">
                    Traiter
                  </button>
                  <span v-else class="text-slate-700">—</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- Explication de valo (P&L explain entre deux dates) -->
      <div v-if="d.status === 'actif'">
        <div class="text-[10px] font-semibold text-slate-500 uppercase tracking-wider mb-1.5">
          Explication de valo
          <HelpTip text="Décompose la variation de MtM entre deux dates avec la base de calcul sélectionnée plus haut (paramètres du booking ou marché actuel), par réévaluations successives à seed identique. Les flux détachés sur la période sont affichés à part." />
        </div>
        <div class="flex items-center gap-2 flex-wrap text-xs">
          <label class="text-slate-500">du</label>
          <input type="date" class="input text-xs py-1 w-auto"
            :value="explainD1[d.id] || defaultExplainStart(d)"
            :max="explainD2[d.id] || todayIso"
            @change="explainD1[d.id] = $event.target.value" />
          <label class="text-slate-500">au</label>
          <input type="date" class="input text-xs py-1 w-auto"
            :value="explainD2[d.id] || todayIso"
            :min="explainD1[d.id] || defaultExplainStart(d)" :max="todayIso"
            @change="explainD2[d.id] = $event.target.value" />
          <button class="btn-secondary text-xs px-3 py-1.5"
            :disabled="explainLoading[d.id] || !explainDatesValid(d)"
            @click="runExplain(d)">
            <span v-if="explainLoading[d.id]"
              class="w-3 h-3 border-2 border-slate-400 border-t-transparent rounded-full animate-spin inline-block mr-1"></span>
            ⚖ Expliquer
          </button>
        </div>
        <div v-if="!explainDatesValid(d)" class="text-[10px] text-red-500 mt-1">
          La date de début doit être antérieure ou égale à la date de fin.
        </div>
        <div v-if="explainResults[d.id]" class="mt-2">
          <div v-if="explainResults[d.id].error" class="text-amber-400 text-xs">
            ⚠ {{ explainResults[d.id].error }}
          </div>
          <template v-else>
            <table class="text-xs border-collapse w-full max-w-xl">
              <tbody>
                <tr class="border-b border-slate-700">
                  <td class="py-1 pr-3 text-slate-300 font-semibold">MtM au {{ explainResults[d.id].date1 }}</td>
                  <td class="py-1 font-mono text-slate-100 font-semibold text-right">{{ (explainResults[d.id].mtm1 * 100).toFixed(2) }}%</td>
                </tr>
                <tr v-for="s in explainResults[d.id].steps" :key="s.label" class="border-b border-slate-800/50">
                  <td class="py-1 pr-3 pl-3 text-slate-400">{{ s.label }}</td>
                  <td class="py-1 font-mono text-right"
                    :class="s.delta_pts >= 0 ? 'text-emerald-400' : 'text-red-400'">
                    {{ s.delta_pts >= 0 ? '+' : '' }}{{ s.delta_pts.toFixed(2) }} pts
                  </td>
                </tr>
                <tr class="border-b border-slate-800/50">
                  <td class="py-1 pr-3 pl-3 text-slate-500">Résidu non attribué</td>
                  <td class="py-1 font-mono text-slate-500 text-right">
                    {{ explainResults[d.id].residual_pts >= 0 ? '+' : '' }}{{ explainResults[d.id].residual_pts.toFixed(2) }} pts
                  </td>
                </tr>
                <tr class="border-b border-slate-700">
                  <td class="py-1 pr-3 text-slate-300 font-semibold">MtM au {{ explainResults[d.id].date2 }}</td>
                  <td class="py-1 font-mono text-slate-100 font-semibold text-right">{{ (explainResults[d.id].mtm2 * 100).toFixed(2) }}%</td>
                </tr>
                <tr class="border-b border-slate-800/50">
                  <td class="py-1 pr-3 text-slate-400">{{ explainResults[d.id].cash_basis === 'CONTRACTUAL_PAYMENT_DATE' ? 'Cash contractuel à échéance' : 'Flux détachés — ancien calcul' }}</td>
                  <td class="py-1 font-mono text-sky-400 text-right">{{ explainResults[d.id].flows_total_pts >= 0 ? '+' : '' }}{{ explainResults[d.id].flows_total_pts.toFixed(2) }} pts</td>
                </tr>
                <tr>
                  <td class="py-1 pr-3 text-slate-300 font-semibold">P&L total de la période</td>
                  <td class="py-1 font-mono font-semibold text-right"
                    :class="explainResults[d.id].pnl_total_pts >= 0 ? 'text-emerald-400' : 'text-red-400'">
                    {{ explainResults[d.id].pnl_total_pts >= 0 ? '+' : '' }}{{ explainResults[d.id].pnl_total_pts.toFixed(2) }} pts
                  </td>
                </tr>
              </tbody>
            </table>
            <ul class="mt-2 flex flex-col gap-1">
              <li v-for="(p, i) in explainResults[d.id].phrases" :key="i"
                class="text-[11px] text-slate-400">• {{ p }}</li>
            </ul>
            <button class="btn-secondary text-[10px] px-2 py-1 mt-2"
              :disabled="explainNoteLoading[d.id] || !explainResults[d.id]?.archive_id" @click="downloadExplainNote(d)"
              title="Génère la note PDF de l'explication de valo (waterfall, phrases, sensibilités Δ/Γ/véga en annexe) — mêmes chiffres que l'écran">
              <span v-if="explainNoteLoading[d.id]"
                class="w-3 h-3 border-2 border-slate-400 border-t-transparent rounded-full animate-spin inline-block mr-1"></span>
              📄 Note d'explication
            </button>
          </template>
        </div>
      </div>

    </template>
  </div>
</template>

<script setup>
// Extracted from BookingView.vue (P1-10, U3). The state stays in the
// view; this panel reads it through useBookingContext().
import HelpTip from '../../components/HelpTip.vue'
import { compterConstatations, compterReleves, estReleve, libelleReduction, ordonnerEvenements, rangConstatation } from '../../utils/dealEvents.js'
import { displayEventLabel, eventDotClass, eventPct, fixingStatusClass, fixingStatusLabel, formatSpot, operationalEventClass } from './dealLabels.js'
import { formatDate, formatPercent } from '../../utils/format.js'
import { useBookingContext } from './context.js'

defineProps({ d: { required: true } })
const {
  autoExceptionEvents, canResolveAutoException, defaultExplainStart, detailErrors, details,
  downloadExplainNote, expanded, explainD1, explainD2, explainDatesValid, explainLoading,
  explainNoteLoading, explainResults, lifePct, loadDetail, obsEvents, openAutoException,
  operationalEventLabel, runExplain, s0For, todayIso,
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

.deal-term strong {
  color: var(--text);
  font-family: 'JetBrains Mono', 'Fira Code', Consolas, monospace;
  font-weight: 700;
}

.deal-realized strong {
  color: var(--text);
  font-family: 'JetBrains Mono', 'Fira Code', Consolas, monospace;
}

.deal-perf.tone-pos { background: var(--positive-light); }

.deal-perf.tone-neg { background: var(--negative-light); }

.deal-underlying__levels strong {
  color: var(--text);
  font-family: 'JetBrains Mono', 'Fira Code', Consolas, monospace;
  font-size: 0.75rem;
  font-weight: 600;
}

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

.deal-barrier-row > strong {
  color: var(--text);
  font-family: 'JetBrains Mono', 'Fira Code', Consolas, monospace;
  font-size: 0.8125rem;
  font-weight: 700;
}

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

.deal-best-case strong {
  color: var(--text);
  font-family: 'JetBrains Mono', 'Fira Code', Consolas, monospace;
}

.deal-best-case span {
  color: #8a6508;
  font-weight: 600;
}

.deal-result-empty > strong {
  color: var(--text);
  font-size: 0.8125rem;
  font-weight: 700;
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
