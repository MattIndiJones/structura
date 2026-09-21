"""Shared study controls: dates, causal prices, inputs and provenance."""
from __future__ import annotations
import datetime as dt
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd

METHOD_VERSION = "studies-2.4"

def date_key(value) -> str:
    return pd.Timestamp(value).strftime("%Y-%m-%d")

def validate_nav(rows: list[dict]) -> list[dict]:
    if len(rows) > 20000:
        raise ValueError("Maximum 20 000 lignes NAV par étude")
    result, seen = [], set()
    for row in rows:
        key = date_key(row["date"])
        value = float(row["nav"])
        if key in seen or not np.isfinite(value) or value <= 0:
            raise ValueError(f"NAV invalide ou date dupliquée : {key}")
        seen.add(key)
        outstanding = row.get("outstanding")
        if outstanding is not None and (not np.isfinite(float(outstanding)) or float(outstanding) < 0):
            raise ValueError(f"Encours invalide : {key}")
        result.append({**row, "date": key, "nav": value})
    return sorted(result, key=lambda r: r["date"])

def price_at(series: pd.Series, as_of, max_age_days: int = 7) -> float:
    from .amc_market_bundle import active_bundle
    bundle = active_bundle()
    if bundle is not None and id(series) in bundle.fx_ids:
        return bundle.fx_at(series, as_of, max_age_days)
    s = series.copy()
    s.index = pd.to_datetime(s.index).tz_localize(None).normalize()
    end = pd.Timestamp(as_of).tz_localize(None).normalize()
    s = s.sort_index().loc[lambda x: x.index <= end].dropna()
    if s.empty or (end - s.index[-1]).days > max_age_days:
        raise ValueError(f"Prix/change absent ou périmé au {date_key(as_of)}")
    value = float(s.iloc[-1])
    if not np.isfinite(value) or value <= 0:
        raise ValueError("Prix/change non positif ou non fini")
    return value

def resolve_file(folder: str, name: str) -> str:
    if not name:
        return ""
    root = Path(folder).resolve()
    candidate = (root / name).resolve()
    if not candidate.is_relative_to(root):
        raise ValueError("Le fichier doit appartenir au dossier de l'étude")
    if candidate.is_file():
        if candidate.stat().st_size > 20 * 1024 * 1024:
            raise ValueError("Fichier source trop volumineux (20 Mo maximum)")
        return str(candidate)
    hits = list(root.glob(name)) if not Path(name).is_absolute() else []
    hits = [p.resolve() for p in hits if p.is_file() and p.resolve().is_relative_to(root)]
    if len(hits) != 1:
        raise ValueError(f"Fichier absent ou ambigu : {name}")
    return resolve_file(folder, str(hits[0]))

def fingerprint(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str, ensure_ascii=False,
                                     allow_nan=False).encode()).hexdigest()

def input_provenance(folder: str, files: dict, manifest: dict) -> dict:
    names = [files.get("market_data"), files.get("composition"), files.get("nav_timeseries"), files.get("cash_events"), files.get("dividends"), *files.get("orders", [])]
    hashes = {name: hashlib.sha256(Path(resolve_file(folder, name)).read_bytes()).hexdigest()
              for name in names if name}
    return {"method_version": METHOD_VERSION, "input_hashes": hashes,
            "manifest_hash": fingerprint(manifest), "generated_at": dt.datetime.now(dt.timezone.utc).isoformat()}

def clustered_mean_test(values: list[float], groups: list[str], null: float = 0.0) -> dict:
    """Test group means; repeated trades/horizons are not independent samples."""
    from scipy.stats import ttest_1samp
    means = pd.DataFrame({"value": values, "group": groups}).dropna().groupby("group")["value"].mean()
    n = len(means)
    if n < 10 or means.std() <= 1e-12:
        return {"tstat": 0.0, "pvalue": 1.0, "n_independent_groups": n, "inference_available": False}
    test = ttest_1samp(means, null)
    return {"tstat": float(test.statistic), "pvalue": float(test.pvalue),
            "n_independent_groups": n, "inference_available": True}


def source_orders(study: dict) -> list[dict]:
    """Read the frozen order perimeter; legacy studies must be recalculated."""
    if "source_orders" not in study:
        raise ValueError("Étude ancienne : relancez le calcul pour figer les ordres et la date d’arrêté.")
    end = pd.Timestamp(study["meta"]["as_of"]).normalize()
    return [{**o, "date": pd.Timestamp(o["date"]).to_pydatetime()}
            for o in study["source_orders"] if o.get("date") and pd.Timestamp(o["date"]).normalize() <= end]


from contextvars import ContextVar
from contextlib import contextmanager
_market_inputs = ContextVar("study_market_inputs", default=None)


@contextmanager
def market_capture():
    records = {}
    token = _market_inputs.set(records)
    try:
        yield records
    finally:
        _market_inputs.reset(token)


def record_market(label, values):
    records = _market_inputs.get()
    if records is not None and values is not None and len(values):
        encoded = values.to_json(date_format="iso", double_precision=15)
        records[label] = {"sha256": hashlib.sha256(encoded.encode()).hexdigest(),
                          "n_obs": len(values), "start": str(values.index.min()), "end": str(values.index.max())}
    return values
