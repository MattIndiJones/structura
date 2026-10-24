import { beforeEach, afterEach, expect, it, vi } from 'vitest'
import { createSSRApp, h } from 'vue'
import { renderToString } from 'vue/server-renderer'
import { createPinia, setActivePinia } from 'pinia'
import ScriptAssistantModal from './ScriptAssistantModal.vue'
import { usePricingStore } from '../stores/pricing.js'

vi.mock('./ui/BaseModal.vue', () => ({ default: { setup: (_, { slots }) => () => slots.default?.() } }))
vi.mock('./AiWorkbench.vue', () => ({ default: { render: () => null } }))
vi.mock('./MicDictation.vue', () => ({ default: { render: () => null } }))

let pinia
const response = proof => ({
  script: 'AT MATURITY:\n  PAY 1', compiles: true, checks_status: 'passed', pricing_check: 'passed',
  checks: [], payoff_qualification: proof,
})
beforeEach(() => {
  pinia = createPinia(); setActivePinia(pinia)
  vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => ({ ok: true, params: [], constats: [] }) })))
})
afterEach(() => vi.unstubAllGlobals())
async function render(proof) {
  usePricingStore().scriptGen = response(proof)
  const app = createSSRApp({ render: () => h(ScriptAssistantModal, { modelValue: true }) })
  app.use(pinia)
  return renderToString(app)
}

it.each([undefined, { status: 'STRUCTURAL_ONLY' }, { status: 'UNQUALIFIED' }])(
  'un script qui compile et price reste présenté comme non qualifié sans preuve', async proof => {
    const html = await render(proof)
    expect(html).toContain('Payoff non qualifié')
    expect(html).toContain('Revue structurelle')
    expect(html).toContain('Exécution de contrôle')
    expect(html).toContain('ne prouvent pas sa conformité économique')
  })

it('la preuve de trajectoires affiche sa portée limitée', async () => {
  const html = await render({ status: 'REFERENCE_PATHS_PASSED' })
  expect(html).toContain('panel de trajectoires de référence')
  expect(html).toContain('Les termes du produit, les calendriers et le modèle de pricing restent à valider')
})

it('la provenance adoptée conserve une copie de la preuve et trace les modifications ultérieures', async () => {
  const store = usePricingStore()
  const proof = { status: 'REFERENCE_PATHS_PASSED', source_hash: 'approved-source', panel_version: 'C09-v1' }
  store.scriptGen = response(proof)
  store.adoptGeneratedScript()
  proof.source_hash = 'changed-response'
  expect(store.scriptProvenance().payoff_qualification.source_hash).toBe('approved-source')
  expect(store.scriptProvenance().modified_after_adoption).toBe(false)
  store.script += '\n# edit'
  expect(store.scriptProvenance().modified_after_adoption).toBe(true)
})
