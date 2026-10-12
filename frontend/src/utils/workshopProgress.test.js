import { describe, it, expect } from 'vitest'
import { actionEvidence, usageProof, campaignRows, liveSummary, workflowSteps, actionOutcome } from './workshopProgress'

function fixture() {
  return {id:'a', status:'RUNNING', month:0, business_date:'2025-10-09', config:{months:12}, actions:[],
    actors:{hector:{name:'Hector',role:'issuer',registered:true,relations:{bnp:{status:'ACTIVE'},client:{status:'ACTIVE'}},deals:[]},
      bnp:{name:'BNP',role:'bank',registered:true,relations:{hector:{status:'ACTIVE'}},deals:[]},
      client:{name:'Élodie',role:'client',registered:true,relations:{hector:{status:'ACTIVE'}},deals:[]}},
    cases:{}, quotes:[], accepted:{}, client_offers:{},client_acceptances:[],book_checks:[]}
}
describe('workshop observability',()=>{
  it('does not let the selected campaign keep an obsolete RUNNING status in the list',()=>{
    const state={id:'a',status:'COMPLETED',turns:47,business_date:'2025-11-10'}
    const rows=[{id:'a',status:'RUNNING',turns:0},{id:'b',status:'DRAFT',turns:0}]
    expect(campaignRows(rows,state)).toEqual([{...state},rows[1]])
    expect(rows[0].status).toBe('RUNNING')
  })
  it('never presents a completed campaign as current IA activity, even with stale actor metadata',()=>{
    const state=fixture();state.status='COMPLETED';state.active_actor='bnp';state.activity={actor:'bnp',phase:'EXECUTING',tool:'quote'}
    expect(liveSummary(state)).toMatchObject({active:false,title:'Campagne terminée : aucun agent n’agit actuellement'})
    state.status='RUNNING';state.activity={actor:'bnp',phase:'THINKING'}
    expect(liveSummary(state).title).toContain('BNP réfléchit')
    expect(liveSummary(state).detail).toContain('Aucune nouvelle opération')
  })
  it('shows a disconnected controller instead of trusting a stale RUNNING record',()=>{
    const s={...fixture(),controller_active:false,activity:{actor:'bnp',phase:'THINKING'}}
    expect(liveSummary(s)).toMatchObject({active:false,title:'Aucun contrôleur actif : les IA ne poursuivent plus la campagne'})
    expect(campaignRows([{id:'a',status:'RUNNING'}],s)[0].displayStatus).toBe('Exécution non confirmée')
    const disconnected=campaignRows([{id:'a',status:'RUNNING'}],s)
    expect(campaignRows(disconnected,{...s,controller_active:true})[0].displayStatus).toBeUndefined()
  })
  it('distinguishes screenshots, real API activity, mail and wait without inventing browser usage',()=>{
    const actions=[{tool:'register',channel:'UI',result:{screenshot:'x.png'},http_calls:[{status:200}]},
      {tool:'book',channel:'API',http_calls:[{status:201},{status:200}]},
      {tool:'mail',channel:'MAIL',http_calls:[]},{tool:'wait',channel:'MAIL',http_calls:[]},
      {tool:'model',status:'FAILED',http_calls:[]}]
    expect(actions.map(a=>actionEvidence(a).label)).toEqual(['Écran + API','API Structura','Message interne','Attente','Preuve à examiner'])
    expect(usageProof({actions})).toEqual({screens:1,apiActions:2,calls:3,messages:1,waits:1,failures:1})
  })
  it('does not mark all responses received just because one bank quoted',()=>{
    const s=fixture();s.actors.ca={name:'CA',role:'bank',registered:true,relations:{hector:{status:'PENDING'}},deals:[]}
    s.actors.hector.relations.ca={status:'PENDING'}
    s.cases['CASE-001']={id:'CASE-001',month:0,nominal:1e7,rfq_sent:true,declines:[]}
    s.quotes=[{case_id:'CASE-001',bank:'bnp'}]
    let steps=workflowSteps(s).steps
    expect(steps[1]).toMatchObject({state:'warning',done:true})
    expect(steps[3]).toMatchObject({done:false,detail:'1 / 2 réponses · 1 prix'})
    s.cases['CASE-001'].declines=['ca'];steps=workflowSteps(s).steps
    expect(steps[3]).toMatchObject({done:true,detail:'2 / 2 réponses · 1 prix'})
    expect(steps[5].detail).toBe('0 / 4 écritures')
  })
  it('shows the all-refusal outcome without pretending a trade or lifecycle was booked',()=>{
    const s=fixture();s.cases.c={id:'c',month:0,nominal:1e7,rfq_sent:true,declines:['bnp'],outcome:'NO_QUOTE'}
    const steps=workflowSteps(s).steps
    expect(steps[4]).toMatchObject({skipped:true,detail:'Aucune banque ne cote'})
    expect(steps[5]).toMatchObject({skipped:true,done:false,detail:'Sans trade'})
    expect(steps[6]).toMatchObject({skipped:true,done:false})
  })
  it('requires the current native book review and settlement before showing lifecycle done',()=>{
    const s=fixture();s.actors.hector.deals=[{settlement_status:'PENDING'}];s.actors.hector.last_review={date:s.business_date,deals:1}
    expect(workflowSteps(s).steps[6].done).toBe(false)
    s.actors.hector.deals[0].settlement_status='SETTLED'
    expect(workflowSteps(s).steps[6].done).toBe(true)
    s.business_date='2025-11-10'
    expect(workflowSteps(s).steps[6].done).toBe(false)
  })
  it('uses a chosen historical case rather than the latest case for the displayed booking',()=>{
    const s=fixture();s.month=1;s.cases={a:{id:'a',month:0,nominal:1e7},b:{id:'b',month:1,nominal:1e7}};s.book_checks=[{case_id:'a',status:'COMPLETE',legs:4}]
    expect(workflowSteps(s).caseId).toBe('b')
    expect(workflowSteps(s,'a').steps[5]).toMatchObject({done:true,detail:'4 / 4 écritures'})
  })
  it('retains a native refusal and the exact issuer/deal identity in plain-language results',()=>{
    expect(actionOutcome({tool:'quote',status:'EXPECTED_REFUSAL',result:{error:'HTTP 422 Documentation absente'}},fixture())).toBe('HTTP 422 Documentation absente')
    expect(actionOutcome({tool:'book',args:{leg:'BANK_SELL'},result:{deal_reference:'BNPX-001',nominal:1e7,counterparty:'Maison Hector'}},fixture())).toContain('BNPX-001')
  })
})
