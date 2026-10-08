<template>
  <button class="btn-secondary text-xs shrink-0" :disabled="disabled" @click="show">Exemples préremplis…</button>
  <BaseModal v-model="open" title="Charger un exemple prérempli" max-width="600px">
    <p class="text-xs text-slate-500 mb-3">Le script, les paramètres et les dates seront remplacés. Le panier et ses hypothèses de marché sont conservés.</p>
    <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
      <label class="label">Exemple<select v-model="selectedKey" class="select">
        <optgroup v-for="group in groups" :key="group.key" :label="group.label">
          <option v-for="p in group.items" :value="p.key" :key="p.key">{{ p.label }}</option>
        </optgroup>
      </select></label>
      <label class="label">Date de départ demandée<input type="date" class="input" v-model="date" /></label>
    </div>
    <p class="text-xs text-slate-500 mt-3">{{ selected?.description }}</p>
    <p class="text-xs text-slate-500 mt-2">{{ currency }} · observations ajustées au jour ouvré suivant · règlement J+3 ouvrés. Termes illustratifs, modifiables dans Economics.</p>
    <p v-if="preparing" class="text-xs text-slate-500 mt-3">Préparation des dates…</p>
    <AlertMessage v-if="error" kind="error" class="mt-3">{{ error }}</AlertMessage>
    <div v-if="plan" class="mt-3 text-xs space-y-3">
      <dl class="grid grid-cols-2 gap-2">
        <dt>StartDate / strike</dt><dd>{{ plan.strikeDate }}{{ plan.strikeDate!==date ? ' (date ajustée)' : '' }}</dd>
        <dt>Date de valeur</dt><dd>{{ plan.strikeDate }}</dd>
        <dt>Première observation</dt><dd>{{ plan.observations[0] }}</dd>
        <dt>Maturité</dt><dd>{{ plan.maturityDate }}</dd>
        <dt>Paiement final</dt><dd>{{ plan.paymentDate }}</dd>
        <template v-for="p in plan.validation.data.params" :key="p.name"><dt>{{ p.name }}</dt><dd>{{ formatValue(plan.params[p.name],p.is_pct) }}</dd></template>
      </dl>
      <details><summary class="cursor-pointer text-slate-500">Voir les {{ plan.observations.length }} observations et le script</summary>
        <p class="mt-2 leading-relaxed">{{ plan.observations.join(' · ') }}</p>
        <pre class="mt-2 max-h-48 overflow-auto text-[10px]">{{ plan.model.script }}</pre>
      </details>
    </div>
    <template #footer><button class="btn-secondary" :disabled="applying" @click="open=false">Annuler</button><button class="btn-primary" :disabled="!plan || preparing || applying" @click="apply">{{ applying ? 'Chargement…' : 'Charger l’exemple' }}</button></template>
  </BaseModal>
</template>
<script setup>
import { computed, ref, watch } from 'vue'
import BaseModal from './ui/BaseModal.vue'
import AlertMessage from './ui/AlertMessage.vue'
import { PRODUCT_MODEL_FAMILIES } from '../utils/productModels.js'
import { payscriptPresets, preparePreset, localTodayIso } from '../utils/payscriptPresets.js'
const props=defineProps({currency:{type:String,default:'EUR'},startDate:String,disabled:Boolean,underlyingCount:{type:Number,default:1},onApply:{type:Function,required:true}})
const open=ref(false), selectedKey=ref('autocall_3y'), date=ref(''), plan=ref(null), error=ref(''), preparing=ref(false), applying=ref(false)
const selected=computed(()=>payscriptPresets.find(p=>p.key===selectedKey.value))
const groups=PRODUCT_MODEL_FAMILIES.map(g=>({...g,items:payscriptPresets.filter(p=>p.group===g.key)})).filter(g=>g.items.length)
function formatValue(value,pct) { return (Array.isArray(value)?value.map(v=>`${v}${pct?' %':''}`).join(' / '):`${value}${pct?' %':''}`) }
function show() { date.value=props.startDate||localTodayIso();open.value=true }
watch(()=>[open.value,selectedKey.value,date.value,props.currency,props.underlyingCount],async (_,__,onCleanup)=>{
  let cancelled=false;onCleanup(()=>{cancelled=true})
  plan.value=null;error.value=''
  if(!open.value) return
  preparing.value=true
  try {
    const next=await preparePreset(selectedKey.value,{startDate:date.value,currency:props.currency})
    if(props.underlyingCount<next.model.underlyings.min||props.underlyingCount>next.model.underlyings.max)
      throw Error(`Cet exemple accepte ${next.model.underlyings.min} à ${next.model.underlyings.max} sous-jacents. Ajustez le panier avant de le charger.`)
    if(!cancelled) plan.value=next
  } catch(e) { if(!cancelled) error.value=e.message }
  finally { if(!cancelled) preparing.value=false }
})
async function apply() {
  if(!plan.value||props.disabled) return
  applying.value=true;error.value=''
  try { await props.onApply(plan.value);open.value=false }
  catch(e) { error.value=e.message }
  finally { applying.value=false }
}
</script>
