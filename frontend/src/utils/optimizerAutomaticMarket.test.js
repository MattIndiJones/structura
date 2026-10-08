import { describe, expect, it } from 'vitest'
import { emptyOptimizerAsset, applyAutomaticAsset, withAutomaticReferences, remapCorrelations } from './optimizerMarket.js'

const reference={ticker:'STMPA.PA',asset_type:'equity',sigma:.31,q:.004}
describe('Automatic dated market assumptions',()=>{
  it('rounds loaded pricing inputs to cents of percent while keeping the provider reference intact',()=>{
    const source={...reference,sigma:.28542308,q:.064559}
    const asset=emptyOptimizerAsset('STMPA.PA')
    applyAutomaticAsset(asset,source)
    expect(asset.vol).toBe(28.54)
    expect(asset.dividend).toBe(6.46)
    expect(source.sigma).toBe(.28542308)
    expect(source.q).toBe(.064559)
    expect(asset.manual).toEqual({vol:false,dividend:false})
  })
  it('starts with missing fields and classifies the selected title from its reference',()=>{
    const asset=emptyOptimizerAsset('STMPA.PA')
    expect(asset.vol).toBeNull();expect(asset.dividend).toBeNull();expect(asset.asset_type).toBe('')
    applyAutomaticAsset(asset,reference)
    expect(asset).toMatchObject({asset_type:'equity',classified:true,vol:31,dividend:.4})
  })
  it('preserves deliberate overrides on a dated refresh, including zero dividend',()=>{
    const asset=emptyOptimizerAsset('STMPA.PA');asset.vol=42;asset.dividend=0;asset.manual={vol:true,dividend:true}
    applyAutomaticAsset(asset,reference)
    expect(asset.vol).toBe(42);expect(asset.dividend).toBe(0)
    asset.manual.vol=false;applyAutomaticAsset(asset,reference);expect(asset.vol).toBe(31)
  })
  it('cannot apply an obsolete response to a different ticker',()=>{
    const asset=emptyOptimizerAsset('BNP.PA')
    applyAutomaticAsset(asset,reference)
    expect(asset.vol).toBeNull();expect(asset.asset_type).toBe('')
  })
  it('keeps absent provider fields missing while retaining explicit hypotheses',()=>{
    const asset=emptyOptimizerAsset('STMPA.PA');asset.vol=29;asset.manual.vol=true
    applyAutomaticAsset(asset,{...reference,sigma:null,q:null})
    expect(asset.vol).toBe(29);expect(asset.dividend).toBeNull()
  })
  it('preserves the source value and date in an overridden frozen request',()=>{
    const market={as_of:'2026-10-04',rate:.03,yield_curve:[],funding_spread:0,funding_curve:[],correlation:[[1]],
      underlyings:[{ticker:'STMPA.PA',currency:'EUR',sigma:.42,q:0,dividend_curve:[]}]}
    const source={captured_at:'2026-10-08T14:00:00Z',provenance:{'underlyings.STMPA.PA.sigma':{source:'HISTORICAL_ESTIMATE',as_of:'2026-10-02',reference_value:.31,method:'Vol réalisée'}}}
    const result=withAutomaticReferences(market,source)
    expect(result.source).toBe('AUTO_MARKET');expect(result.underlyings[0].sigma).toBe(.42)
    expect(result.provenance['underlyings.STMPA.PA.sigma'].reference_value).toBe(.31)
    expect(result.provenance.rate.source).toBe('USER_ASSUMPTION')
    result.provenance['underlyings.STMPA.PA.sigma'].reference_value=1
    expect(source.provenance['underlyings.STMPA.PA.sigma'].reference_value).toBe(.31)
  })
  it('never introduces a generic correlation for a new or missing pair',()=>{
    expect(remapCorrelations(['A','B'],['B','A','C'],{'0-1':.7},null)).toEqual({'0-1':.7,'0-2':null,'1-2':null})
    expect(remapCorrelations(['A','B'],['A','B'],{'0-1':null},null)['0-1']).toBeNull()
  })
})
