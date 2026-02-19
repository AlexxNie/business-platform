"""Business Platform - Universelle Business Object Engine.

API-first Platform zur dynamischen Erstellung von Business-Modulen.
Jedes Modul (CRM, CAFM, HR, ERP...) wird per API definiert und
automatisch als echte PostgreSQL-Tabelle angelegt.
"""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from app.config import get_settings
from app.database import async_engine, Base
from app.core.errors import PlatformError, ErrorResponse, ErrorDetail
from app.api.v1.schema import router as schema_router
from app.api.v1.data import router as data_router
from app.api.v1.introspect import router as introspect_router

logger = logging.getLogger(__name__)
settings = get_settings()

APP_DESCRIPTION = """\
## Universelle Business Object Platform

Definiere beliebige Business-Module (CRM, CAFM, HR, ERP...) per API.
Die Engine erstellt automatisch PostgreSQL-Tabellen, CRUD-Endpoints, Workflows und mehr.

### Fuer LLM-Agents: Empfohlene Reihenfolge

1. **`GET /api/v1/introspect/overview`** — Plattform-Status und alle existierenden Module/BOs abrufen
2. **`PUT /api/v1/schema/modules/{code}`** — Modul erstellen oder aktualisieren (idempotent)
3. **`PUT /api/v1/schema/definitions/{code}`** — BO-Definition erstellen oder aktualisieren (idempotent)
4. **`GET /api/v1/introspect/bo/{bo_code}`** — Detaillierte BO-Infos inkl. Beispiel-Payload abrufen
5. **`POST /api/v1/data/{bo_code}`** — Datensaetze erstellen
6. **`POST /api/v1/data/{bo_code}/{id}/transitions/{code}`** — Workflow-Transitions ausfuehren

### Idempotenz

PUT-Endpoints sind idempotent: Mehrfaches Ausfuehren mit gleichen Daten erzeugt keine Duplikate.
POST-Endpoints auf Schema-Ressourcen geben bei Duplikaten einen `409 Conflict` mit Hint auf PUT zurueck.

### Fehler-Format

Alle Fehler folgen einem einheitlichen Format:
```json
{
  "error": "conflict|validation|not_found|internal",
  "message": "Menschenlesbare Beschreibung",
  "details": [{"code": "FEHLER_CODE", "message": "...", "field": "...", "hint": "..."}]
}
```
"""


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create meta-tables on startup
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await async_engine.dispose()


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=APP_DESCRIPTION,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Global Exception Handlers ────────────────────────────

@app.exception_handler(PlatformError)
async def platform_error_handler(request: Request, exc: PlatformError):
    """Alle PlatformError-Subklassen → strukturierte JSON-Response."""
    return JSONResponse(
        status_code=exc.status_code,
        content=exc.to_response().to_dict(),
    )


@app.exception_handler(IntegrityError)
async def integrity_error_handler(request: Request, exc: IntegrityError):
    """SQLAlchemy IntegrityError → strukturierter 409 Conflict."""
    logger.warning(f"IntegrityError: {exc.orig}")
    detail_msg = str(exc.orig) if exc.orig else str(exc)

    # Unique-Constraint-Verletzung erkennen
    if "unique" in detail_msg.lower() or "duplicate" in detail_msg.lower():
        resp = ErrorResponse(
            error="conflict",
            message="A resource with this identifier already exists.",
            details=[ErrorDetail(
                code="DUPLICATE_RESOURCE",
                message=detail_msg,
                hint="Use the corresponding PUT endpoint to update existing resources.",
            )],
        )
        return JSONResponse(status_code=409, content=resp.to_dict())

    # FK-Constraint
    if "foreign key" in detail_msg.lower() or "violates foreign key" in detail_msg.lower():
        resp = ErrorResponse(
            error="validation",
            message="Referenced resource does not exist.",
            details=[ErrorDetail(
                code="INVALID_REFERENCE",
                message=detail_msg,
                hint="Check that the referenced ID exists before creating this record.",
            )],
        )
        return JSONResponse(status_code=422, content=resp.to_dict())

    # Check-Constraint (Enum, Email, etc.)
    if "check" in detail_msg.lower() or "violates check" in detail_msg.lower():
        resp = ErrorResponse(
            error="validation",
            message="Data violates a check constraint.",
            details=[ErrorDetail(
                code="CHECK_CONSTRAINT_VIOLATION",
                message=detail_msg,
                hint="Verify that enum values, email format, and other constraints are correct.",
            )],
        )
        return JSONResponse(status_code=422, content=resp.to_dict())

    # Fallback
    resp = ErrorResponse(
        error="conflict",
        message="Database constraint violation.",
        details=[ErrorDetail(code="INTEGRITY_ERROR", message=detail_msg)],
    )
    return JSONResponse(status_code=409, content=resp.to_dict())


# Mount API routers
app.include_router(schema_router, prefix="/api/v1")
app.include_router(data_router, prefix="/api/v1")
app.include_router(introspect_router, prefix="/api/v1")


@app.get("/", tags=["Health"],
         summary="Platform Info",
         description="Zeigt Basis-Infos und Endpoint-Uebersicht.")
async def root():
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "docs": "/docs",
        "endpoints": {
            "schema": "/api/v1/schema/definitions",
            "modules": "/api/v1/schema/modules",
            "data": "/api/v1/data/{bo_code}",
            "introspect": "/api/v1/introspect/overview",
            "introspect_bo": "/api/v1/introspect/bo/{bo_code}",
            "suggest": "/api/v1/introspect/suggest",
        },
    }


@app.get("/health", tags=["Health"],
         summary="Health Check",
         description="Einfacher Health-Check fuer Load Balancer / Monitoring.")
async def health():
    return {"status": "ok"}
