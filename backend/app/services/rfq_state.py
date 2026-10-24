"""Canonical RFQ facts and projections shared by routes and workflows."""
from __future__ import annotations
import json
from datetime import date, datetime, timezone
from ..runtime import business_now, business_today
from typing import Annotated, Optional
from fastapi import HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlmodel import Session, select
from ..db.models import (
    Deal, Opportunity, RfqRequest, RfqQuote, RfqProvider, RfqProviderContact,
    Counterparty, Entity, ProductRecord, RfqDesk, RfqDeskShare, RfqOwnership, RfqRelationship,
    RfqExchangeRound, RfqRoundLink, User,
)
from ..core.client_controls import (
    ClientRuleError, OPPORTUNITY_TERMINAL, client_provenance_snapshot,
    require_deal_attribution_coherent, require_opportunity_rfq_ready,
)
from ..core.references import next_audited_id, next_reference
from ..core.payoff_families import canonical_payoff_family, normalize_new_payoff_family
from ..core.audit import record_audit_event
from ..core.rfq_controls import (
    contract_calendar_failures, maturity_iso, pricing_input_hash, product_terms, product_terms_hash,
    rfq_readiness_failures,
)
from ..core.schemas import PricingRequest, validate_correlation_matrix
from ..core.payscript.parser import parse_script
from ..core.product.inputs import IDENTITY_FIELDS, TERM_FIELDS, pricing_input, terms_from_input
from ..core.product.models import CommercialContext, FrozenObject, TradeIntent
from ..core.workflow import RfqBusinessStatus, derive_rfq_status, rfq_business_status
from ..services.product_repository import (
    ProductError, load_product, owned_record, stage_internal_product,
    stage_revision, stage_terms,
)
from ..services.rfq_access import (
    RIGHTS, assign_rfq, effective_rights, lock_rfq_organization, membership_rights, ownership, require_create_desk,
    require_rfq_access, visible_rfqs,
)
from ..services import rfq_relationships, rfq_exchange, rfq_publication, rfq_execution
from ..services import rfq_quote_integrity


_TERMINAL_STATUSES = {"clos", "sans_suite"}
_LEGAL_CONTEXT_FIELDS = {
    "transaction_format", "instrument_family", "payoff_family",
    "payoff_description", "documentation_reference",
}


class RfqPricingInput(BaseModel):
    expected_terms_version: int = Field(gt=0)
    valuation_date: Optional[date] = None
    context: Optional[dict] = None


def _utc_iso(dt: datetime | None) -> str | None:
    """Every datetime column in this module is written as datetime.utcnow()
    (naive) or a value explicitly normalized to naive-UTC (see update_quote)
    — SQLite's DATETIME type drops tzinfo silently on write regardless, so a
    value read back is always naive-but-actually-UTC. Re-attach the 'Z' on
    the way out; without it, `new Date(iso)` on the frontend parses the
    string as LOCAL time instead of UTC, silently shifting displayed times
    by the browser's UTC offset (the bug that made 13:05 redisplay as
    11:05 for a UTC+2 user)."""
    if dt is None:
        return None
    return dt.isoformat() + "Z" if dt.tzinfo is None else dt.isoformat()


def _booked_deals_by_rfq(session: Session, user_id: int) -> dict:
    """rfq id → the deal booked out of it. A tender executes once: the UI
    needs this to offer "see the booking" instead of a second "book this
    response" button, and api/deals.py:book_deal refuses the duplicate
    outright."""
    rows = session.exec(
        select(Deal).where(Deal.user_id == user_id, Deal.rfq_id.is_not(None))
    ).all()
    return {d.rfq_id: {"id": d.id, "reference": d.reference} for d in rows}


def _rfq_row(r: RfqRequest, quotes: list | None = None, cpty_map: dict | None = None,
             booked_by_rfq: dict | None = None, session: Session | None = None,
             current: User | None = None) -> dict:
    business_status = rfq_business_status(
        r.status, ready=not rfq_readiness_failures(r))
    if r.status == "retenue" and quotes:
        selected = next((quote for quote in quotes if quote.id == r.selected_quote_id), None)
        if selected and selected.valid_until and selected.valid_until <= business_now():
            business_status = RfqBusinessStatus.EXPIRED.value
    row = {
        "id": r.id,
        "product_id": r.product_id,
        "product_terms_version": r.product_terms_version,
        "reference": r.reference,
        "entity_id": r.entity_id,
        "user_id": r.user_id,
        "name": r.name,
        "ao_date": r.ao_date,
        "kind": r.kind,
        "sens": r.sens,
        "template_type": r.template_type,
        "script_id": r.script_id,
        # Le besoin client à l'origine de l'appel d'offres, quand il y en a un.
        # Exposé pour que l'écran puisse remonter à l'opportunité ; None sur une
        # RFQ créée hors parcours client, ce qui reste le cas courant.
        "opportunity_id": r.opportunity_id,
        "client_id": r.client_id,
        "mandate_id": r.mandate_id,
        "primary_affiliation_id": r.primary_affiliation_id,
        "commercial_context": (json.loads(r.commercial_context_json)
                               if r.commercial_context_json else None),
        "transaction_format": r.transaction_format,
        "instrument_family": r.instrument_family,
        "payoff_family": r.payoff_family,
        "payoff_description": r.payoff_description,
        "documentation_reference": r.documentation_reference,
        "script_snapshot": r.script_snapshot,
        "params": json.loads(r.params_json),
        "model_price": r.model_price,
        "model_price_at": _utc_iso(r.model_price_at),
        "model_input_hash": r.model_input_hash,
        "status": r.status,
        "business_status": business_status,
        "selected_quote_id": r.selected_quote_id,
        "selected_quote_revision": r.selected_quote_revision,
        "selection_reason_code": r.selection_reason_code,
        "selection_reason_note": r.selection_reason_note,
        # {id, reference} of the deal already booked from this tender, or None.
        "booked_deal": (booked_by_rfq or {}).get(r.id),
        "created_at": _utc_iso(r.created_at),
        "updated_at": _utc_iso(r.updated_at),
    }
    if quotes is not None:
        superseded = superseded_quote_ids(quotes)
        row["quotes"] = [
            _quote_row(q, cpty_map, superseded=q.id in superseded, session=session)
            for q in quotes]
    if session is not None:
        exchange_round = rfq_exchange.round_for(session, r.id)
        row["execution_agreements"] = rfq_execution.workspace(session, r.id)
        from .rfq_electronic import requester_workspace
        row['electronic_execution'] = requester_workspace(session, r.id)
        round_link = session.get(RfqRoundLink, r.id)
        row["exchange_round"] = ({"id": exchange_round.id, "number": exchange_round.number,
            "state": exchange_round.state, "exchange_reference": exchange_round.exchange_reference,
            "previous_round_id": exchange_round.previous_round_id} if exchange_round else None)
        row["previous_round_id"] = round_link.previous_round_id if round_link else None
        if row["booked_deal"] is None:
            deal = session.exec(select(Deal).where(Deal.rfq_id == r.id)).first()
            if deal is not None:
                row["booked_deal"] = {"id": deal.id, "reference": deal.reference}
        scope = ownership(session, r.id)
        if scope is not None:
            desk = session.get(RfqDesk, scope.pilot_desk_id)
            entity = session.get(Entity, scope.entity_id)
            responsible = session.get(User, scope.responsible_user_id) if scope.responsible_user_id else None
            creator = session.get(User, r.user_id)
            row.update({"pilot_desk_id": scope.pilot_desk_id,
                        "pilot_desk_name": desk.name if desk else None,
                        "organization_name": entity.name if entity else None,
                        "responsible_user_id": scope.responsible_user_id,
                        "responsible_user_name": responsible.username if responsible else None,
                        "creator_name": creator.username if creator else None,
                        "access_rights": sorted(effective_rights(session, r, current)) if current else []})
            if current is not None and "read" not in membership_rights(
                    session, scope.pilot_desk_id, current):
                row["commercial_context"] = None
                for field in ("client_id", "mandate_id", "opportunity_id", "primary_affiliation_id"):
                    row[field] = None
    if current is not None and "price" not in effective_rights(session, r, current):
        private_params = row["params"]
        contractual = {"T", "notional", "currency", "strike_date", "value_date",
                       "maturity_date", "payment_date", "user_params", "constats",
                       "frozen_schedule", "date_conventions"}
        row["params"] = {key: value for key, value in private_params.items()
                         if key in contractual}
        row["params"]["underlyings"] = [
            {key: value for key, value in underlying.items()
             if key in IDENTITY_FIELDS}
            for underlying in private_params.get("underlyings", [])]
        row["model_price"] = None
        row["model_price_at"] = None
        row["model_input_hash"] = None
    return row


def _sync_product_rfq(
    session: Session,
    rfq: RfqRequest,
    current: User,
    *,
    action: str,
    product=None,
    update_context: bool = False,
):
    """Replace the RFQ projection and its business context in one revision."""
    if rfq.product_id is None or rfq.product_terms_version is None:
        raise HTTPException(409, detail={
            "code": "RFQ_PRODUCT_MISSING",
            "message": "Cette RFQ ne possède pas de Product canonique.",
        })
    latest = load_product(session, rfq.product_id)
    if product is not None and product.revision != latest.revision:
        raise HTTPException(409, detail={'code': 'PRODUCT_REVISION_STALE',
                                        'message': 'Le Product a changé ; rechargez le dossier.'})
    # A candidate may contain freshly appended terms, but a historical read is
    # only a projection source. It must never replace the current dossier.
    if product is None or product.terms_version <= latest.terms_version:
        product = latest
    snapshot = FrozenObject(_rfq_row(
        rfq, _get_quotes(rfq.id, session), _counterparty_by_provider(session),
        _booked_deals_by_rfq(session, current.id), session=session))
    rfqs = [item for item in product.rfqs if item.to_dict().get('id') != rfq.id]
    changes = {'rfqs': (*rfqs, snapshot)}
    if update_context:
        if product.execution:
            raise HTTPException(409, 'Le contexte booké exige une rectification gouvernée.')
        if rfq.product_terms_version != product.terms_version:
            raise HTTPException(409, 'Une RFQ historique ne peut pas modifier le contexte courant du Product.')
        changes.update({
            'commercial': CommercialContext(client_id=rfq.client_id, mandate_id=rfq.mandate_id,
                opportunity_id=rfq.opportunity_id, primary_affiliation_id=rfq.primary_affiliation_id),
            'intent': TradeIntent(**{**product.intent.model_dump(mode='json'),
                'nominal': json.loads(rfq.params_json or '{}').get('notional', product.intent.nominal),
                'side': 'BUY' if rfq.sens == 'achat' else 'SELL',
                'product_type': rfq.template_type or product.intent.product_type,
                **{field: getattr(rfq, field) or '' for field in _LEGAL_CONTEXT_FIELDS}}),
        })
    try:
        stage_revision(session, product.model_copy(update=changes), expected_revision=product.revision,
            actor_id=current.id, action=action,
            reason=f'Synchronisation de {rfq.reference} dans le Product.')
    except ProductError as exc:
        raise HTTPException(exc.status, detail={'code': exc.code, 'message': str(exc)}) from exc


def _counterparty_by_provider(session: Session) -> dict:
    """Provider label → the eligible counterparty a deal booked out of that
    provider's quote actually faces. Two admin catalogs with no relation used
    to leave the booking prefill writing an RfqProvider label straight into a
    <select> fed by Counterparty: when the labels diverged ("Vontobel
    (deritrade)" vs "Vontobel"), the select showed empty, validate() still
    passed on the non-empty value, and the deal booked against a counterparty
    absent from the catalog and invisible on screen.

    Resolution order: the explicit link (RfqProvider.counterparty_id) first,
    then an exact name match for the many providers that ARE their own
    counterparty. Inactive counterparties are excluded — the booking form only
    offers active ones, so proposing one would recreate the same mismatch."""
    active = {c.name: c for c in session.exec(
        select(Counterparty).where(Counterparty.active == True)  # noqa: E712
    ).all()}
    by_id = {c.id: c for c in active.values()}
    mapping = {}
    for p in session.exec(select(RfqProvider)).all():
        linked = by_id.get(p.counterparty_id) if p.counterparty_id else None
        if linked and p.active:
            mapping[p.label] = linked.name
        elif p.counterparty_id is None and p.active and p.label in active:
            mapping[p.label] = p.label
    return mapping


def _quote_row(q: RfqQuote, cpty_map: dict | None = None, *,
               superseded: bool = False, session: Session | None = None) -> dict:
    comparable = (
        not superseded and q.price is not None and q.status == 'recu'
        and (q.valid_until is None or q.valid_until > business_now())
    )
    row = {
        "id": q.id,
        "revision": q.revision,
        "rfq_id": q.rfq_id,
        "provider": q.provider,
        # None = no eligible counterparty could be resolved; the booking
        # prefill must then leave the field empty rather than inject a value
        # the <select> can't display (see DealTab.vue).
        "provider_id": q.provider_id,
        "counterparty_id": q.counterparty_id if q.identity_frozen else None,
        "counterparty": q.counterparty_name if q.identity_frozen else None,
        "identity_status": "FROZEN" if q.identity_frozen and q.counterparty_id else "TO_QUALIFY",
        "contact": q.contact,
        "price": q.price,
        "currency": q.currency,
        "status": q.status,
        "note": q.note,
        "quoted_at": _utc_iso(q.quoted_at),
        "firmness": q.firmness,
        "valid_until": _utc_iso(q.valid_until),
        "created_at": _utc_iso(q.created_at),
        "last_look": q.last_look,
        "parent_quote_id": q.parent_quote_id,
        "superseded": superseded,
        "comparable": comparable,
    }
    if session is not None:
        from ..services.rfq_quote_integrity import same_currency, effective_currency
        rfq = session.get(RfqRequest, q.rfq_id)
        compatible_currency = same_currency(session, rfq, q)
        exchange_round = rfq_exchange.round_for(session, rfq.id)
        round_open = rfq.status not in _TERMINAL_STATUSES and (not exchange_round or exchange_round.state == 'OPEN')
        row.update(currency=effective_currency(session, rfq, q),
                   currency_matches=compatible_currency,
                   comparable=comparable and compatible_currency and round_open)
        comparable = row['comparable']
        publication = rfq_publication.publication_for_quote(session, q.id)
        if publication:
            public = rfq_publication.public_row(session, publication)
            row.update(origin="NETWORK", publication=public,
                counterparty=public["response"]["counterparty_name"],
                comparable=comparable and public["state"] == "ACTIVE"
                    and public["response"]["conditions_type"] == "NONE")
            from ..services.legal_identity import network_counterparty
            try:
                legal = network_counterparty(session, session.get(RfqRequest, q.rfq_id), publication)
                row.update(counterparty_id=legal.id, counterparty=legal.name, identity_status="LOCAL_MAPPING")
            except HTTPException:
                row.update(counterparty_id=None, counterparty=None, identity_status="TO_QUALIFY")
        row['history_eligible'] = (not superseded and q.price is not None and q.status == 'recu'
            and compatible_currency and (not publication or (public['response']['conditions_type'] == 'NONE'
                and public['state'] in {'ACTIVE', 'EXPIRED', 'RESERVED', 'ROUND_CLOSED', 'PENDING_DELIVERY'})))
    return row


def _get_quotes(rfq_id: int, session: Session) -> list:
    """Top-level quotes (one per solicited provider) ordered by actual
    response time — quoted_at when known, oldest first, unanswered quotes
    pushed to the end rather than jumbled in with answered ones by
    created_at (the previous behavior: sorted by created_at alone, so
    editing a quote's response time never moved it in the list at all).
    A last-look counter-quote (parent_quote_id set) is always placed
    directly under its parent regardless of its own time, since it's a
    continuation of that same provider's response, not a separate slot in
    the competitive timeline."""
    rows = session.exec(select(RfqQuote).where(RfqQuote.rfq_id == rfq_id)).all()
    children_by_parent: dict[int, list] = {}
    parents = []
    for q in rows:
        if q.parent_quote_id is not None:
            children_by_parent.setdefault(q.parent_quote_id, []).append(q)
        else:
            parents.append(q)
    parents.sort(key=lambda q: (q.quoted_at is None, q.quoted_at or q.created_at))
    ordered = []
    seen: set[int] = set()

    def append_tree(q):
        if q.id in seen:
            return
        seen.add(q.id)
        ordered.append(q)
        for child in sorted(children_by_parent.get(q.id, []), key=lambda x: x.created_at):
            append_tree(child)

    for p in parents:
        append_tree(p)
    # Historical malformed/orphan chains must remain visible to the desk even
    # though new nested last looks are now refused.
    for q in sorted(rows, key=lambda x: x.created_at):
        append_tree(q)
    return ordered


def _derive_status(rfq: RfqRequest, quotes: list) -> str:
    """The tender's stage, read off the facts rather than trusted from the
    caller: a provider solicited makes it "envoyée", a first price received
    "cotée", a retained response "retenue". Left to the caller (the historic
    behaviour), "envoye"/"quote" were never posed by anything and an RFQ with
    five prices in hand still displayed "Brouillon" until it jumped straight
    to "Retenue".

    Manual provider rows remain facts of solicitation. Network rounds are
    accounted for by _sync_status, independently of received prices."""
    return derive_rfq_status(rfq.status, rfq.selected_quote_id, quotes)


def _sync_status(rfq: RfqRequest, session: Session) -> None:
    """Recompute after any mutation that can move the tender: a quote added,
    priced, unpriced or deleted, a response retained or un-retained. Also
    closes the hole that left a de-selected RFQ displaying "Retenue" with
    nothing retained."""
    new_status = _derive_status(rfq, _get_quotes(rfq.id, session))
    if new_status == "draft" and rfq_exchange.round_for(session, rfq.id):
        new_status = "envoye"
    if new_status != rfq.status:
        rfq.status = new_status
        session.add(rfq)


def superseded_quote_ids(quotes: list) -> set:
    """Ids of the quotes a last look has replaced — a parent whose counter-quote
    came back with a price. Both rows stay on screen (the original response is
    part of the record), but only ONE of them is that provider's answer to the
    tender: counting both puts the same bank in twice and drags every spread
    statistic toward its improved price. A last look still awaiting an answer
    supersedes nothing — the original is still the live response."""
    return {
        q.parent_quote_id for q in quotes
        if q.parent_quote_id is not None and q.price is not None and q.status == 'recu'
    }


def _get_owned(rfq_id: int, current: User, session: Session,
               right: str = "read") -> RfqRequest:
    return require_rfq_access(session, rfq_id, current, right)


def _rfq_product(rfq: RfqRequest, expected_version: int, current: User, session: Session):
    if not rfq.product_id or not rfq.product_terms_version:
        raise HTTPException(409, detail={"code": "RFQ_PRODUCT_MISSING", "message": "Cette RFQ ne possède pas de version Product exploitable."})
    if rfq.product_terms_version != expected_version:
        raise HTTPException(409, detail={"code": "RFQ_TERMS_STALE", "message": "Les termes de la RFQ ont changé. Rechargez le dossier."})
    try:
        scope = ownership(session, rfq.id)
        if scope is None:
            owned_record(session, rfq.product_id, current)
        else:
            product_row = session.get(ProductRecord, rfq.product_id)
            if product_row is None or product_row.entity_id != scope.entity_id:
                raise HTTPException(404, "Produit introuvable dans cette organisation")
        return load_product(session, rfq.product_id, terms_version=rfq.product_terms_version)
    except ProductError as exc:
        raise HTTPException(exc.status, detail={"code": exc.code, "message": str(exc)}) from exc


def compose_rfq_pricing_input(rfq_id, body: RfqPricingInput, current, session):
    """Compose the linked terms with the RFQ's persisted private assumptions."""
    rfq = _get_owned(rfq_id, current, session, "price")
    product = _rfq_product(rfq, body.expected_terms_version, current, session)
    params = json.loads(rfq.params_json or "{}")
    valuation_date = params.get("valuation_date") or business_today().isoformat()
    if body.context is None and body.valuation_date and body.valuation_date.isoformat() != valuation_date:
        raise HTTPException(409, detail={"code": "RFQ_PRICING_DATE_STALE", "message": "La date de calcul diffère des hypothèses enregistrées. Enregistrez les hypothèses RFQ avant le calcul."})
    context = {key: value for key, value in params.items()
               if key in PricingRequest.model_fields and key not in TERM_FIELDS}
    context["underlyings"] = [
        {key: value for key, value in item.items() if key not in IDENTITY_FIELDS}
        for item in params.get("underlyings", [])
    ]
    count = len(product.terms.underlyings)
    if count == 1:
        context.setdefault("corr_matrix", [[1.0]])
    if body.context is not None:
        # Pricer analyses keep their own market context without changing RFQ.
        context = body.context
        valuation_date = context.get("valuation_date") or valuation_date
    try:
        request = PricingRequest(**pricing_input(product, context)).model_dump(mode="json")
    except ValueError as exc:
        raise HTTPException(422, detail=str(exc)) from exc
    return {
        "pricing_input": {**request, "valuation_date": valuation_date},
        "input_hash": pricing_input_hash(rfq.script_snapshot, params) if body.context is None else None,
        "product_id": product.product_id,
        "terms_version": product.terms_version,
        "terms_fingerprint": product.terms_fingerprint,
    }


