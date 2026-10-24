/**
 * Ce que la déconnexion doit garantir.
 *
 * Le jeton vit dans `localStorage`, donc il survit à un rechargement : s'il
 * n'est pas effacé, le compte suivant repart sur la session du précédent. C'est
 * la seule partie de la déconnexion qui touche à la sécurité, et la seule que
 * le rechargement ne rattrape pas — il faut donc qu'elle soit faite AVANT.
 */
import { beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

import { useAuthStore } from './auth.js'
import { usePricingStore } from './pricing.js'
import { useProductsStore } from './products.js'
import { useRfqStore } from './rfq.js'

describe('les permissions métier reflètent le profil actif', () => {
  beforeEach(() => { setActivePinia(createPinia()); sessionStorage.clear() })

  it.each([
    ['user', ['business.price'], true, false, false, false],
    ['ops_maker', ['book', 'trading.settle'], false, true, false, true],
    ['checker', ['business.read'], false, false, false, false],
    ['organization_admin', ['business.price', 'book', 'trading.relationships.manage', 'trading.settle'], true, true, true, true],
    ['admin', [], false, false, false, false],
  ])('%s utilise les capacités de son installation', (role, capabilities, price, book, manage, settle) => {
    const auth = useAuthStore()
    auth.user = { role, capabilities, installation: { kind: 'organization' } }
    expect([auth.canPrice, auth.canBook, auth.canManageTrading, auth.canSettleTrading]).toEqual([price, book, manage, settle])
    auth.user = { ...auth.user, is_active: false }
    expect([auth.canPrice, auth.canBook, auth.canManageTrading, auth.canSettleTrading]).toEqual([false, false, false, false])
  })

  it('retire immédiatement les commandes lorsque les capacités changent', () => {
    const auth = useAuthStore()
    auth.user = { role: 'ops_maker', capabilities: ['book'], installation: { kind: 'organization' } }
    expect(auth.canBook).toBe(true)
    auth.user = { ...auth.user, capabilities: [] }
    expect(auth.canBook).toBe(false)
  })
})

describe('la déconnexion ne laisse rien derrière', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
  })

  it('efface le jeton du stockage, pas seulement de la mémoire', () => {
    sessionStorage.setItem('auth_token', 'jeton-du-compte-A')
    const auth = useAuthStore()
    auth.logout()

    // Un jeton laissé en stockage reconnecterait le compte A au prochain
    // chargement, y compris après que quelqu'un d'autre se soit assis devant.
    expect(sessionStorage.getItem('auth_token')).toBeNull()
  })

  it('oublie le jeton et le profil en mémoire', () => {
    const auth = useAuthStore()
    auth.token = 'x'
    auth.user = { id: 1, username: 'phil' }
    auth.logout()

    expect(auth.token).toBeNull()
    expect(auth.user).toBeNull()
    expect(auth.isAuthenticated).toBe(false)
  })
})

describe('confidentialité des sessions RFQ bancaires', () => {
  beforeEach(() => { setActivePinia(createPinia()); localStorage.clear() })
  it('ne conserve pas le produit bancaire, ses marchés ou son prix après déconnexion', () => {
    const auth = useAuthStore()
    const pricing = usePricingStore()
    const products = useProductsStore()
    const rfqs = useRfqStore()
    auth.user = { id: 2, entity_id: 2 }
    auth.token = 'fictitious-bank-session'
    pricing.currentProduct = { product_id: 9, name: 'Calcul BNP privé' }
    pricing.result = { price: .9876 }
    pricing.globalParams.r = 8
    pricing.sessionRouteKey = 'product:9:'
    products.current = pricing.currentProduct
    products.items = [{ id: 9 }]
    rfqs.current = { id: 8, model_price: 98.76 }
    rfqs.history = [{ model_price: 98.76 }]
    auth.logout()
    expect(auth.user).toBeNull()
    expect(auth.token).toBeNull()
    expect(pricing.currentProduct).toBeNull()
    expect(pricing.result).toBeNull()
    expect(pricing.globalParams.r).toBe(3)
    expect(pricing.sessionRouteKey).toBeNull()
    expect(products.current).toBeNull()
    expect(products.items).toEqual([])
    expect(rfqs.current).toBeNull()
    expect(rfqs.history).toEqual([])
  })
})

describe('administration locale distincte de la simulation', () => {
  beforeEach(() => { setActivePinia(createPinia()); localStorage.clear() })
  it('permet au super utilisateur de gérer son organisation sans droits techniques', () => {
    const auth = useAuthStore()
    auth.user = { role: 'organization_admin' }
    expect(auth.isOrganizationAdmin).toBe(true)
    expect(auth.canAdministerOrganization).toBe(true)
    expect(auth.isAdmin).toBe(false)
    expect(auth.canManageSimulation).toBe(false)
    for (const role of ['user', 'ops_maker', 'checker']) {
      auth.user = { role }
      expect(auth.canAdministerOrganization).toBe(false)
      expect(auth.isAdmin).toBe(false)
    }
  })
  it('autorise la simulation au seul admin central habilité en développement', () => {
    const auth = useAuthStore()
    auth.user = {role:'platform_admin', capabilities:['directory.read','simulation.manage']}
    expect(auth.canManageSimulation).toBe(true)
    expect(auth.isAdmin).toBe(false)
    expect(auth.canAdministerOrganization).toBe(false)
    auth.user = {role:'platform_admin', capabilities:['directory.read']}
    expect(auth.canManageSimulation).toBe(false)
  })
})
