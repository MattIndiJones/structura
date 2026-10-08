<!--
  Shared PARAM + CONSTAT editor for the RFQ module — used both at creation
  time and in the RFQ detail panel (so pricing hypotheses can be revisited
  before recalculating the model price, not just frozen at creation).
  Mirrors the Pricer's own CONSTAT calendar UI (DealTab.vue) and constat
  data shape (pricing.js: constatOverrides / buildConstats), simplified to
  what a single-underlying RFQ needs.
-->
<template>
  <div class="flex flex-col gap-4">
    <div v-if="parsedParams.length" class="flex flex-col gap-2">
      <div class="label mb-0">Termes du produit</div>
      <div class="grid grid-cols-2 sm:grid-cols-3 gap-3">
        <div v-for="p in parsedParams" :key="p.name" class="flex flex-col gap-1">
          <label class="label">{{ p.name }}</label>
          <div class="relative">
            <template v-if="p.kind === 'array'">
              <div v-for="(_, i) in paramOverrides[p.name]" :key="i" class="flex gap-1">
                <input type="number" class="input pr-6" step="any" v-model.number="paramOverrides[p.name][i]" />
                <button type="button" v-if="paramOverrides[p.name].length > 1" @click="paramOverrides[p.name].splice(i, 1)">−</button>
              </div>
              <button type="button" class="text-xs" @click="paramOverrides[p.name].push(null)">+ Observation</button>
            </template>
            <input v-else type="number" class="input pr-6" step="any" v-model.number="paramOverrides[p.name]" />
            <span v-if="p.is_pct" class="absolute right-2 top-1/2 -translate-y-1/2 text-xs text-slate-500">%</span>
          </div>
          <span v-if="p.desc && p.desc !== p.name" class="text-[10px] text-slate-600">{{ p.desc }}</span>
        </div>
      </div>
    </div>

    <PayScriptCalendars :declarations="constats" :values="constatOverrides" :currency="currency" />

  </div>
</template>

<script setup>
import PayScriptCalendars from './PayScriptCalendars.vue'

const props = defineProps({
  parsedParams: { type: Array, default: () => [] },
  paramOverrides: { type: Object, required: true },
  constats: { type: Array, default: () => [] },
  constatOverrides: { type: Object, required: true },
  // Devise du cash : elle nomme le calendrier de jours ouvrés sur lequel les
  // constatations sont roulées et les décalages de règlement comptés. Le
  // marché du sous-jacent n'y joue aucun rôle.
  currency: { type: String, default: 'EUR' },
})

function tenorStr(t) {
  return (t && t.value) ? `${t.value}${t.unit}` : null
}

// Ce que l'aperçu envoie au serveur — la forme de l'API, pas celle de l'état
// local de cet éditeur.
function scheduleRequest(c) {
  const v = props.constatOverrides[c.name] || {}
  return {
    start_date: v.start_date, end_date: v.end_date, roll_date: v.roll_date,
    frequency: tenorStr(v.frequency), stub: v.stub,
    sub_frequency: tenorStr(v.sub_frequency) || null,
    currency: props.currency,
    convention: v.convention || 'none',
    settlement_lag: v.settlement_lag || 0,
  }
}
</script>
