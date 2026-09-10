"""Le backtest comme ORACLE du pricing — point 4 du §14.

Le backtest rejoue un script sur des cours réels : c'est un cycle de vie sans
fixings officiels ni booking, donc le moyen le moins cher de vérifier
l'invariant central du plan — *même trajectoire, mêmes décisions dans le
pricing, le backtest et le lifecycle* — avant d'avoir construit le modèle de
fixings.

La comparaison est rendue possible par une **série plate** : à cours constant,
le niveau constaté vaut 1,0 partout, quelle que soit la fenêtre et quelle que
soit la grille. Ce qui reste comparable, c'est ce qui nous intéresse — les
décisions : quels blocs se déclenchent, dans quel ordre, avec quel rang
d'observation, et où le `STOP` tombe.

L'invariant s'entend **à la résolution de la grille près** (§14) : le rejeu
travaille sur 252 séances, le moteur sur 52 pas. Les tests ci-dessous ne
comparent donc jamais des dates au jour près, mais des décisions et des rangs.
"""
from datetime import date, timedelta

import pytest

from backend.app.core.payscript.parser import parse_script, resolve_constats
from backend.app.core.payscript.engine import eval_script_on_history, run_mc

DEBUT = date(2026, 9, 10)


def _serie(n_jours=800, niveau=100.0):
    """Une série plate : le niveau constaté vaut 1,0 partout, ce qui rend le
    rejeu et le Monte-Carlo comparables décision par décision."""
    jours = [(DEBUT + timedelta(days=i)).isoformat() for i in range(n_jours)]
    return jours, [niveau] * n_jours


def _resolu(src, constats, currency="EUR"):
    return resolve_constats(parse_script(src), constats, anchor=DEBUT, currency=currency)


def _rejeu(src, constats, user_params=None, T=3.0, tickers=("TK1",), n_jours=900):
    jours, px = _serie(n_jours)
    compiled = _resolu(src, constats)
    return eval_script_on_history(
        compiled, jours, {tk: list(px) for tk in tickers}, start_idx=0,
        T_max=T, user_params=user_params or {}, tickers=list(tickers), r=0.0)


def _ul():
    """Vol quasi nulle : la trajectoire simulée est la série plate du rejeu."""
    return dict(name="TK1", ticker="", ccy="EUR", sigma=0.0001, q=0.0,
                v0=1e-8, kappa=2.0, theta=1e-8, xi=0.01, rho_h=-0.7,
                alpha=0.0001, beta=0.5, rho=-0.3, nu=0.01,
                sigma_fx=0.0, rho_sfx=0.0, ccyh=0.0)


def _pricing(src, constats, user_params=None, T=3.0, n_actifs=1):
    compiled = _resolu(src, constats)
    uls = [dict(_ul(), name=f"TK{i + 1}") for i in range(n_actifs)]
    corr = [[1.0 if i == j else 0.5 for j in range(n_actifs)] for i in range(n_actifs)]
    res = run_mc(compiled, uls, corr, r=0.0, T_max=T, N=2, model="constant",
                 seed=1, antithetic=False, user_params=user_params or {})
    return res


def _montants_rejeu(res):
    """Les flux du rejeu, arrondis — l'ordre chronologique fait foi."""
    return [round(c["cf"], 4) for c in res["cash_flows"]]


def _montants_pricing(res):
    return [round(v["sum"] / 2, 4)
            for v in sorted(res["flux_table"].values(), key=lambda x: x["t"])]


CAL_ANNUEL = {"OBS": {"start_date": "2026-09-10", "end_date": "2029-09-10",
                      "roll_date": "2029-09-10", "frequency": "1Y",
                      "stub": "short_last", "window_frequency": "3M"}}

CAL_DEUX = {
    "COUPONS": {"start_date": "2026-09-10", "end_date": "2029-09-10",
                "roll_date": "2029-09-10", "frequency": "1Y", "stub": "short_last"},
    "SEMESTRES": {"start_date": "2026-09-10", "end_date": "2029-09-10",
                  "roll_date": "2029-09-10", "frequency": "6M", "stub": "short_last"},
}


# ── L'invariant : mêmes décisions des deux côtés ───────────────────────

def test_le_rang_d_observation_est_le_meme_des_deux_cotes():
    """Un seul calendrier, cas sain : rejeu et pricing lisent 1, 2, 3."""
    src = "CONSTAT() OBS\nAT OBS:\n  PAY INDEX \"rang\"\n"
    assert _montants_rejeu(_rejeu(src, CAL_ANNUEL)) == [1.0, 2.0, 3.0]
    assert _montants_pricing(_pricing(src, CAL_ANNUEL)) == [1.0, 2.0, 3.0]


def test_le_rang_reste_le_meme_avec_deux_calendriers():
    """Le cas qui a révélé le défaut côté moteur : un second calendrier ne doit
    pas toucher au rang du premier. Le rejeu doit lire la même chose que le
    pricing — sinon un produit se décide différemment selon qu'on le price ou
    qu'on le rejoue, ce qui est exactement ce que l'invariant interdit."""
    src = ("CONSTAT() COUPONS\nCONSTAT() SEMESTRES\n"
           "AT COUPONS:\n  PAY INDEX \"rang\"\nAT SEMESTRES:\n  PAY 0 \"semestre\"\n")
    rejeu = [m for m, c in zip(_montants_rejeu(_rejeu(src, CAL_DEUX)),
                               _rejeu(src, CAL_DEUX)["cash_flows"]) if m != 0.0]
    pricing = [m for m in _montants_pricing(_pricing(src, CAL_DEUX)) if m != 0.0]
    assert pricing == [1.0, 2.0, 3.0], pricing
    assert rejeu == pricing, f"rejeu={rejeu} vs pricing={pricing}"


def test_un_param_par_observation_lit_la_meme_ligne_des_deux_cotes():
    """`PARAM()` est indexé par le rang : il hérite de la même propriété. Une
    barrière dégressive doit lire les mêmes lignes au rejeu et au pricing."""
    src = ("CONSTAT() OBS\nPARAM() BAR = 100%\nAT OBS:\n  PAY BAR \"barriere lue\"\n")
    up = {"BAR": [0.11, 0.22, 0.33]}
    assert _montants_rejeu(_rejeu(src, CAL_ANNUEL, up)) == [0.11, 0.22, 0.33]
    assert _montants_pricing(_pricing(src, CAL_ANNUEL, up)) == [0.11, 0.22, 0.33]


# ── Les cas du point 9 du plan ─────────────────────────────────────────

def test_evenement_sur_agregat():
    """Une constatation sur période : le rejeu réduit la fenêtre sur les closes
    réels. Série plate, donc la moyenne vaut 1,0 — ce que le test vérifie est
    que la réduction s'applique sans faire dérailler le rejeu."""
    src = "CONSTAT() OBS AVG PERIOD\nAT OBS:\n  PAY WOF \"niveau constate\"\n"
    assert _montants_rejeu(_rejeu(src, CAL_ANNUEL)) == [1.0, 1.0, 1.0]


def test_evenement_direct_sur_une_sous_date():
    """`AT OBS[2][1]` vise un relevé qui n'est aucune constatation : le rejeu
    doit l'évaluer à sa propre date, sans réduction."""
    src = ("CONSTAT() OBS AVG PERIOD\nAT OBS:\n  PAY 0 \"constatation\"\n"
           "AT OBS[2][1]:\n  PAY 1 \"releve isole\"\n")
    res = _rejeu(src, CAL_ANNUEL)
    isoles = [c for c in res["cash_flows"] if c["cf"] == 1.0]
    assert len(isoles) == 1
    # Il tombe entre la première et la deuxième constatation.
    assert 1.0 < isoles[0]["t"] < 2.0, isoles[0]["t"]


def test_le_meme_fixing_sert_aux_deux_roles():
    """`AT OBS.last.last` lit le cours du dernier relevé, qui alimente aussi la
    moyenne de sa constatation. Un seul cours, deux usages — c'est l'invariant
    « aucun fixing compté deux fois » vu depuis le rejeu."""
    src = ("CONSTAT() OBS AVG PERIOD\nAT OBS:\n  PAY 1 \"moyenne\"\n"
           "AT OBS.last.last:\n  PAY 2 \"cloture\"\n")
    res = _rejeu(src, CAL_ANNUEL)
    t_moyenne = [c["t"] for c in res["cash_flows"] if c["cf"] == 1.0][-1]
    t_cloture = [c["t"] for c in res["cash_flows"] if c["cf"] == 2.0][0]
    assert t_moyenne == pytest.approx(t_cloture, abs=1e-9)


def test_un_stop_intermediaire_arrete_le_rejeu():
    """Un rappel à la deuxième constatation : rien ne doit être versé après, et
    le rejeu doit le signaler comme rappel anticipé."""
    src = ("CONSTAT() OBS\nAT OBS:\n  IF INDEX >= 2:\n"
           "    PAY 1 \"rappel\"\n    STOP\n")
    res = _rejeu(src, CAL_ANNUEL)
    assert res["early_recall"] is True
    assert _montants_rejeu(res) == [1.0]
    assert res["T_actual"] == pytest.approx(2.0, abs=0.02)


def test_plusieurs_sous_jacents():
    """Le worst-of de trois séries plates vaut 1,0 : ce que le test vérifie est
    que la réduction PAR SOUS-JACENT traverse le rejeu sans confondre les
    actifs."""
    src = "CONSTAT() OBS AVG PERIOD\nAT OBS:\n  PAY WOF \"worst-of\"\n"
    res = _rejeu(src, CAL_ANNUEL, tickers=("TK1", "TK2", "TK3"))
    assert _montants_rejeu(res) == [1.0, 1.0, 1.0]


def test_historique_insuffisant():
    """L'historique s'arrête avant la fin du produit : le rejeu s'arrête avec
    lui plutôt que d'inventer des cours. Les constatations couvertes sont
    versées, les autres non."""
    src = "CONSTAT() OBS\nAT OBS:\n  PAY 1 \"coupon\"\n"
    complet = _rejeu(src, CAL_ANNUEL, n_jours=1200)
    tronque = _rejeu(src, CAL_ANNUEL, n_jours=500)     # ~1,4 an d'historique
    assert len(_montants_rejeu(complet)) == 3
    assert len(_montants_rejeu(tronque)) == 1, _montants_rejeu(tronque)


def test_historique_absent_ne_leve_pas():
    """Aucun cours du tout : le rejeu renonce proprement plutôt que de lever."""
    compiled = _resolu("CONSTAT() OBS\nAT OBS:\n  PAY 1\n", CAL_ANNUEL)
    jours, _ = _serie(50)
    assert eval_script_on_history(compiled, jours, {"TK1": []}, start_idx=0,
                                  T_max=3.0, user_params={},
                                  tickers=["TK1"], r=0.0) is None


# ── La convention de transposition, vérifiée sans la modifier ──────────

def test_la_convention_252_place_les_constatations_ou_on_les_attend():
    """Le rejeu convertit les year-fractions en séances à 252 par an. Une
    constatation à un an tombe donc autour de la 252ᵉ séance de la série — pas
    à sa date calendaire, puisque la série est en jours calendaires ici.

    Le test fige la convention SANS la juger : c'est elle qui décide si un
    fixing du 10 septembre est lu au bon endroit, et la changer déplacerait
    toutes les constatations d'un backtest."""
    src = "CONSTAT() OBS\nAT OBS:\n  PAY INDEX \"rang\"\n"
    res = _rejeu(src, CAL_ANNUEL, n_jours=1200)
    ts = [round(c["t"], 4) for c in res["cash_flows"]]
    # Les year-fractions du script sont conservées telles quelles dans les flux.
    assert ts == [pytest.approx(0.9993, abs=0.02),
                  pytest.approx(2.0014, abs=0.02),
                  pytest.approx(3.0007, abs=0.02)], ts


# ── Le report d'un cours manquant, et son signalement ──────────────────

def _serie_trouee(n_jours=900, trous=()):
    """Une série plate dont certaines séances n'ont pas coté (cours à 0)."""
    jours, px = _serie(n_jours)
    px = list(px)
    for i in trous:
        px[i] = 0.0
    return jours, px


def test_un_cours_manquant_est_reporte_et_non_saute():
    """Sauter réduisait la fenêtre en silence : une moyenne sur trois relevés
    au lieu de quatre se présentait comme une moyenne. Le report est la
    convention de place pour un jour sans cotation — ce qu'il faut, c'est qu'il
    se dise."""
    src = "CONSTAT() OBS AVG PERIOD\nAT OBS:\n  PAY WOF \"niveau\"\n"
    compiled = _resolu(src, CAL_ANNUEL)
    # La série est plate : le report rend exactement le même niveau, ce qui
    # isole ce qu'on veut vérifier — le signalement, pas la valeur.
    # Trouer une séance qui porte VRAIMENT un relevé : le rejeu convertit les
    # year-fractions en séances à 252 par an, donc l'index se calcule.
    releve = compiled.events[0].window_dates[0][1]
    jours, px = _serie_trouee(trous=(round(releve * 252),))
    res = eval_script_on_history(compiled, jours, {"TK1": px}, start_idx=0,
                                 T_max=3.0, user_params={}, tickers=["TK1"], r=0.0)
    assert _montants_rejeu(res) == [1.0, 1.0, 1.0]
    assert res["releves_reportes"], "le report n'a pas été signalé"


def test_une_serie_complete_ne_signale_aucun_report():
    """Le cas normal : la liste vide est la seule qui autorise à n'en rien
    dire."""
    src = "CONSTAT() OBS AVG PERIOD\nAT OBS:\n  PAY WOF \"niveau\"\n"
    assert _rejeu(src, CAL_ANNUEL)["releves_reportes"] == []
