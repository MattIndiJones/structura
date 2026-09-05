"""Signaux commerciaux — ce qu'il y a à faire aujourd'hui.

Six types, pas davantage. Multiplier les catégories fabrique du bruit, et un
tableau de bord qui signale tout ne signale rien.

Chaque signal porte sa raison en clair. C'est la même règle que partout dans ce
module : un chiffre qu'on ne peut pas justifier n'aurait pas dû être affiché, et
un signal qu'on ne peut pas expliquer n'aurait pas dû être levé.

Sur les événements produits (§52) : ce module ne calcule AUCUNE probabilité de
rappel. Il lit la prochaine constatation que le cycle de vie connaît déjà.
Inventer « autocall probable » demanderait un modèle que rien ici ne porte, et
une probabilité fausse est pire qu'une absence d'information.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, asdict
from datetime import date, timedelta
from typing import Optional

from sqlmodel import Session, select

from ..db.models import (
    Affiliation, Client, ClientTradeHistory, Deal, DealEvent, Interaction,
    Opportunity, Person,
)
from .client_cycle import (
    CONFIANCE_BASSE, compute_cycle, recommend_contact_window,
)
from .client_intelligence import (
    _dates_de_trade, _date_iso, affiliation_ids_of_person, deals_of_affiliations,
    deals_of_client, lead_time_pairs, transactions_by_client,
)
from .client_cycle import observed_lead_days

CONTACT_SOON = "contact_soon"
PREPARE_IDEA = "prepare_idea"
FOLLOW_UP_DUE = "follow_up_due"
DORMANT = "dormant"
UPCOMING_LIFECYCLE_EVENT = "upcoming_lifecycle_event"
# Compatibility for internal callers/tests written before Lot 3.  The signal
# family stays unique; its scope is now the next contractual lifecycle event,
# of which maturity is one possible case.
UPCOMING_MATURITY = UPCOMING_LIFECYCLE_EVENT
OPPORTUNITY_STALE = "opportunity_stale"


def stale_after_days() -> int:
    """Au bout de combien de jours sans activité une opportunité est en sommeil.

    Configurable : un flux institutionnel se relance en deux semaines, un dossier
    de banque privée peut légitimement dormir un mois entre deux comités.
    """
    try:
        return max(1, int(os.getenv("STRUCTURA_OPPORTUNITY_STALE_DAYS", "21")))
    except ValueError:
        return 21


def maturity_horizon_days() -> int:
    try:
        return max(1, int(os.getenv("STRUCTURA_MATURITY_HORIZON_DAYS", "60")))
    except ValueError:
        return 60


@dataclass
class Signal:
    kind: str
    severity: str            # info | warning | urgent
    title: str
    reason: str
    client_id: Optional[int] = None
    client_name: Optional[str] = None
    person_id: Optional[int] = None
    person_name: Optional[str] = None
    opportunity_id: Optional[int] = None
    deal_id: Optional[int] = None
    deal_event_id: Optional[int] = None
    mandate_id: Optional[int] = None
    origin: Optional[str] = None       # life_cycle | life_cycle_legacy | imported_history
    due_date: Optional[str] = None

    def as_dict(self) -> dict:
        return asdict(self)


def _nom_personne(session: Session, person_id: Optional[int]) -> Optional[str]:
    if person_id is None:
        return None
    personne = session.get(Person, person_id)
    return f"{personne.first_name} {personne.last_name}".strip() if personne else None


def build_signals(session: Session, *, entity_id: Optional[int],
                  user_id: Optional[int] = None,
                  asof: Optional[date] = None) -> list[Signal]:
    """Les signaux d'un utilisateur, du plus urgent au plus lointain."""
    asof = asof or date.today()
    signaux: list[Signal] = []

    clients = list(session.exec(
        select(Client).where(Client.entity_id == entity_id,
                             Client.status != "archived")).all())
    clients_par_id = {c.id: c for c in clients}

    # ── Relances échues ──────────────────────────────────────────────
    # Le signal le plus simple, et celui qu'on rate le plus : une action notée
    # sur une interaction, dont la date est arrivée.
    requete = select(Interaction).where(Interaction.entity_id == entity_id)
    if user_id is not None:
        requete = requete.where(Interaction.user_id == user_id)
    for interaction in session.exec(requete).all():
        echeance = _date_iso(interaction.next_action_date)
        if not interaction.next_action or echeance is None or echeance > asof:
            continue
        retard = (asof - echeance).days
        signaux.append(Signal(
            kind=FOLLOW_UP_DUE,
            severity="urgent" if retard > 7 else "warning",
            title=interaction.next_action,
            reason=(f"Échue depuis {retard} jour(s)." if retard
                    else "Échue aujourd'hui."),
            client_id=interaction.client_id,
            client_name=(clients_par_id.get(interaction.client_id).name
                         if interaction.client_id in clients_par_id else None),
            opportunity_id=interaction.opportunity_id,
            due_date=echeance.isoformat()))

    # ── Opportunités en sommeil ──────────────────────────────────────
    seuil_sommeil = stale_after_days()
    requete = select(Opportunity).where(Opportunity.entity_id == entity_id)
    if user_id is not None:
        requete = requete.where(Opportunity.owner_user_id == user_id)
    for opportunite in session.exec(requete).all():
        if opportunite.status in ("won", "lost", "cancelled", "archived"):
            continue
        derniere = (opportunite.last_activity_at or opportunite.updated_at)
        if derniere is None:
            continue
        inactif = (asof - derniere.date()).days
        if inactif < seuil_sommeil:
            continue
        signaux.append(Signal(
            kind=OPPORTUNITY_STALE, severity="warning",
            title=opportunite.title or opportunite.reference,
            reason=(f"Aucune activité depuis {inactif} jours "
                    f"(seuil {seuil_sommeil})."),
            client_id=opportunite.client_id,
            client_name=(clients_par_id.get(opportunite.client_id).name
                         if opportunite.client_id in clients_par_id else None),
            opportunity_id=opportunite.id))

    # ── Cadence : contact à prévoir, idée à préparer, client dormant ──
    # Toujours relatif à l'historique de CHAQUE client — un trimestriel muet
    # depuis 100 jours est normal, un mensuel ne l'est pas.
    # Tout chargé d'un coup, puis regroupé : une requête par client faisait
    # grandir le coût de cet écran avec le portefeuille, et un N+1 ne se voit
    # jamais tant qu'on développe sur trois clients.
    par_client = transactions_by_client(session, entity_id)
    for client in clients:
        deals = par_client.get(client.id, [])
        cycle = compute_cycle(_dates_de_trade(deals), asof=asof)
        if not cycle.has_history:
            continue

        if cycle.overdue:
            signaux.append(Signal(
                kind=DORMANT, severity="warning",
                title=f"{client.name} — activité inhabituellement faible",
                reason=(f"{cycle.days_since_last} jours depuis la dernière "
                        f"transaction, pour une cadence médiane de "
                        f"{round(cycle.median_interval_days)} jours."),
                client_id=client.id, client_name=client.name))
            continue

        # Une confiance basse produit une fenêtre volontairement large — jusqu'à
        # plus de deux mois sur un seul intervalle. En faire un signal URGENT
        # serait doublement faux : ce n'est pas une échéance, et la fiche client
        # refuse déjà d'en faire l'action du jour. Deux parties du même module
        # qui se contredisent apprennent à ignorer les deux.
        #
        # Trouvé en semant le jeu de démonstration sur une vraie base : la carte
        # se taisait, l'écran des signaux criait.
        if cycle.confidence == CONFIANCE_BASSE:
            continue

        delai = observed_lead_days(lead_time_pairs(session, deals))
        fenetre = recommend_contact_window(cycle, lead_days=delai)
        if not fenetre.start:
            continue
        debut = date.fromisoformat(fenetre.start)
        fin = date.fromisoformat(fenetre.end)

        if debut <= asof <= fin:
            signaux.append(Signal(
                kind=CONTACT_SOON, severity="urgent",
                title=f"{client.name} — fenêtre de contact ouverte",
                reason=(f"Transaction attendue entre le "
                        f"{cycle.expected_window_start} et le "
                        f"{cycle.expected_window_end} ; les discussions "
                        f"commencent {fenetre.lead_days} jours avant."),
                client_id=client.id, client_name=client.name,
                due_date=fenetre.end))
        elif asof < debut <= asof + timedelta(days=14):
            signaux.append(Signal(
                kind=PREPARE_IDEA, severity="info",
                title=f"{client.name} — préparer une idée",
                reason=(f"Fenêtre de contact à partir du {fenetre.start}, "
                        f"soit dans {(debut - asof).days} jours."),
                client_id=client.id, client_name=client.name,
                due_date=fenetre.start))

    # ── Prochains événements contractuels ───────────────────────────
    # DealEvent est la vérité du Life Cycle.  Client Intelligence ne recrée
    # ni calendrier, ni statut, ni probabilité : il projette seulement la
    # prochaine ligne encore future de chaque deal dans l'horizon commercial.
    horizon = maturity_horizon_days()
    requete = select(Deal).where(Deal.entity_id == entity_id,
                                 Deal.status == "actif")
    if user_id is not None:
        requete = requete.where(Deal.user_id == user_id)
    deals_lifecycle = [deal for deal in session.exec(requete).all()
                       if deal.client_id is not None]
    deal_ids = [deal.id for deal in deals_lifecycle if deal.id is not None]
    fin_horizon = asof + timedelta(days=horizon)
    prochains: dict[int, DealEvent] = {}
    deals_avec_calendrier: set[int] = set()
    if deal_ids:
        deals_avec_calendrier = set(session.exec(
            select(DealEvent.deal_id)
            .where(DealEvent.deal_id.in_(deal_ids))
            .distinct()
        ).all())
        evenements = session.exec(
            select(DealEvent)
            .where(DealEvent.deal_id.in_(deal_ids),
                   DealEvent.event_date >= asof.isoformat(),
                   DealEvent.event_date <= fin_horizon.isoformat(),
                   DealEvent.status == "futur")
            .order_by(DealEvent.event_date, DealEvent.event_index)
        ).all()
        for evenement in evenements:
            prochains.setdefault(evenement.deal_id, evenement)

    for deal in deals_lifecycle:
        evenement = prochains.get(deal.id)
        date_evenement = _date_iso(evenement.event_date) if evenement else None
        origine = "life_cycle"
        if evenement is None and deal.id not in deals_avec_calendrier:
            # Explicit compatibility path for old/manual deals created before
            # event generation existed.  Current bookings always have
            # DealEvent rows; the fallback must never outrank one.
            date_evenement = _date_iso(deal.maturity_date)
            origine = "life_cycle_legacy"
        if (date_evenement is None
                or not (asof <= date_evenement <= fin_horizon)):
            continue

        jours = (date_evenement - asof).days
        est_maturite = (
            evenement is None
            or date_evenement.isoformat() == deal.maturity_date
            or "matur" in (evenement.label or "").lower()
        )
        if est_maturite:
            titre = f"{deal.reference} — maturité le {date_evenement.isoformat()}"
            raison = (
                f"Échéance contractuelle dans {jours} jours, issue du "
                "calendrier Life Cycle."
            )
        else:
            libelle = (evenement.label or "Constatation").strip()
            titre = f"{deal.reference} — {libelle} le {date_evenement.isoformat()}"
            raison = (
                f"Constatation contractuelle dans {jours} jours, issue du "
                "calendrier Life Cycle. Le coupon ou le rappel éventuel "
                "dépendra du fixing et du script figé."
            )
        signaux.append(Signal(
            kind=UPCOMING_LIFECYCLE_EVENT, severity="info",
            title=titre, reason=raison,
            client_id=deal.client_id,
            client_name=(clients_par_id.get(deal.client_id).name
                         if deal.client_id in clients_par_id else None),
            opportunity_id=deal.opportunity_id,
            deal_id=deal.id,
            deal_event_id=evenement.id if evenement else None,
            mandate_id=deal.mandate_id,
            origin=origine,
            due_date=date_evenement.isoformat()))

    # Les maturités issues d'un historique versé comptent aussi. Nous ne
    # portons pas ces positions — mais le client, lui, va récupérer du cash à
    # cette date, et c'est un fait commercial, pas une position de risque. Le
    # message dit d'où vient l'information, pour qu'on n'aille pas la chercher
    # dans un book où elle n'est pas.
    for ligne in session.exec(
            select(ClientTradeHistory).where(
                ClientTradeHistory.entity_id == entity_id)).all():
        maturite = _date_iso(ligne.maturity_date)
        if maturite is None or not (asof <= maturite <= asof + timedelta(days=horizon)):
            continue
        libelle = ligne.product_type or "Produit"
        signaux.append(Signal(
            kind=UPCOMING_LIFECYCLE_EVENT, severity="info",
            title=f"{libelle} — maturité le {maturite.isoformat()}",
            reason=(f"Échéance dans {(maturite - asof).days} jours, d'après "
                    f"l'historique importé : ce n'est pas une position que nous "
                    f"portons, mais le client récupère du cash."),
            client_id=ligne.client_id,
            client_name=(clients_par_id.get(ligne.client_id).name
                         if ligne.client_id in clients_par_id else None),
            mandate_id=ligne.mandate_id,
            origin="imported_history",
            due_date=maturite.isoformat()))

    ordre = {"urgent": 0, "warning": 1, "info": 2}
    return sorted(signaux, key=lambda s: (ordre.get(s.severity, 9),
                                          s.due_date or "9999-12-31"))
