<template>
  <div v-if="policy" class="card text-xs space-y-3">
    <div class="flex flex-wrap items-center justify-between gap-2">
      <span>Historique utilisé : {{ formatDate(policy.effective_start) }} → {{ formatDate(policy.effective_end) }}
        · {{ policy.mode === 'strict' ? 'Strict' : `Following, ${policy.max_delay_days} jours calendaires maximum` }}</span>
      <button class="btn-secondary btn-sm" @click="exportResult">Exporter le résultat et ses ajustements</button>
    </div>
    <p v-if="policy.requested_start && policy.requested_start !== policy.effective_start" role="status">
      Début demandé : {{ formatDate(policy.requested_start) }} ; première date commune utilisée : {{ formatDate(policy.effective_start) }}.
    </p>
    <p v-if="policy.disclaimer" role="alert" class="text-amber-600">{{ policy.disclaimer }}</p>
    <p v-if="policy.comparison_basis" class="text-slate-500">Période et clôtures communes à tous les candidats disposant d’un historique ; ajustements identiques dédupliqués entre les comparaisons.</p>
    <details v-if="rows.length">
      <summary class="cursor-pointer font-semibold">Dates ajustées — {{ rows.length }} ajustement(s),
        {{ policy.adjusted_underlyings?.length || 0 }} sous-jacent(s)</summary>
      <div class="overflow-auto mt-3 max-h-80">
        <table class="w-full text-xs">
          <thead><tr class="border-b"><th class="text-left p-1">Fenêtre</th><th class="text-left p-1">Sous-jacent</th>
            <th class="text-left p-1">Date demandée</th><th class="text-left p-1">Date retenue</th>
            <th class="text-right p-1">Jours</th><th class="text-left p-1">Motif</th></tr></thead>
          <tbody><tr v-for="(row, i) in visibleRows" :key="`${page}-${i}`" class="border-b">
            <td class="p-1">{{ formatDate(row.window_start) }}</td>
            <td class="p-1"><SensitiveValue>{{ row.ticker }}</SensitiveValue></td>
            <td class="p-1">{{ formatDate(row.requested_date) }}</td><td class="p-1">{{ formatDate(row.effective_date) }}</td>
            <td class="p-1 text-right">{{ row.delay_days }}</td>
            <td class="p-1">{{ row.reason === 'COMMON_BASKET_DATE' ? (policy.comparison_basis ? 'Alignement sur la date commune de l’univers' : 'Alignement sur la date commune du panier') : 'Cours absent (fermeture ou lacune non distinguées)' }}</td>
          </tr></tbody>
        </table>
      </div>
      <div v-if="pageCount > 1" class="flex items-center justify-end gap-3 mt-2">
        <button class="btn-secondary btn-sm" :disabled="page === 0" @click="page--">Précédent</button>
        <span>Page {{ page + 1 }} / {{ pageCount }} · 50 lignes par page</span>
        <button class="btn-secondary btn-sm" :disabled="page + 1 >= pageCount" @click="page++">Suivant</button>
      </div>
    </details>
    <p class="text-slate-500">Observation des clôtures disponibles ; les franchissements intrajournaliers et les cours absents entre ces clôtures ne sont pas reconstitués.</p>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import SensitiveValue from './SensitiveValue.vue'
import { formatDate } from '../utils/format.js'

const props = defineProps({ result: { type: Object, required: true } })
const policy = computed(() => props.result.history_policy)
const rows = computed(() => policy.value?.adjustments || [])
const page = ref(0)
const pageCount = computed(() => Math.ceil(rows.value.length / 50))
const visibleRows = computed(() => rows.value.slice(page.value * 50, (page.value + 1) * 50))
watch(() => props.result, () => { page.value = 0 })
function exportResult() {
  const url = URL.createObjectURL(new Blob([JSON.stringify(props.result, null, 2)], { type: 'application/json' }))
  const anchor = document.createElement('a')
  anchor.href = url; anchor.download = 'structura-backtest.json'; anchor.click()
  URL.revokeObjectURL(url)
}
</script>
