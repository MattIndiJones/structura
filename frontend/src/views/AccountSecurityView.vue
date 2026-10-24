<template>
  <main class="p-6 max-w-xl mx-auto w-full flex flex-col gap-4">
    <h1 class="page-title">Sécurité du compte</h1>
    <AlertMessage v-if="auth.user?.password_change_required" kind="warning">Choisissez un mot de passe personnel avant de poursuivre.</AlertMessage>
    <AlertMessage v-if="error" kind="error">{{ error }}</AlertMessage>
    <p v-if="auth.readOnly" class="text-sm">Book en lecture seule. La révocation ferme les accès à cette consultation sans modifier l’archive.</p>
    <form v-else class="card flex flex-col gap-3" @submit.prevent="changePassword">
      <p class="text-sm">{{ auth.user?.username }} · {{ auth.user?.installation?.name || 'Workspace autonome' }}</p>
      <label class="label">Mot de passe actuel<input v-model="current" class="input" type="password" autocomplete="current-password" required /></label>
      <label class="label">Nouveau mot de passe · 12 caractères minimum<input v-model="password" class="input" type="password" autocomplete="new-password" minlength="12" required /></label>
      <label class="label">Confirmation<input v-model="confirmation" class="input" type="password" autocomplete="new-password" minlength="12" required /></label>
      <p class="text-xs text-slate-500">Le changement ferme toutes vos sessions. Vous devrez vous reconnecter.</p>
      <button class="btn-primary" :disabled="busy">Changer le mot de passe</button>
    </form>
    <button class="btn-secondary" :disabled="busy" @click="revokeAll">Révoquer toutes mes sessions</button>
  </main>
</template>
<script setup>
import { ref } from 'vue'
import { useAuthStore } from '../stores/auth.js'
import { apiFetch } from '../utils/api.js'
import AlertMessage from '../components/ui/AlertMessage.vue'
import { confirmer } from '../composables/useConfirm.js'
const auth = useAuthStore()
const current = ref(''), password = ref(''), confirmation = ref(''), error = ref(''), busy = ref(false)
async function execute(path, body) {
  busy.value = true; error.value = ''
  try {
    const response = await apiFetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, ...(body ? { body: JSON.stringify(body) } : {}) })
    if (!response.ok) { const data = await response.json().catch(() => ({})); throw new Error(typeof data.detail === 'string' ? data.detail : 'Vérifiez le mot de passe : 12 caractères minimum, 72 octets UTF-8 maximum.') }
    current.value = ''; password.value = ''; confirmation.value = ''
    await auth.logout()
    window.location.hash = '#/login'; window.location.reload()
  } catch (e) { error.value = e.message } finally { busy.value = false }
}
async function changePassword() {
  if (password.value !== confirmation.value) { error.value = 'Les mots de passe diffèrent.'; return }
  await execute('/api/auth/password', { current_password: current.value, new_password: password.value })
}
async function revokeAll() {
  if (await confirmer({ titre: 'Révoquer toutes les sessions ?', message: 'Vous devrez vous reconnecter sur chaque navigateur.', confirmer: 'Révoquer', danger: true })) await execute('/api/auth/logout-all')
}
</script>
