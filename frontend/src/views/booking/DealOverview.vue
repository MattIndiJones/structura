<template>
  <!-- Vue synthétique : contrat, marché, repricing et résultat restent
       séparés pour qu'un niveau contractuel ne soit jamais lu comme
       une hypothèse du dernier calcul. Chaque panneau a sa teinte, pour
       que deux voisins ne se confondent pas ; les chiffres, eux, sont
       posés sur blanc et gardent toute leur lisibilité. -->
  <div class="deal-overview-grid">
    <section class="deal-panel deal-panel--contract">
      <header class="deal-panel__head">
        <span class="deal-panel__dot" aria-hidden="true"></span>
        <h3 class="deal-panel__title">Deal & economics</h3>
      </header>
      <div class="deal-well deal-figures">
        <div>
          <span class="deal-label">Nominal</span>
          <strong class="deal-value">{{ formatNominal(d.nominal) }} {{ d.devise }}</strong>
        </div>
        <div>
          <span class="deal-label">Prix traité</span>
          <strong class="deal-value">{{ d.price_traded.toFixed(2) }}%</strong>
        </div>
        <div>
          <span class="deal-label">Fair value</span>
          <strong class="deal-value is-secondary">{{ d.fair_value.toFixed(2) }}%</strong>
        </div>
        <div>
          <span class="deal-label">Marge</span>
          <strong class="deal-value" :class="signToneClass(d.margin)">
            {{ d.margin >= 0 ? '+' : '' }}{{ d.margin.toFixed(2) }}%
          </strong>
        </div>
      </div>
      <dl class="deal-dates">
        <div><dt>Trade</dt><dd>{{ formatDate(d.trade_date) }}</dd></div>
        <div><dt>Strike</dt><dd>{{ formatDate(d.strike_date) }}</dd></div>
        <div><dt>Value</dt><dd>{{ formatDate(d.value_date) }}</dd></div>
        <div><dt>Maturité</dt><dd>{{ formatDate(d.maturity_date) }}</dd></div>
        <div><dt>Paiement</dt><dd>{{ formatDate(d.payment_date) }}</dd></div>
      </dl>
      <div v-if="details[d.id]?.terms?.length" class="deal-term-list">
        <div v-for="t in primaryTerms(details[d.id].terms)" :key="t.name"
          class="deal-term" :title="`${t.name}${t.desc ? ` — ${t.desc}` : ''}`">
          <span>{{ termBusinessLabel(t.name) }}</span>
          <strong>{{ formatTerm(t) }}</strong>
        </div>
        <details v-if="details[d.id].terms.length > primaryTerms(details[d.id].terms).length"
          class="deal-technical-details">
          <summary>Voir les {{ details[d.id].terms.length }} termes contractuels</summary>
          <div class="deal-term-list mt-2">
            <div v-for="t in details[d.id].terms" :key="t.name" class="deal-term" :title="t.desc || t.name">
              <span>{{ termBusinessLabel(t.name) }}</span>
              <strong>{{ formatTerm(t) }}</strong>
            </div>
          </div>
        </details>
      </div>
      <div v-if="d.realized_payout != null" class="deal-realized">
        Remboursement réalisé :
        <strong>{{ (d.realized_payout * 100).toFixed(2) }}%</strong>
        <span v-if="d.resolution_outcome"> ({{ d.resolution_outcome }})</span>
      </div>
    </section>

    <section class="deal-panel deal-panel--market">
      <header class="deal-panel__head">
        <span class="deal-panel__dot" aria-hidden="true"></span>
        <h3 class="deal-panel__title">Sous-jacents & niveaux</h3>
      </header>
      <div class="deal-well deal-underlyings">
        <div v-for="u in d.underlyings" :key="u.name" class="deal-underlying">
          <div class="deal-underlying__top">
            <span class="deal-underlying__name" :title="u.name">{{ u.ticker || u.name }}</span>
            <span v-if="wlUnderlying(d.id, u.name)?.perf != null"
              class="deal-perf" :class="signToneClass(wlUnderlying(d.id, u.name).perf - 1)"
              title="Performance depuis le strike">
              {{ signedPercent((wlUnderlying(d.id, u.name).perf - 1) * 100, 1) }}
            </span>
          </div>
          <div class="deal-underlying__levels">
            <span>Strike <strong>{{ formatSpot(strikeFor(d.id, u.name)) }}</strong></span>
            <span class="deal-underlying__arrow" aria-hidden="true">→</span>
            <span>Cours actuel <strong>{{ formatSpot(wlUnderlying(d.id, u.name)?.spot) }}</strong></span>
          </div>
        </div>
      </div>
      <div v-if="wlRow(d.id)?.barriers?.length" class="deal-well deal-barriers">
        <!-- Règle : position de l'observable entre protection et rappel,
             relue des écarts ci-dessous (utils/barriers.js). -->
        <div v-for="g in barrierGauges(wlRow(d.id).barriers)" :key="g.observable" class="barrier-gauge">
          <div class="barrier-gauge__caption">
            <span>{{ gaugeObservableLabel(d, g.observable) }}</span>
            <span>en % du strike</span>
          </div>
          <div class="barrier-gauge__track" role="img" :aria-label="gaugeAriaLabel(d, g)">
            <div v-if="g.lossZonePct != null" class="barrier-gauge__zone barrier-gauge__zone--loss"
              :style="{ width: `${g.lossZonePct}%` }"></div>
            <div v-if="g.gainZonePct != null" class="barrier-gauge__zone barrier-gauge__zone--gain"
              :style="{ width: `${g.gainZonePct}%` }"></div>
            <div v-for="m in g.marks" :key="m.name"
              class="barrier-gauge__mark" :class="`barrier-gauge__mark--${m.kind}`"
              :style="{ left: `${m.pct}%` }"
              :title="`${barrierBusinessLabel(m)} — ${formatGaugeLevel(m.level)}`">
              <span v-if="m.labelled">{{ formatGaugeLevel(m.level) }}</span>
            </div>
            <div class="barrier-gauge__cursor" :style="{ left: `${g.currentPct}%` }">
              <span>{{ formatGaugeLevel(g.current) }}</span>
            </div>
          </div>
        </div>
        <div v-for="b in wlRow(d.id).barriers" :key="b.name" class="deal-barrier-row">
          <span class="deal-barrier-row__tick" :class="`deal-barrier-row__tick--${b.kind}`"
            aria-hidden="true"></span>
          <div class="min-w-0">
            <span class="deal-barrier-name">{{ barrierBusinessLabel(b) }}</span>
            <span class="deal-barrier-code">{{ b.name }}</span>
          </div>
          <strong>{{ (b.level * 100).toFixed(0) }}%</strong>
          <span :class="barrierChipClass(b)"
            class="px-1.5 py-0.5 rounded text-[10px] font-mono font-semibold whitespace-nowrap">
            {{ barrierGapLabel(b) }}
          </span>
        </div>
      </div>
      <div v-else class="deal-empty-state">
        {{ d.status === 'actif' ? 'Aucune barrière détectée dans le script.' : 'Niveaux de marché non suivis sur ce deal.' }}
      </div>
    </section>

    <section class="deal-panel deal-panel--model">
      <header class="deal-panel__head">
        <span class="deal-panel__dot" aria-hidden="true"></span>
        <h3 class="deal-panel__title">Paramètres de repricing</h3>
      </header>
      <label v-if="d.status === 'actif'" class="deal-basis">
        <span class="deal-label">Base du calcul</span>
        <select class="select deal-panel__select w-full text-xs py-1.5"
          :value="mtmModeFor(d.id)" :disabled="mtmLoading[d.id] || authStore.readOnly" @click.stop
          @change="setMtmMode(d.id, $event.target.value)"
          title="Choix des hypothèses utilisées pour le prochain calcul">
          <option value="realized">Marché actuel</option>
          <option value="booking">Paramètres du booking</option>
        </select>
      </label>
      <div v-else class="deal-basis">
        <span class="deal-label">Base du calcul</span>
        <strong class="deal-value">{{ mtmModeFor(d.id) === 'realized' ? 'Marché actuel' : 'Paramètres du booking' }}</strong>
      </div>
      <label v-if="['actif', 'en_reglement'].includes(d.status)" class="deal-basis">
        <span class="deal-label">Date de valorisation</span>
        <input type="date" class="input deal-panel__select w-full text-xs py-1.5"
          :disabled="mtmLoading[d.id] || authStore.readOnly" :value="mtmDateFor(d.id)" :min="mtmMinDate(d)" :max="todayIso"
          @click.stop @change="setMtmDate(d.id, $event.target.value)"
          title="Date à laquelle le deal et son marché sont valorisés" />
      </label>
      <label class="deal-basis">
        <span class="deal-label">Grille de diffusion (pas/an)</span>
        <select class="select deal-panel__select w-full text-xs py-1.5" :aria-label="'Grille de valorisation ' + d.id"
          :value="mtmGridChoiceFor(d.id)" :disabled="mtmLoading[d.id] || authStore.readOnly" @click.stop
          @change="setMtmGrid(d.id, $event.target.value)">
          <option value="booking">Grille du booking — {{ bookedGrid(d.market_snapshot) }} pas/an</option>
          <option :value="52">52 — rapide</option><option :value="104">104 — intermédiaire</option><option :value="208">208 — fin</option>
        </select>
      </label>
      <p v-if="mtmGridFor(d.id) !== bookedGrid(d.market_snapshot)" class="deal-alert" role="status">
        {{ valuationGridWarning(bookedGrid(d.market_snapshot), mtmGridFor(d.id)) }}
      </p>
      <p v-if="mtmResults[d.id]?.market_used?.surface_context" class="deal-basis-note">
        Surface ancrée au spot courant, fixings contractuels conservés.
        <span v-if="mtmResults[d.id].market_used.surface_context.variance_policy === 'CONTEXT_V0_ASSUMPTION'">
          v₀ est l’hypothèse de variance du contexte, pas une observation de marché.
        </span>
      </p>
      <p v-if="surfaceBenchmarkIssues(mtmResults[d.id]?.market_used?.lsv_calibration).length" class="deal-alert" role="note">
        Contrôle direct SSVI : {{ surfaceBenchmarkIssues(mtmResults[d.id].market_used.lsv_calibration).length }} point(s) hors incertitude et tolérance. Affiner la grille ; la qualification du levier par rapport à Dupire est distincte.
      </p>
      <p class="deal-basis-note">
        {{ mtmModeFor(d.id) === 'realized'
          ? 'Volatilité réalisée du marché actuel : calcul en GBM. Le taux et le funding restent ceux du booking.'
          : 'Paramètres de modèle, volatilités et corrélations du booking, avec les cours disponibles à la date du calcul.' }}
      </p>
      <div class="deal-well deal-figures">
        <div>
          <span class="deal-label">Modèle</span>
          <strong class="deal-value">{{ repricingModelLabel(d) }}</strong>
        </div>
        <div>
          <span class="deal-label">Taux</span>
          <strong class="deal-value">{{ effectiveRateLabel(d) }}</strong>
        </div>
        <div>
          <span class="deal-label">Funding</span>
          <strong class="deal-value">{{ effectiveFundingLabel(d) }}</strong>
        </div>
        <div>
          <span class="deal-label">Source</span>
          <strong class="deal-value">{{ effectiveProviderLabel(d) }}</strong>
        </div>
      </div>
      <details v-if="mtmResults[d.id]?.market_used" class="deal-technical-details">
        <summary>Voir le détail du dernier calcul</summary>
        <p>{{ marketUsedLabel(mtmResults[d.id].market_used) }}</p>
      </details>
      <div v-if="mtmResults[d.id]?.market_used?.data?.contractual_history?.warnings?.length"
        class="deal-alert" role="note">
        <span aria-hidden="true">⚠</span>
        <span>La dernière clôture disponible est ancienne pour au moins un sous-jacent.</span>
      </div>
    </section>

    <section class="deal-panel deal-panel--result">
      <header class="deal-panel__head">
        <span class="deal-panel__dot" aria-hidden="true"></span>
        <h3 class="deal-panel__title">Résultat</h3>
        <RouterLink :to="`/booking/${d.id}/valuations`"
          class="deal-history-link" @click.stop>
          Historique
        </RouterLink>
      </header>
      <!-- Rien de calculé (ou calcul en cours) : l'action est au centre du
           panneau plutôt qu'en bas d'un grand vide. -->
      <div v-if="!mtmResults[d.id]" class="deal-result-empty" role="status" aria-live="polite">
        <template v-if="['actif', 'en_reglement'].includes(d.status)">
          <strong>{{ mtmLoading[d.id] ? mtmProgressLabel(d.id) : 'Aucun MtM pour cette sélection' }}</strong>
          <span>
            {{ mtmLoading[d.id] ? 'Valorisation avec' : 'Le calcul utilisera' }}
            {{ mtmModeFor(d.id) === 'realized' ? 'le marché actuel' : 'les paramètres du booking' }}
            au {{ formatDate(mtmDateFor(d.id)) }}.
          </span>
          <span v-if="mtmLoading[d.id] && mtmModeFor(d.id) === 'realized'">
            Les données en cache sont réutilisées si valides ; les données manquantes sont chargées avant le calcul.
          </span>
          <span v-else-if="!mtmLoading[d.id]">Seuls les calculs du jour sont réaffichés. Les précédents restent dans l’historique.</span>
          <button class="btn-primary text-xs px-3 py-1.5 mt-1"
            :disabled="mtmLoading[d.id] || authStore.readOnly" @click.stop="runMtm(d.id)"
            :title="mtmButtonTitle(d)">
            <span v-if="mtmLoading[d.id]"
              class="w-3 h-3 border-2 border-slate-200 border-t-transparent rounded-full animate-spin inline-block mr-1"></span>
            Calculer le MTM
          </button>
        </template>
        <template v-else>
          <strong>Pas de MTM à calculer</strong>
          <span>Le produit n’est plus en vie.</span>
        </template>
      </div>
      <template v-else>
        <div v-if="mtmResults[d.id].error" class="deal-alert" role="alert">
          <span aria-hidden="true">⚠</span><span>{{ mtmResults[d.id].error }}</span>
        </div>
        <div v-else-if="mtmResults[d.id].resolved_pending" class="deal-alert" role="note">
          <span aria-hidden="true">⚠</span><span>{{ mtmResults[d.id].message }}</span>
        </div>
        <template v-else>
          <div>
            <span class="deal-label">MtM</span>
            <div class="deal-mtm__value">{{ (mtmResults[d.id].mtm * 100).toFixed(2) }}%</div>
            <div class="deal-mtm__ci">
              IC 95% · {{ (mtmResults[d.id].ic95[0] * 100).toFixed(2) }}% à {{ (mtmResults[d.id].ic95[1] * 100).toFixed(2) }}%
            </div>
            <div class="deal-mtm__ci">
              Valorisation au {{ formatDate(mtmResultDate(d.id)) }}
              · grille {{ mtmResults[d.id].market_used?.steps_per_year ?? 52 }} pas/an
              <span v-if="mtmResults[d.id].market_used?.lsv_calibration?.status === 'QUALIFIED'"> · levier LSV qualifié vs Dupire (même grille)</span>
              <span v-if="mtmResults[d.id]._runCreatedAt">
                · {{ mtmResults[d.id]._restored ? (authStore.readOnly ? 'calcul archivé, enregistré le' : 'calcul du jour restauré, enregistré le') : 'calcul effectué le' }} {{ new Date(mtmResults[d.id]._runCreatedAt).toLocaleString('fr-FR') }}
              </span>
            </div>
          </div>
          <div class="deal-result-grid">
            <div>
              <span class="deal-label">Écart vs traité</span>
              <strong class="deal-value" :class="signToneClass(mtmResults[d.id].mtm * 100 - d.price_traded)">
                {{ signedNumber(mtmResults[d.id].mtm * 100 - d.price_traded, 2) }} pts
              </strong>
            </div>
            <div>
              <span class="deal-label">Vie restante</span>
              <strong class="deal-value">{{ mtmResults[d.id].T_remaining.toFixed(2) }} an(s)</strong>
            </div>
            <div v-if="mtmResults[d.id].pre_strike">
              <span class="deal-label">État</span>
              <strong class="deal-value tone-info">Avant strike</strong>
            </div>
            <div v-else>
              <span class="deal-label">Observations passées</span>
              <strong class="deal-value">{{ mtmResults[d.id].obs_passees }}</strong>
            </div>
            <div v-if="mtmResults[d.id].wof_min_realized != null">
              <span class="deal-label">Worst-of min réalisé</span>
              <strong class="deal-value">{{ (mtmResults[d.id].wof_min_realized * 100).toFixed(1) }}%</strong>
            </div>
            <div v-if="mtmResults[d.id].unsettled_total">
              <span class="deal-label">À régler</span>
              <strong class="deal-value tone-warn">{{ (mtmResults[d.id].unsettled_total * 100).toFixed(2) }}%</strong>
            </div>
          </div>
          <div v-if="mtmResults[d.id].best_case?.capped" class="deal-best-case">
            Meilleur scénario : <strong>{{ (mtmResults[d.id].best_case.pv_max * 100).toFixed(2) }}%</strong>
            <span v-if="mtmResults[d.id].best_case.exit_signal"> · sortie envisageable</span>
          </div>
        </template>
        <div class="deal-result-actions">
          <button v-if="['actif', 'en_reglement'].includes(d.status)" class="btn-primary text-xs px-3 py-1.5"
            :disabled="mtmLoading[d.id] || authStore.readOnly" @click.stop="runMtm(d.id)"
            :title="mtmButtonTitle(d)">
            <span v-if="mtmLoading[d.id]"
              class="w-3 h-3 border-2 border-slate-200 border-t-transparent rounded-full animate-spin inline-block mr-1"></span>
            Calculer le MTM
          </button>
          <RouterLink v-if="d.status === 'actif' && mtmResults[d.id]?.valuation_run_id"
            class="btn-secondary text-[10px] px-2 py-1"
            :to="{ path: '/valo-explain', query: { deal: d.id, run: mtmResults[d.id].valuation_run_id, auto: '1' } }"
            @click.stop title="Ouvrir Valo Explain à partir de ce calcul enregistré">
            📄 Note de valo
          </RouterLink>
          <button v-if="d.status === 'actif' && mtmResults[d.id]?.mtm != null"
            class="btn-secondary text-[10px] px-2 py-1" :disabled="rollLoading[d.id]"
            @click.stop="runRoll(d)" title="Reprice le même produit avec un nouveau départ forward">
            🔄 Relancer un prix
          </button>
        </div>
      </template>
    </section>
  </div>
</template>

<script setup>
// Extracted from BookingView.vue (P1-10, U3). The state stays in the
// view; this panel reads it through useBookingContext().
import { RouterLink } from 'vue-router'
import { barrierBusinessLabel, formatGaugeLevel, formatSpot, formatTerm, marketUsedLabel, mtmButtonTitle, mtmMinDate, primaryTerms, signToneClass, signedNumber, signedPercent, termBusinessLabel } from './dealLabels.js'
import { barrierChipClass, barrierGapLabel, barrierGauges } from '../../utils/barriers.js'
import { bookedGrid, valuationGridWarning } from '../../utils/simulationGrid.js'
import { formatDate } from '../../utils/format.js'
import { surfaceBenchmarkIssues } from '../../utils/lsvDiagnostics.js'
import { useBookingContext } from './context.js'

defineProps({ d: { required: true } })
const {
  authStore, details, effectiveFundingLabel, effectiveProviderLabel, effectiveRateLabel,
  formatNominal, gaugeAriaLabel, gaugeObservableLabel, mtmDateFor, mtmGridChoiceFor, mtmGridFor,
  mtmLoading, mtmModeFor, mtmProgressLabel, mtmResultDate, mtmResults, repricingModelLabel,
  rollLoading, runMtm, runRoll, setMtmDate, setMtmGrid, setMtmMode, strikeFor, todayIso, wlRow,
  wlUnderlying,
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

/* ── Synthèse du deal : quatre panneaux, une identité chacun ──────────────
   La teinte dit de quoi parle le panneau (contrat, marché, hypothèses,
   résultat) et deux voisins n'ont jamais la même, en 4, 2 ou 1 colonne. Les
   chiffres sont posés sur des cuvettes blanches et le texte reste encre :
   aucune écriture de couleur sur un fond de la même couleur (le badge bleu
   sur panneau bleu était illisible). */

.deal-overview-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 0.9rem;
  padding-top: 0.9rem;
  border-top: 1px solid var(--border);
}

.deal-panel {
  --panel-tint: var(--surface);
  --panel-edge: var(--border);
  --panel-accent: var(--muted);
  position: relative;
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 0.75rem;
  border: 1px solid var(--panel-edge);
  border-top: 3px solid var(--panel-accent);
  border-radius: 12px;
  background: var(--panel-tint);
  padding: 0.8rem 0.9rem 0.9rem;
  box-shadow: 0 1px 2px rgba(26, 24, 20, 0.05);
  transition: transform 200ms cubic-bezier(0.2, 0.8, 0.2, 1), box-shadow 200ms ease, border-color 200ms ease;
}

.deal-panel--contract { --panel-tint: #f4f6f9; --panel-edge: #d6dce5; --panel-accent: #52627a; }

.deal-panel--market { --panel-tint: #edf7f4; --panel-edge: #c3e1d8; --panel-accent: #14806f; }

.deal-panel--model { --panel-tint: #f5f1fc; --panel-edge: #d9cfef; --panel-accent: #6e51bd; }

.deal-panel--result { --panel-tint: var(--surface); --panel-edge: #b7cfeb; --panel-accent: var(--accent); }

.deal-panel:focus-within {
  border-color: var(--panel-accent);
}

@media (hover: hover) and (prefers-reduced-motion: no-preference) {
  .deal-panel:hover {
    z-index: 2;
    transform: scale(1.04);
    box-shadow: 0 18px 38px -14px rgba(26, 24, 20, 0.32), 0 3px 8px rgba(26, 24, 20, 0.06);
  }
}

@media (hover: hover) and (prefers-reduced-motion: no-preference) and (max-width: 1350px) {
  .deal-panel:hover {
    transform: scale(1.025);
  }
}

@media (hover: hover) and (prefers-reduced-motion: reduce) {
  .deal-panel:hover {
    box-shadow: 0 0 0 2px var(--panel-accent);
  }
}

.deal-panel__head {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.deal-panel__dot {
  width: 0.5rem;
  height: 0.5rem;
  flex: 0 0 auto;
  border-radius: 2px;
  background: var(--panel-accent);
}

.deal-panel__title {
  color: #2f2b25;
  font-size: 0.6875rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  line-height: 1.2;
  text-transform: uppercase;
}

.deal-history-link {
  margin-left: auto;
  border-bottom: 1px solid transparent;
  color: var(--accent);
  font-size: 0.65rem;
  font-weight: 700;
}

.deal-history-link:hover {
  border-bottom-color: var(--accent);
}

.deal-well {
  border: 1px solid var(--panel-edge);
  border-radius: 9px;
  background: var(--surface);
}

.deal-label {
  display: block;
  color: #635d53;
  font-size: 0.6875rem;
  font-weight: 500;
  line-height: 1.2;
}

.deal-value {
  display: block;
  margin-top: 0.2rem;
  color: var(--text);
  font-family: 'JetBrains Mono', 'Fira Code', Consolas, monospace;
  font-size: 0.78rem;
  font-variant-numeric: tabular-nums;
  font-weight: 600;
  line-height: 1.3;
  overflow-wrap: anywhere;
}

.deal-value.is-secondary {
  color: #57524a;
  font-weight: 500;
}

.deal-figures {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
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

/* ── Contrat ── */

.deal-dates {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0.55rem 0.75rem;
  padding: 0 0.15rem;
}

.deal-dates dt {
  color: #635d53;
  font-size: 0.6875rem;
  line-height: 1.2;
}

.deal-dates dd {
  margin-top: 0.15rem;
  color: var(--text);
  font-family: 'JetBrains Mono', 'Fira Code', Consolas, monospace;
  font-size: 0.75rem;
  font-variant-numeric: tabular-nums;
  font-weight: 600;
  white-space: nowrap;
}

.deal-term-list {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
}

.deal-term {
  display: inline-flex;
  align-items: baseline;
  gap: 0.35rem;
  border: 1px solid var(--panel-edge);
  border-radius: 999px;
  background: var(--surface);
  padding: 0.2rem 0.55rem;
  color: #57524a;
  font-size: 0.6875rem;
}

.deal-term strong {
  color: var(--text);
  font-family: 'JetBrains Mono', 'Fira Code', Consolas, monospace;
  font-weight: 700;
}

.deal-realized {
  color: #57524a;
  font-size: 0.75rem;
}

.deal-realized strong {
  color: var(--text);
  font-family: 'JetBrains Mono', 'Fira Code', Consolas, monospace;
}

.deal-technical-details {
  color: #57524a;
  font-size: 0.6875rem;
}

.deal-technical-details summary {
  width: fit-content;
  cursor: pointer;
  color: #3d382f;
  font-weight: 600;
  text-decoration: underline;
  text-decoration-color: var(--panel-edge);
  text-underline-offset: 3px;
}

.deal-technical-details p {
  margin-top: 0.4rem;
  color: #57524a;
  font-family: 'JetBrains Mono', 'Fira Code', Consolas, monospace;
  line-height: 1.45;
}

/* ── Marché ── */

.deal-underlying {
  padding: 0.5rem 0.65rem;
}

.deal-underlying + .deal-underlying {
  border-top: 1px solid var(--border);
}

.deal-underlying__top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
}

.deal-underlying__name {
  overflow: hidden;
  color: var(--text);
  font-family: 'JetBrains Mono', 'Fira Code', Consolas, monospace;
  font-size: 0.8125rem;
  font-weight: 700;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.deal-perf {
  flex: 0 0 auto;
  border-radius: 999px;
  background: var(--surface2);
  padding: 0.1rem 0.5rem;
  color: #57524a;
  font-family: 'JetBrains Mono', 'Fira Code', Consolas, monospace;
  font-size: 0.75rem;
  font-weight: 700;
}

.deal-perf.tone-pos { background: var(--positive-light); }

.deal-perf.tone-neg { background: var(--negative-light); }

.deal-underlying__levels {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 0.2rem 0.4rem;
  margin-top: 0.25rem;
  color: #635d53;
  font-size: 0.6875rem;
}

.deal-underlying__levels strong {
  color: var(--text);
  font-family: 'JetBrains Mono', 'Fira Code', Consolas, monospace;
  font-size: 0.75rem;
  font-weight: 600;
}

.deal-underlying__arrow {
  color: var(--subtle);
}

.deal-barriers > * + * {
  border-top: 1px solid var(--border);
}

/* Règle des barrières : zones, repères et curseur sont placés en % de la
   largeur par barrierGauges (utils/barriers.js). */

.barrier-gauge {
  padding: 0.55rem 0.65rem 0.45rem;
}

.barrier-gauge__caption {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 0.5rem;
  font-size: 0.6875rem;
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

.barrier-gauge__track {
  position: relative;
  height: 0.5rem;
  margin: 1.35rem 0.4rem 1.3rem;
  border-radius: 999px;
  background: #e9e6df;
}

.barrier-gauge__zone {
  position: absolute;
  top: 0;
  bottom: 0;
}

.barrier-gauge__zone--loss {
  left: 0;
  border-radius: 999px 0 0 999px;
  background: #f3c4bd;
}

.barrier-gauge__zone--gain {
  right: 0;
  border-radius: 0 999px 999px 0;
  background: #b9e0c9;
}

.barrier-gauge__mark {
  position: absolute;
  top: -0.3rem;
  bottom: -0.3rem;
  width: 2px;
  margin-left: -1px;
  border-radius: 1px;
  background: var(--muted);
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

.barrier-gauge__cursor {
  position: absolute;
  top: 50%;
  width: 0.85rem;
  height: 0.85rem;
  margin: -0.425rem 0 0 -0.425rem;
  border: 2px solid var(--surface);
  border-radius: 999px;
  background: var(--text);
  box-shadow: 0 1px 3px rgba(26, 24, 20, 0.35);
}

.barrier-gauge__cursor span {
  top: calc(100% + 0.25rem);
  color: var(--text);
}

.deal-barrier-row {
  display: grid;
  grid-template-columns: 0.2rem minmax(0, 1fr) auto auto;
  align-items: center;
  gap: 0.5rem;
  padding: 0.45rem 0.65rem 0.45rem 0.5rem;
}

.deal-barrier-row__tick {
  align-self: stretch;
  border-radius: 2px;
  background: var(--border2);
}

.deal-barrier-row__tick--ki { background: var(--negative); }

.deal-barrier-row__tick--autocall { background: var(--positive); }

.deal-barrier-name {
  display: block;
  color: #3d382f;
  font-size: 0.75rem;
  font-weight: 500;
  line-height: 1.25;
}

.deal-barrier-code {
  display: block;
  color: var(--subtle);
  font-family: 'JetBrains Mono', 'Fira Code', Consolas, monospace;
  font-size: 0.625rem;
}

.deal-barrier-row > strong {
  color: var(--text);
  font-family: 'JetBrains Mono', 'Fira Code', Consolas, monospace;
  font-size: 0.8125rem;
  font-weight: 700;
}

.deal-empty-state {
  color: #57524a;
  font-size: 0.75rem;
  line-height: 1.45;
}

/* ── Hypothèses ── */

.deal-basis {
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
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

.deal-basis-note {
  color: #4f4a42;
  font-size: 0.75rem;
  line-height: 1.45;
}

.deal-alert {
  display: flex;
  align-items: flex-start;
  gap: 0.4rem;
  border: 1px solid rgba(184, 134, 11, 0.35);
  border-radius: 8px;
  background: var(--gold-light);
  padding: 0.45rem 0.6rem;
  color: #6f5207;
  font-size: 0.6875rem;
  line-height: 1.4;
}

/* ── Résultat ── */

.deal-mtm__value {
  margin-top: 0.15rem;
  color: var(--accent);
  font-family: 'JetBrains Mono', 'Fira Code', Consolas, monospace;
  font-size: 1.9rem;
  font-variant-numeric: tabular-nums;
  font-weight: 700;
  letter-spacing: -0.03em;
  line-height: 1.05;
}

.deal-mtm__ci {
  margin-top: 0.25rem;
  color: #635d53;
  font-family: 'JetBrains Mono', 'Fira Code', Consolas, monospace;
  font-size: 0.6875rem;
}

.deal-result-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.6rem 0.8rem;
  border-top: 1px solid var(--border);
  padding-top: 0.7rem;
}

.deal-best-case {
  border-radius: 8px;
  background: var(--surface2);
  padding: 0.45rem 0.6rem;
  color: #4f4a42;
  font-size: 0.6875rem;
}

.deal-best-case strong {
  color: var(--text);
  font-family: 'JetBrains Mono', 'Fira Code', Consolas, monospace;
}

.deal-best-case span {
  color: #8a6508;
  font-weight: 600;
}

.deal-result-empty {
  display: flex;
  flex: 1 1 auto;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.35rem;
  min-height: 8rem;
  border: 1px dashed var(--panel-edge);
  border-radius: 9px;
  padding: 1rem;
  text-align: center;
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

.deal-result-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
  margin-top: auto;
}

/* Couleurs de signe en dernier, sous le panneau : elles doivent l'emporter
   sur toutes les couleurs de base ci-dessus. */

.deal-panel .tone-pos { color: var(--positive); }

.deal-panel .tone-neg { color: var(--negative); }

.deal-panel .tone-warn { color: #8a6508; }

.deal-panel .tone-info { color: #0369a1; }

@media (max-width: 1350px) {
  .deal-overview-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 900px) {

  .deal-overview-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
