"""FIFO order-book reconstruction module.

Independent from the legacy amc_orderbook.  Supports two quantity modes:
  - "shares"     : executedQuantity = real share count, mark from Yahoo Finance
  - "cert_units" : executedQuantity = cert-unit count, mark from stock price × scaling factor
"""
from .engine import reconstruct
from .loader import load_orders
from .schema import Order, Lot, RoundTrip, OpenPosition, ReconResult

__all__ = ["reconstruct", "load_orders", "Order", "Lot", "RoundTrip", "OpenPosition", "ReconResult"]
