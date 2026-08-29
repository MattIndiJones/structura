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
      <AlertMessage v-if="notice" kind="success" dismissible @dismiss="notice = ''">{{ notice }}</AlertMessage>

      <div class="card overflow-x-auto">
        <LoadingSpinner v-if="loading" class="py-6" />
        <table v-else class="w-full text-xs">
          <thead>
            <tr class="text-left text-slate-500 border-b border-slate-800">
              <th class="py-1.5 pr-3 font-medium">Nom</th>
              <th class="py-1.5 pr-3 font-medium">Mode</th>
              <th class="py-1.5 pr-3 font-medium">
                Contrepartie de booking
                <HelpTip text="La contrepartie que le deal affronte réellement quand il est booké depuis une réponse de ce fournisseur. À renseigner uniquement si les deux noms diffèrent (ex. « Vontobel (deritrade) » cote, « Vontobel » fait face au trade) : à libellés identiques, le rapprochement se fait tout seul. Non renseignée et sans nom identique dans le catalogue des contreparties, le booking laisse le champ vide plutôt que d'y écrire une contrepartie hors catalogue." />
              </th>
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
                <select class="select py-1 px-2" :value="p.counterparty_id ?? ''"
                        @change="updateProvider(p, { counterparty_id: $event.target.value === '' ? null : Number($event.target.value) })">
                  <option value="">{{ autoMatch(p) ? `— ${autoMatch(p)} (par le nom) —` : '— Aucune —' }}</option>
                  <option v-for="c in counterparties" :key="c.id" :value="c.id">{{ c.name }}</option>
                </select>
                <!-- Sans rapprochement, le booking laisse la contrepartie vide :
                     autant le dire ici plutôt que de le découvrir au trade. -->
                <div v-if="!p.counterparty_id && !autoMatch(p) && p.active"
                     class="text-[10px] text-amber-500/90 mt-0.5">
                  ⚠ aucune contrepartie — le booking laissera le champ vide
                </div>
              </td>
              <td class="py-1.5 pr-3">
                <input type="checkbox" class="accent-blue-500" :checked="p.active"
                       @change="updateProvider(p, { active: $event.target.checked })" />
              </td>
              <td class="py-1.5 pr-3 text-right">
                <button class="icon-btn-danger" title="Supprimer" aria-label="Supprimer le fournisseur" @click="deleteProvider(p)">🗑</button>
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
import HelpTip from '../components/HelpTip.vue'

const providers = ref([])
const counterparties = ref([])
const loading   = ref(true)
const error     = ref('')
const notice    = ref('')
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

async function fetchCounterparties() {
  try {
    const res = await apiFetch('/api/admin/counterparties')
    if (res.ok) counterparties.value = (await res.json()).filter(c => c.active)
  } catch { /* le select se limite alors à « Aucune » */ }
}

// Le rapprochement automatique par nom identique n'a rien à configurer — on
// le montre dans l'option vide pour que l'admin voie qu'il est déjà couvert
// au lieu de croire le fournisseur non rattaché (voir _counterparty_by_provider).
function autoMatch(p) {
  return counterparties.value.some(c => c.name === p.label) ? p.label : null
}

onMounted(() => { fetchProviders(); fetchCounterparties() })

async function createProvider() {
  const label = newLabel.value.trim()
  if (!label) return
  creating.value = true
  error.value = ''
  notice.value = ''
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
    notice.value = 'Fournisseur ajouté'
  } catch (e) {
    error.value = e.message
  } finally {
    creating.value = false
  }
}

async function updateProvider(p, payload) {
  error.value = ''
  notice.value = ''
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
  if (!await confirmer({ titre: `Supprimer « ${p.label} » ?`,
                       confirmer: 'Supprimer', danger: true })) return
  error.value = ''
  notice.value = ''
  try {
    const res = await apiFetch(`/api/admin/rfq-providers/${p.id}`, { method: 'DELETE' })
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || 'Erreur suppression')
    providers.value = providers.value.filter(x => x.id !== p.id)
  } catch (e) {
    error.value = e.message
  }
}
</script>
