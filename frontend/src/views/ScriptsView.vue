<template>
  <div class="flex-1 flex flex-col min-h-0">

    <div class="page-header px-6 pt-6 pb-0 mb-0">
      <div>
        <h1 class="page-title">Mes Scripts</h1>
      </div>
      <div class="page-actions">
        <RouterLink to="/pricer" class="btn-primary text-xs px-3 py-1.5">+ Nouveau script</RouterLink>
      </div>
    </div>

    <div class="flex flex-1 min-h-0">

      <!-- ── Sidebar dossiers ───────────────────────────────────── -->
      <aside class="w-56 shrink-0 border-r border-slate-800 flex flex-col overflow-y-auto">
        <div class="px-3 py-3 flex items-center justify-between">
          <span class="text-[10px] font-bold text-slate-500 uppercase tracking-widest">Dossiers</span>
          <button class="text-slate-500 hover:text-blue-400 text-xs" title="Nouveau dossier" @click="startNewFolder(null)">+</button>
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
                <button class="text-slate-600 hover:text-blue-400 text-[10px]" title="Sous-dossier" @click.stop="startNewFolder(node.id)">+</button>
                <button class="text-slate-600 hover:text-amber-400 text-[10px]" title="Renommer" @click.stop="startRename(node)">✎</button>
                <button class="text-slate-600 hover:text-red-400 text-[10px]" title="Supprimer" @click.stop="deleteFolder(node.id)">✕</button>
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
        <div class="px-5 py-3 border-b border-slate-800 flex items-center gap-3">
          <input v-model="search" type="text" class="input text-xs flex-1 max-w-xs"
                 placeholder="Rechercher un script…" />
          <span class="text-xs text-slate-600 ml-auto">{{ filteredScripts.length }} script(s)</span>
        </div>

        <!-- Loading -->
        <LoadingSpinner v-if="loading" class="py-16" />

        <!-- Empty -->
        <EmptyState v-else-if="filteredScripts.length === 0"
             icon="📄" :title="`Aucun script${search ? ' correspondant' : ' dans ce dossier'}`">
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
              <span v-if="s.is_shared" class="badge badge-positive shrink-0">Partagé</span>
              <span v-if="s.user_id !== auth.user?.id" class="badge badge-muted shrink-0">{{ s.owner }}</span>
            </div>

            <!-- Tags -->
            <div v-if="s.tags" class="flex flex-wrap gap-1">
              <span v-for="tag in s.tags.split(',').filter(Boolean)" :key="tag"
                    class="text-[10px] bg-slate-800 text-slate-400 rounded px-1.5 py-0.5">{{ tag.trim() }}</span>
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
import { ref, computed, watch, nextTick, onMounted } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth.js'
import { apiFetch } from '../utils/api.js'
import LoadingSpinner from '../components/ui/LoadingSpinner.vue'
import EmptyState from '../components/ui/EmptyState.vue'
import BaseModal from '../components/ui/BaseModal.vue'
import { useToastsStore } from '../stores/toasts.js'

const auth   = useAuthStore()
const router = useRouter()
const toasts = useToastsStore()

// ── State ──────────────────────────────────────────────────────────
const folders         = ref([])
const scripts         = ref([])
const loading         = ref(false)
const selectedFolderId = ref(null)
const search          = ref('')

// New folder inline
const newFolderInput = ref(null)
const newFolder = ref({ active: false, name: '', parentId: null })

// Rename folder modal
const renameFolderInput = ref(null)
const renameFolder = ref({ active: false, id: null, name: '' })

// ── Computed ───────────────────────────────────────────────────────
const folderTree = computed(() => {
  // Sort by depth then name (already done by backend, but re-sort client-side for safety)
  return [...folders.value].sort((a, b) => a.depth - b.depth || a.name.localeCompare(b.name))
})

const filteredScripts = computed(() => {
  let list = scripts.value
  if (selectedFolderId.value !== null) {
    list = list.filter(s => s.folder_id === selectedFolderId.value)
  }
  if (search.value.trim()) {
    const q = search.value.toLowerCase()
    list = list.filter(s =>
      s.name.toLowerCase().includes(q) ||
      s.description.toLowerCase().includes(q) ||
      s.tags.toLowerCase().includes(q)
    )
  }
  return list
})

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
  const res = await apiFetch('/api/folders', {
    method: 'POST',
    headers: { ...auth.authHeaders(), 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, parent_id: newFolder.value.parentId }),
  })
  if (res.ok) { await fetchFolders() }
  newFolder.value.active = false
}

function startRename(node) {
  renameFolder.value = { active: true, id: node.id, name: node.name }
  nextTick(() => renameFolderInput.value?.focus())
}

async function saveRename() {
  const { id, name } = renameFolder.value
  if (!name.trim()) return
  await apiFetch(`/api/folders/${id}`, {
    method: 'PUT',
    headers: { ...auth.authHeaders(), 'Content-Type': 'application/json' },
    body: JSON.stringify({ name: name.trim() }),
  })
  renameFolder.value.active = false
  await fetchFolders()
  toasts.success('Dossier renommé')
}

async function deleteFolder(id) {
  if (!confirm('Supprimer ce dossier ? Les sous-dossiers seront remontés.')) return
  await apiFetch(`/api/folders/${id}`, { method: 'DELETE', headers: auth.authHeaders() })
  if (selectedFolderId.value === id) selectedFolderId.value = null
  await fetchFolders()
  toasts.success('Dossier supprimé')
}

// ── Scripts actions ────────────────────────────────────────────────
function openScript(id) {
  router.push(`/pricer/${id}`)
}

async function deleteScript(id) {
  if (!confirm('Supprimer ce script ?')) return
  await apiFetch(`/api/db/scripts/${id}`, { method: 'DELETE', headers: auth.authHeaders() })
  scripts.value = scripts.value.filter(s => s.id !== id)
  toasts.success('Script supprimé')
}

async function toggleShare(s) {
  const res = await apiFetch(`/api/db/scripts/${s.id}`, {
    method: 'PUT',
    headers: { ...auth.authHeaders(), 'Content-Type': 'application/json' },
    body: JSON.stringify({ is_shared: !s.is_shared }),
  })
  if (res.ok) {
    const updated = await res.json()
    const idx = scripts.value.findIndex(x => x.id === s.id)
    if (idx !== -1) scripts.value[idx] = updated
    toasts.success(updated.is_shared ? 'Script partagé avec votre entité' : 'Script rendu privé')
  }
}

// ── Helpers ────────────────────────────────────────────────────────
function fmtDate(iso) {
  return new Date(iso).toLocaleDateString('fr-FR', { day: '2-digit', month: '2-digit', year: '2-digit' })
}
</script>
