"""Business Platform - Universelle Business Object Engine.

API-first Platform zur dynamischen Erstellung von Business-Modulen.
Jedes Modul (CRM, CAFM, HR, ERP...) wird per API definiert und
automatisch als echte PostgreSQL-Tabelle angelegt.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database import async_engine, Base
from app.api.v1.schema import router as schema_router
from app.api.v1.data import router as data_router
from app.api.v1.introspect import router as introspect_router

settings = get_settings()


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
    description=(
        "Universelle Business Object Platform. "
        "Definiere Module (CRM, CAFM, HR...) per API, "
        "die Engine erstellt automatisch DB-Tabellen, "
        "CRUD-Endpoints, Workflows und mehr."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount API routers
app.include_router(schema_router, prefix="/api/v1")
app.include_router(data_router, prefix="/api/v1")
app.include_router(introspect_router, prefix="/api/v1")


@app.get("/", tags=["Health"])
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
            "suggest": "/api/v1/introspect/suggest",
        },
    }


@app.get("/health", tags=["Health"])
async def health():
    return {"status": "ok"}
