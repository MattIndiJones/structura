"""Realized-market calibration (core/calibration.py) — the "marché actuel"
mode of the residual deal MtM. Pure function, synthetic series, no network."""
import math

import numpy as np
import pytest

from backend.app.core.calibration import realized_market
from backend.app.core.payscript.engine import cholesky


def _series_const_returns(n_days: int, x: float, start: float = 100.0) -> list[float]:
    """Price series whose daily log-returns alternate exactly +x / -x."""
    px = [start]
    for k in range(n_days - 1):
        px.append(px[-1] * math.exp(x if k % 2 == 0 else -x))
    return px


def test_realized_sigma_exact():
    """Alternating ±x log-returns → RMS estimator gives exactly sqrt(252·x²),
    whatever the sign pattern (non-centered, quadratic-variation convention)."""
    x = 0.0126   # ≈ 20% annualized
    rm = realized_market({"TK1": _series_const_returns(300, x)}, ["TK1"])
    assert rm["sigma"]["TK1"] == pytest.approx(math.sqrt(252 * x * x), rel=1e-9)
    assert rm["corr"] == [[1.0]]
    assert rm["n_returns"] == 252   # capped at the default window


def test_realized_corr_psd_and_bounds():
    """Three correlated synthetic series: diagonal 1, |ρ| ≤ 1, PSD, and the
    engine's cholesky() accepts the matrix as-is."""
    rng = np.random.default_rng(7)
    z = rng.standard_normal((3, 400)) * 0.01
    r1, r2, r3 = z[0], 0.8 * z[0] + 0.6 * z[1], -0.5 * z[0] + 0.9 * z[2]
    prices = {}
    for name, r in [("A", r1), ("B", r2), ("C", r3)]:
        prices[name] = list(100.0 * np.exp(np.concatenate([[0.0], np.cumsum(r)])))
    rm = realized_market(prices, ["A", "B", "C"])
    C = np.array(rm["corr"])
    assert np.allclose(np.diag(C), 1.0)
    assert np.all(np.abs(C) <= 1.0 + 1e-12)
    assert np.linalg.eigvalsh(C).min() >= -1e-10
    cholesky(rm["corr"], 3)   # must not raise


def test_realized_corr_degenerate_regularized():
    """Two identical series (ρ = 1, singular matrix) : the eigenvalue clip
    keeps the matrix usable by the engine's cholesky()."""
    px = _series_const_returns(300, 0.01)
    rm = realized_market({"A": px, "B": list(px)}, ["A", "B"])
    assert rm["corr"][0][1] == pytest.approx(1.0, abs=1e-6)
    cholesky(rm["corr"], 2)   # must not raise


def test_realized_window_truncates_and_minimum():
    """Short history: uses what is available; below the minimum common-return
    count, or on a flat series, raises a clear ValueError."""
    rm = realized_market({"TK1": _series_const_returns(101, 0.01)}, ["TK1"],
                         window_days=252)
    assert rm["n_returns"] == 100
    with pytest.raises(ValueError, match="insuffisant"):
        realized_market({"TK1": _series_const_returns(10, 0.01)}, ["TK1"])
    with pytest.raises(ValueError, match="plate"):
        realized_market({"TK1": [100.0] * 300}, ["TK1"])
    with pytest.raises(ValueError, match="Aucun historique"):
        realized_market({"TK1": _series_const_returns(300, 0.01)}, ["TK1", "TK2"])
