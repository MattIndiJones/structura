<template>
  <div class="flex flex-col gap-4">
    <!-- Header + controls -->
    <div class="card">
      <div class="flex items-center gap-3 flex-wrap mb-3">
        <div class="text-xs font-bold text-slate-400 uppercase tracking-wider">🗺️ Mark to Future</div>
        <div class="ml-auto">
          <button class="btn-primary text-xs px-4" :disabled="store.loading || !store.result" @click="launch">
            <span v-if="store.loading" class="w-3 h-3 border border-white border-t-transparent rounded-full animate-spin inline-block mr-1"></span>
            ▶ Lancer
          </button>
        </div>
      </div>

      <div class="text-xs text-slate-400 leading-relaxed bg-slate-800/50 border-l-2 border-blue-500 rounded-lg px-3 py-2 mb-4">
        <strong class="text-slate-200">Nested Monte Carlo risque-neutre.</strong>
        Pour chaque date MTM, N<sub>outer</sub> scénarios de marché sont simulés (GBM, paramètres gelés à
        aujourd'hui), puis le produit résiduel est re-pricé sous le modèle choisi avec N<sub>inner</sub> chemins.
        Résultat : la <em>distribution future des valeurs mark-to-model</em> du produit — pas une prévision
        économique.
      </div>

      <div class="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs mb-2">
        <div>
          <label class="label">N outer
            <HelpTip text="Nombre de scénarios de marché futurs simulés à chaque date MTM — c'est ce qui construit la distribution (P05/P95 etc). Plus il est élevé, moins la distribution est bruitée, mais chaque scénario supplémentaire déclenche N inner re-pricings : le coût total grossit linéairement avec N outer." />
          </label>
          <SensitiveValue mode="input"><input v-model.number="form.n_outer" type="number" step="50" min="20" max="2000" class="input" /></SensitiveValue>
        </div>
        <div>
          <label class="label">N inner
            <HelpTip text="Nombre de chemins Monte Carlo utilisés pour re-pricer le produit résiduel à l'intérieur de chaque scénario outer. Augmenter N inner réduit le bruit de pricing sur chaque point de la distribution, mais ne change pas le nombre de scénarios — c'est un raffinement de précision par scénario, pas un élargissement de l'échantillon." />
          </label>
          <SensitiveValue mode="input"><input v-model.number="form.n_inner" type="number" step="100" min="50" max="5000" class="input" /></SensitiveValue>
        </div>
        <div>
          <label class="label">Dates MTM
            <HelpTip text="Nombre de dates futures auxquelles la distribution de valeur mark-to-model est calculée, réparties entre aujourd'hui et la maturité (ou le premier rappel possible). Chaque date ajoutée multiplie le coût total par N outer × N inner re-pricings supplémentaires." />
          </label>
          <SensitiveValue mode="input"><input v-model.number="form.n_dates" type="number" step="1" min="2" max="12" class="input" /></SensitiveValue>
        </div>
        <div>
          <label class="label">Seed
            <HelpTip text="Graine du générateur aléatoire pour les scénarios outer. Fixe le résultat pour permettre la reproductibilité — changer la seed déplace le bruit d'échantillonnage mais pas la distribution théorique sous-jacente." />
          </label>
          <SensitiveValue mode="input"><input v-model.number="form.seed" type="number" class="input" /></SensitiveValue>
        </div>
      </div>
      <div class="text-xs text-slate-600">
        <SensitiveValue>
          Coût ≈ N<sub>outer</sub> × N<sub>dates</sub> × N<sub>inner</sub> évaluations de pricer
          ({{ formatInt(form.n_outer * form.n_dates * form.n_inner) }} au total).
        </SensitiveValue>
      </div>
      <div v-if="!store.result" class="text-xs text-amber-500 mt-2">
        Lancez d'abord un pricing (▶ Pricer) pour fixer le prix de référence P₀.
      </div>
    </div>

    <!-- Empty state -->
    <div v-if="!store.mtf" class="flex flex-col items-center justify-center h-52 text-slate-600 gap-2">
      <div class="text-3xl">🗺️</div>
      <div class="text-sm font-medium">Configurez les paramètres et lancez le Mark to Future</div>
      <div class="text-xs">Distribution des valeurs futures du produit sous mesure risque-neutre</div>
    </div>

    <template v-else>
      <!-- Fan chart -->
      <div class="card">
        <div class="text-xs font-bold text-slate-500 uppercase tracking-wide mb-3">
          Distribution future du prix (% notionnel) — bandes P05/P95 et P25/P75
        </div>
        <SensitiveChart>
          <div style="height:280px;position:relative;">
            <canvas ref="fanCanvas"></canvas>
          </div>
        </SensitiveChart>
      </div>

      <!-- Scalar sanity tiles + conditional expectations, on one date -->
      <div class="card">
        <div class="flex items-center gap-3 flex-wrap mb-3">
          <div class="text-xs font-bold text-slate-500 uppercase tracking-wide">
            Indicateurs à la date
          </div>
          <select v-model.number="tileDateIdx" class="select !w-auto text-xs !py-1">
            <option v-for="(r, i) in plottableRows" :key="r.t" :value="i">
              {{ formatNumber(r.t, 2) }}Y — {{ r.n_alive }} vivants
            </option>
          </select>
          <div class="text-[11px] text-slate-500">
            Toutes conditionnelles à la survie du contrat à cette date.
          </div>
          <button v-if="tileRow" class="btn-secondary text-xs ml-auto" @click="openQuantiles(tileRow)">
            🔍 Analyser les trajectoires
          </button>
        </div>

        <div v-if="!tileRow" class="text-xs text-amber-500 py-3">
          Aucune date avec un effectif suffisant.
        </div>
        <template v-else>
          <div class="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-3">
            <div v-for="s in scalarTiles" :key="s.label" class="stat-box">
              <div class="text-xs text-slate-500 mb-1">{{ s.label }}
                <HelpTip v-if="s.tip" :text="s.tip" />
              </div>
              <div class="text-lg font-bold" :class="s.cls"><SensitiveValue>{{ s.val }}</SensitiveValue></div>
            </div>
          </div>

          <div class="text-xs font-bold text-slate-500 uppercase tracking-wide mb-2 pt-1">
            Décomposition gagnants / perdants
            <HelpTip text="Le seuil est 100 % du nominal — « le produit vaut-il plus que le pair », indépendamment du prix payé. Ces espérances sont CONDITIONNELLES au signe du résultat : E(MTM | MTM>100) ne moyenne que les scénarios gagnants. À ne pas confondre avec E(max(MTM-100,0)) ci-dessus, qui moyenne sur tout l'échantillon en comptant les perdants comme des zéros — l'une dit « quand ça marche, ça vaut combien », l'autre « combien de potentiel ce produit porte en moyenne »." />
          </div>
          <div class="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div v-for="s in conditionalTiles" :key="s.label" class="stat-box">
              <div class="text-xs text-slate-500 mb-1">{{ s.label }}
                <HelpTip v-if="s.tip" :text="s.tip" />
              </div>
              <div class="text-lg font-bold" :class="s.cls"><SensitiveValue>{{ s.val }}</SensitiveValue></div>
              <div v-if="s.sub" class="text-[11px] text-slate-500 mt-0.5">
                <SensitiveValue>{{ s.sub }}</SensitiveValue>
              </div>
            </div>
          </div>
        </template>
      </div>

      <!-- Histogramme de la distribution -->
      <div v-if="tileRow" class="card">
        <div class="flex items-center gap-3 flex-wrap mb-3">
          <div class="text-xs font-bold text-slate-500 uppercase tracking-wide">
            Distribution du MTM à {{ formatNumber(tileRow.t, 2) }}Y
          </div>
          <div class="text-[11px] text-slate-500">
            {{ tileRow.n_alive }} scénarios vivants · repères P05/P25/P50/P75/P95, moyenne et pair
          </div>
          <div class="ml-auto flex items-center gap-2 text-[11px] text-slate-500">
            <span>Classes</span>
            <input v-model.number="histBins" type="number" min="10" max="80" step="5"
                   class="input !w-16 !py-1 text-xs" />
          </div>
        </div>
        <SensitiveChart>
          <div style="height:250px;position:relative;"><canvas ref="histCanvas"></canvas></div>
        </SensitiveChart>
        <div class="text-[11px] text-slate-500 mt-2">
          Cliquez une barre pour ouvrir les trajectoires qui la composent.
        </div>
      </div>

      <!-- Stats table -->
      <div class="card overflow-x-auto">
        <div class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3">Statistiques par date MTM</div>
        <table class="w-full text-xs border-collapse">
          <thead>
            <tr class="border-b border-slate-700 text-slate-500">
              <th class="text-left py-1.5 pr-3 font-semibold">Date</th>
              <th class="text-right py-1.5 pr-3 font-semibold">E(MTM)
                <HelpTip text="Valeur résiduelle moyenne du contrat, SACHANT qu'il n'a pas été rappelé à cette date. Espérance conditionnelle : elle ne décrit pas la valeur moyenne d'une position, mais celle des produits encore en vie." /></th>
              <th class="text-right py-1.5 pr-3 font-semibold">σ
                <HelpTip text="Dispersion des valeurs résiduelles entre les scénarios encore vivants à cette date." /></th>
              <th class="text-right py-1.5 pr-3 font-semibold whitespace-nowrap">Rappelés
                <HelpTip text="Part des scénarios où le produit a déjà été remboursé par anticipation à cette date. Ces scénarios SORTENT de l'échantillon : ils ne sont ni marqués à zéro, ni affichés à leur valeur de remboursement. Toutes les statistiques de la ligne sont donc conditionnelles à la survie, et portent sur une population qui se réduit et se dégrade au fil des dates — les scénarios qui survivent sont ceux où le sous-jacent est resté bas. Une part de la baisse observée vient de cette sélection, pas du marché." /></th>
              <th class="text-right py-1.5 pr-3 font-semibold whitespace-nowrap">Vivants
                <HelpTip text="Nombre de scénarios encore en vie sur lesquels la ligne est calculée. En dessous de 50, aucun percentile n'est publié : un P05 lu sur une poignée de trajectoires est du bruit déguisé en mesure de risque." /></th>
              <th class="text-right py-1.5 pr-3 font-semibold">P05</th>
              <th class="text-right py-1.5 pr-3 font-semibold">P25</th>
              <th class="text-right py-1.5 pr-3 font-semibold">P50</th>
              <th class="text-right py-1.5 pr-3 font-semibold">P75</th>
              <th class="text-right py-1.5 pr-3 font-semibold">P95</th>
              <th class="text-right py-1.5 pr-3 font-semibold whitespace-nowrap">P(&gt;100%)
                <HelpTip align="right" text="Probabilité que le produit vaille plus que 100% du notionnel à cette date — indicateur brut de gain, indépendant du prix réellement payé à l'achat." /></th>
              <th class="text-right py-1.5 font-semibold whitespace-nowrap">P(&ge;P&#8320;)
                <HelpTip align="right" text="Probabilité que la valeur mark-to-model dépasse le prix d'entrée P₀ (le prix de pricing initial, pas 100%) — répond à 'ai-je une majorité de chances d'être gagnant par rapport à ce que j'ai payé', ce qui diffère de P(>100%) si le produit a été acheté au-dessus ou en-dessous du pair." /></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in store.mtf.results" :key="r.t" class="border-b border-slate-800/50">
              <td class="py-1.5 pr-3 text-slate-300 font-semibold whitespace-nowrap">{{ formatNumber(r.t, 2) }}Y</td>
              <template v-if="r.stats && !r.thin">
                <td class="py-1.5 pr-3 text-right font-mono text-blue-400"><SensitiveValue>{{ pf(r.stats.mean) }}</SensitiveValue></td>
                <td class="py-1.5 pr-3 text-right font-mono text-slate-400"><SensitiveValue>{{ pf(r.stats.std) }}</SensitiveValue></td>
              </template>
              <td v-else colspan="2" class="py-1.5 pr-3 text-right font-mono text-slate-600">—</td>
              <td class="py-1.5 pr-3 text-right font-mono"
                  :class="r.terminated_pct > 0 ? 'text-amber-400' : 'text-slate-600'">
                {{ formatPercent(r.terminated_pct ?? 0, 1) }}
              </td>
              <td class="py-1.5 pr-3 text-right font-mono"
                  :class="(r.stats && !r.thin) ? 'text-slate-400' : 'text-amber-500'">
                {{ r.n_alive ?? '—' }}
              </td>
              <template v-if="r.stats && !r.thin">
                <!-- Chaque cellule de quantile ouvre la trajectoire qui le porte. -->
                <td v-for="q in QUANTILE_CELLS" :key="q.key"
                    class="py-1.5 pr-3 text-right font-mono cursor-pointer hover:underline"
                    :class="q.cls"
                    :title="`Analyser la trajectoire ${q.label} de cette date`"
                    @click="openQuantiles(r, q.label)">
                  <SensitiveValue>{{ pf(r.stats[q.key]) }}</SensitiveValue>
                </td>
                <td class="py-1.5 pr-3 text-right font-mono"
                    :class="r.stats.p_above_100 >= 50 ? 'text-green-400' : 'text-red-400'">
                  <SensitiveValue>{{ formatPercent(r.stats.p_above_100, 1) }}</SensitiveValue>
                </td>
                <td class="py-1.5 text-right font-mono"
                    :class="r.stats.p_above_p0 >= 50 ? 'text-green-400' : 'text-red-400'">
                  <SensitiveValue>{{ formatPercent(r.stats.p_above_p0, 1) }}</SensitiveValue>
                </td>
              </template>
              <!-- Trop peu de survivants : rien plutôt qu'un percentile de bruit. -->
              <td v-else colspan="7" class="py-1.5 text-center text-[11px] text-amber-500/80 italic">
                effectif insuffisant — aucun percentile publié
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- CSV export -->
      <div class="flex gap-2">
        <button class="btn-secondary text-xs" @click="exportCsv('summary')">⬇ Summary CSV</button>
        <button class="btn-secondary text-xs" @click="exportCsv('runs')">⬇ Runs CSV</button>
      </div>
    </template>

    <MtfDrilldownModal v-model="drillOpen" :drill="store.mtfDrill" :focus="drillFocus"
                       :loading="store.mtfDrillLoading" :error-msg="store.mtfDrillError" />
  </div>
</template>

<script setup>
import { ref, computed, watch, nextTick, onMounted, onUnmounted } from 'vue'
import { usePricingStore } from '../stores/pricing.js'
import { useDemoModeStore } from '../stores/demoMode.js'
import { demoChartOptions } from '../composables/useSensitiveChart.js'
import { chartTheme, applyChartTheme } from '../charts/theme.js'
import SensitiveValue from './SensitiveValue.vue'
import SensitiveChart from './SensitiveChart.vue'
import HelpTip from './HelpTip.vue'
import MtfDrilldownModal from './MtfDrilldownModal.vue'
import { formatPercent, formatNumber, formatInt } from '../utils/format.js'
import {
  Chart, LineElement, LineController, PointElement, BarElement, BarController,
  CategoryScale, LinearScale, Filler, Tooltip, Legend,
} from 'chart.js'

Chart.register(LineElement, LineController, PointElement, BarElement, BarController,
  CategoryScale, LinearScale, Filler, Tooltip, Legend)
applyChartTheme(Chart)

const store = usePricingStore()
const demo = useDemoModeStore()
const fanCanvas = ref(null)
const histCanvas = ref(null)
let fanChart = null
let histChart = null

const form = ref({ n_outer: 200, n_inner: 500, n_dates: 5, seed: 42 })
const drillOpen = ref(false)
const drillFocus = ref(null)
const tileDateIdx = ref(0)
const histBins = ref(30)

const QUANTILE_CELLS = [
  { key: 'p05', label: 'P05', cls: 'text-red-400' },
  { key: 'p25', label: 'P25', cls: 'text-slate-300' },
  { key: 'p50', label: 'P50', cls: 'text-slate-200 font-semibold' },
  { key: 'p75', label: 'P75', cls: 'text-slate-300' },
  { key: 'p95', label: 'P95', cls: 'text-green-400' },
]
const QUANTILE_LEVELS = { P05: 0.05, P25: 0.25, P50: 0.50, P75: 0.75, P95: 0.95 }

function launch() {
  store.runMtf({ ...form.value })
}

const pf = v => (v === null || v === undefined) ? '—' : formatPercent(v, 2)

// ── Sélection de trajectoires ──────────────────────────────────────
// Le rang d'un scénario se lit côté client : `pvs` et `alive` sont déjà là, et
// les faire re-classer par le backend l'obligerait à recalculer tout l'éventail
// pour en expliquer cinq lignes. Le tri porte sur les VIVANTS uniquement —
// c'est l'univers sur lequel les quantiles publiés sont calculés, un scénario
// éteint n'a pas de rang dans cette distribution.
function aliveSortedIds(row) {
  const ids = []
  row.pvs.forEach((v, i) => { if (row.alive?.[i]) ids.push(i) })
  ids.sort((a, b) => row.pvs[a] - row.pvs[b])
  return ids
}

function idAtQuantile(row, p) {
  const ids = aliveSortedIds(row)
  if (!ids.length) return null
  return ids[Math.min(ids.length - 1, Math.max(0, Math.round(p * (ids.length - 1))))]
}

// Les onglets gardent toujours l'ordre naturel P05→P95 : c'est une
// distribution, la lire dans le désordre n'aide personne. `focus` ne décide
// que de l'onglet ouvert en arrivant.
function openQuantiles(row, focus = null) {
  const ids = []
  const labels = []
  for (const lb of Object.keys(QUANTILE_LEVELS)) {
    const id = idAtQuantile(row, QUANTILE_LEVELS[lb])
    // Sur un échantillon réduit, deux quantiles peuvent désigner la même
    // trajectoire : on ne la rejoue pas deux fois, on cumule les libellés.
    if (id === null) continue
    const seen = ids.indexOf(id)
    if (seen >= 0) { labels[seen] += ` / ${lb}`; continue }
    ids.push(id); labels.push(lb)
  }
  if (!ids.length) return
  drillFocus.value = focus
  drillOpen.value = true
  store.runMtfDrilldown({ t: row.t, ids, labels })
}

function openScenarios(row, ids, labels) {
  if (!ids.length) return
  drillFocus.value = null
  drillOpen.value = true
  store.runMtfDrilldown({ t: row.t, ids: ids.slice(0, 12), labels })
}

// Sanity-check tiles for the furthest MTM date — the 4 diagnostics a quant would
// check first: tail risk above par, probability of beating the entry price, and
// the two expectation-based metrics (should track the forward price under
// no-arbitrage).
// Toutes ces mesures sont CONDITIONNELLES à la survie du produit : les
// trajectoires rappelées ne font plus partie de l'échantillon. Les libellés le
// disent, sinon on relit une statistique conditionnelle comme une statistique
// de portefeuille — c'est précisément l'erreur que la version précédente
// induisait en marquant les produits morts à zéro.
// Dates publiables (effectif suffisant) — la sélection des tuiles, de
// l'histogramme et du drill-down porte sur celles-là.
const plottableRows = computed(() =>
  (store.mtf?.results || []).filter(r => r.stats && !r.thin))

const tileRow = computed(() => plottableRows.value[tileDateIdx.value] || null)

const scalarTiles = computed(() => {
  const row = tileRow.value
  if (!row) return []
  const s = row.stats
  const surv = `Sur les ${row.n_alive ?? '?'} scénario(s) encore vivant(s) à cette date.`
  return [
    { label: 'P(MTM>100%)', val: formatPercent(s.p_above_100, 1),
      cls: s.p_above_100 >= 50 ? 'text-green-400' : 'text-red-400',
      tip: `Probabilité que le produit vaille plus que 100% du notionnel, sachant qu'il n'a pas été rappelé. ${surv}` },
    { label: 'P(MTM≥P₀)', val: formatPercent(s.p_above_p0, 1),
      cls: s.p_above_p0 >= 50 ? 'text-green-400' : 'text-red-400',
      tip: `Probabilité que la valeur résiduelle dépasse le prix d'entrée P₀, sachant le produit encore vivant. ${surv}` },
    { label: 'E(MTM)', val: pf(s.e_mtm), cls: 'text-blue-400',
      tip: `Valeur résiduelle moyenne sachant le produit encore vivant — une espérance conditionnelle, pas la valeur moyenne d'une position. ${surv}` },
    { label: 'E(max(MTM-100,0))', val: pf(s.e_upside), cls: 'text-green-400',
      tip: `Espérance du seul potentiel au-dessus de 100%, sachant le produit encore vivant. Moyenne sur TOUT l'échantillon, les perdants comptant pour zéro — à distinguer du gain moyen des gagnants ci-dessous. ${surv}` },
  ]
})

const conditionalTiles = computed(() => {
  const row = tileRow.value
  if (!row) return []
  const s = row.stats
  const n = row.n_alive || 1
  const share = c => `${formatPercent(c / n * 100, 1)} des vivants`
  return [
    { label: 'E(MTM | MTM > 100%)', val: pf(s.e_mtm_win), cls: 'text-green-400',
      sub: `${s.n_win} scénario(s) — ${share(s.n_win)}`,
      tip: "Valeur moyenne du produit sur les seuls scénarios où il vaut plus que le pair. Espérance conditionnelle : elle ne dit rien de la probabilité d'y être — c'est P(MTM>100%) qui la porte." },
    { label: 'E(MTM | MTM < 100%)', val: pf(s.e_mtm_lose), cls: 'text-red-400',
      sub: `${s.n_lose} scénario(s) — ${share(s.n_lose)}`,
      tip: "Valeur moyenne du produit sur les seuls scénarios où il vaut moins que le pair. Lue avec le nombre de scénarios concernés, c'est la sévérité d'un mauvais cas, pas sa fréquence." },
    { label: 'Gain moyen des gagnants', val: pf(s.avg_gain), cls: 'text-green-400',
      sub: s.max_gain === null ? null : `Gain maximal : ${pf(s.max_gain)}`,
      tip: "Moyenne de (MTM − 100%) sur les seuls scénarios gagnants. C'est le pendant conditionnel de E(max(MTM-100,0)) : celle-ci divise par tout l'échantillon, celle-là par les seuls gagnants." },
    { label: 'Perte moyenne des perdants', val: pf(s.avg_loss), cls: 'text-red-400',
      sub: s.max_loss === null ? null : `Perte maximale : ${pf(s.max_loss)}`,
      tip: "Moyenne de (100% − MTM) sur les seuls scénarios perdants, en magnitude positive. Multipliée par P(MTM<100%), elle donne la perte espérée sur l'ensemble." },
  ]
})

function renderChart() {
  if (!store.mtf || !fanCanvas.value) return
  if (fanChart) { fanChart.destroy(); fanChart = null }

  const p0 = store.mtf.main_price ?? 100
  const results = store.mtf.results
  const labels = ['t₀', ...results.map(r => r.t.toFixed(2).replace('.', ',') + 'Y')]
  // null pour une date sans effectif suffisant : Chart.js interrompt la ligne
  // plutôt que de la tirer vers une valeur inventée.
  const mk = key => [p0, ...results.map(r => (r.stats && !r.thin ? r.stats[key] : null))]

  // Dataset order matters for fill:'-1' (fills toward the previous dataset).
  // `cubicInterpolationMode: 'monotone'` on every series, and NOT `tension`:
  // free cubic smoothing overshoots between points, independently per curve.
  // On a quantile fan that draws bands the engine never computed — a P25 arc
  // bulging above the médiane, a P05 dipping below P01 — in the one chart whose
  // whole job is to show an ordered distribution. Monotone interpolation cannot
  // overshoot, so the drawn order is the computed order.
  const line = { fill: false, pointRadius: 0, cubicInterpolationMode: 'monotone' }
  fanChart = new Chart(fanCanvas.value, {
    type: 'line',
    data: {
      labels,
      datasets: [
        { ...line, label: 'P95', data: mk('p95'), borderColor: 'rgba(37,99,235,.25)', borderWidth: 1, borderDash: [3, 3] },
        { ...line, label: 'P05', data: mk('p05'), fill: '-1', backgroundColor: 'rgba(37,99,235,.08)', borderColor: 'rgba(37,99,235,.25)', borderWidth: 1, borderDash: [3, 3] },
        { ...line, label: 'P75', data: mk('p75'), borderColor: 'rgba(37,99,235,.5)', borderWidth: 1.5 },
        { ...line, label: 'P25', data: mk('p25'), fill: '-1', backgroundColor: 'rgba(37,99,235,.16)', borderColor: 'rgba(37,99,235,.5)', borderWidth: 1.5 },
        { ...line, label: 'Médiane', data: mk('p50'), borderColor: chartTheme.primary, borderWidth: 2.5, pointRadius: 3, pointBackgroundColor: chartTheme.primary },
        { ...line, label: 'Moyenne', data: mk('mean'), borderColor: chartTheme.gold, borderWidth: 1.5, borderDash: [5, 3] },
        { ...line, label: 'P99', data: mk('p99'), borderColor: 'rgba(192,57,43,.35)', borderWidth: 1, borderDash: [2, 4] },
        { ...line, label: 'P01', data: mk('p01'), borderColor: 'rgba(192,57,43,.35)', borderWidth: 1, borderDash: [2, 4] },
      ],
    },
    options: demoChartOptions({
      responsive: true, maintainAspectRatio: false,
      // Le point cliqué porte une date ET un quantile : on ouvre exactement la
      // trajectoire qui tient ce point du graphe, pas un scénario « proche ».
      onClick: (evt, els, chart) => {
        const hit = chart.getElementsAtEventForMode(evt, 'nearest', { intersect: false }, true)[0]
        if (!hit || hit.index === 0) return          // index 0 = l'ancrage t₀
        const row = results[hit.index - 1]
        if (!row?.stats || row.thin) return
        // La courbe médiane porte le libellé « Médiane », pas « P50 » —
        // cliquer dessus doit quand même ouvrir la trajectoire médiane.
        const raw = chart.data.datasets[hit.datasetIndex]?.label
        const key = raw === 'Médiane' ? 'P50' : raw
        openQuantiles(row, QUANTILE_LEVELS[key] !== undefined ? key : null)
      },
      onHover: (evt, els) => {
        evt.native.target.style.cursor = els.length ? 'pointer' : 'default'
      },
      plugins: {
        legend: { position: 'bottom', labels: { font: { size: 10 }, boxWidth: 12 } },
        tooltip: {
          mode: 'index', intersect: false,
          callbacks: { label: it => `${it.dataset.label}: ${it.raw?.toFixed?.(2)?.replace('.', ',')}%` },
        },
      },
      scales: {
        x: { ticks: { font: { size: 10 } } },
        y: { ticks: { font: { size: 9 }, callback: v => v + '%' } },
      },
      animation: { duration: 250 },
    }, demo.enabled),
  })
}

// ── Histogramme de la distribution à une date ──────────────────────
// Construit sur `pvs_alive` : même univers que les percentiles publiés, donc
// les repères tombent au bon endroit. Le clic renvoie les scénarios de la
// classe, ce qui suppose de retrouver leurs indices — d'où le passage par
// `pvs` + `alive` plutôt que par `pvs_alive` seul, qui a perdu les indices.
const histData = computed(() => {
  const row = tileRow.value
  if (!row) return null
  const ids = []
  row.pvs.forEach((v, i) => { if (row.alive?.[i]) ids.push(i) })
  if (!ids.length) return null
  const vals = ids.map(i => row.pvs[i])
  const lo = Math.min(...vals), hi = Math.max(...vals)
  const nb = Math.max(5, Math.min(80, histBins.value || 30))
  // Distribution dégénérée (tous les survivants au même mark, ce qui arrive à
  // une semaine de la maturité) : une classe unique plutôt qu'une division par
  // zéro déguisée en histogramme plat.
  const width = (hi - lo) / nb || 1
  const buckets = Array.from({ length: nb }, () => [])
  vals.forEach((v, j) => {
    const b = Math.min(nb - 1, Math.max(0, Math.floor((v - lo) / width)))
    buckets[b].push(ids[j])
  })
  return {
    lo, hi, width, nb, buckets,
    counts: buckets.map(b => b.length),
    labels: buckets.map((_, i) => formatNumber(lo + (i + 0.5) * width, 1)),
  }
})

function renderHist() {
  if (histChart) { histChart.destroy(); histChart = null }
  const h = histData.value
  const row = tileRow.value
  if (!h || !row || !histCanvas.value) return
  const s = row.stats
  const p0 = store.mtf?.main_price ?? 100

  // Repères verticaux : sur un axe catégoriel, la position d'une valeur est sa
  // coordonnée fractionnaire en classes. Dessinés en plugin pour rester
  // exactement alignés sur les barres quel que soit le nombre de classes.
  const marks = [
    ...['p05', 'p25', 'p50', 'p75', 'p95'].map(k => ({
      v: s[k], lbl: k.toUpperCase().replace('P', 'P'), color: 'rgba(37,99,235,.75)', dash: [4, 3],
    })),
    { v: s.mean, lbl: 'Moy.', color: chartTheme.gold, dash: [] },
    { v: 100, lbl: 'Pair', color: 'rgba(192,57,43,.85)', dash: [] },
    { v: p0, lbl: 'P₀', color: 'rgba(26,122,74,.85)', dash: [2, 2] },
  ]
  const markerPlugin = {
    id: 'mtfHistMarkers',
    afterDatasetsDraw(chart) {
      const { ctx, chartArea: area, scales } = chart
      ctx.save()
      marks.forEach((m, i) => {
        if (m.v == null || m.v < h.lo || m.v > h.hi + h.width) return
        const frac = (m.v - h.lo) / h.width - 0.5
        const x = scales.x.getPixelForValue(Math.max(0, Math.min(h.nb - 1, frac)))
        ctx.strokeStyle = m.color; ctx.lineWidth = 1.5; ctx.setLineDash(m.dash)
        ctx.beginPath(); ctx.moveTo(x, area.top); ctx.lineTo(x, area.bottom); ctx.stroke()
        ctx.setLineDash([])
        ctx.fillStyle = m.color
        ctx.font = 'bold 9px sans-serif'
        ctx.textAlign = 'center'
        ctx.fillText(m.lbl, x, area.top + 9 + (i % 2) * 10)
      })
      ctx.restore()
    },
  }

  histChart = new Chart(histCanvas.value, {
    type: 'bar',
    data: {
      labels: h.labels,
      datasets: [{
        label: 'Scénarios',
        data: h.counts,
        backgroundColor: h.buckets.map((_, i) =>
          (h.lo + (i + 0.5) * h.width) >= 100 ? 'rgba(26,122,74,.55)' : 'rgba(192,57,43,.5)'),
        borderWidth: 0, barPercentage: 1, categoryPercentage: 1,
      }],
    },
    options: demoChartOptions({
      responsive: true, maintainAspectRatio: false, animation: { duration: 200 },
      onClick: (evt, els) => {
        if (!els.length) return
        const b = h.buckets[els[0].index]
        if (!b?.length) return
        openScenarios(row, b, b.slice(0, 12).map((id, j) => `#${id}`))
      },
      onHover: (evt, els) => {
        evt.native.target.style.cursor = els.length ? 'pointer' : 'default'
      },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            title: it => {
              const i = it[0].dataIndex
              return `[${formatNumber(h.lo + i * h.width, 2)}% ; ${formatNumber(h.lo + (i + 1) * h.width, 2)}%[`
            },
            label: it => {
              const c = it.raw
              return `${c} scénario(s) — ${formatPercent(c / row.n_alive * 100, 1)}`
            },
          },
        },
      },
      scales: {
        x: { ticks: { font: { size: 9 }, maxTicksLimit: 14, callback(v) { return this.getLabelForValue(v) + '%' } },
             grid: { display: false } },
        y: { beginAtZero: true, title: { display: true, text: 'Nombre de scénarios', font: { size: 10 } },
             ticks: { font: { size: 9 }, precision: 0 } },
      },
    }, demo.enabled),
    plugins: [markerPlugin],
  })
}

function exportCsv(type) {
  if (!store.mtf) return
  const { results } = store.mtf
  let csv, filename

  if (type === 'runs') {
    // Le statut vivant/rappelé accompagne chaque valeur : sans lui l'export
    // ne permet pas de distinguer un contrat éteint d'un contrat sans valeur.
    const lines = ['scenario,date_mtm_y,pv_pct,vivant']
    results.forEach(r => r.pvs.forEach((pv, i) => lines.push(
      `${i},${r.t.toFixed(4)},${pv.toFixed(4)},${r.alive?.[i] ? 1 : 0}`)))
    csv = lines.join('\n'); filename = 'mtf_runs.csv'
  } else {
    const cols = ['date_mtm_y', 'n_vivants', 'e_mtm', 'std', 'p01', 'p05', 'p25', 'p50',
      'p75', 'p95', 'p99', 'p_above_100pct', 'p_above_p0', 'e_upside',
      'n_gagnants', 'n_perdants', 'e_mtm_gagnants', 'e_mtm_perdants',
      'gain_moyen', 'perte_moyenne', 'gain_max', 'perte_max', 'mtm_min', 'mtm_max']
    const lines = [cols.join(',')]
    // Toutes les colonnes sont en % de nominal, sauf p_above_* déjà en fraction —
    // les deux en-têtes le disent. Une case vide vaut « pas de sous-échantillon »
    // (aucun gagnant, aucun perdant) et se distingue ainsi d'un zéro calculé.
    const fmt = v => (v === null || v === undefined) ? '' : Number(v).toFixed(4)
    results.forEach(r => {
      const s = r.stats
      if (!s) { lines.push([r.t, r.n_alive ?? 0, ...Array(cols.length - 2).fill('')].join(',')); return }
      lines.push([r.t, r.n_alive ?? 0, s.mean, s.std, s.p01, s.p05, s.p25, s.p50,
        s.p75, s.p95, s.p99, s.p_above_100 / 100, s.p_above_p0 / 100, s.e_upside,
        s.n_win, s.n_lose, s.e_mtm_win, s.e_mtm_lose,
        s.avg_gain, s.avg_loss, s.max_gain, s.max_loss, s.mtm_min, s.mtm_max]
        .map((v, i) => (i === 0 || i === 1 || i === 14 || i === 15) ? v : fmt(v)).join(','))
    })
    csv = lines.join('\n'); filename = 'mtf_summary.csv'
  }

  const a = Object.assign(document.createElement('a'), {
    href: URL.createObjectURL(new Blob([csv], { type: 'text/csv' })),
    download: filename,
  })
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
}

async function renderAll() {
  await nextTick()
  renderChart()
  renderHist()
}

// Un nouvel éventail peut avoir moins de dates publiables que le précédent :
// remettre l'index dans les bornes avant de dessiner, sinon les tuiles et
// l'histogramme visent une ligne qui n'existe plus.
watch(() => store.mtf, () => {
  tileDateIdx.value = Math.max(0, plottableRows.value.length - 1)
  renderAll()
})
watch([tileDateIdx, histBins], async () => { await nextTick(); renderHist() })
watch(() => demo.enabled, renderAll)
onMounted(renderAll)
onUnmounted(() => {
  if (fanChart) fanChart.destroy()
  if (histChart) histChart.destroy()
})
</script>
