<template>
  <div v-if="refreshResults[d.id]" class="text-xs pt-2 border-t border-slate-800"
    :class="refreshResults[d.id].startsWith('⚠') ? 'text-amber-400' : 'text-slate-400'">
    {{ refreshResults[d.id] }}
  </div>

  <!-- ── Greeks (bump-and-reprice CRN) ─────────────────── -->
  <div v-if="greeksFor(d)" class="text-xs pt-2 border-t border-slate-800">
    <div v-if="greeksFor(d).error" class="text-amber-400">⚠ {{ greeksFor(d).error }}</div>
    <div v-else-if="greeksFor(d).resolved_pending" class="text-amber-400">
      ⚠ {{ greeksFor(d).message }}
    </div>
    <div v-else class="flex flex-col gap-1">
      <div class="flex flex-wrap items-center gap-x-4 gap-y-1">
        <span class="text-slate-500">Δ Greeks :
          <HelpTip text="Bump-and-reprice CRN (common random numbers) — dérivées brutes du prix (% du nominal résiduel) par rapport à leur variable de bump : δ/γ pour 100% de variation du spot, ν et ρ pour 100 points (de vol / de taux) de variation — pas pour 1 point. L'agrégat par portefeuille reconvertit ρ en EUR par 1 point de taux (÷100) ; ici ce sont les valeurs brutes. Cliquez Recalculer pour rafraîchir." />
        </span>
        <span v-for="(g, name) in greeksFor(d).per_underlying" :key="name" class="font-mono">
          <span class="text-slate-500">{{ name }}</span>
          <span class="ml-1"
            :class="greeksFor(d).pre_strike ? 'text-sky-300' : 'text-slate-300'">
            δ {{ g.delta?.toFixed(3) }}<span v-if="greeksFor(d).pre_strike" class="text-[10px]"> {{ greeksFor(d).pre_strike.modele_porte_le_smile ? 'smile' : 'nul' }}</span>
          </span>
          <span v-if="g.gamma != null" class="text-slate-400 ml-1">γ {{ g.gamma?.toFixed(3) }}</span>
          <span v-if="g.vega != null" class="text-slate-400 ml-1">ν {{ g.vega?.toFixed(3) }}</span>
        </span>
        <span v-if="greeksFor(d).scalar?.theta != null" class="font-mono text-slate-400">
          θ {{ greeksFor(d).scalar.theta.toFixed(4) }}
        </span>
        <span v-else-if="greeksFor(d).theta_event?.reason" class="font-mono text-slate-500">
          θ n/d
          <HelpTip text="Theta non calculé : vieillir ce produit d'une semaine demanderait une transition d'état qui ne peut pas être reconstruite exactement — observation contractuelle, fixing ou volatilité réalisée dans la fenêtre. Mémoire, accumulation, terminaison et nouveaux fixings doivent d'abord être constatés. Un theta absent vaut mieux qu'un theta faux." />
        </span>
        <span v-if="greeksFor(d).scalar?.rho != null" class="font-mono text-slate-400">
          ρ {{ greeksFor(d).scalar.rho.toFixed(4) }}
        </span>
      </div>
      <div v-if="greeksFor(d).pre_strike"
        class="flex items-start gap-1.5 text-xs text-sky-300/80">
        <span class="shrink-0">↳</span>
        <span>{{ greeksFor(d).pre_strike.message }}</span>
      </div>
      <div v-if="greeksFor(d).theta_event?.pv_pts != null"
        class="flex flex-wrap items-center gap-x-2 text-xs text-amber-300/80">
        <span>Observation dans les 7 jours :
          {{ greeksFor(d).theta_event.labels?.join(', ') || 'flux' }}
          de {{ greeksFor(d).theta_event.pv_pts.toFixed(2) }} pts</span>
        <HelpTip text="Un flux se détache pendant la semaine que mesure le theta. Il est reporté ici plutôt que compté comme de la décroissance temporelle : un coupon de 5% détaché en 7 jours donnerait un theta de -0,7 par jour, exact au niveau du deal mais ininterprétable une fois sommé sur le livre. Le θ affiché ne mesure que la décroissance, hors ce flux." />
        <span v-if="greeksFor(d).theta_event.terminates" class="text-slate-500">
          (observation de rappel — le produit peut s'arrêter là)
        </span>
      </div>
      <div v-if="greeksFor(d).corr_pairs && Object.keys(greeksFor(d).corr_pairs).length"
        class="flex flex-wrap items-center gap-x-4 gap-y-1">
        <span class="text-slate-500">Risque de corrélation :
          <HelpTip text="Sensibilité du prix à une hausse de 5pts de la corrélation entre chaque paire de sous-jacents (bump-and-reprice, même convention CRN que les autres Greeks) — calculée automatiquement dès qu'un deal a ≥2 sous-jacents, c'est le risque le moins intuitif d'un worst-of : une baisse de corrélation en crise peut coûter cher même si chaque sous-jacent pris seul se comporte bien." />
        </span>
        <span v-for="(v, pair) in greeksFor(d).corr_pairs" :key="pair" class="font-mono">
          <span class="text-slate-500">{{ pair }}</span>
          <span class="ml-1" :class="v >= 0 ? 'text-emerald-400' : 'text-red-400'">{{ v?.toFixed(3) }}</span>
        </span>
      </div>
      <span class="text-slate-600 font-mono text-[10px]">
        calculé le {{ new Date(greeksFor(d).computed_at).toLocaleString('fr-FR') }}
      </span>
    </div>
  </div>

  <!-- ── Choc de marché (full reprice) ─────────────────── -->
  <div v-if="shockPanelOpen[d.id]" class="text-xs pt-2 border-t border-slate-800 flex flex-col gap-2">
    <div class="flex items-center gap-2">
      <span class="text-slate-500">⚡ Choc :</span>
      <select class="select text-[10px] py-0.5" @click.stop @change="applyShockPreset(d.id, $event.target.value)">
        <option value="">Preset…</option>
        <option v-for="p in shockPresets" :key="p.label" :value="p.label">{{ p.label }}</option>
      </select>
      <HelpTip text="Full reprice sous le scénario (pas une approximation par les Greeks) — un preset préremplit les champs, tout reste modifiable ensuite. Historique conservé (voir ci-dessous)." />
    </div>
    <div class="flex flex-wrap gap-2" @click.stop>
      <label class="flex flex-col gap-0.5 text-[10px] text-slate-500">Spot %
        <input v-model.number="shockForm[d.id].spot_shock_pct" type="number" step="1" class="input text-xs py-1 w-20" />
      </label>
      <label class="flex flex-col gap-0.5 text-[10px] text-slate-500">Vol (pts)
        <input v-model.number="shockForm[d.id].vol_shock_pts" type="number" step="1" class="input text-xs py-1 w-20" />
      </label>
      <label class="flex flex-col gap-0.5 text-[10px] text-slate-500">Taux (bp)
        <input v-model.number="shockForm[d.id].rate_shock_bp" type="number" step="10" class="input text-xs py-1 w-20" />
      </label>
      <label class="flex flex-col gap-0.5 text-[10px] text-slate-500">Corr (pts)
        <input v-model.number="shockForm[d.id].corr_shock_pts" type="number" step="5" class="input text-xs py-1 w-20" />
      </label>
      <button class="btn-primary text-xs px-3 py-1.5 self-end" :disabled="shockLoading[d.id]"
        @click="runDealShock(d.id)">
        <span v-if="shockLoading[d.id]"
          class="w-3 h-3 border-2 border-white border-t-transparent rounded-full animate-spin inline-block mr-1"></span>
        Lancer le choc
      </button>
    </div>

    <div v-if="shockResults[d.id]">
      <div v-if="shockResults[d.id].error" class="text-amber-400">⚠ {{ shockResults[d.id].error }}</div>
      <div v-else-if="shockResults[d.id].skipped" class="text-amber-400">
        ⚠ {{ shockResults[d.id].reason }}
      </div>
      <div v-else class="flex flex-wrap items-center gap-x-4 gap-y-1">
        <span>ΔMtM :
          <span class="font-mono font-bold" :class="shockResults[d.id].delta_pts >= 0 ? 'text-emerald-400' : 'text-red-400'">
            {{ (shockResults[d.id].delta_pts * 100).toFixed(2) }}pts
          </span>
          <span class="font-mono text-slate-400 ml-1">({{ formatNominal(shockResults[d.id].delta_pts * d.nominal) }} {{ d.devise }})</span>
        </span>
        <span class="text-slate-500">{{ shockResults[d.id].label }}</span>
        <span v-if="shockResults[d.id].spot_shock_scope === 'sans_effet'" class="text-sky-400">
          choc de spot sans effet
          <HelpTip text="Le strike n'est pas encore constaté : il est simulé sur chaque trajectoire, donc un spot qui décroche l'emmène avec lui et le produit reste identique en pourcentage de son propre strike. Le seul canal réel serait le déplacement du skew, que le modèle booké (invariant d'échelle) ne porte pas. Les chocs de vol, de taux et de corrélation restent, eux, pleinement valides." />
        </span>
        <span v-else-if="shockResults[d.id].spot_shock_scope === 'smile'" class="text-sky-400">
          choc de spot = smile
          <HelpTip text="Le strike n'est pas encore constaté : le choc de spot ne met pas le produit hors de la monnaie, il déplace le skew qui s'appliquera au produit une fois le strike fixé. C'est bien un impact réel, mais d'une autre nature qu'un décrochage." />
        </span>
      </div>
    </div>

    <div v-if="shockHistory[d.id]?.length" class="text-[10px] text-slate-600">
      <div class="font-semibold text-slate-500 mb-1">Historique</div>
      <div v-for="h in shockHistory[d.id]" :key="h.id" class="flex gap-2">
        <span>{{ new Date(h.created_at).toLocaleString('fr-FR') }}</span>
        <span class="text-slate-400">{{ h.label }} · {{ riskScopeLabel(h.data_scope) }}</span>
        <span v-if="!h.result.skipped" class="font-mono" :class="h.result.delta_pts >= 0 ? 'text-emerald-500' : 'text-red-500'">
          {{ (h.result.delta_pts * 100).toFixed(2) }}pts
        </span>
      </div>
    </div>
  </div>

  <!-- ── Reconduction (Flow A) ──────────────────────── -->
  <div v-if="rollResults[d.id]" class="text-xs pt-2 border-t border-slate-800">
    <div v-if="rollResults[d.id].error" class="text-amber-400">⚠ {{ rollResults[d.id].error }}</div>
    <div v-else class="flex flex-wrap items-center gap-x-4 gap-y-1">
      <span class="text-slate-500">🔄 Produit reconduit :</span>
      <span>
        Prix départ forward :
        <span class="font-mono font-bold text-sm text-brand-gradient">{{ (rollResults[d.id].price_new * 100).toFixed(2) }}%</span>
      </span>
      <span class="text-slate-500">
        vs traité initial <span class="font-mono" :class="(rollResults[d.id].price_new * 100 - d.price_traded) >= 0 ? 'text-emerald-400' : 'text-red-400'">
          {{ (rollResults[d.id].price_new * 100 - d.price_traded) >= 0 ? '+' : '' }}{{ (rollResults[d.id].price_new * 100 - d.price_traded).toFixed(2) }} pts
        </span>
      </span>
      <span class="text-slate-500">
        nouvelle value date <span class="font-mono text-slate-300">{{ formatDate(rollResults[d.id].value_date) }}</span>
      </span>
      <span class="text-slate-500">
        nouvelle échéance <span class="font-mono text-slate-300">{{ formatDate(rollResults[d.id].maturity_date) }}</span>
      </span>
      <span v-if="!rollResults[d.id].vol_refreshed" class="text-amber-400 text-[10px]"
            :title="`Vol du booking d'origine réutilisée — ${rollResults[d.id].vol_refresh_error || 'historique de marché indisponible'}`">
        ⚠ vol non rafraîchie
      </span>
    </div>
  </div>
</template>

<script setup>
// Extracted from BookingView.vue (P1-10, U3). The state stays in the
// view; this panel reads it through useBookingContext().
import HelpTip from '../../components/HelpTip.vue'
import { formatDate } from '../../utils/format.js'
import { riskScopeLabel } from '../../utils/riskScope.js'
import { shockPresets } from '../../stores/portfolios.js'
import { useBookingContext } from './context.js'

defineProps({ d: { required: true } })
const {
  applyShockPreset, formatNominal, greeksFor, refreshResults, rollResults, runDealShock, shockForm,
  shockHistory, shockLoading, shockPanelOpen, shockResults,
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
