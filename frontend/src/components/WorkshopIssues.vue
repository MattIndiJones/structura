<script setup>
import { computed, ref } from 'vue'
import WorkshopHelp from './WorkshopHelp.vue'
import { campaignIssues, issueCategories, issueReport } from '../utils/workshopIssues'
import { actorName, actionTitle } from '../utils/workshopProgress'
const props=defineProps({state:{type:Object,required:true},actorFilter:{type:String,default:''}})
const emit=defineEmits(['inspect'])
const category=ref('all')
const rows=computed(()=>campaignIssues(props.state))
const counts=computed(()=>Object.fromEntries(Object.keys(issueCategories).map(key=>[key,rows.value.filter(r=>r.category===key).length])))
const filtered=computed(()=>rows.value.filter(row=>(category.value==='all'||row.category===category.value)&&(!props.actorFilter||row.actor===props.actorFilter)).slice().reverse())
function download() {
  const url=URL.createObjectURL(new Blob([issueReport(props.state,rows.value)],{type:'text/plain;charset=utf-8'}))
  const link=document.createElement('a');link.href=url;link.download=`signalements-${props.state.id.slice(0,8)}.txt`;link.click();URL.revokeObjectURL(url)
}
</script>
<template>
  <section class="panel issue-register" aria-label="Registre des problèmes">
    <div class="issue-heading"><div><h2>Problèmes à diagnostiquer et améliorations <WorkshopHelp topic="incidents"/></h2><p>{{rows.length}} points conservés dans cette campagne. Aucun de ces points n’est automatiquement un bug confirmé.</p></div><button class="btn-secondary" :disabled="!rows.length" @click="download">Télécharger les signalements</button></div>
    <p class="issue-notice">Pour décider quoi corriger dans Structura, ouvrir une fiche puis examiner sa preuve. Une mauvaise décision de l’IA, un contrat volontairement incomplet ou un refus de contrôle ne démontrent pas un défaut du code.</p>
    <div class="issue-categories"><button v-for="(label,key) in issueCategories" :key="key" :class="{selected:category===key}" :aria-pressed="category===key" @click="category=category===key?'all':key"><strong>{{counts[key]}}</strong><span>{{label}}</span></button></div>
    <div class="issue-toolbar"><label>Afficher <select v-model="category" aria-label="Catégorie de problème"><option value="all">Tous les points</option><option v-for="(label,key) in issueCategories" :key="key" :value="key">{{label}}</option></select></label><span>{{filtered.length}} fiche(s) affichée(s)<template v-if="actorFilter"> · {{actorName(state,actorFilter)}}</template></span></div>
    <p v-if="!filtered.length" class="empty">{{rows.length ? 'Aucun point dans ce filtre. Choisissez « Tous les points » ou retirez le filtre acteur.' : 'Aucun problème remonté dans cette campagne. Les fonctions non exercées restent à tester.'}}</p>
    <article v-for="row in filtered" :key="row.id" class="issue-card" :data-issue="row.category">
      <div class="issue-heading"><h3>Point {{row.number}} · {{actorName(state,row.actor)}}</h3><span class="issue-tag">{{issueCategories[row.category]}}</span></div>
      <p class="issue-qualification">{{row.qualification}} · {{row.source==='AGENT' ? 'Signalement de l’IA' : row.source==='ACTION' ? 'Échec observé dans le journal' : 'Constat du contrôleur'}} · date du jeu {{row.date}}</p>
      <p class="issue-summary">{{row.summary}}</p>
      <dl><dt>À vérifier avant de corriger</dt><dd>{{row.next}}</dd><template v-if="row.action"><dt>Action concernée</dt><dd>{{actionTitle(row.action)}} · n° {{row.actionIndex+1}}<template v-if="row.action.args?.case_id"> · {{row.action.args.case_id}}</template></dd><dt>Décision de l’IA</dt><dd>{{row.action.reason}}</dd></template></dl>
      <details open><summary>Message original observé</summary><pre>{{row.description}}</pre></details>
      <button v-if="row.action" class="btn-secondary" @click="emit('inspect',row.action)">Voir l’action et sa preuve</button><p v-else class="muted">Aucune action liée avec certitude ; examiner les échanges et les actions précédentes.</p>
    </article>
  </section>
</template>
<style scoped>
.issue-register{min-width:0}.issue-heading{display:flex;justify-content:space-between;align-items:start;gap:14px;flex-wrap:wrap}.issue-heading h2{font-size:16px;font-weight:700}.issue-heading p,.issue-toolbar{font-size:12px;color:var(--subtle);line-height:1.6}.issue-heading h3{font-size:14px;font-weight:650}.issue-notice{font-size:12px;line-height:1.7;padding:12px;background:#edf4fb;border-radius:8px;margin:14px 0}.issue-categories{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px}.issue-categories button{display:flex;align-items:center;gap:12px;border:1px solid var(--border);border-radius:8px;padding:12px;text-align:left;background:var(--surface2)}.issue-categories strong{font-size:22px;font-variant-numeric:tabular-nums}.issue-categories span{font-size:12px}.issue-categories .selected{border-color:#6799c5;background:#edf4fb}.issue-toolbar{display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;margin:18px 0}.issue-toolbar select{border:1px solid var(--border);padding:7px;border-radius:6px;background:var(--surface);max-width:100%}.issue-card{border:1px solid var(--border);border-radius:10px;padding:16px;margin-top:12px}.issue-tag{font-size:11px;padding:5px 8px;border-radius:5px;background:#fff3df;color:#81521f}.issue-qualification{font-size:11px;color:var(--subtle);margin:8px 0}.issue-summary{font-size:14px;line-height:1.6;margin:12px 0}.issue-card dl{font-size:12px;line-height:1.7}.issue-card dt{font-weight:650;margin-top:10px}.issue-card dd{color:var(--subtle);margin:3px 0 0;overflow-wrap:anywhere}.issue-card summary{cursor:pointer;font-size:12px;color:var(--accent);padding:12px 0}.issue-card pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:11px;line-height:1.6;padding:12px;background:var(--surface2);border-radius:6px;max-height:220px;overflow:auto;margin:0 0 14px}.empty,.muted{font-size:12px;color:var(--subtle);line-height:1.6}@media(max-width:760px){.issue-categories{grid-template-columns:repeat(2,minmax(0,1fr))}.issue-categories button{align-items:start;flex-direction:column;gap:6px}.issue-card{padding:12px}.issue-heading button{max-width:100%}}
</style>
