"""Le référentiel de contraintes — élargir le connu sans ouvrir la porte.

Le contrôle d'origine refusait toute clé inconnue, et c'était juste : un champ
mal orthographié qui se range à côté du bon est une contrainte qui ne s'applique
jamais, et rien ne le signale. Le référentiel doit conserver ce refus **tout en**
permettant d'ajouter un champ.

Deux propriétés portent tout le reste, et les deux ont été trouvées par sonde,
pas par relecture :

1. **Un champ propre à un client ne fuit pas chez un autre.** C'est la raison
   d'être de la portée : « poche défensive » n'a de sens que dans une relation.
2. **Archiver un champ ne bloque pas la fiche de ceux qui l'ont rempli.** La
   valeur survit à sa définition ; si la validation ne la connaît plus,
   l'utilisateur se retrouve incapable d'enregistrer une fiche qu'il n'a pas
   modifiée, à cause d'un archivage fait ailleurs des semaines plus tôt.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from backend.app.api.auth import get_current_user
from backend.app.core.client_constraints_ref import (
    ConstraintRefError, Definition, catalog_options, definitions_for,
    normalize_key, validate_constraints_against, validate_value,
)
from backend.app.db.database import get_session
from backend.app.db.models import (
    ConstraintDefinition, Counterparty, Underlying, User,
)


@pytest.fixture
def app_client(monkeypatch):
    import backend.app.db.database as db

    engine = create_engine("sqlite://", poolclass=StaticPool,
                           connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(db, "engine", engine)

    from backend.app.main import app

    session = Session(engine)
    alice = User(id=1, username="alice", email="a@d.com",
                 password_hash="x", role="user", entity_id=1)
    session.add(alice)
    session.add_all([
        Underlying(ticker="^STOXX50E", label="Euro Stoxx 50",
                   group_name="Indices Europe"),
        # Le même ticker dans deux groupes : le catalogue réel le fait
        # (BNP.PA est « Actions FR » et « Banques »).
        Underlying(ticker="MC.PA", label="LVMH", group_name="Luxe"),
        Underlying(ticker="MC.PA", label="LVMH", group_name="Actions FR (CAC)"),
    ])
    session.add_all([Counterparty(name="Citigroup", country="US"),
                     Counterparty(name="UBS", country="CH"),
                     Counterparty(name="Retirée", country="FR", active=False)])
    session.commit()

    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_current_user] = lambda: alice
    client = TestClient(app)
    client.session = session
    yield client
    app.dependency_overrides.clear()
    session.close()


def _client(app_client, nom="ABC AM") -> int:
    reponse = app_client.post("/api/clients",
                              json={"name": nom, "client_type": "asset_manager"})
    assert reponse.status_code == 201, reponse.text
    return reponse.json()["id"]


def _declarer(app_client, **corps) -> dict:
    reponse = app_client.post("/api/constraint-definitions", json=corps)
    assert reponse.status_code == 201, reponse.text
    return reponse.json()


# ── La clé technique ─────────────────────────────────────────────────

def test_un_libelle_francais_donne_une_cle_stable():
    assert normalize_key("Poche défensive max") == "poche_defensive_max"
    assert normalize_key("  Limite   ROUGE  ") == "limite_rouge"
    assert normalize_key("Émetteurs — hors zone €") == "emetteurs_hors_zone"


def test_un_libelle_sans_lettre_ne_produit_pas_de_cle():
    """Une clé vide se rangerait sous `""` dans le blob, invisible et
    irrécupérable."""
    with pytest.raises(ConstraintRefError) as capture:
        normalize_key("!!! ???")
    assert capture.value.code == "CONSTRAINT_KEY_INVALID"


# ── Les catalogues ───────────────────────────────────────────────────

def test_un_ticker_present_dans_deux_groupes_n_est_propose_qu_une_fois(app_client):
    options = catalog_options(app_client.session, "underlyings")
    valeurs = [o["value"] for o in options]
    assert valeurs.count("MC.PA") == 1
    assert "^STOXX50E" in valeurs


def test_une_contrepartie_inactive_n_est_pas_proposee(app_client):
    """Elle reste lisible dans un blob déjà écrit — le libellé est conservé —
    mais on ne la propose plus à la saisie."""
    libelles = [o["value"] for o in catalog_options(app_client.session,
                                                    "counterparties")]
    assert "Citigroup" in libelles and "Retirée" not in libelles


def test_un_catalogue_inconnu_se_signale(app_client):
    with pytest.raises(ConstraintRefError) as capture:
        catalog_options(app_client.session, "planetes")
    assert capture.value.code == "CONSTRAINT_CATALOG_UNKNOWN"


# ── Validation par le type ───────────────────────────────────────────

def test_un_pourcentage_hors_bornes_est_refuse():
    definition = Definition(key="poche", label="Poche", kind="percent")
    assert validate_value(definition, 30) == 30.0
    with pytest.raises(ConstraintRefError):
        validate_value(definition, 140)
    with pytest.raises(ConstraintRefError):
        validate_value(definition, -1)


def test_un_booleen_n_est_pas_un_nombre():
    """`isinstance(True, int)` vaut True en Python : sans garde explicite, une
    case cochée passerait pour la valeur 1."""
    definition = Definition(key="n", label="Nombre", kind="number")
    with pytest.raises(ConstraintRefError):
        validate_value(definition, True)


def test_une_duree_s_exprime_en_mois_entiers():
    definition = Definition(key="d", label="Durée", kind="months")
    assert validate_value(definition, 36) == 36
    with pytest.raises(ConstraintRefError):
        validate_value(definition, 36.5)


def test_un_vocabulaire_ferme_refuse_ce_qui_n_y_est_pas():
    definition = Definition(key="s", label="Segment", kind="list_enum",
                            options=("A", "B"), free_entry=False)
    assert validate_value(definition, ["A"]) == ["A"]
    with pytest.raises(ConstraintRefError) as capture:
        validate_value(definition, ["C"])
    assert capture.value.code == "CONSTRAINTS_VOCABULARY_INVALID"


def test_une_reference_saisie_librement_est_admise():
    """Sans identifiant, exprès : l'historique d'un client nomme « Citi » ce que
    notre catalogue appelle « Citigroup », et la superposition déclaré/observé
    compare des LIBELLÉS. Interdire la saisie libre casserait la lecture pour
    laquelle le champ existe."""
    definition = Definition(key="e", label="Émetteurs", kind="list_ref")
    propre = validate_value(definition, [{"id": 3, "label": "UBS"}, "Citi"])
    assert propre == [{"id": 3, "label": "UBS"}, {"id": None, "label": "Citi"}]


def test_une_cle_qu_aucune_definition_ne_decrit_reste_refusee():
    with pytest.raises(ConstraintRefError) as capture:
        validate_constraints_against({"pocheDefensive": 30},
                                     [Definition(key="poche", label="P",
                                                 kind="percent")])
    assert capture.value.code == "CONSTRAINTS_UNKNOWN_KEY"


def test_une_liste_vide_ne_se_stocke_pas():
    """« Pas de politique » et « politique vide » doivent rester le même état :
    celui qui ne produit aucune anomalie. Les distinguer ferait apparaître une
    politique là où l'utilisateur n'en a déclaré aucune."""
    definition = Definition(key="c", label="Devises", kind="list_text")
    assert validate_constraints_against({"c": []}, [definition]) == {}


# ── Les portées ──────────────────────────────────────────────────────

def test_un_champ_declare_pour_un_client_ne_fuit_pas_chez_un_autre(app_client):
    abc, xyz = _client(app_client, "ABC AM"), _client(app_client, "XYZ SA")
    champ = _declarer(app_client, label="Poche défensive max", kind="percent",
                      client_id=abc)

    chez_lui = app_client.put(f"/api/clients/{abc}/constraints",
                              json={"constraints": {champ["key"]: 30},
                                    "constraints_version": 1})
    assert chez_lui.status_code == 200
    assert chez_lui.json()["constraints"][champ["key"]] == 30.0

    ailleurs = app_client.put(f"/api/clients/{xyz}/constraints",
                              json={"constraints": {champ["key"]: 30},
                                    "constraints_version": 1})
    assert ailleurs.status_code == 422
    assert "inconnue" in ailleurs.json()["detail"]


def test_un_champ_de_maison_vaut_pour_tous_les_clients(app_client):
    abc, xyz = _client(app_client, "ABC AM"), _client(app_client, "XYZ SA")
    champ = _declarer(app_client, label="Comité produit requis", kind="bool")
    assert champ["scope"] == "entity"
    for identifiant in (abc, xyz):
        reponse = app_client.put(f"/api/clients/{identifiant}/constraints",
                                 json={"constraints": {champ["key"]: True},
                                       "constraints_version": 1})
        assert reponse.status_code == 200, reponse.text


def test_une_cle_standard_ne_se_redeclare_pas(app_client):
    """Deux champs de même sens se remplissent chacun à moitié."""
    reponse = app_client.post("/api/constraint-definitions",
                              json={"label": "currencies", "kind": "text"})
    assert reponse.status_code == 422
    assert reponse.json()["detail"]["code"] == "CONSTRAINT_KEY_RESERVED"


def test_une_liste_fermee_sans_valeurs_est_refusee(app_client):
    reponse = app_client.post("/api/constraint-definitions",
                              json={"label": "Segment", "kind": "list_enum"})
    assert reponse.status_code == 422
    assert reponse.json()["detail"]["code"] == "CONSTRAINT_OPTIONS_REQUIRED"


def test_deux_champs_de_meme_cle_dans_la_meme_portee_se_refusent(app_client):
    _declarer(app_client, label="Limite rouge", kind="percent")
    reponse = app_client.post("/api/constraint-definitions",
                              json={"label": "Limite rouge", "kind": "percent"})
    assert reponse.status_code == 422
    assert reponse.json()["detail"]["code"] == "CONSTRAINT_KEY_TAKEN"


# ── L'archivage, et le piège qu'il tendait ───────────────────────────

def test_archiver_un_champ_ne_bloque_pas_la_fiche_de_ceux_qui_l_ont_rempli(app_client):
    """LE défaut que la sonde a trouvé et que la relecture avait laissé passer.

    La valeur reste dans le blob après l'archivage. Si la validation ne connaît
    plus la clé, réenregistrer la fiche TELLE QU'ELLE S'AFFICHE est refusé —
    l'utilisateur est bloqué par une décision prise ailleurs, sans rapport avec
    ce qu'il fait.
    """
    abc = _client(app_client)
    champ = _declarer(app_client, label="Poche défensive max", kind="percent",
                      client_id=abc)
    app_client.put(f"/api/clients/{abc}/constraints",
                   json={"constraints": {champ["key"]: 30},
                         "constraints_version": 1})

    retrait = app_client.delete(f"/api/constraint-definitions/{champ['id']}?force=true")
    assert retrait.json() == {"deleted": False, "archived": True, "usages": 1}

    schema = app_client.get(f"/api/clients/{abc}/constraints/schema").json()
    rejeu = app_client.put(
        f"/api/clients/{abc}/constraints",
        json={"constraints": schema["values"],
              "constraints_version": schema["constraints_version"]})
    assert rejeu.status_code == 200, rejeu.text


def test_un_champ_archive_reste_visible_tant_qu_il_porte_une_valeur(app_client):
    """Sinon la valeur vit dans le blob sans que personne puisse la lire ni
    l'effacer : elle ne s'applique plus, ne se voit plus, et revient au premier
    export."""
    abc = _client(app_client)
    champ = _declarer(app_client, label="Poche défensive max", kind="percent",
                      client_id=abc)
    app_client.put(f"/api/clients/{abc}/constraints",
                   json={"constraints": {champ["key"]: 30},
                         "constraints_version": 1})
    app_client.delete(f"/api/constraint-definitions/{champ['id']}")

    schema = app_client.get(f"/api/clients/{abc}/constraints/schema").json()
    assert [d["key"] for d in schema["retired"]] == [champ["key"]]
    assert champ["key"] not in [d["key"] for d in schema["definitions"]]

    # Effacée, la ligne disparaît des deux côtés.
    app_client.put(f"/api/clients/{abc}/constraints",
                   json={"constraints": {},
                         "constraints_version": schema["constraints_version"]})
    schema = app_client.get(f"/api/clients/{abc}/constraints/schema").json()
    assert schema["retired"] == [] and schema["values"] == {}


def test_un_champ_jamais_rempli_se_supprime_pour_de_bon(app_client):
    abc = _client(app_client)
    champ = _declarer(app_client, label="Jamais servi", kind="text",
                      client_id=abc)
    reponse = app_client.delete(
        f"/api/constraint-definitions/{champ['id']}?force=true")
    assert reponse.json() == {"deleted": True, "archived": False, "usages": 0}
    assert app_client.session.get(ConstraintDefinition, champ["id"]) is None


def test_restaurer_un_champ_le_remet_en_saisie(app_client):
    abc = _client(app_client)
    champ = _declarer(app_client, label="Limite rouge", kind="percent",
                      client_id=abc)
    app_client.delete(f"/api/constraint-definitions/{champ['id']}")
    app_client.post(f"/api/constraint-definitions/{champ['id']}/restore")

    schema = app_client.get(f"/api/clients/{abc}/constraints/schema").json()
    assert champ["key"] in [d["key"] for d in schema["definitions"]]


# ── Le schéma que l'écran consomme ───────────────────────────────────

def test_le_schema_decrit_les_champs_et_resout_les_catalogues(app_client):
    """L'écran ne connaît aucun champ à l'avance : il rend ce que le serveur
    décrit. C'est ce qui empêche le champ d'être décrit différemment des deux
    côtés — la liste déroulante à l'écran et le texte libre au serveur."""
    abc = _client(app_client)
    schema = app_client.get(f"/api/clients/{abc}/constraints/schema").json()

    par_cle = {d["key"]: d for d in schema["definitions"]}
    assert par_cle["underlying_universe"]["catalog"] == "underlyings"
    assert par_cle["product_types"]["free_entry"] is True
    assert "autocall" in par_cle["product_types"]["options"]
    assert par_cle["transaction_formats"]["options"] == ["EMTN", "BMTN", "OTC"]
    assert "Swap" in par_cle["instrument_families"]["options"]
    assert par_cle["documentation_references"]["storage"] == "list_str"
    assert par_cle["allowed_issuers"]["storage"] == "list_ref"

    assert "^STOXX50E" in [o["value"] for o in schema["catalogs"]["underlyings"]]
    assert schema["catalogs"]["underlyings"][0]["group"]


def test_un_payoff_propre_au_client_reutilise_le_champ_existant(app_client):
    """Le catalogue aide la saisie sans enfermer le client dans les standards."""
    abc = _client(app_client)
    reponse = app_client.put(
        f"/api/clients/{abc}/constraints",
        json={"constraints": {
            "product_types": ["phoenix", "Autocall Défensif ABC"],
            "transaction_formats": ["EMTN", "OTC"],
            "instrument_families": ["Note", "Swap"],
            "documentation_references": ["ISDA", "Réf. juridique ABC-2026"],
        }, "constraints_version": 1},
    )
    assert reponse.status_code == 200, reponse.text
    valeurs = reponse.json()["constraints"]
    assert "Autocall Défensif ABC" in valeurs["product_types"]
    assert valeurs["transaction_formats"] == ["EMTN", "OTC"]


def test_le_champ_ajoute_apparait_dans_le_schema_sans_toucher_a_l_ecran(app_client):
    abc = _client(app_client)
    avant = app_client.get(f"/api/clients/{abc}/constraints/schema").json()
    champ = _declarer(app_client, label="Poche défensive max", kind="percent",
                      unit="%", client_id=abc)
    apres = app_client.get(f"/api/clients/{abc}/constraints/schema").json()

    nouvelles = ({d["key"] for d in apres["definitions"]}
                 - {d["key"] for d in avant["definitions"]})
    assert nouvelles == {champ["key"]}
    ajoutee = [d for d in apres["definitions"] if d["key"] == champ["key"]][0]
    assert ajoutee["scope"] == "client" and ajoutee["unit"] == "%"


def test_une_definition_de_client_prime_sur_celle_de_la_maison(app_client):
    """La spécificité croissante n'est pas décorative : elle permet de renommer
    un champ pour un client sans que le champ change d'identité — la clé, elle,
    ne bouge pas, donc les valeurs déjà saisies suivent."""
    abc = _client(app_client)
    session = app_client.session
    session.add(ConstraintDefinition(entity_id=1, key="limite_rouge",
                                     label="Limite rouge", kind="percent"))
    session.add(ConstraintDefinition(entity_id=1, client_id=abc,
                                     key="limite_rouge",
                                     label="Seuil Rouge (leur mot)",
                                     kind="percent"))
    session.commit()

    definitions = {d.key: d for d in definitions_for(session, entity_id=1,
                                                     client_id=abc)}
    assert definitions["limite_rouge"].label == "Seuil Rouge (leur mot)"
    assert definitions["limite_rouge"].scope == "client"

    # Chez un autre client, c'est la définition de la maison qui s'applique.
    autres = {d.key: d for d in definitions_for(session, entity_id=1,
                                                client_id=_client(app_client, "XYZ"))}
    assert autres["limite_rouge"].label == "Limite rouge"


def test_le_cloisonnement_d_entite_vaut_aussi_pour_les_definitions(app_client):
    session = app_client.session
    session.add(ConstraintDefinition(entity_id=99, key="secret_voisin",
                                     label="Champ du voisin", kind="text"))
    session.commit()
    cles = {d.key for d in definitions_for(session, entity_id=1)}
    assert "secret_voisin" not in cles
