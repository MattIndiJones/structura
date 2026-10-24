"""Explicit reference-data validation and governance, without external fetching."""
from fastapi import HTTPException
from pydantic import BaseModel, Field, field_validator

# Instrument currencies are independent of supported payment calendars.
REFERENCE_CURRENCIES = frozenset("EUR USD GBP CHF JPY SGD HKD CNY CNH AUD CAD NZD NOK SEK DKK PLN CZK HUF RON BGN TRY ZAR BRL MXN INR KRW TWD THB IDR MYR PHP ILS AED SAR QAR KWD BHD CLP COP PEN".split())


def text_value(value, label):
    if not isinstance(value, str) or not value.strip():
        raise HTTPException(422, f"{label} ne peut pas être vide.")
    return value.strip()


def currency_value(value, *, allow_missing=False):
    if allow_missing and value == "":
        return ""
    if not isinstance(value, str) or value.strip().upper() not in REFERENCE_CURRENCIES:
        raise HTTPException(422, "Devise inconnue du référentiel de cotation ; qualification requise.")
    return value.strip().upper()


class ReferenceChange(BaseModel):
    reason: str = Field(min_length=3, max_length=500)

    @field_validator("reason")
    @classmethod
    def meaningful_reason(cls, value):
        value = value.strip()
        if len(value) < 3:
            raise ValueError("Un motif explicite est requis.")
        return value


def audit_reference(session, actor, action, item, before, after, reason):
    from .audit import record_audit_event
    record_audit_event(session, action=action, object_type=item.__tablename__.upper(), object_id=item.id,
                       actor_user_id=actor.id, result="SUCCESS", before=before, after=after, reason=reason)
