<template>
  <div class="flex-1 flex flex-col min-h-0 text-slate-100">

    <main class="flex-1 overflow-y-auto p-6">
      <div class="max-w-[1600px] mx-auto flex flex-col gap-3">

        <div class="page-header">
          <div class="flex items-center gap-3">
            <BackLink :fallback="{ path: '/', query: { category: 'life_cycle' } }" />
            <h1 class="page-title">Booking — produits bookés</h1>
          </div>
          <div class="page-actions">
            <span v-if="refreshBookStatus" class="text-xs" style="color: var(--muted);">{{ refreshBookStatus }}</span>
            <button class="btn-secondary text-xs px-3 py-1.5" :disabled="refreshingBook" @click="refreshBook">
              {{ refreshingBook ? '⏳ Rafraîchissement…' : '🔄 Rafraîchir le book' }}
            </button>
            <span v-if="dealsStore.deals.length" class="text-xs" style="color: var(--muted);">
              {{ filteredDeals.length }} / {{ dealsStore.deals.length }} deal(s)
            </span>
          </div>
        </div>

        <LoadingSpinner v-if="dealsStore.loading && !dealsStore.deals.length" class="py-10" />

        <EmptyState v-else-if="!dealsStore.deals.length" icon="📒" title="Aucun deal booké pour l'instant"
          hint="Un deal se book depuis l'onglet Deal du Pricer, une fois un pricing lancé." />

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

          <!-- ── Stats agrégées (sur la sélection filtrée) ───────── -->
          <div class="card kpi-tile">
            <div class="flex flex-wrap gap-x-6 gap-y-3 relative">
              <div>
                <div class="stat-value num" style="font-size:1.4rem;">{{ stats.total }}</div>
                <div class="stat-label">Deals</div>
              </div>
              <div>
                <div class="stat-value num" style="font-size:1.4rem;">{{ formatNominal(stats.nominalTotal) }}</div>
                <div class="stat-label">Nominal total</div>
              </div>
              <div>
                <div class="text-slate-500 text-[10px] uppercase tracking-wider mb-0.5">Par statut</div>
                <div class="flex gap-1.5 flex-wrap">
                  <span v-for="s in statusOptions" :key="s"
                    v-show="stats.byStatus[s]"
                    :class="statusClass(s)" class="badge">
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
                  <span v-if="stats.byOutcome.callé" class="badge badge-gold">
                    callé {{ stats.byOutcome.callé }} ({{ pct(stats.byOutcome.callé, stats.resolved) }})
                  </span>
                  <span v-if="stats.byOutcome.final" class="badge badge-positive">
                    final {{ stats.byOutcome.final }} ({{ pct(stats.byOutcome.final, stats.resolved) }})
                  </span>
                  <span v-if="stats.byOutcome.ki" class="badge badge-negative">
                    ki {{ stats.byOutcome.ki }} ({{ pct(stats.byOutcome.ki, stats.resolved) }})
                  </span>
                </div>
              </div>
              <div v-if="stats.avgRealizedPayout != null">
                <div class="stat-value num" style="font-size:1.4rem;">{{ formatPercent(stats.avgRealizedPayout * 100, 1) }}</div>
                <div class="stat-label">Remboursement moyen réalisé</div>
              </div>
            </div>
          </div>

          <!-- ── Barre d'onglets ────────────────────────────────── -->
          <div class="flex border-b border-slate-800 -mb-1">
            <button @click="activeTab = 'watchlist'"
              :class="activeTab === 'watchlist' ? 'border-b-2 border-blue-500 text-slate-100' : 'text-slate-500 hover:text-slate-300'"
              class="px-5 py-2.5 text-sm font-medium transition-colors">
              Surveillance
            </button>
            <button @click="activeTab = 'deals'"
              :class="activeTab === 'deals' ? 'border-b-2 border-blue-500 text-slate-100' : 'text-slate-500 hover:text-slate-300'"
              class="px-5 py-2.5 text-sm font-medium transition-colors">
              Deals ({{ filteredDeals.length }})
            </button>
            <RouterLink to="/risk"
              class="ml-auto self-center text-xs text-slate-500 hover:text-slate-300 transition-colors px-3"
              title="Portefeuilles, Greeks agrégés, chocs et P&L explain ont déménagé dans le module Risk Management">
              Portefeuilles &amp; chocs → Risk Management ↗
            </RouterLink>
          </div>

          <div v-if="commercialScope.active && activeTab === 'watchlist'"
               class="flex items-center justify-between gap-3 rounded-lg border border-blue-800/50 bg-blue-950/20 px-3 py-2 text-xs">
            <div>
              <span class="font-semibold text-blue-300">Surveillance filtrée</span>
              <span class="text-slate-400"> · {{ commercialScope.label }}</span>
              <span class="text-slate-600"> — mêmes événements et statuts que le Life Cycle.</span>
            </div>
            <RouterLink to="/booking" class="text-blue-400 hover:text-blue-300 whitespace-nowrap">
              Afficher tout
            </RouterLink>
          </div>

          <!-- ── Onglet Surveillance : watchlist barrières ──────── -->
          <template v-if="activeTab === 'watchlist'">

          <EmptyState v-if="commercialScope.active && !watchlistLoading && !watchlist.length && !watchlistError"
                      icon="✓" title="Aucun deal actif sur ce périmètre"
                      hint="Les transactions importées restent dans Clients : elles ne sont pas des positions du book et n'ont pas de Life Cycle." />

          <!-- ── Watchlist barrières (deals actifs) ───────────── -->
          <div v-if="watchlist.length || watchlistError" class="card">
            <h2 class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3">
              Watchlist — proximité barrières
              <HelpTip width="w-72" text="Deals actifs triés par défaut par prochaine observation, puis par proximité de barrière à date égale. Cliquez sur un en-tête pour choisir le tri, puis recliquez pour inverser son sens. Détection par convention de nommage des PARAM (AC_BAR, KI_BAR…) — un script aux noms inhabituels peut passer à travers. Les niveaux sont ceux réellement figés au booking ; le défaut du script n'est utilisé qu'en l'absence de surcharge." />
            </h2>

            <div v-if="watchlistError" class="text-xs text-amber-400">⚠ {{ watchlistError }}</div>

            <template v-else>
            <DataFilterBar v-if="watchlist.length" class="border-0 p-0 bg-transparent mb-3"
                           :fields="wlFilterFields" :state="wlFilter.state"
                           :field-options="wlFilter.fieldOptions.value"
                           :has-active-filters="wlFilter.hasActiveFilters.value"
                           :sorts="wlSorts" :sort-by="wlFilter.sortBy.value" :sort-dir="wlFilter.sortDir.value"
                           :count="sortedWatchlist.length" :total="watchlist.length" noun="deal(s)"
                           @update:sort-by="wlFilter.sortBy.value = $event"
                           @toggle-dir="wlFilter.toggleSortDir()" @reset="wlFilter.reset()" />

            <div class="overflow-x-auto table-shell" tabindex="0" role="region">
              <table class="w-full text-xs border-collapse">
                <thead>
                  <tr class="border-b border-slate-700">
                    <th v-for="column in wlColumns" :key="column.key" scope="col"
                      class="watchlist-heading" :class="{ num: column.key === 'wof' }"
                      :aria-sort="wlFilter.sortBy.value === column.key
                        ? (wlFilter.sortDir.value === 'asc' ? 'ascending' : 'descending') : 'none'">
                      <div class="watchlist-heading__content" :class="{ 'justify-end': column.key === 'wof' }">
                        <button type="button" class="watchlist-heading__sort"
                          :class="{ 'watchlist-heading__sort--active': wlFilter.sortBy.value === column.key }"
                          :title="watchlistSortTitle(column)" :aria-label="watchlistSortTitle(column)"
                          @click="sortWatchlistBy(column.key)">
                          <span>{{ column.heading || column.label }}</span>
                          <span aria-hidden="true" class="watchlist-heading__arrow">{{ wlFilter.sortBy.value === column.key ? (wlFilter.sortDir.value === 'asc' ? '↑' : '↓') : '↕' }}</span>
                        </button>
                        <HelpTip width="w-72" :text="column.help" />
                      </div>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="w in sortedWatchlist" :key="w.deal_id"
                    class="border-b border-slate-800/50 hover:bg-slate-800/20 transition-colors">
                    <td class="py-2 pr-3">
                      <div class="flex items-center gap-1.5">
                        <button type="button"
                          class="font-mono font-semibold text-blue-400 hover:underline whitespace-nowrap"
                          @click="openDealDetail(w.deal_id)">
                          {{ w.reference }}
                        </button>
                        <button type="button"
                          class="text-slate-500 hover:text-blue-300 shrink-0 transition-colors"
                          :class="copiedReference === w.reference ? 'text-emerald-400' : ''"
                          :title="copiedReference === w.reference ? 'Référence copiée' : 'Copier la référence du deal'"
                          :aria-label="`Copier la référence ${w.reference}`"
                          @click.stop="copyDealReference(w.reference)">
                          {{ copiedReference === w.reference ? '✓' : '⧉' }}
                        </button>
                        <RouterLink :to="`/pricer?dealId=${w.deal_id}`"
                          class="text-slate-500 hover:text-slate-300 shrink-0" title="Ouvrir dans le Pricer">
                          ⇥
                        </RouterLink>
                      </div>
                    </td>
                    <td class="py-2 pr-3 text-slate-300">{{ w.contrepartie }}</td>
                    <td class="py-2 pr-3 text-slate-400 whitespace-nowrap">
                      {{ (w.underlyings || []).map(u => u.ticker || u.name).join(' / ') || '—' }}
                    </td>
                    <td class="py-2 pr-3 text-slate-300">
                      {{ watchlistProductName(w) || '—' }}
                    </td>
                    <td class="py-2 pr-3 whitespace-nowrap">
                      <span v-if="w.product_type" class="text-slate-500 text-[10px] border border-slate-700 rounded px-1.5 py-0.5">
                        {{ productTypeLabel(w.product_type) }}
                      </span>
                      <span v-else class="text-slate-600">—</span>
                    </td>
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
                    <td class="py-2 pr-3 font-mono num whitespace-nowrap">
                      <template v-if="w.wof != null">
                        <span :class="w.wof >= 1 ? 'text-emerald-400' : 'text-red-400'">
                          {{ (w.wof * 100).toFixed(1) }}%
                        </span>
                        <span v-if="w.wof_min != null" class="text-slate-600 text-[10px] ml-1">
                          (min {{ (w.wof_min * 100).toFixed(1) }}%)
                        </span>
                      </template>
                      <span v-else-if="w.next_event && w.strike_pending" class="text-slate-600"
                            title="Le strike n'a pas encore eu lieu — aucun niveau de strike n'est fixé, donc aucune performance ne peut être mesurée">
                        avant strike
                      </span>
                      <span v-else class="text-slate-600" title="Niveau de strike manquant — lancez un Refresh sur ce deal">n/d</span>
                    </td>
                    <td class="py-2">
                      <div class="flex gap-1.5 flex-wrap">
                        <span v-for="b in w.barriers" :key="b.name"
                          :class="barrierChipClass(b)"
                          class="px-1.5 py-0.5 rounded text-[10px] font-mono font-semibold whitespace-nowrap">
                          {{ b.name }} {{ (b.level * 100).toFixed(0) }}%<template v-if="b.observable && b.observable !== 'WOF'"> vs {{ b.observable }}</template> · {{ barrierGapLabel(b) }}
                        </span>
                        <span v-if="!w.barriers.length" class="text-slate-600 text-[10px]">aucune dans le script</span>
                      </div>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
            </template>
          </div>

          </template><!-- /watchlist tab -->

          <!-- ── Onglet Deals : filtres + liste ────────────────── -->
          <template v-if="activeTab === 'deals'">

          <!-- ── Filtres ─────────────────────────────────────────── -->
          <div class="card flex flex-wrap gap-3 items-end">
            <div class="flex flex-col gap-1 min-w-[140px]">
              <label class="text-[10px] text-slate-500 uppercase tracking-wider">Contrepartie</label>
              <input v-model="filters.contrepartie" type="text" placeholder="Filtrer…"
                class="bg-slate-800 border border-slate-700 rounded px-2.5 py-1.5 text-xs text-slate-200 placeholder-slate-600 focus:outline-none focus:border-blue-600" />
            </div>
            <div class="flex flex-col gap-1">
              <label class="text-[10px] text-slate-500 uppercase tracking-wider">Sous-jacent</label>
              <select v-model="filters.ticker" class="select text-xs py-1.5 min-w-[120px]">
                <option value="">Tous</option>
                <option v-for="t in tickerOptions" :key="t" :value="t">{{ t }}</option>
              </select>
            </div>
            <div class="flex flex-col gap-1">
              <label class="text-[10px] text-slate-500 uppercase tracking-wider">Type</label>
              <select v-model="filters.productType" class="select text-xs py-1.5 min-w-[140px]">
                <option value="">Tous</option>
                <option v-for="p in productTypeOptions" :key="p" :value="p">{{ p }}</option>
              </select>
            </div>
            <div class="flex flex-col gap-1">
              <label class="text-[10px] text-slate-500 uppercase tracking-wider">Statut</label>
              <select v-model="filters.status" class="select text-xs py-1.5">
                <option value="">Tous</option>
                <option v-for="s in statusOptions" :key="s" :value="s">{{ s }}</option>
              </select>
            </div>
            <div class="flex flex-col gap-1">
              <label class="text-[10px] text-slate-500 uppercase tracking-wider">Portefeuille</label>
              <select v-model="filters.portfolioId" class="select text-xs py-1.5 booking-portfolio-filter">
                <option value="">Tous</option>
                <option v-for="p in portfolios" :key="p.id" :value="String(p.id)">
                  {{ p.name }}
                </option>
              </select>
            </div>
            <div class="flex flex-col gap-1">
              <label class="text-[10px] text-slate-500 uppercase tracking-wider">Trier par</label>
              <div class="flex items-center gap-1">
                <select v-model="sortBy" class="select text-xs py-1.5">
                  <option value="status">Statut</option>
                  <option value="maturity_date">Maturité</option>
                  <option value="reference">Référence</option>
                </select>
                <button class="btn-secondary text-xs px-2 py-1.5" @click="toggleSortDir"
                  :title="sortDir === 'asc' ? 'Croissant' : 'Décroissant'">
                  {{ sortDir === 'asc' ? '↑' : '↓' }}
                </button>
              </div>
            </div>
            <button v-if="hasActiveFilters" class="btn-secondary text-xs px-3 py-1.5 self-end" @click="resetFilters">
              ✕ Réinitialiser
            </button>
          </div>

          <!-- ── Liste des deals ──────────────────────────────── -->
          <div v-if="!filteredDeals.length" class="card text-sm text-slate-500">
            Aucun deal ne correspond à ces filtres.
          </div>

          <div v-for="(d, dealIndex) in filteredDeals" :key="d.id" :id="`deal-${d.id}`"
            class="card deal-card flex flex-col gap-3 hover:shadow-xl hover:shadow-black/30
                   hover:border-slate-700 transition-all duration-200 scroll-mt-4"
            :class="{ 'deal-card--alternate': dealIndex % 2 === 1 }">
            <!-- Ligne d'en-tête — cliquable pour déplier la fiche détail -->
            <div class="deal-card__header cursor-pointer select-none"
              @click="toggleDetail(d.id)">
              <div class="deal-card__identity">
                <div class="flex items-center gap-2 min-w-0">
                  <span class="text-slate-500 text-xs shrink-0">{{ expanded[d.id] ? '▾' : '▸' }}</span>
                  <span class="font-mono font-semibold text-slate-200 whitespace-nowrap">{{ d.reference }}</span>
                  <button type="button"
                    class="text-slate-500 hover:text-blue-300 shrink-0 transition-colors"
                    :class="copiedReference === d.reference ? 'text-emerald-400' : ''"
                    :title="copiedReference === d.reference ? 'Référence copiée' : 'Copier la référence du deal'"
                    :aria-label="`Copier la référence ${d.reference}`"
                    @click.stop="copyDealReference(d.reference)">
                    {{ copiedReference === d.reference ? '✓' : '⧉' }}
                  </button>
                </div>
                <div class="deal-card__identity-meta">
                  <span v-if="d.product_type" class="font-medium text-slate-400">
                    {{ productTypeLabel(d.product_type) }}
                  </span>
                  <span v-if="d.product_type && d.contrepartie" class="text-slate-600">·</span>
                  <span class="text-slate-300">{{ d.contrepartie }}</span>
                  <span class="text-[10px] border rounded px-1.5 py-0.5"
                    style="border-color: var(--border); background: var(--surface2); color: var(--accent);">
                    Fixings automatiques
                  </span>
                  <span :class="statusClass(d.status)" class="badge">
                    {{ statusLabel(d.status) }}
                  </span>
                </div>
              </div>
              <div class="deal-card__actions" @click.stop>
                <template v-if="canAssignPortfolio(d)">
                  <ActionMenu :label="dealPortfolioLabel(d)" class="deal-card__portfolio"
                    :title="`${dealPortfolioLabel(d)} — un deal peut alimenter plusieurs vues de risque`" @click.stop>
                      <label v-for="p in portfoliosForDeal(d)" :key="p.id"
                        class="flex items-center gap-2 px-2 py-1.5 text-[10px] cursor-pointer hover:bg-slate-800 rounded">
                        <input type="checkbox" :checked="dealHasPortfolio(d, p.id)"
                          :disabled="portfolioAssigning[d.id]"
                          @change="toggleDealPortfolio(d, p.id, $event.target.checked)" />
                        <span>{{ p.name }}</span>
                      </label>
                      <div v-if="!portfoliosForDeal(d).length" class="px-2 py-1 text-[10px] text-slate-500">
                        Aucun portefeuille pour ce compte.
                      </div>
                  </ActionMenu>
                  <span v-if="portfolioAssignmentStatus[d.id]" class="text-[10px] max-w-40"
                    :class="portfolioAssignmentStatus[d.id].startsWith('⚠') ? 'text-red-500' : 'text-emerald-600'">
                    {{ portfolioAssignmentStatus[d.id] }}
                  </span>
                </template>
                <span v-else class="deal-card__portfolio-label"
                  :title="`${dealPortfolioLabel(d)} — modification réservée au propriétaire`">
                  {{ dealPortfolioLabel(d) }}
                </span>
                <button v-if="d.status === 'actif'" class="btn-secondary text-xs px-3 py-1.5"
                  :disabled="greeksLoading[d.id]" @click.stop="runGreeks(d.id)"
                  title="Greeks du deal (bump-and-reprice CRN) : delta/gamma/vega par sous-jacent, theta, rho — mêmes hypothèses de marché que le mode MtM sélectionné">
                  <span v-if="greeksLoading[d.id]"
                    class="w-3 h-3 border-2 border-slate-400 border-t-transparent rounded-full animate-spin inline-block mr-1"></span>
                  Δ Greeks
                </button>
                <button v-if="d.status === 'actif'" class="btn-secondary text-xs px-3 py-1.5"
                  @click.stop="toggleShockPanel(d.id)"
                  title="Choc de marché (full reprice, pas une approximation linéaire) : spot/vol/taux/corrélation, sur ce deal seul">
                  ⚡ Choc
                </button>
                <button class="btn-secondary text-xs px-3 py-1.5" :disabled="refreshingId === d.id"
                  @click.stop="refresh(d.id)">
                  <span v-if="refreshingId === d.id"
                    class="w-3 h-3 border-2 border-slate-400 border-t-transparent rounded-full animate-spin inline-block mr-1"></span>
                  ↻ Refresh
                </button>
                <ActionMenu label="→ Ouvrir" @click.stop>
                    <RouterLink
                      :to="{ path: '/pricer', query: { dealId: d.id, tab: 'script' } }"
                      class="deal-open-menu__item">
                      Ouvrir ici
                    </RouterLink>
                    <RouterLink
                      :to="{ path: '/pricer', query: { dealId: d.id, tab: 'script' } }"
                      class="deal-open-menu__item" target="_blank" rel="noopener noreferrer">
                      Ouvrir dans un nouvel onglet ↗
                    </RouterLink>
                </ActionMenu>
              </div>
            </div>

            <!-- Vue synthétique : contrat, marché, repricing et résultat restent
                 séparés pour qu'un niveau contractuel ne soit jamais lu comme
                 une hypothèse du dernier calcul. Chaque panneau a sa teinte, pour
                 que deux voisins ne se confondent pas ; les chiffres, eux, sont
                 posés sur blanc et gardent toute leur lisibilité. -->
            <div class="deal-overview-grid">
              <section class="deal-panel deal-panel--contract">
                <header class="deal-panel__head">
                  <span class="deal-panel__dot" aria-hidden="true"></span>
                  <h3 class="deal-panel__title">Deal & economics</h3>
                </header>
                <div class="deal-well deal-figures">
                  <div>
                    <span class="deal-label">Nominal</span>
                    <strong class="deal-value">{{ formatNominal(d.nominal) }} {{ d.devise }}</strong>
                  </div>
                  <div>
                    <span class="deal-label">Prix traité</span>
                    <strong class="deal-value">{{ d.price_traded.toFixed(2) }}%</strong>
                  </div>
                  <div>
                    <span class="deal-label">Fair value</span>
                    <strong class="deal-value is-secondary">{{ d.fair_value.toFixed(2) }}%</strong>
                  </div>
                  <div>
                    <span class="deal-label">Marge</span>
                    <strong class="deal-value" :class="signToneClass(d.margin)">
                      {{ d.margin >= 0 ? '+' : '' }}{{ d.margin.toFixed(2) }}%
                    </strong>
                  </div>
                </div>
                <dl class="deal-dates">
                  <div><dt>Trade</dt><dd>{{ formatDate(d.trade_date) }}</dd></div>
                  <div><dt>Strike</dt><dd>{{ formatDate(d.strike_date) }}</dd></div>
                  <div><dt>Value</dt><dd>{{ formatDate(d.value_date) }}</dd></div>
                  <div><dt>Maturité</dt><dd>{{ formatDate(d.maturity_date) }}</dd></div>
                  <div><dt>Paiement</dt><dd>{{ formatDate(d.payment_date) }}</dd></div>
                </dl>
                <div v-if="details[d.id]?.terms?.length" class="deal-term-list">
                  <div v-for="t in primaryTerms(details[d.id].terms)" :key="t.name"
                    class="deal-term" :title="`${t.name}${t.desc ? ` — ${t.desc}` : ''}`">
                    <span>{{ termBusinessLabel(t.name) }}</span>
                    <strong>{{ formatTerm(t) }}</strong>
                  </div>
                  <details v-if="details[d.id].terms.length > primaryTerms(details[d.id].terms).length"
                    class="deal-technical-details">
                    <summary>Voir les {{ details[d.id].terms.length }} termes contractuels</summary>
                    <div class="deal-term-list mt-2">
                      <div v-for="t in details[d.id].terms" :key="t.name" class="deal-term" :title="t.desc || t.name">
                        <span>{{ termBusinessLabel(t.name) }}</span>
                        <strong>{{ formatTerm(t) }}</strong>
                      </div>
                    </div>
                  </details>
                </div>
                <div v-if="d.realized_payout != null" class="deal-realized">
                  Remboursement réalisé :
                  <strong>{{ (d.realized_payout * 100).toFixed(2) }}%</strong>
                  <span v-if="d.resolution_outcome"> ({{ d.resolution_outcome }})</span>
                </div>
              </section>

              <section class="deal-panel deal-panel--market">
                <header class="deal-panel__head">
                  <span class="deal-panel__dot" aria-hidden="true"></span>
                  <h3 class="deal-panel__title">Sous-jacents & niveaux</h3>
                </header>
                <div class="deal-well deal-underlyings">
                  <div v-for="u in d.underlyings" :key="u.name" class="deal-underlying">
                    <div class="deal-underlying__top">
                      <span class="deal-underlying__name" :title="u.name">{{ u.ticker || u.name }}</span>
                      <span v-if="wlUnderlying(d.id, u.name)?.perf != null"
                        class="deal-perf" :class="signToneClass(wlUnderlying(d.id, u.name).perf - 1)"
                        title="Performance depuis le strike">
                        {{ signedPercent((wlUnderlying(d.id, u.name).perf - 1) * 100, 1) }}
                      </span>
                    </div>
                    <div class="deal-underlying__levels">
                      <span>Strike <strong>{{ formatSpot(strikeFor(d.id, u.name)) }}</strong></span>
                      <span class="deal-underlying__arrow" aria-hidden="true">→</span>
                      <span>Cours actuel <strong>{{ formatSpot(wlUnderlying(d.id, u.name)?.spot) }}</strong></span>
                    </div>
                  </div>
                </div>
                <div v-if="wlRow(d.id)?.barriers?.length" class="deal-well deal-barriers">
                  <!-- Règle : position de l'observable entre protection et rappel,
                       relue des écarts ci-dessous (utils/barriers.js). -->
                  <div v-for="g in barrierGauges(wlRow(d.id).barriers)" :key="g.observable" class="barrier-gauge">
                    <div class="barrier-gauge__caption">
                      <span>{{ gaugeObservableLabel(d, g.observable) }}</span>
                      <span>en % du strike</span>
                    </div>
                    <div class="barrier-gauge__track" role="img" :aria-label="gaugeAriaLabel(d, g)">
                      <div v-if="g.lossZonePct != null" class="barrier-gauge__zone barrier-gauge__zone--loss"
                        :style="{ width: `${g.lossZonePct}%` }"></div>
                      <div v-if="g.gainZonePct != null" class="barrier-gauge__zone barrier-gauge__zone--gain"
                        :style="{ width: `${g.gainZonePct}%` }"></div>
                      <div v-for="m in g.marks" :key="m.name"
                        class="barrier-gauge__mark" :class="`barrier-gauge__mark--${m.kind}`"
                        :style="{ left: `${m.pct}%` }"
                        :title="`${barrierBusinessLabel(m)} — ${formatGaugeLevel(m.level)}`">
                        <span v-if="m.labelled">{{ formatGaugeLevel(m.level) }}</span>
                      </div>
                      <div class="barrier-gauge__cursor" :style="{ left: `${g.currentPct}%` }">
                        <span>{{ formatGaugeLevel(g.current) }}</span>
                      </div>
                    </div>
                  </div>
                  <div v-for="b in wlRow(d.id).barriers" :key="b.name" class="deal-barrier-row">
                    <span class="deal-barrier-row__tick" :class="`deal-barrier-row__tick--${b.kind}`"
                      aria-hidden="true"></span>
                    <div class="min-w-0">
                      <span class="deal-barrier-name">{{ barrierBusinessLabel(b) }}</span>
                      <span class="deal-barrier-code">{{ b.name }}</span>
                    </div>
                    <strong>{{ (b.level * 100).toFixed(0) }}%</strong>
                    <span :class="barrierChipClass(b)"
                      class="px-1.5 py-0.5 rounded text-[10px] font-mono font-semibold whitespace-nowrap">
                      {{ barrierGapLabel(b) }}
                    </span>
                  </div>
                </div>
                <div v-else class="deal-empty-state">
                  {{ d.status === 'actif' ? 'Aucune barrière détectée dans le script.' : 'Niveaux de marché non suivis sur ce deal.' }}
                </div>
              </section>

              <section class="deal-panel deal-panel--model">
                <header class="deal-panel__head">
                  <span class="deal-panel__dot" aria-hidden="true"></span>
                  <h3 class="deal-panel__title">Paramètres de repricing</h3>
                </header>
                <label v-if="d.status === 'actif'" class="deal-basis">
                  <span class="deal-label">Base du calcul</span>
                  <select class="select deal-panel__select w-full text-xs py-1.5"
                    :value="mtmModeFor(d.id)" :disabled="mtmLoading[d.id]" @click.stop
                    @change="setMtmMode(d.id, $event.target.value)"
                    title="Choix des hypothèses utilisées pour le prochain calcul">
                    <option value="realized">Marché actuel</option>
                    <option value="booking">Paramètres du booking</option>
                  </select>
                </label>
                <div v-else class="deal-basis">
                  <span class="deal-label">Base du calcul</span>
                  <strong class="deal-value">{{ mtmModeFor(d.id) === 'realized' ? 'Marché actuel' : 'Paramètres du booking' }}</strong>
                </div>
                <label v-if="['actif', 'en_reglement'].includes(d.status)" class="deal-basis">
                  <span class="deal-label">Date de valorisation</span>
                  <input type="date" class="input deal-panel__select w-full text-xs py-1.5"
                    :disabled="mtmLoading[d.id]" :value="mtmDateFor(d.id)" :min="mtmMinDate(d)" :max="todayIso"
                    @click.stop @change="setMtmDate(d.id, $event.target.value)"
                    title="Date à laquelle le deal et son marché sont valorisés" />
                </label>
                <p class="deal-basis-note">
                  {{ mtmModeFor(d.id) === 'realized'
                    ? 'Données Yahoo actualisées. Le taux et le funding restent ceux du booking.'
                    : 'Paramètres de modèle, volatilités et corrélations du booking, avec les cours disponibles à la date du calcul.' }}
                </p>
                <div class="deal-well deal-figures">
                  <div>
                    <span class="deal-label">Modèle</span>
                    <strong class="deal-value">{{ repricingModelLabel(d) }}</strong>
                  </div>
                  <div>
                    <span class="deal-label">Taux</span>
                    <strong class="deal-value">{{ effectiveRateLabel(d) }}</strong>
                  </div>
                  <div>
                    <span class="deal-label">Funding</span>
                    <strong class="deal-value">{{ effectiveFundingLabel(d) }}</strong>
                  </div>
                  <div>
                    <span class="deal-label">Source</span>
                    <strong class="deal-value">{{ effectiveProviderLabel(d) }}</strong>
                  </div>
                </div>
                <details v-if="mtmResults[d.id]?.market_used" class="deal-technical-details">
                  <summary>Voir le détail du dernier calcul</summary>
                  <p>{{ marketUsedLabel(mtmResults[d.id].market_used) }}</p>
                </details>
                <div v-if="mtmResults[d.id]?.market_used?.data?.contractual_history?.warnings?.length"
                  class="deal-alert" role="note">
                  <span aria-hidden="true">⚠</span>
                  <span>La dernière clôture disponible est ancienne pour au moins un sous-jacent.</span>
                </div>
              </section>

              <section class="deal-panel deal-panel--result">
                <header class="deal-panel__head">
                  <span class="deal-panel__dot" aria-hidden="true"></span>
                  <h3 class="deal-panel__title">Résultat</h3>
                  <RouterLink :to="`/booking/${d.id}/valuations`"
                    class="deal-history-link" @click.stop>
                    Historique
                  </RouterLink>
                </header>
                <!-- Rien de calculé (ou calcul en cours) : l'action est au centre du
                     panneau plutôt qu'en bas d'un grand vide. -->
                <div v-if="!mtmResults[d.id]" class="deal-result-empty" role="status" aria-live="polite">
                  <template v-if="['actif', 'en_reglement'].includes(d.status)">
                    <strong>{{ mtmLoading[d.id] ? mtmProgressLabel(d.id) : 'Aucun MtM pour cette sélection' }}</strong>
                    <span>
                      {{ mtmLoading[d.id] ? 'Valorisation avec' : 'Le calcul utilisera' }}
                      {{ mtmModeFor(d.id) === 'realized' ? 'le marché actuel' : 'les paramètres du booking' }}
                      au {{ formatDate(mtmDateFor(d.id)) }}.
                    </span>
                    <span v-if="mtmLoading[d.id] && mtmModeFor(d.id) === 'realized'">
                      Les données en cache sont réutilisées si valides ; les données manquantes sont chargées avant le calcul.
                    </span>
                    <span v-else-if="!mtmLoading[d.id]">Seuls les calculs du jour sont réaffichés. Les précédents restent dans l’historique.</span>
                    <button class="btn-primary text-xs px-3 py-1.5 mt-1"
                      :disabled="mtmLoading[d.id]" @click.stop="runMtm(d.id)"
                      :title="mtmButtonTitle(d)">
                      <span v-if="mtmLoading[d.id]"
                        class="w-3 h-3 border-2 border-slate-200 border-t-transparent rounded-full animate-spin inline-block mr-1"></span>
                      Calculer le MTM
                    </button>
                  </template>
                  <template v-else>
                    <strong>Pas de MTM à calculer</strong>
                    <span>Le produit n’est plus en vie.</span>
                  </template>
                </div>
                <template v-else>
                  <div v-if="mtmResults[d.id].error" class="deal-alert" role="alert">
                    <span aria-hidden="true">⚠</span><span>{{ mtmResults[d.id].error }}</span>
                  </div>
                  <div v-else-if="mtmResults[d.id].resolved_pending" class="deal-alert" role="note">
                    <span aria-hidden="true">⚠</span><span>{{ mtmResults[d.id].message }}</span>
                  </div>
                  <template v-else>
                    <div>
                      <span class="deal-label">MtM</span>
                      <div class="deal-mtm__value">{{ (mtmResults[d.id].mtm * 100).toFixed(2) }}%</div>
                      <div class="deal-mtm__ci">
                        IC 95% · {{ (mtmResults[d.id].ic95[0] * 100).toFixed(2) }}% à {{ (mtmResults[d.id].ic95[1] * 100).toFixed(2) }}%
                      </div>
                      <div class="deal-mtm__ci">
                        Valorisation au {{ formatDate(mtmResultDate(d.id)) }}
                        <span v-if="mtmResults[d.id]._runCreatedAt">
                          · {{ mtmResults[d.id]._restored ? 'calcul du jour restauré, enregistré le' : 'calcul effectué le' }} {{ new Date(mtmResults[d.id]._runCreatedAt).toLocaleString('fr-FR') }}
                        </span>
                      </div>
                    </div>
                    <div class="deal-result-grid">
                      <div>
                        <span class="deal-label">Écart vs traité</span>
                        <strong class="deal-value" :class="signToneClass(mtmResults[d.id].mtm * 100 - d.price_traded)">
                          {{ signedNumber(mtmResults[d.id].mtm * 100 - d.price_traded, 2) }} pts
                        </strong>
                      </div>
                      <div>
                        <span class="deal-label">Vie restante</span>
                        <strong class="deal-value">{{ mtmResults[d.id].T_remaining.toFixed(2) }} an(s)</strong>
                      </div>
                      <div v-if="mtmResults[d.id].pre_strike">
                        <span class="deal-label">État</span>
                        <strong class="deal-value tone-info">Avant strike</strong>
                      </div>
                      <div v-else>
                        <span class="deal-label">Observations passées</span>
                        <strong class="deal-value">{{ mtmResults[d.id].obs_passees }}</strong>
                      </div>
                      <div v-if="mtmResults[d.id].wof_min_realized != null">
                        <span class="deal-label">Worst-of min réalisé</span>
                        <strong class="deal-value">{{ (mtmResults[d.id].wof_min_realized * 100).toFixed(1) }}%</strong>
                      </div>
                      <div v-if="mtmResults[d.id].unsettled_total">
                        <span class="deal-label">À régler</span>
                        <strong class="deal-value tone-warn">{{ (mtmResults[d.id].unsettled_total * 100).toFixed(2) }}%</strong>
                      </div>
                    </div>
                    <div v-if="mtmResults[d.id].best_case?.capped" class="deal-best-case">
                      Meilleur scénario : <strong>{{ (mtmResults[d.id].best_case.pv_max * 100).toFixed(2) }}%</strong>
                      <span v-if="mtmResults[d.id].best_case.exit_signal"> · sortie envisageable</span>
                    </div>
                  </template>
                  <div class="deal-result-actions">
                    <button v-if="['actif', 'en_reglement'].includes(d.status)" class="btn-primary text-xs px-3 py-1.5"
                      :disabled="mtmLoading[d.id]" @click.stop="runMtm(d.id)"
                      :title="mtmButtonTitle(d)">
                      <span v-if="mtmLoading[d.id]"
                        class="w-3 h-3 border-2 border-slate-200 border-t-transparent rounded-full animate-spin inline-block mr-1"></span>
                      Calculer le MTM
                    </button>
                    <RouterLink v-if="d.status === 'actif' && mtmResults[d.id]?.valuation_run_id"
                      class="btn-secondary text-[10px] px-2 py-1"
                      :to="{ path: '/valo-explain', query: { deal: d.id, run: mtmResults[d.id].valuation_run_id, auto: '1' } }"
                      @click.stop title="Ouvrir Valo Explain à partir de ce calcul enregistré">
                      📄 Note de valo
                    </RouterLink>
                    <button v-if="d.status === 'actif' && mtmResults[d.id]?.mtm != null"
                      class="btn-secondary text-[10px] px-2 py-1" :disabled="rollLoading[d.id]"
                      @click.stop="runRoll(d)" title="Reprice le même produit avec un nouveau départ forward">
                      🔄 Relancer un prix
                    </button>
                  </div>
                </template>
              </section>
            </div>

            <div v-if="refreshResults[d.id]" class="text-xs pt-2 border-t border-slate-800"
              :class="refreshResults[d.id].startsWith('⚠') ? 'text-amber-400' : 'text-slate-400'">
              {{ refreshResults[d.id] }}
            </div>

            <!-- ── Greeks (bump-and-reprice CRN) ─────────────────── -->
            <div v-if="greeksFor(d)" class="text-xs pt-2 border-t border-slate-800">
              <div v-if="greeksFor(d).error" class="text-amber-400">⚠ {{ greeksFor(d).error }}</div>
              <div v-else-if="greeksFor(d).resolved_pending" class="text-amber-400">
                ⚠ {{ greeksFor(d).message }}
              </div>
              <div v-else class="flex flex-col gap-1">
                <div class="flex flex-wrap items-center gap-x-4 gap-y-1">
                  <span class="text-slate-500">Δ Greeks :
                    <HelpTip text="Bump-and-reprice CRN (common random numbers) — dérivées brutes du prix (% du nominal résiduel) par rapport à leur variable de bump : δ/γ pour 100% de variation du spot, ν et ρ pour 100 points (de vol / de taux) de variation — pas pour 1 point. L'agrégat par portefeuille reconvertit ρ en EUR par 1 point de taux (÷100) ; ici ce sont les valeurs brutes. Cliquez Recalculer pour rafraîchir." />
                  </span>
                  <span v-for="(g, name) in greeksFor(d).per_underlying" :key="name" class="font-mono">
                    <span class="text-slate-500">{{ name }}</span>
                    <span class="ml-1"
                      :class="greeksFor(d).pre_strike ? 'text-sky-300' : 'text-slate-300'">
                      δ {{ g.delta?.toFixed(3) }}<span v-if="greeksFor(d).pre_strike" class="text-[10px]"> {{ greeksFor(d).pre_strike.modele_porte_le_smile ? 'smile' : 'nul' }}</span>
                    </span>
                    <span v-if="g.gamma != null" class="text-slate-400 ml-1">γ {{ g.gamma?.toFixed(3) }}</span>
                    <span v-if="g.vega != null" class="text-slate-400 ml-1">ν {{ g.vega?.toFixed(3) }}</span>
                  </span>
                  <span v-if="greeksFor(d).scalar?.theta != null" class="font-mono text-slate-400">
                    θ {{ greeksFor(d).scalar.theta.toFixed(4) }}
                  </span>
                  <span v-else-if="greeksFor(d).theta_event?.reason" class="font-mono text-slate-500">
                    θ n/d
                    <HelpTip text="Theta non calculé : vieillir ce produit d'une semaine demanderait une transition d'état qui ne peut pas être reconstruite exactement — observation contractuelle, fixing ou volatilité réalisée dans la fenêtre. Mémoire, accumulation, terminaison et nouveaux fixings doivent d'abord être constatés. Un theta absent vaut mieux qu'un theta faux." />
                  </span>
                  <span v-if="greeksFor(d).scalar?.rho != null" class="font-mono text-slate-400">
                    ρ {{ greeksFor(d).scalar.rho.toFixed(4) }}
                  </span>
                </div>
                <div v-if="greeksFor(d).pre_strike"
                  class="flex items-start gap-1.5 text-xs text-sky-300/80">
                  <span class="shrink-0">↳</span>
                  <span>{{ greeksFor(d).pre_strike.message }}</span>
                </div>
                <div v-if="greeksFor(d).theta_event?.pv_pts != null"
                  class="flex flex-wrap items-center gap-x-2 text-xs text-amber-300/80">
                  <span>Observation dans les 7 jours :
                    {{ greeksFor(d).theta_event.labels?.join(', ') || 'flux' }}
                    de {{ greeksFor(d).theta_event.pv_pts.toFixed(2) }} pts</span>
                  <HelpTip text="Un flux se détache pendant la semaine que mesure le theta. Il est reporté ici plutôt que compté comme de la décroissance temporelle : un coupon de 5% détaché en 7 jours donnerait un theta de -0,7 par jour, exact au niveau du deal mais ininterprétable une fois sommé sur le livre. Le θ affiché ne mesure que la décroissance, hors ce flux." />
                  <span v-if="greeksFor(d).theta_event.terminates" class="text-slate-500">
                    (observation de rappel — le produit peut s'arrêter là)
                  </span>
                </div>
                <div v-if="greeksFor(d).corr_pairs && Object.keys(greeksFor(d).corr_pairs).length"
                  class="flex flex-wrap items-center gap-x-4 gap-y-1">
                  <span class="text-slate-500">Risque de corrélation :
                    <HelpTip text="Sensibilité du prix à une hausse de 5pts de la corrélation entre chaque paire de sous-jacents (bump-and-reprice, même convention CRN que les autres Greeks) — calculée automatiquement dès qu'un deal a ≥2 sous-jacents, c'est le risque le moins intuitif d'un worst-of : une baisse de corrélation en crise peut coûter cher même si chaque sous-jacent pris seul se comporte bien." />
                  </span>
                  <span v-for="(v, pair) in greeksFor(d).corr_pairs" :key="pair" class="font-mono">
                    <span class="text-slate-500">{{ pair }}</span>
                    <span class="ml-1" :class="v >= 0 ? 'text-emerald-400' : 'text-red-400'">{{ v?.toFixed(3) }}</span>
                  </span>
                </div>
                <span class="text-slate-600 font-mono text-[10px]">
                  calculé le {{ new Date(greeksFor(d).computed_at).toLocaleString('fr-FR') }}
                </span>
              </div>
            </div>

            <!-- ── Choc de marché (full reprice) ─────────────────── -->
            <div v-if="shockPanelOpen[d.id]" class="text-xs pt-2 border-t border-slate-800 flex flex-col gap-2">
              <div class="flex items-center gap-2">
                <span class="text-slate-500">⚡ Choc :</span>
                <select class="select text-[10px] py-0.5" @click.stop @change="applyShockPreset(d.id, $event.target.value)">
                  <option value="">Preset…</option>
                  <option v-for="p in shockPresets" :key="p.label" :value="p.label">{{ p.label }}</option>
                </select>
                <HelpTip text="Full reprice sous le scénario (pas une approximation par les Greeks) — un preset préremplit les champs, tout reste modifiable ensuite. Historique conservé (voir ci-dessous)." />
              </div>
              <div class="flex flex-wrap gap-2" @click.stop>
                <label class="flex flex-col gap-0.5 text-[10px] text-slate-500">Spot %
                  <input v-model.number="shockForm[d.id].spot_shock_pct" type="number" step="1" class="input text-xs py-1 w-20" />
                </label>
                <label class="flex flex-col gap-0.5 text-[10px] text-slate-500">Vol (pts)
                  <input v-model.number="shockForm[d.id].vol_shock_pts" type="number" step="1" class="input text-xs py-1 w-20" />
                </label>
                <label class="flex flex-col gap-0.5 text-[10px] text-slate-500">Taux (bp)
                  <input v-model.number="shockForm[d.id].rate_shock_bp" type="number" step="10" class="input text-xs py-1 w-20" />
                </label>
                <label class="flex flex-col gap-0.5 text-[10px] text-slate-500">Corr (pts)
                  <input v-model.number="shockForm[d.id].corr_shock_pts" type="number" step="5" class="input text-xs py-1 w-20" />
                </label>
                <button class="btn-primary text-xs px-3 py-1.5 self-end" :disabled="shockLoading[d.id]"
                  @click="runDealShock(d.id)">
                  <span v-if="shockLoading[d.id]"
                    class="w-3 h-3 border-2 border-white border-t-transparent rounded-full animate-spin inline-block mr-1"></span>
                  Lancer le choc
                </button>
              </div>

              <div v-if="shockResults[d.id]">
                <div v-if="shockResults[d.id].error" class="text-amber-400">⚠ {{ shockResults[d.id].error }}</div>
                <div v-else-if="shockResults[d.id].skipped" class="text-amber-400">
                  ⚠ {{ shockResults[d.id].reason }}
                </div>
                <div v-else class="flex flex-wrap items-center gap-x-4 gap-y-1">
                  <span>ΔMtM :
                    <span class="font-mono font-bold" :class="shockResults[d.id].delta_pts >= 0 ? 'text-emerald-400' : 'text-red-400'">
                      {{ (shockResults[d.id].delta_pts * 100).toFixed(2) }}pts
                    </span>
                    <span class="font-mono text-slate-400 ml-1">({{ formatNominal(shockResults[d.id].delta_pts * d.nominal) }} {{ d.devise }})</span>
                  </span>
                  <span class="text-slate-500">{{ shockResults[d.id].label }}</span>
                  <span v-if="shockResults[d.id].spot_shock_scope === 'sans_effet'" class="text-sky-400">
                    choc de spot sans effet
                    <HelpTip text="Le strike n'est pas encore constaté : il est simulé sur chaque trajectoire, donc un spot qui décroche l'emmène avec lui et le produit reste identique en pourcentage de son propre strike. Le seul canal réel serait le déplacement du skew, que le modèle booké (invariant d'échelle) ne porte pas. Les chocs de vol, de taux et de corrélation restent, eux, pleinement valides." />
                  </span>
                  <span v-else-if="shockResults[d.id].spot_shock_scope === 'smile'" class="text-sky-400">
                    choc de spot = smile
                    <HelpTip text="Le strike n'est pas encore constaté : le choc de spot ne met pas le produit hors de la monnaie, il déplace le skew qui s'appliquera au produit une fois le strike fixé. C'est bien un impact réel, mais d'une autre nature qu'un décrochage." />
                  </span>
                </div>
              </div>

              <div v-if="shockHistory[d.id]?.length" class="text-[10px] text-slate-600">
                <div class="font-semibold text-slate-500 mb-1">Historique</div>
                <div v-for="h in shockHistory[d.id]" :key="h.id" class="flex gap-2">
                  <span>{{ new Date(h.created_at).toLocaleString('fr-FR') }}</span>
                  <span class="text-slate-400">{{ h.label }}</span>
                  <span v-if="!h.result.skipped" class="font-mono" :class="h.result.delta_pts >= 0 ? 'text-emerald-500' : 'text-red-500'">
                    {{ (h.result.delta_pts * 100).toFixed(2) }}pts
                  </span>
                </div>
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
                  nouvelle value date <span class="font-mono text-slate-300">{{ formatDate(rollResults[d.id].value_date) }}</span>
                </span>
                <span class="text-slate-500">
                  nouvelle échéance <span class="font-mono text-slate-300">{{ formatDate(rollResults[d.id].maturity_date) }}</span>
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
                    <span>{{ formatDate(d.value_date) }}</span>
                    <span v-if="lifePct(d) !== null" class="text-slate-400">
                      {{ formatPercent(lifePct(d), 0) }} écoulé
                    </span>
                    <span>{{ formatDate(d.maturity_date) }}</span>
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
                    <!-- Liseré blanc : un point bleu reste lisible sur le remplissage bleu. -->
                    <div v-for="ev in obsEvents(d.id)" :key="ev.id"
                      class="absolute top-1/2 -translate-y-1/2 -translate-x-1/2 w-2.5 h-2.5 rounded-full border ring-2 ring-white"
                      :class="eventDotClass(ev)"
                      :style="{ left: eventPct(d, ev) + '%' }"
                      :title="`${displayEventLabel(ev.label)} — ${ev.event_date} (${ev.status})`"></div>
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

                <!-- Constatations (lecture seule) -->
                <div>
                  <div class="flex items-center justify-between gap-3 mb-1.5">
                    <div class="text-[10px] font-semibold text-slate-500 uppercase tracking-wider">
                      Constatations ({{ compterConstatations(details[d.id].events) }})<template
                        v-if="compterReleves(details[d.id].events)"> · {{ compterReleves(details[d.id].events) }} relevé(s)</template>
                    </div>
                    <button v-if="autoExceptionEvents(d.id).length"
                      class="btn-secondary text-[10px] px-2 py-1 text-red-300 border-red-800/60"
                      @click="openAutoException(d, autoExceptionEvents(d.id)[0])">
                      Traiter {{ autoExceptionEvents(d.id).length }} exception(s)
                    </button>
                  </div>
                  <div v-if="autoExceptionEvents(d.id).length"
                    class="mb-2 rounded-lg border border-red-800/50 bg-red-950/25 px-3 py-2 text-xs text-red-300 flex items-center justify-between gap-3">
                    <span>
                      <strong>{{ autoExceptionEvents(d.id).length }} constatation(s) bloquent le lifecycle.</strong>
                      L’utilisateur du deal doit choisir la valeur retenue et motiver sa décision.
                    </span>
                    <button class="btn-secondary text-[10px] px-2 py-1 shrink-0"
                      @click="openAutoException(d, autoExceptionEvents(d.id)[0])">
                      Traiter maintenant
                    </button>
                  </div>
                  <div class="overflow-x-auto table-shell" tabindex="0" role="region">
                    <table class="w-full text-xs border-collapse">
                      <thead>
                        <tr class="border-b border-slate-700 text-left text-slate-500">
                          <th class="pb-1.5 pr-3 font-medium">#</th>
                          <th class="pb-1.5 pr-3 font-medium whitespace-nowrap">Label</th>
                          <th class="pb-1.5 pr-3 font-medium whitespace-nowrap">Date</th>
                          <th v-for="u in details[d.id].underlyings" :key="u.name"
                            class="pb-1.5 pr-3 font-medium whitespace-nowrap">{{ u.ticker || u.name }}</th>
                          <th class="pb-1.5 pr-3 font-medium whitespace-nowrap">Fixing</th>
                          <th class="pb-1.5 pr-3 font-medium">Statut</th>
                          <th class="pb-1.5 font-medium">Action</th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr v-for="ev in ordonnerEvenements(details[d.id].events)" :key="ev.id"
                          class="border-b border-slate-800/50"
                          :class="ev.status === 'annulé' ? 'opacity-40' : ev.status === 'futur' ? 'opacity-60' : ''">
                          <!-- Un relevé alimente la constatation au-dessus de lui : ni
                               numéroté, ni au même niveau (utils/dealEvents.js). -->
                          <td class="py-1.5 pr-3 text-slate-500">{{ rangConstatation(details[d.id].events, ev) ?? '' }}</td>
                          <td class="py-1.5 pr-3 whitespace-nowrap"
                            :class="estReleve(ev) ? 'text-slate-500 pl-6 text-[11px]' : 'text-slate-300'">
                            <span v-if="estReleve(ev)" class="text-slate-700 mr-1">↳</span>{{ displayEventLabel(ev.label) }}
                            <span v-if="ev.reduction"
                              class="ml-1.5 text-[9px] rounded px-1 py-0.5 border border-blue-800/60 text-blue-400"
                              :title="`Niveau constaté : ${libelleReduction(ev.reduction)} des cours de ses relevés, sous-jacent par sous-jacent.`">{{ ev.reduction }}</span>
                          </td>
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
                          <td class="py-1.5 pr-3">
                            <span :class="fixingStatusClass(ev.fixing_status)"
                              class="px-1.5 py-0.5 rounded text-[10px] font-medium whitespace-nowrap">
                              {{ fixingStatusLabel(ev.fixing_status) }}
                            </span>
                          </td>
                          <td class="py-1.5 pr-3">
                            <span :class="operationalEventClass(ev)"
                              class="px-1.5 py-0.5 rounded text-[10px] font-medium whitespace-nowrap">
                              {{ operationalEventLabel(ev) }}
                            </span>
                          </td>
                          <td class="py-1.5">
                            <button v-if="canResolveAutoException(d, ev)"
                              class="btn-secondary text-[10px] px-2 py-1 whitespace-nowrap"
                              @click="openAutoException(d, ev)">
                              Traiter
                            </button>
                            <span v-else class="text-slate-700">—</span>
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
                    <input type="date" class="input text-xs py-1 w-auto"
                      :value="explainD1[d.id] || defaultExplainStart(d)"
                      :max="explainD2[d.id] || todayIso"
                      @change="explainD1[d.id] = $event.target.value" />
                    <label class="text-slate-500">au</label>
                    <input type="date" class="input text-xs py-1 w-auto"
                      :value="explainD2[d.id] || todayIso"
                      :min="explainD1[d.id] || defaultExplainStart(d)" :max="todayIso"
                      @change="explainD2[d.id] = $event.target.value" />
                    <button class="btn-secondary text-xs px-3 py-1.5"
                      :disabled="explainLoading[d.id] || !explainDatesValid(d)"
                      @click="runExplain(d)">
                      <span v-if="explainLoading[d.id]"
                        class="w-3 h-3 border-2 border-slate-400 border-t-transparent rounded-full animate-spin inline-block mr-1"></span>
                      ⚖ Expliquer
                    </button>
                  </div>
                  <div v-if="!explainDatesValid(d)" class="text-[10px] text-red-500 mt-1">
                    La date de début doit être antérieure ou égale à la date de fin.
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

          </template><!-- /deals tab -->



        </template>
      </div>
    </main>

    <AutoFixingExceptionModal
      v-model="autoExceptionModal.open"
      :deal="autoExceptionModal.deal"
      :event="autoExceptionModal.event"
      @resolved="onAutoExceptionResolved" />
  </div>
</template>

<script setup>
import ActionMenu from '../components/ui/ActionMenu.vue'
import BackLink from '../components/ui/BackLink.vue'
import { ref, reactive, computed, onMounted, onUnmounted, nextTick, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { useDealsStore } from '../stores/deals.js'
import { usePortfoliosStore, shockPresets, blankShockForm } from '../stores/portfolios.js'
import { useAuthStore } from '../stores/auth.js'
import { apiFetch } from '../utils/api.js'
import HelpTip from '../components/HelpTip.vue'
import LoadingSpinner from '../components/ui/LoadingSpinner.vue'
import EmptyState from '../components/ui/EmptyState.vue'
import DataFilterBar from '../components/ui/DataFilterBar.vue'
import AutoFixingExceptionModal from '../components/AutoFixingExceptionModal.vue'
import { useBookingMtm } from '../composables/useBookingMtm.js'
import { useDataFilter } from '../composables/useDataFilter.js'
import { formatInt, formatPercent, formatDate } from '../utils/format.js'
import { barrierChipClass, barrierGapLabel, barrierGauges } from '../utils/barriers.js'
import { productTypeLabel } from '../data/payscriptTemplates.js'
import {
  compterConstatations, compterReleves, estReleve, libelleReduction, ordonnerEvenements,
  rangConstatation,
} from '../utils/dealEvents.js'

const route = useRoute()
const dealsStore = useDealsStore()
const portfoliosStore = usePortfoliosStore()
const authStore = useAuthStore()

// Portfolio list & deal→portfolio assignment live in the shared store (the
// Risk Management module is the primary owner) — Booking only reads the list
// for its filter/assignment dropdowns.
const portfolios = computed(() => portfoliosStore.portfolios)
const shockHistory = portfoliosStore.shockHistory
const portfolioAssigning = reactive({})
const portfolioAssignmentStatus = reactive({})

function dealHasPortfolio(deal, portfolioId) {
  return (deal.portfolio_ids || []).includes(portfolioId)
}

function dealPortfolioLabel(deal) {
  const ids = deal.portfolio_ids || []
  if (!ids.length) return 'Non classé'
  if (ids.length === 1) return portfolios.value.find(p => p.id === ids[0])?.name || '1 portefeuille'
  return `${ids.length} portefeuilles`
}

async function toggleDealPortfolio(deal, portfolioId, checked) {
  if (portfolioAssigning[deal.id]) return
  const target = portfolios.value.find(p => p.id === portfolioId)
  const currentIds = deal.portfolio_ids || []
  const nextIds = checked
    ? [...new Set([...currentIds, portfolioId])]
    : currentIds.filter(id => id !== portfolioId)
  portfolioAssigning[deal.id] = true
  portfolioAssignmentStatus[deal.id] = ''
  try {
    await portfoliosStore.setDealPortfolios(deal.id, nextIds)
    portfolioAssignmentStatus[deal.id] = checked
      ? `✓ Ajouté à ${target?.name || 'portefeuille'}`
      : `✓ Retiré de ${target?.name || 'portefeuille'}`
  } catch (e) {
    portfolioAssignmentStatus[deal.id] = `⚠ ${e.message}`
  } finally {
    portfolioAssigning[deal.id] = false
  }
}

function canAssignPortfolio(deal) {
  return authStore.isAdmin || deal.user_id === authStore.user?.id
}

function portfoliosForDeal(deal) {
  return portfolios.value.filter(p => p.user_id === deal.user_id)
}

const activeTab = ref('watchlist')

const refreshingId = ref(null)
const refreshResults = reactive({})
const copiedReference = ref('')
let copyReferenceTimer = null

async function copyDealReference(reference) {
  try {
    await navigator.clipboard.writeText(reference)
  } catch {
    const textarea = document.createElement('textarea')
    textarea.value = reference
    textarea.setAttribute('readonly', '')
    textarea.style.position = 'fixed'
    textarea.style.opacity = '0'
    document.body.appendChild(textarea)
    textarea.select()
    document.execCommand('copy')
    document.body.removeChild(textarea)
  }
  copiedReference.value = reference
  clearTimeout(copyReferenceTimer)
  copyReferenceTimer = setTimeout(() => {
    copiedReference.value = ''
  }, 1800)
}

// ── Fiche détail dépliable (accordéon multi-ouvert) ─────────────────
const expanded = reactive({})
const details = reactive({})   // deal_id → full deal (with events)
const autoExceptionModal = reactive({ open: false, deal: null, event: null })

const autoExceptionStatuses = new Set([
  'RECEIVED', 'PARTIAL', 'MISSING', 'REJECTED', 'CONTESTED', 'MANUAL_REVIEW_REQUIRED',
])

function canResolveAutoException(deal, event) {
  return deal?.fixing_policy === 'AUTO_YAHOO' &&
    event?.event_date <= todayIso.value && autoExceptionStatuses.has(event?.fixing_status)
}

function autoExceptionEvents(dealId) {
  const fullDeal = details[dealId]
  return (fullDeal?.events || []).filter(event =>
    canResolveAutoException(fullDeal, event))
}

function openAutoException(deal, event) {
  autoExceptionModal.deal = details[deal.id] || deal
  autoExceptionModal.event = event
  autoExceptionModal.open = true
}

async function onAutoExceptionResolved(result) {
  const dealId = autoExceptionModal.deal?.id
  if (!dealId) return
  refreshResults[dealId] = `✓ ${result.message}`
  await loadDetail(dealId)
  await dealsStore.loadDeals()
  loadAlerts()
  loadWatchlist()
  const remaining = autoExceptionEvents(dealId)
  if (remaining.length) {
    autoExceptionModal.deal = details[dealId]
    autoExceptionModal.event = remaining[0]
  } else {
    autoExceptionModal.open = false
    autoExceptionModal.deal = null
    autoExceptionModal.event = null
  }
}

async function toggleDetail(id) {
  const opening = !expanded[id]
  expanded[id] = opening
  if (!opening) return
  if (!details[id]) await loadDetail(id)
  await loadSavedMtm(id)
  await focusDealCard(id)
}

async function focusDealCard(id) {
  await nextTick()
  await new Promise(resolve => window.requestAnimationFrame(resolve))
  const card = document.getElementById(`deal-${id}`)
  if (!card) return
  const scrollContainer = card.closest('main')
  const availableHeight = (scrollContainer?.clientHeight || window.innerHeight) - 48
  card.scrollIntoView({
    behavior: 'smooth',
    block: card.offsetHeight <= availableHeight ? 'center' : 'start',
  })
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
  // Les relevés ne sont pas des constatations : pas de point sur la frise.
  return (details[id]?.events || []).filter(e => e.t_years > 0 && !estReleve(e))
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

function fixingStatusLabel(status) {
  const labels = {
    EXPECTED: 'Attendu',
    RECEIVED: 'Reçu — exception source',
    VALIDATED: 'Officiel',
    APPLIED: 'Appliqué',
    PARTIAL: 'Incomplet',
    MISSING: 'Manquant',
    REJECTED: 'Rejeté',
    CONTESTED: 'Contesté',
    MANUAL_REVIEW_REQUIRED: 'Exception source',
  }
  return labels[status] || status || 'Inconnu'
}

function fixingStatusClass(status) {
  if (['VALIDATED', 'APPLIED'].includes(status)) return 'bg-emerald-900/40 text-emerald-400'
  if (status === 'RECEIVED') return 'bg-amber-900/40 text-amber-400'
  if (['PARTIAL', 'MISSING', 'REJECTED', 'CONTESTED', 'MANUAL_REVIEW_REQUIRED'].includes(status)) {
    return 'bg-red-900/40 text-red-400'
  }
  return 'bg-slate-800 text-slate-500'
}

function operationalEventLabel(ev) {
  if (ev.event_date > todayIso.value) return 'À venir'
  if (ev.fixing_status === 'EXPECTED') return 'À récupérer'
  if (ev.fixing_status === 'RECEIVED') return 'Exception à traiter'
  if (['PARTIAL', 'MISSING', 'REJECTED', 'CONTESTED', 'MANUAL_REVIEW_REQUIRED'].includes(ev.fixing_status)) {
    return 'Exception à traiter'
  }
  return ev.status === 'futur' ? 'Fixing à appliquer' : ev.status
}

function operationalEventClass(ev) {
  if (['PARTIAL', 'MISSING', 'REJECTED', 'CONTESTED', 'MANUAL_REVIEW_REQUIRED'].includes(ev.fixing_status)) {
    return 'bg-red-900/40 text-red-400'
  }
  if (ev.fixing_status === 'RECEIVED') return 'bg-amber-900/40 text-amber-400'
  return eventStatusClass(ev.status)
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

function termBusinessLabel(name = '') {
  const normalized = String(name).toUpperCase()
  // Before the coupon itself: M_CPN_BAR 70 % and COUPON 2 % both read
  // "Coupon" otherwise, side by side on a Phoenix.
  if (/(COUP|CPN).*BAR/.test(normalized)) return 'Barrière de coupon'
  if (/COUP|CPN/.test(normalized)) return 'Coupon'
  if (/AC.*BAR|AUTOCALL/.test(normalized)) return 'Barrière de rappel'
  if (/KI.*BAR|PROTECT/.test(normalized)) return 'Barrière de protection'
  if (/PARTIC/.test(normalized)) return 'Participation'
  if (/CAP/.test(normalized)) return 'Plafond'
  if (/FLOOR/.test(normalized)) return 'Plancher'
  if (/STRIKE/.test(normalized)) return 'Strike'
  return String(name).replace(/^M_/, '').replaceAll('_', ' ').toLowerCase()
    .replace(/^./, char => char.toUpperCase())
}

function primaryTerms(terms = []) {
  const important = /COUP|CPN|AC.*BAR|AUTOCALL|KI.*BAR|PROTECT|PARTIC|CAP|FLOOR|STRIKE/i
  const ranked = [...terms].sort((a, b) => Number(important.test(b.name)) - Number(important.test(a.name)))
  return ranked.slice(0, 4)
}

function barrierBusinessLabel(barrier) {
  // The name first for a coupon barrier: WOF >= M_CPN_BAR is an upward
  // monitor, the same kind as the recall — read by kind alone, a Phoenix
  // showed two "Barrière de rappel".
  if (/COUP|CPN/i.test(barrier?.name || '')) return 'Barrière de coupon'
  if (barrier?.kind === 'autocall') return 'Barrière de rappel'
  if (barrier?.kind === 'ki') return 'Barrière de protection'
  return termBusinessLabel(barrier?.name || 'Barrière')
}

// Colour of a signed figure. A class the panel stylesheet owns: a Tailwind
// text-red-400 lost to the scoped `color` of its own element, and a negative
// margin was printed in black.
function signToneClass(value) {
  return Number(value) >= 0 ? 'tone-pos' : 'tone-neg'
}

function formatGaugeLevel(value) {
  return `${+Number(value).toFixed(1)}%`
}

// Which level the ruler reads — see build_watchlist_row:_observable_value.
function gaugeObservableLabel(deal, observable) {
  const rows = wlRow(deal.id)?.underlyings || []
  const tickerOf = (u) => u?.ticker || u?.name || ''
  const single = rows.length === 1 ? tickerOf(rows[0]) : ''
  const priced = rows.filter(u => u.perf != null)
  const extreme = (pick) => priced.length
    ? tickerOf(priced.reduce((a, b) => (pick(b.perf, a.perf) ? b : a)))
    : ''

  if (observable === 'WOF') {
    const worst = extreme((x, y) => x < y)
    return single || (worst ? `Worst-of · ${worst}` : 'Worst-of')
  }
  if (observable === 'BOF') {
    const best = extreme((x, y) => x > y)
    return single || (best ? `Best-of · ${best}` : 'Best-of')
  }
  if (observable === 'WOF_MIN') return `${single || 'Worst-of'} · plus bas depuis le strike`
  if (observable === 'BOF_MAX') return `${single || 'Best-of'} · plus haut depuis le strike`
  if (observable === 'BASKET') return 'Panier'
  const indexed = /^S(?:_MIN|_MAX)?\[(\d+)\]$/.exec(observable || '')
  if (indexed) return tickerOf(rows[Number(indexed[1]) - 1]) || observable
  return observable
}

function gaugeAriaLabel(deal, gauge) {
  const marks = gauge.marks.map(m => `${barrierBusinessLabel(m)} ${formatGaugeLevel(m.level)}`)
  return `${gaugeObservableLabel(deal, gauge.observable)} à ${formatGaugeLevel(gauge.current)} du strike — ${marks.join(', ')}`
}

function mtmButtonTitle(deal) {
  return deal.status === 'en_reglement'
    ? 'Valeur actualisée du remboursement connu jusqu’à sa date de paiement'
    : 'Valorise les flux restants du produit vivant à la date du calcul'
}

function displayEventLabel(label = '') {
  return String(label)
    .replace(/Strike\s*\/\s*Fixing\s*S[₀0]/gi, 'Fixing du strike')
    .replace(/\bS[₀0]\b/g, 'Strike')
}

function signedNumber(value, decimals = 2) {
  const number = Number(value)
  if (!Number.isFinite(number)) return '–'
  return `${number >= 0 ? '+' : ''}${number.toFixed(decimals)}`
}

function signedPercent(value, decimals = 1) {
  const formatted = signedNumber(value, decimals)
  return formatted === '–' ? formatted : `${formatted}%`
}

// Watchlist join — live spot/perf and barrier gaps for active deals
function wlRow(id) {
  return watchlist.value.find(w => w.deal_id === id) || null
}

function wlUnderlying(id, name) {
  return wlRow(id)?.underlyings?.find(u => u.name === name) || null
}

function strikeFor(id, name) {
  return s0For(id, name) ?? wlUnderlying(id, name)?.s0 ?? null
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
const {
  todayIso, mtmLoading, mtmResults, mtmModeFor, mtmDateFor, setMtmMode, setMtmDate,
  loadSavedMtms, loadSavedMtm, runMtm, mtmProgressLabel, syncDay,
} = useBookingMtm()
let dayTimer
function refreshDay() {
  syncDay()
  clearTimeout(dayTimer)
  const now = new Date()
  const midnight = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1)
  dayTimer = setTimeout(refreshDay, midnight - now + 50)
}

function mtmMinDate(deal) {
  if (deal.status === 'en_reglement') return deal.maturity_date || deal.trade_date || undefined
  return deal.trade_date || undefined
}

function mtmResultDate(id) {
  const result = mtmResults[id]
  return result?.valuation_date
    || result?.market_used?.data?.contractual_history?.requested_end
    || mtmDateFor(id)
}

function modelBusinessLabel(model) {
  const labels = {
    constant: 'GBM',
    gbm: 'GBM',
    heston: 'Heston',
    sabr: 'SABR',
    local_vol: 'Vol locale',
    lsv: 'LSV',
  }
  return labels[String(model || '').toLowerCase()] || model || 'Non renseigné'
}

function repricingModelLabel(deal) {
  if (mtmModeFor(deal.id) === 'realized') return 'GBM'
  return modelBusinessLabel(mtmResults[deal.id]?.market_used?.model || deal.market_snapshot?.model)
}

function effectiveRateLabel(deal) {
  const used = mtmResults[deal.id]?.market_used
  const rate = used?.r ?? deal.market_snapshot?.r
  if (rate == null) return 'Non renseigné'
  return `${Number(rate).toFixed(2)}%${used?.r_is_default ? ' (défaut)' : ''}`
}

function effectiveFundingLabel(deal) {
  const used = mtmResults[deal.id]?.market_used
  if (used?.funding_curve?.length) return `Courbe · ${used.funding_curve.length} piliers`
  if (used?.funding_spread != null) return `${Number(used.funding_spread).toFixed(2)}%`

  const market = deal.market_snapshot || {}
  if (market.funding_curve?.length) return `Courbe · ${market.funding_curve.length} piliers`
  if (market.funding?.mode === 'pillars' && market.funding.pillars?.length) {
    return `Courbe · ${market.funding.pillars.length} piliers`
  }
  if (market.funding?.level != null) return `${Number(market.funding.level).toFixed(2)}%`
  return `${(Number(market.funding_spread || 0) * 100).toFixed(2)}%`
}

function effectiveProviderLabel(deal) {
  const provider = mtmResults[deal.id]?.market_used?.data?.provider || deal.market_data_provider
  if (provider === 'YAHOO_FINANCE' || provider === 'YAHOO') return 'Yahoo Finance'
  return provider || 'Yahoo Finance'
}

// ── Greeks (bump-and-reprice CRN) ────────────────────────────────────
const greeksLoading = reactive({})
const greeksResults = reactive({})

// Falls back to the deal's persisted last computation (greeks/greeks_computed_at,
// set by a previous call to POST .../greeks) until a fresh one is fetched in
// this session — the button only refreshes it, the row isn't blank on load.
function greeksFor(d) {
  if (greeksResults[d.id]) return greeksResults[d.id]
  if (d.greeks_computed_at) return { ...d.greeks, computed_at: d.greeks_computed_at }
  return null
}

async function runGreeks(id) {
  greeksLoading[id] = true
  greeksResults[id] = null
  try {
    const mode = mtmModeFor(id)
    const res = await apiFetch(`/api/deals/${id}/greeks`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        recalibrate: mode === 'realized' ? 'realized' : 'none',
        valuation_date: mtmDateFor(id),
      }),
    })
    const data = await res.json()
    if (!res.ok) throw new Error(data.detail || 'Erreur Greeks')
    greeksResults[id] = data
  } catch (e) {
    greeksResults[id] = { error: e.message }
  } finally {
    greeksLoading[id] = false
  }
}

// ── Choc de marché (deal seul) ───────────────────────────────────────
// Presets, history and the shock runner live in the shared portfolios store
// (also used by Risk Management's Chocs tab) — only the per-deal panel UI
// state stays here.
const shockPanelOpen = reactive({})
const shockForm = reactive({})
const shockLoading = reactive({})
const shockResults = reactive({})

function applyShockPreset(id, label) {
  const preset = shockPresets.find(p => p.label === label)
  if (!preset) return
  shockForm[id] = { spot_shock_pct: preset.spot_shock_pct, vol_shock_pts: preset.vol_shock_pts,
                    rate_shock_bp: preset.rate_shock_bp, corr_shock_pts: preset.corr_shock_pts }
}

async function toggleShockPanel(id) {
  shockPanelOpen[id] = !shockPanelOpen[id]
  if (shockPanelOpen[id]) {
    if (!shockForm[id]) shockForm[id] = blankShockForm()
    await portfoliosStore.loadShockHistory('deal', id)
  }
}

async function runDealShock(id) {
  shockLoading[id] = true
  shockResults[id] = null
  try {
    shockResults[id] = await portfoliosStore.runShock('deal', id, shockForm[id])
  } catch (e) {
    shockResults[id] = { error: e.message }
  } finally {
    shockLoading[id] = false
  }
}

// P&L explain between two dates — waterfall temps/spot/vol/corr (see
// EXPLICATION_VALO_DESIGN.md). Date 1 defaults to booking, date 2 to today.
const explainD1 = reactive({})
const explainD2 = reactive({})
const explainLoading = reactive({})
const explainResults = reactive({})
function defaultExplainStart(d) {
  // Value date is the normal P&L origin. For a freshly-booked deal whose
  // settlement is still in the future, use the trade date (or strike as a
  // final fallback) so the screen never proposes a future-to-past period.
  return [d.value_date, d.trade_date, d.strike_date]
    .find(value => value && value <= todayIso.value) || todayIso.value
}

function explainDatesValid(d) {
  const date1 = explainD1[d.id] || defaultExplainStart(d)
  const date2 = explainD2[d.id] || todayIso.value
  return !!date1 && !!date2 && date1 <= date2 && date2 <= todayIso.value
}

async function runExplain(d) {
  explainLoading[d.id] = true
  explainResults[d.id] = null
  try {
    const res = await apiFetch(`/api/deals/${d.id}/mtm/explain`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        date1: explainD1[d.id] || defaultExplainStart(d),
        date2: explainD2[d.id] || todayIso.value,
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
        date1: explainD1[d.id] || defaultExplainStart(d),
        date2: explainD2[d.id] || todayIso.value,
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
  if (mu.source === 'known_settlement') {
    const provider = mu.data?.provider === 'YAHOO_FINANCE'
      ? 'Yahoo Finance' : (mu.data?.provider || '')
    return `flux connu · r ${mu.r}% · funding ${mu.funding_spread || 0}% · ${provider}`
  }
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
  const provider = mu.data?.provider === 'YAHOO_FINANCE'
    ? 'Yahoo Finance' : mu.data?.provider
  const effective = mu.data?.contractual_history?.asof_effective
  const data = provider ? ` · ${provider}${effective ? ` au ${effective}` : ''}` : ''
  return `${uls}${corr} · r ${mu.r}% · ${model} · ${src}${data}`
}

const watchlist = ref([])
const watchlistError = ref('')
const watchlistLoading = ref(false)

function queryId(value) {
  const parsed = Number(Array.isArray(value) ? value[0] : value)
  return Number.isInteger(parsed) && parsed > 0 ? parsed : null
}

const commercialClientId = computed(() => queryId(route.query.client_id))
const commercialMandateId = computed(() => queryId(route.query.mandate_id))
const commercialScope = computed(() => {
  const clientId = commercialClientId.value
  const mandateId = commercialMandateId.value
  if (!clientId && !mandateId) return { active: false, label: '' }

  const matchingDeal = dealsStore.deals.find(deal =>
    (!clientId || deal.client_id === clientId)
    && (!mandateId || deal.mandate_id === mandateId))
  const snapshot = matchingDeal?.client_attribution_current
    || matchingDeal?.client_provenance
    || {}
  const clientLabel = snapshot.client?.name || (clientId ? `Client #${clientId}` : null)
  const mandateLabel = snapshot.mandate?.name || (mandateId ? `Mandat #${mandateId}` : null)
  return {
    active: true,
    label: [clientLabel, mandateLabel].filter(Boolean).join(' · '),
  }
})

async function loadWatchlist() {
  watchlistError.value = ''
  watchlistLoading.value = true
  try {
    watchlist.value = await dealsStore.getWatchlist({
      clientId: commercialClientId.value,
      mandateId: commercialMandateId.value,
    })
  } catch (e) {
    watchlistError.value = e.message
  } finally {
    watchlistLoading.value = false
  }
}

watch(
  () => [route.query.client_id, route.query.mandate_id],
  () => loadWatchlist(),
)

// Default watchlist order = next observation soonest first (backend sorts by
// barrier urgency instead — kept for the daily alert scan, not for this view).
const watchlistByUrgency = computed(() =>
  [...watchlist.value].sort((a, b) =>
    (a.days_to_next ?? Infinity) - (b.days_to_next ?? Infinity)
  )
)

const UAT_BATCH_SUFFIX = /\s*\[\d{8}-\d{6}-[A-Z0-9]+\]\s*$/i

function watchlistProductName(row) {
  const rawName = String(row?.product_name || '')
    .replace(UAT_BATCH_SUFFIX, '')
    .trim()
  if (!rawName) return ''

  const productType = String(row?.product_type || '').trim().toLocaleLowerCase('fr-FR')
  return rawName
    .split(/\s+—\s+/)
    .map(part => part.trim())
    .filter(part => part && (!productType || part.toLocaleLowerCase('fr-FR') !== productType))
    .join(' — ')
}

// Mêmes filtres que l'onglet Deals, sur les axes que porte la watchlist —
// voir composables/useDataFilter.
const wlFilterFields = [
  { key: 'q', label: 'Recherche', kind: 'text', width: 'min-w-[180px]',
    placeholder: 'Référence, produit, contrepartie…',
    get: w => [w.reference, w.product_name, w.contrepartie] },
  { key: 'contrepartie', label: 'Contrepartie', kind: 'select' },
  { key: 'ticker', label: 'Sous-jacent', kind: 'select',
    get: w => (w.underlyings || []).map(u => u.ticker).filter(Boolean) },
  { key: 'product_type', label: 'Type', kind: 'select' },
]
const wlColumns = [
  { key: 'reference', label: 'Référence', heading: 'Réf',
    help: "Référence du deal. Cliquez sur la référence d’une ligne pour ouvrir sa fiche ; l’icône ⇥ ouvre le Pricer." },
  { key: 'contrepartie', label: 'Contrepartie',
    help: 'Entité juridique faisant face au deal. Le client commercial éventuel est porté séparément par le filtre de contexte.' },
  { key: 'underlyings', label: 'Sous-jacent',
    get: row => (row.underlyings || []).map(u => u.ticker || u.name).join(' / '),
    help: 'Tri alphabétique sur les sous-jacents tels qu’affichés. Pour un panier, la comparaison commence par le premier sous-jacent.' },
  { key: 'product_name', label: 'Produit', get: watchlistProductName,
    help: 'Tri alphabétique sur le libellé métier affiché. La famille du payoff figure dans Type et l’identifiant technique dans Réf.' },
  { key: 'product_type', label: 'Type', get: row => row.product_type ? productTypeLabel(row.product_type) : '',
    help: 'Tri alphabétique sur le type affiché : Autocall Athena, Phoenix Mémoire, Reverse Convertible…' },
  { key: 'days_to_next', label: 'Prochaine obs.', heading: 'Prochaine obs',
    help: 'Date de la prochaine observation et jours restants. Tri par défaut : de la plus proche à la plus lointaine ; sans observation en dernier.' },
  { key: 'wof', label: 'WOF',
    help: 'Tri numérique sur la performance actuelle du pire sous-jacent par rapport au strike. Le minimum historique entre parenthèses ne sert pas au tri.' },
  { key: 'min_gap', label: 'Barrière la plus proche', heading: 'Barrières',
    help: 'Tri sur la plus petite distance absolue à une barrière, en points du strike : croissant = plus proche d’abord. Les écarts non calculables restent en dernier. La couleur indique séparément le sens favorable ou défavorable.' },
]
const wlSorts = wlColumns
const wlFilter = useDataFilter(watchlistByUrgency, wlFilterFields, {
  sorts: wlSorts, defaultSort: 'days_to_next',
})

function sortWatchlistBy(key) {
  if (wlFilter.sortBy.value === key) wlFilter.toggleSortDir()
  else {
    wlFilter.sortBy.value = key
    wlFilter.sortDir.value = 'asc'
  }
}

function watchlistSortTitle(column) {
  const descending = wlFilter.sortBy.value === column.key && wlFilter.sortDir.value === 'asc'
  const numeric = ['days_to_next', 'wof', 'min_gap'].includes(column.key)
  const direction = numeric
    ? (descending ? 'décroissant' : 'croissant')
    : (descending ? 'alphabétique Z à A' : 'alphabétique A à Z')
  return `${column.label} : trier par ordre ${direction}`
}
const sortedWatchlist = computed(() => wlFilter.filtered.value)

// Reference click in the watchlist → jump to the deal's own card in the
// Deals tab (expanded + scrolled into view), as an alternative to opening it
// in the Pricer (the ⇥ icon next to it).
async function openDealDetail(id) {
  activeTab.value = 'deals'
  expanded[id] = true
  if (!details[id]) await loadDetail(id)
  await loadSavedMtm(id)
  await focusDealCard(id)
}

// barrierChipClass/barrierGapLabel now live in utils/barriers.js — shared
// with Risk Management's Barrières tab so the color/label convention can't
// diverge between the two.

const statusOptions = ['actif', 'en_reglement', 'callé', 'échu', 'résilié']

const sortBy  = ref('status')
const sortDir = ref('asc')
function toggleSortDir() { sortDir.value = sortDir.value === 'asc' ? 'desc' : 'asc' }

const _STATUS_ORDER = { actif: 0, en_reglement: 1, 'callé': 2, 'échu': 3 }

const filters = reactive({
  contrepartie: '',
  ticker: '',
  productType: '',
  status: '',
  portfolioId: '',
})

const hasActiveFilters = computed(() =>
  !!(filters.contrepartie || filters.ticker || filters.productType || filters.status || filters.portfolioId)
)

function resetFilters() {
  filters.contrepartie = ''
  filters.ticker = ''
  filters.productType = ''
  filters.status = ''
  filters.portfolioId = ''
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
  const list = dealsStore.deals.filter(d => {
    if (filters.status && d.status !== filters.status) return false
    if (filters.productType && d.product_type !== filters.productType) return false
    if (filters.contrepartie && !d.contrepartie.toLowerCase().includes(filters.contrepartie.toLowerCase())) return false
    if (filters.ticker && !(d.underlyings || []).some(u => u.ticker === filters.ticker)) return false
    if (filters.portfolioId && !(d.portfolio_ids || []).map(String).includes(filters.portfolioId)) return false
    return true
  })
  return [...list].sort((a, b) => {
    let cmp = 0
    if (sortBy.value === 'status') {
      cmp = (_STATUS_ORDER[a.status] ?? 9) - (_STATUS_ORDER[b.status] ?? 9)
      if (cmp === 0) cmp = a.maturity_date < b.maturity_date ? -1 : 1
    } else if (sortBy.value === 'maturity_date') {
      cmp = a.maturity_date < b.maturity_date ? -1 : 1
    } else {
      cmp = a.reference < b.reference ? -1 : 1
    }
    return sortDir.value === 'asc' ? cmp : -cmp
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
    actif: 'badge-positive',
    en_reglement: 'badge-gold',
    'callé': 'badge-gold',
    'échu': 'badge-muted',
    'résilié': 'badge-negative',
  }
  return map[s] || 'badge-muted'
}

function statusLabel(status) {
  return {
    actif: 'En cours',
    en_reglement: 'En règlement',
    'callé': 'Rappelé',
    'échu': 'Échu',
    'résilié': 'Résilié',
  }[status] || status || 'Statut inconnu'
}

const formatNominal = formatInt

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
    refreshResults[dealId] = res.policy === 'AUTO_YAHOO'
      ? res.message
      : describeOutcome(res.evaluation) || res.message
  } catch (e) {
    refreshResults[dealId] = `⚠ ${e.message}`
  } finally {
    refreshingId.value = null
    await dealsStore.loadDeals()
    loadWatchlist()   // a refresh can resolve a deal, dropping it off the watchlist
    if (expanded[dealId]) await loadDetail(dealId)   // open panel shows fresh events
  }
}

onMounted(async () => {
  refreshDay()
  window.addEventListener('focus', refreshDay)
  document.addEventListener('visibilitychange', refreshDay)
  await dealsStore.loadDeals()
  await loadSavedMtms(
    dealsStore.deals
      .filter(deal => ['actif', 'en_reglement'].includes(deal.status))
      .map(deal => deal.id),
  )
  loadWatchlist()
  loadAlerts()
  portfoliosStore.load()
  // Deep link from Risk Management ("/booking?deal=<id>") — open the deal's
  // detail card directly instead of landing on the watchlist.
  const dealId = Number(route.query.deal)
  if (dealId) openDealDetail(dealId)
})
onUnmounted(() => {
  clearTimeout(dayTimer)
  clearTimeout(copyReferenceTimer)
  window.removeEventListener('focus', refreshDay)
  document.removeEventListener('visibilitychange', refreshDay)
})
</script>

<style scoped>
.watchlist-heading {
  vertical-align: middle;
  white-space: nowrap;
}

.watchlist-heading__content {
  display: flex;
  align-items: center;
  gap: 0.25rem;
}

.watchlist-heading__content > :last-child {
  flex-shrink: 0;
}

.watchlist-heading__sort {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  min-height: 1.75rem;
  color: inherit;
  font: inherit;
  letter-spacing: inherit;
  text-transform: inherit;
  white-space: nowrap;
  cursor: pointer;
}

.watchlist-heading__sort:hover,
.watchlist-heading__sort--active {
  color: var(--accent);
}

.watchlist-heading__sort:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 3px;
  border-radius: 3px;
}

.watchlist-heading__arrow {
  width: 0.7rem;
  text-align: center;
}

.deal-card--alternate {
  background: var(--surface2);
}

.deal-card__header {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  gap: 0.75rem;
}

.deal-card__identity {
  flex: 1 1 22rem;
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 0.3rem;
}

.deal-card__identity-meta {
  display: flex;
  min-height: 1.35rem;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
  padding-left: 1.25rem;
  font-size: 0.75rem;
}

.deal-card__actions {
  display: flex;
  flex: 0 1 auto;
  flex-wrap: wrap;
  align-items: flex-start;
  justify-content: flex-end;
  gap: 0.5rem;
  min-width: 0;
  max-width: 100%;
  margin-left: auto;
}

.deal-card__actions > button {
  flex: 0 0 auto;
  min-height: 2rem;
  white-space: nowrap;
}

.booking-portfolio-filter {
  width: auto;
  min-width: min(14rem, 100%);
  max-width: 100%;
}

.deal-open-menu__item {
  white-space: nowrap;
  border: 1px solid var(--border);
  border-radius: 0.375rem;
  background: var(--surface);
  padding: 0.375rem 0.55rem;
  color: var(--text);
  font-size: 0.6875rem;
  font-weight: 600;
}

.deal-open-menu__item:hover {
  border-color: var(--accent);
  color: var(--accent);
}

.deal-card__portfolio,
.deal-card__portfolio-label {
  max-width: min(22rem, 100%);
}

.deal-card__portfolio-label {
  min-width: 0;
  white-space: normal;
  overflow-wrap: anywhere;
  border: 1px solid var(--border);
  border-radius: 0.375rem;
  padding: 0.375rem 0.65rem;
  color: var(--muted);
  font-size: 0.75rem;
}

/* ── Synthèse du deal : quatre panneaux, une identité chacun ──────────────
   La teinte dit de quoi parle le panneau (contrat, marché, hypothèses,
   résultat) et deux voisins n'ont jamais la même, en 4, 2 ou 1 colonne. Les
   chiffres sont posés sur des cuvettes blanches et le texte reste encre :
   aucune écriture de couleur sur un fond de la même couleur (le badge bleu
   sur panneau bleu était illisible). */
.deal-overview-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 0.9rem;
  padding-top: 0.9rem;
  border-top: 1px solid var(--border);
}

.deal-panel {
  --panel-tint: var(--surface);
  --panel-edge: var(--border);
  --panel-accent: var(--muted);
  position: relative;
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 0.75rem;
  border: 1px solid var(--panel-edge);
  border-top: 3px solid var(--panel-accent);
  border-radius: 12px;
  background: var(--panel-tint);
  padding: 0.8rem 0.9rem 0.9rem;
  box-shadow: 0 1px 2px rgba(26, 24, 20, 0.05);
  transition: transform 200ms cubic-bezier(0.2, 0.8, 0.2, 1), box-shadow 200ms ease, border-color 200ms ease;
}

.deal-panel--contract { --panel-tint: #f4f6f9; --panel-edge: #d6dce5; --panel-accent: #52627a; }
.deal-panel--market { --panel-tint: #edf7f4; --panel-edge: #c3e1d8; --panel-accent: #14806f; }
.deal-panel--model { --panel-tint: #f5f1fc; --panel-edge: #d9cfef; --panel-accent: #6e51bd; }
.deal-panel--result { --panel-tint: var(--surface); --panel-edge: #b7cfeb; --panel-accent: var(--accent); }

.deal-panel:focus-within {
  border-color: var(--panel-accent);
}

/* Survol : le panneau passe devant ses voisins et grossit. Pointeur
   seulement (au doigt, le survol resterait collé), et sans mouvement pour qui
   l'a désactivé dans son système. */
@media (hover: hover) and (prefers-reduced-motion: no-preference) {
  .deal-panel:hover {
    z-index: 2;
    transform: scale(1.04);
    box-shadow: 0 18px 38px -14px rgba(26, 24, 20, 0.32), 0 3px 8px rgba(26, 24, 20, 0.06);
  }
}

@media (hover: hover) and (prefers-reduced-motion: no-preference) and (max-width: 1350px) {
  .deal-panel:hover {
    transform: scale(1.025);
  }
}

@media (hover: hover) and (prefers-reduced-motion: reduce) {
  .deal-panel:hover {
    box-shadow: 0 0 0 2px var(--panel-accent);
  }
}

.deal-panel__head {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.deal-panel__dot {
  width: 0.5rem;
  height: 0.5rem;
  flex: 0 0 auto;
  border-radius: 2px;
  background: var(--panel-accent);
}

.deal-panel__title {
  color: #2f2b25;
  font-size: 0.6875rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  line-height: 1.2;
  text-transform: uppercase;
}

.deal-history-link {
  margin-left: auto;
  border-bottom: 1px solid transparent;
  color: var(--accent);
  font-size: 0.65rem;
  font-weight: 700;
}

.deal-history-link:hover {
  border-bottom-color: var(--accent);
}

.deal-well {
  border: 1px solid var(--panel-edge);
  border-radius: 9px;
  background: var(--surface);
}

.deal-label {
  display: block;
  color: #635d53;
  font-size: 0.6875rem;
  font-weight: 500;
  line-height: 1.2;
}

.deal-value {
  display: block;
  margin-top: 0.2rem;
  color: var(--text);
  font-family: 'JetBrains Mono', 'Fira Code', Consolas, monospace;
  font-size: 0.78rem;
  font-variant-numeric: tabular-nums;
  font-weight: 600;
  line-height: 1.3;
  overflow-wrap: anywhere;
}

.deal-value.is-secondary {
  color: #57524a;
  font-weight: 500;
}

.deal-figures {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.deal-figures > div {
  min-width: 0;
  padding: 0.5rem 0.65rem;
}

.deal-figures > div:nth-child(odd) {
  border-right: 1px solid var(--border);
}

.deal-figures > div:nth-child(n + 3) {
  border-top: 1px solid var(--border);
}

/* ── Contrat ── */
.deal-dates {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0.55rem 0.75rem;
  padding: 0 0.15rem;
}

.deal-dates dt {
  color: #635d53;
  font-size: 0.6875rem;
  line-height: 1.2;
}

.deal-dates dd {
  margin-top: 0.15rem;
  color: var(--text);
  font-family: 'JetBrains Mono', 'Fira Code', Consolas, monospace;
  font-size: 0.75rem;
  font-variant-numeric: tabular-nums;
  font-weight: 600;
  white-space: nowrap;
}

.deal-term-list {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
}

.deal-term {
  display: inline-flex;
  align-items: baseline;
  gap: 0.35rem;
  border: 1px solid var(--panel-edge);
  border-radius: 999px;
  background: var(--surface);
  padding: 0.2rem 0.55rem;
  color: #57524a;
  font-size: 0.6875rem;
}

.deal-term strong {
  color: var(--text);
  font-family: 'JetBrains Mono', 'Fira Code', Consolas, monospace;
  font-weight: 700;
}

.deal-realized {
  color: #57524a;
  font-size: 0.75rem;
}

.deal-realized strong {
  color: var(--text);
  font-family: 'JetBrains Mono', 'Fira Code', Consolas, monospace;
}

.deal-technical-details {
  color: #57524a;
  font-size: 0.6875rem;
}

.deal-technical-details summary {
  width: fit-content;
  cursor: pointer;
  color: #3d382f;
  font-weight: 600;
  text-decoration: underline;
  text-decoration-color: var(--panel-edge);
  text-underline-offset: 3px;
}

.deal-technical-details p {
  margin-top: 0.4rem;
  color: #57524a;
  font-family: 'JetBrains Mono', 'Fira Code', Consolas, monospace;
  line-height: 1.45;
}

/* ── Marché ── */
.deal-underlying {
  padding: 0.5rem 0.65rem;
}

.deal-underlying + .deal-underlying {
  border-top: 1px solid var(--border);
}

.deal-underlying__top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
}

.deal-underlying__name {
  overflow: hidden;
  color: var(--text);
  font-family: 'JetBrains Mono', 'Fira Code', Consolas, monospace;
  font-size: 0.8125rem;
  font-weight: 700;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.deal-perf {
  flex: 0 0 auto;
  border-radius: 999px;
  background: var(--surface2);
  padding: 0.1rem 0.5rem;
  color: #57524a;
  font-family: 'JetBrains Mono', 'Fira Code', Consolas, monospace;
  font-size: 0.75rem;
  font-weight: 700;
}

.deal-perf.tone-pos { background: var(--positive-light); }
.deal-perf.tone-neg { background: var(--negative-light); }

.deal-underlying__levels {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 0.2rem 0.4rem;
  margin-top: 0.25rem;
  color: #635d53;
  font-size: 0.6875rem;
}

.deal-underlying__levels strong {
  color: var(--text);
  font-family: 'JetBrains Mono', 'Fira Code', Consolas, monospace;
  font-size: 0.75rem;
  font-weight: 600;
}

.deal-underlying__arrow {
  color: var(--subtle);
}

.deal-barriers > * + * {
  border-top: 1px solid var(--border);
}

/* Règle des barrières : zones, repères et curseur sont placés en % de la
   largeur par barrierGauges (utils/barriers.js). */
.barrier-gauge {
  padding: 0.55rem 0.65rem 0.45rem;
}

.barrier-gauge__caption {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 0.5rem;
  font-size: 0.6875rem;
}

.barrier-gauge__caption span:first-child {
  overflow: hidden;
  color: #3d382f;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.barrier-gauge__caption span:last-child {
  flex: 0 0 auto;
  color: var(--subtle);
  font-size: 0.625rem;
}

.barrier-gauge__track {
  position: relative;
  height: 0.5rem;
  margin: 1.35rem 0.4rem 1.3rem;
  border-radius: 999px;
  background: #e9e6df;
}

.barrier-gauge__zone {
  position: absolute;
  top: 0;
  bottom: 0;
}

.barrier-gauge__zone--loss {
  left: 0;
  border-radius: 999px 0 0 999px;
  background: #f3c4bd;
}

.barrier-gauge__zone--gain {
  right: 0;
  border-radius: 0 999px 999px 0;
  background: #b9e0c9;
}

.barrier-gauge__mark {
  position: absolute;
  top: -0.3rem;
  bottom: -0.3rem;
  width: 2px;
  margin-left: -1px;
  border-radius: 1px;
  background: var(--muted);
}

.barrier-gauge__mark--ki { background: var(--negative); }
.barrier-gauge__mark--autocall { background: var(--positive); }

.barrier-gauge__mark span,
.barrier-gauge__cursor span {
  position: absolute;
  left: 50%;
  transform: translateX(-50%);
  font-family: 'JetBrains Mono', 'Fira Code', Consolas, monospace;
  font-size: 0.625rem;
  font-weight: 700;
  line-height: 1;
  white-space: nowrap;
}

.barrier-gauge__mark span { bottom: calc(100% + 0.2rem); }
.barrier-gauge__mark--ki span { color: var(--negative); }
.barrier-gauge__mark--autocall span { color: var(--positive); }

.barrier-gauge__cursor {
  position: absolute;
  top: 50%;
  width: 0.85rem;
  height: 0.85rem;
  margin: -0.425rem 0 0 -0.425rem;
  border: 2px solid var(--surface);
  border-radius: 999px;
  background: var(--text);
  box-shadow: 0 1px 3px rgba(26, 24, 20, 0.35);
}

.barrier-gauge__cursor span {
  top: calc(100% + 0.25rem);
  color: var(--text);
}

.deal-barrier-row {
  display: grid;
  grid-template-columns: 0.2rem minmax(0, 1fr) auto auto;
  align-items: center;
  gap: 0.5rem;
  padding: 0.45rem 0.65rem 0.45rem 0.5rem;
}

.deal-barrier-row__tick {
  align-self: stretch;
  border-radius: 2px;
  background: var(--border2);
}

.deal-barrier-row__tick--ki { background: var(--negative); }
.deal-barrier-row__tick--autocall { background: var(--positive); }

.deal-barrier-name {
  display: block;
  color: #3d382f;
  font-size: 0.75rem;
  font-weight: 500;
  line-height: 1.25;
}

.deal-barrier-code {
  display: block;
  color: var(--subtle);
  font-family: 'JetBrains Mono', 'Fira Code', Consolas, monospace;
  font-size: 0.625rem;
}

.deal-barrier-row > strong {
  color: var(--text);
  font-family: 'JetBrains Mono', 'Fira Code', Consolas, monospace;
  font-size: 0.8125rem;
  font-weight: 700;
}

.deal-empty-state {
  color: #57524a;
  font-size: 0.75rem;
  line-height: 1.45;
}

/* ── Hypothèses ── */
.deal-basis {
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
}

.deal-panel__select.select,
.deal-panel__select.input {
  border-color: var(--panel-edge);
  background-color: var(--surface);
  color: var(--text);
  font-weight: 600;
}

.deal-panel__select.select:hover,
.deal-panel__select.select:focus,
.deal-panel__select.input:hover,
.deal-panel__select.input:focus {
  border-color: var(--panel-accent);
}

.deal-basis-note {
  color: #4f4a42;
  font-size: 0.75rem;
  line-height: 1.45;
}

.deal-alert {
  display: flex;
  align-items: flex-start;
  gap: 0.4rem;
  border: 1px solid rgba(184, 134, 11, 0.35);
  border-radius: 8px;
  background: var(--gold-light);
  padding: 0.45rem 0.6rem;
  color: #6f5207;
  font-size: 0.6875rem;
  line-height: 1.4;
}

/* ── Résultat ── */
.deal-mtm__value {
  margin-top: 0.15rem;
  color: var(--accent);
  font-family: 'JetBrains Mono', 'Fira Code', Consolas, monospace;
  font-size: 1.9rem;
  font-variant-numeric: tabular-nums;
  font-weight: 700;
  letter-spacing: -0.03em;
  line-height: 1.05;
}

.deal-mtm__ci {
  margin-top: 0.25rem;
  color: #635d53;
  font-family: 'JetBrains Mono', 'Fira Code', Consolas, monospace;
  font-size: 0.6875rem;
}

.deal-result-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.6rem 0.8rem;
  border-top: 1px solid var(--border);
  padding-top: 0.7rem;
}

.deal-best-case {
  border-radius: 8px;
  background: var(--surface2);
  padding: 0.45rem 0.6rem;
  color: #4f4a42;
  font-size: 0.6875rem;
}

.deal-best-case strong {
  color: var(--text);
  font-family: 'JetBrains Mono', 'Fira Code', Consolas, monospace;
}

.deal-best-case span {
  color: #8a6508;
  font-weight: 600;
}

.deal-result-empty {
  display: flex;
  flex: 1 1 auto;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.35rem;
  min-height: 8rem;
  border: 1px dashed var(--panel-edge);
  border-radius: 9px;
  padding: 1rem;
  text-align: center;
}

.deal-result-empty > strong {
  color: var(--text);
  font-size: 0.8125rem;
  font-weight: 700;
}

.deal-result-empty > span {
  color: #57524a;
  font-size: 0.75rem;
  line-height: 1.4;
}

.deal-result-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
  margin-top: auto;
}

/* Couleurs de signe en dernier, sous le panneau : elles doivent l'emporter
   sur toutes les couleurs de base ci-dessus. */
.deal-panel .tone-pos { color: var(--positive); }
.deal-panel .tone-neg { color: var(--negative); }
.deal-panel .tone-warn { color: #8a6508; }
.deal-panel .tone-info { color: #0369a1; }

@media (max-width: 1350px) {
  .deal-overview-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 900px) {
  .deal-card__actions {
    flex-basis: 100%;
    justify-content: flex-start;
    margin-left: 0;
  }

  .deal-overview-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
