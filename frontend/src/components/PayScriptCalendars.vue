<template>
  <div class="flex flex-col gap-3">
    <div v-for="c in declarations" :key="c.name" class="rounded-lg border border-slate-700 p-3">
      <div class="text-xs font-semibold mb-2">{{ c.name }}
        <span class="text-slate-500">{{ c.role === 'initial_fixing' ? '· fixing initial du panier' : '' }}</span>
      </div>
      <template v-if="c.kind === 'single'">
        <input type="date" class="input max-w-xs" :value="singleDate(c)" @input="setSingleDate(c, $event.target.value)" />
        <button v-if="c.role !== 'initial_fixing' && typeof values[c.name] === 'string'" class="text-xs text-blue-400 mt-2" @click="values[c.name] = { date: values[c.name], convention: 'none', settlement_lag: 0 }">Convention et règlement…</button>
        <div v-if="c.role !== 'initial_fixing' && typeof values[c.name] === 'object'" class="flex gap-3 mt-2 text-xs">
          <label class="label">Convention<select class="select" v-model="values[c.name].convention"><option value="none">Aucun ajustement</option><option value="following">Suivant</option><option value="modified_following">Suivant modifié</option><option value="preceding">Précédent</option><option value="modified_preceding">Précédent modifié</option></select></label>
          <label class="label">Règlement (jours ouvrés)<input type="number" min="0" max="30" class="input w-20" v-model.number="values[c.name].settlement_lag" /></label>
        </div>
      </template>
      <div v-else class="flex flex-wrap items-end gap-3 text-xs">
        <label class="label">{{ explicit ? 'Première observation (incluse)' : 'Début de période (exclu)' }}
          <input type="date" class="input" v-model="values[c.name][explicit ? 'first_observation_date' : 'start_date']" />
        </label>
        <label class="label">Dernière observation
          <input type="date" class="input" v-model="values[c.name].end_date" />
        </label>
        <label class="label">Fréquence
          <div class="flex gap-1">
            <input type="number" min="1" class="input w-16" v-model.number="values[c.name].frequency.value" />
            <select class="select" v-model="values[c.name].frequency.unit"><option>D</option><option>W</option><option>M</option><option>Y</option></select>
          </div>
        </label>
        <label class="label">Convention
          <select class="select" v-model="values[c.name].convention"><option value="none">Aucun ajustement</option><option value="following">Suivant</option><option value="modified_following">Suivant modifié</option><option value="preceding">Précédent</option><option value="modified_preceding">Précédent modifié</option></select>
        </label>
        <label class="label">Règlement (jours ouvrés)
          <input type="number" min="0" max="30" class="input w-20" v-model.number="values[c.name].settlement_lag" />
        </label>
        <label v-if="c.kind === 'nested_schedule'" class="label">Sous-fréquence
          <div class="flex gap-1"><input type="number" min="1" class="input w-16" v-model.number="values[c.name].sub_frequency.value" /><select class="select" v-model="values[c.name].sub_frequency.unit"><option>D</option><option>W</option><option>M</option><option>Y</option></select></div>
        </label>
      </div>
      <details v-if="c.kind !== 'single'" :open="advancedCalendar(values[c.name])" class="mt-3 text-xs">
        <summary class="cursor-pointer text-slate-500">Réglages avancés du calendrier</summary>
        <div class="flex flex-wrap gap-3 mt-2">
          <label class="label">Roll (première observation si vide)<input type="date" class="input" v-model="values[c.name].roll_date" /></label>
          <label class="label">Stub<select class="select" v-model="values[c.name].stub"><option value="short_last">Court en fin</option><option value="long_last">Long en fin</option><option value="short_first">Court au début</option><option value="long_first">Long au début</option></select></label>
        </div>
      </details>
      <div v-if="c.reduction" class="flex flex-wrap items-end gap-3 mt-3 text-xs">
        <span>{{ c.reduction }} par sous-jacent sur la fenêtre</span>
        <label v-if="c.window_scope === 'period'" class="label">Début de la première période (StartDate si vide)
          <input type="date" class="input" v-model="values[c.name].period_start_date" />
        </label>
        <ConstatWindowFields :scope="c.window_scope" :valeurs="values[c.name]" :apercu="previews[c.name]" />
      </div>
      <ObservationSchedule v-if="c.kind !== 'single'" class="mt-3" :request="request(c)" :window-frequency="c.window_scope === 'period' ? tenorString(values[c.name].window_frequency) : null" />
    </div>
  </div>
</template>
<script setup>
import { computed, ref, watch } from 'vue'
import { apiFetch } from '../utils/api.js'
import ConstatWindowFields from './ConstatWindowFields.vue'
import ObservationSchedule from './ObservationSchedule.vue'
import { serializeCalendars, fixingDate, tenorString } from '../utils/payscriptEconomics.js'
const props = defineProps({ declarations: Array, values: Object, currency: String, initialDate: String, explicitFixing: Boolean })
function advancedCalendar(value) {
  return (value?.stub && value.stub !== 'short_last') || !!(value?.roll_date && value.roll_date !== value.first_observation_date && value.roll_date !== value.period_start_date)
}
const explicit = computed(() => props.explicitFixing || props.declarations.some(c => c.role === 'initial_fixing'))
function singleDate(c) { const value = props.values[c.name]; return typeof value === 'string' ? value : value?.date }
function setSingleDate(c, date) { if (typeof props.values[c.name] === 'object') props.values[c.name].date = date; else props.values[c.name] = date }
const previews = ref({})
watch(() => [props.declarations, props.values, props.currency], async (_, __, onCleanup) => {
  let cancelled = false
  onCleanup(() => { cancelled = true })
  const result = {}
  for (const c of props.declarations) {
    const v = props.values[c.name]
    if (!c.reduction || c.window_scope === 'period' || !v?.window_length?.value || !v?.window_frequency?.value) continue
    const date = c.kind === 'single' ? v.date : v.end_date
    if (!date) continue
    try {
      const response = await apiFetch('/api/schedule/window', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ date, window_length: tenorString(v.window_length), window_frequency: tenorString(v.window_frequency), forward: c.role === 'initial_fixing', currency: props.currency, convention: v.convention || 'none' }),
      })
      const data = await response.json()
      result[c.name] = response.ok ? data : { erreur: typeof data.detail === 'string' ? data.detail : 'Fenêtre incomplète.' }
    } catch { result[c.name] = { erreur: 'Aperçu indisponible.' } }
  }
  if (!cancelled) previews.value = result
}, { deep: true, immediate: true })
function request(c) {
  const value = serializeCalendars(props.declarations, props.values, props.initialDate || fixingDate(props.declarations, props.values))[c.name]
  if (explicit.value) {
    delete value.start_date
    value.roll_date ||= value.first_observation_date
    value.period_start_date ||= props.initialDate
  }
  return { ...value, currency: props.currency }
}
</script>
