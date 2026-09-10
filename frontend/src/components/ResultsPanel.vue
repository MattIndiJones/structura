<template>
  <!-- ── Tabs sans pricing requis ─────────────────────────────── -->
  <SummaryTab  v-if="tab === 'summary'" />
  <VariantCompareTab v-else-if="tab === 'variants'" />
  <ProfileTab  v-else-if="tab === 'profile'" />
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
    <!-- Bandeau de valorisation en cours de vie. Entierement calcule depuis la
         reponse : il ne peut pas se desynchroniser d un mode qu on aurait
         choisi ailleurs, puisqu il n y a pas de mode. -->
    <div v-if="store.result?.in_life"
         class="rounded-xl border border-amber-800/60 bg-amber-950/20 px-4 py-3 flex flex-col gap-1">
      <div class="text-xs font-bold text-amber-400 uppercase tracking-wider">
        Valorisation au {{ formatDate(store.result.valuation_date) }}
      </div>
      <div class="text-[11px] text-slate-400 flex flex-wrap gap-x-4 gap-y-1">
        <span>{{ store.result.past.observations_done }} constatation(s) rejouée(s) sur cours réels</span>
        <span>{{ formatNumber(store.result.past.years_elapsed, 2) }} an écoulé,
              {{ formatNumber(store.result.past.years_remaining, 2) }} restant</span>
        <span v-if="store.result.past.worst_of != null">
          worst-of <span class="font-mono text-slate-300">{{ formatPercent(store.result.past.worst_of * 100, 1) }}</span>
        </span>
      </div>
      <!-- L'état que le passé a écrit, variable par variable et sous le nom
           que le script leur donne. Une somme n'aurait pas de sens : un solde
           de coupons et un indicateur de barrière ne s'additionnent pas. -->
      <div v-if="etatRepris.length" class="text-[10px] flex flex-wrap gap-x-3 gap-y-0.5">
        <span class="text-slate-500 uppercase tracking-wider">État repris</span>
        <span v-for="v in etatRepris" :key="v.nom" class="font-mono text-amber-500">
          {{ v.nom }} <SensitiveValue>{{ formatNumber(v.valeur, 4) }}</SensitiveValue>
        </span>
      </div>
      <div v-if="performancesPassees.length" class="text-[10px] text-slate-500 flex flex-wrap gap-x-3">
        <span v-for="perf in performancesPassees" :key="perf.nom" class="font-mono">
          {{ perf.nom }} {{ formatPercent(perf.valeur * 100, 1) }}
        </span>
      </div>

      <!-- Ce que la déclinaison fait de l'état repris.
           Abandonner la mémoire accumulée est une restructuration parfaitement
           légitime — c'est même le levier principal quand on monétise le
           coupon. Impossible de distinguer l'intention d'un renommage
           étourdi : on ne refuse donc pas, on l'AFFICHE, à côté du prix qu'elle
           a produit. Un fait tu vaut moins qu'un fait montré. -->
      <div v-if="etatAbandonne.length"
           class="mt-1 rounded border border-red-900/50 bg-red-950/20 px-2.5 py-2
                  text-[10px] flex flex-col gap-1">
        <span class="text-red-400 font-semibold uppercase tracking-wider">
          ⚠ Cette déclinaison n'utilise plus {{ etatAbandonne.length }} variable(s)
          d'état du passé
        </span>
        <span class="text-slate-400 flex flex-wrap gap-x-3 gap-y-0.5">
          <span v-for="v in etatAbandonne" :key="v.nom" class="font-mono">
            {{ v.nom }} <SensitiveValue>{{ formatNumber(v.valeur, 4) }}</SensitiveValue>
          </span>
        </span>
        <span class="text-slate-500">
          Ce que le détenteur avait accumulé sous ces variables ne lui est pas
          versé. Voulu si vous monétisez le coupon ; à vérifier si vous avez
          seulement renommé.
        </span>
      </div>
    </div>

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

          <!-- Maturité — résiduelle en cours de vie, sinon la maturité pleine.
               Afficher les 3,00 ans du contrat à côté d'un fugit compté depuis
               la valorisation mettait deux axes différents côte à côte : le
               produit paraissait mourir au tiers de sa vie alors qu'il va au
               bout. -->
          <div class="bg-slate-800/50 rounded-lg px-3 py-2">
            <div class="text-slate-500 mb-1">
              {{ enCoursDeVie ? 'Maturité résiduelle' : 'Maturité' }}
            </div>
            <div class="font-mono font-bold text-slate-100 text-base">
              <SensitiveValue>{{ formatNumber(maturiteAffichee, 2) }} ans</SensitiveValue>
            </div>
            <div v-if="enCoursDeVie" class="text-[10px] text-slate-600 mt-0.5">
              <SensitiveValue>{{ formatNumber(store.result.past.years_elapsed, 2) }}</SensitiveValue> an écoulé
              sur <SensitiveValue>{{ formatNumber(store.result.past.years_elapsed + store.result.past.years_remaining, 2) }}</SensitiveValue>
            </div>
            <div v-else-if="store.result.t_max_effective && Math.abs(store.result.t_max_effective - inputs.T) > 0.01"
                 class="text-amber-500 text-[10px] mt-0.5">
              ↗ depuis <SensitiveValue>{{ formatNumber(inputs.T, 2) }} ans</SensitiveValue> (CONSTAT)
            </div>
          </div>

          <!-- Constatations sur période : ce que la fenêtre a réellement pesé -->
          <div v-if="fenetresConstatation.length" class="bg-slate-800/50 rounded-lg px-3 py-2">
            <div class="text-slate-500 mb-1">Fenêtres de constatation
              <HelpTip width="w-80" text="Nombre de points de grille réellement retenus par chaque fenêtre, contre le nombre demandé. La grille de simulation est hebdomadaire : une fenêtre déclarée quotidienne s'y ramène (30 jours ouvrés ≈ 6 points), ce qui coûte quelques points de base par rapport à un moyennage quotidien. En dessous d'une semaine il ne reste qu'un point et le moyennage n'a pas eu lieu du tout." />
            </div>
            <div v-for="(w, i) in fenetresConstatation" :key="i"
                 class="text-[11px] font-mono flex items-baseline gap-1.5"
                 :class="w.degeneree ? 'text-amber-400' : 'text-slate-300'">
              <span class="text-slate-500">{{ w.constatation === 'STRIKE_FIX' ? 'départ' : 'obs' }}</span>
              <span class="font-bold">{{ w.reduction }}</span>
              <span>{{ w.points_retenus }}/{{ w.points_demandes }} pts</span>
              <span v-if="w.degeneree" class="text-[10px]">— pas de moyennage</span>
            </div>
          </div>

          <!-- Fugit — seulement si le script a un STOP -->
          <div v-if="inputs.hasStop && store.result.fugit != null" class="bg-slate-800/50 rounded-lg px-3 py-2">
            <div class="text-slate-500 mb-1">Fugit <span class="text-slate-600 font-normal">(durée moy.)</span>
              <HelpTip text="Durée de vie moyenne pondérée par probabilité E[τ] — la date à laquelle le produit s'arrête en moyenne (rappel anticipé ou échéance). Sert de point d'interpolation sur la courbe de taux pour ce produit à STOP, puisqu'il n'a pas une maturité unique fixe. En cours de vie, il se compte depuis la date de valorisation : le comparer à la maturité résiduelle dit s'il reste de l'espoir de rappel." />
            </div>
            <div class="font-mono font-bold text-amber-300 text-base">
              <SensitiveValue>{{ formatNumber(store.result.fugit, 2) }} ans</SensitiveValue>
            </div>
            <div v-if="enCoursDeVie" class="text-[10px] text-slate-600 mt-0.5">
              depuis la valorisation · vie totale attendue
              <SensitiveValue>{{ formatNumber(vieTotaleAttendue, 2) }} ans</SensitiveValue>
            </div>
            <div v-else class="text-[10px] text-slate-600 mt-0.5">E[τ] sur {{ formatInt(store.result.n_eff) }} chemins</div>
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
        <div class="text-[10px] font-bold text-slate-600 uppercase tracking-widest">
          Niveaux initiaux constatés (S₀)
          <HelpTip text="Clôture NON AJUSTÉE de chaque sous-jacent à la date de strike — le fixing officiel, celui que cite un term sheet. Quand une valorisation en cours de vie a eu lieu, ce sont les niveaux que le moteur a réellement retenus pour mesurer les performances, donc ceux qui ont produit le prix ci-dessus." />
        </div>
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
              <span v-if="spotState[u.ticker]?.value" class="ml-auto text-[10px] text-slate-600">
                {{ spotState[u.ticker].source === 'moteur' ? 'retenu par le moteur' : 'clôture non ajustée' }}
              </span>
            </template>
            <span v-else class="text-slate-600">100% (référence normalisée, aucun ticker)</span>
          </div>
        </div>
      </div>
    </div>
  </div>

  <!-- ── Flux ──────────────────────────────────────────────────── -->
  <div v-else-if="tab === 'flux'" class="flex flex-col gap-4">
    <!-- En cours de vie, le Monte Carlo ne simule que la vie restante : l'axe
         des temps de sa table de flux part de la DATE DE VALORISATION, pas du
         strike. L'ancrer sur le strike datait les échéances futures deux ans
         dans le passé. -->
    <FluxDecomposition :result="store.result"
                       :origin-date="store.result?.in_life
                         ? store.result.valuation_date : inputs?.strike_date"
                       :value-date="inputs?.value_date" />
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
import SummaryTab from './SummaryTab.vue'
import VariantCompareTab from './VariantCompareTab.vue'
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
import FluxDecomposition from './FluxDecomposition.vue'
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

const enCoursDeVie = computed(() => !!store.result?.in_life)

// Ce qu'une fenêtre de constatation a réellement pesé. Publié pour TOUTES les
// fenêtres, pas seulement les trop courtes : un décompte se lit, là où une
// alerte générique se clique sans lire.
const fenetresConstatation = computed(() => store.result?.constatation_windows || [])

/** Maturité à afficher : résiduelle en cours de vie, pleine sinon. */
const maturiteAffichee = computed(() => {
  const r = store.result
  if (!r) return null
  if (r.in_life) return r.past?.years_remaining ?? null
  return r.t_max_effective ?? inputs.value?.T ?? null
})

/** Vie totale attendue depuis la constatation initiale : ce qui s'est déjà
 *  écoulé plus l'espérance de durée restante. C'est ce chiffre-là qu'on cite,
 *  pas le fugit résiduel seul. */
const vieTotaleAttendue = computed(() => {
  const r = store.result
  if (!r?.in_life || r.fugit == null) return null
  return (r.past?.years_elapsed ?? 0) + r.fugit
})

const maturityDateStr = computed(() => {
  // Celle que le moteur a reçue, quand on l'a. Le repli redérive depuis le
  // STRIKE — origine de l'axe — et non depuis la value date.
  if (inputs.value?.maturity_date) return inputs.value.maturity_date
  const origine = inputs.value?.strike_date || inputs.value?.value_date
  if (!origine) return null
  const T = store.result?.t_max_effective || inputs.value.T
  return addDaysStr(origine, T * 365.25)
})

const observationRows = computed(() => {
  const res = store.result
  if (!res?.flux_table || !inputs.value) return []
  // L'axe des temps du moteur part du STRIKE — et, en cours de vie, de la
  // date de valorisation, puisque seule la vie restante est simulée. L'ancrer
  // sur la value date décalait toutes les échéances ; l'ancrer sur le strike
  // en cours de vie les ramenait deux ans en arrière, toutes marquées passées.
  const enCours = !!res.in_life
  const origine = enCours ? res.valuation_date
                          : (inputs.value.strike_date || inputs.value.value_date)
  if (!origine) return []
  const times = [...new Set(Object.values(res.flux_table).map(e => e.t))].sort((a, b) => a - b)
  const now = todayStr()
  const maturityT = res.t_max_effective ?? inputs.value.T
  // En cours de vie, la numérotation reprend là où le passé s'est arrêté :
  // repartir de 1 ferait croire que le produit vient d'être émis.
  const deja = enCours ? (res.past?.observations_done ?? 0) : 0
  return times.map((t, idx) => {
    const date = addDaysStr(origine, t * 365.25)
    const estMaturite = enCours ? idx === times.length - 1
                                : Math.abs(t - maturityT) < 0.01
    return {
      label: estMaturite ? 'Maturité' : `Obs. ${deja + idx + 1}`,
      date, t, isFuture: date > now,
    }
  })
})

// ── Niveaux initiaux constatés ────────────────────────────────────
// Deux sources, dans cet ordre : ceux que le MOTEUR a effectivement retenus
// quand il a rejoué le passé (ils font foi, puisque c'est eux qui ont produit
// le prix affiché juste au-dessus), sinon la clôture nue à la date de strike.
// Plus de magasin à semer à la main, donc plus d'écran vide après un pricing.
const spotState = reactive({})

async function loadSpots() {
  const inp = inputs.value
  if (!inp?.underlyings?.length) return
  const jour = inp.strike_date || todayStr()
  const tickers = inp.underlyings.map(u => u.ticker).filter(Boolean)
  for (const t of tickers) {
    if (!spotState[t]) spotState[t] = { loading: false, value: null }
    spotState[t].loading = true
  }
  const utilises = store.result?.past?.strike_levels || null
  const closes = await store.loadStrikeCloses(tickers, jour)
  for (const u of inp.underlyings) {
    if (!u.ticker) continue
    const duMoteur = utilises?.[u.name]
    spotState[u.ticker] = duMoteur != null
      ? { loading: false, value: { close: duMoteur, date: jour }, source: 'moteur' }
      : { loading: false, value: closes[u.ticker] || null, source: 'cloture' }
  }
}

watch(inputs, loadSpots, { immediate: true })

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

// ── Greeks ────────────────────────────────────────────────────────
// Solde de coupons accumules par un produit a memoire : la somme des
// variables de memoire non versees. Nul sur un produit qui n en a pas.
// Variables que le rejeu du passé a écrites — solde de coupons en mémoire,
// indicateur de barrière franchie, compteur… L'API a déjà retiré les PARAM du
// script ; on les affiche telles quelles, sans les sommer ni les convertir en
// pourcentage : selon la variable, 1 vaut « 100 % du nominal » ou « vrai ».
const etatRepris = computed(() =>
  Object.entries(store.result?.past?.memory || {})
    .map(([nom, valeur]) => ({ nom, valeur: Number(valeur) || 0 }))
    .sort((a, b) => a.nom.localeCompare(b.nom))
)

/**
 * Les variables d'état que la déclinaison affichée ne lit plus.
 *
 * Le serveur les rapporte dans `variant_state_check` — il ne refuse pas, parce
 * qu'abandonner la mémoire est une restructuration légitime et qu'il ne peut
 * pas distinguer l'intention d'un renommage. Ce rapport partait dans chaque
 * réponse et n'était affiché nulle part : le mécanisme existait, testé, juste,
 * et invisible. Un refus non affiché vaut un refus absent.
 *
 * On ne montre que celles qui sont ABANDONNÉES et qui portaient quelque chose :
 * signaler « CPN 0,0000 non lu » est du bruit qui ferait ignorer la ligne le
 * jour où elle dit « DUE 0,0667 non lu ».
 */
const etatAbandonne = computed(() =>
  Object.entries(store.result?.variant_state_check || {})
    .filter(([, v]) => !v.lu_par_la_variante && Math.abs(Number(v.valeur) || 0) > 1e-9)
    .map(([nom, v]) => ({ nom, valeur: Number(v.valeur) || 0 }))
    .sort((a, b) => a.nom.localeCompare(b.nom))
)

const performancesPassees = computed(() =>
  Object.entries(store.result?.past?.performances || {})
    .map(([nom, valeur]) => ({ nom, valeur }))
    .sort((a, b) => a.valeur - b.valeur))

const fmtG = formatGreek

const GREEK_SYM = { delta: 'Δ', gamma: 'Γ', vega: 'ν', theta: 'Θ', rho: 'ρ', corr: 'ρᵢⱼ', credit: 'CR' }
const GREEK_NAME = { delta: 'Delta', gamma: 'Gamma', vega: 'Vega', theta: 'Theta', rho: 'Rho', corr: 'Corrélation', credit: 'Crédit' }

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
  credit: "CR — sensibilité du prix à un écartement de 100bp du spread émetteur. Signe structurellement opposé au rho : un spread n'actualise que les flux, il ne remonte aucun forward. Le desk lit plutôt le DV01, un centième de ce chiffre.",
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
  if (type === 'credit') return 'pt de prix / +100 bp spread'
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
  if (type === 'credit') {
    // Le DV01 est ce que le desk cote : l'impact d'UN point de base.
    const dv01 = formatNumber(display / 100, 4)
    return `+100 bp de spread → prix ${formatted} · DV01 ${dv01} pt/bp`
  }
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
