<script setup>
import { computed, ref, nextTick, onMounted, onUnmounted } from 'vue'
import { apiFetch } from '../utils/api'
import BackLink from '../components/ui/BackLink.vue'
import WorkshopMonitor from '../components/WorkshopMonitor.vue'
import WorkshopHelp from '../components/WorkshopHelp.vue'
import WorkshopIssues from '../components/WorkshopIssues.vue'
import { campaignIssues } from '../utils/workshopIssues'
import { workshopLabels, campaignRows, actionTitle, actionOutcome, actionEvidence, usageProof, money } from '../utils/workshopProgress'
import { previousLocalYearDate } from '../utils/workshopDate'
import { confirmer } from '../composables/useConfirm'

const base = '/api/agent-workshop'
const campaigns = ref([]), models = ref([]), state = ref(null), error = ref(''), busy = ref(false)
const tab = ref('overview'), actorFilter = ref(''), image = ref(''), selectedAction = ref(null)
const updatedAt = ref(0), now = ref(Date.now()), creating = ref(false)
const proofPanel = ref(null)
const notice = ref('')
const defaultConfig = () => ({ name: 'Une année avec Hector', model: 'qwen2.5-coder:7b', start_date: previousLocalYearDate(), months: 12, ticket: 10000000, target_volume: 100000000, max_turns: 800, timeout_seconds: 90, seed: 42, coaching: true, include_sg: true, contract_scenario: 'baseline' })
const config = ref(defaultConfig())
let timer, clockTimer, closed = false, epoch = 0, imageEpoch = 0
function receive(next) { state.value=next; updatedAt.value=Date.now() }
async function request(path = '', options = {}) {
  const res = await apiFetch(base + path, { ...options, headers: { ...(options.body ? {'Content-Type':'application/json'} : {}) } })
  if (!res.ok) { const body = await res.json().catch(()=>({})); throw new Error(typeof body.detail==='string' ? body.detail : JSON.stringify(body.detail || res.status)) }
  return res.json()
}
async function load() {
  try { campaigns.value = await request(); const data = await request('/models'); models.value = data.models; if (data.error) error.value = data.error }
  catch (e) { error.value = e.message }
}
async function refresh() {
  await load()
  if(state.value&&!busy.value){const id=state.value.id, version=epoch;try{const next=await request('/'+id);if(version===epoch&&state.value?.id===id)receive(next)}catch(e){error.value=e.message}}
}
async function select(id) { const version=++epoch; imageEpoch++; try { const next=await request('/'+id); if(version!==epoch)return; receive(next); error.value = ''; actorFilter.value = ''; selectedAction.value = null; tab.value='overview'; creating.value=false } catch(e) { error.value=e.message } }
async function create() {
  busy.value = true; error.value = ''; const version=++epoch
  try { const next=await request('', {method:'POST',body:JSON.stringify(config.value)}); if(version===epoch){receive(next);tab.value='overview';selectedAction.value=null;actorFilter.value='';creating.value=false} await load() }
  catch(e) { error.value=e.message } finally { busy.value=false }
}
async function command(action) {
  const id=state.value.id, version=++epoch
  busy.value=true; error.value=''
  try { const next=await request(`/${id}/${action}`,{method:'POST'}); if(version===epoch&&state.value?.id===id)receive(next); await load() }
  catch(e) { error.value=e.message } finally { busy.value=false }
}
function resetView() {
  tab.value='overview';actorFilter.value='';selectedAction.value=null;creating.value=false
  imageEpoch++;if(image.value)URL.revokeObjectURL(image.value);image.value=''
}
function resetFields() {
  config.value=defaultConfig()
  if(models.value.length&&!models.value.includes(config.value.model))config.value.model=models.value[0]
}
async function manage(action) {
  const current=state.value
  if(!current||busy.value||live.value)return
  const resetting=action==='reset'
  if(!await confirmer({
    titre:`${resetting ? 'Recommencer' : 'Supprimer'} « ${current.config.name} » ?`,
    message:resetting ? 'Cet essai sera remplacé par une campagne prête à démarrer, avec les mêmes paramètres. Les agents recréeront leurs comptes, contrats et deals depuis zéro.' : 'Cet essai sera retiré de la liste et de la vue. Les autres campagnes restent disponibles.',
    detail:`Essai ${current.id.slice(0,8)} · ${current.turns} décisions\nL’historique et les installations de cet essai seront rangés dans une sauvegarde locale. Vous pouvez exporter les preuves avant de continuer.`,
    confirmer:resetting ? 'Recommencer à zéro' : 'Supprimer la campagne',danger:true,
  }))return
  if(state.value?.id!==current.id)return
  const version=++epoch
  busy.value=true;error.value='';notice.value=''
  try {
    const next=await request(`/${current.id}${resetting ? '/reset' : ''}`,{method:resetting ? 'POST' : 'DELETE'})
    if(version!==epoch)return
    resetView()
    campaigns.value=campaigns.value.filter(c=>c.id!==current.id)
    if(resetting)receive(next);else state.value=null
    notice.value=resetting ? 'Campagne réinitialisée : 0 décision, comptes et books vierges. Cliquez sur « Démarrer les IA » pour rejouer.' : 'Campagne supprimée de la liste ; sauvegarde locale conservée.'
    await load()
    if(!resetting&&version===epoch&&campaigns.value.length)await select(campaigns.value[0].id)
  } catch(e) {error.value=e.message} finally {busy.value=false}
}
async function poll() {
  if (closed) return
  if(state.value && !busy.value) {
    const id=state.value.id, version=epoch
    try { const next=await request('/'+id); if(!closed&&!busy.value&&version===epoch&&state.value?.id===id) {receive(next);error.value=''} }
    catch(e) { error.value=e.message }
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
const live=computed(()=>state.value && state.value.controller_active!==false && ['RUNNING','PAUSING','PAUSED','STOPPING'].includes(state.value.status))
const messages=computed(()=>(state.value?.messages||[]).filter(m=>!actorFilter.value||m.from===actorFilter.value||m.to===actorFilter.value).slice().reverse())
const actions=computed(()=>(state.value?.actions||[]).filter(m=>!actorFilter.value||m.actor===actorFilter.value).slice().reverse())
const actors=computed(()=>Object.values(state.value?.actors||{}))
const issues=computed(()=>state.value ? campaignIssues(state.value) : [])
function openIssues() { actorFilter.value='';tab.value='incidents' }
const bankVolumes=computed(()=>{
  const result={}; let total=0
  for(const actor of actors.value.filter(a=>a.role==='bank')) { const amount=actor.deals.filter(d=>d.leg==='BANK_SELL').reduce((s,d)=>s+d.nominal,0); result[actor.id]=amount; total+=amount }
  return {result,total}
})
function who(id) { return state.value?.actors[id]?.name || id }
onMounted(async()=>{ clockTimer=setInterval(()=>{now.value=Date.now()},1000); const initialEpoch=epoch; await load(); if(epoch===initialEpoch&&!state.value&&campaigns.value.length) await select(campaigns.value[0].id); poll() })
onUnmounted(()=>{ closed=true; imageEpoch++; clearTimeout(timer); clearInterval(clockTimer); if(image.value) URL.revokeObjectURL(image.value) })
</script>

<template>
  <main class="workshop">
    <header class="heading"><BackLink fallback="/"/><div><h1>Recette par utilisateurs IA <WorkshopHelp topic="page"/></h1><p>Suivre les décisions, les actions dans Structura et leurs résultats.</p></div><button class="btn-secondary" @click="refresh">Actualiser</button></header>
    <p class="notice">Environnement de recette isolé · Marché synthétique identifié · Messages internes de simulation · Aucun objectif commercial n’impose un résultat.</p>
    <p v-if="error" role="alert" class="error">{{error}}</p>
    <p v-if="notice" role="status" class="notice">{{notice}}</p>
    <div class="layout">
      <aside class="panel">
        <h2>Campagnes <WorkshopHelp topic="campaigns"/></h2><button class="btn-secondary new-campaign" @click="creating=!creating">{{creating ? 'Fermer la configuration' : '+ Nouvelle campagne'}}</button>
        <form v-if="creating||!campaigns.length" class="form" @submit.prevent="create">
          <label><span class="field-label">Nom <WorkshopHelp topic="name"/></span><input aria-label="Nom" v-model="config.name" required maxlength="100" class="input"/></label>
          <label><span class="field-label">Modèle IA local <WorkshopHelp topic="model"/></span><select aria-label="Modèle IA local" v-model="config.model" class="input"><option v-for="model in models" :key="model">{{model}}</option></select></label>
          <p v-if="!models.length" class="muted">Ollama doit être démarré avec un modèle installé.</p>
          <div class="pair"><label><span class="field-label">Date initiale <WorkshopHelp topic="start"/></span><input aria-label="Date initiale" v-model="config.start_date" type="date" required class="input"/></label><label><span class="field-label">Mois <WorkshopHelp topic="months"/></span><input aria-label="Mois" v-model.number="config.months" type="number" min="1" max="24" required class="input"/></label></div>
          <label><span class="field-label">Ticket par besoin (€) <WorkshopHelp topic="ticket"/></span><input aria-label="Ticket par besoin (€)" v-model.number="config.ticket" type="number" min="1" required class="input"/></label>
          <label><span class="field-label">Objectif Hector (€) <WorkshopHelp topic="target"/></span><input aria-label="Objectif Hector (€)" v-model.number="config.target_volume" type="number" min="1" required class="input"/></label>
          <div class="pair"><label><span class="field-label">Décisions maximum <WorkshopHelp topic="decisions"/></span><input aria-label="Décisions maximum" v-model.number="config.max_turns" type="number" min="10" max="5000" class="input"/></label><label><span class="field-label">Délai IA (s) <WorkshopHelp topic="timeout"/></span><input aria-label="Délai IA (s)" v-model.number="config.timeout_seconds" type="number" min="10" max="180" class="input"/></label></div>
          <label><span class="field-label">Graine du scénario <WorkshopHelp topic="seed"/></span><input aria-label="Graine du scénario" v-model.number="config.seed" type="number" min="0" max="2147483647" class="input"/></label>
          <label><span class="field-label">Configuration contractuelle <WorkshopHelp topic="contracts"/></span><select aria-label="Configuration contractuelle" v-model="config.contract_scenario" class="input"><option value="baseline">BNP / SG complets, CA incomplet</option><option value="all_complete">Toutes les banques documentées</option><option value="random">Tirage reproductible par banque</option></select></label>
          <label class="check"><input aria-label="Inclure Société Générale" v-model="config.include_sg" type="checkbox"/> Inclure Société Générale <WorkshopHelp topic="sg"/></label>
          <label class="check"><input aria-label="Conseils d’Achille après erreur" v-model="config.coaching" type="checkbox"/> Conseils d’Achille après erreur <WorkshopHelp topic="coaching"/></label>
          <button class="btn-primary" :disabled="busy||!models.length">Créer la campagne</button>
          <button type="button" class="btn-secondary" :disabled="busy" @click="resetFields">Réinitialiser les champs</button>
        </form>
        <h2 class="mt-6">Campagnes conservées ({{rows.length}})</h2>
        <p class="muted">Sélectionnez un essai pour le recommencer ou le supprimer.</p>
        <button v-for="c in rows" :key="c.id" class="campaign" :disabled="busy" :class="{selected:state?.id===c.id}" @click="select(c.id)"><strong>{{c.config.name}}</strong><span>{{c.displayStatus||labels[c.status]||c.status}} · {{c.turns}} décisions</span><small>Essai {{c.id.slice(0,8)}}</small></button>
      </aside>
      <section v-if="state" class="content">
        <div class="panel">
          <div class="heading"><div><h2>{{state.config.name}}</h2><p>{{state.controller_active===false&&['RUNNING','PAUSED','PAUSING','STOPPING'].includes(state.status) ? 'Exécution non confirmée' : labels[state.status]||state.status}} · {{state.config.model}}</p></div><span class="badge">{{state.business_date}} · {{state.month>=state.config.months?'Revue finale':'mois '+(state.month+1)+' / '+state.config.months}}</span></div>
          <div class="controls"><button v-if="!live&&state.status!=='COMPLETED'" class="btn-primary" :disabled="busy" @click="command('start')">Démarrer les IA</button><button v-if="live&&state.status==='RUNNING'" class="btn-secondary" :disabled="busy" @click="command('pause')">Pause</button><button v-if="live&&state.status==='PAUSED'" class="btn-primary" :disabled="busy" @click="command('resume')">Reprendre</button><button v-if="live" class="btn-secondary" :disabled="busy" @click="command('stop')">Arrêter</button><button class="btn-secondary" @click="download">Exporter les preuves</button><span class="muted">Commandes <WorkshopHelp topic="controls"/> · Export <WorkshopHelp topic="export"/></span></div>
          <p class="muted">{{state.turns}} décisions IA · {{state.usage.model_calls}} appels au modèle · {{(state.actions||[]).length}} résultats consignés <WorkshopHelp topic="decisions"/></p>
          <div class="management"><button class="btn-secondary" :disabled="busy" @click="resetView">Réinitialiser la vue</button><button class="btn-secondary" :disabled="busy||live" @click="manage('reset')">Recommencer la campagne</button><button class="btn-danger" :disabled="busy||live" @click="manage('delete')">Supprimer la campagne</button><WorkshopHelp topic="manage"/></div>
          <p v-if="live" class="muted">Pour recommencer ou supprimer cet essai, cliquez sur « Arrêter » puis attendez la fermeture des installations.</p>
          <div class="issue-shortcut"><button class="btn-secondary" @click="openIssues">Voir les problèmes ({{issues.length}})</button><span>Signalements à diagnostiquer, pas des bugs confirmés <WorkshopHelp topic="issues"/></span></div>
        </div>
        <nav class="tabs"><span v-for="[id,label] in [['overview','Vue d’ensemble'],['messages','Conversations'],['actions','Actions et preuves'],['books','Books et risques'],['incidents','Bugs et améliorations']]" :key="id" class="tab-item"><button :class="{selected:tab===id}" @click="tab=id">{{label}}<template v-if="id==='incidents'"> ({{issues.length}})</template></button><WorkshopHelp :topic="id==='incidents' ? 'incidents' : id"/></span><button v-if="actorFilter" @click="actorFilter=''">Tous les acteurs ×</button></nav>
        <WorkshopIssues v-if="tab==='incidents'" :key="state.id" :state="state" :actor-filter="actorFilter" @inspect="inspect"/>
        <WorkshopMonitor v-if="tab==='overview'" :key="state.id" :state="state" :now="now" :updated-at="updatedAt" :show-history="true" :actor-filter="actorFilter" @inspect="inspect">
          <template #metrics><div class="metrics"><div><span>Volume clients rapproché <WorkshopHelp topic="volume"/></span><strong>{{state.commercial_volume>=1000000 ? new Intl.NumberFormat('fr-FR',{maximumFractionDigits:2}).format(state.commercial_volume/1000000)+' M€' : money(state.commercial_volume)}}</strong><small>Objectif {{money(state.config.target_volume)}}</small></div><div><span>Opérations rapprochées <WorkshopHelp topic="matched"/></span><strong>{{state.book_checks?.filter(c=>c.status==='COMPLETE').length||0}}</strong><small>4 écritures par opération · {{Object.keys(state.cases).length}} besoins</small></div><div><span>Points à examiner <WorkshopHelp topic="issues"/></span><button class="metric-link" :aria-label="'Voir les problèmes ('+issues.length+')'" @click="openIssues">{{issues.length}} →</button><small>Ouvrir les signalements</small></div></div></template>
        </WorkshopMonitor>
        <div v-if="tab==='overview'" class="actor-grid">
          <article v-for="actor in actors" :key="actor.id" class="panel actor" :class="{selected:actorFilter===actor.id,working:state.activity?.actor===actor.id&&state.status==='RUNNING'&&state.controller_active!==false}">
            <button class="actor-heading" :aria-label="'Filtrer '+actor.name" :aria-pressed="actorFilter===actor.id" @click="actorFilter=actorFilter===actor.id?'':actor.id">
            <svg viewBox="0 0 64 64" width="56" height="56" aria-hidden="true"><circle cx="32" cy="32" r="31" :fill="actor.colour"/><path d="M12 58 Q15 38 32 38 Q49 38 52 58" fill="#dce5ed"/><ellipse cx="32" cy="26" rx="12" ry="15" fill="#e9b890"/><path d="M20 25 Q15 8 32 9 Q48 7 45 25 L40 17 L24 18Z" fill="#263143"/><circle cx="28" cy="26" r="1.3" fill="#263143"/><circle cx="37" cy="26" r="1.3" fill="#263143"/><path d="M29 33 Q33 36 37 32" fill="none" stroke="#9d6451" stroke-width="1.5"/><path v-if="actor.id==='achille'" d="M22 25h8v5h-8zM34 25h8v5h-8zM30 27h4" stroke="#1a263c" fill="none"/></svg>
            <span><strong>{{actor.name}}</strong><small>{{actorStatus(actor)}}</small></span></button>
            <p v-if="lastAction(actor.id)" class="last-action">{{actionTitle(lastAction(actor.id))}}</p><p v-else class="last-action">Aucune action terminée</p>
            <small>{{usageProof(state,actor.id).screens}} écrans · {{usageProof(state,actor.id).apiActions}} actions API · {{actor.deals.length}} deals <WorkshopHelp topic="actors"/></small>
            <button v-if="lastAction(actor.id)" class="proof-link" @click="inspect(lastAction(actor.id))">Voir la dernière preuve →</button>
            <details><summary>Objectif et part de marché</summary><small>{{actor.goal}}</small><small v-if="actor.role==='bank'">Part traitée : {{bankVolumes.total ? (100*bankVolumes.result[actor.id]/bankVolumes.total).toFixed(1):'0'}} %</small></details>
            <a v-if="actor.online" :href="actor.url+'/#/login'" target="_blank" rel="noopener" @click.stop>Ouvrir son Structura ↗</a><span v-else class="muted">{{actor.role==='supervisor'?'Supervision':'Instance fermée'}}</span>
          </article>
        </div>
        <section v-if="tab==='messages'" class="panel feed"><p v-if="!messages.length" class="muted">Les échanges apparaîtront lorsque les IA agiront.</p><article v-for="m in messages.slice(0,120)" :key="m.id"><div class="heading"><strong>{{who(m.from)}} → {{who(m.to)}}</strong><small>{{m.date}} {{m.case_id}}</small></div><h3>{{m.subject}}</h3><p>{{m.body}}</p><details v-if="m.attachment"><summary>Pièce jointe structurée</summary><pre>{{JSON.stringify(m.attachment,null,2)}}</pre></details></article></section>
        <section v-if="tab==='actions'" ref="proofPanel" class="panel">
          <div v-if="selectedAction" class="action-proof"><h2>{{who(selectedAction.actor)}} · {{actionTitle(selectedAction)}}</h2><p>{{actionOutcome(selectedAction,state)}}</p><p class="muted">{{selectedAction.date}} · {{labels[selectedAction.status]||selectedAction.status}} · {{actionEvidence(selectedAction).label}} · {{actionEvidence(selectedAction).detail}}</p><p v-if="selectedAction.reason">Décision de l’IA : {{selectedAction.reason}}</p><img v-if="image" :src="image" alt="Capture de l’écran réellement utilisé"/><p v-else-if="actionEvidence(selectedAction).kind==='api'" class="muted">Cette action a utilisé les API de Structura. Aucune capture de navigation n’est associée.</p><div v-if="selectedAction.http_calls?.length" class="table-wrap"><table><caption>Réponses de Structura dans l’installation de {{who(selectedAction.actor)}}</caption><thead><tr><th>Méthode</th><th>Fonction appelée</th><th>Réponse <WorkshopHelp topic="http"/></th></tr></thead><tbody><tr v-for="(call,i) in selectedAction.http_calls" :key="i"><td>{{call.method}}</td><td>{{call.path}}</td><td>HTTP {{call.status}}</td></tr></tbody></table></div><details><summary>Données complètes de la preuve</summary><pre>{{JSON.stringify(selectedAction,null,2)}}</pre></details></div>
          <h2>Journal des actions terminées <WorkshopHelp topic="actions"/></h2><p class="muted">Cliquez une ligne pour examiner le résultat et les preuves. {{actions.length>160 ? 'Les 160 dernières actions sont affichées ; l’export contient le journal complet.' : ''}}</p><div class="table-wrap"><table><thead><tr><th>Acteur / date</th><th>Action et résultat</th><th>Utilisation <WorkshopHelp topic="usage"/></th><th>Statut <WorkshopHelp topic="failures"/></th></tr></thead><tbody><tr v-for="(a,i) in actions.slice(0,160)" :key="i" @click="showAction(a)" tabindex="0" @keydown.enter="showAction(a)"><td>{{who(a.actor)}}<small>{{a.date}}</small></td><td>{{actionTitle(a)}}<small>{{actionOutcome(a,state)}}</small></td><td>{{actionEvidence(a).label}}</td><td>{{labels[a.status]||a.status}}<small v-if="a.model?.seconds!=null">IA : {{a.model.seconds}} s</small></td></tr></tbody></table></div>
        </section>
        <section v-if="tab==='books'" class="panel"><h2>Rapprochement des opérations <WorkshopHelp topic="books"/></h2><p class="muted">La banque vend à Hector ; Hector achète puis vend au client. Chaque écriture provient de son instance.</p><div class="table-wrap"><table><thead><tr><th>Besoin</th><th>Contrôle <WorkshopHelp topic="matched"/></th><th>Écritures <WorkshopHelp topic="booking"/></th><th>Volume client <WorkshopHelp topic="volume"/></th></tr></thead><tbody><tr v-for="c in state.book_checks" :key="c.case_id"><td>{{c.case_id}}</td><td>{{labels[c.status]||c.status}}</td><td>{{c.legs}}</td><td>{{money(c.client_volume)}}</td></tr></tbody></table></div><details v-for="a in actors.filter(a=>a.role!=='supervisor')" :key="a.id"><summary>{{a.name}} · {{a.deals.length}} exécutions · {{Object.keys(a.relations).length}} relations</summary><p>Le porteur d’une note supporte le risque de son émetteur. Une émission ne constitue pas à elle seule une exposition OTC soumise au CSA.</p><pre>{{JSON.stringify({relations:a.relations,deals:a.deals,review:a.last_review},null,2)}}</pre></details><h3>Couverture effectivement observée <WorkshopHelp topic="coverage"/></h3><pre>{{JSON.stringify(state.coverage,null,2)}}</pre></section>
      </section>
      <section v-else class="panel empty"><h2>Faire utiliser Structura par des IA</h2><p>Créez une campagne, puis démarrez les agents. Ils ouvrent leurs comptes, préparent leurs relations, dialoguent et utilisent le Pricer et le booking. Le journal conserve leurs erreurs et les réponses de l’application.</p></section>
    </div>
  </main>
</template>

<style scoped>
.workshop{padding:24px;max-width:1650px;margin:auto;width:100%;color:var(--text)}
.heading{display:flex;align-items:center;gap:16px;justify-content:space-between;flex-wrap:wrap}.heading h1{font-size:24px;font-weight:750}.heading p,.muted{color:var(--subtle);font-size:12px;margin:6px 0}
.notice{padding:12px 16px;background:#edf4fa;color:#244a68;border:1px solid #c5d8e8;border-radius:10px;font-size:12px;margin:20px 0}
.layout{display:grid;grid-template-columns:280px minmax(0,1fr);gap:20px}.panel{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:18px}.panel h2{font-size:16px;font-weight:700;margin-bottom:12px}
.form{display:flex;flex-direction:column;gap:12px}.form label{font-size:12px;color:var(--text);display:flex;flex-direction:column;gap:5px}.form .check{flex-direction:row;align-items:center}.pair{display:grid;grid-template-columns:1fr 1fr;gap:8px}.input{width:100%}
.campaign{width:100%;text-align:left;padding:12px 8px;border-bottom:1px solid var(--border)}.campaign span,.campaign strong{display:block;font-size:12px}.campaign span{color:var(--subtle);margin-top:4px}.selected{box-shadow:inset 0 0 0 1px #5484a8;background:#edf4fa!important}
.content{display:flex;flex-direction:column;gap:18px;min-width:0}.controls,.tabs{display:flex;gap:10px;flex-wrap:wrap;margin:12px 0}.tabs button{padding:10px 12px;border:1px solid var(--border);border-radius:8px;font-size:12px}.badge{padding:8px;border-radius:8px;background:#edf4fa;color:#244a68;font-size:12px}
.tab-item{display:inline-flex;align-items:center}.issue-shortcut{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-top:12px}.issue-shortcut>span{font-size:11px;color:var(--subtle)}.field-label{display:inline-flex;align-items:center;gap:3px}.metric-link{display:block;font-size:22px;font-weight:700;margin:6px 0;color:var(--accent)}
.management{display:flex;align-items:center;gap:8px;flex-wrap:wrap;padding:12px 0;margin-top:10px;border-top:1px solid var(--border)}.management button{font-size:12px}.campaign small{display:block;color:var(--subtle);font-size:10px;margin-top:4px}
.metrics{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-top:18px}.metrics div{padding:12px;background:var(--surface2);border-radius:8px}.metrics>div>span,.metrics small{display:block;font-size:11px;color:var(--subtle)}.metrics strong{display:block;font-size:22px;margin:6px 0;font-variant-numeric:tabular-nums}
.actor-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}.actor{display:flex;align-items:start;flex-direction:column;gap:7px;text-align:left;min-width:0}.actor-heading{display:flex;align-items:center;gap:10px;width:100%;text-align:left}.actor-heading svg{width:38px;height:38px;flex-shrink:0}.actor-heading strong,.actor-heading small{display:block}.actor-heading strong{font-size:14px}.actor span,.actor a{font-size:12px}.actor small{font-size:11px;color:var(--subtle);line-height:1.5}.actor a,.proof-link{color:var(--accent);font-size:11px}.actor details{width:100%}.actor summary{font-size:10px;padding:4px 0}.actor details small{display:block}.last-action{font-size:12px;margin:4px 0;line-height:1.5}.actor.working{border-color:#6599c5;background:#edf4fb}.new-campaign{width:100%;margin:8px 0 16px}.action-proof{padding-bottom:18px;margin-bottom:18px;border-bottom:1px solid var(--border);scroll-margin-top:80px}.action-proof>p{font-size:13px;line-height:1.6;overflow-wrap:anywhere}.action-proof caption{text-align:left;font-weight:600;padding:14px 0;font-size:12px}.action-proof td{overflow-wrap:anywhere}
.feed{max-height:850px;overflow:auto}.feed article{padding:16px 0;border-bottom:1px solid var(--border)}.feed h3{margin:8px 0;font-weight:650}.feed p{white-space:pre-wrap;font-size:13px;line-height:1.6}.feed small{color:var(--subtle);font-size:11px}
pre{white-space:pre-wrap;overflow-wrap:anywhere;max-height:440px;overflow:auto;background:var(--surface2);padding:12px;font-size:11px;margin:10px 0}summary{cursor:pointer;font-size:12px;padding:12px 0;color:var(--accent)}.table-wrap{overflow:auto}table{width:100%;font-size:12px}th,td{text-align:left;border-bottom:1px solid var(--border);padding:12px 8px}td small{display:block;max-width:350px;color:var(--subtle);margin-top:5px}tbody tr{cursor:pointer}tbody tr:hover{background:var(--surface2)}img{max-width:100%;border-radius:8px}.error{color:#8b2332;background:#fcedef;padding:14px;border-radius:10px;margin:12px 0}.empty p{font-size:14px;line-height:1.8;color:var(--subtle)}
@media(max-width:1100px){.layout{grid-template-columns:240px minmax(0,1fr)}.actor-grid{grid-template-columns:repeat(2,1fr)}}@media(max-width:760px){.layout{grid-template-columns:1fr}.metrics{grid-template-columns:1fr}.workshop{padding:12px}.actor-grid{grid-template-columns:repeat(2,1fr)}}
</style>
