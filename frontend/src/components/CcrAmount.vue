<template>
  <SensitiveValue><span :title="exact" :aria-label="exact">{{ formatMoneyRound(value, currency) }}</span></SensitiveValue>
</template>

<script setup>
import { computed } from 'vue'
import SensitiveValue from './SensitiveValue.vue'
import { formatMoney, formatMoneyRound } from '../utils/format.js'

const props = defineProps({
  value: { type: [Number, String], default: null },
  currency: { type: String, default: 'EUR' },
})
const exact = computed(() => props.value == null || props.value === '' || !Number.isFinite(Number(props.value))
  ? undefined : `Montant exact : ${formatMoney(props.value, props.currency)}`)
</script>
