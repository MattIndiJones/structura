<!--
  Avertissement porté par les analytiques qui prisent encore le produit NEUF.

  Le prix, les Greeks et le profil de payoff basculent sur la jambe résiduelle
  quand une date de valorisation est saisie. Les autres pas encore : elles
  décrivent la même structure émise aujourd'hui à 100 %.

  Sur une note dont le worst-of est à 34 % du strike, l'écart n'est pas un
  détail — l'onglet Probabilités annonçait 39 % de chance de rappel et 2,12 ans
  de durée espérée pour une vie restante de 1,10 an. Tant que ces onglets ne
  sont pas alignés, le dire vaut mieux que laisser lire.
-->
<template>
  <div v-if="store.isInLife()"
       class="rounded-lg border border-amber-800/60 bg-amber-950/20 px-3 py-2 mb-3
              text-[11px] text-amber-400 flex items-start gap-2">
    <span class="shrink-0">⚠</span>
    <span>
      Ces statistiques décrivent le produit <b>à l'émission</b>, pas au
      {{ formatDate(store.globalParams.valuation_date) }}.
      Le passé n'est pas rejoué ici : ni les coupons déjà accumulés, ni les
      barrières déjà franchies, ni la vie restante réelle.
      <span class="text-slate-500">
        Le prix, les Greeks et le profil de payoff, eux, sont bien calculés sur la
        vie restante.
      </span>
    </span>
  </div>
</template>

<script setup>
import { usePricingStore } from '../stores/pricing.js'
import { formatDate } from '../utils/format.js'

const store = usePricingStore()
</script>
