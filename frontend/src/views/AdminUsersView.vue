<template>
  <div class="flex-1 flex flex-col min-h-0">

    <main class="flex-1 min-h-0 overflow-y-auto overscroll-contain p-6 max-w-4xl w-full mx-auto flex flex-col gap-4">
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
                  <option value="ops_maker">Ops Maker</option>
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
              <option value="ops_maker">Ops Maker</option>
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

      <div class="card flex flex-col gap-3">
        <div>
          <div class="font-semibold text-sm">Desks RFQ</div>
          <p class="text-xs text-slate-500">L'appartenance à une organisation ne donne aucun accès RFQ. Accordez les droits par desk.</p>
        </div>
        <div class="flex flex-wrap gap-2 items-end">
          <label class="flex flex-col gap-1 text-xs">Organisation
            <select v-model.number="newDesk.entity_id" class="select">
              <option v-for="e in entities" :key="e.id" :value="e.id">{{ e.name }}</option>
            </select>
          </label>
          <label class="flex flex-col gap-1 text-xs">Nom du desk
            <input v-model="newDesk.name" class="input" placeholder="Sales, Structuration…" />
          </label>
          <button class="btn-secondary btn-sm" @click="createDesk">Créer le desk</button>
        </div>
        <div v-if="desks.length" class="flex flex-wrap gap-2">
          <button v-for="desk in desks" :key="desk.id" class="btn-secondary btn-sm"
                  :class="selectedDeskId === desk.id ? 'border-blue-500' : ''"
                  @click="selectDesk(desk)">{{ entityName(desk.entity_id) }} · {{ desk.name }}</button>
        </div>
        <div v-if="selectedDesk" class="border-t border-slate-700 pt-3 flex flex-col gap-3">
          <div class="text-xs font-semibold">Habilitations · {{ selectedDesk.name }}</div>
          <div class="flex flex-wrap gap-2 items-end">
            <label class="flex flex-col gap-1 text-xs">Collaborateur
              <select v-model.number="memberDraft.user_id" class="select" @change="loadMemberDraft">
                <option :value="null">— Choisir —</option>
                <option v-for="u in users.filter(u => u.entity_id === selectedDesk.entity_id && u.is_active)"
                        :key="u.id" :value="u.id">{{ u.username }}</option>
              </select>
            </label>
            <label class="flex items-center gap-2 text-xs"><input v-model="memberDraft.active" type="checkbox" /> Habilitation active</label>
          </div>
          <div class="flex flex-wrap gap-x-4 gap-y-2 text-xs">
            <label v-for="right in deskRights" :key="right.key" class="flex items-center gap-1">
              <input v-model="memberDraft.rights" type="checkbox" :value="right.key" /> {{ right.label }}
            </label>
          </div>
          <button class="btn-primary btn-sm w-fit" :disabled="!memberDraft.user_id" @click="saveMember">Enregistrer les droits</button>
          <div v-if="selectedDesk.members.length" class="text-xs text-slate-500">
            <button v-for="member in selectedDesk.members" :key="member.user_id" class="block py-1 hover:text-blue-300"
                    @click="memberDraft.user_id = member.user_id; loadMemberDraft()">
              {{ userName(member.user_id) }} · {{ member.active ? member.rights.join(', ') : 'suspendu' }}
            </button>
          </div>
        </div>
      </div>
    </main>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
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
const desks = ref([])
const selectedDeskId = ref(null)
const selectedDesk = computed(() => desks.value.find(d => d.id === selectedDeskId.value))
const newDesk = reactive({ entity_id: null, name: '' })
const memberDraft = reactive({ user_id: null, rights: ['read', 'prepare'], active: true })
const deskRights = [
  { key: 'read', label: 'Lire' }, { key: 'prepare', label: 'Préparer / manuel' },
  { key: 'price', label: 'Pricing interne' }, { key: 'select', label: 'Sélectionner' },
  { key: 'solicit', label: 'Solliciter' }, { key: 'organize', label: 'Organiser / partager' },
  { key: 'book', label: 'Booker' },
  { key: 'validate_quote', label: 'Valider une cotation bancaire' },
  { key: 'publish_quote', label: 'Publier / retirer une cotation bancaire' },
]
const entityName = id => entities.value.find(e => e.id === id)?.name || `Organisation ${id}`
const userName = id => users.value.find(u => u.id === id)?.username || `Utilisateur ${id}`

function selectDesk(desk) {
  selectedDeskId.value = desk.id
  memberDraft.user_id = null
  memberDraft.rights = ['read', 'prepare']
  memberDraft.active = true
}

function loadMemberDraft() {
  const member = selectedDesk.value?.members.find(m => m.user_id === memberDraft.user_id)
  memberDraft.rights = member ? [...member.rights] : ['read', 'prepare']
  memberDraft.active = member?.active ?? true
}

async function createDesk() {
  error.value = ''
  const res = await apiFetch('/api/rfq-desks/admin', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(newDesk),
  })
  if (!res.ok) { error.value = (await res.json().catch(() => ({}))).detail || 'Création du desk refusée'; return }
  const desk = { ...await res.json(), members: [] }
  desks.value.push(desk)
  selectDesk(desk)
  newDesk.name = ''
  notice.value = 'Desk créé'
}

async function saveMember() {
  error.value = ''
  if (!memberDraft.rights.includes('read')) {
    error.value = 'Le droit de lecture est requis pour toute habilitation.'; return
  }
  const res = await apiFetch(`/api/rfq-desks/admin/${selectedDeskId.value}/members/${memberDraft.user_id}`, {
    method: 'PUT', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(memberDraft),
  })
  if (!res.ok) { error.value = (await res.json().catch(() => ({}))).detail || 'Habilitation refusée'; return }
  const saved = await res.json()
  const index = selectedDesk.value.members.findIndex(m => m.user_id === saved.user_id)
  if (index === -1) selectedDesk.value.members.push(saved)
  else selectedDesk.value.members[index] = saved
  notice.value = 'Habilitation RFQ enregistrée'
}

const form = reactive({ username: '', email: '', password: '', role: 'user', entity_id: null })

async function fetchAll() {
  loading.value = true
  try {
    const [uRes, eRes, dRes] = await Promise.all([
      apiFetch('/api/admin/users'),
      apiFetch('/api/admin/entities'),
      apiFetch('/api/rfq-desks/admin'),
    ])
    if (!uRes.ok) throw new Error((await uRes.json().catch(() => ({}))).detail || 'Erreur chargement utilisateurs')
    if (!eRes.ok) throw new Error((await eRes.json().catch(() => ({}))).detail || 'Erreur chargement entités')
    if (!dRes.ok) throw new Error((await dRes.json().catch(() => ({}))).detail || 'Erreur chargement desks')
    users.value = await uRes.json()
    entities.value = await eRes.json()
    desks.value = await dRes.json()
    if (entities.value.length) form.entity_id = entities.value[0].id
    if (entities.value.length) newDesk.entity_id = entities.value[0].id
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
