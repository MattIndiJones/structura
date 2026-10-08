import { describe, expect, it } from 'vitest'
import { diagnosticCandidates, diagnosticFindings, diagnosticStatus, pricingTarget } from './optimizerDiagnostics.js'
import { rankedCandidates } from './productOptimizer.js'

const candidate=(id,coupon,status='REJECTED')=>({candidate_id:id,coupon,fair_value:1,pricing_status:'PRICED',constraint_status:status,
  validation_status:status==='PASS'?'PASSED':'NOT_SELECTED',probability_loss:.2,protection_barrier:.6,errors:[],rejection_details:[]})
const result=candidates=>({candidates,request:{objective:'maximize_coupon',product_family:'autocall_athena',constraints:{target_price:1,price_tolerance:.005},economics:{upfront_fees:.01,structuring_margin:.02}},validation:{selected:0}})

describe('Optimizer pricing diagnostics',()=>{
  it('shows the best calculated coupons even with zero admissible structures and keeps recommendations strict',()=>{
    const data=result([candidate('C1',.07),candidate('C2',.11),candidate('C3',.09)])
    expect(diagnosticCandidates(data).map(c=>c.candidate_id)).toEqual(['C2','C3','C1'])
    expect(rankedCandidates(data)).toEqual([])
    expect(data.candidates.map(c=>c.candidate_id)).toEqual(['C1','C2','C3'])
  })
  it('does not hide a more favourable rejected coupon behind an admissible one',()=>{
    const data=result([candidate('GOOD',.07,'PASS'),candidate('OUT',.11)])
    expect(diagnosticCandidates(data).map(c=>c.candidate_id)).toEqual(['OUT','GOOD'])
    expect(diagnosticStatus(data.candidates[0]).tone).toBe('good')
    expect(diagnosticStatus(data.candidates[1]).tone).toBe('bad')
  })
  it('never colours missing or failed validation green',()=>{
    const pending={...candidate('P',.08,'PASS'),validation_status:'PENDING'}
    expect(diagnosticStatus(pending).tone).toBe('pending')
    expect(diagnosticStatus({...pending,validation_status:'FAILED'}).label).toContain('Erreur')
    expect(diagnosticStatus({...pending,constraint_status:'REJECTED',validation_status:'PASSED'}).tone).toBe('bad')
  })
  it('uses the requested participation, cap and protection objectives',()=>{
    const rows=[{...candidate('A',.08),participation:1.3,redemption_cap:1.4,protection_barrier:.7},
      {...candidate('B',.12),participation:1.1,redemption_cap:1.6,protection_barrier:.5}]
    const data=result(rows)
    data.request.objective='maximize_participation'
    expect(diagnosticCandidates(data,{solved_field:{key:'participation'}})[0].candidate_id).toBe('A')
    data.request.objective='maximize_cap'
    expect(diagnosticCandidates(data,{solved_field:{key:'redemption_cap'}})[0].candidate_id).toBe('B')
    data.request.objective='target_coupon'
    expect(diagnosticCandidates(data)[0].candidate_id).toBe('B')
    data.request.product_family='autocall_gear_put';rows[0].expected_capital_loss=.03;rows[1].expected_capital_loss=.06
    expect(diagnosticCandidates(data)[0].candidate_id).toBe('A')
  })
  it('does not invent prices for failed or skipped structures',()=>{
    const data=result([{...candidate('FAIL',.1),pricing_status:'FAILED'}, {...candidate('SKIP',.1),pricing_status:'SKIPPED'},
      {...candidate('NAN',.1),fair_value:NaN}])
    expect(diagnosticCandidates(data)).toEqual([])
  })
  it('explains a central price inside tolerance with a confidence interval outside it',()=>{
    const c=candidate('MC',.1)
    c.rejection_details=[{category:'MC_UNCERTAINTY',metric:'fair_value',label:'Intervalle hors tolérance',estimate:1,
      interval:[.992,1.008],target:1,tolerance:.005}]
    const finding=diagnosticFindings(c,result([c]))[0]
    expect(finding.reason).toContain('99,20 % – 100,80 %')
    expect(finding.reason).toContain('99,50 % – 100,50 %')
    expect(finding.action).toContain('0,80 points')
    expect(finding.action).toContain('augmenter les simulations')
    expect(diagnosticStatus(c).label).toContain('incertitude Monte-Carlo')
  })
  it('shows a hard risk breach with the direction and magnitude of the required bound',()=>{
    const c=candidate('RISK',.1)
    c.rejection_details=[{category:'HARD_CONSTRAINT',metric:'probability_autocall',label:'Rappel Q',estimate:.6,bound:.55,limit:.7,gap:.15,unit:'fraction'}]
    const finding=diagnosticFindings(c,result([c]))[0]
    expect(finding.reason).toContain('minimum 70,00 %')
    expect(finding.reason).toContain('écart 15,00 %')
    expect(finding.action).toContain('au plus égal à 55,00 %')
  })
  it('distinguishes endpoint prices from a solved quote and calculation errors from economic rejections',()=>{
    const c={...candidate('SKIP',null),pricing_status:'SKIPPED',rejection_details:[{
      category:'PRICE_TARGET',label:'Cible inaccessible',target:1,endpoint_prices:[.8,.95]}]}
    const finding=diagnosticFindings(c,result([c]))[0]
    expect(finding.reason).toContain('80,00 % / 95,00 %')
    expect(finding.action).toContain('bornes')
    const failed={...c,errors:['Erreur moteur']}
    expect(diagnosticFindings(failed,result([failed]))[0].action).toContain('journaux')
  })
  it('computes the net payoff target from the frozen economics',()=>{
    expect(pricingTarget(result([]))).toBeCloseTo(.97)
    expect(pricingTarget({...result([]),economics:{pricing_target:.98}})).toBe(.98)
  })
})
