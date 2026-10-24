<script setup>
import { computed, ref, nextTick, watch, onMounted, onUnmounted } from 'vue'
import { apiFetch } from '../utils/api'
import { useAuthStore } from '../stores/auth.js'
import BackLink from '../components/ui/BackLink.vue'
import WorkshopMonitor from '../components/WorkshopMonitor.vue'
import WorkshopHelp from '../components/WorkshopHelp.vue'
import WorkshopIssues from '../components/WorkshopIssues.vue'
import WorkshopBooks from '../components/WorkshopBooks.vue'
import WorkshopConfiguration from '../components/WorkshopConfiguration.vue'
import { campaignIssues } from '../utils/workshopIssues'
import { workshopLabels, campaignRows, actionTitle, actionOutcome, actionEvidence, usageProof, money } from '../utils/workshopProgress'
import { previousLocalYearDate } from '../utils/workshopDate'
import { timelinePage, matchedBankVolumes } from '../utils/workshopPilot'
import { confirmer } from '../composables/useConfirm'

const base = '/api/agent-workshop'
const auth = useAuthStore()
const campaigns = ref([]), models = ref([]), providers = ref([]), state = ref(null), error = ref(''), busy = ref(false)
const tab = ref('overview'), actorFilter = ref(''), image = ref(''), selectedAction = ref(null)
const updatedAt = ref(0), now = ref(Date.now()), creating = ref(false)
const proofPanel = ref(null)
const notice = ref('')
const modelError=ref(''), pollError=ref(''), campaignQuery=ref(''), campaignStatus=ref('')
const timelineQuery=ref(''), dossierFilter=ref(''), actionStatus=ref(''), actionPage=ref(1), messagePage=ref(1)
const mobileCampaigns=ref(false)
const bookCaseId=ref('')
const consultationBusy=ref('')
const hasConsultations=computed(()=>Object.values(state.value?.consultations||{}).some(c=>c.online))
function canConsult(actor){return actor.role!=='supervisor'&&actor.registered&&['STOPPED','COMPLETED','ATTENTION'].includes(state.value?.status)}
async function openConsultation(actor){
  if(busy.value||consultationBusy.value)return
  const id=state.value.id
  const popup=window.open('','_blank')
  if(popup){popup.opener=null;popup.document.body.textContent='Ouverture de Structura en consultation…'}
  consultationBusy.value=actor.id;error.value=''
  try{
    const opened=await request(`/${id}/consultations/${actor.id}`,{method:'POST'})
    if(popup)popup.location.replace(opened.launch_url)
    else {notice.value='Autorisez les nouveaux onglets, puis cliquez à nouveau sur « Ouvrir en consultation ».'}
    const next=await request('/'+id);if(state.value?.id===id)receive(next)
  }catch(e){popup?.close();error.value=e.message}
  finally{consultationBusy.value=''}
}
async function closeConsultation(actor){
  if(busy.value||consultationBusy.value)return
  const id=state.value.id;consultationBusy.value=actor.id;error.value=''
  try{await request(`/${id}/consultations/${actor.id}`,{method:'DELETE'});const next=await request('/'+id);if(state.value?.id===id)receive(next)}
  catch(e){error.value=e.message}finally{consultationBusy.value=''}
}
const defaultConfig = () => ({ name: 'Campagne de diagnostic — Kepler et cinq répondants', provider: 'openai', model: 'gpt-6-luna', start_date: previousLocalYearDate(), months: 12, maturity_months: 12, payoff_templates: ['reverse_convertible', 'phoenix'], ticket: 10000000, target_volume: 100000000, max_turns: 1200, max_model_calls: 1500, max_ai_cost_usd: 5, timeout_seconds: 90, seed: 42, coaching: true, exploratory_actions: false, include_sg: true, contract_scenario: 'all_complete', environment:'hybrid', leonteq_role:'bank', native_rfq:true })
const config = ref(defaultConfig())
const forecast=ref(null), previewError=ref(''), editingConfig=ref(null)
let defaultsCache=null, previewTimer, previewEpoch=0
async function estimate(){
  if(config.value.schema_version!==2)return
  const revision=++previewEpoch;forecast.value=null;previewError.value=''
  try{const value=await request('/preview',{method:'POST',body:JSON.stringify(config.value)});if(revision===previewEpoch)forecast.value=value}
  catch(e){if(revision===previewEpoch)previewError.value=e.message}
}
function editConfiguration(){editingConfig.value=state.value.id;config.value=JSON.parse(JSON.stringify(state.value.config));creating.value=true}
const selectedProvider = computed(() => providers.value.find(p => p.key === config.value.provider))
const modelOptions = computed(() => selectedProvider.value?.models || [])
function providerFor(campaignConfig) { return providers.value.find(p => p.key === (campaignConfig?.provider || 'ollama')) }
function modelAvailable(campaignConfig) { const p=providerFor(campaignConfig); return !!p?.ready && p.models.some(m => m.id === campaignConfig.model) }
function syncModel() {
  const provider = selectedProvider.value
  models.value = (provider?.models || []).map(m => m.id)
  modelError.value = provider?.hint || ''
  if (models.value.length && !models.value.includes(config.value.model)) config.value.model = provider.default_model || models.value[0]
}
function modelLabel(option) { return option.label + (option.input != null ? ` · ${option.input} $ / ${option.output} $ par million de jetons entrée / sortie` : '') }
function usd(value) { return new Intl.NumberFormat('fr-FR', {minimumFractionDigits: 2, maximumFractionDigits: 4}).format(Number(value || 0)) + ' $' }
let timer, clockTimer, closed = false, epoch = 0, imageEpoch = 0
function receive(next) { state.value=next; updatedAt.value=Date.now() }
async function request(path = '', options = {}) {
  const res = await apiFetch(base + path, { ...options, headers: { ...(options.body ? {'Content-Type':'application/json'} : {}) } })
  if (!res.ok) { const body = await res.json().catch(()=>({})); throw new Error(typeof body.detail==='string' ? body.detail : JSON.stringify(body.detail || res.status)) }
  return res.json()
}
async function load() {
  try { campaigns.value = await request(); const data = await request('/models'); providers.value = data.providers || []; if(!defaultsCache){defaultsCache=await request('/defaults');config.value=structuredClone(defaultsCache)}; syncModel() }
  catch (e) { error.value = e.message }
}
async function refresh() {
  await load()
  if(state.value&&!busy.value){const id=state.value.id, version=epoch;try{const next=await request('/'+id);if(version===epoch&&state.value?.id===id)receive(next)}catch(e){error.value=e.message}}
}
async function select(id) { const version=++epoch; resetView(); notice.value=''; try { const next=await request('/'+id); if(version!==epoch)return; receive(next); mobileCampaigns.value=false;error.value = '';pollError.value=''; } catch(e) { error.value=e.message } }
async function create() {
  busy.value = true; error.value = ''; const version=++epoch
  try { const next=await request(editingConfig.value?`/${editingConfig.value}/configuration`:'', {method:editingConfig.value?'PATCH':'POST',body:JSON.stringify(config.value)}); if(version===epoch){receive(next);tab.value='overview';selectedAction.value=null;actorFilter.value='';creating.value=false;editingConfig.value=null} await load() }
  catch(e) { error.value=e.message } finally { busy.value=false }
}
async function command(action) {
  const id=state.value.id, version=++epoch
  busy.value=true; error.value=''
  try { const next=await request(`/${id}/${action}`,{method:'POST'}); if(version===epoch&&state.value?.id===id)receive(next); await load() }
  catch(e) { error.value=e.message } finally { busy.value=false }
}
function resetView() {
  tab.value='overview';actorFilter.value='';selectedAction.value=null;creating.value=false;timelineQuery.value='';dossierFilter.value='';bookCaseId.value='';actionStatus.value='';actionPage.value=messagePage.value=1
  imageEpoch++;if(image.value)URL.revokeObjectURL(image.value);image.value=''
}
function resetFields() {
  config.value=structuredClone(defaultsCache||defaultConfig())
  editingConfig.value=null
  syncModel()
}
async function manage(action) {
  const current=state.value
  if(!current||busy.value||live.value)return
  const resetting=action==='replay'
  if(!await confirmer({
    titre:`${resetting ? 'Recommencer' : 'Supprimer'} « ${current.config.name} » ?`,
    message:resetting ? 'Une nouvelle campagne sera prête avec les mêmes paramètres. Les identités et référentiels préparés sont réutilisés ; les données transactionnelles sont vierges. Cet essai reste consultable.' : 'Cet essai sera retiré de la liste et de la vue. Les autres campagnes restent disponibles.',
    detail:`Essai ${current.id.slice(0,8)} · ${current.turns} décisions\n${resetting ? 'Les deux essais conserveront des références distinctes. Aucun agent ne démarre automatiquement.' : 'Une sauvegarde locale de cet essai sera conservée. Vous pouvez exporter les preuves avant de continuer.'}`,
    confirmer:resetting ? 'Recommencer à zéro' : 'Supprimer la campagne',danger:!resetting,
  }))return
  if(state.value?.id!==current.id)return
  const version=++epoch
  busy.value=true;error.value='';notice.value=''
  try {
    const next=await request(`/${current.id}${resetting ? '/replay' : ''}`,{method:resetting ? 'POST' : 'DELETE'})
    if(version!==epoch)return
    resetView()
    if(!resetting)campaigns.value=campaigns.value.filter(c=>c.id!==current.id)
    if(resetting)receive(next);else state.value=null
    notice.value=resetting ? 'Nouvel essai prêt : 0 décision, comptes et books vierges. L’ancien essai reste consultable. Cliquez sur « Démarrer les IA » pour rejouer.' : 'Campagne supprimée de la liste ; sauvegarde locale conservée.'
    await load()
    if(!resetting&&version===epoch&&campaigns.value.length){const message=notice.value;await select(campaigns.value[0].id);notice.value=message}
  } catch(e) {error.value=e.message} finally {busy.value=false}
}
async function poll() {
  if (closed) return
  if(state.value && !busy.value) {
    const id=state.value.id, version=epoch
    try { const next=await request('/'+id); if(!closed&&!busy.value&&version===epoch&&state.value?.id===id) {receive(next);pollError.value=''}; const list=await request();if(!closed&&version===epoch)campaigns.value=list }
    catch(e) { pollError.value=e.message }
  }
  if(!closed) timer=setTimeout(poll,3000)
}
async function download() {
  try {
    const res=await apiFetch(base+`/${state.value.id}/export`); if(!res.ok) throw new Error('Export indisponible')
    const url=URL.createObjectURL(await res.blob()), link=document.createElement('a'); link.href=url; link.download=`recette-${state.value.id.slice(0,8)}.json`; link.click(); URL.revokeObjectURL(url)
  } catch(e) { error.value=e.message }
}
async function showAction(action) {
  const version=++imageEpoch, id=state.value.id
  selectedAction.value=action
  if(image.value) URL.revokeObjectURL(image.value); image.value=''
  const name=action.result?.screenshot
  if(name) try { const res=await apiFetch(base+`/${id}/screenshots/${encodeURIComponent(name)}`); if(!res.ok) throw new Error('Capture indisponible'); const blob=await res.blob(); if(version===imageEpoch&&!closed)image.value=URL.createObjectURL(blob) } catch(e) { if(version===imageEpoch)error.value=e.message }
}
async function inspect(action) { tab.value='actions'; showAction(action); await nextTick(); proofPanel.value?.scrollIntoView({behavior:'smooth',block:'start'}) }
function lastAction(id) { return state.value?.actions?.findLast(a=>a.actor===id && a.tool!=='wait') }
function actorStatus(actor) { if(state.value.status==='COMPLETED')return 'Parcours terminé'; if(['STOPPED','ATTENTION'].includes(state.value.status)||state.value.controller_active===false&&state.value.status!=='DRAFT')return 'Agent arrêté'; if(state.value.status==='PAUSED')return 'En pause'; return actor.status }
const labels=workshopLabels
const rows=computed(()=>campaignRows(campaigns.value,state.value))
const visibleCampaigns=computed(()=>rows.value.filter(c=>(!campaignStatus.value||c.status===campaignStatus.value)&&(!campaignQuery.value||`${c.config.name} ${c.id}`.toLocaleLowerCase('fr-FR').includes(campaignQuery.value.toLocaleLowerCase('fr-FR')))))
const live=computed(()=>state.value && state.value.controller_active!==false && ['RUNNING','PAUSING','PAUSED','STOPPING'].includes(state.value.status))
const messages=computed(()=>timelinePage(state.value?.messages||[],{actor:actorFilter.value,caseId:dossierFilter.value,query:timelineQuery.value,page:messagePage.value,messages:true}))
const actions=computed(()=>timelinePage(state.value?.actions||[],{actor:actorFilter.value,caseId:dossierFilter.value,query:timelineQuery.value,status:actionStatus.value,page:actionPage.value}))
const actors=computed(()=>Object.values(state.value?.actors||{}))
const issues=computed(()=>state.value ? campaignIssues(state.value) : [])
function openIssues() { actorFilter.value='';tab.value='incidents' }
const openIssueCount=computed(()=>issues.value.filter(i=>i.status!=='CLOSED').length)
const bankVolumes=computed(()=>matchedBankVolumes(state.value||{}))
const canStart=computed(()=>state.value&&!hasConsultations.value&&!consultationBusy.value&&state.value.turns<state.value.config.max_turns&&modelAvailable(state.value.config)&&!state.value.budget_blocked&&state.value.usage.model_calls<(state.value.config.max_model_calls||20000)&&((state.value.config.provider||'ollama')!=='openai'||(state.value.usage.model_cost_usd||0)<state.value.config.max_ai_cost_usd))
function recover(action){if(action==='configure'){config.value={...state.value.config, provider:state.value.config.provider||'ollama'};syncModel();creating.value=true}else if(!busy.value)command(action)}
async function reviewIssue(id,body){const campaign=state.value.id;await request(`/${campaign}/issues/${encodeURIComponent(id)}`,{method:'PATCH',body:JSON.stringify(body)});const next=await request('/'+campaign);if(state.value?.id===campaign)receive(next)}
watch([actorFilter,dossierFilter,timelineQuery,actionStatus],()=>{actionPage.value=messagePage.value=1})
watch(() => config.value.provider, syncModel)
watch(config,()=>{previewEpoch++;clearTimeout(previewTimer);forecast.value=null;previewTimer=setTimeout(estimate,300)},{deep:true})
watch(creating,value=>{if(value&&!editingConfig.value){config.value=structuredClone(defaultsCache||config.value);estimate()}})
function who(id) { return state.value?.actors[id]?.name || id }
onMounted(async()=>{
  clockTimer=setInterval(()=>{now.value=Date.now()},1000)
  if (auth.isPlatformAdmin) {
    try {
      const response = await apiFetch('/api/platform/simulation/start', {method:'POST'})
      if (!response.ok) { const data = await response.json(); throw new Error(data.detail || 'Contrôleur indisponible.') }
    } catch(e) { error.value=e.message; return }
  }
  const initialEpoch=epoch
  await load()
  if(epoch===initialEpoch&&!state.value&&campaigns.value.length) await select(campaigns.value[0].id)
  poll()
})
onUnmounted(()=>{ closed=true; imageEpoch++; previewEpoch++;clearTimeout(previewTimer); clearTimeout(timer); clearInterval(clockTimer); if(image.value) URL.revokeObjectURL(image.value) })
</script>

<template>
  <main class="workshop">
    <header class="heading"><BackLink fallback="/"/><div><h1>Simulation entre agents <WorkshopHelp topic="page"/></h1><p>Préparer une campagne de diagnostic, suivre les parcours et relever les anomalies.</p></div><button class="btn-secondary mobile-campaigns" @click="mobileCampaigns=!mobileCampaigns">Campagnes ({{rows.length}})</button><button class="btn-secondary" @click="refresh">Actualiser</button></header>
    <p class="notice">Environnement de recette isolé · {{(creating?config:state?.config)?.market_mode==='historical'?'Historiques existants · Arrêt à la date finale':'Ancien marché synthétique identifié'}} · Aucun objectif commercial n’impose un résultat.</p>
    <p v-if="error" role="alert" class="error">{{error}}</p>
    <p v-if="pollError" role="alert" class="error">Suivi interrompu : {{pollError}}. Le dernier état reçu reste affiché.</p>
    <p v-if="notice" role="status" class="notice">{{notice}}</p>
    <div class="layout" :class="{configuring:creating||!campaigns.length}">
      <aside v-if="!creating&&campaigns.length" class="panel campaign-sidebar" :class="{'mobile-open':mobileCampaigns}">
        <h2>Campagnes <WorkshopHelp topic="campaigns"/></h2><button class="btn-secondary new-campaign" @click="creating=!creating">{{creating ? 'Fermer la configuration' : '+ Nouvelle campagne'}}</button>

        <h2 class="mt-6">Campagnes conservées ({{rows.length}})</h2>
        <p class="muted">Sélectionnez un essai pour le recommencer ou le supprimer.</p>
        <input v-model="campaignQuery" aria-label="Rechercher une campagne" class="input" placeholder="Nom ou référence"/>
        <select v-model="campaignStatus" aria-label="État des campagnes" class="input campaign-state"><option value="">Tous les états</option><option v-for="id in ['DRAFT','RUNNING','PAUSED','STOPPED','COMPLETED','ATTENTION']" :key="id" :value="id">{{labels[id]}}</option></select>
        <p v-if="!visibleCampaigns.length&&rows.length" class="muted">Aucun essai dans ce filtre.</p>
        <button v-for="c in visibleCampaigns" :key="c.id" class="campaign" :disabled="busy" :class="{selected:state?.id===c.id}" @click="select(c.id)"><strong>{{c.config.name}}</strong><span>{{c.displayStatus||labels[c.status]||c.status}} · {{c.turns}} actions</span><small>{{c.month||0}} / {{c.config.horizon_months||c.config.months}} mois · essai {{c.id.slice(0,8)}}<template v-if="c.replay_of"> · reprise vierge</template></small></button>
      </aside>
      <WorkshopConfiguration v-if="(creating||!campaigns.length)&&config.schema_version===2" :config="config" :providers="providers" :forecast="forecast" :error="previewError" :busy="busy" :editing="!!editingConfig" @save="create" @cancel="creating=false;editingConfig=null"/>
      <section v-else-if="state" class="content">
        <div class="panel">
          <div class="heading"><div><h2>{{state.config.name}}</h2><p v-if="state.completion_scope==='HISTORICAL_CUTOFF'" class="notice">Date finale atteinte : {{state.config.end_date}}. Les produits encore vivants sont conservés dans les books, avec leur dernière valorisation.</p><p>{{state.controller_active===false&&['RUNNING','PAUSED','PAUSING','STOPPING'].includes(state.status) ? 'Exécution non confirmée' : labels[state.status]||state.status}} · {{state.config.provider==='openai' ? 'OpenAI' : 'Ollama local'}} · {{state.config.model}}</p></div><span class="badge">{{state.business_date}} · {{state.month>=(state.config.horizon_months||state.config.months)?'Suivi contractuel final':'mois '+(state.month+1)+' / '+(state.config.horizon_months||state.config.months)}}</span></div>
          <p v-if="state.replay_of" class="muted">Nouvel essai issu de {{state.replay_of.slice(0,8)}} · <button v-if="rows.some(c=>c.id===state.replay_of)" class="proof-link" @click="select(state.replay_of)">Consulter l’ancien essai</button><span v-else>ancien essai retiré de la liste</span></p>
          <div class="controls"><button v-if="!live&&state.status!=='COMPLETED'" class="btn-primary" :disabled="busy||!canStart" @click="command('start')">Démarrer les IA</button><button v-if="live&&state.status==='RUNNING'" class="btn-secondary" :disabled="busy" @click="command('pause')">Pause</button><button v-if="live&&state.status==='PAUSED'" class="btn-primary" :disabled="busy" @click="command('resume')">Reprendre</button><button v-if="live" class="btn-secondary" :disabled="busy" @click="command('stop')">Arrêter</button><button class="btn-secondary" @click="download">Exporter les preuves</button><button class="btn-secondary" @click="openIssues">Voir les problèmes ({{issues.length}})</button><span class="muted">{{openIssueCount}} ouvert(s) <WorkshopHelp topic="issues"/></span></div>
          <p v-if="!live&&state.status!=='COMPLETED'&&!modelAvailable(state.config)" class="muted">{{providerFor(state.config)?.hint||'Le modèle choisi n’est pas disponible dans ce processus.'}}</p>
          <p class="muted">{{state.turns}} actions · {{state.usage.model_calls}} appels IA · {{(state.actions||[]).length}} résultats consignés <WorkshopHelp topic="decisions"/></p>
          <button v-if="state.status==='DRAFT'&&state.config.schema_version===2" class="btn-secondary" @click="editConfiguration">Modifier les paramètres</button>
          <div v-if="state.forecast" class="forecast-result"><p>Estimation avant lancement : {{usd((state.forecast_at_start||state.forecast).cost_usd.central)}} · jusqu’à {{(state.forecast_at_start||state.forecast).model_calls.high}} appels IA</p><p v-if="state.config.provider==='openai'">Écart au coût central estimé : {{usd((state.usage.model_cost_usd||0)-(state.forecast_at_start||state.forecast).cost_usd.central)}}<template v-if="state.usage.unknown_cost_calls"> · consommation incomplète</template></p><p>Réalisé : {{state.usage.pricings||0}} pricings · {{state.usage.mtms||0}} MtM · {{state.usage.risk_reports||0}} rapports quantitatifs<template v-if="state.usage.unknown_cost_calls"> · {{state.usage.unknown_cost_calls}} appel(s) de coût inconnu</template></p><p v-if="state.stop_reason">Arrêt : {{state.stop_reason.kind}} · {{state.stop_reason.detail||'Consulter les problèmes et preuves avant la reprise.'}}</p></div>
          <p v-if="state.config.provider==='openai'" class="muted">Coût IA estimé : {{usd(state.usage.model_cost_usd)}} / {{usd(state.config.max_ai_cost_usd)}} · {{state.usage.model_input_tokens||0}} jetons en entrée · {{state.usage.model_output_tokens||0}} en sortie <WorkshopHelp topic="ai_budget"/></p>
          <details class="management"><summary>Gérer cet essai <WorkshopHelp topic="manage"/></summary><div><button class="btn-secondary" :disabled="busy" @click="resetView">Réinitialiser la vue</button><button class="btn-secondary" :disabled="busy||live||hasConsultations||consultationBusy" @click="manage('replay')">Recommencer la campagne</button><button class="btn-danger" :disabled="busy||live||hasConsultations||consultationBusy" @click="manage('delete')">Supprimer la campagne</button></div><p v-if="live" class="muted">Arrêtez les IA et attendez la fermeture des installations avant de recommencer ou supprimer cet essai.</p><p v-if="hasConsultations" class="muted">Fermez les consultations avant de démarrer les IA, recommencer ou supprimer la campagne.</p></details>
        </div>
        <WorkshopMonitor :key="state.id" :state="state" :now="now" :updated-at="updatedAt" :show-history="false" :show-workflow="false" :actor-filter="actorFilter" @inspect="inspect" @recover="recover" @issues="openIssues">
          <template #metrics><div class="metrics"><div><span>Volume clients rapproché <WorkshopHelp topic="volume"/></span><strong>{{state.commercial_volume>=1000000 ? new Intl.NumberFormat('fr-FR',{maximumFractionDigits:2}).format(state.commercial_volume/1000000)+' M€' : money(state.commercial_volume)}}</strong><small v-if="state.config.schema_version!==2">Objectif {{money(state.config.target_volume)}}</small><small v-else>Volume constaté ; aucun objectif de vente imposé</small></div><div><span>Opérations rapprochées <WorkshopHelp topic="matched"/></span><strong>{{state.book_checks?.filter(c=>c.status==='COMPLETE').length||0}}</strong><small>4 écritures par opération · {{Object.keys(state.cases).length}} besoins</small></div><div><span>Points à examiner <WorkshopHelp topic="issues"/></span><button class="metric-link" :aria-label="'Voir les problèmes ('+issues.length+')'" @click="openIssues">{{issues.length}} →</button><small>Ouvrir les signalements</small></div></div></template>
        </WorkshopMonitor>
        <nav class="tabs"><span v-for="[id,label] in [['overview','Vue d’ensemble'],['messages','Conversations'],['actions','Actions et preuves'],['books','Books et risques'],['incidents','Bugs et améliorations']]" :key="id" class="tab-item"><button :class="{selected:tab===id}" @click="tab=id">{{label}}<template v-if="id==='incidents'"> ({{issues.length}})</template></button><WorkshopHelp :topic="id==='incidents' ? 'incidents' : id"/></span><button v-if="actorFilter" @click="actorFilter=''">Tous les acteurs ×</button></nav>
        <WorkshopIssues v-if="tab==='incidents'" :key="state.id" :state="state" :actor-filter="actorFilter" :save-review="reviewIssue" @inspect="inspect" @inspect-book="id=>{bookCaseId=id;tab='books'}"/>
        <WorkshopMonitor v-if="tab==='overview'" :key="state.id+'-workflow'" :state="state" :now="now" :updated-at="updatedAt" :show-current="false" :show-history="true" :actor-filter="actorFilter" @inspect="inspect"/>

        <div v-if="tab==='overview'" class="actor-grid">
          <article v-for="actor in actors" :key="actor.id" class="panel actor" :class="{selected:actorFilter===actor.id,working:state.activity?.actor===actor.id&&state.status==='RUNNING'&&state.controller_active!==false}">
            <button class="actor-heading" :aria-label="'Filtrer '+actor.name" :aria-pressed="actorFilter===actor.id" @click="actorFilter=actorFilter===actor.id?'':actor.id">
            <svg viewBox="0 0 64 64" width="56" height="56" aria-hidden="true"><circle cx="32" cy="32" r="31" :fill="actor.colour"/><path d="M12 58 Q15 38 32 38 Q49 38 52 58" fill="#dce5ed"/><ellipse cx="32" cy="26" rx="12" ry="15" fill="#e9b890"/><path d="M20 25 Q15 8 32 9 Q48 7 45 25 L40 17 L24 18Z" fill="#263143"/><circle cx="28" cy="26" r="1.3" fill="#263143"/><circle cx="37" cy="26" r="1.3" fill="#263143"/><path d="M29 33 Q33 36 37 32" fill="none" stroke="#9d6451" stroke-width="1.5"/><path v-if="actor.id==='achille'" d="M22 25h8v5h-8zM34 25h8v5h-8zM30 27h4" stroke="#1a263c" fill="none"/></svg>
            <span><strong>{{actor.name}}</strong><small>{{actorStatus(actor)}}</small></span></button>
            <p v-if="lastAction(actor.id)" class="last-action">{{actionTitle(lastAction(actor.id))}}</p><p v-else class="last-action">Aucune action terminée</p>
            <small>{{usageProof(state,actor.id).screens}} écrans · {{usageProof(state,actor.id).apiActions}} actions API · {{actor.deals.length}} deals <WorkshopHelp topic="actors"/></small>
            <button v-if="lastAction(actor.id)" class="proof-link" @click="inspect(lastAction(actor.id))">Voir la dernière preuve →</button>
            <details><summary>Objectif et part de marché</summary><small>{{actor.goal}}</small><small v-if="actor.role==='bank'">Part du volume rapproché : {{bankVolumes.total ? (100*bankVolumes.result[actor.id]/bankVolumes.total).toFixed(1)+' %':'Non calculable'}}</small></details>
            <a v-if="actor.online&&live" :href="actor.url+'/#/login'" target="_blank" rel="noopener" @click.stop>Ouvrir son Structura ↗</a>
            <div v-else-if="canConsult(actor)" class="consultation-controls">
              <button class="btn-secondary" :disabled="busy||!!consultationBusy" :aria-label="'Ouvrir le Structura de '+actor.name+' en consultation'" @click="openConsultation(actor)">{{consultationBusy===actor.id?'Patientez…':'Ouvrir en consultation ↗'}}</button>
              <button v-if="state.consultations?.[actor.id]?.online" class="proof-link" :disabled="busy||!!consultationBusy" @click="closeConsultation(actor)">Fermer la consultation</button>
              <small>Lecture seule · IA arrêtées<template v-if="state.consultations?.[actor.id]?.online"> · Consultation ouverte</template></small>
            </div>
            <span v-else class="muted">{{actor.role==='supervisor'?'Supervision':'Instance fermée'}}</span>
          </article>
        </div>
        <div v-if="tab==='messages'||tab==='actions'" class="timeline-controls panel">
          <input v-model="timelineQuery" class="input" aria-label="Rechercher dans le journal" placeholder="Rechercher dans tout l’historique"/>
          <select v-model="actorFilter" class="input" aria-label="Acteur du journal"><option value="">Tous les acteurs</option><option v-for="a in actors" :key="a.id" :value="a.id">{{a.name}}</option></select>
          <select v-model="dossierFilter" class="input" aria-label="Dossier du journal"><option value="">Tous les dossiers</option><option v-for="c in Object.values(state.cases)" :key="c.id" :value="c.id">{{c.id}}</option></select>
          <select v-if="tab==='actions'" v-model="actionStatus" class="input" aria-label="Résultat du journal"><option value="">Tous les résultats</option><option v-for="id in ['SUCCESS','FAILED','EXPECTED_REFUSAL']" :key="id" :value="id">{{labels[id]}}</option></select>
          <nav v-if="tab==='actions'" aria-label="Pages des actions" class="pagination"><button class="btn-secondary" :disabled="actions.page<=1" @click="actionPage=actions.page-1">Actions précédentes</button><span>{{actions.total}} résultats · page {{actions.page}} / {{actions.pages}}</span><button class="btn-secondary" :disabled="actions.page>=actions.pages" @click="actionPage=actions.page+1">Actions suivantes</button></nav>
          <nav v-else aria-label="Pages des conversations" class="pagination"><button class="btn-secondary" :disabled="messages.page<=1" @click="messagePage=messages.page-1">Messages précédents</button><span>{{messages.total}} messages · page {{messages.page}} / {{messages.pages}}</span><button class="btn-secondary" :disabled="messages.page>=messages.pages" @click="messagePage=messages.page+1">Messages suivants</button></nav>
        </div>
        <section v-if="tab==='messages'" class="panel feed"><p v-if="!messages.total" class="muted">Les échanges apparaîtront lorsque les IA agiront.</p><article v-for="m in messages.items" :key="m.id"><div class="heading"><strong>{{who(m.from)}} → {{who(m.to)}}</strong><small>{{m.date}} {{m.case_id}}</small></div><h3>{{m.subject}}</h3><p>{{m.body}}</p><details v-if="m.attachment"><summary>Pièce jointe structurée</summary><pre>{{JSON.stringify(m.attachment,null,2)}}</pre></details></article></section>
        <section v-if="tab==='actions'" ref="proofPanel" class="panel">
          <div v-if="selectedAction" class="action-proof"><h2>{{who(selectedAction.actor)}} · {{actionTitle(selectedAction)}}</h2><p>{{actionOutcome(selectedAction,state)}}</p><p class="muted">{{selectedAction.date}} · {{labels[selectedAction.status]||selectedAction.status}} · {{actionEvidence(selectedAction).label}} · {{actionEvidence(selectedAction).detail}}</p><p v-if="selectedAction.reason">Décision de l’IA : {{selectedAction.reason}}</p><img v-if="image" :src="image" alt="Capture de l’écran réellement utilisé"/><p v-else-if="actionEvidence(selectedAction).kind==='api'" class="muted">Cette action a utilisé les API de Structura. Aucune capture de navigation n’est associée.</p><div v-if="selectedAction.http_calls?.length" class="table-wrap"><table><caption>Réponses de Structura dans l’installation de {{who(selectedAction.actor)}}</caption><thead><tr><th>Méthode</th><th>Fonction appelée</th><th>Réponse <WorkshopHelp topic="http"/></th></tr></thead><tbody><tr v-for="(call,i) in selectedAction.http_calls" :key="i"><td>{{call.method}}</td><td>{{call.path}}</td><td>HTTP {{call.status}}</td></tr></tbody></table></div><details><summary>Données complètes de la preuve</summary><pre>{{JSON.stringify(selectedAction,null,2)}}</pre></details></div>
          <h2>Journal des actions terminées <WorkshopHelp topic="actions"/></h2><p class="muted">Cliquez une ligne pour examiner le résultat et les preuves. {{actions.total}} résultat(s) · tout l’historique est accessible par pages.</p><div class="table-wrap"><table><thead><tr><th>Acteur / date</th><th>Action et résultat</th><th>Utilisation <WorkshopHelp topic="usage"/></th><th>Statut <WorkshopHelp topic="failures"/></th></tr></thead><tbody><tr v-for="(a,i) in actions.items" :key="a.journalIndex" @click="showAction(a)" tabindex="0" @keydown.enter="showAction(a)"><td>#{{a.journalIndex+1}} · {{who(a.actor)}}<small>{{a.date}}</small></td><td>{{actionTitle(a)}}<small>{{actionOutcome(a,state)}}</small></td><td>{{actionEvidence(a).label}}</td><td>{{labels[a.status]||a.status}}<small v-if="a.model?.seconds!=null">IA : {{a.model.seconds}} s</small></td></tr></tbody></table></div>
        </section>
        <WorkshopBooks v-if="tab==='books'" :key="state.id" :state="state" :case-id="bookCaseId"/>
      </section>
      <section v-else class="panel empty"><h2>Faire utiliser Structura par des IA</h2><p>Créez une campagne, puis démarrez les agents. Ils réutilisent leurs comptes et contreparties, prennent les décisions prévues et utilisent le Pricer et le booking. Le journal conserve leurs erreurs et les réponses de l’application.</p></section>
    </div>
  </main>
</template>

<style scoped>
.consultation-controls{display:flex;flex-direction:column;align-items:flex-start;gap:8px;margin-top:12px}
.timeline-controls{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}.pagination{grid-column:1/-1;display:flex;gap:12px;align-items:center;justify-content:space-between;flex-wrap:wrap;font-size:12px}.campaign-state{margin:8px 0}.management>div{display:flex;gap:8px;flex-wrap:wrap}.management>summary{font-size:12px;padding:5px 0}.panel>.heading h2{margin-bottom:3px}.mobile-campaigns{display:none}
@media(max-width:760px){.campaign-sidebar{display:none}.campaign-sidebar.configuring,.campaign-sidebar.mobile-open{display:block;order:0}.mobile-campaigns{display:block}.timeline-controls{grid-template-columns:1fr 1fr}.timeline-controls>input{grid-column:1/-1}}

.workshop{padding:24px;max-width:1650px;margin:auto;width:100%;color:var(--text);height:100%;min-height:0;overflow:hidden;display:flex;flex-direction:column}.layout{flex:1;min-height:0;overflow:hidden}.campaign-sidebar,.content{overflow:auto;min-height:0}.forecast-result{padding:10px;background:var(--surface2);border-radius:6px}
.heading{display:flex;align-items:center;gap:16px;justify-content:space-between;flex-wrap:wrap}.heading h1{font-size:24px;font-weight:750}.heading p,.muted{color:var(--subtle);font-size:12px;margin:6px 0}
.notice{padding:8px 12px;background:#edf4fa;color:#244a68;border:1px solid #c5d8e8;border-radius:10px;font-size:12px;margin:12px 0}
.layout{display:grid;grid-template-columns:280px minmax(0,1fr);gap:20px}.layout.configuring{grid-template-columns:minmax(0,1fr)}.panel{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:18px}.panel h2{font-size:16px;font-weight:700;margin-bottom:12px}
.form{display:flex;flex-direction:column;gap:12px}.form label{font-size:12px;color:var(--text);display:flex;flex-direction:column;gap:5px}.form .check{flex-direction:row;align-items:center}.pair{display:grid;grid-template-columns:1fr 1fr;gap:8px}.input{width:100%}
.campaign{width:100%;text-align:left;padding:12px 8px;border-bottom:1px solid var(--border)}.campaign span,.campaign strong{display:block;font-size:12px}.campaign span{color:var(--subtle);margin-top:4px}.selected{box-shadow:inset 0 0 0 1px #5484a8;background:#edf4fa!important}
.content{display:flex;flex-direction:column;gap:18px;min-width:0}.controls,.tabs{display:flex;gap:10px;flex-wrap:wrap;margin:12px 0}.tabs button{padding:10px 12px;border:1px solid var(--border);border-radius:8px;font-size:12px}.badge{padding:8px;border-radius:8px;background:#edf4fa;color:#244a68;font-size:12px}
.tab-item{display:inline-flex;align-items:center}.issue-shortcut{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-top:12px}.issue-shortcut>span{font-size:11px;color:var(--subtle)}.field-label{display:inline-flex;align-items:center;gap:3px}.metric-link{display:block;font-size:22px;font-weight:700;margin:6px 0;color:var(--accent)}
.management{display:block;padding:6px 0;margin-top:6px;border-top:1px solid var(--border)}.management button{font-size:12px}.campaign small{display:block;color:var(--subtle);font-size:10px;margin-top:4px}
.metrics{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-top:18px}.metrics div{padding:12px;background:var(--surface2);border-radius:8px}.metrics>div>span,.metrics small{display:block;font-size:11px;color:var(--subtle)}.metrics strong{display:block;font-size:22px;margin:6px 0;font-variant-numeric:tabular-nums}
.actor-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}.actor{display:flex;align-items:start;flex-direction:column;gap:7px;text-align:left;min-width:0}.actor-heading{display:flex;align-items:center;gap:10px;width:100%;text-align:left}.actor-heading svg{width:38px;height:38px;flex-shrink:0}.actor-heading strong,.actor-heading small{display:block}.actor-heading strong{font-size:14px}.actor span,.actor a{font-size:12px}.actor small{font-size:11px;color:var(--subtle);line-height:1.5}.actor a,.proof-link{color:var(--accent);font-size:11px}.actor details{width:100%}.actor summary{font-size:10px;padding:4px 0}.actor details small{display:block}.last-action{font-size:12px;margin:4px 0;line-height:1.5}.actor.working{border-color:#6599c5;background:#edf4fb}.new-campaign{width:100%;margin:8px 0 16px}.action-proof{padding-bottom:18px;margin-bottom:18px;border-bottom:1px solid var(--border);scroll-margin-top:80px}.action-proof>p{font-size:13px;line-height:1.6;overflow-wrap:anywhere}.action-proof caption{text-align:left;font-weight:600;padding:14px 0;font-size:12px}.action-proof td{overflow-wrap:anywhere}
.feed{max-height:850px;overflow:auto}.feed article{padding:16px 0;border-bottom:1px solid var(--border)}.feed h3{margin:8px 0;font-weight:650}.feed p{white-space:pre-wrap;font-size:13px;line-height:1.6}.feed small{color:var(--subtle);font-size:11px}
pre{white-space:pre-wrap;overflow-wrap:anywhere;max-height:440px;overflow:auto;background:var(--surface2);padding:12px;font-size:11px;margin:10px 0}summary{cursor:pointer;font-size:12px;padding:12px 0;color:var(--accent)}.table-wrap{overflow:auto}table{width:100%;font-size:12px}th,td{text-align:left;border-bottom:1px solid var(--border);padding:12px 8px}td small{display:block;max-width:350px;color:var(--subtle);margin-top:5px}tbody tr{cursor:pointer}tbody tr:hover{background:var(--surface2)}img{max-width:100%;border-radius:8px}.error{color:#8b2332;background:#fcedef;padding:14px;border-radius:10px;margin:12px 0}.empty p{font-size:14px;line-height:1.8;color:var(--subtle)}
@media(max-width:1100px){.layout{grid-template-columns:240px minmax(0,1fr)}.actor-grid{grid-template-columns:repeat(2,1fr)}}@media(max-width:760px){.layout{grid-template-columns:1fr}.metrics{grid-template-columns:1fr}.workshop{padding:12px}.actor-grid{grid-template-columns:repeat(2,1fr)}}
</style>
