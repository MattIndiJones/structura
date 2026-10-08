<template>
  <main class="results-page">
    <header class="page-header shrink-0"><div><RouterLink to="/structuring/researches" class="text-xs">← Recherches & pricings</RouterLink><h1 class="page-title mt-1">{{ record?.title || 'Résultats de la recherche' }}</h1><p v-if="record" class="text-xs text-slate-500">{{ researchStatuses[record.status] }} · marché du {{ record.pricing_date }} · créé le {{ new Date(record.created_at).toLocaleString('fr-FR') }}</p></div><div v-if="record" class="flex flex-wrap gap-2"><RouterLink :to="{path:'/structuring/optimizer',query:{from:record.id}}" class="btn-secondary btn-sm">Modifier / nouveau calcul</RouterLink><button class="btn-secondary btn-sm" @click="downloadResearch(record)">Exporter le dossier</button><button v-if="record.status==='RUNNING'" class="btn-secondary btn-sm" :disabled="stopping" @click="cancel">{{ stopping?'Arrêt demandé…':'Arrêter le calcul' }}</button></div></header>
    <p v-if="error" class="alert-error" role="alert">{{ error }}</p>
    <div class="results-workspace"><p v-if="demo.enabled" class="text-sm">Résultats masqués en mode Démo.</p><OptimizerResearchResults v-else-if="record" :key="record.id" :record="record" @refine-precision="refinePrecision" /><p v-else-if="!error" class="text-sm">Chargement du dossier…</p></div>
  </main>
</template>
<script setup>
import { onBeforeUnmount,ref,watch } from 'vue'
import { RouterLink,useRoute,useRouter } from 'vue-router'
import { useDemoModeStore } from '../stores/demoMode.js'
import OptimizerResearchResults from '../components/OptimizerResearchResults.vue'
import { researchApi,researchStatuses,downloadResearch } from '../utils/optimizerResearch.js'
const route=useRoute(),router=useRouter(),demo=useDemoModeStore(),record=ref(null),error=ref(''),stopping=ref(false)
let timer,controller,generation=0
async function load(id,version){
  if(demo.enabled)return
  controller=new AbortController()
  try {const data=await researchApi(`/${id}`,'GET',undefined,controller.signal);if(version!==generation)return;record.value=data;error.value='';if(data.status==='RUNNING')timer=setTimeout(()=>load(id,version),2000)}
  catch(e){if(e.name!=='AbortError' && version===generation){error.value=e.message;if(record.value?.status==='RUNNING')timer=setTimeout(()=>load(id,version),5000)}}
}
watch(()=>[route.params.researchId,demo.enabled],([id])=>{clearTimeout(timer);controller?.abort();record.value=null;stopping.value=false;load(id,++generation)},{immediate:true})
function refinePrecision(simulations){router.push({path:'/structuring/optimizer',query:{from:record.value.id,simulations:String(simulations)}})}
async function cancel(){stopping.value=true;try{await researchApi(`/${record.value.id}/cancel`,'POST',{});}catch(e){error.value=e.message;stopping.value=false}}
onBeforeUnmount(()=>{generation++;clearTimeout(timer);controller?.abort()})
</script>
<style scoped>
.results-page { display:flex; flex-direction:column; flex:1; min-height:0; min-width:0; width:100%; padding:18px 24px; gap:12px; }
.results-workspace { flex:1; min-height:0; overflow-y:auto; overflow-x:hidden; overscroll-behavior:contain; padding-bottom:12px; }
.alert-error { background:#fff1f2; color:#9f1239; padding:12px; border-radius:6px; }
@media(max-width:700px){.results-page{padding:12px;}.page-header{flex-wrap:wrap;gap:10px;}}
</style>
