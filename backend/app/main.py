from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from .api.pricing import router as pricing_router
from .api.market_data import router as market_data_router
from .api.simulation import router as simulation_router
from .api.scenarios import router as scenarios_router
from .api.schedule import router as schedule_router
from .api.auth import router as auth_router
from .api.folders import router as folders_router
from .api.scripts_db import router as scripts_db_router
from .api.deals import router as deals_router
from .api.kid import router as kid_router
from .api.documents import router as documents_router
from .api.amc import router as amc_router
from .api.amc_prices import router as amc_prices_router
from .api.amc_studies import router as amc_studies_router
from .api.fifo import router as fifo_router
from .db.database import init_db

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

app.include_router(auth_router)
app.include_router(folders_router)
app.include_router(scripts_db_router)
app.include_router(deals_router)
app.include_router(kid_router)
app.include_router(documents_router)
app.include_router(amc_router)
app.include_router(amc_prices_router)
app.include_router(amc_studies_router)
app.include_router(fifo_router)
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
        return FileResponse(str(DIST / "index.html"))
