import { afterEach, describe, expect, it, vi } from 'vitest'
import { durableCommand } from './commands.js'
import { useDealsStore } from '../stores/deals.js'
import { createPinia, setActivePinia } from 'pinia'

afterEach(() => vi.unstubAllGlobals())

describe('reprise des commandes métier', () => {
  it('partage les doubles clics simultanés, même si la réponse est immédiate', async () => {
    const send = vi.fn(async key => ({ key }))
    const results = await Promise.all([durableCommand('retain', { price: 100 }, send),
      durableCommand('retain', { price: 100 }, send)])
    expect(send).toHaveBeenCalledOnce()
    expect(results[0]).toEqual(results[1])
  })

  it('reconnaît un contenu identique indépendamment de l’ordre des propriétés', async () => {
    let key
    await expect(durableCommand('retain', { a: 1, b: { c: 2, d: 3 } }, async value => {
      key = value; throw new Error('Réponse perdue')
    })).rejects.toThrow()
    const next = await durableCommand('retain', { b: { d: 3, c: 2 }, a: 1 }, async value => value)
    expect(next).toBe(key)
  })

  it('ne conserve dans le navigateur ni script, ni prix, ni jeton', async () => {
    sessionStorage.setItem('auth_token', 'SECRET-TOKEN')
    await expect(durableCommand('retain', { script: 'SECRET-PAYOFF', price: 123456789 }, async () => {
      throw new Error('Réponse perdue')
    })).rejects.toThrow()
    const saved = sessionStorage.getItem('structura_pending_commands_v1')
    expect(saved).not.toContain('SECRET')
    expect(saved).not.toContain('123456789')
  })

  it.each(['actor', 'installation'])('sépare les commandes par %s', async scope => {
    sessionStorage.setItem('auth_token', 'actor-one')
    let key
    await expect(durableCommand('retain', { a: 1 }, async value => {
      key = value; throw new Error('Réponse perdue')
    })).rejects.toThrow()
    if (scope === 'actor') sessionStorage.setItem('auth_token', 'actor-two')
    else sessionStorage.setItem('auth_installation', JSON.stringify({ url: 'http://127.0.0.1:8101' }))
    expect(await durableCommand('retain', { a: 1 }, async value => value)).not.toBe(key)
  })

  it('conserve la reprise après renouvellement du jeton du même utilisateur', async () => {
    const token = exp => `header.${btoa(JSON.stringify({ sub: '7', entity_id: 1, exp }))}.signature`
    sessionStorage.setItem('auth_token', token(1))
    let key
    await expect(durableCommand('retain', { a: 1 }, async value => {
      key = value; throw new Error('Réponse perdue')
    })).rejects.toThrow()
    sessionStorage.setItem('auth_token', token(2))
    expect(await durableCommand('retain', { a: 1 }, async value => value)).toBe(key)
  })

  it('ignore un résultat tardif après un changement de session', async () => {
    sessionStorage.setItem('auth_token', 'one')
    let finish, started
    const ready = new Promise(resolve => { started = resolve })
    const pending = durableCommand('retain', { a: 1 }, async () => {
      started(); return new Promise(resolve => { finish = resolve })
    })
    await ready
    sessionStorage.setItem('auth_token', 'two')
    finish({ product_id: 7 })
    await expect(pending).rejects.toThrow('contexte a changé')
    expect(Object.keys(JSON.parse(sessionStorage.getItem('structura_pending_commands_v1')))).toHaveLength(1)
  })

  it('arrête l’envoi si la clé ne peut pas être conservée', async () => {
    vi.stubGlobal('sessionStorage', { ...sessionStorage, setItem() { throw new Error('Quota atteint') } })
    const send = vi.fn()
    await expect(durableCommand('retain', { a: 1 }, send)).rejects.toThrow('Quota atteint')
    expect(send).not.toHaveBeenCalled()
  })

  it('reprend le booking après réponse perdue, puis permet une autre intention explicite', async () => {
    setActivePinia(createPinia())
    const posted = []
    vi.stubGlobal('fetch', vi.fn(async (_url, options) => {
      posted.push(JSON.parse(options.body))
      if (posted.length === 1) throw new Error('Réponse perdue après booking serveur')
      return { ok: true, json: async () => ({ id: posted.length === 2 ? 7 : 8 }) }
    }))
    const store = useDealsStore()
    await expect(store.bookDeal({ nominal: 1000000 })).rejects.toThrow('Réponse perdue')
    await store.bookDeal({ nominal: 1000000 })
    await store.bookDeal({ nominal: 1000000 })
    expect(posted[1].command_key).toBe(posted[0].command_key)
    expect(posted[2].command_key).not.toBe(posted[1].command_key)
    expect(store.deals.map(item => item.id)).toEqual([8, 7])
  })

  it('ne confirme pas une réponse JSON tronquée et réutilise sa clé', async () => {
    setActivePinia(createPinia())
    const posted = []
    vi.stubGlobal('fetch', vi.fn(async (_url, options) => {
      posted.push(JSON.parse(options.body))
      return { ok: true, json: async () => {
        if (posted.length === 1) throw new SyntaxError('JSON tronqué')
        return { id: 7 }
      } }
    }))
    const store = useDealsStore()
    await expect(store.bookDeal({ nominal: 1000000 })).rejects.toThrow('JSON tronqué')
    expect(store.deals).toEqual([])
    await store.bookDeal({ nominal: 1000000 })
    expect(posted[1].command_key).toBe(posted[0].command_key)
    expect(store.deals.map(item => item.id)).toEqual([7])
  })
})
