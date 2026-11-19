<template>
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
          ? "Sonder un niveau de prix pour affiner une idée, avec les Economics du produit."
          : "Préparer un trade avec ses termes, son panier et son calendrier contractuel complets." }}
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
        <select v-model="form.payoff_family" class="select">
          <option value="">— Choisir une famille —</option>
          <option v-if="legacyPayoffFamily" :value="legacyPayoffFamily">
            Ancien libellé : {{ legacyPayoffFamily }} — à classer
          </option>
          <option v-for="family in PAYOFF_FAMILIES" :key="family.code"
                  :value="family.label">{{ family.label }}</option>
        </select>
        <p v-if="form.payoff_family === 'Autre'" class="text-[10px] text-slate-500">
          Décrivez le payoff ci-dessous.
        </p>
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
              @click="onSourceToggle('template')">Modèle générique</button>
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
        Modèle générique ; termes à compléter ci-dessous ou à charger depuis un exemple.
      </p>
      <PayScriptPresetPicker :currency="form.currency" :start-date="form.strike_date"
        :underlying-count="createBasket.length" :disabled="!!sourceProduct"
        :on-apply="applyCreatePreset" />
    </div>
    <div v-else class="flex flex-col gap-1">
      <label class="label">Script de la bibliothèque</label>
      <select :value="librarySelectValue" class="select" @change="onLibrarySelect($event.target.value)">
        <option value="">Choisir un script…</option>
        <optgroup label="Scripts sauvegardés">
          <option v-for="s in scripts" :key="'s'+s.id" :value="'script:'+s.id">{{ s.name }}</option>
        </optgroup>
        <optgroup v-if="scriptedDeals.length" label="Deals bookés">
          <option v-for="d in scriptedDeals" :key="'d'+d.id" :value="'deal:'+d.id">
            {{ d.reference }} — {{ d.product_type || d.contrepartie }}
          </option>
        </optgroup>
      </select>
      <p v-if="form.kind === 'to_trade'" class="text-[10px] text-slate-600 mt-0.5">
        Une RFQ to trade nécessite un calendrier contractuel complet.
      </p>
    </div>

  </div>
</template>

<script setup>
// Extracted from RfqView.vue (P1-10, U3). The state stays in the
// view; this panel reads it through useRfqContext().
import PayScriptPresetPicker from '../../components/PayScriptPresetPicker.vue'
import { PAYOFF_FAMILIES } from '../../utils/payoffFamilies.js'
import { sensHint } from './rfqLabels.js'
import { useRfqContext } from './context.js'

const {
  applyCreatePreset, commercialLinkEnabled, createBasket, directClients, directContacts,
  directMandates, directOpportunities, form, groupedTemplates, legacyPayoffFamily,
  librarySelectValue, onDirectClientChange, onDirectOpportunityChange, onKindToggle,
  onLibrarySelect, onSourceToggle, onTemplateChange, opportuniteContexte, scriptedDeals, scripts,
  sourceProduct, toggleDirectCommercial,
} = useRfqContext()
</script>
