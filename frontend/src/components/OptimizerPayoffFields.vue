<template>
  <div v-if="family" class="flex flex-col gap-3">
    <p class="text-xs text-slate-500">{{ family.coupon_rule }}</p>
    <div class="range-row range-head"><span>Paramètre / mode <HelpTip :text="helpFor('parameter_mode')" /></span><span>Valeur / min.</span><span>Max.</span><span>Pas</span></div>
    <div v-for="field in family.range_fields" :key="field.key" class="range-row" :data-parameter="field.script_param || field.key">
      <span class="parameter-label">{{ field.label }} <HelpTip :text="helpFor(field.key)" /></span>
      <select class="select range-mode" :aria-label="`${field.label} mode`" :value="isFixed(field.key)?'fixed':'explore'" @change="setMode(field,$event.target.value)"><option value="fixed">Fixe</option><option value="explore">À explorer</option></select>
      <input v-for="part in ['minimum','maximum','step']" :key="part" class="input" type="number" required
        :aria-label="`${field.label} ${part}`" :value="ranges[field.key]?.[part]"
        :min="part==='step'?field.step*factor(field):field.minimum*factor(field)" :max="field.maximum*factor(field)" :step="field.step*factor(field)"
        :disabled="isFixed(field.key) && part!=='minimum'"
        @input="updateRange(field.key,part,$event.target.value)" />
      <p class="values">{{ axisValues(field.key) }}</p>
    </div>
    <div v-for="field in family.fixed_fields" :key="field.key">
      <label class="text-xs flex flex-col gap-1"><span>{{ field.label }} <HelpTip :text="helpFor(field.key)" /></span><input class="input" type="number" required :aria-label="field.label"
        :value="settings[field.key]" :min="field.minimum*factor(field)" :max="field.maximum*factor(field)" :step="field.step*factor(field)"
        @input="$emit('update:settings',{...settings,[field.key]:numeric($event.target.value)})" /></label>
    </div>
    <p v-if="family.script_parameters.some(parameter=>parameter.kind==='array')" class="text-xs text-slate-500">Le seuil baisse dès le rang indiqué, puis à chaque constatation jusqu’au plancher. Une valeur M_AC_BAR est générée par date.</p>
    <fieldset v-if="family.has_autocall"><legend class="text-xs font-semibold mb-2">Fréquences de constatation <HelpTip :text="helpFor('observation_months')" /></legend><div class="flex flex-wrap gap-3">
      <label v-for="value in family.observation_months" :key="value" class="text-xs flex items-center gap-1"><input type="checkbox" :value="value" :checked="observations.includes(value)"
        @change="$emit('update:observations',$event.target.checked?[...observations,value]:observations.filter(item=>item!==value))" />{{ frequencyLabels[value] }}</label>
    </div></fieldset>
    <p v-else class="text-xs text-slate-500">Constatation unique à maturité ; aucun seuil de rappel ni fréquence à renseigner.</p>
    <details class="text-xs"><summary>Script utilisé et paramètres requis</summary><table class="mt-2"><thead><tr><th>Paramètre</th><th>Type / rôle</th></tr></thead><tbody>
      <tr v-for="parameter in family.script_parameters" :key="parameter.name"><td>{{ parameter.name }}{{ parameter.required?' · requis':'' }}</td><td>{{ parameter.kind==='array'?'Série par constatation':'Pourcentage' }} · {{ parameter.role==='solved'?'résolu par l’Optimizer':parameter.role==='fixed'?'valeur imposée':'espace de recherche' }}</td></tr>
    </tbody></table><pre class="mt-2 whitespace-pre-wrap overflow-auto">{{ family.script }}</pre></details>
  </div>
</template>

<script setup>
import { reactive } from 'vue'
import HelpTip from './HelpTip.vue'
import { helpFor } from '../utils/optimizerResearch.js'
import { rangeCount } from '../utils/productOptimizer.js'
const props=defineProps({family:Object,ranges:{type:Object,required:true},settings:{type:Object,required:true},observations:{type:Array,required:true}})
const emit=defineEmits(['update:ranges','update:settings','update:observations'])
const factor=field=>field.unit==='fraction'?100:1
const numeric=value=>value.trim()===''?null:Number(value)
const frequencyLabels={1:'Mensuelle',3:'Trimestrielle',6:'Semestrielle',12:'Annuelle'}
const modes=reactive({})
const isFixed=key=>modes[key] ? modes[key]==='fixed' : props.ranges[key]?.minimum===props.ranges[key]?.maximum
function updateRange(key,part,value) {
  const next={...props.ranges[key],[part]:numeric(value)}
  if(isFixed(key)) next.maximum=next.minimum
  emit('update:ranges',{...props.ranges,[key]:next})
}
function setMode(field,mode) {
  modes[field.key]=mode
  const next={...props.ranges[field.key]}
  if(mode==='fixed') next.maximum=next.minimum
  emit('update:ranges',{...props.ranges,[field.key]:next})
}
function axisValues(key) {
  const range=props.ranges[key], count=rangeCount(range)
  if(count==null) return 'Plage à compléter'
  const values=Array.from({length:Math.min(count,12)},(_,i)=>Number((range.minimum+i*range.step).toFixed(8)).toLocaleString('fr-FR'))
  return `${count} valeur(s) : ${values.join(' · ')}${count>12?' …':''}`
}
</script>

<style scoped>
.range-row { display:grid; grid-template-columns:minmax(110px,1.4fr) repeat(3,minmax(0,1fr)); gap:6px; align-items:center; font-size:11px; }
.parameter-label { grid-column:1 / -1; }
.range-mode,.input { grid-row:2; }
.range-mode { width:100%; min-width:0; }
.input { width:100%; min-width:0; }
.values { grid-column:1 / -1; color:#64748b; overflow-wrap:anywhere; }
th,td { padding:5px; text-align:left; }
pre { max-height:280px; background:#f8fafc; padding:8px; }
@media(max-width:480px) { .range-row { gap:4px; grid-template-columns:minmax(100px,1.2fr) repeat(3,minmax(0,1fr)); } .range-row .input { padding:6px 4px; font-size:11px; } }
</style>
