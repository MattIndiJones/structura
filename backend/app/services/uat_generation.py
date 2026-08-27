"""Deterministic Admin generator for RFQ -> booking UAT data.

The generator deliberately calls the production RFQ and booking functions.
It does not write a parallel approximation of the workflow.  Synthetic rows
are tagged with an explicit batch id, making preview reproducible and cleanup
strictly scoped to data created by this service.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import random
import uuid
from datetime import date, datetime, timedelta
from typing import Literal

from fastapi import HTTPException

from ..core.calendars import (
    BusinessDayConvention, add_business_days, adjust,
)
from pydantic import BaseModel, Field
from sqlalchemy import delete, update
from sqlmodel import Session, select

from ..api import deals as deals_api
from ..api import rfq as rfq_api
from ..core.audit import record_audit_event
from ..core.compute.executor import run_batch
from ..core.workflow import DataCategory
from ..db.models import (
    Alert, Counterparty, Deal, DealContractVersion, DealEvent,
    Document, EmtRecord, KidRecord, LifecycleProposal, OfficialFixingVersion,
    RfqProvider, RfqQuote, RfqRequest, ShockRun, TradeAmendmentRequest,
    UatGenerationBatch, User,
)


PRODUCTS = {
    "ATHENA": "Autocall Athena",
    "PHOENIX": "Phoenix Mémoire",
    "REVERSE_CONVERTIBLE": "Reverse Convertible",
    "CAPITAL_GUARANTEED": "Capital Garanti",
}

UNDERLYINGS = [
    {"ticker": "^STOXX50E", "name": "Euro Stoxx 50", "ccy": "EUR", "s0": 5200.0,
     "sigma": 0.18, "q": 0.025},
    {"ticker": "^GSPC", "name": "S&P 500", "ccy": "USD", "s0": 5600.0,
     "sigma": 0.16, "q": 0.015},
    {"ticker": "^NDX", "name": "Nasdaq 100", "ccy": "USD", "s0": 19500.0,
     "sigma": 0.20, "q": 0.006},
    {"ticker": "AAPL", "name": "Apple", "ccy": "USD", "s0": 225.0,
     "sigma": 0.22, "q": 0.005},
    {"ticker": "MSFT", "name": "Microsoft", "ccy": "USD", "s0": 430.0,
     "sigma": 0.20, "q": 0.008},
    {"ticker": "MC.PA", "name": "LVMH", "ccy": "EUR", "s0": 650.0,
     "sigma": 0.26, "q": 0.020},
]

# Paths per UAT pricing run. The probe that motivated real pricing measured a
# 95% half-width around 0.1 to 0.3 point of notional here — far finer than a
# fixture needs, while keeping a deal under ~5 s so a batch stays bearable.
UAT_PRICING_PATHS = 20_000

MODES = ("RFQ_ONLY", "BOOKED_ONLY", "FULL_CHAIN")
RFQ_PROFILES = ("EXECUTABLE", "CONTROL_MIX")

LIFECYCLE_PROFILES = {
    "CURRENT_ACTIVE": "Trade récent — actif",
    "FORWARD_START": "Forward start à 3 mois",
    "ACTIVE_1Y_PENDING": "Trade ancien 1 an — fixings en attente",
    "ACTIVE_2Y_OFFICIAL": "Trade ancien 2 ans — fixings officialisés",
    "MATURED_PENDING": "Maturité passée — traitement en attente",
    "CALLED": "Rappel anticipé appliqué",
    "MATURED_FINAL": "Maturité remboursée sans KI",
    "MATURED_KI": "Maturité avec perte KI",
}
LIFECYCLE_PROFILE_KEYS = tuple(LIFECYCLE_PROFILES)
TERMINAL_PROFILES = {"CALLED", "MATURED_FINAL", "MATURED_KI"}
CALLABLE_PRODUCTS = {"ATHENA", "PHOENIX"}
KI_PRODUCTS = {"ATHENA", "PHOENIX", "REVERSE_CONVERTIBLE"}


class UatGenerationRequest(BaseModel):
    target_user_id: int
    mode: Literal["RFQ_ONLY", "BOOKED_ONLY", "FULL_CHAIN"] = "FULL_CHAIN"
    count: int = Field(default=5, ge=1, le=100)
    seed: int = Field(default=42, ge=0, le=2_147_483_647)
    label: str = Field(default="", max_length=120)
    product_types: list[str] = Field(default_factory=lambda: list(PRODUCTS))
    underlying_tickers: list[str] = Field(
        default_factory=lambda: [item["ticker"] for item in UNDERLYINGS])
    min_underlyings: int = Field(default=1, ge=1, le=3)
    max_underlyings: int = Field(default=2, ge=1, le=3)
    maturity_min_years: float = Field(default=1.0, ge=0.25, le=10.0)
    maturity_max_years: float = Field(default=5.0, ge=0.25, le=10.0)
    nominal_min: float = Field(default=100_000.0, gt=0, le=100_000_000.0)
    nominal_max: float = Field(default=2_000_000.0, gt=0, le=100_000_000.0)
    currencies: list[str] = Field(default_factory=lambda: ["EUR"])
    fixing_policy: Literal["AUTO_YAHOO", "FOUR_EYES", "MIX"] = "AUTO_YAHOO"
    quotes_per_rfq: int = Field(default=2, ge=1, le=5)
    # None means "use every mapped active provider" for CLI/backward callers.
    # An explicit [] from the Admin form means the operator selected none and
    # must be rejected rather than silently restored to every provider.
    provider_ids: list[int] | None = None
    rfq_profile: Literal["EXECUTABLE", "CONTROL_MIX"] = "EXECUTABLE"
    lifecycle_profile: Literal[
        "CURRENT_ACTIVE", "FORWARD_START", "ACTIVE_1Y_PENDING",
        "ACTIVE_2Y_OFFICIAL", "MATURED_PENDING", "CALLED",
        "MATURED_FINAL", "MATURED_KI", "COMPLETE_MIX",
    ] = "CURRENT_ACTIVE"


def _utc_iso(value: datetime) -> str:
    return value.replace(microsecond=0).isoformat() + "Z"


def _batch_row(batch: UatGenerationBatch, session: Session) -> dict:
    creator = session.get(User, batch.created_by)
    target = session.get(User, batch.target_user_id)
    try:
        result = json.loads(batch.result_json or "{}")
    except ValueError:
        result = {}
    return {
        "id": batch.id,
        "batch_key": batch.batch_key,
        "label": batch.label,
        "created_by": creator.username if creator else str(batch.created_by),
        "target_user_id": batch.target_user_id,
        "target_user": target.username if target else str(batch.target_user_id),
        "mode": batch.mode,
        "seed": batch.seed,
        "requested_count": batch.requested_count,
        "rfq_count": batch.rfq_count,
        "deal_count": batch.deal_count,
        "status": batch.status,
        "result": result,
        "error_message": batch.error_message,
        "created_at": batch.created_at.isoformat(),
        "completed_at": batch.completed_at.isoformat() if batch.completed_at else None,
        "deleted_at": batch.deleted_at.isoformat() if batch.deleted_at else None,
    }


def list_batches(session: Session) -> list[dict]:
    batches = session.exec(
        select(UatGenerationBatch).order_by(UatGenerationBatch.created_at.desc())
    ).all()
    return [_batch_row(batch, session) for batch in batches]


def generator_config(session: Session) -> dict:
    users = session.exec(
        select(User).where(User.is_active == True).order_by(User.username)  # noqa: E712
    ).all()
    counterparties = {
        c.id: c for c in session.exec(
            select(Counterparty).where(Counterparty.active == True)  # noqa: E712
        ).all()
    }
    providers = session.exec(
        select(RfqProvider).where(RfqProvider.active == True)  # noqa: E712
        .order_by(RfqProvider.label)
    ).all()
    # An executable UAT RFQ must be bookable. Unmapped providers remain in the
    # normal Admin catalog, but are not offered by this success-path generator.
    provider_rows = []
    for provider in providers:
        cpty = counterparties.get(provider.counterparty_id)
        if not cpty:
            cpty = next((c for c in counterparties.values()
                         if c.name.casefold() == provider.label.casefold()), None)
        if cpty:
            provider_rows.append({
                "id": provider.id,
                "label": provider.label,
                "counterparty": cpty.name,
            })
    return {
        "users": [{"id": user.id, "username": user.username, "role": user.role}
                  for user in users],
        "providers": provider_rows,
        "products": [{"key": key, "label": label} for key, label in PRODUCTS.items()],
        "underlyings": UNDERLYINGS,
        "lifecycle_profiles": [
            {"key": key, "label": label}
            for key, label in LIFECYCLE_PROFILES.items()
        ],
        "limits": {"max_count": 100, "max_quotes_per_rfq": 5},
    }


def _validate_request(body: UatGenerationRequest, session: Session) -> tuple[User, list[dict]]:
    target = session.get(User, body.target_user_id)
    if not target or not target.is_active:
        raise HTTPException(422, "Le compte destinataire est introuvable ou inactif.")
    if body.min_underlyings > body.max_underlyings:
        raise HTTPException(422, "Le minimum de sous-jacents dépasse le maximum.")
    if body.maturity_min_years > body.maturity_max_years:
        raise HTTPException(422, "La maturité minimale dépasse la maturité maximale.")
    if body.nominal_min > body.nominal_max:
        raise HTTPException(422, "Le nominal minimum dépasse le nominal maximum.")
    unknown_products = sorted(set(body.product_types) - set(PRODUCTS))
    if not body.product_types or unknown_products:
        detail = ("Sélectionnez au moins une famille de produit." if not body.product_types
                  else "Familles inconnues : " + ", ".join(unknown_products) + ".")
        raise HTTPException(422, detail)
    known_tickers = {item["ticker"] for item in UNDERLYINGS}
    unknown_tickers = sorted(set(body.underlying_tickers) - known_tickers)
    if not body.underlying_tickers or unknown_tickers:
        detail = ("Sélectionnez au moins un sous-jacent." if not body.underlying_tickers
                  else "Sous-jacents inconnus : " + ", ".join(unknown_tickers) + ".")
        raise HTTPException(422, detail)
    if body.max_underlyings > len(set(body.underlying_tickers)):
        raise HTTPException(
            422, "Le nombre maximal de sous-jacents dépasse la sélection disponible.")
    invalid_ccy = sorted({ccy for ccy in body.currencies
                          if len(ccy) != 3 or not ccy.isalpha()})
    if not body.currencies or invalid_ccy:
        raise HTTPException(422, "Les devises doivent être des codes ISO à trois lettres.")

    requested_profiles = (
        set(LIFECYCLE_PROFILE_KEYS)
        if body.lifecycle_profile == "COMPLETE_MIX"
        else {body.lifecycle_profile}
    )
    periodic_profiles = {
        "ACTIVE_1Y_PENDING", "ACTIVE_2Y_OFFICIAL", "CALLED",
    }
    if requested_profiles & periodic_profiles \
            and not (set(body.product_types) & CALLABLE_PRODUCTS):
        raise HTTPException(
            422, "Les profils historiques à constatations périodiques nécessitent "
                 "Athena ou Phoenix.")
    if "MATURED_KI" in requested_profiles and not (set(body.product_types) & KI_PRODUCTS):
        raise HTTPException(
            422, "Le profil « maturité KI » nécessite Athena, Phoenix ou Reverse Convertible.")
    minimum_tenor = 3.0 if requested_profiles & {"ACTIVE_2Y_OFFICIAL", "CALLED"} else (
        2.0 if "ACTIVE_1Y_PENDING" in requested_profiles else 0.25)
    if set(body.product_types) & CALLABLE_PRODUCTS:
        minimum_tenor = max(minimum_tenor, 0.5)
    if body.maturity_max_years < minimum_tenor:
        raise HTTPException(
            422, f"Ce profil historique nécessite une maturité maximale d'au moins "
                 f"{minimum_tenor:g} ans.")

    config = generator_config(session)
    available = {row["id"]: row for row in config["providers"]}
    if body.provider_ids is not None:
        missing = sorted(set(body.provider_ids) - set(available))
        if missing:
            raise HTTPException(
                422, "Fournisseurs non bookables ou inconnus : "
                     + ", ".join(map(str, missing)) + ".")
        providers = [available[provider_id] for provider_id in body.provider_ids]
    else:
        providers = list(available.values())
    if body.mode in {"RFQ_ONLY", "FULL_CHAIN"} and len(providers) < body.quotes_per_rfq:
        raise HTTPException(
            422, f"{body.quotes_per_rfq} fournisseurs distincts sont requis, "
                 f"mais seulement {len(providers)} sont sélectionnés et reliés à une "
                 "contrepartie active.")
    has_active_counterparty = session.exec(
        select(Counterparty).where(Counterparty.active == True)  # noqa: E712
    ).first() is not None
    if body.mode == "BOOKED_ONLY" and not providers and not has_active_counterparty:
        raise HTTPException(422, "Aucune contrepartie active n'est disponible.")
    return target, providers


def _quarter_year(rng: random.Random, low: float, high: float) -> float:
    raw = rng.uniform(low, high)
    return min(high, max(low, round(raw * 4) / 4))


def _profile_for_index(body: UatGenerationRequest, index: int) -> str:
    if body.lifecycle_profile != "COMPLETE_MIX":
        return body.lifecycle_profile
    return LIFECYCLE_PROFILE_KEYS[(index - 1) % len(LIFECYCLE_PROFILE_KEYS)]


def _family_for_profile(
    rng: random.Random,
    product_types: list[str],
    profile: str,
) -> str:
    eligible = list(product_types)
    if profile in {"ACTIVE_1Y_PENDING", "ACTIVE_2Y_OFFICIAL", "CALLED"}:
        eligible = [family for family in eligible if family in CALLABLE_PRODUCTS]
    elif profile == "MATURED_KI":
        eligible = [family for family in eligible if family in KI_PRODUCTS]
    if not eligible:
        raise ValueError(f"Aucune famille compatible avec le profil {profile}.")
    return rng.choice(eligible)


def _profile_tenor_floor(profile: str, family: str) -> float:
    floor = 0.5 if family in CALLABLE_PRODUCTS else 0.25
    if profile == "ACTIVE_1Y_PENDING":
        floor = max(floor, 2.0)
    elif profile == "ACTIVE_2Y_OFFICIAL":
        floor = max(floor, 3.0)
    elif profile == "CALLED":
        floor = max(floor, 3.0)
    return floor


def _to_business_day(value: date, currency: str = "EUR") -> date:
    """Snap a generated date back to the nearest preceding business day.

    _profile_dates is pure calendar arithmetic, so roughly two dates in seven
    used to land on a weekend — and a strike on Sunday 2023-08-06 has no close
    on any index, so its fixing can never be resolved, automatically or
    manually: the deal is born stuck. Rolling *backwards* rather than forwards
    keeps a maturity inside its own schedule instead of pushing it past its
    payment date.

    Public holidays are now handled: the settlement calendar of the currency
    says which days are closed, TARGET for the euro. The previous version only
    skipped weekends, and generated fixtures whose strike fell on Christmas."""
    return adjust(value, currency, BusinessDayConvention.PRECEDING)


def _profile_dates(profile: str, tenor: float, today: date) -> tuple[date, date, date]:
    # Historical anchors are pushed a few days past the round anniversary. An
    # exact multiple of 365 makes the annual observation schedule land back on
    # today's date, and today has no close published yet — so that observation
    # came back as a YAHOO_CLOSE_NOT_PUBLISHED exception and stayed empty,
    # which is the same trap a same-day strike falls into.
    _CLEAR = 5
    if profile == "FORWARD_START":
        strike = today + timedelta(days=90)
        trade = today
    elif profile == "ACTIVE_1Y_PENDING":
        strike = today - timedelta(days=365 + _CLEAR)
        trade = strike
    elif profile == "ACTIVE_2Y_OFFICIAL":
        strike = today - timedelta(days=2 * 365 + _CLEAR)
        trade = strike
    elif profile == "CALLED":
        # Two elapsed years guarantee at least one truly reached observation,
        # including an annual schedule whose first resolved date is shifted by
        # the contract-calendar resolver.
        strike = today - timedelta(days=2 * 365 + _CLEAR)
        trade = strike
    elif profile in {"MATURED_PENDING", "MATURED_FINAL", "MATURED_KI"}:
        strike = today - timedelta(days=round((tenor + 0.25) * 365.25))
        trade = strike
    elif profile == "CURRENT_ACTIVE":
        # Struck one business day back, but traded today. A deal struck *today*
        # has no close to fix S0 against until tonight, so this fixture arrived
        # — and stayed, all session — with every constatation empty and nothing
        # an operator could do about it. The trade date has to stay today
        # though: _age_generated_records only ages an RFQ whose trade is in the
        # past, so this profile is also what keeps a fresh, bookable RFQ in the
        # control mix. Moving both broke that.
        strike = today - timedelta(days=1)
        trade = today
    else:
        strike = today
        trade = today
    strike = _to_business_day(strike)
    trade = _to_business_day(trade)
    maturity = _to_business_day(strike + timedelta(days=round(tenor * 365.25)))
    return trade, strike, maturity


def _phoenix_period_coupon(coupon: float, period_years: float) -> float:
    """Phoenix coupon actually paid at ONE observation, from an annual rate.

    The Phoenix pays `CPN * COUPON` at *every* observation, so an un-scaled
    coupon makes the price a function of the observation frequency rather
    than of the product's economics: the same drawn 12% priced 110% annually,
    139% semi-annually and 183% quarterly. Athena and Reverse Convertible
    need no such scaling — they pay once (at call, then STOP; at maturity)
    and are already frequency-invariant."""
    return coupon * period_years


def _product_script(family: str, coupon: float, ac_bar: float,
                    coupon_bar: float, ki_bar: float, participation: float,
                    period_years: float = 1.0) -> str:
    if family == "ATHENA":
        return f"""PARAM COUPON = {coupon:.2f}%
PARAM M_AC_BAR = {ac_bar:.2f}%
PARAM M_KI_BAR = {ki_bar:.2f}%
CONSTAT() OBSERVATIONS
AT OBSERVATIONS:
  SET CALL = INDIC(WOF >= M_AC_BAR)
  PAY CALL * COUPON
  PAY CALL * 1
  IF CALL = 1:
    STOP
AT MATURITY:
  SET KI = INDIC(WOF < M_KI_BAR)
  PAY (1 - KI) * 1
  PAY KI * WOF
"""
    if family == "PHOENIX":
        period_coupon = _phoenix_period_coupon(coupon, period_years)
        return f"""PARAM COUPON = {period_coupon:.4f}%  # {coupon:.2f}% p.a. sur {period_years:.2f} an
PARAM M_AC_BAR = {ac_bar:.2f}%
PARAM M_CPN_BAR = {coupon_bar:.2f}%
PARAM M_KI_BAR = {ki_bar:.2f}%
CONSTAT() OBSERVATIONS
AT OBSERVATIONS:
  SET CALL = INDIC(WOF >= M_AC_BAR)
  SET CPN = INDIC(WOF >= M_CPN_BAR)
  PAY CPN * COUPON
  PAY CALL * 1
  IF CALL = 1:
    STOP
AT MATURITY:
  SET KI = INDIC(WOF < M_KI_BAR)
  PAY (1 - KI) * 1
  PAY KI * WOF
"""
    if family == "REVERSE_CONVERTIBLE":
        return f"""PARAM COUPON = {coupon:.2f}%
PARAM M_KI_BAR = {ki_bar:.2f}%
CONSTAT OBSERVATIONS
AT OBSERVATIONS:
  SET KI = INDIC(WOF < M_KI_BAR)
  PAY COUPON
  PAY (1 - KI) * 1
  PAY KI * WOF
"""
    return f"""PARAM M_PARTICIPATION = {participation:.2f}%
CONSTAT OBSERVATIONS
AT OBSERVATIONS:
  PAY 1
  PAY MAX(0, WOF - 1) * M_PARTICIPATION
"""


def _build_specs(body: UatGenerationRequest) -> list[dict]:
    rng = random.Random(body.seed)
    universe = [item for item in UNDERLYINGS if item["ticker"] in body.underlying_tickers]
    today = date.today()
    specs = []
    for index in range(1, body.count + 1):
        lifecycle_profile = _profile_for_index(body, index)
        family = _family_for_profile(rng, body.product_types, lifecycle_profile)
        tenor_floor = _profile_tenor_floor(lifecycle_profile, family)
        maturity_years = _quarter_year(
            rng, max(body.maturity_min_years, tenor_floor),
            body.maturity_max_years)
        trade, strike, maturity = _profile_dates(
            lifecycle_profile, maturity_years, today)
        if family in {"ATHENA", "PHOENIX"}:
            frequency_choices = (3, 6) if lifecycle_profile == "ACTIVE_1Y_PENDING" \
                else (3, 6, 12)
            frequency_months = rng.choice([
                months for months in frequency_choices
                if months / 12 < maturity_years
            ])
            frequency = {3: "3M", 6: "6M", 12: "1Y"}[frequency_months]
            first = strike + timedelta(
                days=round(frequency_months * 365.25 / 12))
        else:
            frequency_months = 12
            frequency = "1Y"
            first = maturity
        period_years = frequency_months / 12
        count_underlyings = rng.randint(body.min_underlyings, body.max_underlyings)
        selected_underlyings = [dict(item) for item in rng.sample(universe, count_underlyings)]
        nominal = round(rng.uniform(body.nominal_min, body.nominal_max) / 10_000) * 10_000
        currency = rng.choice(body.currencies).upper()
        coupon = round(rng.uniform(5.0, 12.0), 2)
        ac_bar = float(rng.choice([90, 95, 100, 105]))
        coupon_bar = float(rng.choice([60, 70, 80]))
        ki_bar = float(rng.choice([50, 55, 60, 65, 70]))
        participation = float(rng.choice([80, 90, 100, 110, 120]))
        script = _product_script(
            family, coupon, ac_bar, coupon_bar, ki_bar, participation,
            period_years)
        if family == "ATHENA":
            user_params = {
                "COUPON": coupon / 100,
                "M_AC_BAR": ac_bar / 100,
                "M_KI_BAR": ki_bar / 100,
            }
        elif family == "PHOENIX":
            # Annualised: the drawn coupon is a yearly rate, the script pays
            # its per-observation share. Must match _product_script's PARAM.
            user_params = {
                "COUPON": _phoenix_period_coupon(coupon, period_years) / 100,
                "M_AC_BAR": ac_bar / 100,
                "M_CPN_BAR": coupon_bar / 100,
                "M_KI_BAR": ki_bar / 100,
            }
        elif family == "REVERSE_CONVERTIBLE":
            user_params = {
                "COUPON": coupon / 100,
                "M_KI_BAR": ki_bar / 100,
            }
        else:
            user_params = {"M_PARTICIPATION": participation / 100}
        # Deux jours ouvrés pour le règlement initial, cinq pour le final :
        # les usages les plus courants sur notes structurées EUR et CHF.
        value_date = add_business_days(strike, 2, currency)
        # Trois jours ouvres apres la derniere constatation : l usage courant.
        payment_date = add_business_days(maturity, 3, currency)
        constat_value = ({
            "start_date": first.isoformat(),
            "end_date": maturity.isoformat(),
            "roll_date": first.isoformat(),
            "frequency": frequency,
            "stub": "short_last",
            # Une constatation tombant un jour fermé passe au jour ouvré
            # suivant, et son coupon est réglé trois jours ouvrés plus tard.
            "convention": "following",
            "settlement_lag": 3,
        } if family in {"ATHENA", "PHOENIX"} else {
            "date": maturity.isoformat(),
            "convention": "following",
            "settlement_lag": 3,
        })
        params = {
            "underlyings": selected_underlyings,
            "user_params": user_params,
            "constats": {"OBSERVATIONS": constat_value},
            "notional": float(nominal),
            "currency": currency,
            "strike_date": strike.isoformat(),
            # Le cash s'échange deux jours ouvrés après la constatation
            # initiale — l'usage sur note structurée. Poser value = strike
            # décrivait un règlement le jour même, qui n'existe pas.
            "value_date": value_date.isoformat(),
            "payment_date": payment_date.isoformat(),
            # T est l'horizon de DIFFUSION : de la constatation initiale à la
            # dernière constatation.
            "T": round((maturity - strike).days / 365.25, 6),
            "model": "constant",
            "r": round(rng.uniform(0.015, 0.045), 4),
            "corr_matrix": [[1.0 if i == j else 0.45
                             for j in range(count_underlyings)]
                            for i in range(count_underlyings)],
        }
        fixing_policy = (rng.choice(["AUTO_YAHOO", "FOUR_EYES"])
                         if body.fixing_policy == "MIX" else body.fixing_policy)
        # Resolved and system-officialized fixtures exercise the production
        # AUTO_YAHOO transition; the pending ones exercise the human path and
        # are forced the other way, because a deliberately unresolved fixing on
        # an automatic deal is a contradiction, not a test case.
        if lifecycle_profile in TERMINAL_PROFILES | {"ACTIVE_2Y_OFFICIAL"}:
            fixing_policy = "AUTO_YAHOO"
        profile_label = LIFECYCLE_PROFILES[lifecycle_profile]
        ao_date = _to_business_day(min(today, trade - timedelta(days=2)))
        specs.append({
            "index": index,
            "family": family,
            "product_type": PRODUCTS[family],
            "name": f"UAT {index:03d} — {PRODUCTS[family]} — {profile_label}",
            "script": script,
            "params": params,
            "trade_date": trade.isoformat(),
            "ao_date": ao_date.isoformat(),
            "maturity_date": maturity.isoformat(),
            "payment_date": payment_date.isoformat(),
            # Filled by _price_specs before anything is written. Left None here
            # on purpose: preview_generation does not price (a batch of Monte
            # Carlo runs is seconds, not milliseconds) and must never surface a
            # made-up number, which is what a placeholder would become.
            "model_price": None,
            "fixing_policy": fixing_policy,
            "lifecycle_profile": lifecycle_profile,
            "lifecycle_profile_label": profile_label,
            "rfq_scenario": ("EXECUTABLE" if (
                                 body.mode == "FULL_CHAIN" or
                                 body.rfq_profile == "EXECUTABLE")
                             else [
                                 "EXECUTABLE", "EXPIRED", "INDICATIVE", "NO_SELECTION",
                             ][(index - 1) % 4]),
        })
    return specs


def _price_specs(specs: list[dict], *, seed: int) -> None:
    """Price every spec with the production engine, in place.

    Replaces a `rng.uniform(97, 100)` draw that ignored the coupon, the
    barriers, the tenor and the basket size alike — so every downstream
    consumer of a fair value (residual MtM, P&L explain, the RFQ margin,
    portfolio risk) was being exercised against a number carrying no
    information about the product it was attached to.

    Pricing at inception needs no historical market data, which is what makes
    this cheap: the generated payoffs are all expressed in fractions of S0
    (WOF, the M_* barriers, PAY in units of 1), so the price as a fraction of
    notional is invariant to the spot level — only sigma, q, r, T and the
    correlation matter, and UNDERLYINGS carries sigma and q per ticker.

    Runs through core/compute so a batch spreads over processes (the engine is
    pure-Python per path, the GIL would serialise threads): ~1 to 5 s per deal
    sequentially, which a fifty-deal batch cannot afford.

    A deal that fails to price raises rather than falling back to a default —
    a silent fallback here would quietly reintroduce exactly the fictional
    price this function exists to remove."""
    if not specs:
        return
    jobs = []
    for spec in specs:
        params = spec["params"]
        jobs.append((spec["index"], {
            "script_text": spec["script"],
            "underlyings": params["underlyings"],
            "corr": params["corr_matrix"],
            "r": params["r"],
            "T": params["T"],
            "n_paths": UAT_PRICING_PATHS,
            "model": params["model"],
            # Derived from the batch seed so a given seed keeps producing a
            # given set of prices — the generator's reproducibility contract.
            "seed": (seed * 100_003 + spec["index"]) % (2 ** 31 - 1),
            "antithetic": True,
            "user_params": params["user_params"],
            "constat_values": params["constats"],
            "strike_date": params["strike_date"],
            "value_date": params["value_date"],
            "payment_date": params["payment_date"],
            "settlement_ccy": params["currency"],
        }))

    results = run_batch(
        "payscript_reprice", jobs,
        max_workers=max(1, min(8, (os.cpu_count() or 4))),
    )
    by_index = {result.job_id: result for result in results}
    failures = []
    for spec in specs:
        result = by_index.get(spec["index"])
        if result is None or not result.ok or result.result is None:
            failures.append(
                f"{spec['name']}: {result.error if result else 'aucun résultat'}")
            continue
        # The engine returns a fraction of notional; the whole booking chain
        # (fair_value, quote prices, price_traded) speaks in percent.
        spec["model_price"] = round(float(result.result["price"]) * 100, 2)
    if failures:
        raise RuntimeError(
            "Pricing UAT impossible pour "
            f"{len(failures)} produit(s) : {' | '.join(failures[:5])}")


def preview_generation(body: UatGenerationRequest, session: Session) -> dict:
    _validate_request(body, session)
    specs = _build_specs(body)
    rfq_count = body.count if body.mode in {"RFQ_ONLY", "FULL_CHAIN"} else 0
    deal_count = body.count if body.mode in {"BOOKED_ONLY", "FULL_CHAIN"} else 0
    profile_counts = {
        key: sum(spec["lifecycle_profile"] == key for spec in specs)
        for key in LIFECYCLE_PROFILE_KEYS
        if any(spec["lifecycle_profile"] == key for spec in specs)
    }
    warnings = []
    if body.mode == "RFQ_ONLY" and body.rfq_profile == "CONTROL_MIX":
        warnings.append(
            "Le profil de contrôles crée volontairement des RFQ non bookables.")
    if body.lifecycle_profile == "COMPLETE_MIX" and body.count < len(LIFECYCLE_PROFILE_KEYS):
        warnings.append(
            f"Un mix complet nécessite au moins {len(LIFECYCLE_PROFILE_KEYS)} objets ; "
            "ce lot ne couvrira que les premiers profils de la matrice.")
    if any(spec["lifecycle_profile"] in TERMINAL_PROFILES | {"ACTIVE_2Y_OFFICIAL"}
           for spec in specs):
        warnings.append(
            "Les profils officialisés et terminaux imposent AUTO_YAHOO afin de tester "
            "le rejeu et l'application automatiques de production.")
    return {
        "seed": body.seed,
        "mode": body.mode,
        "rfq_count": rfq_count,
        "deal_count": deal_count,
        "profile_counts": profile_counts,
        "samples": [{
            "name": spec["name"],
            "product_type": spec["product_type"],
            "underlyings": [u["ticker"] for u in spec["params"]["underlyings"]],
            "nominal": spec["params"]["notional"],
            "currency": spec["params"]["currency"],
            "lifecycle_profile": spec["lifecycle_profile"],
            "lifecycle_profile_label": spec["lifecycle_profile_label"],
            "ao_date": spec["ao_date"],
            "trade_date": spec["trade_date"],
            "strike_date": spec["params"]["strike_date"],
            "maturity_date": spec["maturity_date"],
            "fixing_policy": spec["fixing_policy"],
            "rfq_scenario": spec["rfq_scenario"] if rfq_count else None,
        } for spec in specs[:8]],
        "warnings": warnings,
        # Kept for older clients while the Admin UI moves to the list above.
        "warning": warnings[0] if warnings else None,
    }


def _create_rfq(spec: dict, body: UatGenerationRequest, target: User,
                providers: list[dict], batch: UatGenerationBatch,
                session: Session) -> tuple[RfqRequest, RfqQuote | None]:
    rfq_data = rfq_api._create_rfq(
        rfq_api.RfqCreate(
            name=f"{spec['name']} [{batch.batch_key}]",
            ao_date=spec["ao_date"],
            kind="to_trade",
            sens="achat",
            template_type=spec["family"],
            script_snapshot=spec["script"],
            params=spec["params"],
        ),
        target,
        session,
        reference_prefix=f"UAT-RFQ-{batch.batch_key}-",
        uat_batch_id=batch.id,
    )
    rfq = session.get(RfqRequest, rfq_data["id"])

    rng = random.Random(body.seed * 10_000 + spec["index"])
    quote_rows: list[tuple[dict, dict]] = []
    now = datetime.utcnow()
    selected_providers = rng.sample(providers, body.quotes_per_rfq)
    for offset, provider in enumerate(selected_providers):
        quote = rfq_api.add_quote(
            rfq.id,
            rfq_api.QuoteCreate(
                provider=provider["label"],
                note=f"UAT batch {batch.batch_key}",
            ),
            target,
            session,
        )
        price = round(spec["model_price"] + rng.uniform(-0.45, 0.45) + offset * 0.02, 2)
        scenario = spec["rfq_scenario"]
        quoted_at = now - (timedelta(hours=2) if scenario == "EXPIRED"
                           else timedelta(minutes=5 + offset))
        valid_until = (now - timedelta(hours=1) if scenario == "EXPIRED"
                       else now + timedelta(hours=1))
        quote = rfq_api.update_quote(
            rfq.id,
            quote["id"],
            rfq_api.QuoteUpdate(
                price=price,
                currency=spec["params"]["currency"],
                quoted_at=_utc_iso(quoted_at),
                firmness="INDICATIVE" if scenario == "INDICATIVE" else "FIRM",
                valid_until=_utc_iso(valid_until),
            ),
            target,
            session,
        )
        quote_rows.append((quote, provider))

    rfq_api.update_rfq(
        rfq.id, rfq_api.RfqUpdate(model_price=spec["model_price"]), target, session)
    selected: RfqQuote | None = None
    if spec["rfq_scenario"] != "NO_SELECTION":
        # We buy: the lowest executable response wins.
        winner, _ = min(quote_rows, key=lambda item: item[0]["price"])
        rfq_api.update_rfq(
            rfq.id, rfq_api.RfqUpdate(selected_quote_id=winner["id"]), target, session)
        selected = session.get(RfqQuote, winner["id"])
    return session.get(RfqRequest, rfq.id), selected


def _align_events_to_business_days(deal: Deal, session: Session) -> int:
    """Move every booked observation off Saturday and Sunday.

    _book_deal resolves the contract calendar by rolling year fractions, and
    that resolver carries no business-day convention, so 22% of the events
    this generator produced landed on a weekend — a date on which no index
    has a close, hence a fixing no operator can ever resolve. Snapping the
    anchors in _profile_dates is not enough: the intermediate observations
    come from the resolver, not from the anchors.

    Only event_date moves. t_years is left exactly as booked because it drives
    the Monte-Carlo schedule and the official replay, and a shift of at most
    two days on a multi-year schedule is immaterial there — which is precisely
    how a real observation calendar behaves once its dates are adjusted.
    Consecutive observations are a quarter apart at the tightest, so rolling
    backwards can never make two of them collide."""
    moved = 0
    for event in session.exec(
        select(DealEvent).where(DealEvent.deal_id == deal.id)
    ).all():
        current = date.fromisoformat(event.event_date)
        aligned = _to_business_day(current)
        if aligned != current:
            event.event_date = aligned.isoformat()
            session.add(event)
            moved += 1
    if moved:
        session.flush()
    return moved


def _book(spec: dict, target: User, batch: UatGenerationBatch,
          session: Session, *, rfq: RfqRequest | None = None,
          selected: RfqQuote | None = None, counterparty: str) -> Deal:
    params = spec["params"]
    market = {
        "underlyings": params["underlyings"],
        "user_params": params["user_params"],
        "constats": params["constats"],
        "r": params["r"],
        "model": params["model"],
        "corrMatrix": params["corr_matrix"],
        "uat_scenario": {
            "batch_key": batch.batch_key,
            "lifecycle_profile": spec["lifecycle_profile"],
        },
    }
    deal_data = deals_api._book_deal(
        deals_api.DealCreate(
            sens="vente",
            contrepartie=counterparty,
            devise=params["currency"],
            product_type=spec["product_type"],
            fixing_policy=spec["fixing_policy"],
            nominal=params["notional"],
            fair_value=spec["model_price"],
            price_traded=selected.price if selected else round(spec["model_price"] + 0.2, 2),
            trade_date=spec["trade_date"],
            strike_date=params["strike_date"],
            value_date=params["value_date"],
            maturity_date=spec["maturity_date"],
            payment_date=spec["payment_date"],
            T=params["T"],
            underlyings=params["underlyings"],
            observation_times=[],
            script_snapshot=spec["script"],
            market_snapshot=market,
            rfq_id=rfq.id if rfq else None,
        ),
        target,
        session,
        reference_prefix=(
            f"UAT-DEAL-{batch.batch_key}-{spec['lifecycle_profile']}-"),
        uat_batch_id=batch.id,
    )
    deal = session.get(Deal, deal_data["id"])
    _align_events_to_business_days(deal, session)
    return deal


def _load_yahoo_fixings(deal: Deal, target: User, session: Session,
                        result: dict) -> dict:
    """Officialise, at generation time, everything Yahoo can already answer.

    Generated deals used to arrive with every constatation empty, and the only
    way to fill them was a Refresh the operator had to know to press — so the
    whole fixture was useless for anything downstream of a fixing: residual
    MtM, lifecycle resolution, P&L explain, valuation notes.

    This calls the production path, the very one the Refresh button calls, so
    a batch lands with its reachable closes already applied and its lifecycle
    already resolved where it should be.

    Only for profiles the generator leaves unresolved. The terminal and
    officialised ones attach their own synthetic fixings to force a specific
    outcome (a call at 1.15, a knock-in at 0.35); replaying them against real
    Yahoo closes would contradict the very scenario they exist to produce.

    A failure is recorded, not raised: Yahoo unreachable, or a close not yet
    published, must not sink a whole batch — the deal is still valid, it just
    has nothing to load yet."""
    try:
        outcome = deals_api._refresh_deal_core(
            deal, session, actor_user_id=target.id)
    except Exception as exc:  # provider outage, ticker gap, closed market
        result["fixings_error"] = f"{type(exc).__name__}: {exc}"[:200]
        return result
    result["official_fixings"] = int(outcome.get("officialized") or 0)
    result["pending_exceptions"] = len(outcome.get("exceptions") or [])
    evaluation = outcome.get("evaluation") or {}
    result["outcome"] = evaluation.get("outcome")
    return result


def _materialize_lifecycle_profile(
    spec: dict,
    deal: Deal,
    target: User,
    batch: UatGenerationBatch,
    session: Session,
) -> dict:
    """Give the deal its real observations and let the script say what happened.

    Every profile used to attach a constant synthetic ratio to each reached
    observation — 1.0 at the strike, then a flat 0.80, or 1.15 to force a call,
    or 0.35 to force a knock-in — and then assert the very outcome it had just
    engineered. Two things were wrong with that. The values were not a
    trajectory: a deal showed 344 at three different dates because 344 is
    0.80 x 430, which is not something a stock does. And every profile that
    skipped the machinery got no strike fixing at all, so the barrier watchlist
    had no S0 to measure against and computed nothing on four deals out of five.

    There is one rule now: at each observation date, the underlying's actual
    close, fetched through the production path. Whether a barrier is breached
    follows from the script evaluating those values — it is not decided here.
    A profile no longer forces an outcome; it decides how far back the deal was
    traded, which is the part that was ever worth having."""
    profile = spec["lifecycle_profile"]
    events = list(session.exec(
        select(DealEvent).where(DealEvent.deal_id == deal.id)
        .order_by(DealEvent.t_years, DealEvent.event_index)
    ).all())
    today_iso = date.today().isoformat()
    reached = [event for event in events if event.event_date <= today_iso]
    result = {
        "profile": profile,
        "profile_label": spec["lifecycle_profile_label"],
        "reached_events": len(reached),
        "official_fixings": 0,
        "missing_fixings": 0,
        "outcome": None,
    }

    if not reached:
        # FORWARD_START, and only it: even the strike is still ahead.
        return result
    if spec["fixing_policy"] != "AUTO_YAHOO":
        # A controlled deal has no automatic source: its values are entered by
        # hand. Nothing is invented for it here.
        return result

    _load_yahoo_fixings(deal, target, session, result)
    session.flush()
    record_audit_event(
        session,
        action="UAT_LIFECYCLE_SCENARIO_MATERIALIZED",
        object_type="DEAL",
        object_id=deal.id,
        actor_user_id=None,
        actor_type="SYSTEM",
        result="SUCCESS",
        after={
            "deal_reference": deal.reference,
            "profile": profile,
            "official_fixings": result["official_fixings"],
            "outcome": result["outcome"],
        },
        reason="Constatations UAT chargées depuis les clôtures Yahoo réelles.",
        data_source=DataCategory.FIXING_OFFICIAL,
        correlation_id=f"uat:{batch.batch_key}",
    )
    return result


def _age_generated_records(
    spec: dict,
    session: Session,
    *,
    rfq: RfqRequest | None = None,
    deal: Deal | None = None,
) -> None:
    """Align technical timestamps with the generated business history."""
    if date.fromisoformat(spec["trade_date"]) >= date.today():
        return
    ao_at = datetime.combine(date.fromisoformat(spec["ao_date"]), datetime.min.time()) \
        + timedelta(hours=9)
    trade_at = datetime.combine(
        date.fromisoformat(spec["trade_date"]), datetime.min.time()) \
        + timedelta(hours=16)
    if rfq:
        rfq.created_at = ao_at
        rfq.updated_at = ao_at + timedelta(hours=4)
        if rfq.model_price_at:
            rfq.model_price_at = ao_at + timedelta(hours=2)
        session.add(rfq)
        quotes = session.exec(
            select(RfqQuote).where(RfqQuote.rfq_id == rfq.id)
            .order_by(RfqQuote.id)
        ).all()
        for offset, quote in enumerate(quotes):
            quote_at = ao_at + timedelta(hours=1, minutes=offset * 5)
            quote.created_at = quote_at
            quote.quoted_at = quote_at
            if quote.valid_until:
                quote.valid_until = quote_at + timedelta(hours=1)
            session.add(quote)
    if deal:
        deal.created_at = trade_at
        try:
            provenance = json.loads(deal.rfq_provenance_json or "{}")
        except ValueError:
            provenance = {}
        if provenance:
            provenance["booked_at"] = trade_at.isoformat()
            retained = provenance.get("retained")
            if retained:
                retained["quoted_at"] = (
                    ao_at + timedelta(hours=1)).isoformat()
            deal.rfq_provenance_json = json.dumps(provenance, ensure_ascii=False)
        session.add(deal)


def generate_batch(body: UatGenerationRequest, admin: User, session: Session) -> dict:
    target, providers = _validate_request(body, session)
    specs = _build_specs(body)
    # Before any row is written: a batch that cannot be priced must fail whole
    # rather than book deals carrying an invented fair value.
    _price_specs(specs, seed=body.seed)
    batch_key = datetime.utcnow().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6].upper()
    batch = UatGenerationBatch(
        batch_key=batch_key,
        label=(body.label.strip() or f"Lot UAT {body.mode.lower()}")[:120],
        created_by=admin.id,
        target_user_id=target.id,
        mode=body.mode,
        seed=body.seed,
        requested_count=body.count,
        status="RUNNING",
        config_json=body.model_dump_json(),
    )
    session.add(batch)
    session.commit()
    session.refresh(batch)

    created_rfqs: list[str] = []
    created_deals: list[str] = []
    created_scenarios: list[dict] = []
    try:
        for spec in specs:
            rfq = None
            selected = None
            if body.mode in {"RFQ_ONLY", "FULL_CHAIN"}:
                # The full chain always needs an executable RFQ, regardless of
                # a profile accidentally retained by a caller.
                if body.mode == "FULL_CHAIN":
                    spec["rfq_scenario"] = "EXECUTABLE"
                rfq, selected = _create_rfq(
                    spec, body, target, providers, batch, session)
                created_rfqs.append(rfq.reference)
                if body.mode == "RFQ_ONLY":
                    _age_generated_records(spec, session, rfq=rfq)
            if body.mode in {"BOOKED_ONLY", "FULL_CHAIN"}:
                if rfq:
                    selected_provider = next(
                        row for row in providers if row["label"] == selected.provider)
                    counterparty = selected_provider["counterparty"]
                elif providers:
                    counterparty = providers[(spec["index"] - 1) % len(providers)]["counterparty"]
                else:
                    counterparty = session.exec(
                        select(Counterparty).where(Counterparty.active == True)  # noqa: E712
                        .order_by(Counterparty.name)
                    ).first().name
                deal = _book(
                    spec, target, batch, session, rfq=rfq, selected=selected,
                    counterparty=counterparty)
                created_deals.append(deal.reference)
                scenario_result = _materialize_lifecycle_profile(
                    spec, deal, target, batch, session)
                _age_generated_records(spec, session, rfq=rfq, deal=deal)
                created_scenarios.append({
                    "deal_reference": deal.reference,
                    "rfq_reference": rfq.reference if rfq else None,
                    "ao_date": spec["ao_date"],
                    "trade_date": spec["trade_date"],
                    "strike_date": spec["params"]["strike_date"],
                    "maturity_date": spec["maturity_date"],
                    **scenario_result,
                })
            elif rfq:
                created_scenarios.append({
                    "deal_reference": None,
                    "rfq_reference": rfq.reference,
                    "ao_date": spec["ao_date"],
                    "trade_date": spec["trade_date"],
                    "strike_date": spec["params"]["strike_date"],
                    "maturity_date": spec["maturity_date"],
                    "profile": spec["lifecycle_profile"],
                    "profile_label": spec["lifecycle_profile_label"],
                    "rfq_scenario": spec["rfq_scenario"],
                })

        batch = session.get(UatGenerationBatch, batch.id)
        batch.rfq_count = len(created_rfqs)
        batch.deal_count = len(created_deals)
        batch.status = "COMPLETED"
        batch.completed_at = datetime.utcnow()
        batch.result_json = json.dumps({
            "rfq_references": created_rfqs,
            "deal_references": created_deals,
            "scenarios": created_scenarios,
        }, ensure_ascii=False)
        record_audit_event(
            session,
            action="UAT_BATCH_GENERATED",
            object_type="UAT_BATCH",
            object_id=batch.id,
            actor_user_id=admin.id,
            actor_type="USER",
            result="SUCCESS",
            after={"batch_key": batch.batch_key, "mode": batch.mode,
                   "rfq_count": batch.rfq_count, "deal_count": batch.deal_count,
                   "target_user_id": batch.target_user_id, "seed": batch.seed,
                   "lifecycle_profile": body.lifecycle_profile},
            reason="Génération explicite de données de test depuis Administration.",
            correlation_id=f"uat:{batch.batch_key}",
        )
        session.add(batch)
        session.commit()
        return _batch_row(batch, session)
    except Exception as exc:
        session.rollback()
        batch = session.get(UatGenerationBatch, batch.id)
        if batch:
            batch.rfq_count = len(session.exec(
                select(RfqRequest).where(RfqRequest.uat_batch_id == batch.id)
            ).all())
            batch.deal_count = len(session.exec(
                select(Deal).where(Deal.uat_batch_id == batch.id)
            ).all())
            batch.status = "FAILED"
            batch.completed_at = datetime.utcnow()
            batch.error_message = str(exc)[:4000]
            batch.result_json = json.dumps({
                "rfq_references": created_rfqs,
                "deal_references": created_deals,
                "scenarios": created_scenarios,
            }, ensure_ascii=False)
            record_audit_event(
                session,
                action="UAT_BATCH_GENERATION_FAILED",
                object_type="UAT_BATCH",
                object_id=batch.id,
                actor_user_id=admin.id,
                result="ERROR",
                after={"batch_key": batch.batch_key, "error": str(exc)},
                reason="Le lot partiel reste traçable et peut être supprimé depuis Admin.",
                correlation_id=f"uat:{batch.batch_key}",
            )
            session.add(batch)
            session.commit()
        if isinstance(exc, HTTPException):
            raise
        raise HTTPException(
            500, f"Génération UAT interrompue : {exc}. Le lot partiel peut être supprimé.")


def delete_batch(batch_id: int, admin: User, session: Session) -> dict:
    batch = session.get(UatGenerationBatch, batch_id)
    if not batch:
        raise HTTPException(404, "Lot UAT introuvable.")
    if batch.status == "DELETED":
        raise HTTPException(409, "Ce lot UAT a déjà été supprimé.")

    deal_ids = list(session.exec(
        select(Deal.id).where(Deal.uat_batch_id == batch.id)).all())
    rfq_ids = list(session.exec(
        select(RfqRequest.id).where(RfqRequest.uat_batch_id == batch.id)).all())

    if deal_ids:
        session.exec(update(DealEvent).where(DealEvent.deal_id.in_(deal_ids)).values(
            current_fixing_version_id=None))
        session.exec(update(OfficialFixingVersion).where(
            OfficialFixingVersion.deal_id.in_(deal_ids)).values(supersedes_id=None))
        for model in (LifecycleProposal, OfficialFixingVersion, DealContractVersion,
                      TradeAmendmentRequest, Document, KidRecord, EmtRecord,
                      Alert, ShockRun, DealEvent):
            session.exec(delete(model).where(model.deal_id.in_(deal_ids)))
        session.exec(delete(Deal).where(Deal.id.in_(deal_ids)))

    if rfq_ids:
        quote_ids = list(session.exec(
            select(RfqQuote.id).where(RfqQuote.rfq_id.in_(rfq_ids))).all())
        session.exec(update(RfqRequest).where(RfqRequest.id.in_(rfq_ids)).values(
            selected_quote_id=None))
        if quote_ids:
            session.exec(update(RfqQuote).where(RfqQuote.id.in_(quote_ids)).values(
                parent_quote_id=None))
            session.exec(delete(RfqQuote).where(RfqQuote.id.in_(quote_ids)))
        session.exec(delete(RfqRequest).where(RfqRequest.id.in_(rfq_ids)))

    former_status = batch.status
    batch.status = "DELETED"
    batch.deleted_at = datetime.utcnow()
    record_audit_event(
        session,
        action="UAT_BATCH_DELETED",
        object_type="UAT_BATCH",
        object_id=batch.id,
        actor_user_id=admin.id,
        result="SUCCESS",
        before={"status": former_status, "rfq_count": len(rfq_ids),
                "deal_count": len(deal_ids)},
        after={"status": "DELETED"},
        reason="Suppression ciblée des objets rattachés au lot UAT.",
        correlation_id=f"uat:{batch.batch_key}",
    )
    session.add(batch)
    session.commit()
    return {"id": batch.id, "status": batch.status,
            "deleted_rfqs": len(rfq_ids), "deleted_deals": len(deal_ids)}
