"""API endpoints for the underlying price store."""
from __future__ import annotations

import io
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..db.models import User
from ..api.auth import get_current_user, get_current_admin
from .amc_access import study_folder, study_slot
from ..core.amc_prices import (
    price_status, fetch_prices, upload_prices, delete_prices, load_prices, _slug,
    resolve_ticker, spot_on_date,
)
from ..core.amc_attribution import compute_attribution

router = APIRouter(prefix="/api/amc/prices", tags=["amc-prices"])


# ── Status ─────────────────────────────────────────────────────────────

@router.get("/status")
def get_price_status(
    current: Annotated[User, Depends(get_current_user)],
):
    """List all stored price series."""
    return price_status()


@router.get("/spot")
def get_spot_on_date(
    key: str, date: str,
    current: Annotated[User, Depends(get_current_user)],
):
    """Last known close on or before *date* for a stored key — read-only,
    no Yahoo call (use POST /fetch first if the series isn't stored yet)."""
    result = spot_on_date(key, date)
    if result is None:
        raise HTTPException(404, f"Pas de données disponibles pour '{key}' à cette date.")
    return result


@router.post("/status-for-study")
def get_price_status_for_study(
    payload: dict,
    current: Annotated[User, Depends(get_current_user)],
):
    """List price series status for a specific study's underlyings."""
    underlyings = payload.get("underlyings", [])
    return price_status(underlyings)


# ── Resolve tickers from ISIN ─────────────────────────────────────────

class ResolveItem(BaseModel):
    key: str
    isin: str = ""
    name: str = ""


@router.post("/resolve-tickers")
def resolve_tickers_endpoint(
    payload: List[ResolveItem],
    current: Annotated[User, Depends(get_current_user)],
):
    """Batch-resolve Yahoo Finance tickers from ISIN codes (or names as fallback)."""
    results = []
    for item in payload:
        query = item.isin.strip() or item.name.strip()
        ticker, confidence = resolve_ticker(query)
        results.append({
            "key": item.key,
            "isin": item.isin,
            "name": item.name,
            "ticker": ticker,
            "confidence": confidence,
        })
    return results


# ── Fetch from Yahoo Finance ───────────────────────────────────────────

class FetchRequest(BaseModel):
    key: str           # ISIN or name slug
    ticker: str        # Yahoo Finance ticker
    start: Optional[str] = None
    end:   Optional[str] = None


@router.post("/fetch")
def fetch_underlying(
    req: FetchRequest,
    current: Annotated[User, Depends(get_current_admin)],
):
    """Download price history from Yahoo Finance and persist."""
    try:
        return fetch_prices(req.key, req.ticker, req.start, req.end)
    except ValueError as e:
        raise HTTPException(422, str(e))
    except Exception as e:
        raise HTTPException(500, f"Erreur Yahoo Finance : {e}")


# ── Manual upload ──────────────────────────────────────────────────────

@router.post("/upload")
async def upload_underlying(
    key:    Annotated[str, Form()],
    file:   Annotated[UploadFile, File()],
    ticker: Annotated[str, Form()] = "",
    current: Annotated[User, Depends(get_current_admin)] = None,
):
    """Upload a price time series from Excel (.xlsx) or JSON."""
    content = await file.read(20 * 1024 * 1024 + 1)
    if len(content) > 20 * 1024 * 1024:
        raise HTTPException(413, "Fichier trop volumineux (20 Mo maximum).")
    try:
        return upload_prices(key, content, file.filename or "upload", ticker)
    except ValueError as e:
        raise HTTPException(422, str(e))
    except Exception as e:
        raise HTTPException(500, f"Erreur import : {e}")


# ── Delete ─────────────────────────────────────────────────────────────

@router.delete("/{key}")
def delete_underlying(
    key: str,
    current: Annotated[User, Depends(get_current_admin)],
):
    delete_prices(key)
    return {"ok": True}


# ── VAG computation ───────────────────────────────────────────────────

# ── Attribution Phase 2 ───────────────────────────────────────────────

class AttributionRequest(BaseModel):
    folder: str
    study_result: dict
    amc_currency: str = "CHF"


def _secondary_market_context(folder, study):
    from ..core.amc_market_bundle import market_bundle
    from ..core.amc_controls import input_provenance
    manifest = study.get("manifest") or {}
    files = manifest.get("files") or {}
    if folder and study.get("provenance", {}).get("input_hashes"):
        current = input_provenance(folder, files, manifest)
        if current["input_hashes"] != study["provenance"]["input_hashes"]:
            raise ValueError("Sources modifiées depuis l’étude : relancez le calcul complet.")
    if files.get("market_data") and not folder:
        raise ValueError("Dossier de marché de l’étude requis")
    return market_bundle(folder, files.get("market_data", ""))


@router.post("/attribution")
def compute_attribution_endpoint(
    req: AttributionRequest,
    current: Annotated[User, Depends(get_current_user)],
):
    """Compute retrospective price contributions using the study market sources."""
    req.folder = study_folder(req.folder, current)
    try:
        with _secondary_market_context(req.folder, req.study_result):
            result = compute_attribution(req.folder, req.study_result, amc_currency=req.amc_currency)
    except ValueError as e:
        raise HTTPException(422, str(e))
    except Exception as e:
        raise HTTPException(500, f"Erreur attribution : {e}")
    if "error" in result:
        raise HTTPException(422, result["error"])
    return result


# ── Block G — Brinson Attribution ─────────────────────────────────────

class BrinsonRequest(BaseModel):
    study_result:     dict
    price_keys:       List[str]
    amc_currency:     str = "CHF"
    folder:           str = ""
    benchmark_ticker: str = "ACWI"


@router.post("/brinson")
def compute_brinson_endpoint(
    req: BrinsonRequest,
    current: Annotated[User, Depends(get_current_user)],
):
    """Compute Brinson-Fachler attribution (Block G)."""
    from ..core.amc_brinson import (
        compute_brinson, load_price_cache, save_price_cache,
    )

    if req.folder:
        req.folder = study_folder(req.folder, current)
    if len(req.price_keys) > 500:
        raise HTTPException(422, "Maximum 500 séries par étude.")
    from ..core.amc_confidence import attach_brinson
    try:
        with _secondary_market_context(req.folder, req.study_result) as bundle:
            prices = {}
            if bundle is not None:
                prices = bundle.prices
                cached_sectors = bundle.sectors
            else:
                for key in req.price_keys:
                    try:
                        prices[key] = load_prices(key)
                    except ValueError:
                        pass
                cache = load_price_cache(req.folder) if req.folder else None
                cached_sectors = (cache or {}).get("sector_map") or None
            study = req.study_result
            reference = study.get("reference_portfolio")
            if reference:
                start = reference["start_date"]
                study = {**study, "termsheet_basket": reference["positions"],
                         "meta": {**study["meta"], "nav_start_date": start,
                                  "nav_start_value": next(float(r["nav"]) for r in study["source_nav"] if str(r["date"])[:10] == start)}}
            result = compute_brinson(study, prices,
                benchmark_ticker=req.benchmark_ticker, amc_currency=req.amc_currency,
                folder=req.folder, cached_sectors=cached_sectors)
            if result.get("available") and req.folder and bundle is None:
                save_price_cache(req.folder, req.price_keys, req.amc_currency,
                                 req.benchmark_ticker, result.get("sector_map"))
    except ValueError as exc:
        raise HTTPException(422, str(exc))

    if not result.get("available") and "error" in result:
        raise HTTPException(422, result["error"])
    return {**result, "study_result": attach_brinson(req.study_result, result)}
