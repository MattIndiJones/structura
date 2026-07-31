<template>
  <div class="flex-1 flex flex-col min-h-0">

    <main class="flex-1 p-6 max-w-4xl w-full mx-auto flex flex-col gap-4">
      <div class="page-header">
        <div>
          <h1 class="page-title">Utilisateurs</h1>
        </div>
        <div class="page-actions">
          <RouterLink to="/admin" class="btn-ghost btn-sm">← Administration</RouterLink>
        </div>
      </div>

      <AlertMessage v-if="error" kind="error">{{ error }}</AlertMessage>
      <AlertMessage v-if="notice" kind="success" dismissible @dismiss="notice = ''">{{ notice }}</AlertMessage>

      <div class="card overflow-x-auto">
        <LoadingSpinner v-if="loading" class="py-6" />
        <table v-else class="w-full text-xs">
          <thead>
            <tr class="text-left text-slate-500 border-b border-slate-800">
              <th class="py-1.5 pr-3 font-medium">Identifiant</th>
              <th class="py-1.5 pr-3 font-medium">E-mail</th>
              <th class="py-1.5 pr-3 font-medium">Rôle</th>
              <th class="py-1.5 pr-3 font-medium">Entité</th>
              <th class="py-1.5 pr-3 font-medium">Actif</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="u in users" :key="u.id" class="border-b border-slate-800/60">
              <td class="py-1.5 pr-3 text-slate-200">{{ u.username }}</td>
              <td class="py-1.5 pr-3">
                <input class="input py-1 px-2" :value="u.email"
                       @change="updateUser(u, { email: $event.target.value })" />
              </td>
              <td class="py-1.5 pr-3">
                <select class="select py-1 px-2" :value="u.role"
                        @change="updateUser(u, { role: $event.target.value })">
                  <option value="user">Utilisateur</option>
                  <option value="checker">Checker opérations</option>
                  <option value="admin">Admin</option>
                </select>
              </td>
              <td class="py-1.5 pr-3">
                <select class="select py-1 px-2" :value="u.entity_id"
                        @change="updateUser(u, { entity_id: Number($event.target.value) })">
                  <option v-for="e in entities" :key="e.id" :value="e.id">{{ e.name }}</option>
                </select>
              </td>
              <td class="py-1.5 pr-3">
                <input type="checkbox" class="accent-blue-500" :checked="u.is_active"
                       @change="updateUser(u, { is_active: $event.target.checked })" />
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="card flex flex-col gap-3">
        <div class="label mb-0">Nouvel utilisateur</div>
        <div class="grid grid-cols-2 sm:grid-cols-5 gap-2 items-end">
          <div class="flex flex-col gap-1">
            <label class="label">Identifiant</label>
            <input v-model="form.username" type="text" class="input" />
          </div>
          <div class="flex flex-col gap-1">
            <label class="label">E-mail</label>
            <input v-model="form.email" type="email" class="input" />
          </div>
          <div class="flex flex-col gap-1">
            <label class="label">Mot de passe</label>
            <input v-model="form.password" type="password" class="input" />
          </div>
          <div class="flex flex-col gap-1">
            <label class="label">Rôle</label>
            <select v-model="form.role" class="select">
              <option value="user">Utilisateur</option>
              <option value="checker">Checker opérations</option>
              <option value="admin">Admin</option>
            </select>
          </div>
          <div class="flex flex-col gap-1">
            <label class="label">Entité</label>
            <select v-model="form.entity_id" class="select">
              <option v-for="e in entities" :key="e.id" :value="e.id">{{ e.name }}</option>
            </select>
          </div>
        </div>
        <button class="btn-primary text-xs px-3 py-2 w-fit" :disabled="creating" @click="createUser">Créer</button>
      </div>
    </main>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { RouterLink } from 'vue-router'
import { apiFetch } from '../utils/api.js'
import LoadingSpinner from '../components/ui/LoadingSpinner.vue'
import AlertMessage from '../components/ui/AlertMessage.vue'

const users    = ref([])
const entities = ref([])
const loading  = ref(true)
const error    = ref('')
const notice   = ref('')
const creating = ref(false)

const form = reactive({ username: '', email: '', password: '', role: 'user', entity_id: null })

async function fetchAll() {
  loading.value = true
  try {
    const [uRes, eRes] = await Promise.all([
      apiFetch('/api/admin/users'),
      apiFetch('/api/admin/entities'),
    ])
    if (!uRes.ok) throw new Error((await uRes.json().catch(() => ({}))).detail || 'Erreur chargement utilisateurs')
    if (!eRes.ok) throw new Error((await eRes.json().catch(() => ({}))).detail || 'Erreur chargement entités')
    users.value = await uRes.json()
    entities.value = await eRes.json()
    if (entities.value.length) form.entity_id = entities.value[0].id
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}
onMounted(fetchAll)

async function createUser() {
  if (!form.username.trim() || !form.email.trim() || !form.password) {
    error.value = 'Identifiant, e-mail et mot de passe sont requis'
    return
  }
  creating.value = true
  error.value = ''
  notice.value = ''
  try {
    const res = await apiFetch('/api/admin/users', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(form),
    })
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || 'Erreur création')
    users.value.push(await res.json())
    users.value.sort((a, b) => a.username.localeCompare(b.username))
    form.username = ''; form.email = ''; form.password = ''; form.role = 'user'
    notice.value = 'Utilisateur créé'
  } catch (e) {
    error.value = e.message
  } finally {
    creating.value = false
  }
}

async function updateUser(u, payload) {
  error.value = ''
  notice.value = ''
  try {
    const res = await apiFetch(`/api/admin/users/${u.id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || 'Erreur mise à jour')
    Object.assign(u, await res.json())
  } catch (e) {
    error.value = e.message
  }
}
</script>
