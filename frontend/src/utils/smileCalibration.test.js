import { beforeEach,afterEach,describe,it,expect,vi } from 'vitest'
import { calibrateUnderlying } from './smileCalibration.js'
import { makeSurface } from './volSurface.js'

const result={parameters:{v0:.09,theta:.1,kappa:1.2,xi:.4,rho_h:-.8},max_price_error_bp:20,method:'Fourier Heston',approximate:true}
const underlying=()=>({vol_surface:makeSurface('equity',30),sigma:30,q:2,v0:9,theta:9,kappa:2,xi:35,rho_h:-70,alpha:30,beta:100,rho:-75,nu:50})
describe('surface-driven model parameter synchronization',()=>{
  beforeEach(()=>vi.stubGlobal('fetch',vi.fn(async()=>({ok:true,json:async()=>result}))))
  afterEach(()=>vi.unstubAllGlobals())
  it('maps fractions to display values, caches the applied parameters and deduplicates requests',async()=>{
    const u=underlying()
    await Promise.all([calibrateUnderlying(u,'heston',4,3),calibrateUnderlying(u,'heston',4,3)])
    expect(u.v0).toBe(9);expect(u.theta).toBe(10);expect(u.kappa).toBe(1.2);expect(u.rho_h).toBe(-80)
    expect(u.smile_calibration.status).toBe('ready')
    await calibrateUnderlying(u,'heston',4,3)
    expect(fetch).toHaveBeenCalledTimes(1)
  })
  it('rejects a stale fit rather than pricing new assumptions with old parameters',async()=>{
    let resolve
    fetch.mockImplementationOnce(()=>new Promise(r=>{resolve=r}))
    const u=underlying(),p=calibrateUnderlying(u,'heston',4,3)
    u.vol_surface.eta=.9
    resolve({ok:true,json:async()=>result})
    await expect(p).rejects.toThrow(/changé/)
    expect(u.kappa).toBe(2)
  })
  it('preserves explicit manual model overrides',async()=>{
    const u={...underlying(),smile_parameter_mode:'manual',xi:65}
    await calibrateUnderlying(u,'heston',4,3)
    expect(fetch).not.toHaveBeenCalled();expect(u.xi).toBe(65)
  })
  it('does not replace parameters when manual mode is selected during a fit',async()=>{
    let resolve
    fetch.mockImplementationOnce(()=>new Promise(r=>{resolve=r}))
    const u=underlying(),p=calibrateUnderlying(u,'heston',4,3)
    u.smile_parameter_mode='manual'
    resolve({ok:true,json:async()=>result})
    await expect(p).rejects.toThrow(/changé/)
    expect(u.kappa).toBe(2)
  })
  it('keeps the existing parameters on API failure and exposes its reason',async()=>{
    fetch.mockResolvedValue({ok:false,json:async()=>({detail:'Calibration refusée : domaine invalide.'})})
    const u=underlying()
    await expect(calibrateUnderlying(u,'heston',4,3)).rejects.toThrow(/domaine/)
    expect(u.smile_calibration.status).toBe('error');expect(u.kappa).toBe(2)
  })
})
