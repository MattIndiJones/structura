"""AMC underlying price store.

Persistent store for underlying price time series used in the VAG
(Valeur Ajoutée de Gestion) module.  Each series is stored as a parquet file
keyed by a sanitised slug derived from the underlying name or ISIN.

Two acquisition paths:
  1. Yahoo Finance auto-fetch  (yfinance)
  2. Manual upload             (Excel or JSON)
"""
from __future__ import annotations

import io
import json
import math
import re
import datetime
from pathlib import Path
from typing import Optional

import requests
import numpy as np
import pandas as pd
import yfinance as yf

_PRICE_STORE = Path(__file__).parent.parent.parent / "data" / "underlying_prices"
_PRICE_STORE.mkdir(parents=True, exist_ok=True)

_TICKER_MAP_FILE = _PRICE_STORE / "_ticker_map.json"
_FX_STORE = Path(__file__).parent.parent.parent / "data" / "fx_rates"
_FX_STORE.mkdir(parents=True, exist_ok=True)


# ── helpers ───────────────────────────────────────────────────────────

def _slug(key: str) -> str:
    """Turn an ISIN or name into a safe filename slug."""
    return re.sub(r"[^A-Za-z0-9_\-]", "_", key.strip())[:80]


def _parquet_path(key: str) -> Path:
    return _PRICE_STORE / f"{_slug(key)}.parquet"


def _load_ticker_map() -> dict:
    if _TICKER_MAP_FILE.exists():
        try:
            return json.loads(_TICKER_MAP_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_ticker_map(m: dict) -> None:
    _TICKER_MAP_FILE.write_text(
        json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# ── public API ────────────────────────────────────────────────────────

def price_status(underlyings: list[dict] | None = None) -> list[dict]:
    """Return status of every stored price series.

    If *underlyings* is provided (list of {isin, name} dicts from block_b),
    merge with stored series so missing ones show up as unavailable.
    """
    ticker_map = _load_ticker_map()
    stored: dict[str, dict] = {}

    for p in _PRICE_STORE.glob("*.parquet"):
        key = p.stem
        try:
            df = pd.read_parquet(p)
            stored[key] = {
                "key":      key,
                "rows":     len(df),
                "date_min": str(df.index.min().date()),
                "date_max": str(df.index.max().date()),
                "available": True,
                "source":   df.attrs.get("source", "unknown"),
                "currency": df.attrs.get("currency", ""),
            }
        except Exception:
            stored[key] = {"key": key, "available": False}

    result = []
    seen_keys: set[str] = set()

    if underlyings:
        for u in underlyings:
            isin = u.get("isin", "")
            name = u.get("name", "")
            key = _slug(isin or name)
            seen_keys.add(key)
            ticker = ticker_map.get(key, "")
            entry = stored.get(key, {"key": key, "available": False})
            result.append({**entry, "isin": isin, "name": name, "ticker": ticker})

    # Also expose series stored that aren't in current underlyings list
    for key, info in stored.items():
        if key not in seen_keys:
            ticker = ticker_map.get(key, "")
            result.append({**info, "isin": "", "name": key, "ticker": ticker})

    return result


def fetch_prices(key: str, ticker: str,
                 start: str | None = None,
                 end: str | None = None) -> dict:
    """Download adjusted close prices from Yahoo Finance and persist."""
    if not ticker or ticker.strip() == "":
        raise ValueError("Ticker Yahoo Finance requis")

    # Persist ticker mapping
    m = _load_ticker_map()
    m[_slug(key)] = ticker.strip()
    _save_ticker_map(m)

    _start = start or "2000-01-01"
    _end   = end   or datetime.date.today().isoformat()

    tkr = yf.Ticker(ticker.strip())
    df  = tkr.history(start=_start, end=_end, auto_adjust=True)

    if df.empty:
        raise ValueError(f"Aucune donnée Yahoo Finance pour '{ticker}' sur la période")

    # Detect currency from ticker metadata
    currency = ""
    try:
        info = tkr.fast_info
        currency = getattr(info, "currency", None) or ""
    except Exception:
        pass

    df = df[["Close"]].rename(columns={"Close": "close"})
    df.index = pd.to_datetime(df.index).tz_localize(None)
    df.index.name = "date"
    # LSE tickers (.L) are quoted in GBX (pence) but yfinance reports currency='GBP'.
    # Divide by 100 to store real GBP values and avoid a 100× FX error downstream.
    if ticker.strip().upper().endswith(".L") and currency.upper() == "GBP":
        df["close"] = df["close"] / 100
    df.attrs["source"]   = f"yahoo:{ticker.strip()}"
    df.attrs["currency"] = currency.upper()
    df.to_parquet(_parquet_path(key))

    return {
        "key":      _slug(key),
        "ticker":   ticker.strip(),
        "currency": currency.upper(),
        "rows":     len(df),
        "date_min": str(df.index.min().date()),
        "date_max": str(df.index.max().date()),
    }


def upload_prices(key: str, content: bytes, filename: str,
                  ticker: str = "") -> dict:
    """Parse an Excel or JSON file and persist as a price series.

    Expected formats:
    - Excel: first column = date, second column = price (any header)
    - JSON:  list of {date: "YYYY-MM-DD", close: 123.45}
             or dict {"YYYY-MM-DD": 123.45}
    """
    ext = Path(filename).suffix.lower()

    if ext in (".xlsx", ".xls"):
        raw = pd.read_excel(io.BytesIO(content), header=0)
        raw.columns = [str(c).strip() for c in raw.columns]
        date_col  = raw.columns[0]
        price_col = raw.columns[1]
        raw[date_col] = pd.to_datetime(raw[date_col], errors="coerce")
        raw = raw.dropna(subset=[date_col, price_col])
        df = raw.set_index(date_col)[[price_col]].rename(columns={price_col: "close"})

    elif ext == ".json":
        data = json.loads(content.decode("utf-8"))
        if isinstance(data, list):
            df = pd.DataFrame(data)
            # accept {date, close} or {date, price} or {date, nav}
            for col in ("close", "price", "nav", "value"):
                if col in df.columns:
                    df = df.rename(columns={col: "close"})
                    break
            df["date"] = pd.to_datetime(df["date"], errors="coerce")
            df = df.dropna(subset=["date", "close"]).set_index("date")[["close"]]
        elif isinstance(data, dict):
            df = pd.DataFrame(
                [{"date": k, "close": v} for k, v in data.items()]
            )
            df["date"] = pd.to_datetime(df["date"], errors="coerce")
            df = df.dropna(subset=["date", "close"]).set_index("date")[["close"]]
        else:
            raise ValueError("Format JSON non reconnu")
    else:
        raise ValueError(f"Format non supporté : {ext}. Utiliser .xlsx ou .json")

    df.index = pd.to_datetime(df.index).tz_localize(None)
    df.index.name = "date"
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df = df.dropna()
    df = df.sort_index()

    if df.empty:
        raise ValueError("Aucune donnée valide trouvée dans le fichier")

    df.attrs["source"] = f"manual:{filename}"

    slug = _slug(key)
    df.to_parquet(_parquet_path(key))

    if ticker:
        m = _load_ticker_map()
        m[slug] = ticker
        _save_ticker_map(m)

    return {
        "key": slug,
        "rows": len(df),
        "date_min": str(df.index.min().date()),
        "date_max": str(df.index.max().date()),
        "source": f"manual:{filename}",
    }


def delete_prices(key: str) -> None:
    p = _parquet_path(key)
    if p.exists():
        p.unlink()
    m = _load_ticker_map()
    m.pop(_slug(key), None)
    _save_ticker_map(m)


def get_fx_series(from_ccy: str, to_ccy: str,
                  start: str | None = None,
                  end: str | None = None) -> pd.Series:
    """Return a daily FX series (from_ccy → to_ccy), cached to parquet.

    Uses Yahoo Finance pairs e.g. USDCHF=X, EURUSD=X.
    Returns a Series indexed by date with the exchange rate.
    If from_ccy == to_ccy, returns a constant Series of 1.0 (no conversion needed).
    """
    from_ccy = from_ccy.upper().strip()
    to_ccy   = to_ccy.upper().strip()

    if from_ccy == to_ccy or not from_ccy or not to_ccy:
        return pd.Series(dtype=float)   # caller interprets empty as no-op

    cache_key = f"{from_ccy}{to_ccy}"
    cache_path = _FX_STORE / f"{cache_key}.parquet"

    _start = start or "2000-01-01"
    _end   = end   or datetime.date.today().isoformat()

    # Use cached data if fresh enough (updated today)
    if cache_path.exists():
        try:
            cached = pd.read_parquet(cache_path)
            if not cached.empty:
                last_cached = cached.index.max().date()
                today = datetime.date.today()
                # Refresh only if more than 1 day old and market was open
                if (today - last_cached).days <= 1:
                    s = cached["rate"].dropna()
                    s.index = pd.to_datetime(s.index).tz_localize(None)
                    return s
        except Exception:
            pass

    # Try direct pair first (e.g. USDCHF=X), then inverse (CHFUSD=X → invert)
    ticker_direct  = f"{from_ccy}{to_ccy}=X"
    ticker_inverse = f"{to_ccy}{from_ccy}=X"

    for ticker, invert in [(ticker_direct, False), (ticker_inverse, True)]:
        try:
            df = yf.Ticker(ticker).history(start=_start, end=_end, auto_adjust=True)
            if not df.empty:
                s = df["Close"].rename("rate")
                s.index = pd.to_datetime(s.index).tz_localize(None)
                s.index.name = "date"
                if invert:
                    s = (1.0 / s).rename("rate")
                out = s.to_frame()
                out.attrs["pair"] = f"{from_ccy}/{to_ccy}"
                out.to_parquet(cache_path)
                return s
        except Exception:
            continue

    return pd.Series(dtype=float)   # not found — caller skips conversion


def get_currency(key: str) -> str:
    """Return the stored currency for a price series, or empty string."""
    p = _parquet_path(key)
    if not p.exists():
        return ""
    try:
        df = pd.read_parquet(p)
        return df.attrs.get("currency", "")
    except Exception:
        return ""


def resolve_ticker(query: str) -> tuple[str, str]:
    """Search Yahoo Finance for a ticker matching an ISIN or name.

    Returns (ticker, confidence) where confidence is one of:
      'found'     — a match was returned
      'not_found' — no result
      'error'     — network/parse error
    """
    url = "https://query1.finance.yahoo.com/v1/finance/search"
    params = {"q": query, "quotesCount": 5, "newsCount": 0, "enableFuzzyQuery": "false"}
    headers = {"User-Agent": "Mozilla/5.0 (compatible; Structura/1.0)"}
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=6)
        resp.raise_for_status()
        quotes = resp.json().get("quotes", [])
        if not quotes:
            return "", "not_found"
        # Prefer tradable security types over indices/crypto
        for q in quotes:
            if q.get("quoteType") in ("EQUITY", "ETF", "MUTUALFUND"):
                return q.get("symbol", ""), "found"
        return quotes[0].get("symbol", ""), "found"
    except Exception:
        return "", "error"


def load_prices(key: str) -> pd.DataFrame:
    """Load a stored price series. Raises ValueError if not found."""
    p = _parquet_path(key)
    if not p.exists():
        raise ValueError(f"Prix non disponibles pour '{key}'. Importez d'abord la série.")
    return pd.read_parquet(p)


def yf_symbol(isin: str, name: str = "") -> str:
    """Return a yfinance-usable symbol for the given ISIN.

    yfinance validates ISIN checksums internally and raises ValueError for some
    valid ISINs. Falls back to a name-based search when that happens.
    Centralised here so every module uses the same resolution path.
    """
    try:
        yf.Ticker(isin).fast_info  # lightweight check — raises ValueError on bad checksum
        return isin
    except ValueError:
        pass
    except Exception:
        return isin  # network / other error — still try the ISIN

    if name:
        try:
            results = yf.Search(name, max_results=5).quotes
            for r in results:
                if r.get("quoteType") == "EQUITY" and r.get("exchange") in (
                    "NYQ", "NMS", "NGM", "PCX"
                ):
                    return r["symbol"]
            for r in results:
                if r.get("quoteType") == "EQUITY":
                    return r["symbol"]
        except Exception:
            pass
    return isin


def build_marks(components: list[dict], as_of_date: str, prod_ccy: str) -> dict[str, float]:
    """Return {isin: mark_in_prod_ccy} for open-position valuation (Block B).

    Source priority:
      1. Price store (parquet) — fast, offline, already fetched by the user.
      2. yfinance — live fallback for ISINs not yet in the store.

    Only positions with a positive, finite mark are included.
    Positions not found in either source are silently excluded (mark = None,
    unrealised P&L stays undefined rather than wrong).
    """
    as_of_ts = pd.Timestamp(as_of_date) if as_of_date else pd.Timestamp.today()
    marks: dict[str, float] = {}

    for c in components:
        isin = (c.get("isin") or "").strip()
        name = (c.get("name") or "").strip()
        ccy  = (c.get("currency") or "").upper().strip()
        if not isin:
            continue

        price_local: Optional[float] = None
        price_ccy = ccy

        # ── 1. Price store ────────────────────────────────────────────
        for key in (_slug(isin), _slug(name)):
            p = _parquet_path(key)
            if not p.exists():
                continue
            try:
                df = pd.read_parquet(p)
                before = df[df.index <= as_of_ts]
                if not before.empty:
                    price_local = float(before["close"].iloc[-1])
                    stored_ccy = df.attrs.get("currency", "")
                    if stored_ccy:
                        price_ccy = stored_ccy.upper()
                    break
            except Exception:
                continue

        # ── 2. yfinance fallback ──────────────────────────────────────
        if price_local is None:
            sym = yf_symbol(isin, name)
            start_str = (as_of_ts - pd.Timedelta(days=7)).strftime("%Y-%m-%d")
            end_str   = (as_of_ts + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
            try:
                hist = yf.Ticker(sym).history(
                    start=start_str, end=end_str, auto_adjust=True
                )
                if not hist.empty:
                    price_local = float(hist["Close"].iloc[-1])
                    # LSE tickers (.L): yfinance returns GBX (pence), not GBP → ÷100
                    if sym.upper().endswith(".L") and price_ccy == "GBP":
                        price_local /= 100
            except Exception:
                pass

        if price_local is None or not math.isfinite(price_local) or price_local <= 0:
            continue

        # ── FX conversion to product currency ────────────────────────
        if price_ccy == prod_ccy.upper() or not price_ccy or not prod_ccy:
            marks[isin] = price_local
        else:
            fx_series = get_fx_series(price_ccy, prod_ccy.upper())
            if not fx_series.empty:
                before_fx = fx_series[fx_series.index <= as_of_ts]
                fx = float(before_fx.iloc[-1]) if not before_fx.empty else 1.0
            else:
                fx = 1.0
            marks[isin] = price_local * fx

    return marks


def auto_populate_store(components: list[dict],
                        since: str = "2010-01-01") -> dict[str, str]:
    """Fetch and persist price history for components not yet in the price store.

    Called automatically by load_study_data() on every study so that a
    first-time run populates the store for Blocks H, I, and subsequent marks.
    Components already present in the store are skipped (no re-download).

    Returns {isin: "existing" | "fetched" | "failed"}.
    """
    _end = datetime.date.today().isoformat()
    results: dict[str, str] = {}

    for c in components:
        isin = (c.get("isin") or "").strip()
        name = (c.get("name") or "").strip()
        if not isin:
            continue

        # Skip if already in store (by ISIN or name)
        if any(_parquet_path(k).exists() for k in [isin, name] if k):
            results[isin] = "existing"
            continue

        sym = yf_symbol(isin, name)
        try:
            tkr = yf.Ticker(sym)
            df  = tkr.history(start=since, end=_end, auto_adjust=True)
            if df.empty:
                results[isin] = "failed"
                continue

            currency = ""
            try:
                currency = (getattr(tkr.fast_info, "currency", None) or "").upper()
            except Exception:
                pass

            df = df[["Close"]].rename(columns={"Close": "close"})
            df.index = pd.to_datetime(df.index).tz_localize(None)
            df.index.name = "date"
            if sym.upper().endswith(".L") and currency.upper() == "GBP":
                df["close"] = df["close"] / 100
            df.attrs["source"]   = f"yahoo_auto:{sym}"
            df.attrs["currency"] = currency
            df.to_parquet(_parquet_path(isin))

            m = _load_ticker_map()
            m[_slug(isin)] = sym
            _save_ticker_map(m)

            results[isin] = "fetched"
        except Exception:
            results[isin] = "failed"

    return results
