"""Shared payoff classification for Opportunity, RFQ and Deal.

Historical rows keep their original text. This module classifies them for
reporting and canonicalizes newly written values without rewriting history.
"""

from __future__ import annotations

import json
import unicodedata
from pathlib import Path


_CATALOGUE = json.loads(
    (Path(__file__).resolve().parents[3] / "shared" / "payoffFamilies.json")
    .read_text(encoding="utf-8")
)
PAYOFF_FAMILIES = tuple(_CATALOGUE["families"])


def _key(value: str | None) -> str:
    decomposed = unicodedata.normalize("NFKD", str(value or ""))
    without_accents = "".join(
        char for char in decomposed if not unicodedata.combining(char)
    )
    return " ".join(without_accents.casefold().replace("_", " ")
                    .replace("-", " ").split())


_BY_NAME = {
    _key(value): family["label"]
    for family in PAYOFF_FAMILIES
    for value in (family["code"], family["label"], *family["aliases"],
                  *family["model_keys"])
}


def canonical_payoff_family(value: str | None) -> str | None:
    """Known legacy label/code/template -> canonical family; unknown -> None."""
    return _BY_NAME.get(_key(value))


def normalize_new_payoff_family(
    value: str | None, description: str | None = None,
) -> str | None:
    """Normalize a supplied value without inventing a family for an unknown."""
    if not value or not str(value).strip():
        return None
    canonical = canonical_payoff_family(value)
    if canonical is None:
        raise ValueError("Famille de payoff inconnue : choisissez une famille du catalogue.")
    if canonical == "Autre" and not str(description or "").strip():
        raise ValueError("Décrivez le payoff lorsque la famille « Autre » est choisie.")
    return canonical
