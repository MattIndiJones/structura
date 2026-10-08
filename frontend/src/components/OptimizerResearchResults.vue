<template>
  <div class="research-results">
    <div v-if="result" class="stats"><div v-for="(label,key) in labels" :key="key"><b>{{ result.statistics?.[key] ?? 0 }}</b><span>{{ label }}</span></div></div>
    <p v-if="record.error" class="notice bad" role="alert">{{ record.error }}</p>
    <p v-if="record.status==='RUNNING'" class="notice">Calcul en cours · {{ record.progress.phase==='validation'?'validation indépendante':'exploration' }} · {{ record.progress.completed || 0 }} / {{ record.progress.total || '—' }}. Vous pouvez changer de page ; les résultats sont sauvegardés côté serveur.</p>
    <p v-else-if="record.status==='PARTIAL' || record.status==='INTERRUPTED'" class="notice">Couverture partielle. Les structures non évaluées et validations manquantes restent explicites.</p>
    <OptimizerPanel :scrollable="false" title="Résumé de la demande" class="mt-3" :help="helpFor('objective')" height="30vh"><p class="text-xs text-slate-500 mb-2">{{ family.coupon_rule }}</p><p class="text-sm">{{ record.summary }}</p><p v-if="record.intention" class="text-sm mt-2"><b>Intention :</b> {{ record.intention }}</p><div class="request-grid mt-3"><div v-for="field in family.range_fields" :key="field.key"><b>{{ field.label }}</b><p>{{ range(field) }}</p></div><div><b>Objectif</b><p>{{ family.objectives.find(o=>o.value===request.objective)?.label || request.objective }}</p></div><div><b>Marché</b><p>{{ record.pricing_date }} · {{ request.currency }} · {{ request.market.underlyings.map(u=>u.name || u.ticker).join(' / ') }}</p></div><div><b>Prix et coûts</b><p>Émission {{ pct(request.constraints.target_price) }} · frais {{ pct(request.economics.upfront_fees) }} · marge {{ pct(request.economics.structuring_margin) }}</p></div></div></OptimizerPanel>
    <nav class="tabs" aria-label="Vues des résultats"><button v-for="item in tabs" :key="item.key" type="button" :aria-pressed="tab===item.key" :class="{active:tab===item.key}" @click="tab=item.key">{{ item.label }}</button></nav>
    <template v-if="tab==='structures'">
      <div v-if="recommended" class="notice good"><b>{{ recommended.candidate_id }} · {{ family.solved_field.label }} {{ pct(recommended[family.solved_field.key]) }}</b><p class="text-xs mt-1">{{ result.explanation }} <HelpTip :text="helpFor('status')" /></p></div>
      <div v-if="result" class="outcome mt-3" :class="outcome.tone" role="status"><b>{{ outcome.title }}</b><p class="text-xs mt-2">{{ outcome.text }}</p><p v-if="outcome.example" class="text-xs mt-2">{{ outcome.example }}</p><div v-if="outcome.nextSimulations" class="flex items-center gap-3 flex-wrap mt-3"><button type="button" class="btn-secondary btn-sm" @click="$emit('refine-precision',outcome.nextSimulations)">Préparer un recalcul à {{ outcome.nextSimulations.toLocaleString('fr-FR') }} paires</button><p class="text-xs">Même demande et mêmes contraintes ; paramètres à vérifier avant lancement. Un nouveau calcul ne garantit pas une confirmation.</p></div></div>
      <OptimizerPanel :scrollable="false" v-if="result" title="Pricings et diagnostics" :open="true" :help="helpFor('status')" class="mt-3"><OptimizerPricingResults :result="result" :family="family" :metrics="tableMetrics" :running="record.status==='RUNNING'" :selected="selected" @update:selected="select" @compare="tab='comparison'" /></OptimizerPanel>
      <p v-else class="notice mt-3">Préparation du calcul ; les prix apparaîtront au fur et à mesure de leur sauvegarde.</p>
    </template>
    <template v-if="tab==='comparison'">
      <OptimizerPanel :scrollable="false" title="Radar des structures sélectionnées" :open="true" :help="helpFor('radar')" height="65vh"><OptimizerRadar :result="result" :candidates="compared" /></OptimizerPanel>
      <OptimizerPanel :scrollable="false" title="Comparaison détaillée" class="mt-3" :help="helpFor('status')"><div v-if="compared.length>=2" class="table-scroll"><table><thead><tr><th>Caractéristique</th><th v-for="c in compared" :key="c.candidate_id">{{ c.candidate_id }} · {{ status(c).label }}</th></tr></thead><tbody><tr v-for="metric in metrics" :key="metric.key"><th>{{ metric.label }} <HelpTip :text="helpFor(metric.key)" /></th><td v-for="c in compared" :key="c.candidate_id" :class="status(c).tone">{{ display(c,metric) }}</td></tr></tbody></table></div><p v-else class="text-sm">Sélectionnez deux à cinq structures dans l’onglet Structures.</p></OptimizerPanel>
      <OptimizerPanel :scrollable="false" title="Frontière des structures confirmées" class="mt-3" help="Structures confirmées uniquement. La frontière compare les deux critères affichés ; elle ne représente pas tous les risques." height="45vh"><p v-if="!confirmed.length" class="text-sm">Aucune structure confirmée pour tracer cette frontière.</p><template v-else><p class="text-xs">{{ family.frontier.y.label }} / {{ family.frontier.x.label }}</p><div class="frontier"><canvas ref="frontierCanvas" role="img" aria-label="Frontière des structures confirmées" /></div></template></OptimizerPanel>
    </template>
    <template v-if="tab==='market'">
      <OptimizerPanel :scrollable="false" title="Marché utilisé et références sources" :open="true" :help="helpFor('model')"><div class="table-scroll"><table><thead><tr><th>Champ</th><th>Référence</th><th>Utilisé</th><th>Source / date</th></tr></thead><tbody><tr v-for="(field,key) in snapshot.fields" :key="key"><td>{{ marketLabel(key) }} <HelpTip :text="helpFor(key.split('.').at(-1))" /></td><td>{{ marketValue(field.reference_value,key) }}</td><td>{{ marketValue(field.used_value,key) }} {{ field.overridden?'· modifiée':'' }} {{ field.active===false?'· inactive':'' }}</td><td>{{ field.provider || field.source }} · {{ field.as_of }}</td></tr></tbody></table></div></OptimizerPanel>
      <OptimizerPanel :scrollable="false" title="Calcul, validation et limites" class="mt-3" :help="helpFor('interval')"><p class="text-sm">GBM · {{ request.search.simulations }} paires · graine {{ request.search.seed }} · budget {{ request.search.max_seconds }} s · {{ request.search.parallel_workers }} processus demandés.</p><p v-if="result?.validation" class="text-sm mt-2">{{ result.validation.selected }} candidat(s) sélectionné(s) pour validation indépendante · {{ result.validation.passed }} confirmé(s).</p><ul class="text-xs mt-3"><li v-for="warning in result?.warnings || snapshot.warnings" :key="warning">{{ warning }}</li></ul><p v-if="result?.validation?.ranking_stability==='OVERLAPPING'" class="notice mt-3">Les intervalles du paramètre équitable se recouvrent : le classement reste incertain.</p><p class="text-xs mt-3">Probabilités Q, modèle GBM et hypothèses datées. Les prix archivés conservent leur marché ; une reprise avec de nouvelles hypothèses produit un nouveau calcul.</p></OptimizerPanel>
      <OptimizerPanel :scrollable="false" title="Script et paramètres sauvegardés" class="mt-3" :help="helpFor('product_family')" height="45vh"><p class="text-xs text-slate-500">Script {{ family.script_hash }} · marché {{ snapshot.hash }}.</p><pre class="saved-source mt-3">{{ family.script }}</pre><details class="mt-3"><summary>Demande structurée complète</summary><pre class="saved-source mt-2">{{ JSON.stringify(request,null,2) }}</pre></details></OptimizerPanel>
    </template>
  </div>
</template>
<script setup>
import { computed,nextTick,onBeforeUnmount,ref,watch } from 'vue'
import Chart from 'chart.js/auto'
import HelpTip from './HelpTip.vue'
import OptimizerPanel from './OptimizerPanel.vue'
import OptimizerPricingResults from './OptimizerPricingResults.vue'
import OptimizerRadar from './OptimizerRadar.vue'
import { diagnosticCandidates,diagnosticStatus } from '../utils/optimizerDiagnostics.js'
import { rankedCandidates } from '../utils/productOptimizer.js'
import { payoffMetrics } from '../utils/optimizerPayoff.js'
import { researchOutcome } from '../utils/optimizerOutcome.js'
import { percent,helpFor } from '../utils/optimizerResearch.js'
const props=defineProps({record:{type:Object,required:true}})
defineEmits(['refine-precision'])
const outcome=computed(()=>researchOutcome(props.record))
const result=computed(()=>props.record.result),request=computed(()=>props.record.request),family=computed(()=>props.record.context.payoff)
const snapshot=computed(()=>result.value?.market_snapshot || props.record.context.market_snapshot)
const tab=ref('structures'),selected=ref([]),frontierCanvas=ref(null)
const candidates=computed(()=>diagnosticCandidates(result.value,family.value)),confirmed=computed(()=>rankedCandidates(result.value))
const recommended=computed(()=>confirmed.value.find(c=>c.candidate_id===result.value?.recommended_id))
const compared=computed(()=>candidates.value.filter(c=>selected.value.includes(c.candidate_id)))
const metrics=computed(()=>[...payoffMetrics(family.value),{key:'fair_value',label:'Juste valeur',unit:'pct'},
  {key:'probability_loss',label:'Probabilité de perte Q',unit:'pct'},{key:'expected_maturity',label:'Durée moyenne Q',unit:'years'},
  ...(family.value.has_autocall?[{key:'probability_autocall',label:'Rappel anticipé Q',unit:'pct'},{key:'observation_months',label:'Fréquence',unit:'months'}]:[]),
  ...(family.value.coupon_analytics?[{key:'expected_coupon_paid',label:'Coupons payés Q — nominal',unit:'pct'},{key:'expected_coupon_unpaid',label:request.value.product_family==='phoenix_memoire'?'Mémoire non payée Q — nominal':'Coupons perdus Q — nominal',unit:'pct'}]:[]),
  ...(family.value.script_parameters.some(p=>p.kind==='array')?[{key:'autocall_schedule',label:'Seuils de rappel par date',unit:'schedule'}]:[]),
  ...(family.value.risk_severity?[{key:'probability_capital_loss',label:'Perte en capital — probabilité Q',unit:'pct'},{key:'expected_capital_loss',label:'Perte en capital moyenne Q',unit:'pct'},{key:'conditional_capital_loss',label:'Sévérité conditionnelle Q',unit:'pct'}]:[])])
const tableMetrics=computed(()=>metrics.value.filter(m=>!['autocall_schedule','expected_coupon_paid','expected_coupon_unpaid','probability_capital_loss','conditional_capital_loss'].includes(m.key)))
const labels={generated:'Générés',priced:'Pricés',valid:'Confirmés',rejected:'Rejetés',failed:'Échecs',not_evaluated:'Non évalués'}
const tabs=[{key:'structures',label:'Structures'},{key:'comparison',label:'Comparaison & graphiques'},{key:'market',label:'Marché & calcul'}]
const pct=percent,status=diagnosticStatus
function display(c,m) {const value=c[m.key];return value==null?'—':m.unit==='schedule'?value.map(pct).join(' → '):m.unit==='pct'?pct(value):`${Number(value).toLocaleString('fr-FR',{maximumFractionDigits:2})} ${m.unit==='months'?'mois':m.unit==='multiple'?'×':'ans'}`}
function range(field){const value=request.value.ranges[field.key],factor=field.unit==='fraction'?100:1;return `${Number((value.minimum*factor).toFixed(2))} à ${Number((value.maximum*factor).toFixed(2))} ; pas ${Number((value.step*factor).toFixed(2))}`}
function marketLabel(key){const names={sigma:'Volatilité GBM',q:'Dividende',rate:'Taux',yield_curve:'Courbe de taux',funding_spread:'Funding',funding_curve:'Courbe de funding',dividend_curve:'Courbe de dividendes',correlation:'Corrélations'};const field=key.split('.').at(-1);return key.startsWith('underlyings.')?`${key.slice(12,key.lastIndexOf('.'))} · ${names[field] || field}`:names[key] || key}
function marketValue(value,key){if(!Array.isArray(value))return pct(value);return key==='correlation'?value.map(row=>row.map(x=>Number(x).toFixed(2)).join(' / ')).join(' ; '):value.map(([t,x])=>`${t} ans : ${pct(x)}`).join(' ; ')}
let selectionEdited=false
function select(ids){selectionEdited=true;selected.value=ids}
watch(candidates,rows=>{if(!selectionEdited)selected.value=(confirmed.value.length>=2?confirmed.value:rows).slice(0,2).map(c=>c.candidate_id)},{immediate:true})
let chart
async function draw(){await nextTick();chart?.destroy();chart=null;if(!frontierCanvas.value || !confirmed.value.length)return;chart=new Chart(frontierCanvas.value,{type:'scatter',data:{datasets:[{label:'Structures confirmées',data:confirmed.value.map(c=>({x:c[family.value.frontier.x.key]*100,y:c[family.value.frontier.y.key]*100,id:c.candidate_id})),backgroundColor:'#059669'}]},options:{responsive:true,maintainAspectRatio:false,animation:false,scales:{x:{title:{display:true,text:family.value.frontier.x.label}},y:{title:{display:true,text:family.value.frontier.y.label}}}}})}
watch([tab,result],draw)
onBeforeUnmount(()=>chart?.destroy())
</script>
<style scoped>
.research-results { min-width:0; }
.stats { display:grid; grid-template-columns:repeat(6,minmax(0,1fr)); gap:10px; }
.stats > div { display:flex; flex-direction:column; padding:10px 14px; background:var(--surface); border:1px solid var(--border); border-radius:10px; }
.stats b { font-size:20px; }.stats span { font-size:11px; color:var(--muted); }
.tabs { display:flex; gap:8px; padding:14px 0; flex-wrap:wrap; position:sticky; top:0; z-index:2; background:var(--bg,#faf9f6); }
.tabs button { padding:8px 12px; border-radius:6px; font-size:12px; border:1px solid var(--border); background:var(--surface); }
.tabs .active { background:#1d4ed8; color:#fff; }
.outcome { padding:12px 16px; border-radius:6px; font-size:13px; }.notice { padding:12px 16px; border-radius:6px; background:#eff6ff; color:#1e3a8a; font-size:13px; }
.good { background:#ecfdf5; color:#065f46; }.bad { background:#fff1f2; color:#9f1239; }.pending { background:#fffbeb; color:#92400e; }
.request-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:12px; font-size:12px; }
.table-scroll { overflow-x:auto; }.saved-source { font-size:11px; background:var(--bg); padding:12px; white-space:pre-wrap; overflow-wrap:anywhere; }.frontier { height:270px; }
table { width:100%; border-collapse:collapse; font-size:12px; }th,td { padding:10px; text-align:left; border-bottom:1px solid var(--border); }thead th { position:sticky; top:0; background:var(--surface); }
@media(max-width:700px){.stats{grid-template-columns:repeat(3,minmax(0,1fr));}.request-grid{grid-template-columns:1fr;}}
</style>
