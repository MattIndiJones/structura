<template>
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
      <div class="label mb-0.5">Panier ({{ underlyingSummaries.length }})</div>
      <div class="text-xs text-slate-200 font-mono">
        <SensitiveValue>{{ underlyingSummaries.join(' / ') || '—' }}</SensitiveValue>
      </div>
    </div>
    <div>
      <div class="label mb-0.5">Nominal</div>
      <div class="text-xs text-slate-200"><SensitiveValue>{{ fmtNominal(rfq.current.params?.notional) }} {{ rfq.current.params?.currency || '' }}</SensitiveValue></div>
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
        <button v-if="rfq.current.status !== 'clos' && can(rfq.current, 'prepare')"
                :disabled="rfq.current.status === 'sans_suite' && !!rfq.current.exchange_round"
                class="text-[10px] underline text-slate-500 hover:text-slate-300"
                :title="rfq.current.status === 'sans_suite'
                        ? (rfq.current.exchange_round ? 'La clôture est définitive ; utilisez Nouveau tour dans Diffusion RFQ' : 'Rendre l\'AO au statut déduit de ses cotations')
                        : 'AO abandonné ou perdu — il ne donnera pas lieu à un trade'"
                @click="toggleSansSuite">
          {{ rfq.current.status === 'sans_suite' ? (rfq.current.exchange_round ? 'Tour clôturé' : 'Rouvrir') : 'Sans suite' }}
        </button>
      </div>
    </div>
    <div>
      <div class="label mb-0.5">Sens (notre côté)</div>
      <select class="select py-1 px-2 text-xs" :value="rfq.current.sens || 'achat'"
              :disabled="!!rfq.current.quotes?.length || !can(rfq.current, 'prepare')"
              :title="rfq.current.quotes?.length ? 'Sens figé dès la première sollicitation' : sensHint(rfq.current.sens)"
              @change="updateSens($event.target.value, $event.target)">
        <option value="achat">↓ Achat (nous achetons)</option>
        <option value="vente">↑ Vente (nous vendons)</option>
      </select>
    </div>
  </div>
</template>

<script setup>
// Extracted from RfqView.vue (P1-10, U3). The state stays in the
// view; this panel reads it through useRfqContext().
import AlertMessage from '../../components/ui/AlertMessage.vue'
import SensitiveValue from '../../components/SensitiveValue.vue'
import { can, fmtTenor, sensHint, statusLabel } from './rfqLabels.js'
import { useRfqContext } from './context.js'

const {
  detailMaturityDate, detailTermsDirty, fmtDateOnly, fmtNominal, refreshDetailParams,
  reglementIncoherent, rfq, saveDetailTerms, savingTerms, termsError, toggleSansSuite,
  underlyingSummaries, updateSens,
} = useRfqContext()
</script>
