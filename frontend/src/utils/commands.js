import { sessionInstallation, sessionToken } from './session.js'

const storageKey = 'structura_pending_commands_v1'
const inFlight = new Map()

function canonical(value) {
  if (Array.isArray(value)) return value.map(canonical)
  if (value && typeof value === 'object') return Object.fromEntries(
    Object.keys(value).sort().filter(key => value[key] !== undefined).map(key => [key, canonical(value[key])]))
  return value
}

async function digest(value) {
  const bytes = new TextEncoder().encode(JSON.stringify(canonical(value)))
  return [...new Uint8Array(await globalThis.crypto.subtle.digest('SHA-256', bytes))]
    .map(byte => byte.toString(16).padStart(2, '0')).join('')
}

function readPending() {
  const value = JSON.parse(sessionStorage.getItem(storageKey) || '{}')
  if (!value || Array.isArray(value) || typeof value !== 'object') {
    throw new Error('Le registre des commandes en attente est illisible.')
  }
  return value
}

function actor(token) {
  try {
    const data = JSON.parse(atob(token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')))
    return [data.sub, data.entity_id]
  } catch { return token }
}

/** Retain only a digest and a random key until a response is fully confirmed. */
export function durableCommand(operation, payload, send) {
  const token = sessionToken(), installation = JSON.stringify(sessionInstallation())
  const flightId = JSON.stringify(canonical([token, installation, operation, payload]))
  if (inFlight.has(flightId)) return inFlight.get(flightId)
  const task = runCommand(operation, payload, send, token, installation)
  inFlight.set(flightId, task)
  return task.finally(() => { if (inFlight.get(flightId) === task) inFlight.delete(flightId) })
}

async function runCommand(operation, payload, send, token, installation) {
  const id = await digest([installation, actor(token), operation, payload])
  if (token !== sessionToken() || installation !== JSON.stringify(sessionInstallation())) {
    throw new DOMException('Le contexte a changé.', 'AbortError')
  }
  const pending = readPending()
  const key = pending[id] || `${operation}-${globalThis.crypto.randomUUID()}`
  pending[id] = key
  // A failed storage write stops the action before it can reach the server.
  sessionStorage.setItem(storageKey, JSON.stringify(pending))
  const result = await send(key)
  if (token !== sessionToken() || installation !== JSON.stringify(sessionInstallation())) {
    throw new DOMException('Le contexte a changé.', 'AbortError')
  }
  const latest = readPending()
  if (latest[id] === key) delete latest[id]
  sessionStorage.setItem(storageKey, JSON.stringify(latest))
  return result
}
