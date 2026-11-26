"""Repricing inputs, MtM, Greeks, MtM explain, reports and valuation runs."""
from __future__ import annotations
import json
import re
from datetime import datetime, date, timezone
from typing import Annotated, Literal, Optional
from fastapi import Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select
from ...db.database import get_session
from ...runtime import business_today
from ...db.models import Deal, User, ValuationRun
from ..auth import get_current_user
from ..valuation_progress import valuation_progress_response
from ...services.market_data import (
    dividend_profile, load_hist_prices, load_session_calibration_history,
)
from ...services.archived_documents import DocumentSelection
from ...core.calibration import realized_market
from ...core.simulation_grid import GridFrequency, snapshot_grid, grid_frequency
from ...core.payoff_terms import classify_param_barrier
from ...core.valuation_context import ValuationContext, run_valuation
from ...core.deal_valuation import DealGreeksRequest, MtmRequest, standard_mtm_request, mtm_core as _deal_mtm_core
from ...core.valuation_runs import stage_valuation_run, replay_valuation_run
from ...services.business_access import can_read_deal as _can_access_deal
from ._router import router
from .common import _evenements_pour_la_note, _niveau_initial_constate
from .serializers import _get_events
from ..contracts import returns
from ..responses import DealMtm

@router.get("/{deal_id}/reprice")
def reprice_inputs(
    deal_id: int,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    """Return normalized inputs for re-pricing the deal at current market conditions."""
    deal = session.get(Deal, deal_id)
    if not deal or not _can_access_deal(deal, current, session):
        raise HTTPException(404, "Deal introuvable")

    if deal.status in ("callé", "échu", "en_reglement"):
        # Already resolved (see _evaluate_lifecycle) — there is no more
        # optionality to run a Monte Carlo on. Re-simulating from today with
        # a fresh script would price it as if it restarted now, which is
        # wrong. Report the realized outcome instead.
        events = _get_events(deal_id, session)
        resolved_event = next((e for e in events if e.status in ("callé", "ki", "final")), None)
        return {
            "deal_id": deal_id,
            "reference": deal.reference,
            "resolved": True,
            "status": deal.status,
            "realized_payout": deal.realized_payout,
            "settlement_amount": deal.settlement_amount,
            "payment_date": deal.payment_date,
            "resolution_date": resolved_event.event_date if resolved_event else None,
        }

    today = business_today()
    maturity = date.fromisoformat(deal.maturity_date)
    value_d = date.fromisoformat(deal.value_date)

    T_remaining = max(0.0, (maturity - today).days / 365.25)
    # Meme origine que les temps d observation : la date de strike. Compter le
    # temps ecoule depuis la value date decalerait tout le residuel.
    _elapsed_origin = (date.fromisoformat(deal.strike_date) if deal.strike_date else value_d)
    T_elapsed = max(0.0, (today - _elapsed_origin).days / 365.25)

    underlyings = json.loads(deal.underlyings_json)
    tickers = [u["ticker"] for u in underlyings if u.get("ticker")]

    # S₀ comes from the t=0 event (Strike / Fixing S₀), filled in by the user in
    # Events tab — or, with a start window, from the reduction of its relevés.
    events = _get_events(deal_id, session)
    s0_map: dict = _niveau_initial_constate(events, deal.schedule_json)

    normalized_spots: dict = {}
    current_spots: dict = {}

    if tickers:
        px_data = load_hist_prices(tickers, today.isoformat(), today.isoformat())
        if "error" not in px_data:
            prices = px_data.get("prices", {})
            for u in underlyings:
                tk = u.get("ticker", "")
                name = u["name"]
                s0 = s0_map.get(name, 0.0)
                if tk and tk in prices and prices[tk]:
                    s_current = float(prices[tk][-1])
                    current_spots[name] = round(s_current, 4)
                    if s0 > 0:
                        normalized_spots[name] = round(s_current / s0, 6)

    realized = [
        {
            "event_date": e.event_date,
            "t_years": e.t_years,
            "spots": json.loads(e.spots_json),
            "label": e.label,
        }
        for e in events
        if e.status in ("observé", "callé", "ki") and json.loads(e.spots_json)
    ]

    market_snapshot = json.loads(deal.market_snapshot_json)
    return {
        "deal_id": deal_id,
        "reference": deal.reference,
        "resolved": False,
        "T_remaining": round(T_remaining, 4),
        "T_elapsed": round(T_elapsed, 4),
        "maturity_date": deal.maturity_date,
        "value_date": deal.value_date,
        "normalized_spots": normalized_spots,
        "current_spots": current_spots,
        "realized_events": realized,
        "script_snapshot": deal.script_snapshot,
        "market_snapshot": market_snapshot,
        "underlyings": market_snapshot.get("underlyings", []),
        "corr_matrix": market_snapshot.get("corrMatrix", []),
    }


@router.get("/{deal_id}/archives")
def list_deal_archives(deal_id: int, current: Annotated[User, Depends(get_current_user)],
                      session: Annotated[Session, Depends(get_session)]):
    from ...db.models import ArchivedDocument
    deal = session.get(Deal, deal_id)
    if not deal or not _can_access_deal(deal, current, session):
        raise HTTPException(404, "Deal introuvable")
    return [{"archive_id": row.id, "kind": row.kind, "parent_id": row.parent_id,
             "contract_version": row.contract_version, "created_at": row.created_at.isoformat(),
             "data": json.loads(row.data_json)} for row in session.exec(select(ArchivedDocument).where(
                 ArchivedDocument.deal_id == deal_id, ArchivedDocument.user_id == current.id)
                 .order_by(ArchivedDocument.created_at.desc(), ArchivedDocument.id)).all()]


# Residual MtM schemas and implementation live in core/deal_valuation.py.
def _mtm_core(deal: Deal, session: Session, n_paths: int = 20000,
              body: Optional[MtmRequest] = None,
              asof: Optional[date] = None, *, progress=None):
    """Compatibility boundary for routes and existing callers.

    Dependencies are passed explicitly so the core remains usable by workers
    and deterministic tests without importing this API module.
    """
    return _deal_mtm_core(
        deal, session, n_paths, body, asof,
        load_prices=load_hist_prices,
        dividend_loader=dividend_profile,
        realized_loader=realized_market,
        calibration_loader=load_session_calibration_history,
        progress=progress,
    )


@router.post("/{deal_id}/mtm", responses=returns(DealMtm))
def deal_mtm(
    deal_id: int,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    n_paths: int = 20000,
    body: Optional[MtmRequest] = None,
    stream: bool = False,
):
    """Residual MtM endpoint — see _mtm_core."""
    deal = session.get(Deal, deal_id)
    if not deal or not _can_access_deal(deal, current, session):
        raise HTTPException(404, "Deal introuvable")
    if stream:
        bind = session.get_bind()
        user_id = current.id

        def compute(progress):
            # Never share the request's SQLAlchemy session across threads.
            with Session(bind) as worker_session:
                worker_user = worker_session.get(User, user_id)
                worker_deal = worker_session.get(Deal, deal_id)
                if not worker_user or not worker_deal or not _can_access_deal(
                        worker_deal, worker_user, worker_session):
                    raise HTTPException(404, "Deal introuvable")
                payload, ctx = _mtm_core(
                    worker_deal, worker_session, n_paths, body, progress=progress)
                if ctx is not None:
                    progress("saving")
                    _run, payload = stage_valuation_run(
                        worker_session, worker_deal, user_id, "MTM", ctx, payload,
                        diagnostics={"request": (body.model_dump(mode="json") if body else {})},
                    )
                    worker_session.commit()
                return payload

        return valuation_progress_response(compute)
    payload, ctx = _mtm_core(deal, session, n_paths, body)
    if ctx is None:
        return payload
    _run, payload = stage_valuation_run(
        session, deal, current.id, "MTM", ctx, payload,
        diagnostics={"request": (body.model_dump(mode="json") if body else {})},
    )
    session.commit()
    return payload


@router.post("/{deal_id}/greeks")
def deal_greeks(
    deal_id: int,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    n_paths: int = 20000,
    body: Optional[DealGreeksRequest] = None,
):
    """Bump-and-reprice Greeks on the residual MtM leg — reuses _mtm_core's
    ctx (residual script, effective underlyings, corr, rates) exactly as
    compute_greeks needs it, so the sensitivities are consistent with
    whatever MtM number the same market assumptions would produce. Last
    result is persisted on the deal (greeks_json/greeks_computed_at),
    overwritten at each call — see PLAN squishy-baking-sedgewick."""
    from ...core.payscript.engine import compute_greeks

    deal = session.get(Deal, deal_id)
    if not deal or not _can_access_deal(deal, current, session):
        raise HTTPException(404, "Deal introuvable")

    body = body or DealGreeksRequest()
    mtm_payload, ctx = _mtm_core(deal, session, n_paths, body)
    if ctx is None:
        return mtm_payload   # resolved_pending short-circuit — nothing to bump
    if ctx.get("settlement_claim"):
        raise HTTPException(
            422,
            "Le remboursement est déjà déterminé : les Greeks optionnels ne "
            "s’appliquent plus. Consultez le MtM du flux à régler.",
        )

    names = [u["name"] for u in ctx["underlyings_json"]]
    # Cross-gamma (correlation sensitivity) is meaningless for a single
    # underlying and left out of DealGreeksRequest's default selection (it
    # doesn't sum across deals with different baskets — see the class
    # docstring) — but for a worst-of/basket deal it's exactly the risk a
    # family-office user won't intuit on their own, so force it on here
    # rather than requiring an explicit opt-in every time.
    selected = list(body.selected)
    if len(names) >= 2 and "corr" not in selected:
        selected.append("corr")

    raw = compute_greeks(
        ctx["residual_script"], ctx["engine_uls"], ctx["corr"],
        ctx["r_frac"], ctx["T_remaining"], ctx["N_used"], ctx["model_used"],
        seed=ctx.get("seed", 42), user_params=ctx["user_params"], selected=selected,
        sigma_r=ctx["sigma_r"], a_r=ctx["a_r"], yield_curve=ctx["yc"],
        funding_curve=ctx.get("funding_curve", []),
        funding_spread=ctx.get("funding_spread", 0.0),
        barrier_monitoring=ctx["barrier_monitoring"],
        # A live deal's sensitivities are those of what it has BECOME — spot
        # where it stands today, knock-in already touched or not, coupons
        # already accrued. Repricing it as a brand new product, which is what
        # omitting this does, answers a question nobody asked.
        antithetic=ctx["antithetic"], state=_greeks_state(ctx),
        strike_set_t=ctx.get("strike_set_t"),
        maturity_payment_t=ctx.get("residual_payment_t"),
    steps_per_year=ctx.get("steps_per_year", 52), local_vol_anchor=ctx.get("local_vol_anchor"))

    per_underlying: dict[str, dict] = {}
    scalar: dict[str, float | None] = {}
    # Keyed by the underlying pair's own names ("AAPL / MSFT"), not the raw
    # corr_1_2 index form compute_greeks returns — readable directly in the
    # UI without the caller having to re-resolve indices against names.
    corr_pairs: dict[str, float] = {}
    # Not a sensitivity: the observation the theta window steps over, and the
    # cash it detaches. Kept out of `scalar`, which is summed across the book.
    theta_event = raw.pop("theta_event", None)
    # Not a sensitivity either: what fraction of the volatility the vega bump
    # actually reaches (see compute_greeks). Kept out of `scalar`, which is
    # summed across the book.
    vega_scope = raw.pop("vega_scope", None)
    corr_bumps = raw.pop('corr_bumps', None)
    for key, val in raw.items():
        m = re.match(r"^(delta|gamma|vega)_(\d+)$", key)
        if m:
            greek, idx = m.group(1), int(m.group(2)) - 1
            per_underlying.setdefault(names[idx], {})[greek] = val
            continue
        m = re.match(r"^corr_(\d+)_(\d+)$", key)
        if m:
            i1, i2 = int(m.group(1)) - 1, int(m.group(2)) - 1
            corr_pairs[f"{names[i1]} / {names[i2]}"] = val
        else:
            scalar[key] = val   # theta, rho

    payload = {
        "deal_id": deal_id,
        "reference": deal.reference,
        "contract_version": deal.contract_version,
        "valuation_date": mtm_payload["valuation_date"],
        "computed_at": datetime.utcnow().isoformat(),
        "mtm_reference": mtm_payload["mtm"],
        "per_underlying": per_underlying,
        "scalar": scalar,
        "theta_event": theta_event,
        "vega_scope": vega_scope,
        "corr_pairs": corr_pairs,
        'corr_bumps': corr_bumps,
        "market_used": mtm_payload["market_used"],
    }
    if ctx.get("pre_strike"):
        payload["pre_strike"] = _avertissement_greeks_pre_strike(
            deal.strike_date, ctx["model_used"])

    _run, payload = stage_valuation_run(
        session, deal, current.id, "GREEKS", ctx, payload,
        diagnostics={
            "selected": selected,
            "request": body.model_dump(mode="json"),
        },
    )
    deal.greeks_json = json.dumps(payload)
    deal.greeks_computed_at = datetime.utcnow()
    session.add(deal)
    session.commit()

    return payload


class MtmExplainRequest(BaseModel):
    steps_per_year: Optional[GridFrequency] = None
    """Body of POST /{deal_id}/mtm/explain. date1 defaults to the deal's value
    date (booking), date2 to today. `recalibrate` sets the σ source at date 2 ;
    at date 1 the rule is fixed (booking σ when date1 = value date, realized σ
    otherwise — see EXPLICATION_VALO_DESIGN.md)."""
    date1: Optional[str] = None
    date2: Optional[str] = None
    recalibrate: Literal["none", "realized"] = "realized"
    window_days: int = 252


# Modèles dont la volatilité dépend du NIVEAU du sous-jacent. Eux seuls portent
# une dynamique de smile, donc un delta de forward-start : quand le spot bouge
# avant le strike, le niveau auquel le strike sera constaté se déplace dans une
# surface cotée en strikes absolus, et le skew qui s'appliquera au produit
# change. Sous vol constante ou Heston — tous deux invariants d'échelle — cet
# effet n'existe pas dans le modèle, et un delta nul y est une propriété du
# modèle, pas une absence de risque.
# Modèles dont la volatilité dépend du NIVEAU du sous-jacent. Le delta d'un
# forward-start ne mesure pas l'existence d'un smile mais sa DYNAMIQUE : ancrée
# en strikes absolus (vol locale) elle en donne un, flottante avec le spot
# (Heston, sticky-moneyness) elle n'en donne aucun. Heston a bien un smile et
# rendra pourtant zéro — ce n'est pas une anomalie.
_MODELES_DEPENDANT_DU_NIVEAU = {"localvol", "lsv", "sabr"}


def _avertissement_greeks_pre_strike(strike_date: str | None, model: str) -> dict:
    """Comment lire les sensibilités d'un produit dont le strike n'est pas fixé.

    Tout est calculé, rien n'est retiré : le fixing étant simulé trajectoire par
    trajectoire, un bump de spot met le strike à l'échelle avec le reste et le
    delta sort juste de lui-même. Reste à dire ce qu'il MESURE, car un même
    nombre — zéro — veut dire deux choses opposées selon le modèle, et un
    delta non nul ne se couvre pas comme un delta directionnel."""
    porte_le_smile = model in _MODELES_DEPENDANT_DU_NIVEAU
    if porte_le_smile:
        detail = ("Le delta affiché est un delta de SMILE : le strike suivra le "
                  "spot, seul se déplace le skew qui s'appliquera au produit. "
                  "Il ne se couvre pas comme un delta directionnel — et sous "
                  "vol locale il en surestime l'ampleur, ce modèle faisant "
                  "bouger son smile trop vite.")
    else:
        detail = ("Le modèle booké est invariant d'échelle : la dynamique de "
                  "smile qui donnerait un delta de forward-start n'y existe "
                  "pas, et le delta sort à zéro. Ce n'est pas une absence de "
                  "risque, c'est une limite du modèle.")
    return {
        "strike_date": strike_date,
        "model": model,
        "delta_type": "smile" if porte_le_smile else "nul_par_construction",
        "modele_porte_le_smile": porte_le_smile,
        "message": (
            "Avant strike — le niveau initial n'est pas encore constaté et il "
            "est simulé, un par trajectoire. Véga, thêta, rho et corrélation se "
            "lisent normalement. " + detail
        ),
    }


def _run_explain_step(cal: dict, spot: dict, uls: list, corr, model: str,
                      common: dict) -> float:
    """One waterfall revaluation: calendar bundle (residual script, T_remaining,
    observation counter — pure calendar quantities), spot bundle (seeding spots
    + path-dependent replayed state), vol bundle (σ via uls + model), corr.
    Mirrors _mtm_core's run_mc call exactly so the chain's endpoints coincide
    with the two /mtm figures. Same seed everywhere (CRN)."""
    st = spot["state"]
    context = ValuationContext(
        underlyings=uls, corr_matrix=corr, r=common["r_frac"],
        T=cal["T_remaining"], N=common["N"], model=model,
        seed=common.get("seed", 42), antithetic=common["antithetic"],
        user_params=common["user_params"], yield_curve=common["yc"],
        funding_curve=common.get("funding_curve", []),
        funding_spread=common.get("funding_spread", 0.0),
        sigma_r=common["sigma_r"], a_r=common["a_r"],
        barrier_monitoring=common["bm"],
        maturity_payment_t=cal.get("residual_payment_t"),
        strike_set_t=cal.get("strike_set_t"),
        state={
            "spot_mult": spot["norm_spots"], "spot_base": spot["norm_spots"],
            "wof_min_init": st["wof_min"], "bof_max_init": st["bof_max"], "wof_max_init": st.get("wof_max"),
            "index_offset": cal["index_offset"], "memo_init": st["memo"],
            "accum_init": st["accum"], "s_min_init": st["s_min"],
            "s_max_init": st["s_max"], "s_prev_init": st["s_prev"],
            "wof0_init": min(spot["norm_spots"]),
            "realvol_state_init": st["realvol_state"],
            "fix_state_init": st["fix_state"],
        },
    steps_per_year=common.get("steps_per_year", 52), local_vol_anchor=spot.get("local_vol_anchor", common.get("local_vol_anchor")))
    from ...core.valuation_context import unsettled_cashflows_pv
    return run_valuation(cal["residual_script"], context)["price"] + unsettled_cashflows_pv({
        **common, "unsettled_cash_flows": cal.get("unsettled_cash_flows", [])})


def _greeks_state(ctx: dict) -> dict:
    """The lifecycle bundle compute_greeks needs, assembled from _mtm_core's ctx.

    `spot_base` is what "not bumped" means for this deal — today's spot in % of
    strike. Every bump is taken relative to it, so a deal 30% above its strike
    is shocked by 1% of where it actually trades, not of its issue level."""
    st = ctx["state"]
    return {
        "spot_base": ctx["norm_spots"],
        "wof_min": st["wof_min"], "bof_max": st["bof_max"], "wof_max": st.get("wof_max"),
        "index": st["index"], "memo": st["memo"], "accum": st["accum"],
        "s_min": st["s_min"], "s_max": st["s_max"], "s_prev": st["s_prev"],
        "realvol_state": st["realvol_state"], "fix_state": st["fix_state"],
    }


def _residual_greeks(ctx: dict, n_paths: int) -> list[dict]:
    """Client-facing presentation of the residual sensitivities, for the PDF
    valuation notes: MtM impact in points for a +1% spot move (delta), its
    convexity (gamma) and +1 vol point (vega).

    The maths lives in compute_greeks — this only rescales. Two consequences of
    that convergence, both improvements: gamma now comes from a ±3% bump rather
    than ±1% (a second difference over a tiny denominator is dominated by Monte
    Carlo noise), and vega is no longer None outside GBM, because it bumps the
    diffusion's vol input rather than a `sigma` field that Heston ignores."""
    from ...core.payscript.engine import compute_greeks

    raw = compute_greeks(
        ctx["residual_script"], ctx["engine_uls"], ctx["corr"],
        ctx["r_frac"], ctx["T_remaining"], ctx["N_used"], ctx["model_used"],
        seed=ctx.get("seed", 42), user_params=ctx["user_params"],
        selected=["delta", "gamma", "vega"],
        sigma_r=ctx["sigma_r"], a_r=ctx["a_r"], yield_curve=ctx["yc"],
        funding_curve=ctx.get("funding_curve", []),
        funding_spread=ctx.get("funding_spread", 0.0),
        barrier_monitoring=ctx["barrier_monitoring"],
        antithetic=ctx["antithetic"], state=_greeks_state(ctx),
        strike_set_t=ctx.get("strike_set_t"),
        maturity_payment_t=ctx.get("residual_payment_t"),
    steps_per_year=ctx.get("steps_per_year", 52), local_vol_anchor=ctx.get("local_vol_anchor"))
    out = []
    for i, u in enumerate(ctx["underlyings_json"]):
        delta = raw.get(f"delta_{i+1}")
        gamma = raw.get(f"gamma_{i+1}")
        vega = raw.get(f"vega_{i+1}")
        out.append({
            "name": u["name"],
            # delta is already "price move per 100% of spot", i.e. points per
            # 1% — the two conventions coincide.
            "delta_pts": None if delta is None else round(delta, 2),
            "gamma_pts": None if gamma is None else round(gamma * 0.01, 3),
            "vega_pts": None if vega is None else round(vega, 2),
        })
    return out


def _explain_core(deal: Deal, session: Session, n_paths: int,
                  body: MtmExplainRequest) -> tuple[dict, dict, dict]:
    """P&L explain: time/state/receivables, spot, dividend, diffusion, corr,
    with identical seeds (CRN), plus contractual cash at payment dates.
    The chain telescopes exactly
    to ΔMtM; the residual line is the invariant check (≈0 — anything nonzero
    means a factor escaped the chain). Design: EXPLICATION_VALO_DESIGN.md.
    Returns (payload, ctx1, ctx2) — the ctxs feed the PDF note (greeks at d2)."""

    value_d = date.fromisoformat(deal.value_date)
    today = business_today()
    try:
        d1 = date.fromisoformat(body.date1) if body.date1 else value_d
        d2 = date.fromisoformat(body.date2) if body.date2 else today
    except ValueError as e:
        raise HTTPException(422, f"Date invalide : {e}")
    if d1 < value_d:
        d1 = value_d
    if d2 > today:
        raise HTTPException(422, "La date 2 est dans le futur — un MtM ne se calcule "
                                 "que sur des données réalisées")
    # Sur un deal non striké les deux bornes par défaut arrivent à l'envers (la
    # value date suit la constatation initiale, donc le présent), et le refus
    # générique sur l'ordre des dates se lit comme une saisie fautive. Ce n'est
    # pas une saisie : il n'y a rien à expliquer tant que le produit n'a pas
    # commencé — aucun temps écoulé, aucun flux, aucun mouvement de marché subi.
    if deal.strike_date and today < date.fromisoformat(deal.strike_date):
        raise HTTPException(
            422, f"Deal non striké — constatation initiale le {deal.strike_date}. "
                 f"L'explication de P&L compare deux photos du produit EN VIE ; "
                 f"avant sa première constatation il n'a pas encore d'histoire à "
                 f"décomposer. Le MtM et les Greeks, eux, sont disponibles.")
    if d2 <= d1:
        raise HTTPException(422, "La date 2 doit être strictement postérieure à la date 1")

    # σ à d1 : booking si d1 = date de valeur (l'effet véga répond alors à
    # « pricé à cette vol, le marché a fait autrement »), réalisée sinon.
    body1 = MtmRequest(recalibrate="none" if d1 == value_d else "realized",
                       window_days=body.window_days, steps_per_year=body.steps_per_year)
    body2 = MtmRequest(recalibrate=body.recalibrate, window_days=body.window_days, steps_per_year=body.steps_per_year)

    p1, c1 = _mtm_core(deal, session, n_paths, body1, asof=d1)
    if p1.get("resolved_pending") or c1 is None:
        raise HTTPException(422, "Produit déjà rappelé avant la date 1 — rien à expliquer")
    p2, c2 = _mtm_core(deal, session, n_paths, body2, asof=d2)
    if p2.get("resolved_pending") or c2 is None:
        raise HTTPException(422, "Produit rappelé entre les deux dates — c'est la "
                                 "résolution qui explique le P&L, pas un MtM")

    from ...core.valuation_attribution import (
        ATTRIBUTION_VERSION, CASH_BASIS, contractual_cash_in_period, with_dividend_inputs,
    )
    common = {"local_vol_anchor": c1.get("local_vol_anchor"), "steps_per_year": c1.get("steps_per_year", 52), "r_frac": c1["r_frac"], "yc": c1["yc"], "sigma_r": c1["sigma_r"],
              "a_r": c1["a_r"], "antithetic": c1["antithetic"],
              "user_params": c1["user_params"], "bm": c1["barrier_monitoring"],
              "funding_curve": c1.get("funding_curve", []),
              "funding_spread": c1.get("funding_spread", 0.0),
              "seed": c1.get("seed", 42), "N": c1["N_used"]}
    # strike_set_t : None en cours de vie, donc sans effet sur une cascade
    # existante. Avant le strike, l'omettre ferait pricer chaque étage comme un
    # produit déjà striké pendant que les deux /mtm encadrants pricent un
    # forward-start — la cascade ne télescoperait plus vers ΔMtM.
    cal2 = {"residual_script": c2["residual_script"], "T_remaining": c2["T_remaining"],
            "index_offset": c2["state"]["index"],
            "strike_set_t": c2.get("strike_set_t"),
            "residual_payment_t": c2.get("residual_payment_t"),
            "unsettled_cash_flows": c2.get("unsettled_cash_flows", [])}
    spot2 = {"norm_spots": c2["norm_spots"], "state": c2["state"], "local_vol_anchor": c2.get("local_vol_anchor")}
    # Calendar, realized payoff state and receivables are one lifecycle bundle.
    # Moving only the calendar deletes an observed but still unpaid coupon.
    time_state = {"norm_spots": c1["norm_spots"], "state": c2["state"]}
    dividend_uls = with_dividend_inputs(c1["engine_uls"], c2["engine_uls"])

    mtm1, mtm2 = p1["mtm"], p2["mtm"]
    try:
        v_time = _run_explain_step(cal2, time_state, c1["engine_uls"], c1["corr"],
                                   c1["model_used"], common)
        v_spot = _run_explain_step(cal2, spot2, c1["engine_uls"], c1["corr"],
                                   c1["model_used"], common)
        v_dividend = _run_explain_step(cal2, spot2, dividend_uls, c1["corr"],
                                       c1["model_used"], common)
        v_vol = _run_explain_step(cal2, spot2, c2["engine_uls"], c1["corr"],
                                  c2["model_used"], common)
        if len(c1["engine_uls"]) > 1 and c2["corr"] != c1["corr"]:
            v_corr = _run_explain_step(cal2, spot2, c2["engine_uls"], c2["corr"],
                                       c2["model_used"], common)
            corr_step = True
        else:
            v_corr, corr_step = v_vol, False
    except ValueError as e:
        raise HTTPException(422, f"Réévaluation waterfall impossible : {e}")

    steps = [
        {"label": "Effet temps", "delta_pts": round((v_time - mtm1) * 100, 2),
         "mtm_after": round(v_time, 6)},
        {"label": "Effet spot", "delta_pts": round((v_spot - v_time) * 100, 2),
         "mtm_after": round(v_spot, 6)},
        {"label": "Effet dividendes", "delta_pts": round((v_dividend - v_spot) * 100, 2),
         "mtm_after": round(v_dividend, 6)},
        {"label": "Effet volatilité", "delta_pts": round((v_vol - v_dividend) * 100, 2),
         "mtm_after": round(v_vol, 6)},
    ]
    if corr_step:
        steps.append({"label": "Effet corrélation",
                      "delta_pts": round((v_corr - v_vol) * 100, 2),
                      "mtm_after": round(v_corr, 6)})
    residual = mtm2 - v_corr

    try:
        flows = contractual_cash_in_period(p2, d1, d2)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    flows_total = sum(cf["cf"] for cf in flows)

    # Rule-based sentences — one per waterfall line, auditable.
    months = (d2 - d1).days / 30.44
    delta = mtm2 - mtm1
    phrases = [
        f"Entre le {d1.isoformat()} et le {d2.isoformat()}, la valeur du produit est "
        f"passée de {mtm1 * 100:.2f}% à {mtm2 * 100:.2f}% du nominal, soit "
        f"{delta * 100:+.2f} point(s).",
        f"L'écoulement du temps ({months:.1f} mois) contribue pour "
        f"{steps[0]['delta_pts']:+.2f} point(s) — rapprochement des échéances et des "
        f"coupons ; état réalisé et créances déplacés ensemble.",
    ]
    moves = ", ".join(
        f"{u['name']} de {s1 * 100:.1f}% à {s2 * 100:.1f}% du strike"
        for u, s1, s2 in zip(c1["underlyings_json"], c1["norm_spots"], c2["norm_spots"]))
    phrases.append(f"Le mouvement des sous-jacents ({moves}) contribue pour "
                   f"{steps[1]['delta_pts']:+.2f} point(s) (delta/gamma ; état et "
                   f"franchissements de barrières déjà portés par l'étape temps/état).")
    phrases.append(f"L'évolution des rendements et courbes de dividendes contribue pour "
                   f"{steps[2]['delta_pts']:+.2f} point(s), séparément de la volatilité.")
    sig1 = p1["market_used"]["sigma"]
    sig2 = p2["market_used"]["sigma"]
    vols = ", ".join(f"{n} de {sig1.get(n, '—')}% à {sig2.get(n, '—')}%"
                     for n in sig1)
    phrases.append(f"L'évolution de la volatilité ({vols}) contribue pour "
                   f"{steps[3]['delta_pts']:+.2f} point(s) (véga).")
    if corr_step:
        phrases.append(f"L'évolution des corrélations contribue pour "
                       f"{steps[4]['delta_pts']:+.2f} point(s).")
    if flows:
        phrases.append(f"Flux contractuels à échéance sur la période : {flows_total * 100:.2f}% du "
                       f"nominal — le P&L total de la période ressort à "
                       f"{(delta + flows_total) * 100:+.2f} point(s) (variation de "
                       f"valeur + cash contractuel).")
    phrases.append("Le cash est retenu selon les dates contractuelles de paiement, sur l'intervalle "
                   "]date 1, date 2] ; il ne constitue pas une preuve de virement bancaire.")
    phrases.append("Le taux d'actualisation est maintenu constant entre les deux dates "
                   "(pas de source de taux historiques) — tout effet taux résiduel est "
                   "porté par la ligne « résidu ».")

    payload = {
        "deal_id": deal.id,
        "reference": deal.reference,
        "date1": d1.isoformat(),
        "date2": d2.isoformat(),
        "mtm1": mtm1,
        "mtm2": mtm2,
        "delta_pts": round(delta * 100, 2),
        "steps": steps,
        "residual_pts": round(residual * 100, 2),
        "flows_detached": flows,
        "flows_total_pts": round(flows_total * 100, 2),
        "pnl_total_pts": round((delta + flows_total) * 100, 2),
        "cash_basis": CASH_BASIS,
        "cash_flows": flows,
        "attribution_version": ATTRIBUTION_VERSION,
        "unrounded": {
            "delta_pts": delta * 100, "residual_pts": residual * 100,
            "flows_total_pts": flows_total * 100, "pnl_total_pts": (delta + flows_total) * 100,
            "steps": [{"label": step["label"], "delta_pts": (after-before)*100}
                for step, before, after in zip(steps,
                    [mtm1, v_time, v_spot, v_dividend, v_vol],
                    [v_time, v_spot, v_dividend, v_vol, v_corr])],
        },
        "market1": p1["market_used"],
        "market2": p2["market_used"],
        "phrases": phrases,
    }
    return payload, c1, c2


@router.post("/{deal_id}/mtm/explain")
def deal_mtm_explain(
    deal_id: int,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    n_paths: int = 20000,
    body: Optional[MtmExplainRequest] = None,
):
    """P&L explain endpoint — see _explain_core."""
    deal = session.get(Deal, deal_id)
    if not deal or not _can_access_deal(deal, current, session):
        raise HTTPException(404, "Deal introuvable")
    payload, _c1, c2 = _explain_core(deal, session, n_paths,
                                      body or MtmExplainRequest())
    from ...services import archived_documents as archives
    from ...core.deal_valuation_pdf import generate_explain_pdf
    from ...core.valuation_runs import calculation_identity, replay_context
    data = {
        "deal": {key: getattr(deal, key, None) for key in (
            "reference", "product_type", "sens", "contrepartie", "nominal", "devise",
            "price_traded", "trade_date", "strike_date", "value_date", "maturity_date")},
        "res": payload, "underlyings": [
            {"name": u["name"], "ticker": u.get("ticker", ""), "spot_pct": spot}
            for u, spot in zip(c2["underlyings_json"], c2["norm_spots"])],
        "greeks": None, "calculation_identity": calculation_identity(),
        "replay_contexts": [replay_context(deal, _c1, {"mtm": payload["mtm1"]}),
                            replay_context(deal, c2, {"mtm": payload["mtm2"]})],
    }
    try:
        data["greeks"] = _residual_greeks(c2, n_paths)
    except (ValueError, ArithmeticError, RuntimeError) as exc:
        data["greeks_diagnostic"] = str(exc)
    row = archives.stage(session, kind="EXPLAIN", deal=deal, user=current,
                         request={"n_paths": n_paths, "body": (body or MtmExplainRequest()).model_dump(mode="json")},
                         data=data, pdf=generate_explain_pdf(data))
    session.commit()
    return {**payload, "archive_id": row.id}


@router.post("/{deal_id}/mtm/explain/report")
def deal_mtm_explain_report(
    deal_id: int,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    body: DocumentSelection,
):
    """Return the exact PDF retained with the selected displayed calculation."""
    deal = session.get(Deal, deal_id)
    if not deal or not _can_access_deal(deal, current, session):
        raise HTTPException(404, "Deal introuvable")
    from ...services import archived_documents as archives
    return archives.response(archives.load(session, body.archive_id, kind="EXPLAIN", deal=deal, user=current))


def _monitor_levels(compiled, user_params: dict, next_row: int) -> list[dict]:
    """Resolved barrier levels of the M_ monitoring contract, read at the row
    the NEXT observation will use for PARAM() arrays (same convention as the
    watchlist: obs number is 1-based, _pobs reads memo[name][index-1], so the
    next observation after `next_row` passed ones reads row `next_row`).
    Legacy scripts without any M_ param fall back to the same name heuristic
    as the watchlist (_classify_param_barrier)."""
    full = {p.name: p.stored_val for p in compiled.params}
    full.update(user_params or {})

    def resolve(name):
        v = full.get(name)
        if isinstance(v, list):
            v = v[min(next_row, len(v) - 1)] if v else None
        return float(v) if isinstance(v, (int, float)) else None

    out = []
    for m in compiled.monitors or []:
        lvl = resolve(m["name"])
        if lvl is not None:
            out.append({"name": m["name"], "observable": m.get("observable"),
                        "direction": m.get("direction"), "level": lvl})
    if out:
        return out
    for p in compiled.params:
        lvl = resolve(p.name)
        if lvl is None:
            continue
        kind = classify_param_barrier(p.name, lvl)
        if kind:
            out.append({"name": p.name, "observable": None,
                        "direction": "down" if kind == "ki" else "up",
                        "level": lvl})
    return out


@router.post("/{deal_id}/mtm/report")
def deal_mtm_report(
    deal_id: int,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    n_paths: int = 20000,
    body: Optional[MtmRequest] = None,
):
    """Client-facing valuation note (PDF): re-runs the residual MtM with the
    SAME body and seed as the /mtm endpoint — the figure in the PDF is exactly
    the one displayed in the Booking page. Design: NOTE_VALO_DESIGN.md."""
    import io as _io
    from fastapi.responses import StreamingResponse
    # Heavy import (matplotlib/reportlab) kept out of module load time.
    from ...core.deal_valuation_pdf import generate_valuation_pdf

    deal = session.get(Deal, deal_id)
    if not deal or not _can_access_deal(deal, current, session):
        raise HTTPException(404, "Deal introuvable")
    payload, ctx = _mtm_core(deal, session, n_paths, body)
    if payload.get("resolved_pending") or ctx is None:
        raise HTTPException(422, payload.get("message", "Deal en attente de résolution"))
    if ctx.get("settlement_claim"):
        raise HTTPException(
            422,
            "Le remboursement est déjà déterminé : la note de valorisation "
            "optionnelle n’est plus applicable. Consultez le MtM du flux à régler.",
        )

    ev_rows, next_obs = _evenements_pour_la_note(
        _get_events(deal_id, session), deal.schedule_json)

    start_idx = ctx["start_idx"]
    s0_map = ctx["s0_map"]
    series = {}
    for u in ctx["underlyings_json"]:
        name, tk = u["name"], u.get("ticker", "")
        s0 = s0_map.get(name, 0.0)
        px = ctx["prices"].get(tk, [])
        if s0 > 0 and px:
            series[name] = [(p / s0 if p and p > 0 else None) for p in px[start_idx:]]

    data = {
        "deal": {
            "reference": deal.reference, "product_type": deal.product_type,
            "sens": deal.sens, "contrepartie": deal.contrepartie,
            "nominal": deal.nominal, "devise": deal.devise,
            "price_traded": deal.price_traded,
            "trade_date": deal.trade_date, "strike_date": deal.strike_date,
            "value_date": deal.value_date, "maturity_date": deal.maturity_date,
        },
        "mtm": payload,
        "underlyings": [{"name": u["name"], "ticker": u.get("ticker", ""),
                         "spot_pct": s}
                        for u, s in zip(ctx["underlyings_json"], ctx["norm_spots"])],
        "monitors": _monitor_levels(ctx["compiled"], ctx["user_params"],
                                    ctx["state"]["index"]),
        "events": ev_rows,
        "next_obs_date": next_obs,
        "history": {"dates": ctx["dates"][start_idx:], "series": series},
        "greeks": _residual_greeks(ctx, n_paths),
    }
    run, run_result = stage_valuation_run(
        session, deal, current.id, "REPORT", ctx,
        {"mtm": payload, "greeks": data["greeks"]},
        diagnostics={"document": "valuation_note"},
    )
    data["valuation_run_id"] = run.id
    try:
        pdf_bytes = generate_valuation_pdf(data)
    except Exception as e:
        session.rollback()
        raise HTTPException(500, f"Erreur génération de la note de valorisation : {e}")
    session.commit()
    filename = f"Note_valo_{deal.reference}_{business_today().isoformat()}.pdf"
    return StreamingResponse(
        _io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Valuation-Run-Id": str(run.id),
        },
    )


def _valuation_run_row(run: ValuationRun, include_payload: bool = False) -> dict:
    from ...core.valuation_runs import calculation_identity
    saved_identity = json.loads(run.diagnostics_json or "{}").get("calculation_identity")
    row = {
        "id": run.id, "deal_id": run.deal_id, "run_type": run.run_type,
        "contract_version": run.contract_version,
        "context_hash": run.context_hash, "engine_version": run.engine_version,
        "engine_fingerprint": run.engine_fingerprint, "n_paths": run.n_paths,
        "created_at": run.created_at.isoformat(),
        "calculation_identity": saved_identity,
        "replay_compatible": saved_identity == calculation_identity(),
        "archive_warnings": ([] if saved_identity == calculation_identity() else
                             ["Moteur ou conventions absent/différent ; résultat conservé, rejeu non qualifié."]),
    }
    if include_payload:
        row.update({
            "result": json.loads(run.result_json or "{}"),
            "market_data": json.loads(run.market_data_json or "{}"),
            "data_versions": json.loads(run.data_versions_json or "{}"),
            "diagnostics": json.loads(run.diagnostics_json or "{}"),
        })
    return row


@router.get("/valuation-runs/latest-mtm")
def latest_mtm_runs(
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    deal_ids: str = "",
    created_from: Optional[datetime] = None,
    created_before: Optional[datetime] = None,
    valuation_date: Optional[date] = None,
    recalibrate: Optional[Literal["none", "realized"]] = None,
    steps_per_year: Optional[int] = None,
    booking_grid: bool = False,
):
    """Latest persisted MtM for each requested accessible deal.

    Booking shows several deals at once. Returning the immutable run payloads
    in one call avoids two HTTP requests per row when the user comes back to
    the page. The complete history remains available through the existing
    per-deal endpoint. Optional creation bounds describe the browser's local
    day in UTC; valuation date and market mode are independent filters applied
    before picking a winner, so a newer booking-mode run cannot hide today's
    latest current-market valuation.
    """
    if steps_per_year is not None:
        try:
            steps_per_year = grid_frequency(steps_per_year)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
    try:
        requested_ids = {
            int(raw) for raw in deal_ids.split(",") if raw.strip()
        }
    except ValueError as exc:
        raise HTTPException(422, "deal_ids doit contenir des identifiants entiers") from exc
    if not requested_ids:
        return []
    if len(requested_ids) > 200:
        raise HTTPException(422, "200 deals maximum par requête")

    statement = (
        select(ValuationRun)
        .where(ValuationRun.run_type == "MTM")
        .where(ValuationRun.deal_id.in_(requested_ids))
        .order_by(ValuationRun.created_at.desc(), ValuationRun.id.desc())
    )
    for boundary, lower in ((created_from, True), (created_before, False)):
        if boundary is not None:
            # Browser supplies its local midnight as an offset-aware instant.
            utc = boundary.astimezone(timezone.utc).replace(tzinfo=None) if boundary.tzinfo else boundary
            statement = statement.where(ValuationRun.created_at >= utc if lower else ValuationRun.created_at < utc)
    runs = session.exec(statement).all()
    latest = []
    seen = set()
    for run in runs:
        if run.deal_id in seen:
            continue
        deal = session.get(Deal, run.deal_id)
        if not deal or not _can_access_deal(deal, current, session):
            continue
        if run.contract_version != deal.contract_version:
            continue
        from ...core.valuation_runs import current_fixings_match
        if not current_fixings_match(session, run):
            continue
        row = _valuation_run_row(run, include_payload=True)
        request = row.get("diagnostics", {}).get("request", {})
        if valuation_date is not None:
            saved_date = row["result"].get("valuation_date") or request.get("valuation_date")
            if saved_date != valuation_date.isoformat():
                continue
        if recalibrate is not None:
            if not standard_mtm_request(request, recalibrate):
                continue
        expected_grid = steps_per_year
        if expected_grid is None and booking_grid:
            expected_grid = snapshot_grid(json.loads(deal.market_snapshot_json or "{}"))
        saved_market = row["result"].get("market_used") or {}
        saved_grid = saved_market.get("steps_per_year", (saved_market.get("time_axis") or {}).get("steps_per_year", 52))
        if expected_grid is not None and saved_grid != expected_grid:
            continue
        seen.add(run.deal_id)
        latest.append(row)
    return latest


@router.get("/{deal_id}/valuation-runs")
def list_valuation_runs(
    deal_id: int,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    run_type: Optional[str] = None,
    include_payload: bool = False,
):
    deal = session.get(Deal, deal_id)
    if not deal or not _can_access_deal(deal, current, session):
        raise HTTPException(404, "Deal introuvable")
    statement = select(ValuationRun).where(ValuationRun.deal_id == deal_id)
    if run_type:
        normalized_type = run_type.strip().upper()
        if normalized_type not in {"MTM", "GREEKS", "REPORT"}:
            raise HTTPException(422, "Type de run de valorisation inconnu")
        statement = statement.where(ValuationRun.run_type == normalized_type)
    runs = session.exec(
        statement.order_by(ValuationRun.created_at.desc(), ValuationRun.id.desc())
    ).all()
    return [_valuation_run_row(run, include_payload=include_payload) for run in runs]


@router.get("/valuation-runs/{run_id}")
def get_valuation_run(
    run_id: int,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    run = session.get(ValuationRun, run_id)
    deal = session.get(Deal, run.deal_id) if run else None
    if not run or not deal or not _can_access_deal(deal, current, session):
        raise HTTPException(404, "Run de valorisation introuvable")
    return _valuation_run_row(run, include_payload=True)


@router.post("/valuation-runs/{run_id}/replay")
def replay_saved_valuation_run(
    run_id: int,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    run = session.get(ValuationRun, run_id)
    deal = session.get(Deal, run.deal_id) if run else None
    if not run or not deal or not _can_access_deal(deal, current, session):
        raise HTTPException(404, "Run de valorisation introuvable")
    try:
        return replay_valuation_run(run)
    except Exception as exc:
        raise HTTPException(422, f"Rejeu du run impossible : {exc}") from exc
