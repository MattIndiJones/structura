"""Shared durable provider observations, separate from pricing assumptions."""
from __future__ import annotations
from datetime import datetime, timezone
from hashlib import sha256
import json
from contextlib import nullcontext

import numpy as np
import pandas as pd

from ..runtime import data_path
from ..core import market_policy
from ..core import market_storage


def _path(ticker, adjusted):
    root = data_path("market_history", "adjusted" if adjusted else "unadjusted")
    return root / (sha256(ticker.upper().encode()).hexdigest()+".parquet")


def clean_series(series):
    out = pd.to_numeric(series, errors="coerce").copy()
    out.index = pd.to_datetime(out.index).tz_localize(None).normalize()
    out = out[~out.index.duplicated(keep="last")].sort_index()
    return out.where(np.isfinite(out) & (out > 0)).dropna()


def store_history(ticker, series, adjusted, requested_start, requested_end, *, transaction=None):
    path = _path(ticker, adjusted)
    frame = market_storage.validate_frame(series.to_frame('close'))
    with (nullcontext(transaction) if transaction else market_storage.transaction()) as pending:
        stored = pending.path(path)
        if stored.exists() and not adjusted:
            old = market_storage.validate_frame(pd.read_parquet(stored))
            frame = pd.concat([old, frame]).loc[lambda x: ~x.index.duplicated(keep="last")].sort_index()
            requested_start = min(requested_start, old.attrs.get("requested_start", requested_start))
            requested_end = max(requested_end, old.attrs.get("requested_end", requested_end))
        frame.attrs.update(ticker=ticker, provider="YAHOO_FINANCE", adjusted=bool(adjusted),
                           price_type="ADJUSTED_CLOSE" if adjusted else "UNADJUSTED_CLOSE",
                           requested_start=requested_start, requested_end=requested_end,
                           fetched_at=datetime.now(timezone.utc).isoformat(), finality="UNVERIFIED_PROVIDER_BAR")
        pending.parquet(path, frame)


@market_storage.consistent_read
def local_history(ticker, start, end, adjusted):
    """Select a complete local basis before considering an external fetch."""
    candidates = []
    path = market_storage.current_path(_path(ticker, adjusted))
    if path.exists():
        try:
            frame = pd.read_parquet(path)
            series = clean_series(frame["close"])
            candidates.append((series, {**frame.attrs, "storage": "MARKET_HISTORY", "record_id": path.name}))
        except (OSError, ValueError, KeyError):
            pass
    from ..core import amc_prices
    for key, symbol in amc_prices._load_ticker_map().items():
        if symbol.upper() != ticker.upper():
            continue
        try:
            frame = amc_prices.load_prices(key)
            field = "close" if adjusted else "price_close"
            if field not in frame or not str(frame.attrs.get("source", "")).startswith("yahoo:"):
                continue
            series = clean_series(frame[field])
            # AMC stores London stocks in GBP; restore provider pence here.
            if amc_prices.is_gbx_ticker(ticker, frame.attrs.get("currency", "")):
                series = series*100
            if series.empty:
                continue
            candidates.append((series, {"provider": "YAHOO_FINANCE", "storage": "AMC_PRICES", "field": field,
                            "adjusted": bool(adjusted), "requested_start": frame.attrs.get("requested_start", series.index.min().date().isoformat()),
                            "requested_end": frame.attrs.get("requested_end", series.index.max().date().isoformat()),
                            "fetched_at": frame.attrs.get("fetched_at"), "finality": "UNVERIFIED_PROVIDER_BAR"}))
        except (OSError, ValueError, KeyError):
            continue
    def coverage(candidate):
        series, source = candidate
        observed = series.loc[(series.index >= pd.Timestamp(start)) & (series.index <= pd.Timestamp(end))]
        if observed.empty:
            return False, pd.Timestamp.min, 0
        effective = observed.index[-1]
        complete = (source.get('requested_start', start) <= start
                    and market_policy.freshness(effective.date(), end, 'history')['qualified'])
        return complete, effective, len(observed)
    return max(candidates, key=coverage) if candidates else (None, {})


def _profile_path(ticker, asof, window):
    key = json.dumps([ticker.upper(), asof, float(window)])
    return data_path("market_history", "dividends", sha256(key.encode()).hexdigest()+".json")


def local_profile(ticker, asof, window):
    path = market_storage.current_path(_profile_path(ticker, asof, window))
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return {**value, "storage": "MARKET_HISTORY"} if value.get("ok") else None
    except (OSError, ValueError):
        return None


def store_profile(ticker, asof, window, value, *, transaction=None):
    path = _profile_path(ticker, asof, window)
    with (nullcontext(transaction) if transaction else market_storage.transaction()) as pending:
        pending.json(path, value)


def align_history(tickers, series, start, end, adjusted, sources, failures, allow_partial=False):
    """Align bounded carry without manufacturing leading or suspended prices."""
    frame = pd.DataFrame(series).sort_index()
    frame.index = pd.to_datetime(frame.index)
    frame = frame.loc[(frame.index >= pd.Timestamp(start)) & (frame.index <= pd.Timestamp(end))]
    origins = pd.DataFrame({tk: pd.Series(s.index, index=s.index) for tk, s in series.items()}).reindex(frame.index).ffill()
    ages = pd.DataFrame({tk: (frame.index.to_series()-origins[tk]).dt.days for tk in frame})
    maximum = market_policy.HISTORY_MAX_AGE_DAYS
    bounded = frame.ffill().where(ages <= (maximum if maximum is not None else 0))
    excluded, included, effective, last_quality = [], [], {}, {}
    for ticker in tickers:
        if ticker not in series or series[ticker].empty:
            excluded.append(dict(ticker=ticker, reason=failures.get(ticker, "NO_OBSERVATIONS")))
            continue
        effective[ticker] = series[ticker].index.max().date().isoformat()
        quality = market_policy.freshness(effective[ticker], end, "history")
        last_quality[ticker] = quality
        bad = ages[ticker].notna() & (ages[ticker] > (maximum if maximum is not None else 0))
        gaps = series[ticker].index.to_series().diff().dt.days.dropna()-1
        long_gaps = int((gaps > (maximum if maximum is not None else 0)).sum())
        if not quality["qualified"] or bad.any() or long_gaps:
            excluded.append(dict(ticker=ticker, reason=quality["status"] if not quality["qualified"] else "UNBOUNDED_HISTORY_GAP",
                                 freshness=quality, invalid_rows=int(bad.sum()), long_gaps=long_gaps))
        else:
            included.append(ticker)
    prices = bounded[included].dropna() if included else pd.DataFrame()
    dates = [d.date().isoformat() for d in prices.index]
    payload = dict(dates=dates, prices={tk: [float(x) for x in prices[tk]] for tk in included},
                   n_obs=len(dates), requested_start=start, requested_end=end, requested_tickers=list(tickers),
                   missing=[row["ticker"] for row in excluded], missing_reasons={row["ticker"]:row for row in excluded},
                   provider="YAHOO_FINANCE", adjusted=bool(adjusted),
                   price_type="ADJUSTED_CLOSE" if adjusted else "UNADJUSTED_CLOSE",
                   asof_effective=dates[-1] if dates else None, effective_dates=effective,
                   freshness=last_quality, sources=sources, finality="UNVERIFIED_PROVIDER_BAR",
                   coverage=dict(requested=list(tickers), included=included, excluded=excluded,
                                 complete=not excluded and bool(dates), allow_partial=bool(allow_partial)),
                   source_observation_dates={tk:[x.date().isoformat() for x in origins.loc[prices.index,tk]] for tk in included},
                   carry_age_days={tk:[int(x) for x in ages.loc[prices.index,tk]] for tk in included})
    carried = {tk:sum(x > 0 for x in payload["carry_age_days"][tk]) for tk in included}
    payload["warnings"] = ([dict(code="BOUNDED_CARRY", carried_rows=carried,
                                 message="Clôtures reportées : dates sources et anciennetés disponibles ; finalité non certifiée.")]
                           if any(carried.values()) else [])
    if excluded:
        payload["warnings"].append(dict(code="INCOMPLETE_HISTORY", excluded=excluded,
                                         message="Périmètre historique incomplet ou hors politique."))
    if not dates or (excluded and not allow_partial):
        payload["error"] = "Historique incomplet ou hors politique : " + ", ".join(
            f"{row['ticker']} ({row['reason']})" for row in excluded)
        if not allow_partial:
            payload["prices"] = {}
    elif dates[0] > start:
        payload["start_effective"] = dates[0]
        payload["rows_dropped_incomplete"] = int((frame.index < prices.index.min()).sum())
        payload["note"] = f"Historique commun à partir du {dates[0]} ; aucun cours antérieur inventé."
    return payload


@market_storage.consistent_read
def storage_status(ticker, asof):
    bases = {}
    for adjusted, field in ((False, "unadjusted"), (True, "adjusted")):
        series, source = local_history(ticker, "1900-01-01", asof, adjusted)
        if series is None or series.empty:
            bases[field] = dict(available=False, qualified=False, status="MISSING")
            continue
        series = series.loc[series.index <= pd.Timestamp(asof)]
        effective = series.index[-1].date().isoformat() if not series.empty else None
        quality = market_policy.freshness(effective, asof, "history")
        maximum = market_policy.HISTORY_MAX_AGE_DAYS
        gaps = series.index.to_series().diff().dt.days.dropna()-1
        long_gaps = int((gaps > (maximum if maximum is not None else 0)).sum())
        bases[field] = dict(available=not series.empty, rows=len(series), source=source,
                            date_min=series.index.min().date().isoformat() if not series.empty else None,
                            date_max=effective, freshness=quality, long_gaps=long_gaps,
                            qualified=quality["qualified"] and not long_gaps,
                            status="HISTORY_GAPS" if long_gaps else quality["status"])
    usable = all(row["qualified"] for row in bases.values())
    available = any(row["available"] for row in bases.values())
    present = [row for row in bases.values() if row["available"]]
    return dict(ticker=ticker, bases=bases, available=available, consumer_available=usable,
                rows=min((row["rows"] for row in present), default=0),
                date_min=max((row["date_min"] for row in present), default=None),
                date_max=min((row["date_max"] for row in present), default=None),
                cache_status="ok" if usable else "unqualified" if available else "missing",
                consumers=["PAYOFF_UNADJUSTED", "REALIZED_ADJUSTED"],
                finality="UNVERIFIED_PROVIDER_BAR")
