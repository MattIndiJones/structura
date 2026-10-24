import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useAuthStore } from './auth.js'

const installation = { installation_id:'installation-A', organization_id:'organization-A', kind:'organization', url:'http://127.0.0.1:8101' }
const response = data => ({ ok:true, json:async()=>data })
beforeEach(()=>{ setActivePinia(createPinia()); sessionStorage.clear(); localStorage.clear() })
afterEach(()=>vi.unstubAllGlobals())

describe('identité vérifiée avant transmission des identifiants', ()=>{
  it.each(['installation_id','organization_id','kind'])('refuse une divergence de %s sans envoyer de mot de passe', async field=>{
    const fetch = vi.fn().mockResolvedValue(response({ installation:{...installation,[field]:'foreign'} }))
    vi.stubGlobal('fetch',fetch)
    const auth = useAuthStore()
    await expect(auth.login('front','sensitive-password',installation)).rejects.toThrow('aucun identifiant transmis')
    expect(fetch).toHaveBeenCalledExactlyOnceWith(installation.url+'/api/auth/identity')
    expect(auth.token).toBeNull()
  })

  it('refuse une installation indisponible sans transmettre les identifiants', async()=>{
    const fetch=vi.fn().mockResolvedValue({ok:false})
    vi.stubGlobal('fetch',fetch)
    await expect(useAuthStore().login('front','sensitive-password',installation)).rejects.toThrow('Installation incohérente')
    expect(fetch).toHaveBeenCalledTimes(1)
  })

  it('authentifie dans la base choisie et vérifie aussi le retour de session', async()=>{
    const fetch=vi.fn().mockResolvedValueOnce(response({installation}))
      .mockResolvedValueOnce(response({access_token:'local-session'}))
      .mockResolvedValueOnce(response({role:'user',installation}))
    vi.stubGlobal('fetch',fetch)
    const auth=useAuthStore()
    await auth.login('front','sensitive-password',installation)
    expect(fetch.mock.calls.map(call=>call[0])).toEqual(['/api/auth/identity','/api/auth/login','/api/auth/me'].map(path=>installation.url+path))
    expect(fetch.mock.calls[1][1].body.get('password')).toBe('sensitive-password')
    expect(auth.installation).toEqual(installation)
    expect(auth.token).toBe('local-session')
  })
})

describe('déconnexion serveur et effacement immédiat', ()=>{
  it('efface immédiatement la session locale puis révoque le jeton sur son installation', async()=>{
    let resolve
    const fetch=vi.fn().mockImplementation(()=>new Promise(done=>{resolve=done}))
    vi.stubGlobal('fetch',fetch)
    const auth=useAuthStore()
    auth.activate('local-session',installation,{role:'user',installation})
    const pending=auth.logout()
    expect(auth.token).toBeNull()
    expect(sessionStorage.getItem('auth_token')).toBeNull()
    expect(fetch.mock.calls[0][0]).toBe(installation.url+'/api/auth/logout')
    expect(fetch.mock.calls[0][1].headers.Authorization).toBe('Bearer local-session')
    resolve({ok:true})
    expect(await pending).toBe(true)
  })

  it('signale une révocation non confirmée en cas de serveur indisponible', async()=>{
    vi.stubGlobal('fetch',vi.fn().mockRejectedValue(new Error('offline')))
    const auth=useAuthStore()
    auth.activate('local-session',installation,{role:'user',installation})
    expect(await auth.logout()).toBe(false)
    expect(auth.isAuthenticated).toBe(false)
    expect(sessionStorage.getItem('auth_notice')).toContain('Révocation serveur non confirmée')
  })

  it('révoque aussi la session centrale conservée par un changement de contexte développeur', async()=>{
    const fetch=vi.fn().mockResolvedValue({ok:true})
    vi.stubGlobal('fetch',fetch)
    const auth=useAuthStore()
    sessionStorage.setItem('development_admin_token','central-session')
    auth.activate('local-session',installation,{role:'user',installation})
    expect(await auth.logout()).toBe(true)
    expect(fetch.mock.calls.map(call=>[call[0],call[1].headers.Authorization])).toEqual([
      [installation.url+'/api/auth/logout','Bearer local-session'],['/api/auth/logout','Bearer central-session']])
  })
})

describe('ouverture explicite d’une installation arrêtée',()=>{
  it('demande le démarrage avant échange du ticket sans remplacer la session active',async()=>{
    const identity={role:'user',installation}
    const fetch=vi.fn().mockResolvedValueOnce(response({ticket:'signed-ticket'}))
      .mockResolvedValueOnce(response({access_token:'next-session'})).mockResolvedValueOnce(response(identity))
    vi.stubGlobal('fetch',fetch)
    const auth=useAuthStore()
    auth.activate('initial-admin',null,{role:'admin'})
    const next=await auth.developmentLogin(installation,'front')
    expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({installation_id:installation.installation_id,username:'front',start_if_needed:true})
    expect(next.identity).toEqual(identity)
    expect(auth.token).toBe('initial-admin')
    expect(auth.user.role).toBe('admin')
  })
  it('traduit une panne et conserve le compte courant',async()=>{
    vi.stubGlobal('fetch',vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
    const auth=useAuthStore()
    auth.activate('initial-admin',null,{role:'admin'})
    await expect(auth.developmentLogin(installation,'front')).rejects.toThrow('Installation injoignable')
    expect(auth.token).toBe('initial-admin')
  })
  it('explique le redémarrage nécessaire si un ancien portail tourne encore',async()=>{
    vi.stubGlobal('fetch',vi.fn().mockResolvedValue({ok:false,status:422,json:async()=>({detail:[{loc:['body','start_if_needed'],type:'extra_forbidden'}]})}))
    await expect(useAuthStore().developmentLogin(installation,'front')).rejects.toThrow('Fermez puis relancez Structura')
  })
})
