"""Maker/checker evidence on the native exotic schedule."""

from dataclasses import dataclass
from datetime import date, datetime, timezone
import json
from math import isclose
from typing import Annotated, Literal
from zoneinfo import ZoneInfo

from pydantic import AwareDatetime, Field, field_validator, model_validator
from sqlmodel import Session, select

from ..core.access import has_capability
from ..core.audit import record_audit_event
from ..core.product.models import ExoticTerms, FrozenModel, FrozenObject
from ..core.valuation_context import canonical_json, json_transport_fingerprint
from ..db.models import Deal, NativeExoticLifecycleEntry, User
from ..runtime import business_now
from .business_access import can_read_deal
from .exotic_cln_lifecycle import (
    DEFAULT_EVENT, RECOVERY_EVENT, SETTLEMENT_EVENT, cln_civil_date, cln_contract,
    cln_coupon_amount, cln_redemption_amount, cln_settlement_date,
)
from .exotic_product_booking import is_native_exotic_deal, is_native_template_deal
from .exotic_rates_residual import signed_rates_payment
from .native_template_lifecycle import (
    TEMPLATE_TERMS, TemplateEventState, template_credit_targets, template_event,
    template_event_states, template_resolution, validate_template_fact,
)
from .native_write_policy import native_write_scope
from .product_lifecycle import lifecycle_snapshot
from .product_repository import ProductError, load_product, lock_command_actor, stage_revision


_PARIS = ZoneInfo("Europe/Paris")
_DIGEST = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class RateFixing(FrozenModel):
    kind: Literal["rate_fixing"]
    rate_fraction: float


class ExerciseNotice(FrozenModel):
    kind: Literal["exercise_notice"]
    exercised: bool = Field(strict=True)


class PaymentConfirmation(FrozenModel):
    kind: Literal["payment_confirmed"]
    amount_eur: float


class _CreditFact(FrozenModel):
    reference_entity_id: str = Field(min_length=1, max_length=128)
    effect_date: date


class CreditDefault(_CreditFact):
    kind: Literal["credit_default"]


class CreditRecovery(_CreditFact):
    kind: Literal["credit_recovery"]
    recovery_fraction: float = Field(ge=0, le=1)


class CreditSettlement(_CreditFact):
    kind: Literal["credit_settlement"]
    amount_eur: float


Fact = Annotated[
    RateFixing | ExerciseNotice | PaymentConfirmation | CreditDefault | CreditRecovery | CreditSettlement,
    Field(discriminator="kind"),
]


class CreditFactTarget(FrozenModel):
    event_id: str
    kind: Literal["credit_default", "credit_recovery", "credit_settlement"]
    reference_entity_id: str
    earliest_effect_date: date
    expected_amount_eur: float | None = Field(default=None, exclude_if=lambda value: value is None)


@dataclass(frozen=True)
class _CreditEvent:
    event_id: str
    kind: str
    date: date


class FactProposal(FrozenModel):
    command_key: str = Field(min_length=8, max_length=100)
    expected_contract_version: int = Field(gt=0)
    schedule_fingerprint: _DIGEST
    event_id: str = Field(min_length=1, max_length=250)
    observed_at: AwareDatetime
    available_at: AwareDatetime
    source_reference: str = Field(min_length=3, max_length=250, pattern=r"^\S(?:.*\S)?$")
    source_fingerprint: _DIGEST
    fact: Fact

    @field_validator("observed_at", "available_at")
    @classmethod
    def as_utc(cls, value: datetime) -> datetime:
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def observation_before_availability(self):
        if self.available_at < self.observed_at:
            raise ValueError("La preuve ne peut être disponible avant l’observation ou le règlement.")
        return self


class FactDecision(FrozenModel):
    command_key: str = Field(min_length=8, max_length=100)
    decision: Literal["validate", "reject"]
    reason: str = Field(min_length=3, max_length=500, pattern=r"^\S(?:.*\S)?$")


class FactRow(FrozenModel):
    id: int
    event_id: str
    event_kind: str
    event_date: date
    observed_at: AwareDatetime
    available_at: AwareDatetime
    source_reference: str
    source_fingerprint: _DIGEST
    fact: Fact
    proposed_by: int
    proposed_at: AwareDatetime
    status: Literal["pending", "validated", "rejected"]
    validated_by: int | None = None
    validated_at: AwareDatetime | None = None
    decided_by: int | None = Field(default=None, exclude_if=lambda value: value is None)
    decided_at: AwareDatetime | None = Field(default=None, exclude_if=lambda value: value is None)
    decision_reason: str | None = Field(default=None, exclude_if=lambda value: value is None)
    can_decide: bool = False


class FactLedger(FrozenModel):
    deal_id: int
    contract_version: int
    schedule_fingerprint: _DIGEST
    cutoff: AwareDatetime
    eligible: tuple[FactRow, ...]
    pending: tuple[FactRow, ...]
    limitations: tuple[str, ...]
    can_propose: bool
    can_decide: bool
    credit_targets: tuple[CreditFactTarget, ...] = ()
    contract_events: tuple[TemplateEventState, ...] | None = Field(default=None, exclude_if=lambda value: value is None)
    history: tuple[FactRow, ...] | None = Field(default=None, exclude_if=lambda value: value is None)


def _utc(value: datetime) -> datetime:
    return value.astimezone(timezone.utc) if value.utcoffset() is not None else value.replace(tzinfo=timezone.utc)


def load_exotic_deal_scope(session: Session, deal_id: int, actor: User):
    return _load_native_deal_scope(session, deal_id, actor, include_templates=False)


def _load_native_deal_scope(session: Session, deal_id: int, actor: User, *, include_templates=True):
    deal = session.get(Deal, deal_id)
    template = deal is not None and include_templates and is_native_template_deal(deal)
    if not deal or not can_read_deal(deal, actor, session) or not (template or is_native_exotic_deal(deal)):
        raise ProductError("EXOTIC_DEAL_NOT_FOUND", "Deal natif introuvable.", 404)
    product = load_product(session, deal.product_id, terms_version=deal.product_terms_version, allow_native=True)
    schedule = product.native_schedule
    expected_side = "BUY" if deal.sens == "vente" else "SELL" if deal.sens == "achat" else None
    try:
        booked_schedule, snapshot = json.loads(deal.schedule_json), json.loads(deal.market_snapshot_json)
    except (ValueError, TypeError) as exc:
        raise ProductError("EXOTIC_DEAL_SCHEDULE_INVALID", "La preuve de booking est illisible.") from exc
    if (not isinstance(product.terms, TEMPLATE_TERMS if template else ExoticTerms)
            or schedule is None or product.execution is None
            or (product.intent.nominal, product.intent.side) != (deal.nominal, expected_side)
            or (product.execution.to_dict().get("deal_id"), product.execution.to_dict().get("contract_version"))
            != (deal.id, deal.contract_version)
            or schedule.model_dump(mode="json") != booked_schedule
            or schedule.fingerprint != snapshot.get("schedule_fingerprint")
            or (template and (snapshot.get("terms_fingerprint") != product.terms_fingerprint
                              or deal.product_type != product.terms.instrument_type
                              or product.execution.to_dict().get("market_snapshot") != snapshot))):
        raise ProductError("EXOTIC_DEAL_SCHEDULE_INVALID", "Le Deal ou son échéancier figé a changé.")
    return deal, product, schedule


def _may(actor: User, session: Session, capability: str) -> bool:
    return native_write_scope(actor, session) is not None and has_capability(actor, capability)


def _require(actor: User, session: Session, capability: str):
    if not _may(actor, session, capability):
        raise ProductError("EXOTIC_FACT_AUTHORITY", "Cette action exige un workspace de développement ou de recette et un compte habilité.", 403)


def _binding(deal, schedule) -> dict:
    return {"deal_id": deal.id, "deal_reference": deal.reference, "contract_version": deal.contract_version,
            "schedule_fingerprint": schedule.fingerprint}


def _entry_body(row: NativeExoticLifecycleEntry) -> dict:
    return {"deal_id": row.deal_id, "deal_reference": row.deal_reference, "contract_version": row.contract_version,
            "schedule_fingerprint": row.schedule_fingerprint, "actor_id": row.actor_id, "command_key": row.command_key,
            "proposal_id": row.proposal_id, "created_at": _utc(row.created_at).isoformat(),
            "payload": json.loads(row.entry_json)}


def _payload(row: NativeExoticLifecycleEntry) -> dict:
    body = _entry_body(row)
    if row.entry_hash != json_transport_fingerprint(body):
        raise ProductError("EXOTIC_FACT_EVIDENCE_INVALID", "L’empreinte de la preuve de cycle de vie est invalide.")
    return body["payload"]


def _rows(session, deal, schedule):
    return tuple(session.exec(select(NativeExoticLifecycleEntry).where(
        NativeExoticLifecycleEntry.deal_id == deal.id,
        NativeExoticLifecycleEntry.deal_reference == deal.reference,
        NativeExoticLifecycleEntry.contract_version == deal.contract_version,
        NativeExoticLifecycleEntry.schedule_fingerprint == schedule.fingerprint,
    ).order_by(NativeExoticLifecycleEntry.id)).all())


def _prior(session, actor, key, *, deal, schedule, payload, proposal_id=None):
    row = session.exec(select(NativeExoticLifecycleEntry).where(
        NativeExoticLifecycleEntry.actor_id == actor.id, NativeExoticLifecycleEntry.command_key == key,
    )).first()
    if row is None:
        return None
    body = _entry_body(row)
    if (any(body[field] != value for field, value in _binding(deal, schedule).items())
            or row.proposal_id != proposal_id or _payload(row) != payload):
        raise ProductError("EXOTIC_FACT_COMMAND_CONFLICT", "Cette clé de commande porte déjà une autre preuve.")
    return row


def _append(session, actor, key, *, deal, schedule, payload, now, proposal_id=None) -> NativeExoticLifecycleEntry:
    record = NativeExoticLifecycleEntry(**_binding(deal, schedule), actor_id=actor.id, command_key=key,
                                       proposal_id=proposal_id, entry_json=canonical_json(payload), created_at=now)
    record.entry_hash = json_transport_fingerprint(_entry_body(record))
    session.add(record)
    session.flush()
    return record


def _project(proposal, decision=None, *, include_decision=False) -> FactRow:
    attributes = _payload(proposal)
    decision_body = _payload(decision) if decision is not None else None
    status = "pending" if decision_body is None else "validated" if decision_body["decision"] == "validate" else "rejected"
    # The rejection is a closing decision, never an effective stored fact.
    validated = status == "validated"
    audit = {"decided_by": decision.actor_id, "decided_at": _utc(decision.created_at),
             "decision_reason": decision_body["reason"]} if include_decision and decision_body is not None else {}
    return FactRow(**attributes, id=proposal.id, proposed_by=proposal.actor_id, proposed_at=_utc(proposal.created_at),
                   status=status, validated_by=decision.actor_id if validated else None,
                   validated_at=_utc(decision.created_at) if validated else None, **audit)


def _projected_history(rows, cutoff, *, include_decisions=False):
    decisions = {row.proposal_id: row for row in rows if row.proposal_id is not None and _utc(row.created_at) <= cutoff}
    return tuple(_project(row, decisions.get(row.id), include_decision=include_decisions) for row in rows
                 if row.proposal_id is None and _utc(row.created_at) <= cutoff)


def _classified(items, cutoff):
    eligible = tuple(item for item in items if item.status == "validated" and item.observed_at <= cutoff and item.available_at <= cutoff)
    pending = tuple(item for item in items if item.status == "pending" and item.available_at <= cutoff)
    return eligible, pending


def _as_of(rows, cutoff):
    return _classified(_projected_history(rows, cutoff), cutoff)


def _cln_targets(product, eligible) -> tuple[CreditFactTarget, ...]:
    contract = cln_contract(product)
    evidence = {row.event_id: row for row in eligible}
    reference = product.terms.reference_entities[0]
    if "principal:payment" in evidence or SETTLEMENT_EVENT in evidence:
        return ()
    if DEFAULT_EVENT not in evidence:
        event_id, kind = DEFAULT_EVENT, "credit_default"
        earliest = cln_civil_date(product, contract.protected_from)
    elif RECOVERY_EVENT not in evidence:
        event_id, kind = RECOVERY_EVENT, "credit_recovery"
        earliest = evidence[DEFAULT_EVENT].fact.effect_date
    else:
        event_id, kind = SETTLEMENT_EVENT, "credit_settlement"
        earliest = cln_settlement_date(product, evidence[DEFAULT_EVENT].fact.effect_date)
    return (CreditFactTarget(event_id=event_id, kind=kind, reference_entity_id=reference, earliest_effect_date=earliest),)


def read_exotic_ledger(session, deal_id, actor, *, cutoff=None) -> FactLedger:
    deal, product, schedule = _load_native_deal_scope(session, deal_id, actor)
    cutoff = _utc(cutoff or business_now())
    rows = _rows(session, deal, schedule)
    template = isinstance(product.terms, TEMPLATE_TERMS)
    history = _projected_history(rows, cutoff, include_decisions=template)
    eligible, pending = _classified(history, cutoff)
    if template:
        can_propose = deal.status == "actif" and _may(actor, session, "operations.prepare")
        can_decide = _may(actor, session, "operations.validate")
        pending = tuple(item.model_copy(update={"can_decide": can_decide and item.proposed_by != actor.id}) for item in pending)
        return FactLedger(deal_id=deal.id, contract_version=deal.contract_version, schedule_fingerprint=schedule.fingerprint,
                          cutoff=cutoff, eligible=eligible, pending=pending, limitations=(),
                          can_propose=can_propose, can_decide=can_decide,
                          credit_targets=template_credit_targets(product, eligible) if deal.status == "actif" else (),
                          contract_events=template_event_states(product, json.loads(deal.market_snapshot_json), eligible, cutoff),
                          history=history)
    credit = product.terms.instrument_type == "EXOTIC_CREDIT"
    cln = credit and product.terms.contract.to_dict().get("kind") == "cln"
    limitations = (("Le registre traite la CLN single-name en recette.",) if cln else
                   ("Les événements de défaut des CDS et paniers restent à qualifier.",) if credit else
                   ("Un fixing de spread requiert une preuve pour chacun des deux indices.",))
    supported = not credit or cln
    can_decide = supported and _may(actor, session, "operations.validate")
    pending = tuple(item.model_copy(update={"can_decide": can_decide and item.proposed_by != actor.id}) for item in pending)
    return FactLedger(deal_id=deal.id, contract_version=deal.contract_version, schedule_fingerprint=schedule.fingerprint,
                      cutoff=cutoff, eligible=eligible, pending=pending, limitations=limitations,
                      can_propose=supported and _may(actor, session, "operations.prepare"),
                      can_decide=can_decide, credit_targets=_cln_targets(product, eligible) if cln else ())


def _event(product, schedule, event_id, fact):
    if isinstance(product.terms, TEMPLATE_TERMS):
        return template_event(product, event_id, fact)
    if product.terms.instrument_type == "EXOTIC_CREDIT":
        cln_contract(product)
        for credit_event, kind in ((DEFAULT_EVENT, "credit_default"), (RECOVERY_EVENT, "credit_recovery"),
                                   (SETTLEMENT_EVENT, "credit_settlement")):
            if event_id == credit_event and fact.kind == kind:
                return _CreditEvent(event_id, kind, fact.effect_date)
    if isinstance(fact, _CreditFact):
        raise ProductError("EXOTIC_FACT_EVENT_INVALID", "Le fait de crédit doit viser son événement natif.", 422)
    result = next((item for leg in schedule.legs for item in leg.events if item.event_id == event_id), None)
    if result is None or result.date_projection != "exact":
        raise ProductError("EXOTIC_FACT_EVENT_INVALID", "Sélectionnez un événement du calendrier civil figé.", 422)
    return result


def _booked_amount(product, event, eligible) -> float:
    terms = product.terms.contract.to_dict()
    notices = {row.event_id: row.fact.exercised for row in eligible if isinstance(row.fact, ExerciseNotice)}
    if event.kind == "exercise_settlement":
        item = next(right for right in terms["exercises"] if right["exercise_id"] == event.flow_id)
        if not notices.get(f"{event.flow_id}:decision"):
            raise ProductError("EXOTIC_FACT_PAYMENT_UNQUALIFIED", "Le règlement requiert un exercice préalablement validé.", 422)
        return item["redemption_eur"]
    item = next((flow for flow in terms["cashflows"] if flow["flow_id"] == event.flow_id), None)
    if item is None or item["kind"] != "fixed":
        raise ProductError("EXOTIC_FACT_PAYMENT_UNQUALIFIED", "Le montant de ce flux n’est pas directement fixé par le contrat.", 422)
    for right in terms["exercises"]:
        notice = notices.get(f"{right['exercise_id']}:decision")
        paid_before_exercise = (notice is True and right["decision"] == item["payment"]
                                and item.get("is_coupon", True) and right["coupon_priority"] == "before")
        if right["decision"] <= item["payment"] and notice is not False and not paid_before_exercise:
            raise ProductError("EXOTIC_FACT_PAYMENT_UNQUALIFIED", "Les avis d’exercice validés doivent confirmer le droit au paiement.", 422)
    return item["amount_eur"]


def _validate_fact(deal, product, event, proposal, eligible, now):
    if isinstance(product.terms, TEMPLATE_TERMS):
        validate_template_fact(product, json.loads(deal.market_snapshot_json), event, proposal, eligible, now)
        return
    if product.terms.instrument_type == "EXOTIC_CREDIT":
        _validate_cln_fact(product, event, proposal, eligible, now)
        return
    fact, observed = proposal.fact, proposal.observed_at.astimezone(_PARIS).date()
    allowed = {"rate_fixing": ("observation",), "exercise_notice": ("exercise",),
               "payment_confirmed": ("cashflow", "exercise_settlement")}
    if (event.kind not in allowed[fact.kind] or proposal.available_at > now
            or observed < event.date or fact.kind != "payment_confirmed" and observed != event.date):
        raise ProductError("EXOTIC_FACT_DATE_OR_KIND", "Le type ou l’horodatage de preuve contredit la date contractuelle.", 422)
    if isinstance(fact, RateFixing):
        flow = next(item for item in product.terms.contract.to_dict()["cashflows"] if item["flow_id"] == event.flow_id)
        if flow.get("spread_index") is not None:
            raise ProductError("EXOTIC_FACT_FIXING_UNQUALIFIED", "Un fixing de spread exige la preuve séparée de ses deux indices.", 422)
    if isinstance(fact, ExerciseNotice):
        notices = {row.event_id: row.fact.exercised for row in eligible if isinstance(row.fact, ExerciseNotice)}
        preceding = (right for right in product.terms.contract.to_dict()["exercises"] if right["decision"] < event.model_time_years)
        if any(notices.get(f"{right['exercise_id']}:decision") is not False for right in preceding) or fact.exercised and any(notices.values()):
            raise ProductError("EXOTIC_FACT_EXERCISE_SEQUENCE", "Les droits d’exercice antérieurs doivent avoir été déclinés.", 422)
    if isinstance(fact, PaymentConfirmation):
        side = 1 if product.intent.side == "BUY" else -1
        contract = product.terms.contract.to_dict()
        if event.kind == "cashflow" and any(item["flow_id"] == event.flow_id and item["kind"] != "fixed"
                                          for item in contract["cashflows"]):
            amount = signed_rates_payment(product, event.event_id, eligible)
        else:
            amount = side * _booked_amount(product, event, eligible)
        if not isclose(fact.amount_eur, amount, abs_tol=.005, rel_tol=0):
            raise ProductError("EXOTIC_FACT_PAYMENT_AMOUNT", "Le paiement attesté contredit le montant contractuel signé.", 422)


def _validate_cln_fact(product, event, proposal, eligible, now):
    fact = proposal.fact
    observed = proposal.observed_at.astimezone(_PARIS).date()
    evidence = {row.event_id: row for row in eligible}
    contract = cln_contract(product)
    default = evidence.get(DEFAULT_EVENT)
    maturity = cln_civil_date(product, contract.maturity_years)
    if proposal.available_at > now:
        raise ProductError("EXOTIC_FACT_DATE_OR_KIND", "La preuve doit être disponible à cet arrêté.", 422)
    if isinstance(fact, _CreditFact):
        if (fact.reference_entity_id != product.terms.reference_entities[0] or fact.effect_date > observed):
            raise ProductError("EXOTIC_CLN_PROOF", "La référence ou la date d’effet contredit la preuve fournie.", 422)
        if isinstance(fact, CreditDefault):
            if ("principal:payment" in evidence
                    or not cln_civil_date(product, contract.protected_from) <= fact.effect_date <= maturity):
                raise ProductError("EXOTIC_CLN_DEFAULT_DATE", "Le défaut doit relever de la protection du Deal.", 422)
            for index, coupon in enumerate(contract.coupons, 1):
                if (f"credit-coupon-{index}:payment" in evidence
                        and cln_civil_date(product, coupon.survival_time) >= fact.effect_date):
                    raise ProductError("EXOTIC_CLN_DEFAULT_CONFLICT", "Le défaut contredit un coupon déjà réglé.", 422)
            return
        if default is None or fact.effect_date < default.fact.effect_date:
            raise ProductError("EXOTIC_CLN_DEFAULT_REQUIRED", "Un défaut validé est requis avant ce fait de crédit.", 422)
        if isinstance(fact, CreditRecovery):
            return
        recovery = evidence.get(RECOVERY_EVENT)
        if (recovery is None or fact.effect_date < recovery.fact.effect_date
                or fact.effect_date < cln_settlement_date(product, default.fact.effect_date)):
            raise ProductError("EXOTIC_CLN_SETTLEMENT_DATE", "Le règlement exige un recouvrement validé et sa date contractuelle.", 422)
        amount = cln_redemption_amount(contract, recovery.fact.recovery_fraction)
    elif isinstance(fact, PaymentConfirmation) and event.kind in {"cashflow", "principal"} and observed >= event.date:
        if event.kind == "principal":
            if default is not None:
                raise ProductError("EXOTIC_CLN_PRINCIPAL_CANCELLED", "Un défaut validé remplace le principal en survie.", 422)
            amount = cln_redemption_amount(contract, 1.0)
        else:
            index = int(event.flow_id.removeprefix("credit-coupon-")) - 1
            observation = cln_civil_date(product, contract.coupons[index].survival_time)
            if default is not None and observation >= default.fact.effect_date:
                raise ProductError("EXOTIC_CLN_COUPON_CANCELLED", "Le coupon n’est pas acquis à la date du défaut.", 422)
            amount = cln_coupon_amount(contract, index)
    else:
        raise ProductError("EXOTIC_FACT_DATE_OR_KIND", "Ce fait de crédit ne correspond pas à l’événement choisi.", 422)
    if not isclose(fact.amount_eur, amount, abs_tol=.005, rel_tol=0):
        raise ProductError("EXOTIC_FACT_PAYMENT_AMOUNT", "Le paiement attesté contredit le montant contractuel signé.", 422)


def _decision(session, proposal_id):
    return session.exec(select(NativeExoticLifecycleEntry).where(
        NativeExoticLifecycleEntry.proposal_id == proposal_id,
    )).first()


def _unconfirmed_event(eligible, event_id):
    if any(row.event_id == event_id for row in eligible):
        raise ProductError("EXOTIC_FACT_ALREADY_VALIDATED", "Un fait a déjà été validé pour cet événement. Une correction exige un dispositif dédié.")


def _stage_template_lifecycle(session, deal, product, schedule, actor, entry, now):
    if not isinstance(product.terms, TEMPLATE_TERMS):
        return
    rows = _rows(session, deal, schedule)
    eligible, _ = _as_of(rows, now)
    if deal.status == "actif" and entry.proposal_id is not None and _payload(entry)["decision"] == "validate":
        events = template_event_states(product, json.loads(deal.market_snapshot_json), eligible, now)
        resolution = template_resolution(product, events, eligible, now)
        if resolution:
            outcome, settlement_date, realized_payout = resolution
            deal.status = "échu"
            deal.resolution_outcome = outcome
            deal.realized_payout = realized_payout
            deal.settlement_date = settlement_date.isoformat()
            session.add(deal)
            record_audit_event(session, action="NATIVE_TEMPLATE_LIFECYCLE_RESOLVED", object_type="DEAL",
                               object_id=deal.id, actor_user_id=actor.id, result="SUCCESS",
                               after={"status": deal.status, "outcome": outcome,
                                      "settlement_date": deal.settlement_date, "evidence_fingerprint": entry.entry_hash})
    snapshot = lifecycle_snapshot(session, deal).to_dict()
    snapshot["native_ledger"] = {"entry_id": entry.id, "entry_fingerprint": entry.entry_hash,
                                 "schedule_fingerprint": schedule.fingerprint}
    snapshot["settlement_date"] = deal.settlement_date
    stage_revision(session, product.model_copy(update={"lifecycle": FrozenObject(snapshot)}),
                   expected_revision=product.revision, actor_id=actor.id,
                   action="NATIVE_TEMPLATE_LIFECYCLE_UPDATED", reason="Registre des faits du Deal.")


def _require_template_open(product, deal):
    if isinstance(product.terms, TEMPLATE_TERMS) and deal.status != "actif":
        raise ProductError("NATIVE_FACT_DEAL_CLOSED", "Le Deal est clôturé.")


def propose_exotic_fact(session, deal_id, actor, body: FactProposal) -> FactRow:
    _load_native_deal_scope(session, deal_id, actor)
    _require(actor, session, "operations.prepare")
    lock_command_actor(session, actor)
    deal, product, schedule = _load_native_deal_scope(session, deal_id, actor)
    _require(actor, session, "operations.prepare")
    if (body.expected_contract_version, body.schedule_fingerprint) != (deal.contract_version, schedule.fingerprint):
        raise ProductError("EXOTIC_FACT_SCOPE_STALE", "Le contrat ou l’échéancier a changé. Rechargez le Deal.")
    event = _event(product, schedule, body.event_id, body.fact)
    payload = {**body.model_dump(mode="json", exclude={"command_key", "expected_contract_version", "schedule_fingerprint"}),
               "event_kind": event.kind, "event_date": event.date.isoformat()}
    prior = _prior(session, actor, body.command_key, deal=deal, schedule=schedule, payload=payload)
    if prior is not None:
        return _project(prior, _decision(session, prior.id))
    _require_template_open(product, deal)
    now = _utc(business_now())
    eligible, _ = _as_of(_rows(session, deal, schedule), now)
    _unconfirmed_event(eligible, event.event_id)
    _validate_fact(deal, product, event, body, eligible, now)
    proposal = _append(session, actor, body.command_key, deal=deal, schedule=schedule, payload=payload, now=now)
    record_audit_event(session, action="EXOTIC_FACT_PROPOSED", object_type="DEAL", object_id=deal.id,
                       actor_user_id=actor.id, result="SUCCESS", after={"proposal_id": proposal.id, "event_id": event.event_id,
                                                                      "evidence_fingerprint": proposal.entry_hash})
    _stage_template_lifecycle(session, deal, product, schedule, actor, proposal, now)
    return _project(proposal)


def decide_exotic_fact(session, deal_id, proposal_id, actor, body: FactDecision) -> FactRow:
    _load_native_deal_scope(session, deal_id, actor)
    _require(actor, session, "operations.validate")
    lock_command_actor(session, actor)
    deal, product, schedule = _load_native_deal_scope(session, deal_id, actor)
    _require(actor, session, "operations.validate")
    rows = _rows(session, deal, schedule)
    proposal = next((row for row in rows if row.id == proposal_id and row.proposal_id is None), None)
    if proposal is None:
        raise ProductError("EXOTIC_FACT_NOT_FOUND", "Proposition de fait exotique introuvable.", 404)
    if proposal.actor_id == actor.id:
        raise ProductError("EXOTIC_FACT_FOUR_EYES", "Le proposant et le contrôleur doivent être différents.", 403)
    payload = body.model_dump(mode="json", exclude={"command_key"})
    prior = _prior(session, actor, body.command_key, deal=deal, schedule=schedule, payload=payload, proposal_id=proposal.id)
    if prior is not None:
        return _project(proposal, prior)
    if _decision(session, proposal.id) is not None:
        raise ProductError("EXOTIC_FACT_ALREADY_DECIDED", "La proposition est déjà décidée.")
    now = _utc(business_now())
    if now < _utc(proposal.created_at):
        raise ProductError("EXOTIC_FACT_DECISION_DATE", "La décision ne peut précéder sa proposition.", 422)
    if body.decision == "validate":
        _require_template_open(product, deal)
        eligible, _ = _as_of(rows, now)
        proposed = _project(proposal)
        event = _event(product, schedule, proposed.event_id, proposed.fact)
        _unconfirmed_event(eligible, event.event_id)
        _validate_fact(deal, product, event, proposed, eligible, now)
    decision = _append(session, actor, body.command_key, deal=deal, schedule=schedule, payload=payload, now=now,
                       proposal_id=proposal.id)
    record_audit_event(session, action=f"EXOTIC_FACT_{'VALIDATED' if body.decision == 'validate' else 'REJECTED'}",
                       object_type="DEAL", object_id=deal.id, actor_user_id=actor.id,
                       result="SUCCESS", reason=body.reason, after={"proposal_id": proposal.id, "decision_id": decision.id,
                                                                   "evidence_fingerprint": decision.entry_hash})
    _stage_template_lifecycle(session, deal, product, schedule, actor, decision, now)
    return _project(proposal, decision)
