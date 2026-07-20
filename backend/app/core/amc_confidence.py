"""AMC study — confidence & limitations section.

Makes the confidence in the results *traceable* rather than a number dropped
on the page. Each dimension carries: what is feasible now, a confidence band,
the missing data, what that data would unlock, and the corresponding app
roadmap item (the "future development" the user asked to surface).

Confidence combines three drivers:
  (i)   data completeness vs what the ideal method requires (static),
  (ii)  statistical robustness computed at runtime (sample size, R²),
  (iii) assumption quality (fee add-back = exact; single current mark = medium;
        no continuous constituent prices = caps attribution).
"""
from __future__ import annotations

from typing import Dict, List, Optional


def build_confidence(blocks: Dict, block_a: Optional[dict], n_orders: int,
                     block_e_result: Optional[dict] = None,
                     vag_result: Optional[dict] = None,   # deprecated — ignored
                     attribution_result: Optional[dict] = None,
                     block_f_result: Optional[dict] = None,
                     brinson_result: Optional[dict] = None,
                     block_h_result: Optional[dict] = None,
                     block_i_result: Optional[dict] = None,
                     block_j_result: Optional[dict] = None) -> dict:
    """Assemble the confidence table + overall score from the produced blocks."""
    rows: list[dict] = []

    # ── Bloc A — factoriel ──
    a_conf = 0.0
    if block_a and block_a.get("available"):
        n_obs = (block_a.get("net") or {}).get("period", {}).get("n_obs", 0)
        r2 = ((block_a.get("net") or {}).get("regression", {}) or {}).get("r2", 0.0)
        # base 85%, penalise short samples
        a_conf = 0.85
        if n_obs < 60:
            a_conf = 0.55
        elif n_obs < 120:
            a_conf = 0.70
        elif n_obs < 250:
            a_conf = 0.80
        rows.append(_row(
            "Analyse factorielle (Bloc A)", True, a_conf,
            "Facteurs Ken French en USD uniquement ; pas de facteurs locaux CHF/EUR ; "
            "momentum (MOM) absent du store si non importé.",
            "Alpha propre par devise de classe + Carhart complet.",
            "Module facteurs locaux multi-devises + import du facteur momentum.",
            extra=f"n_obs={n_obs}, R²={r2}"))
    elif block_a is not None:
        rows.append(_row(
            "Analyse factorielle (Bloc A)", False, 0.0,
            block_a.get("error", "Données de facteurs FF non importées."),
            "Régression alpha/bêtas vs facteurs de risque.",
            "Importer les facteurs (bouton « Mettre à jour les facteurs »).",
            extra="bloc indisponible"))

    # ── Bloc B — attribution réalisée ──
    if "B_attribution" in blocks:
        rows.append(_row(
            "Attribution réalisée par sous-jacent (Bloc B)", True, 0.90,
            "—", "—", "—",
            extra="P&L réalisé exact depuis les ordres + décomposition prix/FX"))

    # ── Bloc C — trading ──
    if "C_trading" in blocks:
        rows.append(_row(
            "Round-trips / turnover (Bloc C)", True, 0.85,
            "—", "—", "—",
            extra="appariement FIFO complet depuis les ordres exécutés"))
        rows.append(_row(
            "Skill de timing fin (Bloc C)", True, 0.65,
            "Prix continus entre les transactions.",
            "Détection achat-au-plus-haut / vente-au-plus-bas le long de la trajectoire.",
            "Connecteur de prix marché par ISIN.",
            extra="limité aux points d'exécution"))

    # ── Bloc D — comportement ──
    if "D_behaviour" in blocks:
        rows.append(_row(
            "Comportement / conviction vs incertitude (Bloc D)", True, 0.85,
            "—", "—", "—",
            extra="durées, ordres annulés, fills partiels, sizing, flip-flop"))

    # ── Bloc E — Référentiel Inertiel ──
    if block_e_result and block_e_result.get("available"):
        source  = block_e_result.get("source", "accounting_identity")
        n_pos   = block_e_result.get("n_positions", 0)
        n_warns = block_e_result.get("n_price_warnings", 0)
        vag_pct = block_e_result.get("value_added_pct")
        e_conf  = 0.90 if source == "termsheet" else 0.75
        rows.append(_row(
            "Référentiel Inertiel — B&H vs NAV réelle (Bloc E)", True, e_conf,
            "—" if n_warns == 0 else f"{n_warns} position(s) avec prix yfinance T0 suspect.",
            "Couverture exacte à 100% des sous-jacents." if n_warns > 0 else "—",
            "Renseignez params.termsheet_positions pour la méthode exacte." if source != "termsheet" else "—",
            extra=f"source={source}, n_positions={n_pos}, "
                  f"VAG={vag_pct:+.1f}%" if vag_pct is not None else f"source={source}, n_positions={n_pos}"))
    else:
        rows.append(_row(
            "Référentiel Inertiel (Bloc E)", False, 0.0,
            "NAV historique insuffisante ou aucune source de composition (TS ou ordres).",
            "Comparaison NAV réelle vs Référentiel Inertiel passif.",
            "Renseignez params.termsheet_positions dans le manifeste."))

    # ── Bloc F — Réplicabilité ──
    if block_f_result and block_f_result.get("available"):
        score_f = block_f_result.get("score", 0)
        r2_pct  = block_f_result.get("r2_pct", 0)
        n_obs_f = block_f_result.get("n_obs", 0)
        f_conf  = 0.80 if n_obs_f >= 120 else 0.65 if n_obs_f >= 60 else 0.50
        rows.append(_row(
            "Réplicabilité — portefeuille réplicant vs NAV (Bloc F)", True, f_conf,
            "Facteurs FF en USD uniquement ; pas de version locale CHF/EUR.",
            "Score de réplicabilité multi-devise avec facteurs régionaux.",
            "Import des facteurs locaux multi-devises (feuille de route Bloc A).",
            extra=f"score={score_f}/100, R²={r2_pct}%, n_obs={n_obs_f}"))
    elif block_f_result is not None and not (block_f_result or {}).get("available"):
        rows.append(_row(
            "Réplicabilité (Bloc F)", False, 0.0,
            block_f_result.get("error", "Bloc A requis pour le Bloc F."),
            "Portefeuille réplicant factoriel, score 0-100.",
            "Activer et exécuter le Bloc A (régression Fama-French)."))
    elif "F_replicability" in blocks:
        rows.append(_row(
            "Réplicabilité (Bloc F)", False, 0.0,
            "Bloc A non disponible (données FF non importées).",
            "Portefeuille réplicant factoriel, score 0-100.",
            "Importer les facteurs FF puis relancer l'étude."))

    # ── Bloc H — Timing Score ──
    if block_h_result is not None:
        if block_h_result.get("available"):
            n_h      = block_h_result.get("n_trades_analyzed", 0)
            cov_h    = block_h_result.get("coverage_pct", 0) or 0
            score_h  = round((block_h_result.get("global_score_mean") or 0.5) * 100, 1)
            h_conf   = 0.80 if cov_h >= 50 else 0.65 if cov_h >= 20 else 0.50
            rows.append(_row(
                "Timing Score — Qualité du timing des ordres (Bloc H)", True, h_conf,
                "—" if cov_h >= 80 else f"{100-cov_h:.0f}% des ordres sans série de prix.",
                "Score de timing exact sur 100% des ordres avec prix intraday.",
                "Charger les séries de prix (sous-onglet Sous-jacents).",
                extra=f"score={score_h}/100, n_ordres={n_h}, couverture={cov_h:.0f}%"))
        else:
            rows.append(_row(
                "Timing Score (Bloc H)", False, 0.0,
                block_h_result.get("error", "Prix par sous-jacent requis (parquet store)."),
                "Évaluation du timing des achats/ventes vs trajectoire du titre.",
                "Charger les séries de prix dans l'onglet Sous-jacents."))
    elif "H_timing" in blocks:
        rows.append(_row(
            "Timing Score (Bloc H)", False, 0.0,
            "Aucune série de prix disponible dans le store local.",
            "Évaluation du timing des ordres vs trajectoire du titre.",
            "Importer les séries de prix (sous-onglet Sous-jacents)."))

    # ── Bloc I — Stock Picking Score ──
    if block_i_result is not None:
        if block_i_result.get("available"):
            n_i     = block_i_result.get("n_buys_analyzed", 0)
            cov_i   = block_i_result.get("coverage_pct", 0) or 0
            score_i = block_i_result.get("score", 0)
            i_conf  = 0.80 if cov_i >= 60 else 0.65 if cov_i >= 30 else 0.50
            rows.append(_row(
                "Stock Picking Score — Alpha des ordres vs benchmark (Bloc I)", True, i_conf,
                "—" if cov_i >= 80 else f"Horizon 12M incomplet pour {100-cov_i:.0f}% des positions.",
                "Alpha complet sur 100% des positions à tous les horizons.",
                "Attendre la clôture des positions ouvertes ou allonger l'historique.",
                extra=f"score={score_i}/100, n_trades={n_i}, couverture={cov_i:.0f}%"))
        else:
            rows.append(_row(
                "Stock Picking Score (Bloc I)", False, 0.0,
                block_i_result.get("error", "Prix par sous-jacent requis."),
                "Alpha de chaque ordre vs retour du benchmark au même horizon.",
                "Charger les séries de prix dans l'onglet Sous-jacents."))
    elif "I_stockpicking" in blocks:
        rows.append(_row(
            "Stock Picking Score (Bloc I)", False, 0.0,
            "Aucune série de prix disponible dans le store local.",
            "Alpha de sélection par titre vs benchmark (1M/3M/6M/12M).",
            "Importer les séries de prix (sous-onglet Sous-jacents)."))

    # ── Bloc J — Risk Management Score ──
    if block_j_result is not None:
        if block_j_result.get("available"):
            n_j   = block_j_result.get("n_obs", 0)
            cap_j = block_j_result.get("reliability_cap", 100)
            sc_j  = block_j_result.get("score", 0)
            bm_j  = block_j_result.get("benchmark_available", False)
            j_conf = round(cap_j / 100 * 0.85, 2)
            rows.append(_row(
                "Risk Management Score — Gestion du risque (Bloc J)", True, j_conf,
                "—" if bm_j else "Benchmark non disponible — capture ratios et DD relatif exclus.",
                "Score complet avec benchmark + historique NAV > 120 observations.",
                "Allonger l'historique NAV et vérifier le benchmark ticker.",
                extra=f"score={sc_j}/100, n_obs={n_j}, cap={cap_j}/100, "
                      f"benchmark={'oui' if bm_j else 'non'}"))
        else:
            rows.append(_row(
                "Risk Management Score (Bloc J)", False, 0.0,
                block_j_result.get("error", "Historique NAV insuffisant."),
                "5 sous-scores : drawdown, risque baissier, perf. ajustée, concentration, facteurs.",
                "Vérifier que l'historique NAV contient au moins 10 observations."))
    elif "J_riskmanagement" in blocks:
        rows.append(_row(
            "Risk Management Score (Bloc J)", False, 0.0,
            "Historique NAV insuffisant ou bloc désactivé.",
            "Évaluation complète de la gestion du risque (5 dimensions).",
            "Activer le Bloc J dans le manifest."))

    # ── Bloc G — Brinson ──
    if brinson_result and brinson_result.get("available"):
        n_sectors = len(brinson_result.get("sector_rows", []))
        n_hold_g  = brinson_result.get("n_holdings", 0)
        w_method  = brinson_result.get("weights_method", "")
        bw_method = brinson_result.get("bench_weight_method", "")
        g_conf    = 0.85 if w_method == "termsheet" else 0.75 if "inception_orders" in w_method else 0.60
        if "yfinance" in bw_method:
            g_conf = min(g_conf + 0.05, 0.90)
        rows.append(_row(
            "Attribution Brinson-Fachler par secteur (Bloc G)", True, g_conf,
            "Rendements sectoriels via ETFs SPDR US (biais USD) ; benchmark snapshot actuel.",
            "Brinson avec rendements sectoriels locaux (hedgés devise AMC).",
            "Facteurs locaux multi-devises + composition benchmark historique.",
            extra=f"sectors={n_sectors}, holdings={n_hold_g}, w={w_method}"))
    elif brinson_result is not None:
        rows.append(_row(
            "Attribution Brinson-Fachler (Bloc G)", False, 0.0,
            brinson_result.get("error", "Bloc G non calculé."),
            "Décomposition Allocation / Sélection / Interaction par secteur.",
            "Calculer le Bloc G depuis l'onglet G (nécessite les prix du Bloc F)."))

    # Order-book coverage caveat (affects B/C/D)
    coverage_note = (
        "Le carnet d'ordres couvre la vie du produit depuis l'émission ; les positions "
        "ouvertes avant le premier ordre (le cas échéant) sont clampées. "
        f"{n_orders} ordres analysés.")

    # Overall — weighted mean of feasible-dimension confidences
    feas = [r["confidence_pct"] for r in rows if r["feasible"] and r["confidence_pct"] > 0]
    overall = round(sum(feas) / len(feas), 1) if feas else 0.0

    return {
        "overall_pct": overall,
        "rows": rows,
        "coverage_note": coverage_note,
        "narrative": (
            f"Sans données de prix par constituant ni facteurs locaux, nous estimons la "
            f"confiance globale dans les résultats à ~{overall:.0f}%. Les blocs d'attribution "
            f"réalisée et de comportement (B, D) reposent sur des données exactes du carnet "
            f"d'ordres et sont les plus robustes. Les enrichissements listés ci-dessus "
            f"(connecteur de prix, facteurs locaux) constituent la feuille de route pour "
            f"porter cette confiance au-delà de 90%."),
        "roadmap": [
            {"item": "Connecteur de prix marché par ISIN (yfinance/Bloomberg)",
             "unlocks": "Attribution Brinson pondérée dans le temps, timing fin, trading-vs-portage complet"},
            {"item": "Import du facteur momentum + facteurs locaux multi-devises",
             "unlocks": "Modèle Carhart complet et alpha propre par devise de classe"},
            {"item": "Historique de composition daté (snapshots successifs)",
             "unlocks": "Dérive de poids dans le temps, attribution d'allocation vs sélection"},
        ],
    }


def _row(dimension, feasible, conf, missing, unlocks, roadmap, extra=""):
    return {
        "dimension": dimension,
        "feasible": feasible,
        "confidence_pct": round(conf * 100, 0),
        "missing_data": missing,
        "unlocks": unlocks,
        "roadmap": roadmap,
        "note": extra,
    }
