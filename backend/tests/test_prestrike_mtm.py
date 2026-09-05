"""Valoriser un produit booké dont le strike n'est pas encore constaté.

Le MtM résiduel était écrit pour un deal EN VIE : il chargeait l'historique
depuis le strike, rejouait le passé et lisait S₀ dans l'événement de
constatation initiale. Avant le strike ces trois étapes n'ont pas d'objet, et
la première fabriquait une fenêtre de cours commençant après sa propre fin —
le MtM s'arrêtait sur « Aucune donnée historique disponible », entraînant avec
lui les Greeks, les chocs et, silencieusement, la VaR de portefeuille (le
moteur écarte un deal qui ne se reprice pas).

Le régime pré-strike simule la fenêtre qui reste avant la constatation
initiale : chaque trajectoire y fixe SON propre niveau de référence, et le
payoff — écrit en pourcentage du strike — se lit ensuite par rapport à lui.
C'est ce qui porte la dispersion du fixing (donc la convexité sous vol locale),
l'état de variance atteint au strike sous Heston, et le départ de la courbe
d'aujourd'hui. C'est aussi ce qui rend le delta juste sans mécanisme dédié :
bumper le spot met le fixing à l'échelle avec le reste, donc le payoff normalisé
ne bouge pas et il ne subsiste que le smile.
"""
from datetime import date, timedelta

import pytest

from backend.app.core.inlife_valuation import InLifeProduct, build_residual
from backend.app.core.payscript.engine import compute_greeks, run_mc
from backend.app.core.payscript.parser import parse_script, resolve_constats

STRIKE = date(2026, 9, 15)
MATURITE = date(2029, 9, 15)
VALO = date(2026, 9, 3)          # douze jours AVANT le strike

PHOENIX = """PARAM COUPON = 2%
PARAM M_CPN_BAR = 70%
PARAM M_KI_BAR = 60%
PARAM RAPPEL = 100%

CONSTAT() OBS

AT OBS:
  SET DUE = DUE + COUPON
  SET CPN = INDIC(WOF >= M_CPN_BAR)
  PAY CPN * DUE
  SET DUE = (1 - CPN) * DUE
  IF WOF >= RAPPEL:
    PAY 1
    STOP

AT OBS.last:
  SET KI = INDIC(WOF < M_KI_BAR)
  PAY (1 - KI) * 1
  PAY KI * WOF
"""

CALENDRIER = {"OBS": {"start_date": STRIKE.isoformat(),
                      "end_date": MATURITE.isoformat(),
                      "roll_date": "2026-12-15", "frequency": "3M",
                      "stub": "short_last", "convention": "following"}}


def _sous_jacent(skew: float = 0.0) -> dict:
    return {"name": "SX5E", "ticker": "^STOXX50E", "sigma": 0.20, "q": 0.03,
            "skew": skew, "curvature": 0.0,
            "rho_h": -0.7, "v0": 0.04, "kappa": 2.0, "theta_h": 0.04, "xi": 0.5}


def _produit(**over) -> InLifeProduct:
    base = dict(
        script_snapshot=PHOENIX,
        underlyings=[{"name": "SX5E", "ticker": "^STOXX50E", "ccy": "EUR"}],
        strike_levels={},          # rien n'est constaté : c'est tout le sujet
        strike_date=STRIKE, value_date=date(2026, 9, 17),
        tenor=3.0007, currency="EUR", payment_date=date(2029, 9, 21),
        market={"constats": CALENDRIER, "r": 3.0, "model": "constant",
                "underlyings": [_sous_jacent()]},
    )
    base.update(over)
    return InLifeProduct(**base)


def _historique(fin: date, jours: int = 30) -> tuple[dict, list]:
    """Cours nus jusqu'à la date de valorisation — bornés AVANT le strike."""
    dates, serie = [], []
    jour = fin - timedelta(days=jours)
    while jour <= fin:
        if jour.weekday() < 5:
            dates.append(jour.isoformat())
            serie.append(4500.0)
        jour += timedelta(days=1)
    return {"^STOXX50E": serie}, dates


def _compile():
    # Ancré sur le strike, comme build_residual : sans `anchor`, les temps se
    # compteraient depuis aujourd'hui et le calendrier glisserait de l'écart
    # exact que ce module a pour objet de traiter.
    return resolve_constats(parse_script(PHOENIX), CALENDRIER, anchor=STRIKE,
                            currency="EUR")


# ── Le cœur : construire le produit à pricer sans passé ─────────────────

def test_avant_le_strike_les_constatations_reculent_de_l_ecart_au_strike():
    ecart = (VALO - STRIKE).days / 365.25          # négatif
    prices, dates_list = _historique(VALO)
    res = build_residual(_produit(), prices, dates_list, ecart, VALO)

    assert res.pre_strike is True
    # L'axe commence AUJOURD'HUI : chaque constatation est plus loin de l'écart
    # qui nous sépare du strike. La compter depuis le strike ferait diffuser le
    # produit douze jours de trop peu.
    dates_res = sorted(d for e in res.residual_script.events for d in (e.dates or []))
    dates_org = sorted(d for e in _compile().events for d in (e.dates or []))
    assert dates_res == [pytest.approx(d - ecart) for d in dates_org]
    # Et le fixing est attendu à l'écart exact, pas à l'origine.
    assert res.strike_set_t == pytest.approx(-ecart)
    # Les trajectoires partent du spot du jour, pas d'un strike inexistant.
    assert res.norm_spots == [1.0]


def test_avant_le_strike_rien_n_est_realise():
    prices, dates_list = _historique(VALO)
    res = build_residual(_produit(), prices, dates_list,
                         (VALO - STRIKE).days / 365.25, VALO)

    assert res.realized_flows == []
    assert res.state["index"] == 0
    assert res.state["memo"] == {}
    # Neutres et non nuls : un plus-bas réalisé à zéro serait l'inverse de
    # « aucune constatation n'a eu lieu ».
    assert res.state["wof_min"] is None
    assert res.state["s_min"] is None
    assert res.state["realvol_state"] is None


def test_un_stock_absent_ne_bloque_plus_avant_le_strike():
    """L'historique ne sert plus qu'à l'affichage : son absence n'empêche pas
    de valoriser un produit qui n'a rien à rejouer."""
    res = build_residual(_produit(), {}, [],
                         (VALO - STRIKE).days / 365.25, VALO)
    assert res.pre_strike is True
    assert res.norm_spots == [1.0]


def test_apres_le_strike_le_regime_ordinaire_est_intact():
    """Le même produit valorisé APRÈS sa constatation initiale repasse par le
    rejeu — et redemande donc S₀, qu'il exige toujours."""
    from backend.app.core.inlife_valuation import ValuationError
    apres = STRIKE + timedelta(days=40)
    prices, dates_list = _historique(apres, jours=60)
    with pytest.raises(ValuationError, match="S₀ manquant"):
        build_residual(_produit(), prices, dates_list,
                       (apres - STRIKE).days / 365.25, apres)


# ── Le prix : le fixing est diffusé, pas écrasé sur son forward ─────────

def _prix(strike_set_t=None, sigma: float = 0.20, model: str = "constant",
          skew: float = 0.0, T: float = 3.0007) -> float:
    u = _sous_jacent(skew)
    u["sigma"] = sigma
    return run_mc(_compile(), [u], [[1.0]], 0.03, T, 40000, model, seed=42,
                  user_params={}, strike_set_t=strike_set_t)["price"]


def test_le_prix_pre_strike_bouge_avec_la_volatilite():
    """Le test qui attrape un fil débranché : une hypothèse qui n'atteint pas le
    moteur laisse le prix rigoureusement immobile, et une assertion de valeur ne
    le verrait pas."""
    t = -(VALO - STRIKE).days / 365.25
    bas, haut = _prix(t, sigma=0.15), _prix(t, sigma=0.35)
    assert abs(haut - bas) > 0.01


def test_sous_vol_constante_le_fixing_diffuse_ne_change_pas_le_prix():
    """Signature du forward-start homogène : sous un modèle invariant d'échelle,
    la loi de S(t)/S(strike) ne dépend pas du niveau où le strike tombe. Diffuser
    le fixing ou l'écraser sur son forward doit donc rendre le même prix — au
    bruit Monte Carlo près, la fenêtre supplémentaire changeant les tirages."""
    ecrase = _prix(None, T=3.0007)
    diffuse = _prix(0.0329, T=3.0336)
    assert diffuse == pytest.approx(ecrase, abs=0.005)


def test_sous_vol_locale_la_dispersion_du_fixing_compte():
    """Et voici pourquoi on la simule. Sous vol locale, la vol rencontrée dépend
    du niveau ABSOLU : l'endroit où le fixing tombe change le skew que le produit
    subira, et moyenner sur cette dispersion n'est pas la même chose que pricer
    au forward. Allonger la fenêtre d'attente à maturité constante doit donc
    déplacer le prix — un prix insensible signalerait un fixing écrasé."""
    court = _prix(0.02, model="localvol", skew=-0.40, T=3.02)
    long = _prix(0.50, model="localvol", skew=-0.40, T=3.50)
    assert abs(long - court) > 0.005


# ── Les sensibilités : tout est calculé, reste à dire ce qu'elles mesurent ─

def _greeks(model: str, skew: float = 0.0, pre_strike: bool = True) -> dict:
    u = _sous_jacent(skew)
    return compute_greeks(_compile(), [u], [[1.0]], 0.03,
                          3.0336 if pre_strike else 3.0007, 20000, model,
                          seed=42, user_params={},
                          selected=["delta", "gamma", "vega", "rho"],
                          strike_set_t=0.0329 if pre_strike else None)


@pytest.mark.parametrize("model", ["constant", "heston"])
def test_sans_dynamique_de_smile_le_delta_est_nul(model):
    """Sous un modèle invariant d'échelle, bumper le spot met le fixing simulé à
    l'échelle avec la trajectoire : tous les rapports au strike sont inchangés et
    le prix ne bouge pas d'un centime. Le zéro n'est pas une approximation, c'est
    une identité — et il vaut pour Heston, qui a pourtant un smile : celui-ci
    flotte avec le spot au lieu d'être ancré en strikes."""
    g = _greeks(model)
    assert g["delta_1"] == 0.0
    assert g["gamma_1"] == 0.0
    assert g["vega_1"] != 0.0
    assert g["rho"] != 0.0


def test_sous_dupire_le_delta_de_smile_existe_et_suit_le_skew():
    """Le seul canal par lequel un forward-start a un delta : la nappe est cotée
    en strikes absolus, donc une trajectoire décalée y rencontre d'autres vols.
    Il doit donc RÉPONDRE au skew — un delta insensible à la pente signalerait
    que la normalisation a effacé l'information de niveau."""
    plat = _greeks("localvol", skew=0.0)["delta_1"]
    penche = _greeks("localvol", skew=-0.60)["delta_1"]
    assert penche != 0.0
    assert abs(penche - plat) > 0.05


def test_un_choc_de_spot_avant_le_strike_ne_met_pas_le_produit_hors_de_la_monnaie():
    """Un stress -20 % sur un produit non striké ne le fait pas décrocher : le
    strike se constatera 20 % plus bas lui aussi, et le produit reste identique
    en pourcentage de son propre strike. Sous vol constante l'impact est donc
    rigoureusement nul.

    Le panneau de chocs annonçait auparavant une perte sur un produit dont la
    protection n'a même pas commencé à courir. Aucune branche ne le corrige :
    c'est l'homogénéité, une fois le fixing simulé, qui rend le bon chiffre."""
    def px(mult, model="constant", skew=0.0):
        u = _sous_jacent(skew)
        return run_mc(_compile(), [u], [[1.0]], 0.03, 3.0336, 20000, model,
                      seed=42, user_params={}, strike_set_t=0.0329,
                      spot_mult=[mult], spot_base=[1.0])["price"]

    assert px(0.80) == px(1.0)                       # au centime, tirages communs
    # Sous vol locale, le choc a un effet réel : la trajectoire visite une autre
    # région d'une nappe cotée en strikes absolus.
    assert px(0.80, "localvol", -0.40) != px(1.0, "localvol", -0.40)


def test_le_delta_pre_strike_n_est_pas_le_delta_directionnel():
    """Garde-fou de convention. Les deux nombres répondent à des questions
    différentes — « le spot monte, mon produit striké à 100 % est-il plus dans la
    monnaie ? » contre « le spot monte, le strike montera avec lui, que devient
    le skew qui s'appliquera ? ». Le régime pré-strike existe pour ne pas servir
    le premier à la place du second."""
    strike_lv = _greeks("localvol", skew=-0.30, pre_strike=False)["delta_1"]
    forward_lv = _greeks("localvol", skew=-0.30)["delta_1"]
    assert abs(strike_lv - forward_lv) > 0.10

    # Le cas net : même produit, vol constante. Strike fixé -> delta réel ;
    # strike à venir -> exactement zéro.
    assert abs(_greeks("constant", pre_strike=False)["delta_1"]) > 0.01
    assert _greeks("constant")["delta_1"] == 0.0
