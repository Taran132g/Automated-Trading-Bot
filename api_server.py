"""QUANT_OS FastAPI server — serves REST API + WebSockets + React static build."""
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles

from routers import auth, terminal, analytics, paper, patterns, comparison, logs, admin, agents
from routers.config_router import router as config_router
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
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:5174", "http://localhost:4173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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
app.include_router(patterns.router, prefix="/api/patterns", tags=["patterns"])
app.include_router(comparison.router, prefix="/api/comparison", tags=["comparison"])
app.include_router(logs.router, prefix="/api/logs", tags=["logs"])
app.include_router(admin.router, prefix="/api/admin", tags=["admin"])
app.include_router(config_router, prefix="/api/config", tags=["config"])
app.include_router(agents.router, prefix="/api/agents", tags=["agents"])

# Serve React build in production
if STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
