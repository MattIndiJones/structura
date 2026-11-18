"""Reinvestment: roll, scan, proposal, frozen proposal and PDF."""
from __future__ import annotations
import json
import math
from datetime import date, timedelta
from typing import Annotated
from fastapi import Depends, HTTPException
from sqlmodel import Session, select
from ...db.database import get_session
from ...runtime import business_today
from ...db.models import Deal, User
from ..auth import get_current_user
from ...services.market_data import load_hist_prices
from ...services.archived_documents import DocumentSelection, ProposalFreeze
from ...core.payscript.parser import parse_script, resolve_constats, effective_T_max
from ...core.payscript.engine import derniere_fenetre, eval_script_on_history
from ...core.inlife_valuation import _engine_underlyings
from ...core.simulation_grid import snapshot_grid
from ...core.market_snapshot import snapshot_rate
from ...core.schemas import ReinvestScanRequest, ReinvestProposalRequest
from ...core.valuation_context import ValuationContext, funding_from_market_snapshot
from ...services.business_access import can_read_deal as _can_access_deal
from ._router import router
from .valuation import _monitor_levels

# ── MtM résiduel ──────────────────────────────────────────────────────

def _regenerate_dividend_curve(underlying: dict, maturity: float) -> None:
    """Rebuild a full-tenor curve after a first-year q refresh.

    Reinvestment deliberately refreshes Yahoo's q assumption. If the booked
    structure used a declining curve, changing only the scalar q would be a
    silent no-op because the path engine consumes the frozen nodes. Keep the
    booked decay convention and rebuild every explanatory/used node instead.
    """
    if not underlying.get("dividend_curve"):
        return
    q1 = float(underlying.get("q", 0.0))
    decay = float(underlying.get("dividend_decay", 0.0))
    n_years = max(1, math.ceil(float(maturity)))
    underlying["dividend_curve"] = [
        [float(year), q1 * (1.0 - decay) ** (year - 1)]
        for year in range(1, n_years + 1)
    ]


@router.post("/{deal_id}/reinvest/roll")
def reinvest_roll_endpoint(
    deal_id: int,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    from ...core.payscript.engine import run_mc
    from ...services.market_data import load_hist_vol

    deal = session.get(Deal, deal_id)
    if not deal or not _can_access_deal(deal, current, session):
        raise HTTPException(404, "Deal introuvable")
    if deal.status != "actif":
        raise HTTPException(422, f"Deal {deal.status} — rien à reconduire")

    market = json.loads(deal.market_snapshot_json) if deal.market_snapshot_json else {}
    underlyings_json = json.loads(deal.underlyings_json)
    tickers = [u["ticker"] for u in underlyings_json if u.get("ticker")]
    if not tickers:
        raise HTTPException(422, "Aucun ticker défini sur ce deal")

    try:
        compiled = parse_script(deal.script_snapshot)
        from ...core.payscript.bindings import shift_calendars
        rolled = shift_calendars(market.get("constats") or {}, deal.strike_date, business_today())
        compiled = resolve_constats(compiled, rolled, anchor=business_today(),
                                    currency=(deal.devise or "").strip().upper() or None)
    except ValueError as e:
        raise HTTPException(422, f"Script non exploitable pour la reconduction : {e}")

    engine_uls = _engine_underlyings(market, underlyings_json)
    n_u = len(engine_uls)
    corr = market.get("corrMatrix") or [[1.0 if i == j else 0.0 for j in range(n_u)] for i in range(n_u)]

    # Vol/div rafraîchies depuis Yahoo (pas de source de vol implicite — voir
    # MEMORY) ; en cas d'échec on retombe sur les valeurs du snapshot de
    # booking plutôt que d'échouer toute la reconduction.
    # Same estimator as the Pricer: common real closes of each venue.
    vol_data = load_hist_vol(tickers, session_aware=True)
    vol_refreshed = "error" not in vol_data
    if vol_refreshed:
        for u, tk in zip(engine_uls, tickers):
            if tk in vol_data["vols"]:
                u["sigma"] = vol_data["vols"][tk]
            if tk in vol_data["div_yields"]:
                u["q"] = vol_data["div_yields"][tk]
                _regenerate_dividend_curve(u, deal.T)
        if n_u > 1 and all(tk in vol_data["corr"] for tk in tickers):
            corr = [[vol_data["corr"][t1].get(t2, 0.0) for t2 in tickers] for t1 in tickers]

    current_spots: dict = {}
    px_data = load_hist_prices(tickers, business_today().isoformat(), business_today().isoformat())
    if "error" not in px_data:
        prices = px_data.get("prices", {})
        for tk in tickers:
            if tk in prices and prices[tk]:
                current_spots[tk] = round(float(prices[tk][-1]), 4)

    r_frac = snapshot_rate(market)
    user_params = market.get("user_params", {}) or {}
    rate_model = market.get("rateModel", "deterministic")
    sigma_r = (market.get("sigma_r", 0.0) or 0.0) / 100.0 if rate_model != "deterministic" else 0.0
    a_r = (market.get("a_r", 0.0) or 0.0) if rate_model == "hull_white" else 0.0
    yc = [[p["T"], p["rate"] / 100.0] for p in market.get("yieldCurve") or []]
    funding_curve, funding_spread = funding_from_market_snapshot(market)

    T_new = effective_T_max(compiled, deal.T)
    value_date_new = business_today()
    maturity_date_new = value_date_new + timedelta(days=round(T_new * 365.25))

    try:
        result = run_mc(
            compiled, engine_uls, corr, r_frac, T_new,
            N=20000, model=market.get("model", "constant"), seed=42,
            antithetic=bool(market.get("antithetic", True)),
            user_params=user_params,
            yield_curve=yc, funding_curve=funding_curve,
            funding_spread=funding_spread, sigma_r=sigma_r, a_r=a_r,
            barrier_monitoring=market.get("barrierMonitoring", "weekly"),
        steps_per_year=snapshot_grid(market))
    except ValueError as e:
        raise HTTPException(422, f"Pricing de la reconduction impossible : {e}")

    return {
        "deal_id": deal_id,
        "reference": deal.reference,
        "value_date": value_date_new.isoformat(),
        "maturity_date": maturity_date_new.isoformat(),
        "T": T_new,
        "price_new": round(result["price"], 6),
        "price_current": deal.fair_value,
        "current_spots": current_spots,
        "vol_refreshed": vol_refreshed,
        "vol_refresh_error": None if vol_refreshed else vol_data.get("error"),
        "sigma_used": {tk: round(u["sigma"], 4) for tk, u in zip(tickers, engine_uls)},
    }


def _price_reinvest_candidate(compiled, base_ul: dict, r_frac: float, T: float, corr: list,
                               user_params: dict, ticker: str, name: str,
                               param_name: str, target_price: float, lo: float, hi: float,
                               N: int, model: str, vol_period: str, valuation_context=None) -> dict:
    """Price one candidate underlying for the reinvestment scan/proposal:
    fresh vol/div from Yahoo, solve param_name to target_price, then price
    the risk profile. Shared by the scan (looped over the pool) and the
    proposal endpoint (single candidate, re-derives rather than trusting
    client-echoed figures for a document)."""
    from ...core.payscript.simulation import solve_for_param
    from ...core.payscript.engine import run_mc_proba
    from ...services.market_data import load_hist_vol

    vol_data = load_hist_vol([ticker], period=vol_period, session_aware=True)
    if "error" in vol_data or ticker not in vol_data.get("vols", {}):
        return {"ticker": ticker, "name": name,
                "error": vol_data.get("error", "Vol Yahoo indisponible pour ce ticker")}

    from copy import deepcopy
    from ...core.valuation_context import ValuationContext, run_analysis
    ul = deepcopy(base_ul)
    ul["name"], ul["ticker"] = name, ticker
    ul["sigma"] = vol_data["vols"][ticker]
    q = vol_data.get("div_yields", {}).get(ticker)
    if q is None or not math.isfinite(q):
        return {"ticker": ticker, "name": name, "error": "Dividende inconnu : hypothèse explicite requise avant proposition.",
                "dividend_diagnostic": vol_data.get("dividend_profiles", {}).get(ticker)}
    ul["q"] = q
    _regenerate_dividend_curve(ul, T)

    if ul.get('vol_surface') and model in ('heston','sabr','lsv') and ul.get('smile_parameter_mode','automatic') != 'manual':
        return {'ticker':ticker, 'name':name, 'error':
                'La calibration du sous-jacent d’origine ne qualifie pas ce candidat. Choisissez explicitement GBM ou des hypothèses manuelles qualifiées pour ce modèle.'}
    context = deepcopy(valuation_context) if valuation_context is not None else ValuationContext(
        underlyings=[ul], corr_matrix=corr, r=r_frac, T=T, N=N, model=model)
    context.underlyings = [ul]
    context.N = min(10000, max(2000, N))
    context.user_params = dict(user_params)

    try:
        solved = solve_for_param(
            compiled, [ul], corr, r_frac, T,
            model=model, seed=42, base_user_params=user_params,
            param_name=param_name, target_price=target_price,
            lo=lo, hi=hi, N=context.N, valuation_context=context,
        )
    except ValueError as e:
        return {"ticker": ticker, "name": name, "error": str(e)}
    if not solved["converged"]:
        return {"ticker": ticker, "name": name, "sigma": ul["sigma"], "q": ul["q"],
                "error": "Coupon non bracketé — élargir les bornes du solveur."}

    up = {**user_params, param_name: solved["param_value"]}
    try:
        context.user_params = up
        proba = run_analysis(compiled, context, 'proba', capital_ref=target_price)
    except ValueError as e:
        return {"ticker": ticker, "name": name, "error": str(e)}

    return {
        "ticker": ticker, "name": name,
        "sigma": round(ul["sigma"], 4), "q": round(ul["q"], 4),
        "param_name": param_name, "solved_param": solved["param_value"],
        "price": proba["price"],
        'valuation_context': context.to_dict(),
        'estimator': {**proba['estimator'], 'requested_draws': N},
        'model_source': 'Explicit override or inherited booking model; realized sigma/q, no automatic recalibration',
        "ki_pct": proba["ki_pct"], "autocall_pct": proba["autocall_pct"],
        # Le scan classe des candidats sur « récupère-t-on ce qu'on a payé ? » —
        # une valeur présente contre le prix payé. C'est `net_loss_pct`, pas
        # `capital_loss_pct`, qui répond lui à « récupère-t-on le pair ? » et se
        # lit sur le flux nominal. Les deux étaient une seule mesure, et le
        # défaut de référence à 1,0 la rendait fausse partout ailleurs.
        "capital_loss_pct": proba["net_loss_pct"], "full_coupon_pct": proba["full_coupon_pct"],
    }


def _reinvest_valuation_context(deal, market, base_ul, r, horizon, paths, model, user_params):
    from ...core.valuation_context import ValuationContext
    yc = [[p['T'], p['rate']/100] for p in market.get('yieldCurve') or []]
    fc, fs = funding_from_market_snapshot(market)
    rate_model = market.get('rateModel','deterministic')
    lag = ((date.fromisoformat(str(deal.payment_date))-date.fromisoformat(str(deal.maturity_date))).days/365.25
           if deal.payment_date and deal.maturity_date else 0.)
    settlement = ((date.fromisoformat(str(deal.value_date))-date.fromisoformat(str(deal.strike_date))).days/365.25
                  if deal.value_date and deal.strike_date else 0.)
    return ValuationContext(underlyings=[base_ul], corr_matrix=[[1.]], r=r, T=horizon, N=paths,
        model=model or market.get('model','constant'), antithetic=bool(market.get('antithetic',True)),
        yield_curve=yc, funding_curve=fc, funding_spread=fs,
        sigma_r=(market.get('sigma_r',0.) or 0.)/100 if rate_model!='deterministic' else 0.,
        a_r=(market.get('a_r',0.) or 0.) if rate_model=='hull_white' else 0.,
        barrier_monitoring=market.get('barrierMonitoring','weekly'),
        maturity_payment_t=horizon+lag, value_date_t=settlement,
        user_params=user_params, script_text=deal.script_snapshot, constats=market.get('constats') or {}, steps_per_year=snapshot_grid(market))


def _reinvest_context(deal: Deal, req_T: float | None):
    """Common setup for the scan/proposal endpoints: compiled script, base
    underlying, discounting rate, effective maturity. Raises HTTPException on
    an unusable deal/script — same checks either endpoint needs."""
    market = json.loads(deal.market_snapshot_json) if deal.market_snapshot_json else {}
    underlyings_json = json.loads(deal.underlyings_json)
    if len(underlyings_json) != 1:
        raise HTTPException(422, "Le scan d'alternatives ne gère pour l'instant que les "
                                  "produits mono-sous-jacent (limitation v1).")
    try:
        compiled = parse_script(deal.script_snapshot)
        from ...core.payscript.bindings import shift_calendars
        rolled = shift_calendars(market.get("constats") or {}, deal.strike_date, business_today())
        if req_T is not None and req_T != deal.T and (
                compiled.constats or any(event.type != 'AT_MATURITY' for event in compiled.events)):
            raise ValueError('Changer la maturité de ce produit exige de reconstruire ses '
                             'calendriers et ses PARAM() dans le Pricer ; le scan conserve '
                             'uniquement la maturité contractuelle.')
        original = None
        if compiled.constats:
            original = resolve_constats(parse_script(deal.script_snapshot), market.get('constats') or {},
                anchor=date.fromisoformat(str(deal.strike_date)), currency=(deal.devise or '').strip().upper() or None)
        compiled = resolve_constats(compiled, rolled, anchor=business_today(),
                                    currency=(deal.devise or "").strip().upper() or None)
        if original is not None:
            def shape(script):
                return [(len(event.dates), event.ranks,
                         [len(window) for window in (event.window_dates or [])]) for event in script.events]
            if shape(original) != shape(compiled):
                raise ValueError('Le déplacement des calendriers modifie le nombre de constatations '
                                 'ou de relevés ; reconstruire les termes et les PARAM() dans le Pricer.')
            frozen = json.loads(getattr(deal, 'schedule_json', None) or '{}')
            if frozen.get('constatations'):
                def ranks(schedule):
                    return sorted((str(row['calendrier']), row['rang'], len(row.get('releves') or []))
                                  for row in schedule['constatations'])
                if ranks(frozen) != ranks(compiled.echeancier.to_dict()):
                    raise ValueError('Le calendrier déplacé ne conserve pas les rangs du contrat figé ; '
                                     'reconstruire les termes dans le Pricer.')
    except ValueError as e:
        raise HTTPException(422, f"Script non exploitable : {e}")

    base_ul = _engine_underlyings(market, underlyings_json)[0]
    r_frac = snapshot_rate(market)
    T = effective_T_max(compiled, req_T if req_T else deal.T)
    return compiled, market, base_ul, r_frac, T


@router.post("/{deal_id}/reinvest/scan")
def reinvest_scan_endpoint(
    deal_id: int,
    req: ReinvestScanRequest,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    deal = session.get(Deal, deal_id)
    if not deal or not _can_access_deal(deal, current, session):
        raise HTTPException(404, "Deal introuvable")

    compiled, market, base_ul, r_frac, T = _reinvest_context(deal, req.T)
    # Mode avancé (param_overrides) : les valeurs bookées restent la base,
    # les overrides du structureur gagnent pour tout PARAM autre que celui
    # résolu par bissection (qui gagne toujours, dans _price_reinvest_candidate).
    user_params = {**(market.get("user_params", {}) or {}), **(req.param_overrides or {})}
    corr = [[1.0]]

    context = _reinvest_valuation_context(deal, market, base_ul, r_frac, T, req.N, req.model, user_params)

    def pct(res: dict, metric: str) -> float:
        return {"ki": res["ki_pct"], "autocall": res["autocall_pct"],
                "capital_loss": res["capital_loss_pct"], "full_coupon": res["full_coupon_pct"]}[metric]

    kept, excluded = [], []
    for cand in req.candidates:
        tk = cand.ticker.strip()
        if not tk:
            continue
        row = _price_reinvest_candidate(
            compiled, base_ul, r_frac, T, corr, user_params,
            tk, cand.name or tk, req.param_name, req.target_price, req.lo, req.hi,
            req.N, context.model, req.vol_period, valuation_context=context,
        )
        if "error" in row:
            excluded.append(row)
            continue

        failed = next((f for f in req.filters
                        if (pct(row, f.metric) > f.threshold if f.direction == "max"
                            else pct(row, f.metric) < f.threshold)), None)
        if failed:
            row["error"] = f"Filtre '{failed.metric}' non respecté ({pct(row, failed.metric)}%)"
            excluded.append(row)
        else:
            kept.append(row)

    kept.sort(key=lambda r: r["solved_param"], reverse=True)
    from ...services.archived_documents import sign_preview
    study = {"results": kept, "excluded": excluded}
    return {**study, "study_preview": sign_preview(study, req.model_dump(mode="json"), deal, current, purpose="STUDY")}


def _reinvest_proposal_data(deal: Deal, req: ReinvestProposalRequest) -> dict:
    """Shared by the JSON proposal (screen) and the PDF proposal (download) —
    same body recomputes the same figures, exactly like /mtm and /mtm/report
    share _mtm_core. Price/proba come from _price_reinvest_candidate (single
    candidate); backtest replays the SAME solved param over history via the
    existing _windowed_backtest (pricing.py, shared with /backtest/compare)."""
    from ..pricing import _windowed_backtest
    from ...core.payscript.engine import eval_script_on_history

    compiled, market, base_ul, r_frac, T = _reinvest_context(deal, req.T)
    user_params = {**(market.get("user_params", {}) or {}), **(req.param_overrides or {})}
    corr = [[1.0]]

    context = _reinvest_valuation_context(deal, market, base_ul, r_frac, T, req.N, req.model, user_params)

    row = _price_reinvest_candidate(
        compiled, base_ul, r_frac, T, corr, user_params,
        req.ticker, req.name or req.ticker, req.param_name, req.target_price, req.lo, req.hi,
        req.N, context.model, req.vol_period, valuation_context=context,
    )
    if "error" in row:
        raise HTTPException(422, row["error"])

    px_data = load_hist_prices([req.ticker], req.backtest_start, business_today().isoformat())
    if "error" in px_data:
        backtest = {"error": px_data["error"]}
    else:
        dates = px_data.get("dates", [])
        prices = px_data.get("prices", {})
        series = prices.get(req.ticker, [])
        up = {**user_params, req.param_name: row["solved_param"]}
        stats = _windowed_backtest(compiled, dates, prices, [req.ticker], T,
                                    req.backtest_freq, r_frac, req.backtest_invest_pct, up,
                                    return_windows=True)
        history = None
        if series and series[0]:
            s0 = series[0]
            history = {"dates": dates, "normalized": [round(p / s0, 4) if p else None for p in series]}
        backtest = {"stats": stats, "history": history}
        if stats is None:
            backtest["error"] = "Historique trop court pour la maturité du produit."
        else:
            # Barrières + dates de flux réels de la fenêtre de replay la plus
            # récente, PAS un second graphique séparé : en mono-sous-jacent le
            # worst-of EST le sous-jacent, une courbe "produit" à part ne
            # ferait que redupliquer la queue de la courbe sous-jacent à un
            # autre point de rebasage (voir MEMORY investment-solution-module,
            # le worst-of ne redevient une info distincte qu'avec un panier).
            # Donc : on annote LE graphique du sous-jacent — barrières
            # recalées sur SA base 100 (celle de tout l'historique récupéré,
            # pas celle de la fenêtre), flux positionnés à leur vraie date
            # dans cet historique.
            max_start = derniere_fenetre(compiled, dates, T)
            if max_start >= 0 and history:
                replay = eval_script_on_history(compiled, dates, prices, max_start, T, up, [req.ticker], r_frac)
                base_at_window_start = history["normalized"][max_start] if max_start < len(history["normalized"]) else None
                if replay and base_at_window_start is not None:
                    barriers = []
                    for b in _monitor_levels(compiled, up, 0):
                        lvl = b.get("level")
                        if lvl is None:
                            continue
                        barriers.append({"name": b["name"], "direction": b.get("direction"),
                                          "level": round(lvl * base_at_window_start, 4)})
                    # Chaque flux porte la date à laquelle le rejeu l'a lu : la
                    # recalculer à 252 séances par an la décalait de quelques
                    # jours par année de maturité.
                    cash_flows = [{"date": cf["date"], "amount": cf["cf"]}
                                  for cf in replay["cash_flows"]]
                    backtest["product"] = {
                        "window_start": dates[max_start],
                        "early_recall": replay["early_recall"],
                        "T_actual": replay["T_actual"],
                        "barriers": barriers,
                        "cash_flows": cash_flows,
                    }

    value_date_new = business_today()
    maturity_date_new = value_date_new + timedelta(days=round(T * 365.25))
    param_term = next((p for p in compiled.params if p.name == req.param_name), None)
    from ...core.product.calendar import freeze_calendar

    return {
        "deal": {"reference": deal.reference, "product_type": deal.product_type,
                 "sens": deal.sens, "devise": deal.devise, "nominal": deal.nominal},
        "candidate": row,
        "script_text": deal.script_snapshot,
        "frozen_calendar": freeze_calendar(compiled),
        "param_desc": (param_term.desc if param_term and param_term.desc else req.param_name),
        "param_is_pct": param_term.is_pct if param_term else True,
        "T": T,
        "value_date": value_date_new.isoformat(),
        "maturity_date": maturity_date_new.isoformat(),
        "backtest": backtest,
    }


@router.post("/{deal_id}/reinvest/proposal")
def reinvest_proposal_endpoint(
    deal_id: int,
    req: ReinvestProposalRequest,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    deal = session.get(Deal, deal_id)
    if not deal or not _can_access_deal(deal, current, session):
        raise HTTPException(404, "Deal introuvable")
    from ...services import archived_documents as archives
    study = None
    if req.study_preview:
        study = archives.verify_preview(req.study_preview, deal, current, purpose="STUDY")
        if req.ticker not in [row["ticker"] for row in study["data"]["results"]]:
            raise HTTPException(422, "Le candidat ne figure pas parmi les alternatives retenues de cette étude.")
        material = ("param_name", "target_price", "lo", "hi", "T", "N", "model", "vol_period", "param_overrides")
        request_values = req.model_dump(mode="json")
        if any(request_values.get(key) != study["request"].get(key) for key in material):
            raise HTTPException(409, "Les hypothèses ont changé depuis le scan ; relancez l'étude.")
    data = _reinvest_proposal_data(deal, req)
    data["study"] = study or {"data": {"results": [data["candidate"]], "excluded": []},
                              "scope": "SINGLE_CANDIDATE"}
    data["parent_archive_id"] = req.parent_archive_id
    return {**data, "preview": archives.sign_preview(data, req.model_dump(mode="json"), deal, current)}


@router.post("/{deal_id}/reinvest/proposal/freeze")
def freeze_reinvest_proposal(
    deal_id: int, body: ProposalFreeze,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    from ...services import archived_documents as archives
    from ...core.reinvest_proposal_pdf import generate_reinvest_proposal_pdf
    deal = session.get(Deal, deal_id)
    if not deal or not _can_access_deal(deal, current, session):
        raise HTTPException(404, "Deal introuvable")
    claims = archives.verify_preview(body.preview, deal, current)
    # Repeated freezes of exactly the same server proof are idempotent.
    from ...db.models import ArchivedDocument
    for existing in session.exec(select(ArchivedDocument).where(
            ArchivedDocument.deal_id == deal_id, ArchivedDocument.user_id == current.id,
            ArchivedDocument.kind == "REINVEST")).all():
        if json.loads(existing.data_json).get("preview_signature") == body.preview["signature"]:
            return {"archive_id": existing.id, "data": json.loads(existing.data_json)["proposal"]}
    proof = {"proposal": claims["data"], "calculation_identity": claims["calculation_identity"],
             "preview_signature": body.preview["signature"], "calculated_at": claims["created_at"],
             "product_id": claims["product_id"], "product_terms_version": claims["product_terms_version"]}
    row = archives.stage(session, kind="REINVEST", deal=deal, user=current,
                         request=claims["request"], data=proof,
                         parent_id=claims["data"].get("parent_archive_id"),
                         pdf=generate_reinvest_proposal_pdf(claims["data"]))
    session.commit()
    return {"archive_id": row.id, "data": claims["data"]}


@router.post("/{deal_id}/reinvest/proposal/pdf")
def reinvest_proposal_pdf_endpoint(
    deal_id: int,
    req: DocumentSelection,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    deal = session.get(Deal, deal_id)
    if not deal or not _can_access_deal(deal, current, session):
        raise HTTPException(404, "Deal introuvable")
    from ...services import archived_documents as archives
    return archives.response(archives.load(session, req.archive_id, kind="REINVEST", deal=deal, user=current))
