"""One dated statistical market for all prepared CCR residual contracts."""
from copy import deepcopy
from datetime import date
import json
import numpy as np

from ..calibration import calibration_history_start, realized_market
from ..compute.pricers.var_scenario import residual_script_from_payload
from ..schemas import validate_correlation_matrix
from ..valuation_context import canonical_fingerprint, deterministic_cashflow_pv, run_valuation
from ...services.market_data import market_data_provider_for_deal


def harmonize_market(trades, deals, session, request, histories, progress=None):
    """Return a new coherent book and its evidence, or leave the input untouched."""
    candidates = {}
    by_id = {d.id: d for d in deals}
    providers = set()
    for trade in trades:
        ctx = trade.get("replay", {}).get("valuation_context")
        if not ctx or trade.get("missing"):
            continue
        if ctx["model"] != "constant":
            raise ValueError(f"{trade['reference']} : marché commun CCR réservé au GBM ; aucun changement implicite de modèle")
        deal = by_id[trade["deal_id"]]
        providers.add(market_data_provider_for_deal(deal, session))
        for u in ctx["underlyings"]:
            ticker = u.get("ticker") or u["name"]
            candidates.setdefault(ticker, []).append((deal.trade_date or "", deal.id, trade["reference"], u))
    if not candidates:
        return trades, {"policy": "HISTORICAL_252D", "factors": {}, "tickers": []}
    if len(providers) != 1:
        raise ValueError("Fournisseurs différents entre deals : choisir une source commune avant la calibration CCR")
    tickers = sorted(candidates)
    if progress:
        progress({"stage": "common_market", "phase": "history", "total": len(tickers)})
    data = histories(tickers, calibration_history_start(request.as_of_date).isoformat(),
        request.as_of_date.isoformat(), provider=next(iter(providers)), adjusted=True)
    calibrated = realized_market(data["prices"], tickers, window_days=252)
    matrix = deepcopy(calibrated["corr"])
    for i, a in enumerate(tickers):
        for j, b in enumerate(tickers):
            pair = "|".join(sorted((a, b)))
            if pair in request.correlations:
                matrix[i][j] = request.correlations[pair]
    validate_correlation_matrix(matrix, len(tickers))
    if np.linalg.eigvalsh(matrix).min() < -1e-10:
        raise ValueError("Les surcharges de corrélation rendent la matrice commune non semi-définie positive")
    factors = {}
    for ticker, values in candidates.items():
        # Quanto terms can depend on the settlement currency. Do not erase a
        # real contractual difference to force a common equity diffusion.
        for key in ("sigma_fx", "rho_sfx", "ccyh"):
            if max(v[3].get(key, 0) for v in values) - min(v[3].get(key, 0) for v in values) > 1e-10:
                raise ValueError(f"{ticker} : paramètres quanto incompatibles ({key})")
        latest = max(values, key=lambda v: (v[0], v[1]))
        u = latest[3]
        booked = json.loads(getattr(by_id[latest[1]], "market_snapshot_json", None) or "{}")
        quote = next((v for v in booked.get("underlyings", [])
                      if (v.get("ticker") or v.get("name")) == ticker or v.get("name") == u["name"]), {})
        q = float(quote["q"]) / 100 if quote.get("q") is not None else u["q"]
        q_source = "LATEST_BOOKING_ASSUMPTION" if quote.get("q") is not None else "REFERENCE_DEAL_CONTEXT"
        override = request.market_overrides.get(ticker)
        if (u.get("dividend_curve") or quote.get("dividendCurve")) and (not override or override.q is None):
            raise ValueError(f"{ticker} : courbe de dividendes non prise en charge par la projection GBM ; saisir un q plat explicite")
        factors[ticker] = {
            "sigma": override.sigma if override and override.sigma is not None else calibrated["sigma"][ticker],
            "sigma_source": "USER_OVERRIDE" if override and override.sigma is not None else "REALIZED_252D",
            "q": override.q if override and override.q is not None else q,
            "q_source": "USER_OVERRIDE" if override and override.q is not None else q_source,
            "q_reference": latest[2], "q_deal_id": latest[1], "q_trade_date": latest[0],
        }
    output = deepcopy(trades)
    for index, trade in enumerate(output):
        ctx = trade.get("replay", {}).get("valuation_context")
        if not ctx or trade.get("missing"):
            continue
        if progress:
            progress({"stage": "common_market", "phase": "repricing", "reference": trade["reference"],
                      "completed": index, "total": len(output)})
        keys = [u.get("ticker") or u["name"] for u in ctx["underlyings"]]
        for key, u in zip(keys, ctx["underlyings"]):
            u.update(sigma=factors[key]["sigma"], q=factors[key]["q"], dividend_curve=[])
        ctx["corr_matrix"] = [[matrix[tickers.index(a)][tickers.index(b)] for b in keys] for a in keys]
        trade["replay"]["corr"] = deepcopy(ctx["corr_matrix"])
        trade["mtm_fraction"] = run_valuation(residual_script_from_payload(trade["replay"]), ctx)["price"]
        for flow in trade.get("unsettled_flows", []):
            remaining = (date.fromisoformat(flow["payment_date"]) - request.as_of_date).days / 365.25
            trade["mtm_fraction"] += deterministic_cashflow_pv(flow["cf"], remaining, r=ctx["r"], yield_curve=ctx.get("yield_curve"))
        prep = trade.setdefault("preparation", {})
        prep["before_common_market"] = deepcopy(prep.get("effective_context"))
        prep.update(source="CCR_COMMON_MARKET_REVALUED", effective_context=deepcopy(ctx))
    return output, {"policy": "HISTORICAL_252D", "as_of_date": str(request.as_of_date),
        "n_returns": calibrated["n_returns"], "window_requested": 252,
        "effective_start": data["dates"][-(calibrated["n_returns"] + 1)], "effective_end": data["dates"][-1],
        "history_fingerprint": canonical_fingerprint(data), "provider": data.get("provider"),
        "history_sources": data.get("sources"), "price_type": data.get("price_type"),
        "estimator": "RMS log returns annualized sqrt(252); Pearson; numerical eigenvalue floor 1e-10",
        "tickers": tickers, "factors": factors, "calibrated_correlation": calibrated["corr"], "correlation": matrix}
