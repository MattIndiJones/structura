"""Client Intelligence — ce que les transactions disent, et à quel niveau.

Ce module lit la base et agrège ; toute l'arithmétique de cadence vit dans
`client_cycle.py`, qui n'a besoin que de dates.

**Trois niveaux, jamais confondus.** Une même transaction se lit de trois
façons : elle appartient à une personne (toutes sociétés confondues), à un
passage dans une société donnée, et à la société elle-même. Les mélanger
donnerait exactement ce que §40 interdit — un client décrit comme « risque
moyen » parce qu'il abrite un gérant prudent et un gérant agressif.

**Déclaré et observé cohabitent.** Ce qu'un contact dit préférer et ce qu'il
achète réellement sont rendus côte à côte, jamais l'un écrasé par l'autre
(§11). Leur divergence est une information commerciale, pas une erreur à
corriger.

**Aucune causalité.** On observe qu'une cadence ressemble davantage à celle de
la maison qu'à l'historique de la personne. On n'en déduit rien.
"""
from __future__ import annotations

import json
from collections import Counter
from datetime import date
from typing import Optional, Sequence

from sqlmodel import Session, select

from ..db.models import (
    Affiliation, Client, ClientMandate, ClientPreferenceStatement,
    ClientTradeHistory, Deal, Interaction, InteractionParticipant, Opportunity,
    OpportunityParticipant, Person,
)
from .client_cycle import (
    Cycle, compare_cycles, compute_cycle, observed_lead_days,
    recommend_contact_window,
)


def _date_iso(valeur: Optional[str]) -> Optional[date]:
    """Une date ISO stockée en texte, ou None si elle est illisible.

    Tolérant plutôt que strict : une ligne mal formée doit sortir du calcul,
    pas faire tomber l'écran qui l'affiche.
    """
    if not valeur:
        return None
    try:
        return date.fromisoformat(str(valeur)[:10])
    except (TypeError, ValueError):
        return None


# ── Sélection des transactions ────────────────────────────────────────
# Toujours par AFFILIATION ou par client, jamais par personne directement :
# c'est ce qui garantit qu'un trade reste comptabilisé chez la société où il a
# été fait, même après un changement d'employeur.

def affiliation_ids_of_person(session: Session, person_id: int) -> list[int]:
    return [a.id for a in session.exec(
        select(Affiliation).where(Affiliation.person_id == person_id)).all()]


class Transaction:
    """Une transaction, quelle que soit son origine.

    Deux sources la produisent : un `Deal` réellement booké chez nous, et une
    ligne d'historique versée depuis un fichier client. Elles ne portent ni les
    mêmes champs ni les mêmes noms — `devise`/`currency`,
    `contrepartie`/`issuer`, `nominal`/`notional` — mais elles disent la même
    chose pour l'analyse commerciale : ce client a acheté ceci, ce jour-là.

    Cette normalisation existe pour que le moteur ne connaisse qu'une forme.
    L'alternative — un `if` sur le type dans chaque calcul — garantirait qu'un
    jour l'un des deux soit oublié quelque part, et qu'un client paraisse deux
    fois moins actif qu'il ne l'est.
    """
    __slots__ = ("trade_date", "maturity_date", "reference_date", "product_type",
                 "currency", "issuer", "notional", "underlyings", "imported",
                 "opportunity_id", "client_id", "mandate_id", "affiliation_id",
                 "coupon_pct", "protection_pct", "price_pct", "traded_with_us",
                 "reference", "barriers", "source_type", "source_id",
                 "data_origin", "transaction_format", "instrument_family",
                 "payoff_family", "payoff_description",
                 "documentation_reference", "rfq_provenance")

    def __init__(self, *, trade_date, maturity_date, reference_date, product_type,
                 currency, issuer, notional, underlyings, imported,
                 opportunity_id=None, client_id=None, coupon_pct=None,
                 protection_pct=None, price_pct=None, traded_with_us=None,
                 reference=None, barriers=None, mandate_id=None,
                 affiliation_id=None, source_type="deal", source_id=None,
                 data_origin="native", transaction_format=None,
                 instrument_family=None, payoff_family=None,
                 payoff_description=None, documentation_reference=None,
                 rfq_provenance=None):
        # Les niveaux : coupon et protection. Sur une ligne importée ils sont
        # explicites ; sur un deal booké il faut les LIRE dans le script, sans
        # quoi l'écran technique n'afficherait des niveaux que pour les
        # transactions dont nous sommes le moins sûrs.
        self.coupon_pct = coupon_pct
        self.protection_pct = protection_pct
        self.price_pct = price_pct
        self.traded_with_us = traded_with_us
        self.reference = reference
        self.barriers = barriers or []
        self.opportunity_id = opportunity_id
        # Porté pour permettre de tout charger d'un coup puis de regrouper en
        # mémoire, au lieu d'une requête par client.
        self.client_id = client_id
        self.mandate_id = mandate_id
        self.affiliation_id = affiliation_id
        self.trade_date = trade_date
        self.maturity_date = maturity_date
        self.reference_date = reference_date
        self.product_type = product_type
        self.currency = currency
        self.issuer = issuer
        self.notional = notional
        self.underlyings = underlyings
        self.imported = imported
        self.source_type = source_type
        self.source_id = source_id
        self.data_origin = data_origin
        self.transaction_format = transaction_format
        self.instrument_family = instrument_family
        self.payoff_family = payoff_family
        self.payoff_description = payoff_description
        self.documentation_reference = documentation_reference
        self.rfq_provenance = rfq_provenance

    @property
    def analytically_eligible(self) -> bool:
        """Real/imported observations only; demo remains separately inspectable."""
        return self.data_origin in {"native", "imported"}


def _niveaux_du_deal(deal: Deal) -> dict:
    """Coupon, protection et barrières d'un deal, lus dans son script figé.

    Le script est mis en cache par son texte : une fiche client reparse sinon
    le même modèle autant de fois qu'il y a de deals qui en sont issus, et un
    parse PayScript n'est pas gratuit.
    """
    from .client_technical import niveaux_du_script
    script = deal.script_snapshot or ""
    if script not in _CACHE_NIVEAUX:
        _CACHE_NIVEAUX[script] = niveaux_du_script(script)
    niveaux = _CACHE_NIVEAUX[script]
    return {"coupon_pct": niveaux["coupon_pct"],
            "protection_pct": niveaux["protection_pct"],
            "barriers": niveaux["barriers"]}


# Cache de lecture, vidé à chaque assemblage de fiche : on ne veut pas qu'il
# grossisse indéfiniment dans un processus qui tourne des semaines.
_CACHE_NIVEAUX: dict[str, dict] = {}


def _json_object(raw: Optional[str]) -> Optional[dict]:
    if not raw:
        return None
    try:
        value = json.loads(raw)
        return value if isinstance(value, dict) else None
    except (TypeError, ValueError):
        return None


def _depuis_deal(
    deal: Deal, *, client_origin: str = "native",
    mandate_origin: Optional[str] = None,
) -> Transaction:
    sous_jacents = []
    try:
        for sj in json.loads(deal.underlyings_json or "[]"):
            nom = (sj.get("ticker") or sj.get("name") or "").strip()
            if nom:
                sous_jacents.append(nom)
    except (TypeError, ValueError):
        pass
    origin = ("demo" if deal.uat_batch_id is not None
              or client_origin == "demo" or mandate_origin == "demo"
              else "native")
    return Transaction(
        trade_date=deal.trade_date, maturity_date=deal.maturity_date,
        # La maturité d'un deal se compte depuis le strike, pas depuis le
        # trade : c'est la convention du moteur de pricing.
        reference_date=deal.strike_date or deal.trade_date,
        product_type=(deal.product_type or "").strip(),
        currency=deal.devise, issuer=(deal.contrepartie or "").strip(),
        notional=deal.nominal, underlyings=sous_jacents, imported=False,
        opportunity_id=deal.opportunity_id, client_id=deal.client_id,
        mandate_id=deal.mandate_id,
        affiliation_id=deal.primary_affiliation_id,
        # Un deal booké est par définition traité avec nous, et son prix est
        # déjà en colonne. Les niveaux, eux, se lisent dans le script.
        traded_with_us=True, price_pct=deal.price_traded,
        reference=deal.reference, source_type="deal", source_id=deal.id,
        data_origin=origin,
        transaction_format=deal.transaction_format,
        instrument_family=deal.instrument_family,
        payoff_family=deal.payoff_family,
        payoff_description=deal.payoff_description,
        documentation_reference=deal.documentation_reference,
        rfq_provenance=_json_object(deal.rfq_provenance_json),
        **_niveaux_du_deal(deal))


def _depuis_historique(
    ligne: ClientTradeHistory, *, client_origin: str = "imported",
) -> Transaction:
    from .client_technical import decouper_sous_jacents
    return Transaction(
        trade_date=ligne.trade_date, maturity_date=ligne.maturity_date,
        reference_date=ligne.trade_date,
        product_type=(ligne.product_type or "").strip(),
        currency=ligne.currency, issuer=(ligne.issuer or "").strip(),
        notional=ligne.notional,
        underlyings=decouper_sous_jacents(ligne.underlying),
        imported=True, client_id=ligne.client_id,
        mandate_id=ligne.mandate_id, affiliation_id=ligne.affiliation_id,
        coupon_pct=ligne.coupon_pct, protection_pct=ligne.barrier_pct,
        price_pct=ligne.price_pct, traded_with_us=ligne.traded_with_us,
        reference=ligne.external_ref, source_type="imported_trade",
        source_id=ligne.id,
        data_origin="demo" if client_origin == "demo" else "imported",
        transaction_format=ligne.transaction_format,
        instrument_family=ligne.instrument_family,
        payoff_family=ligne.payoff_family,
        payoff_description=ligne.payoff_description,
        documentation_reference=ligne.documentation_reference)


def _origin_maps(
    session: Session, client_ids: Sequence[int], mandate_ids: Sequence[int],
) -> tuple[dict[int, str], dict[int, str]]:
    client_set = {value for value in client_ids if value is not None}
    mandate_set = {value for value in mandate_ids if value is not None}
    client_origins = {
        row.id: row.data_origin for row in session.exec(
            select(Client).where(Client.id.in_(list(client_set)))).all()
    } if client_set else {}
    mandate_origins = {
        row.id: row.data_origin for row in session.exec(
            select(ClientMandate).where(ClientMandate.id.in_(list(mandate_set)))).all()
    } if mandate_set else {}
    return client_origins, mandate_origins


def _normalise_transactions(
    session: Session, deals: Sequence[Deal], histories: Sequence[ClientTradeHistory],
) -> list[Transaction]:
    client_origins, mandate_origins = _origin_maps(
        session,
        [row.client_id for row in deals] + [row.client_id for row in histories],
        [row.mandate_id for row in deals] + [row.mandate_id for row in histories],
    )
    return [
        _depuis_deal(
            row, client_origin=client_origins.get(row.client_id, "native"),
            mandate_origin=mandate_origins.get(row.mandate_id))
        for row in deals
    ] + [
        _depuis_historique(
            row, client_origin=client_origins.get(row.client_id, "imported"))
        for row in histories
    ]


def eligible_transactions(
    transactions: Sequence[Transaction], *, include_demo: bool = False,
) -> list[Transaction]:
    return [row for row in transactions
            if include_demo or row.analytically_eligible]


def deals_of_affiliations(session: Session,
                          affiliation_ids: Sequence[int]) -> list[Transaction]:
    """Les transactions rattachées à ces affiliations — bookées ET importées."""
    if not affiliation_ids:
        return []
    ids = list(affiliation_ids)
    bookes = session.exec(
        select(Deal).where(Deal.primary_affiliation_id.in_(ids))).all()
    importes = session.exec(
        select(ClientTradeHistory).where(
            ClientTradeHistory.affiliation_id.in_(ids))).all()
    return _normalise_transactions(session, bookes, importes)


def deals_of_client(session: Session, client_id: int) -> list[Transaction]:
    bookes = session.exec(
        select(Deal).where(Deal.client_id == client_id)).all()
    importes = session.exec(
        select(ClientTradeHistory).where(
            ClientTradeHistory.client_id == client_id)).all()
    return _normalise_transactions(session, bookes, importes)


def transactions_of_entity(session: Session, entity_id: Optional[int], *,
                           include_demo: Optional[bool] = None) -> list[Transaction]:
    """Toutes les transactions rattachées d'une entité, en DEUX requêtes.

    L'écran d'analytiques bouclait sur les clients en appelant
    `deals_of_client` pour chacun : 62 requêtes pour 31 clients, mesuré. C'est
    le N+1 que §68 interdit, et il grandit exactement avec le portefeuille —
    donc il ne se voit jamais en développement.
    """
    bookes = session.exec(
        select(Deal).where(Deal.entity_id == entity_id,
                           Deal.client_id.is_not(None))).all()
    importes = session.exec(
        select(ClientTradeHistory).where(
            ClientTradeHistory.entity_id == entity_id)).all()
    normalized = _normalise_transactions(session, bookes, importes)
    if include_demo is None:
        # A database made solely of demonstration Clients is an explicit demo
        # workspace.  As soon as one real/imported fact exists, demo/UAT rows
        # are excluded from portfolio analytics.
        include_demo = bool(normalized) and all(
            row.data_origin == "demo" for row in normalized)
    return eligible_transactions(normalized, include_demo=include_demo)


def transactions_by_client(session: Session, entity_id: Optional[int], *,
                           include_demo: Optional[bool] = None) -> dict[int, list[Transaction]]:
    """Tout l'entité chargé d'un coup, puis regroupé en mémoire.

    Les signaux parcourent chaque client pour comparer sa cadence à son propre
    historique : une requête par client faisait grandir le coût de l'écran avec
    le portefeuille, donc invisible tant qu'on développe sur trois clients.
    """
    groupes: dict[int, list[Transaction]] = {}
    for transaction in transactions_of_entity(
            session, entity_id, include_demo=include_demo):
        if transaction.client_id is not None:
            groupes.setdefault(transaction.client_id, []).append(transaction)
    return groupes


def _dates_de_trade(transactions: Sequence[Transaction]) -> list[date]:
    dates = [_date_iso(t.trade_date) for t in transactions]
    return [d for d in dates if d is not None]


# ── Comportement observé ──────────────────────────────────────────────

def evidence_level(observation_count: int) -> dict:
    """Qualifie le volume sans score opaque ni probabilité inventée."""
    if observation_count <= 0:
        code, label = "none", "Aucune observation"
    elif observation_count == 1:
        code, label = "isolated", "Observation isolée"
    elif observation_count == 2:
        code, label = "repeated", "Répétition observée"
    elif observation_count <= 4:
        code, label = "emerging", "Tendance émergente"
    elif observation_count <= 9:
        code, label = "observed", "Habitude observée"
    else:
        code, label = "well_documented", "Habitude bien documentée"
    return {"code": code, "label": label, "observations": observation_count}


def recency_level(last_observation: Optional[str], *, asof: Optional[date] = None) -> dict:
    """Rend la récence lisible sans supprimer une habitude ancienne."""
    observed_on = _date_iso(last_observation)
    if observed_on is None:
        return {"code": "undated", "label": "Non datée", "days": None}
    days = ((asof or date.today()) - observed_on).days
    if days <= 365:
        code, label = "current", "Actuelle"
    elif days <= 730:
        code, label = "to_confirm", "À confirmer"
    else:
        code, label = "historical", "Historique"
    return {"code": code, "label": label, "days": days}


def observed_behaviour(deals: Sequence[Transaction]) -> dict:
    """Ce que ces transactions disent, sans interprétation.

    Des comptages et des médianes, pas de profil de risque synthétique : dire
    d'un client qu'il est « défensif » suppose une échelle que personne n'a
    définie, alors que « 9 autocalls sur 11, barrière médiane à 50 % » se
    vérifie ligne à ligne.

    `imported` est rendu à part : une lecture fondée surtout sur de l'historique
    versé n'a pas la même valeur de preuve qu'une lecture fondée sur des trades
    que nous avons bookés nous-mêmes, et l'écran doit pouvoir le dire.
    """
    if not deals:
        return {"n_trades": 0, "n_imported": 0,
                "evidence": evidence_level(0),
                "product_types": [], "transaction_formats": [],
                "instrument_families": [], "payoff_families": [],
                "documentation_references": [], "currencies": [],
                "issuers": [], "underlyings": [],
                "origins": {},
                "coverage": {key: 0 for key in (
                    "transaction_format", "instrument_family", "payoff_family",
                    "documentation_reference", "currency", "issuer", "notional",
                    "maturity", "total")},
                "explanation": ["Aucune transaction rattachée."]}

    types = Counter(d.product_type for d in deals if d.product_type)
    formats = Counter(d.transaction_format for d in deals if d.transaction_format)
    instruments = Counter(d.instrument_family for d in deals if d.instrument_family)
    payoffs = Counter(
        d.payoff_family or famille_de_produit(d.product_type)
        for d in deals if d.payoff_family or famille_de_produit(d.product_type))
    documentations = Counter(
        d.documentation_reference for d in deals if d.documentation_reference)
    devises = Counter(d.currency for d in deals if d.currency)
    emetteurs = Counter(d.issuer for d in deals if d.issuer)

    nominaux = sorted(d.notional for d in deals if d.notional)
    maturites = []
    for transaction in deals:
        debut = _date_iso(transaction.reference_date)
        fin = _date_iso(transaction.maturity_date)
        if debut and fin and fin > debut:
            maturites.append(round((fin - debut).days / 30.44))

    sous_jacents = Counter()
    for transaction in deals:
        for nom in transaction.underlyings:
            sous_jacents[nom] += 1

    def _mediane(valeurs):
        if not valeurs:
            return None
        triees = sorted(valeurs)
        n = len(triees)
        return (float(triees[n // 2]) if n % 2
                else (triees[n // 2 - 1] + triees[n // 2]) / 2.0)

    ticket_median = _mediane(nominaux)
    maturite_mediane = _mediane(maturites)

    importees = sum(1 for d in deals if d.imported)
    origines = Counter(d.data_origin for d in deals)
    explication = [f"{len(deals)} transaction(s) rattachée(s)."]
    if importees:
        explication.append(
            f"Dont {importees} issue(s) d'un historique versé. Elles sont comptées "
            f"comme les trades natifs lorsqu'elles sont normalisées ; leur provenance "
            f"reste visible pour permettre l'audit.")
    if types:
        premier, compte = types.most_common(1)[0]
        explication.append(
            f"Structure la plus fréquente : {premier} ({compte} sur {len(deals)}).")
    if ticket_median:
        explication.append(f"Ticket médian {round(ticket_median):,}".replace(",", " "))
    if maturite_mediane:
        explication.append(f"Maturité médiane {round(maturite_mediane)} mois.")

    return {
        "n_trades": len(deals),
        "n_imported": importees,
        "evidence": evidence_level(len(deals)),
        "product_types": types.most_common(),
        "transaction_formats": formats.most_common(),
        "instrument_families": instruments.most_common(),
        "payoff_families": payoffs.most_common(),
        "documentation_references": documentations.most_common(),
        "currencies": devises.most_common(),
        "issuers": emetteurs.most_common(),
        "underlyings": sous_jacents.most_common(10),
        "median_ticket": ticket_median,
        "median_maturity_months": maturite_mediane,
        "origins": dict(origines),
        "coverage": {
            "transaction_format": sum(1 for d in deals if d.transaction_format),
            "instrument_family": sum(1 for d in deals if d.instrument_family),
            "payoff_family": sum(
                1 for d in deals
                if d.payoff_family or famille_de_produit(d.product_type)),
            "documentation_reference": sum(
                1 for d in deals if d.documentation_reference),
            "currency": sum(1 for d in deals if d.currency),
            "issuer": sum(1 for d in deals if d.issuer),
            "notional": sum(1 for d in deals if d.notional is not None),
            "maturity": len(maturites),
            "total": len(deals),
        },
        "explanation": explication,
    }


def lost_reasons(session: Session, *, client_id: Optional[int] = None,
                 affiliation_ids: Optional[Sequence[int]] = None) -> list[tuple]:
    """Pourquoi ça n'a pas abouti — l'autre moitié de l'information.

    Un client dont on ne connaît que les trades gagnés n'est connu qu'à moitié :
    ce qu'il refuse, et pour quel motif, dit quoi lui proposer ensuite.
    """
    requete = select(Opportunity).where(Opportunity.status == "lost")
    if client_id is not None:
        requete = requete.where(Opportunity.client_id == client_id)
    perdues = list(session.exec(requete).all())
    if affiliation_ids is not None:
        ids = set(affiliation_ids)
        participations = {
            p.opportunity_id for p in session.exec(
                select(OpportunityParticipant).where(
                    OpportunityParticipant.affiliation_id.in_(list(ids)))).all()
        } if ids else set()
        perdues = [o for o in perdues
                   if o.primary_affiliation_id in ids or o.id in participations]
    return Counter(o.lost_reason for o in perdues if o.lost_reason).most_common()


# ── Habitudes explicables, par dimension ────────────────────────────

_HABIT_DIMENSIONS = (
    ("transaction_format", "Format", lambda row: [row.transaction_format]),
    ("instrument_family", "Instrument", lambda row: [row.instrument_family]),
    ("payoff_family", "Payoff", lambda row: [
        row.payoff_family or famille_de_produit(row.product_type)]),
    ("issuer", "Émetteur / contrepartie", lambda row: [row.issuer]),
    ("currency", "Devise", lambda row: [row.currency]),
    ("underlying", "Sous-jacent", lambda row: list(row.underlyings)),
    ("documentation_reference", "Documentation référencée",
     lambda row: [row.documentation_reference]),
)


def _habit_evidence(row: Transaction) -> dict:
    return {
        "source_type": row.source_type,
        "source_id": row.source_id,
        "reference": row.reference,
        "trade_date": row.trade_date,
        "mandate_id": row.mandate_id,
        "affiliation_id": row.affiliation_id,
        "data_origin": row.data_origin,
    }


def habit_dimensions(
    transactions: Sequence[Transaction], *, asof: Optional[date] = None,
) -> list[dict]:
    """Transparent counts with their complete evidence, never a global score."""
    result = []
    for key, label, getter in _HABIT_DIMENSIONS:
        values: dict[str, dict] = {}
        comparable = 0
        for row in transactions:
            row_values = []
            seen = set()
            for raw in getter(row):
                display = str(raw or "").strip()
                normalized = _cle(display)
                if not normalized or normalized in seen:
                    continue
                seen.add(normalized)
                row_values.append((normalized, display))
            if not row_values:
                continue
            comparable += 1
            for normalized, display in row_values:
                bucket = values.setdefault(normalized, {
                    "value": display, "count": 0, "dates": [], "evidence": [],
                    "origins": Counter(),
                })
                bucket["count"] += 1
                if row.trade_date:
                    bucket["dates"].append(row.trade_date[:10])
                bucket["evidence"].append(_habit_evidence(row))
                bucket["origins"][row.data_origin] += 1
        rendered = []
        for bucket in values.values():
            last = max(bucket["dates"]) if bucket["dates"] else None
            rendered.append({
                "value": bucket["value"],
                "count": bucket["count"],
                "comparable_count": comparable,
                "share": bucket["count"] / comparable if comparable else None,
                "evidence_level": evidence_level(bucket["count"]),
                "last_observation": last,
                "recency": recency_level(last, asof=asof),
                "origins": dict(bucket["origins"]),
                "evidence": sorted(
                    bucket["evidence"],
                    key=lambda item: item["trade_date"] or "", reverse=True),
            })
        rendered.sort(key=lambda item: (-item["count"], item["value"].casefold()))
        result.append({
            "key": key,
            "label": label,
            "coverage_count": comparable,
            "total_count": len(transactions),
            "coverage_rate": comparable / len(transactions) if transactions else None,
            "values": rendered,
        })
    return result


def mandate_divergences(per_mandate: Sequence[dict]) -> list[dict]:
    """Visible heterogeneity; never silently flatten opposite mandates."""
    dimensions = {
        "transaction_formats": "Format",
        "instrument_families": "Instrument",
        "payoff_families": "Payoff",
        "currencies": "Devise",
        "issuers": "Émetteur / contrepartie",
    }
    output = []
    for key, label in dimensions.items():
        leaders: dict[str, list[str]] = {}
        for mandate in per_mandate:
            behaviour = mandate.get("behaviour") or {}
            values = behaviour.get(key) or []
            if behaviour.get("n_trades", 0) < 3 or not values:
                continue
            top_count = values[0][1]
            top_values = [item[0] for item in values if item[1] == top_count]
            if len(top_values) != 1:
                continue
            leaders.setdefault(str(top_values[0]), []).append(mandate["name"])
        if len(leaders) > 1:
            output.append({
                "key": key, "label": label,
                "message": "Les mandats n'ont pas la même habitude dominante.",
                "values": [{"value": value, "mandates": names}
                           for value, names in sorted(leaders.items())],
            })
    return output


def _final_rfq_responses(snapshot: dict) -> list[dict]:
    """Read both Lot-2 complete snapshots and the previous compact format."""
    responses = snapshot.get("responses")
    if isinstance(responses, list):
        return [row for row in responses if isinstance(row, dict)
                and row.get("is_final", True)]
    output = []
    retained = snapshot.get("retained")
    if isinstance(retained, dict):
        output.append({**retained, "selected": True, "status": "recu",
                       "is_final": True})
    for row in snapshot.get("competition") or []:
        if isinstance(row, dict):
            output.append({**row, "selected": False, "status": "recu",
                           "is_final": True})
    return output


def provider_selection_analysis(
    transactions: Sequence[Transaction], *, asof: Optional[date] = None,
) -> dict:
    """Provider facts from executed RFQ snapshots only, with no causal claim."""
    providers: dict[str, dict] = {}
    comparable_cases = 0
    for transaction in transactions:
        snapshot = transaction.rfq_provenance
        if not isinstance(snapshot, dict):
            continue
        responses = _final_rfq_responses(snapshot)
        priced = [row for row in responses
                  if row.get("price") is not None
                  and row.get("status", "recu") not in {"decline", "expire"}
                  and row.get("comparable", True)]
        retained = snapshot.get("retained") or {}
        selected_provider = str(retained.get("provider") or "").strip()
        if not priced or not selected_provider:
            continue
        sens = snapshot.get("sens") or "achat"
        prices = [float(row["price"]) for row in priced]
        best_price = max(prices) if sens == "vente" else min(prices)
        best_names = {
            str(row.get("provider") or "").strip() for row in priced
            if abs(float(row["price"]) - best_price) <= 1e-9
        }
        comparable_cases += 1
        date_value = (transaction.trade_date or snapshot.get("booked_at") or "")[:10]
        reason_code = snapshot.get("selection_reason_code")
        reason_note = snapshot.get("selection_reason_note")

        for row in responses:
            name = str(row.get("provider") or "").strip()
            if not name:
                continue
            stats = providers.setdefault(name, {
                "provider": name, "solicited": 0, "responded": 0,
                "comparable": 0, "best": 0, "selected": 0,
                "best_not_selected": 0, "cases": [], "dates": [],
            })
            stats["solicited"] += 1
            if row.get("price") is not None:
                stats["responded"] += 1
            is_comparable = row in priced
            is_best = name in best_names and is_comparable
            is_selected = (bool(row.get("selected"))
                           if "selected" in row else name == selected_provider)
            stats["comparable"] += int(is_comparable)
            stats["best"] += int(is_best)
            stats["selected"] += int(is_selected)
            stats["best_not_selected"] += int(is_best and not is_selected)
            if date_value:
                stats["dates"].append(date_value)
            stats["cases"].append({
                "deal_reference": transaction.reference,
                "deal_id": transaction.source_id,
                "trade_date": date_value or None,
                "rfq_reference": snapshot.get("reference"),
                "rfq_id": snapshot.get("rfq_id"),
                "price": row.get("price"),
                "best_price": best_price,
                "is_best": is_best,
                "selected": is_selected,
                "selection_reason_code": reason_code if is_selected else None,
                "selection_reason_note": reason_note if is_selected else None,
            })

    rendered = []
    questions = []
    for stats in providers.values():
        dates = stats.pop("dates")
        last = max(dates) if dates else None
        stats["last_observation"] = last
        stats["recency"] = recency_level(last, asof=asof)
        stats["evidence_level"] = evidence_level(stats["comparable"])
        stats["cases"].sort(
            key=lambda item: item["trade_date"] or "", reverse=True)
        if stats["best_not_selected"] >= 3:
            questions.append({
                "provider": stats["provider"],
                "kind": "provider_revalidation",
                "message": (
                    f"{stats['provider']} a fourni le meilleur prix sur "
                    f"{stats['best_not_selected']} RFQ exécutées sans être retenu. "
                    "Souhaitez-vous revalider ce comportement avec le Client ?"),
            })
        rendered.append(stats)
    rendered.sort(key=lambda item: (-item["best_not_selected"],
                                    -item["comparable"], item["provider"].casefold()))
    return {"comparable_cases": comparable_cases,
            "providers": rendered, "questions": questions}


# ── Déclaré vs observé ────────────────────────────────────────────────

def _statement_value(raw: str):
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return None


def preference_statements(
    session: Session, *, client_id: int, mandate_id: Optional[int] = None,
    affiliation_id: Optional[int] = None, asof: Optional[date] = None,
) -> list[ClientPreferenceStatement]:
    query = select(ClientPreferenceStatement).where(
        ClientPreferenceStatement.client_id == client_id)
    if mandate_id is None:
        query = query.where(ClientPreferenceStatement.mandate_id.is_(None))
    else:
        query = query.where(ClientPreferenceStatement.mandate_id == mandate_id)
    if affiliation_id is None:
        query = query.where(ClientPreferenceStatement.affiliation_id.is_(None))
    else:
        query = query.where(ClientPreferenceStatement.affiliation_id == affiliation_id)
    rows = list(session.exec(query).all())
    if asof is not None:
        rows = [row for row in rows
                if not row.statement_date or row.statement_date <= asof.isoformat()]
    return sorted(rows, key=lambda row: (
        row.statement_date or "", row.created_at, row.id or 0))


def _apply_statements(base: dict, rows: Sequence[ClientPreferenceStatement]) -> dict:
    output = dict(base)
    for row in rows:
        value = _statement_value(row.value_json)
        if value is None:
            output.pop(row.preference_key, None)
        else:
            output[row.preference_key] = value
    return output


def _project_statements(
    base: dict, all_rows: Sequence[ClientPreferenceStatement], *,
    asof: Optional[date],
) -> dict:
    """Replay tracked keys while leaving never-versioned legacy keys intact."""
    output = dict(base)
    for key in {row.preference_key for row in all_rows}:
        output.pop(key, None)
    eligible = [row for row in all_rows
                if asof is None or not row.statement_date
                or row.statement_date <= asof.isoformat()]
    return _apply_statements(output, eligible)


_SCALAR_PREFERENCE_KEYS = {
    "ticket_min", "ticket_max", "ticket_currency",
    "maturity_min_months", "maturity_max_months", "min_rating",
    "max_concentration_pct",
}


def preference_history(
    session: Session, *, client_id: int, mandate_id: Optional[int] = None,
    affiliation_id: Optional[int] = None,
) -> list[dict]:
    rows = preference_statements(
        session, client_id=client_id, mandate_id=mandate_id,
        affiliation_id=affiliation_id)
    latest_by_key = {}
    for row in rows:
        latest_by_key[row.preference_key] = row.id
    # Résoudre les sources en deux requêtes bornées. L'historique est destiné à
    # grandir ; un `session.get()` par déclaration ferait croître le coût de la
    # fiche exactement avec la profondeur d'audit que l'on veut conserver.
    source_ids = sorted({row.source_affiliation_id for row in rows
                         if row.source_affiliation_id is not None})
    source_affiliations = {
        row.id: row for row in session.exec(
            select(Affiliation).where(Affiliation.id.in_(source_ids))).all()
    } if source_ids else {}
    person_ids = sorted({row.person_id for row in source_affiliations.values()})
    source_people = {
        row.id: row for row in session.exec(
            select(Person).where(Person.id.in_(person_ids))).all()
    } if person_ids else {}
    output = []
    for row in reversed(rows):
        source_name = None
        if row.source_affiliation_id:
            affiliation = source_affiliations.get(row.source_affiliation_id)
            person = source_people.get(affiliation.person_id) if affiliation else None
            if person:
                source_name = f"{person.first_name} {person.last_name}".strip()
        output.append({
            "id": row.id,
            "preference_key": row.preference_key,
            "value": _statement_value(row.value_json),
            "statement_kind": row.statement_kind,
            "statement_date": row.statement_date,
            "mandate_id": row.mandate_id,
            "affiliation_id": row.affiliation_id,
            "source_affiliation_id": row.source_affiliation_id,
            "source_name": source_name,
            "channel": row.channel,
            "interaction_id": row.interaction_id,
            "note": row.note,
            "recorded_by_user_id": row.recorded_by_user_id,
            "created_at": row.created_at.isoformat(),
            "is_current": latest_by_key.get(row.preference_key) == row.id,
        })
    return output


def declared_preferences(session: Session, *, client_id: Optional[int] = None,
                         mandate_id: Optional[int] = None,
                         affiliation_id: Optional[int] = None,
                         asof: Optional[date] = None) -> dict:
    """Ce qui a été SAISI, à ses deux niveaux.

    Jamais fusionné avec l'observé, et jamais réécrit par lui : une préférence
    déclarée qui contredit les transactions est une divergence à montrer au
    commercial, pas une donnée périmée à corriger automatiquement.
    """
    resultat = {"client": {}, "mandate": {}, "affiliation": {}, "combined": {}}
    if client_id is not None:
        client = session.get(Client, client_id)
        if client is not None:
            try:
                legacy_client = json.loads(client.constraints_json or "{}")
            except (TypeError, ValueError):
                legacy_client = {}
            all_client_rows = preference_statements(
                session, client_id=client_id)
            resultat["client"] = _project_statements(
                legacy_client,
                [row for row in all_client_rows
                 if row.preference_key not in _SCALAR_PREFERENCE_KEYS],
                asof=asof)
            legacy_scalars = {
                "ticket_min": client.ticket_min, "ticket_max": client.ticket_max,
                "ticket_currency": client.ticket_currency,
                "maturity_min_months": client.maturity_min_months,
                "maturity_max_months": client.maturity_max_months,
                "min_rating": client.min_rating,
                "max_concentration_pct": client.max_concentration_pct,
            }
            resultat["client_scalars"] = _project_statements(
                legacy_scalars,
                [row for row in all_client_rows
                 if row.preference_key in _SCALAR_PREFERENCE_KEYS],
                asof=asof)
            if mandate_id is not None:
                all_mandate_rows = preference_statements(
                    session, client_id=client_id, mandate_id=mandate_id)
                resultat["mandate"] = _project_statements(
                    {}, all_mandate_rows, asof=asof)
    if affiliation_id is not None:
        affiliation = session.get(Affiliation, affiliation_id)
        if affiliation is not None:
            try:
                legacy_affiliation = json.loads(affiliation.preferences_json or "{}")
            except (TypeError, ValueError):
                legacy_affiliation = {}
            all_affiliation_rows = preference_statements(
                session, client_id=affiliation.client_id,
                affiliation_id=affiliation_id)
            resultat["affiliation"] = _project_statements(
                legacy_affiliation, all_affiliation_rows, asof=asof)
    if client_id is not None and mandate_id is not None and affiliation_id is not None:
        combined_rows = preference_statements(
            session, client_id=client_id, mandate_id=mandate_id,
            affiliation_id=affiliation_id)
        resultat["combined"] = _project_statements(
            {}, combined_rows, asof=asof)
    return resultat


# ── L'espace négatif : ce qui n'est PAS traité ────────────────────────
# C'est l'apport de la fiche visuelle. Le déclaré et l'observé superposés
# produisent quatre états, dont deux que personne ne demande jamais : ce qui est
# autorisé et jamais sollicité — l'ouverture commerciale — et ce qui est traité
# hors de la politique déclarée.

def _cle(valeur) -> str:
    return " ".join(str(valeur or "").strip().casefold().split())


# Un produit se saisit en TEXTE LIBRE — « Autocall Athena », « Phoenix Memory »,
# « Capital garanti » — alors que la politique du client se déclare dans un
# vocabulaire FERMÉ : autocall, phoenix, capital_protected… Comparer les deux
# directement ne peut jamais correspondre, et signalait « Phoenix Memory » comme
# hors politique chez un client qui autorise explicitement les phoenix.
#
# Un signal faux se fait ignorer avec les vrais : cette table existe pour que la
# comparaison porte sur la FAMILLE et non sur le libellé commercial.
_FAMILLES_PAR_MOTIF: tuple[tuple[tuple[str, ...], str], ...] = (
    (("reverse convertible", "reverse_convertible", "revconv"), "reverse_convertible"),
    (("capital garanti", "capital protege", "capital protégé",
      "capital_protected", "capital protection"), "capital_protected"),
    (("twin win", "twin_win", "twinwin"), "twin_win"),
    (("credit linked", "credit_linked", "cln"), "credit_linked"),
    (("participation", "tracker"), "participation"),
    (("phoenix",), "phoenix"),
    (("autocall", "athena"), "autocall"),
    (("shark",), "shark"),
)


def famille_de_produit(libelle: Optional[str]) -> Optional[str]:
    """La famille d'un produit d'après son libellé commercial, ou None.

    `None` quand le libellé n'est pas reconnaissable, et ce n'est pas un défaut
    de la table : un produit inclassable ne doit PAS devenir une anomalie de
    politique. « Je ne sais pas ranger ce nom » et « ce produit viole la
    politique » sont deux affirmations différentes, et confondre les deux
    fabrique exactement le faux positif que ce module refuse ailleurs.

    L'ordre des motifs compte : « reverse convertible » avant « convertible »,
    et les familles composées avant les mots isolés.
    """
    if not libelle:
        return None
    texte = _cle(libelle).replace("_", " ")
    for motifs, famille in _FAMILLES_PAR_MOTIF:
        if any(motif.replace("_", " ") in texte for motif in motifs):
            return famille
    return None


def _libelles_declares(constraints: dict, champ: str) -> dict[str, str]:
    """Les libellés d'une liste déclarée, indexés par clé normalisée.

    Accepte les deux formes : chaînes simples (devises, types de produits) et
    références `{id, label}` (émetteurs), sans que l'appelant ait à savoir
    laquelle il manipule.
    """
    sortie: dict[str, str] = {}
    for element in constraints.get(champ) or []:
        libelle = element.get("label") if isinstance(element, dict) else element
        if libelle:
            sortie[_cle(libelle)] = str(libelle)
    return sortie


def _superposer(compte: tuple[Counter, dict[str, str]], autorises: dict[str, str],
                exclus: dict[str, str], *,
                dates: Optional[dict[str, list[str]]] = None,
                classifieur=None) -> dict:
    """Range les valeurs observées et déclarées dans leurs quatre états.

    `à vérifier` couvre deux situations distinctes, et le motif les sépare :
    une valeur traitée alors qu'elle est exclue, et une valeur traitée absente
    de la liste autorisée — soit la liste est périmée, soit le contrôle a été
    contourné.

    Une politique VIDE ne produit aucune anomalie : sans liste autorisée, rien
    n'est hors liste. Signaler « hors politique » à un client qui n'a pas
    déclaré de politique serait un faux positif garanti, et un signal faux se
    fait ignorer avec les vrais.
    """
    observes, libelles = compte
    a_verifier: list[dict] = []
    utilises: list[dict] = []

    # Quand un classifieur est fourni, la comparaison porte sur la FAMILLE
    # déduite du libellé et non sur le libellé lui-même : « Phoenix Memory »
    # se range sous « phoenix », que la politique autorise. Sans lui, le nom
    # commercial ne correspondrait jamais au vocabulaire déclaré.
    def _cles_comparables(cle: str) -> set[str]:
        if classifieur is None:
            return {cle}
        famille = classifieur(libelles.get(cle, cle))
        return {cle, famille} if famille else {cle}

    couverts: set[str] = set()

    for cle, nombre in observes.most_common():
        entree = {"label": libelles.get(cle, cle), "count": nombre}
        if dates and cle in dates:
            jours = sorted(dates[cle])
            entree["first_date"], entree["last_date"] = jours[0], jours[-1]

        candidats = _cles_comparables(cle)
        if candidats & set(exclus):
            declare = next(iter(candidats & set(exclus)))
            a_verifier.append({**entree, "reason": "excluded",
                               "declared_label": exclus[declare]})
        elif autorises and not (candidats & set(autorises)):
            # Un libellé que le classifieur n'a pas su ranger n'est PAS un écart :
            # on ne sait simplement pas. Le signaler fabriquerait un faux positif.
            if classifieur is not None and len(candidats) == 1:
                utilises.append({**entree, "unclassified": True})
            else:
                a_verifier.append({**entree, "reason": "off_list"})
        else:
            utilises.append(entree)
            couverts |= candidats & set(autorises)

    jamais = [{"label": libelle} for cle, libelle in sorted(autorises.items())
              if cle not in observes and cle not in couverts]
    exclusions = [{"label": libelle} for cle, libelle in sorted(exclus.items())
                  if cle not in observes]

    return {"used": utilises, "never_used": jamais, "excluded": exclusions,
            "to_check": a_verifier,
            # Sans politique déclarée, l'écran doit le dire plutôt que de laisser
            # croire à une absence d'ouvertures.
            "has_policy": bool(autorises)}


def _compter(valeurs) -> tuple[Counter, dict[str, str]]:
    """Compte sur des clés normalisées, en gardant le libellé d'origine.

    Le rapprochement doit ignorer la casse — « BNP Paribas » et « bnp paribas »
    sont le même émetteur — mais l'écran doit afficher ce que l'utilisateur a
    saisi, pas la clé. D'où le couple rendu ensemble : une table de libellés
    portée par l'appel, jamais un cache de module qui grossirait indéfiniment
    et mélangerait les entités.
    """
    compteur: Counter = Counter()
    libelles: dict[str, str] = {}
    for brut in valeurs:
        if not brut:
            continue
        cle = _cle(brut)
        libelles.setdefault(cle, str(brut).strip())
        compteur[cle] += 1
    return compteur, libelles


def negative_space(transactions: Sequence[Transaction], constraints: dict) -> dict:
    """Le déclaré et l'observé superposés, dimension par dimension."""
    dates_par_emetteur: dict[str, list[str]] = {}
    for transaction in transactions:
        if transaction.issuer and transaction.trade_date:
            dates_par_emetteur.setdefault(
                _cle(transaction.issuer), []).append(transaction.trade_date[:10])

    payoff_overlay = _superposer(
        _compter(t.payoff_family or t.product_type for t in transactions),
        _libelles_declares(constraints, "product_types"), {},
        classifieur=famille_de_produit)
    return {
        "issuers": _superposer(
            _compter(t.issuer for t in transactions),
            _libelles_declares(constraints, "allowed_issuers"),
            _libelles_declares(constraints, "excluded_issuers"),
            dates=dates_par_emetteur),
        "currencies": _superposer(
            _compter(t.currency for t in transactions),
            _libelles_declares(constraints, "currencies"), {}),
        "transaction_formats": _superposer(
            _compter(t.transaction_format for t in transactions),
            _libelles_declares(constraints, "transaction_formats"), {}),
        "instrument_families": _superposer(
            _compter(t.instrument_family for t in transactions),
            _libelles_declares(constraints, "instrument_families"), {}),
        "payoff_families": payoff_overlay,
        # Historical response key retained for the existing ClientCard.
        "product_types": payoff_overlay,
        "underlyings": _superposer(
            _compter(nom for t in transactions for nom in t.underlyings),
            _libelles_declares(constraints, "underlying_universe"), {}),
        # L'exclusion n'est pas datée en base : `constraints_version` avance mais
        # l'historique du blob n'est pas conservé. Impossible, donc, de
        # distinguer « traité AVANT l'exclusion » de « traité MALGRÉ elle ». Les
        # dates des transactions sont rendues pour que l'utilisateur tranche,
        # plutôt que d'inventer la distinction.
        "exclusion_dates_unknown": True,
    }


# ── Les bornes : observé dans le déclaré ──────────────────────────────
# En dessous d'un seuil, on rend les points eux-mêmes et non une bande : une
# moitié centrale calculée sur deux observations invente une distribution.

OBSERVATIONS_POUR_UNE_BANDE = 5


def _quantile(valeurs: Sequence[float], q: float) -> float:
    triees = sorted(valeurs)
    if len(triees) == 1:
        return float(triees[0])
    position = q * (len(triees) - 1)
    bas = int(position)
    haut = min(bas + 1, len(triees) - 1)
    return triees[bas] + (position - bas) * (triees[haut] - triees[bas])


def _borne(valeurs: Sequence[float], mini, maxi) -> dict:
    propres = sorted(v for v in valeurs if v is not None)
    base = {"declared_min": mini, "declared_max": maxi,
            "n": len(propres), "points": [], "band": None, "median": None}
    if not propres:
        return base
    base["median"] = _quantile(propres, 0.5)
    if len(propres) >= OBSERVATIONS_POUR_UNE_BANDE:
        base["band"] = [_quantile(propres, 0.25), _quantile(propres, 0.75)]
    else:
        base["points"] = propres
    return base


def observed_ranges(transactions: Sequence[Transaction], client: Client, *,
                    scoped_preferences: Optional[dict] = None) -> dict:
    maturites = []
    for transaction in transactions:
        debut = _date_iso(transaction.reference_date)
        fin = _date_iso(transaction.maturity_date)
        if debut and fin and fin > debut:
            maturites.append(round((fin - debut).days / 30.44))
    preferences = scoped_preferences or {}
    return {
        "ticket": _borne([t.notional for t in transactions],
                         preferences.get("ticket_min", client.ticket_min),
                         preferences.get("ticket_max", client.ticket_max)),
        "maturity_months": _borne(
                                  maturites,
                                  preferences.get(
                                      "maturity_min_months",
                                      client.maturity_min_months),
                                  preferences.get(
                                      "maturity_max_months",
                                      client.maturity_max_months)),
    }


# ── Les seuils : rendre l'absence actionnable ─────────────────────────

def next_thresholds(cycle: Cycle) -> list[dict]:
    """Ce que le moteur pourra dire, et à partir de combien de transactions.

    Un écran vide qui n'explique pas son vide se fait ignorer. Ces seuils sont
    ceux de `compute_cycle`, lus dans son code — pas une promesse commerciale.
    Ils bougent avec lui ou ils mentent.
    """
    journees = cycle.n_trading_days
    intervalles = cycle.n_intervals
    return [
        {"reached": True, "at": None, "what": "faits_observes",
         "label": "Dernière transaction, délai écoulé, émetteurs sollicités",
         "detail": ("Des faits observés : ils n'exigent aucun historique.")},
        {"reached": intervalles >= 2, "at": max(0, 3 - journees) or None,
         "what": "dispersion",
         "label": "Un deuxième intervalle — la dispersion devient mesurable",
         "detail": ("La fenêtre cesse d'être élargie par défaut et se resserre "
                    "sur l'écart réellement observé.")},
        {"reached": cycle.confidence in ("medium", "high"),
         "at": max(0, 4 - journees) or None, "what": "confiance_moyenne",
         "label": "Confiance moyenne, si la cadence est régulière",
         "detail": ("Trois intervalles et un étalement central sous la moitié de "
                    "la médiane. Irrégulière, la confiance reste basse : le "
                    "volume seul ne suffit pas.")},
        {"reached": cycle.confidence == "high",
         "at": max(0, 7 - journees) or None, "what": "confiance_haute",
         "label": "Confiance haute et cadence nommée",
         "detail": ("Six intervalles et un étalement sous le quart de la "
                    "médiane. C'est là que « trimestrielle » cesse d'être une "
                    "étiquette et devient une mesure.")},
        {"reached": False, "at": None, "what": "import",
         "label": "Un import d'historique fait tout basculer d'un coup",
         "detail": ("Si le client détient son passé dans un classeur, le verser "
                    "le rend immédiatement au moteur. C'est le raccourci prévu "
                    "pour ce cas.")},
    ]


# ── Délai de discussion avant transaction ─────────────────────────────

def lead_time_pairs(session: Session,
                    deals: Sequence[Transaction]) -> list[tuple]:
    """(première discussion, date du trade) pour les trades qui en ont une.

    La première discussion est la plus ancienne interaction du dossier, à
    défaut la date de création de l'opportunité. Un trade booké sans dossier
    n'apporte rien ici — et une ligne d'historique versée non plus, faute
    d'opportunité : le délai de discussion ne s'observe que sur ce qui s'est
    joué chez nous.
    """
    candidates = [deal for deal in deals
                  if deal.opportunity_id is not None
                  and _date_iso(deal.trade_date) is not None]
    opportunity_ids = sorted({deal.opportunity_id for deal in candidates})
    if not opportunity_ids:
        return []
    first_interaction: dict[int, date] = {}
    for interaction in session.exec(
            select(Interaction).where(
                Interaction.opportunity_id.in_(opportunity_ids))).all():
        observed = _date_iso(interaction.interaction_date)
        if observed is None or interaction.opportunity_id is None:
            continue
        previous = first_interaction.get(interaction.opportunity_id)
        if previous is None or observed < previous:
            first_interaction[interaction.opportunity_id] = observed
    opportunities = {
        row.id: row for row in session.exec(
            select(Opportunity).where(Opportunity.id.in_(opportunity_ids))).all()
    }

    paires = []
    for deal in candidates:
        trade = _date_iso(deal.trade_date)
        debut = first_interaction.get(deal.opportunity_id)
        if debut is None:
            opportunite = opportunities.get(deal.opportunity_id)
            debut = opportunite.created_at.date() if opportunite else None
        if debut is not None:
            paires.append((debut, trade))
    return paires


# ── Vues assemblées ───────────────────────────────────────────────────

def person_intelligence(session: Session, person_id: int, *,
                        asof: Optional[date] = None) -> dict:
    """La lecture complète d'une personne : elle, son poste actuel, sa maison.

    C'est le §85 — pouvoir mettre côte à côte ce qu'elle faisait avant, ce
    qu'elle fait ici, et ce que font les autres ici.
    """
    asof = asof or date.today()
    personne = session.get(Person, person_id)
    if personne is None:
        return {}

    affiliations = session.exec(
        select(Affiliation).where(Affiliation.person_id == person_id)).all()
    ids = [a.id for a in affiliations]
    courante = next((a for a in affiliations if a.end_date is None), None)
    client_ids = sorted({row.client_id for row in affiliations})
    client_origins = {
        row.id: row.data_origin for row in session.exec(
            select(Client).where(Client.id.in_(client_ids))).all()
    } if client_ids else {}
    personal_demo = bool(affiliations) and all(
        client_origins.get(row.client_id) == "demo" for row in affiliations)

    deals_personnels = eligible_transactions(
        deals_of_affiliations(session, ids), include_demo=personal_demo)
    cycle_personnel = compute_cycle(_dates_de_trade(deals_personnels), asof=asof)

    if courante is not None:
        current_demo = client_origins.get(courante.client_id) == "demo"
        deals_courants = eligible_transactions(
            deals_of_affiliations(session, [courante.id]),
            include_demo=current_demo)
        cycle_courant = compute_cycle(_dates_de_trade(deals_courants), asof=asof)

        # La maison SANS cette personne : se comparer à un agrégat qui vous
        # contient revient à se comparer en partie à soi-même.
        autres = [a.id for a in session.exec(
            select(Affiliation).where(
                Affiliation.client_id == courante.client_id)).all()
            if a.person_id != person_id]
        deals_maison = eligible_transactions(
            deals_of_affiliations(session, autres), include_demo=current_demo)
        cycle_maison = compute_cycle(_dates_de_trade(deals_maison), asof=asof)
    else:
        deals_courants, deals_maison = [], []
        cycle_courant = compute_cycle([], asof=asof)
        cycle_maison = compute_cycle([], asof=asof)

    delai = observed_lead_days(lead_time_pairs(session, deals_personnels))
    fenetre_contact = recommend_contact_window(
        cycle_courant if cycle_courant.has_history else cycle_personnel,
        lead_days=delai)

    return {
        "person_id": person_id,
        "name": f"{personne.first_name} {personne.last_name}".strip(),
        "current_affiliation_id": courante.id if courante else None,
        "cycles": {
            "personal": cycle_personnel.as_dict(),
            "current_affiliation": cycle_courant.as_dict(),
            "organization": cycle_maison.as_dict(),
        },
        "comparison": compare_cycles(cycle_personnel, cycle_courant, cycle_maison),
        "behaviour": {
            "personal": observed_behaviour(deals_personnels),
            "current_affiliation": observed_behaviour(deals_courants),
            "organization": observed_behaviour(deals_maison),
        },
        "declared": declared_preferences(
            session, client_id=courante.client_id if courante else None,
            affiliation_id=courante.id if courante else None),
        "lost_reasons": lost_reasons(session, affiliation_ids=ids),
        "contact_window": fenetre_contact.as_dict(),
    }


def technical_view(session: Session,
                   transactions: Sequence[Transaction]) -> dict:
    """La lecture technique : ligne à ligne, puis les moyennes par famille.

    Le détail vient AVANT les moyennes, délibérément. Sur un portefeuille de
    dix transactions, la ligne à ligne est la vraie information et la moyenne
    n'est qu'un résumé ; l'inverse ne devient vrai qu'à partir de plusieurs
    dizaines. Présenter la moyenne en tête inviterait à s'y fier trop tôt.
    """
    from .client_technical import (
        catalogue_natures, famille_de_panier, libelle_famille,
        moyennes_par_famille, repartition_execution,
    )

    natures = catalogue_natures(session)
    lignes = []
    for transaction in transactions:
        panier = famille_de_panier(transaction.underlyings, natures)
        lignes.append({
            "source_type": transaction.source_type,
            "source_id": transaction.source_id,
            "trade_date": transaction.trade_date,
            "maturity_date": transaction.maturity_date,
            "reference": transaction.reference,
            "product_type": transaction.product_type,
            "transaction_format": transaction.transaction_format,
            "instrument_family": transaction.instrument_family,
            "payoff_family": transaction.payoff_family,
            "payoff_description": transaction.payoff_description,
            "documentation_reference": transaction.documentation_reference,
            "mandate_id": transaction.mandate_id,
            "affiliation_id": transaction.affiliation_id,
            "data_origin": transaction.data_origin,
            "issuer": transaction.issuer,
            "currency": transaction.currency,
            "notional": transaction.notional,
            "underlyings": transaction.underlyings,
            "coupon_pct": transaction.coupon_pct,
            "protection_pct": transaction.protection_pct,
            "barriers": transaction.barriers,
            "price_pct": transaction.price_pct,
            "traded_with_us": transaction.traded_with_us,
            "imported": transaction.imported,
            "structure": panier["structure"],
            "nature": panier["nature"],
            "partial": panier["partial"],
            "family_label": libelle_famille(panier["structure"], panier["nature"]),
        })
    lignes.sort(key=lambda l: l["trade_date"] or "", reverse=True)

    # Ce que l'écran ne pourra pas montrer, et pourquoi — plutôt que des
    # colonnes vides que personne ne sait interpréter.
    sans_coupon = [l for l in lignes if l["coupon_pct"] is None]
    return {
        "rows": lignes,
        "by_family": moyennes_par_famille(lignes),
        "execution": repartition_execution(lignes),
        "coverage": {
            "n": len(lignes),
            "with_coupon": len(lignes) - len(sans_coupon),
            "with_protection": len([l for l in lignes
                                    if l["protection_pct"] is not None]),
            "unclassified_underlying": len([l for l in lignes
                                            if l["nature"] is None]),
        },
    }


def _rfqs_du_client(
    session: Session,
    client_id: int,
    opportunity_ids: Sequence[int],
    *, mandate_id: Optional[int] = None,
    affiliation_id: Optional[int] = None,
) -> list[dict]:
    """RFQs explicitly attributed to the Client, directly or via Opportunity."""
    from ..db.models import RfqRequest
    lignes = session.exec(
        select(RfqRequest).where(RfqRequest.client_id == client_id)).all()
    by_id = {row.id: row for row in lignes}
    if opportunity_ids:
        inherited = session.exec(
            select(RfqRequest).where(
                RfqRequest.opportunity_id.in_(list(opportunity_ids)))).all()
        by_id.update({row.id: row for row in inherited})
    rows = list(by_id.values())
    if mandate_id is not None:
        rows = [row for row in rows if row.mandate_id == mandate_id]
    if affiliation_id is not None:
        rows = [row for row in rows
                if row.primary_affiliation_id == affiliation_id]
    return sorted(
        ({"id": r.id, "reference": r.reference, "name": r.name,
          "status": r.status, "kind": r.kind, "ao_date": r.ao_date,
          "opportunity_id": r.opportunity_id, "model_price": r.model_price,
          "mandate_id": r.mandate_id,
          "primary_affiliation_id": r.primary_affiliation_id,
          "transaction_format": r.transaction_format,
          "instrument_family": r.instrument_family,
          "payoff_family": r.payoff_family}
         for r in rows),
        key=lambda d: d["ao_date"] or "", reverse=True)


def client_intelligence(
    session: Session, client_id: int, *, asof: Optional[date] = None,
    mandate_id: Optional[int] = None, affiliation_id: Optional[int] = None,
    include_demo: Optional[bool] = None,
) -> dict:
    """A scoped, auditable profile; Client aggregation never hides mandates."""
    asof = asof or date.today()
    client = session.get(Client, client_id)
    if client is None:
        return {}

    # A demo Client is an explicit demonstration context.  A real/imported
    # Client excludes UAT facts unless a diagnostic caller explicitly asks to
    # inspect them.
    include_demo = client.data_origin == "demo" if include_demo is None else include_demo
    all_transactions = deals_of_client(session, client_id)
    transactions = eligible_transactions(
        all_transactions, include_demo=include_demo)
    excluded_demo_count = len(all_transactions) - len(transactions)

    mandates = list(session.exec(
        select(ClientMandate).where(ClientMandate.client_id == client_id)).all())
    mandate_map = {row.id: row for row in mandates}
    affiliations = list(session.exec(
        select(Affiliation).where(Affiliation.client_id == client_id)).all())
    affiliation_map = {row.id: row for row in affiliations}
    person_ids = [row.person_id for row in affiliations]
    people = {
        row.id: row for row in session.exec(
            select(Person).where(Person.id.in_(person_ids))).all()
    } if person_ids else {}

    scoped = transactions
    scope_kind = "client"
    scope_name = client.name
    if mandate_id is not None:
        scoped = [row for row in scoped if row.mandate_id == mandate_id]
        scope_kind = "mandate"
        scope_name = mandate_map.get(mandate_id).name if mandate_id in mandate_map else None
    if affiliation_id is not None:
        scoped = [row for row in scoped if row.affiliation_id == affiliation_id]
        scope_kind = "affiliation" if mandate_id is None else "mandate_affiliation"
        affiliation = affiliation_map.get(affiliation_id)
        person = people.get(affiliation.person_id) if affiliation else None
        contact_name = (f"{person.first_name} {person.last_name}".strip()
                        if person else None)
        scope_name = (f"{scope_name} · {contact_name}"
                      if mandate_id is not None and scope_name and contact_name
                      else contact_name)

    cycle = compute_cycle(_dates_de_trade(scoped), asof=asof)
    per_contact = []
    for affiliation in affiliations:
        contact_transactions = [
            row for row in transactions if row.affiliation_id == affiliation.id]
        if not contact_transactions:
            continue
        person = people.get(affiliation.person_id)
        per_contact.append({
            "affiliation_id": affiliation.id,
            "person_id": affiliation.person_id,
            "name": (f"{person.first_name} {person.last_name}".strip()
                     if person else None),
            "is_current": affiliation.end_date is None,
            "cycle": compute_cycle(
                _dates_de_trade(contact_transactions), asof=asof).as_dict(),
            "behaviour": observed_behaviour(contact_transactions),
        })

    per_mandate = []
    for mandate in mandates:
        mandate_transactions = [
            row for row in transactions if row.mandate_id == mandate.id]
        per_mandate.append({
            "mandate_id": mandate.id,
            "name": mandate.name,
            "mandate_type": mandate.mandate_type,
            "status": mandate.status,
            "behaviour": observed_behaviour(mandate_transactions),
            "recency": recency_level(
                max((row.trade_date for row in mandate_transactions
                     if row.trade_date), default=None), asof=asof),
        })
    per_mandate.sort(key=lambda row: (-row["behaviour"]["n_trades"],
                                      row["name"].casefold()))

    declared = declared_preferences(
        session, client_id=client_id, mandate_id=mandate_id,
        affiliation_id=affiliation_id, asof=asof)
    current_preferences = dict(declared.get("client") or {})
    current_preferences.update(declared.get("client_scalars") or {})
    current_preferences.update(declared.get("mandate") or {})
    current_preferences.update(declared.get("affiliation") or {})
    current_preferences.update(declared.get("combined") or {})

    dossiers = list(session.exec(
        select(Opportunity).where(Opportunity.client_id == client_id)).all())
    if not include_demo:
        dossiers = [row for row in dossiers if row.data_origin != "demo"]
    scoped_dossiers = dossiers
    if mandate_id is not None:
        scoped_dossiers = [row for row in scoped_dossiers
                           if row.mandate_id == mandate_id]
    if affiliation_id is not None:
        scoped_dossiers = [row for row in scoped_dossiers
                           if row.primary_affiliation_id == affiliation_id]
    won = [row for row in scoped_dossiers if row.status == "won"]
    lost = [row for row in scoped_dossiers if row.status == "lost"]
    decided = len(won) + len(lost)

    lead = observed_lead_days(lead_time_pairs(session, scoped))
    provider_analysis = provider_selection_analysis(scoped, asof=asof)
    return {
        "client_id": client_id,
        "name": client.name,
        "asof": asof.isoformat(),
        "analysis_mode": "demo" if include_demo else "real",
        "excluded_demo_count": excluded_demo_count,
        "scope": {
            "kind": scope_kind, "name": scope_name,
            "client_id": client_id, "mandate_id": mandate_id,
            "affiliation_id": affiliation_id,
        },
        "scope_options": {
            "mandates": [{"id": row.id, "name": row.name,
                           "status": row.status} for row in mandates],
            "contacts": [{
                "affiliation_id": row.id,
                "name": ((f"{people[row.person_id].first_name} "
                          f"{people[row.person_id].last_name}").strip()
                         if row.person_id in people else None),
                "is_current": row.end_date is None,
            } for row in affiliations],
        },
        "cycle": cycle.as_dict(),
        "behaviour": observed_behaviour(scoped),
        "habits": habit_dimensions(scoped, asof=asof),
        "recency": recency_level(cycle.last_trade_date, asof=asof),
        "declared": declared,
        "preference_history": preference_history(
            session, client_id=client_id, mandate_id=mandate_id,
            affiliation_id=affiliation_id),
        "lost_reasons": Counter(
            row.lost_reason for row in scoped_dossiers
            if row.status == "lost" and row.lost_reason).most_common(),
        "contact_window": recommend_contact_window(
            cycle, lead_days=lead).as_dict(),
        "negative_space": negative_space(scoped, current_preferences),
        "ranges": observed_ranges(
            scoped, client, scoped_preferences=current_preferences),
        "thresholds": next_thresholds(cycle),
        "conversion": {
            "won": len(won), "lost": len(lost), "decided": decided,
            "rate": (len(won) / decided) if decided else None,
        },
        "provider_selection": provider_analysis,
        "questions": provider_analysis["questions"],
        "technical": technical_view(session, scoped),
        "rfqs": _rfqs_du_client(
            session, client_id, [row.id for row in dossiers],
            mandate_id=mandate_id, affiliation_id=affiliation_id),
        "transactions": sorted(({
            "source_type": row.source_type,
            "source_id": row.source_id,
            "reference": row.reference,
            "trade_date": row.trade_date,
            "maturity_date": row.maturity_date,
            "transaction_format": row.transaction_format,
            "instrument_family": row.instrument_family,
            "payoff_family": row.payoff_family,
            "payoff_description": row.payoff_description,
            "documentation_reference": row.documentation_reference,
            "product_type": row.product_type,
            "issuer": row.issuer,
            "currency": row.currency,
            "notional": row.notional,
            "underlyings": row.underlyings,
            "imported": row.imported,
            "data_origin": row.data_origin,
            "mandate_id": row.mandate_id,
            "mandate_name": (mandate_map[row.mandate_id].name
                             if row.mandate_id in mandate_map else None),
            "affiliation_id": row.affiliation_id,
        } for row in scoped), key=lambda row: row["trade_date"] or "", reverse=True),
        "per_mandate": per_mandate,
        "mandate_divergences": mandate_divergences(per_mandate),
        "unassigned_mandate_count": sum(
            row.mandate_id is None for row in transactions),
        "per_contact": sorted(
            per_contact, key=lambda row: -row["behaviour"]["n_trades"]),
    }
