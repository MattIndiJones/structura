"""The native write switch admits only a specifically pinned recipe instance."""

from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import event
from sqlmodel import Session, create_engine

from backend.app.db.models import User
from backend.app.services import native_write_policy as policy


def _actor(username="structurer", *, role="user", active=True, user_id=1):
    return User(id=user_id, username=username, email="fixture@recipe.test",
                password_hash="fixture", role=role, is_active=active)


@pytest.fixture
def recipe(monkeypatch, tmp_path):
    root = (tmp_path / "recipe").resolve()
    root.mkdir()
    (root / "structura.db").touch()
    for name, value in {
        "STRUCTURA_NATIVE_WRITES": "1",
        "STRUCTURA_BOOTSTRAP_PROFILE": "simulation",
        "STRUCTURA_WORKSHOP_CHILD": "1",
        "STRUCTURA_NATIVE_WRITES_USERS": "structurer, second-account",
        "STRUCTURA_DATA_DIR": str(root),
        "STRUCTURA_NATIVE_WRITES_DATA_DIR": str(root),
    }.items():
        monkeypatch.setenv(name, value)
    engine = create_engine(f"sqlite:///{root / 'structura.db'}")

    @event.listens_for(engine, "connect")
    def fail_if_connected(*_args):
        pytest.fail("Native write capability must not open a database connection")

    with Session(engine) as session:
        yield root, session
    engine.dispose()


def test_allows_active_named_pricer_bound_to_the_pinned_simulation(recipe):
    _, session = recipe
    assert policy.native_writes_enabled(_actor(), session)
    assert policy.native_writes_enabled(_actor("second-account"), session)


@pytest.mark.parametrize(("name", "value"), [
    ("STRUCTURA_NATIVE_WRITES", None),
    ("STRUCTURA_NATIVE_WRITES", "true"),
    ("STRUCTURA_BOOTSTRAP_PROFILE", "admin_workbench"),
    ("STRUCTURA_WORKSHOP_CHILD", "0"),
    ("STRUCTURA_INSTALLATION_CONFIG", "missing-installation.json"),
    ("STRUCTURA_ADMIN_WORKBENCH_CONFIG", "missing-workbench.json"),
    ("STRUCTURA_CONSULTATION", "1"),
    ("STRUCTURA_DATA_DIR", "relative"),
    ("STRUCTURA_NATIVE_WRITES_DATA_DIR", None),
    ("STRUCTURA_NATIVE_WRITES_USERS", "*"),
])
def test_rejects_missing_conflicting_or_nonisolated_configuration(recipe, monkeypatch, name, value):
    _, session = recipe
    if value is None:
        monkeypatch.delenv(name)
    else:
        monkeypatch.setenv(name, value)
    assert not policy.native_writes_enabled(_actor(), session)


@pytest.mark.parametrize(("username", "role", "active", "user_id"), [
    ("unknown", "user", True, 2),
    ("STRUCTURER", "user", True, 2),
    ("structurer", "ops_maker", True, 1),
    ("structurer", "user", False, 1),
    ("structurer", "user", True, None),
])
def test_allowlist_does_not_replace_current_business_rights(recipe, username, role, active, user_id):
    _, session = recipe
    assert not policy.native_writes_enabled(_actor(username, role=role, active=active, user_id=user_id), session)


def test_rejects_a_different_database_binding_without_creating_it(recipe):
    root, _ = recipe
    target = root / "different.db"
    engine = create_engine(f"sqlite:///{target}")
    with Session(engine) as session:
        assert not policy.native_writes_enabled(_actor(), session)
    engine.dispose()
    assert not target.exists()
    with Session() as unbound:
        assert not policy.native_writes_enabled(_actor(), unbound)


@pytest.mark.parametrize("marker", ["installation.json", ".hybrid-retired.json"])
def test_rejects_installation_markers_even_with_a_simulation_label(recipe, marker):
    root, session = recipe
    (root / marker).touch()
    assert not policy.native_writes_enabled(_actor(), session)


def test_rejects_pinned_paths_inside_the_private_data_root(recipe, monkeypatch):
    root, session = recipe
    monkeypatch.setattr(policy, "DEFAULT_DATA_DIR", root.parent)
    assert not policy.native_writes_enabled(_actor(), session)


def test_rejects_a_database_redirected_outside_the_pinned_path(recipe, monkeypatch):
    root, session = recipe
    database = root / "structura.db"
    resolve = Path.resolve

    def redirected(path, *args, **kwargs):
        if path == database:
            return root.parent / "other.db"
        return resolve(path, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", redirected)
    assert not policy.native_writes_enabled(_actor(), session)


def test_rejects_a_database_with_multiple_hard_links(recipe, monkeypatch):
    root, session = recipe
    database = root / "structura.db"
    stat = Path.stat

    def linked(path, *args, **kwargs):
        metadata = stat(path, *args, **kwargs)
        if path == database:
            return SimpleNamespace(st_mode=metadata.st_mode, st_nlink=2)
        return metadata

    monkeypatch.setattr(Path, "stat", linked)
    assert not policy.native_writes_enabled(_actor(), session)
