"""Reproduce native Pricer receipts offline and adapt them to the Valo Explain."""

from collections.abc import Callable
from dataclasses import dataclass
from functools import cache
from hashlib import sha256
from math import exp, isclose, log
from pathlib import Path
from typing import Literal

from pydantic import TypeAdapter

from ..core.product.credit_default import CreditDefaultContext, CreditDefaultDiscount, CreditDefaultFlow, price_credit_default
from ..core.product.credit_results import CreditContext, CreditResult
from ..core.product.exotic_valuation_explain import (
    ExplainCash, ExplainIdentity, ExplainMarket, ExplainPrice, ExplainScenario, ExplainSnapshot, ExplainUnavailable, ValuationExplain,
    credit_default_explain_observation, explain_valuations, rates_explain_observation,
)
from ..core.product.models import FrozenObject, Product
from ..core.product.native_market import NativeValuationContext, NativeValuationInputs
from ..core.product.rates_market import CurvePillar, RatesMarketSelection, SelectedRatesCurve
from ..core.product.rates_payscript import rates_payoff
from ..core.product.rates_pricing import RatesPriceResult, price_rates
from ..core.valuation_context import canonical_fingerprint


Family = Literal["rates", "credit"]
_RATES_RESULT = TypeAdapter(RatesPriceResult)
_ENGINE_SOURCES = {
    "rates": (
        "product/native_market.py", "product/native_schedule.py", "product/rates_market.py",
        "product/rates_payscript.py", "product/rates_pilot.py", "product/rates_pricing.py", "product/rates_schedule.py",
        "payscript/bindings.py", "payscript/parser.py",
    ),
    "credit": (
        "calendars.py", "valuation_context.py", "product/models.py", "product/native_schedule.py",
        "product/credit_default.py", "product/credit_facts.py", "product/credit_results.py", "product/credit_pricing.py",
        "product/credit_pilot.py", "product/isda_pricing.py", "product/isda_market.py", "product/rates_market.py",
    ),
}


@cache
def native_explain_engine_fingerprint(family: Family) -> str | None:
    core = Path(__file__).resolve().parents[1] / "core"
    digest = sha256()
    for path in _ENGINE_SOURCES[family]:
        try:
            source = (core / path).read_bytes().replace(b"\r\n", b"\n")
        except OSError:
            return None
        digest.update(path.encode() + b"\0" + sha256(source).digest())
    return digest.hexdigest()


@dataclass(frozen=True)
class _NativeArchive:
    family: Family
    snapshot: ExplainSnapshot
    reprice: Callable[[ExplainScenario], ExplainPrice] | None


def _product(receipt: dict, context: NativeValuationContext | CreditContext) -> Product:
    product = Product.model_validate({
        "product_id": context.product_id, "reference": receipt.get("product_reference"),
        "terms_version": context.terms_version or 0, "revision": receipt["input_revision"],
        "intent": {"nominal": context.nominal, "side": context.side},
        "terms": receipt["terms"], "native_schedule": receipt["schedule"],
    })
    if (product.terms_fingerprint, product.native_schedule.fingerprint) != (
        context.terms_fingerprint, context.schedule_fingerprint,
    ):
        raise ExplainUnavailable("EXPLAIN_REPLAY_CONTEXT", "Les termes ou l’échéancier contredisent le contexte signé.")
    return product


def _identity(receipt, context, product, *, model, version):
    archived = receipt.get("calculation_identity") or {}
    if archived.get("engine_version", version) != version:
        raise ExplainUnavailable("EXPLAIN_ENGINE", "La version du moteur contredit le résultat signé.")
    instrument = product.terms.instrument_type
    return ExplainIdentity(
        position_id=(f"product:{product.product_id}" if product.product_id is not None
                     else f"draft:{receipt['user_id']}:{instrument}"),
        terms_version=context.terms_version or 1, terms_fingerprint=context.terms_fingerprint,
        schedule_fingerprint=context.schedule_fingerprint, nominal_eur=context.nominal, side=context.side,
        value_date_convention="date_de_valorisation", model=model, engine_version=version,
        engine_fingerprint=archived.get("engine_fingerprint") or "legacy_identity_unavailable",
    )


def _curve_block(curve: SelectedRatesCurve) -> dict:
    pillars = curve.effective_pillars
    rates = [-365 * log(item.factor) / (item.date - curve.anchor_date).days for item in pillars[1:]]
    if all(isclose(rate, rates[-1], abs_tol=1e-12, rel_tol=0) for rate in rates):
        return {"flat_continuous_rate": round(rates[-1], 14)}
    return {"pillars": [item.model_dump(mode="json") for item in pillars]}


def _replace_curve(template: SelectedRatesCurve, block: FrozenObject) -> SelectedRatesCurve:
    encoded = block.to_dict()
    if encoded == _curve_block(template):
        return template
    rate = encoded.get("flat_continuous_rate")
    if rate is not None:
        points = tuple(CurvePillar(date=item.date, factor=exp(-rate * (item.date - template.anchor_date).days / 365))
                       for item in template.effective_pillars)
    else:
        points = tuple(CurvePillar.model_validate(item) for item in encoded["pillars"])
    return SelectedRatesCurve.model_validate({**template.model_dump(), "pillars": points, "override": None})


def _rates_archive(receipt: dict, archive_id: str | int) -> _NativeArchive:
    context = NativeValuationContext.model_validate(receipt["context"])
    product = _product(receipt, context)
    result = _RATES_RESULT.validate_python(receipt["result"])
    effective = context.market
    if not isinstance(effective, RatesMarketSelection):
        raise ExplainUnavailable("EXPLAIN_REPLAY_CONTEXT", "Le reçu de taux ne porte pas de marché de taux figé.")
    price, cash = rates_explain_observation(result, context)
    market = ExplainMarket(ois=_curve_block(effective.discount), projection_basis=_curve_block(effective.projection),
                           funding={"bps": effective.frn_funding_bps})
    state = {key: value for key, value in effective.model_dump(mode="json").items()
             if key in {"fixings", "payments", "flows", "overdue_treatment"}}
    scenario = ExplainScenario(cutoff=context.cutoff, value_date=context.value_date, market=market, cash=cash, state=state)
    snapshot = ExplainSnapshot(archive_id=archive_id, price=price, scenario=scenario,
                               identity=_identity(receipt, context, product, model=f"rates:{result.payoff_mode}",
                                                  version=result.engine_version))

    def reprice(candidate: ExplainScenario) -> ExplainPrice:
        inputs = context
        if candidate.market != market:
            discount = _replace_curve(effective.discount, candidate.market.ois)
            projection = _replace_curve(effective.projection, candidate.market.projection_basis)
            funding = candidate.market.funding.to_dict()["bps"]
            data = {"policy_version": effective.policy_version, "market_id": effective.market_id,
                    "market_version": effective.market_version, "market_date": effective.valuation_date.isoformat(),
                    "discount": discount.model_dump(mode="json"), "projection": projection.model_dump(mode="json"),
                    "frn_funding_bps": funding}
            selection = effective.model_copy(update={"discount": discount, "projection": projection, "frn_funding_bps": funding,
                                                      "market_fingerprint": canonical_fingerprint(data)})
            inputs = NativeValuationContext.seal(NativeValuationInputs.model_validate({
                **context.model_dump(exclude={"fingerprint"}), "market": selection,
            }))
        payoff, equivalent = None, False
        if product.terms.payoff_mode == "scripted":
            payoff, equivalent, metadata = rates_payoff(product)
            if metadata.model_dump(mode="json") != receipt["script"]:
                raise ExplainUnavailable("EXPLAIN_REPLAY_CONTEXT", "Le payoff compilé diffère du script archivé.")
        value = price_rates(product, inputs, payoff=payoff, equivalent_payoff=equivalent)
        return rates_explain_observation(value, inputs)[0]

    return _NativeArchive("rates", snapshot, reprice)


def _credit_archive(receipt: dict, archive_id: str | int) -> _NativeArchive:
    context = CreditContext.model_validate(receipt["context"])
    product = _product(receipt, context)
    result = CreditResult.model_validate(receipt["result"])
    version = receipt["engine_version"]
    identity = _identity(receipt, context, product, model=f"credit:{result.mode}", version=version)
    context_data = context.market.to_dict()
    default = context_data.get("default_context")
    if default is None or result.state == "alive":
        dirty = next((metric.value for metric in result.metrics if metric.key == "dirty_pv"), None)
        if dirty is None:
            raise ExplainUnavailable("EXPLAIN_CREDIT_BASIS", "La mesure dirty économique du crédit vivant manque au reçu.")
        scenario = ExplainScenario(cutoff=context.cutoff, value_date=context.valuation_date, market=ExplainMarket())
        return _NativeArchive("credit", ExplainSnapshot(archive_id=archive_id, identity=identity, scenario=scenario,
                                                        price=ExplainPrice(economic_dirty_pv_eur=dirty)), None)

    event_context = CreditDefaultContext.model_validate(default)
    if (event_context.product_id, event_context.terms_version, event_context.terms_fingerprint,
            event_context.schedule_fingerprint, event_context.cutoff, event_context.facts.state) != (
        context.product_id, context.terms_version, context.terms_fingerprint, context.schedule_fingerprint,
        context.cutoff, result.state,
    ):
        raise ExplainUnavailable("EXPLAIN_REPLAY_CONTEXT", "L’état de défaut contredit le reçu de crédit.")
    cash = _credit_cash(result, event_context, context_data.get("settlement_flow"))
    price = ExplainPrice(economic_dirty_pv_eur=result.measure.value,
                         state="recovery_pending" if result.state == "recovery_pending" else "available")
    market = ExplainMarket(ois={"flat_continuous_rate": event_context.discount.ois_rate},
                           funding={"bps": event_context.discount.cln_funding_bps})
    lifecycle = event_context.model_dump(mode="json", include={"facts", "paid_basis", "planned_settlement_date", "prior_coupon_payments"})
    scenario = ExplainScenario(cutoff=event_context.cutoff, value_date=event_context.value_date, market=market, cash=cash,
                               state=lifecycle)
    snapshot = ExplainSnapshot(archive_id=archive_id, identity=identity, scenario=scenario, price=price)

    def reprice(candidate: ExplainScenario) -> ExplainPrice:
        inputs = event_context
        if candidate.market != market:
            discount = CreditDefaultDiscount.model_validate({
                **event_context.discount.model_dump(),
                "ois_rate": candidate.market.ois.to_dict()["flat_continuous_rate"],
                "cln_funding_bps": candidate.market.funding.to_dict()["bps"],
            })
            payload = {**event_context.model_dump(mode="json", exclude={"fingerprint"}),
                       "discount": discount.model_dump(mode="json")}
            inputs = CreditDefaultContext.model_validate({**payload, "fingerprint": canonical_fingerprint(payload)})
        return credit_default_explain_observation(price_credit_default(product, inputs), inputs)[0]

    return _NativeArchive("credit", snapshot, reprice)


def _credit_cash(result: CreditResult, context: CreditDefaultContext, settlement: dict | None) -> tuple[ExplainCash, ...]:
    paid = {flow.flow_id: flow for flow in result.flows if flow.state == "paid"}
    cash = []
    for fact in context.prior_coupon_payments:
        flow = paid.get(fact.flow_id)
        if flow is None:
            continue
        if (flow.payment_date, flow.amount_eur) != (fact.effect_date, fact.amount_eur):
            raise ExplainUnavailable("EXPLAIN_CASH_EVIDENCE", "Le coupon réglé contredit son justificatif.")
        cash.append(ExplainCash(flow_id=fact.flow_id, fact_id=fact.fact_id, version=fact.version,
                                amount_eur=fact.amount_eur, effect_date=fact.effect_date,
                                available_at=fact.available_at, validated_at=fact.validated_at))
    if result.state == "settled":
        fact = context.facts.settlement
        flow = CreditDefaultFlow.model_validate(settlement)
        if (flow.state, flow.payment_fact_id, flow.payment_version, flow.paid_date) != (
            "paid", fact.fact_id, fact.version, fact.effect_date,
        ):
            raise ExplainUnavailable("EXPLAIN_CASH_EVIDENCE", "Le règlement net contredit le fait de paiement.")
        cash.append(ExplainCash(flow_id=flow.flow_id, fact_id=fact.fact_id, version=fact.version,
                                amount_eur=flow.amount_eur, effect_date=fact.effect_date,
                                available_at=fact.available_at, validated_at=fact.validated_at))
    return tuple(cash)


def _native_archive(receipt, archive_id):
    instrument = receipt["result"]["instrument_type"]
    if instrument in ("FRN", "IRS"):
        return _rates_archive(receipt, archive_id)
    if instrument in ("CDS", "CLN"):
        return _credit_archive(receipt, archive_id)
    raise ExplainUnavailable("EXPLAIN_INSTRUMENT", "Ce reçu ne porte pas une valorisation native qualifiée.")


def explain_native_calculations(
    start_receipt: dict, end_receipt: dict, *, start_archive_id: str | int = "start", end_archive_id: str | int = "end",
) -> ValuationExplain:
    """Build a two-receipt comparison after caller-side signature and access checks."""
    start, end = _native_archive(start_receipt, start_archive_id), _native_archive(end_receipt, end_archive_id)
    archives = (start, end)

    def price(candidate: ExplainScenario) -> ExplainPrice:
        equivalent = (candidate.cutoff, candidate.value_date, candidate.state, candidate.cash)
        archive = next((item for item in archives if item.snapshot.scenario == candidate), None)
        if archive is None:
            archive = next((item for item in reversed(archives)
                            if (item.snapshot.scenario.cutoff, item.snapshot.scenario.value_date,
                                item.snapshot.scenario.state, item.snapshot.scenario.cash) == equivalent), None)
        if archive is None or archive.reprice is None:
            raise ExplainUnavailable("EXPLAIN_CREDIT_BASIS", "Le crédit vivant n’a pas de pont déterministe qualifié.")
        try:
            return archive.reprice(candidate)
        except ExplainUnavailable:
            raise
        except (ValueError, ArithmeticError) as exc:
            raise ExplainUnavailable("EXPLAIN_REPRICE_UNAVAILABLE", "Le marché intermédiaire ne couvre pas l’état contractuel.") from exc

    def roll_market(earlier: ExplainScenario, later: ExplainScenario) -> ExplainMarket:
        if earlier.value_date != later.value_date and start.family == "rates" and any(
            "flat_continuous_rate" not in curve.to_dict() for curve in (earlier.market.ois, earlier.market.projection_basis)
        ):
            raise ExplainUnavailable("EXPLAIN_ROLL_UNAVAILABLE", "Le report entre dates exige les deux courbes plates du témoin.")
        return earlier.market

    engine = native_explain_engine_fingerprint(start.family) or "current_engine_unavailable"
    result = explain_valuations(start.snapshot, end.snapshot, price=price, roll_market=roll_market,
                                roll_convention="flat_zero_ACT/365F", current_engine_fingerprint=engine)
    if any(item.reprice is None for item in archives):
        return result.model_copy(update={"cash_contractual_eur": None, "contractual_pnl_eur": None})
    return result
