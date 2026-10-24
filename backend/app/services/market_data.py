"""Yahoo Finance market data — realized vol, dividends, correlations, historical prices."""
from __future__ import annotations
import logging
import math
import time
import threading
from concurrent.futures import Future
from copy import deepcopy
import numpy as np
import pandas as pd
from datetime import date, datetime, timedelta, timezone
from typing import Optional
from ..core import market_storage

logger = logging.getLogger(__name__)

try:
    import yfinance as yf
    _HAS_YF = True
except ImportError:
    _HAS_YF = False
    logger.warning("yfinance not installed — pip install yfinance")


def load_hist_vol(tickers: list[str], period: str = "1y",
                  asof: Optional[str] = None, window_days: int | None = None) -> dict:
    """One dated common-sample RMS estimator for every entry point."""
    from ..core.calibration import calibration_history_start, realized_market
    from ..runtime import business_today
    windows = {"1mo": 21, "3mo": 63, "6mo": 126, "1y": 252, "2y": 504, "5y": 1260, "10y": 2520}
    try:
        requested = date.fromisoformat(asof) if asof else business_today()
        window = int(window_days) if window_days is not None else windows.get(period)
        if window is None or not 20 <= window <= 2520:
            return {"error": "Période inconnue ou fenêtre hors bornes : préciser window_days entre 20 et 2520."}
        history = load_hist_prices(tickers, calibration_history_start(requested, window).isoformat(),
                                   requested.isoformat(), adjusted=True)
        if history.get("error"):
            return history
        calibrated = realized_market(history.get("prices", {}), tickers, window)
        matrix = np.asarray(calibrated["corr"], dtype=float)
        if not np.isfinite(matrix).all() or np.linalg.eigvalsh(matrix).min() < -1e-8:
            raise ValueError("Matrice de corrélation réalisée invalide.")
        from .scenario_market import configured_path
        profiles = {tk: ({"ok": False, "error": "Dividendes synthétiques non fournis : hypothèse explicite conservée."}
                         if configured_path() else dividend_profile(tk, requested.isoformat())) for tk in tickers}
        yields = {tk: p["yield_declared"] for tk, p in profiles.items()
                  if p.get("ok") and p.get("yield_declared") is not None
                  and math.isfinite(p["yield_declared"]) and p["yield_declared"] >= 0}
        return {**{k: v for k, v in history.items() if k not in {"prices", "source_observation_dates", "carry_age_days"}},
                "tickers": list(tickers), "vols": {tk: float(calibrated["sigma"][tk]) for tk in tickers},
                "div_yields": yields, "dividend_profiles": profiles,
                "missing_dividends": [tk for tk in tickers if tk not in yields],
                "corr": {t1:{t2:float(matrix[i,j]) for j,t2 in enumerate(tickers)} for i,t1 in enumerate(tickers)},
                "period": period, "window_days": window, "n_obs": int(calibrated["n_returns"]),
                "requested_asof": requested.isoformat(),
                "estimator": {"volatility": "RMS_LOG_RETURNS", "correlation": "PEARSON_COMMON_SAMPLE",
                              "annualization": 252, "n_returns": int(calibrated["n_returns"]),
                              "common_sample": True, "correlation_psd": True}}
    except (ValueError, TypeError) as exc:
        return {"error": f"Calibration réalisée impossible : {exc}"}
    except Exception as exc:
        logger.exception("load_hist_vol")
        return {"error": str(exc)}


# ── Cache d'historique ──────────────────────────────────────────────
#
# Une valorisation en cours de vie reconstruit son contexte résiduel, donc
# retélécharge tout l'historique depuis le strike. Chaque analytique le refait,
# et le comparateur de déclinaisons le refait UNE FOIS PAR LIGNE : sur un panier
# de quatre noms avec sept déclinaisons, cela donnait trente-deux requêtes Yahoo
# séquentielles pour un historique rigoureusement identique — plusieurs minutes
# d'attente, et le régime où Yahoo se met à limiter les appels.
#
# TTL court plutôt que cache de session : en séance, un cours doit pouvoir
# bouger. Deux minutes couvrent largement un tableau comparatif complet tout en
# gardant l'application vivante sur un marché ouvert.
_TTL_PRIX = 120.0
_cache_prix: dict[tuple, tuple[float, dict]] = {}
_cache_lock = threading.Lock()
_cache_inflight = {}
_cache_epoch = 0

DEFAULT_MARKET_DATA_PROVIDER = "YAHOO_FINANCE"
SUPPORTED_MARKET_DATA_PROVIDERS = {DEFAULT_MARKET_DATA_PROVIDER}


def normalize_market_data_provider(provider: Optional[str]) -> str:
    """Return the configured provider code, rejecting unavailable adapters.

    The account-level field is deliberately a provider code rather than a
    Yahoo boolean.  Yahoo is the only adapter today; Bloomberg or Reuters can
    later implement the same contract without changing pricing callers.
    """
    normalized = str(provider or DEFAULT_MARKET_DATA_PROVIDER).strip().upper()
    if normalized not in SUPPORTED_MARKET_DATA_PROVIDERS:
        raise ValueError(
            f"Source de données non disponible : {normalized}. "
            f"Sources actives : {', '.join(sorted(SUPPORTED_MARKET_DATA_PROVIDERS))}."
        )
    return normalized


def market_data_provider_for_deal(deal, session) -> str:
    """Resolve the current data source attached to the deal's client account.

    Product-only and legacy deals have no client account and therefore use the
    platform default.  The function intentionally uses the SQLModel mapper
    dynamically, keeping this service independent from the database models.
    """
    from .scenario_market import configured_path, PROVIDER
    if configured_path():
        return PROVIDER
    client_id = getattr(deal, "client_id", None)
    if not client_id:
        return DEFAULT_MARKET_DATA_PROVIDER
    try:
        from ..db.models import Client
        client = session.get(Client, client_id)
    except Exception:
        client = None
    return normalize_market_data_provider(
        getattr(client, "market_data_provider", None) if client else None)


def _business_sessions_between(last_date: date, requested_end: date) -> int:
    """Weekday sessions expected after ``last_date`` through ``requested_end``.

    Yahoo does not expose a dependable exchange calendar for every instrument.
    This is therefore an age indicator, not a contractual calendar decision;
    weekend days never make a Friday close look stale.
    """
    if last_date >= requested_end:
        return 0
    cursor = last_date + timedelta(days=1)
    count = 0
    while cursor <= requested_end:
        if cursor.weekday() < 5:
            count += 1
        cursor += timedelta(days=1)
    return count


def vider_cache_prix() -> None:
    """Clear memory responses; dated durable observations remain reusable."""
    global _cache_epoch
    with _cache_lock:
        _cache_prix.clear()
        _cache_epoch += 1


def load_hist_prices(tickers: list[str], start: str, end: Optional[str] = None,
                     adjusted: bool = False, provider: str = DEFAULT_MARKET_DATA_PROVIDER,
                     allow_partial: bool = False) -> dict:
    """Coalesce identical reads; every caller receives an independent snapshot."""
    tickers = list(tickers)
    from ..core import market_storage, market_policy
    from ..runtime import business_today
    from .scenario_market import configured_path
    build = lambda: _load_hist_prices_uncached(tickers, start, end, adjusted, provider, allow_partial)
    if configured_path():
        return deepcopy(build())
    try:
        storage_revision = market_storage.view_revision()
    except ValueError as exc:
        return {'error':str(exc)}
    with _cache_lock:
        epoch = _cache_epoch
        key = (storage_revision, epoch, provider, tuple(tickers), start, end or business_today().isoformat(),
               adjusted, allow_partial, market_policy.POLICY_VERSION, market_policy.HISTORY_MAX_AGE_DAYS)
        cached = _cache_prix.get(key)
        if cached and time.monotonic()-cached[0] < _TTL_PRIX:
            return deepcopy(cached[1])
        future = _cache_inflight.get(key)
        leader = future is None
        if leader:
            future = Future()
            _cache_inflight[key] = future
    if not leader:
        return deepcopy(future.result())
    try:
        with market_storage.read_view():
            result = build()
        current_revision = market_storage.revision()
        with _cache_lock:
            if not result.get('error') and epoch == _cache_epoch and current_revision == storage_revision:
                if len(_cache_prix) >= 256:
                    _cache_prix.pop(next(iter(_cache_prix)))
                _cache_prix[key] = (time.monotonic(), deepcopy(result))
        future.set_result(deepcopy(result))
        return deepcopy(result)
    except BaseException as exc:
        future.set_exception(exc)
        raise
    finally:
        with _cache_lock:
            _cache_inflight.pop(key, None)


def _load_hist_prices_uncached(tickers, start, end, adjusted, provider, allow_partial):
    """Provider observations with durable local reuse and explicit coverage."""
    from ..runtime import business_today
    from ..core import market_policy, market_storage
    from .market_history import local_history, store_history, align_history, _path as shared_path
    from .scenario_market import configured_path, history
    if configured_path():
        result = history(tickers, start, end, adjusted)
        if result.get("error"):
            return result
        frames = {tk:pd.Series(values, index=pd.to_datetime(result["dates"])) for tk,values in result.get("prices", {}).items()}
        qualified = align_history(tickers, frames, start, end or business_today().isoformat(), adjusted,
                                  {tk:{"provider":result.get("provider"), "storage":"SCENARIO"} for tk in frames}, {}, allow_partial)
        return {**result, **qualified, "provider":result.get("provider", "SYNTHETIC_SCENARIO")}
    try:
        provider = normalize_market_data_provider(provider)
        requested_end = date.fromisoformat(end) if end else business_today()
        if date.fromisoformat(start) > requested_end:
            raise ValueError('La date de début doit précéder la date de fin.')
    except ValueError as exc:
        return {"error": str(exc)}
    end = requested_end.isoformat()
    series, sources, failures, fetched = {}, {}, {}, {}
    expected = market_storage.versions([shared_path(ticker,adjusted) for ticker in tickers])
    for ticker in tickers:
        local, source = local_history(ticker, start, end, adjusted)
        local_window = local.loc[(local.index >= pd.Timestamp(start)) & (local.index <= pd.Timestamp(end))] if local is not None else None
        usable = (local_window is not None and not local_window.empty
                  and source.get("requested_start", start) <= start
                  and market_policy.freshness(local_window.index[-1].date(), requested_end, "history")["qualified"])
        selected = local_window if usable else None
        if selected is None and _HAS_YF:
            try:
                frame = yf.Ticker(ticker).history(start=start,
                    end=(requested_end+timedelta(days=1)).isoformat(), auto_adjust=adjusted)
                if not frame.empty and "Close" in frame:
                    selected = market_storage.validate_frame(frame[['Close']], ('Close',))['Close']
                    selected = selected.loc[(selected.index >= pd.Timestamp(start)) & (selected.index <= pd.Timestamp(end))]
                    if not selected.empty:
                        source = dict(provider=provider, storage="PROVIDER", fetched_at=datetime.utcnow().isoformat(),
                                      requested_start=start, requested_end=end, finality="UNVERIFIED_PROVIDER_BAR")
                        fetched[ticker] = selected
            except Exception as exc:
                failures[ticker] = f"PROVIDER_UNAVAILABLE: {type(exc).__name__}"
        if selected is None or selected.empty:
            selected = local_window
        if selected is not None and not selected.empty:
            series[ticker] = selected
            sources[ticker] = source
        else:
            failures.setdefault(ticker, "NO_OBSERVATIONS")
    if fetched:
        try:
            with market_storage.transaction() as pending:
                pending.require_unchanged(expected)
                for ticker,values in fetched.items():
                    store_history(ticker,values,adjusted,start,end,transaction=pending)
        except (OSError,ValueError) as exc:
            for ticker in fetched:
                sources[ticker]['storage_error'] = str(exc)
    payload = align_history(tickers, series, start, end, adjusted, sources, failures, allow_partial)
    payload["retrieved_at"] = datetime.utcnow().isoformat()
    payload["fetched_at"] = min((source["fetched_at"] for source in sources.values() if source.get("fetched_at")), default=None)
    payload["age_sessions"] = {tk:_business_sessions_between(date.fromisoformat(day), requested_end)
                               for tk,day in payload["effective_dates"].items()}
    return payload


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
    from .scenario_market import configured_path
    if configured_path():
        # Do not relabel a simulated close as Yahoo. The ordinary manual
        # exception workflow must sign and source each reached fixing.
        return {"series": {}, "splits": {}, "currencies": {}, "provider": "YAHOO",
            "fetched_at": datetime.utcnow().isoformat(), "missing": tickers,
            "warnings": [{"code":"YAHOO_DISABLED_IN_SCENARIO", "message":"Fixings synthétiques à déclarer par décision utilisateur sourcée."}]}
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
        sources: dict[str, dict] = {}
        missing: list[str] = []
        for ticker in tickers:
            try:
                from hashlib import sha256
                import json
                from ..runtime import data_path
                from ..core.fixing_finality import POLICY_VERSION, qualify_close
                from ..core.market_policy import freshness
                cache_path = data_path("market_reference", sha256(ticker.upper().encode()).hexdigest()+".json")
                expected = market_storage.versions([cache_path])
                try:
                    cached = json.loads(market_storage.current_path(cache_path).read_text(encoding="utf-8"))
                    local = {d: v for d, v in cached["series"].items() if start <= d <= last_day.isoformat()}
                    if (local and cached["requested_start"] <= start
                            and qualify_close(last_day.isoformat(), cached["source"])["qualified"]
                            and freshness(max(local), last_day, "history")["qualified"]):
                        series[ticker], splits[ticker] = local, cached["splits"]
                        sources[ticker] = {**cached["source"], "storage": "MARKET_REFERENCE"}
                        if cached.get("currency"):
                            currencies[ticker] = cached["currency"]
                        continue
                except (OSError, ValueError, KeyError, TypeError):
                    pass
                instrument = yf.Ticker(ticker)
                hist = instrument.history(
                    start=start,
                    end=end_exclusive,
                    auto_adjust=False,
                    actions=True,
                )
                history_received_at = datetime.now(timezone.utc).isoformat()
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
                    metadata = {}
                    try:
                        metadata = instrument.get_history_metadata() or {}
                    except Exception:
                        pass
                    sources[ticker] = {
                        "exchange": metadata.get("exchangeName"),
                        "timezone": metadata.get("exchangeTimezoneName"),
                        "fetched_at": history_received_at,
                        "provider": "YAHOO_FINANCE", "price_type": "UNADJUSTED_CLOSE",
                    }
                    try:
                        with market_storage.transaction() as pending:
                            pending.require_unchanged(expected)
                            pending.json(cache_path, {"requested_start": start, "series": closes,
                                "splits": split_rows, "currency": currencies.get(ticker), "source": sources[ticker]})
                    except (OSError, ValueError, RuntimeError) as exc:
                        logger.warning("Reference close cache not published: %s", exc)
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
            "sources": sources,
            "finality_policy": POLICY_VERSION,
            "missing": sorted(set(missing)),
        }
    except Exception as exc:
        logger.exception("load_yahoo_reference_closes")
        return {"error": str(exc)}


def search_symbols(query: str, limit: int = 10) -> dict:
    """Résout un nom ou un fragment de symbole en tickers Yahoo.

    Il n'existe pas de liste exhaustive téléchargeable des instruments cotés :
    c'est la recherche qui tient lieu de référentiel, et elle a l'avantage
    d'être toujours à jour. « STM » rend STM (New York), STMPA.PA (Paris) et
    STMMI.MI (Milan) — trois cotations du même titre, entre lesquelles il faut
    trancher, puisqu'une note fixe sur une place et pas sur une autre.
    """
    if not _HAS_YF:
        return {"error": "yfinance non installé"}
    terme = (query or "").strip()
    if len(terme) < 2:
        return {"error": "Saisissez au moins deux caractères."}
    try:
        quotes = yf.Search(terme, max_results=max(1, min(25, limit))).quotes or []
    except Exception as exc:
        logger.debug("Yahoo search %s: %s", terme, exc)
        return {"error": f"Recherche Yahoo indisponible : {exc}"}
    return {"results": [
        {
            "ticker": q.get("symbol", ""),
            "label": q.get("shortname") or q.get("longname") or q.get("symbol", ""),
            "exchange": q.get("exchange") or "",
            "type": q.get("quoteType") or "",
        }
        for q in quotes if q.get("symbol")
    ]}


def probe_ticker(ticker: str) -> dict:
    """Vérifie qu'un ticker répond, avant de l'inscrire au référentiel.

    Un ticker muet ajouté en silence ne se découvre qu'au moment où l'on
    price — souvent des semaines plus tard, et toujours au mauvais moment. On
    tire un mois d'historique : s'il ne vient rien, on refuse. La devise est
    lue chez Yahoo plutôt que devinée d'après le suffixe de cotation.
    """
    if not _HAS_YF:
        return {"ok": False, "error": "yfinance non installé"}
    symbole = (ticker or "").strip()
    if not symbole:
        return {"ok": False, "error": "Ticker vide"}
    try:
        instrument = yf.Ticker(symbole)
        hist = instrument.history(period="1mo", auto_adjust=False)
        if hist.empty or "Close" not in hist.columns:
            return {"ok": False, "error": f"Aucune cotation pour « {symbole} »."}
        closes = hist["Close"].dropna()
        if closes.empty:
            return {"ok": False, "error": f"Aucune clôture exploitable pour « {symbole} »."}
        ccy = ""
        try:
            ccy = (instrument.fast_info.get("currency") or "").upper()
        except Exception:
            pass
        return {
            "ok": True,
            "last_close": round(float(closes.iloc[-1]), 6),
            "last_date": closes.index[-1].strftime("%Y-%m-%d"),
            "points": int(len(closes)),
            "ccy": ccy,
        }
    except Exception as exc:
        logger.debug("probe_ticker %s: %s", symbole, exc)
        return {"ok": False, "error": f"Ticker injoignable : {exc}"}


@market_storage.consistent_read
def dividend_profile(ticker: str, asof: Optional[str] = None,
                      window_years: float = 1.0) -> dict:
    """Rendement de dividende d'un titre, à une date donnée, par deux voies.

    Le champ `trailingAnnualDividendYield` de Yahoo est un instantané du JOUR :
    il ne sait rien dire du 8 mai 2026, et il tombe à zéro sur un titre qui a
    suspendu son dividende — sans distinguer « ne verse pas » de « donnée
    absente ». Cette fonction reconstruit le rendement à n'importe quelle date,
    et le fait deux fois :

    - `yield_declared` : les dividendes réellement détachés sur la fenêtre,
      rapportés au cours de fin de fenêtre. C'est la convention de pricing —
      ce que le forward consomme, puisqu'on escompte le futur au cours
      d'aujourd'hui.
    - `yield_implied` : lu dans l'écart entre la série ajustée et la série nue.
      Le rapport des deux vaut le produit des (1 − D/C) de chaque détachement,
      chacun pondéré par le cours de SA date. C'est le rendement réellement
      subi par la série de prix.

    Les deux répondent à des questions différentes et doivent rester proches.
    Quand ils divergent, quelque chose manque au flux de dividendes — une
    opération sur titre, typiquement. Le signaler vaut mieux qu'un chiffre
    silencieusement faux.
    """
    symbole = (ticker or "").strip()
    if not symbole:
        return {"ok": False, "error": "Ticker vide"}
    try:
        from ..runtime import business_today
        from ..core.market_policy import freshness
        from .market_history import local_profile, store_profile, store_history, local_history
        fin = date.fromisoformat(asof) if asof else business_today()
        if not math.isfinite(window_years) or window_years <= 0:
            return {"ok": False, "error": "Fenêtre de dividendes invalide."}
        cached = local_profile(symbole, fin.isoformat(), window_years)
        if cached:
            cached["freshness"] = freshness(cached.get("asof_effective"), fin, "history")
            if cached["freshness"]["qualified"]:
                return cached
        if not _HAS_YF:
            return {"ok": False, "error": "Profil de dividendes absent du stock local et fournisseur indisponible."}
        from .market_history import _path as shared_path, _profile_path
        expected = market_storage.versions([shared_path(symbole,True),shared_path(symbole,False),
                                            _profile_path(symbole,fin.isoformat(),window_years)])
        debut = fin - timedelta(days=round(window_years * 365.25))
        # Marge amont : il faut une clôture avant le début de fenêtre pour
        # ancrer le rapport, et le premier jour peut être fermé.
        marge = (debut - timedelta(days=10)).isoformat()
        borne = (fin + timedelta(days=1)).isoformat()

        instrument = yf.Ticker(symbole)
        def observations(adjusted):
            local, source = local_history(symbole, marge, fin.isoformat(), adjusted)
            if local is not None:
                local = local.loc[(local.index >= pd.Timestamp(marge)) & (local.index <= pd.Timestamp(fin))]
                if (not local.empty and source.get('requested_start', marge) <= marge
                        and freshness(local.index[-1].date(), fin, 'history')['qualified']):
                    return local.to_frame('Close'), False
            return instrument.history(start=marge, end=borne, auto_adjust=adjusted), True
        nu, fetched_raw = observations(False)
        ajuste, fetched_adjusted = observations(True)
        if nu.empty or ajuste.empty or 'Close' not in nu or 'Close' not in ajuste:
            return {"ok":False,"error":f"Cours bruts ou ajustés absents pour « {symbole} »."}
        nu = market_storage.validate_frame(nu[['Close']], ('Close',))
        ajuste = market_storage.validate_frame(ajuste[['Close']], ('Close',))
        if nu.empty or "Close" not in nu.columns:
            return {"ok": False, "error": f"Aucune cotation pour « {symbole} » sur la période."}

        closes_nus = nu["Close"].dropna()
        closes_nus.index = closes_nus.index.tz_localize(None)
        closes_aj = ajuste["Close"].dropna()
        closes_aj.index = closes_aj.index.tz_localize(None)

        avant_fin = closes_nus[closes_nus.index <= _ts(fin)]
        avant_debut = closes_nus[closes_nus.index <= _ts(debut)]
        if avant_fin.empty:
            return {"ok": False, "error": f"Aucune clôture au {fin} pour « {symbole} »."}
        cours_fin = float(avant_fin.iloc[-1])

        detaches = []
        try:
            serie_div = instrument.dividends
            serie_div.index = serie_div.index.tz_localize(None)
            fenetre = serie_div[(serie_div.index > _ts(debut)) & (serie_div.index <= _ts(fin))]
            detaches = [{"date": d.strftime("%Y-%m-%d"), "amount": round(float(v), 6)}
                        for d, v in fenetre.items()]
        except Exception as exc:
            logger.debug("dividends %s: %s", symbole, exc)
            return {"ok": False, "error": "Historique des dividendes indisponible ; rendement à renseigner."}

        total = sum(d["amount"] for d in detaches)
        yield_declared = round(total / cours_fin / window_years, 6) if cours_fin else 0.0

        yield_implied = None
        rapports = (closes_aj / closes_nus).dropna()
        rapports = rapports[rapports > 0]
        if not avant_debut.empty and len(rapports) >= 2:
            r_debut = rapports[rapports.index <= _ts(debut)]
            r_fin = rapports[rapports.index <= _ts(fin)]
            if not r_debut.empty and not r_fin.empty:
                yield_implied = round(
                    -math.log(float(r_debut.iloc[-1]) / float(r_fin.iloc[-1])) / window_years, 6)

        ecart = (round(abs(yield_declared - yield_implied), 6)
                 if yield_implied is not None else None)
        # Un ecart de quelques dixiemes de point est NORMAL : les deux methodes
        # ponderent differemment — le declare rapporte au cours de fin de
        # fenetre, l implicite au cours de chaque detachement. Sur un titre qui
        # a beaucoup bouge, l ecart suit le mouvement. Ce qui n est pas normal,
        # c est une divergence de plus de moitie : elle trahit un dividende ou
        # une operation sur titre absent du flux Yahoo.
        plafond = max(yield_declared, yield_implied or 0.0)
        suspect = bool(ecart is not None and ecart > 0.005
                       and plafond > 0 and ecart / plafond > 0.6)
        result = {
            "ok": True,
            "ticker": symbole,
            "asof": fin.isoformat(),
            "asof_effective": avant_fin.index[-1].date().isoformat(),
            "window_years": window_years,
            "price": round(cours_fin, 6),
            "yield_declared": yield_declared,
            "yield_implied": yield_implied,
            "dividends": detaches,
            # Aucun dividende ET aucun écart entre les deux séries : le titre
            # ne verse pas. C'est un fait, pas une donnée manquante — et c'est
            # la distinction que le champ Yahoo ne faisait pas.
            "pays_dividends": bool(detaches) or bool(yield_implied and yield_implied > 1e-6),
            "discrepancy": ecart,
            "suspect": suspect,
            "provider": "YAHOO_FINANCE",
            "method": "TRAILING_CASH_DIVIDENDS_OVER_SPOT",
            "price_type": "UNADJUSTED_CLOSE",
            "adjusted_cross_check": True,
            "fetched_at": datetime.utcnow().isoformat(),
            "storage": "PROVIDER",
            "freshness": freshness(avant_fin.index[-1].date(), fin, "history"),
        }
        if not result["freshness"]["qualified"]:
            result.update(ok=False, error="Cours de référence du dividende hors politique de fraîcheur.")
        if result["ok"]:
            try:
                with market_storage.transaction() as pending:
                    pending.require_unchanged(expected)
                    if fetched_raw:
                        store_history(symbole, closes_nus, False, marge, fin.isoformat(), transaction=pending)
                    if fetched_adjusted:
                        store_history(symbole, closes_aj, True, marge, fin.isoformat(), transaction=pending)
                    store_profile(symbole, fin.isoformat(), window_years, result, transaction=pending)
            except (OSError, ValueError) as exc:
                result["storage_error"] = str(exc)
        return result
    except Exception as exc:
        logger.debug("dividend_profile %s: %s", symbole, exc)
        return {"ok": False, "error": f"Dividendes indisponibles : {exc}"}


def _ts(jour: date):
    import pandas as pd
    return pd.Timestamp(jour)
