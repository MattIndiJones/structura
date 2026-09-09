import asyncio
import mimetypes
from datetime import datetime, timedelta
from pathlib import Path
from fastapi import FastAPI

# Windows registry can have wrong MIME entries for .js/.css — force correct types
# so StaticFiles doesn't serve module scripts as text/plain (breaks ES modules).
mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("text/css", ".css")
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from .api.pricing import router as pricing_router
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
from .api.admin import router as admin_router
from .api.alerts import router as alerts_router
from .api.compute import router as compute_router
from .api.var import router as var_router
from .db.database import init_db
from .services.lifecycle_alerts import run_scheduled_refresh

app = FastAPI(
    title="Structura — PayScript Pricing Engine",
    description="Monte Carlo pricing engine for structured products",
    version="0.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def on_startup():
    init_db()


# Daily lifecycle pass at 23:00 local — after the US close, since deal events
# are close-of-day observations and Yahoo only serves reliable closes. The
# fixing policy frozen on each deal decides whether the pass is automatic or
# proposal-only. Safe as a plain in-process task: run.py runs a single worker
# with reload disabled, and run_scheduled_refresh() never raises.
@app.on_event("startup")
async def start_lifecycle_scheduler():
    async def _daily_loop():
        while True:
            now = datetime.now()
            next_run = now.replace(hour=23, minute=0, second=0, microsecond=0)
            if next_run <= now:
                next_run += timedelta(days=1)
            await asyncio.sleep((next_run - now).total_seconds())
            await asyncio.to_thread(run_scheduled_refresh)

    asyncio.create_task(_daily_loop())

app.include_router(inlife_router)
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
app.include_router(admin_router)
app.include_router(alerts_router)
app.include_router(compute_router)
app.include_router(var_router)
app.include_router(pricing_router)
app.include_router(market_data_router)
app.include_router(simulation_router)
app.include_router(scenarios_router)
app.include_router(schedule_router)

DIST = Path(__file__).parent.parent.parent / "frontend" / "dist"


@app.get("/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}


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
