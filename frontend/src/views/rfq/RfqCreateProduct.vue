<template>
  <div class="card flex flex-col gap-3">
    <!-- Panier contractuel -->
    <div class="grid grid-cols-2 gap-3">
      <div class="col-span-2 flex flex-col gap-2">
        <div class="flex items-center justify-between gap-3">
          <label class="label mb-0">Panier ({{ createBasket.length }} sous-jacent{{ createBasket.length > 1 ? 's' : '' }})</label>
          <button type="button" class="btn-secondary text-xs px-2 py-1"
                  :disabled="!!sourceProduct" @click="addCreateUnderlying">
            + Ajouter un sous-jacent
          </button>
        </div>
        <div v-for="(underlying, index) in createBasket" :key="index"
             :class="['rounded-lg border p-2 grid grid-cols-12 gap-2 cursor-pointer',
                      createActiveUnderlyingIdx === index ? 'border-blue-500 bg-blue-950/10' : 'border-slate-800']"
             @click="createActiveUnderlyingIdx = index">
          <div class="col-span-4">
            <label class="label">Sous-jacent</label>
            <select class="select" :value="underlying.ticker"
                    :disabled="!!sourceProduct"
                    @change="onUnderlyingSelect(index, $event.target.value)">
              <option value="">— Choisir —</option>
              <optgroup v-for="g in underlyingGroups" :key="g.group" :label="g.group">
                <option v-for="it in g.items" :key="it.ticker" :value="it.ticker">{{ it.label }}</option>
              </optgroup>
            </select>
          </div>
          <div class="col-span-3"><label class="label">Ticker</label>
            <input v-model="underlying.ticker" :readonly="!!sourceProduct"
                   class="input font-mono text-xs" placeholder="Ticker"
                   @blur="onUnderlyingSelect(index, underlying.ticker)" />
          </div>
          <div class="col-span-2"><label class="label">Vol. (%)</label>
            <input v-model.number="underlying.sigma" type="number" step="0.1"
                   class="input" title="Volatilité en %" />
          </div>
          <div class="col-span-2"><label class="label">Div. (%)</label>
            <input v-model.number="underlying.q" type="number" step="0.1"
                   class="input" title="Rendement du dividende en %" />
          </div>
          <button type="button" class="icon-btn-danger col-span-1"
                  :disabled="createBasket.length === 1 || !!sourceProduct"
                  :aria-label="`Retirer ${underlying.name || underlying.ticker}`"
                  @click.stop="removeCreateUnderlying(index)">×</button>
          <div class="col-span-9"><label class="label">Nom du sous-jacent</label>
            <input v-model="underlying.name" :readonly="!!sourceProduct"
                   class="input text-xs" placeholder="Nom du sous-jacent" />
          </div>
          <div class="col-span-3"><label class="label">Devise du sous-jacent</label>
          <select v-model="underlying.ccy" class="select" :disabled="!!sourceProduct">
            <option v-if="underlying.ccy && !['EUR','USD','GBP','JPY','CHF','SGD'].includes(underlying.ccy)">{{ underlying.ccy }}</option>
            <option>EUR</option><option>USD</option><option>GBP</option>
            <option>JPY</option><option>CHF</option><option>SGD</option>
          </select>
          <p v-if="catalogInstrument(underlying.ticker)?.ccy && underlying.ccy !== catalogInstrument(underlying.ticker).ccy" class="text-xs text-amber-700">Surcharge ; référence {{ catalogInstrument(underlying.ticker).ccy }}.</p>
          </div>
        </div>
      </div>
      <div class="flex flex-col gap-1">
        <label class="label">Nominal</label>
        <input v-model="nominalRaw" @blur="formatNominal" @focus="unformatNominal"
               type="text" inputmode="numeric" class="input font-mono"
               placeholder="1 000 000" />
      </div>
      <div class="flex flex-col gap-1">
        <label class="label">Devise</label>
        <select v-model="form.currency" class="select">
          <option>EUR</option><option>USD</option><option>GBP</option>
          <option>JPY</option><option>CHF</option><option>SGD</option>
        </select>
      </div>
      <div class="flex flex-col gap-1">
        <label class="label">Maturité (années)</label>
        <input v-model.number="form.T" type="number" step="0.5" class="input" />
      </div>
      <div class="flex flex-col gap-1">
        <label class="label"
               title="Date de constatation du niveau initial du ou des sous-jacents. C'est là que démarre la diffusion Monte Carlo.">Date de strike *</label>
        <input v-model="form.strike_date" :readonly="scriptConstats.some(c => c.role === 'initial_fixing')" type="date" class="input"
               @change="resolveFormDate('strike_date')" />
        <select v-if="!scriptConstats.some(c => c.role === 'initial_fixing')" v-model="form.strike_date_convention" class="select py-1 text-[11px]"
                title="Ce que devient cette date si elle tombe un week-end ou un jour férié du calendrier de la devise."
                @change="resolveFormDate('strike_date')">
          <option value="none">Aucun ajustement</option>
          <option value="following">Jour ouvré suivant</option>
          <option value="modified_following">Suivant, sauf changement de mois</option>
          <option value="preceding">Jour ouvré précédent</option>
          <option value="modified_preceding">Précédent, sauf changement de mois</option>
        </select>
        <span v-if="dateNotices.strike_date" class="text-[10px] text-amber-500">{{ dateNotices.strike_date }}</span>
      </div>
      <div class="flex flex-col gap-1">
        <label class="label"
               title="Date d'échange du cash entre contreparties. Le prix coté est le montant qui bouge ce jour-là. Elle peut précéder la date de strike (forward start).">Date de valeur *</label>
        <input v-model="form.value_date" type="date" class="input"
               @change="resolveFormDate('value_date')" />
        <select v-model="form.value_date_convention" class="select py-1 text-[11px]"
                title="Ce que devient cette date si elle tombe un week-end ou un jour férié du calendrier de la devise."
                @change="resolveFormDate('value_date')">
          <option value="none">Aucun ajustement</option>
          <option value="following">Jour ouvré suivant</option>
          <option value="modified_following">Suivant, sauf changement de mois</option>
          <option value="preceding">Jour ouvré précédent</option>
          <option value="modified_preceding">Précédent, sauf changement de mois</option>
        </select>
        <span v-if="dateNotices.value_date" class="text-[10px] text-amber-500">{{ dateNotices.value_date }}</span>
      </div>
      <div class="flex flex-col gap-1">
        <label class="label">Date de maturité</label>
        <input :value="createMaturityDate" type="date" readonly
               class="input bg-slate-800/40 text-slate-500 cursor-not-allowed" />
      </div>
      <div class="flex flex-col gap-1">
        <label class="label"
               title="Échange final des flux de cash. Proposée à trois jours ouvrés après la dernière constatation — modifiable, c'est le term sheet qui tranche.">Date de paiement *</label>
        <input v-model="form.payment_date" type="date" class="input"
               @change="paymentDateSaisie = true; resolveFormDate('payment_date')" />
        <select v-model="form.payment_date_convention" class="select py-1 text-[11px]"
                title="Ce que devient cette date si elle tombe un week-end ou un jour férié du calendrier de la devise."
                @change="resolveFormDate('payment_date')">
          <option value="none">Aucun ajustement</option>
          <option value="following">Jour ouvré suivant</option>
          <option value="modified_following">Suivant, sauf changement de mois</option>
          <option value="preceding">Jour ouvré précédent</option>
          <option value="modified_preceding">Précédent, sauf changement de mois</option>
        </select>
        <span v-if="dateNotices.payment_date" class="text-[10px] text-amber-500">{{ dateNotices.payment_date }}</span>
      </div>
    </div>

    <!-- Termes du produit + calendrier(s) CONSTAT (dynamiques, extraits du script) -->
    <div v-if="parsedParams.length || scriptConstats.length" class="border-t border-slate-800 pt-3">
      <RfqParamsEditor :parsed-params="parsedParams" :param-overrides="paramOverrides"
                       :constats="scriptConstats" :constat-overrides="constatOverrides"
                       :currency="form.currency" />
    </div>

    <!-- Hypothèses de pricing (avancé, pour le calcul du prix modèle interne) -->
    <details class="border-t border-slate-800 pt-3">
      <summary class="label mb-0 cursor-pointer select-none">▸ Hypothèses de pricing (avancé)</summary>
      <div class="flex items-center gap-3 mt-2">
        <button type="button" class="btn-secondary text-xs px-3 py-1.5"
                :disabled="!createBasket[createActiveUnderlyingIdx]?.ticker?.trim() || createYfLoading"
                :title="createBasket[createActiveUnderlyingIdx]?.ticker?.trim()
                        ? `Vol réalisée 1 an et rendement du dividende de ${createBasket[createActiveUnderlyingIdx].ticker} (Yahoo Finance)`
                        : 'Renseignez un ticker de sous-jacent ci-dessus'"
                @click="loadCreateUnderlyingParams">
          📡 Charger {{ createBasket[createActiveUnderlyingIdx]?.ticker || 'le sous-jacent' }}
        </button>
        <span v-if="createYfStatus" class="text-[10px] text-slate-500">{{ createYfStatus }}</span>
      </div>
      <div class="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-2">
        <div class="flex flex-col gap-1">
          <label class="label">Date de pricing</label>
          <input v-model="form.pricing_date" type="date" class="input" />
        </div>
        <div class="flex flex-col gap-1">
          <label class="label">Taux sans risque (%)</label>
          <input v-model.number="advanced.r" type="number" step="0.1" class="input" />
        </div>
        <div class="flex flex-col gap-1">
          <label class="label">Modèle</label>
          <select v-model="advanced.model" class="select">
            <option value="constant">Constant (GBM)</option>
            <option value="heston">Heston</option>
            <option value="sabr">SABR</option>
            <option value="localvol">Dupire (Local Vol)</option>
            <option value="lsv">Local-Stochastic Vol</option>
          </select>
        </div>
        <div class="flex flex-col gap-1">
          <label class="label">Trajectoires (N)</label>
          <input v-model.number="advanced.N" type="number" step="1000" class="input" />
        </div>
      </div>

      <div v-if="createBasket[createActiveUnderlyingIdx]" class="mt-3 border-t border-slate-800 pt-3">
        <div class="label">Volatilité · {{ createBasket[createActiveUnderlyingIdx].ticker || 'sous-jacent' }}</div>
        <UnderlyingVolFields :au="createBasket[createActiveUnderlyingIdx]"
                             :model="advanced.model" :horizon="form.T" :rate="advanced.r" />
      </div>

      <div v-if="createBasket.length > 1" class="mt-3 overflow-x-auto">
        <div class="label mb-1">Corrélations du panier</div>
        <table class="text-[11px] border-collapse">
          <thead><tr><th class="p-1"></th><th v-for="u in createBasket" :key="u.ticker" class="p-1 font-mono">{{ u.ticker || '—' }}</th></tr></thead>
          <tbody>
            <tr v-for="(row, i) in createCorrMatrix" :key="i">
              <th class="p-1 text-left font-mono">{{ createBasket[i]?.ticker || '—' }}</th>
              <td v-for="(_, j) in row" :key="j" class="p-1">
                <input v-if="j > i" type="number" min="-1" max="1" step="0.05"
                       class="input w-20 text-center" :value="createCorrMatrix[i][j]"
                       @input="setCorrelation(createCorrMatrix, i, j, $event.target.value)" />
                <span v-else class="inline-block w-20 text-center text-slate-600">{{ i === j ? '1.00' : createCorrMatrix[i][j].toFixed(2) }}</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Les mêmes cartes que Marché & Paramètres, dans le MÊME ORDRE,
           sur l'état de l'AO. Elles acceptent leur courbe en prop et retombent sur
           le Pricer quand on ne leur en donne pas : une seule
           implémentation, deux écrans, aucun état partagé. -->
      <div class="flex flex-col gap-3 mt-3 pt-3 border-t border-slate-800">
        <DividendCurveCard :sous-jacents="ao.panier" :index-actif="createActiveUnderlyingIdx"
                           :horizon="form.T" />
        <YieldCurveCard :courbe="ao.yieldCurve" :taux-plat="advanced.r" />
        <FundingCurveCard :courbe="ao.fundingCurve" />
      </div>
    </details>
  </div>
</template>

<script setup>
// Extracted from RfqView.vue (P1-10, U3). The state stays in the
// view; this panel reads it through useRfqContext().
import DividendCurveCard from '../../components/DividendCurveCard.vue'
import FundingCurveCard from '../../components/FundingCurveCard.vue'
import RfqParamsEditor from '../../components/RfqParamsEditor.vue'
import UnderlyingVolFields from '../../components/UnderlyingVolFields.vue'
import YieldCurveCard from '../../components/YieldCurveCard.vue'
import { catalogInstrument, underlyingGroups } from '../../data/commonUnderlyings.js'
import { setCorrelation } from './rfqLabels.js'
import { useRfqContext } from './context.js'

const {
  addCreateUnderlying, advanced, ao, constatOverrides, createActiveUnderlyingIdx, createBasket,
  createCorrMatrix, createMaturityDate, createYfLoading, createYfStatus, dateNotices, form,
  formatNominal, loadCreateUnderlyingParams, nominalRaw, onUnderlyingSelect, paramOverrides,
  parsedParams, paymentDateSaisie, removeCreateUnderlying, resolveFormDate, scriptConstats,
  sourceProduct, unformatNominal,
} = useRfqContext()
</script>
