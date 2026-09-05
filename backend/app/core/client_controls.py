"""Règles d'intégrité de la couche commerciale — Client / Person / Affiliation.

Ce module porte les invariants qui ne doivent JAMAIS dépendre d'un écran. Le
principe est celui du reste de l'application : un contrôle d'interface se
contourne par un appel direct à l'API, donc tout ce qui protège un historique
se vérifie ici, côté serveur.

Trois invariants structurants :

1. **L'affiliation est le seul point d'ancrage temporel.** « Qui travaille où »
   ne se lit jamais sur la personne mais sur l'affiliation ouverte. Aucun code
   de ce module ne réaffecte le couple (person_id, client_id) d'une affiliation
   existante — c'est ce qui rend impossible qu'un trade de 2024 chez Bank A
   devienne un trade Bank B le jour d'un changement de poste.

2. **Un contact d'opportunité appartient au client de l'opportunité.** Vérifié
   à la création comme au changement de client (§29 de la mission), et vérifié
   ici plutôt que dans le routeur pour qu'aucun appelant ne puisse l'oublier.

3. **Un changement de société est une transaction ou n'est pas.** Clôturer sans
   rouvrir laisserait une personne sans employeur ; rouvrir sans clôturer lui
   en donnerait deux. Voir `change_company`.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date, datetime
from typing import Optional

from sqlmodel import Session, select

from ..db.models import (
    Affiliation, Client, ClientMandate, ClientPreferenceStatement,
    ClientTradeHistory, Deal, Interaction, Opportunity,
    OpportunityParticipant, Person,
)


# ── Erreurs métier ────────────────────────────────────────────────────
# Un IntegrityError brut ne dit rien à un commercial. Chaque refus porte un
# code stable (pour les tests et le frontend) et une phrase en français qui
# explique ce qui bloque, comme le fait déjà rfq_controls.ControlFailure.

@dataclass(frozen=True)
class ClientRuleError(Exception):
    code: str
    message: str

    def as_dict(self) -> dict:
        return asdict(self)

    def __str__(self) -> str:            # pragma: no cover - confort de debug
        return f"{self.code}: {self.message}"


# ── Vocabulaires ──────────────────────────────────────────────────────
# Listes fermées, validées côté serveur : un statut inventé par un appelant
# fausserait silencieusement tous les comptages de Client Intelligence.

CLIENT_TYPES = {
    "private_bank", "asset_manager", "family_office", "insurance", "corporate",
    "institutional", "distributor", "bank", "other",
}
CLIENT_STATUSES = {"prospect", "active", "dormant", "inactive", "archived"}
DATA_ORIGINS = {"demo", "imported", "native"}

COMMERCIAL_ROLES = {
    "decision_maker", "cio", "portfolio_manager", "investment_advisor",
    "influencer", "execution", "originator", "other",
}

INTERACTION_TYPES = {
    "call", "meeting", "email", "idea_sent", "client_feedback",
    "indicative_request", "follow_up", "other",
}

OPPORTUNITY_STATUSES = {
    "lead", "need_identified", "idea", "client_interest", "structuring",
    "rfq", "negotiation", "partially_won", "won", "lost", "cancelled", "archived",
}
# Un statut terminal ferme le dossier ; seul 'lost' exige un motif.
OPPORTUNITY_TERMINAL = {"won", "lost", "cancelled", "archived"}

LOST_REASONS = {
    "coupon_too_low", "barrier_too_high", "maturity_too_long", "issuer_rejected",
    "underlying_rejected", "product_complexity", "competitor",
    "client_changed_view", "timing", "internal_approval", "no_liquidity",
    "client_did_nothing", "other",
}

PARTICIPANT_ROLES = {
    "originator", "decision_maker", "influencer", "advisor", "execution", "other",
}

COVERAGE_ROLES = {"primary", "secondary", "read_only"}
MANDATE_TYPES = {"mandate", "fund", "account", "desk", "other"}
MANDATE_STATUSES = {"active", "archived"}


def _check_vocabulary(value: str, allowed: set[str], code: str, label: str) -> None:
    if value not in allowed:
        raise ClientRuleError(
            code=code,
            message=(f"{label} « {value} » inconnu. "
                     f"Valeurs acceptées : {', '.join(sorted(allowed))}."),
        )


def validate_client_type(value: str) -> None:
    _check_vocabulary(value, CLIENT_TYPES, "CLIENT_TYPE_INVALID", "Type de client")


def validate_client_status(value: str) -> None:
    _check_vocabulary(value, CLIENT_STATUSES, "CLIENT_STATUS_INVALID", "Statut de client")


def validate_data_origin(value: str) -> str:
    """La provenance est déclarée, jamais déduite du contenu de la fiche."""
    normalisee = str(value or "").strip().lower()
    _check_vocabulary(normalisee, DATA_ORIGINS, "DATA_ORIGIN_INVALID", "Provenance")
    return normalisee


def validate_commercial_role(value: str) -> None:
    _check_vocabulary(value, COMMERCIAL_ROLES, "ROLE_INVALID", "Rôle commercial")


def validate_interaction_type(value: str) -> None:
    _check_vocabulary(value, INTERACTION_TYPES, "INTERACTION_TYPE_INVALID",
                      "Type d'interaction")


def validate_opportunity_status(value: str) -> None:
    _check_vocabulary(value, OPPORTUNITY_STATUSES, "OPPORTUNITY_STATUS_INVALID",
                      "Statut d'opportunité")


def validate_coverage_role(value: str) -> None:
    _check_vocabulary(value, COVERAGE_ROLES, "COVERAGE_ROLE_INVALID",
                      "Rôle de couverture")


def validate_mandate_type(value: str) -> None:
    _check_vocabulary(value, MANDATE_TYPES, "MANDATE_TYPE_INVALID", "Type de mandat")


def validate_mandate_status(value: str) -> None:
    _check_vocabulary(value, MANDATE_STATUSES, "MANDATE_STATUS_INVALID",
                      "Statut de mandat")


# ── Contraintes institutionnelles ─────────────────────────────────────
# Échelle S&P / Fitch. Le RANG est ce qui compte : comparer deux notations
# par ordre alphabétique donnerait 'BBB' < 'A', donc l'inverse de la réalité.
# Un client qui exige au minimum 'A-' accepte tout ce dont le rang est
# inférieur ou égal au sien.

RATING_SCALE = (
    "AAA", "AA+", "AA", "AA-", "A+", "A", "A-",
    "BBB+", "BBB", "BBB-", "BB+", "BB", "BB-",
    "B+", "B", "B-", "CCC+", "CCC", "CCC-", "CC", "C", "D",
)
_RATING_RANK = {note: rang for rang, note in enumerate(RATING_SCALE)}


def rating_rank(rating: Optional[str]) -> Optional[int]:
    """Rang d'une notation (0 = AAA). None si inconnue ou absente."""
    if rating is None:
        return None
    return _RATING_RANK.get(str(rating).strip().upper())


def validate_rating(rating: Optional[str]) -> None:
    if rating is None or rating == "":
        return
    if rating_rank(rating) is None:
        raise ClientRuleError(
            code="RATING_INVALID",
            message=(f"Notation « {rating} » inconnue. Échelle acceptée : "
                     f"{', '.join(RATING_SCALE[:8])}…"),
        )


ASSET_CLASSES = {
    "equity", "rates", "credit", "fx", "commodity", "fund", "hybrid", "other",
}
PRODUCT_FAMILIES = {
    "autocall", "phoenix", "phoenix_memory", "reverse_convertible",
    "barrier_reverse_convertible", "capital_protected", "participation",
    "twin_win", "shark", "credit_linked", "callable_note",
    "structured_rates", "equity_swap", "rates_swap", "other",
}

# Le schéma du blob vit désormais dans `client_constraints_ref` : c'est le même
# objet qui décrit un champ standard et un champ ajouté par l'admin ou pour un
# client. Le tenir en double ici aurait laissé les deux dériver — et c'est
# exactement par une divergence entre deux chemins que ce module a déjà laissé
# passer ses vrais défauts.

def _convertir(erreur) -> "ClientRuleError":
    """Un refus du référentiel, rendu dans le contrat de ce module.

    Les appelants (routeurs, tests) attrapent `ClientRuleError` ; le référentiel
    lève sa propre erreur pour ne pas dépendre de ce module en retour. La
    conversion se fait ici, en un seul point.
    """
    return ClientRuleError(code=erreur.code, message=erreur.message)


def validate_constraints(constraints: dict, definitions=None) -> dict:
    """Valide le blob de contraintes et le rend normalisé.

    Refuse toute clé qu'aucune définition ne décrit plutôt que de l'accepter
    silencieusement : un champ mal orthographié qui se range à côté du bon est
    une contrainte qui ne s'applique jamais, et rien ne le signale.

    Sans `definitions`, seuls les champs standards sont connus — c'est le
    comportement d'origine, et celui de tout appelant qui n'a pas de session
    sous la main. Avec, les champs déclarés pour l'entité ou pour le client
    s'ajoutent à ce qui est connu. Le référentiel élargit le connu ; il
    n'ouvre pas la porte.
    """
    from .client_constraints_ref import (
        ConstraintRefError, _standards, validate_constraints_against,
    )
    try:
        return validate_constraints_against(
            constraints, definitions if definitions is not None else _standards())
    except ConstraintRefError as erreur:
        raise _convertir(erreur) from None


def validate_scalar_constraints(*, ticket_min: Optional[float],
                                ticket_max: Optional[float],
                                maturity_min_months: Optional[int],
                                maturity_max_months: Optional[int],
                                min_rating: Optional[str],
                                max_concentration_pct: Optional[float]) -> None:
    """Repères cohérents entre eux, même lorsqu'ils ne sont pas bloquants."""
    validate_rating(min_rating)
    for bas, haut, libelle in (
        (ticket_min, ticket_max, "Le ticket minimum"),
        (maturity_min_months, maturity_max_months, "La maturité minimale"),
    ):
        if bas is not None and haut is not None and bas > haut:
            raise ClientRuleError(
                code="CONSTRAINT_RANGE_INVALID",
                message=f"{libelle} dépasse le maximum : la fourchette est incohérente.",
            )
    for valeur, libelle in ((ticket_min, "ticket minimum"),
                            (ticket_max, "ticket maximum"),
                            (max_concentration_pct, "concentration maximale")):
        if valeur is not None and valeur < 0:
            raise ClientRuleError(
                code="CONSTRAINT_RANGE_INVALID",
                message=f"Le {libelle} ne peut pas être négatif.")
    if max_concentration_pct is not None and max_concentration_pct > 100:
        raise ClientRuleError(
            code="CONSTRAINT_RANGE_INVALID",
            message="La concentration maximale s'exprime en pourcentage (0 à 100).")


def require_constraints_version(client: Client, version_envoyee: Optional[int]) -> None:
    """Verrou optimiste sur le blob de contraintes.

    Deux utilisateurs qui éditent le même profil font tous deux un
    lire-modifier-réécrire de l'objet entier. Sans ce contrôle, le second
    écrase le premier sans erreur ni trace — exactement le genre de perte
    qui ne se découvre que le jour où une préférence disparaît de la fiche.

    Même mécanisme que Deal.contract_version sur les amendements : on refuse
    une écriture fondée sur une base périmée plutôt que de l'appliquer.
    """
    if version_envoyee is None:
        raise ClientRuleError(
            code="CONSTRAINTS_VERSION_REQUIRED",
            message=("Version du profil absente : rechargez la fiche avant "
                     "de l'enregistrer."),
        )
    if version_envoyee != client.constraints_version:
        raise ClientRuleError(
            code="CONSTRAINTS_VERSION_STALE",
            message=("Ces préférences ont été modifiées entre-temps par quelqu'un "
                     "d'autre. Rechargez la fiche pour repartir de la version à "
                     "jour, vos modifications n'ont pas été enregistrées."),
        )


def apply_constraints(client: Client, constraints: dict,
                      version_envoyee: Optional[int], definitions=None) -> Client:
    """Écrit le blob sous verrou et fait avancer la version d'un cran.

    `definitions` vient du référentiel et porte les champs ajoutés pour cette
    entité et pour ce client. Omis, seuls les champs standards sont acceptés.
    """
    require_constraints_version(client, version_envoyee)
    propre = validate_constraints(constraints, definitions)
    client.constraints_json = json.dumps(propre, ensure_ascii=False)
    client.constraints_version = client.constraints_version + 1
    client.updated_at = datetime.utcnow()
    return client


def read_constraints(client: Client) -> dict:
    """Le blob relu, tolérant à une ligne écrite avant ce schéma."""
    try:
        valeur = json.loads(client.constraints_json or "{}")
    except (TypeError, ValueError):
        return {}
    return valeur if isinstance(valeur, dict) else {}


# ── Dates ─────────────────────────────────────────────────────────────
# Les dates métier se stockent en ISO comme partout ailleurs (Deal.payment_date,
# RfqRequest.ao_date). Les comparaisons de cycles se feront sur des `date`, donc
# une chaîne qui n'en est pas une doit être refusée à l'écriture, pas découverte
# six mois plus tard par un moteur d'analyse.

def parse_iso_date(value: str, champ: str) -> date:
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        raise ClientRuleError(
            code="DATE_INVALID",
            message=f"{champ} : « {value} » n'est pas une date ISO (AAAA-MM-JJ).",
        )


# ── Affiliation : la source de vérité temporelle ──────────────────────

def current_affiliation(session: Session, person_id: int) -> Optional[Affiliation]:
    """L'affiliation ouverte d'une personne, ou None si elle n'en a aucune.

    « Ouverte » = end_date IS NULL. Rien n'est stocké : un booléen `is_current`
    redondant peut diverger de la date qui fait foi, et la question n'aurait
    alors plus une seule réponse. S'il en existe plusieurs (cas professionnel
    réel, non interdit par le modèle), la plus récemment commencée est rendue —
    c'est celle qu'un écran doit montrer par défaut.
    """
    ouvertes = session.exec(
        select(Affiliation)
        .where(Affiliation.person_id == person_id, Affiliation.end_date.is_(None))
    ).all()
    if not ouvertes:
        return None
    return sorted(ouvertes, key=lambda a: (a.start_date or "", a.id or 0))[-1]


def affiliations_of_client(session: Session, client_id: int,
                           *, only_current: bool = True) -> list[Affiliation]:
    """Les affiliations rattachées à un client.

    `only_current` par défaut : à la création d'une opportunité on ne propose
    que les gens qui y travaillent aujourd'hui. Les anciens restent visibles
    dans les vues d'historique, qui appellent avec only_current=False.
    """
    requete = select(Affiliation).where(Affiliation.client_id == client_id)
    if only_current:
        requete = requete.where(Affiliation.end_date.is_(None))
    return list(session.exec(requete).all())


def require_affiliation_of_client(session: Session, affiliation_id: int,
                                  client_id: int) -> Affiliation:
    """Vérifie qu'une affiliation appartient bien au client visé.

    C'est le contrôle du §29 : il doit être impossible d'enregistrer une
    opportunité chez Client B avec un contact affilié à Client A, quel que
    soit le chemin d'appel.
    """
    affiliation = session.get(Affiliation, affiliation_id)
    if affiliation is None:
        raise ClientRuleError(
            code="AFFILIATION_NOT_FOUND",
            message="Ce contact n'existe pas (ou plus).",
        )
    if affiliation.client_id != client_id:
        client = session.get(Client, client_id)
        nom = client.name if client else f"#{client_id}"
        raise ClientRuleError(
            code="AFFILIATION_CLIENT_MISMATCH",
            message=(f"Ce contact n'est pas rattaché à « {nom} ». "
                     f"Sélectionnez une personne affiliée à ce client."),
        )
    return affiliation


def require_mandate_of_client(
    session: Session,
    mandate_id: int,
    client_id: int,
    *,
    active_required: bool = False,
) -> ClientMandate:
    """Return a mandate only when it belongs to the selected Client.

    An archived mandate remains readable for historical snapshots but cannot
    be used for a new RFQ or Deal.
    """
    mandate = session.get(ClientMandate, mandate_id)
    if mandate is None:
        raise ClientRuleError(
            code="MANDATE_NOT_FOUND",
            message="Ce mandat n'existe pas (ou plus).",
        )
    if mandate.client_id != client_id:
        client = session.get(Client, client_id)
        nom = client.name if client else f"#{client_id}"
        raise ClientRuleError(
            code="MANDATE_CLIENT_MISMATCH",
            message=(f"Ce mandat n'appartient pas à « {nom} ». "
                     "Sélectionnez un périmètre de ce Client."),
        )
    if active_required and mandate.status != "active":
        raise ClientRuleError(
            code="MANDATE_ARCHIVED",
            message=(f"Le mandat « {mandate.name} » est archivé. "
                     "Réactivez-le ou sélectionnez un mandat actif."),
        )
    return mandate


def validate_opportunity_contacts(
    session: Session, client_id: int,
    primary_affiliation_id: Optional[int],
    participant_affiliation_ids: list[int],
) -> None:
    """Cohérence complète du couple client / contacts d'une opportunité.

    Trois refus : un contact d'un autre client (§29), le contact principal
    répété dans les participants (§27), un participant en double (§64 — la
    contrainte d'unicité l'attraperait aussi, mais avec un message illisible).
    """
    if primary_affiliation_id is not None:
        require_affiliation_of_client(session, primary_affiliation_id, client_id)

    vus: set[int] = set()
    for affiliation_id in participant_affiliation_ids:
        require_affiliation_of_client(session, affiliation_id, client_id)
        if affiliation_id == primary_affiliation_id:
            raise ClientRuleError(
                code="PARTICIPANT_IS_PRIMARY",
                message=("Le contact principal est déjà porté comme tel : "
                         "inutile de le répéter dans les participants."),
            )
        if affiliation_id in vus:
            raise ClientRuleError(
                code="PARTICIPANT_DUPLICATE",
                message="Ce contact figure deux fois parmi les participants.",
            )
        vus.add(affiliation_id)


# ── Changement de société ─────────────────────────────────────────────

def change_company(
    session: Session, *, person_id: int, new_client_id: int,
    start_date: str, job_title: str = "", commercial_role: str = "other",
    end_date_previous: Optional[str] = None, notes: Optional[str] = None,
) -> tuple[Optional[Affiliation], Affiliation]:
    """Clôture l'affiliation en cours et en ouvre une nouvelle, d'un seul geste.

    Ne remplace JAMAIS person.client_id — ce champ n'existe pas, exprès. Les
    interactions, opportunités et trades attachés à l'ancienne affiliation la
    gardent : rien ici ne les touche, et c'est précisément la garantie
    recherchée (§8).

    L'appelant reste maître du commit : les deux écritures partagent la session,
    donc si la seconde échoue, la première ne sera jamais validée. Une clôture
    sans réouverture laisserait une personne sans employeur, une réouverture
    sans clôture lui en donnerait deux — ni l'un ni l'autre n'est un état que
    l'application doit pouvoir atteindre (§65).

    Rend le couple (ancienne affiliation clôturée ou None, nouvelle affiliation).
    """
    personne = session.get(Person, person_id)
    if personne is None:
        raise ClientRuleError(code="PERSON_NOT_FOUND",
                              message="Cette personne n'existe pas.")
    if session.get(Client, new_client_id) is None:
        raise ClientRuleError(code="CLIENT_NOT_FOUND",
                              message="Cette société n'existe pas.")
    validate_commercial_role(commercial_role)
    debut = parse_iso_date(start_date, "Date de début")

    ancienne = current_affiliation(session, person_id)
    if ancienne is not None:
        if ancienne.client_id == new_client_id:
            raise ClientRuleError(
                code="AFFILIATION_SAME_CLIENT",
                message=("Cette personne est déjà en poste dans cette société. "
                         "Modifiez son affiliation plutôt que d'en créer une seconde."),
            )
        # Par défaut la veille de la prise de poste : deux affiliations ne se
        # chevauchent pas, et aucune journée ne reste sans employeur.
        fin = end_date_previous or debut.isoformat()
        fin_date = parse_iso_date(fin, "Date de fin de l'affiliation précédente")
        debut_ancien = parse_iso_date(ancienne.start_date or fin, "Date de début")
        if fin_date < debut_ancien:
            raise ClientRuleError(
                code="AFFILIATION_END_BEFORE_START",
                message=("La fin de l'affiliation précédente est antérieure à son "
                         "début. Corrigez les dates avant d'enregistrer."),
            )
        ancienne.end_date = fin_date.isoformat()
        ancienne.updated_at = datetime.utcnow()
        session.add(ancienne)

    nouvelle = Affiliation(
        person_id=person_id, client_id=new_client_id,
        job_title=job_title, commercial_role=commercial_role,
        start_date=debut.isoformat(), end_date=None, notes=notes,
    )
    session.add(nouvelle)
    session.flush()          # l'id de la nouvelle affiliation doit exister
    return ancienne, nouvelle


def close_affiliation(session: Session, affiliation_id: int, end_date: str) -> Affiliation:
    """Clôt une affiliation sans en ouvrir d'autre — un départ sans successeur
    connu. Le couple (person, client) reste intact : on ferme une période, on
    n'efface pas un passage."""
    affiliation = session.get(Affiliation, affiliation_id)
    if affiliation is None:
        raise ClientRuleError(code="AFFILIATION_NOT_FOUND",
                              message="Ce contact n'existe pas (ou plus).")
    fin = parse_iso_date(end_date, "Date de fin")
    debut = parse_iso_date(affiliation.start_date or end_date, "Date de début")
    if fin < debut:
        raise ClientRuleError(
            code="AFFILIATION_END_BEFORE_START",
            message="La date de fin est antérieure à la date de début.",
        )
    affiliation.end_date = fin.isoformat()
    affiliation.updated_at = datetime.utcnow()
    session.add(affiliation)
    return affiliation


# ── Doublons : avertir, jamais bloquer ────────────────────────────────
# §21 est explicite — on signale, l'utilisateur confirme. Une contrainte dure
# sur l'email interdirait d'enregistrer deux homonymes réels, ou de ressaisir
# une adresse générique de desk.

def _normalise_nom(valeur: str) -> str:
    return " ".join(str(valeur or "").strip().casefold().split())


def find_person_duplicates(session: Session, *, first_name: str, last_name: str,
                           email: Optional[str] = None,
                           entity_id: Optional[int] = None,
                           exclude_id: Optional[int] = None) -> list[dict]:
    """Doublons probables d'une personne, du signal le plus fort au plus faible.

    L'email identique est un signal fort ; le couple prénom/nom identique est
    un signal faible (les homonymes existent) mais suffit à mériter une
    question — c'est exactement le cas §20 : Jean Dupont qui rejoint Bank B
    après Bank A ne doit pas devenir un second Jean Dupont.
    """
    requete = select(Person)
    if entity_id is not None:
        requete = requete.where(Person.entity_id == entity_id)
    candidats = [p for p in session.exec(requete).all() if p.id != exclude_id]

    email_norm = _normalise_nom(email) if email else ""
    prenom, nom = _normalise_nom(first_name), _normalise_nom(last_name)

    trouves: list[dict] = []
    for personne in candidats:
        if email_norm and _normalise_nom(personne.email) == email_norm:
            trouves.append({"person_id": personne.id, "signal": "email",
                            "confidence": "high",
                            "label": f"{personne.first_name} {personne.last_name}"})
        elif (prenom and nom
                and _normalise_nom(personne.first_name) == prenom
                and _normalise_nom(personne.last_name) == nom):
            trouves.append({"person_id": personne.id, "signal": "name",
                            "confidence": "medium",
                            "label": f"{personne.first_name} {personne.last_name}"})
    ordre = {"high": 0, "medium": 1}
    return sorted(trouves, key=lambda d: ordre.get(d["confidence"], 9))


def find_client_duplicates(session: Session, *, name: str,
                           legal_name: Optional[str] = None,
                           external_ref: Optional[str] = None,
                           entity_id: Optional[int] = None,
                           exclude_id: Optional[int] = None) -> list[dict]:
    """Doublons probables d'un client. L'identifiant externe est le signal le
    plus fort, puis la raison sociale, puis le nom commercial."""
    requete = select(Client)
    if entity_id is not None:
        requete = requete.where(Client.entity_id == entity_id)
    candidats = [c for c in session.exec(requete).all() if c.id != exclude_id]

    nom_n = _normalise_nom(name)
    legal_n = _normalise_nom(legal_name) if legal_name else ""
    ref_n = _normalise_nom(external_ref) if external_ref else ""

    trouves: list[dict] = []
    for client in candidats:
        if ref_n and _normalise_nom(client.external_ref) == ref_n:
            trouves.append({"client_id": client.id, "signal": "external_ref",
                            "confidence": "high", "label": client.name})
        elif legal_n and _normalise_nom(client.legal_name) == legal_n:
            trouves.append({"client_id": client.id, "signal": "legal_name",
                            "confidence": "high", "label": client.name})
        elif nom_n and _normalise_nom(client.name) == nom_n:
            trouves.append({"client_id": client.id, "signal": "name",
                            "confidence": "medium", "label": client.name})
    ordre = {"high": 0, "medium": 1}
    return sorted(trouves, key=lambda d: ordre.get(d["confidence"], 9))


# ── Suppression : ce qui porte un historique s'archive ────────────────

def client_history_counts(session: Session, client_id: int) -> dict[str, int]:
    """Ce qui pend à un client. Sert au refus de suppression ET au message qui
    l'explique : « 3 contacts, 2 opportunités et 1 trade » est actionnable,
    « foreign key violation » ne l'est pas (§82)."""
    affiliations = session.exec(
        select(Affiliation).where(Affiliation.client_id == client_id)).all()
    return {
        "affiliations": len(affiliations),
        "interactions": len(session.exec(
            select(Interaction).where(Interaction.client_id == client_id)).all()),
        "opportunities": len(session.exec(
            select(Opportunity).where(Opportunity.client_id == client_id)).all()),
        "deals": len(session.exec(
            select(Deal).where(Deal.client_id == client_id)).all()),
        "imported_trades": len(session.exec(
            select(ClientTradeHistory).where(
                ClientTradeHistory.client_id == client_id)).all()),
        "mandates": len(session.exec(
            select(ClientMandate).where(ClientMandate.client_id == client_id)).all()),
        "preferences": len(session.exec(
            select(ClientPreferenceStatement).where(
                ClientPreferenceStatement.client_id == client_id)).all()),
    }


def require_client_deletable(session: Session, client_id: int) -> None:
    """Refuse la suppression physique dès qu'un historique métier existe.

    §17 et §63 : on n'efface pas en cascade un passé commercial. Un client qui
    porte quoi que ce soit s'archive — le statut 'archived' le sort des listes
    sans détruire ce que Client Intelligence a besoin de lire.
    """
    compte = client_history_counts(session, client_id)
    portant = {k: v for k, v in compte.items() if v}
    if not portant:
        return
    libelles = {"affiliations": "contact(s)", "interactions": "interaction(s)",
                "opportunities": "opportunité(s)", "deals": "trade(s)",
                "imported_trades": "transaction(s) importée(s)",
                "mandates": "mandat(s)", "preferences": "préférence(s)",
                "documentation": "référence(s) documentaire(s)"}
    detail = ", ".join(f"{v} {libelles[k]}" for k, v in portant.items())
    raise ClientRuleError(
        code="CLIENT_HAS_HISTORY",
        message=(f"Ce client ne peut pas être supprimé : il porte {detail}. "
                 f"Archivez-le plutôt — son historique reste consultable."),
    )


def person_history_counts(session: Session, person_id: int) -> dict[str, int]:
    affiliations = session.exec(
        select(Affiliation).where(Affiliation.person_id == person_id)).all()
    ids = [a.id for a in affiliations]
    opportunites = 0
    deals = 0
    if ids:
        opportunites = len(session.exec(
            select(Opportunity)
            .where(Opportunity.primary_affiliation_id.in_(ids))).all())
        opportunites += len(session.exec(
            select(OpportunityParticipant)
            .where(OpportunityParticipant.affiliation_id.in_(ids))).all())
        deals = len(session.exec(
            select(Deal).where(Deal.primary_affiliation_id.in_(ids))).all())
    return {"affiliations": len(affiliations),
            "opportunities": opportunites, "deals": deals}


def require_person_deletable(session: Session, person_id: int) -> None:
    compte = person_history_counts(session, person_id)
    portant = {k: v for k, v in compte.items() if v}
    if not portant:
        return
    libelles = {"affiliations": "affiliation(s)",
                "opportunities": "opportunité(s)", "deals": "trade(s)"}
    detail = ", ".join(f"{v} {libelles[k]}" for k, v in portant.items())
    raise ClientRuleError(
        code="PERSON_HAS_HISTORY",
        message=(f"Cette personne ne peut pas être supprimée : elle porte {detail}. "
                 f"Désactivez-la plutôt — son historique professionnel est conservé."),
    )


# ── Statut d'opportunité ──────────────────────────────────────────────

def validate_status_transition(current: str, nouveau: str,
                               lost_reason: Optional[str]) -> None:
    """Le seul garde-fou de pipeline que je pose : perdre une opportunité exige
    de dire pourquoi.

    Aucun ordre imposé entre les étapes — un besoin peut sauter de 'lead' à
    'rfq' si le client arrive avec son idée toute faite, et forcer une
    progression linéaire ferait mentir la saisie. En revanche la raison de
    perte est la matière première de Client Intelligence (§33) : sans elle,
    « pourquoi ce client refuse » n'a aucune réponse.
    """
    validate_opportunity_status(nouveau)
    if nouveau == "lost":
        if not lost_reason:
            raise ClientRuleError(
                code="LOST_REASON_REQUIRED",
                message=("Indiquez pourquoi l'opportunité est perdue : c'est ce qui "
                         "permettra plus tard d'expliquer les refus de ce client."),
            )
        _check_vocabulary(lost_reason, LOST_REASONS, "LOST_REASON_INVALID",
                          "Raison de perte")


def require_opportunity_rfq_ready(session: Session, opportunity: Opportunity) -> None:
    """Qualification gate used only when an Opportunity launches a Client RFQ."""
    if not (str(opportunity.title or "").strip()
            or str(opportunity.description or "").strip()):
        raise ClientRuleError(
            code="OPPORTUNITY_NEED_REQUIRED",
            message="Décrivez le besoin Client avant de lancer l'appel d'offres.",
        )
    if opportunity.mandate_id is None:
        raise ClientRuleError(
            code="OPPORTUNITY_MANDATE_REQUIRED",
            message=("Sélectionnez le mandat, fonds, compte ou desk de l'Opportunity "
                     "avant de lancer l'appel d'offres."),
        )
    require_mandate_of_client(
        session, opportunity.mandate_id, opportunity.client_id,
        active_required=True)
    validate_opportunity_contacts(
        session, opportunity.client_id, opportunity.primary_affiliation_id, [])


# ── Provenance figée d'un trade ───────────────────────────────────────

def client_provenance_snapshot(session: Session, *, client_id: Optional[int],
                               affiliation_id: Optional[int],
                               opportunity_id: Optional[int],
                               mandate_id: Optional[int] = None) -> Optional[str]:
    """Le cliché commercial écrit sur le deal au booking.

    Même raison d'être que rfq_provenance_json : le pointeur garantit la
    justesse, le cliché garantit la preuve. Une fiche client peut être corrigée,
    une personne renommée, une affiliation supprimée par erreur — ce qui a été
    écrit ici ne bouge plus, et une note de valorisation émise dans deux ans
    dira ce qui était vrai le jour du trade.

    Rend None quand il n'y a rien à figer : un deal booké hors parcours client
    ne porte pas un cliché vide.
    """
    if (client_id is None and affiliation_id is None
            and opportunity_id is None and mandate_id is None):
        return None

    cliche: dict = {"captured_at": datetime.utcnow().isoformat()}

    if client_id is not None:
        client = session.get(Client, client_id)
        if client is not None:
            cliche["client"] = {
                "id": client.id, "name": client.name,
                "legal_name": client.legal_name, "client_type": client.client_type,
                "country": client.country, "data_origin": client.data_origin,
            }

    if mandate_id is not None:
        mandate = session.get(ClientMandate, mandate_id)
        if mandate is not None:
            cliche["mandate"] = {
                "id": mandate.id, "name": mandate.name,
                "mandate_type": mandate.mandate_type,
                "reference_currency": mandate.reference_currency,
                "status": mandate.status, "data_origin": mandate.data_origin,
            }

    if affiliation_id is not None:
        affiliation = session.get(Affiliation, affiliation_id)
        if affiliation is not None:
            personne = session.get(Person, affiliation.person_id)
            cliche["contact"] = {
                "affiliation_id": affiliation.id,
                "person_id": affiliation.person_id,
                "name": (f"{personne.first_name} {personne.last_name}".strip()
                         if personne else None),
                "job_title": affiliation.job_title,
                "commercial_role": affiliation.commercial_role,
                "client_id": affiliation.client_id,
            }

    if opportunity_id is not None:
        opportunite = session.get(Opportunity, opportunity_id)
        if opportunite is not None:
            cliche["opportunity"] = {
                "id": opportunite.id, "reference": opportunite.reference,
                "title": opportunite.title, "status": opportunite.status,
            }

    return json.dumps(cliche, ensure_ascii=False)


def require_deal_attribution_coherent(session: Session, *, client_id: Optional[int],
                                      affiliation_id: Optional[int],
                                      opportunity_id: Optional[int],
                                      mandate_id: Optional[int] = None,
                                      entity_id: Optional[int] = None) -> None:
    """Contrôle complet du rattachement commercial d'un trade.

    Deux familles de refus, et il a fallu une sonde pour découvrir que la
    seconde manquait.

    **Cohérence interne** — l'affiliation appartient au client visé, et
    l'opportunité aussi. Sans elle, on écrirait un trade « client B / contact
    chez A » qui corromprait toutes les statistiques par affiliation.

    **Appartenance** — le client et l'opportunité désignés doivent être VISIBLES
    par l'entité qui booke. Ce contrôle manquait : un utilisateur d'une autre
    entité pouvait rattacher son deal à un client qu'il n'a pas le droit de
    lire, et le cliché figé recopiait au passage le nom de ce client dans son
    propre deal. La cohérence ne suffit pas — un rattachement peut être
    parfaitement cohérent et parfaitement indu.

    `entity_id` est optionnel pour ne pas casser un appelant interne qui aurait
    déjà vérifié, mais tout chemin exposé doit le passer.
    """
    if affiliation_id is not None and client_id is None:
        raise ClientRuleError(
            code="DEAL_CONTACT_WITHOUT_CLIENT",
            message="Un contact ne peut être rattaché à un trade sans son client.",
        )
    if mandate_id is not None and client_id is None:
        raise ClientRuleError(
            code="DEAL_MANDATE_WITHOUT_CLIENT",
            message="Un mandat ne peut être rattaché à un trade sans son Client.",
        )
    if opportunity_id is not None and client_id is None:
        raise ClientRuleError(
            code="DEAL_OPPORTUNITY_WITHOUT_CLIENT",
            message="Une Opportunity ne peut être rattachée à un trade sans son Client.",
        )

    if client_id is not None:
        client = session.get(Client, client_id)
        # 404 en substance, comme partout ailleurs : confirmer l'existence d'une
        # fiche d'une autre entité serait déjà une information.
        if client is None or (entity_id is not None
                              and client.entity_id != entity_id):
            raise ClientRuleError(
                code="CLIENT_NOT_FOUND",
                message="Client introuvable — vérifiez le rattachement du trade.",
            )
        if mandate_id is None:
            raise ClientRuleError(
                code="DEAL_MANDATE_REQUIRED",
                message=("Sélectionnez le mandat, fonds, compte ou desk concerné. "
                         "Pour un Deal Produit autonome, retirez tout le contexte Client."),
            )
        require_mandate_of_client(
            session, mandate_id, client_id, active_required=True)

    if affiliation_id is not None:
        require_affiliation_of_client(session, affiliation_id, client_id)

    if opportunity_id is not None:
        opportunite = session.get(Opportunity, opportunity_id)
        if opportunite is None or (entity_id is not None
                                   and opportunite.entity_id != entity_id):
            raise ClientRuleError(code="OPPORTUNITY_NOT_FOUND",
                                  message="Cette opportunité n'existe pas.")
        if client_id is not None and opportunite.client_id != client_id:
            raise ClientRuleError(
                code="OPPORTUNITY_CLIENT_MISMATCH",
                message=("L'opportunité ne concerne pas ce client. "
                         "Vérifiez le rattachement du trade."),
            )
        if opportunite.mandate_id != mandate_id:
            raise ClientRuleError(
                code="OPPORTUNITY_MANDATE_MISMATCH",
                message=("L'Opportunity ne porte pas ce mandat. "
                         "Corrigez son périmètre avant le booking."),
            )
