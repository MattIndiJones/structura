<template>
<div>
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
          <template v-if="model === 'heston' || model === 'lsv'">
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
          <template v-if="model === 'sabr'">
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
          <template v-if="model === 'localvol' || model === 'lsv'">
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
          <div v-if="rateModel !== 'deterministic'">
            <label class="label">ρ(r,S) (%) <span class="text-slate-600 font-normal">corr taux-spot</span>
              <HelpTip text="Corrélation entre les chocs sur ce sous-jacent et le facteur de taux stochastique (ABM/Hull-White). N'a d'effet que si un modèle de taux stochastique est actif." />
            </label>
            <SensitiveValue mode="input"><input v-model.number="au.rho_rS" type="number" step="5" min="-100" max="100" class="input" /></SensitiveValue>
          </div>
        </div>

        <!-- Vol smile chart (Dupire / SABR / Heston) -->
        <VolSmile :underlying="au" :model="model" :horizon="horizon" />

</div>
</template>

<script setup>
import VolSmile from './VolSmile.vue'
import SensitiveValue from './SensitiveValue.vue'
import HelpTip from './HelpTip.vue'

const { au, model, horizon, rateModel } = defineProps({
  au: { type: Object, required: true },
  model: { type: String, required: true },
  horizon: { type: Number, required: true },
  rateModel: { type: String, default: 'deterministic' },
})
</script>
