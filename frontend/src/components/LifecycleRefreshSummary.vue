<template>
  <div role="status" class="text-xs" :class="status === 'SUCCESS' ? 'text-slate-400' : 'text-amber-400'">
    <p>{{ status === 'SUCCESS' ? '✓ Terminé' : status === 'PARTIAL' ? '⚠ Partiel' : '⚠ Échec' }}
      — couverture {{ coverage.succeeded }}/{{ coverage.total }} dossier(s) sans erreur,
      {{ summary.refreshed || 0 }} rafraîchi(s), {{ summary.settled || 0 }} échéance(s) atteinte(s),
      {{ summary.alerts_created || 0 }} alerte(s), {{ summary.proposed?.length || 0 }} proposition(s),
      {{ summary.resolved?.length || 0 }} résolution(s).</p>
    <details v-if="summary.errors?.length" class="mt-1">
      <summary class="cursor-pointer">{{ coverage.failed }} dossier(s) en erreur — consulter le détail avant de relancer</summary>
      <ul class="mt-1 pl-4 list-disc">
        <li v-for="(error, index) in summary.errors" :key="index">{{ error }}</li>
      </ul>
    </details>
  </div>
</template>

<script setup>
import { computed } from 'vue'
const props = defineProps({ summary: { type: Object, required: true } })
const coverage = computed(() => props.summary.coverage || {
  total: props.summary.deals || 0,
  succeeded: Math.max(0, (props.summary.deals || 0) - (props.summary.errors?.length || 0)),
  failed: props.summary.errors?.length || 0,
})
const status = computed(() => props.summary.errors?.length
  ? (coverage.value.succeeded ? 'PARTIAL' : 'FAILED') : props.summary.status || 'SUCCESS')
</script>
