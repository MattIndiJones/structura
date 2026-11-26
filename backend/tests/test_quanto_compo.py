"""Quanto and compo underlyings (payscript/fx_overlay.py).

Each mode is checked against a closed form under constant volatility, the
compo forward is checked as a martingale under every supported smile model,
and the mode is required to move the price: an FX input that never reaches
the engine would pass a value-only test.
"""
from __future__ import annotations

import math
from datetime import date

import numpy as np
import pytest
from dateutil.relativedelta import relativedelta
from scipy.stats import norm

from backend.app.core.payscript.catalogue import PRODUCTS
from backend.app.core.payscript.engine import run_mc
from backend.app.core.payscript.parser import parse_script, resolve_constats

STRIKE = date(2026, 9, 14)
RD, RF, SIG, SX, Q = 0.03, 0.045, 0.22, 0.10, 0.02
UL = dict(name="S1", ticker="", ccy="USD", sigma=SIG, q=Q, v0=SIG**2, kappa=2.0, theta=SIG**2,
          xi=0.35, rho_h=-0.70, alpha=SIG, beta=1.0, rho=-0.30, nu=0.40,
          sigma_fx=0.0, rho_sfx=0.0, ccyh=0.0)


def _compiled(key: str, years: int):
    product = PRODUCTS[key]
    maturity = STRIKE + relativedelta(years=years)
    values = {}
    for name, spec in product["constats"].items():
        values[name] = (maturity.isoformat() if spec["role"] == "maturity"
                        else {"date": STRIKE.isoformat(), "window_length": None, "window_frequency": "1D"})
    compiled = resolve_constats(parse_script(product["script"]), values, anchor=STRIKE, currency="EUR")
    return compiled, max(d for e in compiled.events for d in e.dates)


def _price(key, params, underlying, model="constant", years=3, N=40000, monitoring="weekly"):
    compiled, T = _compiled(key, years)
    res = run_mc(compiled, [underlying], [[1.0]], r=RD, T_max=T, N=N, model=model, seed=3,
                 user_params=params, barrier_monitoring=monitoring)
    se = (res["ic95"][1] - res["ic95"][0]) / 3.92
    return res["price"], se, T


def _bs_call(F, K, vol, T, r):
    d1 = (math.log(F / K) + vol * vol * T / 2) / (vol * math.sqrt(T))
    return math.exp(-r * T) * (F * norm.cdf(d1) - K * norm.cdf(d1 - vol * math.sqrt(T)))


@pytest.mark.parametrize("rho", [-0.4, 0.3])
def test_quanto_call_matches_black_scholes_with_foreign_rate_and_quanto_drift(rho):
    u = dict(UL, sigma_fx=SX, rho_sfx=rho, fx_mode="quanto", r_ccy=RF)
    price, se, T = _price("call", {"STRIKE": 1.0}, u)
    ref = _bs_call(math.exp((RF - Q - rho * SIG * SX) * T), 1.0, SIG, T, RD)
    assert price == pytest.approx(ref, abs=4 * se + 5e-4)


@pytest.mark.parametrize("rho", [-0.4, 0.3])
def test_compo_call_matches_black_scholes_with_composite_volatility(rho):
    u = dict(UL, sigma_fx=SX, rho_sfx=rho, fx_mode="compo", r_ccy=RF)
    price, se, T = _price("call", {"STRIKE": 1.0}, u)
    vol = math.sqrt(SIG**2 + SX**2 + 2 * rho * SIG * SX)
    ref = _bs_call(math.exp((RD - Q) * T), 1.0, vol, T, RD)
    assert price == pytest.approx(ref, abs=4 * se + 5e-4)


@pytest.mark.parametrize("model", ["constant", "heston", "sabr"])
def test_compo_forward_is_a_deal_currency_martingale(model):
    u = dict(UL, sigma_fx=SX, rho_sfx=-0.4, fx_mode="compo", r_ccy=RF)
    price, se, T = _price("call", {"STRIKE": 0.0}, u, model=model)
    assert price == pytest.approx(math.exp(-Q * T), abs=4 * se + 5e-4)


def test_compo_continuous_barrier_reads_the_composite_volatility():
    rho = -0.4
    u = dict(UL, sigma_fx=SX, rho_sfx=rho, fx_mode="compo", r_ccy=RF)
    price, se, T = _price("brc_ki_americaine", {"COUPON": 0.08, "M_KI_BAR": 0.6}, u,
                          monitoring="continuous")
    vol = math.sqrt(SIG**2 + SX**2 + 2 * rho * SIG * SX)
    mu, s, h = RD - Q - vol**2 / 2, vol * math.sqrt(T), math.log(0.6)
    # Down-and-in put at 100 with barrier 60, by the reflection principle.
    from scipy.integrate import quad
    def touched_density(x):
        a = norm.pdf((x - mu * T) / s) / s
        return a if x <= h else math.exp(2 * mu * h / vol**2) * norm.pdf((x - 2 * h - mu * T) / s) / s
    put_in, _ = quad(lambda x: max(1 - math.exp(x), 0) * touched_density(x), mu * T - 9 * s, 0.0,
                     points=[h], limit=200)
    ref = math.exp(-RD * T) * (1.08 - put_in)
    assert price == pytest.approx(ref, abs=4 * se + 5e-4)


def test_each_fx_mode_moves_the_price():
    legacy = dict(UL, sigma_fx=SX, rho_sfx=-0.4)
    quanto = dict(legacy, fx_mode="quanto", r_ccy=RF)
    compo = dict(legacy, fx_mode="compo", r_ccy=RF)
    prices = [_price("call", {"STRIKE": 1.0}, u, N=8000)[0] for u in (legacy, quanto, compo)]
    assert abs(prices[1] - prices[0]) > 0.005 and abs(prices[2] - prices[1]) > 0.005
    # The foreign rate reaches the forward: +100 bps on it raises a quanto call.
    higher = _price("call", {"STRIKE": 1.0}, dict(quanto, r_ccy=RF + 0.01), N=8000)[0]
    assert higher > prices[1] + 0.005


def test_without_fx_mode_the_historical_price_is_unchanged_to_the_bit():
    base = dict(UL, sigma_fx=SX, rho_sfx=-0.4, ccyh=0.001)
    explicit = dict(base, fx_mode=None, r_ccy=None)
    assert _price("call", {"STRIKE": 1.0}, base, N=4000)[0] == _price("call", {"STRIKE": 1.0}, explicit, N=4000)[0]


HESTON = dict(v0=0.0484, kappa=1.5, theta=0.0484, xi=0.6, rho_h=-0.7)
SABR = dict(alpha=0.22, beta=1.0, rho=-0.5, nu=0.8)
SMILE = dict(skew=-0.10, curvature=0.05)


def _foreign_measure_put(model, T, rho, sx, K=0.8, paths=60000, steps_per_year=104, seed=2026):
    """Independent reference by change of numeraire: everything under the
    asset's own measure, no quanto term, plus a correlated FX path.
    quanto = exp(-r_f T) E^f[(K - S_T)^+ X0/X_T]; X drifts at r_d - r_f + sx^2."""
    rng = np.random.default_rng(seed)
    n = int(round(T * steps_per_year)); dt = T / n
    S = np.ones(paths); lX = np.zeros(paths)
    v = np.full(paths, HESTON["v0"]) if model == "heston" else np.full(paths, SABR["alpha"])
    rv = HESTON["rho_h"] if model == "heston" else SABR["rho"]
    rvp, rx = math.sqrt(1 - rv * rv), math.sqrt(1 - rho * rho)
    for _ in range(n):
        zs, z0, zx0 = rng.standard_normal((3, paths))
        zf, zx = rv * zs + rvp * z0, rho * zs + rx * zx0
        if model == "heston":
            vp = np.maximum(v, 0.0); vol = np.sqrt(vp)
            v = v + HESTON["kappa"] * (HESTON["theta"] - vp) * dt + HESTON["xi"] * vol * math.sqrt(dt) * zf
        else:
            vol = np.clip(v, 0.001, 3.0)
            v = v * np.exp(SABR["nu"] * math.sqrt(dt) * zf - 0.5 * SABR["nu"] ** 2 * dt)
        S *= np.exp((RF - Q - 0.5 * vol * vol) * dt + vol * math.sqrt(dt) * zs)
        lX += (RD - RF + 0.5 * sx * sx) * dt + sx * math.sqrt(dt) * zx
    pay = math.exp(-RF * T) * np.maximum(K - S, 0) / np.exp(lX)
    return pay.mean(), pay.std() / math.sqrt(paths)


@pytest.mark.parametrize("model", ["heston", "sabr"])
def test_smile_model_quanto_matches_the_change_of_numeraire(model):
    rho = -0.6
    u = dict(UL, **(HESTON if model == "heston" else SABR),
             sigma_fx=0.2, rho_sfx=rho, fx_mode="quanto", r_ccy=RF)
    price, se, T = _price("put", {"STRIKE": 0.8}, u, model=model)
    ref, rse = _foreign_measure_put(model, T, rho, sx=0.2)
    assert price == pytest.approx(ref, abs=4 * math.hypot(se, rse) + 5e-4)


def test_heston_variance_drift_correction_reaches_the_price(monkeypatch):
    # The deal-measure variance gains -xi*sigma_fx*rho_h*rho*sqrt(V): switched
    # off, the 80 % put moves by far more than its Monte Carlo error.
    from backend.app.core.payscript import diffusion
    u = dict(UL, **HESTON, sigma_fx=0.2, rho_sfx=-0.6, fx_mode="quanto", r_ccy=RF)
    with_shift, se, _ = _price("put", {"STRIKE": 0.8}, u, model="heston")
    monkeypatch.setattr(diffusion, "heston_variance_shift", lambda _u: 0.0)
    without, _, _ = _price("put", {"STRIKE": 0.8}, u, model="heston")
    assert abs(with_shift - without) > 5 * se


def test_local_vol_quanto_without_correlation_is_the_foreign_price_rediscounted():
    u = dict(UL, **SMILE)
    quanto, _, T = _price("put", {"STRIKE": 0.8}, dict(u, sigma_fx=0.2, rho_sfx=0.0, fx_mode="quanto", r_ccy=RF),
                          model="localvol", N=20000)
    compiled, _ = _compiled("put", 3)
    foreign = run_mc(compiled, [u], [[1.0]], r=RF, T_max=T, N=20000, model="localvol", seed=3,
                     user_params={"STRIKE": 0.8})["price"]
    # run_mc rounds prices to 1e-6.
    assert quanto * math.exp((RD - RF) * T) == pytest.approx(foreign, abs=2e-6)


@pytest.mark.parametrize("mode", ["quanto", "compo"])
def test_local_vol_flat_surface_matches_black_scholes(mode):
    rho = -0.6
    u = dict(UL, skew=0.0, curvature=0.0, sigma_fx=0.2, rho_sfx=rho, fx_mode=mode, r_ccy=RF)
    price, se, T = _price("put", {"STRIKE": 0.8}, u, model="localvol")
    if mode == "quanto":
        F, vol = math.exp((RF - Q - rho * SIG * 0.2) * T), SIG
    else:
        F, vol = math.exp((RD - Q) * T), math.sqrt(SIG**2 + 0.04 + 2 * rho * SIG * 0.2)
    call = _bs_call(F, 0.8, vol, T, RD)
    put = call - math.exp(-RD * T) * (F - 0.8)
    assert price == pytest.approx(put, abs=4 * se + 5e-4)


def test_lsv_quanto_leverage_is_fitted_on_the_asset_measure():
    u = dict(UL, **HESTON, **SMILE)
    compiled, T = _compiled("put", 3)
    res = run_mc(compiled, [dict(u, sigma_fx=0.2, rho_sfx=0.0, fx_mode="quanto", r_ccy=RF)], [[1.0]],
                 r=RD, T_max=T, N=40000, model="lsv", seed=9, user_params={"STRIKE": 0.8})
    assert res.get("lsv_own_measure_leverage") is True
    local = run_mc(compiled, [u], [[1.0]], r=RF, T_max=T, N=40000, model="localvol", seed=9,
                   user_params={"STRIKE": 0.8})
    # Same marginal as local vol in the asset's currency, to calibration residual.
    assert res["price"] * math.exp((RD - RF) * T) == pytest.approx(local["price"], abs=1.5e-3)


def test_lsv_fx_mode_is_refused_in_residual_valuation():
    u = dict(UL, **HESTON, **SMILE, sigma_fx=0.2, rho_sfx=-0.4, fx_mode="compo", r_ccy=RF)
    compiled, T = _compiled("put", 3)
    with pytest.raises(ValueError, match="LSV quanto/compo"):
        run_mc(compiled, [u], [[1.0]], r=RD, T_max=T, N=500, model="lsv", seed=1,
               user_params={"STRIKE": 0.8}, spot_base=[1.0])


def test_fx_mode_requires_the_asset_currency_rate():
    with pytest.raises(ValueError, match="taux sans risque de la devise"):
        _price("call", {"STRIKE": 1.0}, dict(UL, fx_mode="compo"), N=500)


def test_booked_snapshot_carries_the_fx_mode_into_lifecycle_valuation():
    from backend.app.core.inlife_valuation import _engine_underlyings
    market = {"underlyings": [{"name": "SPX", "ccy": "USD", "sigma": 20, "q": 1.5,
                               "sigma_fx": 8, "rho_sfx": -30, "ccyh": 0,
                               "fx_mode": "compo", "r_ccy": 4.5}]}
    [u] = _engine_underlyings(market, [{"name": "SPX"}])
    assert u["fx_mode"] == "compo" and u["r_ccy"] == pytest.approx(0.045)
    [legacy] = _engine_underlyings({"underlyings": [{"name": "SX5E", "sigma": 20}]}, [{"name": "SX5E"}])
    assert "fx_mode" not in legacy


def test_schema_accepts_the_modes_and_omits_them_when_absent():
    from backend.app.core.schemas import UnderlyingParams
    assert "fx_mode" not in UnderlyingParams().model_dump()
    u = UnderlyingParams(fx_mode="quanto", r_ccy=0.045)
    assert u.model_dump()["fx_mode"] == "quanto"
    with pytest.raises(ValueError):
        UnderlyingParams(fx_mode="cross")


def test_fx_mode_is_a_contract_term_of_the_product_not_a_market_assumption():
    from backend.app.core.product.inputs import pricing_input, split_pricing_input
    from backend.app.core.product.models import Product, UnderlyingIdentity
    payload = {"script": PRODUCTS["call"]["script"], "strike_date": STRIKE.isoformat(), "r": RD,
               "user_params": {"STRIKE": 1.0},
               "constats": {"STARTDATE": {"date": STRIKE.isoformat(), "window_length": None,
                                          "window_frequency": "1D"},
                            "MATURITYDATE": (STRIKE + relativedelta(years=3)).isoformat()},
               "underlyings": [dict(name="SPX", ticker="^GSPC", ccy="USD", sigma=0.2,
                                    sigma_fx=0.08, rho_sfx=-0.3, fx_mode="compo", r_ccy=RF)]}
    product, context = split_pricing_input(payload)
    assert product.terms.underlyings[0].fx_mode == "compo"
    assert "fx_mode" not in context["underlyings"][0] and context["underlyings"][0]["r_ccy"] == RF
    assert pricing_input(product, context)["underlyings"][0]["fx_mode"] == "compo"
    with pytest.raises(ValueError, match="identité"):
        pricing_input(product, {**context, "underlyings": [{**context["underlyings"][0], "fx_mode": "quanto"}]})
    # Products saved before quanto/compo keep the same serialised identity.
    assert UnderlyingIdentity(name="SX5E", ccy="EUR", fx_mode="").model_dump() == {
        "name": "SX5E", "ticker": "", "ccy": "EUR"}
    assert isinstance(product, Product)


CCY_CURVE = [[0.5, 0.02], [2.0, 0.035], [5.0, 0.055]]
AUTOCALL = {"COUPON": 0.08, "M_AC_BAR": 1.0, "M_KI_BAR": 0.6}


def _autocall(u, N=20000):
    compiled = resolve_constats(parse_script(PRODUCTS["autocall_athena"]["script"]), {
        "STARTDATE": {"date": STRIKE.isoformat(), "window_length": None, "window_frequency": "1D"},
        "OBSERVATIONDATES": {"first_observation_date": (STRIKE + relativedelta(years=1)).isoformat(),
                             "period_start_date": STRIKE.isoformat(),
                             "end_date": (STRIKE + relativedelta(years=5)).isoformat(),
                             "roll_date": STRIKE.isoformat(), "frequency": "1Y", "stub": "short_last"},
    }, anchor=STRIKE, currency="EUR")
    T = max(d for e in compiled.events for d in e.dates)
    return run_mc(compiled, [u], [[1.0]], r=RD, T_max=T, N=N, model="constant", seed=4,
                  user_params=AUTOCALL)["price"]


def test_quanto_reads_the_asset_currency_curve_through_its_shape():
    # Same 5-year zero rate, flat or steep: only the shape differs, and the
    # annual call dates read the forwards along the way.
    base = dict(UL, sigma_fx=SX, rho_sfx=-0.4, fx_mode="quanto", r_ccy=0.055)
    flat = _autocall(base)
    steep = _autocall(dict(base, ccy_curve=CCY_CURVE))
    assert abs(steep - flat) > 0.002


def test_compo_does_not_depend_on_the_asset_currency_curve():
    # S*X drifts at r_deal - q: the foreign rate enters the asset and leaves with the FX leg.
    base = dict(UL, sigma_fx=SX, rho_sfx=-0.4, fx_mode="compo", r_ccy=0.055)
    assert _autocall(dict(base, ccy_curve=CCY_CURVE)) == pytest.approx(_autocall(base), abs=2e-6)


def test_european_quanto_matches_black_scholes_at_the_foreign_zero_rate():
    from backend.app.core.payscript.rates import _build_rate_term
    u = dict(UL, sigma_fx=SX, rho_sfx=-0.4, fx_mode="quanto", r_ccy=0.045, ccy_curve=CCY_CURVE)
    price, se, T = _price("call", {"STRIKE": 1.0}, u, years=5)
    term = _build_rate_term(CCY_CURVE, 1, T, 0.045)
    zero = -math.log(term.df[-1]) / T
    ref = _bs_call(math.exp((zero - Q + 0.4 * SIG * SX) * T), 1.0, SIG, T, RD)
    assert price == pytest.approx(ref, abs=4 * se + 5e-4)


def test_local_vol_quanto_on_a_curve_without_correlation_is_the_foreign_price():
    from backend.app.core.payscript.rates import _build_rate_term
    u = dict(UL, **SMILE)
    compiled, T = _compiled("put", 3)
    quanto = run_mc(compiled, [dict(u, sigma_fx=0.2, rho_sfx=0.0, fx_mode="quanto", r_ccy=0.04,
                                    ccy_curve=CCY_CURVE)], [[1.0]], r=RD, T_max=T, N=20000,
                    model="localvol", seed=3, user_params={"STRIKE": 0.8})["price"]
    foreign = run_mc(compiled, [u], [[1.0]], r=0.04, T_max=T, N=20000, model="localvol", seed=3,
                     user_params={"STRIKE": 0.8}, yield_curve=CCY_CURVE)["price"]
    df_foreign = _build_rate_term(CCY_CURVE, 1, T, 0.04).df[-1]
    assert quanto * df_foreign / math.exp(-RD * T) == pytest.approx(foreign, rel=2e-4)


def test_lifecycle_reads_the_curve_only_behind_an_enabled_switch():
    from backend.app.core.inlife_valuation import _engine_underlyings
    row = {"name": "SPX", "ccy": "USD", "sigma": 20, "fx_mode": "quanto", "r_ccy": 4.5,
           "ccyCurve": [{"T": 1, "rate": 4.0}, {"T": 5, "rate": 5.0}]}
    [on] = _engine_underlyings({"underlyings": [dict(row, ccyCurveEnabled=True)]}, [{"name": "SPX"}])
    [off] = _engine_underlyings({"underlyings": [dict(row, ccyCurveEnabled=False)]}, [{"name": "SPX"}])
    assert [pytest.approx(node) for node in on["ccy_curve"]] == [[1.0, 0.04], [5.0, 0.05]]
    assert off["ccy_curve"] == []


def test_mark_to_future_refuses_compo_and_the_asset_currency_curve():
    from backend.app.core.payscript.mark_to_future import _mtf_reject_unsupported
    with pytest.raises(ValueError, match="compo"):
        _mtf_reject_unsupported("constant", "weekly", [], 0.0, [dict(UL, fx_mode="compo", r_ccy=RF)])
    with pytest.raises(ValueError, match="devise du sous-jacent"):
        _mtf_reject_unsupported("constant", "weekly", [], 0.0,
                                [dict(UL, fx_mode="quanto", r_ccy=RF, ccy_curve=CCY_CURVE)])
    _mtf_reject_unsupported("constant", "weekly", [], 0.0, [dict(UL, fx_mode="quanto", r_ccy=RF)])
