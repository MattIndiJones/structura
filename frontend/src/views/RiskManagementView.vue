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
              <button @click="activeTab = 'contreparties'"
                :class="activeTab === 'contreparties' ? 'border-b-2 border-blue-500 text-slate-100' : 'text-slate-500 hover:text-slate-300'"
                class="px-4 py-2 text-xs font-medium transition-colors">
                🏦 Contreparties
              </button>
              <button @click="activeTab = 'chocs'"
                :class="activeTab === 'chocs' ? 'border-b-2 border-blue-500 text-slate-100' : 'text-slate-500 hover:text-slate-300'"
                class="px-4 py-2 text-xs font-medium transition-colors">
                ⚡ Chocs
              </button>
              <button @click="activeTab = 'var'"
                :class="activeTab === 'var' ? 'border-b-2 border-blue-500 text-slate-100' : 'text-slate-500 hover:text-slate-300'"
                class="px-4 py-2 text-xs font-medium transition-colors">
                📉 VaR
              </button>
              <button @click="activeTab = 'pnl'"
                :class="activeTab === 'pnl' ? 'border-b-2 border-blue-500 text-slate-100' : 'text-slate-500 hover:text-slate-300'"
                class="px-4 py-2 text-xs font-medium transition-colors">
                P&L
              </button>
              <button @click="activeTab = 'barrieres'"
                :class="activeTab === 'barrieres' ? 'border-b-2 border-blue-500 text-slate-100' : 'text-slate-500 hover:text-slate-300'"
                class="px-4 py-2 text-xs font-medium transition-colors">
                📍 Barrières
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

                    <template v-if="Object.keys(pf.risk.corr_pairs || {}).length">
                      <div class="text-xs font-bold text-slate-400 uppercase tracking-wider">
                        Corrélation par paire
                        <HelpTip width="w-72" text="Sensibilité du book à une hausse de corrélation entre deux sous-jacents (cross-gamma), uniquement pour les paires qui apparaissent ensemble dans au moins un deal worst-of/basket — jamais visible deal par deal, un book peut être concentré sur une paire sans qu'aucun deal ne la montre grosse à lui seul." />
                      </div>
                      <div class="overflow-x-auto table-shell" tabindex="0" role="region">
                        <table class="w-full text-xs border-collapse">
                          <thead>
                            <tr class="border-b border-slate-700 text-slate-500">
                              <th class="text-left py-1.5 pr-3 font-semibold">Paire de sous-jacents</th>
                              <th class="text-right py-1.5 font-semibold">Corr (EUR / 1pt)
                                <HelpTip align="right" text="Σ(sensibilité corrélation du deal × nominal × taux de change), rescalée pour lire un impact par 1 point de corrélation — même convention que corr_shock_pts dans l'onglet Chocs (le moteur calcule la dérivée brute par 100pts, d'où le ×0.01)." /></th>
                            </tr>
                          </thead>
                          <tbody>
                            <template v-for="(g, key) in pf.risk.corr_pairs" :key="key">
                              <tr class="border-b border-slate-800/50 hover:bg-slate-800/20 transition-colors cursor-pointer"
                                @click="expandedCorrPair = expandedCorrPair === key ? null : key">
                                <td class="py-1.5 pr-3 text-slate-300 font-semibold">
                                  <span class="text-slate-600 mr-1">{{ expandedCorrPair === key ? '▾' : '▸' }}</span>{{ g.label }}
                                </td>
                                <td class="py-1.5 text-right font-mono" :class="g.corr_eur >= 0 ? 'text-emerald-400' : 'text-red-400'">{{ formatNominal(g.corr_eur) }}</td>
                              </tr>
                              <tr v-if="expandedCorrPair === key" class="bg-slate-900/60">
                                <td colspan="2" class="py-2 pl-6 pr-3">
                                  <table class="w-full text-[11px] border-collapse">
                                    <thead>
                                      <tr class="text-slate-600">
                                        <th class="text-left py-1 pr-3 font-medium">Deal</th>
                                        <th class="text-right py-1 font-medium">Corr (EUR / 1pt)</th>
                                      </tr>
                                    </thead>
                                    <tbody>
                                      <tr v-for="c in g.contributions" :key="c.deal_id"
                                        class="hover:bg-slate-800/40 cursor-pointer" @click.stop="openDealDetail(c.deal_id)">
                                        <td class="py-1 pr-3 font-mono font-semibold text-blue-400">{{ c.reference }}</td>
                                        <td class="py-1 text-right font-mono text-slate-400">{{ formatNominal(c.corr_eur) }}</td>
                                      </tr>
                                    </tbody>
                                  </table>
                                </td>
                              </tr>
                            </template>
                          </tbody>
                        </table>
                      </div>
                    </template>

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

            <!-- ══ Onglet Contreparties : concentration & limites ═ -->
            <template v-else-if="activeTab === 'contreparties'">
                <div class="text-[10px] text-slate-500 -mt-1">
                  Nominal (converti en EUR) par contrepartie sur les deals actifs de cette sélection — pas de recalcul Monte Carlo, lecture directe.
                  <HelpTip text="Base nominal, pas MtM courant : une note structurée est une créance non sécurisée sur l'émetteur pour le remboursement promis — c'est le nominal qui est en jeu en cas de défaut, pas la valeur de marché du jour." />
                </div>

                <div v-if="pf.exposureLoading" class="text-xs text-slate-500">Chargement…</div>

                <template v-else-if="pf.exposure">
                  <div v-if="!pf.exposure.by_counterparty.length" class="text-xs text-slate-500">
                    Aucun deal actif dans cette sélection.
                  </div>

                  <template v-else>
                    <div class="grid grid-cols-2 sm:grid-cols-4 gap-3">
                      <div class="stat-box">
                        <div class="text-xs text-slate-500 mb-1">Nominal total
                          <HelpTip text="Somme des nominaux de tous les deals actifs de cette sélection, convertis en EUR." /></div>
                        <div class="text-lg font-bold font-mono text-slate-200">{{ formatNominal(pf.exposure.nominal_total_eur) }}</div>
                        <div class="text-[10px] text-slate-600">EUR</div>
                      </div>
                      <div class="stat-box">
                        <div class="text-xs text-slate-500 mb-1">Contreparties
                          <HelpTip text="Nombre de contreparties distinctes portant au moins un deal actif de cette sélection." /></div>
                        <div class="text-lg font-bold font-mono text-slate-200">{{ pf.exposure.by_counterparty.length }}</div>
                      </div>
                      <div class="stat-box">
                        <div class="text-xs text-slate-500 mb-1">N effectif (1/HHI)
                          <HelpTip text="Indice de concentration Herfindahl-Hirschman (Σ part²) retourné en 'nombre de contreparties équivalent' — un book réparti sur 10 banques à parts égales donne 10 ; un book concentré sur 2-3 banques donne un chiffre bas même s'il y a nominalement plus de 10 contreparties au total." /></div>
                        <div class="text-lg font-bold font-mono"
                          :class="pf.exposure.effective_n != null && pf.exposure.effective_n < 3 ? 'text-amber-400' : 'text-slate-200'">
                          {{ pf.exposure.effective_n ?? '—' }}
                        </div>
                      </div>
                      <div class="stat-box">
                        <div class="text-xs text-slate-500 mb-1">Top 3 contreparties
                          <HelpTip text="Part du nominal total portée par les 3 plus grosses contreparties de cette sélection." /></div>
                        <div class="text-lg font-bold font-mono text-slate-200">
                          {{ pf.exposure.top3_pct != null ? Math.round(pf.exposure.top3_pct * 100) + '%' : '—' }}
                        </div>
                      </div>
                    </div>

                    <div class="overflow-x-auto table-shell" tabindex="0" role="region">
                      <table class="w-full text-xs border-collapse">
                        <thead>
                          <tr class="border-b border-slate-700 text-slate-500">
                            <th class="text-left py-1.5 pr-3 font-semibold">Contrepartie</th>
                            <th class="text-right py-1.5 pr-3 font-semibold">Nominal (EUR)</th>
                            <th class="text-right py-1.5 pr-3 font-semibold">% du book</th>
                            <th class="text-right py-1.5 pr-3 font-semibold">Deals</th>
                            <th class="text-right py-1.5 pr-3 font-semibold">Limite (EUR)
                              <HelpTip align="right" text="Configurée par un admin dans Administration → Contreparties. Vide = pas de limite définie, jamais de dépassement signalé." /></th>
                            <th class="text-left py-1.5 font-semibold"></th>
                          </tr>
                        </thead>
                        <tbody>
                          <template v-for="c in pf.exposure.by_counterparty" :key="c.contrepartie">
                            <tr class="border-b border-slate-800/50 hover:bg-slate-800/20 transition-colors cursor-pointer"
                              @click="expandedCounterparty = expandedCounterparty === c.contrepartie ? null : c.contrepartie">
                              <td class="py-1.5 pr-3 text-slate-300 font-semibold">
                                <span class="text-slate-600 mr-1">{{ expandedCounterparty === c.contrepartie ? '▾' : '▸' }}</span>{{ c.contrepartie }}
                              </td>
                              <td class="py-1.5 pr-3 text-right font-mono text-slate-200">{{ formatNominal(c.nominal_eur) }}</td>
                              <td class="py-1.5 pr-3 text-right font-mono text-slate-400">{{ c.pct_of_book != null ? Math.round(c.pct_of_book * 100) + '%' : '—' }}</td>
                              <td class="py-1.5 pr-3 text-right font-mono text-slate-400">{{ c.deal_count }}</td>
                              <td class="py-1.5 pr-3 text-right font-mono" :class="c.limit_breached ? 'text-red-400 font-bold' : 'text-slate-500'">
                                {{ c.limit_eur != null ? formatNominal(c.limit_eur) : '—' }}
                              </td>
                              <td class="py-1.5 text-right">
                                <span v-if="c.limit_breached" class="text-[10px] text-red-400 bg-red-950/40 border border-red-900/50 rounded-full px-2 py-0.5">⚠ limite dépassée</span>
                              </td>
                            </tr>
                            <tr v-if="expandedCounterparty === c.contrepartie" class="bg-slate-900/60">
                              <td colspan="6" class="py-2 pl-6 pr-3">
                                <table class="w-full text-[11px] border-collapse">
                                  <thead>
                                    <tr class="text-slate-600">
                                      <th class="text-left py-1 pr-3 font-medium">Deal</th>
                                      <th class="text-right py-1 font-medium">Nominal (EUR)</th>
                                    </tr>
                                  </thead>
                                  <tbody>
                                    <tr v-for="dl in c.deals" :key="dl.id"
                                      class="hover:bg-slate-800/40 cursor-pointer" @click.stop="openDealDetail(dl.id)">
                                      <td class="py-1 pr-3 font-mono font-semibold text-blue-400">{{ dl.reference }}</td>
                                      <td class="py-1 text-right font-mono text-slate-400">{{ formatNominal(dl.nominal_eur) }}</td>
                                    </tr>
                                  </tbody>
                                </table>
                              </td>
                            </tr>
                          </template>
                        </tbody>
                      </table>
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
                        <td class="py-1 pr-3 text-slate-500 whitespace-nowrap">{{ formatDateTime(h.created_at) }}</td>
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

            <!-- ══ Onglet VaR/ES ═════════════════════════════════ -->
            <template v-else-if="activeTab === 'var'">
                <div class="text-sm font-bold text-slate-100">
                  📉 VaR/ES — {{ pf.view === 'global' ? 'Tous portefeuilles' : pf.label }}
                  <HelpTip width="w-80" text="Rejoue le book sous des centaines de scénarios de marché (historique ET paramétrique, affichés côte à côte, jamais fusionnés en un seul chiffre) via le module de calcul générique — asynchrone : rien ne s'exécute tant que le worker de calcul n'est pas démarré (voir l'avertissement ci-dessous)." />
                </div>

                <div class="text-xs text-amber-400 bg-amber-950/30 border border-amber-900/50 rounded-lg px-3 py-2">
                  ⚠ Nécessite que <code class="font-mono">backend\scripts\run_compute_worker.py</code> tourne en parallèle du serveur — sinon l'étude reste "en attente" indéfiniment.
                </div>

                <div class="flex flex-wrap gap-3 items-end">
                  <label class="flex flex-col gap-0.5 text-[10px] text-slate-500">Méthode
                    <select v-model="varForm.method" class="select text-xs py-1 w-32">
                      <option value="both">Les deux</option>
                      <option value="historical">Historique</option>
                      <option value="parametric">Paramétrique</option>
                    </select>
                  </label>
                  <label class="flex flex-col gap-0.5 text-[10px] text-slate-500">Confiance
                    <select v-model.number="varForm.confidence" class="select text-xs py-1 w-24">
                      <option :value="0.95">95%</option>
                      <option :value="0.99">99%</option>
                      <option :value="0.90">90%</option>
                    </select>
                  </label>
                  <label class="flex flex-col gap-0.5 text-[10px] text-slate-500">Horizon (j)
                    <input v-model.number="varForm.horizon_days" type="number" min="1" class="input text-xs py-1 w-20" />
                  </label>
                  <label class="flex flex-col gap-0.5 text-[10px] text-slate-500">Lookback (ans)
                    <input v-model.number="varForm.lookback_years" type="number" min="0.5" step="0.5" class="input text-xs py-1 w-20" />
                  </label>
                  <button class="text-[10px] text-slate-500 hover:text-slate-300 underline self-end pb-1"
                    @click="varAdvancedOpen = !varAdvancedOpen">
                    {{ varAdvancedOpen ? 'masquer' : 'options avancées' }}
                  </button>
                  <button class="btn-primary text-xs px-4 py-1.5 self-end" :disabled="pf.varLaunching || pf.varPolling"
                    @click="launchVarStudy">
                    <span v-if="pf.varLaunching || pf.varPolling"
                      class="w-3 h-3 border-2 border-white border-t-transparent rounded-full animate-spin inline-block mr-1"></span>
                    Lancer l'étude
                  </button>
                </div>

                <div v-if="varLaunchError" class="text-xs text-red-400 bg-red-950/30 border border-red-900/50 rounded-lg px-3 py-2">
                  ⚠ {{ varLaunchError }}
                </div>

                <div v-if="varAdvancedOpen" class="flex flex-wrap gap-3">
                  <label class="flex flex-col gap-0.5 text-[10px] text-slate-500">Tirages paramétriques
                    <input v-model.number="varForm.n_parametric" type="number" min="100" step="100" class="input text-xs py-1 w-28" />
                  </label>
                  <label class="flex flex-col gap-0.5 text-[10px] text-slate-500">Paths / scénario
                    <HelpTip text="Moins de précision par scénario qu'un choc unique (défaut du panneau Chocs : 20000) — le bruit se moyenne sur des centaines de scénarios, contrairement à un choc isolé où on veut la précision max." />
                    <input v-model.number="varForm.n_paths_per_scenario" type="number" min="500" step="500" class="input text-xs py-1 w-28" />
                  </label>
                  <label class="flex flex-col gap-0.5 text-[10px] text-slate-500">Workers parallèles
                    <input v-model.number="varForm.max_workers" type="number" min="1" max="16" class="input text-xs py-1 w-20" />
                  </label>
                </div>

                <template v-if="pf.varStudy">
                  <div v-if="pf.varStudy.status === 'queued' || pf.varStudy.status === 'running'"
                    class="flex flex-col gap-1.5">
                    <div class="text-xs text-slate-400">
                      {{ pf.varStudy.status === 'queued' ? 'En file d\'attente…' : 'En cours…' }}
                      {{ pf.varStudy.completed_jobs + pf.varStudy.failed_jobs }} / {{ pf.varStudy.total_jobs }} scénario(s)
                    </div>
                    <div class="w-full h-1.5 bg-slate-800 rounded-full overflow-hidden">
                      <div class="h-full bg-blue-500 transition-all"
                        :style="{ width: (pf.varStudy.total_jobs ? (pf.varStudy.completed_jobs + pf.varStudy.failed_jobs) / pf.varStudy.total_jobs * 100 : 0) + '%' }"></div>
                    </div>
                  </div>

                  <template v-else>
                    <div v-if="pf.varStudy.failed_jobs" class="text-xs text-amber-400 bg-amber-950/30 border border-amber-900/50 rounded-lg px-3 py-2">
                      ⚠ {{ pf.varStudy.failed_jobs }} / {{ pf.varStudy.total_jobs }} scénario(s) en erreur — chiffres calculés sur les autres.
                    </div>

                    <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
                      <div v-for="m in ['historical', 'parametric']" :key="m" v-show="pf.varStudy.result?.[m]"
                        class="card flex flex-col gap-2">
                        <div class="text-xs font-bold text-slate-300 uppercase tracking-wider">
                          {{ m === 'historical' ? 'Historique' : 'Paramétrique' }}
                          <span class="text-slate-600 font-normal normal-case">— {{ pf.varStudy.result?.[m]?.n_scenarios }} scénario(s)</span>
                        </div>
                        <div class="grid grid-cols-2 gap-2">
                          <div class="stat-box">
                            <div class="text-xs text-slate-500 mb-1">VaR {{ Math.round((pf.varStudy.params.confidence ?? 0.95) * 100) }}%</div>
                            <div class="text-lg font-bold font-mono text-red-400">{{ formatNominal(pf.varStudy.result?.[m]?.var_eur) }}</div>
                            <div class="text-[10px] text-slate-600">EUR</div>
                          </div>
                          <div class="stat-box">
                            <div class="text-xs text-slate-500 mb-1">Expected Shortfall
                              <HelpTip text="Perte moyenne au-delà du seuil VaR — la queue au-delà du pire (confiance)%, pas juste le point de coupure." /></div>
                            <div class="text-lg font-bold font-mono text-red-400">{{ formatNominal(pf.varStudy.result?.[m]?.es_eur) }}</div>
                            <div class="text-[10px] text-slate-600">EUR</div>
                          </div>
                        </div>
                        <div class="text-[10px] text-slate-500 font-mono flex flex-wrap gap-x-3">
                          <span v-for="(v, p) in pf.varStudy.result?.[m]?.distribution_summary" :key="p">{{ p }}: {{ formatNominal(v) }}</span>
                        </div>
                      </div>
                    </div>

                    <div v-if="pf.varStudy.result?.worst_scenarios?.length" class="overflow-x-auto table-shell" tabindex="0" role="region">
                      <div class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-1 mt-1">Pires scénarios</div>
                      <table class="w-full text-xs border-collapse">
                        <thead>
                          <tr class="border-b border-slate-700 text-slate-500">
                            <th class="text-left py-1.5 pr-3 font-semibold">Scénario</th>
                            <th class="text-left py-1.5 pr-3 font-semibold">Méthode</th>
                            <th class="text-right py-1.5 font-semibold">ΔMtM (EUR)</th>
                          </tr>
                        </thead>
                        <tbody>
                          <tr v-for="w in pf.varStudy.result.worst_scenarios" :key="w.scenario_key"
                            class="border-b border-slate-800/50">
                            <td class="py-1 pr-3 font-mono text-slate-300">{{ w.scenario_key }}</td>
                            <td class="py-1 pr-3 text-slate-500">{{ w.method === 'historical' ? 'Historique' : 'Paramétrique' }}</td>
                            <td class="py-1 text-right font-mono text-red-400">{{ formatNominal(w.delta_eur) }}</td>
                          </tr>
                        </tbody>
                      </table>
                    </div>

                    <div v-if="varDealsSkipped.length" class="text-xs text-slate-500">
                      Deals ignorés au lancement : {{ varDealsSkipped.map(d => d.reference).join(', ') }}
                    </div>
                  </template>
                </template>

                <!-- Études passées -->
                <div class="pt-2 border-t border-slate-800">
                  <div class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-2">Études passées</div>
                  <div v-if="!pf.varHistory.length" class="text-xs text-slate-500">Aucune étude VaR lancée pour l'instant.</div>
                  <div v-else class="overflow-x-auto table-shell" tabindex="0" role="region">
                    <table class="w-full text-xs border-collapse">
                      <tbody>
                        <tr v-for="b in pf.varHistory" :key="b.id" class="border-b border-slate-800/50 hover:bg-slate-800/20 cursor-pointer"
                          @click="pf.openVarBatch(b.id)">
                          <td class="py-1 pr-3 text-slate-500 whitespace-nowrap">{{ formatDateTime(b.created_at) }}</td>
                          <td class="py-1 pr-3 text-slate-300">{{ b.label }}</td>
                          <td class="py-1 pr-3 text-slate-500">{{ b.completed_jobs }}/{{ b.total_jobs }}</td>
                          <td class="py-1 text-right"
                            :class="{ completed: 'text-emerald-500', completed_with_failures: 'text-amber-500', failed: 'text-red-500', running: 'text-blue-400', queued: 'text-slate-500' }[b.status]">
                            {{ b.status }}
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

            <!-- ══ Onglet Barrières : proximité aux barrières ═══════ -->
            <template v-else-if="activeTab === 'barrieres'">
              <div class="flex items-center gap-3 flex-wrap">
                <div class="text-sm font-bold text-slate-100">
                  📍 Proximité aux barrières — {{ pf.view === 'global' ? 'Tous portefeuilles' : pf.label }}
                  <HelpTip width="w-80" text="Classe tous les deals actifs de la sélection par écart entre le worst-of actuel et leur prochaine barrière (autocall, KI) détectée dans le script — pour repérer en un coup d'œil ce qui mérite un suivi cette semaine. Réutilise la même détection que la Surveillance de Booking (convention PARAM M_)." />
                </div>
                <button class="btn-secondary text-xs px-3 py-1.5 ml-auto" :disabled="pf.barriersLoading || !pf.members.length"
                  @click="pf.loadBarriers">
                  <span v-if="pf.barriersLoading"
                    class="w-3 h-3 border-2 border-slate-400 border-t-transparent rounded-full animate-spin inline-block mr-1"></span>
                  🔄 Actualiser
                </button>
              </div>

              <div v-if="!pf.barriers && !pf.barriersLoading" class="text-xs text-slate-500 text-center py-8">
                <button class="btn-primary text-xs px-4 py-1.5" :disabled="!pf.members.length" @click="pf.loadBarriers">
                  ▶ Charger la proximité aux barrières
                </button>
                <div v-if="!pf.members.length" class="mt-2 text-slate-600">Aucun deal actif dans cette sélection.</div>
              </div>

              <div v-else-if="pf.barriersLoading" class="text-xs text-slate-500 text-center py-8">
                Calcul en cours — un appel de marché par deal, cela peut prendre quelques secondes…
              </div>

              <template v-else-if="pf.barriers">
                <div class="grid grid-cols-2 sm:grid-cols-3 gap-3">
                  <div class="stat-box">
                    <div class="text-xs text-slate-500 mb-1">Critique — ≤ 5 pts (KI)</div>
                    <div class="text-lg font-bold font-mono text-red-400">{{ pf.barriers.counts.critique }}</div>
                    <div class="text-[10px] text-slate-600">deal(s)</div>
                  </div>
                  <div class="stat-box">
                    <div class="text-xs text-slate-500 mb-1">Attention — zone intermédiaire</div>
                    <div class="text-lg font-bold font-mono text-amber-400">{{ pf.barriers.counts.attention }}</div>
                    <div class="text-[10px] text-slate-600">deal(s)</div>
                  </div>
                  <div class="stat-box">
                    <div class="text-xs text-slate-500 mb-1">Sous contrôle</div>
                    <div class="text-lg font-bold font-mono text-emerald-400">{{ pf.barriers.counts.ok }}</div>
                    <div class="text-[10px] text-slate-600">deal(s)</div>
                  </div>
                </div>

                <div v-if="pf.barriers.errors.length"
                  class="text-xs text-amber-400 bg-amber-950/30 border border-amber-900/50 rounded-lg px-3 py-2">
                  ⚠ Deal(s) non évalués (erreur marché) :
                  <span v-for="(e, i) in pf.barriers.errors" :key="e.deal_id">
                    {{ i > 0 ? ' · ' : '' }}{{ e.reference }} <span class="text-amber-600">({{ e.error }})</span>
                  </span>
                </div>

                <div v-if="!pf.barriers.rows.length" class="text-xs text-slate-500">
                  Aucune barrière PARAM (convention M_) détectée sur les deals actifs de cette sélection.
                </div>

                <div v-else class="overflow-x-auto table-shell" tabindex="0" role="region">
                  <table class="w-full text-xs border-collapse">
                    <thead>
                      <tr class="border-b border-slate-700 text-slate-500">
                        <th class="text-left py-1.5 pr-3 font-semibold">Deal</th>
                        <th class="text-left py-1.5 pr-3 font-semibold">Sous-jacent</th>
                        <th class="text-left py-1.5 pr-3 font-semibold">Prochaine obs</th>
                        <th class="text-right py-1.5 pr-3 font-semibold num">WOF</th>
                        <th class="text-left py-1.5 pr-3 font-semibold">Barrières</th>
                        <th class="text-right py-1.5 font-semibold num">Nominal</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="w in pf.barriers.rows" :key="w.deal_id"
                        class="border-b border-slate-800/50 hover:bg-slate-800/20 transition-colors cursor-pointer"
                        @click="openDealDetail(w.deal_id)">
                        <td class="py-2 pr-3 font-mono font-semibold text-blue-400 whitespace-nowrap">{{ w.reference }}</td>
                        <td class="py-2 pr-3 text-slate-400 whitespace-nowrap">
                          {{ (w.underlyings || []).map(u => u.ticker || u.name).join(' / ') || '—' }}
                        </td>
                        <td class="py-2 pr-3 font-mono whitespace-nowrap">
                          <template v-if="w.next_event">
                            <span class="text-slate-300">{{ w.next_event.date }}</span>
                            <span class="ml-1.5 text-[10px]" :class="w.days_to_next <= 30 ? 'text-amber-400 font-semibold' : 'text-slate-500'">
                              J−{{ w.days_to_next }}
                            </span>
                          </template>
                          <span v-else class="text-slate-600">—</span>
                        </td>
                        <td class="py-2 pr-3 font-mono num whitespace-nowrap text-right">
                          <template v-if="w.wof != null">
                            <span :class="w.wof >= 1 ? 'text-emerald-400' : 'text-red-400'">{{ formatPercent(w.wof * 100, 1) }}</span>
                          </template>
                          <span v-else class="text-slate-600" title="S₀ manquant">n/d</span>
                        </td>
                        <td class="py-2 pr-3">
                          <div class="flex gap-1.5 flex-wrap">
                            <span v-for="b in w.barriers" :key="b.name"
                              :class="barrierChipClass(b)"
                              class="px-1.5 py-0.5 rounded text-[10px] font-mono font-semibold whitespace-nowrap">
                              {{ b.name }} {{ formatPercent(b.level * 100, 0) }}<template v-if="b.observable && b.observable !== 'WOF'"> vs {{ b.observable }}</template> · {{ barrierGapLabel(b) }}
                            </span>
                          </div>
                        </td>
                        <td class="py-2 text-right font-mono num text-slate-300 whitespace-nowrap">{{ formatNominal(w.nominal) }} {{ w.devise }}</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
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
                      title="Renommer" aria-label="Renommer le portefeuille" @click="renamePortfolio(p)">✎</button>
                    <button v-if="!p.is_default" class="text-slate-600 hover:text-red-400 text-xs px-1 shrink-0"
                      title="Supprimer (les deals sont déplacés vers le portefeuille par défaut)"
                      aria-label="Supprimer le portefeuille" @click="deletePortfolio(p)">✕</button>
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
import { ref, reactive, computed, onMounted, onUnmounted, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { useDealsStore } from '../stores/deals.js'
import { usePortfoliosStore, shockPresets, blankShockForm, blankVarForm } from '../stores/portfolios.js'
import { apiFetch } from '../utils/api.js'
import { formatInt, formatDateTime, formatPercent } from '../utils/format.js'
import { barrierChipClass, barrierGapLabel } from '../utils/barriers.js'
import HelpTip from '../components/HelpTip.vue'

const route = useRoute()
const router = useRouter()
const dealsStore = useDealsStore()
const pf = usePortfoliosStore()

// Le sous-menu Risk Management de l'accueil route vers /risk?tab=... — chaque
// entrée (Création de portefeuille / Chocs / Explication de P&L) atterrit
// directement sur sa section.
const VALID_TABS = ['portfolios', 'greeks', 'contreparties', 'chocs', 'var', 'pnl', 'barrieres']
const activeTab = ref(VALID_TABS.includes(route.query.tab) ? route.query.tab : 'portfolios')
watch(() => route.query.tab, (t) => {
  if (VALID_TABS.includes(t)) activeTab.value = t
})

// Barrières is lazy (see stores/portfolios.js loadBarriers doc) — fetch once
// when the tab is first opened, not on every portfolio switch.
watch(activeTab, (t) => {
  if (t === 'barrieres' && !pf.barriers && !pf.barriersLoading) pf.loadBarriers()
})
const expandedUnderlying = ref(null)
const expandedCorrPair = ref(null)
const expandedCounterparty = ref(null)
const newPortfolioName = ref('')

const formatNominal = formatInt

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

// ── VaR/ES study (portefeuille / global) ─────────────────────────────
const varForm = reactive(blankVarForm())
const varAdvancedOpen = ref(false)
// deals_skipped only comes back on the launch (POST) response, never on a
// later poll of GET /var/{id} — kept in its own ref (rather than stashed
// onto pf.varStudy) since the poll loop overwrites pf.varStudy.value
// asynchronously and could otherwise race with this assignment.
const varDealsSkipped = ref([])
const varLaunchError = ref('')

async function launchVarStudy() {
  varDealsSkipped.value = []
  varLaunchError.value = ''
  try {
    const launched = await pf.launchVar(varForm)
    varDealsSkipped.value = launched.deals_skipped || []
  } catch (e) {
    varLaunchError.value = e.message
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
  pf.loadExposure()
  pf.loadVarHistory()
  pf.loadShockHistory(pf.view === 'global' ? 'global' : 'portfolio',
                      pf.view === 'global' ? null : pf.view)
})

// A VaR study's poll loop uses setTimeout, not a Vue-managed watcher — must
// be stopped explicitly on unmount or it keeps polling (and holds a
// reference to this closed-over component) after the user navigates away.
onUnmounted(() => {
  pf.stopVarPolling()
})
</script>
