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


def validate_pricing_calibrations(request, effective_horizon: float, *, secret: str):
    """Only fresh automatic application claims qualification. Frozen lifecycle
    dossiers remain historical evidence; C18 governs their refresh separately.
    """
    if request.model not in ('heston', 'sabr', 'lsv'):
        return
    for underlying in request.underlyings:
        if not underlying.vol_surface or underlying.smile_parameter_mode == 'manual':
            continue
        dossier = verify_calibration(underlying.calibration_evidence, secret=secret)
        from ..core.smile_calibration import METHOD_VERSION, qualification
        controls = dossier['controls']
        if (not dossier['qualification']['qualified']
                or dossier['method_version'] != METHOD_VERSION
                or not qualification(dossier['optimizer']['success'],
                                     controls['max_vanilla_error_bp'],
                                     controls['max_digital_error_bp'])['qualified']):
            raise ValueError('Calibration exploratoire non qualifiée : application automatique refusée.')
        context = dossier['context']
        same = lambda a, b: math.isclose(float(a), float(b), rel_tol=1e-10, abs_tol=1e-10)
        if (dossier['model'] != request.model
                or json_transport_fingerprint(dossier['target']) !=
                json_transport_fingerprint(underlying.vol_surface.model_dump())
                or not same(context['rate'], request.r)
                or not same(context['dividend'], underlying.q)
                or not same(context['requested_horizon'], effective_horizon)
                or not same(context['fit_horizon'], effective_horizon)
                or any(not same(value, getattr(underlying, key))
                       for key, value in dossier['parameters'].items())):
            raise ValueError('Calibration périmée : cible, horizon, taux, dividende ou paramètres modifiés.')
        surface = underlying.vol_surface
        from ..core.volatility_surface import TermSSVISurface
        reference = math.sqrt(TermSSVISurface(surface.model_dump())._theta(1.)[0])
        if not same(underlying.sigma, reference):
            raise ValueError('Niveau de volatilité modifié depuis la calibration.')
        if (request.yield_curve or request.sigma_r or underlying.dividend_curve
                or underlying.dividend_decay or underlying.ccyh
                or underlying.sigma_fx*underlying.rho_sfx):
            raise ValueError('Calibration qualifiée uniquement à taux et dividende plats, sans quanto. Choisissez des hypothèses manuelles explicites pour ce contexte.')
