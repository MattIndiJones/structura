"""Manager Skill Score — global aggregator of all study blocks.

Combines Block A (alpha FF), Block I (stock picking), Block E (Référentiel Inertiel / VAG),
Block J (risk management), Block H (timing), Block D (conviction)
into a single 0-100 composite score.

Base weights (renormalized if a block is unavailable):
  Alpha FF              30%   (Bloc A)
  Stock Picking         25%   (Bloc I)
  Référentiel / VAG     20%   (Bloc E)
  Risk Mgmt             15%   (Bloc J)
  Timing                 7%   (Bloc H)
  Conviction             3%   (Bloc D)
"""
from __future__ import annotations

import math
from typing import Optional


BASE_WEIGHTS: dict[str, float] = {
    "alpha":         0.30,
    "stock_picking": 0.25,
    "vag":           0.20,
    "risk_mgmt":     0.15,
    "timing":        0.07,
    "conviction":    0.03,
}

_LABELS = [
    (80, "Gérant exceptionnel", "#10b981"),
    (60, "Bon gérant",          "#22c55e"),
    (40, "Neutre",              "#f59e0b"),
    (20, "Faible valeur ajoutée", "#f97316"),
    (0,  "Destructeur de valeur", "#ef4444"),
]

_DIM_LABELS = {
    "alpha":         "Alpha Fama-French (A)",
    "stock_picking": "Stock Picking (I)",
    "vag":           "Référentiel Inertiel / VAG (E)",
    "risk_mgmt":     "Risk Management (J)",
    "timing":        "Timing Score (H)",
    "conviction":    "Conviction (D)",
}


def _clamp(v: float) -> float:
    return max(0.0, min(100.0, v))


# ── Per-block conversions ────────────────────────────────────────────────────

def _alpha_score(block_a: Optional[dict]) -> Optional[float]:
    if not block_a or not block_a.get("available"):
        return None
    net = (block_a.get("net") or {})
    reg = net.get("regression") or {}
    alpha_ann  = reg.get("alpha_ann_pct") or 0.0
    alpha_t    = abs(reg.get("alpha_tstat") or 0.0)
    base = _clamp(50 + 50 * math.tanh(alpha_ann / 8))
    # Statistical confidence multiplier: applied as a pull TOWARD 50 (neutral),
    # not toward 0 — a non-significant alpha is uncertain, not confirmed negative.
    # Formula: 50 + (base − 50) × mult  →  mult=1.0 leaves base unchanged,
    # mult=0.70 shrinks the deviation from neutral by 30%.
    if alpha_t >= 2:     mult = 1.00
    elif alpha_t >= 1.5: mult = 0.90
    elif alpha_t >= 1:   mult = 0.80
    else:                mult = 0.70
    return _clamp(50 + (base - 50) * mult)


def _stockpicking_score(block_i: Optional[dict]) -> Optional[float]:
    if not block_i or not block_i.get("available"):
        return None
    return float(block_i.get("score", 50))


def _vag_score(study_result: dict, vag_result: Optional[dict] = None) -> tuple[Optional[float], Optional[float]]:
    """Returns (score_0_100, vag_ann_pct_used).

    Primary source: study_result["block_e"].value_added_pct (annualized).
    Legacy fallback: external vag_result (deprecated).
    """
    import datetime as _dt

    # Primary: block_e embedded in study_result
    block_e = (study_result or {}).get("block_e") or {}
    if block_e.get("available"):
        total_pct = block_e.get("value_added_pct")
        if total_pct is not None:
            meta  = (study_result or {}).get("meta") or {}
            start = meta.get("nav_start_date")
            end   = meta.get("nav_current_date")
            try:
                d0   = _dt.datetime.strptime(str(start)[:10], "%Y-%m-%d")
                d1   = _dt.datetime.strptime(str(end)[:10], "%Y-%m-%d")
                yrs  = max((d1 - d0).days / 365.25, 0.1)
                vag_ann = float(total_pct) / yrs
            except Exception:
                vag_ann = float(total_pct)
            score = _clamp(50 + 50 * math.tanh(vag_ann / 20))
            return score, float(vag_ann)

    # Legacy fallback (external vag_result, deprecated)
    if not vag_result or vag_result.get("error"):
        return None, None
    vag_ann = None
    if "vag_ann_pct" in vag_result:
        vag_ann = vag_result["vag_ann_pct"]
    elif "metrics" in vag_result:
        vag_met = (vag_result["metrics"] or {}).get("vag") or {}
        vag_ann = vag_met.get("ann_ret_pct")
        if vag_ann is None:
            bh  = (vag_result["metrics"] or {}).get("bh") or {}
            yrs = float(bh.get("years") or 0)
            tot = vag_met.get("total_pct")
            if tot is not None and yrs > 0.5:
                vag_ann = float(tot) / yrs
            else:
                vag_ann = tot
    if vag_ann is None:
        return None, None
    score = _clamp(50 + 50 * math.tanh(float(vag_ann) / 20))
    return score, float(vag_ann)


def _riskmanagement_score(block_j: Optional[dict]) -> Optional[float]:
    if not block_j or not block_j.get("available"):
        return None
    return float(block_j.get("score", 50))


def _timing_score(block_h: Optional[dict]) -> Optional[float]:
    if not block_h or not block_h.get("available"):
        return None
    g = block_h.get("global_score_mean")
    if g is None:
        return None
    return _clamp(50 + 200 * (float(g) - 0.5))


def _conviction_score(block_d: Optional[dict]) -> Optional[float]:
    if not block_d:
        return None
    matrix = block_d.get("conviction_matrix") or {}
    counts = matrix.get("counts") or {}
    total = sum(counts.values())
    if total == 0:
        return None
    cw = counts.get("conviction_winners", 0)
    tw = counts.get("tactical_winners", 0)
    sl = counts.get("stubborn_losers", 0)
    uc = counts.get("uncertainty", 0)
    quality = (cw + tw - sl - uc) / total
    return _clamp(50 + quality * 50)


# ── Label + color ────────────────────────────────────────────────────────────

def _label_color(score: int) -> tuple[str, str]:
    for threshold, label, color in _LABELS:
        if score >= threshold:
            return label, color
    return _LABELS[-1][1], _LABELS[-1][2]


# ── Interpretation ───────────────────────────────────────────────────────────

def _interpret(score: int, label: str, dims: list[dict],
               scores: dict[str, Optional[float]]) -> str:
    parts = []

    parts.append(
        f"Manager Skill Score de {score}/100 ({label}) — "
        "évaluation composite basée sur les blocs disponibles."
    )

    # best and worst
    available = {k: v for k, v in scores.items() if v is not None}
    if len(available) >= 2:
        best_k  = max(available, key=lambda k: available[k])
        worst_k = min(available, key=lambda k: available[k])
        parts.append(
            f"Point fort : {_DIM_LABELS[best_k]} ({available[best_k]:.0f}/100). "
            f"Point faible : {_DIM_LABELS[worst_k]} ({available[worst_k]:.0f}/100)."
        )

    # specific alerts
    if scores.get("alpha") is not None and scores["alpha"] < 40:
        parts.append(
            "⚠ L'alpha Fama-French est faible ou non significatif — "
            "la surperformance, si elle existe, n'est pas attribuable à la sélection active."
        )
    if scores.get("timing") is not None and scores["timing"] < 40:
        parts.append(
            "⚠ Le timing des ordres est systématiquement inférieur à l'aléatoire — "
            "biais comportemental documenté."
        )
    if scores.get("risk_mgmt") is not None and scores["risk_mgmt"] < 40:
        parts.append(
            "⚠ La gestion du risque est insuffisante — drawdowns importants ou "
            "ratios ajustés du risque faibles."
        )

    missing = [_DIM_LABELS[k] for k, v in scores.items() if v is None]
    if missing:
        parts.append(
            f"Blocs non disponibles : {', '.join(missing)}. "
            "Les poids ont été renormalisés sur les blocs disponibles."
        )

    return "  ".join(parts)


# ── Public entry point ───────────────────────────────────────────────────────

def compute_manager_skill_score(
    study_result: dict,
    vag_result: Optional[dict] = None,
) -> dict:
    """Compute the Manager Skill Score from all available study blocks.

    Args:
        study_result: output of run_study()
        vag_result:   optional VAG result (from the VAG endpoint)

    Returns:
        Rich result dict with score, dimensions, interpretation.
    """
    vag_score_val, vag_ann_raw = _vag_score(study_result, vag_result)
    raw_scores: dict[str, Optional[float]] = {
        "alpha":         _alpha_score(study_result.get("block_a")),
        "stock_picking": _stockpicking_score(study_result.get("block_i")),
        "vag":           vag_score_val,
        "risk_mgmt":     _riskmanagement_score(study_result.get("block_j")),
        "timing":        _timing_score(study_result.get("block_h")),
        "conviction":    _conviction_score(study_result.get("block_d")),
    }

    # Renormalize weights for available dimensions
    available_keys = [k for k, v in raw_scores.items() if v is not None]
    if not available_keys:
        return {
            "available": False,
            "error": "Aucun bloc disponible pour calculer le Manager Skill Score.",
        }

    total_w = sum(BASE_WEIGHTS[k] for k in available_keys)
    norm_weights = {k: BASE_WEIGHTS[k] / total_w for k in available_keys}

    composite = sum(norm_weights[k] * raw_scores[k] for k in available_keys)
    score = max(0, min(100, round(composite)))
    label, color = _label_color(score)

    # Build dimensions list
    dimensions = []
    for k in ("alpha", "stock_picking", "vag", "risk_mgmt", "timing", "conviction"):
        s = raw_scores[k]
        eff_w = norm_weights.get(k, 0)
        dim: dict = {
            "key":                  k,
            "label":                _DIM_LABELS[k],
            "weight_base_pct":      round(BASE_WEIGHTS[k] * 100, 1),
            "weight_effective_pct": round(eff_w * 100, 1),
            "score":                round(s, 1) if s is not None else None,
            "weighted_contribution": round(eff_w * s, 1) if s is not None else None,
            "available":            s is not None,
        }
        if k == "vag":
            dim["vag_ann_pct"] = round(vag_ann_raw, 2) if vag_ann_raw is not None else None
        dimensions.append(dim)

    interp = _interpret(score, label, dimensions, raw_scores)

    return {
        "available":            True,
        "score":                score,
        "score_label":          label,
        "score_color":          color,
        "dimensions":           dimensions,
        "n_dimensions_available": len(available_keys),
        "interpretation":       interp,
    }
