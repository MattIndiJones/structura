"""Assemble an ordinary Studies folder from frozen independent inputs.

This is packaging only: no Studies calculation and no reference results are
used to produce market inputs. Run from the repository root.
"""
import json
from pathlib import Path
import shutil
import pandas as pd


def assemble(source, output):
    source, output = Path(source), Path(output)
    output.mkdir(parents=True, exist_ok=True)
    original = source / "sources/validated_import"
    manifest = json.loads((original / "manifest.json").read_text(encoding="utf-8-sig"))
    for value in manifest["files"].values():
        for name in (value if isinstance(value, list) else [value]):
            if name:
                shutil.copy2(original / name, output / name)
    assets = pd.read_csv(source / "inputs/asset_classification.csv").set_index("asset_id")
    market = pd.read_csv(source / "inputs/market_daily.csv")
    bundle = {"schema_version": "1.0", "assets": {}, "fx_usd_per_local": {}}
    for key, group in market.groupby("asset_id", sort=True):
        rows = group[["date", "total_return_index_local", "price_split_adjusted"]].rename(
            columns={"total_return_index_local": "close", "price_split_adjusted": "price_close"})
        splits = group[group.split_ratio != 1].set_index("date").split_ratio.to_dict()
        bundle["assets"][key] = {"name": assets.loc[key, "name"], "currency": assets.loc[key, "currency"],
            "sector": assets.loc[key, "sector"], "adjustment_date": "2025-12-31", "splits": splits,
            "rows": rows.to_dict("records")}
    for currency, group in market.groupby("currency", sort=True):
        rows = group.drop_duplicates("date")[["date", "usd_per_local"]].rename(columns={"usd_per_local": "rate"})
        bundle["fx_usd_per_local"][currency] = rows.to_dict("records")
    factors = pd.read_csv(source / "sources/factors.csv")
    bundle["factors"] = {"series": "Developed_5F_MOM", "columns": [c for c in factors if c != "date"],
                         "rows": factors.to_dict("records")}
    bundle["benchmark"] = {"ticker": "SYNTH_BENCH20_USD",
        "rows": pd.read_csv(source / "inputs/benchmark_daily.csv").to_dict("records")}
    economic = json.loads((source / "inputs/termsheet_economic.json").read_text(encoding="utf-8"))
    brinson = pd.read_csv(source / "inputs/brinson_benchmark.csv").set_index("sector")
    bundle["brinson"] = {"start": economic["date"], "end": "2025-12-31",
        "weights": brinson.benchmark_weight.to_dict(), "returns": brinson.benchmark_return.to_dict()}
    (output / "market_data.json").write_text(json.dumps(bundle, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    manifest["files"]["market_data"] = "market_data.json"
    manifest["product"]["name"] = "Fonds fictif long only — recette complète A à K"
    manifest["params"].update(ff_series="Developed_5F_MOM", factor_model="FF5+MOM",
        selected_factors=["Mkt-RF", "SMB", "HML", "RMW", "CMA", "MOM"],
        benchmark_ticker="SYNTH_BENCH20_USD", rolling_window=60,
        reference_portfolio={"start_date": economic["date"], "positions": economic["positions"]})
    manifest["blocks"] = {k: True for k in [*manifest["blocks"], "G_brinson"]}
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    expected = output / "RESULTATS_ATTENDUS"
    expected.mkdir(exist_ok=True)
    for name in ["expected_by_screen.csv", "summary.json"]:
        shutil.copy2(source / "reference" / name, expected / name)
    from methodology_reference import revised_reference
    reference = revised_reference(source, json.loads((expected / "summary.json").read_text(encoding="utf-8")))
    (expected / "summary.json").write_text(json.dumps(reference, ensure_ascii=False, indent=2), encoding="utf-8")
    rows = [{"block": block, "metric": key, "value": value} for block, values in reference.items()
            if isinstance(values, dict) for key, value in values.items() if not isinstance(value, (dict, list))]
    pd.DataFrame(rows).to_csv(expected / "expected_by_screen.csv", index=False)
    guide = Path("docs/projects/studies/STUDIES_SETUP_COMPLET_2026-09-21.md")
    if guide.exists():
        shutil.copy2(guide, output / "LIRE_MOI.md")
        for name in ["STUDIES_METHODOLOGY_2026-09-21.md", "STUDIES_EXISTING_FIXES_2026-09-21.md"]:
            methodology = guide.parent / name
            if methodology.exists():
                shutil.copy2(methodology, output / methodology.name)
    print(output.resolve())


if __name__ == "__main__":
    assemble("artifacts/studies/LO_EXTENDED_BLOCKS_2020_2025_V1", "artifacts/studies/LO_ALL_BLOCKS_2020_2025")
