<template>
  <details class="text-xs">
    <summary class="cursor-pointer text-slate-400">Mes configurations enregistrées…</summary>
    <div class="flex gap-2 mt-2">
      <button class="btn-secondary text-xs" @click="load">Appliquer une configuration…</button>
      <button class="btn-secondary text-xs" @click="saving = true; error = ''">Enregistrer cette configuration…</button>
    </div>
    <BaseModal v-model="open" title="Appliquer une configuration" max-width="560px">
      <AlertMessage v-if="error" kind="error">{{ error }}</AlertMessage>
      <select class="select" v-model="selectedId" :disabled="busy"><option value="">Choisir…</option><option v-for="row in rows" :value="row.id" :key="row.id">{{ row.name }}</option></select>
      <p v-if="!rows.length" class="text-slate-500 mt-2">Aucune configuration enregistrée.</p>
      <div v-if="selected" class="mt-3 space-y-2 text-xs">
        <label class="label">Portée de l’application<select class="select" v-model="scope" :disabled="busy">
          <option value="terms">Termes seulement — conserver les hypothèses actuelles</option>
          <option value="all">Termes et hypothèses enregistrées</option>
        </select></label>
        <p>Remplacera le script, les paramètres, les dates et la devise de règlement.
          {{ scope === 'all' && metadata.include_basket ? 'Le panier enregistré et ses hypothèses seront également chargés.' : 'Le panier actuel sera conservé.' }}</p>
        <p>{{ scope === 'all' ? 'Remplacera aussi les taux, courbes, funding, modèle et réglages numériques enregistrés ci-dessous.' : 'Taux, courbes, funding, modèle et réglages numériques actuels seront conservés.' }}</p>
        <p>Modèle : {{ productTypeLabel(metadata.model_key) || 'personnalisé' }}{{ metadata.model_version ? ` · version ${metadata.model_version}` : '' }}</p>
        <dl class="grid grid-cols-2 gap-2 max-h-64 overflow-auto">
          <template v-for="(value, key) in readJson(selected.params_json)" :key="key"><dt class="text-slate-400">{{ key }}</dt><dd>{{ showParameter(key, value) }}</dd></template>
          <template v-for="(value, key) in readJson(selected.constats_json)" :key="key"><dt class="text-slate-400">{{ key }}</dt><dd>{{ showCalendar(value) }}</dd></template>
        </dl>
        <details><summary>Devise, dates et hypothèses enregistrées</summary>
          <dl class="grid grid-cols-2 gap-2 max-h-64 overflow-auto mt-2">
            <template v-for="row in assumptionPreview" :key="row.key"><dt>{{ row.label }}</dt><dd class="break-words">{{ row.value }}</dd></template>
          </dl>
        </details>
      </div>
      <template #footer><button class="btn-secondary" @click="open = false">Annuler</button><button class="btn-primary" :disabled="!selected || busy || store.contractTermsLocked" @click="apply">Appliquer</button></template>
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
const scope = ref('terms')
const selected = computed(() => rows.value.find(r => r.id === selectedId.value))
function readJson(value) { try { return JSON.parse(value || '{}') } catch { return {} } }
const metadata = computed(() => readJson(selected.value?.global_params_json).configuration || {})
const assumptionPreview = computed(() => {
  const saved = readJson(selected.value?.global_params_json)
  const labels = { deal_ccy:'Devise de règlement', r:'Taux plat (%)', T:'Maturité (années)',
    yield_curve_enabled:'Courbe de taux active', yield_curve_pillars:'Piliers de taux (%, années)', funding:'Funding (%, années)',
    model:'Modèle actions', rateModel:'Modèle de taux', sigma_r:'Volatilité de taux (%)', a_r:'Retour à la moyenne (1/an)',
    N:'Nombre de chemins', seed:'Graine', antithetic:'Antithétiques', barrierMonitoring:'Suivi des barrières',
    trade_date:'Date de trade', strike_date:'Strike', value_date:'Date de valeur', maturity_date:'Maturité',
    payment_date:'Paiement', valuation_date:'Date de valorisation', underlyings:'Panier et hypothèses (%)', corr_matrix:'Corrélations' }
  return Object.entries(saved).filter(([key]) => key !== 'configuration').map(([key,value]) => ({
    key, label:labels[key] || key, value:typeof value === 'object' ? JSON.stringify(value) : String(value ?? 'À renseigner'),
  }))
})
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
  busy.value = true; error.value = ''
  try {
    await store.loadFromDb(selected.value, { scope: scope.value })
    open.value = false
  } catch (e) { error.value = e.message }
  finally { busy.value = false }
}
async function save() {
  busy.value = true; error.value = ''
  try { await store.saveConfiguration(name.value.trim(), includeBasket.value); saving.value = false }
  catch (e) { error.value = e.message }
  finally { busy.value = false }
}
</script>
