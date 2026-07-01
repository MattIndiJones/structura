/**
 * Thin fetch wrapper that injects the JWT Authorization header
 * when a token exists in localStorage.
 * Usage: apiFetch('/api/db/scripts', { method: 'POST', body: JSON.stringify({...}) })
 */
export function apiFetch(url, options = {}) {
  const token = localStorage.getItem('auth_token')
  const headers = { ...(options.headers || {}) }
  if (token) headers['Authorization'] = `Bearer ${token}`
  return fetch(url, { ...options, headers })
}
