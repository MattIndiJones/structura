"""Observable data coverage, never a probability of manager skill."""
from __future__ import annotations


def attach_brinson(study: dict, result: dict) -> dict:
    """Synchronize a supplementary calculation and its saved documentary coverage."""
    from copy import deepcopy
    from .amc_controls import fingerprint
    updated = deepcopy(study)
    updated["block_g"] = result
    coverage = updated.setdefault("confidence", {})
    rows = [r for r in coverage.get("rows", []) if not r["dimension"].endswith("(Bloc G)")]
    rows.extend(build_confidence({"G"}, None, 0, brinson_result=result)["rows"])
    coverage.update(rows=rows, overall_pct=round(sum(r["confidence_pct"] for r in rows) / len(rows), 1))
    updated.setdefault("block_status", {})["G_brinson"] = "completed" if result.get("available") else "error"
    updated.setdefault("provenance", {})["result_hash"] = fingerprint({k: v for k, v in updated.items() if k != "provenance"})
    return updated


def build_confidence(blocks, block_a, n_orders, block_e_result=None, vag_result=None,
                     attribution_result=None, block_f_result=None, brinson_result=None,
                     block_h_result=None, block_i_result=None, block_j_result=None,
                     block_b_result=None, data_quality=None):
    results = {"A": block_a, "B": block_b_result, "E": block_e_result,
               "F": block_f_result, "G": brinson_result, "H": block_h_result,
               "I": block_i_result, "J": block_j_result}
    labels = {"A": "Analyse factorielle", "B": "Attribution FIFO", "C": "Activité de trading",
              "D": "Comportement observé", "E": "Référentiel passif brut", "F": "Explication factorielle",
              "G": "Brinson sur proxies", "H": "Timing descriptif", "I": "Sélection descriptive",
              "J": "Gestion du risque", "K": "Chocs de marché"}
    requested = {str(k)[0] for k in blocks}
    if brinson_result is not None:
        requested.add("G")
    rows = []
    for key in sorted(requested):
        result = results.get(key)
        if key in ("C", "D", "K"):
            feasible = n_orders > 0 and (data_quality or {}).get("status") == "ready"
        else:
            feasible = bool(result) and result.get("available", True) and not result.get("error")
        coverage = float((result or {}).get("coverage_pct", 100 if feasible else 0) or 0)
        if key == "B" and (n_orders == 0 or (data_quality or {}).get("status") != "ready"):
            coverage = 0
        rows.append({"dimension": f"{labels.get(key, key)} (Bloc {key})", "feasible": bool(feasible),
                     "confidence_pct": round(min(100, max(0, coverage)), 1),
                     "missing_data": (result or {}).get("error", "Voir les limites du bloc et le contrôle qualité."),
                     "unlocks": "Analyse sur données complètes et rapprochées.",
                     "roadmap": "Compléter les données sources puis relancer l’étude.",
                     "note": "Couverture documentaire ; aucune probabilité de compétence ni de gain futur."})
        if key == "G":
            rows[-1].update(status="indicative" if feasible else "unavailable", scoring_eligible=False,
                missing_data=("Attribution indicative calculée sur proxies — non intégrée au scoring : portée méthodologique insuffisante pour mesurer la gestion effective."
                              if feasible else (result or {}).get("error", "Bloc G non calculé.")),
                unlocks="Lecture descriptive des effets allocation, sélection et interaction.",
                note="Le pourcentage mesure la couverture des données, pas la fiabilité de l’attribution.")
    overall = round(sum(r["confidence_pct"] for r in rows) / len(rows), 1) if rows else 0
    return {"overall_pct": overall, "rows": rows, "metric": "data_coverage",
            "coverage_note": f"{n_orders} ordres dans le périmètre arrêté. Complétude historique à rapprocher des relevés.",
            "narrative": "Indice de couverture documentaire des blocs demandés. Ce pourcentage ne mesure ni la confiance statistique, ni le talent du gérant. Les blocs indisponibles sont inclus à zéro. Les limites méthodologiques restent applicables même avec une couverture de 100 %.",
            "roadmap": [], "quality_status": (data_quality or {}).get("status", "unverified")}
