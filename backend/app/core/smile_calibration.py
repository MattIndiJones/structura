"""Reproducible fits and bounded diagnostics of synthetic SSVI targets."""
import math
from copy import deepcopy
import hashlib
from pathlib import Path

import numpy as np
import scipy
from scipy.integrate import quad_vec
from scipy.optimize import least_squares
from scipy.special import ndtr

from .volatility_surface import TermSSVISurface

METHOD_VERSION = 'surface-fit-v2'
THRESHOLDS_BP = {'vanilla': 5., 'digital': 10.}


def heston_prices(parameters, expiries, strikes, rate, dividend, *, tolerance=1e-8):
    """Calls and cash put digitals; adaptive Fourier with a BS control variate.

    The control variance is the expected integrated Heston variance. Integration
    is over [0, infinity), with an explicit error estimate, never a fixed cutoff.
    """
    v0, theta, kap, xi, rho = (float(parameters[k]) for k in
                              ('v0', 'theta', 'kappa', 'xi', 'rho_h'))
    times = np.asarray(expiries, dtype=float)[:, None]
    k = np.broadcast_to(np.asarray(strikes, dtype=float),
                        (len(times), np.asarray(strikes).shape[-1]))
    if (not np.all(np.isfinite([v0, theta, kap, xi, rho, rate, dividend]))
            or min(v0, theta, kap) <= 0 or xi < 0 or abs(rho) >= 1
            or np.any(times <= 0) or np.any(k <= 0)
            or not np.all(np.isfinite(times)) or not np.all(np.isfinite(k))):
        raise ValueError('Paramètres Fourier Heston hors domaine.')
    variance = theta*times+(v0-theta)*(-np.expm1(-kap*times))/kap
    root = np.sqrt(variance)
    log_forward = (rate-dividend)*times
    d1 = (log_forward-np.log(k))/root+root/2
    d2 = d1-root
    prepaid, df = np.exp(-dividend*times), np.exp(-rate*times)
    calls = prepaid*ndtr(d1)-k*df*ndtr(d2)
    digitals = df*ndtr(-d2)
    error, evaluations = 0., 0
    if xi > 0:
        def difference(z):
            iz = 1j*z
            b = kap-rho*xi*iz
            d = np.sqrt(b*b+xi*xi*(z*z+iz))
            # Avoid cancellation in b-d at small vol-of-vol.
            minus = -xi*xi*(z*z+iz)/(b+d)
            g = minus/(b+d)
            one_minus_e = -np.expm1(-d*times)
            log_ratio = np.log1p(g*one_minus_e/(1-g))
            exponent = (iz*log_forward+kap*theta/xi**2*(minus*times-2*log_ratio)
                        +minus/xi**2*one_minus_e/(1-g+g*one_minus_e)*v0)
            bs_exponent = iz*log_forward-.5*variance*(z*z+iz)
            delta = exponent-bs_exponent
            result = np.exp(exponent)-np.exp(bs_exponent)
            close = abs(delta) < .5
            result[close] = np.exp(bs_exponent[close])*np.expm1(delta[close])
            return result

        def integrand(u):
            phase = np.exp(-1j*np.log(k)*u)/(1j*u)
            return np.array([np.real(phase*difference(u-1j)/np.exp(log_forward)),
                             np.real(phase*difference(u))]) / math.pi

        integral, error, info = quad_vec(integrand, 0., np.inf, epsabs=tolerance,
                                        epsrel=tolerance, norm='max', limit=1000,
                                        full_output=True)
        if not info.success or not np.all(np.isfinite(integral)):
            raise ValueError('Intégration Fourier Heston non convergée.')
        evaluations = int(info.neval)
        calls += prepaid*integral[0]-k*df*integral[1]
        digitals -= df*integral[1]
    intrinsic = np.maximum(prepaid-k*df, 0)
    bound = max(5e-10, float(error)*float(np.max(prepaid+k*df))*4)
    if (not np.all(np.isfinite(calls)) or not np.all(np.isfinite(digitals))
            or np.any(calls < intrinsic-bound) or np.any(calls > prepaid+bound)
            or np.any(digitals < -bound) or np.any(digitals > df+bound)):
        raise ValueError('Prix Fourier Heston hors des bornes d’arbitrage.')
    corrected_calls = np.clip(calls, intrinsic, prepaid)
    corrected_digitals = np.clip(digitals, 0, df)
    correction = max(float(np.max(abs(calls-corrected_calls))),
                     float(np.max(abs(digitals-corrected_digitals))))
    return corrected_calls, corrected_digitals, {
        'method': 'adaptive-infinite-Fourier-BS-control-variate',
        'absolute_tolerance': tolerance, 'integration_error_estimate': float(error),
        'evaluations': evaluations, 'roundoff_correction_max_bp': correction*10000,
    }


def heston_calls(parameters, expiries, strikes, rate, dividend):
    return heston_prices(parameters, expiries, strikes, rate, dividend)[0]


def qualification(success, vanilla_error_bp, digital_error_bp, restrictions=()):
    reasons = list(restrictions)
    if not success:
        reasons.append('Optimisation non convergée.')
    if not math.isfinite(vanilla_error_bp) or vanilla_error_bp > THRESHOLDS_BP['vanilla']:
        reasons.append('Écart vanille supérieur à 5 pb.')
    if not math.isfinite(digital_error_bp) or digital_error_bp > THRESHOLDS_BP['digital']:
        reasons.append('Écart digitale supérieur à 10 pb.')
    return {'qualified': not reasons, 'reasons': reasons,
            'thresholds_bp': dict(THRESHOLDS_BP),
            'scope': 'Published vanilla/digital control points, flat deterministic carry only',
            'production_approved': False}


def calibrate_surface(payload, model, horizon, rate=.03, dividend=.02):
    if model not in ('heston', 'sabr', 'lsv') or not math.isfinite(horizon) or horizon <= 0:
        raise ValueError('Modèle ou horizon de calibration invalide.')
    surface = TermSSVISurface(payload)
    requested_horizon = horizon
    horizon = min(horizon, surface.max_expiry, 10.)
    # Every material target pillar is an objective point, including edited 7Y.
    expiries = sorted({min(t, horizon) for t in (.5, 1., 2., 4., horizon)} |
                      {float(t) for t, _ in surface.nodes if t <= horizon})
    strikes = np.array([.6, .8, 1., 1.2, 1.5])
    target = [surface.vanillas(strikes, t, rate, dividend) for t in expiries]
    calls, digitals = np.array([p[0] for p in target]), np.array([p[2] for p in target])
    atm = math.sqrt(surface._theta(min(1., horizon))[0]/min(1., horizon))
    vegas = []
    for t in expiries:
        w = surface.derivatives(np.log(strikes)-(rate-dividend)*t, t)[0]
        d1 = -(np.log(strikes)-(rate-dividend)*t)/np.sqrt(w)+np.sqrt(w)/2
        vegas.append(np.maximum(.03, math.exp(-dividend*t)*np.exp(-d1*d1/2)
                                /math.sqrt(2*math.pi)*math.sqrt(t)))
    vegas = np.asarray(vegas)
    restrictions = []
    if requested_horizon > horizon:
        restrictions.append('Horizon demandé non couvert intégralement.')
    if model in ('heston', 'lsv'):
        keys = ('v0', 'theta', 'kappa', 'xi', 'rho_h')
        initial = [atm**2, atm**2, 1., max(.15, atm), surface.rho]
        bounds = ([.0001, .0001, .05, .01, -.98], [2., 2., 12., 3., .98])
        evaluate = lambda x: heston_prices(dict(zip(keys, x)), expiries, strikes, rate, dividend)
        method = 'Fourier Heston'
        if model == 'lsv':
            restrictions.append('Composante Heston seule : le modèle LSV complet n’est pas qualifié par cet ajustement.')
    else:
        from .payscript.engine import _simulate_sabr
        keys = ('alpha', 'beta', 'rho', 'nu')
        initial = [atm, 1., surface.rho, .5]
        bounds = ([.01, .05, -.98, .01], [2., 1., .98, 2.])
        ts = max(1, round(horizon*104))
        dt, pairs = horizon/ts, 3000
        rng = np.random.default_rng(353)
        z = rng.standard_normal((ts, 1, pairs))
        zv = rng.standard_normal(z.shape)
        indices = [max(1, round(t/dt)) for t in expiries]
        modeled_expiries = [i*dt for i in indices]
        restrictions.append('SABR exploratoire : bruit Monte Carlo et erreur de discrétisation non qualifiés indépendamment.')
        def evaluate(x):
            params = dict(zip(keys, x), q=dividend)
            levels = [_simulate_sabr(ts, 1, pairs, dt, math.sqrt(dt), [params], rate,
                                     np.eye(1), sign*z, sign*zv)[indices, 0]
                      for sign in (1., -1.)]
            rows, digital_rows = [], []
            for i, t in enumerate(modeled_expiries):
                a, b = (v[i, :, None] for v in levels)
                call = .5*(np.maximum(a-strikes, 0)+np.maximum(b-strikes, 0)).mean(axis=0)*math.exp(-rate*t)
                put = .5*(np.maximum(strikes-a, 0)+np.maximum(strikes-b, 0)).mean(axis=0)*math.exp(-rate*t)
                rows.append(np.where(strikes < math.exp((rate-dividend)*t),
                            put+math.exp(-dividend*t)-strikes*math.exp(-rate*t), call))
                digital_rows.append(.5*((a < strikes).astype(float)+(b < strikes)).mean(axis=0)*math.exp(-rate*t))
            return np.array(rows), np.array(digital_rows), {'modeled_expiries': modeled_expiries,
                   'pairs': pairs, 'steps_per_year': 104, 'seed': 353}
        method = 'SABR spot MC, 3 000 paires, 104 pas/an, graine 353'
    fit = least_squares(lambda x: ((evaluate(x)[0]-calls)/vegas).ravel(), initial,
                        bounds=bounds, max_nfev=65, diff_step=.003,
                        ftol=1e-6, xtol=1e-6, gtol=1e-6)
    prices, digital_prices, numerical = evaluate(fit.x)
    if not np.all(np.isfinite(prices)) or not np.all(np.isfinite(digital_prices)):
        raise ValueError('La calibration a produit des prix non finis.')
    vanilla_error = float(np.max(abs(prices-calls))*10000)
    digital_error = float(np.max(abs(digital_prices-digitals))*10000)
    checks = qualification(bool(fit.success), vanilla_error, digital_error, restrictions)
    parameters = dict(zip(keys, map(float, fit.x)))
    dossier = {
        'version': 1, 'method_version': METHOD_VERSION, 'model': model,
        'implementation_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'libraries': {'numpy': np.__version__, 'scipy': scipy.__version__},
        'target': deepcopy(payload), 'source': 'Synthetic editable assumption, not market quotes',
        'context': {'requested_horizon': requested_horizon, 'fit_horizon': horizon,
                    'rate': rate, 'dividend': dividend, 'spot': 1.},
        'grid': {'expiries': expiries, 'strikes': strikes.tolist(),
                 'strike_unit': 'spot-normalized', 'weights': (1/vegas).tolist(),
                 'objective': 'vega-weighted vanilla least squares',
                 'excluded_pillars': [{'expiry': float(t), 'reason': 'Beyond fit horizon'}
                                      for t, _ in surface.nodes if t > horizon]},
        'parameters': parameters, 'method': method, 'numerical': numerical,
        'optimizer': {'success': bool(fit.success), 'status': int(fit.status),
                      'message': str(fit.message), 'nfev': int(fit.nfev),
                      'cost': float(fit.cost), 'optimality': float(fit.optimality),
                      'initial_parameters': dict(zip(keys, initial)),
                      'lower_bounds': dict(zip(keys, bounds[0])),
                      'upper_bounds': dict(zip(keys, bounds[1])),
                      'max_nfev': 65, 'diff_step': .003,
                      'ftol': 1e-6, 'xtol': 1e-6, 'gtol': 1e-6},
        'controls': {'target_calls': calls.tolist(), 'model_calls': prices.tolist(),
                     'target_put_digitals': digitals.tolist(), 'model_put_digitals': digital_prices.tolist(),
                     'max_vanilla_error_bp': vanilla_error, 'max_digital_error_bp': digital_error},
        'qualification': checks,
    }
    return dict(parameters=parameters, max_price_error_bp=vanilla_error,
                max_digital_error_bp=digital_error, method=method, approximate=True,
                success=bool(fit.success), qualified=checks['qualified'],
                qualification=checks, dossier=dossier,
                note='Contrôles aux points publiés ; ne qualifie ni les barrières ni le moteur Monte Carlo de production.')
