import { validateSurface } from './volSurface.js'
const object = value => value && typeof value === 'object' && !Array.isArray(value)

/** Decode every persisted block before the live pricing session is touched. */
export function readPricingConfiguration(data) {
  if (typeof data?.script_text !== 'string' || !data.script_text.trim()) throw Error('Script de configuration absent.')
  const read = key => {
    let value
    try { value = JSON.parse(data[key] || '{}') } catch { throw Error(`Configuration JSON invalide (${key}).`) }
    if (!object(value)) throw Error(`Objet de configuration attendu (${key}).`)
    return value
  }
  const params = read('params_json'), calendars = read('constats_json'), global = read('global_params_json')
  for (const value of Object.values(params)) {
    const values = Array.isArray(value) ? value : [value]
    if (!values.length || values.some(v => v != null && v !== '' && (typeof v !== 'number' || !Number.isFinite(v)))) {
      throw Error('Paramètre de configuration invalide : nombre fini ou cellule à renseigner attendu.')
    }
  }
  for (const value of Object.values(calendars)) {
    if (typeof value !== 'string' && !object(value)) throw Error('Calendrier de configuration invalide.')
    if (object(value)) for (const key of ['frequency', 'sub_frequency', 'window_length', 'window_frequency']) {
      const tenor = value[key]
      if (tenor != null && typeof tenor !== 'string' && (!object(tenor) || !['D','W','M','Y'].includes(tenor.unit))) {
        throw Error('Fréquence de calendrier invalide.')
      }
    }
  }
  if (global.underlyings != null && (!Array.isArray(global.underlyings) || !global.underlyings.length
      || global.underlyings.some(u => !object(u)))) throw Error('Panier de configuration invalide.')
  for (const underlying of global.underlyings || []) {
    for (const key of ['sigma','q','v0','theta','xi','rho_h','kappa','alpha','beta','rho','nu','skew','curvature','rho_rS','sigma_fx','rho_sfx','ccyh','dividendDecay']) {
      if (underlying[key] != null && (typeof underlying[key] !== 'number' || !Number.isFinite(underlying[key]))) throw Error('Hypothèse de sous-jacent invalide : '+key)
    }
    if (underlying.vol_surface != null) {
      try { validateSurface(underlying.vol_surface) } catch { throw Error('Surface de volatilité enregistrée invalide.') }
    }
  }
  if (global.corr_matrix != null && (!Array.isArray(global.corr_matrix)
      || global.corr_matrix.some(row => !Array.isArray(row) || row.length !== global.corr_matrix.length
        || row.some(v => typeof v !== 'number' || !Number.isFinite(v)))
      || (global.underlyings && global.underlyings.length !== global.corr_matrix.length))) {
    throw Error('Matrice de corrélation de configuration invalide.')
  }
  if ('funding' in global && !object(global.funding)) throw Error('Funding de configuration invalide.')
  if (global.underlyings && !global.corr_matrix) throw Error('La configuration du panier doit inclure ses corrélations.')
  if (global.yield_curve_enabled && !global.yield_curve_pillars?.length) throw Error('Les piliers de la courbe de taux active sont absents.')
  if (global.funding?.enabled && global.funding.mode === 'pillars' && !global.funding.pillars?.length) throw Error('Les piliers de funding actifs sont absents.')
  for (const key of ['antithetic','yield_curve_enabled']) {
    if (global[key] != null && typeof global[key] !== 'boolean') throw Error('Option de configuration invalide : '+key)
  }
  for (const key of ['r','N','seed','sigma_r','a_r','nominal']) {
    if (global[key] != null && (typeof global[key] !== 'number' || !Number.isFinite(global[key]))) throw Error('Hypothèse numérique invalide : '+key)
  }
  if (global.T != null && (typeof global.T !== 'number' || !Number.isFinite(global.T) || global.T <= 0)) throw Error('Maturité de configuration invalide.')
  for (const [key, choices] of Object.entries({model:['constant','heston','sabr','local_vol','lsv'],rateModel:['deterministic','abm','hull_white'],barrierMonitoring:['weekly','continuous']})) {
    if (global[key] != null && !choices.includes(global[key])) throw Error('Modèle ou convention de configuration inconnu : '+key)
  }
  if (global.configuration?.include_basket === false && (global.underlyings || global.corr_matrix)) throw Error('Le contenu du panier contredit la portée annoncée par la configuration.')
  if (global.funding && (global.funding.level != null && !Number.isFinite(global.funding.level)
      || global.funding.mode != null && !['flat','pillars'].includes(global.funding.mode))) throw Error('Hypothèse de funding invalide.')
  for (const pillars of [global.yield_curve_pillars, global.funding?.pillars]) {
    if (pillars != null && (!Array.isArray(pillars) || pillars.some(p => !object(p)
        || typeof p.T !== 'number' || !Number.isFinite(p.T)
        || !Number.isFinite(p.rate ?? p.spread)))) throw Error('Courbe de configuration invalide.')
  }
  return { params, calendars, global }
}
