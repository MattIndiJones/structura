"""Inspect, then explicitly attest an offline legacy Admin workspace."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.hybrid.admin_adoption import adopt, inspect_adoption


def main():
    parser = argparse.ArgumentParser(description="Reprise explicite du workspace Admin historique, sans réinitialisation")
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--installation-id")
    parser.add_argument("--expected-sha256")
    parser.add_argument("--reason")
    args = parser.parse_args()
    if args.apply and not all((args.installation_id, args.expected_sha256, args.reason)):
        parser.error("--apply exige --installation-id, --expected-sha256 et --reason")
    try:
        result = adopt(args.manifest, expected_installation_id=args.installation_id,
                       expected_sha256=args.expected_sha256, reason=args.reason) if args.apply \
            else inspect_adoption(args.manifest)
    except (RuntimeError, ValueError) as exc:
        parser.exit(1, str(exc) + "\n")
    print(json.dumps(result, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
