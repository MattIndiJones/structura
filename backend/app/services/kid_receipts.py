"""Server evidence for indicative KID calculations and their retained contract."""
from __future__ import annotations

from datetime import datetime
import hashlib
import hmac
from pathlib import Path

from ..core.instance_signing import receipt_signing_secret
from ..core.product.inputs import terms_from_input
from ..core.valuation_context import json_transport_fingerprint, json_transport_json
from ..core.valuation_runs import calculation_identity


RESULT_FIELDS = ('sri', 'mrm', 'crm', 'vev', 'T_rhp', 'horizons', 'costs')
DOMAIN = 'structura-indicative-kid-v1:'


def _seal(claims):
    signature = hmac.new(receipt_signing_secret().encode(),
        (DOMAIN + json_transport_json(claims)).encode(), hashlib.sha256).hexdigest()
    return {**claims, 'server_signature': signature}


def _verify(receipt):
    if not isinstance(receipt, dict) or receipt.get('version') != 1:
        raise ValueError('Preuve de calcul KID absente ou inconnue. Recalculez le KID.')
    claims = {k: v for k, v in receipt.items() if k != 'server_signature'}
    if not hmac.compare_digest(_seal(claims)['server_signature'], str(receipt.get('server_signature', ''))):
        raise ValueError('La preuve de calcul KID a été modifiée. Recalculez le KID.')
    return claims


def _check_result(claims, values):
    calculated = {k: claims['result'][k] for k in RESULT_FIELDS}
    supplied = {k: values[k] for k in RESULT_FIELDS}
    if json_transport_fingerprint(calculated) != json_transport_fingerprint(supplied):
        raise ValueError('Les chiffres KID ne correspondent plus au calcul serveur. Recalculez le KID.')


def issue_kid_receipt(request, result, user, product=None):
    payload = request.model_dump(mode='json')
    terms = product.terms if product else terms_from_input(payload, allow_unresolved=True)
    identity = calculation_identity()
    identity['kid_implementation_sha256'] = hashlib.sha256(
        (Path(__file__).parent.parent / 'api/kid.py').read_bytes() + Path(__file__).read_bytes()).hexdigest()
    return _seal({'version': 1, 'methodology_status': 'INDICATIVE_NON_PRIIPS',
        'user_id': user.id, 'entity_id': user.entity_id,
        'product_id': product.product_id if product else None,
        'product_terms_version': product.terms_version if product else None,
        'terms_fingerprint': json_transport_fingerprint(terms.model_dump(mode='json')),
        'calculated_at': datetime.utcnow().isoformat(), 'input': payload,
        'calculation_identity': identity, 'result': result})


def bind_kid_receipt(receipt, values, user, product):
    claims = _verify(receipt)
    if claims['user_id'] != user.id or claims['entity_id'] != user.entity_id:
        raise ValueError('La preuve KID appartient à un autre utilisateur ou une autre organisation.')
    if claims['product_id'] is not None and (
            claims['product_id'] != product.product_id or claims['product_terms_version'] != product.terms_version):
        raise ValueError('La preuve KID vise un autre Product ou une ancienne version. Recalculez le KID.')
    if claims['terms_fingerprint'] != json_transport_fingerprint(product.terms.model_dump(mode='json')):
        raise ValueError('Les termes du Product diffèrent du calcul KID. Recalculez le KID.')
    _check_result(claims, values)
    return _seal({**claims, 'retained_product_id': product.product_id,
                  'retained_terms_version': product.terms_version})


def archived_kid_status(receipt, row):
    if not receipt:
        return 'LEGACY_UNVERIFIED'
    try:
        claims = _verify(receipt)
        _check_result(claims, row)
        if (claims['user_id'] != row['user_id'] or claims.get('retained_product_id') != row['product_id']
                or claims.get('retained_terms_version') != row['product_terms_version']):
            return 'INVALID_EVIDENCE'
    except (ValueError, KeyError, TypeError):
        return 'INVALID_EVIDENCE'
    return 'SERVER_COMPUTED'
