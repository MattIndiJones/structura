"""Residual deal valuation orchestration shared by MtM, risk and VaR.

This module owns the translation from a booked deal and realized history to a
serializable ``ValuationContext``. API routes only perform authorization and
response delivery; compute workers can import this module without depending on
an API router.
"""
from __future__ import annotations

import json
import math
from datetime import date, timedelta
from typing import List, Literal, Optional

from fastapi import HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from ..db.models import Deal, DealEvent
from ..services.market_data import (
    dividend_profile, load_hist_prices, market_data_provider_for_deal,
)
from .calibration import realized_market
from .inlife_valuation import InLifeProduct, ValuationError, build_residual
from .market_snapshot import snapshot_rate, snapshot_rate_is_default
from .valuation_context import (
    ValuationContext, deterministic_cashflow_pv,
    funding_from_market_snapshot, run_valuation,
)
from ..services.product_repository import ProductError, load_product


_EXIT_CAPTURE = 0.97


class MtmOverrideUL(BaseModel):
    """Manual per-underlying override in display units."""
    sigma: Optional[float] = None
    q: Optional[float] = None


class MtmRequest(BaseModel):
    recalibrate: Literal["none", "realized"] = "none"
    overrides: Optional[dict[str, MtmOverrideUL]] = None
    r: Optional[float] = None
    window_days: int = 252


class DealGreeksRequest(MtmRequest):
    selected: List[str] = ["delta", "gamma", "vega", "theta", "rho"]


def _get_events(deal_id: int, session: Session) -> list:
    return session.exec(
        select(DealEvent).where(DealEvent.deal_id == deal_id)
        .order_by(DealEvent.event_index)
    ).all()


def mtm_core(
    deal: Deal,
    session: Session,
    n_paths: int = 20000,
    body: Optional[MtmRequest] = None,
    asof: Optional[date] = None,
    *,
    load_prices=None,
    dividend_loader=None,
    realized_loader=None,
) -> tuple[dict, Optional[dict]]:
    """Residual mark-to-market of an ACTIVE deal: replay the frozen script on
    realized history (state: memory coupons, observation index, running
    extrema), then Monte Carlo the REMAINING life only — observation dates at
    their true residual times, paths seeded at today's spot/strike levels,
    replayed state injected. This is the desk MtM, as opposed to '→ Ouvrir'
    re-pricing which restarts the product as new. Design:
    MTM_RESIDUEL_DESIGN.md.

    Returns (payload, ctx): payload is the /mtm response; ctx carries the
    intermediates the valuation note (PDF) and the P&L explain need — price
    history, replayed state, compiled script (monitors), effective underlyings,
    residual script — or None on the resolved_pending short-circuit. Ownership
    is the caller's concern.

    asof (default today) values the deal AS OF a past date: the price history
    is truncated there, so the replayed state, the seeding spots, the residual
    calendar and the realized-vol window all follow — this is what the P&L
    explain uses to build its two photos (EXPLICATION_VALO_DESIGN.md)."""
    injected_price_loader = load_prices is not None
    load_prices = load_prices or load_hist_prices
    dividend_loader = dividend_loader or dividend_profile
    realized_loader = realized_loader or realized_market
    deal_id = deal.id
    today = asof or date.today()
    market_provider = market_data_provider_for_deal(deal, session)
    body = body or MtmRequest()
    product = None
    if getattr(deal, "product_id", None) is not None:
        try:
            product = load_product(session, deal.product_id)
        except ProductError as exc:
            raise HTTPException(exc.status, {"code": exc.code, "message": str(exc)})
        if deal.product_terms_version != product.terms_version:
            raise HTTPException(409, {
                "code": "PRODUCT_TERMS_VERSION_MISMATCH",
                "message": "Le deal ne référence pas la version courante de ses termes Product.",
            })
    terms = product.terms if product is not None else None

    # Once the contractual payoff is known, there is no path left to simulate.
    # The receivable nevertheless remains a live credit exposure until cash
    # settlement, so it has a deterministic MtM during this short window.
    if deal.status == "en_reglement":
        payment_value = (terms.payment_date.isoformat()
                         if terms and terms.payment_date else deal.payment_date)
        payment = date.fromisoformat(payment_value)
        if today >= payment:
            raise HTTPException(422, "Règlement atteint — l'exposition est soldée")
        market = json.loads(deal.market_snapshot_json or "{}")
        elapsed_origin = (terms.strike_date if terms and terms.strike_date else
                          date.fromisoformat(deal.strike_date or deal.value_date))
        elapsed = max(0.0, (today - elapsed_origin).days / 365.25)
        funding_curve, funding_spread = funding_from_market_snapshot(market, elapsed)
        r_frac = body.r / 100.0 if body.r is not None else snapshot_rate(market)
        yield_curve = ([] if body.r is not None else
                       [[p["T"], p["rate"] / 100.0]
                        for p in market.get("yieldCurve") or []])
        amount = float(
            deal.settlement_amount
            if deal.settlement_amount is not None else
            (deal.realized_payout or 0.0)
        )
        remaining = (payment - today).days / 365.25
        mtm = deterministic_cashflow_pv(
            amount, remaining, r=r_frac, yield_curve=yield_curve,
            funding_curve=funding_curve, funding_spread=funding_spread)
        payload = {
            "deal_id": deal_id, "reference": deal.reference,
            "status": "en_reglement", "settlement_pending": True,
            "mtm": mtm, "ic95": [mtm, mtm], "prob_gt100": float(mtm > 1.0),
            "fugit": remaining, "T_elapsed": round(elapsed, 4),
            "T_remaining": 0.0, "payment_date": payment.isoformat(),
            "settlement_amount": amount,
            "settled_cash_flows": [],
            "unsettled_cash_flows": [{
                "cf": amount, "payment_date": payment.isoformat(),
                "pv": mtm,
            }],
            "realized_cash_flows": [], "realized_total": 0.0,
            "settled_total": 0.0, "unsettled_total": amount,
            "unsettled_pv": mtm, "best_case": None,
            "n_paths": 0, "elapsed_ms": 0.0,
            "market_used": {
                "source": "known_settlement",
                "model": "deterministic_cashflow",
                "r": round(r_frac * 100.0, 4),
                "funding_spread": round(funding_spread * 100.0, 6),
                "funding_curve": [[round(t, 6), round(s * 100.0, 6)]
                                  for t, s in funding_curve],
                "data": {
                    "provider": market_provider,
                    "price_type": "KNOWN_CASHFLOW",
                    "requested_asof": today.isoformat(),
                },
            },
        }
        return payload, {
            "settlement_claim": True, "fixed_price": mtm,
            "tickers": [], "payment_date": payment.isoformat(),
            "settlement_amount": amount, "time_to_payment": remaining,
        }

    if deal.status != "actif":
        raise HTTPException(422, f"Deal {deal.status} — plus d'optionnalité à valoriser "
                                 f"(remboursement réalisé: {deal.realized_payout})")

    maturity = (terms.maturity_date if terms and terms.maturity_date
                else date.fromisoformat(deal.maturity_date))
    value_d = (terms.value_date if terms and terms.value_date
               else date.fromisoformat(deal.value_date))
    if today >= maturity:
        raise HTTPException(422, "Échéance atteinte — lancer le refresh du cycle de vie "
                                 "pour résoudre le deal plutôt que le valoriser")
    # Meme origine que les temps d observation : la date de strike. Compter le
    # temps ecoule depuis la value date decalerait tout le residuel.
    _elapsed_origin = (terms.strike_date if terms and terms.strike_date else
                       (date.fromisoformat(deal.strike_date) if deal.strike_date else value_d))
    # Avant la constatation initiale, `T_elapsed` devient NÉGATIF : rien ne
    # s'est écoulé, et l'écart au strike décale les constatations vers l'avenir
    # (_shift_events_for_mtf soustrait T_elapsed). L'axe commence dans les deux
    # cas à la date de valorisation ; ce qui change est qu'avant le strike il
    # commence AVANT le produit, et que le fixing est alors simulé comme le
    # reste — `strike_set_t` dit au moteur à quel pas il tombe.
    pre_strike = today < _elapsed_origin
    T_elapsed = (today - _elapsed_origin).days / 365.25
    T_remaining = max(1 / 52, (maturity - today).days / 365.25)
    residual_payment_t = (
        ((terms.payment_date if terms and terms.payment_date
          else date.fromisoformat(deal.payment_date)) - today).days / 365.25
        if (terms and terms.payment_date) or deal.payment_date else None)
    strike_set_t = -T_elapsed if pre_strike else None

    # Le rejeu du passé et la construction du résiduel vivent dans le cœur
    # (core/inlife_valuation) : le Pricer doit pouvoir les appeler sans qu'un
    # deal existe. Ici on ne fait que traduire un deal en paramètres.
    strike_event = next((e for e in _get_events(deal_id, session) if e.t_years == 0.0), None)
    deal_market = json.loads(deal.market_snapshot_json) if deal.market_snapshot_json else {}
    if terms is not None:
        deal_market = {
            **deal_market,
            "constats": terms.constats.to_dict(),
            "user_params": terms.user_params(),
        }
    produit = InLifeProduct(
        script_snapshot=terms.script if terms is not None else deal.script_snapshot,
        underlyings=([u.model_dump(mode="json") for u in terms.underlyings]
                     if terms is not None else json.loads(deal.underlyings_json)),
        strike_levels=json.loads(strike_event.spots_json) if strike_event else {},
        strike_date=(terms.strike_date if terms and terms.strike_date else
                     (date.fromisoformat(deal.strike_date) if deal.strike_date else value_d)),
        value_date=value_d,
        tenor=terms.T if terms is not None else deal.T,
        currency=((terms.settlement_ccy if terms else deal.devise) or "").strip().upper(),
        payment_date=(terms.payment_date if terms and terms.payment_date else
                      (date.fromisoformat(deal.payment_date) if deal.payment_date else None)),
        market=deal_market,
        frozen_schedule=(terms.resolved_events.to_dict()
                         if terms is not None and terms.resolved_events else None),
    )
    # Historique réalisé depuis le strike (même fenêtre J-7 que le refresh du
    # cycle de vie : un strike un week-end ou un férié a besoin de la clôture
    # qui précède). Le chargement reste ici, le cœur ne fait pas d'I/O.
    tickers = [u["ticker"] for u in produit.underlyings if u.get("ticker")]
    if not tickers:
        raise HTTPException(422, "Aucun ticker défini sur ce deal")
    # Avant le strike, la fenêtre partirait d'une date postérieure à sa propre
    # fin : Yahoo refuse l'intervalle et le MtM s'arrêtait là. On borne au jour
    # de valorisation — l'historique ne sert alors qu'à la recalibration
    # réalisée et à l'affichage, le rejeu n'ayant rien à rejouer.
    fetch_start = (min(produit.strike_date, today) - timedelta(days=7)).isoformat()
    if injected_price_loader:
        px_data = load_prices(tickers, fetch_start, today.isoformat())
    else:
        # Raw close is the loader's default. Keep the three-argument contract
        # so test/adapter replacements written before provider selection remain
        # valid; unavailable account providers are rejected when configured.
        px_data = load_prices(tickers, fetch_start, today.isoformat())
    if "error" in px_data:
        raise HTTPException(422, px_data["error"])
    try:
        residuel = build_residual(produit, px_data.get("prices", {}),
                                  px_data.get("dates", []), T_elapsed, today)
    except ValuationError as exc:
        raise HTTPException(422, str(exc))

    if residuel.early_recall:
        # The old wording pointed at "refresh the lifecycle", which stopped
        # being actionable when fixings became governed: a refresh only updates
        # INDICATIVE monitoring data and raises a proposal — resolving the deal
        # now requires a sourced observation validated by an independent Checker.
        return {
            "resolved_pending": True,
            "message": "Le replay indicatif détecte un rappel anticipé : ce deal ne "
                       "devrait plus être actif. La résolution passe par une observation "
                       "sourcée et validée — soumettez la version candidate puis faites-la "
                       "traiter dans la file Checker. Un refresh ne met à jour que les "
                       "données indicatives et ne résoudra pas le deal.",
            "T_actual": residuel.T_actual,
        }, None

    # Noms locaux conservés : toute la suite de la fonction les utilise tels
    # quels, ce qui garde le déplacement mécanique et vérifiable.
    market = produit.market
    underlyings_json = produit.underlyings
    compiled = residuel.compiled
    residual_script = residuel.residual_script
    state = residuel.state
    realized_cfs = residuel.realized_flows
    norm_spots = residuel.norm_spots
    engine_uls = residuel.engine_uls
    r_frac = residuel.r_frac
    prices = residuel.prices
    dates_list = residuel.dates_list
    user_params = residuel.user_params
    replay = residuel.replay
    start_idx = residuel.start_idx
    s0_map = residuel.s0_map
    n_u = len(engine_uls)
    corr = market.get("corrMatrix") or [
        [1.0 if i == j else 0.0 for j in range(n_u)] for i in range(n_u)
    ]

    rate_model = market.get("rateModel", "deterministic")
    sigma_r = (market.get("sigma_r", 0.0) or 0.0) / 100.0 if rate_model != "deterministic" else 0.0
    a_r = (market.get("a_r", 0.0) or 0.0) if rate_model == "hull_white" else 0.0
    yc = [[p["T"], p["rate"] / 100.0] for p in market.get("yieldCurve") or []]
    funding_curve, funding_spread = funding_from_market_snapshot(
        market, max(0.0, T_elapsed))

    # ── Market recalibration (opt-in) — only the FUTURE MC leg is affected,
    # the historical replay and the inherited state never depend on σ/corr.
    model_used = market.get("model", "constant")
    source = "booking"
    n_returns = None
    dividend_sources = {u["name"]: "booking" for u in underlyings_json}
    booked_underlyings = {
        u.get("name"): u for u in (market.get("underlyings") or [])
    }
    statistical_px_data = None
    if body.recalibrate == "realized":
        if injected_price_loader:
            try:
                statistical_px_data = load_prices(
                    tickers, fetch_start, today.isoformat(), adjusted=True)
            except TypeError:
                # Test/legacy injected loaders may expose the former three
                # argument contract. Production always takes the explicit
                # adjusted branch above.
                statistical_px_data = px_data
        else:
            statistical_px_data = load_prices(
                tickers, fetch_start, today.isoformat(), adjusted=True,
                provider=market_provider)
        if "error" in statistical_px_data:
            raise HTTPException(422, statistical_px_data["error"])
        try:
            rm = realized_loader(
                statistical_px_data.get("prices", {}), tickers,
                body.window_days)
        except ValueError as e:
            raise HTTPException(422, f"Recalibration réalisée impossible : {e}")
        for u, tk in zip(engine_uls, tickers):
            u["sigma"] = rm["sigma"][tk]
        corr = rm["corr"]
        n_returns = rm["n_returns"]
        # Realized vol is a GBM-like number: keeping Heston/SABR/LV with only σ
        # swapped would be either a no-op or an incoherent mix (fresh level,
        # stale smile). Forced model is surfaced in market_used.
        model_used = "constant"
        source = "realized"
        # q is a market level at the valuation date.  What survives booking is
        # the curve convention (enabled/decay), not the first-year level.  The
        # latter is refreshed for the requested as-of date, then the residual
        # curve is rebuilt from the frozen convention.
        for u, tk in zip(engine_uls, tickers):
            profile = dividend_loader(tk, today.isoformat())
            name = u["name"]
            if profile.get("ok"):
                u["q"] = float(profile.get("yield_declared") or 0.0)
                policy = booked_underlyings.get(name, {})
                curve_enabled = bool(
                    policy.get("dividendCurveEnabled")
                    or policy.get("dividendCurve")
                )
                if curve_enabled:
                    decay = float(u.get("dividend_decay", 0.0))
                    u["dividend_curve"] = [
                        [float(year), u["q"] * (1.0 - decay) ** (year - 1)]
                        for year in range(1, max(1, math.ceil(T_remaining)) + 1)
                    ]
                else:
                    u["dividend_curve"] = []
                dividend_sources[name] = "current"
            else:
                dividend_sources[name] = "booking_fallback"
    if body.overrides:
        by_name = {u["name"]: u for u in engine_uls}
        for name, ov in body.overrides.items():
            u = by_name.get(name)
            if u is None:
                raise HTTPException(422, f"Override sur sous-jacent inconnu : {name}")
            if ov.sigma is not None:
                u["sigma"] = ov.sigma / 100.0
                model_used = "constant"   # same reasoning as the realized mode
            if ov.q is not None:
                u["q"] = ov.q / 100.0
                policy = booked_underlyings.get(name, {})
                if policy.get("dividendCurveEnabled") or policy.get("dividendCurve"):
                    decay = float(u.get("dividend_decay", 0.0))
                    u["dividend_curve"] = [
                        [float(year), u["q"] * (1.0 - decay) ** (year - 1)]
                        for year in range(1, max(1, math.ceil(T_remaining)) + 1)
                    ]
                else:
                    u["dividend_curve"] = []
                dividend_sources[name] = "manual"
        source += "+overrides"
    if body.r is not None:
        # A fresh flat rate with the stale booking curve would be incoherent —
        # the override replaces the whole discounting/drift term.
        r_frac = body.r / 100.0
        yc = []

    # Convention globale du moteur, commune à tous les produits. Ce n'est ni
    # un terme économique du deal ni un état aléatoire persisté.
    seed = 42
    barrier_monitoring = market.get("barrierMonitoring", "weekly")
    antithetic = bool(market.get("antithetic", True))
    N_used = max(1000, min(100000, n_paths))
    valuation_context = ValuationContext(
        underlyings=engine_uls, corr_matrix=corr, r=r_frac, T=T_remaining,
        N=N_used, model=model_used, seed=seed, antithetic=antithetic,
        user_params=user_params, yield_curve=yc,
        funding_curve=funding_curve, funding_spread=funding_spread,
        sigma_r=sigma_r, a_r=a_r, barrier_monitoring=barrier_monitoring,
        maturity_payment_t=residual_payment_t, strike_set_t=strike_set_t,
        script_text=deal.script_snapshot,
        constats=market.get("constats") or {},
        state={
            "spot_mult": norm_spots, "spot_base": norm_spots,
            "wof_min_init": state["wof_min"], "bof_max_init": state["bof_max"],
            "index_offset": state["index"], "memo_init": state["memo"],
            "accum_init": state["accum"], "s_min_init": state["s_min"],
            "s_max_init": state["s_max"], "s_prev_init": state["s_prev"],
            "wof0_init": min(norm_spots),
            "realvol_state_init": state["realvol_state"],
            "fix_state_init": state["fix_state"],
        },
    )

    try:
        result = run_valuation(residual_script, valuation_context)
    except ValueError as e:
        raise HTTPException(422, f"MC résiduel impossible : {e}")

    settled_flows = []
    unsettled_flows = []
    unsettled_pv = 0.0
    for flow in realized_cfs:
        enriched = dict(flow)
        is_maturity_flow = abs(float(flow.get("t", 0.0)) - float(deal.T)) < 1e-6
        payment_iso = (deal.payment_date if is_maturity_flow and deal.payment_date
                       else flow.get("payment_date") or flow.get("date"))
        enriched["payment_date"] = payment_iso
        try:
            payment_day = date.fromisoformat(payment_iso)
        except (TypeError, ValueError):
            payment_day = today
        if payment_day <= today:
            settled_flows.append(enriched)
        else:
            remaining = (payment_day - today).days / 365.25
            pv = deterministic_cashflow_pv(
                float(flow["cf"]), remaining, r=r_frac, yield_curve=yc,
                funding_curve=funding_curve, funding_spread=funding_spread)
            enriched["pv"] = pv
            unsettled_flows.append(enriched)
            unsettled_pv += pv
    if unsettled_pv:
        result["price"] += unsettled_pv
        if result.get("ic95"):
            result["ic95"] = [float(bound) + unsettled_pv
                              for bound in result["ic95"]]
        # The engine does not retain the terminal samples after returning.
        # Adding a deterministic receivable shifts this probability, so the
        # old number would describe the optional leg alone and is suppressed.
        result["prob_gt100"] = None
        if result.get("pv_max") is not None:
            result["pv_max"] += unsettled_pv
        if result.get("pv_p95") is not None:
            result["pv_p95"] += unsettled_pv

    # Residual upside vs the best possible outcome (present value). A payoff is
    # "capped" when the top of the discounted distribution is flat (best case =
    # 95th percentile within 0.5%) — autocalls, reverse convertibles… For those,
    # a MtM already capturing >= _EXIT_CAPTURE of the best case means the client
    # keeps market+credit risk for near-zero remaining upside: early-exit signal.
    # Uncapped payoffs (open upside participation): pv_max is a meaningless tail
    # quantile — expose pv_p95 as "favourable scenario", never the exit signal.
    pv_max, pv_p95 = result.get("pv_max"), result.get("pv_p95")
    best_case = None
    if pv_max is not None and pv_max > 0:
        # bool()/float() coercions: these come out of numpy reductions, and a
        # numpy.bool_ (unlike numpy.float64, a float subclass) crashes FastAPI's
        # JSON encoder.
        pv_max, pv_p95 = float(pv_max), float(pv_p95 or 0.0)
        capped = bool((pv_max - pv_p95) / pv_max < 0.005)
        horizon = max(result.get("fugit") or T_remaining, 1 / 52)
        upside = pv_max - result["price"]
        capture = result["price"] / pv_max
        best_case = {
            "pv_max": pv_max,
            "pv_p95": pv_p95,
            "capped": capped,
            "capture_ratio": round(capture, 4),
            "upside_pts": round(upside * 100, 2),
            "upside_annualized_pct": round(upside / horizon * 100, 2),
            "horizon_years": round(horizon, 2),
            "exit_signal": bool(capped and capture >= _EXIT_CAPTURE),
        }

    def data_provenance(data: Optional[dict]) -> Optional[dict]:
        if not data:
            return None
        return {
            key: data.get(key) for key in (
                "provider", "price_type", "adjusted", "requested_start",
                "requested_end", "asof_effective", "effective_dates",
                "age_sessions", "warnings", "fetched_at",
            ) if key in data
        }

    payload = {
        "deal_id": deal_id,
        "reference": deal.reference,
        "mtm": result["price"],
        "ic95": result["ic95"],
        "prob_gt100": result["prob_gt100"],
        "fugit": result["fugit"],
        "T_elapsed": round(T_elapsed, 4),
        "T_remaining": round(T_remaining, 4),
        # Avant le strike il n'y a pas de constatation passée : les champs
        # « réalisé » sont vides plutôt que nuls — 0 se lirait comme un
        # plus-bas à zéro, ce qui est l'inverse de ce qu'ils décrivent.
        "pre_strike": pre_strike,
        "strike_date": deal.strike_date,
        "payment_date": deal.payment_date or None,
        "obs_passees": state["index"],
        "wof_min_realized": (None if state["wof_min"] is None
                             else round(state["wof_min"], 4)),
        "s_min_realized": (None if state["s_min"] is None else
                           {u["name"]: round(v, 4)
                            for u, v in zip(underlyings_json, state["s_min"])}),
        "norm_spots": {u["name"]: round(s, 4) for u, s in zip(underlyings_json, norm_spots)},
        "realized_cash_flows": realized_cfs,
        "realized_total": round(sum(cf["cf"] for cf in realized_cfs), 4),
        "settled_cash_flows": settled_flows,
        "unsettled_cash_flows": unsettled_flows,
        "settled_total": round(sum(cf["cf"] for cf in settled_flows), 4),
        "unsettled_total": round(sum(cf["cf"] for cf in unsettled_flows), 4),
        "unsettled_pv": round(unsettled_pv, 8),
        "best_case": best_case,
        "n_paths": result["n_paths"],
        "elapsed_ms": result["elapsed_ms"],
        # Effective market parameters of the future MC leg — always present so
        # a MtM number can never be quoted without knowing what priced it.
        "market_used": {
            "source": source,
            "model": model_used,
            "r": round(r_frac * 100.0, 4),
            # True only for a legacy snapshot carrying no rate at all: the
            # figure above is then our fallback, not this deal's own term.
            # A zero or negative booked rate is honoured and reads False.
            "r_is_default": snapshot_rate_is_default(market) and body.r is None,
            "flat_curve": not yc,
            "window_returns": n_returns,
            "sigma": {u["name"]: round(eu["sigma"] * 100.0, 2)
                      for u, eu in zip(underlyings_json, engine_uls)},
            "q": {u["name"]: round(eu["q"] * 100.0, 2)
                  for u, eu in zip(underlyings_json, engine_uls)},
            "dividend_source": dividend_sources,
            "dividend_curve": {
                u["name"]: [[round(t, 6), round(q * 100.0, 6)] for t, q in
                            (eu.get("dividend_curve") or [])]
                for u, eu in zip(underlyings_json, engine_uls)
            },
            "corr": [[round(v, 4) for v in row] for row in corr],
            "funding_spread": round(funding_spread * 100.0, 6),
            "funding_curve": [[round(t, 6), round(s * 100.0, 6)]
                              for t, s in funding_curve],
            "funding_is_legacy_default": (
                "funding" not in market
                and "funding_spread" not in market
                and "funding_curve" not in market
            ),
            "seed": seed,
            "antithetic": antithetic,
            "barrier_monitoring": barrier_monitoring,
            "data": {
                "provider": market_provider,
                "contractual_history": data_provenance(px_data),
                "statistical_history": data_provenance(statistical_px_data),
            },
        },
    }
    ctx = {
        "compiled": compiled,
        "state": state,
        "user_params": user_params,
        "dates": dates_list,
        "prices": prices,
        "start_idx": start_idx,
        "s0_map": s0_map,
        "tickers": tickers,
        "underlyings_json": underlyings_json,
        "norm_spots": norm_spots,
        "T_elapsed": T_elapsed,
        "passe_jusqu_a": residuel.passe_jusqu_a,
        "T_remaining": T_remaining,
        "residual_payment_t": residual_payment_t,
        # Tout repricing dérivé (chocs, Greeks, explication de P&L) doit
        # simuler le MÊME produit que le MtM auquel il se compare : sans ce
        # report, la jambe choquée pricerait un produit déjà striké contre un
        # forward-start, et l'écart mesurerait surtout cette différence-là.
        "strike_set_t": strike_set_t,
        "pre_strike": pre_strike,
        "n_mc": result["n_paths"],
        # Everything needed to re-run this photo's MC (or a mix of two photos)
        # for the P&L explain waterfall:
        "residual_script": residual_script,
        "engine_uls": engine_uls,
        "corr": corr,
        "model_used": model_used,
        "r_frac": r_frac,
        "yc": yc,
        "sigma_r": sigma_r,
        "a_r": a_r,
        "antithetic": antithetic,
        "barrier_monitoring": barrier_monitoring,
        "funding_curve": funding_curve,
        "funding_spread": funding_spread,
        "unsettled_pv": unsettled_pv,
        "seed": seed,
        "N_used": N_used,
        "valuation_context": valuation_context.to_dict(),
    }
    return payload, ctx


