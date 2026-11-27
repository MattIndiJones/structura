"""Civil ACT/365F schedule projection of the contractual exotic pricing axis."""

from dataclasses import dataclass
from datetime import date, timedelta
from math import floor, isclose

from .exotic_rates_calendar import RatesContractDates
from .models import ExoticTerms
from .native_schedule_models import ScheduleEvent, ScheduleLeg


@dataclass(frozen=True)
class _EventTime:
    event_id: str
    kind: str
    time: float
    flow_id: str | None = None


def _rates_times(contract: dict) -> tuple[tuple[_EventTime, ...], float]:
    events = []
    for flow in contract["cashflows"]:
        key, kind = flow["flow_id"], flow["kind"]
        events.append(_EventTime(f"{key}:payment", "cashflow", flow["payment"], key))
        if kind == "rate":
            events.append(_EventTime(f"{key}:fixing", "observation", flow["fixing"], key))
        elif kind == "range_accrual":
            events.extend(_EventTime(f"{key}:observation:{index}", "observation", observation["time"], key)
                          for index, observation in enumerate(flow["observations"], start=1))
    for exercise in contract.get("exercises", ()):
        key = exercise["exercise_id"]
        events.extend((_EventTime(f"{key}:decision", "exercise", exercise["decision"], key),
                       _EventTime(f"{key}:settlement", "exercise_settlement", exercise["settlement"], key)))
    return tuple(events), max(flow["payment"] for flow in contract["cashflows"])


def _credit_times(contract: dict) -> tuple[tuple[_EventTime, ...], float]:
    maturity = contract["maturity_years"]
    events = [_EventTime("protection:start", "step_in", contract.get("protected_from", 0.)),
              _EventTime("protection:end", "protection_end", maturity)]
    for index, coupon in enumerate(contract["coupons"], start=1):
        flow = f"credit-coupon-{index}"
        observation = coupon.get("observation")
        events.extend((_EventTime(f"{flow}:start", "accrual_start", coupon["start"], flow),
                       _EventTime(f"{flow}:end", "accrual_end", coupon["end"], flow),
                       _EventTime(f"{flow}:observation", "observation", coupon["end"] if observation is None else observation, flow),
                       _EventTime(f"{flow}:payment", "cashflow", coupon["payment"], flow)))
    if contract["kind"] == "cln":
        events.append(_EventTime("principal:payment", "principal", contract.get("principal_payment_years") or maturity, "principal"))
    return tuple(events), maturity


def _event_times(instrument: str, contract: dict) -> tuple[tuple[_EventTime, ...], float]:
    return _rates_times(contract) if instrument == "EXOTIC_RATES" else _credit_times(contract)


def _civil_day(origin: date, time: float) -> tuple[date, bool]:
    days = time * 365
    offset = floor(days + .5)
    return origin + timedelta(days=offset), isclose(days, offset, rel_tol=0, abs_tol=1e-8)


def _explicit_rates_dates(instrument: str, origin: date, contract: dict) -> RatesContractDates | None:
    if instrument != "EXOTIC_RATES" or contract.get("contract_dates") is None:
        return None
    dates = RatesContractDates.model_validate(contract["contract_dates"])
    if dates.time_origin != origin:
        raise ValueError("L’origine du calendrier doit coïncider avec l’origine du modèle ACT/365F.")
    return dates


def exotic_term_dates(instrument: str, origin: date, contract: dict) -> tuple[date, date]:
    dates = _explicit_rates_dates(instrument, origin, contract)
    if dates is not None:
        return dates.start_date, dates.end_date
    events, maturity = _event_times(instrument, contract)
    start = min(0., *(event.time for event in events))
    return _civil_day(origin, start)[0], _civil_day(origin, maturity)[0]


def resolve_exotic_schedule(terms: ExoticTerms) -> tuple[ScheduleLeg, ...]:
    contract = terms.contract.to_dict()
    events, _ = _event_times(terms.instrument_type, contract)
    if (terms.effective_date, terms.maturity_date) != exotic_term_dates(terms.instrument_type, terms.time_origin, contract):
        raise ValueError("Les dates du Product contredisent l’origine ACT/365F figée du contrat exotique.")
    dates = _explicit_rates_dates(terms.instrument_type, terms.time_origin, contract)
    if dates is not None:
        events += tuple(
            _EventTime(f"{period.flow_id}:{suffix}", kind, dates.time(day), period.flow_id)
            for period in dates.accrual_periods
            for suffix, kind, day in (("accrual-start", "accrual_start", period.start_date),
                                      ("accrual-end", "accrual_end", period.end_date))
        )
    dated = []
    for event in sorted(events, key=lambda item: (item.time, item.event_id)):
        day, exact = (dates.at(event.time), True) if dates is not None else _civil_day(terms.time_origin, event.time)
        dated.append(ScheduleEvent(event_id=event.event_id, kind=event.kind, date=day, flow_id=event.flow_id,
                                   model_time_years=event.time, date_projection="exact" if exact else "nearest_calendar_day"))
    return (ScheduleLeg(leg_id="exotic-contract", kind="exotic_contract", calendar="civil_days", events=tuple(dated)),)
