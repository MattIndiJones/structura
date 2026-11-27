"""Independent market inputs and published acceptance levels of the research rolls."""
from __future__ import annotations

from datetime import date, datetime, time
from math import exp
from zoneinfo import ZoneInfo

from backend.app.core.product.credit_pilot import benchmark_terms, july_facts, july_prior_payment
from backend.app.core.product.models import Product
from backend.app.core.product.native_schedule import resolve_native_schedule
from backend.app.core.product.native_schedule_models import NativeSchedule
from backend.app.core.product.rates_market import CurvePillar, RatesSource
from backend.app.core.product.rates_pilot import pilot_market, pilot_payment, pilot_terms


_PARIS = ZoneInfo("Europe/Paris")


def terms_for(vintage: str):
    if vintage.startswith("frn"):
        terms = pilot_terms()[0]
        if vintage == "frn-next":
            terms = terms.model_copy(update={"effective_date": date(2026, 12, 21), "maturity_date": date(2028, 12, 21)})
        return terms
    terms = benchmark_terms("CLN", "JULY-DUE")
    if vintage == "cln-next":
        return terms.model_copy(update={"effective_date": date(2021, 7, 21), "maturity_date": date(2022, 7, 21),
                                        "reference_entity_id": "synthetic-replacement-reference"})
    return terms.model_copy(update={"maturity_date": date(2022, 3, 21)})


def product_for(terms, schedule: dict, *, nominal=1_000_000.0) -> Product:
    return Product(terms=terms, intent={"nominal": nominal, "side": "BUY"},
                   native_schedule=NativeSchedule.model_validate(schedule))


def frn_market(case: str, product: Product) -> tuple[dict, str]:
    market, cutoff = pilot_market("C" if case in ("C-open", "D") else case)
    if case == "C-open":
        cutoff = cutoff.replace(hour=11, minute=59, second=59)
    elif case == "D":
        cutoff = cutoff.replace(day=22)

    if product.terms.effective_date == date(2026, 12, 21):
        anchor, terminal = cutoff.date(), product.terms.maturity_date
        market_id = f"eur-frn-irs-abc-roll-{anchor.isoformat()}-v1"
        clock = datetime.combine(anchor, time(9), _PARIS)
        curves = {}
        for name, source, rate in (("discount", market.discount, .02), ("projection", market.projection, .025)):
            factor = exp(-rate * (terminal - anchor).days / 365)
            curves[name] = source.model_copy(update={
                "curve_id": f"{market_id}-{name}", "anchor_date": anchor,
                "pillars": (CurvePillar(date=anchor, factor=1), CurvePillar(date=terminal, factor=factor)),
                "available_at": clock, "validated_at": clock,
            })
        market = market.model_copy(update={"market_id": market_id, "market_date": anchor, **curves})
    else:
        confirmation = pilot_payment(product, equivalent_payoff=True)
        assert confirmation is not None
        market = market.model_copy(update={"payments": (confirmation,)})
    return market.model_dump(mode="json"), cutoff.isoformat()


def cln_market(day: int, product: Product, *, case: str = "normal") -> tuple[dict, str]:
    valuation_date = date(2021, 7, day)
    timestamp = datetime.combine(valuation_date, time(8), _PARIS)
    cutoff = datetime.combine(valuation_date, time(16), _PARIS)
    market_id = f"eur-cln-flat-{product.terms.reference_entity_id}-{valuation_date.isoformat()}-{case}"
    market = {
        "kind": "cln_research", "market_id": market_id, "market_version": 1,
        "market_date": valuation_date.isoformat(), "reference_entity_id": product.terms.reference_entity_id,
        "source": RatesSource(kind="synthetic", provider="structura-fixture", reference=market_id).model_dump(mode="json"),
        "available_at": timestamp.isoformat(), "validated_at": timestamp.isoformat(),
        "ois_rate": .02, "funding_bps": 0.0, "hazard_rate": .02, "pricing_recovery_fraction": .40,
    }
    if product.terms.effective_date != date(2021, 7, 21):
        default_id, facts = july_facts("JULY-ZERO" if case == "zero" else "JULY-PAID")
        if case == "late_payment":
            facts = (*facts[:-1], facts[-1].model_copy(update={
                "available_at": datetime.fromisoformat("2021-07-21T12:00:00+02:00"),
            }))
        if case == "late_notice":
            notice = facts[0].model_copy(update={"available_at": datetime.fromisoformat("2021-07-16T10:00:00+02:00")})
            facts = (notice, *facts[1:])
        market.update(default_id=default_id, credit_facts=[fact.model_dump(mode="json") for fact in facts],
                      settlement_date="2021-07-20", payments=[july_prior_payment(product).model_dump(mode="json")])
    return market, cutoff.isoformat()


def build_roll_plan(instrument: str, *, daily: bool = False) -> dict:
    prefix = instrument.lower()
    names = (f"{prefix}-first", f"{prefix}-next")
    products = {}
    vintages = []
    for name in names:
        terms = terms_for(name)
        schedule = resolve_native_schedule(terms).schedule
        products[name] = product_for(terms, schedule.model_dump(mode="json"))
        vintages.append({"millesime_id": name, "terms_version": 1,
                         "terms": terms.model_dump(mode="json"), "intent": {"nominal": 1_000_000.0, "side": "BUY"}})

    def session(day_or_case, requests, *, replace=None, sell=False):
        jobs = []
        for operation, vintage in requests:
            product = products[vintage]
            market, cutoff = frn_market(day_or_case, product) if instrument == "FRN" else cln_market(day_or_case, product)
            jobs.append({"operation": operation, "job_id": f"{vintage}-{operation}-{day_or_case}",
                         "millesime_id": vintage, "market": market})
        return {"day": cutoff[:10], "cutoff": cutoff, "jobs": jobs,
                "roll": None if replace is None else {"replacement_millesime_id": replace, "sell_held": sell}}

    first, replacement = names
    if instrument == "FRN":
        sessions = [session("A", (("issue", first),)), session("B", (("mtm", first),)),
                    session("C", (("mtm", first), ("issue", replacement)), replace=replacement, sell=True),
                    session("D", (("mtm", replacement),))]
    else:
        sessions = [session(14, (("issue", first),))]
        if daily:
            sessions.extend(session(day, (("mtm", first),)) for day in (15, 16))
        sessions.extend([session(19, (("mtm", first),)), session(20, (("mtm", first),), replace=replacement),
                         session(21, (("issue", replacement),), replace=replacement), session(22, (("mtm", replacement),))])
    coverage = "daily" if daily else "selected"
    return {"run_id": f"{prefix}-roll-{coverage}-v1", "instrument_type": instrument, "coverage": coverage,
            "initial_nominal_eur": 1_000_000.0, "initial_cash_reserve_eur": 0.0, "sessions": sessions, "millesimes": vintages}


# Independent figures from the methodology, used only as comparison oracles.
FRN_LEVELS = (100.00000000, 100.41130445, 100.76105013, 100.76657144)
FRN_NAVS = (1_029_418.96, 1_033_653.01, 1_037_253.36, 1_037_310.19)
CLN_LEVELS = (100.00000000, 34.71382597, 34.71572815, 34.71572815, 34.71877827)
CLN_NAVS = (1_008_188.56, 349_980.82, 350_000.00, 350_000.00, 350_030.75)
