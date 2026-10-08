import { describe,expect,it } from 'vitest'
import { researchOutcome } from './optimizerOutcome.js'
const priced=(id,status='PASS',validation='NOT_SELECTED')=>({candidate_id:id,pricing_status:'PRICED',constraint_status:status,validation_status:validation,fair_value:.965})
const rejected=id=>({...priced(id,'REJECTED','REJECTED'),fair_value:.966643,
  validation:{runs:[{},{}],exploration:{constraint_status:'PASS'}},
  rejection_details:[{category:'MC_UNCERTAINTY',metric:'fair_value',estimate:.966643,interval:[.961271,.972015],target:.965,tolerance:.005}]})
const record=(status,candidates,extra={})=>({status,progress:{phase:'exploration',completed:23,total:75},request:{search:{simulations:4000}},result:{candidates,validation:extra}})
describe('Provisional versus final research outcomes',()=>{
  it('does not call an ongoing exploration a failed search, counts provisional solutions and does not request another job',()=>{
    const outcome=researchOutcome(record('RUNNING',[priced('P1'),priced('P2'),rejected('R1')]))
    expect(outcome.title).toContain('Exploration en cours')
    expect(outcome.admissible).toBe(3)
    expect(outcome.text).toContain('validation indépendante')
    expect(outcome.title).not.toContain('Aucune')
    expect(outcome.nextSimulations).toBeNull()
  })
  it('explains all five failed holdouts and thirty untested provisional solutions, preserving statistical limits',()=>{
    const candidates=[...Array.from({length:5},(_,i)=>rejected(`C${i}`)),...Array.from({length:30},(_,i)=>priced(`P${i}`))]
    const outcome=researchOutcome(record('COMPLETED',candidates,{exploration_admissible:35,selected:5,complete:true}))
    expect(outcome).toMatchObject({admissible:35,confirmed:0,checked:5,untested:30,precisionOnly:true,nextSimulations:16000,tone:'pending'})
    expect(outcome.title).toContain('précision Monte-Carlo insuffisante')
    expect(outcome.example).toContain('96,66 %');expect(outcome.example).toContain('96,00 % – 97,00 %')
    expect(outcome.example).toContain('contrôle simultané')
    expect(candidates.every(c=>c.validation_status!=='PASSED')).toBe(true)
  })
  it('does not treat hard economic rejection or a technical failure as a lack of precision',()=>{
    const c=rejected('HARD');c.rejection_details[0].category='PRICE_TARGET'
    expect(researchOutcome(record('COMPLETED',[c])).precisionOnly).toBe(false)
    c.validation_status='FAILED';c.errors=['Erreur moteur']
    expect(researchOutcome(record('FAILED',[c])).nextSimulations).toBeNull()
  })
  it('reports validation progress separately and confirms only genuinely passed controls',()=>{
    const data=record('RUNNING',[priced('GOOD','PASS','PASSED'),priced('PENDING','PASS','PENDING')],{selected:2})
    data.progress={phase:'validation',total:2}
    expect(researchOutcome(data)).toMatchObject({confirmed:1,checked:1})
    expect(researchOutcome(data).title).toContain('1 / 2')
    data.status='PARTIAL';data.result.complete=false
    expect(researchOutcome(data).text).toContain('Couverture partielle')
  })
  it('keeps the simulation suggestion within supported bounds and never launches from the diagnostic',()=>{
    const data=record('COMPLETED',[rejected('R')]);data.request.search.simulations=16000
    expect(researchOutcome(data).nextSimulations).toBe(20000)
    data.request.search.simulations=20000
    expect(researchOutcome(data).nextSimulations).toBeNull()
  })
})
