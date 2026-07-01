"""AMC study orchestrator.

Entry point that turns a manifest + study folder into a complete result:
manifest → raw data → order-book reconstruction → blocks A/B/C/D → confidence.

Blocks are independent and degrade gracefully: a disabled block is skipped, and
a block that errors is reported (so the confidence section can account for it)
without sinking the whole study.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Set

from .amc_manifest import StudyManifest, BLOCK_CATALOG
from .amc_orderbook import load_study_data, reconstruct
from .amc_blocks import block_b_attribution, block_c_trading, block_d_behaviour
from .amc_confidence import build_confidence
from .amc_replicability import compute_replicability
from .amc_timing import compute_timing_score
from .amc_stockpicking import compute_stockpicking_score
from .amc_riskmanagement import compute_risk_management_score
from .amc_managerskill import compute_manager_skill_score
from . import amc_engine


# factor_model → (ff selected factors)
_FACTOR_SETS = {
    "FF3": ["Mkt-RF", "SMB", "HML"],
    "FF5": ["Mkt-RF", "SMB", "HML", "RMW", "CMA"],
    "FF5+MOM": ["Mkt-RF", "SMB", "HML", "RMW", "CMA", "MOM"],
}


def run_study(manifest_dict: dict, folder: str) -> dict:
    """Run the full (or partial) study described by the manifest over `folder`."""
    manifest = StudyManifest(**manifest_dict)
    toggles = manifest.blocks
    enabled: Set[str] = {k for k, v in toggles.model_dump().items() if v}

    data = load_study_data(folder, manifest.files.model_dump())
    composition = data["composition"]
    orders = data["orders"]
    nav = data["nav"]
    as_of = data["as_of"]

    recon = reconstruct(
        orders, composition["marks"], composition["components"], as_of,
        recon_mode=manifest.params.recon_mode,
        nav_start_date=nav[0]["date"] if nav else None,
        prod_ccy=composition.get("currency", ""),
        termsheet_positions=[p.model_dump() for p in manifest.params.termsheet_positions],
    )

    # NAV history helpers
    nav_first = nav[0] if nav else None
    nav_last  = nav[-1] if nav else None
    comp_nav_date = composition.get("nav_date")

    result: dict = {
        "meta": {
            # Identification
            "isin":           manifest.product.isin,
            "product_name":   manifest.product.name or composition.get("name", ""),
            "currency":       manifest.product.currency or composition.get("currency", ""),
            "theme":          manifest.product.theme,
            # NAV history
            "nav_start_date":    nav_first["date"] if nav_first else None,
            "nav_start_value":   round(float(nav_first["nav"]), 4) if nav_first else None,
            "nav_current_date":  nav_last["date"] if nav_last else None,
            "nav_current_value": round(float(nav_last["nav"]), 4) if nav_last else None,
            "nav_n_obs":         len(nav),
            # Composition snapshot
            "nav_snapshot_date":  comp_nav_date.strftime("%Y-%m-%d") if comp_nav_date else (as_of.strftime("%Y-%m-%d") if as_of else None),
            "nav_snapshot_value": round(float(composition.get("nav_value", 0)), 4) or None,
            "outstanding":        int(composition.get("outstanding", 0)) or None,
            "total_aum":          round(float(composition.get("total_aum", 0)), 0) or None,
            # Activity
            "as_of":          as_of.strftime("%Y-%m-%d") if as_of else None,
            "n_orders":       len(orders),
            "n_underlyings":  len(composition.get("components", [])),
            # Configuration
            "management_fee_pct":  manifest.params.management_fee_pct,
            "benchmark_ticker":    manifest.params.benchmark_ticker,
            "ff_series":           manifest.params.ff_series,
            "factor_model":        manifest.params.factor_model,
            "rolling_window":      manifest.params.rolling_window,
            "recon_mode":          manifest.params.recon_mode,
            # Output
            "audience":       manifest.output.audience,
            "blocks_run":     sorted(enabled),
            # Study folder — embedded so downstream tools (VAG) can load raw files
            "folder":         folder,
        },
        "block_catalog": BLOCK_CATALOG,
        "warnings": list(recon.warnings),
        "synthetic_report": getattr(recon, "synthetic_report", []),
        # ── Baskets exposés pour l'affichage ──────────────────────────
        "termsheet_basket": [
            p.model_dump() for p in manifest.params.termsheet_positions
        ],
        "current_basket": [
            {
                "isin":       c.get("isin", ""),
                "name":       c.get("name", ""),
                "currency":   c.get("currency", ""),
                "position":   c.get("position"),
                "weight":     c.get("weight"),
                "value_prod": c.get("value_prod"),
                "mark_prod":  c.get("mark_prod"),
            }
            for c in composition.get("components", [])
        ],
    }

    # ── Bloc A — factoriel (reuse the proven FF engine, gross + net) ──
    block_a: Optional[dict] = None
    if toggles.A_factor:
        block_a = _run_block_a(manifest, nav, composition, orders)
        result["block_a"] = block_a

    # ── Bloc B — attribution ──
    if toggles.B_attribution:
        result["block_b"] = block_b_attribution(recon, composition)
        _add_concentration_warnings(result)

    # ── Bloc C — trading ──
    if toggles.C_trading:
        result["block_c"] = block_c_trading(recon, orders, nav, composition)

    # ── Bloc D — comportement ──
    if toggles.D_behaviour:
        result["block_d"] = block_d_behaviour(
            recon, orders, composition,
            manifest.params.long_term_holding_days,
            manifest.params.conviction_weight_pct)

    # ── Bloc H — Timing Score ──
    if toggles.H_timing:
        try:
            result["block_h"] = compute_timing_score(orders)
        except Exception as e:
            result["block_h"] = {"available": False, "error": f"Erreur Bloc H : {e}"}

    # ── Bloc I — Stock Picking Score ──
    if toggles.I_stockpicking:
        try:
            result["block_i"] = compute_stockpicking_score(
                orders, manifest.params.benchmark_ticker)
        except Exception as e:
            result["block_i"] = {"available": False, "error": f"Erreur Bloc I : {e}"}

    # ── Bloc J — Risk Management Score ──
    if toggles.J_riskmanagement:
        try:
            result["block_j"] = compute_risk_management_score(
                nav, composition, block_a, manifest.params.benchmark_ticker)
        except Exception as e:
            result["block_j"] = {"available": False, "error": f"Erreur Bloc J : {e}"}

    # ── Bloc E — Référentiel Inertiel (B&H depuis l'émission) ──
    ts_positions = [p.model_dump() for p in manifest.params.termsheet_positions] or None
    try:
        from .amc_bh import compute_bh
        result["block_e"] = compute_bh(
            nav,
            prod_ccy=composition.get("currency", ""),
            termsheet_positions=ts_positions,
            n_certs=manifest.params.n_certs,
            orders=orders,
            composition=composition,
        )
    except Exception as e:
        result["block_e"] = {"available": False, "error": str(e)}

    # ── Manager Skill Score ──
    try:
        result["manager_skill_score"] = compute_manager_skill_score(result)
    except Exception as e:
        result["manager_skill_score"] = {"available": False, "error": str(e)}

    # ── Bloc F — Réplicabilité ──
    block_f: Optional[dict] = None
    if toggles.F_replicability and block_a and block_a.get("available"):
        try:
            block_f = compute_replicability(block_a)
            result["block_f"] = block_f
        except Exception as e:
            result["block_f"] = {"available": False, "error": f"Erreur Bloc F : {e}"}
            block_f = result["block_f"]

    # ── Confidence & limitations ──
    result["confidence"] = build_confidence(
        enabled, block_a, len(orders),
        block_e_result=result.get("block_e"),
        block_f_result=block_f,
        block_h_result=result.get("block_h"),
        block_i_result=result.get("block_i"),
        block_j_result=result.get("block_j"),
    )

    return result


def _nav_records(nav: list[dict], fee_pct: Optional[float], gross: bool) -> list[dict]:
    """Build run_analysis-compatible NAV records. For gross, add back the daily
    fee accrual to the net return (fee drag is deterministic from the term sheet)."""
    recs = []
    prev = None
    fee_daily = ((fee_pct or 0.0) / 100.0) / 252.0 if gross else 0.0
    for r in nav:
        ret = None
        if prev is not None and prev != 0:
            ret = r["nav"] / prev - 1.0 + fee_daily
        recs.append({"date": r["date"], "nav": r["nav"], "return": ret,
                     "Outstanding Quantity": r.get("outstanding")})
        prev = r["nav"]
    return recs


def _comp_records(composition: dict) -> list[dict]:
    """Composition in the column shape _compute_concentration expects."""
    return [{"Underlying Name": c["name"], "API Weight %": (c["weight"] or 0.0) * 100}
            for c in composition.get("components", [])]


def _orders_to_tx_records(orders: list[dict]) -> list[dict]:
    """Convert study-engine order dicts (from amc_orderbook) to the tx_records
    column format expected by amc_engine._compute_activity."""
    result = []
    for o in orders:
        if o.get("state") != "Done":
            continue
        date = o.get("date")
        date_str = date.strftime("%Y-%m-%d") if hasattr(date, "strftime") else str(date)[:10] if date else ""
        result.append({
            "Date": date_str,
            "Side": o.get("side", "BUY"),
            "Underlying Name": o.get("name", ""),
            "USD Notional Abs": o.get("notional_prod", 0.0),
        })
    return result


def _run_block_a(manifest: StudyManifest, nav: list[dict], composition: dict,
                 orders: list[dict]) -> dict:
    """Run the Fama-French regression on net and gross NAV. Degrades gracefully
    if the FF factor store is empty or the benchmark download fails."""
    if not nav:
        return {"available": False, "error": "Aucune série NAV (timeseries) disponible."}

    # selected_factors: explicit list wins over factor_model preset
    selected = (manifest.params.selected_factors
                or _FACTOR_SETS.get(manifest.params.factor_model, _FACTOR_SETS["FF5"]))
    comp_records = _comp_records(composition)
    tx_records = _orders_to_tx_records(orders)

    def _one(gross: bool):
        recs = _nav_records(nav, manifest.params.management_fee_pct, gross)
        return amc_engine.run_analysis(
            nav_records=recs,
            tx_records=tx_records,
            comp_records=comp_records,
            exposures={},
            ff_series=manifest.params.ff_series,
            selected_factors=selected,
            benchmark_ticker=manifest.params.benchmark_ticker,
            rolling_window=manifest.params.rolling_window,
        )

    try:
        net = _one(gross=False)
    except ValueError as e:
        return {"available": False, "error": str(e), "factor_model": manifest.params.factor_model}
    except Exception as e:  # pragma: no cover - defensive
        return {"available": False, "error": f"Erreur Bloc A : {e}"}

    out = {"available": True, "factor_model": manifest.params.factor_model,
           "ff_series": manifest.params.ff_series, "net": net}

    # Attach composite benchmark definition when applicable (for PDF + UI display)
    from .amc_benchmarks import get_composite, is_composite
    if is_composite(manifest.params.benchmark_ticker):
        bm_def = get_composite(manifest.params.benchmark_ticker)
        if bm_def:
            out["benchmark_composition"] = bm_def
            net["benchmark_composition"] = bm_def

    # Gross only meaningful if a fee was supplied
    if manifest.params.management_fee_pct:
        try:
            out["gross"] = _one(gross=True)
            out["fee_drag_pct"] = manifest.params.management_fee_pct
        except Exception:
            pass
    return out


def _add_concentration_warnings(result: dict) -> None:
    """Add warnings when a single underlying dominates the P&L or latent value."""
    bb = result.get("block_b") or {}
    per_name = bb.get("per_name") or []
    totals   = bb.get("totals") or {}

    total_pnl    = totals.get("total_pnl") or 0
    total_unreal = totals.get("unreal_pnl") or 0

    THRESHOLD = 0.60   # flag when one name > 60% of a metric

    for name_data in per_name:
        n = name_data.get("name", "?")

        # P&L total domination
        pnl = name_data.get("total_pnl") or 0
        if total_pnl and abs(total_pnl) > 0 and abs(pnl / total_pnl) >= THRESHOLD:
            share = pnl / total_pnl * 100
            result["warnings"].append(
                f"⚠ Concentration P&L : {n} représente {abs(share):.0f}% du P&L total "
                f"({'+' if pnl >= 0 else ''}{pnl:,.0f}). "
                "Les scores globaux (Sharpe, alpha, VAG) reflètent principalement ce titre."
            )

        # Latent P&L domination
        unreal = name_data.get("unreal_pnl") or 0
        if total_unreal and abs(total_unreal) > 0 and abs(unreal / total_unreal) >= THRESHOLD:
            share = unreal / total_unreal * 100
            result["warnings"].append(
                f"⚠ Concentration P&L latent : {n} représente {abs(share):.0f}% du P&L latent "
                f"({'+' if unreal >= 0 else ''}{unreal:,.0f}). "
                "La performance latente non réalisée est concentrée sur un seul titre."
            )
