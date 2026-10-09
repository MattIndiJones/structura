import { describe, expect, it } from 'vitest'
import { campaignIssues, issueReport } from './workshopIssues'
const state=()=>({id:'a',config:{name:'Partie'},business_date:'2025-10-08',actors:{bnp:{name:'BNP'},client:{name:'Élodie'}},actions:[],incidents:[]})
describe('workshop problem register',()=>{
  it('links repeated errors to their exact occurrence and preserves their original message',()=>{
    const s=state();s.actions=[0,1].map(()=>({actor:'bnp',tool:'api',status:'FAILED',args:{path:'/api/missing'},result:{error:'HTTP 404 route introuvable'},http_calls:[{path:'/api/missing',method:'GET',status:404}]}))
    s.incidents=[0,1].map(i=>({id:String(i),actor:'bnp',kind:'TO_DIAGNOSE',source:'CONTROLLER',action_index:i,description:'HTTP 404 route introuvable'}))
    const rows=campaignIssues(s)
    expect(rows).toHaveLength(2);expect(rows.map(r=>r.actionIndex)).toEqual([0,1])
    expect(rows.every(r=>r.category==='structura'&&r.qualification==='À examiner — non confirmé')).toBe(true)
  })
  it('does not attach a pilot incident to the next unrelated action at its recorded index',()=>{
    const s=state();s.actions=[{actor:'bnp',tool:'book',status:'SUCCESS',result:{id:4}}]
    s.incidents=[{id:'pause',actor:'bnp',source:'CONTROLLER',kind:'HARNESS',action_index:0,description:'Pause de diagnostic'}]
    expect(campaignIssues(s)[0]).toMatchObject({category:'pilot',actionIndex:-1,action:undefined})
  })
  it('separates an unknown simulated-mail recipient from native Structura errors',()=>{
    const s=state();s.actions=[{actor:'client',tool:'mail',args:{to:'support@example.invalid'},status:'FAILED',result:{error:'Intervenant inconnu.'},http_calls:[]}]
    const row=campaignIssues(s)[0]
    expect(row.category).toBe('agent');expect(row.next).toContain('support@example.invalid')
    expect(row.summary).toContain('destinataire')
  })
  it('shows a native pricing-receipt refusal without claiming a confirmed Structura defect',()=>{
    const s=state();s.actions=[{actor:'bnp',tool:'book',status:'FAILED',result:{error:'PRODUCT_PRICING_RECEIPT_INVALID'},http_calls:[{status:422}]}]
    const row=campaignIssues(s)[0]
    expect(row.category).toBe('structura');expect(row.summary).toContain('preuve serveur')
    expect(row.next).toContain('ne démontre pas à lui seul un bug')
  })
  it('links an AI report by its result id and leaves its assertion unconfirmed',()=>{
    const s=state();s.actions=[{actor:'bnp',tool:'report',status:'SUCCESS',result:{id:'report-1'}}]
    s.incidents=[{id:'report-1',actor:'bnp',kind:'BUG',source:'AGENT',description:'Coupon incorrect'}]
    expect(campaignIssues(s)[0]).toMatchObject({category:'reported',actionIndex:0,qualification:'À examiner — non confirmé'})
  })
  it('exports the original response and action context, including failures without a separate incident',()=>{
    const s=state();s.actions=[{actor:'bnp',tool:'api',date:s.business_date,reason:'Relancer le pricing',args:{path:'/api/retry'},status:'FAILED',result:{error:'HTTP 404'},http_calls:[{method:'GET',path:'/api/retry',status:404}]}]
    const text=issueReport(s)
    expect(text).toContain('Action 1');expect(text).toContain('Relancer le pricing');expect(text).toContain('/api/retry');expect(text).toContain('HTTP 404')
    expect(text).toContain('pas une liste de bugs confirmés')
  })
})
