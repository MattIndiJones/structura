import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createRenderer, nextTick, ssrContextKey } from 'vue'
import Selector from './ContextSelector.vue'

const mocks=vi.hoisted(()=>({auth:{user:null},pricing:{variantDirty:false,hasUnsavedSession:vi.fn()},confirm:vi.fn(),fetch:vi.fn(),prepare:vi.fn()}))
vi.mock('../stores/auth.js',()=>({useAuthStore:()=>mocks.auth}))
vi.mock('../stores/pricing.js',()=>({usePricingStore:()=>mocks.pricing}))
vi.mock('vue-router',()=>({useRoute:()=>({path:'/',query:{}})}))
vi.mock('../composables/useConfirm.js',()=>({confirmer:(...args)=>mocks.confirm(...args)}))
vi.mock('../composables/useContextChanges.js',()=>({hasContextChanges:()=>false,prepareContextReload:()=>mocks.prepare()}))
vi.mock('../utils/session.js',async original=>({...await original(),portalFetch:(...args)=>mocks.fetch(...args)}))
const renderer=createRenderer({createComment:()=>({}),insert(){},remove(){},parentNode(){},nextSibling(){}})
let app,state
async function mount(){
  app=renderer.createApp({setup(props,ctx){state=Selector.setup(props,ctx);return()=>null}})
  app.provide(ssrContextKey,{modules:new Set()});app.mount({});await nextTick()
}
beforeEach(()=>{
  vi.clearAllMocks()
  mocks.auth.user={role:'admin',username:'admin',admin_workbench:true,development_admin_enabled:true,platform_url:'http://127.0.0.1:8100'}
  mocks.pricing.variantDirty=false;mocks.pricing.hasUnsavedSession.mockReturnValue(false)
  vi.stubGlobal('window',{location:{assign:vi.fn()}})
})
afterEach(()=>{app?.unmount();vi.unstubAllGlobals()})
describe('choix de compte depuis Admin',()=>{
  it('rend le passage au portail disponible sans requête inter-origines ni remplacement du compte',async()=>{
    await mount();expect(state.adminPortal.value).toBeTruthy()
    state.opened.value=true;await nextTick();await state.switchContext()
    expect(mocks.fetch).not.toHaveBeenCalled()
    expect(window.location.assign).toHaveBeenCalledWith('http://127.0.0.1:8100/#/login')
    expect(mocks.auth.user.username).toBe('admin')
  })
  it('conserve le contexte si l’utilisateur annule l’abandon de saisies',async()=>{
    mocks.pricing.variantDirty=true;mocks.confirm.mockResolvedValue(false)
    await mount();await state.switchContext()
    expect(mocks.confirm).toHaveBeenCalledTimes(1)
    expect(window.location.assign).not.toHaveBeenCalled()
    expect(mocks.prepare).not.toHaveBeenCalled()
  })
  it('autorise le départ après confirmation explicite',async()=>{
    mocks.pricing.variantDirty=true;mocks.confirm.mockResolvedValue(true)
    await mount();await state.switchContext()
    expect(mocks.prepare).toHaveBeenCalledTimes(1)
    expect(window.location.assign).toHaveBeenCalledTimes(1)
  })
  it('garde la bascule privilégiée désactivée hors mode développeur',async()=>{
    mocks.auth.user.development_admin_enabled=false
    await mount();expect(state.adminPortal.value).toBeFalsy()
    await state.switchContext();expect(window.location.assign).not.toHaveBeenCalled()
  })
})
