"""Yahoo Finance market data — realized vol, dividends, correlations, historical prices."""
from __future__ import annotations
import logging
import math
import numpy as np
from datetime import date, datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

try:
    import yfinance as yf
    import pandas as pd
    _HAS_YF = True
except ImportError:
    _HAS_YF = False
    logger.warning("yfinance not installed — pip install yfinance")


def load_hist_vol(tickers: list[str], period: str = "1y") -> dict:
    """Realized annualized vol + dividend yield + correlation matrix from Yahoo Finance."""
    if not _HAS_YF:
        return {"error": "yfinance non installé — pip install yfinance"}
    try:
        price_series: dict = {}
        for tk in tickers:
            try:
                hist = yf.Ticker(tk).history(period=period, auto_adjust=True)
                if not hist.empty and "Close" in hist.columns:
                    # Each exchange's index is tz-aware in ITS OWN local timezone
                    # (Europe/Paris for ^FCHI, America/New_York for AAPL, etc.) —
                    # combining series across timezones without stripping this
                    # makes pandas treat "same calendar day, different close
                    # time" as distinct rows, so a DataFrame of >1 ticker ends up
                    # almost entirely unaligned (verified: 2 tickers x ~250 daily
                    # rows each merged into ~500 rows of mostly-single-column
                    # data). Normalizing to the naive local date is the standard
                    # (imperfect but industry-standard) fix for daily-close
                    # cross-timezone alignment.
                    hist.index = hist.index.tz_localize(None)
                    s = hist["Close"].dropna()
                    if len(s) > 5:
                        price_series[tk] = s
            except Exception as e:
                logger.debug("YF error %s: %s", tk, e)

        if not price_series:
            return {"error": "Aucune donnée disponible pour ces tickers"}

        prices = pd.DataFrame(price_series).dropna(how="all")
        log_ret = np.log(prices / prices.shift(1)).dropna(how="all")

        vols: dict = {}
        div_yields: dict = {}
        found: list = []
        missing: list = []

        for tk in tickers:
            if tk not in log_ret.columns:
                missing.append(tk)
                continue
            s = log_ret[tk].dropna()
            if len(s) < 10:
                missing.append(tk)
                continue
            vols[tk] = round(float(s.std() * math.sqrt(252)), 4)
            found.append(tk)
            try:
                # fast_info.dividend_yield doesn't exist on current yfinance
                # (0.2.66) — silently returned 0.0 for every ticker via the
                # getattr(..., 0.0) fallback. info['dividendYield'] exists but
                # is pre-multiplied by 100 (0.34 means 0.34%, not a fraction)
                # — trailingAnnualDividendYield is the one field that's a
                # plain fraction, consistent with what UnderlyingParams.q
                # expects. None for tickers with no per-security dividend
                # data (indices) — 0.0 is the right fallback there.
                info = yf.Ticker(tk).get_info()
                dy = info.get("trailingAnnualDividendYield") or 0.0
                div_yields[tk] = round(float(dy), 4)
            except Exception:
                div_yields[tk] = 0.0

        cols = [tk for tk in found if tk in log_ret.columns]
        corr: dict = {}
        if len(cols) > 1:
            corr_df = log_ret[cols].corr()
            for t1 in cols:
                corr[t1] = {t2: round(float(corr_df.loc[t1, t2]), 4) for t2 in cols}
        else:
            for tk in found:
                corr[tk] = {tk: 1.0}

        return {
            "tickers": found,
            "vols": vols,
            "div_yields": div_yields,
            "corr": corr,
            "period": period,
            "n_obs": int(len(log_ret)),
            "missing": missing,
        }
    except Exception as e:
        logger.exception("load_hist_vol")
        return {"error": str(e)}


def load_hist_prices(tickers: list[str], start: str, end: Optional[str] = None) -> dict:
    """Daily close prices for backtest replay."""
    if not _HAS_YF:
        return {"error": "yfinance non installé"}
    try:
        end = end or datetime.today().strftime("%Y-%m-%d")
        price_series: dict = {}
        for tk in tickers:
            try:
                hist = yf.Ticker(tk).history(start=start, end=end, auto_adjust=True)
                if not hist.empty and "Close" in hist.columns:
                    # Same cross-timezone alignment fix as load_hist_vol above —
                    # without it, a multi-ticker basket backtest silently
                    # compares near-random staggered rows instead of the same
                    # calendar day across exchanges.
                    hist.index = hist.index.tz_localize(None)
                    price_series[tk] = hist["Close"].dropna()
            except Exception as e:
                logger.debug("YF prices error %s: %s", tk, e)

        if not price_series:
            return {"error": "Aucune donnée historique disponible"}

        frame = pd.DataFrame(price_series).dropna(how="all").ffill()
        requested_start = frame.index.min() if not frame.empty else None

        # `.bfill()` used to close the remaining holes. Forward filling is
        # legitimate — a closed exchange means the last close still stands,
        # and it only ever uses information already available. Backward
        # filling is the opposite: it copies a ticker's FIRST KNOWN close
        # onto dates that precede it, so a listing, a ticker change or a
        # suspension gets a price on days it had none. Measured on a series
        # starting five days into the window: five fabricated zero returns,
        # realized volatility understated by 21.8%, and a barrier that can
        # never be breached over the fabricated stretch because the level
        # sits wherever the first real quote happened to be — a bias that
        # systematically FAVOURS the product being backtested.
        #
        # After ffill the only holes left are the leading ones, so dropping
        # incomplete rows starts the basket at the first date every
        # constituent actually traded. A worst-of cannot be replayed before
        # its worst member existed.
        prices = frame.dropna()
        dates = [d.strftime("%Y-%m-%d") for d in prices.index]

        payload = {
            "dates": dates,
            "prices": {
                tk: [round(v, 4) for v in prices[tk].tolist()]
                for tk in tickers
                if tk in prices.columns
            },
            "n_obs": len(dates),
        }
        # Say when the window had to be shortened, rather than returning a
        # shorter history that looks like the one that was asked for.
        if not prices.empty and requested_start is not None:
            effective_start = prices.index.min()
            if effective_start > requested_start:
                skipped = int((frame.index < effective_start).sum())
                payload["start_effective"] = effective_start.strftime("%Y-%m-%d")
                payload["rows_dropped_incomplete"] = skipped
                payload["note"] = (
                    f"Historique tronqué au {effective_start.strftime('%Y-%m-%d')} : "
                    f"{skipped} séance(s) écartée(s) car au moins un sous-jacent "
                    f"n'y cotait pas encore.")
        elif prices.empty and not frame.empty:
            return {"error": "Aucune séance où tous les sous-jacents cotent "
                             "simultanément sur la période demandée."}
        return payload
    except Exception as e:
        logger.exception("load_hist_prices")
        return {"error": str(e)}


def load_yahoo_reference_closes(
    tickers: list[str], start: str, end: Optional[str] = None,
) -> dict:
    """Load unadjusted Yahoo closes without cross-ticker backfilling.

    This feed is deliberately separate from ``load_hist_prices``.  Backtests
    and indicative monitoring use adjusted/aligned series; contractual
    fixings must retain the raw close reported for each ticker and market
    date.  ``series`` therefore keeps one independent date/value mapping per
    ticker and records stock splits for the automated exception controls.
    """
    if not _HAS_YF:
        return {"error": "yfinance non installé"}
    try:
        last_day = date.fromisoformat(end) if end else date.today()
        # yfinance's ``end`` bound is exclusive.  Add one day so a close
        # already published on the requested end date is not silently lost.
        end_exclusive = (last_day + timedelta(days=1)).isoformat()
        series: dict[str, dict[str, float]] = {}
        splits: dict[str, dict[str, float]] = {}
        currencies: dict[str, str] = {}
        missing: list[str] = []
        for ticker in tickers:
            try:
                instrument = yf.Ticker(ticker)
                hist = instrument.history(
                    start=start,
                    end=end_exclusive,
                    auto_adjust=False,
                    actions=True,
                )
                if hist.empty or "Close" not in hist.columns:
                    missing.append(ticker)
                    continue
                hist.index = hist.index.tz_localize(None)
                closes: dict[str, float] = {}
                split_rows: dict[str, float] = {}
                for timestamp, value in hist["Close"].dropna().items():
                    numeric = float(value)
                    if math.isfinite(numeric):
                        closes[timestamp.strftime("%Y-%m-%d")] = round(numeric, 8)
                if "Stock Splits" in hist.columns:
                    for timestamp, value in hist["Stock Splits"].dropna().items():
                        numeric = float(value)
                        if math.isfinite(numeric) and abs(numeric) > 1e-12:
                            split_rows[timestamp.strftime("%Y-%m-%d")] = numeric
                if closes:
                    series[ticker] = closes
                    splits[ticker] = split_rows
                    try:
                        currency = instrument.fast_info.get("currency")
                        if currency:
                            currencies[ticker] = str(currency).upper()
                    except Exception:
                        # Currency is a quality control when Yahoo exposes it,
                        # not a reason to discard an otherwise timestamped raw
                        # close when the metadata endpoint itself is down.
                        pass
                else:
                    missing.append(ticker)
            except Exception as exc:
                logger.debug("Yahoo reference close error %s: %s", ticker, exc)
                missing.append(ticker)
        if not series:
            return {"error": "Aucune clôture Yahoo non ajustée disponible"}
        return {
            "provider": "YAHOO_FINANCE",
            "price_type": "UNADJUSTED_CLOSE",
            "fetched_at": datetime.utcnow().isoformat(),
            "series": series,
            "splits": splits,
            "currencies": currencies,
            "missing": sorted(set(missing)),
        }
    except Exception as exc:
        logger.exception("load_yahoo_reference_closes")
        return {"error": str(exc)}
