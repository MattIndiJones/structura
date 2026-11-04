<template>
  <section class="smile-editor mt-3 pt-3 border-t border-slate-700" aria-label="Surface de volatilité">
    <div class="surface-controls mb-2">
      <label>
        <span class="label">Profil de smile</span>
        <select class="select" :value="surface?.profile || ''" @change="selectProfile($event.target.value)" :disabled="busy">
          <option value="">Choisir la classe d’actif</option>
          <option value="equity">Actions</option><option value="index">Indices actions</option>
        </select>
      </label>
      <label v-if="surface">
        <span class="label">Scénario ATM 1–10 ans</span>
        <select class="select" :value="surface.atm_scenario || ''" :disabled="busy" @change="selectAtm($event)">
          <option value="" disabled>Choisir un scénario</option>
          <option v-for="(label, key) in ATM_SCENARIOS" :key="key" :value="key">{{ label }}</option>
          <option v-if="surface.atm_scenario === 'custom'" value="custom" disabled>Personnalisée</option>
        </select>
      </label>
      <template v-if="explicitHeston">
        <label>
          <span class="label">Objectif de calibration</span>
          <select class="select" :value="hestonFitOptions(u).mode" :disabled="fit?.status === 'loading'"
            @change="u.heston_fit = { mode: $event.target.value }">
            <option v-for="(label, mode) in HESTON_FIT_LABELS" :key="mode" :value="mode">{{ label }}</option>
          </select>
        </label>
        <button type="button" class="btn-primary surface-calibrate text-xs"
          :disabled="busy || fit?.status === 'loading'"
          @click="calibrateHeston">Calibrer et appliquer Heston</button>
      </template>
    </div>
    <div v-if="surface" class="flex flex-wrap items-center gap-x-3 gap-y-2 mb-3">
      <template v-if="explicitHeston">
        <span class="badge" role="status">{{ hestonStatus }}</span>
      </template>
      <span v-if="surface" class="badge">Surface indicative</span>
      <button v-if="surface" class="btn text-xs" @click="resetProfile" :disabled="busy">Réinitialiser le profil</button>
      <button v-if="undo" class="btn text-xs" @click="restore" :disabled="busy">Annuler la modification</button>
    </div>
    <p v-if="model === 'heston' && !appliedHeston" class="mb-2 text-xs text-amber-700" role="status">
      {{ u.calibration_evidence?.dossier?.model === 'heston'
        ? 'La calibration précédente ne couvre plus les hypothèses actuelles. Recalibrez pour les appliquer ; le Pricer conserve les paramètres Heston affichés entre-temps.'
        : 'Heston non calibré. Le Pricer utilise les paramètres Heston affichés.' }}
    </p>
    <p v-if="!surface" class="text-xs text-slate-500">Sélectionnez un profil pour initialiser une surface indicative autour de la vol choisie. Les hypothèses existantes sont conservées tant que vous ne l’activez pas.</p>
    <template v-else>
      <p class="text-xs text-slate-500 mb-3">Hypothèse de smile, sans cotations d’options. Strikes en % du forward. σ ci-dessus correspond à l’ATM 1 an.
        {{ u.vol_level_source==='realized' ? 'Niveau repris de la volatilité réalisée chargée.' : '' }}</p>
      <p v-if="explicitHeston" class="text-xs text-slate-500 mb-3">
        {{ atmScenarioNote }} {{ hestonFitNote }}
      </p>
      <div class="grid grid-cols-2 sm:grid-cols-4 gap-2 mb-2">
        <div><label class="label">Maturité active</label><select class="select" v-model.number="tenor" :disabled="busy">
          <option v-for="t in tenors" :key="t" :value="t">{{ tenorLabel(t) }}</option></select></div>
        <div><label class="label">Déplacement de courbe</label><select class="select" v-model="scope" :disabled="busy">
          <option value="one">Cette maturité</option><option value="all">Toutes les maturités</option></select></div>
        <div><label class="label">Asymétrie (%)</label><SensitiveValue mode="input"><input class="input" type="number" step="1" min="-99" max="99"
          :value="Number((surface.rho*100).toFixed(4))" @change="editShape('rho',$event.target.value,$event)" :disabled="busy" /></SensitiveValue></div>
        <div><label class="label">Intensité du smile</label><SensitiveValue mode="input"><input class="input" type="number" step=".05" min="0" max="3"
          :value="Number(surface.eta.toFixed(5))" @change="editShape('eta',$event.target.value,$event)" :disabled="busy || !!surface.wing_nodes" /></SensitiveValue></div>
      </div>
      <form class="surface-controls mb-2" @submit.prevent="adjustWing">
        <label><span class="label">Échéance de l’aile gauche</span>
          <select v-model.number="tenor" class="select" :disabled="busy">
            <option v-for="t in tenors" :key="t" :value="t">{{ tenorLabel(t) }}</option>
          </select>
        </label>
        <label><span class="label">Strike / forward</span>
          <select v-model.number="wingStrike" class="select" :disabled="busy">
            <option v-for="k in strikes.filter(k=>k<1)" :key="k" :value="k">{{ Math.round(k*100) }} %</option>
          </select>
        </label>
        <label><span class="label">Vol implicite cible (%)</span>
          <SensitiveValue mode="input"><input v-model.number="wingTarget" class="input" type="number" min=".01" max="300"
            step="any" required placeholder="110" :disabled="busy" /></SensitiveValue>
        </label>
        <button type="submit" class="btn-secondary text-xs surface-calibrate" :disabled="busy">Ajuster l’aile gauche</button>
      </form>
      <p class="text-xs text-slate-600 mb-2" role="status">
        {{ tenorLabel(tenor) }} · {{ Math.round(wingStrike*100) }} % du forward.
        <template v-if="visibleWingResult">
          Cible <SensitiveValue>{{ formatWingVol(visibleWingResult.target) }}</SensitiveValue> ·
          Avant <SensitiveValue>{{ formatWingVol(visibleWingResult.before) }}</SensitiveValue> ·
          Après <SensitiveValue>{{ formatWingVol(visibleWingResult.achieved*100) }}</SensitiveValue>.
          {{ visibleWingResult.changed ? 'Surface mise à jour.' : 'Surface inchangée.' }}
          {{ wingMessages[visibleWingResult.reason] }}
        </template>
        <template v-else>
          Vol actuelle <SensitiveValue>{{ formatWingVol(vol(tenor, wingStrike)) }}</SensitiveValue>.
          Saisissez une cible pour relever l’aile à ce point.
        </template>
      </p>
      <p v-if="surface.wing_nodes" class="text-xs text-slate-500 mb-2">
        Ajustement par échéance actif. Les strikes et échéances voisins s’ajustent pour préserver la cohérence de la surface. Réinitialisez le profil pour revenir à l’intensité globale.
      </p>
      <SensitiveChart>
        <svg ref="svg" class="smile-plot" viewBox="0 0 680 255" role="img" aria-label="Smiles éditables par maturité"
          @pointermove="move" @pointerup="release" @pointercancel="cancel" @lostpointercapture="cancel">
          <g v-for="v in ticks" :key="v"><line x1="48" x2="662" :y1="y(v)" :y2="y(v)" stroke="var(--border)" />
            <text x="42" :y="y(v)+4" text-anchor="end">{{ demo.enabled ? '•••' : v.toFixed(1)+' %' }}</text></g>
          <g v-for="k in strikes" :key="k"><text :x="x(k)" y="242" text-anchor="middle">{{ Math.round(k*100) }} %</text></g>
          <path v-for="t in plotTenors" :key="t" :d="curve(t)" fill="none" :stroke="colors[tenors.indexOf(t)%colors.length]"
            :stroke-width="t===tenor?3:1.5" :opacity="t===tenor?1:.65" class="smile-line"
            :stroke-dasharray="t===.25?'2 3':t===.5?'6 3':undefined" :data-tenor="t" />
          <path v-if="scope==='all' || !interpolatedAtm(tenor)" :d="curve(tenor)" fill="none"
            stroke="transparent" stroke-width="12" class="smile-drag-target"
            @pointerdown.stop.prevent="start($event,tenor)" />
          <circle v-for="k in strikes" :key="k" :cx="x(k)" :cy="y(vol(tenor,k))" r="5.5" class="smile-handle"
            :fill="colors[tenors.indexOf(tenor)%colors.length]" :data-strike="k"
            @pointerdown.stop.prevent="start($event,tenor,k)" />
          <text x="350" y="254" text-anchor="middle">Strike / forward</text>
        </svg>
      </SensitiveChart>
      <div class="flex flex-wrap gap-1 mb-2">
        <button v-for="(t,i) in tenors" :key="t" class="btn text-xs" :class="t===tenor?'font-bold':''"
          :aria-pressed="t===tenor" @click="tenor=t" :style="{color:colors[i%colors.length]}">{{ tenorLabel(t) }}</button>
      </div>
      <p class="text-[11px] text-slate-500 mb-2">
        Choisissez la maturité dans le sélecteur, la légende ou le tableau, puis tirez la courbe active.
        Les courbes 3 mois et 6 mois sont en pointillés.
        <template v-if="surface.atm_scenario">
          Leurs niveaux ATM sont interpolés à partir du pilier 1 an et évoluent avec lui.
        </template>
      </p>
      <div class="overflow-x-auto table-shell"><table class="w-full text-xs">
        <thead><tr><th class="text-left">Maturité</th><th v-for="k in strikes" :key="k" class="text-right">{{ k===1?'ATM':Math.round(k*100)+' %' }}</th></tr></thead>
        <tbody><tr v-for="t in tenors" :key="t" class="smile-row" :class="{'active-row': t === tenor}"
          @click="tenor = t">
          <th scope="row">
            <button type="button" class="smile-row-selector" :aria-pressed="t === tenor">{{ tenorLabel(t) }}</button>
          </th>
          <td v-for="k in strikes" :key="k">
            <SensitiveValue mode="input"><input class="input smile-cell text-right" type="number" step=".1" min=".01"
              :aria-label="`Vol ${tenorLabel(t)} strike ${Math.round(k*100)} %`" :value="Number(vol(t,k).toFixed(4))"
              @focus="tenor = t" @change="editNode(t,k,Number($event.target.value),$event)"
              :disabled="busy" :readonly="k!==1 ? !!surface.wing_nodes : interpolatedAtm(t)" /></SensitiveValue>
          </td></tr></tbody></table></div>
      <p v-if="busy" class="text-xs text-blue-500 mt-2">Validation de la surface…</p>
      <p v-if="message || u.smile_error" role="alert" class="text-xs text-amber-600 mt-2">{{ message || u.smile_error }}</p>
      <div v-if="explicitHeston && fit?.dossier?.heston_fit?.mode" class="text-xs text-slate-500 mt-2" aria-live="polite">
        <p>Écarts maximaux : calls ATM · {{ bp(fit.dossier.controls.max_atm_error_bp) }} ;
          calls hors ATM · {{ bp(fit.dossier.controls.max_wing_error_bp) }} ;
          digitales 60/100 % spot · {{ bp(fit.dossier.controls.max_barrier_digital_error_bp) }}.</p>
        <p v-if="fit.dossier.controls.worst_atm">
          Pire call ATM · {{ tenorLabel(fit.dossier.controls.worst_atm.expiry) }} ·
          {{ bp(fit.dossier.controls.worst_atm.error_bp) }}.
          Pire digitale · {{ tenorLabel(fit.dossier.controls.worst_barrier_digital.expiry) }} ·
          strike {{ fit.dossier.controls.worst_barrier_digital.strike_spot_pct }} % spot.
        </p>
        <template v-if="fit.dossier.heston_fit.mode === 'atm_smile'">
          <p>Plafond ATM par échéance · {{ bp(fit.dossier.optimizer.atm_constraint_bp) }}.
            Écart RMS des ailes pondéré par vega · {{ volPoints(fit.dossier.optimizer.wing_rms_before_vol_points) }}
            → {{ volPoints(fit.dossier.optimizer.wing_rms_after_vol_points) }}.</p>
          <p v-if="!fit.dossier.optimizer.wing_refined">Aucun candidat ne réduit l’écart des ailes dans le plafond ATM. L’ajustement ATM a été conservé.</p>
          <p v-else-if="fit.dossier.optimizer.wing_solver_converged === false">L’optimisation des ailes n’a pas confirmé la convergence. Le meilleur candidat vérifié par Fourier a été retenu.</p>
          <p v-if="fit.dossier.controls.near_bounds?.length">Paramètres proches d’une borne ·
            {{ fit.dossier.controls.near_bounds.map(key => hestonParamLabels[key]).join(', ') }}.</p>
        </template>
        <p v-if="fit.dossier.optimizer.solver_converged === false">Le solveur initial n’a pas confirmé la convergence. Le meilleur candidat a été vérifié par Fourier.</p>
        <p v-if="surface.rho < 0 && fit.dossier.parameters.rho_h >= 0" class="text-amber-700">
          La corrélation spot–variance ajustée est positive ou nulle malgré le skew baissier de la surface cible.
        </p>
        <p v-if="fit.qualification?.reasons?.length">{{ fit.qualification.reasons.join(' ') }}</p>
        <p v-if="fit.status === 'candidate'">Paramètres proposés ·
          {{ Object.entries(fit.parameters).map(([k,v])=>`${k} ${demo.enabled ? '•••' : Number(v).toPrecision(5)}`).join(' · ') }}
        </p>
      </div>
      <div v-else-if="needsCalibration && !explicitHeston" class="text-xs text-slate-500 mt-2" aria-live="polite">
        <span v-if="u.smile_parameter_mode==='manual'">Paramètres de modèle saisis manuellement ; la surface reste une cible de référence.
          <button class="btn text-xs ml-2" @click="recalibrate">Recalibrer sur la surface</button></span>
        <span v-else-if="fit?.status==='loading'">Recalibration {{ model==='sabr'?'SABR':'Heston' }} en cours…</span>
        <span v-else-if="['ready','unqualified'].includes(fit?.status)">
          {{ fit.status==='ready' ? 'Ajustement qualifié aux points contrôlés.' : 'Ajustement exploratoire, paramètres non appliqués.' }}
          {{ fit.success ? 'Optimisation convergée.' : 'Optimisation non convergée.' }}
          Écarts maximaux : vanille {{ demo.enabled ? '•••' : Number(fit.max_price_error_bp).toFixed(1) }} pb / seuil {{ fit.qualification?.thresholds_bp?.vanilla ?? 5 }} pb ;
          digitale {{ demo.enabled ? '•••' : Number(fit.max_digital_error_bp).toFixed(1) }} pb / seuil 10 pb.
          {{ fit.qualification?.reasons?.join(' ') }}
          Taux/dividende plats, sans quanto. Ce contrôle ne qualifie pas le Monte Carlo de production ni les barrières.
          <details v-if="fit.dossier"><summary>Périmètre de calibration</summary>
            <span>Maturités : {{ fit.dossier.grid.expiries.join(', ') }} ans.
              Horizon couvert : {{ fit.dossier.context.fit_horizon }} ans sur {{ fit.dossier.context.requested_horizon }}.
              Piliers exclus : {{ fit.dossier.grid.excluded_pillars.map(p=>p.expiry+' ans').join(', ') || 'aucun' }}.</span>
            <template v-if="fit.dossier.controls.atm_error_bp">
              <p>ATM forward {{ bp(fit.dossier.controls.max_atm_error_bp) }} · Ailes {{ bp(fit.dossier.controls.max_wing_error_bp) }} · Digitales 60/100 % spot {{ bp(fit.dossier.controls.max_barrier_digital_error_bp) }}.</p>
              <p v-if="fit.dossier.controls.near_bounds.length">Paramètres proches d’une borne · {{ fit.dossier.controls.near_bounds.join(', ') }}</p>
              <p>Écarts ATM par échéance · {{ fit.dossier.controls.atm_error_bp.map(bp).join(' / ') }}</p>
            </template>
            <template v-if="fit.dossier.controls.worst_vanilla">
              <p v-for="kind in ['vanilla','digital']" :key="kind">
                {{ kind === 'vanilla' ? 'Vanille' : 'Digitale' }} la plus éloignée ·
                {{ tenorLabel(fit.dossier.controls['worst_'+kind].expiry) }} ·
                strike {{ Number(fit.dossier.controls['worst_'+kind].strike_spot_pct).toFixed(2) }} % du spot ·
                {{ bp(fit.dossier.controls['worst_'+kind].error_bp) }}
              </p>
            </template>
          </details>
        </span>
        <span v-else-if="fit?.status==='error'" class="text-amber-600">{{ fit.message }}</span>
        <span v-else>La nouvelle surface nécessite une recalibration.</span>
      </div>
      <p v-if="model==='lsv'" class="text-xs text-slate-500 mt-2">
        À l’émission, le Pricer estime le levier sur la cible Dupire avec les paramètres de variance affichés.
        Taux et dividendes plats, monitoring hebdomadaire.
      </p>
      <p v-if="model==='constant'" class="text-xs text-slate-500 mt-2">Constant utilise σ ATM 1 an. La surface est conservée pour les modèles à smile.</p>
    </template>
  </section>
</template>

<script setup>
import { computed, ref, watch, onUnmounted } from 'vue'
import { useDemoModeStore } from '../stores/demoMode.js'
import { apiFetch, apiErrorMessage } from '../utils/api.js'
import { underlyingGroups } from '../data/commonUnderlyings.js'
import { ATM_SCENARIOS, applyAtmScenario, HESTON_FIT_LABELS, hasExplicitHestonFit, hestonFitOptions, surfaceCalibrationKey, SMILE_STRIKES, SMILE_PROFILES, cloneSurface, makeSurface, surfaceVol,
  validateSurface, shiftSurface, moveSurfaceNode, synchronizeSurfaceLevel, resizeSurfaceLevel, classifyUnderlying } from '../utils/volSurface.js'
import { calibrateUnderlying, explicitHestonCalibration, fitAndApplyHeston } from '../utils/smileCalibration.js'
import SensitiveChart from './SensitiveChart.vue'
import SensitiveValue from './SensitiveValue.vue'

const props=defineProps({u:{type:Object,required:true},model:{type:String,required:true},
  horizon:{type:Number,default:4},rate:{type:Number,default:3}})
const surface=computed(()=>props.u.vol_surface)
const demo=useDemoModeStore()
const bp=value=>demo.enabled?'•••':`${Number(value).toFixed(2)} pb`
const volPoints=value=>demo.enabled?'•••':`${Number(value).toFixed(2)} pts de vol équiv.`
const hestonParamLabels = { v0:'V₀', theta:'θ', kappa:'κ', xi:'ξ', rho_h:'ρ Heston' }
const tenors = computed(() => {
  const s = surface.value
  if (!s) return []
  const shortTenors = [.25, .5].filter(t => t <= s.max_expiry)
  return [...new Set([...shortTenors, ...s.atm_nodes.map(([t]) => t), ...(s.wing_nodes || []).map(([t]) => t)])]
    .sort((a, b) => a - b)
})
const tenor=ref(1),scope=ref('one'),message=ref(''),undo=ref(null),busy=ref(false),svg=ref(null)
const plotTenors = computed(() => tenors.value.includes(tenor.value)
  ? [...tenors.value.filter(t => t !== tenor.value), tenor.value] : tenors.value)
const wingStrike=ref(.2),wingTarget=ref(''),wingResult=ref(null)
const visibleWingResult = computed(() => {
  const result = wingResult.value
  if (result && result.expiry === tenor.value && result.strike === wingStrike.value
      && result.target === Number(wingTarget.value) && result.surface === surface.value) return result
  return null
})
const formatWingVol = value => `${value.toLocaleString('fr-FR', {maximumFractionDigits:2})} %`
const interpolatedAtm=t=>!!surface.value?.atm_scenario && !surface.value.atm_nodes.some(([time])=>time===t)
const wingMessages = {
  target: 'Cible atteinte.',
  ssvi: 'Les contraintes sans arbitrage limitent la hausse.',
  dupire: 'La limite de volatilité locale de Dupire restreint la hausse.',
  already_at_or_above: 'La volatilité actuelle atteint déjà cette cible.',
}
watch(tenors,times=>{if(times.length && !times.includes(tenor.value)) tenor.value=times.includes(1)?1:times[0]})
const strikes=SMILE_STRIKES,colors=['#356ca5','#946dba','#2d8c7e','#ce8b38','#be6068','#7279bb','#7d9460','#777777']
const needsCalibration=computed(()=>surface.value&&props.model==='sabr')
const explicitHeston = computed(() => hasExplicitHestonFit(props.u, props.model))
const appliedHeston = computed(() => props.model === 'heston' && explicitHestonCalibration(props.u, props.horizon, props.rate))
const fit = computed(() => {
  const current = props.u.smile_calibration
  if (!explicitHeston.value) return current
  const key = surfaceCalibrationKey(props.u, props.model, props.horizon, props.rate)
  return current?.key === key ? current : appliedHeston.value
})
const hestonStatus = computed(() => ({
  ready: HESTON_FIT_LABELS[fit.value?.dossier?.heston_fit?.mode]
    ? `Appliquée : ${HESTON_FIT_LABELS[fit.value.dossier.heston_fit.mode]}` : 'Calibration précédente appliquée',
  candidate: 'Application en cours', unqualified: 'Ajustement indisponible',
  loading: 'Calibration en cours', error: 'Calibration à relancer',
})[fit.value?.status] || 'Calibration optionnelle')
const atmScenarioNote = computed(() => ({
  flat: 'Plate : même vol ATM forward de 1 à 10 ans ; le smile par strike reste présent.',
  contango: 'Contango : la vol ATM forward monte linéairement jusqu’à +10 % du niveau 1 an à 10 ans.',
  backwardation: 'Backwardation : la vol ATM forward baisse linéairement jusqu’à −10 % du niveau 1 an à 10 ans.',
  hump: 'Bosse : la vol ATM forward atteint +10 % à 3 ans, puis revient au niveau 1 an à 10 ans.',
})[surface.value?.atm_scenario] || 'Les vols ATM forward sont définies par les piliers de la courbe.')
const hestonFitNote = computed(() => ({
  atm: 'Les ailes de 20 à 180 % du forward restent des contrôles. L’objectif ATM seul ne fixe pas le skew Heston.',
  atm_digital: 'Le solveur ajoute les digitales à 60 % et 100 % du spot. Les ailes restent des contrôles.',
  atm_smile: 'Le solveur ajuste d’abord les calls ATM, puis les ailes de 20 à 180 % du forward sous un plafond ATM par échéance. Les digitales restent des contrôles.',
})[hestonFitOptions(props.u).mode])
const vol=(t,k=1)=>surfaceVol(surface.value,t,k)
const tenorLabel=t=>t<1?`${Math.round(t*12)} mois`:`${t} an${t>1?'s':''}`
const naturalBounds=computed(()=>{
  if(!surface.value)return[0,60]
  const vs=tenors.value.flatMap(t=>strikes.map(k=>vol(t,k)))
  const span=Math.max(8,Math.max(...vs)-Math.min(...vs))
  return[Math.max(0,Math.min(...vs)-span*.18),Math.max(...vs)+span*.18]
})
let drag=null,timer=null,revision=0
const bounds=computed(()=>drag?.bounds||naturalBounds.value)
const ticks=computed(()=>Array.from({length:5},(_,i)=>bounds.value[0]+i*(bounds.value[1]-bounds.value[0])/4))
const strikeMin = strikes[0], strikeMax = strikes.at(-1)
const x=k=>48+(k-strikeMin)/(strikeMax-strikeMin)*614
const y=v=>220-(v-bounds.value[0])/(bounds.value[1]-bounds.value[0])*205
const curve=t=>Array.from({length:161},(_,i)=>{const k=strikeMin+i*(strikeMax-strikeMin)/160;return`${i?'L':'M'}${x(k)},${y(vol(t,k))}`}).join(' ')

function scheduleCalibration() {
  clearTimeout(timer)
  if(drag||busy.value||!needsCalibration.value)return
  timer=setTimeout(()=>calibrateUnderlying(props.u,props.model,props.horizon,props.rate,
    ()=>({underlying:props.u,model:props.model,horizon:props.horizon,rate:props.rate})).catch(()=>{}),600)
}
watch(()=>JSON.stringify([surface.value,props.model,props.horizon,props.rate,props.u.q]),scheduleCalibration,{immediate:true})
watch(()=>props.u,()=>{undo.value=null;wingResult.value=null;message.value='';revision++;busy.value=false;cancel()})
watch(()=>props.u.sigma,()=>resizeSurfaceLevel(props.u),{flush:'sync'})
watch(()=>[props.u.ticker,underlyingGroups.length],()=>{
  if(!props.u._smileDefaults)return
  const kind=classifyUnderlying(props.u.ticker,underlyingGroups)
  if(kind==='unknown')return
  props.u.asset_class=kind
  if(props.u.vol_level_source==='default')props.u.sigma=SMILE_PROFILES[kind].sigma
  props.u.vol_surface=makeSurface(kind,props.u.sigma,props.horizon)
  props.u._smileDefaults=false
},{immediate:true})

async function commit(candidate,previous=cloneSurface(surface.value)) {
  const current=++revision,u=props.u
  message.value='';wingResult.value=null
  try {
    validateSurface(candidate);busy.value=true
    const response=await apiFetch('/api/volatility/validate',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({surface:candidate})})
    const result=await response.json()
    if(current!==revision||u!==props.u)return
    if(!response.ok)throw Error(apiErrorMessage(result,'Surface refusée.'))
    undo.value=previous;u.vol_surface=result.surface;synchronizeSurfaceLevel(u);u.smile_error=null
    if(result.surface.mode==='manual')u.vol_level_source='manual'
    if (props.model !== 'heston') u.smile_parameter_mode='automatic'
    return true
  } catch(e) {
    if(current===revision&&u===props.u){u.vol_surface=previous;if(previous)synchronizeSurfaceLevel(u);message.value=e.message}
    return false
  } finally {if(current===revision){busy.value=false;scheduleCalibration()}}
}
async function adjustWing() {
  const u=props.u, previous=surface.value, current=++revision
  const expiry=tenor.value, strike=wingStrike.value, target=Number(wingTarget.value)
  const before=surfaceVol(previous,expiry,strike)
  const horizon=props.horizon, rate=props.rate/100, dividend=u.q/100
  message.value='';wingResult.value=null;busy.value=true
  try {
    const response=await apiFetch('/api/volatility/left-wing',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({surface:previous,expiry,strike,target:target/100,horizon,rate,dividend})})
    const result=await response.json()
    if(current!==revision || u!==props.u) return
    if(surface.value!==previous || horizon!==props.horizon || rate!==props.rate/100 || dividend!==u.q/100)
      throw Error('Le marché a changé pendant l’ajustement. Relancez le calcul.')
    if(!response.ok) throw Error(apiErrorMessage(result,'Ajustement de l’aile refusé.'))
    if(result.changed) {
      validateSurface(result.surface)
      undo.value=cloneSurface(previous);u.vol_surface=result.surface;u.smile_error=null
      if(props.model!=='heston')u.smile_parameter_mode='automatic'
    }
    wingResult.value={...result,expiry,strike,target,before,surface:surface.value}
  } catch(e) {
    if(current===revision && u===props.u) message.value=e.message
  } finally {
    if(current===revision){busy.value=false;scheduleCalibration()}
  }
}
async function selectProfile(profile) {
  if(!profile)return
  if(await commit(profileSurface(profile))) {
    props.u.asset_class=profile;props.u._smileDefaults=false
  }
}
function profileSurface(profile) {
  const fresh = makeSurface(profile, props.u.sigma, props.horizon)
  if (!surface.value) return applyAtmScenario(fresh, 'flat')
  const restored=cloneSurface(surface.value)
  delete restored.wing_nodes
  return { ...restored, profile, rho: fresh.rho, eta: fresh.eta,
    shape_scale: fresh.shape_scale }
}
function resetProfile(){commit(profileSurface(surface.value.profile))}
async function selectAtm(event) {
  try { await commit(applyAtmScenario(surface.value, event.target.value)) }
  catch (e) { message.value = e.message }
  event.target.value = surface.value?.atm_scenario || ''
}
async function calibrateHeston() {
  const u = props.u
  message.value = ''
  try {
    await fitAndApplyHeston(u, props.horizon, props.rate,
      () => ({ underlying: props.u, model: props.model, horizon: props.horizon, rate: props.rate }))
  } catch (e) {
    if (props.u === u) message.value = e.message
  }
}
function recalibrate(){
  if (explicitHeston.value) return calibrateHeston()
  props.u.smile_parameter_mode='automatic';props.u.smile_calibration=null;scheduleCalibration()
}
function restore(){if(undo.value){const before=undo.value;undo.value=null;commit(before)}}
async function editShape(field,value,event){
  if(String(value).trim()==='' || !Number.isFinite(Number(value))) {
    message.value='Valeur requise : la dernière hypothèse est conservée.'
  } else {
    const s=cloneSurface(surface.value);s[field]=Number(value)/(field==='rho'?100:1);s.mode='manual';await commit(s)
  }
  event.target.value=field==='rho'?surface.value.rho*100:surface.value.eta
}
async function editNode(t,k,value,event){
  try{await commit(moveSurfaceNode(surface.value,t,k,value));event.target.value=vol(t,k).toFixed(4)}
  catch(e){message.value=e.message;event.target.value=vol(t,k).toFixed(4)}
}
function start(event,t,strike=null){
  if(busy.value||drag)return
  tenor.value=t
  if ((strike!=null && strike!==1 && surface.value.wing_nodes)
      || (interpolatedAtm(t) && (strike===1 || (strike==null && scope.value!=='all')))) return
  clearTimeout(timer)
  drag={u:props.u,id:event.pointerId,start:event.clientY,surface:cloneSurface(surface.value),bounds:[...naturalBounds.value],
    t,strike,moved:false,failed:false,sigma:props.u.sigma}
  svg.value.setPointerCapture(event.pointerId)
}
function move(event){
  if(!drag||event.pointerId!==drag.id)return
  if (!drag.moved && Math.abs(event.clientY-drag.start) < 2) return
  drag.moved=true
  const rect=svg.value.getBoundingClientRect()
  const delta=-(event.clientY-drag.start)/rect.height*255/205*(drag.bounds[1]-drag.bounds[0])
  try{
    const candidate=drag.strike===null?shiftSurface(drag.surface,drag.t,delta,scope.value==='all'):
      moveSurfaceNode(drag.surface,drag.t,drag.strike,surfaceVol(drag.surface,drag.t,drag.strike)+delta)
    props.u.vol_surface=candidate;synchronizeSurfaceLevel(props.u);drag.failed=false;message.value=''
  }catch(e){drag.failed=true;message.value=e.message}
}
function release(event){
  if(!drag||event.pointerId!==drag.id)return
  const d=drag;drag=null
  if(!d.moved){scheduleCalibration();return}
  if(d.failed){props.u.vol_surface=d.surface;props.u.sigma=d.sigma;scheduleCalibration();return}
  commit(cloneSurface(surface.value),d.surface)
}
function cancel(){if(drag){if(drag.moved){drag.u.vol_surface=drag.surface;drag.u.sigma=drag.sigma}drag=null;scheduleCalibration()}}
onUnmounted(()=>{revision++;cancel();clearTimeout(timer)})
</script>

<style scoped>
.surface-controls {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 9rem), 1fr));
  gap: .5rem;
  align-items: end;
}
.surface-calibrate { min-height: 2.4rem; max-width: 100%; justify-self: start; }
.smile-plot{display:block;width:100%;height:auto;min-height:180px;touch-action:none;user-select:none}
.smile-plot text{font-size:10px;fill:var(--muted)}
.smile-line{pointer-events:none}
.smile-drag-target{cursor:ns-resize;pointer-events:stroke}
.smile-handle{cursor:ns-resize;stroke:white;stroke-width:1.5}
.smile-cell{min-width:72px;padding:.25rem .35rem;font-variant-numeric:tabular-nums}
th,td{padding:.2rem .3rem}
.smile-row{cursor:pointer}
.smile-row-selector{display:block;width:100%;text-align:left;padding:.25rem;white-space:nowrap;font-weight:inherit}
.smile-row:hover,.active-row{background:var(--surface2)}
.active-row > th{box-shadow:inset 3px 0 var(--accent);color:var(--accent);font-weight:600}
</style>
