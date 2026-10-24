"""Resolve local legal IDs; labels describe identities and never replace them."""
from fastapi import HTTPException
import unicodedata
from sqlmodel import select
from ..db.models import Counterparty, RfqProvider, RfqRelationshipSide, RfqSolicitation, RfqQuote


def active_counterparty(session, counterparty_id):
    item = session.get(Counterparty, counterparty_id) if counterparty_id is not None else None
    if not item or not item.active:
        raise HTTPException(422, "Identifiant de contrepartie juridique actif requis ; qualifiez le référentiel.")
    return item


def booking_exception(session, user, body):
    """Validate an explicit administrator attestation, never a general credit override."""
    from ..core.access import require_capability
    require_capability(user, "organization.admin")
    if body.counterparty_id is not None or body.ccr_netting_set_id is not None:
        raise HTTPException(422, "L’exception concerne uniquement une contrepartie hors référentiel, sans netting set.")
    if body.rfq_id is not None or body.execution_agreement_id is not None:
        raise HTTPException(422, "Qualifiez la contrepartie sur la RFQ ; l’exception ne remplace pas son identité juridique.")
    reason = str(body.legal_identity_exception.reason or "").strip()
    name = str(body.contrepartie or "").strip()
    if not 10 <= len(reason) <= 2000:
        raise HTTPException(422, "Motivez explicitement l’exception juridique (10 à 2 000 caractères).")
    if not 2 <= len(name) <= 200 or any(unicodedata.category(c).startswith("C") for c in name):
        raise HTTPException(422, "Saisissez le nom juridique de la contrepartie (2 à 200 caractères).")
    def normalized(value):
        return " ".join(unicodedata.normalize("NFKC", value).casefold().split())
    # Include inactive entries: an exception must not reactivate an excluded bank.
    if any(normalized(item.name) == normalized(name) for item in session.exec(select(Counterparty)).all()):
        raise HTTPException(422, "Cette contrepartie existe déjà ; utilisez son identifiant actif ou qualifiez le référentiel.")
    return {"counterparty_name": name, "reason": reason, "credit_status": "NOT_ASSESSED",
            "requires_legal_qualification": True}


def provider_identity(session, label, provider_id=None):
    if provider_id is not None:
        provider = session.get(RfqProvider, provider_id)
        if not provider or not provider.active or provider.label != label:
            raise HTTPException(422, "Fournisseur actif et libellé concordant requis.")
    else:
        candidates = session.exec(select(RfqProvider).where(RfqProvider.label == label)).all()
        if candidates and (len(candidates) != 1 or not candidates[0].active):
            raise HTTPException(422, "Fournisseur inactif ou ambigu ; qualifiez le référentiel.")
        provider = candidates[0] if len(candidates) == 1 and candidates[0].active else None
    if not provider:
        return None, None
    if provider.counterparty_id is not None:
        item = session.get(Counterparty, provider.counterparty_id)
        return provider, item if item and item.active else None
    candidates = session.exec(select(Counterparty).where(Counterparty.name == label, Counterparty.active == True)).all()
    return provider, candidates[0] if len(candidates) == 1 else None


def network_counterparty(session, rfq, published):
    quote = session.get(RfqQuote, published.quote_id)
    if quote and quote.identity_frozen:
        return active_counterparty(session, quote.counterparty_id)
    solicitation = session.get(RfqSolicitation, published.solicitation_id)
    return relation_counterparty(session, rfq, solicitation)


def relation_counterparty(session, rfq, solicitation):
    side = session.exec(select(RfqRelationshipSide).where(
        RfqRelationshipSide.relationship_id == solicitation.relationship_id,
        RfqRelationshipSide.entity_id == rfq.entity_id)).first() if solicitation else None
    return active_counterparty(session, side.counterparty_id if side else None)


def quote_counterparty(session, quote):
    # Legacy quotes without a frozen ID need explicit desk qualification.
    if not quote.identity_frozen:
        raise HTTPException(422, "Identité juridique historique à qualifier explicitement sur la cotation.")
    return active_counterparty(session, quote.counterparty_id)
