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
from ..db.models import Portfolio, Deal, User, Counterparty, position_sign
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

def _canonical_pair(name_to_ticker: dict, n1: str, n2: str) -> tuple[str, str]:
    """Turn a deal-local corr_pairs key ("Amazon / LVMH") into a (bucket_key,
    label) pair that's the same across deals regardless of index ordering or
    how that deal happened to name its underlyings — same ticker->catalog
    resolution as the per_underlying bucketing above, just applied to both
    sides and sorted so {A,B} and {B,A} land in the same bucket."""
    t1, t2 = name_to_ticker.get(n1, ""), name_to_ticker.get(n2, "")
    k1, k2 = _TICKER_TO_KEY.get(t1, t1 or n1), _TICKER_TO_KEY.get(t2, t2 or n2)
    l1, l2 = _TICKER_TO_LABEL.get(t1, n1), _TICKER_TO_LABEL.get(t2, n2)
    if k1 <= k2:
        return f"{k1}|{k2}", f"{l1} / {l2}"
    return f"{k2}|{k1}", f"{l2} / {l1}"


def _aggregate_risk(deals: list[Deal], session: Session) -> dict:
    per_underlying: dict[str, dict] = {}
    corr_pairs: dict[str, dict] = {}
    scalar = {"theta": 0.0, "rho": 0.0}
    deals_included, deals_missing_greeks, deals_stale = [], [], []
    deals_missing_theta: list[dict] = []
    oldest_computed_at = None
    nominal_total_eur = 0.0
    now = datetime.utcnow()

    for d in deals:
        # Nominal is known regardless of whether Greeks were ever computed —
        # unlike the sensitivities below, it must not wait on deals_missing_greeks.
        fx = get_fx_series(d.devise, "EUR")
        fx_rate = float(fx.iloc[-1]) if not fx.empty else 1.0
        # Unsigned on purpose: this is the book's gross size, the denominator
        # of every percentage below. A long and a short of the same size are
        # two positions to fund, not zero.
        nominal_total_eur += d.nominal * fx_rate

        if not d.greeks_computed_at:
            deals_missing_greeks.append({"id": d.id, "reference": d.reference})
            continue

        # Signed exposure factor: a sold product carries the opposite risk of
        # the same product held. Without it a hedge adds to what it hedges.
        w = position_sign(d) * d.nominal * fx_rate

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
                    amt = v * w
                    bucket[out_key] += amt
                    contrib[out_key] = amt
            bucket["contributions"].append(contrib)

        # Correlation Greek (compute_greeks' corr_i_j, cross-gamma to a rise
        # in the correlation between two of a basket's underlyings) — the
        # one sensitivity a family-office user can't intuit on their own
        # (see deals.py's per-deal computation), but never before summed
        # across the book: a worst-of-heavy book's biggest correlation
        # exposure might be a pair that no single deal shows large on its
        # own. Same *0.01 rescale as rho and for the same reason: the raw
        # Greek is "per 1.0 (100pts) of correlation", nobody reads a risk
        # number in units that large — per 1pt matches the Chocs tab's own
        # corr_shock_pts convention, so the two numbers are comparable.
        for pair_key, v in (greeks.get("corr_pairs") or {}).items():
            parts = pair_key.split(" / ")
            if len(parts) != 2 or v is None:
                continue
            key, label = _canonical_pair(name_to_ticker, parts[0], parts[1])
            bucket = corr_pairs.setdefault(key, {"label": label, "corr_eur": 0.0, "contributions": []})
            amt = v * 0.01 * w
            bucket["corr_eur"] += amt
            bucket["contributions"].append({"deal_id": d.id, "reference": d.reference, "corr_eur": amt})

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
                scalar[greek_name] += v * w * _SCALE[greek_name]

        # A deal whose theta could not be rolled forward exactly (fixing window
        # or realized-vol script) reports None rather than a wrong number. The
        # book total is then a partial sum, and saying so beats letting it pass
        # for the whole book's decay.
        if (greeks.get("scalar") or {}).get("theta") is None:
            deals_missing_theta.append({
                "id": d.id, "reference": d.reference,
                "reason": (greeks.get("theta_event") or {}).get("reason"),
            })

        deals_included.append({"id": d.id, "reference": d.reference})
        if oldest_computed_at is None or d.greeks_computed_at < oldest_computed_at:
            oldest_computed_at = d.greeks_computed_at
        if (now - d.greeks_computed_at) > timedelta(days=_STALE_DAYS):
            deals_stale.append({"id": d.id, "reference": d.reference,
                                 "greeks_computed_at": d.greeks_computed_at.isoformat()})

    return {
        "deals_included": deals_included,
        "deals_missing_greeks": deals_missing_greeks,
        "deals_missing_theta": deals_missing_theta,
        "deals_stale": deals_stale,
        "nominal_total_eur": nominal_total_eur,
        "per_underlying": per_underlying,
        "corr_pairs": corr_pairs,
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
        # pts of nominal → EUR, signed: a P&L explain on a sold product must
        # come out the other way round. Signing here covers every term of the
        # waterfall at once, so no branch of it can be missed.
        to_eur = position_sign(d) * d.nominal * fx_rate / 100.0

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


# ── Counterparty exposure & concentration ────────────────────────────
#
# Nominal-EUR concentration by contrepartie — same cheap "sum over already-
# known deal fields" philosophy as _aggregate_risk (no Monte Carlo, no
# dependency on Greeks ever having been computed): Deal.contrepartie is a
# free string, not a FK (see models.py:Counterparty), so grouping is a direct
# string group-by. Nominal, not live MtM, is the exposure basis on purpose —
# for a family office or a small desk with no dedicated risk function, "what
# nominal am I facing this bank for" is the number that actually gets acted
# on (a structured note is an unsecured claim on the issuer for the promised
# redemption, not today's secondary MtM), and unlike a live reprice it's
# always available with zero compute cost.
def _aggregate_exposure_by_counterparty(deals: list[Deal], session: Session) -> dict:
    by_cpty: dict[str, dict] = {}
    nominal_total_eur = 0.0

    for d in deals:
        fx = get_fx_series(d.devise, "EUR")
        fx_rate = float(fx.iloc[-1]) if not fx.empty else 1.0
        nom_eur = d.nominal * fx_rate
        nominal_total_eur += nom_eur

        key = d.contrepartie or "(non renseignée)"
        bucket = by_cpty.setdefault(key, {"nominal_eur": 0.0, "deals": []})
        bucket["nominal_eur"] += nom_eur
        bucket["deals"].append({"id": d.id, "reference": d.reference, "nominal_eur": round(nom_eur, 2)})

    limits = {c.name: c.limit_eur for c in session.exec(select(Counterparty)).all()}

    rows = []
    for name, bucket in by_cpty.items():
        limit = limits.get(name)
        pct = (bucket["nominal_eur"] / nominal_total_eur) if nominal_total_eur else None
        rows.append({
            "contrepartie": name,
            "nominal_eur": round(bucket["nominal_eur"], 2),
            "pct_of_book": round(pct, 4) if pct is not None else None,
            "deal_count": len(bucket["deals"]),
            "limit_eur": limit,
            "limit_breached": bool(limit is not None and bucket["nominal_eur"] > limit),
            "deals": sorted(bucket["deals"], key=lambda x: -x["nominal_eur"]),
        })
    rows.sort(key=lambda r: -r["nominal_eur"])

    # HHI (Herfindahl-Hirschman) on nominal shares — standard concentration
    # read: close to 1/n for an evenly split book of n counterparties, 1.0
    # for a book facing a single one. effective_n = 1/HHI is the "equivalent
    # number of equally-sized counterparties" this book behaves like — more
    # intuitive to read than a raw HHI for someone without a risk background.
    hhi = sum((r["pct_of_book"] or 0.0) ** 2 for r in rows) if nominal_total_eur else None
    effective_n = round(1 / hhi, 2) if hhi else None
    top3_pct = round(sum(r["pct_of_book"] or 0.0 for r in rows[:3]), 4) if nominal_total_eur else None

    return {
        "nominal_total_eur": round(nominal_total_eur, 2),
        "by_counterparty": rows,
        "hhi": round(hhi, 4) if hhi else None,
        "effective_n": effective_n,
        "top3_pct": top3_pct,
        "reporting_ccy": "EUR",
    }


# ── Barrier proximity ─────────────────────────────────────────────────
#
# Ranks every active deal of the scope by how close its worst-of is to the
# next barrier-looking PARAM in its booked script — reuses build_watchlist_row
# (api/deals.py, shared with Booking's Surveillance tab and the daily alert
# scheduler) so barrier detection and gap computation never diverge across
# the three call sites. Unlike _aggregate_risk (pure arithmetic over already-
# persisted greeks_json), build_watchlist_row calls out to live market data
# per deal (services/market_data.load_hist_prices, no caching) — bucket
# unexpected failures into `errors` rather than aborting the whole book,
# same discipline as _run_explain_on_book above.
def _barrier_severity(b: dict) -> str:
    """Mirrors frontend/src/utils/barriers.js barrierChipClass exactly (kept
    in sync by hand — small enough, and duplicating it here avoids a
    round-trip just for a KPI count): direction-aware, not a naive distance
    read. A KI hurts as WOF falls TO it; an autocall is favorable once WOF
    has risen above it — a green (already-called) autocall is NOT 'critique'
    even though its gap is small in absolute value."""
    g = b["gap_pts"]
    # No gap computable yet (strike not fixed) — a barrier that cannot be
    # measured is not a barrier that is safe, but it is not one to raise an
    # alarm on either.
    if g is None:
        return "ok"
    if b["kind"] == "ki":
        if g <= 5:
            return "critique"
        if g <= 15:
            return "attention"
        return "ok"
    if b["kind"] == "autocall":
        if -5 <= g < 0:
            return "attention"
        return "ok"
    return "ok"


_SEVERITY_RANK = {"critique": 0, "attention": 1, "ok": 2}


def _deal_severity(barriers: list[dict]) -> str:
    if not barriers:
        return "ok"
    return min((_barrier_severity(b) for b in barriers), key=lambda s: _SEVERITY_RANK[s])


def _aggregate_barriers(deals: list[Deal], session: Session) -> dict:
    from datetime import date
    from .deals import build_watchlist_row

    today = date.today()
    rows, errors = [], []
    for d in deals:
        try:
            row = build_watchlist_row(d, session, today)
        except Exception as e:
            errors.append({"deal_id": d.id, "reference": d.reference, "error": str(e)})
            continue
        if row["barriers"]:
            rows.append(row)

    rows.sort(key=lambda r: (
        r["min_gap"] if r["min_gap"] is not None else 1e9,
        r["days_to_next"] if r["days_to_next"] is not None else 1e9,
    ))

    counts = {"critique": 0, "attention": 0, "ok": 0}
    for r in rows:
        counts[_deal_severity(r["barriers"])] += 1

    return {
        "rows": rows,
        "errors": errors,
        "counts": counts,
    }


@router.get("/barriers-global")
def barriers_global(
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    """Barrier proximity ranked across every active deal of the user, across
    all of their portfolios — same 'always the true total' contract as
    /risk-global."""
    deals = session.exec(
        select(Deal).where(Deal.user_id == current.id, Deal.status == "actif")
    ).all()
    payload = _aggregate_barriers(list(deals), session)
    payload["scope"] = "global"
    return payload


@router.get("/{portfolio_id}/barriers")
def portfolio_barriers(
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
    payload = _aggregate_barriers(list(deals), session)
    payload["scope"] = "portfolio"
    payload["portfolio_id"] = portfolio_id
    payload["name"] = p.name
    return payload


@router.get("/exposure-by-counterparty")
def exposure_by_counterparty_global(
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    """Concentration by counterparty across every active deal of the user,
    across all of their portfolios — same 'always the true total' contract
    as /risk-global."""
    deals = session.exec(
        select(Deal).where(Deal.user_id == current.id, Deal.status == "actif")
    ).all()
    payload = _aggregate_exposure_by_counterparty(list(deals), session)
    payload["scope"] = "global"
    return payload


@router.get("/{portfolio_id}/exposure-by-counterparty")
def exposure_by_counterparty_portfolio(
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
    payload = _aggregate_exposure_by_counterparty(list(deals), session)
    payload["scope"] = "portfolio"
    payload["portfolio_id"] = portfolio_id
    payload["name"] = p.name
    return payload
