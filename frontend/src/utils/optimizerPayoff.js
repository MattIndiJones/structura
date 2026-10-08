/** Only fields declared by the selected server-side script adapter are sent. */
export function payoffMode(family, objective) {
  if (!family) return null
  const selected=family.objectives.some(item=>item.value===objective)?objective:family.objectives[0].value
  return {...family,...family.modes[selected],objective:selected}
}

export function payoffState(family, previousRanges = {}) {
  return {
    ranges:Object.fromEntries(family.range_fields.map(field=> {
      const factor=field.unit === 'fraction' ? 100 : 1
      const initial=field.initial*factor
      const previous=previousRanges[field.key]
      const reusable=previous && previous.minimum>=field.minimum*factor && previous.maximum<=field.maximum*factor
      return [field.key, reusable ? previous : {minimum:initial,maximum:field.key==='maturity_months'?60:initial,step:field.key==='maturity_months'?12:field.unit==='multiple'?field.step:5}]
    })),
    settings:Object.fromEntries(family.fixed_fields.map(field=>[field.key,field.initial*(field.unit==='fraction'?100:1)])),
  }
}

export function solutionPayload(family, minimum, maximum) {
  const field=family.solved_field
  if (![minimum,maximum].every(value=>typeof value==='number' && Number.isFinite(value)) || minimum>=maximum)
    throw Error('Les bornes du paramètre résolu sont incohérentes.')
  return {[field.minimum_key]:minimum/100,[field.maximum_key]:maximum/100}
}

export function payoffMetrics(family) {
  if(!family) return []
  const fields=[...family.range_fields,...family.fixed_fields.filter(field=>field.key==='participation'),family.solved_field]
  return fields.map(field=>({key:field.key,label:field.label,unit:field.unit==='fraction'?'pct':field.unit}))
}

export function payoffPayload(family, ranges, settings, observations) {
  if(!family || family.status !== 'SUPPORTED') throw Error('Choisissez un script qualifié pour l’Optimizer.')
  const converted={}
  for(const field of family.range_fields) {
    const range=ranges[field.key]
    if(!range || Object.values(range).some(value=>typeof value !== 'number' || !Number.isFinite(value)))
      throw Error(`Renseignez les bornes de ${field.label}.`)
    const divisor=field.unit === 'fraction'?100:1
    converted[field.key]=Object.fromEntries(Object.entries(range).map(([key,value])=>[key,Number((value/divisor).toFixed(12))]))
  }
  if(family.has_autocall) {
    if(!observations.length || observations.some(value=>!family.observation_months.includes(value)))
      throw Error('Choisissez une fréquence de constatation autorisée pour ce script.')
    converted.observation_months=[...observations]
  }
  const effective={}
  for(const field of family.fixed_fields) {
    const value=settings[field.key]
    if(typeof value !== 'number' || !Number.isFinite(value)) throw Error(`Renseignez ${field.label}.`)
    effective[field.key]=value/(field.unit==='fraction'?100:1)
  }
  return {product_family:family.product_family,ranges:converted,payoff_settings:effective}
}
