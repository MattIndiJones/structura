<template>
  <div class="flex flex-col gap-5">

    <!-- No pricing result warning -->
    <div v-if="!store.result" class="card border-amber-800/50 bg-amber-950/20">
      <p class="text-amber-400 text-sm">
        ⚠ Lancez d'abord un pricing (▶ Pricer) pour pré-remplir le fair value et les temps d'observation.
      </p>
    </div>

    <div v-if="store.currentRfqId"
         :class="['text-[10px] border rounded-lg px-3 py-1.5 w-fit',
                  (fairValueFromRfq || rfqUnmatchedProvider) ? 'border-amber-700/60 bg-amber-950/20 text-amber-300' : 'border-slate-700 text-slate-500']">
      📨 Pré-rempli depuis la RFQ #{{ store.currentRfqId }} — contrepartie et prix traité repris de la réponse retenue.
      <template v-if="rfqUnmatchedProvider">
        <br />
        ⚠ Le fournisseur <b>{{ rfqUnmatchedProvider }}</b> ne correspond à aucune contrepartie éligible —
        choisissez-la ci-dessous, ou rattachez-la une fois pour toutes dans
        <b>Administration → Fournisseurs RFQ</b>.
      </template>
      <template v-if="fairValueFromRfq">
        <br />
        ⚠ La fair value affichée est le prix modèle figé sur la RFQ<span v-if="rfqPriceAgeDays > 0"> (calculé il y a {{ rfqPriceAgeDays }} j)</span> —
        lancez <b>▶ Pricer</b> pour la recalculer aux conditions du jour avant de booker.
      </template>
    </div>

    <!-- ── Identité du deal ─────────────────────────────────── -->
    <div class="card">
      <h2 class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-4">Identité</h2>
      <div class="grid grid-cols-2 gap-3">
        <div class="col-span-2">
          <label class="label">Sens du deal</label>
          <div class="flex gap-2">
            <button v-for="s in ['vente', 'achat']" :key="s"
              @click="form.sens = s"
              :class="[
                'flex-1 py-2 rounded-lg text-xs font-bold border transition-colors',
                form.sens === s
                  ? s === 'vente'
                    ? 'bg-blue-900/50 border-blue-500 text-blue-300'
                    : 'bg-emerald-900/50 border-emerald-500 text-emerald-300'
                  : 'border-slate-700 text-slate-500 hover:border-slate-500'
              ]">
              {{ s === 'vente' ? '↑ Vente (banque vend)' : '↓ Achat (banque achète)' }}
            </button>
          </div>
        </div>

        <div class="col-span-2">
          <label class="label">Contrepartie <span class="text-red-400">*</span>
            <HelpTip text="Liste des contreparties éligibles, gérée dans Administration → Contreparties deals. Seules les banques actives de ce catalogue peuvent faire face à un deal." />
          </label>
          <select v-model="form.contrepartie" class="select">
            <option value="">— Choisir une contrepartie —</option>
            <option v-for="c in counterparties" :key="c.id" :value="c.name">
              {{ c.name }}{{ c.country ? ` (${c.country})` : '' }}
            </option>
          </select>
          <p v-if="errors.contrepartie" class="text-red-400 text-xs mt-1">{{ errors.contrepartie }}</p>
        </div>

        <div class="col-span-2">
          <label class="label">Type de produit
            <HelpTip text="Libre — sert à classer et filtrer dans la page Booking (par famille de produit). Pas de lien automatique avec les tags du script sauvegardé." />
          </label>
          <input v-model="form.product_type" type="text" class="input" list="product-type-suggestions"
            placeholder="ex: Autocall Athena, Reverse Convertible…" />
          <datalist id="product-type-suggestions">
            <option value="Autocall" /><option value="Options" />
            <option value="Produits à capital" /><option value="Sharks" />
          </datalist>
        </div>

        <div class="col-span-2">
          <label class="label">Traitement des constatations
            <HelpTip width="w-80" text="Classique : la clôture Yahoo non ajustée devient automatiquement le fixing de référence si tous les contrôles passent. Contrôlé : chaque fixing suit le workflow Ops Maker / Ops Checker. La politique est figée au booking." />
          </label>
          <select v-model="form.fixing_policy" class="select">
            <option value="AUTO_YAHOO">Classique — Yahoo automatique</option>
            <option value="FOUR_EYES">Produit contrôlé — validation à quatre yeux</option>
          </select>
          <p class="text-[10px] text-slate-500 mt-1">
            Une anomalie Yahoo bascule toujours la constatation en contrôle manuel, sans écraser le dernier fixing officiel.
          </p>
        </div>

        <div>
          <label class="label">Entité (vous)</label>
          <input :value="entityLabel" type="text"
            class="input bg-slate-800/40 text-slate-500 cursor-not-allowed" readonly />
        </div>
        <div>
          <label class="label">Devise</label>
          <select v-model="store.globalParams.deal_ccy" class="select">
            <option>EUR</option><option>USD</option><option>GBP</option>
            <option>JPY</option><option>CHF</option><option>SGD</option>
          </select>
        </div>
      </div>
    </div>

    <!-- ── Économique ──────────────────────────────────────── -->
    <div class="card">
      <h2 class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-4">Économique</h2>
      <div class="grid grid-cols-2 gap-3">
        <div class="col-span-2">
          <label class="label">Nominal <span class="text-red-400">*</span></label>
          <input v-model="nominalRaw" @blur="formatNominal" @focus="unformatNominal"
            type="text" inputmode="numeric" class="input font-mono"
            placeholder="1 000 000" />
          <p v-if="errors.nominal" class="text-red-400 text-xs mt-1">{{ errors.nominal }}</p>
        </div>

        <div>
          <label class="label">Fair Value (%) <span class="text-red-400">*</span>
            <HelpTip text="Prix théorique issu du dernier pricing Monte Carlo (onglet ▶ Pricer) — pas nécessairement le prix auquel le deal est traité. Modifiable ici si vous voulez figer une valeur différente du dernier run. Sert de base au P&L du deal : un deal ne peut pas être booké à 0." />
          </label>
          <input v-model.number="form.fair_value" type="number" step="0.01" class="input"
            :class="!store.result ? 'border-amber-700/50' : ''" />
          <p v-if="errors.fair_value" class="text-red-400 text-xs mt-1">{{ errors.fair_value }}</p>
          <p v-else-if="!store.result" class="text-amber-500 text-[10px] mt-0.5">
            {{ fairValueFromRfq ? 'Prix modèle de la RFQ — à recalculer' : 'Issu du dernier pricing' }}
          </p>
        </div>
        <div>
          <label class="label">Prix traité (%) <span class="text-red-400">*</span>
            <HelpTip text="Le prix réellement négocié avec la contrepartie — peut différer de la fair value (commission, négociation, contraintes de cotation). C'est ce prix qui sert de référence pour le suivi de P&L du deal." />
          </label>
          <input v-model.number="form.price_traded" type="number" step="0.01" class="input" />
          <p v-if="errors.price_traded" class="text-red-400 text-xs mt-1">{{ errors.price_traded }}</p>
        </div>

        <div class="col-span-2">
          <div class="flex items-center justify-between bg-slate-800/60 rounded-lg px-4 py-2.5">
            <span class="text-xs text-slate-400">Marge
              <HelpTip text="Prix traité − fair value. Positif = la banque vend plus cher que le prix théorique (ou achète moins cher) — c'est la marge commerciale capturée sur le deal, indépendamment de la performance future du produit." />
            </span>
            <span class="font-mono font-bold text-sm"
              :class="margin >= 0 ? 'text-emerald-400' : 'text-red-400'">
              {{ margin >= 0 ? '+' : '' }}{{ formatPercent(margin, 2) }}
              <span class="text-slate-500 font-normal ml-1 text-xs">
                ({{ nominalValue > 0 ? formatCcy(nominalValue * margin / 100) : '–' }})
              </span>
            </span>
          </div>
        </div>
      </div>
    </div>

    <!-- ── Dates ───────────────────────────────────────────── -->
    <div class="card">
      <h2 class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-4">Dates</h2>
      <div class="grid grid-cols-2 gap-3">
        <div>
          <label class="label">Trade date
            <HelpTip text="Date d'accord commercial entre les parties — la date à laquelle le deal est juridiquement conclu. Distincte de la strike date (fixing des niveaux initiaux) et de la value date (règlement effectif)." />
          </label>
          <input v-model="form.trade_date" type="date" class="input" />
        </div>
        <div>
          <label class="label">Strike date <span class="text-slate-600 font-normal">(fixing S₀)</span>
            <HelpTip text="Date à laquelle les niveaux initiaux (S₀) des sous-jacents sont constatés — la référence par rapport à laquelle toutes les performances du produit sont mesurées ensuite. Se saisit dans l'onglet Events une fois le deal booké." />
          </label>
          <input v-model="form.strike_date" type="date" class="input" />
        </div>
        <div>
          <label class="label">Value date
            <HelpTip text="t=0 pour l'actualisation. Généralement strike + 2j ouvrés." />
          </label>
          <input v-model="form.value_date" type="date" class="input" />
        </div>
        <div>
          <label class="label">Maturité
            <HelpTip text="Calculée automatiquement — pas éditable directement. Si le script utilise un calendrier CONSTAT (mode expert), c'est la date de fin la plus tardive parmi les calendriers ci-dessous. Sinon, value date + T (maturité en années définie dans Marché &amp; Paramètres)." />
          </label>
          <input :value="maturityDate" type="date"
            class="input bg-slate-800/40 text-slate-500 cursor-not-allowed" readonly />
        </div>
        <div class="col-span-2">
          <label class="label">Payment date <span class="text-slate-600 font-normal">(règlement cash final)</span>
            <HelpTip text="Date à laquelle le client reçoit définitivement son cash — distincte de la maturité, qui est la dernière date d'observation. Proposée à maturité + 3 jours ouvrés sur le calendrier de la devise, éditable si le term sheet prévoit autre chose. Elle porte l'actualisation du remboursement final : ce n'est pas qu'une donnée de booking, elle entre dans le prix." />
          </label>
          <input v-model="form.payment_date" type="date" class="input"
            @input="paymentDateDirty = true" />
        </div>
      </div>
    </div>

    <!-- ── Sous-jacents ──────────────────────────────────────── -->
    <div class="card">
      <div class="flex items-center justify-between mb-3">
        <h2 class="text-xs font-bold text-slate-400 uppercase tracking-wider">Sous-jacents
          <HelpTip text="Composition du panier — nom, ticker, devise. Les paramètres de marché (volatilité, dividende, smile, quanto) se calibrent ensuite dans l'onglet Marché & Paramètres." />
        </h2>
        <button class="btn-secondary text-xs" @click="onAddUnderlying">+ Ajouter</button>
      </div>

      <div class="flex gap-1 mb-3 flex-wrap items-center">
        <button v-for="(u, i) in store.underlyings" :key="i"
          @click="store.activeUnderlyingIdx = i"
          :class="[
            'px-2.5 py-1 rounded-md text-xs font-medium transition-colors border',
            activeUIdx === i
              ? 'bg-blue-900/50 border-blue-600 text-blue-300'
              : 'bg-slate-800 border-slate-700 text-slate-400 hover:border-slate-500 hover:text-slate-200'
          ]">
          <span class="font-semibold">{{ demo.underlyingLabel(u.name, i) }}</span>
          <span v-if="u.ticker" class="ml-1.5 opacity-50 font-mono text-[10px]">
            <SensitiveValue placeholder="···">{{ u.ticker }}</SensitiveValue>
          </span>
        </button>
      </div>

      <div v-if="activeU" class="bg-slate-800/60 border border-slate-700 rounded-lg p-4">
        <div class="flex items-center justify-between mb-3">
          <span v-if="demo.enabled" class="text-sm font-semibold text-slate-300 border-b border-slate-600 pb-1">
            {{ demo.underlyingLabel(activeU.name, activeUIdx) }}
          </span>
          <input v-else v-model="activeU.name"
            class="input w-auto text-sm font-semibold bg-transparent border-0 border-b border-slate-600 rounded-none px-0 pb-1 focus:border-blue-500" />
          <button v-if="store.underlyings.length > 1"
            class="text-slate-600 hover:text-red-400 text-xs ml-2"
            @click="onRemoveUnderlying">✕</button>
        </div>

        <div class="mb-1">
          <label class="label">Ticker Yahoo Finance</label>
          <SensitiveValue mode="input">
          <div class="flex gap-2 items-center">
            <select class="select text-xs flex-1"
              :value="activeU.ticker"
              @change="onTickerSelect($event.target.value)">
              <option value="">— Choisir un sous-jacent —</option>
              <optgroup v-for="g in underlyingGroups" :key="g.group" :label="g.group">
                <option v-for="it in g.items" :key="it.ticker" :value="it.ticker">{{ it.label }}</option>
              </optgroup>
            </select>
            <button class="btn-secondary text-lg px-3 flex-shrink-0" title="Charger σ, q depuis Yahoo Finance"
              :disabled="store.loading || !activeU.ticker" @click="store.loadYfOne(activeUIdx)">📡</button>
          </div>
          <input v-model="activeU.ticker" class="input font-mono mt-1 text-xs"
            placeholder="ou saisir manuellement ex: ^STOXX50E"
            @focus="onTickerFocus" @blur="onTickerBlur" />
          </SensitiveValue>
        </div>
        <div v-if="store.yfStatus" class="text-xs mb-2 leading-relaxed"
             :class="store.yfStatus.startsWith('⚠') ? 'text-amber-400' : 'text-green-400'">
          <SensitiveValue placeholder="Données chargées">{{ store.yfStatus }}</SensitiveValue>
        </div>

        <div class="w-32">
          <label class="label">CCY</label>
          <select v-model="activeU.ccy" class="select">
            <option>EUR</option><option>USD</option><option>GBP</option>
            <option>JPY</option><option>CHF</option><option>SGD</option>
          </select>
        </div>
      </div>
    </div>

    <!-- ── Calendrier du script (CONSTAT, mode expert) ─────── -->
    <div v-if="store.scriptConstats.length > 0" class="card">
      <div class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3">Calendrier du script (CONSTAT)
        <HelpTip width="w-72" text="Chaque CONSTAT()/CONSTAT()() déclaré dans le script attend ici ses vraies dates (début, fin, roll, fréquence) — le script référence le calendrier par son nom (AT NomDuConstat:), les dates concrètes ne sont résolues qu'au moment du pricing, pas à l'écriture du script." />
      </div>
      <div class="flex flex-col gap-3">
        <div v-for="c in store.scriptConstats" :key="c.name"
             class="bg-slate-800/60 border border-slate-700 rounded-lg p-3">
          <div class="text-xs font-semibold text-slate-300 mb-2">{{ c.name }}</div>

          <!-- CONSTAT : une date unique -->
          <div v-if="c.kind === 'single'" class="text-xs max-w-xs">
            <label class="label">Date</label>
            <SensitiveValue mode="input">
              <input type="date" v-model="store.constatOverrides[c.name]" class="input" />
            </SensitiveValue>
          </div>

          <!-- CONSTAT() / CONSTAT()() -->
          <div v-else class="flex flex-col gap-2 text-xs">
            <div class="flex flex-wrap gap-3 items-end">
              <div>
                <label class="label">Date de début
                  <HelpTip text="Début de la première période (typiquement la date de strike) — pas elle-même une date d'observation : le moteur exclut toujours ce premier point généré. Pour N observations réelles à partir d'une date donnée, mets cette date de début un cran AVANT la première observation voulue (ex: date de strike)." />
                </label>
                <SensitiveValue mode="input">
                  <input type="date" v-model="store.constatOverrides[c.name].start_date" class="input" />
                </SensitiveValue>
              </div>
              <div>
                <label class="label">Date de fin</label>
                <SensitiveValue mode="input">
                  <input type="date" v-model="store.constatOverrides[c.name].end_date" class="input" />
                </SensitiveValue>
              </div>
              <div>
                <label class="label">Date de roll</label>
                <SensitiveValue mode="input">
                  <input type="date" v-model="store.constatOverrides[c.name].roll_date" class="input" />
                </SensitiveValue>
              </div>
              <div>
                <label class="label">Fréquence</label>
                <div class="flex gap-1">
                  <input type="number" min="1" v-model.number="store.constatOverrides[c.name].frequency.value"
                         class="input w-14" />
                  <select v-model="store.constatOverrides[c.name].frequency.unit" class="select">
                    <option value="D">D</option>
                    <option value="M">M</option>
                    <option value="Y">Y</option>
                  </select>
                </div>
              </div>
              <!-- Convention et règlement : le masque RFQ les portait déjà,
                   pas cet éditeur. Sans eux un term sheet ne peut pas être
                   saisi tel qu'il est écrit — une constatation tombant un
                   samedi restait au samedi, et un règlement à J+7 ouvrés était
                   inexprimable. Les deux étaient pourtant déjà lus par
                   scheduleRequest(). -->
              <div>
                <label class="label">Convention
                  <HelpTip text="Ce que devient une date de constatation qui tombe un jour fermé sur le calendrier de la devise de règlement. « Jour ouvré suivant » est l'usage courant. Le calendrier tient compte des fériés, pas seulement des week-ends." />
                </label>
                <select v-model="store.constatOverrides[c.name].convention" class="select">
                  <option value="none">Aucun ajustement</option>
                  <option value="following">Jour ouvré suivant</option>
                  <option value="modified_following">Suivant, sauf changement de mois</option>
                  <option value="preceding">Jour ouvré précédent</option>
                  <option value="modified_preceding">Précédent, sauf changement de mois</option>
                </select>
              </div>
              <div>
                <label class="label">Règlement
                  <HelpTip text="Nombre de jours ouvrés entre une constatation et l'échange de cash correspondant. C'est cette date-là qui porte l'actualisation, pas celle de l'observation." />
                </label>
                <div class="flex items-center gap-1">
                  <input type="number" min="0" max="15" class="input w-16"
                         v-model.number="store.constatOverrides[c.name].settlement_lag" />
                  <span class="text-[10px] text-slate-500 whitespace-nowrap">j. ouvrés</span>
                </div>
              </div>
              <div>
                <label class="label">Stub
                  <HelpTip text="Quand la période totale n'est pas un multiple exact de la fréquence, le stub dit où va la période irrégulière restante. Short/Long = la période résiduelle est plus courte/longue qu'une période pleine. First/Last = elle se place au début ou à la fin du calendrier." />
                </label>
                <select v-model="store.constatOverrides[c.name].stub" class="select">
                  <option value="short_last">Short Last</option>
                  <option value="long_last">Long Last</option>
                  <option value="short_first">Short First</option>
                  <option value="long_first">Long First</option>
                </select>
              </div>
              <div v-if="c.kind === 'nested_schedule'">
                <label class="label">Sous-fréq.</label>
                <div class="flex gap-1">
                  <input type="number" min="1" v-model.number="store.constatOverrides[c.name].sub_frequency.value"
                         class="input w-14" />
                  <select v-model="store.constatOverrides[c.name].sub_frequency.unit" class="select">
                    <option value="D">D</option>
                    <option value="M">M</option>
                    <option value="Y">Y</option>
                  </select>
                </div>
              </div>
            </div>

            <!-- Même échéancier que le module RFQ : un calendrier ne se lit
                 pas différemment selon l'écran où on l'ouvre. -->
            <ObservationSchedule class="mt-1" :request="scheduleRequest(c)" />
          </div>
        </div>
      </div>
    </div>

    <!-- ── Aperçu des constatations ──────────────────────── -->
    <div class="card">
      <h2 class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3">
        Structure des constatations
        <HelpTip width="w-72" text="Aperçu du calendrier d'observation dérivé du dernier pricing (dates AT du script). Les colonnes S₀ sont vides ici à dessein — les spots réels ne se saisissent qu'après booking, dans l'onglet Events, une fois le deal existant." />
      </h2>

      <div v-if="!store.result" class="text-xs text-slate-600 italic py-2">
        Lancez un pricing (▶ Pricer) pour visualiser le tableau des constatations.
      </div>

      <div v-else>
        <div class="overflow-x-auto table-shell" tabindex="0" role="region">
          <table class="w-full text-xs border-collapse">
            <thead>
              <tr class="border-b border-slate-700">
                <th class="text-left text-slate-500 font-medium pb-2 pr-3">#</th>
                <th class="text-left text-slate-500 font-medium pb-2 pr-3 whitespace-nowrap">Label</th>
                <th class="text-left text-slate-500 font-medium pb-2 pr-3 whitespace-nowrap">Date</th>
                <th class="text-left text-slate-500 font-medium pb-2 pr-3 whitespace-nowrap num">T (Y)</th>
                <th v-for="u in store.underlyings" :key="u.name"
                  class="text-left text-slate-500 font-medium pb-2 pr-2 whitespace-nowrap">
                  {{ u.ticker || u.name }}
                  <span class="text-slate-600 font-normal">S₀</span>
                </th>
                <th class="text-left text-slate-500 font-medium pb-2">Statut</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(ev, i) in previewEvents" :key="i"
                :class="[
                  'border-b border-slate-800/50',
                  ev.t === 0 ? 'bg-amber-950/20' : '',
                  ev.isFuture && ev.t !== 0 ? 'opacity-50' : '',
                ]">
                <td class="py-1.5 pr-3 text-slate-500">{{ i + 1 }}</td>
                <td class="py-1.5 pr-3 whitespace-nowrap"
                  :class="ev.t === 0 ? 'text-amber-400 font-semibold' : 'text-slate-300'">
                  {{ ev.label }}
                </td>
                <td class="py-1.5 pr-3 font-mono text-slate-300 whitespace-nowrap">{{ formatDate(ev.date) }}</td>
                <td class="py-1.5 pr-3 font-mono num text-slate-400">{{ formatNumber(ev.t, 2) }}</td>
                <td v-for="u in store.underlyings" :key="u.name" class="py-1.5 pr-2">
                  <span v-if="closesPassees[ev.date]?.[u.ticker]"
                        class="text-slate-300 font-mono text-[10px]">
                    <SensitiveValue>{{ formatNumber(closesPassees[ev.date][u.ticker], 2) }}</SensitiveValue>
                  </span>
                  <span v-else class="text-slate-600 font-mono text-[10px]">–</span>
                </td>
                <td class="py-1.5">
                  <span class="text-[10px]"
                    :class="ev.isFuture ? 'text-slate-600' : 'text-emerald-400'">
                    {{ ev.isFuture ? 'à observer' : 'constaté' }}
                  </span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <p class="text-[10px] text-slate-600 mt-2">
          {{ previewEvents.length }} constatation(s) · {{ store.underlyings.length }} sous-jacent(s) ·
          Les spots S₀ se saisissent dans Events après booking.
        </p>
        <!-- Ces dates viennent de la grille hebdomadaire du dernier Monte
             Carlo (flux_table), à quelques jours des dates contractuelles. Le
             booking, lui, résout le calendrier du script (deals.py:
             _derive_observation_times) — d'où l'avertissement plutôt qu'un
             aperçu qui prétendrait à l'exactitude. -->
        <p v-if="store.scriptConstats.length" class="text-[10px] text-slate-600">
          Dates indicatives, alignées sur la grille de simulation — le booking retient
          celles du calendrier CONSTAT du script.
        </p>
      </div>
    </div>

    <!-- ── Booking ─────────────────────────────────────────── -->
    <div class="card">
      <div v-if="bookingError"
        class="bg-red-900/30 border border-red-700/50 rounded-lg px-4 py-3 mb-3 text-red-300 text-sm">
        ⚠ {{ bookingError }}
      </div>
      <div v-if="bookedDeal"
        class="bg-emerald-900/30 border border-emerald-700/50 rounded-lg px-4 py-3 mb-3">
        <p class="text-emerald-400 font-semibold text-sm">✓ Deal booké — {{ bookedDeal.reference }}</p>
        <p class="text-slate-400 text-xs mt-1">
          Rendez-vous dans l'onglet Events pour renseigner les spots initiaux (S₀) et suivre les constatations.
        </p>
        <button class="btn-secondary text-xs mt-2 px-3 py-1"
          @click="$emit('go-events', bookedDeal.id)">
          → Voir les Events
        </button>
      </div>
      <!-- Une fois le deal booké, le bouton de booking disparaît : re-cliquer
           créait un second deal identique sous une nouvelle référence, sans
           rien pour le signaler. Booker deux fois le même produit reste
           légitime (deux clients), d'où le lien de réarmement explicite
           plutôt qu'un blocage. -->
      <template v-if="existingDeal">
        <RouterLink :to="`/booking?deal=${existingDeal.id}`"
          class="btn-primary w-full py-3 text-sm font-bold block text-center">
          📋 Voir le deal {{ existingDeal.reference }}
        </RouterLink>
        <button class="text-[11px] text-slate-500 hover:text-slate-300 underline mt-2 w-full text-center"
          @click="rearmBooking">
          Booker un autre deal à partir de ce pricing
        </button>
      </template>
      <button v-else class="btn-primary w-full py-3 text-sm font-bold"
        :disabled="dealsStore.loading"
        @click="book">
        <span v-if="dealsStore.loading"
          class="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin inline-block mr-2"></span>
        {{ dealsStore.loading ? 'Booking en cours…' : '📋 Booker le deal' }}
      </button>
    </div>

  </div>
</template>

<script setup>
import { ref, reactive, computed, watch, onMounted, nextTick } from 'vue'
import { RouterLink } from 'vue-router'
import { usePricingStore } from '../stores/pricing.js'
import { useDealsStore } from '../stores/deals.js'
import { useAuthStore } from '../stores/auth.js'
import { useDemoModeStore } from '../stores/demoMode.js'
import { apiFetch } from '../utils/api.js'
import HelpTip from './HelpTip.vue'
import SensitiveValue from './SensitiveValue.vue'
import ObservationSchedule from './ObservationSchedule.vue'
import { underlyingGroups, ensureUnderlyings } from '../data/commonUnderlyings.js'
import { formatPercent, formatNumber, formatInt, formatMoneyRound, formatDate } from '../utils/format.js'

// Catalogue de sous-jacents : chargé depuis la base au montage.
onMounted(ensureUnderlyings)

const emit = defineEmits(['go-events'])

const store = usePricingStore()
const dealsStore = useDealsStore()
const auth = useAuthStore()
const demo = useDemoModeStore()

const today = new Date().toISOString().split('T')[0]

function addBizDays(isoDate, n) {
  const d = new Date(isoDate)
  let added = 0
  while (added < n) {
    d.setDate(d.getDate() + 1)
    if (d.getDay() !== 0 && d.getDay() !== 6) added++
  }
  return d.toISOString().split('T')[0]
}

// Eligible counterparties (admin-managed catalog, active only)
const counterparties = ref([])
onMounted(async () => {
  try {
    const res = await apiFetch('/api/deals/counterparties')
    if (res.ok) counterparties.value = await res.json()
  } catch { /* list stays empty — the select just shows the placeholder */ }
})

const form = reactive({
  sens: 'vente',
  contrepartie: '',
  product_type: '',
  fixing_policy: 'AUTO_YAHOO',
  fair_value: 0,
  price_traded: 0,
  trade_date: store.globalParams.trade_date || today,
  strike_date: store.globalParams.strike_date || today,
  value_date: addBizDays(today, 2),
  payment_date: '',
})

// ── Sous-jacents (picker — identité, la calibration se fait dans Marché & Paramètres) ──
const activeUIdx = computed(() => store.activeUnderlyingIdx)
const activeU = computed(() => store.underlyings[activeUIdx.value] ?? store.underlyings[0])

function onAddUnderlying() {
  store.addUnderlying()
}

function onRemoveUnderlying() {
  store.removeUnderlying(activeUIdx.value)
}

// Picking from the curated dropdown is a deliberate, discrete action —
// always worth auto-fetching σ/q/corr, no need to also click "Charger".
function onTickerSelect(ticker) {
  activeU.value.ticker = ticker
  if (ticker) store.loadYfOne(activeUIdx.value)
}

// Manual typing needs a "did it actually change" guard on blur, otherwise
// tabbing through the field with no edit would re-fetch every time.
let _tickerBeforeEdit = ''
function onTickerFocus() {
  _tickerBeforeEdit = activeU.value.ticker
}
function onTickerBlur() {
  activeU.value.ticker = activeU.value.ticker.trim().toUpperCase()
  if (activeU.value.ticker && activeU.value.ticker !== _tickerBeforeEdit) {
    store.loadYfOne(activeUIdx.value)
  }
}

// ── Calendrier CONSTAT (mode expert) ──────────────────────
const tenorStr = t => (t && t.value) ? `${t.value}${t.unit}` : null

// Corps de requete de l apercu : ObservationSchedule appelle le serveur
// lui-meme, ce composant ne fait que lui donner la forme attendue.
function scheduleRequest(c) {
  const v = store.constatOverrides[c.name] || {}
  return {
    start_date: v.start_date, end_date: v.end_date, roll_date: v.roll_date,
    frequency: tenorStr(v.frequency), stub: v.stub,
    sub_frequency: tenorStr(v.sub_frequency) || null,
    currency: form.devise || store.globalParams.deal_ccy || 'EUR',
    convention: v.convention || 'none',
    settlement_lag: v.settlement_lag || 0,
  }
}

watch(() => store.result, (r) => {
  if (r) {
    form.fair_value = parseFloat((r.price * 100).toFixed(4))
    if (!form.price_traded) form.price_traded = form.fair_value
  }
}, { immediate: true })

// Les trois dates du deal vivent à deux endroits : le formulaire de cet
// onglet et le contexte de pricing. La synchronisation va DANS LES DEUX SENS.
// Elle n'allait que du store vers le formulaire ; le retour reposait sur un
// @change du DOM, qui ne se déclenche pas sur une écriture programmatique et
// laissait le moteur pricer sur une date de strike périmée — donc valoriser à
// l'émission un produit déjà en cours de vie, sans que rien ne le signale.
// L'assignation conditionnelle suffit à couper la boucle : réécrire la même
// valeur ne redéclenche pas le watcher.
// Déclaré AVANT tout watcher immédiat qui le touche. Il vivait plus bas :
// la synchronisation des dates, elle aussi immédiate, le lisait dans sa zone
// morte temporelle. L'exception passait inaperçue, le drapeau restait faux, et
// la proposition à J+3 écrasait la date de règlement d'un script rouvert.
const paymentDateDirty = ref(false)

for (const champ of ['trade_date', 'strike_date', 'value_date', 'payment_date']) {
  watch(() => store.globalParams[champ], (v) => {
    if (v && form[champ] !== v) form[champ] = v
    // Une date de règlement qui arrive du contexte — script rouvert depuis la
    // bibliothèque, deal rechargé — est un fait, pas un défaut. Sans ce
    // drapeau, la proposition à J+3 ouvrés l'écrasait au chargement : un
    // term sheet à J+7 revenait silencieusement à J+3.
    if (champ === 'payment_date' && v) paymentDateDirty.value = true
  }, { immediate: true })
  watch(() => form[champ], (v) => {
    if (v && store.globalParams[champ] !== v) store.globalParams[champ] = v
  })
}

// ── Nominal formatting ────────────────────────────────────
const nominalRaw = ref('1 000 000')
const nominalValue = computed(() => {
  return parseFloat(nominalRaw.value.replace(/\s/g, '').replace(',', '.')) || 0
})

function formatNominal() {
  const n = nominalValue.value
  if (n) nominalRaw.value = formatInt(n)
}
function unformatNominal(event) {
  nominalRaw.value = String(nominalValue.value || '')
  // Select the whole field on focus so typing a new nominal replaces it
  // instead of inserting at the cursor — without this, clicking into an
  // already-filled field and typing silently CONCATENATES onto the
  // existing value (e.g. 1 000 000 + 1000000 -> 10 000 001 000 000).
  const el = event?.target
  if (el) nextTick(() => el.select())
}
onMounted(() => formatNominal())

// Handoff from RfqView.vue's "Booker cette réponse" (see pricing.js:
// loadFromRfq) — contrepartie/prix traité de la réponse retenue, nominal/
// product_type/fair value de la RFQ.
//
// A watch, not a read at setup: this component is v-if'd on store.leftTab,
// which survives navigation. If the Deal tab was already open, DealTab is
// created BEFORE Pricer.vue's async onMounted has even fetched the RFQ, so a
// setup-time read finds nothing and the prefill is silently lost. immediate
// covers the opposite order (prefill already waiting when we mount), and
// nulling it after applying keeps it from being replayed onto a later deal.
const rfqPrefillAt = ref(null)
// Provider whose quote won, when no eligible counterparty could be resolved
// from it — the field stays empty and the banner names the provider so the
// desk knows what to pick instead of facing a blank required select.
const rfqUnmatchedProvider = ref('')
watch(() => store.pendingDealPrefill, (prefill) => {
  if (!prefill) return
  const { nominal, fair_value_at, rfq_provider_label, ...formFields } = prefill
  Object.assign(form, formFields)
  if (nominal != null) nominalRaw.value = formatInt(nominal)
  rfqPrefillAt.value = fair_value_at || null
  rfqUnmatchedProvider.value = (rfq_provider_label && !formFields.contrepartie)
    ? rfq_provider_label : ''
  // A settlement date that came with the deal is a fact, not a default — the
  // maturity watch below must not overwrite a non-standard one.
  if (formFields.payment_date) paymentDateDirty.value = true
  store.pendingDealPrefill = null
}, { immediate: true })

// True while fair_value is still the RFQ's stored model price rather than a
// price computed here — cleared by the store.result watch above on the first
// ▶ Pricer. Drives the "à revérifier" warning in the RFQ banner.
const fairValueFromRfq = computed(() => !!rfqPrefillAt.value && !store.result)
const rfqPriceAgeDays = computed(() => {
  if (!rfqPrefillAt.value) return 0
  return Math.floor((Date.now() - new Date(rfqPrefillAt.value)) / 86400000)
})

function formatCcy(val) {
  return formatMoneyRound(val, store.globalParams.deal_ccy)
}

// ── Computed ─────────────────────────────────────────────
const margin = computed(() => (form.price_traded || 0) - (form.fair_value || 0))

// Mode expert (calendrier CONSTAT) : la maturité est la date de fin la plus
// tardive parmi les calendriers du script, pas value_date + T. Toujours
// dérivée, jamais éditable directement — sinon elle pourrait diverger de ce
// que le moteur a réellement priçé.
const scheduleEndDates = computed(() => {
  return store.scriptConstats
    .filter(c => c.kind !== 'single')
    .map(c => store.constatOverrides[c.name]?.end_date)
    .filter(Boolean)
})

const maturityDate = computed(() => {
  if (scheduleEndDates.value.length > 0) {
    return scheduleEndDates.value.reduce((max, d) => (d > max ? d : max))
  }
  // La maturité se compte depuis le STRIKE : c'est la constatation initiale
  // qui ouvre la vie du produit, pas le règlement du nominal. Ancrer sur la
  // value date décalait toute l'échéance de (value − strike) — quelques jours
  // sur un produit réel, systématiquement dans le même sens.
  const origine = form.strike_date || form.value_date
  if (!origine || !store.globalParams.T) return ''
  const d = new Date(origine)
  d.setDate(d.getDate() + Math.round(store.globalParams.T * 365.25))
  return d.toISOString().split('T')[0]
})

// Payment date par défaut = maturité + 3j ouvrés, l'usage courant. Le
// calendrier vient du serveur et dépend de la devise : un 14 juillet ou un
// lundi de Pâques n'est pas un jour de règlement, et un décompte local qui ne
// saute que les week-ends proposerait une date fermée. Reste éditable pour un
// délai non standard — dès que l'utilisateur y touche, on arrête de l'écraser.
const SETTLEMENT_LAG_DEFAULT = 3

async function proposePaymentDate(maturite) {
  if (!maturite || paymentDateDirty.value) return
  const devise = form.devise || store.globalParams.deal_ccy || 'EUR'
  try {
    const res = await fetch('/api/calendar/resolve', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ date: maturite, currency: devise,
                             business_days: SETTLEMENT_LAG_DEFAULT }),
    })
    if (res.ok) { form.payment_date = (await res.json()).date; return }
  } catch { /* serveur muet : on retombe sur le décompte local ci-dessous */ }
  // Repli hors ligne — week-ends seulement, donc potentiellement un jour férié.
  form.payment_date = addBizDays(maturite, SETTLEMENT_LAG_DEFAULT)
}

watch(maturityDate, proposePaymentDate, { immediate: true })

const entityLabel = computed(() => auth.user?.entity_id ? `Entité #${auth.user.entity_id}` : 'N/A')

// Dates de constatation issues du calendrier CONSTAT, et clôtures relevées à
// ces dates. Deux choses que le tableau affichait en tirets faute de les avoir.
const datesCalendrier = ref([])
const closesPassees = ref({})   // { 'YYYY-MM-DD': { ticker: cours } }

async function chargerCalendrier() {
  const calendriers = store.scriptConstats.filter(c => c.kind !== 'single')
  if (!calendriers.length) { datesCalendrier.value = []; return }
  const toutes = new Set()
  for (const c of calendriers) {
    try {
      const res = await fetch('/api/schedule/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(scheduleRequest(c)),
      })
      if (!res.ok) continue
      const data = await res.json()
      // La première date est le début de période, pas une observation.
      ;(data.dates || []).slice(1).forEach(d => toutes.add(d))
    } catch { /* calendrier incomplet : on retombe sur les flux */ }
  }
  datesCalendrier.value = [...toutes].sort()
}

async function chargerCloturesPassees() {
  const todayStr = new Date().toISOString().split('T')[0]
  // Les mêmes dates que le tableau affiche — calendrier CONSTAT quand il y en
  // a un, sinon celles déduites des flux. Se limiter au calendrier laissait
  // les colonnes S₀ vides sur tout script en mode Normal, qui n'en a pas.
  // Le strike en fait partie : c'est la constatation la plus utile à relire.
  const jours = new Set(datesObservations.value)
  if (form.strike_date) jours.add(form.strike_date)
  const passees = [...jours].filter(d => d <= todayStr).sort()
  const tickers = store.underlyings.map(u => u.ticker).filter(Boolean)
  if (!passees.length || !tickers.length) { closesPassees.value = {}; return }
  try {
    const q = new URLSearchParams({ tickers: tickers.join(','),
                                     start: form.strike_date || passees[0], end: todayStr })
    const res = await fetch(`/api/finance/hist_prices?${q}`)
    if (!res.ok) return
    const data = await res.json()
    const dates = data.dates || []
    const releve = {}
    for (const jour of passees) {
      // Dernière clôture connue à cette date : un jour fermé n'a pas de cours,
      // c'est celui d'avant qui fait foi — la même convention que le replay.
      let idx = -1
      for (let i = 0; i < dates.length; i++) {
        if (dates[i] <= jour) idx = i; else break
      }
      if (idx < 0) continue
      releve[jour] = {}
      for (const tk of tickers) {
        const serie = data.prices?.[tk]
        if (serie && serie[idx]) releve[jour][tk] = serie[idx]
      }
    }
    closesPassees.value = releve
  } catch { /* pas d'historique : les cellules restent vides */ }
}

watch(() => [store.scriptConstats, store.constatOverrides, form.strike_date],
      chargerCalendrier, { deep: true, immediate: true })

const observationTimes = computed(() => {
  if (!store.result?.flux_table) return []
  return [...new Set(Object.values(store.result.flux_table).map(e => e.t))].sort((a, b) => a - b)
})

function addDays(isoDate, days) {
  const d = new Date(isoDate)
  d.setDate(d.getDate() + Math.round(days))
  return d.toISOString().split('T')[0]
}

// Dates de constatation du produit, quelle que soit la façon dont le script
// les exprime : le calendrier CONSTAT fait foi quand il existe, sinon on les
// reconstruit depuis les temps de flux, ancrés sur le strike. Une seule
// source pour le tableau et pour le relevé des clôtures passées.
const datesObservations = computed(() => {
  if (datesCalendrier.value.length) return datesCalendrier.value
  const origine = form.strike_date
  if (!origine) return []
  // En cours de vie, le Monte Carlo ne simule que la vie restante : les temps
  // de sa table de flux se comptent depuis la DATE DE VALORISATION, pas depuis
  // le strike. Les ancrer sur le strike ramenait la maturité d'un produit de
  // trois ans à dix mois après son émission. Les constatations déjà passées
  // ne sont pas dans cette table — elles sont dans realized_flows, elles
  // comptées depuis le strike.
  const res = store.result
  if (res?.in_life && res.valuation_date) {
    const passees = [...new Set((res.past?.realized_flows || []).map(f => f.t))]
      .sort((a, b) => a - b)
      .map(t => addDays(origine, t * 365.25))
    const futures = observationTimes.value.map(t => addDays(res.valuation_date, t * 365.25))
    return [...passees, ...futures]
  }
  return observationTimes.value.map(t => addDays(origine, t * 365.25))
})

watch(datesObservations, chargerCloturesPassees, { immediate: true })

const previewEvents = computed(() => {
  if (!store.result && !datesCalendrier.value.length) return []
  const todayStr = new Date().toISOString().split('T')[0]
  const origine = form.strike_date || todayStr
  const events = []

  // Ligne 0 : strike date (fixing S₀)
  events.push({
    label: 'Strike / Fixing S₀',
    date: origine,
    t: 0,
    isFuture: origine > todayStr,
  })

  // Les dates du CALENDRIER CONTRACTUEL quand il y en a un. Auparavant elles
  // étaient dérivées de la table de flux du Monte Carlo, donc des pas de la
  // grille hebdomadaire : jusqu'à trois jours de décalage sur chaque date,
  // et comptés depuis la value date alors que l'axe s'ancre sur le strike.
  const lignes = (datesObservations.value.length
      ? datesObservations.value
      : observationTimes.value.map(t => addDays(origine, t * 365.25))
  ).map(date => ({
    date,
    t: Math.round(((new Date(date) - new Date(origine)) / 86400000 / 365.25) * 1e4) / 1e4,
  }))

  lignes.forEach(({ date, t }, idx) => {
    const isLast = idx === lignes.length - 1
    events.push({
      label: isLast ? 'Maturité' : `Obs. ${idx + 1} (${formatNumber(t, 2)}Y)`,
      date,
      t,
      isFuture: date > todayStr,
    })
  })

  return events
})

// ── Validation & booking ──────────────────────────────────
const errors = reactive({})
const bookingError = ref(null)
const bookedDeal = ref(null)

// Le deal existe déjà — soit on vient de le booker, soit on a rouvert un deal
// booké (store.openedDeal, voir pricing.js:loadFromDeal). Dans les deux cas le
// bouton de booking créerait un doublon sous une nouvelle référence.
const existingDeal = computed(() => bookedDeal.value || store.openedDeal)

// Rebooker le même produit reste légitime (deux clients, deux trades) — mais
// ça doit être un geste explicite.
function rearmBooking() {
  bookedDeal.value = null
  store.openedDeal = null
}

function validate() {
  Object.keys(errors).forEach(k => delete errors[k])
  if (!form.contrepartie.trim()) errors.contrepartie = 'Contrepartie requise'
  if (!nominalValue.value || nominalValue.value <= 0) errors.nominal = 'Nominal requis'
  if (!form.price_traded) errors.price_traded = 'Prix traité requis'
  // A zero fair value is never a real product — it means nothing has been
  // priced in this session (the RFQ→booking path arrives with the results
  // cleared). Booking it would set the deal's whole P&L baseline to 0.
  if (!form.fair_value) errors.fair_value = 'Fair value requise — lancez ▶ Pricer, ou saisissez-la'
  return Object.keys(errors).length === 0
}

async function book() {
  bookingError.value = null
  bookedDeal.value = null
  if (!validate()) return

  const underlyings = store.underlyings.map(u => ({
    name: u.name,
    ticker: u.ticker || '',
    ccy: u.ccy,
  }))

  const marketSnapshot = {
    r: store.globalParams.r,
    T: store.globalParams.T,
    model: store.globalParams.model,
    antithetic: store.globalParams.antithetic,
    deal_ccy: store.globalParams.deal_ccy,
    rateModel: store.globalParams.rateModel,
    sigma_r: store.globalParams.sigma_r,
    a_r: store.globalParams.a_r,
    yieldCurve: store.yieldCurve.enabled ? store.yieldCurve.pillars : [],
    // Full underlying objects (not just name/ticker/sigma/q/ccy) so a smile
    // model (Heston/SABR/Local Vol/quanto) survives a reopen — see
    // pricing.js:loadFromDeal and reprice_inputs' "still alive" branch.
    underlyings: store.underlyings.map(u => ({
      ...u,
      // Freeze both the generating assumptions and the exact annual nodes.
      // Lifecycle replay consumes the nodes; q/decay explain how they arose.
      dividendCurve: store.buildDividendCurve(u),
    })),
    corrMatrix: store.corrMatrix,
    // PARAM overrides frozen in STORED units (fractions), same shape the
    // pricing API takes — the lifecycle replay and the watchlist read these,
    // so a deal booked with a degressive M_AC_BAR keeps its real barrier
    // schedule instead of falling back to the script's seed default.
    user_params: store.buildUserParams(),
    // CONSTAT calendar values frozen at booking (raw dates/frequencies, same
    // shape /api/price takes) — without them an expert-mode deal can never be
    // replayed (lifecycle) or residual-MtM'd: the script alone has no dates.
    constats: store.buildConstats(),
  }

  try {
    const deal = await dealsStore.bookDeal({
      sens: form.sens,
      contrepartie: form.contrepartie.trim(),
      devise: store.globalParams.deal_ccy,
      product_type: form.product_type.trim(),
      fixing_policy: form.fixing_policy,
      nominal: nominalValue.value,
      fair_value: form.fair_value,
      price_traded: form.price_traded,
      trade_date: form.trade_date,
      strike_date: form.strike_date,
      value_date: form.value_date,
      maturity_date: maturityDate.value,
      payment_date: form.payment_date,
      T: store.globalParams.T,
      underlyings,
      observation_times: observationTimes.value,
      script_snapshot: store.script,
      script_id: store.currentScriptId || null,
      market_snapshot: marketSnapshot,
      indicative_id: store.currentIndicativeId || null,
      rfq_id: store.currentRfqId || null,
    })
    bookedDeal.value = deal
  } catch (e) {
    bookingError.value = e.message
  }
}
</script>
