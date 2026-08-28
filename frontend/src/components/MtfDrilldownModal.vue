<!--
  Panneau d'explication d'un mark-to-future.

  Répond à « pourquoi le P05 vaut-il 47 % ? » en ouvrant les trajectoires qui
  portent chaque quantile. Le chiffre affiché ici est celui du graphique, au
  centime : le backend rejoue les mêmes tirages (même graine, même rang de date,
  même lot). Le tableau des flux futurs se resomme exactement au mark, et l'écart
  de reconstitution est publié plutôt que masqué.
-->
<template>
  <BaseModal :model-value="modelValue" max-width="1180px"
             :title="`Analyse de trajectoires — date de valorisation ${fmtY(drill?.t)}`"
             @update:model-value="$emit('update:modelValue', $event)">

    <div v-if="loading" class="flex items-center justify-center gap-3 py-12 text-sm text-slate-500">
      <span class="w-4 h-4 border-2 border-slate-400 border-t-transparent rounded-full animate-spin"></span>
      Rejeu des scénarios…
    </div>

    <AlertMessage v-else-if="errorMsg" kind="error">{{ errorMsg }}</AlertMessage>

    <template v-else-if="drill">
      <!-- Sélecteur de scénario -->
      <div class="flex flex-wrap items-center gap-2">
        <button v-for="(sc, i) in drill.scenarios" :key="sc.id"
                class="px-3 py-1.5 rounded-[10px] text-xs font-bold border transition-colors"
                :class="i === activeIdx
                  ? 'bg-[var(--accent)] text-white border-[var(--accent)]'
                  : 'bg-[var(--surface2)] text-[var(--muted)] border-[var(--border)] hover:border-[var(--accent)]'"
                @click="activeIdx = i">
          {{ sc.label || `#${sc.id}` }}
          <span class="opacity-70 font-mono ml-1">{{ pf(sc.mtf) }}</span>
        </button>
        <div class="ml-auto text-[11px] text-slate-500">
          {{ drill.n_inner }} chemins internes par scénario · calcul {{ Math.round(drill.elapsed_ms) }} ms
        </div>
      </div>

      <template v-if="sc">
        <!-- Bandeau de synthèse -->
        <div class="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-6 gap-2">
          <div v-for="tile in headline" :key="tile.label" class="stat-box !p-3">
            <div class="text-[10px] uppercase tracking-wider text-slate-500 mb-0.5">
              {{ tile.label }}<HelpTip v-if="tile.tip" :text="tile.tip" />
            </div>
            <div class="text-sm font-bold font-mono" :class="tile.cls">{{ tile.val }}</div>
          </div>
        </div>

        <!-- MTF vs payoff final réalisé -->
        <div class="card !p-4">
          <div class="text-xs font-bold text-slate-500 uppercase tracking-wide mb-2">
            Mark-to-Future à {{ fmtY(drill.t) }} vs payoff final de CETTE trajectoire
            <HelpTip text="À gauche : l'espérance, sur cette trajectoire de marché, de ce que le produit vaut encore — moyenne des re-pricings internes. À droite : ce que cette trajectoire précise finit réellement par payer si on la laisse courir jusqu'au bout. Le mark n'a aucune raison d'égaler le réalisé : il en est l'espérance conditionnelle. L'écart, c'est le risque restant à cette date." />
          </div>
          <div class="flex flex-wrap items-stretch gap-3">
            <div class="flex-1 min-w-[180px] rounded-[10px] p-3"
                 style="background: var(--accent-light); border: 1px solid var(--border);">
              <div class="text-[11px] text-slate-600 mb-1">MTF à {{ fmtY(drill.t) }} (valeur en {{ fmtY(drill.t) }})</div>
              <div class="text-xl font-bold font-mono text-[var(--accent)]">{{ pf(sc.mtf) }}</div>
              <div class="text-[11px] text-slate-500 mt-1">
                {{ sc.alive ? 'Contrat encore vivant' : 'Contrat déjà éteint — rien à marquer' }}
              </div>
            </div>
            <div class="flex-1 min-w-[180px] rounded-[10px] p-3"
                 style="background: var(--surface2); border: 1px solid var(--border);">
              <div class="text-[11px] text-slate-600 mb-1">Payoff final réalisé (non actualisé)</div>
              <div class="text-xl font-bold font-mono"
                   :class="sc.final.total_undiscounted >= 100 ? 'text-[var(--positive)]' : 'text-[var(--negative)]'">
                {{ pf(sc.final.total_undiscounted) }}
              </div>
              <div class="text-[11px] text-slate-500 mt-1">
                {{ sc.final.recalled ? `Rappelé à ${fmtY(sc.final.stop_t)}` : 'Porté jusqu\'à maturité' }}
                · VA à t=0 : {{ pf(sc.final.pv_at_0) }}
              </div>
            </div>
            <div class="flex-1 min-w-[180px] rounded-[10px] p-3"
                 style="background: var(--surface2); border: 1px solid var(--border);">
              <div class="text-[11px] text-slate-600 mb-1">Déjà encaissé avant {{ fmtY(drill.t) }}</div>
              <div class="text-xl font-bold font-mono text-slate-700">{{ pf(sc.realized_cash) }}</div>
              <div class="text-[11px] text-slate-500 mt-1">
                {{ sc.realized_flows.length }} flux — hors du mark, par construction
              </div>
            </div>
          </div>
        </div>

        <!-- Trajectoire -->
        <div class="card !p-4">
          <div class="text-xs font-bold text-slate-500 uppercase tracking-wide mb-2">
            Évolution du sous-jacent (worst-of) — scénario #{{ sc.id }}
          </div>
          <div style="height:230px;position:relative;"><canvas ref="pathCanvas"></canvas></div>
        </div>

        <!-- Observations -->
        <div class="card !p-4 overflow-x-auto">
          <div class="text-xs font-bold text-slate-500 uppercase tracking-wide mb-2">
            Calendrier d'observation et statut
          </div>
          <table class="w-full text-xs border-collapse">
            <thead>
              <tr class="border-b border-[var(--border)] text-slate-500">
                <th class="text-left py-1.5 pr-3 font-semibold">Date</th>
                <th class="text-right py-1.5 pr-3 font-semibold">Worst-of</th>
                <th v-for="b in drill.barriers" :key="b.name" class="text-right py-1.5 pr-3 font-semibold whitespace-nowrap">
                  Dist. {{ b.name }}
                  <HelpTip :text="`Écart relatif du worst-of au niveau ${b.name} (${fmtLvl(b)}), comparé via ${b.observable}. Positif = au-dessus du niveau.`" />
                </th>
                <th class="text-left py-1.5 pr-3 font-semibold">Statut</th>
                <th class="text-left py-1.5 font-semibold">Flux payés</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="o in sc.observations" :key="o.step"
                  class="border-b border-[var(--border)]/40"
                  :class="o.past ? '' : 'opacity-70'">
                <td class="py-1.5 pr-3 font-mono whitespace-nowrap">
                  {{ fmtY(o.t) }}
                  <span v-if="o.past" class="text-[10px] text-slate-400 ml-1">passé</span>
                </td>
                <td class="py-1.5 pr-3 text-right font-mono">{{ pf(o.wof * 100) }}</td>
                <td v-for="b in drill.barriers" :key="b.name" class="py-1.5 pr-3 text-right font-mono"
                    :class="o.wof >= b.level ? 'text-[var(--positive)]' : 'text-[var(--negative)]'">
                  {{ fmtSigned((o.wof / b.level - 1) * 100) }}
                </td>
                <td class="py-1.5 pr-3">
                  <span class="badge" :class="statusCls(o.status)">{{ o.status }}</span>
                </td>
                <td class="py-1.5 font-mono text-[11px]">
                  <span v-for="f in o.flows" :key="f.lbl" class="mr-2">
                    {{ f.lbl }} : <strong>{{ pf(f.v) }}</strong>
                  </span>
                  <span v-if="!o.flows.length" class="text-slate-400">—</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <!-- Décomposition du MTF -->
        <div class="card !p-4 overflow-x-auto">
          <div class="text-xs font-bold text-slate-500 uppercase tracking-wide mb-2">
            Détail du calcul du Mark-to-Future
            <HelpTip text="Chaque ligne est un flux du script, tel qu'il se comporte sur les chemins internes partant de ce scénario. Probabilité = part des chemins où il se déclenche ; E[montant] = espérance sur TOUS les chemins (donc déjà pondérée par la probabilité) ; VA = E[montant] × facteur d'actualisation. La somme des VA est le mark." />
          </div>
          <div v-if="!sc.alive" class="text-xs text-amber-600 py-2">
            Contrat éteint à cette date : plus aucun flux futur, le mark est nul par construction.
          </div>
          <table v-else class="w-full text-xs border-collapse">
            <thead>
              <tr class="border-b border-[var(--border)] text-slate-500">
                <th class="text-left py-1.5 pr-3 font-semibold">Date</th>
                <th class="text-left py-1.5 pr-3 font-semibold">Flux</th>
                <th class="text-right py-1.5 pr-3 font-semibold">Probabilité</th>
                <th class="text-right py-1.5 pr-3 font-semibold whitespace-nowrap">Montant si déclenché</th>
                <th class="text-right py-1.5 pr-3 font-semibold">E[montant]</th>
                <th class="text-right py-1.5 pr-3 font-semibold">DF</th>
                <th class="text-right py-1.5 font-semibold">Valeur actuelle</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(f, i) in sc.future_flows" :key="i" class="border-b border-[var(--border)]/40">
                <td class="py-1.5 pr-3 font-mono whitespace-nowrap">
                  {{ fmtY(f.t_abs) }}<span class="text-slate-400 text-[10px] ml-1">(+{{ fmtY(f.t) }})</span>
                </td>
                <td class="py-1.5 pr-3">{{ f.lbl }}</td>
                <td class="py-1.5 pr-3 text-right font-mono">{{ formatPercent(f.proba, 1) }}</td>
                <td class="py-1.5 pr-3 text-right font-mono text-slate-500">{{ pf(f.amount_if_fires) }}</td>
                <td class="py-1.5 pr-3 text-right font-mono">{{ pf(f.e_amount) }}</td>
                <td class="py-1.5 pr-3 text-right font-mono text-slate-500">{{ formatNumber(f.df, 6) }}</td>
                <td class="py-1.5 text-right font-mono font-semibold">{{ pf(f.pv) }}</td>
              </tr>
              <tr class="border-t-2 border-[var(--border2)] font-bold">
                <td class="py-2 pr-3" colspan="6">Total — Mark-to-Future</td>
                <td class="py-2 text-right font-mono text-[var(--accent)]">{{ pf(sc.sum_pv) }}</td>
              </tr>
              <tr v-if="Math.abs(sc.pv_residual) > 1e-6">
                <td class="py-1 pr-3 text-[11px] text-amber-600" colspan="6">
                  Écart de reconstitution (somme des VA − mark)
                </td>
                <td class="py-1 text-right font-mono text-[11px] text-amber-600">{{ sc.pv_residual.toExponential(2) }}</td>
              </tr>
            </tbody>
          </table>
        </div>

        <!-- Coupons déjà acquis -->
        <div v-if="sc.realized_flows.length" class="card !p-4 overflow-x-auto">
          <div class="text-xs font-bold text-slate-500 uppercase tracking-wide mb-2">
            Flux déjà encaissés avant la date de valorisation
            <HelpTip text="Ces montants sont sortis du produit : ils ne font plus partie du mark. Ils sont rappelés ici parce que le rendement d'une position les inclut, alors que sa valeur résiduelle ne les inclut pas." />
          </div>
          <table class="w-full text-xs border-collapse">
            <thead>
              <tr class="border-b border-[var(--border)] text-slate-500">
                <th class="text-left py-1.5 pr-3 font-semibold">Date</th>
                <th class="text-right py-1.5 pr-3 font-semibold">Montant</th>
                <th class="text-right py-1.5 font-semibold">Valeur en {{ fmtY(drill.t) }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(f, i) in sc.realized_flows" :key="i" class="border-b border-[var(--border)]/40">
                <td class="py-1.5 pr-3 font-mono">{{ fmtY(f.t) }}</td>
                <td class="py-1.5 pr-3 text-right font-mono">{{ pf(f.v) }}</td>
                <td class="py-1.5 text-right font-mono text-slate-500">{{ pf(f.pv_t0) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </template>
    </template>
  </BaseModal>
</template>

<script setup>
import { ref, computed, watch, nextTick, onUnmounted } from 'vue'
import BaseModal from './ui/BaseModal.vue'
import HelpTip from './HelpTip.vue'
import AlertMessage from './ui/AlertMessage.vue'
import { useDemoModeStore } from '../stores/demoMode.js'
import { demoChartOptions } from '../composables/useSensitiveChart.js'
import { applyChartTheme, axisTick, chartTheme } from '../charts/theme.js'
import { formatPercent, formatNumber } from '../utils/format.js'
import {
  Chart, LineElement, LineController, PointElement,
  CategoryScale, LinearScale, Filler, Tooltip, Legend,
} from 'chart.js'

Chart.register(LineElement, LineController, PointElement, CategoryScale, LinearScale, Filler, Tooltip, Legend)
applyChartTheme(Chart)

const props = defineProps({
  modelValue: { type: Boolean, required: true },
  drill: { type: Object, default: null },
  // Libellé de quantile sur lequel ouvrir (le point du graphe qui a été
  // cliqué). Les onglets restent dans l'ordre naturel de la distribution.
  focus: { type: String, default: null },
  loading: { type: Boolean, default: false },
  errorMsg: { type: String, default: null },
})
defineEmits(['update:modelValue'])

const demo = useDemoModeStore()
const activeIdx = ref(0)
const pathCanvas = ref(null)
let pathChart = null

const ASSET_COLORS = ['rgba(120,120,120,.75)', 'rgba(160,110,60,.75)',
  'rgba(90,140,120,.75)', 'rgba(140,100,150,.75)', 'rgba(110,130,170,.75)']

const sc = computed(() => props.drill?.scenarios?.[activeIdx.value] || null)

const pf = v => (v === null || v === undefined) ? '—' : formatPercent(v, 2)
const fmtY = v => (v === null || v === undefined) ? '—' : `${formatNumber(v, 2)}Y`
const fmtSigned = v => (v >= 0 ? '+' : '') + formatPercent(v, 1)
const fmtLvl = b => b.is_pct ? formatPercent(b.level * 100, 1) : formatNumber(b.level, 4)

function statusCls(s) {
  if (s === 'rappelé') return 'badge-positive'
  if (s === 'maturité') return 'badge-gold'
  if (s === 'éteint') return 'badge-muted'
  return 'badge-accent'
}

const headline = computed(() => {
  if (!sc.value || !props.drill) return []
  const s = sc.value
  const tiles = [
    { label: 'Simulation n°', val: `#${s.id}` },
    { label: `Worst-of à ${fmtY(props.drill.t)}`, val: pf(s.wof_t0 * 100) },
    { label: 'Statut', val: s.alive ? 'Vivant' : 'Éteint',
      cls: s.alive ? 'text-[var(--positive)]' : 'text-[var(--muted)]' },
    { label: 'MTF', val: pf(s.mtf), cls: 'text-[var(--accent)]' },
  ]
  if (s.alive) {
    tiles.push({
      label: 'P(rappel restante)', val: formatPercent(s.recall_proba, 1),
      tip: 'Part des chemins internes partant de ce scénario où le produit est rappelé avant maturité. C\'est une probabilité conditionnelle à l\'état atteint par cette trajectoire, pas la probabilité de rappel du produit.',
    })
    tiles.push({
      label: 'Vie espérée', val: fmtY(s.expected_life),
      tip: 'Date moyenne de sortie (rappel ou maturité) sur les chemins internes de ce scénario, en années depuis aujourd\'hui.',
    })
  }
  return tiles
})

function renderPath() {
  if (pathChart) { pathChart.destroy(); pathChart = null }
  if (!props.modelValue || !sc.value || !pathCanvas.value) return
  const s = sc.value
  const d = props.drill
  const markIdx = d.step_k

  // Les barrières sont des lignes horizontales constantes : elles se lisent
  // contre la même échelle que le worst-of, donc en % du niveau initial.
  const barrierSets = (d.barriers || []).map((b, i) => ({
    label: `${b.name} (${fmtLvl(b)})`,
    data: s.path.t.map(() => b.level * 100),
    borderColor: i === 0 ? 'rgba(192,57,43,.55)' : 'rgba(217,119,6,.55)',
    borderWidth: 1, borderDash: [6, 4], pointRadius: 0, fill: false,
  }))

  // Sur un panier, le worst-of ne suffit pas à raconter la trajectoire : il
  // change de composant en cours de route. Chaque sous-jacent est tracé en
  // trait fin, le worst-of restant la courbe qui porte le payoff.
  const assetSets = d.n_assets > 1 ? s.path.assets.map((serie, a) => ({
    label: d.asset_names[a],
    data: serie.map(v => v * 100),
    borderColor: ASSET_COLORS[a % ASSET_COLORS.length],
    borderWidth: 1, pointRadius: 0, fill: false, cubicInterpolationMode: 'monotone',
  })) : []

  pathChart = new Chart(pathCanvas.value, {
    type: 'line',
    data: {
      labels: s.path.t.map(t => formatNumber(t, 2)),
      datasets: [
        {
          label: d.n_assets > 1 ? 'Worst-of' : d.asset_names[0],
          data: s.path.wof.map(v => v * 100),
          borderColor: chartTheme.primary, borderWidth: 2, pointRadius: 0,
          fill: false, cubicInterpolationMode: 'monotone',
        },
        // Marqueur de la date de valorisation : un point unique sur la courbe.
        {
          label: `Date de valorisation ${fmtY(d.t)}`,
          data: s.path.wof.map((v, i) => (i === markIdx ? v * 100 : null)),
          borderColor: chartTheme.gold, backgroundColor: chartTheme.gold,
          pointRadius: 6, pointStyle: 'rectRot', showLine: false,
        },
        ...assetSets,
        ...barrierSets,
      ],
    },
    options: demoChartOptions({
      responsive: true, maintainAspectRatio: false, animation: { duration: 200 },
      plugins: {
        legend: { position: 'bottom', labels: { font: { size: 10 }, boxWidth: 12, usePointStyle: true } },
        tooltip: {
          mode: 'index', intersect: false,
          callbacks: {
            title: it => `t = ${it[0].label}Y`,
            label: it => it.raw == null ? null : `${it.dataset.label} : ${formatPercent(it.raw, 2)}`,
          },
        },
      },
      scales: {
        x: { ticks: { font: { size: 9 }, maxTicksLimit: 12 } },
        y: { ticks: { font: { size: 9 }, callback: axisTick('%') } },
      },
    }, demo.enabled),
  })
}

watch([() => props.drill, activeIdx, () => props.modelValue, () => demo.enabled], async () => {
  await nextTick()
  renderPath()
})
watch(() => props.drill, (d) => {
  // Le libellé peut cumuler deux quantiles tombés sur la même trajectoire
  // (« P25 / P50 » sur un petit échantillon) — d'où la recherche par inclusion.
  const i = props.focus
    ? (d?.scenarios || []).findIndex(s => (s.label || '').split(' / ').includes(props.focus))
    : -1
  activeIdx.value = i >= 0 ? i : 0
})
onUnmounted(() => { if (pathChart) pathChart.destroy() })
</script>
