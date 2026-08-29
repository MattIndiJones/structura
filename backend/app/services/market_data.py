"""Yahoo Finance market data — realized vol, dividends, correlations, historical prices."""
from __future__ import annotations
import logging
import math
import time
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


def vider_cache_prix() -> None:
    """Force le prochain appel à repartir de la source. Pour les tests, et pour
    un rafraîchissement explicite demandé par l'utilisateur."""
    _cache_prix.clear()


def load_hist_prices(tickers: list[str], start: str, end: Optional[str] = None,
                      adjusted: bool = False) -> dict:
    """Daily close prices for backtest replay.

    `adjusted` decides WHICH price, and the two answer different questions.

    False (the default) returns the raw close — the price that actually traded
    that day. Every payoff reads this one: a barrier, a coupon condition, a
    fixing and a strike are written on the price the market printed, not on a
    total-return series. Yahoo's adjusted close deflates past prices by every
    dividend paid since, so a 50% barrier tested on it is crossed later than in
    reality, or never. On Société Générale at 14/06/2024 the raw close is 22.150
    — the strike of a real term sheet to the cent — where the adjusted one says
    21.105, 4.7% off. It also keeps this feed consistent with the contractual
    fixings, which load_yahoo_reference_closes already takes raw.

    True returns the dividend-adjusted close, for statistical estimates where
    total return is the honest input: realized volatility, correlations,
    calibration. Never for anything a payoff reads."""
    if not _HAS_YF:
        return {"error": "yfinance non installé"}

    # La clé porte les tickers TRIÉS : deux appels au même panier dans un ordre
    # différent décrivent le même historique.
    cle = (tuple(sorted(tickers)), start, end, adjusted)
    fige = _cache_prix.get(cle)
    if fige is not None and (time.monotonic() - fige[0]) < _TTL_PRIX:
        # Copie superficielle : l'appelant ne doit pas pouvoir muter le cache.
        return {**fige[1]}

    try:
        end = end or datetime.today().strftime("%Y-%m-%d")
        price_series: dict = {}
        for tk in tickers:
            try:
                hist = yf.Ticker(tk).history(start=start, end=end, auto_adjust=adjusted)
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
        # Seuls les SUCCÈS sont mis en cache : figer une erreur réseau la
        # rejouerait pendant deux minutes alors qu'un simple réessai passerait.
        _cache_prix[cle] = (time.monotonic(), payload)
        return {**payload}
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
    if not _HAS_YF:
        return {"ok": False, "error": "yfinance non installé"}
    symbole = (ticker or "").strip()
    if not symbole:
        return {"ok": False, "error": "Ticker vide"}
    try:
        fin = date.fromisoformat(asof) if asof else date.today()
        debut = fin - timedelta(days=round(window_years * 365.25))
        # Marge amont : il faut une clôture avant le début de fenêtre pour
        # ancrer le rapport, et le premier jour peut être fermé.
        marge = (debut - timedelta(days=10)).isoformat()
        borne = (fin + timedelta(days=1)).isoformat()

        instrument = yf.Ticker(symbole)
        nu = instrument.history(start=marge, end=borne, auto_adjust=False)
        ajuste = instrument.history(start=marge, end=borne, auto_adjust=True)
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
        return {
            "ok": True,
            "ticker": symbole,
            "asof": fin.isoformat(),
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
        }
    except Exception as exc:
        logger.debug("dividend_profile %s: %s", symbole, exc)
        return {"ok": False, "error": f"Dividendes indisponibles : {exc}"}


def _ts(jour: date):
    import pandas as pd
    return pd.Timestamp(jour)
