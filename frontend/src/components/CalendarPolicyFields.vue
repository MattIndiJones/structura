<template>
  <div class="mt-3 grid sm:grid-cols-2 gap-x-3 gap-y-2 text-xs">
    <div v-for="purpose in purposes" :key="purpose.key" class="min-w-0">
      <details class="rounded-lg border border-slate-300 px-2 py-1.5">
        <summary class="cursor-pointer" :aria-label="purpose.label">
          <span class="font-medium">{{ purpose.label }} :</span>
          {{ selected(purpose.key).map(code => CALENDAR_LABELS[code] || code).join(', ') || 'À renseigner' }}
          <span class="text-slate-500"> · {{ frozen && !values[`${purpose.key}_calendars`] ? 'Hérité' : defaults.state.value[purpose.key].automatic ? 'Défaut' : 'Personnalisé' }}</span>
        </summary>
        <div class="grid grid-cols-2 gap-1 mt-2 max-h-40 overflow-auto">
          <label v-for="code in catalog[purpose.key]" :key="code" class="flex items-center gap-1.5 py-1">
            <input type="checkbox" :checked="selected(purpose.key).includes(code)" :disabled="frozen"
              :aria-label="`${purpose.label} : ${code}`" @change="toggleCalendar(purpose.key, code, $event.target.checked)" />
            {{ CALENDAR_LABELS[code] || code }}<span v-if="CALENDAR_LABELS[code]" class="text-slate-500">({{ code }})</span>
          </label>
        </div>
        <button type="button" class="underline mt-2" :disabled="frozen" @click="defaults.reset(purpose.key)">Utiliser le défaut proposé</button>
      </details>
      <label v-if="selected(purpose.key).length > 1" class="label mt-1">{{ purpose.key === 'observation' ? 'Combinaison des places' : 'Combinaison des centres' }}
        <select class="select w-full" v-model="values[`${purpose.key}_join`]" :disabled="frozen"
          @change="defaults.state.value[purpose.key].automatic = false">
          <option value="">Choisir explicitement…</option>
          <option value="all_open">{{ purpose.key === 'observation' ? 'Toutes les places ouvertes' : 'Tous les centres ouverts' }}</option>
          <option value="any_open">{{ purpose.key === 'observation' ? 'Au moins une place ouverte' : 'Au moins un centre ouvert' }}</option>
        </select>
      </label>
      <p v-if="!selected(purpose.key).length" class="text-amber-600 mt-1">Sélectionnez au moins un calendrier.</p>
    </div>
    <p v-if="error" role="alert" class="text-amber-600 sm:col-span-2">{{ error }}</p>
    <p v-if="defaults.state.value.observation.automatic && defaults.suggested.value.approximation" class="text-amber-600 sm:col-span-2">
      Observation : approximation bancaire {{ currency || 'indisponible' }} ; place à préciser{{ defaults.suggested.value.unresolved.length ? ` pour ${defaults.suggested.value.unresolved.join(', ')}` : ' après sélection du sous-jacent' }}.
    </p>
    <p v-if="values.observation_join === 'any_open' && selected('observation').length > 1" class="text-slate-500 sm:col-span-2">Une place ouverte ne fournit aucun fixing pour les autres places fermées.</p>
  </div>
</template>
<script setup>
import { onMounted, ref } from 'vue'
import { apiFetch } from '../utils/api.js'
import { CALENDAR_LABELS, useCalendarDefaults } from '../composables/useCalendarDefaults.js'
const props = defineProps({ values: { type: Object, required: true }, currency: String,
  underlyings: { type: Array, default: () => [] }, frozen: Boolean })
const purposes = [
  { key: 'observation', label: 'Places d’observation' },
  { key: 'settlement', label: 'Centres de règlement' },
]
const defaults = useCalendarDefaults(props)
const catalog = ref({ observation: [], settlement: [] })
const error = ref('')
const selected = purpose => props.values[`${purpose}_calendars`] || (props.frozen && props.currency ? [props.currency] : [])
onMounted(async () => {
  try {
    const response = await apiFetch('/api/calendar/catalog')
    if (!response.ok) throw new Error()
    const data = await response.json()
    catalog.value = { observation: data.observation_codes, settlement: data.settlement_codes }
  } catch { error.value = 'Catalogue des calendriers indisponible.' }
})
function selectCalendars(purpose, event) {
  defaults.customize(purpose, [...event.target.selectedOptions].map(option => option.value))
}
function toggleCalendar(purpose, code, checked) {
  defaults.customize(purpose, checked ? [...selected(purpose), code] : selected(purpose).filter(value => value !== code))
}
</script>
