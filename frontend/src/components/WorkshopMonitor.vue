<script setup>
import { computed, ref } from 'vue'
import WorkshopHelp from './WorkshopHelp.vue'
import { stepHelp } from '../utils/workshopHelp'
import { actorName, actionTitle, actionOutcome, actionEvidence, usageProof, liveSummary, workflowSteps, workshopLabels } from '../utils/workshopProgress'

const props = defineProps({state:{type:Object,required:true}, now:{type:Number,required:true}, updatedAt:{type:Number,default:0}, showHistory:Boolean, actorFilter:{type:String,default:''}})
const emit = defineEmits(['inspect'])
const caseId = ref('')
const showWaits = ref(false)
const summary = computed(()=>liveSummary(props.state))
const proof = computed(()=>usageProof(props.state))
const workflow = computed(()=>workflowSteps(props.state,caseId.value))
const cases = computed(()=>Object.values(props.state.cases || {}).slice().reverse())
const recent = computed(()=>(props.state.actions || []).map((action,index)=>({...action,index})).filter(a=>(!props.actorFilter || a.actor===props.actorFilter)&&(showWaits.value||a.tool!=='wait')).reverse().slice(0,12))
const activity = computed(()=>props.state.activity)
const elapsed = computed(()=>activity.value?.started_at ? Math.max(0,Math.floor((props.now-Date.parse(activity.value.started_at))/1000)) : null)
const age = computed(()=>props.updatedAt ? Math.max(0,Math.floor((props.now-props.updatedAt)/1000)) : null)
const stale = computed(()=>age.value!=null && age.value>15)
const progress = computed(()=>Math.min(props.state.month || 0,props.state.config.months))
const request = computed(()=>activity.value?.request)
</script>

<template>
  <section class="panel monitor" aria-label="Suivi de la simulation">
    <div class="monitor-heading"><strong>Maintenant <WorkshopHelp topic="now"/></strong><span :class="{stale}">{{stale ? 'Suivi sans nouvelle réponse depuis '+age+' s' : 'Suivi actualisé toutes les 3 s'}}<template v-if="!stale && age!=null"> · reçu il y a {{age}} s</template></span></div>
    <div class="current" :class="{running:summary.active && !stale}">
      <span class="status-dot" aria-hidden="true"></span><div><h3>{{summary.title}}</h3><p>{{summary.detail}}</p>
        <p v-if="stale" class="stale">L’état affiché est la dernière réponse reçue ; l’activité actuelle ne peut pas être confirmée.</p>
        <p v-if="summary.active && activity?.phase==='THINKING' && activity.tasks?.length" class="task">Tâche proposée au modèle : {{activity.tasks[0]}}</p>
        <p v-if="summary.active && activity?.phase==='EXECUTING'" class="task"><template v-if="request">{{request.status==='PENDING' ? 'Structura traite' : 'Structura a répondu à'}} : <code>{{request.method}} {{request.path}}</code><template v-if="request.status!=='PENDING'"> · HTTP {{request.status}}</template></template><template v-else-if="['register','browser'].includes(activity.tool)">Action dans le navigateur de l’agent · preuve disponible après exécution</template><template v-else-if="['mail','request','client_accept','wait','report'].includes(activity.tool)">Échange interne ou attente · aucun deal booké par ce seul message</template><template v-else>Décision en cours d’exécution · attente du premier résultat de Structura</template></p>
      </div><span v-if="summary.active && elapsed!=null" class="elapsed">{{elapsed}} s</span>
    </div>
    <div class="time-row"><span><strong>Date du jeu : {{state.business_date}}</strong> · {{progress}} / {{state.config.months}} mois parcourus <WorkshopHelp topic="clock"/></span><span>{{summary.active ? 'Temps du jeu suspendu pendant le travail' : 'Temps du jeu arrêté'}}</span></div>
    <progress :value="progress" :max="state.config.months" aria-label="Mois parcourus"></progress>
    <slot name="metrics"></slot>
    <div class="proof-summary"><strong>Utilisation de Structura constatée <WorkshopHelp topic="usage"/></strong><div><span>{{proof.screens}} actions par écran</span><span>{{proof.apiActions}} actions par API · {{proof.calls}} appels HTTP</span><span>{{proof.messages}} échanges internes</span><span v-if="proof.failures" class="stale">{{proof.failures}} échecs techniques <WorkshopHelp topic="failures"/></span></div><p>Un message entre agents ne prouve pas un booking. Les actions par API utilisent Structura, sans navigation dans ses formulaires. Cliquez sur une action pour examiner sa preuve.</p></div>
    <div class="monitor-heading workflow-heading"><strong>Parcours métier {{workflow.caseId ? '· '+workflow.caseId : ''}} <WorkshopHelp topic="workflow"/></strong><label v-if="cases.length>1">Dossier <select v-model="caseId" aria-label="Dossier à suivre"><option value="">Dossier courant / dernier dossier</option><option v-for="c in cases" :key="c.id" :value="c.id">{{c.id}}</option></select></label></div>
    <ol class="workflow"><li v-for="(step,i) in workflow.steps" :key="step.title" :class="step.state"><span class="step-number">{{step.state==='done' ? '✓' : step.state==='skipped' ? '—' : i+1}}</span><div><strong>{{step.title}} <WorkshopHelp :topic="stepHelp[step.title]"/></strong><p>{{step.detail}}</p></div></li></ol>
    <p class="legend">✓ Réalisé · bleu : prochaine étape à compléter · orange : documentation incomplète ou écart · — : étape sans objet après refus. Le suivi de vie porte sur l’ensemble des books.</p>
    <template v-if="showHistory">
      <div class="monitor-heading history-title"><h3>Ce qui vient de se passer <small v-if="actorFilter">· {{actorName(state,actorFilter)}}</small></h3><label><input v-model="showWaits" type="checkbox"/> Inclure les attentes</label></div>
      <p v-if="!recent.length" class="empty">Aucune action terminée. Le bloc « Maintenant » indique la préparation ou la décision en cours.</p>
      <ol class="history"><li v-for="a in recent" :key="a.index"><button @click="emit('inspect',a)"><span class="action-number">#{{a.index+1}}</span><span class="history-body"><strong>{{actorName(state,a.actor)}} · {{actionTitle(a)}}</strong><span>{{actionOutcome(a,state)}}</span><small>{{a.date}} · {{workshopLabels[a.status] || a.status}}<template v-if="a.duration_seconds!=null"> · {{a.duration_seconds.toFixed(1)}} s</template></small></span><span class="channel" :class="actionEvidence(a).kind">{{actionEvidence(a).label}}<small>Voir la preuve →</small></span></button></li></ol>
    </template>
  </section>
</template>

<style scoped>
.monitor{padding:20px;min-width:0}.monitor-heading{display:flex;align-items:center;justify-content:space-between;gap:12px;font-size:13px}.monitor-heading>span{font-size:11px;color:var(--subtle)}.current{display:flex;gap:12px;background:var(--surface2);border:1px solid var(--border);border-radius:10px;padding:16px;margin:14px 0}.current.running{background:#edf4fb;border-color:#acc9e5}.status-dot{width:9px;height:9px;border-radius:50%;background:#7b8490;flex-shrink:0;margin-top:5px}.running .status-dot{background:#2468a3}.current h3{font-size:16px;margin:0 0 6px}.current p{font-size:12px;line-height:1.65;margin:4px 0;color:var(--subtle)}.current .task{color:var(--text);overflow-wrap:anywhere}.elapsed{margin-left:auto;flex-shrink:0;font-variant-numeric:tabular-nums;font-size:13px}.time-row{display:flex;flex-wrap:wrap;justify-content:space-between;gap:8px;font-size:12px}.time-row>span:last-child{color:var(--subtle);font-size:11px}progress{width:100%;height:6px;accent-color:#2468a3;margin-top:10px}.proof-summary{margin-top:18px;padding:14px 0;border-top:1px solid var(--border);border-bottom:1px solid var(--border);font-size:12px}.proof-summary>div{display:flex;flex-wrap:wrap;gap:8px;margin-top:9px}.proof-summary>div>span{background:var(--surface2);padding:6px 9px;border-radius:5px}.proof-summary p,.legend{color:var(--subtle);font-size:11px;line-height:1.6;margin:9px 0 0}.workflow-heading{margin:18px 0 12px}.workflow-heading label{font-size:11px;color:var(--subtle)}select{border:1px solid var(--border);border-radius:5px;padding:5px;background:var(--surface)}.workflow{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px;padding:0;list-style:none}.workflow li{display:flex;gap:8px;padding:10px;background:var(--surface2);border:1px solid var(--border);border-radius:7px;font-size:11px;min-width:0}.step-number{display:grid;place-items:center;width:20px;height:20px;flex-shrink:0;border-radius:50%;background:var(--surface);font-size:11px}.workflow strong{font-size:12px}.workflow p{font-size:11px;line-height:1.5;margin:5px 0 0;color:var(--subtle)}.workflow .done .step-number{background:#d5e9df;color:#1c6346}.workflow .current{background:#edf4fb;border-color:#8eb9df;margin:0}.workflow .warning{background:#fff6e7;border-color:#e4c58d}.history-title{font-size:14px;margin:22px 0 12px}.history-title small{font-size:12px;color:var(--subtle)}.history{list-style:none;padding:0;margin:0}.history li+li{border-top:1px solid var(--border)}.history button{width:100%;display:flex;gap:12px;text-align:left;padding:12px 0;border-radius:5px}.history button:hover{background:var(--surface2)}.action-number{font-size:11px;color:var(--subtle);min-width:34px;padding-top:2px}.history-body{display:flex;flex-direction:column;gap:5px;min-width:0;flex:1;font-size:12px;overflow-wrap:anywhere}.history-body strong{font-size:13px}.history-body small{color:var(--subtle);font-size:11px}.channel{align-self:start;font-size:10px;background:#eaf1f8;color:#23557d;border-radius:5px;padding:6px 9px;white-space:nowrap}.channel small{display:block;margin-top:5px}.channel.message,.channel.wait,.channel.report{background:var(--surface2);color:var(--subtle)}.empty{font-size:12px;color:var(--subtle)}.stale{color:#97571c!important}code{font-size:11px;overflow-wrap:anywhere}
@media(max-width:1100px){.workflow{grid-template-columns:repeat(3,minmax(0,1fr))}}@media(max-width:760px){.monitor{padding:14px}.monitor-heading{align-items:start;flex-direction:column}.workflow{grid-template-columns:repeat(2,minmax(0,1fr))}.current{padding:12px}.current h3{font-size:14px}.history button{flex-wrap:wrap;gap:8px}.history .channel{margin-left:42px}.history-body{flex-basis:calc(100% - 42px)}.workflow-heading select{max-width:100%}}
</style>
