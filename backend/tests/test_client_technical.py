"""La lecture technique — niveaux, protections, familles, exécution.

Ce module a une exigence propre : **il doit dire la même chose d'un deal booké
et d'une ligne importée**. Un deal ne porte pas ses niveaux en colonnes, ils
vivent dans les PARAM de son script ; une ligne importée les porte
explicitement. Sans extraction, l'écran afficherait des coupons pour les
clients dont l'historique a été versé et rien pour ceux dont nous avons booké
les trades — l'incohérence frapperait justement les données dont nous sommes
le plus sûrs.

Le reste tient sur les refus habituels : pas de moyenne sous deux
observations, pas de nature devinée pour un sous-jacent inconnu, et « traité
ailleurs » jamais présumé d'une case vide.
"""
from datetime import date

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from backend.app.core.client_intelligence import (
    deals_of_client, technical_view,
)
from backend.app.core.client_technical import (
    catalogue_natures, decouper_sous_jacents, famille_de_panier,
    libelle_famille,
    moyennes_par_famille, nature_du_sous_jacent, niveaux_du_script,
    repartition_execution,
)
from backend.app.db.models import (
    Client, ClientTradeHistory, Deal, Underlying,
)


def _session() -> Session:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    session = Session(engine)
    # Le catalogue, réduit à ce qui sert ici.
    session.add_all([
        Underlying(ticker="^STOXX50E", label="Euro Stoxx 50",
                   group_name="Indices Europe", ccy="EUR"),
        Underlying(ticker="^GSPC", label="S&P 500", group_name="Indices US",
                   ccy="USD"),
        Underlying(ticker="GLE.PA", label="Société Générale",
                   group_name="Banques", ccy="EUR"),
        Underlying(ticker="MC.PA", label="LVMH", group_name="Luxe", ccy="EUR"),
        Underlying(ticker="GLD", label="Or", group_name="ETF / Matières premières",
                   ccy="USD"),
    ])
    session.commit()
    return session


# Un VRAI script, repris de test_parser.py. La convention M_ n'y est pas
# seulement déclarée, elle est utilisée dans les événements — c'est la
# condition pour que le parseur en déduise une direction.
#
# Une première version de ce fichier inventait la syntaxe. Le script ne
# compilait pas, le module rendait « rien » — comportement correct — et le test
# semblait accuser le code. Un script de test doit passer le parseur du projet,
# sinon il ne teste que sa propre invention.
SCRIPT_M = """
PARAM COUPON = 8%
PARAM() M_AC_BAR = 105%
PARAM M_KI_BAR = 60%

AT 1, 2, 3:
  SET CALL = INDIC(WOF >= M_AC_BAR)
  PAY CALL * COUPON * INDEX
  PAY CALL * 1
  IF CALL = 1:
    STOP

AT MATURITY:
  SET KI = INDIC(WOF < M_KI_BAR)
  PAY (1 - KI) * 1
  PAY KI * WOF
"""

# Sans préfixe M_ : le cas hérité, que la watchlist traite par heuristique de
# nom et que ce module doit traiter exactement pareil.
SCRIPT_HERITE = """
PARAM COUPON = 6.5%
PARAM AC_BAR = 100%
PARAM KI_BAR = 50%

AT MATURITY:
  SET KI = INDIC(WOF < KI_BAR)
  PAY (1 - KI) * 1
  PAY KI * WOF
"""


# ── Les niveaux d'un deal booké ──────────────────────────────────────

def test_le_coupon_et_la_protection_se_lisent_dans_le_script():
    """Sans cette extraction, l'écran technique serait vide pour toutes les
    transactions que nous avons bookées nous-mêmes."""
    niveaux = niveaux_du_script(SCRIPT_M)
    assert niveaux["coupon_pct"] == 8.0
    assert niveaux["protection_pct"] == 60.0
    genres = {b["kind"] for b in niveaux["barriers"]}
    assert genres == {"autocall", "ki"}


def test_un_script_herite_sans_moniteurs_passe_par_l_heuristique():
    """Les scripts sans contrat M_ existent — la watchlist les traite déjà par
    heuristique de nom. On réutilise la sienne pour que les deux écrans ne se
    contredisent jamais sur un même deal."""
    niveaux = niveaux_du_script(SCRIPT_HERITE)
    assert niveaux["coupon_pct"] == 6.5
    assert niveaux["protection_pct"] == 50.0


def test_un_script_illisible_ne_fait_pas_tomber_la_fiche():
    niveaux = niveaux_du_script("ceci n'est pas du PayScript {{{")
    assert niveaux == {"coupon_pct": None, "barriers": [], "protection_pct": None}


def test_un_script_absent_rend_des_niveaux_vides_et_non_zero():
    """Un coupon inconnu et un coupon nul ne se ressemblent que pour qui ne
    lit pas."""
    for script in (None, ""):
        assert niveaux_du_script(script)["coupon_pct"] is None


def test_un_param_a_zero_n_est_pas_un_coupon():
    niveaux = niveaux_du_script("PARAM COUPON = 0%\nAT MATURITY:\n  PAY 1\n")
    assert niveaux["coupon_pct"] is None


# ── Deal booké et ligne importée disent la même chose ────────────────

def test_un_deal_et_une_ligne_importee_rendent_les_memes_champs():
    """L'exigence centrale du module."""
    session = _session()
    client = Client(name="Test", entity_id=1)
    session.add(client); session.commit(); session.refresh(client)

    import json
    session.add(Deal(
        reference="D-1", user_id=1, entity_id=1, client_id=client.id,
        trade_date="2024-01-15", strike_date="2024-01-15",
        maturity_date="2027-01-15", nominal=1e6, devise="EUR",
        product_type="Autocall Athena", contrepartie="BNP Paribas",
        price_traded=98.5, status="actif", script_snapshot=SCRIPT_M,
        underlyings_json=json.dumps([{"ticker": "^STOXX50E"}])))
    session.add(ClientTradeHistory(
        entity_id=1, client_id=client.id, trade_date="2024-06-15",
        maturity_date="2027-06-15", product_type="Phoenix Memory",
        underlying="GLE.PA", issuer="UBS", currency="EUR", notional=1e6,
        coupon_pct=7.2, barrier_pct=55.0, price_pct=99.1,
        traded_with_us=False, external_ref="XS-1"))
    session.commit()

    vue = technical_view(session, deals_of_client(session, client.id))
    par_ref = {l["reference"]: l for l in vue["rows"]}

    booke = par_ref["D-1"]
    assert booke["coupon_pct"] == 8.0        # lu dans le script
    assert booke["protection_pct"] == 60.0
    assert booke["traded_with_us"] is True
    assert booke["price_pct"] == 98.5

    importe = par_ref["XS-1"]
    assert importe["coupon_pct"] == 7.2      # porté en colonne
    assert importe["protection_pct"] == 55.0
    assert importe["traded_with_us"] is False
    assert importe["price_pct"] == 99.1

    # Aucun des deux n'a de champ manquant que l'autre porterait.
    assert set(booke) == set(importe)
    assert vue["coverage"]["with_coupon"] == 2
    assert vue["coverage"]["with_protection"] == 2


# ── Familles de sous-jacents ─────────────────────────────────────────

def test_la_nature_vient_du_catalogue():
    session = _session()
    natures = catalogue_natures(session)
    assert nature_du_sous_jacent("^STOXX50E", natures) == "indice"
    assert nature_du_sous_jacent("GLE.PA", natures) == "action"
    assert nature_du_sous_jacent("MC.PA", natures) == "action"
    assert nature_du_sous_jacent("GLD", natures) == "etf"


def test_le_prefixe_yahoo_sert_de_repli():
    """Un indice absent du catalogue reste reconnaissable : « ^ » est la
    convention Yahoo, indépendante de notre référentiel."""
    assert nature_du_sous_jacent("^N100", {}) == "indice"


def test_un_ticker_inconnu_ne_se_devine_pas():
    """Deviner qu'un ticker inconnu est une action produirait une moyenne
    fausse sans le dire."""
    assert nature_du_sous_jacent("XYZ.ZZ", {}) is None


def test_mono_et_multi_se_distinguent_par_le_compte():
    session = _session()
    natures = catalogue_natures(session)
    assert famille_de_panier(["^STOXX50E"], natures) == {
        "structure": "mono", "nature": "indice", "partial": False, "n": 1}
    panier = famille_de_panier(["GLE.PA", "MC.PA"], natures)
    assert panier["structure"] == "multi" and panier["nature"] == "action"


def test_un_panier_melange_est_dit_mixte():
    session = _session()
    natures = catalogue_natures(session)
    panier = famille_de_panier(["^STOXX50E", "GLE.PA"], natures)
    assert panier["nature"] == "mixte"


def test_un_panier_partiellement_connu_est_signale():
    session = _session()
    natures = catalogue_natures(session)
    panier = famille_de_panier(["^STOXX50E", "INCONNU.XX"], natures)
    assert panier["nature"] == "indice"
    assert panier["partial"] is True, (
        "une moyenne calculée sur une base incomplète doit pouvoir se signaler")


def test_les_libelles_sont_lisibles():
    assert libelle_famille("mono", "indice") == "Mono-indice"
    assert libelle_famille("multi", "action") == "Panier d'actions"
    assert "inconnue" in libelle_famille("mono", None)
    assert libelle_famille(None, None) == "Sans sous-jacent renseigné"


# ── Moyennes par famille ─────────────────────────────────────────────

def _ligne(structure, nature, coupon=None, protection=None, partial=False,
           produit="Autocall Athena"):
    return {"structure": structure, "nature": nature, "coupon_pct": coupon,
            "protection_pct": protection, "partial": partial,
            "product_type": produit}


def test_les_moyennes_se_font_par_famille():
    lignes = [
        _ligne("mono", "indice", 6.0, 60.0),
        _ligne("mono", "indice", 8.0, 60.0),
        _ligne("mono", "indice", 7.0, 50.0),
        _ligne("multi", "action", 14.0, 50.0),
        _ligne("multi", "action", 16.0, 50.0),
    ]
    groupes = {g["label"]: g for g in moyennes_par_famille(lignes)}
    assert groupes["Mono-indice"]["median_coupon_pct"] == 7.0
    assert groupes["Panier d'actions"]["median_coupon_pct"] == 15.0
    # L'ordre suit le volume : la famille la plus traitée en tête.
    assert moyennes_par_famille(lignes)[0]["label"] == "Mono-indice"


def test_une_seule_observation_ne_fait_pas_une_moyenne():
    """Le coupon d'une transaction unique n'est pas une moyenne, c'est ce
    coupon-là. Le présenter comme une tendance ferait croire à une régularité
    qui n'existe pas."""
    groupes = moyennes_par_famille([_ligne("mono", "indice", 9.0, 60.0)])
    assert groupes[0]["median_coupon_pct"] is None
    # Mais le fait brut reste rendu — le vide serait pire.
    assert groupes[0]["single_coupon_pct"] == 9.0
    assert groupes[0]["n_coupons"] == 1


def test_une_famille_sans_coupon_connu_rend_null():
    groupes = moyennes_par_famille([_ligne("mono", "indice"),
                                    _ligne("mono", "indice")])
    assert groupes[0]["median_coupon_pct"] is None
    assert groupes[0]["single_coupon_pct"] is None
    assert groupes[0]["n_trades"] == 2


# ── Avec nous, ailleurs, ou inconnu ──────────────────────────────────

def test_les_trois_etats_d_execution_restent_distincts():
    """Fondre « inconnu » dans « ailleurs » gonflerait la part de marché qu'on
    croit ne pas avoir."""
    lignes = [
        {"traded_with_us": True, "price_pct": 99.0},
        {"traded_with_us": True, "price_pct": 98.0},
        {"traded_with_us": False, "price_pct": 97.0},
        {"traded_with_us": False, "price_pct": 95.0},
        {"traded_with_us": None, "price_pct": None},
    ]
    execution = repartition_execution(lignes)
    assert execution["with_us"] == 2
    assert execution["elsewhere"] == 2
    assert execution["unknown"] == 1
    assert execution["median_price_elsewhere"] == 96.0
    assert execution["median_price_with_us"] == 98.5


def test_sans_prix_connu_la_mediane_reste_nulle():
    execution = repartition_execution([{"traded_with_us": False, "price_pct": None}])
    assert execution["elsewhere"] == 1
    assert execution["median_price_elsewhere"] is None
    assert execution["n_priced_elsewhere"] == 0


# ── L'import porte les deux nouvelles colonnes ───────────────────────

def test_l_import_lit_traite_avec_nous_et_le_prix():
    import io, json
    from backend.app.core.client_import import analyser, appliquer

    session = _session()
    charge = {
        "clients": [{"name": "Neuchâtel"}],
        "transactions": [
            {"client_name": "Neuchâtel", "trade_date": "2024-01-15",
             "product_type": "Autocall", "traded_with_us": "oui",
             "price_pct": 99.2, "external_ref": "A1"},
            {"client_name": "Neuchâtel", "trade_date": "2024-04-15",
             "product_type": "Autocall", "traded_with_us": "non",
             "price_pct": 97.5, "external_ref": "A2"},
            {"client_name": "Neuchâtel", "trade_date": "2024-07-15",
             "product_type": "Autocall", "external_ref": "A3"},
        ],
    }
    appliquer(session, json.dumps(charge).encode(), format_="json",
              filename="t.json", entity_id=None, user_id=1)
    session.commit()

    lignes = {l.external_ref: l for l in
              session.exec(select(ClientTradeHistory)).all()}
    assert lignes["A1"].traded_with_us is True
    assert lignes["A1"].price_pct == 99.2
    assert lignes["A2"].traded_with_us is False
    # Case vide = inconnu, JAMAIS « ailleurs ».
    assert lignes["A3"].traded_with_us is None


def test_une_valeur_ni_oui_ni_non_est_refusee_avec_le_bon_conseil():
    import json
    from backend.app.core.client_import import analyser

    session = _session()
    charge = {
        "clients": [{"name": "Neuchâtel"}],
        "transactions": [{"client_name": "Neuchâtel", "trade_date": "2024-01-15",
                          "traded_with_us": "peut-être"}],
    }
    rapport = analyser(session, json.dumps(charge).encode(), format_="json",
                       entity_id=None, user_id=1)
    assert rapport.bloquant is True
    message = " ".join(a.message for a in rapport.anomalies)
    assert "Laissez vide si vous ne savez pas" in message


# ── Découpage d'un panier importé ─────────────────────────────────

def test_un_panier_importe_tient_dans_une_cellule():
    """Sans découpage, TOUTE ligne importée serait mono.

    C'est le défaut qui compte le plus ici : l'historique versé est la source
    principale du module, et les moyennes « panier » se seraient construites
    sur les seuls deals bookés, c'est-à-dire sur la minorité des données.
    """
    assert decouper_sous_jacents("MC.PA / OR.PA / KER.PA") == [
        "MC.PA", "OR.PA", "KER.PA"]
    assert decouper_sous_jacents("LVMH, Kering; Hermès") == [
        "LVMH", "Kering", "Hermès"]
    assert decouper_sous_jacents("^STOXX50E+^GSPC") == ["^STOXX50E", "^GSPC"]


def test_un_ticker_seul_reste_un_ticker():
    """Les séparateurs ne figurent dans aucune convention connue : découper ne
    doit jamais casser un symbole légitime."""
    for ticker in ("^STOXX50E", "BRK-B", "MC.PA", "000300.SS", "STMPA.PA"):
        assert decouper_sous_jacents(ticker) == [ticker]
    assert decouper_sous_jacents(None) == []
    assert decouper_sous_jacents("   ") == []


def test_le_decoupage_atteint_vraiment_la_lecture_d_historique():
    """Le test qui vérifie que le fil est branché, pas seulement qu'il existe.

    `decouper_sous_jacents` peut être parfaite et n'être appelée nulle part :
    c'est exactement le défaut que la maison a déjà rencontré sur les courbes
    de dividende. On exige donc que la FAMILLE change.
    """
    session = _session()
    client = Client(name="Panier SA", entity_id=1)
    session.add(client)
    session.commit()
    session.refresh(client)
    session.add(ClientTradeHistory(
        client_id=client.id, entity_id=1, trade_date="2025-03-01",
        product_type="Phoenix Memory", underlying="MC.PA / OR.PA / KER.PA",
        issuer="BNP Paribas", notional=1_000_000.0, coupon_pct=12.5,
        barrier_pct=55.0))
    session.commit()

    vue = technical_view(session, deals_of_client(session, client.id))
    assert vue["rows"][0]["underlyings"] == ["MC.PA", "OR.PA", "KER.PA"]
    assert vue["rows"][0]["structure"] == "multi"
    assert vue["rows"][0]["family_label"] == "Panier d'actions"


# ── Ce que la médiane ne doit pas laisser passer ────────────────────

def test_la_mediane_ne_laisse_pas_fuir_le_binaire():
    """6,80 et 7,50 donnent 7,1499999999999995 en flottant.

    L'écran remet en forme, mais l'API rend la valeur brute : un export ou un
    test d'égalité hériterait du bruit.
    """
    groupes = moyennes_par_famille([_ligne("mono", "indice", 6.80, 60.0),
                                    _ligne("mono", "indice", 7.50, 60.0)])
    assert groupes[0]["median_coupon_pct"] == 7.15


def test_une_famille_nomme_les_payoffs_qu_elle_melange():
    """Une protection médiane sur un capital garanti (100 %) et un autocall
    (60 %) donne 80 % — exact et vide de sens. La famille est celle du
    SOUS-JACENT, pas celle du payoff ; l'écran doit pouvoir le montrer."""
    groupes = moyennes_par_famille([
        _ligne("mono", "indice", None, 100.0, produit="Capital garanti"),
        _ligne("mono", "indice", 7.20, 60.0, produit="Autocall Athena"),
    ])
    assert groupes[0]["median_protection_pct"] == 80.0
    assert groupes[0]["product_types"] == ["Autocall Athena", "Capital garanti"]
