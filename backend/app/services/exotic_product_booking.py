"""Atomic booking of a native exotic contract in development."""

from datetime import date
import json

from pydantic import Field
from sqlmodel import Session, select

from ..core.access import require_booking_permission
from ..core.audit import record_audit_event
from ..core.ccr.service import enforce_booking, enforce_otc_documentation
from ..core.product.models import ExoticTerms, FrozenModel, FrozenObject, Product
from ..core.references import next_audited_id
from ..core.valuation_context import canonical_json, json_transport_fingerprint
from ..core.workflow import FixingPolicy
from ..db.models import Deal, DealContractVersion, Entity, User
from .booking_commands import booking_intent, stage_booking_command
from .exotic_product import booking_diagnostics, economic_value, read_exotic_calculation
from .exotic_valuation import price_exotic_scenario, read_scenario, result_payload
from .legal_identity import active_counterparty
from .product_lifecycle import lifecycle_snapshot
from .product_repository import ProductError, load_product, owned_record, stage_revision
from .native_write_policy import native_write_scope, native_writes_enabled


class ExoticBookingRequest(FrozenModel):
    calculation_id: int = Field(gt=0)
    expected_revision: int = Field(gt=0)
    expected_terms_version: int = Field(gt=0)
    command_key: str = Field(min_length=8, max_length=100)
    counterparty_id: int = Field(gt=0)
    execution_price_eur: float
    trade_date: date
    value_date: date
    ccr_netting_set_id: int | None = Field(default=None, gt=0)
    documentation_reference: str | None = Field(default=None, max_length=300)


class _BookingIntent(ExoticBookingRequest):
    product_id: int


class _LegalBooking(FrozenModel):
    transaction_format: str
    instrument_family: str
    ccr_netting_set_id: int | None
    documentation_reference: str | None
    counterparty_id: int
    devise: str
    product_type: str
    nominal: float
    sens: str
    pricing_receipt: None = None


def exotic_transaction_format(terms: ExoticTerms) -> str:
    contract = terms.contract.to_dict()
    if terms.instrument_type == "EXOTIC_CREDIT":
        return "NOTE" if contract["kind"] == "cln" else "OTC"
    return "NOTE" if any(flow["kind"] == "fixed" and not flow.get("is_coupon", True) for flow in contract["cashflows"]) else "OTC"


def _native_booking_kind(deal: Deal) -> str | None:
    if deal.product_id is None:
        return None
    try:
        snapshot = json.loads(deal.market_snapshot_json or "{}")
    except (TypeError, ValueError):
        return None
    return snapshot.get("kind") if isinstance(snapshot, dict) else None


def is_native_exotic_deal(deal: Deal) -> bool:
    return _native_booking_kind(deal) == "native_exotic_booking_v1"


def is_native_template_deal(deal: Deal) -> bool:
    return _native_booking_kind(deal) == "native_template_booking_v1"


def is_native_scheduled_deal(deal: Deal) -> bool:
    return _native_booking_kind(deal) in ("native_exotic_booking_v1", "native_template_booking_v1")


def _require_open(session: Session, user: User) -> None:
    require_booking_permission(user)
    if not native_writes_enabled(user, session):
        raise ProductError("NATIVE_PRODUCT_WRITES_CLOSED", "Le booking natif est fermé sur cette installation.", 403)


def begin_native_booking(session: Session, user: User, product_id: int, body: ExoticBookingRequest):
    _require_open(session, user)
    owned_record(session, product_id, user, right="prepare")
    command = _BookingIntent(product_id=product_id, **body.model_dump())
    key, digest, previous = booking_intent(session, user, command)
    _require_open(session, user)
    if previous is not None:
        if previous.product_id != product_id:
            raise ProductError("BOOKING_NOT_FOUND", "Booking introuvable.", 404)
        return key, digest, load_product(session, product_id, allow_native=True), previous
    return key, digest, load_product(session, product_id, allow_native=True), None


def require_current_unbooked_product(session: Session, product: Product, body: ExoticBookingRequest):
    if (product.revision, product.terms_version) != (body.expected_revision, body.expected_terms_version):
        raise ProductError("PRODUCT_REVISION_STALE", "Le produit a changé. Rechargez le dossier.")
    if product.archived or product.execution is not None or session.exec(select(Deal.id).where(Deal.product_id == product.product_id)).first():
        raise ProductError("PRODUCT_ALREADY_BOOKED", "Le Product est archivé ou porte déjà un Deal.")


def stage_exotic_booking(session: Session, user: User, product_id: int, body: ExoticBookingRequest, *, secret: str) -> tuple[Product, Deal]:
    key, digest, product, previous = begin_native_booking(session, user, product_id, body)
    if previous is not None:
        return product, previous
    archived = read_exotic_calculation(session, product_id, body.calculation_id, user, secret=secret)
    product, terms = archived.product, archived.product.terms
    if not isinstance(terms, ExoticTerms):
        raise ProductError("PRODUCT_TERMS_UNSUPPORTED", "Ce dossier ne porte pas un contrat exotique.", 422)
    require_current_unbooked_product(session, product, body)
    if issues := booking_diagnostics(archived):
        raise ProductError("EXOTIC_BOOKING_INELIGIBLE", " ".join(issues), 422)
    if (body.trade_date, body.value_date) != (terms.time_origin, terms.time_origin):
        raise ProductError("EXOTIC_BOOKING_DATE", "Transaction et valeur doivent reprendre la date du calcul signé.", 422)
    scenario = read_scenario(archived.receipt["request"])
    replayed = result_payload(price_exotic_scenario(scenario))
    if json_transport_fingerprint(replayed) != archived.receipt["result_fingerprint"]:
        raise ProductError("EXOTIC_BOOKING_REPLAY", "Le prix ne se reproduit pas depuis le reçu figé.")

    evidence = {
        "kind": "native_exotic_booking_v1", "calculation_id": archived.calculation_id,
        "terms_fingerprint": product.terms_fingerprint, "schedule_fingerprint": product.native_schedule.fingerprint,
        "engine_fingerprint": archived.receipt["engine_fingerprint"], "result_fingerprint": archived.receipt["result_fingerprint"],
        "receipt_fingerprint": json_transport_fingerprint(archived.receipt), "cutoff": scenario.cutoff.isoformat(),
    }
    return stage_frozen_deal(session, user, product, body, key=key, digest=digest,
                             form=exotic_transaction_format(terms), fair_value=economic_value(archived.result), evidence=evidence)


def stage_frozen_deal(session: Session, user: User, product: Product, body: ExoticBookingRequest, *,
                      key: str, digest: str, form: str, fair_value: float, evidence: dict) -> tuple[Product, Deal]:
    from ..api.deals.serializers import _contract_snapshot, _gen_ref

    product_id, terms, schedule = product.product_id, product.terms, product.native_schedule
    counterparty = active_counterparty(session, body.counterparty_id)
    nominal = product.intent.nominal
    direction = 1 if product.intent.side == "BUY" else -1
    sign = "vente" if direction == 1 else "achat"
    legal = _LegalBooking(transaction_format=form, instrument_family="NOTE" if form == "NOTE" else terms.instrument_type,
                          ccr_netting_set_id=body.ccr_netting_set_id, documentation_reference=body.documentation_reference,
                          counterparty_id=counterparty.id, devise=terms.currency, product_type=terms.instrument_type,
                          nominal=nominal, sens=sign)
    if form == "OTC":
        enforce_otc_documentation(session, user, legal, body.trade_date)
    enforce_booking(session, user, legal)
    # The legacy Deal stores a cleanly labelled per-100 value before applying
    # the position sign. The signed EUR amounts stay in the native evidence.
    price = -evidence["initial_settlement_eur"] if "initial_settlement_eur" in evidence else body.execution_price_eur
    trade_per_100 = direction * price * 100 / nominal
    fair_per_100 = direction * fair_value * 100 / nominal
    if form == "NOTE" and (trade_per_100 <= 0 or fair_per_100 <= 0):
        raise ProductError("EXOTIC_BOOKING_PRICE", "Le prix traité et la valeur de la note par 100 doivent être positifs.", 422)
    payments = [period.payment_date for leg in schedule.legs for period in leg.periods]
    payments.extend(event.date for leg in schedule.legs for event in leg.events
                    if event.date is not None and event.kind in {"cashflow", "principal", "exercise_settlement", "initial_settlement"})
    terminal_payment = max(payments, default=None)
    evidence = {
        **evidence, "economic_dirty_pv_eur": fair_value,
        "execution_price_eur": body.execution_price_eur, "booking_scope": native_write_scope(user, session),
    }
    entity = session.get(Entity, user.entity_id) if user.entity_id is not None else None
    deal = Deal(
        id=next_audited_id(session, Deal, "DEAL"), reference=_gen_ref(entity.name if entity else None, session),
        product_id=product_id, product_terms_version=product.terms_version, entity_id=user.entity_id, user_id=user.id,
        counterparty_id=counterparty.id, contrepartie=counterparty.name, devise=terms.currency, sens=sign, nominal=nominal,
        fair_value=fair_per_100, price_traded=trade_per_100, product_type=terms.instrument_type,
        transaction_format=form, instrument_family=legal.instrument_family, payoff_family=terms.instrument_type,
        documentation_reference=body.documentation_reference, ccr_netting_set_id=body.ccr_netting_set_id,
        fixing_policy=FixingPolicy.FOUR_EYES.value, trade_date=body.trade_date.isoformat(),
        strike_date=terms.effective_date.isoformat(), value_date=body.value_date.isoformat(),
        maturity_date=terms.maturity_date.isoformat(),
        payment_date=max(terminal_payment, terms.maturity_date).isoformat() if terminal_payment else "",
        T=(terms.maturity_date - body.trade_date).days / 365,
        market_snapshot_json=canonical_json(evidence), schedule_json=canonical_json(schedule.model_dump(mode="json")),
    )
    session.add(deal)
    session.flush()
    snapshot = _contract_snapshot(deal)
    session.add(DealContractVersion(deal_id=deal.id, version=1, dedup_key=f"{deal.id}:1",
                                    snapshot_json=canonical_json(snapshot), created_by=user.id))
    intent = product.intent.model_copy(update={
        "counterparty_id": counterparty.id, "counterparty_name": counterparty.name,
        "product_type": terms.instrument_type,
        "transaction_format": form, "instrument_family": legal.instrument_family,
        "payoff_family": terms.instrument_type, "documentation_reference": body.documentation_reference or "",
    })
    updated = product.model_copy(update={"intent": intent, "execution": FrozenObject(snapshot),
                                         "lifecycle": lifecycle_snapshot(session, deal)})
    booked = stage_revision(session, updated, expected_revision=product.revision, actor_id=user.id,
                            action="PRODUCT_BOOKED", reason=f"Booking du Product dans le deal {deal.reference}.")
    record_audit_event(session, action="BOOKING_ACCEPTED", object_type="DEAL", object_id=deal.id,
                       actor_user_id=user.id, result="SUCCESS", after={**evidence, "product_id": product_id,
                       "counterparty_id": counterparty.id, "reference": deal.reference}, metadata={"command_key": key})
    stage_booking_command(session, user, key, digest, deal)
    return booked, deal
