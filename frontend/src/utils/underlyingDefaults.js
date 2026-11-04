// Display units shared by the Pricer and RFQ calibration forms.
export function defaultUnderlying(n = 1, ccy = 'EUR') {
  return {
    name: `Sous-jacent ${n}`, ticker: '', ccy,
    sigma: 20, q: 2, sigma_fx: 0, rho_sfx: 0, ccyh: 0,
    dividendCurveEnabled: false, dividendDecay: 10,
    v0: 4, kappa: 2, theta: 4, xi: 35, rho_h: -70, rho_rS: 40,
    alpha: 20, beta: 50, rho: -30, nu: 40,
    skew: 0, curvature: 0, showQuanto: false,
    asset_class: 'unknown', vol_surface: null, _smileDefaults: true, vol_level_source: 'default',
  }
}

export const PERCENT_MARKET_FIELDS = [
  'sigma', 'q', 'sigma_fx', 'rho_sfx', 'v0', 'theta', 'xi', 'rho_h',
  'rho_rS', 'alpha', 'beta', 'rho', 'nu', 'skew', 'curvature',
]

// Only follow the reference while the original variance assumptions are untouched.
// Both fields are variance in UI percent units, not volatility in percent.
export function anchorDefaultHestonVariance(u) {
  if (u.vol_level_source === 'saved' || u.smile_parameter_mode === 'manual' || u.calibration_evidence) return
  const previous = u._hestonVarianceAnchor ?? 4
  if (u.v0 !== previous || u.theta !== previous
      || (u._hestonVarianceAnchor == null && (u.kappa !== 2 || u.xi !== 35 || u.rho_h !== -70))) return
  const sigma = Number(u.sigma)
  if (!(sigma > 0) || !Number.isFinite(sigma)) return
  const variance = Math.round(sigma ** 2 * 1e4) / 1e6
  if (variance > 0) u.v0 = u.theta = u._hestonVarianceAnchor = variance
}

// Engine fractions can contain binary floating-point tails in editable inputs.
export function fractionToPercent(value) {
  return Math.round(Number(value) * 1e6) / 1e4
}

// Shift the persisted decimal without rounding meaningful saved digits.
export function fractionToPercentExact(value) {
  const [coefficient, exponent = '0'] = String(Number(value)).split('e')
  return Number(`${coefficient}e${Number(exponent) + 2}`)
}
