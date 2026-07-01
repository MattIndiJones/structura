from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any


class UnderlyingParams(BaseModel):
    name: str = "Underlying"
    ticker: str = ""
    ccy: str = "EUR"
    sigma: float = 0.20
    q: float = 0.02
    sigma_fx: float = 0.0
    rho_sfx: float = 0.0
    ccyh: float = 0.0
    # Heston
    v0: float = 0.04
    kappa: float = 2.0
    theta: float = 0.04
    xi: float = 0.35
    rho_h: float = -0.70
    rho_rS: float = 0.0
    # SABR
    alpha: float = 0.20
    beta: float = 0.50
    rho: float = -0.30
    nu: float = 0.40
    # Dupire local vol
    skew: float = 0.0
    curvature: float = 0.0


class PricingRequest(BaseModel):
    script: str
    underlyings: List[UnderlyingParams]
    corr_matrix: List[List[float]]
    r: float = 0.03
    T: float = 3.0
    N: int = Field(default=20000, ge=1000, le=200000)
    seed: int = 42
    model: str = "constant"
    antithetic: bool = True
    user_params: Dict[str, Any] = {}
    compute_greeks: bool = False
    selected_greeks: List[str] = ["delta", "gamma", "vega", "theta", "rho"]
    yield_curve: List[List[float]] = []
    sigma_r: float = Field(default=0.0, ge=0.0, le=0.10)
    a_r: float = Field(default=0.0, ge=0.0, le=2.0)
    # CONSTAT values, keyed by name — see core/payscript/parser.resolve_constats.
    # Empty dict is a no-op (the common/simple-mode case: no AT<ConstatName>:).
    constats: Dict[str, Any] = {}


class PricingResponse(BaseModel):
    price: float
    ic95: List[float]
    median: float
    var5: float
    prob_gt100: float
    payoffs: List[float]
    flux_table: Dict[str, Any]
    greeks: Dict[str, Any]
    elapsed_ms: float
    n_paths: int
    n_eff: int
    status: str = "ok"
    errors: Optional[str] = None
    # Actual simulation horizon used — may exceed the requested T if the
    # script's (possibly CONSTAT-resolved) event dates run past it.
    # See core/payscript/parser.effective_T_max.
    t_max_effective: float = 0.0
    fugit: Optional[float] = None


class ParseRequest(BaseModel):
    script: str


class ParseResponse(BaseModel):
    ok: bool
    params: List[Dict[str, Any]]
    constats: List[Dict[str, Any]] = []
    events_count: int
    has_stop: bool = False
    errors: Optional[str] = None


# ── Analytics request/response models ──────────────────────────────

class AnalysisBase(BaseModel):
    """Shared fields for profile / paths / proba / backtest / mtf requests."""
    script: str
    underlyings: List[UnderlyingParams]
    corr_matrix: List[List[float]]
    r: float = 0.03
    T: float = 3.0
    seed: int = 42
    model: str = "constant"
    user_params: Dict[str, Any] = {}
    yield_curve: List[List[float]] = []
    constats: Dict[str, Any] = {}


class ProfileRequest(AnalysisBase):
    pass


class PathsRequest(AnalysisBase):
    N_stat: int = Field(default=500, ge=50, le=5000)
    N_display: int = Field(default=50, ge=10, le=200)


class ProbaRequest(AnalysisBase):
    N: int = Field(default=5000, ge=1000, le=20000)


class BacktestRequest(AnalysisBase):
    start_date: str = "2010-01-01"
    end_date: Optional[str] = None
    freq: int = Field(default=21, ge=5, le=252)
    invest_pct: float = Field(default=100.0, gt=0, le=200)
    rf_rate: float = 2.0


class MtfRequest(AnalysisBase):
    """Mark-to-Future — nested Monte Carlo. main_price is the t=0 fair price
    (% of notional, from a prior /price call), used as the P(MTM >= P0) threshold."""
    main_price: float
    n_outer: int = Field(default=200, ge=20, le=2000)
    n_inner: int = Field(default=500, ge=50, le=5000)
    n_dates: int = Field(default=5, ge=2, le=12)


class SolverRequest(AnalysisBase):
    """Solve for the script PARAM value that hits a target price (bisection).
    target_price/lo/hi are in the PARAM's stored units (fraction for % params)."""
    param_name: str
    target_price: float
    lo: float
    hi: float
    N: int = Field(default=8000, ge=1000, le=50000)
    tol: float = Field(default=1e-4, gt=0, le=0.01)
    max_iter: int = Field(default=40, ge=5, le=100)


class GridRequest(AnalysisBase):
    """2D price heatmap over two script PARAM ranges (stored units)."""
    param_x: str
    x_min: float
    x_max: float
    x_steps: int = Field(default=9, ge=2, le=15)
    param_y: str
    y_min: float
    y_max: float
    y_steps: int = Field(default=9, ge=2, le=15)
    N: int = Field(default=4000, ge=500, le=20000)


class ScenarioRequest(AnalysisBase):
    """Stress grid — price under combined spot x vol shocks (market data, not
    script PARAMs). spot_shocks are multiplicative fractions (e.g. -0.10 = -10%
    spot), vol_shocks are additive fractions (e.g. 0.05 = +5pp vol)."""
    spot_shocks: List[float] = Field(
        default=[-0.30, -0.20, -0.10, -0.05, 0.0, 0.05, 0.10, 0.20, 0.30],
        min_length=1, max_length=15)
    vol_shocks: List[float] = Field(
        default=[0.10, 0.05, 0.0, -0.05, -0.10],
        min_length=1, max_length=15)
    N: int = Field(default=2000, ge=300, le=20000)


class ScheduleRequest(BaseModel):
    """CONSTAT()/CONSTAT()() calendar generation — "expert mode", independent
    of any script. Dates are ISO strings (YYYY-MM-DD); frequency/sub_frequency
    are tenor strings (e.g. "3M", "1W", "1Y", "1D")."""
    start_date: str
    end_date: str
    roll_date: str
    frequency: str
    stub: str = Field(default="short_last",
                       pattern="^(short_first|short_last|long_first|long_last)$")
    sub_frequency: Optional[str] = None
