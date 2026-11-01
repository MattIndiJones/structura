"""Published capabilities must match existing Admin rights, without broadening managed access."""
from types import SimpleNamespace

import pytest

from backend.app.core.access import capabilities, has_capability


@pytest.mark.parametrize("kind", [None, "organization", "platform"])
@pytest.mark.parametrize("active", [False, True])
def test_technical_admin_only_publishes_business_rights_in_standalone_workspace(monkeypatch, kind, active):
    monkeypatch.setattr("backend.app.hybrid.config.current_config",
                        lambda: None if kind is None else SimpleNamespace(kind=kind))
    user = SimpleNamespace(role="admin", is_active=active)
    published = capabilities(user)
    for right in ("business.price", "business.prepare", "book", "operations.prepare",
                  "operations.validate", "trading.relationships.manage", "trading.settle"):
        expected = active and kind is None
        assert (right in published) == expected
        assert has_capability(user, right) == expected


@pytest.mark.parametrize("role,price,book", [
    ("user", True, False), ("ops_maker", False, True),
    ("checker", False, False), ("organization_admin", True, True),
    ("platform_admin", False, False),
])
def test_business_profiles_keep_their_existing_explicit_rights(monkeypatch, role, price, book):
    monkeypatch.setattr("backend.app.hybrid.config.current_config", lambda: SimpleNamespace(kind="organization"))
    user = SimpleNamespace(role=role, is_active=True)
    assert ("business.price" in capabilities(user)) == price
    assert has_capability(user, "business.price") == price
    assert ("book" in capabilities(user)) == book
    assert has_capability(user, "book") == book
