import { apiFetch } from './api.js'

export function rangeCount(range) {
  if (!range) return null
  const { minimum, maximum, step } = range
  if (![minimum, maximum, step].every(Number.isFinite) || step <= 0 || maximum < minimum) return null
  return Math.floor((maximum - minimum) / step + 1e-8) + 1
}

export function searchSize(ranges) {
  const counts = Object.entries(ranges).filter(([key])=>key!=='observation_months').map(([,range])=>rangeCount(range))
  if (!counts.length || counts.some(x => x == null) || ranges.observation_months?.length === 0) return null
  return counts.reduce((a, b) => a * b, ranges.observation_months?.length ?? 1)
}

export async function responseError(response) {
  const data = await response.json().catch(() => ({}))
  if (Array.isArray(data.detail)) return data.detail.map(e => `${e.loc?.slice(1).join('.') || 'Saisie'} : ${e.msg}`).join(' · ')
  return typeof data.detail === 'string' ? data.detail : `Erreur serveur (${response.status}).`
}

export async function optimizerJson(path, body, signal) {
  const response = await apiFetch(`/api/product-optimizer/${path}`, body ? {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body), signal,
  } : { signal })
  if (!response.ok) throw new Error(await responseError(response))
  return response.json()
}

export async function runOptimizer(body, signal, onEvent) {
  const response = await apiFetch('/api/product-optimizer/run', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body), signal,
  })
  if (!response.ok) throw new Error(await responseError(response))
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = '', receivedResult = false
  const consume = line => {
    if (!line.trim()) return
    const event = JSON.parse(line)
    if (event.type === 'error') throw new Error(event.message)
    if (event.type === 'result') receivedResult = true
    onEvent(event)
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
    if (!receivedResult) throw new Error('Flux interrompu avant le résultat final. Relancez la recherche.')
  } finally {
    await reader.cancel().catch(() => {})
    reader.releaseLock()
  }
}

export function rankedCandidates(result) {
  return (result?.candidates || []).filter(c => c.constraint_status === 'PASS'
    && (!result.validation || c.validation_status === 'PASSED')).sort((a, b) => a.rank - b.rank)
}
