"""Le jeu de démonstration produit-il bien les comportements qu'il annonce ?

Un jeu de données dont on affirme qu'il « couvre les cas » ne couvre rien tant
que personne ne l'a vérifié. Ces tests sèment le jeu sur une base en mémoire et
contrôlent, société par société, que le module réagit comme le tableau du
docstring le promet.

Ils ont un second usage, moins évident : ils sont le seul endroit où le module
est exercé sur un volume réaliste et sur des données qui se croisent. La plupart
des défauts trouvés dans ce module l'ont été en confrontant deux chemins ; ce
fichier confronte tout le module à un portefeuille entier.
"""
from datetime import date

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from backend.app.core.client_cycle import compute_cycle
from backend.app.core.client_intelligence import (
    _dates_de_trade, client_intelligence, deals_of_client, person_intelligence,
)
from backend.app.core.client_signals import (
    CONTACT_SOON, DORMANT, FOLLOW_UP_DUE, UPCOMING_MATURITY, build_signals,
)
from backend.app.db.models import (
    Affiliation, Client, ClientTradeHistory, Deal, Person, Underlying, User,
)
from backend.scripts.seed_client_demo import (
    POLITIQUE_COMPLETE, SOCIETES, purger, semer,
)


# Ces tests SUPPRIMENT — c'est le seul endroit où l'ordre compte, donc le seul
# où l'absence de contrainte laisse passer un vrai défaut. D'où l'usage de la
# fabrique de `conftest.py` plutôt que d'un `create_engine` nu. Voir ce
# fichier-là pour la raison du choix « à la demande » plutôt que global.
from backend.tests.conftest import _moteur_sqlite


def _moteur():
    return _moteur_sqlite(integrite=True)


# Le catalogue de sous-jacents, réduit à ce que le jeu de démonstration
# emploie. Sans lui, aucune famille n'est déterminable et l'onglet technique
# ne montrerait que « nature inconnue » — comportement correct du module, mais
# qui ferait passer le jeu d'essai pour défectueux.
CATALOGUE = [
    ("^STOXX50E", "Indices Europe"), ("^GSPC", "Indices US"),
    ("^SSMI", "Indices Europe"), ("GLD", "ETF / Matières premières"),
    ("MC.PA", "Luxe"), ("OR.PA", "Luxe"), ("KER.PA", "Luxe"),
    ("BNP.PA", "Banques"), ("GLE.PA", "Banques"), ("UBSG.SW", "Banques"),
    ("STMPA.PA", "Actions FR (CAC)"), ("UCG.MI", "Actions IT (FTSE MIB)"),
    ("TTE.PA", "Actions FR (CAC)"),
]


@pytest.fixture(scope="module")
def base():
    engine = _moteur()
    session = Session(engine)
    session.add(User(id=1, username="alice", email="a@d.com",
                     password_hash="x", role="user", entity_id=None))
    for ticker, groupe in CATALOGUE:
        session.add(Underlying(ticker=ticker, label=ticker, group_name=groupe))
    session.commit()
    semer(session, entity_id=None, user_id=1)
    yield session
    session.close()


def _client(session, nom) -> Client:
    fiche = session.exec(select(Client).where(Client.name == nom)).first()
    assert fiche is not None, f"« {nom} » absent du jeu"
    return fiche


AUJOURDHUI = date.today()


# ── Le jeu existe et se tient ────────────────────────────────────────

def test_les_neuf_societes_sont_semees(base):
    noms = {c.name for c in base.exec(select(Client)).all()}
    assert set(SOCIETES) <= noms


def test_toutes_les_transactions_sont_rattachees(base):
    """Une ligne d'historique sans client ne serait lue par personne — et une
    sans affiliation fausserait les lectures par personne."""
    for ligne in base.exec(select(ClientTradeHistory)).all():
        assert ligne.client_id is not None
        assert ligne.affiliation_id is not None


def test_chaque_affiliation_pointe_sur_le_bon_client(base):
    """Le garde-fou du modèle, vérifié sur le jeu entier : une transaction ne
    peut pas porter l'affiliation d'une autre société."""
    for ligne in base.exec(select(ClientTradeHistory)).all():
        affiliation = base.get(Affiliation, ligne.affiliation_id)
        assert affiliation.client_id == ligne.client_id


# ── Rhône AM : le cas riche ──────────────────────────────────────────

def test_rhone_a_une_cadence_de_confiance_haute(base):
    fiche = client_intelligence(base, _client(base, "Rhône Asset Management").id,
                                asof=AUJOURDHUI)
    cycle = fiche["cycle"]
    assert cycle["confidence"] == "high"
    assert cycle["cadence"] == "trimestrielle"
    # 17 journées portant 23 lignes : la distinction que la revue a créée.
    assert cycle["n_trading_days"] == 17
    assert cycle["n_trades"] > cycle["n_trading_days"]


def test_rhone_ouvre_sa_fenetre_de_contact_aujourdhui(base):
    """La bande d'action bleue de la maquette. Les dates du jeu sont calées
    pour que ce soit vrai le jour où on le sème, quel qu'il soit."""
    fiche = client_intelligence(base, _client(base, "Rhône Asset Management").id,
                                asof=AUJOURDHUI)
    fenetre = fiche["contact_window"]
    assert fenetre["start"] is not None
    assert fenetre["start"] <= AUJOURDHUI.isoformat() <= fenetre["end"], (
        f"fenêtre {fenetre['start']} → {fenetre['end']}, "
        f"aujourd'hui {AUJOURDHUI.isoformat()}")


def test_rhone_porte_les_deux_anomalies_d_emetteur(base):
    """Deux natures distinctes : traité bien qu'exclu, et absent de la liste."""
    fiche = client_intelligence(base, _client(base, "Rhône Asset Management").id,
                                asof=AUJOURDHUI)
    a_verifier = {e["label"]: e["reason"]
                  for e in fiche["negative_space"]["issuers"]["to_check"]}
    assert a_verifier == {"Marex": "excluded", "Natixis": "off_list"}, (
        "exactement deux anomalies, pas une de plus : une démonstration qui "
        "signale plus qu'elle n'annonce décrédibilise ses vrais signaux")
    # Et une ouverture réelle : autorisés, jamais sollicités.
    jamais = {e["label"] for e in fiche["negative_space"]["issuers"]["never_used"]}
    assert {"Vontobel", "Citi"} <= jamais


def test_rhone_distingue_le_booke_de_l_importe(base):
    fiche = client_intelligence(base, _client(base, "Rhône Asset Management").id,
                                asof=AUJOURDHUI)
    assert fiche["behaviour"]["n_imported"] > 0
    assert fiche["behaviour"]["n_trades"] > fiche["behaviour"]["n_imported"]


def test_rhone_a_un_taux_de_conversion_et_des_motifs_de_perte(base):
    fiche = client_intelligence(base, _client(base, "Rhône Asset Management").id,
                                asof=AUJOURDHUI)
    assert fiche["conversion"]["decided"] == 4
    assert fiche["conversion"]["rate"] == pytest.approx(0.5)
    motifs = dict(fiche["lost_reasons"])
    assert motifs.get("coupon_too_low") == 1
    assert motifs.get("issuer_rejected") == 1


def test_rhone_expose_son_appel_d_offres(base):
    """L'onglet « Appels d'offres », remonté par RFQ → Opportunité → Client."""
    fiche = client_intelligence(base, _client(base, "Rhône Asset Management").id,
                                asof=AUJOURDHUI)
    assert len(fiche["rfqs"]) == 1
    assert fiche["rfqs"][0]["status"] == "quote"


# ── Jura : l'historique pauvre ───────────────────────────────────────

def test_jura_ne_nomme_aucune_cadence(base):
    """Deux transactions : un intervalle, donc une confiance basse et une
    fenêtre élargie par défaut. L'écran doit refuser de trancher."""
    fiche = client_intelligence(base, _client(base, "Jura Assurances").id,
                                asof=AUJOURDHUI)
    cycle = fiche["cycle"]
    assert cycle["n_trades"] == 2
    assert cycle["n_intervals"] == 1
    assert cycle["confidence"] == "low"
    assert "élargie par défaut" in " ".join(cycle["explanation"])


def test_jura_rend_des_points_et_non_une_bande(base):
    """Une moitié centrale sur deux observations inventerait une distribution."""
    fiche = client_intelligence(base, _client(base, "Jura Assurances").id,
                                asof=AUJOURDHUI)
    ticket = fiche["ranges"]["ticket"]
    assert ticket["band"] is None
    assert ticket["points"] == [1_800_000.0, 2_000_000.0]
    assert ticket["declared_max"] == 10_000_000


def test_jura_a_des_seuils_encore_a_atteindre(base):
    fiche = client_intelligence(base, _client(base, "Jura Assurances").id,
                                asof=AUJOURDHUI)
    restants = [s for s in fiche["thresholds"] if not s["reached"]]
    assert restants, "un client à 2 transactions doit avoir des seuils devant lui"
    dispersion = next(s for s in fiche["thresholds"] if s["what"] == "dispersion")
    assert dispersion["reached"] is False
    assert dispersion["at"] == 1


def test_jura_leve_une_relance_echue_et_aucune_fenetre(base):
    """Sur un client sans cadence établie, la seule action possible est celle
    qui a été notée à la main.

    Le second point est celui qu'un semis sur base réelle a révélé : le moteur
    produit BIEN une fenêtre pour Jura — large de plus de deux mois, sur un
    seul intervalle — mais elle ne doit pas devenir un signal urgent. La fiche
    client refusait déjà d'en faire l'action du jour ; les signaux, eux,
    criaient. Deux parties du même module qui se contredisent apprennent à
    ignorer les deux.
    """
    signaux = build_signals(base, entity_id=None, user_id=1, asof=AUJOURDHUI)
    jura = _client(base, "Jura Assurances")

    relances = [s for s in signaux
                if s.kind == FOLLOW_UP_DUE and s.client_id == jura.id]
    assert len(relances) == 1
    assert "indicatif" in relances[0].title

    contacts = [s for s in signaux
                if s.kind == CONTACT_SOON and s.client_id == jura.id]
    assert contacts == [], (
        "une fenêtre large de deux mois sur un seul intervalle n'est pas une "
        "échéance : elle ne doit pas remonter comme signal urgent")


# ── Fondation Lémanique : rien du tout ───────────────────────────────

def test_la_fondation_est_muette_mais_sa_fiche_est_entiere(base):
    fiche = client_intelligence(base, _client(base, "Fondation Lémanique").id,
                                asof=AUJOURDHUI)
    assert fiche["cycle"]["confidence"] == "insufficient_history"
    assert fiche["cycle"]["expected_window_start"] is None
    assert fiche["contact_window"]["start"] is None
    assert fiche["transactions"] == []
    assert fiche["conversion"]["rate"] is None
    # Mais la politique, elle, porte toute la valeur de l'écran : chaque
    # émetteur autorisé est une ouverture, puisqu'aucun n'a été sollicité.
    # Dérivé de la politique du jeu plutôt que codé en dur — le nombre suivra
    # si la liste change.
    autorises = {i["label"] for i in POLITIQUE_COMPLETE["allowed_issuers"]}
    jamais = {e["label"] for e in fiche["negative_space"]["issuers"]["never_used"]}
    assert jamais == autorises
    assert fiche["ranges"]["ticket"]["declared_max"] == 5_000_000


# ── Alpes : la dormance relative ─────────────────────────────────────

def test_alpes_est_dormant_par_rapport_a_sa_propre_cadence(base):
    fiche = client_intelligence(base, _client(base, "Alpes Institutionnel").id,
                                asof=AUJOURDHUI)
    cycle = fiche["cycle"]
    assert cycle["overdue"] is True
    assert round(cycle["median_interval_days"]) == 62
    assert cycle["days_since_last"] == 210

    signaux = build_signals(base, entity_id=None, user_id=None, asof=AUJOURDHUI)
    dormants = {s.client_name for s in signaux if s.kind == DORMANT}
    assert "Alpes Institutionnel" in dormants
    # Rhône traite tous les 88 jours et se tait depuis 74 : pas dormant.
    assert "Rhône Asset Management" not in dormants


# ── Genève : le volume ne fait pas la confiance ──────────────────────

def test_geneve_reste_en_confiance_basse_malgre_dix_transactions(base):
    fiche = client_intelligence(base, _client(base, "Genève Privée").id,
                                asof=AUJOURDHUI)
    cycle = fiche["cycle"]
    assert cycle["n_trades"] == 10
    assert cycle["confidence"] == "low"
    assert cycle["cadence"] == "irreguliere"


# ── Valais : sans politique, aucune anomalie ─────────────────────────

def test_valais_ne_produit_aucune_anomalie_faute_de_politique(base):
    """Le faux positif que le module refuse : signaler un écart à quelqu'un qui
    n'a rien déclaré."""
    fiche = client_intelligence(base, _client(base, "Valais Distribution").id,
                                asof=AUJOURDHUI)
    emetteurs = fiche["negative_space"]["issuers"]
    assert emetteurs["has_policy"] is False
    assert emetteurs["to_check"] == []
    assert emetteurs["never_used"] == []
    # Marex y est pourtant traité — il ne serait signalé que face à une
    # politique qui l'exclut.
    assert any(e["label"] == "Marex" for e in emetteurs["used"])


def test_valais_n_a_pas_de_rail_faute_de_fourchette(base):
    fiche = client_intelligence(base, _client(base, "Valais Distribution").id,
                                asof=AUJOURDHUI)
    assert fiche["ranges"]["ticket"]["declared_min"] is None
    assert fiche["ranges"]["ticket"]["n"] == 6


# ── Léman : l'agrégat mentirait ──────────────────────────────────────

def test_leman_montre_deux_profils_que_la_moyenne_effacerait(base):
    fiche = client_intelligence(base, _client(base, "Léman Family Office").id,
                                asof=AUJOURDHUI)
    profils = {c["name"]: c for c in fiche["per_contact"]}
    assert len(profils) == 2

    prudent = profils["Henri Favre"]
    agressif = profils["Nadia Silva"]
    assert prudent["behaviour"]["product_types"][0][0] == "Capital garanti"
    assert agressif["behaviour"]["product_types"][0][0] == "Phoenix Memory"
    # Cadences franchement différentes : 180 jours contre 30.
    assert prudent["cycle"]["median_interval_days"] > 150
    assert agressif["cycle"]["median_interval_days"] < 40
    # Et des tickets d'un ordre de grandeur d'écart.
    assert prudent["behaviour"]["median_ticket"] > 10 * agressif["behaviour"]["median_ticket"]


# ── Le changement de société ─────────────────────────────────────────

def test_l_historique_d_anne_reste_chez_son_ancien_employeur(base):
    """Le §76 vérifié sur le jeu : cinq transactions chez Helvetia, quatre chez
    Zurich, et rien n'a migré."""
    helvetia = _client(base, "Bank Helvetia")
    zurich = _client(base, "Zurich Partners")
    anne = base.exec(select(Person).where(Person.last_name == "Keller")).first()

    fiche = person_intelligence(base, anne.id, asof=AUJOURDHUI)
    cycles = fiche["cycles"]
    # Personnel : les deux périodes réunies.
    assert cycles["personal"]["n_trades"] == 9
    # Chez son employeur actuel seulement.
    assert cycles["current_affiliation"]["n_trades"] == 4
    # La maison SANS elle — sinon on la comparerait en partie à elle-même.
    assert cycles["organization"]["n_trades"] == 8

    assert len(deals_of_client(base, helvetia.id)) == 5
    assert len(deals_of_client(base, zurich.id)) == 12


def test_la_comparaison_d_anne_est_lisible_et_descriptive(base):
    anne = base.exec(select(Person).where(Person.last_name == "Keller")).first()
    comparaison = person_intelligence(base, anne.id,
                                      asof=AUJOURDHUI)["comparison"]
    assert comparaison["comparable"] is True
    assert comparaison["closer_to"] in ("personal", "organization", "tie")
    assert "observation, pas explication" in " ".join(comparaison["explanation"])


# ── Signaux : le jeu doit en produire de plusieurs natures ───────────

def test_le_jeu_produit_des_signaux_de_plusieurs_natures(base):
    """Un jeu qui ne lèverait qu'un type de signal ne permettrait pas de voir
    l'écran Cycles & Signaux faire son travail."""
    signaux = build_signals(base, entity_id=None, user_id=None, asof=AUJOURDHUI)
    natures = {s.kind for s in signaux}
    assert FOLLOW_UP_DUE in natures
    assert DORMANT in natures
    assert UPCOMING_MATURITY in natures
    assert len(natures) >= 3, f"seulement {natures}"


# ── Le fichier d'import de démonstration ─────────────────────────────

def test_le_fichier_d_import_demontre_bien_ses_anomalies():
    """Il annonce contenir des lignes fautives « pour voir le rapport
    travailler ». Encore faut-il qu'elles soient réellement refusées — sinon
    l'écran d'import paraîtrait laxiste alors que c'est le fichier qui serait
    propre."""
    import json
    from backend.app.core.client_import import analyser
    from backend.scripts.seed_client_demo import fichier_import

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    session = Session(engine)

    rapport = analyser(
        session, json.dumps(fichier_import()).encode(), format_="json",
        entity_id=None, user_id=1)

    assert rapport.bloquant is True
    par_feuille = {}
    for anomalie in rapport.anomalies:
        par_feuille.setdefault(anomalie.feuille, []).append(anomalie.message)

    # Un nom vide et un type de client inconnu.
    assert len(par_feuille["clients"]) == 2
    # Une personne absente du fichier comme de la base.
    assert any("introuvable" in m for m in par_feuille["affiliations"])
    # Une transaction hors de toute période d'emploi, et une société absente.
    assert len(par_feuille["transactions"]) == 2
    assert any("ne couvre le" in m for m in par_feuille["transactions"])
    # Une date illisible.
    assert any("demain" in m for m in par_feuille["interactions"])

    # Et les lignes saines, elles, seraient bien créées.
    assert rapport.a_creer.get("clients") == 2
    assert rapport.a_creer.get("transactions") == 3
    session.close()


def test_le_fichier_d_import_accepte_les_dates_francaises():
    """Un export d'un autre outil ne sortira pas forcément en ISO — le jeu
    mélange les deux formats exprès."""
    import json
    from backend.scripts.seed_client_demo import fichier_import
    charge = json.dumps(fichier_import())
    assert "15/09/2023" in charge and "2023-02-14" in charge


# ── L'entité : le piège qui rend un semis invisible ──────────────────

def test_le_semis_prend_l_entite_du_compte_et_non_none():
    """Tout le module filtre par `entity_id`. Semer sur une autre entité que
    celle du compte produit des données parfaitement écrites et parfaitement
    INVISIBLES — neuf sociétés en base, un écran vide, et rien à l'écran pour
    comprendre pourquoi.

    C'est arrivé au premier semis sur la base réelle : le script valait `None`
    par défaut, les comptes étaient sur l'entité 1.
    """
    from backend.scripts.seed_client_demo import entite_du_compte

    from backend.app.db.models import Entity

    engine = _moteur()
    session = Session(engine)
    # L'entité doit exister : avec les clés étrangères appliquées, un
    # `entity_id` pointant dans le vide est refusé — comme en production.
    session.add(Entity(id=7, name="Genève"))
    session.commit()
    session.add(User(id=1, username="admin", email="a@d.com",
                     password_hash="x", role="admin", entity_id=7))
    session.commit()

    entity_id, nom = entite_du_compte(session, 1)
    assert entity_id == 7, "l'entité doit venir du compte, pas d'un défaut"
    assert nom == "admin"

    semer(session, entity_id=entity_id, user_id=1)
    clients = session.exec(select(Client)).all()
    assert clients, "le semis n'a rien produit"
    assert {c.entity_id for c in clients} == {7}, (
        "toutes les sociétés doivent porter l'entité du compte, sinon l'écran "
        "les filtre et n'affiche rien")

    # Et tout ce qui pend en dépend aussi : une transaction sur une autre
    # entité serait invisible des analytiques.
    assert {t.entity_id for t in session.exec(select(ClientTradeHistory)).all()} == {7}
    session.close()


def test_un_compte_inexistant_arrete_le_semis():
    """Plutôt que de semer sur `None` et de laisser découvrir le vide."""
    engine = _moteur()
    session = Session(engine)
    from backend.scripts.seed_client_demo import entite_du_compte
    with pytest.raises(SystemExit) as capture:
        entite_du_compte(session, 999)
    assert "introuvable" in str(capture.value)
    session.close()


# ── Le retrait ───────────────────────────────────────────────────────

def test_le_jeu_se_retire_entierement():
    """Un jeu de démonstration qu'on ne peut pas défaire pollue une base réelle
    définitivement.

    Sur un moteur qui applique les clés étrangères, comme la production : la
    première version de ce test passait sans elles et masquait un ordre de
    suppression faux.
    """
    engine = _moteur()
    session = Session(engine)
    session.add(User(id=1, username="a", email="a@d.com", password_hash="x",
                     entity_id=None))
    session.commit()

    # Une société réelle, qui ne doit surtout pas être emportée.
    session.add(Client(name="Client réel à ne pas toucher", entity_id=None))
    session.commit()

    semer(session, entity_id=None, user_id=1)
    assert len(session.exec(select(Client)).all()) == len(SOCIETES) + 1

    compte = purger(session)
    assert compte["clients"] == len(SOCIETES)
    restants = session.exec(select(Client)).all()
    assert [c.name for c in restants] == ["Client réel à ne pas toucher"]
    # Et rien d'orphelin derrière.
    assert session.exec(select(ClientTradeHistory)).all() == []
    assert session.exec(select(Affiliation)).all() == []
    assert session.exec(select(Deal)).all() == []
    session.close()


# ── L'onglet technique a-t-il de quoi montrer ? ─────────────────────

def test_le_jeu_produit_plusieurs_familles_de_sous_jacent(base):
    """Un jeu où tout serait mono-indice ne testerait rien des moyennes.

    L'écran sépare mono/multi et indice/action/ETF : les quatre doivent
    exister quelque part dans le jeu, sans quoi une régression sur le
    classement passerait inaperçue.
    """
    familles = set()
    for client in base.exec(select(Client)).all():
        vue = client_intelligence(base, client.id)["technical"]
        familles.update(f["label"] for f in vue["by_family"])
    for attendue in ("Mono-indice", "Panier d'indices", "Mono-action",
                     "Panier d'actions", "Mono-ETF"):
        assert attendue in familles, f"« {attendue} » absente du jeu : {familles}"


def test_les_trois_etats_d_execution_existent_dans_le_jeu(base):
    """« Avec nous », « ailleurs » et « inconnu » doivent tous être représentés.

    Un jeu entièrement renseigné n'exercerait jamais l'affichage du cas
    majoritaire d'un historique réellement versé par un client : l'inconnu.
    """
    total = {"with_us": 0, "elsewhere": 0, "unknown": 0}
    for client in base.exec(select(Client)).all():
        execution = client_intelligence(base, client.id)["technical"]["execution"]
        for cle in total:
            total[cle] += execution[cle]
    assert all(total[cle] > 0 for cle in total), total


def test_une_comparaison_de_prix_est_possible_quelque_part(base):
    """C'est le renseignement pour lequel ce sous-onglet existe : à quel prix
    la concurrence a servi. Il faut donc au moins un client où les DEUX
    médianes existent — comparer notre prix à rien produirait un nombre qui
    ressemble à une mesure."""
    comparables = [
        c.name for c in base.exec(select(Client)).all()
        if all(client_intelligence(base, c.id)["technical"]["execution"][cle]
               is not None
               for cle in ("median_price_with_us", "median_price_elsewhere"))
    ]
    assert comparables, "aucun client ne permet la comparaison de prix"


def test_un_capital_garanti_n_invente_pas_un_coupon(base):
    """Le cas qui distingue une absence de donnée d'un niveau nul : sur Jura,
    le capital garanti n'a pas de coupon, et il doit rester à None."""
    jura = _client(base, "Jura Assurances")
    lignes = client_intelligence(base, jura.id)["technical"]["rows"]
    garanti = [l for l in lignes if l["product_type"] == "Capital garanti"]
    assert garanti and garanti[0]["coupon_pct"] is None
    assert garanti[0]["protection_pct"] == 100.0


def test_l_univers_declare_rencontre_vraiment_les_sous_jacents_traites(base):
    """« SX5E » ne rencontre jamais « ^STOXX50E ».

    La superposition déclaré / observé compare des libellés normalisés. Un
    univers saisi en noms d'usage ne correspond à aucune transaction, et l'écran
    conclut que le client n'a jamais traité son propre univers — sans que rien
    ne le signale, puisque le résultat est un écran vide et non une erreur.
    """
    rhone = _client(base, "Rhône Asset Management")
    espace = client_intelligence(base, rhone.id)["negative_space"]["underlyings"]
    utilises = {ligne["label"] for ligne in espace["used"]}
    assert utilises, ("aucun sous-jacent déclaré ne correspond à ce qui est "
                      f"traité : {espace}")
    assert "^STOXX50E" in utilises
