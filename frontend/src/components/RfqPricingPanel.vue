<!--
  Panneau de contrôle du prix modèle d'un AO — colonne droite du détail RFQ.

  Le prix qu'on oppose à un fournisseur ne vaut que si on peut l'expliquer :
  d'où il vient (flux par date), à quel bruit près il est connu (IC 95 %),
  et sous quelles hypothèses il a été produit. Ce panneau met les trois au
  même endroit, à côté du bouton qui les a produits.

  Il vit sur la dernière réponse /api/price conservée par le store — non
  persistée : après un rechargement de page, le prix reste (il est en base)
  mais sa décomposition demande un recalcul, et le panneau le dit.
-->
<template>
  <aside class="flex flex-col gap-4">
    <div class="flex items-center justify-between">
      <div class="text-xs font-bold text-slate-400 uppercase tracking-wider">Contrôle du prix modèle</div>
      <span v-if="pricing?.at" class="text-[10px] text-slate-600">{{ fmtDateTime(pricing.at) }}</span>
    </div>

    <!-- Rien à montrer : on distingue « jamais calculé » de « calculé mais
         plus en mémoire », parce que l'action à faire n'est pas la même. -->
    <div v-if="!result" class="card flex flex-col items-center justify-center gap-2 py-10 text-center">
      <div class="text-3xl">🧮</div>
      <template v-if="rfq?.model_price != null">
        <div class="text-xs text-slate-400">Prix modèle en base : <span class="font-semibold text-slate-200">{{ fmtPts(rfq.model_price) }}</span></div>
        <div class="text-[11px] text-slate-600 max-w-[34ch]">
          Sa décomposition n'est pas conservée d'une session à l'autre — relancez
          « Calculer prix modèle » pour la voir.
        </div>
      </template>
      <template v-else>
        <div class="text-sm font-medium text-slate-500">Aucun prix modèle</div>
        <div class="text-[11px] text-slate-600 max-w-[34ch]">
          Lancez « Calculer prix modèle » : le prix, son intervalle de confiance
          et le détail des flux s'afficheront ici.
        </div>
      </template>
    </div>

    <template v-else>
      <!-- Indicateurs de fiabilité du chiffre -->
      <div class="card grid grid-cols-2 gap-3">
        <div class="stat-box min-w-0 col-span-2">
          <div class="text-[10px] text-slate-500 uppercase tracking-wider mb-1">
            Prix Monte Carlo
            <HelpTip text="Espérance actualisée du payoff sous la mesure risque-neutre, en points de nominal (100 = pair). C'est le chiffre stocké sur l'AO et celui auquel les cotations fournisseurs sont comparées." />
          </div>
          <div class="text-2xl font-bold text-slate-100"><SensitiveValue>{{ fmtPts(pts(result.price)) }}</SensitiveValue></div>
        </div>

        <div class="stat-box min-w-0">
          <div class="text-[10px] text-slate-500 uppercase tracking-wider mb-1">
            IC 95 %
            <HelpTip text="Intervalle de confiance à 95 % du prix, dû au seul bruit d'échantillonnage Monte Carlo. Tant qu'un écart de cotation reste dans cet intervalle, il n'est pas distinguable du bruit de simulation : augmentez N avant d'en tirer une conclusion de négociation." />
          </div>
          <div class="text-sm font-bold text-slate-200 font-mono">
            <SensitiveValue>± {{ fmtPts(ic95Half) }}</SensitiveValue>
          </div>
          <div v-if="ic95Bps != null" class="text-[10px] text-slate-600 mt-0.5">
            ± {{ formatNumber(ic95Bps, 1) }} bps du prix
          </div>
        </div>

        <div class="stat-box min-w-0">
          <div class="text-[10px] text-slate-500 uppercase tracking-wider mb-1">
            Durée de vie
            <HelpTip text="Fugit : maturité espérée du produit, en années, compte tenu des rappels anticipés simulés. Sur un autocall c'est la vraie duration à opposer au fournisseur — la maturité contractuelle n'est atteinte que dans les scénarios sans rappel." />
          </div>
          <div class="text-sm font-bold text-slate-200 font-mono">
            <SensitiveValue>{{ result.fugit != null ? formatNumber(result.fugit, 2) + ' ans' : '—' }}</SensitiveValue>
          </div>
          <div v-if="result.t_max_effective != null" class="text-[10px] text-slate-600 mt-0.5">
            maturité {{ formatNumber(result.t_max_effective, 2) }} ans
          </div>
        </div>

        <div class="stat-box min-w-0">
          <div class="text-[10px] text-slate-500 uppercase tracking-wider mb-1">
            Médiane
            <HelpTip text="Payoff médian actualisé sur les trajectoires simulées. Un écart marqué entre médiane et prix moyen signale une distribution asymétrique — typique d'un produit à barrière, où une minorité de scénarios porte l'essentiel de la perte." />
          </div>
          <div class="text-sm font-bold text-slate-200 font-mono">
            <SensitiveValue>{{ result.median != null ? fmtPts(pts(result.median)) : '—' }}</SensitiveValue>
          </div>
        </div>

        <div class="stat-box min-w-0">
          <div class="text-[10px] text-slate-500 uppercase tracking-wider mb-1">
            Chemins
            <HelpTip text="Nombre de trajectoires effectivement retenues dans la moyenne (après antithétiques éventuels). L'erreur Monte Carlo décroît en 1/√N : quadrupler N divise l'IC par deux." />
          </div>
          <div class="text-sm font-bold text-slate-200 font-mono">
            <SensitiveValue>{{ formatInt(result.n_eff) }}</SensitiveValue>
          </div>
          <div v-if="result.elapsed_ms != null" class="text-[10px] text-slate-600 mt-0.5">
            {{ formatInt(result.elapsed_ms) }} ms
          </div>
        </div>
      </div>

      <!-- Sous quelles hypothèses ce chiffre a été produit -->
      <div class="card flex flex-col gap-1.5 text-[11px]">
        <div class="text-[10px] font-bold text-slate-500 uppercase tracking-wider">
          Hypothèses du calcul
          <HelpTip text="Les hypothèses effectivement envoyées au moteur pour ce calcul. Elles figent le chiffre : toute modification côté « Paramètres de pricing » invalide le prix modèle et impose un recalcul." />
        </div>
        <div class="flex flex-wrap gap-x-4 gap-y-1 text-slate-400 font-mono">
          <span>{{ modelLabel }}</span>
          <span v-if="h.sigma != null">σ {{ formatNumber(h.sigma * 100, 2) }} %</span>
          <span v-if="h.q != null">q {{ formatNumber(h.q * 100, 2) }} %</span>
          <span v-if="h.r != null">r {{ formatNumber(h.r * 100, 2) }} %</span>
          <span v-if="h.N != null">N {{ formatInt(h.N) }}</span>
        </div>
      </div>

      <FluxDecomposition :result="result" :origin-date="pricing.strikeDate"
                         :value-date="pricing.valueDate" />
    </template>
  </aside>
</template>

<script setup>
import { computed } from 'vue'
import FluxDecomposition from './FluxDecomposition.vue'
import HelpTip from './HelpTip.vue'
import SensitiveValue from './SensitiveValue.vue'
import { formatDateTime, formatInt, formatNumber } from '../utils/format.js'

const props = defineProps({
  // L'AO courant (pour son model_price déjà en base).
  rfq:     { type: Object, default: null },
  // Entrée lastPricing du store :
  // { rfqId, result, strikeDate, valueDate, hypotheses, at }.
  pricing: { type: Object, default: null },
})

const MODEL_LABELS = {
  constant: 'Constant (GBM)',
  heston:   'Heston',
  sabr:     'SABR',
  localvol: 'Dupire (Local Vol)',
  lsv:      'Local-Stochastic Vol',
}

// Une décomposition ne vaut que pour l'AO qui l'a produite.
const result = computed(() =>
  props.pricing && props.pricing.rfqId === props.rfq?.id ? props.pricing.result : null
)

const h = computed(() => props.pricing?.hypotheses || {})
const modelLabel = computed(() => MODEL_LABELS[h.value.model] || h.value.model || '—')

// /api/price rend des fractions de nominal ; l'AO raisonne en points (100 = pair).
const pts = v => (v != null ? v * 100 : null)
const fmtPts = v => (v != null ? formatNumber(v, 3) : '—')
const fmtDateTime = v => (v ? formatDateTime(v) : '')

const ic95Half = computed(() => {
  const ic = result.value?.ic95
  if (!Array.isArray(ic) || ic.length < 2) return null
  return pts((ic[1] - ic[0]) / 2)
})

// Le même repère que les écarts de cotation de la table fournisseurs : sous ce
// seuil, un écart de prix n'est pas un edge, c'est du bruit de simulation.
const ic95Bps = computed(() => {
  const half = ic95Half.value
  const price = pts(result.value?.price)
  if (half == null || !price) return null
  return half / price * 10000
})
</script>
