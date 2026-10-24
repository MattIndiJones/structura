import { beforeEach, afterEach, expect, it, vi } from 'vitest'
import { createRenderer, nextTick, ssrContextKey } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import { createPinia, setActivePinia } from 'pinia'
import BookingView from './BookingView.vue'
import ReinvestView from './ReinvestView.vue'
import VariantCompareTab from '../components/VariantCompareTab.vue'

const renderer=createRenderer({createComment:()=>({}),insert(){},remove(){},parentNode(){},nextSibling(){}})
const reply=data=>({ok:true,json:async()=>data,blob:async()=>new Blob(['%PDF'])})
let app,state
beforeEach(()=>{
  setActivePinia(createPinia());localStorage.clear()
  vi.stubGlobal('window',{addEventListener(){},removeEventListener(){}})
  vi.stubGlobal('document',{addEventListener(){},removeEventListener(){},visibilityState:'visible',createElement:()=>({click(){}})})
  const OriginalURL=URL
  vi.stubGlobal('URL',class extends OriginalURL {static createObjectURL(){return 'blob:frozen'}static revokeObjectURL(){}})
  vi.stubGlobal('fetch',vi.fn(async url=>String(url).startsWith('/api/alerts?')?reply({alerts:[]}):reply([])))
})
afterEach(()=>{app?.unmount();app=null;vi.unstubAllGlobals()})
async function mount(Component){
  const router=createRouter({history:createMemoryHistory(),routes:[{path:'/test',component:{render:()=>null}}]})
  await router.push('/test');await router.isReady()
  app=renderer.createApp({setup(_,ctx){state=Component.setup({},ctx);return()=>null}})
  app.provide(ssrContextKey,{modules:new Set()});app.use(router);app.mount({})
  for(let i=0;i<20;i++)await nextTick()
}

it('Booking exporte le résultat sélectionné malgré une modification des dates et du mode',async()=>{
  await mount(BookingView)
  state.explainResults[1]={archive_id:'saved-explain'}
  state.explainD1[1]='2020-01-01';state.explainD2[1]='2026-10-21'
  fetch.mockClear();fetch.mockResolvedValue(reply({}))
  await state.downloadExplainNote({id:1,reference:'A'})
  const [url,options]=fetch.mock.calls[0]
  expect(url).toBe('/api/deals/1/mtm/explain/report')
  expect(JSON.parse(options.body)).toEqual({archive_id:'saved-explain'})
})

it('une proposition est gelée avec sa preuve affichée puis exportée par identifiant',async()=>{
  await mount(ReinvestView)
  state.deal.value={id:1,reference:'A'}
  const preview={claims:{data:{candidate:{solved_param:.141602}}},signature:'proof'}
  state.proposalData.value={preview}
  fetch.mockClear();fetch.mockImplementation(async url=>String(url).endsWith('/freeze')?reply({archive_id:'frozen-1'}):reply([]))
  await state.freezeProposal()
  expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({preview})
  expect(state.proposalArchiveId.value).toBe('frozen-1')
  state.form.model='heston';fetch.mockClear();fetch.mockResolvedValue(reply({}))
  await state.downloadProposalPdf({ticker:'TK1'})
  expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({archive_id:'frozen-1'})
})

it('un gel tardif ne remplace pas une autre proposition affichée',async()=>{
  await mount(ReinvestView);state.deal.value={id:1,reference:'A'}
  state.proposalData.value={preview:{signature:'A'}}
  let resolve;fetch.mockImplementationOnce(()=>new Promise(r=>{resolve=r}))
  const pending=state.freezeProposal()
  state.proposalData.value={preview:{signature:'B'}}
  resolve(reply({archive_id:'archive-A'}));await pending
  expect(state.proposalArchiveId.value).toBe(null)
})

it('réouvrir une archive restitue ses chiffres sans demander de pricing',async()=>{
  await mount(ReinvestView);fetch.mockClear()
  const proposal={candidate:{ticker:'TK1',solved_param:.141602,sigma:.1}}
  state.openArchivedProposal({archive_id:'frozen-1',data:{proposal}})
  expect(state.proposalData.value).toEqual(proposal)
  expect(state.proposalArchiveId.value).toBe('frozen-1')
  expect(fetch).not.toHaveBeenCalled()
})

it('le comparateur fige la preuve affichée et restitue une étude conservée',async()=>{
  await mount(VariantCompareTab)
  const preview={claims:{result:{lignes:[{prix:.4}]}},signature:'comparison'}
  state.resultat.value={preview,lignes:[{prix:.4}]}
  fetch.mockClear();fetch.mockImplementation(async(url,options)=>options?.method==='POST'?reply({archive_id:'study-1'}):reply([]))
  await state.figer()
  expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({preview})
  expect(state.archiveId.value).toBe('study-1')
  state.archives.value=[{archive_id:'study-2',evidence:{result:{lignes:[{prix:.6}]}}}]
  fetch.mockClear();state.ouvrirArchive('study-2')
  expect(state.resultat.value.lignes[0].prix).toBe(.6)
  expect(fetch).not.toHaveBeenCalled()
})
