"""AMC underlying price store.

Persistent store for underlying price time series used in the VAG module.
Logical instrument keys resolve through an atomic market manifest to immutable
Parquet generations; exact legacy addresses remain readable without migration.

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
from contextlib import nullcontext
from hashlib import sha256
from pathlib import Path
from typing import Optional

import requests
import numpy as np
import pandas as pd
import yfinance as yf

from ..runtime import data_path, business_today
from . import market_storage
from .reference_data import REFERENCE_CURRENCIES

_PRICE_STORE = data_path("underlying_prices")
_PRICE_STORE.mkdir(parents=True, exist_ok=True)

_TICKER_MAP_FILE = _PRICE_STORE / "_ticker_map.json"
_FX_STORE = data_path("fx_rates")
_FX_STORE.mkdir(parents=True, exist_ok=True)


# ── helpers ───────────────────────────────────────────────────────────

def is_gbx_ticker(ticker: str, currency: str) -> bool:
    """Return True when yfinance prices are in GBX (pence) but declared as GBP.

    London Stock Exchange tickers end in .L and are quoted in pence.
    yfinance reports currency='GBP' which is misleading — values are actually
    in GBX (1 GBP = 100 GBX).  Dividing by 100 gives real GBP pounds.
    """
    suffix = ticker.upper().rsplit(".", 1)[-1] if "." in ticker else ""
    return currency.upper() == "GBP" and suffix == "L"


def _slug(key: str) -> str:
    """Keep uppercase identifiers; hash every lossy, long or case-ambiguous name."""
    identity = key.strip()
    if not identity or re.fullmatch(r"[A-Z0-9_\-]{1,80}", identity):
        return identity
    if re.fullmatch(r"[A-Za-z0-9_\-]{0,32}--[a-f0-9]{64}", identity):
        return identity
    prefix = re.sub(r"[^A-Za-z0-9_\-]", "_", identity)[:32]
    return prefix+'--'+sha256(identity.encode('utf-8')).hexdigest()


def _logical_price_path(key):
    return _PRICE_STORE / f"{_slug(key)}.parquet"


def _parquet_path(key: str) -> Path:
    logical = _logical_price_path(key)
    path = market_storage.current_path(logical)
    if path.exists() or path != logical:
        return path
    # Legacy names can be read only through an exact, lossless identity.
    for legacy in _PRICE_STORE.glob('*.parquet'):
        if _slug(legacy.stem) == _slug(key):
            return market_storage.current_path(legacy)
    return path


def _load_ticker_map(*, transaction=None) -> dict:
    path = transaction.path(_TICKER_MAP_FILE) if transaction else market_storage.current_path(_TICKER_MAP_FILE)
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding='utf-8'),object_pairs_hook=_unique_json_object)
        if not isinstance(value, dict) or any(not isinstance(k,str) or not isinstance(v,str) for k,v in value.items()):
            raise ValueError('Invalid ticker mapping')
        return {_slug(key):ticker for key,ticker in value.items()}
    except (ValueError, TypeError) as exc:
        raise ValueError('Association instrument/ticker illisible ; remplacement suspendu.') from exc


def _save_ticker_map(mapping: dict, *, transaction=None) -> None:
    with (nullcontext(transaction) if transaction else market_storage.transaction()) as pending:
        pending.json(_TICKER_MAP_FILE, mapping)


@market_storage.consistent_read
def price_status(underlyings: list[dict] | None = None) -> list[dict]:
    ticker_map = _load_ticker_map()
    stored = {}
    for logical in market_storage.logical_paths(_PRICE_STORE):
        key = _slug(logical.stem)
        try:
            frame = pd.read_parquet(market_storage.current_path(logical))
            stored[key] = dict(key=key, rows=len(frame), date_min=str(frame.index.min().date()),
                date_max=str(frame.index.max().date()), available=True,
                source=frame.attrs.get('source','unknown'), currency=frame.attrs.get('currency',''),
                price_type=frame.attrs.get('price_type','UNKNOWN_LEGACY'),
                unit=frame.attrs.get('unit','UNKNOWN_LEGACY'),
                instrument_key=frame.attrs.get('instrument_key',logical.stem),
                storage_revision=frame.attrs.get('storage_revision','legacy'))
        except (OSError, ValueError, KeyError):
            stored[key] = dict(key=key,available=False)
    result, seen = [], set()
    for underlying in underlyings or []:
        isin, name = underlying.get('isin',''), underlying.get('name','')
        key = _slug(isin or name); seen.add(key)
        result.append({**stored.get(key,dict(key=key,available=False)), 'isin':isin,'name':name,
                       'ticker':ticker_map.get(key,'')})
    for key,item in stored.items():
        if key not in seen:
            result.append({**item,'isin':'','name':item.get('instrument_key',key),'ticker':ticker_map.get(key,'')})
    return result


def _validate_key(key):
    if not isinstance(key,str) or not key.strip():
        raise ValueError('Identifiant instrument requis.')
    return key.strip()


def _save_series(key, frame, ticker='', *, shared=False, expected=None):
    """Publish the series, association and optional raw/adjusted copies together."""
    from ..services.market_history import store_history
    key = _validate_key(key)
    frame = frame.copy(deep=True)
    frame.attrs['instrument_key'] = key
    with market_storage.transaction() as pending:
        pending.require_unchanged(expected)
        mapping = _load_ticker_map(transaction=pending)
        pending.parquet(_logical_price_path(key), frame)
        if ticker:
            mapping[_slug(key)] = ticker
        else:
            mapping.pop(_slug(key),None)
        _save_ticker_map(mapping,transaction=pending)
        if shared:
            scale = 100 if is_gbx_ticker(ticker,frame.attrs.get('currency','')) else 1
            for field,adjusted in [('close',True),('price_close',False)]:
                store_history(ticker,frame[field]*scale,adjusted,
                    frame.attrs['requested_start'],frame.attrs['requested_end'],transaction=pending)
    return dict(key=_slug(key),ticker=ticker,rows=len(frame),date_min=str(frame.index.min().date()),
                date_max=str(frame.index.max().date()),currency=frame.attrs['currency'],
                source=frame.attrs['source'],price_type=frame.attrs['price_type'],unit=frame.attrs['unit'])


def fetch_prices(key: str, ticker: str, start: str | None = None, end: str | None = None) -> dict:
    key = _validate_key(key)
    if not ticker or not ticker.strip():
        raise ValueError('Ticker Yahoo Finance requis')
    ticker = ticker.strip().upper()
    from ..services.market_history import _path as shared_path
    expected = market_storage.versions([_logical_price_path(key),shared_path(ticker,True),shared_path(ticker,False)])
    first = datetime.date.fromisoformat(start) if start else datetime.date(2000,1,1)
    last = datetime.date.fromisoformat(end) if end else business_today()+datetime.timedelta(days=1)
    if first >= last:
        raise ValueError('Période de téléchargement invalide (fin exclusive).')
    instrument = yf.Ticker(ticker)
    adjusted = instrument.history(start=first.isoformat(),end=last.isoformat(),auto_adjust=True)
    raw = instrument.history(start=first.isoformat(),end=last.isoformat(),auto_adjust=False)
    if adjusted.empty or raw.empty or 'Close' not in adjusted or 'Close' not in raw:
        raise ValueError('Cours bruts ou ajustés absents ; aucun remplacement.')
    try:
        info = instrument.fast_info
        currency = str(info.get('currency','') if isinstance(info,dict) else getattr(info,'currency','')).upper()
    except Exception as exc:
        raise ValueError('Devise du fournisseur indisponible ; aucun remplacement.') from exc
    if currency not in REFERENCE_CURRENCIES:
        raise ValueError('Devise du fournisseur inconnue ; aucun remplacement.')
    adjusted = market_storage.validate_frame(adjusted[['Close']].rename(columns={'Close':'close'}))
    raw = market_storage.validate_frame(raw[['Close']].rename(columns={'Close':'price_close'}),('price_close',))
    if not adjusted.index.equals(raw.index):
        raise ValueError('Dates des cours bruts et ajustés différentes ; aucun remplacement.')
    if adjusted.index.min().date() < first or adjusted.index.max().date() >= last:
        raise ValueError('Cours reçus hors de la période demandée.')
    adjusted['price_close'] = raw['price_close']
    if is_gbx_ticker(ticker,currency):
        adjusted[['close','price_close']] /= 100
    adjusted.attrs.update(source=f'yahoo:{ticker}',currency=currency,price_type='ADJUSTED_CLOSE',
        raw_price_type='UNADJUSTED_CLOSE',unit='CURRENCY',adjustment_date=business_today().isoformat(),
        requested_start=first.isoformat(),requested_end=(last-datetime.timedelta(days=1)).isoformat(),
        fetched_at=datetime.datetime.now(datetime.timezone.utc).isoformat())
    return _save_series(key,adjusted,ticker,shared=True,expected=expected)


def _unique_json_object(pairs):
    value = {}
    for key,item in pairs:
        if key in value:
            raise ValueError('Clé JSON ou date dupliquée ; aucun remplacement.')
        value[key] = item
    return value


def upload_prices(key: str, content: bytes, filename: str, ticker: str = '', *,
                  currency: str | None = None, price_type: str | None = None, unit: str | None = None,
                  adjustment_date: str | None = None) -> dict:
    """Import explicit total-return observations; optional price_close stays raw."""
    _validate_key(key)
    currency = (currency or '').strip().upper()
    if currency not in REFERENCE_CURRENCIES or price_type not in {'ADJUSTED_CLOSE','TOTAL_RETURN_NAV'} or unit != 'CURRENCY':
        raise ValueError('Conventions requises : devise reconnue, cours ajusté ou NAV de rendement total, unité de devise. Un cours brut seul ne remplace pas une série de rendement total.')
    ext = Path(filename).suffix.lower()
    try:
        if ext in ('.xlsx','.xls'):
            frame = pd.read_excel(io.BytesIO(content))
            if len(frame.columns) < 2:
                raise ValueError('Colonnes date et cours requises.')
            frame = frame.rename(columns={frame.columns[0]:'date',frame.columns[1]:'close'})
        elif ext == '.json':
            data = json.loads(content.decode('utf-8'),object_pairs_hook=_unique_json_object)
            if isinstance(data,dict):
                frame = pd.DataFrame([{'date':day,'close':value} for day,value in data.items()])
            elif isinstance(data,list):
                frame = pd.DataFrame(data)
                aliases = [field for field in ['close','price','nav','value'] if field in frame]
                if len(aliases) != 1:
                    raise ValueError('Une seule colonne de cours requise.')
                frame = frame.rename(columns={aliases[0]:'close'})
            else:
                raise ValueError('Format JSON non reconnu.')
        else:
            raise ValueError('Format non supporté : utiliser .xlsx, .xls ou .json.')
        if 'date' not in frame or frame.columns.has_duplicates:
            raise ValueError('Dates absentes ou colonnes dupliquées.')
        # Avoid ambiguous locale-dependent dates in JSON and text Excel cells.
        if frame['date'].map(lambda v:isinstance(v,str) and not re.fullmatch(r'\d{4}-\d{2}-\d{2}',v)).any():
            raise ValueError('Dates texte attendues au format AAAA-MM-JJ.')
        columns = ['close']+(['price_close'] if 'price_close' in frame else [])
        frame = market_storage.validate_frame(frame.set_index('date')[columns],columns)
    except (KeyError, TypeError, UnicodeError) as exc:
        raise ValueError('Fichier de cours invalide ; aucun remplacement.') from exc
    frame.attrs.update(source=f'manual:{Path(filename).name}',currency=currency,
        price_type=price_type,unit=unit,imported_at=datetime.datetime.now(datetime.timezone.utc).isoformat())
    if 'price_close' in frame:
        if not adjustment_date:
            raise ValueError('Colonne price_close : date de référence des unités de titres requise.')
        reference = datetime.date.fromisoformat(adjustment_date)
        if reference < frame.index.max().date() or reference > business_today():
            raise ValueError('Date des unités de titres attendue entre la dernière observation et aujourd’hui.')
        frame.attrs.update(raw_price_type='UNADJUSTED_CLOSE',adjustment_date=reference.isoformat())
    return _save_series(key,frame,(ticker or '').strip().upper())


def delete_prices(key: str) -> None:
    logical = _logical_price_path(key)
    with market_storage.transaction() as pending:
        pending.delete(logical)
        # Keep an old legacy file on disk but hide its logical address.
        for legacy in _PRICE_STORE.glob('*.parquet'):
            if _slug(legacy.stem) == _slug(key):
                pending.delete(legacy)
        mapping = _load_ticker_map(transaction=pending)
        mapping.pop(_slug(key),None)
        _save_ticker_map(mapping,transaction=pending)


def get_fx_series(from_ccy: str, to_ccy: str, start: str | None = None, end: str | None = None) -> pd.Series:
    from .amc_market_bundle import active_bundle
    bundle = active_bundle()
    if bundle is not None:
        return bundle.fx(from_ccy.upper().strip(),to_ccy.upper().strip()).copy(deep=True)
    return _stored_fx_series(from_ccy,to_ccy,start,end)


@market_storage.consistent_read
def _stored_fx_series(from_ccy, to_ccy, start, end):
    from_ccy = from_ccy.upper().strip()
    to_ccy   = to_ccy.upper().strip()

    if from_ccy == to_ccy or not from_ccy or not to_ccy:
        return pd.Series(dtype=float)   # caller interprets empty as no-op
    if not re.fullmatch(r'[A-Z]{3}', from_ccy) or not re.fullmatch(r'[A-Z]{3}', to_ccy):
        raise ValueError('Paire de devises invalide.')

    cache_key = f"{from_ccy}{to_ccy}"
    logical_path = _FX_STORE / f"{cache_key}.parquet"
    expected = market_storage.versions([logical_path])
    cache_path = market_storage.current_path(logical_path)

    _start = start or "2000-01-01"
    _end   = end   or datetime.date.today().isoformat()

    from .amc_controls import record_market
    cached_series = None
    # A historical request can use a cache that already covers its endpoint.
    if cache_path.exists():
        try:
            cached = market_storage.validate_frame(pd.read_parquet(cache_path), ('rate',))
            if not cached.empty:
                last_cached = cached.index.max().date()
                today = datetime.date.today()
                # Refresh only if more than 1 day old and market was open
                cached_series = cached["rate"].dropna()
                cached_series.index = pd.to_datetime(cached_series.index).tz_localize(None)
                from .market_policy import freshness
                requested = datetime.date.fromisoformat(end)-datetime.timedelta(days=1) if end else today
                known = cached_series.loc[cached_series.index <= pd.Timestamp(requested)]
                if not known.empty and freshness(known.index[-1].date(), requested, "reporting_fx")["qualified"]:
                    return record_market(f"fx:{cache_key}", cached_series)
                if (today - last_cached).days <= 1 or (end and last_cached >= datetime.date.fromisoformat(end)):
                    return record_market(f"fx:{cache_key}", cached_series)
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
                out = market_storage.validate_frame(s.to_frame(), ('rate',))
                out.attrs["pair"] = f"{from_ccy}/{to_ccy}"
                with market_storage.transaction() as pending:
                    pending.require_unchanged(expected)
                    pending.parquet(logical_path, out)
                return record_market(f"fx:{cache_key}", s)
        except Exception:
            continue

    return record_market(f"fx:{cache_key}", cached_series) if cached_series is not None else pd.Series(dtype=float)


def fx_quote_to(from_ccy: str | None, to_ccy: str = "EUR",
                asof: datetime.date | str | None = None) -> dict:
    """Conversion rate at *asof* (latest by default), or None if unknown.

    `get_fx_series` answers with an empty Series in two unrelated situations:
    the conversion is a no-op (same currency, or none recorded), and the pair
    could not be loaded at all (provider down, exotic cross, empty cache).
    Every caller used to collapse both into `else 1.0`. That is correct for
    the first and silently wrong for the second — a JPY notional booked at
    parity overstates its EUR size by a factor of 164, a USD one by 8.7%, and
    nothing anywhere said a rate had been invented. Because almost every deal
    is already in the reporting currency and legitimately takes the empty
    branch, the defect never showed in normal use.

    Splitting the two is the whole point: 1.0 means "no conversion needed",
    None means "do not add this position to a total until you know its size".
    Callers are expected to exclude and name it rather than guess."""
    src = (from_ccy or "").upper().strip()
    dst = (to_ccy or "EUR").upper().strip()
    from ..runtime import business_today
    from .market_policy import freshness
    asof_date = datetime.date.fromisoformat(asof) if isinstance(asof, str) else asof or business_today()
    quote = dict(from_ccy=src, to_ccy=dst, requested_asof=asof_date.isoformat(),
                 provider="YAHOO_FINANCE", rate=None, raw_rate=None, qualified=False)
    if not src or src == dst:
        return {**quote, "rate": 1., "qualified": True, "status": "NO_CONVERSION", "age_days": 0,
                "effective_date": asof_date.isoformat(), "provider": None}
    # Yahoo's `end` is exclusive. Ask through the following calendar day, then
    # filter locally as caches may contain newer quotes than the requested
    # historical valuation date.
    provider_end = ((asof_date + datetime.timedelta(days=1)).isoformat()
                    if asof_date else None)
    try:
        series = get_fx_series(src, dst, end=provider_end).copy()
    except Exception as exc:
        return {**quote, **freshness(None, asof_date, "reporting_fx"), "reason": type(exc).__name__}
    series.index = pd.to_datetime(series.index).tz_localize(None)
    series = series.loc[~series.index.duplicated(keep="last")].sort_index()
    if asof_date is not None and not series.empty:
        index = pd.to_datetime(series.index).tz_localize(None)
        series = series[index <= pd.Timestamp(asof_date)]
    if series.empty:
        return {**quote, **freshness(None, asof_date, "reporting_fx")}
    try:
        rate = float(series.iloc[-1])
    except (TypeError, ValueError):
        return {**quote, "status": "INVALID_RATE"}
    if not math.isfinite(rate) or rate <= 0.0:
        return {**quote, "status": "INVALID_RATE"}
    quality = freshness(pd.Timestamp(series.index[-1]).date(), asof_date, "reporting_fx")
    return {**quote, **quality, "raw_rate": rate, "rate": rate if quality["qualified"] else None}


def fx_rate_to(from_ccy: str | None, to_ccy: str = "EUR",
               asof: datetime.date | str | None = None) -> float | None:
    """Compatibility scalar: an unqualified quote never feeds a reporting total."""
    return fx_quote_to(from_ccy, to_ccy, asof)["rate"]


def _bundle_key(bundle, key):
    if key in bundle.aliases:
        return key
    matches = [alias for alias in bundle.aliases if _slug(alias) == key]
    if len(matches) != 1:
        raise ValueError(f'Titre absent ou ambigu dans le dossier de marché : {key}')
    return matches[0]


def get_currency(key: str) -> str:
    from .amc_market_bundle import active_bundle
    bundle = active_bundle()
    if bundle is not None:
        return bundle.load(_bundle_key(bundle,key)).attrs['currency']
    with market_storage.read_view():
        path = _parquet_path(key)
        if not path.exists():
            return ''
        try:
            return pd.read_parquet(path).attrs.get('currency','')
        except (OSError,ValueError):
            return ''


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
    """Read an independent local-bundle or committed-store frame."""
    from .amc_market_bundle import active_bundle
    bundle = active_bundle()
    if bundle is not None:
        return bundle.load(_bundle_key(bundle,key)).copy(deep=True)
    with market_storage.read_view():
        path = _parquet_path(key)
        if not path.exists():
            raise ValueError(f"Prix non disponibles pour '{key}'. Importez d'abord la série.")
        from .amc_controls import record_market
        return record_market(f'prices:{key}',pd.read_parquet(path))


def spot_on_date(key: str, date_str: str) -> dict | None:
    """Last close on or before *date_str* from the stored series (same
    as-of convention used for Total Return in amc_bh.py) — a pure read
    against the local Parquet store, no Yahoo call. None if the series
    isn't stored yet, or has no data on/before that date."""
    try:
        df = load_prices(key)
    except ValueError:
        return None
    df = df.copy()
    df.index = pd.to_datetime(df.index).tz_localize(None)
    before = df[df.index <= pd.Timestamp(date_str)]["close"]
    if before.empty:
        return None
    return {"date": str(before.index[-1].date()), "close": float(before.iloc[-1])}


def yf_symbol(isin: str, name: str = "") -> str:
    """Return a yfinance-usable symbol for the given ISIN.

    Resolution order:
      1. ticker_map (explicit user mapping, handles ISINs yfinance can't resolve, e.g. IL*)
      2. yfinance ISIN checksum validation
      3. Name-based Yahoo Finance search as fallback
    """
    from .amc_market_bundle import active_bundle
    bundle = active_bundle()
    if bundle is not None:
        raise ValueError(f"Source locale obligatoire : {isin}")
    # Check explicit ticker map first (e.g. IL0011334468 → CYBR)
    tm = _load_ticker_map()
    mapped = tm.get(_slug(isin))
    if mapped:
        return mapped

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


_split_calendar_cache: dict[str, dict] = {}
_split_calendar_times: dict[str, float] = {}


def get_split_calendar(isin: str, name: str = "") -> dict:
    """Return {split_date: ratio} of real stock splits for this security,
    via yfinance's corporate-action calendar. Cached per resolved ticker
    symbol for the lifetime of the process. Empty dict when no splits are
    found or the ticker can't be resolved.

    Shared by every module that mixes as-traded carnet prices with the
    auto-adjusted (auto_adjust=True) price store — core/fifo/pipeline.py's
    fix_carnet_splits() and amc_orderbook.py's apply_split_corrections() —
    so the split calendar and ticker resolution are fetched once, not
    duplicated per caller.
    """
    from .amc_market_bundle import active_bundle
    bundle = active_bundle()
    if bundle is not None:
        if isin not in bundle.aliases:
            raise ValueError(f"Splits absents du dossier : {isin}")
        return bundle.splits[bundle.aliases[isin]]
    symbol = yf_symbol(isin, name)
    import time
    if symbol not in _split_calendar_cache or time.monotonic() - _split_calendar_times.get(symbol, 0) > 3600:
        try:
            actions = yf.Ticker(symbol).actions
            if actions is None or actions.empty or "Stock Splits" not in actions.columns:
                _split_calendar_cache[symbol] = {}
            else:
                s = actions["Stock Splits"]
                _split_calendar_cache[symbol] = {d.date(): float(r) for d, r in s[s != 0].items()}
        except Exception as exc:
            raise ValueError(f"Calendrier des splits indisponible : {symbol}") from exc
        _split_calendar_times[symbol] = time.monotonic()
    return _split_calendar_cache[symbol]


def split_factor_between(isin: str, name: str,
                         order_date: "datetime.date", as_of: "datetime.date") -> float:
    """Cumulative split factor for real splits strictly after order_date and
    on/before as_of. Multiply a raw carnet quantity by this factor and
    divide its price by it to convert an as-traded order into the same
    post-split terms used by the auto-adjusted price store. Returns 1.0
    when no qualifying split occurred."""
    factor = 1.0
    for split_date, ratio in get_split_calendar(isin, name).items():
        if order_date < split_date <= as_of:
            factor *= ratio
    return factor


def build_marks(components: list[dict], as_of_date: str, prod_ccy: str, *, price_basis: str = "total_return") -> dict[str, float]:
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
                    from .amc_controls import price_at
                    if price_basis == "execution":
                        price_local = price_at(execution_series(isin, name, as_of_date), as_of_ts)
                    else:
                        price_local = price_at(before["close"], as_of_ts)
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
            if not price_ccy:
                try:
                    fi_ccy = yf.Ticker(sym).fast_info.get("currency")
                    if fi_ccy:
                        price_ccy = fi_ccy.upper()
                except Exception:
                    pass
            try:
                hist = yf.Ticker(sym).history(
                    start=start_str, end=end_str, auto_adjust=price_basis != "execution"
                )
                if not hist.empty:
                    from .amc_controls import price_at
                    price_local = price_at(hist["Close"], as_of_ts)
                    if price_basis == "execution":
                        price_local *= split_factor_between(isin, name, as_of_ts.date(), pd.Timestamp.today().date())
                    if is_gbx_ticker(sym, price_ccy):
                        price_local /= 100
            except Exception:
                pass

        if price_local is None or not math.isfinite(price_local) or price_local <= 0:
            continue

        # ── FX conversion to product currency ────────────────────────
        if not price_ccy or not prod_ccy:
            raise ValueError(f"Devise inconnue pour {isin}")
        if price_ccy == prod_ccy.upper():
            marks[isin] = price_local
        else:
            from .amc_controls import price_at
            fx_series = get_fx_series(price_ccy, prod_ccy.upper())
            fx = price_at(fx_series, as_of_ts)
            marks[isin] = price_local * fx

    return marks


def auto_populate_store(components: list[dict], since: str = "2010-01-01") -> dict[str,str]:
    """Use the same validated atomic ingestion path for automatic local caching."""
    from .amc_market_bundle import active_bundle
    if active_bundle() is not None:
        return {}
    results = {}
    for component in components:
        isin,name = (component.get('isin') or '').strip(),(component.get('name') or '').strip()
        if not isin:
            continue
        if any(_parquet_path(key).exists() for key in [isin,name] if key):
            results[isin] = 'existing'
            continue
        try:
            fetch_prices(isin,yf_symbol(isin,name),start=since)
            results[isin] = 'fetched'
        except Exception:
            results[isin] = 'failed'
    return results


def execution_series(isin: str, name: str, as_of: str) -> pd.Series:
    """Price-only history in as-of share units; never use dividend-adjusted prices for lots."""
    from .amc_controls import price_at
    try:
        df = load_prices(isin)
    except ValueError:
        df = pd.DataFrame()
    if "price_close" in df.columns:
        series = df["price_close"].copy()
        adjustment_date = pd.Timestamp(df.attrs.get("adjustment_date", as_of)).date()
    else:
        ticker = yf_symbol(isin, name)
        raw = yf.Ticker(ticker).history(start="2000-01-01", end=(pd.Timestamp(as_of) + pd.Timedelta(days=1)).strftime("%Y-%m-%d"), auto_adjust=False)
        if raw.empty:
            raise ValueError(f"Cours hors dividendes indisponible pour {isin}")
        series = raw["Close"].copy()
        ccy = (df.attrs.get("currency") or get_currency(isin) or "").upper()
        if is_gbx_ticker(ticker, ccy):
            series /= 100
        adjustment_date = pd.Timestamp.today().date()
    series.index = pd.to_datetime(series.index).tz_localize(None).normalize()
    series = series.loc[:as_of]
    factor = split_factor_between(isin, name, pd.Timestamp(as_of).date(), adjustment_date)
    series = series * factor
    price_at(series, as_of)
    from .amc_controls import record_market
    return record_market(f"execution:{isin}:{as_of}", series)
