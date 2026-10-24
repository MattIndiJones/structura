import { beforeEach, afterEach, expect, it, vi } from 'vitest'
import { createRenderer, reactive, nextTick, ssrContextKey } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import { createPinia, setActivePinia } from 'pinia'
import RfqView from './RfqView.vue'
import RfqInboxView from './RfqInboxView.vue'
import BookingView from './BookingView.vue'
import RfqExecutionPanel from '../components/RfqExecutionPanel.vue'
import RfqBankQuotePanel from '../components/RfqBankQuotePanel.vue'
import { useRfqStore } from '../stores/rfq.js'
import { makeSurface } from '../utils/volSurface.js'

const renderer=createRenderer({createComment:()=>({}),insert(){},remove(){},parentNode(){},nextSibling(){}})
const reply=(data,status=200)=>({ok:status>=200 && status<300,status,json:async()=>data})
const deferred=()=>{let resolve,reject;const promise=new Promise((r,j)=>{resolve=r;reject=j});return {promise,resolve,reject}}
const flush=async()=>{for(let i=0;i<18;i++) await nextTick()}
const row=id=>({id,case:{revision:1,responsible_user_id:1,product_id:id},quotes:[]})
let app,state
beforeEach(()=>{
  setActivePinia(createPinia());localStorage.clear()
  vi.stubGlobal('window',{addEventListener(){},removeEventListener(){}})
  vi.stubGlobal('document',{addEventListener(){},removeEventListener(){},visibilityState:'visible'})
  vi.stubGlobal('fetch',vi.fn(async url=>{
    if(url==='/api/parse')return reply({ok:true,params:[],constats:[]})
    if(String(url).startsWith('/api/alerts?'))return reply({alerts:[]})
    if(String(url).startsWith('/api/rfq-inbox/'))return reply(row(Number(String(url).split('/')[3])))
    return reply([])
  }))
})
afterEach(()=>{app?.unmount();app=null;vi.unstubAllGlobals()})
async function mount(Component,props={},emit=null){
  const router=createRouter({history:createMemoryHistory(),routes:[{path:'/test',component:{render:()=>null}}]})
  await router.push('/test');await router.isReady()
  app=renderer.createApp({setup(_,ctx){state=Component.setup(props,emit?{...ctx,emit}:ctx);return()=>null}})
  app.provide(ssrContextKey,{modules:new Set()});app.use(router);app.mount({});await flush();return state
}

const bankRow=id=>({...row(id),rights:['read','prepare','price','validate_quote','publish_quote'],
  open_for_work:true,publication_policy:{version:1,max_calculation_age_minutes:60},quote_draft:null})

it('la préparation bancaire actualise le dossier ouvert avec son contexte de réponse',async()=>{
  await mount(RfqInboxView);await state.open({id:1})
  const ticket=state.opening
  state.applyQuoteUpdate({...row(1),quote_draft:{revision:1}},ticket)
  expect(state.selected.value.quote_draft.revision).toBe(1)
})

it('une publication tardive ne remplace pas une réouverture du même dossier',async()=>{
  await mount(RfqInboxView);await state.open({id:1})
  const previous=state.opening
  state.show.value=false;await state.open({id:1})
  state.applyQuoteUpdate({...row(1),quote_draft:{revision:9}},previous)
  expect(state.selected.value.quote_draft).toBeUndefined()
})

it('le panneau bancaire émet le contexte capturé au départ du contrôle',async()=>{
  const emit=vi.fn(),props=reactive({received:bankRow(1),contextRevision:7})
  await mount(RfqBankQuotePanel,props,emit)
  const updated={...bankRow(1),quote_draft:{revision:1}}
  fetch.mockResolvedValueOnce(reply(updated))
  await state.refresh()
  expect(emit).toHaveBeenCalledWith('updated',updated,7)
  expect(state.busy.value).toBe(false)
})

it.each([false,true])('le contrôle bancaire tardif reste ignoré après changement de contexte, autre dossier=%s',async other=>{
  const emit=vi.fn(),props=reactive({received:bankRow(1),contextRevision:7})
  await mount(RfqBankQuotePanel,props,emit)
  const wait=deferred();fetch.mockImplementationOnce(()=>wait.promise)
  const pending=state.refresh()
  props.received=bankRow(other?2:1);props.contextRevision=8;await flush()
  wait.resolve(reply({...bankRow(1),quote_draft:{revision:99}}));await pending
  expect(emit).not.toHaveBeenCalled()
  expect(state.error.value).toBe('')
})

it('une erreur de publication arrivée après fermeture ne pollue pas le panneau suivant',async()=>{
  const emit=vi.fn(),props=reactive({received:bankRow(1),contextRevision:7})
  await mount(RfqBankQuotePanel,props,emit)
  const wait=deferred();fetch.mockImplementationOnce(()=>wait.promise)
  const pending=state.action('publish','POST',{expected_revision:1})
  props.contextRevision=8;await flush()
  wait.resolve(reply({detail:'Ancienne publication refusée'},409))
  expect(await pending).toBe(false)
  expect(state.error.value).toBe('');expect(emit).not.toHaveBeenCalled()
})

it('le refresh collectif recharge les événements ouverts et invalide le MtM affiché', async()=>{
  await mount(BookingView)
  state.dealsStore.deals=[{id:1},{id:2}]
  vi.spyOn(state.dealsStore,'loadDeals').mockResolvedValue()
  state.expanded[1]=true
  state.details[1]={id:1,events:[{fixing_status:'EXPECTED'}]}
  state.mtmResults[1]={mtm:101}
  const calls=[]
  fetch.mockImplementation(async url=>{
    calls.push(url)
    if(url==='/api/alerts/refresh-book')return reply({status:'FAILED',errors:['Source indisponible']})
    if(url==='/api/deals/1')return reply({id:1,events:[{fixing_status:'MISSING'}]})
    if(String(url).startsWith('/api/alerts?'))return reply({alerts:[]})
    return reply([])
  })
  await state.refreshBook()
  expect(state.details[1].events[0].fixing_status).toBe('MISSING')
  expect(state.mtmResults[1]).toBeNull()
  expect(calls).toContain('/api/deals/1')
  expect(calls).not.toContain('/api/deals/2')
  expect(state.refreshBookSummary.value.status).toBe('FAILED')
})

it('un détail refusé est signalé et sa reprise réussie efface l’erreur',async()=>{
  await mount(BookingView)
  fetch.mockResolvedValueOnce(reply({detail:'Lecture refusée'},403))
  await state.loadDetail(1)
  expect(state.detailErrors[1]).toBe('Lecture refusée')
  fetch.mockResolvedValueOnce(reply({id:1,events:[]}))
  await state.loadDetail(1)
  expect(state.detailErrors[1]).toBeUndefined()
  expect(state.details[1].id).toBe(1)
})

it.each([false,true])('réaffecter A ne remplace pas B, refus serveur=%s',async refused=>{
  await mount(RfqInboxView);await state.open({id:1})
  const wait=deferred();fetch.mockImplementationOnce(()=>wait.promise)
  state.assignedTo.value=3;state.assignmentReason.value='Réaffectation motivée'
  const pending=state.assign();await state.open({id:2})
  wait.resolve(reply(refused?{detail:'Conflit de révision'}:{...row(1),case:{revision:2,responsible_user_id:3}},refused?409:200))
  await pending
  expect(state.selected.value.id).toBe(2);expect(state.show.value).toBe(true)
  expect(state.error.value).toBe('');expect(state.assigning.value).toBe(false)
})
it('fermer une RFQ pendant la réaffectation ne réouvre pas son détail',async()=>{
  await mount(RfqInboxView);await state.open({id:1})
  const wait=deferred();fetch.mockImplementationOnce(()=>wait.promise)
  state.assignedTo.value=3;state.assignmentReason.value='Motif'
  const pending=state.assign();state.show.value=false
  wait.resolve(reply({...row(1),case:{revision:2}}));await pending
  expect(state.show.value).toBe(false);expect(state.selected.value.case.revision).toBe(1)
})
it('la réponse de réaffectation courante reste applicable',async()=>{
  await mount(RfqInboxView);await state.open({id:1})
  state.assignedTo.value=3;state.assignmentReason.value='Motif'
  fetch.mockResolvedValueOnce(reply({...row(1),case:{revision:2,responsible_user_id:3}}))
  await state.assign()
  expect(state.selected.value.case.revision).toBe(2);expect(state.showAssignment.value).toBe(false)
})
it('une ancienne liste de collaborateurs ne s’ouvre pas sur B',async()=>{
  await mount(RfqInboxView);await state.open({id:1})
  const wait=deferred();fetch.mockImplementationOnce(()=>wait.promise)
  const pending=state.prepareAssignment();await state.open({id:2})
  wait.resolve(reply([{id:3,name:'Collaborateur de A'}]));await pending
  expect(state.showAssignment.value).toBe(false);expect(state.assignees.value).toEqual([])
})

function execution(id=1){return {...row(id),selected_quote_id:4,quotes:[{id:4,contact:'Banque A'}],
  execution_agreements:[{id:8,state:'REQUESTED'}]}}
it.each(['rfq','quote','agreement'])('le formulaire d’exécution est remis à zéro au changement %s',async change=>{
  const props=reactive({rfq:execution()});await mount(RfqExecutionPanel,props)
  Object.assign(state.request,{source:'EMAIL',reference:'Demande A',bank_contact:'Banque A'})
  Object.assign(state.confirmation,{execution_reference:'Execution A',bank_contact:'Contact A',
    acceptance_received_at:'2026-10-21T10:00',confirmed_at:'2026-10-21T10:01',acceptance_evidence:'Accord A',evidence:'Confirmation A',source:'EMAIL'})
  state.commandKey.value='commande-A';state.cancelReason.value='Annulation A';state.opened.value=true
  expect(state.confirmationComplete.value).toBeTruthy()
  if(change==='rfq')props.rfq=execution(2)
  if(change==='quote')props.rfq.selected_quote_id=5
  if(change==='agreement')props.rfq.execution_agreements=[{id:9,state:'REQUESTED'}]
  expect(state.confirmationComplete.value).toBeFalsy();expect(state.opened.value).toBe(false)
  expect(state.request).toEqual({source:'PHONE',reference:'',bank_contact:''})
  expect(state.confirmation).toEqual({execution_reference:'',bank_contact:'',acceptance_received_at:'',confirmed_at:'',acceptance_evidence:'',evidence:'',source:'BANK_CONFIRMATION'})
  expect(state.commandKey.value).toBe('');expect(state.cancelReason.value).toBe('')
  const confirm=vi.spyOn(useRfqStore(),'confirmTreatment')
  await state.confirm();expect(confirm).not.toHaveBeenCalled()
})
it('les termes tardifs d’exécution ne remplissent pas une autre RFQ',async()=>{
  const props=reactive({rfq:{...execution(),execution_agreements:[]}});await mount(RfqExecutionPanel,props)
  const wait=deferred();fetch.mockImplementationOnce(()=>wait.promise)
  const pending=state.open();props.rfq={...execution(2),execution_agreements:[]}
  wait.resolve(reply({terms_version:1,terms_fingerprint:'empreinte-A'}));await pending
  expect(state.terms.value).toBeNull();expect(state.commandKey.value).toBe('')
})
it('un rafraîchissement du même accord conserve les preuves en cours de saisie',async()=>{
  const props=reactive({rfq:execution()});await mount(RfqExecutionPanel,props)
  state.confirmation.evidence='Preuve en cours';state.request.reference='Demande conservée';state.opened.value=true
  props.rfq=execution()
  expect(state.confirmation.evidence).toBe('Preuve en cours');expect(state.request.reference).toBe('Demande conservée')
  expect(state.opened.value).toBe(true)
})

it.each(['single','all'].flatMap(mode=>['500','403','network','success'].map(outcome=>[mode,outcome])))(
  'l’acquittement %s ne retire une alerte que sur succès : %s',async(mode,outcome)=>{
    await mount(BookingView);const alert={id:1,message:'Alerte à conserver',read_at:null}
    state.alerts.value=[alert]
    fetch.mockImplementationOnce(async()=>{if(outcome==='network')throw Error('Réseau indisponible')
      return reply({detail:{message:'Acquittement refusé'}},outcome==='success'?200:Number(outcome))})
    await (mode==='single'?state.markRead(alert):state.markAllRead())
    expect(state.alerts.value).toHaveLength(outcome==='success'?0:1)
    if(outcome!=='success'){expect(state.alerts.value[0].read_at).toBeNull();expect(state.alertError.value).toMatch(/refusé|indisponible/)}
    expect(state.markingAlerts.size).toBe(0);expect(state.markingAll.value).toBe(false)
  })
it('un acquittement global ne masque pas une nouvelle alerte reçue pendant son attente',async()=>{
  await mount(BookingView);const wait=deferred();state.alerts.value=[{id:1}]
  fetch.mockImplementationOnce(()=>wait.promise);const pending=state.markAllRead()
  state.alerts.value.push({id:2});wait.resolve(reply({}));await pending
  expect(state.alerts.value).toEqual([{id:2}])
})
it('un ancien chargement ne ressuscite pas une alerte acquittée',async()=>{
  await mount(BookingView);const wait=deferred();const alert={id:1};state.alerts.value=[alert]
  fetch.mockImplementationOnce(()=>wait.promise);const loading=state.loadAlerts()
  fetch.mockResolvedValueOnce(reply({}));await state.markRead(alert)
  wait.resolve(reply({alerts:[alert]}));await loading;expect(state.alerts.value).toEqual([])
})

const quote=()=>({id:4,price:100,status:'recu',firmness:'FIRM',quoted_at:'2026-10-21T08:00:00Z',valid_until:'2026-10-21T10:00:00Z'})
function currentQuote(){const q=quote();state.rfq.current={id:1,params:{},quotes:[q],selected_quote_id:null};return q}
it.each(['price','status','firmness','quoted_at','valid_until'])(
  'le refus du champ %s restaure sa valeur affichée et conserve la saisie refusée',async field=>{
    await mount(RfqView);const q=currentQuote(),element={value:'saisie refusée'}
    vi.spyOn(state.rfq,'updateQuote').mockRejectedValue(Error('Version dépassée'))
    const value=['quoted_at','valid_until'].includes(field)?'2026-10-22T09:00':field==='price'?'105':'NEW'
    if(field==='price')await state.onQuotePriceChange(q,value,element)
    else if(field==='quoted_at')await state.onQuoteDateChange(q,value,element)
    else if(field==='valid_until')await state.onQuoteValidityChange(q,value,element)
    else await state.updateQuoteField(q,field,value,element)
    expect(state.mutationError.value).toContain('Version dépassée')
    expect(state.rejectedMutation.value).toMatchObject({quoteId:4,field,value})
    expect(element.value).toBe(['quoted_at','valid_until'].includes(field)?state.toDatetimeLocal(q[field]):q[field])
    expect(state.rfq.current.quotes[0][field]).toBe(q[field])
  })
it.each(['add','remove','select','side'])('un refus de %s RFQ est restitué sans succès visuel',async action=>{
  await mount(RfqView);const q=currentQuote();state.addingQuote.value=true
  const method={add:'addQuote',remove:'removeQuote',select:'selectQuote',side:'update'}[action]
  vi.spyOn(state.rfq,method).mockRejectedValue(Error('Droit métier insuffisant'))
  if(action==='add'){state.quoteForm.provider='Banque A';await state.submitAddQuote();expect(state.addingQuote.value).toBe(true);expect(state.quoteForm.provider).toBe('Banque A')}
  if(action==='remove')await state.removeQuote(q.id)
  if(action==='select')await state.onSelectQuote(q)
  if(action==='side')await state.updateSens('vente')
  expect(state.mutationError.value).toContain('Droit métier insuffisant')
  expect(state.rfq.current.quotes).toHaveLength(1);expect(state.rfq.current.selected_quote_id).toBeNull()
})
it('un ancien refus de prix ne restaure pas une saisie plus récente',async()=>{
  await mount(RfqView);const q=currentQuote(),first=deferred(),last=deferred(),element={value:'105'}
  vi.spyOn(state.rfq,'updateQuote').mockReturnValueOnce(first.promise).mockReturnValueOnce(last.promise)
  const a=state.onQuotePriceChange(q,'105',element);element.value='106'
  const b=state.onQuotePriceChange(q,'106',element)
  first.reject(Error('Premier refus'));await a
  expect(element.value).toBe('106');expect(state.mutationError.value).toBe('')
  state.rfq.current.quotes[0].price=106;last.resolve({price:106});await b
  expect(state.rfq.current.quotes[0].price).toBe(106)
})
it('un refus reçu après navigation ne devient pas une erreur sur B',async()=>{
  await mount(RfqView);const q=currentQuote(),wait=deferred()
  vi.spyOn(state.rfq,'selectQuote').mockReturnValueOnce(wait.promise)
  const pending=state.onSelectQuote(q);state.rfq.current={id:2,params:{},quotes:[]}
  wait.reject(Error('Refus de A'));await pending
  expect(state.mutationError.value).toBe('');expect(state.rfq.current.id).toBe(2)
})
it('un prix refusé recharge la valeur désormais enregistrée sur le serveur',async()=>{
  await mount(RfqView);const q=currentQuote(),element={value:'105'}
  vi.spyOn(state.rfq,'updateQuote').mockRejectedValue(Error('Version dépassée'))
  fetch.mockResolvedValueOnce(reply({id:1,params:{},quotes:[{...q,price:103}]}))
  await state.onQuotePriceChange(q,'105',element)
  expect(state.rfq.current.quotes[0].price).toBe(103);expect(element.value).toBe(103)
  expect(state.rejectedMutation.value).toMatchObject({value:'105',reloadFailed:false})
})
it('le sens refusé revient au sens enregistré et conserve la saisie refusée',async()=>{
  await mount(RfqView);currentQuote();state.rfq.current.sens='achat';const element={value:'vente'}
  vi.spyOn(state.rfq,'update').mockRejectedValue(Error('Sens figé'))
  fetch.mockResolvedValueOnce(reply({...state.rfq.current,sens:'achat'}))
  await state.updateSens('vente',element)
  expect(element.value).toBe('achat');expect(state.rejectedMutation.value.value).toBe('vente')
})
it('le last look refusé restaure le choix enregistré sans ajouter de ligne',async()=>{
  await mount(RfqView);const q=currentQuote(),element={value:'oui'}
  vi.spyOn(state.rfq,'toggleLastLook').mockRejectedValue(Error('Cotation non éligible'))
  fetch.mockResolvedValueOnce(reply({...state.rfq.current,quotes:[{...q,last_look:false}]}))
  await state.onLastLookToggle(q,true,element)
  expect(element.value).toBe('non');expect(state.rfq.current.quotes).toHaveLength(1)
  expect(state.mutationError.value).toContain('non éligible')
})
it('un refus de A ne relance pas une lecture de A pendant l’ouverture de B',async()=>{
  await mount(RfqView);const q=currentQuote(),mutation=deferred(),opening=deferred()
  vi.spyOn(state.rfq,'selectQuote').mockReturnValueOnce(mutation.promise)
  const old=state.onSelectQuote(q)
  fetch.mockImplementationOnce(()=>opening.promise)
  const recent=state.selectRfq(2)
  mutation.reject(Error('Refus A'));await old
  opening.resolve(reply({id:2,params:{},quotes:[]}));await recent
  expect(state.rfq.current.id).toBe(2);expect(state.mutationError.value).toBe('')
})
it('la RFQ refuse de calculer avec une calibration correspondant à l’ancien taux',async()=>{
  await mount(RfqView)
  state.rfq.current={id:1,script_snapshot:'AT MATURITY:\n  PAY 1',params:{T:1,r:.03,model:'heston',
    underlyings:[{name:'A',ticker:'A',ccy:'EUR',sigma:.3,q:.02,vol_surface:makeSurface('equity',30)}]}}
  await state.refreshDetailParams()
  const wait=deferred();fetch.mockImplementationOnce(()=>wait.promise)
  const update=vi.spyOn(state.rfq,'update'),pending=state.computeModelPrice()
  await flush();state.detailAdvanced.r=4
  wait.resolve(reply({parameters:{kappa:4,v0:.09}}));await pending
  expect(update).not.toHaveBeenCalled();expect(state.computeError.value).toMatch(/changé|contexte/)
})
