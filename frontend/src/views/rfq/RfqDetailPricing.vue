<template>
  <div class="card flex flex-col gap-3">
    <div class="flex items-center gap-4">
      <div class="stat-box flex-1">
        <div class="text-[10px] text-slate-500 uppercase tracking-wider mb-1">Prix modèle Structura</div>
        <div class="text-xl font-bold text-slate-100"><SensitiveValue>{{ fmtPrice(rfq.current.model_price) }}</SensitiveValue></div>
        <!-- Ligne toujours rendue : sans elle, la tuile gagnait un cran
             de hauteur au premier calcul et tout le bloc sautait. -->
        <div class="text-[10px] text-slate-600 mt-0.5">
          {{ rfq.current.model_price_at ? 'Calculé le ' + fmtDate(rfq.current.model_price_at) : 'Pas encore calculé' }}
        </div>
      </div>
      <!-- Les deux libellés partagent la même cellule de grille : le
           bouton se dimensionne sur le plus long et ne bouge plus en
           passant à « Calcul… ». Une largeur en dur serait à refaire à
           chaque changement de libellé ou de police. -->
      <button v-if="can(rfq.current, 'price')" class="btn-price-model grid shrink-0" :disabled="computing || !!rfq.current.booked_deal" @click="computeModelPrice">
        <span class="col-start-1 row-start-1" :class="computing ? 'invisible' : ''">Calculer prix modèle</span>
        <span class="col-start-1 row-start-1" :class="computing ? '' : 'invisible'">Calcul…</span>
      </button>
    </div>

    <details v-if="can(rfq.current, 'price')" class="border-t border-slate-800 pt-3">
      <summary class="label mb-0 cursor-pointer select-none">▸ Paramètres de pricing (modifiables)</summary>
      <SensitiveValue mode="input">
      <div class="mt-2 flex flex-col gap-3">
        <fieldset :disabled="!!rfq.current.quotes?.length">
          <RfqParamsEditor :parsed-params="detailParsedParams" :param-overrides="detailParamOverrides"
                           :constats="detailScriptConstats" :constat-overrides="detailConstatOverrides"
                           :currency="rfq.current.params?.currency || 'EUR'" />
        </fieldset>

        <!-- L'éditeur ci-dessus ne vivait qu'en mémoire : le calcul du
             prix n'envoie que les hypothèses de modèle, jamais les
             termes. Un échéancier modifié se perdait donc au premier
             rechargement de l'AO. Cette barre est le seul chemin qui
             les persiste. -->
        <div class="flex flex-wrap items-center gap-3 border-t border-slate-800 pt-3">
          <button type="button" class="btn-primary text-xs px-3 py-1.5 shrink-0"
                  :disabled="!detailTermsDirty || savingTerms"
                  title="Enregistre l'échéancier, les termes du produit et les dates sur l'AO. Refusé par le serveur si une cotation existe déjà — les termes contractuels sont alors figés."
                  @click="saveDetailTerms">
            💾 Enregistrer les termes
          </button>
          <span class="text-[11px]" :class="detailTermsDirty ? 'text-amber-500' : 'text-slate-600'">
            {{ detailTermsDirty
              ? 'Modifications non enregistrées — elles seront perdues sans cette sauvegarde.'
              : 'Termes enregistrés.' }}
          </span>
          <button type="button" class="text-[11px] underline text-slate-500 hover:text-slate-300 shrink-0"
                  title="Recharger les termes tels qu'ils sont enregistrés sur l'AO"
                  @click="refreshDetailParams">Recharger</button>
        </div>

        <div class="flex items-center gap-3 border-t border-slate-800 pt-3">
          <div v-if="detailBasket.length > 1" class="flex flex-wrap gap-1">
            <button v-for="(underlying, index) in detailBasket" :key="underlying.ticker || index"
                    type="button" class="btn-secondary text-xs px-2 py-1"
                    :class="detailActiveUnderlyingIdx === index ? 'border-blue-500 text-blue-300' : ''"
                    @click="detailActiveUnderlyingIdx = index">
              {{ underlying.ticker || underlying.name }}
            </button>
          </div>
          <button type="button" class="btn-secondary text-xs px-3 py-1.5"
                  :disabled="!underlyingSummary.ticker || detailYfLoading"
                  :title="underlyingSummary.ticker
                          ? `Vol réalisée 1 an et rendement du dividende de ${underlyingSummary.ticker} (Yahoo Finance)`
                          : 'Aucun ticker de sous-jacent sur cette RFQ'"
                  @click="loadDetailUnderlyingParams">
            📡 Charger les paramètres du sous-jacent
          </button>
          <span v-if="detailYfStatus" class="text-[10px] text-slate-500">{{ detailYfStatus }}</span>
        </div>
        <div class="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <div class="flex flex-col gap-1">
            <label class="label">Date de pricing</label>
            <input v-model="detailAdvanced.valuation_date" type="date" class="input" />
          </div>
          <div class="flex flex-col gap-1">
            <label class="label">Taux sans risque (%)</label>
            <input v-model.number="detailAdvanced.r" type="number" step="0.1" class="input" />
          </div>
          <div class="flex flex-col gap-1">
            <label class="label">Modèle</label>
            <select v-model="detailAdvanced.model" class="select">
              <option value="constant">Constant (GBM)</option>
              <option value="heston">Heston</option>
              <option value="sabr">SABR</option>
              <option value="localvol">Dupire (Local Vol)</option>
              <option value="lsv">Local-Stochastic Vol</option>
            </select>
          </div>
          <div class="flex flex-col gap-1">
            <label class="label">Trajectoires (N)</label>
            <input v-model.number="detailAdvanced.N" type="number" step="1000" class="input" />
          </div>
          <div class="flex flex-col gap-1">
            <label class="label">Date de strike</label>
            <input v-model="detailAdvanced.strike_date" type="date" class="input" :readonly="detailScriptConstats.some(c => c.role === 'initial_fixing')"
                   :disabled="!!rfq.current.quotes?.length" />
          </div>
          <div class="flex flex-col gap-1">
            <label class="label">Date de valeur</label>
            <input v-model="detailAdvanced.value_date" type="date" class="input"
                   :disabled="!!rfq.current.quotes?.length" />
          </div>
          <div class="flex flex-col gap-1">
            <label class="label">Date de maturité</label>
            <input :value="detailMaturityDate" type="date" readonly
                   class="input bg-slate-800/40 text-slate-500 cursor-not-allowed" />
          </div>
          <div class="flex flex-col gap-1">
            <label class="label"
                   title="Date d'échange final des flux de cash — celle du term sheet. C'est elle qui actualise le remboursement, pas la maturité.">Date de paiement ⓘ</label>
            <input v-model="detailAdvanced.payment_date" type="date" class="input"
                   :disabled="!!rfq.current.quotes?.length" />
          </div>
        </div>
        <div v-if="detailBasket[detailActiveUnderlyingIdx]" class="mt-3 border-t border-slate-800 pt-3">
          <div class="label">Volatilité · {{ detailBasket[detailActiveUnderlyingIdx].ticker || 'sous-jacent' }}</div>
          <UnderlyingVolFields :au="detailBasket[detailActiveUnderlyingIdx]"
                               :model="detailAdvanced.model" :horizon="detailHorizon" :rate="detailAdvanced.r" />
        </div>

        <div v-if="detailBasket.length > 1" class="mt-3 overflow-x-auto border-t border-slate-800 pt-3">
          <div class="label mb-1">Corrélations du panier</div>
          <table class="text-[11px] border-collapse">
            <thead><tr><th class="p-1"></th><th v-for="u in detailBasket" :key="u.ticker" class="p-1 font-mono">{{ u.ticker || '—' }}</th></tr></thead>
            <tbody>
              <tr v-for="(row, i) in detailCorrMatrix" :key="i">
                <th class="p-1 text-left font-mono">{{ detailBasket[i]?.ticker || '—' }}</th>
                <td v-for="(_, j) in row" :key="j" class="p-1">
                  <input v-if="j > i" type="number" min="-1" max="1" step="0.05"
                         class="input w-20 text-center" :value="detailCorrMatrix[i][j]"
                         @input="setCorrelation(detailCorrMatrix, i, j, $event.target.value)" />
                  <span v-else class="inline-block w-20 text-center text-slate-600">{{ i === j ? '1.00' : detailCorrMatrix[i][j].toFixed(2) }}</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <!-- Les mêmes cartes qu'à la création, dans l'ordre du Pricer,
             sur l'état du détail. Ce sont des hypothèses de MODÈLE : elles
             restent ajustables cotations en main, contrairement
             aux dates ci-dessus qui, elles, sont contractuelles. -->
        <div class="flex flex-col gap-3 mt-3 pt-3 border-t border-slate-800">
          <DividendCurveCard :sous-jacents="aoDetail.panier" :index-actif="detailActiveUnderlyingIdx"
                             :horizon="detailHorizon" />
          <YieldCurveCard :courbe="aoDetail.yieldCurve" :taux-plat="detailAdvanced.r" />
          <FundingCurveCard :courbe="aoDetail.fundingCurve" />
        </div>
      </div>
      </SensitiveValue>
    </details>
  </div>
</template>

<script setup>
// Extracted from RfqView.vue (P1-10, U3). The state stays in the
// view; this panel reads it through useRfqContext().
import DividendCurveCard from '../../components/DividendCurveCard.vue'
import FundingCurveCard from '../../components/FundingCurveCard.vue'
import RfqParamsEditor from '../../components/RfqParamsEditor.vue'
import SensitiveValue from '../../components/SensitiveValue.vue'
import UnderlyingVolFields from '../../components/UnderlyingVolFields.vue'
import YieldCurveCard from '../../components/YieldCurveCard.vue'
import { can, setCorrelation } from './rfqLabels.js'
import { useRfqContext } from './context.js'

const {
  aoDetail, computeModelPrice, computing, detailActiveUnderlyingIdx, detailAdvanced, detailBasket,
  detailConstatOverrides, detailCorrMatrix, detailHorizon, detailMaturityDate, detailParamOverrides,
  detailParsedParams, detailScriptConstats, detailTermsDirty, detailYfLoading, detailYfStatus,
  fmtDate, fmtPrice, loadDetailUnderlyingParams, refreshDetailParams, rfq, saveDetailTerms,
  savingTerms, underlyingSummary,
} = useRfqContext()
</script>
