<template>
  <div class="flex-1 flex flex-col min-h-0">

    <div class="flex-1 flex min-h-0">

      <!-- Sidebar -->
      <aside class="w-52 shrink-0 border-r border-slate-800 p-4 flex flex-col gap-1">
        <RouterLink to="/pricer" class="btn-ghost btn-sm mb-2 text-center">← Pricer</RouterLink>
        <button v-for="s in sections" :key="s.id"
          @click="activeSection = s.id"
          :class="[
            'flex items-center gap-2.5 px-3 py-2.5 rounded-lg text-sm text-left transition-colors',
            activeSection === s.id
              ? 'bg-blue-900/40 text-blue-300 border border-blue-700/50'
              : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
          ]">
          <span>{{ s.icon }}</span>
          <span>{{ s.label }}</span>
        </button>
      </aside>

      <!-- Main content -->
      <main class="flex-1 overflow-y-auto p-6">

        <!-- ── BIBLIOTHÈQUE ─────────────────────────────────── -->
        <div v-if="activeSection === 'library'">
          <div class="flex items-center justify-between mb-6">
            <div>
              <h1 class="text-xl font-display font-bold text-slate-100">Bibliothèque de documents</h1>
              <p class="text-sm text-slate-500 mt-0.5">Tous vos documents générés, classés par deal</p>
            </div>
            <div class="flex items-center gap-2">
              <select v-model="filterType" class="select text-xs py-1.5">
                <option value="">Tous les types</option>
                <option value="kid">KID PRIIPs</option>
                <option value="termsheet_indicatif">Term Sheet indicatif</option>
                <option value="termsheet_final">Term Sheet final</option>
                <option value="confirmation">Confirmation</option>
                <option value="autre">Autre</option>
              </select>
              <button class="btn-secondary text-xs px-3 py-1.5" @click="loadDocs">↺ Actualiser</button>
            </div>
          </div>

          <div v-if="loadingDocs" class="text-center py-12 text-slate-600">Chargement…</div>

          <div v-else-if="!filteredDocs.length"
            class="text-center py-16 border-2 border-dashed border-slate-800 rounded-xl">
            <div class="text-4xl mb-3">📄</div>
            <p class="text-slate-500 font-medium">Aucun document</p>
            <p class="text-slate-600 text-sm mt-1">
              Utilisez l'onglet "Générateur" pour créer vos premiers documents.
            </p>
          </div>

          <div v-else class="flex flex-col gap-2">
            <div v-for="doc in filteredDocs" :key="doc.id"
              class="card flex items-center gap-4 hover:border-slate-600 hover:shadow-xl hover:shadow-black/30
                     hover:-translate-y-0.5 transition-all duration-200">
              <div class="w-10 h-10 rounded-lg flex items-center justify-center shrink-0"
                :class="docTypeColor(doc.doc_type)">
                <span class="text-lg">{{ docTypeIcon(doc.doc_type) }}</span>
              </div>
              <div class="flex-1 min-w-0">
                <div class="font-semibold text-slate-200 text-sm truncate">{{ doc.title }}</div>
                <div class="text-xs text-slate-500 mt-0.5 flex items-center gap-3">
                  <span :class="docTypeBadge(doc.doc_type)"
                    class="px-1.5 py-0.5 rounded text-[10px] font-medium">
                    {{ docTypeLabel(doc.doc_type) }}
                  </span>
                  <span v-if="doc.deal_id" class="text-slate-600">Deal #{{ doc.deal_id }}</span>
                  <span>{{ fmtDate(doc.created_at) }}</span>
                </div>
              </div>
              <div class="flex items-center gap-2 shrink-0">
                <a :href="`/api/documents/${doc.id}/download`"
                  target="_blank" class="btn-secondary text-xs px-2.5 py-1">
                  ↓ Télécharger
                </a>
                <button class="text-slate-600 hover:text-red-400 transition-colors text-xs px-2 py-1"
                  @click="deleteDoc(doc.id)">✕</button>
              </div>
            </div>
          </div>
        </div>

        <!-- ── GÉNÉRATEUR ──────────────────────────────────── -->
        <div v-if="activeSection === 'generator'">
          <h1 class="text-xl font-display font-bold text-slate-100 mb-1">Générateur de documents</h1>
          <p class="text-sm text-slate-500 mb-6">
            Sélectionnez un type de document, configurez-le et générez.
          </p>

          <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">

            <!-- Term Sheet Indicatif -->
            <div class="card flex flex-col gap-3 hover:border-blue-700 hover:shadow-xl hover:shadow-black/30
                       hover:-translate-y-0.5 transition-all duration-200">
              <div class="flex items-center gap-3">
                <div class="w-12 h-12 rounded-xl bg-blue-900/50 flex items-center justify-center text-2xl">📋</div>
                <div>
                  <div class="font-bold text-slate-100">Term Sheet Indicatif</div>
                  <div class="text-xs text-slate-500">Avant booking · Pricing en cours</div>
                </div>
              </div>
              <p class="text-xs text-slate-600">
                Résumé commercial du produit : sous-jacents, maturité, prix, paramètres clés, flux attendus.
                Généré depuis le pricing en cours dans le Pricer.
              </p>
              <RouterLink to="/pricer" class="btn-primary text-xs text-center py-2">
                → Aller dans le Pricer
              </RouterLink>
            </div>

            <!-- KID PRIIPs -->
            <div class="card flex flex-col gap-3 hover:border-amber-700 hover:shadow-xl hover:shadow-black/30
                       hover:-translate-y-0.5 transition-all duration-200">
              <div class="flex items-center gap-3">
                <div class="w-12 h-12 rounded-xl bg-amber-900/50 flex items-center justify-center text-2xl">⚖️</div>
                <div>
                  <div class="font-bold text-slate-100">KID PRIIPs</div>
                  <div class="text-xs text-slate-500">Réglementaire · Règlement EU 1286/2014</div>
                </div>
              </div>
              <p class="text-xs text-slate-600">
                SRI 1→7, scénarios de performance (stress / défavorable / modéré / favorable) à 3 horizons,
                composition des coûts. Disponible dans l'onglet "KID" du Pricer.
              </p>
              <RouterLink to="/pricer" class="btn-secondary text-xs text-center py-2">
                → Aller dans le Pricer (onglet KID)
              </RouterLink>
            </div>

            <!-- Term Sheet Final (après booking) -->
            <div class="card flex flex-col gap-3 hover:border-emerald-700 hover:shadow-xl hover:shadow-black/30
                       hover:-translate-y-0.5 transition-all duration-200">
              <div class="flex items-center gap-3">
                <div class="w-12 h-12 rounded-xl bg-emerald-900/50 flex items-center justify-center text-2xl">✅</div>
                <div>
                  <div class="font-bold text-slate-100">Term Sheet Final</div>
                  <div class="text-xs text-slate-500">Post-booking · Référence deal requise</div>
                </div>
              </div>
              <p class="text-xs text-slate-600">
                Version définitive avec référence deal, contrepartie, dates exactes, spots S₀.
                Requiert un deal booké dans l'onglet Events.
              </p>
              <div class="flex items-center gap-2">
                <select v-model="selectedDealForTs" class="select text-xs py-1.5 flex-1">
                  <option :value="null">— Sélectionner un deal —</option>
                  <option v-for="d in deals" :key="d.id" :value="d.id">{{ d.reference }}</option>
                </select>
                <button class="btn-primary text-xs px-3 py-2"
                  :disabled="!selectedDealForTs"
                  @click="openTermSheetFinal">
                  Générer →
                </button>
              </div>
            </div>

            <!-- Confirmation de trade -->
            <div class="card flex flex-col gap-3 border-slate-800 opacity-50 cursor-not-allowed">
              <div class="flex items-center gap-3">
                <div class="w-12 h-12 rounded-xl bg-slate-800 flex items-center justify-center text-2xl">🏦</div>
                <div>
                  <div class="font-bold text-slate-400">Confirmation de trade</div>
                  <div class="text-xs text-slate-600">Back-office · Bientôt disponible</div>
                </div>
              </div>
              <p class="text-xs text-slate-700">
                Format ISDA / SIFMA, instructions de règlement, références de contrepartie.
              </p>
            </div>

          </div>
        </div>

        <!-- ── TEMPLATES ────────────────────────────────────── -->
        <div v-if="activeSection === 'templates'">
          <h1 class="text-xl font-display font-bold text-slate-100 mb-1">Templates</h1>
          <p class="text-sm text-slate-500 mb-6">
            Personnalisez les modèles de documents par entité.
          </p>
          <div class="text-center py-16 border-2 border-dashed border-slate-800 rounded-xl">
            <div class="text-4xl mb-3">🛠️</div>
            <p class="text-slate-500 font-medium">Bientôt disponible</p>
            <p class="text-slate-600 text-sm mt-1">
              Éditeur de templates Jinja2/HTML avec logo, mentions légales et mise en page personnalisables.
            </p>
          </div>
        </div>

      </main>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { RouterLink } from 'vue-router'
import { apiFetch } from '../utils/api.js'
import { useDealsStore } from '../stores/deals.js'
import { formatDate } from '../utils/format.js'

const dealsStore = useDealsStore()

const activeSection = ref('library')
const sections = [
  { id: 'library',   icon: '📚', label: 'Bibliothèque' },
  { id: 'generator', icon: '⚡', label: 'Générateur' },
  { id: 'templates', icon: '🎨', label: 'Templates' },
]

const docs = ref([])
const loadingDocs = ref(false)
const filterType = ref('')
const selectedDealForTs = ref(null)

const deals = computed(() => dealsStore.deals)

const filteredDocs = computed(() => {
  if (!filterType.value) return docs.value
  return docs.value.filter(d => d.doc_type === filterType.value)
})

onMounted(async () => {
  await Promise.all([loadDocs(), dealsStore.loadDeals()])
})

async function loadDocs() {
  loadingDocs.value = true
  try {
    const res = await apiFetch('/api/documents')
    if (res.ok) docs.value = await res.json()
  } finally {
    loadingDocs.value = false
  }
}

async function deleteDoc(id) {
  if (!await confirmer({ titre: 'Supprimer ce document ?',
                       confirmer: 'Supprimer', danger: true })) return
  await apiFetch(`/api/documents/${id}`, { method: 'DELETE' })
  docs.value = docs.value.filter(d => d.id !== id)
}

function openTermSheetFinal() {
  if (!selectedDealForTs.value) return
  window.open(`#/documentation/termsheet/${selectedDealForTs.value}`, '_blank')
}

const fmtDate = formatDate

function docTypeLabel(t) {
  const m = {
    kid: 'KID PRIIPs', termsheet_indicatif: 'Term Sheet indicatif',
    termsheet_final: 'Term Sheet final', confirmation: 'Confirmation', autre: 'Autre',
  }
  return m[t] || t
}

function docTypeIcon(t) {
  const m = { kid: '⚖️', termsheet_indicatif: '📋', termsheet_final: '✅', confirmation: '🏦', autre: '📄' }
  return m[t] || '📄'
}

function docTypeColor(t) {
  const m = {
    kid: 'bg-amber-900/40', termsheet_indicatif: 'bg-blue-900/40',
    termsheet_final: 'bg-emerald-900/40', confirmation: 'bg-purple-900/40', autre: 'bg-slate-800',
  }
  return m[t] || 'bg-slate-800'
}

function docTypeBadge(t) {
  const m = {
    kid: 'bg-amber-900/40 text-amber-400', termsheet_indicatif: 'bg-blue-900/40 text-blue-400',
    termsheet_final: 'bg-emerald-900/40 text-emerald-400', confirmation: 'bg-purple-900/40 text-purple-400',
    autre: 'bg-slate-700 text-slate-400',
  }
  return m[t] || 'bg-slate-700 text-slate-400'
}
</script>
