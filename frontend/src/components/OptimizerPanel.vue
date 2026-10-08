<template>
  <details class="card optimizer-panel" :open="open"><summary><span>{{ title }}</span><HelpTip v-if="help" :text="help" /><span class="panel-toggle" aria-hidden="true">⌄</span></summary><div class="panel-body" :class="{'panel-body-scroll':scrollable}" :style="scrollable?{maxHeight:height}:undefined"><slot /></div></details>
</template>
<script setup>
import HelpTip from './HelpTip.vue'
defineProps({title:{type:String,required:true},help:String,open:Boolean,height:{type:String,default:'52vh'},scrollable:{type:Boolean,default:true}})
</script>
<style scoped>
.optimizer-panel { padding:0; min-width:0; }
summary { display:flex; align-items:center; gap:8px; padding:14px 16px; cursor:pointer; font-size:13px; font-weight:600; list-style:none; }
summary::-webkit-details-marker { display:none; }
.panel-toggle { margin-left:auto; transition:transform .15s; }
details[open] .panel-toggle { transform:rotate(180deg); }
.panel-body { padding:0 16px 16px; min-width:0; }
.panel-body-scroll { overflow:auto; overscroll-behavior:contain; }
</style>
