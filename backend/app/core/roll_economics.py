"""Explicit cash budget and recovery on the original holder's nominal basis."""
from __future__ import annotations

import math
import re
from datetime import date
from statistics import median
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


class RollFinancing(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    exit_basis: Literal['model', 'model_haircut', 'observed_bid'] = 'model'
    bid_pct: float | None = Field(default=None, ge=0)
    bid_source: str = Field(default='', max_length=300)
    bid_observed_at: AwareDatetime | None = None
    haircut_points: float = Field(default=0, ge=0)
    exit_cost_points: float = Field(default=0, ge=0)
    entry_cost_points: float = Field(default=0, ge=0)

    @model_validator(mode='after')
    def explicit_basis(self):
        self.bid_source = self.bid_source.strip()
        if self.exit_basis == 'observed_bid':
            if self.bid_pct is None or len(self.bid_source) < 3 or self.bid_observed_at is None:
                raise ValueError('Un bid observé exige son niveau, sa source et un horodatage avec fuseau.')
        elif self.bid_pct is not None or self.bid_source or self.bid_observed_at is not None:
            raise ValueError('Les données de bid sont réservées au mode bid observé.')
        if self.exit_basis != 'model_haircut' and self.haircut_points != 0:
            raise ValueError('La décote est réservée au mode modèle avec décote.')
        return self


def roll_budget(model_exit: float, model_entry: float, assumptions: RollFinancing,
                *, valuation_date: str | None, calculated_at: str) -> tuple[float, dict]:
    if not math.isfinite(model_exit) or model_exit < 0:
        raise ValueError('Le prix modèle de sortie doit être fini et positif ou nul.')
    if not math.isfinite(model_entry) or model_entry <= 0:
        raise ValueError('Le prix modèle de la nouvelle note doit être fini et strictement positif.')
    age = None
    if assumptions.exit_basis == 'observed_bid':
        gross = assumptions.bid_pct / 100
        if valuation_date:
            age = (date.fromisoformat(str(valuation_date)[:10]) - assumptions.bid_observed_at.date()).days
            if age < 0:
                raise ValueError('Le bid est postérieur à la date de valorisation comparée.')
    else:
        gross = model_exit - assumptions.haircut_points / 100
    proceeds = gross - assumptions.exit_cost_points / 100
    entry = model_entry + assumptions.entry_cost_points / 100
    if proceeds < 0:
        raise ValueError('Le produit net de cession est négatif : le roll ne se finance pas sans apport explicite.')
    if not all(math.isfinite(value) for value in (gross, proceeds, entry)) or entry <= 0:
        raise ValueError('Les prix nets du roll doivent être finis et le prix d’entrée strictement positif.')
    quantity = proceeds / entry
    if not math.isfinite(quantity):
        raise ValueError('La quantité réinvestie n’est pas finie.')
    return quantity, {
        **assumptions.model_dump(mode='json'),
        'model_exit_price': model_exit, 'model_entry_price': model_entry,
        'gross_exit_price': gross, 'net_exit_proceeds': proceeds, 'entry_unit_price': entry,
        'bid_age_calendar_days': age, 'model_calculated_at': calculated_at,
        'valuation_date': valuation_date,
        'exit_evidence': 'OBSERVED_BID_INPUT' if assumptions.exit_basis == 'observed_bid' else 'MODEL_HYPOTHESIS',
        'cost_units': 'price_points', 'exit_cost_basis': 'original_nominal',
        'entry_cost_basis': 'new_nominal', 'recovery_basis': 'original_nominal_future_undiscounted_flows',
        'exit_price_convention': 'all_rights_sold_same_value_basis_as_model_before_explicit_costs',
    }


def fixed_maturity_cap(script: str) -> float | None:
    """Prove only a narrow fixed-payment contract; never infer a cap from paths.

    Pricing already validates the PayScript. Any declaration, parameter, state,
    condition, intermediate date or nonliteral expression leaves the cap unknown.
    """
    lines = [line.split('#', 1)[0].strip() for line in script.splitlines()]
    lines = [line for line in lines if line]
    if len(lines) < 2 or not re.fullmatch(r'AT\s+MATURITY\s*:?', lines[0], re.I):
        return None
    values = []
    for line in lines[1:]:
        match = re.fullmatch(r'PAY\s+([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)(%)?(?:\s+"[^"\n]*")?', line, re.I)
        if not match:
            return None
        value = float(match[1]) / (100 if match[2] else 1)
        if not math.isfinite(value):
            return None
        values.append(value)
    try:
        total = math.fsum(values)
    except OverflowError:
        return None
    return total if math.isfinite(total) else None


def recovery_summary(result: dict, quantity: float, *, script: str | None = None) -> dict:
    raw = result.get('payoffs') or []
    values = [float(value) * quantity for value in raw]
    if any(not math.isfinite(value) for value in values):
        raise ValueError('Distribution de récupération non finie ; comparaison indisponible.')
    cap = fixed_maturity_cap(script) if script is not None else None
    cap = None if cap is None else cap * quantity
    if cap is not None and (not math.isfinite(cap) or any(value > cap + 1e-9 for value in values)):
        cap = None
    return {
        'reinvested_notional': quantity,
        'recovery_mean': math.fsum(value / len(values) for value in values) if values else None,
        'recovery_median': median(values) if values else None,
        'recovery_sample_max': max(values) if values else None,
        'recovery_paths': len(values),
        'plafond': cap,
        'recovery_cap_method': 'FIXED_LITERAL_MATURITY_PAYMENTS' if cap is not None else 'NOT_PROVEN',
    }
