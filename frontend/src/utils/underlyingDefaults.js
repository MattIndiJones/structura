// Display units shared by the Pricer and RFQ calibration forms.
export function defaultUnderlying(n = 1, ccy = 'EUR') {
  return {
    name: `Sous-jacent ${n}`, ticker: '', ccy,
    sigma: 20, q: 2, sigma_fx: 0, rho_sfx: 0, ccyh: 0,
    dividendCurveEnabled: false, dividendDecay: 10,
    v0: 4, kappa: 2, theta: 4, xi: 35, rho_h: -70, rho_rS: 40,
    alpha: 20, beta: 50, rho: -30, nu: 40,
    skew: -10, curvature: 5, showQuanto: false,
  }
}

export const PERCENT_MARKET_FIELDS = [
  'sigma', 'q', 'sigma_fx', 'rho_sfx', 'v0', 'theta', 'xi', 'rho_h',
  'rho_rS', 'alpha', 'beta', 'rho', 'nu', 'skew', 'curvature',
]

// Engine fractions can contain binary floating-point tails in editable inputs.
export function fractionToPercent(value) {
  return Math.round(Number(value) * 1e6) / 1e4
}
