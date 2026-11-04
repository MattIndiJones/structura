import { apiFetch, apiErrorMessage } from './api.js'
import { hasExplicitHestonFit, hestonFitOptions, surfaceCalibrationKey, surfaceVol } from './volSurface.js'

const pending=new WeakMap()

export function explicitHestonCalibration(u, horizon, rate) {
  if (u.smile_parameter_mode === 'manual') return null
  const key = surfaceCalibrationKey(u, 'heston', horizon, rate)
  const evidence = u.calibration_evidence
  const dossier = evidence?.dossier
  const same = (a, b) => Math.abs(a-b) <= 1e-10
  if (!evidence?.server_signature || !dossier?.qualification?.qualified || dossier.model !== 'heston'
      || !dossier.target || !u.vol_surface || !dossier.context || !dossier.parameters
      || !same(dossier.context.rate, Number(rate)/100)
      || !same(dossier.context.dividend, Number(u.q)/100)
      || !(dossier.target.atm_scenario
        ? horizon > 0 && horizon <= dossier.context.fit_horizon
        : same(horizon, dossier.context.fit_horizon) && same(horizon, dossier.context.requested_horizon))
      || Math.abs(Number(u.sigma)/100-surfaceVol(u.vol_surface, 1)/100) > 5.1e-9
      || Object.keys(dossier.target).some(field =>
        JSON.stringify(dossier.target[field]) !== JSON.stringify(u.vol_surface?.[field]))
      || Object.entries(dossier.parameters).some(([field, value]) =>
        !same(field === 'kappa' ? u[field] : u[field]/100, value))) return null
  return { status:'ready', key, success:true, dossier, qualification:dossier.qualification,
    parameters:dossier.parameters, calibration_evidence:evidence,
    max_price_error_bp:dossier.controls.max_vanilla_error_bp,
    max_digital_error_bp:dossier.controls.max_digital_error_bp }
}
export async function calibrateUnderlying(u,model,horizon,rate,context = () => ({ model, horizon, rate }), {
  explicit = false,
} = {}) {
  if(!u.vol_surface || !['heston','sabr','lsv'].includes(model)) return
  if(u.smile_parameter_mode==='manual' && !explicit) return
  const fitHorizon = model === 'heston' && u.vol_surface.atm_scenario && horizon <= 10 ? 10 : horizon
  const key=surfaceCalibrationKey(u,model,horizon,rate)
  const scenario = hasExplicitHestonFit(u, model)
  const hestonFit = explicit && scenario ? hestonFitOptions(u) : null
  const signedFit = scenario ? explicitHestonCalibration(u, horizon, rate) : null
  if (signedFit?.status === 'ready' && (!hestonFit || signedFit.dossier.heston_fit?.mode === hestonFit.mode)) {
    u.smile_calibration = signedFit
    return true
  }
  if(u.smile_calibration?.key===key && u.smile_calibration.status==='ready' && !hestonFit) return
  const existing=pending.get(u)
  if(existing?.key===key && existing.explicit===explicit) return existing.promise
  const entry={key,explicit,promise:null}
  const isCurrent=()=>{
    const live=context()
    if(live.underlying && live.underlying!==u) return false
    return surfaceCalibrationKey(u,live.model,live.horizon,live.rate)===key
  }
  u.smile_calibration={status:'loading',key,model,explicit}
  const promise=(async()=>{
    try {
      const response=await apiFetch('/api/volatility/calibrate',{method:'POST',
        headers:{'Content-Type':'application/json'},body:JSON.stringify({
          surface:u.vol_surface,model,horizon:Number(fitHorizon),
          rate:Number(rate)/100,dividend:Number(u.q)/100,
          ...(hestonFit ? { heston_fit: hestonFit } : {}),
        })})
      if(!response.ok) throw Error(apiErrorMessage(await response.json(),'Calibration refusée.'))
      const data=await response.json()
      if(pending.get(u)!==entry) return false
      if(!isCurrent())
        throw Error('La surface ou les paramètres ont changé pendant la calibration. Relancez le calcul.')
      if (hestonFit && data.dossier?.heston_fit?.mode !== hestonFit.mode)
        throw Error('Le serveur n’a pas confirmé le mode de calibration demandé. Relancez Structura et réessayez.')
      if(data.success!==true || data.qualified!==true || !data.calibration_evidence) {
        u.smile_calibration={...data,status:'unqualified',key,model,explicit}
        return false
      }
      if (hestonFit) {
        u.smile_calibration = {...data,status:'candidate',model,key}
      } else {
        applyFit(u, data, model, horizon, rate)
      }
      return true
    } catch(e) {
      if(pending.get(u)!==entry) return false
      if(isCurrent()) u.smile_calibration={status:'error',key,model,explicit,message:e.message}
      else if(u.smile_calibration?.key===key) u.smile_calibration={status:'stale',key,model,message:e.message}
      throw e
    } finally { if(pending.get(u)===entry) pending.delete(u) }
  })()
  entry.promise=promise
  pending.set(u,entry)
  return promise
}

function applyFit(u, fit, model, horizon, rate) {
  for (const [name, value] of Object.entries(fit.parameters)) u[name] = name === 'kappa' ? value : value*100
  u.calibration_evidence = fit.calibration_evidence
  u.smile_calibration = {...fit,status:'ready',model,key:surfaceCalibrationKey(u,model,horizon,rate)}
}

export function applyHestonCalibration(u, horizon, rate) {
  const fit = u.smile_calibration
  if (fit?.status !== 'candidate' || fit.key !== surfaceCalibrationKey(u, 'heston', horizon, rate)) return false
  u.smile_parameter_mode = 'automatic'
  applyFit(u, fit, 'heston', horizon, rate)
  return true
}

export async function fitAndApplyHeston(u, horizon, rate, context) {
  const fitted = await calibrateUnderlying(u, 'heston', horizon, rate, context, { explicit: true })
  const live = context()
  if (!fitted || live.underlying !== u || live.model !== 'heston') return false
  return applyHestonCalibration(u, live.horizon, live.rate)
    || explicitHestonCalibration(u, live.horizon, live.rate)?.dossier.heston_fit?.mode === hestonFitOptions(u).mode
}
