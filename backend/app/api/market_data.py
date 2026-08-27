"""Market data API endpoints — Yahoo Finance vol, dividends, correlations, historical prices."""
from typing import Annotated, Optional
from fastapi import APIRouter, Depends
from sqlmodel import Session, select
from ..db.database import get_session
from ..db.models import Underlying, User
from ..services.market_data import dividend_profile, load_hist_vol, load_hist_prices
from .auth import get_current_user

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


@router.get("/underlyings")
def list_underlyings_endpoint(
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    """Le catalogue de sous-jacents, groupé et trié alphabétiquement.

    Sert les listes déroulantes du Pricer et du module RFQ. Seuls les titres
    actifs sortent : désactiver vaut retrait des menus sans perdre l'historique
    des produits qui s'y réfèrent.
    """
    rows = session.exec(
        select(Underlying)
        .where(Underlying.active == True)   # noqa: E712 — SQLModel veut la comparaison
        .order_by(Underlying.group_name, Underlying.label)
    ).all()
    groupes: dict[str, list] = {}
    for u in rows:
        groupes.setdefault(u.group_name, []).append(
            {"ticker": u.ticker, "label": u.label, "ccy": u.ccy})
    return [{"group": g, "items": groupes[g]} for g in sorted(groupes)]


@router.get("/dividends")
def dividend_profile_endpoint(
    ticker: str,
    current: Annotated[User, Depends(get_current_user)],
    asof: Optional[str] = None,
    window_years: float = 1.0,
):
    """Rendement de dividende d'un titre, à une date quelconque.

    Le paramètre asof permet de valoriser un produit en cours de vie avec le
    dividende qui avait cours à cette date-là — ce que le champ instantané de
    Yahoo, qui ne connaît qu'aujourd'hui, ne sait pas faire.
    """
    return dividend_profile(ticker, asof, window_years)
