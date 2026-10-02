<template>
  <section class="card ccr-credit-check flex flex-col gap-3">
    <div class="flex flex-wrap items-center justify-between gap-2">
      <h2 class="text-sm font-semibold">{{ bookedDeal ? 'Risque de crédit du produit booké — CCR économique' : 'Contrôle crédit de contrepartie — Counterparty Credit Risk (CCR)' }}</h2>
      <RouterLink to="/risk/ccr" class="btn-ghost btn-sm">Référentiel crédit</RouterLink>
    </div>
    <p v-if="!counterpartyName && !rfqId" class="text-xs text-slate-500">Aucune contrepartie sélectionnée : analyse standalone sans netting ni collatéral ; aucune limite contrôlée.</p>
    <details v-if="!counterpartyName && !rfqId" class="text-xs"><summary>Hypothèses de crédit facultatives pour la CVA standalone</summary>
      <label class="flex gap-2 my-2"><input v-model="hypothetical" type="checkbox" /> Utiliser un profil hypothétique explicite (USER_ASSUMPTION)</label>
      <div v-if="hypothetical" class="ccr-hypotheses"><label><span>Recouvrement (%) <HelpTip :text="ccrHelp.recovery" /></span><input v-model.number="recovery" type="number" min="0" max="99.9" step="0.1" class="input" /></label><label><span>PD cumulées risk-neutral [[année, fraction]] <HelpTip :text="ccrHelp.pd_curve" /></span><textarea v-model="pdCurve" class="input font-mono" rows="2" /></label></div>
    </details>
    <div class="flex gap-2 items-end flex-wrap">
      <label class="flex-1 text-xs"><span>Netting set juridiquement reconnu <HelpTip :text="ccrHelp.netting_set_id" /></span><span v-if="bookedDeal" class="input mt-1">{{ bookedDeal.ccr_netting_set_id ? `Set #${bookedDeal.ccr_netting_set_id} · rattachement booké` : 'Aucun — sans netting' }}</span><select v-else v-model="setId" class="select mt-1" :disabled="!counterpartyId"><option :value="null">Aucun — sans netting</option><option v-for="s in sets" :key="s.id" :value="s.id">{{ s.data.netting_set_id }}</option></select></label>
      <span class="text-xs text-slate-500">{{ counterpartyName || (rfqId ? 'Contrepartie liée au fournisseur RFQ' : 'Standalone') }}</span>
    </div>
    <div class="flex flex-wrap gap-2"><button class="btn-secondary btn-sm" :disabled="busy || (!pricing && !rfqId && !bookedDeal)" @click="run('FAST')">{{ busy ? 'Calcul…' : 'Contrôle rapide — exposition courante' }}</button><button class="btn-primary btn-sm" :disabled="busy || (!pricing && !rfqId && !bookedDeal)" @click="run('FULL')">{{ bookedDeal ? 'Calculer le risque du deal' : 'Calcul CCR complet' }}</button></div>
    <p class="text-xs text-slate-500">{{ bookedDeal ? 'Contrat booké : fixings officiels et payoff résiduel conservés. Le CCR prépare son MtM à la date de calcul avec un taux provisoire commun de 3 %. La PFE mesure l’exposition économique envers la contrepartie ; pour une note, celle-ci doit être l’émetteur juridique. La CVA exige des données de crédit et de recouvrement.' : 'Le contrôle rapide ne calcule pas de PFE. Le booking réévalue les limites contraignantes côté serveur.' }}</p>
    <AlertMessage v-if="error" kind="error">{{ error }}</AlertMessage>
    <div v-if="result" class="ccr-credit-results" tabindex="0" aria-label="Résultats du contrôle crédit"><CcrResult :result="result" /></div>
  </section>
</template>
<script setup>
import { ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { ccrApi } from '../utils/ccr.js'
import HelpTip from './HelpTip.vue'
import { ccrHelp } from '../utils/ccrHelp.js'
import CcrResult from './CcrResult.vue'
import AlertMessage from './ui/AlertMessage.vue'
const props = defineProps({ counterpartyName: String, pricing: Object, nominal: Number, currency: String, sens: String, productType: String, rfqId: Number, quoteId: Number, bookedDeal: Object })
const emit = defineEmits(['netting-set'])
const counterpartyId = ref(null), sets = ref([]), setId = ref(null), result = ref(null), busy = ref(false), error = ref('')
const hypothetical = ref(false), recovery = ref(40), pdCurve = ref('[[1, 0.01], [5, 0.05], [10, 0.10]]')
let generation = 0
let calculationRevision = 0
const localToday = () => {
  const now = new Date()
  return new Date(now.getTime() - now.getTimezoneOffset() * 60_000).toISOString().slice(0, 10)
}
watch(() => [props.counterpartyName, props.pricing, props.nominal, props.sens, props.currency, props.rfqId, props.quoteId, props.productType, props.bookedDeal, setId.value, hypothetical.value, recovery.value, pdCurve.value], () => { calculationRevision++; result.value = null }, { deep: true })
watch(() => [props.counterpartyName, props.rfqId, props.quoteId, props.bookedDeal?.id], async ([name, rfqId, quoteId]) => {
  const g = ++generation
  counterpartyId.value = null; sets.value = []; setId.value = null; result.value = null
  if (props.bookedDeal?.id) {
    counterpartyId.value = props.bookedDeal.counterparty_id || null
    setId.value = props.bookedDeal.ccr_netting_set_id || null
    return
  }
  if (!name && !rfqId) return
  try {
    if (rfqId && quoteId) {
      const context = await ccrApi(`/rfq/${rfqId}/quotes/${quoteId}/context`)
      if (g !== generation) return
      counterpartyId.value = context.counterparty_id
      sets.value = context.configuration['netting-sets'].filter(s => s.data.active)
      return
    }
    const rows = await ccrApi('/counterparties')
    if (g !== generation) return
    counterpartyId.value = rows.find(c => c.name === name)?.id || null
    if (counterpartyId.value) {
      const cfg = await ccrApi(`/counterparties/${counterpartyId.value}/configuration`)
      if (g === generation) sets.value = cfg['netting-sets'].filter(s => s.data.active)
    }
  } catch (e) { error.value = e.message }
}, { immediate: true })
watch(setId, value => { if (!props.bookedDeal) emit('netting-set', value); result.value = null })
watch(() => [props.pricing, props.nominal, props.sens, props.currency, props.quoteId, props.productType], () => { result.value = null }, { deep: true })
async function run(mode) {
  const revision = calculationRevision
  busy.value = true; error.value = ''; result.value = null
  try {
    if (!props.bookedDeal && props.counterpartyName && !counterpartyId.value && !props.rfqId) throw new Error('Contrepartie non résolue : recharger le référentiel')
    const body = { mode, currency: props.bookedDeal?.devise || props.currency || 'EUR', counterparty_id: props.bookedDeal?.counterparty_id || counterpartyId.value }
    if (!counterpartyId.value && !props.rfqId && hypothetical.value) body.hypothetical_profile = {
      recovery:recovery.value / 100, recovery_source:'USER_ASSUMPTION', pd_measure:'RISK_NEUTRAL', curve_source:'MANUAL', pd_curve:JSON.parse(pdCurve.value), has_isda:false, has_csa:false,
    }
    let response
    if (props.bookedDeal?.id) {
      Object.assign(body, { deal_id:props.bookedDeal.id, data_scope:props.bookedDeal.uat_batch_id ? 'UAT' : 'PRODUCTION',
        prepare_mtm:true, common_rate:.03, allow_market_fetch:true,
        as_of_date:props.pricing?.valuation_date || localToday() })
      response = await ccrApi('/calculate', body)
    } else if (props.rfqId) response = await ccrApi(`/rfq/${props.rfqId}/quotes/${props.quoteId}/check`, {...body, netting_set_id:setId.value})
    else {
      body.proposed = { pricing: props.pricing, nominal: props.nominal, currency: props.currency, sens: props.sens, product_type: props.productType || '', netting_set_id: setId.value }
      response = await ccrApi('/calculate', body)
    }
    if (revision === calculationRevision) result.value = response
    else error.value = 'Les entrées ont changé pendant le calcul : relancer le contrôle.'
  } catch (e) { error.value = e.message } finally { busy.value = false }
}
</script>

<style scoped>
.ccr-credit-check { min-width: 0; }
.ccr-credit-check label { min-width: 0; }
.ccr-credit-check .input, .ccr-credit-check .select { min-width: 0; }
.ccr-credit-check textarea { max-height: 12rem; resize: vertical; }
.ccr-hypotheses { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: .75rem; }
.ccr-hypotheses label { display: flex; flex-direction: column; gap: .25rem; }
.ccr-hypotheses label > span { min-height: 2.5rem; display: flex; align-items: end; }
.ccr-credit-results { min-width: 0; max-height: min(60dvh, 42rem); overflow: auto; overscroll-behavior: auto; scrollbar-gutter: stable; padding: .25rem; border-top: 1px solid var(--border); }
.ccr-credit-results:focus-visible { outline: 2px solid var(--accent); outline-offset: -2px; }
@media (max-width: 639px) {
  .ccr-hypotheses { grid-template-columns: minmax(0, 1fr); }
  .ccr-hypotheses label > span { min-height: auto; }
}
</style>
