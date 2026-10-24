"""Indicative unadjusted-close observations, indexed by booked constituent."""
import math

from .market_policy import freshness


def _positive(value):
    if isinstance(value, bool):
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) and value > 0 else None


def watchlist_observations(underlyings, initial_levels, history, strike, asof):
    """Never compact missing constituents or infer extrema from current spots.

    Extrema include the official initial level and sampled post-strike closes.
    They do not certify a continuously observed contractual barrier.
    """
    dates = history.get("dates", [])
    indices = sorted((i for i, day in enumerate(dates) if strike <= day <= asof),
                     key=lambda i: dates[i])
    all_indices = sorted((i for i, day in enumerate(dates) if day <= asof),
                         key=lambda i: dates[i])
    rows = []
    for underlying in underlyings:
        name, ticker = underlying["name"], underlying.get("ticker", "")
        initial = _positive(initial_levels.get(name))
        row = dict(name=name, ticker=ticker, s0=initial, spot=None, perf=None,
                   min_perf=None, max_perf=None, effective_date=None,
                   current_status="UNAVAILABLE", extrema_status="UNAVAILABLE")
        rows.append(row)
        if strike > asof:
            row.update(current_status="STRIKE_PENDING", extrema_status="STRIKE_PENDING")
            continue
        if not initial or not ticker or history.get("error"):
            continue
        raw = history.get("prices", {}).get(ticker, [])
        valid = {i: _positive(raw[i]) for i in all_indices if i < len(raw)}
        observed = [i for i in all_indices if valid.get(i) is not None]
        if not observed:
            continue
        source_dates = history.get("source_observation_dates", {}).get(ticker)
        if source_dates and any(i >= len(source_dates) for i in observed):
            continue
        # A carried provider row dated today is older than an official fixing
        # received yesterday when its actual source close predates that fixing.
        last = max(observed, key=lambda i: (source_dates[i], dates[i])) if source_dates else observed[-1]
        effective = source_dates[last] if source_dates else history.get("effective_dates", {}).get(ticker) or dates[last]
        quality = freshness(effective, asof, "history")
        row.update(effective_date=effective, freshness=quality)
        if not quality["qualified"]:
            continue
        row.update(spot=valid[last], perf=valid[last] / initial, current_status="AVAILABLE")
        # No pre-strike fallback; no minimum over a partially missing window.
        # The common history can start late: never call that a since-strike path.
        if (not indices or not freshness(strike, dates[indices[0]], "history")["qualified"]
                or any(valid.get(i) is None for i in indices)
                or any(not freshness(dates[a], dates[b], "history")["qualified"]
                       for a, b in zip(indices, indices[1:]))):
            continue
        if source_dates and any(i >= len(source_dates) or source_dates[i] < strike for i in indices):
            continue
        path = [1.0] + [valid[i] / initial for i in indices]
        row.update(min_perf=min(path), max_perf=max(path), extrema_status="AVAILABLE")
    current_complete = bool(rows) and all(r["perf"] is not None for r in rows)
    extrema_complete = bool(rows) and all(r["min_perf"] is not None for r in rows)
    return dict(underlyings=rows,
        wof=min(r["perf"] for r in rows) if current_complete else None,
        bof=max(r["perf"] for r in rows) if current_complete else None,
        basket=sum(r["perf"] for r in rows) / len(rows) if current_complete else None,
        wof_min=min(r["min_perf"] for r in rows) if extrema_complete else None,
        bof_max=max(r["max_perf"] for r in rows) if extrema_complete else None,
        coverage=dict(total=len(rows), current_available=sum(r["perf"] is not None for r in rows),
                      extrema_available=sum(r["min_perf"] is not None for r in rows),
                      current_complete=current_complete, extrema_complete=extrema_complete))
