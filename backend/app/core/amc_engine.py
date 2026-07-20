"""AMC Fama-French analysis engine.

Parses the diagnostic Excel, downloads FF factors from Ken French's library,
fetches benchmark via yfinance, runs OLS + rolling OLS, and returns a
self-contained result dict for the frontend.
"""
from __future__ import annotations

import io
import math
import zipfile
import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import requests
import statsmodels.api as sm
import yfinance as yf
from scipy import stats as _scipy_stats

# ── Persistent FF factor store (never auto-deleted, updated via /ff-refresh) ──
_FF_STORE = Path(__file__).parent.parent.parent / "data" / "ff_factors"
_FF_STORE.mkdir(parents=True, exist_ok=True)

# ── Fama-French series catalog ─────────────────────────────────────────

FF_SERIES: dict[str, dict] = {
    "Developed_5F": {
        "label": "Marchés Développés 5F — proxy Global (Mkt-RF, SMB, HML, RMW, CMA) ✓ actuel",
        "url": "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/Developed_5_Factors_daily_CSV.zip",
        "factors": ["Mkt-RF", "SMB", "HML", "RMW", "CMA"],
        "rf_col": "RF",
        "scope": "Developed",
    },
    "Developed_5F_MOM": {
        "label": "Marchés Développés 5F + Momentum Carhart (MOM/WML) ✓ actuel",
        "url": "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/Developed_5_Factors_daily_CSV.zip",
        "url_mom": "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/Developed_Mom_Factor_daily_CSV.zip",
        "mom_col": "WML",
        "factors": ["Mkt-RF", "SMB", "HML", "RMW", "CMA", "MOM"],
        "rf_col": "RF",
        "scope": "Developed",
    },
    "Developed_3F": {
        "label": "Marchés Développés 3F — proxy Global (Mkt-RF, SMB, HML) ✓ actuel",
        "url": "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/Developed_3_Factors_daily_CSV.zip",
        "factors": ["Mkt-RF", "SMB", "HML"],
        "rf_col": "RF",
        "scope": "Developed",
    },
    "Global_3F": {
        "label": "Global 3F (Mkt-RF, SMB, HML) — données jusqu'en 2019",
        "url": "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/Global_3_Factors_daily_CSV.zip",
        "factors": ["Mkt-RF", "SMB", "HML"],
        "rf_col": "RF",
        "scope": "Global",
    },
    "Global_5F": {
        "label": "Global 5F (+ RMW, CMA) — données jusqu'en 2019",
        "url": "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/Global_5_Factors_daily_CSV.zip",
        "factors": ["Mkt-RF", "SMB", "HML", "RMW", "CMA"],
        "rf_col": "RF",
        "scope": "Global",
    },
    "US_3F": {
        "label": "US 3 Facteurs  (Mkt-RF, SMB, HML) — Ken French",
        "url": "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/F-F_Research_Data_Factors_daily_CSV.zip",
        "factors": ["Mkt-RF", "SMB", "HML"],
        "rf_col": "RF",
        "scope": "US",
    },
    "US_5F": {
        "label": "US 5 Facteurs  (+ RMW, CMA) — Ken French",
        "url": "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/F-F_Research_Data_5_Factors_2x3_daily_CSV.zip",
        "factors": ["Mkt-RF", "SMB", "HML", "RMW", "CMA"],
        "rf_col": "RF",
        "scope": "US",
    },
    "US_5F_MOM": {
        "label": "US 5 Facteurs + Momentum Carhart (MOM) — Ken French",
        "url": "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/F-F_Research_Data_5_Factors_2x3_daily_CSV.zip",
        "url_mom": "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/F-F_Momentum_Factor_daily_CSV.zip",
        "mom_col": "Mom",
        "factors": ["Mkt-RF", "SMB", "HML", "RMW", "CMA", "MOM"],
        "rf_col": "RF",
        "scope": "US",
    },
    "EU_3F": {
        "label": "Europe 3 Facteurs  (Mkt-RF, SMB, HML) — Ken French",
        "url": "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/Europe_3_Factors_daily_CSV.zip",
        "factors": ["Mkt-RF", "SMB", "HML"],
        "rf_col": "RF",
        "scope": "Europe",
    },
    "EU_5F": {
        "label": "Europe 5 Facteurs  (+ RMW, CMA) — Ken French",
        "url": "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/Europe_5_Factors_daily_CSV.zip",
        "factors": ["Mkt-RF", "SMB", "HML", "RMW", "CMA"],
        "rf_col": "RF",
        "scope": "Europe",
    },
    "EU_5F_MOM": {
        "label": "Europe 5 Facteurs + Momentum Carhart (MOM/WML) — Ken French",
        "url": "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/Europe_5_Factors_daily_CSV.zip",
        "url_mom": "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/Europe_Mom_Factor_daily_CSV.zip",
        "mom_col": "WML",
        "factors": ["Mkt-RF", "SMB", "HML", "RMW", "CMA", "MOM"],
        "rf_col": "RF",
        "scope": "Europe",
    },
}

BENCHMARKS: list[dict] = [
    # ── Marchés larges ─────────────────────────────────────────────
    {"ticker": "ACWI",  "label": "MSCI ACWI – Monde (ACWI – iShares)",          "group": "Large"},
    {"ticker": "URTH",  "label": "MSCI World – Développés (URTH – iShares)",     "group": "Large"},
    {"ticker": "SPY",   "label": "S&P 500 (SPY – State Street)",                 "group": "Large"},
    {"ticker": "VGK",   "label": "MSCI Europe (VGK – Vanguard)",                 "group": "Large"},
    {"ticker": "EEM",   "label": "MSCI Emerging Markets (EEM – iShares)",        "group": "Large"},
    # ── Financières ────────────────────────────────────────────────
    {"ticker": "IXG",   "label": "MSCI World Financials – Global (IXG – iShares)","group": "Financières"},
    {"ticker": "XLF",   "label": "S&P 500 Financials – US (XLF – SPDR)",         "group": "Financières"},
    {"ticker": "EUFN",  "label": "MSCI Europe Financials (EUFN – iShares)",      "group": "Financières"},
    {"ticker": "IAI",   "label": "US Brokers & Exchanges (IAI – iShares)",       "group": "Financières"},
    {"ticker": "KBE",   "label": "S&P Bank ETF – US Banks (KBE – SPDR)",         "group": "Financières"},
    {"ticker": "ARKF",  "label": "ARK Fintech Innovation (ARKF)",                "group": "Financières"},
    # ── Infrastructures ────────────────────────────────────────────
    {"ticker": "IGF",   "label": "MSCI World Infrastructure (IGF – iShares)",   "group": "Infrastructures"},
    {"ticker": "NFRA",  "label": "Global Infrastructure (NFRA – FlexShares)",   "group": "Infrastructures"},
    {"ticker": "PAVE",  "label": "US Infrastructure (PAVE – Global X)",         "group": "Infrastructures"},
    # ── Longévité ──────────────────────────────────────────────────
    {"ticker": "AGED.L","label": "iShares Ageing Population UCITS ETF (IE00BYZK4669 – iSTOXX FactSet Ageing Population)", "group": "Longévité"},
    # ── Personnalisé ───────────────────────────────────────────────
    {"ticker": "CUSTOM","label": "Personnalisé (entrer un ticker)",              "group": "Autre"},
]


# ── Excel parsing ──────────────────────────────────────────────────────

def _safe_records(df: pd.DataFrame) -> list[dict]:
    """Convert DataFrame → JSON-safe records: Timestamps to str, NaN/inf to None."""
    if df.empty:
        return []
    df = df.copy()
    for col in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            df[col] = df[col].dt.strftime("%Y-%m-%d")
    records = df.to_dict("records")
    # pandas float NaN cannot be stored as None in float columns — sanitize post-conversion
    for row in records:
        for k, v in list(row.items()):
            if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                row[k] = None
    return records


def parse_amc_excel(buf: io.BytesIO) -> dict:
    """Return structured data from the AMC diagnostic workbook."""
    wb = pd.ExcelFile(buf)
    sheets = wb.sheet_names

    # Dashboard meta
    meta: dict[str, Any] = {}
    if "Dashboard" in sheets:
        df = wb.parse("Dashboard", header=None)
        for _, row in df.iterrows():
            vals = [str(v).strip() for v in row if pd.notna(v) and str(v).strip()]
            if len(vals) >= 2:
                key, val = vals[0], vals[1]
                if "Product name" in key:  meta["product_name"] = val
                elif "ISIN" in key:         meta["isin"] = val
                elif "Currency" in key:     meta["currency"] = val
                elif "Issue date" in key:   meta["issue_date"] = val

    # NAV history — try known sheet names first, then scan all sheets
    nav_df = pd.DataFrame()
    _NAV_SHEET_PRIORITY = ["NAV_History", "NAV", "Nav", "Sheet1", "Data"]
    _nav_candidates = _NAV_SHEET_PRIORITY + [s for s in sheets if s not in _NAV_SHEET_PRIORITY]
    _NAV_COL_NAMES = {"NAV", "Nav", "Price", "Close", "Value", "Net Asset Value"}

    for _sheet in _nav_candidates:
        if _sheet not in sheets:
            continue
        _df = wb.parse(_sheet)
        if _df.empty:
            continue
        _df.columns = [str(c).strip() for c in _df.columns]
        _date_col = next((c for c in _df.columns if "date" in c.lower()), None)
        _nav_col  = next((c for c in _df.columns if c in _NAV_COL_NAMES), None)
        _oq_col   = next((c for c in _df.columns if "outstanding" in c.lower()), None)
        if _date_col and _nav_col:
            _cols = [_date_col, _nav_col] + ([_oq_col] if _oq_col else [])
            nav_df = _df[_cols].rename(columns={_date_col: "date", _nav_col: "nav",
                                                 **({_oq_col: "Outstanding Quantity"} if _oq_col else {})})
            nav_df["date"] = pd.to_datetime(nav_df["date"], errors="coerce")
            nav_df = nav_df.dropna(subset=["date", "nav"]).sort_values("date")
            nav_df["nav"] = pd.to_numeric(nav_df["nav"], errors="coerce")
            nav_df = nav_df.dropna(subset=["nav"])
            if "Outstanding Quantity" in nav_df.columns:
                nav_df["Outstanding Quantity"] = pd.to_numeric(nav_df["Outstanding Quantity"], errors="coerce")
            nav_df["return"] = nav_df["nav"].pct_change()
            nav_df["return"] = nav_df["return"].where(pd.notna(nav_df["return"]), None)
            break  # found valid NAV sheet

    # Transactions
    tx_df = pd.DataFrame()
    if "Transactions" in sheets:
        tx_df = wb.parse("Transactions")
        tx_df.columns = [str(c).strip() for c in tx_df.columns]
        date_col = next((c for c in tx_df.columns if c == "Date"), None)
        if date_col:
            tx_df["Date"] = pd.to_datetime(tx_df["Date"], errors="coerce")
            tx_df = tx_df.dropna(subset=["Date"])

    # Current composition
    comp_df = pd.DataFrame()
    if "Current_Composition_API" in sheets:
        comp_df = wb.parse("Current_Composition_API")
        comp_df.columns = [str(c).strip() for c in comp_df.columns]

    # Factsheet exposures
    exposures: dict = {}
    if "Factsheet_Exposures" in sheets:
        fe = wb.parse("Factsheet_Exposures", header=None)
        def _extract_section(df, col_name, col_weight, skip_header=2):
            rows = []
            for _, row in df.iloc[skip_header:].iterrows():
                name = row.iloc[col_name] if col_name < len(row) else None
                weight = row.iloc[col_weight] if col_weight < len(row) else None
                if pd.notna(name) and pd.notna(weight):
                    try:
                        rows.append({"name": str(name), "weight": float(weight)})
                    except (ValueError, TypeError):
                        pass
            return rows
        exposures["sectors"]    = _extract_section(fe, 0, 1)
        exposures["countries"]  = _extract_section(fe, 3, 4)
        exposures["currencies"] = _extract_section(fe, 6, 7)

    return {
        "meta": meta,
        "nav": _safe_records(nav_df),
        "transactions": _safe_records(tx_df),
        "composition": _safe_records(comp_df),
        "exposures": exposures,
    }


# ── FF factor store — load / refresh ──────────────────────────────────

def _ff_parquet(series_key: str) -> Path:
    return _FF_STORE / f"{series_key}.parquet"


def ff_data_status() -> list[dict]:
    """Return availability status for every FF series."""
    result = []
    for key, info in FF_SERIES.items():
        p = _ff_parquet(key)
        if p.exists():
            df = pd.read_parquet(p)
            mtime = datetime.datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
            result.append({
                "key": key, "label": info["label"],
                "available": True,
                "rows": len(df),
                "date_min": str(df.index.min().date()),
                "date_max": str(df.index.max().date()),
                "updated_at": mtime,
            })
        else:
            result.append({
                "key": key, "label": info["label"],
                "available": False, "rows": 0,
                "date_min": None, "date_max": None, "updated_at": None,
            })
    return result


def ff_refresh(series_key: str) -> dict:
    """Download from Ken French library and save permanently.

    For +MOM series, downloads the 5F file and the separate momentum file
    then merges them on the date index before saving.
    """
    if series_key not in FF_SERIES:
        raise ValueError(f"Série inconnue : {series_key}")
    info = FF_SERIES[series_key]

    def _fetch_zip(url: str) -> str:
        resp = requests.get(url, timeout=60)
        resp.raise_for_status()
        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            csv_name = next(n for n in zf.namelist() if n.lower().endswith(".csv"))
            return zf.read(csv_name).decode("latin-1", errors="replace")

    df = _parse_ff_csv(_fetch_zip(info["url"]))

    if "url_mom" in info:
        df_mom = _parse_ff_csv(_fetch_zip(info["url_mom"]))
        mom_col = info.get("mom_col", "Mom")
        if mom_col in df_mom.columns:
            df_mom = df_mom[[mom_col]].rename(columns={mom_col: "MOM"})
        elif df_mom.shape[1] == 1:
            df_mom.columns = ["MOM"]
        df = df.join(df_mom[["MOM"]], how="inner")

    df.to_parquet(_ff_parquet(series_key))
    return {
        "key": series_key, "rows": len(df),
        "date_min": str(df.index.min().date()),
        "date_max": str(df.index.max().date()),
    }


def _load_ff_data(series_key: str) -> pd.DataFrame:
    """Load FF data from permanent store. Raises ValueError if not yet imported."""
    p = _ff_parquet(series_key)
    if not p.exists():
        raise ValueError(
            f"Données FF '{series_key}' non disponibles. "
            "Cliquez sur 'Mettre à jour les facteurs' dans l'interface pour les importer."
        )
    return pd.read_parquet(p)


def _parse_ff_csv(text: str) -> pd.DataFrame:
    """Parse the Ken French CSV format (daily only, returns in %)."""
    lines = text.splitlines()

    # Find first 8-digit date row
    first_data = None
    for i, line in enumerate(lines):
        parts = line.strip().replace(",", " ").split()
        if parts and len(parts[0]) == 8 and parts[0].isdigit():
            first_data = i
            break
    if first_data is None:
        raise ValueError("Aucune donnée journalière trouvée dans le fichier FF")

    # Find header row just before first_data (last non-empty line)
    header_idx = first_data
    for i in range(first_data - 1, max(0, first_data - 6), -1):
        if lines[i].strip():
            header_idx = i
            break

    # Find end: annual section starts with 4-digit year (after some daily data)
    last_data = first_data
    for i in range(first_data, len(lines)):
        parts = lines[i].strip().replace(",", " ").split()
        if not parts:
            continue
        if len(parts[0]) == 8 and parts[0].isdigit():
            last_data = i
        elif len(parts[0]) == 4 and parts[0].isdigit() and i > first_data + 10:
            break  # Annual section begins

    subset = "\n".join(lines[header_idx : last_data + 1])
    df = pd.read_csv(io.StringIO(subset), index_col=0, skipinitialspace=True)
    df.columns = [c.strip() for c in df.columns]
    df.index = pd.to_datetime(df.index.astype(str).str.strip(), format="%Y%m%d", errors="coerce")
    df = df[df.index.notna()].copy()
    df = df.apply(pd.to_numeric, errors="coerce") / 100.0
    return df


def get_ff_series_list() -> list[dict]:
    _hidden = {"url", "url_mom", "mom_col"}
    return [{"key": k, **{kk: vv for kk, vv in v.items() if kk not in _hidden}}
            for k, v in FF_SERIES.items()]


def get_benchmark_list() -> dict:
    """Return benchmark catalog + ISIN→benchmark map for the frontend."""
    from .amc_benchmarks import COMPOSITE_BENCHMARKS, ISIN_DEFAULT_BENCHMARK
    composite_items = [
        {
            "ticker":      c["id"],
            "label":       c["label"],
            "group":       c["category"],
            "composite":   True,
            "color":       c.get("color"),
            "description": c.get("description"),
            "components":  c["components"],
        }
        for c in COMPOSITE_BENCHMARKS
    ]
    return {
        "items":    composite_items + BENCHMARKS,
        "isin_map": ISIN_DEFAULT_BENCHMARK,
    }


# ── Benchmark download ─────────────────────────────────────────────────

def _download_raw_ticker(ticker: str, start: str, end: str) -> pd.Series:
    """Download a single yfinance ticker and return daily returns."""
    start_dt = (pd.Timestamp(start) - pd.Timedelta(days=7)).strftime("%Y-%m-%d")
    raw = yf.download(ticker, start=start_dt, end=end, progress=False, auto_adjust=True)
    if raw.empty:
        raise ValueError(f"Aucune donnée yfinance pour {ticker}")
    close = raw["Close"].squeeze()
    returns = close.pct_change().dropna()
    returns.index = pd.to_datetime(returns.index)
    return returns


def _download_benchmark(ticker: str, start: str, end: str) -> pd.Series:
    """Download benchmark returns. Handles single ETF tickers and composite IDs."""
    from .amc_benchmarks import get_composite

    composite = get_composite(ticker)
    if composite is not None:
        pieces = [
            _download_raw_ticker(c["ticker"], start, end) * c["weight"]
            for c in composite["components"]
        ]
        blended = pd.concat(pieces, axis=1).dropna().sum(axis=1)
        blended.name = ticker
        return blended

    if ticker == "CUSTOM":
        raise ValueError("Veuillez spécifier un ticker personnalisé valide.")

    return _download_raw_ticker(ticker, start, end)


# ── Main analysis ──────────────────────────────────────────────────────

def run_analysis(
    nav_records: list[dict],
    tx_records: list[dict],
    comp_records: list[dict],
    exposures: dict,
    ff_series: str,
    selected_factors: list[str],
    benchmark_ticker: str,
    rolling_window: int = 60,
) -> dict:
    """Full Fama-French analysis pipeline."""
    warnings: list[str] = []

    # ── 1. Build NAV return series ─────────────────────────────────────
    if not nav_records:
        raise ValueError("Aucune donnée NAV trouvée dans le fichier. "
                         "Vérifiez que le fichier contient un onglet avec des colonnes Date et NAV/Price.")
    nav_df = pd.DataFrame(nav_records)
    nav_df["date"] = pd.to_datetime(nav_df["date"])
    nav_df = nav_df.sort_values("date").set_index("date")
    nav_series = nav_df["nav"].astype(float)
    # Accept pre-computed 'return' column or recompute from NAV
    if "return" in nav_df.columns:
        ret_series = nav_df["return"].astype(float)
    else:
        ret_series = nav_series.pct_change()

    date_start = nav_df.index.min().strftime("%Y-%m-%d")
    date_end   = nav_df.index.max().strftime("%Y-%m-%d")
    n_nav = len(nav_series)

    if n_nav < 5:
        raise ValueError(f"Historique NAV trop court ({n_nav} observations, minimum 5).")
    if n_nav < 30:
        warnings.append(f"⚠ Historique très court ({n_nav} obs). Régression à titre indicatif uniquement — intervalles de confiance très larges.")
    elif n_nav < 60:
        warnings.append(f"⚠ Historique court ({n_nav} obs). Un minimum de 252 jours est recommandé pour des résultats fiables.")
    elif n_nav < 120:
        warnings.append(f"Historique limité ({n_nav} obs journalières). Interprétez les coefficients avec prudence.")

    # ── 2. Load FF factors from permanent store ────────────────────────
    try:
        ff_df = _load_ff_data(ff_series)
    except ValueError:
        raise
    except Exception as e:
        raise ValueError(f"Erreur lecture facteurs FF : {e}")

    info = FF_SERIES[ff_series]
    rf_col = info.get("rf_col", "RF")

    # Intersect date range with available FF data
    ff_start = ff_df.index.min().strftime("%Y-%m-%d")
    ff_end   = ff_df.index.max().strftime("%Y-%m-%d")
    overlap_start = max(date_start, ff_start)
    overlap_end   = min(date_end,   ff_end)

    if overlap_start > overlap_end:
        raise ValueError(
            f"Aucune période commune entre les données NAV ({date_start} → {date_end}) "
            f"et les facteurs FF {ff_series} ({ff_start} → {ff_end}). "
            f"Essayez une autre série FF (ex. US_3F ou EU_3F qui couvrent jusqu'en 2026)."
        )

    ff_df = ff_df.loc[overlap_start:overlap_end]

    # Validate requested factors
    available = [c for c in selected_factors if c in ff_df.columns]
    if not available:
        raise ValueError(f"Facteurs {selected_factors} non trouvés dans {ff_series}. "
                         f"Disponibles : {list(ff_df.columns)}")
    if len(available) < len(selected_factors):
        missing = [f for f in selected_factors if f not in available]
        warnings.append(f"Facteurs ignorés (absents de cette série) : {missing}")

    # ── 3. Download benchmark ──────────────────────────────────────────
    bm_returns: pd.Series | None = None
    bm_cum: list = []
    try:
        bm_returns = _download_benchmark(benchmark_ticker, overlap_start, overlap_end)
    except Exception as e:
        warnings.append(f"Benchmark {benchmark_ticker} non disponible : {e}. "
                        "Les métriques relatives seront omises.")

    # ── 4. Align series on overlap window ─────────────────────────────
    ret_overlap = ret_series.loc[overlap_start:overlap_end]
    merged = ret_overlap.rename("amc_ret").to_frame()
    merged = merged.join(ff_df[[rf_col] + available], how="inner")
    if bm_returns is not None:
        merged = merged.join(bm_returns.rename("bm_ret"), how="left")

    merged = merged.dropna(subset=["amc_ret"] + available)
    n_obs = len(merged)

    if n_obs < 5:
        raise ValueError(
            f"Seulement {n_obs} observations communes après alignement "
            f"({overlap_start} → {overlap_end}). Impossible de régresser."
        )
    if n_obs < 20:
        warnings.append(f"⚠ Seulement {n_obs} observations communes — résultats très peu fiables statistiquement.")

    merged["excess_ret"] = merged["amc_ret"] - merged[rf_col]
    if "bm_ret" in merged.columns:
        merged["bm_excess"] = merged["bm_ret"].fillna(0) - merged[rf_col]

    # ── 5. OLS regression ─────────────────────────────────────────────
    Y = merged["excess_ret"]
    X = sm.add_constant(merged[available])
    ols = sm.OLS(Y, X).fit()

    alpha_daily = float(ols.params.get("const", 0))
    alpha_ann   = alpha_daily * 252

    # Compute p-values directly from t-stats via scipy to avoid statsmodels
    # version inconsistencies where pvalues Series indexing can silently
    # return the default (1.0) instead of the actual p-value.
    df_resid = int(ols.df_resid)

    def _pval(t_val: float) -> float:
        return float(2 * _scipy_stats.t.sf(abs(t_val), df_resid))

    def _fmt_pval(p: float) -> float:
        # Never round to 0.0 — preserve the raw float for very small p-values
        # so that downstream code (PDF: `pvalue or 1`) doesn't misread them.
        return p if p < 0.0001 else round(p, 4)

    ci = ols.conf_int(alpha=0.05)
    factor_rows = []
    for f in available:
        t_val = float(ols.tvalues[f])
        factor_rows.append({
            "name":    f,
            "beta":    round(float(ols.params[f]), 4),
            "ci_low":  round(float(ci.loc[f, 0]), 4),
            "ci_high": round(float(ci.loc[f, 1]), 4),
            "tstat":   round(t_val, 3),
            "pvalue":  _fmt_pval(_pval(t_val)),
        })

    alpha_tstat_val = float(ols.tvalues.get("const", 0))
    regression = {
        "alpha_daily":    round(alpha_daily, 6),
        "alpha_ann_pct":  round(alpha_ann * 100, 2),
        "alpha_tstat":    round(alpha_tstat_val, 3),
        "alpha_pvalue":   _fmt_pval(_pval(alpha_tstat_val)),
        "alpha_ci_low":   round(float(ci.loc["const", 0]) * 252 * 100, 2) if "const" in ci.index else None,
        "alpha_ci_high":  round(float(ci.loc["const", 1]) * 252 * 100, 2) if "const" in ci.index else None,
        "r2":             round(float(ols.rsquared), 4),
        "adj_r2":         round(float(ols.rsquared_adj), 4),
        "n_obs":          int(n_obs),
        "dw":             round(float(sm.stats.stattools.durbin_watson(ols.resid)), 3),
        "factors":        factor_rows,
    }

    # ── 5b. Benchmark OLS (Jensen's alpha vs benchmark) ───────────────
    benchmark_reg: dict | None = None
    if "bm_excess" in merged.columns and merged["bm_excess"].notna().sum() > 20:
        try:
            df_bm_valid = merged[["excess_ret", "bm_excess"]].dropna()
            Y_bm = df_bm_valid["excess_ret"]
            X_bm = sm.add_constant(df_bm_valid["bm_excess"])
            ols_bm = sm.OLS(Y_bm, X_bm).fit()
            df_bm_resid = int(ols_bm.df_resid)
            def _pval_bm(t): return float(2 * _scipy_stats.t.sf(abs(t), df_bm_resid))
            alpha_bm_daily = float(ols_bm.params.get("const", 0))
            alpha_bm_ann   = alpha_bm_daily * 252
            t_alpha_bm = float(ols_bm.tvalues.get("const", 0))
            beta_bm    = float(ols_bm.params.get("bm_excess", 0))
            t_beta_bm  = float(ols_bm.tvalues.get("bm_excess", 0))
            benchmark_reg = {
                "ticker":        benchmark_ticker,
                "alpha_ann_pct": round(alpha_bm_ann * 100, 3),
                "alpha_tstat":   round(t_alpha_bm, 3),
                "alpha_pvalue":  _fmt_pval(_pval_bm(t_alpha_bm)),
                "beta":          round(beta_bm, 4),
                "beta_tstat":    round(t_beta_bm, 3),
                "beta_pvalue":   _fmt_pval(_pval_bm(t_beta_bm)),
                "r2":            round(float(ols_bm.rsquared), 4),
                "n_obs":         len(Y_bm),
            }
        except Exception as _e_bm:
            warnings.append(f"Régression benchmark {benchmark_ticker} échouée : {_e_bm}")

    # ── 6. Rolling regression ──────────────────────────────────────────
    rolling_out: list[dict] = []
    min_win = max(rolling_window, len(available) + 5)
    if n_obs >= min_win + 5:
        for end in range(min_win, n_obs + 1):
            window_df = merged.iloc[end - min_win : end]
            Yw = window_df["excess_ret"]
            Xw = sm.add_constant(window_df[available])
            try:
                res_w = sm.OLS(Yw, Xw).fit()
                row: dict = {
                    "date": merged.index[end - 1].strftime("%Y-%m-%d"),
                    "r2":   round(float(res_w.rsquared), 4),
                    "alpha_ann_pct": round(float(res_w.params.get("const", 0)) * 252 * 100, 2),
                }
                for f in available:
                    row[f] = round(float(res_w.params.get(f, 0)), 4)
                rolling_out.append(row)
            except Exception:
                pass
    else:
        warnings.append(f"Fenêtre glissante ({rolling_window}j) trop grande pour l'historique "
                        f"disponible ({n_obs} obs). Analyse rolling non disponible.")

    # ── 7. Performance metrics ─────────────────────────────────────────
    # 7a. Full NAV period (all data, regardless of FF overlap)
    full_nav   = nav_series.dropna()
    full_ret   = float(full_nav.iloc[-1] / full_nav.iloc[0] - 1)
    full_days  = len(full_nav)
    full_ann   = float((1 + full_ret) ** (252 / full_days) - 1) if full_days > 1 else 0.0
    full_vol   = float(nav_series.pct_change().dropna().std() * math.sqrt(252))
    full_dates = [d.strftime("%Y-%m-%d") for d in full_nav.index]
    full_base  = float(full_nav.iloc[0])
    full_cum   = [round(float(v) / full_base - 1, 6) for v in full_nav]
    full_peak  = 0.0
    full_dd: list[float] = []
    for r in full_cum:
        full_peak = max(full_peak, r)
        full_dd.append(round(r - full_peak, 6))

    # 7b. Overlap period (used for regression)
    ret_clean = merged["amc_ret"].dropna()
    total_ret = float((1 + ret_clean).prod() - 1)
    ann_factor = 252 / len(ret_clean)
    ann_ret  = float((1 + total_ret) ** ann_factor - 1)
    ann_vol  = float(ret_clean.std() * math.sqrt(252))
    rf_mean  = float(merged[rf_col].mean() * 252)
    sharpe   = (ann_ret - rf_mean) / ann_vol if ann_vol > 0 else 0.0

    nav_aligned = nav_series.reindex(merged.index).dropna()
    nav_base    = float(nav_aligned.iloc[0])
    cum_amc     = [round(float(v) / nav_base - 1, 6) for v in nav_aligned]
    running_peak = 0.0
    drawdown: list[float] = []
    for r in cum_amc:
        running_peak = max(running_peak, r)
        drawdown.append(round(r - running_peak, 6))
    max_dd = min(drawdown) if drawdown else 0.0

    cum_bm: list[float] = []
    if "bm_ret" in merged.columns:
        bm_cum_series = (1 + merged["bm_ret"].fillna(0)).cumprod() - 1
        cum_bm = [round(float(v), 6) for v in bm_cum_series]

    tracking_err = info_ratio = None
    if "bm_ret" in merged.columns and merged["bm_ret"].notna().sum() > 10:
        active_ret   = merged["amc_ret"] - merged["bm_ret"].fillna(merged["amc_ret"].mean())
        tracking_err = round(float(active_ret.std() * math.sqrt(252)), 4)
        active_ann   = float(active_ret.mean() * 252)
        info_ratio   = round(active_ann / tracking_err, 3) if tracking_err > 0 else None

    performance = {
        # ── Overlap period (charts + regression-consistent metrics) ──
        "dates":      [d.strftime("%Y-%m-%d") for d in nav_aligned.index],
        "nav":        [round(float(v), 4) for v in nav_aligned],
        "cum_amc":    cum_amc,
        "cum_bm":     cum_bm,
        "drawdown":   drawdown,
        "total_ret_pct":    round(total_ret * 100, 2),
        "ann_ret_pct":      round(ann_ret * 100, 2),
        "ann_vol_pct":      round(ann_vol * 100, 2),
        "sharpe":           round(sharpe, 3),
        "max_dd_pct":       round(max_dd * 100, 2),
        "tracking_err_pct": round(tracking_err * 100, 2) if tracking_err else None,
        "info_ratio":       info_ratio,
        # ── Full NAV period (true lifetime performance) ──
        "full_dates":       full_dates,
        "full_cum_amc":     full_cum,
        "full_drawdown":    full_dd,
        "full_total_ret_pct": round(full_ret * 100, 2),
        "full_ann_ret_pct":   round(full_ann * 100, 2),
        "full_ann_vol_pct":   round(full_vol * 100, 2),
        "full_nav_start":     full_dates[0] if full_dates else None,
        "full_nav_end":       full_dates[-1] if full_dates else None,
    }

    # ── 7c. Data used in regression (for "Données" tab) ──────────────
    data_used_cols = ["amc_ret", rf_col] + available
    if "bm_ret" in merged.columns:
        data_used_cols.append("bm_ret")
    data_used_df = merged[data_used_cols].copy()
    data_used_df.index.name = "date"
    data_used_df = data_used_df.reset_index()
    data_used_df["date"] = data_used_df["date"].dt.strftime("%Y-%m-%d")
    # Round for display
    for c in data_used_df.columns:
        if c != "date":
            data_used_df[c] = data_used_df[c].round(6)
    data_used_records = _safe_records(data_used_df)

    # ── 8. Activity metrics ────────────────────────────────────────────
    activity = _compute_activity(tx_records, nav_records)

    # ── 9. Composition / concentration ────────────────────────────────
    concentration = _compute_concentration(comp_records, exposures)

    # ── 10. Manager Dependency Score ──────────────────────────────────
    dep_score = _dependency_score(
        r2=float(ols.rsquared),
        alpha_tstat=float(ols.tvalues.get("const", 0)),
        turnover_rate=activity.get("turnover_rate", 0),
        hhi=concentration.get("hhi", 0.05),
    )

    return {
        "warnings":     warnings,
        "performance":  performance,
        "regression":   regression,
        "rolling":      rolling_out,
        "activity":     activity,
        "concentration": concentration,
        "dependency_score": dep_score,
        "factors_used":        available,
        "ff_series":           ff_series,
        "benchmark":           benchmark_ticker,
        "benchmark_regression": benchmark_reg,
        "data_used":           data_used_records,
        "period": {
            "nav_start":     date_start,
            "nav_end":       date_end,
            "ff_start":      ff_start,
            "ff_end":        ff_end,
            "overlap_start": overlap_start,
            "overlap_end":   overlap_end,
            "n_obs":         n_obs,
        },
    }


# ── Activity ───────────────────────────────────────────────────────────

def _compute_activity(tx_records: list[dict], nav_records: list[dict]) -> dict:
    if not tx_records:
        return {"total_trades": 0, "turnover_rate": 0}

    tx_df = pd.DataFrame(tx_records)
    # Columns present: Date, Side, Underlying Name, USD Notional Abs, etc.
    date_col = next((c for c in tx_df.columns if "Date" in str(c) and "Time" not in str(c)), None)
    notional_col = next((c for c in tx_df.columns if "Notional Abs" in str(c) or "NotionalAbs" in str(c)), None)

    total_trades = len(tx_df)
    gross_traded = float(tx_df[notional_col].sum()) if notional_col else 0.0

    # Average AUM from NAV × outstanding qty
    avg_aum = 0.0
    if nav_records:
        nav_df = pd.DataFrame(nav_records)
        if ("nav" in nav_df.columns and "Outstanding Quantity" in nav_df.columns
                and nav_df["Outstanding Quantity"].notna().any()):
            nav_df["aum"] = nav_df["nav"].astype(float) * nav_df["Outstanding Quantity"].ffill().astype(float)
            avg_aum = float(nav_df["aum"].mean())
        # else: outstanding quantity unavailable — avg_aum stays 0.0 and
        # turnover_rate is reported as unavailable rather than guessed.

    turnover_rate = gross_traded / avg_aum if avg_aum > 0 else 0.0

    # Monthly trading activity
    monthly: dict[str, dict] = {}
    if date_col and notional_col:
        tx_df["_date"] = pd.to_datetime(tx_df[date_col], errors="coerce")
        tx_df["_month"] = tx_df["_date"].dt.strftime("%Y-%m")
        tx_df["_notional"] = pd.to_numeric(tx_df[notional_col], errors="coerce").fillna(0)
        for month, grp in tx_df.groupby("_month"):
            monthly[str(month)] = {
                "trades":   int(len(grp)),
                "notional": round(float(grp["_notional"].sum()), 0),
            }

    # Unique securities
    name_col = next((c for c in tx_df.columns if "Name" in str(c) or "Underlying Name" in str(c)), None)
    unique_sec = int(tx_df[name_col].nunique()) if name_col else 0

    # Trading days
    trading_days = int(tx_df["_date"].dt.normalize().nunique()) if date_col else 0

    # Side analysis
    side_col = next((c for c in tx_df.columns if c == "Side"), None)
    buy_notional = sell_notional = 0.0
    if side_col and notional_col:
        tx_df["_notional"] = pd.to_numeric(tx_df[notional_col], errors="coerce").fillna(0)
        buy_notional  = float(tx_df.loc[tx_df[side_col] == "BUY",  "_notional"].sum())
        sell_notional = float(tx_df.loc[tx_df[side_col] == "SELL", "_notional"].sum())

    return {
        "total_trades":   total_trades,
        "trading_days":   trading_days,
        "unique_securities": unique_sec,
        "gross_traded":   round(gross_traded, 0),
        "buy_notional":   round(buy_notional, 0),
        "sell_notional":  round(sell_notional, 0),
        "avg_aum":        round(avg_aum, 0),
        "turnover_rate":  round(turnover_rate, 4),
        "turnover_ann_pct": round(
            turnover_rate / (max(len(nav_records), 1) / 252) * 100, 1
        ) if nav_records else None,
        "monthly":        monthly,
    }


# ── Concentration ──────────────────────────────────────────────────────

def _compute_concentration(comp_records: list[dict], exposures: dict) -> dict:
    if not comp_records:
        return {"n_holdings": 0, "hhi": 0, "top5_weight": 0}

    comp_df = pd.DataFrame(comp_records)
    # Priority: "Weight Per Certificat" (col I, index-price-based) > "API Weight %" > any weight col
    _weight_priority = ["Weight Per Certificat", "API Weight %"]
    weight_col = next((c for c in _weight_priority if c in comp_df.columns), None)
    if not weight_col:
        weight_col = next((c for c in comp_df.columns
                           if "weight" in str(c).lower() and "%" in str(c).lower()), None)
    name_col   = next((c for c in comp_df.columns if "Underlying Name" in str(c)), None)

    if not weight_col:
        return {"n_holdings": len(comp_df), "hhi": 0, "top5_weight": 0}

    weights = pd.to_numeric(comp_df[weight_col], errors="coerce").dropna()
    # Convert percent (>1 mean) to fraction
    if len(weights) > 0 and weights.mean() > 1:
        weights = weights / 100.0
    weights = weights[weights > 0].sort_values(ascending=False)
    # Renormalize so weights sum to exactly 1.0 (handles rounding, partial data, etc.)
    w_total = weights.sum()
    if w_total > 0:
        weights = weights / w_total
    n = len(weights)
    hhi = float((weights ** 2).sum())
    top5 = float(weights.head(5).sum())

    top_holdings = []
    if name_col:
        tmp = comp_df[[name_col, weight_col]].copy()
        tmp[weight_col] = pd.to_numeric(tmp[weight_col], errors="coerce")
        valid = tmp[weight_col].notna() & (tmp[weight_col] > 0)
        if tmp.loc[valid, weight_col].mean() > 1:
            tmp[weight_col] = tmp[weight_col] / 100.0
        # Same renormalization for display
        th_total = tmp.loc[tmp[weight_col].notna() & (tmp[weight_col] > 0), weight_col].sum()
        if th_total > 0:
            tmp[weight_col] = tmp[weight_col] / th_total
        for _, row in tmp.dropna().sort_values(weight_col, ascending=False).head(15).iterrows():
            try:
                top_holdings.append({"name": str(row[name_col]), "weight": round(float(row[weight_col]), 6)})
            except (ValueError, TypeError):
                pass

    return {
        "n_holdings":  n,
        "hhi":         round(hhi, 4),
        "top5_weight": round(top5, 4),
        "top_holdings": top_holdings,
        "sectors":     exposures.get("sectors", []),
        "countries":   exposures.get("countries", []),
        "currencies":  exposures.get("currencies", []),
    }


# ── Manager Dependency Score ───────────────────────────────────────────

def _dependency_score(r2: float, alpha_tstat: float, turnover_rate: float, hhi: float) -> dict:
    """
    0 = entièrement factoriel (gérant suit le marché)
    100 = totalement idiosyncratique (gérant crée de la valeur propre)
    """
    # Component A — Idiosyncratic risk: (1 - R²), max 40 points
    idio_score = round((1 - max(0.0, min(1.0, r2))) * 40, 1)

    # Component B — Turnover: annualized turnover mapped 0-2 → 0-30 pts
    turnover_norm = min(turnover_rate / 2.0, 1.0)
    turnover_score = round(turnover_norm * 30, 1)

    # Component C — Concentration (low HHI = diversified = less manager pick)
    # HHI ranges 0 (perfect diversification) to 1 (single stock)
    # We interpret high HHI as more manager-specific → more dependent
    hhi_score = round(min(hhi / 0.15, 1.0) * 20, 1)

    # Component D — Alpha significance (abs t-stat mapped 0-3 → 0-10 pts)
    alpha_score = round(min(abs(alpha_tstat) / 3.0, 1.0) * 10, 1)

    total = round(idio_score + turnover_score + hhi_score + alpha_score, 1)

    if total >= 70:
        interpretation = "Très dépendant du gérant — performance essentiellement idiosyncratique"
        level = "high"
    elif total >= 45:
        interpretation = "Modérément dépendant — mélange gestion active et exposition factorielle"
        level = "medium"
    else:
        interpretation = "Faiblement dépendant — performance principalement factorielle"
        level = "low"

    return {
        "total": total,
        "score": round(total / 10, 1),
        "level": level,
        "interpretation": interpretation,
        "components": {
            "idiosyncratic": {"score": idio_score, "value": round(1 - r2, 4), "label": f"Risque idiosyncratique (1-R²)"},
            "turnover":      {"score": turnover_score, "value": round(turnover_rate, 4), "label": "Taux de rotation"},
            "concentration": {"score": hhi_score, "value": round(hhi, 4), "label": "Concentration (HHI)"},
            "alpha_signif":  {"score": alpha_score, "value": round(alpha_tstat, 3), "label": "Significativité alpha (|t|)"},
        },
    }
