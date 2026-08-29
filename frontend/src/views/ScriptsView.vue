<template>
  <div class="flex-1 flex flex-col min-h-0">

    <div class="page-header px-6 pt-6 pb-0 mb-0">
      <div class="flex items-center gap-3">
        <BackLink :fallback="{ path: '/', query: { category: 'pricing' } }" />
        <h1 class="page-title">Mes Scripts</h1>
      </div>
      <div class="page-actions">
        <RouterLink to="/pricer" class="btn-primary text-xs px-3 py-1.5">+ Nouveau script</RouterLink>
      </div>
    </div>
    <AlertMessage v-if="error" kind="error" dismissible class="mx-5 mt-3" @dismiss="error = ''">{{ error }}</AlertMessage>
    <AlertMessage v-if="notice" kind="success" dismissible class="mx-5 mt-3" @dismiss="notice = ''">{{ notice }}</AlertMessage>

    <div class="flex flex-1 min-h-0">

      <!-- ── Sidebar dossiers ───────────────────────────────────── -->
      <aside class="w-56 shrink-0 border-r border-slate-800 flex flex-col overflow-y-auto">
        <div class="px-3 py-3 flex items-center justify-between">
          <span class="text-[10px] font-bold text-slate-500 uppercase tracking-widest">Dossiers</span>
          <button class="text-slate-500 hover:text-blue-400 text-xs" title="Nouveau dossier" aria-label="Nouveau dossier racine" @click="startNewFolder(null)">+</button>
        </div>

        <!-- Tous les scripts -->
        <button
          :class="['w-full text-left px-3 py-1.5 text-xs transition-colors',
                   selectedFolderId === null ? 'bg-blue-900/40 text-blue-300 font-semibold' : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50']"
          @click="selectedFolderId = null"
        >Tous les scripts</button>

        <!-- Tree -->
        <div class="flex-1">
          <template v-for="node in folderTree" :key="node.id">
            <div class="flex items-center group"
                 :style="{ paddingLeft: (12 + node.depth * 14) + 'px' }">
              <button
                :class="['flex-1 text-left py-1.5 pr-2 text-xs transition-colors truncate',
                         selectedFolderId === node.id ? 'text-blue-300 font-semibold' : 'text-slate-400 hover:text-slate-200']"
                @click="selectedFolderId = node.id"
              >
                <span class="text-slate-600 mr-1">{{ node.depth > 0 ? '└' : '📂' }}</span>
                {{ node.name }}
              </button>
              <!-- Folder actions -->
              <div class="hidden group-hover:flex items-center gap-1 pr-2 shrink-0">
                <button class="text-slate-600 hover:text-blue-400 text-[10px]" title="Sous-dossier" aria-label="Nouveau sous-dossier" @click.stop="startNewFolder(node.id)">+</button>
                <button class="text-slate-600 hover:text-amber-400 text-[10px]" title="Renommer" aria-label="Renommer le dossier" @click.stop="startRename(node)">✎</button>
                <button class="text-slate-600 hover:text-red-400 text-[10px]" title="Supprimer" aria-label="Supprimer le dossier" @click.stop="deleteFolder(node.id)">✕</button>
              </div>
            </div>
          </template>
        </div>

        <!-- New folder inline input -->
        <div v-if="newFolder.active" class="px-3 py-2 border-t border-slate-800">
          <div class="text-[10px] text-slate-500 mb-1">{{ newFolder.parentId ? 'Sous-dossier' : 'Dossier racine' }}</div>
          <input ref="newFolderInput" v-model="newFolder.name" type="text"
                 class="input text-xs w-full"
                 placeholder="Nom du dossier"
                 @keyup.enter="saveNewFolder"
                 @keyup.esc="newFolder.active = false" />
          <div class="flex gap-1 mt-1.5">
            <button class="btn-primary text-[10px] px-2 py-1" @click="saveNewFolder">Créer</button>
            <button class="btn-secondary text-[10px] px-2 py-1" @click="newFolder.active = false">Annuler</button>
          </div>
        </div>
      </aside>

      <!-- ── Liste scripts ──────────────────────────────────────── -->
      <main class="flex-1 flex flex-col overflow-hidden">

        <!-- Search + sort bar -->
        <div class="px-5 py-3 border-b border-slate-800">
          <DataFilterBar :fields="scriptFilterFields" :state="scriptFilter.state"
                         :field-options="scriptFilter.fieldOptions.value"
                         :has-active-filters="scriptFilter.hasActiveFilters.value"
                         :sorts="scriptSorts" :sort-by="scriptFilter.sortBy.value"
                         :sort-dir="scriptFilter.sortDir.value"
                         :count="filteredScripts.length" :total="folderScripts.length" noun="script(s)"
                         class="border-0 p-0 bg-transparent"
                         @update:sort-by="scriptFilter.sortBy.value = $event"
                         @toggle-dir="scriptFilter.toggleSortDir()" @reset="scriptFilter.reset()" />
        </div>

        <!-- Loading -->
        <LoadingSpinner v-if="loading" class="py-16" />

        <!-- Empty -->
        <EmptyState v-else-if="filteredScripts.length === 0"
             icon="📄" :title="`Aucun script${scriptFilter.hasActiveFilters.value ? ' correspondant' : ' dans ce dossier'}`">
          <RouterLink to="/pricer" class="btn-primary text-xs">Créer mon premier script</RouterLink>
        </EmptyState>

        <!-- Grid -->
        <div v-else class="flex-1 overflow-y-auto p-5 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 content-start">
          <div v-for="s in filteredScripts" :key="s.id"
               class="card flex flex-col gap-2 hover:border-blue-700/60 hover:shadow-xl hover:shadow-black/30
                      hover:-translate-y-0.5 transition-all duration-200 group cursor-pointer"
               @click="openScript(s.id)">

            <!-- Header -->
            <div class="flex items-start gap-2">
              <div class="flex-1 min-w-0">
                <div class="font-semibold text-slate-200 text-sm truncate group-hover:text-blue-300 transition-colors">
                  {{ s.name }}
                </div>
                <div v-if="s.description" class="text-xs text-slate-500 truncate mt-0.5">{{ s.description }}</div>
              </div>
              <!-- Une origine à déclinaisons se distingue AVANT d'être
                   ouverte : sans ça on rouvre le deal en croyant ouvrir la
                   variante sur laquelle on travaillait. -->
              <button v-if="s.variant_count" class="badge shrink-0 bg-amber-500/15 text-amber-400
                             border border-amber-600/40 hover:bg-amber-500/25 transition-colors"
                      :title="`${s.variant_count} déclinaison(s)`"
                      @click.stop="basculerVariantes(s)">
                ⑂ {{ s.variant_count }} {{ ouvert === s.id ? '▲' : '▼' }}
              </button>
              <span v-if="s.is_shared" class="badge badge-positive shrink-0">Partagé</span>
              <span v-if="s.user_id !== auth.user?.id" class="badge badge-muted shrink-0">{{ s.owner }}</span>
            </div>

            <!-- Tags -->
            <div v-if="s.tags" class="flex flex-wrap gap-1">
              <span v-for="tag in s.tags.split(',').filter(Boolean)" :key="tag"
                    class="text-[10px] bg-slate-800 text-slate-400 rounded px-1.5 py-0.5">{{ tag.trim() }}</span>
            </div>

            <!-- Sous-onglets : l'origine d'abord, toujours, puis chaque
                 déclinaison avec son titre et son mode. -->
            <div v-if="ouvert === s.id" class="flex flex-col gap-1 rounded border border-slate-800
                                                bg-slate-900/60 p-2" @click.stop>
              <button class="text-left text-[11px] px-2 py-1 rounded text-slate-300
                             hover:bg-slate-800 transition-colors"
                      @click="openScript(s.id)">
                Origine — {{ s.name }}
              </button>
              <button v-for="v in (variantesPar[s.id] || [])" :key="v.id"
                      class="text-left text-[11px] px-2 py-1 rounded text-slate-400
                             hover:bg-slate-800 hover:text-slate-200 transition-colors
                             flex items-center gap-1.5"
                      @click="router.push(`/pricer/v/${v.id}`)">
                <span class="flex-1 truncate">{{ v.variant_title }}</span>
                <span class="text-[9px] px-1 py-px rounded uppercase tracking-wide shrink-0"
                      :class="v.variant_mode === 'roll'
                        ? 'bg-violet-500/20 text-violet-300' : 'bg-slate-700 text-slate-500'">
                  {{ v.variant_mode === 'roll' ? 'note neuve' : 'avenant' }}
                </span>
                <span v-if="v.ecarts?.length" class="text-[9px] text-amber-400 shrink-0">
                  {{ v.ecarts.length }} △
                </span>
                <span class="text-slate-600 hover:text-red-400 text-[10px] shrink-0"
                      :title="`Supprimer « ${v.variant_title} »`"
                      @click.stop="supprimerVariante(s, v)">✕</span>
              </button>
              <div v-if="!(variantesPar[s.id] || []).length" class="text-[10px] text-slate-600 px-2">
                Chargement…
              </div>
            </div>

            <!-- Footer -->
            <div class="flex items-center gap-2 mt-auto pt-1 border-t border-slate-800/60">
              <span class="text-[10px] text-slate-600">{{ fmtDate(s.updated_at) }}</span>
              <div class="ml-auto hidden group-hover:flex items-center gap-1">
                <button class="text-[10px] text-slate-500 hover:text-red-400 px-1"
                        @click.stop="deleteScript(s.id)">Supprimer</button>
                <button class="text-[10px] text-slate-500 hover:text-green-400 px-1"
                        v-if="s.user_id === auth.user?.id"
                        @click.stop="toggleShare(s)">
                  {{ s.is_shared ? 'Priver' : 'Partager' }}
                </button>
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>

    <!-- Rename modal -->
    <BaseModal v-model="renameFolder.active" title="Renommer le dossier" max-width="360px">
      <input ref="renameFolderInput" v-model="renameFolder.name" type="text" class="input"
             @keyup.enter="saveRename" @keyup.esc="renameFolder.active = false" />
      <template #footer>
        <button class="btn-secondary text-xs" @click="renameFolder.active = false">Annuler</button>
        <button class="btn-primary text-xs" @click="saveRename">Renommer</button>
      </template>
    </BaseModal>
  </div>
</template>

<script setup>
import BackLink from '../components/ui/BackLink.vue'
import { ref, computed, watch, nextTick, onMounted } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth.js'
import { apiFetch } from '../utils/api.js'
import { confirmer } from '../composables/useConfirm.js'
import LoadingSpinner from '../components/ui/LoadingSpinner.vue'
import EmptyState from '../components/ui/EmptyState.vue'
import DataFilterBar from '../components/ui/DataFilterBar.vue'
import { useDataFilter } from '../composables/useDataFilter.js'
import BaseModal from '../components/ui/BaseModal.vue'
import AlertMessage from '../components/ui/AlertMessage.vue'
import { formatDate } from '../utils/format.js'

const auth   = useAuthStore()
const router = useRouter()

// ── State ──────────────────────────────────────────────────────────
const folders         = ref([])
const scripts         = ref([])
const loading         = ref(false)
const selectedFolderId = ref(null)
const error           = ref('')
const notice          = ref('')

// New folder inline
const newFolderInput = ref(null)
const newFolder = ref({ active: false, name: '', parentId: null })

// Rename folder modal
const renameFolderInput = ref(null)
const renameFolder = ref({ active: false, id: null, name: '' })

// Déclinaisons dépliées. Chargées à la demande : les remonter avec la liste
// ferait un appel par carte pour une information que l'on ne regarde que sur
// une carte à la fois.
const ouvert = ref(null)
const variantesPar = ref({})

async function basculerVariantes(s) {
  if (ouvert.value === s.id) { ouvert.value = null; return }
  ouvert.value = s.id
  if (variantesPar.value[s.id]) return
  try {
    const res = await apiFetch(`/api/db/scripts/${s.id}/variants`, { headers: auth.authHeaders() })
    if (res.ok) variantesPar.value = { ...variantesPar.value, [s.id]: await res.json() }
  } catch { /* la carte reste dépliée, vide — l'origine reste ouvrable */ }
}

// ── Computed ───────────────────────────────────────────────────────
const folderTree = computed(() => {
  // Sort by depth then name (already done by backend, but re-sort client-side for safety)
  return [...folders.value].sort((a, b) => a.depth - b.depth || a.name.localeCompare(b.name))
})

// Le dossier reste la navigation principale (arborescence à gauche) ; les
// filtres portent sur ce qu'il contient. Même mécanisme que l'onglet Deals du
// Booking — voir composables/useDataFilter.
const folderScripts = computed(() =>
  selectedFolderId.value === null
    ? scripts.value
    : scripts.value.filter(s => s.folder_id === selectedFolderId.value))

const scriptFilterFields = [
  { key: 'q', label: 'Recherche', kind: 'text', width: 'min-w-[200px]',
    placeholder: 'Nom, description, tag…',
    get: s => [s.name, s.description, s.tags] },
  { key: 'category', label: 'Catégorie', kind: 'select' },
  // Les tags sont stockés en une seule chaîne « a,b,c » : on les éclate pour
  // que le select en propose un par tag et non une combinaison entière.
  { key: 'tag', label: 'Tag', kind: 'select',
    get: s => (s.tags || '').split(',').map(t => t.trim()).filter(Boolean) },
]

const scriptSorts = [
  { key: 'name', label: 'Nom' },
  { key: 'updated_at', label: 'Dernière modification' },
  { key: 'category', label: 'Catégorie' },
]

const scriptFilter = useDataFilter(folderScripts, scriptFilterFields, { sorts: scriptSorts })
const filteredScripts = computed(() => scriptFilter.filtered.value)

// ── Fetch ──────────────────────────────────────────────────────────
async function fetchFolders() {
  const res = await apiFetch('/api/folders', { headers: auth.authHeaders() })
  if (res.ok) folders.value = await res.json()
}

async function fetchScripts() {
  loading.value = true
  const res = await apiFetch('/api/db/scripts', { headers: auth.authHeaders() })
  if (res.ok) scripts.value = await res.json()
  loading.value = false
}

onMounted(async () => {
  await Promise.all([fetchFolders(), fetchScripts()])
})

// ── Folders CRUD ───────────────────────────────────────────────────
function startNewFolder(parentId) {
  newFolder.value = { active: true, name: '', parentId }
  nextTick(() => newFolderInput.value?.focus())
}

async function saveNewFolder() {
  const name = newFolder.value.name.trim()
  if (!name) return
  error.value = ''
  try {
    const res = await apiFetch('/api/folders', {
      method: 'POST',
      headers: { ...auth.authHeaders(), 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, parent_id: newFolder.value.parentId }),
    })
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || 'Erreur création dossier')
    await fetchFolders()
    newFolder.value.active = false
  } catch (e) {
    error.value = e.message
  }
}

function startRename(node) {
  renameFolder.value = { active: true, id: node.id, name: node.name }
  nextTick(() => renameFolderInput.value?.focus())
}

async function saveRename() {
  const { id, name } = renameFolder.value
  if (!name.trim()) return
  error.value = ''
  notice.value = ''
  try {
    const res = await apiFetch(`/api/folders/${id}`, {
      method: 'PUT',
      headers: { ...auth.authHeaders(), 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: name.trim() }),
    })
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || 'Erreur renommage')
    renameFolder.value.active = false
    await fetchFolders()
    notice.value = 'Dossier renommé'
  } catch (e) {
    error.value = e.message
  }
}

async function deleteFolder(id) {
  if (!await confirmer({ titre: 'Supprimer ce dossier ?',
                       message: "Les sous-dossiers seront remontés d'un niveau.",
                       confirmer: 'Supprimer', danger: true })) return
  error.value = ''
  notice.value = ''
  try {
    const res = await apiFetch(`/api/folders/${id}`, { method: 'DELETE', headers: auth.authHeaders() })
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || 'Erreur suppression')
    if (selectedFolderId.value === id) selectedFolderId.value = null
    await fetchFolders()
    notice.value = 'Dossier supprimé'
  } catch (e) {
    error.value = e.message
  }
}

// ── Scripts actions ────────────────────────────────────────────────
function openScript(id) {
  router.push(`/pricer/${id}`)
}

async function deleteScript(id) {
  if (!await confirmer({ titre: 'Supprimer ce script ?',
                       confirmer: 'Supprimer', danger: true })) return
  await _supprimer(id, false)
}

/**
 * Le serveur refuse (409) de supprimer une origine qui porte des déclinaisons,
 * et dit lesquelles. On relaie sa phrase plutôt que d'en inventer une : elle
 * les nomme, ce qu'un message générique ne ferait pas. La cascade n'est tentée
 * que si l'utilisateur a lu ça et confirmé.
 */
async function _supprimer(id, cascade) {
  error.value = ''
  notice.value = ''
  try {
    const url = `/api/db/scripts/${id}${cascade ? '?cascade=true' : ''}`
    const res = await apiFetch(url, { method: 'DELETE', headers: auth.authHeaders() })
    if (res.status === 409 && !cascade) {
      const detail = (await res.json().catch(() => ({}))).detail || ''
      if (await confirmer({
        titre: 'Ce deal porte des déclinaisons',
        // Le serveur les NOMME : reproduire sa phrase vaut mieux que la
        // résumer, sinon on confirme une cascade à l'aveugle.
        detail,
        confirmer: 'Supprimer le deal et ses déclinaisons', danger: true })) {
        return _supprimer(id, true)
      }
      return
    }
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || 'Erreur suppression')
    scripts.value = scripts.value.filter(s => s.id !== id)
    if (ouvert.value === id) ouvert.value = null
    notice.value = cascade ? 'Deal et déclinaisons supprimés' : 'Script supprimé'
  } catch (e) {
    error.value = e.message
  }
}

async function supprimerVariante(parent, v) {
  if (!await confirmer({
    titre: `Supprimer « ${v.variant_title} » ?`,
    message: "Son origine et les autres déclinaisons ne sont pas affectées.",
    confirmer: 'Supprimer', danger: true })) return
  error.value = ''
  notice.value = ''
  try {
    const res = await apiFetch(`/api/db/scripts/${v.id}`,
                               { method: 'DELETE', headers: auth.authHeaders() })
    if (!res.ok && res.status !== 204) {
      throw new Error((await res.json().catch(() => ({}))).detail || 'Erreur suppression')
    }
    variantesPar.value = { ...variantesPar.value,
                           [parent.id]: (variantesPar.value[parent.id] || []).filter(x => x.id !== v.id) }
    const idx = scripts.value.findIndex(x => x.id === parent.id)
    if (idx !== -1) {
      scripts.value[idx] = { ...scripts.value[idx],
                             variant_count: Math.max(0, (scripts.value[idx].variant_count || 1) - 1) }
    }
    notice.value = 'Déclinaison supprimée'
  } catch (e) {
    error.value = e.message
  }
}

async function toggleShare(s) {
  error.value = ''
  notice.value = ''
  try {
    const res = await apiFetch(`/api/db/scripts/${s.id}`, {
      method: 'PUT',
      headers: { ...auth.authHeaders(), 'Content-Type': 'application/json' },
      body: JSON.stringify({ is_shared: !s.is_shared }),
    })
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || 'Erreur mise à jour')
    const updated = await res.json()
    const idx = scripts.value.findIndex(x => x.id === s.id)
    if (idx !== -1) scripts.value[idx] = updated
    notice.value = updated.is_shared ? 'Script partagé avec votre entité' : 'Script rendu privé'
  } catch (e) {
    error.value = e.message
  }
}

// ── Helpers ────────────────────────────────────────────────────────
const fmtDate = formatDate
</script>
