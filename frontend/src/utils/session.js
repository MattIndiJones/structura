// Browser sessions belong to a tab. Never import the former shared token.
export function sessionToken() { return sessionStorage.getItem('auth_token') }
export function sessionInstallation() {
  try { return JSON.parse(sessionStorage.getItem('auth_installation') || 'null') } catch { return null }
}
export function installationUrl(installation) {
  if (!installation) return ''
  if (!/^http:\/\/127\.0\.0\.1:\d{4,5}$/.test(installation.url || '')) throw new Error('Adresse d’installation invalide.')
  return installation.url
}
export function sessionUrl(path) { return installationUrl(sessionInstallation()) + path }
export function portalFetch(path, options = {}) {
  if (!String(path).startsWith('/api/platform/')) throw new Error('Chemin du portail invalide.')
  return fetch(path, options)
}
let epoch = 0
const pending = new Set()
export function cancelSessionRequests() {
  epoch++
  for (const controller of pending) controller.abort()
  pending.clear()
}
export async function sessionFetch(path, options = {}) {
  if (!String(path).startsWith('/api/') && path !== '/health') throw new Error('Chemin API invalide.')
  const version = epoch, controller = new AbortController()
  pending.add(controller)
  const abort = () => controller.abort()
  options.signal?.addEventListener('abort', abort, { once: true })
  if (options.signal?.aborted) controller.abort()
  try {
    const response = await fetch(sessionUrl(path), { ...options, signal: controller.signal })
    if (version !== epoch) throw new DOMException('Le contexte a changé.', 'AbortError')
    return response
  } finally {
    pending.delete(controller)
    options.signal?.removeEventListener('abort', abort)
  }
}
export function saveSession(token, installation) {
  cancelSessionRequests()
  sessionStorage.setItem('auth_token', token)
  if (installation) sessionStorage.setItem('auth_installation', JSON.stringify(installation))
  else sessionStorage.removeItem('auth_installation')
  localStorage.removeItem('auth_token')
}
export function clearSession() {
  cancelSessionRequests()
  sessionStorage.removeItem('auth_token')
  sessionStorage.removeItem('auth_installation')
  sessionStorage.removeItem('development_admin_token')
  localStorage.removeItem('auth_token')
}
