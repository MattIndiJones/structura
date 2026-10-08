<template>
  <section class="pricing-results">
    <div class="flex flex-wrap items-end justify-between gap-3">
      <div><h2 class="text-sm font-bold">Pricings calculés — meilleures structures selon votre objectif</h2>
        <p class="text-xs text-slate-500 mt-1">{{ candidates.length }} structure(s) pricée(s), y compris celles hors conditions. Classement économique indicatif ; les structures rouges restent non admissibles.</p></div>
      <div class="flex gap-2"><label class="text-xs">Tri<select class="select" v-model="sort"><option value="objective">Objectif de la recherche</option><option value="price">Proximité du prix cible</option><option value="risk">Probabilité de perte Q</option></select></label>
        <label class="text-xs">Par page<select class="select" v-model.number="limit"><option :value="10">10 structures</option><option :value="25">25 structures</option></select></label></div>
    </div>
    <p class="text-xs mt-3"><span class="legend good">Vert : confirmée</span> <span class="legend bad">Rouge : hors conditions ou contrôle non concluant</span> <span class="legend pending">Ambre : validation manquante</span></p>
    <p v-if="target!=null" class="text-xs mt-2">Cible payoff : {{ pct(target) }} · tolérance {{ pct(result.request.constraints.price_tolerance) }} · les prix et contrôles proviennent des hypothèses de cette recherche.</p>
    <div v-if="candidates.length" class="pricing-table mt-3">
      <table><thead><tr><th>Comparer</th><th>Ordre</th><th>Structure / statut</th><th v-for="metric in metrics" :key="metric.key">{{ metric.label }} <HelpTip :text="helpFor(metric.key)" /></th><th>Intervalle de contrôle / écart cible <HelpTip :text="helpFor('interval')" /></th><th>Ce qui bloque / quoi modifier</th></tr></thead>
        <tbody><tr v-for="(candidate,index) in visible" :key="candidate.candidate_id" :class="status(candidate).tone">
          <td><input type="checkbox" :checked="selected.includes(candidate.candidate_id)" :disabled="selected.length>=5 && !selected.includes(candidate.candidate_id)" :aria-label="`Comparer ${candidate.candidate_id}`" @change="toggle(candidate.candidate_id,$event.target.checked)" /></td>
          <td>{{ (page-1)*limit+index+1 }}</td><td class="diagnostic-cell"><b>{{ candidate.candidate_id }}</b><span class="block mt-1">{{ status(candidate).label }}</span><small class="block mt-1">{{ candidate.validation?.runs?.length?'Dernier calcul de validation indépendant':'Calcul d’exploration' }}</small></td>
          <td v-for="metric in metrics" :key="metric.key">{{ display(candidate,metric) }}</td>
          <td><span>{{ candidate.price_ic95?.map(pct).join(' – ') || 'Indisponible' }}</span><small v-if="target!=null" class="block mt-1">Écart central : {{ signed(candidate.fair_value-target) }} points</small></td>
          <td class="diagnostic-cell findings"><details><summary>{{ status(candidate).tone==='good'?'Contrôles respectés':status(candidate).tone==='pending'?'Voir le statut de validation':'Voir les blocages et réglages' }}</summary><div class="finding-scroll"><div v-for="(finding,i) in findings(candidate,result)" :key="i" class="finding"><p>{{ finding.reason }}</p><p class="mt-1 font-semibold">{{ finding.action }}</p></div></div></details></td>
        </tr></tbody>
      </table>
    </div>
    <p v-else class="text-sm mt-3">Aucun prix de structure complète disponible. Les causes de non-calcul figurent ci-dessous.</p>
    <div v-if="candidates.length" class="flex flex-wrap justify-between gap-2 mt-3"><p class="text-xs">{{ (page-1)*limit+1 }}–{{ Math.min(page*limit,candidates.length) }} / {{ candidates.length }} · page {{ page }} / {{ pages }}. Les contraintes restent celles de la demande initiale.</p><div class="flex gap-2"><button type="button" class="btn-secondary btn-sm" :disabled="page<=1" @click="page--">Précédente</button><button type="button" class="btn-secondary btn-sm" :disabled="page>=pages" @click="page++">Suivante</button><button type="button" class="btn-secondary btn-sm" :disabled="selected.length<2" @click="$emit('compare')">Comparer {{ selected.length }} structures (2 à 5)</button></div></div>
    <OptimizerPanel :scrollable="false" v-if="unpriced.length" class="mt-4" :title="`Structures non pricées / erreurs (${unpriced.length})`" :help="helpFor('status')" height="35vh"><details v-for="candidate in unpriced" :key="candidate.candidate_id" class="unpriced bad mt-2"><summary><b>{{ candidate.candidate_id }} · {{ status(candidate).label }}</b></summary><div class="finding-scroll"><div v-for="(finding,i) in findings(candidate,result)" :key="i" class="mt-1 text-xs"><p>{{ finding.reason }}</p><p class="font-semibold mt-1">{{ finding.action }}</p></div></div></details></OptimizerPanel>
  </section>
</template>

<script setup>
import { computed, ref,watch } from 'vue'
import HelpTip from './HelpTip.vue'
import OptimizerPanel from './OptimizerPanel.vue'
import { helpFor } from '../utils/optimizerResearch.js'
import { diagnosticCandidates, diagnosticStatus, diagnosticFindings, pricingTarget } from '../utils/optimizerDiagnostics.js'
const props=defineProps({result:{type:Object,required:true},family:Object,metrics:{type:Array,required:true},selected:{type:Array,required:true},running:Boolean})
const emit=defineEmits(['update:selected','compare'])
const sort=ref('objective'),limit=ref(10),page=ref(1)
const candidates=computed(()=>diagnosticCandidates(props.result,props.family))
const unpriced=computed(()=>(props.result.candidates || []).filter(c=>!candidates.value.includes(c)))
const target=computed(()=>pricingTarget(props.result))
const ordered=computed(()=>{
  const rows=[...candidates.value]
  if(sort.value==='price' && target.value!=null) rows.sort((a,b)=>Math.abs(a.fair_value-target.value)-Math.abs(b.fair_value-target.value))
  if(sort.value==='risk') rows.sort((a,b)=>(a.probability_loss ?? Infinity)-(b.probability_loss ?? Infinity))
  return rows
})
const pages=computed(()=>Math.max(1,Math.ceil(ordered.value.length/limit.value)))
const visible=computed(()=>ordered.value.slice((page.value-1)*limit.value,page.value*limit.value))
watch([sort,limit],()=>{page.value=1})
watch(pages,count=>{if(page.value>count)page.value=count})
const status=diagnosticStatus,findings=(candidate,result)=>diagnosticFindings(candidate,result,{running:props.running})
const pct=value=>value==null?'—':`${(value*100).toLocaleString('fr-FR',{minimumFractionDigits:2,maximumFractionDigits:2})} %`
const signed=value=>`${value>=0?'+':''}${(value*100).toLocaleString('fr-FR',{minimumFractionDigits:2,maximumFractionDigits:2})}`
function display(candidate,metric) {
  const value=candidate[metric.key]
  return value==null?'—':metric.unit==='pct'?pct(value):`${Number(value).toLocaleString('fr-FR',{maximumFractionDigits:2})} ${metric.unit==='months'?'mois':metric.unit==='multiple'?'×':'ans'}`
}
function toggle(id,checked) {emit('update:selected',checked?[...new Set([...props.selected,id])]:props.selected.filter(value=>value!==id))}
</script>

<style scoped>
label { display:flex; flex-direction:column; gap:4px; }
table { width:100%; border-collapse:collapse; font-size:12px; }
th,td { padding:10px; text-align:right; border-bottom:1px solid #cbd5e1; vertical-align:top; white-space:nowrap; }
.pricing-table { overflow-x:auto; }
thead th { position:sticky; top:0; background:#f8fafc; z-index:1; }
.finding-scroll { padding-top:8px; }
summary { cursor:pointer; font-size:12px; }
th { color:#475569; font-weight:600; }
th:nth-child(3),th:last-child,.diagnostic-cell { text-align:left; }
.diagnostic-cell { white-space:normal; min-width:180px; }
.findings { min-width:350px; max-width:450px; }
.finding + .finding { margin-top:12px; border-top:1px solid #cbd5e1; padding-top:8px; }
.good { background:#ecfdf5; color:#065f46; }
.bad { background:#fff1f2; color:#9f1239; }
.pending { background:#fffbeb; color:#92400e; }
.legend { display:inline-block; padding:4px 8px; border-radius:4px; margin:0 4px 4px 0; }
.unpriced { padding:12px; border-radius:6px; }
</style>
