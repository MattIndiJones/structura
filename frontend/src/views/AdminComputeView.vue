<template>
  <div class="flex-1 flex flex-col min-h-0">

    <main class="flex-1 p-6 max-w-6xl w-full mx-auto flex flex-col gap-4">
      <div class="page-header">
        <div>
          <h1 class="page-title">Files de calcul</h1>
          <p class="page-subtitle">
            Études VaR et batches de repricing, tous comptes confondus — le worker
            (<code>run_compute_worker.py</code>) doit tourner pour qu'un batch avance.
          </p>
        </div>
        <div class="page-actions">
          <RouterLink to="/admin" class="btn-ghost btn-sm">← Administration</RouterLink>
          <button class="btn-secondary text-xs px-3 py-1.5" :disabled="loading" @click="fetchBatches">
            Actualiser
          </button>
        </div>
      </div>

      <AlertMessage v-if="error" kind="error">{{ error }}</AlertMessage>
      <AlertMessage v-if="notice" kind="success" dismissible @dismiss="notice = ''">{{ notice }}</AlertMessage>

      <div class="card overflow-x-auto">
        <LoadingSpinner v-if="loading" class="py-6" />
        <p v-else-if="batches.length === 0" class="text-xs py-6 text-center" style="color: var(--subtle);">
          Aucun batch en base.
        </p>
        <table v-else class="w-full text-xs">
          <thead>
            <tr class="text-left text-slate-500 border-b border-slate-800">
              <th class="py-1.5 pr-3 font-medium">Type</th>
              <th class="py-1.5 pr-3 font-medium">Libellé</th>
              <th class="py-1.5 pr-3 font-medium">Compte</th>
              <th class="py-1.5 pr-3 font-medium">Statut</th>
              <th class="py-1.5 pr-3 font-medium">Progression</th>
              <th class="py-1.5 pr-3 font-medium">Créé le</th>
              <th class="py-1.5 pr-3 font-medium">Terminé le</th>
              <th class="py-1.5 pr-3 font-medium"></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="b in batches" :key="b.id" class="border-b border-slate-800/60">
              <td class="py-1.5 pr-3 whitespace-nowrap">{{ kindLabel(b.kind) }}</td>
              <td class="py-1.5 pr-3 max-w-xs truncate" :title="b.label">{{ b.label }}</td>
              <td class="py-1.5 pr-3 whitespace-nowrap">{{ b.owner }}</td>
              <td class="py-1.5 pr-3 whitespace-nowrap">
                <span class="inline-block px-2 py-0.5 rounded-full text-[10px] font-semibold"
                      :class="statusClass(b.status)">{{ statusLabel(b.status) }}</span>
              </td>
              <td class="py-1.5 pr-3 whitespace-nowrap font-mono">
                {{ b.completed_jobs + b.failed_jobs }}/{{ b.total_jobs }}
                <span v-if="b.failed_jobs" class="text-red-400">({{ b.failed_jobs }} éch.)</span>
              </td>
              <td class="py-1.5 pr-3 whitespace-nowrap font-mono" style="color: var(--subtle);">{{ fmtDate(b.created_at) }}</td>
              <td class="py-1.5 pr-3 whitespace-nowrap font-mono" style="color: var(--subtle);">{{ fmtDate(b.finished_at) }}</td>
              <td class="py-1.5 pr-3 whitespace-nowrap text-right">
                <div class="flex justify-end gap-1">
                  <button v-if="['queued', 'running'].includes(b.status)"
                          class="btn-secondary text-[10px] px-2 py-1" :disabled="b.busy"
                          @click="stopBatch(b)">Arrêter</button>
                  <button v-if="['failed', 'completed_with_failures', 'cancelled'].includes(b.status)"
                          class="btn-secondary text-[10px] px-2 py-1" :disabled="b.busy"
                          @click="relaunchBatch(b)">Relancer</button>
                  <button class="icon-btn-danger" title="Supprimer" aria-label="Supprimer le batch" :disabled="b.busy"
                          @click="deleteBatch(b)">🗑</button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
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
import { formatDateTime } from '../utils/format.js'

const batches = ref([])
const loading = ref(true)
const error   = ref('')
const notice  = ref('')

const KIND_LABELS = { var_scenario: 'VaR/ES', payscript_reprice: 'Repricing' }
function kindLabel(kind) { return KIND_LABELS[kind] || kind }

const STATUS_LABELS = {
  queued: 'En attente', running: 'En cours', completed: 'Terminé',
  completed_with_failures: 'Terminé (échecs)', failed: 'Échoué', cancelled: 'Annulé',
}
function statusLabel(s) { return STATUS_LABELS[s] || s }

const STATUS_CLASSES = {
  queued: 'bg-slate-800 text-slate-400',
  running: 'bg-blue-900/50 text-blue-400',
  completed: 'bg-green-900/50 text-green-400',
  completed_with_failures: 'bg-amber-900/50 text-amber-400',
  failed: 'bg-red-900/50 text-red-400',
  cancelled: 'bg-purple-900/50 text-purple-400',
}
function statusClass(s) { return STATUS_CLASSES[s] || 'bg-slate-800 text-slate-400' }

const fmtDate = formatDateTime

async function fetchBatches() {
  loading.value = true
  error.value = ''
  try {
    const res = await apiFetch('/api/compute/admin/batches')
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || 'Erreur chargement')
    batches.value = (await res.json()).map(b => ({ ...b, busy: false }))
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}
onMounted(fetchBatches)

async function stopBatch(b) {
  b.busy = true
  error.value = ''
  notice.value = ''
  try {
    const res = await apiFetch(`/api/compute/admin/batches/${b.id}/stop`, { method: 'POST' })
    const data = await res.json().catch(() => ({}))
    if (!res.ok) throw new Error(data.detail || 'Erreur arrêt')
    Object.assign(b, data)
    notice.value = 'Batch arrêté'
  } catch (e) {
    error.value = e.message
  } finally {
    b.busy = false
  }
}

async function relaunchBatch(b) {
  b.busy = true
  error.value = ''
  notice.value = ''
  try {
    const res = await apiFetch(`/api/compute/admin/batches/${b.id}/relaunch`, { method: 'POST' })
    const data = await res.json().catch(() => ({}))
    if (!res.ok) throw new Error(data.detail || 'Erreur relance')
    Object.assign(b, data)
    notice.value = 'Batch relancé — le worker le reprendra à son prochain poll'
  } catch (e) {
    error.value = e.message
  } finally {
    b.busy = false
  }
}

async function deleteBatch(b) {
  if (!await confirmer({ titre: `Supprimer le batch « ${b.label} » ?`,
                       message: `${b.total_jobs} job(s) seront supprimés. Irréversible.`,
                       confirmer: 'Supprimer le batch', danger: true })) return
  b.busy = true
  error.value = ''
  notice.value = ''
  try {
    const res = await apiFetch(`/api/compute/admin/batches/${b.id}`, { method: 'DELETE' })
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || 'Erreur suppression')
    batches.value = batches.value.filter(x => x.id !== b.id)
    notice.value = 'Batch supprimé'
  } catch (e) {
    error.value = e.message
    b.busy = false
  }
}
</script>
