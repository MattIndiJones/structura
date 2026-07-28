<template>
  <div class="flex-1 flex flex-col min-h-0">

    <main class="flex-1 p-6 max-w-2xl w-full mx-auto flex flex-col gap-4">
      <div class="page-header">
        <div>
          <h1 class="page-title">Entités</h1>
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
              <th class="py-1.5 pr-3 font-medium">Nom</th>
              <th class="py-1.5 pr-3 font-medium">Créée le</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="e in entities" :key="e.id" class="border-b border-slate-800/60">
              <td class="py-1.5 pr-3">
                <input class="input py-1 px-2" :value="e.name"
                       @change="updateEntity(e, $event.target.value)" />
              </td>
              <td class="py-1.5 pr-3 text-slate-500">{{ formatDate(e.created_at) }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="card flex items-end gap-2">
        <div class="flex flex-col gap-1 flex-1">
          <label class="label">Nouvelle entité</label>
          <input v-model="newName" type="text" class="input" placeholder="Ex: UTI" @keyup.enter="createEntity" />
        </div>
        <button class="btn-primary text-xs px-3 py-2" :disabled="creating" @click="createEntity">Ajouter</button>
      </div>
    </main>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { RouterLink } from 'vue-router'
import { apiFetch } from '../utils/api.js'
import LoadingSpinner from '../components/ui/LoadingSpinner.vue'
import AlertMessage from '../components/ui/AlertMessage.vue'
import { formatDate } from '../utils/format.js'

const entities = ref([])
const loading  = ref(true)
const error    = ref('')
const notice   = ref('')
const creating = ref(false)
const newName  = ref('')

async function fetchEntities() {
  loading.value = true
  try {
    const res = await apiFetch('/api/admin/entities')
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || 'Erreur chargement')
    entities.value = await res.json()
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}
onMounted(fetchEntities)

async function createEntity() {
  const name = newName.value.trim()
  if (!name) return
  creating.value = true
  error.value = ''
  notice.value = ''
  try {
    const res = await apiFetch('/api/admin/entities', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name }),
    })
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || 'Erreur création')
    entities.value.push(await res.json())
    entities.value.sort((a, b) => a.name.localeCompare(b.name))
    newName.value = ''
    notice.value = 'Entité ajoutée'
  } catch (e) {
    error.value = e.message
  } finally {
    creating.value = false
  }
}

async function updateEntity(e, name) {
  error.value = ''
  notice.value = ''
  try {
    const res = await apiFetch(`/api/admin/entities/${e.id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name }),
    })
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || 'Erreur mise à jour')
    Object.assign(e, await res.json())
  } catch (err) {
    error.value = err.message
  }
}
</script>
