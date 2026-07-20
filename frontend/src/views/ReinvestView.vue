<template>
  <div class="min-h-screen bg-slate-950 flex flex-col text-slate-100">

    <!-- Header -->
    <header class="border-b border-slate-800 px-6 py-3 flex items-center gap-4 shrink-0">
      <RouterLink to="/" class="flex items-center gap-2.5 hover:opacity-80 transition-opacity">
        <img src="/tp_logo.png" alt="TP Advisory" class="h-7 w-7 rounded-sm bg-white object-contain p-0.5">
        <span class="font-bold text-slate-100 tracking-tight">Structura</span>
      </RouterLink>
      <RouterLink to="/" class="btn-secondary text-xs px-3 py-1.5">← Accueil</RouterLink>
      <span class="text-slate-700">|</span>
      <span class="font-bold text-slate-100 tracking-tight">Réinvestissement — alternatives à un produit en vie</span>
    </header>

    <main class="flex-1 overflow-y-auto p-6">
      <div class="max-w-4xl mx-auto flex flex-col gap-4">

        <div class="text-xs text-slate-500">
          Espace de travail interne, pas montré au client : partez d'un deal en vie et cherchez le meilleur
          sous-jacent de remplacement pour la même structure. Pour du sur-mesure au niveau du script, utilisez
          l'onglet Script.
        </div>

        <!-- ── 1. Sélecteur de produit ─────────────────────────── -->
        <div class="card">
          <div class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3">1. Produit client en vie</div>
          <select class="select text-sm" v-model.number="selectedDealId" @change="onSelectDeal">
            <option :value="null">— Choisir un deal —</option>
            <option v-for="d in activeDeals" :key="d.id" :value="d.id">
              {{ d.reference }} — {{ d.product_type || 'produit structuré' }} ({{ d.underlyings.map(u => u.name).join(', ') }})
            </option>
          </select>
          <div v-if="dealsStore.loading" class="text-xs text-slate-600 mt-2">Chargement des deals…</div>
        </div>

        <template v-if="deal">
          <!-- ── 2. Économique ──────────────────────────────────── -->
          <div class="card">
            <div class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3">2. Économique</div>
            <div class="grid grid-cols-2 sm:grid-cols-3 gap-3 text-xs mb-4">
              <div><div class="text-slate-500 mb-0.5">Value date</div><div class="font-mono text-slate-200">{{ deal.value_date }}</div></div>
              <div><div class="text-slate-500 mb-0.5">Maturité bookée</div><div class="font-mono text-slate-200">{{ deal.maturity_date }} ({{ deal.T.toFixed(2) }} an(s))</div></div>
              <div><div class="text-slate-500 mb-0.5">Nominal</div><div class="font-mono text-slate-200">{{ deal.nominal.toLocaleString('fr-FR') }} {{ deal.devise }}</div></div>
            </div>

            <div v-if="deal.underlyings.length !== 1" class="text-xs text-amber-500">
              ⚠ Le scan d'alternatives ne gère pour l'instant que les produits mono-sous-jacent (limitation v1) —
              ce deal en a {{ deal.underlyings.length }}.
            </div>

            <template v-else>
              <div v-if="!scalarTerms.length" class="text-xs text-amber-500">
                Aucun paramètre exploitable trouvé sur ce produit.
              </div>
              <template v-else>
                <!-- Hypothèses économiques du scan -->
                <div class="grid grid-cols-2 gap-3 text-xs mb-3">
                  <div>
                    <label class="label">Maturité du scan (an(s))
                      <HelpTip text="Préremplie sur la maturité bookée — modifiable si vous voulez tester une reconduction sur une autre durée. Tous les candidats du scan seront pricés sur cette maturité." />
                    </label>
                    <input v-model.number="form.T_years" type="number" step="0.25" min="0.1" class="input" />
                  </div>
                  <div>
                    <label class="label">Prix cible (%)
                      <HelpTip text="Prérempli au prix actuel du produit (fair value au booking) — pertinent pour la plupart des produits qui ne pricent pas au pair. Mettez 100 si vous visez explicitement le pair (typique pour un autocall/phoenix)." />
                    </label>
                    <input v-model.number="form.target_price_pct" type="number" step="0.5" class="input" />
                  </div>
                </div>

                <!-- Paramètre résolu par bissection + ses bornes, groupés ensemble -->
                <div class="grid grid-cols-3 gap-3 text-xs">
                  <div>
                    <label class="label">Paramètre à optimiser
                      <HelpTip text="Le PARAM du script dont on cherche la valeur au prix cible — coupon pour un autocall/phoenix, strike pour une option, etc. Dépend du produit sélectionné." />
                    </label>
                    <select class="select" v-model="form.param_name" @change="prefillBounds">
                      <option v-for="p in scalarTerms" :key="p.name" :value="p.name">{{ p.desc || p.name }}</option>
                    </select>
                  </div>
                  <div>
                    <label class="label">Borne basse{{ paramUnit }}
                      <HelpTip text="Borne inférieure de la recherche par bissection sur le paramètre ci-dessus — il faut que la solution soit encadrée. Préremplie à 0,5x la valeur actuellement booquée, à élargir si le solveur ne converge pas." />
                    </label>
                    <input v-model.number="form.lo_display" type="number" step="0.1" class="input" />
                  </div>
                  <div>
                    <label class="label">Borne haute{{ paramUnit }}
                      <HelpTip text="Borne supérieure de la recherche sur le paramètre ci-dessus — même logique que la borne basse. Préremplie à 1,5x la valeur actuellement booquée." />
                    </label>
                    <input v-model.number="form.hi_display" type="number" step="0.1" class="input" />
                  </div>
                </div>

                <!-- Mode avancé — édite tous les autres PARAM du script -->
                <div class="mt-3 pt-3 border-t border-slate-800">
                  <label class="flex items-center gap-2 text-xs cursor-pointer">
                    <input type="checkbox" v-model="advancedMode" />
                    Mode avancé — éditer les autres paramètres du script
                    <HelpTip text="Par défaut, tous les paramètres du script restent figés à leur valeur bookée, sauf celui résolu par bissection ci-dessus. Le mode avancé permet de fixer manuellement n'importe quel autre paramètre (barrière, fréquence, etc.) avant de lancer le scan." />
                  </label>
                  <div v-if="advancedMode && overridableTerms.length" class="grid grid-cols-2 sm:grid-cols-3 gap-3 mt-3">
                    <div v-for="t in overridableTerms" :key="t.name" class="flex flex-col gap-1"
                      :class="t.kind === 'array' ? 'col-span-2 sm:col-span-1' : ''">
                      <label class="label">{{ t.desc || t.name }}</label>
                      <template v-if="t.kind === 'array'">
                        <div v-for="(v, ri) in overrides[t.name]" :key="ri" class="flex items-center gap-1.5">
                          <span class="text-[10px] text-slate-600 font-mono w-9 shrink-0">Obs {{ ri + 1 }}</span>
                          <div class="relative flex-1">
                            <input type="number" class="input pr-6 text-xs py-1" step="any" v-model.number="overrides[t.name][ri]" />
                            <span v-if="t.is_pct" class="absolute right-2 top-1/2 -translate-y-1/2 text-[10px] text-slate-500">%</span>
                          </div>
                          <button v-if="overrides[t.name].length > 1" class="text-slate-600 hover:text-red-400 text-xs shrink-0"
                            @click="overrides[t.name].splice(ri, 1)">✕</button>
                        </div>
                        <button class="text-xs text-blue-400 hover:underline self-start"
                          @click="overrides[t.name].push(overrides[t.name].at(-1) ?? 0)">+ Ajouter une observation</button>
                      </template>
                      <div v-else class="relative">
                        <input type="number" class="input pr-6 text-xs" step="any" v-model.number="overrides[t.name]" />
                        <span v-if="t.is_pct" class="absolute right-2 top-1/2 -translate-y-1/2 text-xs text-slate-500">%</span>
                      </div>
                    </div>
                  </div>
                </div>
              </template>
            </template>
          </div>

          <template v-if="deal.underlyings.length === 1 && form.param_name">
            <!-- ── 3. Métriques ──────────────────────────────────── -->
            <div class="card">
              <div class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3">3. Métriques (filtres de risque)</div>
              <div v-if="hiddenBarrierMetrics" class="text-xs text-slate-600 mb-2">
                Ce produit n'a pas de mécanisme de KI/rappel anticipé détecté — seules les métriques génériques restent affichées.
              </div>
              <div class="flex flex-col gap-2">
                <div v-for="m in visibleMetricDefs" :key="m.key" class="flex items-center gap-2 text-xs">
                  <input type="checkbox" v-model="filters[m.key].active" />
                  <span class="w-60 shrink-0 flex items-center gap-1 whitespace-nowrap overflow-hidden text-ellipsis">
                    <span class="overflow-hidden text-ellipsis">{{ m.label }}</span>
                    <HelpTip :text="m.help" />
                  </span>
                  <span class="text-slate-500">ne pas</span>
                  <select class="select w-32 text-xs" v-model="filters[m.key].direction" :disabled="!filters[m.key].active">
                    <option value="max">dépasser</option>
                    <option value="min">descendre sous</option>
                  </select>
                  <input v-model.number="filters[m.key].threshold" type="number" step="1" min="0" max="100"
                    class="input w-20 text-xs" :disabled="!filters[m.key].active" />
                  <span class="text-slate-500">%</span>
                </div>
              </div>
            </div>

            <!-- ── 4. Univers de sous-jacents ─────────────────────── -->
            <div class="card">
              <div class="flex items-center justify-between mb-3">
                <div class="text-xs font-bold text-slate-400 uppercase tracking-wider">4. Univers de sous-jacents candidats</div>
                <div class="flex items-center gap-3">
                  <span class="text-xs text-slate-500">{{ selectedTickers.length }} sélectionné(s)</span>
                  <button class="text-[10px] text-blue-400 hover:underline" @click="selectAllTickers()">Tout</button>
                  <button class="text-[10px] text-slate-500 hover:underline" @click="selectedTickers = []">Aucun</button>
                </div>
              </div>
              <div class="flex flex-col gap-3 max-h-80 overflow-y-auto pr-1">
                <div v-for="g in underlyingGroups" :key="g.group">
                  <div class="flex items-center gap-2 mb-1.5">
                    <span class="text-xs text-slate-500">{{ g.group }}</span>
                    <button class="text-[10px] text-blue-400/80 hover:underline" @click="selectAllTickers(g)">tout</button>
                    <span class="text-slate-700 text-[10px]">·</span>
                    <button class="text-[10px] text-slate-600 hover:underline" @click="deselectGroupTickers(g)">aucun</button>
                  </div>
                  <div class="flex flex-wrap gap-1.5">
                    <button v-for="it in g.items" :key="it.ticker" type="button"
                      class="px-2.5 py-1 rounded-full text-xs border transition-colors"
                      :class="selectedTickers.includes(it.ticker)
                        ? 'border-blue-500 bg-blue-950/50 text-blue-300'
                        : 'border-slate-700 text-slate-400 hover:border-slate-500 hover:text-slate-300'"
                      @click="toggleTicker(it.ticker)">
                      {{ it.label }}
                    </button>
                  </div>
                </div>
              </div>
            </div>

            <!-- ── 5. Lancer ──────────────────────────────────────── -->
            <div class="flex justify-end">
              <button class="btn-primary text-xs px-5" :disabled="scanLoading || !selectedTickers.length" @click="launchScan">
                <span v-if="scanLoading" class="w-3 h-3 border border-white border-t-transparent rounded-full animate-spin inline-block mr-1"></span>
                ▶ Lancer les prix
              </button>
            </div>
            <div v-if="scanError" class="text-xs text-red-400">⚠ {{ scanError }}</div>

            <!-- ── Résultats ───────────────────────────────────────── -->
            <div v-if="scanResult" class="card overflow-x-auto">
              <div class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3">
                Classement — {{ scanResult.results.length }} candidat(s) retenu(s)
              </div>
              <table v-if="scanResult.results.length" class="text-xs w-full border-collapse">
                <thead>
                  <tr class="border-b border-slate-700">
                    <th class="text-left text-slate-500 font-medium py-1 pr-3">Sous-jacent</th>
                    <th class="text-right text-slate-500 font-medium py-1 pr-3">
                      {{ paramColumnLabel }} résolu
                      <HelpTip align="right" :text="activeParam?.desc || 'Valeur du paramètre sélectionné en étape 2 qui atteint le prix cible pour ce candidat.'" />
                    </th>
                    <th class="text-right text-slate-500 font-medium py-1 pr-3">Prix atteint</th>
                    <th class="text-right text-slate-500 font-medium py-1 pr-3">
                      σ / q
                      <HelpTip align="right" text="Volatilité historique 1 an et rendement du dividende utilisés pour ce candidat (Yahoo Finance) — comparez-les si des candidats se ressemblent de façon suspecte." />
                    </th>
                    <th v-if="showMetricCol('ki')" class="text-right text-slate-500 font-medium py-1 pr-3">
                      P(KI) <HelpTip align="right" text="Probabilité qu'un chemin simulé déclenche le mécanisme de barrière basse (KI) du produit." />
                    </th>
                    <th v-if="showMetricCol('autocall')" class="text-right text-slate-500 font-medium py-1 pr-3">
                      P(autocall) <HelpTip align="right" text="Probabilité qu'un chemin simulé déclenche un rappel anticipé (autocall) avant l'échéance." />
                    </th>
                    <th class="text-right text-slate-500 font-medium py-1 pr-3">
                      P(perte nette) <HelpTip align="right" text="Probabilité que le payoff actualisé soit inférieur au prix cible payé — perte nette pour l'investisseur, quel que soit le type de produit." />
                    </th>
                    <th class="text-right text-slate-500 font-medium py-1 pr-3">
                      P(scénario optimal) <HelpTip align="right" text="Probabilité d'atteindre un payoff proche du meilleur scénario simulé pour ce candidat." />
                    </th>
                    <th class="py-1"></th>
                  </tr>
                </thead>
                <tbody>
                  <template v-for="(r, i) in scanResult.results" :key="r.ticker">
                    <tr class="border-b border-slate-800 hover:bg-slate-800/40">
                      <td class="py-1.5 pr-3 font-medium">
                        <span :class="i === 0 ? 'text-amber-400' : 'text-slate-200'">{{ i === 0 ? '🏆 ' : '' }}{{ r.name }}</span>
                      </td>
                      <td class="py-1.5 pr-3 text-right font-mono text-green-400">{{ displayParam(r.solved_param) }}</td>
                      <td class="py-1.5 pr-3 text-right font-mono text-slate-300">{{ (r.price * 100).toFixed(2) }}%</td>
                      <td class="py-1.5 pr-3 text-right font-mono text-slate-500">{{ (r.sigma * 100).toFixed(1) }}% / {{ (r.q * 100).toFixed(1) }}%</td>
                      <td v-if="showMetricCol('ki')" class="py-1.5 pr-3 text-right font-mono text-slate-400">{{ r.ki_pct.toFixed(1) }}%</td>
                      <td v-if="showMetricCol('autocall')" class="py-1.5 pr-3 text-right font-mono text-slate-400">{{ r.autocall_pct.toFixed(1) }}%</td>
                      <td class="py-1.5 pr-3 text-right font-mono" :class="r.capital_loss_pct > 0 ? 'text-red-400' : 'text-slate-400'">{{ r.capital_loss_pct.toFixed(1) }}%</td>
                      <td class="py-1.5 pr-3 text-right font-mono text-slate-400">{{ r.full_coupon_pct.toFixed(1) }}%</td>
                      <td class="py-1.5 text-right whitespace-nowrap">
                        <button class="text-[10px] px-2 py-1 bg-slate-700 hover:bg-slate-600 text-slate-200 rounded"
                          @click="toggleProposal(r)">
                          {{ proposalFor === r.ticker ? '▲' : '📄' }} Proposition
                        </button>
                      </td>
                    </tr>
                    <tr v-if="proposalFor === r.ticker">
                      <td :colspan="resultColCount" class="py-3 px-2 bg-slate-900/50 border-b border-slate-800">
                        <div v-if="proposalLoading" class="text-xs text-slate-500">Génération de la proposition…</div>
                        <div v-else-if="proposalError" class="text-xs text-red-400">⚠ {{ proposalError }}</div>
                        <div v-else-if="proposalData" class="flex flex-col gap-3">
                          <div class="flex flex-wrap items-center justify-between gap-2">
                            <div class="text-xs text-slate-400">
                              {{ proposalData.param_desc }} <span class="font-mono text-slate-200">{{ displayParam(proposalData.candidate.solved_param) }}</span>
                              · value date <span class="font-mono text-slate-200">{{ proposalData.value_date }}</span>
                              · échéance <span class="font-mono text-slate-200">{{ proposalData.maturity_date }}</span>
                            </div>
                            <button class="btn-secondary text-[10px] px-2 py-1" :disabled="pdfLoading" @click="downloadProposalPdf(r)">
                              <span v-if="pdfLoading" class="w-3 h-3 border-2 border-slate-400 border-t-transparent rounded-full animate-spin inline-block mr-1"></span>
                              📄 Télécharger le PDF
                            </button>
                          </div>

                          <!-- Paramètres du backtest — relançable sans refaire tout le scan -->
                          <div class="flex flex-wrap items-end gap-2 pt-2 border-t border-slate-800">
                            <div>
                              <label class="label mb-0.5">Début historique</label>
                              <input v-model="btForm.start" type="date" class="input text-xs py-1" />
                            </div>
                            <div>
                              <label class="label mb-0.5">Fréquence relance</label>
                              <select v-model.number="btForm.freq" class="select text-xs py-1">
                                <option :value="1">Quotidien</option>
                                <option :value="5">Hebdo</option>
                                <option :value="21">Mensuel</option>
                                <option :value="63">Trimestriel</option>
                                <option :value="126">Semestriel</option>
                              </select>
                            </div>
                            <div>
                              <label class="label mb-0.5">Montant investi (%)</label>
                              <input v-model.number="btForm.invest_pct" type="number" step="10" class="input text-xs py-1 w-24" />
                            </div>
                            <button class="btn-secondary text-[10px] px-2 py-1" :disabled="proposalLoading" @click="fetchProposal(r)">
                              🔄 Relancer le backtest
                            </button>
                          </div>

                          <div v-if="proposalData.backtest?.error" class="text-xs text-amber-500">
                            ⚠ Backtest indisponible : {{ proposalData.backtest.error }}
                          </div>
                          <template v-else-if="proposalData.backtest?.stats">
                            <div class="grid grid-cols-3 sm:grid-cols-6 gap-2 text-xs">
                              <div class="stat-box"><div class="text-slate-500 mb-0.5">TRI médian</div><div class="font-mono text-green-400">{{ (proposalData.backtest.stats.median_irr * 100).toFixed(2) }}%</div></div>
                              <div class="stat-box"><div class="text-slate-500 mb-0.5">TRI moyen</div><div class="font-mono text-slate-300">{{ (proposalData.backtest.stats.mean_irr * 100).toFixed(2) }}%</div></div>
                              <div class="stat-box"><div class="text-slate-500 mb-0.5">P10 / pire</div><div class="font-mono" :class="proposalData.backtest.stats.worst_irr < 0 ? 'text-red-400' : 'text-slate-400'">{{ (proposalData.backtest.stats.p10_irr * 100).toFixed(2) }}% / {{ (proposalData.backtest.stats.worst_irr * 100).toFixed(2) }}%</div></div>
                              <div class="stat-box"><div class="text-slate-500 mb-0.5">% positif</div><div class="font-mono text-slate-400">{{ proposalData.backtest.stats.pct_positive.toFixed(1) }}%</div></div>
                              <div class="stat-box"><div class="text-slate-500 mb-0.5">% rappel anticipé</div><div class="font-mono text-slate-400">{{ proposalData.backtest.stats.early_recall_pct.toFixed(1) }}%</div></div>
                              <div class="stat-box"><div class="text-slate-500 mb-0.5">Fenêtres</div><div class="font-mono text-slate-500">{{ proposalData.backtest.stats.n_windows }}</div></div>
                            </div>
                            <div class="text-[10px] text-slate-600">
                              Barrières et flux réellement versés de la fenêtre de replay la plus récente
                              (départ {{ proposalData.backtest.product?.window_start || '—' }}), superposés à la
                              trajectoire du sous-jacent — en mono-sous-jacent le worst-of est le sous-jacent, pas
                              besoin d'un second graphique. Le TRI par fenêtre en dessous couvre toutes les
                              fenêtres testées ; elles se chevauchent fortement sur une maturité pluriannuelle, ce
                              ne sont pas des observations indépendantes.
                            </div>
                            <div>
                              <div class="text-[10px] text-slate-500 mb-1">Trajectoire de {{ r.ticker }}</div>
                              <div class="h-44"><canvas ref="proposalCanvas"></canvas></div>
                            </div>
                            <div v-if="proposalData.backtest.stats.windows?.length">
                              <div class="text-[10px] text-slate-500 mb-1">TRI réalisé par fenêtre</div>
                              <div class="h-28"><canvas ref="proposalWindowsCanvas"></canvas></div>
                            </div>
                          </template>
                        </div>
                      </td>
                    </tr>
                  </template>
                </tbody>
              </table>
              <div v-else class="text-xs text-slate-600">Aucun candidat ne passe les filtres de risque configurés.</div>

              <details v-if="scanResult.excluded.length" class="mt-3">
                <summary class="text-xs text-slate-500 cursor-pointer hover:text-slate-300">
                  {{ scanResult.excluded.length }} candidat(s) écarté(s)
                </summary>
                <ul class="text-xs text-slate-500 mt-2 flex flex-col gap-1">
                  <li v-for="e in scanResult.excluded" :key="e.ticker">{{ e.name }} — {{ e.error }}</li>
                </ul>
              </details>
            </div>
          </template>
        </template>

      </div>
    </main>
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch, nextTick } from 'vue'
import { RouterLink } from 'vue-router'
import { useDealsStore } from '../stores/deals.js'
import { apiFetch } from '../utils/api.js'
import { underlyingGroups } from '../data/commonUnderlyings.js'
import HelpTip from '../components/HelpTip.vue'
import {
  Chart, LineElement, LineController, PointElement, BarElement, BarController,
  CategoryScale, LinearScale, Tooltip, Legend,
} from 'chart.js'

Chart.register(LineElement, LineController, PointElement, BarElement, BarController,
  CategoryScale, LinearScale, Tooltip, Legend)

const dealsStore = useDealsStore()
dealsStore.loadDeals()

const activeDeals = computed(() => dealsStore.deals.filter(d => d.status === 'actif'))

const selectedDealId = ref(null)
const deal = ref(null)

const allTerms = computed(() => deal.value?.terms || [])
const scalarTerms = computed(() => allTerms.value.filter(t => t.kind === 'scalar'))
const activeParam = computed(() => scalarTerms.value.find(t => t.name === form.param_name))
const paramUnit = computed(() => activeParam.value?.is_pct ? ' (%)' : '')
// Le script décrit déjà chaque PARAM (desc) — on l'affiche telle quelle
// plutôt que d'inventer un libellé générique ("coupon") qui ne colle qu'aux
// autocalls.
const paramColumnLabel = computed(() => activeParam.value?.desc || activeParam.value?.name || 'Paramètre')

// Mode avancé — tous les PARAM sauf celui résolu par bissection deviennent
// éditables (overrides en unités d'affichage, convertis en unités stockées
// à l'envoi). Le PARAM choisi dans le dropdown en sort dynamiquement : s'il
// change, l'ancien redevient éditable, le nouveau disparaît de la liste.
const advancedMode = ref(false)
const overrides = reactive({})
const overridableTerms = computed(() => allTerms.value.filter(t => t.name !== form.param_name))

const form = reactive({
  param_name: '',
  target_price_pct: 100,
  lo_display: 0,
  hi_display: 0,
  T_years: 0,
})

async function onSelectDeal() {
  deal.value = null
  form.param_name = ''
  advancedMode.value = false
  Object.keys(overrides).forEach(k => delete overrides[k])
  scanResult.value = null
  scanError.value = ''
  if (!selectedDealId.value) return
  deal.value = await dealsStore.selectDeal(selectedDealId.value)
  form.T_years = deal.value.T
  // Prix cible ancré sur le prix réel du produit (fair value au booking) —
  // 100% (par) n'a de sens que pour les structures conçues pour ça
  // (autocall/phoenix). Une option vanille ne trade jamais près du pair.
  form.target_price_pct = deal.value.fair_value || deal.value.price_traded || 100
  for (const t of allTerms.value) {
    overrides[t.name] = Array.isArray(t.value) ? t.value.map(v => toDisplay(t, v)) : toDisplay(t, t.value)
  }
  if (scalarTerms.value.length) {
    form.param_name = scalarTerms.value[0].name
    prefillBounds()
  }
}

function toDisplay(term, storedVal) {
  return term.is_pct ? storedVal * 100 : storedVal
}
function toStored(term, displayVal) {
  return term.is_pct ? displayVal / 100 : displayVal
}

function prefillBounds() {
  const t = activeParam.value
  if (!t) return
  const d = toDisplay(t, t.value)
  form.lo_display = +(d * 0.5).toFixed(4)
  form.hi_display = +(d > 0 ? d * 1.5 : d + 1).toFixed(4)
}

function displayParam(storedVal) {
  const t = activeParam.value
  if (!t) return storedVal
  return toDisplay(t, storedVal).toFixed(4) + (t.is_pct ? '%' : '')
}

const metricDefs = [
  { key: 'ki', label: 'Probabilité de KI', requires: 'has_ki_param',
    help: "Probabilité qu'un chemin simulé déclenche le mécanisme de barrière basse (KI) du produit." },
  { key: 'autocall', label: "Probabilité d'autocall anticipé", requires: 'has_stop',
    help: "Probabilité qu'un chemin simulé déclenche un rappel anticipé (autocall) avant l'échéance." },
  { key: 'capital_loss', label: 'Probabilité de perte nette',
    help: "Probabilité que le payoff actualisé soit inférieur au prix cible payé — perte nette pour l'investisseur, quel que soit le type de produit (pas seulement les notes à capital garanti)." },
  { key: 'full_coupon', label: 'Probabilité de scénario optimal',
    help: "Probabilité d'atteindre un payoff proche du meilleur scénario simulé pour ce candidat." },
]
// N'affiche KI/autocall que si le script du produit a réellement ce
// mécanisme (deal.flags, heuristique _classify_param_barrier côté backend) —
// pas de sens pour une option vanille par exemple. Les colonnes du tableau
// de résultats suivent la même règle (showMetricCol).
const visibleMetricDefs = computed(() => metricDefs.filter(m => !m.requires || deal.value?.flags?.[m.requires]))
const hiddenBarrierMetrics = computed(() => visibleMetricDefs.value.length < metricDefs.length)
function showMetricCol(key) {
  return visibleMetricDefs.value.some(m => m.key === key)
}
const filters = reactive({
  ki: { active: true, direction: 'max', threshold: 20 },
  autocall: { active: false, direction: 'min', threshold: 50 },
  capital_loss: { active: true, direction: 'max', threshold: 10 },
  full_coupon: { active: false, direction: 'min', threshold: 50 },
})

const selectedTickers = ref([])
function toggleTicker(ticker) {
  const i = selectedTickers.value.indexOf(ticker)
  if (i >= 0) selectedTickers.value.splice(i, 1)
  else selectedTickers.value.push(ticker)
}
function selectAllTickers(group) {
  const tickers = (group ? [group] : underlyingGroups).flatMap(g => g.items.map(it => it.ticker))
  selectedTickers.value = Array.from(new Set([...selectedTickers.value, ...tickers]))
}
function deselectGroupTickers(group) {
  const tickers = new Set(group.items.map(it => it.ticker))
  selectedTickers.value = selectedTickers.value.filter(tk => !tickers.has(tk))
}

const scanLoading = ref(false)
const scanError = ref('')
const scanResult = ref(null)

function buildParamOverrides() {
  if (!advancedMode.value) return {}
  return Object.fromEntries(overridableTerms.value.map(ot => [
    ot.name,
    Array.isArray(overrides[ot.name]) ? overrides[ot.name].map(v => toStored(ot, v)) : toStored(ot, overrides[ot.name]),
  ]))
}

async function launchScan() {
  scanLoading.value = true
  scanError.value = ''
  scanResult.value = null
  proposalFor.value = null
  try {
    const t = activeParam.value
    const payload = {
      candidates: selectedTickers.value.map(tk => ({ ticker: tk })),
      param_name: form.param_name,
      target_price: form.target_price_pct / 100,
      lo: toStored(t, form.lo_display),
      hi: toStored(t, form.hi_display),
      T: form.T_years,
      filters: visibleMetricDefs.value
        .filter(m => filters[m.key].active)
        .map(m => ({ metric: m.key, threshold: filters[m.key].threshold, direction: filters[m.key].direction })),
      param_overrides: buildParamOverrides(),
    }
    const res = await apiFetch(`/api/deals/${deal.value.id}/reinvest/scan`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    const data = await res.json()
    if (!res.ok) throw new Error(data.detail || 'Erreur scan')
    scanResult.value = data
  } catch (e) {
    scanError.value = e.message
  } finally {
    scanLoading.value = false
  }
}

// Nombre de colonnes du tableau de résultats — pour le colspan du panneau
// de proposition, qui doit s'étendre sous toute la ligne.
const resultColCount = computed(() =>
  6 + (showMetricCol('ki') ? 1 : 0) + (showMetricCol('autocall') ? 1 : 0) + 1)

// Paramètres du backtest — modifiables sans relancer tout le scan, un seul
// jeu de valeurs partagé (une seule proposition ouverte à la fois, comme
// proposalFor). Réinitialisés à l'ouverture d'une nouvelle proposition.
const btForm = reactive({ start: '2015-01-01', freq: 21, invest_pct: 100 })

function buildProposalPayload(row) {
  const t = activeParam.value
  return {
    ticker: row.ticker,
    name: row.name,
    param_name: form.param_name,
    target_price: form.target_price_pct / 100,
    lo: toStored(t, form.lo_display),
    hi: toStored(t, form.hi_display),
    T: form.T_years,
    param_overrides: buildParamOverrides(),
    backtest_start: btForm.start,
    backtest_freq: btForm.freq,
    backtest_invest_pct: btForm.invest_pct,
  }
}

const proposalFor = ref(null)
const proposalLoading = ref(false)
const proposalError = ref('')
const proposalData = ref(null)
const proposalCanvas = ref(null)
const proposalWindowsCanvas = ref(null)
let proposalChart = null
let proposalWindowsChart = null

async function fetchProposal(row) {
  proposalLoading.value = true
  proposalError.value = ''
  proposalData.value = null
  try {
    const res = await apiFetch(`/api/deals/${deal.value.id}/reinvest/proposal`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(buildProposalPayload(row)),
    })
    const data = await res.json()
    if (!res.ok) throw new Error(data.detail || 'Erreur proposition')
    proposalData.value = data
  } catch (e) {
    proposalError.value = e.message
  } finally {
    proposalLoading.value = false
  }
}

function toggleProposal(row) {
  if (proposalFor.value === row.ticker) { proposalFor.value = null; return }
  proposalFor.value = row.ticker
  Object.assign(btForm, { start: '2015-01-01', freq: 21, invest_pct: 100 })
  fetchProposal(row)
}

watch(proposalData, async () => {
  await nextTick()
  if (proposalChart) { proposalChart.destroy(); proposalChart = null }
  if (proposalWindowsChart) { proposalWindowsChart.destroy(); proposalWindowsChart = null }

  // Trajectoire du sous-jacent, annotée avec les barrières et les dates de
  // flux réels de la fenêtre de replay la plus récente (déjà recalées côté
  // backend sur la base 100 de CET historique). Pas de second graphique
  // "produit" séparé : en mono-sous-jacent le worst-of EST le sous-jacent —
  // voir MEMORY investment-solution-module pour l'échange qui a mené ici.
  const hist = proposalData.value?.backtest?.history
  const prod = proposalData.value?.backtest?.product
  if (hist && proposalCanvas.value) {
    const values = hist.normalized.map(v => v != null ? +(v * 100).toFixed(2) : null)
    const dateIdx = new Map(hist.dates.map((d, i) => [d, i]))
    const cfIdxSet = new Set((prod?.cash_flows || [])
      .map(cf => dateIdx.get(cf.date)).filter(i => i != null))

    const datasets = [{
      label: proposalFor.value, data: values, borderColor: '#3b82f6',
      backgroundColor: 'rgba(59,130,246,.1)', borderWidth: 1.3, tension: 0.1,
      pointRadius: (ctx) => cfIdxSet.has(ctx.dataIndex) ? 4 : 0,
      pointBackgroundColor: '#f59e0b', pointBorderColor: '#f59e0b',
    }]
    for (const b of prod?.barriers || []) {
      if (b.level == null) continue
      const col = b.direction === 'up' ? 'rgba(16,185,129,.7)' : 'rgba(239,68,68,.7)'
      datasets.push({
        label: `${b.name} ${(b.level * 100).toFixed(0)}%`, data: hist.dates.map(() => b.level * 100),
        borderColor: col, borderWidth: 1, borderDash: [5, 4], pointRadius: 0,
      })
    }
    proposalChart = new Chart(proposalCanvas.value, {
      type: 'line',
      data: { labels: hist.dates, datasets },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: {
          legend: { position: 'bottom', labels: { color: '#94a3b8', font: { size: 8 }, boxWidth: 10 } },
          tooltip: { callbacks: { label: it => (it.datasetIndex === 0 && cfIdxSet.has(it.dataIndex))
            ? `${it.dataset.label}: ${it.raw}% (flux versé)` : `${it.dataset.label}: ${it.raw}%` } },
        },
        scales: {
          x: { ticks: { color: '#475569', font: { size: 8 }, maxTicksLimit: 8 }, grid: { color: '#1e293b' } },
          y: { ticks: { color: '#475569', font: { size: 8 }, callback: v => v + '%' }, grid: { color: '#1e293b' } },
        },
        animation: { duration: 150 },
      },
    })
  }

  // TRI réalisé par fenêtre — sert à vérifier visuellement, en regard du
  // graphique de trajectoire ci-dessus, où le produit se ferait rappeler ou
  // perdrait du capital, plutôt que de juger uniquement sur les stats
  // agrégées (médiane/moyenne peuvent masquer des fenêtres très
  // chevauchantes, voir HelpTip ci-dessus).
  const windows = proposalData.value?.backtest?.stats?.windows
  if (windows?.length && proposalWindowsCanvas.value) {
    proposalWindowsChart = new Chart(proposalWindowsCanvas.value, {
      type: 'bar',
      data: {
        labels: windows.map(w => w.start_date),
        datasets: [{
          label: 'TRI par fenêtre',
          data: windows.map(w => +(w.irr * 100).toFixed(2)),
          backgroundColor: windows.map(w => w.irr >= 0 ? 'rgba(16,185,129,.6)' : 'rgba(239,68,68,.6)'),
        }],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: { callbacks: { label: it => `TRI: ${it.raw}%${windows[it.dataIndex].early_recall ? ' (rappel anticipé)' : ''}` } },
        },
        scales: {
          x: { ticks: { color: '#475569', font: { size: 8 }, maxTicksLimit: 8 }, grid: { display: false } },
          y: { ticks: { color: '#475569', font: { size: 8 }, callback: v => v + '%' }, grid: { color: '#1e293b' } },
        },
        animation: { duration: 150 },
      },
    })
  }
})

const pdfLoading = ref(false)
async function downloadProposalPdf(row) {
  pdfLoading.value = true
  try {
    const res = await apiFetch(`/api/deals/${deal.value.id}/reinvest/proposal/pdf`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(buildProposalPayload(row)),
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      throw new Error(err.detail || 'Erreur génération PDF')
    }
    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `Proposition_${deal.value.reference}_${row.ticker}_${new Date().toISOString().slice(0, 10)}.pdf`
    a.click()
    URL.revokeObjectURL(url)
  } catch (e) {
    proposalError.value = e.message
  } finally {
    pdfLoading.value = false
  }
}
</script>
