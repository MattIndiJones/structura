import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createRenderer, nextTick, ssrContextKey } from 'vue'
import View from './LoginView.vue'
vi.mock('/tp_logo.png',()=>({default:'/tp_logo.png'}))

const mocks=vi.hoisted(()=>({login:vi.fn(),developmentLogin:vi.fn(),activate:vi.fn(),route:{query:{}},user:null}))
vi.mock('../stores/auth.js',()=>({useAuthStore:()=>mocks}))
vi.mock('vue-router',()=>({useRoute:()=>mocks.route}))
const renderer=createRenderer({createComment:()=>({}),insert(){},remove(){},parentNode(){},nextSibling(){}})
let app,state
const target={installation_id:'org-A',organization_id:'A',kind:'organization',name:'Organisation A',key:'org-a',url:'http://127.0.0.1:8101'}
const reply=data=>({ok:true,json:async()=>data})
async function mount(){
  app=renderer.createApp({setup(props,ctx){state=View.setup(props,ctx);return()=>null}})
  app.provide(ssrContextKey,{modules:new Set()});app.mount({})
  for(let i=0;i<8;i++)await nextTick()
}
beforeEach(()=>{
  mocks.login.mockReset();mocks.developmentLogin.mockReset();mocks.activate.mockReset();mocks.user=null;mocks.route.query={};sessionStorage.clear()
  vi.stubGlobal('window',{location:{hash:'',reload:vi.fn(),assign:vi.fn()},history:{length:1,back:vi.fn()}})
})

describe('choix de compte et sortie du portail',()=>{
  async function portal(adminUrl='http://127.0.0.1:8000') {
    const central={installation_id:'central',kind:'platform',name:'Admin Structura'}
    vi.stubGlobal('fetch',vi.fn().mockResolvedValueOnce(reply({installation_portal:true,admin_workbench_url:adminUrl}))
      .mockResolvedValueOnce(reply({installations:[target,central]}))
      .mockResolvedValueOnce(reply({enabled:true,installations:[target,central]})))
    await mount()
    return central
  }
  it.each(['superuser','front','operations','controller'])('ouvre explicitement le profil %s',async profile=>{
    await portal()
    mocks.developmentLogin.mockResolvedValue({accessToken:'new-token',descriptor:target,identity:{role:'user'}})
    state.developmentProfile.value=profile
    await state.open(target)
    expect(mocks.developmentLogin).toHaveBeenCalledWith(target,profile)
    expect(mocks.activate).toHaveBeenCalledTimes(1)
  })
  it('garde la session initiale et un retour utilisable après une panne',async()=>{
    await portal()
    mocks.user={role:'admin',username:'admin'}
    mocks.developmentLogin.mockRejectedValue(new TypeError('Failed to fetch'))
    await state.open(target)
    expect(state.error.value).toContain('Installation injoignable')
    expect(state.loading.value).toBe(false)
    expect(mocks.activate).not.toHaveBeenCalled()
    await state.returnToAdmin()
    expect(window.location.assign).toHaveBeenCalledWith('http://127.0.0.1:8000/#/')
    expect(mocks.user.username).toBe('admin')
  })
  it('permet de revenir en arrière sans appel réseau, même après une erreur',async()=>{
    await portal()
    window.history.length=2
    const before=fetch.mock.calls.length
    state.goBack()
    expect(window.history.back).toHaveBeenCalledTimes(1)
    expect(fetch.mock.calls).toHaveLength(before)
  })
  it('traduit aussi une panne pendant la connexion par mot de passe',async()=>{
    await portal()
    state.selectedId.value=target.installation_id
    mocks.login.mockRejectedValue(new TypeError('Failed to fetch'))
    await state.submit()
    expect(state.error.value).toContain('Installation injoignable')
    await state.returnToAdmin()
    expect(window.location.assign).toHaveBeenCalledWith('http://127.0.0.1:8000/#/')
  })
  it('revient vers Admin sans dépendre du portail pour une ouverture directe',async()=>{
    await portal()
    const before=fetch.mock.calls.length
    state.goBack()
    expect(window.location.assign).toHaveBeenCalledWith('http://127.0.0.1:8000/#/')
    expect(fetch.mock.calls).toHaveLength(before)
  })
})
afterEach(()=>{app?.unmount();vi.unstubAllGlobals()})

describe('connexion normale par le portail',()=>{
  it('charge le choix des installations hors mode développeur et interdit le repli central implicite',async()=>{
    const fetch=vi.fn().mockResolvedValueOnce(reply({installation_portal:true}))
      .mockResolvedValueOnce(reply({installations:[target]}))
      .mockResolvedValueOnce(reply({enabled:false,installations:[]}))
    vi.stubGlobal('fetch',fetch)
    await mount()
    expect(state.loginInstallations.value).toEqual([target])
    expect(state.installations.value).toEqual([])
    expect(state.loginReady.value).toBe(true)
    state.username.value='front';state.password.value='sensitive-password'
    await state.submit()
    expect(mocks.login).not.toHaveBeenCalled()
    state.selectedId.value='unknown'
    await state.submit()
    expect(mocks.login).not.toHaveBeenCalled()
    state.selectedId.value=target.installation_id
    await state.submit()
    expect(mocks.login).toHaveBeenCalledExactlyOnceWith('front','sensitive-password',target)
  })

  it('bloque la connexion du portail quand son annuaire est indisponible',async()=>{
    vi.stubGlobal('fetch',vi.fn().mockResolvedValueOnce(reply({installation_portal:true})).mockResolvedValueOnce({ok:false}))
    await mount()
    expect(state.loginReady.value).toBe(false)
    await state.submit()
    expect(mocks.login).not.toHaveBeenCalled()
  })

  it('préserve la connexion directe au workspace autonome',async()=>{
    vi.stubGlobal('fetch',vi.fn().mockResolvedValueOnce(reply({registration_enabled:false})).mockResolvedValueOnce({ok:false}))
    await mount()
    expect(state.loginReady.value).toBe(true)
    await state.submit()
    expect(mocks.login).toHaveBeenCalledWith('','',null)
  })
})
