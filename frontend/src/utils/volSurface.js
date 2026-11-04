// Surface ATM nodes always use engine fractions, including in editable snapshots.
export const SMILE_STRIKES = [.2, .4, .6, .8, 1, 1.2, 1.4, 1.6, 1.8]
export const SMILE_TENORS = [.25, .5, 1, 2, 3, 5, 7, 10]
export const SMILE_PROFILES = {
  equity: { label: 'Actions', sigma: 30, rho: -.75, eta: .85 },
  index: { label: 'Indices actions', sigma: 20, rho: -.80, eta: 1.05 },
}
export const ATM_SCENARIOS = {
  flat: 'Plate', contango: 'Contango', backwardation: 'Backwardation', hump: 'Bosse',
}
export const HESTON_FIT_LABELS = {
  atm: 'Calls ATM uniquement',
  atm_digital: 'Calls ATM + digitales',
  atm_smile: 'Calls ATM + smile complet',
}
export const cloneSurface = s => s ? JSON.parse(JSON.stringify(s)) : null

export function classifyUnderlying(ticker, groups = []) {
  const key = String(ticker || '').trim().toUpperCase()
  if (!key || ['^VIX', '^VVIX', '^MOVE'].includes(key)) return 'unknown'
  const group = groups.find(g => g.items?.some(u => u.ticker?.toUpperCase() === key))?.group || ''
  if (/indices/i.test(group) || key.startsWith('^')) return 'index'
  if (/actions|banques|luxe/i.test(group)) return 'equity'
  // Unknown instruments must not acquire an equity smile from their ticker syntax.
  return 'unknown'
}

export function makeSurface(profile, sigma, horizon = 10) {
  const p = SMILE_PROFILES[profile] || SMILE_PROFILES.equity
  const max = Math.max(10, Number(horizon) || 10)
  const times = [...SMILE_TENORS, ...(max > 10 ? [max] : [])]
  return { version: 1, profile, mode: 'automatic', rho: p.rho, eta: p.eta,
    shape_scale: .04, max_expiry: max, atm_nodes: times.map(t => [t, Number(sigma)/100]) }
}

export function applyAtmScenario(surface, scenario) {
  if (!Object.hasOwn(ATM_SCENARIOS, scenario)) throw Error('Scénario ATM inconnu.')
  const s = cloneSurface(surface)
  const base = surfaceVol(s, 1) / 100
  s.atm_nodes = Array.from({ length: 10 }, (_, i) => {
    const t = i + 1
    const slope = i / 9
    const shift = scenario === 'contango' ? .1 * slope
      : scenario === 'backwardation' ? -.1 * slope
      : scenario === 'hump' ? .1 * (t <= 3 ? i / 2 : (10 - t) / 7) : 0
    return [t, base * (1 + shift)]
  })
  s.atm_scenario = scenario
  s.mode = 'manual'
  return validateSurface(s)
}

export function thetaAt(s, t) {
  const nodes = [[0,0], ...s.atm_nodes.map(([time,vol]) => [time,time*vol*vol])]
  const last = nodes.at(-1)
  if (t >= last[0]) return last[1]*t/last[0]
  const i = nodes.findIndex(n => n[0] > t)
  const [a,b] = [nodes[i-1],nodes[i]]
  return a[1]+(b[1]-a[1])*(t-a[0])/(b[0]-a[0])
}

export function surfaceVol(s, t, strike = 1) {
  const theta=thetaAt(s,t), k=Math.log(strike)
  let phi=s.eta/Math.sqrt(s.shape_scale+theta)
  if (s.wing_nodes?.length) {
    const index=s.wing_nodes.findIndex(([time])=>time>t)
    if (index===0) phi=s.wing_nodes[0][1]/thetaAt(s,s.wing_nodes[0][0])
    else if (index<0) phi=s.wing_nodes.at(-1)[1]/theta
    else {
      const [t0,p0]=s.wing_nodes[index-1], [t1,p1]=s.wing_nodes[index]
      const theta0=thetaAt(s,t0), theta1=thetaAt(s,t1)
      phi=(p0+(p1-p0)*(theta-theta0)/(theta1-theta0))/theta
    }
  }
  const w=.5*theta*(1+s.rho*phi*k+Math.sqrt((phi*k+s.rho)**2+1-s.rho**2))
  return Math.sqrt(w/t)*100
}

export function validateSurface(s) {
  if (!s || !Number.isFinite(s.rho) || Math.abs(s.rho)>=1 || !Number.isFinite(s.eta) || s.eta<0
    || !(s.shape_scale>0) || !(s.max_expiry>0) || s.max_expiry>30) throw Error('Paramètres de surface invalides.')
  let lastTime=0, lastTheta=0
  for (const [t,v] of s.atm_nodes) {
    const theta=t*v*v
    if (!Number.isFinite(t) || !Number.isFinite(v) || t<=lastTime || v<=0 || theta<=lastTheta)
      throw Error('La variance totale ATM doit croître avec la maturité. Modification refusée.')
    lastTime=t; lastTheta=theta
  }
  const theta=thetaAt(s,s.max_expiry), phi=s.eta/Math.sqrt(s.shape_scale+theta)
  if (theta*phi*(1+Math.abs(s.rho))>=4 || theta*phi**2*(1+Math.abs(s.rho))>4)
    throw Error('Ce smile dépasse les bornes SSVI sans arbitrage. Réduisez la pente ou la convexité.')
  if (s.wing_nodes) {
    let lastTime=0, lastPsi=0, lastPhi=Infinity
    for (const [t,psi] of s.wing_nodes) {
      const theta=thetaAt(s,t), phi=psi/theta, factor=1+Math.abs(s.rho)
      if (!Number.isFinite(t) || !Number.isFinite(psi) || t<=lastTime || t>s.max_expiry
          || psi<0 || psi<lastPsi-1e-12 || phi>lastPhi+1e-12
          || psi*factor>=4 || psi*phi*factor>4)
        throw Error('Cette modification est incompatible avec les piliers d’aile. Réinitialisez le profil pour repartir de sa forme globale.')
      lastTime=t; lastPsi=psi; lastPhi=phi
    }
  }
  return s
}

export function shiftSurface(surface, tenor, delta, all = false) {
  const s=cloneSurface(surface)
  const current=surfaceVol(s,tenor)
  if (all) s.atm_nodes=s.atm_nodes.map(([t,v]) => [t,v+delta/100])
  else {
    const node=s.atm_nodes.find(n => Math.abs(n[0]-tenor)<1e-8)
    if (node) node[1]=(current+delta)/100
    else { s.atm_nodes.push([tenor,(current+delta)/100]); s.atm_nodes.sort((a,b)=>a[0]-b[0]) }
  }
  s.mode='manual'
  if (s.atm_scenario) s.atm_scenario = 'custom'
  return validateSurface(s)
}

// One wing edit solves one shared shape parameter. Other maturities remain
// coherent, and all their resulting matrix values are shown, never hidden.
export function moveSurfaceNode(surface, tenor, strike, requested) {
  if (!(requested>0) || !Number.isFinite(requested)) throw Error('Volatilité demandée invalide.')
  if (strike===1) return shiftSurface(surface,tenor,requested-surfaceVol(surface,tenor))
  const field=strike===.8 ? 'rho' : 'eta'
  const bounds=field==='rho' ? [-.99,.99] : [0,3]
  let best=null, error=Infinity
  const objective=value => {
    const s=cloneSurface(surface); s[field]=value; s.mode='manual'
    try { validateSurface(s) } catch { return }
    const e=Math.abs(surfaceVol(s,tenor,strike)-requested)
    if(e<error) {error=e;best=s}
  }
  // Global scan then local refinement handles a non-monotone wing response.
  const step=(bounds[1]-bounds[0])/180
  for(let i=0;i<=180;i++) objective(bounds[0]+i*step)
  if(best) {
    let lo=Math.max(bounds[0],best[field]-step),hi=Math.min(bounds[1],best[field]+step)
    for(let j=0;j<28;j++) {
      const x=lo+(hi-lo)/3,y=hi-(hi-lo)/3
      const a=cloneSurface(surface),b=cloneSurface(surface); a[field]=x;b[field]=y
      objective(x);objective(y)
      if(Math.abs(surfaceVol(a,tenor,strike)-requested)<Math.abs(surfaceVol(b,tenor,strike)-requested)) hi=y
      else lo=x
    }
  }
  if(!best || error>.10) throw Error('Point incompatible avec la surface cohérente (tolérance 0,10 point de vol).')
  return best
}

export function synchronizeSurfaceLevel(u) {
  const s=u.vol_surface
  if(!s) return
  u.sigma=Math.round(surfaceVol(s,1)*1e6)/1e6
}

// Preserve the manually edited term structure when its reference level changes.
export function resizeSurfaceLevel(u) {
  if (!u.vol_surface) return
  const atm=surfaceVol(u.vol_surface,1), target=Number(u.sigma)
  if (Math.abs(atm-target)<1e-5) return
  try {
    if (!(target>0) || !Number.isFinite(target)) throw Error('La volatilité doit être strictement positive.')
    const s=cloneSurface(u.vol_surface)
    s.atm_nodes=s.atm_nodes.map(([t,v])=>[t,v*target/atm])
    validateSurface(s);u.vol_surface=s;u.smile_error=null
  } catch(e) { synchronizeSurfaceLevel(u);u.smile_error=e.message }
}

export function hasExplicitHestonFit(u, model) {
  return model === 'heston' && Boolean(u.vol_surface?.atm_scenario)
}

export function hestonFitOptions(u) {
  return { mode: u.heston_fit?.mode ?? u.calibration_evidence?.dossier?.heston_fit?.mode ?? 'atm' }
}

export function surfaceCalibrationKey(u,model,horizon,rate) {
  const scenario = hasExplicitHestonFit(u, model)
  const fitHorizon = scenario && horizon <= 10 ? 10 : Number(horizon)
  const fields = scenario ? ['v0','theta','kappa','xi','rho_h']
    : ['v0','theta','kappa','xi','rho_h','alpha','beta','rho','nu']
  return JSON.stringify([u.vol_surface,model,fitHorizon,Number(rate),Number(u.q),u.smile_parameter_mode || 'automatic',
    u.ticker,u.ccy,Number(u.sigma),scenario ? hestonFitOptions(u).mode : null,
    fields.map(k=>Number(u[k]))])
}
