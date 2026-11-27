"""Book deterministic contracts from a retained, reproducible pricing receipt."""

from datetime import date
from math import exp, isfinite
from typing import Literal

from sqlmodel import Session

from ..core.access import can_book
from ..core.product.credit_pilot import case_cutoff
from ..core.product.credit_results import CreditContext, analytic_value
from ..core.product.models import CDSTerms, CLNTerms, FRNTerms, FrozenModel, IRSTerms, Product
from ..core.product.native_market import NativeValuationContext
from ..core.product.rates_payscript import rates_payoff
from ..core.product.rates_pricing import price_rates
from ..core.valuation_context import json_transport_fingerprint
from ..db.models import Deal, User
from .exotic_product_booking import (
    ExoticBookingRequest, begin_native_booking, require_current_unbooked_product, stage_frozen_deal,
)
from .native_calculation_archive import CREDIT_CALCULATION_KIND, RATES_CALCULATION_KIND, read_native_calculation
from .native_valuation_explain import native_explain_engine_fingerprint
from .native_write_policy import native_writes_enabled
from .product_receipts import verify_credit_receipt, verify_rates_receipt
from .product_repository import ProductError


class NativeBookingPreview(FrozenModel):
    supported: bool
    diagnostics: tuple[str, ...]
    trade_date: date
    value_date: date
    effective_date: date
    maturity_date: date
    protection_start_date: date | None
    fair_value_eur: float | None
    currency: Literal["EUR"] = "EUR"
    transaction_format: Literal["NOTE", "OTC"]


def native_booking_capability(session: Session, user: User) -> dict:
    if not native_writes_enabled(user, session):
        return {"supported": False, "diagnostics": ["Le booking natif est fermé sur cette installation."]}
    if not can_book(user):
        return {"supported": False, "diagnostics": ["Le booking exige un compte habilité."]}
    return {"supported": True, "diagnostics": []}


def _verified_archive(session, product, user, calculation_id, secret):
    terms = product.terms
    rates = isinstance(terms, (FRNTerms, IRSTerms))
    if not rates and not isinstance(terms, (CDSTerms, CLNTerms)):
        raise ProductError("PRODUCT_TERMS_UNSUPPORTED", "Ce dossier ne porte pas un Template de taux ou de crédit.", 422)
    receipt = read_native_calculation(session, product.product_id, calculation_id, user,
                                      kind=RATES_CALCULATION_KIND if rates else CREDIT_CALCULATION_KIND)
    verify = verify_rates_receipt if rates else verify_credit_receipt
    verify(receipt, secret=secret)
    context = (NativeValuationContext if rates else CreditContext).model_validate(receipt["context"])
    schedule = product.native_schedule
    if schedule is None or (context.product_id, context.terms_version, context.terms_fingerprint,
            context.schedule_fingerprint, context.nominal, context.side) != (
            product.product_id, product.terms_version, product.terms_fingerprint, schedule.fingerprint,
            product.intent.nominal, product.intent.side):
        raise ProductError("NATIVE_BOOKING_PRICE_MISMATCH", "Repricez la version et la position actuelles du Product.")
    result = receipt["result"]
    if (receipt.get("terms"), receipt.get("schedule"), result.get("instrument_type")) != (
            terms.model_dump(mode="json"), schedule.model_dump(mode="json"), terms.instrument_type):
        raise ProductError("NATIVE_BOOKING_PRICE_MISMATCH", "Le calcul ne correspond pas à l’échéancier et aux termes figés.")
    return receipt, context


def _preview(session, user, product, receipt, context) -> NativeBookingPreview:
    terms, result = product.terms, receipt["result"]
    rates = isinstance(terms, (FRNTerms, IRSTerms))
    cds = isinstance(terms, CDSTerms)
    form = "OTC" if isinstance(terms, (IRSTerms, CDSTerms)) else "NOTE"
    trade_date = context.valuation_date
    settlement = next((event.date for leg in product.native_schedule.legs for event in leg.events
                       if event.kind == "initial_settlement"), None)
    value_date = (settlement if cds else context.value_date if rates else trade_date)
    dirty = result.get("economic_pv_eur") if rates else next(
        (item["value"] for item in result["metrics"] if item["key"] == "dirty_pv"), None)
    capability = native_booking_capability(session, user)
    issues = list(capability["diagnostics"])
    if product.archived or product.execution is not None:
        issues.append("Le Product est archivé ou porte déjà un Deal.")
    if (receipt.get("calculation_identity", {}).get("engine_fingerprint")
            != native_explain_engine_fingerprint("rates" if rates else "credit")):
        issues.append("Relancez le pricing sur le moteur courant et conservez le nouveau calcul.")
    if not rates and result["state"] != "alive":
        issues.append("Choisissez un arrêté de crédit avant tout défaut constaté.")
    elif not rates and receipt["case"] != "INITIAL-DATED" and result["mode"] != "isda_converter":
        issues.append("Choisissez l’arrêté initial daté ou le convertisseur ISDA pour booker ce contrat.")
    if (terms.maturity_date <= trade_date or (cds and terms.trade_date != trade_date)
            or any(period.payment_date <= trade_date for leg in product.native_schedule.legs for period in leg.periods)):
        issues.append("Le booking initial exige sa date de transaction et des flux contractuels encore à venir.")
    if dirty is None or not isfinite(dirty):
        issues.append("La valeur économique de ce calcul est indisponible.")
    if value_date is None:
        raise ProductError("NATIVE_BOOKING_DATE", "Le calendrier ne porte pas la date de règlement initial.", 422)
    return NativeBookingPreview(supported=not issues, diagnostics=tuple(issues), trade_date=trade_date, value_date=value_date,
                                effective_date=terms.effective_date, maturity_date=terms.maturity_date,
                                protection_start_date=terms.effective_date if cds else None,
                                fair_value_eur=dirty, transaction_format=form)


def template_booking_preview(session, user, product, calculation_id, *, secret) -> NativeBookingPreview:
    receipt, context = _verified_archive(session, product, user, calculation_id, secret)
    return _preview(session, user, product, receipt, context)


def _replay(product, receipt, context):
    if isinstance(context, NativeValuationContext):
        payoff, equivalent = None, False
        if product.terms.payoff_mode == "scripted":
            payoff, equivalent, metadata = rates_payoff(product)
            if metadata.model_dump(mode="json") != receipt["script"]:
                raise ProductError("NATIVE_BOOKING_REPLAY", "Le payoff compilé diffère du script signé.")
        return price_rates(product, context, payoff=payoff, equivalent_payoff=equivalent)

    market = context.market.to_dict()
    if receipt["result"]["mode"] == "isda_converter":
        from ..api.credit_pricer import _isda_result

        return _isda_result(product, receipt["case"], NativeValuationContext.model_validate(market["prepared_context"]))[0]
    return analytic_value(product, receipt["case"], case_cutoff(receipt["case"]), recovery=market["pricing_recovery_fraction"],
                          funding_bps=market["funding_bps"])[0]


def stage_template_booking(session: Session, user: User, product_id: int, body: ExoticBookingRequest, *, secret: str) -> tuple[Product, Deal]:
    key, digest, product, previous = begin_native_booking(session, user, product_id, body)
    if previous is not None:
        return product, previous
    require_current_unbooked_product(session, product, body)
    receipt, context = _verified_archive(session, product, user, body.calculation_id, secret)
    preview = _preview(session, user, product, receipt, context)
    if not preview.supported:
        raise ProductError("NATIVE_BOOKING_INELIGIBLE", " ".join(preview.diagnostics), 422)
    if (body.trade_date, body.value_date) != (preview.trade_date, preview.value_date):
        raise ProductError("NATIVE_BOOKING_DATE", "Utilisez les dates de transaction et de valeur du calcul et de son calendrier.", 422)
    replayed = _replay(product, receipt, context).model_dump(mode="json")
    result_fingerprint = json_transport_fingerprint(receipt["result"])
    if json_transport_fingerprint(replayed) != result_fingerprint:
        raise ProductError("NATIVE_BOOKING_REPLAY", "Le prix ne se reproduit pas depuis le reçu figé.")
    evidence = {
        "kind": "native_template_booking_v1", "calculation_id": body.calculation_id,
        "terms_fingerprint": product.terms_fingerprint, "schedule_fingerprint": product.native_schedule.fingerprint,
        "engine_fingerprint": receipt["calculation_identity"]["engine_fingerprint"],
        "receipt_fingerprint": json_transport_fingerprint(receipt), "result_fingerprint": result_fingerprint,
        "cutoff": context.cutoff.isoformat(),
    }
    if isinstance(product.terms, CDSTerms):
        market = context.market.to_dict()
        if receipt["result"]["mode"] == "isda_converter":
            settlement_discount = market["initial_settlement_discount_factor"]
        else:
            settlement_discount = exp(-market["ois_rate"] * (preview.value_date - preview.trade_date).days / 365)
        evidence["initial_settlement_eur"] = body.execution_price_eur
        evidence["initial_settlement_pv_eur"] = body.execution_price_eur * settlement_discount
    return stage_frozen_deal(session, user, product, body, key=key, digest=digest,
                             form=preview.transaction_format, fair_value=preview.fair_value_eur, evidence=evidence)
