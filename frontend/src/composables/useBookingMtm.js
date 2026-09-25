import { reactive, ref } from 'vue'
import { apiFetch } from '../utils/api.js'

export function localDay(date = new Date()) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
}

// SQLite timestamps are UTC, even when the serialized value has no suffix.
export function runTimestamp(value) {
  if (!value) return null
  const date = new Date(/[zZ]|[+-]\d\d:\d\d$/.test(value) ? value : `${value}Z`)
  return Number.isNaN(date.getTime()) ? null : date
}

export async function readMtmResponse(response, onProgress, interruptedMessage = 'Le calcul a été interrompu avant réception du résultat. Relancez le MtM.') {
  if (!response.ok || !response.headers?.get('content-type')?.includes('application/x-ndjson')) {
    const data = await response.json()
    if (!response.ok) throw new Error(data.detail?.message || data.detail || 'Erreur MtM')
    return data
  }
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let result
  const consume = line => {
    if (!line.trim()) return
    const event = JSON.parse(line)
    if (event.type === 'progress') onProgress(event.phase)
    if (event.type === 'error') throw new Error(event.detail?.message || event.detail || 'Erreur MtM')
    if (event.type === 'result') result = event.data
  }
  try {
    while (true) {
      const { value, done } = await reader.read()
      buffer += decoder.decode(value, { stream: !done })
      const lines = buffer.split('\n')
      buffer = lines.pop()
      for (const line of lines) consume(line)
      if (done) break
    }
    consume(buffer)
    if (!result) throw new Error(interruptedMessage)
    return result
  } finally {
    reader.releaseLock()
  }
}

export function useBookingMtm() {
  const todayIso = ref(localDay())
  const mtmLoading = reactive({})
  const mtmResults = reactive({})
  const mtmMode = reactive({})
  const mtmDate = reactive({})
  const mtmProgress = reactive({})
  const runningGeneration = {}
  const restored = new Set()
  const revisions = {}
  let generation = 0

  function syncDay() {
    const today = localDay()
    if (today === todayIso.value) return
    todayIso.value = today
    generation++
    for (const state of [mtmResults, mtmMode, mtmDate]) {
      for (const id of Object.keys(state)) delete state[id]
    }
    restored.clear()
  }

  // Reopen a deal on its booked model and calibration. Realized volatility is
  // an explicit alternative: it deliberately switches the engine to GBM.
  const mtmModeFor = id => mtmMode[id] || 'booking'
  const mtmDateFor = id => mtmDate[id] || todayIso.value
  function invalidate(id) {
    revisions[id] = (revisions[id] || 0) + 1
    mtmResults[id] = null
  }
  function setMtmMode(id, mode) {
    syncDay()
    if (mtmLoading[id] || mtmModeFor(id) === mode) return
    mtmMode[id] = mode
    invalidate(id)
  }
  function setMtmDate(id, date) {
    syncDay()
    const next = date || todayIso.value
    if (mtmLoading[id] || mtmDateFor(id) === next) return
    mtmDate[id] = next
    invalidate(id)
  }

  async function loadSavedMtms(ids) {
    syncDay()
    const pending = [...new Set(ids)].filter(id => id && !restored.has(id) && !mtmLoading[id])
    if (!pending.length) return
    const day = todayIso.value
    const epoch = generation
    const versions = Object.fromEntries(pending.map(id => [id, revisions[id] || 0]))
    pending.forEach(id => restored.add(id))
    // Local calendar boundaries, converted to UTC for the database (DST-safe).
    const start = new Date(`${day}T00:00:00`)
    const end = new Date(start)
    end.setDate(end.getDate() + 1)
    const query = new URLSearchParams({
      deal_ids: pending.join(','), created_from: start.toISOString(),
      created_before: end.toISOString(), valuation_date: day, recalibrate: 'none',
    })
    try {
      const response = await apiFetch(`/api/deals/valuation-runs/latest-mtm?${query}`)
      if (!response.ok) throw new Error('Historique indisponible')
      const runs = await response.json()
      syncDay()
      if (generation !== epoch) return
      for (const saved of runs) {
        const id = saved.deal_id
        const result = saved.result || {}
        const request = saved.diagnostics?.request || {}
        const timestamp = runTimestamp(saved.created_at)
        const valuationDate = result.valuation_date || request.valuation_date
        if (!(id in versions) || versions[id] !== (revisions[id] || 0) || mtmLoading[id] || mtmResults[id]) continue
        if (!timestamp || localDay(timestamp) !== day || valuationDate !== day) continue
        if (request.recalibrate !== 'none' || request.r != null || Object.keys(request.overrides || {}).length || (request.window_days ?? 252) !== 252) continue
        if (mtmModeFor(id) !== 'booking' || mtmDateFor(id) !== day) continue
        if (result.mtm == null && !result.resolved_pending) continue
        mtmResults[id] = { ...result, _runCreatedAt: timestamp.toISOString(), _restored: true }
      }
    } catch {
      if (generation === epoch) pending.forEach(id => restored.delete(id))
    }
  }

  async function runMtm(id) {
    syncDay()
    if (mtmLoading[id]) return
    const epoch = generation
    runningGeneration[id] = epoch
    invalidate(id)
    mtmLoading[id] = true
    mtmProgress[id] = 'preparing'
    try {
      const response = await apiFetch(`/api/deals/${id}/mtm?stream=true`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          recalibrate: mtmModeFor(id) === 'realized' ? 'realized' : 'none',
          valuation_date: mtmDateFor(id),
        }),
      })
      const data = await readMtmResponse(response, phase => { mtmProgress[id] = phase })
      syncDay()
      if (generation === epoch) mtmResults[id] = { ...data, _runCreatedAt: new Date().toISOString() }
    } catch (e) {
      syncDay()
      if (generation === epoch) mtmResults[id] = { error: e.message }
    } finally {
      mtmLoading[id] = false
      delete mtmProgress[id]
      delete runningGeneration[id]
    }
  }

  function mtmProgressLabel(id) {
    if (mtmLoading[id] && runningGeneration[id] !== generation) {
      return 'Fin du calcul lancé la veille — un nouveau calcul sera nécessaire pour aujourd’hui…'
    }
    return {
      preparing: 'Préparation du calcul et vérification des données de marché…',
      history: 'Chargement des cours à la date de valorisation…',
      calibration: 'Chargement et calibration des paramètres de marché…',
      pricing: 'Paramètres prêts — calcul du MtM en cours…',
      saving: 'Calcul terminé — enregistrement du résultat…',
    }[mtmProgress[id]] || 'Calcul du MtM en cours…'
  }

  return {
    todayIso, mtmLoading, mtmResults, mtmModeFor, mtmDateFor, setMtmMode, setMtmDate,
    loadSavedMtms, loadSavedMtm: id => loadSavedMtms([id]), runMtm, mtmProgressLabel, syncDay,
  }
}
