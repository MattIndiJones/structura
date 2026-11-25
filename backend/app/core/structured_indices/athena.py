"""Research issues, contractual events and residual valuations for structured index notes."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache
from math import fsum, isclose, isfinite

from ..inlife_valuation import InLifeProduct, build_residual
from ..payscript.catalogue import PRODUCTS
from ..payscript.engine import eval_script_on_history
from ..payscript.parser import parse_script, validate_observation_dates
from ..payscript.qualification import APPROVED_SOURCES
from ..payscript.schedule_model import construire
from ..product.calendar import freeze_calendar
from ..valuation_context import (
    ValuationContext,
    deterministic_cashflow_pv,
    json_transport_fingerprint,
    residual_surface_anchor,
    run_valuation,
)
from .schemas import (
    AUTOCALL_GEAR_PUT,
    BOOSTER,
    CAPITAL_GUARANTEED,
    EUROPEAN_CALL,
    EUROPEAN_PUT,
    AthenaFixing,
    AthenaIssueRequest,
    AthenaLifecycleRequest,
    AthenaMarkRequest,
    AthenaMarket,
    AthenaPricing,
    AthenaSolvedQuote,
    AthenaTerms,
    AthenaVintage,
    AutocallGearPutPayoff,
    BoosterPayoff,
    CapitalGuaranteedPayoff,
    EuropeanOptionPayoff,
    EuropeanPutPayoff,
)


_UNDERLYING = "SX5E"
_CURRENCY = "EUR"
_NOMINAL = 100.0
_ACT_YEAR = 365.25
_PAYOFF = PRODUCTS["autocall_athena"]["script"]
_STEP_DOWN_PAYOFF = PRODUCTS["autocall_barriere_degressive"]["script"]
_PHOENIX_PAYOFF = PRODUCTS["phoenix"]["script"]
_PHOENIX_MEMORY_PAYOFF = PRODUCTS["phoenix_memoire"]["script"]
_REVERSE_CONVERTIBLE_PAYOFF = PRODUCTS["reverse_convertible"]["script"]
_QUOTED_SCRIPTS = {
    CAPITAL_GUARANTEED: "capital_garanti",
    BOOSTER: "booster",
    AUTOCALL_GEAR_PUT: "autocall_gear_put",
    EUROPEAN_PUT: "put",
    EUROPEAN_CALL: "call",
}
_QUOTED_PAYOFFS = {key: PRODUCTS[script]["script"] for key, script in _QUOTED_SCRIPTS.items()}
_MATURITY_PAYOFFS = (
    _REVERSE_CONVERTIBLE_PAYOFF, _QUOTED_PAYOFFS[CAPITAL_GUARANTEED], _QUOTED_PAYOFFS[BOOSTER],
    _QUOTED_PAYOFFS[EUROPEAN_PUT], _QUOTED_PAYOFFS[EUROPEAN_CALL],
)
_QUALIFIED_SCRIPTS = {
    _PHOENIX_PAYOFF: "phoenix",
    _PHOENIX_MEMORY_PAYOFF: "phoenix_memoire",
    _REVERSE_CONVERTIBLE_PAYOFF: "reverse_convertible",
    **{source: _QUOTED_SCRIPTS[key] for key, source in _QUOTED_PAYOFFS.items()},
}
_SINGLE_COUPON_LABEL = "Coupon"
_GEAR_PUT_NOMINAL_LABEL = "Remboursement nominal"
_GEAR_PUT_LOSS_LABEL = "Put vendu avec levier, perte plafonnée au capital"
_GUARANTEED_CAPITAL_LABEL = "Capital garanti"
_UPSIDE_PARTICIPATION_LABEL = "Participation à la hausse"
_CAPPED_PARTICIPATION_LABEL = "Participation plafonnée"
_CALL_CAPITAL_LABEL = "Capital — remboursement au rappel"
_PHOENIX_COUPON_LABEL = "Coupon conditionnel"
_MEMORY_COUPON_LABEL = "Coupon et rattrapage"
_MEMORY_CALL_LABEL = "Remboursement anticipé"
_MATURITY_CAPITAL_LABEL = "Capital — remboursement à maturité"
_CAPITAL_LOSS_LABEL = "Put vendu — perte en capital"
_OPTION_PAYOFF_LABELS = {EUROPEAN_PUT: "Put", EUROPEAN_CALL: "Call"}


def _year_fraction(day: date, origin: date) -> float:
    return round((day - origin).days / _ACT_YEAR, 6)


@lru_cache(maxsize=64)
def _compile_schedule(payoff: str, strike_date: date, schedule: tuple[tuple[date, date], ...]):
    """Bind effective contractual dates without regenerating or rolling them."""
    compiled = parse_script(payoff)
    template = _QUALIFIED_SCRIPTS.get(payoff)
    if template is not None and compiled.source_hash != APPROVED_SOURCES[template]:
        raise ValueError("Le script du produit doit être qualifié avant d'être utilisé.")
    if payoff in _MATURITY_PAYOFFS:
        calendar, qualifiers = "MATURITYDATE", (None,)
    else:
        calendar, qualifiers = "OBSERVATIONDATES", (None, [("last",)])
    observed, paid = (list(days) for days in zip(*schedule, strict=True))
    obs_times = [_year_fraction(day, strike_date) for day in observed]
    pay_times = [_year_fraction(day, strike_date) for day in paid]
    for event, qualifier in zip(compiled.events, qualifiers, strict=True):
        if event.constat_ref != calendar or event.type != "AT" or event.constat_qualifier != qualifier:
            raise ValueError("Le script du produit ne correspond plus à son calendrier contractuel.")
        start = -1 if qualifier else 0
        event.dates = obs_times[start:]
        event.payment_dates = pay_times[start:]
        event.ranks = list(range(1, len(schedule) + 1))[start:]
    validate_observation_dates(compiled.events)
    binding = next(constat for constat in compiled.constats if constat.role == "initial_fixing")
    binding.calendar_values = {"STARTDATE": strike_date.isoformat()}
    binding.calendar_currency = _CURRENCY
    compiled.origine = strike_date
    compiled.echeancier = construire(compiled, {calendar: (observed, paid)})
    return compiled, freeze_calendar(compiled)


def _payoff(terms: AthenaTerms) -> str:
    if terms.payoff is not None:
        return _QUOTED_PAYOFFS[terms.payoff.id]
    if terms.reverse_convertible:
        return _REVERSE_CONVERTIBLE_PAYOFF
    if terms.coupon_memory:
        return _PHOENIX_MEMORY_PAYOFF
    if terms.coupon_barrier is not None:
        return _PHOENIX_PAYOFF
    return _STEP_DOWN_PAYOFF if terms.call_barriers is not None else _PAYOFF


def _contract(terms: AthenaTerms):
    return _compile_schedule(
        _payoff(terms),
        terms.strike_date,
        tuple((row.observation_date, row.payment_date) for row in terms.observations),
    )


def _params(terms: AthenaTerms, coupon: float | None) -> dict:
    payoff = terms.payoff
    if isinstance(payoff, EuropeanOptionPayoff):
        return {"STRIKE": payoff.strike_ratio}
    if isinstance(payoff, CapitalGuaranteedPayoff):
        return {"PART": payoff.participation, "STRIKE": payoff.participation_strike}
    if isinstance(payoff, BoosterPayoff):
        return {"PART": payoff.participation, "CAP": payoff.redemption_cap}
    if isinstance(payoff, AutocallGearPutPayoff):
        return {
            "COUPON": payoff.single_coupon, "M_AC_BAR": terms.call_barrier,
            "M_PUT_STRIKE": payoff.put_strike, "GEARING": payoff.gearing,
        }
    if terms.reverse_convertible:
        return {"COUPON": coupon * terms.maturity_years, "M_KI_BAR": terms.protection_barrier}
    # Catalogue COUPON is per observation; the frozen rate is annual.
    return {
        "COUPON": coupon * terms.observation_months / 12,
        "M_AC_BAR": list(terms.call_barriers) if terms.call_barriers is not None else terms.call_barrier,
        "M_KI_BAR": terms.protection_barrier,
        **({"M_CPN_BAR": terms.coupon_barrier} if terms.coupon_barrier is not None else {}),
    }


def _reference(prefix: str, payload) -> str:
    return f"{prefix}-{json_transport_fingerprint(payload)}"


def _terms_reference(vintage: AthenaVintage) -> str:
    script, _ = _contract(vintage.terms)
    return _reference("athena-terms", {
        "template": vintage.terms.payoff_version,
        "payoff": script.source_hash,
        "vintage": vintage.model_dump(mode="json"),
    })


def _market_reference(market: AthenaMarket) -> str:
    return _reference("athena-market", market.model_dump(mode="json"))


def _with_receipt(operation: str, request, result: dict) -> dict:
    terms = request.terms if isinstance(request, AthenaIssueRequest) else request.vintage.terms
    return {**result, "receipt_id": _reference("athena-receipt", {
        "template": terms.payoff_version,
        "payoff": _payoff(terms),
        "operation": operation,
        "inputs": request.model_dump(mode="json"),
        "result": result,
    })}


def _redemption_pv(amount: float, payment_date: date, market: AthenaMarket) -> float:
    return deterministic_cashflow_pv(
        amount, (payment_date - market.as_of).days / _ACT_YEAR,
        r=market.rate, yield_curve=market.yield_curve, funding_curve=market.funding_curve,
        funding_spread=market.funding_spread,
    )


def _next_call(script, vintage: AthenaVintage, market: AthenaMarket, pricing: AthenaPricing, flux_table: dict,
               *, memory_periods: int = 0) -> dict:
    terms = vintage.terms
    call_label = _MEMORY_CALL_LABEL if terms.coupon_memory else _CALL_CAPITAL_LABEL
    if f'"{call_label}"' not in _payoff(terms):
        raise ValueError("Le flux de capital au rappel a changé dans le script.")
    rank, observation = next((rank, row) for rank, row in enumerate(terms.observations, 1)
                             if row.observation_date > market.as_of)
    first_occurrence = min(t for event in script.events for t in event.dates)
    # A positive principal payment identifies a call even at zero coupon or
    # on the final observation. PayScript already averages these counts over
    # the two legs of each antithetic pair, with N as the denominator.
    calls = fsum(row["n"] for row in flux_table.values()
                 if row["lbl"] == call_label
                 and isclose(row["t"], first_occurrence, rel_tol=0, abs_tol=1e-6))
    coupon_per_observation = _params(terms, vintage.annual_coupon)["COUPON"]
    if isinstance(terms.payoff, AutocallGearPutPayoff):
        coupon_periods = 1
    else:
        coupon_periods = 1 + memory_periods if terms.coupon_barrier is not None else rank
    amount = _NOMINAL * (1 + coupon_periods * coupon_per_observation)
    diagnostic = {
        "observation_date": observation.observation_date.isoformat(),
        "payment_date": observation.payment_date.isoformat(),
        "is_final_observation": rank == len(terms.observations),
        "probability": calls / pricing.n_paths,
        "redemption_amount": amount,
        "redemption_pv": _redemption_pv(amount, observation.payment_date, market),
    }
    if terms.call_barriers is not None or terms.coupon_barrier is not None or terms.payoff is not None:
        diagnostic["threshold"] = terms.effective_call_barriers[rank - 1]
    if terms.coupon_memory:
        diagnostic["memory_periods"] = memory_periods
    return diagnostic


def _value_mc(script, vintage: AthenaVintage, market: AthenaMarket, pricing: AthenaPricing, *, state=None,
              include_next_call: bool = False, memory_periods: int = 0) -> dict:
    normalized_spot = market.spot / vintage.initial_fixing
    underlying = {
        "name": _UNDERLYING, "ticker": _UNDERLYING, "ccy": _CURRENCY,
        "spot0": vintage.initial_fixing, "sigma": market.volatility, "q": market.dividend_yield,
        **pricing.underlying_parameters(),
    }
    if market.dividend_curve:
        underlying["dividend_curve"] = [list(point) for point in market.dividend_curve]
    if market.vol_surface is not None:
        underlying["vol_surface"] = market.vol_surface.model_dump(mode="json")
    context = ValuationContext(
        underlyings=[underlying],
        corr_matrix=[[1.0]],
        r=market.rate,
        T=max(day for event in script.events for day in event.dates),
        N=pricing.n_paths,
        model=pricing.model,
        seed=pricing.seed,
        steps_per_year=pricing.steps_per_year,
        antithetic=pricing.antithetic,
        user_params=_params(vintage.terms, vintage.annual_coupon),
        yield_curve=[list(point) for point in market.yield_curve or ()],
        funding_curve=[list(point) for point in market.funding_curve or ()],
        funding_spread=market.funding_spread,
        # Each market snapshot is already anchored to its valuation date.
        local_vol_anchor=(residual_surface_anchor(pricing.model, [underlying], [normalized_spot])
                          if market.as_of > vintage.terms.strike_date else None),
        state={
            **(state or {}),
            "spot_mult": [normalized_spot],
            "spot_base": [normalized_spot],
            "wof0_init": normalized_spot,
        },
    )
    result = run_valuation(script, context)
    price = result["price"] * _NOMINAL
    if not isfinite(price) or price < 0:
        raise ValueError("Valorisation Athena non finie ou négative.")
    valuation = {"price": price, "confidence_interval": [value * _NOMINAL for value in result["ic95"]]}
    if include_next_call:
        valuation["next_call"] = _next_call(
            script, vintage, market, pricing, result["flux_table"], memory_periods=memory_periods,
        )
    return valuation


def _solve_quoted_issue(settings: AthenaSolvedQuote, value, *, piecewise: bool):
    target, tolerance = settings.target_price, settings.price_tolerance
    low, high = settings.minimum, settings.maximum
    low_value = value(low)
    high_value = value(high) if low != high else low_value
    low_price, high_price = low_value[1]["price"], high_value[1]["price"]
    solver = {
        "quantity": settings.quantity,
        "method": "bisection_common_random_numbers" if piecewise else "affine_common_random_numbers",
        "target_price": target,
        "price_tolerance": tolerance,
        "minimum": low,
        "maximum": high,
        "minimum_price": low_price,
        "maximum_price": high_price,
    }
    if piecewise and abs(high_price - target) <= tolerance:
        return high_value, solver  # Same maximal allowed quantity convention as the Optimizer.
    if abs(low_price - target) <= tolerance:
        return low_value, solver
    if abs(high_price - target) <= tolerance:
        return high_value, solver
    if not low_price <= target <= high_price:
        return (None, None), solver
    if not piecewise:
        candidate = low + (high - low) * (target - low_price) / (high_price - low_price)
        result = value(min(high, max(low, candidate)))
        if abs(result[1]["price"] - target) <= tolerance:
            return result, solver
    else:
        for _ in range(52):
            candidate = (low + high) / 2
            result = value(candidate)
            price = result[1]["price"]
            if abs(price - target) <= tolerance:
                return result, solver
            if price < target:
                low = candidate
            else:
                high = candidate
    raise ValueError("Quantité du payoff non conclue à la tolérance de prix demandée.")


def _price_quoted_issue(request: AthenaIssueRequest, script) -> dict:
    settings = request.quote
    solving = isinstance(settings, AthenaSolvedQuote)

    def value(quantity: float | None = None) -> tuple[AthenaVintage, dict]:
        terms = request.terms
        if solving:
            solved_payoff = terms.payoff.model_copy(update={settings.quantity: quantity})
            terms = terms.model_copy(update={"payoff": solved_payoff})
        vintage = AthenaVintage(
            note_id=request.note_id,
            terms=terms,
            initial_fixing=request.initial_fixing,
            initial_fixing_reference=request.initial_fixing_reference,
        )
        return vintage, _value_mc(script, vintage, request.market, request.pricing)

    solver = None
    if solving:
        (vintage, valuation), solver = _solve_quoted_issue(
            settings, value, piecewise=isinstance(request.terms.payoff, BoosterPayoff),
        )
    else:
        vintage, valuation = value()
    if valuation and valuation["price"] <= 0 and not request.terms.has_option_payoff:
        raise ValueError("Prix d’émission du payoff nul.")
    result = {
        "status": "issued" if vintage else "no_parameter_in_bounds",
        "note_id": request.note_id,
        "day": request.market.as_of.isoformat(),
        "vintage": vintage.model_dump(mode="json") if vintage else None,
        "terms_reference": _terms_reference(vintage) if vintage else None,
        "price": valuation["price"] if valuation else None,
        "confidence_interval": valuation["confidence_interval"] if valuation else None,
        "market_snapshot_id": _market_reference(request.market),
        "pricing": request.pricing.model_dump(mode="json"),
        "solver": solver,
    }
    if solving and vintage:
        result["quote_result"] = {
            "quantity": settings.quantity, "value": getattr(vintage.terms.payoff, settings.quantity), "unit": "fraction",
        }
    return _with_receipt("issue", request, result)


def price_athena_issue(request: AthenaIssueRequest) -> dict:
    """Price an issue at its strike with fixed or market-solved economics."""
    script, _ = _contract(request.terms)
    if request.quote is not None:
        return _price_quoted_issue(request, script)

    def value(coupon: float) -> tuple[AthenaVintage, dict]:
        vintage = AthenaVintage(
            note_id=request.note_id,
            terms=request.terms,
            initial_fixing=request.initial_fixing,
            initial_fixing_reference=request.initial_fixing_reference,
            annual_coupon=coupon,
        )
        return vintage, _value_mc(script, vintage, request.market, request.pricing)

    settings = request.coupon
    solver = None
    if settings.mode == "fixed":
        vintage, valuation = value(settings.fixed_coupon)
    else:
        target, tolerance = settings.target_price, settings.price_tolerance
        low, high = settings.min_coupon, settings.max_coupon
        vintage_low, valuation_low = value(low)
        vintage_high, valuation_high = value(high) if high != low else (vintage_low, valuation_low)
        low_price, high_price = valuation_low["price"], valuation_high["price"]
        solver = {
            "method": "affine_common_random_numbers",
            "target_price": target,
            "price_tolerance": tolerance,
            "min_coupon": low,
            "max_coupon": high,
            "min_coupon_price": low_price,
            "max_coupon_price": high_price,
        }
        if abs(low_price - target) <= tolerance:
            vintage, valuation = vintage_low, valuation_low
        elif abs(high_price - target) <= tolerance:
            vintage, valuation = vintage_high, valuation_high
        elif low_price <= target <= high_price:
            # The coupon multiplies fixed cash flows on unchanged paths, so
            # the expected PV is affine at a fixed seed. Reprice the published
            # coupon to verify it against the requested price tolerance.
            candidate = low + (high - low) * (target - low_price) / (high_price - low_price)
            vintage, valuation = value(min(high, max(low, round(candidate, 6))))
            if abs(valuation["price"] - target) > tolerance:
                raise ValueError("Coupon Athena non concluant à la tolérance demandée.")
        else:
            vintage, valuation = None, None
    if valuation and valuation["price"] <= 0:
        raise ValueError("Prix d’émission Athena nul.")
    return _with_receipt("issue", request, {
        "status": "issued" if vintage else "no_coupon_in_bounds",
        "note_id": request.note_id,
        "day": request.market.as_of.isoformat(),
        "vintage": vintage.model_dump(mode="json") if vintage else None,
        "terms_reference": _terms_reference(vintage) if vintage else None,
        "coupon_rate": vintage.annual_coupon if vintage else None,
        "price": valuation["price"] if valuation else None,
        "confidence_interval": valuation["confidence_interval"] if valuation else None,
        "market_snapshot_id": _market_reference(request.market),
        "pricing": request.pricing.model_dump(mode="json"),
        "solver": solver,
    })


@dataclass
class _History:
    prices: dict[date, float]
    references: dict[str, str]
    barriers: list[dict]
    status: str = "active"
    redemption_day: date | None = None
    payment_day: date | None = None
    unpaid_coupon_periods: int = 0
    memory_releases: dict[str, int] = field(default_factory=dict)

    def replay_inputs(self) -> tuple[dict[str, list[float]], list[str]]:
        return {_UNDERLYING: list(self.prices.values())}, [day.isoformat() for day in self.prices]


def _history(vintage: AthenaVintage, as_of: date, fixings: tuple[AthenaFixing, ...]) -> _History:
    terms = vintage.terms
    observations = terms.observations
    initial = vintage.initial_fixing
    history = _History({terms.strike_date: initial},
                       {terms.strike_date.isoformat(): vintage.initial_fixing_reference}, [])
    by_day = {fixing.day: fixing for fixing in fixings}
    for observation, barrier in zip(observations, terms.effective_call_barriers, strict=True):
        day = observation.observation_date
        if day > as_of:
            break
        fixing = by_day.get(day)
        if fixing is None:
            raise ValueError(f"Fixing Athena manquant à la date contractuelle du {day}.")
        day_iso = day.isoformat()
        history.prices[day] = fixing.spot
        history.references[day_iso] = fixing.reference
        ratio = fixing.spot / initial
        base = {"observation_date": day_iso, "fixing": fixing.spot,
                "initial_fixing": initial, "ratio": ratio}
        called = False
        if terms.has_autocall:
            called = ratio >= barrier
            history.barriers.append({
                **base, "kind": "call", "threshold": barrier, "condition_met": called,
            })
        if terms.coupon_barrier is not None:
            coupon_paid = ratio >= terms.coupon_barrier
            history.barriers.append({
                **base, "kind": "coupon", "threshold": terms.coupon_barrier, "condition_met": coupon_paid,
            })
            if terms.coupon_memory:
                if coupon_paid:
                    history.memory_releases[day_iso] = history.unpaid_coupon_periods
                    history.unpaid_coupon_periods = 0
                else:
                    history.unpaid_coupon_periods += 1
        final = observation == observations[-1]
        if final and not called and terms.has_terminal_protection:
            threshold = terms.effective_protection_barrier
            history.barriers.append({
                **base, "kind": "capital", "threshold": threshold, "condition_met": ratio >= threshold,
            })
        if called or final:
            history.status = "called" if called else "matured"
            history.redemption_day = day
            history.payment_day = observation.payment_date
            break
    return history


def _historical_flows(vintage: AthenaVintage, history: _History, *, include_labels: bool = False) -> list[dict]:
    script, _ = _contract(vintage.terms)
    prices, days = history.replay_inputs()
    payoff = eval_script_on_history(
        script, days, prices, 0, max(day for event in script.events for day in event.dates),
        _params(vintage.terms, vintage.annual_coupon), [_UNDERLYING],
        origine=vintage.terms.strike_date, reference_levels={_UNDERLYING: vintage.initial_fixing},
        include_flow_labels=include_labels,
    )
    return payoff["cash_flows"] if payoff else []


def _redemption(vintage: AthenaVintage, history: _History) -> dict:
    flows = _historical_flows(vintage, history)
    observed, payment = history.redemption_day.isoformat(), history.payment_day.isoformat()
    if not flows or any(flow["date"] != observed or flow["payment_date"] != payment for flow in flows):
        raise ValueError("Le flux Athena rejoué diffère du calendrier de remboursement.")
    amount = _NOMINAL * fsum(flow["cf"] for flow in flows)
    if not isfinite(amount) or amount < 0:
        raise ValueError("Montant de remboursement Athena invalide.")
    return {
        "event_id": _reference("athena-redemption", [_terms_reference(vintage), observed]),
        "observed_date": observed,
        "payment_date": payment,
        "amount": amount,
    }


def _typed_claim(prefix: str, terms_reference: str, kind: str, observed: str, payment: str, amount: float) -> dict:
    return {
        "event_id": _reference(f"{prefix}-{kind}", [terms_reference, observed]),
        "observed_date": observed, "payment_date": payment, "amount": _NOMINAL * amount, "kind": kind,
    }


def _option_settlement(vintage: AthenaVintage, history: _History) -> dict | None:
    if history.redemption_day is None:
        return None
    payoff = vintage.terms.payoff
    observed, payment = history.redemption_day.isoformat(), history.payment_day.isoformat()
    flows = _historical_flows(vintage, history, include_labels=True)
    if len(flows) != 1 or (
        flows[0]["label"] != _OPTION_PAYOFF_LABELS[payoff.id]
        or flows[0]["date"] != observed or flows[0]["payment_date"] != payment
    ):
        raise ValueError("Flux de l’option incompatible avec l’échéancier contractuel.")
    amount = flows[0]["cf"]
    if (not isfinite(amount) or amount < 0
            or (isinstance(payoff, EuropeanPutPayoff) and amount > payoff.strike_ratio)):
        raise ValueError("Montant de règlement de l’option invalide.")
    return _typed_claim(payoff.id, _terms_reference(vintage), "option_payoff", observed, payment, amount)


def _participation_claims(vintage: AthenaVintage, history: _History) -> tuple[list[dict], dict | None]:
    if history.redemption_day is None:
        return [], None
    observed, payment = history.redemption_day.isoformat(), history.payment_day.isoformat()
    guaranteed = isinstance(vintage.terms.payoff, CapitalGuaranteedPayoff)
    participation_label = _UPSIDE_PARTICIPATION_LABEL if guaranteed else _CAPPED_PARTICIPATION_LABEL
    capital_labels = {_GUARANTEED_CAPITAL_LABEL} if guaranteed else {_MATURITY_CAPITAL_LABEL, _CAPITAL_LOSS_LABEL}
    amounts = {}
    for flow in _historical_flows(vintage, history, include_labels=True):
        label, amount = flow["label"], flow["cf"]
        if (flow["date"] != observed or flow["payment_date"] != payment or label in amounts or not isfinite(amount)):
            raise ValueError("Flux de participation incompatible avec l’échéancier contractuel.")
        amounts[label] = amount
    if amounts.keys() != capital_labels | {participation_label}:
        raise ValueError("Flux de participation ou de capital incompatible avec le payoff.")
    principal, gain = fsum(amounts[label] for label in capital_labels), amounts[participation_label]
    if not 0 <= principal <= 1 or gain < 0:
        raise ValueError("Montants de capital ou de participation invalides.")
    prefix, terms_reference = vintage.terms.payoff.id, _terms_reference(vintage)
    participation = [_typed_claim(prefix, terms_reference, "participation", observed, payment, gain)] if gain else []
    return participation, _typed_claim(prefix, terms_reference, "redemption", observed, payment, principal)


def _has_split_coupons(terms: AthenaTerms) -> bool:
    return terms.coupon_barrier is not None or terms.reverse_convertible or isinstance(terms.payoff, AutocallGearPutPayoff)


def _separate_claims(vintage: AthenaVintage, history: _History, flows: list[dict]) -> tuple[list[dict], dict | None]:
    """Project labelled PayScript legs onto individually identified receivables."""
    terms = vintage.terms
    terms_reference = _terms_reference(vintage)
    payments = {event.observation_date.isoformat(): event.payment_date.isoformat()
                for event in terms.observations if event.observation_date in history.prices}
    terminal_day = history.redemption_day.isoformat() if history.redemption_day else None
    memory = terms.coupon_memory
    gear_put = isinstance(terms.payoff, AutocallGearPutPayoff)
    if gear_put:
        coupon_label = _SINGLE_COUPON_LABEL
        prefix, product = "autocall-gear-put", "Gear Put"
    elif terms.reverse_convertible:
        coupon_label = _SINGLE_COUPON_LABEL
        prefix, product = "reverse-convertible", "Reverse Convertible"
    else:
        coupon_label = _MEMORY_COUPON_LABEL if memory else _PHOENIX_COUPON_LABEL
        prefix, product = "phoenix", "Phoenix"
    call_label = _MEMORY_CALL_LABEL if memory else _CALL_CAPITAL_LABEL
    coupon_flows = {}
    principal_legs = {}
    for flow in flows:
        observed, payment, amount = flow["date"], flow["payment_date"], flow["cf"]
        if payments.get(observed) != payment or not isfinite(amount):
            raise ValueError(f"Flux {product} incompatible avec son échéancier contractuel.")
        label = flow["label"]
        if label == coupon_label:
            if observed in coupon_flows or amount < 0:
                raise ValueError(f"Coupon {product} invalide ou dupliqué.")
            coupon_flows[observed] = amount
        elif observed == terminal_day and label not in principal_legs:
            principal_legs[label] = amount
        else:
            raise ValueError(f"Flux de capital {product} invalide ou dupliqué.")

    coupon = _params(terms, vintage.annual_coupon)["COUPON"]
    if gear_put:
        expected_coupons = {terminal_day: coupon} if history.status == "called" else {}
    elif terms.reverse_convertible:
        expected_coupons = {terminal_day: coupon} if terminal_day else {}
    elif memory:
        expected_coupons = {day: coupon * (1 + periods) for day, periods in history.memory_releases.items()}
    else:
        expected_coupons = {row["observation_date"]: coupon if row["condition_met"] else 0.
                            for row in history.barriers if row["kind"] == "coupon"}
    if coupon_flows != expected_coupons:
        raise ValueError(f"Les coupons {product} rejoués diffèrent des constats contractuels.")

    def claim(kind, observed, amount):
        return _typed_claim(prefix, terms_reference, kind, observed, payments[observed], amount)

    coupons = [claim("coupon", observed, amount) for observed, amount in coupon_flows.items() if amount > 0]
    if memory:
        for receivable in coupons:
            receivable["memory_periods"] = history.memory_releases[receivable["observed_date"]]
    if terminal_day is None:
        return coupons, None
    if history.status == "called":
        expected_labels = {call_label}
    elif gear_put:
        expected_labels = {_GEAR_PUT_NOMINAL_LABEL, _GEAR_PUT_LOSS_LABEL}
    else:
        expected_labels = {_MATURITY_CAPITAL_LABEL, _CAPITAL_LOSS_LABEL}
    principal = fsum(principal_legs.values())
    if principal_legs.keys() != expected_labels or not 0 <= principal <= 1:
        raise ValueError(f"Le capital {product} rejoué diffère du statut contractuel.")
    return coupons, claim("redemption", terminal_day, principal)


def check_athena_lifecycle(request: AthenaLifecycleRequest) -> dict:
    """Resolve the life of a vintage from dated contractual fixings."""
    vintage = request.vintage
    history = _history(vintage, request.as_of, request.fixings)
    terminated = history.status != "active"
    claims = {}
    if vintage.terms.has_option_payoff:
        claims["option_settlement"] = _option_settlement(vintage, history)
        redemption = None
    elif vintage.terms.has_participation:
        claims["participation_claims"], redemption = _participation_claims(vintage, history)
    elif _has_split_coupons(vintage.terms):
        claims["coupon_claims"], redemption = _separate_claims(
            vintage, history, _historical_flows(vintage, history, include_labels=True),
        )
    else:
        redemption = _redemption(vintage, history) if terminated else None
    return _with_receipt("lifecycle", request, {
        "day": request.as_of.isoformat(),
        "note_id": vintage.note_id,
        "terms_reference": _terms_reference(vintage),
        "status": history.status,
        "terminated": terminated,
        "barriers": history.barriers,
        "redemption": redemption,
        **claims,
        "fixing_references": history.references,
    })


def _live_mark(request: AthenaMarkRequest, history: _History) -> tuple[dict, list[dict]]:
    vintage, market = request.vintage, request.market
    terms = vintage.terms
    _, schedule = _contract(terms)
    product = InLifeProduct(
        script_snapshot=_payoff(terms),
        underlyings=[{"name": _UNDERLYING, "ticker": _UNDERLYING, "ccy": _CURRENCY}],
        strike_levels={_UNDERLYING: vintage.initial_fixing},
        strike_date=terms.strike_date,
        value_date=terms.strike_date,
        tenor=_year_fraction(terms.observations[-1].observation_date, terms.strike_date),
        currency=_CURRENCY,
        payment_date=terms.observations[-1].payment_date,
        market={"r": market.rate * 100, "user_params": _params(terms, vintage.annual_coupon)},
        frozen_schedule=schedule,
    )
    # The snapshot spot only fills the off-observation edge of replay. On a
    # contractual day the exact fixing stays in history, independently of spot.
    history.prices.setdefault(market.as_of, market.spot)
    prices, days = history.replay_inputs()
    phoenix = terms.coupon_barrier is not None
    residual = build_residual(product, prices, days, _year_fraction(market.as_of, terms.strike_date), market.as_of,
                              include_flow_labels=phoenix)
    if residual.early_recall or (residual.realized_flows and not phoenix):
        raise ValueError("L'état rejoué ne correspond pas aux constats contractuels.")
    state = residual.state
    value = _value_mc(residual.residual_script, vintage, market, request.pricing,
                      include_next_call=terms.has_autocall,
                      memory_periods=history.unpaid_coupon_periods, state={
        "wof_min_init": state["wof_min"],
        "bof_max_init": state["bof_max"],
        "index_offset": state["index"],
        "memo_init": state["memo"],
        "accum_init": state["accum"],
        "s_min_init": state["s_min"],
        "s_max_init": state["s_max"],
        "s_prev_init": state["s_prev"],
        "realvol_state_init": state["realvol_state"],
        "fix_state_init": state["fix_state"],
    })
    return value, residual.realized_flows


def _pending_claims(claims: list[dict], market: AthenaMarket) -> list[dict]:
    day = market.as_of.isoformat()
    return [
        {**claim, "pv": _redemption_pv(claim["amount"], date.fromisoformat(claim["payment_date"]), market)}
        for claim in claims if claim["payment_date"] > day or claim["observed_date"] == day
    ]


def price_athena_mark(request: AthenaMarkRequest) -> dict:
    """Return ex-claims MTM and any detached receivable for one vintage/day."""
    vintage, market = request.vintage, request.market
    history = _history(vintage, market.as_of, request.fixings)
    terminated = history.status != "active"
    split_coupons = _has_split_coupons(vintage.terms)
    if terminated:
        valuation = None
        flows = _historical_flows(vintage, history, include_labels=True) if split_coupons else []
    else:
        valuation, flows = _live_mark(request, history)
    if vintage.terms.has_option_payoff:
        settlement = _option_settlement(vintage, history)
        gains, redemption = ([settlement] if settlement else []), None
    elif vintage.terms.has_participation:
        gains, redemption = _participation_claims(vintage, history)
    elif split_coupons:
        gains, redemption = _separate_claims(vintage, history, flows)
    else:
        gains, redemption = [], _redemption(vintage, history) if terminated else None
    claims = _pending_claims([*gains, redemption] if redemption else gains, market)
    day = market.as_of.isoformat()
    return _with_receipt("mark", request, {
        "note_id": vintage.note_id,
        "day": day,
        "terms_reference": _terms_reference(vintage),
        "market_snapshot_id": _market_reference(market),
        "status": history.status,
        "terminated": terminated,
        "residual_pv": valuation["price"] if valuation else 0.0,
        "confidence_interval": valuation["confidence_interval"] if valuation else None,
        **({"next_call": valuation["next_call"]} if valuation and "next_call" in valuation else {}),
        "claims": claims,
        "barriers": [row for row in history.barriers if row["observation_date"] == day],
        "fixing_references": history.references,
        "pricing": request.pricing.model_dump(mode="json"),
    })
