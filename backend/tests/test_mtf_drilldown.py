"""Drill-down Mark-to-Future : l'explication doit tomber juste, au centime.

Un panneau d'explication qui affiche un mark « voisin » de celui du graphique
est pire qu'aucun panneau : il donne au lecteur la certitude d'avoir compris un
chiffre qu'il n'a pas sous les yeux. Ces tests verrouillent les deux identités
qui font tenir l'écran :

    mark du panneau            == pvs[i] de l'éventail
    somme des VA des flux      == mark du panneau
"""
import math
from functools import lru_cache

import numpy as np
import pytest

from backend.app.core.payscript import engine as payscript_engine
from backend.app.core.payscript.parser import parse_script
from backend.app.core.payscript.engine import (
    run_mc, run_mark_to_future, run_mtf_drilldown, _simulate_mtf_outer, SY,
)


@pytest.fixture(autouse=True)
def _bound_test_mtf_batches(monkeypatch):
    """Keep fan/detail identity coverage while forcing several small chunks."""
    monkeypatch.setattr(payscript_engine, "MTF_MAX_BATCH", 5_000)


def _ul(**kw):
    d = dict(name="Nikkei", ticker="", ccy="EUR", sigma=0.20, q=0.019, v0=0.04,
             kappa=2.0, theta=0.04, xi=0.35, rho_h=-0.70, alpha=0.20, beta=1.0,
             rho=-0.30, nu=0.40, sigma_fx=0.0, rho_sfx=0.0, ccyh=0.0)
    d.update(kw)
    return [d]


C1 = [[1.0]]
REFERENCE_PATHS = 8_000

AUTOCALL = """
PARAM CPN = 8%
PARAM AC  = 100%
PARAM PDI = 60%
AT 1, 2, 3
  IF WOF >= AC
    PAY 1 + CPN * INDEX "rappel"
    STOP
AT MATURITY
  IF WOF >= PDI
    PAY 1 + CPN * 3 "pair + coupons"
  ELSE
    PAY WOF "perte en capital"
"""

PHOENIX = """
PARAM CPN = 8%
PARAM AC  = 100%
PARAM CB  = 70%
PARAM PDI = 60%
AT 0.5, 1, 1.5, 2, 2.5, 3
  IF WOF >= CB
    PAY CPN / 2 * (INDEX - MEMO) "coupon"
    SET MEMO = INDEX
  IF WOF >= AC
    PAY 1 "rappel"
    STOP
AT MATURITY
  IF WOF >= PDI
    PAY 1 "pair"
  ELSE
    PAY WOF "perte"
"""

CFG = dict(model="constant", n_outer=240, n_inner=120, n_dates=4, seed=42)


def _compute_fan(src, T, r, uls):
    cs = parse_script(src)
    p0 = run_mc(cs, uls, C1, r=r, T_max=T, N=REFERENCE_PATHS, model="constant", seed=123)["price"] * 100
    fan = run_mark_to_future(cs, uls, C1, r=r, T_max=T, main_price=p0, **CFG)
    return cs, uls, r, T, p0, fan


@lru_cache(maxsize=None)
def _cached_fan(src, T, r):
    """Share deterministic reference fans across read-only identity tests."""
    return _compute_fan(src, T, r, _ul())


def _fan(src, T=3.0, r=0.025, uls=None):
    if uls is None:
        return _cached_fan(src, T, r)
    return _compute_fan(src, T, r, uls)


def _quantile_ids(row, qs=(0.05, 0.25, 0.50, 0.75, 0.95)):
    """Même sélection que le front : rang sur les VIVANTS uniquement."""
    ids = [i for i, a in enumerate(row["alive"]) if a]
    ids.sort(key=lambda i: row["pvs"][i])
    out = []
    for q in qs:
        j = min(len(ids) - 1, max(0, round(q * (len(ids) - 1))))
        if ids[j] not in out:
            out.append(ids[j])
    return out


# ── Les deux identités qui portent l'écran ──────────────────────────

@pytest.mark.parametrize("src", [AUTOCALL, PHOENIX])
def test_le_mark_du_panneau_est_celui_de_l_eventail(src):
    """Le tirage interne est indexé sur (graine, rang de la date, lot). Rejouer
    le même rang et le même lot doit reproduire les chemins au bit près — sinon
    l'explication porte sur un mark que personne n'a affiché.

    Tolérance 1e-4 : `pvs` est arrondi à 4 décimales dans la charge utile de
    l'éventail, le panneau en publie 6."""
    cs, uls, r, T, p0, fan = _fan(src)
    for row in fan["results"]:
        if row["stats"] is None or not any(row["alive"]):
            continue
        ids = _quantile_ids(row)
        dd = run_mtf_drilldown(cs, uls, C1, r=r, T_max=T, main_price=p0,
                               t0=row["t"], scenario_ids=ids, script_source=src, **CFG)
        assert len(dd["scenarios"]) == len(ids)
        for scn in dd["scenarios"]:
            assert scn["mtf"] == pytest.approx(row["pvs"][scn["id"]], abs=1e-4), (
                f"t={row['t']} scénario #{scn['id']}")


@pytest.mark.parametrize("src", [AUTOCALL, PHOENIX])
def test_la_somme_des_va_reconstruit_le_mark(src):
    """La décomposition affichée doit se resommer au mark : c'est ce qui rend le
    tableau vérifiable à l'écran plutôt que déclaratif."""
    cs, uls, r, T, p0, fan = _fan(src)
    row = next(r_ for r_ in fan["results"] if r_["stats"] and any(r_["alive"]))
    dd = run_mtf_drilldown(cs, uls, C1, r=r, T_max=T, main_price=p0, t0=row["t"],
                           scenario_ids=_quantile_ids(row), script_source=src, **CFG)
    for scn in dd["scenarios"]:
        if not scn["alive"]:
            continue
        assert scn["future_flows"], "un contrat vivant a forcément des flux futurs"
        total = sum(f["pv"] for f in scn["future_flows"])
        assert total == pytest.approx(scn["mtf"], abs=1e-4)
        assert abs(scn["pv_residual"]) < 1e-4
        # VA = E[montant] x facteur d'actualisation, ligne par ligne.
        for f in scn["future_flows"]:
            assert f["pv"] == pytest.approx(f["e_amount"] * f["df"], abs=1e-4)
            assert 0.0 <= f["proba"] <= 100.0
            assert 0.0 < f["df"] <= 1.0


def test_la_trajectoire_expliquee_est_celle_de_l_eventail():
    """Les chemins outer sont tirés en ordre C : allonger l'horizon jusqu'à la
    maturité laisse chaque pas antérieur identique. C'est ce qui autorise le
    panneau à montrer la fin de la trajectoire sans changer son début."""
    cs, uls, r, T, p0, fan = _fan(AUTOCALL)
    row = fan["results"][1]
    ids = _quantile_ids(row)
    dd = run_mtf_drilldown(cs, uls, C1, r=r, T_max=T, main_price=p0, t0=row["t"],
                           scenario_ids=ids, script_source=AUTOCALL, **CFG)
    S_fan = _simulate_mtf_outer(uls, C1, r, fan_grid(fan), CFG["n_outer"], CFG["seed"])
    for scn in dd["scenarios"]:
        wof_fan = S_fan[1:, :, scn["id"]].min(axis=1)
        wof_panel = scn["path"]["wof"][1:1 + len(wof_fan)]
        assert np.allclose(wof_fan, wof_panel, atol=1e-6)
        # Le worst-of publié à la date de valorisation est celui du graphe.
        assert scn["wof_t0"] == pytest.approx(
            float(S_fan[dd["step_k"], :, scn["id"]].min()), abs=1e-6)


def fan_grid(fan):
    return [r["t"] for r in fan["results"]]


# ── Cohérence métier ────────────────────────────────────────────────

def test_contrat_eteint_marque_a_zero_et_sans_flux():
    """Un scénario déjà rappelé sort de l'échantillon dans l'éventail ; le
    panneau doit dire la même chose, pas exhiber le prix d'un produit mort."""
    cs, uls, r, T, p0, fan = _fan(AUTOCALL)
    row = next((r_ for r_ in fan["results"] if not all(r_["alive"])), None)
    assert row is not None, "aucun rappel dans ce run — test non concluant"
    dead = row["alive"].index(False)
    dd = run_mtf_drilldown(cs, uls, C1, r=r, T_max=T, main_price=p0, t0=row["t"],
                           scenario_ids=[dead], script_source=AUTOCALL, **CFG)
    scn = dd["scenarios"][0]
    assert scn["alive"] is False
    assert scn["mtf"] == 0.0
    assert scn["future_flows"] == []
    assert scn["recall_proba"] is None
    assert row["pvs"][dead] == 0.0
    # Il a bien encaissé quelque chose avant de mourir.
    assert scn["realized_cash"] > 0
    assert scn["final"]["recalled"] is True


def test_le_payoff_final_est_celui_de_la_trajectoire_et_non_une_esperance():
    """Le panneau compare un mark (espérance conditionnelle) au payoff réellement
    obtenu par CETTE trajectoire. Le second doit être une réalisation unique :
    somme de ses propres flux, pas une moyenne."""
    cs, uls, r, T, p0, fan = _fan(AUTOCALL)
    row = fan["results"][0]
    dd = run_mtf_drilldown(cs, uls, C1, r=r, T_max=T, main_price=p0, t0=row["t"],
                           scenario_ids=_quantile_ids(row), script_source=AUTOCALL, **CFG)
    for scn in dd["scenarios"]:
        fin = scn["final"]
        assert fin["total_undiscounted"] == pytest.approx(
            sum(f["v"] for f in fin["flows"]), abs=1e-6)
        # Un autocall paie 1+CPN*INDEX au rappel, ou 124% / WOF à maturité :
        # toujours une valeur unique, jamais une moyenne lissée.
        assert fin["total_undiscounted"] > 0
        assert fin["pv_at_0"] == pytest.approx(
            sum(f["v"] * math.exp(-r * f["t"]) for f in fin["flows"]), abs=1e-4)


def test_observations_statut_et_coherence_du_rappel():
    cs, uls, r, T, p0, fan = _fan(AUTOCALL)
    row = fan["results"][2]
    dd = run_mtf_drilldown(cs, uls, C1, r=r, T_max=T, main_price=p0, t0=row["t"],
                           scenario_ids=_quantile_ids(row), script_source=AUTOCALL, **CFG)
    for scn in dd["scenarios"]:
        obs = scn["observations"]
        assert [o["t"] for o in obs] == sorted(o["t"] for o in obs)
        # `past` suit exactement le pas de la date de valorisation.
        for o in obs:
            assert o["past"] == (o["step"] <= dd["step_k"])
        statuts = [o["status"] for o in obs]
        # Une fois éteint, on ne redevient pas vivant.
        if "éteint" in statuts:
            assert statuts.index("éteint") > 0
            assert "vivant" not in statuts[statuts.index("éteint"):]
        # Un scénario vivant à t0 n'a aucune observation passée qui l'ait rappelé.
        if scn["alive"]:
            assert all(o["status"] == "vivant" for o in obs if o["past"])


def test_barrieres_detectees_sans_confondre_coupon_et_niveau():
    """AC et PDI sont comparés au worst-of : ce sont des barrières. CPN ne l'est
    pas : c'est un taux. Deviner sur la valeur les aurait mis côte à côte."""
    cs, uls, r, T, p0, fan = _fan(AUTOCALL)
    row = fan["results"][0]
    dd = run_mtf_drilldown(cs, uls, C1, r=r, T_max=T, main_price=p0, t0=row["t"],
                           scenario_ids=[_quantile_ids(row)[0]], script_source=AUTOCALL, **CFG)
    noms = {b["name"] for b in dd["barriers"]}
    assert noms == {"AC", "PDI"}
    for b in dd["barriers"]:
        assert b["observable"] == "WOF"
        assert b["is_pct"] is True
    assert {b["name"]: b["level"] for b in dd["barriers"]} == {"AC": 1.0, "PDI": 0.6}


def test_panier_trois_actifs_series_par_sous_jacent_et_observable_distingue():
    """Sur un panier, le worst-of change de composant en cours de route : le
    panneau doit livrer chaque sous-jacent, pas seulement leur minimum.

    Et l'observable compté doit être le bon — `AC` se compare au worst-of
    courant, `KI` au worst-of MINIMUM (barrière knock-in surveillée en continu).
    Les confondre décrirait deux barrières identiques."""
    uls = [dict(name=nm, ticker="", ccy="EUR", sigma=s, q=0.02, v0=s * s, kappa=2.0,
                theta=s * s, xi=0.35, rho_h=-0.70, alpha=s, beta=1.0, rho=-0.30,
                nu=0.40, sigma_fx=0.0, rho_sfx=0.0, ccyh=0.0)
            for nm, s in [("SX5E", 0.24), ("SPX", 0.18), ("NKY", 0.21)]]
    corr = [[1.0, 0.6, 0.5], [0.6, 1.0, 0.55], [0.5, 0.55, 1.0]]
    src = """
PARAM CPN = 9%
PARAM AC  = 100%
PARAM KI  = 65%
AT 1, 2, 3
  IF WOF >= AC
    PAY 1 + CPN * INDEX "rappel"
    STOP
AT MATURITY
  IF WOF_MIN >= KI
    PAY 1 + CPN * 3 "pair + coupons"
  ELSE
    PAY WOF "perte"
"""
    cs = parse_script(src)
    r, T = 0.025, 3.0
    basket_cfg = {**CFG, "n_outer": 120, "n_inner": 80}
    p0 = run_mc(cs, uls, corr, r=r, T_max=T, N=REFERENCE_PATHS, model="constant", seed=123)["price"] * 100
    fan = run_mark_to_future(cs, uls, corr, r=r, T_max=T, main_price=p0, **basket_cfg)
    row = next(x for x in fan["results"] if x["stats"] and any(x["alive"]))
    dd = run_mtf_drilldown(cs, uls, corr, r=r, T_max=T, main_price=p0, t0=row["t"],
                           scenario_ids=_quantile_ids(row), script_source=src, **basket_cfg)

    assert dd["n_assets"] == 3
    assert dd["asset_names"] == ["SX5E", "SPX", "NKY"]
    obs = {b["name"]: b["observable"] for b in dd["barriers"]}
    assert obs == {"AC": "WOF", "KI": "WOF_MIN"}

    for scn in dd["scenarios"]:
        assert len(scn["path"]["assets"]) == 3
        assert all(len(a) == len(scn["path"]["t"]) for a in scn["path"]["assets"])
        assert len(scn["spots_t0"]) == 3
        # Le worst-of publié est bien le minimum des trois à la date de mark.
        assert scn["wof_t0"] == pytest.approx(min(scn["spots_t0"]), abs=1e-6)
        # Et la série worst-of domine par le bas, pas par le haut.
        for i in range(1, len(scn["path"]["t"])):
            assert scn["path"]["wof"][i] == pytest.approx(
                min(a[i] for a in scn["path"]["assets"]), abs=1e-6)
        # Le mark reste celui de l'éventail, panier ou pas.
        assert scn["mtf"] == pytest.approx(row["pvs"][scn["id"]], abs=1e-4)


# ── Garde-fous ──────────────────────────────────────────────────────

def test_date_hors_grille_refusee():
    """Le rang de la date indexe le RNG interne : expliquer une date absente de
    la grille produirait un mark plausible et différent de l'affiché."""
    cs, uls, r, T, p0, fan = _fan(AUTOCALL)
    with pytest.raises(ValueError, match="ne figure pas dans la grille"):
        run_mtf_drilldown(cs, uls, C1, r=r, T_max=T, main_price=p0, t0=1.234,
                          scenario_ids=[0], script_source=AUTOCALL, **CFG)


def test_scenario_hors_bornes_refuse():
    cs, uls, r, T, p0, fan = _fan(AUTOCALL)
    t0 = fan["results"][0]["t"]
    with pytest.raises(ValueError, match="hors bornes"):
        run_mtf_drilldown(cs, uls, C1, r=r, T_max=T, main_price=p0, t0=t0,
                          scenario_ids=[CFG["n_outer"]], script_source=AUTOCALL, **CFG)


def test_trop_de_scenarios_refuse():
    cs, uls, r, T, p0, fan = _fan(AUTOCALL)
    t0 = fan["results"][0]["t"]
    with pytest.raises(ValueError, match="au maximum"):
        run_mtf_drilldown(cs, uls, C1, r=r, T_max=T, main_price=p0, t0=t0,
                          scenario_ids=list(range(20)), script_source=AUTOCALL, **CFG)


def test_memes_refus_que_l_eventail():
    """Le drill-down ne doit jamais accepter ce que l'éventail refuse : il
    expliquerait un chiffre que l'écran ne peut pas produire."""
    cs, uls, r, T, p0, fan = _fan(AUTOCALL)
    t0 = fan["results"][0]["t"]
    base = dict(cs=cs)
    for kw, motif in [({"yield_curve": [[1.0, 0.02]]}, "courbe de taux"),
                      ({"sigma_r": 0.01}, "taux stochastiques"),
                      ({"barrier_monitoring": "continuous"}, "monitoring continu")]:
        cfg = {**CFG, **kw}
        with pytest.raises(ValueError, match=motif):
            run_mtf_drilldown(cs, uls, C1, r=r, T_max=T, main_price=p0, t0=t0,
                              scenario_ids=[0], script_source=AUTOCALL, **cfg)


def test_doublons_de_scenarios_dedupliques():
    cs, uls, r, T, p0, fan = _fan(AUTOCALL)
    row = fan["results"][0]
    dd = run_mtf_drilldown(cs, uls, C1, r=r, T_max=T, main_price=p0, t0=row["t"],
                           scenario_ids=[3, 3, 7, 3], script_source=AUTOCALL, **CFG)
    assert [s["id"] for s in dd["scenarios"]] == [3, 7]


# ── Espérances conditionnelles (fonctionnalité 2) ───────────────────

@pytest.mark.parametrize("src", [AUTOCALL, PHOENIX])
def test_esperances_conditionnelles_recalculables(src):
    """Chaque nouvelle tuile doit se retrouver à la main depuis `pvs_alive`."""
    _cs, _uls, _r, _T, _p0, fan = _fan(src)
    for row in fan["results"]:
        s = row["stats"]
        if s is None:
            continue
        av = np.array(row["pvs_alive"])
        win, lose = av[av > 100], av[av < 100]
        assert s["n_win"] == len(win)
        assert s["n_lose"] == len(lose)
        # n_win + n_lose peut être < n_alive : un mark pile à 100 n'est ni l'un
        # ni l'autre. La somme n'est donc pas une invariante, la borne l'est.
        assert s["n_win"] + s["n_lose"] <= row["n_alive"]
        for key, sub, off in [("e_mtm_win", win, 0.0), ("e_mtm_lose", lose, 0.0)]:
            if len(sub):
                assert s[key] == pytest.approx(sub.mean(), abs=1e-4)
            else:
                assert s[key] is None
        if len(win):
            assert s["avg_gain"] == pytest.approx((win - 100).mean(), abs=1e-4)
            assert s["max_gain"] == pytest.approx(win.max() - 100, abs=1e-4)
            assert s["e_mtm_win"] > 100
        if len(lose):
            assert s["avg_loss"] == pytest.approx((100 - lose).mean(), abs=1e-4)
            assert s["max_loss"] == pytest.approx(100 - lose.min(), abs=1e-4)
            assert s["avg_loss"] > 0 and s["max_loss"] > 0    # magnitudes positives
            assert s["e_mtm_lose"] < 100
        assert s["mtm_min"] == pytest.approx(av.min(), abs=1e-4)
        assert s["mtm_max"] == pytest.approx(av.max(), abs=1e-4)


def test_esperance_totale_est_la_moyenne_ponderee_des_deux_conditionnelles():
    """E(MTM) = P(gain)·E(MTM|gain) + P(perte)·E(MTM|perte) + P(=100)·100.
    L'identité qui empêche de lire une espérance conditionnelle comme une
    espérance tout court."""
    _cs, _uls, _r, _T, _p0, fan = _fan(PHOENIX)
    for row in fan["results"]:
        s = row["stats"]
        if s is None:
            continue
        n = row["n_alive"]
        n_flat = n - s["n_win"] - s["n_lose"]
        tot = (s["n_win"] * (s["e_mtm_win"] or 0)
               + s["n_lose"] * (s["e_mtm_lose"] or 0)
               + n_flat * 100.0)
        assert tot / n == pytest.approx(s["mean"], abs=1e-4)
