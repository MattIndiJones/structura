"""Contractual cash amount as a function of the observable at one event."""

from typing import Annotated, Literal

import numpy as np
from pydantic import Field, model_validator

from ..core.product.exotic_credit_payscript import credit_default_amounts
from ..core.product.exotic_rates_mc import (
    FixedCashflow, RangeAccrualCoupon, RateCoupon, _cashflow_amount, _compile_coupon_scripts,
)
from ..core.product.models import FrozenModel
from .exotic_valuation import ExoticRatesScenario, ExoticScenario


Axis = Literal["rate_fraction", "spread_fraction", "occupation_fraction", "recovery_fraction", "fixed"]
Identifier = Annotated[str, Field(min_length=1, max_length=200)]


class ExoticContractProfileError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class ExoticContractProfileCall(FrozenModel):
    receipt: dict = Field(min_length=1)
    flow_id: Identifier | None = None
    points: tuple[float, ...] | None = Field(default=None, min_length=1, max_length=101)

    @model_validator(mode="after")
    def increasing_points(self):
        if self.points and any(left >= right for left, right in zip(self.points, self.points[1:])):
            raise ValueError("Les points du profil doivent être distincts et croissants.")
        return self


class ContractProfileChoice(FrozenModel):
    flow_id: str
    axis: Axis
    calculation: Literal["template", "payscript", "credit_gross_default"]
    payment_time: float | None = None


class ContractProfilePoint(FrozenModel):
    x: float
    amount_eur: float
    amount_per_100: float


class ExoticContractProfileResult(FrozenModel):
    schema_version: Literal[1] = 1
    family: Literal["rates", "credit"]
    currency: Literal["EUR"] = "EUR"
    measure: Literal["undiscounted_signed_contractual_amount"] = "undiscounted_signed_contractual_amount"
    nominal_eur: float
    side: Literal["BUY", "SELL"]
    choices: tuple[ContractProfileChoice, ...]
    selected: ContractProfileChoice
    points: tuple[ContractProfilePoint, ...]
    acquired_x: float | None = None
    acquired_amount_eur: float | None = None
    minimum_x: float | None = None
    maximum_x: float | None = None
    conditions: tuple[str, ...]


def _choice(flow) -> ContractProfileChoice:
    if isinstance(flow, RangeAccrualCoupon):
        axis = "occupation_fraction"
    elif isinstance(flow, RateCoupon):
        axis = "spread_fraction" if flow.spread_index is not None else "rate_fraction"
    else:
        axis = "fixed"
    return ContractProfileChoice(
        flow_id=flow.flow_id, axis=axis, payment_time=flow.payment,
        calculation="payscript" if getattr(flow, "payscript", None) is not None else "template",
    )


def _axis_points(requested, default, minimum=None, maximum=None):
    values = np.asarray(requested if requested is not None else default, dtype=float)
    if (not 1 <= values.size <= 101 or not np.isfinite(values).all() or np.any(np.diff(values) <= 0)
            or (minimum is not None and values[0] < minimum) or (maximum is not None and values[-1] > maximum)):
        raise ExoticContractProfileError(
            "EXOTIC_CONTRACT_PROFILE_GRID", "Les points sont hors du domaine de l’observable ou de l’état acquis.",
        )
    return values


def _range_bounds(flow: RangeAccrualCoupon) -> tuple[float, float]:
    weight = sum(item.weight for item in flow.observations)
    minimum = maximum = 0.0
    for item in flow.observations:
        value = item.realized_rate
        if value is None:
            maximum += item.weight
        else:
            included = (value > flow.lower or flow.lower_inclusive and value == flow.lower) and (
                value < flow.upper or flow.upper_inclusive and value == flow.upper
            )
            if included:
                maximum += item.weight
                minimum += item.weight
    return minimum / weight, maximum / weight


def _points(values, amounts, nominal, side) -> tuple[ContractProfilePoint, ...]:
    sign = 1 if side == "BUY" else -1
    return tuple(ContractProfilePoint(x=x, amount_eur=sign * amount, amount_per_100=sign * amount / nominal * 100)
                 for x, amount in zip(values, amounts, strict=True))


def _rates_profile(scenario: ExoticRatesScenario, flow_id: str | None, points) -> ExoticContractProfileResult:
    terms, market = scenario.terms, scenario.market
    choices = tuple(_choice(flow) for flow in terms.cashflows)
    choices += tuple(
        ContractProfileChoice(flow_id=right.exercise_id, axis="fixed", payment_time=right.settlement, calculation="template")
        for right in terms.exercises
    )
    selected = (next((item for item in choices if item.axis != "fixed"), choices[0]) if flow_id is None
                else next((item for item in choices if item.flow_id == flow_id), None))
    if selected is None:
        raise ExoticContractProfileError("EXOTIC_CONTRACT_PROFILE_FLOW", "Le flux sélectionné est absent du contrat figé.")
    flow = next((flow for flow in terms.cashflows if flow.flow_id == selected.flow_id), None)
    conditions = ("Le flux est présenté à sa date de paiement, sous réserve du droit contractuel.",)
    acquired = acquired_amount = low = high = None
    if selected.axis == "fixed":
        if points is not None:
            raise ExoticContractProfileError("EXOTIC_CONTRACT_PROFILE_GRID", "Le montant fixe utilise un seul point contractuel.")
        values = (0.0,)
        if isinstance(flow, FixedCashflow):
            amounts = (flow.amount_eur,)
        else:
            right = next(right for right in terms.exercises if right.exercise_id == selected.flow_id)
            amounts = (right.redemption_eur,)
            conditions = ("Le remboursement est dû si ce droit d’exercice est exercé.",)
    elif isinstance(flow, RangeAccrualCoupon):
        low, high = _range_bounds(flow)
        values = _axis_points(points, (low,) if low == high else np.linspace(low, high, 41), low, high)
        conditions = (
            "L’axe représente la fraction pondérée des constats dans la bande, en conservant les constats acquis.",
            "La grille parcourt l’intervalle d’occupation. Les valeurs réalisables dépendent des poids discrets du contrat.",
        )
        compiled = _compile_coupon_scripts(terms).get(flow.flow_id) if flow.payscript is not None else None
        amounts = (
            terms.nominal_eur * compiled.evaluate(values.size, RANGE_FRACTION=values,
                                                  YEAR_FRACTION=flow.year_fraction, ANNUAL_RATE=flow.annual_rate)
            if compiled else terms.nominal_eur * flow.year_fraction * flow.annual_rate * values
        )
        if low == high:
            acquired, acquired_amount = low, float(amounts[0])
    else:
        acquired = flow.realized_rate
        compiled = _compile_coupon_scripts(terms).get(flow.flow_id) if flow.payscript is not None else None
        defaults = np.linspace(-.04, .08, 41) if selected.axis == "rate_fraction" else np.linspace(-.05, .05, 41)
        if acquired is not None:
            defaults = np.unique(np.append(defaults, acquired))
        values = _axis_points(points, defaults)
        state = {0.0: np.zeros(1)}

        def amount(observable):
            # Inject a hypothetical observed coupon input into the existing payoff.
            # The archived deal and all other coupon inputs are untouched.
            evaluation = flow.model_copy(update={"fixing": 0.0, "realized_rate": float(observable)})
            return float(np.asarray(_cashflow_amount(terms, evaluation, market, state, compiled)).item())

        amounts = tuple(amount(observable) for observable in values)
        if acquired is not None:
            acquired_amount = amount(acquired)
            conditions += ("Un point acquis est signalé séparément du profil conditionnel.",)
    sign = 1 if terms.side == "BUY" else -1
    return ExoticContractProfileResult(
        family="rates", nominal_eur=terms.nominal_eur, side=terms.side, choices=choices, selected=selected,
        points=_points(values, amounts, terms.nominal_eur, terms.side), acquired_x=acquired,
        acquired_amount_eur=sign * acquired_amount if acquired_amount is not None else None,
        minimum_x=low, maximum_x=high, conditions=conditions,
    )


def _credit_profile(scenario, flow_id, points) -> ExoticContractProfileResult:
    request = scenario.credit
    terms = request.contract
    if request.realized is not None:
        raise ExoticContractProfileError(
            "EXOTIC_CONTRACT_PROFILE_REALISED", "Les montants acquis après défaut sont disponibles dans le dossier du règlement.",
        )
    cln = terms.kind == "cln"
    scripted = terms.payscript is not None and terms.payscript.default is not None
    selected = ContractProfileChoice(flow_id="default_redemption" if cln else "protection",
                                     axis="recovery_fraction", calculation="payscript" if scripted else "credit_gross_default")
    if flow_id not in (None, selected.flow_id):
        raise ExoticContractProfileError("EXOTIC_CONTRACT_PROFILE_FLOW", "Le flux de crédit demandé est indisponible.")
    values = _axis_points(points, np.linspace(0., 1., 41), 0., 1.)
    amounts, _ = credit_default_amounts(
        terms.payscript, cln=cln, recovery=values, rank=terms.trigger_rank or 1,
    ) if scripted else (values if cln else 1.0 - values, None)
    gross = terms.nominal_eur * amounts
    condition = ("Remboursement brut conditionnel au défaut de référence." if cln else
                 "Protection brute conditionnelle au défaut au rang contractuel sur la période couverte.")
    return ExoticContractProfileResult(
        family="credit", nominal_eur=terms.nominal_eur, side=terms.side, choices=(selected,), selected=selected,
        points=_points(values, gross, terms.nominal_eur, terms.side), minimum_x=0., maximum_x=1.,
        conditions=(condition, "L’axe porte le recouvrement du nom déclencheur. La prime et son couru sont hors de ce montant brut."),
    )


def exotic_contract_profile(
    scenario: ExoticScenario, *, flow_id: str | None = None, points: tuple[float, ...] | None = None,
) -> ExoticContractProfileResult:
    """Read one payoff from frozen terms, with no price, market shock or discounting."""
    try:
        with np.errstate(over="raise", invalid="raise", divide="raise"):
            if isinstance(scenario, ExoticRatesScenario):
                return _rates_profile(scenario, flow_id, points)
            return _credit_profile(scenario, flow_id, points)
    except ArithmeticError as exc:
        raise ExoticContractProfileError("EXOTIC_CONTRACT_PROFILE_NUMERICAL", "Le montant sort du domaine numérique.") from exc
