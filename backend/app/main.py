"""Punto de entrada de la API de Flock Planner."""

import logging

from fastapi import APIRouter, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api import backlog, documents, exports, integrations, plans, projects, requirements, scenarios, team
from app.config import get_settings
from app.db import engine
from app.errors import install_error_handlers
from app.schemas import SystemStatus

VERSION = "0.1.0"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

settings = get_settings()
app = FastAPI(
    title="Flock Planner API",
    version=VERSION,
    description="Planificación inteligente de proyectos: requisitos, backlog, estimación, planificación, "
                "escenarios de equipo, PDF e integración opcional con JIRA.",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)
install_error_handlers(app)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Content-Type", "X-PM-User"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    return response


system = APIRouter(tags=["Sistema"])


@system.get("/health")
def health():
    return {"status": "ok"}


@system.get("/system/status", response_model=SystemStatus)
def system_status():
    db_ok = True
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001
        db_ok = False
    s = get_settings()
    provider = s.resolved_ai_provider
    available = provider == "demo"
    model = "demo-heuristico" if provider == "demo" else ""
    if provider == "claude_code":
        from app.ai.claude_code import find_claude_cli

        available = find_claude_cli(s.claude_code_path) is not None
        model = s.claude_code_model or "modelo por defecto de Claude Code"
    return SystemStatus(
        ai_provider=provider,
        ai_model=model,
        app_env=s.app_env,
        database=engine.dialect.name,
        database_ok=db_ok,
        ai_demo_mode=provider == "demo",
        ai_available=available,
        secrets_encryption_configured=bool(s.secrets_encryption_key),
        version=VERSION,
    )


for r in (system, projects.router, requirements.router, documents.router, backlog.router, team.router, plans.router,
          scenarios.router, exports.router, integrations.router):
    app.include_router(r, prefix="/api/v1")
