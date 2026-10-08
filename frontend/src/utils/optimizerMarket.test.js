import { beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { usePricingStore } from '../stores/pricing.js'
import { optimizerMarketFromPricer, withMarketReferences, curveText, parseOptimizerCurve, remapCorrelations } from './optimizerMarket.js'

function source() {
  return {model:'constant',rate_model:'deterministic',currency:'EUR',as_of:'2026-10-08',r:.03,
    yield_curve:[[1,.03],[5,.04]],funding_spread:.015,funding_curve:[],corr_matrix:[[1,.4],[.4,1]],
    underlyings:[{ticker:'TEST',name:'Test',ccy:'EUR',sigma:.2,q:.02,asset_class:'equity',dividend_curve:[[1,.02],[2,.018]]},
      {ticker:'TEST2',name:'Test2',ccy:'EUR',sigma:.3,q:.01}]}
}

describe('Optimizer market snapshot', () => {
  beforeEach(() => setActivePinia(createPinia()))
  it('copies exact engine values and every reference, without changing the Pricer', () => {
    const input=source(), before=JSON.stringify(input)
    const snapshot=optimizerMarketFromPricer(input)
    expect(JSON.stringify(input)).toBe(before)
    expect(snapshot.market.underlyings[0].sigma).toBe(.2)
    expect(snapshot.market.funding_spread).toBe(.015)
    expect(snapshot.market.provenance['underlyings.TEST.sigma'].reference_value).toBe(.2)
    input.underlyings[0].sigma=.4; input.yield_curve[0][1]=.09
    expect(snapshot.market.underlyings[0].sigma).toBe(.2)
    expect(snapshot.market.yield_curve[0][1]).toBe(.03)
  })
  it('keeps references while editing and prunes removed identities', () => {
    const imported=optimizerMarketFromPricer(source()).market
    const market=JSON.parse(JSON.stringify(imported))
    market.underlyings.shift();market.underlyings[0].sigma=.45
    const edited=withMarketReferences(market,imported)
    expect(edited.provenance['underlyings.TEST.sigma']).toBeUndefined()
    expect(edited.provenance['underlyings.TEST2.sigma'].reference_value).toBe(.3)
    expect(edited.underlyings[0].sigma).toBe(.45)
    edited.underlyings[0].ticker='NEW'
    const changed=withMarketReferences(edited,imported)
    expect(changed.provenance['underlyings.NEW.sigma'].source).toBe('USER_ASSUMPTION')
    expect(imported.underlyings[1].sigma).toBe(.3)
  })
  it.each(['heston','local_vol','lsv'])('refuses implicit conversion from %s', model => {
    expect(()=>optimizerMarketFromPricer({...source(),model})).toThrow('GBM')
  })
  it('refuses stochastic rates, cross-currency, quanto and invalid identities', () => {
    expect(()=>optimizerMarketFromPricer({...source(),rate_model:'hull_white'})).toThrow('déterministes')
    for(const patch of [{ccy:'USD'},{ccyh:.001},{sigma_fx:.1,rho_sfx:.3},{ticker:''},{ticker:'TEST2'}]) {
      const input=source(); Object.assign(input.underlyings[0],patch)
      expect(()=>optimizerMarketFromPricer(input)).toThrow()
    }
  })
  it('converts curve percentages exactly once and rejects missing numeric nodes', () => {
    expect(parseOptimizerCurve(curveText([[1,.02],[3,.018]]))).toEqual([[1,.02],[3,.018]])
    for(const text of ['oops','[[1,null]]','[[1,"3"]]','[1,2]','{}']) expect(()=>parseOptimizerCurve(text)).toThrow()
    expect(parseOptimizerCurve('')).toEqual([])
  })
  it('keeps correlations attached to identities when removing or reordering assets', () => {
    expect(remapCorrelations(['A','B','C'],['B','C'],{'0-1':.2,'0-2':.3,'1-2':.7})).toEqual({'0-1':.7})
    expect(remapCorrelations(['A','B','C'],['C','A','D'],{'0-1':.2,'0-2':.3,'1-2':.7})).toEqual({'0-1':.3,'0-2':.5,'1-2':.5})
  })
  it('exports the actual Pricer market without requiring script parameters or network', () => {
    const store=usePricingStore()
    store.underlyings[0].ticker='TEST';store.underlyings[0].sigma=27
    store.underlyings[0].q=3;store.underlyings[0].dividendCurveEnabled=true;store.underlyings[0].dividendDecay=10
    store.globalParams.T=3;store.globalParams.strike_date='2026-10-08'
    store.fundingCurve.enabled=true;store.fundingCurve.mode='flat';store.fundingCurve.level=1.5
    const input=store.optimizerMarketInputs()
    expect(input.underlyings[0].sigma).toBe(.27)
    expect(input.underlyings[0].dividend_curve[1][1]).toBeCloseTo(.027)
    expect(input.funding_spread).toBe(.015)
    expect(input.as_of).toBe('2026-10-08')
    expect(optimizerMarketFromPricer(input).market.underlyings[0].sigma).toBe(.27)
  })
})
