"""Block F — Réplicabilité de la stratégie.

Construit un portefeuille réplicant passif à partir des bêtas Fama-French
estimés en Bloc A, compare sa trajectoire à la NAV réelle, et calcule
un score de réplicabilité 0-100.

Aucune donnée externe supplémentaire requise : tout vient du résultat Bloc A.
"""
from __future__ import annotations

import math


# ── point d'entrée public ─────────────────────────────────────────────


def compute_replicability(block_a: dict) -> dict:
    """Compute Block F from Block A net regression results.

    Parameters
    ----------
    block_a : dict
        Full block_a dict (as returned by _run_block_a in amc_study).

    Returns
    -------
    dict with keys: available, score, profile, r2_pct, alpha_ann_pct,
    alpha_tstat, replicant_total_pct, amc_total_pct, alpha_gap_pct,
    replicant_nav, amc_nav, factor_contributions, interpretation,
    score_components, period_start, period_end, n_obs.
    """
    if not block_a or not block_a.get("available"):
        return {
            "available": False,
            "error": "Bloc A non disponible — régression Fama-French requise pour le Bloc F.",
        }

    net = block_a.get("net") or {}
    regression = net.get("regression") or {}
    data_used = net.get("data_used") or []

    if not data_used:
        return {
            "available": False,
            "error": "Données de régression journalières absentes du Bloc A "
                     "(data_used vide). Relancer l'étude.",
        }

    # ── 1. Bêtas et paramètres de régression ─────────────────────────
    factor_rows = regression.get("factors") or []
    betas: dict[str, float] = {f["name"]: float(f["beta"]) for f in factor_rows}

    if not betas:
        return {
            "available": False,
            "error": "Aucun bêta factoriel dans la régression Bloc A.",
        }

    r2 = float(regression.get("r2") or 0.0)
    alpha_daily = float(regression.get("alpha_daily") or 0.0)
    alpha_tstat = float(regression.get("alpha_tstat") or 0.0)
    alpha_ann_pct = float(regression.get("alpha_ann_pct") or 0.0)

    # ── 2. Reconstruction des séries réplicant et AMC ─────────────────
    # R_rep(t) = RF(t) + Σ β_i × F_i(t)
    # F_i(t) est le rendement excédentaire du facteur (déjà au-dessus du RF
    # dans les données Ken French).
    p_rep = 100.0
    p_amc = 100.0
    replicant_nav: list[dict] = []
    amc_nav: list[dict] = []
    dates: list[str] = []

    for row in data_used:
        date = str(row.get("date") or "")
        rf = float(row.get("RF") or 0.0)
        amc_ret = float(row.get("amc_ret") or 0.0)

        factor_sum = sum(
            betas.get(f, 0.0) * float(row.get(f) or 0.0)
            for f in betas
        )
        r_rep = rf + factor_sum

        p_rep *= 1.0 + r_rep
        p_amc *= 1.0 + amc_ret

        dates.append(date)
        replicant_nav.append({"date": date, "value": round(p_rep, 4)})
        amc_nav.append({"date": date, "value": round(p_amc, 4)})

    if not replicant_nav:
        return {"available": False, "error": "Aucune observation dans data_used."}

    replicant_total_pct = round((p_rep / 100.0 - 1.0) * 100.0, 2)
    amc_total_pct = round((p_amc / 100.0 - 1.0) * 100.0, 2)
    alpha_gap_pct = round(amc_total_pct - replicant_total_pct, 2)

    # ── 3. Décomposition par facteur ──────────────────────────────────
    factor_contributions = _factor_contributions(data_used, betas)

    # ── 4. Score de réplicabilité + IC 95% ───────────────────────────
    n_obs = len(data_used)
    score, score_components = _score(r2, replicant_total_pct, amc_total_pct, alpha_tstat)

    # Intervalle de confiance basé sur l'erreur d'échantillonnage du R²
    # se(R²) ≈ 2 × √(R²) × (1 − R²) / √n  (méthode delta)
    r2_se = 2.0 * math.sqrt(max(r2, 0.0)) * (1.0 - r2) / math.sqrt(max(n_obs, 1))
    r2_low  = max(0.0, r2 - 1.96 * r2_se)
    r2_high = min(1.0, r2 + 1.96 * r2_se)
    score_ci_low,  _ = _score(r2_low,  replicant_total_pct, amc_total_pct, alpha_tstat)
    score_ci_high, _ = _score(r2_high, replicant_total_pct, amc_total_pct, alpha_tstat)

    # ── 5. Profil et interprétation ───────────────────────────────────
    profile, profile_color = _profile(score)
    interpretation = _interpretation(
        score, profile, replicant_total_pct, amc_total_pct,
        alpha_ann_pct, alpha_tstat, r2,
    )

    return {
        "available": True,
        # Score synthétique
        "score": score,
        "score_ci_low":  score_ci_low,
        "score_ci_high": score_ci_high,
        "r2_se_pct": round(r2_se * 100.0, 1),
        "score_components": score_components,
        "profile": profile,
        "profile_color": profile_color,
        # Statistiques de régression
        "r2_pct": round(r2 * 100.0, 1),
        "alpha_ann_pct": alpha_ann_pct,
        "alpha_tstat": alpha_tstat,
        # Performances comparées
        "replicant_total_pct": replicant_total_pct,
        "amc_total_pct": amc_total_pct,
        "alpha_gap_pct": alpha_gap_pct,
        # Séries temporelles (base 100 virtuelle au début de la période)
        "replicant_nav": replicant_nav,
        "amc_nav": amc_nav,
        # Décomposition factorielle
        "factor_contributions": factor_contributions,
        "factors_used": list(betas.keys()),
        # Période
        "period_start": dates[0] if dates else None,
        "period_end": dates[-1] if dates else None,
        "n_obs": n_obs,
        # Texte
        "interpretation": interpretation,
    }


# ── Helpers privés ────────────────────────────────────────────────────


def _factor_contributions(data_used: list, betas: dict) -> list:
    """Contribution de chaque facteur à la performance cumulée du réplicant.

    Approximation additive : Σ β_i × R_cumulé_facteur_i.
    Valide pour des périodes courtes (<2 ans) et des bêtas modérés.
    """
    contribs = {}
    for f, beta in betas.items():
        p = 1.0
        for row in data_used:
            fi = float(row.get(f) or 0.0)
            p *= 1.0 + beta * fi
        contribs[f] = round((p - 1.0) * 100.0, 2)

    result = [
        {"name": f, "beta": round(beta, 4), "contribution_pct": contribs[f]}
        for f, beta in betas.items()
    ]
    result.sort(key=lambda x: abs(x["contribution_pct"]), reverse=True)
    return result


def _score(r2: float, rep_total: float, amc_total: float,
           alpha_tstat: float) -> tuple[int, dict]:
    """Calcule le score de réplicabilité 0-100 et ses composantes.

    Composantes (pondérations) :
      - C1 : R²          → 40 % — part de la variance expliquée par les facteurs
      - C2 : Couverture   → 35 % — part de la performance capturée par le réplicant
      - C3 : α non-signi  → 25 % — l'alpha est-il du bruit statistique ?
    """
    # C1 — R² (0-100 linéaire)
    c1 = r2 * 100.0

    # C2 — couverture de performance (formule symétrique)
    # min(ratio, 1/ratio) = 1 quand rep=amc, décroît dans les deux sens
    if amc_total > 0 and rep_total > 0:
        ratio = rep_total / amc_total
        c2 = min(ratio, 1.0 / ratio) * 100.0
    elif amc_total < 0 and rep_total < 0:
        ratio = rep_total / amc_total  # positif car même signe
        c2 = min(ratio, 1.0 / ratio) * 100.0
    elif rep_total <= 0 < amc_total:
        # Réplicant négatif, AMC positif → alpha compense les facteurs → peu réplicable
        c2 = 0.0
    elif amc_total <= 0 < rep_total:
        # Réplicant positif, AMC négatif → facteurs ont sur-performé → très réplicable
        c2 = 100.0
    else:
        c2 = 50.0
    c2 = max(0.0, min(100.0, c2))

    # C3 — alpha non-significatif → score élevé (stratégie réplicable)
    c3 = (1.0 - min(abs(alpha_tstat) / 3.0, 1.0)) * 100.0

    score = 0.40 * c1 + 0.35 * c2 + 0.25 * c3
    score = max(0, min(100, round(score)))

    return int(score), {
        "r2_component": round(c1, 1),
        "perf_coverage": round(c2, 1),
        "alpha_insig": round(c3, 1),
    }


def _profile(score: int) -> tuple[str, str]:
    if score >= 80:
        return "Quasi-systématique", "blue"
    if score >= 60:
        return "Principalement systématique", "blue"
    if score >= 40:
        return "Mixte", "amber"
    if score >= 20:
        return "Principalement discrétionnaire", "amber"
    return "Pur discrétionnaire", "emerald"


def _interpretation(
    score: int, profile: str,
    rep_total: float, amc_total: float,
    alpha_ann_pct: float, alpha_tstat: float, r2: float,
) -> str:
    r2_pct = r2 * 100.0
    alpha_sig = abs(alpha_tstat) >= 2.0
    gap = amc_total - rep_total

    parts = [
        f"Score de réplicabilité : {score}/100 — {profile}.",
        f"Les facteurs Fama-French expliquent {r2_pct:.1f}% de la variance des rendements "
        f"journaliers (R²). Sur la même période, le portefeuille réplicant aurait réalisé "
        f"{rep_total:+.2f}% vs {amc_total:+.2f}% pour l'AMC réel. "
        f"La couverture de performance est calculée par la formule symétrique "
        f"min(rep/amc, amc/rep) × 100, qui pénalise autant la sur-performance que la "
        f"sous-performance du réplicant par rapport à l'AMC.",
    ]

    if gap > 0.5 and alpha_sig:
        parts.append(
            f"L'alpha annualisé de {alpha_ann_pct:+.2f}% est statistiquement significatif "
            f"(t = {alpha_tstat:.2f}) : le gérant génère une valeur ajoutée réelle au-delà "
            f"des primes factorielles."
        )
    elif gap > 0.5 and not alpha_sig:
        parts.append(
            f"L'écart de {gap:+.2f}% en faveur du gérant n'est pas statistiquement significatif "
            f"(t = {alpha_tstat:.2f}) — il pourrait s'agir de chance ou d'un historique trop court."
        )
    elif gap < -0.5:
        parts.append(
            f"Le réplicant sur-performe l'AMC de {abs(gap):.2f}% : les expositions factorielles "
            f"seules auraient été plus efficaces sur cette période."
        )

    if score >= 60:
        parts.append(
            "Implication pratique : un panier d'ETFs factoriels couvre l'essentiel du profil "
            "risque/rendement de cette stratégie."
        )
    elif score < 40:
        parts.append(
            "Implication pratique : la stratégie présente un fort caractère discrétionnaire — "
            "le gérant s'écarte significativement des primes factorielles documentées."
        )

    return " ".join(parts)
