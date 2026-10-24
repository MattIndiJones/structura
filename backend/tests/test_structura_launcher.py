"""Launcher selection, legacy entry point and precise process ownership."""
import runpy
import sys

import pytest
from backend.app.hybrid import launcher


@pytest.fixture
def menu(tmp_path, monkeypatch):
    controller = launcher.Launcher(tmp_path / "manual", 8230)
    active, started, stopped, urls = {}, [], [], []
    def start(config, developer_access=False, launcher_id=None):
        reused = config.key in active
        active[config.key] = config
        if not reused: started.append(config.key)
        return {"key":config.key,"started":not reused,"reused":reused}
    def stop(config, **kwargs):
        active.pop(config.key,None); stopped.append(config.key)
        return {"key":config.key,"stopped":True,"process_exited":True,"port_released":True}
    monkeypatch.setattr(launcher,"start",start)
    monkeypatch.setattr(launcher,"stop",stop)
    monkeypatch.setattr(launcher,"probe",lambda config: {"process_id":12} if config.key in active else None)
    monkeypatch.setattr(launcher,"stop_candidate",lambda config: config.key in active)
    monkeypatch.setattr(launcher.webbrowser,"open",lambda url:urls.append(url))
    return controller, active, started, stopped, urls


def test_menu_choices_start_only_needed_services_and_reuse_them(menu):
    controller, active, started, stopped, urls = menu
    controller.launch("admin")
    assert set(active) == {"platform","admin-workbench"}
    assert urls[-1].startswith("http://127.0.0.1:8000/#/login?development_admin=1")
    controller.launch("organization","leonteq")
    assert set(active) == {"platform","admin-workbench","leonteq"}
    assert "organization=leonteq" in urls[-1]
    controller.launch("simulation")
    assert "simulation" not in active and "next=/agent-workshop" in urls[-1]
    controller.launch("all")
    assert len([key for key in active if key not in {"platform","admin-workbench"}]) == 6
    assert started.count("platform") == 1
    assert all(row["running"] for row in controller.status() if row["key"] != "simulation")
    controller.launch("platform")
    assert "console=1" in urls[-1]
    controller.stop()
    assert not active and set(stopped) == set(started)
    assert "simulation" not in stopped


def test_failed_partial_launch_only_stops_newly_created_services(menu, monkeypatch):
    controller, active, started, stopped, urls = menu
    controller.launch("admin", open_browser=False)
    original = launcher.start
    def fail(config, **kwargs):
        if config.key == "societe-generale": raise RuntimeError("test failure")
        return original(config, **kwargs)
    monkeypatch.setattr(launcher,"start",fail)
    with pytest.raises(RuntimeError,match="test failure"):
        controller.launch("all")
    assert stopped == ["bnp-paribas"]
    assert set(active) == {"platform","admin-workbench"}
    assert not urls


def test_occupied_admin_port_does_not_replace_its_occupant_or_block_portal(menu, monkeypatch):
    controller, active, started, stopped, urls = menu
    original = launcher.start
    def fail(config, **kwargs):
        if config.key == "admin-workbench": raise RuntimeError("Port occupé")
        return original(config, **kwargs)
    monkeypatch.setattr(launcher,"start",fail)
    with pytest.raises(RuntimeError, match="Port occupé"):
        controller.launch("admin")
    controller.launch("platform")
    assert active["platform"] and "admin-workbench" not in active
    assert not stopped


def test_backend_without_explicit_environment_opens_launcher(monkeypatch):
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    sys.path.insert(0,str(root / "backend"))
    from app.hybrid import launcher as entry_launcher
    invoked = []
    monkeypatch.delenv("STRUCTURA_INSTALLATION_CONFIG",raising=False)
    monkeypatch.delenv("STRUCTURA_DATA_DIR",raising=False)
    monkeypatch.setattr(entry_launcher,"main",lambda:invoked.append(True))
    runpy.run_path(str(root / "backend" / "run.py"),run_name="__main__")
    assert invoked == [True]


def test_full_admin_has_its_own_manifest_and_separate_data_directory(menu):
    controller = menu[0]
    config = controller.controls["admin-workbench"]
    assert config.service == "admin_workbench" and config.port == 8000
    assert config.data_dir not in {item.data_dir for item in controller.configs}
    assert (config.data_dir / ".bootstrap_credentials.json").exists()
    assert not (config.data_dir / "structura.db").exists()


@pytest.mark.parametrize("key", ["bnp-paribas", "societe-generale", "citi", "ubs", "leonteq", "kepler-cheuvreux-solutions"])
def test_each_organization_shortcut_opens_its_own_superuser_route(menu, key):
    controller, active, started, stopped, urls = menu
    result = controller.launch("organization", key)
    assert set(active) == {"platform", key}
    assert result["url"] == "http://127.0.0.1:8230/#/login?organization=" + key
    controller.launch("organization", key)
    assert started.count(key) == 1 and started.count("platform") == 1


def test_console_shortcut_remains_separate_from_full_admin(menu):
    controller, active, started, stopped, urls = menu
    controller.launch("platform")
    assert set(active) == {"platform"}
    assert urls == ["http://127.0.0.1:8230/#/login?console=1&next=/platform"]


def test_simulation_shortcut_opens_admin_screen_without_campaign_or_controller(menu):
    controller, active, started, stopped, urls = menu
    controller.launch("simulation")
    assert set(active) == {"platform", "admin-workbench"}
    assert urls == ["http://127.0.0.1:8000/#/login?development_admin=1&next=/agent-workshop"]
    assert not list(controller.root.glob("*/campaigns/*"))


def test_acceptance_failure_cleans_admin_and_controller_but_preserves_existing_portal(menu, monkeypatch):
    from scripts import check_structura_launcher as acceptance
    controller = menu[0]
    for config in (controller.platform, *controller.controls.values()):
        (config.data_dir / ".process.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(acceptance, "Launcher", lambda *args: controller)
    monkeypatch.setattr(acceptance, "probe", lambda config: {"process_id": 1} if config.key == "platform" else None)
    monkeypatch.setattr(controller, "launch", lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("expected failure")))
    cleaned = []
    monkeypatch.setattr(controller, "stop", lambda only: cleaned.extend(c.key for c in only) or [])
    proof = controller.root / "separate-proof.json"
    with pytest.raises(RuntimeError, match="expected failure"):
        acceptance.check(controller.root, 8230, evidence_path=proof)
    assert set(cleaned) == {"admin-workbench", "simulation"}
    assert proof.exists() and not (controller.root / "launcher-acceptance.json").exists()
