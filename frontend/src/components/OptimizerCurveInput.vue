<template>
  <div class="curve-input mt-2">
    <p class="text-xs font-semibold">{{ label }}</p>
    <p v-if="!modelValue.length" class="text-xs text-slate-500 mt-1">{{ emptyLabel }}</p>
    <table v-else class="mt-2 w-full text-xs">
      <thead><tr><th>Maturité (années)</th><th>{{ rateLabel }}</th><th></th></tr></thead>
      <tbody><tr v-for="(node,index) in modelValue" :key="index">
        <td><input class="input" type="number" min="0.000001" max="30" :step="annual ? 1 : .25" :value="node[0]" required :aria-label="`${label}, nœud ${index+1}, maturité`" @input="edit(index,0,$event.target.value)" /></td>
        <td><OptimizerNumberInput :min="minimum" :max="maximum" :model-value="node[1]" required :aria-label="`${label}, nœud ${index+1}, taux en pourcent`" @update:model-value="edit(index,1,$event)" /></td>
        <td><button type="button" class="btn-ghost btn-sm" :aria-label="`Retirer ${label}, nœud ${index+1}`" @click="remove(index)">Retirer</button></td>
      </tr></tbody>
    </table>
    <button type="button" class="btn-secondary btn-sm mt-2" :disabled="modelValue.length >= maxNodes" @click="add">Ajouter un nœud</button>
  </div>
</template>

<script setup>
import OptimizerNumberInput from './OptimizerNumberInput.vue'
import { roundPricingInput } from '../utils/optimizerMarket.js'
const props = defineProps({
  modelValue:{type:Array,required:true},label:{type:String,required:true},
  rateLabel:{type:String,default:'Taux (%)'},emptyLabel:{type:String,default:'Courbe inactive : niveau plat utilisé.'},
  annual:Boolean,minimum:{type:Number,default:-10},maximum:{type:Number,default:30},
  maxNodes:{type:Number,default:30},initialRate:{type:Number,default:0},
})
const emit = defineEmits(['update:modelValue'])
function edit(index,column,value) {
  const rows=props.modelValue.map(row=>[...row])
  rows[index][column]=value === '' ? null : Number(value)
  emit('update:modelValue',rows)
}
function remove(index) { emit('update:modelValue',props.modelValue.filter((_,i)=>i!==index).map(row=>[...row])) }
function add() {
  const last=props.modelValue.at(-1)
  emit('update:modelValue',[...props.modelValue.map(row=>[...row]),[last ? Number(last[0])+1 : 1,roundPricingInput(last?.[1] ?? props.initialRate)]])
}
</script>

<style scoped>
th { text-align:left; color:#64748b; font-weight:500; }
td,th { padding:4px; }
:deep(.input) { width:100%; min-width:0; }
</style>
