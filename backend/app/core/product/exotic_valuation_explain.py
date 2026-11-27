"""Attribution of native dated valuations on frozen inputs and contractual cash."""

from collections.abc import Callable
from datetime import date, datetime, time
from math import fsum, sqrt
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import numpy as np
from pydantic import AwareDatetime, Field, field_validator, model_validator

from .credit_default import CreditDefaultContext, CreditDefaultResult
from .models import FrozenModel, FrozenObject
from .native_market import NativeValuationContext
from .rates_market import RatesMarketSelection
from .rates_pricing import FRNPriceResult, RatesPriceResult


METHOD_VERSION = "native-economic-dirty-v1"
REPLAY_TOLERANCE_PER_NOMINAL = 1e-10
Factor = Literal["time_state", "ois", "projection_basis", "credit_quotes", "calibration_recovery",
                 "funding", "volatility", "dependence"]


class ExplainUnavailable(ValueError):
    """A valuation bridge lacks the evidence needed for a causal attribution."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class ExplainIdentity(FrozenModel):
    position_id: str = Field(min_length=1)
    terms_version: int = Field(ge=1)
    terms_fingerprint: str = Field(min_length=1)
    schedule_fingerprint: str = Field(min_length=1)
    nominal_eur: float = Field(gt=0)
    side: Literal["BUY", "SELL"]
    currency: Literal["EUR"] = "EUR"
    measure: Literal["economic_dirty_pv_eur"] = "economic_dirty_pv_eur"
    value_date_convention: str = Field(min_length=1)
    settlement_timezone: str = "Europe/Paris"
    model: str = Field(min_length=1)
    engine_version: str = Field(min_length=1)
    engine_fingerprint: str = Field(min_length=1)
    numerical_protocol: str | None = None
    exercise_policy: Literal["none", "frozen", "reoptimized"] = "none"
    exercise_policy_fingerprint: str | None = None

    @field_validator("settlement_timezone")
    @classmethod
    def known_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("Le fuseau de règlement est inconnu.") from exc
        return value

    @model_validator(mode="after")
    def exercise_evidence(self):
        if self.exercise_policy != "none" and not self.exercise_policy_fingerprint:
            raise ValueError("Une politique d’exercice exige une empreinte de règle ou de protocole.")
        if self.exercise_policy == "none" and self.exercise_policy_fingerprint is not None:
            raise ValueError("L’empreinte de politique exige une convention d’exercice explicite.")
        return self


class ExplainMarket(FrozenModel):
    ois: FrozenObject | None = None
    projection_basis: FrozenObject | None = None
    credit_quotes: FrozenObject | None = None
    calibration_recovery: FrozenObject | None = None
    funding: FrozenObject | None = None
    volatility: FrozenObject | None = None
    dependence: FrozenObject | None = None


_MARKET_ORDER: tuple[Factor, ...] = (
    "ois", "projection_basis", "credit_quotes", "calibration_recovery", "funding", "volatility", "dependence",
)


class ExplainCash(FrozenModel):
    flow_id: str = Field(min_length=1)
    fact_id: str = Field(min_length=1)
    version: int = Field(ge=1)
    amount_eur: float
    effect_date: date
    available_at: AwareDatetime
    validated_at: AwareDatetime
    paid_at: AwareDatetime | None = None

    def recognized_at(self, timezone: ZoneInfo) -> datetime:
        payment = self.paid_at or datetime.combine(self.effect_date, time.min, timezone)
        if payment.astimezone(timezone).date() != self.effect_date:
            raise ExplainUnavailable("EXPLAIN_CASH_DATE", "L’heure réelle de paiement contredit sa date d’effet.")
        return max(payment, self.available_at, self.validated_at)


class ExplainScenario(FrozenModel):
    cutoff: AwareDatetime
    value_date: date
    market: ExplainMarket
    state: FrozenObject = Field(default_factory=FrozenObject)
    cash: tuple[ExplainCash, ...] = ()


class ExplainSample(FrozenModel):
    """Independent path or antithetic-pair means, in EUR and common draw order."""

    pairing_key: str = Field(min_length=1)
    independent_units: tuple[float, ...] = Field(min_length=2)


class ExplainPrice(FrozenModel):
    economic_dirty_pv_eur: float | None
    clean_pv_eur: float | None = None
    accrued_eur: float | None = None
    sample: ExplainSample | None = None
    state: Literal["available", "recovery_pending"] = "available"

    @model_validator(mode="after")
    def economic_measure(self):
        if (self.economic_dirty_pv_eur is None) != (self.state == "recovery_pending"):
            raise ValueError("La valeur nulle est distincte d’un recouvrement en attente.")
        if (self.clean_pv_eur is None) != (self.accrued_eur is None):
            raise ValueError("Le clean et le couru doivent partager la même base économique.")
        if self.state == "recovery_pending" and (self.clean_pv_eur is not None or self.sample is not None):
            raise ValueError("La valorisation en attente ne porte pas de prix.")
        return self


class ExplainSnapshot(FrozenModel):
    archive_id: str | int
    identity: ExplainIdentity
    scenario: ExplainScenario
    price: ExplainPrice


class ExplainDifferenceInterval(FrozenModel):
    independent_units: int
    standard_error_eur: float
    half_width_95_eur: float
    low_95_eur: float
    high_95_eur: float
    resolved: bool


class ExplainEffect(FrozenModel):
    factor: Factor
    delta_eur: float
    from_dirty_pv_eur: float
    to_dirty_pv_eur: float
    interval: ExplainDifferenceInterval | None = None
    credit_rebootstrap: bool = False


class ExplainPayment(FrozenModel):
    confirmation: ExplainCash
    recognized_at: AwareDatetime
    signed_eur: float


class ValuationExplain(FrozenModel):
    method: Literal["native-economic-dirty-v1"] = METHOD_VERSION
    status: Literal["attributed", "observed", "pending"]
    reason_code: str | None = None
    reason: str | None = None
    roll_convention: str
    start_archive_id: str | int
    end_archive_id: str | int
    start_cutoff: AwareDatetime
    end_cutoff: AwareDatetime
    direction: Literal["forward", "reverse"]
    exercise_policy: Literal["none", "frozen", "reoptimized"]
    from_dirty_pv_eur: float | None
    to_dirty_pv_eur: float | None
    observed_dirty_change_eur: float | None
    cash_contractual_eur: float | None = None
    contractual_pnl_eur: float | None = None
    clean_change_eur: float | None = None
    accrued_change_eur: float | None = None
    cash: tuple[ExplainPayment, ...] = ()
    effects: tuple[ExplainEffect, ...] = ()
    residual_eur: float | None = None
    start_replay_error_eur: float | None = None
    end_replay_error_eur: float | None = None
    interval: ExplainDifferenceInterval | None = None


_CONTRACT_CHECKS = (
    (("position_id", "nominal_eur", "side"), "EXPLAIN_POSITION", "La position ou son nominal a changé."),
    (("terms_version", "terms_fingerprint"), "EXPLAIN_TERMS", "Les termes exécutés ont changé."),
    (("schedule_fingerprint",), "EXPLAIN_SCHEDULE", "L’échéancier exécuté a changé."),
    (("value_date_convention", "settlement_timezone"), "EXPLAIN_VALUE_CONVENTION", "Les conventions de valeur diffèrent."),
)
_MODEL_CHECKS = (
    (("model",), "EXPLAIN_MODEL", "Les modèles de valorisation diffèrent."),
    (("engine_version", "engine_fingerprint"), "EXPLAIN_ENGINE", "L’identité du moteur a changé."),
    (("numerical_protocol",), "EXPLAIN_NUMERICAL_PROTOCOL", "Les protocoles numériques diffèrent."),
    (("exercise_policy", "exercise_policy_fingerprint"), "EXPLAIN_EXERCISE", "Les politiques d’exercice diffèrent."),
)


def _incompatibility(first: ExplainIdentity, second: ExplainIdentity, checks):
    for keys, code, message in checks:
        if any(getattr(first, key) != getattr(second, key) for key in keys):
            return ExplainUnavailable(code, message)
    return None


def _confirmed_cash(first: ExplainScenario, second: ExplainScenario, timezone: ZoneInfo, sign: int) -> tuple[ExplainPayment, ...]:
    def index(scenario: ExplainScenario):
        facts = {}
        for fact in scenario.cash:
            recognized = fact.recognized_at(timezone)
            if recognized > scenario.cutoff or fact.flow_id in facts:
                raise ExplainUnavailable(
                    "EXPLAIN_CASH_EVIDENCE", "Un paiement est dupliqué ou indisponible à l’arrêté archivé.",
                )
            facts[fact.flow_id] = (fact, recognized)
        return facts

    before, after = index(first), index(second)
    for key, (old, _) in before.items():
        if key not in after:
            raise ExplainUnavailable("EXPLAIN_CASH_EVIDENCE", "Une preuve de règlement antérieure manque à l’arrivée.")
        new, _ = after[key]
        if (old.fact_id, old.amount_eur, old.effect_date) != (new.fact_id, new.amount_eur, new.effect_date) or new.version < old.version:
            raise ExplainUnavailable(
                "EXPLAIN_CASH_REVISION", "Le cash déjà confirmé a changé. Un ajustement requiert un flux distinct.",
            )
    payments = []
    for key in after.keys() - before.keys():
        fact, recognized = after[key]
        if not first.cutoff < recognized <= second.cutoff:
            raise ExplainUnavailable("EXPLAIN_CASH_EVIDENCE", "Un règlement disponible au départ manque dans son archive.")
        payments.append(ExplainPayment(confirmation=fact, recognized_at=recognized, signed_eur=sign * fact.amount_eur))
    return tuple(sorted(payments, key=lambda row: (row.recognized_at, row.confirmation.flow_id), reverse=sign < 0))


def _dirty(price: ExplainPrice, tolerance: float) -> float:
    dirty = price.economic_dirty_pv_eur
    if dirty is None:
        raise ExplainUnavailable("EXPLAIN_RECOVERY_PENDING", "Le recouvrement est en attente à un arrêté.")
    if price.clean_pv_eur is not None and abs(dirty - (price.clean_pv_eur + price.accrued_eur)) > tolerance:
        raise ExplainUnavailable("EXPLAIN_DIRTY_BASIS", "La somme du clean et du couru ne reproduit pas le dirty économique.")
    if price.sample is not None and abs(fsum(price.sample.independent_units) / len(price.sample.independent_units) - dirty) > tolerance:
        raise ExplainUnavailable("EXPLAIN_SAMPLE_MEAN", "Les unités statistiquement indépendantes ne reproduisent pas le prix.")
    return dirty


def _interval(first: ExplainPrice, second: ExplainPrice, delta: float) -> ExplainDifferenceInterval:
    left, right = first.sample, second.sample
    if left is None or right is None or left.pairing_key != right.pairing_key or len(left.independent_units) != len(right.independent_units):
        raise ExplainUnavailable(
            "EXPLAIN_MC_PAIRING", "Les unités indépendantes ne sont pas appariables sur les mêmes dates et facteurs.",
        )
    from scipy.stats import t

    n = len(left.independent_units)
    paired_differences = np.subtract(right.independent_units, left.independent_units, dtype=np.float64)
    standard_error = float(np.std(paired_differences, ddof=1)) / sqrt(n)
    half_width = float(t.ppf(.975, n - 1)) * standard_error
    return ExplainDifferenceInterval(
        independent_units=n, standard_error_eur=standard_error, half_width_95_eur=half_width,
        low_95_eur=delta - half_width, high_95_eur=delta + half_width, resolved=half_width == 0 or abs(delta) > half_width,
    )


def _directional_effect(factor, left: ExplainPrice, right: ExplainPrice, sign: int, stochastic: bool, tolerance: float,
                        credit_rebootstrap: bool = False) -> ExplainEffect:
    first, second = (left, right) if sign > 0 else (right, left)
    source, target = _dirty(first, tolerance), _dirty(second, tolerance)
    delta = target - source
    return ExplainEffect(factor=factor, delta_eur=delta, from_dirty_pv_eur=source, to_dirty_pv_eur=target,
                         interval=_interval(first, second, delta) if stochastic else None,
                         credit_rebootstrap=credit_rebootstrap)


def _waterfall(first, second, first_price, second_price, *, sign, price, roll_market, tolerance, credit_rebootstrap):
    start, target = first.scenario, second.scenario
    if (start.cutoff, start.value_date) != (target.cutoff, target.value_date):
        if roll_market is None:
            raise ExplainUnavailable("EXPLAIN_ROLL_UNAVAILABLE", "Le report des données de départ n’est pas défini.")
        market = roll_market(start, target)
    else:
        market = start.market
    state_roll = target.model_copy(update={"market": market})
    stochastic = first.identity.numerical_protocol is not None
    effects = []
    checkpoint = first_price

    def apply(factor: Factor, scenario: ExplainScenario, *, rebootstrap=False):
        nonlocal checkpoint
        next_checkpoint = second_price if scenario == target else price(scenario)
        effects.append(_directional_effect(factor, checkpoint, next_checkpoint, sign, stochastic, tolerance, rebootstrap))
        checkpoint = next_checkpoint

    if state_roll != start:
        apply("time_state", state_roll)
    for factor in _MARKET_ORDER:
        incoming = getattr(target.market, factor)
        if incoming != getattr(market, factor):
            market = market.model_copy(update={factor: incoming})
            apply(factor, target.model_copy(update={"market": market}), rebootstrap=credit_rebootstrap
                  and market.credit_quotes is not None and factor in ("ois", "credit_quotes", "calibration_recovery"))
    return tuple(effects if sign > 0 else reversed(effects))


def explain_valuations(
    start: ExplainSnapshot,
    end: ExplainSnapshot,
    *,
    price: Callable[[ExplainScenario], ExplainPrice],
    roll_market: Callable[[ExplainScenario, ExplainScenario], ExplainMarket] | None = None,
    roll_convention: str = "same_cutoff",
    current_engine_fingerprint: str | None = None,
    credit_rebootstrap: bool = False,
) -> ValuationExplain:
    """Compare archives using a chronology-safe roll and a declared market-step order."""
    backwards = end.scenario.cutoff < start.scenario.cutoff
    earlier, later = (end, start) if backwards else (start, end)
    sign = -1 if backwards else 1
    initial, final = start.price.economic_dirty_pv_eur, end.price.economic_dirty_pv_eur
    observed = None if initial is None or final is None else final - initial
    facts = {
        "start_archive_id": start.archive_id, "end_archive_id": end.archive_id,
        "start_cutoff": start.scenario.cutoff, "end_cutoff": end.scenario.cutoff,
        "direction": "reverse" if backwards else "forward", "roll_convention": roll_convention,
        "exercise_policy": start.identity.exercise_policy, "from_dirty_pv_eur": initial,
        "to_dirty_pv_eur": final, "observed_dirty_change_eur": observed,
    }

    def fallback(error: ExplainUnavailable, *, status="observed") -> ValuationExplain:
        return ValuationExplain(**facts, status=status, reason_code=error.code, reason=str(error))

    if mismatch := _incompatibility(start.identity, end.identity, _CONTRACT_CHECKS):
        return fallback(mismatch)
    tolerance = start.identity.nominal_eur * REPLAY_TOLERANCE_PER_NOMINAL
    try:
        cash = _confirmed_cash(earlier.scenario, later.scenario, ZoneInfo(start.identity.settlement_timezone), sign)
        cash_total = fsum(item.signed_eur for item in cash)
        facts.update(cash=cash, cash_contractual_eur=cash_total)
        for archive in (start, end):
            _dirty(archive.price, tolerance)
        if observed is not None:
            facts["contractual_pnl_eur"] = fsum((observed, cash_total))
        if start.price.clean_pv_eur is not None and end.price.clean_pv_eur is not None:
            facts.update(clean_change_eur=end.price.clean_pv_eur - start.price.clean_pv_eur,
                         accrued_change_eur=end.price.accrued_eur - start.price.accrued_eur)
        if mismatch := _incompatibility(start.identity, end.identity, _MODEL_CHECKS):
            return fallback(mismatch)
        if current_engine_fingerprint is not None and current_engine_fingerprint != start.identity.engine_fingerprint:
            return fallback(ExplainUnavailable("EXPLAIN_ENGINE", "Le moteur d’origine n’est plus disponible."))
        first_price, second_price = price(earlier.scenario), price(later.scenario)
        chronological = (first_price, second_price)
        replay_start, replay_end = reversed(chronological) if backwards else chronological
        start_error = _dirty(replay_start, tolerance) - initial
        end_error = _dirty(replay_end, tolerance) - final
        facts.update(start_replay_error_eur=start_error, end_replay_error_eur=end_error)
        if observed is None or max(abs(start_error), abs(end_error)) > tolerance:
            return fallback(ExplainUnavailable("EXPLAIN_REPLAY", "Les prix rejoués diffèrent des prix archivés."))
        if start.identity.numerical_protocol is None and (first_price.sample is not None or second_price.sample is not None):
            return fallback(ExplainUnavailable("EXPLAIN_NUMERICAL_PROTOCOL", "Le protocole des échantillons n’a pas été archivé."))
        uncertainty = (
            _interval(replay_start, replay_end, observed) if start.identity.numerical_protocol is not None else None
        )
        effects = _waterfall(earlier, later, first_price, second_price, sign=sign, price=price,
                             roll_market=roll_market, tolerance=tolerance, credit_rebootstrap=credit_rebootstrap)
    except ExplainUnavailable as error:
        return fallback(error, status="pending" if error.code == "EXPLAIN_RECOVERY_PENDING" else "observed")
    return ValuationExplain(**facts, status="attributed", effects=effects, interval=uncertainty,
                            residual_eur=observed - fsum(effect.delta_eur for effect in effects))


def _cash_observation(flow, fact) -> ExplainCash:
    if (fact is None or fact.validated_at is None
            or (flow.payment_fact_id, flow.payment_version, flow.paid_date) !=
            (fact.fact_id, fact.version, fact.effect_date)):
        raise ExplainUnavailable("EXPLAIN_CASH_EVIDENCE", "La preuve de paiement du flux valorisé est indisponible.")
    return ExplainCash(flow_id=flow.flow_id, fact_id=fact.fact_id, version=fact.version,
                       amount_eur=flow.amount_eur, effect_date=fact.effect_date,
                       available_at=fact.available_at, validated_at=fact.validated_at)


def rates_explain_observation(result: RatesPriceResult, context: NativeValuationContext) -> tuple[ExplainPrice, tuple[ExplainCash, ...]]:
    """Read signed dirty/clean and confirmed payments from a frozen FRN or IRS."""
    market = context.market
    if result.context_fingerprint != context.fingerprint or not isinstance(market, RatesMarketSelection):
        raise ExplainUnavailable("EXPLAIN_REPLAY_CONTEXT", "Le résultat de taux ne correspond pas au contexte archivé.")
    facts = {(fact.flow_id, fact.fact_id, fact.version): fact for fact in market.payments}
    cash = tuple(
        _cash_observation(flow, facts.get((flow.flow_id, flow.payment_fact_id, flow.payment_version)))
        for flow in result.flows if flow.state == "paid"
    )
    clean = result.clean_pv_eur + result.detached_pv_eur if isinstance(result, FRNPriceResult) else None
    accrued = result.accrued_eur if isinstance(result, FRNPriceResult) else None
    return ExplainPrice(economic_dirty_pv_eur=result.economic_pv_eur, clean_pv_eur=clean, accrued_eur=accrued), cash


def credit_default_explain_observation(result: CreditDefaultResult, context: CreditDefaultContext) -> tuple[ExplainPrice, tuple[ExplainCash, ...]]:
    """Read the debt/claim and net settlement exactly once after a credit event."""
    if result.context_fingerprint != context.fingerprint:
        raise ExplainUnavailable("EXPLAIN_REPLAY_CONTEXT", "Le résultat crédit ne correspond pas au contexte archivé.")
    if result.state == "alive":
        raise ExplainUnavailable("EXPLAIN_LIVE_CREDIT", "La valeur contingente doit venir de l’archive de crédit vivant.")
    facts = {(fact.flow_id, fact.fact_id, fact.version): fact for fact in context.prior_coupon_payments}
    cash = tuple(
        _cash_observation(flow, facts.get((flow.flow_id, flow.payment_fact_id, flow.payment_version)))
        for flow in result.earned_coupon_flows if flow.state == "paid"
    )
    if result.settlement_flow is not None and result.settlement_flow.state == "paid":
        cash += (_cash_observation(result.settlement_flow, context.facts.settlement),)
    state = "recovery_pending" if result.state == "recovery_pending" else "available"
    return ExplainPrice(economic_dirty_pv_eur=result.economic_pv_eur, state=state), cash
