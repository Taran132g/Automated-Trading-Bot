"""QUANT_OS FastAPI server — serves REST API + WebSockets + React static build."""
import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from routers import auth, terminal, analytics, paper, comparison, logs, admin, agents
from routers.config_router import router as config_router
from routers.market import router as market_router
from routers.signals import router as signals_router
from routers.screener import router as screener_router
from routers.telegram import router as telegram_router
from ws_manager import terminal_broadcast_loop

STATIC_DIR = Path(__file__).parent / "quant-os-ui" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(terminal_broadcast_loop())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="QUANT_OS API", lifespan=lifespan)

app.add_middleware(GZipMiddleware, minimum_size=1000)

# Local dev origins + any extra origins (e.g. the Vercel showcase) via env.
_DEFAULT_ORIGINS = ["http://localhost:5173", "http://localhost:5174", "http://localhost:4173"]
_EXTRA_ORIGINS = [o.strip() for o in os.environ.get("EXTRA_CORS_ORIGINS", "").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_DEFAULT_ORIGINS + _EXTRA_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Read-only public mode: when API_READONLY=1 (set on the public Oracle box),
# reject every mutating request so the exposed surface is view-only. Read
# endpoints need no auth, so the showcase still works; config/admin writes 403.
_READONLY = os.environ.get("API_READONLY") == "1"
_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


@app.middleware("http")
async def enforce_readonly(request: Request, call_next):
    if _READONLY and request.method not in _SAFE_METHODS:
        return JSONResponse(status_code=403, content={"detail": "read-only public instance"})
    return await call_next(request)


@app.middleware("http")
async def cache_static_assets(request: Request, call_next):
    response = await call_next(request)
    path = request.url.path
    if path.startswith("/assets/"):
        # Content-hashed filenames can be cached indefinitely
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    elif path == "/" or path == "/index.html" or (not path.startswith("/api") and not path.startswith("/assets")):
        # HTML (SPA shell) must not be cached — browser must always revalidate
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
    return response

# API routes
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(terminal.router, prefix="/api/terminal", tags=["terminal"])
app.include_router(analytics.router, prefix="/api/analytics", tags=["analytics"])
app.include_router(paper.router, prefix="/api/paper", tags=["paper"])
app.include_router(comparison.router, prefix="/api/comparison", tags=["comparison"])
app.include_router(logs.router, prefix="/api/logs", tags=["logs"])
app.include_router(admin.router, prefix="/api/admin", tags=["admin"])
app.include_router(config_router, prefix="/api/config", tags=["config"])
app.include_router(agents.router, prefix="/api/agents", tags=["agents"])
app.include_router(market_router, prefix="/api/market", tags=["market"])
app.include_router(signals_router)
app.include_router(screener_router)
app.include_router(telegram_router)

# Serve React build in production
if STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
