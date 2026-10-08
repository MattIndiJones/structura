import { describe, expect, it } from 'vitest'
import families from './__fixtures__/optimizerFamilies.json'
import { payoffState, payoffPayload, payoffMode, solutionPayload, payoffMetrics } from './optimizerPayoff.js'
import { searchSize } from './productOptimizer.js'

describe('Script-owned optimizer fields',()=>{
  it('preserves decimal endpoints after display-percent conversion',()=>{
    const family=families.find(f=>f.product_family==='phoenix'),state=payoffState(family)
    state.ranges.protection_barrier={minimum:59.3,maximum:59.6,step:.1}
    const payload=payoffPayload(family,state.ranges,state.settings,[3])
    expect(payload.ranges.protection_barrier).toEqual({minimum:.593,maximum:.596,step:.001})
    expect(searchSize(payload.ranges)).toBe(12)
  })
  it('every default fixed value belongs to its native input step grid',()=>{
    for(const family of families) for(const mode of Object.values(family.modes)) for(const field of mode.fixed_fields) {
      const steps=(field.initial-field.minimum)/field.step
      expect(Math.abs(steps-Math.round(steps))).toBeLessThan(1e-8)
    }
  })
  it('switches booster objective between solving PART and solving CAP without stale axes',()=>{
    const base=families.find(f=>f.product_family==='booster')
    const participation=payoffMode(base,'maximize_participation'), first=payoffState(participation)
    expect(first.ranges.redemption_cap.minimum).toBe(130)
    expect(solutionPayload(participation,0,300)).toEqual({participation_minimum:0,participation_maximum:3})
    const cap=payoffMode(base,'maximize_cap'), second=payoffState(cap,first.ranges)
    const payload=payoffPayload(cap,second.ranges,second.settings,[3])
    expect(payload.ranges).not.toHaveProperty('redemption_cap')
    expect(payload.ranges).not.toHaveProperty('observation_months')
    expect(payload.payoff_settings).toEqual({participation:1.5})
    expect(solutionPayload(cap,101,200)).toEqual({cap_minimum:1.01,cap_maximum:2})
    expect(payoffMetrics(cap).map(f=>f.key)).toEqual(['maturity_months','participation','redemption_cap'])
    expect(payoffMode(base,'maximize_coupon').objective).toBe('maximize_participation')
  })
  it('keeps gearing in multiples and gear coupon as a unique contractual amount',()=>{
    const family=payoffMode(families.find(f=>f.product_family==='autocall_gear_put'),'maximize_coupon')
    const state=payoffState(family)
    expect(state.ranges.gearing).toEqual({minimum:2,maximum:2,step:.1})
    const payload=payoffPayload(family,state.ranges,state.settings,[3])
    expect(payload.ranges.gearing.minimum).toBe(2)
    expect(payload.ranges.put_strike.minimum).toBe(.6)
    expect(payload.ranges).not.toHaveProperty('protection_barrier')
    expect(family.solved_field.value_convention).toBe('total')
  })
  it('adds coupon barrier only for Phoenix and removes recall axes for reverse convertible',()=>{
    const athena=families.find(f=>f.product_family==='autocall_athena')
    const phoenix=families.find(f=>f.product_family==='phoenix')
    const reverse=families.find(f=>f.product_family==='reverse_convertible')
    const initial=payoffState(athena)
    const conditional=payoffState(phoenix,initial.ranges)
    expect(conditional.ranges.coupon_barrier.minimum).toBe(70)
    conditional.ranges.coupon_barrier.maximum=80
    const request=payoffPayload(phoenix,conditional.ranges,conditional.settings,[3])
    expect(request.ranges.coupon_barrier).toEqual({minimum:.7,maximum:.8,step:.05})
    expect(searchSize(request.ranges)).toBe(9)
    const terminal=payoffState(reverse,conditional.ranges)
    expect(Object.keys(terminal.ranges)).toEqual(['maturity_months','protection_barrier'])
    const payload=payoffPayload(reverse,conditional.ranges,{decrement:5},[3,6])
    expect(payload.ranges.autocall_trigger).toBeUndefined()
    expect(payload.ranges.coupon_barrier).toBeUndefined()
    expect(payload.ranges.observation_months).toBeUndefined()
    expect(payload.payoff_settings).toEqual({})
    expect(searchSize(payload.ranges)).toBe(3)
  })
  it('converts only percentage settings and keeps observation rank as an integer unit',()=>{
    const family=families.find(f=>f.product_family==='autocall_barriere_degressive')
    const state=payoffState(family)
    const request=payoffPayload(family,state.ranges,state.settings,[3])
    expect(request.payoff_settings).toEqual({decrement:.025,floor:.8,first_decrease_rank:2})
    expect(request.product_family).toBe(family.product_family)
  })
  it('missing required values block rather than becoming zero or silently disappearing',()=>{
    const family=families.find(f=>f.product_family==='phoenix_memoire')
    const state=payoffState(family)
    state.ranges.coupon_barrier.minimum=null
    expect(()=>payoffPayload(family,state.ranges,{},[3])).toThrow('Barrière coupon')
    expect(()=>payoffPayload(null,{}, {},[3])).toThrow('script qualifié')
    const valid=payoffState(family)
    expect(()=>payoffPayload(family,valid.ranges,{},[])).toThrow('fréquence')
  })
})
