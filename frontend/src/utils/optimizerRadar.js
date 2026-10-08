/** Fixed, disclosed scales for a single frozen research, independent of selection. */
export function radarAxes(result,candidates) {
  const family=result?.payoff,req=result?.request
  if(!family || !req) return []
  const solved=family.solved_field
  const maximum=req.constraints[solved.maximum_key] ?? solved.maximum
  const axes=[{key:solved.key,label:solved.label,min:0,max:maximum,unit:'pct',reverse:false},
    {key:'probability_loss',label:'Probabilité de perte Q',min:0,max:1,unit:'pct',reverse:true},
    {key:'expected_maturity',label:'Durée moyenne Q',min:0,max:req.ranges.maturity_months.maximum/12,unit:'years',reverse:true}]
  if(family.range_fields.some(f=>f.key==='protection_barrier')) axes.push({key:'protection_barrier',label:'Barrière de protection',min:0,max:1,unit:'pct',reverse:true})
  if(family.has_autocall) axes.push({key:'probability_autocall',label:'Rappel anticipé Q',min:0,max:1,unit:'pct',reverse:false})
  if(family.risk_severity) axes.push({key:'expected_capital_loss',label:'Perte en capital moyenne Q',min:0,max:1,unit:'pct',reverse:true})
  return axes.filter(axis=>axis.max>axis.min && candidates.every(c=>typeof c[axis.key]==='number' && Number.isFinite(c[axis.key])))
}
export function radarScore(value,axis) {
  const level=(value-axis.min)/(axis.max-axis.min)
  return Math.max(0,Math.min(100,(axis.reverse?1-level:level)*100))
}
