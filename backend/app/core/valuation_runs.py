"""Append-only evidence and offline replay for explicit deal valuations."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path

from sqlmodel import Session, select

from .valuation_context import canonical_fingerprint, canonical_json
from ..db.models import Deal, DealEvent, ValuationRun


_ENGINE_FILES = (
    "payscript/engine.py", "payscript/bridge.py", "payscript/time_grid.py", "payscript/parser.py", "payscript/bindings.py", "payscript/schedule_model.py", "schedule.py", "valuation_context.py",
    "deal_valuation.py", "inlife_valuation.py", "smile_calibration.py", "volatility_surface.py",
    "compute/pricers/var_scenario.py", "product/calendar.py", "calendars.py", "payscript/simulation.py",
)


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[3]


def engine_identity() -> tuple[str, str]:
    root = _repository_root()
    git_dir = root / ".git"
    version = os.getenv("STRUCTURA_ENGINE_VERSION", "unknown")
    try:
        head = (git_dir / "HEAD").read_text(encoding="utf-8").strip()
        if head.startswith("ref: "):
            ref = head[5:]
            version = (git_dir / ref).read_text(encoding="utf-8").strip()
        elif head:
            version = head
    except OSError:
        pass
    digest = hashlib.sha256()
    for relative in _ENGINE_FILES:
        path = Path(__file__).parent / relative
        digest.update(relative.encode("utf-8"))
        digest.update(path.read_bytes())
    return version, digest.hexdigest()


def calculation_identity() -> dict:
    """Identity of the implementation and numerical conventions, never a backfill."""
    import platform
    import numpy
    import scipy
    version, fingerprint = engine_identity()
    return {"schema_version": 1, "engine_version": version,
            "engine_fingerprint": fingerprint, "compiler": "payscript",
            "conventions_version": "valuation-context-v1/calendar-v2/act365.25",
            "python": platform.python_version(), "numpy": numpy.__version__,
            "scipy": scipy.__version__}


def replay_context(deal: Deal, ctx: dict, mtm_payload: dict) -> dict:
    if ctx.get("settlement_claim"):
        return {"settlement_claim": True, **deepcopy(ctx["claim_inputs"])}
    valuation_context = deepcopy(ctx["valuation_context"])
    product_terms = ctx["product_terms"]
    from .product.calendar import freeze_calendar
    return {
        "script_text": product_terms["script"],
        "frozen_calendar": freeze_calendar(ctx["compiled"]),
        "constat_values": valuation_context.get("constats") or {},
        "value_date": product_terms["value_date"],
        "strike_date": product_terms["strike_date"],
        "settlement_ccy": product_terms["settlement_ccy"],
        "T_elapsed": ctx["T_elapsed"],
        "passe_jusqu_a": ctx.get("passe_jusqu_a"),
        "state": deepcopy(ctx["state"]),
        "norm_spots": list(ctx["norm_spots"]),
        "corr": deepcopy(ctx["corr"]),
        "valuation_context": valuation_context,
        "unsettled_pv": float(ctx.get("unsettled_pv") or 0.0),
        "unsettled_cash_flows": deepcopy(ctx.get("unsettled_cash_flows") or []),
    }


def _market_evidence(ctx: dict, mtm_payload: dict) -> dict:
    observations = []
    for underlying, normalized in zip(
            ctx.get("underlyings_json") or [], ctx.get("norm_spots") or []):
        s0 = float((ctx.get("s0_map") or {}).get(underlying.get("name")) or 0.0)
        observations.append({
            "name": underlying.get("name"), "ticker": underlying.get("ticker"),
            "reference_spot": s0, "normalized_spot": float(normalized),
            "effective_spot": s0 * float(normalized) if s0 else None,
        })
    return {
        "market_used": deepcopy(mtm_payload.get("market_used") or {}),
        "observations": observations,
    }


def _data_versions(session: Session, deal_id: int) -> dict:
    events = session.exec(
        select(DealEvent).where(DealEvent.deal_id == deal_id)
        .order_by(DealEvent.event_index, DealEvent.id)
    ).all()
    return {"events": [{
        "event_id": event.id, "event_date": event.event_date,
        "fixing_version_id": event.current_fixing_version_id,
        "fixing_version": event.fixing_version,
        "record_sha256": event.fixing_record_sha256,
    } for event in events if event.fixing_version or event.current_fixing_version_id]}


def current_fixings_match(session: Session, run: ValuationRun) -> bool:
    """Only current projections are invalidated; historical evidence stays intact."""
    result = json.loads(run.result_json or "{}")
    mtm = result.get("mtm") if isinstance(result.get("mtm"), dict) else result
    asof = mtm.get("valuation_date")
    if not asof:
        return True
    saved = json.loads(run.data_versions_json or "{}").get("events", [])
    current = _data_versions(session, run.deal_id)["events"]
    def projection(rows):
        return sorted((row["event_id"], row.get("fixing_version_id"), row.get("fixing_version"), row.get("record_sha256"))
                      for row in rows if row.get("event_date", "") <= asof)
    return projection(saved) == projection(current)


def stage_valuation_run(session: Session, deal: Deal, user_id: int,
                        run_type: str, ctx: dict, result: dict,
                        diagnostics: dict | None = None) -> tuple[ValuationRun, dict]:
    """Stage one immutable row in the caller's transaction."""
    mtm_payload = (result.get("mtm") if isinstance(result.get("mtm"), dict)
                   else result)
    frozen_context = replay_context(deal, ctx, mtm_payload)
    diagnostics = deepcopy(diagnostics or {})
    effective_payload = result.get('mtm') if isinstance(result.get('mtm'), dict) else result
    diagnostics['effective_source'] = (effective_payload.get('market_used') or {}).get('source')
    diagnostics['calculation_identity'] = calculation_identity()
    if run_type in {"MTM", "REPORT"} and ctx.get("compiled") and not ctx.get("settlement_claim"):
        from .valuation_notes import note_snapshot
        diagnostics["note_snapshot"] = note_snapshot(session, deal, ctx, mtm_payload)
    engine_version, engine_fingerprint = engine_identity()
    row = ValuationRun(
        deal_id=deal.id, user_id=user_id, run_type=run_type,
        contract_version=deal.contract_version,
        context_json=canonical_json(frozen_context),
        context_hash=canonical_fingerprint(frozen_context),
        market_data_json=canonical_json(_market_evidence(ctx, mtm_payload)),
        data_versions_json=canonical_json(
            {"fixing_registry": ctx["fixing_registry"], "events": [{
                "event_id": row["event_id"], "event_date": row["event_date"],
                "fixing_version_id": row["version_id"], "fixing_version": row["version"],
                "record_sha256": row["record_sha256"],
            } for row in ctx["fixing_registry"]["official_fixings"]]} if "fixing_registry" in ctx
            else _data_versions(session, deal.id)),
        engine_version=engine_version, engine_fingerprint=engine_fingerprint,
        n_paths=int(ctx.get("N_used") or ctx.get("n_mc") or 0),
        result_json="{}", diagnostics_json=canonical_json(diagnostics),
    )
    session.add(row)
    session.flush()
    final_result = deepcopy(result)
    final_result["valuation_run_id"] = row.id
    row.result_json = canonical_json(final_result)
    deal.latest_valuation_run_id = row.id
    session.add(row)
    session.add(deal)
    return row, final_result


def replay_valuation_run(run: ValuationRun) -> dict:
    """Replay only the frozen numerical inputs; never call a data provider."""
    from .compute.pricers.var_scenario import price_var_scenario_job

    context = json.loads(run.context_json)
    if canonical_fingerprint(context) != run.context_hash:
        raise ValueError("L'empreinte du contexte archivé est invalide.")
    replayed = float(price_var_scenario_job(context)["price"])
    original = json.loads(run.result_json)
    original_mtm = original.get("mtm")
    if isinstance(original_mtm, dict):
        original_mtm = original_mtm.get("mtm")
    if original_mtm is None:
        # A Greeks run names the same baseline value explicitly because the
        # rest of its result is a set of sensitivities, not another MtM.
        original_mtm = original.get("mtm_reference")
    original_mtm = float(original_mtm)
    difference = replayed - original_mtm
    compatible = (json.loads(run.diagnostics_json or "{}").get("calculation_identity") == calculation_identity())
    return {
        "valuation_run_id": run.id, "original_mtm": original_mtm,
        "replayed_mtm": replayed, "difference": difference,
        "identical": replayed == original_mtm,
        "within_tolerance": abs(difference) <= 1e-12,
        "replayed_at": datetime.utcnow().isoformat(),
        "engine_version_original": run.engine_version,
        "engine_fingerprint_original": run.engine_fingerprint,
        "engine_version_current": engine_identity()[0],
        "engine_fingerprint_current": engine_identity()[1],
        "qualified": compatible and abs(difference) <= 1e-12,
        "mode": "qualified_replay" if compatible else "probe",
        "diagnostic": (None if compatible else
                       "Identité de moteur ou conventions absente/différente : sonde distincte, archive conservée."),
    }
