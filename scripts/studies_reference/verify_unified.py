"""Exercise the ordinary scanner and engine, without replacing market loaders."""
import json
from pathlib import Path
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path.cwd() / "backend"))
from app.core.amc_manifest import detect_study_folder
from app.core.amc_study import run_study
from report_comparison import report


def main():
    folder = Path("artifacts/studies/LO_ALL_BLOCKS_2020_2025").resolve()
    source = Path("artifacts/studies/LO_EXTENDED_BLOCKS_2020_2025_V1")
    manifest = detect_study_folder(str(folder))["manifest"]
    attempts = []
    def blocked(*args, **kwargs):
        attempts.append(str(args[:1]))
        raise AssertionError("Accès réseau interdit")
    with patch("socket.socket.connect", blocked), patch("socket.create_connection", blocked), \
            patch("yfinance.download", blocked), patch("yfinance.Ticker", blocked):
        result = run_study(manifest, str(folder))
    assert not attempts, attempts
    assert all(v == "completed" for v in result["block_status"].values()), result["block_status"]
    assert result["meta"]["n_orders"] == 1540
    assert result["termsheet_basket"] == []  # No invented starting lots.
    vag = next(d for d in result["manager_skill_score"]["dimensions"] if d["key"] == "vag")
    assert vag["available"] and vag["weight_effective_pct"] == 20
    assert result["block_b"]["totals"]["fx_share_of_realized_pct"] == -7.84
    g_rows = [r for r in result["confidence"]["rows"] if r["dimension"].endswith("(Bloc G)")]
    assert len(g_rows) == 1 and g_rows[0]["feasible"] and not g_rows[0]["scoring_eligible"]
    out = folder / "RESULTATS_ATTENDUS/CONTROLE_OUTIL"
    out.mkdir(parents=True, exist_ok=True)
    (out / "resultat.json").write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    comparison = report(source, unified_result=result, output=out)
    assert comparison["comparisons"] == 85
    assert comparison["to_examine"] == [], comparison["to_examine"]
    print("Tous les blocs calculés, 85 comparaisons conformes ; aucun accès réseau.")



if __name__ == "__main__":
    main()
