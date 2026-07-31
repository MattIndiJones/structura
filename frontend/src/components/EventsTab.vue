<template>
  <div class="flex flex-col gap-5">

    <!-- ═══════════════════════════════════════════════════════════════ -->
    <!-- MODE A — Deal booké sélectionné                                -->
    <!-- ═══════════════════════════════════════════════════════════════ -->
    <template v-if="deal">

      <!-- Résumé du deal -->
      <div class="card">
        <div class="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
          <div>
            <div class="text-slate-500 mb-0.5">Référence</div>
            <div class="font-mono font-semibold text-slate-200">
              {{ deal.reference }} <span class="text-slate-500">v{{ deal.contract_version || 1 }}</span>
            </div>
          </div>
          <div>
            <div class="text-slate-500 mb-0.5">Contrepartie</div>
            <div class="text-slate-200">{{ deal.contrepartie }}</div>
          </div>
          <div>
            <div class="text-slate-500 mb-0.5">Nominal</div>
            <div class="font-mono text-slate-200">{{ formatNominal(deal.nominal) }} {{ deal.devise }}</div>
          </div>
          <div>
            <div class="text-slate-500 mb-0.5">Prix / FV / Marge</div>
            <div class="font-mono">
              <span class="text-slate-200">{{ deal.price_traded.toFixed(2) }}%</span>
              <span class="text-slate-600 mx-1">/</span>
              <span class="text-slate-400">{{ deal.fair_value.toFixed(2) }}%</span>
              <span class="mx-1" :class="deal.margin >= 0 ? 'text-emerald-400' : 'text-red-400'">
                {{ deal.margin >= 0 ? '+' : '' }}{{ deal.margin.toFixed(2) }}%
              </span>
            </div>
          </div>
          <div>
            <div class="text-slate-500 mb-0.5">Trade date</div>
            <div class="font-mono text-slate-300">{{ formatDate(deal.trade_date) }}</div>
          </div>
          <div>
            <div class="text-slate-500 mb-0.5">Strike date</div>
            <div class="font-mono text-slate-300">{{ formatDate(deal.strike_date) }}</div>
          </div>
          <div>
            <div class="text-slate-500 mb-0.5">Value date</div>
            <div class="font-mono text-slate-300">{{ formatDate(deal.value_date) }}</div>
          </div>
          <div>
            <div class="text-slate-500 mb-0.5">Maturité</div>
            <div class="font-mono text-slate-300">{{ formatDate(deal.maturity_date) }}</div>
          </div>
        </div>

        <!-- S₀ — seulement si l'event strike (t=0) existe -->
        <template v-if="strikeEvent">
          <div v-if="hasS0" class="mt-3 pt-3 border-t border-slate-700">
            <div class="text-xs text-slate-500 mb-2">Spots initiaux S₀ (strike date)</div>
            <div class="flex flex-wrap gap-2">
              <div v-for="u in deal.underlyings" :key="u.name"
                class="flex items-center gap-1.5 bg-slate-800 rounded-lg px-3 py-1.5">
                <span class="text-xs text-slate-400 font-mono">{{ u.ticker || u.name }}</span>
                <span class="text-xs font-bold text-slate-200 font-mono">
                  {{ formatSpot(strikeEvent.spots[u.name]) }}
                </span>
              </div>
            </div>
          </div>
          <div v-else class="mt-3 pt-3 border-t border-slate-700">
            <p class="text-xs text-amber-500/80">
              S₀ à renseigner — un Ops Maker doit soumettre le fixing Strike avec sa preuve officielle.
            </p>
          </div>
        </template>

        <!-- Statut + Re-pricer -->
        <div class="mt-3 flex items-center gap-2 flex-wrap">
          <span class="px-2 py-1 rounded border border-slate-700 bg-slate-800 text-xs text-slate-300">
            {{ deal.status }}
          </span>
          <HelpTip text="Le statut contractuel est en lecture seule. Un résultat terminal passe obligatoirement par proposition, validation humaine puis application auditée." />
          <button class="btn-secondary text-xs px-3 py-1.5" @click="reprice" :disabled="repricing">
            <span v-if="repricing"
              class="w-3 h-3 border-2 border-slate-400 border-t-transparent rounded-full animate-spin inline-block mr-1"></span>
            ↺ Re-pricer
          </button>
          <HelpTip width="w-72" text="Recharge le script figé au booking dans le Pricer, avec la maturité restante (T remaining) et les spots normalisés (spot actuel / S₀) comme point de départ — pour obtenir une valorisation mark-to-market actuelle du deal. Vous atterrissez ensuite dans Marché &amp; Paramètres pour lancer le pricing." />
          <span v-if="repriceMsg" class="text-xs"
            :class="repriceMsg.startsWith('⚠') ? 'text-amber-400' : 'text-emerald-400'">
            {{ repriceMsg }}
          </span>
        </div>
      </div>

      <!-- Tableau des constatations (deal booké) -->
      <div class="card">
        <div class="flex items-center justify-between mb-3">
          <div>
            <h2 class="text-xs font-bold text-slate-400 uppercase tracking-wider">
              Constatations ({{ deal.events?.length ?? 0 }})
            </h2>
            <p class="text-[10px] text-slate-600 mt-0.5">
              Sous-jacents figés au booking · {{ deal.underlyings.map(u => u.ticker || u.name).join(', ') }}
            </p>
          </div>
          <button v-if="isDealOwner" class="btn-secondary text-xs px-3 py-1.5"
            :disabled="dealsStore.loading" @click="doRefresh">
            <span v-if="dealsStore.loading"
              class="w-3 h-3 border-2 border-slate-400 border-t-transparent rounded-full animate-spin inline-block mr-1"></span>
            📡 Actualiser monitoring indicatif
          </button>
        </div>

        <div v-if="deal.lifecycle_proposals?.length" class="mb-3 flex flex-col gap-2">
          <div v-for="proposal in deal.lifecycle_proposals" :key="proposal.id"
               class="rounded-lg border border-amber-800/50 bg-amber-950/20 px-3 py-2 flex items-center justify-between gap-3">
            <div class="text-xs">
              <span class="font-semibold text-amber-300">Résolution proposée : {{ proposal.proposed_outcome }}</span>
              <span class="ml-2 text-slate-500">{{ proposal.status }} · source {{ proposal.data_source }}</span>
              <div class="text-[10px] text-slate-500 mt-0.5">
                {{ proposal.result?.event_date || 'date inconnue' }} · l’autorisation Checker applique atomiquement le résultat officiel
              </div>
              <div v-if="proposal.comparison_status" class="text-[10px] mt-0.5"
                   :class="proposal.comparison_status === 'MATCH' ? 'text-emerald-400' : 'text-amber-400'">
                Rejeu officiel : {{ proposal.comparison_status }}
                <span v-if="proposal.official_result?.realized_payout != null">
                  · payout {{ (proposal.official_result.realized_payout * 100).toFixed(4) }}%
                </span>
              </div>
            </div>
            <div class="flex gap-2 shrink-0">
              <button v-if="isOpsChecker && proposal.status === 'PROPOSED'" class="btn-secondary text-xs px-2 py-1"
                      @click="validateProposal(proposal)">Autoriser et appliquer</button>
            </div>
          </div>
        </div>

        <!-- Bandeau résultat refresh -->
        <div v-if="refreshBanner" class="mb-3 px-3 py-2.5 rounded-lg text-xs flex items-start gap-2"
          :class="refreshBanner.type === 'warn'
            ? 'bg-amber-950/50 border border-amber-800/50 text-amber-300'
            : refreshBanner.type === 'error'
              ? 'bg-red-950/50 border border-red-800/50 text-red-300'
              : 'bg-emerald-950/50 border border-emerald-800/50 text-emerald-300'">
          <span class="shrink-0">{{ refreshBanner.icon }}</span>
          <span>{{ refreshBanner.text }}</span>
        </div>

        <!-- Bandeau sauvegarde spot -->
        <div v-if="saveMsg" class="mb-3 px-3 py-2 rounded-lg text-xs whitespace-pre-line bg-blue-950/40 border border-blue-800/50 text-blue-300">
          {{ saveMsg }}
        </div>

        <div class="overflow-x-auto table-shell" tabindex="0" role="region">
          <table class="w-full text-xs border-collapse">
            <thead>
              <tr class="border-b border-slate-700">
                <th class="text-left text-slate-500 font-medium pb-2 pr-3">#</th>
                <th class="text-left text-slate-500 font-medium pb-2 pr-3 whitespace-nowrap">Label</th>
                <th class="text-left text-slate-500 font-medium pb-2 pr-3 whitespace-nowrap">Date</th>
                <th class="text-left text-slate-500 font-medium pb-2 pr-3 whitespace-nowrap num">T (Y)</th>
                <th v-for="u in deal.underlyings" :key="u.name"
                  class="text-left text-slate-500 font-medium pb-2 pr-3 whitespace-nowrap">
                  {{ u.ticker || u.name }}
                  <span class="text-slate-600 font-normal ml-1">officiel / indicatif</span>
                </th>
                <th class="text-left text-slate-500 font-medium pb-2 pr-3">Fixing
                  <HelpTip text="Yahoo est uniquement indicatif. Un Ops Maker soumet un fixing candidat avec sa preuve ; un Ops Checker distinct le valide avant toute résolution." />
                </th>
                <th class="text-left text-slate-500 font-medium pb-2">Statut
                  <HelpTip text="futur = date pas encore atteinte. observé = spot constaté normalement. callé = ce constat a déclenché le rappel anticipé du produit. ki = barrière de knock-in franchie à ce constat. final = constat de maturité." />
                </th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="!deal.events?.length">
                <td :colspan="4 + (deal.underlyings?.length ?? 1) + 2"
                  class="py-6 text-center text-slate-600 italic text-xs">
                  Aucune constatation.
                </td>
              </tr>
              <tr v-for="ev in deal.events" :key="ev.id"
                :class="[
                  'border-b border-slate-800/50 hover:bg-slate-800/20 transition-colors',
                  ev.t_years === 0 ? 'bg-amber-950/20' : '',
                  savingEventId === ev.id ? 'opacity-40' : '',
                  ev.event_date > today && ev.t_years !== 0 ? 'opacity-50' : '',
                ]">
                <td class="py-2 pr-3 text-slate-500">{{ ev.event_index + 1 }}</td>
                <td class="py-2 pr-3 whitespace-nowrap">
                  <span :class="ev.t_years === 0 ? 'text-amber-400 font-semibold' : 'text-slate-300'">
                    {{ ev.label }}
                  </span>
                </td>
                <td class="py-2 pr-3 font-mono text-slate-300 whitespace-nowrap">
                  {{ formatDate(ev.event_date) }}
                  <span v-if="ev.event_date === today" class="ml-1 text-amber-400 text-[10px]">aujourd'hui</span>
                </td>
                <td class="py-2 pr-3 font-mono num text-slate-400">{{ ev.t_years.toFixed(2) }}</td>
                <td v-for="u in deal.underlyings" :key="u.name" class="py-2 pr-3">
                  <div class="flex items-center gap-1.5">
                    <span class="w-24 text-xs font-mono"
                          :class="ev.spots[u.name] ? 'text-slate-200' : 'text-slate-600'">
                      {{ ev.spots[u.name] != null ? formatSpot(ev.spots[u.name]) : '—' }}
                    </span>
                    <span v-if="perf(ev, u)" class="text-[10px] font-mono shrink-0"
                      :class="perfClass(ev, u)">
                      {{ perf(ev, u) }}
                    </span>
                  </div>
                  <div v-if="ev.indicative_spots?.[u.name]" class="text-[10px] text-blue-400 mt-0.5 font-mono">
                    indic. {{ formatSpot(ev.indicative_spots[u.name]) }}
                  </div>
                </td>
                <td class="py-2 pr-3">
                  <span :class="sourceClass(ev.source)"
                    class="px-1.5 py-0.5 rounded text-[10px] font-medium">
                    {{ ev.fixing_status }}<span v-if="ev.fixing_version"> · v{{ ev.fixing_version }}</span>
                  </span>
                  <div v-if="ev.fixing_provider" class="text-[10px] text-slate-500 mt-1">
                    {{ ev.fixing_provider }} · {{ ev.fixing_external_reference }}
                  </div>
                  <details v-if="ev.current_fixing_version_id" class="mt-1 text-[10px] text-slate-500 max-w-80">
                    <summary class="cursor-pointer text-cyan-400 hover:text-cyan-300">
                      Contrôler la provenance et l’historique
                    </summary>
                    <div class="mt-1.5 rounded border border-slate-700 bg-slate-950/70 p-2 space-y-1">
                      <div><span class="text-slate-600">Source :</span> {{ ev.fixing_provider }} / {{ ev.fixing_source_type }}</div>
                      <div><span class="text-slate-600">Référence :</span> {{ ev.fixing_external_reference }}</div>
                      <div><span class="text-slate-600">Observation :</span> {{ ev.fixing_observed_at }} · {{ ev.fixing_timezone }}</div>
                      <div><span class="text-slate-600">Convention :</span> {{ ev.fixing_venue }} · {{ ev.fixing_calendar }}</div>
                      <div>
                        <span class="text-slate-600">Instruments / unités :</span>
                        <span v-for="(underlying, index) in deal.underlyings" :key="underlying.name">
                          {{ index ? ' · ' : '' }}{{ underlying.name }}
                          ({{ underlying.ticker || 'identifiant contractuel' }}, {{ underlying.ccy || deal.devise }})
                          = {{ ev.spots?.[underlying.name] }}
                        </span>
                      </div>
                      <div><span class="text-slate-600">Maker :</span> utilisateur #{{ ev.fixing_entered_by }} · {{ ev.fixing_entered_at }}</div>
                      <div><span class="text-slate-600">Motif :</span> {{ ev.fixing_reason }}</div>
                      <template v-if="currentFixingVersion(ev)">
                        <div>
                          <span class="text-slate-600">Pièce :</span>
                          {{ currentFixingVersion(ev).evidence_filename }}
                          ({{ formatEvidenceSize(currentFixingVersion(ev).evidence_size_bytes) }})
                        </div>
                        <button class="text-blue-400 hover:text-blue-300"
                                @click="downloadEvidence(ev, currentFixingVersion(ev))">
                          Télécharger et contrôler la pièce archivée
                        </button>
                      </template>
                      <div class="break-all font-mono"><span class="text-slate-600">SHA preuve :</span> {{ ev.fixing_evidence_sha256 }}</div>
                      <div class="break-all font-mono"><span class="text-slate-600">SHA record :</span> {{ ev.fixing_record_sha256 }}</div>
                      <div v-if="ev.fixing_versions?.length" class="pt-1 border-t border-slate-800">
                        <div class="text-slate-600 mb-0.5">Historique immuable :</div>
                        <div v-for="version in ev.fixing_versions" :key="version.id" class="font-mono">
                          v{{ version.version }} · {{ version.status }} · Maker #{{ version.entered_by }}
                          <span v-if="version.validated_by"> · Checker #{{ version.validated_by }}</span>
                          <span v-if="version.rejected_by"> · rejetée par #{{ version.rejected_by }}</span>
                        </div>
                      </div>
                    </div>
                  </details>
                  <button v-if="canSubmitFixing(ev)"
                          class="block mt-1 text-[10px] text-blue-400 hover:text-blue-300"
                          @click="openFixingForm(ev)">
                    {{ ev.fixing_version ? `Corriger la v${ev.fixing_version}` : 'Saisir avec preuve' }}
                  </button>
                  <button v-if="canValidateFixing(ev)"
                          class="block mt-1 text-[10px] text-emerald-400 hover:text-emerald-300"
                          @click="validateEventFixing(ev)">Valider le fixing</button>
                  <button v-if="canValidateFixing(ev)"
                          class="block mt-1 text-[10px] text-red-400 hover:text-red-300"
                          @click="rejectEventFixing(ev)">Rejeter le fixing</button>
                </td>
                <td class="py-2">
                  <span class="text-[10px] bg-slate-800 border border-slate-700 rounded px-1.5 py-0.5 text-slate-300">
                    {{ ev.status }}
                  </span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <div v-if="fixingEvent" class="mt-4 rounded-lg border border-blue-800/50 bg-blue-950/20 p-4">
          <div class="flex items-start justify-between gap-3 mb-3">
            <div>
              <h3 class="text-xs font-semibold text-blue-300">
                {{ fixingEvent.fixing_version ? `Correction du fixing v${fixingEvent.fixing_version}` : 'Nouveau fixing candidat' }}
              </h3>
              <p class="text-[10px] text-slate-500 mt-0.5">
                {{ fixingEvent.label }} · {{ fixingEvent.event_date }} · la saisie restera candidate jusqu’au contrôle d’un Checker distinct
              </p>
            </div>
            <button class="btn-ghost text-xs" @click="closeFixingForm">Fermer</button>
          </div>

          <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            <div v-for="u in deal.underlyings" :key="u.name" class="flex flex-col gap-1">
              <label class="label">Fixing {{ u.ticker || u.name }}</label>
              <input v-model.number="fixingForm.spots[u.name]" type="number" step="any"
                     class="input" placeholder="Valeur strictement positive" />
            </div>
            <div class="flex flex-col gap-1">
              <label class="label">Fournisseur officiel</label>
              <select v-model="fixingForm.provider" class="select">
                <option v-for="provider in fixingProviders" :key="provider" :value="provider">
                  {{ provider }}
                </option>
              </select>
            </div>
            <div class="flex flex-col gap-1">
              <label class="label">Type de source</label>
              <select v-model="fixingForm.source_type" class="select">
                <option value="MESSAGE">Message</option>
                <option value="FILE">Fichier</option>
                <option value="API">API</option>
                <option value="PLATFORM">Plateforme</option>
                <option value="CALCULATION_AGENT">Agent de calcul</option>
                <option value="OTHER">Autre</option>
              </select>
            </div>
            <div class="flex flex-col gap-1">
              <label class="label">Référence externe</label>
              <input v-model="fixingForm.external_reference" class="input" placeholder="Message, fichier ou batch" />
            </div>
            <div class="flex flex-col gap-1">
              <label class="label">Observation avec timezone</label>
              <input v-model="fixingForm.observed_at" class="input font-mono"
                     placeholder="2026-07-31T17:30:00+02:00" />
            </div>
            <div class="flex flex-col gap-1">
              <label class="label">Timezone de marché</label>
              <input v-model="fixingForm.timezone" class="input" placeholder="Europe/Zurich" />
            </div>
            <div class="flex flex-col gap-1">
              <label class="label">Place / convention</label>
              <input v-model="fixingForm.venue" class="input" placeholder="Official close" />
            </div>
            <div class="flex flex-col gap-1">
              <label class="label">Calendrier</label>
              <input v-model="fixingForm.calendar" class="input" placeholder="TARGET, SIX…" />
            </div>
            <div class="flex flex-col gap-1 sm:col-span-2">
              <label class="label">Pièce source officielle (5 Mo maximum)</label>
              <input type="file" class="input" @change="captureEvidence" />
              <div v-if="fixingForm.evidence_filename" class="text-[10px] text-slate-500">
                {{ fixingForm.evidence_filename }} · {{ formatEvidenceSize(fixingForm.evidence_size_bytes) }}
              </div>
            </div>
            <div class="flex flex-col gap-1 sm:col-span-2 lg:col-span-3">
              <label class="label">SHA-256 calculé depuis la pièce archivée</label>
              <input v-model="fixingForm.evidence_sha256" class="input font-mono" readonly
                     placeholder="Sélectionnez une pièce source" />
            </div>
            <div class="flex flex-col gap-1 sm:col-span-2 lg:col-span-3">
              <label class="label">Motif de capture / correction</label>
              <textarea v-model="fixingForm.reason" class="input min-h-20"
                        placeholder="Décrivez l’origine de la donnée et la raison de la saisie"></textarea>
            </div>
          </div>
          <div class="mt-3 flex items-center gap-2">
            <button class="btn-primary text-xs px-3 py-1.5" :disabled="savingEventId === fixingEvent.id"
                    @click="submitFixing">
              {{ fixingEvent.fixing_version ? 'Soumettre la correction' : 'Soumettre au Checker' }}
            </button>
            <span class="text-[10px] text-slate-500">Tous les champs de provenance sont obligatoires.</span>
          </div>
        </div>

        <p v-if="allEventsFuture && deal.events?.length" class="mt-3 text-[11px] text-slate-600 italic">
          Tous les événements sont futurs — le formulaire de fixing officiel sera disponible pour
          l’Ops Maker après chaque date de constatation.
        </p>
      </div>

      <div class="card">
        <div class="flex items-center justify-between mb-3">
          <div>
            <h2 class="text-xs font-bold text-slate-400 uppercase tracking-wider">Amendements gouvernés</h2>
            <p class="text-[10px] text-slate-600 mt-0.5">
              Maker distinct du checker · version contractuelle · application exactement une fois
            </p>
          </div>
        </div>

        <div v-if="isDealOwner" class="grid grid-cols-1 sm:grid-cols-4 gap-2 mb-3">
          <select v-model="amendmentForm.field_name" class="select text-xs">
            <option value="nominal">Nominal</option>
            <option value="contrepartie">Contrepartie</option>
            <option value="price_traded">Prix traité</option>
            <option value="payment_date">Date de paiement</option>
          </select>
          <input v-model="amendmentForm.new_value" class="input text-xs" placeholder="Nouvelle valeur" />
          <input v-model="amendmentForm.reason" class="input text-xs" placeholder="Motif contractuel détaillé" />
          <button class="btn-secondary text-xs" @click="createAmendment">Soumettre au checker</button>
        </div>
        <div v-if="!deal.amendment_requests?.length" class="text-xs text-slate-600">Aucun amendement.</div>
        <div v-else class="flex flex-col gap-2">
          <div v-for="request in deal.amendment_requests" :key="request.id"
               class="rounded-lg border border-slate-800 bg-slate-900/40 px-3 py-2 flex items-center justify-between gap-3">
            <div class="text-xs min-w-0">
              <span class="font-mono text-slate-300">{{ request.field_name }}</span>
              <span class="text-slate-500 mx-1">:</span>
              <span class="text-slate-500">{{ displayValue(request.old_value) }}</span>
              <span class="text-slate-600 mx-1">→</span>
              <span class="text-slate-200">{{ displayValue(request.new_value) }}</span>
              <span class="ml-2 text-[10px]" :class="amendmentStatusClass(request.status)">
                {{ request.status }} · base v{{ request.base_contract_version }}
              </span>
              <div class="text-[10px] text-slate-600 mt-0.5">{{ request.reason }}</div>
            </div>
            <div v-if="canCheck(request)" class="flex gap-1 shrink-0">
              <button v-if="request.status === 'PENDING'" class="btn-secondary text-[10px] px-2 py-1"
                      @click="transitionAmendment(request, 'approve')">Approuver</button>
              <button v-if="request.status === 'PENDING'" class="btn-ghost text-[10px] px-2 py-1 text-red-400"
                      @click="transitionAmendment(request, 'reject')">Rejeter</button>
              <button v-if="request.status === 'APPROVED'" class="btn-primary text-[10px] px-2 py-1"
                      @click="transitionAmendment(request, 'apply')">Appliquer</button>
            </div>
          </div>
        </div>
      </div>

      <div class="card">
        <div class="flex items-center justify-between gap-3 mb-3">
          <div>
            <h2 class="text-xs font-bold text-slate-400 uppercase tracking-wider">Piste d’audit</h2>
            <p class="text-[10px] text-slate-600 mt-0.5">Décisions, refus, sources et motifs persistés</p>
          </div>
          <div class="flex gap-2">
            <select v-model="auditResult" class="select text-xs py-1" @change="loadAudit">
              <option value="">Tous les résultats</option>
              <option value="SUCCESS">SUCCESS</option>
              <option value="REJECTED">REJECTED</option>
              <option value="ERROR">ERROR</option>
            </select>
            <button class="btn-secondary text-xs px-2 py-1" @click="loadAudit">Actualiser</button>
            <button class="btn-ghost text-xs px-2 py-1" @click="exportAudit">Exporter CSV</button>
          </div>
        </div>
        <div v-if="!dealsStore.auditEvents.length" class="text-xs text-slate-600">Aucun événement d’audit.</div>
        <div v-else class="overflow-x-auto table-shell max-h-72">
          <table class="w-full text-[11px]">
            <thead class="sticky top-0 bg-slate-900">
              <tr class="text-left text-slate-500 border-b border-slate-800">
                <th class="py-1.5 pr-3 font-medium">Date</th>
                <th class="py-1.5 pr-3 font-medium">Action</th>
                <th class="py-1.5 pr-3 font-medium">Résultat</th>
                <th class="py-1.5 pr-3 font-medium">Objet</th>
                <th class="py-1.5 font-medium">Motif</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in dealsStore.auditEvents" :key="row.id" class="border-b border-slate-800/60">
                <td class="py-1.5 pr-3 font-mono text-slate-500 whitespace-nowrap">{{ formatAuditDate(row.created_at) }}</td>
                <td class="py-1.5 pr-3 font-mono text-slate-300 whitespace-nowrap">{{ row.action }}</td>
                <td class="py-1.5 pr-3" :class="auditResultClass(row.result)">{{ row.result }}</td>
                <td class="py-1.5 pr-3 text-slate-500 whitespace-nowrap">{{ row.object_type }} #{{ row.object_id }}</td>
                <td class="py-1.5 text-slate-400 min-w-64">{{ row.reason || '—' }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

    </template>

    <!-- ═══════════════════════════════════════════════════════════════ -->
    <!-- MODE B — Preview live (aucun deal sélectionné)                 -->
    <!-- ═══════════════════════════════════════════════════════════════ -->
    <template v-else>

      <!-- Pas encore de pricing -->
      <div v-if="!store.result" class="card">
        <p class="text-slate-500 text-sm text-center py-4">
          Lancez un pricing (▶ Pricer) pour visualiser la structure des constatations.
        </p>
      </div>

      <!-- Preview basée sur le pricing en cours -->
      <div v-else class="card">
        <div class="flex items-center justify-between mb-3">
          <div>
            <h2 class="text-xs font-bold text-slate-400 uppercase tracking-wider">
              Structure des constatations
            </h2>
            <p class="text-[10px] text-slate-500 mt-0.5">
              Basée sur le pricing en cours · {{ store.underlyings.length }} sous-jacent(s) ·
              {{ previewEvents.length }} constatation(s)
            </p>
          </div>
          <button class="btn-primary text-xs px-3 py-1.5" @click="goToDeal">
            📋 Booker ce deal →
          </button>
        </div>

        <div class="overflow-x-auto table-shell" tabindex="0" role="region">
          <table class="w-full text-xs border-collapse">
            <thead>
              <tr class="border-b border-slate-700">
                <th class="text-left text-slate-500 font-medium pb-2 pr-3">#</th>
                <th class="text-left text-slate-500 font-medium pb-2 pr-3 whitespace-nowrap">Label</th>
                <th class="text-left text-slate-500 font-medium pb-2 pr-3 whitespace-nowrap">Date indicative</th>
                <th class="text-left text-slate-500 font-medium pb-2 pr-3 whitespace-nowrap num">T (Y)</th>
                <th v-for="u in store.underlyings" :key="u.name"
                  class="text-left text-slate-500 font-medium pb-2 pr-3 whitespace-nowrap">
                  {{ u.ticker || u.name }}
                  <span class="text-slate-600 font-normal ml-1">S₀</span>
                </th>
                <th class="text-left text-slate-500 font-medium pb-2">Statut</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="!previewEvents.length">
                <td :colspan="4 + store.underlyings.length + 1"
                  class="py-6 text-center text-slate-600 italic">
                  Aucune constatation détectée dans le script.
                </td>
              </tr>
              <tr v-for="(ev, i) in previewEvents" :key="i"
                :class="[
                  'border-b border-slate-800/50',
                  ev.t === 0 ? 'bg-amber-950/20' : 'opacity-60',
                ]">
                <td class="py-2 pr-3 text-slate-500">{{ i + 1 }}</td>
                <td class="py-2 pr-3 whitespace-nowrap"
                  :class="ev.t === 0 ? 'text-amber-400 font-semibold' : 'text-slate-300'">
                  {{ ev.label }}
                </td>
                <td class="py-2 pr-3 font-mono text-slate-400 whitespace-nowrap">{{ ev.date }}</td>
                <td class="py-2 pr-3 font-mono num text-slate-400">{{ ev.t.toFixed(2) }}</td>
                <td v-for="u in store.underlyings" :key="u.name" class="py-2 pr-3">
                  <span class="text-slate-700 font-mono text-[10px]">–</span>
                </td>
                <td class="py-2">
                  <span class="text-[10px] text-slate-600">futur</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <p class="text-[10px] text-slate-600 mt-3 pt-3 border-t border-slate-800">
          Les spots S₀ et les dates exactes seront fixés au booking — cliquez "Booker ce deal →" pour
          verrouiller la structure.
        </p>
      </div>

    </template>

  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { useDealsStore } from '../stores/deals.js'
import { usePricingStore } from '../stores/pricing.js'
import { useAuthStore } from '../stores/auth.js'
import HelpTip from './HelpTip.vue'
import { formatDate } from '../utils/format.js'
import { apiFetch } from '../utils/api.js'

const props = defineProps({ initialDealId: { type: Number, default: null } })

const dealsStore = useDealsStore()
const store = usePricingStore()
const authStore = useAuthStore()

const today = new Date().toISOString().split('T')[0]
const repricing = ref(false)
const repriceMsg = ref('')
const savingEventId = ref(null)
const saveMsg = ref('')
const auditResult = ref('')
const amendmentForm = reactive({ field_name: 'nominal', new_value: '', reason: '' })
const fixingEventId = ref(null)
const fixingProviders = [
  'BLOOMBERG', 'REFINITIV', 'OFFICIAL_EXCHANGE',
  'CALCULATION_AGENT', 'ISSUER_AGENT', 'CUSTODIAN',
]
const fixingForm = reactive({
  spots: {}, provider: 'BLOOMBERG', source_type: 'MESSAGE', external_reference: '',
  observed_at: '', venue: '', calendar: '', timezone: 'UTC',
  evidence_sha256: '', evidence_filename: '',
  evidence_content_type: 'application/octet-stream', evidence_payload_b64: '',
  evidence_size_bytes: 0, reason: '', supersedes_version: null,
})
let saveMsgTimer = null

const deal = computed(() => dealsStore.currentDeal)
const strikeEvent = computed(() => deal.value?.events?.find(e => e.t_years === 0) ?? null)
const hasS0 = computed(() => !!strikeEvent.value && Object.keys(strikeEvent.value.spots).length > 0)
const isDealOwner = computed(() => deal.value?.user_id === authStore.user?.id)
const isOpsMaker = computed(() => authStore.user?.role === 'ops_maker' &&
  deal.value?.entity_id === authStore.user?.entity_id)
const isOpsChecker = computed(() => authStore.user?.role === 'checker' &&
  deal.value?.entity_id === authStore.user?.entity_id &&
  deal.value?.user_id !== authStore.user?.id)
const fixingEvent = computed(() => deal.value?.events?.find(
  event => event.id === fixingEventId.value) ?? null)

const allEventsFuture = computed(() => {
  const evs = deal.value?.events
  if (!evs?.length) return false
  return evs.every(e => e.event_date > today)
})

// ── Preview live (avant booking) ──────────────────────────
function addDays(isoDate, days) {
  const d = new Date(isoDate)
  d.setDate(d.getDate() + Math.round(days))
  return d.toISOString().split('T')[0]
}

const pricingObsTimes = computed(() => {
  if (!store.result?.flux_table) return []
  return [...new Set(Object.values(store.result.flux_table).map(e => e.t))].sort((a, b) => a - b)
})

const previewEvents = computed(() => {
  const base = store.globalParams.value_date || today
  const events = []

  events.push({
    label: 'Strike / Fixing S₀',
    date: addDays(base, -2),
    t: 0,
  })

  pricingObsTimes.value.forEach((t, idx) => {
    const isLast = idx === pricingObsTimes.value.length - 1
    events.push({
      label: isLast ? 'Maturité' : `Obs. ${idx + 1} (${t.toFixed(2)}Y)`,
      date: addDays(base, t * 365.25),
      t,
    })
  })

  return events
})

function goToDeal() {
  store.leftTab = 'deal'
}

// ── Lifecycle ─────────────────────────────────────────────
// Events is scoped to the product currently open in this Pricer session —
// not a picker across every deal ever booked (that's what /booking is for).
// It shows the real, frozen deal only if THIS script has already been
// booked; otherwise it falls back to the live indicative preview (Mode B).
onMounted(async () => {
  await dealsStore.loadDeals()
  const id = props.initialDealId
    ?? (store.currentScriptId
        ? dealsStore.deals.find(d => d.script_id === store.currentScriptId)?.id ?? null
        : null)
  if (id) await selectDeal(id)
})

async function selectDeal(id) {
  dealsStore.refreshStatus = ''
  await dealsStore.selectDeal(id)
  if (dealsStore.currentDeal) await loadAudit()
}

// ── Formatting ────────────────────────────────────────────
function formatNominal(n) {
  return (n || 0).toLocaleString('fr-FR')
}

function formatSpot(s) {
  if (!s) return '–'
  return s.toLocaleString('fr-FR', { maximumFractionDigits: 2 })
}

function s0ForUnderlying(name) {
  return strikeEvent.value?.spots?.[name] ?? 0
}

function perf(ev, u) {
  if (ev.t_years === 0) return null
  const s = ev.spots[u.name]
  const s0 = s0ForUnderlying(u.name)
  if (!s || !s0) return null
  const pct = ((s / s0 - 1) * 100).toFixed(1)
  return `${Number(pct) >= 0 ? '+' : ''}${pct}%`
}

function perfClass(ev, u) {
  const s = ev.spots[u.name], s0 = s0ForUnderlying(u.name)
  if (!s || !s0) return ''
  return s >= s0 ? 'text-emerald-400' : 'text-red-400'
}

function sourceClass(s) {
  if (s === 'auto') return 'bg-blue-900/40 text-blue-400'
  if (s === 'manuel') return 'bg-amber-900/40 text-amber-400'
  return 'bg-slate-700 text-slate-500'
}

// Bandeau refresh
const refreshBanner = computed(() => {
  const s = dealsStore.refreshStatus
  if (!s) return null
  if (s.startsWith('⚠')) return { type: 'error', icon: '⚠', text: s.slice(2).trim() }
  if (s.includes('0 événement')) {
    return {
      type: 'warn', icon: 'ℹ',
      text: 'Aucun événement passé à mettre à jour — les spots peuvent être saisis manuellement.',
    }
  }
  return { type: 'ok', icon: '✓', text: s.replace(/^[✓\s]+/, '') }
})

// ── Event edits ───────────────────────────────────────────
function showSaveMsg(text) {
  saveMsg.value = text
  clearTimeout(saveMsgTimer)
  saveMsgTimer = setTimeout(() => { saveMsg.value = '' }, 2500)
}

function canSubmitFixing(ev) {
  return isOpsMaker.value && deal.value?.user_id !== authStore.user?.id &&
    ev.event_date <= today && ev.fixing_status !== 'APPLIED'
}

function canValidateFixing(ev) {
  return isOpsChecker.value &&
    ['RECEIVED', 'PARTIAL', 'MANUAL_REVIEW_REQUIRED'].includes(ev.fixing_status) &&
    ev.fixing_entered_by !== authStore.user?.id
}

function currentFixingVersion(ev) {
  return ev.fixing_versions?.find(
    version => version.id === ev.current_fixing_version_id) ?? null
}

function formatEvidenceSize(size) {
  if (!size) return '0 octet'
  if (size < 1024) return `${size} octets`
  return `${(size / 1024).toFixed(size < 1024 * 1024 ? 1 : 0)} Ko`
}

async function captureEvidence(event) {
  const file = event.target.files?.[0]
  if (!file) return
  if (file.size > 5 * 1024 * 1024) {
    event.target.value = ''
    showSaveMsg('⚠ Pièce refusée : taille supérieure à 5 Mo. Sélectionnez un export plus compact.')
    return
  }
  const buffer = await file.arrayBuffer()
  const digest = await crypto.subtle.digest('SHA-256', buffer)
  const evidenceSha = Array.from(new Uint8Array(digest))
    .map(byte => byte.toString(16).padStart(2, '0')).join('')
  const reader = new FileReader()
  const payload = await new Promise((resolve, reject) => {
    reader.onload = () => resolve(String(reader.result).split(',', 2)[1] || '')
    reader.onerror = () => reject(reader.error)
    reader.readAsDataURL(file)
  })
  Object.assign(fixingForm, {
    evidence_sha256: evidenceSha,
    evidence_filename: file.name,
    evidence_content_type: file.type || 'application/octet-stream',
    evidence_payload_b64: payload,
    evidence_size_bytes: file.size,
  })
}

async function downloadEvidence(ev, version) {
  try {
    const res = await apiFetch(
      `/api/deals/${deal.value.id}/events/${ev.id}/fixing-versions/${version.id}/evidence`)
    if (!res.ok) {
      const err = await res.json()
      throw new Error(err?.detail?.message || err?.detail || 'Preuve indisponible')
    }
    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = version.evidence_filename || `fixing-v${version.version}`
    link.click()
    URL.revokeObjectURL(url)
  } catch (error) {
    showSaveMsg(`⚠ Téléchargement refusé : ${error.message}`)
  }
}

function openFixingForm(ev) {
  fixingEventId.value = ev.id
  Object.assign(fixingForm, {
    spots: Object.fromEntries(deal.value.underlyings.map(
      underlying => [underlying.name, ev.spots?.[underlying.name] ?? ''])),
    provider: ev.fixing_provider || 'BLOOMBERG',
    source_type: ev.fixing_source_type || 'MESSAGE',
    external_reference: '',
    observed_at: '',
    venue: ev.fixing_venue || '',
    calendar: ev.fixing_calendar || '',
    timezone: ev.fixing_timezone || 'UTC',
    evidence_sha256: '',
    evidence_filename: '',
    evidence_content_type: 'application/octet-stream',
    evidence_payload_b64: '',
    evidence_size_bytes: 0,
    reason: '',
    supersedes_version: ev.fixing_version || null,
  })
}

function closeFixingForm() {
  fixingEventId.value = null
}

async function submitFixing() {
  const ev = fixingEvent.value
  if (!ev) return
  savingEventId.value = ev.id
  try {
    await dealsStore.updateEvent(deal.value.id, ev.id, {
      spots: Object.fromEntries(Object.entries(fixingForm.spots)
        .map(([name, value]) => [name, Number(value)])),
      source: 'manuel',
      provider: fixingForm.provider.trim(),
      source_type: fixingForm.source_type,
      external_reference: fixingForm.external_reference.trim(),
      observed_at: fixingForm.observed_at.trim(),
      venue: fixingForm.venue.trim(),
      calendar: fixingForm.calendar.trim(),
      timezone: fixingForm.timezone.trim(),
      evidence_sha256: fixingForm.evidence_sha256.trim(),
      evidence_filename: fixingForm.evidence_filename,
      evidence_content_type: fixingForm.evidence_content_type,
      evidence_payload_b64: fixingForm.evidence_payload_b64,
      reason: fixingForm.reason.trim(),
      supersedes_version: fixingForm.supersedes_version,
    })
    showSaveMsg(`✓ Fixing v${(ev.fixing_version || 0) + 1} soumis au Checker avec sa preuve`)
    closeFixingForm()
    await loadAudit()
  } catch (e) {
    showSaveMsg(`⚠ Soumission refusée :\n${e.message}`)
  } finally {
    savingEventId.value = null
  }
}

async function validateEventFixing(ev) {
  const reason = window.prompt('Motif de validation du fixing officiel :')
  if (!reason) return
  try {
    await dealsStore.validateFixing(deal.value.id, ev.id, reason)
    showSaveMsg('✓ Fixing officiel validé')
  } catch (e) {
    showSaveMsg(`⚠ Validation refusée : ${e.message}`)
  }
}

async function rejectEventFixing(ev) {
  const reason = window.prompt('Motif obligatoire du rejet de cette version de fixing :')
  if (!reason) return
  try {
    await dealsStore.rejectFixing(deal.value.id, ev.id, reason)
    showSaveMsg('✓ Version de fixing rejetée ; la version officielle précédente a été restaurée si nécessaire')
    await loadAudit()
  } catch (e) {
    showSaveMsg(`⚠ Rejet impossible : ${e.message}`)
  }
}

function displayValue(value) {
  if (value == null) return '—'
  return typeof value === 'object' ? JSON.stringify(value) : String(value)
}

function amendmentStatusClass(status) {
  if (status === 'APPLIED') return 'text-emerald-400'
  if (status === 'REJECTED') return 'text-red-400'
  if (status === 'APPROVED') return 'text-blue-400'
  return 'text-amber-400'
}

function canCheck(request) {
  return ['checker', 'admin'].includes(authStore.user?.role) &&
    request.requested_by !== authStore.user?.id
}

function auditResultClass(result) {
  if (result === 'SUCCESS') return 'text-emerald-400'
  if (result === 'REJECTED') return 'text-amber-400'
  return 'text-red-400'
}

function formatAuditDate(raw) {
  if (!raw) return '—'
  return new Date(raw).toLocaleString('fr-FR')
}

async function loadAudit() {
  if (!deal.value) return
  try {
    await dealsStore.loadAudit(deal.value.id, { result: auditResult.value })
  } catch (e) {
    showSaveMsg(`⚠ Audit indisponible : ${e.message}`)
  }
}

function exportAudit() {
  const rows = dealsStore.auditEvents
  if (!rows.length) return
  const csvCell = value => `"${String(value ?? '').replaceAll('"', '""')}"`
  const lines = [
    ['date', 'action', 'resultat', 'objet', 'objet_id', 'acteur', 'source', 'motif']
      .map(csvCell).join(','),
    ...rows.map(row => [row.created_at, row.action, row.result, row.object_type,
      row.object_id, row.actor_user_id, row.data_source, row.reason]
      .map(csvCell).join(',')),
  ]
  const blob = new Blob([`\uFEFF${lines.join('\n')}`], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `audit-${deal.value.reference}.csv`
  link.click()
  URL.revokeObjectURL(url)
}

async function validateProposal(proposal) {
  const confirmedOutcome = window.prompt(
    'Confirmez indépendamment le résultat officiel en saisissant exactement : callé, ki ou final')
  if (!['callé', 'ki', 'final'].includes((confirmedOutcome || '').trim().toLowerCase())) {
    showSaveMsg('⚠ Confirmation explicite requise : saisissez callé, ki ou final')
    return
  }
  const reason = window.prompt('Motif de validation de la résolution :')
  if (!reason) return
  try {
    await dealsStore.transitionProposal(
      deal.value.id, proposal.id, 'validate', reason,
      confirmedOutcome.trim().toLowerCase())
    showSaveMsg('✓ Résolution autorisée et appliquée atomiquement')
  } catch (e) {
    showSaveMsg(`⚠ Validation refusée : ${e.message}`)
  }
}

async function createAmendment() {
  if (!deal.value || !amendmentForm.new_value || amendmentForm.reason.trim().length < 10) {
    showSaveMsg('⚠ Nouvelle valeur et motif détaillé (10 caractères minimum) requis')
    return
  }
  const numeric = ['nominal', 'price_traded'].includes(amendmentForm.field_name)
  const value = numeric ? Number(amendmentForm.new_value) : amendmentForm.new_value
  if (numeric && (!Number.isFinite(value) || value <= 0)) {
    showSaveMsg('⚠ La nouvelle valeur doit être strictement positive')
    return
  }
  try {
    await dealsStore.requestAmendment(deal.value.id, {
      field_name: amendmentForm.field_name,
      new_value: value,
      reason: amendmentForm.reason.trim(),
    })
    amendmentForm.new_value = ''
    amendmentForm.reason = ''
    showSaveMsg('✓ Demande transmise au checker')
    await loadAudit()
  } catch (e) {
    showSaveMsg(`⚠ Demande refusée : ${e.message}`)
  }
}

async function transitionAmendment(request, action) {
  const labels = { approve: 'approbation', reject: 'rejet', apply: 'application' }
  const reason = window.prompt(`Motif de ${labels[action]} de l’amendement :`)
  if (!reason || reason.trim().length < 10) return
  try {
    await dealsStore.transitionAmendment(
      deal.value.id, request.id, action, reason.trim())
    showSaveMsg(`✓ Amendement ${action === 'apply' ? 'appliqué' : action === 'approve' ? 'approuvé' : 'rejeté'}`)
    await loadAudit()
  } catch (e) {
    showSaveMsg(`⚠ Transition refusée : ${e.message}`)
  }
}

async function doRefresh() {
  if (!deal.value) return
  dealsStore.refreshStatus = ''
  try {
    await dealsStore.refreshEvents(deal.value.id)
  } catch { /* error already in refreshStatus */ }
}

// ── Re-pricer ─────────────────────────────────────────────
async function reprice() {
  if (!deal.value) return
  repricing.value = true; repriceMsg.value = ''
  try {
    const inputs = await dealsStore.getRepriceInputs(deal.value.id)

    // Deal already resolved (callé/échu) — no optionality left to run a
    // Monte Carlo on. Re-simulating from today on the raw script would
    // price it as if it restarted now (AT 1,2,3 means "1/2/3Y from now" to
    // the engine, not from the original inception). Show what was actually
    // realized instead.
    if (inputs.resolved) {
      const payout = inputs.realized_payout != null ? `${(inputs.realized_payout * 100).toFixed(2)}%` : 'inconnu'
      repriceMsg.value = `Prix résiduel : 0% (deal clos) · Remboursement réalisé : ${payout}` +
        (inputs.resolution_date ? ` le ${inputs.resolution_date}` : '')
      return
    }

    store.script = inputs.script_snapshot
    await store.parseScript()
    store.globalParams.T = inputs.T_remaining
    store.globalParams.value_date = deal.value.value_date
    if (inputs.underlyings?.length) {
      store.underlyings = inputs.underlyings.map(u => ({ ...u }))
      store.activeUnderlyingIdx = 0
    }
    if (inputs.corr_matrix?.length) store.corrMatrix = inputs.corr_matrix
    const ms = inputs.market_snapshot || {}
    if (ms.model) store.globalParams.model = ms.model
    if (ms.r != null) store.globalParams.r = ms.r
    const parts = [`T restant: ${inputs.T_remaining.toFixed(2)}Y`]
    const ns = inputs.normalized_spots || {}
    if (Object.keys(ns).length) {
      parts.push(`Spot/S₀: ${Object.entries(ns).map(([n, v]) => `${n}: ${(v * 100).toFixed(1)}%`).join(', ')}`)
    }
    repriceMsg.value = parts.join(' · ')
    store.leftTab = 'params'
  } catch (e) {
    repriceMsg.value = `⚠ ${e.message}`
  } finally {
    repricing.value = false
  }
}
</script>
