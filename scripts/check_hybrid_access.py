"""Check the common development portal on already running manual installations."""
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from contextlib import closing
import sys

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.hybrid.deployment import load_layout, atomic_json


def main():
    configs = load_layout(ROOT / ".runtime" / "hybrid-saas")
    platform = next(config for config in configs if config.kind == "platform")
    base = platform.public_descriptor()["url"]
    evidence = {"checked_at":datetime.now(timezone.utc).isoformat(),"accounts":[],"checks":[]}
    with httpx.Client(timeout=15,trust_env=False) as client:
        catalog = client.get(base + "/api/platform/development/access").json()
        assert catalog["enabled"] and len(catalog["installations"]) == 7
        headers = {"X-Structura-Development":"1", "Origin":base}
        central = client.post(base + "/api/platform/development/session",json={"installation_id":str(platform.installation_id),"username":"admin"},headers=headers)
        assert central.status_code == 200, central.text
        central_headers = {**headers,"Authorization":"Bearer " + central.json()["access_token"]}
        for config in configs[1:]:
            url = config.public_descriptor()["url"]
            for username in ("superuser","front","operations","controller"):
                granted = client.post(base + "/api/platform/development/session",json={"installation_id":str(config.installation_id),"username":username},headers=central_headers)
                assert granted.status_code == 200, granted.text
                ticket = granted.json()["ticket"]
                session = client.post(url + "/api/auth/development-session",json={"ticket":ticket},headers=headers)
                assert session.status_code == 200, session.text
                token = session.json()["access_token"]
                me = client.get(url + "/api/auth/me",headers={"Authorization":"Bearer " + token}).json()
                assert me["username"] == username and me["installation"]["installation_id"] == str(config.installation_id)
                assert me["developer_origin"]["kind"] == "CENTRAL_ADMIN"
                assert client.post(url + "/api/auth/development-session",json={"ticket":ticket},headers=headers).status_code == 409
                if username == "superuser":
                    other = configs[2] if config == configs[1] else configs[1]
                    assert client.get(other.public_descriptor()["url"] + "/api/auth/me",headers={"Authorization":"Bearer " + token}).status_code == 401
                cors = client.options(url + "/api/auth/development-session",headers={"Origin":base,"Access-Control-Request-Method":"POST","Access-Control-Request-Headers":"content-type,x-structura-development"})
                assert cors.status_code == 200 and cors.headers["access-control-allow-origin"] == base
                evidence["accounts"].append({"installation":config.key,"username":username,"origin":"CENTRAL_ADMIN"})
            with closing(sqlite3.connect((config.data_dir / "structura.db").as_uri() + "?mode=ro",uri=True)) as connection:
                for table in ("products","product_calculation_runs","deals","rfq_requests","amc_studies","portfolios",
                              "indicatives","valuation_runs","valuation_notes","compute_batches","compute_jobs","shock_runs"):
                    assert connection.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0] == 0
        evidence["checks"] = ["seven_cards","25_development_accounts","central_origin_audited","single_use_tickets","cross_installation_tokens_rejected","portal_cors","empty_manual_books"]
        assert client.get(base + "/").status_code == 200
        assert client.get(base + "/api/deals",headers=central_headers).status_code == 404
    atomic_json(platform.data_dir.parent / "access-acceptance.json",evidence)
    print(json.dumps({"passed":True,"accounts":len(evidence["accounts"])+1,"checks":evidence["checks"]},ensure_ascii=False,indent=2))


if __name__ == "__main__":
    main()
