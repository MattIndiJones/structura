"""Dated optimizer references built from the existing historical services."""
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import date, datetime, timezone
import math
import threading
import time

from pydantic import Field, model_validator

from ..core.product_optimizer.contracts import StrictModel
from .market_data import load_hist_vol, dividend_profile


class MarketReferenceRequest(StrictModel):
    tickers: list[str] = Field(min_length=1, max_length=3)
    pricing_date: date
    currency: str = Field(min_length=3, max_length=3)

    @model_validator(mode="after")
    def valid(self):
        if len(set(self.tickers)) != len(self.tickers) or any(not t.strip() or len(t) > 40 for t in self.tickers):
            raise ValueError("Choisissez des tickers distincts et renseignés dans l’Optimizer.")
        if self.pricing_date > date.today() or self.pricing_date.year < 2000:
            raise ValueError("Date de pricing entre 2000 et aujourd’hui ; aucune clôture future n’est disponible.")
        return self


_cache = OrderedDict()
_lock = threading.Lock()


def _number(value, high):
    return value if isinstance(value, (int, float)) and math.isfinite(value) and 0 <= value <= high else None


def load_optimizer_references(tickers, pricing_date):
    """Reuse dated references in memory, preserving missing fields and diagnostics."""
    key = (tuple(tickers), pricing_date)
    with _lock:
        saved = _cache.get(key)
        if saved and time.monotonic() - saved[0] < 300:
            _cache.move_to_end(key)
            return deepcopy(saved[1])
    with ThreadPoolExecutor(max_workers=3) as pool:
        vol_job = pool.submit(load_hist_vol, tickers, asof=pricing_date, window_days=252)
        div_jobs = {ticker: pool.submit(dividend_profile, ticker, asof=pricing_date) for ticker in tickers}
        vol = vol_job.result()
        dividends = {ticker: job.result() for ticker, job in div_jobs.items()}
    fetched = datetime.now(timezone.utc).isoformat()
    result = {"pricing_date": pricing_date, "captured_at": fetched, "underlyings": [],
              "correlation": None, "provenance": {}, "warnings": []}
    effective = vol.get("asof_effective")
    vol_valid = bool(effective and effective <= pricing_date and not vol.get("error"))
    warnings = [w.get("message", str(w)) if isinstance(w, dict) else str(w) for w in vol.get("warnings", [])]
    if vol.get("error"):
        warnings.append("Volatilités / corrélations indisponibles : " + vol["error"])
    for ticker in tickers:
        div = dividends[ticker]
        sigma = _number(vol.get("vols", {}).get(ticker), 1.5) if vol_valid else None
        div_date = div.get("asof_effective")
        q = _number(div.get("yield_declared"), .5) if div.get("ok") and div_date and div_date <= pricing_date else None
        title_warnings = []
        if sigma is None: title_warnings.append("Volatilité absente : saisir une hypothèse GBM.")
        if q is None: title_warnings.append(div.get("error") or "Dividende absent : saisir une hypothèse.")
        if div.get("suspect"): title_warnings.append("Dividendes suspects : divergence entre rendement déclaré et ajusté/nu.")
        for field, value, observed, method in (
            ("sigma", sigma, effective, "Volatilité réalisée annualisée ; clôtures ajustées, 252 rendements communs maximum"),
            ("q", q, div_date, "Dividendes détachés sur un an / dernière clôture nue ; hypothèse forward à confirmer"),
        ):
            if value is not None:
                result["provenance"][f"underlyings.{ticker}.{field}"] = {
                    "source": "HISTORICAL_ESTIMATE", "as_of": observed, "reference_value": value,
                    "method": method, "provider": vol.get("provider", "yahoo") if field == "sigma" else "yahoo",
                    "fetched_at": fetched, "window_days": 252 if field == "sigma" else 365,
                    "n_observations": vol.get("n_obs") if field == "sigma" else len(div.get("dividends", [])),
                    "warnings": warnings if field == "sigma" else title_warnings,
                }
        result["underlyings"].append({"ticker": ticker, "sigma": sigma, "q": q,
            "vol_date": effective if sigma is not None else None, "dividend_date": div_date if q is not None else None,
            "reference_close": div.get("price") if div.get("ok") else None, "warnings": title_warnings})
    if vol_valid:
        corr = vol.get("corr", {})
        matrix = [[corr.get(a, {}).get(b) for b in tickers] for a in tickers]
        if all(isinstance(v, (int, float)) and math.isfinite(v) and -1 <= v <= 1 for row in matrix for v in row):
            result["correlation"] = matrix
            result["provenance"]["correlation"] = {
                "source": "HISTORICAL_ESTIMATE", "as_of": effective, "reference_value": matrix,
                "method": "Corrélations réalisées sur les rendements ajustés communs", "provider": vol.get("provider", "yahoo"),
                "fetched_at": fetched, "window_days": 252, "n_observations": vol.get("n_obs"), "warnings": warnings,
            }
    result["warnings"] = warnings
    with _lock:
        _cache[key] = (time.monotonic(), deepcopy(result))
        while len(_cache) > 128: _cache.popitem(last=False)
    return result
