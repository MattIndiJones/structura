import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createRenderer, nextTick, reactive } from 'vue'
import { useAiWorkbench } from './useAiWorkbench'
import { aiSettings, aiCredentials, aiCatalog, refreshAiCatalog, syncAiIdentity } from './useAiSettings'

// Exercise the actual workflow with Vue's lifecycle, without a browser or a model.
const renderer = createRenderer({ createComment: () => ({}), insert() {}, remove() {}, parentNode() {}, nextSibling() {} })
const apps = []
function mount(overrides = {}) {
  const props = reactive({ endpoint: '/test/generate', payload: { value: 1 }, contextKey: '', disabled: false, ...overrides })
  const emit = vi.fn()
  let state
  const app = renderer.createApp({ setup() { state = useAiWorkbench(props, emit); return () => null } })
  app.mount({}); apps.push(app)
  return { props, state, emit }
}
const preview = { system: 'Instructions', user: 'Chiffres', base_hash: 'a'.repeat(64), prompt_version: 'v1' }
const catalog = { providers: [{ key: 'ollama', models: ['test:7b'], default_model: 'test:7b', ready: true }] }
const result = { text: 'Proposition', provider: 'ollama', effective_model: 'test:7b', prompt: preview }
const reply = data => ({ ok: true, json: async () => data })
const settle = async () => { for (let i = 0; i < 10; i++) await Promise.resolve(); await nextTick() }
let calls
beforeEach(() => {
  localStorage.clear(); syncAiIdentity(); calls = []
  aiSettings.provider = 'ollama'; aiSettings.ollamaUrl = 'http://localhost:11434'; aiSettings.models = { ollama: 'test:7b' }
  aiCatalog.providers = catalog.providers; aiCatalog.url = aiSettings.ollamaUrl
  vi.stubGlobal('fetch', vi.fn(async (url, options) => {
    if (url.startsWith('/api/ai/providers')) return reply(catalog)
    calls.push({ url, body: JSON.parse(options.body) })
    return reply(url.endsWith('/prompt') ? preview : result)
  }))
})
afterEach(() => { apps.splice(0).forEach(app => app.unmount()); vi.unstubAllGlobals() })

describe('shared AI workflow', () => {
  it('sends the edited prompt verbatim, emits a proposal and reports real phases', async () => {
    const { state, emit } = mount()
    await state.showPrompt()
    expect(calls).toHaveLength(1)
    state.draft.user += '\nTexte ajouté'
    state.draft.system = 'Consignes personnalisées'
    await state.run()
    expect(calls[1].body.prompt_override).toEqual({ base_hash: preview.base_hash, system: state.draft.system, user: state.draft.user })
    expect(emit).toHaveBeenCalledWith('result', result)
    expect(state.working.value).toBe(false)
    expect(state.last.value).toEqual(result)
  })

  it('keeps custom edits visible but blocks generation after a context change', async () => {
    const { state, props, emit } = mount()
    await state.showPrompt(); state.draft.user = 'Personnalisé'
    props.payload = { value: 2 }; await nextTick()
    expect(state.stale.value).toBe(true)
    expect(state.draft.user).toBe('Personnalisé')
    await state.run()
    expect(calls).toHaveLength(1)
    expect(emit).not.toHaveBeenCalledWith('result', expect.anything())
    await state.resetPrompt()
    expect(state.stale.value).toBe(false)
    expect(state.draft.user).toBe(preview.user)
  })

  it('waits for draft saving before constructing a valuation prompt', async () => {
    const { props, state } = mount()
    props.beforePrepare = async () => { props.payload = { revision: 2 }; await nextTick() }
    await state.run()
    expect(calls.map(c => c.body.revision)).toEqual([2, 2])
  })

  it('rejects an obsolete preview arriving after the context changed', async () => {
    let release
    const { props, state } = mount(); await settle()
    fetch.mockImplementationOnce(() => new Promise(resolve => { release = () => resolve(reply(preview)) }))
    const pending = state.showPrompt(); await settle()
    props.payload = { value: 2 }; release(); await pending
    expect(state.prompt.value).toBeNull()
    expect(state.error.value).toContain('contexte a changé')
  })

  it('discards late results and prevents duplicate submissions', async () => {
    const { props, state, emit } = mount(); await state.showPrompt()
    let release
    fetch.mockImplementationOnce(() => new Promise(resolve => { release = () => resolve(reply(result)) }))
    const pending = state.run(); await settle()
    expect(state.phase.value).toBe('Génération par le modèle')
    await state.run()
    props.payload = { value: 3 }; release(); await pending
    expect(emit).not.toHaveBeenCalledWith('result', expect.anything())
    expect(state.error.value).toContain('pas été appliqué')
    expect(state.last.value).toEqual(result)
  })

  it('exposes provider errors and releases the busy state', async () => {
    const { state } = mount(); await state.showPrompt()
    fetch.mockResolvedValueOnce({ ok: false, status: 429, json: async () => ({ detail: 'Quota atteint' }) })
    await state.run()
    expect(state.error.value).toBe('Quota atteint')
    expect(state.working.value).toBe(false)
  })

  it('does not apply a result to another screen after unmount', async () => {
    const { state, emit } = mount(); await state.showPrompt()
    let release
    fetch.mockImplementationOnce(() => new Promise(resolve => { release = () => resolve(reply(result)) }))
    const pending = state.run(); await settle()
    apps.pop().unmount(); release(); await pending
    expect(emit).not.toHaveBeenCalledWith('result', expect.anything())
  })
})

describe('shared settings', () => {
  it('shares model choices, persists no secrets and clears credentials on account change', async () => {
    const a = mount(), b = mount()
    a.state.selectedModel.value = 'other:14b'
    expect(b.state.selectedModel.value).toBe('other:14b')
    aiCredentials.openai = 'secret-test'; await nextTick()
    expect(localStorage.getItem('ai_settings_v1')).not.toContain('secret-test')
    localStorage.setItem('auth_token', 'other-account'); syncAiIdentity()
    expect(aiCredentials.openai).toBe('')
  })

  it('preserves an unavailable chosen model and disables generation instead of switching it', async () => {
    const { state } = mount(); await settle()
    state.selectedModel.value = 'uninstalled:70b'; await refreshAiCatalog()
    expect(state.selectedModel.value).toBe('uninstalled:70b')
    expect(state.ready.value).toBe(false)
  })

  it('ignores discovery for a previous Ollama address', async () => {
    let release
    fetch.mockImplementationOnce(() => new Promise(resolve => { release = () => resolve(reply(catalog)) }))
    const pending = refreshAiCatalog()
    aiSettings.ollamaUrl = 'http://localhost:11435'
    release(); await pending
    expect(aiCatalog.url).not.toBe(aiSettings.ollamaUrl)
  })
})
