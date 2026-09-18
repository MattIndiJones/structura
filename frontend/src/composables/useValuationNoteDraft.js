import { computed, ref, watch } from 'vue'
import { apiFetch } from '../utils/api.js'

export async function noteJson(url, options = {}) {
  const response = await apiFetch(url, { ...options, headers: { 'Content-Type': 'application/json', ...options.headers } })
  if (response.status === 404 && (url === '/api/valuation-notes' || url.startsWith('/api/valuation-notes/sources/'))) {
    throw new Error('Valo Explain n’est pas disponible côté serveur. Relancez le backend puis rechargez cette page.')
  }
  const data = await response.json()
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'La demande a échoué.')
  return data
}

// Serialize saves and preserve edits made while the previous revision is in flight.
export function useValuationNoteDraft(request = noteJson) {
  const note = ref(null), title = ref(''), draft = ref({})
  const saved = ref(''), saving = ref(false), saveError = ref('')
  const signature = computed(() => JSON.stringify({ title: title.value, draft: draft.value }))
  const dirty = computed(() => !!note.value && signature.value !== saved.value)
  let timer, pending, disposed = false

  function load(value) {
    note.value = value
    title.value = value.title
    draft.value = { ...value.draft }
    saved.value = signature.value
    saveError.value = ''
  }

  async function flush() {
    clearTimeout(timer)
    if (pending) return pending
    if (!dirty.value || disposed) return
    saving.value = true
    saveError.value = ''
    pending = Promise.resolve().then(async () => {
      try {
        while (dirty.value && !disposed) {
          const sent = signature.value, id = note.value.id, revision = note.value.revision
          const result = await request(`/api/valuation-notes/${id}`, {
            method: 'PATCH', body: JSON.stringify({ ...JSON.parse(sent), revision }),
          })
          note.value = result
          saved.value = sent
        }
      } catch (error) {
        saveError.value = error.message
        throw error
      } finally {
        saving.value = false
        pending = null
      }
    })
    return pending
  }

  const stop = watch(signature, () => {
    clearTimeout(timer)
    if (dirty.value && !saveError.value) timer = setTimeout(() => flush().catch(() => {}), 900)
  })
  function dispose() { disposed = true; clearTimeout(timer); stop() }
  return { note, title, draft, dirty, saving, saveError, signature, load, flush, dispose }
}
