<template>
  <div class="flex items-start justify-between gap-2 flex-wrap">
    <div>
      <div class="flex items-center gap-2">
        <h2 class="text-lg font-bold text-slate-100">{{ rfq.current.name || rfq.current.reference }}</h2>
        <span :class="['text-[9px] rounded px-1.5 py-0.5 border', sensBadge(rfq.current.sens)]" :title="sensHint(rfq.current.sens)">{{ sensLabel(rfq.current.sens) }}</span>
        <span :class="['text-[9px] rounded px-1.5 py-0.5 border', kindBadge(rfq.current.kind)]">{{ kindLabel(rfq.current.kind) }}</span>
      </div>
      <div class="text-xs text-slate-500 font-mono">{{ rfq.current.reference }} · {{ rfq.current.template_type || 'script personnalisé' }}</div>
      <div v-if="rfq.current.pilot_desk_id" class="text-xs text-slate-500">
        {{ rfq.current.organization_name }} · Desk pilote {{ rfq.current.pilot_desk_name }} · Responsable {{ rfq.current.responsible_user_name }} · Créateur {{ rfq.current.creator_name }}
      </div>
    </div>
    <div class="flex items-center gap-2 flex-wrap">
      <button v-if="rfq.current.access_rights?.includes('organize')" class="btn-secondary btn-sm" @click="openShares">Partager entre desks</button>
      <button v-if="rfq.current.access_rights?.includes('organize')" class="btn-secondary btn-sm" @click="openAssignment">Affecter / transférer</button>
      <button v-if="can(rfq.current, 'solicit')" class="btn-secondary btn-sm" :disabled="!rfq.current.product_id || detailTermsDirty" @click="showExchange = true">Préparer la demande partagée</button>
      <button v-if="rfq.current.kind === 'indicatif'" class="btn-secondary text-xs px-3 py-1.5" title="Créer une RFQ 'to trade' à partir de celle-ci, avec un script précis"
              @click="convertToTrade(rfq.current)">📐 Convertir en RFQ to trade</button>
      <button class="btn-secondary text-xs px-3 py-1.5" title="Créer une nouvelle RFQ à partir de celle-ci"
              @click="duplicateRfq(rfq.current)">⎘ Dupliquer</button>
      <button v-if="can(rfq.current, 'organize')" class="icon-btn-danger" title="Supprimer" aria-label="Supprimer la RFQ" @click="deleteRfq(rfq.current.id)">🗑</button>
    </div>
  </div>
  <AlertMessage v-if="rfq.current.pilot_desk_id && !can(rfq.current, 'prepare')" kind="info">
    Dossier en consultation : les modifications nécessitent une habilitation du desk.
  </AlertMessage>
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
      {{ payoffFamilyForDisplay(rfq.current.payoff_family) }}
    </span>
  </div>
</template>

<script setup>
// Extracted from RfqView.vue (P1-10, U3). The state stays in the
// view; this panel reads it through useRfqContext().
import AlertMessage from '../../components/ui/AlertMessage.vue'
import { can, kindBadge, kindLabel, sensBadge, sensHint, sensLabel } from './rfqLabels.js'
import { payoffFamilyForDisplay } from '../../utils/payoffFamilies.js'
import { useRfqContext } from './context.js'

const {
  convertToTrade, deleteRfq, detailTermsDirty, duplicateRfq, openAssignment, openShares, rfq,
  showExchange,
} = useRfqContext()
</script>
