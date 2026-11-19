<template>
  <div class="text-[10px] text-slate-500 -mt-1">
    Périmètre {{ pf.scopeLabel }}. Somme des Greeks calculés à la date d’analyse (nominal × sensibilité % × taux de change vers EUR), regroupés par sous-jacent. Créer un portefeuille ne lance aucun calcul.
    <HelpTip text="La lecture de cet onglet ne lance aucun Monte Carlo. Recalculer produit et conserve un calcul daté pour chaque deal actif à la date choisie." />
  </div>

  <div v-if="pf.riskLoading" class="text-xs text-slate-500">Chargement…</div>

  <template v-else-if="pf.risk">
    <!-- Devise non convertible : la position est ABSENTE de tous les
         totaux ci-dessous (le backend refuse d'inventer un taux).
         Sans ce bandeau l'exclusion serait invisible et le total
         paraîtrait complet. -->
    <div v-if="pf.risk.deals_missing_fx?.length"
      class="text-xs text-red-400 bg-red-950/30 border border-red-900/50 rounded-lg px-3 py-2">
      ⚠ {{ pf.risk.deals_missing_fx.length }} deal(s) exclu(s) des totaux — taux de change indisponible
      ({{ pf.risk.deals_missing_fx.map(d => `${d.reference} (${d.devise})`).join(', ') }})
    </div>
    <div v-if="pf.risk.deals_missing_greeks.length"
      class="text-xs text-amber-400 bg-amber-950/30 border border-amber-900/50 rounded-lg px-3 py-2">
      ⚠ {{ pf.risk.deals_missing_greeks.length }} deal(s) sans Greeks calculés — chiffres incomplets
      ({{ pf.risk.deals_missing_greeks.map(d => d.reference).join(', ') }})
    </div>
    <div v-if="riskMetricRows.length" class="flex flex-wrap gap-2 text-[11px]" data-testid="risk-metric-coverage">
      <span v-for="row in riskMetricRows" :key="row.key" :title="row.detail"
        class="rounded border px-2 py-1"
        :class="row.complete ? 'border-slate-700 text-slate-400' : 'border-amber-800 text-amber-400'">
        {{ row.label }} : {{ row.available }}/{{ row.required }}
        · {{ row.complete ? 'complet' : 'indisponible pour le périmètre' }}
      </span>
    </div>
    <div v-if="pf.risk.deals_stale.length"
      class="text-xs text-slate-400 bg-slate-800/40 border border-slate-700/60 rounded-lg px-3 py-2">
      ⏱ {{ pf.risk.deals_stale.length }} deal(s) avec des Greeks vieux de plus de 7 jours
      ({{ pf.risk.deals_stale.map(d => d.reference).join(', ') }})
    </div>
    <div v-if="hasMixedVegaScopes"
      class="text-xs text-amber-400 bg-amber-950/30 border border-amber-900/50 rounded-lg px-3 py-2">
      ⚠ Certains sous-jacents portent plusieurs périmètres de vega. Les montants sont présentés séparément et ne sont pas additionnés.
    </div>

    <div v-if="!pf.risk.deals_included.length" class="text-xs text-slate-500">
      Aucun deal avec des Greeks calculés dans cette sélection.
    </div>

    <template v-else>
      <div class="overflow-x-auto table-shell" tabindex="0" role="region">
        <table class="w-full text-xs border-collapse">
          <thead>
            <tr class="border-b border-slate-700 text-slate-500">
              <th class="text-left py-1.5 pr-3 font-semibold">Sous-jacent
                <HelpTip text="Sous-jacent canonique (regroupe les deals qui le nomment différemment, via le catalogue Admin market-data) — cliquez la ligne pour voir le détail par deal." /></th>
              <th class="text-right py-1.5 pr-3 font-semibold">Delta (EUR)
                <HelpTip align="right" text="Exposition nette en EUR pour un mouvement de 100% du sous-jacent : Σ(delta% du deal × nominal × taux de change), sommée sur tous les deals qui le contiennent. Vert = exposition longue, rouge = short." /></th>
              <th class="text-right py-1.5 pr-3 font-semibold">Gamma (EUR)
                <HelpTip align="right" text="Variation du delta net (EUR) pour un mouvement de 100% du sous-jacent. Peut être très élevé et bruité près d'une barrière autocall/KI (payoff quasi-digital) — vérifiez le détail par deal si un chiffre paraît disproportionné." /></th>
              <th class="text-right py-1.5 font-semibold">Vega par périmètre (EUR)
                <HelpTip align="right" width="w-80" text="Les vegas de volatilité totale, de jambe indépendante de variance et les anciens vegas sans périmètre documenté restent séparés. Les additionner donnerait une exposition sans définition commune." /></th>
            </tr>
          </thead>
          <tbody>
            <template v-for="(g, key) in pf.risk.per_underlying" :key="key">
              <tr class="border-b border-slate-800/50 hover:bg-slate-800/20 transition-colors cursor-pointer"
                @click="expandedUnderlying = expandedUnderlying === key ? null : key">
                <td class="py-1.5 pr-3 text-slate-300 font-semibold">
                  <span class="text-slate-600 mr-1">{{ expandedUnderlying === key ? '▾' : '▸' }}</span>{{ g.label }}
                </td>
                <td class="py-1.5 pr-3 text-right font-mono"
                  :class="g.delta_eur >= 0 ? 'text-emerald-400' : 'text-red-400'">{{ formatNominal(g.delta_eur) }}</td>
                <td class="py-1.5 pr-3 text-right font-mono text-slate-400">{{ formatNominal(g.gamma_eur) }}</td>
                <td class="py-1.5 text-right font-mono text-slate-400">
                  <div v-for="row in vegaRows(g)" :key="row.scope">
                    <span class="text-[10px] text-slate-600">{{ vegaScopeLabel(row.scope) }}</span>
                    {{ formatNominal(row.value) }}
                  </div>
                  <span v-if="!vegaRows(g).length" class="text-slate-600">—</span>
                </td>
              </tr>
              <tr v-if="expandedUnderlying === key" class="bg-slate-900/60">
                <td colspan="4" class="py-2 pl-6 pr-3">
                  <table class="w-full text-[11px] border-collapse">
                    <thead>
                      <tr class="text-slate-600">
                        <th class="text-left py-1 pr-3 font-medium">Deal</th>
                        <th class="text-right py-1 pr-3 font-medium">Delta (EUR / %)
                          <HelpTip align="right" text="% = part de ce deal dans le delta net de la ligne — peut dépasser 100% ou être négatif si des deals se compensent entre eux." /></th>
                        <th class="text-right py-1 pr-3 font-medium">Gamma (EUR / %)</th>
                        <th class="text-right py-1 font-medium">Vega (EUR / périmètre / %)</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="c in g.contributions" :key="c.deal_id"
                        class="hover:bg-slate-800/40 cursor-pointer" @click.stop="openDealDetail(c.deal_id)">
                        <td class="py-1 pr-3 font-mono font-semibold text-blue-400"><DealReferenceLink :deal-id="c.deal_id" :reference="c.reference" /></td>
                        <td class="py-1 pr-3 text-right font-mono text-slate-400">
                          {{ formatNominal(c.delta_eur) }} <span class="text-slate-600">({{ sharePct(c.delta_eur, g.delta_eur) }})</span>
                        </td>
                        <td class="py-1 pr-3 text-right font-mono text-slate-400">
                          {{ formatNominal(c.gamma_eur) }} <span class="text-slate-600">({{ sharePct(c.gamma_eur, g.gamma_eur) }})</span>
                        </td>
                        <td class="py-1 text-right font-mono text-slate-400">
                          <template v-if="c.vega_eur != null">
                            {{ formatNominal(c.vega_eur) }}
                            <span class="text-slate-600">{{ vegaScopeLabel(c.vega_scope) }} · ({{ sharePct(c.vega_eur, vegaScopeTotal(g, c.vega_scope)) }})</span>
                          </template>
                          <span v-else class="text-slate-600">—</span>
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </td>
              </tr>
            </template>
          </tbody>
        </table>
      </div>

      <template v-if="Object.keys(pf.risk.corr_pairs || {}).length">
        <div class="text-xs font-bold text-slate-400 uppercase tracking-wider">
          Corrélation par paire
          <HelpTip width="w-72" text="Sensibilité du book à une hausse de corrélation entre deux sous-jacents (cross-gamma), uniquement pour les paires qui apparaissent ensemble dans au moins un deal worst-of/basket — jamais visible deal par deal, un book peut être concentré sur une paire sans qu'aucun deal ne la montre grosse à lui seul." />
        </div>
        <div class="overflow-x-auto table-shell" tabindex="0" role="region">
          <table class="w-full text-xs border-collapse">
            <thead>
              <tr class="border-b border-slate-700 text-slate-500">
                <th class="text-left py-1.5 pr-3 font-semibold">Paire de sous-jacents</th>
                <th class="text-right py-1.5 font-semibold">Corr (EUR / 1pt)
                  <HelpTip align="right" text="Σ(sensibilité corrélation du deal × nominal × taux de change), rescalée pour lire un impact par 1 point de corrélation — même convention que corr_shock_pts dans l'onglet Chocs (le moteur calcule la dérivée brute par 100pts, d'où le ×0.01)." /></th>
              </tr>
            </thead>
            <tbody>
              <template v-for="(g, key) in pf.risk.corr_pairs" :key="key">
                <tr class="border-b border-slate-800/50 hover:bg-slate-800/20 transition-colors cursor-pointer"
                  @click="expandedCorrPair = expandedCorrPair === key ? null : key">
                  <td class="py-1.5 pr-3 text-slate-300 font-semibold">
                    <span class="text-slate-600 mr-1">{{ expandedCorrPair === key ? '▾' : '▸' }}</span>{{ g.label }}
                  </td>
                  <td class="py-1.5 text-right font-mono" :class="g.corr_eur >= 0 ? 'text-emerald-400' : 'text-red-400'">{{ formatNominal(g.corr_eur) }}</td>
                </tr>
                <tr v-if="expandedCorrPair === key" class="bg-slate-900/60">
                  <td colspan="2" class="py-2 pl-6 pr-3">
                    <table class="w-full text-[11px] border-collapse">
                      <thead>
                        <tr class="text-slate-600">
                          <th class="text-left py-1 pr-3 font-medium">Deal</th>
                          <th class="text-right py-1 font-medium">Corr (EUR / 1pt)</th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr v-for="c in g.contributions" :key="c.deal_id"
                          class="hover:bg-slate-800/40 cursor-pointer" @click.stop="openDealDetail(c.deal_id)">
                          <td class="py-1 pr-3 font-mono font-semibold text-blue-400"><DealReferenceLink :deal-id="c.deal_id" :reference="c.reference" /></td>
                          <td class="py-1 text-right font-mono text-slate-400">{{ formatNominal(c.corr_eur) }}</td>
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

      <div class="grid grid-cols-2 sm:grid-cols-5 gap-3">
        <div class="stat-box">
          <div class="text-xs text-slate-500 mb-1">Nominal total
            <HelpTip text="Somme des nominaux de tous les deals actifs de cette sélection, convertis en EUR au taux de change courant (get_fx_series) — inclut aussi les deals sans Greeks calculés, contrairement aux autres tuiles de cette rangée." /></div>
          <div class="text-lg font-bold font-mono text-slate-200">{{ formatNominal(pf.risk.nominal_total_eur) }}</div>
          <div class="text-[10px] text-slate-600">EUR</div>
        </div>
        <div class="stat-box">
          <div class="text-xs text-slate-500 mb-1">Theta net
            <HelpTip text="Décroissance temporelle nette du book, en EUR par jour calendaire — somme des theta par deal (signe de la position × nominal × taux de change), déjà scalaire donc pas de regroupement par sous-jacent nécessaire. Un flux détaché pendant la semaine mesurée n'y entre pas : il est reporté à part sur le deal concerné." /></div>
          <div class="text-lg font-bold font-mono text-slate-200">{{ formatNominal(pf.risk.scalar.theta) }}</div>
          <div class="text-[10px] text-slate-600">EUR / jour</div>
          <div v-if="pf.risk.deals_missing_theta?.length"
            class="text-[10px] text-amber-400/80 mt-0.5">
            total indisponible — {{ pf.risk.deals_missing_theta.length }} deal(s) sans theta
            <HelpTip text="Ces deals n'ont pas de theta calculable : la semaine franchit une transition contractuelle ou un état réalisé qui ne peut pas être inventé exactement (observation, fixing, mémoire ou volatilité réalisée). Ils sont exclus de la somme plutôt que comptés à zéro." />
          </div>
        </div>
        <div class="stat-box">
          <div class="text-xs text-slate-500 mb-1">Rho net
            <HelpTip text="Sensibilité nette du book à une hausse de 100 points de base (1pt) du taux sans risque, en EUR — le moteur calcule la dérivée brute par rapport au taux (par unité de r, soit par 100pt), rescalée ×0.01 ici pour lire un impact par 1pt réellement, puis sommée par deal (nominal × taux de change)." /></div>
          <div class="text-lg font-bold font-mono text-slate-200">{{ formatNominal(pf.risk.scalar.rho) }}</div>
          <div class="text-[10px] text-slate-600">EUR / 1pt taux</div>
        </div>
        <div class="stat-box">
          <div class="text-xs text-slate-500 mb-1">Deals inclus
            <HelpTip text="Nombre de deals dont les Greeks ont pu être sommés dans cet écran — exclut les deals sans Greeks jamais calculés (voir l'avertissement au-dessus)." /></div>
          <div class="text-lg font-bold font-mono text-slate-200">{{ pf.risk.deals_included.length }}</div>
        </div>
        <div class="stat-box">
          <div class="text-xs text-slate-500 mb-1">Plus ancien calcul
            <HelpTip text="Date du calcul de Greeks le plus ancien parmi les deals inclus — l'agrégat n'est fiable que si cette date est récente ; utilisez Recalculer sinon." /></div>
          <div class="text-sm font-bold font-mono text-slate-200">
            {{ pf.risk.oldest_computed_at ? new Date(pf.risk.oldest_computed_at).toLocaleDateString('fr-FR') : '—' }}
          </div>
        </div>
      </div>
    </template>
  </template>
</template>

<script setup>
// Extracted from RiskManagementView.vue (P1-10, U3). The state stays in the
// view; this panel reads it through useRiskContext().
import DealReferenceLink from '../../components/DealReferenceLink.vue'
import HelpTip from '../../components/HelpTip.vue'
import { sharePct, vegaRows, vegaScopeLabel, vegaScopeTotal } from './riskLabels.js'
import { useRiskContext } from './context.js'

const {
  expandedCorrPair, expandedUnderlying, formatNominal, hasMixedVegaScopes, openDealDetail, pf,
  riskMetricRows,
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
