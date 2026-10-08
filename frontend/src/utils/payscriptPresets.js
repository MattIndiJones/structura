import presets from '../data/payscriptPresets.json'
import { productModels, buildModelCalendars, addMonthsIso } from './productModels.js'
import { tenorPair, tenorString, parameterValues } from './payscriptEconomics.js'
import { apiFetch, apiErrorMessage } from './api.js'

export const payscriptPresets = presets.map(p => ({ ...p,
  group: productModels.find(m => m.key===p.model_key)?.family,
}))
export function localTodayIso() {
  const now=new Date(), pad=n=>String(n).padStart(2,'0')
  return `${now.getFullYear()}-${pad(now.getMonth()+1)}-${pad(now.getDate())}`
}

// Resolve every proposed date before changing a session. The selected example
// explicitly supplies Following/J+3, never changes global calendar defaults.
export async function preparePreset(key, { startDate, currency='EUR' }, fetcher=apiFetch) {
  const preset=payscriptPresets.find(p=>p.key===key)
  const model=productModels.find(m=>m.key===preset?.model_key)
  if (!model || !/^\d{4}-\d{2}-\d{2}$/.test(startDate||'')) throw Error('Choisissez un exemple et une date de départ valide.')
  async function post(url, body) {
    const response=await fetcher(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})
    const data=await response.json()
    if (!response.ok) throw Error(apiErrorMessage(data,'Préparation de l’exemple refusée.'))
    return data
  }
  const initial=await post('/api/calendar/resolve',{date:startDate,currency,convention:'following',business_days:0})
  const plan=buildModelCalendars(model,{strikeDate:initial.date,tenorCode:preset.tenor})
  const constats=plan.constats, observations=[]
  let maturity='', payment=''
  for (const [name, spec] of Object.entries(model.constats)) {
    const value=constats[name]
    if (spec.role==='initial_fixing') continue
    value.convention='following'; value.settlement_lag=3
    if (spec.role==='observations') {
      value.frequency=tenorPair(preset.frequency||spec.frequency)
      const freq=value.frequency
      value.first_observation_date=addMonthsIso(initial.date,freq.value*(freq.unit==='Y'?12:1))
      const resolved=await post('/api/schedule/generate',{
        ...value,frequency:tenorString(freq),currency,
      })
      if (!resolved.dates?.length) throw Error('L’exemple ne produit aucune observation.')
      observations.push(...resolved.dates)
      maturity=resolved.dates.at(-1); payment=resolved.payment_dates.at(-1)
      // The final observation is the effective date shown in Economics/RFQ.
      // The generator deduplicates a rolled final stub against the last roll.
      value.end_date=maturity
    } else {
      const observed=await post('/api/calendar/resolve',{date:value.date,currency,convention:'following',business_days:0})
      value.date=observed.date; maturity=observed.date
      payment=(await post('/api/calendar/resolve',{date:maturity,currency,convention:'none',business_days:3})).date
      observations.push(maturity)
    }
  }
  const data=await post('/api/parse',{script:model.script})
  if (!data.ok) throw Error((data.errors||['Script invalide.']).join('\n'))
  if (data.params.length!==Object.keys(preset.params).length || data.params.some(p=>!Object.hasOwn(preset.params,p.name)))
    throw Error('Les paramètres de cet exemple ne correspondent plus au modèle.')
  parameterValues(data.params,preset.params)
  return { preset, model, currency, requestedStartDate:startDate, strikeDate:initial.date,
    maturityDate:maturity, paymentDate:payment, observations, constats,
    params:structuredClone(preset.params), validation:{script:model.script,data},
    T:(Date.parse(maturity)-Date.parse(initial.date))/(365.25*86400000) }
}
