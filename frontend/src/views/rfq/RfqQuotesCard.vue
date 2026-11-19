<template>
  <div class="card flex flex-col gap-3">
    <div class="flex items-center justify-between">
      <div class="text-xs font-bold text-slate-400 uppercase tracking-wider">Fournisseurs sollicités</div>
      <div class="flex items-center gap-2">
        <span v-if="bestQuote" class="text-[10px] text-slate-500" :title="sensHint(rfq.current.sens)">
          Meilleure réponse ({{ rfq.current.sens === 'vente' ? 'prix le plus haut' : 'prix le plus bas' }}) :
          <span class="text-slate-300 font-semibold"><SensitiveValue>{{ fmtPrice(bestQuote.price) }}</SensitiveValue></span>
          ({{ providerLabel(bestQuote.provider) }})
        </span>
        <button v-if="!rfq.current.booked_deal && can(rfq.current, 'prepare')" class="btn-secondary text-xs" @click="openAddQuote">+ Ajouter un fournisseur</button>
      </div>
    </div>

    <AlertMessage v-if="mutationError" kind="error" dismissible @dismiss="mutationError = ''; rejectedMutation = null">
      {{ mutationError }}
      <p v-if="rejectedMutation" class="mt-1">Saisie refusée · {{ rejectedMutation.label }} :
        <SensitiveValue>{{ rejectedMutation.value }}</SensitiveValue>.
        {{ rejectedMutation.reloadFailed ? 'Rechargement impossible ; dernière valeur connue affichée.' : 'Valeur enregistrée restaurée.' }}
      </p>
    </AlertMessage>

    <!-- Un AO s'exécute une fois : une fois booké, plus de bouton de
         booking, on renvoie vers le deal. Le serveur refuse le doublon
         de toute façon (deals.py:book_deal, 409). -->
    <div v-if="rfq.current.booked_deal"
         class="flex items-center justify-between gap-3 rounded-lg border border-slate-700 bg-slate-900/40 px-3 py-2">
      <span class="text-xs text-slate-300">
        📋 AO exécuté — deal <DealReferenceLink
          :deal-id="rfq.current.booked_deal.id"
          :reference="rfq.current.booked_deal.reference"
          class="font-mono text-slate-200" />.
      </span>
      <button class="btn-secondary text-xs px-3 py-1.5 shrink-0"
              @click="openBookedDeal">→ Voir le booking</button>
    </div>

    <div v-if="rfq.current.booked_deal && rfq.current.selected_quote_id"
         class="flex items-start gap-3 flex-wrap rounded-lg border border-slate-800 bg-slate-900/40 px-3 py-2">
      <div class="min-w-0 flex-1">
        <div class="text-xs font-bold text-slate-300">
          Motif de sélection figé au booking
          <span v-if="bestQuote && !selectedIsBest" class="ml-1 text-amber-400">
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
        <span v-if="rfq.current.selected_quote_revision !== selectedQuote?.revision" class="font-semibold">
          révision historique à requalifier en cliquant sur Retenir à nouveau.
        </span>
        <span v-if="selectedQuote?.origin === 'NETWORK'">{{ confirmedExecution ? 'accord de traitement confirmé ; ' : 'cotation réseau publiée ; confirmation de traitement requise avant booking. ' }}</span>
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
        <button v-if="!modelPriceRecorded && can(rfq.current, 'price')" class="btn-price-model"
                :disabled="computing" @click="computeModelPrice">
          {{ computing ? 'Calcul…' : 'Calculer prix modèle' }}
        </button>
        <button v-else-if="can(rfq.current, 'book') && (confirmedExecution || (selectedQuote?.origin !== 'NETWORK' && !activeExecution))" class="btn-primary text-xs px-3 py-1.5"
                @click="bookFromRfq">📋 Booker cette réponse</button>
      </div>
    </div>

    <RfqExecutionPanel :rfq="rfq.current" />

    <div v-if="rfq.current.selected_quote_id && !rfq.current.booked_deal && can(rfq.current, 'select')"
         class="flex items-end gap-3 flex-wrap rounded-lg border border-slate-800 bg-slate-900/40 px-3 py-2">
      <div class="min-w-0">
        <div class="text-xs font-bold text-slate-300">
          Motif de sélection
          <span v-if="bestQuote && !selectedIsBest" class="ml-1 text-amber-400">
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

    <SensitiveValue v-else>
    <div class="table-shell" tabindex="0" role="region">
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
              <div v-if="q.origin !== 'NETWORK' && q.identity_status === 'TO_QUALIFY' && !rfq.current.booked_deal && can(rfq.current, 'prepare')" class="flex flex-col gap-1 mt-2 whitespace-normal">
                <span class="text-amber-700">Identité juridique à qualifier</span>
                <select v-model="legalDraft[q.id]" class="select text-xs"><option :value="undefined">Choisir une contrepartie</option><option v-for="legal in legalCounterparties" :key="legal.id" :value="legal.id">{{ legal.name }}</option></select>
                <input v-model="legalReasons[q.id]" class="input text-xs" placeholder="Motif de la qualification" minlength="3" />
                <button class="btn-secondary btn-sm" @click="qualifyQuote(q)">Qualifier l’identité</button>
              </div>
              <span v-if="q.origin === 'NETWORK'" class="badge badge-accent ml-1">Réseau · v{{ q.publication.revision }} · {{ publicationStateLabel(q.publication.state) }}</span>
              <span v-else-if="q.revision" class="text-[10px] text-slate-500 ml-1">r{{ q.revision }} · {{ q.currency }}</span>
              <details v-if="q.origin === 'NETWORK'" class="text-xs mt-1"><summary class="cursor-pointer">Réponse publiée et conditions</summary><div class="max-w-sm whitespace-normal space-y-1"><p>{{ q.publication.response.counterparty_name }} · émetteur {{ q.publication.response.issuer_name || 'Sans objet' }}</p><p>{{ q.publication.response.documentation_reference }}</p><p>{{ q.publication.response.conditions_type === 'NONE' ? 'Sans condition supplémentaire' : 'Réponse conditionnelle' }}</p><p v-for="(condition, i) in q.publication.response.conditions" :key="i">{{ quoteConditionLabel(condition.code) }} : {{ condition.description }}</p><p v-if="q.publication.withdrawal_reason">Retrait : {{ q.publication.withdrawal_reason }}</p></div></details>
            </span>
          </td>
          <td class="py-1.5 pr-2 text-slate-500 whitespace-nowrap">{{ q.contact || '—' }}</td>
          <td class="py-1.5 pr-2">
            <input type="number" class="input py-1 px-2 w-24"
                   :disabled="!!rfq.current.booked_deal || activeExecution?.quote_id === q.id || q.origin === 'NETWORK' || !can(rfq.current, 'prepare')"
                   :value="q.price ?? ''"
                   @change="onQuotePriceChange(q, $event.target.value, $event.target)" />
          </td>
          <td class="py-1.5 pr-2 num whitespace-nowrap" :class="spreadClass(q)">{{ spreadBps(q) }}</td>
          <td class="py-1.5 pr-2">
            <select class="select py-1 px-2 min-w-[125px]" :value="q.status"
                    :disabled="!!rfq.current.booked_deal || activeExecution?.quote_id === q.id || q.origin === 'NETWORK' || !can(rfq.current, 'prepare')" @change="updateQuoteField(q, 'status', $event.target.value, $event.target)">
              <option value="en_attente">En attente</option>
              <option value="recu">Reçu</option>
              <option value="decline">Décliné</option>
              <option value="expire">Expiré</option>
            </select>
          </td>
          <td class="py-1.5 pr-2">
            <select class="select py-1 px-2 min-w-[125px]" :value="q.firmness || 'UNKNOWN'"
                    :disabled="!!rfq.current.booked_deal || activeExecution?.quote_id === q.id || q.origin === 'NETWORK' || !can(rfq.current, 'prepare')"
                    @change="updateQuoteField(q, 'firmness', $event.target.value, $event.target)">
              <option value="UNKNOWN">À qualifier</option>
              <option value="INDICATIVE">Indicative</option>
              <option value="FIRM">Ferme</option>
            </select>
          </td>
          <td class="py-1.5 pr-2">
            <input type="datetime-local" class="input py-1 px-2 min-w-[170px]"
                   :disabled="!!rfq.current.booked_deal || activeExecution?.quote_id === q.id || q.origin === 'NETWORK' || !can(rfq.current, 'prepare')"
                   :value="toDatetimeLocal(q.quoted_at)"
                   @change="onQuoteDateChange(q, $event.target.value, $event.target)" />
          </td>
          <td class="py-1.5 pr-2">
            <input type="datetime-local" class="input py-1 px-2 min-w-[170px]"
                   :disabled="!!rfq.current.booked_deal || activeExecution?.quote_id === q.id || q.origin === 'NETWORK' || !can(rfq.current, 'prepare')"
                   :value="toDatetimeLocal(q.valid_until)"
                   @change="onQuoteValidityChange(q, $event.target.value, $event.target)" />
          </td>
          <td class="py-1.5 pr-2">
            <select v-if="!q.parent_quote_id" class="select py-1 px-2 min-w-[80px]"
                    :disabled="!!rfq.current.booked_deal || activeExecution?.quote_id === q.id || q.origin === 'NETWORK' || q.price == null || !can(rfq.current, 'prepare')"
                    :value="q.last_look ? 'oui' : 'non'"
                    @change="onLastLookToggle(q, $event.target.value === 'oui', $event.target)">
              <option value="non">Non</option>
              <option value="oui">Oui</option>
            </select>
          </td>
          <td class="py-1.5 pr-2 text-right whitespace-nowrap">
            <button :class="['text-xs mr-2', q.id === rfq.current.selected_quote_id ? 'text-amber-400 font-semibold' : 'text-slate-600 hover:text-amber-400']"
                    :disabled="!!rfq.current.booked_deal || !!activeExecution || !q.comparable || !can(rfq.current, 'select')"
                    :title="!q.comparable ? 'Seule une cotation finale, active et non remplacée peut être retenue' : (q.id === rfq.current.selected_quote_id ? 'Réponse retenue — cliquer pour désélectionner' : 'Retenir cette réponse')"
                    @click="onSelectQuote(q)">
              {{ q.id === rfq.current.selected_quote_id ? (rfq.current.selected_quote_revision === q.revision ? '★ Retenue' : '☆ Retenir à nouveau') : '☆ Retenir' }}
            </button>
            <button v-if="q.origin !== 'NETWORK' && !rfq.current.booked_deal && can(rfq.current, 'prepare')" class="text-slate-600 hover:text-red-400" @click="removeQuote(q.id)">✕</button>
          </td>
        </tr>
        </template>
      </tbody>
    </table>
    </div>
    </SensitiveValue>

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
        <select v-if="availableQuoteContacts.length" v-model="quoteForm.contact" class="select">
          <option value="">— Choisir un contact —</option>
          <option v-for="contact in availableQuoteContacts" :key="contact.id" :value="contact.name">
            {{ contact.name }}{{ contact.email ? ` · ${contact.email}` : '' }}
          </option>
        </select>
        <input v-else v-model="quoteForm.contact" type="text" class="input"
               placeholder="Nom / email (optionnel)" />
      </div>
      <button class="btn-primary text-xs px-3 py-2" @click="submitAddQuote">Ajouter</button>
      <button class="btn-secondary text-xs px-3 py-2" @click="addingQuote = false">Annuler</button>
    </div>
  </div>
</template>

<script setup>
// Extracted from RfqView.vue (P1-10, U3). The state stays in the
// view; this panel reads it through useRfqContext().
import AlertMessage from '../../components/ui/AlertMessage.vue'
import DealReferenceLink from '../../components/DealReferenceLink.vue'
import RfqExecutionPanel from '../../components/RfqExecutionPanel.vue'
import SensitiveValue from '../../components/SensitiveValue.vue'
import { SELECTION_REASONS, can, selectionReasonLabel, sensHint, toDatetimeLocal } from './rfqLabels.js'
import { publicationStateLabel, quoteConditionLabel } from '../../utils/rfqQuoteStates.js'
import { useRfqContext } from './context.js'

const {
  activeExecution, addingQuote, availableQuoteContacts, bestQuote, bookFromRfq, computeModelPrice,
  computing, confirmedExecution, convertToTrade, fmtPrice, legalCounterparties, legalDraft,
  legalReasons, modelPriceRecorded, mutationError, onLastLookToggle, onQuoteDateChange,
  onQuotePriceChange, onQuoteValidityChange, onSelectQuote, openAddQuote, openBookedDeal,
  providerLabel, qualifyQuote, quoteForm, rejectedMutation, removeQuote, rfq, saveSelectionReason,
  selectedIsBest, selectedQuote, selectionReasonChanged, selectionReasonCode, selectionReasonError,
  selectionReasonNote, spreadBps, spreadClass, submitAddQuote, updateQuoteField,
} = useRfqContext()
</script>
