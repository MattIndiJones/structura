import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { aiSettings as settings, aiCredentials as credentials, aiCatalog as catalog, aiPost, refreshAiCatalog, syncAiIdentity } from './useAiSettings'

// A prompt belongs to its input context. Keep edited text for review on context
// changes, but prevent stale submissions and discard late results from old inputs.
export function useAiWorkbench(props, emit) {
  const working = ref(false), phase = ref(''), seconds = ref(0), error = ref(''), expanded = ref(false), copied = ref(false)
  const prompt = ref(null), stale = ref(false), last = ref(null)
  const draft = reactive({ system: '', user: '' })
  const key = computed(() => JSON.stringify([props.endpoint, props.payload, props.contextKey]))
  const provider = computed(() => catalog.providers.find(p => p.key === settings.provider))
  const models = computed(() => provider.value?.models || [])
  const selectedModel = computed({ get: () => settings.models[settings.provider] || '', set: value => { settings.models[settings.provider] = value } })
  const ready = computed(() => !!selectedModel.value && !!provider.value && (settings.provider === 'ollama'
    ? catalog.url === settings.ollamaUrl && provider.value.ready && models.value.includes(selectedModel.value)
    : provider.value.ready || !!credentials[settings.provider]))
  const customized = computed(() => prompt.value && (draft.system !== prompt.value.system || draft.user !== prompt.value.user))
  let clock, alive = true
  watch(key, () => {
    if (prompt.value && customized.value) stale.value = true
    else { prompt.value = null; stale.value = false }
  }, { flush: 'sync' })
  onMounted(() => { syncAiIdentity(); refreshAiCatalog() })
  onBeforeUnmount(() => { emit('busy', false); alive = false; clearInterval(clock) })
  function begin(label) {
    working.value = true; emit('busy', true); error.value = ''; phase.value = label; seconds.value = 0
    clock = setInterval(() => seconds.value++, 1000)
  }
  function end() { clearInterval(clock); working.value = false; if (alive) emit('busy', false) }
  async function prepare() { if (props.beforePrepare) await props.beforePrepare(); await nextTick() }
  async function loadPrompt() {
    const snapshot = key.value
    const data = await aiPost(props.previewEndpoint || `${props.endpoint}/prompt`, props.payload)
    if (!alive || snapshot !== key.value) throw new Error('Le contexte a changé pendant la préparation. Réessayez.')
    if (!data.base_hash) throw new Error('Le service IA doit être redémarré pour activer le nouvel éditeur de prompt.')
    prompt.value = data; draft.system = data.system; draft.user = data.user; stale.value = false; copied.value = false
  }
  async function showPrompt() {
    if (working.value || props.disabled) return
    expanded.value = true
    if (prompt.value) return
    await resetPrompt()
  }
  async function resetPrompt() {
    if (working.value || props.disabled) return
    begin('Préparation du prompt')
    try { await prepare(); await loadPrompt() } catch (e) { error.value = e.message } finally { end() }
  }
  async function run() {
    syncAiIdentity()
    if (working.value || props.disabled || !ready.value || stale.value) return
    begin('Préparation du prompt')
    try {
      await prepare()
      if (!alive) return
      if (stale.value) throw new Error('Le contexte a changé. Reconstruisez le prompt avant de générer.')
      if (!prompt.value) await loadPrompt()
      if (!draft.system.trim() || !draft.user.trim()) throw new Error('Renseignez les deux messages du prompt avant de générer.')
      const snapshot = key.value
      const body = { ...props.payload, provider: settings.provider, model: selectedModel.value,
        ollama_url: settings.ollamaUrl, api_key: credentials[settings.provider] || '',
        prompt_override: { base_hash: prompt.value.base_hash, system: draft.system, user: draft.user } }
      phase.value = 'Génération par le modèle'
      const data = await aiPost(props.endpoint, body)
      if (!alive) return
      last.value = data
      if (snapshot !== key.value) throw new Error('Le contexte a changé pendant la génération. Le résultat n’a pas été appliqué ; relancez la demande.')
      emit('result', data)
    } catch (e) { if (alive) error.value = e.message } finally { end() }
  }
  async function copyPrompt() {
    try { await navigator.clipboard.writeText(`${draft.system}\n\n=== DEMANDE ===\n\n${draft.user}`); copied.value = true }
    catch { error.value = 'Copie indisponible. Vous pouvez sélectionner le texte dans les champs.' }
  }
  return { settings, credentials, catalog, refreshAiCatalog, working, phase, seconds,
    error, expanded, copied, prompt, stale, last, draft, provider, models, selectedModel,
    ready, customized, showPrompt, resetPrompt, run, copyPrompt }
}
