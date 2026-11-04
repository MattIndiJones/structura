import { describe,it,expect } from 'vitest'
import { applyAtmScenario,classifyUnderlying,makeSurface,surfaceVol,validateSurface,moveSurfaceNode,shiftSurface,resizeSurfaceLevel } from './volSurface.js'
import { rfqBasketFromParams,rfqUnderlyingToParams } from './rfqBasket.js'

describe('editable coherent equity smiles',()=>{
  it.each([['flat',25,25],['contango',25+5/9,27.5],
    ['backwardation',25-5/9,22.5],['hump',27.5,25]])(
    'builds the ten editable annual ATM points for %s without altering the smile',
    (scenario, atThree, atTen) => {
      const original = makeSurface('index',25)
      const surface = applyAtmScenario(original,scenario)
      expect(surface.atm_nodes.map(([t])=>t)).toEqual([1,2,3,4,5,6,7,8,9,10])
      expect([surface.profile,surface.rho,surface.eta]).toEqual([original.profile,original.rho,original.eta])
      expect(surfaceVol(surface,1)).toBeCloseTo(25)
      expect(surfaceVol(surface,3)).toBeCloseTo(atThree)
      expect(surfaceVol(surface,10)).toBeCloseTo(atTen)
      expect(moveSurfaceNode(surface,4,1,surfaceVol(surface,4)+.1).atm_scenario).toBe('custom')
    })
  it('uses catalogue class and excludes volatility indices and unknown instruments',()=>{
    const groups=[{group:'Actions FR',items:[{ticker:'GLE.PA'}]},
      {group:'Banques',items:[{ticker:'JPM'}]}, {group:'Luxe',items:[{ticker:'CPRI'}]}]
    expect(classifyUnderlying('gle.pa',groups)).toBe('equity')
    expect(classifyUnderlying('^STOXX50E',groups)).toBe('index')
    expect(classifyUnderlying('^VIX',groups)).toBe('unknown')
    expect(classifyUnderlying('EURUSD=X',groups)).toBe('unknown')
    expect(classifyUnderlying('JPM',groups)).toBe('equity')
    expect(classifyUnderlying('CPRI',groups)).toBe('equity')
  })
  it('matches class/level anchors and maturity attenuation',()=>{
    expect(surfaceVol(makeSurface('equity',30),1,.8)).toBeCloseTo(35.6977,3)
    expect(surfaceVol(makeSurface('index',20),1,.8)).toBeCloseTo(26.073,2)
    expect(surfaceVol(makeSurface('equity',40),1,.8)).toBeGreaterThan(46)
    expect(surfaceVol(makeSurface('equity',30),4,.8)).toBeLessThan(35.7)
  })
  it('moves one maturity or all, preserves the original and rejects calendar inversion',()=>{
    const original=makeSurface('equity',30)
    const one=shiftSurface(original,1,1)
    expect(surfaceVol(one,1)).toBeCloseTo(31)
    expect(surfaceVol(one,2)).toBeCloseTo(30)
    const all=shiftSurface(original,1,2,true)
    expect(surfaceVol(all,5)).toBeCloseTo(32)
    expect(surfaceVol(original,1)).toBeCloseTo(30)
    expect(()=>shiftSurface(original,1,-25)).toThrow(/variance/)
  })
  it('fits a wing target and propagates the coherent shape to other maturities',()=>{
    const original=makeSurface('equity',30)
    const moved=moveSurfaceNode(original,1,.8,surfaceVol(original,1,.8)+1)
    expect(surfaceVol(moved,1,.8)).toBeCloseTo(surfaceVol(original,1,.8)+1,2)
    expect(moved.mode).toBe('manual')
    expect(surfaceVol(moved,2,.8)).not.toBe(surfaceVol(original,2,.8))
    expect(()=>moveSurfaceNode(original,1,.8,100)).toThrow(/incompatible/)
    expect(()=>validateSurface({...original,eta:3})).toThrow(/bornes/)
  })
  it('preserves engine fractions across RFQ editing and saving',()=>{
    const s=makeSurface('index',20)
    const rows=rfqBasketFromParams([{name:'SX5E',sigma:.2,asset_class:'index',vol_surface:s}])
    expect(rows[0].vol_surface.atm_nodes[2][1]).toBe(.2)
    expect(rfqUnderlyingToParams(rows[0]).vol_surface).toEqual(s)
    rows[0].smile_parameter_mode='manual'
    expect(rfqBasketFromParams([rfqUnderlyingToParams(rows[0])])[0].smile_parameter_mode).toBe('manual')
  })
  it('rescales a manually edited term structure and restores invalid reference levels',()=>{
    const u={vol_surface:shiftSurface(makeSurface('equity',30),2,1),sigma:35}
    resizeSurfaceLevel(u)
    expect(surfaceVol(u.vol_surface,1)).toBeCloseTo(35)
    expect(surfaceVol(u.vol_surface,2)).toBeCloseTo(31*35/30)
    expect(u.vol_surface.mode).toBe('manual')
    u.sigma=-10;resizeSurfaceLevel(u)
    expect(u.sigma).toBe(35);expect(u.smile_error).toMatch(/positive/)
  })
})
