"""Shared quote/decision identity and currency checks against frozen Product terms."""
from .product_repository import load_product


def request_currency(session, rfq):
    product = load_product(session, rfq.product_id, terms_version=rfq.product_terms_version)
    return str(product.terms.settlement_ccy or '').strip().upper()


def effective_currency(session, rfq, quote):
    return str(quote.currency or request_currency(session, rfq)).strip().upper()


def same_currency(session, rfq, quote):
    expected = request_currency(session, rfq)
    return bool(expected) and effective_currency(session, rfq, quote) == expected


def clear_selection(rfq):
    rfq.selected_quote_id = None
    rfq.selected_quote_revision = None
    rfq.selection_reason_code = None
    rfq.selection_reason_note = None


def selection_matches(rfq, quote):
    return rfq.selected_quote_id == quote.id and rfq.selected_quote_revision == quote.revision
