"""Request-scoped, explicit market inputs. Never populate shared market caches."""
from contextlib import contextmanager
from contextvars import ContextVar
import json
from pathlib import Path

import numpy as np
import pandas as pd

_current = ContextVar("study_market_bundle", default=None)


def active_bundle():
    return _current.get()


def _frame(rows, columns, *, positive=True):
    frame = pd.DataFrame(rows)
    if frame.empty or not {"date", *columns}.issubset(frame.columns):
        raise ValueError("Série de marché vide ou colonnes manquantes")
    frame.index = pd.to_datetime(frame.pop("date"), errors="raise")
    if frame.index.tz is not None or frame.index.hasnans or frame.index.has_duplicates:
        raise ValueError("Dates de marché invalides ou dupliquées")
    if not frame.index.equals(frame.index.normalize()):
        raise ValueError("Dates journalières requises")
    frame = frame[columns].astype(float).sort_index()
    if not np.isfinite(frame.to_numpy()).all() or (positive and (frame <= 0).any().any()):
        raise ValueError("Valeurs de marché invalides")
    return frame


class MarketBundle:
    def __init__(self, data):
        if data.get("schema_version") != "1.0":
            raise ValueError("Version du dossier de marché non reconnue")
        self.prices, self.aliases, self.splits = {}, {}, {}
        self.sectors = {"Liquidités": "Liquidités"}
        for key, asset in data["assets"].items():
            frame = _frame(asset["rows"], ["close", "price_close"])
            currency = asset["currency"]
            if len(currency) != 3 or not currency.isupper():
                raise ValueError("Devise de marché invalide")
            adjustment = pd.Timestamp(asset["adjustment_date"])
            if adjustment != adjustment.normalize() or adjustment < frame.index[-1]:
                raise ValueError("Date d'ajustement des splits invalide")
            frame.attrs.update(currency=currency, adjustment_date=str(adjustment.date()), source="study_bundle")
            self.prices[key] = frame
            self.aliases[key] = key
            name = asset.get("name", key)
            if name in self.aliases and self.aliases[name] != key:
                raise ValueError("Nom de titre ambigu")
            self.aliases[name] = key
            self.sectors[name] = asset["sector"]
            splits = asset.get("splits", {})
            self.splits[key] = {pd.Timestamp(d).date(): float(r) for d, r in splits.items()}
            if any(not np.isfinite(r) or r <= 0 for r in self.splits[key].values()):
                raise ValueError("Ratio de split invalide")
        self.fx_base = {ccy: _frame(rows, ["rate"])["rate"] for ccy, rows in data["fx_usd_per_local"].items()}
        if "USD" not in self.fx_base or not (self.fx_base["USD"] == 1).all():
            raise ValueError("La convention FX exige USD par unité locale et USD/USD = 1")
        self.fx_cache, self.fx_ids, self.lookup_cache = {}, set(), {}
        self.factor_key = data["factors"]["series"]
        self.factors = _frame(data["factors"]["rows"], data["factors"]["columns"], positive=False)
        self.benchmark_key = data["benchmark"]["ticker"]
        self.benchmark = _frame(data["benchmark"]["rows"], ["close"])["close"]
        self.brinson = data.get("brinson")
        if self.brinson:
            weights, returns = self.brinson["weights"], self.brinson["returns"]
            if (not weights or abs(sum(weights.values()) - 1) > 1e-8
                    or any(not np.isfinite(w) or w < 0 for w in weights.values())
                    or any(s not in returns or not np.isfinite(returns[s]) or returns[s] < -1 for s in weights)):
                raise ValueError("Décomposition sectorielle du benchmark invalide")

    def load(self, key):
        if key not in self.aliases:
            raise ValueError(f"Titre absent du dossier de marché : {key}")
        from .amc_controls import record_market
        return record_market(f"bundle:prices:{key}", self.prices[self.aliases[key]].copy())

    def fx(self, source, target):
        key = (source, target)
        if key not in self.fx_cache:
            if source not in self.fx_base or target not in self.fx_base:
                raise ValueError(f"Change absent du dossier : {source}/{target}")
            series = (self.fx_base[source] / self.fx_base[target]).dropna()
            self.fx_cache[key] = series
            self.fx_ids.add(id(series))
            from .amc_controls import record_market
            record_market(f"bundle:fx:{source}{target}", series)
        return self.fx_cache[key]

    def benchmark_series(self, ticker):
        if ticker != self.benchmark_key:
            raise ValueError(f"Benchmark absent du dossier : {ticker}")
        from .amc_controls import record_market
        return record_market(f"bundle:benchmark:{ticker}", self.benchmark.copy())

    def sector_data(self, start, end):
        if not self.brinson or (start, end) != (self.brinson["start"], self.brinson["end"]):
            raise ValueError("Décomposition sectorielle absente pour cette période de référence")
        return self.brinson

    def fx_at(self, series, as_of, max_age_days):
        # Only owned, validated, immutable FX series take this fast causal path.
        key = (id(series), as_of, max_age_days)
        if key in self.lookup_cache:
            return self.lookup_cache[key]
        end = pd.Timestamp(as_of).tz_localize(None).normalize()
        i = series.index.searchsorted(end, side="right") - 1
        if i < 0 or (end - series.index[i]).days > max_age_days:
            raise ValueError(f"Prix/change absent ou périmé au {end.date()}")
        value = float(series.iloc[i])
        self.lookup_cache[key] = value
        return value


@contextmanager
def market_bundle(folder, name):
    from .amc_controls import resolve_file
    bundle = MarketBundle(json.loads(Path(resolve_file(folder, name)).read_text(encoding="utf-8"))) if name else None
    token = _current.set(bundle)
    try:
        yield bundle
    finally:
        _current.reset(token)
