<template>
  <div class="flex-1 flex flex-col min-h-0">

    <main class="flex-1 p-6 max-w-3xl w-full mx-auto flex flex-col gap-4">
      <div class="page-header">
        <div>
          <h1 class="page-title">Contreparties deals</h1>
          <p class="page-subtitle">
            Contreparties éligibles à faire face à un deal booké. Seules les contreparties actives
            apparaissent dans le formulaire de booking — décocher "Actif" retire une banque de la
            liste sans toucher aux deals existants.
          </p>
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
              <th class="py-1.5 pr-3 font-medium">Pays</th>
              <th class="py-1.5 pr-3 font-medium">Actif</th>
              <th class="py-1.5 pr-3 font-medium">Limite (EUR)</th>
              <th class="py-1.5 pr-3 font-medium"></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="c in counterparties" :key="c.id" class="border-b border-slate-800/60"
              :class="!c.active ? 'opacity-50' : ''">
              <td class="py-1.5 pr-3">
                <input class="input py-1 px-2" :value="c.name"
                       @change="updateCpty(c, { name: $event.target.value })" />
              </td>
              <td class="py-1.5 pr-3">
                <input class="input py-1 px-2 w-16 font-mono uppercase" :value="c.country" maxlength="2"
                       @change="updateCpty(c, { country: $event.target.value.toUpperCase() })" />
              </td>
              <td class="py-1.5 pr-3">
                <input type="checkbox" class="accent-blue-500" :checked="c.active"
                       @change="updateCpty(c, { active: $event.target.checked })" />
              </td>
              <td class="py-1.5 pr-3">
                <input type="number" step="100000" class="input py-1 px-2 w-28 font-mono" :value="c.limit_eur"
                       placeholder="illimité"
                       title="Limite de concentration (nominal EUR) — utilisée par Risk Management → Contreparties pour signaler un dépassement. Vide = pas de limite."
                       @change="updateCpty(c, { limit_eur: $event.target.value === '' ? null : Number($event.target.value) })" />
              </td>
              <td class="py-1.5 pr-3 text-right">
                <button class="icon-btn-danger" title="Supprimer" aria-label="Supprimer la contrepartie" @click="deleteCpty(c)">🗑</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="card flex items-end gap-2">
        <div class="flex flex-col gap-1 flex-1">
          <label class="label">Nouvelle contrepartie</label>
          <input v-model="newName" type="text" class="input" placeholder="Ex: Standard Chartered" @keyup.enter="createCpty" />
        </div>
        <div class="flex flex-col gap-1">
          <label class="label">Pays</label>
          <input v-model="newCountry" type="text" class="input w-20 font-mono uppercase" maxlength="2" placeholder="GB" />
        </div>
        <button class="btn-primary text-xs px-3 py-2" :disabled="creating" @click="createCpty">Ajouter</button>
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

const counterparties = ref([])
const loading    = ref(true)
const error      = ref('')
const notice     = ref('')
const creating   = ref(false)
const newName    = ref('')
const newCountry = ref('')

async function fetchCptys() {
  loading.value = true
  try {
    const res = await apiFetch('/api/admin/counterparties')
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || 'Erreur chargement')
    counterparties.value = await res.json()
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

onMounted(fetchCptys)

async function createCpty() {
  const name = newName.value.trim()
  if (!name) return
  creating.value = true
  error.value = ''
  notice.value = ''
  try {
    const res = await apiFetch('/api/admin/counterparties', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, country: newCountry.value.trim().toUpperCase() }),
    })
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || 'Erreur création')
    counterparties.value.push(await res.json())
    counterparties.value.sort((a, b) => a.name.localeCompare(b.name))
    newName.value = ''
    newCountry.value = ''
    notice.value = 'Contrepartie ajoutée'
  } catch (e) {
    error.value = e.message
  } finally {
    creating.value = false
  }
}

async function updateCpty(c, payload) {
  error.value = ''
  notice.value = ''
  try {
    const res = await apiFetch(`/api/admin/counterparties/${c.id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || 'Erreur mise à jour')
    Object.assign(c, await res.json())
  } catch (e) {
    error.value = e.message
  }
}

async function deleteCpty(c) {
  if (!await confirmer({ titre: `Supprimer « ${c.name} » ?`,
                       message: 'Les deals existants gardent leur contrepartie en texte.',
                       confirmer: 'Supprimer', danger: true })) return
  error.value = ''
  notice.value = ''
  try {
    const res = await apiFetch(`/api/admin/counterparties/${c.id}`, { method: 'DELETE' })
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || 'Erreur suppression')
    counterparties.value = counterparties.value.filter(x => x.id !== c.id)
  } catch (e) {
    error.value = e.message
  }
}
</script>
