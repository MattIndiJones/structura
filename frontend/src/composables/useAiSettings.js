import { reactive, watch } from 'vue'
import { apiFetch } from '../utils/api'

function read(key) { try { return localStorage.getItem(key) } catch { return null } }
function saved() { try { return JSON.parse(read('ai_settings_v1') || '{}') } catch { return {} } }
const previous = saved()
const legacyProvider = read('ai_provider')
export const aiSettings = reactive({
  provider: previous.provider || (legacyProvider === 'claude' ? 'anthropic' : legacyProvider) || 'ollama',
  models: previous.models || { ollama: read('ai_ollama_model') || '', anthropic: read('ai_claude_model') || '', openai: read('ai_openai_model') || '' },
  ollamaUrl: previous.ollamaUrl || read('ai_ollama_url') || 'http://localhost:11434',
})
// Session credentials are shared, but never written to browser storage.
export const aiCredentials = reactive({ openai: '', anthropic: '' })
export const aiCatalog = reactive({ providers: [], loading: false, error: '', url: '' })
let identity = read('auth_token'), epoch = 0
watch(aiSettings, () => {
  try { localStorage.setItem('ai_settings_v1', JSON.stringify(aiSettings)) } catch { /* private browsing */ }
}, { deep: true })

export function syncAiIdentity() {
  if (identity !== read('auth_token')) {
    identity = read('auth_token')
    aiCredentials.openai = ''; aiCredentials.anthropic = ''
  }
}

export async function aiPost(endpoint, body) {
  const res = await apiFetch(endpoint, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
  const data = await res.json()
  if (!res.ok) throw new Error(typeof data.detail === 'string' ? data.detail : data.detail?.message || `Requête IA refusée (${res.status}).`)
  return data
}

export async function refreshAiCatalog() {
  syncAiIdentity()
  const request = ++epoch, url = aiSettings.ollamaUrl
  aiCatalog.loading = true; aiCatalog.error = ''
  try {
    const res = await apiFetch(`/api/ai/providers?ollama_url=${encodeURIComponent(url)}`)
    if (res.status === 404) throw new Error('Le service IA commun nécessite un redémarrage du backend, puis un rechargement de la page.')
    const data = await res.json()
    if (!res.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Catalogue IA indisponible.')
    if (request !== epoch || url !== aiSettings.ollamaUrl) return
    aiCatalog.providers = data.providers; aiCatalog.url = url
    for (const p of data.providers) {
      if (!aiSettings.models[p.key]) aiSettings.models[p.key] = p.default_model
    }
    if (!data.providers.some(p => p.key === aiSettings.provider)) aiSettings.provider = 'ollama'
  } catch (e) {
    if (request === epoch) aiCatalog.error = e.message
  } finally { if (request === epoch) aiCatalog.loading = false }
}
