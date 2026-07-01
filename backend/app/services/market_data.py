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
                info = yf.Ticker(tk).fast_info
                dy = getattr(info, "dividend_yield", 0.0) or 0.0
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
