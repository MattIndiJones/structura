"""Yahoo Finance market data — realized vol, dividends, correlations, historical prices."""
from __future__ import annotations
import logging
import math
import numpy as np
from datetime import datetime
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

        prices = pd.DataFrame(price_series).dropna(how="all").ffill().bfill()
        dates = [d.strftime("%Y-%m-%d") for d in prices.index]

        return {
            "dates": dates,
            "prices": {
                tk: [round(v, 4) for v in prices[tk].tolist()]
                for tk in tickers
                if tk in prices.columns
            },
            "n_obs": len(dates),
        }
    except Exception as e:
        logger.exception("load_hist_prices")
        return {"error": str(e)}
