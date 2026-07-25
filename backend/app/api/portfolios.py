"""User-defined portfolios (risk-aggregation buckets) and Greeks aggregation
across the deals they contain. See PLAN squishy-baking-sedgewick.

CRUD mirrors folders.py (user-scoped organizational bucket). The aggregation
itself is pure arithmetic over each deal's already-persisted greeks_json
(api/deals.py POST /{id}/greeks) — no Monte Carlo here, cheap enough to run
on every screen load. What can be expensive is keeping the underlying
per-deal Greeks fresh, which stays an explicit action (see the frontend's
"Recalculer" loop over the existing per-deal endpoint)."""
from __future__ import annotations
import json
from datetime import datetime, timedelta
from typing import Annotated, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select
from ..db.database import get_session
from ..db.models import Portfolio, Deal, User
from .auth import get_current_user
from .admin import _CATALOG
from .deals import MtmExplainRequest
from ..core.amc_prices import get_fx_series

router = APIRouter(prefix="/api/portfolios", tags=["portfolios"])

_STALE_DAYS = 7   # same convention as Admin market-data's price staleness

_TICKER_TO_KEY = {c["ticker"]: c["key"] for c in _CATALOG}
_TICKER_TO_LABEL = {c["ticker"]: c["label"] for c in _CATALOG}


class PortfolioCreate(BaseModel):
    name: str


class PortfolioRename(BaseModel):
    name: str


def _portfolio_row(p: Portfolio, deal_count: int) -> dict:
    return {
        "id": p.id, "name": p.name,
        "is_default": p.is_default,
        "created_at": p.created_at.isoformat(),
        "deal_count": deal_count,
    }


def get_or_create_default_portfolio(session: Session, user_id: int) -> Portfolio:
    """The one portfolio every deal of this user always falls back to — a
    deal must never be left unmonitored. Created lazily on first use (at
    booking time, or by the boot-time backfill for pre-existing deals)."""
    default = session.exec(
        select(Portfolio).where(Portfolio.user_id == user_id, Portfolio.is_default == True)  # noqa: E712
    ).first()
    if default:
        return default
    default = Portfolio(name="Portefeuille par défaut", user_id=user_id, is_default=True)
    session.add(default)
    session.flush()
    return default


@router.get("")
def list_portfolios(
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    portfolios = session.exec(
        select(Portfolio).where(Portfolio.user_id == current.id)
    ).all()
    rows = []
    for p in portfolios:
        n = len(session.exec(
            select(Deal.id).where(Deal.portfolio_id == p.id)
        ).all())
        rows.append(_portfolio_row(p, n))
    return sorted(rows, key=lambda r: (not r["is_default"], r["name"]))


@router.post("", status_code=201)
def create_portfolio(
    body: PortfolioCreate,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    p = Portfolio(name=body.name.strip(), user_id=current.id)
    session.add(p)
    session.commit()
    session.refresh(p)
    return _portfolio_row(p, 0)


@router.put("/{portfolio_id}")
def rename_portfolio(
    portfolio_id: int,
    body: PortfolioRename,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    p = session.get(Portfolio, portfolio_id)
    if not p or p.user_id != current.id:
        raise HTTPException(404, "Portefeuille introuvable")
    p.name = body.name.strip()
    session.add(p)
    session.commit()
    return {"id": p.id, "name": p.name}


@router.delete("/{portfolio_id}", status_code=204)
def delete_portfolio(
    portfolio_id: int,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    p = session.get(Portfolio, portfolio_id)
    if not p or p.user_id != current.id:
        raise HTTPException(404, "Portefeuille introuvable")
    if p.is_default:
        raise HTTPException(422, "Le portefeuille par défaut ne peut pas être supprimé — "
                                  "un deal doit toujours rester rattaché à un portefeuille")
    # Deals inside are moved to the default portfolio, never left unassigned
    # nor deleted — same "detach, don't lose" logic as delete_folder
    # reparenting its children, but here there's always a home to fall back to.
    default = get_or_create_default_portfolio(session, current.id)
    members = session.exec(select(Deal).where(Deal.portfolio_id == portfolio_id)).all()
    for d in members:
        d.portfolio_id = default.id
        session.add(d)
    session.delete(p)
    session.commit()


# ── Risk aggregation ─────────────────────────────────────────────────

def _aggregate_risk(deals: list[Deal], session: Session) -> dict:
    per_underlying: dict[str, dict] = {}
    scalar = {"theta": 0.0, "rho": 0.0}
    deals_included, deals_missing_greeks, deals_stale = [], [], []
    oldest_computed_at = None
    nominal_total_eur = 0.0
    now = datetime.utcnow()

    for d in deals:
        # Nominal is known regardless of whether Greeks were ever computed —
        # unlike the sensitivities below, it must not wait on deals_missing_greeks.
        fx = get_fx_series(d.devise, "EUR")
        fx_rate = float(fx.iloc[-1]) if not fx.empty else 1.0
        nominal_total_eur += d.nominal * fx_rate

        if not d.greeks_computed_at:
            deals_missing_greeks.append({"id": d.id, "reference": d.reference})
            continue

        greeks = json.loads(d.greeks_json)
        name_to_ticker = {u.get("name"): u.get("ticker", "")
                          for u in json.loads(d.underlyings_json)}

        for name, g in (greeks.get("per_underlying") or {}).items():
            ticker = name_to_ticker.get(name, "")
            key = _TICKER_TO_KEY.get(ticker, ticker or name)
            label = _TICKER_TO_LABEL.get(ticker, name)
            bucket = per_underlying.setdefault(key, {"label": label, "delta_eur": 0.0,
                                                       "gamma_eur": 0.0, "vega_eur": 0.0,
                                                       "contributions": []})
            contrib = {"deal_id": d.id, "reference": d.reference,
                       "delta_eur": None, "gamma_eur": None, "vega_eur": None}
            for greek_name, out_key in (("delta", "delta_eur"), ("gamma", "gamma_eur"),
                                         ("vega", "vega_eur")):
                v = g.get(greek_name)
                if v is not None:
                    amt = v * d.nominal * fx_rate
                    bucket[out_key] += amt
                    contrib[out_key] = amt
            bucket["contributions"].append(contrib)

        # theta is already "per calendar day" out of compute_greeks (its finite
        # difference divides by 7 days, not by an artificial bump size — see
        # engine.py). rho is NOT: it's (price(dr=+1pt) - price(dr=-1pt)) / 0.02,
        # a true derivative dPrice/dr "per unit of r" (r itself a fraction, so
        # per 100 PERCENTAGE POINTS of rate) — the same per-100%-of-bump-scale
        # convention as delta/gamma/vega. Unlike an equity delta ("cash per 100%
        # spot move" is a standard, meaningful quantity), nobody quotes rates
        # sensitivity per 10'000bp — the desk-standard is per 100bp (1pt), hence
        # the extra *0.01 to actually match what "EUR / 1pt taux" promises.
        _SCALE = {"theta": 1.0, "rho": 0.01}
        for greek_name in ("theta", "rho"):
            v = (greeks.get("scalar") or {}).get(greek_name)
            if v is not None:
                scalar[greek_name] += v * d.nominal * fx_rate * _SCALE[greek_name]

        deals_included.append({"id": d.id, "reference": d.reference})
        if oldest_computed_at is None or d.greeks_computed_at < oldest_computed_at:
            oldest_computed_at = d.greeks_computed_at
        if (now - d.greeks_computed_at) > timedelta(days=_STALE_DAYS):
            deals_stale.append({"id": d.id, "reference": d.reference,
                                 "greeks_computed_at": d.greeks_computed_at.isoformat()})

    return {
        "deals_included": deals_included,
        "deals_missing_greeks": deals_missing_greeks,
        "deals_stale": deals_stale,
        "nominal_total_eur": nominal_total_eur,
        "per_underlying": per_underlying,
        "scalar": scalar,
        "oldest_computed_at": oldest_computed_at.isoformat() if oldest_computed_at else None,
        "reporting_ccy": "EUR",
    }


@router.get("/risk-global")
def risk_global(
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    """Risk aggregated across every active deal of the user, across all of
    their portfolios (every deal always belongs to one, at minimum the
    default portfolio) — the total book is always the true total."""
    deals = session.exec(
        select(Deal).where(Deal.user_id == current.id, Deal.status == "actif")
    ).all()
    payload = _aggregate_risk(list(deals), session)
    payload["scope"] = "global"
    return payload


# ── P&L explain aggregation ──────────────────────────────────────────
#
# Portfolio-level P&L explain: the per-deal waterfall (_explain_core, api/
# deals.py — temps/spot/vol/corr revaluations at identical seed, CRN) run
# over every active deal of the scope, each line converted from points of
# that deal's nominal into EUR and summed. Same book-traversal conventions
# as shocks._run_shock_on_book: non-repriceable deals (called between the
# two dates, booked after date 2...) land in `skipped` with the 422 detail
# as reason instead of aborting the whole book; the EUR totals telescope
# per construction since each deal's chain does.

_STEP_KEYS = {"Effet temps": "temps", "Effet spot": "spot",
              "Effet volatilité": "vol", "Effet corrélation": "corr"}


def _run_explain_on_book(deals: list[Deal], session: Session, n_paths: int,
                         body: MtmExplainRequest) -> dict:
    from .deals import _explain_core

    steps = {"temps": 0.0, "spot": 0.0, "vol": 0.0, "corr": 0.0}
    has_corr = False
    contributions, skipped, errors = [], [], []
    delta_mtm_eur = flows_eur = residual_eur = 0.0
    nominal_total_eur = 0.0

    for d in deals:
        fx = get_fx_series(d.devise, "EUR")
        fx_rate = float(fx.iloc[-1]) if not fx.empty else 1.0
        nominal_total_eur += d.nominal * fx_rate
        to_eur = d.nominal * fx_rate / 100.0   # pts of nominal → EUR

        try:
            payload, _c1, _c2 = _explain_core(d, session, n_paths, body)
        except HTTPException as e:
            skipped.append({"deal_id": d.id, "reference": d.reference,
                            "reason": e.detail})
            continue
        except Exception as e:
            errors.append({"deal_id": d.id, "reference": d.reference,
                           "error": str(e)})
            continue

        contrib_steps = {}
        for s in payload["steps"]:
            key = _STEP_KEYS.get(s["label"])
            if key is None:
                continue
            eur = s["delta_pts"] * to_eur
            steps[key] += eur
            contrib_steps[key] = round(eur, 2)
            if key == "corr":
                has_corr = True
        residual_eur += payload["residual_pts"] * to_eur
        flows_eur += payload["flows_total_pts"] * to_eur
        delta_mtm_eur += payload["delta_pts"] * to_eur

        contributions.append({
            "deal_id": d.id, "reference": d.reference,
            "date1": payload["date1"], "date2": payload["date2"],
            "mtm1": payload["mtm1"], "mtm2": payload["mtm2"],
            "delta_mtm_eur": round(payload["delta_pts"] * to_eur, 2),
            "flows_eur": round(payload["flows_total_pts"] * to_eur, 2),
            "pnl_eur": round(payload["pnl_total_pts"] * to_eur, 2),
            "residual_eur": round(payload["residual_pts"] * to_eur, 2),
            "steps_eur": contrib_steps,
        })

    pnl_total_eur = delta_mtm_eur + flows_eur
    pct = (pnl_total_eur / nominal_total_eur * 100.0) if nominal_total_eur else None
    waterfall = [
        {"key": "temps", "label": "Effet temps", "delta_eur": round(steps["temps"], 2)},
        {"key": "spot", "label": "Effet spot", "delta_eur": round(steps["spot"], 2)},
        {"key": "vol", "label": "Effet volatilité", "delta_eur": round(steps["vol"], 2)},
    ]
    if has_corr:
        waterfall.append({"key": "corr", "label": "Effet corrélation",
                          "delta_eur": round(steps["corr"], 2)})
    return {
        "nominal_total_eur": round(nominal_total_eur, 2),
        "steps": waterfall,
        "residual_eur": round(residual_eur, 2),
        "flows_total_eur": round(flows_eur, 2),
        "delta_mtm_eur": round(delta_mtm_eur, 2),
        "pnl_total_eur": round(pnl_total_eur, 2),
        "pct_impact": round(pct, 3) if pct is not None else None,
        "contributions": contributions,
        "skipped": skipped,
        "errors": errors,
        "reporting_ccy": "EUR",
    }


@router.post("/pnl-explain-global")
def pnl_explain_global(
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    n_paths: int = 20000,
    body: Optional[MtmExplainRequest] = None,
):
    """P&L explain aggregated across every active deal of the user. date1
    omitted means each deal explains from its own value date (P&L depuis
    l'origine) ; date2 omitted means today."""
    deals = session.exec(
        select(Deal).where(Deal.user_id == current.id, Deal.status == "actif")
    ).all()
    result = _run_explain_on_book(list(deals), session, n_paths,
                                  body or MtmExplainRequest())
    result["scope"] = "global"
    return result


@router.post("/{portfolio_id}/pnl-explain")
def pnl_explain_portfolio(
    portfolio_id: int,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    n_paths: int = 20000,
    body: Optional[MtmExplainRequest] = None,
):
    p = session.get(Portfolio, portfolio_id)
    if not p or p.user_id != current.id:
        raise HTTPException(404, "Portefeuille introuvable")
    deals = session.exec(
        select(Deal).where(Deal.portfolio_id == portfolio_id, Deal.status == "actif")
    ).all()
    result = _run_explain_on_book(list(deals), session, n_paths,
                                  body or MtmExplainRequest())
    result["scope"] = "portfolio"
    result["portfolio_id"] = portfolio_id
    result["name"] = p.name
    return result


@router.get("/{portfolio_id}/risk")
def portfolio_risk(
    portfolio_id: int,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    p = session.get(Portfolio, portfolio_id)
    if not p or p.user_id != current.id:
        raise HTTPException(404, "Portefeuille introuvable")
    deals = session.exec(
        select(Deal).where(Deal.portfolio_id == portfolio_id, Deal.status == "actif")
    ).all()
    payload = _aggregate_risk(list(deals), session)
    payload["scope"] = "portfolio"
    payload["portfolio_id"] = portfolio_id
    payload["name"] = p.name
    return payload
