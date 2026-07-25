<template>
  <div class="flex-1 flex flex-col min-h-0 text-slate-100">

    <main class="flex-1 overflow-y-auto p-6">
      <div class="max-w-[1600px] mx-auto flex flex-col gap-3">

        <div class="page-header">
          <div class="flex items-center gap-3">
            <RouterLink :to="{ path: '/', query: { category: 'risk_management' } }" class="btn-secondary text-xs px-3 py-1.5">← Retour</RouterLink>
            <h1 class="page-title">Risk Management</h1>
          </div>
        </div>

        <div class="flex gap-4 flex-wrap items-start">

          <!-- ── Sélection du portefeuille actif (partagée par tous les onglets) ── -->
          <div class="card flex flex-col gap-1 w-full sm:w-64 shrink-0">
            <div class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-1 px-0.5">Portefeuille actif</div>
            <button class="flex items-center gap-2 text-left px-2.5 py-2 rounded-lg text-xs font-medium transition-colors"
              :class="pf.view === 'global' ? 'bg-blue-600/15 text-blue-300 ring-1 ring-blue-600/40' : 'text-slate-400 hover:bg-slate-800/60'"
              @click="pf.selectView('global')">
              <span class="text-sm">📊</span>
              <span class="flex-1">Tous portefeuilles</span>
              <span class="text-[10px] font-mono px-1.5 py-0.5 rounded-full bg-slate-800 text-slate-400">{{ pf.activeDealsCount }}</span>
            </button>
            <div class="border-t border-slate-800 my-1"></div>
            <button v-for="p in pf.portfolios" :key="p.id"
              class="flex items-center gap-2 text-left px-2.5 py-2 rounded-lg text-xs font-medium transition-colors min-w-0"
              :class="pf.view === p.id ? 'bg-blue-600/15 text-blue-300 ring-1 ring-blue-600/40' : 'text-slate-400 hover:bg-slate-800/60'"
              @click="pf.selectView(p.id)">
              <span class="text-sm shrink-0">{{ p.is_default ? '⭐' : '📁' }}</span>
              <span class="flex-1 truncate">{{ p.name }}</span>
              <span class="text-[10px] font-mono px-1.5 py-0.5 rounded-full bg-slate-800 text-slate-400 shrink-0">{{ p.deal_count }}</span>
            </button>
          </div>

          <!-- ── Panneau principal ──────────────────────────────── -->
          <div class="card kpi-tile flex-1 min-w-0 flex flex-col gap-3">
            <div class="flex items-center gap-3 flex-wrap">
              <div class="text-sm font-bold text-slate-100">
                {{ pf.view === 'global' ? '📊 Tous portefeuilles' : `${pf.isDefaultView ? '⭐' : '📁'} ${pf.label}` }}
              </div>
              <button class="btn-secondary text-xs px-3 py-1.5 ml-auto" :disabled="recomputing || !pf.members.length"
                @click="recomputePortfolio">
                <span v-if="recomputing"
                  class="w-3 h-3 border-2 border-slate-400 border-t-transparent rounded-full animate-spin inline-block mr-1"></span>
                🔄 Recalculer{{ recomputing ? ` (${recomputeDone}/${recomputeTotal})` : '' }}
              </button>
            </div>

            <!-- Menu du module : gestion / analyses (d'autres viendront) -->
            <div class="flex border-b border-slate-800 -mb-1">
              <button @click="activeTab = 'portfolios'"
                :class="activeTab === 'portfolios' ? 'border-b-2 border-blue-500 text-slate-100' : 'text-slate-500 hover:text-slate-300'"
                class="px-4 py-2 text-xs font-medium transition-colors">
                Portefeuilles ({{ pf.members.length }})
              </button>
              <button @click="activeTab = 'greeks'"
                :class="activeTab === 'greeks' ? 'border-b-2 border-blue-500 text-slate-100' : 'text-slate-500 hover:text-slate-300'"
                class="px-4 py-2 text-xs font-medium transition-colors">
                Greeks
              </button>
              <button @click="activeTab = 'chocs'"
                :class="activeTab === 'chocs' ? 'border-b-2 border-blue-500 text-slate-100' : 'text-slate-500 hover:text-slate-300'"
                class="px-4 py-2 text-xs font-medium transition-colors">
                ⚡ Chocs
              </button>
              <button @click="activeTab = 'pnl'"
                :class="activeTab === 'pnl' ? 'border-b-2 border-blue-500 text-slate-100' : 'text-slate-500 hover:text-slate-300'"
                class="px-4 py-2 text-xs font-medium transition-colors">
                P&L
              </button>
            </div>

            <!-- ══ Onglet Greeks agrégés ═════════════════════════ -->
            <template v-if="activeTab === 'greeks'">
                <div class="text-[10px] text-slate-500 -mt-1">
                  Somme des Greeks déjà calculés par deal (nominal × sensibilité % × taux de change vers EUR), regroupés par sous-jacent — lecture pure, aucun recalcul Monte Carlo ici.
                  <HelpTip text="Utilisez le bouton Recalculer pour rafraîchir les Greeks des deals sous-jacents avant de lire cet écran." />
                </div>

                <div v-if="pf.riskLoading" class="text-xs text-slate-500">Chargement…</div>

                <template v-else-if="pf.risk">
                  <div v-if="pf.risk.deals_missing_greeks.length"
                    class="text-xs text-amber-400 bg-amber-950/30 border border-amber-900/50 rounded-lg px-3 py-2">
                    ⚠ {{ pf.risk.deals_missing_greeks.length }} deal(s) sans Greeks calculés — chiffres incomplets
                    ({{ pf.risk.deals_missing_greeks.map(d => d.reference).join(', ') }})
                  </div>
                  <div v-if="pf.risk.deals_stale.length"
                    class="text-xs text-slate-400 bg-slate-800/40 border border-slate-700/60 rounded-lg px-3 py-2">
                    ⏱ {{ pf.risk.deals_stale.length }} deal(s) avec des Greeks vieux de plus de 7 jours
                    ({{ pf.risk.deals_stale.map(d => d.reference).join(', ') }})
                  </div>

                  <div v-if="!pf.risk.deals_included.length" class="text-xs text-slate-500">
                    Aucun deal avec des Greeks calculés dans cette sélection.
                  </div>

                  <template v-else>
                    <div class="overflow-x-auto table-shell" tabindex="0" role="region">
                      <table class="w-full text-xs border-collapse">
                        <thead>
                          <tr class="border-b border-slate-700 text-slate-500">
                            <th class="text-left py-1.5 pr-3 font-semibold">Sous-jacent
                              <HelpTip text="Sous-jacent canonique (regroupe les deals qui le nomment différemment, via le catalogue Admin market-data) — cliquez la ligne pour voir le détail par deal." /></th>
                            <th class="text-right py-1.5 pr-3 font-semibold">Delta (EUR)
                              <HelpTip align="right" text="Exposition nette en EUR pour un mouvement de 100% du sous-jacent : Σ(delta% du deal × nominal × taux de change), sommée sur tous les deals qui le contiennent. Vert = exposition longue, rouge = short." /></th>
                            <th class="text-right py-1.5 pr-3 font-semibold">Gamma (EUR)
                              <HelpTip align="right" text="Variation du delta net (EUR) pour un mouvement de 100% du sous-jacent. Peut être très élevé et bruité près d'une barrière autocall/KI (payoff quasi-digital) — vérifiez le détail par deal si un chiffre paraît disproportionné." /></th>
                            <th class="text-right py-1.5 font-semibold">Vega (EUR)
                              <HelpTip align="right" text="Sensibilité nette en EUR à une hausse de 100 points de volatilité implicite du sous-jacent, sommée sur tous les deals concernés." /></th>
                          </tr>
                        </thead>
                        <tbody>
                          <template v-for="(g, key) in pf.risk.per_underlying" :key="key">
                            <tr class="border-b border-slate-800/50 hover:bg-slate-800/20 transition-colors cursor-pointer"
                              @click="expandedUnderlying = expandedUnderlying === key ? null : key">
                              <td class="py-1.5 pr-3 text-slate-300 font-semibold">
                                <span class="text-slate-600 mr-1">{{ expandedUnderlying === key ? '▾' : '▸' }}</span>{{ g.label }}
                              </td>
                              <td class="py-1.5 pr-3 text-right font-mono"
                                :class="g.delta_eur >= 0 ? 'text-emerald-400' : 'text-red-400'">{{ formatNominal(g.delta_eur) }}</td>
                              <td class="py-1.5 pr-3 text-right font-mono text-slate-400">{{ formatNominal(g.gamma_eur) }}</td>
                              <td class="py-1.5 text-right font-mono text-slate-400">{{ formatNominal(g.vega_eur) }}</td>
                            </tr>
                            <tr v-if="expandedUnderlying === key" class="bg-slate-900/60">
                              <td colspan="4" class="py-2 pl-6 pr-3">
                                <table class="w-full text-[11px] border-collapse">
                                  <thead>
                                    <tr class="text-slate-600">
                                      <th class="text-left py-1 pr-3 font-medium">Deal</th>
                                      <th class="text-right py-1 pr-3 font-medium">Delta (EUR / %)
                                        <HelpTip align="right" text="% = part de ce deal dans le delta net de la ligne — peut dépasser 100% ou être négatif si des deals se compensent entre eux." /></th>
                                      <th class="text-right py-1 pr-3 font-medium">Gamma (EUR / %)</th>
                                      <th class="text-right py-1 font-medium">Vega (EUR / %)</th>
                                    </tr>
                                  </thead>
                                  <tbody>
                                    <tr v-for="c in g.contributions" :key="c.deal_id"
                                      class="hover:bg-slate-800/40 cursor-pointer" @click.stop="openDealDetail(c.deal_id)">
                                      <td class="py-1 pr-3 font-mono font-semibold text-blue-400">{{ c.reference }}</td>
                                      <td class="py-1 pr-3 text-right font-mono text-slate-400">
                                        {{ formatNominal(c.delta_eur) }} <span class="text-slate-600">({{ sharePct(c.delta_eur, g.delta_eur) }})</span>
                                      </td>
                                      <td class="py-1 pr-3 text-right font-mono text-slate-400">
                                        {{ formatNominal(c.gamma_eur) }} <span class="text-slate-600">({{ sharePct(c.gamma_eur, g.gamma_eur) }})</span>
                                      </td>
                                      <td class="py-1 text-right font-mono text-slate-400">
                                        {{ formatNominal(c.vega_eur) }} <span class="text-slate-600">({{ sharePct(c.vega_eur, g.vega_eur) }})</span>
                                      </td>
                                    </tr>
                                  </tbody>
                                </table>
                              </td>
                            </tr>
                          </template>
                        </tbody>
                      </table>
                    </div>

                    <div class="grid grid-cols-2 sm:grid-cols-5 gap-3">
                      <div class="stat-box">
                        <div class="text-xs text-slate-500 mb-1">Nominal total
                          <HelpTip text="Somme des nominaux de tous les deals actifs de cette sélection, convertis en EUR au taux de change courant (get_fx_series) — inclut aussi les deals sans Greeks calculés, contrairement aux autres tuiles de cette rangée." /></div>
                        <div class="text-lg font-bold font-mono text-slate-200">{{ formatNominal(pf.risk.nominal_total_eur) }}</div>
                        <div class="text-[10px] text-slate-600">EUR</div>
                      </div>
                      <div class="stat-box">
                        <div class="text-xs text-slate-500 mb-1">Theta net
                          <HelpTip text="Décroissance temporelle nette du book, en EUR par jour calendaire — somme des theta par deal (nominal × taux de change), déjà scalaire donc pas de regroupement par sous-jacent nécessaire." /></div>
                        <div class="text-lg font-bold font-mono text-slate-200">{{ formatNominal(pf.risk.scalar.theta) }}</div>
                        <div class="text-[10px] text-slate-600">EUR / jour</div>
                      </div>
                      <div class="stat-box">
                        <div class="text-xs text-slate-500 mb-1">Rho net
                          <HelpTip text="Sensibilité nette du book à une hausse de 100 points de base (1pt) du taux sans risque, en EUR — le moteur calcule la dérivée brute par rapport au taux (par unité de r, soit par 100pt), rescalée ×0.01 ici pour lire un impact par 1pt réellement, puis sommée par deal (nominal × taux de change)." /></div>
                        <div class="text-lg font-bold font-mono text-slate-200">{{ formatNominal(pf.risk.scalar.rho) }}</div>
                        <div class="text-[10px] text-slate-600">EUR / 1pt taux</div>
                      </div>
                      <div class="stat-box">
                        <div class="text-xs text-slate-500 mb-1">Deals inclus
                          <HelpTip text="Nombre de deals dont les Greeks ont pu être sommés dans cet écran — exclut les deals sans Greeks jamais calculés (voir l'avertissement au-dessus)." /></div>
                        <div class="text-lg font-bold font-mono text-slate-200">{{ pf.risk.deals_included.length }}</div>
                      </div>
                      <div class="stat-box">
                        <div class="text-xs text-slate-500 mb-1">Plus ancien calcul
                          <HelpTip text="Date du calcul de Greeks le plus ancien parmi les deals inclus — l'agrégat n'est fiable que si cette date est récente ; utilisez Recalculer sinon." /></div>
                        <div class="text-sm font-bold font-mono text-slate-200">
                          {{ pf.risk.oldest_computed_at ? new Date(pf.risk.oldest_computed_at).toLocaleDateString('fr-FR') : '—' }}
                        </div>
                      </div>
                    </div>
                  </template>
                </template>
              </template>

            <!-- ══ Onglet Chocs ══════════════════════════════════ -->
            <template v-else-if="activeTab === 'chocs'">
                <div class="text-sm font-bold text-slate-100">
                  ⚡ Choc — {{ pf.view === 'global' ? 'Tous portefeuilles' : pf.label }}
                  <HelpTip width="w-72" text="Full reprice Monte Carlo sous le scénario choqué, deal par deal — pas une approximation par les Greeks (les payoffs à barrière sont trop non-linéaires pour ça). Chaque run est conservé en historique." />
                </div>

                <div class="flex items-center gap-2">
                  <select class="select text-xs py-1.5" @change="applyShockPreset($event.target.value)">
                    <option value="">Preset…</option>
                    <option v-for="p in shockPresets" :key="p.label" :value="p.label">{{ p.label }}</option>
                  </select>
                </div>
                <div class="flex flex-wrap gap-3">
                  <label class="flex flex-col gap-0.5 text-[10px] text-slate-500">Spot %
                    <input v-model.number="shockForm.spot_shock_pct" type="number" step="1" class="input text-xs py-1 w-24" />
                  </label>
                  <label class="flex flex-col gap-0.5 text-[10px] text-slate-500">Vol (pts)
                    <input v-model.number="shockForm.vol_shock_pts" type="number" step="1" class="input text-xs py-1 w-24" />
                  </label>
                  <label class="flex flex-col gap-0.5 text-[10px] text-slate-500">Taux (bp)
                    <input v-model.number="shockForm.rate_shock_bp" type="number" step="10" class="input text-xs py-1 w-24" />
                  </label>
                  <label class="flex flex-col gap-0.5 text-[10px] text-slate-500">Corr (pts)
                    <input v-model.number="shockForm.corr_shock_pts" type="number" step="5" class="input text-xs py-1 w-24" />
                  </label>
                  <button class="btn-primary text-xs px-4 py-1.5 self-end" :disabled="shockLoading"
                    @click="runPortfolioShock">
                    <span v-if="shockLoading"
                      class="w-3 h-3 border-2 border-white border-t-transparent rounded-full animate-spin inline-block mr-1"></span>
                    Lancer le choc
                  </button>
                </div>

                <template v-if="shockResult">
                  <div v-if="shockResult.error" class="text-xs text-amber-400">⚠ {{ shockResult.error }}</div>
                  <template v-else>
                    <div class="grid grid-cols-2 sm:grid-cols-4 gap-3">
                      <div class="stat-box">
                        <div class="text-xs text-slate-500 mb-1">ΔMtM total</div>
                        <div class="text-lg font-bold font-mono" :class="shockResult.total_delta_eur >= 0 ? 'text-emerald-400' : 'text-red-400'">
                          {{ formatNominal(shockResult.total_delta_eur) }}
                        </div>
                        <div class="text-[10px] text-slate-600">EUR</div>
                      </div>
                      <div class="stat-box">
                        <div class="text-xs text-slate-500 mb-1">Impact / nominal
                          <HelpTip text="ΔMtM total ÷ nominal total (EUR) du périmètre choqué — même dénominateur que la tuile Nominal total du sous-onglet Greeks (inclut les deals ignorés/en erreur, pas seulement ceux effectivement repricés)." /></div>
                        <div class="text-lg font-bold font-mono" :class="(shockResult.pct_impact ?? 0) >= 0 ? 'text-emerald-400' : 'text-red-400'">
                          {{ shockResult.pct_impact != null ? shockResult.pct_impact.toFixed(2) + '%' : '—' }}
                        </div>
                        <div class="text-[10px] text-slate-600">vs {{ formatNominal(shockResult.nominal_total_eur) }} EUR</div>
                      </div>
                      <div class="stat-box">
                        <div class="text-xs text-slate-500 mb-1">Deals choqués</div>
                        <div class="text-lg font-bold font-mono text-slate-200">{{ shockResult.contributions.length }}</div>
                      </div>
                      <div class="stat-box">
                        <div class="text-xs text-slate-500 mb-1">Ignorés / erreurs</div>
                        <div class="text-lg font-bold font-mono text-slate-200">
                          {{ shockResult.skipped.length }} / {{ shockResult.errors.length }}
                        </div>
                      </div>
                    </div>

                    <div v-if="shockResult.skipped.length || shockResult.errors.length"
                      class="text-xs text-amber-400 bg-amber-950/30 border border-amber-900/50 rounded-lg px-3 py-2">
                      ⚠ {{ [...shockResult.skipped.map(s => s.reference), ...shockResult.errors.map(e => e.reference)].join(', ') }}
                      — deal(s) non choqués (résolution en attente ou erreur de pricing)
                    </div>

                    <div class="overflow-x-auto table-shell" tabindex="0" role="region">
                      <table class="w-full text-xs border-collapse">
                        <thead>
                          <tr class="border-b border-slate-700 text-slate-500">
                            <th class="text-left py-1.5 pr-3 font-semibold">Deal</th>
                            <th class="text-right py-1.5 pr-3 font-semibold num">MtM avant</th>
                            <th class="text-right py-1.5 pr-3 font-semibold num">MtM après</th>
                            <th class="text-right py-1.5 font-semibold num">ΔMtM (EUR)</th>
                          </tr>
                        </thead>
                        <tbody>
                          <tr v-for="c in shockResult.contributions" :key="c.deal_id"
                            class="border-b border-slate-800/50 hover:bg-slate-800/20 transition-colors cursor-pointer"
                            @click="openDealDetail(c.deal_id)">
                            <td class="py-1.5 pr-3 font-mono font-semibold text-blue-400">{{ c.reference }}</td>
                            <td class="py-1.5 pr-3 text-right font-mono text-slate-400">{{ (c.mtm_before * 100).toFixed(2) }}%</td>
                            <td class="py-1.5 pr-3 text-right font-mono text-slate-400">{{ (c.mtm_after * 100).toFixed(2) }}%</td>
                            <td class="py-1.5 text-right font-mono" :class="c.delta_eur >= 0 ? 'text-emerald-400' : 'text-red-400'">
                              {{ formatNominal(c.delta_eur) }}
                            </td>
                          </tr>
                        </tbody>
                      </table>
                    </div>
                  </template>
                </template>

                <!-- Historique -->
                <div class="pt-2 border-t border-slate-800">
                  <div class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-2">Historique</div>
                  <div v-if="!pf.currentShockHistory.length" class="text-xs text-slate-500">Aucun choc joué sur cette sélection.</div>
                  <div v-else class="overflow-x-auto table-shell" tabindex="0" role="region">
                  <table class="w-full text-xs border-collapse">
                    <tbody>
                      <tr v-for="h in pf.currentShockHistory" :key="h.id" class="border-b border-slate-800/50">
                        <td class="py-1 pr-3 text-slate-500 whitespace-nowrap">{{ new Date(h.created_at).toLocaleString('fr-FR') }}</td>
                        <td class="py-1 pr-3 text-slate-300">{{ h.label }}</td>
                        <td class="py-1 pr-3 text-right font-mono" :class="(h.result.total_delta_eur ?? 0) >= 0 ? 'text-emerald-500' : 'text-red-500'">
                          {{ formatNominal(h.result.total_delta_eur) }} EUR
                        </td>
                        <td class="py-1 text-right font-mono" :class="(h.result.pct_impact ?? 0) >= 0 ? 'text-emerald-500' : 'text-red-500'">
                          {{ h.result.pct_impact != null ? h.result.pct_impact.toFixed(2) + '%' : '—' }}
                        </td>
                      </tr>
                    </tbody>
                  </table>
                  </div>
                </div>
            </template>

            <!-- ══ Onglet P&L ════════════════════════════════════ -->
            <template v-else-if="activeTab === 'pnl'">
              <div class="text-sm font-bold text-slate-100">
                P&L explain — {{ pf.view === 'global' ? 'Tous portefeuilles' : pf.label }}
                <HelpTip width="w-72" text="Waterfall temps / spot / vol / corrélation entre deux dates, calculé deal par deal (réévaluations séquentielles à graine identique — CRN) puis agrégé en EUR sur la sélection. Full reprice Monte Carlo : comptez plusieurs secondes par deal." />
              </div>

              <div class="flex flex-wrap gap-3 items-end">
                <label class="flex flex-col gap-0.5 text-[10px] text-slate-500">Date 1
                  <input v-model="pnlD1" type="date" class="input text-xs py-1"
                    title="Vide = chaque deal part de sa propre date de valeur (P&L depuis l'origine)" />
                </label>
                <label class="flex flex-col gap-0.5 text-[10px] text-slate-500">Date 2
                  <input v-model="pnlD2" type="date" class="input text-xs py-1" />
                </label>
                <button class="btn-primary text-xs px-4 py-1.5" :disabled="pnlLoading || !pf.members.length"
                  @click="runPnl">
                  <span v-if="pnlLoading"
                    class="w-3 h-3 border-2 border-white border-t-transparent rounded-full animate-spin inline-block mr-1"></span>
                  {{ pnlLoading ? 'Calcul en cours…' : 'Expliquer le P&L' }}
                </button>
                <span v-if="pnlLoading" class="text-[10px] text-slate-500">
                  Full reprice × {{ pf.members.length }} deal(s) — cela peut prendre plusieurs minutes.
                </span>
              </div>

              <template v-if="pnlResult">
                <div v-if="pnlResult.error" class="text-xs text-amber-400">⚠ {{ pnlResult.error }}</div>
                <template v-else>
                  <div class="grid grid-cols-2 sm:grid-cols-4 gap-3">
                    <div class="stat-box">
                      <div class="text-xs text-slate-500 mb-1">P&L total
                        <HelpTip text="Variation de valeur (ΔMtM) + flux détachés sur la période, en EUR, sommés sur tous les deals expliqués." /></div>
                      <div class="text-lg font-bold font-mono" :class="pnlResult.pnl_total_eur >= 0 ? 'text-emerald-400' : 'text-red-400'">
                        {{ formatNominal(pnlResult.pnl_total_eur) }}
                      </div>
                      <div class="text-[10px] text-slate-600">EUR</div>
                    </div>
                    <div class="stat-box">
                      <div class="text-xs text-slate-500 mb-1">ΔMtM / Flux</div>
                      <div class="text-sm font-bold font-mono text-slate-200">
                        {{ formatNominal(pnlResult.delta_mtm_eur) }} / {{ formatNominal(pnlResult.flows_total_eur) }}
                      </div>
                      <div class="text-[10px] text-slate-600">EUR</div>
                    </div>
                    <div class="stat-box">
                      <div class="text-xs text-slate-500 mb-1">P&L / nominal
                        <HelpTip text="P&L total ÷ nominal total (EUR) de la sélection — le nominal inclut aussi les deals ignorés/en erreur, même dénominateur que les tuiles Risque et Chocs." /></div>
                      <div class="text-lg font-bold font-mono" :class="(pnlResult.pct_impact ?? 0) >= 0 ? 'text-emerald-400' : 'text-red-400'">
                        {{ pnlResult.pct_impact != null ? pnlResult.pct_impact.toFixed(2) + '%' : '—' }}
                      </div>
                      <div class="text-[10px] text-slate-600">vs {{ formatNominal(pnlResult.nominal_total_eur) }} EUR</div>
                    </div>
                    <div class="stat-box">
                      <div class="text-xs text-slate-500 mb-1">Expliqués / ignorés / erreurs</div>
                      <div class="text-lg font-bold font-mono text-slate-200">
                        {{ pnlResult.contributions.length }} / {{ pnlResult.skipped.length }} / {{ pnlResult.errors.length }}
                      </div>
                    </div>
                  </div>

                  <div v-if="pnlResult.skipped.length || pnlResult.errors.length"
                    class="text-xs text-amber-400 bg-amber-950/30 border border-amber-900/50 rounded-lg px-3 py-2">
                    ⚠ Deal(s) non expliqués :
                    <span v-for="(s, i) in [...pnlResult.skipped, ...pnlResult.errors]" :key="s.deal_id">
                      {{ i > 0 ? ' · ' : '' }}{{ s.reference }} <span class="text-amber-600">({{ s.reason || s.error }})</span>
                    </span>
                  </div>

                  <!-- Waterfall agrégé -->
                  <div class="overflow-x-auto table-shell" tabindex="0" role="region">
                    <table class="w-full text-xs border-collapse max-w-xl">
                      <tbody>
                        <tr v-for="st in pnlResult.steps" :key="st.key" class="border-b border-slate-800/50">
                          <td class="py-1.5 pr-3 text-slate-300">{{ st.label }}</td>
                          <td class="py-1.5 text-right font-mono" :class="st.delta_eur >= 0 ? 'text-emerald-400' : 'text-red-400'">
                            {{ formatNominal(st.delta_eur) }} EUR
                          </td>
                        </tr>
                        <tr class="border-b border-slate-800/50">
                          <td class="py-1.5 pr-3 text-slate-500">Résidu
                            <HelpTip text="Ce qui échappe à la chaîne temps/spot/vol/corr (effet taux, croisements…) — doit rester petit devant le ΔMtM ; un résidu élevé signale un facteur non capturé." /></td>
                          <td class="py-1.5 text-right font-mono text-slate-400">{{ formatNominal(pnlResult.residual_eur) }} EUR</td>
                        </tr>
                        <tr class="border-b border-slate-800/50">
                          <td class="py-1.5 pr-3 text-slate-500">Flux détachés</td>
                          <td class="py-1.5 text-right font-mono text-slate-400">{{ formatNominal(pnlResult.flows_total_eur) }} EUR</td>
                        </tr>
                        <tr>
                          <td class="py-1.5 pr-3 font-bold text-slate-200">P&L total</td>
                          <td class="py-1.5 text-right font-mono font-bold" :class="pnlResult.pnl_total_eur >= 0 ? 'text-emerald-400' : 'text-red-400'">
                            {{ formatNominal(pnlResult.pnl_total_eur) }} EUR
                          </td>
                        </tr>
                      </tbody>
                    </table>
                  </div>

                  <!-- Contributions par deal -->
                  <div class="overflow-x-auto table-shell" tabindex="0" role="region">
                    <table class="w-full text-xs border-collapse">
                      <thead>
                        <tr class="border-b border-slate-700 text-slate-500">
                          <th class="text-left py-1.5 pr-3 font-semibold">Deal</th>
                          <th class="text-left py-1.5 pr-3 font-semibold">Période</th>
                          <th class="text-right py-1.5 pr-3 font-semibold num">Temps</th>
                          <th class="text-right py-1.5 pr-3 font-semibold num">Spot</th>
                          <th class="text-right py-1.5 pr-3 font-semibold num">Vol</th>
                          <th v-if="pnlHasCorr" class="text-right py-1.5 pr-3 font-semibold num">Corr</th>
                          <th class="text-right py-1.5 pr-3 font-semibold num">Flux</th>
                          <th class="text-right py-1.5 font-semibold num">P&L (EUR)</th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr v-for="c in pnlResult.contributions" :key="c.deal_id"
                          class="border-b border-slate-800/50 hover:bg-slate-800/20 transition-colors cursor-pointer"
                          @click="openDealDetail(c.deal_id)">
                          <td class="py-1.5 pr-3 font-mono font-semibold text-blue-400">{{ c.reference }}</td>
                          <td class="py-1.5 pr-3 text-slate-500 whitespace-nowrap">{{ c.date1 }} → {{ c.date2 }}</td>
                          <td class="py-1.5 pr-3 text-right font-mono text-slate-400">{{ formatNominal(c.steps_eur.temps ?? 0) }}</td>
                          <td class="py-1.5 pr-3 text-right font-mono text-slate-400">{{ formatNominal(c.steps_eur.spot ?? 0) }}</td>
                          <td class="py-1.5 pr-3 text-right font-mono text-slate-400">{{ formatNominal(c.steps_eur.vol ?? 0) }}</td>
                          <td v-if="pnlHasCorr" class="py-1.5 pr-3 text-right font-mono text-slate-400">{{ formatNominal(c.steps_eur.corr ?? 0) }}</td>
                          <td class="py-1.5 pr-3 text-right font-mono text-slate-400">{{ formatNominal(c.flows_eur) }}</td>
                          <td class="py-1.5 text-right font-mono" :class="c.pnl_eur >= 0 ? 'text-emerald-400' : 'text-red-400'">
                            {{ formatNominal(c.pnl_eur) }}
                          </td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                </template>
              </template>
            </template>

            <!-- ══ Onglet Portefeuilles : création, gestion, composition ══ -->
            <template v-else>

              <!-- Création & gestion -->
              <div class="flex flex-col gap-2">
                <div class="text-xs font-bold text-slate-400 uppercase tracking-wider">Création & gestion</div>
                <div class="flex gap-1.5 max-w-md">
                  <input v-model="newPortfolioName" type="text" placeholder="Nom du nouveau portefeuille…"
                    class="bg-slate-800 border border-slate-700 rounded px-2.5 py-1.5 text-xs text-slate-200 placeholder-slate-600 flex-1 min-w-0 focus:outline-none focus:border-blue-600"
                    @keyup.enter="createPortfolio" />
                  <button class="btn-primary text-xs px-3 py-1.5 shrink-0" :disabled="!newPortfolioName.trim()" @click="createPortfolio">＋ Créer</button>
                </div>
                <div class="flex flex-col gap-1 max-w-md">
                  <div v-for="p in pf.portfolios" :key="p.id"
                    class="flex items-center gap-2 px-2.5 py-1.5 rounded-lg border border-slate-800 group">
                    <span class="text-sm shrink-0">{{ p.is_default ? '⭐' : '📁' }}</span>
                    <span class="flex-1 truncate text-xs text-slate-300">{{ p.name }}</span>
                    <span class="text-[10px] font-mono px-1.5 py-0.5 rounded-full bg-slate-800 text-slate-400 shrink-0">{{ p.deal_count }} deal(s)</span>
                    <button class="text-slate-600 hover:text-slate-300 text-xs px-1 shrink-0"
                      title="Renommer" @click="renamePortfolio(p)">✎</button>
                    <button v-if="!p.is_default" class="text-slate-600 hover:text-red-400 text-xs px-1 shrink-0"
                      title="Supprimer (les deals sont déplacés vers le portefeuille par défaut)" @click="deletePortfolio(p)">✕</button>
                    <span v-else class="text-slate-700 text-xs px-1 shrink-0" title="Portefeuille par défaut — ne peut pas être supprimé, chaque deal doit toujours être surveillé">🔒</span>
                  </div>
                </div>
              </div>

              <!-- Composition de la sélection -->
              <div class="text-xs font-bold text-slate-400 uppercase tracking-wider pt-2 border-t border-slate-800">
                Composition — {{ pf.view === 'global' ? 'Tous portefeuilles' : pf.label }}
              </div>
              <div v-if="!pf.members.length" class="text-xs text-slate-500">
                Aucun deal actif dans cette sélection.
              </div>
              <div v-else class="overflow-x-auto table-shell" tabindex="0" role="region">
                <table class="w-full text-xs border-collapse">
                  <thead>
                    <tr class="border-b border-slate-700 text-slate-500">
                      <th class="text-left py-1.5 pr-3 font-semibold">Réf</th>
                      <th class="text-left py-1.5 pr-3 font-semibold">Contrepartie</th>
                      <th class="text-left py-1.5 pr-3 font-semibold">Type</th>
                      <th class="text-right py-1.5 pr-3 font-semibold num">Nominal</th>
                      <th class="text-left py-1.5 pr-3 font-semibold">Portefeuille
                        <HelpTip text="Changez le portefeuille d'un deal directement ici — la ré-affectation met à jour les agrégats Risque/P&L à la volée." /></th>
                      <th class="text-left py-1.5 font-semibold">Greeks calculés le
                        <HelpTip text="Date du dernier calcul de Greeks de ce deal (POST .../greeks) — c'est ce qui nourrit l'agrégat du sous-onglet Greeks. Cliquez la ligne pour ouvrir la fiche dans Booking." /></th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="d in pf.members" :key="d.id"
                      class="border-b border-slate-800/50 hover:bg-slate-800/20 transition-colors cursor-pointer"
                      @click="openDealDetail(d.id)">
                      <td class="py-1.5 pr-3 font-mono font-semibold text-blue-400">{{ d.reference }}</td>
                      <td class="py-1.5 pr-3 text-slate-300">{{ d.contrepartie }}</td>
                      <td class="py-1.5 pr-3 text-slate-500 text-[10px]">{{ d.product_type || '—' }}</td>
                      <td class="py-1.5 pr-3 text-right font-mono num text-slate-300">{{ formatNominal(d.nominal) }} {{ d.devise }}</td>
                      <td class="py-1.5 pr-3" @click.stop>
                        <select class="select text-[10px] py-0.5" :value="d.portfolio_id ? String(d.portfolio_id) : ''"
                          @change="pf.assignDeal(d.id, $event.target.value)">
                          <option v-for="p in pf.portfolios" :key="p.id" :value="String(p.id)">
                            {{ p.is_default ? '⭐ ' : '' }}{{ p.name }}
                          </option>
                        </select>
                      </td>
                      <td class="py-1.5 text-slate-500">
                        <span v-if="d.greeks_computed_at">{{ new Date(d.greeks_computed_at).toLocaleDateString('fr-FR') }}</span>
                        <span v-else class="text-amber-400">jamais calculé</span>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </template>

          </div>
        </div>

      </div>
    </main>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { useDealsStore } from '../stores/deals.js'
import { usePortfoliosStore, shockPresets, blankShockForm } from '../stores/portfolios.js'
import { apiFetch } from '../utils/api.js'
import HelpTip from '../components/HelpTip.vue'

const route = useRoute()
const router = useRouter()
const dealsStore = useDealsStore()
const pf = usePortfoliosStore()

// Le sous-menu Risk Management de l'accueil route vers /risk?tab=... — chaque
// entrée (Création de portefeuille / Chocs / Explication de P&L) atterrit
// directement sur sa section.
const VALID_TABS = ['portfolios', 'greeks', 'chocs', 'pnl']
const activeTab = ref(VALID_TABS.includes(route.query.tab) ? route.query.tab : 'portfolios')
watch(() => route.query.tab, (t) => {
  if (VALID_TABS.includes(t)) activeTab.value = t
})
const expandedUnderlying = ref(null)
const newPortfolioName = ref('')

function formatNominal(n) {
  return (n ?? 0).toLocaleString('fr-FR')
}

function sharePct(contribution, bucketTotal) {
  if (contribution == null || !bucketTotal) return '—'
  return `${Math.round((contribution / bucketTotal) * 100)}%`
}

// Deal drill-down lives in Booking — route there with the deal pre-expanded.
function openDealDetail(id) {
  router.push({ path: '/booking', query: { deal: id } })
}

// ── Gestion des portefeuilles ────────────────────────────────────────
async function createPortfolio() {
  const name = newPortfolioName.value.trim()
  if (!name) return
  await pf.create(name)
  newPortfolioName.value = ''
}

async function renamePortfolio(p) {
  const name = prompt('Nouveau nom du portefeuille :', p.name)
  if (!name || !name.trim() || name.trim() === p.name) return
  await pf.rename(p, name.trim())
}

async function deletePortfolio(p) {
  if (!confirm(`Supprimer "${p.name}" ? Les deals qu'il contient seront déplacés vers le portefeuille par défaut.`)) return
  await pf.remove(p)
}

// ── Recalcul des Greeks par deal (batch) ─────────────────────────────
const recomputing = ref(false)
const recomputeDone = ref(0)
const recomputeTotal = ref(0)

async function recomputePortfolio() {
  const memberIds = pf.members.map(d => d.id)
  if (!memberIds.length) return
  recomputing.value = true
  recomputeDone.value = 0
  recomputeTotal.value = memberIds.length
  try {
    for (const id of memberIds) {
      try {
        await apiFetch(`/api/deals/${id}/greeks`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ recalibrate: 'none' }),
        })
      } catch { /* one deal's failure shouldn't stop the batch */ }
      recomputeDone.value++
      await new Promise(r => setTimeout(r, 400))   // same pacing as Admin market-data's batch fetch
    }
  } finally {
    recomputing.value = false
    await dealsStore.loadDeals()
    await pf.loadRisk()
  }
}

// ── Chocs (portefeuille / global) ────────────────────────────────────
const shockForm = reactive(blankShockForm())
const shockLoading = ref(false)
const shockResult = ref(null)

function applyShockPreset(label) {
  const preset = shockPresets.find(p => p.label === label)
  if (!preset) return
  Object.assign(shockForm, {
    spot_shock_pct: preset.spot_shock_pct, vol_shock_pts: preset.vol_shock_pts,
    rate_shock_bp: preset.rate_shock_bp, corr_shock_pts: preset.corr_shock_pts,
  })
}

async function runPortfolioShock() {
  shockLoading.value = true
  shockResult.value = null
  try {
    const global = pf.view === 'global'
    shockResult.value = await pf.runShock(global ? 'global' : 'portfolio',
                                          global ? null : pf.view, shockForm)
  } catch (e) {
    shockResult.value = { error: e.message }
  } finally {
    shockLoading.value = false
  }
}

// ── P&L explain (portefeuille / global) ──────────────────────────────
const todayIso = new Date().toISOString().slice(0, 10)
const pnlD1 = ref('')                  // vide = origine de chaque deal
const pnlD2 = ref(todayIso)
const pnlLoading = ref(false)
const pnlResult = ref(null)

const pnlHasCorr = computed(() =>
  !!pnlResult.value?.steps?.some(st => st.key === 'corr'))

async function runPnl() {
  pnlLoading.value = true
  pnlResult.value = null
  try {
    pnlResult.value = await pf.runPnlExplain({
      date1: pnlD1.value || null,
      date2: pnlD2.value || todayIso,
      recalibrate: 'realized',
    })
  } catch (e) {
    pnlResult.value = { error: e.message }
  } finally {
    pnlLoading.value = false
  }
}

onMounted(() => {
  dealsStore.loadDeals()
  pf.load()
  pf.loadRisk()
  pf.loadShockHistory(pf.view === 'global' ? 'global' : 'portfolio',
                      pf.view === 'global' ? null : pf.view)
})
</script>
