<template>
  <div class="col-span-full mt-1">
    <label class="flex items-center gap-2 cursor-pointer select-none">
      <input type="checkbox" :checked="au.ccyCurveEnabled" @change="toggle" />
      <span class="label mb-0">Courbe {{ au.ccy }} (taux zéro)
        <HelpTip width="w-80" :text="`Courbe de taux zéro de la devise du sous-jacent. Elle porte son forward pas à pas (drift quanto, trajectoire de change du compo, nappe de vol locale, levier LSV). Désactivée, le taux plat ${au.ccy} ci-dessus s'applique. L'actualisation reste celle du deal.`" />
      </span>
    </label>

    <div v-if="au.ccyCurveEnabled" class="mt-2 space-y-1">
      <div v-for="(pillar, index) in au.ccyCurve" :key="index" class="flex items-center gap-2">
        <div class="relative w-24">
          <SensitiveValue mode="input">
            <input v-model.number="pillar.T" type="number" step="0.5" min="0.01" class="input pr-6 font-mono"
                   :aria-label="`Maturité du pilier ${index + 1}`" />
          </SensitiveValue>
          <span class="absolute right-2 top-1/2 -translate-y-1/2 text-slate-500 text-xs pointer-events-none">an</span>
        </div>
        <div class="relative w-24">
          <SensitiveValue mode="input">
            <input v-model.number="pillar.rate" type="number" step="0.05" class="input pr-6 font-mono"
                   :aria-label="`Taux du pilier ${index + 1}`" />
          </SensitiveValue>
          <span class="absolute right-2 top-1/2 -translate-y-1/2 text-slate-500 text-xs pointer-events-none">%</span>
        </div>
        <button type="button" class="text-xs text-slate-500 hover:text-red-400"
                :disabled="au.ccyCurve.length <= 1" @click="au.ccyCurve.splice(index, 1)"
                :aria-label="`Supprimer le pilier ${index + 1}`">✕</button>
      </div>
      <button type="button" class="text-xs text-slate-400 hover:text-blue-400" @click="addPillar">
        + Ajouter un pilier
      </button>
      <p v-if="orderError" class="text-xs text-amber-400">{{ orderError }}</p>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import HelpTip from './HelpTip.vue'
import SensitiveValue from './SensitiveValue.vue'

const props = defineProps({ au: { type: Object, required: true } })
const DEFAULT_PILLARS = [1, 2, 3, 5, 7, 10]

function toggle() {
  const u = props.au
  u.ccyCurveEnabled = !u.ccyCurveEnabled
  // Seeded at the flat rate: enabling the curve alone must not move the price.
  if (u.ccyCurveEnabled && !(u.ccyCurve || []).length) {
    const flat = Number.isFinite(Number(u.r_ccy)) && u.r_ccy !== null ? Number(u.r_ccy) : 0
    u.ccyCurve = DEFAULT_PILLARS.map(T => ({ T, rate: flat }))
  }
}

function addPillar() {
  const curve = props.au.ccyCurve
  const last = curve[curve.length - 1]
  curve.push({ T: last ? Number(last.T) + 1 : 1, rate: last ? Number(last.rate) : 0 })
}

const orderError = computed(() => {
  const maturities = (props.au.ccyCurve || []).map(p => Number(p.T))
  if (maturities.some(T => !(T > 0))) return 'Chaque maturité doit être strictement positive.'
  if (maturities.some((T, i) => i && T <= maturities[i - 1])) return 'Les maturités doivent être strictement croissantes.'
  return ''
})
</script>
