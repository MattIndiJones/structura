"""Prepare clean CCR valuations without changing official Booking valuations."""
from copy import deepcopy
from datetime import date
import json
import time

import pandas as pd
import numpy as np
from fastapi import HTTPException

from ...db.models import Deal, ValuationRun
from ...services import market_data
from ..deal_valuation import MtmRequest, mtm_core
from ..market_snapshot import snapshot_rate
from ..valuation_context import canonical_fingerprint, deterministic_cashflow_pv, run_valuation
from ..valuation_runs import replay_context, _data_versions, engine_identity
from ..compute.pricers.var_scenario import residual_script_from_payload


class MarketHistory:
    """Per-run immutable history cache: supplied data, local raw store/cache, fetch."""
    def __init__(self, request, archived=None):
        self.request = request
        self.evidence = {}
        self.cache = {}
        self.archived = archived or []

    def __call__(self, tickers, start, end, *, provider=market_data.DEFAULT_MARKET_DATA_PROVIDER, adjusted=False):
        key = (provider, tuple(tickers), start, end, adjusted)
        if key in self.cache:
            return deepcopy(self.cache[key])
        from ..amc_prices import _load_ticker_map, load_prices
        mapping = _load_ticker_map()
        series, sources = {}, {}
        for ticker in tickers:
            manual = None if adjusted else self.request.price_histories.get(ticker)
            if manual:
                series[ticker] = pd.Series(manual.closes, index=pd.to_datetime([str(d) for d in manual.dates]))
                sources[ticker] = "USER_SUPPLIED_UNADJUSTED_CLOSE"
            else:
                for name in [ticker] + sorted(k for k, v in mapping.items() if v == ticker):
                    try:
                        frame = load_prices(name)
                    except (ValueError, OSError):
                        continue
                    # The adjusted 'close' is never a substitute for a fixing.
                    # AMC normalizes London pence to pounds; contractual raw
                    # prices have no equivalent unit conversion in this path.
                    column = "close" if adjusted else "price_close"
                    if column in frame and (adjusted or not ticker.upper().endswith(".L")):
                        raw = frame[column].copy()
                        raw.index = pd.to_datetime(raw.index).tz_localize(None)
                        series[ticker] = raw.sort_index()
                        sources[ticker] = f"LOCAL_{'ADJUSTED' if adjusted else 'RAW'}_STORE:{name}"
                        break
        def usable(values):
            if set(values) != set(tickers):
                return False
            for values_ in values.values():
                window = values_.loc[(values_.index >= start) & (values_.index <= end)]
                if (window.empty or (window.index[0].date() - date.fromisoformat(start)).days > 7
                        or market_data._business_sessions_between(window.index[-1].date(), date.fromisoformat(end)) > 1
                        or (window <= 0).any() or not np.isfinite(window).all()
                        or window.index.has_duplicates
                        or window.index.to_series().diff().dt.days.max() > 10):
                    return False
            return True
        # Preserve the prices already frozen for this as-of before considering
        # another provider request. Manual contractual inputs remain primary.
        for saved in self.archived:
            if (bool(saved.get("adjusted")) != adjusted
                    or saved.get("provider") not in {provider, "LOCAL"}
                    or saved.get("requested_end") != end
                    or not saved.get("requested_start") or saved["requested_start"] > start
                    or not set(tickers).issubset(saved.get("prices", {}))
                    or (not adjusted and any(t in self.request.price_histories for t in tickers))):
                continue
            values = {t: pd.Series(saved["prices"][t], index=pd.to_datetime(saved["dates"])) for t in tickers}
            if not usable(values):
                continue
            indices = [i for i,d in enumerate(saved["dates"]) if start <= d <= end]
            payload = {**deepcopy(saved), "dates": [saved["dates"][i] for i in indices],
                "prices": {t:[saved["prices"][t][i] for i in indices] for t in tickers}, "requested_start": start}
            payload["n_obs"] = len(indices)
            for field in ("sources", "effective_dates", "age_sessions"):
                if field in payload:
                    payload[field] = {t: payload[field][t] for t in tickers if t in payload[field]}
            self.evidence[canonical_fingerprint(payload)] = deepcopy(payload)
            self.cache[key] = deepcopy(payload)
            return payload
        if usable(series):
            frame = pd.DataFrame(series).sort_index().ffill().dropna()
            frame = frame.loc[(frame.index >= start) & (frame.index <= end)]
            payload = {"dates": [str(t.date()) for t in frame.index],
                       "prices": {t: frame[t].tolist() for t in tickers}, "provider": "LOCAL",
                       "price_type": "ADJUSTED_CLOSE" if adjusted else "UNADJUSTED_CLOSE", "adjusted": adjusted, "sources": sources,
                       "requested_start": start, "requested_end": end,
                       "asof_effective": str(frame.index[-1].date())}
        else:
            # An explicitly supplied incomplete series must not silently fall
            # back to a different provider.
            if not adjusted and any(t in self.request.price_histories for t in tickers):
                raise ValueError("Historique manuel incomplet : couvrir le strike et la date d'arrêté pour tous les tickers du panier")
            cache_key = (provider, tuple(sorted(tickers)), start, end, adjusted)
            cached = market_data._cache_prix.get(cache_key)
            if cached and time.monotonic() - cached[0] < market_data._TTL_PRIX:
                payload = deepcopy(cached[1])
            elif self.request.allow_market_fetch:
                payload = market_data.load_hist_prices(tickers, start, end, adjusted=adjusted, provider=provider)
            else:
                raise ValueError("Historique ajusté local insuffisant pour le marché commun : autoriser la récupération de marché" if adjusted else "Historique brut local insuffisant : autoriser la récupération de marché ou fournir les clôtures dans le panneau CCR")
            if "error" in payload:
                raise ValueError(payload["error"])
            values = {t: pd.Series(v, index=pd.to_datetime(payload["dates"])) for t, v in payload.get("prices", {}).items()}
            if not usable(values):
                raise ValueError("Historique incomplet ou périmé à la date demandée")
        self.evidence[canonical_fingerprint(payload)] = deepcopy(payload)
        self.cache[key] = deepcopy(payload)
        return payload


def adjust_context(context, request):
    context = deepcopy(context)
    context.update(funding_curve=[], funding_spread=0., N=request.mtm_paths, seed=request.seed)
    if request.common_rate is not None:
        context.update(r=request.common_rate, yield_curve=[])
    keys = [u.get("ticker") or u["name"] for u in context["underlyings"]]
    for key, ul in zip(keys, context["underlyings"]):
        override = request.market_overrides.get(key)
        if not override:
            continue
        if override.sigma is not None:
            if context["model"] != "constant":
                raise ValueError(f"{key} : surcharge sigma plate réservée au GBM ; aucun changement implicite de modèle")
            ul["sigma"] = override.sigma
        if override.q is not None:
            ul.update(q=override.q, dividend_curve=[])
    for i, a in enumerate(keys):
        for j, b in enumerate(keys):
            pair = "|".join(sorted((a, b)))
            if pair in request.correlations:
                context["corr_matrix"][i][j] = request.correlations[pair]
    from ..schemas import validate_correlation_matrix
    validate_correlation_matrix(context["corr_matrix"], len(keys))
    return context


def prepare_trade(session, deal, trade, request, histories, progress):
    """Reuse a valid residual snapshot, or build it through the existing MtM core."""
    original = deepcopy(trade)
    row = session.get(ValuationRun, trade.get("valuation_run_id")) if trade.get("valuation_run_id") else None
    reusable = row is not None and json.loads(row.data_versions_json).get("events", []) == _data_versions(session, deal.id)["events"]
    tickers = {u.get("ticker") for u in json.loads(deal.underlyings_json or "[]")}
    if request.refresh_mtm or tickers.intersection(request.price_histories):
        reusable = False  # Explicit histories must affect the replayed past.
    if reusable:
        payload_market = trade.get("settlement_valuation_market", {})
        source = "SAVED_RESIDUAL_CONTEXT"
    else:
        if deal.counterparty_id is None and request.counterparty_id:
            raise ValueError("Contrepartie historique sans identifiant juridique : rattachement à régulariser")
        # Detached copy only: no UPDATE to the deal or its booking snapshot.
        detached = Deal.model_validate(deal.model_dump())
        market = json.loads(detached.market_snapshot_json or "{}")
        market.update(funding={}, funding_curve=[], funding_spread=0.)
        detached.market_snapshot_json = json.dumps(market)
        history_sources = []
        def load_history(tickers, start, end):
            data = histories(tickers, start, end,
                provider=market_data.market_data_provider_for_deal(deal, session))
            history_sources.append({"fingerprint": canonical_fingerprint(data),
                **{key: data[key] for key in ("provider", "sources", "requested_start", "requested_end", "asof_effective", "reused_from_run_id") if key in data}})
            return data
        payload, context = mtm_core(detached, session, n_paths=request.mtm_paths,
            body=MtmRequest(valuation_date=request.as_of_date,
                            r=None if request.common_rate is None else request.common_rate * 100),
            load_prices=load_history, progress=progress)
        if context is None or payload.get("mtm") is None:
            raise ValueError(payload.get("message", "Contexte résiduel non disponible"))
        trade.update(replay=replay_context(detached, context, payload), mtm_fraction=payload["mtm"],
                     unsettled_flows=payload.get("unsettled_cash_flows", []),
                     payment_date=payload.get("payment_date") or deal.payment_date,
                     settlement_amount=payload.get("settlement_amount", deal.settlement_amount),
                     settlement_market=market, settlement_valuation_market=payload.get("market_used", {}))
        trade.pop("missing", None)
        payload_market = payload.get("market_used", {})
        payload_market["history_sources"] = history_sources
        source = "CCR_RESIDUAL_MTM"
    replay = deepcopy(trade["replay"])
    if replay.get("settlement_claim"):
        rate = request.common_rate
        if rate is None:
            rate = (payload_market["r"] / 100 if "r" in payload_market else snapshot_rate(json.loads(deal.market_snapshot_json or "{}")))
        remaining = (date.fromisoformat(trade["payment_date"]) - request.as_of_date).days / 365.25
        amount = trade.get("settlement_amount")
        if amount is None or remaining <= 0:
            raise ValueError("Montant ou date de règlement manquant/incompatible")
        market = trade.get("settlement_market", {})
        curve = [] if request.common_rate is not None else [[p["T"], p["rate"] / 100] for p in market.get("yieldCurve") or []]
        trade["mtm_fraction"] = deterministic_cashflow_pv(amount, remaining, r=rate, yield_curve=curve)
        replay["fixed_price"] = trade["mtm_fraction"]
        trade.update(settlement_market={"yieldCurve": [{"T":t,"rate":r*100} for t,r in curve]}, settlement_valuation_market={"r": rate * 100, "funding_spread": 0})
        effective = {"model": "deterministic_cashflow", "r": rate, "yield_curve": curve, "funding_spread": 0}
    else:
        before = replay["valuation_context"]
        effective = adjust_context(before, request)
        replay["valuation_context"] = effective
        if not reusable or effective != before or row.engine_fingerprint != engine_identity()[1]:
            progress("repricing")
            trade["mtm_fraction"] = run_valuation(residual_script_from_payload(replay), effective)["price"]
            for flow in trade.get("unsettled_flows", []):
                remaining = (date.fromisoformat(flow["payment_date"]) - request.as_of_date).days / 365.25
                trade["mtm_fraction"] += deterministic_cashflow_pv(flow["cf"], remaining,
                    r=effective["r"], yield_curve=effective.get("yield_curve"))
            if reusable:
                source = "SAVED_CONTEXT_REVALUED"
        else:
            source = "SAVED_MTM_REUSED"
    trade["replay"] = replay
    trade["preparation"] = {"source": source, "source_valuation_run_id": original.get("valuation_run_id"),
        "as_of_date": str(request.as_of_date), "original_market": original.get("replay", {}).get("valuation_context", payload_market),
        "booking_market": json.loads(deal.market_snapshot_json or "{}"),
        "market_provenance": payload_market, "effective_context": effective, "clean_credit": True}
    return trade
