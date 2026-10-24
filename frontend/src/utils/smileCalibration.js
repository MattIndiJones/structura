import { apiFetch, apiErrorMessage } from './api.js'
import { surfaceCalibrationKey } from './volSurface.js'

const pending=new WeakMap()
export async function calibrateUnderlying(u,model,horizon,rate,context = () => ({ model, horizon, rate })) {
  if(!u.vol_surface || !['heston','sabr','lsv'].includes(model)) return
  if(u.smile_parameter_mode==='manual') return
  const key=surfaceCalibrationKey(u,model,horizon,rate)
  if(u.smile_calibration?.key===key && u.smile_calibration.status==='ready') return
  const existing=pending.get(u)
  if(existing?.key===key) return existing.promise
  const entry={key,promise:null}
  const isCurrent=()=>{
    const live=context()
    if(live.underlying && live.underlying!==u) return false
    return surfaceCalibrationKey(u,live.model,live.horizon,live.rate)===key
  }
  u.smile_calibration={status:'loading',key,model}
  const promise=(async()=>{
    try {
      const response=await apiFetch('/api/volatility/calibrate',{method:'POST',
        headers:{'Content-Type':'application/json'},body:JSON.stringify({
          surface:u.vol_surface,model,horizon:Number(horizon),
          rate:Number(rate)/100,dividend:Number(u.q)/100,
        })})
      if(!response.ok) throw Error(apiErrorMessage(await response.json(),'Calibration refusée.'))
      const data=await response.json()
      if(pending.get(u)!==entry) return false
      if(!isCurrent())
        throw Error('La surface ou les paramètres ont changé pendant la calibration. Relancez le calcul.')
      if(data.success!==true || data.qualified!==true || !data.calibration_evidence) {
        u.smile_calibration={...data,status:'unqualified',key,model}
        return false
      }
      for(const [name,value] of Object.entries(data.parameters)) u[name]=name==='kappa'?value:value*100
      u.calibration_evidence=data.calibration_evidence
      u.smile_calibration={...data,status:'ready',model,
        key:surfaceCalibrationKey(u,model,horizon,rate)}
      return true
    } catch(e) {
      if(pending.get(u)!==entry) return false
      if(isCurrent()) u.smile_calibration={status:'error',key,model,message:e.message}
      else if(u.smile_calibration?.key===key) u.smile_calibration={status:'stale',key,model,message:e.message}
      throw e
    } finally { if(pending.get(u)===entry) pending.delete(u) }
  })()
  entry.promise=promise
  pending.set(u,entry)
  return promise
}
