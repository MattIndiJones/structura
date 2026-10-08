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

/** Turn structured API validation errors into actionable French messages. */
export function apiErrorMessage(data, fallback = 'La demande n’a pas pu être traitée.') {
  const detail = data?.detail
  if (typeof detail === 'string') return detail
  if (typeof detail?.message === 'string') return detail.message
  if (!Array.isArray(detail) || !detail.length) return fallback
  const labels = {
    strike_date: 'StartDate / date de strike', anchor: 'StartDate / date de strike',
    value_date: 'Date de valeur', maturity_date: 'Date de maturité',
    payment_date: 'Date de paiement', valuation_date: 'Date de valorisation',
    T: 'Durée entre StartDate et maturité', N: 'Nombre de trajectoires',
    r: 'Taux sans risque', sigma: 'Volatilité', q: 'Dividende',
    spot0: 'Cours initial en devise', script: 'Script PayScript',
    vol_surface: 'Surface de volatilité', surface: 'Surface de volatilité',
    first_observation_date: 'Première observation', end_date: 'Dernière observation',
    frequency: 'Fréquence des observations', date: 'Date de constatation',
  }
  const messages = detail.map(issue => {
    if (typeof issue === 'string') return issue
    const path = Array.isArray(issue?.loc) ? issue.loc.filter(x => x !== 'body' && x !== 'query') : []
    const field = path.at(-1)
    const label = labels[field] || (path.includes('user_params') ? `Paramètre ${field}` : 'Une valeur saisie')
    const prefix = path[0] === 'underlyings' && Number.isInteger(path[1])
      ? `Sous-jacent ${path[1] + 1} — ` : ''
    let instruction = 'valeur invalide, à corriger.'
    const type = issue?.type || ''
    if (type==='value_error' && (path.includes('surface') || path.includes('vol_surface')))
      return `Surface de volatilité : ${String(issue.msg || '').replace(/^Value error, /,'')}`
    if (type === 'missing' || issue?.input === null || issue?.input === '') instruction = 'à renseigner.'
    else if (type.startsWith('date')) instruction = 'renseignez une date valide.'
    else if (/^(float|int|finite_number)/.test(type)) instruction = 'renseignez un nombre valide.'
    else if (type === 'greater_than') instruction = `la valeur doit être supérieure à ${issue.ctx?.gt}.`
    else if (type === 'greater_than_equal') instruction = `la valeur doit être au moins égale à ${issue.ctx?.ge}.`
    else if (type === 'less_than') instruction = `la valeur doit être inférieure à ${issue.ctx?.lt}.`
    else if (type === 'less_than_equal') instruction = `la valeur doit être au plus égale à ${issue.ctx?.le}.`
    return `${prefix}${label} : ${instruction}`
  })
  return [...new Set(messages)].join('\n')
}
