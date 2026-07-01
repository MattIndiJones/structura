"""Market data API endpoints — Yahoo Finance vol, dividends, correlations, historical prices."""
from typing import Optional
from fastapi import APIRouter
from ..services.market_data import load_hist_vol, load_hist_prices

router = APIRouter(prefix="/api/finance", tags=["market-data"])


@router.get("/hist_vol")
async def hist_vol_endpoint(tickers: str, period: str = "1y"):
    """Load realized vol, dividend yield, and correlation matrix for the given tickers."""
    tks = [t.strip().upper() for t in tickers.split(",") if t.strip()]
    if not tks:
        return {"error": "Aucun ticker fourni"}
    return load_hist_vol(tks, period)


@router.get("/hist_prices")
async def hist_prices_endpoint(
    tickers: str, start: str = "2010-01-01", end: Optional[str] = None
):
    """Load daily close prices for backtest replay."""
    tks = [t.strip().upper() for t in tickers.split(",") if t.strip()]
    if not tks:
        return {"error": "Aucun ticker fourni"}
    return load_hist_prices(tks, start, end)
