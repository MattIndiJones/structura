"""Legal aggregation and economic exposure. No database or external market I/O."""
from datetime import date, timedelta
import math

import numpy as np

from ..calendars import add_business_days, business_days_between
from .contracts import CreditProfile, CreditLimit, CSAAgreement

VERSION = "ccr-1.2"
METRICS = ("gross_notional", "current_exposure", "pfe95", "pfe99", "ead", "cva", "stressed_exposure")


def eligible_set(trade, netting_sets, agreements, as_of):
    """Return a legal bucket or a unique standalone bucket, never a cpty bucket."""
    sid = trade.get("netting_set_id")
    ns = netting_sets.get(sid)
    if ns:
        agreement = agreements.get(ns["master_agreement_id"])
        eligible = (ns["active"] and ns["enforceable_netting"] is True
                    and agreement and agreement["status"] == "ACTIVE"
                    and agreement["close_out_netting_enforceable"] is True
                    and agreement["effective_date"] <= str(as_of)
                    and trade["currency"] == ns["currency"]
                    and trade.get("product_type") in ns["product_scope"])
        if eligible:
            return f"set:{sid}"
    return f"trade:{trade['key']}"


def collateral_profile(values, times, as_of: date, csa: CSAAgreement | None, position: dict | None):
    """Lagged VM on the explicit valuation grid, with business-day MPOR freeze.

    Coarse-grid margining is disclosed as such; there is no claim of daily
    simulation when the pricing grid is weekly. No synthetic t=0 margin call.
    """
    zero = np.zeros_like(values)
    if csa is not None and csa.active and csa.collateralised is None:
        raise ValueError("CSA STATUS UNKNOWN : statut collatéralisé inconnu")
    if csa is None or not csa.active or csa.collateralised is not True:
        return zero, {"held": 0., "posted": 0., "net": 0., "im": 0.}
    if position is None or not position["recognised"]:
        raise ValueError("CSA collatéralisé : position de collatéral reconnue manquante à la date d'arrêté")
    if position["currency"] != csa.base_currency or position["collateral_type"] not in csa.eligible_collateral:
        raise ValueError("Devise ou actif du collatéral non éligible")
    haircut = csa.collateral_haircut
    # Posted collateral is a claim: the haircut increases its exposure value.
    held, posted = position["held"] * (1 - haircut), position["posted"] / (1 - haircut)
    im = position["im_held"] * (1 - haircut) if csa.im_recognised else 0.
    current = held - posted
    margins = np.full_like(values, current)
    if csa.vm_required is None or csa.im_required is None:
        raise ValueError("Statut VM ou IM inconnu")
    if csa.vm_required:
        if csa.mpor_days is None:
            raise ValueError("MPOR inconnu : renseigner la période de risque de marge")
        dates = [as_of + timedelta(days=round(t * 365.25)) for t in times]
        calls = [(dates[0], np.full(values.shape[1], current))]
        last_call = dates[0]
        settled = np.full(values.shape[1], current)
        pending = []
        for i in range(1, len(times)):
            day = dates[i]
            for due, transfer in pending:
                if due <= day:
                    settled += transfer
            pending = [(due, transfer) for due, transfer in pending if due > day]
            if business_days_between(last_call, day, csa.base_currency) >= csa.vm_frequency_days:
                target = np.maximum(values[i] - csa.threshold_counterparty, 0)
                if csa.bilateral:
                    target -= np.maximum(-values[i] - csa.threshold_our_side, 0)
                target += csa.independent_amount
                outstanding = sum((p[1] for p in pending), np.zeros(values.shape[1]))
                transfer = target - settled - outstanding
                transfer = np.where(np.abs(transfer) >= csa.mta, transfer, 0)
                due = add_business_days(day, csa.settlement_lag_days, csa.base_currency)
                calls.append((due, transfer.copy()))
                pending.append((due, transfer))
                last_call = day
            # Freeze calls during MPOR; settled calls at/before freeze remain.
            freeze = add_business_days(day, -csa.mpor_days, csa.base_currency)
            margins[i] = current + sum((v for d, v in calls[1:] if d <= freeze), np.zeros(values.shape[1]))
    return margins + im, {"held": held, "posted": posted, "net": current + im, "im": im}


def cva(times, ee, discount_rate, profile: CreditProfile | None, spread_multiplier=1.):
    if profile is None or profile.recovery is None:
        return None, "Recouvrement / LGD inconnu"
    if profile.pd_measure != "RISK_NEUTRAL":
        return None, "CVA marchande indisponible : PD non qualifiée risk-neutral"
    if not profile.pd_curve and not profile.spread_curve:
        return None, "Courbe de crédit inconnue"
    curve = profile.pd_curve or profile.spread_curve
    if times[-1] > curve[-1][0] + 1e-8:
        return None, "Courbe de crédit trop courte : aucune extrapolation implicite"
    if profile.pd_curve:
        pd = np.interp(times, [0] + [p[0] for p in curve], [0] + [p[1] for p in curve])
        pd = 1 - (1 - pd) ** spread_multiplier
    else:
        # Explicit simple flat-in-bucket hazard approximation, not CDS bootstrap.
        hazard = [p[1] * spread_multiplier / (1 - profile.recovery) for p in curve]
        cumulative = []
        for t in times:
            prev, integrated = 0., 0.
            for (end, _), h in zip(curve, hazard):
                integrated += max(0., min(t, end) - prev) * h
                prev = end
            cumulative.append(1 - math.exp(-integrated))
        pd = np.array(cumulative)
    loss = (1 - profile.recovery) * np.sum(np.exp(-discount_rate * np.array(times[1:])) * ee[1:] * np.diff(pd))
    return float(loss), None


def summarize(exposures, uncollateralised, times, rate, profile, spread_multiplier=1.):
    ee = exposures.mean(axis=1)
    p95, p99 = np.quantile(exposures, [0.95, 0.99], axis=1, method="linear")
    uncoll = uncollateralised.mean(axis=1)
    adjustment, reason = cva(times, ee, rate, profile, spread_multiplier)
    # Trapezoidal time weights on the actual, irregular grid.
    epe = float(np.sum((ee[:-1] + ee[1:]) / 2 * np.diff(times)) / times[-1])
    maximum = int(np.argmax(p95))
    return {
        "current_exposure": float(ee[0]), "ee": epe, "epe": epe,
        "pfe95": float(p95.max()), "pfe99": float(p99.max()),
        "maximum_pfe": float(p95[maximum]), "maximum_pfe_t": float(times[maximum]),
        "cva": adjustment, "cva_missing_reason": reason,
        "ead": None, "stressed_exposure": None,
        "profile": [{"t": float(t), "ee": float(e), "pfe95": float(p), "pfe99": float(q),
                     "uncollateralised_ee": float(u)} for t, e, p, q, u in zip(times, ee, p95, p99, uncoll)],
    }


def limit_check(limit: CreditLimit | None, value, currency, as_of):
    if limit is None or not limit.active or as_of < limit.effective_date or (limit.expiry_date and as_of > limit.expiry_date):
        return {"status": "NO_LIMIT", "label": "NO LIMIT DEFINED", "utilisation": None}
    base = {"metric": limit.metric, "limit": limit.amount, "currency": limit.currency, "action": limit.action,
            "warning_threshold": limit.warning_threshold, "hard_threshold": limit.hard_threshold}
    if value is None or currency != limit.currency or not math.isfinite(value):
        return {**base, "status": "MISSING_DATA", "utilisation": None, "remaining_capacity": None}
    utilisation = value / limit.amount
    status = ("BREACH" if utilisation > limit.hard_threshold else
              "LIMIT_REACHED" if math.isclose(utilisation, limit.hard_threshold, rel_tol=0, abs_tol=1e-12) else
              "WARNING" if utilisation >= limit.warning_threshold else "OK")
    return {**base, "status": status, "utilisation": utilisation,
            "exposure": value, "remaining_capacity": limit.amount - value}


def decision(checks):
    blocked = any(c.get("action") == "HARD_BLOCK" and c["status"] in {"BREACH", "MISSING_DATA"} for c in checks)
    approval = any(c.get("action") == "REQUIRE_APPROVAL" and c["status"] in {"WARNING", "LIMIT_REACHED", "BREACH", "MISSING_DATA"} for c in checks)
    order = ["BREACH", "MISSING_DATA", "LIMIT_REACHED", "WARNING", "NO_LIMIT", "OK", "NOT_APPLICABLE"]
    return {"status": next((s for s in order if any(c["status"] == s for c in checks)), "NOT_APPLICABLE"),
            "booking_allowed": not blocked and not approval, "requires_approval": approval, "hard_block": blocked}
