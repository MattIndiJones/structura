"""KID PRIIPs — Key Information Document analytical computation.

Runs one simulation to the recommended holding period, plus one per
intermediate period of Annex IV points 32-34, and returns:
  - SRI (Synthetic Risk Indicator 1-7) from VEV / MRM / CRM
  - 4 PRIIPs scenarios (stress/défavorable/modéré/favorable) × 3 horizons
  - Annualized net returns after costs for a 10 000€ investment
"""
from __future__ import annotations
import math
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from typing import Literal, Optional
try:
    from typing import Annotated
except ImportError:
    from typing_extensions import Annotated

import numpy as np
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

import json
from sqlmodel import Session, select

from ..core.schemas import PricingRequest
from ..core.payscript.parser import parse_script, resolve_analysis_constats, resolve_constats, effective_T_max
from ..core.payscript.engine import run_mark_to_future, compute_irr
from ..core.valuation_context import (
    ValuationContext, valuation_context_from_request, run_valuation,
    validate_mtf_context,
)
from .auth import get_current_user
from ..db.database import get_session
from ..db.models import User, KidRecord, Indicative, Deal
from ..core.product.models import FrozenObject
from ..core.product.inputs import calculation_context, pricing_input
from ..services.product_repository import ProductError, load_product, owned_record, stage_revision
from ..core import priips, priips_bootstrap
from ..core.regulatory_status import kid_status
from ..services.kid_receipts import issue_kid_receipt, bind_kid_receipt, archived_kid_status

router = APIRouter(prefix="/api/kid", tags=["kid"])

# ── PRIIPs classes: tables and formulas live in core/priips.py ─────────
# The former local SRI table did not match Annex II point 52 (a common
# autocall, MRM 5 / CRM 3, came out at SRI 4 instead of 5).
_mrm_from_vev = priips.mrm_from_vev
_sri = priips.sri


def _risk_free_df(t: float, r: float, yield_curve) -> float:
    """Risk-free discount factor from today, on the same zero-rate pillars and
    interpolation as the engine (engine._build_df_arr). Funding never enters:
    Annex II point 16 discounts the VaR at the risk-free rate."""
    if t <= 0:
        return 1.0
    if not yield_curve:
        return math.exp(-r * t)
    pillars = sorted(yield_curve, key=lambda p: p[0])
    times, rates = [p[0] for p in pillars], [p[1] for p in pillars]
    return math.exp(-float(np.interp(t, times, rates)) * t)


# ── Single MC run ─────────────────────────────────────────────────────

def _mc_percentiles(compiled, uls, corr, r, T_run, T_cap, N, model, seed,
                    antithetic, user_params, yield_curve, sigma_r, a_r,
                    floor_price: float = 0.0, valuation_context=None,
                    path_simulator=None) -> dict:
    """Amounts held at the recommended holding period, per scenario.

    Only valid when T_cap reaches the product's own horizon: the script runs
    to term and every path resolves contractually. Intermediate horizons go
    through `_horizon_percentiles` instead — see why there.

    Two figures per scenario, and they are different questions:

    - the AMOUNT is what the investor receives, the plain sum of the flows.
      An autocall redeemed at year 1 for 1.08 returns 1.08. No discounting,
      no reinvestment — a KID does not assume the client does anything with
      the money afterwards, and neither does this.
    - the RETURN is the internal rate of return of those flows AT THEIR
      DATES, which is what Excel's XIRR computes. Redeemed at year 1 paying
      8% gives 8%, whatever nominal horizon the row is labelled with.

    That denominator is the whole bug. `(amount/notional)^(1/T_h) - 1` spread
    an 8% one-year coupon over the five-year RHP and reported 1.55% a year.
    A scenario's return is annualised over the life THAT scenario had, not
    over the label at the top of the column."""
    T_eff = min(effective_T_max(compiled, T_run), T_cap)
    context = deepcopy(valuation_context) if valuation_context is not None else ValuationContext(
        underlyings=uls, corr_matrix=corr, r=r, T=T_eff, N=N,
        model=model, seed=seed, antithetic=antithetic, user_params=user_params,
        yield_curve=yield_curve or [], sigma_r=sigma_r, a_r=a_r)
    context.T = T_eff
    if path_simulator is not None:
        # Annex II point 19: at least 10 000 simulations.
        context.N = max(int(context.N), priips.MIN_SIMULATIONS)
    res = run_valuation(compiled, context, per_path_flows=True, flows_at_payment=True,
                        path_simulator=path_simulator)
    flows = [[(float(t) - context.value_date_t, float(v)) for t, v in stream]
             for stream in res["path_flows"]]
    if any(t < -1e-6 for stream in flows for t, _v in stream):
        raise ValueError("Le KID ne couvre pas les flux antérieurs à la value date.")
    px = np.array([sum(v for _t, v in fl) for fl in flows], dtype=np.float64)

    # Floor near-zero payoffs (surviving paths at intermediate horizon)
    if floor_price > 0.01:
        px = np.where(px < 0.01, floor_price, px)

    out = _percentile_rows(px, flows, res["price"], T_eff)
    curve = context.yield_curve or []
    out["present_values"] = [sum(v * _risk_free_df(t, context.r, curve) for t, v in fl)
                             for fl in flows]
    out["lives"] = [max((t for t, _v in fl), default=T_eff) for fl in flows]
    return out


def _percentile_rows(amounts, flows, pv, t_eff) -> dict:
    """Pick the scenario sitting at each PRIIPs percentile and report ITS
    amount and ITS return.

    Reading the percentile of the amounts and the percentile of the returns
    separately would pair one scenario's payout with another scenario's
    holding period, which is how a table ends up internally impossible. So
    the ranking is done once, on the outcome, and both figures are read off
    the same scenario."""
    order = np.argsort(amounts)
    n = len(order)

    def at(p: float) -> dict:
        idx = int(order[min(n - 1, max(0, int(round(p / 100.0 * n)) - 1 if p > 0 else 0))])
        cf = [{"t": float(t), "cf": float(v)} for t, v in flows[idx]]
        life = max((f["t"] for f in cf), default=float(t_eff))
        return {"amount": float(amounts[idx]),
                "irr": compute_irr([{"t": 0.0, "cf": -1.0}] + cf),
                "life": round(life, 4),
                # Per unit invested — _scenario_row rescales them for costs.
                "flows": cf}

    rows = {f"p{p}": at(p) for p in (1, 5, 10, 50, 90)}
    return {
        "price": float(np.mean(amounts)),
        "pv": float(pv),
        "p1": rows["p1"]["amount"], "p5": rows["p5"]["amount"], "p10": rows["p10"]["amount"],
        "p50": rows["p50"]["amount"], "p90": rows["p90"]["amount"],
        "scenarios": rows,
        "T_eff": round(float(t_eff), 4),
    }


def _horizon_percentiles(compiled, uls, corr, r, T_run, T_cap, N, model, seed,
                         antithetic, user_params, yield_curve, sigma_r, a_r,
                         n_outer: int = 2000, n_inner: int = 250,
                         valuation_context=None, outer_simulator=None) -> dict:
    """Distribution of what an investor walks away with at an INTERMEDIATE
    horizon: cash already received, plus continuation value and unpaid claims,
    including claims surviving a contractual STOP.

    Why this is not `_mc_percentiles` with a smaller T_cap. Truncating T_max
    filters `step_map` but never `mat_events`, so the `AT MATURITY` block fired
    at the truncated date and the product was valued as if it had reached
    term. Measured on a 5-year autocall (barrier 100%, coupon 8%, sigma 25%)
    at the 1-year horizon: price 1.0000 with a median gross payoff of 1.0000
    and 100% of paths paying something, half of them straight out of the
    maturity block. The product was redeeming its capital four years early.
    The reported figure was not even monotone in horizon (1.0000 at 1y against
    0.9502 at 5y), which is the tell: a shorter horizon cannot be worth more
    than the whole life of a capital-at-risk product for no reason.

    `floor_price` was the previous mitigation — surviving paths were floored
    at the full-maturity price. It replaced a distribution by a constant, so
    the "défavorable" and "stress" columns of every intermediate horizon read
    the same number for every scenario that had not knocked out.

    The payment-aware Mark-to-Future replay follows each outer scenario to the
    horizon, keeping coupon memory, observation counter and realized extrema.
    It preserves unpaid receivables after recall and reprices the continuation
    of live contracts. Total value per scenario = residual mark + cash received, which
    is precisely the PRIIPs question "what do I get if I exit here".

    Known limitation, refused rather than absorbed: the nested replay prices
    off a scalar rate. Letting a yield curve or a stochastic rate through
    would produce a document whose RHP row uses the curve and whose
    intermediate rows quietly use a flat rate — two conventions in one KID,
    which is the class of defect this rewrite exists to remove."""
    context = valuation_context or ValuationContext(
        underlyings=uls, corr_matrix=corr, r=r, T=effective_T_max(compiled, T_run),
        N=N, model=model, seed=seed, antithetic=antithetic,
        user_params=user_params, yield_curve=yield_curve or [],
        sigma_r=sigma_r, a_r=a_r)
    validate_mtf_context(compiled, context, payment_aware=True)
    outer = {}
    if outer_simulator is not None:
        # Annex IV point 37: intermediate values estimated consistently with
        # the RHP — the same historical bootstrap drives the market up to the
        # exit date; the continuation value after it stays the model's.
        from ..core.payscript.engine import mtf_simulation_axis
        from ..core.simulation_grid import simulation_grid
        with simulation_grid(context.steps_per_year):
            outer_ts, outer_dt = mtf_simulation_axis(compiled, context.T, [T_cap], False)
        outer = {"outer_paths": outer_simulator(outer_ts, outer_dt, len(context.underlyings),
                                                n_outer, np.random.default_rng(context.seed)),
                 "outer_times": priips_bootstrap.outer_axis_times(outer_dt, outer_ts)}
    mtf = run_mark_to_future(
        script=compiled, underlyings=context.underlyings,
        corr_matrix=context.corr_matrix, r=context.r, T_max=context.T,
        main_price=0.0, model=context.model,
        n_outer=n_outer, n_inner=n_inner, seed=context.seed,
        user_params=context.user_params, mtm_dates=[T_cap],
        barrier_monitoring=context.barrier_monitoring,
        yield_curve=context.yield_curve, sigma_r=context.sigma_r,
        credit_exposure=True, maturity_payment_t=context.maturity_payment_t,
        state=context.state, **outer,
    steps_per_year=context.steps_per_year)
    row = mtf["results"][0]
    marks = np.array(row["pvs"], dtype=np.float64) / 100.0        # residual value at T_cap

    # One dated flow stream per scenario: what was already paid, at its dates,
    # plus continuation value and unpaid receivables sold at the horizon.
    # A scenario recalled at year 1 keeps a one-year life even in the row
    # labelled "2.5 ans"; the exponent must follow the scenario, not the label.
    flows: list[list] = []
    for i, past in enumerate(row["realized_flows"]):
        # The payment-aware replay carries acquired future receivables too.
        # They belong in the residual mark, never in cash already received.
        stream = [(float(t), float(v)) for t, v in past if t <= T_cap + 1e-10]
        if marks[i] != 0.0:
            stream.append((float(T_cap), float(marks[i])))
        flows.append(stream)

    amounts = np.array([sum(v for _t, v in fl) for fl in flows], dtype=np.float64)
    pv = float(np.mean([sum(v * math.exp(-context.r * t) for t, v in fl) for fl in flows]))

    out = _percentile_rows(amounts, flows, pv, T_cap)
    out["terminated_pct"] = row["terminated_pct"]
    return out


# ── Historical returns for the Category 3 bootstrap ───────────────────

def _bootstrap_history(req, uls) -> "priips_bootstrap.HistoricalReturns":
    """Five years of daily closes (Annex II point 22(a)), unadjusted — a
    fixing is a raw close, and the drift correction removes the measured mean
    anyway. Every underlying needs a ticker, and the strike currency must be
    the asset's: the quanto term of point 22(c) is not implemented."""
    from datetime import timedelta
    from ..runtime import business_today
    from ..services.market_data import load_hist_prices
    tickers = [str(u.get("ticker") or "").strip() for u in uls]
    if not all(tickers):
        raise ValueError("Le bootstrap PRIIPs exige l'historique de chaque sous-jacent : "
                         "un ticker manque. Choisissez la simulation risque-neutre (indicative).")
    settlement = (getattr(req, "settlement_ccy", None) or "").upper()
    foreign = [u.get("name") or t for u, t in zip(uls, tickers)
               if settlement and (u.get("ccy") or settlement).upper() != settlement]
    if foreign:
        raise ValueError("Sous-jacent en devise différente de celle du produit ("
                         + ", ".join(foreign) + ") : la correction quanto de l'annexe II, "
                         "point 22(c), n'est pas implémentée.")
    today = business_today()
    start = today - timedelta(days=round(365.25 * priips_bootstrap.LOOKBACK_YEARS))
    # raw_history, as the Pricer backtest: the freshness policy is built for
    # fixings and refuses any five-year series with a gap longer than three
    # days (a long Easter weekend is one). The bootstrap only needs the
    # sessions common to every underlying, filtered by historical_returns.
    data = load_hist_prices(tickers, start.isoformat(), today.isoformat(),
                            adjusted=False, raw_history=True)
    if data.get("error"):
        raise ValueError(f"Historique indisponible pour le bootstrap : {data['error']}")
    return priips_bootstrap.historical_returns(data["dates"], data["prices"], tickers)


# ── Cost-adjusted scenario row ────────────────────────────────────────

def _scenario_row(sc: dict, T_h: float, cost_entry: float,
                  cost_exit: float, cost_ongoing: float,
                  initial_price_pct: float = 100.0, stress: dict | None = None) -> dict:
    """Convert scenario outcomes to KID display (10 000€ invested).

    Annex IV points 42, 44 and 45: the amount is the sum received net of
    costs, rounded to 10 EUR; the return is (value / investment)^(1/T) - 1
    with T the scenario's OWN holding period — its call date when it is
    called (Annex V point 17), never the label of the column. That is what
    kept an autocall redeemed at year 1 with an 8 % coupon from being shown
    at 1.55 % a year over a five-year RHP.

    `life` is the scenario's real holding period. It belongs on screen: two
    cells of the same column can legitimately carry different horizons, and a
    reader who is not told will think one of them is wrong."""
    investment = 10_000.0
    invested = investment * (1 - cost_entry / 100)
    # PayScript flows are expressed per unit of contractual notional.  A note
    # issued at par therefore keeps the historic 10k scaling.  For a product
    # bought away from par (a call premium of 12, for example), the same 10k
    # investment buys 10k / 12% units of contractual notional.
    contract_notional = invested / (initial_price_pct / 100.0)
    scen = sc.get("scenarios") or {}

    def _fmt(key: str, payoff: float, source: dict | None = None) -> dict:
        # `source`: another distribution's scenarios (the stressed run).
        row = (scen if source is None else source).get(key) or {}
        life = row.get("life") or T_h
        # One canonical dated stream drives BOTH published amount and return.
        # Older cached scenario fixtures may not carry flows; representing the
        # aggregate payoff as one flow at the scenario life is the only honest
        # backwards-compatible reconstruction.
        gross_flows = row.get("flows")
        if gross_flows is None:
            gross_flows = [{"t": life, "cf": payoff}]
        final_t = max((float(f["t"]) for f in gross_flows), default=float(life))
        net_flows = []
        for flow in gross_flows:
            t = float(flow["t"])
            gross_cf = float(flow["cf"]) * contract_notional
            ongoing_factor = (1 - cost_ongoing / 100) ** t
            # Exit costs apply once, to the cash movements at the scenario's
            # actual exit/redemption date.  Interim coupons are not exits.
            exit_factor = (1 - cost_exit / 100) if abs(t - final_t) < 1e-10 else 1.0
            net_flows.append({"t": t, "cf": gross_cf * ongoing_factor * exit_factor})

        net_flows = [{"t": round(f["t"], 6), "cf": round(f["cf"], 2)}
                     for f in net_flows]
        value = round(sum(f["cf"] for f in net_flows), 2)
        # Annex IV points 42, 44 and 45. The figure shown is the sum received,
        # coupons included, without reinvestment, rounded to the nearest 10
        # EUR; the return is (value / investment)^(1/T) - 1 over the scenario's
        # own holding period, not annualised up to one year. It replaces the
        # IRR of the dated flows the module used before: a three-year autocall
        # paying 8 % a year shows 7.4 % a year here, as the text prescribes,
        # not the 8 % an IRR gives.
        ratio_return = priips.scenario_return(value, investment, life)
        return {
            "amount": priips.round_amount(value),
            "value": value,
            "ann_return": round(ratio_return * 100.0, 2),
            "return_annualised": life > 1.0 + 1e-9,
            "return_status": "total_loss" if ratio_return == -1.0 else "computed",
            "life": round(life, 4),
            "net_flows": net_flows,
        }

    unfavourable = _fmt("p10", sc["p10"])
    if stress is None:
        # Risk-neutral (indicative) simulation: 1st percentile of the same run.
        stress_cell = _fmt("p1", sc["p1"])
    else:
        # Annex IV points 26-27: the stressed bootstrap's own distribution, at
        # the 1st percentile for a one-year holding period, the 5th otherwise.
        key = "p1" if T_h <= 1.0 + 1e-9 else "p5"
        stress_cell = _fmt(key, stress[key], stress.get("scenarios") or {})
        stress_cell["percentile"] = int(key[1:])
    # Annex IV point 20: the stress scenario shall not be better than the
    # unfavourable one.
    if stress_cell["value"] > unfavourable["value"]:
        stress_cell = {**unfavourable, "capped_at_unfavourable": True}
    return {
        "T": round(T_h, 4),
        "stress":      stress_cell,
        "defavorable": unfavourable,
        "modere":      _fmt("p50", sc["p50"]),
        "favorable":   _fmt("p90", sc["p90"]),
    }


# ── Request schema ────────────────────────────────────────────────────

class KidRequest(PricingRequest):
    product_id: Optional[int] = None
    product_terms_version: Optional[int] = None
    crm: int = Field(default=3, ge=1, le=6)
    # Annex II, Part 2: when the issuer's rating is given, the CRM is derived
    # from it (credit quality step adjusted to the maturity) and `crm` above is
    # ignored. Without a rating, `issuer_unrated_regulated` selects the
    # default step of point 43.
    issuer_rating: Optional[Literal["AAA", "AA", "A", "BBB", "BB", "B", "CCC"]] = None
    issuer_unrated_regulated: Optional[bool] = None
    initial_price_pct: float = Field(default=100.0, gt=0.0, le=1000.0)
    cost_entry: float = Field(default=0.0, ge=0, le=10)    # % one-shot
    cost_exit: float = Field(default=0.0, ge=0, le=10)     # % one-shot
    cost_ongoing: float = Field(default=0.0, ge=0, le=5)   # % per year
    # Annex II points 19-22: Category 3 simulates by bootstrapping five years
    # of daily historical returns. The model's risk-neutral simulation stays
    # available, explicitly, for products without a usable history.
    simulation: Literal["historical_bootstrap", "risk_neutral_model"] = "historical_bootstrap"


# ── Endpoint ──────────────────────────────────────────────────────────

@router.post("/compute")
def kid_compute(
    req: KidRequest,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    """Compute PRIIPs KID scenarios and SRI."""
    product = None
    if req.product_id is not None:
        try:
            owned_record(session, req.product_id, current)
            product = load_product(session, req.product_id)
            if (req.product_terms_version is not None
                    and req.product_terms_version != product.terms_version):
                raise ProductError(
                    "PRODUCT_TERMS_STALE",
                    "La version des termes du Product a changé.")
            req = KidRequest.model_validate(pricing_input(
                product, calculation_context(req.model_dump(mode="json"))))
        except ProductError as exc:
            raise HTTPException(
                exc.status, detail={"code": exc.code, "message": str(exc)})
        except ValueError as exc:
            raise HTTPException(422, str(exc))
    try:
        compiled = parse_script(req.script)
        compiled = resolve_analysis_constats(compiled, req)
    except ValueError as e:
        raise HTTPException(422, str(e))

    if not compiled.events:
        raise HTTPException(422, "Aucun événement AT défini dans le script.")

    uls = [u.model_dump() for u in req.underlyings]
    corr = req.corr_matrix
    n = len(uls)
    if len(corr) != n or any(len(row) != n for row in corr):
        raise HTTPException(422, "Matrice de corrélation invalide.")

    context = valuation_context_from_request(req, compiled)
    T_full = context.T
    # Annex IV points 32-34: one year for an RHP of one to ten years; one year
    # and half the RHP (rounded up to a year end) from ten years. The former
    # code always added half the RHP.
    periods = priips.intermediate_periods(T_full)

    bootstrap = None
    if req.simulation == "historical_bootstrap":
        try:
            history = _bootstrap_history(req, uls)
        except ValueError as e:
            raise HTTPException(422, str(e))
        curve = req.yield_curve or []
        bootstrap = {
            "history": history,
            # Annex II point 22(c): for the VaR, risk-neutral expectation.
            "risk_neutral": priips_bootstrap.BootstrapSimulator(
                history, "risk_neutral",
                discount_factor=lambda t: _risk_free_df(t, req.r, curve),
                dividend_yields=[float(u.get("q") or 0.0) for u in uls]),
            # Annex IV point 25: for the scenarios, the observed return.
            "historical": priips_bootstrap.BootstrapSimulator(history, "historical"),
        }

    common = dict(
        compiled=compiled, uls=uls, corr=corr, r=req.r,
        T_run=T_full, N=req.N, model=req.model, seed=req.seed,
        antithetic=req.antithetic, user_params=req.user_params,
        yield_curve=req.yield_curve or [], sigma_r=req.sigma_r, a_r=req.a_r,
        valuation_context=context,
    )

    try:
        if periods:
            validate_mtf_context(compiled, context, payment_aware=True)
        # Step 1 — recommended holding period: the contract runs to term.
        # With the bootstrap, two distributions: risk-neutral for the VaR
        # (Annex II), historical for the scenarios (Annex IV point 25).
        if bootstrap:
            sc_risk = _mc_percentiles(**common, T_cap=T_full, path_simulator=bootstrap["risk_neutral"])
            sc_full = _mc_percentiles(**common, T_cap=T_full, path_simulator=bootstrap["historical"])
        else:
            sc_full = sc_risk = _mc_percentiles(**common, T_cap=T_full, floor_price=0.0)

        # Step 2 — intermediate horizons, valued as a LIVING product (nested
        # replay, see _horizon_percentiles) rather than a truncated maturity.
        outer_simulator = bootstrap["historical"] if bootstrap else None
        with ThreadPoolExecutor(max_workers=max(1, len(periods))) as ex:
            futures = [ex.submit(_horizon_percentiles, **common, T_cap=t, outer_simulator=outer_simulator)
                       for t in periods]
            intermediate = [(t, f.result()) for t, f in zip(periods, futures)]

        # Step 3 — stress scenario (Annex IV point 26): returns rescaled to the
        # stressed volatility of EACH holding period, bootstrapped again.
        stress_by_period = {}
        if bootstrap:
            stressed = {t: priips_bootstrap.BootstrapSimulator(
                bootstrap["history"], "stress", stress_years=t) for t in [*periods, T_full]}
            stress_by_period[T_full] = _mc_percentiles(
                **common, T_cap=T_full, path_simulator=stressed[T_full])
            for t in periods:
                stress_by_period[t] = _horizon_percentiles(
                    **common, T_cap=t, outer_simulator=stressed[t])
    except ValueError as e:
        raise HTTPException(422, str(e))

    # Annex II points 16-17. The VaR is the value of the PRIIP at a 97.5 %
    # confidence level, discounted to today at the risk-free rate, per unit
    # invested — PayScript outcomes are per unit of contractual notional, so a
    # call bought for 12 is measured against 0.12. T is the RHP, or the call
    # date of that very outcome when it is called earlier.
    # A non-positive VaR (total loss at the 2.5th percentile) has no finite VEV:
    # it is the top of the scale, never the bottom.
    price_factor = req.initial_price_pct / 100.0
    var_value, var_years = priips.var_975(
        [v / price_factor for v in sc_risk["present_values"]], sc_risk["lives"], T_full)
    vev = priips.vev_from_var(var_value, var_years)
    mrm = priips.mrm_from_vev(vev)
    if req.issuer_rating is not None or req.issuer_unrated_regulated is not None:
        credit = priips.crm_from_credit(req.issuer_rating, T_full,
                                        unrated_regulated=bool(req.issuer_unrated_regulated))
    else:
        credit = {"crm": req.crm, "basis": "classe CRM saisie"}
    crm = credit["crm"]
    sri = _sri(mrm, crm)

    # Build horizons list (ascending T)
    cost = (req.cost_entry, req.cost_exit, req.cost_ongoing, req.initial_price_pct)
    horizons = [_scenario_row(sc, t, *cost, stress=stress_by_period.get(t)) for t, sc in intermediate]
    horizons.append(_scenario_row(sc_full, T_full, *cost, stress=stress_by_period.get(T_full)))
    # Annex VI points 70-71 and Annex VII table 1: costs over time, on the
    # moderate scenario — the same scenario without costs against with costs.
    for row, (t, sc) in zip(horizons, [*intermediate, (T_full, sc_full)]):
        gross = _scenario_row(sc, t, 0.0, 0.0, 0.0, req.initial_price_pct)["modere"]
        row["costs_over_time"] = priips.costs_over_time(
            gross["value"], row["modere"]["value"], 10_000.0, row["modere"]["life"])

    result = {
        "sri":  sri,
        "mrm":  mrm,
        "crm":  crm,
        "credit_risk": credit,
        "vev":  None if vev is None else round(vev * 100, 2),   # expressed in %
        # Annex II point 16: 97.5 % value, risk-free discounted, per unit invested.
        "var_975": round(var_value, 6), "var_years": round(var_years, 4),
        "simulation": ({**bootstrap["history"].metadata(),
                        "simulations": max(int(req.N), priips.MIN_SIMULATIONS)}
                       if bootstrap else {"method": "risk_neutral_model", "model": req.model,
                                          "simulations": int(req.N), "antithetic": bool(req.antithetic)}),
        "T_rhp": round(T_full, 4),
        "horizons": horizons,
        # The product's PRICE — a present value. `sc_full["price"]` is now the
        # mean amount held at the RHP, which is a different quantity.
        "full_price": round(sc_full["pv"], 4),
        "initial_price_pct": req.initial_price_pct,
        # No reinvestment hypothesis anywhere: an amount is the sum of the
        # flows received, a return is the IRR of those flows at their dates.
        # Each cell carries the `life` of the scenario it describes, which is
        # what its return is annualised over.
        "annualisation": "tri_flux_dates",
        "costs": {
            "initial_price": req.initial_price_pct,
            "entry":   req.cost_entry,
            "exit":    req.cost_exit,
            "ongoing": req.cost_ongoing,
            # Annex VII table 2, simplified: one-off entry and exit costs on
            # the amount invested, ongoing costs per year on that amount.
            "composition": priips.cost_composition(
                req.cost_entry, req.cost_exit, req.cost_ongoing, 10_000.0),
        },
    }
    # The status sits outside the signed result: it describes the method,
    # not the figures the receipt certifies.
    return {**result, **kid_status(), 'calculation_receipt': issue_kid_receipt(req, result, current, product)}


# ── Persistence — append-only, one row per generation ──────────────────

class KidSaveRequest(BaseModel):
    product_id: Optional[int] = None
    product_terms_version: Optional[int] = None
    indicative_id: Optional[int] = None
    deal_id: Optional[int] = None
    product_title: str = "Produit structuré"
    sri: int
    mrm: int
    crm: int
    # A total-loss first percentile has no finite VEV.  The compute endpoint
    # returns null with MRM 7 and persistence must preserve that fact.
    vev: Optional[float] = None
    T_rhp: float
    horizons: list = Field(default_factory=list)
    costs: dict = Field(default_factory=dict)
    calculation_receipt: Optional[dict] = None


def _kid_record_row(k: KidRecord) -> dict:
    row = {
        "id": k.id,
        "indicative_id": k.indicative_id,
        "deal_id": k.deal_id,
        "product_id": k.product_id,
        "product_terms_version": k.product_terms_version,
        "product_title": k.product_title,
        "sri": k.sri, "mrm": k.mrm, "crm": k.crm, "vev": k.vev, "T_rhp": k.t_rhp,
        "horizons": json.loads(k.horizons_json),
        "costs": json.loads(k.costs_json),
        "created_at": k.created_at.isoformat(),
    }
    try:
        evidence = json.loads(k.calculation_evidence_json or '{}')
    except (ValueError, TypeError):
        evidence = {'invalid': True}
    row['provenance_status'] = archived_kid_status(evidence, {**row, 'user_id': k.user_id})
    row['calculation_evidence'] = evidence or None
    row.update(kid_status())
    return row


@router.post("/save", status_code=201)
def save_kid(
    req: KidSaveRequest,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    if not req.indicative_id and not req.deal_id and not req.product_id:
        raise HTTPException(422, "product_id, indicative_id ou deal_id requis.")
    linked_product_id = req.product_id
    if req.indicative_id:
        ind = session.get(Indicative, req.indicative_id)
        if not ind or ind.user_id != current.id:
            raise HTTPException(404, "Indicatif introuvable")
        if linked_product_id is not None and ind.product_id != linked_product_id:
            raise HTTPException(422, "L’indicatif ne correspond pas au Product demandé.")
        linked_product_id = linked_product_id or ind.product_id
    if req.deal_id:
        deal = session.get(Deal, req.deal_id)
        if not deal or deal.user_id != current.id:
            raise HTTPException(404, "Deal introuvable")
        if deal.product_id is None:
            raise HTTPException(409, detail={
                "code": "DEAL_PRODUCT_MISSING",
                "message": "Le deal ne possède pas de Product canonique.",
            })
        if linked_product_id is not None and deal.product_id != linked_product_id:
            raise HTTPException(422, "Le deal ne correspond pas au Product demandé.")
        linked_product_id = linked_product_id or deal.product_id

    if linked_product_id is None:
        raise HTTPException(409, detail={
            "code": "DOCUMENT_PRODUCT_MISSING",
            "message": "Le KID doit être rattaché au Product canonique.",
        })

    product = None
    if linked_product_id is not None:
        try:
            owned_record(session, linked_product_id, current)
            product = load_product(session, linked_product_id)
        except ProductError as exc:
            raise HTTPException(exc.status, detail={"code": exc.code, "message": str(exc)})
        if req.product_terms_version is not None and req.product_terms_version != product.terms_version:
            raise HTTPException(409, "La version des termes du Product a changé.")

    try:
        evidence = bind_kid_receipt(req.calculation_receipt, req.model_dump(mode='json'), current, product)
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(422, str(exc)) from exc

    rec = KidRecord(
        product_id=linked_product_id,
        product_terms_version=product.terms_version if product else None,
        indicative_id=req.indicative_id, deal_id=req.deal_id, user_id=current.id,
        product_title=req.product_title,
        sri=req.sri, mrm=req.mrm, crm=req.crm, vev=req.vev, t_rhp=req.T_rhp,
        horizons_json=json.dumps(req.horizons), costs_json=json.dumps(req.costs),
        calculation_evidence_json=json.dumps(evidence, ensure_ascii=False),
    )
    try:
        session.add(rec)
        session.flush()
        document = FrozenObject({"kind": "KID", "record_id": rec.id,
                                 "terms_version": product.terms_version,
                                 "created_at": rec.created_at.isoformat()})
        product = product.model_copy(update={"documents": (*product.documents, document)})
        stage_revision(session, product, expected_revision=product.revision,
                       actor_id=current.id, action="PRODUCT_KID_RETAINED",
                       reason="Conservation d’un KID sur le Product.")
        session.commit()
    except Exception:
        session.rollback()
        raise
    session.refresh(rec)
    return _kid_record_row(rec)


@router.get("/records")
def list_kid_records(
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    indicative_id: Optional[int] = None,
    deal_id: Optional[int] = None,
    product_id: Optional[int] = None,
):
    if not indicative_id and not deal_id and not product_id:
        raise HTTPException(422, "product_id, indicative_id ou deal_id requis.")
    q = select(KidRecord).where(KidRecord.user_id == current.id)
    if indicative_id:
        q = q.where(KidRecord.indicative_id == indicative_id)
    if deal_id:
        q = q.where(KidRecord.deal_id == deal_id)
    if product_id:
        q = q.where(KidRecord.product_id == product_id)
    rows = session.exec(q.order_by(KidRecord.created_at.desc())).all()
    return [_kid_record_row(r) for r in rows]
