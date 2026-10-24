"""Native launcher access acceptance, without creating or starting AI campaigns."""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import sys
from uuid import uuid4

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.hybrid.launcher import Launcher
from app.hybrid.deployment import atomic_json, probe


def owned_services(controller, existing):
    """Include the full Admin and controller, excluding preexisting services."""
    return [c for c in [*controller.controls.values(), *controller.configs]
            if c.key not in existing and (c.data_dir / ".process.json").exists()]


def check(root, port, keep_running=False, evidence_path=None):
    controller = Launcher(root, port)
    evidence = {"started_at": datetime.now(timezone.utc).isoformat(), "checks": [],
                "processes": [], "organizations": [], "cleanup": []}
    existing = {c.key for c in [*controller.configs, *controller.controls.values()] if probe(c)}
    try:
        first = controller.launch("all", open_browser=False)
        evidence["processes"] += first["services"]
        console = controller.launch("platform", open_browser=False)
        assert console["url"].endswith("/#/login?console=1&next=/platform")
        assert not any(row["started"] for row in console["services"])
        simulation = controller.launch("simulation", open_browser=False)
        evidence["processes"] += [row for row in simulation["services"] if row["started"]]
        admin_config = controller.controls["admin-workbench"]
        assert simulation["url"] == admin_config.public_descriptor()["url"] + "/#/login?development_admin=1&next=/agent-workshop"
        platform = controller.platform
        base = platform.public_descriptor()["url"]
        workbench = admin_config.public_descriptor()["url"]
        with httpx.Client(timeout=120, trust_env=False) as client:
            headers = {"X-Structura-Development": "1", "Origin": base}
            session = client.post(base + "/api/platform/development/session",
                                  json={"installation_id": str(platform.installation_id), "username": "admin"}, headers=headers)
            assert session.status_code == 200, session.text
            central = {"Authorization": "Bearer " + session.json()["access_token"]}
            assert client.get(base + "/").status_code == 200
            assert "simulation.manage" in client.get(base + "/api/auth/me", headers=central).json()["capabilities"]
            assert len(client.get(base + "/api/platform/installations", headers=central).json()["installations"]) == 6
            directory = client.get(base + "/api/platform/development/access", headers=headers).json()
            assert directory["enabled"] and len(directory["installations"]) == 7
            business_tokens = []
            for config in (c for c in controller.configs if c.kind == "organization"):
                direct = controller.launch("organization", config.key, open_browser=False)
                assert direct["url"] == base + "/#/login?organization=" + config.key
                assert not any(row["started"] for row in direct["services"])
                url = config.public_descriptor()["url"]
                assert client.get(url + "/").status_code == 200
                identities = []
                for username, role in (("superuser", "organization_admin"), ("front", "user"),
                                       ("operations", "ops_maker"), ("controller", "checker")):
                    grant = client.post(base + "/api/platform/development/session", headers={**headers, **central},
                                        json={"installation_id": str(config.installation_id), "username": username})
                    assert grant.status_code == 200, grant.text
                    redeemed = client.post(url + "/api/auth/development-session", headers=headers,
                                           json={"ticket": grant.json()["ticket"]})
                    assert redeemed.status_code == 200, redeemed.text
                    business = {"Authorization": "Bearer " + redeemed.json()["access_token"]}
                    me = client.get(url + "/api/auth/me", headers=business)
                    assert me.status_code == 200 and me.json()["role"] == role
                    assert me.json()["installation"]["installation_id"] == str(config.installation_id)
                    assert client.get(url + "/api/agent-workshop", headers=business).status_code == 403
                    assert client.get(base + "/api/platform/installations", headers=business).status_code == 401
                    identities.append({"username": username, "role": role})
                    if username == "superuser":
                        assert client.get(url + "/api/products", headers=business).status_code == 200
                        business_tokens.append((url, business))
                evidence["organizations"].append({"key": config.key, "identities": identities})
            assert client.get(business_tokens[1][0] + "/api/products", headers=business_tokens[0][1]).status_code == 401
            local_session = client.post(workbench + "/api/auth/development-admin-session",
                                        headers={"Origin": workbench, "X-Structura-Development": "1"})
            assert local_session.status_code == 200, local_session.text
            admin = {"Authorization": "Bearer " + local_session.json()["access_token"]}
            for suffix in ("", "/models", "/defaults"):
                response = client.get(workbench + "/api/agent-workshop" + suffix, headers=admin)
                assert response.status_code == 200, response.text
            # Starts only the signed HTTP gateway's controller, never a campaign.
            assert client.post(base + "/api/platform/simulation/start", headers=central).status_code == 200
            for suffix in ("", "/models", "/defaults"):
                response = client.get(base + "/api/agent-workshop" + suffix, headers=central)
                assert response.status_code == 200, response.text
            assert client.get(controller.controls["simulation"].public_descriptor()["url"] + "/api/agent-workshop",
                              headers=central).status_code == 401
            assert client.get(base + "/api/deals", headers=central).status_code == 404
            status = client.get(base + "/api/platform/status", headers=central)
            assert status.status_code == 200
            assert {r["key"] for r in status.json()["services"] if r["state"] == "RUNNING"} >= {
                "platform", "simulation", *(c.key for c in controller.configs if c.kind == "organization")}
            with closing(sqlite3.connect((platform.data_dir / "platform.db").as_uri() + "?mode=ro", uri=True)) as db:
                assert {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")} == {
                    "platform_identity", "platform_users", "platform_installations", "platform_audit", "platform_revoked_sessions"}
            assert not (controller.controls["simulation"].data_dir / "structura.db").exists()
        evidence["checks"] = ["all_six_organizations", "individual_organization_shortcuts_reuse_services",
            "24_development_identities", "business_products", "cross_installation_tokens_denied",
            "central_console", "launcher_simulation_opens_full_admin", "admin_campaign_screen_read_apis",
            "signed_central_simulation_read_apis", "business_simulation_denied", "no_business_schema_central",
            "no_campaign_created_or_started"]
        evidence["passed"] = True
    finally:
        owned = owned_services(controller, existing)
        evidence["owned_keys"] = [c.key for c in owned]
        if not keep_running or not evidence.get("passed"):
            evidence["cleanup"] = controller.stop(only=owned)
        evidence["finished_at"] = datetime.now(timezone.utc).isoformat()
        atomic_json(evidence_path or root / "launcher-acceptance.json", evidence)
    return {"passed": evidence.get("passed", False), "runtime_root": str(root), "url": base,
            "checks": evidence["checks"], "cleanup": evidence["cleanup"], "kept_for_ui": keep_running}


def main():
    parser = argparse.ArgumentParser(description="Recette native des accès du lanceur, sans campagne IA")
    parser.add_argument("--keep-for-ui", action="store_true")
    parser.add_argument("--port", type=int, default=8370)
    parser.add_argument("--evidence-file", type=Path, help="Preuve distincte des anciens rapports du runtime")
    parser.add_argument("--runtime-root", type=Path, default=ROOT / "tmp" / "launcher-native" /
                        (datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid4().hex[:6]))
    args = parser.parse_args()
    print(json.dumps(check(args.runtime_root.resolve(), args.port, args.keep_for_ui,
                           args.evidence_file.resolve() if args.evidence_file else None), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
