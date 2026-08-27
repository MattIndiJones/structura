<!--
  Décomposition d'un prix Monte Carlo en flux — PV par composante.

  Extrait de ResultsPanel (onglet Flux du Pricer) pour être partagé avec le
  module RFQ : un prix modèle qu'on oppose à une cotation fournisseur doit
  pouvoir s'expliquer ligne à ligne, et il n'y a aucune raison que le Pricer
  et l'AO le racontent différemment.

  Piloté par props (pas par le store du Pricer) : `result` est la réponse
  brute de /api/price, `originDate` la date de strike — origine de l'axe des
  temps du moteur, donc seule ancre valide pour reconvertir un t en date.
  `valueDate` ne sert plus que de repli pour les appelants qui n'ont pas de
  date de strike ; sans l'une ni l'autre les échéances restent en T+n ans.
-->
<template>
  <div class="flex flex-col gap-4">
    <div v-if="groups.length === 0"
         class="flex flex-col items-center justify-center py-12 gap-2 text-slate-600">
      <div class="text-3xl">💰</div>
      <div class="text-sm font-medium">Aucun flux — vérifiez les instructions PAY dans le script</div>
    </div>

    <template v-else>
      <!-- Résumé -->
      <div class="grid grid-cols-3 gap-3">
        <div class="stat-box min-w-0">
          <div class="text-xs text-slate-500 mb-1">Prix MC (PV Σ)</div>
          <div class="text-xl font-bold text-blue-400"><SensitiveValue>{{ f2(result.price) }} %</SensitiveValue></div>
        </div>
        <div class="stat-box min-w-0">
          <div class="text-xs text-slate-500 mb-1">Dates de flux</div>
          <div class="text-xl font-bold text-slate-200">{{ formatInt(groups.length) }}</div>
        </div>
        <div class="stat-box min-w-0">
          <div class="text-xs text-slate-500 mb-1">N chemins</div>
          <div class="text-xl font-bold text-slate-300"><SensitiveValue>{{ formatInt(result.n_eff) }}</SensitiveValue></div>
        </div>
      </div>

      <!-- Table -->
      <div class="card overflow-x-auto table-shell" tabindex="0" role="region">
        <div class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-1">
          💰 Décomposition des flux — PV par composante
        </div>
        <div class="text-[11px] text-slate-600 mb-4">
          Contribution PV = E[CF] × DF · la somme des lignes reconstitue le prix MC
        </div>
        <table class="w-full min-w-[520px] text-xs border-collapse">
          <thead>
            <tr class="bg-slate-800/60 border-b-2 border-slate-700">
              <th class="text-left py-1.5 px-2 whitespace-nowrap">Date
                <HelpTip text="Date de CONSTATATION du flux, comptée depuis la date de strike — origine de la diffusion. Quand le règlement tombe plus tard (décalage de règlement du CONSTAT, ou date de paiement du remboursement final), la date d'échange du cash est rappelée en dessous : c'est elle qui porte l'actualisation, donc le DF de la ligne." />
              </th>
              <th class="text-left py-1.5 px-2">Expression</th>
              <th class="text-right py-1.5 px-2 whitespace-nowrap num">P(actif)
                <HelpTip align="right" text="Fraction des chemins simulés où cette instruction PAY a effectivement produit un flux (ex : condition IF vraie, produit pas encore rappelé). 100% = flux systématique." />
              </th>
              <th class="text-right py-1.5 px-2 whitespace-nowrap num">E[CF]
                <HelpTip align="right" text="Espérance du flux brut, non actualisé, moyennée sur tous les chemins (y compris ceux où il vaut 0). C'est le montant avant application du facteur d'actualisation DF." />
              </th>
              <th class="text-right py-1.5 px-2 whitespace-nowrap num">DF
                <HelpTip align="right" text="Facteur d'actualisation implicite = PV ÷ E[CF]. Sous taux déterministes c'est exp(−r·t) ; sous taux stochastiques c'est l'espérance conditionnelle E[B(0,t) | ce flux se déclenche], donc peut différer légèrement de exp(−r·t)." />
              </th>
              <th class="text-right py-1.5 px-2 whitespace-nowrap num">Contrib. PV
                <HelpTip align="right" text="Contribution actualisée de cette ligne au prix total = E[CF] × DF. La somme de toutes les lignes de toutes les dates redonne exactement le prix Monte Carlo." />
              </th>
            </tr>
          </thead>
          <tbody>
            <template v-for="grp in groups" :key="grp.tKey">
              <tr v-for="(row, ri) in grp.rows" :key="row.key"
                  :class="[
                    ri < grp.rows.length - 1 ? 'border-b border-slate-800' : 'border-b-2 border-slate-700',
                    row.pv < 0 ? 'bg-red-950/20' : ''
                  ]">
                <td class="py-1.5 px-2 font-bold text-slate-300 whitespace-nowrap align-top text-[10px]">
                  <template v-if="ri === 0">
                    <div>{{ grp.label }}</div>
                    <div v-if="grp.payLabel" class="font-normal text-slate-500 text-[9px]">
                      règl. {{ grp.payLabel }}
                    </div>
                  </template>
                </td>
                <td class="py-1.5 px-2 font-mono text-[11px]"
                    :class="row.pv < 0 ? 'text-red-400' : 'text-slate-500'">{{ row.lbl }}</td>
                <td class="py-1.5 px-2 text-right num text-slate-400"><SensitiveValue>{{ formatPercent(row.pAct, 1) }}</SensitiveValue></td>
                <td class="py-1.5 px-2 text-right num font-semibold font-mono"
                    :class="row.eCF >= 0 ? 'text-slate-300' : 'text-red-400'">
                  <SensitiveValue>{{ formatSignedPercent(row.eCF, 2) }}</SensitiveValue>
                </td>
                <td class="py-1.5 px-2 text-right num font-mono text-slate-400">
                  <SensitiveValue>{{ formatNumber(row.df, 4) }}</SensitiveValue>
                </td>
                <td class="py-1.5 px-2 text-right num font-bold font-mono"
                    :class="row.pv >= 0 ? 'text-green-400' : 'text-red-400'">
                  <SensitiveValue>{{ formatSignedPercent(row.pv, 3) }}</SensitiveValue>
                </td>
              </tr>
            </template>
          </tbody>
          <tfoot>
            <tr class="bg-slate-800/60 border-t-2 border-slate-600">
              <td colspan="5" class="py-2 px-2 font-black text-slate-200">= Prix total</td>
              <td class="py-2 px-2 text-right num font-black text-blue-400 text-sm">
                <SensitiveValue>{{ formatPercent(total, 2) }}</SensitiveValue>
              </td>
            </tr>
          </tfoot>
        </table>
      </div>

      <!-- Contrôle de cohérence : muet tant que les flux reconstituent le prix.
           Un écart visible veut dire qu'une jambe du payoff n'est pas dans la
           table — donc que le prix qu'on oppose au fournisseur n'est pas
           entièrement explicable. -->
      <div v-if="reconciliationGap != null"
           class="rounded-lg border border-amber-800/60 bg-amber-950/20 px-3 py-2 text-[11px] text-amber-400">
        ⚠ La somme des flux ({{ formatPercent(total, 3) }}) ne reconstitue pas le prix Monte Carlo
        ({{ formatPercent(result.price * 100, 3) }}) — écart de
        {{ formatSignedPercent(reconciliationGap, 3) }} pt. Vérifiez les instructions PAY du script.
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import SensitiveValue from './SensitiveValue.vue'
import HelpTip from './HelpTip.vue'
import { formatDate, formatInt, formatNumber, formatPercent } from '../utils/format.js'

const props = defineProps({
  // Réponse brute de /api/price (price, flux_table, n_eff…), ou null.
  result:    { type: Object, default: null },
  // Origine de l'axe des temps du moteur, ISO — la date de STRIKE, puisque
  // c'est là que le niveau initial se constate et que la diffusion démarre.
  originDate: { type: String, default: null },
  // Repli pour les appelants sans date de strike. Ancrer sur elle décale
  // toutes les échéances de (value − strike) : c'est faux dès que les deux
  // dates diffèrent, ce qui est le cas normal d'un produit réel.
  valueDate: { type: String, default: null },
})

const anchor = computed(() => props.originDate || props.valueDate)

const f2 = v => (v != null ? formatNumber(v * 100, 2) : '—')
const formatSignedPercent = (value, decimals) =>
  (value >= 0 ? '+' : '') + formatPercent(value, decimals)

function addDaysStr(isoDate, days) {
  const d = new Date(isoDate)
  d.setDate(d.getDate() + Math.round(days))
  return d.toISOString().split('T')[0]
}

function tToCalDate(t) {
  if (!anchor.value) return t < 0.005 ? 'T₀' : 'T + ' + formatNumber(t, 2) + ' ans'
  return formatDate(addDaysStr(anchor.value, t * 365.25))
}

const groups = computed(() => {
  const ft = props.result?.flux_table
  if (!ft) return []
  const N = props.result.n_eff || props.result.n_paths || 1
  const byDate = new Map()

  for (const [key, d] of Object.entries(ft)) {
    if (!d || typeof d.t !== 'number') continue
    // Groupé sur le COUPLE (constatation, règlement) : à une même
    // constatation, un coupon et un remboursement final peuvent tomber sur
    // deux dates de paiement distinctes, et les confondre reviendrait à
    // afficher une échéance de cash qui n'existe pas.
    const tPay = typeof d.t_pay === 'number' ? d.t_pay : d.t
    const tKey = d.t.toFixed(6) + '|' + tPay.toFixed(6)
    if (!byDate.has(tKey)) {
      const t = d.t
      byDate.set(tKey, {
        t, tKey,
        label: tToCalDate(t),
        // Muet quand le cash bouge le jour même : n'afficher la date de
        // paiement que lorsqu'elle apprend quelque chose.
        payLabel: Math.abs(tPay - t) > 1e-6 ? tToCalDate(tPay) : null,
        rows: [],
      })
    }
    const pvRaw = typeof d.pv === 'number' ? d.pv : (d.sum ?? 0)
    const eCF   = (d.sum ?? 0) / N * 100
    const pv    = pvRaw / N * 100
    byDate.get(tKey).rows.push({
      key,
      lbl:    d.lbl ?? key,
      n:      d.n ?? 0,
      pAct:   (d.n ?? 0) / N * 100,
      eCF,
      pv,
      df:     typeof d.df === 'number' ? d.df : null,
    })
  }

  return [...byDate.values()]
    .sort((a, b) => a.t - b.t)
    .map(g => ({ ...g, rows: [...g.rows].sort((a, b) => b.pv - a.pv) }))
})

const total = computed(() =>
  groups.value.reduce((s, g) => s + g.rows.reduce((rs, r) => rs + r.pv, 0), 0)
)

// null tant que l'écart reste sous un demi-point de base — les valeurs de
// flux_table sont arrondies à 1e-6 côté serveur, un résidu est normal.
const reconciliationGap = computed(() => {
  if (props.result?.price == null || groups.value.length === 0) return null
  const gap = total.value - props.result.price * 100
  return Math.abs(gap) > 0.005 ? gap : null
})
</script>
