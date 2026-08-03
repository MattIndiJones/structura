<template>
  <BaseModal :model-value="modelValue" :title="title" max-width="720px"
    @update:model-value="$emit('update:modelValue', $event)">
    <div v-if="deal && event" class="flex flex-col gap-4 text-xs">
      <div class="rounded-lg border border-amber-800/50 bg-amber-950/25 px-3 py-2.5">
        <div class="font-semibold text-amber-300">{{ exceptionExplanation }}</div>
        <div class="mt-1 text-amber-200/70">
          La décision sera signée par l’utilisateur connecté, historisée et suivie d’un rejeu automatique du lifecycle.
        </div>
      </div>

      <div class="overflow-x-auto table-shell" tabindex="0" role="region">
        <table class="w-full border-collapse text-xs">
          <thead>
            <tr class="border-b border-slate-700 text-left text-slate-500">
              <th class="pb-2 pr-3 font-medium">Sous-jacent</th>
              <th class="pb-2 pr-3 font-medium">Valeur courante</th>
              <th class="pb-2 pr-3 font-medium">Dernière valeur Yahoo</th>
              <th class="pb-2 font-medium">Écart</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="underlying in deal.underlyings" :key="underlying.name"
              class="border-b border-slate-800/60">
              <td class="py-2 pr-3 font-mono text-slate-300">
                {{ underlying.ticker || underlying.name }}
              </td>
              <td class="py-2 pr-3 font-mono text-slate-200">
                {{ formatSpot(event.spots?.[underlying.name]) }}
              </td>
              <td class="py-2 pr-3 font-mono text-blue-300">
                {{ formatSpot(event.indicative_spots?.[underlying.name]) }}
              </td>
              <td class="py-2 font-mono" :class="differenceClass(underlying.name)">
                {{ differenceLabel(underlying.name) }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <fieldset class="flex flex-col gap-2">
        <legend class="label mb-1">Décision utilisateur</legend>
        <label class="rounded-lg border p-3 cursor-pointer flex gap-3"
          :class="form.action === 'USE_YAHOO' ? selectedClass : idleClass">
          <input v-model="form.action" type="radio" value="USE_YAHOO" class="mt-0.5" />
          <span>
            <span class="block font-semibold text-slate-200">Reprendre Yahoo</span>
            <span class="block mt-0.5 text-[10px] text-slate-500">
              Recharge la clôture Yahoo, archive la preuve et l’officialise après ta confirmation.
            </span>
          </span>
        </label>
        <label class="rounded-lg border p-3 cursor-pointer flex gap-3"
          :class="form.action === 'CONFIRM_CURRENT' ? selectedClass : idleClass">
          <input v-model="form.action" type="radio" value="CONFIRM_CURRENT" class="mt-0.5" />
          <span>
            <span class="block font-semibold text-slate-200">Confirmer la valeur courante</span>
            <span class="block mt-0.5 text-[10px] text-slate-500">
              Conserve les valeurs affichées et clôt la version humaine déjà ouverte.
            </span>
          </span>
        </label>
        <label class="rounded-lg border p-3 cursor-pointer flex gap-3"
          :class="form.action === 'REPLACE_MANUAL' ? selectedClass : idleClass">
          <input v-model="form.action" type="radio" value="REPLACE_MANUAL" class="mt-0.5" />
          <span>
            <span class="block font-semibold text-slate-200">Corriger manuellement</span>
            <span class="block mt-0.5 text-[10px] text-slate-500">
              Crée une nouvelle version officielle ; la source et le motif sont obligatoires.
            </span>
          </span>
        </label>
      </fieldset>

      <div v-if="form.action === 'REPLACE_MANUAL'"
        class="grid grid-cols-1 sm:grid-cols-2 gap-3 rounded-lg border border-slate-700 bg-slate-900/40 p-3">
        <div v-for="underlying in deal.underlyings" :key="underlying.name" class="flex flex-col gap-1">
          <label class="label">Fixing {{ underlying.ticker || underlying.name }}</label>
          <input v-model.number="form.spots[underlying.name]" type="number" step="any"
            min="0" class="input font-mono" placeholder="Valeur strictement positive" />
        </div>
        <div class="flex flex-col gap-1 sm:col-span-2">
          <label class="label">Source / référence contrôlée</label>
          <input v-model="form.source_reference" class="input"
            placeholder="Ex. avis agent de calcul, message émetteur, Bloomberg…" />
        </div>
      </div>

      <div class="flex flex-col gap-1">
        <label class="label">Motif de la décision</label>
        <textarea v-model="form.reason" rows="3" class="input resize-y"
          placeholder="Décris le contrôle effectué et pourquoi cette valeur doit devenir officielle (10 caractères minimum)."></textarea>
        <div class="text-[10px] text-slate-600">
          L’ancienne version reste dans l’historique ; aucun fixing officiel n’est écrasé.
        </div>
      </div>

      <div v-if="error" class="rounded-lg border border-red-800/60 bg-red-950/30 px-3 py-2 text-red-300 whitespace-pre-line">
        {{ error }}
      </div>
    </div>

    <template #footer>
      <button class="btn-secondary" :disabled="submitting"
        @click="$emit('update:modelValue', false)">Annuler</button>
      <button class="btn-primary" :disabled="submitting || !canSubmit" @click="submit">
        {{ submitting ? 'Traitement…' : 'Officialiser et rejouer le lifecycle' }}
      </button>
    </template>
  </BaseModal>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { useDealsStore } from '../stores/deals.js'
import BaseModal from './ui/BaseModal.vue'

const props = defineProps({
  modelValue: { type: Boolean, required: true },
  deal: { type: Object, default: null },
  event: { type: Object, default: null },
})
const emit = defineEmits(['update:modelValue', 'resolved'])
const dealsStore = useDealsStore()
const submitting = ref(false)
const error = ref('')
const selectedClass = 'border-blue-700/70 bg-blue-950/30'
const idleClass = 'border-slate-700 bg-slate-900/20 hover:border-slate-600'
const form = reactive({
  action: 'USE_YAHOO', spots: {}, source_reference: '', reason: '',
})

const title = computed(() => props.event
  ? `Traiter l’exception — ${props.event.label}`
  : 'Traiter une exception de fixing')

const currentVersion = computed(() => props.event?.fixing_versions?.find(
  version => version.id === props.event?.current_fixing_version_id) ?? null)

const exceptionExplanation = computed(() => {
  const status = props.event?.fixing_status
  if (status === 'PARTIAL') return 'La version courante est incomplète : au moins un fixing doit être renseigné.'
  if (status === 'CONTESTED') return 'Yahoo et la valeur officielle existante divergent : une décision explicite est requise.'
  if (currentVersion.value?.capture_actor_type === 'USER' || ['RECEIVED', 'MANUAL_REVIEW_REQUIRED'].includes(status)) {
    return `Une version humaine${currentVersion.value ? ` v${currentVersion.value.version}` : ''} est déjà ouverte ; l’automatisation ne peut pas la remplacer.`
  }
  return 'Les contrôles automatiques n’autorisent pas l’application de cette constatation.'
})

const canSubmit = computed(() => {
  if (form.reason.trim().length < 10) return false
  if (form.action !== 'REPLACE_MANUAL') return true
  if (form.source_reference.trim().length < 3) return false
  return (props.deal?.underlyings || []).every(underlying => {
    const value = Number(form.spots[underlying.name])
    return Number.isFinite(value) && value > 0
  })
})

function reset() {
  error.value = ''
  form.action = Object.keys(props.event?.indicative_spots || {}).length
    ? 'USE_YAHOO' : 'CONFIRM_CURRENT'
  form.spots = Object.fromEntries((props.deal?.underlyings || []).map(
    underlying => [underlying.name, props.event?.spots?.[underlying.name] ?? '']))
  form.source_reference = ''
  form.reason = ''
}

watch(() => [props.modelValue, props.event?.id], ([open]) => {
  if (open) reset()
})

function formatSpot(value) {
  if (value == null || value === '') return '—'
  return Number(value).toLocaleString('fr-FR', { maximumFractionDigits: 8 })
}

function difference(name) {
  const current = Number(props.event?.spots?.[name])
  const yahoo = Number(props.event?.indicative_spots?.[name])
  if (!Number.isFinite(current) || current <= 0 || !Number.isFinite(yahoo)) return null
  return yahoo / current - 1
}

function differenceLabel(name) {
  const value = difference(name)
  if (value == null) return '—'
  return `${value >= 0 ? '+' : ''}${(value * 100).toFixed(4)}%`
}

function differenceClass(name) {
  const value = difference(name)
  if (value == null) return 'text-slate-600'
  return Math.abs(value) < 1e-10 ? 'text-emerald-400' : 'text-amber-400'
}

async function submit() {
  if (!canSubmit.value || !props.deal || !props.event) return
  submitting.value = true
  error.value = ''
  try {
    const result = await dealsStore.resolveAutoFixingException(
      props.deal.id, props.event.id, {
        action: form.action,
        expected_version_id: props.event.current_fixing_version_id,
        spots: form.action === 'REPLACE_MANUAL' ? form.spots : null,
        source_reference: form.source_reference.trim(),
        reason: form.reason.trim(),
      })
    emit('resolved', result)
  } catch (err) {
    error.value = err.message
  } finally {
    submitting.value = false
  }
}
</script>
