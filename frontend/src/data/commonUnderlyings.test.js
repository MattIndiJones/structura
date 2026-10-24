import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { underlyingGroups, clearUnderlyings, ensureUnderlyings, selectCatalogUnderlying } from './commonUnderlyings.js'
import { saveSession } from '../utils/session.js'
const mocks=vi.hoisted(()=>({api:vi.fn()}))
vi.mock('../utils/api.js',()=>({apiFetch:(...args)=>mocks.api(...args)}))
const groups=[{group:'US',items:[{ticker:'AAPL',label:'Apple',ccy:'USD'}]}]
const response=data=>({ok:true,json:async()=>data})
beforeEach(()=>{sessionStorage.clear();clearUnderlyings();mocks.api.mockReset()})
afterEach(()=>vi.restoreAllMocks())

describe('sélection cohérente du référentiel',()=>{
  it('reprend ensemble ticker, nom et devise dans le Pricer et la RFQ',()=>{
    underlyingGroups.push(...groups)
    for(let i=0;i<2;i++){
      const row={ticker:'BNP.PA',name:'BNP',ccy:'EUR'}
      selectCatalogUnderlying(row,'AAPL')
      expect(row).toEqual({ticker:'AAPL',name:'Apple',ccy:'USD'})
    }
  })
  it('conserve un alias réellement utilisé par le payoff',()=>{
    underlyingGroups.push(...groups)
    const row={ticker:'BNP.PA',name:'UL1',ccy:'EUR'}
    selectCatalogUnderlying(row,'AAPL','PAY UL1.spot')
    expect(row).toEqual({ticker:'AAPL',name:'UL1',ccy:'USD'})
  })
  it('refuse une devise absente ou divergente sans mutation partielle',()=>{
    underlyingGroups.push(...groups,{group:'Conflict',items:[{ticker:'AAPL',label:'Apple',ccy:'EUR'}]})
    const row={ticker:'BNP.PA',name:'BNP',ccy:'EUR'}
    expect(()=>selectCatalogUnderlying(row,'AAPL')).toThrow('qualifier')
    expect(row.ticker).toBe('BNP.PA')
  })
})

describe('rafraîchissement et isolation du catalogue',()=>{
  it('rafraîchit en place après une modification administrateur',async()=>{
    mocks.api.mockResolvedValueOnce(response(groups)).mockResolvedValueOnce(response([]))
    const original=underlyingGroups
    await ensureUnderlyings()
    await ensureUnderlyings()
    expect(mocks.api).toHaveBeenCalledTimes(1)
    await ensureUnderlyings({force:true})
    expect(underlyingGroups).toBe(original)
    expect(underlyingGroups).toEqual([])
  })
  it('ne réutilise ni n’applique une réponse provenant de la session précédente',async()=>{
    let complete
    mocks.api.mockImplementationOnce(()=>new Promise(resolve=>{complete=resolve})).mockResolvedValueOnce(response([]))
    saveSession('session-A',null)
    const first=ensureUnderlyings()
    saveSession('session-B',null)
    await ensureUnderlyings()
    complete(response(groups));await first
    expect(underlyingGroups).toEqual([])
  })
  it('retire un catalogue périmé lorsque le rafraîchissement échoue',async()=>{
    mocks.api.mockResolvedValueOnce(response(groups)).mockRejectedValueOnce(new Error('offline'))
    await ensureUnderlyings()
    expect(underlyingGroups.length).toBe(1)
    await ensureUnderlyings({force:true})
    expect(underlyingGroups).toEqual([])
  })
})
