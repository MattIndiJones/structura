"""User-defined portfolios (risk-aggregation buckets) and Greeks aggregation
across the deals they contain. See PLAN squishy-baking-sedgewick.

CRUD mirrors folders.py (user-scoped organizational bucket). The aggregation
itself is pure arithmetic over immutable, date-matched GREEKS valuation runs
(api/deals.py POST /{id}/greeks) — no Monte Carlo here, cheap enough to run
on every screen load. What can be expensive is producing those per-deal
Greeks, which stays an explicit action in the frontend."""
from __future__ import annotations
import json
import math
from itertools import combinations
from datetime import date, datetime, timedelta
from typing import Annotated, Optional, Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select
from ..db.database import get_session
from ..db.models import (
    Portfolio, Deal, DealPortfolioMembership, ShockRun, User, Entity,
    Counterparty, ValuationRun, position_sign,
)
from .auth import get_current_user
from ..services.business_access import can_read_organization_record, visible_deals
from .admin import _CATALOG
from .deals import MtmExplainRequest
from ..core.amc_prices import fx_quote_to
from ..core.risk_lifecycle import deal_risk_state, terminal_dates_by_deal
from ..core.valuation_runs import current_fixings_match
from ..core.risk_scope import DataScope, select_risk_deals, risk_scope_metadata

router = APIRouter(prefix="/api/portfolios", tags=["portfolios"])

_STALE_DAYS = 7   # Valuation-run age; market observation quality has its own policy.

_TICKER_TO_KEY = {c["ticker"]: c["key"] for c in _CATALOG}
_TICKER_TO_LABEL = {c["ticker"]: c["label"] for c in _CATALOG}

_REPORTING_CCY = "EUR"


def _fx_to_reporting(devise: str | None,
                     asof: date | str | None = None, *, coverage: dict | None = None) -> float | None:
    """Rate towards the reporting currency — None when genuinely unknown.
    See core/amc_prices.fx_rate_to for why 1.0 and None must stay distinct."""
    key = devise or _REPORTING_CCY
    quote = coverage.get(key) if coverage is not None else None
    if quote is None:
        quote = fx_quote_to(devise, _REPORTING_CCY, asof=asof)
    if coverage is not None:
        coverage[key] = quote
    return quote['rate']


def _fx_missing_row(d: Deal) -> dict:
    return {"id": d.id, "reference": d.reference, "devise": d.devise}


class PortfolioCreate(BaseModel):
    name: str
    # An administrator may create the portfolio for the owner of the deals it
    # will contain. Ordinary users are always scoped to their own account.
    user_id: Optional[int] = None


class PortfolioRename(BaseModel):
    name: str


def _portfolio_row(
    p: Portfolio,
    deal_count: int,
    owner_username: str | None = None,
    owner_entity_name: str | None = None,
) -> dict:
    return {
        "id": p.id, "name": p.name,
        "user_id": p.user_id,
        "owner_username": owner_username,
        "owner_entity_name": owner_entity_name,
        "is_default": p.is_default,
        "created_at": p.created_at.isoformat(),
        "deal_count": deal_count,
    }


def _is_admin(user: User) -> bool:
    return getattr(user, "role", "user") == "admin"


def _active_deals_statement(current: User):
    statement = select(Deal).where(Deal.status == "actif")
    return statement


def _all_deals_statement(current: User):
    statement = select(Deal)
    return statement


def _portfolio_accessible(p: Portfolio | None, current: User) -> bool:
    return can_read_organization_record(p, current)


def _portfolio_deals(
    session: Session,
    portfolio_id: int,
    statuses: tuple[str, ...] | None = None,
    *, current: User | None = None,
) -> list[Deal]:
    """Load members once, deduplicated by economic deal identity.

    The legacy pointer fallback exists only for databases and fixtures which
    have not run the one-time membership backfill yet.
    """
    statement = (
        select(Deal)
        .join(
            DealPortfolioMembership,
            DealPortfolioMembership.deal_id == Deal.id,
        )
        .where(DealPortfolioMembership.portfolio_id == portfolio_id)
    )
    if statuses:
        statement = statement.where(Deal.status.in_(statuses))
    by_id = {deal.id: deal for deal in session.exec(statement).all()}

    legacy_statement = select(Deal).where(Deal.portfolio_id == portfolio_id)
    if statuses:
        legacy_statement = legacy_statement.where(Deal.status.in_(statuses))
    for deal in session.exec(legacy_statement).all():
        by_id.setdefault(deal.id, deal)
    rows = list(by_id.values())
    return visible_deals(session, rows, current) if current is not None else rows


@router.get("")
def list_portfolios(
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    data_scope: DataScope = "PRODUCTION",
):
    statement = select(Portfolio)
    portfolios = session.exec(statement).all()
    rows = []
    for p in portfolios:
        if not _portfolio_accessible(p, current):
            continue
        owner = session.get(User, p.user_id)
        entity = session.get(Entity, owner.entity_id) if owner and owner.entity_id else None
        # The same deal may appear in several portfolios. Each badge counts
        # the distinct live positions in that view.
        n = len(select_risk_deals(_portfolio_deals(session, p.id, ("actif",), current=current), data_scope))
        rows.append(_portfolio_row(
            p,
            n,
            owner.username if owner else f"Compte #{p.user_id}",
            entity.name if entity else None,
        ))
    for row in rows:
        row["data_scope"] = data_scope
    return sorted(rows, key=lambda r: (
        r["owner_username"] if _is_admin(current) else "",
        r["name"],
    ))


@router.post("", status_code=201)
def create_portfolio(
    body: PortfolioCreate,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    name = body.name.strip()
    if not name:
        raise HTTPException(422, "Le nom du portefeuille est obligatoire")
    target_user_id = body.user_id if _is_admin(current) and body.user_id is not None else current.id
    if not _is_admin(current) and body.user_id not in {None, current.id}:
        raise HTTPException(403, "Vous ne pouvez créer un portefeuille que pour votre compte")
    owner = session.get(User, target_user_id)
    if not owner:
        raise HTTPException(404, "Compte propriétaire introuvable")
    p = Portfolio(name=name, user_id=target_user_id, entity_id=owner.entity_id)
    session.add(p)
    session.commit()
    session.refresh(p)
    entity = session.get(Entity, owner.entity_id) if owner.entity_id else None
    return _portfolio_row(p, 0, owner.username, entity.name if entity else None)


@router.put("/{portfolio_id}")
def rename_portfolio(
    portfolio_id: int,
    body: PortfolioRename,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    p = session.get(Portfolio, portfolio_id)
    if not p or (not _is_admin(current) and p.user_id != current.id):
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
    if not p or (not _is_admin(current) and p.user_id != current.id):
        raise HTTPException(404, "Portefeuille introuvable")
    # A portfolio is a view. Deleting it detaches its memberships only; deals
    # and valuation history remain intact. Historical shock runs are kept but
    # detached so their JSON snapshot remains available without blocking the
    # foreign-key deletion.
    memberships = session.exec(select(DealPortfolioMembership).where(
        DealPortfolioMembership.portfolio_id == portfolio_id)).all()
    for membership in memberships:
        session.delete(membership)
    legacy_members = session.exec(select(Deal).where(
        Deal.portfolio_id == portfolio_id)).all()
    for deal in legacy_members:
        deal.portfolio_id = None
        session.add(deal)
    runs = session.exec(select(ShockRun).where(
        ShockRun.portfolio_id == portfolio_id)).all()
    for run in runs:
        run.portfolio_id = None
        session.add(run)
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


def _greeks_valuation_date(payload: dict) -> str | None:
    """Read the explicit date, with a safe bridge for pre-migration runs."""
    if payload.get("valuation_date"):
        return str(payload["valuation_date"])
    data = (payload.get("market_used") or {}).get("data") or {}
    history = data.get("contractual_history") or {}
    return history.get("requested_end") or data.get("requested_asof")


def _parsed_computed_at(payload: dict, fallback: datetime | None) -> datetime | None:
    raw = payload.get("computed_at")
    if raw:
        try:
            return datetime.fromisoformat(str(raw).replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            pass
    return fallback


def _greeks_snapshots(
    deals: list[Deal], session: Session, valuation_date: date,
) -> dict[int, tuple[dict, datetime | None]]:
    """Latest immutable Greek snapshot matching the selected valuation date."""
    target = valuation_date.isoformat()
    snapshots: dict[int, tuple[dict, datetime | None]] = {}
    timestamps: dict[int, datetime] = {}

    for deal in deals:
        if not deal.greeks_json:
            continue
        try:
            payload = json.loads(deal.greeks_json)
        except (TypeError, json.JSONDecodeError):
            continue
        if _greeks_valuation_date(payload) != target:
            continue
        payload_version = payload.get("contract_version")
        if ((payload_version is None and deal.contract_version != 1)
                or (payload_version is not None
                    and payload_version != deal.contract_version)):
            continue
        source = session.get(ValuationRun, payload.get("valuation_run_id")) if payload.get("valuation_run_id") else None
        if not current_fixings_match(session, source or ValuationRun(
                deal_id=deal.id, result_json=deal.greeks_json)):
            continue
        computed_at = _parsed_computed_at(payload, deal.greeks_computed_at)
        snapshots[deal.id] = (payload, computed_at)
        timestamps[deal.id] = computed_at or datetime.min

    deal_ids = [deal.id for deal in deals if deal.id is not None]
    if not deal_ids:
        return snapshots
    deal_versions = {deal.id: deal.contract_version for deal in deals}
    runs = session.exec(
        select(ValuationRun).where(
            ValuationRun.deal_id.in_(deal_ids),
            ValuationRun.run_type == "GREEKS",
        ).order_by(ValuationRun.created_at.desc(), ValuationRun.id.desc())
    ).all()
    for run in runs:
        if run.contract_version != deal_versions.get(run.deal_id):
            continue
        if run.deal_id in snapshots and timestamps[run.deal_id] > run.created_at:
            continue
        try:
            payload = json.loads(run.result_json)
        except (TypeError, json.JSONDecodeError):
            continue
        if _greeks_valuation_date(payload) != target:
            continue
        if not current_fixings_match(session, run):
            continue
        payload["valuation_run_id"] = run.id
        computed_at = _parsed_computed_at(payload, run.created_at)
        snapshots[run.deal_id] = (payload, computed_at)
        timestamps[run.deal_id] = computed_at or run.created_at
    return snapshots


def _aggregate_risk(
    deals: list[Deal], session: Session, valuation_date: date | None = None,
    data_scope: Literal["PRODUCTION", "UAT"] = "PRODUCTION",
) -> dict:
    valuation_date = valuation_date or date.today()
    if valuation_date > date.today():
        raise HTTPException(422, "La date d’analyse ne peut pas être future")
    terminal_dates = terminal_dates_by_deal(
        session, [deal.id for deal in deals if deal.id is not None])
    scoped_deals: list[Deal] = []
    deals_outside_scope: list[dict] = []
    for deal in deals:
        if (deal.uat_batch_id is not None) != (data_scope == "UAT"):
            deals_outside_scope.append({"id": deal.id, "reference": deal.reference,
                                        "reason": f"Hors périmètre {data_scope}"})
            continue
        active, reason = deal_risk_state(
            deal, valuation_date, terminal_dates.get(deal.id))
        if active:
            scoped_deals.append(deal)
        else:
            deals_outside_scope.append({
                "id": deal.id,
                "reference": deal.reference,
                "reason": reason,
            })
    snapshots = _greeks_snapshots(scoped_deals, session, valuation_date)
    per_underlying: dict[str, dict] = {}
    corr_pairs: dict[str, dict] = {}
    scalar = {"theta": 0.0, "rho": 0.0}
    deals_included, deals_missing_greeks, deals_stale = [], [], []
    deals_missing_theta: list[dict] = []
    deals_missing_fx: list[dict] = []
    fx_coverage = {}
    oldest_computed_at = None
    nominal_total_eur = 0.0
    now = datetime.utcnow()

    for d in scoped_deals:
        # Nominal is known regardless of whether Greeks were ever computed —
        # unlike the sensitivities below, it must not wait on deals_missing_greeks.
        fx_rate = _fx_to_reporting(d.devise, valuation_date, coverage=fx_coverage)
        if fx_rate is None:
            # Excluded from every total, not converted at parity: this deal's
            # size in EUR is unknown, and an unknown size must not be added.
            deals_missing_fx.append(_fx_missing_row(d))
            continue
        # Unsigned on purpose: this is the book's gross size, the denominator
        # of every percentage below. A long and a short of the same size are
        # two positions to fund, not zero.
        nominal_total_eur += d.nominal * fx_rate

        snapshot = snapshots.get(d.id)
        if snapshot is None:
            deals_missing_greeks.append({
                "id": d.id,
                "reference": d.reference,
                "reason": f"Aucun calcul au {valuation_date.isoformat()}",
            })
            continue

        # Signed exposure factor: a sold product carries the opposite risk of
        # the same product held. Without it a hedge adds to what it hedges.
        w = position_sign(d) * d.nominal * fx_rate

        greeks, computed_at = snapshot
        vega_scope = (greeks.get("vega_scope") or {}).get("type") or "non_documente"
        if vega_scope not in {"total", "leg_independante", "effective_local_vol"}:
            vega_scope = "non_documente"
        name_to_ticker = {u.get("name"): u.get("ticker", "")
                          for u in json.loads(d.underlyings_json)}

        for name, g in (greeks.get("per_underlying") or {}).items():
            ticker = name_to_ticker.get(name, "")
            key = _TICKER_TO_KEY.get(ticker, ticker or name)
            label = _TICKER_TO_LABEL.get(ticker, name)
            bucket = per_underlying.setdefault(key, {"label": label, "delta_eur": 0.0,
                                                       "gamma_eur": 0.0,
                                                       "vega_by_scope_eur": {
                                                           "total": 0.0,
                                                           "leg_independante": 0.0,
                                                           "effective_local_vol": 0.0,
                                                           "non_documente": 0.0,
                                                       },
                                                       "_vega_scopes": [],
                                                       "contributions": []})
            contrib = {"deal_id": d.id, "reference": d.reference,
                       "delta_eur": None, "gamma_eur": None, "vega_eur": None,
                       "vega_scope": None}
            for greek_name, out_key in (("delta", "delta_eur"), ("gamma", "gamma_eur")):
                v = g.get(greek_name)
                if v is not None and math.isfinite(v):
                    amt = v * w
                    bucket[out_key] += amt
                    contrib[out_key] = amt
            vega = g.get("vega")
            if vega is not None and math.isfinite(vega):
                amt = vega * w
                bucket["vega_by_scope_eur"][vega_scope] += amt
                if vega_scope not in bucket["_vega_scopes"]:
                    bucket["_vega_scopes"].append(vega_scope)
                contrib["vega_eur"] = amt
                contrib["vega_scope"] = vega_scope
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
            if len(parts) != 2 or v is None or not math.isfinite(v):
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
            if v is not None and math.isfinite(v):
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

        deals_included.append({
            "id": d.id,
            "reference": d.reference,
            "greeks_computed_at": computed_at.isoformat() if computed_at else None,
        })
        if computed_at and (oldest_computed_at is None or computed_at < oldest_computed_at):
            oldest_computed_at = computed_at
        if computed_at and (now - computed_at) > timedelta(days=_STALE_DAYS):
            deals_stale.append({"id": d.id, "reference": d.reference,
                                 "greeks_computed_at": computed_at.isoformat()})

    for bucket in per_underlying.values():
        scopes = bucket.pop("_vega_scopes")
        bucket["vega_scopes"] = scopes
        bucket["vega_scope_mixed"] = len(scopes) > 1
        # Compatibility for consumers that can display only one vega number:
        # publish it only when it has one unambiguous scope. A mixed number is
        # economically undefined, so None is safer than a plausible-looking sum.
        bucket["vega_eur"] = (
            bucket["vega_by_scope_eur"][scopes[0]] if len(scopes) == 1 else None
        )

    # Keep the latest run as one coherent snapshot. Never fill a missing
    # metric from an older market state. Partial sums are separate evidence.
    metric_coverage = {name: {"required": 0, "available": 0, "missing": [], "sources": []}
                       for name in ("delta", "gamma", "vega", "theta", "rho", "corr")}
    bucket_counts = {}
    for deal in scoped_deals:
        snapshot = snapshots.get(deal.id)
        payload, stamp = snapshot if snapshot else ({}, None)
        source = {"deal_id": deal.id, "reference": deal.reference,
                  "run_id": payload.get("valuation_run_id"),
                  "source": "VALUATION_RUN" if payload.get("valuation_run_id") else "LEGACY_CACHE",
                  "computed_at": stamp.isoformat() if stamp else None,
                  "valuation_date": valuation_date.isoformat()}
        fx_ok = not any(row["id"] == deal.id for row in deals_missing_fx)
        underlyings = json.loads(deal.underlyings_json or "[]")
        names = {u.get("name"): u.get("ticker", "") for u in underlyings}

        def register(metric, value, factor=None):
            entry = metric_coverage[metric]
            entry["required"] += 1
            present = fx_ok and value is not None and math.isfinite(value)
            if present:
                entry["available"] += 1
                entry["sources"].append({**source, "factor": factor})
            else:
                entry["missing"].append({**source, "factor": factor,
                    "reason": "FX indisponible" if not fx_ok else "Métrique absente du dernier calcul valable"})
            return present

        for u in underlyings:
            name, ticker = u.get("name"), u.get("ticker", "")
            key = _TICKER_TO_KEY.get(ticker, ticker or name)
            bucket = per_underlying.setdefault(key, {"label": _TICKER_TO_LABEL.get(ticker, name),
                "delta_eur": 0., "gamma_eur": 0., "vega_eur": None,
                "vega_by_scope_eur": {}, "vega_scopes": [], "vega_scope_mixed": False, "contributions": []})
            counts = bucket_counts.setdefault(key, {m: [0, 0] for m in ("delta", "gamma", "vega")})
            for metric in counts:
                counts[metric][0] += 1
                counts[metric][1] += register(metric, (payload.get("per_underlying", {}).get(name) or {}).get(metric), key)
        for metric in ("theta", "rho"):
            register(metric, (payload.get("scalar") or {}).get(metric))
        for a, b in combinations(names, 2):
            key, label = _canonical_pair(names, a, b)
            values = payload.get("corr_pairs") or {}
            present = register("corr", values.get(f"{a} / {b}", values.get(f"{b} / {a}")), key)
            bucket = corr_pairs.setdefault(key, {"label": label, "corr_eur": 0., "contributions": []})
            bucket.setdefault("coverage", {"required": 0, "available": 0})
            bucket["coverage"]["required"] += 1
            bucket["coverage"]["available"] += present
    for metric, coverage in metric_coverage.items():
        required, available = coverage["required"], coverage["available"]
        coverage.update(status="NOT_APPLICABLE" if not required else "COMPLETE" if available == required else "PARTIAL" if available else "UNAVAILABLE",
                        coverage_pct=100 * available / required if required else None,
                        basis="required factor/metric components in requested scope")
        if metric in scalar:
            coverage["available_sum_eur"] = scalar[metric] if available else None
            if available != required or not required:
                scalar[metric] = None
    for key, counts in bucket_counts.items():
        bucket = per_underlying[key]
        bucket["coverage"] = {}
        for metric, (required, available) in counts.items():
            field = f"{metric}_eur"
            bucket[f"available_{field}"] = bucket.get(field) if available else None
            bucket["coverage"][metric] = {"required": required, "available": available,
                                           "coverage_pct": 100 * available / required}
            if available != required:
                bucket[field] = None
    for bucket in corr_pairs.values():
        coverage = bucket.get("coverage", {})
        bucket["available_corr_eur"] = bucket["corr_eur"] if coverage.get("available") else None
        if coverage.get("required") != coverage.get("available"):
            bucket["corr_eur"] = None

    return {
        "deals_included": deals_included,
        "deals_missing_greeks": deals_missing_greeks,
        "deals_outside_scope": deals_outside_scope,
        "deals_missing_theta": deals_missing_theta,
        "deals_stale": deals_stale,
        # Positions left out because their currency could not be converted.
        # Non-empty means every total below is partial — say so on screen.
        "deals_missing_fx": deals_missing_fx,
        "fx_coverage": list(fx_coverage.values()),
        "nominal_total_eur": nominal_total_eur,
        "per_underlying": per_underlying,
        "corr_pairs": corr_pairs,
        "scalar": scalar,
        "metric_coverage": metric_coverage,
        "data_scope": data_scope,
        "is_test": data_scope == "UAT",
        "oldest_computed_at": oldest_computed_at.isoformat() if oldest_computed_at else None,
        "reporting_ccy": "EUR",
        "valuation_date": valuation_date.isoformat(),
    }


@router.get("/risk-global")
def risk_global(
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    valuation_date: date | None = None,
    data_scope: Literal["PRODUCTION", "UAT"] = "PRODUCTION",
):
    """Risk aggregated over deals whose optional exposure existed as of date."""
    deals = visible_deals(session, session.exec(_all_deals_statement(current)).all(), current)
    payload = _aggregate_risk(list(deals), session, valuation_date, data_scope)
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
              "Effet dividendes": "dividendes", "Effet volatilité": "vol", "Effet corrélation": "corr"}


def _run_explain_on_book(deals: list[Deal], session: Session, n_paths: int,
                         body: MtmExplainRequest) -> dict:
    from .deals import _explain_core

    steps = {"temps": 0.0, "spot": 0.0, "dividendes": 0.0, "vol": 0.0, "corr": 0.0}
    has_corr = False
    contributions, skipped, errors = [], [], []
    fx_coverage = {}
    delta_mtm_eur = flows_eur = residual_eur = 0.0
    nominal_total_eur = 0.0

    for d in deals:
        fx_rate = _fx_to_reporting(d.devise, body.date2, coverage=fx_coverage)
        if fx_rate is None:
            # Same treatment as a deal that cannot be repriced: named in
            # `skipped`, absent from the EUR totals. Converting at parity here
            # would break the telescoping the whole waterfall relies on.
            skipped.append({"deal_id": d.id, "reference": d.reference,
                            "reason": f"Taux de change {d.devise}/EUR indisponible — "
                                      f"position exclue des totaux."})
            continue
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

        # Display precision in points must not become an EUR accounting input.
        # Archived legacy payloads remain readable at their original precision.
        measured = payload.get("unrounded") or payload
        contrib_steps = {}
        for s in measured["steps"]:
            key = _STEP_KEYS.get(s["label"])
            if key is None:
                continue
            eur = s["delta_pts"] * to_eur
            steps[key] += eur
            contrib_steps[key] = round(eur, 2)
            if key == "corr":
                has_corr = True
        residual_eur += measured["residual_pts"] * to_eur
        flows_eur += measured["flows_total_pts"] * to_eur
        delta_mtm_eur += measured["delta_pts"] * to_eur

        contributions.append({
            "deal_id": d.id, "reference": d.reference,
            "date1": payload["date1"], "date2": payload["date2"],
            "mtm1": payload["mtm1"], "mtm2": payload["mtm2"],
            "delta_mtm_eur": round(measured["delta_pts"] * to_eur, 2),
            "flows_eur": round(measured["flows_total_pts"] * to_eur, 2),
            "pnl_eur": round(measured["pnl_total_pts"] * to_eur, 2),
            "residual_eur": round(measured["residual_pts"] * to_eur, 2),
            "steps_eur": contrib_steps,
        })

    pnl_total_eur = delta_mtm_eur + flows_eur
    pct = (pnl_total_eur / nominal_total_eur * 100.0) if nominal_total_eur else None
    waterfall = [
        {"key": "temps", "label": "Effet temps", "delta_eur": round(steps["temps"], 2)},
        {"key": "spot", "label": "Effet spot", "delta_eur": round(steps["spot"], 2)},
        {"key": "dividendes", "label": "Effet dividendes", "delta_eur": round(steps["dividendes"], 2)},
        {"key": "vol", "label": "Effet volatilité", "delta_eur": round(steps["vol"], 2)},
    ]
    if has_corr:
        waterfall.append({"key": "corr", "label": "Effet corrélation",
                          "delta_eur": round(steps["corr"], 2)})
    return {
        "cash_basis": "CONTRACTUAL_PAYMENT_DATE",
        "attribution_version": "pnl-payment-v2",
        "nominal_total_eur": round(nominal_total_eur, 2),
        "steps": waterfall,
        "residual_eur": round(residual_eur, 2),
        "flows_total_eur": round(flows_eur, 2),
        "delta_mtm_eur": round(delta_mtm_eur, 2),
        "pnl_total_eur": round(pnl_total_eur, 2),
        "pct_impact": round(pct, 3) if pct is not None else None,
        "contributions": contributions,
        "fx_coverage": list(fx_coverage.values()),
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
    data_scope: DataScope = "PRODUCTION",
):
    """P&L explain aggregated across every active deal of the user. date1
    omitted means each deal explains from its own value date (P&L depuis
    l'origine) ; date2 omitted means today."""
    deals = visible_deals(session, session.exec(_active_deals_statement(current)).all(), current)
    deals = select_risk_deals(deals, data_scope)
    result = _run_explain_on_book(list(deals), session, n_paths,
                                  body or MtmExplainRequest())
    result["scope"] = "global"
    result.update(risk_scope_metadata(deals, data_scope))
    return result


@router.post("/{portfolio_id}/pnl-explain")
def pnl_explain_portfolio(
    portfolio_id: int,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    n_paths: int = 20000,
    body: Optional[MtmExplainRequest] = None,
    data_scope: DataScope = "PRODUCTION",
):
    p = session.get(Portfolio, portfolio_id)
    if not _portfolio_accessible(p, current):
        raise HTTPException(404, "Portefeuille introuvable")
    deals = _portfolio_deals(session, portfolio_id, ("actif",), current=current)
    deals = select_risk_deals(deals, data_scope)
    result = _run_explain_on_book(list(deals), session, n_paths,
                                  body or MtmExplainRequest())
    result["scope"] = "portfolio"
    result["portfolio_id"] = portfolio_id
    result["name"] = p.name
    result.update(risk_scope_metadata(deals, data_scope))
    return result


@router.get("/{portfolio_id}/risk")
def portfolio_risk(
    portfolio_id: int,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    valuation_date: date | None = None,
    data_scope: Literal["PRODUCTION", "UAT"] = "PRODUCTION",
):
    p = session.get(Portfolio, portfolio_id)
    if not _portfolio_accessible(p, current):
        raise HTTPException(404, "Portefeuille introuvable")
    deals = _portfolio_deals(session, portfolio_id, current=current)
    payload = _aggregate_risk(list(deals), session, valuation_date, data_scope)
    payload["scope"] = "portfolio"
    payload["portfolio_id"] = portfolio_id
    payload["name"] = p.name
    return payload


# ── Counterparty exposure & concentration ────────────────────────────
#
# Nominal-EUR monitoring is separate from blocking CCR limits. Legal IDs own
# aggregation and limits; labels remain descriptive snapshots. Unqualified
# legacy positions and D01 exceptions remain visible without inferred IDs.
def _aggregate_exposure_by_counterparty(deals: list[Deal], session: Session) -> dict:
    by_cpty: dict[str, dict] = {}
    catalog = {item.id: item for item in session.exec(select(Counterparty)).all()}
    requiring_qualification = []
    deals_missing_fx: list[dict] = []
    fx_coverage = {}
    nominal_total_eur = 0.0

    for d in deals:
        legal = catalog.get(d.counterparty_id)
        key = f"counterparty:{d.counterparty_id}" if d.counterparty_id is not None else f"unqualified:{d.contrepartie or '(non renseignée)'}"
        identity_status = ("ACTIVE" if legal.active else "INACTIVE") if legal else (
            "REFERENCE_MISSING" if d.counterparty_id is not None else "UNQUALIFIED")
        bucket = by_cpty.setdefault(key, {"counterparty_id": d.counterparty_id,
            "contrepartie": legal.name if legal else d.contrepartie or "(non renseignée)",
            "identity_status": identity_status, "historical_names": set(),
            "limit_eur": legal.limit_eur if legal else None,
            "nominal_eur": 0.0, "deals": [], "missing_fx_count": 0})
        bucket["historical_names"].add(d.contrepartie)
        if legal is None:
            requiring_qualification.append({"id": d.id, "reference": d.reference,
                "counterparty_id": d.counterparty_id, "contrepartie": d.contrepartie,
                "identity_status": identity_status,
                "administrator_exception": bool(d.legal_identity_exception_json),
                "credit_status": "NOT_ASSESSED"})
        fx_rate = _fx_to_reporting(d.devise, coverage=fx_coverage)
        if fx_rate is None:
            # A counterparty limit is checked against a number. Understating
            # an exposure because a rate was missing is the one failure mode
            # this screen exists to prevent, so the position is named instead.
            deals_missing_fx.append(_fx_missing_row(d))
            bucket["missing_fx_count"] += 1
            continue
        exposure_fraction = (
            float(d.settlement_amount or 0.0)
            if d.status == "en_reglement" else 1.0
        )
        nom_eur = d.nominal * exposure_fraction * fx_rate
        nominal_total_eur += nom_eur

        bucket["nominal_eur"] += nom_eur
        bucket["deals"].append({
            "id": d.id, "reference": d.reference,
            "contrepartie": d.contrepartie,
            "nominal_eur": round(nom_eur, 2), "status": d.status,
            "exposure_basis": ("settlement_amount"
                               if d.status == "en_reglement" else "nominal"),
        })

    rows = []
    for key, bucket in by_cpty.items():
        limit = bucket["limit_eur"]
        breached = bool(limit is not None and bucket["nominal_eur"] > limit)
        qualified = bucket["identity_status"] in {"ACTIVE", "INACTIVE"}
        limit_status = ("UNQUALIFIED" if not qualified else "INCOMPLETE" if bucket["missing_fx_count"]
                        else "NO_LIMIT" if limit is None else "BREACH" if breached else "OK")
        pct = (bucket["nominal_eur"] / nominal_total_eur) if nominal_total_eur else None
        rows.append({
            "identity_key": key,
            "counterparty_id": bucket["counterparty_id"],
            "contrepartie": bucket["contrepartie"],
            "identity_status": bucket["identity_status"],
            "historical_names": sorted(bucket["historical_names"]),
            "nominal_eur": round(bucket["nominal_eur"], 2),
            "pct_of_book": round(pct, 4) if pct is not None else None,
            "deal_count": len(bucket["deals"]) + bucket["missing_fx_count"],
            "limit_eur": limit,
            "limit_breached": breached if qualified and (not bucket["missing_fx_count"] or breached) else None,
            "limit_status": limit_status,
            "missing_fx_count": bucket["missing_fx_count"],
            "deals": sorted(bucket["deals"], key=lambda x: -x["nominal_eur"]),
        })
    rows.sort(key=lambda r: -r["nominal_eur"])

    # HHI (Herfindahl-Hirschman) on nominal shares — standard concentration
    # read: close to 1/n for an evenly split book of n counterparties, 1.0
    # for a book facing a single one. effective_n = 1/HHI is the "equivalent
    # number of equally-sized counterparties" this book behaves like — more
    # intuitive to read than a raw HHI for someone without a risk background.
    complete = not requiring_qualification and not deals_missing_fx
    hhi = sum((r["pct_of_book"] or 0.0) ** 2 for r in rows) if nominal_total_eur and complete else None
    effective_n = round(1 / hhi, 2) if hhi else None
    top3_pct = round(sum(r["pct_of_book"] or 0.0 for r in rows[:3]), 4) if nominal_total_eur and complete else None

    return {
        "nominal_total_eur": round(nominal_total_eur, 2),
        "by_counterparty": rows,
        "coverage_complete": complete,
        "fx_coverage": list(fx_coverage.values()),
        "deals_requiring_qualification": requiring_qualification,
        "limit_basis": "NOMINAL_EUR_MONITORING",
        "hhi": round(hhi, 4) if hhi else None,
        "effective_n": effective_n,
        "top3_pct": top3_pct,
        # Non-empty: the exposures and the limit checks above cover only part
        # of the book. A breach could be hiding in what is listed here.
        "deals_missing_fx": deals_missing_fx,
        "reporting_ccy": _REPORTING_CCY,
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
    if b["kind"] == "coupon":
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
    data_scope: DataScope = "PRODUCTION",
):
    """Barrier proximity ranked across every active deal of the user, across
    all of their portfolios — same 'always the true total' contract as
    /risk-global."""
    deals = visible_deals(session, session.exec(_active_deals_statement(current)).all(), current)
    deals = select_risk_deals(deals, data_scope)
    payload = _aggregate_barriers(list(deals), session)
    payload["scope"] = "global"
    payload.update(risk_scope_metadata(deals, data_scope))
    return payload


@router.get("/{portfolio_id}/barriers")
def portfolio_barriers(
    portfolio_id: int,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    data_scope: DataScope = "PRODUCTION",
):
    p = session.get(Portfolio, portfolio_id)
    if not _portfolio_accessible(p, current):
        raise HTTPException(404, "Portefeuille introuvable")
    deals = _portfolio_deals(session, portfolio_id, ("actif",), current=current)
    deals = select_risk_deals(deals, data_scope)
    payload = _aggregate_barriers(list(deals), session)
    payload["scope"] = "portfolio"
    payload["portfolio_id"] = portfolio_id
    payload["name"] = p.name
    payload.update(risk_scope_metadata(deals, data_scope))
    return payload


@router.get("/exposure-by-counterparty")
def exposure_by_counterparty_global(
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    data_scope: DataScope = "PRODUCTION",
):
    """Concentration by counterparty across every active deal of the user,
    across all of their portfolios — same 'always the true total' contract
    as /risk-global."""
    statement = select(Deal).where(Deal.status.in_(["actif", "en_reglement"]))
    deals = visible_deals(session, session.exec(statement).all(), current)
    deals = select_risk_deals(deals, data_scope)
    payload = _aggregate_exposure_by_counterparty(list(deals), session)
    payload["scope"] = "global"
    payload.update(risk_scope_metadata(deals, data_scope))
    return payload


@router.get("/{portfolio_id}/exposure-by-counterparty")
def exposure_by_counterparty_portfolio(
    portfolio_id: int,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    data_scope: DataScope = "PRODUCTION",
):
    p = session.get(Portfolio, portfolio_id)
    if not _portfolio_accessible(p, current):
        raise HTTPException(404, "Portefeuille introuvable")
    deals = _portfolio_deals(session, portfolio_id, ("actif", "en_reglement"), current=current)
    deals = select_risk_deals(deals, data_scope)
    payload = _aggregate_exposure_by_counterparty(list(deals), session)
    payload["scope"] = "portfolio"
    payload["portfolio_id"] = portfolio_id
    payload["name"] = p.name
    payload.update(risk_scope_metadata(deals, data_scope))
    return payload
