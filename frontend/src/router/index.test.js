import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('vue-router', async original => {
  const actual = await original()
  return {
    ...actual,
    createWebHashHistory: actual.createMemoryHistory,
    // Exercise the real route records and guards without mounting business views.
    createRouter: options => actual.createRouter({
      ...options,
      routes: options.routes.map(route => route.component
        ? { ...route, component: { render: () => null } } : route),
    }),
  }
})

import router from './index.js'
import { useAuthStore } from '../stores/auth.js'

const adminWorkbench = {
  role: 'admin', admin_workbench: true, capabilities: [],
  installation: { kind: 'platform', key: 'admin-workbench' },
}
const pricingRoutes = [
  '/pricer', '/pricer/7', '/pricer/v/3', '/products/7/pricer',
  '/structuring/optimizer', '/structuring/researches', '/structuring/researches/4',
]

beforeEach(async () => {
  setActivePinia(createPinia())
  const auth = useAuthStore()
  auth.token = 'isolated-router-session'
  auth.user = { ...adminWorkbench }
  await router.push('/')
})

describe('accès aux routes de pricing', () => {
  it.each(pricingRoutes)('le workspace Admin ouvre %s', async path => {
    await router.push(path)
    expect(router.currentRoute.value.path).toBe(path)
  })

  it.each(['user', 'organization_admin'])('le profil métier %s habilité ouvre le Pricer', async role => {
    useAuthStore().user = { role, capabilities: ['business.price'], installation: { kind: 'organization' } }
    await router.push('/pricer')
    expect(router.currentRoute.value.path).toBe('/pricer')
  })

  it.each(['ops_maker', 'checker', 'admin'])('le profil métier %s sans capacité reste refusé', async role => {
    useAuthStore().user = { role, capabilities: [], installation: { kind: 'organization' } }
    await router.push('/pricer')
    expect(router.currentRoute.value.path).toBe('/')
  })

  it('une session absente conduit à la connexion', async () => {
    useAuthStore().token = null
    await router.push('/pricer')
    expect(router.currentRoute.value.path).toBe('/login')
  })

  it('la console centrale conserve son propre périmètre', async () => {
    useAuthStore().user = { role: 'platform_admin', capabilities: [], installation: { kind: 'platform' } }
    await router.push('/pricer')
    expect(router.currentRoute.value.path).toBe('/platform')
  })

  it('la reprise après rechargement applique le profil Admin restauré', async () => {
    const auth = useAuthStore()
    auth.user = null
    const fetchMe = vi.spyOn(auth, 'fetchMe').mockImplementation(async () => {
      auth.user = { ...adminWorkbench }
    })
    await router.push('/pricer')
    expect(fetchMe).toHaveBeenCalledOnce()
    expect(router.currentRoute.value.path).toBe('/pricer')
  })
})

describe('routes voisines et profils autorisés', () => {
  it.each([
    '/scripts', '/product-models', '/products', '/documentation', '/rfq', '/rfq/recues',
    '/rfq/analyse', '/rfq/9/booking', '/booking', '/booking/9/valuations',
    '/valo-explain', '/risk', '/risk/ccr', '/reinvest', '/trading', '/amc', '/fifo',
    '/clients/liste', '/clients/fiche/7', '/clients/contacts/7', '/clients/opportunites/7',
    '/admin', '/admin/users', '/admin/browse/deals', '/agent-workshop',
  ])('le workspace Admin ouvre %s', async path => {
    await router.push(path)
    expect(router.currentRoute.value.path).toBe(path)
  })

  it.each([
    ['user', ['business.price'], '/'],
    ['ops_maker', ['book'], '/rfq/9/booking'],
    ['checker', ['operations.validate'], '/'],
    ['organization_admin', ['book'], '/rfq/9/booking'],
  ])('la revue de booking respecte le profil %s', async (role, capabilities, expected) => {
    useAuthStore().user = { role, capabilities, installation: { kind: 'organization' } }
    await router.push('/rfq/9/booking')
    expect(router.currentRoute.value.path).toBe(expected)
  })
})

describe('cohérence des liens internes', () => {
  const views = import.meta.glob('../**/*.vue', { query: '?raw', import: 'default', eager: true })
  const links = Object.entries(views).flatMap(([file, source]) =>
    [...source.matchAll(/(?<![:\w])to=["'](\/[^"']*)["']/g)]
      .map(match => [file, match[1]]))

  it('contrôle un ensemble non vide de liens réels des écrans', () => {
    expect(links.length).toBeGreaterThan(30)
  })

  it.each(links)('%s : %s correspond à une route déclarée', (_file, path) => {
    const matched = router.resolve(path).matched
    expect(matched.length).toBeGreaterThan(0)
    expect(matched[0].path).not.toBe('/:pathMatch(.*)*')
  })
})
