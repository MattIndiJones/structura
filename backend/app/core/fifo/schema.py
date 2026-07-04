"""FIFO data structures — pure dataclasses, no I/O."""
from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Order:
    id: str
    date: datetime.date
    isin: str
    name: str
    qty: float          # signed: positive = BUY, negative = SELL
    price_local: float  # price per unit in local currency (share price OR cert-unit price)
    price_ccy: str      # local currency code
    fx: float           # local → prod_ccy rate at execution
    price_prod: float   # price_local × fx


@dataclass
class Lot:
    order_id: str
    date: datetime.date
    isin: str
    name: str
    qty: float          # always positive — remaining open quantity
    price_prod: float   # cost per unit in prod_ccy
    source: str = "carnet"   # "carnet" | "synthetic_t0"
    price_local: float = 0.0  # cost per unit in local currency (for FX decomposition)
    fx: float = 1.0           # local → prod_ccy rate at entry
    ccy: str = ""             # local currency code


@dataclass
class RoundTrip:
    isin: str
    name: str
    buy_date: datetime.date
    sell_date: datetime.date
    qty: float
    buy_price_prod: float
    sell_price_prod: float
    pnl_prod: float
    buy_source: str = "carnet"   # "carnet" | "synthetic_t0"
    # Raw price/FX fields — carried for FX attribution in the AMC adapter
    buy_price_local: float = 0.0
    buy_fx: float = 1.0
    sell_price_local: float = 0.0
    sell_fx: float = 1.0
    ccy: str = ""  # local currency code


@dataclass
class OpenPosition:
    isin: str
    name: str
    open_qty: float
    avg_cost_prod: float         # weighted average cost per unit in prod_ccy
    cost_prod: float             # total cost basis in prod_ccy
    mark_prod: Optional[float]   # current mark per unit in prod_ccy (None if unavailable)
    unreal_pnl_prod: Optional[float]   # None when mark unavailable
    lots: list[Lot] = field(default_factory=list)
    ccy: str = ""  # local currency code


@dataclass
class SyntheticInjection:
    """One synthetic T0 BUY injected to cover an excess SELL."""
    isin: str
    name: str
    excess_qty: float
    t0_date: datetime.date
    price_prod: float
    price_local: Optional[float]
    price_ccy: str
    fx: float
    source: str     # "yfinance" | "scaling_factor" | "order_proxy" | "termsheet" | "unavailable"
    injected: bool  # False when excess detected but price unavailable


@dataclass
class ReconResult:
    open_positions: list[OpenPosition]
    round_trips: list[RoundTrip]
    synthetic_report: list[SyntheticInjection]
    earliest_lots: dict[str, "Lot"]  # {isin: earliest lot seen — includes closed positions}
    qty_mode: str       # "shares" | "cert_units"
    recon_mode: str     # "strict" | "t0_synthetic"
    prod_ccy: str
    as_of: datetime.date
    total_realized: float
    total_latent: Optional[float]
    total_pnl: Optional[float]
