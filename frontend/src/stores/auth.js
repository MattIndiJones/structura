import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { usePricingStore } from './pricing.js'
import { useProductsStore } from './products.js'
import { useRfqStore } from './rfq.js'
import { clearUnderlyings } from '../data/commonUnderlyings.js'
import { sessionToken, sessionInstallation, installationUrl, saveSession, clearSession, sessionFetch } from '../utils/session.js'
import { accessErrorMessage } from '../utils/accessErrors.js'

export const useAuthStore = defineStore('auth', () => {
  localStorage.removeItem('auth_token')
  const token = ref(sessionToken() || null)
  const installation = ref(sessionInstallation())
  const user  = ref(null)

  const isAuthenticated = computed(() => !!token.value)
  const isAdmin         = computed(() => user.value?.role === 'admin')
  const isOrganizationAdmin = computed(() => user.value?.role === 'organization_admin')
  const isPlatformAdmin = computed(() => user.value?.role === 'platform_admin')
  const canManageSimulation = computed(() => isAdmin.value || (isPlatformAdmin.value && user.value?.capabilities?.includes('simulation.manage')))
  const canAdministerOrganization = computed(() => isAdmin.value || isOrganizationAdmin.value)
  function hasBusinessCapability(capability, roles) {
    if (!user.value || user.value.is_active === false) return false
    if (user.value.installation) return user.value.capabilities?.includes(capability) === true
    return roles.includes(user.value.role)
  }
  const canPrice = computed(() => hasBusinessCapability('business.price', ['admin', 'organization_admin', 'user']))
  const canBook = computed(() => hasBusinessCapability('book', ['admin', 'organization_admin', 'ops_maker', 'user']))
  const canManageTrading = computed(() => hasBusinessCapability('trading.relationships.manage', ['admin', 'organization_admin']))
  const canSettleTrading = computed(() => hasBusinessCapability('trading.settle', ['admin', 'organization_admin', 'ops_maker']))
  const readOnly        = computed(() => user.value?.read_only === true)

  function authHeaders() {
    return token.value ? { Authorization: `Bearer ${token.value}` } : {}
  }

  function activate(accessToken, descriptor, identity) {
    saveSession(accessToken, descriptor)
    token.value = accessToken
    installation.value = descriptor
    user.value = identity
    if (identity.role === 'platform_admin') sessionStorage.setItem('development_admin_token', accessToken)
  }

  async function validatedSession(accessToken, descriptor) {
    const res = await fetch(installationUrl(descriptor) + '/api/auth/me', { headers: { Authorization: `Bearer ${accessToken}` } })
    if (!res.ok) throw new Error('La session est indisponible.')
    const identity = await res.json()
    if (descriptor && !sameInstallation(identity.installation, descriptor)) throw new Error('Installation incohérente.')
    return identity
  }

  async function login(username, password, descriptor = null) {
    if (descriptor) {
      const response = await fetch(installationUrl(descriptor) + '/api/auth/identity')
      const identity = response.ok ? (await response.json()).installation : null
      if (!sameInstallation(identity, descriptor)) throw new Error('Installation incohérente ; aucun identifiant transmis.')
    }
    const form = new FormData()
    form.append('username', username)
    form.append('password', password)
    const res = await fetch(installationUrl(descriptor) + '/api/auth/login', { method: 'POST', body: form })
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      throw new Error(err.detail || 'Identifiants incorrects')
    }
    const data = await res.json()
    const identity = await validatedSession(data.access_token, descriptor)
    activate(data.access_token, identity.installation || descriptor, identity)
  }

  async function developmentLogin(descriptor, username) {
    try {
    const headers = { 'Content-Type': 'application/json', 'X-Structura-Development': '1' }
    const central = sessionStorage.getItem('development_admin_token')
    if (central) headers.Authorization = `Bearer ${central}`
    const response = await fetch('/api/platform/development/session', { method: 'POST', headers,
      body: JSON.stringify({ installation_id: descriptor.installation_id, username,
        start_if_needed: descriptor.kind === 'organization' }) })
    const grant = await response.json()
    if (!response.ok) {
      const outdated = response.status === 422 && Array.isArray(grant.detail) && grant.detail.some(item => item.loc?.includes('start_if_needed'))
      throw new Error(outdated ? 'Fermez puis relancez Structura pour activer le changement de compte.' : typeof grant.detail === 'string' ? grant.detail : 'Accès développeur indisponible.')
    }
    let accessToken = grant.access_token
    if (grant.ticket) {
      const redeemed = await fetch(installationUrl(descriptor) + '/api/auth/development-session', {
        method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Structura-Development': '1' },
        body: JSON.stringify({ ticket: grant.ticket }) })
      const data = await redeemed.json()
      if (!redeemed.ok) throw new Error(data.detail || 'Installation indisponible.')
      accessToken = data.access_token
    }
    const identity = await validatedSession(accessToken, descriptor)
    // Callers can check the open dossier before replacing the active identity.
    return { accessToken, descriptor, identity }
    } catch (error) { throw new Error(accessErrorMessage(error)) }
  }

  async function fetchMe() {
    if (!token.value) return
    const expectedToken = token.value
    try {
      const res = await sessionFetch('/api/auth/me', { headers: authHeaders() })
      if (!res.ok) { if (token.value === expectedToken) clearLocal(); return }
      if (token.value !== expectedToken) return
      user.value = await res.json()
      if (installation.value && !sameInstallation(user.value.installation, installation.value)) clearLocal()
    } catch {
      if (token.value === expectedToken) clearLocal()
    }
  }

  async function developmentAdminLogin() {
    const response = await fetch('/api/auth/development-admin-session', { method: 'POST',
      headers: { 'X-Structura-Development': '1' } })
    const data = await response.json()
    if (!response.ok) throw new Error(data.detail || 'Accès Admin indisponible.')
    const identity = await validatedSession(data.access_token, null)
    if (identity.role !== 'admin' || !identity.admin_workbench) throw new Error('Workspace Admin incohérent.')
    activate(data.access_token, null, identity)
  }

  async function openConsultation(accessToken) {
    const health = await sessionFetch('/health').then(res => res.json())
    if (health.read_only !== true) throw new Error('Cette installation ne permet pas la consultation protégée.')
    token.value = accessToken
    saveSession(accessToken, null)
    await fetchMe()
    if (!readOnly.value) {
      logout()
      throw new Error('La session de consultation est indisponible.')
    }
  }

  function clearLocal() {
    token.value = null
    user.value  = null
    installation.value = null
    clearSession()
    clearUnderlyings()
    usePricingStore().releaseSession()
    const products = useProductsStore()
    products.release()
    products.items = []
    products.error = ''
    const rfqs = useRfqStore()
    rfqs.list = []
    rfqs.current = null
    rfqs.lastPricing = null
    rfqs.history = []
  }

  async function logout() {
    const activeToken = token.value, descriptor = installation.value
    const centralToken = sessionStorage.getItem('development_admin_token')
    clearLocal()
    const sessions = activeToken ? [[activeToken, descriptor]] : []
    if (centralToken && centralToken !== activeToken) sessions.push([centralToken, null])
    const results = await Promise.all(sessions.map(async ([value, target]) => {
      try {
        const response = await fetch(installationUrl(target) + '/api/auth/logout', { method: 'POST',
          headers: { Authorization: `Bearer ${value}` }, signal: AbortSignal.timeout(10000) })
        return response.ok || response.status === 401
      } catch { return false }
    }))
    const revoked = results.every(Boolean)
    if (!revoked) sessionStorage.setItem('auth_notice', 'Session locale fermée. Révocation serveur non confirmée ; utilisez « Révoquer toutes mes sessions » dès la reconnexion.')
    return revoked
  }

  return { token, user, installation, isAuthenticated, isAdmin, isPlatformAdmin, canManageSimulation, isOrganizationAdmin, canAdministerOrganization, canPrice, canBook, canManageTrading, canSettleTrading, readOnly,
    login, activate, developmentLogin, developmentAdminLogin, fetchMe, openConsultation, logout, authHeaders }
})

function sameInstallation(actual, expected) {
  return actual?.installation_id === expected.installation_id
    && actual?.organization_id === expected.organization_id && actual?.kind === expected.kind
}
