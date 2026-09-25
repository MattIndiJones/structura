"""The shared catalogue keeps old labels readable and new entries consistent."""

import pytest

from backend.app.core.payoff_families import (
    PAYOFF_FAMILIES, canonical_payoff_family, normalize_new_payoff_family,
)


def test_legacy_labels_group_into_one_primary_family():
    assert canonical_payoff_family("ATHENA") == "Autocall"
    assert canonical_payoff_family("Autocall Athena") == "Autocall"
    assert canonical_payoff_family("Phoenix Memory") == "Phoenix"
    assert canonical_payoff_family("CAPITAL_GUARANTEED") == "Capital protégé"
    assert canonical_payoff_family("Shark") == "Capital protégé"
    assert canonical_payoff_family("Call") == "Option"
    assert canonical_payoff_family("unknown") is None


def test_new_values_are_canonical_and_other_has_a_description():
    assert normalize_new_payoff_family("ATHENA") == "Autocall"
    assert normalize_new_payoff_family("Autre", "Payoff sur mesure") == "Autre"
    with pytest.raises(ValueError, match="Famille de payoff inconnue"):
        normalize_new_payoff_family("custom payoff")
    with pytest.raises(ValueError, match="Décrivez le payoff"):
        normalize_new_payoff_family("Autre")


def test_catalogue_names_and_aliases_are_unambiguous():
    for family in PAYOFF_FAMILIES:
        for name in (family["code"], family["label"], *family["aliases"],
                     *family["model_keys"]):
            assert canonical_payoff_family(name) == family["label"]
