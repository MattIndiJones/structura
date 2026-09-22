"""Frozen valuation evidence, ordered attribution and editable note rendering."""
from copy import deepcopy
import json
import math

from .valuation_runs import engine_identity
from .compute.pricers.var_scenario import price_var_scenario_job, residual_script_from_payload
from .deal_valuation import _get_events
from .valuation_note_support import events_for_note, monitor_levels, residual_greeks

SECTIONS = ("synthese", "analyse", "contexte", "conclusion")
LABELS = dict(zip(SECTIONS, ("Synthèse", "Analyse", "Contexte et limites", "Conclusion")))


def note_snapshot(session, deal, ctx, mtm):
    events, _ = events_for_note(_get_events(deal.id, session), deal.schedule_json)
    for event in events:
        if event["date"] > mtm["valuation_date"]:
            event["status"] = "futur"
    start = ctx.get("start_idx", 0)
    prices = ctx.get("prices") or {}
    series = {}
    for u in ctx.get("underlyings_json") or []:
        base = (ctx.get("s0_map") or {}).get(u["name"])
        values = prices.get(u["ticker"], [])
        if base:
            series[u["name"]] = [float(v) / base if v is not None and math.isfinite(v) else None
                                  for v in values[start:]]
    return {
        "deal": {k: getattr(deal, k, None) for k in (
            "reference", "product_type", "sens", "contrepartie", "nominal", "devise",
            "price_traded", "trade_date", "strike_date", "value_date", "maturity_date")},
        "underlyings": [{"name": u["name"], "ticker": u.get("ticker"), "spot_pct": s}
                        for u, s in zip(ctx.get("underlyings_json") or [], ctx.get("norm_spots") or [])],
        "events": events,
        "next_obs_date": min((e["date"] for e in events if e["date"] > mtm["valuation_date"]), default=None),
        "monitors": monitor_levels(ctx["compiled"], ctx["user_params"], ctx["state"]["index"]),
        "history": {"dates": ctx.get("dates", [])[start:], "series": series},
    }


def saved_evidence(run, deal):
    result = json.loads(run.result_json)
    mtm = result["mtm"] if isinstance(result.get("mtm"), dict) else result
    if not isinstance(mtm.get("mtm"), (int, float)) or not math.isfinite(mtm["mtm"]):
        raise ValueError("Ce calcul ne contient pas de valorisation exploitable.")
    diagnostics = json.loads(run.diagnostics_json or "{}")
    data = deepcopy(diagnostics.get("note_snapshot"))
    warnings = []
    if not data:
        # Never reconstruct old historical observations from today's market data.
        market = json.loads(run.market_data_json or "{}")
        data = {
            "deal": {k: getattr(deal, k, None) for k in (
                "reference", "product_type", "sens", "contrepartie", "nominal", "devise",
                "price_traded", "trade_date", "strike_date", "value_date", "maturity_date")},
            "underlyings": [{"name": u.get("name"), "ticker": u.get("ticker"),
                             "spot_pct": u.get("normalized_spot", 1)}
                            for u in market.get("observations", [])],
            "events": [], "monitors": [], "history": {"dates": [], "series": {}},
        }
        warnings.append("Ancien calcul : identité issue de la fiche actuelle ; calendrier, barrières et graphique historiques non archivés dans ce calcul.")
    data.update(mtm=mtm, valuation_run_id=run.id, greeks=result.get("greeks"))
    if run.contract_version != deal.contract_version:
        warnings.append("La version contractuelle de ce calcul diffère de la version actuelle du deal.")
    return {"run_id": run.id, "created_at": run.created_at.isoformat() + "Z",
            "contract_version": run.contract_version, "context_hash": run.context_hash,
            "engine_fingerprint": run.engine_fingerprint, "data": data, "warnings": warnings}


def frozen_greeks(run, evidence, progress):
    """Reuse the existing Greek engine and display units on the frozen context."""
    if evidence["data"].get("greeks"):
        return
    p = json.loads(run.context_json)
    c = p.get("valuation_context")
    if not c or run.engine_fingerprint != engine_identity()[1] or p.get("settlement_claim"):
        evidence["warnings"].append("Sensibilités non disponibles avec le moteur archivé ; aucune sensibilité actuelle n'est substituée.")
        return
    progress("Calcul des sensibilités sur les paramètres archivés")
    if abs(price_var_scenario_job(p)["price"] - evidence["data"]["mtm"]["mtm"]) > 1e-10:
        evidence["warnings"].append("Sensibilités omises : le calcul de référence ne se reproduit pas à la précision attendue.")
        return
    ctx = dict(residual_script=residual_script_from_payload(p), engine_uls=c["underlyings"],
               corr=p["corr"], r_frac=c["r"], T_remaining=c["T"], N_used=c["N"],
               model_used=c["model"], seed=c["seed"], user_params=c["user_params"],
               sigma_r=c["sigma_r"], a_r=c["a_r"], yc=c["yield_curve"],
               funding_curve=c["funding_curve"], funding_spread=c["funding_spread"],
               barrier_monitoring=c["barrier_monitoring"], antithetic=c["antithetic"],
               state=p["state"], norm_spots=p["norm_spots"], strike_set_t=c["strike_set_t"],
               residual_payment_t=c["maturity_payment_t"], underlyings_json=c["underlyings"])
    evidence["data"]["greeks"] = residual_greeks(ctx, c["N"])


def compare_runs(first, second, progress=lambda phase: None):
    """Sequential frozen revaluations, no provider calls or inferred market inputs.

    Time and realized path state move together: decoupling a crossed coupon or
    fixing window from its calendar would create a financially invalid state.
    Contributions depend on ordering; unexplained changes remain a residual.
    """
    a, b = json.loads(first.context_json), json.loads(second.context_json)
    def mtm(run):
        r = json.loads(run.result_json)
        return r["mtm"] if isinstance(r.get("mtm"), dict) else r
    m1, m2 = mtm(first), mtm(second)
    delta = (m2["mtm"] - m1["mtm"]) * 100
    res = dict(date1=m1.get("valuation_date"), date2=m2.get("valuation_date"),
               mtm1=m1["mtm"], mtm2=m2["mtm"], delta_pts=delta, steps=[],
               residual_pts=delta, available=False, warnings=[],
               methodology="Réévaluations successives sur les entrées archivées, à graine et nombre de trajectoires identiques. Ordre : temps et état réalisé, spots, dividendes, diffusion et change, corrélations, taux, financement, flux à recevoir. L'attribution dépend de cet ordre ; le résidu reste non attribué. La variation du MtM exclut les flux déjà payés et ne constitue pas un P&L total.")
    ca, cb = a.get("valuation_context", {}), b.get("valuation_context", {})
    reason = None
    if first.contract_version != second.contract_version:
        reason = "Versions contractuelles différentes."
    elif first.engine_fingerprint != second.engine_fingerprint or first.engine_fingerprint != engine_identity()[1]:
        reason = "Moteur différent entre les calculs ou depuis leur enregistrement."
    elif not ca or not cb or a.get("settlement_claim") or b.get("settlement_claim"):
        reason = "Contexte résiduel complet indisponible ou produit déjà dénoué."
    elif any(a.get(k) != b.get(k) for k in ("script_text", "constat_values", "value_date", "strike_date", "settlement_ccy")):
        reason = "Termes contractuels ou conventions différents."
    elif any(ca.get(k) != cb.get(k) for k in ("model", "N", "seed", "antithetic", "barrier_monitoring", "user_params", "schema_version")):
        reason = "Modèle, paramètres du payoff ou réglages numériques différents."
    elif [(u.get("name"), u.get("ticker")) for u in ca["underlyings"]] != [(u.get("name"), u.get("ticker")) for u in cb["underlyings"]]:
        reason = "Univers ou ordre des sous-jacents différent."
    if reason:
        res["warnings"].append(reason + " Écart observé uniquement, sans attribution causale.")
        return res
    progress("Vérification des deux calculs archivés")
    start = float(price_var_scenario_job(a)["price"])
    end = float(price_var_scenario_job(b)["price"])
    if abs(start - m1["mtm"]) > 1e-10 or abs(end - m2["mtm"]) > 1e-10:
        res["warnings"].append("Les calculs archivés ne se reproduisent pas à la précision attendue ; attribution désactivée.")
        return res
    current = deepcopy(a)
    previous = start
    def step(label, top=(), nested=(), underlying=None):
        nonlocal previous
        before = deepcopy(current)
        for k in top:
            current[k] = deepcopy(b.get(k))
        for k in nested:
            current["valuation_context"][k] = deepcopy(cb.get(k))
        if underlying:
            for old, new in zip(current["valuation_context"]["underlyings"], cb["underlyings"]):
                if underlying == "dividend":
                    for k in ("q", "dividend_curve", "dividend_decay"):
                        if k in new:
                            old[k] = deepcopy(new[k])
                        else:
                            old.pop(k, None)
                else:
                    old.clear()
                    old.update(deepcopy(new))
        progress("Attribution : " + label)
        value = previous if current == before else float(price_var_scenario_job(current)["price"])
        if not math.isfinite(value):
            raise ValueError("Une réévaluation intermédiaire n'est pas finie.")
        res["steps"].append({"label": label, "delta_pts": (value - previous) * 100})
        previous = value
    step("Temps et état réalisé", ("T_elapsed", "passe_jusqu_a", "state"),
         ("T", "maturity_payment_t", "value_date_t", "strike_set_t", "state"))
    step("Spots", ("norm_spots",))
    step("Dividendes", underlying="dividend")
    step("Diffusion et change", underlying="remaining")
    step("Corrélations", ("corr",), ("corr_matrix",))
    step("Taux", nested=("r", "yield_curve", "sigma_r", "a_r"))
    step("Financement", nested=("funding_curve", "funding_spread"))
    step("Flux à recevoir (PV)", ("unsettled_pv",))
    res.update(available=True, residual_pts=(m2["mtm"] - previous) * 100)
    return res


def build_note(deal, runs, progress=lambda phase: None):
    evidence = {"runs": [saved_evidence(r, deal) for r in runs]}
    frozen_greeks(runs[-1], evidence["runs"][-1], progress)
    last = evidence["runs"][-1]["data"]
    m = last["mtm"]
    draft = dict.fromkeys(SECTIONS, "")
    draft["synthese"] = f"Valorisation au {m.get('valuation_date', '—')} : {m['mtm'] * 100:.2f}% du nominal."
    warnings = [w for r in evidence["runs"] for w in r["warnings"]]
    if len(runs) == 2:
        comparison = compare_runs(*runs, progress=progress)
        evidence["comparison"] = comparison
        draft["synthese"] = (f"Entre les calculs VR-{runs[0].id} et VR-{runs[1].id}, la valorisation passe de "
            f"{comparison['mtm1'] * 100:.2f}% à {comparison['mtm2'] * 100:.2f}% du nominal, "
            f"soit {comparison['delta_pts']:+.2f} points.")
        draft["analyse"] = "\n".join(f"{s['label']} : {s['delta_pts']:+.2f} points."
                                        for s in comparison["steps"])
        warnings += comparison["warnings"]
        draft["contexte"] = comparison["methodology"]
    else:
        from .deal_valuation_pdf import build_explanation
        if last["underlyings"]:
            draft["analyse"] = "\n".join(build_explanation(last))
    draft["contexte"] += ("\n" if draft["contexte"] else "") + "\n".join(dict.fromkeys(warnings))
    evidence["warnings"] = list(dict.fromkeys(warnings))
    return evidence, draft


def render_note(evidence, draft, title):
    from .deal_valuation_pdf import generate_valuation_pdf, generate_frozen_comparison_pdf
    data = deepcopy(evidence["runs"][-1]["data"])
    data["editorial"] = draft
    data["note_title"] = title
    data["note_warnings"] = evidence["warnings"]
    if "comparison" in evidence:
        data["comparison"] = evidence["comparison"]
        data["run_ids"] = [r["run_id"] for r in evidence["runs"]]
        return generate_frozen_comparison_pdf(data)
    return generate_valuation_pdf(data)
