<template>
  <main class="optimizer p-4 lg:p-6 w-full max-w-[1500px] mx-auto">
    <div class="page-header">
      <div><h1 class="page-title">Product Optimizer</h1><p class="page-subtitle">Contraintes → paramètre résolu au prix cible → solutions admissibles</p></div>
      <div class="flex gap-2"><RouterLink class="btn-ghost btn-sm" to="/structuring/researches">Recherches & pricings</RouterLink><RouterLink class="btn-ghost btn-sm" to="/structuring">← Structuring Intelligence</RouterLink></div>
    </div>
    <p v-if="demo.enabled" class="scope-note mt-4">Mode Démo : les hypothèses et les résultats de l'Optimizer sont masqués. Désactivez ce mode pour travailler sur une recherche.</p>
    <template v-else>
    <p class="scope-note mt-3">GBM · Protection européenne · 1 à 3 actifs de même devise. Champs, objectifs et règles de paiement propres au script choisi, hors défaut émetteur.</p>
    <p v-if="resumeWarning" class="scope-note mt-3">{{ resumeWarning }}</p>
    <p v-if="error" role="alert" class="alert-error mt-3">{{ error }}</p>
    <form @submit.prevent="start" class="request-form mt-3">
      <OptimizerPanel title="Nom et intention de la recherche" :help="helpFor('intention')" height="24vh" class="mb-3">
        <label>Nom du dossier<input class="input" :disabled="busy || loading" v-model="title" maxlength="160" placeholder="Automatique si laissé vide" /></label>
        <label class="mt-2">Résumé de votre demande<textarea class="input" :disabled="busy || loading" v-model="intention" maxlength="4000" rows="3" placeholder="Ex. : rechercher un Athena trimestriel avec protection à 60 %, en privilégiant le coupon." /></label>
        <p class="text-xs text-slate-500 mt-2">Votre intention et le résumé exact des paramètres seront sauvegardés avec les résultats.</p>
      </OptimizerPanel>
      <p v-if="parentResearch" class="scope-note mb-3">Reprise de « {{ parentResearch.title }} » (marché d’origine du {{ parentResearch.pricing_date }}). <span v-if="frozenIdentity">Hypothèses et références du dossier conservées.</span> Ce lancement créera une nouvelle recherche liée au dossier d’origine. <button v-if="frozenIdentity" class="btn-ghost btn-sm" :disabled="busy" type="button" @click="refreshMarket">Actualiser les références</button></p>
      <fieldset :disabled="busy || loading" class="optimizer-panels">
        <section class="card flex flex-col gap-3">
          <h2 class="section-title">1 · Objectif et univers</h2>
          <p class="text-xs text-slate-500">Marché chargé automatiquement pour les titres sélectionnés et la date de pricing. Hypothèses utilisées arrondies à deux décimales ; références sources conservées dans le snapshot figé au lancement.</p>
          <p v-if="marketLoading" class="scope-note" role="status">Chargement du marché historique…</p>
          <p v-if="marketError" class="alert-error" role="alert">{{ marketError }} Les champs absents doivent être complétés manuellement.</p>
          <p v-for="warning in automaticMarket?.warnings" :key="warning" class="scope-note">{{ warning }}</p>
          <label><span class="label-title">Objectif <HelpTip :text="helpFor('objective')" /></span><select class="select" v-model="form.objective"><option v-for="item in activeFamily?.objectives" :key="item.value" :value="item.value">{{ item.label }}</option></select></label>
          <div class="grid gap-2"><label><span class="label-title">Famille / script <HelpTip :text="helpFor('product_family')" /></span><select class="select" v-model="form.product_family"><option v-for="family in supportedFamilies" :key="family.product_family" :value="family.product_family">{{ family.label }}</option></select></label><label><span class="label-title">Modèle <HelpTip :text="helpFor('model')" /></span><select v-model="form.model" class="select"><option value="auto">Auto — GBM</option><option value="constant">GBM explicite</option></select></label></div>
          <div class="grid grid-cols-2 gap-2"><label><span class="label-title">Devise <HelpTip :text="helpFor('currency')" /></span><select v-model="form.currency" class="select"><option v-for="ccy in currencies" :key="ccy">{{ ccy }}</option></select></label><label><span class="label-title">Date de pricing <HelpTip :text="helpFor('pricing_date')" /></span><input class="input" required type="date" :max="today" v-model="form.strike_date" /></label></div>
          <p class="text-xs text-slate-500">Recherche à l’émission : fixing initial et valeur au {{ form.strike_date }}. Les constatations et leurs paiements sont calculés séparément depuis le fixing initial. Démarrage différé et produits en cours de vie hors de ce parcours.</p>
          <div class="grid grid-cols-2 gap-2"><label><span class="label-title">Convention <HelpTip :text="helpFor('convention')" /></span><select v-model="form.convention" class="select" required><option disabled value="">À choisir</option><option value="modified_following">Modified Following</option><option value="following">Following</option><option value="preceding">Preceding</option><option value="none">Sans ajustement</option></select></label><label><span class="label-title">Paiement — jours ouvrés <HelpTip :text="helpFor('settlement_lag')" /></span><input class="input" type="number" min="0" max="10" step="1" v-model.number="form.settlement_lag" required /></label></div>
          <p class="text-xs text-slate-500">Action / indice issu du référentiel ; qualification manuelle seulement si inconnue. Même devise pour tous les titres et le règlement.</p>
          <div v-for="(asset, index) in assets" :key="index" class="asset-row">
            <label><span class="label-title">Sous-jacent {{ index + 1 }} <HelpTip :text="helpFor('underlying')" /></span><select class="select" required v-model="asset.ticker"><option value="" disabled>Choisir dans le catalogue</option><option v-for="item in catalogue" :key="item.ticker" :value="item.ticker">{{ item.label }} · {{ item.ticker }}</option></select></label>
            <div class="asset-inputs mt-2"><label><span class="label-title">Type <HelpTip :text="helpFor('asset_type')" /></span><select class="select" required :disabled="asset.classified" v-model="asset.asset_type"><option disabled value="">À qualifier</option><option value="index">Indice</option><option value="equity">Action</option></select></label><label><span class="label-title">Vol. utilisée % <HelpTip :text="helpFor('sigma')" /></span><OptimizerNumberInput class="input" required min="0" max="150" v-model="asset.vol" @input="asset.manual.vol=true" /></label><label><span class="label-title">Dividende utilisé % <HelpTip :text="helpFor('q')" /></span><OptimizerNumberInput class="input" required min="0" max="50" v-model="asset.dividend" @input="asset.manual.dividend=true" /></label></div>
            <div v-for="[field,key] in [['vol','sigma'],['dividend','q']]" :key="key" class="text-xs text-slate-500 mt-1">
              {{ field==='vol'?'Vol réalisée':'Dividendes historiques' }} : {{ referenceLabel(asset.ticker,key) }} · {{ assumptionLabel(asset,field) }}
              <button v-if="assetReference(asset.ticker,key)" type="button" class="btn-ghost btn-sm" @click="resetAssetReference(asset,field,key)">Revenir à la référence</button>
            </div>
            <p v-for="warning in automaticMarket?.underlyings.find(item=>item.ticker===asset.ticker)?.warnings" :key="warning" class="text-xs text-amber-700 mt-1">{{ warning }}</p>
            <details class="mt-2"><summary>Courbe de dividendes <HelpTip :text="helpFor('dividend_curve')" /></summary><OptimizerCurveInput v-model="asset.dividendCurve" label="Courbe de dividendes" rate-label="Rendement (%)" :initial-rate="asset.dividend" :minimum="0" :maximum="50" :max-nodes="30" annual /><p class="text-xs text-slate-500">Vide : rendement plat. Buckets annuels dégressifs ; premier rendement égal au dividende saisi. Le dernier bucket est prolongé.</p></details>
            <button v-if="assets.length > 1" type="button" class="btn-ghost btn-sm mt-1" @click="assets.splice(index, 1)">Retirer</button>
          </div>
          <button v-if="assets.length < 3" type="button" class="btn-secondary btn-sm" @click="assets.push(emptyOptimizerAsset())">Ajouter au panier worst-of</button>
          <div v-if="assets.length > 1" class="grid grid-cols-3 gap-2"><label v-for="pair in pairs" :key="pair.key"><span class="label-title">Corr. {{ pair.i + 1 }}/{{ pair.j + 1 }} <HelpTip :text="helpFor('correlation')" /></span><OptimizerNumberInput class="input" min="-0.99" max="0.99" required v-model="correlations[pair.key]" @input="manualCorrelations[pairIdentity(pair)]=true" /></label></div>
          <p v-if="pairs.length" class="text-xs text-slate-500">Corrélations : {{ automaticMarket?.provenance.correlation?.as_of || 'référence absente' }} · rendements ajustés communs. {{ Object.keys(manualCorrelations).some(key=>manualCorrelations[key])?'Surcharges manuelles conservées.':'' }}</p>
          <button v-if="pairs.length && automaticMarket?.correlation" type="button" class="btn-ghost btn-sm" @click="resetCorrelations">Revenir aux corrélations de référence</button>
          <label><span class="label-title">Taux plat / repli % <HelpTip :text="helpFor('rate')" /></span><OptimizerNumberInput class="input" min="-10" max="30" required v-model="rate" /></label>
          <details><summary>Courbe de taux et funding <HelpTip :text="helpFor('yield_curve')" /></summary>
            <OptimizerCurveInput v-model="yieldNodes" label="Courbe de taux zéro" :initial-rate="rate" />
            <label class="mt-2"><span class="label-title">Funding <HelpTip :text="helpFor('funding')" /></span><select class="select" v-model="fundingMode"><option value="flat">Spread plat</option><option value="curve">Courbe par maturité</option></select></label>
            <label v-if="fundingMode === 'flat'" class="mt-2"><span class="label-title">Spread de funding — bps/an <HelpTip :text="helpFor('funding')" /></span><OptimizerNumberInput class="input" min="-500" max="5000" required v-model="fundingSpread" /></label>
            <OptimizerCurveInput v-else v-model="fundingNodes" label="Courbe de funding" rate-label="Spread (%)" empty-label="Ajoutez des nœuds ou choisissez un spread plat." :initial-rate="fundingSpread/100" :minimum="-5" :maximum="50" />
            <p class="text-xs text-slate-500 mt-2">Taux zéro interpolés comme dans le Pricer. Funding appliqué à l’actualisation seule ; 100 bps = 1 % par an.</p>
          </details>
          <p class="scope-note">Volatilité réalisée utilisée comme hypothèse GBM ; dividendes historiques utilisés comme hypothèse forward, sans garantie. Taux, courbes et funding : hypothèses manuelles. Les références ne sont pas des cotations implicites de booking.</p>
        </section>
        <section class="card flex flex-col gap-3">
          <h2 class="section-title">2 · Espace de recherche</h2>
          <OptimizerPayoffFields :key="`${form.product_family}/${parentResearch?.id || ''}`" :family="activeFamily" :ranges="ranges" :settings="payoffSettings" v-model:observations="observations" @update:ranges="updateRanges" @update:settings="updateSettings" />
          <p class="text-xs text-slate-500">Maturités en mois, multiples des fréquences retenues sur les autocalls. La borne haute est incluse seulement si elle tombe sur le pas.<span v-if="activeFamily?.range_fields.some(field=>field.key==='protection_barrier')"> Barrière de protection plus basse = meilleure protection conditionnelle.</span></p>
          <div v-if="activeFamily" class="grid grid-cols-2 gap-2"><label><span class="label-title">{{ activeFamily.solved_field.label }} — min. <HelpTip :text="helpFor(activeFamily.solved_field.key)" /></span><OptimizerNumberInput class="input" :min="activeFamily.solved_field.minimum*100" :max="activeFamily.solved_field.maximum*100" required v-model="solutionMinimum" /></label><label><span class="label-title">{{ activeFamily.solved_field.label }} — max. <HelpTip :text="helpFor(activeFamily.solved_field.key)" /></span><OptimizerNumberInput class="input" :min="activeFamily.solved_field.minimum*100" :max="activeFamily.solved_field.maximum*100" required v-model="solutionMaximum" /></label></div>
          <div v-if="form.objective === 'target_coupon'" class="grid grid-cols-2 gap-2"><label><span class="label-title">Coupon cible % <HelpTip :text="helpFor('coupon')" /></span><OptimizerNumberInput class="input" min="0" max="50" required v-model="targetCoupon" /></label><label><span class="label-title">Tolérance coupon — points % <HelpTip :text="helpFor('coupon_tolerance')" /></span><OptimizerNumberInput class="input" min="0.01" max="10" required v-model="couponTolerance" /></label></div>
          <div class="grid grid-cols-2 gap-2"><label><span class="label-title">Prix d'émission cible % <HelpTip :text="helpFor('target_price')" /></span><OptimizerNumberInput class="input" min="80" max="120" required v-model="constraints.target_price" /></label><label><span class="label-title">Tolérance prix — points % <HelpTip :text="helpFor('price_tolerance')" /></span><OptimizerNumberInput class="input" min="0.01" max="3" required v-model="constraints.price_tolerance" /></label></div>
          <div class="grid grid-cols-2 gap-2"><label><span class="label-title">Frais initiaux — points de nominal % <HelpTip :text="helpFor('costs')" /></span><OptimizerNumberInput class="input" min="0" max="10" required v-model="economics.upfront_fees" /></label><label><span class="label-title">Marge — points de nominal % <HelpTip :text="helpFor('costs')" /></span><OptimizerNumberInput class="input" min="0" max="10" required v-model="economics.structuring_margin" /></label></div>
          <p class="scope-note">Budget du payoff : {{ netBudget.toLocaleString('fr-FR') }} % = {{ constraints.target_price }} % − {{ economics.upfront_fees }} % de frais − {{ economics.structuring_margin }} % de marge. Coûts initiaux, hors flows investisseurs ; funding déjà dans le PV.</p>
          <p class="scope-note">Le paramètre choisi est résolu par dichotomie. Jusqu’à cinq candidats sont ensuite revalorisés à paramètre conservé sur des tirages indépendants ; leur intervalle de prix entier doit tenir dans la tolérance.</p>
        </section>
        <section class="card flex flex-col gap-3">
          <h2 class="section-title">3 · Risque et budget</h2>
          <p class="text-xs text-slate-500">Contraintes facultatives, sous mesure risque-neutre Q. Les bornes IC95 sont utilisées pour filtrer, pas seulement les estimations centrales.</p>
          <label><span class="label-title">Probabilité de perte max. % <HelpTip :text="helpFor('probability_loss')" /></span><OptimizerNumberInput class="input" min="0" max="100" placeholder="Sans plafond" v-model="risk.loss" /></label>
          <p class="text-xs text-slate-500">Perte = somme des flux non actualisés inférieure au prix d'émission ; ce n'est pas une probabilité de franchissement de barrière.</p>
          <label v-if="activeFamily?.has_autocall"><span class="label-title">Probabilité de rappel anticipé min. % <HelpTip :text="helpFor('probability_autocall')" /></span><OptimizerNumberInput class="input" min="0" max="100" placeholder="Sans minimum" v-model="risk.autocall" /></label>
          <label v-if="activeFamily?.risk_severity"><span class="label-title">Perte en capital moyenne max. — % du nominal <HelpTip :text="helpFor('expected_capital_loss')" /></span><OptimizerNumberInput class="input" min="0" max="100" placeholder="Sans plafond" v-model="risk.capitalLoss" /></label>
          <p v-if="activeFamily?.risk_severity" class="text-xs text-slate-500">Perte en capital de la jambe put, avant coupon ; moyenne Q non actualisée. La sévérité conditionnelle mesure la perte moyenne parmi les trajectoires en perte de capital.</p>
          <label><span class="label-title">Durée moyenne max. — années <HelpTip :text="helpFor('expected_maturity')" /></span><OptimizerNumberInput class="input" min="0.01" max="6" placeholder="Sans plafond" v-model="risk.life" /></label>
          <div class="grid grid-cols-2 gap-2"><label><span class="label-title">Simulations indépendantes <HelpTip :text="helpFor('simulations')" /></span><input class="input" type="number" min="1000" max="20000" step="1000" required v-model.number="simulations" /></label><label><span class="label-title">Plafond de candidats <HelpTip :text="helpFor('budget')" /></span><input class="input" type="number" min="1" max="256" step="1" required v-model.number="maxCandidates" /></label></div>
          <label><span class="label-title">Budget temps maximal — secondes <HelpTip :text="helpFor('budget')" /></span><input class="input" type="number" min="30" max="3600" step="30" required v-model.number="maxSeconds" /></label>
          <label><span class="label-title">Calculs simultanés <HelpTip :text="helpFor('budget')" /></span><select class="select" v-model.number="parallelWorkers"><option v-for="n in [1,2,3,4]" :key="n" :value="n">{{ n === 1 ? '1 — séquentiel' : `${n} structures` }}</option></select></label>
          <p class="text-xs text-slate-500">Grille complète calculée par lots bornés au nombre de processus ; mémoire contrôlée par calcul, sans réduction des simulations. Exploration à graine 42 ; validation indépendante des cinq premiers au maximum à N et 2N paires. Budget global {{ maxSeconds }} s ; seuls les candidats confirmés sont recommandables.</p>
          <div class="search-summary"><strong>{{ size ?? '—' }} structures</strong><span>Grille déterministe · paramètre résolu</span></div>
          <p v-if="size!=null && size>maxCandidates" class="text-xs text-red-700">{{ size }} combinaisons dépassent le plafond choisi de {{ maxCandidates }}. Augmentez-le jusqu’à 256 ou ajustez explicitement les axes explorés.</p>
          <button type="button" class="btn-secondary" @click="estimate">Vérifier le budget</button>
          <div v-if="estimateResult" class="text-xs" aria-live="polite"><p>{{ estimateResult.allowed ? 'Budget admissible' : 'Recherche bloquée' }} · {{ estimateResult.budget.estimated_peak_mb }} Mo estimés</p><p>{{ estimateResult.candidate_count }} combinaisons · {{ estimateResult.contractually_excluded ?? '—' }} exclusions contractuelles · {{ estimateResult.pricing_count ?? '—' }} candidats à calculer.</p><p v-if="estimateResult.execution">{{ estimateResult.execution.workers }} calcul(s) simultané(s) retenu(s)<span v-if="estimateResult.execution.workers < parallelWorkers"> sur {{ parallelWorkers }} demandés, selon la grille et les ressources</span>.</p><p v-for="reason in estimateResult.reasons" :key="reason" class="text-red-700">{{ reason }}</p></div>
          <p v-for="warning in estimateResult?.warnings" :key="warning" class="text-xs text-amber-700">{{ warning }}</p>
          <button type="submit" class="btn-primary" :disabled="!capability || marketLoading || size == null || size > maxCandidates">{{ busy?'Sauvegarde et lancement…':'Rechercher les structures' }}</button>
        </section>
      </fieldset>
    </form>
    </template>
  </main>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import HelpTip from '../components/HelpTip.vue'
import OptimizerPanel from '../components/OptimizerPanel.vue'
import OptimizerNumberInput from '../components/OptimizerNumberInput.vue'
import OptimizerCurveInput from '../components/OptimizerCurveInput.vue'
import OptimizerPayoffFields from '../components/OptimizerPayoffFields.vue'
import { payoffState, payoffPayload, payoffMode, solutionPayload } from '../utils/optimizerPayoff.js'
import { roundPricingInput, emptyOptimizerAsset, applyAutomaticAsset, withAutomaticReferences, parseOptimizerCurve, remapCorrelations } from '../utils/optimizerMarket.js'
import { researchApi,helpFor } from '../utils/optimizerResearch.js'
import { researchFormState } from '../utils/optimizerResume.js'
import { useDemoModeStore } from '../stores/demoMode.js'
import { underlyingGroups, ensureUnderlyings } from '../data/commonUnderlyings.js'
import { optimizerJson, searchSize } from '../utils/productOptimizer.js'
const route=useRoute(),router=useRouter()
const resumeWarning=ref('')
const title=ref(''),intention=ref(''),parentResearch=ref(null),frozenIdentity=ref(''),marketRefresh=ref(0)
let restoring=false,commandSignature='',savedCommand=null,disposed=false
const marketIdentity=()=>JSON.stringify([form.strike_date,form.currency,assets.value.map(asset=>asset.ticker)])

const today = new Date().toLocaleDateString('en-CA')
const demo = useDemoModeStore()
const automaticMarket = ref(null), marketLoading=ref(false), marketError=ref('')
const manualCorrelations=reactive({})
const yieldNodes = ref([]), fundingNodes = ref([]), fundingSpread = ref(0), fundingMode = ref('flat')
const economics = reactive({upfront_fees:0,structuring_margin:0})
const form = reactive({ product_family:'autocall_athena', objective: 'maximize_coupon', model: 'auto', currency: 'EUR', strike_date: today, convention: '', settlement_lag: 3 })
const assets = ref([emptyOptimizerAsset()])
const rate = ref(3), correlations = reactive({})
const ranges = reactive({ maturity_months: { minimum: 36, maximum: 60, step: 12 }, protection_barrier: { minimum: 60, maximum: 60, step: 5 }, autocall_trigger: { minimum: 100, maximum: 100, step: 5 } })
const payoffSettings = reactive({})
const observations = ref([3]), constraints = reactive({ target_price: 100, price_tolerance: .5 })
const solutionMinimum=ref(0), solutionMaximum=ref(30)
const netBudget = computed(() => constraints.target_price-economics.upfront_fees-economics.structuring_margin)
const targetCoupon = ref(8), couponTolerance = ref(.5), risk = reactive({ loss: '', autocall: '', life: '', capitalLoss:'' })
const simulations = ref(4000), maxCandidates = ref(256), maxSeconds=ref(1800), parallelWorkers = ref(2), capability = ref(null), loading = ref(true), busy = ref(false), error = ref(''), estimateResult = ref(null)
let marketAborter=null, marketTimer=null, marketGeneration=0
const currencies = ['EUR','USD','GBP','CHF','JPY','SGD']
const supportedFamilies = computed(()=>(capability.value?.families || []).filter(family=>family.status==='SUPPORTED'))
const activeFamily = computed(()=>payoffMode(supportedFamilies.value.find(family=>family.product_family===form.product_family),form.objective))
function replaceFields(target,next) { for(const key of Object.keys(target)) delete target[key]; Object.assign(target,next) }
function updateRanges(next) { replaceFields(ranges,next) }
function updateSettings(next) { replaceFields(payoffSettings,next) }
let solutionConvention=''
watch(activeFamily,family=>{ if(!family) return
  const state=payoffState(family,ranges); updateRanges(state.ranges); updateSettings(state.settings)
  if(!family.has_autocall) risk.autocall=''
  if(!family.risk_severity) risk.capitalLoss=''
  const convention=`${family.solved_field.key}/${family.solved_field.value_convention}`
  if(solutionConvention!==convention) {
    solutionMinimum.value=family.solved_field.initial_minimum*100; solutionMaximum.value=family.solved_field.initial_maximum*100
    solutionConvention=convention
  }
  if(form.objective!==family.objective) form.objective=family.objective
},{flush:'sync'})
const catalogue = computed(() => [...new Map(underlyingGroups.flatMap(g => g.items).filter(i => i.ccy === form.currency).map(i => [i.ticker, i])).values()])
watch(()=>assets.value.map(asset=>asset.ticker),(nextTickers,previousTickers)=>{
  if(restoring) return
  const remapped=remapCorrelations(previousTickers,nextTickers,correlations,null)
  for(const key of Object.keys(correlations)) delete correlations[key]
  Object.assign(correlations,remapped)
  const activePairs=new Set(nextTickers.flatMap((ticker,i)=>nextTickers.slice(i+1).map(other=>[ticker,other].sort().join('|'))))
  for(const key of Object.keys(manualCorrelations)) if(!activePairs.has(key)) delete manualCorrelations[key]
  for(let i=0;i<nextTickers.length;i++) {
    const asset=assets.value[i]
    if(asset._ticker!==asset.ticker) {
      const identity=catalogue.value.find(item=>item.ticker===asset.ticker)
      const kind=['equity','index'].includes(identity?.asset_class)?identity.asset_class:''
      Object.assign(asset,emptyOptimizerAsset(asset.ticker,kind),{_ticker:asset.ticker})
    }
    for(let j=i+1;j<nextTickers.length;j++) {
      if(!previousTickers.includes(nextTickers[i]) || !previousTickers.includes(nextTickers[j])) correlations[`${i}-${j}`]=null
    }
  }
},{flush:'sync'})
const pairs = computed(() => assets.value.flatMap((_, i) => assets.value.slice(i+1).map((__, k) => ({i,j:i+k+1,key:`${i}-${i+k+1}`}))))
const size = computed(() => activeFamily.value ? searchSize({ ...ranges, ...(activeFamily.value.has_autocall?{observation_months:observations.value}:{}) }) : null)
const signature = computed(() => JSON.stringify({form, assets:assets.value, rate:rate.value, correlations, ranges, payoffSettings, observations:observations.value, constraints,solutionMinimum:solutionMinimum.value,solutionMaximum:solutionMaximum.value, targetCoupon:targetCoupon.value, couponTolerance:couponTolerance.value, risk, simulations:simulations.value, maxCandidates:maxCandidates.value,maxSeconds:maxSeconds.value, parallelWorkers:parallelWorkers.value,economics,yieldNodes:yieldNodes.value,fundingNodes:fundingNodes.value,fundingSpread:fundingSpread.value,fundingMode:fundingMode.value,automaticMarket:automaticMarket.value}))
const pct = value => value == null ? '—' : `${(value*100).toLocaleString('fr-FR',{maximumFractionDigits:2,minimumFractionDigits:2})} %`
const optional = (value, divisor=1) => String(value).trim() === '' ? null : Number(value)/divisor

function requestBody() {
  if(marketLoading.value) throw Error('Attendez la fin du chargement des références de marché.')
  if(assets.value.some(asset=>!asset.asset_type)) throw Error('Qualifiez action / indice pour les sous-jacents inconnus du référentiel.')
  const numbers = [rate.value, form.settlement_lag, simulations.value, maxCandidates.value, maxSeconds.value, parallelWorkers.value,
    ...Object.values(constraints),solutionMinimum.value,solutionMaximum.value, ...Object.values(economics), ...(fundingMode.value === 'flat' ? [fundingSpread.value] : []), ...assets.value.flatMap(u => [u.vol, u.dividend]),
    ...pairs.value.map(pair => correlations[pair.key])]
  if (form.objective === 'target_coupon') numbers.push(targetCoupon.value, couponTolerance.value)
  if (numbers.some(n => n === '' || n == null || !Number.isFinite(Number(n)))) throw new Error('Renseignez chaque hypothèse numérique obligatoire ; une donnée absente ne vaut pas zéro.')
  const payoff = payoffPayload(activeFamily.value,ranges,payoffSettings,observations.value)
  if (size.value == null || !form.convention || assets.value.some(u => !catalogue.value.find(i => i.ticker === u.ticker))) throw new Error('Vérifiez les plages, choisissez la convention et chaque sous-jacent dans sa devise.')
  const body = { ...form, pricing_date:form.strike_date, ...payoff, market:{ as_of:form.strike_date, source:'USER_ASSUMPTION', rate:rate.value/100, yield_curve:parseOptimizerCurve(yieldNodes.value), funding_curve:fundingMode.value === 'curve' ? parseOptimizerCurve(fundingNodes.value) : [], funding_spread:fundingMode.value === 'flat' ? fundingSpread.value/10000 : 0,
    underlyings:assets.value.map(u => ({ ticker:u.ticker, name:catalogue.value.find(i => i.ticker === u.ticker).label, currency:form.currency, asset_type:u.asset_type, sigma:u.vol/100, q:u.dividend/100, dividend_curve:parseOptimizerCurve(u.dividendCurve) })),
    correlation:assets.value.map((_,i) => assets.value.map((__,j) => i === j ? 1 : Number(correlations[`${Math.min(i,j)}-${Math.max(i,j)}`]))) },
    economics:Object.fromEntries(Object.entries(economics).map(([key,value]) => [key,value/100])), constraints:{...Object.fromEntries(Object.entries(constraints).map(([k,v]) => [k,v/100])), ...(form.objective === 'target_coupon' ? {target_coupon:targetCoupon.value/100,coupon_tolerance:couponTolerance.value/100} : {}), max_expected_capital_loss:activeFamily.value.risk_severity?optional(risk.capitalLoss,100):null, max_probability_loss:optional(risk.loss,100), min_probability_autocall:activeFamily.value.has_autocall?optional(risk.autocall,100):null, max_expected_maturity:optional(risk.life)}, search:{simulations:simulations.value,max_candidates:maxCandidates.value,max_seconds:maxSeconds.value,parallel_workers:parallelWorkers.value,strategy:'grid',seed:42} }
  Object.assign(body.constraints,solutionPayload(activeFamily.value,solutionMinimum.value,solutionMaximum.value))
  if (fundingMode.value === 'curve' && !body.market.funding_curve.length) throw Error('Renseignez la courbe de funding ou choisissez un spread plat.')
  body.market = withAutomaticReferences(body.market,automaticMarket.value)
  return body
}
function assetReference(ticker,key) { return automaticMarket.value?.provenance[`underlyings.${ticker}.${key}`] }
function referenceLabel(ticker,key) {
  const field=assetReference(ticker,key)
  return field?`${pct(field.reference_value)} · ${field.provider} · ${field.as_of}`:'indisponible — hypothèse à renseigner'
}
function resetAssetReference(asset,field,key) {
  const reference=assetReference(asset.ticker,key)
  if(!reference) return
  asset[field]=roundPricingInput(reference.reference_value*100); asset.manual[field]=false
  if(field==='dividend') asset.dividendCurve=[]
}
function assumptionLabel(asset,field){
  const original=parentResearch.value?.request.market.underlyings.find(u=>u.ticker===asset.ticker)
  const key=field==='vol'?'sigma':'q'
  if(asset.manual[field] && original && asset[field]===roundPricingInput(original[key]*100)) return 'hypothèse reprise du dossier'
  return asset.manual[field]?'surcharge manuelle':'référence arrondie utilisée'
}
function pairIdentity(pair) { return [assets.value[pair.i].ticker,assets.value[pair.j].ticker].sort().join('|') }
function resetCorrelations() {
  for(const pair of pairs.value) {
    correlations[pair.key]=roundPricingInput(automaticMarket.value.correlation[pair.i][pair.j])
    manualCorrelations[pairIdentity(pair)]=false
  }
}
watch(()=>JSON.stringify([form.strike_date,form.currency,assets.value.map(asset=>asset.ticker),demo.enabled,marketRefresh.value]),()=> {
  if(restoring || (!demo.enabled && frozenIdentity.value===marketIdentity())) return
  frozenIdentity.value=''
  clearTimeout(marketTimer); marketAborter?.abort()
  const generation=++marketGeneration
  automaticMarket.value=null; marketError.value=''
  for(const asset of assets.value) {
    if(!asset.manual.vol) asset.vol=null
    if(!asset.manual.dividend) asset.dividend=null
  }
  for(const pair of pairs.value) if(!manualCorrelations[pairIdentity(pair)]) correlations[pair.key]=null
  const tickers=assets.value.map(asset=>asset.ticker)
  if(demo.enabled || !form.strike_date || tickers.some(t=>!t)) {marketLoading.value=false;return}
  if(new Set(tickers).size!==tickers.length) {marketLoading.value=false;marketError.value='Sélectionnez des tickers distincts dans l’Optimizer.';return}
  marketLoading.value=true
  marketTimer=setTimeout(async()=> {
    const controller=new AbortController(); marketAborter=controller
    try {
      const reference=await optimizerJson('market-reference',{tickers,pricing_date:form.strike_date,currency:form.currency},controller.signal)
      if(generation!==marketGeneration) return
      automaticMarket.value=reference
      for(const asset of assets.value) applyAutomaticAsset(asset,reference.underlyings.find(item=>item.ticker===asset.ticker))
      for(const pair of pairs.value) if(!manualCorrelations[pairIdentity(pair)]) correlations[pair.key]=roundPricingInput(reference.correlation?.[pair.i]?.[pair.j] ?? null)
    } catch(e) { if(generation===marketGeneration && e.name!=='AbortError') marketError.value=e.message }
    finally {if(generation===marketGeneration) marketLoading.value=false}
  },250)
},{flush:'sync'})
async function estimate() { error.value=''; try { estimateResult.value = await optimizerJson('estimate-search',requestBody()) } catch(e) { error.value=e.message } }
async function start() {
  if(busy.value) return
  error.value=''
  try {
    const body=requestBody();busy.value=true
    estimateResult.value=await optimizerJson('estimate-search',body)
    if(!estimateResult.value.allowed) throw Error(estimateResult.value.reasons.join(' '))
    const command={optimization:body,title:title.value,intention:intention.value,parent_id:parentResearch.value?.id || null}
    const fingerprint=JSON.stringify([signature.value,title.value,intention.value,parentResearch.value?.id])
    if(commandSignature!==fingerprint){savedCommand={...command,command_key:crypto.randomUUID()};commandSignature=fingerprint}
    const saved=await researchApi('', 'POST',savedCommand)
    if(!disposed) await router.push(`/structuring/researches/${saved.id}`)
  } catch(e) {error.value=e.message}
  finally {busy.value=false}
}
function refreshMarket(){frozenIdentity.value='';marketRefresh.value++}
async function restore(id){
  const record=await researchApi(`/${id}`)
  if(disposed)return
  restoring=true;clearTimeout(marketTimer);marketAborter?.abort();marketGeneration++
  try {
    const family=payoffMode(supportedFamilies.value.find(item=>item.product_family===record.request.product_family),record.request.objective)
    if(!family || family.objective!==record.request.objective) throw Error('Le script ou l’objectif de cette recherche n’est plus pris en charge.')
    const state=researchFormState(record,family)
    resumeWarning.value=family.script_hash!==record.context.payoff.script_hash?'Le script actuel diffère de celui du dossier d’origine. Le nouveau calcul utilisera cette version ; les anciens prix conservent leur script.':''
    Object.assign(form,state.form);assets.value=state.assets;updateRanges(state.ranges);updateSettings(state.settings)
    observations.value=state.observations;Object.assign(constraints,state.constraints);Object.assign(economics,state.economics);Object.assign(risk,state.risk)
    solutionMinimum.value=state.solutionMinimum;solutionMaximum.value=state.solutionMaximum
    targetCoupon.value=state.targetCoupon;couponTolerance.value=state.couponTolerance
    rate.value=state.rate;yieldNodes.value=state.yieldNodes;fundingNodes.value=state.fundingNodes;fundingMode.value=state.fundingMode;fundingSpread.value=state.fundingSpread
    replaceFields(correlations,state.correlations);replaceFields(manualCorrelations,state.manualCorrelations)
    simulations.value=state.search.simulations;maxCandidates.value=state.search.max_candidates;maxSeconds.value=state.search.max_seconds;parallelWorkers.value=state.search.parallel_workers
    automaticMarket.value=state.automaticMarket;marketLoading.value=false;marketError.value='';frozenIdentity.value=marketIdentity()
    title.value=record.title;intention.value=record.intention;parentResearch.value=record
  } finally {restoring=false}
}
watch(signature,()=>{estimateResult.value=null})
onMounted(async()=>{try {
  const [caps]=await Promise.all([optimizerJson('capabilities'),ensureUnderlyings()]);capability.value=caps
  if(disposed)return
  if(!catalogue.value.length) error.value='Catalogue indisponible. Vérifiez les sous-jacents dans Administration.'
  if(route?.query.from) {
    await restore(route.query.from)
    const requested=Number(route.query.simulations)
    if(Number.isInteger(requested) && requested>=1000 && requested<=20000 && requested%1000===0)simulations.value=requested
  }
} catch(e){error.value=e.message} finally{loading.value=false} })
onBeforeUnmount(()=>{disposed=true;clearTimeout(marketTimer);marketGeneration++;marketAborter?.abort()})
</script>

<style scoped>
.optimizer { font-size:13px; display:flex; flex-direction:column; flex:1; min-height:0; }
.page-header,.scope-note { flex-shrink:0; }
.request-form { flex:1; min-height:0; overflow:auto; overscroll-behavior:contain; }
.label-title { display:flex; align-items:center; gap:5px; }
.optimizer-panels { display:grid; grid-template-columns:minmax(0,1fr); gap:16px; align-items:start; }
.optimizer-panels > .card { min-width:0; max-height:72vh; overflow:auto; overscroll-behavior:contain; }
.asset-inputs { display:grid; grid-template-columns:minmax(80px,.85fr) repeat(2,minmax(0,1fr)); gap:8px; }
@media(min-width:1200px) { .optimizer-panels { grid-template-columns:repeat(3,minmax(0,1fr)); } }
@media(min-width:768px) and (max-width:1199px) { .optimizer-panels { grid-template-columns:repeat(2,minmax(0,1fr)); } }

label { display: flex; flex-direction: column; gap: 5px; font-size: 12px; min-width:0; }
.optimizer :deep(.input),.select { width:100%; min-width:0; }
.grid > label { justify-content:space-between; }
.optimizer :deep(input[type="number"]) { font-variant-numeric:tabular-nums; }
.section-title { font-size:14px; font-weight:700; }
.scope-note { background:#f5f7fa; border-left:3px solid #94a3b8; padding:10px 12px; font-size:12px; color:#475569; }
.alert-error { background:#fff1f2; color:#9f1239; padding:12px; border-radius:6px; }
.asset-row { border-top:1px solid #e2e8f0; padding-top:10px; }
.range-head { display:grid; grid-template-columns:1.4fr repeat(3,1fr); align-items:center; gap:6px; font-size:11px; }
.check-label { flex-direction:row; align-items:center; }
.search-summary { display:flex; flex-direction:column; padding:14px; background:#eff6ff; color:#1e3a8a; gap:5px; }
.search-summary strong { font-size:20px; }
</style>
