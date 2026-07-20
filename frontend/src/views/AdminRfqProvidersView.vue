<template>
  <div class="min-h-screen bg-slate-950 flex flex-col">

    <!-- Header -->
    <header class="border-b border-slate-800 px-6 py-3 flex items-center gap-4 sticky top-0 z-20 bg-slate-950/95 backdrop-blur">
      <RouterLink to="/" class="flex items-center gap-2.5 hover:opacity-80 transition-opacity">
        <img src="/tp_logo.png" alt="TP Advisory" class="h-7 w-7 rounded-sm bg-white object-contain p-0.5">
        <span class="font-bold text-slate-100 tracking-tight">Structura</span>
        <span class="text-slate-600 text-xs">/ Fournisseurs RFQ</span>
      </RouterLink>
      <RouterLink to="/admin" class="btn-secondary text-xs px-3 py-1.5">← Administration</RouterLink>
      <span class="text-xs text-slate-500 ml-auto">{{ auth.user?.username }}</span>
    </header>

    <main class="flex-1 p-6 max-w-3xl w-full mx-auto flex flex-col gap-4">
      <div v-if="error" class="bg-red-950/60 border border-red-800 rounded px-3 py-2 text-xs text-red-300">{{ error }}</div>

      <div class="card overflow-x-auto">
        <div v-if="loading" class="text-xs text-slate-600 py-6 text-center">Chargement…</div>
        <table v-else class="w-full text-xs">
          <thead>
            <tr class="text-left text-slate-500 border-b border-slate-800">
              <th class="py-1.5 pr-3 font-medium">Nom</th>
              <th class="py-1.5 pr-3 font-medium">Mode</th>
              <th class="py-1.5 pr-3 font-medium">Actif</th>
              <th class="py-1.5 pr-3 font-medium"></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="p in providers" :key="p.id" class="border-b border-slate-800/60">
              <td class="py-1.5 pr-3">
                <input class="input py-1 px-2" :value="p.label"
                       @change="updateProvider(p, { label: $event.target.value })" />
              </td>
              <td class="py-1.5 pr-3">
                <select class="select py-1 px-2" :value="p.mode"
                        @change="updateProvider(p, { mode: $event.target.value })">
                  <option value="manual">Manuel</option>
                  <option value="api">API</option>
                </select>
              </td>
              <td class="py-1.5 pr-3">
                <input type="checkbox" class="accent-blue-500" :checked="p.active"
                       @change="updateProvider(p, { active: $event.target.checked })" />
              </td>
              <td class="py-1.5 pr-3 text-right">
                <button class="text-slate-600 hover:text-red-400" title="Supprimer" @click="deleteProvider(p)">🗑</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="card flex items-end gap-2">
        <div class="flex flex-col gap-1 flex-1">
          <label class="label">Nouveau fournisseur</label>
          <input v-model="newLabel" type="text" class="input" placeholder="Ex: Citi" @keyup.enter="createProvider" />
        </div>
        <div class="flex flex-col gap-1">
          <label class="label">Mode</label>
          <select v-model="newMode" class="select">
            <option value="manual">Manuel</option>
            <option value="api">API</option>
          </select>
        </div>
        <button class="btn-primary text-xs px-3 py-2" :disabled="creating" @click="createProvider">Ajouter</button>
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

const providers = ref([])
const loading   = ref(true)
const error     = ref('')
const creating  = ref(false)
const newLabel  = ref('')
const newMode   = ref('manual')

async function fetchProviders() {
  loading.value = true
  try {
    const res = await apiFetch('/api/admin/rfq-providers')
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || 'Erreur chargement')
    providers.value = await res.json()
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

onMounted(fetchProviders)

async function createProvider() {
  const label = newLabel.value.trim()
  if (!label) return
  creating.value = true
  error.value = ''
  try {
    const res = await apiFetch('/api/admin/rfq-providers', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ label, mode: newMode.value }),
    })
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || 'Erreur création')
    providers.value.push(await res.json())
    providers.value.sort((a, b) => a.label.localeCompare(b.label))
    newLabel.value = ''
    newMode.value = 'manual'
  } catch (e) {
    error.value = e.message
  } finally {
    creating.value = false
  }
}

async function updateProvider(p, payload) {
  error.value = ''
  try {
    const res = await apiFetch(`/api/admin/rfq-providers/${p.id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || 'Erreur mise à jour')
    Object.assign(p, await res.json())
  } catch (e) {
    error.value = e.message
  }
}

async function deleteProvider(p) {
  if (!confirm(`Supprimer "${p.label}" ?`)) return
  error.value = ''
  try {
    const res = await apiFetch(`/api/admin/rfq-providers/${p.id}`, { method: 'DELETE' })
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || 'Erreur suppression')
    providers.value = providers.value.filter(x => x.id !== p.id)
  } catch (e) {
    error.value = e.message
  }
}
</script>
