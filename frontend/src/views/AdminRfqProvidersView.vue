<template>
  <div class="flex-1 flex flex-col min-h-0">

    <main class="flex-1 p-6 max-w-3xl w-full mx-auto flex flex-col gap-4">
      <div class="page-header">
        <div>
          <h1 class="page-title">Fournisseurs RFQ</h1>
        </div>
        <div class="page-actions">
          <RouterLink to="/admin" class="btn-ghost btn-sm">← Administration</RouterLink>
        </div>
      </div>

      <AlertMessage v-if="error" kind="error">{{ error }}</AlertMessage>

      <div class="card overflow-x-auto">
        <LoadingSpinner v-if="loading" class="py-6" />
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
import { apiFetch } from '../utils/api.js'
import LoadingSpinner from '../components/ui/LoadingSpinner.vue'
import AlertMessage from '../components/ui/AlertMessage.vue'
import { useToastsStore } from '../stores/toasts.js'

const toasts = useToastsStore()
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
    toasts.success('Fournisseur ajouté')
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
