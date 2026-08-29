"""Variantes d'un deal en cours de vie — étape 1 : le découplage rejeu/pricing.

Une variante d'avenant ne réécrit pas le passé. Le passé s'est produit sous les
termes d'origine ; seule la vie restante prend les termes nouveaux. Tout ce
fichier tourne autour de la conséquence de cette phrase.

Le piège, tel qu'il se présente sur le Phoenix Mémoire Marex : le worst-of est
aujourd'hui à 34 % du strike, mais il est resté au-dessus de 50 % pendant dix-
huit des vingt-trois constatations écoulées. Une variante qui abaisse le seuil
de rappel à 50 % — l'une des restructurations les plus naturelles à proposer —
rappellerait donc dans le PASSÉ si le rejeu l'utilisait. Le moteur rendrait le
prix d'une note déjà remboursée, sans rien signaler. C'est exactement la classe
d'erreur que les conventions de pricing du projet visent : un prix faux qui ne
se dénonce pas.

Le découplage rend cette erreur impossible par construction plutôt que par
contrôle — le passé n'est jamais rejoué avec la variante. Ces tests le
vérifient sur un historique fabriqué : le titre tient 80 % du strike pendant
deux ans, puis décroche à 34 %.
"""
from datetime import date, timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.app.api import inlife as api
from backend.app.core.inlife_valuation import VariantTerms
from backend.app.core.schemas import UnderlyingParams

USER = SimpleNamespace(id=1, entity_id=1)

STRIKE = date(2024, 6, 14)
MATURITE = date(2027, 6, 14)
VALORISATION = date(2026, 6, 14)

# Le squelette du Marex : mémoire, rappel à partir de la 3ᵉ constatation,
# protection à 50 % à l'échéance.
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

# La même chose avec le seuil de rappel à 50 % — la restructuration « rendre
# le rappel atteignable ». C'est CE script qui rappellerait dans le passé.
PHOENIX_AC50 = PHOENIX.replace("PARAM M_AC_BAR = 100%", "PARAM M_AC_BAR = 50%")

# Et celle qui abandonne le coupon : plus de mémoire du tout, la valeur
# récupérée servant ailleurs. C'est le levier n°1 d'une restructuration.
PHOENIX_SANS_COUPON = """PARAM M_AC_BAR = 100%
PARAM M_KI_BAR = 50%

CONSTAT() OBS

AT OBS:
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


def _historique_en_deux_temps():
    """100 au strike, 80 pendant deux ans, puis 34 — cours NUS, jours ouvrés.

    Les six premières constatations tombent à 80 % du strike, donc bien au-
    dessus d'un seuil de rappel à 50 %. Les deux dernières sont à 34 %. C'est
    la forme du dossier Marex, en plus net."""
    dates, serie = [], []
    jour = STRIKE - timedelta(days=7)
    fin = VALORISATION
    while jour <= fin:
        if jour.weekday() < 5:
            dates.append(jour.isoformat())
            if jour <= STRIKE:
                serie.append(100.0)
            elif jour < date(2026, 1, 15):
                serie.append(80.0)
            else:
                serie.append(34.0)
        jour += timedelta(days=1)
    return {"dates": dates, "prices": {"UL.PA": serie}}


@pytest.fixture
def marche(monkeypatch):
    monkeypatch.setattr(api, "load_hist_prices",
                        lambda tickers, debut, fin: _historique_en_deux_temps())


def _requete(**over):
    base = dict(
        script=PHOENIX,
        underlyings=[UnderlyingParams(name="U1", ticker="UL.PA", ccy="EUR",
                                      sigma=0.50, q=0.0)],
        corr_matrix=[[1.0]],
        r=0.025, N=2000, model="constant", constats=CALENDRIER,
        strike_date=STRIKE, value_date=date(2024, 6, 18),
        maturity_date=MATURITE, payment_date=date(2027, 6, 23),
        valuation_date=VALORISATION, settlement_ccy="EUR",
    )
    base.update(over)
    return api.InLifePricingRequest(**base)


# ── Le piège, et sa désactivation ───────────────────────────────────

def test_le_passe_ne_rappelle_pas_sous_le_seuil_de_la_variante(marche):
    """LE test de l'étape 1.

    Le titre est resté à 80 % du strike pendant six constatations, dont quatre
    éligibles au rappel (`INDEX >= 3`). Une variante à 50 % rappellerait donc
    largement dans le passé si le rejeu l'employait — et le moteur rendrait le
    prix d'une note remboursée depuis mars 2025.

    Le contrat est double : aucun rappel anticipé, et les huit constatations
    écoulées sont toutes là. Un rappel les aurait tronquées."""
    ctx = api.build_request_residual(
        _requete(), variant=VariantTerms(script=PHOENIX_AC50))

    assert ctx.residuel.early_recall is False
    assert ctx.residuel.state["index"] == 8


def test_le_meme_seuil_au_rejeu_aurait_bien_rappele(marche):
    """Le contrôle négatif, sans lequel le test précédent ne prouve rien.

    Si l'on donne le script à 50 % au REJEU — ce que faisait le code avant le
    découplage — le rappel anticipé se déclenche. C'est la preuve que le
    scénario est bien piégeux et que le test d'à côté ne passe pas par
    accident."""
    res = api.price_in_life(_requete(script=PHOENIX_AC50), USER)
    assert res["early_recall"] is True
    assert "rappel anticipé" in res["message"]


def test_la_variante_price_bien_la_vie_restante_a_son_seuil(marche):
    """Le pendant du précédent : le seuil de la variante doit AGIR sur l'avenir.

    Un découplage qui protégerait le passé mais oublierait d'appliquer les
    nouveaux termes au reliquat serait pire que rien — il rendrait le prix
    d'origine sous une étiquette de variante. On exige donc que le prix BOUGE :
    un rappel atteignable vaut plus cher qu'un rappel hors d'atteinte."""
    origine = api.build_request_residual(_requete())
    variante = api.build_request_residual(
        _requete(), variant=VariantTerms(script=PHOENIX_AC50))

    prix_origine = _prix(origine)
    prix_variante = _prix(variante)
    assert prix_variante > prix_origine * 1.02, (prix_origine, prix_variante)


def _prix(ctx):
    """Le prix de la jambe résiduelle, dans les termes portés par le contexte."""
    from backend.app.core.payscript.engine import run_mc
    res = run_mc(ctx.script, ctx.underlyings, [[1.0]], ctx.r, ctx.T_remaining,
                 N=4000, model="constant", seed=42,
                 user_params=ctx.user_params, **ctx.mc_kwargs)
    return res["price"]


# ── Le cas sans variante ne bouge pas d'un iota ─────────────────────

@pytest.mark.parametrize("variante", [None, VariantTerms()])
def test_sans_variante_le_comportement_est_celui_d_avant(marche, variante):
    """La garantie de non-régression : introduire la notion de variante ne
    doit changer le prix d'AUCUNE valorisation ordinaire. Un objet vide vaut
    exactement l'absence d'objet."""
    reference = api.build_request_residual(_requete())
    essai = api.build_request_residual(_requete(), variant=variante)

    assert essai.residuel.state == reference.residuel.state
    assert essai.user_params == reference.residuel.user_params
    assert essai.variant_state_check == {}
    assert _prix(essai) == pytest.approx(_prix(reference), rel=1e-12)


# ── Ce qui doit être refusé ─────────────────────────────────────────

def test_changer_la_frequence_passee_est_refuse(marche):
    """Les constatations écoulées ne s'aligneraient plus, et `INDEX` — que la
    variante hérite du rejeu — désignerait une autre observation que celle
    qu'il compte. Un recalage silencieux donnerait un prix plausible pour un
    produit qui n'existe pas."""
    semestriel = {"OBS": {**CALENDRIER["OBS"], "frequency": "6M"}}
    with pytest.raises(HTTPException) as exc:
        api.build_request_residual(_requete(), variant=VariantTerms(constats=semestriel))
    detail = str(exc.value.detail)
    assert "calendrier passé" in detail and "nouvelle note" in detail


def test_prolonger_la_maturite_est_permis(marche):
    """Le cas symétrique : les dates passées restent un préfixe du nouveau
    calendrier, donc rien ne diverge. C'est la restructuration « acheter du
    temps », et elle doit passer."""
    jusqu_en_2029 = {"OBS": {**CALENDRIER["OBS"], "end_date": "2029-06-14"}}
    ctx = api.build_request_residual(_requete(), variant=VariantTerms(constats=jusqu_en_2029))

    assert ctx.residuel.early_recall is False
    assert ctx.residuel.state["index"] == 8
    # Le reliquat porte bien les constatations supplémentaires.
    futures = sum(len(e.dates or []) for e in ctx.script.events)
    origine = api.build_request_residual(_requete())
    assert futures > sum(len(e.dates or []) for e in origine.script.events)


# ── Ce qui doit être rapporté, pas refusé ───────────────────────────

def test_une_memoire_abandonnee_est_signalee_et_non_refusee(marche):
    """Abandonner la mémoire accumulée est une restructuration légitime — c'est
    même le levier principal quand on monétise le coupon. Impossible de
    distinguer ici l'intention de l'étourderie d'un renommage : on ne refuse
    pas, on RAPPORTE, et l'écran le montrera à côté du prix."""
    ctx = api.build_request_residual(
        _requete(), variant=VariantTerms(script=PHOENIX_SANS_COUPON))

    check = ctx.variant_state_check
    assert check["DUE"]["lu_par_la_variante"] is False
    assert check["DUE"]["valeur"] > 0, "le rejeu doit avoir accumulé quelque chose"
    assert check["CPN"]["lu_par_la_variante"] is False
    # Et les variables que la variante conserve sont signalées comme telles.
    assert check["CALL"]["lu_par_la_variante"] is True


def test_une_variante_qui_garde_ses_variables_ne_signale_rien_de_perdu(marche):
    ctx = api.build_request_residual(
        _requete(), variant=VariantTerms(script=PHOENIX_AC50))
    assert all(v["lu_par_la_variante"] for v in ctx.variant_state_check.values())


# ── Les PARAM de la variante ────────────────────────────────────────

def test_les_param_de_la_variante_pricent_le_reliquat_sans_toucher_au_passe(marche):
    """La voie la plus fréquente : la variante ne change qu'un PARAM, pas le
    texte du script. Le rejeu doit rester aux PARAM d'origine — sinon la
    mémoire accumulée serait recalculée au nouveau coupon, ce qui inventerait
    un passé."""
    ctx = api.build_request_residual(
        _requete(), variant=VariantTerms(user_params={"M_AC_BAR": 0.50}))

    assert ctx.residuel.early_recall is False
    assert ctx.user_params == {"M_AC_BAR": 0.50}
    # Le rejeu, lui, a bien tourné aux paramètres de la requête.
    assert ctx.residuel.user_params == {}


# ── Le fil débranché trouvé en construisant ce chantier ─────────────

@pytest.mark.parametrize("param, valeur", [
    ("COUPON", 0.10),      # 2 % → 10 %
    ("M_AC_BAR", 0.50),    # rappel hors d'atteinte → atteignable
    ("M_KI_BAR", 0.01),    # protection quasi certaine
])
def test_un_param_saisi_atteint_le_moteur_en_cours_de_vie(marche, param, valeur):
    """Régression : le rejeu ré-injectait ses propres PARAM par-dessus l'écran.

    Le moteur range les PARAM dans `ctx["memo"]`, aux côtés des variables du
    script. La mémoire rendue par le rejeu contenait donc les barrières EN
    VIGUEUR PENDANT LE PASSÉ, et elle était réinjectée dans le Monte Carlo
    résiduel *après* la fusion des PARAM : elle les écrasait. Toute valorisation
    en cours de vie priçait aux termes du rejeu, quoi qu'on saisisse — passer le
    coupon de 2 % à 10 % ne déplaçait le prix d'aucun centième, là où la même
    modification vaut +27 points à l'émission.

    Le défaut ne se signalait pas : le prix restait plausible, et il coïncidait
    avec le prix juste chaque fois que la saisie égalait le défaut du script —
    c'est-à-dire dans le cas nominal. On exige donc que le prix BOUGE ; vérifier
    une valeur ne verrait pas ce fil-là débranché.

    C'est aussi la condition d'existence des variantes : une variante dont
    l'objet est de changer un PARAM ne vaudrait rien sans cette correction."""
    ctx = api.build_request_residual(_requete())
    assert _prix(ctx) != pytest.approx(_prix_avec(ctx, {param: valeur}), rel=1e-6)


def test_les_param_ne_survivent_pas_au_rejeu_mais_les_variables_si(marche):
    """La règle qui sous-tend la correction : un terme du contrat se saisit, une
    variable d'état s'hérite. La mémoire reprise ne doit donc porter que les
    secondes."""
    ctx = api.build_request_residual(_requete())
    memoire = ctx.residuel.state["memo"]

    assert {"DUE", "CPN", "CALL"} <= set(memoire)
    assert memoire["DUE"] > 0, "deux constatations sous la barrière, non versées"
    assert not ({"COUPON", "M_AC_BAR", "M_CPN_BAR", "M_KI_BAR"} & set(memoire))


def _prix_avec(ctx, user_params):
    from backend.app.core.payscript.engine import run_mc
    return run_mc(ctx.script, ctx.underlyings, [[1.0]], ctx.r, ctx.T_remaining,
                  N=4000, model="constant", seed=42,
                  user_params=user_params, **ctx.mc_kwargs)["price"]


def test_prolonger_deplace_l_horizon_de_simulation(marche):
    """Régression : la prolongation laissait ses constatations hors du Monte Carlo.

    `T_remaining` se calcule sur la maturité de la REQUÊTE, qui est celle du
    parent. Une variante prolongée gardait donc l'horizon d'origine : ses
    constatations supplémentaires — dont le remboursement final — tombaient
    au-delà et n'étaient jamais versées.

    Le prix restait plausible, ce qui rendait le défaut invisible. Le seul
    signe était que deux variantes de protection DIFFÉRENTES rendaient le même
    prix, le remboursement n'ayant lieu dans aucune des deux. C'est ce que ce
    test exige : que la barrière de protection continue de peser."""
    jusqu_en_2029 = {"OBS": {**CALENDRIER["OBS"], "end_date": "2029-06-14"}}
    origine = api.build_request_residual(_requete())
    longue = api.build_request_residual(
        _requete(), variant=VariantTerms(constats=jusqu_en_2029))

    assert longue.T_remaining > origine.T_remaining + 1.5, (
        "l'horizon doit suivre le calendrier de la variante, pas la maturité du parent")
    # Et le remboursement final a bien lieu : deux protections différentes ne
    # peuvent pas donner le même prix.
    protegee = _prix_avec(longue, {"M_KI_BAR": 0.05})
    exposee = _prix_avec(longue, {"M_KI_BAR": 0.95})
    assert protegee > exposee * 1.05, (protegee, exposee)


# ── Bout en bout : la variante arrive par la requête ────────────────

def test_l_api_price_la_variante_et_pas_le_parent(marche):
    """Le chemin réel : la requête porte les termes d'ORIGINE, et un bloc
    `variant` porte ceux de l'avenant. C'est cette asymétrie qui protège le
    passé — envoyer directement les termes de la variante dans `script`
    rejouerait l'histoire avec elle."""
    origine = api.price_in_life(_requete(), USER)
    avenant = api.price_in_life(
        _requete(variant={"script": PHOENIX_AC50, "mode": "avenant"}), USER)

    assert origine["in_life"] and avenant["in_life"]
    assert avenant["price"] > origine["price"] * 1.02, (origine["price"], avenant["price"])
    # Le passé est le même dans les deux : c'est le même produit jusqu'ici.
    assert avenant["past"]["observations_done"] == origine["past"]["observations_done"]
    assert avenant["past"]["memory"] == origine["past"]["memory"]


def test_l_api_signale_ce_que_la_variante_fait_de_l_etat_repris(marche):
    res = api.price_in_life(
        _requete(variant={"script": PHOENIX_SANS_COUPON, "mode": "avenant"}), USER)
    assert res["variant_state_check"]["DUE"]["lu_par_la_variante"] is False


def test_hors_variante_le_rapport_est_vide(marche):
    assert api.price_in_life(_requete(), USER)["variant_state_check"] == {}


def test_une_note_neuve_ne_se_valorise_pas_en_cours_de_vie(marche):
    """Un roll est striké AUJOURD'HUI : il n'a pas de passé à rejouer. Le
    valoriser par ce chemin donnerait un prix, et c'est bien le problème."""
    with pytest.raises(HTTPException) as exc:
        api.price_in_life(
            _requete(variant={"script": PHOENIX_AC50, "mode": "roll"}), USER)
    assert "roll" in str(exc.value.detail).lower()


def test_les_probabilites_decrivent_la_meme_variante_que_le_prix(marche):
    """Sans ce lien, l'onglet Probabilités décrirait le produit d'origine sous
    un prix d'avenant — exactement l'écart fermé partout ailleurs."""
    from backend.app.api import pricing as api_px
    from backend.app.core.schemas import ProbaRequest

    def _proba(variant=None):
        req = ProbaRequest(
            script=PHOENIX, underlyings=_requete().underlyings, corr_matrix=[[1.0]],
            r=0.025, T=3.0, N=4000, model="constant", seed=42, constats=CALENDRIER,
            settlement_ccy="EUR", strike_date=STRIKE, maturity_date=MATURITE,
            valuation_date=VALORISATION, variant=variant)
        return api_px.proba_endpoint(req)

    origine = _proba()
    avenant = _proba({"script": PHOENIX_AC50, "mode": "avenant"})

    assert origine["in_life"] and avenant["in_life"]
    # Le rappel devient atteignable : sa probabilité doit monter.
    assert avenant["autocall_pct"] > origine["autocall_pct"], (
        origine["autocall_pct"], avenant["autocall_pct"])
