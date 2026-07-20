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
      <span class="font-bold text-slate-100 tracking-tight">Booking — produits bookés</span>
      <div class="ml-auto flex items-center gap-3">
        <span v-if="refreshBookStatus" class="text-xs text-slate-500">{{ refreshBookStatus }}</span>
        <button class="btn-secondary text-xs px-3 py-1.5" :disabled="refreshingBook" @click="refreshBook">
          {{ refreshingBook ? '⏳ Rafraîchissement…' : '🔄 Rafraîchir le book' }}
        </button>
        <span v-if="dealsStore.deals.length" class="text-xs text-slate-500">
          {{ filteredDeals.length }} / {{ dealsStore.deals.length }} deal(s)
        </span>
      </div>
    </header>

    <main class="flex-1 overflow-y-auto p-6">
      <div class="max-w-5xl mx-auto flex flex-col gap-3">

        <div v-if="dealsStore.loading && !dealsStore.deals.length" class="text-sm text-slate-500">Chargement…</div>

        <div v-else-if="!dealsStore.deals.length" class="card text-sm text-slate-500">
          Aucun deal booké pour l'instant. Un deal se book depuis l'onglet Deal du Pricer, une fois un pricing lancé.
        </div>

        <template v-else>

          <!-- ── Alertes non lues (cycle de vie & barrières) ───── -->
          <div v-if="alerts.length" class="card border-amber-800/60">
            <div class="flex items-center mb-3">
              <h2 class="text-xs font-bold text-amber-400 uppercase tracking-wider flex items-center gap-2">
                <span class="inline-block w-2 h-2 rounded-full bg-red-500 pulse-ring"></span>
                🔔 Alertes non lues ({{ alerts.length }})
                <HelpTip width="w-72" text="Alertes levées par le refresh quotidien (23h) ou par le bouton Rafraîchir le book : rappel/échéance/KI détecté sur un deal, ou franchissement d'une barrière surveillée (M_). Chaque fait n'alerte qu'une seule fois." />
              </h2>
              <button class="ml-auto btn-secondary text-[10px] px-2 py-1" @click="markAllRead">✓ Tout marquer lu</button>
            </div>
            <div class="flex flex-col gap-1.5">
              <div v-for="a in alerts" :key="a.id" class="flex items-start gap-2 text-xs">
                <span :class="alertChipClass(a.kind)" class="px-1.5 py-0.5 rounded text-[10px] font-semibold shrink-0 whitespace-nowrap">
                  {{ alertKindLabel(a.kind) }}
                </span>
                <span class="text-slate-300 flex-1">{{ a.message }}</span>
                <span class="text-slate-600 text-[10px] shrink-0">{{ a.created_at.slice(0, 10) }}</span>
                <button class="text-slate-500 hover:text-emerald-400 shrink-0" title="Marquer lu" @click="markRead(a)">✓</button>
              </div>
            </div>
          </div>

          <!-- ── Filtres ──────────────────────────────────────── -->
          <div class="card flex flex-wrap items-end gap-3">
            <div class="flex-1 min-w-[160px]">
              <label class="label">Contrepartie</label>
              <input v-model="filters.contrepartie" type="text" class="input text-xs"
                placeholder="Rechercher un client…" />
            </div>
            <div class="min-w-[140px]">
              <label class="label">Sous-jacent</label>
              <select v-model="filters.ticker" class="select text-xs">
                <option value="">Tous</option>
                <option v-for="t in tickerOptions" :key="t" :value="t">{{ t }}</option>
              </select>
            </div>
            <div class="min-w-[140px]">
              <label class="label">Type de produit</label>
              <select v-model="filters.productType" class="select text-xs">
                <option value="">Tous</option>
                <option v-for="p in productTypeOptions" :key="p" :value="p">{{ p }}</option>
              </select>
            </div>
            <div class="min-w-[120px]">
              <label class="label">Statut</label>
              <select v-model="filters.status" class="select text-xs">
                <option value="">Tous</option>
                <option v-for="s in statusOptions" :key="s" :value="s">{{ s }}</option>
              </select>
            </div>
            <button v-if="hasActiveFilters" class="btn-secondary text-xs px-3 py-1.5" @click="resetFilters">
              ✕ Réinitialiser
            </button>
          </div>

          <!-- ── Stats agrégées (sur la sélection filtrée) ───────── -->
          <div class="card kpi-tile">
            <div class="flex flex-wrap gap-x-6 gap-y-3 relative">
              <div>
                <div class="text-slate-500 text-[10px] uppercase tracking-wider mb-0.5">Deals</div>
                <div class="font-mono text-lg font-bold text-slate-100">{{ stats.total }}</div>
              </div>
              <div>
                <div class="text-slate-500 text-[10px] uppercase tracking-wider mb-0.5">Nominal total</div>
                <div class="font-mono text-lg font-bold text-slate-100">{{ formatNominal(stats.nominalTotal) }}</div>
              </div>
              <div>
                <div class="text-slate-500 text-[10px] uppercase tracking-wider mb-0.5">Par statut</div>
                <div class="flex gap-1.5 flex-wrap">
                  <span v-for="s in statusOptions" :key="s"
                    v-show="stats.byStatus[s]"
                    :class="statusClass(s)" class="px-1.5 py-0.5 rounded text-[10px] font-semibold">
                    {{ s }} {{ stats.byStatus[s] }} ({{ pct(stats.byStatus[s], stats.total) }})
                  </span>
                </div>
              </div>
              <div v-if="stats.resolved">
                <div class="text-slate-500 text-[10px] uppercase tracking-wider mb-0.5">
                  Hit ratio — {{ stats.resolved }} deal(s) résolu(s)
                  <HelpTip text="Répartition des deals arrivés au bout de leur vie (callé, ou échu à maturité en KI ou en remboursement normal). Les deals encore actifs ne comptent pas dans ce ratio." />
                </div>
                <div class="flex gap-1.5 flex-wrap">
                  <span v-if="stats.byOutcome.callé" class="px-1.5 py-0.5 rounded text-[10px] font-semibold bg-amber-900/40 text-amber-400">
                    callé {{ stats.byOutcome.callé }} ({{ pct(stats.byOutcome.callé, stats.resolved) }})
                  </span>
                  <span v-if="stats.byOutcome.final" class="px-1.5 py-0.5 rounded text-[10px] font-semibold bg-emerald-900/40 text-emerald-400">
                    final {{ stats.byOutcome.final }} ({{ pct(stats.byOutcome.final, stats.resolved) }})
                  </span>
                  <span v-if="stats.byOutcome.ki" class="px-1.5 py-0.5 rounded text-[10px] font-semibold bg-red-900/40 text-red-400">
                    ki {{ stats.byOutcome.ki }} ({{ pct(stats.byOutcome.ki, stats.resolved) }})
                  </span>
                </div>
              </div>
              <div v-if="stats.avgRealizedPayout != null">
                <div class="text-slate-500 text-[10px] uppercase tracking-wider mb-0.5">Remboursement moyen réalisé</div>
                <div class="font-mono text-lg font-bold text-slate-100">{{ (stats.avgRealizedPayout * 100).toFixed(1) }}%</div>
              </div>
            </div>
          </div>

          <!-- ── Watchlist barrières (deals actifs) ───────────── -->
          <div v-if="watchlist.length || watchlistError" class="card">
            <h2 class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3">
              Watchlist — proximité barrières
              <HelpTip width="w-72" text="Deals actifs triés par urgence : écart du worst-of actuel à chaque barrière détectée dans le script (en points de S₀), et prochaine date d'observation. Détection des barrières par convention de nommage des PARAM (AC_BAR, KI_BAR…) — un script aux noms inhabituels peut passer à travers. Utilise les valeurs par défaut du script, pas les surcharges UI du pricing." />
            </h2>

            <div v-if="watchlistError" class="text-xs text-amber-400">⚠ {{ watchlistError }}</div>

            <div v-else class="overflow-x-auto">
              <table class="w-full text-xs border-collapse">
                <thead>
                  <tr class="border-b border-slate-700">
                    <th class="text-left text-slate-500 font-medium pb-2 pr-3 whitespace-nowrap">Réf</th>
                    <th class="text-left text-slate-500 font-medium pb-2 pr-3">Client</th>
                    <th class="text-left text-slate-500 font-medium pb-2 pr-3 whitespace-nowrap">Prochaine obs</th>
                    <th class="text-left text-slate-500 font-medium pb-2 pr-3 whitespace-nowrap">WOF
                      <HelpTip text="Performance actuelle du pire sous-jacent vs son S₀ (spot le plus récent). Entre parenthèses : le minimum touché depuis le strike — c'est lui qu'une barrière KI en continu compare." />
                    </th>
                    <th class="text-left text-slate-500 font-medium pb-2">Barrières</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="w in watchlist" :key="w.deal_id"
                    class="border-b border-slate-800/50 hover:bg-slate-800/20 transition-colors">
                    <td class="py-2 pr-3">
                      <RouterLink :to="`/pricer?dealId=${w.deal_id}`"
                        class="font-mono font-semibold text-blue-400 hover:underline whitespace-nowrap">
                        {{ w.reference }}
                      </RouterLink>
                    </td>
                    <td class="py-2 pr-3 text-slate-300">{{ w.contrepartie }}</td>
                    <td class="py-2 pr-3 font-mono whitespace-nowrap">
                      <template v-if="w.next_event">
                        <span class="text-slate-300">{{ w.next_event.date }}</span>
                        <span class="ml-1.5 text-[10px]"
                          :class="w.days_to_next <= 30 ? 'text-amber-400 font-semibold' : 'text-slate-500'">
                          J−{{ w.days_to_next }}
                        </span>
                      </template>
                      <span v-else class="text-slate-600">—</span>
                    </td>
                    <td class="py-2 pr-3 font-mono whitespace-nowrap">
                      <template v-if="w.wof != null">
                        <span :class="w.wof >= 1 ? 'text-emerald-400' : 'text-red-400'">
                          {{ (w.wof * 100).toFixed(1) }}%
                        </span>
                        <span v-if="w.wof_min != null" class="text-slate-600 text-[10px] ml-1">
                          (min {{ (w.wof_min * 100).toFixed(1) }}%)
                        </span>
                      </template>
                      <span v-else class="text-slate-600" title="S₀ manquant — lancez un Refresh sur ce deal">n/d</span>
                    </td>
                    <td class="py-2">
                      <div class="flex gap-1.5 flex-wrap">
                        <span v-for="b in w.barriers" :key="b.name"
                          :class="barrierChipClass(b)"
                          class="px-1.5 py-0.5 rounded text-[10px] font-mono font-semibold whitespace-nowrap">
                          {{ b.name }} {{ (b.level * 100).toFixed(0) }}%<template v-if="b.observable && b.observable !== 'WOF'"> vs {{ b.observable }}</template> · {{ barrierGapLabel(b) }}
                        </span>
                        <span v-if="!w.barriers.length" class="text-slate-600 text-[10px]">aucune détectée</span>
                      </div>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <!-- ── Liste des deals ──────────────────────────────── -->
          <div v-if="!filteredDeals.length" class="card text-sm text-slate-500">
            Aucun deal ne correspond à ces filtres.
          </div>

          <div v-for="d in filteredDeals" :key="d.id"
            class="card flex flex-col gap-3 hover:shadow-xl hover:shadow-black/30
                   hover:border-slate-700 transition-all duration-200">
            <!-- Ligne d'en-tête — cliquable pour déplier la fiche détail -->
            <div class="flex items-start justify-between gap-3 flex-wrap cursor-pointer select-none"
              @click="toggleDetail(d.id)">
              <div class="flex items-center gap-2 flex-wrap">
                <span class="text-slate-500 text-xs">{{ expanded[d.id] ? '▾' : '▸' }}</span>
                <span class="font-mono font-semibold text-slate-200">{{ d.reference }}</span>
                <span class="text-slate-600">·</span>
                <span class="text-slate-300">{{ d.contrepartie }}</span>
                <span v-if="d.product_type" class="text-slate-500 text-[10px] border border-slate-700 rounded px-1.5 py-0.5">
                  {{ d.product_type }}
                </span>
                <span :class="statusClass(d.status)" class="px-1.5 py-0.5 rounded text-[10px] font-semibold uppercase">
                  {{ d.status }}
                </span>
              </div>
              <div class="flex items-center gap-2 shrink-0">
                <select v-if="d.status === 'actif'" class="select text-xs py-1"
                  :value="mtmMode[d.id] || 'booking'" @click.stop
                  @change="mtmMode[d.id] = $event.target.value"
                  title="Paramètres de marché du MtM : σ/corrélations figées au booking, ou recalibrées sur la vol réalisée 1 an (modèle GBM)">
                  <option value="booking">Params booking</option>
                  <option value="realized">Marché actuel</option>
                </select>
                <button v-if="d.status === 'actif'" class="btn-secondary text-xs px-3 py-1.5"
                  :disabled="mtmLoading[d.id]" @click.stop="runMtm(d.id)"
                  title="MtM résiduel : valorise les cash-flows restants du produit vivant (calendrier résiduel, spots en % du strike, état KI/mémoire hérité)">
                  <span v-if="mtmLoading[d.id]"
                    class="w-3 h-3 border-2 border-slate-400 border-t-transparent rounded-full animate-spin inline-block mr-1"></span>
                  💰 MtM
                </button>
                <button class="btn-secondary text-xs px-3 py-1.5" :disabled="refreshingId === d.id"
                  @click.stop="refresh(d.id)">
                  <span v-if="refreshingId === d.id"
                    class="w-3 h-3 border-2 border-slate-400 border-t-transparent rounded-full animate-spin inline-block mr-1"></span>
                  ↻ Refresh
                </button>
                <RouterLink :to="`/pricer?dealId=${d.id}`" class="btn-secondary text-xs px-3 py-1.5" @click.stop>
                  → Ouvrir
                </RouterLink>
              </div>
            </div>

            <div class="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
              <div>
                <div class="text-slate-500 mb-0.5">Nominal</div>
                <div class="font-mono text-slate-200">{{ formatNominal(d.nominal) }} {{ d.devise }}</div>
              </div>
              <div>
                <div class="text-slate-500 mb-0.5">Prix / FV / Marge</div>
                <div class="font-mono">
                  <span class="text-slate-200">{{ d.price_traded.toFixed(2) }}%</span>
                  <span class="text-slate-600 mx-1">/</span>
                  <span class="text-slate-400">{{ d.fair_value.toFixed(2) }}%</span>
                  <span class="mx-1" :class="d.margin >= 0 ? 'text-emerald-400' : 'text-red-400'">
                    {{ d.margin >= 0 ? '+' : '' }}{{ d.margin.toFixed(2) }}%
                  </span>
                </div>
              </div>
              <div>
                <div class="text-slate-500 mb-0.5">Strike / Value</div>
                <div class="font-mono text-slate-300">{{ d.strike_date }} → {{ d.value_date }}</div>
              </div>
              <div>
                <div class="text-slate-500 mb-0.5">Maturité</div>
                <div class="font-mono text-slate-300">{{ d.maturity_date }}</div>
              </div>
            </div>

            <div v-if="d.realized_payout != null" class="text-xs text-slate-400">
              Remboursement réalisé : <span class="font-mono text-slate-200">{{ (d.realized_payout * 100).toFixed(2) }}%</span>
              <span v-if="d.resolution_outcome" class="text-slate-600"> ({{ d.resolution_outcome }})</span>
            </div>

            <div v-if="refreshResults[d.id]" class="text-xs pt-2 border-t border-slate-800"
              :class="refreshResults[d.id].startsWith('⚠') ? 'text-amber-400' : 'text-slate-400'">
              {{ refreshResults[d.id] }}
            </div>

            <!-- ── MtM résiduel ────────────────────────────────── -->
            <div v-if="mtmResults[d.id]" class="text-xs pt-2 border-t border-slate-800">
              <div v-if="mtmResults[d.id].error" class="text-amber-400">⚠ {{ mtmResults[d.id].error }}</div>
              <div v-else-if="mtmResults[d.id].resolved_pending" class="text-amber-400">
                ⚠ {{ mtmResults[d.id].message }}
              </div>
              <div v-else class="flex flex-wrap items-center gap-x-4 gap-y-1">
                <span>
                  MtM résiduel :
                  <span class="font-mono font-bold text-sm text-brand-gradient">{{ (mtmResults[d.id].mtm * 100).toFixed(2) }}%</span>
                  <span class="text-slate-600 font-mono text-[10px]">
                    [{{ (mtmResults[d.id].ic95[0] * 100).toFixed(2) }} – {{ (mtmResults[d.id].ic95[1] * 100).toFixed(2) }}]
                  </span>
                </span>
                <span class="text-slate-500">
                  vs traité <span class="font-mono" :class="(mtmResults[d.id].mtm * 100 - d.price_traded) >= 0 ? 'text-emerald-400' : 'text-red-400'">
                    {{ (mtmResults[d.id].mtm * 100 - d.price_traded) >= 0 ? '+' : '' }}{{ (mtmResults[d.id].mtm * 100 - d.price_traded).toFixed(2) }} pts
                  </span>
                </span>
                <span class="text-slate-500">
                  vie restante <span class="font-mono text-slate-300">{{ mtmResults[d.id].T_remaining.toFixed(2) }} an(s)</span>
                </span>
                <span class="text-slate-500">
                  obs passées <span class="font-mono text-slate-300">{{ mtmResults[d.id].obs_passees }}</span>
                </span>
                <span class="text-slate-500">
                  WOF min réalisé <span class="font-mono text-slate-300">{{ (mtmResults[d.id].wof_min_realized * 100).toFixed(1) }}%</span>
                </span>
                <span v-if="mtmResults[d.id].realized_total" class="text-slate-500">
                  flux déjà payés <span class="font-mono text-slate-300">{{ (mtmResults[d.id].realized_total * 100).toFixed(2) }}%</span>
                </span>
                <span v-if="mtmResults[d.id].best_case && mtmResults[d.id].best_case.capped" class="text-slate-500"
                  title="Meilleur dénouement possible du produit, en valeur actualisée (maximum de la distribution Monte Carlo)">
                  meilleur scénario <span class="font-mono text-slate-300">{{ (mtmResults[d.id].best_case.pv_max * 100).toFixed(2) }}%</span>
                </span>
                <span v-if="mtmResults[d.id].best_case && mtmResults[d.id].best_case.exit_signal"
                  class="text-amber-400 border border-amber-700 rounded px-1.5 py-0.5 text-[10px]"
                  :title="`Le MtM capture ${(mtmResults[d.id].best_case.capture_ratio * 100).toFixed(1)}% du meilleur dénouement — potentiel résiduel ${mtmResults[d.id].best_case.upside_pts} pt (≈ ${mtmResults[d.id].best_case.upside_annualized_pct}%/an)`">
                  ⚡ sortie envisageable
                </span>
                <button class="btn-secondary text-[10px] px-2 py-1" :disabled="noteLoading[d.id]"
                  @click.stop="downloadNote(d)"
                  title="Génère la note de valorisation PDF à envoyer au client — même chiffre que le MtM affiché (mode et seed identiques)">
                  <span v-if="noteLoading[d.id]"
                    class="w-3 h-3 border-2 border-slate-400 border-t-transparent rounded-full animate-spin inline-block mr-1"></span>
                  📄 Note de valo
                </button>
                <button class="btn-secondary text-[10px] px-2 py-1" :disabled="rollLoading[d.id]"
                  @click.stop="runRoll(d)"
                  title="Reprice le même produit, même sous-jacent, départ forward (value date = aujourd'hui, tenor plein) — juste une simulation, rien n'est booké">
                  <span v-if="rollLoading[d.id]"
                    class="w-3 h-3 border-2 border-slate-400 border-t-transparent rounded-full animate-spin inline-block mr-1"></span>
                  🔄 Relancer un prix
                </button>
                <span v-if="mtmResults[d.id].market_used" class="w-full font-mono text-[10px] pt-0.5"
                  :class="mtmResults[d.id].market_used.source === 'booking' ? 'text-slate-600' : 'text-sky-400'">
                  Marché utilisé : {{ marketUsedLabel(mtmResults[d.id].market_used) }}
                </span>
              </div>
            </div>

            <!-- ── Reconduction (Flow A) ──────────────────────── -->
            <div v-if="rollResults[d.id]" class="text-xs pt-2 border-t border-slate-800">
              <div v-if="rollResults[d.id].error" class="text-amber-400">⚠ {{ rollResults[d.id].error }}</div>
              <div v-else class="flex flex-wrap items-center gap-x-4 gap-y-1">
                <span class="text-slate-500">🔄 Produit reconduit :</span>
                <span>
                  Prix départ forward :
                  <span class="font-mono font-bold text-sm text-brand-gradient">{{ (rollResults[d.id].price_new * 100).toFixed(2) }}%</span>
                </span>
                <span class="text-slate-500">
                  vs traité initial <span class="font-mono" :class="(rollResults[d.id].price_new * 100 - d.price_traded) >= 0 ? 'text-emerald-400' : 'text-red-400'">
                    {{ (rollResults[d.id].price_new * 100 - d.price_traded) >= 0 ? '+' : '' }}{{ (rollResults[d.id].price_new * 100 - d.price_traded).toFixed(2) }} pts
                  </span>
                </span>
                <span class="text-slate-500">
                  nouvelle value date <span class="font-mono text-slate-300">{{ rollResults[d.id].value_date }}</span>
                </span>
                <span class="text-slate-500">
                  nouvelle échéance <span class="font-mono text-slate-300">{{ rollResults[d.id].maturity_date }}</span>
                </span>
                <span v-if="!rollResults[d.id].vol_refreshed" class="text-amber-400 text-[10px]" title="Yahoo Finance indisponible — vol du booking d'origine réutilisée">
                  ⚠ vol non rafraîchie
                </span>
              </div>
            </div>

            <!-- ── Fiche détail dépliable ─────────────────────── -->
            <div v-if="expanded[d.id]" class="pt-3 border-t border-slate-800 flex flex-col gap-4">
              <div v-if="!details[d.id]" class="text-xs text-slate-600">Chargement du détail…</div>
              <template v-else>

                <!-- Barre de vie du produit -->
                <div>
                  <div class="flex items-center justify-between text-[10px] text-slate-500 mb-1">
                    <span>{{ d.value_date }}</span>
                    <span v-if="lifePct(d) !== null" class="text-slate-400">
                      {{ lifePct(d) }}% écoulé
                    </span>
                    <span>{{ d.maturity_date }}</span>
                  </div>
                  <div class="relative h-2.5 bg-slate-800 rounded-full">
                    <div class="absolute inset-y-0 left-0 rounded-full"
                      :class="d.status === 'callé' ? 'bg-amber-700/60' : d.status === 'échu' ? 'bg-slate-600' : 'bg-blue-800/70'"
                      :style="{ width: (lifePct(d) ?? 0) + '%' }"></div>
                    <!-- Aujourd'hui -->
                    <div v-if="d.status === 'actif' && lifePct(d) !== null"
                      class="absolute -top-1 -bottom-1 w-0.5 bg-amber-400"
                      :style="{ left: lifePct(d) + '%' }" title="Aujourd'hui"></div>
                    <!-- Constatations -->
                    <div v-for="ev in obsEvents(d.id)" :key="ev.id"
                      class="absolute top-1/2 -translate-y-1/2 -translate-x-1/2 w-2.5 h-2.5 rounded-full border"
                      :class="eventDotClass(ev)"
                      :style="{ left: eventPct(d, ev) + '%' }"
                      :title="`${ev.label} — ${ev.event_date} (${ev.status})`"></div>
                  </div>
                  <div class="flex gap-3 mt-1.5 text-[10px] text-slate-600 flex-wrap">
                    <span><span class="inline-block w-2 h-2 rounded-full bg-blue-500 border border-blue-400 mr-1"></span>observé</span>
                    <span><span class="inline-block w-2 h-2 rounded-full bg-amber-500 border border-amber-400 mr-1"></span>callé</span>
                    <span><span class="inline-block w-2 h-2 rounded-full bg-emerald-500 border border-emerald-400 mr-1"></span>final</span>
                    <span><span class="inline-block w-2 h-2 rounded-full bg-red-500 border border-red-400 mr-1"></span>KI</span>
                    <span><span class="inline-block w-2 h-2 rounded-full bg-slate-900 border border-slate-600 mr-1"></span>futur</span>
                    <span><span class="inline-block w-2 h-2 rounded-full bg-slate-700 border border-slate-600 mr-1 opacity-50"></span>annulé</span>
                  </div>
                </div>

                <!-- Dates complètes -->
                <div class="grid grid-cols-2 sm:grid-cols-5 gap-3 text-xs">
                  <div><div class="text-slate-500 mb-0.5">Trade</div><div class="font-mono text-slate-300">{{ d.trade_date }}</div></div>
                  <div><div class="text-slate-500 mb-0.5">Strike</div><div class="font-mono text-slate-300">{{ d.strike_date }}</div></div>
                  <div><div class="text-slate-500 mb-0.5">Value</div><div class="font-mono text-slate-300">{{ d.value_date }}</div></div>
                  <div><div class="text-slate-500 mb-0.5">Maturité</div><div class="font-mono text-slate-300">{{ d.maturity_date }}</div></div>
                  <div><div class="text-slate-500 mb-0.5">Payment</div><div class="font-mono text-slate-300">{{ d.payment_date || '–' }}</div></div>
                </div>

                <!-- Termes économiques (PARAM figés au booking) -->
                <div v-if="details[d.id].terms?.length">
                  <div class="text-[10px] font-semibold text-slate-500 uppercase tracking-wider mb-1.5">
                    Termes économiques
                    <HelpTip text="Les PARAM du script figé au booking, avec les valeurs réellement bookées (surcharges UI si figées, défauts du script sinon). Un PARAM() par observation affiche toutes ses lignes dans l'ordre des dates AT." />
                  </div>
                  <div class="flex flex-wrap gap-2">
                    <div v-for="t in details[d.id].terms" :key="t.name"
                      class="flex items-center gap-2 bg-slate-800/60 border border-slate-700 rounded-lg px-3 py-1.5 text-xs"
                      :title="t.desc || t.name">
                      <span class="font-mono text-slate-400">{{ t.name }}</span>
                      <span class="font-mono font-semibold text-slate-200">{{ formatTerm(t) }}</span>
                      <span v-if="t.kind === 'array'" class="text-[10px] text-slate-600">par obs</span>
                    </div>
                  </div>
                </div>

                <!-- Sous-jacents : S₀ figé + spot actuel (watchlist) -->
                <div>
                  <div class="text-[10px] font-semibold text-slate-500 uppercase tracking-wider mb-1.5">Sous-jacents</div>
                  <div class="flex flex-wrap gap-2">
                    <div v-for="u in details[d.id].underlyings" :key="u.name"
                      class="flex items-center gap-2 bg-slate-800/60 border border-slate-700 rounded-lg px-3 py-1.5 text-xs">
                      <span class="font-mono font-semibold text-slate-200">{{ u.ticker || u.name }}</span>
                      <span class="text-slate-500">S₀ <span class="font-mono text-slate-300">{{ formatSpot(s0For(d.id, u.name)) }}</span></span>
                      <template v-if="wlUnderlying(d.id, u.name)">
                        <span class="text-slate-500">spot <span class="font-mono text-slate-300">{{ formatSpot(wlUnderlying(d.id, u.name).spot) }}</span></span>
                        <span class="font-mono font-semibold"
                          :class="wlUnderlying(d.id, u.name).perf >= 1 ? 'text-emerald-400' : 'text-red-400'">
                          {{ ((wlUnderlying(d.id, u.name).perf - 1) * 100).toFixed(1) >= 0 ? '+' : '' }}{{ ((wlUnderlying(d.id, u.name).perf - 1) * 100).toFixed(1) }}%
                        </span>
                      </template>
                    </div>
                  </div>
                </div>

                <!-- Barrières (watchlist, deals actifs seulement) -->
                <div v-if="wlRow(d.id)?.barriers?.length">
                  <div class="text-[10px] font-semibold text-slate-500 uppercase tracking-wider mb-1.5">Barrières</div>
                  <div class="flex gap-1.5 flex-wrap">
                    <span v-for="b in wlRow(d.id).barriers" :key="b.name"
                      :class="barrierChipClass(b)"
                      class="px-1.5 py-0.5 rounded text-[10px] font-mono font-semibold whitespace-nowrap">
                      {{ b.name }} {{ (b.level * 100).toFixed(0) }}%<template v-if="b.observable && b.observable !== 'WOF'"> vs {{ b.observable }}</template> · {{ barrierGapLabel(b) }}
                    </span>
                  </div>
                </div>

                <!-- Constatations (lecture seule) -->
                <div>
                  <div class="text-[10px] font-semibold text-slate-500 uppercase tracking-wider mb-1.5">
                    Constatations ({{ details[d.id].events?.length ?? 0 }})
                  </div>
                  <div class="overflow-x-auto">
                    <table class="w-full text-xs border-collapse">
                      <thead>
                        <tr class="border-b border-slate-700 text-left text-slate-500">
                          <th class="pb-1.5 pr-3 font-medium">#</th>
                          <th class="pb-1.5 pr-3 font-medium whitespace-nowrap">Label</th>
                          <th class="pb-1.5 pr-3 font-medium whitespace-nowrap">Date</th>
                          <th v-for="u in details[d.id].underlyings" :key="u.name"
                            class="pb-1.5 pr-3 font-medium whitespace-nowrap">{{ u.ticker || u.name }}</th>
                          <th class="pb-1.5 font-medium">Statut</th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr v-for="ev in details[d.id].events" :key="ev.id"
                          class="border-b border-slate-800/50"
                          :class="ev.status === 'annulé' ? 'opacity-40' : ev.status === 'futur' ? 'opacity-60' : ''">
                          <td class="py-1.5 pr-3 text-slate-500">{{ ev.event_index + 1 }}</td>
                          <td class="py-1.5 pr-3 text-slate-300 whitespace-nowrap">{{ ev.label }}</td>
                          <td class="py-1.5 pr-3 font-mono text-slate-300 whitespace-nowrap">{{ ev.event_date }}</td>
                          <td v-for="u in details[d.id].underlyings" :key="u.name" class="py-1.5 pr-3 font-mono">
                            <template v-if="ev.spots[u.name]">
                              <span class="text-slate-200">{{ formatSpot(ev.spots[u.name]) }}</span>
                              <span v-if="ev.t_years > 0 && s0For(d.id, u.name)"
                                class="text-[10px] ml-1"
                                :class="ev.spots[u.name] >= s0For(d.id, u.name) ? 'text-emerald-400' : 'text-red-400'">
                                {{ ((ev.spots[u.name] / s0For(d.id, u.name) - 1) * 100) >= 0 ? '+' : '' }}{{ ((ev.spots[u.name] / s0For(d.id, u.name) - 1) * 100).toFixed(1) }}%
                              </span>
                            </template>
                            <span v-else class="text-slate-600">–</span>
                          </td>
                          <td class="py-1.5">
                            <span :class="eventStatusClass(ev.status)"
                              class="px-1.5 py-0.5 rounded text-[10px] font-medium">{{ ev.status }}</span>
                          </td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                </div>

                <!-- Explication de valo (P&L explain entre deux dates) -->
                <div v-if="d.status === 'actif'">
                  <div class="text-[10px] font-semibold text-slate-500 uppercase tracking-wider mb-1.5">
                    Explication de valo
                    <HelpTip text="Décompose la variation de MtM entre deux dates en effets de risque (temps, spot, volatilité, corrélation) par réévaluations successives à seed identique. Date 1 = booking par défaut (σ du booking) ; les flux détachés sur la période sont affichés à part." />
                  </div>
                  <div class="flex items-center gap-2 flex-wrap text-xs">
                    <label class="text-slate-500">du</label>
                    <input type="date" class="bg-slate-800 border border-slate-700 rounded px-2 py-1 text-xs text-slate-200"
                      :value="explainD1[d.id] || d.value_date"
                      @change="explainD1[d.id] = $event.target.value" />
                    <label class="text-slate-500">au</label>
                    <input type="date" class="bg-slate-800 border border-slate-700 rounded px-2 py-1 text-xs text-slate-200"
                      :value="explainD2[d.id] || todayIso"
                      @change="explainD2[d.id] = $event.target.value" />
                    <button class="btn-secondary text-xs px-3 py-1.5" :disabled="explainLoading[d.id]"
                      @click="runExplain(d)">
                      <span v-if="explainLoading[d.id]"
                        class="w-3 h-3 border-2 border-slate-400 border-t-transparent rounded-full animate-spin inline-block mr-1"></span>
                      ⚖ Expliquer
                    </button>
                  </div>
                  <div v-if="explainResults[d.id]" class="mt-2">
                    <div v-if="explainResults[d.id].error" class="text-amber-400 text-xs">
                      ⚠ {{ explainResults[d.id].error }}
                    </div>
                    <template v-else>
                      <table class="text-xs border-collapse w-full max-w-xl">
                        <tbody>
                          <tr class="border-b border-slate-700">
                            <td class="py-1 pr-3 text-slate-300 font-semibold">MtM au {{ explainResults[d.id].date1 }}</td>
                            <td class="py-1 font-mono text-slate-100 font-semibold text-right">{{ (explainResults[d.id].mtm1 * 100).toFixed(2) }}%</td>
                          </tr>
                          <tr v-for="s in explainResults[d.id].steps" :key="s.label" class="border-b border-slate-800/50">
                            <td class="py-1 pr-3 pl-3 text-slate-400">{{ s.label }}</td>
                            <td class="py-1 font-mono text-right"
                              :class="s.delta_pts >= 0 ? 'text-emerald-400' : 'text-red-400'">
                              {{ s.delta_pts >= 0 ? '+' : '' }}{{ s.delta_pts.toFixed(2) }} pts
                            </td>
                          </tr>
                          <tr class="border-b border-slate-800/50">
                            <td class="py-1 pr-3 pl-3 text-slate-500">Résidu (effets croisés)</td>
                            <td class="py-1 font-mono text-slate-500 text-right">
                              {{ explainResults[d.id].residual_pts >= 0 ? '+' : '' }}{{ explainResults[d.id].residual_pts.toFixed(2) }} pts
                            </td>
                          </tr>
                          <tr class="border-b border-slate-700">
                            <td class="py-1 pr-3 text-slate-300 font-semibold">MtM au {{ explainResults[d.id].date2 }}</td>
                            <td class="py-1 font-mono text-slate-100 font-semibold text-right">{{ (explainResults[d.id].mtm2 * 100).toFixed(2) }}%</td>
                          </tr>
                          <tr v-if="explainResults[d.id].flows_total_pts" class="border-b border-slate-800/50">
                            <td class="py-1 pr-3 text-slate-400">Flux détachés sur la période</td>
                            <td class="py-1 font-mono text-sky-400 text-right">+{{ explainResults[d.id].flows_total_pts.toFixed(2) }} pts</td>
                          </tr>
                          <tr v-if="explainResults[d.id].flows_total_pts">
                            <td class="py-1 pr-3 text-slate-300 font-semibold">P&L total de la période</td>
                            <td class="py-1 font-mono font-semibold text-right"
                              :class="explainResults[d.id].pnl_total_pts >= 0 ? 'text-emerald-400' : 'text-red-400'">
                              {{ explainResults[d.id].pnl_total_pts >= 0 ? '+' : '' }}{{ explainResults[d.id].pnl_total_pts.toFixed(2) }} pts
                            </td>
                          </tr>
                        </tbody>
                      </table>
                      <ul class="mt-2 flex flex-col gap-1">
                        <li v-for="(p, i) in explainResults[d.id].phrases" :key="i"
                          class="text-[11px] text-slate-400">• {{ p }}</li>
                      </ul>
                      <button class="btn-secondary text-[10px] px-2 py-1 mt-2"
                        :disabled="explainNoteLoading[d.id]" @click="downloadExplainNote(d)"
                        title="Génère la note PDF de l'explication de valo (waterfall, phrases, sensibilités Δ/Γ/véga en annexe) — mêmes chiffres que l'écran">
                        <span v-if="explainNoteLoading[d.id]"
                          class="w-3 h-3 border-2 border-slate-400 border-t-transparent rounded-full animate-spin inline-block mr-1"></span>
                        📄 Note d'explication
                      </button>
                    </template>
                  </div>
                </div>

              </template>
            </div>
          </div>

        </template>
      </div>
    </main>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { useDealsStore } from '../stores/deals.js'
import { apiFetch } from '../utils/api.js'
import HelpTip from '../components/HelpTip.vue'

const dealsStore = useDealsStore()

const refreshingId = ref(null)
const refreshResults = reactive({})

// ── Fiche détail dépliable (accordéon multi-ouvert) ─────────────────
const expanded = reactive({})
const details = reactive({})   // deal_id → full deal (with events)

async function toggleDetail(id) {
  expanded[id] = !expanded[id]
  if (expanded[id] && !details[id]) await loadDetail(id)
}

async function loadDetail(id) {
  try {
    const res = await apiFetch(`/api/deals/${id}`)
    if (res.ok) details[id] = await res.json()
  } catch { /* panel keeps showing "Chargement…" */ }
}

// Position (%) of a date within the deal's life [value_date → maturity_date]
function _datePct(d, iso) {
  const t0 = new Date(d.value_date).getTime()
  const t1 = new Date(d.maturity_date).getTime()
  if (!iso || t1 <= t0) return null
  const p = ((new Date(iso).getTime() - t0) / (t1 - t0)) * 100
  return Math.max(0, Math.min(100, p))
}

function lifePct(d) {
  // Resolved deals: life effectively ended at the resolving event.
  if (d.status !== 'actif') {
    const evs = details[d.id]?.events || []
    const resolving = evs.find(e => ['callé', 'ki', 'final'].includes(e.status))
    if (resolving) return Math.round(_datePct(d, resolving.event_date) ?? 100)
    return 100
  }
  const p = _datePct(d, new Date().toISOString().split('T')[0])
  return p === null ? null : Math.round(p)
}

function obsEvents(id) {
  return (details[id]?.events || []).filter(e => e.t_years > 0)
}

function eventPct(d, ev) {
  return _datePct(d, ev.event_date) ?? 0
}

function eventDotClass(ev) {
  const map = {
    'observé': 'bg-blue-500 border-blue-400',
    'callé': 'bg-amber-500 border-amber-400',
    'final': 'bg-emerald-500 border-emerald-400',
    'ki': 'bg-red-500 border-red-400',
    'annulé': 'bg-slate-700 border-slate-600 opacity-50',
    'futur': 'bg-slate-900 border-slate-600',
  }
  return map[ev.status] || 'bg-slate-800 border-slate-600'
}

function eventStatusClass(s) {
  const map = {
    'observé': 'bg-blue-900/40 text-blue-400',
    'callé': 'bg-amber-900/40 text-amber-400',
    'final': 'bg-emerald-900/40 text-emerald-400',
    'ki': 'bg-red-900/40 text-red-400',
    'annulé': 'bg-slate-800 text-slate-500 line-through',
    'futur': 'bg-slate-800 text-slate-500',
  }
  return map[s] || 'bg-slate-800 text-slate-500'
}

function s0For(id, name) {
  const strike = (details[id]?.events || []).find(e => e.t_years === 0)
  return strike?.spots?.[name] ?? null
}

function formatSpot(s) {
  if (!s) return '–'
  return s.toLocaleString('fr-FR', { maximumFractionDigits: 2 })
}

// Terms come in stored units (fractions) — display ×100 with % when is_pct.
// Array params show every per-observation row in AT-date order.
function formatTerm(t) {
  const one = (x) => t.is_pct ? `${+(x * 100).toFixed(4)}%` : `${+(+x).toFixed(4)}`
  return Array.isArray(t.value) ? t.value.map(one).join(' / ') : one(t.value)
}

// Watchlist join — live spot/perf and barrier gaps for active deals
function wlRow(id) {
  return watchlist.value.find(w => w.deal_id === id) || null
}

function wlUnderlying(id, name) {
  return wlRow(id)?.underlyings?.find(u => u.name === name) || null
}

// ── Alertes cycle de vie / barrières ────────────────────────────────
const alerts = ref([])
const refreshingBook = ref(false)
const refreshBookStatus = ref('')

async function loadAlerts() {
  try {
    const res = await apiFetch('/api/alerts?unread_only=true')
    if (res.ok) alerts.value = (await res.json()).alerts
  } catch { /* non bloquant — la page reste utilisable sans alertes */ }
}

function alertKindLabel(kind) {
  return {
    'callé': 'rappel', ki: 'KI', final: 'échéance',
    barrier_ki: 'barrière KI', barrier_ac: 'zone rappel',
  }[kind] || kind
}

function alertChipClass(kind) {
  if (kind === 'ki' || kind === 'barrier_ki') return 'bg-red-900/40 text-red-400'
  if (kind === 'final') return 'bg-emerald-900/40 text-emerald-400'
  return 'bg-amber-900/40 text-amber-400'
}

async function markRead(a) {
  await apiFetch(`/api/alerts/${a.id}/read`, { method: 'POST' })
  alerts.value = alerts.value.filter(x => x.id !== a.id)
}

async function markAllRead() {
  await apiFetch('/api/alerts/read-all', { method: 'POST' })
  alerts.value = []
}

async function refreshBook() {
  refreshingBook.value = true; refreshBookStatus.value = ''
  try {
    const res = await apiFetch('/api/alerts/refresh-book', { method: 'POST' })
    if (!res.ok) throw new Error((await res.json()).detail || 'Erreur refresh')
    const s = await res.json()
    refreshBookStatus.value = `✓ ${s.refreshed}/${s.deals} deal(s) rafraîchi(s), `
      + `${s.alerts_created} alerte(s)`
      + (s.resolved.length ? `, ${s.resolved.length} résolu(s)` : '')
    await dealsStore.loadDeals()
    loadWatchlist()
    loadAlerts()
  } catch (e) {
    refreshBookStatus.value = `⚠ ${e.message}`
  } finally {
    refreshingBook.value = false
  }
}

// ── MtM résiduel ────────────────────────────────────────────────────
const mtmLoading = reactive({})
const mtmResults = reactive({})
const mtmMode = reactive({})   // deal id -> 'booking' (défaut) | 'realized'

async function runMtm(id) {
  mtmLoading[id] = true
  mtmResults[id] = null
  try {
    const mode = mtmMode[id] || 'booking'
    const res = await apiFetch(`/api/deals/${id}/mtm`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ recalibrate: mode === 'realized' ? 'realized' : 'none' }),
    })
    const data = await res.json()
    if (!res.ok) throw new Error(data.detail || 'Erreur MtM')
    mtmResults[id] = data
  } catch (e) {
    mtmResults[id] = { error: e.message }
  } finally {
    mtmLoading[id] = false
  }
}

// P&L explain between two dates — waterfall temps/spot/vol/corr (see
// EXPLICATION_VALO_DESIGN.md). Date 1 defaults to booking, date 2 to today.
const explainD1 = reactive({})
const explainD2 = reactive({})
const explainLoading = reactive({})
const explainResults = reactive({})
const todayIso = new Date().toISOString().slice(0, 10)

async function runExplain(d) {
  explainLoading[d.id] = true
  explainResults[d.id] = null
  try {
    const res = await apiFetch(`/api/deals/${d.id}/mtm/explain`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        date1: explainD1[d.id] || d.value_date,
        date2: explainD2[d.id] || todayIso,
        recalibrate: 'realized',
      }),
    })
    const data = await res.json()
    if (!res.ok) throw new Error(data.detail || 'Erreur explication')
    explainResults[d.id] = data
  } catch (e) {
    explainResults[d.id] = { error: e.message }
  } finally {
    explainLoading[d.id] = false
  }
}

const explainNoteLoading = reactive({})

async function downloadExplainNote(d) {
  explainNoteLoading[d.id] = true
  try {
    const res = await apiFetch(`/api/deals/${d.id}/mtm/explain/report`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        date1: explainD1[d.id] || d.value_date,
        date2: explainD2[d.id] || todayIso,
        recalibrate: 'realized',
      }),
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      throw new Error(err.detail || 'Erreur génération PDF')
    }
    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `Explication_valo_${d.reference}.pdf`
    a.click()
    URL.revokeObjectURL(url)
  } catch (e) {
    refreshResults[d.id] = `⚠ Note d'explication : ${e.message}`
  } finally {
    explainNoteLoading[d.id] = false
  }
}

// Client-facing valuation note (PDF) — same body as the displayed MtM so the
// figure in the PDF is exactly the one on screen.
const noteLoading = reactive({})

async function downloadNote(d) {
  noteLoading[d.id] = true
  try {
    const mode = mtmMode[d.id] || 'booking'
    const res = await apiFetch(`/api/deals/${d.id}/mtm/report`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ recalibrate: mode === 'realized' ? 'realized' : 'none' }),
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      throw new Error(err.detail || 'Erreur génération PDF')
    }
    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `Note_valo_${d.reference}_${new Date().toISOString().slice(0, 10)}.pdf`
    a.click()
    URL.revokeObjectURL(url)
  } catch (e) {
    refreshResults[d.id] = `⚠ Note de valo : ${e.message}`
  } finally {
    noteLoading[d.id] = false
  }
}

// Flow A (module réinvestissement) — reconduire le même produit sur le même
// sous-jacent, départ forward (value date = aujourd'hui, tenor plein). Juste
// un pricing de comparaison, rien n'est booké tant que Philippe ne le décide
// pas explicitement. Voir MEMORY investment-solution-module.
const rollLoading = reactive({})
const rollResults = reactive({})

async function runRoll(d) {
  rollLoading[d.id] = true
  rollResults[d.id] = null
  try {
    const res = await apiFetch(`/api/deals/${d.id}/reinvest/roll`, { method: 'POST' })
    const data = await res.json()
    if (!res.ok) throw new Error(data.detail || 'Erreur reconduction')
    rollResults[d.id] = data
  } catch (e) {
    rollResults[d.id] = { error: e.message }
  } finally {
    rollLoading[d.id] = false
  }
}

// Effective market parameters of the MtM run — one compact line so a quoted
// number is never separated from what priced it.
function marketUsedLabel(mu) {
  const uls = Object.entries(mu.sigma || {})
    .map(([n, s]) => `${n} σ ${s}%` + (mu.q && mu.q[n] != null ? ` q ${mu.q[n]}%` : ''))
    .join(' · ')
  let corr = ''
  const c = mu.corr || []
  if (c.length === 2) corr = ` · ρ ${(c[0][1] * 100).toFixed(0)}%`
  else if (c.length > 2) {
    let sum = 0, k = 0
    for (let i = 0; i < c.length; i++) for (let j = i + 1; j < c.length; j++) { sum += c[i][j]; k++ }
    corr = ` · ρ̄ ${(sum / k * 100).toFixed(0)}%`
  }
  const model = mu.model === 'constant' ? 'GBM' : mu.model
  let src = mu.source && mu.source.indexOf('realized') === 0
    ? `marché actuel${mu.window_returns ? ` (${mu.window_returns} rendements)` : ''}`
    : 'params booking'
  if (mu.source && mu.source.indexOf('+overrides') >= 0) src += ' + overrides'
  return `${uls}${corr} · r ${mu.r}% · ${model} · ${src}`
}

const watchlist = ref([])
const watchlistError = ref('')

async function loadWatchlist() {
  watchlistError.value = ''
  try {
    watchlist.value = await dealsStore.getWatchlist()
  } catch (e) {
    watchlistError.value = e.message
  }
}

// Chip color = how close the worst-of currently is to that barrier, read in
// the direction the barrier bites: a KI hurts when WOF falls TO it (small
// positive gap = danger), an autocall triggers when WOF rises ABOVE it.
function barrierChipClass(b) {
  const g = b.gap_pts
  if (b.kind === 'ki') {
    if (g <= 0) return 'bg-red-900/60 text-red-300 border border-red-700'
    if (g <= 5) return 'bg-red-900/40 text-red-400'
    if (g <= 15) return 'bg-amber-900/40 text-amber-400'
    return 'bg-slate-800 text-slate-500'
  }
  if (b.kind === 'autocall') {
    if (g >= 0) return 'bg-emerald-900/40 text-emerald-400'
    if (g >= -5) return 'bg-amber-900/40 text-amber-400'
    return 'bg-slate-800 text-slate-500'
  }
  // 'neutral' — M_ param whose usage in the script is ambiguous: the gap is
  // shown but not color-read, we don't know which way the barrier bites.
  return 'bg-slate-800 text-slate-400 border border-slate-600'
}

function barrierGapLabel(b) {
  const g = b.gap_pts
  if (b.kind === 'ki' && g <= 0) return `franchie (${g.toFixed(1)} pts)`
  if (b.kind === 'autocall' && g >= 0) return `≥ barrière (+${g.toFixed(1)} pts)`
  return `${g >= 0 ? '+' : ''}${g.toFixed(1)} pts`
}

const statusOptions = ['actif', 'callé', 'échu', 'résilié']

const filters = reactive({
  contrepartie: '',
  ticker: '',
  productType: '',
  status: '',
})

const hasActiveFilters = computed(() =>
  !!(filters.contrepartie || filters.ticker || filters.productType || filters.status)
)

function resetFilters() {
  filters.contrepartie = ''
  filters.ticker = ''
  filters.productType = ''
  filters.status = ''
}

const tickerOptions = computed(() => {
  const set = new Set()
  for (const d of dealsStore.deals) {
    for (const u of d.underlyings || []) {
      if (u.ticker) set.add(u.ticker)
    }
  }
  return [...set].sort()
})

const productTypeOptions = computed(() => {
  const set = new Set()
  for (const d of dealsStore.deals) {
    if (d.product_type) set.add(d.product_type)
  }
  return [...set].sort()
})

const filteredDeals = computed(() => {
  return dealsStore.deals.filter(d => {
    if (filters.status && d.status !== filters.status) return false
    if (filters.productType && d.product_type !== filters.productType) return false
    if (filters.contrepartie && !d.contrepartie.toLowerCase().includes(filters.contrepartie.toLowerCase())) return false
    if (filters.ticker && !(d.underlyings || []).some(u => u.ticker === filters.ticker)) return false
    return true
  })
})

// Hit-ratio and other aggregates recompute over whatever is currently
// filtered — slicing by client/sous-jacent/type shows that segment's own
// ratio, not just the whole book's.
const stats = computed(() => {
  const deals = filteredDeals.value
  const byStatus = {}
  const byOutcome = {}
  let nominalTotal = 0
  let payoutSum = 0
  let payoutCount = 0

  for (const d of deals) {
    byStatus[d.status] = (byStatus[d.status] || 0) + 1
    nominalTotal += d.nominal || 0
    if (d.resolution_outcome) {
      byOutcome[d.resolution_outcome] = (byOutcome[d.resolution_outcome] || 0) + 1
    }
    if (d.realized_payout != null) {
      payoutSum += d.realized_payout
      payoutCount++
    }
  }

  const resolved = (byOutcome.callé || 0) + (byOutcome.final || 0) + (byOutcome.ki || 0)

  return {
    total: deals.length,
    nominalTotal,
    byStatus,
    byOutcome,
    resolved,
    avgRealizedPayout: payoutCount ? payoutSum / payoutCount : null,
  }
})

function pct(n, total) {
  return total ? `${Math.round((n / total) * 100)}%` : '0%'
}

function statusClass(s) {
  const map = {
    actif: 'bg-emerald-900/40 text-emerald-400',
    'callé': 'bg-amber-900/40 text-amber-400',
    'échu': 'bg-slate-700 text-slate-400',
    'résilié': 'bg-red-900/40 text-red-400',
  }
  return map[s] || 'bg-slate-800 text-slate-500'
}

function formatNominal(n) {
  return (n ?? 0).toLocaleString('fr-FR')
}

function describeOutcome(ev) {
  if (!ev) return null
  if (ev.outcome === 'callé') return `Rappel anticipé détecté — ${ev.event_date}`
  if (ev.outcome === 'final') return `Remboursé à maturité (${ev.event_date}) — 100% du nominal`
  if (ev.outcome === 'ki') return `Knock-in à maturité (${ev.event_date}) — ${(ev.maturity_payout * 100).toFixed(1)}% du nominal remboursé`
  if (ev.outcome === 'en_cours') return 'Toujours en vie — aucun rappel ni maturité détecté sur l\'historique disponible'
  return null
}

async function refresh(dealId) {
  refreshingId.value = dealId
  try {
    const res = await dealsStore.refreshEvents(dealId)
    refreshResults[dealId] = describeOutcome(res.evaluation) || res.message
  } catch (e) {
    refreshResults[dealId] = `⚠ ${e.message}`
  } finally {
    refreshingId.value = null
    await dealsStore.loadDeals()
    loadWatchlist()   // a refresh can resolve a deal, dropping it off the watchlist
    if (expanded[dealId]) await loadDetail(dealId)   // open panel shows fresh events
  }
}

onMounted(() => {
  dealsStore.loadDeals()
  loadWatchlist()
  loadAlerts()
})
</script>
