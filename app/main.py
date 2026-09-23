import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.api.deps import DB
from app.api.v1.router import router
from app.core.config import get_settings
from app.db.session import get_engine

logger = logging.getLogger("kpi")
DASHBOARD_DIR = Path(__file__).resolve().parents[1] / "dashboard"


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    get_engine().dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="KPI Command Center",
        version="0.1.0",
        description="Operaciones ATM, sucursales y planificación geoespacial. Importes en DOP.",
        docs_url="/docs" if settings.app_env != "production" else None,
        redoc_url="/redoc" if settings.app_env != "production" else None,
        openapi_url="/openapi.json" if settings.app_env != "production" else None,
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
        expose_headers=["X-Request-ID"],
    )
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.trusted_hosts)

    @app.middleware("http")
    async def headers(request: Request, call_next):
        request.state.request_id = str(uuid4())
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        # No devolver input ni ctx: pueden contener contraseñas u objetos no serializables.
        errors = [{"loc": e["loc"], "msg": e["msg"], "type": e["type"]} for e in exc.errors()]
        return JSONResponse(status_code=422, content={"detail": errors})

    @app.exception_handler(IntegrityError)
    async def integrity_error(request: Request, exc: IntegrityError):
        code = getattr(exc.orig, "pgcode", None)
        status, message = (
            (409, "Ya existe un registro con esa clave")
            if code == "23505"
            else (422, "El registro incumple una relación o restricción de datos")
        )
        logger.warning(
            "Restricción de datos: request_id=%s sqlstate=%s", request.state.request_id, code
        )
        return JSONResponse(status_code=status, content={"detail": message})

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request: Request, exc: SQLAlchemyError):
        logger.error(
            "Fallo de base de datos: request_id=%s type=%s",
            request.state.request_id,
            type(exc).__name__,
        )
        return JSONResponse(
            status_code=503, content={"detail": "Base de datos temporalmente no disponible"}
        )

    @app.get("/health/live", tags=["Salud"])
    def live():
        return {"status": "ok"}

    @app.get("/health/ready", tags=["Salud"])
    def ready(db: DB):
        db.execute(text("SELECT 1"))
        version = db.execute(text("SELECT version_num FROM alembic_version")).scalar_one_or_none()
        if version != "0004_job_runs":
            return JSONResponse(status_code=503, content={"status": "migration_required"})
        return {"status": "ready", "migration": version}

    @app.get("/", include_in_schema=False)
    def home():
        return RedirectResponse("/dashboard/")

    @app.get("/dashboard/config.js", include_in_schema=False)
    def dashboard_config():
        payload = {
            "apiBase": "/api/v1",
            "googleMapsApiKey": settings.google_maps_api_key,
            "googleMapsLibraries": [],
        }
        return Response(
            "window.KPI_CONFIG = " + json.dumps(payload) + ";",
            media_type="application/javascript",
        )

    app.include_router(router)
    app.mount("/dashboard", StaticFiles(directory=DASHBOARD_DIR, html=True), name="dashboard")
    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=5000)
