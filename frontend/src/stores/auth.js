import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export const useAuthStore = defineStore('auth', () => {
  const token = ref(localStorage.getItem('auth_token') || null)
  const user  = ref(null)

  const isAuthenticated = computed(() => !!token.value)
  const isAdmin         = computed(() => user.value?.role === 'admin')

  function authHeaders() {
    return token.value ? { Authorization: `Bearer ${token.value}` } : {}
  }

  async function login(username, password) {
    const form = new FormData()
    form.append('username', username)
    form.append('password', password)
    const res = await fetch('/api/auth/login', { method: 'POST', body: form })
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      throw new Error(err.detail || 'Identifiants incorrects')
    }
    const data = await res.json()
    token.value = data.access_token
    localStorage.setItem('auth_token', data.access_token)
    await fetchMe()
  }

  async function fetchMe() {
    if (!token.value) return
    try {
      const res = await fetch('/api/auth/me', { headers: authHeaders() })
      if (!res.ok) { logout(); return }
      user.value = await res.json()
    } catch {
      logout()
    }
  }

  function logout() {
    token.value = null
    user.value  = null
    localStorage.removeItem('auth_token')
  }

  return { token, user, isAuthenticated, isAdmin, login, fetchMe, logout, authHeaders }
})
