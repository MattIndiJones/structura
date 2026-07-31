<template>
  <div class="flex-1 flex flex-col min-h-0 overflow-hidden">

    <div class="page-header px-6 pt-6 pb-0 mb-0">
      <div class="flex items-center gap-3">
        <RouterLink :to="{ path: '/', query: { category: 'competitive_bidding' } }" class="btn-secondary text-xs px-3 py-1.5">← Retour</RouterLink>
        <h1 class="page-title">RFQ Fournisseurs</h1>
      </div>
      <div class="page-actions">
        <RouterLink to="/rfq/analyse" class="btn-ghost btn-sm">📈 Analyse</RouterLink>
        <button class="btn-primary text-xs px-3 py-1.5" @click="openCreateForm">+ Nouvelle RFQ</button>
      </div>
    </div>
    <AlertMessage v-if="listError" kind="error" dismissible class="mx-6 mt-3" @dismiss="listError = ''">{{ listError }}</AlertMessage>
    <AlertMessage v-if="notice" kind="success" dismissible class="mx-6 mt-3" @dismiss="notice = ''">{{ notice }}</AlertMessage>

    <div class="flex flex-1 min-h-0">

      <!-- ── Liste RFQ ──────────────────────────────────────────── -->
      <aside class="w-80 shrink-0 border-r border-slate-800 overflow-y-auto p-3 flex flex-col gap-2">
        <LoadingSpinner v-if="loadingList" class="py-4" />
        <EmptyState v-else-if="!rfq.list.length" icon="📨" title="Aucune RFQ pour l'instant" />
        <template v-else>
          <DataFilterBar :fields="rfqFilterFields" :state="rfqFilter.state"
                         :field-options="rfqFilter.fieldOptions.value"
                         :has-active-filters="rfqFilter.hasActiveFilters.value"
                         :sorts="rfqSorts" :sort-by="rfqFilter.sortBy.value"
                         :sort-dir="rfqFilter.sortDir.value"
                         :count="filteredRfqs.length" :total="rfq.list.length" noun="AO"
                         class="p-2 gap-2"
                         @update:sort-by="rfqFilter.sortBy.value = $event"
                         @toggle-dir="rfqFilter.toggleSortDir()" @reset="rfqFilter.reset()" />
          <div v-if="!filteredRfqs.length" class="text-xs text-slate-600 px-1 py-3">
            Aucun AO ne correspond à ces filtres.
          </div>
        </template>
        <div v-for="r in filteredRfqs" :key="r.id"
             :class="['card p-3 flex flex-col gap-1.5 cursor-pointer transition-all duration-200 hover:shadow-lg hover:shadow-black/20',
                      selectedId === r.id ? 'border-blue-600 shadow-lg shadow-blue-950/30' : 'hover:border-slate-700']"
             @click="selectRfq(r.id)">
          <div class="flex items-start justify-between gap-2">
            <span class="font-semibold text-slate-200 text-sm truncate">{{ r.name || r.reference }}</span>
            <div class="flex items-center gap-1.5 shrink-0">
              <span :class="['text-[9px] rounded px-1.5 py-0.5 border', sensBadge(r.sens)]" :title="sensHint(r.sens)">{{ sensLabel(r.sens) }}</span>
              <span :class="['text-[9px] rounded px-1.5 py-0.5 border', kindBadge(r.kind)]">{{ kindLabel(r.kind) }}</span>
              <span :class="['text-[9px] rounded px-1.5 py-0.5 border', statusBadge(r.status)]">{{ statusLabel(r.status) }}</span>
              <button class="icon-btn-danger" title="Supprimer" aria-label="Supprimer la RFQ" @click.stop="deleteRfq(r.id)">🗑</button>
            </div>
          </div>
          <div class="text-[10px] text-slate-600 font-mono">{{ r.reference }} · AO {{ fmtDateOnly(r.ao_date) }}</div>
          <div class="flex items-center gap-3 text-[10px] text-slate-500 mt-1">
            <span v-if="r.model_price !== null">Modèle: {{ fmtPrice(r.model_price) }}</span>
            <span v-else class="text-slate-700">Modèle: —</span>
          </div>
        </div>
      </aside>

      <!-- ── Panneau principal ──────────────────────────────────── -->
      <main class="flex-1 overflow-y-auto p-6">

        <!-- Formulaire de création -->
        <div v-if="showCreateForm" class="max-w-2xl flex flex-col gap-4">
          <h2 class="text-sm font-bold text-slate-300 uppercase tracking-wider">Nouvelle RFQ</h2>

          <AlertMessage v-if="createError" kind="error">{{ createError }}</AlertMessage>

          <div class="card flex flex-col gap-3">
            <div class="grid grid-cols-2 gap-3">
              <div class="flex flex-col gap-1">
                <label class="label">Nom *</label>
                <input v-model="form.name" type="text" class="input" placeholder="Autocall Athena USD 3Y — Client X" />
              </div>
              <div class="flex flex-col gap-1">
                <label class="label">Date de l'AO</label>
                <input v-model="form.ao_date" type="date" class="input" />
              </div>
            </div>

            <div class="flex flex-col gap-1">
              <label class="label">Type de RFQ</label>
              <div class="flex items-center gap-1 text-[10px] border border-slate-700 rounded overflow-hidden w-fit">
                <button :class="['px-2 py-1 transition-colors', form.kind === 'indicatif' ? 'bg-slate-700 text-slate-200 font-semibold' : 'text-slate-500 hover:text-slate-400']"
                        @click="onKindToggle('indicatif')">Indicatif</button>
                <button :class="['px-2 py-1 transition-colors', form.kind === 'to_trade' ? 'bg-amber-900/80 text-amber-300 font-semibold' : 'text-slate-500 hover:text-slate-400']"
                        @click="onKindToggle('to_trade')">To trade</button>
              </div>
              <p class="text-[10px] text-slate-600 mt-0.5">
                {{ form.kind === 'indicatif'
                  ? "Sonder rapidement un niveau de prix pour affiner une idée — script Normal, pas de trade attendu."
                  : "Pensée pour aboutir à un trade — script en mode Expert (calendrier CONSTAT réel) : template Expert prédéfini, script sauvegardé ou deal déjà booké." }}
              </p>
            </div>

            <div class="flex flex-col gap-1">
              <label class="label">Sens (notre côté)</label>
              <div class="flex items-center gap-1 text-[10px] border border-slate-700 rounded overflow-hidden w-fit">
                <button :class="['px-2 py-1 transition-colors', form.sens === 'achat' ? 'bg-emerald-900/70 text-emerald-300 font-semibold' : 'text-slate-500 hover:text-slate-400']"
                        @click="form.sens = 'achat'">↓ Achat (nous achetons)</button>
                <button :class="['px-2 py-1 transition-colors', form.sens === 'vente' ? 'bg-blue-900/70 text-blue-300 font-semibold' : 'text-slate-500 hover:text-slate-400']"
                        @click="form.sens = 'vente'">↑ Vente (nous vendons)</button>
              </div>
              <p class="text-[10px] text-slate-600 mt-0.5">{{ sensHint(form.sens) }}</p>
            </div>

            <div class="flex items-center gap-1 text-[10px] border border-slate-700 rounded overflow-hidden w-fit">
              <button :class="['px-2 py-1 transition-colors', form.source === 'template' ? 'bg-slate-700 text-slate-200 font-semibold' : 'text-slate-500 hover:text-slate-400']"
                      @click="onSourceToggle('template')">{{ form.kind === 'to_trade' ? 'Template Expert' : 'Template no-code' }}</button>
              <button :class="['px-2 py-1 transition-colors', form.source === 'script' ? 'bg-blue-900/80 text-blue-300 font-semibold' : 'text-slate-500 hover:text-slate-400']"
                      @click="onSourceToggle('script')">Script existant</button>
            </div>

            <div v-if="form.source === 'template'" class="flex flex-col gap-1">
              <label class="label">Type de produit</label>
              <select v-model="form.template_type" class="select" @change="onTemplateChange">
                <option value="">Choisir un template…</option>
                <optgroup v-for="(items, group) in groupedTemplates" :key="group" :label="group">
                  <option v-for="t in items" :key="t.key" :value="t.key">{{ t.label }}</option>
                </optgroup>
              </select>
              <p v-if="form.kind === 'to_trade'" class="text-[10px] text-slate-600 mt-0.5">
                Version Expert du template (calendrier CONSTAT déjà en place) — les mêmes 16 modèles qu'en mode Normal.
              </p>
            </div>
            <div v-else class="flex flex-col gap-1">
              <label class="label">Script de la bibliothèque</label>
              <select :value="librarySelectValue" class="select" @change="onLibrarySelect($event.target.value)">
                <option value="">Choisir un script…</option>
                <optgroup label="Scripts sauvegardés">
                  <option v-for="s in scripts" :key="'s'+s.id" :value="'script:'+s.id">{{ s.name }}</option>
                </optgroup>
                <optgroup v-if="expertDeals.length" label="Deals bookés (mode Expert)">
                  <option v-for="d in expertDeals" :key="'d'+d.id" :value="'deal:'+d.id">
                    {{ d.reference }} — {{ d.product_type || d.contrepartie }}
                  </option>
                </optgroup>
              </select>
              <p v-if="form.kind === 'to_trade'" class="text-[10px] text-slate-600 mt-0.5">
                Seuls les scripts avec un calendrier CONSTAT réel (mode Expert) conviennent pour une RFQ to trade.
              </p>
            </div>

            <!-- Sous-jacent -->
            <div class="grid grid-cols-2 gap-3">
              <div class="flex flex-col gap-1">
                <label class="label">Sous-jacent</label>
                <select class="select" :value="form.underlying_ticker" @change="onUnderlyingSelect($event.target.value)">
                  <option value="">— Choisir un sous-jacent —</option>
                  <optgroup v-for="g in underlyingGroups" :key="g.group" :label="g.group">
                    <option v-for="it in g.items" :key="it.ticker" :value="it.ticker">{{ it.label }}</option>
                  </optgroup>
                </select>
                <input v-model="form.underlying_ticker" type="text" class="input font-mono text-xs mt-1"
                       placeholder="Ticker (ou saisie libre)" />
              </div>
              <div class="flex flex-col gap-1">
                <label class="label">Nominal</label>
                <input v-model="nominalRaw" @blur="formatNominal" @focus="unformatNominal"
                       type="text" inputmode="numeric" class="input font-mono"
                       placeholder="1 000 000" />
              </div>
              <div class="flex flex-col gap-1">
                <label class="label">Devise</label>
                <select v-model="form.currency" class="select">
                  <option>EUR</option><option>USD</option><option>GBP</option>
                  <option>JPY</option><option>CHF</option><option>SGD</option>
                </select>
              </div>
              <div class="flex flex-col gap-1">
                <label class="label">Maturité (années)</label>
                <input v-model.number="form.T" type="number" step="0.5" class="input" />
              </div>
              <div class="flex flex-col gap-1">
                <label class="label">Date de strike</label>
                <input v-model="form.strike_date" type="date" class="input" />
              </div>
              <div class="flex flex-col gap-1">
                <label class="label">Date de valeur</label>
                <input v-model="form.value_date" type="date" class="input" />
              </div>
              <div class="flex flex-col gap-1">
                <label class="label">Date de maturité</label>
                <input :value="createMaturityDate" type="date" readonly
                       class="input bg-slate-800/40 text-slate-500 cursor-not-allowed" />
              </div>
            </div>

            <!-- Termes du produit + calendrier(s) CONSTAT (dynamiques, extraits du script) -->
            <div v-if="parsedParams.length || scriptConstats.length" class="border-t border-slate-800 pt-3">
              <RfqParamsEditor :parsed-params="parsedParams" :param-overrides="paramOverrides"
                               :constats="scriptConstats" :constat-overrides="constatOverrides" />
            </div>

            <!-- Hypothèses de pricing (avancé, pour le calcul du prix modèle interne) -->
            <details class="border-t border-slate-800 pt-3">
              <summary class="label mb-0 cursor-pointer select-none">▸ Hypothèses de pricing (avancé)</summary>
              <div class="flex items-center gap-3 mt-2">
                <button type="button" class="btn-secondary text-xs px-3 py-1.5"
                        :disabled="!form.underlying_ticker?.trim() || createYfLoading"
                        :title="form.underlying_ticker?.trim()
                                ? `Vol réalisée 1 an et rendement du dividende de ${form.underlying_ticker} (Yahoo Finance)`
                                : 'Renseignez un ticker de sous-jacent ci-dessus'"
                        @click="loadCreateUnderlyingParams">
                  📡 Charger les paramètres du sous-jacent
                </button>
                <span v-if="createYfStatus" class="text-[10px] text-slate-500">{{ createYfStatus }}</span>
              </div>
              <div class="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-2">
                <div class="flex flex-col gap-1">
                  <label class="label">Vol implicite (%)</label>
                  <input v-model.number="advanced.sigma" type="number" class="input" />
                </div>
                <div class="flex flex-col gap-1">
                  <label class="label">Dividende (%)</label>
                  <input v-model.number="advanced.q" type="number" step="0.1" class="input" />
                </div>
                <div class="flex flex-col gap-1">
                  <label class="label">Taux sans risque (%)</label>
                  <input v-model.number="advanced.r" type="number" step="0.1" class="input" />
                </div>
                <div class="flex flex-col gap-1">
                  <label class="label">Trajectoires (N)</label>
                  <input v-model.number="advanced.N" type="number" step="1000" class="input" />
                </div>
                <div class="flex flex-col gap-1">
                  <label class="label">Modèle</label>
                  <select v-model="advanced.model" class="select">
                    <option value="constant">Constant (GBM)</option>
                    <option value="heston">Heston</option>
                    <option value="sabr">SABR</option>
                    <option value="localvol">Dupire (Local Vol)</option>
                    <option value="lsv">Local-Stochastic Vol</option>
                  </select>
                </div>
              </div>
            </details>
          </div>

          <div class="flex gap-2">
            <button class="btn-primary text-sm" :disabled="creating" @click="submitCreate">
              {{ creating ? 'Création…' : 'Créer la RFQ' }}
            </button>
            <button class="btn-secondary text-sm" @click="showCreateForm = false">Annuler</button>
          </div>
        </div>

        <!-- Détail RFQ -->
        <div v-else-if="rfq.current" class="max-w-5xl flex flex-col gap-4">
          <div class="flex items-start justify-between">
            <div>
              <div class="flex items-center gap-2">
                <h2 class="text-lg font-bold text-slate-100">{{ rfq.current.name || rfq.current.reference }}</h2>
                <span :class="['text-[9px] rounded px-1.5 py-0.5 border', sensBadge(rfq.current.sens)]" :title="sensHint(rfq.current.sens)">{{ sensLabel(rfq.current.sens) }}</span>
                <span :class="['text-[9px] rounded px-1.5 py-0.5 border', kindBadge(rfq.current.kind)]">{{ kindLabel(rfq.current.kind) }}</span>
              </div>
              <div class="text-xs text-slate-500 font-mono">{{ rfq.current.reference }} · {{ rfq.current.template_type || 'script personnalisé' }}</div>
            </div>
            <div class="flex items-center gap-2 shrink-0">
              <button v-if="rfq.current.kind === 'indicatif'" class="btn-secondary text-xs px-3 py-1.5" title="Créer une RFQ 'to trade' à partir de celle-ci, avec un script précis"
                      @click="convertToTrade(rfq.current)">📐 Convertir en RFQ to trade</button>
              <button class="btn-secondary text-xs px-3 py-1.5" title="Créer une nouvelle RFQ à partir de celle-ci"
                      @click="duplicateRfq(rfq.current)">⎘ Dupliquer</button>
              <button class="icon-btn-danger" title="Supprimer" aria-label="Supprimer la RFQ" @click="deleteRfq(rfq.current.id)">🗑</button>
            </div>
          </div>

          <!-- Détails du produit -->
          <div class="card grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div>
              <div class="label mb-0.5">Date de l'AO</div>
              <div class="text-xs text-slate-200">{{ fmtDateOnly(rfq.current.ao_date) }}</div>
            </div>
            <div>
              <div class="label mb-0.5">Sous-jacent</div>
              <div class="text-xs text-slate-200">
                {{ underlyingSummary.name || '—' }}
                <span v-if="underlyingSummary.ticker" class="text-slate-500 font-mono">({{ underlyingSummary.ticker }})</span>
              </div>
            </div>
            <div>
              <div class="label mb-0.5">Nominal</div>
              <div class="text-xs text-slate-200">{{ fmtNominal(rfq.current.params?.notional) }} {{ rfq.current.params?.currency || '' }}</div>
            </div>
            <div>
              <div class="label mb-0.5">Date de strike</div>
              <div class="text-xs text-slate-200">{{ fmtDateOnly(rfq.current.params?.strike_date) || '—' }}</div>
            </div>
            <div>
              <div class="label mb-0.5">Date de valeur</div>
              <div class="text-xs text-slate-200">{{ fmtDateOnly(rfq.current.params?.value_date) || '—' }}</div>
            </div>
            <div>
              <div class="label mb-0.5">Maturité</div>
              <div class="text-xs text-slate-200">
                {{ fmtDateOnly(detailMaturityDate) || '—' }}
                <span v-if="rfq.current.params?.T" class="text-slate-500">({{ fmtTenor(rfq.current.params.T) }} ans)</span>
              </div>
            </div>
            <div>
              <div class="label mb-0.5">Statut</div>
              <div class="flex items-center gap-2">
                <span class="text-xs text-slate-200">{{ statusLabel(rfq.current.status) }}</span>
                <button v-if="rfq.current.status !== 'clos'"
                        class="text-[10px] underline text-slate-500 hover:text-slate-300"
                        :title="rfq.current.status === 'sans_suite'
                                ? 'Rendre l\'AO au statut déduit de ses cotations'
                                : 'AO abandonné ou perdu — il ne donnera pas lieu à un trade'"
                        @click="toggleSansSuite">
                  {{ rfq.current.status === 'sans_suite' ? 'Rouvrir' : 'Sans suite' }}
                </button>
              </div>
            </div>
            <div>
              <div class="label mb-0.5">Sens (notre côté)</div>
              <select class="select py-1 px-2 text-xs" :value="rfq.current.sens || 'achat'"
                      :disabled="!!rfq.current.quotes?.length"
                      :title="rfq.current.quotes?.length ? 'Sens figé dès la première sollicitation' : sensHint(rfq.current.sens)"
                      @change="updateSens($event.target.value)">
                <option value="achat">↓ Achat (nous achetons)</option>
                <option value="vente">↑ Vente (nous vendons)</option>
              </select>
            </div>
          </div>

          <!-- Prix modèle — params modifiables avant recalcul -->
          <div class="card flex flex-col gap-3">
            <div class="flex items-center gap-4">
              <div class="stat-box flex-1">
                <div class="text-[10px] text-slate-500 uppercase tracking-wider mb-1">Prix modèle Structura</div>
                <div class="text-xl font-bold text-slate-100">{{ fmtPrice(rfq.current.model_price) }}</div>
                <div v-if="rfq.current.model_price_at" class="text-[10px] text-slate-600 mt-0.5">
                  Calculé le {{ fmtDate(rfq.current.model_price_at) }}
                </div>
              </div>
              <button class="btn-secondary text-xs" :disabled="computing || !!rfq.current.booked_deal" @click="computeModelPrice">
                {{ computing ? 'Calcul…' : 'Calculer prix modèle' }}
              </button>
            </div>

            <details class="border-t border-slate-800 pt-3">
              <summary class="label mb-0 cursor-pointer select-none">▸ Paramètres de pricing (modifiables)</summary>
              <div class="mt-2 flex flex-col gap-3">
                <fieldset :disabled="!!rfq.current.quotes?.length">
                  <RfqParamsEditor :parsed-params="detailParsedParams" :param-overrides="detailParamOverrides"
                                   :constats="detailScriptConstats" :constat-overrides="detailConstatOverrides" />
                </fieldset>
                <div class="flex items-center gap-3 border-t border-slate-800 pt-3">
                  <button type="button" class="btn-secondary text-xs px-3 py-1.5"
                          :disabled="!underlyingSummary.ticker || detailYfLoading"
                          :title="underlyingSummary.ticker
                                  ? `Vol réalisée 1 an et rendement du dividende de ${underlyingSummary.ticker} (Yahoo Finance)`
                                  : 'Aucun ticker de sous-jacent sur cette RFQ'"
                          @click="loadDetailUnderlyingParams">
                    📡 Charger les paramètres du sous-jacent
                  </button>
                  <span v-if="detailYfStatus" class="text-[10px] text-slate-500">{{ detailYfStatus }}</span>
                </div>
                <div class="grid grid-cols-2 sm:grid-cols-4 gap-3">
                  <div class="flex flex-col gap-1">
                    <label class="label">Vol implicite (%)</label>
                    <input v-model.number="detailAdvanced.sigma" type="number" class="input" />
                  </div>
                  <div class="flex flex-col gap-1">
                    <label class="label">Dividende (%)</label>
                    <input v-model.number="detailAdvanced.q" type="number" step="0.1" class="input" />
                  </div>
                  <div class="flex flex-col gap-1">
                    <label class="label">Taux sans risque (%)</label>
                    <input v-model.number="detailAdvanced.r" type="number" step="0.1" class="input" />
                  </div>
                  <div class="flex flex-col gap-1">
                    <label class="label">Trajectoires (N)</label>
                    <input v-model.number="detailAdvanced.N" type="number" step="1000" class="input" />
                  </div>
                  <div class="flex flex-col gap-1">
                    <label class="label">Modèle</label>
                    <select v-model="detailAdvanced.model" class="select">
                      <option value="constant">Constant (GBM)</option>
                      <option value="heston">Heston</option>
                      <option value="sabr">SABR</option>
                      <option value="localvol">Dupire (Local Vol)</option>
                      <option value="lsv">Local-Stochastic Vol</option>
                    </select>
                  </div>
                  <div class="flex flex-col gap-1">
                    <label class="label">Date de strike</label>
                    <input v-model="detailAdvanced.strike_date" type="date" class="input"
                           :disabled="!!rfq.current.quotes?.length" />
                  </div>
                  <div class="flex flex-col gap-1">
                    <label class="label">Date de valeur</label>
                    <input v-model="detailAdvanced.value_date" type="date" class="input"
                           :disabled="!!rfq.current.quotes?.length" />
                  </div>
                  <div class="flex flex-col gap-1">
                    <label class="label">Date de maturité</label>
                    <input :value="detailMaturityDate" type="date" readonly
                           class="input bg-slate-800/40 text-slate-500 cursor-not-allowed" />
                  </div>
                </div>
              </div>
            </details>
          </div>
          <AlertMessage v-if="computeError" kind="error">{{ computeError }}</AlertMessage>

          <!-- Script (collapsible) -->
          <details class="card text-xs text-slate-400">
            <summary class="font-bold cursor-pointer text-slate-300 select-none">▸ PayScript</summary>
            <pre class="mt-3 font-mono text-slate-400 whitespace-pre-wrap">{{ rfq.current.script_snapshot }}</pre>
          </details>

          <!-- Quotes -->
          <div class="card flex flex-col gap-3">
            <div class="flex items-center justify-between">
              <div class="text-xs font-bold text-slate-400 uppercase tracking-wider">Fournisseurs sollicités</div>
              <div class="flex items-center gap-2">
                <span v-if="bestQuote" class="text-[10px] text-slate-500" :title="sensHint(rfq.current.sens)">
                  Meilleure réponse ({{ rfq.current.sens === 'vente' ? 'prix le plus haut' : 'prix le plus bas' }}) :
                  <span class="text-slate-300 font-semibold">{{ fmtPrice(bestQuote.price) }}</span>
                  ({{ providerLabel(bestQuote.provider) }})
                </span>
                <button v-if="!rfq.current.booked_deal" class="btn-secondary text-xs" @click="openAddQuote">+ Ajouter un fournisseur</button>
              </div>
            </div>

            <AlertMessage v-if="lastLookError" kind="error" dismissible @dismiss="lastLookError = ''">{{ lastLookError }}</AlertMessage>

            <!-- Un AO s'exécute une fois : une fois booké, plus de bouton de
                 booking, on renvoie vers le deal. Le serveur refuse le doublon
                 de toute façon (deals.py:book_deal, 409). -->
            <div v-if="rfq.current.booked_deal"
                 class="flex items-center justify-between gap-3 rounded-lg border border-slate-700 bg-slate-900/40 px-3 py-2">
              <span class="text-xs text-slate-300">
                📋 AO exécuté — deal <span class="font-mono text-slate-200">{{ rfq.current.booked_deal.reference }}</span>.
              </span>
              <button class="btn-secondary text-xs px-3 py-1.5 shrink-0"
                      @click="openBookedDeal">→ Voir le booking</button>
            </div>

            <div v-else-if="rfq.current.selected_quote_id" class="flex items-center justify-between gap-3 rounded-lg border border-amber-800/60 bg-amber-950/20 px-3 py-2">
              <span class="text-xs text-amber-300">
                ⭐ Réponse retenue — prête à booker.
                <span v-if="rfq.current.kind === 'indicatif'" class="text-amber-500/80">
                  RFQ indicative — pensée pour explorer, pas pour trader.
                </span>
              </span>
              <div class="flex items-center gap-2 shrink-0">
                <button v-if="rfq.current.kind === 'indicatif'" class="btn-secondary text-xs px-3 py-1.5"
                        @click="convertToTrade(rfq.current)">📐 Convertir en RFQ to trade</button>
                <button class="btn-primary text-xs px-3 py-1.5" @click="bookFromRfq">📋 Booker cette réponse</button>
              </div>
            </div>

            <div v-if="!rfq.current.quotes?.length" class="text-xs text-slate-600 py-2">
              Aucun fournisseur sollicité pour l'instant.
            </div>

            <div v-else class="table-shell" tabindex="0" role="region">
            <table class="w-full text-xs min-w-[1280px]">
              <thead>
                <tr class="text-left text-slate-500 border-b border-slate-800">
                  <th class="py-1.5 pr-2 font-medium">Fournisseur</th>
                  <th class="py-1.5 pr-2 font-medium">Contact</th>
                  <th class="py-1.5 pr-2 font-medium num">Prix</th>
                  <th class="py-1.5 pr-2 font-medium num"
                      title="Écart au prix modèle Structura, signé de notre côté : positif = en notre faveur (à l'achat, coter sous le modèle ; à la vente, au-dessus).">Écart</th>
                  <th class="py-1.5 pr-2 font-medium whitespace-nowrap">Statut</th>
                  <th class="py-1.5 pr-2 font-medium whitespace-nowrap">Fermeté</th>
                  <th class="py-1.5 pr-2 font-medium whitespace-nowrap">Date réponse</th>
                  <th class="py-1.5 pr-2 font-medium whitespace-nowrap">Valide jusqu'au</th>
                  <th class="py-1.5 pr-2 font-medium whitespace-nowrap" title="Le fournisseur voit le meilleur prix du marché et peut s'aligner, ou garder le deal à son propre prix.">Last look</th>
                  <th class="py-1.5 pr-2 font-medium"></th>
                </tr>
              </thead>
              <tbody>
                <template v-for="q in rfq.current.quotes" :key="q.id">
                <tr :class="['border-b border-slate-800/60', q.id === rfq.current.selected_quote_id ? 'bg-amber-950/10' : '']">
                  <td class="py-1.5 pr-2 text-slate-300 whitespace-nowrap">
                    <span v-if="q.parent_quote_id" class="text-slate-600 mr-1">↳</span>
                    <span :class="q.parent_quote_id ? 'text-slate-400 italic' : ''">
                      {{ q.parent_quote_id ? 'Last look' : providerLabel(q.provider) }}
                    </span>
                  </td>
                  <td class="py-1.5 pr-2 text-slate-500 whitespace-nowrap">{{ q.contact || '—' }}</td>
                  <td class="py-1.5 pr-2">
                    <input type="number" class="input py-1 px-2 w-24"
                           :disabled="!!rfq.current.booked_deal"
                           :value="q.price ?? ''"
                           @change="onQuotePriceChange(q, $event.target.value)" />
                  </td>
                  <td class="py-1.5 pr-2 num whitespace-nowrap" :class="spreadClass(q)">{{ spreadBps(q) }}</td>
                  <td class="py-1.5 pr-2">
                    <select class="select py-1 px-2 min-w-[110px]" :value="q.status"
                            :disabled="!!rfq.current.booked_deal" @change="updateQuoteField(q, 'status', $event.target.value)">
                      <option value="en_attente">En attente</option>
                      <option value="recu">Reçu</option>
                      <option value="decline">Décliné</option>
                      <option value="expire">Expiré</option>
                    </select>
                  </td>
                  <td class="py-1.5 pr-2">
                    <select class="select py-1 px-2 min-w-[110px]" :value="q.firmness || 'UNKNOWN'"
                            :disabled="!!rfq.current.booked_deal"
                            @change="updateQuoteField(q, 'firmness', $event.target.value)">
                      <option value="UNKNOWN">À qualifier</option>
                      <option value="INDICATIVE">Indicative</option>
                      <option value="FIRM">Ferme</option>
                    </select>
                  </td>
                  <td class="py-1.5 pr-2">
                    <input type="datetime-local" class="input py-1 px-2 min-w-[170px]"
                           :disabled="!!rfq.current.booked_deal"
                           :value="toDatetimeLocal(q.quoted_at)"
                           @change="onQuoteDateChange(q, $event.target.value)" />
                  </td>
                  <td class="py-1.5 pr-2">
                    <input type="datetime-local" class="input py-1 px-2 min-w-[170px]"
                           :disabled="!!rfq.current.booked_deal"
                           :value="toDatetimeLocal(q.valid_until)"
                           @change="onQuoteValidityChange(q, $event.target.value)" />
                  </td>
                  <td class="py-1.5 pr-2">
                    <select v-if="!q.parent_quote_id" class="select py-1 px-2 min-w-[80px]"
                            :disabled="!!rfq.current.booked_deal || q.price == null"
                            :value="q.last_look ? 'oui' : 'non'"
                            @change="onLastLookToggle(q, $event.target.value === 'oui')">
                      <option value="non">Non</option>
                      <option value="oui">Oui</option>
                    </select>
                  </td>
                  <td class="py-1.5 pr-2 text-right whitespace-nowrap">
                    <button :class="['text-xs mr-2', q.id === rfq.current.selected_quote_id ? 'text-amber-400 font-semibold' : 'text-slate-600 hover:text-amber-400']"
                            :disabled="!!rfq.current.booked_deal || q.price == null || ['decline', 'expire'].includes(q.status)"
                            :title="q.price == null ? 'Saisissez un prix final avant de retenir la réponse' : (q.id === rfq.current.selected_quote_id ? 'Réponse retenue — cliquer pour désélectionner' : 'Retenir cette réponse')"
                            @click="onSelectQuote(q)">
                      {{ q.id === rfq.current.selected_quote_id ? '★ Retenue' : '☆ Retenir' }}
                    </button>
                    <button v-if="!rfq.current.booked_deal" class="text-slate-600 hover:text-red-400" @click="removeQuote(q.id)">✕</button>
                  </td>
                </tr>
                </template>
              </tbody>
            </table>
            </div>

            <!-- Add quote inline form -->
            <div v-if="addingQuote" class="flex items-end gap-2 pt-2 border-t border-slate-800">
              <div class="flex flex-col gap-1">
                <label class="label">Fournisseur</label>
                <select v-model="quoteForm.provider" class="select">
                  <option v-for="p in rfq.providers" :key="p.id" :value="p.label">{{ p.label }}</option>
                  <option value="autre">Autre (banque non listée)</option>
                </select>
              </div>
              <div v-if="quoteForm.provider === 'autre'" class="flex flex-col gap-1">
                <label class="label">Nom de la banque</label>
                <input v-model="quoteForm.customProvider" type="text" class="input" />
              </div>
              <div class="flex flex-col gap-1">
                <label class="label">Contact</label>
                <input v-model="quoteForm.contact" type="text" class="input" placeholder="Nom / email (optionnel)" />
              </div>
              <button class="btn-primary text-xs px-3 py-2" @click="submitAddQuote">Ajouter</button>
              <button class="btn-secondary text-xs px-3 py-2" @click="addingQuote = false">Annuler</button>
            </div>
          </div>
        </div>

        <!-- État vide -->
        <div v-else class="flex flex-col items-center justify-center py-24 gap-3 text-slate-600">
          <div class="text-4xl">📨</div>
          <div class="text-sm">Sélectionnez une RFQ ou créez-en une nouvelle</div>
        </div>
      </main>
    </div>

    <BaseModal v-model="showDeleteConfirm" title="Supprimer la RFQ" max-width="380px">
      <p class="text-sm text-slate-300">
        Supprimer « {{ deleteTargetLabel }} » ? Les réponses fournisseurs associées seront supprimées aussi. Cette action est irréversible.
      </p>
      <template #footer>
        <button class="btn-secondary text-sm" @click="showDeleteConfirm = false">Annuler</button>
        <button class="btn-danger text-sm" @click="confirmDeleteRfq">Supprimer</button>
      </template>
    </BaseModal>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, nextTick } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import { useRfqStore } from '../stores/rfq.js'
import { apiFetch } from '../utils/api.js'
import { templateMeta, examples, expertExamples } from '../data/payscriptTemplates.js'
import { underlyingGroups } from '../data/commonUnderlyings.js'
import LoadingSpinner from '../components/ui/LoadingSpinner.vue'
import BaseModal from '../components/ui/BaseModal.vue'
import EmptyState from '../components/ui/EmptyState.vue'
import AlertMessage from '../components/ui/AlertMessage.vue'
import DataFilterBar from '../components/ui/DataFilterBar.vue'
import { useDataFilter } from '../composables/useDataFilter.js'
import RfqParamsEditor from '../components/RfqParamsEditor.vue'
import { formatDate, formatDateTime, formatPercent, formatInt, formatBps } from '../utils/format.js'

// ── CONSTAT calendar helpers — mirror of pricing.js's constatOverrides
// shape/serialization (see RfqParamsEditor.vue's docstring), duplicated
// here rather than imported since pricing.js's version is tangled up with
// that store's own script/parseScript state.
function makeDefaultConstatValue(kind) {
  if (kind === 'single') return ''
  return reactive({
    start_date: '', end_date: '', roll_date: '',
    frequency: { value: 3, unit: 'M' }, stub: 'short_last',
    sub_frequency: kind === 'nested_schedule' ? { value: 1, unit: 'M' } : null,
  })
}
function syncConstatOverrides(constats, overridesObj) {
  const names = new Set(constats.map(c => c.name))
  for (const name of Object.keys(overridesObj)) {
    if (!names.has(name)) delete overridesObj[name]
  }
  for (const c of constats) {
    if (!(c.name in overridesObj)) overridesObj[c.name] = makeDefaultConstatValue(c.kind)
  }
}
function tenorStr(t) {
  return (t && t.value) ? `${t.value}${t.unit}` : null
}
function parseTenor(s) {
  const m = s ? String(s).match(/^(\d+)([DMY])$/) : null
  return m ? { value: Number(m[1]), unit: m[2] } : { value: 3, unit: 'M' }
}
function buildConstatsPayload(constats, overridesObj) {
  const out = {}
  for (const c of constats) {
    const v = overridesObj[c.name]
    if (c.kind === 'single') {
      out[c.name] = v
    } else {
      out[c.name] = {
        start_date: v.start_date, end_date: v.end_date, roll_date: v.roll_date,
        frequency: tenorStr(v.frequency), stub: v.stub,
        sub_frequency: c.kind === 'nested_schedule' ? tenorStr(v.sub_frequency) : null,
      }
    }
  }
  return out
}
// Restores overridesObj from a previously-saved constats payload (same
// shape buildConstatsPayload produces) — used when duplicating/converting
// an RFQ, or loading the detail view's editable copy.
function restoreConstatOverrides(constats, overridesObj, saved) {
  syncConstatOverrides(constats, overridesObj)
  for (const c of constats) {
    const sv = saved?.[c.name]
    if (sv == null) continue
    if (c.kind === 'single') {
      overridesObj[c.name] = typeof sv === 'string' ? sv : (sv.date || '')
    } else {
      overridesObj[c.name].start_date = sv.start_date || ''
      overridesObj[c.name].end_date = sv.end_date || ''
      overridesObj[c.name].roll_date = sv.roll_date || ''
      overridesObj[c.name].frequency = parseTenor(sv.frequency)
      overridesObj[c.name].stub = sv.stub || 'short_last'
      if (c.kind === 'nested_schedule') overridesObj[c.name].sub_frequency = parseTenor(sv.sub_frequency)
    }
  }
}

const rfq = useRfqStore()
const router = useRouter()

const loadingList    = ref(true)
const listError      = ref('')
const notice         = ref('')
const selectedId     = ref(null)
const showCreateForm = ref(false)
const creating       = ref(false)
const createError    = ref('')
const computing      = ref(false)
const computeError   = ref('')
const addingQuote    = ref(false)
const scripts        = ref([])
// Booked deals, used only to offer their frozen Expert-mode script as an
// alternative source in the "Script de la bibliothèque" picker below — a
// desk often already has the exact precise calendar it wants sitting on a
// past deal rather than saved separately in the script library.
const dealsForScripts = ref([])
const expertDeals = computed(() =>
  dealsForScripts.value.filter(d => d.script_snapshot?.includes('CONSTAT'))
)

const groupedTemplates = computed(() => {
  const groups = {}
  for (const t of templateMeta) {
    (groups[t.group] ||= []).push(t)
  }
  return groups
})

function todayIso() {
  return new Date().toISOString().slice(0, 10)
}

// Mirrors DealTab.vue's own addBizDays/maturity derivation — kept local here
// too since an RFQ has no Deal instance to borrow it from, and the two only
// need to agree on the date shape (ISO string), not share a live import.
function addBizDays(isoDate, n) {
  const d = new Date(isoDate)
  let added = 0
  while (added < n) {
    d.setDate(d.getDate() + 1)
    if (d.getDay() !== 0 && d.getDay() !== 6) added++
  }
  return d.toISOString().split('T')[0]
}
function addYears(isoDate, years) {
  const d = new Date(isoDate)
  d.setDate(d.getDate() + Math.round(years * 365.25))
  return d.toISOString().split('T')[0]
}
// Inverse of addYears (same 365.25-day year) — turns an absolute calendar end
// back into the tenor /api/price expects.
function yearsBetween(fromIso, toIso) {
  const days = (new Date(toIso) - new Date(fromIso)) / 86400000
  return Math.round((days / 365.25) * 1e4) / 1e4
}
// A tenor derived from a calendar rarely lands round (2.9986 years for a
// 3Y schedule) — display it rounded, price the exact value.
function fmtTenor(t) {
  return Number.isFinite(t) ? String(Math.round(t * 100) / 100) : t
}

const form = reactive({
  name: '',
  ao_date: todayIso(),
  kind: 'indicatif',
  sens: 'achat',
  source: 'template',
  template_type: '',
  script_id: null,
  source_deal_id: null,  // set instead of script_id when sourced from expertDeals
  underlying_name: 'Sous-jacent',
  underlying_ticker: '',
  currency: 'CHF',
  T: 3,
  strike_date: todayIso(),
  value_date: addBizDays(todayIso(), 2),
})

// Read-only preview of the maturity date, same rule DealTab.vue books with:
// the latest CONSTAT schedule end date if the script has one (to_trade),
// else value_date + T years.
const createMaturityDate = computed(() => {
  const ends = scriptConstats.value
    .filter(c => c.kind !== 'single')
    .map(c => constatOverrides[c.name]?.end_date)
    .filter(Boolean)
  if (ends.length) return ends.reduce((max, d) => (d > max ? d : max))
  if (!form.value_date || !form.T) return ''
  return addYears(form.value_date, form.T)
})

// "To trade" needs the precision a real Expert-mode CONSTAT calendar gives —
// currentScriptText() below switches the template wizard to expertExamples
// for this kind instead of hiding it, since every template already has a
// ready Expert version (same 16 keys as examples/templateMeta).
function onKindToggle(kind) {
  form.kind = kind
  refreshParsedParams()
}

const advanced = reactive({ sigma: 20, q: 2, r: 3, N: 20000, model: 'constant' })

function onUnderlyingSelect(ticker) {
  form.underlying_ticker = ticker
  const label = underlyingGroups.flatMap(g => g.items).find(it => it.ticker === ticker)?.label
  if (label) form.underlying_name = label
}

// ── Termes du produit + calendrier(s) CONSTAT (dynamiques, extraits du script) ──
const parsedParams = ref([])
const paramOverrides = reactive({})
const scriptConstats = ref([])
const constatOverrides = reactive({})
// Set only while duplicating an existing RFQ: the frozen snapshot overrides
// whatever form.template_type/script_id would otherwise resolve to, so a
// duplicate always reproduces the exact script that was actually quoted.
const duplicateSourceScript = ref(null)

function currentScriptText() {
  if (duplicateSourceScript.value) return duplicateSourceScript.value
  if (form.source === 'template') {
    const lib = form.kind === 'to_trade' ? expertExamples : examples
    return lib[form.template_type] || ''
  }
  return scripts.value.find(x => x.id === form.script_id)?.script_text || ''
}

async function refreshParsedParams(overrideValues = null, overrideConstats = null) {
  const script = currentScriptText()
  Object.keys(paramOverrides).forEach(k => delete paramOverrides[k])
  if (!script.trim()) { parsedParams.value = []; scriptConstats.value = []; return }
  try {
    const res = await fetch('/api/parse', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ script }),
    })
    const data = await res.json()
    parsedParams.value = data.ok ? data.params : []
    for (const p of parsedParams.value) {
      const ov = overrideValues && (p.name in overrideValues) ? overrideValues[p.name] : null
      paramOverrides[p.name] = ov !== null ? (p.is_pct ? ov * 100 : ov) : p.raw_default
    }
    scriptConstats.value = data.ok ? (data.constats || []) : []
    if (overrideConstats) restoreConstatOverrides(scriptConstats.value, constatOverrides, overrideConstats)
    else syncConstatOverrides(scriptConstats.value, constatOverrides)
  } catch {
    parsedParams.value = []
    scriptConstats.value = []
  }
}

function onSourceToggle(src) {
  form.source = src
  duplicateSourceScript.value = null
  refreshParsedParams()
}
function onTemplateChange() {
  duplicateSourceScript.value = null
  refreshParsedParams()
}
// The picker offers two kinds of options in one <select>: rows from the
// saved script library (form.script_id) and Expert-mode scripts frozen on
// already-booked deals (form.source_deal_id, no Script row to point at —
// the deal's snapshot is handed to duplicateSourceScript instead, same
// override currentScriptText() already uses for RFQ duplication).
const librarySelectValue = computed(() => {
  if (form.script_id) return `script:${form.script_id}`
  if (form.source_deal_id) return `deal:${form.source_deal_id}`
  return ''
})
function onLibrarySelect(value) {
  duplicateSourceScript.value = null
  form.script_id = null
  form.source_deal_id = null
  if (value.startsWith('script:')) {
    form.script_id = Number(value.slice(7))
  } else if (value.startsWith('deal:')) {
    const dealId = Number(value.slice(5))
    form.source_deal_id = dealId
    duplicateSourceScript.value = dealsForScripts.value.find(d => d.id === dealId)?.script_snapshot || null
  }
  refreshParsedParams()
}

// ── Nominal formatting (séparateur de milliers, mirror de DealTab.vue) ──
const nominalRaw = ref('1 000 000')
const nominalValue = computed(() => {
  return parseFloat(nominalRaw.value.replace(/\s/g, '').replace(',', '.')) || 0
})
function formatNominal() {
  const n = nominalValue.value
  if (n) nominalRaw.value = n.toLocaleString('fr-FR').replace(/,/g, ' ')
}
function unformatNominal(event) {
  nominalRaw.value = String(nominalValue.value || '')
  // Select on focus so typing replaces the value instead of appending to it
  // (mirror of the same fix in DealTab.vue).
  const el = event?.target
  if (el) nextTick(() => el.select())
}
formatNominal()

const quoteForm = reactive({ provider: '', customProvider: '', contact: '' })

onMounted(async () => {
  loadingList.value = true
  try {
    await Promise.all([rfq.fetchList(), rfq.fetchProviders(), fetchScripts(), fetchDealsForScripts()])
  } finally {
    loadingList.value = false
  }
})

async function fetchScripts() {
  const res = await apiFetch('/api/db/scripts')
  if (res.ok) scripts.value = await res.json()
}

async function fetchDealsForScripts() {
  const res = await apiFetch('/api/deals')
  if (res.ok) dealsForScripts.value = await res.json()
}

function openCreateForm() {
  showCreateForm.value = true
  selectedId.value = null
  rfq.current = null
  createError.value = ''
  notice.value = ''
  duplicateSourceScript.value = null
  Object.assign(form, {
    name: '', ao_date: todayIso(), kind: 'indicatif', sens: 'achat', source: 'template', template_type: '',
    script_id: null, source_deal_id: null,
    underlying_name: 'Sous-jacent', underlying_ticker: '', currency: 'CHF', T: 3,
    strike_date: todayIso(), value_date: addBizDays(todayIso(), 2),
  })
  Object.assign(advanced, { sigma: 20, q: 2, r: 3, N: 20000, model: 'constant' })
  nominalRaw.value = '1 000 000'
  parsedParams.value = []
}

// Pre-fills the create form from an existing RFQ (new tender round on the
// same product, params free to adjust before submitting as a new RFQ).
async function duplicateRfq(source) {
  showCreateForm.value = true
  selectedId.value = null
  createError.value = ''
  const p = source.params || {}
  const u = (p.underlyings && p.underlyings[0]) || {}
  Object.assign(form, {
    name: `${source.name || source.reference} (copie)`,
    ao_date: todayIso(),
    kind: source.kind || 'indicatif',
    sens: source.sens || 'achat',
    source: source.script_id ? 'script' : 'template',
    template_type: source.template_type || '',
    script_id: source.script_id || null,
    source_deal_id: null,
    underlying_name: u.name || 'Sous-jacent',
    underlying_ticker: u.ticker || '',
    currency: p.currency || 'CHF',
    T: p.T ?? 3,
    strike_date: todayIso(), value_date: addBizDays(todayIso(), 2),
  })
  Object.assign(advanced, {
    sigma: Math.round((u.sigma ?? 0.20) * 1000) / 10,
    q: Math.round((u.q ?? 0.02) * 1000) / 10,
    r: Math.round((p.r ?? 0.03) * 1000) / 10,
    N: p.N ?? 20000,
    model: p.model || 'constant',
  })
  nominalRaw.value = String(p.notional ?? 1000000)
  formatNominal()
  duplicateSourceScript.value = source.script_snapshot
  await refreshParsedParams(p.user_params || {}, p.constats || {})
}

// Promote an indicatif RFQ into a "to trade" one — same idea as duplicateRfq
// (new round, params adjustable), but the script must clear the Expert-mode
// bar: keep the source's script_id only if it's actually a CONSTAT script,
// otherwise fall back to that same product's Expert template (every
// template_type has one, see expertExamples) so the user isn't left staring
// at an empty picker.
async function convertToTrade(source) {
  showCreateForm.value = true
  selectedId.value = null
  createError.value = ''
  const p = source.params || {}
  const u = (p.underlyings && p.underlyings[0]) || {}
  const sourceScript = source.script_id && scripts.value.find(s => s.id === source.script_id)
  const keepsScriptId = sourceScript?.script_text?.includes('CONSTAT')
  Object.assign(form, {
    name: `${source.name || source.reference} (to trade)`,
    ao_date: todayIso(),
    kind: 'to_trade',
    sens: source.sens || 'achat',
    source: keepsScriptId ? 'script' : 'template',
    template_type: source.template_type || '',
    script_id: keepsScriptId ? source.script_id : null,
    source_deal_id: null,
    underlying_name: u.name || 'Sous-jacent',
    underlying_ticker: u.ticker || '',
    currency: p.currency || 'CHF',
    T: p.T ?? 3,
    strike_date: todayIso(), value_date: addBizDays(todayIso(), 2),
  })
  Object.assign(advanced, {
    sigma: Math.round((u.sigma ?? 0.20) * 1000) / 10,
    q: Math.round((u.q ?? 0.02) * 1000) / 10,
    r: Math.round((p.r ?? 0.03) * 1000) / 10,
    N: p.N ?? 20000,
    model: p.model || 'constant',
  })
  nominalRaw.value = String(p.notional ?? 1000000)
  formatNominal()
  duplicateSourceScript.value = null
  await refreshParsedParams(null, keepsScriptId ? (p.constats || {}) : null)
}

async function selectRfq(id) {
  showCreateForm.value = false
  selectedId.value = id
  computeError.value = ''
  await rfq.fetchOne(id)
  await refreshDetailParams()
}

// Editable copy of the RFQ's pricing params, shown in the detail panel's
// "Paramètres de pricing" — separate reactive state from the create form's
// (paramOverrides/constatOverrides/advanced) so editing one never bleeds
// into the other. Recalculating persists this copy back onto the RFQ (see
// computeModelPrice) rather than being a one-shot, throw-away tweak.
const detailParsedParams    = ref([])
const detailParamOverrides  = reactive({})
const detailScriptConstats  = ref([])
const detailConstatOverrides = reactive({})
const detailAdvanced = reactive({
  sigma: 20, q: 2, r: 3, N: 20000, model: 'constant',
  strike_date: todayIso(), value_date: addBizDays(todayIso(), 2),
})

async function refreshDetailParams() {
  const script = rfq.current?.script_snapshot || ''
  const p = rfq.current?.params || {}
  const u = (p.underlyings && p.underlyings[0]) || {}
  Object.assign(detailAdvanced, {
    sigma: Math.round((u.sigma ?? 0.20) * 1000) / 10,
    q: Math.round((u.q ?? 0.02) * 1000) / 10,
    r: Math.round((p.r ?? 0.03) * 1000) / 10,
    N: p.N ?? 20000,
    model: p.model || 'constant',
    strike_date: p.strike_date || todayIso(),
    value_date: p.value_date || addBizDays(todayIso(), 2),
  })
  Object.keys(detailParamOverrides).forEach(k => delete detailParamOverrides[k])
  if (!script.trim()) { detailParsedParams.value = []; detailScriptConstats.value = []; return }
  try {
    const res = await fetch('/api/parse', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ script }),
    })
    const data = await res.json()
    detailParsedParams.value = data.ok ? data.params : []
    const savedParams = p.user_params || {}
    for (const pp of detailParsedParams.value) {
      const ov = pp.name in savedParams ? savedParams[pp.name] : null
      detailParamOverrides[pp.name] = ov !== null ? (pp.is_pct ? ov * 100 : ov) : pp.raw_default
    }
    detailScriptConstats.value = data.ok ? (data.constats || []) : []
    restoreConstatOverrides(detailScriptConstats.value, detailConstatOverrides, p.constats || {})
  } catch {
    detailParsedParams.value = []
    detailScriptConstats.value = []
  }
}

// ── Filtres de la liste d'AO ────────────────────────────────────────────
// Même mécanisme que l'onglet Deals du Booking (composables/useDataFilter).
// Les libellés des selects passent par les mêmes fonctions que les badges de
// la liste, sinon on filtrerait sur « clos » en lisant « Bookée » à l'écran.
const rfqFilterFields = [
  { key: 'q', label: 'Nom / référence', kind: 'text', width: 'w-full',
    get: r => [r.name, r.reference, r.template_type] },
  { key: 'status', label: 'Statut', kind: 'select', optionLabel: statusLabel },
  { key: 'kind', label: 'Type', kind: 'select', optionLabel: kindLabel },
  { key: 'sens', label: 'Sens', kind: 'select', optionLabel: sensLabel },
]
// Pas de filtre par fournisseur ici : GET /api/rfq ne renvoie pas les
// cotations (elles n'arrivent qu'avec le détail), le select serait vide.
// C'est l'écran Analyse qui porte la lecture par banque.

const rfqSorts = [
  { key: 'ao_date', label: 'Date d\'AO' },
  { key: 'name', label: 'Nom' },
  { key: 'reference', label: 'Référence' },
  { key: 'status', label: 'Statut' },
  { key: 'model_price', label: 'Prix modèle' },
]

const rfqList = computed(() => rfq.list)
const rfqFilter = useDataFilter(rfqList, rfqFilterFields, { sorts: rfqSorts })
const filteredRfqs = computed(() => rfqFilter.filtered.value)

const underlyingSummary = computed(() => (rfq.current?.params?.underlyings || [])[0] || {})

// Même source que le "📡 Yahoo" du Pricer (pricing.js:loadYfOne) : vol
// réalisée 1 an et rendement du dividende. Saisir ces deux nombres à la main
// dans une RFQ alors que le sous-jacent est renseigné n'a pas de sens — et
// une vol tapée de mémoire fait un prix modèle dont l'écart aux cotations ne
// veut plus rien dire.
const createYfStatus  = ref('')
const createYfLoading = ref(false)
const detailYfStatus  = ref('')
const detailYfLoading = ref(false)

async function _loadUnderlyingParams(ticker, target, status, loading) {
  const tk = (ticker || '').trim().toUpperCase()
  if (!tk) { status.value = '⚠ Aucun ticker de sous-jacent'; return }
  loading.value = true
  status.value = `Chargement ${tk}…`
  try {
    const res = await fetch(`/api/finance/hist_vol?tickers=${encodeURIComponent(tk)}&period=1y`)
    const data = await res.json()
    if (data.error) { status.value = `⚠ ${tk} : ${data.error}`; return }
    const vol = data.vols?.[tk] ?? null
    if (vol == null) {
      status.value = `⚠ ${tk} : introuvable sur Yahoo Finance`
      if (data.missing?.includes(tk)) status.value += ' — vérifiez le ticker'
      return
    }
    const q = data.div_yields?.[tk] ?? 0
    target.sigma = Math.round(vol * 1000) / 10
    target.q = Math.round(q * 10000) / 100
    status.value = `✓ ${tk} — σ=${(vol * 100).toFixed(1)}%, q=${(q * 100).toFixed(2)}% · ${data.n_obs} obs.`
  } catch (e) {
    status.value = '⚠ Erreur réseau : ' + e.message
  } finally {
    loading.value = false
  }
}

function loadCreateUnderlyingParams() {
  return _loadUnderlyingParams(form.underlying_ticker, advanced, createYfStatus, createYfLoading)
}
function loadDetailUnderlyingParams() {
  return _loadUnderlyingParams(underlyingSummary.value.ticker, detailAdvanced,
                               detailYfStatus, detailYfLoading)
}

// Latest CONSTAT schedule end date — empty when the script has no calendar
// at all (simple-mode indicatif), which is what tells the tenor derivation
// below whether there is a real maturity date to price against.
const detailCalendarEnd = computed(() => {
  const ends = detailScriptConstats.value
    .filter(c => c.kind !== 'single')
    .map(c => detailConstatOverrides[c.name]?.end_date)
    .filter(Boolean)
  return ends.length ? ends.reduce((max, d) => (d > max ? d : max)) : ''
})

// Same derivation rule as createMaturityDate/DealTab.vue: latest CONSTAT
// schedule end date when the script has one, else value_date + T years.
const detailMaturityDate = computed(() => {
  if (detailCalendarEnd.value) return detailCalendarEnd.value
  const p = rfq.current?.params || {}
  if (!p.value_date || !p.T) return ''
  return addYears(p.value_date, p.T)
})

const fmtNominal = formatInt

async function submitCreate() {
  createError.value = ''
  if (!form.name.trim()) { createError.value = 'Le nom est requis'; return }
  if (form.source === 'template' && !form.template_type && !duplicateSourceScript.value) {
    createError.value = 'Choisissez un template'; return
  }
  if (form.source === 'script' && !form.script_id && !form.source_deal_id && !duplicateSourceScript.value) {
    createError.value = 'Choisissez un script'; return
  }
  const script_snapshot = currentScriptText()
  if (form.kind === 'to_trade' && !script_snapshot.includes('CONSTAT')) {
    createError.value = "Une RFQ 'to trade' doit utiliser un script en mode Expert (calendrier CONSTAT réel) — choisissez-le ci-dessus."
    return
  }

  const user_params = {}
  for (const p of parsedParams.value) {
    const v = paramOverrides[p.name] ?? p.raw_default
    user_params[p.name] = p.is_pct ? v / 100 : v
  }

  creating.value = true
  try {
    const rfqObj = await rfq.create({
      name: form.name,
      ao_date: form.ao_date,
      kind: form.kind,
      sens: form.sens,
      template_type: form.source === 'template' ? form.template_type : '',
      script_id: form.source === 'script' ? form.script_id : null,
      script_snapshot,
      params: {
        underlyings: [{
          name: form.underlying_name, ticker: form.underlying_ticker,
          ccy: form.currency, sigma: advanced.sigma / 100, q: advanced.q / 100,
        }],
        corr_matrix: [[1]],
        r: advanced.r / 100, T: form.T, N: advanced.N, model: advanced.model,
        user_params,
        constats: buildConstatsPayload(scriptConstats.value, constatOverrides),
        notional: nominalValue.value, currency: form.currency,
        strike_date: form.strike_date, value_date: form.value_date,
      },
    })
    showCreateForm.value = false
    await selectRfq(rfqObj.id)
    notice.value = 'RFQ créée'
  } catch (e) {
    createError.value = e.message
  } finally {
    creating.value = false
  }
}

// The only status the desk poses by hand: an AO that led nowhere. "auto"
// hands the RFQ back to the server-side derivation, which puts it at the
// stage its quotes actually justify (see api/rfq.py _derive_status).
async function toggleSansSuite() {
  listError.value = ''
  try {
    await rfq.update(rfq.current.id, {
      status: rfq.current.status === 'sans_suite' ? 'auto' : 'sans_suite',
    })
  } catch (e) {
    listError.value = e.message || 'Erreur mise à jour du statut'
  }
}

// Custom confirmation modal (BaseModal) instead of the native confirm() —
// no more disorienting native-browser flash, matches the app's own dialogs.
const showDeleteConfirm = ref(false)
const deleteTargetId    = ref(null)
const deleteTargetLabel = computed(() => {
  const r = rfq.list.find(x => x.id === deleteTargetId.value)
  return r?.name || r?.reference || `#${deleteTargetId.value}`
})

function deleteRfq(id) {
  deleteTargetId.value = id
  showDeleteConfirm.value = true
}

async function confirmDeleteRfq() {
  const id = deleteTargetId.value
  showDeleteConfirm.value = false
  listError.value = ''
  notice.value = ''
  try {
    await rfq.remove(id)
    if (selectedId.value === id) selectedId.value = null
    notice.value = 'RFQ supprimée'
  } catch (e) {
    listError.value = e.message || 'Erreur suppression'
  }
}

async function computeModelPrice() {
  computing.value = true
  computeError.value = ''
  try {
    // Persist the (possibly just-edited) params before pricing with them —
    // "Calculer prix modèle" always reflects what's currently in the form
    // above, not the values frozen at creation time.
    const user_params = {}
    for (const pp of detailParsedParams.value) {
      const v = detailParamOverrides[pp.name] ?? pp.raw_default
      user_params[pp.name] = pp.is_pct ? v / 100 : v
    }
    // The panel displays the CONSTAT calendar end as the maturity, so that's
    // the tenor to price. Left at the T typed at creation, AT_MATURITY fires
    // on a date the RFQ never shows (2Y calendar with T=3 → redemption
    // simulated at 3 years: effective_T_max only ever extends the horizon,
    // never shortens it). No calendar (simple-mode indicatif) → T stays the
    // tenor and the dates are metadata, nothing to derive.
    let T = rfq.current.params?.T ?? 3
    if (detailCalendarEnd.value) {
      T = yearsBetween(detailAdvanced.value_date, detailCalendarEnd.value)
      if (!(T > 0)) {
        throw new Error(`La fin de calendrier (${detailCalendarEnd.value}) précède la date de `
                      + `valeur (${detailAdvanced.value_date}) — corrigez les dates avant de calculer.`)
      }
    }
    const existingUnderlying = (rfq.current.params?.underlyings || [])[0] || {}
    const mergedParams = {
      ...rfq.current.params,
      T,
      underlyings: [{ ...existingUnderlying, sigma: detailAdvanced.sigma / 100, q: detailAdvanced.q / 100 }],
      r: detailAdvanced.r / 100,
      N: detailAdvanced.N,
      model: detailAdvanced.model,
      user_params,
      constats: buildConstatsPayload(detailScriptConstats.value, detailConstatOverrides),
      strike_date: detailAdvanced.strike_date,
      value_date: detailAdvanced.value_date,
    }
    await rfq.update(rfq.current.id, { params: mergedParams })
    await rfq.computeModelPrice(rfq.current)
  } catch (e) {
    computeError.value = e.message
  } finally {
    computing.value = false
  }
}

function openAddQuote() {
  quoteForm.provider = rfq.providers[0]?.label || 'autre'
  quoteForm.customProvider = ''
  quoteForm.contact = ''
  addingQuote.value = true
}

async function submitAddQuote() {
  const provider = quoteForm.provider === 'autre' ? (quoteForm.customProvider.trim() || 'Autre') : quoteForm.provider
  await rfq.addQuote(rfq.current.id, { provider, contact: quoteForm.contact || null })
  addingQuote.value = false
}

async function removeQuote(quoteId) {
  await rfq.removeQuote(rfq.current.id, quoteId)
}

function updateQuoteField(q, field, value) {
  rfq.updateQuote(rfq.current.id, q.id, { [field]: value })
}

function onQuotePriceChange(q, value) {
  const price = value === '' ? null : Number(value)
  const payload = { price }
  // First time a price is entered, log the response as received now unless
  // a date was already set explicitly.
  if (price !== null && !q.quoted_at) payload.quoted_at = new Date().toISOString()
  rfq.updateQuote(rfq.current.id, q.id, payload)
}

function onQuoteDateChange(q, value) {
  rfq.updateQuote(rfq.current.id, q.id, { quoted_at: value ? new Date(value).toISOString() : null })
}

function onQuoteValidityChange(q, value) {
  rfq.updateQuote(rfq.current.id, q.id, { valid_until: value ? new Date(value).toISOString() : null })
}

// <input type="datetime-local"> expects "YYYY-MM-DDTHH:mm" in local time.
function toDatetimeLocal(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  const pad = n => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

const fmtDateOnly = formatDate

function providerLabel(id) {
  return rfq.providers.find(p => p.id === id)?.label || id
}

function fmtPrice(v) {
  return formatPercent(v)
}

const fmtDate = formatDateTime

// Écart de la cotation au prix modèle, signé de NOTRE côté : positif = en
// notre faveur. À l'achat la bonne réponse est celle qui cote SOUS le prix
// modèle (on paie moins), à la vente celle qui cote au-dessus. Miroir exact
// de _edge_bps côté backend (api/rfq.py), sur lequel la vue Analyse agrège.
function edgeBps(q) {
  const model = rfq.current?.model_price
  if (q.price === null || q.price === undefined || !model) return null
  const diff = rfq.current?.sens === 'vente' ? (q.price - model) : (model - q.price)
  return diff / model * 10000
}

function spreadBps(q) {
  const e = edgeBps(q)
  if (e === null) return '—'
  return (e >= 0 ? '+' : '') + formatBps(e, 0)
}

function spreadClass(q) {
  const e = edgeBps(q)
  if (e === null) return 'text-slate-600'
  return e >= 0 ? 'text-green-400' : 'text-red-400'
}

// Statuts déduits côté serveur du déroulé de l'AO (api/rfq.py
// _derive_status) — sauf « Bookée » (posé au booking) et « Sans suite »
// (posé à la main : AO abandonné ou perdu).
const STATUS_LABELS = { draft: 'Brouillon', envoye: 'Envoyée', quote: 'Cotée', retenue: 'Retenue', clos: 'Bookée', sans_suite: 'Sans suite' }
const STATUS_BADGES = {
  draft:      'bg-slate-800 text-slate-400 border-slate-700',
  sans_suite: 'bg-red-900/40 text-red-300 border-red-900',
  envoye:  'bg-blue-900/50 text-blue-300 border-blue-800',
  quote:   'bg-green-900/50 text-green-400 border-green-800',
  retenue: 'bg-amber-900/50 text-amber-300 border-amber-800',
  clos:    'bg-slate-800 text-slate-500 border-slate-700',
}
function statusLabel(s) { return STATUS_LABELS[s] || s }
function statusBadge(s) { return STATUS_BADGES[s] || STATUS_BADGES.draft }

const KIND_LABELS = { indicatif: 'Indicatif', to_trade: 'To trade' }
const KIND_BADGES = {
  indicatif: 'bg-slate-800 text-slate-400 border-slate-700',
  to_trade:  'bg-amber-900/40 text-amber-300 border-amber-800',
}
function kindLabel(k) { return KIND_LABELS[k] || KIND_LABELS.indicatif }
function kindBadge(k) { return KIND_BADGES[k] || KIND_BADGES.indicatif }

// Notre côté du trade, pas celui de la contrepartie — attention, Deal.sens
// suit la convention INVERSE ("Vente (banque vend)" = nous achetons), d'où
// l'inversion au moment de préremplir le booking (pricing.js:loadFromRfq).
const SENS_LABELS = { achat: '↓ Achat', vente: '↑ Vente' }
const SENS_BADGES = {
  achat: 'bg-emerald-900/40 text-emerald-300 border-emerald-800',
  vente: 'bg-blue-900/40 text-blue-300 border-blue-800',
}
function sensLabel(s) { return SENS_LABELS[s] || SENS_LABELS.achat }
function sensBadge(s) { return SENS_BADGES[s] || SENS_BADGES.achat }
function sensHint(s) {
  return s === 'vente'
    ? 'Nous vendons le produit : la meilleure réponse est le prix le PLUS HAUT (on encaisse davantage).'
    : 'Nous achetons le produit aux fournisseurs : la meilleure réponse est le prix le PLUS BAS (on paie moins).'
}

async function updateSens(value) {
  await rfq.update(rfq.current.id, { sens: value })
}

// ── Last look ─────────────────────────────────────────────────────────
const lastLookError = ref('')

// The best competing price to date — the reference an existing responder is
// invited to match (or the desk uses to judge "close enough, give them the
// deal at their own price"). Which extreme wins depends on our side of the
// trade: cheapest when we buy, richest when we sell. Assuming the latter
// unconditionally (the previous behaviour) designates the WORST offer as best
// on a buy tender — this module's normal direction.
const bestQuote = computed(() => {
  const priced = (rfq.current?.quotes || []).filter(q => q.price !== null && q.price !== undefined)
  if (!priced.length) return null
  const selling = rfq.current?.sens === 'vente'
  return priced.reduce((best, q) =>
    (selling ? q.price > best.price : q.price < best.price) ? q : best)
})

async function onLastLookToggle(q, value) {
  lastLookError.value = ''
  try {
    await rfq.toggleLastLook(rfq.current.id, q.id, value)
  } catch (e) {
    lastLookError.value = e.message
  }
}

async function onSelectQuote(q) {
  const alreadySelected = rfq.current.selected_quote_id === q.id
  await rfq.selectQuote(rfq.current.id, alreadySelected ? null : q.id)
}

function bookFromRfq() {
  router.push({ path: '/pricer', query: { fromRfq: rfq.current.id } })
}

// Deep link vers la fiche du deal dans la liste des deals bookés
// (BookingView lit ?deal=<id> et ouvre le détail directement).
function openBookedDeal() {
  router.push({ path: '/booking', query: { deal: rfq.current.booked_deal.id } })
}
</script>
