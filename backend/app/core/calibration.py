"""Realized-market calibration from historical closes.

Feeds the residual-MtM "marché actuel" mode (api/deals.py:deal_mtm): instead
of the σ/corr frozen in the booking snapshot, estimate them from the recent
daily history — the same price series already fetched for the lifecycle
replay, so no extra market-data call is ever needed.

Conventions (deliberate, keep in sync with the engine):
- σ_i = sqrt(252 · mean(r²)) on daily log-returns — a quadratic-variation
  (RMS, non-centered) estimator, the SAME convention as the engine's REALVOL
  (engine.py:_eval_paths): internally consistent, and the daily drift term it
  ignores is negligible at this horizon.
- Correlations: Pearson on the same common-day return matrix — PSD by
  construction; a tiny eigenvalue clip (mini-Higham) guards against numerical
  degeneracy (identical series) so the engine's cholesky() never fails.
- Window: the last `window_days` returns (default 252 ≈ 1 year) — long enough
  to be statistically stable, short enough to reflect the current vol regime.
"""
from __future__ import annotations
import math
import numpy as np

MIN_RETURNS = 20


def realized_market(prices: dict, tickers: list[str], window_days: int = 252) -> dict:
    """Annualized realized vols and correlation matrix from daily closes.

    prices: {ticker: [close, ...]} — aligned series (same trading-day grid),
    as returned by load_hist_prices. Returns are computed only on days where
    EVERY ticker has a positive price, so the correlation estimate uses a
    complete common sample. Raises ValueError on unusable data (missing
    ticker, < MIN_RETURNS common returns, flat series).

    -> {"sigma": {ticker: frac}, "corr": [[...]], "n_returns": int}
    """
    cols = []
    for tk in tickers:
        px = [float(p) if p else 0.0 for p in prices.get(tk, [])]
        if not px:
            raise ValueError(f"Aucun historique de prix pour {tk}")
        cols.append(px)

    n_days = min(len(c) for c in cols)
    common = [i for i in range(n_days) if all(c[i] > 0 for c in cols)]
    if len(common) < MIN_RETURNS + 1:
        raise ValueError(
            f"Historique commun insuffisant pour la calibration réalisée : "
            f"{max(0, len(common) - 1)} rendements (minimum {MIN_RETURNS})"
        )

    rets = np.array([
        [math.log(c[common[k]] / c[common[k - 1]]) for k in range(1, len(common))]
        for c in cols
    ])                                   # (n_tickers, n_returns)
    rets = rets[:, -window_days:]
    m = rets.shape[1]

    sigma: dict[str, float] = {}
    for tk, r in zip(tickers, rets):
        s = math.sqrt(252.0 * float(np.mean(r ** 2)))
        if s < 1e-6:
            raise ValueError(f"Série plate pour {tk} — vol réalisée nulle, calibration impossible")
        sigma[tk] = s

    n = len(tickers)
    if n == 1:
        corr = [[1.0]]
    else:
        C = np.corrcoef(rets)
        C = np.nan_to_num(C, nan=0.0)
        np.fill_diagonal(C, 1.0)
        # Mini-Higham: clip eigenvalues, rebuild, renormalize the diagonal —
        # keeps the matrix strictly PSD even for degenerate (identical) series.
        w, V = np.linalg.eigh((C + C.T) / 2)
        C = V @ np.diag(np.clip(w, 1e-10, None)) @ V.T
        d = np.sqrt(np.clip(np.diag(C), 1e-12, None))
        C = C / np.outer(d, d)
        np.fill_diagonal(C, 1.0)
        corr = [[float(min(1.0, max(-1.0, C[i, j]))) for j in range(n)] for i in range(n)]

    return {"sigma": sigma, "corr": corr, "n_returns": m}
