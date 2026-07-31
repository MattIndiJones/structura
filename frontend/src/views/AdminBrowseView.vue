<template>
  <div class="flex-1 min-h-0 overflow-hidden flex flex-col">

    <div class="flex flex-1 min-h-0">

      <!-- Tables -->
      <aside class="w-56 shrink-0 border-r border-slate-800 overflow-y-auto p-3 flex flex-col gap-1">
        <RouterLink v-for="t in tables" :key="t.key" :to="`/admin/browse/${t.key}`"
          :class="['text-left px-3 py-1.5 text-xs rounded transition-colors',
                   activeTable === t.key ? 'bg-blue-900/40 text-blue-300 font-semibold' : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50']">
          {{ t.label }}
        </RouterLink>
      </aside>

      <!-- Rows -->
      <main class="flex-1 overflow-y-auto p-6">
        <div class="page-header">
          <div>
            <h1 class="page-title">Données de l'application</h1>
          </div>
          <div class="page-actions">
            <RouterLink to="/admin" class="btn-ghost btn-sm">← Administration</RouterLink>
          </div>
        </div>

        <AlertMessage v-if="error" kind="error" class="mb-4">{{ error }}</AlertMessage>
        <AlertMessage v-if="notice" kind="success" dismissible class="mb-4" @dismiss="notice = ''">{{ notice }}</AlertMessage>

        <DataFilterBar v-if="rows.length" :fields="filterFields" :state="dataFilter.state"
                       :field-options="dataFilter.fieldOptions.value"
                       :has-active-filters="dataFilter.hasActiveFilters.value"
                       :count="visibleRows.length" :total="rows.length" noun="ligne(s)"
                       class="mb-3" @reset="dataFilter.reset()" />

        <div v-if="rows.length" class="flex items-center gap-3 mb-2 text-xs">
          <span v-if="selected.size" class="text-slate-500">
            <b class="text-slate-300">{{ selected.size }}</b> sélectionné(s)
          </span>
          <button v-if="selected.size" class="btn-danger text-xs px-3 py-1"
                  @click="showBulkConfirm = true">
            🗑 Supprimer la sélection ({{ selected.size }})
          </button>
          <button v-if="selected.size" class="text-slate-500 hover:text-slate-300 underline"
                  @click="selected.clear()">Tout désélectionner</button>
          <span v-if="sortCol" class="ml-auto text-slate-600">
            trié par <b class="text-slate-400">{{ sortCol }}</b> {{ sortDir === 'asc' ? '↑' : '↓' }} ·
            <button class="underline hover:text-slate-300" @click="sortCol = ''">ordre d'origine</button>
          </span>
        </div>

        <div class="card overflow-x-auto table-shell" tabindex="0" role="region">
          <LoadingSpinner v-if="loading" class="py-6" />
          <EmptyState v-else-if="!rows.length" icon="🗄️" title="Aucun enregistrement" />
          <table v-else class="w-full text-xs">
            <thead>
              <tr class="text-left text-slate-500 border-b border-slate-800">
                <th class="py-1.5 pr-3 w-8">
                  <input type="checkbox" class="accent-blue-500" :checked="allSelected"
                         :indeterminate="selected.size > 0 && !allSelected"
                         title="Tout sélectionner / désélectionner"
                         aria-label="Tout sélectionner" @change="toggleAll" />
                </th>
                <th v-for="col in columns" :key="col"
                    class="py-1.5 pr-3 font-medium whitespace-nowrap cursor-pointer select-none hover:text-slate-300"
                    :title="`Trier par ${col}`" @click="sortBy(col)">
                  {{ col }}<span v-if="sortCol === col" class="ml-1 text-blue-400">{{ sortDir === 'asc' ? '↑' : '↓' }}</span>
                </th>
                <th class="py-1.5 pr-3 font-medium"></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in sortedRows" :key="row.id"
                  :class="['border-b border-slate-800/60', selected.has(row.id) ? 'bg-blue-950/30' : '']">
                <td class="py-1.5 pr-3">
                  <input type="checkbox" class="accent-blue-500" :checked="selected.has(row.id)"
                         :aria-label="`Sélectionner l'enregistrement ${row.id}`"
                         @change="toggleRow(row.id)" />
                </td>
                <td v-for="col in columns" :key="col" class="py-1.5 pr-3 text-slate-300 whitespace-nowrap max-w-xs truncate">
                  {{ fmtCell(row[col]) }}
                </td>
                <td class="py-1.5 pr-3 text-right whitespace-nowrap">
                  <button v-if="editableFields" class="icon-btn-neutral"
                          title="Modifier" aria-label="Modifier l'enregistrement" @click="openEdit(row)">✏️</button>
                  <button class="icon-btn-danger" title="Supprimer" aria-label="Supprimer l'enregistrement" @click="deleteRow(row)">🗑</button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </main>
    </div>

    <BaseModal v-model="showBulkConfirm" title="Supprimer la sélection">
      <p class="text-sm text-slate-300">
        Supprimer <b>{{ selected.size }}</b> enregistrement(s) de
        <b>{{ tables.find(t => t.key === activeTable)?.label || activeTable }}</b> ?
      </p>
      <p class="text-xs text-slate-500 mt-2">
        Les enregistrements protégés (un deal rattaché à un KID, une RFQ dont un deal
        a été booké…) seront refusés et listés — les autres seront bien supprimés.
        Cette action est définitive.
      </p>
      <template #footer>
        <button class="btn-secondary text-sm" @click="showBulkConfirm = false">Annuler</button>
        <button class="btn-danger text-sm" :disabled="bulkDeleting" @click="confirmBulkDelete">
          {{ bulkDeleting ? 'Suppression…' : `Supprimer ${selected.size} enregistrement(s)` }}
        </button>
      </template>
    </BaseModal>

    <BaseModal v-model="showEdit" title="Modifier l'enregistrement">
      <AlertMessage v-if="editError" kind="error" class="mb-3">{{ editError }}</AlertMessage>
      <div class="flex flex-col gap-3">
        <div v-for="field in Object.keys(editableFields || {})" :key="field" class="flex flex-col gap-1">
          <label class="label">{{ field }}</label>
          <select v-if="editableFields[field].startsWith('select:')" v-model="editForm[field]" class="select">
            <option v-for="opt in editableFields[field].slice(7).split(',')" :key="opt" :value="opt">{{ opt }}</option>
          </select>
          <input v-else :type="editableFields[field]" v-model="editForm[field]"
                 :step="editableFields[field] === 'number' ? 'any' : undefined" class="input" />
        </div>
      </div>
      <template #footer>
        <button class="btn-secondary text-sm" @click="showEdit = false">Annuler</button>
        <button class="btn-primary text-sm" :disabled="savingEdit" @click="submitEdit">
          {{ savingEdit ? 'Enregistrement…' : 'Enregistrer' }}
        </button>
      </template>
    </BaseModal>
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch, onMounted } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { apiFetch } from '../utils/api.js'
import LoadingSpinner from '../components/ui/LoadingSpinner.vue'
import EmptyState from '../components/ui/EmptyState.vue'
import AlertMessage from '../components/ui/AlertMessage.vue'
import BaseModal from '../components/ui/BaseModal.vue'
import DataFilterBar from '../components/ui/DataFilterBar.vue'
import { useDataFilter } from '../composables/useDataFilter.js'
import { formatDateTime } from '../utils/format.js'

const route = useRoute()

const tables  = ref([])
const rows    = ref([])
const loading = ref(true)
const error   = ref('')
const notice  = ref('')

const activeTable = computed(() => route.params.table || tables.value[0]?.key || '')

// {} for every table except deals today — see admin_registry.py's
// editable_fields allowlist. Empty object is falsy-by-convention here
// (Object.keys length check), so the ✏️ button only renders where it's real.
const editableFields = computed(() => {
  const fields = tables.value.find(t => t.key === activeTable.value)?.editable_fields
  return fields && Object.keys(fields).length ? fields : null
})

// Columns come from whatever keys the rows actually carry (owner is appended
// server-side when the table has a user_id column) — no separate schema call.
const columns = computed(() => {
  if (!rows.value.length) return []
  return Object.keys(rows.value[0])
})

// ── Filtres (déduits de la table affichée) ──────────────────────────────
// Cet écran sert sept tables aux colonnes différentes : rien ne peut être
// déclaré à l'avance. Une recherche libre sur toutes les colonnes, plus un
// select par colonne à faible cardinalité (statut, devise, propriétaire…) —
// les identifiants et les dates en sont exclus, un select de trente dates
// n'aide personne.
const _NO_SELECT = /(^id$|_id$|reference|_at$|_date$|^name$|^label$)/i

const filterFields = computed(() => {
  const fields = [{ key: 'q', label: 'Recherche', kind: 'text', width: 'min-w-[220px]',
                    placeholder: 'Dans toutes les colonnes…',
                    get: row => columns.value.map(c => row[c]) }]
  for (const col of columns.value) {
    if (_NO_SELECT.test(col)) continue
    const distinct = new Set(rows.value.map(r => r[col]).filter(v => v !== null && v !== ''))
    if (distinct.size > 1 && distinct.size <= 12) {
      fields.push({ key: col, label: col, kind: 'select' })
    }
  }
  return fields
})

// Une seule instance, alimentée par des champs qui changent avec la table —
// la recréer à chaque changement de colonnes effacerait la saisie en cours.
const dataFilter = useDataFilter(rows, filterFields)
const visibleRows = computed(() => dataFilter.filtered.value)

// ── Tri (client) ────────────────────────────────────────────────────────
// Toutes les lignes de la table sont déjà chargées (list_rows ne pagine pas),
// donc trier ici évite un aller-retour et marche sur n'importe quelle colonne
// de n'importe quelle table, sans rien déclarer côté serveur.
const sortCol = ref('')
const sortDir = ref('asc')

function sortBy(col) {
  if (sortCol.value === col) {
    sortDir.value = sortDir.value === 'asc' ? 'desc' : 'asc'
  } else {
    sortCol.value = col
    sortDir.value = 'asc'
  }
}

function _cmp(a, b) {
  // Les vides toujours en dernier, quel que soit le sens : une cellule non
  // renseignée n'est ni la plus petite ni la plus grande, elle n'a pas de rang.
  const aEmpty = a === null || a === undefined || a === ''
  const bEmpty = b === null || b === undefined || b === ''
  if (aEmpty || bEmpty) return aEmpty && bEmpty ? 0 : (aEmpty ? 1 : -1)
  if (typeof a === 'number' && typeof b === 'number') return a - b
  if (typeof a === 'boolean' && typeof b === 'boolean') return (a ? 1 : 0) - (b ? 1 : 0)
  return String(a).localeCompare(String(b), 'fr', { numeric: true, sensitivity: 'base' })
}

// Le tri s'applique aux lignes qui ont passé les filtres, pas à la table
// entière — sinon on trierait des lignes qu'on ne voit pas.
const sortedRows = computed(() => {
  if (!sortCol.value) return visibleRows.value
  const dir = sortDir.value === 'asc' ? 1 : -1
  // Copie : trier en place réordonnerait la source et ferait perdre l'ordre
  // d'origine (id décroissant) qu'on peut vouloir retrouver.
  return [...visibleRows.value].sort((x, y) => dir * _cmp(x[sortCol.value], y[sortCol.value]))
})

// ── Sélection multiple ──────────────────────────────────────────────────
const selected = reactive(new Set())
// « Tout sélectionner » porte sur ce qui est affiché : filtrer puis tout
// cocher doit prendre la sélection filtrée, pas la table entière.
const allSelected = computed(() => visibleRows.value.length > 0
  && visibleRows.value.every(r => selected.has(r.id)))

function toggleRow(id) {
  selected.has(id) ? selected.delete(id) : selected.add(id)
}

function toggleAll() {
  if (allSelected.value) visibleRows.value.forEach(r => selected.delete(r.id))
  else visibleRows.value.forEach(r => selected.add(r.id))
}

async function fetchTables() {
  const res = await apiFetch('/api/admin/browse')
  if (res.ok) tables.value = await res.json()
}

async function fetchRows() {
  if (!activeTable.value) return
  loading.value = true
  error.value = ''
  notice.value = ''
  // Une sélection ou un tri portent sur la table qu'on quitte : les garder
  // ferait pointer des ids d'une table sur les lignes d'une autre.
  selected.clear()
  sortCol.value = ''
  dataFilter.reset()
  try {
    const res = await apiFetch(`/api/admin/browse/${activeTable.value}`)
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || 'Erreur chargement')
    rows.value = await res.json()
  } catch (e) {
    error.value = e.message
    rows.value = []
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  await fetchTables()
  await fetchRows()
})

watch(() => route.params.table, fetchRows)

async function deleteRow(row) {
  if (!confirm(`Supprimer l'enregistrement #${row.id} ?`)) return
  error.value = ''
  notice.value = ''
  try {
    const res = await apiFetch(`/api/admin/browse/${activeTable.value}/${row.id}`, { method: 'DELETE' })
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || 'Erreur suppression')
    rows.value = rows.value.filter(r => r.id !== row.id)
    selected.delete(row.id)
    notice.value = 'Enregistrement supprimé'
  } catch (e) {
    error.value = e.message
  }
}

// ── Suppression en lot ──────────────────────────────────────────────────
const showBulkConfirm = ref(false)
const bulkDeleting    = ref(false)

async function confirmBulkDelete() {
  bulkDeleting.value = true
  error.value = ''
  notice.value = ''
  try {
    const res = await apiFetch(`/api/admin/browse/${activeTable.value}/delete`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ids: [...selected] }),
    })
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || 'Erreur suppression')
    const { deleted, blocked } = await res.json()
    const gone = new Set(deleted)
    rows.value = rows.value.filter(r => !gone.has(r.id))
    selected.clear()
    showBulkConfirm.value = false
    notice.value = `${deleted.length} enregistrement(s) supprimé(s).`
    // Un refus n'est pas une erreur de l'opération : le lot est passé, ces
    // lignes-là sont protégées. On les nomme avec leur raison plutôt que de
    // laisser deviner lesquelles sont restées.
    if (blocked.length) {
      error.value = `${blocked.length} refusé(s) — `
        + blocked.map(b => `#${b.id} : ${b.reason}`).join(' · ')
      blocked.forEach(b => selected.add(b.id))
    }
  } catch (e) {
    error.value = e.message
  } finally {
    bulkDeleting.value = false
  }
}

// ── Edit (whitelisted fields only, see editableFields) ──────────────────
const showEdit    = ref(false)
const editForm    = reactive({})
const editRow     = ref(null)
const editError   = ref('')
const savingEdit  = ref(false)

async function openEdit(row) {
  editRow.value = row
  editError.value = ''
  Object.keys(editForm).forEach(k => delete editForm[k])
  showEdit.value = true
  // The list row only carries `columns` (a deliberately short summary) —
  // fetch the full record so fields like the dates/price_traded that
  // aren't in the table view still show their real current value here.
  try {
    const res = await apiFetch(`/api/admin/browse/${activeTable.value}/${row.id}`)
    const detail = res.ok ? await res.json() : row
    for (const field of Object.keys(editableFields.value || {})) {
      editForm[field] = detail[field] ?? ''
    }
  } catch {
    for (const field of Object.keys(editableFields.value || {})) {
      editForm[field] = row[field] ?? ''
    }
  }
}

async function submitEdit() {
  savingEdit.value = true
  editError.value = ''
  try {
    const patch = { ...editForm }
    for (const [field, kind] of Object.entries(editableFields.value || {})) {
      if (kind === 'number') patch[field] = patch[field] === '' ? null : Number(patch[field])
    }
    const res = await apiFetch(`/api/admin/browse/${activeTable.value}/${editRow.value.id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(patch),
    })
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || 'Erreur modification')
    const updated = await res.json()
    const idx = rows.value.findIndex(r => r.id === editRow.value.id)
    if (idx !== -1) rows.value[idx] = { ...rows.value[idx], ...updated }
    showEdit.value = false
    notice.value = 'Enregistrement modifié'
  } catch (e) {
    editError.value = e.message
  } finally {
    savingEdit.value = false
  }
}

function fmtCell(v) {
  if (v === null || v === undefined) return '—'
  if (typeof v === 'boolean') return v ? '✓' : '—'
  if (typeof v === 'string' && /^\d{4}-\d{2}-\d{2}T/.test(v)) return formatDateTime(v)
  return v
}
</script>
