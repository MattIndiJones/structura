"""Adapt signed exotic scenario prices to the native attribution workflow."""
from __future__ import annotations

from ..core.product.credit_default import CreditDefaultResult
from ..core.product.exotic_valuation_explain import (
    ExplainIdentity, ExplainMarket, ExplainPrice, ExplainSample, ExplainScenario, ExplainSnapshot,
    ExplainUnavailable, credit_default_explain_observation, explain_valuations,
)
from ..core.valuation_context import json_transport_fingerprint
from .exotic_valuation import (
    ExoticRatesScenario, exotic_engine_fingerprint, price_exotic_scenario, read_scenario, result_payload,
)


def _credit_market(snapshot) -> ExplainMarket:
    market = snapshot.credit.market.model_dump(mode="json")
    marginals = [
        {field: value for field, value in name.items() if field != "loading"}
        for name in market["marginals"]
    ]
    loading = {name["reference_entity_id"]: name["loading"] for name in market["marginals"]}
    dependence = {field: value for field, value in market.items() if field.startswith("dependence_")}
    return ExplainMarket(
        ois={"discount_rate": market["discount_rate"]}, funding={"funding_bps": market["funding_bps"]},
        credit_quotes={"marginals": sorted(marginals, key=lambda name: name["reference_entity_id"])},
        dependence={**dependence, "loadings": loading},
    )


def _market(snapshot) -> ExplainMarket:
    if isinstance(snapshot, ExoticRatesScenario):
        market = snapshot.market.model_dump(mode="json")
        return ExplainMarket(
            ois={"discount": market["discount"]}, projection_basis={"projection": market["projection"]},
            funding={"funding_bps": market["funding_bps"]},
            volatility={field: market[field] for field in ("mean_reversion", "volatility")},
        )
    return _credit_market(snapshot)


def _economic_price(snapshot, result: dict, calculation=None) -> ExplainPrice:
    if isinstance(snapshot, ExoticRatesScenario):
        sample = None if calculation is None else ExplainSample(
            pairing_key=result["draw_fingerprint"], independent_units=tuple(calculation.independent_pv_eur.tolist()),
        )
        return ExplainPrice(economic_dirty_pv_eur=result["pv_eur"], sample=sample)
    realized = result.get("realized")
    if realized is not None:
        dirty = realized["economic_pv_eur"]
        return ExplainPrice(economic_dirty_pv_eur=dirty, state="recovery_pending" if dirty is None else "available")
    sample = None
    if calculation is not None and calculation.dirty_samples is not None:
        sample = ExplainSample(pairing_key=calculation.draw_fingerprint,
                               independent_units=tuple(calculation.dirty_samples.tolist()))
    dirty = result["estimate"]["dirty_pv_eur"]["mean"]
    clean = result["estimate"]["clean_pv_eur"]["mean"]
    return ExplainPrice(economic_dirty_pv_eur=dirty, clean_pv_eur=clean, accrued_eur=dirty - clean, sample=sample)


def _archive(claims: dict, snapshot) -> ExplainSnapshot:
    if isinstance(snapshot, ExoticRatesScenario):
        terms = snapshot.terms.model_dump(mode="json")
        schedule = {key: terms[key] for key in ("cashflows", "exercises")}
        protocol = snapshot.settings.model_dump(mode="json")
        has_exercise = bool(snapshot.terms.exercises)
        model = "hull_white_1f_ois"
        cash = ()
        realized = None
    else:
        terms = snapshot.credit.contract.model_dump(mode="json")
        reference_ids = sorted(name.reference_entity_id for name in snapshot.credit.market.marginals)
        terms["reference_entities"] = reference_ids
        schedule = {"coupons": terms["coupons"], "maturity_years": terms["maturity_years"]}
        protocol = snapshot.credit.settings.model_dump(mode="json")
        realized = snapshot.credit.realized
        model = "credit_frozen_survival_marginals"
        cash = ()
        if realized is not None:
            _, cash = credit_default_explain_observation(
                CreditDefaultResult.model_validate(claims["result"]["realized"]), realized.context,
            )
        has_exercise = False
    result = claims["result"]
    engine_version = result["engine_version"] if isinstance(snapshot, ExoticRatesScenario) else result["provenance"]["engine_version"]
    state = {} if realized is None else {"realized": realized.model_dump(mode="json")}
    terms_fingerprint = (json_transport_fingerprint(terms) if realized is None
                         else realized.product.terms_fingerprint)
    schedule_fingerprint = (json_transport_fingerprint(schedule) if realized is None
                            else realized.product.native_schedule.fingerprint)
    identity = ExplainIdentity(
        position_id=snapshot.position_id, terms_version=snapshot.terms_version,
        terms_fingerprint=terms_fingerprint, schedule_fingerprint=schedule_fingerprint,
        nominal_eur=terms["nominal_eur"], side=terms["side"],
        value_date_convention=snapshot.value_date_convention, model=model,
        engine_version=engine_version, engine_fingerprint=claims["engine_fingerprint"],
        numerical_protocol=None if realized else json_transport_fingerprint(protocol),
        exercise_policy="reoptimized" if has_exercise else "none",
        exercise_policy_fingerprint=json_transport_fingerprint(protocol) if has_exercise else None,
    )
    return ExplainSnapshot(
        archive_id=json_transport_fingerprint({"request": claims["request"], "result": claims["result_fingerprint"]}),
        identity=identity, price=_economic_price(snapshot, result),
        scenario=ExplainScenario(cutoff=snapshot.cutoff, value_date=snapshot.valuation_date, market=_market(snapshot),
                                 state=state, cash=cash),
    )


def _scenario_at(template, scenario: ExplainScenario):
    payload = template.model_dump(mode="json")
    payload.update(cutoff=scenario.cutoff, valuation_date=scenario.value_date)
    market = scenario.market
    if isinstance(template, ExoticRatesScenario):
        payload["market"] = {
            **market.ois.to_dict(), **market.projection_basis.to_dict(),
            **market.funding.to_dict(), **market.volatility.to_dict(),
        }
    else:
        dependence = market.dependence.to_dict()
        loadings = dependence.pop("loadings")
        marginals = market.credit_quotes.to_dict()["marginals"]
        payload["credit"]["market"].update(
            **market.ois.to_dict(), **market.funding.to_dict(), **dependence,
            marginals=[{**name, "loading": loadings[name["reference_entity_id"]]} for name in marginals],
        )
        payload["credit"]["realized"] = scenario.state.to_dict().get("realized")
    return read_scenario(payload)


def explain_exotic_receipts(start: dict, end: dict):
    first_input, last_input = (read_scenario(claims["request"]) for claims in (start, end))
    first, last = _archive(start, first_input), _archive(end, last_input)
    endpoints = {first.scenario: first_input, last.scenario: last_input}

    def price(scenario: ExplainScenario) -> ExplainPrice:
        try:
            request = endpoints.get(scenario)
            if request is None:
                request = _scenario_at(last_input, scenario)
            calculation = price_exotic_scenario(request, retain_samples=True)
            return _economic_price(request, result_payload(calculation), calculation)
        except ValueError as exc:
            raise ExplainUnavailable("EXPLAIN_SCENARIO_UNAVAILABLE", str(exc)) from exc

    def roll_market(earlier: ExplainScenario, later: ExplainScenario) -> ExplainMarket:
        same_default_market = (
            earlier.state.to_dict().get("realized") is not None
            and later.state.to_dict().get("realized") is not None
            and earlier.market == later.market
        )
        if earlier.value_date != later.value_date and not same_default_market:
            raise ExplainUnavailable("EXPLAIN_ROLL_UNAVAILABLE", "Le report de la grille Monte Carlo entre deux dates de valeur requiert une convention qualifiée.")
        return earlier.market

    return explain_valuations(
        first, last, price=price, roll_market=roll_market,
        roll_convention="same_value_date_or_deterministic_default_with_frozen_market",
        current_engine_fingerprint=exotic_engine_fingerprint(),
    )
