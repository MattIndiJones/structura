<template>
  <div class="min-h-screen bg-slate-950 flex flex-col">

    <!-- Header -->
    <header class="border-b border-slate-800 px-6 py-3 flex items-center gap-4 sticky top-0 z-20 bg-slate-950/95 backdrop-blur">
      <RouterLink to="/" class="flex items-center gap-2.5 hover:opacity-80 transition-opacity">
        <img src="/tp_logo.png" alt="TP Advisory" class="h-7 w-7 rounded-sm bg-white object-contain p-0.5">
        <span class="font-bold text-slate-100 tracking-tight">Structura</span>
        <span class="text-slate-600 text-xs">/ Entités</span>
      </RouterLink>
      <RouterLink to="/admin" class="btn-secondary text-xs px-3 py-1.5">← Administration</RouterLink>
      <span class="text-xs text-slate-500 ml-auto">{{ auth.user?.username }}</span>
    </header>

    <main class="flex-1 p-6 max-w-2xl w-full mx-auto flex flex-col gap-4">
      <div v-if="error" class="bg-red-950/60 border border-red-800 rounded px-3 py-2 text-xs text-red-300">{{ error }}</div>

      <div class="card overflow-x-auto">
        <div v-if="loading" class="text-xs text-slate-600 py-6 text-center">Chargement…</div>
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
              <td class="py-1.5 pr-3 text-slate-500">{{ new Date(e.created_at).toLocaleDateString('fr-FR') }}</td>
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
import { useAuthStore } from '../stores/auth.js'
import { apiFetch } from '../utils/api.js'

const auth = useAuthStore()

const entities = ref([])
const loading  = ref(true)
const error    = ref('')
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
  } catch (e) {
    error.value = e.message
  } finally {
    creating.value = false
  }
}

async function updateEntity(e, name) {
  error.value = ''
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
