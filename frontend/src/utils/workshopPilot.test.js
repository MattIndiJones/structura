import { describe, it, expect } from 'vitest'
import { durationLabel, pilotSummary, timelinePage, matchedBankVolumes } from './workshopPilot'

const state=()=>({status:'RUNNING',controller_active:true,config:{months:12,max_turns:800},month:0,turns:12,actors:{},cases:{},book_checks:[]})

it('uses the diagnostic follow-up horizon instead of the former twelve-month scenario',()=>{
  const s=state();s.config.horizon_months=60;s.month=12
  expect(pilotSummary(s).percent).toBe(20)
})

describe('campaign pilot',()=>{
  it('keeps periods, refusals and reconciliation errors distinct',()=>{
    const s=state();s.month=2;s.book_checks=[{status:'COMPLETE'},{status:'NO_TRADE'},{status:'MISMATCH'},{status:'UNVERIFIED'}]
    expect(pilotSummary(s)).toMatchObject({percent:17,completed:1,refusals:1,uncertain:2,remaining:788})
  })
  it('does not propose restarting an exhausted campaign or silently change its budget',()=>{
    const s=state();s.status='ATTENTION';s.controller_active=false;s.turns=800
    expect(pilotSummary(s).action).toBe('configure')
    expect(s.config.max_turns).toBe(800)
    s.turns=799
    expect(pilotSummary(s).action).toBe('start')
    s.status='COMPLETED'
    expect(pilotSummary(s).action).toBe('')
  })
  it('explains an error pause separately from a user pause',()=>{
    const s=state();s.status='PAUSED';s.pause_reason='ERROR'
    expect(pilotSummary(s)).toMatchObject({action:'resume'})
    expect(pilotSummary(s).advice).toContain('plusieurs erreurs')
    s.pause_reason='USER'
    expect(pilotSummary(s).advice).not.toContain('erreurs')
  })
  it('finds old actions beyond the former 160-entry cutoff and preserves original numbering',()=>{
    const items=Array.from({length:181},(_,i)=>({actor:i%2?'bnp':'hector',args:{case_id:i<10?'CASE-001':'CASE-002'},result:{note:`Action ${i}`}}))
    expect(timelinePage(items,{page:8}).items.at(-1).journalIndex).toBe(0)
    expect(timelinePage(items,{actor:'bnp',caseId:'CASE-001'}).total).toBe(5)
    expect(timelinePage(items,{query:'Action 0'}).items[0].journalIndex).toBe(0)
    expect(items[0].journalIndex).toBeUndefined()
  })
  it('counts bank market shares only for complete client operations',()=>{
    const s=state();s.actors={bnp:{role:'bank',deals:[{leg:'BANK_SELL',case_id:'a',nominal:10},{leg:'BANK_SELL',case_id:'b',nominal:20}]},sg:{role:'bank',deals:[]}}
    s.book_checks=[{case_id:'a',status:'COMPLETE'},{case_id:'b',status:'MATCHED'}]
    expect(matchedBankVolumes(s)).toEqual({result:{bnp:10,sg:0},total:10})
  })
  it('formats cumulative real time without interpreting it as simulated months',()=>{
    expect(durationLabel(3661)).toBe('1 h 1 min')
    expect(durationLabel(65)).toBe('1 min 5 s')
  })
})
