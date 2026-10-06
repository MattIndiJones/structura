<template>
  <main class="optimizer p-4 lg:p-6 w-full max-w-[1500px] mx-auto">
    <div class="page-header">
      <div><h1 class="page-title">Product Optimizer</h1><p class="page-subtitle">Contraintes → coupon résolu au prix cible → solutions admissibles</p></div>
      <RouterLink class="btn-ghost btn-sm" to="/structuring">← Structuring Intelligence</RouterLink>
    </div>
    <p v-if="demo.enabled" class="scope-note mt-4">Mode Démo : les hypothèses et les résultats de l'Optimizer sont masqués. Désactivez ce mode pour travailler sur une recherche.</p>
    <template v-else>
    <p class="scope-note mt-3">V1 · Autocall Athena, barrière européenne · GBM · 1 à 3 actifs de même devise. Coupon accumulé, payé au rappel ; aucun coupon si jamais rappelé. Coupon nominal annualisé, hors frais et crédit.</p>
    <p v-if="error" role="alert" class="alert-error mt-3">{{ error }}</p>
    <form @submit.prevent="start" class="mt-4">
      <fieldset :disabled="busy || loading" class="grid lg:grid-cols-3 gap-4">
        <section class="card flex flex-col gap-3">
          <h2 class="section-title">1 · Objectif et univers</h2>
          <label>Objectif<select class="select" v-model="form.objective"><option value="maximize_coupon">Maximiser le coupon</option><option value="maximize_protection">Maximiser la protection</option><option value="target_coupon">Coupon cible et meilleure protection</option></select></label>
          <div class="grid grid-cols-2 gap-2"><label>Famille<select class="select" disabled><option>Autocall Athena</option></select></label><label>Modèle<select v-model="form.model" class="select"><option value="auto">Auto — GBM</option><option value="constant">GBM explicite</option></select></label></div>
          <div class="grid grid-cols-2 gap-2"><label>Devise<select v-model="form.currency" class="select"><option v-for="ccy in currencies" :key="ccy">{{ ccy }}</option></select></label><label>Strike / valeur / hypothèses<input class="input" required type="date" v-model="form.strike_date" /></label></div>
          <div class="grid grid-cols-2 gap-2"><label>Convention<select v-model="form.convention" class="select" required><option disabled value="">À choisir</option><option value="modified_following">Modified Following</option><option value="following">Following</option><option value="preceding">Preceding</option><option value="none">Sans ajustement</option></select></label><label>Paiement — jours ouvrés<input class="input" type="number" min="0" max="10" step="1" v-model.number="form.settlement_lag" required /></label></div>
          <p class="text-xs text-slate-500">Qualification actions/indices déclarée par l'utilisateur. Catalogue de sous-jacents existant ; aucun choix implicite de change.</p>
          <div v-for="(asset, index) in assets" :key="index" class="asset-row">
            <label>Sous-jacent {{ index + 1 }}<select class="select" required v-model="asset.ticker"><option value="" disabled>Choisir dans le catalogue</option><option v-for="item in catalogue" :key="item.ticker" :value="item.ticker">{{ item.label }} · {{ item.ticker }}</option></select></label>
            <div class="grid grid-cols-3 gap-2 mt-2"><label>Type<select class="select" v-model="asset.asset_type"><option value="index">Indice</option><option value="equity">Action</option></select></label><label>Vol. utilisée %<input class="input" required type="number" min="0" max="150" step="0.1" v-model.number="asset.vol" /></label><label>Dividende %<input class="input" required type="number" min="0" max="50" step="0.1" v-model.number="asset.dividend" /></label></div>
            <button v-if="assets.length > 1" type="button" class="btn-ghost btn-sm mt-1" @click="assets.splice(index, 1)">Retirer</button>
          </div>
          <button v-if="assets.length < 3" type="button" class="btn-secondary btn-sm" @click="assets.push({ ticker: '', asset_type: 'index', vol: 20, dividend: 2 })">Ajouter au panier worst-of</button>
          <div v-if="assets.length > 1" class="grid grid-cols-3 gap-2"><label v-for="pair in pairs" :key="pair.key">Corr. {{ pair.i + 1 }}/{{ pair.j + 1 }}<input class="input" type="number" min="-0.99" max="0.99" step="0.01" required v-model.number="correlations[pair.key]" /></label></div>
          <label>Taux plat utilisé %<input class="input" type="number" min="-10" max="30" step="0.1" required v-model.number="rate" /></label>
          <p class="scope-note">Hypothèses utilisateur, pas de données de marché téléchargées : vérifier volatilités, dividendes, corrélations et taux avant usage.</p>
        </section>
        <section class="card flex flex-col gap-3">
          <h2 class="section-title">2 · Espace de recherche</h2>
          <div class="range-head"><span>Paramètre</span><span>Min.</span><span>Max.</span><span>Pas</span></div>
          <div v-for="field in rangeFields" :key="field.key" class="range-head">
            <span>{{ field.label }}</span><input v-for="part in ['minimum','maximum','step']" :key="part" class="input" type="number" :aria-label="`${field.label} ${part}`" :min="part === 'step' ? field.step : field.min" :max="field.max" :step="field.step" required v-model.number="ranges[field.key][part]" />
          </div>
          <fieldset><legend class="text-xs font-semibold mb-2">Fréquences de constatation</legend><div class="flex flex-wrap gap-3"><label v-for="frequency in frequencies" :key="frequency.value" class="check-label"><input type="checkbox" :value="frequency.value" v-model="observations" />{{ frequency.label }}</label></div></fieldset>
          <p class="text-xs text-slate-500">Maturités en mois, multiples des fréquences retenues. La borne haute est incluse seulement si elle tombe sur le pas. Barrière de protection plus basse = meilleure protection conditionnelle.</p>
          <div class="grid grid-cols-2 gap-2"><label>Coupon annuel min. %<input class="input" type="number" min="0" max="50" step="0.1" required v-model.number="constraints.coupon_minimum" /></label><label>Coupon annuel max. %<input class="input" type="number" min="0.1" max="50" step="0.1" required v-model.number="constraints.coupon_maximum" /></label></div>
          <div v-if="form.objective === 'target_coupon'" class="grid grid-cols-2 gap-2"><label>Coupon cible %<input class="input" type="number" min="0" max="50" step="0.1" required v-model.number="targetCoupon" /></label><label>Tolérance coupon — points %<input class="input" type="number" min="0.01" max="10" step="0.01" required v-model.number="couponTolerance" /></label></div>
          <div class="grid grid-cols-2 gap-2"><label>Prix d'émission cible %<input class="input" type="number" min="80" max="120" step="0.1" required v-model.number="constraints.target_price" /></label><label>Tolérance prix — points %<input class="input" type="number" min="0.01" max="3" step="0.01" required v-model.number="constraints.price_tolerance" /></label></div>
          <p class="scope-note">Le coupon est résolu par dichotomie pour chaque structure, puis repricé. L'IC95 entier du prix doit tenir dans la tolérance choisie.</p>
        </section>
        <section class="card flex flex-col gap-3">
          <h2 class="section-title">3 · Risque et budget</h2>
          <p class="text-xs text-slate-500">Contraintes facultatives, sous mesure risque-neutre Q. Les bornes IC95 sont utilisées pour filtrer, pas seulement les estimations centrales.</p>
          <label>Probabilité de perte max. %<input class="input" type="number" min="0" max="100" step="0.1" placeholder="Sans plafond" v-model="risk.loss" /></label>
          <p class="text-xs text-slate-500">Perte = somme des flux non actualisés inférieure au prix d'émission ; ce n'est pas une probabilité de franchissement de barrière.</p>
          <label>Probabilité de rappel anticipé min. %<input class="input" type="number" min="0" max="100" step="0.1" placeholder="Sans minimum" v-model="risk.autocall" /></label>
          <label>Durée moyenne max. — années<input class="input" type="number" min="0.01" max="6" step="0.1" placeholder="Sans plafond" v-model="risk.life" /></label>
          <div class="grid grid-cols-2 gap-2"><label>Simulations indépendantes<input class="input" type="number" min="1000" max="20000" step="1000" required v-model.number="simulations" /></label><label>Plafond de candidats<input class="input" type="number" min="1" max="64" step="1" required v-model.number="maxCandidates" /></label></div>
          <p class="text-xs text-slate-500">Prix sur N paires antithétiques ; probabilités sur N trajectoires de base indépendantes. Graine 42. Budget temps 120 s, vérifié entre candidats.</p>
          <div class="search-summary"><strong>{{ size ?? '—' }} structures</strong><span>Grille déterministe · coupon résolu</span></div>
          <button type="button" class="btn-secondary" @click="estimate">Vérifier le budget</button>
          <div v-if="estimateResult" class="text-xs" aria-live="polite"><p>{{ estimateResult.allowed ? 'Budget admissible' : 'Recherche bloquée' }} · {{ estimateResult.budget.estimated_peak_mb }} Mo estimés</p><p v-for="reason in estimateResult.reasons" :key="reason" class="text-red-700">{{ reason }}</p></div>
          <button type="submit" class="btn-primary" :disabled="!capability || size == null || size > maxCandidates">Rechercher les structures</button>
        </section>
      </fieldset>
    </form>
    <section v-if="busy" class="card mt-4 flex items-center justify-between" aria-live="polite"><div><strong>Recherche en cours · {{ progress.completed }} / {{ progress.total }}</strong><p class="text-xs mt-1">{{ progress.candidate_id || 'Préparation' }} · un échec isolé n'arrête pas la recherche.</p></div><button class="btn-secondary" @click="cancel">Arrêter</button></section>
    <template v-if="result">
      <div class="flex items-center justify-between mt-6"><h2 class="section-title">Résultats de la recherche {{ result.complete ? '' : 'partielle' }}</h2><button class="btn-secondary btn-sm" @click="download">Exporter le dossier JSON</button></div>
      <p v-if="stale" class="scope-note mt-2">Saisie modifiée depuis ce calcul. Les résultats ci-dessous restent ceux des hypothèses archivées dans le dossier.</p>
      <div class="stats-grid mt-3"><div v-for="(label,key) in statLabels" :key="key" class="card"><b>{{ result.statistics[key] }}</b><span>{{ label }}</span></div></div>
      <section v-if="recommended" class="card recommendation mt-4">
        <div class="flex flex-wrap justify-between gap-3"><div><p class="eyebrow">Structure recommandée dans la grille évaluée</p><h2 class="text-xl font-semibold mt-1">{{ result.request.market.underlyings.map(u => u.name).join(' / ') }} · Athena</h2></div><span class="text-3xl font-semibold">{{ pct(recommended.coupon) }} <small class="text-sm">coupon annuel</small></span></div>
        <div class="metric-grid mt-4"><div v-for="metric in metrics" :key="metric.key"><span>{{ metric.label }}</span><b>{{ display(recommended, metric) }}</b></div></div>
        <p class="mt-4 text-sm">{{ result.explanation }}</p>
        <ul class="text-xs mt-3 space-y-1"><li>✓ Prix IC95 : {{ pct(recommended.price_ic95[0]) }} à {{ pct(recommended.price_ic95[1]) }} ; cible {{ pct(result.request.constraints.target_price) }} ± {{ pct(result.request.constraints.price_tolerance) }}.</li><li>✓ Probabilité de perte Q : {{ pct(recommended.probability_loss) }} ; borne haute IC95 {{ pct(recommended.probability_loss_ic95[1]) }}{{ result.request.constraints.max_probability_loss == null ? ' (sans plafond imposé)' : ` ≤ ${pct(result.request.constraints.max_probability_loss)}` }}.</li><li>✓ Paramètres structurels dans les plages ; coupon {{ pct(recommended.coupon) }} dans les bornes de résolution.</li></ul>
      </section>
      <section v-else class="card mt-4"><h2 class="font-semibold">Aucune structure admissible</h2><p class="text-sm mt-2">Consultez les motifs de rejet. Une absence de solution dans cette grille ne signifie pas qu'aucune structure n'existe. L'incertitude Monte-Carlo peut aussi empêcher le passage d'une contrainte.</p></section>
      <div v-if="valid.length" class="grid xl:grid-cols-3 gap-4 mt-4">
        <section class="card xl:col-span-2 overflow-x-auto"><div class="flex justify-between items-center mb-3"><h2 class="section-title">Alternatives admissibles</h2><label>Trier<select class="select" v-model="sort"><option value="rank">Classement</option><option value="coupon">Coupon</option><option value="protection_barrier">Protection</option><option value="probability_loss">Perte Q</option><option value="expected_maturity">Durée moyenne</option></select></label></div>
          <table><thead><tr><th>Comparer</th><th>Rang</th><th>Structure</th><th v-for="metric in tableMetrics" :key="metric.key">{{ metric.label }}</th></tr></thead><tbody><tr v-for="candidate in alternatives" :key="candidate.candidate_id" :class="{ selected: selected.includes(candidate.candidate_id) }"><td><input type="checkbox" :value="candidate.candidate_id" v-model="selected" :disabled="selected.length >= 5 && !selected.includes(candidate.candidate_id)" :aria-label="`Comparer ${candidate.candidate_id}`" /></td><td>{{ candidate.rank }}</td><td>{{ candidate.candidate_id }}<small v-if="candidate.pareto_efficient" class="block text-blue-700">Pareto</small></td><td v-for="metric in tableMetrics" :key="metric.key">{{ display(candidate, metric) }}</td></tr></tbody></table>
          <button class="btn-secondary btn-sm mt-3" :disabled="selected.length < 2" @click="showComparison = true">Comparer {{ selected.length }} structures (2 à 5)</button>
        </section>
        <section class="card"><h2 class="section-title">Frontière coupon / protection</h2><p class="text-xs text-slate-500 mt-1">Coupon plus haut, barrière plus basse. Tous les candidats admissibles ; Pareto en bleu, recommandé en doré, sélection en vert.</p><div class="chart-container mt-3"><canvas ref="frontierCanvas" aria-label="Frontière coupon / barrière de protection" role="img"></canvas></div></section>
      </div>
      <section v-if="showComparison && compared.length >= 2" class="card mt-4 overflow-x-auto"><h2 class="section-title mb-3">Comparaison</h2><table><thead><tr><th>Caractéristique</th><th v-for="c in compared" :key="c.candidate_id">{{ c.candidate_id }} · rang {{ c.rank }}</th></tr></thead><tbody><tr v-for="metric in metrics" :key="metric.key"><th>{{ metric.label }}</th><td v-for="c in compared" :key="c.candidate_id">{{ display(c, metric) }}</td></tr><tr><th>Modèle / statut</th><td v-for="c in compared" :key="c.candidate_id">GBM · admissible</td></tr><tr><th>IC95 perte Q</th><td v-for="c in compared" :key="c.candidate_id">{{ c.probability_loss_ic95.map(pct).join(' – ') }}</td></tr><tr><th>Réserves</th><td v-for="c in compared" :key="c.candidate_id" class="whitespace-normal">{{ c.warnings.join(' ') }}</td></tr></tbody></table></section>
      <details class="card mt-4"><summary>Détails des rejets et échecs ({{ rejected.length }})</summary><ul class="text-xs mt-3 space-y-2"><li v-for="c in rejected" :key="c.candidate_id"><b>{{ c.candidate_id }} · {{ c.pricing_status }}</b> — {{ [...c.rejection_reasons, ...c.errors].join(' ') }}</li></ul></details>
      <details class="card mt-3"><summary>Hypothèses, calcul et limites</summary><p class="text-xs mt-3">GBM · grille · N={{ result.simulations }} · graine {{ result.seed }} · hypothèses du {{ result.market_date }} · {{ result.elapsed_seconds }} s · taux {{ pct(result.request.market.rate) }} · version {{ result.engine_version }}</p><ul class="text-xs mt-3 space-y-1"><li v-for="warning in result.warnings" :key="warning">{{ warning }}</li></ul><p class="text-xs mt-3">VaR, ES, rendement espéré, Greeks, probabilités physiques, Phoenix et modèles à smile indisponibles dans cette V1. L'IC95 est ponctuel, sans correction de sélection multiple. Résultat exploratoire à confirmer avant proposition client.</p></details>
    </template>
    </template>
  </main>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import Chart from 'chart.js/auto'
import { useDemoModeStore } from '../stores/demoMode.js'
import { underlyingGroups, ensureUnderlyings } from '../data/commonUnderlyings.js'
import { optimizerJson, runOptimizer, searchSize, rankedCandidates } from '../utils/productOptimizer.js'

const today = new Date().toLocaleDateString('en-CA')
const demo = useDemoModeStore()
const form = reactive({ objective: 'maximize_coupon', model: 'auto', currency: 'EUR', strike_date: today, convention: '', settlement_lag: 3 })
const assets = ref([{ ticker: '', asset_type: 'index', vol: 20, dividend: 2 }])
const rate = ref(3), correlations = reactive({ '0-1': .5, '0-2': .5, '1-2': .5 })
const ranges = reactive({ maturity_months: { minimum: 36, maximum: 60, step: 12 }, protection_barrier: { minimum: 60, maximum: 60, step: 5 }, autocall_trigger: { minimum: 100, maximum: 100, step: 5 } })
const observations = ref([3]), constraints = reactive({ target_price: 100, price_tolerance: .5, coupon_minimum: 0, coupon_maximum: 30 })
const targetCoupon = ref(8), couponTolerance = ref(.5), risk = reactive({ loss: '', autocall: '', life: '' })
const simulations = ref(4000), maxCandidates = ref(32), capability = ref(null), loading = ref(true), busy = ref(false), error = ref(''), estimateResult = ref(null), result = ref(null)
const selected = ref([]), showComparison = ref(false), sort = ref('rank'), progress = reactive({ completed: 0, total: 0, candidate_id: '' })
const frontierCanvas = ref(null)
let chart = null, aborter = null, runSignature = ''
const currencies = ['EUR','USD','GBP','CHF','JPY','SGD']
const frequencies = [{value:1,label:'Mensuelle'},{value:3,label:'Trimestrielle'},{value:6,label:'Semestrielle'},{value:12,label:'Annuelle'}]
const rangeFields = [{key:'maturity_months',label:'Maturité (mois)',min:12,max:60,step:1},{key:'protection_barrier',label:'Protection (%)',min:30,max:100,step:.5},{key:'autocall_trigger',label:'Rappel (%)',min:80,max:120,step:.5}]
const statLabels = { generated:'Générés', priced:'Pricés', valid:'Admissibles', rejected:'Rejetés', failed:'Échecs', not_evaluated:'Non évalués' }
const metrics = [{key:'maturity_months',label:'Maturité',unit:'months'},{key:'coupon',label:'Coupon annuel',unit:'pct'},{key:'protection_barrier',label:'Protection',unit:'pct'},{key:'autocall_trigger',label:'Rappel',unit:'pct'},{key:'observation_months',label:'Fréquence',unit:'months'},{key:'fair_value',label:'Juste valeur',unit:'pct'},{key:'probability_loss',label:'Perte Q',unit:'pct'},{key:'probability_autocall',label:'Rappel anticipé Q',unit:'pct'},{key:'expected_maturity',label:'Durée moyenne',unit:'years'}]
const tableMetrics = computed(() => metrics.filter(m => ['maturity_months','coupon','protection_barrier','fair_value','probability_loss'].includes(m.key)))
const catalogue = computed(() => [...new Map(underlyingGroups.flatMap(g => g.items).filter(i => i.ccy === form.currency).map(i => [i.ticker, i])).values()])
const pairs = computed(() => assets.value.flatMap((_, i) => assets.value.slice(i+1).map((__, k) => ({i,j:i+k+1,key:`${i}-${i+k+1}`}))))
const size = computed(() => searchSize({ ...ranges, observation_months: observations.value }))
const valid = computed(() => rankedCandidates(result.value))
const recommended = computed(() => valid.value.find(c => c.candidate_id === result.value?.recommended_id))
const rejected = computed(() => (result.value?.candidates || []).filter(c => c.constraint_status !== 'PASS'))
const alternatives = computed(() => [...valid.value].sort((a,b) => sort.value === 'coupon' ? b.coupon-a.coupon : a[sort.value]-b[sort.value]))
const compared = computed(() => valid.value.filter(c => selected.value.includes(c.candidate_id)))
const signature = computed(() => JSON.stringify({form, assets:assets.value, rate:rate.value, correlations, ranges, observations:observations.value, constraints, targetCoupon:targetCoupon.value, couponTolerance:couponTolerance.value, risk, simulations:simulations.value, maxCandidates:maxCandidates.value}))
const stale = computed(() => result.value && signature.value !== runSignature)
const pct = value => value == null ? '—' : `${(value*100).toLocaleString('fr-FR',{maximumFractionDigits:2,minimumFractionDigits:2})} %`
function display(c,m) { return c[m.key] == null ? '—' : m.unit === 'pct' ? pct(c[m.key]) : `${Number(c[m.key]).toLocaleString('fr-FR',{maximumFractionDigits:2})} ${m.unit === 'months' ? 'mois' : 'ans'}` }
const optional = (value, divisor=1) => String(value).trim() === '' ? null : Number(value)/divisor

function requestBody() {
  const numbers = [rate.value, form.settlement_lag, simulations.value, maxCandidates.value,
    ...Object.values(constraints), ...assets.value.flatMap(u => [u.vol, u.dividend]),
    ...pairs.value.map(pair => correlations[pair.key])]
  if (form.objective === 'target_coupon') numbers.push(targetCoupon.value, couponTolerance.value)
  if (numbers.some(n => n === '' || n == null || !Number.isFinite(Number(n)))) throw new Error('Renseignez chaque hypothèse numérique obligatoire ; une donnée absente ne vaut pas zéro.')
  const converted = Object.fromEntries(Object.entries(ranges).map(([key,value]) => [key,Object.fromEntries(Object.entries(value).map(([part,n]) => [part,Number(n)/(key === 'maturity_months' ? 1 : 100)]))]))
  if (size.value == null || !form.convention || assets.value.some(u => !catalogue.value.find(i => i.ticker === u.ticker))) throw new Error('Vérifiez les plages, choisissez la convention et chaque sous-jacent dans sa devise.')
  const body = { ...form, product_family:'autocall_athena', market:{ as_of:form.strike_date, source:'USER_ASSUMPTION', rate:rate.value/100,
    underlyings:assets.value.map(u => ({ ticker:u.ticker, name:catalogue.value.find(i => i.ticker === u.ticker).label, currency:form.currency, asset_type:u.asset_type, sigma:u.vol/100, q:u.dividend/100 })),
    correlation:assets.value.map((_,i) => assets.value.map((__,j) => i === j ? 1 : Number(correlations[`${Math.min(i,j)}-${Math.max(i,j)}`]))) },
    ranges:{...converted,observation_months:[...observations.value]}, constraints:{...Object.fromEntries(Object.entries(constraints).map(([k,v]) => [k,v/100])), target_coupon:form.objective === 'target_coupon' ? targetCoupon.value/100 : null, coupon_tolerance:couponTolerance.value/100, max_probability_loss:optional(risk.loss,100), min_probability_autocall:optional(risk.autocall,100), max_expected_maturity:optional(risk.life)}, search:{simulations:simulations.value,max_candidates:maxCandidates.value,strategy:'grid',seed:42} }
  if (constraints.coupon_minimum >= constraints.coupon_maximum) throw new Error('Les bornes du coupon sont incohérentes.')
  return body
}
async function estimate() { error.value=''; try { estimateResult.value = await optimizerJson('estimate-search',requestBody()) } catch(e) { error.value=e.message } }
async function start() {
  error.value=''
  try {
    const body=requestBody(); busy.value=true; aborter=new AbortController()
    estimateResult.value=await optimizerJson('estimate-search',body,aborter.signal)
    aborter.signal.throwIfAborted()
    if (!estimateResult.value.allowed) throw new Error(estimateResult.value.reasons.join(' '))
    result.value=null; selected.value=[]; showComparison.value=false; runSignature=signature.value
    Object.assign(progress,{completed:0,total:estimateResult.value.candidate_count,candidate_id:''})
    await runOptimizer(body,aborter.signal,event => {
      if(event.type==='progress') Object.assign(progress,event)
      if(event.type==='result') { result.value=event.result; selected.value=rankedCandidates(event.result).slice(0,2).map(c=>c.candidate_id) }
    })
  } catch(e) { error.value=e.name==='AbortError' ? 'Recherche arrêtée. Le calcul du candidat en cours se termine côté serveur ; aucun résultat final conservé.' : e.message }
  finally { busy.value=false; aborter=null }
}
function cancel() { aborter?.abort() }
function download() { const url=URL.createObjectURL(new Blob([JSON.stringify(result.value,null,2)],{type:'application/json'})); const a=document.createElement('a'); a.href=url; a.download=`structura-optimizer-${result.value.market_date}.json`; a.click(); URL.revokeObjectURL(url) }
async function drawChart() {
  await nextTick(); chart?.destroy(); chart=null
  if(!frontierCanvas.value || !valid.value.length) return
  chart=new Chart(frontierCanvas.value,{type:'scatter',data:{datasets:[{label:'Structures admissibles',data:valid.value.map(c=>({x:c.protection_barrier*100,y:c.coupon*100,id:c.candidate_id})),pointRadius:valid.value.map(c=>c.candidate_id===result.value.recommended_id?7:5),pointBackgroundColor:valid.value.map(c=>c.candidate_id===result.value.recommended_id?'#b88736':selected.value.includes(c.candidate_id)?'#0f766e':c.pareto_efficient?'#2563eb':'#94a3b8')}]},options:{responsive:true,maintainAspectRatio:false,animation:false,plugins:{legend:{display:false},tooltip:{callbacks:{label:ctx=>`${ctx.raw.id} : coupon ${ctx.parsed.y.toFixed(2)} %, barrière ${ctx.parsed.x.toFixed(1)} %`}}},scales:{x:{title:{display:true,text:'Barrière de protection (%)'}},y:{title:{display:true,text:'Coupon annuel (%)'}}}}})
}
watch([result,selected,()=>demo.enabled],drawChart,{deep:true})
watch(signature,()=>{estimateResult.value=null})
onMounted(async()=>{try { const [caps]=await Promise.all([optimizerJson('capabilities'),ensureUnderlyings()]); capability.value=caps; if(!catalogue.value.length) error.value='Catalogue indisponible. Vérifiez les sous-jacents dans Administration.' } catch(e){error.value=e.message} finally{loading.value=false} })
onBeforeUnmount(()=>{cancel();chart?.destroy()})
</script>

<style scoped>
.optimizer { font-size: 13px; }
label { display: flex; flex-direction: column; gap: 5px; font-size: 12px; }
.input,.select { width:100%; min-width:0; }
.section-title { font-size:14px; font-weight:700; }
.scope-note { background:#f5f7fa; border-left:3px solid #94a3b8; padding:10px 12px; font-size:12px; color:#475569; }
.alert-error { background:#fff1f2; color:#9f1239; padding:12px; border-radius:6px; }
.asset-row { border-top:1px solid #e2e8f0; padding-top:10px; }
.range-head { display:grid; grid-template-columns:1.4fr repeat(3,1fr); align-items:center; gap:6px; font-size:11px; }
.check-label { flex-direction:row; align-items:center; }
.search-summary { display:flex; flex-direction:column; padding:14px; background:#eff6ff; color:#1e3a8a; gap:5px; }
.search-summary strong { font-size:20px; }
.stats-grid { display:grid; grid-template-columns:repeat(6,minmax(0,1fr)); gap:10px; }
.stats-grid .card { display:flex; flex-direction:column; gap:5px; padding:12px; }
.stats-grid b { font-size:23px; }.stats-grid span { font-size:11px; color:#64748b; }
.recommendation { border-top:3px solid #b88736; }.eyebrow { font-size:11px; text-transform:uppercase; letter-spacing:.08em; color:#85602c; }
.metric-grid { display:grid; grid-template-columns:repeat(5,minmax(0,1fr)); gap:15px; }
.metric-grid div { display:flex; flex-direction:column; gap:6px; }.metric-grid span { font-size:11px; color:#64748b; }
table { width:100%; font-size:12px; border-collapse:collapse; }th,td { padding:9px 8px; text-align:right; border-bottom:1px solid #e2e8f0; white-space:nowrap; }th:first-child,td:first-child { text-align:left; }th { color:#64748b; font-weight:600; }.selected { background:#eff6ff; }
.chart-container { height:290px; }summary { cursor:pointer; font-weight:600; }
@media(max-width:800px) { .stats-grid,.metric-grid { grid-template-columns:repeat(2,minmax(0,1fr)); } }
</style>
