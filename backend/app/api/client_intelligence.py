"""Client Intelligence — les lectures analytiques.

Endpoints en lecture seule : ce module ne modifie rien, il agrège. Le
cloisonnement par entité est vérifié ici comme ailleurs — une lecture est aussi
une fuite si elle traverse la frontière.

`asof` est exposé sur chaque route. Ce n'est pas un confort de test : rejouer
une analyse à une date passée est la seule façon de vérifier qu'un signal levé
la semaine dernière l'était à raison.
"""
from __future__ import annotations

from datetime import date
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select

from ..core.client_cycle import compute_cycle, default_lead_days
from ..core.client_intelligence import (
    _dates_de_trade, affiliation_ids_of_person, client_intelligence,
    deals_of_affiliations, observed_behaviour, person_intelligence,
)
from ..core.client_signals import build_signals, maturity_horizon_days, stale_after_days
from ..db.database import get_session
from ..db.models import Affiliation, Client, ClientMandate, Person, User
from .auth import get_current_user

router = APIRouter(prefix="/api/client-intelligence", tags=["client-intelligence"])


def _asof(valeur: Optional[str]) -> date:
    if not valeur:
        return date.today()
    try:
        return date.fromisoformat(valeur)
    except ValueError:
        raise HTTPException(422, "asof doit être une date ISO (AAAA-MM-JJ).")


@router.get("/clients/{client_id}")
def lecture_client(
    client_id: int,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    asof: Optional[str] = Query(None),
    mandate_id: Optional[int] = Query(None),
    affiliation_id: Optional[int] = Query(None),
    include_demo: Optional[bool] = Query(None),
):
    client = session.get(Client, client_id)
    if client is None or client.entity_id != current.entity_id:
        raise HTTPException(404, "Client introuvable")
    if mandate_id is not None:
        mandate = session.get(ClientMandate, mandate_id)
        if mandate is None or mandate.client_id != client.id:
            raise HTTPException(404, "Mandat introuvable")
    if affiliation_id is not None:
        affiliation = session.get(Affiliation, affiliation_id)
        if affiliation is None or affiliation.client_id != client.id:
            raise HTTPException(404, "Affiliation introuvable")
    return client_intelligence(
        session, client_id, asof=_asof(asof), mandate_id=mandate_id,
        affiliation_id=affiliation_id, include_demo=include_demo)


@router.get("/persons/{person_id}")
def lecture_personne(
    person_id: int,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    asof: Optional[str] = Query(None),
):
    personne = session.get(Person, person_id)
    if personne is None or personne.entity_id != current.entity_id:
        raise HTTPException(404, "Personne introuvable")
    return person_intelligence(session, person_id, asof=_asof(asof))


@router.get("/affiliations/{affiliation_id}")
def lecture_affiliation(
    affiliation_id: int,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    asof: Optional[str] = Query(None),
):
    """Le comportement d'une personne DANS une société donnée.

    Distinct de sa lecture personnelle : c'est la comparaison des deux qui dit
    si quelqu'un garde ses habitudes en changeant de maison.
    """
    affiliation = session.get(Affiliation, affiliation_id)
    if affiliation is None:
        raise HTTPException(404, "Affiliation introuvable")
    client = session.get(Client, affiliation.client_id)
    if client is None or client.entity_id != current.entity_id:
        raise HTTPException(404, "Affiliation introuvable")

    deals = deals_of_affiliations(session, [affiliation_id])
    return {
        "affiliation_id": affiliation_id,
        "person_id": affiliation.person_id,
        "client_id": affiliation.client_id,
        "cycle": compute_cycle(_dates_de_trade(deals), asof=_asof(asof)).as_dict(),
        "behaviour": observed_behaviour(deals),
    }


@router.get("/signals")
def signaux(
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    asof: Optional[str] = Query(None),
    mine_only: bool = Query(True, description="Mes dossiers seulement"),
):
    liste = build_signals(session, entity_id=current.entity_id,
                          user_id=current.id if mine_only else None,
                          asof=_asof(asof))
    return {
        "signals": [s.as_dict() for s in liste],
        # Les seuils sont rendus avec les signaux : un utilisateur qui voit
        # « en sommeil » doit pouvoir savoir depuis quand on considère qu'un
        # dossier dort, sans aller lire le code.
        "thresholds": {
            "opportunity_stale_days": stale_after_days(),
            "lifecycle_event_horizon_days": maturity_horizon_days(),
            # Compatibility for consumers deployed before Client Lot 3.
            "maturity_horizon_days": maturity_horizon_days(),
            "default_contact_lead_days": default_lead_days(),
        },
    }


@router.get("/analytics")
def analytiques(
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    asof: Optional[str] = Query(None),
):
    """Les chiffres du portefeuille commercial.

    Volontairement peu nombreux. Un tableau de bord qui affiche quinze
    graphiques ne se lit pas : chaque métrique ici répond à une question qu'un
    commercial se pose vraiment, et celles qui n'ont pas assez de matière pour
    être honnêtes rendent `null` plutôt qu'un zéro trompeur.
    """
    from ..core.client_cycle import observed_lead_days
    from ..core.client_intelligence import _date_iso, lead_time_pairs
    from ..db.models import Deal, Interaction, Opportunity

    jour = _asof(asof)

    clients = list(session.exec(
        select(Client).where(Client.entity_id == current.entity_id)).all())
    actifs = [c for c in clients if c.status == "active"]
    dormants = [c for c in clients if c.status in ("dormant", "inactive")]

    personnes = list(session.exec(
        select(Person).where(Person.entity_id == current.entity_id,
                             Person.is_active.is_(True))).all())
    en_poste = {a.person_id for a in session.exec(
        select(Affiliation).where(Affiliation.end_date.is_(None))).all()}

    opportunites = list(session.exec(
        select(Opportunity).where(Opportunity.entity_id == current.entity_id)).all())
    TERMINAUX = {"won", "lost", "cancelled", "archived"}
    ouvertes = [o for o in opportunites if o.status not in TERMINAUX]
    gagnees = [o for o in opportunites if o.status == "won"]
    perdues = [o for o in opportunites if o.status == "lost"]

    # Taux de conversion : sur les dossiers TRANCHÉS seulement. Inclure les
    # dossiers encore ouverts au dénominateur ferait baisser le taux à mesure
    # qu'on prospecte, ce qui punirait exactement le bon comportement.
    tranchees = len(gagnees) + len(perdues)
    conversion = (len(gagnees) / tranchees) if tranchees else None

    motifs = {}
    for opportunite in perdues:
        if opportunite.lost_reason:
            motifs[opportunite.lost_reason] = motifs.get(opportunite.lost_reason, 0) + 1

    # Les transactions de TOUTES origines — trades bookés ici ET historique
    # versé. Ne compter que les Deals ferait dire « 0 transaction » à cet écran
    # pendant que la fiche client en affiche quatre : deux vérités pour un même
    # portefeuille, et personne pour savoir laquelle croire.
    #
    # En deux requêtes, pas une par client : boucler ici coûtait 62 requêtes
    # pour 31 clients, et le coût grandit avec le portefeuille — donc il ne se
    # voit jamais avant la mise en service.
    from ..core.client_intelligence import transactions_of_entity
    deals = transactions_of_entity(session, current.entity_id)

    # Délai entre ouverture du dossier et transaction — médiane, comme partout.
    delais = []
    for deal in deals:
        trade = _date_iso(deal.trade_date)
        if trade is None or deal.opportunity_id is None:
            continue
        opportunite = session.get(Opportunity, deal.opportunity_id)
        if opportunite and opportunite.created_at:
            ecart = (trade - opportunite.created_at.date()).days
            if ecart >= 0:
                delais.append(float(ecart))
    delai_median = None
    if delais:
        tries = sorted(delais)
        n = len(tries)
        delai_median = (tries[n // 2] if n % 2
                        else (tries[n // 2 - 1] + tries[n // 2]) / 2.0)

    lead_median = observed_lead_days(lead_time_pairs(session, deals))

    par_produit = {}
    for deal in deals:
        cle = deal.product_type or "(non renseigné)"
        par_produit[cle] = par_produit.get(cle, 0) + 1
    importees = sum(1 for d in deals if d.imported)

    return {
        "asof": jour.isoformat(),
        "clients": {"total": len(clients), "active": len(actifs),
                    "dormant": len(dormants)},
        "contacts": {"total": len(personnes),
                     "affiliated": len([p for p in personnes if p.id in en_poste])},
        "opportunities": {
            "open": len(ouvertes), "won": len(gagnees), "lost": len(perdues),
            "pipeline_amount": sum(o.amount or 0 for o in ouvertes),
            # None et non 0 : sans dossier tranché, le taux n'existe pas.
            "conversion_rate": conversion,
            "decided": tranchees,
        },
        "lost_reasons": sorted(motifs.items(), key=lambda kv: -kv[1]),
        "trades": {
            "total": len(deals),
            # Rendu à part : une lecture fondée surtout sur de l'historique
            # versé n'a pas la même valeur de preuve qu'une lecture fondée sur
            # nos propres bookings, et l'écran doit pouvoir le dire.
            "imported": importees,
            "by_product": sorted(par_produit.items(), key=lambda kv: -kv[1]),
        },
        "timing": {
            "median_opportunity_to_trade_days": delai_median,
            "median_discussion_lead_days": lead_median,
        },
    }


@router.get("/overview")
def apercu(
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    asof: Optional[str] = Query(None),
):
    """Ce qu'il y a à faire ce matin, groupé par nature.

    L'écran d'accueil du module ne cherche pas à tout montrer : il répond à
    « par quoi je commence », ce qui suppose de trier, pas d'énumérer.
    """
    jour = _asof(asof)
    liste = build_signals(session, entity_id=current.entity_id,
                          user_id=current.id, asof=jour)
    groupes: dict[str, list] = {}
    for signal in liste:
        groupes.setdefault(signal.kind, []).append(signal.as_dict())
    return {
        "asof": jour.isoformat(),
        "by_kind": groupes,
        "counts": {kind: len(items) for kind, items in groupes.items()},
        "total": len(liste),
    }
