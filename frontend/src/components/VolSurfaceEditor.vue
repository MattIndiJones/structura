<template>
  <section class="smile-editor mt-3 pt-3 border-t border-slate-700" aria-label="Surface de volatilité">
    <div class="flex flex-wrap items-end gap-2 mb-3">
      <div class="min-w-40"><label class="label">Profil de smile</label>
        <select class="select" :value="surface?.profile || ''" @change="selectProfile($event.target.value)" :disabled="busy">
          <option value="">Choisir la classe d’actif</option>
          <option value="equity">Actions</option><option value="index">Indices actions</option>
        </select>
      </div>
      <span v-if="surface" class="badge">{{ surface.mode === 'manual' ? 'Manuel' : 'Profil indicatif' }}</span>
      <button v-if="surface" class="btn text-xs" @click="resetProfile" :disabled="busy">Réinitialiser le profil</button>
      <button v-if="undo" class="btn text-xs" @click="restore" :disabled="busy">Annuler la modification</button>
    </div>
    <p v-if="!surface" class="text-xs text-slate-500">Sélectionnez un profil pour initialiser une surface indicative autour de la vol choisie. Les hypothèses existantes sont conservées tant que vous ne l’activez pas.</p>
    <template v-else>
      <p class="text-xs text-slate-500 mb-3">Hypothèse de smile, sans cotations d’options. Strikes en % du forward. σ ci-dessus correspond à l’ATM 1 an.
        {{ u.vol_level_source==='realized' ? 'Niveau repris de la volatilité réalisée chargée.' : '' }}</p>
      <div class="grid grid-cols-2 sm:grid-cols-4 gap-2 mb-2">
        <div><label class="label">Maturité active</label><select class="select" v-model.number="tenor" :disabled="busy">
          <option v-for="t in tenors" :key="t" :value="t">{{ tenorLabel(t) }}</option></select></div>
        <div><label class="label">Déplacement de courbe</label><select class="select" v-model="scope" :disabled="busy">
          <option value="one">Cette maturité</option><option value="all">Toutes les maturités</option></select></div>
        <div><label class="label">Asymétrie (%)</label><SensitiveValue mode="input"><input class="input" type="number" step="1" min="-99" max="99"
          :value="Number((surface.rho*100).toFixed(4))" @change="editShape('rho',Number($event.target.value)/100,$event)" :disabled="busy" /></SensitiveValue></div>
        <div><label class="label">Intensité du smile</label><SensitiveValue mode="input"><input class="input" type="number" step=".05" min="0" max="3"
          :value="Number(surface.eta.toFixed(5))" @change="editShape('eta',Number($event.target.value),$event)" :disabled="busy" /></SensitiveValue></div>
      </div>
      <SensitiveChart>
        <svg ref="svg" class="smile-plot" viewBox="0 0 680 255" role="img" aria-label="Smiles éditables par maturité"
          @pointermove="move" @pointerup="release" @pointercancel="cancel" @lostpointercapture="cancel">
          <g v-for="v in ticks" :key="v"><line x1="48" x2="662" :y1="y(v)" :y2="y(v)" stroke="var(--border)" />
            <text x="42" :y="y(v)+4" text-anchor="end">{{ demo.enabled ? '•••' : v.toFixed(1)+' %' }}</text></g>
          <g v-for="k in strikes" :key="k"><text :x="x(k)" y="242" text-anchor="middle">{{ Math.round(k*100) }} %</text></g>
          <path v-for="(t,i) in tenors" :key="t" :d="curve(t)" fill="none" :stroke="colors[i%colors.length]"
            :stroke-width="t===tenor?3:1.3" :opacity="t===tenor?1:.55" class="smile-line"
            :data-tenor="t" @pointerdown.stop.prevent="start($event,t)" />
          <circle v-for="k in strikes" :key="k" :cx="x(k)" :cy="y(vol(tenor,k))" r="5.5" class="smile-handle"
            :fill="colors[tenors.indexOf(tenor)%colors.length]" :data-strike="k"
            @pointerdown.stop.prevent="start($event,tenor,k)" />
          <text x="350" y="254" text-anchor="middle">Strike / forward</text>
        </svg>
      </SensitiveChart>
      <div class="flex flex-wrap gap-1 mb-2">
        <button v-for="(t,i) in tenors" :key="t" class="btn text-xs" :class="t===tenor?'font-bold':''"
          @click="tenor=t" :style="{color:colors[i%colors.length]}">{{ tenorLabel(t) }}</button>
      </div>
      <p class="text-[11px] text-slate-500 mb-2">Tirez une courbe pour changer son niveau ; utilisez les poignées pour modifier le smile. Asymétrie et intensité sont communes à la surface : une poignée d’aile peut modifier plusieurs maturités.</p>
      <div class="overflow-x-auto table-shell"><table class="w-full text-xs">
        <thead><tr><th class="text-left">Maturité</th><th v-for="k in strikes" :key="k" class="text-right">{{ k===1?'ATM':Math.round(k*100)+' %' }}</th></tr></thead>
        <tbody><tr v-for="t in tenors" :key="t" :class="t===tenor?'active-row':''">
          <td>{{ tenorLabel(t) }}</td><td v-for="k in strikes" :key="k">
            <SensitiveValue mode="input"><input class="input smile-cell text-right" type="number" step=".1" min=".01"
              :aria-label="`Vol ${tenorLabel(t)} strike ${Math.round(k*100)} %`" :value="Number(vol(t,k).toFixed(4))"
              @change="editNode(t,k,Number($event.target.value),$event)" :disabled="busy" /></SensitiveValue>
          </td></tr></tbody></table></div>
      <p v-if="busy" class="text-xs text-blue-500 mt-2">Validation de la surface…</p>
      <p v-if="message || u.smile_error" role="alert" class="text-xs text-amber-600 mt-2">{{ message || u.smile_error }}</p>
      <div v-if="needsCalibration" class="text-xs text-slate-500 mt-2" aria-live="polite">
        <span v-if="u.smile_parameter_mode==='manual'">Paramètres de modèle saisis manuellement ; la surface reste une cible de référence.
          <button class="btn text-xs ml-2" @click="recalibrate">Recalibrer sur la surface</button></span>
        <span v-else-if="fit?.status==='loading'">Recalibration {{ model==='sabr'?'SABR':'Heston' }} en cours…</span>
        <span v-else-if="fit?.status==='ready'">Ajustement indicatif {{ model==='sabr'?'SABR':model==='lsv'?'de la composante Heston du LSV':'Heston' }} : écart maximal vanille {{ demo.enabled ? '•••' : Number(fit.max_price_error_bp).toFixed(1) }} bps.
          {{ fit.success===false ? 'Optimisation non convergée. ' : '' }}Taux/dividende plats de référence ; paramètres constants. {{ horizon>10 ? 'Ajustement limité aux dix premières années.' : '' }}</span>
        <span v-else-if="fit?.status==='error'" class="text-amber-600">{{ fit.message }}</span>
        <span v-else>La nouvelle surface nécessite une recalibration.</span>
      </div>
      <p v-if="model==='constant'" class="text-xs text-slate-500 mt-2">Constant utilise σ ATM 1 an. La surface est conservée pour les modèles à smile.</p>
    </template>
  </section>
</template>

<script setup>
import { computed, ref, watch, onUnmounted } from 'vue'
import { useDemoModeStore } from '../stores/demoMode.js'
import { apiFetch, apiErrorMessage } from '../utils/api.js'
import { underlyingGroups } from '../data/commonUnderlyings.js'
import { SMILE_STRIKES, SMILE_PROFILES, cloneSurface, makeSurface, surfaceVol,
  validateSurface, shiftSurface, moveSurfaceNode, synchronizeSurfaceLevel, resizeSurfaceLevel, classifyUnderlying } from '../utils/volSurface.js'
import { calibrateUnderlying } from '../utils/smileCalibration.js'
import SensitiveChart from './SensitiveChart.vue'
import SensitiveValue from './SensitiveValue.vue'

const props=defineProps({u:{type:Object,required:true},model:{type:String,required:true},
  horizon:{type:Number,default:4},rate:{type:Number,default:3}})
const surface=computed(()=>props.u.vol_surface)
const demo=useDemoModeStore()
const tenors=computed(()=>surface.value?.atm_nodes.map(n=>n[0])||[])
const tenor=ref(1),scope=ref('one'),message=ref(''),undo=ref(null),busy=ref(false),svg=ref(null)
const strikes=SMILE_STRIKES,colors=['#356ca5','#946dba','#2d8c7e','#ce8b38','#be6068','#7279bb','#7d9460','#777777']
const needsCalibration=computed(()=>surface.value&&['heston','sabr','lsv'].includes(props.model))
const fit=computed(()=>props.u.smile_calibration)
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
const x=k=>48+(k-.6)/.8*614
const y=v=>220-(v-bounds.value[0])/(bounds.value[1]-bounds.value[0])*205
const curve=t=>Array.from({length:81},(_,i)=>{const k=.6+i*.01;return`${i?'L':'M'}${x(k)},${y(vol(t,k))}`}).join(' ')

function scheduleCalibration() {
  clearTimeout(timer)
  if(drag||busy.value||!needsCalibration.value)return
  timer=setTimeout(()=>calibrateUnderlying(props.u,props.model,props.horizon,props.rate).catch(()=>{}),600)
}
watch(()=>JSON.stringify([surface.value,props.model,props.horizon,props.rate,props.u.q]),scheduleCalibration,{immediate:true})
watch(()=>props.u,()=>{undo.value=null;message.value='';revision++;busy.value=false;cancel()})
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
  message.value=''
  try {
    validateSurface(candidate);busy.value=true
    const response=await apiFetch('/api/volatility/validate',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({surface:candidate})})
    const result=await response.json()
    if(current!==revision||u!==props.u)return
    if(!response.ok)throw Error(apiErrorMessage(result,'Surface refusée.'))
    undo.value=previous;u.vol_surface=result.surface;synchronizeSurfaceLevel(u);u.smile_error=null
    if(result.surface.mode==='manual')u.vol_level_source='manual'
    u.smile_parameter_mode='automatic'
    return true
  } catch(e) {
    if(current===revision&&u===props.u){u.vol_surface=previous;if(previous)synchronizeSurfaceLevel(u);message.value=e.message}
    return false
  } finally {if(current===revision){busy.value=false;scheduleCalibration()}}
}
async function selectProfile(profile) {
  if(!profile)return
  if(await commit(makeSurface(profile,props.u.sigma,props.horizon))) {
    props.u.asset_class=profile;props.u._smileDefaults=false
  }
}
function resetProfile(){commit(makeSurface(surface.value.profile,props.u.sigma,props.horizon))}
function recalibrate(){props.u.smile_parameter_mode='automatic';props.u.smile_calibration=null;scheduleCalibration()}
function restore(){if(undo.value){const before=undo.value;undo.value=null;commit(before)}}
async function editShape(field,value,event){const s=cloneSurface(surface.value);s[field]=value;s.mode='manual';await commit(s);event.target.value=field==='rho'?surface.value.rho*100:surface.value.eta}
async function editNode(t,k,value,event){
  try{await commit(moveSurfaceNode(surface.value,t,k,value));event.target.value=vol(t,k).toFixed(4)}
  catch(e){message.value=e.message;event.target.value=vol(t,k).toFixed(4)}
}
function start(event,t,strike=null){
  if(busy.value||drag)return
  tenor.value=t;clearTimeout(timer)
  drag={u:props.u,id:event.pointerId,start:event.clientY,surface:cloneSurface(surface.value),bounds:[...naturalBounds.value],
    t,strike,failed:false,sigma:props.u.sigma}
  svg.value.setPointerCapture(event.pointerId)
}
function move(event){
  if(!drag||event.pointerId!==drag.id)return
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
  if(d.failed){props.u.vol_surface=d.surface;props.u.sigma=d.sigma;scheduleCalibration();return}
  commit(cloneSurface(surface.value),d.surface)
}
function cancel(){if(drag){drag.u.vol_surface=drag.surface;drag.u.sigma=drag.sigma;drag=null;scheduleCalibration()}}
onUnmounted(()=>{revision++;cancel();clearTimeout(timer)})
</script>

<style scoped>
.smile-plot{display:block;width:100%;height:auto;min-height:180px;touch-action:none;user-select:none}
.smile-plot text{font-size:10px;fill:var(--muted)}
.smile-line{cursor:ns-resize;pointer-events:stroke}
.smile-handle{cursor:ns-resize;stroke:white;stroke-width:1.5}
.smile-cell{min-width:72px;padding:.25rem .35rem;font-variant-numeric:tabular-nums}
th,td{padding:.2rem .3rem}
.active-row{background:var(--surface2)}
</style>
