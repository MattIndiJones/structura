"""Credit Product pricing, quote evidence and signed calculation retention."""
from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, model_validator
from sqlmodel import Session

from .auth import get_current_pricer, receipt_signing_secret
from ..core.product.credit_default import CreditDefaultDiscount, prepare_credit_default, price_credit_default
from ..core.product.credit_pilot import (
    CALIBRATION_RECOVERY, REFERENCE_ENTITY, SYNTHETIC_OIS, CreditCase, case_cutoff, case_mode,
    credit_catalogue, isda_selection, july_facts, july_prior_payment, verify_synthetic_terms,
)
from ..core.product.credit_pricing import SurvivalPillar
from ..core.product.credit_results import CreditContext, CreditFlow, CreditMeasure, CreditResult, analytic_value, metric, result_for
from ..core.product.isda_market import IsdaMarketSelection
from ..core.product.isda_pricing import price_isda_cds
from ..core.product.models import CDSTerms, CLNTerms, Product, TradeIntent, product_terms_schema
from ..core.product.native_market import NativeValuationContext, prepare_native_context
from ..core.product.native_schedule import native_draft_diagnostics, resolve_native_schedule
from ..core.valuation_context import json_transport_fingerprint
from ..db.database import get_session
from ..db.models import User
from ..services.native_calculation_archive import (
    CREDIT_CALCULATION_KIND, read_native_calculation, stage_native_calculation,
)
from ..services.native_template_booking import native_booking_capability
from ..services.native_context_repository import load_native_context
from ..services.native_write_policy import native_writes_enabled
from ..services.native_valuation_explain import native_explain_engine_fingerprint
from ..services.product_receipts import signed_credit_receipt, verify_credit_receipt
from ..services.product_repository import ProductError, load_product, owned_record, previous_command, stage_command


router = APIRouter(prefix="/api/products", tags=["credit-pricer"])
PricerUser = Annotated[User, Depends(get_current_pricer)]
ProductSession = Annotated[Session, Depends(get_session)]


def _check_terms_schema(terms):
    if not isinstance(terms, (CDSTerms, CLNTerms)) and product_terms_schema(terms) != 2:
        raise ValueError("Le Pricer crédit exige des termes de schéma 2.")
    return terms


CreditTerms = Annotated[CDSTerms | CLNTerms, Field(discriminator="instrument_type"), BeforeValidator(_check_terms_schema)]


class CreditAssumptions(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    pricing_recovery_fraction: float | None = Field(default=None, ge=0, le=1)
    funding_bps: float = Field(default=0, ge=-5_000, le=5_000)


class CreditPriceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case: CreditCase | None = None
    context_id: int | None = Field(default=None, ge=1)
    terms: CreditTerms | None = None
    intent: TradeIntent | None = None
    product_id: int | None = Field(default=None, ge=1)
    expected_revision: int | None = Field(default=None, ge=1)
    expected_terms_version: int | None = Field(default=None, ge=1)
    assumptions: CreditAssumptions = Field(default_factory=CreditAssumptions)

    @model_validator(mode="after")
    def check_target(self):
        if (self.case is None) == (self.context_id is None):
            raise ValueError("Choisissez un scénario ou un contexte ISDA archivé.")
        versions = self.expected_revision, self.expected_terms_version
        if self.product_id is None:
            if self.terms is None or self.intent is None or self.context_id is not None or any(v is not None for v in versions):
                raise ValueError("Le brouillon requiert les termes crédit, l’intention et un scénario.")
        elif self.terms is not None or self.intent is not None or any(v is None for v in versions):
            raise ValueError("Le dossier requiert sa révision et sa version de termes attendues.")
        return self


class CreditPriceResponse(BaseModel):
    result: CreditResult
    context: CreditContext
    receipt: dict
    warnings: tuple[str, ...] = ()


class CreditArchiveResponse(CreditPriceResponse):
    calculation_id: int


class CreditRetentionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    command_key: str = Field(min_length=8, max_length=100)
    expected_revision: int = Field(ge=1)
    receipt: dict


class CreditRetentionResponse(BaseModel):
    calculation_id: int
    product: Product


def _fail(exc: Exception, code: str = "CREDIT_INPUT_INVALID"):
    raise HTTPException(status_code=getattr(exc, "status", 422),
                        detail={"code": getattr(exc, "code", code), "message": str(exc)}) from exc


def _require_credit_terms(product: Product) -> None:
    if not isinstance(product.terms, (CDSTerms, CLNTerms)):
        raise ProductError("PRODUCT_TERMS_UNSUPPORTED", "Ce Pricer concerne les CDS et les CLN.")


def _resolve_product(body: CreditPriceRequest, session: Session, user: User) -> Product:
    if body.product_id is None:
        product = Product(terms=body.terms, intent=body.intent)
    else:
        owned_record(session, body.product_id, user)
        product = load_product(session, body.product_id, allow_native=True)
        _require_credit_terms(product)
        if (product.revision, product.terms_version) != (body.expected_revision, body.expected_terms_version):
            raise ProductError("PRODUCT_REVISION_STALE", "Le dossier a changé. Rechargez le produit.")
    missing = native_draft_diagnostics(product)
    if missing:
        raise ProductError("PRODUCT_DRAFT_INCOMPLETE", " ".join(missing), 422)
    if product.product_id is None:
        product = product.model_copy(update={"native_schedule": resolve_native_schedule(product.terms).schedule})
    if product.native_schedule is None:
        raise ProductError("PRODUCT_SCHEDULE_NOT_READY", "Un échéancier de crédit figé est requis.")
    return product


def _isda_result(product: Product, case: CreditCase, context: NativeValuationContext) -> tuple[CreditResult, dict]:
    priced = price_isda_cds(product, context)
    row = SurvivalPillar(maturity_years=(priced.protection_end_inclusive_date - priced.valuation_date).days / 365,
                         source_quote=priced.quoted_spread_bps, source_unit="bp", source_kind="quoted_spread",
                         normalized_coupon_bps=priced.coupon_bps, normalized_upfront_fraction=priced.clean_upfront_fraction,
                         hazard_rate=priced.constant_hazard_rate, survival=priced.terminal_survival_fraction,
                         reprice_error_eur=priced.calibration_residual_fraction * priced.nominal_eur)
    metrics = (metric("clean_upfront", "Upfront clean", priced.clean_upfront_fraction, "fraction"),
               metric("settlement_buyer_to_seller", "Règlement coté acheteur vers vendeur", priced.cash_settlement_eur_buyer_to_seller),
               metric("position_settlement_cash", "Encaissement de la position au règlement", priced.position_settlement_cash_eur),
               metric("initial_accrued_days", "Jours courus au règlement initial", priced.accrued_days, "days"),
               metric("initial_accrued", "Couru certain du règlement initial", priced.accrued_premium_eur),
               metric("protection", "Protection", priced.protection_pv_eur),
               metric("scheduled_premiums", "Primes programmées", priced.scheduled_premium_pv_eur),
               metric("accrual_on_default", "Prime attendue au défaut", priced.accrual_on_default_pv_eur),
               metric("dirty_pv", "PV dirty", priced.dirty_pv_eur), metric("clean_pv", "PV clean", priced.clean_pv_eur),
               metric("par_spread", "Spread au pair", priced.par_spread_bps, "bp"))
    flows = tuple(CreditFlow(flow_id=item.flow_id, label="Prime programmée", state="expected",
                             payment_date=item.payment_date, amount_eur=item.amount_eur_if_survives,
                             pv_eur=item.scheduled_pv_eur) for item in priced.premium_flows)
    flows = (*flows, CreditFlow(flow_id="cds-protection-expected", label="Protection attendue", state="expected", pv_eur=priced.protection_pv_eur),
             CreditFlow(flow_id="cds-aod-expected", label="Prime attendue au défaut", state="expected", pv_eur=priced.accrual_on_default_pv_eur),
             CreditFlow(flow_id=priced.initial_settlement_flow_id, label="Règlement indicatif du convertisseur", state="indicative",
                        payment_date=priced.initial_cash_settlement_date, amount_eur=priced.position_settlement_cash_eur))
    direction = 1 if context.side == "BUY" else -1
    instant = direction * (priced.nominal_eur * (1 - priced.pricing_recovery_fraction) - priced.accrued_premium_eur)
    result = result_for(product, case, context.cutoff,
                        measure=CreditMeasure(kind="cds_clean_price", unit="per_100_notional", value=priced.clean_price_per_100),
                        metrics=metrics, calibration=(row,), flows=flows,
                        sensitivities=(metric("cs01", "CS01 coté +1 pb", priced.cs01_eur),
                                       metric("jump_to_default", "Défaut immédiat · variation de PV", instant - priced.dirty_pv_eur)))
    selected = context.market
    market = {"provenance": {"kind": "published_historical_benchmark", "reference": f"{priced.benchmark_id} · {priced.scenario_source_cells}",
                             "archive_url": selected.provenance.archive_url},
              "reference_entity_id": product.terms.reference_entity_id, "ois_rate": None, "funding_bps": 0,
              "calibration_recovery_fraction": priced.calibration_recovery_fraction, "pricing_recovery_fraction": priced.pricing_recovery_fraction,
              "ois_quotes": selected.ois_quotes.model_dump(mode="json"),
              "ois_pillars": [{"date": p.maturity_date.isoformat(), **p.model_dump(mode="json")} for p in priced.ois_curve.pillars],
              "prepared_context_fingerprint": context.fingerprint, "prepared_context": context.model_dump(mode="json"),
              "step_in_date": priced.step_in_date.isoformat(), "protection_end_date": priced.protection_end_inclusive_date.isoformat(),
              "initial_settlement_date": priced.initial_cash_settlement_date.isoformat(),
              "initial_settlement_discount_factor": priced.initial_settlement_discount_factor,
              "jump_to_default": {"valuation_date": priced.valuation_date.isoformat(), "delay_days": 0,
                                   "recovery_fraction": priced.pricing_recovery_fraction, "accrued_eur": priced.accrued_premium_eur}}
    return result, market


def _default_result(product: Product, case: CreditCase, assumptions: CreditAssumptions, recovery: float) -> tuple[CreditResult, dict]:
    cutoff = case_cutoff(case)
    default_id, facts = july_facts(case)
    coupon = july_prior_payment(product)
    frozen = prepare_credit_default(product, valuation_date=cutoff.date(), cutoff=cutoff, default_id=default_id,
                                    facts=facts, settlement_date=date(2021, 7, 20), reference_entity_id=REFERENCE_ENTITY,
                                    prior_payments=(coupon,), discount=CreditDefaultDiscount(ois_rate=SYNTHETIC_OIS,
                                                                                              cln_funding_bps=float(assumptions.funding_bps)))
    market = {"provenance": {"kind": "synthetic", "reference": default_id}, "reference_entity_id": product.terms.reference_entity_id,
              "ois_rate": SYNTHETIC_OIS, "funding_bps": assumptions.funding_bps, "calibration_recovery_fraction": None,
              "pricing_recovery_fraction": recovery, "default_context": frozen.model_dump(mode="json")}
    if frozen.facts.state == "alive":
        result, live_market = analytic_value(product, case, cutoff, recovery=recovery, funding_bps=assumptions.funding_bps)
        prior = CreditFlow(flow_id=coupon.flow_id, label="Coupon antérieur confirmé", state="paid", payment_date=coupon.effect_date,
                           amount_eur=coupon.amount_eur, pv_eur=0)
        return result.model_copy(update={"flows": (*result.flows, prior)}), {**live_market, "default_context": market["default_context"],
                                                                          "prior_payment": coupon.model_dump(mode="json")}

    priced = price_credit_default(product, frozen)
    market["final_recovery_fraction"] = priced.recovery_fraction
    events = tuple(fact.model_dump(mode="json") for fact in (frozen.facts.default, frozen.facts.recovery, frozen.facts.settlement)
                   if fact is not None)
    metrics = (metric("net_due", "Règlement net dû", priced.net_due_eur), metric("claim_pv", "PV du règlement dû", priced.claim_pv_eur),
               metric("cash_on_value_date", "Cash confirmé à l’arrêté", priced.cash_on_value_date_eur),
               metric("contingent_pv", "PV contingente", priced.contingent_pv_eur),
               metric("accrued_days", "Jours de prime courue au défaut", priced.accrued_days_at_default, "days"),
               metric("final_recovery", "Recouvrement final constaté", priced.recovery_fraction, "fraction"))
    labels = {"protection": "Protection constatée", "accrued_premium": "Prime courue au défaut",
              "recovery_redemption": "Remboursement au recouvrement", "earned_coupon": "Coupon acquis"}
    flows = tuple(CreditFlow(flow_id=item.flow_id, label=labels[item.kind], state=item.state,
                             payment_date=item.paid_date or item.scheduled_date, amount_eur=item.amount_eur, pv_eur=item.pv_eur)
                  for item in (*priced.earned_coupon_flows, *priced.components))
    result = result_for(product, case, cutoff, state=priced.state, measure=CreditMeasure.model_validate(priced.measure.model_dump()),
                        metrics=metrics, flows=flows, events=events,
                        sensitivities=(metric("cs01", "CS01 du règlement constaté", 0.0),)
                        if priced.state in ("settlement_pending", "settled") else ())
    if priced.settlement_flow is not None:
        market["settlement_flow"] = priced.settlement_flow.model_dump(mode="json")
    return result, market


@router.get("/credit/pilots")
def list_credit_pilots(current: PricerUser, session: ProductSession):
    return {"can_retain": native_writes_enabled(current, session), "products": credit_catalogue(),
            "booking": native_booking_capability(session, current)}


@router.post("/credit/price")
def calculate_credit(body: CreditPriceRequest, current: PricerUser, session: ProductSession) -> CreditPriceResponse:
    try:
        product = _resolve_product(body, session, current)
        assumptions = body.assumptions
        if isinstance(product.terms, CDSTerms) and assumptions.funding_bps:
            raise ProductError("CREDIT_FUNDING_INCOMPATIBLE", "Le funding émetteur s’applique à la CLN.", 422)
        recovery = CALIBRATION_RECOVERY if assumptions.pricing_recovery_fraction is None else assumptions.pricing_recovery_fraction
        prepared = None
        case = body.case
        if body.context_id is not None:
            prepared = load_native_context(session, product.product_id, body.context_id, user=current)
            if not isinstance(prepared.market, IsdaMarketSelection) or not isinstance(product.terms, CDSTerms):
                raise ProductError("CREDIT_CONTEXT_INCOMPATIBLE", "Ce contexte ne contient pas le jeu ISDA du CDS.", 422)
            if (prepared.terms_version, prepared.nominal, prepared.side) != (product.terms_version, product.intent.nominal, product.intent.side):
                raise ProductError("CREDIT_CONTEXT_STALE", "Le contexte appartient à une autre version ou position.")
            case = f"ISDA-{prepared.market.scenario.market_inputs.quoted_spread_bp}"
        mode = case_mode(case)
        cutoff = case_cutoff(case) if prepared is None else prepared.cutoff
        valuation_date = cutoff.date() if prepared is None else prepared.valuation_date
        warnings = ()
        if mode == "isda_converter":
            if not isinstance(product.terms, CDSTerms) or recovery != CALIBRATION_RECOVERY:
                raise ProductError("ISDA_CONVENTIONS_REQUIRED", "La grille requiert le CDS et son recouvrement de référence de 40 %.", 422)
            if prepared is None:
                prepared = prepare_native_context(product, valuation_date=valuation_date, cutoff=cutoff,
                                                  market=isda_selection(case), allow_draft=True)
            result, market = _isda_result(product, case, prepared)
            engine_version = "isda-eur-rfr-converter-v1"
        else:
            verify_synthetic_terms(product, case)
            if mode == "piecewise_survival":
                result, market = analytic_value(product, case, cutoff, recovery=recovery, funding_bps=assumptions.funding_bps)
                engine_version = "eur-credit-survival-v1"
            else:
                result, market = _default_result(product, case, assumptions, recovery)
                engine_version = "eur-credit-survival-v1" if result.state == "alive" else "synthetic-credit-default-v1"
                if result.state == "recovery_pending":
                    warnings = ("Le défaut est reconnu. Le recouvrement final et le montant à régler sont en attente.",)
        context = CreditContext.seal(product, valuation_date=valuation_date, cutoff=cutoff, market=market)
        receipt = signed_credit_receipt({
            "user_id": current.id, "product_reference": product.reference, "input_revision": product.revision,
            "context_id": body.context_id, "case": case, "engine_version": engine_version, "warnings": warnings,
            "calculation_identity": {"engine_version": engine_version, "engine_fingerprint": native_explain_engine_fingerprint("credit")},
            "terms": product.terms.model_dump(mode="json"), "schedule": product.native_schedule.model_dump(mode="json"),
            "context": context.model_dump(mode="json"), "result": result.model_dump(mode="json"),
        }, secret=receipt_signing_secret())
        return CreditPriceResponse(result=result, context=context, receipt=receipt, warnings=warnings)
    except (ValueError, ArithmeticError) as exc:
        _fail(exc)


def _require_retention(session: Session, current: User):
    if not native_writes_enabled(current, session):
        raise ProductError("NATIVE_PRODUCT_WRITES_CLOSED", "La conservation du crédit est fermée dans cette installation.", 403)


@router.post("/{product_id}/credit/calculations", status_code=201)
def retain_credit_calculation(product_id: int, body: CreditRetentionRequest,
                              current: PricerUser, session: ProductSession) -> CreditRetentionResponse:
    try:
        _require_retention(session, current)
        owned_record(session, product_id, current, right="prepare")
        payload = {"operation": "retain_credit_calculation", "product_id": product_id,
                   "expected_revision": body.expected_revision, "receipt_fingerprint": json_transport_fingerprint(body.receipt)}
        previous = previous_command(session, current, body.command_key, payload, allow_native=True)
        _require_retention(session, current)
        if previous is not None:
            session.rollback()
            return CreditRetentionResponse(calculation_id=previous.calculations[-1].id, product=previous)
        verified = verify_credit_receipt(body.receipt, secret=receipt_signing_secret())
        product = load_product(session, product_id, allow_native=True)
        _require_credit_terms(product)
        if product.revision != body.expected_revision:
            raise ProductError("PRODUCT_REVISION_STALE", "Le dossier a changé. Rechargez le produit.")
        context = CreditContext.model_validate(verified["context"])
        refs = (context.product_id, context.terms_version, context.terms_fingerprint, context.schedule_fingerprint,
                context.nominal, context.side, verified["product_reference"], verified["input_revision"], verified["user_id"])
        schedule = product.native_schedule
        if schedule is None or refs != (product_id, product.terms_version, product.terms_fingerprint, schedule.fingerprint,
                                         product.intent.nominal, product.intent.side, product.reference, product.revision, current.id):
            raise ProductError("CREDIT_RECEIPT_MISMATCH", "Le reçu ne correspond plus au dossier et à sa position.")
        if verified["context_id"] is not None:
            prepared = load_native_context(session, product_id, verified["context_id"], user=current)
            if prepared.fingerprint != context.market.to_dict()["prepared_context_fingerprint"]:
                raise ProductError("CREDIT_RECEIPT_MISMATCH", "Le contexte archivé ne correspond pas au reçu.")
        saved, calculation_id = stage_native_calculation(session, product, current, body.receipt, kind=CREDIT_CALCULATION_KIND,
                                                         reason="Conservation du calcul de crédit.")
        stage_command(session, current, body.command_key, payload, saved)
        session.commit()
        return CreditRetentionResponse(calculation_id=calculation_id, product=saved)
    except ValueError as exc:
        session.rollback()
        _fail(exc, "CREDIT_RECEIPT_INVALID")
    except Exception:
        session.rollback()
        raise


@router.get("/{product_id}/credit/calculations/{calculation_id}")
def reopen_credit_calculation(product_id: int, calculation_id: int, current: PricerUser,
                              session: ProductSession) -> CreditArchiveResponse:
    try:
        receipt = read_native_calculation(session, product_id, calculation_id, current, kind=CREDIT_CALCULATION_KIND)
        return CreditArchiveResponse(calculation_id=calculation_id, result=receipt["result"], context=receipt["context"],
                                     receipt=receipt, warnings=receipt["warnings"])
    except ValueError as exc:
        _fail(exc, "CREDIT_ARCHIVE_INVALID")
