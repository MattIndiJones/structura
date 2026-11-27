"""Retain an authenticated exotic price as a native Product calculation."""

from dataclasses import dataclass
from datetime import datetime
import json
from math import isclose

from pydantic import TypeAdapter
from sqlmodel import Session

from ..core.product.exotic_credit_mc import CreditMcResult
from ..core.product.exotic_rates_mc import RatesMCResult
from ..core.product.models import CalculationRef, ExoticTerms, Product
from ..core.product.native_schedule_exotic import exotic_term_dates
from ..core.valuation_context import canonical_json, json_transport_fingerprint
from ..db.models import ProductCalculationRun, User
from .exotic_valuation import ExoticRatesScenario, PROFILE, exotic_engine_fingerprint, read_scenario
from .native_write_policy import native_writes_enabled
from .product_receipts import verify_exotic_receipt
from .product_repository import (
    ProductError, load_product, owned_record, previous_command, stage_command, stage_new_product, stage_revision,
)


EXOTIC_CALCULATION_KIND = "EXOTIC_PRICING"
_RESULT = TypeAdapter(RatesMCResult | CreditMcResult)


@dataclass(frozen=True)
class ExoticProductCalculation:
    product: Product
    calculation_id: int
    receipt: dict
    result: RatesMCResult | CreditMcResult


def product_from_exotic_price(claims: dict, *, name: str) -> Product:
    scenario = read_scenario(claims["request"])
    origin = scenario.valuation_date
    origin_product_id = None
    if isinstance(scenario, ExoticRatesScenario):
        instrument, contract = "EXOTIC_RATES", scenario.terms
        payload = contract.model_dump(mode="json", exclude={"nominal_eur", "side"})
        scripted = any("payscript" in flow for flow in payload["cashflows"])
        for flow in payload["cashflows"]:
            flow.pop("realized_rate", None)
            for observation in flow.get("observations", ()):
                observation.pop("realized_rate", None)
        refs = ()
    else:
        instrument, contract = "EXOTIC_CREDIT", scenario.credit.contract
        payload = contract.model_dump(mode="json", exclude={"nominal_eur", "side"})
        scripted = contract.payscript is not None
        refs = tuple(sorted(member.reference_entity_id for member in scenario.credit.market.marginals))
        if scenario.credit.realized is not None:
            origin_product_id = scenario.credit.realized.product.product_id
    effective, maturity = exotic_term_dates(instrument, origin, payload)
    terms = ExoticTerms(schema_version=2, instrument_type=instrument, currency="EUR",
                        template_id=f"{instrument.lower()}-mc", template_version=1, clock="ACT/365F",
                        payoff_mode="scripted" if scripted else "native", time_origin=origin,
                        effective_date=effective, maturity_date=maturity, contract=payload, reference_entities=refs)
    return Product(name=name, terms=terms, origin_product_id=origin_product_id,
                   intent={"nominal": contract.nominal_eur, "side": contract.side})


def read_exotic_price(receipt: dict, *, secret: str) -> tuple[dict, RatesMCResult | CreditMcResult]:
    claims = verify_exotic_receipt(receipt, secret=secret)
    if claims.get("profile") != PROFILE or claims.get("result_fingerprint") != json_transport_fingerprint(claims.get("result")):
        raise ProductError("EXOTIC_RECEIPT_INVALID", "Le reçu ne porte pas un résultat de pricing exotique.", 422)
    result = _RESULT.validate_python(claims["result"])
    family = "rates" if isinstance(result, RatesMCResult) else "credit"
    if claims["request"]["family"] != family:
        raise ProductError("EXOTIC_RECEIPT_INVALID", "Le résultat ne correspond pas à la famille de son reçu.", 422)
    return claims, result


def economic_value(result: RatesMCResult | CreditMcResult) -> float | None:
    if isinstance(result, RatesMCResult):
        return result.pv_eur
    if result.estimate is not None:
        return result.estimate.dirty_pv_eur.mean
    return result.realized.economic_pv_eur if result.realized is not None else None


def booking_diagnostics(calculation: ExoticProductCalculation) -> tuple[str, ...]:
    product = calculation.product
    result = calculation.result
    terms = product.terms
    contract = terms.contract.to_dict()
    is_credit = terms.instrument_type == "EXOTIC_CREDIT"
    issues = []
    if is_credit and terms.payoff_mode == "scripted":
        issues.append("Le booking du crédit PayScript requiert une résolution contractuelle au défaut qualifiée.")
    if is_credit:
        lag_days = contract.get("default_settlement_delay_years", 0.0) * 365
        if not isclose(lag_days, round(lag_days), rel_tol=0, abs_tol=1e-8):
            issues.append("Le délai de règlement du défaut doit être un nombre entier de jours civils ACT/365F.")
        if contract.get("initial_accrued_fraction", 0.0) != 0.0:
            issues.append("Le booking avant événement exige un couru initial nul.")
        if contract["kind"] == "cln" and contract.get("protected_from", 0.0) != 0.0:
            issues.append("Le cycle de vie de la CLN exige une protection à l’origine de la note.")
        if any(coupon["payment"] < coupon["end"] or coupon["end"] > contract["maturity_years"]
               for coupon in contract["coupons"]):
            issues.append("La fin de période doit précéder le paiement et rester dans l’horizon de crédit.")
    if product.archived:
        issues.append("Le Product est archivé.")
    if product.execution is not None:
        issues.append("Le Product porte déjà un Deal.")
    events = tuple(event for leg in product.native_schedule.legs for event in leg.events) if product.native_schedule else ()
    if not events or any(event.date_projection != "exact" for event in events):
        issues.append("Les événements doivent être alignés sur des jours civils ACT/365F avant le pricing.")
    if any(event.model_time_years <= 0 and event.kind in {"observation", "cashflow", "principal", "exercise", "exercise_settlement"}
           for event in events if event.model_time_years is not None):
        issues.append("Un fait d’observation, d’exercice ou de règlement déjà acquis doit être qualifié avant booking.")
    if calculation.receipt["engine_fingerprint"] != exotic_engine_fingerprint():
        issues.append("Le moteur du reçu doit être disponible à l’identique.")
    if economic_value(result) is None or isinstance(result, CreditMcResult) and result.state != "alive":
        issues.append("Le booking exige un prix économique disponible avant tout événement de crédit.")
    forward_rates = (terms.instrument_type == "EXOTIC_RATES" and contract.get("contract_dates") is not None
                     and terms.effective_date > terms.time_origin)
    if terms.effective_date != terms.time_origin and not forward_rates:
        issues.append("Ce contrat exige une prise d’effet à la date d’origine.")
    return tuple(issues)


def _binding(product: Product) -> dict:
    return {"terms_fingerprint": product.terms_fingerprint, "schedule_fingerprint": product.native_schedule.fingerprint,
            "nominal": product.intent.nominal, "side": product.intent.side}


def read_exotic_calculation(session: Session, product_id: int, calculation_id: int, user: User, *, secret: str) -> ExoticProductCalculation:
    owned_record(session, product_id, user)
    row = session.get(ProductCalculationRun, calculation_id)
    if row is None or (row.product_id, row.kind) != (product_id, EXOTIC_CALCULATION_KIND):
        raise ProductError("PRODUCT_CALCULATION_NOT_FOUND", "Calcul exotique introuvable.", 404)
    try:
        archive, result = json.loads(row.input_json), json.loads(row.result_json)
        receipt = {**archive["receipt"], "result": result}
        if row.input_hash != json_transport_fingerprint({**archive, "result": result}):
            raise ValueError("Empreinte de conservation incohérente.")
        claims, priced = read_exotic_price(receipt, secret=secret)
        if claims["user_id"] != row.user_id:
            raise ValueError("Le titulaire de la preuve est incohérent.")
        original = load_product(session, product_id, revision=row.input_revision, terms_version=row.terms_version, allow_native=True)
        if not isinstance(original.terms, ExoticTerms) or _binding(original) != archive["binding"]:
            raise ValueError("Les termes du calcul et du Product diffèrent.")
    except (KeyError, TypeError, ValueError) as exc:
        raise ProductError("EXOTIC_ARCHIVE_INVALID", "Les preuves archivées du calcul exotique sont incohérentes.") from exc
    product = load_product(session, product_id, allow_native=True)
    return ExoticProductCalculation(product, calculation_id, receipt, priced)


def retain_exotic_price(session: Session, user: User, *, name: str, receipt: dict, command_key: str,
                        secret: str) -> ExoticProductCalculation:
    claims, result = read_exotic_price(receipt, secret=secret)
    if claims["user_id"] != user.id:
        raise ProductError("EXOTIC_RECEIPT_NOT_FOUND", "Reçu de valorisation introuvable.", 404)
    command = {"operation": "retain_exotic_price", "name": name, "receipt_fingerprint": json_transport_fingerprint(receipt)}
    existing = previous_command(session, user, command_key, command, allow_native=True)
    if not native_writes_enabled(user, session):
        raise ProductError("NATIVE_PRODUCT_WRITES_CLOSED", "La conservation des exotiques est fermée.", 403)
    if existing is not None:
        ref = next(item for item in existing.calculations if item.kind == EXOTIC_CALCULATION_KIND)
        return read_exotic_calculation(session, existing.product_id, ref.id, user, secret=secret)
    product = stage_new_product(session, product_from_exotic_price(claims, name=name), user=user)
    archive = {"binding": _binding(product), "receipt": {key: value for key, value in receipt.items() if key != "result"}}
    row = ProductCalculationRun(
        product_id=product.product_id, terms_version=product.terms_version, input_revision=product.revision,
        kind=EXOTIC_CALCULATION_KIND, user_id=user.id, calculated_at=datetime.fromisoformat(claims["calculated_at"]),
        valuation_date=claims["request"]["valuation_date"], source="PRICER",
        input_hash=json_transport_fingerprint({**archive, "result": receipt["result"]}),
        input_json=canonical_json(archive), result_json=canonical_json(receipt["result"]),
    )
    session.add(row)
    session.flush()
    ref = CalculationRef(id=row.id, terms_version=product.terms_version, kind=row.kind, source=row.source,
                         calculated_at=claims["calculated_at"], valuation_date=row.valuation_date,
                         price=economic_value(result), measure="exotic_economic_pv", price_unit="EUR",
                         nominal=product.intent.nominal, side=product.intent.side)
    updated = product.model_copy(update={"calculations": (*product.calculations, ref)})
    saved = stage_revision(session, updated, expected_revision=product.revision, actor_id=user.id,
                           action="PRODUCT_CALCULATION_RETAINED", reason="Conservation du prix Monte Carlo signé.")
    stage_command(session, user, command_key, command, saved)
    return ExoticProductCalculation(saved, ref.id, receipt, result)
