"""Data API - Dynamische CRUD-Endpunkte fuer alle Business Objects.

Ein einziger Router bedient ALLE BO-Typen:
  GET    /data/{bo_code}          -> Liste mit Filter/Sort/Pagination
  POST   /data/{bo_code}          -> Neuen Datensatz erstellen
  GET    /data/{bo_code}/{id}     -> Einzelnen Datensatz lesen
  PUT    /data/{bo_code}/{id}     -> Datensatz aktualisieren
  DELETE /data/{bo_code}/{id}     -> Datensatz loeschen
  POST   /data/{bo_code}/{id}/transitions/{code} -> Workflow-Transition
  GET    /data/{bo_code}/{id}/transitions -> Verfuegbare Transitions
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.schema_service import get_bo_definition
from app.core.query_engine import (
    query_bo_table, get_bo_record, insert_bo_record,
    update_bo_record, delete_bo_record,
)
from app.core.workflow_engine import (
    get_available_transitions, execute_transition, WorkflowError,
)

router = APIRouter(prefix="/data", tags=["Data (CRUD)"])


async def _resolve_bo(code: str, db: AsyncSession):
    """Resolve BO code to definition, raise 404 if not found."""
    bo_def = await get_bo_definition(db, code)
    if not bo_def or not bo_def.table_created:
        raise HTTPException(404, f"Business Object '{code}' not found or table not created")
    return bo_def


@router.get("/{bo_code}")
async def list_records(bo_code: str, request: Request, db: AsyncSession = Depends(get_db)):
    """List records with filtering, sorting and pagination.

    Query params:
    - field=value (exact match)
    - field__contains=value (ILIKE)
    - field__gt=value, field__lt=value, etc.
    - sort=-field1,field2 (prefix - for DESC)
    - page=1&page_size=20
    - fields=id,name,status (field selection)
    """
    bo_def = await _resolve_bo(bo_code, db)
    params = dict(request.query_params)
    return await query_bo_table(db, bo_def.table_name, params)


@router.post("/{bo_code}", status_code=201)
async def create_record(bo_code: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Create a new record. Body = JSON with field values."""
    bo_def = await _resolve_bo(bo_code, db)
    body = await request.json()

    # Set initial workflow state if workflow exists
    if bo_def.workflow and "_state" not in body:
        body["_state"] = bo_def.workflow.initial_state

    # Validate fields exist
    valid_fields = {f.code for f in bo_def.fields}
    system_fields = {"_state", "_notes", "_created_by"}
    for key in body:
        if key not in valid_fields and key not in system_fields:
            raise HTTPException(400, f"Unknown field: '{key}'. Valid: {sorted(valid_fields)}")

    try:
        return await insert_bo_record(db, bo_def.table_name, body)
    except Exception as e:
        raise HTTPException(400, str(e))


@router.get("/{bo_code}/{record_id}")
async def get_record(bo_code: str, record_id: int, db: AsyncSession = Depends(get_db)):
    """Get a single record by ID."""
    bo_def = await _resolve_bo(bo_code, db)
    record = await get_bo_record(db, bo_def.table_name, record_id)
    if not record:
        raise HTTPException(404, f"{bo_code}#{record_id} not found")
    return record


@router.put("/{bo_code}/{record_id}")
async def update_record(
    bo_code: str, record_id: int, request: Request, db: AsyncSession = Depends(get_db)
):
    """Update a record. Body = JSON with fields to update."""
    bo_def = await _resolve_bo(bo_code, db)
    body = await request.json()

    # Don't allow direct state changes (use transitions)
    if "_state" in body and bo_def.workflow:
        raise HTTPException(
            400, "Use POST /{bo_code}/{id}/transitions/{code} to change state"
        )

    record = await update_bo_record(db, bo_def.table_name, record_id, body)
    if not record:
        raise HTTPException(404, f"{bo_code}#{record_id} not found")
    return record


@router.delete("/{bo_code}/{record_id}", status_code=204)
async def delete_record(bo_code: str, record_id: int, db: AsyncSession = Depends(get_db)):
    """Delete a record."""
    bo_def = await _resolve_bo(bo_code, db)
    deleted = await delete_bo_record(db, bo_def.table_name, record_id)
    if not deleted:
        raise HTTPException(404, f"{bo_code}#{record_id} not found")


# ── Workflow Transitions ─────────────────────────────────

@router.get("/{bo_code}/{record_id}/transitions")
async def list_transitions(
    bo_code: str, record_id: int, db: AsyncSession = Depends(get_db)
):
    """Get available workflow transitions for a record."""
    bo_def = await _resolve_bo(bo_code, db)
    if not bo_def.workflow:
        raise HTTPException(400, f"{bo_code} has no workflow defined")

    record = await get_bo_record(db, bo_def.table_name, record_id)
    if not record:
        raise HTTPException(404, f"{bo_code}#{record_id} not found")

    return await get_available_transitions(db, bo_def.id, record.get("_state"))


@router.post("/{bo_code}/{record_id}/transitions/{transition_code}")
async def execute_workflow_transition(
    bo_code: str, record_id: int, transition_code: str,
    db: AsyncSession = Depends(get_db),
):
    """Execute a workflow transition on a record."""
    bo_def = await _resolve_bo(bo_code, db)
    if not bo_def.workflow:
        raise HTTPException(400, f"{bo_code} has no workflow defined")

    try:
        return await execute_transition(
            db, bo_def.id, bo_def.table_name, record_id, transition_code
        )
    except WorkflowError as e:
        raise HTTPException(400, str(e))
