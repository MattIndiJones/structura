"""KID PRIIPs — Key Information Document analytical computation.

Runs 3 Monte Carlo simulations (T_full, T_half, T_1Y) and returns:
  - SRI (Synthetic Risk Indicator 1-7) from VEV / MRM / CRM
  - 4 PRIIPs scenarios (stress/défavorable/modéré/favorable) × 3 horizons
  - Annualized net returns after costs for a 10 000€ investment
"""
from __future__ import annotations
import math
from concurrent.futures import ThreadPoolExecutor
from typing import Optional
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
from ..core.payscript.parser import parse_script, resolve_constats, effective_T_max
from ..core.payscript.engine import run_mc, run_mark_to_future, compute_irr
from .auth import get_current_user
from ..db.database import get_session
from ..db.models import User, KidRecord, Indicative, Deal

router = APIRouter(prefix="/api/kid", tags=["kid"])

# ── PRIIPs SRI lookup table [MRM-1][CRM-1] ───────────────────────────
_SRI_TABLE = [
    [1, 1, 2, 3, 4, 5],  # MRM 1
    [1, 2, 2, 3, 4, 5],  # MRM 2
    [2, 2, 3, 4, 4, 5],  # MRM 3
    [3, 3, 4, 4, 5, 6],  # MRM 4
    [4, 4, 4, 5, 6, 6],  # MRM 5
    [5, 5, 5, 5, 6, 7],  # MRM 6
    [6, 7, 7, 7, 7, 7],  # MRM 7
]

_VEV_THRESHOLDS = [0.005, 0.05, 0.12, 0.20, 0.30, 0.80]


def _mrm_from_vev(vev: float) -> int:
    for i, thr in enumerate(_VEV_THRESHOLDS):
        if vev < thr:
            return i + 1
    return 7


def _sri(mrm: int, crm: int) -> int:
    return _SRI_TABLE[max(0, min(mrm - 1, 6))][max(0, min(crm - 1, 5))]


# ── Single MC run ─────────────────────────────────────────────────────

def _mc_percentiles(compiled, uls, corr, r, T_run, T_cap, N, model, seed,
                    antithetic, user_params, yield_curve, sigma_r, a_r,
                    floor_price: float = 0.0) -> dict:
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
    res = run_mc(
        script=compiled, underlyings=uls, corr_matrix=corr, r=r,
        T_max=T_eff, N=N, model=model, seed=seed, antithetic=antithetic,
        user_params=user_params, yield_curve=yield_curve or [],
        sigma_r=sigma_r, a_r=a_r, per_path_flows=True,
    )
    flows = res["path_flows"]
    px = np.array([sum(v for _t, v in fl) for fl in flows], dtype=np.float64)

    # Floor near-zero payoffs (surviving paths at intermediate horizon)
    if floor_price > 0.01:
        px = np.where(px < 0.01, floor_price, px)

    return _percentile_rows(px, flows, res["price"], T_eff)


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

    rows = {f"p{p}": at(p) for p in (1, 10, 50, 90)}
    return {
        "price": float(np.mean(amounts)),
        "pv": float(pv),
        "p1": rows["p1"]["amount"], "p10": rows["p10"]["amount"],
        "p50": rows["p50"]["amount"], "p90": rows["p90"]["amount"],
        "scenarios": rows,
        "T_eff": round(float(t_eff), 4),
    }


def _horizon_percentiles(compiled, uls, corr, r, T_run, T_cap, N, model, seed,
                         antithetic, user_params, yield_curve, sigma_r, a_r,
                         n_outer: int = 2000, n_inner: int = 250) -> dict:
    """Distribution of what an investor walks away with at an INTERMEDIATE
    horizon: cash already received, plus the residual value of a contract that
    is still alive.

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

    Since the Mark-to-Future replay was made state-aware it computes exactly
    the right thing: each outer scenario is replayed from inception to the
    horizon, keeping coupon memory, observation counter and realized extrema;
    scenarios already recalled are marked at zero residual value and carry
    their cash; the rest get a residual repricing of what is left of the
    contract. Total value per scenario = residual mark + cash received, which
    is precisely the PRIIPs question "what do I get if I exit here".

    Known limitation, refused rather than absorbed: the nested replay prices
    off a scalar rate. Letting a yield curve or a stochastic rate through
    would produce a document whose RHP row uses the curve and whose
    intermediate rows quietly use a flat rate — two conventions in one KID,
    which is the class of defect this rewrite exists to remove."""
    if yield_curve:
        raise ValueError(
            "Horizons intermédiaires PRIIPs et courbe de taux : la revalorisation "
            "résiduelle ne porte pas encore la courbe. Générez le KID à taux plat, "
            "ou limitez-vous à la période de détention recommandée.")
    if sigma_r and sigma_r > 0:
        raise ValueError(
            "Horizons intermédiaires PRIIPs et taux stochastiques : la "
            "revalorisation résiduelle ne porte pas encore le facteur de taux. "
            "Générez le KID avec sigma_r = 0.")

    mtf = run_mark_to_future(
        script=compiled, underlyings=uls, corr_matrix=corr, r=r,
        T_max=effective_T_max(compiled, T_run),
        main_price=0.0, model=model,
        n_outer=n_outer, n_inner=n_inner, seed=seed,
        user_params=user_params, mtm_dates=[T_cap],
    )
    row = mtf["results"][0]
    marks = np.array(row["pvs"], dtype=np.float64) / 100.0        # residual value at T_cap
    alive = row["alive"]

    # One dated flow stream per scenario: what was already paid, at its dates,
    # plus — for a contract still running — the exit proceeds at the horizon.
    # A scenario recalled at year 1 keeps a one-year life even in the row
    # labelled "2.5 ans"; the exponent must follow the scenario, not the label.
    flows: list[list] = []
    for i, past in enumerate(row["realized_flows"]):
        stream = [(float(t), float(v)) for t, v in past]
        if alive[i] and marks[i] != 0.0:
            stream.append((float(T_cap), float(marks[i])))
        flows.append(stream)

    amounts = np.array([sum(v for _t, v in fl) for fl in flows], dtype=np.float64)
    pv = float(np.mean([sum(v * math.exp(-r * t) for t, v in fl) for fl in flows]))

    out = _percentile_rows(amounts, flows, pv, T_cap)
    out["terminated_pct"] = row["terminated_pct"]
    return out


# ── Cost-adjusted scenario row ────────────────────────────────────────

def _scenario_row(sc: dict, T_h: float, cost_entry: float,
                  cost_exit: float, cost_ongoing: float) -> dict:
    """Convert scenario outcomes to KID display (10 000€ invested).

    The annualised return is the IRR of the scenario's own dated flows — the
    XIRR of the client's actual cash movements — recomputed net of costs, and
    NOT `(amount/notional)^(1/T_h)`. Those two disagree the moment a product
    pays before the end of the row's nominal horizon, which is the normal
    case for anything callable: an autocall redeemed at year 1 with an 8%
    coupon returns 8%, and used to be published at 1.55% because the exponent
    said five years.

    `life` is the scenario's real holding period. It belongs on screen: two
    cells of the same column can now legitimately carry different horizons,
    and a reader who is not told will think one of them is wrong."""
    notional = 10_000.0
    invested = notional * (1 - cost_entry / 100)
    scen = sc.get("scenarios") or {}

    def _fmt(key: str, payoff: float) -> dict:
        row = scen.get(key) or {}
        life = row.get("life") or T_h
        gross = invested * payoff
        net = gross * ((1 - cost_exit / 100) * (1 - cost_ongoing / 100) ** life)
        net = round(net, 2)
        # Same flows, each bearing the ongoing cost accrued to its OWN date,
        # so the published rate is the one the client actually earns rather
        # than a gross figure with a net amount printed beside it.
        flows = row.get("flows")
        if flows:
            scaled = [{"t": f["t"],
                       "cf": f["cf"] * invested * (1 - cost_exit / 100)
                             * (1 - cost_ongoing / 100) ** f["t"]}
                      for f in flows]
            ann_irr = compute_irr([{"t": 0.0, "cf": -notional}] + scaled)
        else:
            ann_irr = None
            if life > 0 and net > 0:
                ann_irr = (net / notional) ** (1.0 / life) - 1.0
        ann = -100.0 if ann_irr is None else ann_irr * 100.0
        return {"amount": net, "ann_return": round(ann, 2), "life": round(life, 4)}

    return {
        "T": round(T_h, 4),
        "stress":      _fmt("p1", sc["p1"]),
        "defavorable": _fmt("p10", sc["p10"]),
        "modere":      _fmt("p50", sc["p50"]),
        "favorable":   _fmt("p90", sc["p90"]),
    }


# ── Request schema ────────────────────────────────────────────────────

class KidRequest(PricingRequest):
    crm: int = Field(default=3, ge=1, le=6)
    cost_entry: float = Field(default=0.0, ge=0, le=10)    # % one-shot
    cost_exit: float = Field(default=0.0, ge=0, le=10)     # % one-shot
    cost_ongoing: float = Field(default=0.0, ge=0, le=5)   # % per year


# ── Endpoint ──────────────────────────────────────────────────────────

@router.post("/compute")
def kid_compute(
    req: KidRequest,
    current: Annotated[User, Depends(get_current_user)],
):
    """Compute PRIIPs KID scenarios and SRI."""
    try:
        compiled = parse_script(req.script)
        compiled = resolve_constats(compiled, req.constats, anchor=req.anchor)
    except ValueError as e:
        raise HTTPException(422, str(e))

    if not compiled.events:
        raise HTTPException(422, "Aucun événement AT défini dans le script.")

    uls = [u.model_dump() for u in req.underlyings]
    corr = req.corr_matrix
    n = len(uls)
    if len(corr) != n or any(len(row) != n for row in corr):
        raise HTTPException(422, "Matrice de corrélation invalide.")

    T_full = req.T
    T_half = T_full / 2.0
    T_1y   = min(1.0, T_full)

    common = dict(
        compiled=compiled, uls=uls, corr=corr, r=req.r,
        T_run=T_full, N=req.N, model=req.model, seed=req.seed,
        antithetic=req.antithetic, user_params=req.user_params,
        yield_curve=req.yield_curve or [], sigma_r=req.sigma_r, a_r=req.a_r,
    )

    try:
        # Step 1 — recommended holding period: the contract runs to term.
        sc_full = _mc_percentiles(**common, T_cap=T_full, floor_price=0.0)

        # Step 2 — intermediate horizons, valued as a LIVING product (nested
        # replay, see _horizon_percentiles) rather than a truncated maturity.
        # They are only computed when they are actually displayed below.
        sc_half = sc_1y = None
        with ThreadPoolExecutor(max_workers=2) as ex:
            fut_half = (ex.submit(_horizon_percentiles, **common, T_cap=T_half)
                        if T_full > 0.5 else None)
            fut_1y = (ex.submit(_horizon_percentiles, **common, T_cap=T_1y)
                      if T_full > 1.0 else None)
            if fut_half is not None:
                sc_half = fut_half.result()
            if fut_1y is not None:
                sc_1y = fut_1y.result()
    except ValueError as e:
        raise HTTPException(422, str(e))

    # VEV from the 1st-percentile OUTCOME at the RHP (PRIIPs Annex II).
    # p1 is the amount received per unit invested — unchanged in definition
    # from before this module's rework, so MRM classification is untouched.
    # (The VEV formula itself remains the module's own approximation rather
    # than the RTS expression; that non-conformity is tracked separately.)
    p1 = sc_full["p1"]
    if p1 > 0.0 and p1 < 1.0:
        vev = math.sqrt(-2.0 * math.log(p1) / T_full)
        mrm = _mrm_from_vev(vev)
    elif p1 >= 1.0:
        # The 1st percentile still repays par: no downside worth measuring.
        vev, mrm = 0.0, 1
    else:
        # p1 <= 0 — at least 1% of scenarios wipe the investment out. The log
        # is undefined, and a single `else: vev = 0.0` used to route this into
        # the LOWEST risk class: a product that can lose everything came out at
        # MRM 1, i.e. safer than a government bond. A total loss is by
        # construction the top of the scale. The VEV itself has no finite value
        # here and is reported as absent rather than as a number.
        vev, mrm = None, 7

    sri = _sri(mrm, req.crm)

    # Build horizons list (ascending T)
    cost = (req.cost_entry, req.cost_exit, req.cost_ongoing)
    horizons = []
    if sc_1y is not None:
        horizons.append(_scenario_row(sc_1y,   T_1y,   *cost))
    if sc_half is not None:
        horizons.append(_scenario_row(sc_half, T_half, *cost))
    horizons.append(_scenario_row(sc_full, T_full, *cost))

    return {
        "sri":  sri,
        "mrm":  mrm,
        "crm":  req.crm,
        "vev":  None if vev is None else round(vev * 100, 2),   # expressed in %
        "T_rhp": round(T_full, 4),
        "horizons": horizons,
        # The product's PRICE — a present value. `sc_full["price"]` is now the
        # mean amount held at the RHP, which is a different quantity.
        "full_price": round(sc_full["pv"], 4),
        # No reinvestment hypothesis anywhere: an amount is the sum of the
        # flows received, a return is the IRR of those flows at their dates.
        # Each cell carries the `life` of the scenario it describes, which is
        # what its return is annualised over.
        "annualisation": "tri_flux_dates",
        "costs": {
            "entry":   req.cost_entry,
            "exit":    req.cost_exit,
            "ongoing": req.cost_ongoing,
        },
    }


# ── Persistence — append-only, one row per generation ──────────────────

class KidSaveRequest(BaseModel):
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
    horizons: list = []
    costs: dict = {}


def _kid_record_row(k: KidRecord) -> dict:
    return {
        "id": k.id,
        "indicative_id": k.indicative_id,
        "deal_id": k.deal_id,
        "product_title": k.product_title,
        "sri": k.sri, "mrm": k.mrm, "crm": k.crm, "vev": k.vev, "T_rhp": k.t_rhp,
        "horizons": json.loads(k.horizons_json),
        "costs": json.loads(k.costs_json),
        "created_at": k.created_at.isoformat(),
    }


@router.post("/save", status_code=201)
def save_kid(
    req: KidSaveRequest,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    if not req.indicative_id and not req.deal_id:
        raise HTTPException(422, "indicative_id ou deal_id requis.")
    if req.indicative_id:
        ind = session.get(Indicative, req.indicative_id)
        if not ind or ind.user_id != current.id:
            raise HTTPException(404, "Indicatif introuvable")
    if req.deal_id:
        deal = session.get(Deal, req.deal_id)
        if not deal or deal.user_id != current.id:
            raise HTTPException(404, "Deal introuvable")

    rec = KidRecord(
        indicative_id=req.indicative_id, deal_id=req.deal_id, user_id=current.id,
        product_title=req.product_title,
        sri=req.sri, mrm=req.mrm, crm=req.crm, vev=req.vev, t_rhp=req.T_rhp,
        horizons_json=json.dumps(req.horizons), costs_json=json.dumps(req.costs),
    )
    session.add(rec)
    session.commit()
    session.refresh(rec)
    return _kid_record_row(rec)


@router.get("/records")
def list_kid_records(
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    indicative_id: Optional[int] = None,
    deal_id: Optional[int] = None,
):
    if not indicative_id and not deal_id:
        raise HTTPException(422, "indicative_id ou deal_id requis.")
    q = select(KidRecord).where(KidRecord.user_id == current.id)
    if indicative_id:
        q = q.where(KidRecord.indicative_id == indicative_id)
    if deal_id:
        q = q.where(KidRecord.deal_id == deal_id)
    rows = session.exec(q.order_by(KidRecord.created_at.desc())).all()
    return [_kid_record_row(r) for r in rows]
