<template>
  <div class="space-y-4 text-sm" style="color: var(--text)">
    <p class="text-xs" style="color: var(--muted)">
      Ces paramètres seront enregistrés avec le deal. Le MtM reprendra par défaut le modèle,
      les volatilités, les corrélations, les taux et le funding du booking, avec les cours et la
      date de valorisation choisis. Le nombre de trajectoires décrit le pricing initial.
    </p>
    <p v-if="!hasReceipt" class="rounded-lg border border-amber-600/50 bg-amber-950/20 p-3 text-xs text-amber-400">
      Aucun résultat de pricing joint : les paramètres actuellement saisis seront enregistrés.
      Lancez ▶ Pricer pour rattacher un résultat vérifiable avant de confirmer.
    </p>
    <dl class="grid grid-cols-2 gap-3 rounded-lg border p-3 sm:grid-cols-3" style="border-color: var(--border)">
      <div><dt class="text-xs" style="color: var(--muted)">Modèle de volatilité</dt><dd class="font-semibold">{{ modelLabel }}</dd></div>
      <div><dt class="text-xs" style="color: var(--muted)">Taux sans risque</dt><dd>{{ pct(snapshot.r) }}</dd></div>
      <div><dt class="text-xs" style="color: var(--muted)">Trajectoires du prix initial</dt><dd>{{ number(snapshot.N) }}</dd></div>
      <div><dt class="text-xs" style="color: var(--muted)">Modèle de taux</dt><dd>{{ rateModelLabel }}</dd></div>
      <div><dt class="text-xs" style="color: var(--muted)">Funding</dt><dd>{{ fundingLabel }}</dd></div>
      <div><dt class="text-xs" style="color: var(--muted)">Barrières</dt><dd>{{ snapshot.barrierMonitoring === 'continuous' ? 'Monitoring continu' : 'Grille hebdomadaire' }}</dd></div>
      <div><dt class="text-xs" style="color: var(--muted)">Tirages antithétiques</dt><dd>{{ snapshot.antithetic ? 'Oui' : 'Non' }}</dd></div>
      <div v-if="pricingDate"><dt class="text-xs" style="color: var(--muted)">Date du prix initial</dt><dd>{{ pricingDate }}</dd></div>
      <div v-if="snapshot.rateModel !== 'deterministic' && snapshot.sigma_r != null"><dt class="text-xs" style="color: var(--muted)">σ taux</dt><dd>{{ pct(snapshot.sigma_r) }}</dd></div>
    </dl>

    <div v-for="(u, index) in snapshot.underlyings || []" :key="`${u.ticker || u.name}-${index}`"
         class="rounded-lg border p-3" style="border-color: var(--border)">
      <h3 class="font-semibold mb-2">{{ u.name || u.ticker || `Sous-jacent ${index + 1}` }} <span class="font-normal text-xs" style="color: var(--muted)">{{ u.ticker }} · {{ u.ccy }}</span></h3>
      <dl class="grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-3">
        <div v-for="field in underlyingFields(u)" :key="field.key">
          <dt class="text-xs" style="color: var(--muted)">{{ field.label }}</dt>
          <dd>{{ field.value }}</dd>
        </div>
      </dl>
      <p v-if="u.dividendCurve?.length" class="mt-2 text-xs" style="color: var(--muted)">
        Courbe de dividendes : {{ u.dividendCurve.map(p => `${number(p.T)} an(s) ${pct(p.rate)}`).join(' · ') }}
      </p>
    </div>

    <div v-if="snapshot.yieldCurve?.length" class="text-xs">
      <strong>Courbe de taux :</strong> {{ snapshot.yieldCurve.map(p => `${number(p.T)} an(s) ${pct(p.rate)}`).join(' · ') }}
    </div>
    <div v-if="snapshot.funding?.mode === 'pillars' && snapshot.funding.pillars?.length" class="text-xs">
      <strong>Courbe de funding :</strong> {{ snapshot.funding.pillars.map(p => `${number(p.T)} an(s) ${pct(p.spread)}`).join(' · ') }}
    </div>
    <div v-if="snapshot.corrMatrix?.length > 1" class="text-xs">
      <strong>Corrélations :</strong>
      <span v-for="(row, i) in snapshot.corrMatrix" :key="i">
        <span v-for="(corr, j) in row" :key="j">
          <span v-if="j > i">{{ snapshot.underlyings?.[i]?.name || i + 1 }} / {{ snapshot.underlyings?.[j]?.name || j + 1 }} {{ number(corr) }} · </span>
        </span>
      </span>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  snapshot: { type: Object, required: true },
  hasReceipt: { type: Boolean, default: false },
  pricingDate: { type: String, default: '' },
})

const modelLabel = computed(() => ({
  constant: 'Vol constante (GBM)', heston: 'Heston QE', sabr: 'SABR (Hagan)',
  localvol: 'Vol locale (Dupire)', lsv: 'Vol locale stochastique (LSV)',
})[props.snapshot.model] || props.snapshot.model || 'Non renseigné')
const rateModelLabel = computed(() => ({
  deterministic: 'Déterministe', abm: 'ABM stochastique', hull_white: 'Hull-White',
})[props.snapshot.rateModel] || props.snapshot.rateModel || 'Déterministe')
const number = value => Number.isFinite(Number(value)) ? new Intl.NumberFormat('fr-FR', { maximumFractionDigits: 4 }).format(Number(value)) : '—'
const pct = value => value == null ? '—' : `${number(value)} %`
const fundingLabel = computed(() => {
  if (props.snapshot.funding?.mode === 'pillars' && props.snapshot.funding.pillars?.length) return 'Courbe'
  if (props.snapshot.funding?.level != null) return pct(props.snapshot.funding.level)
  return pct(Number(props.snapshot.funding_spread || 0) * 100)
})

function underlyingFields(u) {
  const fields = [
    { key: 'sigma', label: 'Vol implicite', value: pct(u.sigma) },
    { key: 'q', label: 'Dividende', value: pct(u.q) },
  ]
  const model = props.snapshot.model
  const modelFields = {
    heston: [['v0', 'V₀', true], ['kappa', 'κ', false], ['theta', 'θ', true], ['xi', 'ξ', true], ['rho_h', 'ρ Heston', true]],
    sabr: [['alpha', 'α', true], ['beta', 'β', true], ['rho', 'ρ SABR', true], ['nu', 'ν', true]],
    localvol: [['skew', 'Skew', true], ['curvature', 'Convexité', true]],
    lsv: [['v0', 'V₀', true], ['kappa', 'κ', false], ['theta', 'θ', true], ['xi', 'ξ', true], ['rho_h', 'ρ Heston', true], ['skew', 'Skew', true], ['curvature', 'Convexité', true]],
  }[model] || []
  for (const [key, label, percent] of modelFields) {
    if (u[key] != null) fields.push({ key, label, value: percent ? pct(u[key]) : number(u[key]) })
  }
  if (u.sigma_fx != null && u.ccy !== props.snapshot.deal_ccy) {
    fields.push({ key: 'sigma_fx', label: 'Vol FX', value: pct(u.sigma_fx) })
    if (u.rho_sfx != null) fields.push({ key: 'rho_sfx', label: 'ρ spot/FX', value: pct(u.rho_sfx) })
    if (u.ccyh != null) fields.push({ key: 'ccyh', label: 'Basis FX', value: `${number(u.ccyh)} bp` })
  }
  if (u.rho_rS != null && props.snapshot.rateModel !== 'deterministic') {
    fields.push({ key: 'rho_rS', label: 'ρ spot/taux', value: pct(u.rho_rS) })
  }
  return fields
}
</script>
