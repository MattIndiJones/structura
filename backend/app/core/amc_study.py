"""AMC study orchestrator.

Entry point that turns a manifest + study folder into a complete result:
manifest → raw data → order-book reconstruction → blocks A/B/C/D → confidence.

Blocks are independent and degrade gracefully: a disabled block is skipped, and
a block that errors is reported (so the confidence section can account for it)
without sinking the whole study.
"""
from __future__ import annotations

import glob
from pathlib import Path
from typing import Dict, List, Optional, Set

from .amc_manifest import StudyManifest, BLOCK_CATALOG
from .amc_orderbook import load_study_data
from .amc_fifo_adapter import fifo_to_legacy_recon
from .amc_blocks import block_b_attribution, block_c_trading, block_d_behaviour
from .fifo.pipeline import run_fifo_recon
from .amc_confidence import build_confidence
from .amc_replicability import compute_replicability
from .amc_timing import compute_timing_score
from .amc_stockpicking import compute_stockpicking_score
from .amc_riskmanagement import compute_risk_management_score
from .amc_managerskill import compute_manager_skill_score
from .amc_marketshocks import compute_market_shocks
from . import amc_engine


# factor_model → (ff selected factors)
_FACTOR_SETS = {
    "FF3": ["Mkt-RF", "SMB", "HML"],
    "FF5": ["Mkt-RF", "SMB", "HML", "RMW", "CMA"],
    "FF5+MOM": ["Mkt-RF", "SMB", "HML", "RMW", "CMA", "MOM"],
}


def _resolve_order_files(folder: str, names: list[str]) -> Optional[List[str]]:
    """Resolve manifest-listed order files against the study folder.

    Mirrors amc_orderbook.load_study_data()'s _resolve() so a manifest edited
    to include/exclude specific carnet files is honoured by the FIFO pipeline
    too, instead of it silently re-globbing the folder from scratch.
    """
    from .amc_controls import resolve_file
    return [resolve_file(folder, name) for name in names]


def run_study(manifest_dict: dict, folder: str) -> dict:
    from .amc_controls import market_capture
    from .amc_market_bundle import market_bundle
    with market_bundle(folder, manifest_dict.get("files", {}).get("market_data", "")), market_capture() as market_inputs:
        result = _run_study(manifest_dict, folder)
        result["provenance"]["market_inputs"] = market_inputs
        return result


def _run_study(manifest_dict: dict, folder: str) -> dict:
    """Run the full (or partial) study described by the manifest over `folder`."""
    manifest = StudyManifest(**manifest_dict)
    toggles = manifest.blocks
    enabled: Set[str] = {k for k, v in toggles.model_dump().items() if v}

    from .amc_controls import input_provenance, resolve_file, fingerprint
    from types import SimpleNamespace
    import time
    started = time.monotonic()
    initial_provenance = input_provenance(folder, manifest.files.model_dump(), manifest.model_dump())
    needs_fifo = toggles.B_attribution or toggles.C_trading or toggles.D_behaviour
    needs_orders = needs_fifo or toggles.H_timing or toggles.I_stockpicking or toggles.K_marketshocks or manifest.params.dividends.status == "provided"
    data = load_study_data(folder, manifest.files.model_dump(), as_of=manifest.params.as_of,
                           require_orders=needs_orders, require_composition=needs_fifo,
                           product_currency=manifest.product.currency, valuation_source=manifest.params.valuation_source,
                           orders_split_adjusted=manifest.params.orders_split_adjusted)
    composition = data["composition"]
    orders = data["orders"]
    nav = data["nav"]
    as_of = data["as_of"]

    prod_ccy = manifest.product.currency
    from .amc_dividends import prepare_dividends
    from .fifo.schema import Order
    dividends = prepare_dividends(resolve_file(folder, manifest.files.dividends),
        resolve_file(folder, manifest.files.cash_events), manifest.params.dividends,
        orders, nav[0]["date"], nav[-1]["date"], prod_ccy,
        initial_positions=[p.model_dump() for p in manifest.params.termsheet_positions],
        units=nav[0].get("outstanding") or manifest.params.n_certs,
        transaction_fee_pct=manifest.params.txn_cost_pct)
    extra_orders = [Order(id=o["id"], date=o["date"].date(), isin=o["isin"], name=o["name"],
        qty=o["executed_qty"], price_local=o["price_local"], price_ccy=o["ccy"], fx=o["fx"], price_prod=o["price_prod"])
        for o in dividends["generated_orders"]]
    orders = sorted(orders + dividends["generated_orders"], key=lambda o: o.get("date") or as_of)
    cash_income = dividends["totals"]["net_income_prod"]
    if composition.get("currency") and composition["currency"].upper() != prod_ccy.upper():
        raise ValueError("La devise du manifeste diffère de celle du relevé de composition")
    # qty_mode is always "shares": the T0 basket formula (n_certs × weight% × NAV /
    # real_market_price) already cancels out whatever unit the term sheet's qty_per_cert
    # was expressed in (shares or accounting units) — confirmed on CH1352587724 by
    # cross-checking against the LUKB factsheet. A separate "cert_units" carnet mode
    # would only matter if the carnet itself recorded accounting-unit trades, which
    # isn't the case for any fund studied so far (carnets are real share executions).
    fifo_meta, carnet_orders = {}, []
    recon = SimpleNamespace(round_trips=[], open_positions=[], synthetic_report=[], warnings=[])
    fifo_error = None
    if needs_fifo:
        try:
            fifo_result, carnet_orders, fifo_meta = run_fifo_recon(
                folder, qty_mode="shares", recon_mode=manifest.params.recon_mode, prod_ccy=prod_ccy,
                order_files=_resolve_order_files(folder, manifest.files.orders),
                termsheet_positions=[p.model_dump() for p in manifest.params.termsheet_positions],
                nav_path=resolve_file(folder, manifest.files.nav_timeseries),
                as_of_date=as_of.strftime("%Y-%m-%d"),
                additional_orders=extra_orders,
                supplied_marks=composition["marks"] if manifest.params.valuation_source == "composition" else None,
                orders_split_adjusted=manifest.params.orders_split_adjusted)
            recon = fifo_to_legacy_recon(fifo_result, carnet_orders, as_of, prod_ccy)
        except ValueError as exc:
            fifo_error = str(exc)
            recon.warnings.append(f"FIFO indisponible : {exc}")

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
            "outstanding":        composition.get("outstanding"),
            "total_aum":          composition.get("total_aum"),
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
            "valuation_source": manifest.params.valuation_source,
            "management_fee_basis": manifest.params.management_fee_basis,
            "performance_crystallization": manifest.params.performance_crystallization,
            # Output
            "audience":       manifest.output.audience,
            "blocks_run":     sorted(enabled),
            # Study folder — embedded so downstream tools (VAG) can load raw files
            "folder":         folder,
            # FIFO pipeline diagnostics (T0 fixing, ISIN aliases, injected orders)
            "fifo":           fifo_meta,
        },
        "dividends": {k: v for k, v in dividends.items() if k != "generated_orders"},
        "reconstructed_dividend_orders": [{**o, "date": o["date"].isoformat()} for o in dividends["generated_orders"]],
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
    if toggles.B_attribution and not fifo_error:
        result["block_b"] = block_b_attribution(
            recon, composition, nav=nav,
            management_fee_pct=manifest.params.management_fee_pct,
            fifo_as_of=fifo_meta.get("as_of"),
            perf_fee_pct=manifest.params.perf_fee_pct,
            txn_cost_pct=manifest.params.txn_cost_pct,
            carnet_orders=carnet_orders,
            management_fee_basis=manifest.params.management_fee_basis,
            performance_crystallization=manifest.params.performance_crystallization,
            cash_income=cash_income, dividend_ledger=dividends,
        )
        _add_concentration_warnings(result)

    # ── Bloc C — trading ──
    if toggles.C_trading and not fifo_error:
        result["block_c"] = block_c_trading(recon, orders, nav, composition)

    # ── Bloc D — comportement ──
    if toggles.D_behaviour and not fifo_error:
        result["block_d"] = block_d_behaviour(
            recon, orders, composition,
            manifest.params.long_term_holding_days,
            manifest.params.conviction_weight_pct)

    # ── Bloc H — Timing Score ──
    if toggles.H_timing:
        try:
            result["block_h"] = compute_timing_score(orders, as_of=as_of.strftime("%Y-%m-%d"))
        except Exception as e:
            result["block_h"] = {"available": False, "error": f"Erreur Bloc H : {e}"}

    # ── Bloc I — Stock Picking Score ──
    if toggles.I_stockpicking:
        try:
            result["block_i"] = compute_stockpicking_score(
                orders, manifest.params.benchmark_ticker, as_of=as_of.strftime("%Y-%m-%d"), prod_ccy=prod_ccy)
        except Exception as e:
            result["block_i"] = {"available": False, "error": f"Erreur Bloc I : {e}"}

    # ── Bloc J — Risk Management Score ──
    if toggles.J_riskmanagement:
        try:
            result["block_j"] = compute_risk_management_score(
                nav, composition, block_a, manifest.params.benchmark_ticker)
        except Exception as e:
            result["block_j"] = {"available": False, "error": f"Erreur Bloc J : {e}"}

    # ── Bloc K — Réactivité aux Chocs de Marché ──
    if toggles.K_marketshocks:
        try:
            result["block_k"] = compute_market_shocks(
                orders, result["meta"], block_h=result.get("block_h"))
        except Exception as e:
            result["block_k"] = {"available": False, "error": f"Erreur Bloc K : {e}"}

    # ── Bloc E — Référentiel Inertiel (B&H depuis l'émission) ──
    reference = manifest.params.reference_portfolio
    reference_nav = nav
    ts_positions = [p.model_dump() for p in manifest.params.termsheet_positions] or None
    if reference:
        if reference.start_date not in {str(r["date"])[:10] for r in nav}:
            raise ValueError("Date du panier de référence absente de la NAV")
        reference_nav = [r for r in nav if str(r["date"])[:10] >= reference.start_date]
        ts_positions = [p.model_dump() for p in reference.positions]
        result["reference_portfolio"] = reference.model_dump()
    try:
        from .amc_bh import compute_bh
        result["block_e"] = compute_bh(
            reference_nav,
            prod_ccy=composition.get("currency", ""),
            termsheet_positions=ts_positions,
            n_certs=manifest.params.n_certs,
            orders=orders,
            composition=composition,
            as_of=as_of.strftime("%Y-%m-%d"),
        ) if toggles.E_bh else {"available": False, "skipped": True}
    except Exception as e:
        result["block_e"] = {"available": False, "error": str(e)}

    if toggles.G_brinson:
        try:
            from .amc_market_bundle import active_bundle
            from .amc_brinson import compute_brinson
            bundle = active_bundle()
            if bundle is None:
                raise ValueError("Le calcul automatique de G exige un dossier de marché ; sinon utiliser son onglet dédié")
            if not result.get("block_b"):
                raise ValueError("Le bloc B est requis pour le calcul automatique de G")
            g_study = {**result, "termsheet_basket": ts_positions or [], "meta": {
                **result["meta"], "nav_start_date": str(reference_nav[0]["date"])[:10],
                "nav_start_value": float(reference_nav[0]["nav"])}}
            result["block_g"] = compute_brinson(g_study, bundle.prices, manifest.params.benchmark_ticker,
                manifest.product.currency, cached_sectors=bundle.sectors)
        except Exception as exc:
            result["block_g"] = {"available": False, "error": str(exc)}

    # Conservative quality gate, independent from statistical scores.
    missing_marks = [p["isin"] for p in recon.open_positions if not p.get("marked")]
    negative_positions = [p["isin"] for p in recon.open_positions if p.get("open_qty", 0) < 0]
    expected = {c.get("isin"): c.get("position", 0) for c in composition.get("components", []) if c.get("isin")}
    actual = {p["isin"]: p.get("open_qty", 0) for p in recon.open_positions}
    mismatches = [{"isin": k, "reconstructed": actual.get(k, 0), "reported": expected.get(k, 0)}
                  for k in expected.keys() | actual.keys()
                  if abs(actual.get(k, 0) - expected.get(k, 0)) > 1e-3] if needs_fifo else []
    reconciliation = (result.get("block_b", {}).get("totals", {}).get("reconciliation") or {})
    gap = reconciliation.get("gap_aum_bps")
    problems = []
    if needs_fifo and result["meta"].get("nav_snapshot_date") != result["meta"]["as_of"]:
        problems.append("Relevé de composition daté différemment de l’arrêté : rapprochement à valider")
    if needs_fifo and cash_income is None:
        result["warnings"].append("Dividendes non renseignés : le rapprochement ne les inclut pas")
    if manifest.params.valuation_source == "composition":
        result["warnings"].append("Valorisation issue du relevé daté ; pas de validation indépendante des cours de marché")
    result["warnings"].extend(dividends["issues"])
    if dividends["status"] == "provided":
        problems.extend(dividends["issues"])
    if dividends["generated_orders"]:
        problems.append("Achats de réinvestissement reconstruits : hypothèses à valider")
    if fifo_error: problems.append(fifo_error)
    if missing_marks: problems.append("Valorisations manquantes")
    if negative_positions: problems.append("Positions négatives non expliquées")
    if mismatches: problems.append("Quantités non rapprochées du relevé")
    if recon.synthetic_report: problems.append("Achats synthétiques : reconstruction estimée")
    if toggles.B_attribution and (gap is None or abs(gap) > 1): problems.append("Rapprochement NAV non validé (tolérance indicative : 1 bp AUM)")
    result["data_quality"] = {"status": "review_required" if problems else "ready",
        "issues": problems, "missing_marks": missing_marks, "position_differences": mismatches,
        "snapshot_date": result["meta"].get("nav_snapshot_date"), "gap_aum_bps": gap}
    result["warnings"].extend(problems)
    for key in ("b", "c", "d"):
        if fifo_error and getattr(toggles, {"b": "B_attribution", "c": "C_trading", "d": "D_behaviour"}[key]):
            result["block_" + key] = {"available": False, "error": fifo_error}

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

    if toggles.F_replicability and "block_f" not in result:
        result["block_f"] = {"available": False, "error": "Bloc A requis et disponible pour calculer F"}
        block_f = result["block_f"]

    # ── Confidence & limitations ──
    result["confidence"] = build_confidence(
        enabled, block_a, len(orders),
        block_e_result=result.get("block_e"), brinson_result=result.get("block_g"),
        block_f_result=block_f,
        block_h_result=result.get("block_h"),
        block_i_result=result.get("block_i"),
        block_j_result=result.get("block_j"),
        block_b_result=result.get("block_b"), data_quality=result.get("data_quality"),
    )
    if toggles.B_attribution:
        complete_dividends = dividends["status"] in {"none", "provided"} and not dividends["issues"]
        result["confidence"]["rows"].append({
            "dimension": "Dividendes et créances", "feasible": complete_dividends,
            "confidence_pct": 100 if complete_dividends else 0,
            "missing_data": "" if complete_dividends else "Dates de détachement/paiement, montants ou réinvestissements non documentés",
            "unlocks": "Attribution des revenus et des créances à l'arrêté",
            "roadmap": "Fournir le registre daté ou confirmer explicitement l'absence de dividendes",
            "note": "Exhaustivité déclarée par l'utilisateur ; les paiements seuls ne prouvent pas l'absence de créances."})
        coverage_rows = result["confidence"]["rows"]
        result["confidence"]["overall_pct"] = round(sum(r["confidence_pct"] for r in coverage_rows)/len(coverage_rows), 1)

    provenance = input_provenance(folder, manifest.files.model_dump(), manifest.model_dump())
    if provenance["input_hashes"] != initial_provenance["input_hashes"]:
        raise ValueError("Les fichiers sources ont changé pendant le calcul : relancez l’étude")
    result["provenance"] = provenance
    result["manifest"] = manifest.model_dump()
    result["source_orders"] = [{**o, "date": o["date"].isoformat() if o.get("date") else None} for o in orders]
    result["source_nav"] = nav
    result["block_status"] = {k: ("skipped" if not v else "error" if result.get("block_" + k[0].lower(), {}).get("available") is False else "completed") for k, v in toggles.model_dump().items()}
    provenance["elapsed_seconds"] = round(time.monotonic() - started, 3)
    provenance["result_hash"] = fingerprint({k: v for k, v in result.items() if k != "provenance"})
    return result


def _nav_records(nav: list[dict], fee_pct: Optional[float], gross: bool) -> list[dict]:
    """Build run_analysis-compatible NAV records. For gross, add back the daily
    fee accrual to the net return (fee drag is deterministic from the term sheet)
    and rebuild the "nav" level series by compounding those gross-adjusted returns
    — otherwise run_analysis's NAV-level metrics (chart, drawdown, full-period
    stats) would keep showing the net trajectory while only the regression and
    total-return scalars reflected the fee add-back."""
    recs = []
    prev_net = None
    prev_level = None
    fee_daily = ((fee_pct or 0.0) / 100.0) / 252.0 if gross else 0.0
    for r in nav:
        ret = None
        level = r["nav"]
        if prev_net is not None and prev_net != 0:
            ret = r["nav"] / prev_net - 1.0 + fee_daily
            if gross:
                level = prev_level * (1.0 + ret)
        recs.append({"date": r["date"], "nav": level, "return": ret,
                     "Outstanding Quantity": r.get("outstanding")})
        prev_net = r["nav"]
        prev_level = level
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
            nav_currency=manifest.product.currency,
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
            out["gross_methodology"] = "Ajout forfaitaire des seuls frais de gestion aux rendements (taux annuel / 252). Ni frais de performance, ni frais de transaction réintégrés ; ne constitue pas une NAV brute comptable."
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
