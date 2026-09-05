"""Import d'historique commercial — le format, sa validation, son versement.

Un client arrive avec un passé stocké ailleurs. Ce module le fait entrer sans
que personne n'ait à ressaisir cinq ans de relation.

**Un seul classeur, six feuilles, dans l'ordre des dépendances.** Un client
doit exister avant la personne qui y travaille, qui doit exister avant sa
transaction. Des fichiers séparés obligeraient à respecter cet ordre à la
main, et à découvrir l'erreur au troisième. Une feuille par objet dans un même
classeur — ou un objet JSON à six tableaux — résout l'ordonnancement tout
seul, et tout entre dans une transaction unique.

**Rien ne s'écrit sans avoir été montré.** `analyser()` lit, valide, résout les
correspondances et rend un compte rendu ligne à ligne, puis annule tout : la
base n'est pas touchée. Il suit exactement le même chemin que `appliquer()` —
un chemin unique, écrivant dans la session, dont seule la fin diffère
(`rollback` ou `commit`). Une version antérieure validait « sans écrire » et
sautait de ce fait tous les contrôles qui ont besoin d'un identifiant :
l'aperçu approuvait ce que le versement refusait ensuite.

**Tout est réversible.** Chaque ligne créée porte l'identifiant de son lot. Un
fichier mal formaté versé sur une base peuplée se défait, au lieu d'y laisser
des lignes qu'on ne saurait plus distinguer des vraies.

**Rapprocher plutôt que dupliquer.** Un client déjà connu par son nom, une
personne déjà connue par son e-mail ne sont pas recréés : ils sont retrouvés et
complétés. Sans cela, un second import du même fichier doublerait le référentiel
en silence — le pire résultat possible pour un outil censé consolider.
"""
from __future__ import annotations

import io
import json
import re
from dataclasses import dataclass, field, asdict
from datetime import date, datetime
from typing import Any, Optional

from sqlmodel import Session, select

from ..db.models import (
    Affiliation, Client, ClientImportBatch, ClientMandate, ClientTradeHistory,
    Interaction, Person,
)
from .client_controls import (
    CLIENT_STATUSES, CLIENT_TYPES, COMMERCIAL_ROLES, INTERACTION_TYPES,
    MANDATE_TYPES,
)

# ── Le format canonique ───────────────────────────────────────────────
# Une feuille par objet. Les colonnes obligatoires sont marquées ; les autres
# peuvent manquer ou rester vides. L'ordre des colonnes n'importe pas — c'est
# l'en-tête qui fait foi, parce qu'un export d'un autre outil ne respectera
# jamais un ordre imposé.

FEUILLES = (
    "clients", "mandates", "contacts", "affiliations", "transactions",
    "interactions",
)

SCHEMA: dict[str, dict] = {
    "clients": {
        "requis": ["name"],
        "colonnes": ["name", "legal_name", "client_type", "country", "status",
                     "external_ref", "notes"],
        "libelle": "Sociétés clientes",
    },
    "mandates": {
        "requis": ["client_name", "name"],
        "colonnes": ["client_name", "name", "mandate_type",
                     "reference_currency", "comment"],
        "libelle": "Mandats, fonds, comptes ou desks",
    },
    "contacts": {
        "requis": ["last_name"],
        "colonnes": ["first_name", "last_name", "email", "phone", "notes"],
        "libelle": "Personnes",
    },
    "affiliations": {
        # La feuille qui porte tout l'intérêt du module : le passé
        # professionnel, celui qu'aucun outil ne conserve et qu'on ne peut pas
        # reconstituer après coup.
        "requis": ["person_email_or_name", "client_name", "start_date"],
        "colonnes": ["person_email_or_name", "client_name", "job_title",
                     "commercial_role", "start_date", "end_date", "notes"],
        "libelle": "Parcours professionnels",
    },
    "transactions": {
        "requis": ["client_name", "trade_date"],
        "colonnes": ["client_name", "mandate_name", "person_email_or_name",
                     "trade_date", "maturity_date", "transaction_format",
                     "instrument_family", "payoff_family", "payoff_description",
                     "documentation_reference", "product_type", "underlying", "issuer",
                     "currency", "notional", "coupon_pct", "barrier_pct",
                     "traded_with_us", "price_pct", "external_ref", "notes"],
        "libelle": "Transactions passées",
    },
    "interactions": {
        "requis": ["client_name", "interaction_date"],
        "colonnes": ["client_name", "interaction_date", "interaction_type",
                     "summary", "notes"],
        "libelle": "Échanges passés",
    },
}

EXEMPLES: dict[str, list[dict]] = {
    "clients": [{
        "name": "ABC Asset Management", "legal_name": "ABC Asset Management SA",
        "client_type": "asset_manager", "country": "Suisse", "status": "active",
        "external_ref": "LEI-123456", "notes": "Comité produit mensuel",
    }],
    "mandates": [{
        "client_name": "ABC Asset Management",
        "name": "Fonds Europe Rendement", "mandate_type": "fund",
        "reference_currency": "EUR", "comment": "Périmètre principal",
    }],
    "contacts": [{
        "first_name": "Jean", "last_name": "Dupont",
        "email": "jean.dupont@abc-am.ch", "phone": "+41 22 000 00 00",
        "notes": "Préfère les structures défensives",
    }],
    "affiliations": [
        {"person_email_or_name": "jean.dupont@abc-am.ch",
         "client_name": "ABC Asset Management", "job_title": "Gérant",
         "commercial_role": "portfolio_manager", "start_date": "2022-01-01",
         "end_date": "", "notes": ""},
    ],
    "transactions": [{
        "client_name": "ABC Asset Management",
        "mandate_name": "Fonds Europe Rendement",
        "person_email_or_name": "jean.dupont@abc-am.ch",
        "trade_date": "2024-03-15", "maturity_date": "2027-03-15",
        "transaction_format": "EMTN", "instrument_family": "Note",
        "payoff_family": "Autocall", "payoff_description": "Athena 3Y",
        "documentation_reference": "Programme EMTN ABC",
        "product_type": "Autocall Athena", "underlying": "SX5E",
        "issuer": "BNP Paribas", "currency": "EUR", "notional": 1000000,
        "coupon_pct": 7.5, "barrier_pct": 60,
        "traded_with_us": "non", "price_pct": 98.5,
        "external_ref": "XS1234567890", "notes": "",
    }],
    "interactions": [{
        "client_name": "ABC Asset Management", "interaction_date": "2024-02-01",
        "interaction_type": "meeting", "summary": "Revue de book annuelle",
        "notes": "",
    }],
}

VOCABULAIRES = {
    "client_type": sorted(CLIENT_TYPES),
    "status": sorted(CLIENT_STATUSES),
    "commercial_role": sorted(COMMERCIAL_ROLES),
    "interaction_type": sorted(INTERACTION_TYPES),
    "mandate_type": sorted(MANDATE_TYPES),
}


# ── Compte rendu ──────────────────────────────────────────────────────

@dataclass
class Anomalie:
    feuille: str
    ligne: int          # numéro dans le fichier, en-tête comprise
    champ: Optional[str]
    message: str

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class Rapport:
    """Ce qu'un import ferait, ou vient de faire."""
    a_creer: dict[str, int] = field(default_factory=dict)
    a_mettre_a_jour: dict[str, int] = field(default_factory=dict)
    ignorees: dict[str, int] = field(default_factory=dict)
    anomalies: list[Anomalie] = field(default_factory=list)
    feuilles_lues: list[str] = field(default_factory=list)
    feuilles_inconnues: list[str] = field(default_factory=list)

    @property
    def bloquant(self) -> bool:
        return bool(self.anomalies)

    def as_dict(self) -> dict:
        return {
            "created": self.a_creer, "updated": self.a_mettre_a_jour,
            "skipped": self.ignorees,
            "issues": [a.as_dict() for a in self.anomalies],
            "sheets_read": self.feuilles_lues,
            "unknown_sheets": self.feuilles_inconnues,
            "blocking": self.bloquant,
            "total_created": sum(self.a_creer.values()),
            "total_updated": sum(self.a_mettre_a_jour.values()),
            "total_skipped": sum(self.ignorees.values()),
        }


class ImportError_(Exception):
    """Le fichier n'est pas lisible du tout — distinct d'une ligne fautive."""
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


# ── Lecture des deux formats ──────────────────────────────────────────

def _normaliser_entete(valeur: Any) -> str:
    """Un en-tête tolérant : « Nom du client », « client_name », « CLIENT NAME »
    désignent la même colonne. Un export d'un autre outil ne respectera jamais
    notre casse ni nos underscores."""
    texte = str(valeur or "").strip().casefold()
    texte = texte.replace("’", "'")
    return re.sub(r"[^a-z0-9]+", "_", texte).strip("_")


def _cellule(valeur: Any) -> Any:
    """Une cellule vide, quelle que soit sa forme, vaut None."""
    if valeur is None:
        return None
    if isinstance(valeur, str):
        nettoye = valeur.strip()
        return nettoye or None
    return valeur


def lire_classeur(contenu: bytes) -> tuple[dict[str, list[dict]], list[str]]:
    """Rend {feuille: [lignes]} et la liste des feuilles non reconnues."""
    try:
        from openpyxl import load_workbook
        classeur = load_workbook(io.BytesIO(contenu), data_only=True, read_only=True)
    except Exception as erreur:
        raise ImportError_(f"Classeur illisible : {erreur}")

    donnees: dict[str, list[dict]] = {}
    inconnues: list[str] = []
    for nom in classeur.sheetnames:
        cle = _normaliser_entete(nom)
        if cle not in SCHEMA:
            inconnues.append(nom)
            continue
        feuille = classeur[nom]
        lignes_brutes = list(feuille.iter_rows(values_only=True))
        if not lignes_brutes:
            donnees[cle] = []
            continue
        entete = [_normaliser_entete(c) for c in lignes_brutes[0]]
        lignes = []
        for index, brute in enumerate(lignes_brutes[1:], start=2):
            ligne = {entete[i]: _cellule(v)
                     for i, v in enumerate(brute) if i < len(entete) and entete[i]}
            # Une ligne entièrement vide n'est pas une erreur : les classeurs
            # en portent toujours quelques-unes après la dernière saisie.
            if any(v is not None for v in ligne.values()):
                ligne["__ligne__"] = index
                lignes.append(ligne)
        donnees[cle] = lignes
    classeur.close()
    return donnees, inconnues


def lire_json(contenu: bytes) -> tuple[dict[str, list[dict]], list[str]]:
    try:
        charge = json.loads(contenu.decode("utf-8-sig"))
    except Exception as erreur:
        raise ImportError_(f"JSON illisible : {erreur}")
    if not isinstance(charge, dict):
        raise ImportError_(
            "Le JSON doit être un objet dont les clés sont les sections "
            f"({', '.join(FEUILLES)}), chacune portant un tableau.")

    donnees: dict[str, list[dict]] = {}
    inconnues: list[str] = []
    for nom, valeur in charge.items():
        cle = _normaliser_entete(nom)
        if cle not in SCHEMA:
            inconnues.append(nom)
            continue
        if not isinstance(valeur, list):
            raise ImportError_(f"La section « {nom} » doit être un tableau.")
        lignes = []
        for index, brute in enumerate(valeur, start=1):
            if not isinstance(brute, dict):
                raise ImportError_(
                    f"La section « {nom} », entrée {index} : un objet est attendu.")
            ligne = {_normaliser_entete(k): _cellule(v) for k, v in brute.items()}
            ligne["__ligne__"] = index
            lignes.append(ligne)
        donnees[cle] = lignes
    return donnees, inconnues


# ── Validation ────────────────────────────────────────────────────────

def _date_ou_none(valeur: Any) -> Optional[str]:
    """Excel rend parfois un datetime, parfois une chaîne. Les deux sont
    acceptés ; tout le reste est refusé plutôt que deviné."""
    if valeur is None:
        return None
    if isinstance(valeur, (datetime, date)):
        return valeur.date().isoformat() if isinstance(valeur, datetime) else valeur.isoformat()
    texte = str(valeur).strip()
    if not texte:
        return None
    for motif in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(texte[:10], motif).date().isoformat()
        except ValueError:
            continue
    raise ValueError(f"« {valeur} » n'est pas une date reconnue "
                     f"(attendu AAAA-MM-JJ ou JJ/MM/AAAA)")


def _nombre_ou_none(valeur: Any) -> Optional[float]:
    if valeur is None:
        return None
    if isinstance(valeur, (int, float)):
        return float(valeur)
    texte = str(valeur).strip().replace(" ", "").replace(" ", "")
    texte = texte.replace("%", "").replace(",", ".")
    if not texte:
        return None
    try:
        return float(texte)
    except ValueError:
        raise ValueError(f"« {valeur} » n'est pas un nombre")


_OUI = {"oui", "o", "yes", "y", "true", "vrai", "1", "avec nous", "nous"}
_NON = {"non", "n", "no", "false", "faux", "0", "ailleurs", "concurrent"}


def _oui_non_ou_none(valeur: Any) -> Optional[bool]:
    """Trois états, pas deux.

    Une cellule vide vaut `None` — « on ne sait pas » — et surtout PAS « non ».
    Présumer qu'un historique muet a été traité ailleurs gonflerait la part de
    marché qu'on croit ne pas avoir, et fausserait exactement la lecture pour
    laquelle cette colonne existe.
    """
    if valeur is None:
        return None
    if isinstance(valeur, bool):
        return valeur
    texte = _normaliser_entete(valeur).replace("_", " ")
    if not texte:
        return None
    if texte in _OUI:
        return True
    if texte in _NON:
        return False
    raise ValueError(
        f"« {valeur} » n'est ni oui ni non. Laissez vide si vous ne savez pas — "
        f"une case vide veut dire « inconnu », pas « ailleurs ».")


def _vocabulaire(valeur: Any, champ: str, defaut: str) -> str:
    if valeur is None:
        return defaut
    candidat = _normaliser_entete(valeur)
    accepte = VOCABULAIRES.get(champ, [])
    if candidat in accepte:
        return candidat
    raise ValueError(f"« {valeur} » inconnu pour {champ}. "
                     f"Valeurs acceptées : {', '.join(accepte)}")


# ── Résolution des correspondances ────────────────────────────────────

def _cle_nom(valeur: Any) -> str:
    return " ".join(str(valeur or "").strip().casefold().split())


class Resolveur:
    """Retrouve ce qui existe déjà, pour compléter au lieu de dupliquer.

    Construit une fois par import, puis alimenté au fil des créations : une
    personne créée par la feuille « contacts » doit être trouvable par la
    feuille « affiliations » du même fichier, avant tout commit.
    """

    def __init__(self, session: Session, entity_id: Optional[int]):
        self.session = session
        self.entity_id = entity_id
        self.clients: dict[str, Any] = {}
        self.personnes: dict[str, Any] = {}
        self.mandats: dict[tuple[int, str], Any] = {}
        for client in session.exec(
                select(Client).where(Client.entity_id == entity_id)).all():
            self.clients[_cle_nom(client.name)] = client
            if client.legal_name:
                self.clients.setdefault(_cle_nom(client.legal_name), client)
        for personne in session.exec(
                select(Person).where(Person.entity_id == entity_id)).all():
            if personne.email:
                self.personnes[_cle_nom(personne.email)] = personne
            self.personnes.setdefault(
                _cle_nom(f"{personne.first_name} {personne.last_name}"), personne)
        for mandat in session.exec(
                select(ClientMandate).where(ClientMandate.entity_id == entity_id)).all():
            self.mandats[(mandat.client_id, _cle_nom(mandat.name))] = mandat

    def client(self, nom: Any):
        return self.clients.get(_cle_nom(nom))

    def personne(self, cle: Any):
        return self.personnes.get(_cle_nom(cle))

    def mandat(self, client_id: int, nom: Any):
        return self.mandats.get((client_id, _cle_nom(nom)))

    def enregistrer_client(self, client):
        self.clients[_cle_nom(client.name)] = client

    def enregistrer_personne(self, personne):
        if personne.email:
            self.personnes[_cle_nom(personne.email)] = personne
        self.personnes[_cle_nom(f"{personne.first_name} {personne.last_name}")] = personne

    def enregistrer_mandat(self, mandate):
        self.mandats[(mandate.client_id, _cle_nom(mandate.name))] = mandate


# ── Le traitement, commun à l'aperçu et au versement ──────────────────

def _traiter(session: Session, donnees: dict[str, list[dict]],
             inconnues: list[str], *, entity_id: Optional[int], user_id: int,
             batch_id: Optional[int] = None) -> Rapport:
    """Le traitement, identique pour l'aperçu et le versement.

    Il ÉCRIT toujours dans la session, et c'est l'appelant qui décide : un
    `rollback()` en fait un import à blanc, un `commit()` en fait un versement.

    Ce n'est pas un détail d'implémentation. Une première version validait sans
    écrire, et sautait donc tous les contrôles qui ont besoin d'un identifiant —
    en particulier le rattachement d'une transaction au passage professionnel
    qui couvre sa date, puisque la personne venait d'être « créée » sans jamais
    recevoir d'id. L'aperçu approuvait alors ce que le versement refusait
    ensuite. Deux chemins finissent toujours par diverger ; il n'y en a plus
    qu'un.
    """
    rapport = Rapport(feuilles_lues=[f for f in FEUILLES if f in donnees],
                      feuilles_inconnues=inconnues)
    resolveur = Resolveur(session, entity_id)

    def compter(dico: dict, feuille: str):
        dico[feuille] = dico.get(feuille, 0) + 1

    def anomalie(feuille, ligne, champ, message):
        rapport.anomalies.append(Anomalie(feuille, ligne, champ, message))

    # ── clients ──────────────────────────────────────────────────────
    for ligne in donnees.get("clients", []):
        numero = ligne.get("__ligne__", 0)
        nom = ligne.get("name")
        if not nom:
            anomalie("clients", numero, "name", "Le nom de la société est requis.")
            continue
        existant = resolveur.client(nom)
        try:
            type_client = _vocabulaire(ligne.get("client_type"), "client_type", "other")
            statut = _vocabulaire(ligne.get("status"), "status", "prospect")
        except ValueError as erreur:
            anomalie("clients", numero, "client_type/status", str(erreur))
            continue

        if existant is not None:
            compter(rapport.a_mettre_a_jour, "clients")
            # On complète les vides, on n'écrase jamais une saisie faite dans
            # l'outil : le fichier est une source d'appoint, pas la vérité qui
            # prime.
            for champ, valeur in (("legal_name", ligne.get("legal_name")),
                                  ("country", ligne.get("country")),
                                  ("external_ref", ligne.get("external_ref")),
                                  ("notes", ligne.get("notes"))):
                if valeur and not getattr(existant, champ):
                    setattr(existant, champ, str(valeur))
            existant.updated_at = datetime.utcnow()
            session.add(existant)
            continue

        compter(rapport.a_creer, "clients")
        client = Client(
            entity_id=entity_id, name=str(nom).strip(),
            legal_name=ligne.get("legal_name"), client_type=type_client,
            country=ligne.get("country"), status=statut,
            external_ref=ligne.get("external_ref"), notes=ligne.get("notes"),
            data_origin="imported",
            created_by_user_id=user_id)
        session.add(client)
        session.flush()
        resolveur.enregistrer_client(client)

    # ── mandats / fonds / comptes / desks ──────────────────────────
    for ligne in donnees.get("mandates", []):
        numero = ligne.get("__ligne__", 0)
        client = resolveur.client(ligne.get("client_name"))
        name = str(ligne.get("name") or "").strip()
        if client is None:
            anomalie(
                "mandates", numero, "client_name",
                f"Société « {ligne.get('client_name')} » introuvable.")
            continue
        if not name:
            anomalie("mandates", numero, "name", "Le nom du périmètre est requis.")
            continue
        try:
            mandate_type = _vocabulaire(
                ligne.get("mandate_type"), "mandate_type", "mandate")
        except ValueError as erreur:
            anomalie("mandates", numero, "mandate_type", str(erreur))
            continue
        existing = resolveur.mandat(client.id, name)
        if existing is not None:
            compter(rapport.ignorees, "mandates")
            continue
        compter(rapport.a_creer, "mandates")
        mandate = ClientMandate(
            entity_id=entity_id, client_id=client.id, name=name,
            mandate_type=mandate_type, status="active",
            reference_currency=(str(ligne.get("reference_currency")).strip()
                                if ligne.get("reference_currency") else None),
            comment=ligne.get("comment"), data_origin="imported",
            created_by_user_id=user_id)
        session.add(mandate)
        session.flush()
        resolveur.enregistrer_mandat(mandate)

    # ── contacts ─────────────────────────────────────────────────────
    for ligne in donnees.get("contacts", []):
        numero = ligne.get("__ligne__", 0)
        nom = ligne.get("last_name")
        if not nom:
            anomalie("contacts", numero, "last_name", "Le nom est requis.")
            continue
        prenom = ligne.get("first_name") or ""
        email = ligne.get("email")
        existant = (resolveur.personne(email) if email
                    else resolveur.personne(f"{prenom} {nom}"))
        if existant is not None:
            compter(rapport.a_mettre_a_jour, "contacts")
            for champ, valeur in (("email", email), ("phone", ligne.get("phone")),
                                  ("notes", ligne.get("notes"))):
                if valeur and not getattr(existant, champ):
                    setattr(existant, champ, str(valeur))
            existant.updated_at = datetime.utcnow()
            session.add(existant)
            continue

        compter(rapport.a_creer, "contacts")
        personne = Person(entity_id=entity_id, first_name=str(prenom).strip(),
                          last_name=str(nom).strip(),
                          email=str(email) if email else None,
                          phone=ligne.get("phone"), notes=ligne.get("notes"),
                          created_by_user_id=user_id)
        session.add(personne)
        session.flush()
        resolveur.enregistrer_personne(personne)

    # ── affiliations ─────────────────────────────────────────────────
    for ligne in donnees.get("affiliations", []):
        numero = ligne.get("__ligne__", 0)
        cle_personne = ligne.get("person_email_or_name")
        nom_client = ligne.get("client_name")
        if not cle_personne or not nom_client:
            anomalie("affiliations", numero, None,
                     "La personne et la société sont toutes deux requises.")
            continue
        personne = resolveur.personne(cle_personne)
        client = resolveur.client(nom_client)
        if personne is None:
            anomalie("affiliations", numero, "person_email_or_name",
                     f"Personne « {cle_personne} » introuvable — ajoutez-la à la "
                     f"feuille « contacts » ou vérifiez l'orthographe.")
            continue
        if client is None:
            anomalie("affiliations", numero, "client_name",
                     f"Société « {nom_client} » introuvable — ajoutez-la à la "
                     f"feuille « clients ».")
            continue
        try:
            debut = _date_ou_none(ligne.get("start_date"))
            fin = _date_ou_none(ligne.get("end_date"))
            role = _vocabulaire(ligne.get("commercial_role"), "commercial_role", "other")
        except ValueError as erreur:
            anomalie("affiliations", numero, "start_date/end_date/commercial_role",
                     str(erreur))
            continue
        if not debut:
            anomalie("affiliations", numero, "start_date",
                     "La date de début est requise.")
            continue
        if fin and fin < debut:
            anomalie("affiliations", numero, "end_date",
                     "La date de fin est antérieure à la date de début.")
            continue

        # Le même passage déjà présent ne se recrée pas — c'est ce qui rend un
        # second import du même fichier inoffensif.
        deja = None
        if personne.id is not None and client.id is not None:
            deja = session.exec(
                select(Affiliation).where(
                    Affiliation.person_id == personne.id,
                    Affiliation.client_id == client.id,
                    Affiliation.start_date == debut)).first()
        if deja is not None:
            compter(rapport.ignorees, "affiliations")
            continue

        compter(rapport.a_creer, "affiliations")
        session.add(Affiliation(
            person_id=personne.id, client_id=client.id,
            job_title=str(ligne.get("job_title") or ""),
            commercial_role=role, start_date=debut, end_date=fin,
            notes=ligne.get("notes")))
        # Flush immédiat : la feuille des transactions, juste après, cherche le
        # passage qui couvre sa date. Sans identifiant, elle ne trouverait rien.
        session.flush()

    # ── transactions ─────────────────────────────────────────────────
    for ligne in donnees.get("transactions", []):
        numero = ligne.get("__ligne__", 0)
        nom_client = ligne.get("client_name")
        if not nom_client:
            anomalie("transactions", numero, "client_name",
                     "La société est requise.")
            continue
        client = resolveur.client(nom_client)
        if client is None:
            anomalie("transactions", numero, "client_name",
                     f"Société « {nom_client} » introuvable.")
            continue
        try:
            jour = _date_ou_none(ligne.get("trade_date"))
            maturite = _date_ou_none(ligne.get("maturity_date"))
            nominal = _nombre_ou_none(ligne.get("notional"))
            coupon = _nombre_ou_none(ligne.get("coupon_pct"))
            barriere = _nombre_ou_none(ligne.get("barrier_pct"))
            prix = _nombre_ou_none(ligne.get("price_pct"))
            avec_nous = _oui_non_ou_none(ligne.get("traded_with_us"))
        except ValueError as erreur:
            anomalie("transactions", numero, None, str(erreur))
            continue
        if not jour:
            anomalie("transactions", numero, "trade_date",
                     "La date de transaction est requise — c'est elle qui porte "
                     "toute la cadence.")
            continue
        if maturite and maturite < jour:
            anomalie("transactions", numero, "maturity_date",
                     "La maturité est antérieure à la transaction.")
            continue

        mandate_id = None
        mandate_name = ligne.get("mandate_name")
        if mandate_name:
            mandate = resolveur.mandat(client.id, mandate_name)
            if mandate is None:
                anomalie(
                    "transactions", numero, "mandate_name",
                    f"Mandat ou périmètre « {mandate_name} » introuvable pour "
                    f"« {nom_client} ». Créez-le dans la fiche Client avant l'import.")
                continue
            mandate_id = mandate.id

        # Rattachement à l'affiliation EN VIGUEUR À LA DATE DU TRADE, pas à
        # l'actuelle : c'est ce qui place une transaction de 2024 chez
        # l'employeur de 2024, y compris quand la personne a changé depuis.
        affiliation_id = None
        cle_personne = ligne.get("person_email_or_name")
        if cle_personne:
            personne = resolveur.personne(cle_personne)
            if personne is None:
                anomalie("transactions", numero, "person_email_or_name",
                         f"Personne « {cle_personne} » introuvable.")
                continue
            if personne.id is not None and client.id is not None:
                candidates = session.exec(
                    select(Affiliation).where(
                        Affiliation.person_id == personne.id,
                        Affiliation.client_id == client.id)).all()
                retenue = next(
                    (a for a in candidates
                     if (a.start_date or "") <= jour
                     and (a.end_date is None or a.end_date >= jour)), None)
                if retenue is None:
                    anomalie("transactions", numero, "person_email_or_name",
                             f"Aucun passage de cette personne chez « {nom_client} » "
                             f"ne couvre le {jour}. Vérifiez les dates du parcours.")
                    continue
                affiliation_id = retenue.id

        reference = ligne.get("external_ref")
        if reference and client.id is not None:
            doublon = session.exec(
                select(ClientTradeHistory).where(
                    ClientTradeHistory.client_id == client.id,
                    ClientTradeHistory.external_ref == str(reference))).first()
            if doublon is not None:
                compter(rapport.ignorees, "transactions")
                continue

        compter(rapport.a_creer, "transactions")
        session.add(ClientTradeHistory(
                entity_id=entity_id, import_batch_id=batch_id,
                client_id=client.id, affiliation_id=affiliation_id,
                mandate_id=mandate_id,
                trade_date=jour, maturity_date=maturite,
                product_type=str(ligne.get("product_type") or ""),
                transaction_format=ligne.get("transaction_format"),
                instrument_family=ligne.get("instrument_family"),
                payoff_family=ligne.get("payoff_family"),
                payoff_description=ligne.get("payoff_description"),
                documentation_reference=ligne.get("documentation_reference"),
                underlying=ligne.get("underlying"), issuer=ligne.get("issuer"),
                currency=str(ligne.get("currency") or "EUR"),
                notional=nominal, coupon_pct=coupon, barrier_pct=barriere,
            traded_with_us=avec_nous, price_pct=prix,
            external_ref=str(reference) if reference else None,
            notes=ligne.get("notes")))
        session.flush()

    # ── interactions ─────────────────────────────────────────────────
    for ligne in donnees.get("interactions", []):
        numero = ligne.get("__ligne__", 0)
        nom_client = ligne.get("client_name")
        client = resolveur.client(nom_client) if nom_client else None
        if client is None:
            anomalie("interactions", numero, "client_name",
                     f"Société « {nom_client} » introuvable.")
            continue
        try:
            jour = _date_ou_none(ligne.get("interaction_date"))
            type_interaction = _vocabulaire(
                ligne.get("interaction_type"), "interaction_type", "other")
        except ValueError as erreur:
            anomalie("interactions", numero, None, str(erreur))
            continue
        if not jour:
            anomalie("interactions", numero, "interaction_date",
                     "La date est requise.")
            continue

        # Le même échange déjà versé ne se recrée pas. Sans cette clé naturelle
        # — société, date, type, résumé — un second passage du même fichier
        # doublait les interactions en silence, alors que le module promet le
        # contraire pour tout le reste. Une sonde l'a montré après coup.
        resume = str(ligne.get("summary") or "")
        if client.id is not None:
            deja = session.exec(
                select(Interaction).where(
                    Interaction.client_id == client.id,
                    Interaction.interaction_date == jour,
                    Interaction.interaction_type == type_interaction,
                    Interaction.summary == resume)).first()
            if deja is not None:
                compter(rapport.ignorees, "interactions")
                continue

        compter(rapport.a_creer, "interactions")
        session.add(Interaction(
            entity_id=entity_id, user_id=user_id, client_id=client.id,
            interaction_date=jour, interaction_type=type_interaction,
            summary=resume, notes=ligne.get("notes")))
        session.flush()

    return rapport


def analyser(session: Session, contenu: bytes, *, format_: str,
             entity_id: Optional[int], user_id: int) -> Rapport:
    """Import à blanc.

    Le traitement écrit réellement dans la session — c'est ce qui donne aux
    lignes leurs identifiants et permet aux contrôles qui en dépendent de
    s'exécuter — puis tout est annulé. Rien n'atteint la base.
    """
    donnees, inconnues = (lire_classeur(contenu) if format_ == "xlsx"
                          else lire_json(contenu))
    if not any(donnees.get(f) for f in FEUILLES):
        raise ImportError_(
            "Aucune section exploitable. Le fichier doit porter au moins une "
            f"des sections : {', '.join(FEUILLES)}. Téléchargez le modèle pour "
            f"le format attendu.")
    rapport = _traiter(session, donnees, inconnues, entity_id=entity_id,
                       user_id=user_id)
    # L'aperçu ne doit rien laisser derrière lui, pas même en session.
    session.rollback()
    return rapport


def appliquer(session: Session, contenu: bytes, *, format_: str, filename: str,
              entity_id: Optional[int], user_id: int,
              ignorer_lignes_fautives: bool = False) -> tuple[ClientImportBatch, Rapport]:
    """Verse le fichier. Tout ou rien, sauf demande explicite du contraire.

    Le refus global est le défaut parce qu'un import à moitié passé laisse une
    base dans un état que personne ne connaît. `ignorer_lignes_fautives` existe
    pour le cas réel du fichier de 500 lignes dont trois sont mauvaises — mais
    il se demande, il ne s'applique pas tout seul.
    """
    donnees, inconnues = (lire_classeur(contenu) if format_ == "xlsx"
                          else lire_json(contenu))

    controle = _traiter(session, donnees, inconnues, entity_id=entity_id,
                        user_id=user_id)
    session.rollback()
    if controle.bloquant and not ignorer_lignes_fautives:
        raise ImportError_(
            f"{len(controle.anomalies)} ligne(s) en anomalie : rien n'a été "
            f"importé. Corrigez le fichier, ou demandez explicitement à ignorer "
            f"les lignes fautives.")

    lot = ClientImportBatch(
        entity_id=entity_id, user_id=user_id, filename=filename,
        source_format=format_, status="applied")
    session.add(lot)
    session.flush()

    rapport = _traiter(session, donnees, inconnues, entity_id=entity_id,
                       user_id=user_id, batch_id=lot.id)
    lot.rows_created = sum(rapport.a_creer.values())
    lot.rows_updated = sum(rapport.a_mettre_a_jour.values())
    lot.rows_skipped = sum(rapport.ignorees.values())
    lot.report_json = json.dumps(rapport.as_dict(), ensure_ascii=False)
    session.add(lot)
    return lot, rapport


def annuler(session: Session, lot: ClientImportBatch) -> int:
    """Défait un versement — les transactions d'historique seulement.

    Ce que ce module NE défait pas, délibérément : les clients, personnes et
    affiliations créés. Ils ont pu, entre-temps, recevoir des interactions, des
    opportunités ou des trades saisis à la main, et les supprimer emporterait
    ce travail. Les transactions d'historique, elles, ne portent rien : leur
    retrait est sans effet de bord.

    Le compte rendu du lot reste lisible après annulation, ce qui laisse de quoi
    faire le ménage à la main si nécessaire.
    """
    lignes = session.exec(
        select(ClientTradeHistory).where(
            ClientTradeHistory.import_batch_id == lot.id)).all()
    for ligne in lignes:
        session.delete(ligne)
    lot.status = "reverted"
    lot.reverted_at = datetime.utcnow()
    session.add(lot)
    return len(lignes)


# ── Le modèle à remplir ───────────────────────────────────────────────

def modele_json() -> dict:
    """Le gabarit JSON, exemples compris. Un format qu'on décrit sans le montrer
    se remplit de travers."""
    return {
        "_format": {
            "description": ("Une section par type d'objet. Toutes sont "
                            "facultatives — ne remplissez que ce que vous avez."),
            "ordre": ("Les sections sont traitées dans cet ordre : clients, "
                      "contacts, affiliations, transactions, interactions. Une "
                      "affiliation ne peut désigner qu'un client et une personne "
                      "présents dans le même fichier ou déjà en base."),
            "dates": "AAAA-MM-JJ ou JJ/MM/AAAA.",
            "vocabulaires": VOCABULAIRES,
            "champs_requis": {f: SCHEMA[f]["requis"] for f in FEUILLES},
        },
        **{feuille: EXEMPLES[feuille] for feuille in FEUILLES},
    }


def modele_xlsx() -> bytes:
    """Le classeur à remplir : une feuille par objet, l'en-tête exacte, une
    ligne d'exemple, plus une feuille de mode d'emploi."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    classeur = Workbook()
    classeur.remove(classeur.active)

    mode_emploi = classeur.create_sheet("Mode d'emploi")
    mode_emploi.column_dimensions["A"].width = 26
    mode_emploi.column_dimensions["B"].width = 96
    lignes_aide = [
        ("Principe", "Une feuille par type d'objet. Ne remplissez que ce que vous avez ; "
                     "une feuille vide est ignorée."),
        ("Ordre", "Les feuilles sont traitées dans l'ordre : clients, contacts, "
                  "affiliations, transactions, interactions. Une affiliation ne peut "
                  "désigner qu'un client et une personne déjà présents — dans ce même "
                  "fichier ou déjà en base."),
        ("En-têtes", "L'ordre des colonnes est libre : c'est le nom de l'en-tête qui "
                     "compte. La casse et les accents sont tolérés."),
        ("Dates", "AAAA-MM-JJ ou JJ/MM/AAAA. Une vraie date Excel fonctionne aussi."),
        ("Doublons", "Un client déjà connu par son nom, une personne déjà connue par son "
                     "e-mail ne sont pas recréés : ils sont complétés. Un second import "
                     "du même fichier ne double donc rien."),
        ("Avant d'importer", "L'écran vous montre ce qui serait créé, mis à jour ou "
                             "ignoré, et signale chaque ligne fautive avec son numéro. "
                             "Rien n'est écrit tant que vous n'avez pas validé."),
        ("Transactions", "Elles alimentent l'analyse commerciale (cadence, comportement "
                         "observé). Ce ne sont PAS des positions : elles n'entrent ni "
                         "dans le book, ni dans le risque, ni dans le MtM."),
        ("", ""),
        ("Vocabulaires", "Valeurs acceptées, à recopier telles quelles :"),
    ]
    for champ, valeurs in VOCABULAIRES.items():
        lignes_aide.append((champ, ", ".join(valeurs)))

    gras = Font(bold=True)
    for index, (gauche, droite) in enumerate(lignes_aide, start=1):
        mode_emploi.cell(row=index, column=1, value=gauche).font = gras
        cellule = mode_emploi.cell(row=index, column=2, value=droite)
        cellule.alignment = Alignment(wrap_text=True, vertical="top")

    fond_requis = PatternFill("solid", start_color="FFF3D6")
    fond_entete = PatternFill("solid", start_color="E8EFF5")
    for feuille in FEUILLES:
        onglet = classeur.create_sheet(feuille)
        colonnes = SCHEMA[feuille]["colonnes"]
        requis = set(SCHEMA[feuille]["requis"])
        for index, colonne in enumerate(colonnes, start=1):
            cellule = onglet.cell(row=1, column=index, value=colonne)
            cellule.font = gras
            cellule.fill = fond_requis if colonne in requis else fond_entete
            onglet.column_dimensions[cellule.column_letter].width = max(
                14, min(28, len(colonne) + 6))
        for numero, exemple in enumerate(EXEMPLES[feuille], start=2):
            for index, colonne in enumerate(colonnes, start=1):
                onglet.cell(row=numero, column=index, value=exemple.get(colonne, ""))
        onglet.freeze_panes = "A2"

    tampon = io.BytesIO()
    classeur.save(tampon)
    return tampon.getvalue()
