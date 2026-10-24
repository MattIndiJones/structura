"""Native seven-service acceptance on temporary databases with guaranteed teardown."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
from uuid import uuid4

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.hybrid.config import credentials
from app.hybrid.deployment import atomic_json, initialize, prepare, probe, start, stop


def check(root, base_port):
    configs = prepare(root, base_port)
    evidence = {"started_at": datetime.now(timezone.utc).isoformat(), "initialization": [],
                "processes": [], "checks": [], "cleanup": []}
    started = []
    try:
        for config in configs:
            evidence["initialization"].append(initialize(config))
        before = [(str(c.installation_id), hashlib.sha256((c.data_dir / ".jwt_secret").read_bytes()).hexdigest()) for c in configs]
        for config in configs:
            evidence["initialization"].append(initialize(config))
        assert before == [(str(c.installation_id), hashlib.sha256((c.data_dir / ".jwt_secret").read_bytes()).hexdigest()) for c in configs]
        for config in configs:
            process = start(config)
            evidence["processes"].append(process)
            if process["started"]:
                started.append(config)
        with httpx.Client(timeout=10, trust_env=False) as client:
            tokens = {}
            for config in configs:
                url = config.public_descriptor()["url"]
                usernames = ["admin"] if config.kind == "platform" else ["superuser", "front", "operations", "controller"]
                for username in usernames:
                    response = client.post(url + "/api/auth/login", data={"username": username, "password": credentials(config)[username]})
                    assert response.status_code == 200, (config.key, username, response.status_code)
                    headers = {"Authorization": "Bearer " + response.json()["access_token"]}
                    assert client.get(url + "/api/auth/me", headers=headers).status_code == 200
                    tokens[(config.key, username)] = headers
                    if config.kind == "organization":
                        status = 200 if username == "superuser" else 403
                        assert client.get(url + "/api/admin/users", headers=headers).status_code == status
                        assert client.get(url + "/api/agent-workshop", headers=headers).status_code == 403
                        assert client.get(url + "/api/admin/agent-workshop", headers=headers).status_code == 403
                        if username in {"front", "controller"}:
                            payload = {"contrepartie": "Test", "nominal": 1000000,
                                "fair_value": 100, "price_traded": 100, "trade_date": "2026-10-13",
                                "strike_date": "2026-10-13", "value_date": "2026-10-15",
                                "maturity_date": "2027-10-13", "T": 1, "underlyings": [],
                                "observation_times": [1], "script_snapshot": "AT 1:\n  PAY 1"}
                            assert client.post(url + "/api/deals", headers=headers, json=payload).status_code == 403
                evidence["checks"].append({"installation": config.key, "accounts_authenticated": len(usernames)})
            platform = configs[0]
            directory = client.get(platform.public_descriptor()["url"] + "/api/platform/installations", headers=tokens[("platform", "admin")])
            assert directory.status_code == 200 and len(directory.json()["installations"]) == 6
            for config in configs[1:]:
                url = config.public_descriptor()["url"]
                assert client.get(url + "/api/auth/me", headers=tokens[("platform", "admin")]).status_code == 401
                other = configs[2] if config == configs[1] else configs[1]
                assert client.get(url + "/api/auth/me", headers=tokens[(other.key, "superuser")]).status_code == 401
                assert client.get(platform.public_descriptor()["url"] + "/api/auth/me", headers=tokens[(config.key, "superuser")]).status_code == 401
                for username in ("operations", "controller"):
                    response = client.post(url + "/api/parse", headers=tokens[(config.key, username)], json={"script": "AT 1:\n  PAY 1"})
                    assert response.status_code == 403
            # An installation outage leaves the others available and preserves identity on restart.
            stopped = stop(configs[1])
            evidence["cleanup"].append({**stopped, "phase": "restart"})
            assert probe(configs[2]) is not None
            restarted = start(configs[1])
            evidence["processes"].append(restarted)
            assert client.get(configs[1].public_descriptor()["url"] + "/api/auth/me",
                              headers=tokens[(configs[1].key, "superuser")]).status_code == 200
        for config in configs[1:]:
            with sqlite3.connect(f"{(config.data_dir / 'structura.db').as_uri()}?mode=ro", uri=True) as connection:
                assert connection.execute("SELECT count(*) FROM users").fetchone()[0] == 4
                assert connection.execute("SELECT count(*) FROM rfq_desks").fetchone()[0] == 2
                for table in ("products", "deals", "rfq_requests", "compute_jobs", "amc_studies"):
                    count = connection.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0]
                    assert count == 0, (config.key, table, count)
        evidence["checks"].extend([{"cross_installation_tokens": "REJECTED"},
                                  {"restart_preserves_sessions": True}, {"business_dossiers": 0}])
        evidence["success"] = True
    except BaseException as error:
        evidence["success"] = False
        evidence["error"] = str(error)
        raise
    finally:
        for config in reversed(started):
            try:
                evidence["cleanup"].append(stop(config))
            except Exception as error:
                evidence["cleanup"].append({"key": config.key, "error": str(error)})
                evidence["success"] = False
        atomic_json(root / "acceptance.json", evidence)
    assert evidence["success"], "Arrêt de toutes les instances non confirmé"
    return {"success": True, "installations": 7, "accounts_authenticated": 25,
            "evidence": str(root / "acceptance.json"), "processes_cleaned": True}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-port", type=int, default=8120)
    arguments = parser.parse_args()
    root = ROOT / "tmp" / "hybrid-foundation" / (datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid4().hex[:6])
    print(json.dumps(check(root, arguments.base_port), ensure_ascii=False, indent=2))
