import { describe,expect,it } from 'vitest'
import { radarAxes,radarScore } from './optimizerRadar.js'
import { payoffMode } from './optimizerPayoff.js'
import families from './__fixtures__/optimizerFamilies.json'
const result=(key,objective)=>{
  const payoff=payoffMode(families.find(f=>f.product_family===key),objective)
  return {payoff,request:{ranges:{maturity_months:{maximum:60}},constraints:{[payoff.solved_field.maximum_key]:payoff.solved_field.initial_maximum}}}
}
const metrics={coupon:.1,participation:.8,redemption_cap:1.3,probability_loss:.2,expected_maturity:2,protection_barrier:.6,probability_autocall:.7,expected_capital_loss:.05}
describe('Radar scales and financial directions',()=>{
  it('keeps identical scales for different selections and clips display without changing raw inputs',()=>{
    const r=result('autocall_athena','maximize_coupon'),high={...metrics,coupon:10}
    expect(radarAxes(r,[metrics])).toEqual(radarAxes(r,[high]))
    const axis=radarAxes(r,[high])[0]
    expect(radarScore(high.coupon,axis)).toBe(100);expect(high.coupon).toBe(10)
    expect(radarScore(.1,axis)).toBeCloseTo(.1/axis.max*100)
  })
  it('puts lower loss and protection barriers farther out, and shows explicit Q scales',()=>{
    const axes=radarAxes(result('autocall_athena','maximize_coupon'),[metrics])
    for(const key of ['probability_loss','protection_barrier','expected_maturity']){
      const axis=axes.find(a=>a.key===key)
      expect(radarScore(.1,axis)).toBeGreaterThan(radarScore(.5,axis))
    }
    expect(axes.find(a=>a.key==='expected_maturity')).toMatchObject({min:0,max:5,unit:'years'})
  })
  it('adapts solved axes to participation and redemption cap, omits unavailable metrics and recall on non-autocalls',()=>{
    for(const family of families.filter(f=>!f.has_autocall)){
      const r=result(family.product_family,family.objectives[0].value)
      const axes=radarAxes(r,[metrics,{...metrics,expected_maturity:null}])
      expect(axes[0].key).toBe(r.payoff.solved_field.key)
      expect(axes.some(a=>a.key==='probability_autocall')).toBe(false)
      expect(axes.some(a=>a.key==='expected_maturity')).toBe(false)
    }
    expect(radarAxes(null,[metrics])).toEqual([])
  })
})
