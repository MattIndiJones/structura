"""Prepare an exact inventory, then apply it to authorized fictitious Structura data."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.hybrid.deployment import atomic_json
from app.hybrid.reset import apply_inventory, inventory


def main():
    parser = argparse.ArgumentParser(description="Retrait ciblé des anciens jeux Structura fictifs")
    parser.add_argument("command", choices=["inventory", "apply"])
    args = parser.parse_args()
    runtime = ROOT / ".runtime" / "hybrid-saas"
    path = runtime / "cleanup-inventory.json"
    if args.command == "inventory":
        plan = inventory(ROOT, runtime)
        atomic_json(path, plan)
        print(json.dumps({"inventory": str(path), "databases": len(plan["databases"]), "files": len(plan["files"]),
                          "preserved_database_count": len(plan["unidentified_databases_preserved"])}, ensure_ascii=False, indent=2))
    else:
        result = apply_inventory(json.loads(path.read_text(encoding="utf-8")), ROOT, runtime)
        result["preserved_database_count"] = len(result.pop("unidentified_databases_preserved"))
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
