"""Lifecycle evaluation of a deal and its terminal-state rules."""
from __future__ import annotations
import json
from datetime import date
from typing import Optional
from ...runtime import business_today
from ...db.models import Deal
from ...core.payscript.parser import parse_script, resolve_constats
from ...core.payscript.engine import eval_script_on_history
from ...core.lifecycle_controls import horizon_contractuel, semantic_maturity_outcome
from ...core.market_snapshot import snapshot_rate

def _evaluate_lifecycle(deal: Deal, events: list, dates_list: list, prices: dict,
                         tickers: list) -> dict | None:
    """Replay the booked script against the historical prices already loaded
    for events/refresh, to find out whether the product has actually called
    early or reached maturity — vs. just knowing raw spot values without
    ever checking them against the payoff condition. Returns a small summary
    dict for the API response, or None if evaluation couldn't run (e.g. a
    CONSTAT-based script whose calendar overrides aren't persisted on the
    deal — a known gap, not fatal to the spot refresh above).

    This function is deliberately pure with respect to persistence: indicative
    market data may propose a result, but it may never apply it."""
    market = json.loads(deal.market_snapshot_json) if deal.market_snapshot_json else {}
    compiled = parse_script(deal.script_snapshot)
    # Expert-mode deals: CONSTAT calendars frozen at booking (market.constats,
    # persisted since 2026-07-19) — resolved relative to the deal's value_date,
    # not today. Deals booked before that persistence still raise ValueError
    # here, which callers already treat as "replay unavailable".
    _origin = deal.strike_date or deal.value_date
    compiled = resolve_constats(
        compiled, market.get("constats") or {},
        anchor=date.fromisoformat(_origin) if _origin else None,
        currency=(deal.devise or "").strip().upper() or None,
    )
    r_frac = snapshot_rate(market)
    # PARAM overrides frozen at booking (stored units) — without them the
    # replay would use the script's seed defaults, wrong for any deal whose
    # terms were tuned in the UI (degressive barriers, negotiated coupon…).
    user_params = market.get("user_params", {}) or {}

    # Reference index = last trading day <= strike_date (the same "closest
    # price at or before the event" convention _closest_price uses for the
    # displayed S₀). The fetched window starts BEFORE the strike (see
    # refresh_events) precisely so a weekend/holiday strike date still has a
    # preceding close to anchor on — index 0 would otherwise be a week early.
    start_idx = 0
    for i_d, d_str in enumerate(dates_list):
        if d_str <= deal.strike_date:
            start_idx = i_d
        else:
            break

    # Chaque date du contrat se lit à sa date, maturité comprise : l'horizon est
    # celui de la date de maturité du deal, pas le tenor saisi au pricing.
    horizon = horizon_contractuel(deal, compiled)
    res = eval_script_on_history(
        compiled, dates_list, prices, start_idx, horizon, user_params, tickers, r_frac,
        origine=_origin,
    )
    if res is None:
        return None

    today_str = business_today().isoformat()
    non_strike = [e for e in events if e.t_years > 0]

    # Total of every cash flow that actually fired, in both branches below —
    # what the client actually received in total, as a fraction of nominal.
    # eval_script_on_history only ever appends flows that fired, so summing
    # the whole list (not just the terminal one) is correct in either case.
    # Keep the same precision as the authoritative fixing replay.  Rounding
    # the monitoring leg to four decimals created false payout mismatches on
    # large notionals even when both calculations were economically identical.
    realized_payout = round(sum(cf["cf"] for cf in res["cash_flows"]), 8)

    if res["early_recall"]:
        T_actual = res["T_actual"]
        triggering = min(non_strike, key=lambda e: abs(e.t_years - T_actual))
        point = next((c for c in compiled.echeancier.constatations if abs(c.t-T_actual)<1e-5), None)
        payment_day = point.jour_paiement if point and point.jour_paiement else date.fromisoformat(triggering.event_date)
        terminal_amount = sum(cf['cf'] for cf in res['cash_flows'] if abs(cf['t']-T_actual)<1e-5)
        return {"outcome": "callé", "event_id": triggering.id,
                "event_date": triggering.event_date, "t_years": triggering.t_years,
                "settlement_date":payment_day.isoformat(), "settlement_amount":round(terminal_amount,8),
                "realized_payout": realized_payout}

    # No early recall — only conclude "matured" if today has actually
    # reached the maturity date. T_actual == T_max on its own is ambiguous:
    # eval_script_on_history also returns that when the price history simply
    # doesn't extend far enough yet to know (see its mat_events branch).
    if today_str >= deal.maturity_date:
        maturity_payout = sum(cf["cf"] for cf in res["cash_flows"] if abs(cf["t"] - horizon) < 1e-6)
        maturity_event = max(events, key=lambda e: e.t_years)
        # The label comes from explicit script state (KI/BREACHED variables),
        # never from the amount paid. A capital-protected or option payoff can
        # be below par without being a knock-in.
        outcome, outcome_basis = semantic_maturity_outcome(compiled, res)
        return {"outcome": outcome, "event_id": maturity_event.id,
                "event_date": maturity_event.event_date,
                "outcome_basis": outcome_basis,
                "maturity_payout": round(maturity_payout, 8),
                "realized_payout": realized_payout}

    return {"outcome": "en_cours"}


def _payout_reconciliation_tolerance(deal: Deal) -> tuple[float, float]:
    """Return (normalised payout tolerance, monetary tolerance).

    PayScript cash flows are expressed as a fraction of notional.  The
    accepted difference is therefore half of the smallest currency unit,
    converted back to a fraction of the booked notional.
    """
    decimals = 0 if deal.devise in {"JPY", "KRW", "CLP", "VND"} else (
        3 if deal.devise in {"BHD", "KWD", "OMR", "JOD", "TND"} else 2)
    monetary_tolerance = 0.5 * (10 ** -decimals)
    if not deal.nominal or deal.nominal <= 0:
        return 0.0, monetary_tolerance
    return monetary_tolerance / float(deal.nominal), monetary_tolerance


def _terminal_deal_state(
    deal: Deal, outcome: str, result: dict, asof: date,
) -> tuple[str, Optional[float]]:
    """Status and outstanding amount after a terminal observation."""
    if outcome == "callé":
        payment = date.fromisoformat(result.get('settlement_date') or deal.settlement_date or result.get('event_date') or asof.isoformat())
        amount = result.get('settlement_amount',result.get('realized_payout'))
        return ('en_reglement',float(amount)) if payment>asof and amount is not None else ('callé',None)
    payment = date.fromisoformat(deal.payment_date or deal.maturity_date)
    outstanding = result.get("maturity_payout")
    if payment > asof and outstanding is not None:
        return "en_reglement", float(outstanding)
    return "échu", None
