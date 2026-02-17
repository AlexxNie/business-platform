"""Schema API - BO-Definitionen verwalten (das "TSI" der Plattform).

Hier werden Business Objects definiert, Felder hinzugefuegt,
Workflows konfiguriert - alles per REST API.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.bo_definition import (
    BODefinitionCreate, BODefinitionResponse, BODefinitionList,
    FieldCreate, FieldResponse,
)
from app.schemas.module import ModuleCreate, ModuleResponse, ModuleUpdate
from app.services import schema_service
from app.models.module import Module
from sqlalchemy import select

router = APIRouter(prefix="/schema", tags=["Schema (TSI)"])


# ── Modules ──────────────────────────────────────────────

@router.post("/modules", response_model=ModuleResponse, status_code=201)
async def create_module(data: ModuleCreate, db: AsyncSession = Depends(get_db)):
    """Create a new module (e.g. CRM, CAFM, HR)."""
    module = Module(code=data.code, name=data.name, description=data.description, icon=data.icon)
    db.add(module)
    await db.commit()
    await db.refresh(module)
    return module


@router.get("/modules", response_model=list[ModuleResponse])
async def list_modules(db: AsyncSession = Depends(get_db)):
    """List all modules."""
    result = await db.execute(select(Module).order_by(Module.code))
    return result.scalars().all()


@router.patch("/modules/{code}", response_model=ModuleResponse)
async def update_module(code: str, data: ModuleUpdate, db: AsyncSession = Depends(get_db)):
    """Update a module."""
    result = await db.execute(select(Module).where(Module.code == code))
    module = result.scalar_one_or_none()
    if not module:
        raise HTTPException(404, f"Module '{code}' not found")
    for key, val in data.model_dump(exclude_unset=True).items():
        setattr(module, key, val)
    await db.commit()
    await db.refresh(module)
    return module


# ── BO Definitions ───────────────────────────────────────

@router.post("/definitions", response_model=BODefinitionResponse, status_code=201)
async def create_bo_definition(data: BODefinitionCreate, db: AsyncSession = Depends(get_db)):
    """Create a new Business Object definition + database table.

    This is the core operation: Define a BO type and the platform
    automatically creates a real PostgreSQL table for it.
    """
    try:
        bo_def = await schema_service.create_bo_definition(db, data.model_dump())
        return bo_def
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/definitions", response_model=list[BODefinitionList])
async def list_bo_definitions(
    module: str | None = Query(None, description="Filter by module code"),
    db: AsyncSession = Depends(get_db),
):
    """List all BO definitions, optionally filtered by module."""
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


@router.get("/definitions/{code}", response_model=BODefinitionResponse)
async def get_bo_definition(code: str, db: AsyncSession = Depends(get_db)):
    """Get a BO definition with all field definitions."""
    bo_def = await schema_service.get_bo_definition(db, code)
    if not bo_def:
        raise HTTPException(404, f"BO definition '{code}' not found")
    return bo_def


@router.delete("/definitions/{code}", status_code=204)
async def delete_bo_definition(code: str, db: AsyncSession = Depends(get_db)):
    """Delete a BO definition and drop its database table."""
    try:
        await schema_service.delete_bo_definition(db, code)
    except ValueError as e:
        raise HTTPException(404, str(e))


# ── Fields ───────────────────────────────────────────────

@router.post("/definitions/{code}/fields", response_model=FieldResponse, status_code=201)
async def add_field(code: str, data: FieldCreate, db: AsyncSession = Depends(get_db)):
    """Add a new field to an existing BO definition (ALTER TABLE ADD COLUMN)."""
    try:
        field = await schema_service.add_field_to_bo(db, code, data.model_dump())
        return field
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.delete("/definitions/{code}/fields/{field_code}", status_code=204)
async def remove_field(code: str, field_code: str, db: AsyncSession = Depends(get_db)):
    """Remove a field from a BO definition (ALTER TABLE DROP COLUMN)."""
    try:
        await schema_service.remove_field_from_bo(db, code, field_code)
    except ValueError as e:
        raise HTTPException(400, str(e))


# ── Table Info (TSI View) ────────────────────────────────

@router.get("/definitions/{code}/table-info")
async def get_table_info(code: str, db: AsyncSession = Depends(get_db)):
    """Get actual database table information (columns, types, constraints).

    This is the TSI-equivalent: shows the real DB structure behind a BO.
    """
    try:
        return await schema_service.get_table_info(db, code)
    except ValueError as e:
        raise HTTPException(404, str(e))
