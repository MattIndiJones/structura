"""Resolve native terms once and restore their frozen contractual dates."""
from __future__ import annotations

import holidays

from ..calendar_budget import check_dates
from ..calendars import EXCHANGE_CALENDARS
from .models import CDSTerms, CLNTerms, ExoticTerms, IRSTerms, NativeProductTerms, NativeTerms, Product
from .native_schedule_models import NativeSchedule, ScheduleCalendarVersion, ScheduleContent, SchedulePreparation


_RESOLVER_VERSION = "native-schedule-v1"


def _missing_dates(terms: NativeTerms) -> tuple[str, ...]:
    fields = [(terms.effective_date, "date d’effet"), (terms.maturity_date, "date de maturité")]
    if isinstance(terms, CDSTerms):
        fields.append((terms.trade_date, "date de transaction"))
    return tuple(f"À préciser : {label}." for value, label in fields if value is None)


def _missing_economics(product: Product, terms: NativeTerms) -> tuple[str, ...]:
    fields = [(product.intent.nominal, "nominal")]
    if isinstance(terms, CDSTerms):
        fields.append((terms.premium_leg.coupon_bps, "coupon du CDS (pb)"))
    elif isinstance(terms, CLNTerms):
        fields.append((terms.fixed_leg.coupon_rate, "taux du coupon fixe de la CLN"))
    elif not isinstance(terms, ExoticTerms):
        fields.append((terms.floating_leg.margin_bps, "marge contractuelle de la jambe flottante (pb)"))
        if isinstance(terms, IRSTerms):
            fields.append((terms.fixed_leg.coupon_rate, "taux de la jambe fixe"))
    return tuple(f"À préciser : {label}." for value, label in fields if value is None)


def native_draft_diagnostics(product: Product) -> tuple[str, ...]:
    """Identify the incomplete fields supported by the retained native terms."""
    terms = product.terms
    if not isinstance(terms, NativeProductTerms):
        return ()
    return _missing_dates(terms) + _missing_economics(product, terms)


def _calendar_version(name: str) -> str:
    if name == "civil_days":
        return "act365f-civil-v1"
    if name == "weekdays_only":
        return "weekdays-v1"
    if name.upper() in EXCHANGE_CALENDARS:
        import exchange_calendars

        return f"exchange-calendars-{exchange_calendars.__version__}"
    return f"holidays-{holidays.__version__}"


def resolve_native_schedule(terms: NativeTerms, *, product_id: int | None = None,
                            terms_version: int | None = None) -> SchedulePreparation:
    diagnostics = _missing_dates(terms)
    if diagnostics:
        return SchedulePreparation(status="incomplete", diagnostics=diagnostics)

    if isinstance(terms, CDSTerms):
        from .cds_schedule import resolve_cds_schedule

        check_dates(terms.effective_date, terms.maturity_date, terms.trade_date)
        legs = resolve_cds_schedule(terms)
    elif isinstance(terms, CLNTerms):
        from .cln_schedule import resolve_cln_schedule

        legs = resolve_cln_schedule(terms)
    elif isinstance(terms, ExoticTerms):
        from .native_schedule_exotic import resolve_exotic_schedule

        check_dates(terms.effective_date, terms.maturity_date, terms.time_origin)
        legs = resolve_exotic_schedule(terms)
    else:
        from .rates_schedule import resolve_rates_schedule

        check_dates(terms.effective_date, terms.maturity_date)
        legs = resolve_rates_schedule(terms)
    calendars = {name for leg in legs for name in (leg.calendar, leg.fixing_calendar) if name is not None}
    versions = tuple(ScheduleCalendarVersion(calendar_id=name, version=_calendar_version(name)) for name in sorted(calendars))
    content = ScheduleContent(
        resolver_version=_RESOLVER_VERSION,
        instrument_type=terms.instrument_type,
        terms_fingerprint=terms.fingerprint,
        product_id=product_id,
        terms_version=terms_version,
        calendar_versions=versions,
        legs=legs,
    )
    return SchedulePreparation(status="ready", schedule=NativeSchedule.seal(content))


def read_native_schedule(product: Product) -> SchedulePreparation:
    if product.native_schedule is not None:
        return SchedulePreparation(
            status="ready", schedule=product.native_schedule, diagnostics=native_draft_diagnostics(product),
        )
    date_diagnostics = _missing_dates(product.terms)
    diagnostics = date_diagnostics + _missing_economics(product, product.terms)
    if date_diagnostics:
        return SchedulePreparation(status="incomplete", diagnostics=diagnostics)
    return SchedulePreparation(status="not_prepared", diagnostics=("Échéancier figé indisponible.", *diagnostics))
