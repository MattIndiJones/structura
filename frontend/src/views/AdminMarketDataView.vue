<template>
  <div class="flex-1 flex flex-col min-h-0">

    <main class="flex-1 p-6 max-w-5xl w-full mx-auto flex flex-col gap-5">

      <!-- Top bar -->
      <div class="page-header">
        <div>
          <h1 class="page-title">Données de marché</h1>
          <p class="page-subtitle">
            Cache de prix historiques Yahoo Finance — ajustés dividendes &amp; splits.
            <span v-if="!loading" class="ml-2" style="color: var(--subtle);">
              {{ okCount }}/{{ items.length }} séries OK
            </span>
          </p>
        </div>
        <div class="page-actions">
          <RouterLink to="/admin" class="btn-ghost btn-sm">← Administration</RouterLink>
          <button class="btn-secondary text-xs px-3 py-1.5" :disabled="running || loading" @click="doLoadAll">
            Charger tout
          </button>
          <button class="btn-primary text-xs px-3 py-1.5" :disabled="running || loading || missingCount === 0" @click="doRefreshMissing">
            Rafraîchir manquants
            <span v-if="!loading && missingCount > 0" class="ml-1 opacity-70">({{ missingCount }})</span>
          </button>
        </div>
      </div>

      <!-- Error -->
      <AlertMessage v-if="error" kind="error">{{ error }}</AlertMessage>

      <!-- Progress -->
      <div v-if="running" class="card py-3 flex flex-col gap-2">
        <div class="flex items-center justify-between text-xs">
          <span class="text-slate-300 truncate max-w-xs">{{ progress.current }}</span>
          <span class="text-slate-500 flex-shrink-0 ml-4">{{ progress.done }} / {{ progress.total }}</span>
        </div>
        <div class="progress-track">
          <div class="progress-fill" :style="{ width: `${progress.total ? (progress.done / progress.total) * 100 : 0}%` }"></div>
        </div>
      </div>

      <!-- Loading skeleton -->
      <LoadingSpinner v-if="loading" label="Chargement du catalogue…" class="py-10" />

      <!-- Catalog by category -->
      <template v-else>
        <div v-for="cat in byCategory" :key="cat.name" class="card">
          <div class="flex items-center gap-2 mb-3">
            <span class="text-xs font-bold text-slate-300">{{ cat.name }}</span>
            <span class="text-xs text-slate-600">
              {{ cat.items.filter(i => i.cache_status === 'ok').length }}/{{ cat.items.length }} OK
            </span>
          </div>
          <div class="overflow-x-auto overflow-y-auto max-h-64">
            <table class="w-full text-xs">
              <thead class="sticky top-0 z-10 bg-slate-900">
                <tr class="text-left text-slate-500 border-b border-slate-800">
                  <th class="py-1.5 pr-4 font-medium">Sous-jacent</th>
                  <th class="py-1.5 pr-4 font-medium">Ticker</th>
                  <th class="py-1.5 pr-4 font-medium">Statut</th>
                  <th class="py-1.5 pr-4 font-medium">Dernière date</th>
                  <th class="py-1.5 pr-4 font-medium">Devise</th>
                  <th class="py-1.5 pr-3 font-medium text-right">Points</th>
                  <th class="py-1.5 font-medium"></th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="item in cat.items" :key="item.key"
                    class="border-b border-slate-800/40 last:border-0 hover:bg-slate-900/40 transition-colors">
                  <td class="py-2 pr-4 text-slate-200 font-medium whitespace-nowrap">{{ item.label }}</td>
                  <td class="py-2 pr-4 font-mono text-slate-400 whitespace-nowrap">{{ item.ticker }}</td>
                  <td class="py-2 pr-4">
                    <span v-if="item.loading" class="text-slate-500 animate-pulse">chargement…</span>
                    <span v-else-if="item.cache_status === 'ok'"
                          class="inline-block px-2 py-0.5 rounded-full text-[10px] font-semibold bg-green-900/50 text-green-400">OK</span>
                    <span v-else-if="item.cache_status === 'stale'"
                          class="inline-block px-2 py-0.5 rounded-full text-[10px] font-semibold bg-amber-900/50 text-amber-400">Périmé</span>
                    <span v-else-if="item.cache_status === 'error'"
                          class="inline-block px-2 py-0.5 rounded-full text-[10px] font-semibold bg-red-900/50 text-red-400 cursor-help"
                          :title="item.error">Erreur</span>
                    <span v-else
                          class="inline-block px-2 py-0.5 rounded-full text-[10px] font-semibold bg-slate-800 text-slate-500">Manquant</span>
                  </td>
                  <td class="py-2 pr-4 font-mono text-slate-400 whitespace-nowrap">{{ item.date_max || '—' }}</td>
                  <td class="py-2 pr-4 text-slate-500 whitespace-nowrap">{{ item.currency || '—' }}</td>
                  <td class="py-2 pr-3 text-slate-500 text-right whitespace-nowrap">
                    {{ item.rows > 0 ? item.rows.toLocaleString('fr-FR') : '—' }}
                  </td>
                  <td class="py-2">
                    <button class="btn-secondary text-[10px] px-2 py-1 whitespace-nowrap"
                            :disabled="item.loading || running"
                            @click="fetchOne(item)">↓ Fetch</button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </template>

    </main>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { RouterLink } from 'vue-router'
import { apiFetch } from '../utils/api.js'
import LoadingSpinner from '../components/ui/LoadingSpinner.vue'
import AlertMessage from '../components/ui/AlertMessage.vue'

const items    = ref([])
const loading  = ref(true)
const running  = ref(false)
const error    = ref('')
const progress = ref({ done: 0, total: 0, current: '' })

const CATEGORY_ORDER = ['Indices US', 'Indices EU', 'Indices Asie', 'Actions US', 'Actions EU', 'Actions CH', 'Matières premières', 'Crypto']

const byCategory = computed(() => {
  const map = {}
  for (const item of items.value) {
    if (!map[item.category]) map[item.category] = []
    map[item.category].push(item)
  }
  return CATEGORY_ORDER.filter(c => map[c]).map(c => ({ name: c, items: map[c] }))
})

const okCount      = computed(() => items.value.filter(i => i.cache_status === 'ok').length)
const missingCount = computed(() => items.value.filter(i => i.cache_status !== 'ok').length)

async function loadCatalog() {
  loading.value = true
  error.value = ''
  try {
    const res = await apiFetch('/api/admin/market-data')
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || 'Erreur chargement')
    items.value = (await res.json()).map(i => ({ ...i, loading: false, error: '' }))
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}
onMounted(loadCatalog)

async function fetchOne(item) {
  item.loading = true
  item.error = ''
  try {
    const res = await apiFetch('/api/admin/market-data/fetch', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ key: item.key, ticker: item.ticker }),
    })
    const data = await res.json().catch(() => ({}))
    if (!res.ok) {
      item.error = data.detail || 'Erreur'
      item.cache_status = 'error'
    } else {
      item.available    = true
      item.date_min     = data.date_min
      item.date_max     = data.date_max
      item.rows         = data.rows
      item.currency     = data.currency
      item.cache_status = 'ok'
    }
  } catch (e) {
    item.error = e.message
    item.cache_status = 'error'
  } finally {
    item.loading = false
  }
}

async function batchFetch(targets) {
  if (!targets.length) return
  running.value = true
  progress.value = { done: 0, total: targets.length, current: '' }
  for (const item of targets) {
    progress.value.current = `${item.label} (${item.ticker})`
    await fetchOne(item)
    progress.value.done++
    if (progress.value.done < progress.value.total) {
      await new Promise(r => setTimeout(r, 400))
    }
  }
  running.value = false
}

function doLoadAll()        { batchFetch([...items.value]) }
function doRefreshMissing() { batchFetch(items.value.filter(i => i.cache_status !== 'ok')) }
</script>
