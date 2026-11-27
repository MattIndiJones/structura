"""Launcher selection, legacy entry point and precise process ownership."""
from concurrent.futures import ThreadPoolExecutor
import json
import runpy
import sys
from pathlib import Path
from threading import Barrier, Event, get_ident
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from backend.app.hybrid import deployment, launcher


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


@pytest.fixture
def parallel_menu(menu):
    controller, active, started, stopped, urls = menu
    parallel = launcher.Launcher(controller.root, controller.platform.port, parallel_admin_start=True)
    return parallel, active, started, stopped, urls


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


@pytest.mark.parametrize("action,destination", [("admin", "/"), ("simulation", "/agent-workshop")])
def test_deferred_admin_waits_only_for_admin_then_defers_the_portal(menu, monkeypatch, action, destination):
    legacy, active, started, stopped, urls = menu
    controller = launcher.Launcher(legacy.root, legacy.platform.port, defer_admin_portal=True)
    original_start = launcher.start

    def admin_only(config, **kwargs):
        assert config.key == "admin-workbench"
        return original_start(config, **kwargs)

    def open_admin(url):
        assert set(active) == {"admin-workbench"}
        urls.append(url)

    monkeypatch.setattr(launcher, "start", admin_only)
    monkeypatch.setattr(launcher.webbrowser, "open", open_admin)
    result = controller.launch(action)
    assert started == ["admin-workbench"]
    assert [service["key"] for service in result["services"]] == ["admin-workbench"]
    assert urls == [f"http://127.0.0.1:8000/#/login?development_admin=1&next={destination}"]
    assert not stopped

    monkeypatch.setattr(launcher, "start", original_start)
    console = controller.launch("platform", open_browser=False)
    assert started == ["admin-workbench", "platform"]
    assert [service["key"] for service in console["services"]] == ["platform"]
    assert console["url"].endswith("/#/login?console=1&next=/platform")
    controller.stop()
    assert not active and set(stopped) == {"admin-workbench", "platform"}


def test_deferred_portal_started_from_admin_belongs_to_the_launcher(menu):
    legacy, active, _, stopped, _ = menu
    controller = launcher.Launcher(legacy.root, legacy.platform.port, defer_admin_portal=True)
    controller.launch("admin", open_browser=False)
    assert set(controller.opened) == {"admin-workbench"}

    # An explicit browser request starts the portal outside Launcher.launch.
    portal = controller.platform
    active[portal.key] = portal
    (portal.data_dir / ".process.json").write_text(json.dumps({
        "installation_id": str(portal.installation_id), "launcher_id": controller.launcher_id,
    }), encoding="utf-8")

    controller.stop()
    assert not active and set(stopped) == {"admin-workbench", "platform"}


@pytest.mark.parametrize("action", ["admin", "simulation"])
def test_parallel_admin_starts_both_services_and_preserves_menu_order(parallel_menu, monkeypatch, action):
    controller, active, started, stopped, urls = parallel_menu
    ready = Barrier(2, timeout=4)
    platform_finished = Event()
    original = launcher.start

    def start_together(config, **kwargs):
        assert kwargs == {"developer_access": True, "launcher_id": controller.launcher_id}
        ready.wait()
        if config.key == "admin-workbench":
            assert platform_finished.wait(4)
        result = original(config, **kwargs)
        if config.key == "platform":
            platform_finished.set()
        return result

    monkeypatch.setattr(launcher, "start", start_together)
    result = controller.launch(action)
    assert started == ["platform", "admin-workbench"]
    assert [row["key"] for row in result["services"]] == ["admin-workbench", "platform"]
    assert set(controller.opened) == set(active) == {"admin-workbench", "platform"}
    assert urls == [result["url"]] and not stopped
    assert ("/agent-workshop" in result["url"]) == (action == "simulation")


@pytest.mark.parametrize("platform_reused", [False, True])
def test_parallel_failure_drains_late_platform_and_only_stops_new_services(parallel_menu, monkeypatch, platform_reused):
    controller, active, started, stopped, urls = parallel_menu
    if platform_reused:
        active["platform"] = controller.platform
    platform_starting, admin_failed, finish_platform = Event(), Event(), Event()
    original = launcher.start

    def fail_then_finish(config, **kwargs):
        if config.key == "admin-workbench":
            assert platform_starting.wait(4)
            admin_failed.set()
            raise RuntimeError("Échec Admin témoin")
        assert config.key == "platform"
        platform_starting.set()
        assert finish_platform.wait(4)
        return original(config, **kwargs)

    monkeypatch.setattr(launcher, "start", fail_then_finish)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(controller.launch, "admin")
        try:
            assert admin_failed.wait(4)
            assert not future.done()
        finally:
            finish_platform.set()
        with pytest.raises(RuntimeError, match="Échec Admin témoin"):
            future.result(timeout=4)
    assert not urls and not controller.opened
    assert (set(active), stopped, started) == (
        ({"platform"}, [], []) if platform_reused else (set(), ["platform"], ["platform"])
    )


def test_parallel_option_keeps_organization_launch_sequential(parallel_menu, monkeypatch):
    controller, active, started, _, _ = parallel_menu
    original = launcher.start
    calling_thread = get_ident()

    def start_in_caller(config, **kwargs):
        assert get_ident() == calling_thread
        return original(config, **kwargs)

    monkeypatch.setattr(launcher, "start", start_in_caller)
    result = controller.launch("organization", "leonteq", open_browser=False)
    assert started == [row["key"] for row in result["services"]] == ["platform", "leonteq"]
    assert set(active) == {"platform", "leonteq"}


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


@pytest.fixture
def start_service(tmp_path, monkeypatch):
    (tmp_path / "logs").mkdir()
    config = SimpleNamespace(key="admin-workbench", name="Admin", data_dir=tmp_path,
                             port=19508, installation_id="installation-temoin")
    bind = Mock()
    socket = Mock()
    socket.return_value.__enter__ = Mock(return_value=SimpleNamespace(bind=bind))
    socket.return_value.__exit__ = Mock(return_value=False)
    monkeypatch.setattr(deployment, "socket", SimpleNamespace(socket=socket))
    monkeypatch.setattr(deployment, "environment", lambda _config: {})
    return config, bind


def test_cold_start_skips_http_on_closed_port_and_waits_for_its_own_health(start_service, monkeypatch):
    config, bind = start_service
    accepts = Mock(side_effect=[False, False, True, True])
    launch_environment = {}
    answers = []

    def probe(_config):
        assert _config is config and launch_environment
        launch_id = "ancienne-session" if not answers else launch_environment["STRUCTURA_LAUNCH_ID"]
        answers.append(launch_id)
        return {"launch_id": launch_id, "process_id": 42}

    def popen(_command, *, env, **_kwargs):
        assert not answers
        launch_environment.update(env)
        return SimpleNamespace(pid=41, poll=lambda: None)

    monkeypatch.setattr(deployment, "_accepts_local_connections", accepts)
    monkeypatch.setattr(deployment, "probe", probe)
    monkeypatch.setattr(deployment.subprocess, "Popen", popen)

    result = deployment.start(config, developer_access=True, launcher_id="lanceur-temoin")

    assert result["started"] and result["pid"] == 42 and result["launcher_pid"] == 41
    assert accepts.call_count == 4
    assert answers == ["ancienne-session", launch_environment["STRUCTURA_LAUNCH_ID"]]
    bind.assert_called_once_with(("127.0.0.1", config.port))
    record = json.loads((config.data_dir / ".process.json").read_text(encoding="utf-8"))
    assert record["server_pid"] == result["pid"]
    assert record["launch_id"] == answers[-1]
    assert record["launcher_id"] == "lanceur-temoin"


def test_live_service_is_reused_after_http_identity_check(start_service, monkeypatch):
    config, bind = start_service
    record_path = config.data_dir / ".process.json"
    record = {"installation_id": config.installation_id, "pid": 41, "launch_id": "session-temoin",
              "launcher_id": "ancien-lanceur"}
    record_path.write_text(json.dumps(record), encoding="utf-8")
    accepts = Mock(return_value=True)
    probe = Mock(return_value={"process_id": 42, "launch_id": record["launch_id"], "developer_access": True})
    no_process = Mock(side_effect=AssertionError("Ne pas lancer un deuxième service"))
    monkeypatch.setattr(deployment, "_accepts_local_connections", accepts)
    monkeypatch.setattr(deployment, "probe", probe)
    monkeypatch.setattr(deployment.subprocess, "Popen", no_process)

    result = deployment.start(config, developer_access=True, launcher_id="lanceur-temoin")

    assert result == {"key": config.key, "started": False, "reused": True, "pid": 42}
    accepts.assert_called_once_with(config.port)
    probe.assert_called_once_with(config)
    bind.assert_not_called()
    no_process.assert_not_called()
    assert json.loads(record_path.read_text(encoding="utf-8")) == {**record, "launcher_id": "lanceur-temoin"}


@pytest.mark.parametrize("accepts", [False, True])
def test_occupied_port_is_preserved_even_when_its_listener_is_not_ready(start_service, monkeypatch, accepts):
    config, bind = start_service
    bind.side_effect = OSError("Port déjà réservé")
    probe = Mock(return_value=None)
    no_process = Mock(side_effect=AssertionError("Ne pas lancer sur un port occupé"))
    monkeypatch.setattr(deployment, "_accepts_local_connections", Mock(return_value=accepts))
    monkeypatch.setattr(deployment, "probe", probe)
    monkeypatch.setattr(deployment.subprocess, "Popen", no_process)
    monkeypatch.setattr(deployment, "stop", no_process)

    with pytest.raises(RuntimeError, match="Port 19508 occupé"):
        deployment.start(config, launcher_id="lanceur-temoin")

    assert probe.call_count == int(accepts)
    bind.assert_called_once_with(("127.0.0.1", config.port))
    no_process.assert_not_called()
    assert not (config.data_dir / ".process.json").exists()


def _load_script(path, name):
    import importlib.util
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_backend_without_explicit_environment_hands_over_to_launcher_script(monkeypatch):
    # run.py must not depend on the checkout's .venv being present (CI has
    # none): only the hand-over to scripts/launch_structura.py is its job.
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    run_module = _load_script(root / "backend" / "run.py", "structura_run_under_test")
    handed = []
    monkeypatch.delenv("STRUCTURA_INSTALLATION_CONFIG",raising=False)
    monkeypatch.delenv("STRUCTURA_DATA_DIR",raising=False)
    monkeypatch.setattr(runpy,"run_path",lambda path,run_name=None:handed.append((Path(path),run_name)))
    run_module.main()
    assert handed == [((root / "scripts" / "launch_structura.py").resolve(),"__main__")]


@pytest.fixture
def launch_script(tmp_path, monkeypatch):
    # A throwaway checkout root with its own .venv, so neither the real one nor
    # its absence matters, and no real menu or interpreter is ever started.
    # The checkout sits one level down, so its structura-react sibling belongs
    # to this test alone and never to the real clone next to the repository.
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    sys.path.insert(0,str(root / "backend"))
    from app.hybrid import launcher as entry_launcher
    script = _load_script(root / "scripts" / "launch_structura.py", "structura_launch_under_test")
    venv = tmp_path / "structura" / ".venv"
    (venv / "Scripts").mkdir(parents=True)
    (venv / "Scripts" / "python.exe").write_bytes(b"")
    monkeypatch.setattr(script,"ROOT",tmp_path / "structura")
    monkeypatch.setattr(sys,"argv",[str(root / "scripts" / "launch_structura.py")])
    opened, spawned, directories = [], [], []
    monkeypatch.setattr(entry_launcher,"main",lambda:opened.append(True))
    def popen(args, **kw):
        spawned.append(args)
        directories.append(kw.get("cwd"))
    monkeypatch.setattr(script.subprocess,"Popen",popen)
    return script, venv, opened, spawned, directories


@pytest.fixture
def react_chooser(tmp_path):
    chooser = tmp_path / "structura-react" / "scripts" / "launch_versions.py"
    chooser.parent.mkdir(parents=True)
    chooser.write_text("", encoding="utf-8")
    return chooser


def test_launcher_script_opens_menu_inside_project_python(launch_script, monkeypatch):
    script, venv, opened, spawned, _ = launch_script
    monkeypatch.setattr(sys,"prefix",str(venv))
    script.main()
    assert opened == [True] and spawned == []


def test_launcher_script_relaunches_itself_with_project_python(launch_script, tmp_path, monkeypatch):
    script, venv, opened, spawned, _ = launch_script
    monkeypatch.setattr(sys,"prefix",str(tmp_path / "another-python"))
    script.main()
    assert opened == []
    assert spawned == [[str(venv / "Scripts" / "python.exe"), str(Path(script.__file__).resolve())]]


def test_launcher_script_refuses_without_project_python(launch_script):
    script, venv, opened, spawned, _ = launch_script
    (venv / "Scripts" / "python.exe").unlink()
    with pytest.raises(RuntimeError, match="Python du projet introuvable"):
        script.main()
    assert opened == [] and spawned == []


@pytest.mark.parametrize("inside_project_python", [True, False])
def test_shortcut_offers_the_version_chooser_when_react_sits_next_to_the_checkout(
        launch_script, react_chooser, tmp_path, monkeypatch, inside_project_python):
    script, venv, opened, spawned, directories = launch_script
    monkeypatch.setattr(sys,"prefix",str(venv if inside_project_python else tmp_path / "another-python"))
    script.main()
    # The React checkout has no interpreter: the chooser runs on this one,
    # from its own directory, exactly as its lancer_structura.vbs does.
    assert opened == []
    assert spawned == [[str(venv / "Scripts" / "python.exe"), "-B", str(react_chooser)]]
    assert directories == [tmp_path / "structura-react"]


def test_vue_flag_opens_the_vue_menu_even_beside_the_chooser(launch_script, react_chooser, monkeypatch):
    script, venv, opened, spawned, _ = launch_script
    monkeypatch.setattr(sys,"prefix",str(venv))
    script.main(["--vue"])
    assert opened == [True] and spawned == []


def test_vue_flag_survives_the_relaunch_with_project_python(launch_script, react_chooser, tmp_path, monkeypatch):
    script, venv, opened, spawned, _ = launch_script
    monkeypatch.setattr(sys,"prefix",str(tmp_path / "another-python"))
    script.main(["--vue"])
    # Without the flag the relaunched script would offer the chooser again.
    assert opened == []
    assert spawned == [[str(venv / "Scripts" / "python.exe"), str(Path(script.__file__).resolve()), "--vue"]]


def test_menu_that_cannot_import_says_so_instead_of_vanishing(launch_script, monkeypatch):
    # A .venv left behind by a pull (PyJWT missing on 25/11) killed the menu
    # before any window: pythonw showed nothing at all.
    script, venv, opened, spawned, _ = launch_script
    monkeypatch.setattr(sys,"prefix",str(venv))
    monkeypatch.setitem(sys.modules,"app.hybrid.launcher",None)
    shown = []
    monkeypatch.setattr(script,"show_error",shown.append)
    with pytest.raises(ImportError):
        script.main()
    assert opened == [] and len(shown) == 1
    assert "pip install --require-hashes -r requirements.lock.txt" in shown[0]


def test_vue_shortcut_called_by_the_react_chooser_cannot_loop_back_to_it():
    # structura-react's "Ouvrir Vue" runs lancer_structura.vbs: it must open the
    # Vue menu itself, from its own folder, while the .bat stays the entry point.
    root = Path(__file__).resolve().parents[2]
    shortcut = (root / "lancer_structura.vbs").read_text(encoding="ascii")
    code = "\n".join(line for line in shortcut.splitlines() if not line.lstrip().startswith("'"))
    assert r'".venv\Scripts\pythonw.exe"' in code and r'"scripts\launch_structura.py"' in code
    assert '" --vue"' in code and ".bat" not in code
    assert "C:\\Users" not in code
    assert "--vue" not in (root / "lancer_structura.bat").read_text(encoding="ascii")


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
