"""Variantes — étape 5 : le tableau comparatif.

À iso-valeur, le prix ne départage plus rien : c'est même le but d'une
restructuration réussie. La colonne qui décide est donc P(récupérer le pair
D'ORIGINE) — et c'est elle que ces tests protègent, parce qu'elle est le seul
endroit du chantier où un chiffre juste peut mener à la conclusion inverse.

Le piège, mesuré sur le dossier Marex : la note neuve affiche 53,8 % de chance
de rendre SON pair, contre 28,0 % pour l'avenant. Rangés côte à côte, ces deux
nombres donnent le roll gagnant. Mais le roll ne rend son pair que sur un
nominal réduit — le détenteur débouclé à 46 % n'achète que 53 unités d'une note
à 87 %. Sa récupération plafonne à 53 % du nominal d'origine, définitivement,
alors que l'avenant garde 100 % atteignable.

Une probabilité sans son plafond n'est donc pas comparable, et c'est ce que le
tableau doit encoder plutôt que laisser le lecteur le reconstituer.
"""
import json
from datetime import date, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from backend.app.core.variants import MODE_AVENANT, MODE_ROLL

USER = SimpleNamespace(id=1, entity_id=1)

STRIKE = date(2024, 6, 14)
MATURITE = date(2027, 6, 14)
VALORISATION = date(2026, 6, 14)

PHOENIX = """PARAM COUPON = 2%
PARAM M_AC_BAR = 100%
PARAM M_CPN_BAR = 50%
PARAM M_KI_BAR = 50%

CONSTAT() OBS

AT OBS:
  SET DUE = DUE + COUPON
  SET CPN = INDIC(WOF >= M_CPN_BAR)
  PAY CPN * DUE
  SET DUE = (1 - CPN) * DUE
  SET CALL = INDIC(INDEX >= 3) * INDIC(WOF >= M_AC_BAR)
  PAY CALL * 1
  IF CALL = 1:
    STOP

AT OBS.last:
  SET KI = INDIC(WOF < M_KI_BAR)
  PAY (1 - KI) * 1
  PAY KI * WOF
"""

CALENDRIER = {"OBS": {"start_date": "2024-06-14", "end_date": "2027-06-14",
                      "roll_date": "2024-09-14", "frequency": "3M",
                      "stub": "short_last", "convention": "following"}}

# Le titre tient 80 % du strike deux ans, puis décroche à 34 % — la forme du
# dossier Marex, en plus net.
def _historique():
    dates, serie = [], []
    jour = STRIKE - timedelta(days=7)
    while jour <= VALORISATION:
        if jour.weekday() < 5:
            dates.append(jour.isoformat())
            serie.append(100.0 if jour <= STRIKE
                         else 80.0 if jour < date(2026, 1, 15) else 34.0)
        jour += timedelta(days=1)
    return {"dates": dates, "prices": {"UL.PA": serie}}


# Le contexte STOCKÉ (unités d'affichage), tel que saveScript l'écrit.
CONTEXTE = {
    "script_text": PHOENIX,
    "params": {"COUPON": 2.0, "M_AC_BAR": 100.0, "M_CPN_BAR": 50.0, "M_KI_BAR": 50.0},
    "constats": CALENDRIER,
    "global": {
        "r": 2.5, "T": 3.0, "model": "constant",
        "strike_date": "2024-06-14", "value_date": "2024-06-18",
        "payment_date": "2027-06-23", "valuation_date": "2026-06-14",
        "underlyings": [{"name": "U1", "ticker": "UL.PA", "ccy": "EUR",
                         "sigma": 50.0, "q": 0.0}],
        "corr_matrix": [[1.0]],
    },
}

# Le corps de requête que l'ÉCRAN envoie (unités moteur).
BASE = {
    "script": PHOENIX,
    "underlyings": [{"name": "U1", "ticker": "UL.PA", "ccy": "EUR",
                     "sigma": 0.50, "q": 0.0}],
    "corr_matrix": [[1.0]],
    "r": 0.025, "N": 4000, "model": "constant", "constats": CALENDRIER,
    "user_params": {"COUPON": 0.02, "M_AC_BAR": 1.0,
                    "M_CPN_BAR": 0.5, "M_KI_BAR": 0.5},
    "strike_date": "2024-06-14", "value_date": "2024-06-18",
    "maturity_date": "2027-06-14", "payment_date": "2027-06-23",
    "valuation_date": "2026-06-14", "settlement_ccy": "EUR",
}


@pytest.fixture
def client(monkeypatch):
    import backend.app.db.database as db
    from backend.app.api import inlife as api_inlife
    from backend.app.api.auth import get_current_user
    from backend.app.db.models import User

    monkeypatch.setattr(api_inlife, "load_hist_prices",
                        lambda tickers, debut, fin: _historique())
    moteur = create_engine("sqlite://", poolclass=StaticPool,
                           connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(moteur)
    monkeypatch.setattr(db, "engine", moteur)

    from backend.app.main import app
    with Session(moteur) as s:
        u = User(username="phil", email="phil@test.local", password_hash="x", entity_id=1)
        s.add(u); s.commit(); s.refresh(u)
        uid = u.id

    def _session():
        with Session(moteur) as s:
            yield s

    def _user():
        with Session(moteur) as s:
            return s.get(User, uid)

    app.dependency_overrides[db.get_session] = _session
    app.dependency_overrides[get_current_user] = _user
    yield TestClient(app)
    app.dependency_overrides.clear()


def _origine(client) -> int:
    res = client.post("/api/db/scripts", json={
        "name": "Phoenix", "script_text": CONTEXTE["script_text"],
        "params_json": json.dumps(CONTEXTE["params"]),
        "constats_json": json.dumps(CONTEXTE["constats"]),
        "global_params_json": json.dumps(CONTEXTE["global"])})
    assert res.status_code == 201, res.text
    return res.json()["id"]


def _variante(client, pid, titre, mode, delta):
    res = client.post(f"/api/db/scripts/{pid}/variants", json={
        "variant_title": titre, "variant_mode": mode, "delta": delta})
    assert res.status_code == 201, res.text
    return res.json()["id"]


def _comparer(client, ids, N=4000):
    res = client.post("/api/variants/compare",
                      json={"base": BASE, "variant_ids": ids, "N": N})
    assert res.status_code == 200, res.text
    return {l["titre"]: l for l in res.json()["lignes"]}


# ── L'origine est dans le tableau, comme référence ──────────────────

def test_l_origine_est_repricee_dans_le_meme_appel(client):
    """Pas reprise d'un calcul antérieur : la comparaison n'a de sens que si
    toutes les lignes sortent du même tirage et de la même base de marché."""
    _origine(client)
    lignes = _comparer(client, [])
    assert "Origine" in lignes
    o = lignes["Origine"]
    assert o["ecart"] == 0.0 and o["plafond"] == 1.0
    assert 0 < o["prix"] < 1


# ── L'avenant : le nominal ne bouge pas ─────────────────────────────

def test_un_avenant_garde_le_pair_atteignable(client):
    pid = _origine(client)
    vid = _variante(client, pid, "Protection 20 %", MODE_AVENANT,
                    {"set": {"params[M_KI_BAR]": 20.0}})
    lignes = _comparer(client, [vid])
    v = lignes["Protection 20 %"]

    assert v["plafond"] == 1.0, "le nominal est inchangé"
    # Une barrière abaissée protège : la probabilité de rendre le pair monte.
    assert v["proba_pair_origine"] > lignes["Origine"]["proba_pair_origine"]


def test_les_param_de_la_variante_atteignent_bien_le_moteur(client):
    """Le tableau ne vaut rien si les écarts n'agissent pas : on exige que le
    prix BOUGE, pas qu'il ait une valeur."""
    pid = _origine(client)
    a = _variante(client, pid, "KI 20", MODE_AVENANT, {"set": {"params[M_KI_BAR]": 20.0}})
    b = _variante(client, pid, "KI 90", MODE_AVENANT, {"set": {"params[M_KI_BAR]": 90.0}})
    lignes = _comparer(client, [a, b])

    assert lignes["KI 20"]["prix"] != pytest.approx(lignes["KI 90"]["prix"], rel=1e-4)
    assert lignes["KI 20"]["prix"] > lignes["KI 90"]["prix"]


def test_les_pourcentages_stockes_sont_convertis_pour_le_moteur(client):
    """Le contexte est en unités d'AFFICHAGE (50 pour 50 %), la requête en
    unités moteur (0,50). Sans conversion, une barrière de variante partirait à
    5 000 % — et le prix resterait un nombre."""
    pid = _origine(client)
    vid = _variante(client, pid, "Identique", MODE_AVENANT,
                    {"set": {"params[M_KI_BAR]": 50.0}})
    lignes = _comparer(client, [vid])
    # Même valeur que l'origine : l'écart doit être du bruit MC, pas un gouffre.
    assert abs(lignes["Identique"]["ecart"]) < 0.02, lignes["Identique"]


# ── Le roll : le nominal se réduit, et c'est LE piège ───────────────

def test_une_note_neuve_plafonne_la_recuperation(client):
    """Le détenteur débouclé à P₀ n'achète que P₀/P_neuve unités. Son plafond
    tombe donc sous 100 %, définitivement, et c'est ce que la colonne doit
    dire."""
    pid = _origine(client)
    vid = _variante(client, pid, "Roll 3 ans", MODE_ROLL, {})
    lignes = _comparer(client, [vid])
    r, o = lignes["Roll 3 ans"], lignes["Origine"]

    assert r["plafond"] < 1.0, "une note neuve réduit le nominal"
    assert r["plafond"] == pytest.approx(o["prix"] / r["prix"], rel=1e-3)


def test_la_proba_du_roll_est_ramenee_au_pair_D_ORIGINE(client):
    """LE test de l'étape.

    La note neuve a toutes les chances de rendre SON pair — elle est strikée à
    la monnaie. Mais rendre le pair D'ORIGINE lui demanderait de payer bien plus
    que le sien, puisque le détenteur n'en détient qu'une fraction. La colonne
    doit donc être NETTEMENT plus basse que la P(≥100 %) brute de cette note.

    Sans ce ramené, le tableau afficherait 54 % contre 28 % et donnerait le roll
    gagnant, alors qu'il plafonne la récupération à la moitié du nominal."""
    pid = _origine(client)
    vid = _variante(client, pid, "Roll", MODE_ROLL, {})
    lignes = _comparer(client, [vid])
    r = lignes["Roll"]

    # Le seuil exigé de la note neuve est 1/plafond, très au-dessus du pair.
    assert 1.0 / r["plafond"] > 1.3, "le scénario doit bien être piégeux"
    assert r["proba_pair_origine"] < 0.10, (
        "récupérer le pair d'origine par un roll est quasi impossible ici")


def test_un_roll_ne_reprend_pas_les_niveaux_du_term_sheet_d_origine(client):
    """Les laisser passer ferait repartir les barrières d'un strike vieux de
    deux ans : une note neuve à 34 % du monde d'avant, sous des barrières qui
    la croient intacte. Le prix resterait plausible."""
    pid = _origine(client)
    vid = _variante(client, pid, "Roll", MODE_ROLL, {})
    lignes = _comparer(client, [vid])
    # Strikée à la monnaie, la note neuve vaut bien plus que la note effondrée.
    assert lignes["Roll"]["prix"] > lignes["Origine"]["prix"] * 1.4, lignes


# ── Les refus se lisent, ils ne se devinent pas ─────────────────────

def test_une_variante_impriceable_garde_sa_ligne_avec_son_motif(client):
    """L'omettre laisserait croire qu'elle n'existe pas ; lui donner un prix nul
    la ferait classer dernière. Un refus se lit."""
    pid = _origine(client)
    vid = _variante(client, pid, "Cassée", MODE_AVENANT,
                    {"set": {"script": "CECI N'EST PAS DU PAYSCRIPT"}})
    lignes = _comparer(client, [vid])

    assert "Cassée" in lignes
    assert lignes["Cassée"]["prix"] is None
    assert lignes["Cassée"]["refus"]


def test_le_tableau_compte_les_ecarts_de_chaque_ligne(client):
    pid = _origine(client)
    vid = _variante(client, pid, "Deux écarts", MODE_AVENANT,
                    {"set": {"params[M_KI_BAR]": 30.0, "params[COUPON]": 0.0}})
    assert _comparer(client, [vid])["Deux écarts"]["ecarts"] == 2


def test_toutes_les_lignes_portent_les_memes_colonnes(client):
    """Le tableau les lit sans vérifier : une clé manquante afficherait une
    colonne vide plutôt qu'une erreur."""
    pid = _origine(client)
    ids = [_variante(client, pid, "A", MODE_AVENANT, {}),
           _variante(client, pid, "R", MODE_ROLL, {})]
    attendu = {"id", "titre", "mode", "prix", "ecart", "proba_pair_origine",
               "plafond", "duree", "ecarts"}
    for ligne in _comparer(client, ids).values():
        assert attendu <= set(ligne), ligne


# ── Le corps de requête que l'ÉCRAN construit ───────────────────────
#
# Ces tests-là ne portent pas sur le moteur, qui sait déjà séparer le rejeu du
# pricing, mais sur le CHEMIN D'APPEL. C'est le troisième fil débranché du même
# type dans ce chantier : un mécanisme correct qu'un appelant n'emprunte pas.
# Un test au seul niveau du moteur ne l'aurait pas vu.

def _vue(client, vid):
    res = client.get(f"/api/db/scripts/variants/{vid}/resolved")
    assert res.status_code == 200, res.text
    return res.json()


def _corps_comme_l_ecran(vue):
    """Exactement ce que `_inLifeBody()` produit sur une variante affichée.

    Le corps porte les termes de l'ORIGINE — c'est sous eux que le passé se
    rejoue — et le bloc `variant` porte ce que l'écran montre."""
    from backend.app.core.variants import params_moteur
    ctx, base = vue["contexte"], vue["base_pricing"]
    return {
        **BASE,
        "script": base["script"],
        "user_params": base["user_params"],
        "constats": base["constats"],
        "variant": {
            "script": ctx["script_text"],
            "user_params": params_moteur(ctx["script_text"], ctx["params"]),
            "constats": ctx["constats"],
            "mode": "avenant",
        },
    }


def test_un_avenant_expose_les_termes_de_rejeu_de_son_origine(client):
    pid = _origine(client)
    vid = _variante(client, pid, "AC 50", MODE_AVENANT,
                    {"set": {"params[M_AC_BAR]": 50.0}})
    base = _vue(client, vid)["base_pricing"]

    assert base["script"] == PHOENIX
    # Unités MOTEUR : le contexte stocke 100, la requête veut 1,0.
    assert base["user_params"]["M_AC_BAR"] == 1.0
    assert base["constats"] == CALENDRIER


def test_une_note_neuve_n_expose_pas_de_termes_de_rejeu(client):
    """Elle n'a pas de passé : lui donner une base de rejeu suggérerait qu'il
    y a quelque chose à rejouer."""
    pid = _origine(client)
    vid = _variante(client, pid, "Roll", MODE_ROLL, {})
    assert "base_pricing" not in _vue(client, vid)


def test_le_corps_de_l_ecran_ne_rappelle_pas_dans_le_passe(client):
    """LE test de ce correctif.

    Le titre est resté au-dessus de 50 % pendant six constatations. Une
    variante à `M_AC_BAR = 50 %` rappellerait donc largement dans le passé si le
    corps de requête ne séparait pas les deux jeux de termes."""
    pid = _origine(client)
    vid = _variante(client, pid, "AC 50", MODE_AVENANT,
                    {"set": {"params[M_AC_BAR]": 50.0}})

    res = client.post("/api/price/in-life", json=_corps_comme_l_ecran(_vue(client, vid)))
    assert res.status_code == 200, res.text
    corps = res.json()
    assert not corps.get("early_recall"), corps
    assert corps["past"]["observations_done"] == 8


def test_sans_la_separation_le_passe_rappelle_bien(client):
    """Le contrôle négatif, sans lequel le test précédent ne prouve rien.

    C'est exactement ce que faisait l'écran avant ce correctif : envoyer les
    termes de la variante comme s'ils étaient ceux du deal."""
    from backend.app.core.variants import params_moteur
    pid = _origine(client)
    vid = _variante(client, pid, "AC 50", MODE_AVENANT,
                    {"set": {"params[M_AC_BAR]": 50.0}})
    ctx = _vue(client, vid)["contexte"]

    naif = {**BASE, "script": ctx["script_text"], "constats": ctx["constats"],
            "user_params": params_moteur(ctx["script_text"], ctx["params"])}
    corps = client.post("/api/price/in-life", json=naif).json()
    assert corps.get("early_recall") is True, (
        "le scénario doit bien être piégeux, sinon le test d'à côté ne dit rien")


def test_la_barriere_de_la_variante_agit_sur_la_vie_restante(client):
    """Le pendant : protéger le passé sans appliquer les nouveaux termes à
    l'avenir rendrait le prix d'origine sous une étiquette de variante."""
    pid = _origine(client)
    haute = _variante(client, pid, "AC 100", MODE_AVENANT,
                      {"set": {"params[M_AC_BAR]": 100.0}})
    basse = _variante(client, pid, "AC 50", MODE_AVENANT,
                      {"set": {"params[M_AC_BAR]": 50.0}})

    prix = {}
    for nom, vid in (("haute", haute), ("basse", basse)):
        r = client.post("/api/price/in-life", json=_corps_comme_l_ecran(_vue(client, vid)))
        assert r.status_code == 200, r.text
        prix[nom] = r.json()["price"]
    # Un rappel atteignable vaut plus cher qu'un rappel hors d'atteinte.
    assert prix["basse"] > prix["haute"] * 1.02, prix


def test_les_termes_de_rejeu_portent_le_calendrier_de_l_origine(client):
    """L'écran doit pouvoir le reconvertir : c'est la forme STOCKÉE qui est
    rendue, celle de `constats_json`, et pas une forme intermédiaire."""
    pid = _origine(client)
    vid = _variante(client, pid, "AC 50", MODE_AVENANT,
                    {"set": {"params[M_AC_BAR]": 50.0}})
    assert _vue(client, vid)["base_pricing"]["constats"] == CALENDRIER


def test_un_calendrier_mal_forme_est_refuse_lisiblement(client):
    """Régression : une fréquence en OBJET plutôt qu'en chaîne — la forme
    stockée envoyée telle quelle — levait une AttributeError non rattrapée. Le
    serveur répondait « Internal Server Error » en texte brut, que l'écran ne
    savait même pas lire (« Unexpected token 'I' »).

    Un refus doit se lire, surtout celui-là : il désigne un défaut de
    l'appelant, donc quelque chose de corrigeable."""
    pid = _origine(client)
    vid = _variante(client, pid, "AC 50", MODE_AVENANT,
                    {"set": {"params[M_AC_BAR]": 50.0}})
    corps = _corps_comme_l_ecran(_vue(client, vid))
    # La forme stockée de l'écran : fréquence en objet.
    corps["variant"]["constats"] = {
        "OBS": {**CALENDRIER["OBS"], "frequency": {"value": 3, "unit": "M"}}}

    res = client.post("/api/price/in-life", json=corps)
    assert res.status_code == 422, res.status_code
    assert "mal formé" in res.json()["detail"]


# ── Les analytiques suivent la variante, sans réécrire le passé ─────

def _corps_analytique(vue, **extra):
    """Ce que `_baseBody()` produit sur une variante affichée."""
    from backend.app.core.variants import params_moteur
    ctx, base = vue["contexte"], vue["base_pricing"]
    corps = {k: v for k, v in BASE.items() if k != "N"}
    corps.update({
        "script": base["script"], "user_params": base["user_params"],
        "constats": base["constats"], "T": 3.0,
        "anchor": BASE["strike_date"],
        "variant": {"script": ctx["script_text"],
                    "user_params": params_moteur(ctx["script_text"], ctx["params"]),
                    "constats": ctx["constats"], "mode": "avenant"},
    })
    corps.update(extra)
    return corps


def test_les_probabilites_ne_rappellent_pas_dans_le_passe(client):
    """Régression : les analytiques passaient par un corps que je n'avais pas
    corrigé. L'onglet Probabilités rejouait donc le passé sous la barrière de la
    VARIANTE et comptait des rappels qui n'ont jamais eu lieu — le prix décrivait
    une chose, la distribution une autre, et rien ne le signalait."""
    pid = _origine(client)
    vid = _variante(client, pid, "AC 50", MODE_AVENANT,
                    {"set": {"params[M_AC_BAR]": 50.0}})
    vue = _vue(client, vid)

    res = client.post("/api/proba", json=_corps_analytique(vue, N=4000))
    assert res.status_code == 200, res.text
    d = res.json()
    assert d["in_life"] is True
    # Huit constatations écoulées, dont six au-dessus de 50 % : si le passé
    # avait été rejoué avec la variante, il ne resterait aucune vie à décrire.
    assert d["total"] > 0 and d["expected_life"] > 0


def test_la_barriere_de_la_variante_agit_sur_les_probabilites(client):
    """Le pendant : suivre la variante ne sert à rien si son seuil n'agit pas
    sur la vie restante. On exige que la probabilité de rappel BOUGE."""
    pid = _origine(client)
    haute = _vue(client, _variante(client, pid, "AC 100", MODE_AVENANT,
                                   {"set": {"params[M_AC_BAR]": 100.0}}))
    basse = _vue(client, _variante(client, pid, "AC 50", MODE_AVENANT,
                                   {"set": {"params[M_AC_BAR]": 50.0}}))

    p_haute = client.post("/api/proba", json=_corps_analytique(haute, N=4000)).json()
    p_basse = client.post("/api/proba", json=_corps_analytique(basse, N=4000)).json()
    assert p_basse["autocall_pct"] > p_haute["autocall_pct"], (
        p_haute["autocall_pct"], p_basse["autocall_pct"])


def test_la_vue_de_variante_porte_le_contexte_de_son_origine(client):
    """L'écran en a besoin pour calculer ses écarts au moment d'enregistrer."""
    pid = _origine(client)
    vid = _variante(client, pid, "AC 50", MODE_AVENANT,
                    {"set": {"params[M_AC_BAR]": 50.0}})
    parent = _vue(client, vid)["contexte_parent"]

    assert parent["params"]["M_AC_BAR"] == 100.0, "la valeur d'ORIGINE, pas celle de la variante"
    assert parent["script_text"] == PHOENIX
    assert {"script_text", "params", "constats", "global"} == set(parent)


def test_enregistrer_un_delta_le_relit_a_l_identique(client):
    """Le cycle complet : écrire des écarts, les relire, retrouver le produit.

    Sans lui, travailler sur une variante puis y revenir perdait tout — l'écran
    rechargeait un contexte qui ne portait aucune modification."""
    pid = _origine(client)
    vid = _variante(client, pid, "Brouillon", MODE_AVENANT, {})
    assert _vue(client, vid)["contexte"]["params"]["M_AC_BAR"] == 100.0

    res = client.put(f"/api/db/scripts/variants/{vid}", json={
        "delta": {"set": {"params[M_AC_BAR]": 50.0, "params[COUPON]": 0.0}}})
    assert res.status_code == 200, res.text

    relu = _vue(client, vid)
    assert relu["contexte"]["params"]["M_AC_BAR"] == 50.0
    assert relu["contexte"]["params"]["COUPON"] == 0.0
    assert len(relu["ecarts"]) == 2
    # Et l'origine n'a pas bougé.
    assert relu["contexte_parent"]["params"]["M_AC_BAR"] == 100.0


# ── L'appariement des dates et des rappels ──────────────────────────

MENSUEL = {"OBS": {**CALENDRIER["OBS"], "frequency": "1M", "roll_date": "2024-07-14"}}


def test_les_comptes_de_rappel_sont_tous_lisibles_par_leur_date(client):
    """Régression : l'écran apparie `event_counts[t]` pour chaque `t` de
    `obs_times`. Les deux sortaient arrondis DIFFÉREMMENT — les dates brutes
    (0,019230769…), les clés à quatre décimales. La recherche ratait dès qu'une
    date n'était pas ronde.

    Sur un calendrier mensuel, l'écran ne lisait que 23 rappels sur 58 : le
    graphe « P(rappel) par date » restait vide et le donut n'affichait que la
    perte en capital, alors que le compteur annonçait 32 % de rappels. Un
    trimestriel, lui, tombait juste par hasard — d'où un défaut resté invisible.

    On exige donc l'égalité EXACTE des deux totaux, pas leur voisinage."""
    corps = {k: v for k, v in BASE.items() if k != "N"}
    corps.update({"constats": MENSUEL, "T": 3.0, "N": 4000,
                  "anchor": BASE["strike_date"]})
    d = client.post("/api/proba", json=corps).json()

    assert d["has_autocall"] and d["autocall_count"] > 0
    lisibles = sum(d["event_counts"].get(str(t), d["event_counts"].get(t, 0))
                   for t in d["obs_times"])
    assert lisibles == d["autocall_count"], (
        f"{lisibles} rappels lisibles sur {d['autocall_count']} — "
        f"des clés de date ne tombent pas juste")


def test_aucune_date_de_rappel_n_est_orpheline(client):
    """Le pendant : un compte dont la date n'est pas dans `obs_times` ne
    s'afficherait nulle part."""
    corps = {k: v for k, v in BASE.items() if k != "N"}
    corps.update({"constats": MENSUEL, "T": 3.0, "N": 4000,
                  "anchor": BASE["strike_date"]})
    d = client.post("/api/proba", json=corps).json()

    dates = {str(t) for t in d["obs_times"]} | set(d["obs_times"])
    orphelines = [k for k in d["event_counts"] if k not in dates and float(k) not in set(d["obs_times"])]
    assert not orphelines, orphelines


# ── La parenté, et la base qui ne doit pas être mutée ───────────────

def test_une_declinaison_d_un_autre_deal_est_refusee(client):
    """Régression (audit C3).

    Le comparateur vérifiait qu'une variante était lisible, jamais qu'elle
    descendait du produit envoyé. Appliquer le delta d'un produit A à la base
    d'un produit B rendait un tableau de chiffres sans aucun sens, sous des
    titres qui en avaient l'air."""
    a = _origine(client)
    b = client.post("/api/db/scripts", json={
        "name": "Autre deal", "script_text": CONTEXTE["script_text"],
        "params_json": json.dumps(CONTEXTE["params"]),
        "constats_json": json.dumps(CONTEXTE["constats"]),
        "global_params_json": json.dumps(CONTEXTE["global"])}).json()["id"]
    intruse = _variante(client, b, "Étrangère", MODE_AVENANT,
                        {"set": {"params[M_KI_BAR]": 20.0}})

    res = client.post("/api/variants/compare",
                      json={"base": BASE, "parent_id": a, "variant_ids": [intruse]})
    assert res.status_code == 200
    ligne = {l["titre"]: l for l in res.json()["lignes"]}["Étrangère"]
    assert ligne["prix"] is None
    assert "autre deal" in ligne["refus"].lower()


def test_une_note_neuve_ne_contamine_pas_les_lignes_suivantes(client):
    """Régression (nouveau, N3).

    `_corps_roll` filtrait les sous-jacents de la base puis écrivait dedans pour
    convertir les unités — mais sur des RÉFÉRENCES aux dictionnaires partagés
    par toutes les lignes. Une note neuve qui touche une calibration la ferait
    fuiter dans tout ce qui se calcule après elle.

    Inoffensif tant que le delta ne porte aucun champ de sous-jacent ; le test
    fixe le contrat avant que ce ne soit plus le cas."""
    pid = _origine(client)
    roll = _variante(client, pid, "Roll", MODE_ROLL, {})
    apres = _variante(client, pid, "Avenant après", MODE_AVENANT, {})

    seul = _comparer(client, [apres])["Avenant après"]["prix"]
    ensemble = _comparer(client, [roll, apres])["Avenant après"]["prix"]
    assert ensemble == pytest.approx(seul, rel=1e-9), (
        "l'avenant doit valoir la même chose, qu'un roll ait été calculé avant lui")


def test_sans_parent_id_la_comparaison_reste_possible(client):
    """Non-régression : le champ est facultatif, un appel qui ne le porte pas
    doit continuer de fonctionner."""
    pid = _origine(client)
    vid = _variante(client, pid, "T", MODE_AVENANT, {})
    assert "T" in _comparer(client, [vid])


# ── Chaque analytique voit-elle la variante ? ───────────────────────

def _analytique(vue, endpoint, req_cls, **extra):
    """Le corps que `_baseBody()` produit, envoyé à une analytique."""
    from backend.app.core.variants import params_moteur
    ctx, base = vue["contexte"], vue["base_pricing"]
    corps = {k: v for k, v in BASE.items() if k != "N"}
    corps.update({"script": base["script"], "user_params": base["user_params"],
                  "constats": base["constats"], "T": 3.0,
                  "anchor": BASE["strike_date"],
                  "variant": {"script": ctx["script_text"],
                              "user_params": params_moteur(ctx["script_text"], ctx["params"]),
                              "constats": ctx["constats"], "mode": "avenant"}})
    corps.update(extra)
    sans = {k: v for k, v in corps.items() if k != "variant"}
    return endpoint(req_cls(**sans)), endpoint(req_cls(**corps))


def test_les_scenarios_suivent_la_variante(client):
    """Régression (audit A1) — la quatrième occurrence du même motif.

    L'endpoint calculait le script résiduel de la variante, le validait, puis
    passait `req.script` aux workers, qui recompilent depuis le texte. Le script
    de la variante était calculé PUIS JETÉ : la grille décrivait le produit
    d'origine sous une étiquette de variante, au dernier chiffre près.

    Le test compare AVEC et SANS variante. Vérifier que la case sans choc vaut
    le prix — ce que faisait le test de cohérence — passait sans rien voir,
    puisqu'il n'employait pas de variante."""
    from backend.app.api import scenarios as api_sc
    from backend.app.core.schemas import ScenarioRequest

    pid = _origine(client)
    vue = _vue(client, _variante(client, pid, "AC 50", MODE_AVENANT,
                                 {"set": {"params[M_AC_BAR]": 50.0}}))
    sans, avec = _analytique(vue, api_sc.scenarios_endpoint, ScenarioRequest,
                             N=2000, spot_shocks=[0.0], vol_shocks=[0.0])
    assert avec["prices"][0][0] != pytest.approx(sans["prices"][0][0], rel=1e-6), (
        "la grille de stress doit décrire la variante, pas l'origine")


def test_la_grille_de_stress_et_la_grille_2d_concordent(client):
    """Deux chemins de code entièrement distincts — l'un par processus séparés,
    l'autre en direct — doivent pricer la même variante à l'identique. Qu'ils
    divergent signalerait qu'une hypothèse n'atteint pas l'un des deux."""
    from backend.app.api import scenarios as api_sc, simulation as api_sim
    from backend.app.core.schemas import ScenarioRequest, GridRequest

    pid = _origine(client)
    vue = _vue(client, _variante(client, pid, "AC 50", MODE_AVENANT,
                                 {"set": {"params[M_AC_BAR]": 50.0}}))
    _, stress = _analytique(vue, api_sc.scenarios_endpoint, ScenarioRequest,
                            N=2000, spot_shocks=[0.0], vol_shocks=[0.0])
    _, grille = _analytique(vue, api_sim.grid_endpoint, GridRequest, N=2000,
                            param_x="M_CPN_BAR", x_min=0.5, x_max=0.6, x_steps=2,
                            param_y="M_KI_BAR", y_min=0.5, y_max=0.6, y_steps=2)
    assert stress["prices"][0][0] == pytest.approx(grille["prices"][0][0], rel=1e-9)
