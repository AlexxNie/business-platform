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

from fastapi import APIRouter, Depends, Request
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
from app.core.data_validator import validate_record_data
from app.core.errors import NotFoundError, ValidationError, ErrorDetail, PlatformError

router = APIRouter(prefix="/data", tags=["Data (CRUD)"])


async def _resolve_bo(code: str, db: AsyncSession):
    """Resolve BO code to definition, raise 404 if not found."""
    bo_def = await get_bo_definition(db, code)
    if not bo_def or not bo_def.table_created:
        raise NotFoundError(
            f"Business Object '{code}' not found or table not created.",
            details=[ErrorDetail(
                code="BO_NOT_FOUND",
                message=f"Business Object '{code}' does not exist or its table has not been created.",
                hint="Use GET /api/v1/schema/definitions to list available BOs, "
                     "or create it with PUT /api/v1/schema/definitions/{code}.",
            )],
        )
    return bo_def


@router.get(
    "/{bo_code}",
    summary="Datensaetze auflisten",
    description=(
        "Listet Datensaetze mit Filterung, Sortierung und Pagination.\n\n"
        "**Filter:** `field=value`, `field__contains=value`, `field__gt=value`, "
        "`field__lt=value`, `field__gte=value`, `field__lte=value`, "
        "`field__ne=value`, `field__in=a,b,c`, `field__isnull=true`\n\n"
        "**Sortierung:** `sort=-field1,field2` (- = absteigend)\n\n"
        "**Pagination:** `page=1&page_size=20` (max 100)"
    ),
    responses={404: {"description": "BO nicht gefunden"}},
)
async def list_records(bo_code: str, request: Request, db: AsyncSession = Depends(get_db)):
    bo_def = await _resolve_bo(bo_code, db)
    params = dict(request.query_params)
    return await query_bo_table(db, bo_def.table_name, params)


@router.post(
    "/{bo_code}",
    status_code=201,
    summary="Datensatz erstellen",
    description=(
        "Erstellt einen neuen Datensatz. Body = JSON mit Feldwerten.\n\n"
        "Tipp: Nutze `GET /api/v1/introspect/bo/{bo_code}` fuer ein Beispiel-Payload."
    ),
    responses={
        404: {"description": "BO nicht gefunden"},
        422: {"description": "Validierungsfehler (Typ, Required, Enum, etc.)"},
    },
)
async def create_record(bo_code: str, request: Request, db: AsyncSession = Depends(get_db)):
    bo_def = await _resolve_bo(bo_code, db)
    body = await request.json()

    # Set initial workflow state if workflow exists
    if bo_def.workflow and "_state" not in body:
        body["_state"] = bo_def.workflow.initial_state

    # Validate fields exist
    valid_fields = {f.code for f in bo_def.fields}
    system_fields = {"_state", "_notes", "_created_by"}
    unknown = [k for k in body if k not in valid_fields and k not in system_fields]
    if unknown:
        raise ValidationError(
            f"Unknown field(s): {unknown}",
            details=[
                ErrorDetail(
                    code="UNKNOWN_FIELD",
                    message=f"Field '{k}' does not exist on '{bo_code}'.",
                    field=k,
                    hint=f"Valid fields: {sorted(valid_fields)}",
                )
                for k in unknown
            ],
        )

    # Data validation (type, required, enum, email, url, max_length)
    validate_record_data(body, bo_def.fields, is_create=True)

    try:
        return await insert_bo_record(db, bo_def.table_name, body)
    except Exception as e:
        raise ValidationError(
            f"Insert failed: {e}",
            details=[ErrorDetail(
                code="INSERT_ERROR",
                message=str(e),
                hint="Check that all values match the expected types and constraints.",
            )],
        )


@router.get(
    "/{bo_code}/{record_id}",
    summary="Einzelnen Datensatz abrufen",
    description="Gibt einen einzelnen Datensatz anhand seiner ID zurueck.",
    responses={404: {"description": "BO oder Datensatz nicht gefunden"}},
)
async def get_record(bo_code: str, record_id: int, db: AsyncSession = Depends(get_db)):
    bo_def = await _resolve_bo(bo_code, db)
    record = await get_bo_record(db, bo_def.table_name, record_id)
    if not record:
        raise NotFoundError(
            f"{bo_code}#{record_id} not found.",
            details=[ErrorDetail(
                code="RECORD_NOT_FOUND",
                message=f"Record with ID {record_id} does not exist in '{bo_code}'.",
                hint=f"Use GET /api/v1/data/{bo_code} to list available records.",
            )],
        )
    return record


@router.put(
    "/{bo_code}/{record_id}",
    summary="Datensatz aktualisieren",
    description=(
        "Aktualisiert einen Datensatz. Body = JSON mit zu aktualisierenden Feldern.\n\n"
        "**Achtung:** State-Aenderungen nur ueber Workflow-Transitions, nicht direkt per PUT."
    ),
    responses={
        404: {"description": "BO oder Datensatz nicht gefunden"},
        422: {"description": "Validierungsfehler oder direkter State-Change"},
    },
)
async def update_record(
    bo_code: str, record_id: int, request: Request, db: AsyncSession = Depends(get_db)
):
    bo_def = await _resolve_bo(bo_code, db)
    body = await request.json()

    # Don't allow direct state changes (use transitions)
    if "_state" in body and bo_def.workflow:
        raise ValidationError(
            "Direct state changes are not allowed when a workflow is defined.",
            details=[ErrorDetail(
                code="DIRECT_STATE_CHANGE",
                message="Cannot change _state directly. Use workflow transitions.",
                field="_state",
                hint=f"Use POST /api/v1/data/{bo_code}/{record_id}/transitions/{{code}} to change state. "
                     f"Use GET /api/v1/data/{bo_code}/{record_id}/transitions to see available transitions.",
            )],
        )

    # Data validation (type, enum, email, url, max_length — no required check on update)
    validate_record_data(body, bo_def.fields, is_create=False)

    record = await update_bo_record(db, bo_def.table_name, record_id, body)
    if not record:
        raise NotFoundError(
            f"{bo_code}#{record_id} not found.",
            details=[ErrorDetail(
                code="RECORD_NOT_FOUND",
                message=f"Record with ID {record_id} does not exist in '{bo_code}'.",
            )],
        )
    return record


@router.delete(
    "/{bo_code}/{record_id}",
    status_code=204,
    summary="Datensatz loeschen",
    description="Loescht einen Datensatz anhand seiner ID.",
    responses={404: {"description": "BO oder Datensatz nicht gefunden"}},
)
async def delete_record(bo_code: str, record_id: int, db: AsyncSession = Depends(get_db)):
    bo_def = await _resolve_bo(bo_code, db)
    deleted = await delete_bo_record(db, bo_def.table_name, record_id)
    if not deleted:
        raise NotFoundError(
            f"{bo_code}#{record_id} not found.",
            details=[ErrorDetail(
                code="RECORD_NOT_FOUND",
                message=f"Record with ID {record_id} does not exist in '{bo_code}'.",
            )],
        )


# ── Workflow Transitions ─────────────────────────────────

@router.get(
    "/{bo_code}/{record_id}/transitions",
    summary="Verfuegbare Transitions abrufen",
    description="Zeigt welche Workflow-Transitions fuer den aktuellen State verfuegbar sind.",
    responses={
        404: {"description": "BO oder Datensatz nicht gefunden"},
        422: {"description": "BO hat keinen Workflow"},
    },
)
async def list_transitions(
    bo_code: str, record_id: int, db: AsyncSession = Depends(get_db)
):
    bo_def = await _resolve_bo(bo_code, db)
    if not bo_def.workflow:
        raise ValidationError(
            f"'{bo_code}' has no workflow defined.",
            details=[ErrorDetail(
                code="NO_WORKFLOW",
                message=f"BO '{bo_code}' does not have a workflow.",
                hint="Add a workflow via PUT /api/v1/schema/definitions/{code} with a 'workflow' property.",
            )],
        )

    record = await get_bo_record(db, bo_def.table_name, record_id)
    if not record:
        raise NotFoundError(
            f"{bo_code}#{record_id} not found.",
            details=[ErrorDetail(
                code="RECORD_NOT_FOUND",
                message=f"Record with ID {record_id} does not exist.",
            )],
        )

    return await get_available_transitions(db, bo_def.id, record.get("_state"))


@router.post(
    "/{bo_code}/{record_id}/transitions/{transition_code}",
    summary="Workflow-Transition ausfuehren",
    description=(
        "Fuehrt eine Workflow-Transition auf einem Datensatz aus.\n\n"
        "Beispiel: `POST /data/Deal/1/transitions/qualify` aendert den State von 'lead' zu 'qualified'."
    ),
    responses={
        404: {"description": "BO oder Datensatz nicht gefunden"},
        422: {"description": "Transition nicht gueltig oder kein Workflow"},
    },
)
async def execute_workflow_transition(
    bo_code: str, record_id: int, transition_code: str,
    db: AsyncSession = Depends(get_db),
):
    bo_def = await _resolve_bo(bo_code, db)
    if not bo_def.workflow:
        raise ValidationError(
            f"'{bo_code}' has no workflow defined.",
            details=[ErrorDetail(
                code="NO_WORKFLOW",
                message=f"BO '{bo_code}' does not have a workflow.",
            )],
        )

    try:
        return await execute_transition(
            db, bo_def.id, bo_def.table_name, record_id, transition_code
        )
    except WorkflowError as e:
        raise ValidationError(
            str(e),
            details=[ErrorDetail(
                code="INVALID_TRANSITION",
                message=str(e),
                hint=f"Use GET /api/v1/data/{bo_code}/{record_id}/transitions to see available transitions.",
            )],
        )
