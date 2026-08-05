<template>
  <div class="flex flex-col gap-5">

    <!-- ── Yahoo Finance loader ──────────────────────────────────── -->
    <div class="card">
      <div class="flex items-center gap-3 mb-3 flex-wrap">
        <h2 class="text-xs font-bold text-slate-400 uppercase tracking-wider mr-auto">Données Yahoo Finance</h2>
        <button class="btn-secondary text-xs px-3" :disabled="store.loading" @click="store.loadYfAll()">
          📡 Charger vols &amp; corr.
        </button>
      </div>
      <div v-if="store.yfStatus" class="text-xs mt-1 leading-relaxed"
           :class="store.yfStatus.startsWith('⚠') ? 'text-amber-400' : 'text-green-400'">
        <SensitiveValue placeholder="Données chargées">{{ store.yfStatus }}</SensitiveValue>
      </div>
      <div v-else class="text-xs text-slate-600 italic">
        Renseignez les tickers puis cliquez "Charger" pour auto-remplir σ, q et la corrélation.
      </div>
    </div>

    <!-- ── Paramètres globaux ─────────────────────────────────────── -->
    <div class="card">
      <h2 class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-4">Paramètres Monte Carlo</h2>
      <div class="grid grid-cols-2 sm:grid-cols-3 gap-3">

        <!-- Contexte marché -->
        <div class="col-span-2 sm:col-span-3 text-[10px] font-semibold text-slate-600 uppercase tracking-wider -mb-1">
          Contexte marché
        </div>
        <div>
          <label class="label">Devise deal
            <HelpTip text="Éditable dans l'onglet Deal (carte Identité) — affichée ici en lecture seule pour contexte." />
          </label>
          <input :value="store.globalParams.deal_ccy" type="text"
            class="input bg-slate-800/40 text-slate-500 cursor-not-allowed" readonly />
        </div>
        <div>
          <label class="label">Taux sans risque (%)
            <HelpTip text="Taux utilisé pour actualiser les flux futurs (valeur présente) et comme drift risque-neutre des trajectoires simulées. Un taux constant unique ici, sauf si vous activez une courbe de taux plus bas." />
          </label>
          <SensitiveValue mode="input">
            <input v-model.number="store.globalParams.r" type="number" step="0.1" class="input" />
          </SensitiveValue>
        </div>
        <div>
          <label class="label">Maturité (Y)
            <HelpTip v-if="store.scriptConstats.length > 0" text="Le script utilise CONSTAT — la maturité réelle est dictée par le calendrier (la date la plus tardive parmi les événements résolus, éditable dans l'onglet Deal), pas par ce champ." />
            <HelpTip v-else text="Horizon de simulation en années. Si le script a des dates AT qui dépassent cette valeur, le pricer étend automatiquement l'horizon effectif (voir t_max_effective dans les résultats) — ce champ est un minimum, pas un plafond strict." />
          </label>
          <div v-if="store.scriptConstats.length > 0"
               class="input bg-slate-800/40 text-slate-500 cursor-not-allowed flex items-center justify-between">
            <span>Calendrier (CONSTAT)</span>
            <span v-if="store.result?.t_max_effective" class="font-mono text-slate-400">
              {{ formatNumber(store.result.t_max_effective, 2) }} Y
            </span>
          </div>
          <input v-else v-model.number="store.globalParams.T" type="number" step="0.25" class="input" />
        </div>

        <!-- Modèle -->
        <div class="col-span-2 sm:col-span-3 text-[10px] font-semibold text-slate-600 uppercase tracking-wider -mb-1 mt-1">
          Modèle
        </div>
        <div>
          <label class="label">Modèle vol
            <HelpTip width="w-72" text="Constant (GBM) : volatilité fixe, le plus rapide, suffisant pour la plupart des produits. Heston/SABR : volatilité stochastique avec smile, à utiliser si le produit est sensible au smile (barrières proches de la monnaie, options digitales). Local Vol (Dupire) : calibré sur un skew/convexité paramétriques, réconcilie exactement les prix vanille au marché mais avec une dynamique de skew forward peu réaliste. Local-Stochastic Vol : combine les deux — calibré comme Local Vol, dynamique de skew forward réaliste comme Heston. Recommandé pour les barrières/autocalls, plus lent à calculer." />
          </label>
          <select v-model="store.globalParams.model" class="select">
            <option value="constant">Constant (GBM)</option>
            <option value="heston">Heston QE</option>
            <option value="sabr">SABR (Hagan)</option>
            <option value="localvol">Local Vol (Dupire)</option>
            <option value="lsv">Local-Stochastic Vol</option>
          </select>
        </div>
        <div>
          <label class="label">Modèle de taux
            <HelpTip width="w-72" text="Déterministe : taux constant, pas de risque de taux dans le pricing (rho sera nul). Stochastique ABM/Hull-White : simule un taux court aléatoire — nécessaire si le produit a une sensibilité réelle aux taux (durée longue, flux différés) ou si vous voulez calculer un rho non trivial." />
          </label>
          <select v-model="store.globalParams.rateModel" class="select">
            <option value="deterministic">Déterministe (r constant)</option>
            <option value="abm">Stochastique ABM (corrélé actions)</option>
            <option value="hull_white">Hull-White (mean-reverting)</option>
          </select>
        </div>
        <template v-if="store.globalParams.rateModel !== 'deterministic'">
          <div>
            <label class="label">σ taux (%/an)
              <HelpTip text="Vol du facteur de taux stochastique, partagé par tous les sous-jacents. La corrélation taux-spot par actif se règle via ρ(r,S) sur chaque sous-jacent." />
            </label>
            <SensitiveValue mode="input">
              <input v-model.number="store.globalParams.sigma_r" type="number" step="0.1" min="0" class="input" />
            </SensitiveValue>
          </div>
          <div v-if="store.globalParams.rateModel === 'hull_white'">
            <label class="label">a (retour à la moyenne)
              <HelpTip text="Vitesse de retour à la moyenne du taux court (Hull-White). Plus a est grand, plus le taux revient vite vers la courbe forward. Demi-vie ≈ ln(2)/a." />
            </label>
            <SensitiveValue mode="input">
              <input v-model.number="store.globalParams.a_r" type="number" step="0.05" min="0" class="input" />
            </SensitiveValue>
          </div>
        </template>

        <!-- Mécanique moteur -->
        <div class="col-span-2 sm:col-span-3 text-[10px] font-semibold text-slate-600 uppercase tracking-wider -mb-1 mt-1">
          Mécanique moteur
        </div>
        <div>
          <label class="label">N simulations
            <HelpTip text="Nombre de trajectoires Monte Carlo. Plus N est grand, plus l'intervalle de confiance du prix (IC95%) est étroit, mais le temps de calcul croît linéairement — 20 000 est un bon compromis pour explorer, montez à 50-100k pour un prix final à figer." />
          </label>
          <select v-model.number="store.globalParams.N" class="select">
            <option :value="5000">5 000</option>
            <option :value="10000">10 000</option>
            <option :value="20000">20 000</option>
            <option :value="50000">50 000</option>
            <option :value="100000">100 000</option>
          </select>
        </div>
        <div>
          <label class="label">Seed
            <HelpTip text="Graine du générateur aléatoire — fixe le tirage des trajectoires. Deux runs avec le même seed et les mêmes paramètres donnent exactement le même prix (reproductible pour du débogage ou une comparaison A/B), un seed différent donne un résultat légèrement différent (bruit Monte Carlo)." />
          </label>
          <SensitiveValue mode="input">
            <input v-model.number="store.globalParams.seed" type="number" step="1" class="input" />
          </SensitiveValue>
        </div>
        <div>
          <label class="label">Monitoring barrières
            <HelpTip width="w-72" text="Hebdomadaire : les extrema (WOF_MIN, S_MIN, BOF_MAX) sont observés aux pas de la grille MC (52/an) — une barrière contractuellement continue ou daily est alors sous-estimée. Continu : un pont brownien reconstitue les extrema intra-pas — P(KI) plus élevée, la jambe put d'un autocall est mieux valorisée. Les valeurs aux dates d'observation (WOF, fixings) restent inchangées." />
          </label>
          <select v-model="store.globalParams.barrierMonitoring" class="select">
            <option value="weekly">Hebdomadaire (grille MC)</option>
            <option value="continuous">Continu (pont brownien)</option>
          </select>
        </div>
      </div>
      <div class="mt-3">
        <label class="flex items-center gap-2 text-xs text-slate-300 cursor-pointer w-fit">
          <input type="checkbox" v-model="store.globalParams.antithetic" class="accent-blue-500" />
          Variantes antithétiques (variance réduite)
          <HelpTip text="Pour chaque trajectoire tirée, simule aussi son opposé (mêmes chocs aléatoires inversés) et moyenne les deux. Réduit la variance de l'estimateur de prix sans biais — même précision qu'un N plus grand, à coût de calcul quasi identique. Laissez coché sauf cas de débogage." />
        </label>
      </div>
    </div>

    <!-- ── Greeks ─────────────────────────────────────────────────── -->
    <div class="card">
      <h2 class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3">
        Greeks (CRN bump-and-reprice)
        <span class="font-normal text-slate-600 ml-1">— cochez puis "∂ Greeks"</span>
        <HelpTip text="CRN = Common Random Numbers : chaque greek est calculé en repriçant avec le paramètre bumpé mais les mêmes tirages aléatoires que le prix central, pour annuler le bruit Monte Carlo dans la différence. Cocher plus de greeks multiplie le nombre de repricings (donc le temps de calcul)." />
      </h2>
      <div class="flex flex-wrap gap-2">
        <label v-for="g in greekOptions" :key="g.key"
          class="greek-chk"
          :class="{ 'greek-chk-on': store.greekSel[g.key] }">
          <input type="checkbox" v-model="store.greekSel[g.key]" class="accent-blue-500" />
          <span v-html="g.label"></span>
          <HelpTip :text="g.tip" />
        </label>
      </div>
    </div>

    <!-- ── Sous-jacents (calibration) ────────────────────────────── -->
    <div class="card">
      <h2 class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3">Sous-jacents — calibration
        <HelpTip text="La composition du panier (choix des sous-jacents, tickers) se définit dans l'onglet Deal. Ici, seuls les paramètres de marché (volatilité, dividende, smile, quanto) sont calibrés pour chaque sous-jacent déjà ajouté." />
      </h2>

      <!-- Liste des sous-jacents (toujours visible) -->
      <div class="flex gap-1 mb-3 flex-wrap items-center">
        <button v-for="(u, i) in store.underlyings" :key="i"
          @click="store.activeUnderlyingIdx = i"
          :class="[
            'px-2.5 py-1 rounded-md text-xs font-medium transition-colors border',
            activeIdx === i
              ? 'bg-blue-900/50 border-blue-600 text-blue-300'
              : 'bg-slate-800 border-slate-700 text-slate-400 hover:border-slate-500 hover:text-slate-200'
          ]">
          <span class="font-semibold">{{ demo.underlyingLabel(u.name, i) }}</span>
          <span v-if="u.ticker" class="ml-1.5 opacity-50 font-mono text-[10px]">
            <SensitiveValue placeholder="···">{{ u.ticker }}</SensitiveValue>
          </span>
        </button>
      </div>

      <!-- Card du sous-jacent actif -->
      <div v-if="au" class="bg-slate-800/60 border border-slate-700 rounded-lg p-4">

        <!-- Nom (identité définie dans Deal, lecture seule ici) -->
        <div class="mb-3 text-sm font-semibold text-slate-300 border-b border-slate-600 pb-1">
          {{ demo.underlyingLabel(au.name, activeIdx) }}
        </div>

        <!-- YF status inline -->
        <div v-if="store.yfStatus" class="text-xs mb-2 leading-relaxed"
             :class="store.yfStatus.startsWith('⚠') ? 'text-amber-400' : 'text-green-400'">
          <SensitiveValue placeholder="Données chargées">{{ store.yfStatus }}</SensitiveValue>
        </div>

        <!-- Paramètres de base -->
        <div class="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs mb-2">
          <div>
            <label class="label">σ (%)
              <HelpTip text="Volatilité annualisée du sous-jacent, utilisée telle quelle en modèle Constant (GBM) ou comme point de départ/référence pour les modèles à smile (Heston/SABR/Local Vol)." />
            </label>
            <SensitiveValue mode="input"><input v-model.number="au.sigma" type="number" step="0.5" class="input" /></SensitiveValue>
          </div>
          <div>
            <label class="label">q (%/an)
              <HelpTip text="Rendement du dividende, soustrait du drift risque-neutre (μ = r − q). Un q plus élevé réduit la dérive du sous-jacent, donc réduit le prix des calls et augmente celui des puts, toutes choses égales par ailleurs." />
            </label>
            <SensitiveValue mode="input"><input v-model.number="au.q" type="number" step="0.1" class="input" /></SensitiveValue>
          </div>

          <!-- Heston params (also used by LSV's stochastic variance leg) -->
          <template v-if="store.globalParams.model === 'heston' || store.globalParams.model === 'lsv'">
            <div><label class="label">V₀ (%)
                <HelpTip text="Variance instantanée de départ (racine = vol de départ). Si différent de σ ci-dessus, le processus de vol Heston converge progressivement de V₀ vers θ." /></label>
              <SensitiveValue mode="input"><input v-model.number="au.v0" type="number" step="0.5" class="input" /></SensitiveValue></div>
            <div><label class="label">κ (mean-rev.)
                <HelpTip text="Vitesse de retour de la variance vers son niveau long terme θ. κ grand = la vol revient vite à θ (smile qui s'aplatit vite avec la maturité) ; κ petit = la vol met du temps à revenir, smile persistant." /></label>
              <SensitiveValue mode="input"><input v-model.number="au.kappa" type="number" step="0.1" class="input" /></SensitiveValue></div>
            <div><label class="label">θ long-term (%)
                <HelpTip text="Niveau de variance long terme vers lequel V₀ converge — le niveau de vol « structurel » du sous-jacent, indépendant du régime court terme." /></label>
              <SensitiveValue mode="input"><input v-model.number="au.theta" type="number" step="0.5" class="input" /></SensitiveValue></div>
            <div><label class="label">ξ vol-of-vol (%)
                <HelpTip text="Volatilité de la variance elle-même. Contrôle l'épaisseur du smile — ξ=0 dégénère vers un GBM à vol constante, ξ élevé donne un smile prononcé (queues épaisses)." /></label>
              <SensitiveValue mode="input"><input v-model.number="au.xi" type="number" step="1" class="input" /></SensitiveValue></div>
            <div><label class="label">ρ_h corr (%)
                <HelpTip text="Corrélation entre le choc sur le spot et le choc sur la variance. Négative (typique actions) = effet levier, la vol monte quand le spot baisse, ce qui pentifie le skew (puts plus chers que calls à même distance du strike)." /></label>
              <SensitiveValue mode="input"><input v-model.number="au.rho_h" type="number" step="1" class="input" /></SensitiveValue></div>
          </template>

          <!-- SABR params -->
          <template v-if="store.globalParams.model === 'sabr'">
            <div><label class="label">α ATM vol (%)
                <HelpTip text="Niveau de volatilité à la monnaie (ATM) — le paramètre SABR analogue à σ en GBM." /></label>
              <SensitiveValue mode="input"><input v-model.number="au.alpha" type="number" step="0.5" class="input" /></SensitiveValue></div>
            <div><label class="label">β (%)
                <HelpTip text="Élasticité CEV du processus de spot (0 = normal/Bachelier, 100% = lognormal). Contrôle la forme du backbone du smile — rarement calibré, souvent fixé (ex: 50-100% sur indices actions)." /></label>
              <SensitiveValue mode="input"><input v-model.number="au.beta" type="number" step="5" class="input" /></SensitiveValue></div>
            <div><label class="label">ρ (%)
                <HelpTip text="Corrélation spot/vol SABR — pilote l'asymétrie (skew) du smile, comme ρ_h en Heston." /></label>
              <SensitiveValue mode="input"><input v-model.number="au.rho" type="number" step="1" class="input" /></SensitiveValue></div>
            <div><label class="label">ν vol-of-vol (%)
                <HelpTip text="Vol de la vol SABR — pilote la courbure (convexité) du smile, comme ξ en Heston." /></label>
              <SensitiveValue mode="input"><input v-model.number="au.nu" type="number" step="1" class="input" /></SensitiveValue></div>
          </template>

          <!-- Dupire local vol params (also the calibration target for LSV) -->
          <template v-if="store.globalParams.model === 'localvol' || store.globalParams.model === 'lsv'">
            <div>
              <label class="label">Skew <span class="text-slate-600 font-normal">(%/ln(K/F))</span>
                <HelpTip text="Pente du smile paramétrique par unité de log-moneyness. Négatif = puts OTM plus chers que calls OTM (skew actions typique)." />
              </label>
              <SensitiveValue mode="input"><input v-model.number="au.skew" type="number" step="1" class="input" placeholder="-10" /></SensitiveValue>
            </div>
            <div>
              <label class="label">Convexité <span class="text-slate-600 font-normal">(%)</span>
                <HelpTip text="Courbure du smile paramétrique — contrôle à quel point les deux ailes (calls et puts très OTM) remontent par rapport au centre." />
              </label>
              <SensitiveValue mode="input"><input v-model.number="au.curvature" type="number" step="0.5" class="input" placeholder="5" /></SensitiveValue>
            </div>
          </template>

          <!-- Rate-spot correlation (only meaningful once a rate model is active) -->
          <div v-if="store.globalParams.rateModel !== 'deterministic'">
            <label class="label">ρ(r,S) (%) <span class="text-slate-600 font-normal">corr taux-spot</span>
              <HelpTip text="Corrélation entre les chocs sur ce sous-jacent et le facteur de taux stochastique (ABM/Hull-White). N'a d'effet que si un modèle de taux stochastique est actif." />
            </label>
            <SensitiveValue mode="input"><input v-model.number="au.rho_rS" type="number" step="5" min="-100" max="100" class="input" /></SensitiveValue>
          </div>
        </div>

        <!-- Vol smile chart (Dupire / SABR / Heston) -->
        <VolSmile :idx="activeIdx" />

        <!-- Quanto / CCY -->
        <button class="text-xs text-slate-500 hover:text-blue-400 transition-colors mt-1"
                @click="au.showQuanto = !au.showQuanto">
          {{ au.showQuanto ? '▲' : '▼' }}
          Quanto / CCY
          <span v-if="au.ccy !== store.globalParams.deal_ccy" class="text-amber-500 ml-1">⚠ CCY ≠ deal</span>
        </button>

        <div v-if="au.showQuanto" class="grid grid-cols-2 sm:grid-cols-3 gap-2 text-xs mt-2 pt-2 border-t border-slate-700">
          <div>
            <label class="label">σ<sub>FX</sub> (%) <span class="text-slate-600 font-normal">vol FX</span>
              <HelpTip text="Volatilité du taux de change entre la devise du sous-jacent (CCY) et la devise du deal. N'a d'effet que si les deux diffèrent (⚠ CCY ≠ deal ci-dessus)." />
            </label>
            <SensitiveValue mode="input"><input v-model.number="au.sigma_fx" type="number" step="0.5" class="input" /></SensitiveValue>
          </div>
          <div>
            <label class="label">ρ(S,FX) (%) <span class="text-slate-600 font-normal">corr</span>
              <HelpTip text="Corrélation entre le sous-jacent et le taux de change — pilote l'ajustement quanto du drift (le sous-jacent est payé dans une devise, converti dans une autre à un taux fixé d'avance)." />
            </label>
            <SensitiveValue mode="input"><input v-model.number="au.rho_sfx" type="number" step="1" min="-100" max="100" class="input" /></SensitiveValue>
          </div>
          <div>
            <label class="label">Basis CCYH (bp) <span class="text-slate-600 font-normal">spread</span>
              <HelpTip text="Spread de base de change (cross-currency basis) ajouté au drift quanto — un coût/bénéfice de financement additionnel entre les deux devises, indépendant de la corrélation spot/FX." />
            </label>
            <SensitiveValue mode="input"><input v-model.number="au.ccyh" type="number" step="5" class="input" /></SensitiveValue>
          </div>
        </div>
      </div>
    </div>

    <!-- ── Courbe de dividende ──────────────────────────────────────── -->
    <DividendCurveCard />

    <!-- ── Courbe de taux ───────────────────────────────────────────── -->
    <YieldCurveCard />

    <!-- ── Matrice corrélation ────────────────────────────────────── -->
    <div v-if="store.underlyings.length > 1" class="card">
      <h2 class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3">Matrice de corrélation
        <HelpTip width="w-72" text="Corrélation entre les chocs browniens des sous-jacents dans la simulation. Sur un payoff worst-of, une corrélation plus faible augmente la dispersion des trajectoires donc la probabilité qu'un des actifs traîne loin derrière — c'est en général défavorable au détenteur du produit. La diagonale est fixée à 1 (chaque actif est parfaitement corrélé à lui-même)." />
      </h2>
      <div class="overflow-x-auto">
        <table class="text-xs border-collapse">
          <thead>
            <tr>
              <th class="w-20"></th>
              <th v-for="(u, j) in store.underlyings" :key="j"
                  class="text-slate-400 font-medium pb-1 px-2 text-center">
                {{ demo.underlyingLabel(u.name, j).slice(0, 7) }}
              </th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(u, i) in store.underlyings" :key="i">
              <td class="text-slate-400 font-medium pr-2 py-1 whitespace-nowrap">{{ demo.underlyingLabel(u.name, i).slice(0, 7) }}</td>
              <td v-for="(_, j) in store.underlyings" :key="j" class="px-1 py-0.5">
                <SensitiveValue v-if="i !== j" mode="input" placeholder="·.··">
                  <input type="number" step="0.05" min="-1" max="1"
                    :value="store.corrMatrix[i]?.[j] ?? 0"
                    @input="setCorr(i, j, $event.target.value)"
                    class="input w-16 text-center text-xs" />
                </SensitiveValue>
                <span v-else class="block text-center text-slate-600 w-16">1.00</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { usePricingStore } from '../stores/pricing.js'
import { useDemoModeStore } from '../stores/demoMode.js'
import VolSmile from './VolSmile.vue'
import DividendCurveCard from './DividendCurveCard.vue'
import YieldCurveCard from './YieldCurveCard.vue'
import SensitiveValue from './SensitiveValue.vue'
import HelpTip from './HelpTip.vue'
import { formatNumber } from '../utils/format.js'

const store = usePricingStore()
const demo = useDemoModeStore()

// Active underlying — shared with Deal (store.activeUnderlyingIdx), which owns
// add/remove/ticker selection. This tab only calibrates whichever one is active.
const activeIdx = computed(() => store.activeUnderlyingIdx)
const au = computed(() => store.underlyings[activeIdx.value] ?? store.underlyings[0])

const greekOptions = [
  { key: 'delta', label: '&Delta; Delta',  tip: 'Sensibilité au spot (+1% bump centré)' },
  { key: 'gamma', label: '&Gamma; Gamma',  tip: 'Convexité au spot (±3% bump)' },
  { key: 'vega',  label: '&nu; Vega',      tip: 'Sensibilité à la vol (+1% bump)' },
  { key: 'theta', label: '&Theta; Theta',  tip: 'Décroissance temporelle (1j)' },
  { key: 'rho',   label: '&rho; Rho',      tip: 'Sensibilité aux taux (+100bp)' },
  { key: 'corr',  label: '&rho;<sub>ij</sub> Corr', tip: 'Sensibilité corrélation (+5%, multi-actifs)' },
]

function setCorr(i, j, val) {
  const v = Math.max(-1, Math.min(1, parseFloat(val) || 0))
  if (!store.corrMatrix[i]) store.corrMatrix[i] = []
  store.corrMatrix[i][j] = v
  store.corrMatrix[j][i] = v
}
</script>

<style scoped>
.greek-chk {
  @apply inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border border-slate-700
         text-xs font-semibold text-slate-400 cursor-pointer bg-slate-800/50
         hover:border-blue-600 hover:text-blue-400 transition-colors select-none;
}
.greek-chk-on {
  @apply border-blue-600 bg-blue-950/50 text-blue-400;
}
</style>
