<script setup>
import { ref } from 'vue'
import { apiFetch } from '../utils/api.js'
import { formatDateTime, formatNumber } from '../utils/format.js'
const props = defineProps({ transport: Object, canRetry: Boolean })
const emit = defineEmits(['updated'])
const busy = ref(false)
const error = ref('')
const labels = { PENDING: 'En attente', RETRY: 'Reprise automatique', BLOCKED: 'Reprise bloquée', DELIVERED: 'Réception confirmée', CANCELLED: 'Envoi annulé avant réception' }
async function retry() {
  busy.value = true
  error.value = ''
  try {
    const result = await apiFetch(`/api/rfq-transport/messages/${props.transport.message_id}/retry`, { method: 'POST' })
    if (!result.ok) throw new Error((await result.json()).detail || 'Relance refusée')
    emit('updated')
  } catch (failure) { error.value = failure.message }
  finally { busy.value = false }
}
</script>
<template>
  <div v-if="transport" class="text-xs space-y-1">
    <strong>{{ labels[transport.state] || 'État à vérifier' }}</strong>
    <p>{{ formatNumber(transport.attempts, 0) }} tentative(s)<template v-if="transport.next_attempt_at && !['DELIVERED', 'CANCELLED'].includes(transport.state)"> · prochaine reprise {{ formatDateTime(transport.next_attempt_at) }}</template></p>
    <p v-if="transport.last_error" class="text-amber-400">{{ transport.last_error }}</p>
    <p v-if="error" class="text-red-400">{{ error }}</p>
    <button v-if="canRetry && !['DELIVERED', 'CANCELLED'].includes(transport.state)" class="btn-ghost btn-sm" :disabled="busy" @click="retry">Relancer la livraison</button>
    <details v-if="transport.history.length"><summary class="cursor-pointer">Dernières tentatives</summary><div class="max-h-32 overflow-y-auto overscroll-contain"><p v-for="(attempt, index) in transport.history" :key="index">{{ formatDateTime(attempt.at) }} · {{ labels[attempt.outcome] }}<template v-if="attempt.detail"> · {{ attempt.detail }}</template></p></div></details>
  </div>
</template>
