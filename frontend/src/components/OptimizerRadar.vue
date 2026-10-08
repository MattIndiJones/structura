<template>
  <div><p class="text-xs text-slate-500">Échelles communes figées par la demande ; lecture des compromis, sans score global. Deux à quatre structures. La durée courte et le rappel fréquent ne sont pas des préférences universelles.</p>
    <p v-if="candidates.length<2 || axes.length<3" class="text-sm mt-3">Sélectionnez au moins deux structures avec trois métriques comparables pour afficher le radar.</p>
    <template v-else><p v-if="candidates.length>4" class="text-xs mt-2">Les quatre premières structures sélectionnées sont représentées.</p><div class="radar-chart"><canvas ref="canvas" role="img" aria-label="Radar comparatif des structures sélectionnées" /></div><div class="scales text-xs"><div v-for="axis in axes" :key="axis.key"><b>{{ axis.label }}</b> : {{ raw(axis.min,axis) }} à {{ raw(axis.max,axis) }} ; {{ axis.reverse?'valeur faible vers l’extérieur':'valeur élevée vers l’extérieur' }}.</div></div><p class="text-xs mt-2">Une valeur hors échelle est ramenée au bord du radar ; sa valeur exacte reste affichée au survol et dans le tableau.</p></template>
  </div>
</template>
<script setup>
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import Chart from 'chart.js/auto'
import { radarAxes,radarScore } from '../utils/optimizerRadar.js'
import { diagnosticStatus } from '../utils/optimizerDiagnostics.js'
import { percent } from '../utils/optimizerResearch.js'
const props=defineProps({result:Object,candidates:{type:Array,required:true}})
const canvas=ref(null),shown=computed(()=>props.candidates.slice(0,4)),axes=computed(()=>radarAxes(props.result,shown.value))
let chart
const raw=(value,axis)=>axis.unit==='pct'?percent(value):`${Number(value).toLocaleString('fr-FR',{maximumFractionDigits:2})} ans`
async function draw() {
  await nextTick();chart?.destroy();chart=null
  if(!canvas.value || shown.value.length<2 || axes.value.length<3)return
  const colors={good:['#059669','#047857','#34d399','#064e3b'],bad:['#e11d48','#9f1239','#fb7185','#881337'],pending:['#d97706','#92400e','#f59e0b','#b45309']}
  chart=new Chart(canvas.value,{type:'radar',data:{labels:axes.value.map(a=>a.label),datasets:shown.value.map((c,i)=>{
    const color=colors[diagnosticStatus(c).tone][i]
    return {label:`${c.candidate_id} · ${diagnosticStatus(c).label}`,data:axes.value.map(a=>radarScore(c[a.key],a)),borderColor:color,backgroundColor:`${color}16`,pointBackgroundColor:color,borderWidth:2}
  })},options:{responsive:true,maintainAspectRatio:false,animation:false,scales:{r:{min:0,max:100,ticks:{display:false}}},plugins:{tooltip:{callbacks:{label:ctx=>`${shown.value[ctx.datasetIndex].candidate_id} : ${raw(shown.value[ctx.datasetIndex][axes.value[ctx.dataIndex].key],axes.value[ctx.dataIndex])}`}}}}})
}
watch([()=>props.result,()=>props.candidates],draw,{deep:true,immediate:true})
onBeforeUnmount(()=>chart?.destroy())
</script>
<style scoped>
.radar-chart { height:340px; margin-top:12px; }
.scales { color:#475569; display:grid; gap:6px; }
</style>
