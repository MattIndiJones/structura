<template>
  <div class="mt-3 grid sm:grid-cols-2 gap-3 text-xs">
    <div v-for="purpose in purposes" :key="purpose.key">
      <label class="label">{{ purpose.label }}
        <select multiple class="select w-full h-24" :value="values[`${purpose.key}_calendars`] || []"
                @change="selectCalendars(purpose.key, $event)">
          <option v-for="code in catalog[purpose.key]" :key="code" :value="code">{{ code }}</option>
        </select>
      </label>
      <p v-if="!values[`${purpose.key}_calendars`]" class="text-amber-400 mt-1">
        Hérité : calendrier bancaire {{ currency || 'non renseigné' }}. Sélectionnez les calendriers contractuels pour expliciter ce choix.
      </p>
      <label v-else class="label mt-1">Règle de combinaison du produit
        <select class="select w-full" v-model="values[`${purpose.key}_join`]">
          <option value="">Choisir explicitement…</option>
          <option value="all_open">Toutes les places / centres ouverts</option>
          <option value="any_open">Au moins une place / un centre ouvert</option>
        </select>
      </label>
    </div>
    <p v-if="error" role="alert" class="text-amber-400">{{ error }}</p>
    <p class="text-slate-500 sm:col-span-2">Les fermetures restent propres à chaque place. « Au moins une ouverte » ne fournit aucun fixing pour une place fermée.</p>
  </div>
</template>
<script setup>
import { onMounted, ref } from 'vue'
import { apiFetch } from '../utils/api.js'
const props = defineProps({ values: { type: Object, required: true }, currency: String })
const purposes = [
  { key: 'observation', label: 'Places / calendriers d’observation' },
  { key: 'settlement', label: 'Centres de règlement' },
]
const catalog = ref({ observation: [], settlement: [] })
const error = ref('')
onMounted(async () => {
  try {
    const response = await apiFetch('/api/calendar/catalog')
    if (!response.ok) throw new Error()
    const data = await response.json()
    catalog.value = { observation: data.observation_codes, settlement: data.settlement_codes }
  } catch { error.value = 'Catalogue des calendriers indisponible.' }
})
function selectCalendars(purpose, event) {
  props.values[`${purpose}_calendars`] = [...event.target.selectedOptions].map(option => option.value)
  // No product combination rule is inferred from the number of venues.
  props.values[`${purpose}_join`] ||= ''
}
</script>
