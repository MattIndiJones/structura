<script setup>
import { computed, ref, watch } from 'vue'
import WorkshopHelp from './WorkshopHelp.vue'
import { actorName, actionTitle, money, workshopLabels } from '../utils/workshopProgress'
const props=defineProps({state:{type:Object,required:true},caseId:{type:String,default:''}})
const selected=ref(props.caseId)
watch(()=>props.caseId,id=>{selected.value=id})
const checks=computed(()=>props.state.book_checks||[])
const chosen=computed(()=>checks.value.find(c=>c.case_id===selected.value)||checks.value.at(-1))
const records=computed(()=>Object.entries(props.state.actors).flatMap(([actor,a])=>(a.deals||[]).filter(d=>d.case_id===chosen.value?.case_id).map(d=>({...d,actor}))))
const actors=computed(()=>Object.values(props.state.actors).filter(a=>a.role!=='supervisor'))
const coverageNames={registration_ui:'Inscription par écran',bilateral_isda_csa:'Accords ISDA / CSA',crm:'Dossier client',native_pricing:'Pricing natif',notes_booking:'Booking de notes',native_mtm:'MtM résiduel',sourced_manual_fixings:'Fixings synthétiques tracés',otc_credit_risk:'CCR OTC hypothétique',margin_calls:'Appels de marge',counterparty_default:'Défaut de contrepartie',hector_own_issuance:'Émission propre du demandeur',reinvestment:'Réinvestissement',historical_market:'Marché historique',inter_entity_rfq_network:'Réseau RFQ entre installations',proactive_client_proposals:'Propositions commerciales',incomplete_relationship:'Refus documentaire'}
const coverageLabels={EXERCISED:'Fonction utilisée',NOT_EXERCISED:'Non exercée',OUT_OF_SCOPE:'Hors campagne',DEFERRED:'Différée',EXPECTED_REFUSAL:'Refus observé',DECLINED_WITH_LEGAL_EVIDENCE:'Refus documentaire observé'}
const fieldNames={count:'Nombre d’écritures',actor:'Acteur',role:'Rôle',counterparty:'Contrepartie',our_side:'Sens',nominal:'Nominal',price_traded:'Prix traité (%)',currency:'Devise',value_date:'Date de valeur',contract_hash:'Empreinte des termes',instrument_reference:'Instrument',trade_reference:'Transaction',outcome:'Clôture commerciale'}
const legTitle=leg=>actionTitle({tool:'book',args:{leg}})
function value(v){return v==null?'Absent':typeof v==='object'?JSON.stringify(v):String(v)}
</script>
<template>
  <section class="panel books" aria-label="Dossiers et books">
    <h2>Rapprochement des opérations <WorkshopHelp topic="books"/></h2>
    <p>La banque vend à Hector ; Hector achète puis revend au client. Le contrôle vérifie les quatre écritures uniques, leurs parties et leurs termes.</p>
    <p v-if="!checks.length">Aucun besoin client reçu. Les dossiers apparaîtront pendant la partie.</p>
    <div v-else class="table-wrap"><table><thead><tr><th>Dossier</th><th>Résultat</th><th>Écritures</th><th>Volume client rapproché</th></tr></thead><tbody><tr v-for="c in checks" :key="c.case_id"><td><button :aria-pressed="chosen?.case_id===c.case_id" @click="selected=c.case_id">{{c.case_id}} →</button></td><td>{{workshopLabels[c.status]||c.status}}</td><td>{{c.legs}} / 4</td><td class="numeric">{{money(c.client_volume)}}</td></tr></tbody></table></div>
    <template v-if="chosen">
      <h3>{{chosen.case_id}} · écritures enregistrées</h3>
      <p v-if="chosen.status==='NO_TRADE'">Dossier clôturé par refus, sans opération enregistrée.</p>
      <p v-if="chosen.missing_legs?.length">Écritures encore attendues : {{chosen.missing_legs.map(legTitle).join(' ; ')}}.</p>
      <p v-if="chosen.missing_evidence?.length" class="warning">Preuves manquantes : {{chosen.missing_evidence.map(f=>fieldNames[f]||f).join(', ')}}. Le dossier ne peut pas être déclaré complet.</p>
      <div v-if="chosen.issues?.length" class="table-wrap warning"><table><caption>Écarts à examiner</caption><thead><tr><th>Écriture / champ</th><th>Attendu</th><th>Observé</th></tr></thead><tbody><tr v-for="(issue,i) in chosen.issues" :key="i"><td>{{legTitle(issue.leg)}} · {{fieldNames[issue.field]||issue.field}}</td><td>{{value(issue.expected)}}</td><td>{{value(issue.actual)}}</td></tr></tbody></table></div>
      <div v-if="records.length" class="table-wrap"><table><thead><tr><th>Acteur / écriture</th><th>Contrepartie</th><th>Nominal</th><th>Prix (%)</th><th>Règlement initial</th></tr></thead><tbody><tr v-for="(d,i) in records" :key="i"><td>{{actorName(state,d.actor)}}<small>{{legTitle(d.leg)}} · {{d.deal_reference||d.deal_id}}</small></td><td>{{d.counterparty||'Preuve absente'}}</td><td class="numeric">{{money(d.nominal)}}</td><td class="numeric">{{d.price_traded??'—'}}</td><td>{{d.settlement_status==='SETTLED'?'Preuve enregistrée':'En attente'}}<small>{{d.value_date}}</small></td></tr></tbody></table></div>
    </template>
    <h3>Dernière revue de chaque book</h3>
    <div class="book-grid"><article v-for="a in actors" :key="a.id"><strong>{{a.name}}</strong><p>{{a.deals.length}} exécution(s) · {{a.last_review?.date||'Aucune revue'}}</p><p v-if="a.native_sync_error" class="warning">Relecture native à vérifier : {{a.native_sync_error}}</p><table v-if="a.last_review?.positions?.positions?.length"><thead><tr><th>Émetteur</th><th>Position nominale</th><th>Cash initial en attente</th></tr></thead><tbody><tr v-for="(p,i) in a.last_review.positions.positions" :key="i"><td>{{p.issuer}}</td><td class="numeric">{{money(p.nominal)}}</td><td class="numeric">{{money(p.pending_cash)}}</td></tr></tbody></table><p v-if="a.risk_runs?.length">CCR hypothétique : {{a.risk_runs.at(-1).status==='CALCULATED'?'calcul réalisé':a.risk_runs.at(-1).status||'résultat à examiner'}} · {{a.risk_runs.at(-1).date}}</p><details><summary>Preuves natives et hypothèses</summary><pre>{{JSON.stringify({relations:a.relations,deals:a.deals,review:a.last_review,risk:a.risk_runs},null,2)}}</pre></details></article></div>
    <section v-if="state.coverage_matrix"><h3>Matrice de recette de cette campagne</h3><table><thead><tr><th>Module</th><th>Résultat</th><th>Limite de preuve</th></tr></thead><tbody><tr v-for="(row,module) in state.coverage_matrix" :key="module"><td>{{module}}</td><td>{{{NOT_TESTED:'Non testé',NOT_IMPLEMENTED:'À raccorder',NOT_APPLICABLE:'Sans objet',EXERCISED:'Scénario exercé',FAILED:'Échec'}[row.status]||row.status}}</td><td>{{row.remaining||'Voir les preuves ; fonction exercée ne signifie pas validation exhaustive.'}}</td></tr></tbody></table></section>
    <h3>Fonctions utilisées <WorkshopHelp topic="coverage"/></h3><p>Une fonction utilisée n’est pas une validation quantitative ou une recette exhaustive. Le CCR hypothétique reste distinct du risque émetteur des notes.</p>
    <table><thead><tr><th>Fonction</th><th>Observation</th></tr></thead><tbody><tr v-for="(status,name) in state.coverage" :key="name"><td>{{coverageNames[name]||name}}</td><td>{{coverageLabels[status]||status}}</td></tr></tbody></table>
  </section>
</template>
<style scoped>
.books{min-width:0}.books h2{font-size:16px;font-weight:700}.books h3{font-size:14px;font-weight:650;margin:20px 0 10px}.books p{font-size:12px;line-height:1.65;color:var(--subtle);margin:8px 0}.table-wrap{overflow:auto}table{width:100%;font-size:12px}th,td{padding:10px 8px;text-align:left;border-bottom:1px solid var(--border)}td small{display:block;color:var(--subtle);font-size:11px;margin-top:4px}.numeric{text-align:right;font-variant-numeric:tabular-nums}button,summary{color:var(--accent);cursor:pointer}caption{text-align:left;padding:10px;font-weight:650}.warning{color:#97571c!important;background:#fff6e7;padding:10px;border-radius:6px}.book-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.book-grid article{min-width:0;background:var(--surface2);padding:14px;border-radius:8px}.book-grid table{font-size:11px}pre{font-size:11px;white-space:pre-wrap;overflow-wrap:anywhere;max-height:300px;overflow:auto}summary{font-size:12px;padding:10px 0}@media(max-width:900px){.book-grid{grid-template-columns:1fr}}
</style>
