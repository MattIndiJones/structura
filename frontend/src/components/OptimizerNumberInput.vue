<template>
  <input class="input" type="number" step="0.01" :value="focused ? draft : formatted"
    @focus="focus" @input="edit" @blur="focused=false" />
</template>

<script setup>
import { computed, ref } from 'vue'
import { roundPricingInput } from '../utils/optimizerMarket.js'

const props=defineProps({modelValue:[Number,String]})
const emit=defineEmits(['update:modelValue','input'])
const focused=ref(false), draft=ref('')
const formatted=computed(()=>props.modelValue == null || props.modelValue === '' ? '' : Number(props.modelValue).toFixed(2))
function focus(event) { focused.value=true; draft.value=event.target.value }
function edit(event) {
  draft.value=event.target.value
  const value=roundPricingInput(draft.value)
  // Keep incomplete decimal entry editable; round extra digits immediately.
  if(draft.value.split('.')[1]?.length>2) {
    draft.value=Number(value).toFixed(2)
    event.target.value=draft.value
  }
  emit('update:modelValue',value)
  emit('input',event)
}
</script>
