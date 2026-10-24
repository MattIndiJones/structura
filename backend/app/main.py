import asyncio
import mimetypes
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from fastapi import FastAPI, Request, HTTPException

# Windows registry can have wrong MIME entries for .js/.css — force correct types
# so StaticFiles doesn't serve module scripts as text/plain (breaks ES modules).
mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("text/css", ".css")
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from .runtime import consultation_mode
from .core.document_uploads import DocumentUploadLimitMiddleware
from .api.pricing import router as pricing_router
from .api.volatility import router as volatility_router
from .api.ccr import router as ccr_router
from .api.inlife import router as inlife_router
from .api.market_data import router as market_data_router
from .api.simulation import router as simulation_router
from .api.scenarios import router as scenarios_router
from .api.schedule import router as schedule_router
from .api.auth import router as auth_router
from .api.folders import router as folders_router
from .api.clients import router as clients_router
from .api.persons import router as persons_router
from .api.opportunities import router as opportunities_router
from .api.interactions import router as interactions_router
from .api.client_intelligence import router as client_intelligence_router
from .api.client_import import router as client_import_router
from .api.constraint_definitions import router as constraint_definitions_router
from .api.scripts_db import router as scripts_db_router
from .api.variants import router as variants_router
from .api.deals import router as deals_router
from .api.valuation_notes import router as valuation_notes_router
from .api.portfolios import router as portfolios_router
from .api.shocks import router as shocks_router
from .api.indicatives import router as indicatives_router
from .api.kid import router as kid_router
from .api.emt import router as emt_router
from .api.documents import router as documents_router
from .api.amc import router as amc_router
from .api.amc_prices import router as amc_prices_router
from .api.amc_studies import router as amc_studies_router
from .api.fifo import router as fifo_router
from .api.rfq import router as rfq_router
from .api.rfq_desks import router as rfq_desks_router
from .api.rfq_relations import router as rfq_relations_router
from .api.rfq_inbox import router as rfq_inbox_router
from .api.rfq_transport import router as rfq_transport_router
from .api.rfq_reconciliation import router as rfq_reconciliation_router
from .api.admin import router as admin_router
from .api.alerts import router as alerts_router
from .api.compute import router as compute_router
from .api.var import router as var_router
from .api.products import router as products_router
from .api.product_optimizer import router as product_optimizer_router
from .api.trading import router as trading_router
from .api.agent_workshop import router as agent_workshop_router, admin_router as admin_agent_workshop_router
from .db.database import init_db
from .services.lifecycle_alerts import (
    SCHEDULER_TIMEZONE, configure_lifecycle_handlers,
    run_missed_refresh_if_needed, run_scheduled_refresh,
)
from .api.deals import refresh_deal_core, build_watchlist_row
from zoneinfo import ZoneInfo

app = FastAPI(
    title="Structura — PayScript Pricing Engine",
    description="Monte Carlo pricing engine for structured products",
    version="0.2.0",
)

app.add_middleware(DocumentUploadLimitMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[v.strip() for v in __import__("os").environ.get(
        "STRUCTURA_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173,http://localhost:8000,http://127.0.0.1:8000"
    ).split(",") if v.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from .hybrid.config import current_config as installation_config
from .hybrid.development import add_portal_cors
add_portal_cors(app, installation_config())

configure_lifecycle_handlers(refresh_deal_core, build_watchlist_row)

@app.middleware("http")
async def consultation_read_only(request: Request, call_next):
    if consultation_mode() and request.method not in {"GET", "HEAD", "OPTIONS"}:
        allowed = {"/api/auth/login", "/api/auth/logout", "/api/auth/logout-all", "/_instance/stop", "/_instance/consultation-session"}
        if request.url.path not in allowed:
            return JSONResponse(status_code=403, content={"detail":
                "Consultation en lecture seule : modification et recalcul désactivés."})
    return await call_next(request)


@app.on_event("startup")
def on_startup():
    init_db()
    if consultation_mode():
        from .services.agent_workshop.lease import CampaignLease
        directory = os.environ.get("STRUCTURA_CONSULTATION_LOCK_DIR")
        if not directory:
            raise RuntimeError("Dossier de verrouillage de consultation absent.")
        app.state.consultation_lease = CampaignLease(Path(directory))
        return
    from .services.optimizer_research import recover
    from .db.database import engine
    recover(engine)


@app.on_event("shutdown")
async def stop_optimizer_researches():
    if consultation_mode():
        lease = getattr(app.state, "consultation_lease", None)
        if lease:
            lease.close()
        return
    from .services.optimizer_research import shutdown
    await asyncio.to_thread(shutdown)
    from .services.agent_workshop.engine import manager
    await asyncio.to_thread(manager.shutdown)
    from .services.agent_workshop.consultation import consultations
    await asyncio.to_thread(consultations.shutdown)


# Daily lifecycle pass at 23:00 local — after the US close, since deal events
# are close-of-day observations and Yahoo only serves reliable closes. The
# provider controls decide whether a close can become official automatically.
# Safe as a plain in-process task: run.py runs a single worker
# with reload disabled, and run_scheduled_refresh() never raises.
@app.on_event("startup")
async def start_lifecycle_scheduler():
    if consultation_mode() or os.getenv("PYTEST_CURRENT_TEST") or os.getenv("STRUCTURA_DISABLE_SCHEDULER") == "1":
        return
    async def _daily_loop():
        await asyncio.to_thread(run_missed_refresh_if_needed)
        tz = ZoneInfo(SCHEDULER_TIMEZONE)
        while True:
            now = datetime.now(tz)
            next_run = now.replace(hour=23, minute=0, second=0, microsecond=0)
            if next_run <= now:
                next_run += timedelta(days=1)
            await asyncio.sleep((next_run - now).total_seconds())
            slot = next_run.astimezone(timezone.utc).replace(tzinfo=None)
            await asyncio.to_thread(run_scheduled_refresh, slot, "SCHEDULED")

    asyncio.create_task(_daily_loop())

app.include_router(inlife_router)
app.include_router(volatility_router)
app.include_router(ccr_router)
app.include_router(auth_router)
app.include_router(folders_router)
app.include_router(clients_router)
app.include_router(persons_router)
app.include_router(opportunities_router)
app.include_router(interactions_router)
app.include_router(client_intelligence_router)
app.include_router(client_import_router)
app.include_router(constraint_definitions_router)
app.include_router(scripts_db_router)
app.include_router(variants_router)
app.include_router(deals_router)
app.include_router(valuation_notes_router)
app.include_router(portfolios_router)
app.include_router(shocks_router)
app.include_router(indicatives_router)
app.include_router(kid_router)
app.include_router(emt_router)
app.include_router(documents_router)
app.include_router(amc_router)
app.include_router(amc_prices_router)
app.include_router(amc_studies_router)
app.include_router(fifo_router)
app.include_router(rfq_router)
app.include_router(rfq_desks_router)
app.include_router(rfq_relations_router)
app.include_router(rfq_inbox_router)
app.include_router(rfq_transport_router)
app.include_router(rfq_reconciliation_router)
app.include_router(admin_router)
app.include_router(alerts_router)
app.include_router(compute_router)
app.include_router(var_router)
app.include_router(products_router)
app.include_router(product_optimizer_router)
app.include_router(trading_router)
app.include_router(agent_workshop_router)
app.include_router(admin_agent_workshop_router)
app.include_router(pricing_router)
app.include_router(market_data_router)
app.include_router(simulation_router)
app.include_router(scenarios_router)
app.include_router(schedule_router)


@app.on_event("startup")
async def start_rfq_transport():
    if consultation_mode() or os.getenv("PYTEST_CURRENT_TEST") or os.getenv("STRUCTURA_DISABLE_RFQ_TRANSPORT") == "1":
        return
    from .db.database import engine
    from .services.rfq_transport import process_pending
    app.state.rfq_transport_stop = asyncio.Event()
    async def run():
        while not app.state.rfq_transport_stop.is_set():
            try:
                await asyncio.to_thread(process_pending, engine, app.state.rfq_transport_stop.is_set)
            except Exception:
                import logging
                logging.getLogger(__name__).error("Cycle de transport RFQ interrompu ; reprise au cycle suivant")
            try:
                await asyncio.wait_for(app.state.rfq_transport_stop.wait(), timeout=2)
            except asyncio.TimeoutError:
                pass
    app.state.rfq_transport_task = asyncio.create_task(run())


@app.on_event("shutdown")
async def stop_rfq_transport():
    task = getattr(app.state, "rfq_transport_task", None)
    if task:
        app.state.rfq_transport_stop.set()
        await task

DIST = Path(__file__).parent.parent.parent / "frontend" / "dist"


@app.get("/health")
async def health():
    result = {"status": "ok", "version": "0.1.0"}
    if os.environ.get("STRUCTURA_INSTANCE_ID"):
        result.update(instance_id=os.environ["STRUCTURA_INSTANCE_ID"], process_id=os.getpid())
    if os.environ.get("STRUCTURA_BOOTSTRAP_PROFILE") == "admin_workbench":
        result.update(kind="admin_workbench", launch_id=os.environ.get("STRUCTURA_LAUNCH_ID"),
                      developer_access=os.environ.get("STRUCTURA_DEVELOPER_ACCESS") == "1")
    from .hybrid.config import current_config
    config = current_config()
    if config:
        from .hybrid.development import enabled
        result.update(instance_id=str(config.installation_id), process_id=os.getpid(),
                      launch_id=os.environ.get("STRUCTURA_LAUNCH_ID"), kind=config.kind,
                      registry_state=config.registry_state, developer_access=enabled(config))
    if consultation_mode():
        result["read_only"] = True
    return result


@app.post("/_instance/stop", include_in_schema=False)
async def stop_owned_instance(request: Request):
    import secrets
    expected = os.environ.get("STRUCTURA_INSTANCE_CONTROL_TOKEN", "")
    supplied = request.headers.get("X-Instance-Control", "")
    if not expected or not secrets.compare_digest(expected, supplied):
        raise HTTPException(404, "Not found")
    server = getattr(app.state, "instance_server", None)
    if server is None:
        raise HTTPException(409, "Instance not managed")
    server.should_exit = True
    return {"stopping": True}


@app.post("/_instance/consultation-session", include_in_schema=False)
async def consultation_session(request: Request):
    import secrets
    from sqlmodel import Session
    from .db.database import engine
    from .db.models import User
    from .api.auth import _make_token
    expected = os.environ.get("STRUCTURA_INSTANCE_CONTROL_TOKEN", "")
    if not consultation_mode() or not expected or not secrets.compare_digest(
            expected, request.headers.get("X-Instance-Control", "")):
        raise HTTPException(404, "Not found")
    with Session(engine) as session:
        from .core.consultation_sessions import load_user
        user = load_user(session, user_id=int(os.environ["STRUCTURA_CONSULTATION_USER_ID"]))
        if not user or not user.is_active:
            raise HTTPException(409, "Le compte sauvegardé de cet acteur est indisponible.")
        return {"access_token": _make_token(user.id, user.role, user.entity_id, auth_version=user.auth_version), "token_type": "bearer"}


if DIST.exists():
    app.mount("/assets", StaticFiles(directory=str(DIST / "assets")), name="assets")

    @app.get("/tp_logo.png")
    async def tp_logo_png():
        return FileResponse(str(DIST / "tp_logo.png"), media_type="image/png")

    @app.get("/")
    async def root():
        # `no-cache` = revalider avant de servir, PAS « ne pas stocker » : le
        # navigateur garde le fichier et ne redemande qu'un 304, donc le coût
        # est nul. Sans cet en-tête, FileResponse n'envoie qu'un ETag et un
        # Last-Modified, et le navigateur applique sa mise en cache
        # HEURISTIQUE — il garde index.html plusieurs minutes de son propre
        # chef. Il pointe alors sur des bundles à empreinte que le build
        # suivant a supprimés : l'écran affiche l'ancienne version, ou rien.
        # C'est ce qui imposait un Ctrl+Shift+R après chaque `npm run build`.
        # Les fichiers de /assets, eux, portent leur empreinte dans leur nom et
        # peuvent rester en cache indéfiniment — on ne touche pas à leur mount.
        return FileResponse(str(DIST / "index.html"),
                            headers={"Cache-Control": "no-cache"})
