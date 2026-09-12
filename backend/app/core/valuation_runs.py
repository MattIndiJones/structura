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
    "payscript/engine.py", "payscript/parser.py", "valuation_context.py",
    "deal_valuation.py", "inlife_valuation.py",
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


def replay_context(deal: Deal, ctx: dict, mtm_payload: dict) -> dict:
    if ctx.get("settlement_claim"):
        return {"settlement_claim": True, "fixed_price": mtm_payload["mtm"]}
    valuation_context = deepcopy(ctx["valuation_context"])
    return {
        "script_text": deal.script_snapshot,
        "constat_values": valuation_context.get("constats") or {},
        "value_date": deal.value_date,
        "strike_date": deal.strike_date,
        "settlement_ccy": (deal.devise or "").strip().upper() or None,
        "T_elapsed": ctx["T_elapsed"],
        "passe_jusqu_a": ctx.get("passe_jusqu_a"),
        "state": deepcopy(ctx["state"]),
        "norm_spots": list(ctx["norm_spots"]),
        "corr": deepcopy(ctx["corr"]),
        "valuation_context": valuation_context,
        "unsettled_pv": float(ctx.get("unsettled_pv") or 0.0),
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


def stage_valuation_run(session: Session, deal: Deal, user_id: int,
                        run_type: str, ctx: dict, result: dict,
                        diagnostics: dict | None = None) -> tuple[ValuationRun, dict]:
    """Stage one immutable row in the caller's transaction."""
    mtm_payload = (result.get("mtm") if isinstance(result.get("mtm"), dict)
                   else result)
    frozen_context = replay_context(deal, ctx, mtm_payload)
    engine_version, engine_fingerprint = engine_identity()
    row = ValuationRun(
        deal_id=deal.id, user_id=user_id, run_type=run_type,
        contract_version=deal.contract_version,
        context_json=canonical_json(frozen_context),
        context_hash=canonical_fingerprint(frozen_context),
        market_data_json=canonical_json(_market_evidence(ctx, mtm_payload)),
        data_versions_json=canonical_json(_data_versions(session, deal.id)),
        engine_version=engine_version, engine_fingerprint=engine_fingerprint,
        n_paths=int(ctx.get("N_used") or ctx.get("n_mc") or 0),
        result_json="{}", diagnostics_json=canonical_json(diagnostics or {}),
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
    }
