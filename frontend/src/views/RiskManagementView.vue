<template>
  <div class="risk-management-view flex-1 flex flex-col min-h-0 text-slate-100">

    <main class="flex-1 overflow-y-auto p-6">
      <div class="max-w-[1600px] mx-auto flex flex-col gap-3">

        <div class="page-header">
          <div class="flex items-center gap-3">
            <BackLink :fallback="{ path: '/', query: { category: 'risk_management' } }" />
            <h1 class="page-title">Risk Management</h1>
          </div>
        </div>

        <div class="flex gap-4 flex-wrap items-start">

          <!-- ── Sélection du portefeuille actif (partagée par tous les onglets) ── -->
          <div class="card flex flex-col gap-1 w-full sm:w-64 shrink-0">
            <div class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-1 px-0.5">Portefeuille actif</div>
            <button class="flex items-center gap-2 text-left px-2.5 py-2 rounded-lg text-xs font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              :class="pf.view === 'global' ? 'bg-blue-600/15 text-blue-300 ring-1 ring-blue-600/40' : 'text-slate-400 hover:bg-slate-800/60'"
              :disabled="calculationActive"
              @click="pf.selectView('global')">
              <span class="text-sm">📊</span>
              <span class="flex-1">Tous portefeuilles</span>
              <span class="text-[10px] font-mono px-1.5 py-0.5 rounded-full bg-slate-800 text-slate-400">{{ pf.activeDealsCount }}</span>
            </button>
            <div class="border-t border-slate-800 my-1"></div>
            <button v-for="p in pf.portfolios" :key="p.id"
              class="flex items-center gap-2 text-left px-2.5 py-2 rounded-lg text-xs font-medium transition-colors min-w-0 disabled:opacity-50 disabled:cursor-not-allowed"
              :class="pf.view === p.id ? 'bg-blue-600/15 text-blue-300 ring-1 ring-blue-600/40' : 'text-slate-400 hover:bg-slate-800/60'"
              :disabled="calculationActive"
              @click="pf.selectView(p.id)">
              <span class="text-sm shrink-0">📁</span>
              <span class="flex-1 min-w-0">
                <span class="block truncate">{{ p.name }}</span>
                <span v-if="authStore.isAdmin" class="block truncate text-[9px] text-slate-600">
                  {{ p.owner_username }}{{ p.owner_entity_name ? ` · ${p.owner_entity_name}` : '' }}
                </span>
              </span>
              <span class="text-[10px] font-mono px-1.5 py-0.5 rounded-full bg-slate-800 text-slate-400 shrink-0">{{ p.deal_count }}</span>
            </button>
          </div>

          <!-- ── Panneau principal ──────────────────────────────── -->
          <div class="card kpi-tile flex-1 min-w-0 flex flex-col gap-3">
            <div class="flex items-center gap-3 flex-wrap">
              <div class="text-sm font-bold text-slate-100">
                {{ pf.view === 'global' ? '📊 Tous portefeuilles' : `📁 ${pf.label}` }}
              </div>
              <label class="ml-auto flex items-center gap-2 text-[10px] text-slate-400">
                Date des Greeks
                <input v-model="pf.valuationDate" type="date" :max="todayIso"
                  :disabled="calculationActive" class="input text-xs py-1 w-36" />
              </label>
              <button class="btn-secondary text-xs px-3 py-1.5" :disabled="calculationActive || !pf.riskMembers.length"
                @click="recomputePortfolio">
                <span v-if="recomputing"
                  class="w-3 h-3 border-2 border-slate-400 border-t-transparent rounded-full animate-spin inline-block mr-1"></span>
                🔄 Recalculer{{ recomputing ? ` (${recomputeDone}/${recomputeTotal})` : '' }}
              </button>
            </div>

            <div v-if="calculationProgress"
              class="rounded-lg border border-blue-900/60 bg-blue-950/20 px-3 py-2">
              <div class="flex items-center gap-2 text-[10px] text-slate-400 mb-1.5">
                <span class="font-semibold text-blue-300">{{ calculationProgress.label }}</span>
                <span v-if="calculationProgress.total" class="font-mono">
                  {{ calculationProgress.completed }}/{{ calculationProgress.total }}
                </span>
                <span v-else>calcul en cours</span>
                <span class="ml-auto font-mono">{{ formatElapsed(calculationElapsed) }}</span>
              </div>
              <div class="h-1.5 rounded-full bg-slate-800 overflow-hidden">
                <div class="h-full rounded-full bg-blue-500 transition-all duration-300"
                  :class="calculationProgress.total ? '' : 'animate-pulse'"
                  :style="{ width: calculationProgress.total ? `${calculationProgress.percent}%` : '45%' }"></div>
              </div>
            </div>

            <AlertMessage v-if="recomputeNotice" :kind="recomputeFailures.length ? 'warning' : 'success'"
              dismissible @dismiss="recomputeNotice = ''">
              {{ recomputeNotice }}
            </AlertMessage>

            <!-- Menu du module : gestion / analyses (d'autres viendront) -->
            <div class="flex border-b border-slate-800 -mb-1">
              <button @click="activeTab = 'portfolios'"
                :class="activeTab === 'portfolios' ? 'border-b-2 border-blue-500 text-slate-100' : 'text-slate-500 hover:text-slate-300'"
                class="px-4 py-2 text-xs font-medium transition-colors">
                Portefeuilles ({{ pf.allMembers.length }})
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
              <button @click="activeTab = 'smile'"
                :class="activeTab === 'smile' ? 'border-b-2 border-blue-500 text-slate-100' : 'text-slate-500 hover:text-slate-300'"
                class="px-4 py-2 text-xs font-medium transition-colors">
                〰 Smile
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
                  Somme des Greeks calculés à la date d’analyse (nominal × sensibilité % × taux de change vers EUR), regroupés par sous-jacent. Créer un portefeuille ne lance aucun calcul ; le générateur UAT peut en revanche calculer les Greeks au booking lorsque l’option « Calculer les Greeks pour Risk » est cochée.
                  <HelpTip text="La lecture de cet onglet ne lance aucun Monte Carlo. Recalculer produit et conserve un calcul daté pour chaque deal actif à la date choisie." />
                </div>

                <div v-if="pf.riskLoading" class="text-xs text-slate-500">Chargement…</div>

                <template v-else-if="pf.risk">
                  <!-- Devise non convertible : la position est ABSENTE de tous les
                       totaux ci-dessous (le backend refuse d'inventer un taux).
                       Sans ce bandeau l'exclusion serait invisible et le total
                       paraîtrait complet. -->
                  <div v-if="pf.risk.deals_missing_fx?.length"
                    class="text-xs text-red-400 bg-red-950/30 border border-red-900/50 rounded-lg px-3 py-2">
                    ⚠ {{ pf.risk.deals_missing_fx.length }} deal(s) exclu(s) des totaux — taux de change indisponible
                    ({{ pf.risk.deals_missing_fx.map(d => `${d.reference} (${d.devise})`).join(', ') }})
                  </div>
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
                  <div v-if="hasMixedVegaScopes"
                    class="text-xs text-amber-400 bg-amber-950/30 border border-amber-900/50 rounded-lg px-3 py-2">
                    ⚠ Certains sous-jacents portent plusieurs périmètres de vega. Les montants sont présentés séparément et ne sont pas additionnés.
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
                            <th class="text-right py-1.5 font-semibold">Vega par périmètre (EUR)
                              <HelpTip align="right" width="w-80" text="Les vegas de volatilité totale, de jambe indépendante de variance et les anciens vegas sans périmètre documenté restent séparés. Les additionner donnerait une exposition sans définition commune." /></th>
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
                              <td class="py-1.5 text-right font-mono text-slate-400">
                                <div v-for="row in vegaRows(g)" :key="row.scope">
                                  <span class="text-[10px] text-slate-600">{{ vegaScopeLabel(row.scope) }}</span>
                                  {{ formatNominal(row.value) }}
                                </div>
                                <span v-if="!vegaRows(g).length" class="text-slate-600">—</span>
                              </td>
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
                                      <th class="text-right py-1 font-medium">Vega (EUR / périmètre / %)</th>
                                    </tr>
                                  </thead>
                                  <tbody>
                                    <tr v-for="c in g.contributions" :key="c.deal_id"
                                      class="hover:bg-slate-800/40 cursor-pointer" @click.stop="openDealDetail(c.deal_id)">
                                      <td class="py-1 pr-3 font-mono font-semibold text-blue-400"><DealReferenceLink :deal-id="c.deal_id" :reference="c.reference" /></td>
                                      <td class="py-1 pr-3 text-right font-mono text-slate-400">
                                        {{ formatNominal(c.delta_eur) }} <span class="text-slate-600">({{ sharePct(c.delta_eur, g.delta_eur) }})</span>
                                      </td>
                                      <td class="py-1 pr-3 text-right font-mono text-slate-400">
                                        {{ formatNominal(c.gamma_eur) }} <span class="text-slate-600">({{ sharePct(c.gamma_eur, g.gamma_eur) }})</span>
                                      </td>
                                      <td class="py-1 text-right font-mono text-slate-400">
                                        <template v-if="c.vega_eur != null">
                                          {{ formatNominal(c.vega_eur) }}
                                          <span class="text-slate-600">{{ vegaScopeLabel(c.vega_scope) }} · ({{ sharePct(c.vega_eur, vegaScopeTotal(g, c.vega_scope)) }})</span>
                                        </template>
                                        <span v-else class="text-slate-600">—</span>
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
                                        <td class="py-1 pr-3 font-mono font-semibold text-blue-400"><DealReferenceLink :deal-id="c.deal_id" :reference="c.reference" /></td>
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
                          <HelpTip text="Décroissance temporelle nette du book, en EUR par jour calendaire — somme des theta par deal (signe de la position × nominal × taux de change), déjà scalaire donc pas de regroupement par sous-jacent nécessaire. Un flux détaché pendant la semaine mesurée n'y entre pas : il est reporté à part sur le deal concerné." /></div>
                        <div class="text-lg font-bold font-mono text-slate-200">{{ formatNominal(pf.risk.scalar.theta) }}</div>
                        <div class="text-[10px] text-slate-600">EUR / jour</div>
                        <div v-if="pf.risk.deals_missing_theta?.length"
                          class="text-[10px] text-amber-400/80 mt-0.5">
                          somme partielle — {{ pf.risk.deals_missing_theta.length }} deal(s) sans theta
                          <HelpTip text="Ces deals n'ont pas de theta calculable : la semaine franchit une transition contractuelle ou un état réalisé qui ne peut pas être inventé exactement (observation, fixing, mémoire ou volatilité réalisée). Ils sont exclus de la somme plutôt que comptés à zéro." />
                        </div>
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
                  Exposition par contrepartie sur les deals actifs et les remboursements en attente — pas de recalcul Monte Carlo.
                  <HelpTip text="Avant maturité, la base est le nominal. Entre maturité et paiement, la base devient le remboursement contractuel connu encore dû par l'émetteur." />
                </div>

                <div v-if="pf.exposureLoading" class="text-xs text-slate-500">Chargement…</div>

                <template v-else-if="pf.exposure">
                  <div v-if="!pf.exposure.by_counterparty.length" class="text-xs text-slate-500">
                    Aucun deal actif ou en attente de règlement dans cette sélection.
                  </div>

                  <template v-else>
                    <div class="grid grid-cols-2 sm:grid-cols-4 gap-3">
                      <div class="stat-box">
                        <div class="text-xs text-slate-500 mb-1">Exposition totale
                          <HelpTip text="Somme des nominaux actifs et des remboursements connus non réglés, convertis en EUR." /></div>
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
                                      <td class="py-1 pr-3 font-mono font-semibold text-blue-400"><DealReferenceLink :deal-id="dl.id" :reference="dl.reference" /></td>
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
                  <button class="btn-primary text-xs px-4 py-1.5 self-end" :disabled="calculationActive"
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
                            <td class="py-1.5 pr-3 font-mono font-semibold text-blue-400"><DealReferenceLink :deal-id="c.deal_id" :reference="c.reference" /></td>
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
                  <button class="btn-primary text-xs px-4 py-1.5 self-end" :disabled="calculationActive"
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
                    <input v-model.number="varForm.n_paths_per_scenario" type="number" min="1000" step="500" class="input text-xs py-1 w-28" />
                  </label>
                  <label class="flex flex-col gap-0.5 text-[10px] text-slate-500">Workers parallèles
                    <input v-model.number="varForm.max_workers" type="number" min="1" max="4" class="input text-xs py-1 w-20" />
                  </label>
                </div>

                <template v-if="pf.varStudy">
                  <div v-if="pf.varStudy.status === 'queued' || pf.varStudy.status === 'running'"
                    class="flex flex-col gap-1.5">
                    <div class="text-xs text-slate-400">
                      {{ pf.varStudy.status === 'queued' ? 'En file d\'attente…' : 'En cours…' }}
                      {{ pf.varStudy.completed_jobs + pf.varStudy.failed_jobs }} / {{ pf.varStudy.total_jobs }} valorisation(s)
                    </div>
                    <div class="w-full h-1.5 bg-slate-800 rounded-full overflow-hidden">
                      <div class="h-full bg-blue-500 transition-all"
                        :style="{ width: (pf.varStudy.total_jobs ? (pf.varStudy.completed_jobs + pf.varStudy.failed_jobs) / pf.varStudy.total_jobs * 100 : 0) + '%' }"></div>
                    </div>
                  </div>

                  <template v-else>
                    <div v-if="pf.varStudy.result?.global_status === 'incomplete'"
                      class="text-xs text-red-300 bg-red-950/30 border border-red-900/50 rounded-lg px-3 py-2">
                      <div class="font-semibold">VaR du portefeuille demandé indisponible.</div>
                      <div class="mt-1 text-red-300/80">
                        Couverture {{ pf.varStudy.result.coverage?.included_deals ?? 0 }}/{{ pf.varStudy.result.coverage?.requested_deals ?? 0 }} deal(s).
                        Aucune VaR ni aucun ES global n'est publié.
                      </div>
                    </div>

                    <div v-if="varPublishedScope" class="text-xs text-slate-400">
                      <span class="font-semibold text-slate-200">{{ varPublishedScopeLabel }}</span>
                      <span v-if="pf.varStudy.result?.global_status === 'incomplete'">
                        — univers fixe après exclusion de {{ varExcludedDeals.length }} deal(s) dans tous les scénarios.
                      </span>
                    </div>

                    <div v-if="pf.varStudy.params?.market_data"
                      class="text-[10px] text-slate-500 font-mono">
                      Source : {{ pf.varStudy.params.market_data.provider === 'YAHOO_FINANCE'
                        ? 'Yahoo Finance' : pf.varStudy.params.market_data.provider }} ·
                      clôtures ajustées · date effective
                      {{ pf.varStudy.params.market_data.asof_effective || 'indisponible' }}
                      <span v-if="pf.varStudy.params.market_data.warnings?.length"
                        class="text-amber-400"> · ⚠ données anciennes</span>
                    </div>

                    <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
                      <div v-for="m in ['historical', 'parametric']" :key="m" v-show="varPublishedScope?.[m]"
                        class="card flex flex-col gap-2">
                        <div class="text-xs font-bold text-slate-300 uppercase tracking-wider">
                          {{ m === 'historical' ? 'Historique' : 'Paramétrique' }}
                          <span class="text-slate-600 font-normal normal-case">— {{ varPublishedScope?.[m]?.n_scenarios }} scénario(s)</span>
                        </div>
                        <div class="grid grid-cols-2 gap-2">
                          <div class="stat-box">
                            <div class="text-xs text-slate-500 mb-1">VaR {{ Math.round((pf.varStudy.params.confidence ?? 0.95) * 100) }}%</div>
                            <div class="text-lg font-bold font-mono text-red-400">{{ formatNominal(varPublishedScope?.[m]?.var_eur) }}</div>
                            <div class="text-[10px] text-slate-600">EUR</div>
                          </div>
                          <div class="stat-box">
                            <div class="text-xs text-slate-500 mb-1">Expected Shortfall
                              <HelpTip text="Perte moyenne au-delà du seuil VaR — la queue au-delà du pire (confiance)%, pas juste le point de coupure." /></div>
                            <div class="text-lg font-bold font-mono text-red-400">{{ formatNominal(varPublishedScope?.[m]?.es_eur) }}</div>
                            <div class="text-[10px] text-slate-600">EUR</div>
                          </div>
                        </div>
                        <div class="text-[10px] text-slate-500 font-mono flex flex-wrap gap-x-3">
                          <span v-for="(v, p) in varPublishedScope?.[m]?.distribution_summary" :key="p">{{ p }}: {{ formatNominal(v) }}</span>
                        </div>
                      </div>
                    </div>

                    <div v-if="varPublishedScope?.worst_scenarios?.length" class="overflow-x-auto table-shell" tabindex="0" role="region">
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
                          <tr v-for="w in varPublishedScope.worst_scenarios" :key="w.scenario_key"
                            class="border-b border-slate-800/50">
                            <td class="py-1 pr-3 font-mono text-slate-300">{{ w.scenario_key }}</td>
                            <td class="py-1 pr-3 text-slate-500">{{ w.method === 'historical' ? 'Historique' : 'Paramétrique' }}</td>
                            <td class="py-1 text-right font-mono text-red-400">{{ formatNominal(w.delta_eur) }}</td>
                          </tr>
                        </tbody>
                      </table>
                    </div>

                    <div v-if="varExcludedDeals.length" class="text-xs text-slate-500 flex flex-col gap-1">
                      <div class="font-semibold text-slate-400">Deals exclus du périmètre calculable</div>
                      <div v-for="deal in varExcludedDeals" :key="`${deal.phase}-${deal.deal_id}`">
                        <DealReferenceLink :deal-id="deal.deal_id" :reference="deal.reference"
                                           class="font-mono text-blue-400" />
                        — {{ deal.reason }}
                      </div>
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
                <button class="btn-primary text-xs px-4 py-1.5" :disabled="calculationActive || !pf.members.length"
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
                      {{ i > 0 ? ' · ' : '' }}<DealReferenceLink :deal-id="s.deal_id"
                        :reference="s.reference" class="font-mono text-blue-400" /> <span class="text-amber-600">({{ s.reason || s.error }})</span>
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
                          <td class="py-1.5 pr-3 font-mono font-semibold text-blue-400"><DealReferenceLink :deal-id="c.deal_id" :reference="c.reference" /></td>
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

            <!-- ══ Onglet risque de smile ══════════════════════════ -->
            <template v-else-if="activeTab === 'smile'">
              <div class="flex flex-col gap-1">
                <div class="text-sm font-bold text-slate-100">
                  〰 Risque de smile — {{ pf.view === 'global' ? 'Tous les deals actifs' : pf.label }}
                </div>
                <div class="text-[10px] text-slate-500 max-w-4xl">
                  Repricing complet avec les mêmes termes, la même date de valorisation et le même marché de base.
                  Les paramètres restent propres au modèle : σ/skew/courbure pour Local Vol, α/ρ/ν pour SABR,
                  v0/θ/ρ/ξ pour Heston. Aucun mapping implicite n’est appliqué entre ces modèles.
                </div>
              </div>

              <div class="grid grid-cols-1 lg:grid-cols-3 gap-3">
                <div class="rounded-lg border border-slate-800 p-3 flex flex-col gap-2">
                  <div class="text-xs font-semibold text-slate-300">Surface locale</div>
                  <div class="grid grid-cols-3 gap-2">
                    <label class="text-[10px] text-slate-500">ATM (pts)
                      <input v-model.number="smileForm.atm_vol_pts" type="number" step="1" class="input mt-1 w-full text-xs" />
                    </label>
                    <label class="text-[10px] text-slate-500">Skew (pts)
                      <input v-model.number="smileForm.skew_pts" type="number" step="1" class="input mt-1 w-full text-xs" />
                    </label>
                    <label class="text-[10px] text-slate-500">Courbure (pts)
                      <input v-model.number="smileForm.curvature_pts" type="number" step="1" class="input mt-1 w-full text-xs" />
                    </label>
                  </div>
                  <div class="text-[9px] text-slate-600">ATM : modèles constants et Local Vol · skew/courbure : Local Vol et LSV.</div>
                </div>

                <div class="rounded-lg border border-slate-800 p-3 flex flex-col gap-2">
                  <div class="text-xs font-semibold text-slate-300">SABR natif</div>
                  <div class="grid grid-cols-3 gap-2">
                    <label class="text-[10px] text-slate-500">α (pts)
                      <input v-model.number="smileForm.sabr_alpha_pts" type="number" step="1" class="input mt-1 w-full text-xs" />
                    </label>
                    <label class="text-[10px] text-slate-500">ρ (pts)
                      <input v-model.number="smileForm.sabr_rho_pts" type="number" step="1" class="input mt-1 w-full text-xs" />
                    </label>
                    <label class="text-[10px] text-slate-500">ν (pts)
                      <input v-model.number="smileForm.sabr_nu_pts" type="number" step="1" class="input mt-1 w-full text-xs" />
                    </label>
                  </div>
                </div>

                <div class="rounded-lg border border-slate-800 p-3 flex flex-col gap-2">
                  <div class="text-xs font-semibold text-slate-300">Heston / LSV natif</div>
                  <div class="grid grid-cols-4 gap-2">
                    <label class="text-[10px] text-slate-500">v0 (pts)
                      <input v-model.number="smileForm.heston_v0_pts" type="number" step="1" class="input mt-1 w-full text-xs" />
                    </label>
                    <label class="text-[10px] text-slate-500">θ (pts)
                      <input v-model.number="smileForm.heston_theta_pts" type="number" step="1" class="input mt-1 w-full text-xs" />
                    </label>
                    <label class="text-[10px] text-slate-500">ρ (pts)
                      <input v-model.number="smileForm.heston_rho_pts" type="number" step="1" class="input mt-1 w-full text-xs" />
                    </label>
                    <label class="text-[10px] text-slate-500">ξ (pts)
                      <input v-model.number="smileForm.heston_xi_pts" type="number" step="1" class="input mt-1 w-full text-xs" />
                    </label>
                  </div>
                </div>
              </div>

              <div class="flex items-center gap-3 flex-wrap">
                <label class="text-[10px] text-slate-500">Sous-jacent ciblé
                  <select v-model="smileTarget" class="select ml-2 text-xs min-w-48">
                    <option value="all">Tous les sous-jacents</option>
                    <option v-for="u in smileUnderlyings" :key="u.key" :value="u.key">
                      {{ u.label }}
                    </option>
                  </select>
                </label>
                <label class="text-[10px] text-slate-500">Nom du scénario
                  <input v-model="smileForm.label" type="text" placeholder="Ex. Stress skew actions" class="input ml-2 text-xs w-56" />
                </label>
                <button class="btn-primary text-xs px-4 py-1.5 ml-auto"
                  :disabled="calculationActive || !pf.members.length || !smileHasShock"
                  @click="runSmile">
                  <span v-if="pf.smileLoading"
                    class="w-3 h-3 border-2 border-white/60 border-t-transparent rounded-full animate-spin inline-block mr-1"></span>
                  Repricer le smile
                </button>
              </div>

              <AlertMessage v-if="smileError" kind="error" dismissible @dismiss="smileError = ''">
                {{ smileError }}
              </AlertMessage>

              <template v-if="pf.smileResult">
                <div class="grid grid-cols-2 sm:grid-cols-4 gap-3">
                  <div class="stat-box">
                    <div class="text-xs text-slate-500 mb-1">Impact total</div>
                    <div class="text-lg font-bold font-mono" :class="pf.smileResult.total_delta_eur >= 0 ? 'text-emerald-400' : 'text-red-400'">
                      {{ formatNominal(pf.smileResult.total_delta_eur) }} EUR
                    </div>
                  </div>
                  <div class="stat-box">
                    <div class="text-xs text-slate-500 mb-1">Impact / nominal</div>
                    <div class="text-lg font-bold font-mono text-slate-200">{{ pf.smileResult.pct_impact ?? '—' }}%</div>
                  </div>
                  <div class="stat-box">
                    <div class="text-xs text-slate-500 mb-1">Couverture repricée</div>
                    <div class="text-lg font-bold font-mono text-blue-300">{{ pf.smileResult.coverage_pct ?? '—' }}%</div>
                  </div>
                  <div class="stat-box">
                    <div class="text-xs text-slate-500 mb-1">Deals repricés</div>
                    <div class="text-lg font-bold font-mono text-slate-200">{{ pf.smileResult.contributions.length }}</div>
                  </div>
                </div>

                <div v-if="pf.smileResult.skipped.length || pf.smileResult.errors.length"
                  class="text-xs text-amber-400 bg-amber-950/30 border border-amber-900/50 rounded-lg px-3 py-2">
                  {{ pf.smileResult.skipped.length }} non applicable(s) · {{ pf.smileResult.errors.length }} erreur(s).
                  <span v-for="row in pf.smileResult.skipped" :key="`skip-${row.deal_id}`" class="block mt-1">
                    <DealReferenceLink :deal-id="row.deal_id" :reference="row.reference"
                                       class="font-mono text-blue-400" /> — {{ row.reason }}
                  </span>
                  <span v-for="row in pf.smileResult.errors" :key="`err-${row.deal_id}`" class="block mt-1">
                    <DealReferenceLink :deal-id="row.deal_id" :reference="row.reference"
                                       class="font-mono text-blue-400" /> — {{ row.error }}
                  </span>
                </div>

                <div v-if="pf.smileResult.contributions.length" class="overflow-x-auto table-shell" tabindex="0" role="region">
                  <table class="w-full text-xs border-collapse">
                    <thead>
                      <tr class="border-b border-slate-700 text-slate-500">
                        <th class="text-left py-1.5 pr-3 font-semibold">Deal</th>
                        <th class="text-left py-1.5 pr-3 font-semibold">Modèle</th>
                        <th class="text-left py-1.5 pr-3 font-semibold">Paramètres déplacés</th>
                        <th class="text-right py-1.5 pr-3 font-semibold">Avant</th>
                        <th class="text-right py-1.5 pr-3 font-semibold">Après</th>
                        <th class="text-right py-1.5 font-semibold">Impact EUR</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="row in pf.smileResult.contributions" :key="row.deal_id"
                        class="border-b border-slate-800/50 hover:bg-slate-800/20 cursor-pointer"
                        @click="openDealDetail(row.deal_id)">
                        <td class="py-2 pr-3 font-mono font-semibold text-blue-400"><DealReferenceLink :deal-id="row.deal_id" :reference="row.reference" /></td>
                        <td class="py-2 pr-3 uppercase text-[10px] text-slate-400">{{ row.model }}</td>
                        <td class="py-2 pr-3 text-[10px] text-slate-400">
                          <span v-for="u in row.parameter_changes" :key="u.ticker || u.name" class="block">
                            {{ u.ticker || u.name }} : {{ u.changes.map(c => `${c.parameter} ${c.shift_pts > 0 ? '+' : ''}${c.shift_pts}pt`).join(', ') }}
                          </span>
                        </td>
                        <td class="py-2 pr-3 text-right font-mono text-slate-400">{{ Number(row.mtm_before).toFixed(3) }}</td>
                        <td class="py-2 pr-3 text-right font-mono text-slate-300">{{ Number(row.mtm_after).toFixed(3) }}</td>
                        <td class="py-2 text-right font-mono font-semibold" :class="row.delta_eur >= 0 ? 'text-emerald-400' : 'text-red-400'">
                          {{ formatNominal(row.delta_eur) }}
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </template>

              <div v-if="pf.currentSmileHistory.length" class="pt-2 border-t border-slate-800">
                <div class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-2">Historique des scénarios</div>
                <div class="grid grid-cols-1 md:grid-cols-2 gap-2">
                  <div v-for="run in pf.currentSmileHistory" :key="run.id"
                    class="rounded-lg border border-slate-800 px-3 py-2 flex items-center gap-3">
                    <div class="min-w-0 flex-1">
                      <div class="text-xs text-slate-300 truncate">{{ run.label }}</div>
                      <div class="text-[9px] text-slate-600">{{ formatDateTime(run.created_at) }}</div>
                    </div>
                    <div class="font-mono text-xs font-semibold"
                      :class="run.result.total_delta_eur >= 0 ? 'text-emerald-400' : 'text-red-400'">
                      {{ formatNominal(run.result.total_delta_eur) }} EUR
                    </div>
                    <div class="font-mono text-[10px] text-slate-500">{{ run.result.coverage_pct ?? '—' }}%</div>
                  </div>
                </div>
              </div>
            </template>

            <!-- ══ Onglet Barrières : proximité aux barrières ═══════ -->
            <template v-else-if="activeTab === 'barrieres'">
              <div class="flex items-center gap-3 flex-wrap">
                <div class="text-sm font-bold text-slate-100">
                  📍 Proximité aux barrières — {{ pf.view === 'global' ? 'Tous portefeuilles' : pf.label }}
                  <HelpTip width="w-80" text="Classe tous les deals actifs de la sélection par écart entre le worst-of actuel et leur prochaine barrière (autocall, KI) détectée dans le script — pour repérer en un coup d'œil ce qui mérite un suivi cette semaine. Réutilise la même détection que la Surveillance de Booking (convention PARAM M_)." />
                </div>
                <button class="btn-secondary text-xs px-3 py-1.5 ml-auto" :disabled="calculationActive || !pf.members.length"
                  @click="pf.loadBarriers">
                  <span v-if="pf.barriersLoading"
                    class="w-3 h-3 border-2 border-slate-400 border-t-transparent rounded-full animate-spin inline-block mr-1"></span>
                  🔄 Actualiser
                </button>
              </div>

              <div v-if="!pf.barriers && !pf.barriersLoading" class="text-xs text-slate-500 text-center py-8">
                <button class="btn-primary text-xs px-4 py-1.5" :disabled="calculationActive || !pf.members.length" @click="pf.loadBarriers">
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
                    {{ i > 0 ? ' · ' : '' }}<DealReferenceLink :deal-id="e.deal_id"
                      :reference="e.reference" class="font-mono text-blue-400" /> <span class="text-amber-600">({{ e.error }})</span>
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
                        <td class="py-2 pr-3 font-mono font-semibold text-blue-400 whitespace-nowrap"><DealReferenceLink :deal-id="w.deal_id" :reference="w.reference" /></td>
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

              <AlertMessage v-if="portfolioError" kind="error" dismissible
                @dismiss="portfolioError = ''">{{ portfolioError }}</AlertMessage>
              <AlertMessage v-if="portfolioNotice" kind="success" dismissible
                @dismiss="portfolioNotice = ''">{{ portfolioNotice }}</AlertMessage>

              <!-- Création & gestion -->
              <div class="flex flex-col gap-2">
                <div class="text-xs font-bold text-slate-400 uppercase tracking-wider">Création & gestion</div>
                <div class="max-w-md">
                  <label v-if="authStore.isAdmin" for="new-portfolio-owner" class="label">Compte propriétaire</label>
                  <select v-if="authStore.isAdmin" id="new-portfolio-owner" v-model.number="newPortfolioUserId"
                    class="select text-xs py-1.5 w-full mt-1 mb-2" :disabled="creatingPortfolio">
                    <option v-for="owner in portfolioOwners" :key="owner.id" :value="owner.id">
                      {{ owner.username }}{{ owner.entity ? ` · ${owner.entity}` : '' }}
                    </option>
                  </select>
                  <label for="new-portfolio-name" class="label">Nom du portefeuille</label>
                  <div class="flex gap-1.5 mt-1">
                    <input id="new-portfolio-name" v-model="newPortfolioName" type="text"
                      placeholder="Ex. Produits structurés EUR" class="input text-xs py-1.5 flex-1 min-w-0"
                      :disabled="creatingPortfolio" autocomplete="off" @keyup.enter="createPortfolio" />
                    <button class="btn-primary text-xs px-3 py-1.5 shrink-0"
                      :disabled="creatingPortfolio || !newPortfolioName.trim()" @click="createPortfolio">
                      {{ creatingPortfolio ? 'Création…' : '＋ Créer' }}
                    </button>
                  </div>
                  <p class="text-[10px] mt-1" style="color: var(--subtle);">
                    Saisissez un nom : le bouton Créer s’active dès que le champ n’est plus vide.
                  </p>
                </div>
                <div class="flex flex-col gap-1 max-w-md">
                  <div v-for="p in pf.portfolios" :key="p.id"
                    class="flex items-center gap-2 px-2.5 py-1.5 rounded-lg border border-slate-800 group">
                    <span class="text-sm shrink-0">📁</span>
                    <span class="flex-1 min-w-0 text-xs text-slate-300">
                      <span class="block truncate">{{ p.name }}</span>
                      <span v-if="authStore.isAdmin" class="block truncate text-[9px] text-slate-600">
                        {{ p.owner_username }}{{ p.owner_entity_name ? ` · ${p.owner_entity_name}` : '' }}
                      </span>
                    </span>
                    <span class="text-[10px] font-mono px-1.5 py-0.5 rounded-full bg-slate-800 text-slate-400 shrink-0">{{ p.deal_count }} deal(s)</span>
                    <button class="text-slate-600 hover:text-slate-300 text-xs px-1 shrink-0"
                      title="Renommer" aria-label="Renommer le portefeuille" @click="renamePortfolio(p)">✎</button>
                    <button class="text-slate-600 hover:text-red-400 text-xs px-1 shrink-0"
                      title="Supprimer le portefeuille (les deals et leurs calculs sont conservés)"
                      aria-label="Supprimer le portefeuille" @click="deletePortfolio(p)">✕</button>
                  </div>
                </div>
              </div>

              <!-- Composition de la sélection -->
              <div class="text-xs font-bold text-slate-400 uppercase tracking-wider pt-2 border-t border-slate-800">
                Composition — {{ pf.view === 'global' ? 'Tous portefeuilles' : pf.label }}
                <span class="ml-2 font-normal normal-case text-slate-500">
                  {{ pf.riskMembers.length }} actif(s) à la date sur {{ pf.allMembers.length }} deal(s)
                </span>
              </div>
              <div v-if="!pf.allMembers.length" class="text-xs text-slate-500">
                Aucun deal dans cette sélection.
              </div>
              <div v-else class="overflow-x-auto table-shell" tabindex="0" role="region">
                <table class="w-full text-xs border-collapse">
                  <thead>
                    <tr class="border-b border-slate-700 text-slate-500">
                      <th class="text-left py-1.5 pr-3 font-semibold">Réf</th>
                      <th class="text-left py-1.5 pr-3 font-semibold">Contrepartie</th>
                      <th class="text-left py-1.5 pr-3 font-semibold">Type</th>
                      <th class="text-left py-1.5 pr-3 font-semibold">État au {{ pf.valuationDate }}</th>
                      <th class="text-right py-1.5 pr-3 font-semibold num">Nominal</th>
                      <th class="text-left py-1.5 pr-3 font-semibold">Portefeuilles
                        <HelpTip text="Un deal peut appartenir à plusieurs portefeuilles. Cochez toutes les vues de risque qui doivent le contenir." /></th>
                      <th class="text-left py-1.5 font-semibold">Greeks à la date
                        <HelpTip text="Disponibilité d'un calcul dont la date de valorisation correspond exactement à la date d’analyse. La date d’exécution technique peut être postérieure. Cliquez la ligne pour ouvrir la fiche dans Booking." /></th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="d in pf.allMembers" :key="d.id"
                      class="border-b border-slate-800/50 hover:bg-slate-800/20 transition-colors cursor-pointer"
                      :class="riskState(d).active ? '' : 'opacity-45 grayscale bg-slate-900/40'"
                      @click="openDealDetail(d.id)">
                      <td class="py-1.5 pr-3 font-mono font-semibold text-blue-400"><DealReferenceLink :deal-id="d.id" :reference="d.reference" /></td>
                      <td class="py-1.5 pr-3 text-slate-300">{{ d.contrepartie }}</td>
                      <td class="py-1.5 pr-3 text-slate-500 text-[10px]">{{ d.product_type || '—' }}</td>
                      <td class="py-1.5 pr-3 text-[10px]"
                        :class="riskState(d).active ? 'text-emerald-400' : 'text-slate-500'">
                        {{ riskState(d).reason }}
                      </td>
                      <td class="py-1.5 pr-3 text-right font-mono num text-slate-300">{{ formatNominal(d.nominal) }} {{ d.devise }}</td>
                      <td class="py-1.5 pr-3" @click.stop>
                        <ActionMenu :label="dealPortfolioLabel(d)" :title="dealPortfolioLabel(d)" class="max-w-sm">
                            <label v-for="p in portfoliosForDeal(d)" :key="p.id"
                              class="flex items-center gap-2 px-2 py-1.5 rounded hover:bg-slate-800 text-[10px] text-slate-300 cursor-pointer">
                              <input type="checkbox" :checked="dealHasPortfolio(d, p.id)"
                                :disabled="portfolioAssigning[d.id]"
                                @change="togglePortfolioMembership(d, p.id, $event.target.checked)" />
                              <span>{{ p.name }}</span>
                            </label>
                            <div v-if="!portfoliosForDeal(d).length" class="px-2 py-1 text-[10px] text-slate-500">
                              Aucun portefeuille pour ce compte.
                            </div>
                        </ActionMenu>
                      </td>
                      <td class="py-1.5 text-slate-500">
                        <span v-if="greeksMatchSelectedDate(d)" class="text-emerald-400"
                          :title="greekExecutionTitle(d)">
                          disponibles
                        </span>
                        <span v-else-if="riskState(d).active" class="text-amber-400">absents à cette date</span>
                        <span v-else>hors périmètre</span>
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
import ActionMenu from '../components/ui/ActionMenu.vue'
import BackLink from '../components/ui/BackLink.vue'
import { ref, reactive, computed, onMounted, onUnmounted, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { useDealsStore } from '../stores/deals.js'
import { usePortfoliosStore, shockPresets, blankShockForm, blankVarForm } from '../stores/portfolios.js'
import { useAuthStore } from '../stores/auth.js'
import { apiFetch } from '../utils/api.js'
import { formatInt, formatDateTime, formatPercent } from '../utils/format.js'
import { barrierChipClass, barrierGapLabel } from '../utils/barriers.js'
import { dealRiskState, localTodayIso } from '../utils/riskDates.js'
import { runConcurrentPool } from '../utils/concurrentPool.js'
import HelpTip from '../components/HelpTip.vue'
import AlertMessage from '../components/ui/AlertMessage.vue'
import DealReferenceLink from '../components/DealReferenceLink.vue'
import { confirmer } from '../composables/useConfirm.js'

const route = useRoute()
const router = useRouter()
const dealsStore = useDealsStore()
const pf = usePortfoliosStore()
const authStore = useAuthStore()

// Le sous-menu Risk Management de l'accueil route vers /risk?tab=... — chaque
// entrée (Création de portefeuille / Chocs / Explication de P&L) atterrit
// directement sur sa section.
const VALID_TABS = ['portfolios', 'greeks', 'contreparties', 'chocs', 'smile', 'var', 'pnl', 'barrieres']
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
const newPortfolioUserId = ref(authStore.user?.id || null)
const creatingPortfolio = ref(false)
const portfolioAssigning = reactive({})
const portfolioError = ref('')
const portfolioNotice = ref('')
const todayIso = localTodayIso()

const formatNominal = formatInt

function riskState(deal) {
  return dealRiskState(deal, pf.valuationDate)
}

function greekValuationDate(deal) {
  const data = deal.greeks?.market_used?.data || {}
  return deal.greeks?.valuation_date
    || data.contractual_history?.requested_end
    || data.requested_asof
    || null
}

function greeksMatchSelectedDate(deal) {
  if (pf.risk?.valuation_date === pf.valuationDate) {
    return pf.risk.deals_included?.some(row => row.id === deal.id) || false
  }
  return !!deal.greeks_computed_at && greekValuationDate(deal) === pf.valuationDate
}

function greekExecutionTitle(deal) {
  const included = pf.risk?.deals_included?.find(row => row.id === deal.id)
  const computedAt = included?.greeks_computed_at || deal.greeks_computed_at
  return computedAt
    ? `Calcul exécuté le ${new Date(computedAt).toLocaleString('fr-FR')}`
    : 'Calcul daté disponible'
}

const portfolioOwners = computed(() => {
  const owners = new Map()
  if (authStore.user?.id) owners.set(authStore.user.id, {
    id: authStore.user.id,
    username: authStore.user.username,
    entity: null,
  })
  for (const p of pf.portfolios) {
    owners.set(p.user_id, {
      id: p.user_id,
      username: p.owner_username || `Compte #${p.user_id}`,
      entity: p.owner_entity_name || null,
    })
  }
  return [...owners.values()].sort((a, b) => a.username.localeCompare(b.username, 'fr'))
})

watch(portfolioOwners, owners => {
  if (!owners.length) return
  if (!owners.some(owner => owner.id === newPortfolioUserId.value)) {
    newPortfolioUserId.value = authStore.user?.id || owners[0].id
  }
}, { immediate: true })

function portfoliosForDeal(deal) {
  return pf.portfolios.filter(p => p.user_id === deal.user_id)
}

function dealHasPortfolio(deal, portfolioId) {
  return (deal.portfolio_ids || []).includes(portfolioId)
}

function dealPortfolioLabel(deal) {
  const count = (deal.portfolio_ids || []).length
  return count ? `${count} portefeuille${count > 1 ? 's' : ''}` : 'Non classé'
}

const hasMixedVegaScopes = computed(() =>
  Object.values(pf.risk?.per_underlying || {}).some(bucket => bucket.vega_scope_mixed)
)

const VEGA_SCOPE_LABELS = {
  total: 'vol totale',
  leg_independante: 'jambe indépendante',
  non_documente: 'périmètre non documenté',
}

function vegaScopeLabel(scope) {
  return VEGA_SCOPE_LABELS[scope] || scope || 'périmètre non documenté'
}

function vegaScopeTotal(bucket, scope) {
  return bucket?.vega_by_scope_eur?.[scope] ?? null
}

function vegaRows(bucket) {
  return (bucket?.vega_scopes || []).map(scope => ({
    scope,
    value: vegaScopeTotal(bucket, scope),
  }))
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
  if (!name || creatingPortfolio.value) return
  creatingPortfolio.value = true
  portfolioError.value = ''
  portfolioNotice.value = ''
  try {
    const created = await pf.create(name, authStore.isAdmin ? newPortfolioUserId.value : null)
    newPortfolioName.value = ''
    portfolioNotice.value = `Portefeuille « ${created.name} » créé. Vous pouvez maintenant y affecter des deals.`
  } catch (e) {
    portfolioError.value = e.message
  } finally {
    creatingPortfolio.value = false
  }
}

async function renamePortfolio(p) {
  const name = prompt('Nouveau nom du portefeuille :', p.name)
  if (!name || !name.trim() || name.trim() === p.name) return
  portfolioError.value = ''
  portfolioNotice.value = ''
  try {
    await pf.rename(p, name.trim())
    portfolioNotice.value = `Portefeuille renommé « ${name.trim()} ».`
  } catch (e) {
    portfolioError.value = e.message
  }
}

async function deletePortfolio(p) {
  if (!await confirmer({ titre: `Supprimer « ${p.name} » ?`,
                       message: "Seules les appartenances à ce portefeuille seront supprimées. "
                              + 'Les deals et tous leurs calculs seront conservés.',
                       confirmer: 'Supprimer', danger: true })) return
  portfolioError.value = ''
  portfolioNotice.value = ''
  try {
    await pf.remove(p)
    portfolioNotice.value = `Portefeuille « ${p.name} » supprimé. Les deals et leurs calculs sont conservés.`
  } catch (e) {
    portfolioError.value = e.message
  }
}

async function togglePortfolioMembership(deal, portfolioId, checked) {
  if (portfolioAssigning[deal.id]) return
  const target = pf.portfolios.find(p => p.id === portfolioId)
  const currentIds = deal.portfolio_ids || []
  const nextIds = checked
    ? [...new Set([...currentIds, portfolioId])]
    : currentIds.filter(id => id !== portfolioId)
  portfolioAssigning[deal.id] = true
  portfolioError.value = ''
  portfolioNotice.value = ''
  try {
    await pf.setDealPortfolios(deal.id, nextIds)
    portfolioNotice.value = checked
      ? `${deal.reference} ajouté à « ${target?.name || 'portefeuille sélectionné'} ».`
      : `${deal.reference} retiré de « ${target?.name || 'portefeuille sélectionné'} ».`
  } catch (e) {
    portfolioError.value = `${deal.reference} : ${e.message}`
  } finally {
    portfolioAssigning[deal.id] = false
  }
}

// ── Risque de smile, paramètres explicites par modèle ───────────────
const smileForm = reactive({
  atm_vol_pts: 0, skew_pts: 0, curvature_pts: 0,
  sabr_alpha_pts: 0, sabr_rho_pts: 0, sabr_nu_pts: 0,
  heston_v0_pts: 0, heston_theta_pts: 0, heston_rho_pts: 0, heston_xi_pts: 0,
  label: '', recalibrate: 'none',
})
const smileError = ref('')
const smileTarget = ref('all')
const smileUnderlyings = computed(() => {
  const seen = new Map()
  for (const deal of pf.members) {
    for (const underlying of deal.underlyings || []) {
      const key = underlying.ticker || underlying.name
      if (key && !seen.has(key)) {
        seen.set(key, { key, label: underlying.ticker
          ? `${underlying.name || underlying.ticker} · ${underlying.ticker}`
          : underlying.name })
      }
    }
  }
  return [...seen.values()].sort((a, b) => a.label.localeCompare(b.label, 'fr'))
})
const smileHasShock = computed(() => Object.entries(smileForm).some(([key, value]) =>
  key.endsWith('_pts') && Number(value) !== 0))

async function runSmile() {
  smileError.value = ''
  try {
    const fields = Object.fromEntries(Object.entries(smileForm)
      .filter(([key]) => key.endsWith('_pts')))
    const payload = smileTarget.value === 'all'
      ? { ...smileForm }
      : {
          ...Object.fromEntries(Object.keys(fields).map(key => [key, 0])),
          label: smileForm.label,
          recalibrate: smileForm.recalibrate,
          underlying_overrides: { [smileTarget.value]: fields },
        }
    await pf.runSmileRisk(payload)
  } catch (e) {
    smileError.value = e.message
  }
}

// ── Recalcul des Greeks par deal (batch) ─────────────────────────────
const recomputing = ref(false)
const recomputeDone = ref(0)
const recomputeTotal = ref(0)
const recomputeFailures = ref([])
const recomputeNotice = ref('')
const PORTFOLIO_GREEK_CONCURRENCY = 2

async function recomputePortfolio() {
  const memberIds = pf.riskMembers.map(d => d.id)
  if (!memberIds.length) return
  recomputing.value = true
  recomputeDone.value = 0
  recomputeTotal.value = memberIds.length
  recomputeFailures.value = []
  recomputeNotice.value = ''
  try {
    const results = await runConcurrentPool(memberIds, async id => {
      const response = await apiFetch(`/api/deals/${id}/greeks`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            recalibrate: 'none',
            valuation_date: pf.valuationDate,
          }),
      })
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}))
        const detail = payload.detail
        throw new Error(typeof detail === 'string' ? detail : detail?.message || 'Calcul refusé')
      }
      return id
    }, {
      concurrency: PORTFOLIO_GREEK_CONCURRENCY,
      onSettled: () => { recomputeDone.value += 1 },
    })
    recomputeFailures.value = results.flatMap((result, index) => result.status === 'rejected'
      ? [{ id: memberIds[index], reason: result.reason?.message || 'Erreur de calcul' }]
      : [])
    const succeeded = memberIds.length - recomputeFailures.value.length
    recomputeNotice.value = recomputeFailures.value.length
      ? `${succeeded}/${memberIds.length} calcul(s) terminés. ${recomputeFailures.value.length} deal(s) en erreur.`
      : `${succeeded} calcul(s) de Greeks terminés à la date sélectionnée.`
  } finally {
    try {
      await dealsStore.loadDeals()
      await pf.loadRisk()
    } finally {
      recomputing.value = false
    }
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

const varExcludedDeals = computed(() => {
  const resultDeals = pf.varStudy?.result?.excluded_deals
  if (resultDeals?.length) return resultDeals
  const persisted = pf.varStudy?.params?.preflight_exclusions
  if (persisted?.length) return persisted
  return varDealsSkipped.value
})

const varPublishedScope = computed(() => {
  const result = pf.varStudy?.result
  if (!result) return null
  if (result.global_status === 'complete') return result
  if (result.global_status === 'incomplete') return result.reduced_scope || null
  // Historical batches created before the publication gate.
  return result.historical || result.parametric ? result : null
})

const varPublishedScopeLabel = computed(() =>
  varPublishedScope.value?.label || 'VaR du portefeuille demandé')

async function launchVarStudy() {
  varDealsSkipped.value = []
  varLaunchError.value = ''
  try {
    const launched = await pf.launchVar(varForm)
    varDealsSkipped.value = launched.deals_skipped || []
  } catch (e) {
    const detail = e.computeDetail
    if (detail?.code === 'COMPUTE_CONFIRMATION_REQUIRED') {
      const x = detail.estimate || {}
      const accepted = await confirmer({
        titre: 'Confirmer cette VaR lourde ?',
        message: `${Number(x.cells || 0).toLocaleString('fr-FR')} valorisations, ` +
          `${Number(x.paths_per_scenario || 0).toLocaleString('fr-FR')} trajectoires chacune, ` +
          `mémoire de pointe estimée ${x.estimated_peak_mb || 0} Mo.`,
        confirmer: 'Lancer la VaR',
      })
      if (accepted) {
        try {
          const launched = await pf.launchVar({
            ...varForm, confirmation_token: detail.confirmation_token,
          })
          varDealsSkipped.value = launched.deals_skipped || []
          return
        } catch (retryError) {
          varLaunchError.value = retryError.message
          return
        }
      }
      return
    }
    varLaunchError.value = e.message
  }
}

// ── P&L explain (portefeuille / global) ──────────────────────────────
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

// ── Progression unifiée des calculs de portefeuille ────────────────
// Greeks et VaR exposent un compteur exact. Les endpoints synchrones
// (choc, smile, P&L, barrières) n'exposent pas encore leurs étapes internes :
// la barre reste alors indéterminée mais le temps écoulé reste visible.
const calculationProgress = computed(() => {
  if (recomputing.value) {
    const total = recomputeTotal.value
    const completed = recomputeDone.value
    return {
      key: 'greeks', label: 'Calcul des Greeks du portefeuille', completed, total,
      percent: total ? Math.round(completed / total * 100) : 0,
    }
  }
  if (shockLoading.value) return { key: 'shock', label: 'Repricing du choc portefeuille' }
  if (pf.smileLoading) return { key: 'smile', label: 'Repricing du smile portefeuille' }
  if (pf.varLaunching || pf.varPolling) {
    const total = Number(pf.varStudy?.total_jobs || 0)
    const completed = Number(pf.varStudy?.completed_jobs || 0) + Number(pf.varStudy?.failed_jobs || 0)
    return {
      key: 'var', label: pf.varLaunching ? 'Préparation de la VaR' : 'Calcul de la VaR',
      completed, total, percent: total ? Math.round(completed / total * 100) : 0,
    }
  }
  if (pnlLoading.value) return { key: 'pnl', label: 'Explication du P&L portefeuille' }
  if (pf.barriersLoading) return { key: 'barriers', label: 'Analyse des barrières du portefeuille' }
  return null
})
const calculationActive = computed(() => calculationProgress.value !== null)
const calculationElapsed = ref(0)
let calculationTimer = null

function formatElapsed(seconds) {
  const mins = Math.floor(seconds / 60)
  const secs = seconds % 60
  return mins ? `${mins} min ${String(secs).padStart(2, '0')} s` : `${secs} s`
}

watch(() => calculationProgress.value?.key || null, key => {
  if (calculationTimer) clearInterval(calculationTimer)
  calculationTimer = null
  calculationElapsed.value = 0
  if (key) {
    const startedAt = Date.now()
    calculationTimer = setInterval(() => {
      calculationElapsed.value = Math.floor((Date.now() - startedAt) / 1000)
    }, 1000)
  }
}, { immediate: true })

onMounted(() => {
  const rememberedVarBatchId = pf.varStudy?.batch_id
  dealsStore.loadDeals()
  pf.load()
  pf.loadRisk()
  pf.loadExposure()
  pf.loadVarHistory()
  // The view deliberately stops its timer while unmounted. Refresh the
  // remembered batch on return so a study completed in the meantime cannot
  // remain displayed with an old "En cours" counter.
  if (rememberedVarBatchId) pf.openVarBatch(rememberedVarBatchId)
  pf.loadShockHistory(pf.view === 'global' ? 'global' : 'portfolio',
                      pf.view === 'global' ? null : pf.view)
  pf.loadShockHistory(pf.view === 'global' ? 'smile_global' : 'smile_portfolio',
                      pf.view === 'global' ? null : pf.view)
})

watch(() => pf.valuationDate, (value) => {
  if (!value || value > todayIso) return
  pf.loadRisk()
})

// A VaR study's poll loop uses setTimeout, not a Vue-managed watcher — must
// be stopped explicitly on unmount or it keeps polling (and holds a
// reference to this closed-over component) after the user navigates away.
onUnmounted(() => {
  pf.stopVarPolling()
  if (calculationTimer) clearInterval(calculationTimer)
})
</script>

<style scoped>
/* Keep every heading directly above its values, including nested detail tables. */
.risk-management-view table th,
.risk-management-view table td {
  text-align: center;
  vertical-align: middle;
}

.risk-management-view table td > .flex {
  justify-content: center;
}
</style>
