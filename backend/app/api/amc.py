"""AMC Fama-French analysis — REST endpoints."""
from __future__ import annotations

import io
import json
try:
    from typing import Annotated
except ImportError:
    from typing_extensions import Annotated

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Optional, Any
import io

from .auth import get_current_user
from ..db.models import User
from ..core.amc_engine import (
    parse_amc_excel,
    get_ff_series_list,
    get_benchmark_list,
    run_analysis,
    ff_data_status,
    ff_refresh,
)
from ..core.amc_pdf import generate_pdf, generate_study_pdf
from ..core.amc_manifest import (
    detect_study_folder, blank_template, StudyManifest,
    MANIFEST_DOC, BLOCK_CATALOG,
)
from ..core.amc_study import run_study

router = APIRouter(prefix="/api/amc", tags=["amc"])


@router.get("/ff-series")
def list_ff_series(current: Annotated[User, Depends(get_current_user)]):
    return get_ff_series_list()


@router.get("/ff-status")
def get_ff_status(current: Annotated[User, Depends(get_current_user)]):
    """Return availability status of all stored FF series."""
    return ff_data_status()


@router.post("/ff-refresh")
def refresh_ff(
    series_key: str,
    current: Annotated[User, Depends(get_current_user)],
):
    """Download from Ken French library and persist locally. Call once per series."""
    try:
        return ff_refresh(series_key)
    except ValueError as e:
        raise HTTPException(422, str(e))
    except Exception as e:
        raise HTTPException(500, f"Erreur téléchargement : {e}")


@router.get("/benchmarks")
def list_benchmarks(current: Annotated[User, Depends(get_current_user)]):
    return get_benchmark_list()


@router.post("/upload")
async def upload_amc(
    file: UploadFile = File(...),
    current: Annotated[User, Depends(get_current_user)] = None,
):
    """Parse the AMC diagnostic Excel and return structured data."""
    content = await file.read()
    try:
        result = parse_amc_excel(io.BytesIO(content))
        return result
    except Exception as e:
        raise HTTPException(422, f"Erreur de lecture du fichier : {e}")


class AnalyzeRequest(BaseModel):
    nav: list
    transactions: list = []
    composition: list = []
    exposures: dict = {}
    ff_series: str = "Global_3F"
    selected_factors: List[str] = ["Mkt-RF", "SMB", "HML"]
    benchmark_ticker: str = "IGF"
    rolling_window: int = 60


class ExportPdfRequest(BaseModel):
    result: dict
    meta: dict = {}


@router.post("/analyze")
def analyze(
    req: AnalyzeRequest,
    current: Annotated[User, Depends(get_current_user)],
):
    """Run the full Fama-French analysis."""
    try:
        return run_analysis(
            nav_records=req.nav,
            tx_records=req.transactions,
            comp_records=req.composition,
            exposures=req.exposures,
            ff_series=req.ff_series,
            selected_factors=req.selected_factors,
            benchmark_ticker=req.benchmark_ticker,
            rolling_window=req.rolling_window,
        )
    except ValueError as e:
        raise HTTPException(422, str(e))
    except Exception as e:
        raise HTTPException(500, f"Erreur d'analyse : {e}")


@router.post("/export-pdf")
def export_pdf(
    req: ExportPdfRequest,
    current: Annotated[User, Depends(get_current_user)],
):
    """Generate a professional PDF report from analysis results."""
    try:
        pdf_bytes = generate_pdf(req.result, req.meta or {})
        filename = f"AMC_FF_{req.meta.get('isin', 'report')}_{__import__('datetime').date.today()}.pdf"
        return StreamingResponse(
            io.BytesIO(pdf_bytes),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as e:
        import traceback; traceback.print_exc()
        raise HTTPException(500, f"Erreur génération PDF : {e}")


# ── Study (manifest-based full pipeline) ──────────────────────────────

# ── AI Synthesis ──────────────────────────────────────────────────────────

class SynthesizeRequest(BaseModel):
    study_result:       dict
    vag_result:         Optional[dict] = None
    attribution_result: Optional[dict] = None
    brinson_result:     Optional[dict] = None
    provider:           str = "ollama"
    ollama_url:         str = "http://localhost:11434"
    ollama_model:       str = "llama3.3:70b"
    claude_key:         str = ""
    claude_model:       str = "claude-sonnet-4-6"
    openai_key:         str = ""
    openai_model:       str = "gpt-4o"


@router.post("/synthesize/payload")
def get_synthesis_payload(
    req: SynthesizeRequest,
    current: Annotated[User, Depends(get_current_user)],
):
    """Return the human-readable payload that would be sent to the LLM — no AI call."""
    from ..core.amc_synthesize import build_synthesis_payload
    payload = build_synthesis_payload(
        req.study_result,
        req.vag_result,
        req.attribution_result,
        req.brinson_result,
    )
    return {"payload": payload}


@router.post("/synthesize")
def synthesize_study(
    req: SynthesizeRequest,
    current: Annotated[User, Depends(get_current_user)],
):
    """Generate an AI synthesis using the configured LLM provider."""
    from ..core.amc_synthesize import (
        build_synthesis_payload, _get_system_prompt,
        call_ollama, call_claude, call_openai,
    )
    meta     = req.study_result.get("meta") or {}
    audience = meta.get("audience", "committee")
    language = (req.study_result.get("output") or {}).get("language", "fr")

    payload       = build_synthesis_payload(
        req.study_result, req.vag_result, req.attribution_result, req.brinson_result,
    )
    system_prompt = _get_system_prompt(audience, language)

    try:
        if req.provider == "ollama":
            text = call_ollama(payload, system_prompt, req.ollama_url, req.ollama_model)
        elif req.provider == "claude":
            if not req.claude_key:
                raise ValueError("Clé API Claude requise.")
            text = call_claude(payload, system_prompt, req.claude_key, req.claude_model)
        elif req.provider == "openai":
            if not req.openai_key:
                raise ValueError("Clé API OpenAI requise.")
            text = call_openai(payload, system_prompt, req.openai_key, req.openai_model)
        else:
            raise ValueError(f"Provider inconnu : {req.provider}")
    except ValueError as e:
        raise HTTPException(422, str(e))
    except Exception as e:
        raise HTTPException(500, f"Erreur LLM ({req.provider}) : {e}")

    return {"synthesis": text, "payload": payload}


@router.get("/synthesize/ollama-models")
def get_ollama_models(
    url: str = "http://localhost:11434",
    current: Annotated[User, Depends(get_current_user)] = None,
):
    """List available Ollama models at the given URL."""
    from ..core.amc_synthesize import list_ollama_models
    try:
        models = list_ollama_models(url)
        return {"models": models, "error": None}
    except Exception as e:
        return {"models": [], "error": str(e)}


# ── Study (manifest-based full pipeline) ──────────────────────────────

class StudyRunRequest(BaseModel):
    manifest: dict
    folder: str                         # absolute path on the server


class StudyExportRequest(BaseModel):
    study_result:       dict
    synthese_text:      str = ""
    vag_result:         Optional[dict] = None
    attribution_result: Optional[dict] = None
    brinson_result:      Optional[dict] = None
    market_shocks_result: Optional[dict] = None
    company_name:       str = "TP Advisory Services"
    client_name:        str = ""
    include_annexes:    bool = True
    include_brinson:    bool = False
    include_marketshocks: bool = False


@router.get("/study/doc")
def study_doc(current: Annotated[User, Depends(get_current_user)]):
    """Return manifest field documentation + block catalog for the UI."""
    return {"fields": MANIFEST_DOC, "blocks": BLOCK_CATALOG}


@router.get("/study/template")
def study_template(current: Annotated[User, Depends(get_current_user)]):
    """Return a documented blank manifest template."""
    return blank_template()


@router.post("/study/detect")
def study_detect(
    payload: dict,
    current: Annotated[User, Depends(get_current_user)],
):
    """Scan a local ISIN folder and return a pre-filled manifest.

    Body: {"folder": "<absolute path to the ISIN folder>"}
    """
    folder = payload.get("folder", "")
    if not folder:
        raise HTTPException(422, "Champ 'folder' requis.")
    try:
        return detect_study_folder(folder)
    except ValueError as e:
        raise HTTPException(422, str(e))
    except Exception as e:
        raise HTTPException(500, f"Erreur de scan : {e}")


class ManagerSkillRequest(BaseModel):
    study_result: dict
    vag_result:   Optional[dict] = None


@router.post("/manager-skill")
def compute_manager_skill(
    req: ManagerSkillRequest,
    current: Annotated[User, Depends(get_current_user)],
):
    """Recompute Manager Skill Score — always returns both with_vag and no_vag scores."""
    from ..core.amc_managerskill import compute_manager_skill_score
    try:
        mss_with = compute_manager_skill_score(req.study_result, req.vag_result)
        mss_no   = compute_manager_skill_score(req.study_result, None)
        mss_with["mss_no_vag"] = mss_no
        return mss_with
    except Exception as e:
        raise HTTPException(422, str(e))


class MarketShocksRequest(BaseModel):
    study_result: dict
    folder:       str


@router.post("/marketshocks")
def compute_market_shocks_endpoint(
    req: MarketShocksRequest,
    current: Annotated[User, Depends(get_current_user)],
):
    """Compute Bloc K (Réactivité aux Chocs de Marché) on demand.

    Mirrors Bloc G (Brinson): not run automatically inside run_study() unless
    manifest.blocks.K_marketshocks was pre-selected — otherwise computed here,
    from its own tab, on an already-completed study.
    """
    import glob
    from pathlib import Path
    from ..core.amc_orderbook import load_orders, apply_split_corrections
    from ..core.amc_marketshocks import compute_market_shocks

    base = Path(req.folder)
    paths: list[str] = []
    seen: set[str] = set()
    for p in (list(base.glob("* Data*.json")) + list(base.glob("*Data*.json"))
              + list(base.glob("merged-*.json"))):
        rp = str(p.resolve())
        if rp not in seen:
            seen.add(rp)
            paths.append(str(p))
    if not paths:
        raise HTTPException(422, f"Aucun fichier d'ordres JSON trouvé dans {req.folder}")

    meta = req.study_result.get("meta") or {}
    orders = load_orders(paths)
    as_of = orders[-1]["date"] if orders else None
    orders = apply_split_corrections(orders, as_of)

    try:
        result = compute_market_shocks(orders, meta, block_h=req.study_result.get("block_h"))
    except Exception as e:
        raise HTTPException(500, f"Erreur Bloc K : {e}")
    if not result.get("available") and "error" in result:
        raise HTTPException(422, result["error"])
    return result


@router.post("/study/run")
def study_run(
    req: StudyRunRequest,
    current: Annotated[User, Depends(get_current_user)],
):
    """Run the complete (or partial) AMC study from a manifest.

    Returns a rich result dict covering the enabled blocks A/B/C/D + confidence.
    """
    try:
        return run_study(req.manifest, req.folder)
    except ValueError as e:
        raise HTTPException(422, str(e))
    except Exception as e:
        import traceback; traceback.print_exc()
        raise HTTPException(500, f"Erreur d'étude : {e}")


@router.post("/study/export-pdf")
def study_export_pdf(
    req: StudyExportRequest,
    current: Annotated[User, Depends(get_current_user)],
):
    """Generate the extended study report PDF (blocs A/B/C/D + confiance)."""
    try:
        pdf_bytes = generate_study_pdf(
            req.study_result,
            synthese_text=req.synthese_text,
            vag_result=req.vag_result,
            attribution_result=req.attribution_result,
            brinson_result=req.brinson_result if req.include_brinson else None,
            market_shocks_result=req.market_shocks_result if req.include_marketshocks else None,
            company_name=req.company_name,
            client_name=req.client_name,
            include_annexes=req.include_annexes,
        )
        isin = (req.study_result.get("meta") or {}).get("isin", "study")
        filename = f"AMC_Etude_{isin}_{__import__('datetime').date.today()}.pdf"
        return StreamingResponse(
            io.BytesIO(pdf_bytes),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as e:
        import traceback; traceback.print_exc()
        raise HTTPException(500, f"Erreur génération PDF étude : {e}")
