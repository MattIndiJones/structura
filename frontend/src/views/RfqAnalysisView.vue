<template>
  <div class="flex-1 flex flex-col min-h-0">

    <main class="flex-1 overflow-y-auto p-6 flex flex-col gap-4">
      <div class="page-header">
        <div>
          <h1 class="page-title">Analyse Contreparties</h1>
        </div>
        <div class="page-actions">
          <RouterLink to="/rfq" class="btn-ghost btn-sm">← Retour aux RFQ</RouterLink>
        </div>
      </div>

      <div v-if="loading" class="text-xs text-slate-600 py-8 text-center">Chargement…</div>

      <template v-else>
        <!-- Filtres -->
        <div class="card flex flex-wrap items-end gap-4">
          <div class="flex flex-col gap-1">
            <label class="label">Type de produit</label>
            <select v-model="filters.templateType" class="select w-56">
              <option value="">Tous les types</option>
              <option v-for="t in templateMeta" :key="t.key" :value="t.key">{{ t.label }}</option>
            </select>
          </div>

          <div class="flex flex-col gap-1">
            <label class="label">Depuis</label>
            <input v-model="filters.from" type="date" class="input w-40" />
          </div>
          <div class="flex flex-col gap-1">
            <label class="label">Jusqu'à</label>
            <input v-model="filters.to" type="date" class="input w-40" />
          </div>

          <div class="flex flex-col gap-1 flex-1 min-w-[220px]">
            <label class="label">Fournisseurs</label>
            <div class="flex flex-wrap gap-3">
              <label v-for="p in distinctProviders" :key="p"
                     class="flex items-center gap-1.5 text-xs text-slate-300 cursor-pointer select-none">
                <input type="checkbox" class="accent-blue-500"
                       :checked="filters.providers.includes(p)"
                       @change="toggleProvider(p)" />
                {{ providerLabel(p) }}
              </label>
              <span v-if="!distinctProviders.length" class="text-xs text-slate-600">Aucune donnée</span>
            </div>
          </div>
        </div>

        <!-- État vide -->
        <div v-if="!rfq.history.length" class="flex flex-col items-center justify-center py-24 gap-3 text-slate-600">
          <div class="text-4xl">📈</div>
          <div class="text-sm">Aucun prix reçu pour l'instant — les données apparaîtront ici au fil des RFQ cotées.</div>
        </div>

        <template v-else>
          <div v-if="excludedNoModelCount" class="text-[10px] text-amber-500/80">
            {{ excludedNoModelCount }} quote(s) exclue(s) — prix modèle non calculé sur leur RFQ.
          </div>
          <div v-if="supersededCount" class="text-[10px] text-slate-500">
            {{ supersededCount }} cotation(s) remplacée(s) par un last look — seule la contre-cote
            finale du fournisseur est comptée, sinon la même banque pèse deux fois dans l'AO.
          </div>

          <!-- Graphique -->
          <div class="card">
            <div class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3"
                 title="Écart au prix modèle Structura, signé de notre côté : positif = en notre faveur, achats et ventes confondus.">
              Écart favorable vs prix modèle par fournisseur (bps)
            </div>
            <canvas ref="chartRef" height="90"></canvas>
          </div>

          <!-- Tableau de synthèse -->
          <div class="card overflow-x-auto">
            <div class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3">Synthèse</div>
            <table class="w-full text-xs">
              <thead>
                <tr class="text-left text-slate-500 border-b border-slate-800">
                  <th class="py-1.5 pr-4 font-medium">Fournisseur</th>
                  <th class="py-1.5 pr-4 font-medium"
                      title="Part des AO tranchés, où ce fournisseur avait coté, qu'il a effectivement gagnés. Les AO encore en cours ne comptent pas ; un AO classé sans suite compte comme non gagné.">Hit ratio</th>
                  <th class="py-1.5 pr-4 font-medium">Nb quotes</th>
                  <th class="py-1.5 pr-4 font-medium"
                      title="Moyenne de l'écart favorable : positif = ce fournisseur cote en moyenne du bon côté de notre prix modèle.">Écart favorable moyen</th>
                  <th class="py-1.5 pr-4 font-medium">Min</th>
                  <th class="py-1.5 pr-4 font-medium">Max</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="row in summaryRows" :key="row.provider" class="border-b border-slate-800/60">
                  <td class="py-1.5 pr-4 text-slate-200">{{ providerLabel(row.provider) }}</td>
                  <td class="py-1.5 pr-4" :class="row.hitRatio === null ? 'text-slate-600' : 'text-slate-200'">{{ fmtHitRatio(row) }}</td>
                  <td class="py-1.5 pr-4 text-slate-400">{{ row.count }}</td>
                  <td class="py-1.5 pr-4" :class="row.avg >= 0 ? 'text-green-400' : 'text-red-400'">{{ fmtBps(row.avg) }}</td>
                  <td class="py-1.5 pr-4 text-slate-500">{{ fmtBps(row.min) }}</td>
                  <td class="py-1.5 pr-4 text-slate-500">{{ fmtBps(row.max) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </template>
      </template>
    </main>
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch, onMounted, onUnmounted } from 'vue'
import { RouterLink } from 'vue-router'
import { Chart, registerables } from 'chart.js'
import { useRfqStore } from '../stores/rfq.js'
import { useDemoModeStore } from '../stores/demoMode.js'
import { demoChartOptions } from '../composables/useSensitiveChart.js'
import { chartTheme, applyChartTheme } from '../charts/theme.js'
import { templateMeta } from '../data/payscriptTemplates.js'
import { formatBps as centralFormatBps } from '../utils/format.js'

Chart.register(...registerables)
applyChartTheme(Chart)
const rfq  = useRfqStore()
const demo = useDemoModeStore()

const loading  = ref(true)
const chartRef = ref(null)
let chart = null

const filters = reactive({ templateType: '', from: '', to: '', providers: [] })

const distinctProviders = computed(() => {
  const seen = new Set(rfq.history.map(h => h.provider))
  return [...seen].sort()
})

// Default to "all providers selected" once history first loads.
watch(distinctProviders, (list) => {
  if (!filters.providers.length) filters.providers = [...list]
}, { immediate: true })

function toggleProvider(p) {
  const i = filters.providers.indexOf(p)
  if (i === -1) filters.providers.push(p)
  else filters.providers.splice(i, 1)
}

// Everything below ranks providers on edge_bps, not the raw spread: it is
// signed from our side (positive = in our favour) whichever way each RFQ was
// traded, so buy and sell tenders can sit in the same average. Raw spreads
// would cancel each other out — see api/rfq.py:_edge_bps.
const excludedNoModelCount = computed(() =>
  rfq.history.filter(h => h.edge_bps === null || h.edge_bps === undefined).length
)

const supersededCount = computed(() => rfq.history.filter(h => h.superseded).length)

const filteredHistory = computed(() => {
  return rfq.history.filter(h => {
    if (h.edge_bps === null || h.edge_bps === undefined) return false
    // Une cotation remplacée par le last look du même fournisseur n'est pas
    // une réponse de plus : la compter mettrait la banque deux fois dans
    // l'AO et tirerait sa moyenne vers sa cotation améliorée.
    if (h.superseded) return false
    if (filters.templateType && h.template_type !== filters.templateType) return false
    if (!filters.providers.includes(h.provider)) return false
    if (filters.from && h.date.slice(0, 10) < filters.from) return false
    if (filters.to && h.date.slice(0, 10) > filters.to) return false
    return true
  })
})

const FACTOR_COLORS = chartTheme.series

function providerLabel(id) {
  return rfq.providers.find(p => p.id === id)?.label || id
}

function fmtBps(v) {
  if (v === null || v === undefined) return '—'
  return (v >= 0 ? '+' : '') + centralFormatBps(v, 0)
}

// Hit ratio : gagnés / AO tranchés où la banque a coté. Le dénominateur
// exclut volontairement les AO encore en cours — une banque qui vient de
// coter un AO non tranché n'a rien perdu. Un AO classé « sans suite » y
// reste en revanche : personne ne l'a gagné, c'est un AO où sa cotation
// n'a pas abouti.
const DECIDED = new Set(['clos', 'sans_suite'])

const summaryRows = computed(() => {
  const byProvider = {}
  for (const h of filteredHistory.value) {
    const p = (byProvider[h.provider] ||= { edges: [], won: 0, decided: 0 })
    p.edges.push(h.edge_bps)
    if (DECIDED.has(h.rfq_status)) p.decided++
    if (h.won) p.won++
  }
  return Object.entries(byProvider).map(([provider, p]) => ({
    provider,
    count: p.edges.length,
    avg: p.edges.reduce((a, b) => a + b, 0) / p.edges.length,
    min: Math.min(...p.edges),
    max: Math.max(...p.edges),
    won: p.won,
    decided: p.decided,
    hitRatio: p.decided ? p.won / p.decided : null,
  })).sort((a, b) => (b.hitRatio ?? -1) - (a.hitRatio ?? -1) || a.provider.localeCompare(b.provider))
})

function fmtHitRatio(row) {
  if (row.hitRatio === null) return '—'
  return `${Math.round(row.hitRatio * 100)}% (${row.won}/${row.decided})`
}

function chartOpts() {
  return {
    responsive: true, maintainAspectRatio: true,
    plugins: {
      legend: { display: true, labels: { font: { size: 10 }, boxWidth: 12 } },
      tooltip: {
        callbacks: { label: ctx => ` ${ctx.dataset.label}: ${ctx.parsed.y >= 0 ? '+' : ''}${ctx.parsed.y} bps` },
      },
    },
    scales: {
      x: { ticks: { font: { size: 9 }, maxTicksLimit: 8 } },
      y: { ticks: { font: { size: 9 }, callback: v => `${v} bps` } },
    },
  }
}

// Chart.js category scale (no date adapter installed in this project) —
// build a shared, sorted date-label axis and align each provider's series
// to it (null where that provider has no quote on a given date).
function rebuildChart() {
  chart?.destroy()
  if (!chartRef.value || !filters.providers.length) return

  const labels = [...new Set(filteredHistory.value.map(h => h.date.slice(0, 10)))].sort()

  const datasets = filters.providers.map((provider, i) => {
    const byDate = {}
    for (const h of filteredHistory.value) {
      if (h.provider === provider) byDate[h.date.slice(0, 10)] = h.edge_bps
    }
    return {
      label: providerLabel(provider),
      data: labels.map(d => byDate[d] ?? null),
      spanGaps: true,
      borderColor: FACTOR_COLORS[i % FACTOR_COLORS.length],
      backgroundColor: 'transparent',
      borderWidth: 2, pointRadius: 3, tension: 0.2,
    }
  })

  chart = new Chart(chartRef.value, {
    type: 'line',
    data: { labels, datasets },
    options: demoChartOptions(chartOpts(), demo.enabled),
  })
}

watch([filteredHistory, () => filters.providers.length, () => demo.enabled], rebuildChart)

onMounted(async () => {
  loading.value = true
  try {
    await Promise.all([rfq.fetchHistory(), rfq.fetchProviders()])
  } finally {
    loading.value = false
  }
})

onUnmounted(() => chart?.destroy())
</script>
