"""Server-authenticated calibration dossiers, archived with pricing inputs."""
from copy import deepcopy
from datetime import datetime, timezone
import hmac
import math

from .product_receipts import _signature
from ..core.valuation_context import json_transport_fingerprint

_DOMAIN = 'surface-calibration-v1:'


def sign_calibration(dossier: dict, *, secret: str) -> dict:
    claims = {'version': 1, 'issued_at': datetime.now(timezone.utc).isoformat(),
              'dossier': deepcopy(dossier)}
    return {**claims, 'server_signature': _signature(secret, claims, domain=_DOMAIN)}


def verify_calibration(evidence: dict, *, secret: str) -> dict:
    if not isinstance(evidence, dict) or evidence.get('version') != 1:
        raise ValueError('Preuve de calibration absente ou inconnue. Recalibrez explicitement.')
    claims = {k: v for k, v in evidence.items() if k != 'server_signature'}
    try:
        expected = _signature(secret, claims, domain=_DOMAIN)
    except (ValueError, TypeError) as exc:
        raise ValueError('Preuve de calibration non sérialisable.') from exc
    if not hmac.compare_digest(expected, str(evidence.get('server_signature') or '')):
        raise ValueError('Preuve serveur de calibration invalide ou modifiée.')
    return deepcopy(claims['dossier'])


def validate_pricing_calibrations(request, effective_horizon: float, *, secret: str,
                                  allow_indicative_heston=False):
    """Only fresh automatic application claims qualification. Frozen lifecycle
    dossiers remain historical evidence; C18 governs their refresh separately.
    """
    if request.model not in ('heston', 'sabr', 'lsv'):
        return
    for underlying in request.underlyings:
        if not allow_indicative_heston and (
            not underlying.vol_surface or underlying.smile_parameter_mode == 'manual'
        ):
            continue
        scenario_fit = request.model == 'heston' and underlying.vol_surface is not None and (
            underlying.vol_surface.atm_scenario is not None)
        if allow_indicative_heston and (not scenario_fit or underlying.smile_parameter_mode == 'manual'):
            raise ValueError('Le MTF indicatif exige une calibration Heston signée sur une courbe ATM par scénario.')
        dossier = verify_calibration(underlying.calibration_evidence, secret=secret)
        from ..core.smile_calibration import HESTON_FIT_MODES, METHOD_VERSION, qualification
        controls = dossier['controls']
        heston_fit = dossier.get('heston_fit') if scenario_fit else None
        optional_fit = heston_fit is not None and heston_fit.get('mode') in HESTON_FIT_MODES
        checks = {'qualified': True, 'reasons': []} if optional_fit else qualification(
            dossier['optimizer']['success'], controls['max_vanilla_error_bp'],
            controls['max_digital_error_bp'],
            vanilla_limit_bp=heston_fit.get('vanilla_limit_bp') if heston_fit is not None else None)
        qualified = dossier['qualification']['qualified'] and checks['qualified']
        if (dossier['method_version'] != METHOD_VERSION or not dossier['optimizer']['success']
                or (not qualified and not allow_indicative_heston)):
            reasons = ' '.join(dossier['qualification']['reasons'] or checks['reasons'])
            raise ValueError(f'Calibration exploratoire non qualifiée. {reasons}'.strip())
        context = dossier['context']
        same = lambda a, b: math.isclose(float(a), float(b), rel_tol=1e-10, abs_tol=1e-10)
        horizon_matches = (same(context['fit_horizon'], 10.) and effective_horizon <= 10. + 1e-9
                           if scenario_fit else same(context['requested_horizon'], effective_horizon)
                           and same(context['fit_horizon'], effective_horizon))
        if (dossier['model'] != request.model
                or json_transport_fingerprint(dossier['target']) !=
                json_transport_fingerprint(underlying.vol_surface.model_dump())
                or not same(context['rate'], request.r)
                or not same(context['dividend'], underlying.q)
                or not horizon_matches
                or any(not same(value, getattr(underlying, key))
                       for key, value in dossier['parameters'].items())):
            raise ValueError('Calibration périmée : cible, horizon, taux, dividende ou paramètres modifiés.')
        surface = underlying.vol_surface
        from ..core.volatility_surface import TermSSVISurface
        reference = math.sqrt(TermSSVISurface(surface.model_dump())._theta(1.)[0])
        # The editor displays ATM volatility to six decimal places in percent.
        if not math.isclose(underlying.sigma, reference, rel_tol=1e-10, abs_tol=5.1e-9):
            raise ValueError('Niveau de volatilité modifié depuis la calibration.')
        if (request.yield_curve or request.sigma_r or underlying.dividend_curve
                or underlying.dividend_decay or underlying.ccyh
                or underlying.sigma_fx*underlying.rho_sfx):
            raise ValueError('Calibration qualifiée uniquement à taux et dividende plats, sans quanto. Choisissez des hypothèses manuelles explicites pour ce contexte.')
