import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { createRenderer, createSSRApp, h, reactive, ssrContextKey, nextTick } from 'vue'
import { renderToString } from 'vue/server-renderer'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import VolSurfaceEditor from './VolSurfaceEditor.vue'
import ProductContextBar from './ProductContextBar.vue'
import PayScriptConfigurations from './PayScriptConfigurations.vue'
import OptimizerNumberInput from './OptimizerNumberInput.vue'
import ProductsView from '../views/ProductsView.vue'
import PricerView from '../views/PricerView.vue'
import { makeSurface } from '../utils/volSurface.js'
import { usePricingStore } from '../stores/pricing.js'
import { useProductsStore } from '../stores/products.js'
import { useAuthStore } from '../stores/auth.js'

let app, state
const renderer=createRenderer({createComment:()=>({}),insert(){},remove(){},parentNode(){},nextSibling(){}})
const reply=data=>({ok:true,json:async()=>data})
beforeEach(()=>{setActivePinia(createPinia());vi.stubGlobal('fetch',vi.fn(async(url,options)=>reply({surface:JSON.parse(options.body).surface})))})
afterEach(()=>{app?.unmount();app=null;vi.unstubAllGlobals()})
function setup(Component,props={}) {
  app=renderer.createApp({setup(_,context){state=Component.setup(props,context);return()=>null}})
  app.provide(ssrContextKey,{modules:new Set()});app.mount({});return state
}

it.each(['rho','eta'])('un champ de smile vide conserve la valeur de %s sans appel serveur',async field=>{
  const u=reactive({sigma:20,q:0,vol_surface:makeSurface('index',20),_smileDefaults:false})
  const surface=JSON.stringify(u.vol_surface)
  setup(VolSurfaceEditor,{u,model:'constant',horizon:4,rate:3})
  const event={target:{value:''}}
  await state.editShape(field,'',event)
  expect(JSON.stringify(u.vol_surface)).toBe(surface);expect(state.message.value).toContain('dernière hypothèse')
  expect(globalThis.fetch).not.toHaveBeenCalled()
})

it('saisir explicitement zéro reste une modification valide du smile',async()=>{
  const u=reactive({sigma:20,q:0,vol_surface:makeSurface('index',20),_smileDefaults:false})
  setup(VolSurfaceEditor,{u,model:'constant',horizon:4,rate:3})
  await state.editShape('eta','0',{target:{value:'0'}})
  expect(u.vol_surface.eta).toBe(0);expect(globalThis.fetch).toHaveBeenCalledOnce()
})

it('l’aperçu des configurations décrit devise, taux, courbes, funding et modèles',()=>{
  setup(PayScriptConfigurations)
  state.rows.value=[{id:1,global_params_json:JSON.stringify({deal_ccy:'USD',r:5,model:'heston',rateModel:'hull_white',
    yield_curve_pillars:[{T:1,rate:5}],funding:{level:2},configuration:{include_basket:false}})}]
  state.selectedId.value=1
  expect(state.scope.value).toBe('terms')
  expect(state.assumptionPreview.value.map(r=>r.key)).toEqual(['deal_ccy','r','model','rateModel','yield_curve_pillars','funding'])
  expect(state.assumptionPreview.value.find(r=>r.key==='r').label).toContain('(%)')
})

it('un refus de sauvegarde conserve la copie de travail et sa version attendue',async()=>{
  const router=createRouter({history:createMemoryHistory(),routes:[{path:'/pricer',component:{render:()=>null}}]})
  await router.push('/pricer');await router.isReady()
  const pinia=createPinia();setActivePinia(pinia)
  const pricing=usePricingStore(),products=useProductsStore(),auth=useAuthStore()
  auth.user={role:'user'};pricing.currentProduct={product_id:3,terms_version:1,revision:4}
  pricing.editingProductTerms=true;pricing.script='AT MATURITY\n  PAY 1';pricing.globalParams.T=1
  vi.spyOn(pricing,'validateScript').mockResolvedValue(true)
  vi.spyOn(products,'reviseTerms').mockRejectedValue(Error('Le produit a changé.'))
  app=renderer.createApp({setup(_,context){state=ProductContextBar.setup({},context);return()=>null}})
  app.provide(ssrContextKey,{modules:new Set()});app.use(router);app.use(pinia);app.mount({})
  state.termsReason.value='Compléter le brouillon'
  await state.saveTerms()
  expect(pricing.editingProductTerms).toBe(true);expect(pricing.currentProduct.revision).toBe(4)
  expect(products.error).toBe('Le produit a changé.')
})

it('la barre Product affiche exclusivement le dossier ouvert',async()=>{
  const pinia=createPinia();setActivePinia(pinia)
  const pricing=usePricingStore();useAuthStore().user={role:'user'}
  pricing.currentProduct={product_id:3,reference:'P-C07',terms_version:2,revision:4,listed:true}
  const router=createRouter({history:createMemoryHistory(),routes:[{path:'/pricer',component:{render:()=>null}}]})
  await router.push('/pricer');await router.isReady()
  const html=await renderToString(createSSRApp({render:()=>h(ProductContextBar)}).use(pinia).use(router))
  expect(html).toContain('P-C07');expect(html).toContain('Modifier les termes');expect(html).not.toContain('Session de pricing non conservée')
})

it.each(['new_edits','another_product','unchanged'])('la fin de sauvegarde respecte la session courante : %s',async mode=>{
  const pinia=createPinia();setActivePinia(pinia)
  const pricing=usePricingStore(),products=useProductsStore()
  pricing.currentProduct={product_id:3,terms_version:1,revision:1};pricing.editingProductTerms=true
  pricing.script='AT MATURITY\n  PAY 1';pricing.globalParams.T=1
  vi.spyOn(pricing,'validateScript').mockResolvedValue(true)
  let finish
  vi.spyOn(products,'reviseTerms').mockImplementation(()=>new Promise(resolve=>{finish=resolve}))
  const router=createRouter({history:createMemoryHistory(),routes:[{path:'/pricer',component:{render:()=>null}}]})
  await router.push('/pricer');await router.isReady()
  app=renderer.createApp({setup(_,context){state=ProductContextBar.setup({},context);return()=>null}})
  app.provide(ssrContextKey,{modules:new Set()});app.use(pinia);app.use(router);app.mount({})
  state.termsReason.value='Premier complément'
  const saving=state.saveTerms();await nextTick()
  if(mode==='new_edits') pricing.globalParams.payment_date='2030-01-01'
  if(mode==='another_product') pricing.currentProduct={product_id:99,terms_version:1,revision:1}
  finish({product_id:3,terms_version:2,revision:2})
  await saving
  if(mode==='another_product') {
    expect(pricing.currentProduct.product_id).toBe(99);expect(products.error).toContain('actuellement affiché est inchangé')
  } else {
    expect(pricing.currentProduct.terms_version).toBe(2)
    expect(pricing.editingProductTerms).toBe(mode==='new_edits')
    if(mode==='new_edits') {
      expect(pricing.globalParams.payment_date).toBe('2030-01-01');expect(pricing.productLoadNotice).toContain('saisies plus récentes')
    }
  }
})

it('le simple focus d’un nombre arrondi à l’écran ne remplace pas sa précision conservée',()=>{
  setup(OptimizerNumberInput,{modelValue:2.001})
  expect(state.formatted.value).toBe('2.00')
  state.focus({target:{value:'2.00'}})
  expect(state.props.modelValue).toBe(2.001)
})

it('le dossier et ses calculs utilisent des pages bornées, avec les liens métier conservés',async()=>{
  const products=useProductsStore()
  vi.spyOn(products,'fetchAll').mockResolvedValue([])
  vi.spyOn(products,'fetchDetails').mockResolvedValue({product_id:4,terms_version:2,rfqs:[{id:7}],execution:{deal_id:9},
    documents:[{kind:'DOCUMENT',record_id:3}],calculations:[{id:10,terms_version:1}],calculation_page:{offset:0,has_more:true}})
  vi.spyOn(products,'fetchHistory').mockResolvedValue({items:[{revision:4,terms_version:2}],offset:0,has_more:false})
  setup(ProductsView)
  await state.toggleCalculations({id:4})
  expect(products.fetchDetails).toHaveBeenCalledWith(4,{offset:0})
  expect(state.detailsByProduct[4]).toMatchObject({rfqs:[{id:7}],execution:{deal_id:9},documents:[{record_id:3}]})
  state.selectedCalculations[4]=[10]
  await state.loadCalculationPage(4,20)
  expect(products.fetchDetails).toHaveBeenLastCalledWith(4,{offset:20})
  expect(state.selectedCalculations[4]).toEqual([])
})

it('une ouverture refusée garde la session et permet une nouvelle tentative sur la même route',async()=>{
  const pinia=createPinia();setActivePinia(pinia)
  const pricing=usePricingStore(),products=useProductsStore()
  pricing.sessionRouteKey='draft';pricing.script='Saisie à conserver';products.error='Lecture momentanément impossible.'
  const reset=vi.spyOn(pricing,'resetToDefaults'),fetch=vi.spyOn(products,'fetchOne').mockResolvedValue(null)
  const router=createRouter({history:createMemoryHistory(),routes:[{path:'/products/:productId/pricer',component:{render:()=>null}}]})
  await router.push('/products/7/pricer');await router.isReady()
  app=renderer.createApp({setup(_,context){state=PricerView.setup({},context);return()=>null}})
  app.provide(ssrContextKey,{modules:new Set()});app.use(pinia);app.use(router);app.mount({})
  for(let i=0;i<12;i++)await nextTick()
  expect(state.loadError.value).toContain('Lecture momentanément');expect(pricing.sessionRouteKey).toBe('draft')
  expect(pricing.script).toBe('Saisie à conserver');expect(reset).not.toHaveBeenCalled()
  await state.charger();expect(fetch).toHaveBeenCalledTimes(2)
})
