"""Variantes — étape 2 : le modèle de filiation.

Une variante est un DELTA rattaché à une origine, jamais une copie. Ce choix
n'est pas une économie de place : c'est ce qui rend possibles les deux
exigences d'affichage sans lesquelles l'outil ne sert à rien.

Colorer ce qui a changé devient gratuit — la couleur est l'appartenance au
delta, pas le résultat d'une comparaison à refaire sur les bons champs sans en
oublier. Et griser ce qui a été retiré devient POSSIBLE : dans une copie, un
sous-jacent retiré est simplement absent, et rien ne distingue « on l'a
enlevé » de « il n'y a jamais été ».

Ces tests tiennent donc surtout sur l'héritage — ce qui n'est pas dit doit
suivre l'origine, et rien d'autre ne doit bouger.
"""
import json
from datetime import date

import pytest
from fastapi.testclient import TestClient

from backend.app.core.variants import (
    MODE_AVENANT, MODE_ROLL, VariantError, decrire_ecarts, lire, resoudre, valider,
)

PARENT = {
    "script_text": "PARAM M_PDI_BAR = 50%\nCONSTAT() OBS\nAT OBS.last:\n  PAY 1\n",
    "params": {"M_PDI_BAR": 0.50, "COUPON": 0.0133},
    "constats": {"OBS": {"start_date": "2024-06-14", "end_date": "2027-06-14",
                         "frequency": "1M", "convention": "following"}},
    "global": {
        "r": 2.5, "model": "constant",
        "strike_date": "2024-06-14", "valuation_date": "2026-05-08",
        "underlyings": [
            {"name": "GLE.PA", "sigma": 34.27, "q": 2.46},
            {"name": "UCG.MI", "sigma": 31.13, "q": 4.47},
            {"name": "STLAM.MI", "sigma": 53.15, "q": 0.0},
        ],
        "corr_matrix": [[1.0, 0.78, 0.29], [0.78, 1.0, 0.25], [0.29, 0.25, 1.0]],
    },
}


# ── L'héritage, qui est tout l'intérêt ──────────────────────────────

def test_ce_qui_n_est_pas_dit_est_herite():
    """Un delta ne décrit QUE ses écarts. Le reste ne doit pas dériver — sinon
    la variante ne se comparerait plus « toutes choses égales par ailleurs »,
    et l'écart de prix mesurerait autre chose que la restructuration."""
    ctx = resoudre(PARENT, {"set": {"params[M_PDI_BAR]": 0.30}})

    assert ctx["params"]["M_PDI_BAR"] == 0.30
    assert ctx["params"]["COUPON"] == PARENT["params"]["COUPON"]
    assert ctx["script_text"] == PARENT["script_text"]
    assert ctx["constats"] == PARENT["constats"]
    assert ctx["global"]["underlyings"] == PARENT["global"]["underlyings"]


def test_un_delta_vide_rend_le_parent_a_l_identique():
    for delta in (None, {}, {"set": {}}, {"set": {}, "removed": []}):
        assert resoudre(PARENT, delta) == PARENT


def test_resoudre_ne_modifie_jamais_le_parent():
    """Le parent est partagé entre toutes ses variantes : le muter ferait
    dépendre chaque résolution de l'ordre dans lequel on les a lues."""
    avant = json.dumps(PARENT, sort_keys=True)
    resoudre(PARENT, {"set": {"params[M_PDI_BAR]": 0.30},
                      "removed": ["underlyings[STLAM.MI]"]}, MODE_ROLL)
    assert json.dumps(PARENT, sort_keys=True) == avant


@pytest.mark.parametrize("chemin, valeur", [
    ("script", "AT OBS:\n  PAY 0\n"),
    ("params[M_PDI_BAR]", 0.30),
    ("constats[OBS].end_date", "2029-06-14"),
    ("global.r", 3.5),
])
def test_chaque_espace_de_noms_atteint_sa_cible(chemin, valeur):
    ctx = resoudre(PARENT, {"set": {chemin: valeur}}, MODE_ROLL)
    assert lire(ctx, chemin) == valeur


def test_l_espace_des_sous_jacents_sert_a_ajouter_un_titre(chemin=None):
    """Le cinquième espace de noms ne se lit pas comme les autres.

    `underlyings[NOM]` n'adresse pas un champ à écraser : il AJOUTE un titre au
    panier, avec sa définition entière. Modifier la calibration d'un titre
    hérité est refusé — c'est une hypothèse de marché, commune à toute la
    famille de déclinaisons (voir test_variantes_roll)."""
    neuf = {"ticker": "SAN.PA", "sigma": 28.0,
            "correlations": {"GLE.PA": 0.6, "UCG.MI": 0.5, "STLAM.MI": 0.2}}
    ctx = resoudre(PARENT, {"set": {"underlyings[SAN.PA]": neuf}}, MODE_ROLL)
    assert lire(ctx, "underlyings[SAN.PA].sigma") == 28.0
    assert len(ctx["global"]["corr_matrix"]) == 4


def test_un_chemin_inconnu_est_refuse():
    """Un delta invalide stocké est bien pire qu'un delta refusé : il ne se
    manifeste qu'à la relecture, longtemps après, sur une variante qu'on
    croyait bonne."""
    with pytest.raises(VariantError) as e:
        resoudre(PARENT, {"set": {"barrieres[PDI]": 0.30}})
    assert "Chemin inconnu" in str(e.value)


# ── Le retrait, que seule la forme delta sait exprimer ──────────────

def test_retirer_un_sous_jacent_reduit_aussi_la_correlation():
    """Les deux ne se séparent pas : une matrice 3×3 pour deux noms est soit
    refusée par le moteur, soit « réparée » en silence — et une corrélation
    réparée d'office est une hypothèse que personne n'a saisie."""
    ctx = resoudre(PARENT, {"removed": ["underlyings[UCG.MI]"]}, MODE_ROLL)

    noms = [u["name"] for u in ctx["global"]["underlyings"]]
    assert noms == ["GLE.PA", "STLAM.MI"]
    assert ctx["global"]["corr_matrix"] == [[1.0, 0.29], [0.29, 1.0]]


def test_le_parent_garde_ce_que_la_variante_retire():
    """La condition du grisé : le retrait est un FAIT porté par le delta, et
    l'origine conserve la fiche complète à afficher en grisé. Une copie aurait
    perdu jusqu'au souvenir du titre."""
    delta = {"removed": ["underlyings[UCG.MI]"]}
    ctx = resoudre(PARENT, delta, MODE_ROLL)

    assert not any(u["name"] == "UCG.MI" for u in ctx["global"]["underlyings"])
    assert any(u["name"] == "UCG.MI" for u in PARENT["global"]["underlyings"])
    ecart = next(e for e in decrire_ecarts(PARENT, delta) if e["etat"] == "retire")
    assert ecart["avant"]["name"] == "UCG.MI", "de quoi l'afficher en grisé"


def test_on_ne_vide_pas_le_panier():
    seul = {**PARENT, "global": {**PARENT["global"],
                                 "underlyings": [{"name": "GLE.PA"}],
                                 "corr_matrix": [[1.0]]}}
    with pytest.raises(VariantError):
        resoudre(seul, {"removed": ["underlyings[GLE.PA]"]}, MODE_ROLL)


# ── La règle de structuration : le panier est figé en avenant ───────

@pytest.mark.parametrize("delta", [
    {"removed": ["underlyings[STLAM.MI]"]},
    {"set": {"underlyings[STLAM.MI].sigma": 60.0}},
])
def test_toucher_au_panier_est_refuse_sur_un_avenant(delta):
    """Retirer un nom change le sens de `WOF`. Les flux réalisés restent justes
    — ils ont eu lieu — mais les extrema repris du rejeu décrivent un worst-of
    à trois noms, et rien ne dit ce qu'ils deviennent à deux. Ce n'est donc pas
    un avenant : c'est une note neuve."""
    with pytest.raises(VariantError) as e:
        resoudre(PARENT, delta, MODE_AVENANT)
    assert "roll" in str(e.value)


def test_le_meme_delta_passe_en_note_neuve():
    ctx = resoudre(PARENT, {"removed": ["underlyings[STLAM.MI]"]}, MODE_ROLL)
    assert len(ctx["global"]["underlyings"]) == 2


# ── Ce que l'écran doit colorer ─────────────────────────────────────

def test_les_ecarts_portent_l_avant_et_l_apres():
    """L'écran doit pouvoir écrire « 50 % → 30 % » sans relire les deux
    contextes : sinon il recalculerait un diff, et un diff recalculé ailleurs
    finit par diverger de celui qui a servi à pricer."""
    delta = {"set": {"params[M_PDI_BAR]": 0.30, "constats[OBS].end_date": "2029-06-14"},
             "removed": ["underlyings[STLAM.MI]"]}
    par_chemin = {e["chemin"]: e for e in decrire_ecarts(PARENT, delta)}

    assert par_chemin["params[M_PDI_BAR]"] == {
        "chemin": "params[M_PDI_BAR]", "etat": "modifie", "avant": 0.50, "apres": 0.30}
    assert par_chemin["constats[OBS].end_date"]["avant"] == "2027-06-14"
    assert par_chemin["underlyings[STLAM.MI]"]["etat"] == "retire"


def test_sans_ecart_il_n_y_a_rien_a_colorer():
    assert decrire_ecarts(PARENT, {}) == []


# ── La validation, avant la base ────────────────────────────────────

@pytest.mark.parametrize("delta, mode, motif", [
    ({"set": {}}, "bizarre", "Mode inconnu"),
    ({"ajoute": {}}, MODE_AVENANT, "Clés inattendues"),
    ({"set": []}, MODE_AVENANT, "doit être un objet"),
    ({"removed": {}}, MODE_AVENANT, "doit être une liste"),
    ({"set": {"nimporte[quoi]": 1}}, MODE_AVENANT, "Chemin inconnu"),
    ({"set": {"params[X]": 1}, "removed": ["params[X]"]}, MODE_AVENANT, "à la fois"),
])
def test_un_delta_mal_forme_est_refuse(delta, mode, motif):
    with pytest.raises(VariantError) as e:
        valider(delta, mode)
    assert motif in str(e.value)


# ── L'API ───────────────────────────────────────────────────────────

@pytest.fixture
def client(monkeypatch):
    """Une base neuve par test, EN MÉMOIRE.

    Pas de `tmp_path` : le nettoyage de tmpdir de pytest échoue sur cette
    machine Windows (`PermissionError` sur pytest-of-Philippe), et un test qui
    n'échoue que par son ménage est un test qu'on finit par ignorer.
    `StaticPool` garde une seule connexion, sans quoi chaque session repartirait
    sur une base vide."""
    import backend.app.db.database as db
    from sqlmodel import SQLModel, Session, create_engine
    from sqlalchemy.pool import StaticPool

    moteur = create_engine("sqlite://", poolclass=StaticPool,
                           connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(moteur)
    monkeypatch.setattr(db, "engine", moteur)

    from backend.app.main import app
    from backend.app.api.auth import get_current_user
    from backend.app.db.models import User

    with Session(moteur) as s:
        u = User(username="phil", email="phil@test.local",
                 password_hash="x", entity_id=1)
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
        "name": "Phoenix Marex", "script_text": PARENT["script_text"],
        "params_json": json.dumps(PARENT["params"]),
        "constats_json": json.dumps(PARENT["constats"]),
        "global_params_json": json.dumps(PARENT["global"]),
    })
    assert res.status_code == 201, res.text
    return res.json()["id"]


def test_une_variante_ne_copie_pas_le_contexte_de_son_origine(client):
    """La ligne de variante garde ses blobs VIDES : dupliquer le contexte le
    figerait, et une variante doit suivre son origine pour rester comparable à
    marché constant."""
    from backend.app.db.models import Script
    import backend.app.db.database as db
    from sqlmodel import Session

    pid = _origine(client)
    res = client.post(f"/api/db/scripts/{pid}/variants", json={
        "variant_title": "Capital — PDI 30 %",
        "delta": {"set": {"params[M_PDI_BAR]": 0.30}}})
    assert res.status_code == 201, res.text
    vid = res.json()["id"]

    with Session(db.engine) as s:
        ligne = s.get(Script, vid)
        assert ligne.script_text == "" and ligne.global_params_json == "{}"
        assert ligne.parent_id == pid
    # Et pourtant la variante price un produit complet.
    assert res.json()["contexte"]["script_text"] == PARENT["script_text"]
    assert res.json()["contexte"]["params"]["M_PDI_BAR"] == 0.30


def test_la_variante_suit_son_origine(client):
    """Repricer l'origine déplace ses variantes — c'est la seule façon de les
    comparer à marché constant, et l'usage dominant."""
    pid = _origine(client)
    client.post(f"/api/db/scripts/{pid}/variants", json={
        "variant_title": "AC 50 %", "delta": {"set": {"params[M_AC_BAR]": 0.50}}})

    nouveau = {**PARENT["global"], "r": 4.0}
    client.put(f"/api/db/scripts/{pid}",
               json={"global_params_json": json.dumps(nouveau)})

    v = client.get(f"/api/db/scripts/{pid}/variants").json()[0]
    assert v["contexte"]["global"]["r"] == 4.0
    assert v["contexte"]["params"]["M_AC_BAR"] == 0.50


def test_les_variantes_ne_polluent_pas_la_liste_mais_s_y_comptent(client):
    """Elles vivent en sous-onglets de leur origine ; les remonter à plat
    noierait la liste et ferait perdre ce à quoi elles se comparent."""
    pid = _origine(client)
    for titre in ("Capital", "Sortie", "Hybride"):
        client.post(f"/api/db/scripts/{pid}/variants",
                    json={"variant_title": titre, "delta": {}})

    liste = client.get("/api/db/scripts").json()
    assert len(liste) == 1
    assert liste[0]["variant_count"] == 3
    assert len(client.get("/api/db/scripts?include_variants=true").json()) == 4


def test_les_variantes_restent_a_plat(client):
    """Une variante de variante rendrait « différent de quoi ? » ambigu et la
    couleur illisible."""
    pid = _origine(client)
    vid = client.post(f"/api/db/scripts/{pid}/variants",
                      json={"variant_title": "Capital", "delta": {}}).json()["id"]

    res = client.post(f"/api/db/scripts/{vid}/variants",
                      json={"variant_title": "Capital bis", "delta": {}})
    assert res.status_code == 422
    assert "sœur" in res.json()["detail"]


def test_un_titre_est_obligatoire(client):
    """C'est ce qui permet de s'y retrouver entre cinq déclinaisons."""
    pid = _origine(client)
    res = client.post(f"/api/db/scripts/{pid}/variants",
                      json={"variant_title": "   ", "delta": {}})
    assert res.status_code == 422 and "titre" in res.json()["detail"]


def test_un_delta_incoherent_est_refuse_a_la_creation(client):
    """Refusé maintenant, pas découvert à la relecture sur une variante qu'on
    croyait bonne."""
    pid = _origine(client)
    res = client.post(f"/api/db/scripts/{pid}/variants", json={
        "variant_title": "Panier réduit", "variant_mode": MODE_AVENANT,
        "delta": {"removed": ["underlyings[STLAM.MI]"]}})
    assert res.status_code == 422 and "roll" in res.json()["detail"]


def test_l_api_rend_les_ecarts_prets_a_colorer(client):
    pid = _origine(client)
    res = client.post(f"/api/db/scripts/{pid}/variants", json={
        "variant_title": "Extension 2029", "delta": {
            "set": {"params[M_PDI_BAR]": 0.30, "constats[OBS].end_date": "2029-06-14"}}})

    ecarts = {e["chemin"]: e for e in res.json()["ecarts"]}
    assert ecarts["params[M_PDI_BAR]"]["avant"] == 0.50
    assert ecarts["constats[OBS].end_date"]["apres"] == "2029-06-14"


def test_modifier_une_variante_ne_touche_pas_l_origine(client):
    pid = _origine(client)
    vid = client.post(f"/api/db/scripts/{pid}/variants",
                      json={"variant_title": "Capital",
                            "delta": {"set": {"params[M_PDI_BAR]": 0.30}}}).json()["id"]

    client.put(f"/api/db/scripts/variants/{vid}",
               json={"variant_title": "Capital — PDI 25 %",
                     "delta": {"set": {"params[M_PDI_BAR]": 0.25}}})

    v = client.get(f"/api/db/scripts/variants/{vid}/resolved").json()
    assert v["variant_title"] == "Capital — PDI 25 %"
    assert v["contexte"]["params"]["M_PDI_BAR"] == 0.25
    origine = client.get(f"/api/db/scripts/{pid}").json()
    assert json.loads(origine["params_json"])["M_PDI_BAR"] == 0.50


# ── Le roll par l'API ───────────────────────────────────────────────

def test_une_variante_roll_ressort_deja_recalee(client):
    """Le contexte rendu par l'API est prêt à pricer tel quel.

    L'appelant ne doit pas avoir à savoir quel mode demande quel
    post-traitement : un seul chemin qui l'oublierait pricerait une note neuve
    sur l'axe des temps de l'ancienne, avec un chiffre plausible."""
    pid = _origine(client)
    res = client.post(f"/api/db/scripts/{pid}/variants", json={
        "variant_title": "Roll 3 ans", "variant_mode": MODE_ROLL,
        "delta": {"removed": ["underlyings[STLAM.MI]"]}})
    assert res.status_code == 201, res.text

    g = res.json()["contexte"]["global"]
    assert g["strike_date"] == "2026-05-08", "strikée à la date de valorisation"
    assert g["valuation_date"] == g["strike_date"], "donc pricée à l'émission"
    assert res.json()["contexte"]["constats"]["OBS"]["start_date"] == "2026-05-08"
    # Le panier a bien pu changer, ce que l'avenant refusait.
    assert [u["name"] for u in g["underlyings"]] == ["GLE.PA", "UCG.MI"]


def test_avenant_et_roll_du_meme_delta_ne_donnent_pas_le_meme_produit(client):
    """Ce ne sont pas deux paramétrages, ce sont deux produits — et c'est
    précisément ce que le mode encode."""
    pid = _origine(client)
    delta = {"set": {"params[M_PDI_BAR]": 0.30}}
    a = client.post(f"/api/db/scripts/{pid}/variants", json={
        "variant_title": "Avenant", "variant_mode": MODE_AVENANT, "delta": delta}).json()
    r = client.post(f"/api/db/scripts/{pid}/variants", json={
        "variant_title": "Roll", "variant_mode": MODE_ROLL, "delta": delta}).json()

    assert a["contexte"]["global"]["strike_date"] == "2024-06-14"
    assert r["contexte"]["global"]["strike_date"] == "2026-05-08"
    # Le même écart de barrière dans les deux, malgré tout.
    assert a["contexte"]["params"]["M_PDI_BAR"] == r["contexte"]["params"]["M_PDI_BAR"] == 0.30


# ── Le contrat dont l'écran dépend ──────────────────────────────────
#
# La barre de déclinaison et la liste des scripts lisent ces clés précises.
# Les renommer côté serveur casserait l'affichage sans qu'aucun test de
# pricing ne s'en aperçoive : un onglet sans titre, une puce de mode vide, ou
# des champs qui cessent d'être colorés — c'est-à-dire une variante qui a
# l'air de son origine.

def test_la_liste_des_variantes_porte_ce_que_l_ecran_affiche(client):
    pid = _origine(client)
    client.post(f"/api/db/scripts/{pid}/variants", json={
        "variant_title": "Capital", "variant_mode": MODE_AVENANT,
        "delta": {"set": {"params[M_PDI_BAR]": 0.30}}})

    v = client.get(f"/api/db/scripts/{pid}/variants").json()[0]
    assert {"id", "parent_id", "name", "variant_title", "variant_mode",
            "delta", "ecarts", "contexte", "updated_at"} <= set(v)
    assert v["variant_title"] and v["variant_mode"]
    ecart = v["ecarts"][0]
    assert {"chemin", "etat", "avant", "apres"} == set(ecart)
    assert ecart["etat"] in ("modifie", "retire")


def test_le_contexte_rendu_a_la_forme_que_le_pricer_recharge(client):
    """`loadVariant` le réinjecte tel quel dans les quatre blobs du store."""
    pid = _origine(client)
    v = client.post(f"/api/db/scripts/{pid}/variants",
                    json={"variant_title": "T", "delta": {}}).json()
    assert {"script_text", "params", "constats", "global"} == set(v["contexte"])


def test_la_liste_des_scripts_porte_le_compte_de_variantes(client):
    """C'est lui qui rend une origine à déclinaisons distinguable avant d'être
    ouverte."""
    pid = _origine(client)
    assert client.get("/api/db/scripts").json()[0]["variant_count"] == 0
    client.post(f"/api/db/scripts/{pid}/variants",
                json={"variant_title": "T", "delta": {}})
    assert client.get("/api/db/scripts").json()[0]["variant_count"] == 1


# ── Supprimer ───────────────────────────────────────────────────────

def test_une_declinaison_se_supprime_seule(client):
    """Elle ne stocke que ses écarts : ni son origine ni ses sœurs n'en
    dépendent. C'est ce qui permet de la supprimer sans cérémonie."""
    pid = _origine(client)
    a = client.post(f"/api/db/scripts/{pid}/variants",
                    json={"variant_title": "A", "delta": {}}).json()["id"]
    b = client.post(f"/api/db/scripts/{pid}/variants",
                    json={"variant_title": "B", "delta": {}}).json()["id"]

    assert client.delete(f"/api/db/scripts/{a}").status_code == 204

    restantes = client.get(f"/api/db/scripts/{pid}/variants").json()
    assert [v["id"] for v in restantes] == [b]
    assert client.get(f"/api/db/scripts/{pid}").status_code == 200
    assert client.get("/api/db/scripts").json()[0]["variant_count"] == 1


def test_supprimer_une_origine_a_declinaisons_est_refuse(client):
    """Les supprimer en silence détruirait un travail réel ; les laisser
    derrière en ferait des fantômes sans contexte à hériter, donc sans prix."""
    pid = _origine(client)
    client.post(f"/api/db/scripts/{pid}/variants",
                json={"variant_title": "Capital — PDI 30 %", "delta": {}})

    res = client.delete(f"/api/db/scripts/{pid}")
    assert res.status_code == 409
    detail = res.json()["detail"]
    # Le refus NOMME ce qui bloque : un message générique ferait confirmer à
    # l'aveugle.
    assert "Capital — PDI 30 %" in detail
    assert client.get(f"/api/db/scripts/{pid}").status_code == 200


def test_la_cascade_explicite_emporte_les_declinaisons(client):
    pid = _origine(client)
    ids = [client.post(f"/api/db/scripts/{pid}/variants",
                       json={"variant_title": t, "delta": {}}).json()["id"]
           for t in ("A", "B", "C")]

    assert client.delete(f"/api/db/scripts/{pid}?cascade=true").status_code == 204
    assert client.get(f"/api/db/scripts/{pid}").status_code == 404
    for vid in ids:
        assert client.get(f"/api/db/scripts/variants/{vid}/resolved").status_code == 404
    assert client.get("/api/db/scripts?include_variants=true").json() == []


def test_une_origine_sans_declinaison_se_supprime_comme_avant(client):
    """La garantie de non-régression : le garde-fou ne doit gêner personne."""
    pid = _origine(client)
    assert client.delete(f"/api/db/scripts/{pid}").status_code == 204
    assert client.get("/api/db/scripts").json() == []


# ── Ce qu'un avenant ne peut pas déplacer ───────────────────────────

@pytest.mark.parametrize("cle", ["strike_date", "value_date", "valuation_date", "trade_date"])
def test_un_avenant_ne_deplace_pas_les_dates_du_passe(cle):
    """Régression (audit C2).

    Déplacer la date de strike d'un avenant déplace l'ORIGINE de l'axe des
    temps : le passé n'est plus rejoué au bon endroit. Le prix reste plausible,
    la table de flux reste cohérente avec lui, et rien ne dit que le produit
    valorisé n'est plus celui qui a été émis.

    La chaîne était entièrement franchissable — le delta capturait la date,
    l'écran l'envoyait comme strike du deal, et le rejeu la suivait."""
    with pytest.raises(VariantError) as e:
        resoudre(PARENT, {"set": {f"global.{cle}": "2025-01-01"}}, MODE_AVENANT)
    assert cle in str(e.value) and "roll" in str(e.value)


def test_un_avenant_peut_amender_le_reglement_final():
    """Le pendant : ce qui ne porte pas le passé reste amendable. Un avenant qui
    ne pourrait plus rien changer ne servirait à rien."""
    ctx = resoudre(PARENT, {"set": {"global.payment_date": "2027-07-01"}}, MODE_AVENANT)
    assert ctx["global"]["payment_date"] == "2027-07-01"


def test_une_note_neuve_deplace_librement_ses_dates():
    """Elle n'a pas de passé : c'est tout l'intérêt du mode."""
    ctx = resoudre(PARENT, {"set": {"global.strike_date": "2026-05-08"}}, MODE_ROLL)
    assert ctx["global"]["strike_date"] == "2026-05-08"


def test_l_api_refuse_une_declinaison_qui_deplace_le_strike(client):
    pid = _origine(client)
    res = client.post(f"/api/db/scripts/{pid}/variants", json={
        "variant_title": "Strike déplacé", "variant_mode": MODE_AVENANT,
        "delta": {"set": {"global.strike_date": "2025-01-01"}}})
    assert res.status_code == 422
    assert "roll" in res.json()["detail"]


# ── Visibilité : une variante n'expose pas une origine privée ───────

def _autre_utilisateur(nom="autre", entity_id=1):
    import backend.app.db.database as db
    from backend.app.db.models import User
    from sqlmodel import Session
    with Session(db.engine) as s:
        u = User(username=nom, email=f"{nom}@test.local",
                 password_hash="x", entity_id=entity_id)
        s.add(u); s.commit(); s.refresh(u)
        return u.id


def test_une_variante_n_expose_pas_une_origine_devenue_privee(client):
    """Régression (audit C4).

    Le partage s'hérite à la CRÉATION et ne se révise jamais. Une origine
    partagée, une variante créée, puis l'origine repassée en privé : la variante
    restait lisible et rendait `contexte_parent` — le script complet de son
    origine — à quelqu'un qui n'y avait plus droit."""
    import backend.app.db.database as db
    from backend.app.api.auth import get_current_user
    from backend.app.db.models import Script, User
    from backend.app.main import app
    from sqlmodel import Session

    pid = _origine(client)
    client.put(f"/api/db/scripts/{pid}", json={"is_shared": True})
    vid = client.post(f"/api/db/scripts/{pid}/variants",
                      json={"variant_title": "Partagée", "delta": {}}).json()["id"]
    with Session(db.engine) as s:
        v = s.get(Script, vid); v.is_shared = True; s.add(v)
        p = s.get(Script, pid); p.is_shared = False; s.add(p)
        s.commit()

    uid = _autre_utilisateur()
    app.dependency_overrides[get_current_user] = (
        lambda: Session(db.engine).get(User, uid))
    try:
        assert client.get(f"/api/db/scripts/variants/{vid}/resolved").status_code == 403
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_la_liste_ne_rend_pas_les_brouillons_des_autres(client):
    """Sur une origine partagée, une proposition à demi rédigée n'a rien à faire
    sous les yeux d'un collègue."""
    import backend.app.db.database as db
    from backend.app.db.models import Script
    from sqlmodel import Session

    pid = _origine(client)
    client.put(f"/api/db/scripts/{pid}", json={"is_shared": True})
    mienne = client.post(f"/api/db/scripts/{pid}/variants",
                         json={"variant_title": "La mienne", "delta": {}}).json()["id"]
    autre = client.post(f"/api/db/scripts/{pid}/variants",
                        json={"variant_title": "Brouillon d'un autre", "delta": {}}).json()["id"]
    uid = _autre_utilisateur("collegue")
    with Session(db.engine) as s:
        v = s.get(Script, autre); v.user_id = uid; v.is_shared = False; s.add(v); s.commit()

    titres = [v["variant_title"] for v in client.get(f"/api/db/scripts/{pid}/variants").json()]
    assert titres == ["La mienne"]


def test_la_cascade_n_emporte_pas_les_declinaisons_d_autrui(client):
    """Régression : ranger son dossier détruisait les propositions client des
    collègues, après une confirmation qui ne nommait que des titres."""
    import backend.app.db.database as db
    from backend.app.db.models import Script
    from sqlmodel import Session

    pid = _origine(client)
    client.put(f"/api/db/scripts/{pid}", json={"is_shared": True})
    autre = client.post(f"/api/db/scripts/{pid}/variants",
                        json={"variant_title": "La sienne", "delta": {}}).json()["id"]
    uid = _autre_utilisateur("collegue2")
    with Session(db.engine) as s:
        v = s.get(Script, autre); v.user_id = uid; s.add(v); s.commit()

    # Le refus nomme le propriétaire, plutôt que d'annoncer un titre anonyme.
    res = client.delete(f"/api/db/scripts/{pid}")
    assert res.status_code == 409 and "collegue2" in res.json()["detail"]
    # Et la cascade elle-même refuse plutôt que de détruire sans prévenir l'auteur.
    forcee = client.delete(f"/api/db/scripts/{pid}?cascade=true")
    assert forcee.status_code == 409
    with Session(db.engine) as s:
        assert s.get(Script, autre) is not None


# ── Une déclinaison ne stocke que ses écarts ────────────────────────

@pytest.mark.parametrize("champ, valeur", [
    ("script_text", "AT 1:\n  PAY 1\n"),
    ("params_json", '{"X": 1}'),
    ("constats_json", '{"OBS": {}}'),
    ("global_params_json", '{"r": 9.0}'),
])
def test_le_put_generique_refuse_d_ecrire_un_contexte_de_variante(client, champ, valeur):
    """Régression (audit C5).

    Les blobs d'une déclinaison ne sont jamais relus — sa vue résout toujours
    depuis l'origine. Y écrire ne produisait donc pas un prix faux, mais de la
    donnée morte et un utilisateur convaincu d'avoir enregistré quelque chose."""
    pid = _origine(client)
    vid = client.post(f"/api/db/scripts/{pid}/variants",
                      json={"variant_title": "T", "delta": {}}).json()["id"]

    res = client.put(f"/api/db/scripts/{vid}", json={champ: valeur})
    assert res.status_code == 422
    assert champ in res.json()["detail"]


@pytest.mark.parametrize("corps", [
    {"name": "Renommée"},
    {"is_shared": True},
    {"tags": "client-a"},
])
def test_la_fiche_d_une_variante_reste_modifiable(client, corps):
    """Le pendant : refuser la requête entière casserait le renommage, le
    rangement en dossier et le partage, qui passent par ce même endpoint."""
    pid = _origine(client)
    vid = client.post(f"/api/db/scripts/{pid}/variants",
                      json={"variant_title": "T", "delta": {}}).json()["id"]
    assert client.put(f"/api/db/scripts/{vid}", json=corps).status_code == 200


def test_une_origine_garde_le_droit_d_ecrire_son_contexte(client):
    """Non-régression : le garde-fou ne vise que les déclinaisons."""
    pid = _origine(client)
    res = client.put(f"/api/db/scripts/{pid}", json={"script_text": "AT 1:\n  PAY 1\n"})
    assert res.status_code == 200
