"""CCR orchestration: existing valuations, legal data, shared paths and audit."""
from copy import deepcopy
from datetime import date, datetime
import hashlib
import json
from pathlib import Path

import numpy as np
from fastapi import HTTPException
from sqlmodel import select
from sqlalchemy import or_, and_, update

from ...db.models import (Counterparty, Deal, DealEvent, DealPortfolioMembership, Portfolio, User, ValuationRun,
                          CCRExposureCalculation)
from ...db.ccr_models import RECORDS
from ..audit import record_audit_event
from ..valuation_context import ValuationContext, canonical_json, canonical_fingerprint, run_valuation
from ..valuation_runs import engine_identity
from ..compute.pricers.var_scenario import residual_script_from_payload
from ..payscript.parser import parse_script, resolve_analysis_constats, analysis_origin, effective_T_max
from ..payscript.engine import run_mark_to_future, _simulate_mtf_outer, _mtf_reject_unsupported
from ..schemas import PricingRequest, validate_correlation_matrix
from ..var_engine import MarketScenario, apply_scenario_to_deal_base
from .contracts import SCHEMAS, CalculationRequest, CreditProfile, CreditLimit, CSAAgreement
from .exposure import VERSION, METRICS, eligible_set, collateral_profile, summarize, limit_check, decision


def organization(user):
    if user.entity_id is None:
        raise HTTPException(409, "Une organisation est requise pour le CCR")
    return user.entity_id


def row_payload(row):
    return {"id": row.id, "version": row.version, "counterparty_id": row.counterparty_id,
            "updated_at": row.updated_at.isoformat(), "updated_by": row.updated_by,
            "data": json.loads(row.payload_json)}


def records(session, user, cpty_id):
    if not session.get(Counterparty, cpty_id):
        raise HTTPException(404, "Contrepartie introuvable")
    return {kind: [row_payload(row) for row in session.exec(select(model).where(
        model.entity_id == organization(user), model.counterparty_id == cpty_id)).all()]
        for kind, model in RECORDS.items()}


def save_record(session, user, cpty_id, kind, data, row_id=None, expected_version=None):
    if user.role != "admin":
        raise HTTPException(403, "Administration du risque réservée aux administrateurs")
    if kind not in SCHEMAS:
        raise HTTPException(404, "Type de paramétrage CCR inconnu")
    model = RECORDS[kind]
    session.exec(update(model).where(model.entity_id == organization(user), model.counterparty_id == cpty_id)
                 .values(version=model.version))
    config = records(session, user, cpty_id)
    parsed = SCHEMAS[kind].model_validate(data)
    payload = parsed.model_dump(mode="json")
    # CSA and netting-set records also carry a human-readable `csa_id` /
    # `netting_set_id`. These are business references, not foreign keys.
    foreign_keys = {"csas": (("master_agreement_id", "agreements"),),
                    "netting-sets": (("master_agreement_id", "agreements"), ("csa_id", "csas")),
                    "collateral": (("netting_set_id", "netting-sets"),),
                    "overrides": (("limit_id", "limits"),)}
    for field, target in foreign_keys.get(kind, ()):
        if payload.get(field) is not None and not any(x["id"] == payload[field] for x in config[target]):
            raise HTTPException(422, f"{field} : rattachement hors de la contrepartie ou de l'organisation")
    if kind == "netting-sets" and payload.get("csa_id"):
        csa = next(x["data"] for x in config["csas"] if x["id"] == payload["csa_id"])
        if csa["master_agreement_id"] != payload["master_agreement_id"] or csa["base_currency"] != payload["currency"]:
            raise HTTPException(422, "Le CSA doit porter le même accord et la même devise que le set")
    if kind == "csas":
        for row in config["netting-sets"]:
            ns = row["data"]
            if ns.get("csa_id") == row_id and (ns["master_agreement_id"] != payload["master_agreement_id"] or ns["currency"] != payload["base_currency"]):
                raise HTTPException(422, "Un netting set utilise ce CSA : accord/devise incompatibles")
        if payload["im_model"] != "FIXED":
            raise HTTPException(422, "Seul le modèle IM fixe est disponible")
    if kind == "profiles" and config[kind] and row_id is None:
        raise HTTPException(409, "Un profil de crédit existe déjà : modifier sa version")
    if kind == "overrides":
        # Reserve the data model; no fake approval endpoint bypassing four eyes.
        if payload["status"] != "REQUESTED" or payload["approved_by"] is not None:
            raise HTTPException(422, "Le circuit d'approbation des dérogations n'est pas activé")
        payload["requested_by"] = user.id
    model = RECORDS[kind]
    before = None
    if row_id is not None:
        row = session.get(model, row_id)
        if not row or row.entity_id != organization(user) or row.counterparty_id != cpty_id:
            raise HTTPException(404, "Paramétrage introuvable")
        session.refresh(row)
        if expected_version != row.version:
            raise HTTPException(409, "Version modifiée par un autre utilisateur : recharger")
        before = row_payload(row)
        row.version += 1
    else:
        row = model(entity_id=organization(user), counterparty_id=cpty_id, updated_by=user.id)
    row.payload_json = canonical_json(payload)
    row.updated_at = datetime.utcnow()
    row.updated_by = user.id
    session.add(row)
    session.flush()
    record_audit_event(session, action="CCR_CONFIGURATION_CHANGED", object_type=f"CCR_{kind}",
                       object_id=row.id, actor_user_id=user.id, result="SUCCESS", before=before, after=row_payload(row))
    session.commit()
    return row_payload(row)


def legal_assignment(session, user, cpty_id, set_id, currency, product_type):
    if set_id is None:
        return None
    if cpty_id is None:
        raise HTTPException(422, "Un set juridique nécessite une contrepartie identifiée")
    config = records(session, user, cpty_id)
    ns = next((r for r in config["netting-sets"] if r["id"] == set_id), None)
    if not ns or not ns["data"]["active"] or ns["data"]["currency"] != currency:
        raise HTTPException(422, "Netting set inactif ou incompatible avec la contrepartie/devise")
    if product_type not in ns["data"]["product_scope"]:
        raise HTTPException(422, "Produit absent du périmètre juridique du netting set")
    return ns


def portfolio_deals(session, user, request):
    query = select(Deal).where(Deal.entity_id == organization(user))
    query = query.where(Deal.uat_batch_id != None if request.data_scope == "UAT" else Deal.uat_batch_id == None)
    if request.uat_batch_id is not None:
        query = query.where(Deal.uat_batch_id == request.uat_batch_id)
    if request.counterparty_id is not None:
        cpty = session.get(Counterparty, request.counterparty_id)
        if not cpty:
            raise HTTPException(404, "Contrepartie introuvable")
        query = query.where(or_(Deal.counterparty_id == cpty.id,
            and_(Deal.counterparty_id == None, Deal.contrepartie == cpty.name)))
    if request.deal_id is not None:
        query = query.where(Deal.id == request.deal_id)
    if request.netting_set_id is not None:
        query = query.where(Deal.ccr_netting_set_id == request.netting_set_id)
    if request.portfolio_id is not None:
        portfolio = session.get(Portfolio, request.portfolio_id)
        owner = session.get(User, portfolio.user_id) if portfolio else None
        if not portfolio or not owner or owner.entity_id != organization(user):
            raise HTTPException(404, "Portefeuille introuvable")
        members = session.exec(select(DealPortfolioMembership.deal_id).where(
            DealPortfolioMembership.portfolio_id == request.portfolio_id)).all()
        query = query.where(Deal.id.in_(members))
    if request.counterparty_id is None and request.deal_id is None:
        return []
    deals = session.exec(query.order_by(Deal.id)).all()
    if request.deal_id and not deals:
        raise HTTPException(404, "Deal introuvable dans le périmètre demandé")
    # Historical scope follows the actual terminal event, not the original
    # contractual maturity/payment date (which can remain after an early call).
    # Keep unsettled claims and trades whose resolution occurred after as-of.
    selected = []
    as_of = str(request.as_of_date)
    for deal in deals:
        if deal.trade_date and deal.trade_date > as_of:
            continue
        if deal.status in {"actif", "en_reglement"}:
            selected.append(deal)
            continue
        if request.as_of_date >= date.today():
            continue
        terminal = session.exec(select(DealEvent.event_date).where(
            DealEvent.deal_id == deal.id,
            DealEvent.status.in_(["callé", "ki", "final"]),
            DealEvent.event_date != "").order_by(DealEvent.event_date)).first()
        if terminal and terminal <= as_of and not (
                deal.settlement_amount is not None and deal.payment_date and as_of < deal.payment_date):
            continue
        selected.append(deal)
    return selected


def archived_trade(session, deal, request):
    trade = {"key": str(deal.id), "deal_id": deal.id, "reference": deal.reference,
             "product_type": deal.product_type, "currency": deal.devise, "nominal": deal.nominal,
             "sens": deal.sens, "netting_set_id": deal.ccr_netting_set_id,
             "uat_batch_id": deal.uat_batch_id,
             "counterparty_id": deal.counterparty_id, "contract_version": deal.contract_version}
    if deal.counterparty_id is None and request.counterparty_id:
        return {**trade, "missing": "Contrepartie historique sans identifiant juridique : rattachement à régulariser"}
    runs = session.exec(select(ValuationRun).where(ValuationRun.deal_id == deal.id,
        ValuationRun.contract_version == deal.contract_version).order_by(ValuationRun.id.desc())).all()
    for run in runs:
        result = json.loads(run.result_json)
        result = result["mtm"] if isinstance(result.get("mtm"), dict) else result
        if result.get("valuation_date") != str(request.as_of_date):
            continue
        replay = json.loads(run.context_json)
        if result.get("mtm") is None:
            continue
        return {**trade, "mtm_fraction": result["mtm"], "replay": replay,
                "valuation_run_id": run.id, "market_data_version": run.context_hash,
                "unsettled_flows": result.get("unsettled_cash_flows", []),
                "payment_date": result.get("payment_date") or deal.payment_date,
                "settlement_amount": result.get("settlement_amount", deal.settlement_amount),
                "settlement_valuation_market": result.get("market_used", {}),
                "settlement_market": json.loads(deal.market_snapshot_json or "{}")}
    # The booking price is never substituted for an as-of market value.
    return {**trade, "missing": "MtM absent à cette date : préparation automatique disponible dans le calcul CCR"}


def proposed_trade(request):
    p = request.proposed
    return {"key": "proposed", "reference": "PROPOSED", "deal_id": None,
            "product_type": p.product_type, "currency": p.currency, "nominal": p.nominal,
            "sens": p.sens, "netting_set_id": p.netting_set_id, "pricing": p.pricing.model_dump(mode="json")}


def scope_diagnostic(session, user, request):
    """Read-only eligibility inventory; never refresh prices or substitute dates."""
    selected = portfolio_deals(session, user, request)
    other = request.model_copy(update={"data_scope": "PRODUCTION" if request.data_scope == "UAT" else "UAT",
                                       "uat_batch_id": None, "deal_id": None})
    excluded = portfolio_deals(session, user, other)
    if request.deal_id is not None:
        excluded = [d for d in excluded if d.id == request.deal_id]
    rows, common = [], None
    for deal in selected:
        dates = set()
        for run in session.exec(select(ValuationRun).where(ValuationRun.deal_id == deal.id,
                ValuationRun.contract_version == deal.contract_version)).all():
            result = json.loads(run.result_json)
            result = result["mtm"] if isinstance(result.get("mtm"), dict) else result
            if result.get("valuation_date") and result.get("mtm") is not None:
                dates.add(result["valuation_date"])
        common = dates if common is None else common & dates
        trade = archived_trade(session, deal, request)
        rows.append({"deal_id": deal.id, "reference": deal.reference, "uat_batch_id": deal.uat_batch_id,
                     "valuation_available": "missing" not in trade, "reason": trade.get("missing"),
                     "available_dates": sorted(dates, reverse=True), "booking_url": f"/booking?deal={deal.id}"})
    # A historical date may reintroduce a deal now called/matured. Suggest it
    # only if that date's actual scope also has every required frozen valuation.
    common = [day for day in (common or []) if all("missing" not in archived_trade(session, deal,
        request.model_copy(update={"as_of_date": date.fromisoformat(day)}))
        for deal in portfolio_deals(session, user, request.model_copy(update={"as_of_date": date.fromisoformat(day)})))]
    return {"data_scope": request.data_scope, "uat_batch_id": request.uat_batch_id,
            "as_of_date": str(request.as_of_date), "selected_count": len(rows),
            "excluded_other_scope_count": len(excluded),
            "missing_valuation_count": sum(not r["valuation_available"] for r in rows),
            "common_valuation_dates": sorted(common or [], reverse=True), "deals": rows}


def runtime(trade, request):
    if trade.get("missing"):
        raise ValueError(f"{trade['reference']} : {trade['missing']}")
    if "pricing" in trade:
        req = PricingRequest.model_validate(trade["pricing"])
        origin = analysis_origin(req)
        if origin != request.as_of_date:
            raise ValueError("CCR pré-trade V1 : le strike doit coïncider avec la date d'arrêté ; pour un produit vivant utiliser son MtM figé")
        compiled = resolve_analysis_constats(parse_script(req.script), req)
        T = effective_T_max(compiled, req.T)
        ctx = ValuationContext(underlyings=[u.model_dump() for u in req.underlyings], corr_matrix=req.corr_matrix,
              r=req.r, T=T, N=max(1000, request.n_inner), model=req.model, seed=request.seed,
              user_params=req.user_params, yield_curve=req.yield_curve, funding_curve=req.funding_curve,
              funding_spread=req.funding_spread, sigma_r=req.sigma_r, barrier_monitoring=req.barrier_monitoring,
              maturity_payment_t=(req.payment_date-origin).days / 365.25 if req.payment_date else T,
              script_text=req.script, constats=req.constats)
        context = ctx.to_dict()
    else:
        replay = trade["replay"]
        if replay.get("settlement_claim"):
            return None, None
        compiled = residual_script_from_payload(replay)
        context = deepcopy(replay["valuation_context"])
    if context.get("strike_set_t"):
        raise ValueError("Forward-start : transmission du fixing futur au CCR non prise en charge")
    context["N"] = max(1000, request.n_inner)
    context["seed"] = request.seed
    if request.stress:
        allowed = {"spot_pct", "vol_points", "rate_bp", "correlation_points"}
        if set(request.stress) - allowed:
            raise ValueError("Stress CCR inconnu : utiliser spot_pct, vol_points, rate_bp, correlation_points")
        keys = [u.get("ticker") or u.get("name") for u in context["underlyings"]]
        scenario = MarketScenario(key="CCR_STRESS", label="Stress CCR explicite", method="stress",
            spot_pct={k: request.stress.get("spot_pct", 0) for k in keys},
            vol_pts={k: request.stress.get("vol_points", 0) for k in keys},
            corr_delta=request.stress.get("correlation_points", 0), dr_frac=request.stress.get("rate_bp", 0) / 10000)
        shock = apply_scenario_to_deal_base({"tickers": keys, "base": {"valuation_context": context, "corr": context["corr_matrix"]}}, scenario)
        context["r"] += shock["dr"]
        context["corr_matrix"] = shock["corr_shocked"]
        old_spots = context.get("state", {}).get("spot_mult") or [1.] * len(keys)
        new_spots = [x * y for x, y in zip(old_spots, shock["spot_mult"])]
        if min(new_spots) <= 0:
            raise ValueError("Le choc de spot doit rester supérieur à -100 %")
        context.setdefault("state", {}).update(spot_mult=new_spots, spot_base=new_spots, wof0_init=min(new_spots))
        for u, bump in zip(context["underlyings"], shock["vol_add"]):
            u["sigma"] += bump
            if u["sigma"] < 0:
                raise ValueError("Volatilité négative après stress")
    return compiled, context


def validate_future_context(context):
    # Current pricing supports every existing model. Future exposures are a
    # separate capability and must never downgrade the current pricing model.
    if context.get("funding_curve") or context.get("funding_spread"):
        raise ValueError("CCR clean : le contexte contient un spread/funding émetteur ; fournir une valorisation sans ajustement de crédit")
    if context["model"] != "constant":
        raise ValueError("CCR V1 : diffusion jointe GBM uniquement ; aucun remplacement implicite du modèle")
    _mtf_reject_unsupported(context["model"], context.get("barrier_monitoring", "weekly"),
                            context.get("yield_curve"), context.get("sigma_r", 0), context["underlyings"])


def joint_scenarios(runtimes, request, times):
    factors, correlations = {}, {}
    rate = None
    for _, ctx in runtimes:
        if ctx is None:
            continue
        if rate is not None and abs(rate - ctx["r"]) > 1e-10:
            raise ValueError("Taux incompatibles entre deals : harmoniser les contextes de marché")
        rate = ctx["r"]
        keys = []
        for u in ctx["underlyings"]:
            key = u.get("ticker") or u.get("name")
            if not key or key in keys:
                raise ValueError("Identifiant de facteur absent ou dupliqué")
            keys.append(key)
            risk = {k: u.get(k, 0) for k in ("sigma", "q", "sigma_fx", "rho_sfx", "ccyh")}
            if key in factors and factors[key] != risk:
                raise ValueError(f"Hypothèses de marché incompatibles pour {key}")
            factors[key] = risk
        for i, a in enumerate(keys):
            for j, b in enumerate(keys):
                pair = tuple(sorted((a, b)))
                value = ctx["corr_matrix"][i][j]
                if pair in correlations and abs(correlations[pair] - value) > 1e-10:
                    raise ValueError(f"Corrélations incompatibles pour {pair}")
                correlations[pair] = value
    keys = sorted(factors)
    if not keys:
        return {}, 0.
    matrix = []
    for a in keys:
        row = []
        for b in keys:
            pair = tuple(sorted((a, b)))
            value = correlations.get(pair, request.correlations.get("|".join(pair)))
            if value is None:
                raise ValueError(f"Corrélation inter-produits manquante : {'|'.join(pair)}")
            row.append(value)
        matrix.append(row)
    validate_correlation_matrix(matrix, len(keys))
    if np.linalg.eigvalsh(matrix).min() < -1e-10:
        raise ValueError("Matrice jointe non semi-définie positive : aucune réparation implicite CCR")
    paths = _simulate_mtf_outer([factors[k] for k in keys], matrix, rate, times[1:], request.n_outer, request.seed)
    return {k: paths[:, i, :] for i, k in enumerate(keys)}, rate


def legal_maps(config):
    return ({r["id"]: r["data"] for r in config.get("netting-sets", [])},
            {r["id"]: r["data"] for r in config.get("agreements", [])})


def aggregate(trades, matrices, times, rate, config, request, profile, *, standalone=False):
    sets, agreements = legal_maps(config)
    buckets = {}
    for trade, values in zip(trades, matrices):
        key = f"trade:{trade['key']}" if standalone else eligible_set(trade, sets, agreements, request.as_of_date)
        buckets.setdefault(key, []).append((trade, values))
    if not standalone:
        for row in config.get("collateral", []):
            position = row["data"]
            if (position["as_of_date"] == str(request.as_of_date) and position["posted"] > 0
                    and f"set:{position['netting_set_id']}" not in buckets):
                raise ValueError("Collatéral posté hors d'un set éligible du périmètre : créance à analyser séparément")
    total = np.zeros((len(times), request.n_outer))
    uncoll_total = total.copy()
    breakdown, warnings = [], []
    if not standalone and any(t.get("netting_set_id") and eligible_set(t, sets, agreements, request.as_of_date).startswith("trade:") for t in trades):
        warnings.append("Un rattachement ne satisfait pas les critères juridiques : exposition calculée sans compensation ni collatéral")
    held = posted = collateral = 0.
    for key, members in buckets.items():
        # Cross-product netting needs its own explicit legal permission.
        if key.startswith("set:"):
            ns = sets[int(key.split(":")[1])]
            agreement = agreements[ns["master_agreement_id"]]
            if len({t["product_type"] for t, _ in members}) > 1 and agreement["cross_product_netting_allowed"] is not True:
                raise ValueError("Netting inter-produits non autorisé par l'accord")
        net = sum((v for _, v in members), np.zeros_like(total))
        margin, margin_details = np.zeros_like(net), {"held": 0., "posted": 0., "net": 0., "im": 0.}
        if key.startswith("set:"):
            ns = sets[int(key.split(":")[1])]
            csa_row = next((r for r in config.get("csas", []) if r["id"] == ns.get("csa_id")), None)
            if csa_row:
                csa = CSAAgreement.model_validate(csa_row["data"])
                positions = [r for r in config.get("collateral", []) if r["data"]["netting_set_id"] == int(key.split(":")[1])
                             and r["data"]["as_of_date"] == str(request.as_of_date)]
                position = max(positions, key=lambda p: p["id"])["data"] if positions else None
                margin, margin_details = collateral_profile(net, times, request.as_of_date, csa, position)
                warnings.append("VM sur grille de valorisation ; appels sous-échantillonnés, gel MPOR en jours ouvrés, IM fixe reconnue")
        exposures = np.maximum(net - margin, 0)
        total += exposures
        uncoll_total += np.maximum(net, 0)
        held += margin_details["held"]
        posted += margin_details["posted"]
        collateral += margin_details["net"]
        breakdown.append({"bucket": key, "deal_ids": [t["deal_id"] for t, _ in members],
                          "net_mtm": float(net[0, 0]), "current_exposure": float(exposures[0, 0]),
                          "collateral": margin_details})
    result = summarize(total, uncoll_total, times, rate, profile, request.credit_spread_multiplier)
    result.update(gross_notional=sum(t["nominal"] for t in trades),
                  gross_positive_mtm=sum(max(float(v[0, 0]), 0) for v in matrices),
                  net_mtm=sum(float(v[0, 0]) for v in matrices), collateral=collateral,
                  collateral_held=held, collateral_posted=posted, netting_sets=breakdown,
                  warnings=sorted(set(warnings)))
    return result


def evaluate_inputs(inputs, progress=None):
    original_request = CalculationRequest.model_validate(inputs["request"])
    request = original_request.model_copy(deep=True)
    common_market = inputs.get("common_market", {})
    if common_market.get("correlation"):
        keys = common_market["tickers"]
        from ..var_engine import _shock_corr_scalar
        matrix = _shock_corr_scalar(common_market["correlation"],
            request.stress.get("correlation_points", 0) if inputs.get("stress_pass") else 0)
        request.correlations = {"|".join(sorted((a,b))): matrix[i][j]
            for i,a in enumerate(keys) for j,b in enumerate(keys)}
    if not inputs.get("stress_pass"):
        request.stress = {}
        request.credit_spread_multiplier = 1.
    market_stress = any(value != 0 for value in request.stress.values())
    trades, config = inputs["trades"], inputs["configuration"]
    profile = (CreditProfile.model_validate(config["profiles"][0]["data"]) if config.get("profiles") else request.hypothetical_profile)
    warnings = []
    if profile is None or profile.has_isda is None:
        warnings.append("ISDA STATUS UNKNOWN")
    if profile is None or profile.has_csa is None:
        warnings.append("CSA STATUS UNKNOWN")
    elif profile.has_csa is False:
        warnings.append("UNCOLLATERALISED")
    matrices, current, runtimes, errors = [], [], [], []
    if common_market.get("error"):
        errors.append(common_market["error"])
    for trade in trades:
        sign = 1 if trade["sens"] == "vente" else -1
        mtm = None if market_stress else trade.get("mtm_fraction")
        try:
            settlement_market = trade.get("settlement_valuation_market", {})
            if trade.get("replay", {}).get("settlement_claim") and (
                    settlement_market.get("funding_spread") or settlement_market.get("funding_curve")):
                mtm = None
                raise ValueError("CCR clean : créance en règlement valorisée avec funding émetteur")
            compiled, ctx = runtime(trade, request)
            if ctx and (ctx.get("funding_curve") or ctx.get("funding_spread")):
                mtm = None
                raise ValueError("CCR clean : fournir une valorisation sans spread/funding émetteur")
            if ctx is None and inputs.get("stress_pass"):
                if market_stress:
                    raise ValueError("Stress de marché d'une créance en règlement non pris en charge")
                mtm = trade.get("mtm_fraction")
            if ctx is not None:
                # Revalue proposed trades, preserving the existing pricing engine.
                if mtm is None:
                    mtm = run_valuation(compiled, ctx)["price"]
                    for flow in trade.get("unsettled_flows", []):
                        remaining = (date.fromisoformat(flow["payment_date"]) - request.as_of_date).days / 365.25
                        mtm += flow["cf"] * np.exp(-ctx["r"] * remaining)
            runtimes.append((compiled, ctx))
        except (ValueError, KeyError) as exc:
            runtimes.append((None, None))
            errors.append(str(exc))
        if trade["currency"] != request.currency:
            errors.append(f"{trade['reference']} : conversion FX non définie pour {trade['currency']}/{request.currency}")
            mtm = None
        current.append(None if mtm is None else mtm * trade["nominal"] * sign)
    if request.mode == "FULL":
        for _, ctx in runtimes:
            if ctx:
                try:
                    validate_future_context(ctx)
                except ValueError as exc:
                    errors.append(str(exc))
    full = request.mode == "FULL" and not errors
    if full:
        payments = [(date.fromisoformat(d) - request.as_of_date).days / 365.25
                    for trade in trades for d in
                    [trade.get("payment_date"), *[f.get("payment_date") for f in trade.get("unsettled_flows", [])]] if d]
        horizon = max([max(ctx["T"], ctx.get("maturity_payment_t") or 0) for _, ctx in runtimes if ctx] + payments + [1 / 52])
        # Weekly lattice inherited from the pricing engine; add every observation
        # and terminal settlement so the grid cannot omit a contractual boundary.
        marks = set(float(v) for v in np.linspace(1 / 52, horizon, request.n_dates))
        marks.update(t for t in payments if t > 0)
        for script, ctx in runtimes:
            if ctx:
                marks.update(d for ev in script.events for d in ev.dates if d >= 1 / 52)
                marks.update([ctx["T"], ctx.get("maturity_payment_t") or ctx["T"]])
        marks.add(float(np.ceil(horizon * 52) / 52))
        times = [0.] + sorted(set(round(max(1, round(t * 52)) / 52, 8) for t in marks))
        try:
            if len(times) * request.n_outer * request.n_inner * max(1, len(trades)) > 10_000_000:
                raise ValueError("Budget CCR dépassé : réduire les simulations ou le périmètre")
            shared, rate = joint_scenarios(runtimes, request, times)
            settlement_rates = []
            for trade, (_, ctx), mtm in zip(trades, runtimes, current):
                if ctx is None:
                    remaining = (date.fromisoformat(trade["payment_date"]) - request.as_of_date).days / 365.25
                    amount = trade.get("settlement_amount")
                    if remaining <= 0 or amount is None or not mtm or not amount:
                        raise ValueError("Créance en règlement : montant non nul et paiement futur requis pour la projection")
                    settlement_rates.append(float(np.log(abs(amount * trade["nominal"] / mtm)) / remaining))
            rates = ([rate] if shared else []) + settlement_rates
            if rates and max(rates) - min(rates) > 1e-8:
                raise ValueError("Taux de règlement incompatibles avec les autres valorisations")
            if rates:
                rate = rates[0]
            for trade_index, (trade, (script, ctx), mtm) in enumerate(zip(trades, runtimes, current)):
                if progress:
                    progress({"stage": "stress" if inputs.get("stress_pass") else "projection",
                              "deal_id": trade.get("deal_id"), "reference": trade["reference"],
                              "completed": trade_index, "total": len(trades)})
                matrix = np.zeros((len(times), request.n_outer))
                matrix[0] = mtm
                sign = 1 if trade["sens"] == "vente" else -1
                if ctx:
                    keys = [u.get("ticker") or u.get("name") for u in ctx["underlyings"]]
                    outer = np.stack([shared[k] for k in keys], axis=1)
                    spots = ctx.get("state", {}).get("spot_mult") or [1.] * len(keys)
                    outer *= np.asarray(spots)[None, :, None]
                    mtf = run_mark_to_future(script, ctx["underlyings"], ctx["corr_matrix"], ctx["r"], ctx["T"],
                            main_price=0, model=ctx["model"], n_outer=request.n_outer, n_inner=request.n_inner,
                            n_dates=len(times)-1, seed=request.seed, user_params=ctx["user_params"],
                            barrier_monitoring=ctx.get("barrier_monitoring", "weekly"), state=ctx.get("state"),
                            mtm_dates=times[1:], outer_paths=outer, credit_exposure=True,
                            maturity_payment_t=ctx.get("maturity_payment_t"),
                            progress=(lambda done, total: progress({"stage": "stress" if inputs.get("stress_pass") else "projection",
                                "deal_id": trade.get("deal_id"), "reference": trade["reference"],
                                "completed": trade_index, "total": len(trades), "horizon": done, "horizons": total})) if progress else None)
                    matrix[1:] = np.array([r["pvs"] for r in mtf["results"]]) * trade["nominal"] / 100 * sign
                    for flow in trade.get("unsettled_flows", []):
                        remaining = ((date.fromisoformat(flow["payment_date"]) - request.as_of_date).days / 365.25
                                     if flow.get("payment_date") else None)
                        if remaining is None:
                            raise ValueError("Date résiduelle de paiement absente d'un flux constaté")
                        for i, t in enumerate(times[1:], 1):
                            if t < remaining:
                                matrix[i] += flow["cf"] * np.exp(-rate * (remaining-t)) * trade["nominal"] * sign
                else:
                    payment = date.fromisoformat(trade["payment_date"])
                    remaining = (payment - request.as_of_date).days / 365.25
                    market = trade.get("settlement_market", {})
                    if market.get("yieldCurve") or market.get("fundingCurve"):
                        raise ValueError("Créance en règlement avec courbe : projection CCR non disponible")
                    amount = trade.get("settlement_amount")
                    if amount is None or mtm == 0 or amount == 0:
                        raise ValueError("Montant de règlement manquant ou nul : projection CCR indisponible")
                    effective_rate = np.log(abs(amount * trade["nominal"] / mtm)) / remaining
                    matrix[1:] = np.array([mtm * np.exp(effective_rate * t) if t < remaining else 0 for t in times[1:]])[:, None]
                matrices.append(matrix)
                if progress:
                    progress({"stage": "stress" if inputs.get("stress_pass") else "projection",
                              "deal_id": trade.get("deal_id"), "reference": trade["reference"],
                              "completed": trade_index + 1, "total": len(trades)})
        except (ValueError, KeyError) as exc:
            errors.append(str(exc))
            full = False
    if not full:
        times, rate = [0., 1.], 0.
        matrices = [np.full((2, request.n_outer), mtm if mtm is not None else 0) for mtm in current]
    def summarize_subset(ts, vs, standalone=False):
        try:
            result = aggregate(ts, vs, times, rate, config, request, profile, standalone=standalone)
        except ValueError as exc:
            errors.append(str(exc))
            # Missing collateral is not a measured current exposure.
            result = {"gross_notional": sum(t["nominal"] for t in ts), "current_exposure": None,
                      "net_mtm": None, "gross_positive_mtm": None, "profile": [], "warnings": []}
        if not full or not result.get("profile"):
            for key in ("ee", "epe", "pfe95", "pfe99", "maximum_pfe", "maximum_pfe_t", "cva", "ead", "stressed_exposure"):
                result[key] = None
            result["profile"] = []
        if any(current[trades.index(t)] is None for t in ts):
            for key in ("current_exposure", "net_mtm", "gross_positive_mtm"):
                result[key] = None
        if any(t["currency"] != request.currency for t in ts):
            result["gross_notional"] = None
        return result
    existing = [(t, v) for t, v in zip(trades, matrices) if t["key"] != "proposed"]
    if progress:
        progress({"stage": "aggregation"})
    proposed = [(t, v) for t, v in zip(trades, matrices) if t["key"] == "proposed"]
    before = summarize_subset([t for t, _ in existing], [v for _, v in existing])
    after = summarize_subset(trades, matrices)
    standalone = summarize_subset([t for t, _ in proposed], [v for _, v in proposed], True) if proposed else None
    incremental = {k: after.get(k) - before.get(k) if after.get(k) is not None and before.get(k) is not None else None
                   for k in METRICS} if proposed else None
    checks = []
    if request.counterparty_id is None:
        checks = [{"status": "NOT_APPLICABLE", "metric": k} for k in METRICS]
    else:
        # A subset is useful analytically but cannot clear a counterparty limit.
        partial = request.data_scope == "PRODUCTION" and any((request.deal_id, request.netting_set_id, request.portfolio_id))
        for metric in METRICS:
            limits = [r for r in config.get("limits", []) if r["data"]["metric"] == metric]
            active = [r for r in limits if r["data"]["active"] and r["data"]["effective_date"] <= str(request.as_of_date)
                      and (not r["data"].get("expiry_date") or r["data"]["expiry_date"] >= str(request.as_of_date))]
            if not active:
                checks.append({"metric": metric, **limit_check(None, None, request.currency, request.as_of_date)})
            for row in active:
                checks.append({"limit_id": row["id"], **limit_check(CreditLimit.model_validate(row["data"]),
                    None if partial else after.get(metric), request.currency, request.as_of_date)})
    deals = [{"deal_id": t["deal_id"], "reference": t["reference"], "product_type": t["product_type"],
              "netting_set_id": t.get("netting_set_id"), "nominal": t["nominal"],
              **summarize_subset([t], [v], True)} for t, v in zip(trades, matrices)]
    result = {"methodology": "NESTED_MONTE_CARLO_GBM" if full else (
                  "NESTED_MONTE_CARLO_INCOMPLETE" if request.mode == "FULL" else "FAST_CURRENT_EXPOSURE_ONLY"),
            "counterparty_id": request.counterparty_id,
            "data_scope": request.data_scope, "uat_batch_id": request.uat_batch_id,
            "is_test": request.data_scope == "UAT",
            "requested_mode": request.mode,
            "status": "MISSING_DATA" if errors else "CALCULATED", "errors": sorted(set(errors)),
            "credit_data_status": "MISSING_DATA" if request.counterparty_id and (profile is None or profile.recovery is None or profile.has_isda is None or profile.has_csa is None) else "AVAILABLE",
            "warnings": warnings + (["PFE99 : échantillon faible (< 1 000 scénarios)"] if request.n_outer < 1000 and full else []),
            "currency": request.currency, "as_of_date": str(request.as_of_date), "before": before, "after": after,
            "standalone": standalone, "incremental": incremental,
            "netting_benefit": (standalone["pfe95"] - incremental["pfe95"] if standalone and standalone.get("pfe95") is not None
                                and incremental["pfe95"] is not None else None),
            "deals": deals, "limits": checks, "decision": decision(checks),
            "regulatory": {"status": "NOT_APPLICABLE", "ead": None,
                           "reason": "SA-CCR non implémenté ; le PFE économique n'est jamais utilisé comme add-on réglementaire"},
            "credit_profile": profile.model_dump(mode="json") if profile else None,
            "assumptions": {"measure": "RISK_NEUTRAL", "wwr": "INDEPENDENCE",
              "seed": request.seed, "n_outer": request.n_outer, "n_inner": request.n_inner,
              "requested_dates": request.n_dates, "mtm_paths": request.mtm_paths if request.prepare_mtm else None,
              "common_rate": request.common_rate, "common_rate_source": request.common_rate_source,
              "market_overrides": {k:v.model_dump() for k,v in request.market_overrides.items()},
              "correlations": request.correlations, "allow_market_fetch": request.allow_market_fetch,
              "quantile": "linear", "pfe_limit_metric": "maximum over horizons", "time_grid": "weekly",
              "cva_integration": "right endpoint", "spread_to_hazard": "spread / LGD, piecewise constant; no CDS bootstrap",
              "collateral": "lagged margin calls on valuation grid; no interpolation", "source": "frozen valuations / explicit pricer inputs"}}
    if not inputs.get("stress_pass") and (original_request.stress or original_request.credit_spread_multiplier != 1):
        stressed = evaluate_inputs({**inputs, "stress_pass": True}, progress=progress)
        result["stress"] = {"assumptions": original_request.stress,
                           "credit_spread_multiplier": original_request.credit_spread_multiplier,
                           "after": stressed["after"], "errors": stressed["errors"],
                           "wwr": "STRESS — scénario, pas modèle joint"}
        result["after"]["stressed_exposure"] = stressed["after"].get("current_exposure")
        for index, check in enumerate(result["limits"]):
            if check["metric"] == "stressed_exposure" and check.get("limit_id"):
                row = next(r for r in config["limits"] if r["id"] == check["limit_id"])
                result["limits"][index] = {"limit_id": row["id"], **limit_check(CreditLimit.model_validate(row["data"]),
                    None if request.data_scope == "PRODUCTION" and any((request.deal_id, request.netting_set_id, request.portfolio_id)) else result["after"]["stressed_exposure"],
                    request.currency, request.as_of_date)}
        result["decision"] = decision(result["limits"])
    if request.data_scope == "UAT":
        result["warnings"].insert(0, "RECETTE UAT — contrôle des limites simulé, sans autorisation de booking ni consommation du portefeuille réel")
        result["decision"]["simulation_only"] = True
    result["valuation_assumptions"] = [{"deal_id": t.get("deal_id"), "reference": t["reference"],
        "error": t.get("missing"), **t.get("preparation", {})} for t in trades]
    result["common_market"] = common_market
    result["preparation_cache"] = inputs.get("preparation_cache", {})
    return result


def calculate(session, user, request, *, persist=True, progress=None):
    organization(user)
    if request.prepare_mtm:
        # Desk-approved temporary common rate until as-of rate data is wired.
        # Normalize only new calculations; archived replay keeps its own inputs.
        rate = .03 if request.common_rate is None else request.common_rate
        temporary = request.common_rate is None or (rate == .03 and request.common_rate_source == "TEMPORARY_ASSUMPTION")
        request = request.model_copy(update={"common_rate": rate,
            "common_rate_source": "TEMPORARY_ASSUMPTION" if temporary else "USER_OVERRIDE"})
    if not any((request.counterparty_id, request.deal_id, request.proposed)):
        raise HTTPException(422, "Choisir une contrepartie, un deal ou une proposition standalone")
    if request.valuation_method != "NESTED_MONTE_CARLO":
        raise HTTPException(422, f"Méthode CCR {request.valuation_method} non implémentée ; utiliser NESTED_MONTE_CARLO")
    if request.as_of_date > date.today():
        raise HTTPException(422, "La date d'arrêté ne peut pas être future")
    if request.wwr in {"GENERAL", "SPECIFIC"}:
        raise HTTPException(422, "Modèle joint de wrong-way risk non implémenté ; utiliser le stress explicite")
    if request.counterparty_id and request.hypothetical_profile:
        raise HTTPException(422, "Un profil hypothétique ne peut remplacer le profil d'une contrepartie identifiée")
    deals = portfolio_deals(session, user, request)
    if progress:
        progress({"stage": "scope", "total": len(deals), "deals": [{"id":d.id,"reference":d.reference} for d in deals]})
    if not deals and request.proposed is None:
        diagnostic = scope_diagnostic(session, user, request)
        raise HTTPException(422, f"Aucun deal retenu dans le périmètre {request.data_scope}. "
                            f"{diagnostic['excluded_other_scope_count']} deal(s) actif(s) exclu(s) appartenant à l'autre périmètre. "
                            "Vérifier le mode Production / Recette UAT et les filtres.")
    if request.counterparty_id is None and request.deal_id and deals:
        # Deal analysis remains standalone, including when the deal has a cpty.
        config = {}
    else:
        config = records(session, user, request.counterparty_id) if request.counterparty_id else {}
    if request.proposed:
        legal_assignment(session, user, request.counterparty_id, request.proposed.netting_set_id,
                         request.proposed.currency, request.proposed.product_type)
    version, fingerprint = engine_identity()
    ccr_digest = hashlib.sha256()
    for filename in ("contracts.py", "exposure.py", "service.py", "preparation.py", "common_market.py", "cache.py"):
        ccr_digest.update((Path(__file__).parent / filename).read_bytes())
    from .cache import preparation_key, find_prepared_base, archived_histories
    key = preparation_key(session, organization(user), deals, request, fingerprint + ccr_digest.hexdigest()) if request.prepare_mtm else None
    cached = find_prepared_base(session, organization(user), request, key) if key else None
    preparation_cache = {"key": key, "reused": bool(cached), "source_run_id": cached[0] if cached else None,
                         "snapshot_at": datetime.utcnow().isoformat(), "policy": "FROZEN_BASE_UNTIL_EXPLICIT_REFRESH"} if key else {}
    trades = [archived_trade(session, d, request) for d in deals]
    history_evidence = {}
    common_market = {}
    if cached:
        source_id, frozen = cached
        trades = frozen["trades"]
        history_evidence = frozen.get("market_histories", {})
        common_market = frozen.get("common_market", {})
        preparation_cache["snapshot_at"] = frozen["preparation_cache"]["snapshot_at"]
        if progress:
            progress({"stage": "reuse", "source_run_id": source_id, "completed": len(trades), "total": len(trades)})
    if request.prepare_mtm and not cached:
        from .preparation import MarketHistory, prepare_trade
        histories = MarketHistory(request, archived_histories(session, organization(user), request))
        for index, (deal, trade) in enumerate(zip(deals, trades)):
            def notify(phase):
                if progress:
                    progress({"stage": "mtm", "phase": phase, "deal_id": deal.id,
                        "reference": deal.reference, "completed": index, "total": len(deals)})
            notify("preparing")
            try:
                trades[index] = prepare_trade(session, deal, trade, request, histories, notify)
                phase = trades[index]["preparation"]["source"]
            except (ValueError, HTTPException) as exc:
                reason = str(exc.detail) if isinstance(exc, HTTPException) else str(exc)
                trades[index] = {k:v for k,v in trade.items() if k not in {"mtm_fraction", "replay"}}
                trades[index]["missing"] = f"Préparation MtM : {reason}"
                phase = "failed"
            if progress:
                progress({"stage":"mtm", "phase":phase, "deal_id":deal.id, "reference":deal.reference,
                    "completed":index+1, "total":len(deals), "error":trades[index].get("missing")})
        if request.common_market:
            from .common_market import harmonize_market
            try:
                trades, common_market = harmonize_market(trades, deals, session, request, histories, progress)
            except ValueError as exc:
                common_market = {"policy": "HISTORICAL_252D", "error": f"Marché commun : {exc}"}
        history_evidence = histories.evidence
    if request.proposed:
        trades.append(proposed_trade(request))
    inputs = {"request": request.model_dump(mode="json"), "trades": trades, "configuration": config,
              "pricing_model_version": version, "pricing_engine_fingerprint": fingerprint,
              "ccr_version": VERSION, "ccr_fingerprint": ccr_digest.hexdigest(), "entity_id": organization(user),
              "market_histories": history_evidence, "common_market": common_market, "preparation_cache": preparation_cache}
    result = evaluate_inputs(inputs, progress=progress)
    if persist:
        if progress:
            progress({"stage":"saving"})
        row = CCRExposureCalculation(entity_id=organization(user), counterparty_id=request.counterparty_id,
                created_by=user.id, as_of_date=str(request.as_of_date), methodology=result["methodology"],
                input_hash=canonical_fingerprint(inputs), inputs_json=canonical_json(inputs), results_json=canonical_json(result))
        session.add(row)
        session.flush()
        record_audit_event(session, action="CCR_CALCULATED", object_type="CCR_RUN", object_id=row.id,
                           actor_user_id=user.id, result="SUCCESS", after={"input_hash": row.input_hash,
                           "data_scope": request.data_scope, "uat_batch_id": request.uat_batch_id, "decision": result["decision"]})
        result["run_id"] = row.id
        result["calculation_timestamp"] = row.calculation_timestamp.isoformat()
        session.commit()
    if progress:
        progress({"stage":"completed", "status":result["status"]})
    return result


def enforce_booking(session, user, body):
    """Fresh server-side decision in the booking transaction; no client receipt reuse."""
    cpty = session.exec(select(Counterparty).where(Counterparty.name == body.contrepartie)).first()
    if not cpty:
        if body.ccr_netting_set_id is not None:
            raise HTTPException(422, "Un netting set nécessite une contrepartie référencée")
        return
    model = RECORDS["limits"]
    if user.entity_id is None:
        # Preserve legacy booking only where no CCR policy can be bypassed.
        configured = session.exec(select(model.id).where(model.counterparty_id == cpty.id)).first()
        if configured is not None or body.ccr_netting_set_id is not None:
            organization(user)
        return
    # Take the SQLite write lock before reading policy and portfolio state.
    session.exec(update(model).where(model.entity_id == organization(user), model.counterparty_id == cpty.id)
                 .values(version=model.version))
    legal_assignment(session, user, cpty.id, body.ccr_netting_set_id, body.devise, body.product_type)
    config = records(session, user, cpty.id)
    today = date.today().isoformat()
    active = [r for r in config["limits"] if r["data"]["active"] and r["data"]["effective_date"] <= today
              and (not r["data"].get("expiry_date") or r["data"]["expiry_date"] >= today)]
    if not active:
        return
    priced = (body.pricing_receipt or {}).get("pricing_input")
    if not priced:
        if any(r["data"]["action"] in {"HARD_BLOCK", "REQUIRE_APPROVAL"} for r in active):
            raise HTTPException(409, "CCR MISSING_DATA : preuve de pricing absente")
        return
    req = CalculationRequest(counterparty_id=cpty.id, currency=body.devise,
        mode="FULL" if any(r["data"]["metric"] not in {"gross_notional", "current_exposure"} for r in active) else "FAST",
        proposed={"pricing": priced, "nominal": body.nominal, "currency": body.devise,
                  "sens": body.sens, "product_type": body.product_type, "netting_set_id": body.ccr_netting_set_id})
    result = calculate(session, user, req, persist=False)
    if not result["decision"]["booking_allowed"]:
        raise HTTPException(409, {"code": "CCR_CREDIT_BLOCK", "message": "Limite de crédit dépassée, données manquantes ou approbation requise",
                                  "limits": result["limits"], "errors": result["errors"]})
    record_audit_event(session, action="CCR_BOOKING_CHECK", object_type="COUNTERPARTY", object_id=cpty.id,
                      actor_user_id=user.id, result="SUCCESS", after=result)
