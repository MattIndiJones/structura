import { apiFetch, apiErrorMessage } from './api.js'
import { surfaceCalibrationKey } from './volSurface.js'

const pending=new WeakMap()
export async function calibrateUnderlying(u,model,horizon,rate) {
  if(!u.vol_surface || !['heston','sabr','lsv'].includes(model)) return
  if(u.smile_parameter_mode==='manual') return
  const key=surfaceCalibrationKey(u,model,horizon,rate)
  if(u.smile_calibration?.key===key && u.smile_calibration.status==='ready') return
  const existing=pending.get(u)
  if(existing?.key===key) return existing.promise
  u.smile_calibration={status:'loading',key,model}
  const promise=(async()=>{
    try {
      const response=await apiFetch('/api/volatility/calibrate',{method:'POST',
        headers:{'Content-Type':'application/json'},body:JSON.stringify({
          surface:u.vol_surface,model,horizon:Math.min(10,Number(horizon)||4),
          rate:Number(rate)/100,dividend:Number(u.q)/100,
        })})
      if(!response.ok) throw Error(apiErrorMessage(await response.json(),'Calibration refusée.'))
      const data=await response.json()
      if(surfaceCalibrationKey(u,model,horizon,rate)!==key)
        throw Error('La surface ou les paramètres ont changé pendant la calibration. Relancez le calcul.')
      for(const [name,value] of Object.entries(data.parameters)) u[name]=name==='kappa'?value:value*100
      u.smile_calibration={...data,status:'ready',model,
        key:surfaceCalibrationKey(u,model,horizon,rate)}
    } catch(e) {
      if(surfaceCalibrationKey(u,model,horizon,rate)===key) u.smile_calibration={status:'error',key,model,message:e.message}
      throw e
    } finally { if(pending.get(u)?.key===key) pending.delete(u) }
  })()
  pending.set(u,{key,promise})
  return promise
}
