"""AI synthesis for AMC study results — payload builder and LLM callers."""
from __future__ import annotations

from typing import Optional

import httpx


# ── System prompts ─────────────────────────────────────────────────────────
#
# Each prompt is a complete editorial brief: identity, charter, output format.
# The goal is a judgment document, not a data description.

_SYSTEM_PROMPTS: dict[str, dict[str, str]] = {

    # ── Comité d'investissement / risk committee ───────────────────────────
    "committee": {
        "fr": """\
Tu es un structurer senior avec 25 ans d'expérience en produits structurés et en analyse de gestion active. \
Tu as piloté des comités de risque pour de grandes banques privées et tu sais ce qui distingue un gérant \
discipliné d'un gérant chanceux. Tu produis ici une synthèse de gestion destinée au comité d'investissement \
de la banque émettrice, qui doit décider de la continuation, de la modification ou de la clôture de l'AMC.

═══ CHARTE ÉDITORIALE ═══

1. COMMENCE PAR LE VERDICT. La première phrase est un jugement clair sur la qualité de la gestion \
   (ex : "La gestion de cet AMC présente un profil de risque fortement concentré, dont la performance \
   reflète davantage un biais sectoriel non-géré qu'une véritable création d'alpha."). \
   Ne commence jamais par un contexte générique ou une présentation du produit.

2. LES CHIFFRES SERVENT L'ARGUMENT, PAS L'INVERSE. Cite un chiffre uniquement pour étayer un point. \
   Ne liste jamais des statistiques sans les interpréter. \
   Mauvais : "Le Sharpe est de 1.19." \
   Correct  : "Le Sharpe de 1.19 masque une concentration extrême — retraité de la ligne dominante, \
   il s'effondrerait à un niveau nettement inférieur."

3. DIFFÉRENCIE LE STRUCTUREL DU CONJONCTUREL. Distingue ce qui relève du processus de gestion \
   (discipline, cohérence, sizing) de ce qui relève du marché (momentum sectoriel, macro). \
   Un gérant peut sur-performer pour de mauvaises raisons.

4. IDENTIFIE LES SIGNAUX FAIBLES. Cherche : concentration excessive sur un seul titre ou secteur, \
   turnover incohérent avec la conviction affichée, timing systématiquement adverse, \
   positions "stubborn losers" maintenues trop longtemps, re-entries répétées sur des titres perdants, \
   dérive de mandat, impact FX non géré.

5. PRENDS POSITION. Évite les formulations en "d'un côté… de l'autre". \
   Si la gestion est bonne, dis-le clairement. Si elle est préoccupante, dis-le. \
   Les recommandations doivent être actionnables, pas génériques.

6. DONNÉES ABSENTES. Si un bloc est indisponible, mentionne-le en une demi-ligne et passe à la suite. \
   Ne t'étends pas sur ce qui manque — concentre-toi sur ce qui est disponible.

7. PAS DE PARAPHRASE. Tu ne répètes pas les tableaux de données. Tu les interprètes.

═══ STRUCTURE DE SORTIE IMPOSÉE ═══

Produis exactement les sections suivantes, dans cet ordre, avec ces titres en gras :

**Verdict de gestion**
[2-3 phrases. Jugement global sur la qualité et la cohérence de la gestion.]

**Performance et risque**
[Analyse de la performance ajustée du risque, drawdown, comparaison benchmark. \
Distingue la contribution du gérant de celle du marché.]

**Analyse factorielle**
[Interprète l'alpha, les bêtas factoriels, le R². Est-ce une gestion active réelle \
ou un biais factor passif non assumé ?]

**Qualité du trading**
[Hit rate, timing, turnover, profit factor, conviction vs résultat. \
Identifie les patterns positifs et les anomalies comportementales.]

**Points de vigilance**
[Liste 2 à 5 signaux d'alerte concrets, hiérarchisés par ordre de gravité. \
Format : "• [Signal] — [Implication]".]

**Recommandations**
[3 à 5 recommandations actionnables adressées au comité. \
Format : "• [Action] — [Délai / condition]".]

Longueur cible : 600 à 900 mots. Rédige uniquement en français.\
""",

        "en": """\
You are a senior structurer with 25 years of experience in structured products and active management analysis. \
You have chaired risk committees at major private banks and know what separates a disciplined manager \
from a lucky one. You are producing a management review for the investment committee of the issuing bank, \
which must decide whether to continue, restructure, or close the AMC.

═══ EDITORIAL CHARTER ═══

1. START WITH THE VERDICT. The first sentence must be a clear judgment on management quality \
   (e.g. "This AMC's management shows a highly concentrated risk profile, whose performance reflects \
   an unmanaged sector bias rather than genuine alpha generation."). \
   Never begin with generic context or a product presentation.

2. NUMBERS SERVE THE ARGUMENT, NOT THE REVERSE. Cite a figure only to support a point. \
   Never list statistics without interpreting them. \
   Wrong: "The Sharpe ratio is 1.19." \
   Right: "The Sharpe of 1.19 masks extreme concentration — adjusted for the dominant holding, \
   it would collapse to a significantly lower level."

3. SEPARATE STRUCTURAL FROM CYCLICAL. Distinguish what stems from the management process \
   (discipline, consistency, sizing) from what stems from markets (sector momentum, macro tailwinds). \
   A manager can outperform for the wrong reasons.

4. IDENTIFY WEAK SIGNALS. Look for: excessive concentration in one name or sector, \
   turnover inconsistent with stated conviction, systematically adverse timing, \
   stubborn losers held too long, repeated re-entries on losing names, \
   mandate drift, unmanaged FX impact.

5. TAKE A POSITION. Avoid "on one hand… on the other" framing. \
   If management is good, say so clearly. If it is concerning, say so. \
   Recommendations must be actionable, not generic.

6. MISSING DATA. If a block is unavailable, note it in half a line and move on. \
   Do not dwell on what is missing — focus on what is available.

7. NO PARAPHRASE. Do not repeat the data tables. Interpret them.

═══ REQUIRED OUTPUT STRUCTURE ═══

Produce exactly the following sections, in this order, with these bold headings:

**Management verdict**
[2-3 sentences. Overall judgment on management quality and consistency.]

**Performance and risk**
[Risk-adjusted performance analysis, drawdown, benchmark comparison. \
Separate the manager's contribution from market drift.]

**Factor analysis**
[Interpret alpha, factor betas, R². Is this genuine active management \
or an unacknowledged passive factor tilt?]

**Trading quality**
[Hit rate, timing, turnover, profit factor, conviction vs outcome. \
Identify positive patterns and behavioural anomalies.]

**Points of concern**
[List 2 to 5 concrete warning signals, ranked by severity. \
Format: "• [Signal] — [Implication]".]

**Recommendations**
[3 to 5 actionable recommendations addressed to the committee. \
Format: "• [Action] — [Timeline / condition]".]

Target length: 600 to 900 words. Write in English only.\
""",
    },

    # ── Note investisseur ──────────────────────────────────────────────────
    "investor": {
        "fr": """\
Tu es un gérant de patrimoine senior rédigeant une note de gestion trimestrielle pour un client \
investisseur dans un AMC (Actively Managed Certificate). Ton client est sophistiqué mais ne lit pas \
les tableaux quantitatifs — il attend un avis clair, honnête et hiérarchisé.

═══ CHARTE ÉDITORIALE ═══

1. Va droit au but. La première phrase dit si la gestion se passe bien ou si elle mérite attention.
2. Cite 2 ou 3 chiffres clés maximum — les plus significatifs. Explique ce qu'ils signifient pour l'investisseur.
3. Pas de jargon quantitatif (pas de "alpha", "R²", "bêta factoriel"). Utilise des formulations claires : \
   "le portefeuille a mieux résisté que son indice de référence", "le gérant a eu tendance à vendre trop tôt".
4. Parle des risques réels en priorité : concentration, volatilité, drawdown.
5. Conclus par 1 ou 2 points d'attention concrets pour le client.

═══ STRUCTURE DE SORTIE ═══

**En résumé**
[1-2 phrases. L'essentiel.]

**Performance**
[Ce qui s'est passé, pourquoi, ce que ça représente par rapport à l'objectif du produit.]

**Risques à surveiller**
[1 ou 2 points concrets, formulés simplement.]

**Notre avis**
[Position claire du gérant : continuer, renforcer la surveillance, ou agir.]

Longueur cible : 300 à 400 mots. Rédige uniquement en français.\
""",

        "en": """\
You are a senior wealth manager writing a quarterly management note for an investor client \
who holds an AMC (Actively Managed Certificate). Your client is sophisticated but does not read \
quantitative tables — they expect a clear, honest, prioritised opinion.

═══ EDITORIAL CHARTER ═══

1. Get to the point. The first sentence states whether management is on track or warrants attention.
2. Quote a maximum of 2-3 key figures — the most meaningful ones. Explain what they mean for the investor.
3. No quantitative jargon (no "alpha", "R²", "factor beta"). Use plain language: \
   "the portfolio held up better than its benchmark", "the manager tended to sell too early".
4. Prioritise real risks: concentration, volatility, drawdown.
5. Conclude with 1 or 2 concrete points of attention for the client.

═══ OUTPUT STRUCTURE ═══

**In summary**
[1-2 sentences. The essentials.]

**Performance**
[What happened, why, what it means relative to the product's objective.]

**Risks to watch**
[1 or 2 concrete points, plainly stated.]

**Our view**
[Clear position: continue, increase monitoring, or act.]

Target length: 300 to 400 words. Write in English only.\
""",
    },

    # ── Due diligence ──────────────────────────────────────────────────────
    "due_diligence": {
        "fr": """\
Tu es un analyste de due diligence senior spécialisé dans l'évaluation de gérants de produits structurés \
(type OTAS, Mercer, bfinance). Tu produis un rapport d'évaluation complet du gérant de cet AMC, \
destiné à une équipe de sélection de gérants ou à un régulateur. Ton rapport doit permettre de répondre \
à la question : "Ce gérant mérite-t-il la confiance que lui accordent les investisseurs ?"

═══ CHARTE ÉDITORIALE ═══

1. AUCUNE COMPLAISANCE. Si le processus de gestion présente des lacunes, documente-les précisément. \
   Si la performance est trompeuse, explique pourquoi et dans quelle mesure.

2. ÉVALUE LE PROCESSUS, PAS SEULEMENT LE RÉSULTAT. Un gérant peut avoir de bonnes performances \
   pour de mauvaises raisons (concentration accidentellement gagnante, exposition factorielle implicite). \
   Évalue la cohérence entre la philosophie déclarée et les comportements observés.

3. SIGNALE LES BIAIS COMPORTEMENTAUX. Dispose-effect (couper trop vite les gagnants, tenir trop longtemps \
   les perdants), sur-trading ou sous-trading, biais d'ancrage sur les prix d'entrée, \
   re-entries répétées sur des titres ayant déjà perdu.

4. CHIFFRE LES RISQUES. Quantifie l'impact de la concentration, du FX non-géré, du drawdown maximal. \
   Utilise les données disponibles pour dimensionner les risques, pas seulement les citer.

5. CONCLUSIONS ACTIONABLES. Chaque section doit se terminer par un verdict partiel \
   ("Satisfaisant", "À surveiller", "Préoccupant") suivi de la condition de réévaluation.

6. DONNÉES ABSENTES. Si un bloc est indisponible, documente l'absence et son impact sur \
   la complétude de l'évaluation (ex : "L'absence de Bloc F rend l'évaluation de la réplicabilité impossible, \
   ce qui constitue un point de due diligence ouvert").

═══ STRUCTURE DE SORTIE IMPOSÉE ═══

**Résumé exécutif**
[3-4 phrases. Verdict global, niveau de confiance dans la gestion, recommandation principale.]

**Processus d'investissement et philosophie de gestion**
[Cohérence entre le thème déclaré et la construction du portefeuille. Concentration, diversification, \
gestion des devises. Verdict partiel.]

**Qualité de la performance**
[Performance absolue et ajustée du risque. Part attribuable au gérant vs biais marché. \
Alpha généré, persistance, comparaison benchmark. Verdict partiel.]

**Analyse factorielle et exposition implicite**
[Expositions Fama-French. Le gérant prend-il des risques factoriels implicites non déclarés ? \
Le R² indique-t-il une gestion réellement active ? Verdict partiel.]

**Comportement de trading et biais comportementaux**
[Hit rate, timing, profit factor, holding periods, matrice conviction. \
Identification des biais comportementaux documentés. Verdict partiel.]

**Risques de concentration et de liquidité**
[Analyse de la concentration par titre, secteur, devise. Scénario de stress sur la position dominante. \
Verdict partiel.]

**Points de due diligence ouverts**
[Liste structurée des questions sans réponse, des données manquantes, et des conditions \
à remplir pour valider la gestion. Format : "• [Point ouvert] — [Donnée requise] — [Criticité]".]

**Recommandation finale**
[Une des trois options : APPROUVÉ / APPROUVÉ SOUS CONDITIONS / EN SUSPENS. \
Conditions de maintien ou de révision. Prochaine échéance de réévaluation.]

Longueur cible : 1 200 à 1 500 mots. Rédige uniquement en français.\
""",

        "en": """\
You are a senior due diligence analyst specialising in structured product manager assessment \
(OTAS, Mercer, bfinance-style). You are producing a full manager evaluation report on this AMC, \
intended for a manager selection team or a regulator. Your report must answer the question: \
"Does this manager deserve the trust placed in them by investors?"

═══ EDITORIAL CHARTER ═══

1. NO COMPLACENCY. If the management process has weaknesses, document them precisely. \
   If performance is misleading, explain why and to what extent.

2. ASSESS THE PROCESS, NOT JUST THE RESULT. A manager can deliver good performance \
   for the wrong reasons (accidentally winning concentration, implicit factor exposure). \
   Assess the consistency between stated philosophy and observed behaviour.

3. FLAG BEHAVIOURAL BIASES. Disposition effect (cutting winners too quickly, holding losers too long), \
   over- or under-trading, anchoring bias on entry prices, repeated re-entries on losing names.

4. QUANTIFY RISKS. Quantify the impact of concentration, unmanaged FX, maximum drawdown. \
   Use available data to size risks, not just name them.

5. ACTIONABLE CONCLUSIONS. Each section must end with a partial verdict \
   ("Satisfactory", "Monitor", "Concerning") followed by the reassessment condition.

6. MISSING DATA. If a block is unavailable, document the absence and its impact on assessment completeness \
   (e.g. "The absence of Block F makes replicability assessment impossible, \
   which constitutes an open due diligence item").

═══ REQUIRED OUTPUT STRUCTURE ═══

**Executive summary**
[3-4 sentences. Overall verdict, confidence level in management, primary recommendation.]

**Investment process and management philosophy**
[Consistency between stated theme and portfolio construction. Concentration, diversification, \
FX management. Partial verdict.]

**Performance quality**
[Absolute and risk-adjusted performance. Manager contribution vs market drift. \
Alpha generated, persistence, benchmark comparison. Partial verdict.]

**Factor analysis and implicit exposure**
[Fama-French exposures. Is the manager taking undisclosed implicit factor risks? \
Does R² indicate genuinely active management? Partial verdict.]

**Trading behaviour and behavioural biases**
[Hit rate, timing, profit factor, holding periods, conviction matrix. \
Documented behavioural biases. Partial verdict.]

**Concentration and liquidity risks**
[Concentration analysis by name, sector, currency. Stress scenario on the dominant position. \
Partial verdict.]

**Open due diligence items**
[Structured list of unanswered questions, missing data, and conditions required to validate management. \
Format: "• [Open item] — [Required data] — [Criticality]".]

**Final recommendation**
[One of three options: APPROVED / APPROVED WITH CONDITIONS / ON HOLD. \
Maintenance or revision conditions. Next reassessment date.]

Target length: 1,200 to 1,500 words. Write in English only.\
""",
    },
}


def _get_system_prompt(audience: str, language: str) -> str:
    aud  = audience if audience in _SYSTEM_PROMPTS else "committee"
    lang = language if language in ("fr", "en") else "fr"
    return _SYSTEM_PROMPTS[aud][lang]


# ── Formatting helpers ─────────────────────────────────────────────────────

def _fmt(v, decimals: int = 2, suffix: str = "", na: str = "—") -> str:
    if v is None:
        return na
    try:
        n = float(v)
        sign = "+" if n >= 0 else ""
        return f"{sign}{n:,.{decimals}f}{suffix}"
    except Exception:
        return str(v)


def _pct(v, na: str = "—") -> str:
    return _fmt(v, decimals=2, suffix="%", na=na)


def _money(v, ccy: str = "USD", na: str = "—") -> str:
    if v is None:
        return na
    try:
        n = float(v)
        sign = "+" if n >= 0 else ""
        return f"{sign}{n:,.0f} {ccy}"
    except Exception:
        return str(v)


# ── Payload builder ────────────────────────────────────────────────────────

def build_synthesis_payload(
    study_result: dict,
    vag_result: Optional[dict] = None,
    attribution_result: Optional[dict] = None,
    brinson_result: Optional[dict] = None,
) -> str:
    """Serialize the full study result + optional enrichments into a
    structured human-readable text that can be passed to any LLM."""

    lines: list[str] = []
    add = lines.append

    meta = study_result.get("meta") or {}
    ccy  = meta.get("currency", "USD")

    # ── Header / identification ────────────────────────────────────────────
    add("=" * 66)
    add("  ANALYSE AMC — STRUCTURA")
    add("=" * 66)
    add(f"Produit      : {meta.get('product_name', '—')}")
    add(f"ISIN         : {meta.get('isin', '—')}")
    add(f"Devise       : {ccy}")
    add(f"Thème        : {meta.get('theme', '—')}")
    aum = meta.get("total_aum")
    outstanding = meta.get("outstanding")
    if aum:
        add(f"AUM          : {aum:,.0f} {ccy}  ({outstanding} certificats)")
    nav_snap = meta.get("nav_snapshot_value")
    if nav_snap:
        add(f"NAV actuelle : {nav_snap:.4f} {ccy}  (au {meta.get('nav_snapshot_date') or meta.get('as_of', '—')})")
    nav0 = meta.get("nav_start_value")
    if nav0:
        add(f"NAV initiale : {nav0:.4f} {ccy}  (au {meta.get('nav_start_date', '—')})")
    n_orders = meta.get("n_orders")
    n_und    = meta.get("n_underlyings")
    if n_orders is not None:
        add(f"Ordres       : {n_orders}  |  Sous-jacents actifs : {n_und}")
    fee = meta.get("management_fee_pct")
    add(f"Frais gestion: {fee}% p.a." if fee is not None else "Frais gestion: non renseigné")
    bench = meta.get("benchmark_ticker")
    ff    = meta.get("ff_series")
    if bench:
        add(f"Benchmark    : {bench}  |  Modèle FF : {ff}")
    audience = meta.get("audience", "committee")
    language = (study_result.get("output") or {}).get("language", "fr")
    add(f"Audience     : {audience}  |  Langue : {language}")
    add("")

    # ── Warnings ──────────────────────────────────────────────────────────
    warnings = study_result.get("warnings") or []
    if warnings:
        add("AVERTISSEMENTS")
        for w in warnings:
            add(f"  ⚠  {w}")
        add("")

    # ── Block A — Fama-French ─────────────────────────────────────────────
    add("=" * 66)
    add("BLOC A — ANALYSE FACTORIELLE (Fama-French)")
    add("=" * 66)
    ba = study_result.get("block_a") or {}
    if not ba.get("available"):
        add(f"  Non disponible : {ba.get('error', 'données insuffisantes')}")
    else:
        for scope in ("net", "gross"):
            reg = ((ba.get(scope) or {}).get("regression")) or {}
            if not reg:
                continue
            label = "NET (après frais)" if scope == "net" else "BRUT (avant frais)"
            add(f"\n  {label}")
            add(f"    Alpha annualisé  : {_pct(reg.get('alpha_ann_pct'))}")
            add(f"    Alpha t-stat     : {_fmt(reg.get('alpha_tstat'), 2)}")
            add(f"    R²               : {_pct((reg.get('r2') or 0) * 100)}")
            add(f"    N observations   : {reg.get('n_obs', '—')}")
            factors = reg.get("factors") or []
            if factors:
                add("    Expositions factorielles :")
                for f in factors:
                    add(
                        f"      {f.get('name','?'):10s}  "
                        f"beta={_fmt(f.get('beta'), 3)}  "
                        f"t={_fmt(f.get('tstat'), 2)}  "
                        f"p={_fmt(f.get('pvalue'), 3)}"
                    )
        bench_reg = (ba.get("net") or {}).get("benchmark_regression") or {}
        if bench_reg:
            add(f"\n  Régression vs benchmark ({bench_reg.get('ticker', '')})")
            add(f"    Alpha ann.   : {_pct(bench_reg.get('alpha_ann_pct'))}")
            add(f"    Alpha t-stat : {_fmt(bench_reg.get('alpha_tstat'), 2)}")
            add(f"    Beta marché  : {_fmt(bench_reg.get('beta'), 3)}")
            add(f"    R²           : {_pct((bench_reg.get('r2') or 0) * 100)}")
    add("")

    # ── Block B — Attribution ─────────────────────────────────────────────
    add("=" * 66)
    add("BLOC B — ATTRIBUTION PAR SOUS-JACENT")
    add("=" * 66)
    bb = study_result.get("block_b") or {}
    totals = bb.get("totals") or {}
    if totals:
        add(f"P&L réalisé total : {_money(totals.get('realized_pnl'), ccy)}")
        add(f"P&L latent total  : {_money(totals.get('unreal_pnl'), ccy)}")
        add(f"P&L total         : {_money(totals.get('total_pnl'), ccy)}")
        fx_pnl   = totals.get("realized_fx_pnl")
        fx_share = totals.get("fx_share_of_realized_pct")
        if fx_pnl is not None:
            add(f"Impact FX réalisé : {_money(fx_pnl, ccy)} ({_pct(fx_share)} du réalisé)")
        add("")

    quarterly = bb.get("quarterly_realized") or []
    if quarterly:
        add("P&L réalisé par trimestre :")
        for q in quarterly:
            add(f"  {q.get('quarter', '?')} : {_money(q.get('realized_pnl'), ccy)}")
        add("")

    top5 = bb.get("top5") or []
    if top5:
        add("TOP 5 contributeurs :")
        for i, p in enumerate(top5, 1):
            add(
                f"  {i}. {p.get('name','?')} ({p.get('ccy','?')}) — "
                f"poids {_pct((p.get('weight') or 0) * 100)} — "
                f"P&L total {_money(p.get('total_pnl'), ccy)}  "
                f"(réal. {_money(p.get('realized_pnl'), ccy)}, "
                f"latent {_money(p.get('unreal_pnl'), ccy)})  "
                f"{p.get('n_round_trips', '?')} RT"
            )
        add("")

    flop5 = bb.get("flop5") or []
    if flop5:
        add("FLOP 5 destructeurs :")
        for i, p in enumerate(flop5, 1):
            add(
                f"  {i}. {p.get('name','?')} ({p.get('ccy','?')}) — "
                f"poids {_pct((p.get('weight') or 0) * 100)} — "
                f"P&L total {_money(p.get('total_pnl'), ccy)}  "
                f"(réal. {_money(p.get('realized_pnl'), ccy)}, "
                f"latent {_money(p.get('unreal_pnl'), ccy)})  "
                f"{p.get('n_round_trips', '?')} RT"
            )
        add("")

    # Full per-name table
    per_name = bb.get("per_name") or []
    if per_name:
        add("Tableau complet par sous-jacent :")
        add(f"  {'Nom':35s} {'Poids':>8} {'P&L total':>15} {'Réal.':>15} {'Latent':>15} {'RT':>4}")
        add("  " + "-" * 82)
        for p in per_name:
            add(
                f"  {str(p.get('name','?'))[:35]:35s} "
                f"{_pct((p.get('weight') or 0) * 100):>8} "
                f"{_money(p.get('total_pnl'), ''):>15} "
                f"{_money(p.get('realized_pnl'), ''):>15} "
                f"{_money(p.get('unreal_pnl'), ''):>15} "
                f"{p.get('n_round_trips', 0):>4}"
            )
        add("")

    # ── Block C — Trading ─────────────────────────────────────────────────
    add("=" * 66)
    add("BLOC C — TRADING & TURNOVER")
    add("=" * 66)
    bc = study_result.get("block_c") or {}
    rt = bc.get("round_trips") or {}
    if rt:
        add(f"Round trips         : {rt.get('count', '—')}")
        add(f"Hit rate            : {_pct(rt.get('win_rate_pct'))}")
        add(f"Gain moyen / win    : {_money(rt.get('avg_win'), ccy)}")
        add(f"Perte moy. / loss   : {_money(rt.get('avg_loss'), ccy)}")
        add(f"Profit factor       : {_fmt(rt.get('profit_factor'), 2)}")
        add(f"Holding moyen       : {_fmt(rt.get('avg_holding_days'), 1)} jours (médiane {rt.get('median_holding_days', '—')}j)")
        add(f"P&L réalisé cumulé  : {_money(rt.get('realized_pnl'), ccy)}")
        add("")

    turnover = bc.get("turnover") or {}
    if turnover:
        add(f"Turnover annualisé  : {_fmt(turnover.get('turnover_annualized'), 2)}x")
        add(f"Volume brut traité  : {_money(turnover.get('gross_traded_prod'), ccy)}")
        add(f"Période analysée    : {turnover.get('period_days', '—')} jours")
        add("")

    timing = bc.get("timing") or []
    if timing:
        with_delta = [t for t in timing if t.get("sell_vs_buy_pct") is not None]
        sorted_t   = sorted(with_delta, key=lambda x: x["sell_vs_buy_pct"], reverse=True)
        best = [t for t in sorted_t if t["sell_vs_buy_pct"] > 0][:5]
        worst = [t for t in sorted_t if t["sell_vs_buy_pct"] < 0][-5:]
        if best:
            add("Meilleur timing (vente vs achat) :")
            for t in best:
                add(f"  {str(t.get('name', '?'))[:40]:40s}  {_pct(t.get('sell_vs_buy_pct'))}")
        if worst:
            add("Pire timing (vente vs achat) :")
            for t in worst:
                add(f"  {str(t.get('name', '?'))[:40]:40s}  {_pct(t.get('sell_vs_buy_pct'))}")
        add("")

    # ── Block D — Behaviour ───────────────────────────────────────────────
    add("=" * 66)
    add("BLOC D — COMPORTEMENT & CONVICTION")
    add("=" * 66)
    bd = study_result.get("block_d") or {}
    hdist = bd.get("holding_distribution") or {}
    if hdist:
        cutoff = hdist.get("long_term_days_cutoff", 180)
        add(f"Positions long-terme (>{cutoff}j)  : {hdist.get('long_term_count', '—')}")
        add(f"Positions tactiques (<{cutoff}j)   : {hdist.get('tactical_count', '—')}")
        add(f"Holding moyen                      : {_fmt(hdist.get('avg_holding_days'), 1)} jours")
        add(f"Positions fermées / ouvertes       : {hdist.get('closed_count', '—')} / {hdist.get('open_count', '—')}")
        add("")

    hygiene = bd.get("order_hygiene") or {}
    if hygiene:
        add(f"Ordres exécutés   : {hygiene.get('n_done', '—')}")
        add(f"Ordres annulés    : {hygiene.get('n_discarded', '—')} ({_pct(hygiene.get('discarded_ratio_pct'))})")
        add(f"Fills partiels    : {hygiene.get('n_partial_fills', '—')}")
        add("")

    cmatrix = bd.get("conviction_matrix") or {}
    counts  = cmatrix.get("counts") or {}
    pnl_q   = cmatrix.get("pnl") or {}
    labels  = cmatrix.get("labels") or {}
    if counts:
        add("Matrice conviction × résultat :")
        for q_key in ("conviction_winners", "stubborn_losers", "tactical_winners", "uncertainty"):
            n   = counts.get(q_key, 0)
            pnl = pnl_q.get(q_key, 0)
            lbl = labels.get(q_key, q_key)
            add(f"  {lbl:50s}  ({n} pos.) : {_money(pnl, ccy)}")
        add("")

        quads = cmatrix.get("quadrants") or {}
        for q_key in ("conviction_winners", "stubborn_losers", "tactical_winners", "uncertainty"):
            items = quads.get(q_key) or []
            if not items:
                continue
            lbl = labels.get(q_key, q_key)
            add(f"  Détail — {lbl} :")
            for item in items:
                name = item.get("name") or item.get("isin", "?")
                add(
                    f"    {str(name)[:35]:35s}  "
                    f"poids {_pct(item.get('weight_pct'))}  "
                    f"max {item.get('max_hold_days', '?')}j  "
                    f"P&L {_money(item.get('total_pnl'), ccy)}"
                )
            add("")

    reentry = bd.get("reentry") or {}
    multi   = reentry.get("names_multiple_round_trips") or []
    if multi:
        add("Re-entries multiples (>1 round trip sur le même titre) :")
        for r in multi:
            add(f"  {r.get('isin', '?')}  —  {r.get('round_trips', '?')} round trips")
        add("")

    # ── Bloc E — Référentiel Inertiel ─────────────────────────────────────
    add("=" * 66)
    add("BLOC E — RÉFÉRENTIEL INERTIEL (Buy & Hold passif depuis l'émission)")
    add("=" * 66)
    be = study_result.get("block_e") or {}
    if be.get("available"):
        source = be.get("source", "accounting_identity")
        n_certs = be.get("n_certs")
        aum_t0  = be.get("total_aum_t0")
        add(f"Source             : {'Term sheet' if source == 'termsheet' else 'Identité comptable (fallback)'}")
        if n_certs:
            add(f"Certificats émis   : {n_certs:,}")
        if aum_t0:
            add(f"AUM initial        : {aum_t0:,.0f} {study_result.get('meta', {}).get('currency', '')}")
        add(f"Performance B&H    : {_pct(be.get('bh_perf_pct'))}")
        add(f"NAV réelle         : {_pct(be.get('actual_perf_pct'))}")
        vag = be.get("value_added_pct")
        add(f"VAG (valeur ajoutée): {_pct(vag)}")
        if vag is not None:
            verdict = "Le gérant a créé de la valeur vs le portefeuille initial passif." if vag >= 0 \
                else "L'inertie depuis l'émission aurait été préférable à la gestion active."
            add(f"  → {verdict}")
        add(f"Nb. sous-jacents   : {be.get('n_positions', '—')}")
    else:
        add(f"  Non disponible : {be.get('error', 'Données insuffisantes')}")
    add("")

    # ── Block F — Replicability ───────────────────────────────────────────
    add("=" * 66)
    add("BLOC F — RÉPLICABILITÉ")
    add("=" * 66)
    bf = study_result.get("block_f") or {}
    if bf.get("available"):
        add(f"Score de réplicabilité : {bf.get('score', '—')}/100 — {bf.get('interpretation', '')}")
        perf_r = bf.get("replicant_perf_pct")
        perf_a = bf.get("amc_perf_pct")
        if perf_r is not None:
            add(f"Perf. réplicant factoriel : {_pct(perf_r)}  vs AMC réel : {_pct(perf_a)}")
    else:
        add(f"  Non disponible : {bf.get('error', 'Bloc A requis')}")
    add("")

    # ── Block G — Brinson ─────────────────────────────────────────────────
    add("=" * 66)
    add("BLOC G — ATTRIBUTION BRINSON-FACHLER")
    add("=" * 66)
    if brinson_result and brinson_result.get("available"):
        add(f"Retour actif total   : {_pct(brinson_result.get('active_return_pct'))}")
        add(f"  Effet Allocation   : {_pct(brinson_result.get('allocation_pct'))}")
        add(f"  Effet Sélection    : {_pct(brinson_result.get('selection_pct'))}")
        add(f"  Effet Interaction  : {_pct(brinson_result.get('interaction_pct'))}")
    elif attribution_result and not attribution_result.get("error"):
        add(f"Attribution timing    : {_pct(attribution_result.get('timing_pct'))}")
        add(f"Attribution sélection : {_pct(attribution_result.get('selection_pct'))}")
    else:
        reason = (
            (brinson_result or {}).get("error")
            or (attribution_result or {}).get("error")
            or "données non disponibles"
        )
        add(f"  Non disponible : {reason}")
    add("")

    # ── Block H — Timing Score ────────────────────────────────────────────
    add("=" * 66)
    add("BLOC H — TIMING SCORE (Qualité des Points d'Entrée et de Sortie)")
    add("=" * 66)
    bh = study_result.get("block_h") or {}
    if not bh.get("available"):
        reason = bh.get("error") or "prix des constituants non chargés"
        add(f"  Non disponible : {reason}")
    else:
        add(f"Score global    : {_fmt(bh.get('global_score_mean'), 3)}  (baseline aléatoire = 0.500)")
        add(f"Score entrées   : {_fmt(bh.get('entry_score_mean'), 3)}  (BUY — {bh.get('n_buy', '—')} trades)")
        add(f"Score sorties   : {_fmt(bh.get('exit_score_mean'), 3)}  (SELL — {bh.get('n_sell', '—')} trades)")
        add(f"t-stat global   : {_fmt(bh.get('tstat_global'), 3)}  (vs µ₀=0.5)  p={_fmt(bh.get('pvalue_global'), 4)}")
        add(f"Couverture      : {_fmt(bh.get('coverage_pct'), 1)}%  ({bh.get('n_trades_analyzed', '—')} / {bh.get('n_trades_total', '—')} ordres)")
        warn = bh.get("warning")
        if warn:
            add(f"⚠  {warn}")
        add("")
        interp = bh.get("interpretation")
        if interp:
            add(f"Interprétation : {interp}")
        add("")
        near_lows = bh.get("near_lows_buys") or []
        if near_lows:
            add(f"Achats proches des plus bas ({len(near_lows)}) :")
            for t in near_lows[:5]:
                add(f"  {t.get('date','')} {t.get('name','')} — score {_fmt(t.get('score'), 3)}")
        near_highs_b = bh.get("near_highs_buys") or []
        if near_highs_b:
            add(f"Achats proches des plus hauts ({len(near_highs_b)}) :")
            for t in near_highs_b[:5]:
                add(f"  {t.get('date','')} {t.get('name','')} — score {_fmt(t.get('score'), 3)}")
        good_exits = bh.get("near_highs_sells") or []
        if good_exits:
            add(f"Ventes bien timées ({len(good_exits)}) :")
            for t in good_exits[:5]:
                add(f"  {t.get('date','')} {t.get('name','')} — score {_fmt(t.get('score'), 3)}")
        early_sells = bh.get("early_sells") or []
        if early_sells:
            add(f"Ventes prématurées ({len(early_sells)}) :")
            for t in early_sells[:5]:
                add(f"  {t.get('date','')} {t.get('name','')} — score {_fmt(t.get('score'), 3)}")
    add("")

    # ── Block I — Stock Picking Score ────────────────────────────────────
    add("=" * 66)
    add("BLOC I — STOCK PICKING SCORE (Qualité de Sélection de Titres)")
    add("=" * 66)
    bi = study_result.get("block_i") or {}
    if not bi.get("available"):
        reason = bi.get("error") or "prix des constituants non chargés"
        add(f"  Non disponible : {reason}")
    else:
        add(f"Score de stock picking : {bi.get('score', '—')}/100 — {bi.get('score_label', '')}")
        add(f"Alpha moyen global     : {_pct(bi.get('global_alpha_mean', 0) * 100)}")
        add(f"Taux de succès global  : {_pct((bi.get('global_success_rate') or 0) * 100)}")
        add(f"Information Ratio      : {_fmt(bi.get('information_ratio'), 3)}")
        add(f"t-stat (vs µ₀=0)       : {_fmt(bi.get('tstat_alpha'), 3)}  p={_fmt(bi.get('pvalue_alpha'), 4)}")
        add(f"Couverture             : {_fmt(bi.get('coverage_pct'), 1)}%  ({bi.get('n_buys_analyzed', '—')} / {bi.get('n_buys_total', '—')} achats)")
        bench_ok = bi.get("benchmark_available")
        add(f"Benchmark utilisé      : {bi.get('benchmark_ticker', '—')}  ({'disponible' if bench_ok else 'indisponible — retour brut utilisé'})")
        warn = bi.get("warning")
        if warn:
            add(f"⚠  {warn}")
        add("")
        add("Alpha par horizon (moyenne / taux de succès) :")
        for h in ("1M", "3M", "6M", "12M"):
            hstats = (bi.get("stats_by_horizon") or {}).get(h, {})
            if hstats.get("available"):
                add(
                    f"  {h:4s}  alpha moy {_pct(hstats.get('alpha_mean', 0) * 100)}"
                    f"  médiane {_pct(hstats.get('alpha_median', 0) * 100)}"
                    f"  succès {_pct((hstats.get('success_rate') or 0) * 100)}"
                    f"  n={hstats.get('n', '—')}"
                )
            else:
                add(f"  {h:4s}  données insuffisantes")
        add("")
        best = bi.get("best_ideas") or []
        if best:
            add("Meilleures idées (alpha pondéré décroissant) :")
            for i, t in enumerate(best, 1):
                add(
                    f"  {i}. {str(t.get('name', '?'))[:35]:35s}"
                    f"  alpha {_pct((t.get('alpha_weighted') or 0) * 100)}"
                    f"  ({t.get('date', '—')})"
                )
        worst = bi.get("worst_ideas") or []
        if worst:
            add("Pires idées :")
            for i, t in enumerate(worst, 1):
                add(
                    f"  {i}. {str(t.get('name', '?'))[:35]:35s}"
                    f"  alpha {_pct((t.get('alpha_weighted') or 0) * 100)}"
                    f"  ({t.get('date', '—')})"
                )
        add("")
        interp = bi.get("interpretation")
        if interp:
            add(f"Interprétation : {interp}")
    add("")

    # ── Block J — Risk Management Score ─────────────────────────────────
    add("=" * 66)
    add("BLOC J — RISK MANAGEMENT SCORE")
    add("=" * 66)
    bj = study_result.get("block_j") or {}
    if not bj.get("available"):
        reason = bj.get("error") or "données insuffisantes"
        add(f"  Non disponible : {reason}")
    else:
        add(f"Score global    : {bj.get('score', '—')}/100 — {bj.get('score_label', '')}")
        add(f"Score brut      : {bj.get('score_raw', '—')}/100 (avant plafonnement)")
        add(f"Plafond fiabilité : {bj.get('reliability_cap', '—')}/100  ({bj.get('n_obs', '—')} obs)")
        bench_ok = bj.get("benchmark_available")
        add(f"Benchmark       : {bj.get('benchmark_ticker', '—')}  ({'disponible' if bench_ok else 'indisponible'})")
        warn = bj.get("warning")
        if warn:
            add(f"⚠  {warn}")
        add("")
        sub = bj.get("sub_scores") or {}
        weights = bj.get("weights") or {}
        for key, label in [
            ("risk_adjusted", "Perf. ajustée du risque"),
            ("drawdown",      "Gestion drawdown"),
            ("downside_risk", "Risque baissier"),
            ("concentration", "Concentration"),
            ("factor_risk",   "Risque factoriel"),
        ]:
            s = sub.get(key) or {}
            w_pct = round((weights.get(key) or 0) * 100)
            add(f"  [{w_pct:2d}%] {label:30s}  score={s.get('score', '—')}/100")
        add("")
        ra = sub.get("risk_adjusted") or {}
        if ra:
            add(f"  Sharpe         : {_fmt(ra.get('sharpe_ratio'), 3)}")
            add(f"  Calmar         : {_fmt(ra.get('calmar_ratio'), 3)}")
            add(f"  Sortino        : {_fmt(ra.get('sortino_ratio'), 3)}")
            ir = ra.get("information_ratio")
            if ir is not None:
                add(f"  Info Ratio     : {_fmt(ir, 3)}")
            te = ra.get("tracking_error_pct")
            if te is not None:
                add(f"  Tracking Error : {_pct(te)}")
            up = ra.get("upside_capture_pct")
            dn = ra.get("downside_capture_pct")
            if up is not None:
                add(f"  Capture Up/Down: {up:.0f}% / {dn:.0f}%")
        dd = sub.get("drawdown") or {}
        if dd:
            add(f"  Max Drawdown   : {_pct(dd.get('max_drawdown_pct'))}")
            add(f"  Ulcer Index    : {_pct(dd.get('ulcer_index_pct'))}")
            add(f"  N épisodes DD  : {dd.get('n_drawdown_episodes', '—')}  "
                f"(durée moy. {dd.get('avg_episode_duration_days', '—')}j)")
        dr = sub.get("downside_risk") or {}
        if dr:
            add(f"  Semi-écart ann.: {_pct(dr.get('semi_deviation_ann_pct'))}")
            add(f"  VaR 95%        : {_pct(dr.get('var_95_pct'))}")
            add(f"  ES 95%         : {_pct(dr.get('es_95_pct'))}")
            add(f"  Pire jour      : {_pct(dr.get('worst_day_pct'))}")
        conc = sub.get("concentration") or {}
        if conc:
            add(f"  Titres actifs  : {conc.get('n_holdings', '—')}")
            add(f"  Poids max      : {_pct(conc.get('max_weight_pct'))}")
            add(f"  Top-5 poids    : {_pct(conc.get('top5_weight_pct'))}")
            add(f"  HHI            : {_fmt(conc.get('hhi'), 4)}")
            add(f"  N effectif     : {_fmt(conc.get('effective_n'), 1)}")
        add("")
        interp = bj.get("interpretation")
        if interp:
            add(f"Interprétation : {interp}")
    add("")

    # ── Manager Skill Score ───────────────────────────────────────────────
    add("=" * 66)
    add("MANAGER SKILL SCORE — ÉVALUATION GLOBALE DU GÉRANT")
    add("=" * 66)
    mss = study_result.get("manager_skill_score") or {}
    if not mss.get("available"):
        reason = mss.get("error") or "blocs insuffisants"
        add(f"  Non disponible : {reason}")
    else:
        add(f"Score global    : {mss.get('score', '—')}/100 — {mss.get('score_label', '')}")
        add(f"Blocs actifs    : {mss.get('n_dimensions_available', '—')} / 6")
        add("")
        add(f"  {'Dimension':35s} {'Poids eff.':>10} {'Score':>8} {'Contrib.':>10}")
        add("  " + "-" * 65)
        for d in (mss.get("dimensions") or []):
            if d.get("available"):
                add(
                    f"  {d['label']:35s} "
                    f"{d['weight_effective_pct']:>9.1f}% "
                    f"{d['score'] or 0:>8.1f} "
                    f"{d['weighted_contribution'] or 0:>10.1f}"
                )
            else:
                add(f"  {d['label']:35s}  — non disponible")
        add("")
        interp = mss.get("interpretation")
        if interp:
            add(f"Interprétation : {interp}")
    add("")

    # ── Confidence ────────────────────────────────────────────────────────
    add("=" * 66)
    add("CONFIANCE DE L'ANALYSE")
    add("=" * 66)
    conf = study_result.get("confidence") or {}
    add(f"Score global : {conf.get('overall_pct', '—')}%")
    add("")
    for row in (conf.get("rows") or []):
        status = "OK " if row.get("feasible") else "N/A"
        add(
            f"  [{status}] {row.get('dimension', '?'):52s}  "
            f"{row.get('confidence_pct', 0):5.0f}%"
        )
        if not row.get("feasible") and row.get("missing_data"):
            add(f"         Manquant : {row.get('missing_data')}")
    add("")

    narrative = conf.get("narrative")
    if narrative:
        add(f"Note : {narrative}")
        add("")

    roadmap = conf.get("roadmap") or []
    if roadmap:
        add("Feuille de route :")
        for r in roadmap:
            add(f"  • {r.get('item', '')}  →  {r.get('unlocks', '')}")
    add("")

    add("=" * 66)
    add(f"Audience cible : {audience}  |  Langue de rédaction : {language}")
    add("=" * 66)

    return "\n".join(lines)


# ── LLM callers ────────────────────────────────────────────────────────────

def call_ollama(
    payload: str,
    system_prompt: str,
    url: str,
    model: str,
    timeout: int = 180,
) -> str:
    endpoint = url.rstrip("/") + "/api/chat"
    body = {
        "model": model,
        "stream": False,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": payload},
        ],
    }
    resp = httpx.post(endpoint, json=body, timeout=timeout)
    resp.raise_for_status()
    return resp.json()["message"]["content"]


def list_ollama_models(url: str, timeout: int = 10) -> list[str]:
    endpoint = url.rstrip("/") + "/api/tags"
    resp = httpx.get(endpoint, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    return [m["name"] for m in (data.get("models") or [])]


def call_claude(
    payload: str,
    system_prompt: str,
    api_key: str,
    model: str = "claude-sonnet-4-6",
    timeout: int = 180,
) -> str:
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    body = {
        "model": model,
        "max_tokens": 3000,
        "system": system_prompt,
        "messages": [{"role": "user", "content": payload}],
    }
    resp = httpx.post(
        "https://api.anthropic.com/v1/messages",
        json=body,
        headers=headers,
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.json()["content"][0]["text"]


def call_openai(
    payload: str,
    system_prompt: str,
    api_key: str,
    model: str = "gpt-4o",
    timeout: int = 180,
) -> str:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    body = {
        "model": model,
        "max_tokens": 3000,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": payload},
        ],
    }
    resp = httpx.post(
        "https://api.openai.com/v1/chat/completions",
        json=body,
        headers=headers,
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]
