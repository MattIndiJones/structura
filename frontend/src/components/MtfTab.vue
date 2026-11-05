<template>
  <div class="flex flex-col gap-4">
    <!-- Header + controls -->
    <div class="card">
      <div class="flex items-center gap-3 flex-wrap mb-3">
        <div class="text-xs font-bold text-slate-400 uppercase tracking-wider">🗺️ Mark to Future</div>
        <div class="ml-auto">
          <button class="btn-primary text-xs px-4" :disabled="store.loading || store.mtfLoading || !store.result || !!mtfUnavailableReason" @click="launch">
            <span v-if="store.mtfLoading" class="w-3 h-3 border border-white border-t-transparent rounded-full animate-spin inline-block mr-1"></span>
            {{ compareMode ? '▶ Comparer A et B' : '▶ Lancer' }}
          </button>
        </div>
      </div>

      <div class="text-xs text-slate-400 leading-relaxed bg-slate-800/50 border-l-2 border-blue-500 rounded-lg px-3 py-2 mb-4">
        <strong class="text-slate-200">Nested Monte Carlo risque-neutre.</strong>
        Pour chaque date MTM, N<sub>outer</sub> scénarios de marché sont simulés, puis le produit résiduel
        est revalorisé avec le même modèle et N<sub>inner</sub> chemins à partir de l’état atteint.
        Résultat : la <em>distribution future des valeurs mark-to-model</em> du produit — pas une prévision
        économique.
      </div>

      <div class="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs mb-4">
        <label class="label">Analyse
          <select v-model="compareMode" class="select" :disabled="store.mtfLoading">
            <option :value="false">Calcul simple</option>
            <option :value="true">Comparaison A/B</option>
          </select>
        </label>
        <label class="label">{{ compareMode ? 'Modèle A' : 'Modèle du MTF' }}
          <select v-model="modelA" class="select" :disabled="store.mtfLoading">
            <option value="">Même modèle que le Pricer</option>
            <option v-for="(label, model) in modelLabels" :key="model" :value="model">{{ label }}</option>
          </select>
        </label>
        <label v-if="compareMode" class="label">Modèle B
          <select v-model="modelB" class="select" :disabled="store.mtfLoading">
            <option v-for="(label, model) in modelLabels" :key="model" :value="model" :disabled="model === effectiveModelA">{{ label }}</option>
          </select>
        </label>
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
            <HelpTip text="Nombre de dates futures auxquelles la distribution de valeur mark-to-model est calculée, réparties entre aujourd'hui et la maturité. En cas de paiement final différé, la maturité, un point intermédiaire et le dernier règlement complètent cette grille. Chaque date ajoutée multiplie le coût total par N outer × N inner re-pricings supplémentaires." />
          </label>
          <SensitiveValue mode="input"><input v-model.number="form.n_dates" type="number" step="1" min="2" max="12" class="input" /></SensitiveValue>
        </div>
        <div>
          <label class="label">Graine fixe
            <HelpTip text="Graine Monte Carlo imposée à 42 pour la reproductibilité des calculs de desk. Elle ne se modifie pas ici ; ces calculs ne constituent pas des réplications statistiques indépendantes." />
          </label>
          <SensitiveValue mode="input"><input :value="42" type="number" readonly aria-label="Graine Monte Carlo fixe" class="input" /></SensitiveValue>
        </div>
      </div>
      <div class="text-xs text-slate-600">
        <SensitiveValue>
          Coût de la grille de base ≈ N<sub>outer</sub> × N<sub>dates</sub> × N<sub>inner</sub> évaluations de pricer
          ({{ formatInt(form.n_outer * form.n_dates * form.n_inner) }} évaluations). Les dates de maturité et de règlement final ajoutées sont incluses dans le budget serveur.
        </SensitiveValue>
      </div>
      <div v-if="!store.result" class="text-xs text-amber-500 mt-2">
        Lancez d'abord un pricing (▶ Pricer) pour fixer le prix de référence P₀.
      </div>
      <p v-if="mtfUnavailableReason" role="alert" class="text-xs text-amber-600 mt-2">{{ mtfUnavailableReason }}</p>
      <p v-else-if="usesLsv" class="text-xs text-slate-500 mt-2">
        Le serveur contrôle le levier LSV sur des chemins indépendants avant de calculer son éventail.
      </p>
    </div>

    <p v-if="store.mtfLoading" role="status" class="text-xs text-slate-500">{{ compareMode ? 'Comparaison A/B en cours.' : 'Mark to Future en cours.' }}</p>
    <p v-if="store.mtfIsStale" role="alert" class="text-xs text-amber-600">Le produit ou le marché a changé. Relancez le calcul pour ouvrir le détail.</p>

    <div v-if="store.mtfComparison" class="grid grid-cols-1 sm:grid-cols-2 gap-3">
      <div v-for="(leg, key) in store.mtfComparison" :key="key" class="card text-xs space-y-2">
        <p class="font-semibold">{{ key.toUpperCase() }} · {{ modelLabels[leg.model] || leg.model }}</p>
        <p v-if="leg.error" role="alert" class="text-red-600">{{ leg.error }}</p>
        <template v-else-if="leg.result">
          <LocalVolWingNotice :wings="leg.result.local_vol_wings" />
          <p v-if="leg.result.indicative_heston" class="text-amber-700" role="status">Surface indicative · les écarts de calibration contribuent aux écarts de MTF.</p>
          <p v-for="row in leg.result.calibration_diagnostics || []" :key="row.underlying">
            {{ row.underlying }} · <SensitiveValue>ATM {{ fmtBp(row.max_atm_error_bp) }}, ailes {{ fmtBp(row.max_wing_error_bp) }}, digitales 60/100 % {{ fmtBp(row.max_barrier_digital_error_bp) }}</SensitiveValue>
            <span v-if="row.near_bounds.length"> · Bornes {{ row.near_bounds.join(', ') }}</span>
          </p>
          <p v-if="leg.result.lsv_calibration">Levier LSV qualifié vs Dupire sur la même grille. v₀ du contexte : hypothèse non observée.</p>
          <p v-if="surfaceBenchmarkIssues(leg.result.lsv_calibration).length" class="text-amber-700" role="note">Contrôle direct SSVI : {{ surfaceBenchmarkIssues(leg.result.lsv_calibration).length }} point(s) hors incertitude et tolérance ; affiner la grille.</p>
          <p>P₀ <SensitiveValue>{{ pf(leg.result.main_price) }}</SensitiveValue></p>
          <p v-if="leg.result.reference_ci95">IC 95 % <SensitiveValue>{{ leg.result.reference_ci95.map(pf).join(' à ') }}</SensitiveValue></p>
          <button class="btn-secondary text-xs" :aria-pressed="store.mtfActiveLeg === key"
                  @click="selectLeg(key)">Afficher les détails {{ key.toUpperCase() }}</button>
        </template>
      </div>
    </div>

    <!-- Empty state -->
    <div v-if="!store.mtf" class="flex flex-col items-center justify-center h-52 text-slate-600 gap-2">
      <div class="text-3xl">🗺️</div>
      <div class="text-sm font-medium">Configurez les paramètres et lancez le Mark to Future</div>
      <div class="text-xs">Distribution des valeurs futures du produit sous mesure risque-neutre</div>
    </div>

    <template v-else>
      <div v-if="!store.mtfComparison && store.mtf.model" class="card text-xs">
        <LocalVolWingNotice :wings="store.mtf.local_vol_wings" />
        {{ modelLabels[store.mtf.gbm_atm_curve ? 'gbm_atm_curve' : store.mtf.indicative_heston ? 'heston_indicative' : store.mtf.model] }}
        · P₀ <SensitiveValue>{{ pf(store.mtf.main_price) }}</SensitiveValue>
        <p v-if="store.mtf.lsv_calibration">Levier LSV qualifié vs Dupire sur la même grille. v₀ du contexte : hypothèse non observée.</p>
        <p v-if="surfaceBenchmarkIssues(store.mtf.lsv_calibration).length" class="text-amber-700" role="note">Contrôle direct SSVI : {{ surfaceBenchmarkIssues(store.mtf.lsv_calibration).length }} point(s) hors incertitude et tolérance ; affiner la grille.</p>
        <span v-if="store.mtf.reference_ci95"> · IC 95 % <SensitiveValue>{{ store.mtf.reference_ci95.map(pf).join(' à ') }}</SensitiveValue></span>
        <p v-if="store.mtf.indicative_heston" class="text-amber-700" role="status">Surface indicative · les écarts de calibration contribuent aux écarts de MTF.</p>
        <p v-for="row in store.mtf.calibration_diagnostics || []" :key="row.underlying">
          {{ row.underlying }} · <SensitiveValue>ATM {{ fmtBp(row.max_atm_error_bp) }}, ailes {{ fmtBp(row.max_wing_error_bp) }}, digitales 60/100 % {{ fmtBp(row.max_barrier_digital_error_bp) }}</SensitiveValue>
          <span v-if="row.near_bounds.length"> · Bornes {{ row.near_bounds.join(', ') }}</span>
        </p>
      </div>
      <div class="card text-xs space-y-2">
        <label class="label" for="mtf-population">Population de l’éventail et des statistiques</label>
        <select id="mtf-population" v-model="distributionView" class="select" :disabled="!supportsViews">
          <option value="all">Tous les scénarios initiaux</option>
          <option value="outstanding">Engagements non encore réglés</option>
        </select>
        <p v-if="!supportsViews" role="alert" class="text-amber-600">Ancien résultat : seuls les payoffs actifs sont représentés. Relancez le backend et le calcul pour obtenir les deux vues et les créances impayées.</p>
        <p v-else-if="distributionView === 'all'">Tous les scénarios initiaux sont conservés, y compris ceux intégralement réglés dont le mark vaut zéro. La valeur résiduelle exclut le cash déjà échu.</p>
        <p v-else>Vue conditionnelle aux engagements non réglés : payoffs actifs et créances impayées après rappel ou maturité. Les scénarios intégralement réglés sont exclus ; la population peut changer d’une date à l’autre.</p>
        <p>La valeur résiduelle exclut le cash déjà échu : un mark nul après remboursement ne signifie pas une perte de 100 %.</p>
        <p>Convention : après observations et règlements contractuellement dus le jour de valorisation. Un rappel ne supprime pas les créances encore impayées.</p>
      </div>
      <!-- Fan chart -->
      <div class="card">
        <div class="text-xs font-bold text-slate-500 uppercase tracking-wide mb-3">
          {{ populationLabel }} — valeur résiduelle (% nominal), {{ store.mtfComparison ? 'moyennes et bandes P05/P95' : 'bandes P05/P95 et P25/P75' }}
        </div>
        <SensitiveChart>
          <div style="height:280px;position:relative;">
            <canvas ref="fanCanvas"></canvas>
          </div>
        </SensitiveChart>
      </div>

      <div v-if="comparisonRows.length" class="card text-xs">
        <p class="font-semibold mb-2">Comparaison par date · écarts B − A en points de nominal</p>
        <div class="overflow-x-auto"><table class="w-full whitespace-nowrap text-right">
          <thead><tr>
            <th class="text-left">Date</th><th>Moy. A</th><th>Moy. B</th><th>Δ Moy.</th>
            <th>Δ P05</th><th>Δ P95</th><th>Effectif A/B</th><th>Réglés A/B</th>
          </tr></thead>
          <tbody><tr v-for="{ a, b } in comparisonRows" :key="a.t">
            <td class="py-1 text-left">{{ fmtMtfDate(a.t) }}</td>
            <td><SensitiveValue>{{ pf(a.stats?.mean) }}</SensitiveValue></td>
            <td><SensitiveValue>{{ pf(b.stats?.mean) }}</SensitiveValue></td>
            <td><SensitiveValue>{{ difference(a, b, 'mean') }}</SensitiveValue></td>
            <td><SensitiveValue>{{ difference(a, b, 'p05') }}</SensitiveValue></td>
            <td><SensitiveValue>{{ difference(a, b, 'p95') }}</SensitiveValue></td>
            <td><SensitiveValue>{{ a.n_selected }} / {{ b.n_selected }}</SensitiveValue></td>
            <td><SensitiveValue>{{ pf(a.settled_pct) }} / {{ pf(b.settled_pct) }}</SensitiveValue></td>
          </tr></tbody>
        </table></div>
      </div>

      <!-- Scalar sanity tiles + conditional expectations, on one date -->
      <div class="card">
        <div class="flex items-center gap-3 flex-wrap mb-3">
          <div class="text-xs font-bold text-slate-500 uppercase tracking-wide">
            Indicateurs à la date{{ store.mtfActiveLeg ? ` · modèle ${store.mtfActiveLeg.toUpperCase()}` : '' }}
          </div>
          <select v-model.number="tileDateIdx" class="select !w-auto text-xs !py-1">
            <option v-for="(r, i) in plottableRows" :key="r.t" :value="i">
              {{ fmtMtfDate(r.t) }} — {{ r.n_selected }} scénarios de la vue
            </option>
          </select>
          <div class="text-[11px] text-slate-500">
            {{ populationLabel }} · cash déjà échu exclu de la valeur résiduelle.
          </div>
          <button v-if="tileRow" class="btn-secondary text-xs ml-auto" :disabled="store.mtfIsStale" @click="openQuantiles(tileRow)">
            🔍 Analyser les trajectoires
          </button>
        </div>

        <p v-if="tileRow?.n_outstanding === 0" class="text-xs text-slate-500 mb-3">À cette date, tous les engagements sont réglés : le MTM résiduel est nul. Les remboursements encaissés sont hors du mark.</p>

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
            Valeur résiduelle au-dessus / en dessous du pair
            <HelpTip text="Ces statistiques comparent la valeur résiduelle au pair dans la population sélectionnée. Elles excluent le cash déjà échu et ne mesurent ni le rendement ni le P&amp;L total de l’investissement. Un scénario remboursé a un mark nul sans perte de son remboursement." />
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
            Distribution du MTM au {{ fmtMtfDate(tileRow.t) }}
          </div>
          <div class="text-[11px] text-slate-500">
            {{ tileRow.n_selected }} scénarios de la vue · repères P05/P25/P50/P75/P95, moyenne et pair
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
                <HelpTip text="Moyenne des valeurs résiduelles dans la vue sélectionnée. Tous scénarios inclut les valeurs nulles après règlement complet ; engagements non réglés les exclut." /></th>
              <th class="text-right py-1.5 pr-3 font-semibold">σ
                <HelpTip text="Dispersion des valeurs résiduelles entre les scénarios encore scénarios de la vue à cette date." /></th>
              <th class="text-right py-1.5 pr-3 font-semibold whitespace-nowrap">Réglés
                <HelpTip text="Part des scénarios intégralement réglés. Leur valeur résiduelle est nulle : ils restent dans la vue Tous scénarios et sortent de la vue Engagements non réglés. Un rappel avec créance impayée ne compte pas comme un règlement complet." /></th>
              <th class="text-right py-1.5 pr-3 font-semibold whitespace-nowrap">Effectif vue
                <HelpTip text="Nombre de scénarios retenus dans la vue sélectionnée. En dessous de 50, aucun percentile n'est publié : un P05 lu sur une poignée de trajectoires est du bruit déguisé en mesure de risque." /></th>
              <th class="text-right py-1.5 pr-3 font-semibold">P05</th>
              <th class="text-right py-1.5 pr-3 font-semibold">P25</th>
              <th class="text-right py-1.5 pr-3 font-semibold">P50</th>
              <th class="text-right py-1.5 pr-3 font-semibold">P75</th>
              <th class="text-right py-1.5 pr-3 font-semibold">P95</th>
              <th class="text-right py-1.5 pr-3 font-semibold whitespace-nowrap">P(&gt;100%)
                <HelpTip align="right" text="Probabilité que le produit vaille plus que 100% du notionnel à cette date — comparaison de valeur résiduelle au pair, hors cash déjà échu. Ce n’est pas une probabilité de gain sur l’investissement." /></th>
              <th class="text-right py-1.5 font-semibold whitespace-nowrap">P(&ge;P&#8320;)
                <HelpTip align="right" text="Part de la population sélectionnée dont la valeur résiduelle dépasse le prix initial P₀. Le cash déjà échu est exclu : cette mesure n’est pas une probabilité de bénéfice total." /></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in displayRows" :key="r.t" class="border-b border-slate-800/50">
              <td class="py-1.5 pr-3 text-slate-300 font-semibold whitespace-nowrap">{{ fmtMtfDate(r.t) }}</td>
              <template v-if="r.stats && !r.thin">
                <td class="py-1.5 pr-3 text-right font-mono text-blue-400"><SensitiveValue>{{ pf(r.stats.mean) }}</SensitiveValue></td>
                <td class="py-1.5 pr-3 text-right font-mono text-slate-400"><SensitiveValue>{{ pf(r.stats.std) }}</SensitiveValue></td>
              </template>
              <td v-else colspan="2" class="py-1.5 pr-3 text-right font-mono text-slate-600">—</td>
              <td class="py-1.5 pr-3 text-right font-mono"
                  :class="r.settled_pct > 0 ? 'text-amber-400' : 'text-slate-600'">
                {{ formatPercent(r.settled_pct ?? 0, 1) }}<div class="text-[10px] text-slate-500 whitespace-nowrap">{{ r.n_pending_settlement ?? 0 }} arrêté(s), impayé(s)</div>
              </td>
              <td class="py-1.5 pr-3 text-right font-mono"
                  :class="(r.stats && !r.thin) ? 'text-slate-400' : 'text-amber-500'">
                {{ r.n_selected ?? '—' }}
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
              <!-- Trop peu de scénarios dans la vue : rien plutôt qu'un percentile de bruit. -->
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
import LocalVolWingNotice from './LocalVolWingNotice.vue'
import { surfaceBenchmarkIssues } from '../utils/lsvDiagnostics.js'
import { MTF_MODEL_LABELS as modelLabels, mtfRowsForView } from '../utils/mtfViews.js'
import { ref, computed, watch, nextTick, onMounted, onUnmounted } from 'vue'
import { usePricingStore } from '../stores/pricing.js'
import { useDemoModeStore } from '../stores/demoMode.js'
import { demoChartOptions } from '../composables/useSensitiveChart.js'
import { applyChartTheme, axisTick, chartTheme } from '../charts/theme.js'
import SensitiveValue from './SensitiveValue.vue'
import SensitiveChart from './SensitiveChart.vue'
import HelpTip from './HelpTip.vue'
import MtfDrilldownModal from './MtfDrilldownModal.vue'
import { formatPercent, formatNumber, formatInt, formatDate } from '../utils/format.js'
import {
  Chart, LineElement, LineController, PointElement, BarElement, BarController,
  CategoryScale, LinearScale, Filler, Tooltip, Legend,
} from 'chart.js'

Chart.register(LineElement, LineController, PointElement, BarElement, BarController,
  CategoryScale, LinearScale, Filler, Tooltip, Legend)
applyChartTheme(Chart)

const store = usePricingStore()
const demo = useDemoModeStore()
const fmtBp = value => `${Number(value).toFixed(2)} pb`
const compareMode = ref(!!store.mtfComparison)
const modelA = ref(store.mtfComparison?.a?.model || '')
const modelB = ref(store.mtfComparison?.b?.model || 'heston')
const effectiveModelA = computed(() => modelA.value || store.globalParams.model)
const mtfUnavailableReason = computed(() => {
  if (!Object.hasOwn(modelLabels, effectiveModelA.value)) return 'Le levier LSV doit être qualifié avant activation. Choisissez un modèle disponible dans cet onglet.'
  if ((effectiveModelA.value === 'lsv' || (compareMode.value && modelB.value === 'lsv'))
      && (store.isPreStrike() || !store.underlyings.every(u => u.vol_surface))) {
    return 'Le levier LSV doit être qualifié avec une surface SSVI pour chaque sous-jacent, après le fixing initial.'
  }
  if (compareMode.value && modelB.value === effectiveModelA.value) return 'Sélectionnez deux modèles différents.'
  if (store.globalParams.rateModel !== 'deterministic' && store.globalParams.sigma_r > 0) return 'Le Mark to Future exige des taux déterministes (σr = 0). Sélectionnez ce mode et relancez le pricing avant le MTF.'
  if (store.resultIsStale) return 'Le prix de référence est périmé. Relancez le pricing avant le Mark to Future.'
  return ''
})
const fanCanvas = ref(null)
const histCanvas = ref(null)
let fanChart = null
let histChart = null

const distributionView = ref('all')
const supportsViews = computed(() => (store.mtf?.results || []).every(row => row.stats_all !== undefined))
const populationLabel = computed(() => !supportsViews.value ? 'Payoffs actifs (ancien backend)' :
  distributionView.value === 'all' ? 'Tous les scénarios initiaux' : 'Engagements non encore réglés')
const displayRows = computed(() => mtfRowsForView(store.mtf?.results || [], distributionView.value))
const comparisonSeries = computed(() => ['a', 'b'].flatMap(key => {
  const leg = store.mtfComparison?.[key]
  if (!leg?.result) return []
  return [{ key, price: leg.result.main_price, rows: mtfRowsForView(leg.result.results, distributionView.value) }]
}))
const comparisonRows = computed(() => {
  if (comparisonSeries.value.length !== 2) return []
  const [a, b] = comparisonSeries.value
  const datesB = new Map(b.rows.map(row => [row.t, row]))
  return a.rows.flatMap(row => datesB.has(row.t) ? [{ a: row, b: datesB.get(row.t) }] : [])
})

function difference(a, b, key) {
  if (a.thin || b.thin || a.stats?.[key] == null || b.stats?.[key] == null) return '—'
  const delta = b.stats[key] - a.stats[key]
  return `${delta > 0 ? '+' : ''}${formatNumber(delta, 2)}`
}

const form = ref({ n_outer: 200, n_inner: 500, n_dates: 5 })
const usesLsv = computed(() => effectiveModelA.value === 'lsv' || (compareMode.value && modelB.value === 'lsv'))
watch(usesLsv, active => {
  if (active && store.underlyings.length > 1 && form.value.n_outer === 200 && form.value.n_inner === 500) {
    form.value.n_outer = 100
    form.value.n_inner = 200
  }
}, { immediate: true })
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
  if (mtfUnavailableReason.value) return
  drillOpen.value = false
  distributionView.value = 'all'
  store.runMtf({ ...form.value, model: effectiveModelA.value, modelB: compareMode.value ? modelB.value : null })
}

function selectLeg(key) {
  drillOpen.value = false
  store.selectMtfLeg(key)
}

const pf = v => (v === null || v === undefined) ? '—' : formatPercent(v, 2)
const fmtMtfDate = t => {
  if (!store.mtf?.origin_date) return `${formatNumber(t, 4)}Y`
  const day = new Date(store.mtf.origin_date + 'T00:00:00Z')
  day.setUTCDate(day.getUTCDate() + Math.round(t * 365.25))
  return formatDate(day.toISOString().slice(0, 10))
}

// ── Sélection de trajectoires ──────────────────────────────────────
// Quantiles retain original scenario IDs and use the selected population.
function aliveSortedIds(row) {
  const ids = []
  row.pvs.forEach((v, i) => { if (row.selected_mask?.[i]) ids.push(i) })
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
  if (store.mtfIsStale) return
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
  if (!ids.length || store.mtfIsStale) return
  drillFocus.value = null
  drillOpen.value = true
  store.runMtfDrilldown({ t: row.t, ids: ids.slice(0, 12), labels })
}

// The selected population owns every statistic and the minimum sample threshold.
const plottableRows = computed(() =>
  displayRows.value.filter(r => r.stats && !r.thin))

const tileRow = computed(() => plottableRows.value[tileDateIdx.value] || null)

const scalarTiles = computed(() => {
  const row = tileRow.value
  if (!row) return []
  const s = row.stats
  const surv = `${populationLabel.value} : ${row.n_selected ?? '?'} scénario(s) à cette date.`
  return [
    { label: 'P(MTM>100%)', val: formatPercent(s.p_above_100, 1),
      cls: s.p_above_100 >= 50 ? 'text-green-400' : 'text-red-400',
      tip: `Probabilité que le produit vaille plus que 100% du notionnel, sur la population sélectionnée. ${surv}` },
    { label: 'P(MTM≥P₀)', val: formatPercent(s.p_above_p0, 1),
      cls: s.p_above_p0 >= 50 ? 'text-green-400' : 'text-red-400',
      tip: `Probabilité que la valeur résiduelle dépasse le prix d'entrée P₀, sur la population sélectionnée. ${surv}` },
    { label: 'E(MTM)', val: pf(s.e_mtm), cls: 'text-blue-400',
      tip: `Valeur résiduelle moyenne sur la population sélectionnée — une moyenne selon le périmètre choisi. ${surv}` },
    { label: 'E(max(MTM-100,0))', val: pf(s.e_upside), cls: 'text-green-400',
      tip: `Espérance du seul potentiel au-dessus de 100%, sur la population sélectionnée. Moyenne sur TOUT l'échantillon, les valeurs sous le pair comptant pour zéro. Le cash déjà échu est exclu. ${surv}` },
  ]
})

const conditionalTiles = computed(() => {
  const row = tileRow.value
  if (!row) return []
  const s = row.stats
  const n = row.n_selected || 1
  const share = c => `${formatPercent(c / n * 100, 1)} des scénarios de la vue`
  return [
    { label: 'E(MTM | MTM > 100%)', val: pf(s.e_mtm_win), cls: 'text-green-400',
      sub: `${s.n_win} scénario(s) — ${share(s.n_win)}`,
      tip: "Valeur moyenne du produit sur les seuls scénarios où il vaut plus que le pair. Espérance conditionnelle : elle ne dit rien de la probabilité d'y être — c'est P(MTM>100%) qui la porte." },
    { label: 'E(MTM | MTM < 100%)', val: pf(s.e_mtm_lose), cls: 'text-red-400',
      sub: `${s.n_lose} scénario(s) — ${share(s.n_lose)}`,
      tip: "Valeur moyenne du produit sur les seuls scénarios où il vaut moins que le pair. Lue avec le nombre de scénarios concernés, c'est la sévérité d'un mauvais cas, pas sa fréquence." },
    { label: 'Écart moyen au-dessus du pair', val: pf(s.avg_gain), cls: 'text-green-400',
      sub: s.max_gain === null ? null : `Écart maximal : ${pf(s.max_gain)}`,
      tip: "Moyenne de (MTM − 100%) sur les seuls scénarios au-dessus du pair. C'est le pendant conditionnel de E(max(MTM-100,0)) : celle-ci divise par tout l'échantillon, celle-là par les seules valeurs au-dessus du pair." },
    { label: 'Écart moyen sous le pair', val: pf(s.avg_loss), cls: 'text-red-400',
      sub: s.max_loss === null ? null : `Écart maximal : ${pf(s.max_loss)}`,
      tip: "Moyenne de (100% − MTM) sur les seuls scénarios sous le pair, en magnitude positive. Multipliée par P(MTM<100%), elle donne l’écart sous le pair sur l’ensemble, hors cash échu ; ce n’est pas une perte sur l’investissement." },
  ]
})

function renderChart() {
  if (fanChart) { fanChart.destroy(); fanChart = null }
  if (!store.mtf || !fanCanvas.value) return

  const p0 = store.mtf.main_price ?? 100
  const results = displayRows.value
  // null pour une date sans effectif suffisant : Chart.js interrompt la ligne
  // plutôt que de la tirer vers une valeur inventée.
  const mk = key => [{ x: 0, y: p0 }, ...results.map(r => ({ x: r.t,
    y: r.stats && !r.thin ? r.stats[key] : null }))]

  // Dataset order matters for fill:'-1' (fills toward the previous dataset).
  // `cubicInterpolationMode: 'monotone'` on every series, and NOT `tension`:
  // free cubic smoothing overshoots between points, independently per curve.
  // On a quantile fan that draws bands the engine never computed — a P25 arc
  // bulging above the médiane, a P05 dipping below P01 — in the one chart whose
  // whole job is to show an ordered distribution. Monotone interpolation cannot
  // overshoot, so the drawn order is the computed order.
  const line = { fill: false, pointRadius: 0, cubicInterpolationMode: 'monotone' }
  const comparisonDatasets = comparisonSeries.value.flatMap(({ key, price, rows }) => {
    const color = key === 'a' ? '#2563eb' : '#a35c12'
    const fill = key === 'a' ? 'rgba(37,99,235,.13)' : 'rgba(163,92,18,.13)'
    return [['p95', 'P95'], ['p05', 'P05'], ['mean', 'Moyenne']].map(([metric, label]) => ({
      ...line, label: `${key.toUpperCase()} · ${label}`, mtfLeg: key, mtfMetric: label,
      data: [{ x: 0, y: price }, ...rows.map(row => ({ x: row.t, y: row.thin ? null : row.stats?.[metric] ?? null }))],
      borderColor: color, borderWidth: metric === 'mean' ? 2 : 1,
      fill: metric === 'p05' ? '-1' : false, backgroundColor: fill,
    }))
  })
  fanChart = new Chart(fanCanvas.value, {
    type: 'line',
    data: {
      datasets: comparisonDatasets.length ? comparisonDatasets : [
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
        const dataset = chart.data.datasets[hit.datasetIndex]
        const leg = dataset.mtfLeg
        const rows = leg ? comparisonSeries.value.find(series => series.key === leg)?.rows : results
        const row = rows?.[hit.index - 1]
        if (!row?.stats || row.thin) return
        // La courbe médiane porte le libellé « Médiane », pas « P50 » —
        // cliquer dessus doit quand même ouvrir la trajectoire médiane.
        const raw = dataset.mtfMetric || dataset.label
        const key = raw === 'Médiane' ? 'P50' : raw
        if (leg) store.selectMtfLeg(leg)
        openQuantiles(row, QUANTILE_LEVELS[key] !== undefined ? key : null)
      },
      onHover: (evt, els) => {
        evt.native.target.style.cursor = els.length ? 'pointer' : 'default'
      },
      plugins: {
        legend: { position: 'bottom', labels: { font: { size: 10 }, boxWidth: 12 } },
        tooltip: {
          mode: 'index', intersect: false,
          callbacks: {
            title: items => fmtMtfDate(items[0].parsed.x),
            label: it => `${it.dataset.label}: ${formatPercent(it.parsed.y, 2)}`,
          },
        },
      },
      scales: {
        x: { type: 'linear', title: { display: true, text: 'Années depuis la date de valorisation' },
          ticks: { font: { size: 10 }, callback: v => `${formatNumber(v, 2)}Y` } },
        y: { ticks: { font: { size: 9 }, callback: axisTick('%') } },
      },
      animation: { duration: 250 },
    }, demo.enabled),
  })
}

// ── Histogramme de la distribution à une date ──────────────────────
// Histogram values and drill-down IDs use exactly the selected population.
const histData = computed(() => {
  const row = tileRow.value
  if (!row) return null
  const ids = []
  row.pvs.forEach((v, i) => { if (row.selected_mask?.[i]) ids.push(i) })
  if (!ids.length) return null
  const vals = ids.map(i => row.pvs[i])
  const lo = Math.min(...vals), hi = Math.max(...vals)
  const nb = Math.max(5, Math.min(80, histBins.value || 30))
  // Distribution dégénérée (tous les surscénarios de la vue au même mark, ce qui arrive à
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
              return `${c} scénario(s) — ${formatPercent(c / row.n_selected * 100, 1)}`
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
  const results = displayRows.value
  let csv, filename

  if (type === 'runs') {
    // Le statut vivant/rappelé accompagne chaque valeur : sans lui l'export
    // ne permet pas de distinguer un contrat éteint d'un contrat sans valeur.
    const lines = ['scenario,date_mtm_y,pv_pct,payoff_actif,engagement_non_regle,creance_impayee,vue_selectionnee,dans_vue']
    results.forEach(r => r.pvs.forEach((pv, i) => lines.push(
      `${i},${r.t.toFixed(4)},${pv.toFixed(4)},${r.alive?.[i] ? 1 : 0},${r.outstanding?.[i] ? 1 : 0},${r.pending_settlement?.[i] ? 1 : 0},${distributionView.value},${r.selected_mask?.[i] ? 1 : 0}`)))
    csv = lines.join('\n'); filename = 'mtf_runs.csv'
  } else {
    const cols = ['date_mtm_y', 'n_selected', 'e_mtm', 'std', 'p01', 'p05', 'p25', 'p50',
      'p75', 'p95', 'p99', 'p_above_100pct', 'p_above_p0', 'e_upside',
      'n_au_dessus_pair', 'n_sous_pair', 'e_mtm_au_dessus_pair', 'e_mtm_sous_pair',
      'ecart_moyen_haut', 'ecart_moyen_bas', 'ecart_max_haut', 'ecart_max_bas', 'mtm_min', 'mtm_max']
    const lines = [cols.join(',')]
    // Toutes les colonnes sont en % de nominal, sauf p_above_* déjà en fraction —
    // les deux en-têtes le disent. Une case vide vaut « pas de sous-échantillon »
    // (aucun gagnant, aucun perdant) et se distingue ainsi d'un zéro calculé.
    const fmt = v => (v === null || v === undefined) ? '' : Number(v).toFixed(4)
    results.forEach(r => {
      const s = r.stats
      if (!s) { lines.push([r.t, r.n_selected ?? 0, ...Array(cols.length - 2).fill('')].join(',')); return }
      lines.push([r.t, r.n_selected ?? 0, s.mean, s.std, s.p01, s.p05, s.p25, s.p50,
        s.p75, s.p95, s.p99, s.p_above_100 / 100, s.p_above_p0 / 100, s.e_upside,
        s.n_win, s.n_lose, s.e_mtm_win, s.e_mtm_lose,
        s.avg_gain, s.avg_loss, s.max_gain, s.max_loss, s.mtm_min, s.mtm_max]
        .map((v, i) => (i === 0 || i === 1 || i === 14 || i === 15) ? v : fmt(v)).join(','))
    })
    csv = ['vue,' + distributionView.value, ...lines].join('\n'); filename = 'mtf_summary.csv'
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

// Match the initial mount: a new fan opens at its first eligible date.
// The final settlement date legitimately contains zeros and stays selectable.
watch(() => store.mtf, () => {
  tileDateIdx.value = 0
  renderAll()
}, { flush: 'post' })
watch(() => store.mtfIsStale, stale => { if (stale) drillOpen.value = false })
watch(effectiveModelA, model => {
  if (modelB.value === model) modelB.value = Object.keys(modelLabels).find(key => key !== model)
}, { immediate: true })
watch([tileDateIdx, histBins], async () => { await nextTick(); renderHist() })
watch(distributionView, (_, previousView) => {
  const previousRows = mtfRowsForView(store.mtf?.results || [], previousView).filter(r => r.stats && !r.thin)
  const selectedTime = previousRows[tileDateIdx.value]?.t
  const matchingIndex = plottableRows.value.findIndex(r => r.t === selectedTime)
  tileDateIdx.value = Math.max(0, matchingIndex)
  renderAll()
})
watch(() => demo.enabled, renderAll)
onMounted(renderAll)
onUnmounted(() => {
  if (fanChart) fanChart.destroy()
  if (histChart) histChart.destroy()
})
</script>
