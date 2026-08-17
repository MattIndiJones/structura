<template>
  <!-- ── Tabs sans pricing requis ─────────────────────────────── -->
  <ProfileTab  v-if="tab === 'profile'" />
  <PathsTab    v-else-if="tab === 'paths'" />
  <ProbaTab    v-else-if="tab === 'proba'" />
  <BacktestTab   v-else-if="tab === 'backtest'" />
  <MtfTab        v-else-if="tab === 'mtf'" />
  <SimulationTab v-else-if="tab === 'simulation'" />
  <ScenarioGrid  v-else-if="tab === 'scenarios'" />

  <!-- ── Pas encore de résultat ───────────────────────────────── -->
  <div v-else-if="!store.result"
       class="flex flex-col items-center justify-center h-64 text-slate-600 gap-3">
    <div class="text-4xl">📊</div>
    <div class="text-sm font-medium">Lancez un pricing pour voir les résultats</div>
    <div class="text-xs text-slate-700">▶ Pricer → résultats en moins d'une seconde</div>
  </div>

  <!-- ── Résultats ─────────────────────────────────────────────── -->
  <div v-else-if="tab === 'results'" class="flex flex-col gap-4">
    <!-- Prix -->
    <div class="rounded-xl border border-blue-800/50 bg-blue-950/30 p-5">
      <div class="text-xs font-bold text-blue-400/70 uppercase tracking-wider mb-1">Prix équitable</div>
      <div class="flex items-baseline gap-4 flex-wrap">
        <span class="text-4xl font-black text-blue-400"><SensitiveValue>{{ f2(store.result.price) }} %</SensitiveValue></span>
        <span class="text-sm text-slate-500">
          IC 95% [<SensitiveValue>{{ f2(store.result.ic95[0]) }} %, {{ f2(store.result.ic95[1]) }} %</SensitiveValue>]
          &nbsp;±<SensitiveValue>{{ f2((store.result.ic95[1] - store.result.ic95[0]) / 2) }} %</SensitiveValue>
          <HelpTip text="Incertitude d'estimation Monte Carlo sur le prix lui-même (erreur standard × 1.96), pas une fourchette bid/offer de marché. Se resserre en 1/√N — pour la diviser par 2, il faut 4× plus de chemins." />
        </span>
      </div>
    </div>

    <!-- Tuiles stats -->
    <div class="grid grid-cols-2 sm:grid-cols-3 gap-3">
      <div class="stat-box">
        <div class="text-xs text-slate-500 mb-1">Médiane</div>
        <div class="text-xl font-bold text-slate-200"><SensitiveValue>{{ f2(store.result.median) }} %</SensitiveValue></div>
      </div>
      <div class="stat-box">
        <div class="text-xs text-slate-500 mb-1">VaR 5%
          <HelpTip text="5ᵉ percentile du payoff simulé (non actualisé) — la valeur en dessous de laquelle tombent 5% des chemins. C'est une VaR sur le remboursement final, pas sur le P&amp;L d'une position déjà en portefeuille." />
        </div>
        <div class="text-xl font-bold text-amber-400"><SensitiveValue>{{ f2(store.result.var5) }} %</SensitiveValue></div>
      </div>
      <div class="stat-box">
        <div class="text-xs text-slate-500 mb-1">P(retour &gt; 100%)
          <HelpTip text="Fraction des chemins simulés où le payoff (non actualisé) dépasse strictement le nominal — probabilité d'un scénario gagnant, pas la probabilité que le prix de marché dépasse le pair." />
        </div>
        <div class="text-xl font-bold text-green-400"><SensitiveValue>{{ f1(store.result.prob_gt100) }} %</SensitiveValue></div>
      </div>
      <div class="stat-box">
        <div class="text-xs text-slate-500 mb-1">N chemins</div>
        <div class="text-lg font-semibold text-slate-300"><SensitiveValue>{{ formatInt(store.result.n_eff) }}</SensitiveValue></div>
      </div>
      <div class="stat-box">
        <div class="text-xs text-slate-500 mb-1">Temps calcul</div>
        <div class="text-lg font-semibold text-slate-300"><SensitiveValue>{{ formatInt(store.result.elapsed_ms) }} ms</SensitiveValue></div>
      </div>
      <div class="stat-box">
        <div class="text-xs text-slate-500 mb-1">Spread P75–P25
          <HelpTip text="Écart interquartile du payoff simulé (P75 − P25) — dispersion typique de la distribution autour de la médiane, moins sensible aux valeurs extrêmes que l'écart-type." />
        </div>
        <div class="text-lg font-semibold text-slate-300"><SensitiveValue>{{ spreadP75P25 }}</SensitiveValue></div>
      </div>
    </div>

    <!-- Histogramme -->
    <div class="card">
      <div class="flex flex-col gap-1 mb-3">
        <div class="text-xs font-bold text-slate-400 uppercase tracking-wider">Distribution des payoffs
          <HelpTip text="Histogramme des payoffs bruts (non actualisés) sur tous les chemins simulés. Barres bleues = payoff ≥ prix équitable actualisé (scénarios au-dessus du prix), barres grises = en dessous." />
        </div>
        <div class="text-[11px] text-slate-600">
          <SensitiveValue>
            Payoffs bruts non actualisés · {{ formatInt(store.result.payoffs?.length) }} valeurs
            <template v-if="store.result.payoffs?.length">
              · min {{ formatPercent(store.result.payoffs[0] * 100, 2) }} · max {{ formatPercent(store.result.payoffs[store.result.payoffs.length - 1] * 100, 2) }}
            </template>
          </SensitiveValue>
        </div>
      </div>
      <SensitiveChart>
        <canvas ref="histCanvas" style="max-height:220px"></canvas>
      </SensitiveChart>
    </div>

    <!-- Résumé market data — ce qui a produit CE prix -->
    <div v-if="inputs" class="card flex flex-col gap-5">
      <div class="text-xs font-bold text-slate-400 uppercase tracking-wider">
        Données utilisées pour ce pricing
      </div>

      <!-- ── Sous-jacent(s) ───────────────────────────────────────── -->
      <div class="flex flex-col gap-2">
        <div class="text-[10px] font-bold text-slate-600 uppercase tracking-widest">Sous-jacent(s)</div>
        <div class="flex flex-col gap-2">
          <div v-for="(u, i) in inputs.underlyings" :key="i"
               class="flex flex-wrap items-center gap-x-4 gap-y-1 bg-slate-800/50 rounded-lg px-3 py-2">
            <span class="font-semibold text-slate-200 text-sm min-w-[80px]">
              <SensitiveValue placeholder="SJ">{{ demo.underlyingLabel(u.name, i) }}</SensitiveValue>
            </span>
            <span v-if="u.ticker" class="font-mono text-xs text-blue-400">
              <SensitiveValue>{{ u.ticker }}</SensitiveValue>
            </span>
            <span class="text-xs text-slate-400">
              σ <span class="font-mono font-semibold text-slate-200"><SensitiveValue>{{ formatPercent(u.sigma, 2) }}</SensitiveValue></span>
            </span>
            <span class="text-xs text-slate-400">
              q <span class="font-mono font-semibold text-slate-200"><SensitiveValue>{{ formatPercent(u.q, 3) }}</SensitiveValue></span>
            </span>
            <span v-if="showRhoRS" class="text-xs text-slate-400">
              ρ(r,S) <span class="font-mono font-semibold text-slate-200"><SensitiveValue>{{ formatPercent(u.rho_rS, 2) }}</SensitiveValue></span>
            </span>
            <span class="text-xs text-slate-600">{{ u.ccy }}</span>
          </div>
        </div>
        <!-- Corrélation multi-actifs -->
        <div v-if="inputs.underlyings.length > 1" class="flex flex-wrap gap-2 text-xs">
          <template v-for="(row, i) in inputs.corrMatrix" :key="i">
            <template v-for="(v, j) in row" :key="j">
              <span v-if="j > i" class="bg-slate-800 border border-slate-700 rounded px-2 py-0.5 font-mono text-slate-400">
                ρ({{ demo.underlyingLabel(inputs.underlyings[i].name, i) }},{{ demo.underlyingLabel(inputs.underlyings[j].name, j) }})
                = <SensitiveValue class="text-slate-200">{{ formatNumber(v, 2) }}</SensitiveValue>
              </span>
            </template>
          </template>
        </div>
      </div>

      <!-- ── Caractéristiques économiques ────────────────────────── -->
      <div class="flex flex-col gap-2">
        <div class="text-[10px] font-bold text-slate-600 uppercase tracking-widest">Caractéristiques économiques</div>
        <div class="grid grid-cols-2 sm:grid-cols-3 gap-2 text-xs">

          <!-- Maturité -->
          <div class="bg-slate-800/50 rounded-lg px-3 py-2">
            <div class="text-slate-500 mb-1">Maturité</div>
            <div class="font-mono font-bold text-slate-100 text-base">
              <SensitiveValue>{{ formatNumber(store.result.t_max_effective ?? inputs.T, 2) }} ans</SensitiveValue>
            </div>
            <div v-if="store.result.t_max_effective && Math.abs(store.result.t_max_effective - inputs.T) > 0.01"
                 class="text-amber-500 text-[10px] mt-0.5">
              ↗ depuis <SensitiveValue>{{ formatNumber(inputs.T, 2) }} ans</SensitiveValue> (CONSTAT)
            </div>
          </div>

          <!-- Fugit — seulement si le script a un STOP -->
          <div v-if="inputs.hasStop && store.result.fugit != null" class="bg-slate-800/50 rounded-lg px-3 py-2">
            <div class="text-slate-500 mb-1">Fugit <span class="text-slate-600 font-normal">(durée moy.)</span>
              <HelpTip text="Durée de vie moyenne pondérée par probabilité E[τ] — la date à laquelle le produit s'arrête en moyenne (rappel anticipé ou échéance). Sert de point d'interpolation sur la courbe de taux pour ce produit à STOP, puisqu'il n'a pas une maturité unique fixe." />
            </div>
            <div class="font-mono font-bold text-amber-300 text-base">
              <SensitiveValue>{{ formatNumber(store.result.fugit, 2) }} ans</SensitiveValue>
            </div>
            <div class="text-[10px] text-slate-600 mt-0.5">E[τ] sur {{ formatInt(store.result.n_eff) }} chemins</div>
          </div>

          <!-- Taux / courbe -->
          <div class="bg-slate-800/50 rounded-lg px-3 py-2"
               :class="inputs.yieldCurvePillars?.length ? 'col-span-2 sm:col-span-1' : ''">
            <div class="text-slate-500 mb-1">
              Taux
              <span :class="inputs.yieldCurvePillars?.length ? 'text-green-500' : 'text-slate-600'"
                    class="text-[10px] font-semibold ml-1">
                {{ inputs.yieldCurvePillars?.length ? '● Courbe' : '● Plat' }}
              </span>
            </div>
            <!-- Taux plat -->
            <template v-if="!inputs.yieldCurvePillars?.length">
              <div class="font-mono font-bold text-slate-100 text-base">
                <SensitiveValue>{{ formatPercent(inputs.r, 2) }}</SensitiveValue>
              </div>
            </template>
            <!-- Courbe de taux : points clés -->
            <template v-else>
              <div class="flex flex-col gap-1 text-xs">
                <div class="flex items-center justify-between gap-3">
                  <span class="text-slate-500">Court terme</span>
                  <span class="font-mono font-semibold text-slate-200">
                    <SensitiveValue>{{ formatPercent(interpRate(inputs.yieldCurvePillars[0].T, inputs.yieldCurvePillars), 2) }}</SensitiveValue>
                    <span class="text-slate-600 text-[10px] ml-1">{{ inputs.yieldCurvePillars[0].label }}</span>
                  </span>
                </div>
                <div v-if="inputs.hasStop && store.result.fugit != null"
                     class="flex items-center justify-between gap-3">
                  <span class="text-amber-400/80">Fugit</span>
                  <span class="font-mono font-semibold text-amber-300">
                    <SensitiveValue>{{ formatPercent(interpRate(store.result.fugit, inputs.yieldCurvePillars), 2) }}</SensitiveValue>
                    <span class="text-slate-600 text-[10px] ml-1">{{ formatNumber(store.result.fugit, 2) }} ans</span>
                  </span>
                </div>
                <div class="flex items-center justify-between gap-3">
                  <span class="text-slate-500">Maturité</span>
                  <span class="font-mono font-semibold text-slate-200">
                    <SensitiveValue>{{ formatPercent(interpRate(store.result.t_max_effective ?? inputs.T, inputs.yieldCurvePillars), 2) }}</SensitiveValue>
                    <span class="text-slate-600 text-[10px] ml-1">{{ formatNumber(store.result.t_max_effective ?? inputs.T, 2) }} ans</span>
                  </span>
                </div>
              </div>
            </template>
          </div>

          <!-- Modèle vol -->
          <div class="bg-slate-800/50 rounded-lg px-3 py-2">
            <div class="text-slate-500 mb-1">Modèle vol
              <HelpTip text="Dynamique du sous-jacent simulée sous la mesure risque-neutre. Constant = Black-Scholes (vol figée) ; Heston/SABR = vol stochastique, capture le smile mais plus lent et plus sensible aux paramètres de calibration ; Local Vol = surface de vol locale à la Dupire." />
            </div>
            <div class="font-mono font-semibold text-slate-200 text-sm">{{ modelLabel(inputs.model) }}</div>
          </div>

          <!-- Modèle taux -->
          <div class="bg-slate-800/50 rounded-lg px-3 py-2">
            <div class="text-slate-500 mb-1">Modèle taux
              <HelpTip text="Déterministe = taux plat/courbe figée, pas de risque de taux dans la simulation. ABM/Hull-White = taux court stochastique — affecte l'actualisation ET, si le sous-jacent a un ρ(r,S) non nul, la trajectoire simulée elle-même." />
            </div>
            <div class="font-mono font-semibold text-slate-200 text-sm"><SensitiveValue>{{ rateModelLabel(inputs) }}</SensitiveValue></div>
          </div>

        </div>
      </div>

      <!-- ── Simulation ───────────────────────────────────────────── -->
      <div class="flex flex-col gap-2">
        <div class="text-[10px] font-bold text-slate-600 uppercase tracking-widest">Simulation</div>
        <div class="flex flex-wrap gap-2 text-xs">
          <span class="bg-slate-800 border border-slate-700 rounded px-2.5 py-1 text-slate-400">
            N <span class="font-mono font-semibold text-slate-200 ml-1"><SensitiveValue>{{ formatInt(inputs.N) }}</SensitiveValue></span>
            <HelpTip text="Nombre de chemins Monte Carlo demandé. Plus N est grand, plus l'IC 95% affiché sur le prix se resserre (en 1/√N) — mais le temps de calcul croît linéairement." />
          </span>
          <span class="bg-slate-800 border border-slate-700 rounded px-2.5 py-1 text-slate-400">
            Seed <span class="font-mono font-semibold text-slate-200 ml-1"><SensitiveValue>{{ inputs.seed }}</SensitiveValue></span>
            <HelpTip text="Graine du générateur aléatoire — même seed + mêmes paramètres = mêmes chemins simulés, donc même prix exact. Utile pour reproduire un résultat ou pour le bump-and-reprice des Greeks (CRN)." />
          </span>
          <span class="bg-slate-800 border border-slate-700 rounded px-2.5 py-1"
                :class="inputs.antithetic ? 'text-green-400 border-green-900' : 'text-slate-500'">
            {{ inputs.antithetic ? '✓ Antithétique' : 'Sans antithétique' }}
            <HelpTip text="Variance réduite : chaque chemin simulé est apparié à son symétrique (browniens opposés). Réduit le bruit MC sur le prix à N égal, sans biais — désactiver seulement pour diagnostiquer un problème de convergence." />
          </span>
        </div>
      </div>

      <!-- ── Paramètres du script ─────────────────────────────────── -->
      <div v-if="inputs.paramsUsed.length" class="flex flex-col gap-2">
        <div class="text-[10px] font-bold text-slate-600 uppercase tracking-widest">Paramètres du script</div>
        <div class="flex flex-wrap gap-2">
          <span v-for="p in inputs.paramsUsed" :key="p.name"
                class="font-mono bg-slate-800 border border-slate-700 rounded px-2.5 py-1 text-xs">
            <span class="text-slate-500">{{ p.name }}</span>
            <span class="text-slate-100 font-bold ml-1">=<SensitiveValue>{{ p.value }}{{ p.is_pct ? '%' : '' }}</SensitiveValue></span>
          </span>
        </div>
      </div>

      <!-- ── Dates clés ───────────────────────────────────────────── -->
      <div class="flex flex-col gap-2">
        <div class="text-[10px] font-bold text-slate-600 uppercase tracking-widest">Dates clés</div>
        <div class="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
          <div class="result-date-card bg-slate-800/50 rounded-lg px-3 py-2">
            <div class="result-date-label text-slate-500 mb-1">Date de trade
              <HelpTip text="Date d'accord des termes entre les parties. Sert de référence commerciale/juridique — n'intervient pas dans le calcul du prix lui-même (c'est value date qui fixe t=0)." />
            </div>
            <div class="font-mono font-semibold text-slate-200"><SensitiveValue>{{ formatDate(inputs.trade_date) }}</SensitiveValue></div>
          </div>
          <div class="result-date-card bg-slate-800/50 rounded-lg px-3 py-2">
            <div class="result-date-label text-slate-500 mb-1">Date de strike <span class="text-slate-600 font-normal">(fixing S₀)</span>
              <HelpTip text="Date à laquelle le niveau initial S₀ des sous-jacents est figé — la référence par rapport à laquelle toutes les performances (WOF, barrières...) sont mesurées ensuite." />
            </div>
            <div class="font-mono font-semibold text-slate-200"><SensitiveValue>{{ formatDate(inputs.strike_date) }}</SensitiveValue></div>
          </div>
          <div class="result-date-card bg-slate-800/50 rounded-lg px-3 py-2">
            <div class="result-date-label text-slate-500 mb-1">Date de valeur <span class="text-slate-600 font-normal">(t=0)</span>
              <HelpTip text="Date d'échange effectif du nominal — le t=0 depuis lequel tous les flux sont actualisés. Généralement strike date + 2 jours ouvrés (délai de règlement-livraison standard)." />
            </div>
            <div class="font-mono font-semibold text-slate-200"><SensitiveValue>{{ formatDate(inputs.value_date) }}</SensitiveValue></div>
          </div>
          <div class="result-date-card bg-slate-800/50 rounded-lg px-3 py-2">
            <div class="result-date-label text-slate-500 mb-1">Maturité</div>
            <div class="font-mono font-semibold text-slate-200"><SensitiveValue>{{ formatDate(maturityDateStr) }}</SensitiveValue></div>
          </div>
        </div>
      </div>

      <!-- ── Dates d'observation ──────────────────────────────────── -->
      <div v-if="observationRows.length" class="flex flex-col gap-2">
        <div class="text-[10px] font-bold text-slate-600 uppercase tracking-widest">Dates d'observation</div>
        <div class="max-h-56 overflow-y-auto border border-slate-800 rounded table-shell" tabindex="0" role="region">
          <table class="w-full text-xs border-collapse">
            <thead class="sticky top-0 bg-slate-900">
              <tr class="border-b border-slate-700">
                <th class="text-left py-1 px-2 text-slate-500 font-semibold text-[10px] uppercase">#</th>
                <th class="text-left py-1 px-2 text-slate-500 font-semibold text-[10px] uppercase">Label</th>
                <th class="text-left py-1 px-2 text-slate-500 font-semibold text-[10px] uppercase">Date</th>
                <th class="text-right py-1 px-2 text-slate-500 font-semibold text-[10px] uppercase num">T (ans)</th>
                <th class="text-right py-1 px-2 text-slate-500 font-semibold text-[10px] uppercase">Statut</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(ev, i) in observationRows" :key="i" class="border-b border-slate-800/60">
                <td class="py-1 px-2 text-slate-500">{{ i + 1 }}</td>
                <td class="py-1 px-2 text-slate-300">{{ ev.label }}</td>
                <td class="py-1 px-2 font-mono text-slate-300"><SensitiveValue>{{ formatDate(ev.date) }}</SensitiveValue></td>
                <td class="py-1 px-2 font-mono text-right num text-slate-400">{{ formatNumber(ev.t, 2) }}</td>
                <td class="py-1 px-2 text-right text-[10px]"
                    :class="ev.isFuture ? 'text-slate-500' : 'text-amber-400'">
                  {{ ev.isFuture ? 'à venir' : 'passé' }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- ── Spots ────────────────────────────────────────────────── -->
      <div class="flex flex-col gap-2">
        <div class="text-[10px] font-bold text-slate-600 uppercase tracking-widest">Spots (à la strike date)</div>
        <div class="flex flex-col gap-2">
          <div v-for="(u, i) in inputs.underlyings" :key="i"
               class="flex flex-wrap items-center gap-3 bg-slate-800/50 rounded-lg px-3 py-2 text-xs">
            <span class="font-semibold text-slate-200 min-w-[80px]">
              <SensitiveValue placeholder="SJ">{{ demo.underlyingLabel(u.name, i) }}</SensitiveValue>
            </span>
            <template v-if="u.ticker">
              <span v-if="spotState[u.ticker]?.loading" class="text-slate-500">chargement…</span>
              <template v-else-if="spotState[u.ticker]?.value">
                <span class="font-mono font-bold text-slate-100">
                  <SensitiveValue>{{ formatNumber(spotState[u.ticker].value.close, 2) }}</SensitiveValue>
                </span>
                <span class="text-slate-600">au {{ formatDate(spotState[u.ticker].value.date) }}</span>
              </template>
              <span v-else class="text-slate-600">non disponible</span>
              <button class="text-blue-400 hover:underline ml-auto"
                      :disabled="spotState[u.ticker]?.refreshing"
                      @click="refreshSpot(u.ticker)">
                {{ spotState[u.ticker]?.refreshing ? '…' : '↺ Actualiser' }}
              </button>
            </template>
            <span v-else class="text-slate-600">100% (référence normalisée, aucun ticker)</span>
          </div>
        </div>
      </div>
    </div>
  </div>

  <!-- ── Flux ──────────────────────────────────────────────────── -->
  <div v-else-if="tab === 'flux'" class="flex flex-col gap-4">
    <div v-if="fluxGroups.length === 0"
         class="flex flex-col items-center justify-center py-16 gap-2 text-slate-600">
      <div class="text-3xl">💰</div>
      <div class="text-sm font-medium">Aucun flux — vérifiez les instructions PAY dans le script</div>
    </div>
    <template v-else>
      <!-- Résumé -->
      <div class="grid grid-cols-3 gap-3">
        <div class="stat-box min-w-0">
          <div class="text-xs text-slate-500 mb-1">Prix MC (PV Σ)</div>
          <div class="text-xl font-bold text-blue-400"><SensitiveValue>{{ f2(store.result.price) }} %</SensitiveValue></div>
        </div>
        <div class="stat-box min-w-0">
          <div class="text-xs text-slate-500 mb-1">Dates de flux</div>
          <div class="text-xl font-bold text-slate-200">{{ formatInt(fluxGroups.length) }}</div>
        </div>
        <div class="stat-box min-w-0">
          <div class="text-xs text-slate-500 mb-1">N chemins</div>
          <div class="text-xl font-bold text-slate-300"><SensitiveValue>{{ formatInt(store.result.n_eff) }}</SensitiveValue></div>
        </div>
      </div>

      <!-- Table -->
      <div class="card overflow-x-auto table-shell" tabindex="0" role="region">
        <div class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-1">
          💰 Décomposition des flux — PV par composante
        </div>
        <div class="text-[11px] text-slate-600 mb-4">
          Contribution PV = E[CF] × DF · la somme des lignes reconstitue le prix MC
        </div>
        <table class="w-full min-w-[520px] text-xs border-collapse">
          <thead>
            <tr class="bg-slate-800/60 border-b-2 border-slate-700">
              <th class="text-left py-1.5 px-2 whitespace-nowrap">Date</th>
              <th class="text-left py-1.5 px-2">Expression</th>
              <th class="text-right py-1.5 px-2 whitespace-nowrap num">P(actif)
                <HelpTip align="right" text="Fraction des chemins simulés où cette instruction PAY a effectivement produit un flux (ex : condition IF vraie, produit pas encore rappelé). 100% = flux systématique." />
              </th>
              <th class="text-right py-1.5 px-2 whitespace-nowrap num">E[CF]
                <HelpTip align="right" text="Espérance du flux brut, non actualisé, moyennée sur tous les chemins (y compris ceux où il vaut 0). C'est le montant avant application du facteur d'actualisation DF." />
              </th>
              <th class="text-right py-1.5 px-2 whitespace-nowrap num">DF
                <HelpTip align="right" text="Facteur d'actualisation implicite = PV ÷ E[CF]. Sous taux déterministes c'est exp(−r·t) ; sous taux stochastiques c'est l'espérance conditionnelle E[B(0,t) | ce flux se déclenche], donc peut différer légèrement de exp(−r·t)." />
              </th>
              <th class="text-right py-1.5 px-2 whitespace-nowrap num">Contrib. PV
                <HelpTip align="right" text="Contribution actualisée de cette ligne au prix total = E[CF] × DF. La somme de toutes les lignes de toutes les dates redonne exactement le Prix équitable de l'onglet Résultats." />
              </th>
            </tr>
          </thead>
          <tbody>
            <template v-for="grp in fluxGroups" :key="grp.tKey">
              <tr v-for="(row, ri) in grp.rows" :key="row.key"
                  :class="[
                    ri < grp.rows.length - 1 ? 'border-b border-slate-800' : 'border-b-2 border-slate-700',
                    row.pv < 0 ? 'bg-red-950/20' : ''
                  ]">
                <td class="py-1.5 px-2 font-bold text-slate-300 whitespace-nowrap align-top text-[10px]">
                  <span v-if="ri === 0">{{ grp.label }}</span>
                </td>
                <td class="py-1.5 px-2 font-mono text-[11px]"
                    :class="row.pv < 0 ? 'text-red-400' : 'text-slate-500'">{{ row.lbl }}</td>
                <td class="py-1.5 px-2 text-right num text-slate-400"><SensitiveValue>{{ formatPercent(row.pAct, 1) }}</SensitiveValue></td>
                <td class="py-1.5 px-2 text-right num font-semibold font-mono"
                    :class="row.eCF >= 0 ? 'text-slate-300' : 'text-red-400'">
                  <SensitiveValue>{{ formatSignedPercent(row.eCF, 2) }}</SensitiveValue>
                </td>
                <td class="py-1.5 px-2 text-right num font-mono text-slate-400">
                  <SensitiveValue>{{ formatNumber(row.df, 4) }}</SensitiveValue>
                </td>
                <td class="py-1.5 px-2 text-right num font-bold font-mono"
                    :class="row.pv >= 0 ? 'text-green-400' : 'text-red-400'">
                  <SensitiveValue>{{ formatSignedPercent(row.pv, 3) }}</SensitiveValue>
                </td>
              </tr>
            </template>
          </tbody>
          <tfoot>
            <tr class="bg-slate-800/60 border-t-2 border-slate-600">
              <td colspan="5" class="py-2 px-2 font-black text-slate-200">= Prix total</td>
              <td class="py-2 px-2 text-right num font-black text-blue-400 text-sm">
                <SensitiveValue>{{ formatPercent(fluxTotal, 2) }}</SensitiveValue>
              </td>
            </tr>
          </tfoot>
        </table>
      </div>
    </template>
  </div>

  <!-- ── Greeks ────────────────────────────────────────────────── -->
  <div v-else-if="tab === 'greeks'" class="flex flex-col gap-4">
    <div v-if="!hasGreeks"
         class="flex flex-col items-center justify-center py-16 gap-3 text-slate-600">
      <div class="text-3xl">∂</div>
      <div class="text-sm font-medium">Cliquez "∂ Greeks" dans le header</div>
      <div class="text-xs">Cochez les Greeks dans l'onglet Paramètres puis relancez</div>
      <button class="btn-secondary text-xs mt-2" :disabled="store.loading" @click="store.runGreeks()">
        Calculer les Greeks
      </button>
    </div>
    <template v-else>
      <div class="card">
        <div class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-4">
          Greeks — CRN bump-and-reprice (seed <SensitiveValue>{{ inputs?.seed ?? store.globalParams.seed }}</SensitiveValue>)
          <HelpTip width="w-72" text="Chaque Greek est estimé en repricant avec un paramètre de marché légèrement décalé (bump), en réutilisant EXACTEMENT les mêmes nombres aléatoires (Common Random Numbers) que le pricing de référence. Ça annule l'essentiel du bruit Monte Carlo dans la différence bumpée-référence — sans CRN, les Greeks seraient beaucoup trop instables pour être utilisables." />
        </div>
        <div class="grid grid-cols-2 sm:grid-cols-3 gap-3">
          <div v-for="entry in greekEntries" :key="entry.name" class="stat-box min-w-0">
            <div class="text-xs text-slate-500 mb-1 font-mono">{{ gLabel(entry.name) }}
              <HelpTip :text="gDesc(entry.name)" />
            </div>
            <div class="text-base font-bold font-mono"
                 :class="entry.displayValue > 0 ? 'text-green-400' : entry.displayValue < 0 ? 'text-red-400' : 'text-slate-400'">
              <SensitiveValue>{{ fmtG(entry.displayValue) }}</SensitiveValue>
            </div>
            <div class="text-[11px] text-slate-600 mt-0.5">{{ gUnit(entry.name) }}</div>
          </div>
        </div>
        <div v-if="vegaScopeNote || thetaEventNote" class="flex flex-col gap-2 mt-3">
          <div v-if="vegaScopeNote" class="rounded-lg border border-slate-700 bg-slate-800/40 px-3 py-2 text-[11px] text-slate-500">
            {{ vegaScopeNote }}
          </div>
          <div v-if="thetaEventNote" class="rounded-lg border border-amber-800/50 bg-amber-950/20 px-3 py-2 text-[11px] text-amber-500">
            {{ thetaEventNote }}
          </div>
        </div>
      </div>
      <div v-if="greekEntries.length" class="card overflow-x-auto table-shell" tabindex="0" role="region">
        <div class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3">Lecture par choc</div>
        <table class="w-full min-w-[500px] text-xs">
          <thead>
            <tr class="border-b border-slate-700 text-slate-500">
              <th class="pb-2 pr-4 text-left font-semibold">Greek</th>
              <th class="pb-2 pr-4 text-right font-semibold num">Valeur</th>
              <th class="pb-2 text-left font-semibold">Interprétation</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="entry in greekEntries" :key="entry.name"
                class="border-b border-slate-800/50">
              <td class="py-1.5 pr-4 font-mono font-semibold text-slate-300">{{ gLabel(entry.name) }}</td>
              <td class="py-1.5 pr-4 font-mono num text-right"
                  :class="entry.displayValue > 0 ? 'text-green-400' : entry.displayValue < 0 ? 'text-red-400' : 'text-slate-400'">
                <SensitiveValue>{{ fmtG(entry.displayValue) }}</SensitiveValue>
              </td>
              <td class="py-1.5 text-slate-500"><SensitiveValue>{{ gInterp(entry.name, entry.rawValue) }}</SensitiveValue></td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
  </div>

  <!-- ── Fallback (tab inconnu) ─────────────────────────────────── -->
  <div v-else class="flex flex-col items-center justify-center h-64 text-slate-600 gap-2">
    <div class="text-4xl">📊</div>
    <div class="text-sm">Sélectionnez un onglet</div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch, nextTick, onMounted, onUnmounted } from 'vue'
import { usePricingStore } from '../stores/pricing.js'
import { useDemoModeStore } from '../stores/demoMode.js'
import { demoChartOptions } from '../composables/useSensitiveChart.js'
import { chartTheme, applyChartTheme } from '../charts/theme.js'
import { Chart, BarElement, BarController, CategoryScale, LinearScale, Tooltip } from 'chart.js'
import ProfileTab  from './ProfileTab.vue'
import PathsTab    from './PathsTab.vue'
import ProbaTab    from './ProbaTab.vue'
import BacktestTab from './BacktestTab.vue'
import MtfTab      from './MtfTab.vue'
import SimulationTab from './SimulationTab.vue'
import ScenarioGrid from './ScenarioGrid.vue'
import SensitiveValue from './SensitiveValue.vue'
import SensitiveChart from './SensitiveChart.vue'
import HelpTip from './HelpTip.vue'
import { formatDate, formatGreek, formatInt, formatNumber, formatPercent } from '../utils/format.js'

Chart.register(BarElement, BarController, CategoryScale, LinearScale, Tooltip)
applyChartTheme(Chart)

const store = usePricingStore()
const demo = useDemoModeStore()
const histCanvas = ref(null)
let histChart = null

const tab = computed(() => store.rightTab)

// ── Helpers format ────────────────────────────────────────────────
const f2 = v => v != null ? formatNumber(v * 100, 2) : '—'
const f1 = v => v != null ? formatNumber(v * 100, 1) : '—'
const formatSignedPercent = (value, decimals) =>
  `${value >= 0 ? '+' : ''}${formatPercent(value, decimals)}`

const spreadP75P25 = computed(() => {
  const p = store.result?.payoffs
  if (!p || p.length < 4) return '—'
  const p25 = p[Math.floor(p.length * 0.25)]
  const p75 = p[Math.floor(p.length * 0.75)]
  return formatPercent((p75 - p25) * 100, 2)
})

// ── Résumé market data (snapshot pris au moment du pricing) ───────
const inputs = computed(() => store.result?._inputs ?? null)
const showRhoRS = computed(() => inputs.value?.rateModel !== 'deterministic')

// ── Dates clés + calendrier d'observation ─────────────────────────
const todayStr = () => new Date().toISOString().split('T')[0]

function addDaysStr(isoDate, days) {
  const d = new Date(isoDate)
  d.setDate(d.getDate() + Math.round(days))
  return d.toISOString().split('T')[0]
}

const maturityDateStr = computed(() => {
  if (!inputs.value?.value_date) return null
  const T = store.result?.t_max_effective || inputs.value.T
  return addDaysStr(inputs.value.value_date, T * 365.25)
})

const observationRows = computed(() => {
  if (!store.result?.flux_table || !inputs.value?.value_date) return []
  const times = [...new Set(Object.values(store.result.flux_table).map(e => e.t))].sort((a, b) => a - b)
  const vd = inputs.value.value_date
  const now = todayStr()
  const maturityT = store.result?.t_max_effective ?? inputs.value.T
  return times.map((t, idx) => {
    const date = addDaysStr(vd, t * 365.25)
    return {
      label: Math.abs(t - maturityT) < 0.01 ? 'Maturité' : `Obs. ${idx + 1}`,
      date, t, isFuture: date > now,
    }
  })
})

// ── Spots (store Parquet — lecture seule + bouton d'actualisation) ─
const spotState = reactive({})

async function loadSpot(ticker) {
  if (!ticker) return
  if (!spotState[ticker]) spotState[ticker] = { loading: false, refreshing: false, value: null }
  spotState[ticker].loading = true
  try {
    spotState[ticker].value = await store.fetchStoredSpot(ticker, inputs.value?.strike_date || todayStr())
  } finally {
    spotState[ticker].loading = false
  }
}

async function refreshSpot(ticker) {
  if (!spotState[ticker]) spotState[ticker] = { loading: false, refreshing: false, value: null }
  spotState[ticker].refreshing = true
  try {
    await store.refreshStoredSpot(ticker, ticker)
    await loadSpot(ticker)
  } catch (e) {
    spotState[ticker].error = e.message
  } finally {
    spotState[ticker].refreshing = false
  }
}

watch(inputs, (inp) => {
  if (!inp) return
  for (const u of inp.underlyings) {
    if (u.ticker) loadSpot(u.ticker)
  }
}, { immediate: true })

const MODEL_LABELS = { constant: 'Constant (GBM)', heston: 'Heston QE', sabr: 'SABR (Hagan)', localvol: 'Local Vol (Dupire)' }
const modelLabel = m => MODEL_LABELS[m] || m

function rateModelLabel(inp) {
  if (inp.rateModel === 'deterministic') return 'Déterministe'
  if (inp.rateModel === 'abm') return `ABM (σ=${inp.sigma_r}%)`
  return `Hull-White (σ=${inp.sigma_r}%, a=${inp.a_r})`
}

function interpRate(t, pillars) {
  if (!pillars || pillars.length === 0) return 0
  if (t <= pillars[0].T) return pillars[0].rate
  if (t >= pillars[pillars.length - 1].T) return pillars[pillars.length - 1].rate
  for (let i = 0; i < pillars.length - 1; i++) {
    if (t >= pillars[i].T && t <= pillars[i + 1].T) {
      const frac = (t - pillars[i].T) / (pillars[i + 1].T - pillars[i].T)
      return pillars[i].rate + frac * (pillars[i + 1].rate - pillars[i].rate)
    }
  }
  return pillars[pillars.length - 1].rate
}

// ── Histogramme ───────────────────────────────────────────────────
async function drawHist() {
  if (tab.value !== 'results') return
  await nextTick()
  if (!histCanvas.value || !store.result?.payoffs?.length) return
  if (histChart) { histChart.destroy(); histChart = null }

  const arr = store.result.payoffs.map(p => p * 100)
  const mn = arr.reduce((a, b) => Math.min(a, b), Infinity)
  const mx = arr.reduce((a, b) => Math.max(a, b), -Infinity)
  const isDegenerate = Math.abs(mx - mn) < 1e-8
  const bins = isDegenerate ? 9 : 40
  const padding = isDegenerate ? Math.max(Math.abs(mn) * 0.0025, 0.25) : 0
  const histMin = mn - padding
  const histMax = mx + padding
  const w = (histMax - histMin) / bins
  const counts = new Array(bins).fill(0)
  const binDecimals = w < 0.1 ? 2 : 1
  const leftEdges = Array.from({ length: bins }, (_, i) => histMin + i * w)
  const labels = leftEdges.map(left => formatPercent(left, binDecimals))
  arr.forEach(v => { counts[Math.min(bins - 1, Math.max(0, Math.floor((v - histMin) / w)))]++ })
  const price = store.result.price * 100

  histChart = new Chart(histCanvas.value, {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        data: counts,
        backgroundColor: leftEdges.map(left => left + w >= price ? chartTheme.primaryFill : 'rgba(122,116,105,.35)'),
        borderColor:     leftEdges.map(left => left + w >= price ? chartTheme.primary : 'rgba(122,116,105,.5)'),
        borderWidth: 1, borderRadius: 2,
      }],
    },
    options: demoChartOptions({
      responsive: true, maintainAspectRatio: true,
      plugins: { legend: { display: false },
        tooltip: { callbacks: {
          title: i => {
            const left = leftEdges[i[0].dataIndex]
            return `Payoff : ${formatPercent(left, binDecimals)} — ${formatPercent(left + w, binDecimals)}`
          },
          label: i => `${formatInt(i.raw)} chemins`,
        } } },
      scales: {
        x: { ticks: { autoSkip: true, maxTicksLimit: 7, maxRotation: 0, font: { size: 10 } } },
        y: { beginAtZero: true, ticks: { maxTicksLimit: 6, precision: 0, font: { size: 10 }, callback: value => formatInt(value) } },
      },
    }, demo.enabled),
  })
}

watch(() => store.result, drawHist)
watch(tab, t => { if (t === 'results') drawHist() })
watch(() => demo.enabled, drawHist)   // instant — re-render axes/tooltip on toggle
onMounted(() => { if (tab.value === 'results') drawHist() })
onUnmounted(() => { if (histChart) histChart.destroy() })

// ── Flux ──────────────────────────────────────────────────────────
function tToCalDate(t) {
  const valueDate = inputs.value?.value_date
  if (!valueDate) return t < 0.005 ? 'T₀' : `T + ${formatNumber(t, 2)} ans`
  return formatDate(addDaysStr(valueDate, t * 365.25))
}

const fluxGroups = computed(() => {
  const ft = store.result?.flux_table
  if (!ft) return []
  const N = store.result.n_eff || store.result.n_paths || 1
  const byDate = new Map()

  for (const [key, d] of Object.entries(ft)) {
    if (!d || typeof d.t !== 'number') continue
    const tKey = d.t.toFixed(6)
    if (!byDate.has(tKey)) {
      const t = d.t
      byDate.set(tKey, { t, tKey, label: tToCalDate(t), rows: [] })
    }
    const pvRaw = typeof d.pv === 'number' ? d.pv : (d.sum ?? 0)
    const eCF   = (d.sum ?? 0) / N * 100
    const pv    = pvRaw / N * 100
    byDate.get(tKey).rows.push({
      key,
      lbl:    d.lbl ?? key,
      n:      d.n ?? 0,
      pAct:   (d.n ?? 0) / N * 100,
      eCF,
      pv,
      df:     typeof d.df === 'number' ? d.df : null,
    })
  }

  return [...byDate.values()]
    .sort((a, b) => a.t - b.t)
    .map(g => ({ ...g, rows: [...g.rows].sort((a, b) => b.pv - a.pv) }))
})

const fluxTotal = computed(() =>
  fluxGroups.value.reduce((s, g) => s + g.rows.reduce((rs, r) => rs + r.pv, 0), 0)
)

// ── Greeks ────────────────────────────────────────────────────────
const fmtG = formatGreek

const GREEK_SYM = { delta: 'Δ', gamma: 'Γ', vega: 'ν', theta: 'Θ', rho: 'ρ', corr: 'ρᵢⱼ' }
const GREEK_NAME = { delta: 'Delta', gamma: 'Gamma', vega: 'Vega', theta: 'Theta', rho: 'Rho', corr: 'Corrélation' }

const gType = name => name.match(/^([a-z]+)/)?.[1] || name

const gDisplayValue = (name, value) => {
  const type = gType(name)
  if (type === 'gamma') return value * 0.01
  if (type === 'theta') return value * 100
  if (type === 'corr') return value * 5
  return value
}

const greekEntries = computed(() => Object.entries(store.result?.greeks || {})
  .filter(([, value]) => typeof value === 'number' && Number.isFinite(value))
  .map(([name, rawValue]) => ({ name, rawValue, displayValue: gDisplayValue(name, rawValue) })))

const thetaEvent = computed(() => store.result?.greeks?.theta_event || null)
const vegaScope = computed(() => store.result?.greeks?.vega_scope || null)

const hasGreeks = computed(() => greekEntries.value.length > 0 || !!thetaEvent.value || !!vegaScope.value)

const gLabel = name => {
  const pair = name.match(/^corr_(\d+)_(\d+)$/)
  if (pair) {
    const i = Number(pair[1]) - 1
    const j = Number(pair[2]) - 1
    const left = store.underlyings[i] ? demo.underlyingLabel(store.underlyings[i].name, i) : `S${i + 1}`
    const right = store.underlyings[j] ? demo.underlyingLabel(store.underlyings[j].name, j) : `S${j + 1}`
    return `${GREEK_SYM.corr} ${left} / ${right}`
  }

  const perUnderlying = name.match(/^(delta|gamma|vega)_(\d+)$/)
  if (perUnderlying) {
    const type = perUnderlying[1]
    const idx = Number(perUnderlying[2]) - 1
    const ul = store.underlyings[idx]
    return ul ? `${GREEK_SYM[type]} ${demo.underlyingLabel(ul.name, idx)}` : `${GREEK_SYM[type]} S${idx + 1}`
  }

  const type = gType(name)
  return GREEK_SYM[type] ? `${GREEK_SYM[type]} ${GREEK_NAME[type]}` : name
}

const GREEK_DESC = {
  delta: "Δ — sensibilité du prix à une hausse de 1% du spot de ce sous-jacent. Couverture = vendre/acheter Δ×nominal du sous-jacent pour neutraliser ce risque au premier ordre.",
  gamma: "Γ — sensibilité du delta lui-même à une variation du spot (convexité). Un gamma élevé signifie que la couverture delta doit être réajustée fréquemment.",
  vega:  "ν — sensibilité du prix à une hausse de 1% de la volatilité implicite de ce sous-jacent.",
  theta: "Θ — décroissance du prix due au seul passage d'un jour, marché inchangé (portage temporel).",
  rho:   "ρ — sensibilité du prix à une hausse de 100bp du taux sans risque.",
  corr:  "ρᵢⱼ — sensibilité du prix à une hausse de 5pts de corrélation entre les sous-jacents concernés (pertinent surtout sur les payoffs worst-of/best-of).",
}
const gDesc = name => {
  const key = name.match(/^([a-z]+)/)?.[1] || name
  return GREEK_DESC[key] || ''
}

const gUnit = name => {
  const type = gType(name)
  if (type === 'delta') return 'pt de prix / +1 % spot'
  if (type === 'gamma') return 'pt de delta / +1 % spot'
  if (type === 'vega')  return 'pt de prix / +1 pt vol'
  if (type === 'theta') return 'pt de prix / jour'
  if (type === 'rho')   return 'pt de prix / +100 bp'
  if (type === 'corr')  return 'pt de prix / +5 pts corr.'
  return ''
}

const gInterp = (name, val) => {
  // Convert the engine's derivatives to the explicit shock printed in the UI.
  // This is display-only: raw values remain untouched in store.result.greeks.
  const type = gType(name)
  const display = gDisplayValue(name, val)
  const formatted = `${display >= 0 ? '+' : ''}${formatNumber(display, type === 'gamma' ? 3 : 2)} pt`
  if (type === 'delta') return `+1 % spot → prix ${formatted}`
  if (type === 'gamma') return `+1 % spot → delta ${formatted}`
  if (type === 'vega')  return `+1 pt vol → prix ${formatted}`
  if (type === 'theta') return `1 jour → prix ${formatted}`
  if (type === 'rho')   return `+100 bp → prix ${formatted}`
  if (type === 'corr')  return `+5 pts corr. → prix ${formatted}`
  return ''
}

const vegaScopeNote = computed(() => {
  const scope = vegaScope.value
  if (!scope) return ''
  if (scope.type === 'total') return 'Périmètre du Vega : bump appliqué à l’ensemble de la volatilité diffusée.'
  const coverage = Object.entries(scope.coverage || {})
    .map(([name, value]) => {
      const idx = store.underlyings.findIndex(underlying => underlying.name === name)
      const label = idx >= 0 ? demo.underlyingLabel(name, idx) : name
      return `${label} ${formatPercent(Number(value) * 100, 0)}`
    })
    .join(' · ')
  return `Périmètre du Vega : jambe indépendante de la variance${coverage ? ` · couverture ${coverage}` : ''}.`
})

const thetaEventNote = computed(() => {
  const event = thetaEvent.value
  if (!event) return ''
  const reasons = {
    observation_transition_required: 'Theta non publié : la fenêtre de calcul franchit une observation contractuelle nécessitant une transition d’état.',
    fenetre_strike_fix: 'Theta non publié : la fenêtre de calcul franchit une date de fixing initial.',
    realvol: 'Theta non publié : le vieillissement nécessiterait d’inventer une observation de volatilité réalisée.',
  }
  return reasons[event.reason] || 'Theta non publié : une transition contractuelle empêche un simple vieillissement du produit.'
})
</script>

<style scoped>
.result-date-card {
  min-width: 0;
  display: flex;
  flex-direction: column;
}
.result-date-label {
  min-height: 2.5rem;
  line-height: 1.25;
}
</style>
