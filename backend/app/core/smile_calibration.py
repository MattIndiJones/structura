"""Reproducible fits and bounded diagnostics of synthetic SSVI targets."""
import math
from copy import deepcopy
from functools import lru_cache
import hashlib
from pathlib import Path

import numpy as np
import scipy
from scipy.integrate import quad_vec
from scipy.optimize import least_squares, minimize
from scipy.special import ndtr

from .volatility_surface import TermSSVISurface

METHOD_VERSION = 'surface-fit-v2'
THRESHOLDS_BP = {'vanilla': 5., 'digital': 10.}
HESTON_FIT_MODES = ('atm', 'atm_digital', 'atm_smile')


@lru_cache(maxsize=1)
def _search_quadrature():
    nodes, weights = np.polynomial.legendre.leggauss(192)
    unit = (nodes+1.)/2.
    return (12.*unit/(1.-unit))[:, None, None], weights*6./(1.-unit)**2


def heston_prices(parameters, expiries, strikes, rate, dividend, *, tolerance=1e-8,
                  search=False):
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

        if search:
            nodes, weights = _search_quadrature()
            integral = np.sum(integrand(nodes)*weights[None, :, None, None], axis=1)
            evaluations = len(weights)
        else:
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
            or (not search and (np.any(calls < intrinsic-bound) or np.any(calls > prepaid+bound)
                                or np.any(digitals < -bound) or np.any(digitals > df+bound)))):
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


def qualification(success, vanilla_error_bp, digital_error_bp, restrictions=(), *, vanilla_limit_bp=None):
    thresholds = dict(THRESHOLDS_BP)
    if vanilla_limit_bp is not None:
        thresholds['vanilla'] = vanilla_limit_bp
    reasons = list(restrictions)
    if not success:
        reasons.append('Optimisation non convergée.')
    if not math.isfinite(vanilla_error_bp) or vanilla_error_bp > thresholds['vanilla']:
        reasons.append(f"Écart vanille supérieur à {thresholds['vanilla']:g} pb.")
    if not math.isfinite(digital_error_bp) or digital_error_bp > THRESHOLDS_BP['digital']:
        reasons.append('Écart digitale supérieur à 10 pb.')
    return {'qualified': not reasons, 'reasons': reasons,
            'thresholds_bp': thresholds,
            'scope': 'Published vanilla/digital control points, flat deterministic carry only',
            'production_approved': False}


def _fit_atm_priority(evaluate, search_prices, calls, vegas, initial, bounds):
    atm = 2
    price_convergence_bp = .05
    starts = [initial, [initial[0], initial[1], .3, .35, -.65]]
    fits = []
    for start in starts:
        try:
            fits.append(least_squares(
                lambda x: 1e4 * (search_prices(x)[:, atm] - calls[:, atm]), start,
                bounds=bounds, max_nfev=250, diff_step=.001,
                ftol=1e-7, xtol=1e-7, gtol=1e-7))
        except (ValueError, FloatingPointError):
            continue
    if not fits:
        raise ValueError('Aucun ajustement Heston ATM numériquement admissible.')
    fit = min(fits, key=lambda candidate: (
        not (candidate.success or np.max(np.abs(candidate.fun)) <= price_convergence_bp),
        candidate.cost))
    base_error = evaluate(fit.x)[0] - calls
    atm_max = float(1e4*np.max(np.abs(base_error[:, atm])))
    if np.max(np.abs(base_error[:, atm]*1e4-fit.fun)) > price_convergence_bp:
        raise ValueError('La vérification Fourier de l’ajustement ATM dépasse 0,05 pb.')
    solver_converged = bool(fit.success)
    if not fit.success and atm_max <= price_convergence_bp:
        fit.success = True
        fit.message = 'Tous les prix ATM sont à moins de 0,05 pb en Fourier adaptatif.'
    cap = max(THRESHOLDS_BP['vanilla'], atm_max + .5)
    wings = [0, 1, 3, 4]

    @lru_cache(maxsize=32)
    def residual(parameters):
        return search_prices(parameters) - calls

    def wing_loss(x):
        error = 1e2 * residual(tuple(x))[:, wings] / vegas[:, wings]
        return float(np.mean(error**2))

    def atm_constraint(x):
        error = 1e4 * residual(tuple(x))[:, atm]
        return np.r_[cap - error, cap + error]

    parameters = fit.x
    if fit.success:
        try:
            refined = minimize(wing_loss, fit.x, method='SLSQP', bounds=list(zip(*bounds)),
                               constraints=[{'type': 'ineq', 'fun': atm_constraint}],
                               options={'maxiter': 70, 'ftol': 1e-7})
            if (np.all(atm_constraint(refined.x) >= -1e-5) and wing_loss(refined.x) < wing_loss(fit.x)):
                final_error = evaluate(refined.x)[0] - calls
                if (1e4*np.max(np.abs(final_error[:, atm])) <= cap + 1e-5
                        and np.mean((final_error[:, wings]/vegas[:, wings])**2)
                        < np.mean((base_error[:, wings]/vegas[:, wings])**2)):
                    parameters = refined.x
        except (ValueError, FloatingPointError):
            # The converged ATM solution is the feasible starting point.
            pass
    return fit, parameters, dict(atm_first_max_bp=atm_max, atm_constraint_bp=cap,
                                 solver_converged=solver_converged,
                                 wing_refined=parameters is not fit.x)


def _fit_heston_max_error(evaluate, search, calls, digitals, initial, bounds, vanilla_limit):
    limits = np.array([vanilla_limit, THRESHOLDS_BP['digital']])[:, None, None]
    target = np.stack((calls, digitals))

    @lru_cache(maxsize=32)
    def residual(parameters):
        return ((np.stack(search(parameters)[:2])-target)*1e4/limits).ravel()

    def constraints(x):
        errors = residual(tuple(x[:-1]))
        return np.r_[x[-1]-errors, x[-1]+errors]

    candidates = []
    starts = [initial, [initial[0], initial[1], .3, .7, initial[-1]],
              [initial[0], initial[1], 4., 1.2, initial[-1]]]
    for start in starts:
        try:
            seed = least_squares(lambda x: residual(tuple(x)), start, bounds=bounds,
                                 max_nfev=90, diff_step=.001, ftol=1e-6)
        except (ValueError, FloatingPointError):
            continue
        worst = float(np.max(np.abs(seed.fun)))
        trial = [(seed, seed.x)]
        try:
            refined = minimize(lambda x: x[-1], np.r_[seed.x, worst+1e-4],
                               method='SLSQP', bounds=[*zip(*bounds), (0., None)],
                               constraints=[{'type': 'ineq', 'fun': constraints}],
                               options={'maxiter': 100, 'ftol': 1e-7})
            trial.append((refined, refined.x[:-1]))
        except (ValueError, FloatingPointError):
            pass
        for fit, parameters in trial:
            try:
                prices, digital_prices, _ = evaluate(parameters)
            except (ValueError, FloatingPointError):
                continue
            error = (np.stack((prices, digital_prices))-target)*1e4/limits
            score = float(np.max(np.abs(error)))
            candidates.append((not fit.success, score, fit, parameters))
    if not candidates:
        raise ValueError('Aucun ajustement Heston numériquement admissible.')
    _, score, fit, parameters = min(candidates, key=lambda item: item[:2])
    return fit, parameters, dict(starts=len(starts), normalized_max_error=score)


def _fit_heston_atm(evaluate, search, calls, digitals, initial, bounds, mode, atm_index, barrier_columns):
    def errors(prices):
        vanilla = 1e4 * (prices[0][:, atm_index] - calls[:, atm_index])
        groups = [vanilla]
        if mode == 'atm_digital':
            groups.append((1e4 * (prices[1][:, barrier_columns] - digitals[:, barrier_columns])).ravel())
        return np.concatenate([group / np.sqrt(group.size) for group in groups])

    starts = [initial, [initial[0], initial[1], .3, .7, initial[-1]],
              [initial[0], initial[1], 4., 1.2, initial[-1]]]
    candidates = []
    for start in starts:
        try:
            fit = least_squares(lambda x: errors(search(x)), start, bounds=bounds,
                                max_nfev=120, diff_step=.001, ftol=1e-6)
            verified = errors(evaluate(fit.x))
            candidates.append((float(np.linalg.norm(verified)), fit))
        except (ValueError, FloatingPointError):
            continue
    if not candidates:
        raise ValueError('Aucun ajustement Heston numériquement admissible.')
    score, fit = min(candidates, key=lambda item: item[0])
    return fit, fit.x, dict(starts=len(starts), verified_objective_bp=score)


def _refine_heston_smile(evaluate, search, calls, vegas, baseline, initial, bounds, atm_index, wings):
    """Fit all eight wings per expiry inside a hard per-expiry ATM budget."""
    def wing_loss(error):
        return float(np.mean(np.square(100 * error[:, wings] / vegas[:, wings])))

    base_error = evaluate(baseline)[0] - calls
    atm_max = float(1e4 * np.max(np.abs(base_error[:, atm_index])))
    # Protect a verified fit within 5 bp, otherwise allow at most 0.5 bp
    # beyond the best verified ATM-only candidate.
    limit = THRESHOLDS_BP['vanilla']
    cap = limit if atm_max <= limit else atm_max + .5
    base_loss = best_loss = wing_loss(base_error)
    parameters = baseline
    selected = None

    @lru_cache(maxsize=32)
    def search_error(x):
        return search(x)[0] - calls

    def atm_constraint(x):
        error_bp = 1e4 * search_error(tuple(x))[:, atm_index]
        return np.r_[cap - error_bp, cap + error_bp]

    for start in (baseline, initial):
        try:
            fit = minimize(lambda x: wing_loss(search_error(tuple(x))), start,
                           method='SLSQP', bounds=list(zip(*bounds)),
                           constraints=[{'type': 'ineq', 'fun': atm_constraint}],
                           options={'maxiter': 100, 'ftol': 1e-8})
            error = evaluate(fit.x)[0] - calls
            loss = wing_loss(error)
            if 1e4 * np.max(np.abs(error[:, atm_index])) <= cap + 1e-5 and loss < best_loss - 1e-10:
                parameters, best_loss, selected = fit.x, loss, fit
        except (ValueError, FloatingPointError):
            continue

    return parameters, dict(atm_first_max_bp=atm_max, atm_constraint_bp=cap,
                            wing_refined=selected is not None,
                            wing_solver_converged=bool(selected.success) if selected is not None else None,
                            wing_solver_iterations=int(selected.nit) if selected is not None else None,
                            wing_points=int(calls.shape[0] * len(wings)),
                            wing_rms_before_vol_points=math.sqrt(base_loss),
                            wing_rms_after_vol_points=math.sqrt(best_loss))


def calibrate_surface(payload, model, horizon, rate=.03, dividend=.02, *, heston_fit=None):
    if model not in ('heston', 'sabr', 'lsv') or not math.isfinite(horizon) or horizon <= 0:
        raise ValueError('Modèle ou horizon de calibration invalide.')
    surface = TermSSVISurface(payload)
    requested_horizon = horizon
    atm_priority = model == 'heston' and payload.get('atm_scenario') is not None
    if heston_fit is not None and not atm_priority:
        raise ValueError('Le solveur Heston explicite exige une courbe ATM par scénario.')
    fit_mode = heston_fit.get('mode') if heston_fit is not None else None
    if fit_mode is not None and fit_mode not in HESTON_FIT_MODES:
        raise ValueError('Objectif de calibration Heston invalide.')
    vanilla_limit = heston_fit.get('vanilla_limit_bp') if heston_fit is not None else None
    horizon = min(horizon, surface.max_expiry, 10.)
    # Every material target pillar is an objective point, including edited 7Y.
    expiries = sorted({min(t, horizon) for t in (.5, 1., 2., 4., horizon)} |
                      {float(t) for t, _ in surface.nodes if t <= horizon})
    # Keep the historical qualification grid for legacy evidence. Explicit
    # Heston studies report the full smile; only their stated targets enter the fit.
    strikes = (np.arange(1, 10)/5 if fit_mode else np.array([.6, .8, 1., 1.2, 1.5]))
    atm_index = int(np.flatnonzero(strikes == 1.)[0])
    wing_columns = np.flatnonzero(strikes != 1.)
    barrier_strikes = [.6, 1.]
    barrier_columns = slice(len(strikes), None)
    if atm_priority:
        horizon = 10.
        expiries = list(range(1, 11))
        # Each row contains the smile in forward moneyness and the two
        # contractual Athena strikes in spot moneyness for diagnostics.
        strike_rows = np.column_stack((np.exp((rate-dividend)*np.array(expiries))[:, None]*strikes,
                                       np.tile(barrier_strikes, (len(expiries), 1))))
    else:
        strike_rows = np.broadcast_to(strikes, (len(expiries), len(strikes)))
    target = [surface.vanillas(row, t, rate, dividend) for row, t in zip(strike_rows, expiries)]
    calls, digitals = np.array([p[0] for p in target]), np.array([p[2] for p in target])
    atm = math.sqrt(surface._theta(min(1., horizon))[0]/min(1., horizon))
    vegas = []
    for row, t in zip(strike_rows, expiries):
        log_moneyness = np.log(row)-(rate-dividend)*t
        w = surface.derivatives(log_moneyness, t)[0]
        d1 = -log_moneyness/np.sqrt(w)+np.sqrt(w)/2
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
        evaluate = lambda x: heston_prices(dict(zip(keys, x)), expiries, strike_rows, rate, dividend)
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
    if heston_fit is not None:
        search = lambda x: heston_prices(dict(zip(keys, x)), expiries, strike_rows, rate, dividend, search=True)
        if fit_mode:
            fit, calibrated, max_error_fit = _fit_heston_atm(
                evaluate, search, calls, digitals, initial, bounds, fit_mode, atm_index, barrier_columns)
            if fit_mode == 'atm_smile':
                calibrated, smile_fit = _refine_heston_smile(
                    evaluate, search, calls, vegas, calibrated, initial, bounds, atm_index, wing_columns)
        else:
            fit, calibrated, max_error_fit = _fit_heston_max_error(
                evaluate, search, calls, digitals, initial, bounds, vanilla_limit or THRESHOLDS_BP['vanilla'])
    elif atm_priority:
        search_prices = lambda x: heston_prices(
            dict(zip(keys, x)), expiries, strike_rows, rate, dividend, search=True)[0]
        fit, calibrated, atm_fit = _fit_atm_priority(evaluate, search_prices, calls, vegas, initial, bounds)
    else:
        fit = least_squares(lambda x: ((evaluate(x)[0]-calls)/vegas).ravel(), initial,
                            bounds=bounds, max_nfev=65, diff_step=.003,
                            ftol=1e-6, xtol=1e-6, gtol=1e-6)
        calibrated = fit.x
    prices, digital_prices, numerical = evaluate(calibrated)
    if not np.all(np.isfinite(prices)) or not np.all(np.isfinite(digital_prices)):
        raise ValueError('La calibration a produit des prix non finis.')
    vanilla_error = float(np.max(abs(prices-calls))*10000)
    digital_error = float(np.max(abs(digital_prices-digitals))*10000)
    checks = (dict(qualified=not restrictions, reasons=restrictions, thresholds_bp={},
                   scope='Numerically admissible indicative approximation', production_approved=False)
              if fit_mode else qualification(bool(fit.success), vanilla_error, digital_error, restrictions,
                                             vanilla_limit_bp=vanilla_limit))
    usable = bool(fit.success) or bool(fit_mode)
    parameters = dict(zip(keys, map(float, calibrated)))
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
        'optimizer': {'success': usable, 'status': int(fit.status),
                      'message': str(fit.message), 'nfev': int(fit.nfev),
                      'cost': float(fit.cost if hasattr(fit, 'cost') else fit.fun),
                      'optimality': float(fit.optimality) if hasattr(fit, 'optimality') else None,
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
    if atm_priority:
        gap_bp = 1e4 * (prices - calls)
        dossier['grid'].update(strike_rows=strike_rows.tolist(),
                               strike_unit='forward-moneyness',
                               strike_rows_unit='spot-normalized',
                               objective='ATM first, constrained vega-weighted wings',
                               barrier_strikes_spot=barrier_strikes)
        if heston_fit is None:
            dossier['optimizer'].update(atm_fit, max_nfev=250, diff_step=.001,
                                        ftol=1e-7, xtol=1e-7, gtol=1e-7)
        else:
            dossier['heston_fit'] = dict(heston_fit)
            dossier['grid'].update(objective='Minimax normalized vanilla and digital price errors', weights=None)
            dossier['optimizer'].update(max_error_fit, max_nfev=90, diff_step=.001,
                                        ftol=1e-6, xtol=None, gtol=None)
            for name, errors in (('vanilla', gap_bp), ('digital', 1e4*(digital_prices-digitals))):
                i, j = np.unravel_index(np.argmax(abs(errors)), errors.shape)
                dossier['controls'][f'worst_{name}'] = dict(
                    expiry=expiries[i], strike_spot_pct=100*float(strike_rows[i,j]),
                    error_bp=float(errors[i,j]))
            if fit_mode:
                dossier['grid']['objective'] = {
                    'atm': 'ATM call RMS',
                    'atm_digital': 'ATM call RMS plus barrier digital RMS (squared)',
                    'atm_smile': 'ATM call RMS first, then vega-scaled wing call RMS under per-expiry ATM cap',
                }[fit_mode]
                dossier['optimizer'].update(solver_converged=bool(fit.success), max_nfev=120)
                if fit_mode == 'atm_smile':
                    dossier['optimizer'].update(smile_fit)
                    dossier['grid'].update(wing_strikes=strikes[wing_columns].tolist(),
                                           wing_weights=(1/vegas[:, wing_columns]).tolist())
                atm_i = int(np.argmax(abs(gap_bp[:, atm_index])))
                dossier['controls']['worst_atm'] = dict(expiry=expiries[atm_i],
                                                       error_bp=float(gap_bp[atm_i, atm_index]))
                barrier = 1e4*(digital_prices[:, barrier_columns]-digitals[:, barrier_columns])
                i, j = np.unravel_index(np.argmax(abs(barrier)), barrier.shape)
                dossier['controls']['worst_barrier_digital'] = dict(
                    expiry=expiries[i], strike_spot_pct=100*barrier_strikes[j],
                    error_bp=float(barrier[i, j]))
        dossier['controls'].update(
            atm_error_bp=gap_bp[:, atm_index].tolist(),
            max_atm_error_bp=float(np.max(np.abs(gap_bp[:, atm_index]))),
            max_wing_error_bp=float(np.max(np.abs(gap_bp[:, wing_columns]))),
            max_barrier_digital_error_bp=float(1e4*np.max(abs(
                digital_prices[:, barrier_columns] - digitals[:, barrier_columns]))),
            near_bounds=[key for key, value, lo, hi in zip(keys, calibrated, *bounds)
                         if min(value-lo, hi-value) <= .001*(hi-lo)],
        )
    return dict(parameters=parameters, max_price_error_bp=vanilla_error,
                max_digital_error_bp=digital_error, method=method, approximate=True,
                success=usable, qualified=checks['qualified'],
                qualification=checks, dossier=dossier,
                note='Contrôles aux points publiés ; ne qualifie ni les barrières ni le moteur Monte Carlo de production.')
