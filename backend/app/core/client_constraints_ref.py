"""Le référentiel des contraintes client — champs standards et champs ajoutés.

Une contrainte client se saisissait jusqu'ici en texte libre séparé par des
virgules. Trois défauts, tous du même genre : ils ne se signalent pas.

1. **« SX5E » ne rencontre jamais « ^STOXX50E ».** L'univers de sous-jacents se
   compare aux tickers réellement traités ; tapé à la main, il ne correspond à
   rien et l'écran conclut que le client n'a jamais traité son propre univers.
2. **Le vocabulaire fermé des types de produits était rappelé en prose** sous le
   champ, à recopier de mémoire. Une faute de frappe passe la validation du
   navigateur et échoue au serveur, ou pire : ne correspond à rien.
3. **Rien ne pouvait être ajouté.** `validate_constraints` refuse toute clé
   inconnue — protection réelle contre le champ mal orthographié qui se range à
   côté du bon, mais qui interdisait aussi la contrainte que ce client-là est le
   seul à avoir.

Ce module répond aux trois par une même idée : **une contrainte est décrite, pas
devinée**. Une définition porte son type, l'endroit d'où viennent ses valeurs, et
sa portée. Les champs standards et les champs ajoutés ont exactement la même
forme — c'est ce qui permet à l'écran de n'avoir qu'un seul rendu, et au serveur
qu'une seule validation.

**La protection contre la clé inconnue est conservée.** « Connue » veut désormais
dire « standard, ou déclarée pour cette entité, ou déclarée pour ce client » —
jamais « acceptée parce qu'envoyée ».

## Portées

| Portée | Qui la pose | Ce qu'elle exprime |
|---|---|---|
| `standard` | le produit | ce que toute maison déclare |
| `entity` | l'admin | une politique propre à la maison |
| `client` | l'utilisateur | un nom convenu entre lui et ce client-là |

La portée `client` est le point du besoin le moins évident et le plus utile : un
client parle de sa « poche défensive » ou de sa « limite Rouge », vocabulaire
qui n'a de sens qu'entre lui et son commercial. Le ranger dans un champ
« notes » le rendrait illisible par le reste du module ; en faire un champ
standard le proposerait à des clients qui n'en ont que faire.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Sequence

from sqlmodel import Session, select

from ..db.models import (
    ConstraintDefinition, Counterparty, Underlying,
)


class ConstraintRefError(Exception):
    """Refus du référentiel — même contrat que ClientRuleError."""

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message

    def as_dict(self) -> dict:
        return {"code": self.code, "message": self.message}


# ── Types de champ ────────────────────────────────────────────────────
# Le type décide de TROIS choses d'un coup : la forme stockée, la validation
# serveur et le contrôle affiché. Les séparer aurait laissé dériver l'écran et
# le serveur — le défaut classique du champ qui s'affiche en liste déroulante et
# se valide comme du texte libre.

KINDS: dict[str, dict] = {
    "list_enum": {"storage": "list_str", "label": "Liste à choix fermé"},
    "list_text": {"storage": "list_str", "label": "Liste ouverte"},
    "list_ref":  {"storage": "list_ref", "label": "Liste de références"},
    "text":      {"storage": "text",     "label": "Texte libre"},
    "number":    {"storage": "number",   "label": "Nombre"},
    "percent":   {"storage": "number",   "label": "Pourcentage"},
    "months":    {"storage": "number",   "label": "Durée en mois"},
    "money":     {"storage": "number",   "label": "Montant"},
    "rating":    {"storage": "text",     "label": "Notation"},
    "bool":      {"storage": "bool",     "label": "Oui / non"},
}

SCOPES = ("standard", "entity", "client")

# Catalogues vivants : le champ ne porte pas ses valeurs, il pointe sur une
# table. Un émetteur ajouté à l'admin apparaît dans la contrainte sans qu'on
# touche au code.
CATALOGS = ("underlyings", "counterparties", "currencies", "ratings")


@dataclass(frozen=True)
class Definition:
    """Ce qu'est une contrainte : son type, ses valeurs, sa portée."""
    key: str
    label: str
    kind: str
    scope: str = "standard"
    options: tuple = ()
    catalog: Optional[str] = None
    unit: Optional[str] = None
    help_text: Optional[str] = None
    # Une valeur hors catalogue est-elle admise ? Sur les émetteurs, OUI et il
    # le faut : l'historique d'un client nomme « Citi » ce que notre catalogue
    # appelle « Citigroup ». Interdire la saisie libre casserait la
    # superposition déclaré / observé, qui compare des LIBELLÉS.
    free_entry: bool = True
    id: Optional[int] = None
    client_id: Optional[int] = None
    # Un champ archivé n'est plus PROPOSÉ, mais il reste CONNU : la valeur
    # déjà saisie chez un client survit à sa définition, et la validation
    # suivante la refuserait comme clé inconnue — bloquant l'utilisateur sur
    # une fiche à cause d'un archivage fait ailleurs, des semaines plus tôt.
    archived: bool = False

    @property
    def storage(self) -> str:
        return KINDS[self.kind]["storage"]

    def as_dict(self) -> dict:
        return {
            "key": self.key, "label": self.label, "kind": self.kind,
            "scope": self.scope, "options": list(self.options),
            "catalog": self.catalog, "unit": self.unit,
            "help_text": self.help_text, "free_entry": self.free_entry,
            "storage": self.storage, "id": self.id,
            "client_id": self.client_id, "archived": self.archived,
        }


# ── Les champs standards ──────────────────────────────────────────────
# Décrits ici plutôt que dans l'écran : c'est la seule manière que le contrôle
# affiché et la validation serveur ne divergent jamais.

def _standards() -> tuple[Definition, ...]:
    from .client_controls import ASSET_CLASSES, PRODUCT_FAMILIES
    return (
        Definition(
            key="currencies", label="Devises habituellement traitées", kind="list_text",
            catalog="currencies",
            help_text=("Proposées : les devises dont l'application porte un "
                       "calendrier de jours ouvrés. Une autre reste saisissable "
                       "— il s'agit d'une habitude ou d'une préférence, "
                       "jamais d'un blocage permanent."),
        ),
        Definition(
            key="transaction_formats", label="Formats de transaction habituels",
            kind="list_enum", options=("EMTN", "BMTN", "OTC"),
            free_entry=False,
            help_text=("EMTN, BMTN et OTC décrivent le format ou l'enveloppe. "
                       "Swap reste un instrument et se renseigne séparément."),
        ),
        Definition(
            key="instrument_families", label="Familles d'instruments habituelles",
            kind="list_enum",
            options=("Note", "Swap", "Option", "Forward", "Dépôt", "Fonds", "Autre"),
            free_entry=False,
            help_text=("Un Swap peut être traité en OTC. Le format et l'instrument "
                       "ne sont donc jamais fusionnés."),
        ),
        Definition(
            key="product_types", label="Familles de payoffs habituellement traitées",
            kind="list_text", options=tuple(sorted(PRODUCT_FAMILIES)),
            free_entry=True,
            help_text=("Le catalogue propose les familles standards, tout en "
                       "acceptant un payoff ou un nom propre à ce client. "
                       "La comparaison avec l'historique "
                       "porte sur la FAMILLE : « Phoenix Memory » est reconnu "
                       "comme un phoenix."),
        ),
        Definition(
            key="asset_classes", label="Classes d'actifs", kind="list_enum",
            options=tuple(sorted(ASSET_CLASSES)), free_entry=False,
        ),
        Definition(
            key="underlying_universe", label="Univers de sous-jacents",
            kind="list_text", catalog="underlyings",
            help_text=("Choisis dans le catalogue : c'est le seul moyen que "
                       "l'univers déclaré rencontre les tickers réellement "
                       "traités. « SX5E » tapé à la main ne correspond à rien."),
        ),
        Definition(
            key="allowed_issuers", label="Émetteurs habituellement retenus", kind="list_ref",
            catalog="counterparties",
            help_text=("Indication commerciale non bloquante, superposée aux "
                       "Deals observés. Une contrepartie absente reste traitable."),
        ),
        Definition(
            key="excluded_issuers", label="Émetteurs habituellement évités", kind="list_ref",
            catalog="counterparties",
            help_text=("Une habitude d'évitement n'est pas une interdiction. "
                       "Exemple : Marex peut avoir le meilleur prix sans être retenu, "
                       "puis être choisi lors d'une transaction ultérieure."),
        ),
        Definition(
            key="documentation_references",
            label="Documentation juridique référencée",
            kind="list_text",
            options=("Programme EMTN", "Programme BMTN", "ISDA", "CSA", "FBF",
                     "Convention bilatérale locale", "Autre"),
            free_entry=True,
            help_text=("Structura conserve seulement une référence ou une "
                       "appellation ; aucun document contractuel n'est stocké ici."),
        ),
        Definition(
            key="internal_constraints", label="Restrictions opérationnelles déclarées",
            kind="text",
            help_text=("Réserver ce champ aux impossibilités ou restrictions "
                       "réelles. Les habitudes de trading se renseignent dans "
                       "les champs structurés ci-dessus."),
        ),
        Definition(
            key="commercial_notes", label="Notes commerciales", kind="text",
            help_text=("Observation du commercial, distincte d'une déclaration "
                       "du client et des faits issus des Deals."),
        ),
    )


STANDARD_KEYS = tuple(d.key for d in _standards())


# ── Catalogues ────────────────────────────────────────────────────────

def _devises_proposees() -> list[dict]:
    from .calendars import SUPPORTED_CURRENCIES
    return [{"value": code, "label": code, "group": "Calendrier disponible"}
            for code in SUPPORTED_CURRENCIES]


def catalog_options(session: Session, catalog: Optional[str]) -> list[dict]:
    """Les valeurs proposées par un catalogue, à l'instant de la lecture.

    Rend `{value, label, group, id}`. `group` sert à l'écran : proposer
    cinquante tickers à plat est aussi peu utilisable qu'un champ vide, alors
    que « Indices Europe / Actions FR (CAC) / Banques » se parcourt.
    """
    if not catalog:
        return []
    if catalog == "currencies":
        return _devises_proposees()
    if catalog == "ratings":
        from .client_controls import RATING_SCALE
        return [{"value": note, "label": note, "group": "S&P / Fitch"}
                for note in RATING_SCALE]
    if catalog == "underlyings":
        sortie = []
        vus = set()
        for ligne in session.exec(select(Underlying)).all():
            ticker = (ligne.ticker or "").strip()
            # Un ticker peut figurer dans deux groupes du catalogue (BNP.PA est
            # « Actions FR » et « Banques ») : on n'en propose qu'une entrée.
            if not ticker or ticker in vus:
                continue
            vus.add(ticker)
            sortie.append({"value": ticker,
                           "label": f"{ticker} — {ligne.label or ticker}",
                           "group": ligne.group_name or "Sans groupe",
                           "id": ligne.id})
        return sorted(sortie, key=lambda o: (o["group"], o["value"]))
    if catalog == "counterparties":
        return [{"value": c.name, "label": c.name,
                 "group": c.country or "—", "id": c.id}
                for c in session.exec(
                    select(Counterparty).where(Counterparty.active == True)  # noqa: E712
                ).all()]
    raise ConstraintRefError(
        code="CONSTRAINT_CATALOG_UNKNOWN",
        message=f"Catalogue inconnu : {catalog}. Connus : {', '.join(CATALOGS)}.")


# ── Assemblage des définitions applicables ────────────────────────────

def _depuis_table(ligne: ConstraintDefinition) -> Definition:
    import json
    try:
        options = tuple(json.loads(ligne.options_json or "[]"))
    except (TypeError, ValueError):
        options = ()
    return Definition(
        key=ligne.key, label=ligne.label, kind=ligne.kind,
        scope="client" if ligne.client_id else "entity",
        options=options, catalog=ligne.catalog, unit=ligne.unit,
        help_text=ligne.help_text, free_entry=ligne.free_entry,
        id=ligne.id, client_id=ligne.client_id, archived=ligne.archived,
    )


def definitions_for(session: Session, *, entity_id: Optional[int],
                    client_id: Optional[int] = None,
                    include_archived: bool = False) -> list[Definition]:
    """Les définitions applicables : standards, puis entité, puis client.

    L'ordre est celui de la spécificité croissante et il est significatif :
    une définition d'entité qui reprend une clé standard la remplace, une
    définition de client remplace les deux. C'est ce qui permet à une maison de
    renommer « Émetteurs habituellement retenus » dans son vocabulaire sans que le
    champ change d'identité — la clé, elle, ne bouge pas.

    **`include_archived` sépare PROPOSER de CONNAÎTRE**, et cette séparation
    n'est pas théorique : sans elle, archiver un champ rendait irrecevable la
    fiche de tout client qui l'avait rempli. L'écran l'affichait, l'utilisateur
    n'y touchait pas, et l'enregistrement était refusé pour clé inconnue. La
    validation connaît donc tout ; la saisie ne propose que le vivant.
    """
    par_cle: dict[str, Definition] = {d.key: d for d in _standards()}

    requete = select(ConstraintDefinition)
    if not include_archived:
        requete = requete.where(
            ConstraintDefinition.archived == False)  # noqa: E712
    if entity_id is None:
        requete = requete.where(ConstraintDefinition.entity_id.is_(None))
    else:
        requete = requete.where(ConstraintDefinition.entity_id == entity_id)

    lignes = session.exec(requete).all()
    # Entité d'abord, client ensuite : le second écrase le premier.
    for ligne in sorted(lignes, key=lambda l: (l.client_id is not None, l.id or 0)):
        if ligne.client_id is not None and ligne.client_id != client_id:
            continue
        par_cle[ligne.key] = _depuis_table(ligne)
    return list(par_cle.values())


# ── Validation d'une valeur contre sa définition ──────────────────────

def _refus(cle: str, message: str) -> ConstraintRefError:
    return ConstraintRefError(code="CONSTRAINTS_SHAPE_INVALID",
                              message=f"« {cle} » : {message}")


def _valider_liste_de_chaines(definition: Definition, valeur) -> list:
    if not isinstance(valeur, list):
        raise _refus(definition.label, "attend une liste.")
    propre = []
    for element in valeur:
        if not isinstance(element, str) or not element.strip():
            raise _refus(definition.label, "attend une liste de chaînes non vides.")
        propre.append(element.strip())
    if definition.kind == "list_enum" or not definition.free_entry:
        admises = set(definition.options)
        hors = [e for e in propre if e not in admises]
        if hors:
            raise ConstraintRefError(
                code="CONSTRAINTS_VOCABULARY_INVALID",
                message=(f"« {definition.label} » : valeur(s) inconnue(s) "
                         f"{', '.join(hors)}. Acceptées : "
                         f"{', '.join(sorted(admises))}."))
    return propre


def _valider_liste_de_refs(definition: Definition, valeur) -> list:
    """Une référence se stocke `{"id": 12, "label": "Marex"}`.

    L'identifiant sert à résoudre, le libellé à rester lisible si la ligne
    disparaît du catalogue — même motif que `rfq_provenance_json`. Un `id` nul
    est légitime : c'est une valeur saisie librement, et c'est précisément le
    cas d'un émetteur que le client nomme autrement que notre catalogue.
    """
    if not isinstance(valeur, list):
        raise _refus(definition.label, "attend une liste.")
    propre = []
    for element in valeur:
        if isinstance(element, str) and element.strip():
            # Tolérance d'entrée : une chaîne nue est promue en référence sans
            # identifiant. Les blobs écrits avant le référentiel en contiennent.
            propre.append({"id": None, "label": element.strip()})
            continue
        if not isinstance(element, dict) or not str(element.get("label") or "").strip():
            raise _refus(definition.label,
                         'attend des entrées de la forme {"id": 12, "label": "Marex"}.')
        identifiant = element.get("id")
        if identifiant is not None and not isinstance(identifiant, int):
            raise _refus(definition.label,
                         "l'identifiant doit être un entier ou absent.")
        propre.append({"id": identifiant, "label": str(element["label"]).strip()})
    return propre


_BORNES = {"percent": (0.0, 100.0), "months": (0.0, None), "money": (0.0, None)}


def _valider_nombre(definition: Definition, valeur) -> float:
    if isinstance(valeur, bool) or not isinstance(valeur, (int, float)):
        raise _refus(definition.label, "attend un nombre.")
    nombre = float(valeur)
    bas, haut = _BORNES.get(definition.kind, (None, None))
    if bas is not None and nombre < bas:
        raise _refus(definition.label, f"ne peut pas être inférieur à {bas:g}.")
    if haut is not None and nombre > haut:
        raise _refus(definition.label,
                     f"s'exprime en pourcentage ({bas:g} à {haut:g}).")
    if definition.kind == "months" and nombre != int(nombre):
        raise _refus(definition.label, "s'exprime en mois entiers.")
    return int(nombre) if definition.kind == "months" else nombre


def validate_value(definition: Definition, valeur):
    """Valide et normalise UNE valeur contre sa définition."""
    if valeur is None:
        return None
    if definition.storage == "list_str":
        return _valider_liste_de_chaines(definition, valeur)
    if definition.storage == "list_ref":
        return _valider_liste_de_refs(definition, valeur)
    if definition.storage == "number":
        return _valider_nombre(definition, valeur)
    if definition.storage == "bool":
        if not isinstance(valeur, bool):
            raise _refus(definition.label, "attend oui ou non.")
        return valeur
    # text et rating
    if not isinstance(valeur, str):
        raise _refus(definition.label, "attend du texte.")
    texte = valeur.strip()
    if definition.kind == "rating" and texte:
        from .client_controls import RATING_SCALE
        if texte not in RATING_SCALE:
            raise ConstraintRefError(
                code="CONSTRAINTS_VOCABULARY_INVALID",
                message=(f"« {definition.label} » : notation inconnue {texte}. "
                         f"Échelle : {', '.join(RATING_SCALE)}."))
    return texte


def validate_constraints_against(constraints: dict,
                                 definitions: Sequence[Definition]) -> dict:
    """Valide le blob entier contre les définitions applicables.

    Refuse toute clé qu'aucune définition ne décrit. C'est le contrôle d'origine,
    conservé mot pour mot dans son intention : un champ mal orthographié qui se
    range à côté du bon est une contrainte qui ne s'applique jamais, et rien ne
    le signale. Le référentiel élargit ce qui est connu, il ne l'ouvre pas.
    """
    if not isinstance(constraints, dict):
        raise ConstraintRefError(code="CONSTRAINTS_SHAPE_INVALID",
                                 message="Les contraintes doivent être un objet.")
    par_cle = {d.key: d for d in definitions}
    inconnues = set(constraints) - set(par_cle)
    if inconnues:
        raise ConstraintRefError(
            code="CONSTRAINTS_UNKNOWN_KEY",
            message=(f"Contrainte(s) inconnue(s) : {', '.join(sorted(inconnues))}. "
                     f"Clés acceptées : {', '.join(sorted(par_cle))}. "
                     f"Un champ propre à ce client s'ajoute au référentiel."))

    propre: dict = {}
    for cle, valeur in constraints.items():
        normalisee = validate_value(par_cle[cle], valeur)
        # Une liste vide n'est pas une politique vide par accident : on la
        # retire du blob pour que « pas de politique » et « politique vide »
        # restent le même état, celui qui ne produit aucune anomalie.
        if normalisee is None or normalisee == [] or normalisee == "":
            continue
        propre[cle] = normalisee
    return propre


# ── Déclarer un champ ─────────────────────────────────────────────────

_CARACTERES_CLE = set("abcdefghijklmnopqrstuvwxyz0123456789_")


def normalize_key(brut: str) -> str:
    """Un libellé français devient une clé technique stable.

    « Poche défensive max » → `poche_defensive_max`. La clé ne change plus
    jamais ensuite : c'est elle qui est écrite dans le blob de chaque client,
    et la renommer orphelinerait toutes les valeurs déjà saisies.
    """
    import unicodedata
    sans_accents = "".join(
        c for c in unicodedata.normalize("NFD", brut or "")
        if unicodedata.category(c) != "Mn")
    minuscule = sans_accents.strip().casefold()
    propre = "".join(c if c in _CARACTERES_CLE else "_" for c in minuscule)
    propre = "_".join(morceau for morceau in propre.split("_") if morceau)
    if not propre:
        raise ConstraintRefError(
            code="CONSTRAINT_KEY_INVALID",
            message="Le libellé ne produit aucune clé exploitable.")
    return propre[:60]


def require_definable(session: Session, *, entity_id: Optional[int],
                      client_id: Optional[int], key: str,
                      kind: str, catalog: Optional[str],
                      options: Sequence[str],
                      definition_id: Optional[int] = None) -> None:
    """Refuse une déclaration qui produirait un champ inutilisable."""
    if kind not in KINDS:
        raise ConstraintRefError(
            code="CONSTRAINT_KIND_INVALID",
            message=f"Type inconnu : {kind}. Connus : {', '.join(sorted(KINDS))}.")
    if catalog is not None and catalog not in CATALOGS:
        raise ConstraintRefError(
            code="CONSTRAINT_CATALOG_UNKNOWN",
            message=f"Catalogue inconnu : {catalog}. Connus : {', '.join(CATALOGS)}.")
    if kind == "list_enum" and not options:
        raise ConstraintRefError(
            code="CONSTRAINT_OPTIONS_REQUIRED",
            message=("Une liste à choix fermé sans valeur possible n'accepterait "
                     "rien : donnez ses valeurs, ou choisissez une liste ouverte."))
    if key in STANDARD_KEYS:
        raise ConstraintRefError(
            code="CONSTRAINT_KEY_RESERVED",
            message=(f"« {key} » est un champ standard. Renommez-le plutôt que "
                     f"d'en créer un second — deux champs de même sens se "
                     f"remplissent chacun à moitié."))

    requete = select(ConstraintDefinition).where(
        ConstraintDefinition.key == key,
        ConstraintDefinition.archived == False)  # noqa: E712
    if entity_id is None:
        requete = requete.where(ConstraintDefinition.entity_id.is_(None))
    else:
        requete = requete.where(ConstraintDefinition.entity_id == entity_id)
    if client_id is None:
        requete = requete.where(ConstraintDefinition.client_id.is_(None))
    else:
        requete = requete.where(ConstraintDefinition.client_id == client_id)

    for existante in session.exec(requete).all():
        if existante.id != definition_id:
            raise ConstraintRefError(
                code="CONSTRAINT_KEY_TAKEN",
                message=(f"Un champ « {existante.label} » porte déjà cette clé "
                         f"dans cette portée."))


def key_in_use(session: Session, definition: ConstraintDefinition) -> int:
    """Combien de clients ont une valeur pour ce champ.

    Un champ utilisé ne se supprime pas : sa valeur resterait dans le blob de
    chaque client, sans définition pour la décrire, et la prochaine validation
    la refuserait comme clé inconnue. On archive.
    """
    from ..db.models import Client
    import json
    requete = select(Client)
    if definition.client_id is not None:
        requete = requete.where(Client.id == definition.client_id)
    elif definition.entity_id is not None:
        requete = requete.where(Client.entity_id == definition.entity_id)
    compte = 0
    for client in session.exec(requete).all():
        try:
            blob = json.loads(client.constraints_json or "{}")
        except (TypeError, ValueError):
            continue
        if isinstance(blob, dict) and blob.get(definition.key) not in (None, [], ""):
            compte += 1
    return compte
