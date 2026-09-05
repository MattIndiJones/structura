<template>
  <div class="flex-1 flex flex-col min-h-0 overflow-hidden">

    <div class="page-header px-6 pt-6 pb-0 mb-0">
      <div class="flex items-center gap-3">
        <BackLink :fallback="{ path: '/', query: { category: 'competitive_bidding' } }" />
        <h1 class="page-title">RFQ Fournisseurs</h1>
      </div>
      <div class="page-actions">
        <RouterLink to="/rfq/analyse" class="btn-ghost btn-sm">📈 Analyse</RouterLink>
        <button class="btn-primary text-xs px-3 py-1.5" @click="openCreateForm">+ Nouvelle RFQ</button>
      </div>
    </div>
    <!-- Contexte commercial, quand on arrive depuis une fiche d'opportunité.
         L'appel d'offres créé ici portera le lien, ce qui permettra plus tard
         de remonter du trade jusqu'au client et à la personne qui l'a porté. -->
    <AlertMessage v-if="opportuniteContexte" kind="info" class="mx-6 mt-3">
      <div class="flex items-center justify-between gap-3 flex-wrap">
        <span>
          Appel d'offres pour
          <span class="font-semibold">{{ opportuniteContexte.title || opportuniteContexte.reference }}</span>
          — {{ opportuniteContexte.client_name }}
          <template v-if="opportuniteContexte.mandate?.name">
            · {{ opportuniteContexte.mandate.name }}
          </template>.
          La RFQ créée restera rattachée à cette opportunité.
        </span>
        <RouterLink :to="`/clients/opportunites/${opportuniteContexte.id}`"
                    class="btn-ghost btn-sm shrink-0">Revenir au dossier</RouterLink>
      </div>
    </AlertMessage>
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
        <div v-if="showCreateForm" class="flex flex-col gap-4 max-w-2xl xl:max-w-[1500px]">
          <!-- Le titre ET les actions dans un bandeau collé en haut.
               Choisir un template ajoute les termes du produit et le calendrier
               CONSTAT — près de 400 px — et le bouton « Créer » descendait
               d'autant, sous le curseur de qui venait de choisir. Placé en bas,
               même collant, il bougeait encore entre un formulaire court et un
               formulaire long. En haut, il ne dépend plus du contenu du tout —
               c'est déjà où le Pricer met son action principale. -->
          <div class="sticky top-0 z-20 -mx-6 -mt-6 px-6 py-3 mb-1 flex items-center gap-3 flex-wrap border-b"
               style="background: rgba(250,249,246,.94); backdrop-filter: blur(10px);
                      border-color: var(--border); box-shadow: 0 4px 14px rgba(11,26,49,.04);">
            <h2 class="text-sm font-bold text-slate-300 uppercase tracking-wider">Nouvelle RFQ</h2>
            <span v-if="champsManquants.length" class="text-[11px] text-amber-600">
              À compléter : {{ champsManquants.join(', ') }}
            </span>
            <div class="ml-auto flex gap-2">
              <button class="btn-secondary text-sm" @click="showCreateForm = false">Annuler</button>
              <button class="btn-primary text-sm" :disabled="creating" @click="submitCreate">
                {{ creating ? 'Création…' : 'Créer la RFQ' }}
              </button>
            </div>
          </div>

          <AlertMessage v-if="createError" kind="error">{{ createError }}</AlertMessage>

          <!-- Deux colonnes dès qu'il y a la place : à gauche ce qu'on
               demande et à qui, à droite le produit qu'on fait pricer. -->
          <div class="grid grid-cols-1 xl:grid-cols-2 gap-4 items-start">
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

              <div class="grid grid-cols-2 gap-3">
                <div class="flex flex-col gap-1">
                  <label class="label">Format juridique</label>
                  <input v-model="form.transaction_format" class="input" list="rfq-formats"
                         placeholder="EMTN, BMTN, OTC…" />
                  <datalist id="rfq-formats">
                    <option value="EMTN" /><option value="BMTN" /><option value="OTC" />
                  </datalist>
                </div>
                <div class="flex flex-col gap-1">
                  <label class="label">Instrument</label>
                  <input v-model="form.instrument_family" class="input" list="rfq-instruments"
                         placeholder="Note, Swap…" />
                  <datalist id="rfq-instruments">
                    <option value="Note" /><option value="Certificat" />
                    <option value="Swap" /><option value="Option" />
                  </datalist>
                </div>
                <div class="flex flex-col gap-1">
                  <label class="label">Famille de payoff</label>
                  <input v-model="form.payoff_family" class="input"
                         placeholder="Phoenix, Autocall…" />
                </div>
                <div class="flex flex-col gap-1">
                  <label class="label">Référence documentaire</label>
                  <input v-model="form.documentation_reference" class="input"
                         placeholder="Term sheet / ISDA / confirmation" />
                </div>
                <div class="col-span-2 flex flex-col gap-1">
                  <label class="label">Description du payoff</label>
                  <textarea v-model="form.payoff_description" class="input" rows="2"
                            placeholder="Précisions propres à cette RFQ"></textarea>
                </div>
              </div>

              <div v-if="!opportuniteContexte" class="rounded-lg border p-3 flex flex-col gap-3"
                   style="border-color: var(--border); background: var(--surface2)">
                <div class="flex items-center justify-between gap-3">
                  <div>
                    <div class="text-xs font-semibold">Contexte Client facultatif</div>
                    <p class="text-[10px] mt-0.5" style="color: var(--subtle)">
                      Laissez désactivé pour une RFQ Produit autonome.
                    </p>
                  </div>
                  <button class="btn-ghost btn-sm" @click="toggleDirectCommercial">
                    {{ commercialLinkEnabled ? 'Retirer le contexte' : 'Rattacher à un Client' }}
                  </button>
                </div>
                <div v-if="commercialLinkEnabled" class="grid grid-cols-2 gap-2">
                  <div class="col-span-2">
                    <label class="label">Client</label>
                    <select v-model="form.client_id" class="select" @change="onDirectClientChange">
                      <option :value="null">— Choisir —</option>
                      <option v-for="client in directClients" :key="client.id" :value="client.id">
                        {{ client.name }}
                      </option>
                    </select>
                  </div>
                  <div>
                    <label class="label">Mandat / périmètre</label>
                    <select v-model="form.mandate_id" class="select" :disabled="!form.client_id">
                      <option :value="null">— Obligatoire —</option>
                      <option v-for="mandat in directMandates" :key="mandat.id" :value="mandat.id">
                        {{ mandat.name }}
                      </option>
                    </select>
                  </div>
                  <div>
                    <label class="label">Opportunity éventuelle</label>
                    <select v-model="form.opportunity_id" class="select"
                            :disabled="!form.client_id" @change="onDirectOpportunityChange">
                      <option :value="null">— Aucune —</option>
                      <option v-for="opp in directOpportunities" :key="opp.id" :value="opp.id">
                        {{ opp.title || opp.reference }}
                      </option>
                    </select>
                  </div>
                  <div class="col-span-2">
                    <label class="label">Contact principal éventuel</label>
                    <select v-model="form.primary_affiliation_id" class="select"
                            :disabled="!form.client_id">
                      <option :value="null">— Aucun —</option>
                      <option v-for="contact in directContacts" :key="contact.affiliation_id"
                              :value="contact.affiliation_id">
                        {{ contact.first_name }} {{ contact.last_name }}
                      </option>
                    </select>
                  </div>
                </div>
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

            </div>

            <div class="card flex flex-col gap-3">
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
                  <label class="label"
                         title="Date de constatation du niveau initial du ou des sous-jacents. C'est là que démarre la diffusion Monte Carlo.">Date de strike *</label>
                  <input v-model="form.strike_date" type="date" class="input"
                         @change="resolveFormDate('strike_date')" />
                  <select v-model="form.strike_date_convention" class="select py-1 text-[11px]"
                          title="Ce que devient cette date si elle tombe un week-end ou un jour férié du calendrier de la devise."
                          @change="resolveFormDate('strike_date')">
                    <option value="none">Aucun ajustement</option>
                    <option value="following">Jour ouvré suivant</option>
                    <option value="modified_following">Suivant, sauf changement de mois</option>
                    <option value="preceding">Jour ouvré précédent</option>
                    <option value="modified_preceding">Précédent, sauf changement de mois</option>
                  </select>
                  <span v-if="dateNotices.strike_date" class="text-[10px] text-amber-500">{{ dateNotices.strike_date }}</span>
                </div>
                <div class="flex flex-col gap-1">
                  <label class="label"
                         title="Date d'échange du cash entre contreparties. Le prix coté est le montant qui bouge ce jour-là. Elle peut précéder la date de strike (forward start).">Date de valeur *</label>
                  <input v-model="form.value_date" type="date" class="input"
                         @change="resolveFormDate('value_date')" />
                  <select v-model="form.value_date_convention" class="select py-1 text-[11px]"
                          title="Ce que devient cette date si elle tombe un week-end ou un jour férié du calendrier de la devise."
                          @change="resolveFormDate('value_date')">
                    <option value="none">Aucun ajustement</option>
                    <option value="following">Jour ouvré suivant</option>
                    <option value="modified_following">Suivant, sauf changement de mois</option>
                    <option value="preceding">Jour ouvré précédent</option>
                    <option value="modified_preceding">Précédent, sauf changement de mois</option>
                  </select>
                  <span v-if="dateNotices.value_date" class="text-[10px] text-amber-500">{{ dateNotices.value_date }}</span>
                </div>
                <div class="flex flex-col gap-1">
                  <label class="label">Date de maturité</label>
                  <input :value="createMaturityDate" type="date" readonly
                         class="input bg-slate-800/40 text-slate-500 cursor-not-allowed" />
                </div>
                <div class="flex flex-col gap-1">
                  <label class="label"
                         title="Échange final des flux de cash. Proposée à trois jours ouvrés après la dernière constatation — modifiable, c'est le term sheet qui tranche.">Date de paiement *</label>
                  <input v-model="form.payment_date" type="date" class="input"
                         @change="paymentDateSaisie = true; resolveFormDate('payment_date')" />
                  <select v-model="form.payment_date_convention" class="select py-1 text-[11px]"
                          title="Ce que devient cette date si elle tombe un week-end ou un jour férié du calendrier de la devise."
                          @change="resolveFormDate('payment_date')">
                    <option value="none">Aucun ajustement</option>
                    <option value="following">Jour ouvré suivant</option>
                    <option value="modified_following">Suivant, sauf changement de mois</option>
                    <option value="preceding">Jour ouvré précédent</option>
                    <option value="modified_preceding">Précédent, sauf changement de mois</option>
                  </select>
                  <span v-if="dateNotices.payment_date" class="text-[10px] text-amber-500">{{ dateNotices.payment_date }}</span>
                </div>
              </div>

              <!-- Termes du produit + calendrier(s) CONSTAT (dynamiques, extraits du script) -->
              <div v-if="parsedParams.length || scriptConstats.length" class="border-t border-slate-800 pt-3">
                <RfqParamsEditor :parsed-params="parsedParams" :param-overrides="paramOverrides"
                                 :constats="scriptConstats" :constat-overrides="constatOverrides"
                                 :currency="form.currency" />
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

                <!-- Les mêmes cartes que Marché & Paramètres, dans le MÊME ORDRE,
                     sur l'état de l'AO. Elles acceptent leur courbe en prop et retombent sur
                     le Pricer quand on ne leur en donne pas : une seule
                     implémentation, deux écrans, aucun état partagé. -->
                <div class="flex flex-col gap-3 mt-3 pt-3 border-t border-slate-800">
                  <DividendCurveCard :sous-jacents="ao.panier" :index-actif="0"
                                     :horizon="form.T" />
                  <YieldCurveCard :courbe="ao.yieldCurve" :taux-plat="advanced.r" />
                  <FundingCurveCard :courbe="ao.fundingCurve" />
                </div>
              </details>
            </div>
          </div>

        </div>

        <!-- Détail RFQ -->
        <div v-else-if="rfq.current" class="flex flex-col gap-4 max-w-[1900px]">
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
          <div v-if="rfq.current.commercial_context || rfq.current.transaction_format
                     || rfq.current.instrument_family || rfq.current.payoff_family"
               class="card py-2.5 px-3 flex items-center gap-2 flex-wrap text-xs">
            <span v-if="rfq.current.commercial_context?.client" class="badge badge-accent">
              Client · {{ rfq.current.commercial_context.client.name }}
            </span>
            <span v-if="rfq.current.commercial_context?.mandate" class="badge badge-muted">
              Mandat · {{ rfq.current.commercial_context.mandate.name }}
            </span>
            <span v-if="rfq.current.transaction_format" class="badge badge-muted">
              {{ rfq.current.transaction_format }}
            </span>
            <span v-if="rfq.current.instrument_family" class="badge badge-muted">
              {{ rfq.current.instrument_family }}
            </span>
            <span v-if="rfq.current.payoff_family" class="badge badge-muted">
              {{ rfq.current.payoff_family }}
            </span>
          </div>

          <!-- Deux colonnes figées : à gauche tout l'AO (produit, prix,
               script, cotations), à droite le contrôle du prix. La grille ne
               dépend QUE de la largeur de fenêtre, jamais de l'état des
               données — la colonne de gauche a la même largeur avant et après
               un pricing, rien ne se réagence quand le prix arrive.

               1650 px : en-dessous, la colonne de gauche descendrait sous
               700 px utiles une fois les 560 px du panneau retirés (plus la
               liste des AO et les marges) — on empile alors plutôt que de
               rendre les deux colonnes illisibles. 560 px, c'est la largeur
               qu'exige la table des flux pour ne pas défiler. -->
          <div class="flex flex-col gap-4 min-[1650px]:grid min-[1650px]:grid-cols-[minmax(0,1fr)_560px] min-[1650px]:items-start">
            <div class="flex flex-col gap-4 min-w-0">
              <!-- ── L'état de l'écran par rapport à la BASE ────────────
                   Les termes saisis dans « Paramètres de pricing » ne vivent
                   qu'en mémoire : « Calculer prix modèle » n'envoie que les
                   hypothèses de modèle, jamais les termes. Le seul bouton qui
                   les persistait vivait à l'INTÉRIEUR du bloc replié — modifier
                   une date puis quitter la perdait sans un mot, et l'écran
                   continuait d'afficher une valeur que la base n'avait pas.

                   Rendue TOUJOURS visible, et pas seulement en cas d'écart :
                   une barre qui n'apparaît qu'au moment du problème ne se
                   cherche pas, elle se remarque — ou pas. Là, la question
                   « est-ce que ce que je vois est en base ? » a une réponse
                   affichée en permanence, sans rien déplier. -->
              <div class="card flex flex-wrap items-center gap-3"
                   :class="detailTermsDirty ? 'border-amber-600/50 bg-amber-900/10' : ''">
                <span class="text-xs font-semibold"
                      :class="detailTermsDirty ? 'text-amber-400' : 'text-emerald-500'">
                  {{ detailTermsDirty ? '⚠ Modifications non enregistrées' : '✓ Écran conforme à la base' }}
                </span>
                <span class="text-[11px] flex-1 min-w-40"
                      :class="detailTermsDirty ? 'text-slate-400' : 'text-slate-600'">
                  {{ detailTermsDirty
                    ? 'Ce qui est affiché ne correspond pas à la base. Quitter cette page le perd.'
                    : 'Les termes affichés sont ceux enregistrés.' }}
                </span>
                <button type="button" class="btn-primary text-xs px-3 py-1.5 shrink-0"
                        :disabled="!detailTermsDirty || savingTerms"
                        title="Écrit les termes contractuels de l'AO en base. Refusé par le serveur si une cotation existe déjà — ils sont alors figés."
                        @click="saveDetailTerms">
                  {{ savingTerms ? 'Enregistrement…' : '💾 Enregistrer les termes' }}
                </button>
                <button type="button" class="text-[11px] underline shrink-0"
                        :class="detailTermsDirty ? 'text-slate-400 hover:text-slate-200' : 'text-slate-600 hover:text-slate-400'"
                        title="Recharger les termes tels qu'ils sont enregistrés en base"
                        @click="refreshDetailParams">
                  {{ detailTermsDirty ? 'Abandonner' : 'Recharger' }}
                </button>
              </div>
              <AlertMessage v-if="termsError" kind="error" dismissible @dismiss="termsError = ''">{{ termsError }}</AlertMessage>

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
                <!-- La date de paiement est un terme CONTRACTUEL, gelé comme le
                     strike et la maturité. La cacher dans « paramètres de
                     pricing (modifiables) », parmi les hypothèses de modèle, a
                     produit un AO réglé trois ans avant son échéance sans que
                     rien ne se voie. Sa place est ici, avec les trois autres. -->
                <div>
                  <div class="label mb-0.5">Date de paiement</div>
                  <div class="text-xs" :class="reglementIncoherent ? 'text-red-400 font-semibold' : 'text-slate-200'">
                    {{ fmtDateOnly(rfq.current.params?.payment_date) || '—' }}
                    <span v-if="reglementIncoherent" :title="`Le règlement précède la maturité du ${fmtDateOnly(detailMaturityDate)}`">⚠</span>
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
                    <!-- Ligne toujours rendue : sans elle, la tuile gagnait un cran
                         de hauteur au premier calcul et tout le bloc sautait. -->
                    <div class="text-[10px] text-slate-600 mt-0.5">
                      {{ rfq.current.model_price_at ? 'Calculé le ' + fmtDate(rfq.current.model_price_at) : 'Pas encore calculé' }}
                    </div>
                  </div>
                  <!-- Les deux libellés partagent la même cellule de grille : le
                       bouton se dimensionne sur le plus long et ne bouge plus en
                       passant à « Calcul… ». Une largeur en dur serait à refaire à
                       chaque changement de libellé ou de police. -->
                  <button class="btn-secondary text-xs grid shrink-0" :disabled="computing || !!rfq.current.booked_deal" @click="computeModelPrice">
                    <span class="col-start-1 row-start-1" :class="computing ? 'invisible' : ''">Calculer prix modèle</span>
                    <span class="col-start-1 row-start-1" :class="computing ? '' : 'invisible'">Calcul…</span>
                  </button>
                </div>

                <details class="border-t border-slate-800 pt-3">
                  <summary class="label mb-0 cursor-pointer select-none">▸ Paramètres de pricing (modifiables)</summary>
                  <div class="mt-2 flex flex-col gap-3">
                    <fieldset :disabled="!!rfq.current.quotes?.length">
                      <RfqParamsEditor :parsed-params="detailParsedParams" :param-overrides="detailParamOverrides"
                                       :constats="detailScriptConstats" :constat-overrides="detailConstatOverrides"
                                       :currency="rfq.current.params?.currency || 'EUR'" />
                    </fieldset>

                    <!-- L'éditeur ci-dessus ne vivait qu'en mémoire : le calcul du
                         prix n'envoie que les hypothèses de modèle, jamais les
                         termes. Un échéancier modifié se perdait donc au premier
                         rechargement de l'AO. Cette barre est le seul chemin qui
                         les persiste. -->
                    <div class="flex flex-wrap items-center gap-3 border-t border-slate-800 pt-3">
                      <button type="button" class="btn-primary text-xs px-3 py-1.5 shrink-0"
                              :disabled="!detailTermsDirty || savingTerms"
                              title="Enregistre l'échéancier, les termes du produit et les dates sur l'AO. Refusé par le serveur si une cotation existe déjà — les termes contractuels sont alors figés."
                              @click="saveDetailTerms">
                        💾 Enregistrer les termes
                      </button>
                      <span class="text-[11px]" :class="detailTermsDirty ? 'text-amber-500' : 'text-slate-600'">
                        {{ detailTermsDirty
                          ? 'Modifications non enregistrées — elles seront perdues sans cette sauvegarde.'
                          : 'Termes enregistrés.' }}
                      </span>
                      <button type="button" class="text-[11px] underline text-slate-500 hover:text-slate-300 shrink-0"
                              title="Recharger les termes tels qu'ils sont enregistrés sur l'AO"
                              @click="refreshDetailParams">Recharger</button>
                    </div>

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
                      <div class="flex flex-col gap-1">
                        <label class="label"
                               title="Date d'échange final des flux de cash — celle du term sheet. C'est elle qui actualise le remboursement, pas la maturité.">Date de paiement ⓘ</label>
                        <input v-model="detailAdvanced.payment_date" type="date" class="input"
                               :disabled="!!rfq.current.quotes?.length" />
                      </div>
                    </div>

                    <!-- Les mêmes cartes qu'à la création, dans l'ordre du Pricer,
                         sur l'état du détail. Ce sont des hypothèses de MODÈLE : elles
                         restent ajustables cotations en main, contrairement
                         aux dates ci-dessus qui, elles, sont contractuelles. -->
                    <div class="flex flex-col gap-3 mt-3 pt-3 border-t border-slate-800">
                      <DividendCurveCard :sous-jacents="aoDetail.panier" :index-actif="0"
                                         :horizon="detailHorizon" />
                      <YieldCurveCard :courbe="aoDetail.yieldCurve" :taux-plat="detailAdvanced.r" />
                      <FundingCurveCard :courbe="aoDetail.fundingCurve" />
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

                <div v-if="rfq.current.booked_deal && rfq.current.selected_quote_id"
                     class="flex items-start gap-3 flex-wrap rounded-lg border border-slate-800 bg-slate-900/40 px-3 py-2">
                  <div class="min-w-0 flex-1">
                    <div class="text-xs font-bold text-slate-300">
                      Motif de sélection figé au booking
                      <span v-if="!selectedIsBest" class="ml-1 text-amber-400">
                        · meilleur prix non retenu
                      </span>
                    </div>
                    <div v-if="rfq.current.selection_reason_note"
                         class="text-[11px] text-slate-500 mt-1">
                      {{ rfq.current.selection_reason_note }}
                    </div>
                  </div>
                  <span class="badge badge-muted shrink-0">
                    {{ selectionReasonLabel(rfq.current.selection_reason_code) }}
                  </span>
                </div>

                <div v-else-if="rfq.current.selected_quote_id" class="flex items-center justify-between gap-3 rounded-lg border border-amber-800/60 bg-amber-950/20 px-3 py-2">
                  <span class="text-xs text-amber-300">
                    ⭐ Réponse retenue —
                    {{ modelPriceRecorded
                      ? 'prix modèle enregistré, prête à contrôler dans le Pricer.'
                      : 'calculez le prix modèle Structura avant le booking.' }}
                    <span v-if="rfq.current.kind === 'indicatif'" class="text-amber-500/80">
                      RFQ indicative — pensée pour explorer, pas pour trader.
                    </span>
                  </span>
                  <div class="flex items-center gap-2 shrink-0">
                    <button v-if="rfq.current.kind === 'indicatif'" class="btn-secondary text-xs px-3 py-1.5"
                            @click="convertToTrade(rfq.current)">📐 Convertir en RFQ to trade</button>
                    <button v-if="!modelPriceRecorded" class="btn-secondary text-xs px-3 py-1.5"
                            :disabled="computing" @click="computeModelPrice">
                      {{ computing ? 'Calcul…' : 'Calculer prix modèle' }}
                    </button>
                    <button v-else class="btn-primary text-xs px-3 py-1.5"
                            @click="bookFromRfq">📋 Booker cette réponse</button>
                  </div>
                </div>

                <div v-if="rfq.current.selected_quote_id && !rfq.current.booked_deal"
                     class="flex items-end gap-3 flex-wrap rounded-lg border border-slate-800 bg-slate-900/40 px-3 py-2">
                  <div class="min-w-0">
                    <div class="text-xs font-bold text-slate-300">
                      Motif de sélection
                      <span v-if="!selectedIsBest" class="ml-1 text-amber-400">
                        · meilleur prix non retenu
                      </span>
                    </div>
                    <div class="text-[11px] text-slate-500 mt-0.5">
                      Facultatif et non bloquant. Il documente le choix sans transformer
                      une habitude en interdiction fournisseur.
                    </div>
                  </div>
                  <select v-model="selectionReasonCode" class="select py-1.5 text-xs min-w-[190px]">
                    <option value="">Non renseigné</option>
                    <option v-for="reason in SELECTION_REASONS" :key="reason.value"
                            :value="reason.value">{{ reason.label }}</option>
                  </select>
                  <input v-model="selectionReasonNote" class="input py-1.5 text-xs min-w-[230px] flex-1"
                         placeholder="Précision factuelle (facultative)" />
                  <button class="btn-secondary text-xs px-3 py-1.5 shrink-0"
                          :disabled="!selectionReasonChanged"
                          @click="saveSelectionReason">Enregistrer</button>
                </div>
                <AlertMessage v-if="selectionReasonError" kind="error" dismissible
                              @dismiss="selectionReasonError = ''">
                  {{ selectionReasonError }}
                </AlertMessage>

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
                      <th class="py-1.5 pr-2 font-medium whitespace-nowrap"
                      title="Renseignée d'office à l'heure de réponse + 2 h dès qu'on connaît celle-ci — une cotation ne se tient pas plus longtemps. Modifiable ensuite, et jamais écrasée une fois saisie.">Valide jusqu'au</th>
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
                        <select class="select py-1 px-2 min-w-[125px]" :value="q.status"
                                :disabled="!!rfq.current.booked_deal" @change="updateQuoteField(q, 'status', $event.target.value)">
                          <option value="en_attente">En attente</option>
                          <option value="recu">Reçu</option>
                          <option value="decline">Décliné</option>
                          <option value="expire">Expiré</option>
                        </select>
                      </td>
                      <td class="py-1.5 pr-2">
                        <select class="select py-1 px-2 min-w-[125px]" :value="q.firmness || 'UNKNOWN'"
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
                                :disabled="!!rfq.current.booked_deal || !q.comparable"
                                :title="!q.comparable ? 'Seule une cotation finale, active et non remplacée peut être retenue' : (q.id === rfq.current.selected_quote_id ? 'Réponse retenue — cliquer pour désélectionner' : 'Retenir cette réponse')"
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

            <RfqPricingPanel :rfq="rfq.current" :pricing="rfq.lastPricing" />
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
import BackLink from '../components/ui/BackLink.vue'
import { ref, reactive, computed, watch, onMounted, nextTick } from 'vue'
import { RouterLink, useRouter, useRoute } from 'vue-router'
import { useRfqStore } from '../stores/rfq.js'
import { useMarketAssumptions } from '../composables/useMarketAssumptions.js'
import YieldCurveCard from '../components/YieldCurveCard.vue'
import FundingCurveCard from '../components/FundingCurveCard.vue'
import DividendCurveCard from '../components/DividendCurveCard.vue'
import { apiFetch } from '../utils/api.js'
import { templateMeta, examples, expertExamples } from '../data/payscriptTemplates.js'
import { underlyingGroups, ensureUnderlyings } from '../data/commonUnderlyings.js'
import LoadingSpinner from '../components/ui/LoadingSpinner.vue'
import BaseModal from '../components/ui/BaseModal.vue'
import EmptyState from '../components/ui/EmptyState.vue'
import AlertMessage from '../components/ui/AlertMessage.vue'
import DataFilterBar from '../components/ui/DataFilterBar.vue'
import { useDataFilter } from '../composables/useDataFilter.js'
import RfqParamsEditor from '../components/RfqParamsEditor.vue'
import RfqPricingPanel from '../components/RfqPricingPanel.vue'
import { formatDate, formatDateTime, formatPercent, formatInt, formatBps } from '../utils/format.js'

// Catalogue de sous-jacents : chargé depuis la base au montage.
onMounted(ensureUnderlyings)

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
    // Pas de convention par défaut : une date fixée par un term sheet ne se
    // déplace pas tant que personne n'a dit comment.
    convention: 'none', settlement_lag: 0,
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
        convention: v.convention || 'none',
        settlement_lag: v.settlement_lag || 0,
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
      overridesObj[c.name].convention = sv.convention || 'none'
      overridesObj[c.name].settlement_lag = sv.settlement_lag || 0
      if (c.kind === 'nested_schedule') overridesObj[c.name].sub_frequency = parseTenor(sv.sub_frequency)
    }
  }
}

const rfq = useRfqStore()
const router = useRouter()
const route = useRoute()

// Contexte commercial, quand on arrive depuis une fiche d'opportunité
// (`/rfq?opportunity=12`). Purement additif : sans ce paramètre, l'écran se
// comporte exactement comme avant, et le champ part à null.
const opportuniteContexte = ref(null)
const commercialLinkEnabled = ref(false)
const directClients = ref([])
const directMandates = ref([])
const directOpportunities = ref([])
const directContacts = ref([])
onMounted(async () => {
  const id = Number(route.query.opportunity)
  if (!id) return
  const reponse = await apiFetch(`/api/opportunities/${id}`)
  if (reponse.ok) opportuniteContexte.value = await reponse.json()
})

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

// addBizDays a disparu avec les dates devinees : il ne comptait que les jours
// de semaine, sans aucun ferie, et servait a proposer une value date a
// strike + 2. Les jours ouvres vivent desormais cote serveur, sur un vrai
// calendrier par devise (core/calendars.py).
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
  transaction_format: '',
  instrument_family: '',
  payoff_family: '',
  payoff_description: '',
  documentation_reference: '',
  opportunity_id: null,
  client_id: null,
  mandate_id: null,
  primary_affiliation_id: null,
  script_id: null,
  source_deal_id: null,  // set instead of script_id when sourced from expertDeals
  underlying_name: 'Sous-jacent',
  underlying_ticker: '',
  currency: 'CHF',
  T: 3,
  // Aucune date par défaut : elles viennent du term sheet, pas d'une règle
  // T+2 qui aurait l'air juste sans l'être. Saisie obligatoire.
  strike_date: '',
  value_date: '',
  payment_date: '',
  // Une convention par date, sans défaut global : une date fixée par un term
  // sheet un jour fermé y reste tant que personne n'a dit comment la traiter.
  strike_date_convention: 'none',
  value_date_convention: 'none',
  payment_date_convention: 'none',
})
const dateNotices = reactive({ strike_date: '', value_date: '', payment_date: '' })

// Vrai dès que l'utilisateur saisit la date de paiement lui-même.
//
// Sans ce drapeau, le seul garde-fou de la proposition était « le champ est-il
// vide » — qui ne distingue pas une saisie d'une proposition faite depuis une
// maturité qui a bougé depuis. La date se verrouillait donc sur la première
// maturité vue, souvent celle d'un calendrier CONSTAT à moitié rempli, et ne
// suivait plus jamais. C'est ce qui a produit un AO à maturité 2029 réglé en
// 2026.
const paymentDateSaisie = ref(false)

// Read-only preview of the maturity date, same rule DealTab.vue books with:
// the latest CONSTAT schedule end date if the script has one (to_trade),
// else value_date + T years.
const createMaturityDate = computed(() => {
  const ends = scriptConstats.value
    .filter(c => c.kind !== 'single')
    .map(c => constatOverrides[c.name]?.end_date)
    .filter(Boolean)
  if (ends.length) return ends.reduce((max, d) => (d > max ? d : max))
  // Sans calendrier, la maturité se compte depuis le strike : T est l'horizon
  // de diffusion, et la diffusion démarre à la constatation initiale.
  if (!form.strike_date || !form.T) return ''
  return addYears(form.strike_date, form.T)
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

// ── Hypothèses de marché de l'appel d'offres ──────────────────────
//
// LOCALES, pas celles du Pricer. Les trois cartes acceptent désormais leur état
// en prop et retombent sur le store quand on ne leur en donne pas : le Pricer
// n'a rien changé, et l'AO édite les siennes sans que les deux écrans se
// marchent dessus.
//
// Deux jeux indépendants — un pour la saisie, un pour le détail — rendus par
// la même fabrique, qui porte aussi la conversion vers le moteur et le chemin
// du retour. Voir `useMarketAssumptions`.
// Le panier d'un AO est mono-sous-jacent : la carte de dividende édite sa
// courbe à travers cette fiche, qui reflète `advanced`.
const ao = useMarketAssumptions(computed(() => [{
  name: form.underlying_name || form.underlying_ticker || 'Sous-jacent',
  q: advanced.q,
}]))

// Le détail a son PROPRE jeu. Le partager avec le formulaire de création
// ferait qu'ouvrir un AO existant écrase les hypothèses d'un AO en cours de
// saisie — et l'inverse.
const aoDetail = useMarketAssumptions(computed(() => [{
  name: underlyingSummary.value?.name || 'Sous-jacent',
  q: detailAdvanced.q,
}]))

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
    // Le store Pinia survit à la navigation RFQ → Pricer → RFQ. Le détail
    // conservé peut donc dater d'avant le booking alors que la liste, elle,
    // vient d'être relue. On recharge explicitement l'AO courant pour ne pas
    // laisser apparaître une seconde fois le bouton de booking.
    const currentId = rfq.current?.id || null
    await Promise.all([rfq.fetchList(), rfq.fetchProviders(), fetchScripts(), fetchDealsForScripts()])
    if (currentId && rfq.list.some(item => item.id === currentId)) {
      selectedId.value = currentId
      await rfq.fetchOne(currentId)
      await refreshDetailParams()
    } else if (currentId) {
      selectedId.value = null
      rfq.current = null
    }
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
  commercialLinkEnabled.value = false
  Object.assign(form, {
    name: '', ao_date: todayIso(), kind: 'indicatif', sens: 'achat', source: 'template', template_type: '',
    script_id: null, source_deal_id: null,
    transaction_format: opportuniteContexte.value?.transaction_format || '',
    instrument_family: opportuniteContexte.value?.instrument_family || '',
    payoff_family: opportuniteContexte.value?.payoff_family || '',
    payoff_description: opportuniteContexte.value?.payoff_description || '',
    documentation_reference: '',
    opportunity_id: opportuniteContexte.value?.id ?? null,
    client_id: opportuniteContexte.value?.client_id ?? null,
    mandate_id: opportuniteContexte.value?.mandate_id ?? null,
    primary_affiliation_id:
      opportuniteContexte.value?.primary_contact?.affiliation_id ?? null,
    underlying_name: 'Sous-jacent', underlying_ticker: '', currency: 'CHF', T: 3,
    // Aucune date inventee : ni a l ouverture du formulaire, ni en dupliquant,
    // ni en convertissant. Elles viennent du term sheet de l affaire en cours,
    // pas de celle d avant.
    strike_date: '', value_date: '', payment_date: '',
  })
  // Le drapeau de saisie suit les dates : sans ça, avoir saisi une date de
  // paiement sur une affaire empêcherait toute proposition sur la suivante.
  paymentDateSaisie.value = false
  Object.assign(advanced, { sigma: 20, q: 2, r: 3, N: 20000, model: 'constant' })
  nominalRaw.value = '1 000 000'
  parsedParams.value = []
}

async function toggleDirectCommercial() {
  commercialLinkEnabled.value = !commercialLinkEnabled.value
  if (!commercialLinkEnabled.value) {
    Object.assign(form, {
      client_id: null, mandate_id: null, opportunity_id: null,
      primary_affiliation_id: null,
    })
    directMandates.value = []
    directOpportunities.value = []
    directContacts.value = []
    return
  }
  if (!directClients.value.length) {
    const response = await apiFetch('/api/clients')
    if (response.ok) directClients.value = await response.json()
  }
}

async function loadDirectCommercialOptions(clientId) {
  directMandates.value = []
  directOpportunities.value = []
  directContacts.value = []
  if (!clientId) return
  const [mandates, opportunities, contacts] = await Promise.all([
    apiFetch(`/api/clients/${clientId}/mandates`),
    apiFetch(`/api/opportunities?client_id=${clientId}&open_only=true`),
    apiFetch(`/api/clients/${clientId}/contacts`),
  ])
  if (mandates.ok) directMandates.value = await mandates.json()
  if (opportunities.ok) directOpportunities.value = await opportunities.json()
  if (contacts.ok) directContacts.value = await contacts.json()
}

async function onDirectClientChange() {
  Object.assign(form, {
    mandate_id: null, opportunity_id: null, primary_affiliation_id: null,
  })
  await loadDirectCommercialOptions(form.client_id)
}

function onDirectOpportunityChange() {
  const selected = directOpportunities.value.find(opp => opp.id === form.opportunity_id)
  if (!selected) return
  form.mandate_id = selected.mandate_id ?? null
  form.primary_affiliation_id = selected.primary_contact?.affiliation_id ?? null
  form.transaction_format ||= selected.transaction_format || ''
  form.instrument_family ||= selected.instrument_family || ''
  form.payoff_family ||= selected.payoff_family || ''
  form.payoff_description ||= selected.payoff_description || ''
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
    opportunity_id: source.opportunity_id ?? null,
    client_id: source.client_id ?? null,
    mandate_id: source.mandate_id ?? null,
    primary_affiliation_id: source.primary_affiliation_id ?? null,
    transaction_format: source.transaction_format || '',
    instrument_family: source.instrument_family || '',
    payoff_family: source.payoff_family || '',
    payoff_description: source.payoff_description || '',
    documentation_reference: source.documentation_reference || '',
    script_id: source.script_id || null,
    source_deal_id: null,
    underlying_name: u.name || 'Sous-jacent',
    underlying_ticker: u.ticker || '',
    currency: p.currency || 'CHF',
    T: p.T ?? 3,
    // Aucune date inventee : ni a l ouverture du formulaire, ni en dupliquant,
    // ni en convertissant. Elles viennent du term sheet de l affaire en cours,
    // pas de celle d avant.
    strike_date: '', value_date: '', payment_date: '',
  })
  // Le drapeau de saisie suit les dates : sans ça, avoir saisi une date de
  // paiement sur une affaire empêcherait toute proposition sur la suivante.
  paymentDateSaisie.value = false
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
  if (source.client_id && !opportuniteContexte.value) {
    commercialLinkEnabled.value = true
    if (!directClients.value.length) {
      const response = await apiFetch('/api/clients')
      if (response.ok) directClients.value = await response.json()
    }
    await loadDirectCommercialOptions(source.client_id)
  }
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
    opportunity_id: source.opportunity_id ?? null,
    client_id: source.client_id ?? null,
    mandate_id: source.mandate_id ?? null,
    primary_affiliation_id: source.primary_affiliation_id ?? null,
    transaction_format: source.transaction_format || '',
    instrument_family: source.instrument_family || '',
    payoff_family: source.payoff_family || '',
    payoff_description: source.payoff_description || '',
    documentation_reference: source.documentation_reference || '',
    script_id: keepsScriptId ? source.script_id : null,
    source_deal_id: null,
    underlying_name: u.name || 'Sous-jacent',
    underlying_ticker: u.ticker || '',
    currency: p.currency || 'CHF',
    T: p.T ?? 3,
    // Aucune date inventee : ni a l ouverture du formulaire, ni en dupliquant,
    // ni en convertissant. Elles viennent du term sheet de l affaire en cours,
    // pas de celle d avant.
    strike_date: '', value_date: '', payment_date: '',
  })
  // Le drapeau de saisie suit les dates : sans ça, avoir saisi une date de
  // paiement sur une affaire empêcherait toute proposition sur la suivante.
  paymentDateSaisie.value = false
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
  if (source.client_id && !opportuniteContexte.value) {
    commercialLinkEnabled.value = true
    if (!directClients.value.length) {
      const response = await apiFetch('/api/clients')
      if (response.ok) directClients.value = await response.json()
    }
    await loadDirectCommercialOptions(source.client_id)
  }
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
// into the other. Le calcul du prix n'envoie QUE les hypothèses de modèle :
// les termes contractuels (échéancier, dates, termes du produit) ne sont
// persistés que par saveDetailTerms, via le bouton dédié.
const detailParsedParams    = ref([])
const detailParamOverrides  = reactive({})
const detailScriptConstats  = ref([])
const detailConstatOverrides = reactive({})
const detailAdvanced = reactive({
  sigma: 20, q: 2, r: 3, N: 20000, model: 'constant',
  strike_date: '', value_date: '', payment_date: '',
})

async function refreshDetailParams() {
  await _loadDetailParams()
  termsBaseline.value = contractualSubset(detailTermsPayload())
}

async function _loadDetailParams() {
  const script = rfq.current?.script_snapshot || ''
  const p = rfq.current?.params || {}
  const u = (p.underlyings && p.underlyings[0]) || {}
  Object.assign(detailAdvanced, {
    sigma: Math.round((u.sigma ?? 0.20) * 1000) / 10,
    q: Math.round((u.q ?? 0.02) * 1000) / 10,
    r: Math.round((p.r ?? 0.03) * 1000) / 10,
    N: p.N ?? 20000,
    model: p.model || 'constant',
    strike_date: p.strike_date || '',
    value_date: p.value_date || '',
    payment_date: p.payment_date || '',
  })
  // Les hypothèses de marché avec lesquelles cet AO a été pricé, remises dans
  // les cartes. Sans ce retour, elles rouvriraient décochées et le prochain
  // « Calculer prix modèle » les effacerait sans un mot.
  aoDetail.depuisParams(p)
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

const savingTerms  = ref(false)
const termsError   = ref('')
// Photo des termes tels que l'éditeur les affichait au dernier chargement.
const termsBaseline = ref('')

// Tri récursif des clés : les termes stockés viennent du serveur, ceux de
// l'éditeur sont reconstruits — sans canonisation, deux objets identiques
// mais différemment ordonnés passeraient pour une modification. Même règle
// que le _normalise() de rfq_controls.py côté serveur.
function canonical(v) {
  if (Array.isArray(v)) return v.map(canonical)
  if (v && typeof v === 'object') {
    return Object.keys(v).sort().reduce((o, k) => { o[k] = canonical(v[k]); return o }, {})
  }
  return v
}

// Termes contractuels tels que l'éditeur les tient en ce moment. On repart
// des params STOCKÉS et on n'écrase que ce que l'éditeur pilote : une
// reconstruction complète depuis le formulaire réduisait un panier worst-of
// à son premier sous-jacent et déclenchait le gel sur cinq termes auxquels
// personne n'avait touché.
function detailTermsPayload() {
  const stored = rfq.current?.params || {}
  const user_params = {}
  for (const pp of detailParsedParams.value) {
    const v = detailParamOverrides[pp.name] ?? pp.raw_default
    user_params[pp.name] = pp.is_pct ? v / 100 : v
  }
  return {
    ...stored,
    user_params,
    constats: buildConstatsPayload(detailScriptConstats.value, detailConstatOverrides),
    strike_date: detailAdvanced.strike_date,
    value_date: detailAdvanced.value_date,
    payment_date: detailAdvanced.payment_date,
    // T suit le calendrier, comme à la création : déplacer la dernière
    // constatation sans bouger T laisserait la maturité affichée et
    // l'horizon de simulation raconter deux histoires différentes.
    T: detailCalendarEnd.value
      ? yearsBetween(detailAdvanced.strike_date, detailCalendarEnd.value)
      : (stored.T ?? null),
  }
}

// Sous-ensemble contractuel — ce que le serveur compare pour décider si les
// termes ont bougé (product_terms). Les hypothèses de modèle en sont exclues.
function contractualSubset(p) {
  return JSON.stringify(canonical({
    user_params: p.user_params ?? {},
    constats: p.constats ?? {},
    strike_date: p.strike_date ?? null,
    value_date: p.value_date ?? null,
    payment_date: p.payment_date ?? null,
    T: p.T ?? null,
  }))
}

// Le règlement final ne peut pas précéder la dernière constatation. Le serveur
// le refuse à l'écriture ; ici on le SIGNALE sur les AO déjà en base, que ce
// refus n'atteint plus — leurs termes sont gelés dès la première cotation.
const reglementIncoherent = computed(() => {
  const paiement = rfq.current?.params?.payment_date
  return !!(paiement && detailMaturityDate.value && paiement < detailMaturityDate.value)
})

const detailTermsDirty = computed(() => {
  if (!rfq.current || !termsBaseline.value) return false
  return contractualSubset(detailTermsPayload()) !== termsBaseline.value
})

async function saveDetailTerms() {
  termsError.value = ''
  savingTerms.value = true
  try {
    await rfq.update(rfq.current.id, { params: detailTermsPayload() })
    await refreshDetailParams()
    notice.value = 'Termes de l\'AO enregistrés'
  } catch (e) {
    termsError.value = e.message
  } finally {
    savingTerms.value = false
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

// L'horizon du détail, pour la courbe de dividende : la même règle que
// `detailTermsPayload` — le calendrier fait foi, le T stocké prend le relais.
const detailHorizon = computed(() => (
  detailCalendarEnd.value && detailAdvanced.strike_date
    ? yearsBetween(detailAdvanced.strike_date, detailCalendarEnd.value)
    : (rfq.current?.params?.T ?? 1)
))

const fmtNominal = formatInt

// Une date saisie ne se déplace jamais en silence : le serveur la résout sur
// le calendrier de la devise, l'écran dit d'où elle vient et où elle va.
async function resolveFormDate(field) {
  dateNotices[field] = ''
  const value = form[field]
  const convention = form[`${field}_convention`]
  if (!value || !convention || convention === 'none') return
  try {
    const res = await apiFetch('/api/calendar/resolve', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ date: value, currency: form.currency, convention }),
    })
    if (!res.ok) return
    const data = await res.json()
    if (data.moved) {
      form[field] = data.date
      dateNotices[field] = `Ajustée depuis le ${data.source}, jour fermé sur le calendrier ${form.currency}.`
    }
  } catch { /* le champ garde ce qui a été saisi */ }
}

// Trois jours ouvrés après la dernière constatation : l'usage courant. Une
// proposition, jamais un écrasement — un term sheet qui dit autre chose gagne.
// Vrai dès que l'utilisateur saisit la date lui-même. Sans ce drapeau, le seul
// garde-fou était « le champ est-il vide » — qui ne distingue pas une saisie
// d'une proposition faite depuis une maturité qui a bougé depuis. La date se
// verrouillait donc sur la première maturité vue, souvent celle d'un calendrier
// à moitié rempli, et ne suivait plus jamais.
async function proposePaymentDate() {
  if (paymentDateSaisie.value || !createMaturityDate.value) return
  try {
    const res = await apiFetch('/api/calendar/resolve', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ date: createMaturityDate.value, currency: form.currency,
                             business_days: 3 }),
    })
    if (res.ok) form.payment_date = (await res.json()).date
  } catch { /* rien à proposer, le champ reste à saisir */ }
}

watch(createMaturityDate, proposePaymentDate)

/**
 * Ce qui manque encore, dans l'ordre du formulaire.
 *
 * Une SEULE liste de règles, lue par la barre d'actions et par la soumission :
 * deux listes finiraient par diverger, et le bouton refuserait pour une raison
 * que l'écran n'annonce pas.
 */
const champsManquants = computed(() => {
  const trous = []
  if (!form.name.trim()) trous.push('nom')
  if (form.source === 'template' && !form.template_type && !duplicateSourceScript.value) {
    trous.push('template')
  }
  if (form.source === 'script' && !form.script_id && !form.source_deal_id
      && !duplicateSourceScript.value) {
    trous.push('script')
  }
  for (const [champ, libelle] of [['strike_date', 'date de strike'],
                                  ['value_date', 'date de valeur'],
                                  ['payment_date', 'date de paiement']]) {
    if (!form[champ]) trous.push(libelle)
  }
  return trous
})

async function submitCreate() {
  createError.value = ''
  if (champsManquants.value.length) {
    createError.value = `À compléter : ${champsManquants.value.join(', ')}`
    return
  }
  if (form.payment_date < form.value_date) {
    createError.value = 'La date de paiement ne peut pas précéder la date de valeur'; return
  }
  // Et surtout pas la MATURITÉ. Le contrôle ci-dessus comparait à la date de
  // valeur, ce qui laissait passer une maturité 2029 réglée en 2026 : trois ans
  // d'écart, sans un mot, jusqu'au refus de booking — et l'AO était alors
  // impossible à corriger, ses termes gelés par la première cotation reçue.
  // Le serveur refuse aussi ; ici c'est pour le dire avant d'envoyer.
  if (createMaturityDate.value && form.payment_date < createMaturityDate.value) {
    createError.value = `Le règlement (${fmtDateOnly(form.payment_date)}) précède la maturité `
      + `(${fmtDateOnly(createMaturityDate.value)}). La date de paiement date l'échange final `
      + `des flux : elle suit la dernière constatation.`
    return
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
      // Le besoin client à l'origine, s'il y en a un. Null sinon — le cas
      // courant, et celui de tout l'existant.
      opportunity_id: form.opportunity_id,
      client_id: form.client_id,
      mandate_id: form.mandate_id,
      primary_affiliation_id: form.primary_affiliation_id,
      transaction_format: form.transaction_format || null,
      instrument_family: form.instrument_family || null,
      payoff_family: form.payoff_family || null,
      payoff_description: form.payoff_description || null,
      documentation_reference: form.documentation_reference || null,
      template_type: form.source === 'template' ? form.template_type : '',
      script_id: form.source === 'script' ? form.script_id : null,
      script_snapshot,
      params: {
        underlyings: [{
          name: form.underlying_name, ticker: form.underlying_ticker,
          ccy: form.currency, sigma: advanced.sigma / 100, q: advanced.q / 100,
          ...ao.dividendeDuSousJacent(0, createMaturityDate.value
            ? yearsBetween(form.strike_date, createMaturityDate.value) : form.T),
        }],
        corr_matrix: [[1]],
        // T dérivé du calendrier CONSTAT quand il y en a un, et non du ténor
        // tapé : c'est la fin de calendrier que l'écran affiche comme maturité.
        // Laisser les deux diverger obligeait à « corriger » T à chaque calcul
        // de prix modèle — donc à toucher un terme contractuel après
        // sollicitation. T est fixé une fois, à la création, où il est encore
        // librement modifiable.
        r: advanced.r / 100,
        // T est l'horizon de DIFFUSION : il se compte depuis le strike, pas
        // depuis le règlement. Deux jours ouvrés d'écart avec l'ancienne
        // définition, mais surtout deux définitions différentes du symbole.
        T: (createMaturityDate.value
            ? yearsBetween(form.strike_date, createMaturityDate.value)
            : form.T),
        N: advanced.N, model: advanced.model,
        // Les trois hypothèses de marché saisies au-dessus. Sans elles dans le
        // payload, les cartes seraient éditables sans le moindre effet sur le
        // prix — le projet a déjà connu ça avec la courbe de dividende, qui vaut
        // pourtant −491,6 bps.
        ...ao.hypothesesDeMarche(),
        user_params,
        constats: buildConstatsPayload(scriptConstats.value, constatOverrides),
        notional: nominalValue.value, currency: form.currency,
        strike_date: form.strike_date, value_date: form.value_date,
        payment_date: form.payment_date,
        // Traçabilité : les dates stockées sont déjà les dates effectives, la
        // convention dit seulement comment on y est arrivé.
        date_conventions: {
          strike_date: form.strike_date_convention,
          value_date: form.value_date_convention,
          payment_date: form.payment_date_convention,
        },
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
    // On n'envoie QUE les hypothèses de modèle. Les termes contractuels
    // (constats, dates, sous-jacents, user_params, T) restent côté serveur et
    // ne transitent pas : c'est ce qui permet de recalculer le prix modèle à
    // tout moment de la vie de l'AO, cotations reçues ou non.
    //
    // Auparavant ce bouton renvoyait le bloc complet reconstruit depuis le
    // formulaire. Rien de tout cela n'était une modification voulue, mais la
    // re-sérialisation ne retombait pas sur la valeur stockée : le contrôle de
    // gel se déclenchait sur cinq termes auxquels personne n'avait touché, et
    // l'AO devenait impossible à re-pricer. Le même remaniement réduisait au
    // passage un panier worst-of à son premier sous-jacent.
    //
    // sigma/q sont fusionnés par INDICE sur le panier stocké (voir
    // _merge_pricing_params) : la taille du panier vient de l'AO, pas du
    // formulaire de pricing.
    const nUnderlyings = (rfq.current.params?.underlyings || []).length || 1
    const pricingUnderlyings = Array.from({ length: nUnderlyings }, () => ({
      sigma: detailAdvanced.sigma / 100,
      q: detailAdvanced.q / 100,
      // Le dividende se porte par SOUS-JACENT. Le hisser au niveau du produit
      // le ferait ignorer en silence — une courbe à 8 % vaut pourtant
      // −491,6 bps.
      ...aoDetail.dividendeDuSousJacent(0, detailHorizon.value),
    }))
    await rfq.update(rfq.current.id, {
      pricing_params: {
        underlyings: pricingUnderlyings,
        r: detailAdvanced.r / 100,
        N: detailAdvanced.N,
        model: detailAdvanced.model,
        // Hypothèses de modèle, donc admises par `_merge_pricing_params` :
        // elles n'appartiennent pas au périmètre contractuel gelé.
        ...aoDetail.hypothesesDeMarche(),
      },
    })
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

// Une cotation vit quelques heures, pas quelques jours : dès qu'on connaît
// l'heure de réponse, on tient le prix pour valable deux heures. C'est une
// valeur proposée — une validité déjà saisie n'est jamais écrasée, et le
// serveur exige de toute façon une validité postérieure à la réponse
// (api/rfq.py update_quote).
const DEFAULT_VALIDITY_HOURS = 2

function withDefaultValidity(q, quotedAtIso, payload) {
  if (quotedAtIso && !q.valid_until) {
    payload.valid_until = new Date(
      new Date(quotedAtIso).getTime() + DEFAULT_VALIDITY_HOURS * 3600_000
    ).toISOString()
  }
  return payload
}

function onQuotePriceChange(q, value) {
  const price = value === '' ? null : Number(value)
  const payload = { price }
  // First time a price is entered, log the response as received now unless
  // a date was already set explicitly.
  if (price !== null && !q.quoted_at) {
    payload.quoted_at = new Date().toISOString()
    withDefaultValidity(q, payload.quoted_at, payload)
  }
  rfq.updateQuote(rfq.current.id, q.id, payload)
}

function onQuoteDateChange(q, value) {
  const quotedAt = value ? new Date(value).toISOString() : null
  rfq.updateQuote(rfq.current.id, q.id, withDefaultValidity(q, quotedAt, { quoted_at: quotedAt }))
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
  const priced = (rfq.current?.quotes || []).filter(q => q.comparable)
  if (!priced.length) return null
  const selling = rfq.current?.sens === 'vente'
  return priced.reduce((best, q) =>
    (selling ? q.price > best.price : q.price < best.price) ? q : best)
})
const selectedQuote = computed(() => (rfq.current?.quotes || []).find(
  q => q.id === rfq.current?.selected_quote_id) || null)
const selectedIsBest = computed(
  () => !!selectedQuote.value && !!bestQuote.value
        && Math.abs(selectedQuote.value.price - bestQuote.value.price) <= 1e-9)

const SELECTION_REASONS = [
  { value: 'client_request', label: 'Demande du Client' },
  { value: 'documentation', label: 'Documentation / programme' },
  { value: 'credit', label: 'Crédit / contrepartie' },
  { value: 'concentration', label: 'Concentration' },
  { value: 'relationship', label: 'Relation fournisseur' },
  { value: 'execution_quality', label: "Qualité d'exécution" },
  { value: 'other', label: 'Autre' },
]
function selectionReasonLabel(code) {
  return SELECTION_REASONS.find(reason => reason.value === code)?.label || 'Non renseigné'
}
const selectionReasonCode = ref('')
const selectionReasonNote = ref('')
const selectionReasonError = ref('')
watch([
  () => rfq.current?.id,
  () => rfq.current?.selection_reason_code,
  () => rfq.current?.selection_reason_note,
], () => {
  selectionReasonCode.value = rfq.current?.selection_reason_code || ''
  selectionReasonNote.value = rfq.current?.selection_reason_note || ''
})
const selectionReasonChanged = computed(() => (
  selectionReasonCode.value !== (rfq.current?.selection_reason_code || '')
  || selectionReasonNote.value.trim() !== (rfq.current?.selection_reason_note || '')
))

async function saveSelectionReason() {
  selectionReasonError.value = ''
  try {
    await rfq.update(rfq.current.id, {
      selection_reason_code: selectionReasonCode.value || null,
      selection_reason_note: selectionReasonNote.value.trim() || null,
    })
  } catch (e) {
    selectionReasonError.value = e.message || 'Le motif n’a pas pu être enregistré.'
  }
}

// Le backend refuse à juste titre un booking sans prix modèle horodaté et
// relié au snapshot RFQ. Ne pas annoncer « prête à booker » avant que ces deux
// faits visibles existent : le contrôle cryptographique final reste côté
// serveur, mais l'utilisateur n'entre plus dans un parcours condamné d'avance.
const modelPriceRecorded = computed(() =>
  Number(rfq.current?.model_price) > 0 && !!rfq.current?.model_price_at)

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
