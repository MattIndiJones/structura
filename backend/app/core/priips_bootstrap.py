"""Historical bootstrap simulation of PRIIPs Category 3 (Annex II points 19-22).

Every simulated trading day draws ONE historical date, with replacement, and
applies that date's log-return to every underlying at once (point 22(b)): the
joint behaviour of the basket is the observed one, without a correlation
matrix. The simulator plugs into the PayScript engine through
`run_mc(path_simulator=...)`, so the payoff is evaluated exactly as in pricing.

Three regimes of expected return:

- "risk_neutral" — Annex II point 22(c), for the market risk measure: each
  contract's summed return is corrected by + E[risk-neutral return]
  - E[measured return] - 0.5 sigma^2 N. The risk-neutral term is the forward
  rate of the curve minus the dividend yield, over each step.
- "historical"   — Annex IV point 25, for the performance scenarios: the
  expected return is the one observed over the period, without correction.
- "stress"       — Annex IV point 26: returns rescaled by stressed volatility
  over measured volatility, then recentred so that the expected return is
  -0.5 sigma_S^2 N.

Not implemented, and refused rather than ignored by the caller: the quanto
term of point 22(c) (strike currency different from the asset currency) and
curve simulation by principal components (point 23).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from .payscript.time_grid import durations, times

TRADING_DAYS = 252
MIN_HISTORY_YEARS = 2.0        # Annex II point 6: at least 2 years of daily prices
LOOKBACK_YEARS = 5             # Annex II point 22(a): the past 5 years
BLOCK_PATHS = 2_000
REGIMES = ("risk_neutral", "historical", "stress")


@dataclass
class HistoricalReturns:
    """Daily log-returns on the dates observed for EVERY underlying."""
    returns: np.ndarray                 # (H, n)
    first_date: str
    last_date: str
    tickers: list[str]
    dropped_dates: int = 0
    mean: np.ndarray = field(init=False)
    variance: np.ndarray = field(init=False)

    def __post_init__(self):
        if self.returns.ndim != 2 or self.returns.shape[0] < 2:
            raise ValueError("Historique de rendements insuffisant pour le bootstrap.")
        self.mean = self.returns.mean(axis=0)
        self.variance = self.returns.var(axis=0, ddof=0)

    @property
    def observations(self) -> int:
        return int(self.returns.shape[0])

    def metadata(self) -> dict:
        return {"method": "historical_bootstrap", "frequency": "daily",
                "first_date": self.first_date, "last_date": self.last_date,
                "observations": self.observations, "tickers": list(self.tickers),
                "dates_dropped_not_common": self.dropped_dates,
                "annualised_volatility": [round(float(math.sqrt(v * TRADING_DAYS)), 6)
                                          for v in self.variance]}


def historical_returns(dates: list[str], prices: dict[str, list], tickers: list[str]) -> HistoricalReturns:
    """Annex II point 22(a): log of each close over the previous one, on the
    dates every underlying traded. A date missing for one underlying is
    dropped for all, so a drawn date always carries one return per asset."""
    if not tickers:
        raise ValueError("Aucun sous-jacent pour le bootstrap.")
    rows = []
    for index, day in enumerate(dates):
        values = [prices.get(t, [None] * len(dates))[index] for t in tickers]
        if all(v is not None and np.isfinite(v) and v > 0 for v in values):
            rows.append((day, values))
    dropped = len(dates) - len(rows)
    if len(rows) < 2:
        raise ValueError("Aucune séance commune à tous les sous-jacents.")
    levels = np.array([v for _d, v in rows], dtype=float)
    returns = np.diff(np.log(levels), axis=0)
    first, last = rows[0][0], rows[-1][0]
    span_years = (np.datetime64(last) - np.datetime64(first)).astype(int) / 365.25
    if span_years < MIN_HISTORY_YEARS - 1e-9:
        raise ValueError(
            f"Historique commun de {span_years:.1f} an(s) : la Catégorie 3 exige au moins "
            f"{MIN_HISTORY_YEARS:g} ans de cours quotidiens (annexe II, point 6).")
    return HistoricalReturns(returns, str(first), str(last), list(tickers), dropped)


def stressed_volatility(returns: np.ndarray, holding_years: float) -> float:
    """Annex IV point 18 (used by point 26(a)) for one asset's daily returns.

    Rolling sub-intervals of w observations (21 for one year or less, 63
    beyond, daily data); volatility of each window around its own mean; the
    99th percentile of those volatilities for a one-year holding period, the
    95th otherwise."""
    w = 21 if holding_years <= 1.0 + 1e-9 else 63
    values = np.asarray(returns, dtype=float)
    if values.size < w:
        raise ValueError("Historique trop court pour la volatilité stressée.")
    windows = np.lib.stride_tricks.sliding_window_view(values, w)
    vols = np.sqrt(((windows - windows.mean(axis=1, keepdims=True)) ** 2).sum(axis=1) / w)
    percentile = 99 if holding_years <= 1.0 + 1e-9 else 95
    return float(np.percentile(vols, percentile))


class BootstrapSimulator:
    """Callable `(ts, dt, n, N, rng) -> S` for `run_mc(path_simulator=...)`.

    S has the engine's shape (ts + 1, n, N), starts at 1 and lands exactly on
    the engine's contractual time axis: each grid step takes the trading days
    between its two dates (252 a year), each day one drawn historical date."""

    def __init__(self, history: HistoricalReturns, regime: str, *,
                 discount_factor=None, dividend_yields=None, stress_years: float | None = None):
        if regime not in REGIMES:
            raise ValueError(f"Régime de bootstrap inconnu : {regime!r}.")
        self.history = history
        self.regime = regime
        n = history.returns.shape[1]
        daily = history.returns.copy()
        if regime == "risk_neutral":
            # Point 22(c): - E[measured] - 0.5 sigma^2 per day; the risk-neutral
            # expectation is added per grid step from the curve (see __call__).
            daily = daily - history.mean - 0.5 * history.variance
        elif regime == "stress":
            years = stress_years if stress_years is not None else 1.0
            sigma = np.sqrt(history.variance)
            sigma_s = np.array([stressed_volatility(history.returns[:, i], years) for i in range(n)])
            scaled = daily * np.where(sigma > 0, sigma_s / sigma, 1.0)          # point 26(b)
            daily = scaled - scaled.mean(axis=0) - 0.5 * sigma_s ** 2         # point 26(d)
            self.stressed_volatility = sigma_s
        self.daily = daily
        self.discount_factor = discount_factor
        self.dividend_yields = np.zeros(n) if dividend_yields is None else np.asarray(dividend_yields, float)
        if regime == "risk_neutral" and discount_factor is None:
            raise ValueError("Le régime risque-neutre exige une courbe d'actualisation.")

    def __call__(self, ts: int, dt, n: int, N: int, rng) -> np.ndarray:
        if n != self.daily.shape[1]:
            raise ValueError("Le bootstrap ne couvre pas tous les sous-jacents du produit.")
        grid = times(dt, ts)
        day_index = np.rint(grid * TRADING_DAYS).astype(np.int64)      # cumulative trading days
        total_days = int(day_index[-1])
        drift = np.zeros((ts + 1, n))
        if self.regime == "risk_neutral":
            for i in range(n):
                drift[:, i] = [-math.log(self.discount_factor(t)) - self.dividend_yields[i] * t
                               for t in grid]
        S = np.empty((ts + 1, n, N), dtype=np.float64)
        H = self.daily.shape[0]
        for start in range(0, N, BLOCK_PATHS):
            size = min(BLOCK_PATHS, N - start)
            drawn = rng.integers(0, H, size=(total_days, size), dtype=np.int64)
            for i in range(n):
                cumulative = np.zeros((total_days + 1, size))
                if total_days:
                    np.cumsum(self.daily[drawn, i], axis=0, out=cumulative[1:])
                S[:, i, start:start + size] = np.exp(cumulative[day_index] + drift[:, i, None])
        return S


def outer_axis_times(dt, ts) -> list[float]:
    """Exact time axis to hand to run_mark_to_future(outer_times=...)."""
    return times(durations(dt, ts), ts).tolist()
