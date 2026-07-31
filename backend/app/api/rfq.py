"""RFQ (request-for-quote) tracker: collect and compare bank quotes for a
structured product against Structura's own model price."""
from __future__ import annotations
import json
from datetime import date, datetime, timezone
from typing import Annotated, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, select
from ..db.database import get_session
from ..db.models import RfqRequest, RfqQuote, RfqProvider, Counterparty, Deal, User
from ..core.references import next_reference
from ..core.audit import record_audit_event
from ..core.rfq_controls import (
    pricing_input_hash, product_terms, product_terms_hash,
    rfq_readiness_failures,
)
from ..core.payscript.parser import parse_script
from ..core.workflow import RfqBusinessStatus, rfq_business_status
from .auth import get_current_user

router = APIRouter(prefix="/api/rfq", tags=["rfq"])


# ── Pydantic schemas ──────────────────────────────────────────────────

class RfqCreate(BaseModel):
    name: str
    ao_date: Optional[str] = None  # ISO date; defaults to today if omitted
    # Contraints par motif, et pas seulement documentés : _edge_bps teste
    # `sens == "achat"` et retombe SINON sur la branche vente, donc un sens
    # mal orthographié inversait silencieusement la lecture de tous les écarts,
    # la meilleure réponse et la coloration de l'écran. Un kind invalide
    # contournait au passage le contrôle « to trade exige un calendrier ».
    kind: str = Field(default="indicatif", pattern="^(indicatif|to_trade)$")
    sens: str = Field(default="achat", pattern="^(achat|vente)$")
    template_type: str = ""
    script_id: Optional[int] = None
    script_snapshot: str
    params: dict = {}


class RfqUpdate(BaseModel):
    name: Optional[str] = None
    ao_date: Optional[str] = None
    sens: Optional[str] = Field(default=None, pattern="^(achat|vente)$")
    params: Optional[dict] = None
    status: Optional[str] = None
    model_price: Optional[float] = None
    selected_quote_id: Optional[int] = None


class QuoteCreate(BaseModel):
    provider: str = Field(default="manuel", min_length=1)
    contact: Optional[str] = None
    note: Optional[str] = None


class QuoteUpdate(BaseModel):
    price: Optional[float] = None
    currency: Optional[str] = None
    status: Optional[str] = Field(
        default=None, pattern="^(en_attente|recu|decline|expire)$")
    note: Optional[str] = None
    quoted_at: Optional[str] = None  # ISO datetime string
    firmness: Optional[str] = Field(
        default=None, pattern="^(UNKNOWN|INDICATIVE|FIRM)$")
    valid_until: Optional[str] = None
    last_look: Optional[bool] = None


# ── Helpers ───────────────────────────────────────────────────────────

def _gen_ref(session: Session) -> str:
    return next_reference(session, RfqRequest, f"RFQ-{date.today().strftime('%Y%m%d')}-")


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


def _parse_utc_datetime(raw, field_name: str) -> datetime | None:
    if raw is None or raw == "":
        return None
    if isinstance(raw, datetime):
        parsed = raw
    else:
        try:
            parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            raise HTTPException(422, f"{field_name} doit être une date-heure ISO valide.")
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _edge_bps(price: float | None, model: float | None, sens: str) -> float | None:
    """Quote quality from our own side, in bps — positive is always in our
    favour, whichever way we trade. Buying, the good response is the one BELOW
    our model price; selling, the one above. The raw (price − model) spread
    can't be compared or averaged across both directions: a good purchase and
    a good sale carry opposite signs and cancel out (see RfqAnalysisView.vue,
    which ranks providers on this)."""
    if price is None or not model:
        return None
    diff = (model - price) if sens == "achat" else (price - model)
    return round(diff / model * 10000, 1)


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
             booked_by_rfq: dict | None = None) -> dict:
    business_status = rfq_business_status(
        r.status, ready=not rfq_readiness_failures(r))
    if r.status == "retenue" and quotes:
        selected = next((quote for quote in quotes if quote.id == r.selected_quote_id), None)
        if selected and selected.valid_until and selected.valid_until <= datetime.utcnow():
            business_status = RfqBusinessStatus.EXPIRED.value
    row = {
        "id": r.id,
        "reference": r.reference,
        "entity_id": r.entity_id,
        "user_id": r.user_id,
        "name": r.name,
        "ao_date": r.ao_date,
        "kind": r.kind,
        "sens": r.sens,
        "template_type": r.template_type,
        "script_id": r.script_id,
        "script_snapshot": r.script_snapshot,
        "params": json.loads(r.params_json),
        "model_price": r.model_price,
        "model_price_at": _utc_iso(r.model_price_at),
        "status": r.status,
        "business_status": business_status,
        "selected_quote_id": r.selected_quote_id,
        # {id, reference} of the deal already booked from this tender, or None.
        "booked_deal": (booked_by_rfq or {}).get(r.id),
        "created_at": _utc_iso(r.created_at),
        "updated_at": _utc_iso(r.updated_at),
    }
    if quotes is not None:
        row["quotes"] = [_quote_row(q, cpty_map) for q in quotes]
    return row


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
        if linked:
            mapping[p.label] = linked.name
        elif p.label in active:
            mapping[p.label] = p.label
    return mapping


def _quote_row(q: RfqQuote, cpty_map: dict | None = None) -> dict:
    return {
        "id": q.id,
        "rfq_id": q.rfq_id,
        "provider": q.provider,
        # None = no eligible counterparty could be resolved; the booking
        # prefill must then leave the field empty rather than inject a value
        # the <select> can't display (see DealTab.vue).
        "counterparty": (cpty_map or {}).get(q.provider),
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
    }


def _rfq_audit_state(rfq: RfqRequest) -> dict:
    return {
        "reference": rfq.reference,
        "kind": rfq.kind,
        "status": rfq.status,
        "selected_quote_id": rfq.selected_quote_id,
        "model_price": rfq.model_price,
        "model_price_at": _utc_iso(rfq.model_price_at),
        "model_input_hash": rfq.model_input_hash,
    }


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


# Statuses the desk poses by hand; everything else is deduced from what has
# actually happened to the tender. "clos" is posed by api/deals.py:book_deal,
# "sans_suite" by the user (an AO that led nowhere — the majority of them, and
# the denominator of any hit-ratio statistic). Both are terminal: a booked or
# abandoned tender never falls back to an earlier stage on its own.
_TERMINAL_STATUSES = {"clos", "sans_suite"}
# The only status a PATCH may pose directly, plus the sentinel that hands the
# RFQ back to the derivation.
_SETTABLE_STATUSES = {"sans_suite", "auto"}


def _derive_status(rfq: RfqRequest, quotes: list) -> str:
    """The tender's stage, read off the facts rather than trusted from the
    caller: a provider solicited makes it "envoyée", a first price received
    "cotée", a retained response "retenue". Left to the caller (the historic
    behaviour), "envoye"/"quote" were never posed by anything and an RFQ with
    five prices in hand still displayed "Brouillon" until it jumped straight
    to "Retenue".

    Note the app has no explicit "send the tender" action: adding a provider
    IS the act of soliciting it, so that's what "envoyée" keys off."""
    if rfq.status in _TERMINAL_STATUSES:
        return rfq.status
    if rfq.selected_quote_id is not None:
        return "retenue"
    if any(q.price is not None for q in quotes):
        return "quote"
    if quotes:
        return "envoye"
    return "draft"


def _sync_status(rfq: RfqRequest, session: Session) -> None:
    """Recompute after any mutation that can move the tender: a quote added,
    priced, unpriced or deleted, a response retained or un-retained. Also
    closes the hole that left a de-selected RFQ displaying "Retenue" with
    nothing retained."""
    new_status = _derive_status(rfq, _get_quotes(rfq.id, session))
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
        if q.parent_quote_id is not None and q.price is not None
    }


# Une cotation est un pourcentage du nominal. La borne haute n'est pas une
# limite de marché — c'est un filet à faute de frappe : 9850 saisi pour 98,50,
# ou un montant en devise tapé dans un champ en %.
_QUOTE_PRICE_MAX = 1000.0


def _validate_quote_price(price: float | None) -> None:
    if price is None:
        return
    if price <= 0:
        raise HTTPException(
            422, f"Un prix de cotation est un pourcentage du nominal, il ne peut pas être "
                 f"nul ou négatif (reçu : {price}). Pour un fournisseur qui ne répond pas, "
                 f"laissez le prix vide et passez son statut à « Décliné ».")
    if price > _QUOTE_PRICE_MAX:
        raise HTTPException(
            422, f"Prix de cotation invraisemblable : {price} % du nominal. Les cotations se "
                 f"saisissent en points de pourcentage (98,50 et non 9850).")


def _improves(new_price: float, old_price: float, sens: str) -> bool:
    """Un last look, c'est « s'aligner ou garder son prix ». Une contre-cote
    doit donc améliorer, ou au pire égaler, la cotation d'origine — dans le
    sens de l'AO : on achète, le mieux est plus bas ; on vend, plus haut."""
    return new_price <= old_price if sens == "achat" else new_price >= old_price


def _refuse_if_booked(rfq: RfqRequest, session: Session, what: str) -> None:
    """Once a trade has come out of a tender, the tender IS the evidence for
    it: who was put in competition, at what prices, and why this one won.
    Leaving it editable made that evidence worthless — every one of these was
    accepted on a booked RFQ before this guard: un-retaining the winning
    quote (the hit ratio then credits nobody), deleting it, rewriting its
    price to anything, flipping the RFQ's side (every edge changes sign), or
    reclassifying the tender as "sans suite" when it demonstrably traded.

    Deal.rfq_provenance_json freezes the same picture on the deal, but the
    counterparty analysis reads the live RFQ — so the number the desk uses to
    decide who to put in competition tomorrow was rewritable after the fact.

    Cosmetic fields (name, ao_date, notes) stay editable: they document, they
    don't evidence."""
    if rfq.status != "clos":
        return
    deal = session.exec(select(Deal).where(Deal.rfq_id == rfq.id)).first()
    ref = f" (deal {deal.reference})" if deal else ""
    raise HTTPException(
        409, f"AO déjà booké{ref} — {what} ferait partie de la piste de best execution "
             f"de ce trade et ne peut plus être modifié.")


def _get_owned(rfq_id: int, current: User, session: Session) -> RfqRequest:
    r = session.get(RfqRequest, rfq_id)
    if not r or r.user_id != current.id:
        raise HTTPException(404, "RFQ introuvable")
    return r


# ── Endpoints ─────────────────────────────────────────────────────────

@router.get("/providers")
def list_providers(
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    providers = session.exec(
        select(RfqProvider).where(RfqProvider.active == True)  # noqa: E712
        .order_by(RfqProvider.label)
    ).all()
    return [{"id": p.id, "label": p.label, "mode": p.mode} for p in providers]


def _is_expert_script(script_text: str) -> bool:
    """A to-trade script must parse a real CONSTAT declaration and use it.

    Looking for the substring ``CONSTAT`` accepted comments and dead metadata;
    the parser's own declarations/references are the authoritative contract.
    """
    try:
        compiled = parse_script(script_text)
    except ValueError:
        return False
    declared = {c.name for c in compiled.constats}
    return bool(declared and any(
        ev.constat_ref in declared for ev in compiled.events if ev.constat_ref))


@router.post("", status_code=201)
def create_rfq(
    body: RfqCreate,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    if body.kind == "to_trade" and not _is_expert_script(body.script_snapshot):
        raise HTTPException(
            422, "Une RFQ 'to trade' doit utiliser un script en mode Expert (calendrier "
                 "CONSTAT réel) pour la précision requise — sauvegardez-le dans le Pricer, "
                 "ou repartez du script d'un deal déjà booké en mode Expert.")

    reference = _gen_ref(session)
    rfq = RfqRequest(
        reference=reference,
        entity_id=current.entity_id,
        user_id=current.id,
        name=body.name.strip(),
        ao_date=body.ao_date or date.today().isoformat(),
        kind=body.kind,
        sens=body.sens,
        template_type=body.template_type,
        script_id=body.script_id,
        script_snapshot=body.script_snapshot,
        params_json=json.dumps(body.params),
    )
    session.add(rfq)
    session.flush()
    record_audit_event(
        session,
        action="RFQ_CREATED",
        object_type="RFQ",
        object_id=rfq.id,
        actor_user_id=current.id,
        result="SUCCESS",
        after=_rfq_audit_state(rfq),
        reason="Création de la demande de prix.",
    )
    session.commit()
    session.refresh(rfq)
    return _rfq_row(rfq, [])


@router.get("")
def list_rfqs(
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    rfqs = session.exec(
        select(RfqRequest).where(RfqRequest.user_id == current.id)
        .order_by(RfqRequest.created_at.desc())
    ).all()
    booked = _booked_deals_by_rfq(session, current.id)
    quotes_by_rfq: dict[int, list[RfqQuote]] = {}
    if rfqs:
        for quote in session.exec(select(RfqQuote).where(
                RfqQuote.rfq_id.in_([rfq.id for rfq in rfqs]))).all():
            quotes_by_rfq.setdefault(quote.rfq_id, []).append(quote)
    return [_rfq_row(r, quotes_by_rfq.get(r.id, []), booked_by_rfq=booked)
            for r in rfqs]


@router.get("/history")
def rfq_history(
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    """Flat list of priced quotes joined with their RFQ, for the counterparty
    analysis view. No server-side aggregation — volumes are small, the
    frontend filters/groups by provider and product type. It does need to be
    told which rows are a provider's FINAL answer and which tender each row
    won, though: neither is derivable from a quote in isolation."""
    rows = session.exec(
        select(RfqQuote, RfqRequest)
        .join(RfqRequest, RfqQuote.rfq_id == RfqRequest.id)
        .where(RfqRequest.user_id == current.id)
        .where(RfqQuote.price.is_not(None))
    ).all()
    # Superseded parents are computed over ALL quotes, not just the priced
    # ones above: a last look answers with a price, so it is always in the
    # filtered set, but that is not something to rely on silently.
    superseded = superseded_quote_ids(session.exec(
        select(RfqQuote).join(RfqRequest, RfqQuote.rfq_id == RfqRequest.id)
        .where(RfqRequest.user_id == current.id)
    ).all())
    return [
        {
            "quote_id": q.id,
            "rfq_id": rfq.id,
            "reference": rfq.reference,
            "template_type": rfq.template_type,
            "provider": q.provider,
            "price": q.price,
            "model_price": rfq.model_price,
            "sens": rfq.sens,
            # Raw signed price difference, kept as the factual number; edge_bps
            # is the one to aggregate on (see _edge_bps).
            "spread_bps": round((q.price - rfq.model_price) / rfq.model_price * 10000, 1)
                          if rfq.model_price else None,
            "edge_bps": _edge_bps(q.price, rfq.model_price, rfq.sens),
            "date": _utc_iso(q.quoted_at or q.created_at),
            "status": q.status,
            # This row is a last-look counter-quote…
            "is_last_look": q.parent_quote_id is not None,
            # …and this one is the original it replaced. Superseded rows are
            # kept (the initial response is part of the record) but must be
            # left out of any per-provider statistic.
            "superseded": q.id in superseded,
            # Won the tender: retained AND actually traded. "Retenue" alone
            # isn't a win — the deal can still fall through, which is exactly
            # what the "sans suite" status records.
            "won": rfq.selected_quote_id == q.id and rfq.status == "clos",
            # Whether the tender was decided at all: a hit ratio computed over
            # AOs still in progress would punish whoever quotes on live ones.
            "rfq_status": rfq.status,
        }
        for q, rfq in rows
    ]


@router.get("/{rfq_id}")
def get_rfq(
    rfq_id: int,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    rfq = _get_owned(rfq_id, current, session)
    return _rfq_row(rfq, _get_quotes(rfq_id, session), _counterparty_by_provider(session),
                    _booked_deals_by_rfq(session, current.id))


@router.patch("/{rfq_id}")
def update_rfq(
    rfq_id: int,
    body: RfqUpdate,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    rfq = _get_owned(rfq_id, current, session)
    before_audit = _rfq_audit_state(rfq)
    data = body.model_dump(exclude_unset=True)
    requested_fields = set(data)
    if "params" in data:
        _refuse_if_booked(rfq, session, "les termes et paramètres de l'AO")
        new_params = data.pop("params") or {}
        existing_terms = product_terms(rfq.script_snapshot, json.loads(rfq.params_json))
        new_terms = product_terms(rfq.script_snapshot, new_params)
        if _get_quotes(rfq_id, session) and new_terms != existing_terms:
            changed = sorted(k for k in set(existing_terms) | set(new_terms)
                             if existing_terms.get(k) != new_terms.get(k))
            raise HTTPException(
                409, "Les termes contractuels d'une RFQ sont figés dès qu'un fournisseur "
                     "est sollicité. Créez une nouvelle RFQ pour modifier : "
                     + ", ".join(changed) + ".")
        # Non-contractual model inputs (rates, vols, model, path count) may be
        # refreshed while quotes are live; the product identity above may not.
        new_pricing_hash = pricing_input_hash(rfq.script_snapshot, new_params)
        if rfq.model_price is not None and rfq.model_input_hash != new_pricing_hash:
            # A scalar price cannot survive an input change.  The next explicit
            # model pricing will write a fresh hash and timestamp.
            rfq.model_price = None
            rfq.model_price_at = None
            rfq.model_input_hash = None
        rfq.params_json = json.dumps(new_params)
    if "model_price" in data:
        _refuse_if_booked(rfq, session, "le prix modèle")
        mp = data.pop("model_price")
        if mp is not None and mp < 0:
            raise HTTPException(
                422, f"Un prix modèle négatif ({mp}) n'est pas un prix de produit — tous les "
                     f"écarts aux cotations en découlent.")
        rfq.model_price = mp
        rfq.model_price_at = datetime.utcnow()
        rfq.model_input_hash = (
            pricing_input_hash(rfq.script_snapshot, json.loads(rfq.params_json or "{}"))
            if mp is not None else None)
    if data.get("sens") is not None and data["sens"] != rfq.sens:
        _refuse_if_booked(rfq, session, "le sens de l'AO")
        if _get_quotes(rfq_id, session):
            raise HTTPException(
                409, "Le sens d'une RFQ est figé dès qu'un fournisseur est sollicité. "
                     "Créez une nouvelle RFQ pour inverser le sens du trade.")
    if "selected_quote_id" in data:
        _refuse_if_booked(rfq, session, "la réponse retenue")
        qid = data.pop("selected_quote_id")
        if qid is not None:
            q = session.get(RfqQuote, qid)
            if not q or q.rfq_id != rfq_id:
                raise HTTPException(404, "Quote introuvable pour cette RFQ")
            if q.price is None:
                raise HTTPException(
                    422, "Une réponse sans prix ne peut pas être retenue. Saisissez la "
                         "cotation finale ou marquez le fournisseur comme décliné.")
            if q.status in {"decline", "expire"}:
                raise HTTPException(
                    422, f"Une réponse au statut « {q.status} » ne peut pas être retenue.")
            quotes = _get_quotes(rfq_id, session)
            if q.id in superseded_quote_ids(quotes):
                raise HTTPException(
                    422, "Cette cotation a été remplacée par son last look : retenez la "
                         "contre-cotation finale.")
        rfq.selected_quote_id = qid
    if "status" in data:
        _refuse_if_booked(rfq, session, "le statut")
        want = data.pop("status")
        if want not in _SETTABLE_STATUSES:
            raise HTTPException(
                422, "Le statut se déduit du déroulé de l'AO — seul « sans_suite » se pose "
                     "à la main, « auto » le rend à la déduction.")
        # "auto" reopens by clearing the terminal flag; _sync_status then
        # puts the tender back at the stage its quotes actually justify.
        rfq.status = "sans_suite" if want == "sans_suite" else "draft"
    for field, value in data.items():
        if value is not None:
            setattr(rfq, field, value)
    _sync_status(rfq, session)
    rfq.updated_at = datetime.utcnow()
    session.add(rfq)
    critical = requested_fields & {"params", "model_price", "selected_quote_id", "status"}
    if critical:
        if "selected_quote_id" in requested_fields:
            action = "QUOTE_SELECTED" if rfq.selected_quote_id else "QUOTE_DESELECTED"
        elif "model_price" in requested_fields:
            action = "MODEL_PRICE_RECORDED"
        elif "params" in requested_fields:
            action = "RFQ_INPUTS_UPDATED"
        else:
            action = "RFQ_STATUS_CHANGED"
        record_audit_event(
            session,
            action=action,
            object_type="RFQ",
            object_id=rfq.id,
            actor_user_id=current.id,
            result="SUCCESS",
            before=before_audit,
            after=_rfq_audit_state(rfq),
            reason="Transition RFQ explicite.",
        )
    session.commit()
    return _rfq_row(rfq, _get_quotes(rfq_id, session), _counterparty_by_provider(session),
                    _booked_deals_by_rfq(session, current.id))


@router.delete("/{rfq_id}", status_code=204)
def delete_rfq(
    rfq_id: int,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    rfq = _get_owned(rfq_id, current, session)
    # The tender a trade came out of is a best-execution record: which banks
    # were put in competition, at what prices, and why this one won. Once a
    # deal points at it, that trail must survive — deleting the RFQ would
    # leave deal.rfq_id dangling and the justification gone. Same blocker
    # spirit as deals ↔ KID/EMT in core/admin_registry.py.
    booked = session.exec(select(Deal).where(Deal.rfq_id == rfq_id)).first()
    if booked:
        raise HTTPException(
            409, f"Suppression impossible : le deal {booked.reference} a été booké depuis "
                 f"cette RFQ, qui documente sa best execution.")
    for q in _get_quotes(rfq_id, session):
        session.delete(q)
    session.delete(rfq)
    session.commit()


@router.post("/{rfq_id}/quotes", status_code=201)
def add_quote(
    rfq_id: int,
    body: QuoteCreate,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    rfq = _get_owned(rfq_id, current, session)
    _refuse_if_booked(rfq, session, "l'ajout d'un fournisseur")
    if rfq.kind == "to_trade":
        readiness = rfq_readiness_failures(rfq)
        if readiness:
            raise HTTPException(422, {
                "code": "RFQ_NOT_READY",
                "message": "La RFQ to-trade doit être complète avant sollicitation.",
                "failures": [failure.as_dict() for failure in readiness],
            })
    # Un fournisseur = une ligne = une réponse. Deux lignes pour la même banque
    # la font peser double dans l'écart moyen et le hit ratio, et rendent le
    # last look ambigu (quelle ligne la contre-cote remplace-t-elle ?). Le
    # last look, lui, crée son enfant sans passer par ici.
    provider = body.provider.strip()
    if not provider:
        raise HTTPException(422, "Le fournisseur est obligatoire.")
    provider_key = provider.casefold()
    already = next((q for q in _get_quotes(rfq_id, session)
                    if q.parent_quote_id is None and q.provider.strip().casefold() == provider_key), None)
    if already:
        raise HTTPException(
            409, f"« {body.provider} » est déjà sollicité sur cet AO. Saisissez son prix sur "
                 f"la ligne existante, ou utilisez le last look pour enregistrer une seconde "
                 f"cotation de sa part.")
    q = RfqQuote(
        rfq_id=rfq_id,
        provider=provider,
        contact=body.contact,
        note=body.note,
    )
    session.add(q)
    session.flush()   # the row must exist before the status is read off it
    _sync_status(rfq, session)
    record_audit_event(
        session,
        action="QUOTE_SOLICITED",
        object_type="RFQ_QUOTE",
        object_id=q.id,
        actor_user_id=current.id,
        result="SUCCESS",
        after=_quote_row(q, _counterparty_by_provider(session)),
        reason="Ajout d'un fournisseur au processus de cotation.",
    )
    session.commit()
    session.refresh(q)
    return _quote_row(q, _counterparty_by_provider(session))


@router.patch("/{rfq_id}/quotes/{quote_id}")
def update_quote(
    rfq_id: int,
    quote_id: int,
    body: QuoteUpdate,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    rfq = _get_owned(rfq_id, current, session)
    q = session.get(RfqQuote, quote_id)
    if not q or q.rfq_id != rfq_id:
        raise HTTPException(404, "Quote introuvable")
    before_audit = _quote_row(q, _counterparty_by_provider(session))
    data = body.model_dump(exclude_unset=True)
    audited_fields = set(data) & {"price", "currency", "status", "quoted_at",
                                  "firmness", "valid_until", "last_look"}
    # A note annotates, it doesn't evidence — everything else on a quote is
    # part of the competitive record once the tender has traded.
    if any(k != "note" for k in data):
        _refuse_if_booked(rfq, session, "les cotations")
    if "price" in data:
        _validate_quote_price(data["price"])
        if "status" not in data:
            data["status"] = "recu" if data["price"] is not None else "en_attente"
        if data["price"] is not None and q.quoted_at is None and "quoted_at" not in data:
            data["quoted_at"] = datetime.utcnow()
        # Contre-cote de last look : elle doit améliorer la cotation qu'elle
        # remplace. Sinon elle sortait la meilleure réponse du fournisseur de
        # ses propres statistiques — un UBS à +102 bps en notre faveur devenu
        # -102 bps à l'écran, sans que personne ne l'ait décidé.
        if q.parent_quote_id is not None and data["price"] is not None:
            parent = session.get(RfqQuote, q.parent_quote_id)
            if parent and parent.price is not None and not _improves(
                    data["price"], parent.price, rfq.sens):
                sense = "plus bas" if rfq.sens == "achat" else "plus haut"
                raise HTTPException(
                    422, f"Un last look s'aligne ou garde son prix : la contre-cote "
                         f"({data['price']}) doit être {sense} que la cotation d'origine "
                         f"({parent.price}). Si le fournisseur revient moins bien, sa cotation "
                         f"initiale reste sa réponse — annulez le last look.")
    if "quoted_at" in data:
        data["quoted_at"] = _parse_utc_datetime(data["quoted_at"], "quoted_at")
    if "valid_until" in data:
        data["valid_until"] = _parse_utc_datetime(data["valid_until"], "valid_until")
        received_at = data.get("quoted_at", q.quoted_at)
        if data["valid_until"] is not None and received_at is not None \
                and data["valid_until"] <= received_at:
            raise HTTPException(
                422, "valid_until doit être postérieure à l'heure de réception de la quote.")

    if "last_look" in data:
        want = data.pop("last_look")
        if q.parent_quote_id is not None:
            raise HTTPException(
                422, "Un last look est une contre-cotation finale et ne peut pas "
                     "engendrer un nouveau last look.")
        if want and q.price is None:
            raise HTTPException(
                422, "Un last look ne peut être demandé qu'après réception d'un prix initial.")
        child = session.exec(
            select(RfqQuote).where(RfqQuote.parent_quote_id == quote_id)
        ).first()
        if want and not child:
            child = RfqQuote(rfq_id=rfq_id, provider=q.provider, contact=q.contact,
                              parent_quote_id=quote_id)
            session.add(child)
        elif not want and child:
            if child.price is not None or child.quoted_at is not None:
                raise HTTPException(
                    422, "Le last look a déjà une réponse — on ne peut pas l'annuler, "
                         "seule la cotation retenue compte désormais.")
            session.delete(child)
        q.last_look = want

    for field, value in data.items():
        setattr(q, field, value)
    if rfq.selected_quote_id == q.id and (
            q.price is None or q.status in {"decline", "expire"}):
        rfq.selected_quote_id = None
        session.add(rfq)
    if q.parent_quote_id is not None and q.price is not None \
            and rfq.selected_quote_id == q.parent_quote_id:
        # The answered counter-quote replaces its parent.  Never leave the
        # tender pointing at a response that its own history marks superseded.
        rfq.selected_quote_id = None
        session.add(rfq)
    session.add(q)
    # A price arriving (or being cleared) is what moves the tender from
    # "envoyée" to "cotée" and back.
    _sync_status(rfq, session)
    if audited_fields:
        record_audit_event(
            session,
            action="QUOTE_UPDATED",
            object_type="RFQ_QUOTE",
            object_id=q.id,
            actor_user_id=current.id,
            result="SUCCESS",
            before=before_audit,
            after=_quote_row(q, _counterparty_by_provider(session)),
            reason="Mise à jour d'une donnée de cotation.",
            metadata={"fields": sorted(audited_fields)},
        )
    session.commit()
    return _quote_row(q, _counterparty_by_provider(session))


@router.delete("/{rfq_id}/quotes/{quote_id}", status_code=204)
def delete_quote(
    rfq_id: int,
    quote_id: int,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    rfq = _get_owned(rfq_id, current, session)
    q = session.get(RfqQuote, quote_id)
    if not q or q.rfq_id != rfq_id:
        raise HTTPException(404, "Quote introuvable")
    _refuse_if_booked(rfq, session, "la suppression d'une cotation")
    child = session.exec(select(RfqQuote).where(RfqQuote.parent_quote_id == quote_id)).first()
    ids_removed = {quote_id} | ({child.id} if child else set())
    if child:
        session.delete(child)
    if rfq.selected_quote_id in ids_removed:
        rfq.selected_quote_id = None
        session.add(rfq)
    session.delete(q)
    _sync_status(rfq, session)
    session.commit()
