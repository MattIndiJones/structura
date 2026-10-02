<template>
  <div class="ccr-result flex flex-col gap-3">
    <div class="flex flex-wrap gap-3 items-center text-xs">
      <span v-if="result.is_test" class="badge-gold">RECETTE UAT · {{ result.uat_batch_id ? `lot #${result.uat_batch_id}` : 'tous les lots' }} · limites simulées</span>
      <span v-else class="badge-muted">Production</span>
      <b>{{ result.methodology === 'NESTED_MONTE_CARLO_GBM' ? 'Monte-Carlo imbriqué · revalorisation PayScript · GBM' : result.methodology === 'NESTED_MONTE_CARLO_INCOMPLETE' ? 'Calcul complet demandé · projection incomplète · PFE indisponible' : 'Contrôle rapide · exposition courante uniquement' }}</b>
      <span class="badge-muted">{{ result.as_of_date }} · {{ result.currency }}</span>
      <span :class="result.decision.hard_block ? 'text-red-500' : 'text-amber-600'">{{ statusLabels[result.decision.status] }}</span>
      <span v-if="result.run_id">Calcul #{{ result.run_id }}</span>
      <span v-if="result.credit_data_status === 'MISSING_DATA'" class="text-amber-600">Profil crédit incomplet</span>
    </div>
    <p v-if="result.preparation_cache?.key" class="card text-sm">
      <b>{{ result.preparation_cache.reused ? `Base MtM réutilisée depuis le calcul #${result.preparation_cache.source_run_id}` : 'Base MtM préparée pour ce calcul' }}</b>.
      Marché figé le {{ runTimestamp(result.preparation_cache.snapshot_at)?.toLocaleString('fr-FR') || '—' }}. Les scénarios et projections sont recalculés ; pour renouveler la base, cocher « Recalculer la base MtM ».
    </p>
    <p v-if="result.assumptions?.common_rate != null" class="card text-sm">
      <b>Taux commun appliqué <HelpTip :text="ccrHelp.commonRate" /> : {{ percent(result.assumptions.common_rate) }}</b> · {{ result.assumptions.common_rate_source === 'TEMPORARY_ASSUMPTION' ? 'Hypothèse provisoire — taux du jour non raccordés' : 'Surcharge manuelle' }}.
      Même taux pour le drift et l’actualisation de tous les deals préparés.
    </p>
    <details v-if="result.common_market?.correlation" class="card text-sm" open>
      <summary class="font-semibold">Marché commun appliqué — volatilités réalisées et corrélations historiques</summary>
      <p>{{ number(result.common_market.n_returns) }} rendements communs · du {{ result.common_market.effective_start }} au {{ result.common_market.effective_end }} · {{ result.common_market.provider }} · clôtures ajustées. Ces volatilités sont historiques, pas implicites.</p>
      <div class="table-shell ccr-table mt-2"><table class="w-full text-xs"><thead><tr><th>Facteur</th><th>Volatilité <HelpTip :text="ccrHelp.sigma" /></th><th>Source volatilité</th><th>Dividende <HelpTip :text="ccrHelp.q" /></th><th>Source dividende</th></tr></thead><tbody>
        <tr v-for="(f,ticker) in result.common_market.factors" :key="ticker"><td>{{ ticker }}</td><td>{{ percent(f.sigma) }}</td><td>{{ f.sigma_source === 'USER_OVERRIDE' ? 'Surcharge manuelle' : 'Réalisée, fenêtre 252 rendements' }}</td><td>{{ percent(f.q) }}</td><td>{{ f.q_source === 'USER_OVERRIDE' ? 'Surcharge manuelle' : `${f.q_source === 'LATEST_BOOKING_ASSUMPTION' ? 'Hypothèse du booking' : 'Hypothèse du contexte'} ${f.q_reference}` }}</td></tr>
      </tbody></table></div>
      <details class="mt-2"><summary>Matrice de corrélation commune et provenance</summary><pre class="ccr-assumptions-json">{{ JSON.stringify(result.common_market, null, 2) }}</pre></details>
    </details>
    <AlertMessage v-for="message in [...result.errors, ...result.warnings, ...(result.after.warnings || [])]" :key="message" kind="warning">{{ message }}</AlertMessage>
    <p class="text-xs text-slate-500">Montants en {{ result.currency }} · — = donnée indisponible, jamais zéro.</p>
    <div class="ccr-metrics">
      <div v-for="key in cards" :key="key" class="card ccr-metric !p-3">
        <p class="text-xs text-slate-500">{{ metricLabels[key] }} <HelpTip :text="ccrHelp[key]" /></p>
        <p class="ccr-metric-value tabular-nums"><CcrAmount :value="result.after[key]" :currency="result.currency" /></p>
      </div>
    </div>
    <div class="card ccr-conditional-loss !p-3">
      <div>
        <p class="text-xs text-slate-500">Perte indicative si défaut immédiat <HelpTip :text="ccrHelp.immediate_default_loss" /></p>
        <p v-if="immediateDefaultLoss !== null" class="text-xs text-slate-500">
          Exposition courante × (1 − recouvrement {{ percent(recovery) }}) · {{ recoverySource }}.
          Scénario conditionnel, sans probabilité de défaut.
        </p>
        <p v-else class="text-xs text-amber-600">Exposition courante ou hypothèse de recouvrement indisponible.</p>
      </div>
      <p class="ccr-metric-value tabular-nums"><CcrAmount :value="immediateDefaultLoss" :currency="result.currency" /></p>
    </div>
    <p v-if="result.after.cva_missing_reason" class="text-xs text-amber-600">CVA : {{ result.after.cva_missing_reason }}</p>
    <div v-if="result.stress" class="card text-xs"><h3 class="font-semibold mb-2">Base / stress de marché et crédit — {{ result.stress.wwr }}</h3>
      <p v-for="e in result.stress.errors" :key="e" class="text-red-500">{{ e }}</p>
      <div class="table-shell ccr-table" tabindex="0" aria-label="Comparaison base et stress"><table class="w-full"><thead><tr><th>Métrique</th><th class="num">Base</th><th class="num">Stress</th></tr></thead><tbody><tr v-for="key in ['net_mtm','current_exposure','pfe95','pfe99','cva']" :key="key"><td class="p-2">{{ metricLabels[key] }} <HelpTip :text="ccrHelp[key]" /></td><td class="text-right"><CcrAmount :value="result.after[key]" :currency="result.currency" /></td><td class="text-right"><CcrAmount :value="result.stress.after[key]" :currency="result.currency" /></td></tr></tbody></table></div>
    </div>
    <div v-if="result.standalone" class="table-shell ccr-table" tabindex="0" aria-label="Expositions avant et après transaction">
      <table class="w-full text-xs"><thead><tr><th>Métrique</th><th class="num">Avant</th><th class="num">Deal seul</th><th class="num">Après</th><th class="num">Incrément signé <HelpTip :text="ccrHelp.incremental" /></th></tr></thead>
        <tbody><tr v-for="key in ['current_exposure','pfe95','pfe99','cva']" :key="key">
          <td>{{ metricLabels[key] }} <HelpTip :text="ccrHelp[key]" /></td><td v-for="group in ['before','standalone','after','incremental']" :key="group" class="text-right p-2"><CcrAmount :value="result[group][key]" :currency="result.currency" /></td>
        </tr></tbody>
      </table>
      <p class="p-2 text-xs">Bénéfice d’agrégation / netting PFE 95 % <HelpTip :text="ccrHelp.netting_benefit" /> : <CcrAmount :value="result.netting_benefit" :currency="result.currency" />. Un incrément négatif réduit le risque.</p>
    </div>
    <div v-if="result.after.profile?.length" class="card">
      <h3 class="font-semibold text-sm">Profil d’exposition — EE (Expected Exposure), PFE 95 % et 99 %</h3>
      <SensitiveValue mode="blur"><div class="h-64"><canvas ref="canvas" role="img" aria-label="Profil d’exposition par horizon"></canvas></div></SensitiveValue>
    </div>
    <div class="table-shell ccr-table" tabindex="0" aria-label="Utilisation des limites">
      <table class="w-full text-xs"><thead><tr><th>Limite</th><th class="num">Montant</th><th class="num">Utilisation <HelpTip :text="ccrHelp.utilisation" /></th><th class="num">Capacité restante <HelpTip :text="ccrHelp.remaining_capacity" /></th><th>Statut</th><th>Action</th></tr></thead>
        <tbody><tr v-for="(l, i) in result.limits" :key="i"><td class="p-2">{{ metricLabels[l.metric] }} <HelpTip :text="ccrHelp[l.metric]" /></td><td class="text-right"><CcrAmount :value="l.limit" :currency="result.currency" /></td><td class="text-right"><SensitiveValue>{{ percent(l.utilisation) }}</SensitiveValue></td><td class="text-right"><CcrAmount :value="l.remaining_capacity" :currency="result.currency" /></td><td class="p-2">{{ statusLabels[l.status] }}</td><td>{{ l.action || '—' }}</td></tr></tbody>
      </table>
    </div>
    <details class="card text-xs"><summary class="cursor-pointer font-semibold">Détail des deals et netting sets</summary>
      <div class="table-shell ccr-table mt-3" tabindex="0" aria-label="Détail des expositions par deal"><table class="w-full"><thead><tr><th>Deal</th><th>Produit</th><th>Set</th><th class="num">MtM <HelpTip :text="ccrHelp.net_mtm" /></th><th class="num">Exposition seule <HelpTip :text="ccrHelp.current_exposure" /></th><th class="num">PFE95 seule <HelpTip :text="ccrHelp.pfe95" /></th><th class="num">PFE99 seule <HelpTip :text="ccrHelp.pfe99" /></th></tr></thead>
        <tbody><tr v-for="d in result.deals" :key="d.reference"><td class="p-2">{{ d.reference }}</td><td>{{ d.product_type }}</td><td>{{ d.netting_set_id || 'Aucun' }}</td><td v-for="k in ['net_mtm','current_exposure','pfe95','pfe99']" :key="k" class="text-right"><CcrAmount :value="d[k]" :currency="result.currency" /></td></tr></tbody></table></div>
      <p v-for="s in result.after.netting_sets" :key="s.bucket" class="mt-2">{{ s.bucket }} · MtM <CcrAmount :value="s.net_mtm" :currency="result.currency" /> · exposition <CcrAmount :value="s.current_exposure" :currency="result.currency" /></p>
    </details>
    <details v-if="result.valuation_assumptions?.length" class="card text-xs" open>
      <summary class="font-semibold">Hypothèses effectives des MtM</summary>
      <p class="mt-2">Arrêté : {{ result.as_of_date }} · MtM : {{ result.assumptions.mtm_paths ? number(result.assumptions.mtm_paths) : 'Contexte figé' }} trajectoires · seed {{ result.assumptions.seed }}.</p>
      <p>Expositions : {{ number(result.assumptions.n_outer) }} scénarios extérieurs × {{ number(result.assumptions.n_inner) }} trajectoires intérieures · {{ number(result.assumptions.requested_dates) }} horizons demandés.</p>
      <p>Le MtM clean exclut le funding émetteur. {{ result.common_market?.correlation ? "Volatilités et corrélations issues du marché commun ci-dessus ; dividendes issus du booking de référence ou des surcharges." : "Sans surcharge, paramètres des contextes enregistrés, sans calibration actualisée." }}</p>
      <div class="table-shell ccr-table mt-2"><table class="w-full"><thead><tr><th>Deal</th><th>Source / statut</th><th>Modèle <HelpTip :text="ccrHelp.commonMarket" /></th><th>Taux <HelpTip :text="ccrHelp.commonRate" /></th><th>Facteurs : volatilité / dividende</th></tr></thead>
        <tbody><tr v-for="d in result.valuation_assumptions" :key="d.reference"><td>{{ d.reference }}</td><td>{{ d.error || valuationSources[d.source] || 'Entrées figées' }}</td><td>{{ d.effective_context?.model || '—' }}</td><td>{{ percent(d.effective_context?.r) }}{{ d.effective_context?.yield_curve?.length ? ' + courbe' : '' }}</td><td><p v-for="u in d.effective_context?.underlyings || []" :key="u.ticker || u.name">{{ u.ticker || u.name }} : {{ percent(u.sigma) }} / {{ percent(u.q) }}{{ u.dividend_curve?.length ? ' + courbe dividendes' : '' }}</p></td></tr></tbody>
      </table></div>
      <details v-for="d in result.valuation_assumptions.filter(d => d.effective_context)" :key="d.reference" class="mt-2"><summary>{{ d.reference }} — paramètres complets, corrélations et provenance</summary><pre class="ccr-assumptions-json">{{ JSON.stringify({source:d.source,as_of_date:d.as_of_date,market_provenance:d.market_provenance,parameters:d.effective_context}, null, 2) }}</pre></details>
    </details>
    <details class="card text-xs"><summary class="cursor-pointer font-semibold">Hypothèses, crédit et réglementaire</summary>
      <p class="mt-2">PFE des limites = maximum sur les horizons. EPE = moyenne temporelle de l’EE. Scénarios risk-neutral, grille hebdomadaire, quantiles interpolés. CVA unilatérale avec indépendance crédit/marché ; intégration à droite.</p>
      <p class="mt-2">PD : {{ result.credit_profile?.curve_source || 'UNKNOWN' }} / {{ result.credit_profile?.pd_measure || 'UNKNOWN' }}. Recouvrement : {{ percent(result.credit_profile?.recovery) }} / {{ result.credit_profile?.recovery_source || 'UNKNOWN' }}.</p>
      <p class="mt-2">Courbe de spreads : approximation explicite intensité = spread / LGD, sans bootstrap CDS.</p>
      <p class="mt-2">{{ result.regulatory.reason }}</p>
    </details>
  </div>
</template>
<script setup>
import { computed, ref, watch, nextTick, onBeforeUnmount } from 'vue'
import { Chart, registerables } from 'chart.js'
import { runTimestamp } from '../composables/useBookingMtm.js'
import HelpTip from './HelpTip.vue'
import { ccrHelp } from '../utils/ccrHelp.js'
import SensitiveValue from './SensitiveValue.vue'
import CcrAmount from './CcrAmount.vue'
import AlertMessage from './ui/AlertMessage.vue'
import { metricLabels, money, percent, statusLabels, valuationSources, number } from '../utils/ccr.js'
Chart.register(...registerables)
const props = defineProps({ result: { type: Object, required: true } })
const cards = ['gross_notional','gross_positive_mtm','net_mtm','collateral','current_exposure','ee','pfe95','pfe99','cva']
const recovery = computed(() => {
  const value = props.result.credit_profile?.recovery
  return typeof value === 'number' && Number.isFinite(value) && value >= 0 && value < 1 ? value : null
})
const immediateDefaultLoss = computed(() => {
  const exposure = props.result.after?.current_exposure
  return typeof exposure === 'number' && Number.isFinite(exposure) && exposure >= 0 && recovery.value !== null
    ? exposure * (1 - recovery.value) : null
})
const recoverySource = computed(() => {
  const source = props.result.credit_profile?.recovery_source
  if (source === 'USER_ASSUMPTION') return props.result.is_test ? 'hypothèse de recette UAT' : 'hypothèse utilisateur'
  return { MARKET_DATA: 'donnée de marché', INTERNAL_DATA: 'donnée interne', SYSTEM_DEFAULT: 'valeur par défaut du système' }[source] || 'source non précisée'
})
const canvas = ref(null)
let chart
watch(() => props.result, async () => {
  await nextTick(); chart?.destroy()
  if (!canvas.value || !props.result.after.profile?.length) return
  const rows = props.result.after.profile
  chart = new Chart(canvas.value, { type: 'line', data: { labels: rows.map(r => `${number(r.t, 2)} A`), datasets: [
    ['ee','EE','#2563eb'], ['pfe95','PFE95','#d97706'], ['pfe99','PFE99','#dc2626'], ['uncollateralised_ee','EE sans collatéral','#94a3b8'],
  ].map(([key,label,color]) => ({ label, data: rows.map(r => r[key]), borderColor: color, pointRadius: 2, borderWidth: 2 })) },
  options: { locale: 'fr-FR', plugins: { tooltip: { callbacks: { label: ctx => `${ctx.dataset.label} : ${money(ctx.parsed.y)} ${props.result.currency}` } } }, responsive: true, maintainAspectRatio: false, animation: false, scales: { y: { beginAtZero: true, ticks: { callback: value => number(value) } } } } })
}, { immediate: true })
onBeforeUnmount(() => chart?.destroy())
</script>

<style scoped>
.ccr-result, .ccr-result > *, .ccr-result .card { min-width: 0; }
.ccr-result > * { flex-shrink: 0; }
.ccr-metrics { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: .5rem; }
.ccr-metric { display: flex; flex-direction: column; justify-content: space-between; gap: .5rem; }
.ccr-metric > p:first-child { min-height: 2rem; }
.ccr-metric-value { font-size: 1.125rem; font-weight: 600; line-height: 1.5rem; text-align: right; overflow-wrap: anywhere; }
.ccr-conditional-loss { display: flex; align-items: end; justify-content: space-between; gap: 1rem; }
.ccr-conditional-loss > p { flex-shrink: 0; }
.ccr-table { max-width: 100%; max-height: none; overflow-x: auto; overflow-y: hidden; overscroll-behavior: auto; scrollbar-gutter: stable; }
.ccr-table:focus-visible { outline: 2px solid var(--accent); outline-offset: -2px; }
.ccr-table th { position: sticky; top: 0; z-index: 1; background: var(--surface2); white-space: nowrap; }
.ccr-table th.num { text-align: right; }
.ccr-table td { white-space: nowrap; }
.ccr-assumptions-json { max-height: 16rem; overflow: auto; overscroll-behavior: auto; padding: .5rem; }
.ccr-result summary { cursor: pointer; }
@media (max-width: 639px) {
  .ccr-metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .ccr-metric-value { font-size: 1rem; }
  .ccr-conditional-loss { align-items: stretch; flex-direction: column; gap: .5rem; }
}
</style>
