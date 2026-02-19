"""Schema API - BO-Definitionen verwalten (das "TSI" der Plattform).

Hier werden Business Objects definiert, Felder hinzugefuegt,
Workflows konfiguriert - alles per REST API.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.schemas.bo_definition import (
    BODefinitionCreate, BODefinitionResponse, BODefinitionList,
    FieldCreate, FieldResponse,
)
from app.schemas.module import ModuleCreate, ModuleResponse, ModuleUpdate
from app.services import schema_service
from app.models.module import Module
from app.core.errors import ConflictError, NotFoundError, ErrorDetail, PlatformError

router = APIRouter(prefix="/schema", tags=["Schema (TSI)"])


# ── Modules ──────────────────────────────────────────────

@router.post(
    "/modules",
    response_model=ModuleResponse,
    status_code=201,
    summary="Modul erstellen",
    description="Erstellt ein neues Modul. Bei Duplikat: 409 mit Hint auf PUT.",
    responses={
        409: {"description": "Modul existiert bereits — nutze PUT /schema/modules/{code}"},
    },
)
async def create_module(data: ModuleCreate, db: AsyncSession = Depends(get_db)):
    # Duplikat-Check
    result = await db.execute(select(Module).where(Module.code == data.code))
    if result.scalar_one_or_none():
        raise ConflictError(
            f"Module '{data.code}' already exists.",
            details=[ErrorDetail(
                code="DUPLICATE_MODULE",
                message=f"A module with code '{data.code}' already exists.",
                field="code",
                hint=f"Use PUT /api/v1/schema/modules/{data.code} to update it.",
            )],
        )

    module = Module(code=data.code, name=data.name, description=data.description, icon=data.icon)
    db.add(module)
    await db.commit()
    await db.refresh(module)
    return module


@router.put(
    "/modules/{code}",
    response_model=ModuleResponse,
    summary="Modul erstellen oder aktualisieren (idempotent)",
    description=(
        "Erstellt ein Modul oder aktualisiert es, wenn es bereits existiert. "
        "Idempotent: Mehrfaches Ausfuehren mit gleichen Daten ist sicher."
    ),
)
async def upsert_module(code: str, data: ModuleCreate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Module).where(Module.code == code))
    module = result.scalar_one_or_none()

    if module:
        # Update existing
        module.name = data.name
        if data.description is not None:
            module.description = data.description
        if data.icon is not None:
            module.icon = data.icon
        await db.commit()
        await db.refresh(module)
        return module

    # Create new
    module = Module(code=code, name=data.name, description=data.description, icon=data.icon)
    db.add(module)
    await db.commit()
    await db.refresh(module)
    return module


@router.get(
    "/modules",
    response_model=list[ModuleResponse],
    summary="Alle Module auflisten",
    description="Gibt alle Module sortiert nach Code zurueck.",
)
async def list_modules(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Module).order_by(Module.code))
    return result.scalars().all()


@router.patch(
    "/modules/{code}",
    response_model=ModuleResponse,
    summary="Modul teilweise aktualisieren",
    description="Aktualisiert nur die uebergebenen Felder.",
    responses={404: {"description": "Modul nicht gefunden"}},
)
async def update_module(code: str, data: ModuleUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Module).where(Module.code == code))
    module = result.scalar_one_or_none()
    if not module:
        raise NotFoundError(
            f"Module '{code}' not found.",
            details=[ErrorDetail(
                code="MODULE_NOT_FOUND",
                message=f"Module '{code}' does not exist.",
                hint=f"Use PUT /api/v1/schema/modules/{code} to create it.",
            )],
        )
    for key, val in data.model_dump(exclude_unset=True).items():
        setattr(module, key, val)
    await db.commit()
    await db.refresh(module)
    return module


# ── BO Definitions ───────────────────────────────────────

@router.post(
    "/definitions",
    response_model=BODefinitionResponse,
    status_code=201,
    summary="BO-Definition erstellen",
    description=(
        "Erstellt eine neue BO-Definition und die zugehoerige PostgreSQL-Tabelle. "
        "Bei Duplikat: 409 mit Hint auf PUT."
    ),
    responses={
        409: {"description": "BO existiert bereits — nutze PUT /schema/definitions/{code}"},
        404: {"description": "Referenziertes Modul nicht gefunden"},
    },
)
async def create_bo_definition(data: BODefinitionCreate, db: AsyncSession = Depends(get_db)):
    bo_def = await schema_service.create_bo_definition(db, data.model_dump())
    return bo_def


@router.put(
    "/definitions/{code}",
    response_model=BODefinitionResponse,
    summary="BO-Definition erstellen oder aktualisieren (idempotent)",
    description=(
        "Erstellt eine BO-Definition oder aktualisiert sie, wenn sie bereits existiert. "
        "Bestehende Felder werden NICHT entfernt. Neue Felder werden via ALTER TABLE hinzugefuegt. "
        "Idempotent: Mehrfaches Ausfuehren mit gleichen Daten ist sicher."
    ),
)
async def upsert_bo_definition(code: str, data: BODefinitionCreate, db: AsyncSession = Depends(get_db)):
    bo_def, created = await schema_service.upsert_bo_definition(db, code, data.model_dump())
    return bo_def


@router.get(
    "/definitions",
    response_model=list[BODefinitionList],
    summary="Alle BO-Definitionen auflisten",
    description="Gibt alle BO-Definitionen zurueck, optional gefiltert nach Modul.",
)
async def list_bo_definitions(
    module: str | None = Query(None, description="Filter nach Modul-Code"),
    db: AsyncSession = Depends(get_db),
):
    defs = await schema_service.list_bo_definitions(db, module)
    return [
        BODefinitionList(
            id=d.id,
            code=d.code,
            name=d.name,
            table_name=d.table_name,
            is_active=d.is_active,
            table_created=d.table_created,
            field_count=len(d.fields),
        )
        for d in defs
    ]


@router.get(
    "/definitions/{code}",
    response_model=BODefinitionResponse,
    summary="BO-Definition abrufen",
    description="Gibt eine BO-Definition mit allen Feld-Definitionen zurueck.",
    responses={404: {"description": "BO-Definition nicht gefunden"}},
)
async def get_bo_definition(code: str, db: AsyncSession = Depends(get_db)):
    bo_def = await schema_service.get_bo_definition(db, code)
    if not bo_def:
        raise NotFoundError(
            f"BO definition '{code}' not found.",
            details=[ErrorDetail(
                code="BO_NOT_FOUND",
                message=f"BO definition '{code}' does not exist.",
                hint="Use GET /api/v1/schema/definitions to list all available BOs.",
            )],
        )
    return bo_def


@router.delete(
    "/definitions/{code}",
    status_code=204,
    summary="BO-Definition loeschen",
    description="Loescht eine BO-Definition und die zugehoerige PostgreSQL-Tabelle.",
    responses={404: {"description": "BO-Definition nicht gefunden"}},
)
async def delete_bo_definition(code: str, db: AsyncSession = Depends(get_db)):
    await schema_service.delete_bo_definition(db, code)


# ── Fields ───────────────────────────────────────────────

@router.post(
    "/definitions/{code}/fields",
    response_model=FieldResponse,
    status_code=201,
    summary="Feld zu BO hinzufuegen",
    description=(
        "Fuegt ein neues Feld zu einer BO-Definition hinzu (ALTER TABLE ADD COLUMN). "
        "Idempotent: Existiert das Feld mit gleichem Typ, wird es zurueckgegeben."
    ),
    responses={
        409: {"description": "Feld existiert mit anderem Typ"},
        404: {"description": "BO-Definition nicht gefunden"},
    },
)
async def add_field(code: str, data: FieldCreate, db: AsyncSession = Depends(get_db)):
    field, created = await schema_service.add_field_to_bo(db, code, data.model_dump())
    return field


@router.delete(
    "/definitions/{code}/fields/{field_code}",
    status_code=204,
    summary="Feld von BO entfernen",
    description="Entfernt ein Feld aus der BO-Definition (ALTER TABLE DROP COLUMN).",
    responses={404: {"description": "BO oder Feld nicht gefunden"}},
)
async def remove_field(code: str, field_code: str, db: AsyncSession = Depends(get_db)):
    await schema_service.remove_field_from_bo(db, code, field_code)


# ── Table Info (TSI View) ────────────────────────────────

@router.get(
    "/definitions/{code}/table-info",
    summary="DB-Tabellenstruktur abrufen",
    description=(
        "Zeigt die tatsaechliche PostgreSQL-Tabellenstruktur hinter einem BO. "
        "Nuetzlich zum Debugging und fuer TSI-Ansichten."
    ),
    responses={404: {"description": "BO-Definition nicht gefunden"}},
)
async def get_table_info(code: str, db: AsyncSession = Depends(get_db)):
    return await schema_service.get_table_info(db, code)
