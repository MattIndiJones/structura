"""Market-shock scenarios (spot/vol/rate/corr) — full reprice, not a linear
Greeks approximation, because barrier payoffs (autocalls, phoenix...) are too
non-linear for that (a -20% shock isn't 20x the delta). See PLAN
squishy-baking-sedgewick.

Reuses run_mc's existing bump vocabulary (spot_mult, vol_add, dr) exactly as
compute_greeks does, but with larger, named amplitudes and a full reprice
instead of a tiny bump-and-reprice derivative. Correlation shocks bypass
run_mc's corr_delta (single-pair only, built for Greeks' cross-gamma) and pass
a directly-shifted corr_matrix instead — run_mc already accepts that as a
first-class parameter, no new engine mechanism needed.

_mtm_core (api/deals.py) already builds everything a shock needs (residual
script, effective underlyings, corr, rates, N) to reprice a deal — a shock
just calls run_mc again with that same ctx, bumped. Runs are persisted
append-only (ShockRun, never updated in place — same pattern as
KidRecord/EmtRecord) since a scenario's parameters can change on the next
run and past ones should stay reconstructable."""
from __future__ import annotations
import json
import math
from typing import Annotated, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, select
from ..db.database import get_session
from ..db.models import Deal, Portfolio, ShockRun, User, position_sign
from .auth import get_current_user
from .deals import _can_access_deal, _mtm_core, MtmRequest
from ..core.amc_prices import fx_rate_to
from ..core.valuation_context import run_valuation

router = APIRouter(tags=["shocks"])


class ShockOverride(BaseModel):
    spot_shock_pct: Optional[float] = None
    vol_shock_pts: Optional[float] = None


class ShockRequest(MtmRequest):
    """Body of the shock endpoints. recalibrate/overrides/r/window_days are
    inherited from MtmRequest and set the pre-shock baseline market
    assumptions (same as a MtM/Greeks call) — the fields below are the shock
    itself, layered on top via run_mc's own bump kwargs. Global by default,
    shock_overrides lets one underlying deviate from the global amplitude."""
    spot_shock_pct: float = 0.0
    vol_shock_pts: float = 0.0
    rate_shock_bp: float = 0.0
    corr_shock_pts: float = 0.0
    shock_overrides: dict[str, ShockOverride] = Field(default_factory=dict)
    label: str = ""


class SmileUnderlyingOverride(BaseModel):
    """Optional model parameters for one named/ticker underlying.

    Values are shifts in displayed percentage points. They map to parameters
    with the same name; there is deliberately no hidden conversion from a
    generic "skew" into a SABR or Heston calibration parameter.
    """
    atm_vol_pts: Optional[float] = None
    skew_pts: Optional[float] = None
    curvature_pts: Optional[float] = None
    sabr_alpha_pts: Optional[float] = None
    sabr_rho_pts: Optional[float] = None
    sabr_nu_pts: Optional[float] = None
    heston_v0_pts: Optional[float] = None
    heston_theta_pts: Optional[float] = None
    heston_rho_pts: Optional[float] = None
    heston_xi_pts: Optional[float] = None


class SmileRiskRequest(MtmRequest):
    atm_vol_pts: float = 0.0
    skew_pts: float = 0.0
    curvature_pts: float = 0.0
    sabr_alpha_pts: float = 0.0
    sabr_rho_pts: float = 0.0
    sabr_nu_pts: float = 0.0
    heston_v0_pts: float = 0.0
    heston_theta_pts: float = 0.0
    heston_rho_pts: float = 0.0
    heston_xi_pts: float = 0.0
    underlying_overrides: dict[str, SmileUnderlyingOverride] = Field(default_factory=dict)
    label: str = ""


def _build_shock_arrays(underlyings_json: list, shock: ShockRequest,
                        norm_spots: list) -> tuple[list, list]:
    """Shocked spot vector and vol add-on.

    The shock is applied RELATIVE to where the deal actually trades: a live deal
    at 130% of its strike, shocked -10%, must be repriced at 117%, not at 90%.
    Building the multiplier from 1.0 instead repriced every live deal as though
    it were freshly struck at par — so the tab reported a non-zero impact even
    under a zero shock, because it was subtracting two different products.

    Avant le strike, aucun cas particulier n'est nécessaire et c'est voulu : le
    fixing étant simulé, le multiplicateur met à l'échelle la trajectoire ET le
    strike qu'elle constatera. Un stress -20 % ne fait donc pas décrocher un
    produit dont la protection n'a pas commencé à courir — il ne laisse que le
    déplacement du skew, nul sous un modèle invariant d'échelle. C'est
    l'homogénéité qui rend le bon chiffre, pas une branche."""
    spot_mult, vol_add = [], []
    for u, ns in zip(underlyings_json, norm_spots):
        ov = shock.shock_overrides.get(u.get("name", ""))
        spot_pct = ov.spot_shock_pct if (ov and ov.spot_shock_pct is not None) else shock.spot_shock_pct
        vol_pts = ov.vol_shock_pts if (ov and ov.vol_shock_pts is not None) else shock.vol_shock_pts
        spot_mult.append(ns * (1.0 + spot_pct / 100.0))
        vol_add.append(vol_pts / 100.0)
    return spot_mult, vol_add


def _shock_corr(corr: list, corr_shock_pts: float) -> list:
    if not corr_shock_pts:
        return corr
    delta = corr_shock_pts / 100.0
    n = len(corr)
    return [
        [1.0 if i == j else max(-0.99, min(0.99, corr[i][j] + delta)) for j in range(n)]
        for i in range(n)
    ]


def _describe_shock(shock: ShockRequest) -> str:
    if shock.label.strip():
        return shock.label.strip()
    parts = []
    if shock.spot_shock_pct:
        parts.append(f"Spot {shock.spot_shock_pct:+.0f}%")
    if shock.vol_shock_pts:
        parts.append(f"Vol {shock.vol_shock_pts:+.0f}pts")
    if shock.rate_shock_bp:
        parts.append(f"Taux {shock.rate_shock_bp:+.0f}bp")
    if shock.corr_shock_pts:
        parts.append(f"Corr {shock.corr_shock_pts:+.0f}pts")
    return " / ".join(parts) or "Choc nul"


def _run_shock_on_deal(deal: Deal, session: Session, n_paths: int, shock: ShockRequest) -> dict:
    """Full reprice under the shocked scenario. Never raises for a
    resolved-pending deal (returns a skip marker instead), so a
    portfolio-wide shock can keep going over the rest of the book."""
    mtm_payload, ctx = _mtm_core(deal, session, n_paths, shock)
    if ctx is None:
        return {"deal_id": deal.id, "reference": deal.reference, "skipped": True,
                "reason": mtm_payload.get("message", "résolution en attente")}

    # Between contractual maturity and payment the claim is known. Spot, vol
    # and correlation shocks have no effect; a parallel rate shock still moves
    # its present value under the same continuous-compounding convention.
    if ctx.get("settlement_claim"):
        price_before = float(ctx["fixed_price"])
        dr = shock.rate_shock_bp / 10000.0
        price_after = price_before * math.exp(
            -dr * float(ctx.get("time_to_payment", 0.0)))
        fx_rate = fx_rate_to(deal.devise, "EUR")
        if fx_rate is None:
            raise HTTPException(
                422, f"Taux de change {deal.devise}/EUR indisponible — l'impact en "
                     f"euros de ce choc ne peut pas être calculé pour {deal.reference}.")
        delta_pts = price_after - price_before
        return {
            "deal_id": deal.id, "reference": deal.reference, "skipped": False,
            "mtm_before": price_before, "mtm_after": price_after,
            "delta_pts": round(delta_pts, 4),
            "delta_eur": round(
                delta_pts * position_sign(deal) * deal.nominal * fx_rate, 2),
            "n_paths": 0, "spot_shock_scope": "flux_connu",
        }

    spot_mult, vol_add = _build_shock_arrays(ctx["underlyings_json"], shock,
                                             ctx["norm_spots"])
    corr_shocked = _shock_corr(ctx["corr"], shock.corr_shock_pts)
    dr = shock.rate_shock_bp / 10000.0

    # The shocked leg must inherit exactly the lifecycle state the MtM it is
    # compared against was built on — same knock-in status, same accrued
    # coupons, same observation counter. Repricing without it produced a
    # `delta_pts` that mostly measured the difference between a live deal and a
    # brand new one, not the effect of the shock.
    result = run_valuation(
        ctx["residual_script"], ctx["valuation_context"],
        corr_matrix=corr_shocked,
        spot_mult=spot_mult, spot_base=ctx["norm_spots"], vol_add=vol_add, dr=dr,
        wof0_init=min(spot_mult),
    )
    # Observed but not yet paid coupons are already part of the baseline MtM.
    # They carry no spot/vol/correlation optionality and must remain in the
    # shocked value; otherwise even a zero shock creates a fictitious loss.
    result["price"] += float(ctx.get("unsettled_pv", 0.0))

    fx_rate = fx_rate_to(deal.devise, "EUR")
    if fx_rate is None:
        # delta_pts is currency-free and stays meaningful; delta_eur is not
        # computable and must not be invented — a shock impact understated by
        # a missing rate is exactly the number a stress test exists to get right.
        raise HTTPException(
            422, f"Taux de change {deal.devise}/EUR indisponible — l'impact en "
                 f"euros de ce choc ne peut pas être calculé pour {deal.reference}.")
    delta_pts = result["price"] - mtm_payload["mtm"]

    return {
        "deal_id": deal.id, "reference": deal.reference, "skipped": False,
        "mtm_before": mtm_payload["mtm"], "mtm_after": result["price"],
        "delta_pts": round(delta_pts, 4),
        # delta_pts stays the raw price move of the product; the sign belongs
        # on the cash figure, which is the one that gets summed across a book.
        "delta_eur": round(delta_pts * position_sign(deal) * deal.nominal * fx_rate, 2),
        "n_paths": result["n_paths"],
        # Ce que le choc de spot a REELLEMENT fait a ce deal. Avant le strike
        # il ne met pas le produit dans ou hors de la monnaie : le strike suit
        # le spot, seul le skew qui s'appliquera se deplace.
        "spot_shock_scope": (
            None if not ctx.get("pre_strike") else
            ("smile" if ctx["model_used"] in ("localvol", "lsv", "sabr")
             else "sans_effet")
        ),
    }


def _run_shock_on_book(deals: list[Deal], session: Session, n_paths: int, shock: ShockRequest) -> dict:
    contributions, skipped, errors = [], [], []
    total_delta_eur = 0.0
    # Nominal total (EUR) of every deal in scope — including skipped/errored
    # ones, same denominator convention as the Risque tab's "Nominal total"
    # tile — the % impact must be read against the portfolio's actual size,
    # not just the subset that happened to reprice cleanly this time.
    nominal_total_eur = 0.0
    for d in deals:
        fx_rate = fx_rate_to(d.devise, "EUR")
        if fx_rate is None:
            # Not folded into the denominator at parity: the "% of book"
            # figures below would otherwise be measured against a size that
            # includes a made-up conversion. _run_shock_on_deal raises on the
            # same condition, so the deal also lands in `errors` with the reason.
            errors.append({"deal_id": d.id, "reference": d.reference,
                           "error": f"Taux de change {d.devise}/EUR indisponible — "
                                    f"position exclue des totaux."})
            continue
        nominal_total_eur += d.nominal * fx_rate

        try:
            r = _run_shock_on_deal(d, session, n_paths, shock)
        except HTTPException as e:
            errors.append({"deal_id": d.id, "reference": d.reference, "error": e.detail})
            continue
        if r.get("skipped"):
            skipped.append(r)
            continue
        contributions.append(r)
        total_delta_eur += r["delta_eur"]

    pct_impact = (total_delta_eur / nominal_total_eur * 100.0) if nominal_total_eur else None
    return {
        "total_delta_eur": round(total_delta_eur, 2),
        "nominal_total_eur": round(nominal_total_eur, 2),
        "pct_impact": round(pct_impact, 3) if pct_impact is not None else None,
        "contributions": contributions,
        "skipped": skipped,
        "errors": errors,
    }


_SMILE_INPUT_TO_ENGINE = {
    "atm_vol_pts": "sigma",
    "skew_pts": "skew",
    "curvature_pts": "curvature",
    "sabr_alpha_pts": "alpha",
    "sabr_rho_pts": "rho",
    "sabr_nu_pts": "nu",
    "heston_v0_pts": "v0",
    "heston_theta_pts": "theta",
    "heston_rho_pts": "rho_h",
    "heston_xi_pts": "xi",
}

_SMILE_FIELDS_BY_MODEL = {
    "constant": ("atm_vol_pts",),
    "localvol": ("atm_vol_pts", "skew_pts", "curvature_pts"),
    "lsv": (
        "atm_vol_pts", "skew_pts", "curvature_pts",
        "heston_v0_pts", "heston_theta_pts", "heston_rho_pts", "heston_xi_pts",
    ),
    "sabr": ("sabr_alpha_pts", "sabr_rho_pts", "sabr_nu_pts"),
    "heston": (
        "heston_v0_pts", "heston_theta_pts", "heston_rho_pts", "heston_xi_pts",
    ),
}


def _smile_shift(body: SmileRiskRequest, underlying: dict, field_name: str) -> float:
    key_candidates = [underlying.get("ticker"), underlying.get("name")]
    override = next((body.underlying_overrides.get(str(key))
                     for key in key_candidates
                     if key and str(key) in body.underlying_overrides), None)
    if override is not None:
        value = getattr(override, field_name)
        if value is not None:
            return float(value)
    return float(getattr(body, field_name))


def _validate_smile_parameter(name: str, value: float, underlying_name: str) -> None:
    if name in {"sigma", "v0", "theta", "xi", "alpha"} and value <= 0:
        raise ValueError(
            f"{underlying_name}: {name} doit rester strictement positif")
    if name == "nu" and value < 0:
        raise ValueError(f"{underlying_name}: nu doit rester positif ou nul")
    if name in {"rho", "rho_h"} and not -1.0 <= value <= 1.0:
        raise ValueError(f"{underlying_name}: {name} doit rester dans [-1, 1]")


def _smile_underlying_overrides(
    body: SmileRiskRequest,
    model: str,
    underlyings: list[dict],
) -> tuple[dict, list[dict], list[str]]:
    supported = set(_SMILE_FIELDS_BY_MODEL.get(model, ()))
    overrides: dict[str, dict] = {}
    changes: list[dict] = []
    applied_fields: set[str] = set()

    for index, underlying in enumerate(underlyings):
        key = str(underlying.get("ticker") or underlying.get("name") or index)
        name = str(underlying.get("name") or key)
        engine_changes = {}
        visible_changes = []
        for input_name in supported:
            shift_pts = _smile_shift(body, underlying, input_name)
            if not shift_pts:
                continue
            engine_name = _SMILE_INPUT_TO_ENGINE[input_name]
            before = float(underlying.get(engine_name, 0.0) or 0.0)
            after = before + shift_pts / 100.0
            _validate_smile_parameter(engine_name, after, name)
            engine_changes[engine_name] = after
            applied_fields.add(input_name)
            visible_changes.append({
                "parameter": engine_name,
                "before_pct": round(before * 100.0, 6),
                "after_pct": round(after * 100.0, 6),
                "shift_pts": shift_pts,
            })
        if engine_changes:
            overrides[key] = engine_changes
            changes.append({
                "name": name,
                "ticker": underlying.get("ticker"),
                "changes": visible_changes,
            })

    requested_fields = {
        field_name for field_name in _SMILE_INPUT_TO_ENGINE
        if float(getattr(body, field_name)) != 0.0
    }
    for override in body.underlying_overrides.values():
        requested_fields.update(
            field_name for field_name in _SMILE_INPUT_TO_ENGINE
            if getattr(override, field_name) not in (None, 0, 0.0)
        )
    ignored = sorted(requested_fields - supported)
    return overrides, changes, ignored


def _run_smile_on_deal(
    deal: Deal,
    session: Session,
    n_paths: int,
    body: SmileRiskRequest,
) -> dict:
    mtm_payload, ctx = _mtm_core(deal, session, n_paths, body)
    if ctx is None:
        return {
            "deal_id": deal.id, "reference": deal.reference, "skipped": True,
            "reason": mtm_payload.get("message", "résolution en attente"),
        }
    if ctx.get("settlement_claim"):
        return {
            "deal_id": deal.id, "reference": deal.reference, "skipped": True,
            "reason": "Flux contractuel déjà fixé : aucun risque de smile résiduel.",
        }

    model = str(ctx.get("model_used") or "constant")
    valuation_context = ctx["valuation_context"]
    underlyings = (valuation_context.underlyings
                   if hasattr(valuation_context, "underlyings")
                   else valuation_context.get("underlyings", []))
    overrides, changes, ignored = _smile_underlying_overrides(body, model, underlyings)
    if not overrides:
        return {
            "deal_id": deal.id, "reference": deal.reference, "model": model,
            "skipped": True,
            "reason": "Aucun paramètre demandé ne s'applique au modèle du deal.",
            "ignored_fields": ignored,
        }

    result = run_valuation(
        ctx["residual_script"], valuation_context,
        underlying_overrides=overrides,
    )
    result["price"] += float(ctx.get("unsettled_pv", 0.0))
    fx_rate = fx_rate_to(deal.devise, "EUR")
    if fx_rate is None:
        raise ValueError(
            f"Taux de change {deal.devise}/EUR indisponible pour {deal.reference}")
    delta_pts = float(result["price"]) - float(mtm_payload["mtm"])
    return {
        "deal_id": deal.id,
        "reference": deal.reference,
        "model": model,
        "skipped": False,
        "mtm_before": mtm_payload["mtm"],
        "mtm_after": result["price"],
        "delta_pts": round(delta_pts, 4),
        "delta_eur": round(
            delta_pts * position_sign(deal) * deal.nominal * fx_rate, 2),
        "n_paths": result["n_paths"],
        "parameter_changes": changes,
        "ignored_fields": ignored,
    }


def _run_smile_on_book(
    deals: list[Deal],
    session: Session,
    n_paths: int,
    body: SmileRiskRequest,
) -> dict:
    contributions, skipped, errors = [], [], []
    nominal_total_eur = 0.0
    priced_nominal_eur = 0.0
    total_delta_eur = 0.0
    by_model: dict[str, int] = {}

    for deal in deals:
        fx_rate = fx_rate_to(deal.devise, "EUR")
        if fx_rate is None:
            errors.append({
                "deal_id": deal.id, "reference": deal.reference,
                "error": f"Taux de change {deal.devise}/EUR indisponible.",
            })
            continue
        deal_nominal_eur = deal.nominal * fx_rate
        nominal_total_eur += deal_nominal_eur
        try:
            row = _run_smile_on_deal(deal, session, n_paths, body)
        except (HTTPException, ValueError) as exc:
            errors.append({
                "deal_id": deal.id,
                "reference": deal.reference,
                "error": exc.detail if isinstance(exc, HTTPException) else str(exc),
            })
            continue
        if row.get("skipped"):
            skipped.append(row)
            continue
        contributions.append(row)
        total_delta_eur += row["delta_eur"]
        priced_nominal_eur += deal_nominal_eur
        by_model[row["model"]] = by_model.get(row["model"], 0) + 1

    return {
        "total_delta_eur": round(total_delta_eur, 2),
        "nominal_total_eur": round(nominal_total_eur, 2),
        "priced_nominal_eur": round(priced_nominal_eur, 2),
        "coverage_pct": round(priced_nominal_eur / nominal_total_eur * 100.0, 2)
        if nominal_total_eur else None,
        "pct_impact": round(total_delta_eur / nominal_total_eur * 100.0, 4)
        if nominal_total_eur else None,
        "contributions": contributions,
        "skipped": skipped,
        "errors": errors,
        "by_model": by_model,
    }


def _describe_smile(body: SmileRiskRequest) -> str:
    if body.label.strip():
        return body.label.strip()
    parts = []
    labels = {
        "atm_vol_pts": "ATM", "skew_pts": "Skew", "curvature_pts": "Courbure",
        "sabr_alpha_pts": "SABR α", "sabr_rho_pts": "SABR ρ",
        "sabr_nu_pts": "SABR ν", "heston_v0_pts": "Heston v0",
        "heston_theta_pts": "Heston θ", "heston_rho_pts": "Heston ρ",
        "heston_xi_pts": "Heston ξ",
    }
    for field_name, label in labels.items():
        value = float(getattr(body, field_name))
        if value:
            parts.append(f"{label} {value:+g}pt")
    return " / ".join(parts) or "Scénario smile par sous-jacent"


def _persist_shock(session: Session, user_id: int, scope: str, shock: ShockRequest,
                    result: dict, deal_id: int | None = None,
                    portfolio_id: int | None = None) -> ShockRun:
    run = ShockRun(
        user_id=user_id, scope=scope, deal_id=deal_id, portfolio_id=portfolio_id,
        label=_describe_shock(shock),
        params_json=shock.model_dump_json(),
        result_json=json.dumps(result),
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def _shock_run_row(r: ShockRun) -> dict:
    return {
        "id": r.id, "scope": r.scope, "deal_id": r.deal_id, "portfolio_id": r.portfolio_id,
        "label": r.label, "params": json.loads(r.params_json), "result": json.loads(r.result_json),
        "created_at": r.created_at.isoformat(),
    }


@router.post("/api/deals/{deal_id}/shock")
def shock_deal(
    deal_id: int,
    body: ShockRequest,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    n_paths: int = 20000,
):
    deal = session.get(Deal, deal_id)
    if not deal or not _can_access_deal(deal, current, session):
        raise HTTPException(404, "Deal introuvable")
    result = _run_shock_on_deal(deal, session, n_paths, body)
    run = _persist_shock(session, current.id, "deal", body, result, deal_id=deal_id)
    return {**result, "run_id": run.id, "label": run.label}


@router.post("/api/portfolios/{portfolio_id}/shock")
def shock_portfolio(
    portfolio_id: int,
    body: ShockRequest,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    n_paths: int = 20000,
):
    p = session.get(Portfolio, portfolio_id)
    if not p or (getattr(current, "role", "user") != "admin" and p.user_id != current.id):
        raise HTTPException(404, "Portefeuille introuvable")
    from .portfolios import _portfolio_deals
    deals = _portfolio_deals(session, portfolio_id, ("actif", "en_reglement"))
    result = _run_shock_on_book(list(deals), session, n_paths, body)
    run = _persist_shock(session, current.id, "portfolio", body, result, portfolio_id=portfolio_id)
    return {**result, "run_id": run.id, "label": run.label}


@router.post("/api/portfolios/shock-global")
def shock_global(
    body: ShockRequest,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    n_paths: int = 20000,
):
    statement = select(Deal).where(Deal.status.in_(["actif", "en_reglement"]))
    if getattr(current, "role", "user") != "admin":
        statement = statement.where(Deal.user_id == current.id)
    deals = session.exec(statement).all()
    result = _run_shock_on_book(list(deals), session, n_paths, body)
    run = _persist_shock(session, current.id, "global", body, result)
    return {**result, "run_id": run.id, "label": run.label}


def _persist_smile(
    session: Session,
    user_id: int,
    scope: str,
    body: SmileRiskRequest,
    result: dict,
    portfolio_id: int | None = None,
) -> ShockRun:
    run = ShockRun(
        user_id=user_id,
        scope=scope,
        portfolio_id=portfolio_id,
        label=_describe_smile(body),
        params_json=body.model_dump_json(),
        result_json=json.dumps(result),
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


@router.post("/api/portfolios/{portfolio_id}/smile-risk")
def smile_risk_portfolio(
    portfolio_id: int,
    body: SmileRiskRequest,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    n_paths: int = 20000,
):
    p = session.get(Portfolio, portfolio_id)
    if not p or (getattr(current, "role", "user") != "admin" and p.user_id != current.id):
        raise HTTPException(404, "Portefeuille introuvable")
    from .portfolios import _portfolio_deals
    deals = _portfolio_deals(session, portfolio_id, ("actif", "en_reglement"))
    result = _run_smile_on_book(deals, session, n_paths, body)
    run = _persist_smile(
        session, current.id, "smile_portfolio", body, result,
        portfolio_id=portfolio_id,
    )
    return {**result, "run_id": run.id, "label": run.label}


@router.post("/api/portfolios/smile-risk-global")
def smile_risk_global(
    body: SmileRiskRequest,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    n_paths: int = 20000,
):
    statement = select(Deal).where(Deal.status.in_(["actif", "en_reglement"]))
    if getattr(current, "role", "user") != "admin":
        statement = statement.where(Deal.user_id == current.id)
    deals = session.exec(statement).all()
    result = _run_smile_on_book(list(deals), session, n_paths, body)
    run = _persist_smile(session, current.id, "smile_global", body, result)
    return {**result, "run_id": run.id, "label": run.label}


@router.get("/api/shocks")
def list_shocks(
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    scope: Optional[str] = None,
    deal_id: Optional[int] = None,
    portfolio_id: Optional[int] = None,
    limit: int = 20,
):
    q = select(ShockRun).where(ShockRun.user_id == current.id)
    if scope:
        q = q.where(ShockRun.scope == scope)
    if deal_id is not None:
        q = q.where(ShockRun.deal_id == deal_id)
    if portfolio_id is not None:
        q = q.where(ShockRun.portfolio_id == portfolio_id)
    q = q.order_by(ShockRun.created_at.desc()).limit(limit)
    runs = session.exec(q).all()
    return [_shock_run_row(r) for r in runs]
