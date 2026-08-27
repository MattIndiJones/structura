"""Official lifecycle replay and reconciliation controls.

Indicative history may create a proposal.  Only validated official fixings may
validate it.  Observation-date products can be replayed from those fixings;
payoffs requiring an intra-period path are failed closed until an official
daily/continuous path feed is available.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import date, timedelta

from .market_snapshot import snapshot_rate
from .payscript.engine import eval_script_on_history
from .payscript.parser import parse_script, resolve_constats


_PATH_OBSERVABLE = re.compile(
    r"\b(?:WOF_MIN|BOF_MAX|S_MIN\s*\[|S_MAX\s*\[|REALVOL|FIX_(?:MIN|MAX|AVG))",
    re.IGNORECASE,
)
_KI_STATE = re.compile(r"(?:^|_)(?:KI|KNOCK_?IN|BREACH(?:ED)?)(?:$|_)", re.IGNORECASE)


def official_input_hash(deal, events: list) -> str:
    """Hash every contractual and official input used by the replay."""
    market = json.loads(deal.market_snapshot_json or "{}")
    payload = {
        "deal_id": deal.id,
        "contract_version": getattr(deal, "contract_version", 1),
        "script_snapshot": deal.script_snapshot,
        "T": deal.T,
        "value_date": deal.value_date,
        "strike_date": deal.strike_date,
        "market": {
            "r": market.get("r"),
            "user_params": market.get("user_params") or {},
            "constats": market.get("constats") or {},
        },
        "events": [
            {
                "id": event.id,
                "event_index": event.event_index,
                "event_date": event.event_date,
                "t_years": event.t_years,
                "spots": json.loads(event.spots_json or "{}"),
                "fixing_status": event.fixing_status,
                "data_category": event.data_category,
                "fixing_version_id": getattr(event, "current_fixing_version_id", None),
                "fixing_version": getattr(event, "fixing_version", 0),
                "fixing_record_sha256": getattr(event, "fixing_record_sha256", None),
                "fixing_evidence_sha256": getattr(event, "fixing_evidence_sha256", None),
                "fixing_provider": getattr(event, "fixing_provider", None),
                "fixing_external_reference": getattr(
                    event, "fixing_external_reference", None),
                "fixing_entered_by": getattr(event, "fixing_entered_by", None),
                "validated_by": getattr(event, "validated_by", None),
            }
            for event in sorted(events, key=lambda row: (row.t_years, row.event_index))
        ],
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def path_dependency_reasons(script_snapshot: str) -> list[str]:
    """Return explicit observables that cannot be proven from event fixings."""
    return sorted({match.group(0).upper().replace(" ", "")
                   for match in _PATH_OBSERVABLE.finditer(script_snapshot or "")})


def semantic_maturity_outcome(compiled, replay: dict) -> tuple[str, str]:
    """Read an explicit KI/breach state set by the script, never the payout.

    PARAM values live in the same memo as SET variables, so parameters are
    excluded before inspecting semantic state names.
    """
    memo = (replay.get("state") or {}).get("memo") or {}
    param_names = {param.name.upper() for param in compiled.params}
    states = {
        str(name).upper(): value for name, value in memo.items()
        if str(name).upper() not in param_names and _KI_STATE.search(str(name).upper())
    }
    breached = []
    for name, value in states.items():
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            is_set = math.isfinite(float(value)) and abs(float(value)) > 1e-12
        else:
            is_set = bool(value)
        if is_set:
            breached.append(name)
    if breached:
        return "ki", "EXPLICIT_SCRIPT_STATE:" + ",".join(sorted(breached))
    return "final", "MATURITY_NO_EXPLICIT_KI_STATE"


def replay_official_fixings(deal, events: list) -> tuple[dict | None, list[dict]]:
    """Replay a terminal proposal from validated observation-date fixings.

    The synthetic 252-step series is piecewise constant between contractual
    observations. This is exact for scripts that only read values at those
    observations. Any running/path observable is rejected before construction.
    """
    reasons = path_dependency_reasons(deal.script_snapshot)
    if reasons:
        return None, [{
            "code": "OFFICIAL_PATH_REQUIRED",
            "observables": reasons,
            "message": (
                "Le payoff dépend du chemin entre les constatations. Un flux "
                "officiel daily/continu est requis; les seuls fixings événementiels "
                "ne constituent pas une preuve suffisante."
            ),
        }]

    market = json.loads(deal.market_snapshot_json or "{}")
    origin = deal.strike_date or deal.value_date
    compiled = resolve_constats(
        parse_script(deal.script_snapshot),
        market.get("constats") or {},
        anchor=date.fromisoformat(origin) if origin else None,
        currency=(deal.devise or "").strip().upper() or None,
    )
    underlyings = json.loads(deal.underlyings_json or "[]")
    names = [row.get("name") for row in underlyings]
    tickers = [row.get("ticker") for row in underlyings]
    if not names or any(not name for name in names) or any(not ticker for ticker in tickers):
        return None, [{"code": "OFFICIAL_REPLAY_UNDERLYINGS_INVALID"}]

    ordered = sorted(events, key=lambda row: (row.t_years, row.event_index))
    strike = next((event for event in ordered if abs(event.t_years) < 1e-9), None)
    if not strike:
        return None, [{"code": "OFFICIAL_REPLAY_STRIKE_MISSING"}]
    strike_spots = json.loads(strike.spots_json or "{}")
    if any(float(strike_spots.get(name, 0) or 0) <= 0 for name in names):
        return None, [{"code": "OFFICIAL_REPLAY_STRIKE_INVALID"}]

    last_step = max(round(float(event.t_years) * 252) for event in ordered)
    maturity_step = round(float(deal.T) * 252)
    # A replay over an incomplete fixing prefix must stop at the last fixing
    # actually observed.  Padding every prefix to maturity used to manufacture
    # a terminal path by carrying the latest spot forward, which could mature
    # an otherwise live deal (or hide a later autocall) without official data.
    maturity_reached = any(
        float(event.t_years) >= float(deal.T) - 1e-9 or
        event.event_date >= deal.maturity_date
        for event in ordered
    )
    terminal_step = max(last_step, maturity_step) if maturity_reached else last_step
    grid_size = terminal_step + 1
    anchor = date.fromisoformat(deal.value_date or deal.strike_date)
    dates = [(anchor + timedelta(days=index)).isoformat() for index in range(grid_size)]
    prices = {
        ticker: [float(strike_spots[name])] * grid_size
        for name, ticker in zip(names, tickers)
    }
    for event in ordered:
        step = min(max(round(float(event.t_years) * 252), 0), grid_size - 1)
        spots = json.loads(event.spots_json or "{}")
        for name, ticker in zip(names, tickers):
            value = float(spots.get(name, 0) or 0)
            if value <= 0:
                return None, [{
                    "code": "OFFICIAL_REPLAY_FIXING_INVALID",
                    "event_id": event.id,
                    "underlying": name,
                }]
            prices[ticker][step:] = [value] * (grid_size - step)

    replay = eval_script_on_history(
        compiled,
        dates,
        prices,
        0,
        deal.T,
        market.get("user_params") or {},
        tickers,
        snapshot_rate(market),
    )
    if replay is None:
        return None, [{"code": "OFFICIAL_REPLAY_UNAVAILABLE"}]

    realized_payout = round(sum(flow["cf"] for flow in replay["cash_flows"]), 8)
    non_strike = [event for event in ordered if event.t_years > 0]
    if replay["early_recall"]:
        trigger = min(non_strike, key=lambda row: abs(row.t_years - replay["T_actual"]))
        result = {
            "outcome": "callé",
            "outcome_basis": "SCRIPT_STOP",
            "event_id": trigger.id,
            "event_date": trigger.event_date,
            "t_years": trigger.t_years,
            "realized_payout": realized_payout,
        }
    elif not maturity_reached:
        # Coupons paid by the supplied observations remain part of the replay,
        # but the lifecycle itself is not terminal until a contractual maturity
        # fixing has actually been supplied.
        trigger = max(ordered, key=lambda row: row.t_years)
        result = {
            "outcome": "en_cours",
            "event_id": trigger.id,
            "event_date": trigger.event_date,
            "realized_payout": realized_payout,
        }
    else:
        trigger = max(ordered, key=lambda row: row.t_years)
        outcome, basis = semantic_maturity_outcome(compiled, replay)
        maturity_payout = sum(
            flow["cf"] for flow in replay["cash_flows"]
            if abs(flow["t"] - deal.T) < 1e-6)
        result = {
            "outcome": outcome,
            "outcome_basis": basis,
            "event_id": trigger.id,
            "event_date": trigger.event_date,
            "maturity_payout": round(maturity_payout, 8),
            "realized_payout": realized_payout,
        }
    result["input_kind"] = "VALIDATED_EVENT_FIXINGS"
    return result, []
