"""Introspection API - TSI-aehnliche Ansicht der gesamten Plattform-Struktur.

Zeigt AI und Frontend welche Module, BOs, Felder und Workflows existieren.
Perfekt fuer AI-Agents die das System verstehen und erweitern wollen.
"""

from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.module import Module
from app.models.bo_definition import BODefinition
from app.models.field_definition import FieldDefinition
from app.models.workflow import WorkflowDefinition, WorkflowState, WorkflowTransition
from app.core.errors import NotFoundError, ErrorDetail

router = APIRouter(prefix="/introspect", tags=["Introspection (TSI View)"])


FILTER_OPERATORS = {
    "eq": "Exact match (default)",
    "ne": "Not equal",
    "gt": "Greater than",
    "gte": "Greater than or equal",
    "lt": "Less than",
    "lte": "Less than or equal",
    "contains": "ILIKE %value%",
    "startswith": "ILIKE value%",
    "endswith": "ILIKE %value",
    "in": "IN (comma-separated values)",
    "isnull": "IS NULL (true) / IS NOT NULL (false)",
}


def _build_field_info(f, include_details: bool = False) -> dict:
    """Build field info dict."""
    info = {
        "code": f.code,
        "name": f.name,
        "type": f.field_type,
        "required": f.required,
        "unique": f.unique,
    }
    if include_details:
        info.update({
            "description": f.description,
            "indexed": f.indexed,
            "max_length": f.max_length,
            "default_value": f.default_value,
            "is_searchable": f.is_searchable,
            "sort_order": f.sort_order,
        })
    if f.enum_values:
        info["enum_values"] = f.enum_values
    if f.reference_bo_code:
        info["reference"] = f.reference_bo_code
    return info


def _build_workflow_info(workflow) -> dict | None:
    """Build workflow info dict."""
    if not workflow:
        return None
    return {
        "initial_state": workflow.initial_state,
        "states": [
            {"code": s.code, "name": s.name, "color": s.color, "is_final": s.is_final}
            for s in workflow.states
        ],
        "transitions": [
            {
                "code": t.code, "name": t.name,
                "from": t.from_state, "to": t.to_state,
            }
            for t in workflow.transitions
        ],
    }


def _build_example_payload(fields, workflow=None) -> dict:
    """Generate an example POST payload for a BO."""
    example = {}
    for f in fields:
        if f.field_type == "text":
            example[f.code] = f"Example {f.name}"
        elif f.field_type == "integer":
            example[f.code] = 1
        elif f.field_type == "float":
            example[f.code] = 1.0
        elif f.field_type == "boolean":
            example[f.code] = True
        elif f.field_type == "date":
            example[f.code] = "2026-01-15"
        elif f.field_type == "datetime":
            example[f.code] = "2026-01-15T10:30:00Z"
        elif f.field_type == "email":
            example[f.code] = "user@example.com"
        elif f.field_type == "url":
            example[f.code] = "https://example.com"
        elif f.field_type == "enum" and f.enum_values:
            vals = f.enum_values if isinstance(f.enum_values, list) else list(f.enum_values)
            example[f.code] = vals[0] if vals else "value"
        elif f.field_type == "json":
            example[f.code] = {}
        elif f.field_type == "reference":
            example[f.code] = 1
    return example


@router.get(
    "/overview",
    summary="Plattform-Uebersicht",
    description=(
        "Komplette Plattform-Uebersicht fuer AI-Agents und Frontends.\n\n"
        "Zeigt alle Module, BO-Definitionen, Felder und Workflows."
    ),
)
async def platform_overview(db: AsyncSession = Depends(get_db)):
    # Modules
    modules_result = await db.execute(select(Module).order_by(Module.code))
    modules = modules_result.scalars().all()

    # BO Definitions with fields and workflows
    bo_result = await db.execute(
        select(BODefinition)
        .options(
            selectinload(BODefinition.fields),
            selectinload(BODefinition.workflow).selectinload(WorkflowDefinition.states),
            selectinload(BODefinition.workflow).selectinload(WorkflowDefinition.transitions),
        )
        .order_by(BODefinition.sort_order, BODefinition.code)
    )
    bo_defs = bo_result.scalars().all()

    # Build response
    module_map = {}
    for m in modules:
        module_map[m.id] = {
            "code": m.code,
            "name": m.name,
            "description": m.description,
            "bo_definitions": [],
        }

    unassigned = []

    for bo in bo_defs:
        bo_info = {
            "code": bo.code,
            "name": bo.name,
            "description": bo.description,
            "table_name": bo.table_name,
            "table_created": bo.table_created,
            "display_field": bo.display_field,
            "fields": [_build_field_info(f, include_details=True) for f in bo.fields],
            "workflow": _build_workflow_info(bo.workflow),
        }

        if bo.module_id and bo.module_id in module_map:
            module_map[bo.module_id]["bo_definitions"].append(bo_info)
        else:
            unassigned.append(bo_info)

    return {
        "platform": "Business Platform",
        "version": "0.1.0",
        "modules": list(module_map.values()),
        "unassigned_bos": unassigned,
        "stats": {
            "modules": len(modules),
            "bo_definitions": len(bo_defs),
            "total_fields": sum(len(bo.fields) for bo in bo_defs),
        },
        "hints": {
            "create_module": "PUT /api/v1/schema/modules/{code}",
            "create_bo": "PUT /api/v1/schema/definitions/{code}",
            "bo_details": "GET /api/v1/introspect/bo/{bo_code}",
            "create_record": "POST /api/v1/data/{bo_code}",
            "filter_syntax": "GET /api/v1/data/{bo_code}?field__operator=value",
            "available_operators": list(FILTER_OPERATORS.keys()),
        },
    }


@router.get(
    "/bo/{bo_code}",
    summary="BO-Detail-Introspection",
    description=(
        "Alles was ein LLM-Agent braucht um mit einem BO zu arbeiten:\n\n"
        "- Alle Felder mit Typ, Constraints, Enum-Werte, Referenz-Ziel\n"
        "- Beispiel-Payload fuer POST\n"
        "- Verfuegbare Filter-Operatoren\n"
        "- Workflow-States und Transitions\n"
        "- Endpoint-URLs"
    ),
    responses={404: {"description": "BO nicht gefunden"}},
)
async def bo_introspection(bo_code: str, db: AsyncSession = Depends(get_db)):
    """Detaillierte BO-Informationen fuer LLM-Agents."""
    # Load BO with all relations
    result = await db.execute(
        select(BODefinition)
        .options(
            selectinload(BODefinition.fields),
            selectinload(BODefinition.workflow).selectinload(WorkflowDefinition.states),
            selectinload(BODefinition.workflow).selectinload(WorkflowDefinition.transitions),
        )
        .where(BODefinition.code == bo_code)
    )
    bo = result.scalar_one_or_none()

    if not bo or not bo.table_created:
        raise NotFoundError(
            f"Business Object '{bo_code}' not found.",
            details=[ErrorDetail(
                code="BO_NOT_FOUND",
                message=f"BO '{bo_code}' does not exist or its table has not been created.",
                hint="Use GET /api/v1/introspect/overview to see all available BOs.",
            )],
        )

    # Build field details
    fields_detail = []
    required_fields = []
    for f in bo.fields:
        fd = {
            "code": f.code,
            "name": f.name,
            "type": f.field_type,
            "required": f.required,
            "unique": f.unique,
            "indexed": f.indexed,
            "max_length": f.max_length,
            "default_value": f.default_value,
            "description": f.description,
            "is_searchable": f.is_searchable,
        }
        if f.enum_values:
            fd["enum_values"] = f.enum_values
        if f.reference_bo_code:
            fd["reference_bo_code"] = f.reference_bo_code
        fields_detail.append(fd)
        if f.required:
            required_fields.append(f.code)

    # Example payload
    example_payload = _build_example_payload(bo.fields, bo.workflow)

    # Endpoints
    base = f"/api/v1/data/{bo_code}"
    endpoints = {
        "list": f"GET {base}",
        "create": f"POST {base}",
        "get": f"GET {base}/{{id}}",
        "update": f"PUT {base}/{{id}}",
        "delete": f"DELETE {base}/{{id}}",
    }
    if bo.workflow:
        endpoints["transitions"] = f"GET {base}/{{id}}/transitions"
        endpoints["execute_transition"] = f"POST {base}/{{id}}/transitions/{{code}}"

    response = {
        "bo_code": bo.code,
        "name": bo.name,
        "description": bo.description,
        "table_name": bo.table_name,
        "display_field": bo.display_field,
        "fields": fields_detail,
        "required_fields": required_fields,
        "example_payload": example_payload,
        "endpoints": endpoints,
        "filter_operators": FILTER_OPERATORS,
        "workflow": _build_workflow_info(bo.workflow),
    }

    return response


@router.get(
    "/suggest",
    summary="Schema-Verbesserungsvorschlaege",
    description=(
        "Analysiert das aktuelle Schema und gibt Verbesserungsvorschlaege.\n\n"
        "Nuetzlich fuer AI-Agents die das System optimieren wollen."
    ),
)
async def suggest_extensions(db: AsyncSession = Depends(get_db)):
    bo_result = await db.execute(
        select(BODefinition)
        .options(
            selectinload(BODefinition.fields),
            selectinload(BODefinition.workflow),
        )
    )
    bo_defs = bo_result.scalars().all()

    suggestions = []

    for bo in bo_defs:
        # No workflow?
        if not bo.workflow:
            suggestions.append({
                "type": "add_workflow",
                "bo_code": bo.code,
                "message": f"BO '{bo.name}' has no workflow. Consider adding states for lifecycle management.",
                "hint": f"Use PUT /api/v1/schema/definitions/{bo.code} with a 'workflow' property.",
            })

        # No display field?
        if not bo.display_field and bo.fields:
            text_fields = [f for f in bo.fields if f.field_type == "text"]
            if text_fields:
                suggestions.append({
                    "type": "set_display_field",
                    "bo_code": bo.code,
                    "suggested_field": text_fields[0].code,
                    "message": f"BO '{bo.name}' has no display field. Consider using '{text_fields[0].code}'.",
                })

        # Reference fields without index
        for field in bo.fields:
            if field.field_type == "reference" and not field.indexed:
                suggestions.append({
                    "type": "add_index",
                    "bo_code": bo.code,
                    "field_code": field.code,
                    "message": f"Reference field '{field.code}' on '{bo.name}' should be indexed for performance.",
                })

        # No searchable fields
        searchable = [f for f in bo.fields if f.is_searchable]
        if not searchable and bo.fields:
            suggestions.append({
                "type": "add_searchable",
                "bo_code": bo.code,
                "message": f"BO '{bo.name}' has no searchable fields. Mark key text fields as searchable.",
            })

    return {
        "suggestions": suggestions,
        "total": len(suggestions),
    }
