<template>
  <details class="text-xs">
    <summary class="cursor-pointer text-slate-400">Mes configurations enregistrées…</summary>
    <div class="flex gap-2 mt-2">
      <button class="btn-secondary text-xs" @click="load">Appliquer une configuration…</button>
      <button class="btn-secondary text-xs" @click="saving = true; error = ''">Enregistrer cette configuration…</button>
    </div>
    <BaseModal v-model="open" title="Appliquer une configuration" max-width="560px">
      <AlertMessage v-if="error" kind="error">{{ error }}</AlertMessage>
      <select class="select" v-model="selectedId"><option value="">Choisir…</option><option v-for="row in rows" :value="row.id" :key="row.id">{{ row.name }}</option></select>
      <p v-if="!rows.length" class="text-slate-500 mt-2">Aucune configuration enregistrée.</p>
      <div v-if="selected" class="mt-3 space-y-2 text-xs">
        <p>Remplacera le script, les paramètres et les dates affichés. {{ metadata.include_basket ? 'Le panier enregistré sera également chargé.' : 'Le panier actuel sera conservé.' }}</p>
        <p>Modèle : {{ productTypeLabel(metadata.model_key) || 'personnalisé' }}{{ metadata.model_version ? ` · version ${metadata.model_version}` : '' }}</p>
        <dl class="grid grid-cols-2 gap-2 max-h-64 overflow-auto">
          <template v-for="(value, key) in readJson(selected.params_json)" :key="key"><dt class="text-slate-400">{{ key }}</dt><dd>{{ showParameter(key, value) }}</dd></template>
          <template v-for="(value, key) in readJson(selected.constats_json)" :key="key"><dt class="text-slate-400">{{ key }}</dt><dd>{{ showCalendar(value) }}</dd></template>
        </dl>
      </div>
      <template #footer><button class="btn-secondary" @click="open = false">Annuler</button><button class="btn-primary" :disabled="!selected" @click="apply">Appliquer</button></template>
    </BaseModal>
    <BaseModal v-model="saving" title="Enregistrer une configuration" max-width="420px">
      <AlertMessage v-if="error" kind="error">{{ error }}</AlertMessage>
      <label class="label">Nom<input class="input" v-model="name" /></label>
      <label class="text-xs"><input type="checkbox" v-model="includeBasket" /> Inclure le panier et ses hypothèses</label>
      <template #footer><button class="btn-secondary" @click="saving = false">Annuler</button><button class="btn-primary" :disabled="!name.trim() || busy" @click="save">Enregistrer</button></template>
    </BaseModal>
  </details>
</template>
<script setup>
import { ref, computed } from 'vue'
import { productTypeLabel } from '../data/payscriptTemplates.js'
import { tenorString } from '../utils/payscriptEconomics.js'
import { apiFetch } from '../utils/api.js'
import { usePricingStore } from '../stores/pricing.js'
import BaseModal from './ui/BaseModal.vue'
import AlertMessage from './ui/AlertMessage.vue'
const store = usePricingStore()
const open = ref(false), saving = ref(false), busy = ref(false), error = ref('')
const rows = ref([]), selectedId = ref(''), name = ref(''), includeBasket = ref(false)
const selected = computed(() => rows.value.find(r => r.id === selectedId.value))
function readJson(value) { try { return JSON.parse(value || '{}') } catch { return {} } }
const metadata = computed(() => readJson(selected.value?.global_params_json).configuration || {})
function showParameter(key, value) {
  const format = v => v == null || v === '' ? 'À renseigner' : `${v}${metadata.value.parameter_units?.[key] || ''}`
  return Array.isArray(value) ? value.map(format).join(' · ') : format(value)
}
function showCalendar(value) {
  if (typeof value === 'string') return value || 'À renseigner'
  if (!value) return 'À renseigner'
  const dates = value.date || `${value.first_observation_date || value.start_date || '…'} → ${value.end_date || '…'}`
  const frequency = tenorString(value.frequency)
  return dates + (frequency ? ` · ${frequency}` : '')
}
async function load() {
  open.value = true; error.value = ''
  try {
    const response = await apiFetch('/api/db/scripts')
    if (!response.ok) throw new Error('Lecture des configurations impossible.')
    const data = await response.json()
    rows.value = (Array.isArray(data) ? data : data.scripts || []).filter(r => String(r.tags).includes('configuration:payscript-v2'))
  } catch (e) { error.value = e.message }
}
async function apply() {
  const basket = JSON.parse(JSON.stringify(store.underlyings)), corr = JSON.parse(JSON.stringify(store.corrMatrix))
  const keep = !metadata.value.include_basket
  try {
    await store.loadFromDb(selected.value)
    if (keep) { store.underlyings = basket; store.corrMatrix = corr }
    open.value = false
  } catch (e) { error.value = e.message }
}
async function save() {
  busy.value = true; error.value = ''
  try { await store.saveConfiguration(name.value.trim(), includeBasket.value); saving.value = false }
  catch (e) { error.value = e.message }
  finally { busy.value = false }
}
</script>
