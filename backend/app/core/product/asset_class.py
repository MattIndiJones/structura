"""Asset-class routing for the Product pricer and its consumers."""
from typing import Literal

from .models import NativeTerms, ProductTerms


ProductAsset = Literal["equity", "rates", "credit"]

_NATIVE_ASSET_CLASSES: dict[str, ProductAsset] = {
    "FRN": "rates",
    "IRS": "rates",
    "EXOTIC_RATES": "rates",
    "CDS": "credit",
    "CLN": "credit",
    "EXOTIC_CREDIT": "credit",
}


def product_terms_asset_class(terms: ProductTerms | NativeTerms) -> ProductAsset | None:
    if isinstance(terms, ProductTerms):
        return "equity"
    return _NATIVE_ASSET_CLASSES.get(terms.instrument_type)
