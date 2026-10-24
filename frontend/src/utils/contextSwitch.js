import { installationUrl } from './session.js'

// A local number only has meaning inside its installation. A profile switch
// may retain a dossier after a fresh authorization check by its own server.
export async function destinationForContext(route, current, next, accessToken, identity, request = fetch) {
  const home = next.kind === 'platform' ? '/platform' : '/'
  if (current?.installation_id !== next.installation_id) return home
  if (identity.role === 'platform_admin') return home
  if (route.meta.requiresTechnicalAdmin || (route.meta.requiresAdmin && identity.role !== 'organization_admin')) return home
  if (route.path.includes('pricer') && !identity.capabilities?.includes('business.price')) return home
  if (route.meta.requiresBooking && !identity.capabilities?.includes('book')) return home
  const path = route.path
  let endpoint
  let match = path.match(/^\/products\/(\d+)\/pricer$/)
  if (match) endpoint = `/api/products/${match[1]}`
  match = path.match(/^\/pricer\/(\d+)$/)
  if (match) endpoint = `/api/db/scripts/${match[1]}`
  match = path.match(/^\/rfq\/(\d+)$/)
  if (match) endpoint = `/api/rfq/${match[1]}`
  match = path.match(/^\/rfq\/(\d+)\/booking$/)
  if (match) endpoint = `/api/rfq/${match[1]}/booking-review`
  match = path.match(/^\/clients\/fiche\/(\d+)/)
  if (match) endpoint = `/api/clients/${match[1]}`
  match = path.match(/^\/booking\/(\d+)\/valuations$/)
  if (match) endpoint = `/api/deals/${match[1]}`
  if (!endpoint && (/\d/.test(path) || Object.keys(route.query || {}).some(key => /id|rfq|product|deal|script|variant/i.test(key)))) return home
  if (endpoint) {
    try { const res = await request(installationUrl(next) + endpoint, { headers: { Authorization: `Bearer ${accessToken}` } }); if (!res.ok) return home }
    catch { return home }
  }
  return route.fullPath
}
