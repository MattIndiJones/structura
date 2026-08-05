"""Audit Mark-to-Future du 2026-08-03 — non-régression des défauts trouvés.

Le fil conducteur de cet audit est la **propriété de la tour** : à toute date de
valorisation t0, un mark-to-future correct vérifie

    P0 = E[ VA(flux déjà versés avant t0) + 1{vivant} · DF(t0) · MTF(t0) ]

C'est la seule identité qui teste d'un coup les cash-flows, les dates, les
probabilités, l'actualisation, le conditionnement et le partage passé/futur.
Elle tenait déjà sur les produits dont le calendrier tombe pile sur la grille
hebdomadaire — ce que testaient les tests existants — et se cassait dès que ce
n'était pas le cas.
"""
import datetime as dtm
import math

import numpy as np
import pytest

from backend.app.core.payscript import engine as payscript_engine
from backend.app.core.payscript.parser import parse_script, resolve_constats
from backend.app.core.payscript.engine import (
    run_mc, run_mark_to_future, build_mtf_dates, _mtf_date_stats, _mtf_step, SY,
)


@pytest.fixture(autouse=True)
def _bound_test_mtf_batches(monkeypatch):
    """Exercise chunking without giving a statistical test a production-size peak."""
    monkeypatch.setattr(payscript_engine, "MTF_MAX_BATCH", 5_000)


def _ul(**kw):
    d = dict(name="S1", ticker="", ccy="EUR", sigma=0.22, q=0.0, v0=0.0484,
             kappa=2.0, theta=0.0484, xi=0.35, rho_h=-0.70, alpha=0.22, beta=1.0,
             rho=-0.30, nu=0.40, sigma_fx=0.0, rho_sfx=0.0, ccyh=0.0)
    d.update(kw)
    return [d]


C1 = [[1.0]]
REFERENCE_PATHS = 20_000


def _tower_z(cs, uls, r, T, p0, t0, n_outer=3000, n_inner=300, params=None):
    """Écart à la propriété de la tour, en nombre d'erreurs-types."""
    res = run_mark_to_future(cs, uls, C1, r=r, T_max=T, main_price=p0,
                             model="constant", n_outer=n_outer, n_inner=n_inner,
                             seed=42, user_params=params or {}, mtm_dates=[t0])
    row = res["results"][0]
    pvs = np.array(row["pvs"])
    alive = np.array(row["alive"])
    cash = np.array([sum(v * math.exp(-r * t) for t, v in fl) * 100
                     for fl in row["realized_flows"]])
    tot = cash + np.where(alive, pvs, 0.0) * math.exp(-r * t0)
    se = tot.std(ddof=1) / math.sqrt(len(tot))
    return (tot.mean() - p0) / se, tot.mean()


PHOENIX = """
PARAM CPN = 10%
PARAM AC  = 100%
PARAM CB  = 70%
AT 1, 2
  IF WOF >= CB
    PAY CPN "coupon"
  IF WOF >= AC
    PAY 1 "rappel"
    STOP
AT MATURITY
  PAY WOF "final"
"""


# ── Le partage passé/futur du calendrier ────────────────────────────

def test_partition_des_dates_sans_recouvrement():
    """Le rejeu outer résout tout événement dont le pas hebdomadaire est <=
    step_k ; le script résiduel doit donc écarter exactement ceux-là.

    Le critère était `d > t0` d'un côté et `round(d*SY) <= step_k` de l'autre :
    non complémentaires. Toute observation tombant entre t0 et sa propre
    frontière de pas (jusqu'à une demi-semaine) était rejouée ET repricée."""
    from backend.app.core.payscript.engine import _shift_events_for_mtf
    ev = parse_script(PHOENIX).events
    t0 = 0.995                      # step_k = 52, comme l'observation à t=1
    assert _mtf_step(t0) == _mtf_step(1.0) == 52
    shifted = _shift_events_for_mtf(ev, t0)
    dates_at = [d for e in shifted if e.type == "AT" for d in e.dates]
    # 1.0 est déjà consommée par le rejeu : elle ne doit PAS repartir dans le résiduel.
    assert not any(abs(d - (1.0 - t0)) < 1e-6 for d in dates_at)
    assert any(abs(d - (2.0 - t0)) < 1e-6 for d in dates_at)


def test_pas_de_double_comptage_dans_la_fenetre_d_arrondi():
    """Le coupon était payé deux fois — une fois dans `realized_flows`, une fois
    dans le mark — et la barrière d'autocall testée deux fois à une semaine
    d'écart. Mesuré à t0=0.995 : +415 bp d'écart à la tour, z = +21.8."""
    cs = parse_script(PHOENIX)
    r, T = 0.03, 2.0
    p0 = run_mc(cs, _ul(), C1, r=r, T_max=T, N=REFERENCE_PATHS, model="constant",
                seed=123)["price"] * 100
    for t0 in (0.98, 0.995, 1.0):
        z, _ = _tower_z(cs, _ul(), r, T, p0, t0)
        assert abs(z) < 4.0, f"t0={t0} : écart à la tour z={z:.1f}"


@pytest.mark.parametrize("t0", [0.5962, 1.1923, 1.7885, 2.3846, 2.9808])
def test_tour_sur_autocall_a_toutes_les_dates(t0):
    """Autocall 3 ans, coupon 8 %, PDI 60 % — le cas de référence du métier."""
    cs = parse_script("""
PARAM CPN = 8%
PARAM AC  = 100%
PARAM PDI = 60%
AT 1, 2, 3
  IF WOF >= AC
    PAY 1 + CPN * INDEX "rappel"
    STOP
AT MATURITY
  IF WOF >= PDI
    PAY 1 + CPN * 3
  ELSE
    PAY WOF
""")
    uls, r = _ul(sigma=0.20, q=0.019), 0.025
    p0 = run_mc(cs, uls, C1, r=r, T_max=3.0, N=REFERENCE_PATHS, model="constant",
                seed=123)["price"] * 100
    z, _ = _tower_z(cs, uls, r, 3.0, p0, t0, n_outer=2000, n_inner=300)
    assert abs(z) < 4.0, f"t0={t0} : écart à la tour z={z:.1f}"


# ── Fenêtre de fixing réalisée ──────────────────────────────────────

FIX_SCRIPT = """
CONSTAT() STRIKE_FIX
PARAM AC = 100%
AT 2, 3
  IF WOF / FIX_AVG >= AC
    PAY 1 + 0.08 * INDEX "rappel"
    STOP
AT MATURITY
  PAY WOF / FIX_AVG "final"
"""


def _fix_script():
    return resolve_constats(parse_script(FIX_SCRIPT), {"STRIKE_FIX": {
        "start_date": "2026-08-03", "end_date": "2027-02-03",
        "roll_date": "2026-09-03", "frequency": "1M"}}, anchor=dtm.date(2026, 8, 3))


@pytest.mark.parametrize("t0", [0.35, 0.8, 1.5])
def test_strike_fix_realise_conserve_en_mtf(t0):
    """La réduction MIN/MAX/AVERAGE des fixings déjà tombés doit être transmise
    au repricing résiduel, une valeur par scénario outer.

    Elle ne l'était pas : le résiduel ne voyait que les fixings encore à venir.
    Fenêtre à moitié écoulée -> moyenne sur le mauvais sous-ensemble ;
    fenêtre entièrement écoulée -> repli sur le neutre 1.0, c'est-à-dire un
    produit à strike asiatique marqué comme si son strike n'avait jamais été
    fixé (mesuré : -108 bp à t0=1.5, z=-3.6)."""
    cs = _fix_script()
    r, T = 0.03, 3.0
    p0 = run_mc(cs, _ul(), C1, r=r, T_max=T, N=REFERENCE_PATHS, model="constant",
                seed=1)["price"] * 100
    z, _ = _tower_z(cs, _ul(), r, T, p0, t0, n_outer=2000, n_inner=400)
    assert abs(z) < 4.0, f"t0={t0} : écart à la tour z={z:.1f}"


def test_fenetre_de_fixing_entierement_passee_ne_revient_pas_au_neutre():
    """Cas le plus net : à t0=1.5 tous les fixings sont derrière. Le strike est
    alors une constante par scénario, et les marks doivent en hériter — donc
    différer entre scénarios autrement que par le seul spot."""
    cs = _fix_script()
    assert all(d < 0.6 for d in cs.strike_fix_dates)
    res = run_mark_to_future(cs, _ul(), C1, r=0.03, T_max=3.0, main_price=89.0,
                             model="constant", n_outer=300, n_inner=200, seed=3,
                             mtm_dates=[1.5])
    pvs = np.array(res["results"][0]["pvs"])
    assert pvs.std() > 1e-6      # le strike réalisé varie d'un scénario à l'autre


# ── Estimateur de quantile ──────────────────────────────────────────

def test_quantiles_standards_et_strictement_ordonnes():
    """`sorted[int(p*n)]` renvoyait la (floor(p*n)+1)-ième statistique d'ordre :
    à n=60, le « P01 » publié était le MINIMUM de l'échantillon (9 points de
    nominal sous le vrai 1er centile) et le « P99 » le MAXIMUM. Ce sont les deux
    lignes de risque extrême de l'éventail, et le MTF conditionne sur la survie,
    donc les dates tardives d'un produit rappelable tournent sur quelques
    dizaines de contrats."""
    rng = np.random.default_rng(0)
    for n in (60, 200, 2000):
        x = rng.normal(100, 15, n)
        st = _mtf_date_stats(x, 100.0)
        for p, k in [(0.01, "p01"), (0.05, "p05"), (0.25, "p25"), (0.50, "p50"),
                     (0.75, "p75"), (0.95, "p95"), (0.99, "p99")]:
            assert st[k] == pytest.approx(float(np.quantile(x, p)), abs=1e-9)
        qs = [st[k] for k in ("p01", "p05", "p25", "p50", "p75", "p95", "p99")]
        assert all(a < b for a, b in zip(qs, qs[1:]))


# ── Garde-fous ──────────────────────────────────────────────────────

def test_date_de_mark_sous_un_demi_pas_refusee():
    """step_k = 0 faisait indexer un tenseur vide : `IndexError: index -1 is out
    of bounds for axis 0 with size 0`, une trace sur laquelle aucun appelant ne
    peut agir."""
    cs = parse_script(PHOENIX)
    with pytest.raises(ValueError, match="trop proche"):
        run_mark_to_future(cs, _ul(), C1, r=0.03, T_max=2.0, main_price=100.0,
                           model="constant", n_outer=20, n_inner=20, seed=1,
                           mtm_dates=[0.005])


def test_grille_de_dates_strictement_croissante_sur_produit_ultra_court():
    """Le plancher à une semaine ne doit pas produire deux marks identiques."""
    for T_max, n in [(0.05, 4), (0.1, 6), (1.0, 12), (3.0, 5), (10.0, 12)]:
        g = build_mtf_dates(T_max, n)
        assert all(a < b for a, b in zip(g, g[1:])), (T_max, n, g)
        assert all(_mtf_step(d) >= 1 for d in g), (T_max, n, g)
    assert build_mtf_dates(3.0, 5) == [0.5962, 1.1923, 1.7885, 2.3846, 2.9808]


def test_courbe_et_taux_stochastiques_refuses_au_lieu_d_etre_ignores():
    """L'IHM envoie `yield_curve` dans le même corps de requête pour toutes les
    analyses. /api/mtf le recevait et le jetait : le prix P0 portait la courbe,
    tout l'éventail — et le seuil P(MTM>=P0) auquel on le compare — était
    actualisé à plat, sans rien à l'écran pour le dire."""
    cs = parse_script(PHOENIX)
    with pytest.raises(ValueError, match="courbe de taux"):
        run_mark_to_future(cs, _ul(), C1, r=0.03, T_max=2.0, main_price=100.0,
                           model="constant", n_outer=20, n_inner=20, seed=1,
                           yield_curve=[[1.0, 0.02], [2.0, 0.035]])
    with pytest.raises(ValueError, match="taux stochastiques"):
        run_mark_to_future(cs, _ul(), C1, r=0.03, T_max=2.0, main_price=100.0,
                           model="constant", n_outer=20, n_inner=20, seed=1,
                           sigma_r=0.01)


def test_endpoint_mtf_transmet_courbe_et_sigma_r():
    """La garde ne sert à rien si la couche API ne fait pas suivre les champs."""
    import inspect
    from backend.app.api.pricing import mtf_endpoint
    src = inspect.getsource(mtf_endpoint)
    assert "yield_curve=req.yield_curve" in src
    assert "sigma_r=req.sigma_r" in src


# ── Univers statistique ─────────────────────────────────────────────

def test_toutes_les_statistiques_portent_sur_les_survivants():
    """Chaque agrégat publié doit se recalculer sur `pvs_alive`, et
    `terminated_pct` / `n_alive` sur l'échantillon complet.

    Tolérance 1e-4 et non 1e-9 : `pvs`/`pvs_alive` sont arrondis à 4 décimales
    dans la charge utile alors que `stats` est calculé en pleine précision. Un
    client qui recalcule les agrégats depuis l'export retrouve donc les mêmes
    chiffres au demi-pip près, pas au bit près — c'est voulu."""
    cs = parse_script(PHOENIX)
    res = run_mark_to_future(cs, _ul(), C1, r=0.03, T_max=2.0, main_price=100.0,
                             model="constant", n_outer=400, n_inner=100, n_dates=4,
                             seed=5)
    for row in res["results"]:
        pvs = np.array(row["pvs"])
        alive = np.array(row["alive"])
        assert row["n_alive"] == int(alive.sum())
        assert row["terminated_pct"] == pytest.approx((~alive).mean() * 100, abs=0.01)
        assert np.array(row["pvs_alive"]) == pytest.approx(pvs[alive], abs=1e-9)
        assert np.all(pvs[~alive] == 0.0)
        if row["stats"] is None:
            assert row["n_alive"] == 0
            continue
        s, av = row["stats"], pvs[alive]
        assert s["mean"] == pytest.approx(av.mean(), abs=1e-4)
        assert s["std"] == pytest.approx(av.std(ddof=0), abs=1e-4)
        assert s["p50"] == pytest.approx(float(np.quantile(av, 0.5)), abs=1e-4)
        assert s["p_above_100"] == pytest.approx((av > 100).mean() * 100, abs=1e-9)
