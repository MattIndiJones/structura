"""Prepare/init/start/status/stop an owned seven-service development environment."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.hybrid.deployment import initialize, load_layout, prepare, probe, start, stop


def main():
    parser = argparse.ArgumentParser(description="Installations Structura hybrides fictives")
    parser.add_argument("command", choices=["prepare", "init", "start", "status", "stop"])
    parser.add_argument("--runtime-root", type=Path, default=ROOT / ".runtime" / "hybrid-saas")
    parser.add_argument("--installation", help="Clé d'installation ; toutes par défaut")
    parser.add_argument("--base-port", type=int, default=8100)
    parser.add_argument("--developer-access", action="store_true", help="Active explicitement les raccourcis locaux de développement")
    arguments = parser.parse_args()
    configs = prepare(arguments.runtime_root, arguments.base_port) if arguments.command in {"prepare", "init"} else load_layout(arguments.runtime_root)
    if arguments.installation:
        configs = [c for c in configs if c.key == arguments.installation]
        if not configs:
            parser.error("Installation inconnue")
    results, started = [], []
    try:
        for config in configs:
            if arguments.command == "init":
                result = initialize(config)
            elif arguments.command == "start":
                result = start(config, developer_access=arguments.developer_access)
                if result["started"]:
                    started.append(config)
            elif arguments.command == "stop":
                result = stop(config)
            elif arguments.command == "status":
                result = {"key": config.key, "health": probe(config)}
            else:
                result = config.public_descriptor()
            results.append(result)
    except BaseException:
        for config in reversed(started):
            stop(config)
        raise
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
