import { describe, expect, it, vi } from 'vitest'
import { createSSRApp, h } from 'vue'
import { renderToString } from 'vue/server-renderer'
import { createPinia, setActivePinia } from 'pinia'
import View from './RiskManagementView.vue'
import { usePortfoliosStore } from '../stores/portfolios.js'
const route = vi.hoisted(() => ({ query: { tab: 'contreparties' }, path: '/risk', meta: {} }))
vi.mock('vue-router', () => ({ useRoute: () => route,
  useRouter: () => ({ replace: vi.fn() }), RouterLink: { render: () => null } }))
vi.mock('../stores/auth.js', () => ({ useAuthStore: () => ({ user: { id: 7 }, canAdministerOrganization: true }) }))

describe('concentration et qualification juridique', () => {
  it('rend la sélection UAT et la consultation des anciennes études distinctes', async () => {
    route.query.tab = 'var'
    const pinia = createPinia(); setActivePinia(pinia)
    const store = usePortfoliosStore()
    store.dataScope = 'UAT'
    store.historyMode = 'LEGACY_UNQUALIFIED'
    store.varStudy = { data_scope: 'LEGACY_UNQUALIFIED', status: 'queued', completed_jobs: 0, failed_jobs: 0, total_jobs: 1 }
    const app = createSSRApp({ render: () => h(View) }); app.use(pinia)
    const html = await renderToString(app)
    expect(html).toContain('Périmètre des calculs')
    expect(html).toContain('Calculs : Recette UAT · Historiques : Historique non qualifié.')
    expect(html).toContain('Étude conservée : Historique non qualifié.')
  })
  it('affiche une exception non qualifiée sans présenter sa limite comme contrôlée', async () => {
    const pinia = createPinia(); setActivePinia(pinia)
    route.query.tab = 'contreparties'
    const store = usePortfoliosStore()
    store.exposure = { nominal_total_eur: 1000000, coverage_complete: false,
      deals_requiring_qualification: [{ id: 1, administrator_exception: true }], deals_missing_fx: [{ id: 2 }],
      hhi: null, effective_n: null, top3_pct: null,
      by_counterparty: [{ identity_key: 'unqualified:Bank', contrepartie: 'Bank', identity_status: 'UNQUALIFIED',
        nominal_eur: 1000000, pct_of_book: 1, deal_count: 1, limit_eur: null, limit_status: 'UNQUALIFIED',
        limit_breached: null, deals: [] }] }
    const app = createSSRApp({ render: () => h(View) }); app.use(pinia)
    const html = await renderToString(app)
    expect(html).toContain('dossier(s) à qualifier juridiquement')
    expect(html).toContain('juridique à qualifier · limite non évaluée')
    expect(html).toContain('indicateurs de concentration incomplets')
    expect(html).toContain('total EUR partiel')
    expect(html).not.toContain('⚠ limite dépassée')
  })
  it('signale gamma et rho absents du calcul courant avec leur couverture et la source du delta', async () => {
    route.query.tab = 'greeks'
    const pinia = createPinia(); setActivePinia(pinia)
    const store = usePortfoliosStore()
    store.risk = { data_scope: 'PRODUCTION', deals_included: [{ id: 1 }], deals_missing_greeks: [],
      deals_stale: [], per_underlying: { ACT: { label: 'Action', delta_eur: 500000, gamma_eur: null,
        vega_eur: null, vega_scopes: [], contributions: [] } }, scalar: { theta: null, rho: null }, corr_pairs: {},
      metric_coverage: { delta: { required: 1, available: 1, status: 'COMPLETE', sources: [
        { reference: 'PARTIAL', run_id: 42, valuation_date: '2026-10-22', computed_at: '2026-10-22T10:00:00' }] },
        gamma: { required: 1, available: 0, status: 'UNAVAILABLE' }, rho: { required: 1, available: 0, status: 'UNAVAILABLE' } } }
    const app = createSSRApp({ render: () => h(View) }); app.use(pinia)
    const html = await renderToString(app)
    expect(html).toContain('Périmètre Production')
    expect(html).toContain('Gamma : 0/1 · indisponible pour le périmètre')
    expect(html).toContain('Rho : 0/1 · indisponible pour le périmètre')
    expect(html).toContain('calcul #42')
    expect(html).toContain('Delta : 1/1 · complet')
  })
  it.each([
    ['CONTRACTUAL_PAYMENT_DATE', 'Cash contractuel à échéance'],
    [undefined, 'Flux détachés — ancien calcul'],
  ])('distingue le cash contractuel et les anciens calculs P&L (%s)', async (basis, label) => {
    route.query.tab = 'pnl'
    const pinia = createPinia(); setActivePinia(pinia)
    const Wrapped = { ...View, setup(props, context) {
      const state = View.setup(props, context)
      state.pnlResult.value = { cash_basis: basis, pnl_total_eur: 0, delta_mtm_eur: -100000,
        flows_total_eur: 100000, pct_impact: 0, nominal_total_eur: 1000000, residual_eur: 0,
        contributions: [], skipped: [], errors: [],
        steps: [{ key: 'dividendes', label: 'Effet dividendes', delta_eur: 0 }] }
      return state
    } }
    const app = createSSRApp({ render: () => h(Wrapped) }); app.use(pinia)
    const html = await renderToString(app)
    expect(html).toContain(label)
    expect(html).toContain('Effet dividendes')
    if (basis) expect(html).toContain('aucune preuve de virement bancaire')
  })
})
