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

        <div class="card overflow-x-auto table-shell" tabindex="0" role="region">
          <LoadingSpinner v-if="loading" class="py-6" />
          <EmptyState v-else-if="!rows.length" icon="🗄️" title="Aucun enregistrement" />
          <table v-else class="w-full text-xs">
            <thead>
              <tr class="text-left text-slate-500 border-b border-slate-800">
                <th v-for="col in columns" :key="col" class="py-1.5 pr-3 font-medium whitespace-nowrap">{{ col }}</th>
                <th class="py-1.5 pr-3 font-medium"></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in rows" :key="row.id" class="border-b border-slate-800/60">
                <td v-for="col in columns" :key="col" class="py-1.5 pr-3 text-slate-300 whitespace-nowrap max-w-xs truncate">
                  {{ fmtCell(row[col]) }}
                </td>
                <td class="py-1.5 pr-3 text-right">
                  <button class="text-slate-600 hover:text-red-400" title="Supprimer" @click="deleteRow(row)">🗑</button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </main>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { apiFetch } from '../utils/api.js'
import LoadingSpinner from '../components/ui/LoadingSpinner.vue'
import EmptyState from '../components/ui/EmptyState.vue'
import AlertMessage from '../components/ui/AlertMessage.vue'
import { useToastsStore } from '../stores/toasts.js'

const toasts = useToastsStore()
const route = useRoute()

const tables  = ref([])
const rows    = ref([])
const loading = ref(true)
const error   = ref('')

const activeTable = computed(() => route.params.table || tables.value[0]?.key || '')

// Columns come from whatever keys the rows actually carry (owner is appended
// server-side when the table has a user_id column) — no separate schema call.
const columns = computed(() => {
  if (!rows.value.length) return []
  return Object.keys(rows.value[0])
})

async function fetchTables() {
  const res = await apiFetch('/api/admin/browse')
  if (res.ok) tables.value = await res.json()
}

async function fetchRows() {
  if (!activeTable.value) return
  loading.value = true
  error.value = ''
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
  try {
    const res = await apiFetch(`/api/admin/browse/${activeTable.value}/${row.id}`, { method: 'DELETE' })
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || 'Erreur suppression')
    rows.value = rows.value.filter(r => r.id !== row.id)
    toasts.success('Enregistrement supprimé')
  } catch (e) {
    error.value = e.message
  }
}

function fmtCell(v) {
  if (v === null || v === undefined) return '—'
  if (typeof v === 'boolean') return v ? '✓' : '—'
  if (typeof v === 'string' && /^\d{4}-\d{2}-\d{2}T/.test(v)) return new Date(v).toLocaleString('fr-FR')
  return v
}
</script>
