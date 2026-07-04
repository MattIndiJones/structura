"""FIFO order-book reconstruction — REST endpoints.

Thin HTTP layer over core/fifo/pipeline.py — the same pipeline the AMC study
uses (amc_study.py), so both entry points share one implementation and can't
drift out of sync again.
"""
from __future__ import annotations

import dataclasses
import datetime
import os
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..api.auth import get_current_user
from ..db.models import User
from ..core.fifo.loader import load_orders
from ..core.fifo.engine import reconstruct
from ..core.fifo.marks import (
    fetch_t0_prices_from_lots,
    compute_scaling_factors_from_positions,
)
from ..core.fifo.pipeline import run_fifo_recon, detect_order_files

router = APIRouter(prefix="/api/fifo", tags=["fifo"])


# ── Pydantic models ────────────────────────────────────────────────────

class FifoRunRequest(BaseModel):
    folder: str                                 # absolute path on server
    qty_mode: str = "auto"                      # "shares" | "cert_units" | "auto"
    recon_mode: str = "t0_synthetic"            # "strict" | "t0_synthetic"
    prod_ccy: str = "USD"
    order_files: Optional[list[str]] = None     # explicit file list; None = auto-detect
    termsheet_path: Optional[str] = None        # path to termsheet_positions.json; None = auto-detect in folder


# ── Helpers ────────────────────────────────────────────────────────────

def _detect_qty_mode(scaling_factors: dict[str, float]) -> str:
    """Heuristic: if most scaling factors are far from 1.0 → cert_units."""
    if not scaling_factors:
        return "shares"
    k_values = list(scaling_factors.values())
    far_from_one = sum(1 for k in k_values if k < 0.5 or k > 2.0)
    return "cert_units" if far_from_one / len(k_values) > 0.2 else "shares"


def _serial(obj):
    """Recursively make dataclasses/dates JSON-serialisable."""
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {k: _serial(v) for k, v in dataclasses.asdict(obj).items()}
    if isinstance(obj, list):
        return [_serial(i) for i in obj]
    if isinstance(obj, datetime.date):
        return obj.isoformat()
    return obj


def _run_fifo(folder: str, qty_mode: str, recon_mode: str, prod_ccy: str,
              order_files: list[str] | None, termsheet_path: str | None = None) -> dict:
    """Thin wrapper over the shared FIFO pipeline (core/fifo/pipeline.py) — the
    exact same code path the AMC study uses (amc_study.py) — reshaped into this
    endpoint's REST response shape.
    """
    if qty_mode == "auto":
        qty_mode = "shares"

    result, carnet_orders, meta = run_fifo_recon(
        folder,
        qty_mode=qty_mode,
        recon_mode=recon_mode,
        prod_ccy=prod_ccy,
        order_files=order_files,
        termsheet_path=termsheet_path,
    )

    return {
        "meta": meta,
        "summary": {
            "total_realized": result.total_realized,
            "total_latent": result.total_latent,
            "total_pnl": result.total_pnl,
            "open_position_count": len(result.open_positions),
            "round_trip_count": len(result.round_trips),
            "synthetic_count": len(result.synthetic_report),
        },
        "open_positions": _serial(result.open_positions),
        "round_trips": _serial(result.round_trips),
        "synthetic_report": _serial(result.synthetic_report),
        "scaling_factors": {},
    }


# ── Endpoints ──────────────────────────────────────────────────────────

@router.post("/run")
def fifo_run(
    req: FifoRunRequest,
    current: Annotated[User, Depends(get_current_user)],
):
    """Run FIFO reconstruction on a carnet folder.

    Returns open positions, round trips, synthetic injections and P&L summary.
    """
    if not os.path.isdir(req.folder):
        raise HTTPException(422, f"Dossier introuvable : {req.folder}")
    try:
        return _run_fifo(
            folder=req.folder,
            qty_mode=req.qty_mode,
            recon_mode=req.recon_mode,
            prod_ccy=req.prod_ccy,
            order_files=req.order_files,
            termsheet_path=req.termsheet_path,
        )
    except ValueError as e:
        raise HTTPException(422, str(e))
    except Exception as e:
        import traceback; traceback.print_exc()
        raise HTTPException(500, f"Erreur FIFO : {e}")


@router.post("/detect")
def fifo_detect(
    payload: dict,
    current: Annotated[User, Depends(get_current_user)],
):
    """Scan a folder and return detected order files + suggested mode.

    Body: {"folder": "<path>"}
    """
    folder = payload.get("folder", "")
    if not folder or not os.path.isdir(folder):
        raise HTTPException(422, "Dossier introuvable")

    files = detect_order_files(folder)
    if not files:
        return {"files": [], "suggested_mode": "shares", "order_count": 0}

    try:
        orders = load_orders(files)
        # Quick pass to estimate mode
        result_p1 = reconstruct(orders, {}, orders[-1].date, "USD",
                                recon_mode="strict", t0_date=orders[0].date,
                                t0_prices_prod={})
        t0_prices = fetch_t0_prices_from_lots(result_p1.open_positions, "USD")
        factors = compute_scaling_factors_from_positions(result_p1.open_positions, t0_prices)
        mode = _detect_qty_mode(factors)
    except Exception:
        mode = "shares"
        orders = []

    return {
        "files": [os.path.basename(f) for f in files],
        "suggested_mode": mode,
        "order_count": len(orders),
    }
