"""RFQ (request-for-quote) tracker: collect and compare bank quotes for a
structured product against Structura's own model price."""
from __future__ import annotations
import json
from datetime import date, datetime, timezone
from ..runtime import business_now, business_today
from typing import Annotated, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlmodel import Session, select
from ..db.database import get_session
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
from .auth import get_current_user
from ..services.rfq_state import (
    RfqPricingInput,
    _booked_deals_by_rfq,
    _counterparty_by_provider,
    _derive_status,
    _get_owned,
    _get_quotes,
    _quote_row,
    _rfq_product,
    _rfq_row,
    _sync_product_rfq,
    _sync_status,
    _utc_iso,
    superseded_quote_ids,
    _TERMINAL_STATUSES,
    _LEGAL_CONTEXT_FIELDS,
    compose_rfq_pricing_input as _compose_rfq_pricing_input,
)

router = APIRouter(prefix="/api/rfq", tags=["rfq"])


# ── Pydantic schemas ──────────────────────────────────────────────────

class RfqCreate(BaseModel):
    pilot_desk_id: Optional[int] = None
    previous_round_id: Optional[int] = None
    product_id: Optional[int] = None
    product_terms_version: Optional[int] = None
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
    # Le besoin client à l'origine de cet appel d'offres, s'il y en a un.
    # Optionnel et sans effet sur le reste du module : une RFQ créée hors de
    # tout parcours client se comporte exactement comme avant. Sert à remonter
    # Trade → RFQ → Opportunity → Client → Affiliation.
    opportunity_id: Optional[int] = None
    client_id: Optional[int] = None
    mandate_id: Optional[int] = None
    primary_affiliation_id: Optional[int] = None
    transaction_format: Optional[str] = None
    instrument_family: Optional[str] = None
    payoff_family: Optional[str] = None
    payoff_description: Optional[str] = None
    documentation_reference: Optional[str] = None


class RfqUpdate(BaseModel):
    name: Optional[str] = None
    ao_date: Optional[str] = None
    sens: Optional[str] = Field(default=None, pattern="^(achat|vente)$")
    params: Optional[dict] = None
    # Model assumptions only — volatility, dividend, rate, model, path count.
    # Merged into the stored params without ever touching the contractual
    # identity, so re-pricing stays possible for the whole life of a tender,
    # quotes in hand or not. See _merge_pricing_params for why this exists
    # rather than resubmitting the whole blob through `params`.
    pricing_params: Optional[dict] = None
    status: Optional[str] = None
    model_price: Optional[float] = None
    pricing_receipt: Optional[dict] = None
    expected_model_input_hash: Optional[str] = Field(default=None, min_length=64, max_length=64)
    selected_quote_id: Optional[int] = None
    expected_quote_revision: Optional[int] = Field(default=None, ge=1)
    selection_reason_code: Optional[str] = Field(
        default=None,
        pattern="^(price|client_request|documentation|credit|concentration|relationship|execution_quality|other)$")
    selection_reason_note: Optional[str] = None
    opportunity_id: Optional[int] = None
    client_id: Optional[int] = None
    mandate_id: Optional[int] = None
    primary_affiliation_id: Optional[int] = None
    transaction_format: Optional[str] = None
    instrument_family: Optional[str] = None
    payoff_family: Optional[str] = None
    payoff_description: Optional[str] = None
    documentation_reference: Optional[str] = None




class RfqExchangePreview(BaseModel):
    expected_terms_version: int = Field(gt=0)
    shared_title: str = Field(min_length=1, max_length=200)
    response_deadline: datetime
    provider_ids: list[int] = Field(default_factory=list, max_length=50)
    relationship_ids: list[int] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def recipients(self):
        if not 1 <= len(self.provider_ids) + len(self.relationship_ids) <= 50:
            raise ValueError("Choisissez entre un et cinquante destinataires")
        return self


class RfqExchangeSend(RfqExchangePreview):
    command_key: str = Field(min_length=16, max_length=100)
    expected_preview_hash: str = Field(min_length=64, max_length=64)


class RfqSharePut(BaseModel):
    rights: list[str] = Field(min_length=1)
    reason: str = Field(min_length=3, max_length=500)
    expires_at: Optional[datetime] = None


class RfqAssignmentPut(BaseModel):
    pilot_desk_id: int
    responsible_user_id: int
    expected_pilot_desk_id: int
    expected_responsible_user_id: Optional[int] = None
    expected_share_desk_ids: list[int]
    retained_share_desk_ids: list[int]
    reason: str = Field(min_length=3, max_length=500)


class QuoteCreate(BaseModel):
    provider: str = Field(default="manuel", min_length=1)
    contact: Optional[str] = None
    note: Optional[str] = None
    provider_id: Optional[int] = None
    counterparty_id: Optional[int] = None


class QuoteUpdate(BaseModel):
    expected_revision: Optional[int] = Field(default=None, ge=1)
    counterparty_id: Optional[int] = None
    identity_reason: Optional[str] = Field(default=None, min_length=3, max_length=500)
    price: Optional[float] = Field(default=None, allow_inf_nan=False)
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












def _rfq_audit_state(rfq: RfqRequest) -> dict:
    return {
        "reference": rfq.reference,
        "kind": rfq.kind,
        "status": rfq.status,
        "selected_quote_id": rfq.selected_quote_id,
        "selected_quote_revision": rfq.selected_quote_revision,
        "model_price": rfq.model_price,
        "model_price_at": _utc_iso(rfq.model_price_at),
        "model_input_hash": rfq.model_input_hash,
        "client_id": rfq.client_id,
        "mandate_id": rfq.mandate_id,
        "primary_affiliation_id": rfq.primary_affiliation_id,
        "opportunity_id": rfq.opportunity_id,
        "transaction_format": rfq.transaction_format,
        "instrument_family": rfq.instrument_family,
        "payoff_family": rfq.payoff_family,
        "selection_reason_code": rfq.selection_reason_code,
        "selection_reason_note": rfq.selection_reason_note,
    }




# Statuses the desk poses by hand; everything else is deduced from what has
# actually happened to the tender. "clos" is posed by api/deals.py:book_deal,
# "sans_suite" by the user (an AO that led nowhere — the majority of them, and
# the denominator of any hit-ratio statistic). Both are terminal: a booked or
# abandoned tender never falls back to an earlier stage on its own.
# The only status a PATCH may pose directly, plus the sentinel that hands the
# RFQ back to the derivation.
_SETTABLE_STATUSES = {"sans_suite", "auto"}








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


# Keys that define WHAT is being tendered. They are frozen once a provider has
# been solicited, and a re-pricing must never be able to reach them — not even
# by resubmitting an identical-looking value.
_CONTRACTUAL_KEYS = set(TERM_FIELDS) | {'notional', 'currency', 'date_conventions',
    'product_id', 'product_terms_version', 'script_snapshot'}
_CONTRACTUAL_UL_KEYS = set(IDENTITY_FIELDS)
_RFQ_MODEL_KEYS = {'r', 'corr_matrix', 'N', 'seed', 'model', 'antithetic',
    'yield_curve', 'funding_curve', 'funding_spread', 'sigma_r', 'a_r',
    'barrier_monitoring', 'valuation_date', 'compute_greeks', 'selected_greeks'}


def _merge_pricing_params(rfq: RfqRequest, incoming: dict) -> dict:
    """Only explicit calculation assumptions may cross this boundary."""
    from ..core.schemas import UnderlyingParams
    forbidden = set(incoming) - _RFQ_MODEL_KEYS - {'underlyings'}
    if forbidden:
        raise HTTPException(422, detail={'code': 'RFQ_PRICING_FIELDS_FORBIDDEN',
            'message': 'Le pricing ne modifie pas les termes contractuels ni les champs inconnus : '
                       + ', '.join(sorted(forbidden))})
    stored = json.loads(rfq.params_json or '{}')
    merged = {**stored, **{key: value for key, value in incoming.items() if key != 'underlyings'}}
    if 'underlyings' in incoming:
        rows = incoming['underlyings']
        originals = stored.get('underlyings') or []
        if not isinstance(rows, list) or len(rows) > len(originals):
            raise HTTPException(422, 'Les hypothèses doivent respecter le panier stocké.')
        allowed = set(UnderlyingParams.model_fields) - IDENTITY_FIELDS
        out = [dict(item) for item in originals]
        for i, row in enumerate(rows):
            if not isinstance(row, dict) or set(row) - allowed:
                raise HTTPException(422, 'Les hypothèses de sous-jacent ne modifient pas son identité ; champ inconnu ou contractuel.')
            out[i].update(row)
        merged['underlyings'] = out
    return merged


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
    contacts = session.exec(select(RfqProviderContact).where(
        RfqProviderContact.active == True)).all()  # noqa: E712
    return [{"id": p.id, "label": p.label, "mode": p.mode,
             "contacts": [{"id": c.id, "name": c.name, "email": c.email}
                          for c in contacts if c.provider_id == p.id]}
            for p in providers]


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


def _refuser_reglement_avant_maturite(params: dict) -> None:
    """Le remboursement final ne peut pas précéder la dernière constatation.

    Refusé à l'ÉCRITURE, pas seulement au booking. Un AO peut recevoir des
    cotations en quelques minutes, et ses termes contractuels sont alors gelés :
    une incohérence acceptée à la création devient impossible à corriger, et ne
    se révèle qu'au refus de booking — sur un message qui parle d'un écart de
    `payment_date` sans dire lequel des deux côtés a tort.

    C'est exactement ce qui est arrivé à RFQ-20260829-001 : maturité 2029,
    règlement 2026.
    """
    paiement = params.get("payment_date")
    maturite = maturity_iso(params)
    if paiement and maturite and str(paiement) < maturite:
        raise HTTPException(
            422,
            f"Le règlement ({paiement}) précède la maturité ({maturite}). "
            f"La date de paiement date l'échange final des flux : elle suit la "
            f"dernière constatation, elle ne la précède pas.")


_COMMERCIAL_CONTEXT_FIELDS = {
    "client_id", "mandate_id", "primary_affiliation_id", "opportunity_id",
}


def _resolve_commercial_context(
    *,
    opportunity_id: int | None,
    client_id: int | None,
    mandate_id: int | None,
    primary_affiliation_id: int | None,
    current: User,
    session: Session,
    explicit_fields: set[str] | None = None,
    qualification_required: bool = True,
) -> tuple[dict, Opportunity | None]:
    """Resolve one optional Client context without affecting product-only RFQs."""
    explicit_fields = explicit_fields or set()
    opportunity = None
    if opportunity_id is not None:
        opportunity = session.get(Opportunity, opportunity_id)
        if opportunity is None or opportunity.entity_id != current.entity_id:
            raise HTTPException(404, "Opportunité introuvable")
        if opportunity.status in OPPORTUNITY_TERMINAL:
            raise HTTPException(409, detail={
                "code": "OPPORTUNITY_CLOSED",
                "message": "Cette Opportunity est clôturée. Rouvrez-la avant de lancer un RFQ.",
            })
        if qualification_required:
            try:
                require_opportunity_rfq_ready(session, opportunity)
            except ClientRuleError as error:
                raise HTTPException(422, detail=error.as_dict())

        inherited = {
            "client_id": opportunity.client_id,
            "mandate_id": opportunity.mandate_id,
            "primary_affiliation_id": opportunity.primary_affiliation_id,
        }
        supplied = {
            "client_id": client_id,
            "mandate_id": mandate_id,
            "primary_affiliation_id": primary_affiliation_id,
        }
        for field, expected in inherited.items():
            if (field in explicit_fields and supplied[field] is not None
                    and supplied[field] != expected):
                raise HTTPException(422, detail={
                    "code": "RFQ_OPPORTUNITY_CONTEXT_MISMATCH",
                    "message": (f"Le champ {field} contredit l'Opportunity. "
                                "Le contexte RFQ est déduit côté serveur."),
                    "field": field, "expected": expected,
                    "received": supplied[field],
                })
        client_id = inherited["client_id"]
        mandate_id = inherited["mandate_id"]
        primary_affiliation_id = inherited["primary_affiliation_id"]

    try:
        require_deal_attribution_coherent(
            session, client_id=client_id, mandate_id=mandate_id,
            affiliation_id=primary_affiliation_id,
            opportunity_id=opportunity_id, entity_id=current.entity_id)
    except ClientRuleError as error:
        raise HTTPException(422, detail=error.as_dict())

    snapshot = client_provenance_snapshot(
        session, client_id=client_id, mandate_id=mandate_id,
        affiliation_id=primary_affiliation_id,
        opportunity_id=opportunity_id)
    return {
        "client_id": client_id,
        "mandate_id": mandate_id,
        "primary_affiliation_id": primary_affiliation_id,
        "opportunity_id": opportunity_id,
        "commercial_context_json": snapshot,
    }, opportunity


def _clean_optional(value) -> str | None:
    cleaned = str(value or "").strip()
    return cleaned or None


def _validate_rfq_correlation(params: dict) -> None:
    """Reject an incomplete basket before it can become an RFQ record.

    Correlation is a material input for both pricing and Risk.  Persisting a
    two-name basket without it would force a later module to invent an
    identity matrix, so every RFQ mutation that can carry pricing inputs uses
    the same explicit contract.
    """
    underlyings = params.get("underlyings") or []
    matrix = params.get("corr_matrix")
    if len(underlyings) <= 1 and not matrix:
        return
    try:
        validate_correlation_matrix(matrix or [], len(underlyings))
    except (TypeError, ValueError) as exc:
        raise HTTPException(422, detail={
            "code": "CORRELATION_MATRIX_INVALID",
            "message": f"Matrice de corrélation RFQ invalide : {exc}",
        }) from exc


def _product_terms_from_payload(script: str, params: dict, *, kind: str):
    """Build canonical Product terms from validated RFQ fields."""
    return terms_from_input({
        "script": script,
        "underlyings": params.get("underlyings") or [],
        "user_params": params.get("user_params") or {},
        "constats": params.get("constats") or {},
        "T": params.get("T"),
        "strike_date": params.get("strike_date"),
        "value_date": params.get("value_date"),
        "maturity_date": params.get("maturity_date") or maturity_iso(params),
        "payment_date": params.get("payment_date"),
        "anchor": params.get("anchor"),
        "settlement_ccy": params.get("currency"),
        "frozen_schedule": params.get("frozen_schedule"),
    }, allow_unresolved=kind != "to_trade")


def _product_terms_from_rfq(body: RfqCreate):
    return _product_terms_from_payload(
        body.script_snapshot, body.params or {}, kind=body.kind)


def _create_rfq(
    body: RfqCreate,
    current: User,
    session: Session,
    *,
    reference_prefix: str | None = None,
    uat_batch_id: int | None = None,
):
    desk = (require_create_desk(session, body.pilot_desk_id, current)
            if uat_batch_id is None else None)
    previous_round = None
    if body.previous_round_id is not None:
        previous_round = session.get(RfqExchangeRound, body.previous_round_id)
        if previous_round is None:
            raise HTTPException(404, "Tour précédent introuvable")
        previous_rfq = lock_rfq_organization(session, previous_round.rfq_id, current, "prepare")
        if desk is None or previous_rfq.entity_id != desk.entity_id:
            raise HTTPException(403, "Le nouveau tour doit appartenir à la même organisation")
        if previous_round.state not in {"OPEN", "CLOSED"} or session.exec(select(RfqRoundLink).where(
                RfqRoundLink.previous_round_id == previous_round.id)).first():
            raise HTTPException(409, "Un nouveau tour existe déjà pour cette consultation")
        _refuse_if_booked(previous_rfq, session, "l’ouverture d’un nouveau tour")
        if previous_rfq.status == 'sans_suite' and previous_round.state == 'OPEN':
            rfq_exchange.close_round(session, previous_rfq, current)
            _sync_product_rfq(session, previous_rfq, current, action='PRODUCT_RFQ_LEGACY_ROUND_CLOSED')
    product = None
    if body.product_id is not None:
        try:
            product_row = owned_record(session, body.product_id, current)
            if desk is not None and product_row.entity_id != desk.entity_id:
                raise HTTPException(404, "Produit introuvable dans cette organisation")
            product = load_product(session, body.product_id)
        except ProductError as exc:
            raise HTTPException(exc.status, detail={"code": exc.code, "message": str(exc)})
        if (body.product_terms_version is not None
                and body.product_terms_version != product.terms_version):
            raise HTTPException(409, detail={
                "code": "PRODUCT_TERMS_STALE",
                "message": "La version des termes du produit a changé. Rechargez le produit.",
            })
        if product.execution:
            raise HTTPException(409, detail={'code': 'PRODUCT_BOOKED',
                'message': 'Ce Product est booké ; conservez un nouveau Product pour une autre demande.'})
        # Omitted RFQ fields inherit the retained intent. Explicit empty/null
        # fields remain user decisions and pass normal commercial validation.
        inherited = {'sens': 'achat' if product.intent.side == 'BUY' else 'vente',
                     'template_type': product.intent.product_type,
                     **{field: getattr(product.intent, field) for field in _LEGAL_CONTEXT_FIELDS},
                     **product.commercial.model_dump(mode='json')}
        body = body.model_copy(update={field: value for field, value in inherited.items()
                                       if field not in body.model_fields_set})
        terms = product.terms
        params = dict(body.params or {})
        if 'notional' not in params and product.intent.nominal is not None:
            params['notional'] = product.intent.nominal
        market_underlyings = params.get("underlyings") or [{} for _ in terms.underlyings]
        if len(market_underlyings) != len(terms.underlyings):
            raise HTTPException(422, detail={
                "code": "PRODUCT_MARKET_CONTEXT_INCOMPLETE",
                "message": "Les hypothèses RFQ ne couvrent pas tout le panier du produit.",
            })
        params.update({
            "T": terms.T,
            "user_params": terms.user_params(),
            "constats": terms.constats.to_dict(),
            "strike_date": terms.strike_date.isoformat() if terms.strike_date else None,
            "value_date": terms.value_date.isoformat() if terms.value_date else None,
            "maturity_date": terms.maturity_date.isoformat() if terms.maturity_date else None,
            "payment_date": terms.payment_date.isoformat() if terms.payment_date else None,
            "currency": terms.settlement_ccy,
            "frozen_schedule": (terms.resolved_events.to_dict()
                                if terms.resolved_events else None),
            "underlyings": [
                {**market, **identity.model_dump(mode="json")}
                for identity, market in zip(terms.underlyings, market_underlyings)
            ],
        })
        body = body.model_copy(update={
            "script_snapshot": terms.script,
            "params": params,
            "product_terms_version": product.terms_version,
        })
    _validate_rfq_correlation(body.params or {})
    if body.kind == "to_trade" and not _is_expert_script(body.script_snapshot):
        raise HTTPException(
            422, "Une RFQ 'to trade' doit utiliser un script en mode Expert (calendrier "
                 "CONSTAT réel) pour la précision requise — sauvegardez-le dans le Pricer, "
                 "ou repartez du script d'un deal déjà booké en mode Expert.")

    if body.kind == "to_trade":
        calendar_failures = contract_calendar_failures(
            body.script_snapshot, body.params or {})
        if calendar_failures:
            raise HTTPException(422, detail={
                "code": calendar_failures[0].code,
                "message": calendar_failures[0].message,
                "failures": [failure.as_dict() for failure in calendar_failures],
            })

    _refuser_reglement_avant_maturite(body.params or {})

    # Rattachement commercial facultatif. L'absence complète de contexte est
    # un parcours Produit autonome valide. Dès qu'une référence existe, le
    # couple Client/Mandat devient obligatoire et cohérent.
    context, opportunity = _resolve_commercial_context(
        opportunity_id=body.opportunity_id,
        client_id=body.client_id,
        mandate_id=body.mandate_id,
        primary_affiliation_id=body.primary_affiliation_id,
        current=current, session=session,
        explicit_fields=set(body.model_fields_set),
    )

    transaction_format = (_clean_optional(body.transaction_format)
                          or (opportunity.transaction_format if opportunity else None))
    instrument_family = (_clean_optional(body.instrument_family)
                         or (opportunity.instrument_family if opportunity else None))
    payoff_family = (_clean_optional(body.payoff_family)
                     or (opportunity.payoff_family if opportunity else None)
                     or canonical_payoff_family(body.template_type))
    payoff_description = (_clean_optional(body.payoff_description)
                          or (opportunity.payoff_description if opportunity else None))
    try:
        payoff_family = normalize_new_payoff_family(
            payoff_family, payoff_description)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc

    commercial = CommercialContext(
        client_id=context["client_id"],
        mandate_id=context["mandate_id"],
        opportunity_id=context["opportunity_id"],
        primary_affiliation_id=context["primary_affiliation_id"],
    )
    intent_values = {
        "nominal": (body.params or {}).get("notional"),
        "side": "BUY" if body.sens == "achat" else "SELL",
        "product_type": body.template_type,
        "transaction_format": transaction_format or "",
        "instrument_family": instrument_family or "",
        "payoff_family": payoff_family or "",
        "payoff_description": payoff_description or "",
        "documentation_reference": _clean_optional(body.documentation_reference) or "",
    }
    if product is None:
        try:
            product = stage_internal_product(
                session,
                user=current,
                name=body.name,
                terms=_product_terms_from_rfq(body),
                intent=TradeIntent(**intent_values),
                commercial=commercial,
                data_origin="uat" if uat_batch_id is not None else "native",
                uat_batch_id=uat_batch_id,
                reason="Création interne du Product à l'ouverture de la RFQ.",
            )
        except (ProductError, ValueError) as exc:
            session.rollback()
            detail = ({"code": exc.code, "message": str(exc)}
                      if isinstance(exc, ProductError) else {
                          "code": "PRODUCT_TERMS_INVALID", "message": str(exc)})
            raise HTTPException(422, detail=detail) from exc
        body = body.model_copy(update={
            "product_id": product.product_id,
            "product_terms_version": product.terms_version,
        })
    else:
        product = product.model_copy(update={
            "intent": TradeIntent(**{
                **product.intent.model_dump(mode="json"),
                **intent_values,
            }),
            "commercial": commercial,
        })

    reference = (next_reference(session, RfqRequest, reference_prefix)
                 if reference_prefix else _gen_ref(session))
    rfq = RfqRequest(
        id=next_audited_id(session, RfqRequest, "RFQ"),
        reference=reference,
        entity_id=current.entity_id,
        user_id=current.id,
        uat_batch_id=uat_batch_id,
        product_id=product.product_id,
        product_terms_version=product.terms_version,
        name=body.name.strip(),
        ao_date=body.ao_date or business_today().isoformat(),
        kind=body.kind,
        sens=body.sens,
        template_type=body.template_type,
        script_id=body.script_id,
        script_snapshot=body.script_snapshot,
        params_json=json.dumps(body.params),
        **context,
        transaction_format=transaction_format,
        instrument_family=instrument_family,
        payoff_family=payoff_family,
        payoff_description=payoff_description,
        documentation_reference=_clean_optional(body.documentation_reference),
    )
    session.add(rfq)
    session.flush()
    if desk is not None:
        session.add(RfqOwnership(
            rfq_id=rfq.id, entity_id=desk.entity_id,
            pilot_desk_id=desk.id, responsible_user_id=current.id))
        session.flush()
    if previous_round is not None:
        session.add(RfqRoundLink(rfq_id=rfq.id, previous_round_id=previous_round.id))
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
    snapshot = FrozenObject(_rfq_row(rfq, []))
    product = product.model_copy(update={"rfqs": (*product.rfqs, snapshot)})
    stage_revision(
        session, product, expected_revision=product.revision,
        actor_id=current.id, action="PRODUCT_RFQ_CREATED",
        reason=f"Création de {rfq.reference} depuis le produit.")
    session.commit()
    session.refresh(rfq)
    return _rfq_row(rfq, [], session=session, current=current)


@router.post("", status_code=201)
def create_rfq(
    body: RfqCreate,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    return _create_rfq(body, current, session)


@router.get("")
def list_rfqs(
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    rfqs = visible_rfqs(session, current)
    booked = _booked_deals_by_rfq(session, current.id)
    quotes_by_rfq: dict[int, list[RfqQuote]] = {}
    if rfqs:
        for quote in session.exec(select(RfqQuote).where(
                RfqQuote.rfq_id.in_([rfq.id for rfq in rfqs]))).all():
            quotes_by_rfq.setdefault(quote.rfq_id, []).append(quote)
    return [_rfq_row(r, quotes_by_rfq.get(r.id, []), booked_by_rfq=booked,
                     session=session, current=current)
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
    visible_ids = {rfq.id for rfq in visible_rfqs(session, current)
                   if "price" in effective_rights(session, rfq, current)}
    if not visible_ids:
        return []
    rows = session.exec(
        select(RfqQuote, RfqRequest)
        .join(RfqRequest, RfqQuote.rfq_id == RfqRequest.id)
        .where(RfqRequest.id.in_(visible_ids))
        .where(RfqQuote.price.is_not(None))
    ).all()
    # Superseded parents are computed over ALL quotes, not just the priced
    # ones above: a last look answers with a price, so it is always in the
    # filtered set, but that is not something to rely on silently.
    superseded = superseded_quote_ids(session.exec(
        select(RfqQuote).join(RfqRequest, RfqQuote.rfq_id == RfqRequest.id)
        .where(RfqRequest.id.in_(visible_ids))
    ).all())
    return [
        {
            "quote_id": q.id,
            "rfq_id": rfq.id,
            "reference": rfq.reference,
            "template_type": rfq.template_type,
            "provider": q.provider,
            "price": q.price,
            "model_price": (json.loads(q.model_reference_json).get("price") if q.model_reference_json else None),
            "model_reference": json.loads(q.model_reference_json) if q.model_reference_json else None,
            "sens": rfq.sens,
            # Raw signed price difference, kept as the factual number; edge_bps
            # is the one to aggregate on (see _edge_bps).
            "spread_bps": round((q.price - json.loads(q.model_reference_json)["price"]) / json.loads(q.model_reference_json)["price"] * 10000, 1)
                          if q.model_reference_json and json.loads(q.model_reference_json).get("price") else None,
            "edge_bps": _edge_bps(q.price, json.loads(q.model_reference_json).get("price") if q.model_reference_json else None, rfq.sens),
            "date": _utc_iso(q.quoted_at or q.created_at),
            "status": q.status,
            **{key: value for key, value in _quote_row(q, superseded=q.id in superseded, session=session).items()
               if key in {'origin', 'comparable', 'history_eligible', 'currency', 'revision'}},
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
        for q, rfq in rows if rfq.id in visible_ids
    ]


@router.get("/{rfq_id}")
def get_rfq(
    rfq_id: int,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    rfq = _get_owned(rfq_id, current, session)
    return _rfq_row(rfq, _get_quotes(rfq_id, session), _counterparty_by_provider(session),
                    _booked_deals_by_rfq(session, current.id), session=session, current=current)


@router.get("/{rfq_id}/terms")
def rfq_terms(
    rfq_id: int,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    """Only this RFQ's contractual Product terms; no sibling RFQs or private calculations."""
    rfq = _get_owned(rfq_id, current, session)
    product = _rfq_product(rfq, rfq.product_terms_version, current, session)
    return {"product_id": product.product_id, "reference": product.reference,
            "terms_version": product.terms_version,
            "terms_fingerprint": product.terms_fingerprint,
            "terms": product.terms.model_dump(mode="json", exclude={"schedule_error"})}


from ..services import rfq_electronic


@router.post('/{rfq_id}/electronic-execution')
def request_electronic_execution(rfq_id: int, body: rfq_electronic.ElectronicRequest,
                                current: Annotated[User, Depends(get_current_user)],
                                session: Annotated[Session, Depends(get_session)]):
    return rfq_electronic.request(session, rfq_id, current, body)


@router.post("/{rfq_id}/treatment")
def declare_treatment(rfq_id: int, body: rfq_execution.TreatmentRequest,
                      current: Annotated[User, Depends(get_current_user)],
                      session: Annotated[Session, Depends(get_session)]):
    return rfq_execution.request_treatment(session, rfq_id, current, body)


@router.post("/{rfq_id}/treatment/{agreement_id}/confirm")
def confirm_treatment(rfq_id: int, agreement_id: int, body: rfq_execution.TreatmentConfirmation,
                      current: Annotated[User, Depends(get_current_user)],
                      session: Annotated[Session, Depends(get_session)]):
    return rfq_execution.confirm_treatment(session, rfq_id, agreement_id, current, body)


class TreatmentCancellation(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


@router.post("/{rfq_id}/treatment/{agreement_id}/cancel")
def cancel_treatment(rfq_id: int, agreement_id: int, body: TreatmentCancellation,
                     current: Annotated[User, Depends(get_current_user)],
                     session: Annotated[Session, Depends(get_session)]):
    return rfq_execution.cancel_request(session, rfq_id, agreement_id, current, body.reason)


@router.get("/{rfq_id}/shares")
def list_rfq_shares(
    rfq_id: int,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    rfq = _get_owned(rfq_id, current, session, "organize")
    if ownership(session, rfq.id) is None:
        return []
    rows = session.exec(select(RfqDeskShare).where(
        RfqDeskShare.rfq_id == rfq_id).order_by(RfqDeskShare.created_at)).all()
    return [{"desk_id": row.desk_id, "desk_name": session.get(RfqDesk, row.desk_id).name,
             "rights": json.loads(row.rights_json), "active": row.active,
             "expires_at": _utc_iso(row.expires_at), "reason": row.reason}
            for row in rows]


@router.put("/{rfq_id}/assignment")
def change_rfq_assignment(
    rfq_id: int,
    body: RfqAssignmentPut,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    return assign_rfq(session, rfq_id, current, **body.model_dump())


@router.put("/{rfq_id}/shares/{desk_id}")
def share_rfq(
    rfq_id: int,
    desk_id: int,
    body: RfqSharePut,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    rfq = lock_rfq_organization(session, rfq_id, current)
    scope = ownership(session, rfq.id)
    desk = session.get(RfqDesk, desk_id)
    if scope is None or not desk or not desk.active or desk.entity_id != scope.entity_id \
            or desk_id == scope.pilot_desk_id:
        raise HTTPException(422, "Desk de partage invalide")
    rights = set(body.rights)
    if not rights <= (RIGHTS - {"organize", "book"}) or "read" not in rights:
        raise HTTPException(422, "Le partage exige la lecture et ne délègue ni organisation ni booking")
    if len(body.reason.strip()) < 3:
        raise HTTPException(422, "Le motif du partage est requis")
    expiry = (body.expires_at.astimezone(timezone.utc).replace(tzinfo=None)
              if body.expires_at and body.expires_at.tzinfo else body.expires_at)
    if expiry and expiry <= datetime.utcnow():
        raise HTTPException(422, "L'échéance doit être future")
    existing = session.exec(select(RfqDeskShare).where(
        RfqDeskShare.rfq_id == rfq_id, RfqDeskShare.desk_id == desk_id)).first()
    before = ({"rights": json.loads(existing.rights_json), "active": existing.active}
              if existing else None)
    share = existing or RfqDeskShare(rfq_id=rfq_id, desk_id=desk_id, actor_user_id=current.id)
    share.rights_json = json.dumps(sorted(rights))
    share.active = True
    share.reason = body.reason.strip()
    share.expires_at = expiry
    share.actor_user_id = current.id
    share.updated_at = datetime.utcnow()
    session.add(share)
    session.flush()
    after = {"desk_id": desk_id, "rights": sorted(rights), "active": True,
             "reason": share.reason, "expires_at": _utc_iso(share.expires_at)}
    record_audit_event(session, action="RFQ_DESK_SHARED", object_type="RFQ",
                       object_id=rfq_id, actor_user_id=current.id, result="SUCCESS",
                       before=before, after=after, reason=share.reason)
    session.commit()
    return after


@router.delete("/{rfq_id}/shares/{desk_id}", status_code=204)
def revoke_rfq_share(
    rfq_id: int,
    desk_id: int,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    lock_rfq_organization(session, rfq_id, current)
    share = session.exec(select(RfqDeskShare).where(
        RfqDeskShare.rfq_id == rfq_id, RfqDeskShare.desk_id == desk_id,
        RfqDeskShare.active == True,  # noqa: E712
    )).first()
    if not share:
        raise HTTPException(404, "Partage introuvable")
    share.active = False
    share.updated_at = datetime.utcnow()
    session.add(share)
    record_audit_event(session, action="RFQ_DESK_SHARE_REVOKED", object_type="RFQ",
                       object_id=rfq_id, actor_user_id=current.id, result="SUCCESS",
                       before={"desk_id": desk_id, "rights": json.loads(share.rights_json)},
                       after={"desk_id": desk_id, "active": False})
    session.commit()




@router.post("/{rfq_id}/pricing-input")
def compose_rfq_pricing_input(
    rfq_id: int,
    body: RfqPricingInput,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    """Compose the canonical RFQ pricing input through its shared service."""
    return _compose_rfq_pricing_input(rfq_id, body, current, session)


def _network_recipient(session: Session, relation: RfqRelationship) -> dict:
    partner = session.get(Entity, relation.partner_entity_id)
    desk = session.get(RfqDesk, relation.receiver_desk_id)
    terms = json.loads(relation.terms_json)
    return {"id": relation.id, "version": relation.version, "label": partner.name,
            "partner_entity_id": relation.partner_entity_id, "desk_id": relation.receiver_desk_id,
            "desk_name": desk.name if desk else None, "reference": relation.reference,
            "treatment_allowed": terms["treatment_allowed"]}


def _transport_issues(session, relation):
    from ..services.rfq_transport import channel_for_relation, channel_current
    channel = channel_for_relation(session, relation.id)
    if channel:
        try:
            channel_current(session, channel)
            if channel.role != "REQUESTER" or channel.entity_id != relation.requester_entity_id:
                return ["Canal distant configuré dans une autre direction"]
        except HTTPException as exc:
            return [str(exc.detail)]
    return []


@router.get("/{rfq_id}/recipients")
def authorized_rfq_recipients(
    rfq_id: int,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    rfq = _get_owned(rfq_id, current, session, "solicit")
    if ownership(session, rfq_id) is None:
        return {"eligible": [], "excluded": [], "network_enabled": False}
    product = _rfq_product(rfq, rfq.product_terms_version, current, session)
    params = json.loads(rfq.params_json)
    rows = session.exec(select(RfqRelationship).where(
        RfqRelationship.requester_entity_id == rfq.entity_id).order_by(RfqRelationship.reference)).all()
    eligible, excluded = [], []
    for relation in rows:
        issues = rfq_relationships.eligibility(session, relation, rfq,
            currency=product.terms.settlement_ccy, nominal=params.get("notional"))
        issues += _transport_issues(session, relation)
        recipient = _network_recipient(session, relation)
        (excluded if issues else eligible).append({**recipient, "issues": issues})
    return {"eligible": eligible, "excluded": excluded, "network_enabled": True}



def _shared_rfq_request(rfq, product, title, deadline, current, session):
    issues = []
    try:
        product.terms.require_complete()
    except ValueError as exc:
        issues.append(str(exc))
    params = json.loads(rfq.params_json or "{}")
    nominal = params.get("notional")
    if not isinstance(nominal, (float, int)) or isinstance(nominal, bool) or not (0 < nominal < float("inf")):
        issues.append("Le nominal enregistré doit être positif et fini.")
        nominal = None
    if not product.terms.settlement_ccy:
        issues.append("La devise contractuelle de règlement est manquante.")
    if rfq.kind == "to_trade":
        for field, label in (("strike_date", "strike"), ("value_date", "valeur"), ("maturity_date", "maturité"), ("payment_date", "paiement")):
            if getattr(product.terms, field) is None:
                issues.append(f"La date de {label} est manquante.")
    if rfq.status in {"clos", "sans_suite"}:
        issues.append("La consultation est clôturée ; dupliquez la RFQ pour une nouvelle demande.")
    entity = session.get(Entity, rfq.entity_id) if rfq.entity_id else None
    if entity is None:
        issues.append("L’organisation du dossier doit être renseignée.")
    scope = ownership(session, rfq.id)
    desk = session.get(RfqDesk, scope.pilot_desk_id) if scope else None
    shared = {
        "format_version": 1,
        **rfq_exchange.identity(session, rfq),
        "product_reference": product.reference,
        "product_model": {"template_type": rfq.template_type or None, "payscript_semantics_version": 1},
        "rfq_reference": rfq.reference,
        "title": title.strip(),
        "kind": rfq.kind,
        "requester": {"organization": entity.name if entity else None, "organization_id": rfq.entity_id,
            "legal_entity": entity.name if entity else None, "desk_id": scope.pilot_desk_id if scope else None,
            "desk": desk.name if desk else None,
            "contact": {"name": current.username, "email": current.email}},
        "side": "BUY" if rfq.sens == "achat" else "SELL",
        "nominal": nominal,
        "currency": product.terms.settlement_ccy,
        "requested_metric": "PRICE",
        "price_unit": "PERCENT_OF_NOTIONAL",
        "price_convention": "ALL_IN",
        "response_deadline": _utc_iso(deadline) if deadline else None,
        "transaction_format": rfq.transaction_format,
        "instrument_family": rfq.instrument_family,
        "payoff_family": rfq.payoff_family,
        "documentation_reference": rfq.documentation_reference,
        "terms_version": product.terms_version,
        "terms_fingerprint": product.terms_fingerprint,
        "terms": product.terms.model_dump(mode="json", exclude={"schedule_error"}),
    }
    return shared, issues


@router.post("/{rfq_id}/exchange-preview")
def preview_rfq_exchange(
    rfq_id: int,
    body: RfqExchangePreview,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    """Read-only recipient projections. No solicitation or delivery is created."""
    rfq = _get_owned(rfq_id, current, session, "solicit")
    product = _rfq_product(rfq, body.expected_terms_version, current, session)
    if not body.shared_title.strip():
        raise HTTPException(422, "L’intitulé partagé est obligatoire.")
    if body.response_deadline.tzinfo is None:
        raise HTTPException(422, "La limite de réponse doit préciser son fuseau horaire.")
    deadline = _parse_utc_datetime(body.response_deadline, "response_deadline")
    if deadline <= business_now():
        raise HTTPException(422, "La limite de réponse doit être dans le futur.")
    if len(set(body.provider_ids)) != len(body.provider_ids):
        raise HTTPException(422, "Un fournisseur ne peut pas figurer deux fois dans la demande.")
    providers = [session.get(RfqProvider, provider_id) for provider_id in body.provider_ids]
    if any(provider is None or not provider.active for provider in providers):
        raise HTTPException(422, "Un destinataire est inconnu ou désactivé.")
    if len(set(body.relationship_ids)) != len(body.relationship_ids):
        raise HTTPException(422, "Une relation ne peut pas figurer deux fois dans la demande")
    network_recipients = []
    if body.relationship_ids and ownership(session, rfq_id) is None:
        raise HTTPException(409, "Créez une RFQ avec un desk pilote pour préparer un destinataire réseau")
    for relation_id in body.relationship_ids:
        relation = rfq_relationships.require_relation(session, relation_id, current.entity_id)
        if relation.requester_entity_id != rfq.entity_id:
            raise HTTPException(404, "Relation RFQ introuvable")
        failures = rfq_relationships.eligibility(session, relation, rfq,
            currency=product.terms.settlement_ccy, nominal=json.loads(rfq.params_json).get("notional"))
        failures += _transport_issues(session, relation)
        if failures:
            raise HTTPException(422, {"code": "RFQ_RELATIONSHIP_NOT_ELIGIBLE",
                "message": "Destinataire réseau non autorisé", "failures": [
                    {"code": "RELATION", "message": issue} for issue in failures]})
        network_recipients.append(_network_recipient(session, relation))
    shared, issues = _shared_rfq_request(rfq, product, body.shared_title, deadline, current, session)
    frozen = rfq_exchange.round_for(session, rfq.id)
    if frozen:
        old = json.loads(frozen.request_json)
        if frozen.state != "OPEN":
            raise HTTPException(409, "Ce tour est clôturé ; ouvrez un nouveau tour lié")
        if old["response_deadline"] != shared["response_deadline"] or old["title"] != shared["title"]:
            raise HTTPException(409, "L’intitulé et le délai du tour sont figés ; ouvrez un nouveau tour")
        shared = old
    if len({item["partner_entity_id"] for item in network_recipients}) != len(network_recipients):
        raise HTTPException(422, "Une organisation ne peut être sollicitée deux fois dans le même envoi")
    packet = {
        "source": {"rfq_id": rfq.id, "product_id": product.product_id, "product_reference": product.reference,
                   "terms_version": product.terms_version, "terms_fingerprint": product.terms_fingerprint},
        "request": shared,
        "messages": [{"recipient_id": provider.id, "recipient_type": "MANUAL",
                      "request": {**shared, "recipient": {"provider": provider.label}}} for provider in providers]
                    + [{"recipient_id": recipient["id"], "recipient_type": "NETWORK",
                        "request": {**shared, "recipient": {"organization": recipient["label"],
                            "organization_id": recipient["partner_entity_id"], "desk": recipient["desk_name"],
                            "desk_id": recipient["desk_id"], "relationship_id": recipient["id"],
                            "relationship_version": recipient["version"], "relationship_reference": recipient["reference"]}}}
                       for recipient in network_recipients],
        "issues": issues,
        "delivery_available": bool(network_recipients) and not issues,
    }
    packet["preview_hash"] = rfq_exchange.digest({"request": packet["request"], "messages": packet["messages"]})
    return packet


@router.get("/{rfq_id}/exchange")
def rfq_exchange_tracking(rfq_id: int, current: Annotated[User, Depends(get_current_user)],
                          session: Annotated[Session, Depends(get_session)]):
    _get_owned(rfq_id, current, session)
    return rfq_exchange.tracking(session, rfq_id)


@router.post("/{rfq_id}/send")
def send_rfq_exchange(rfq_id: int, body: RfqExchangeSend,
                      current: Annotated[User, Depends(get_current_user)],
                      session: Annotated[Session, Depends(get_session)]):
    rfq = lock_rfq_organization(session, rfq_id, current, "solicit")
    if ownership(session, rfq_id) is None:
        raise HTTPException(409, "Créez une RFQ avec un desk pilote pour l’envoi réseau")
    payload_hash = rfq_exchange.digest(body.model_dump(mode="json"))
    previous = rfq_exchange.replay(session, rfq_id, body.command_key, payload_hash)
    if previous:
        return {**previous, "replayed": True, "tracking": rfq_exchange.tracking(session, rfq_id)}
    packet = preview_rfq_exchange(rfq_id, body, current, session)
    if packet["preview_hash"] != body.expected_preview_hash:
        raise HTTPException(409, "Le contenu ou la relation a changé ; préparez à nouveau le récapitulatif")
    if body.provider_ids:
        raise HTTPException(422, "L’envoi réseau concerne les partenaires ; ajoutez les fournisseurs manuels séparément")
    result = rfq_exchange.deliver(session, rfq, packet, current, body.command_key, payload_hash)
    _sync_status(rfq, session)
    _sync_product_rfq(session, rfq, current, action="PRODUCT_RFQ_NETWORK_SENT")
    session.commit()
    return {**result, "replayed": False, "tracking": rfq_exchange.tracking(session, rfq_id)}


@router.patch("/{rfq_id}")
def update_rfq(
    rfq_id: int,
    body: RfqUpdate,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    try:
        return _update_rfq(rfq_id, body, current, session)
    except HTTPException:
        session.rollback()
        raise
    except ProductError as exc:
        session.rollback()
        raise HTTPException(exc.status, detail={'code': exc.code, 'message': str(exc)}) from exc
    except ValueError as exc:
        session.rollback()
        raise HTTPException(422, str(exc)) from exc


def _update_rfq(rfq_id: int, body: RfqUpdate, current: User, session: Session):
    requested = body.model_dump(exclude_unset=True)
    selection_fields = {"selected_quote_id", "expected_quote_revision", "selection_reason_code", "selection_reason_note"}
    price_fields = {"pricing_params", "model_price", "expected_model_input_hash", "pricing_receipt"}
    required_rights = set()
    if requested.keys() & selection_fields:
        required_rights.add("select")
    if requested.keys() & price_fields:
        required_rights.add("price")
    if not requested or requested.keys() - selection_fields - price_fields:
        required_rights.add("prepare")
    rfq = _get_owned(rfq_id, current, session)
    # Scoped mutations serialize with sends, assignments and sharing changes.
    if ownership(session, rfq_id):
        rfq = lock_rfq_organization(session, rfq_id, current, next(iter(required_rights)))
    for right in required_rights:
        _get_owned(rfq_id, current, session, right)
    rfq_execution.protect_mutation(session, rfq_id, set(requested) & {
        "selected_quote_id", "sens", "status", "transaction_format", "instrument_family",
        "payoff_family", "payoff_description", "documentation_reference",
        "client_id", "mandate_id", "opportunity_id", "primary_affiliation_id"})
    if rfq.product_id is None or rfq.product_terms_version is None:
        raise HTTPException(409, detail={
            "code": "RFQ_PRODUCT_MISSING",
            "message": "Cette RFQ ne possède pas de Product canonique.",
        })
    exchange_round = rfq_exchange.round_for(session, rfq_id)
    if exchange_round and exchange_round.state != "OPEN" and (requested.keys() & selection_fields or requested.get("status") == "auto"):
        raise HTTPException(409, "Un tour remplacé ne peut plus être sélectionné ou rouvert")
    product = load_product(session, rfq.product_id, terms_version=rfq.product_terms_version)
    before_audit = _rfq_audit_state(rfq)
    data = body.model_dump(exclude_unset=True)
    pricing_evidence = data.pop("pricing_receipt", None)
    if pricing_evidence is not None and "model_price" not in data:
        raise HTTPException(422, "La preuve de calcul doit accompagner le prix modèle.")
    requested_fields = set(data)
    if 'params' in data and 'pricing_params' in data:
        raise HTTPException(422, 'Séparez la modification des termes et les hypothèses de pricing.')
    merged_pricing = (_merge_pricing_params(rfq, data.get('pricing_params') or {})
                      if 'pricing_params' in data else None)
    old_params = json.loads(rfq.params_json or '{}')
    changes_terms = ('params' in data and product_terms(rfq.script_snapshot, data['params'] or {})
                     != product_terms(rfq.script_snapshot, old_params))
    context_requested = bool(requested_fields & (_COMMERCIAL_CONTEXT_FIELDS | _LEGAL_CONTEXT_FIELDS | {'sens'}))
    nominal_changed = ('params' in data and (data['params'] or {}).get('notional') != old_params.get('notional'))
    latest = load_product(session, rfq.product_id)
    if (context_requested or changes_terms) and latest.terms_version != rfq.product_terms_version:
        raise HTTPException(409, detail={'code': 'PRODUCT_TERMS_STALE',
            'message': 'La RFQ utilise des termes historiques ; ouvrez le Product courant avant de les modifier.'})
    context_changes = requested_fields & _COMMERCIAL_CONTEXT_FIELDS
    if context_changes:
        scope = ownership(session, rfq.id)
        if scope is not None and "read" not in membership_rights(
                session, scope.pilot_desk_id, current):
            raise HTTPException(403, "Le contexte Client reste réservé au desk pilote")
        _refuse_if_booked(rfq, session, "le contexte Client")
        if _get_quotes(rfq_id, session) or rfq_exchange.round_for(session, rfq_id):
            raise HTTPException(
                409, "Le contexte Client d'une RFQ est figé dès qu'un fournisseur "
                     "est sollicité. Ouvrez un nouveau tour pour le corriger.")
        candidate = {
            "opportunity_id": data.get("opportunity_id", rfq.opportunity_id),
            "client_id": data.get("client_id", rfq.client_id),
            "mandate_id": data.get("mandate_id", rfq.mandate_id),
            "primary_affiliation_id": data.get(
                "primary_affiliation_id", rfq.primary_affiliation_id),
        }
        context, _ = _resolve_commercial_context(
            **candidate, current=current, session=session,
            explicit_fields=requested_fields,
        )
        for field, value in context.items():
            setattr(rfq, field, value)
        for field in _COMMERCIAL_CONTEXT_FIELDS:
            data.pop(field, None)

    legal_changes = requested_fields & _LEGAL_CONTEXT_FIELDS
    if legal_changes:
        _refuse_if_booked(rfq, session, "la structure juridique du produit")
        if _get_quotes(rfq_id, session) or rfq_exchange.round_for(session, rfq_id):
            raise HTTPException(
                409, "La structure juridique et produit est figée dès qu'un "
                     "fournisseur est sollicité. Créez une nouvelle RFQ pour la modifier.")
        if "payoff_family" in data or (
            "payoff_description" in data
            and canonical_payoff_family(rfq.payoff_family) == "Autre"
        ):
            try:
                candidate_family = normalize_new_payoff_family(
                    data.get("payoff_family", rfq.payoff_family),
                    data.get("payoff_description", rfq.payoff_description),
                )
            except ValueError as exc:
                raise HTTPException(422, str(exc)) from exc
            if "payoff_family" in data:
                data["payoff_family"] = candidate_family
        for field in _LEGAL_CONTEXT_FIELDS:
            if field in data:
                setattr(rfq, field, _clean_optional(data.pop(field)))
    if "pricing_params" in data:
        _refuse_if_booked(rfq, session, "les hypothèses de pricing")
        data.pop("pricing_params")
        merged = merged_pricing
        _validate_rfq_correlation(merged)
        new_hash = pricing_input_hash(rfq.script_snapshot, merged)
        if rfq.model_price is not None and rfq.model_input_hash != new_hash:
            rfq.model_price = None
            rfq.model_price_at = None
            rfq.model_input_hash = None
        rfq.params_json = json.dumps(merged)
    if "params" in data:
        _refuse_if_booked(rfq, session, "les termes et paramètres de l'AO")
        new_params = data.pop("params") or {}
        if ownership(session, rfq.id) is not None and "price" not in effective_rights(
                session, rfq, current):
            stored = json.loads(rfq.params_json)
            allowed = {"T", "notional", "currency", "strike_date", "value_date",
                       "maturity_date", "payment_date", "user_params", "constats",
                       "frozen_schedule", "date_conventions"}
            combined = {**stored, **{key: value for key, value in new_params.items()
                                     if key in allowed}}
            if "underlyings" in new_params:
                incoming = new_params["underlyings"]
                originals = stored.get("underlyings", [])
                if len(incoming) != len(originals):
                    raise HTTPException(422, "Le panier de la RFQ doit conserver le même nombre de sous-jacents")
                combined["underlyings"] = [
                    {**old, **{key: value for key, value in new.items()
                              if key in IDENTITY_FIELDS}}
                    for old, new in zip(originals, incoming)]
            new_params = combined
        _refuser_reglement_avant_maturite(new_params)
        _validate_rfq_correlation(new_params)
        existing_terms = product_terms(rfq.script_snapshot, json.loads(rfq.params_json))
        new_terms = product_terms(rfq.script_snapshot, new_params)
        if (_get_quotes(rfq_id, session) or rfq_exchange.round_for(session, rfq_id)) and new_terms != existing_terms:
            changed = sorted(k for k in set(existing_terms) | set(new_terms)
                             if existing_terms.get(k) != new_terms.get(k))
            raise HTTPException(
                409, "Les termes contractuels d'une RFQ sont figés dès qu'un fournisseur "
                     "est sollicité. Créez une nouvelle RFQ pour modifier : "
                     + ", ".join(changed) + ".")
        try:
            canonical_terms = _product_terms_from_payload(
                rfq.script_snapshot, new_params, kind=rfq.kind)
            if (_get_quotes(rfq_id, session) or rfq_exchange.round_for(session, rfq_id)) and canonical_terms.fingerprint != product.terms_fingerprint:
                raise HTTPException(409, "Les termes Product sont figés ; ouvrez un nouveau tour")
            product = stage_terms(
                session, product, canonical_terms, actor_id=current.id,
                reason=f"Mise à jour des termes depuis {rfq.reference}.")
        except (ProductError, ValueError) as exc:
            detail = ({"code": exc.code, "message": str(exc)}
                      if isinstance(exc, ProductError) else {
                          "code": "PRODUCT_TERMS_INVALID", "message": str(exc)})
            raise HTTPException(422, detail=detail) from exc
        rfq.product_terms_version = product.terms_version
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
        expected_hash = data.pop("expected_model_input_hash", None)
        if expected_hash is not None and expected_hash != pricing_input_hash(rfq.script_snapshot, json.loads(rfq.params_json or "{}")):
            raise HTTPException(409, detail={"code": "RFQ_PRICING_INPUTS_STALE", "message": "Les hypothèses de la RFQ ont changé pendant le calcul. Relancez le pricing."})
        mp = data.pop("model_price")
        if mp is not None and mp < 0:
            raise HTTPException(
                422, f"Un prix modèle négatif ({mp}) n'est pas un prix de produit — tous les "
                     f"écarts aux cotations en découlent.")
        rfq.model_price = mp
        rfq.model_price_at = business_now()
        rfq.model_input_hash = (
            pricing_input_hash(rfq.script_snapshot, json.loads(rfq.params_json or "{}"))
            if mp is not None else None)
    data.pop("expected_model_input_hash", None)
    if pricing_evidence is not None:
        from ..services.rfq_booking import retain_evidence
        try:
            retain_evidence(session, rfq, current, pricing_evidence)
        except HTTPException:
            session.rollback()
            raise
    if data.get("sens") is not None and data["sens"] != rfq.sens:
        _refuse_if_booked(rfq, session, "le sens de l'AO")
        if _get_quotes(rfq_id, session) or rfq_exchange.round_for(session, rfq_id):
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
            expected_quote_revision = data.get('expected_quote_revision')
            if expected_quote_revision is not None and expected_quote_revision != q.revision:
                raise HTTPException(409, "La cotation a changé ; rechargez la révision à retenir.")
            from ..services.rfq_quote_integrity import same_currency
            if not same_currency(session, rfq, q):
                raise HTTPException(422, "La devise de la cotation diffère des termes Product ; ouvrez un nouveau tour pour une contre-proposition.")
            exchange_round = rfq_exchange.round_for(session, rfq_id)
            if rfq.status in _TERMINAL_STATUSES or (exchange_round and exchange_round.state != 'OPEN'):
                raise HTTPException(409, "Ce tour est clôturé ; ouvrez un nouveau tour lié.")
            if rfq_publication.publication_for_quote(session, q.id) and not _quote_row(q, session=session)["comparable"]:
                raise HTTPException(422, "Cette cotation est inactive, remplacée ou conditionnelle")
            if q.price is None:
                raise HTTPException(
                    422, "Une réponse sans prix ne peut pas être retenue. Saisissez la "
                         "cotation finale ou marquez le fournisseur comme décliné.")
            if q.status in {"decline", "expire"}:
                raise HTTPException(
                    422, f"Une réponse au statut « {q.status} » ne peut pas être retenue.")
            if q.valid_until is not None and q.valid_until <= business_now():
                raise HTTPException(
                    422, "Cette cotation a expiré. Demandez une réponse ferme à jour "
                         "avant de la retenir.")
            quotes = _get_quotes(rfq_id, session)
            if q.id in superseded_quote_ids(quotes):
                raise HTTPException(
                    422, "Cette cotation a été remplacée par son last look : retenez la "
                         "contre-cotation finale.")
        if (qid != rfq.selected_quote_id
                and not requested_fields & {
                    "selection_reason_code", "selection_reason_note"}):
            # Un motif explique UNE décision de sélection. Le conserver en
            # changeant de réponse retenue attribuerait au nouveau choix la
            # justification de l'ancien, ce qui est pire qu'un motif absent.
            rfq.selection_reason_code = None
            rfq.selection_reason_note = None
        rfq.selected_quote_id = qid
        rfq.selected_quote_revision = q.revision if qid is not None else None
        if qid is None:
            rfq.selection_reason_code = None
            rfq.selection_reason_note = None
    selection_reason_fields = {"selection_reason_code", "selection_reason_note"}
    if requested_fields & selection_reason_fields:
        reason_code = data.pop(
            "selection_reason_code", rfq.selection_reason_code)
        reason_note = data.pop(
            "selection_reason_note", rfq.selection_reason_note)
        if rfq.selected_quote_id is None and (reason_code or reason_note):
            raise HTTPException(
                422, "Un motif de sélection exige d'abord une réponse retenue.")
        rfq.selection_reason_code = _clean_optional(reason_code)
        rfq.selection_reason_note = _clean_optional(reason_note)
    if "status" in data:
        _refuse_if_booked(rfq, session, "le statut")
        want = data.pop("status")
        if want not in _SETTABLE_STATUSES:
            raise HTTPException(
                422, "Le statut se déduit du déroulé de l'AO — seul « sans_suite » se pose "
                     "à la main, « auto » le rend à la déduction.")
        exchange_round = rfq_exchange.round_for(session, rfq_id)
        if want == 'auto' and exchange_round and (
                exchange_round.state != 'OPEN' or rfq.status in _TERMINAL_STATUSES):
            raise HTTPException(409, "Ce tour est clôturé ; ouvrez un nouveau tour lié.")
        if want == 'sans_suite':
            rfq_exchange.close_round(session, rfq, current)
        rfq.status = "sans_suite" if want == "sans_suite" else "draft"
    data.pop('expected_quote_revision', None)
    for field, value in data.items():
        if value is not None:
            setattr(rfq, field, value)
    _sync_status(rfq, session)
    rfq.updated_at = datetime.utcnow()
    session.add(rfq)
    critical = requested_fields & (
        {"params", "model_price", "selected_quote_id", "status",
         "selection_reason_code", "selection_reason_note"}
        | _COMMERCIAL_CONTEXT_FIELDS | _LEGAL_CONTEXT_FIELDS)
    if critical:
        if context_changes:
            action = "RFQ_COMMERCIAL_CONTEXT_CHANGED"
        elif legal_changes:
            action = "RFQ_LEGAL_CONTEXT_CHANGED"
        elif "selected_quote_id" in requested_fields:
            action = "QUOTE_SELECTED" if rfq.selected_quote_id else "QUOTE_DESELECTED"
        elif requested_fields & selection_reason_fields:
            action = "QUOTE_SELECTION_EXPLAINED"
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
    _sync_product_rfq(
        session, rfq, current, action="PRODUCT_RFQ_UPDATED", product=product,
        update_context=context_requested or nominal_changed)
    session.commit()
    return _rfq_row(rfq, _get_quotes(rfq_id, session), _counterparty_by_provider(session),
                    _booked_deals_by_rfq(session, current.id), session=session, current=current)


@router.delete("/{rfq_id}", status_code=204)
def delete_rfq(
    rfq_id: int,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    rfq = _get_owned(rfq_id, current, session, "organize")
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
    if rfq_exchange.round_for(session, rfq_id):
        raise HTTPException(409, "Un tour figé conserve sa preuve et ne peut pas être supprimé")
    if rfq_execution.workspace(session, rfq_id):
        raise HTTPException(409, "La RFQ conserve ses preuves de traitement et ne peut pas être supprimée")
    link = session.get(RfqRoundLink, rfq_id)
    if link:
        session.delete(link)
    product = load_product(session, rfq.product_id) if rfq.product_id else None
    for q in _get_quotes(rfq_id, session):
        session.delete(q)
    if ownership(session, rfq_id) is not None:
        for share in session.exec(select(RfqDeskShare).where(RfqDeskShare.rfq_id == rfq_id)).all():
            session.delete(share)
        session.delete(ownership(session, rfq_id))
    from ..db.models import RfqBookingEvidence
    evidence = session.get(RfqBookingEvidence, rfq_id)
    if evidence:
        session.delete(evidence)
    session.flush()
    session.delete(rfq)
    session.flush()
    if product is not None:
        remaining = tuple(
            item for item in product.rfqs if item.to_dict().get("id") != rfq_id)
        stage_revision(
            session, product.model_copy(update={"rfqs": remaining}),
            expected_revision=product.revision, actor_id=current.id,
            action="PRODUCT_RFQ_REMOVED",
            reason=f"Suppression de la RFQ {rfq.reference} non bookée.",
        )
    session.commit()


@router.post("/{rfq_id}/quotes", status_code=201)
def add_quote(
    rfq_id: int,
    body: QuoteCreate,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    rfq = _get_owned(rfq_id, current, session, "prepare")
    if ownership(session, rfq_id):
        rfq = lock_rfq_organization(session, rfq_id, current, "prepare")
        existing_round = rfq_exchange.round_for(session, rfq_id)
        if existing_round and existing_round.state != "OPEN":
            raise HTTPException(409, "Ce tour est clôturé")
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
    if ownership(session, rfq_id):
        product = _rfq_product(rfq, rfq.product_terms_version, current, session)
        shared, _ = _shared_rfq_request(rfq, product, rfq.payoff_family or "Produit structuré", None, current, session)
        rfq_exchange.freeze(session, rfq, shared, current)
    from ..services.legal_identity import provider_identity, active_counterparty
    directory_provider, legal = provider_identity(session, provider, body.provider_id)
    if body.counterparty_id is not None:
        requested = active_counterparty(session, body.counterparty_id)
        if directory_provider and directory_provider.counterparty_id is not None and directory_provider.counterparty_id != requested.id:
            raise HTTPException(422, "La contrepartie diffère du rattachement explicite du fournisseur.")
        legal = requested
    q = RfqQuote(
        id=next_audited_id(session, RfqQuote, "RFQ_QUOTE"),
        rfq_id=rfq_id,
        currency=rfq_quote_integrity.request_currency(session, rfq),
        provider=provider,
        provider_id=directory_provider.id if directory_provider else None,
        counterparty_id=legal.id if legal else None,
        counterparty_name=legal.name if legal else None,
        identity_frozen=True,
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
    _sync_product_rfq(session, rfq, current, action="PRODUCT_RFQ_QUOTE_SOLICITED")
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
    rfq = lock_rfq_organization(session, rfq_id, current, "prepare")
    q = session.get(RfqQuote, quote_id)
    if not q or q.rfq_id != rfq_id:
        raise HTTPException(404, "Quote introuvable")
    if rfq_publication.publication_for_quote(session, quote_id):
        raise HTTPException(409, "La cotation réseau publiée est immuable ; demandez une révision à la banque")
    from ..services.rfq_quote_integrity import clear_selection, request_currency, effective_currency
    before_audit = _quote_row(q, _counterparty_by_provider(session))
    before_audit["model_reference"] = json.loads(q.model_reference_json) if q.model_reference_json else None
    before_decision = _rfq_audit_state(rfq)
    data = body.model_dump(exclude_unset=True)
    expected_revision = data.pop('expected_revision', None)
    if expected_revision is not None and expected_revision != q.revision:
        raise HTTPException(409, "La cotation a changé ; rechargez sa révision avant de la modifier.")
    exchange_round = rfq_exchange.round_for(session, rfq_id)
    if set(data) - {'note'} and (rfq.status in _TERMINAL_STATUSES or (
            exchange_round and exchange_round.state != 'OPEN')):
        raise HTTPException(409, "Ce tour est clôturé ; ouvrez un nouveau tour lié.")
    rfq_execution.protect_mutation(session, rfq_id, set(data) - {"note"}, quote_id)
    if "counterparty_id" in data:
        from ..services.legal_identity import active_counterparty
        legal = active_counterparty(session, data.pop("counterparty_id"))
        if q.identity_frozen and q.counterparty_id is not None and q.counterparty_id != legal.id:
            raise HTTPException(409, "Une cotation historisée ne peut pas changer de banque ; ouvrez une nouvelle cotation.")
        if not (body.identity_reason or "").strip() or len(body.identity_reason.strip()) < 3:
            raise HTTPException(422, "Motif explicite requis pour qualifier l'identité juridique.")
        _refuse_if_booked(rfq, session, "l'identité juridique")
        if not q.identity_frozen or q.counterparty_id is None:
            q.counterparty_id, q.counterparty_name = legal.id, legal.name
        q.identity_frozen = True
        record_audit_event(session, action="QUOTE_LEGAL_IDENTITY_QUALIFIED", object_type="RFQ_QUOTE", object_id=q.id,
                           actor_user_id=current.id, result="SUCCESS", before=before_audit,
                           after=_quote_row(q), reason=body.identity_reason.strip())
    data.pop("identity_reason", None)
    if 'currency' in data or 'price' in data:
        raw_currency = data['currency'] if 'currency' in data else q.currency
        data['currency'] = str(raw_currency or '').strip().upper() or request_currency(session, rfq)
        if len(data['currency']) != 3 or not data['currency'].isascii() or not data['currency'].isalpha():
            raise HTTPException(422, "La devise doit être un code de trois lettres.")
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
            data["quoted_at"] = business_now()
    if "quoted_at" in data:
        data["quoted_at"] = _parse_utc_datetime(data["quoted_at"], "quoted_at")
    if "valid_until" in data:
        data["valid_until"] = _parse_utc_datetime(data["valid_until"], "valid_until")
    received_at = data.get("quoted_at", q.quoted_at)
    valid_until = data.get('valid_until', q.valid_until)
    if valid_until is not None and received_at is not None and valid_until <= received_at:
        raise HTTPException(422, "valid_until doit être postérieure à l'heure de la cotation.")
    if q.parent_quote_id is not None and data.get('status', q.status) == 'recu':
        parent = session.get(RfqQuote, q.parent_quote_id)
        price = data.get('price', q.price)
        currency = data.get('currency', effective_currency(session, rfq, q))
        if not parent or parent.price is None or price is None or not _improves(price, parent.price, rfq.sens) \
                or currency != effective_currency(session, rfq, parent):
            raise HTTPException(422, "Le last look doit améliorer l'originale dans la même devise ; requalifiez son prix.")
    material_changed = any(getattr(q, key) != value for key, value in data.items() if key != 'note')
    material_changed = material_changed or ('last_look' in data and data['last_look'] != q.last_look)
    identity_changed = (before_audit['counterparty_id'], before_audit['identity_status']) != (
        q.counterparty_id if q.identity_frozen else None, 'FROZEN' if q.identity_frozen and q.counterparty_id else 'TO_QUALIFY')
    material_changed = material_changed or identity_changed

    if "last_look" in data:
        want = data.pop("last_look")
        if q.parent_quote_id is not None:
            raise HTTPException(
                422, "Un last look est une contre-cotation finale et ne peut pas "
                     "engendrer un nouveau last look.")
        if want and data.get('price', q.price) is None:
            raise HTTPException(
                422, "Un last look ne peut être demandé qu'après réception d'un prix initial.")
        child = session.exec(
            select(RfqQuote).where(RfqQuote.parent_quote_id == quote_id)
        ).first()
        if want and not child:
            child = RfqQuote(id=next_audited_id(session, RfqQuote, "RFQ_QUOTE"),
                             rfq_id=rfq_id, provider=q.provider, contact=q.contact,
                             provider_id=q.provider_id, counterparty_id=q.counterparty_id,
                             counterparty_name=q.counterparty_name, identity_frozen=q.identity_frozen,
                             currency=data.get('currency', effective_currency(session, rfq, q)),
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
    if "price" in data and before_audit['price'] != q.price:
        from ..services.rfq_model_reference import snapshot
        q.model_reference_json = snapshot(session, rfq) if q.price is not None else None
    if material_changed:
        q.revision += 1
    if rfq.selected_quote_id == q.id and material_changed:
        clear_selection(rfq)
        session.add(rfq)
    if q.parent_quote_id is not None and q.price is not None \
            and rfq.selected_quote_id == q.parent_quote_id:
        # The answered counter-quote replaces its parent.  Never leave the
        # tender pointing at a response that its own history marks superseded.
        clear_selection(rfq)
        session.add(rfq)
    if q.parent_quote_id is None and material_changed:
        for child in session.exec(select(RfqQuote).where(RfqQuote.parent_quote_id == q.id)).all():
            if child.status == 'recu' and child.price is not None and (
                    q.price is None or not _improves(child.price, q.price, rfq.sens)
                    or effective_currency(session, rfq, child) != effective_currency(session, rfq, q)):
                old = _quote_row(child)
                child.status = 'expire'
                child.revision += 1
                if rfq.selected_quote_id == child.id:
                    clear_selection(rfq)
                session.add(child)
                record_audit_event(session, action='QUOTE_LAST_LOOK_INVALIDATED', object_type='RFQ_QUOTE',
                    object_id=child.id, actor_user_id=current.id, result='SUCCESS', before=old,
                    after=_quote_row(child), reason="La révision de l'originale exige une nouvelle contre-cotation.")
    session.add(q)
    # A price arriving (or being cleared) is what moves the tender from
    # "envoyée" to "cotée" and back.
    _sync_status(rfq, session)
    if material_changed:
        record_audit_event(
            session,
            action="QUOTE_UPDATED",
            object_type="RFQ_QUOTE",
            object_id=q.id,
            actor_user_id=current.id,
            result="SUCCESS",
            before=before_audit,
            after={**_quote_row(q, _counterparty_by_provider(session)),
                   "model_reference": json.loads(q.model_reference_json) if q.model_reference_json else None},
            reason="Mise à jour d'une donnée de cotation.",
            metadata={"fields": sorted(audited_fields), "revision":q.revision},
        )
    if before_decision['selected_quote_id'] is not None and rfq.selected_quote_id is None:
        record_audit_event(session, action='QUOTE_SELECTION_INVALIDATED', object_type='RFQ', object_id=rfq.id,
            actor_user_id=current.id, result='SUCCESS', before=before_decision, after=_rfq_audit_state(rfq),
            reason='La révision de la cotation ou de son last look exige une nouvelle décision explicite.')
    if material_changed or ('note' in data and before_audit['note'] != q.note):
        _sync_product_rfq(session, rfq, current, action="PRODUCT_RFQ_QUOTE_UPDATED")
    session.commit()
    result = _quote_row(q, _counterparty_by_provider(session), session=session)
    quotes = _get_quotes(rfq_id, session)
    superseded = superseded_quote_ids(quotes)
    result['rfq_state'] = {
        'id':rfq.id, 'status':rfq.status, 'selected_quote_id':rfq.selected_quote_id,
        'business_status':_rfq_row(rfq, quotes, session=session, current=current)['business_status'],
        'selected_quote_revision':rfq.selected_quote_revision,
        'selection_reason_code':rfq.selection_reason_code, 'selection_reason_note':rfq.selection_reason_note,
        'quotes':[{key:value for key,value in _quote_row(item, superseded=item.id in superseded, session=session).items()
                   if key in {'id','revision','status','superseded','comparable'}} for item in quotes],
    }
    return result


@router.delete("/{rfq_id}/quotes/{quote_id}", status_code=204)
def delete_quote(
    rfq_id: int,
    quote_id: int,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    rfq = lock_rfq_organization(session, rfq_id, current, "prepare")
    q = session.get(RfqQuote, quote_id)
    if not q or q.rfq_id != rfq_id:
        raise HTTPException(404, "Quote introuvable")
    if rfq_publication.publication_for_quote(session, quote_id):
        raise HTTPException(409, "Une publication réseau conserve son historique ; la banque peut la retirer")
    _refuse_if_booked(rfq, session, "la suppression d'une cotation")
    exchange_round = rfq_exchange.round_for(session, rfq_id)
    if rfq.status in _TERMINAL_STATUSES or (exchange_round and exchange_round.state != "OPEN"):
        raise HTTPException(409, "Ce tour est clôturé ; ouvrez un nouveau tour lié.")
    rfq_execution.protect_mutation(session, rfq_id, {"delete"}, quote_id)
    child = session.exec(select(RfqQuote).where(RfqQuote.parent_quote_id == quote_id)).first()
    ids_removed = {quote_id} | ({child.id} if child else set())
    if rfq.selected_quote_id in ids_removed:
        rfq_quote_integrity.clear_selection(rfq)
        session.add(rfq)
        session.flush()
    if child:
        # SQLite checks the self-reference immediately, before parent deletion.
        session.delete(child)
        session.flush()
    session.delete(q)
    _sync_status(rfq, session)
    _sync_product_rfq(session, rfq, current, action="PRODUCT_RFQ_QUOTE_REMOVED")
    session.commit()


from ..services.rfq_booking import ReviewBooking


@router.get("/{rfq_id}/booking-review")
def review_rfq_booking(rfq_id: int, current: Annotated[User, Depends(get_current_user)],
                       session: Annotated[Session, Depends(get_session)]):
    from ..services.rfq_booking import review
    return review(session, rfq_id, current)


@router.post("/{rfq_id}/book", status_code=201)
def book_reviewed_rfq(rfq_id: int, body: ReviewBooking,
                      current: Annotated[User, Depends(get_current_user)],
                      session: Annotated[Session, Depends(get_session)]):
    from ..services.rfq_booking import book
    from .deals import _book_deal
    try:
        return book(session, rfq_id, current, body, book_deal=_book_deal)
    except HTTPException:
        session.rollback()
        raise
