<template>
  <div class="flex flex-col gap-6 p-1">

    <!-- Pas de résultat -->
    <div v-if="!store.result" class="text-center py-12 text-slate-600">
      <p class="text-sm">Lancez un pricing (▶ Pricer) pour calculer le KID.</p>
    </div>

    <template v-else>

      <!-- ── Paramètres KID ─────────────────────────────────── -->
      <div class="card">
        <h3 class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3">Paramètres KID</h3>
        <!-- items-end: a label that wraps onto two lines must not push its
             input below its neighbours' — the inputs share the row's baseline. -->
        <div class="grid grid-cols-2 sm:grid-cols-3 xl:grid-cols-5 gap-3 items-end">
          <div>
            <label class="label">Simulation
              <HelpTip text="Bootstrap historique (annexe II, points 19 à 22) : cinq ans de cours quotidiens de chaque sous-jacent, une même date tirée pour tous, 10 000 simulations au moins. C'est la méthode qu'impose la Catégorie 3. La simulation risque-neutre du modèle de pricing reste disponible pour un produit sans historique exploitable, et le KID l'indique alors comme indicatif." />
            </label>
            <select v-model="params.simulation" class="select text-xs">
              <option value="historical_bootstrap">Bootstrap historique (PRIIPs)</option>
              <option value="risk_neutral_model">Modèle risque-neutre (indicatif)</option>
            </select>
          </div>
          <div>
            <label class="label">Émetteur (risque de crédit)
              <HelpTip text="Annexe II, partie 2 : la note de l'émetteur donne un rang de qualité de crédit (AAA = 0 … CCC = 6), ajusté à la maturité du produit (jusqu'à 1 an, de 1 à 12 ans, au-delà), puis converti en classe CRM. Sans note, le rang par défaut est 3 pour un établissement de crédit ou un assureur régulé, 5 sinon. La classe CRM se croise ensuite avec le MRM dans la table du point 52." />
            </label>
            <select v-model="params.issuer" class="select text-xs">
              <option v-for="r in ['AAA', 'AA', 'A', 'BBB', 'BB', 'B', 'CCC']" :key="r" :value="r">Note {{ r }}</option>
              <option value="unrated_regulated">Non noté — établissement régulé</option>
              <option value="unrated_other">Non noté — autre</option>
              <option value="manual">Classe CRM saisie</option>
            </select>
          </div>
          <div v-if="params.issuer === 'manual'">
            <label class="label">CRM (saisi)
              <HelpTip text="Classe de risque de crédit saisie directement, de 1 à 6, quand la note de l'émetteur ne s'applique pas (garantie, collatéral : annexe II, points 46 à 51)." />
            </label>
            <select v-model.number="params.crm" class="select text-xs">
              <option v-for="c in 6" :key="c" :value="c">{{ c }}</option>
            </select>
          </div>
          <div>
            <label class="label">Prix d'émission / prime
              <HelpTip text="Prix payé en % du nominal. Une note émise au pair reste à 100. Pour un produit non pair, par exemple un call acheté 12, saisissez 12 : la VaR et le rendement se mesurent alors contre la prime effectivement payée." />
            </label>
            <input v-model.number="params.initial_price_pct" type="number" step="0.01" min="0.01" max="1000" class="input text-xs" />
          </div>
          <div>
            <label class="label">Frais d'entrée (%)
              <HelpTip text="Frais ponctuel prélevé à la souscription, en % du montant investi. Réduit le capital réellement investi (10 000€ × (1 − frais)) avant application des scénarios de performance." />
            </label>
            <input v-model.number="params.cost_entry" type="number" step="0.1" min="0" max="10" class="input text-xs" />
          </div>
          <div>
            <label class="label">Frais de sortie (%)
              <HelpTip text="Frais ponctuel prélevé à la sortie (vente ou remboursement), appliqué au montant final de chaque scénario." />
            </label>
            <input v-model.number="params.cost_exit" type="number" step="0.1" min="0" max="10" class="input text-xs" />
          </div>
          <div>
            <label class="label">Frais courants (% / an)
              <HelpTip text="Frais récurrent annuel (gestion), composé sur la durée de détention de chaque horizon affiché — plus l'horizon est long, plus son impact cumulé pèse sur le montant final." />
            </label>
            <input v-model.number="params.cost_ongoing" type="number" step="0.01" min="0" max="5" class="input text-xs" />
          </div>
        </div>
        <div class="flex items-center gap-3 mt-3">
          <button class="btn-primary text-xs px-4 py-2" @click="compute" :disabled="loading">
            <span v-if="loading"
              class="w-3 h-3 border-2 border-white border-t-transparent rounded-full animate-spin inline-block mr-1.5"></span>
            {{ loading ? 'Calcul KID…' : '⚖ Calculer le KID PRIIPs' }}
          </button>
          <span v-if="error" class="text-xs text-red-400">⚠ {{ error }}</span>
        </div>
      </div>

      <!-- ── SRI ───────────────────────────────────────────── -->
      <div v-if="kid" class="mb-4 rounded border border-amber-500/40 bg-amber-500/10 px-3 py-2
                             text-[11px] leading-relaxed text-amber-200/90">
        <span class="font-bold">Document indicatif — méthodologie non conforme PRIIPs.</span>
        La méthode de Catégorie 3 du règlement délégué 2017/653 est implémentée : bootstrap historique,
        VaR à 97,5 % et VEV, table SRI, CRM tiré de la note, scénarios, tension sous volatilité stressée,
        périodes intermédiaires et coûts. Restent hors champ : la correction quanto, les sous-jacents de
        type courbe, la composition fine des coûts (transaction, accessoires), et toute validation
        indépendante. À usage d'analyse interne — ne pas diffuser comme KID réglementaire.
      </div>
      <div v-if="kid" class="card">
        <h3 class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-4">
          Indicateur Synthétique de Risque (SRI)
          <HelpTip width="w-72" text="Échelle réglementaire PRIIPs de 1 (risque le plus faible) à 7 (le plus élevé), combinant le risque de marché (MRM, dérivé de la VEV du produit) et le risque de crédit de l'émetteur (CRM) via une table de correspondance fixée par le règlement." />
        </h3>
        <div class="flex items-center gap-6">
          <!-- Gauge 1-7 -->
          <div class="flex gap-1">
            <div v-for="n in 7" :key="n"
              class="flex flex-col items-center gap-1">
              <div class="w-9 h-9 rounded flex items-center justify-center text-sm font-black transition-all"
                :class="n === kid.sri
                  ? 'scale-110 ring-2 ring-white text-white ' + sriColorBg(n)
                  : 'opacity-30 text-slate-500 ' + sriColorBg(n)">
                {{ n }}
              </div>
              <div class="text-[8px] text-slate-600 text-center leading-tight hidden sm:block" style="width:36px">
                {{ sriLabel(n) }}
              </div>
            </div>
          </div>

          <!-- Détails -->
          <div class="flex flex-col gap-1.5">
            <div class="flex items-center gap-2 text-xs">
              <span class="text-slate-500 w-36">Risque marché (MRM)
                <HelpTip text="Market Risk Measure, 1 à 7, dérivé directement de la VEV (voir ci-dessous) via des seuils fixés par le règlement PRIIPs." />
              </span>
              <span class="font-mono font-bold text-slate-200">{{ kid.mrm }} / 7</span>
            </div>
            <div class="flex items-center gap-2 text-xs">
              <span class="text-slate-500 w-36">Risque crédit (CRM)</span>
              <span class="font-mono font-bold text-slate-200">{{ kid.crm }} / 6</span>
              <span v-if="kid.credit_risk" class="text-[10px] text-slate-500">{{ kid.credit_risk.basis }}</span>
            </div>
            <div v-if="kid.simulation" class="flex items-center gap-2 text-xs">
              <span class="text-slate-500 w-36">Simulation
                <HelpTip text="Méthode et données qui ont produit la distribution : période de l'historique, nombre de séances communes à tous les sous-jacents et nombre de simulations. Le bootstrap tire chaque jour simulé parmi ces séances." />
              </span>
              <span v-if="bootstrapped" class="font-mono text-[11px] text-slate-300">
                bootstrap {{ kid.simulation.first_date }} → {{ kid.simulation.last_date }},
                {{ formatInt(kid.simulation.observations) }} séances, {{ formatInt(kid.simulation.simulations) }} simulations
              </span>
              <span v-else class="font-mono text-[11px] text-amber-400">
                modèle risque-neutre ({{ kid.simulation.model }}), {{ formatInt(kid.simulation.simulations) }} trajectoires — indicatif
              </span>
            </div>
            <div class="flex items-center gap-2 text-xs">
              <span class="text-slate-500 w-36">VEV (équiv. vol)
                <HelpTip text="VaR-equivalent volatility (annexe II, point 17) : VEV = (√(3,842 − 2·ln VaR) − 1,96) / √T. La VaR est la valeur du produit à 97,5 % de confiance, actualisée au taux sans risque ; T est la durée recommandée, ou la date de rappel du scénario retenu s'il est rappelé avant. La classe MRM se lit ensuite dans la table du point 2." />
              </span>
              <span v-if="kid.vev != null" class="font-mono font-bold text-slate-200">{{ formatPercent(kid.vev, 1) }}</span>
              <span v-else class="font-mono font-bold text-red-400">n/d
                <HelpTip text="Au moins 2,5 % des scénarios perdent la totalité du capital : la VaR à 97,5 % est nulle et la VEV, qui passe par son logarithme, n'a pas de valeur finie. Le risque marché est classé au maximum (MRM 7)." />
              </span>
            </div>
            <div v-if="kid.var_975 != null" class="flex items-center gap-2 text-xs">
              <span class="text-slate-500 w-36">VaR 97,5 %
                <HelpTip text="Valeur du produit au 2,5ᵉ percentile de la distribution simulée, actualisée au taux sans risque, pour 1 investi (annexe II, point 16). C'est le chiffre dont la VEV est tirée ; la durée indiquée est celle de ce scénario, sa date de rappel s'il est rappelé avant la durée recommandée." />
              </span>
              <span class="font-mono font-bold text-slate-200">{{ formatPercent(kid.var_975 * 100, 1) }}</span>
              <span class="font-mono text-[10px] text-slate-500">sur {{ formatNumber(kid.var_years, 2) }} an(s)</span>
            </div>
            <div class="flex items-center gap-2 text-xs">
              <span class="text-slate-500 w-36">Durée recommandée
                <HelpTip text="Recommended Holding Period (T_rhp) — fixée ici à la maturité du produit. Toute la lecture du SRI et des scénarios de performance suppose que vous conservez le produit jusque-là ; une sortie anticipée expose à un profil de risque différent, non capturé par ces chiffres." />
              </span>
              <span class="font-mono font-bold text-slate-200">{{ formatNumber(kid.T_rhp, 1) }} ans</span>
            </div>
          </div>
        </div>

        <p class="text-[10px] text-slate-600 mt-4 pt-3 border-t border-slate-800">
          L'indicateur de risque part de l'hypothèse que vous conservez le produit {{ formatNumber(kid.T_rhp, 1) }} an(s).
          Si vous le vendez avant cette date, le risque réel peut être très différent.
          PRIIPs Règlement (UE) 1286/2014 — calcul interne MC, non officiel.
        </p>
      </div>

      <!-- ── Scénarios de performance ───────────────────────── -->
      <div v-if="kid" class="card">
        <div class="flex items-center justify-between mb-4">
          <h3 class="text-xs font-bold text-slate-400 uppercase tracking-wider">
            Scénarios de performance
          </h3>
          <span class="text-[10px] text-slate-600 italic">Pour un investissement de 10 000 €</span>
        </div>

        <div class="overflow-x-auto">
          <table class="w-full text-xs border-collapse">
            <thead>
              <tr class="border-b border-slate-700">
                <th class="text-left text-slate-500 font-medium pb-2 pr-4">Scénario</th>
                <th v-for="h in kid.horizons" :key="h.T"
                  class="text-right text-slate-500 font-medium pb-2 px-3 whitespace-nowrap">
                  {{ h.T >= kid.T_rhp ? 'Maturité' : formatNumber(h.T, 0) + ' an' + (h.T > 1 ? 's' : '') }}
                  <span class="block font-normal text-slate-600">{{ formatNumber(h.T, 2) }}Y</span>
                </th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="sc in scenarios" :key="sc.key"
                class="border-b border-slate-800/60 hover:bg-slate-800/20">
                <td class="py-3 pr-4">
                  <div class="flex items-center gap-2">
                    <div class="w-2 h-2 rounded-full shrink-0" :class="sc.dot"></div>
                    <div>
                      <div :class="sc.labelClass" class="font-semibold">{{ sc.label }}</div>
                      <div class="text-[10px] text-slate-600">{{ sc.sub }}</div>
                    </div>
                  </div>
                </td>
                <td v-for="h in kid.horizons" :key="h.T" class="py-3 px-3 text-right">
                  <div class="font-mono font-bold text-sm"
                    :class="h[sc.key].amount >= 10000 ? 'text-slate-200' : 'text-red-400'">
                    {{ fmtAmount(h[sc.key].amount) }} €
                  </div>
                  <div v-if="h[sc.key].ann_return != null" class="font-mono text-[10px] mt-0.5"
                    :class="h[sc.key].ann_return >= 0 ? 'text-emerald-400' : 'text-red-400'">
                    {{ h[sc.key].ann_return >= 0 ? '+' : '' }}{{ formatPercent(h[sc.key].ann_return, 2) }}{{ h[sc.key].return_annualised === false ? ' sur la période' : ' / an' }}
                  </div>
                  <div v-else class="text-[10px] mt-0.5 text-amber-400">
                    Rendement non calculable
                  </div>
                  <!-- Durée sur laquelle CE scénario a été annualisé. Un produit
                       rappelé par anticipation a vécu moins longtemps que l'en-tête
                       de colonne : sans cette mention le lecteur croit à une erreur. -->
                  <div v-if="sc.key === 'stress' && h.stress.capped_at_unfavourable"
                    class="text-[10px] text-slate-500 mt-0.5">ramené au défavorable</div>
                  <div v-else-if="sc.key === 'stress' && h.stress.percentile"
                    class="text-[10px] text-slate-500 mt-0.5">P{{ h.stress.percentile }} sous volatilité stressée</div>
                  <div v-if="h[sc.key].life && Math.abs(h[sc.key].life - h.T) > 0.01"
                    class="font-mono text-[10px] text-amber-500/80 mt-0.5">
                    rappel à {{ formatNumber(h[sc.key].life, 2) }} an{{ h[sc.key].life > 1 ? 's' : '' }}
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <p class="text-[10px] text-slate-600 mt-3 pt-3 border-t border-slate-800">
          Les scénarios défavorable / modéré / favorable correspondent aux percentiles P10 / P50 / P90 de la
          distribution simulée (annexe IV, points 21 à 23) ; en bootstrap, ils suivent le rendement historique
          observé (point 25). Le scénario stress rejoue le bootstrap sous volatilité stressée et retient le P1 à un an,
          le P5 au-delà, sans jamais dépasser le défavorable (points 20, 26 et 27). Le montant est la somme des flux reçus, coupons compris, sans réinvestissement, nette
          de frais et arrondie à 10 € (point 42). Le rendement est (montant / investissement)^(1/T) − 1, T étant la
          durée réelle du scénario — sa date de rappel s'il est rappelé (point 44) ; jusqu'à un an il n'est pas
          annualisé (point 45). Périodes intermédiaires : un an pour une durée recommandée de 1 à 10 ans, plus la
          mi-durée au-delà (points 32 à 34).
        </p>
      </div>

      <!-- ── Coûts ──────────────────────────────────────────── -->
      <div v-if="kid" class="card">
        <h3 class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3">Composition des coûts</h3>
        <div class="grid grid-cols-3 gap-4 text-xs">
          <div class="bg-slate-800/40 rounded-lg px-4 py-3 text-center">
            <div class="text-slate-500 mb-1">Frais d'entrée</div>
            <div class="font-mono font-bold text-slate-200 text-sm">{{ formatPercent(kid.costs.entry, 2) }}</div>
            <div class="text-slate-600 text-[10px] mt-1">{{ fmtAmount(10000 * kid.costs.entry / 100) }} € / 10 k€</div>
          </div>
          <div class="bg-slate-800/40 rounded-lg px-4 py-3 text-center">
            <div class="text-slate-500 mb-1">Frais courants / an</div>
            <div class="font-mono font-bold text-slate-200 text-sm">{{ formatPercent(kid.costs.ongoing, 2) }}</div>
            <div class="text-slate-600 text-[10px] mt-1">{{ fmtAmount(10000 * kid.costs.ongoing / 100) }} € / 10 k€</div>
          </div>
          <div class="bg-slate-800/40 rounded-lg px-4 py-3 text-center">
            <div class="text-slate-500 mb-1">Frais de sortie</div>
            <div class="font-mono font-bold text-slate-200 text-sm">{{ formatPercent(kid.costs.exit, 2) }}</div>
            <div class="text-slate-600 text-[10px] mt-1">{{ fmtAmount(10000 * kid.costs.exit / 100) }} € / 10 k€</div>
          </div>
        </div>
        <h4 class="text-[11px] font-semibold text-slate-400 mt-4 mb-2">Coûts au fil du temps
          <HelpTip text="Annexe VII, tableau 1, sur le scénario modéré : coûts totaux (écart entre le montant sans coûts et avec coûts) et incidence annuelle des coûts (écart entre les deux rendements, point 44). Euros à l'unité, pourcentages à une décimale (annexe VI, point 78)." />
        </h4>
        <table class="w-full text-xs">
          <thead>
            <tr class="text-slate-500">
              <th class="text-left font-medium pb-1">Sortie après</th>
              <th class="text-right font-medium pb-1">Coûts totaux</th>
              <th class="text-right font-medium pb-1">Incidence annuelle</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="h in kid.horizons" :key="'c' + h.T" class="border-t border-slate-800/60">
              <td class="py-1.5 text-slate-300">{{ formatNumber(h.T, 2) }} an(s)</td>
              <td class="py-1.5 text-right font-mono text-slate-200">{{ fmtAmount(h.costs_over_time?.total_costs ?? 0) }} €</td>
              <td class="py-1.5 text-right font-mono text-amber-400">
                {{ formatPercent(h.costs_over_time?.annual_cost_impact_pct ?? 0, 1) }}{{ h.costs_over_time?.annualised === false ? ' sur la période' : ' / an' }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- ── Boutons sauvegarde / export ──────────────────────── -->
      <div v-if="kid" class="flex gap-3">
        <button class="btn-primary text-xs px-4 py-2 flex-1" @click="saveKid" :disabled="saving">
          <span v-if="saving" class="w-3 h-3 border-2 border-white border-t-transparent rounded-full animate-spin inline-block mr-1.5"></span>
          {{ saving ? 'Sauvegarde…' : (saveConfirm ? '✓ Sauvegardé' : '💾 Sauvegarder') }}
        </button>
        <button class="btn-secondary text-xs px-4 py-2 flex-1" @click="printKid">
          🖨️ Imprimer / Exporter PDF
        </button>
      </div>
      <div v-if="saveError" class="text-xs text-red-400">⚠ {{ saveError }}</div>

    </template>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { usePricingStore } from '../stores/pricing.js'
import { apiFetch } from '../utils/api.js'
import { formatInt, formatNumber, formatPercent } from '../utils/format.js'
import HelpTip from './HelpTip.vue'

const store = usePricingStore()

const loading = ref(false)
const error   = ref('')
const kid     = computed({ get: () => store.kid, set: (v) => { store.kid = v } })

const saving      = ref(false)
const saveError   = ref('')
const saveConfirm = ref(false)

const params = ref({
  simulation: 'historical_bootstrap',
  issuer: 'BBB',
  crm: 3,
  initial_price_pct: 100,
  cost_entry: 0,
  cost_exit: 0,
  cost_ongoing: 0,
})

// ── Scenarios metadata ────────────────────────────────────
const scenarios = [
  { key: 'stress',      label: 'Stress',      sub: 'Percentile extrême', dot: 'bg-red-600', labelClass: 'text-red-400' },
  { key: 'defavorable', label: 'Défavorable', sub: 'Percentile 10%', dot: 'bg-orange-500', labelClass: 'text-orange-400' },
  { key: 'modere',      label: 'Modéré',      sub: 'Percentile 50%', dot: 'bg-slate-400',  labelClass: 'text-slate-300' },
  { key: 'favorable',   label: 'Favorable',   sub: 'Percentile 90%', dot: 'bg-emerald-500',labelClass: 'text-emerald-400' },
]

// ── SRI helpers ──────────────────────────────────────────
function sriColorBg(n) {
  const map = {
    1: 'bg-emerald-700', 2: 'bg-green-600', 3: 'bg-yellow-600',
    4: 'bg-amber-500',   5: 'bg-orange-600', 6: 'bg-red-600', 7: 'bg-red-800',
  }
  return map[n] || 'bg-slate-700'
}

function sriLabel(n) {
  const map = { 1: 'Très faible', 2: 'Faible', 3: 'Moyen-faible', 4: 'Moyen', 5: 'Moyen-élevé', 6: 'Élevé', 7: 'Très élevé' }
  return map[n] || ''
}

// ── Formatting ───────────────────────────────────────────
const fmtAmount = formatInt


// Annex II, Part 2: the issuer's rating drives the CRM unless it is entered.
function creditInput() {
  const issuer = params.value.issuer
  if (issuer === 'manual') return { crm: params.value.crm }
  if (issuer === 'unrated_regulated') return { issuer_unrated_regulated: true }
  if (issuer === 'unrated_other') return { issuer_unrated_regulated: false }
  return { issuer_rating: issuer }
}

const bootstrapped = computed(() => kid.value?.simulation?.method === 'historical_bootstrap')

// ── Compute KID ──────────────────────────────────────────
async function compute() {
  if (!store.result) return
  // The KID describes the validated script, never a text being typed.
  if (!(await store.ensureScriptValidated())) {
    error.value = 'Le script ne valide pas : corrigez-le dans l’onglet Script avant le KID.'
    return
  }
  loading.value = true
  error.value = ''
  kid.value = null

  try {
    const res = await apiFetch('/api/kid/compute', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        ...store.pricingBody(),
        product_id: store.currentProduct?.product_id || null,
        product_terms_version: store.currentProduct?.terms_version || null,
        simulation: params.value.simulation,
        ...creditInput(),
        initial_price_pct: params.value.initial_price_pct,
        cost_entry: params.value.cost_entry,
        cost_exit: params.value.cost_exit,
        cost_ongoing: params.value.cost_ongoing,
      }),
    })
    if (!res.ok) {
      const text = await res.text()
      try { const err = JSON.parse(text); throw new Error(err.detail || 'Erreur KID') }
      catch { throw new Error(`Erreur ${res.status}: ${text.slice(0, 300)}`) }
    }
    kid.value = await res.json()
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

// ── Actions ──────────────────────────────────────────────
function printKid() {
  window.print()
}

// Sauvegarde append-only — rattachée à la fiche Indicatif (créée à la
// volée au premier enregistrement, réutilisée ensuite pour ce pricing).
async function saveKid() {
  if (!kid.value) return
  saving.value = true
  saveError.value = ''
  try {
    const productId = store.currentProduct?.product_id || null
    const indicativeId = productId ? null : await store.ensureIndicative()
    const res = await apiFetch('/api/kid/save', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        indicative_id: indicativeId,
        product_id: productId,
        product_terms_version: store.currentProduct?.terms_version || null,
        product_title: store.productTitle,
        sri: kid.value.sri, mrm: kid.value.mrm, crm: kid.value.crm,
        vev: kid.value.vev, T_rhp: kid.value.T_rhp,
        horizons: kid.value.horizons, costs: kid.value.costs,
        calculation_receipt: kid.value.calculation_receipt,
      }),
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      throw new Error(err.detail || `Erreur ${res.status}`)
    }
    saveConfirm.value = true
    setTimeout(() => { saveConfirm.value = false }, 2000)
  } catch (e) {
    saveError.value = e.message || 'Erreur de sauvegarde'
  } finally {
    saving.value = false
  }
}
</script>
