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
            <input type="number" class="input pr-6" step="any" v-model.number="paramOverrides[p.name]" />
            <span v-if="p.is_pct" class="absolute right-2 top-1/2 -translate-y-1/2 text-xs text-slate-500">%</span>
          </div>
          <span v-if="p.desc && p.desc !== p.name" class="text-[10px] text-slate-600">{{ p.desc }}</span>
        </div>
      </div>
    </div>

    <div v-if="constats.length" class="flex flex-col gap-3 border-t border-slate-800 pt-3">
      <div class="label mb-0">Calendrier{{ constats.length > 1 ? 's' : '' }} CONSTAT</div>
      <div v-for="c in constats" :key="c.name" class="flex flex-col gap-1.5">
        <span class="text-xs font-semibold text-slate-300">{{ c.name }}</span>

        <div v-if="c.kind === 'single'" class="max-w-xs">
          <input type="date" v-model="constatOverrides[c.name]" class="input" />
        </div>

        <div v-else class="flex flex-col gap-2">
          <div class="flex flex-wrap items-end gap-2">
            <div class="flex flex-col gap-0.5">
              <label class="text-[10px] text-slate-600"
                     title="Début de la première période (typiquement la date de strike) — pas elle-même une observation, toujours exclue des dates de pricing. Pour N observations à partir d'une date donnée, recule cette date d'un cran (ex: date de strike).">Début ⓘ</label>
              <input type="date" v-model="constatOverrides[c.name].start_date" class="input py-1 px-2" />
            </div>
            <div class="flex flex-col gap-0.5">
              <label class="text-[10px] text-slate-600">Fin</label>
              <input type="date" v-model="constatOverrides[c.name].end_date" class="input py-1 px-2" />
            </div>
            <div class="flex flex-col gap-0.5">
              <label class="text-[10px] text-slate-600">Roll</label>
              <input type="date" v-model="constatOverrides[c.name].roll_date" class="input py-1 px-2" />
            </div>
            <div class="flex flex-col gap-0.5">
              <label class="text-[10px] text-slate-600">Fréquence</label>
              <div class="flex gap-1">
                <input type="number" min="1" v-model.number="constatOverrides[c.name].frequency.value" class="input py-1 px-2 w-14" />
                <select v-model="constatOverrides[c.name].frequency.unit" class="select py-1 pl-2 w-16">
                  <option value="D">D</option><option value="M">M</option><option value="Y">Y</option>
                </select>
              </div>
            </div>
            <div class="flex flex-col gap-0.5">
              <label class="text-[10px] text-slate-600"
                     title="Ce que devient une constatation qui tombe un week-end ou un jour férié du calendrier de la devise de règlement. « Aucun ajustement » laisse la date là où le term sheet l'a mise.">Convention ⓘ</label>
              <select v-model="constatOverrides[c.name].convention" class="select py-1 px-2">
                <option value="none">Aucun ajustement</option>
                <option value="following">Jour ouvré suivant</option>
                <option value="modified_following">Suivant, sauf changement de mois</option>
                <option value="preceding">Jour ouvré précédent</option>
                <option value="modified_preceding">Précédent, sauf changement de mois</option>
              </select>
            </div>
            <div class="flex flex-col gap-0.5">
              <label class="text-[10px] text-slate-600"
                     title="Jours ouvrés entre une constatation et le mouvement effectif du cash. 0 = payé le jour de la constatation.">Règlement ⓘ</label>
              <div class="flex items-center gap-1">
                <input type="number" min="0" max="30" class="input py-1 px-2 w-14"
                       v-model.number="constatOverrides[c.name].settlement_lag" />
                <span class="text-[10px] text-slate-600">j. ouvrés</span>
              </div>
            </div>
            <div class="flex flex-col gap-0.5">
              <label class="text-[10px] text-slate-600">Stub</label>
              <select v-model="constatOverrides[c.name].stub" class="select py-1 px-2">
                <option value="short_last">Short Last</option>
                <option value="long_last">Long Last</option>
                <option value="short_first">Short First</option>
                <option value="long_first">Long First</option>
              </select>
            </div>
            <div v-if="c.kind === 'nested_schedule'" class="flex flex-col gap-0.5">
              <label class="text-[10px] text-slate-600">Sous-fréquence</label>
              <div class="flex gap-1">
                <input type="number" min="1" v-model.number="constatOverrides[c.name].sub_frequency.value" class="input py-1 px-2 w-14" />
                <select v-model="constatOverrides[c.name].sub_frequency.unit" class="select py-1 pl-2 w-16">
                  <option value="D">D</option><option value="M">M</option><option value="Y">Y</option>
                </select>
              </div>
            </div>
          </div>
          <ObservationSchedule :request="scheduleRequest(c)" />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { reactive } from 'vue'
import ObservationSchedule from './ObservationSchedule.vue'

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
