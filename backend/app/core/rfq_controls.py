"""Central RFQ readiness, pricing-integrity and booking controls."""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from typing import Any

from ..db.models import RfqQuote, RfqRequest
from .payscript.parser import parse_script, resolve_constats
from .workflow import QuoteFirmness


MODEL_PRICE_MAX_AGE_MINUTES = max(
    1, int(os.getenv("STRUCTURA_RFQ_MODEL_PRICE_MAX_AGE_MINUTES", "60")))


@dataclass(frozen=True)
class ControlFailure:
    code: str
    message: str

    def as_dict(self) -> dict:
        return asdict(self)


def failures_payload(failures: list[ControlFailure]) -> dict:
    return {
        "code": "BOOKING_GATE_FAILED",
        "message": "Booking refusé : certains contrôles d'exécution ont échoué.",
        "failures": [failure.as_dict() for failure in failures],
    }


def _normalise(value: Any):
    if isinstance(value, dict):
        return {str(k): _normalise(value[k]) for k in sorted(value)}
    if isinstance(value, list):
        return [_normalise(v) for v in value]
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return value
    if isinstance(value, (int, float)):
        return round(float(value), 12)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)


def product_terms(script_snapshot: str, params: dict | None) -> dict:
    """Canonical contractual identity, excluding model assumptions."""
    p = params or {}
    underlyings = [
        {k: u.get(k) for k in ("name", "ticker", "ccy") if k in u}
        for u in (p.get("underlyings") or [])
    ]
    terms = {
        "script_snapshot": "\n".join(
            line.rstrip()
            for line in (script_snapshot or "").replace("\r\n", "\n").split("\n")
        ).strip(),
    }
    if "underlyings" in p:
        terms["underlyings"] = underlyings
    if "user_params" in p:
        terms["user_params"] = p.get("user_params") or {}
    if "constats" in p:
        terms["constats"] = p.get("constats") or {}
    for key in ("notional", "currency", "strike_date", "value_date",
                "payment_date", "T"):
        if key in p:
            terms[key] = p[key]
    return _normalise(terms)


def _hash(value: dict) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def product_terms_hash(terms: dict) -> str:
    return _hash(_normalise(terms))


def pricing_input_hash(script_snapshot: str, params: dict | None) -> str:
    """Hash every persisted input capable of changing the model price."""
    return _hash(_normalise({
        "script_snapshot": "\n".join(
            line.rstrip()
            for line in (script_snapshot or "").replace("\r\n", "\n").split("\n")
        ).strip(),
        "params": params or {},
    }))


def _valid_iso_date(value: Any) -> bool:
    try:
        date.fromisoformat(str(value))
        return True
    except (TypeError, ValueError):
        return False


def rfq_readiness_failures(rfq: RfqRequest) -> list[ControlFailure]:
    """Validate the minimum executable product definition persisted on an RFQ."""
    failures: list[ControlFailure] = []
    try:
        params = json.loads(rfq.params_json or "{}")
    except (TypeError, ValueError):
        return [ControlFailure("RFQ_PARAMS_INVALID", "Les paramètres RFQ ne sont pas un JSON valide.")]

    if rfq.kind != "to_trade":
        failures.append(ControlFailure(
            "RFQ_NOT_EXECUTABLE", "Une RFQ indicative ne peut pas être bookée."))
    if not (rfq.script_snapshot or "").strip():
        failures.append(ControlFailure("SCRIPT_MISSING", "Le script contractuel est absent."))

    underlyings = params.get("underlyings") or []
    if not underlyings:
        failures.append(ControlFailure("UNDERLYINGS_MISSING", "Aucun sous-jacent n'est défini."))
    else:
        for idx, underlying in enumerate(underlyings, start=1):
            missing = [key for key in ("name", "ticker", "ccy")
                       if not str(underlying.get(key) or "").strip()]
            if missing:
                failures.append(ControlFailure(
                    "UNDERLYING_INCOMPLETE",
                    f"Sous-jacent {idx} incomplet : {', '.join(missing)}."))

    notional = params.get("notional")
    if not isinstance(notional, (int, float)) or isinstance(notional, bool) or notional <= 0:
        failures.append(ControlFailure(
            "NOTIONAL_INVALID", "Le nominal RFQ doit être strictement positif."))
    currency = str(params.get("currency") or "").strip().upper()
    if len(currency) != 3 or not currency.isalpha():
        failures.append(ControlFailure(
            "CURRENCY_INVALID", "La devise RFQ doit être un code ISO à trois lettres."))
    if not _valid_iso_date(params.get("strike_date")):
        failures.append(ControlFailure("STRIKE_DATE_INVALID", "La date de strike RFQ est absente ou invalide."))
    if not _valid_iso_date(params.get("value_date")):
        failures.append(ControlFailure("VALUE_DATE_INVALID", "La date de valeur RFQ est absente ou invalide."))
    if not _valid_iso_date(params.get("payment_date")):
        failures.append(ControlFailure(
            "PAYMENT_DATE_INVALID",
            "La date de paiement RFQ est absente ou invalide — c'est elle qui date "
            "l'échange final des flux, et elle ne se déduit d'aucun fixing."))
    # L'écart entre strike et value date n'est PAS contraint : il vaut deux jours
    # ouvrés dans le cas courant, mais un forward start verse le nominal avant
    # que le niveau de référence soit fixé, et un départ décalé peut mettre des
    # semaines entre les deux. C'est une décision commerciale, pas une règle —
    # le moteur sait actualiser dans les deux sens (engine._df_at_time).
    # Seul l'ordre du règlement final reste contraint : le dernier échange de
    # cash ne peut pas précéder le premier.
    _value, _payment = params.get("value_date"), params.get("payment_date")
    if all(_valid_iso_date(d) for d in (_value, _payment)) and _payment < _value:
        failures.append(ControlFailure(
            "DATES_OUT_OF_ORDER",
            f"La date de paiement ({_payment}) précède la date de valeur ({_value})."))
    tenor = params.get("T")
    if not isinstance(tenor, (int, float)) or isinstance(tenor, bool) or tenor <= 0:
        failures.append(ControlFailure("TENOR_INVALID", "La maturité T de la RFQ doit être positive."))

    if rfq.script_snapshot:
        try:
            compiled = parse_script(rfq.script_snapshot)
            # Le calendrier se compte depuis la constatation initiale : c'est
            # là que le produit commence, pas au règlement.
            anchor = (date.fromisoformat(params["strike_date"])
                      if _valid_iso_date(params.get("strike_date")) else None)
            resolve_constats(compiled, params.get("constats") or {}, anchor=anchor,
                             currency=str(params.get("currency") or "").strip().upper() or None)
        except (KeyError, TypeError, ValueError) as exc:
            failures.append(ControlFailure(
                "CONTRACT_CALENDAR_INVALID",
                f"Le calendrier contractuel n'est pas exploitable : {exc}."))
    return failures

def booking_gate_failures(
    rfq: RfqRequest,
    selected: RfqQuote | None,
    *,
    expected_counterparty: str | None,
    requested_counterparty: str,
    now: datetime | None = None,
) -> list[ControlFailure]:
    """Return every independent pre-booking failure in one response."""
    failures = rfq_readiness_failures(rfq)
    now = now or datetime.utcnow()

    if rfq.status != "retenue":
        failures.append(ControlFailure(
            "RFQ_STATUS_INVALID",
            "La RFQ doit être au statut sélectionné avant booking."))
    if selected is None:
        failures.append(ControlFailure(
            "QUOTE_NOT_SELECTED", "Aucune quote sélectionnée n'est disponible."))
    else:
        if selected.price is None:
            failures.append(ControlFailure("QUOTE_PRICE_MISSING", "La quote sélectionnée n'a pas de prix."))
        if selected.status != "recu":
            failures.append(ControlFailure(
                "QUOTE_STATUS_INVALID", "La quote sélectionnée n'est pas au statut reçu."))
        if selected.firmness != QuoteFirmness.FIRM.value:
            failures.append(ControlFailure(
                "QUOTE_NOT_FIRM", "La quote sélectionnée doit être explicitement ferme."))
        if selected.valid_until is None:
            failures.append(ControlFailure(
                "QUOTE_VALIDITY_UNKNOWN", "La validité de la quote sélectionnée est inconnue."))
        elif selected.valid_until <= now:
            failures.append(ControlFailure(
                "QUOTE_EXPIRED", "La quote sélectionnée a expiré."))

    if not expected_counterparty:
        failures.append(ControlFailure(
            "PROVIDER_COUNTERPARTY_UNMAPPED",
            "Le fournisseur retenu n'est relié à aucune contrepartie active."))
    elif requested_counterparty != expected_counterparty:
        failures.append(ControlFailure(
            "COUNTERPARTY_MISMATCH",
            f"La contrepartie attendue est {expected_counterparty}."))

    if rfq.model_price is None or rfq.model_price <= 0:
        failures.append(ControlFailure(
            "MODEL_PRICE_MISSING", "Un prix modèle positif est requis avant booking."))
    if rfq.model_price_at is None:
        failures.append(ControlFailure(
            "MODEL_PRICE_TIMESTAMP_MISSING", "La date du prix modèle est absente."))
    elif rfq.model_price_at < now - timedelta(minutes=MODEL_PRICE_MAX_AGE_MINUTES):
        failures.append(ControlFailure(
            "MODEL_PRICE_STALE",
            f"Le prix modèle dépasse sa validité de {MODEL_PRICE_MAX_AGE_MINUTES} minutes."))

    try:
        params = json.loads(rfq.params_json or "{}")
    except (TypeError, ValueError):
        params = {}
    current_hash = pricing_input_hash(rfq.script_snapshot, params)
    if not rfq.model_input_hash:
        failures.append(ControlFailure(
            "MODEL_INPUT_HASH_MISSING",
            "Le prix modèle n'est relié à aucun snapshot d'inputs vérifiable."))
    elif rfq.model_input_hash != current_hash:
        failures.append(ControlFailure(
            "MODEL_INPUTS_CHANGED",
            "Les inputs ont changé depuis le dernier pricing."))
    return failures
