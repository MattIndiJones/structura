"""Shared factor boundaries and contractual cash conventions for valuation explain."""
from copy import deepcopy
from datetime import date
import math

ATTRIBUTION_VERSION = 'pnl-payment-v2'
CASH_BASIS = 'CONTRACTUAL_PAYMENT_DATE'
DIVIDEND_FIELDS = ('q', 'dividend_curve', 'dividend_decay')


def with_dividend_inputs(base: list[dict], target: list[dict]) -> list[dict]:
    """Change dividend inputs only, keeping diffusion, FX and identity intact."""
    if len(base) != len(target):
        raise ValueError('Univers de sous-jacents incompatible pour l’attribution des dividendes.')
    result = deepcopy(base)
    for old, new in zip(result, target):
        for key in DIVIDEND_FIELDS:
            if key in new:
                old[key] = deepcopy(new[key])
            else:
                old.pop(key, None)
    return result


def contractual_cash_in_period(payload: dict, start: date, end: date) -> list[dict]:
    """Contractual cash in (start, end]; never infer a payment from observation.

    These dated entitlements do not prove a bank transfer. Equal PAY legs remain
    distinct; deduplicating by amount/date/label would erase legitimate cash.
    """
    rows = payload.get('settled_cash_flows')
    if rows is None:
        raise ValueError('Flux contractuels à échéance absents : P&L cash indisponible.')
    result = []
    for row in rows:
        try:
            payment = date.fromisoformat(row['payment_date'])
            amount = float(row['cf'])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError('Date de paiement ou montant absent/invalide : P&L cash indisponible.') from exc
        if not math.isfinite(amount):
            raise ValueError('Montant de cash non fini : P&L indisponible.')
        if start < payment <= end:
            cash = deepcopy(row)
            cash['cf'] = amount
            result.append(cash)
    return result
