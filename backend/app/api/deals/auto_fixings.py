"""Automatic provider fixings, their controls and exception resolution."""
from __future__ import annotations
import base64
import json
import hashlib
import math
from datetime import datetime, date, timedelta, timezone
from typing import Annotated, Literal, Optional
from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlmodel import Session, select
from ...db.database import get_session
from ...runtime import business_today
from ...core.access import is_organization_superuser
from ...db.models import Alert, Deal, DealEvent, User, LifecycleProposal, OfficialFixingVersion
from ..auth import get_current_user
from ...services.market_data import load_yahoo_reference_closes
from ...core.audit import record_audit_event
from ...core.lifecycle_controls import official_input_hash, replay_official_fixings
from ...core.workflow import DataCategory, FixingPolicy, FixingStatus, LifecycleStatus
from ...services.product_lifecycle import stage_product_lifecycle
from ...services.business_access import can_read_deal as _can_access_deal
from ._router import router
from .common import _ensure_alert, _reject_workflow_action, _workflow_failure
from .serializers import _deal_row, _event_row, _get_events, _proposal_row
from .fixing_controls import _fixing_record_hash, _spot_failures
from .lifecycle_rules import _evaluate_lifecycle, _payout_reconciliation_tolerance, _terminal_deal_state

class AutoFixingExceptionResolutionRequest(BaseModel):
    """One-person decision for an AUTO_YAHOO fixing exception.

    The expected version is an optimistic lock: the UI must resolve exactly
    the version it displayed.  A concurrent capture or provider revision
    therefore fails closed instead of being silently overwritten.
    """
    action: Literal["USE_YAHOO", "CONFIRM_CURRENT", "REPLACE_MANUAL"]
    expected_version_id: Optional[int] = None
    spots: Optional[dict] = None
    source_reference: str = Field(default="", max_length=500)
    # Taking the automatic source is not a deviation, so it carries no written
    # justification: the signature exists to record *departures* from Yahoo,
    # and demanding a motive to accept the default inverted that — an operator
    # had to write ten characters to agree with the machine. The actor, the
    # action and its timestamp are audited either way. The two actions that do
    # override the automatic source keep the requirement, and so does a
    # USE_YAHOO that overrides a soft control (enforced in the handler, where
    # the control outcome is known).
    reason: str = Field(default="", max_length=2000)

    @model_validator(mode="after")
    def _motive_required_when_overriding(self):
        if self.action != "USE_YAHOO" and len(self.reason.strip()) < 10:
            raise ValueError(
                "Le motif est obligatoire (10 caractères minimum) pour toute "
                "décision qui écarte la source automatique.")
        return self


_AUTO_YAHOO_MAX_FALLBACK_DAYS = 3
_AUTO_YAHOO_MAX_DAILY_MOVE = 0.50


def _reference_history_arrays(
    reference_data: dict, tickers: list[str],
) -> tuple[list[str], dict[str, list[float]]]:
    """Align independent raw-close series without backfilling the past."""
    series = reference_data.get("series") or {}
    union_dates = sorted({
        market_date
        for ticker in tickers
        for market_date in (series.get(ticker) or {})
    })
    last_values: dict[str, float] = {}
    dates: list[str] = []
    prices = {ticker: [] for ticker in tickers}
    for market_date in union_dates:
        for ticker in tickers:
            value = (series.get(ticker) or {}).get(market_date)
            if value is not None:
                last_values[ticker] = float(value)
        # Forward-fill only after every ticker has published at least one
        # close.  A future close is never backfilled into an earlier date.
        if any(ticker not in last_values for ticker in tickers):
            continue
        dates.append(market_date)
        for ticker in tickers:
            prices[ticker].append(last_values[ticker])
    return dates, prices


def _auto_yahoo_event_values(
    event: DealEvent,
    underlyings: list[dict],
    reference_data: dict,
) -> tuple[dict, dict, list[dict], bool]:
    """Resolve and quality-check one contractual Yahoo close.

    Returns ``(spots, used_dates, failures, waiting_for_close)``.  The policy
    is explicit: exact close for an event dated today; otherwise the last
    unadjusted close on or before the date, no more than three calendar days
    old.  Splits and daily moves above 50% are escalated instead of silently
    becoming contractual facts.
    """
    series = reference_data.get("series") or {}
    splits = reference_data.get("splits") or {}
    currencies = reference_data.get("currencies") or {}
    spots: dict[str, float] = {}
    used_dates: dict[str, str] = {}
    failures: list[dict] = []
    waiting_for_close = False
    today = business_today().isoformat()
    target = date.fromisoformat(event.event_date)
    for underlying in underlyings:
        name = str(underlying.get("name") or "").strip()
        ticker = str(underlying.get("ticker") or "").strip()
        ticker_series = series.get(ticker) or {}
        available = sorted(d for d in ticker_series if d <= event.event_date)
        if not available:
            failures.append(_workflow_failure(
                "YAHOO_CLOSE_MISSING", f"spots.{name}",
                "Aucune clôture Yahoo n'est disponible à la date contractuelle.",
                expected=f"Une clôture non ajustée pour {ticker} au plus tard le {event.event_date}.",
                action="Vérifiez le ticker Yahoo ou traitez cette constatation en exception contrôlée.",
                received=None,
            ))
            continue
        used_date = available[-1]
        if event.event_date == today and used_date != event.event_date:
            waiting_for_close = True
            failures.append(_workflow_failure(
                "YAHOO_CLOSE_NOT_PUBLISHED", f"spots.{name}",
                "La clôture Yahoo du jour n'est pas encore publiée.",
                expected=f"La clôture non ajustée du {event.event_date} pour {ticker}.",
                action="Relancez l'actualisation après la clôture du marché.",
                received=used_date,
            ))
            continue
        value = float(ticker_series[used_date])
        if not math.isfinite(value) or value <= 0:
            failures.append(_workflow_failure(
                "YAHOO_CLOSE_INVALID", f"spots.{name}",
                "La clôture Yahoo n'est pas une valeur strictement positive.",
                expected="Une valeur numérique finie et strictement positive.",
                action="Contrôlez la publication Yahoo ou utilisez le workflow d'exception.",
                received=value,
            ))
            continue
        # Keep the provider value visible even when a quality control below
        # escalates it.  A human cannot make an informed decision if the UI
        # only says "outlier" without showing the value under review.
        spots[name] = round(value, 8)
        used_dates[name] = used_date
        from ...core.fixing_finality import qualify_close
        finality = qualify_close(used_date, (reference_data.get("sources") or {}).get(ticker) or {})
        if not finality["qualified"]:
            waiting = finality["status"] == "WAITING_SESSION_CLOSE"
            waiting_for_close = waiting_for_close or waiting
            failures.append(_workflow_failure(
                "YAHOO_CLOSE_NOT_PUBLISHED" if waiting else "YAHOO_CLOSE_FINALITY_UNVERIFIED",
                f"spots.{name}",
                "La clôture n'est pas encore disponible après la fin de sa séance locale.",
                expected="Séance, fuseau et téléchargement après clôture établis, sans délai ajouté.",
                action="Relancez à la publication de la clôture ou traitez une exception sourcée explicite.",
                received=finality))
            continue
        lag_days = (target - date.fromisoformat(used_date)).days
        if lag_days > _AUTO_YAHOO_MAX_FALLBACK_DAYS:
            failures.append(_workflow_failure(
                "YAHOO_CLOSE_STALE", f"spots.{name}",
                "La dernière clôture Yahoo est trop ancienne pour faire foi automatiquement.",
                expected=f"Un écart de 0 à {_AUTO_YAHOO_MAX_FALLBACK_DAYS} jours calendaires.",
                action="Vérifiez le calendrier, le ticker et la source avant validation manuelle.",
                received={"market_date": used_date, "lag_days": lag_days, "close": value},
            ))
        expected_currency = str(underlying.get("ccy") or "").strip().upper()
        provider_currency = str(currencies.get(ticker) or "").strip().upper()
        if (expected_currency and provider_currency and
                expected_currency != provider_currency):
            failures.append(_workflow_failure(
                "YAHOO_CURRENCY_MISMATCH", f"underlyings.{name}.ccy",
                "La devise publiée par Yahoo ne correspond pas à la devise contractuelle du sous-jacent.",
                expected=expected_currency,
                action="Corrigez le ticker ou la devise contractuelle avant toute application.",
                received=provider_currency,
            ))
        if abs(float((splits.get(ticker) or {}).get(used_date, 0) or 0)) > 1e-12:
            failures.append(_workflow_failure(
                "YAHOO_CORPORATE_ACTION", f"spots.{name}",
                "Yahoo signale un split à la date du fixing.",
                expected="Aucune corporate action non réconciliée.",
                action="Contrôlez le ratio du split et les termes contractuels avant application.",
                received={"market_date": used_date, "split": splits[ticker][used_date]},
            ))
        previous_dates = [d for d in sorted(ticker_series) if d < used_date]
        if previous_dates:
            previous = float(ticker_series[previous_dates[-1]])
            if previous > 0 and abs(value / previous - 1.0) > _AUTO_YAHOO_MAX_DAILY_MOVE:
                failures.append(_workflow_failure(
                    "YAHOO_CLOSE_OUTLIER", f"spots.{name}",
                    "La variation quotidienne Yahoo dépasse le seuil de contrôle automatique.",
                    expected=f"Une variation absolue inférieure ou égale à {_AUTO_YAHOO_MAX_DAILY_MOVE:.0%}.",
                    action="Contrôlez une éventuelle corporate action ou une erreur de ticker.",
                    received={
                        "previous_market_date": previous_dates[-1],
                        "previous_close": previous,
                        "market_date": used_date,
                        "close": value,
                    },
                ))
    return spots, used_dates, failures, waiting_for_close


def _auto_yahoo_evidence(
    deal: Deal,
    event: DealEvent,
    underlyings: list[dict],
    spots: dict,
    used_dates: dict,
    fetched_at: str,
    provider_currencies: dict,
    provider_sources: dict | None = None,
) -> tuple[dict, bytes, str]:
    inputs = []
    for underlying in underlyings:
        name = underlying["name"]
        from ...core.fixing_finality import qualify_close
        inputs.append({
            "name": name,
            "ticker": underlying["ticker"],
            "market_date": used_dates[name],
            "unadjusted_close": spots[name],
            "currency": underlying.get("ccy") or deal.devise,
            "provider_currency": provider_currencies.get(underlying["ticker"]),
            "finality": qualify_close(used_dates[name], (provider_sources or {}).get(underlying["ticker"]) or {}),
        })
    evidence = {
        "provider": "YAHOO_FINANCE",
        "price_type": "UNADJUSTED_CLOSE",
        "policy": FixingPolicy.AUTO_YAHOO.value,
        "fallback_rule": f"LAST_CLOSE_ON_OR_BEFORE_MAX_{_AUTO_YAHOO_MAX_FALLBACK_DAYS}D",
        "deal_id": deal.id,
        "contract_version": deal.contract_version,
        "event_id": event.id,
        "event_date": event.event_date,
        "fetched_at": fetched_at,
        "inputs": inputs,
    }
    payload = json.dumps(
        evidence, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return evidence, payload, hashlib.sha256(payload).hexdigest()


def _auto_exception_manual_evidence(
    deal: Deal,
    event: DealEvent,
    *,
    action: str,
    spots: dict,
    source_reference: str,
    reason: str,
    actor_user_id: int,
    previous_version: OfficialFixingVersion | None,
) -> tuple[dict, bytes, str]:
    evidence = {
        "evidence_type": "AUTO_YAHOO_USER_EXCEPTION_DECISION",
        "policy": FixingPolicy.AUTO_YAHOO.value,
        "deal_id": deal.id,
        "contract_version": deal.contract_version,
        "event_id": event.id,
        "event_date": event.event_date,
        "action": action,
        "actor_user_id": actor_user_id,
        "source_reference": source_reference,
        "reason": reason,
        "spots": spots,
        "previous_version_id": previous_version.id if previous_version else None,
        "previous_version": previous_version.version if previous_version else None,
        "previous_spots": json.loads(event.spots_json or "{}"),
        "last_yahoo_spots": json.loads(event.indicative_spots_json or "{}"),
        "decided_at": datetime.utcnow().isoformat(),
    }
    payload = json.dumps(
        evidence, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return evidence, payload, hashlib.sha256(payload).hexdigest()


def _user_exception_lifecycle_evaluation(
    deal: Deal,
    session: Session,
) -> tuple[dict | None, list[dict]]:
    """Derive a terminal fact only from all reached official observations."""
    today = business_today().isoformat()
    reached = sorted((event for event in _get_events(deal.id, session)
                      if event.event_date <= today and event.status != "annulé"),
                     key=lambda event: (event.t_years, event.event_index))
    if not reached:
        return {"outcome": "en_cours"}, []
    prefix = []
    official_result = None
    for event in reached:
        if (event.fixing_status not in {
                FixingStatus.VALIDATED.value, FixingStatus.APPLIED.value,
            } or event.data_category != DataCategory.FIXING_OFFICIAL.value):
            return None, [_workflow_failure(
                "AUTO_USER_EXCEPTION_STILL_PENDING",
                "events",
                "Une constatation nécessaire au rejeu n'est pas encore validée.",
                expected="Une décision utilisateur sur chaque exception requise.",
                action="Traitez la prochaine ligne signalée en exception.",
                received=[event.id],
            )]
        prefix.append(event)
        official_result, failures = replay_official_fixings(deal, prefix)
        if failures or not official_result:
            return None, failures
        # A terminal prefix ends contractual life even when replay happens
        # years later. Subsequent observations are no longer required.
        if official_result.get("outcome") == "callé":
            return official_result, []
    if today >= deal.maturity_date:
        maturity = max(reached, key=lambda row: row.t_years)
        # DealEvent stores a rounded display time. The immutable contractual
        # date identifies maturity; comparing it with an unrounded T can
        # leave a fully fixed product active forever.
        if maturity.event_date >= deal.maturity_date:
            return official_result, []
    return {"outcome": "en_cours"}, []


def _pending_auto_fixing_exceptions(deal: Deal, session: Session) -> list[DealEvent]:
    today = business_today().isoformat()
    return [event for event in _get_events(deal.id, session) if (
        event.event_date <= today and event.fixing_status in {
            FixingStatus.RECEIVED.value,
            FixingStatus.PARTIAL.value,
            FixingStatus.MISSING.value,
            FixingStatus.REJECTED.value,
            FixingStatus.CONTESTED.value,
            FixingStatus.MANUAL_REVIEW_REQUIRED.value,
        }
    )]


@router.post("/{deal_id}/events/{event_id}/resolve-auto-exception")
def resolve_auto_fixing_exception(
    deal_id: int,
    event_id: int,
    body: AutoFixingExceptionResolutionRequest,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    try:
        return _resolve_auto_fixing_exception(deal_id, event_id, body, current, session)
    except Exception:
        session.rollback()
        raise


def _resolve_auto_fixing_exception(deal_id, event_id, body, current, session):
    """Make the authenticated deal user accountable for an AUTO exception.

    This is deliberately not the FOUR_EYES endpoint.  It creates a new,
    immutable, user-signed official version and then replays the product from
    official fixings.  The provider feed or a concurrent human version can
    never be overwritten in place.
    """
    deal = session.get(Deal, deal_id)
    if not deal or not _can_access_deal(deal, current, session):
        raise HTTPException(404, "Deal introuvable")
    if current.id != deal.user_id and getattr(current, "role", None) != "admin" and not is_organization_superuser(current):
        raise HTTPException(403, {
            "code": "AUTO_EXCEPTION_USER_RESPONSIBILITY_REQUIRED",
            "message": "Cette exception doit être décidée par le propriétaire du deal.",
        })
    event = session.get(DealEvent, event_id)
    if not event or event.deal_id != deal.id:
        raise HTTPException(404, "Événement introuvable")

    failures: list[dict] = []
    if deal.fixing_policy != FixingPolicy.AUTO_YAHOO.value:
        failures.append(_workflow_failure(
            "AUTO_EXCEPTION_POLICY_REQUIRED", "fixing_policy",
            "La validation mono-utilisateur est réservée aux produits Yahoo automatiques.",
            expected=FixingPolicy.AUTO_YAHOO.value,
            action="Actualisez le deal pour appliquer la politique automatique.",
            received=deal.fixing_policy,
        ))
    if event.event_date > business_today().isoformat():
        failures.append(_workflow_failure(
            "FIXING_EVENT_IN_FUTURE", "event_date",
            "La constatation contractuelle n'est pas encore atteinte.",
            expected="Une date atteinte.",
            action="Attendez la date de constatation.", received=event.event_date,
        ))
    if event.fixing_status not in {
        FixingStatus.RECEIVED.value, FixingStatus.PARTIAL.value,
        FixingStatus.MISSING.value, FixingStatus.REJECTED.value,
        FixingStatus.CONTESTED.value, FixingStatus.MANUAL_REVIEW_REQUIRED.value,
    }:
        failures.append(_workflow_failure(
            "AUTO_EXCEPTION_STATUS_INVALID", "fixing_status",
            "Cette constatation n'est plus dans un état d'exception traitable.",
            expected="Une exception ouverte et non appliquée.",
            action="Actualisez le deal et consultez son dernier statut.",
            received=event.fixing_status,
        ))
    current_version = (
        session.get(OfficialFixingVersion, event.current_fixing_version_id)
        if event.current_fixing_version_id else None
    )
    if body.expected_version_id != event.current_fixing_version_id:
        failures.append(_workflow_failure(
            "AUTO_EXCEPTION_VERSION_CONFLICT", "expected_version_id",
            "La version affichée n'est plus la version courante.",
            expected=str(event.current_fixing_version_id),
            action="Actualisez la fiche puis contrôlez la nouvelle version.",
            received=body.expected_version_id,
        ))
    if current_version and current_version.status == FixingStatus.APPLIED.value:
        failures.append(_workflow_failure(
            "APPLIED_FIXING_CORRECTION_REQUIRES_CANCEL_REPLACE", "fixing_version.status",
            "Le fixing a déjà été consommé par une résolution appliquée.",
            expected="Un fixing non appliqué.",
            action="Utilisez une procédure d'annulation/remplacement.",
            received=current_version.status,
        ))
    if failures:
        _reject_workflow_action(
            session, action="AUTO_FIXING_EXCEPTION_RESOLUTION_REJECTED",
            object_type="DEAL_EVENT", object_id=event.id, current=current,
            message=f"Exception non traitée — {len(failures)} contrôle(s) bloquant(s).",
            failures=failures, status_code=409, before=_event_row(event),
        )

    before = _event_row(event)
    underlyings = json.loads(deal.underlyings_json or "[]")
    spots: dict
    provider: str
    source_type: str
    external_reference: str
    venue: str
    calendar: str
    observed_at: datetime
    evidence_payload: bytes
    evidence_hash: str
    review_failures: list[dict] = []
    if body.action == "USE_YAHOO":
        tickers = [str(row.get("ticker") or "").strip() for row in underlyings]
        if not tickers or any(not ticker for ticker in tickers):
            _reject_workflow_action(
                session, action="AUTO_FIXING_EXCEPTION_RESOLUTION_REJECTED",
                object_type="DEAL_EVENT", object_id=event.id, current=current,
                message="Valeur Yahoo indisponible — ticker contractuel manquant.",
                failures=[_workflow_failure(
                    "YAHOO_TICKER_MISSING", "underlyings.ticker",
                    "Un ticker Yahoo est absent.", expected="Un ticker par sous-jacent.",
                    action="Corrigez le référentiel ou saisissez une valeur manuelle.")],
                before=before,
            )
        fetch_start = (date.fromisoformat(event.event_date) - timedelta(days=7)).isoformat()
        reference_data = load_yahoo_reference_closes(
            tickers, fetch_start, business_today().isoformat())
        if "error" in reference_data:
            raise HTTPException(422, {
                "code": "YAHOO_PROVIDER_ERROR",
                "message": f"Yahoo indisponible : {reference_data['error']}",
                "action": "Réessayez ou choisissez une décision manuelle.",
            })
        spots, used_dates, review_failures, waiting = _auto_yahoo_event_values(
            event, underlyings, reference_data)
        hard_codes = {
            "YAHOO_CLOSE_MISSING", "YAHOO_CLOSE_INVALID",
            "YAHOO_CLOSE_NOT_PUBLISHED", "YAHOO_CURRENCY_MISMATCH",
            "YAHOO_CLOSE_FINALITY_UNVERIFIED",
        }
        hard_failures = [failure for failure in review_failures
                         if failure["code"] in hard_codes]
        spot_failures = _spot_failures(deal, spots)
        if waiting or hard_failures or spot_failures:
            normalized = hard_failures + [
                _workflow_failure(
                    failure["code"],
                    f"spots.{failure.get('underlying', '')}".rstrip("."),
                    "La valeur Yahoo n'est pas exploitable pour tous les sous-jacents.",
                    expected="Une clôture complète, positive et dans la devise contractuelle.",
                    action="Corrigez le ticker ou choisissez une saisie manuelle.",
                    received=failure.get("value"),
                ) for failure in spot_failures
            ]
            _reject_workflow_action(
                session, action="AUTO_FIXING_EXCEPTION_RESOLUTION_REJECTED",
                object_type="DEAL_EVENT", object_id=event.id, current=current,
                message="Valeur Yahoo non adoptée — la donnée reste inexploitable.",
                failures=normalized, before=before,
            )
        # Accepting a clean Yahoo close needs no motive — see the schema. But a
        # USE_YAHOO that survives a soft control is the operator overruling that
        # control, and an overrule with no stated reason leaves nothing in the
        # ledger to review later.
        if review_failures and len(body.reason.strip()) < 10:
            _reject_workflow_action(
                session, action="AUTO_FIXING_EXCEPTION_RESOLUTION_REJECTED",
                object_type="DEAL_EVENT", object_id=event.id, current=current,
                message="Motif requis — cette reprise Yahoo écarte un contrôle.",
                failures=[_workflow_failure(
                    "AUTO_EXCEPTION_REASON_REQUIRED", "reason",
                    "Reprendre la clôture Yahoo malgré un contrôle en échec "
                    "doit être motivé.",
                    expected="Un motif de 10 caractères minimum.",
                    action="Décrivez le contrôle effectué avant de retenir la donnée.",
                    received=body.reason or None,
                )],
                before=before,
            )
        evidence, evidence_payload, evidence_hash = _auto_yahoo_evidence(
            deal, event, underlyings, spots, used_dates,
            str(reference_data.get("fetched_at") or datetime.utcnow().isoformat()),
            reference_data.get("currencies") or {},
            reference_data.get("sources") or {},
        )
        if review_failures:
            evidence["user_reviewed_failures"] = review_failures
            evidence["user_decision_reason"] = body.reason
            evidence_payload = json.dumps(
                evidence, ensure_ascii=False, sort_keys=True,
                separators=(",", ":")).encode("utf-8")
            evidence_hash = hashlib.sha256(evidence_payload).hexdigest()
        provider, source_type = "YAHOO_FINANCE", "API"
        external_reference = (
            f"YAHOO-USER:{event.event_date}:{','.join(used_dates.values())}")
        venue = "Yahoo Finance"
        calendar = f"LAST_CLOSE_ON_OR_BEFORE_MAX_{_AUTO_YAHOO_MAX_FALLBACK_DAYS}D"
        observed_at = datetime.fromisoformat(f"{max(used_dates.values())}T00:00:00")
    else:
        spots = (
            json.loads(event.spots_json or "{}")
            if body.action == "CONFIRM_CURRENT" else dict(body.spots or {})
        )
        decision_failures = _spot_failures(deal, spots)
        if body.action == "REPLACE_MANUAL" and len(body.source_reference.strip()) < 3:
            decision_failures.append({
                "code": "MANUAL_SOURCE_REFERENCE_MISSING",
                "underlying": "source_reference", "value": body.source_reference,
            })
        if decision_failures:
            _reject_workflow_action(
                session, action="AUTO_FIXING_EXCEPTION_RESOLUTION_REJECTED",
                object_type="DEAL_EVENT", object_id=event.id, current=current,
                message="Décision non enregistrée — valeur ou source incomplète.",
                failures=[_workflow_failure(
                    failure["code"],
                    ("source_reference" if failure.get("underlying") == "source_reference"
                     else f"spots.{failure.get('underlying', '')}".rstrip(".")),
                    ("La référence de la source manuelle est obligatoire."
                     if failure.get("underlying") == "source_reference" else
                     "Le fixing doit contenir une valeur strictement positive par sous-jacent."),
                    expected=("Au moins 3 caractères."
                              if failure.get("underlying") == "source_reference" else
                              "Une valeur numérique strictement positive."),
                    action=("Indiquez le message, document ou source contrôlée."
                            if failure.get("underlying") == "source_reference" else
                            "Complétez ou corrigez la valeur."),
                    received=failure.get("value"),
                ) for failure in decision_failures],
                before=before,
            )
        source_reference = body.source_reference.strip()
        if body.action == "CONFIRM_CURRENT" and not source_reference:
            source_reference = (
                current_version.external_reference if current_version else
                f"EVENT:{event.id}:CURRENT_VALUE")
        _, evidence_payload, evidence_hash = _auto_exception_manual_evidence(
            deal, event, action=body.action, spots=spots,
            source_reference=source_reference, reason=body.reason,
            actor_user_id=current.id, previous_version=current_version,
        )
        provider = (
            current_version.provider
            if body.action == "CONFIRM_CURRENT" and current_version else
            "USER_DECLARED_SOURCE")
        source_type = "USER_DECISION"
        external_reference = source_reference
        venue = current_version.venue if current_version else "User exception decision"
        calendar = current_version.calendar if current_version else "CONTRACTUAL_EVENT_DATE"
        observed_at = (
            current_version.observed_at if current_version else
            datetime.fromisoformat(f"{event.event_date}T12:00:00"))

    latest = session.exec(
        select(OfficialFixingVersion)
        .where(OfficialFixingVersion.deal_event_id == event.id)
        .order_by(OfficialFixingVersion.version.desc())
    ).first()
    next_version = (latest.version if latest else 0) + 1
    supersedes_id = current_version.id if current_version else None
    decided_at = datetime.utcnow()
    evidence_filename = f"user-decision-{deal.reference}-{event.event_date}.json"
    capture_reason = (
        "Adoption explicite de la clôture Yahoo par l'utilisateur."
        if body.action == "USE_YAHOO" else
        "Confirmation utilisateur de la valeur courante."
        if body.action == "CONFIRM_CURRENT" else
        "Correction manuelle décidée par l'utilisateur."
    )
    record_payload = {
        "deal_id": deal.id,
        "contract_version": deal.contract_version,
        "event_id": event.id,
        "event_date": event.event_date,
        "event_index": event.event_index,
        "version": next_version,
        "supersedes_id": supersedes_id,
        "underlyings": underlyings,
        "spots": spots,
        "provider": provider,
        "source_type": source_type,
        "external_reference": external_reference,
        "observed_at": observed_at.replace(tzinfo=timezone.utc).isoformat(),
        "venue": venue,
        "calendar": calendar,
        "timezone": "MARKET_LOCAL_DATE" if body.action == "USE_YAHOO" else "UTC",
        "evidence_sha256": evidence_hash,
        "evidence_filename": evidence_filename,
        "evidence_content_type": "application/json",
        "evidence_size_bytes": len(evidence_payload),
        "capture_reason": capture_reason,
    }
    version = OfficialFixingVersion(
        deal_id=deal.id, deal_event_id=event.id, version=next_version,
        supersedes_id=supersedes_id, status=FixingStatus.VALIDATED.value,
        spots_json=json.dumps(spots, ensure_ascii=False, sort_keys=True),
        provider=provider, source_type=source_type,
        external_reference=external_reference, observed_at=observed_at,
        received_at=decided_at, venue=venue, calendar=calendar,
        timezone=record_payload["timezone"], evidence_sha256=evidence_hash,
        evidence_filename=evidence_filename,
        evidence_content_type="application/json",
        evidence_size_bytes=len(evidence_payload),
        evidence_payload_b64=base64.b64encode(evidence_payload).decode("ascii"),
        record_sha256=_fixing_record_hash(record_payload),
        capture_reason=capture_reason, entered_by=current.id,
        capture_actor_type="USER", validated_by=current.id,
        validation_reason=body.reason, validated_at=decided_at,
    )
    if current_version:
        current_version.status = FixingStatus.SUPERSEDED.value
        session.add(current_version)
    session.add(version)
    session.flush()
    event.spots_json = version.spots_json
    event.source = "auto" if body.action == "USE_YAHOO" else "manuel"
    event.status = "observé"
    event.fixing_status = FixingStatus.VALIDATED.value
    event.data_category = DataCategory.FIXING_OFFICIAL.value
    event.current_fixing_version_id = version.id
    event.fixing_version = version.version
    event.fixing_entered_by = current.id
    event.fixing_entered_at = decided_at
    event.fixing_provider = version.provider
    event.fixing_source_type = version.source_type
    event.fixing_external_reference = version.external_reference
    event.fixing_observed_at = version.observed_at
    event.fixing_venue = version.venue
    event.fixing_calendar = version.calendar
    event.fixing_timezone = version.timezone
    event.fixing_evidence_sha256 = version.evidence_sha256
    event.fixing_record_sha256 = version.record_sha256
    event.fixing_reason = version.capture_reason
    event.validated_by = current.id
    event.validated_at = decided_at
    session.add(event)
    for proposal in session.exec(select(LifecycleProposal).where(
        LifecycleProposal.deal_id == deal.id,
        LifecycleProposal.status.in_([
            LifecycleStatus.PROPOSED.value,
            LifecycleStatus.VALIDATED.value,
            LifecycleStatus.MANUAL_REVIEW_REQUIRED.value,
        ]),
    )).all():
        proposal.status = LifecycleStatus.STALE.value
        proposal.error_message = (
            f"Fixing {event.event_date} décidé par l'utilisateur en version {version.version}.")
        proposal.updated_at = decided_at
        session.add(proposal)
    for alert in session.exec(select(Alert).where(
        Alert.deal_id == deal.id,
        Alert.read == False,  # noqa: E712
        Alert.dedup_key.startswith(
            f"auto-fixing-exception:{deal.id}:{event.id}:"),
    )).all():
        alert.read = True
        session.add(alert)
    record_audit_event(
        session,
        action=f"AUTO_FIXING_EXCEPTION_{body.action}",
        object_type="DEAL_EVENT", object_id=event.id,
        actor_user_id=current.id, actor_type="USER", result="SUCCESS",
        before=before, after=_event_row(event), reason=body.reason,
        data_source=DataCategory.FIXING_OFFICIAL,
        metadata={
            "policy": deal.fixing_policy,
            "decision_action": body.action,
            "previous_version_id": supersedes_id,
            "fixing_version_id": version.id,
            "reviewed_failures": review_failures,
            "source_reference": body.source_reference,
        },
    )
    deal.updated_at = decided_at
    session.add(deal)
    session.flush()

    evaluation, replay_failures = _user_exception_lifecycle_evaluation(deal, session)
    proposal = None
    if evaluation and evaluation.get("outcome") != "en_cours":
        proposal = _auto_apply_lifecycle(
            deal, evaluation, session, actor_user_id=current.id)
    stage_product_lifecycle(
        session, deal, actor_user_id=current.id,
        action="PRODUCT_FIXING_EXCEPTION_DECIDED",
        reason=body.reason,
    )
    session.commit()
    remaining = _pending_auto_fixing_exceptions(deal, session)
    actor_label = getattr(current, "username", None) or f"utilisateur #{current.id}"
    if proposal and proposal.status == LifecycleStatus.APPLIED.value:
        message = (
            f"Observation v{version.version} validée par {actor_label}; "
            f"résolution {proposal.proposed_outcome} appliquée automatiquement.")
    elif remaining:
        message = (
            f"Observation v{version.version} validée par {actor_label}; "
            f"{len(remaining)} exception(s) reste(nt) à traiter.")
    elif replay_failures:
        message = (
            f"Observation v{version.version} validée; le lifecycle reste bloqué : "
            f"{replay_failures[0].get('message', replay_failures[0].get('code'))}")
    else:
        message = (
            f"Observation v{version.version} validée par {actor_label}; "
            "le produit reste en vie.")
    return {
        "event": _event_row(session.get(DealEvent, event.id)),
        "decision_action": body.action,
        "remaining_exceptions": len(remaining),
        "lifecycle_proposal": _proposal_row(proposal) if proposal else None,
        "replay_failures": replay_failures,
        "message": message,
    }


def _auto_yahoo_exception(
    deal: Deal,
    event: DealEvent,
    failures: list[dict],
    session: Session,
    actor_user_id: int | None,
    *,
    waiting_for_close: bool = False,
) -> dict:
    if not waiting_for_close:
        event.fixing_status = FixingStatus.MANUAL_REVIEW_REQUIRED.value
        event.source = "auto"
        session.add(event)
        _ensure_alert(
            session,
            deal,
            "auto_fixing_exception",
            f"Constatation Yahoo à contrôler pour {deal.reference} au {event.event_date}.",
            f"auto-fixing-exception:{deal.id}:{event.id}:"
            + hashlib.sha256(json.dumps(failures, sort_keys=True).encode()).hexdigest()[:16],
        )
    record_audit_event(
        session,
        action=("AUTO_FIXING_WAITING" if waiting_for_close else "AUTO_FIXING_REVIEW_REQUIRED"),
        object_type="DEAL_EVENT",
        object_id=event.id,
        actor_user_id=actor_user_id,
        actor_type="USER" if actor_user_id else "PROCESS",
        result="REJECTED" if not waiting_for_close else "PENDING",
        before={"fixing_status": event.fixing_status},
        after={"failures": failures},
        reason=(
            "Clôture du jour non encore publiée."
            if waiting_for_close else
            "Les contrôles automatiques Yahoo n'autorisent pas ce fixing."
        ),
        data_source=DataCategory.INDICATIVE,
        metadata={"policy": deal.fixing_policy, "failures": failures},
    )
    return {
        "event_id": event.id,
        "event_date": event.event_date,
        "waiting_for_close": waiting_for_close,
        "failures": failures,
    }


def _auto_validate_yahoo_event(
    deal: Deal,
    event: DealEvent,
    underlyings: list[dict],
    reference_data: dict,
    session: Session,
    actor_user_id: int | None,
) -> tuple[bool, dict | None]:
    spots, used_dates, failures, waiting = _auto_yahoo_event_values(
        event, underlyings, reference_data)
    if spots:
        event.indicative_spots_json = json.dumps(
            spots, ensure_ascii=False, sort_keys=True)
        session.add(event)
    current_version = (
        session.get(OfficialFixingVersion, event.current_fixing_version_id)
        if event.current_fixing_version_id else None
    )
    # A source diagnostic cannot revoke a validated ledger fact, regardless
    # of whether it was captured automatically or by a user.
    official = current_version and current_version.status in {
        FixingStatus.VALIDATED.value, FixingStatus.APPLIED.value}
    if official and (failures or current_version.capture_actor_type == "USER"):
        if failures:
            record_audit_event(session, action="OFFICIAL_FIXING_SOURCE_UNAVAILABLE",
                object_type="DEAL_EVENT", object_id=event.id, actor_user_id=actor_user_id,
                result="PENDING", reason="Le registre officiel conserve son autorité.",
                metadata={"source_failures": failures, "fixing_version_id": current_version.id})
        return False, None
    if failures:
        return False, _auto_yahoo_exception(
            deal, event, failures, session, actor_user_id,
            waiting_for_close=waiting and all(
                failure["code"] == "YAHOO_CLOSE_NOT_PUBLISHED"
                for failure in failures),
        )

    before = _event_row(event)
    current_spots = json.loads(event.spots_json or "{}")
    if (current_version and current_spots == spots and
            event.fixing_status in {
                FixingStatus.VALIDATED.value, FixingStatus.APPLIED.value,
            }):
        session.add(event)
        return False, None
    if current_version and event.fixing_status not in {
        FixingStatus.VALIDATED.value, FixingStatus.APPLIED.value,
    }:
        failure = _workflow_failure(
            "CONTROLLED_FIXING_PENDING", "fixing_status",
            "Une version de fixing est déjà en cours de traitement humain.",
            expected="Validation ou rejet explicite de la version courante.",
            action="Terminez le workflow d'exception affiché ; l'automatisation ne remplacera pas une saisie humaine.",
            received=event.fixing_status,
        )
        return False, _auto_yahoo_exception(
            deal, event, [failure], session, actor_user_id)

    evidence, evidence_payload, evidence_hash = _auto_yahoo_evidence(
        deal, event, underlyings, spots, used_dates,
        str(reference_data.get("fetched_at") or datetime.utcnow().isoformat()),
        reference_data.get("currencies") or {},
        reference_data.get("sources") or {},
    )
    latest = session.exec(
        select(OfficialFixingVersion)
        .where(OfficialFixingVersion.deal_event_id == event.id)
        .order_by(OfficialFixingVersion.version.desc())
    ).first()
    next_version = (latest.version if latest else 0) + 1
    supersedes_id = current_version.id if current_version else None
    observed_date = max(used_dates.values())
    record_payload = {
        **evidence,
        "version": next_version,
        "supersedes_id": supersedes_id,
        "spots": spots,
        "evidence_sha256": evidence_hash,
        "capture_actor_type": "PROCESS",
    }
    record_hash = _fixing_record_hash(record_payload)

    # A changed Yahoo value is never allowed to overwrite an already official
    # fact silently.  Archive the new provider record and escalate the event.
    if current_version and current_spots != spots:
        revision = OfficialFixingVersion(
            deal_id=deal.id,
            deal_event_id=event.id,
            version=next_version,
            supersedes_id=current_version.id,
            status=FixingStatus.MANUAL_REVIEW_REQUIRED.value,
            spots_json=json.dumps(spots, ensure_ascii=False, sort_keys=True),
            provider="YAHOO_FINANCE",
            source_type="API",
            external_reference=f"YAHOO:{event.event_date}:{','.join(used_dates.values())}",
            observed_at=datetime.fromisoformat(f"{observed_date}T00:00:00"),
            received_at=datetime.utcnow(),
            venue="Yahoo Finance",
            calendar=f"LAST_CLOSE_ON_OR_BEFORE_MAX_{_AUTO_YAHOO_MAX_FALLBACK_DAYS}D",
            timezone="MARKET_LOCAL_DATE",
            evidence_sha256=evidence_hash,
            evidence_filename=f"yahoo-{deal.reference}-{event.event_date}.json",
            evidence_content_type="application/json",
            evidence_size_bytes=len(evidence_payload),
            evidence_payload_b64=base64.b64encode(evidence_payload).decode("ascii"),
            record_sha256=record_hash,
            capture_reason="Correction Yahoo détectée après validation automatique.",
            entered_by=deal.user_id,
            capture_actor_type="PROCESS",
        )
        session.add(revision)
        event.fixing_status = FixingStatus.CONTESTED.value
        session.add(event)
        failure = _workflow_failure(
            "YAHOO_OFFICIAL_REVISION_DETECTED", "spots",
            "Yahoo publie une valeur différente de l’observation déjà validée.",
            expected=current_spots,
            action="Comparez les deux versions et décidez explicitement si le lifecycle doit être rejoué.",
            received=spots,
        )
        return False, _auto_yahoo_exception(
            deal, event, [failure], session, actor_user_id)

    validated_at = datetime.utcnow()
    version = OfficialFixingVersion(
        deal_id=deal.id,
        deal_event_id=event.id,
        version=next_version,
        supersedes_id=supersedes_id,
        status=FixingStatus.VALIDATED.value,
        spots_json=json.dumps(spots, ensure_ascii=False, sort_keys=True),
        provider="YAHOO_FINANCE",
        source_type="API",
        external_reference=f"YAHOO:{event.event_date}:{','.join(used_dates.values())}",
        observed_at=datetime.fromisoformat(f"{observed_date}T00:00:00"),
        received_at=validated_at,
        venue="Yahoo Finance",
        calendar=f"LAST_CLOSE_ON_OR_BEFORE_MAX_{_AUTO_YAHOO_MAX_FALLBACK_DAYS}D",
        timezone="MARKET_LOCAL_DATE",
        evidence_sha256=evidence_hash,
        evidence_filename=f"yahoo-{deal.reference}-{event.event_date}.json",
        evidence_content_type="application/json",
        evidence_size_bytes=len(evidence_payload),
        evidence_payload_b64=base64.b64encode(evidence_payload).decode("ascii"),
        record_sha256=record_hash,
        capture_reason="Validation automatique de la clôture Yahoo non ajustée.",
        entered_by=deal.user_id,
        capture_actor_type="PROCESS",
        validation_reason="Contrôles AUTO_YAHOO passés.",
        validated_at=validated_at,
    )
    session.add(version)
    session.flush()
    event.spots_json = json.dumps(spots, ensure_ascii=False, sort_keys=True)
    event.source = "auto"
    event.status = "observé"
    event.fixing_status = FixingStatus.VALIDATED.value
    event.data_category = DataCategory.FIXING_OFFICIAL.value
    event.current_fixing_version_id = version.id
    event.fixing_version = version.version
    event.fixing_entered_by = deal.user_id
    event.fixing_entered_at = validated_at
    event.fixing_provider = version.provider
    event.fixing_source_type = version.source_type
    event.fixing_external_reference = version.external_reference
    event.fixing_observed_at = version.observed_at
    event.fixing_venue = version.venue
    event.fixing_calendar = version.calendar
    event.fixing_timezone = version.timezone
    event.fixing_evidence_sha256 = version.evidence_sha256
    event.fixing_record_sha256 = version.record_sha256
    event.fixing_reason = version.capture_reason
    event.validated_by = None
    event.validated_at = validated_at
    session.add(event)
    record_audit_event(
        session,
        action="FIXING_AUTO_VALIDATED",
        object_type="DEAL_EVENT",
        object_id=event.id,
        actor_user_id=actor_user_id,
        actor_type="USER" if actor_user_id else "PROCESS",
        result="SUCCESS",
        before=before,
        after=_event_row(event),
        reason="Clôture Yahoo non ajustée validée par les contrôles automatiques.",
        data_source=DataCategory.FIXING_OFFICIAL,
        metadata={
            "policy": FixingPolicy.AUTO_YAHOO.value,
            "provider": "YAHOO_FINANCE",
            "price_type": "UNADJUSTED_CLOSE",
            "price_dates": used_dates,
            "provider_currencies": reference_data.get("currencies") or {},
            "fixing_version_id": version.id,
        },
    )
    return True, None


def _auto_review_proposal(
    deal: Deal,
    evaluation: dict,
    failures: list[dict],
    session: Session,
    actor_user_id: int | None,
) -> LifecycleProposal:
    fingerprint = hashlib.sha256(
        json.dumps(failures, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]
    dedup_key = (
        f"auto-lifecycle-review:{deal.id}:{evaluation.get('event_id')}:"
        f"{evaluation.get('outcome')}:{fingerprint}"
    )
    existing = session.exec(
        select(LifecycleProposal).where(LifecycleProposal.dedup_key == dedup_key)
    ).first()
    if existing:
        return existing
    proposal = LifecycleProposal(
        deal_id=deal.id,
        event_id=evaluation.get("event_id"),
        dedup_key=dedup_key,
        status=LifecycleStatus.MANUAL_REVIEW_REQUIRED.value,
        proposed_outcome=str(evaluation.get("outcome")),
        result_json=json.dumps(evaluation, ensure_ascii=False, sort_keys=True),
        data_source=DataCategory.FIXING_OFFICIAL.value,
        proposed_by=actor_user_id,
        error_message=json.dumps(failures, ensure_ascii=False, sort_keys=True),
    )
    session.add(proposal)
    session.flush()
    _ensure_alert(
        session,
        deal,
        "auto_lifecycle_exception",
        f"Résolution automatique bloquée pour {deal.reference}; contrôle requis.",
        f"auto-lifecycle-review:{proposal.dedup_key}",
    )
    record_audit_event(
        session,
        action="RESOLUTION_AUTO_REVIEW_REQUIRED",
        object_type="LIFECYCLE_PROPOSAL",
        object_id=proposal.id,
        actor_user_id=actor_user_id,
        actor_type="USER" if actor_user_id else "PROCESS",
        result="REJECTED",
        after=_proposal_row(proposal),
        reason="Le replay automatique ne satisfait pas tous les contrôles.",
        data_source=DataCategory.FIXING_OFFICIAL,
        metadata={"failures": failures, "policy": deal.fixing_policy},
    )
    return proposal


def _auto_apply_lifecycle(
    deal: Deal,
    evaluation: dict | None,
    session: Session,
    actor_user_id: int | None,
) -> LifecycleProposal | None:
    if not evaluation or evaluation.get("outcome") == "en_cours":
        return None
    outcome = str(evaluation.get("outcome"))
    if outcome not in {"callé", "ki", "final"}:
        return _auto_review_proposal(
            deal, evaluation,
            [_workflow_failure(
                "AUTO_OUTCOME_UNSUPPORTED", "evaluation.outcome",
                "Le moteur automatique a produit un résultat terminal non supporté.",
                expected="callé, ki ou final",
                action="Contrôlez le script et la proposition lifecycle.",
                received=outcome,
            )],
            session, actor_user_id,
        )
    events = _get_events(deal.id, session)
    trigger = next(
        (event for event in events if event.id == evaluation.get("event_id")), None)
    required_events = (
        [event for event in events if event.t_years <= trigger.t_years + 1e-6]
        if trigger else []
    )
    failures: list[dict] = []
    if not trigger or not required_events:
        failures.append(_workflow_failure(
            "LIFECYCLE_TRIGGER_EVENT_MISSING", "evaluation.event_id",
            "Le résultat Yahoo ne référence pas une constatation contractuelle.",
            expected="Un identifiant d'événement du deal.",
            action="Rejouez le monitoring depuis le calendrier contractuel gelé.",
            received=evaluation.get("event_id"),
        ))
    for event in required_events:
        if (event.fixing_status != FixingStatus.VALIDATED.value or
                event.data_category != DataCategory.FIXING_OFFICIAL.value):
            failures.append(_workflow_failure(
                "AUTO_FIXING_NOT_OFFICIAL", f"event.{event.id}.fixing_status",
                "Une constatation requise n'a pas passé les contrôles Yahoo.",
                expected=FixingStatus.VALIDATED.value,
                action="Traitez l'exception affichée sur cette constatation.",
                received=event.fixing_status,
            ))
    official_result = None
    if not failures:
        official_result, replay_failures = replay_official_fixings(
            deal, required_events)
        failures.extend(replay_failures)
    if official_result and official_result.get("outcome") != outcome:
        failures.append(_workflow_failure(
            "AUTO_REPLAY_OUTCOME_MISMATCH", "evaluation.outcome",
            "Le replay des fixings Yahoo diverge du monitoring historique.",
            expected=official_result.get("outcome"),
            action="Contrôlez le produit et les fixings avant toute application.",
            received=outcome,
        ))
    if official_result:
        expected_payout = official_result.get("realized_payout")
        monitored_payout = evaluation.get("realized_payout")
        if expected_payout is not None and monitored_payout is not None:
            difference = abs(float(expected_payout) - float(monitored_payout))
            tolerance, monetary_tolerance = _payout_reconciliation_tolerance(deal)
            if difference > tolerance:
                failures.append(_workflow_failure(
                    "AUTO_REPLAY_PAYOUT_MISMATCH", "evaluation.realized_payout",
                    "Le payout Yahoo diverge du rejeu des observations validées au-delà de la tolérance monétaire.",
                    expected=f"Écart ≤ {tolerance:.12g} ({monetary_tolerance:.6g} {deal.devise}).",
                    action="Contrôlez le script et les fixings avant application.",
                    received={
                        "monitoring": monitored_payout,
                        "official": expected_payout,
                        "difference": difference,
                    },
                ))
    if failures:
        return _auto_review_proposal(
            deal, evaluation, failures, session, actor_user_id)

    input_hash = official_input_hash(deal, required_events)
    dedup_key = (
        f"auto-lifecycle:{deal.id}:{trigger.id}:{outcome}:{input_hash[:16]}"
    )
    existing = session.exec(
        select(LifecycleProposal).where(LifecycleProposal.dedup_key == dedup_key)
    ).first()
    if existing:
        return existing
    now = datetime.utcnow()
    proposal = LifecycleProposal(
        deal_id=deal.id,
        event_id=trigger.id,
        dedup_key=dedup_key,
        status=LifecycleStatus.APPLIED.value,
        proposed_outcome=outcome,
        result_json=json.dumps(evaluation, ensure_ascii=False, sort_keys=True),
        data_source=DataCategory.FIXING_OFFICIAL.value,
        official_result_json=json.dumps(
            official_result, ensure_ascii=False, sort_keys=True),
        official_input_hash=input_hash,
        official_replayed_at=now,
        comparison_status="MATCH",
        validated_at=now,
        validation_reason="Contrôles automatiques AUTO_YAHOO passés.",
        applied_at=now,
        correlation_id=f"auto-yahoo:{deal.id}:{trigger.id}:{input_hash[:16]}",
        updated_at=now,
    )
    session.add(proposal)
    session.flush()
    before_deal = _deal_row(deal)
    trigger.status = outcome
    deal.status, deal.settlement_amount = _terminal_deal_state(
        deal, outcome, official_result, business_today())
    deal.realized_payout = official_result.get("realized_payout")
    deal.resolution_outcome = outcome
    deal.settlement_date = official_result.get('settlement_date')
    deal.updated_at = now
    session.add(deal)
    if outcome == "callé":
        for event in events:
            if event.t_years > trigger.t_years + 1e-6:
                event.status = "annulé"
                session.add(event)
    for event in required_events:
        event.fixing_status = FixingStatus.APPLIED.value
        event.applied_at = now
        session.add(event)
        version = (
            session.get(OfficialFixingVersion, event.current_fixing_version_id)
            if event.current_fixing_version_id else None
        )
        if version:
            version.status = FixingStatus.APPLIED.value
            version.applied_at = now
            session.add(version)
        record_audit_event(
            session,
            action="FIXING_AUTO_APPLIED",
            object_type="DEAL_EVENT",
            object_id=event.id,
            actor_user_id=actor_user_id,
            actor_type="USER" if actor_user_id else "PROCESS",
            result="SUCCESS",
            after=_event_row(event),
            reason="Fixing Yahoo consommé par la résolution automatique.",
            data_source=DataCategory.FIXING_OFFICIAL,
            metadata={"proposal_id": proposal.id, "policy": deal.fixing_policy},
        )
    for stale in session.exec(select(LifecycleProposal).where(
        LifecycleProposal.deal_id == deal.id,
        LifecycleProposal.id != proposal.id,
        LifecycleProposal.status.in_([
            LifecycleStatus.PROPOSED.value,
            LifecycleStatus.MANUAL_REVIEW_REQUIRED.value,
        ]),
    )).all():
        stale.status = LifecycleStatus.STALE.value
        stale.error_message = "Remplacée par la résolution automatique AUTO_YAHOO."
        stale.updated_at = now
        session.add(stale)
    # A former reconciliation exception is no longer actionable once the same
    # deal has been resolved successfully from authoritative fixings.
    for alert in session.exec(select(Alert).where(
        Alert.deal_id == deal.id,
        Alert.kind == "auto_lifecycle_exception",
        Alert.read == False,  # noqa: E712
    )).all():
        alert.read = True
        session.add(alert)
    record_audit_event(
        session,
        action="RESOLUTION_AUTO_APPLIED",
        object_type="LIFECYCLE_PROPOSAL",
        object_id=proposal.id,
        actor_user_id=actor_user_id,
        actor_type="USER" if actor_user_id else "PROCESS",
        result="SUCCESS",
        before={"deal": before_deal},
        after={"deal": _deal_row(deal), "proposal": _proposal_row(proposal)},
        reason="Résolution appliquée automatiquement depuis les observations Yahoo validées.",
        data_source=DataCategory.FIXING_OFFICIAL,
        correlation_id=proposal.correlation_id,
        metadata={"policy": deal.fixing_policy, "official_result": official_result},
    )
    _ensure_alert(
        session,
        deal,
        "resolution_auto_applied",
        f"Résolution {outcome!r} appliquée automatiquement pour {deal.reference}.",
        f"resolution-auto:{proposal.dedup_key}",
    )
    return proposal


def _refresh_auto_yahoo_deal_core(
    deal: Deal,
    session: Session,
    actor_user_id: int | None,
    underlyings: list[dict],
    tickers: list[str],
) -> dict:
    if deal.status != "actif":
        return {
            "updated": 0,
            "officialized": 0,
            "exceptions": [],
            "message": "Deal déjà résolu : aucune constatation à actualiser.",
            "evaluation": None,
            "proposal": None,
        }
    today = business_today().isoformat()
    events = _get_events(deal.id, session)
    past_events = [event for event in events if event.event_date <= today]
    if not past_events:
        return {
            "updated": 0,
            "officialized": 0,
            "exceptions": [],
            "message": "Aucun événement contractuel atteint.",
            "evaluation": None,
            "proposal": None,
        }
    fetch_start = (
        min(date.fromisoformat(event.event_date) for event in past_events)
        - timedelta(days=7)
    ).isoformat()
    reference_data = load_yahoo_reference_closes(tickers, fetch_start, today)
    if "error" in reference_data and not any(
            event.current_fixing_version_id and event.fixing_status in {
                FixingStatus.VALIDATED.value, FixingStatus.APPLIED.value}
            for event in past_events):
        raise ValueError(reference_data["error"])
    officialized = 0
    exceptions: list[dict] = []
    official_prefix: list[DealEvent] = []
    official_evaluation = None
    replay_failures: list[dict] = []
    # Contractual observations are consumed in order.  As soon as their
    # authoritative prefix proves an autocall/maturity, later rows no longer
    # belong to the life of the product and must neither be validated nor
    # generate fallback alerts.
    for event in sorted(past_events, key=lambda row: (row.t_years, row.event_index)):
        changed, exception = _auto_validate_yahoo_event(
            deal, event, underlyings, reference_data, session, actor_user_id)
        officialized += int(changed)
        if exception:
            exceptions.append(exception)
            break
        if (event.fixing_status != FixingStatus.VALIDATED.value or
                event.data_category != DataCategory.FIXING_OFFICIAL.value):
            break
        official_prefix.append(event)
        official_evaluation, replay_failures = replay_official_fixings(
            deal, official_prefix)
        if (official_evaluation and
                official_evaluation.get("outcome") != "en_cours"):
            break
    dates, prices = _reference_history_arrays(reference_data, tickers)
    if not dates and official_evaluation is None and not reference_data.get("error"):
        from ...services.scenario_market import configured_path
        if configured_path():
            # Preserve the real missing-source exception for a subsequent
            # signed manual decision. Synthetic prices never become Yahoo.
            record_audit_event(session, action="SCENARIO_FIXING_EXCEPTION_OPENED",
                object_type="DEAL", object_id=deal.id, actor_user_id=actor_user_id,
                result="PENDING", reason="Scénario synthétique : source Yahoo absente, décision utilisateur sourcée requise.")
            session.commit()
            return {"updated":0,"officialized":0,"exceptions":exceptions,"evaluation":None,"proposal":None,
                "message":"Source Yahoo absente dans ce scénario ; déclarer le fixing synthétique par une décision utilisateur sourcée.",
                "monitoring_source":"SYNTHETIC_SCENARIO","policy":FixingPolicy.AUTO_YAHOO.value}
        raise ValueError("Les clôtures Yahoo ne permettent pas de construire un historique commun")

    # Lifecycle truth comes from the longest contiguous prefix of validated
    # contractual fixings.  The dense Yahoo history remains useful monitoring
    # data and a governed fallback for scripts whose path dependence cannot be
    # established from event fixings alone, but it must not decide an otherwise
    # replayable terminal outcome on dates that differ from the booked calendar.
    if official_prefix and official_evaluation is None:
        official_evaluation, replay_failures = replay_official_fixings(
            deal, official_prefix)
    evaluation = official_evaluation
    if evaluation is None:
        evaluation = (_evaluate_lifecycle(deal, events, dates, prices, tickers)
                      if dates else {"outcome": "en_cours"})
    proposal = _auto_apply_lifecycle(deal, evaluation, session, actor_user_id)
    deal.updated_at = datetime.utcnow()
    session.add(deal)
    stage_product_lifecycle(
        session, deal, actor_user_id=actor_user_id,
        action=("PRODUCT_LIFECYCLE_RESOLUTION_APPLIED"
                if proposal and proposal.status == LifecycleStatus.APPLIED.value
                else "PRODUCT_LIFECYCLE_REFRESHED"),
        reason="Synchronisation après traitement lifecycle automatique.")
    session.commit()
    if exceptions:
        first_failure = exceptions[0]["failures"][0]
        message = (
            f"⚠ {len(exceptions)} constatation(s) non appliquée(s) : "
            f"{first_failure.get('message', first_failure.get('code'))} "
            f"{first_failure.get('action', '')}"
        ).strip()
    elif proposal and proposal.status == LifecycleStatus.APPLIED.value:
        message = (
            f"✓ {officialized} constatation(s) Yahoo validée(s) ; "
            f"résolution {proposal.proposed_outcome} appliquée automatiquement."
        )
    elif proposal and proposal.status == LifecycleStatus.MANUAL_REVIEW_REQUIRED.value:
        message = (
            f"⚠ {officialized} constatation(s) Yahoo validée(s), "
            "mais la résolution requiert un contrôle manuel."
        )
    else:
        message = (
            f"✓ {officialized} constatation(s) Yahoo validée(s) ; "
            "le produit reste en vie."
        )
    if reference_data.get("error"):
        message = f"Flux indisponible : {reference_data['error']}. Les fixings officiels sont conservés. " + message
    return {
        "monitoring_error": reference_data.get("error"),
        "updated": officialized,
        "officialized": officialized,
        "exceptions": exceptions,
        "message": message,
        "evaluation": evaluation,
        "proposal": _proposal_row(proposal) if proposal else None,
        "official_replay_failures": replay_failures,
        "policy": FixingPolicy.AUTO_YAHOO.value,
    }
