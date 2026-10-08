<template>
  <main class="research-library">
    <header class="page-header"><div><h1 class="page-title">Recherches & pricings</h1><p class="page-subtitle">Demandes, marchés figés et résultats de vos calculs.</p></div><div class="flex gap-2"><RouterLink to="/structuring" class="btn-ghost btn-sm">← Structuring Intelligence</RouterLink><RouterLink to="/structuring/optimizer" class="btn-primary btn-sm">Nouvelle recherche</RouterLink></div></header>
    <p v-if="demo.enabled" class="scope-note">Dossiers masqués en mode Démo.</p>
    <template v-else>
      <div class="filters"><label>Rechercher<input class="input" type="search" v-model="query" placeholder="Nom, sous-jacent ou intention…" /></label><label>Famille<select class="select" v-model="family"><option value="">Toutes les familles</option><option v-for="item in families" :key="item.product_family" :value="item.product_family">{{ item.label }}</option></select></label><label>État<select class="select" v-model="status"><option value="">Tous les états</option><option v-for="(label,key) in researchStatuses" :key="key" :value="key">{{ label }}</option></select></label><label class="archive-toggle"><input type="checkbox" v-model="archived" /> Dossiers archivés</label><button class="btn-secondary btn-sm" :disabled="loading" @click="load">Actualiser</button></div>
      <p v-if="error" class="alert-error" role="alert">{{ error }}</p>
      <div class="card library-table"><table><thead><tr><th>Recherche</th><th>Marché / création</th><th>État <HelpTip :text="helpFor('status')" /></th><th>Pricés / confirmés</th><th>Actions</th></tr></thead><tbody>
        <template v-for="item in items" :key="item.id"><tr :class="{expanded:opened===item.id}"><td><button class="row-toggle" @click="opened=opened===item.id?null:item.id" :aria-expanded="opened===item.id">{{ opened===item.id?'▾':'▸' }} {{ item.title }}</button><p class="text-xs text-slate-500 mt-1">{{ item.family_label }}</p></td><td>{{ item.pricing_date }}<p class="text-xs text-slate-500">{{ date(item.created_at) }}</p></td><td><span class="status" :class="item.status.toLowerCase()">{{ researchStatuses[item.status] }}</span></td><td>{{ item.statistics?.priced ?? 0 }} / {{ item.statistics?.valid ?? 0 }}</td><td><div class="actions"><RouterLink :to="`/structuring/researches/${item.id}`" class="btn-secondary btn-sm">Ouvrir</RouterLink><RouterLink :to="{path:'/structuring/optimizer',query:{from:item.id}}" class="btn-ghost btn-sm">Reprendre</RouterLink><button class="btn-ghost btn-sm" :disabled="updating===item.id" @click="archive(item)">{{ item.archived?'Restaurer':'Archiver' }}</button></div></td></tr>
        <tr v-if="opened===item.id"><td colspan="5"><div class="summary-scroll"><p>{{ item.summary }}</p><p v-if="item.intention" class="mt-2"><b>Intention :</b> {{ item.intention }}</p><p v-if="item.error" class="text-red-700 mt-2">{{ item.error }}</p><p v-if="item.parent_id" class="text-xs mt-2">Version issue de <RouterLink :to="`/structuring/researches/${item.parent_id}`">la recherche d’origine</RouterLink>.</p><p v-if="item.status==='RUNNING'" class="text-xs mt-2">{{ item.progress.phase==='validation'?'Validation indépendante':'Exploration' }} · {{ item.progress.completed || 0 }} / {{ item.progress.total || '—' }}.</p></div></td></tr></template>
        <tr v-if="!items.length"><td colspan="5" class="text-center">{{ loading?'Chargement…':'Aucune recherche pour ces filtres.' }}</td></tr>
      </tbody></table></div>
      <footer class="pagination"><span>{{ total }} dossier(s) · page {{ Math.floor(offset/limit)+1 }}</span><div class="flex gap-2"><button class="btn-secondary btn-sm" :disabled="loading || offset===0" @click="offset-=limit">Précédente</button><button class="btn-secondary btn-sm" :disabled="loading || offset+limit>=total" @click="offset+=limit">Suivante</button></div></footer>
    </template>
  </main>
</template>
<script setup>
import { onBeforeUnmount,onMounted,ref,watch } from 'vue'
import { RouterLink } from 'vue-router'
import HelpTip from '../components/HelpTip.vue'
import { useDemoModeStore } from '../stores/demoMode.js'
import { researchApi,researchStatuses,helpFor } from '../utils/optimizerResearch.js'
import { optimizerJson } from '../utils/productOptimizer.js'
const demo=useDemoModeStore(),query=ref(''),family=ref(''),status=ref(''),archived=ref(false),offset=ref(0),limit=30
const families=ref([]),items=ref([]),total=ref(0),opened=ref(null),loading=ref(false),error=ref(''),updating=ref(null)
let timer,controller,generation=0,disposed=false
const date=value=>new Date(value).toLocaleString('fr-FR')
async function load(){
  if(disposed)return
  clearTimeout(timer);controller?.abort();const version=++generation
  if(demo.enabled){items.value=[];total.value=0;loading.value=false;return}
  controller=new AbortController();loading.value=true
  try {
    const params=new URLSearchParams({q:query.value,family:family.value,status:status.value,archived:String(archived.value),offset:String(offset.value),limit:String(limit)})
    const data=await researchApi(`?${params}`,'GET',undefined,controller.signal)
    if(version!==generation)return
    items.value=data.items;total.value=data.total;error.value=''
    if(data.items.some(item=>item.status==='RUNNING'))timer=setTimeout(load,4000)
  } catch(e){if(e.name!=='AbortError' && version===generation)error.value=e.message}
  finally {if(version===generation)loading.value=false}
}
watch([query,family,status,archived,()=>demo.enabled],()=>{offset.value=0;clearTimeout(timer);timer=setTimeout(load,250)})
watch(offset,load)
onMounted(async()=>{load();try{const data=await optimizerJson('capabilities');if(!disposed)families.value=data.families.filter(f=>f.status==='SUPPORTED')}catch(e){if(!disposed)error.value=e.message}})
async function archive(item){updating.value=item.id;try{await researchApi(`/${item.id}`,'PATCH',{archived:!item.archived});if(offset.value>0 && items.value.length===1)offset.value-=limit;else await load()}catch(e){error.value=e.message}finally{updating.value=null}}
onBeforeUnmount(()=>{disposed=true;generation++;clearTimeout(timer);controller?.abort()})
</script>
<style scoped>
.research-library { display:flex; flex-direction:column; flex:1; min-height:0; width:100%; padding:20px 24px; gap:16px; }
.filters { display:flex; align-items:end; gap:12px; flex-wrap:wrap; }.filters label { display:flex; flex-direction:column; gap:5px; font-size:12px; }.filters label:first-child { flex:1; min-width:200px; }.filters .archive-toggle { flex-direction:row; align-items:center; align-self:center; }
.library-table { padding:0; flex:1; min-height:0; overflow:auto; overscroll-behavior:contain; }
table { width:100%; border-collapse:collapse; font-size:13px; }th,td { padding:12px 16px; text-align:left; border-bottom:1px solid var(--border); }thead th { position:sticky; top:0; z-index:1; background:var(--surface); font-size:12px; }td:first-child { min-width:240px; }td { vertical-align:top; }.expanded { background:var(--bg); }
.row-toggle { text-align:left; font-weight:600; }.actions { display:flex; gap:6px; flex-wrap:wrap; }.summary-scroll { max-height:180px; overflow:auto; overscroll-behavior:contain; font-size:12px; line-height:1.6; white-space:pre-wrap; }
.status { padding:4px 8px; border-radius:5px; font-size:11px; white-space:nowrap; background:#eff6ff; color:#1e3a8a; }.failed,.interrupted { background:#fff1f2; color:#9f1239; }.partial { background:#fffbeb; color:#92400e; }.completed { background:#f1f5f9; color:#334155; }
.pagination { display:flex; justify-content:space-between; align-items:center; font-size:12px; }.alert-error { padding:12px; background:#fff1f2; color:#9f1239; }
@media(max-width:700px){.research-library{padding:12px;gap:12px;}.page-header{flex-wrap:wrap;gap:10px;}.filters label{min-width:120px;}.library-table{min-height:180px;}th,td{padding:10px;}}
</style>
