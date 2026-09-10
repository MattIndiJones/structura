import itertools
from datetime import date
import math
import os
from pathlib import Path
import tempfile
import numpy as np
from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel
from ..core.schemas import (
    PricingRequest, PricingResponse, ParseRequest, ParseResponse,
    ProfileRequest, PathsRequest, ProbaRequest, BacktestRequest, BacktestCompareRequest,
    MtfRequest, MtfDrilldownRequest, ScriptGenerateRequest,
)
from ..core.payscript.parser import analysis_origin, parse_script, resolve_analysis_constats, effective_T_max
from ..core.payscript.engine import (
    run_mc, compute_greeks,
    run_payoff_profile, run_mc_paths, run_mc_proba,
    eval_script_on_history, compute_irr,
    run_mark_to_future, run_mtf_drilldown,
)
from ..services.market_data import load_hist_prices
from ..core.calendars import UnsupportedCurrency

router = APIRouter(prefix="/api", tags=["pricing"])


def _clean_flux(flux_map: dict) -> dict:
    """Return per-expression flux entries with rounded values for JSON.
    df = implied discount factor = pv/sum (exact under deterministic rates,
    conditional expectation E[B(0,t)|CF fires] under stochastic rates)."""
    result = {}
    for k, v in flux_map.items():
        sm = round(v["sum"], 6)
        pv = round(v.get("pv", v["sum"]), 6)
        df = round(pv / sm, 6) if abs(sm) > 1e-10 else 1.0
        result[k] = {
            "t":   round(v["t"], 6),
            # When the cash actually moves. Equal to t when nothing settles
            # later, which is what makes df readable as exp(-r·t).
            "t_pay": round(v.get("t_pay", v["t"]), 6),
            "lbl": v["lbl"],
            "n":   v["n"],
            "sum": sm,
            "pv":  pv,
            "df":  df,
        }
    return result


@router.post("/parse", response_model=ParseResponse)
def parse_endpoint(req: ParseRequest):
    try:
        compiled = parse_script(req.script)
        return ParseResponse(
            ok=True,
            params=[{
                "name": p.name,
                "raw_default": p.raw_default,
                "display_default": p.raw_default,
                "stored_val": p.stored_val,
                "is_pct": p.is_pct,
                "desc": p.desc,
                "kind": p.kind,
            } for p in compiled.params],
            constats=[{"name": c.name, "kind": c.kind, "reduction": c.reduction,
                       "window_scope": c.window_scope} for c in compiled.constats],
            events_count=len(compiled.events),
            has_stop=compiled.has_stop,
            monitors=compiled.monitors or [],
        )
    except ValueError as e:
        return ParseResponse(ok=False, params=[], constats=[], events_count=0, has_stop=False, errors=str(e))


@router.post("/price", response_model=PricingResponse)
def price_endpoint(req: PricingRequest):
    # Sync (threadpool) on purpose: run_mc is CPU-bound for seconds — an
    # `async def` here would hold the event loop and freeze the whole API
    # for every other request while a pricing runs. Same for every other
    # MC-driven endpoint in this file.
    # L'axe du temps s'ancre sur la date de strike : c'est là que le niveau
    # initial est constaté, donc là que la diffusion démarre. Sans elle, on
    # retombe sur `anchor` — la value date, comme avant.
    origin = analysis_origin(req)
    try:
        compiled = parse_script(req.script)
        # Meme resolveur que toutes les analytiques : c'est ce qui garantit que
        # le profil, les probas ou la grille decrivent le produit qu'on price.
        compiled = resolve_analysis_constats(compiled, req)
    except (ValueError, UnsupportedCurrency) as e:
        raise HTTPException(status_code=422, detail=str(e))

    if not compiled.events:
        raise HTTPException(status_code=422, detail="Aucun événement AT défini dans le script.")

    # La date de paiement finale se compte sur le même axe que les
    # constatations : celui ancré sur `anchor`.
    maturity_payment_t = None
    if req.payment_date is not None:
        maturity_payment_t = round((req.payment_date - origin).days / 365.25, 6)
    value_date_t = (round((req.value_date - origin).days / 365.25, 6)
                    if req.value_date is not None else 0.0)

    uls = [u.model_dump() for u in req.underlyings]
    corr = req.corr_matrix
    n = len(uls)

    if len(corr) != n or any(len(row) != n for row in corr):
        raise HTTPException(status_code=422, detail="Matrice de corrélation invalide.")

    T_eff = effective_T_max(compiled, req.T)

    try:
        result = run_mc(
            script=compiled,
            underlyings=uls,
            corr_matrix=corr,
            r=req.r,
            T_max=T_eff,
            N=req.N,
            model=req.model,
            seed=req.seed,
            antithetic=req.antithetic,
            user_params=req.user_params,
            yield_curve=req.yield_curve or [],
            funding_curve=req.funding_curve or [],
            funding_spread=req.funding_spread,
            sigma_r=req.sigma_r,
            a_r=req.a_r,
            barrier_monitoring=req.barrier_monitoring,
            maturity_payment_t=maturity_payment_t,
            value_date_t=value_date_t,
        )

        greeks: dict = {}
        if req.compute_greeks and req.selected_greeks:
            greeks = compute_greeks(
                compiled, uls, corr, req.r, T_eff,
                req.N, req.model, req.seed, req.user_params,
                selected=req.selected_greeks, sigma_r=req.sigma_r, a_r=req.a_r,
                yield_curve=req.yield_curve or [],
                funding_curve=req.funding_curve or [],
                funding_spread=req.funding_spread,
                barrier_monitoring=req.barrier_monitoring,
            )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    return PricingResponse(
        price=result["price"],
        ic95=result["ic95"],
        median=result["median"],
        var5=result["var5"],
        prob_gt100=result["prob_gt100"],
        payoffs=result["payoffs"],
        flux_table=_clean_flux(result["flux_table"]),
        greeks=greeks,
        elapsed_ms=result["elapsed_ms"],
        n_paths=result["n_paths"],
        n_eff=result["n_eff"],
        t_max_effective=round(T_eff, 4),
        fugit=result.get("fugit"),
        constatation_windows=result.get("constatation_windows"),
        schedule=(compiled.echeancier.to_dict()
                  if getattr(compiled, "echeancier", None) else None),
    )


@router.post("/profile")
def profile_endpoint(req: ProfileRequest):
    """Payoff profile — sweep spot 40%–200%, quasi-deterministic.

    En cours de vie, le profil se dessine sur la jambe RÉSIDUELLE : mêmes
    niveaux balayés, mais avec les coupons déjà accumulés et les barrières
    déjà franchies. Sans ça la courbe est celle du produit neuf, ce qui sur
    une note en difficulté raconte une autre histoire que la sienne.
    """
    ctx = residual_context_or_none(req)
    try:
        if ctx is not None:
            compiled, uls = ctx.script, ctx.underlyings
            r_eff, T_eff = ctx.r, ctx.T_remaining
            etat = ctx.mc_kwargs
            # Le balayage pince le spot lui-même : le multiplicateur de spot du
            # rejeu n'a pas lieu d'être ici, il ferait double emploi.
            etat.pop("spot_mult", None)
            etat.pop("spot_base", None)
        else:
            compiled = resolve_analysis_constats(parse_script(req.script), req)
            uls = [u.model_dump() for u in req.underlyings]
            r_eff, T_eff = req.r, effective_T_max(compiled, req.T)
            etat = None
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    corr = req.corr_matrix
    n = len(uls)
    if len(corr) != n or any(len(row) != n for row in corr):
        raise HTTPException(status_code=422, detail="Matrice de corrélation invalide.")

    try:
        res = run_payoff_profile(compiled, uls, corr, r_eff, T_eff,
                                  analysis_user_params(req, ctx), state=etat)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    res["in_life"] = ctx is not None
    if ctx is not None:
        res["valuation_date"] = ctx.valuation.isoformat()
        res["years_remaining"] = round(ctx.T_remaining, 4)
    return res


def analysis_user_params(req, ctx):
    """Les PARAM que l'analytique doit employer.

    Sur une jambe résiduelle d'avenant, ce sont ceux de la VARIANTE : la
    requête, elle, porte les termes d'origine, qui n'ont servi qu'à rejouer le
    passé. Hors variante les deux coïncident, donc rien ne bouge sur une
    analytique ordinaire."""
    return ctx.user_params if ctx is not None else req.user_params


def residual_context_or_none(req):
    """Contexte résiduel quand la requête est en cours de vie, sinon None.

    Import différé : inlife.py importe déjà ce module, un import au sommet
    créerait un cycle."""
    valuation = getattr(req, "valuation_date", None)
    strike = getattr(req, "strike_date", None)
    maturity = getattr(req, "maturity_date", None)
    if not (valuation and strike and maturity and valuation > strike):
        return None
    from .inlife import build_request_residual, variant_terms_or_none
    # La variante suit le prix jusque dans les analytiques : sans ça l'onglet
    # Probabilités décrirait le produit d'origine sous un prix d'avenant, ce
    # qui est exactement l'écart qu'on vient de fermer partout ailleurs.
    ctx = build_request_residual(req, variant_terms_or_none(req))
    # Un rappel anticipé détecté dans le passé : il n'y a plus rien à analyser
    # sur la vie restante, on retombe sur l'analyse à l'émission.
    return None if ctx.residuel.early_recall else ctx


@router.post("/paths")
def paths_endpoint(req: PathsRequest):
    """Monte Carlo sample paths for visualization."""
    ctx = residual_context_or_none(req)
    try:
        if ctx is not None:
            compiled, uls = ctx.script, ctx.underlyings
            r_eff, T_eff, etat = ctx.r, ctx.T_remaining, ctx.mc_kwargs
            yc = ctx.sur_axe_residuel(req.yield_curve)
        else:
            compiled = resolve_analysis_constats(parse_script(req.script), req)
            uls = [u.model_dump() for u in req.underlyings]
            r_eff, T_eff = req.r, effective_T_max(compiled, req.T)
            etat, yc = None, (req.yield_curve or [])
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    corr = req.corr_matrix
    n = len(uls)
    if len(corr) != n or any(len(row) != n for row in corr):
        raise HTTPException(status_code=422, detail="Matrice de corrélation invalide.")
    try:
        res = run_mc_paths(
            compiled, uls, corr, r_eff, T_eff,
            N_display=req.N_display,
            N_stat=req.N_stat,
            model=req.model,
            seed=req.seed,
            user_params=analysis_user_params(req, ctx),
            barrier_monitoring=req.barrier_monitoring,
            state=etat,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    res["in_life"] = ctx is not None
    if ctx is not None:
        res["valuation_date"] = ctx.valuation.isoformat()
        res["years_remaining"] = round(ctx.T_remaining, 4)
    return res


@router.post("/proba")
def proba_endpoint(req: ProbaRequest):
    """Probability analysis — P(autocall), P(KI), expected life, percentiles."""
    ctx = residual_context_or_none(req)
    try:
        if ctx is not None:
            compiled, uls = ctx.script, ctx.underlyings
            r_eff, T_eff, etat = ctx.r, ctx.T_remaining, ctx.mc_kwargs
            yc = ctx.sur_axe_residuel(req.yield_curve)
        else:
            compiled = resolve_analysis_constats(parse_script(req.script), req)
            uls = [u.model_dump() for u in req.underlyings]
            r_eff, T_eff = req.r, effective_T_max(compiled, req.T)
            etat, yc = None, (req.yield_curve or [])
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    corr = req.corr_matrix
    n = len(uls)
    if len(corr) != n or any(len(row) != n for row in corr):
        raise HTTPException(status_code=422, detail="Matrice de corrélation invalide.")
    try:
        res = run_mc_proba(
            compiled, uls, corr, r_eff, T_eff,
            N=req.N,
            model=req.model,
            seed=req.seed,
            user_params=analysis_user_params(req, ctx),
            yield_curve=yc,
            barrier_monitoring=req.barrier_monitoring,
            state=etat,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    res["in_life"] = ctx is not None
    if ctx is not None:
        res["valuation_date"] = ctx.valuation.isoformat()
        res["years_remaining"] = round(ctx.T_remaining, 4)
    return res


@router.post("/mtf")
def mtf_endpoint(req: MtfRequest):
    """Mark-to-Future — nested Monte Carlo: distribution of future mark-to-model
    values of the product, under the risk-neutral measure with frozen market params.

    En cours de vie, l'éventail part du niveau du jour et de l'état déjà réalisé :
    les scénarios extérieurs composent leur propre histoire par-dessus celle que
    le passé a écrite, au lieu de repartir d'un produit neuf."""
    ctx = residual_context_or_none(req)
    try:
        if ctx is not None:
            compiled, uls = ctx.script, ctx.underlyings
            r_eff, T_eff, etat = ctx.r, ctx.T_remaining, ctx.mc_kwargs
        else:
            compiled = resolve_analysis_constats(parse_script(req.script), req)
            uls = [u.model_dump() for u in req.underlyings]
            r_eff, T_eff, etat = req.r, None, None
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    if not compiled.events:
        raise HTTPException(status_code=422, detail="Aucun événement AT défini dans le script.")

    corr = req.corr_matrix
    n = len(uls)
    if len(corr) != n or any(len(row) != n for row in corr):
        raise HTTPException(status_code=422, detail="Matrice de corrélation invalide.")

    if T_eff is None:
        T_eff = effective_T_max(compiled, req.T)
    try:
        res = run_mark_to_future(
            compiled, uls, corr, r_eff, T_eff,
            main_price=req.main_price,
            state=etat,
            model=req.model,
            n_outer=req.n_outer,
            n_inner=req.n_inner,
            n_dates=req.n_dates,
            seed=req.seed,
            user_params=analysis_user_params(req, ctx),
            barrier_monitoring=req.barrier_monitoring,
            # Forwarded to be REFUSED, not honoured: the analysis is flat-rate
            # throughout. Dropping them here (which is what happened) priced the
            # fan on a different discount basis than the P0 it is plotted
            # against, with nothing on screen saying so.
            yield_curve=req.yield_curve,
            sigma_r=req.sigma_r,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    res["in_life"] = ctx is not None
    if ctx is not None:
        res["valuation_date"] = ctx.valuation.isoformat()
        res["years_remaining"] = round(ctx.T_remaining, 4)
    return res


@router.get("/script/providers")
def script_providers_endpoint():
    """Moteurs disponibles pour l'assistant, avec l'état de chacun.

    Ollama est annoncé disponible sans sonder localhost : une seconde d'attente
    à chaque affichage de page pour une information que le premier appel donnera
    de toute façon."""
    from ..services.llm import available_providers, DEFAULT_PROVIDER
    return {"providers": available_providers(), "default": DEFAULT_PROVIDER}


@router.post("/script/prompt")
def script_prompt_endpoint(req: ScriptGenerateRequest):
    """Le prompt exact qui partirait, sans appeler de modèle.

    Les exemples envoyés dépendent de la description : sans pouvoir les lire, on
    ne peut ni comprendre une génération ratée, ni ajuster sa demande autrement
    qu'à tâtons."""
    from ..services.llm import preview_prompt
    return preview_prompt(req.description, n_underlyings=len(req.underlyings) or 1,
                          maturity=req.T)


class ProductAnalysisRequest(BaseModel):
    """Un résumé de produit et ce qu'on veut en faire.

    Le résumé arrive REDIGE depuis l'écran, il n'est pas reconstruit ici : ce
    que l'utilisateur a lu est exactement ce qui part au modèle. Le reconstruire
    côté serveur rouvrirait l'écart entre l'affiché et l'envoyé."""
    resume: str
    intention: str = "analyse"
    question: str = ""
    provider: str = ""
    model: str = ""


@router.post("/product/analyse")
def product_analyse_endpoint(req: ProductAnalysisRequest):
    """Second avis d'un modèle sur un produit déjà pricé.

    200 dès que le modèle a répondu : son avis est un texte, pas un calcul, et
    il n'y a rien à valider côté serveur. Seule l'indisponibilité du moteur ou
    une intention inconnue est un 4xx."""
    from ..services.llm import DEFAULT_PROVIDER, LlmError
    from ..services.llm.analysis import analyse_produit

    try:
        return analyse_produit(
            req.resume, req.intention, question=req.question,
            provider=req.provider or DEFAULT_PROVIDER,
            model=req.model or None,
        )
    except LlmError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.post("/product/analyse/prompt")
def product_analyse_prompt_endpoint(req: ProductAnalysisRequest):
    """Les deux messages qui PARTIRAIENT, sans appeler le modèle.

    Même constructeur que l'envoi réel (`construire_prompts`) : un aperçu
    reconstruit à part finirait par décrire autre chose que ce qui part, et
    l'utilisateur croirait relire sa demande alors qu'il lirait une fiction.
    Aucun appel réseau, aucun jeton consommé — on peut donc regarder avant de
    demander."""
    from ..services.llm import LlmError
    from ..services.llm.analysis import construire_prompts

    try:
        return construire_prompts(req.resume, req.intention, req.question)
    except LlmError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get("/product/analyse/intentions")
def product_intentions_endpoint():
    """Les intentions proposables, avec leur libellé d'écran."""
    from ..services.llm.analysis import INTENTIONS
    return {"intentions": [{"id": k, "label": v["label"]} for k, v in INTENTIONS.items()]}


@router.post("/script/generate")
def script_generate_endpoint(req: ScriptGenerateRequest):
    """Assistant de scripting — description en français vers script PayScript.

    Renvoie toujours 200 quand le modèle a répondu, même si son script ne
    compile pas : l'erreur du parser fait partie du résultat à afficher, pas
    d'un échec de la requête. Seule l'indisponibilité du moteur est un 4xx/5xx.
    """
    from ..services.llm import generate, LlmError

    uls = [u.model_dump() for u in req.underlyings]
    if not uls:
        # Le pricing de contrôle a besoin d'un sous-jacent ; l'assistant doit
        # rester utilisable avant que l'utilisateur en ait configuré un.
        uls = [{"name": "S1", "ticker": "", "ccy": "EUR", "sigma": 0.22, "q": 0.02,
                "v0": 0.0484, "kappa": 2.0, "theta": 0.0484, "xi": 0.35,
                "rho_h": -0.70, "alpha": 0.22, "beta": 1.0, "rho": -0.30,
                "nu": 0.40, "sigma_fx": 0.0, "rho_sfx": 0.0, "ccyh": 0.0}]
    n = len(uls)
    corr = req.corr_matrix
    if len(corr) != n or any(len(row) != n for row in corr):
        corr = [[1.0 if i == j else 0.5 for j in range(n)] for i in range(n)]

    try:
        return generate(
            req.description, provider=req.provider, model=req.model,
            underlyings=uls, corr=corr, r=req.r, T=req.T,
            user_params=req.user_params,
            current_script=req.current_script, refine=req.refine,
        )
    except LlmError as e:
        # 502 : c'est le fournisseur qui est en cause, pas la requête. Le
        # message est déjà rédigé pour l'utilisateur (Ollama éteint, clé
        # absente, modèle non installé, quota).
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/script/transcribe/engines")
def script_transcribe_engines_endpoint():
    """Le moteur de dictée est-il utilisable, et faut-il annoncer un
    téléchargement ?

    L'écran s'en sert pour griser le micro plutôt que de laisser cliquer sur un
    bouton qui échouera après coup — même raison que la sonde des modèles
    Ollama : un sélecteur doit annoncer ce qui existe."""
    from ..services.transcription import available_engines, DEFAULT_ENGINE
    return {"engines": available_engines(), "default": DEFAULT_ENGINE}


@router.post("/script/transcribe/prepare")
def script_transcribe_prepare_endpoint():
    """Charge le moteur — et télécharge ses poids si besoin — HORS dictée.

    Sans cette route, les ~480 Mo du premier usage partaient à l'intérieur de la
    requête de transcription : elle pendait plusieurs minutes et le navigateur
    lâchait la connexion (« Failed to fetch ») pendant que le téléchargement,
    lui, allait à son terme. L'utilisateur voyait une dictée en échec alors que
    rien n'était cassé.

    Idempotent : une fois les poids là et le modèle en mémoire, l'appel est
    instantané."""
    from ..services.transcription import TranscriptionError, warmup

    try:
        return warmup()
    except TranscriptionError as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/script/transcribe")
def script_transcribe_endpoint(audio: UploadFile = File(...)):
    """Un enregistrement de dictée vers du texte brut.

    Endpoint SYNCHRONE volontairement : la transcription est du calcul CPU de
    plusieurs secondes. En `async def` elle bloquerait la boucle d'événements et
    figerait tout le serveur pendant la dictée ; en `def`, FastAPI l'exécute
    dans son pool de threads.

    Le texte remonte tel quel, ni reformulé ni relu par un modèle de langage :
    il atterrit dans le champ de description où l'utilisateur le corrige. Une
    dictée qui avale « à tout moment » décrit un autre produit — c'est à l'écran
    de le montrer, pas au serveur de le deviner.
    """
    from ..services.transcription import (MAX_UPLOAD_MB, TranscriptionError,
                                          transcribe)

    data = audio.file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Enregistrement vide.")
    if len(data) > MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(
            status_code=413,
            detail=f"Enregistrement trop long (limite {MAX_UPLOAD_MB} Mo).")

    # Fichier temporaire plutôt qu'un flux mémoire : le décodage de l'Opus passe
    # par ffmpeg, qui veut un chemin. `delete=False` puis suppression explicite —
    # sous Windows un NamedTemporaryFile encore ouvert ne peut pas être rouvert
    # par un autre processus.
    suffix = Path(audio.filename or "").suffix or ".webm"
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    try:
        tmp.write(data)
        tmp.close()
        return transcribe(tmp.name)
    except TranscriptionError as e:
        # 502 comme pour l'assistant : c'est le moteur qui est en cause, pas la
        # requête, et le message est déjà rédigé pour l'utilisateur.
        raise HTTPException(status_code=502, detail=str(e))
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


@router.post("/mtf/drilldown")
def mtf_drilldown_endpoint(req: MtfDrilldownRequest):
    """Mark-to-Future — explication détaillée de scénarios choisis à une date.

    Rejoue les mêmes tirages que /api/mtf (mêmes graine, grille de dates et
    découpage en lots) : le mark renvoyé ici est celui de l'éventail, pas une
    ré-estimation voisine."""
    try:
        compiled = parse_script(req.script)
        compiled = resolve_analysis_constats(compiled, req)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    if not compiled.events:
        raise HTTPException(status_code=422, detail="Aucun événement AT défini dans le script.")

    uls = [u.model_dump() for u in req.underlyings]
    corr = req.corr_matrix
    n = len(uls)
    if len(corr) != n or any(len(row) != n for row in corr):
        raise HTTPException(status_code=422, detail="Matrice de corrélation invalide.")

    T_eff = effective_T_max(compiled, req.T)
    try:
        return run_mtf_drilldown(
            compiled, uls, corr, req.r, T_eff,
            main_price=req.main_price,
            t0=req.t,
            scenario_ids=req.scenario_ids,
            labels=req.labels,
            # Le texte du script sert à retrouver statiquement quels PARAM sont
            # comparés à une observable — c'est ce qui distingue une barrière
            # d'un taux de coupon sans avoir à le deviner sur la valeur.
            script_source=req.script,
            model=req.model,
            n_outer=req.n_outer,
            n_inner=req.n_inner,
            n_dates=req.n_dates,
            seed=req.seed,
            user_params=req.user_params,
            barrier_monitoring=req.barrier_monitoring,
            yield_curve=req.yield_curve,
            sigma_r=req.sigma_r,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.post("/backtest")
def backtest_endpoint(req: BacktestRequest):
    """Historical backtest — replay script on actual Yahoo Finance price history."""
    try:
        compiled = parse_script(req.script)
        compiled = resolve_analysis_constats(compiled, req)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    tickers = [u.ticker for u in req.underlyings if u.ticker.strip()]
    if not tickers:
        raise HTTPException(status_code=422, detail="Aucun ticker défini dans les sous-jacents.")

    # Load historical prices
    px_data = load_hist_prices(tickers, req.start_date, req.end_date)
    if "error" in px_data:
        raise HTTPException(status_code=422, detail=px_data["error"])

    dates = px_data.get("dates", [])
    prices = px_data.get("prices", {})
    missing = [tk for tk in tickers if tk not in prices]
    if missing:
        raise HTTPException(status_code=422, detail=f"Tickers manquants dans l'historique: {missing}")

    T_eff = effective_T_max(compiled, req.T)
    SY_H = 252
    days_T = round(T_eff * SY_H)
    max_start = len(dates) - days_T - 1
    if max_start < 1:
        raise HTTPException(status_code=422, detail="Historique trop court pour la maturité du produit.")

    windows = list(range(0, max_start + 1, req.freq))
    results = []
    excluded: list[dict] = []
    invest_dec = req.invest_pct / 100.0

    try:
        for si in windows:
            res = eval_script_on_history(
                compiled, dates, prices, si, T_eff, req.user_params, tickers, req.r
            )
            if res is None:
                continue
            cfs = [{"t": 0.0, "cf": -invest_dec}] + res["cash_flows"]
            irr = compute_irr(cfs)
            if irr is None:
                # A window whose IRR cannot be defined is dropped — but it is
                # counted and dated, because a silent drop is how a backtest
                # loses its worst cases without anyone noticing.
                excluded.append({"date": dates[si], "reason": "IRR non défini"})
                continue
            results.append({
                "date": dates[si],
                "irr": round(irr, 4),
                "T_actual": round(res["T_actual"], 3),
                "early_recall": res["early_recall"],
            })
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    if not results:
        raise HTTPException(status_code=422, detail="Aucun résultat de backtest (données insuffisantes ou script incompatible).")

    irrs = [r["irr"] for r in results]
    n = len(irrs)
    sorted_irrs = sorted(irrs)
    mean_irr = sum(irrs) / n
    median_irr = sorted_irrs[n // 2]
    p10 = sorted_irrs[int(n * 0.10)]
    p90 = sorted_irrs[int(n * 0.90)]
    positive = sum(1 for v in irrs if v > 0)
    early_recalls = sum(1 for r in results if r["early_recall"])
    rf = req.rf_rate / 100.0
    excess = [v - rf for v in irrs]
    ex_mean = sum(excess) / n
    ex_std = (sum((v - ex_mean)**2 for v in excess) / n) ** 0.5
    sharpe = round(ex_mean / ex_std, 3) if ex_std > 1e-6 else None

    # Consecutive rolling windows spaced `freq` days apart, each covering
    # `days_T` days, share `days_T - freq` days of the same price history
    # when freq < days_T — the closer freq is to 0, the more their outcomes
    # are the same realization replayed, not independent draws. That
    # inflates this cross-window Sharpe (shrinks its denominator) without
    # reflecting genuine risk-adjusted return — see BacktestTab.vue caveat.
    overlap_pct = round(100 * max(0, days_T - req.freq) / days_T, 1) if days_T else 0.0

    return {
        "rows": results,
        "n_windows": n,
        "mean_irr": round(mean_irr, 4),
        "median_irr": round(median_irr, 4),
        "p10": round(p10, 4),
        "p90": round(p90, 4),
        "pct_positive": round(positive / n * 100, 1),
        "early_recall_pct": round(early_recalls / n * 100, 1),
        "sharpe": sharpe,
        "overlap_pct": overlap_pct,
        # Windows the statistics above do NOT cover. Every figure on this
        # screen is computed over n_windows, not over len(windows); the
        # difference belongs on screen, not in a log nobody reads.
        "excluded_windows": excluded,
        "n_excluded": len(excluded),
    }


# ── Underlying comparator ──────────────────────────────────────────────
# Same script, same params, swap the underlying(s) and see which ones would
# have backtested best. See BacktestCompareRequest docstring for the
# two-stage funnel (individual screen, then combinations only within the
# shortlist) — an exhaustive combinatorial scan is not feasible.

def _windowed_backtest(compiled, dates, prices, tickers, T_eff, freq, r, invest_pct, user_params,
                        return_windows=False):
    """Sliding-window historical replay for a fixed set of tickers — the
    core loop shared by /backtest, /backtest/compare and the reinvestment
    proposal (api/deals.py). Returns summary stats only by default (the
    comparator only needs the ranking) — return_windows=True additionally
    attaches a per-window {start_date, irr, early_recall} list, used by the
    proposal to plot the product's realized outcome against the underlying's
    price history (opt-in: keeps /backtest/compare's response light across
    its up-to-20-candidate pool)."""
    SY_H = 252
    days_T = round(T_eff * SY_H)
    max_start = len(dates) - days_T - 1
    if max_start < 1:
        return None

    windows = range(0, max_start + 1, freq)
    invest_dec = invest_pct / 100.0
    irrs, early_recalls = [], 0
    n_excluded = 0
    window_rows = [] if return_windows else None
    for si in windows:
        res = eval_script_on_history(compiled, dates, prices, si, T_eff, user_params, tickers, r)
        if res is None:
            n_excluded += 1
            continue
        cfs = [{"t": 0.0, "cf": -invest_dec}] + res["cash_flows"]
        irr = compute_irr(cfs)
        if irr is None:
            # Counted, not merely skipped: this comparator ranks candidates
            # against each other, so two of them dropping a different number
            # of windows are not being compared on the same basis.
            n_excluded += 1
            continue
        irrs.append(irr)
        if res["early_recall"]:
            early_recalls += 1
        if return_windows:
            window_rows.append({"start_date": dates[si], "irr": round(irr, 4),
                                 "early_recall": res["early_recall"]})

    if not irrs:
        return None
    n = len(irrs)
    sorted_irrs = sorted(irrs)
    result = {
        "n_windows": n,
        "mean_irr": round(sum(irrs) / n, 4),
        "median_irr": round(sorted_irrs[n // 2], 4),
        # A good median/mean can still hide a real loss tail (worst-of
        # payoffs are asymmetric: mostly clustered near the coupon, with a
        # thin but real chance of a sharp capital loss) — surface it here
        # rather than only in the full single-underlying Backtest tab.
        "p10_irr": round(sorted_irrs[int(n * 0.10)], 4),
        "worst_irr": round(sorted_irrs[0], 4),
        "pct_positive": round(sum(1 for v in irrs if v > 0) / n * 100, 1),
        "early_recall_pct": round(early_recalls / n * 100, 1),
        "n_excluded": n_excluded,
    }
    if return_windows:
        result["windows"] = window_rows
    return result


def _realized_corr(prices: dict, tickers: list) -> list:
    """Pairwise correlation of daily log returns — the actual historical
    joint behaviour of this basket, not an assumed/default matrix, since
    the price history needed is already in hand from the backtest."""
    n = len(tickers)
    if n == 1:
        return [[1.0]]
    min_len = min(len(prices[tk]) for tk in tickers)
    series = []
    for tk in tickers:
        px = np.array(prices[tk][-min_len:], dtype=np.float64)
        px = np.where(px > 0, px, np.nan)
        series.append(np.diff(np.log(px)))
    mat = np.array(series)
    valid = ~np.isnan(mat).any(axis=0)
    mat = mat[:, valid]
    if mat.shape[1] < 10:
        return [[1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]
    corr = np.corrcoef(mat)
    return [[round(float(corr[i][j]), 4) for j in range(n)] for i in range(n)]


@router.post("/backtest/compare")
def backtest_compare_endpoint(req: BacktestCompareRequest):
    try:
        compiled = parse_script(req.script)
        compiled = resolve_analysis_constats(compiled, req)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    tickers, ticker_name = [], {}
    for c in req.candidates:
        tk = c.ticker.strip()
        if tk and tk not in ticker_name:
            tickers.append(tk)
            ticker_name[tk] = c.name or tk
    if not tickers:
        raise HTTPException(status_code=422, detail="Aucun ticker dans la liste des sous-jacents (Marché & Paramètres).")
    if len(tickers) < req.basket_size:
        raise HTTPException(status_code=422,
            detail=f"Il faut au moins {req.basket_size} sous-jacent(s) distinct(s) pour un panier de taille {req.basket_size}.")

    px_data = load_hist_prices(tickers, req.start_date, req.end_date)
    if "error" in px_data:
        raise HTTPException(status_code=422, detail=px_data["error"])
    dates = px_data.get("dates", [])
    prices = px_data.get("prices", {})
    tickers = [tk for tk in tickers if tk in prices]
    if not tickers:
        raise HTTPException(status_code=422, detail="Aucun historique trouvé pour ces tickers.")

    T_eff = effective_T_max(compiled, req.T)

    # Stage 1 — every candidate alone, cheap (O(N) backtests)
    stage1 = []
    for tk in tickers:
        summary = _windowed_backtest(compiled, dates, prices, [tk], T_eff, req.freq, req.r, req.invest_pct, req.user_params)
        if summary is not None:
            stage1.append({"tickers": [tk], "names": [ticker_name[tk]], "corr_matrix": [[1.0]], **summary})
    if not stage1:
        raise HTTPException(status_code=422, detail="Aucun résultat de backtest (historique insuffisant pour tous les candidats).")
    stage1.sort(key=lambda r_: r_["median_irr"], reverse=True)

    if req.basket_size == 1:
        return {"stage": "individual", "results": stage1, "shortlist": [r_["tickers"][0] for r_ in stage1]}

    # Stage 2 — combinations, but only within the top performers of stage 1
    shortlist = [r_["tickers"][0] for r_ in stage1[:req.shortlist_n]]
    if len(shortlist) < req.basket_size:
        raise HTTPException(status_code=422,
            detail=f"Seulement {len(shortlist)} candidat(s) exploitable(s) pour un panier de {req.basket_size}.")

    n_combos = math.comb(len(shortlist), req.basket_size)
    MAX_COMBOS = 3000
    if n_combos > MAX_COMBOS:
        raise HTTPException(status_code=422,
            detail=f"{n_combos} combinaisons à tester (top {len(shortlist)} candidats, panier de {req.basket_size}) "
                   f"— trop pour rester rapide (max {MAX_COMBOS}). Réduisez la shortlist ou la taille du panier.")

    combos = []
    for combo in itertools.combinations(shortlist, req.basket_size):
        combo = list(combo)
        summary = _windowed_backtest(compiled, dates, prices, combo, T_eff, req.freq, req.r, req.invest_pct, req.user_params)
        if summary is not None:
            combos.append({
                "tickers": combo, "names": [ticker_name[tk] for tk in combo],
                "corr_matrix": _realized_corr(prices, combo), **summary,
            })
    if not combos:
        raise HTTPException(status_code=422, detail="Aucune combinaison exploitable (historique insuffisant).")
    combos.sort(key=lambda r_: r_["median_irr"], reverse=True)

    return {"stage": "combinations", "results": combos, "shortlist": shortlist, "individual": stage1}
