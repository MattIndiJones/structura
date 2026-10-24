<template>
  <div v-if="rows.length" class="my-2 space-y-1 text-[10px] text-slate-500">
    <div v-for="item in rows" :key="item.field">
      <span>{{ item.label }} · </span>
      <SensitiveValue>
        <span v-if="item.reference">référence {{ item.referencePct }}% · {{ item.reference.ticker }} · {{ item.reference.asof_effective || 'date inconnue' }} · {{ item.reference.provider }}</span>
        <span v-if="item.missing" class="text-amber-400"> · indisponible : {{ item.missing.error }}</span>
        <span :class="item.overridden ? 'text-amber-400' : ''"> · utilisée {{ item.usedPct }}%{{ item.overridden ? ' (surcharge)' : '' }}</span>
        <span v-if="item.sourceChanged" class="text-amber-400"> · référence d’un autre ticker</span>
      </SensitiveValue>
    </div>
    <p>Références historiques ; hypothèses de projection à valider.</p>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import SensitiveValue from './SensitiveValue.vue'
import { marketProvenanceRows } from '../utils/marketProvenance.js'

const props = defineProps({ row: { type: Object, required: true } })
const rows = computed(() => marketProvenanceRows(props.row))
</script>
