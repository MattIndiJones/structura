<template>
  <div class="min-h-screen bg-slate-950 flex flex-col text-slate-100">

    <!-- Header -->
    <header class="border-b border-slate-800 px-6 py-3 flex items-center gap-4 shrink-0">
      <RouterLink to="/" class="text-slate-500 hover:text-slate-300 transition-colors text-sm">← Accueil</RouterLink>
      <span class="text-slate-700">|</span>
      <span class="font-bold text-slate-100 tracking-tight">Carnet d'ordres — FIFO</span>
      <div class="ml-auto flex items-center gap-3">
        <span v-if="result" class="text-xs text-slate-500">{{ result.meta.order_count }} ordres · {{ result.meta.isin_count }} ISINs · {{ result.meta.as_of }}</span>
      </div>
    </header>

    <div class="flex flex-1 overflow-hidden">

      <!-- Sidebar config -->
      <aside class="w-72 border-r border-slate-800 flex flex-col gap-4 p-4 shrink-0 overflow-y-auto">

        <div class="text-xs font-semibold text-slate-400 uppercase tracking-widest">Configuration</div>

        <!-- Folder -->
        <div class="flex flex-col gap-1.5">
          <label class="text-xs text-slate-400">Dossier carnet</label>
          <input v-model="folder" placeholder="Chemin absolu…"
            class="input text-xs font-mono" @keydown.enter="detect" />
          <button class="btn-secondary text-xs" @click="detect" :disabled="!folder || detecting">
            {{ detecting ? 'Scan…' : 'Scanner' }}
          </button>
          <div v-if="detectedFiles.length" class="text-xs text-slate-500 mt-1">
            <div v-for="f in detectedFiles" :key="f" class="truncate">📄 {{ f }}</div>
          </div>
        </div>

        <!-- Mode -->
        <div class="flex flex-col gap-1.5">
          <label class="text-xs text-slate-400">Mode quantités</label>
          <select v-model="qtyMode" class="input text-xs">
            <option value="auto">Auto-détection</option>
            <option value="shares">Actions réelles (shares)</option>
            <option value="cert_units">Unités de compte (cert-units)</option>
          </select>
          <div v-if="detectedMode" class="text-xs text-cyan-400">Détecté : {{ detectedMode }}</div>
        </div>

        <div class="flex flex-col gap-1.5">
          <label class="text-xs text-slate-400">Mode reconstruction</label>
          <select v-model="reconMode" class="input text-xs">
            <option value="t0_synthetic">T0 synthétique (recommandé)</option>
            <option value="strict">Strict (pas d'injection)</option>
          </select>
        </div>

        <div class="flex flex-col gap-1.5">
          <label class="text-xs text-slate-400">Devise du produit</label>
          <select v-model="prodCcy" class="input text-xs">
            <option>USD</option><option>EUR</option><option>CHF</option>
            <option>GBP</option><option>JPY</option>
          </select>
        </div>

        <button class="btn-primary text-sm mt-2" @click="run"
          :disabled="!folder || loading">
          {{ loading ? 'Calcul…' : 'Lancer le FIFO' }}
        </button>

        <div v-if="error" class="text-xs text-red-400 bg-red-950/30 rounded p-2">{{ error }}</div>

        <!-- Mini summary -->
        <div v-if="result" class="flex flex-col gap-2 border-t border-slate-800 pt-4">
          <div class="text-xs font-semibold text-slate-400 uppercase tracking-widest">Résumé</div>
          <div class="flex flex-col gap-1 text-xs">
            <div class="flex justify-between">
              <span class="text-slate-400">Mode appliqué</span>
              <span class="text-cyan-300 font-mono">{{ result.meta.qty_mode }}</span>
            </div>
            <div class="flex justify-between">
              <span class="text-slate-400">P&L réalisé</span>
              <span :class="result.summary.total_realized >= 0 ? 'text-green-400' : 'text-red-400'" class="font-mono">
                {{ fmt(result.summary.total_realized) }}
              </span>
            </div>
            <div class="flex justify-between">
              <span class="text-slate-400">P&L latent</span>
              <span :class="(result.summary.total_latent ?? 0) >= 0 ? 'text-green-400' : 'text-red-400'" class="font-mono">
                {{ result.summary.total_latent != null ? fmt(result.summary.total_latent) : 'N/A' }}
              </span>
            </div>
            <div class="flex justify-between border-t border-slate-700 pt-1 mt-1">
              <span class="text-slate-300 font-semibold">P&L total</span>
              <span :class="(result.summary.total_pnl ?? 0) >= 0 ? 'text-green-300' : 'text-red-300'" class="font-mono font-bold">
                {{ result.summary.total_pnl != null ? fmt(result.summary.total_pnl) : 'N/A' }}
              </span>
            </div>
            <div class="flex justify-between text-slate-500 mt-1">
              <span>Positions ouvertes</span><span>{{ result.summary.open_position_count }}</span>
            </div>
            <div class="flex justify-between text-slate-500">
              <span>Round trips</span><span>{{ result.summary.round_trip_count }}</span>
            </div>
            <div class="flex justify-between text-slate-500">
              <span>Synthétiques</span><span>{{ result.summary.synthetic_count }}</span>
            </div>
          </div>
        </div>

      </aside>

      <!-- Main panel -->
      <main class="flex-1 overflow-auto p-4 flex flex-col gap-4">

        <!-- Placeholder -->
        <div v-if="!result && !loading" class="flex-1 flex items-center justify-center text-slate-600 text-sm">
          Entrez un chemin de dossier et lancez le FIFO
        </div>

        <!-- Loading -->
        <div v-if="loading" class="flex-1 flex items-center justify-center text-slate-500 text-sm">
          <div class="flex flex-col items-center gap-3">
            <div class="w-6 h-6 border-2 border-cyan-600 border-t-transparent rounded-full animate-spin"></div>
            Reconstruction FIFO en cours…
          </div>
        </div>

        <template v-if="result && !loading">

          <!-- Tabs -->
          <div class="flex gap-1 border-b border-slate-800 shrink-0">
            <button v-for="t in tabs" :key="t.key" @click="tab = t.key"
              class="px-4 py-2 text-xs font-medium transition-colors"
              :class="tab === t.key ? 'text-cyan-300 border-b-2 border-cyan-500' : 'text-slate-500 hover:text-slate-300'">
              {{ t.label }}
            </button>
          </div>

          <!-- Open Positions -->
          <div v-if="tab === 'open'" class="overflow-auto">
            <table class="w-full text-xs text-left border-collapse">
              <thead>
                <tr class="text-slate-500 border-b border-slate-800">
                  <th class="py-2 pr-4 font-medium">Instrument</th>
                  <th class="py-2 pr-4 font-medium text-right">Qté ouverte</th>
                  <th class="py-2 pr-4 font-medium text-right">Coût moy.</th>
                  <th class="py-2 pr-4 font-medium text-right">Mark</th>
                  <th class="py-2 pr-4 font-medium text-right">Coût total</th>
                  <th class="py-2 font-medium text-right">Latent</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="p in sortedOpen" :key="p.isin"
                  class="border-b border-slate-800/50 hover:bg-slate-800/30 transition-colors">
                  <td class="py-1.5 pr-4">
                    <div class="font-medium text-slate-200">{{ p.name }}</div>
                    <div class="text-slate-600 font-mono text-[10px]">{{ p.isin }}</div>
                  </td>
                  <td class="py-1.5 pr-4 text-right font-mono text-slate-300">{{ fmtQty(p.open_qty) }}</td>
                  <td class="py-1.5 pr-4 text-right font-mono text-slate-300">{{ fmtPx(p.avg_cost_prod) }}</td>
                  <td class="py-1.5 pr-4 text-right font-mono" :class="p.mark_prod ? 'text-slate-300' : 'text-slate-600'">
                    {{ p.mark_prod != null ? fmtPx(p.mark_prod) : '—' }}
                  </td>
                  <td class="py-1.5 pr-4 text-right font-mono text-slate-400">{{ fmt(p.cost_prod) }}</td>
                  <td class="py-1.5 text-right font-mono font-semibold"
                    :class="(p.unreal_pnl_prod ?? 0) >= 0 ? 'text-green-400' : 'text-red-400'">
                    {{ p.unreal_pnl_prod != null ? fmt(p.unreal_pnl_prod) : '—' }}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          <!-- Round Trips -->
          <div v-if="tab === 'trips'" class="overflow-auto">
            <table class="w-full text-xs text-left border-collapse">
              <thead>
                <tr class="text-slate-500 border-b border-slate-800">
                  <th class="py-2 pr-4 font-medium">Instrument</th>
                  <th class="py-2 pr-4 font-medium">Achat</th>
                  <th class="py-2 pr-4 font-medium">Vente</th>
                  <th class="py-2 pr-4 font-medium text-right">Qté</th>
                  <th class="py-2 pr-4 font-medium text-right">Px achat</th>
                  <th class="py-2 pr-4 font-medium text-right">Px vente</th>
                  <th class="py-2 font-medium text-right">P&L réalisé</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(rt, i) in result.round_trips" :key="i"
                  class="border-b border-slate-800/50 hover:bg-slate-800/30 transition-colors">
                  <td class="py-1.5 pr-4">
                    <div class="font-medium text-slate-200">{{ rt.name }}</div>
                    <div v-if="rt.buy_source === 'synthetic_t0'" class="text-[10px] text-amber-500">synthétique T0</div>
                  </td>
                  <td class="py-1.5 pr-4 font-mono text-slate-500">{{ rt.buy_date }}</td>
                  <td class="py-1.5 pr-4 font-mono text-slate-500">{{ rt.sell_date }}</td>
                  <td class="py-1.5 pr-4 text-right font-mono text-slate-300">{{ fmtQty(rt.qty) }}</td>
                  <td class="py-1.5 pr-4 text-right font-mono text-slate-400">{{ fmtPx(rt.buy_price_prod) }}</td>
                  <td class="py-1.5 pr-4 text-right font-mono text-slate-400">{{ fmtPx(rt.sell_price_prod) }}</td>
                  <td class="py-1.5 text-right font-mono font-semibold"
                    :class="rt.pnl_prod >= 0 ? 'text-green-400' : 'text-red-400'">
                    {{ fmt(rt.pnl_prod) }}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          <!-- Synthetics -->
          <div v-if="tab === 'synth'" class="overflow-auto">
            <div class="text-xs text-slate-500 mb-3">
              Injections synthétiques T0 : BUYs injectés à la date d'inception pour couvrir des ventes sans achat préalable dans le carnet.
            </div>
            <table class="w-full text-xs text-left border-collapse">
              <thead>
                <tr class="text-slate-500 border-b border-slate-800">
                  <th class="py-2 pr-4 font-medium">Instrument</th>
                  <th class="py-2 pr-4 font-medium text-right">Excès vente</th>
                  <th class="py-2 pr-4 font-medium">Date T0</th>
                  <th class="py-2 pr-4 font-medium text-right">Prix injecté</th>
                  <th class="py-2 pr-4 font-medium">Source</th>
                  <th class="py-2 font-medium text-center">Injecté</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(s, i) in result.synthetic_report" :key="i"
                  class="border-b border-slate-800/50 hover:bg-slate-800/30 transition-colors">
                  <td class="py-1.5 pr-4 font-medium text-slate-200">{{ s.name }}</td>
                  <td class="py-1.5 pr-4 text-right font-mono text-slate-300">{{ fmtQty(s.excess_qty) }}</td>
                  <td class="py-1.5 pr-4 font-mono text-slate-500">{{ s.t0_date }}</td>
                  <td class="py-1.5 pr-4 text-right font-mono text-slate-400">{{ s.price_prod > 0 ? fmtPx(s.price_prod) : '—' }}</td>
                  <td class="py-1.5 pr-4 text-slate-500">{{ s.source }}</td>
                  <td class="py-1.5 text-center">
                    <span v-if="s.injected" class="text-green-400">✓</span>
                    <span v-else class="text-red-500">✗</span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

        </template>
      </main>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { RouterLink } from 'vue-router'
import { useAuthStore } from '../stores/auth.js'
import { apiFetch } from '../utils/api.js'

const auth = useAuthStore()

const folder     = ref('')
const qtyMode    = ref('auto')
const reconMode  = ref('t0_synthetic')
const prodCcy    = ref('USD')
const loading    = ref(false)
const detecting  = ref(false)
const error      = ref('')
const result     = ref(null)
const detectedFiles = ref([])
const detectedMode  = ref('')
const tab        = ref('open')

const tabs = [
  { key: 'open',  label: 'Positions ouvertes' },
  { key: 'trips', label: 'Round trips' },
  { key: 'synth', label: 'Synthétiques' },
]

const sortedOpen = computed(() => {
  if (!result.value) return []
  return [...result.value.open_positions].sort(
    (a, b) => Math.abs(b.unreal_pnl_prod ?? 0) - Math.abs(a.unreal_pnl_prod ?? 0)
  )
})

async function detect() {
  if (!folder.value) return
  detecting.value = true
  error.value = ''
  try {
    const data = await apiFetch('/api/fifo/detect', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ folder: folder.value }),
    })
    detectedFiles.value = data.files || []
    detectedMode.value  = data.suggested_mode || ''
    if (qtyMode.value === 'auto') detectedMode.value = `auto → ${data.suggested_mode}`
  } catch (e) {
    error.value = e.message || 'Erreur scan'
  } finally {
    detecting.value = false
  }
}

async function run() {
  if (!folder.value) return
  loading.value = true
  error.value   = ''
  result.value  = null
  tab.value     = 'open'
  try {
    result.value = await apiFetch('/api/fifo/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        folder:     folder.value,
        qty_mode:   qtyMode.value,
        recon_mode: reconMode.value,
        prod_ccy:   prodCcy.value,
      }),
    })
    detectedMode.value = result.value.meta.detected_mode
  } catch (e) {
    error.value = e.message || 'Erreur FIFO'
  } finally {
    loading.value = false
  }
}

const fmtNum = new Intl.NumberFormat('fr-CH', { maximumFractionDigits: 0 })
const fmtPxN = new Intl.NumberFormat('fr-CH', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

function fmt(v) {
  if (v == null) return '—'
  return (v >= 0 ? '+' : '') + fmtNum.format(v)
}
function fmtPx(v) {
  return v != null ? fmtPxN.format(v) : '—'
}
function fmtQty(v) {
  return v != null ? fmtNum.format(v) : '—'
}
</script>
