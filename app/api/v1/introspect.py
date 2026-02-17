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

router = APIRouter(prefix="/introspect", tags=["Introspection (TSI View)"])


@router.get("/overview")
async def platform_overview(db: AsyncSession = Depends(get_db)):
    """Complete platform overview - shows everything an AI needs to understand the system."""

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
            "fields": [
                {
                    "code": f.code,
                    "name": f.name,
                    "type": f.field_type,
                    "required": f.required,
                    "unique": f.unique,
                    "enum_values": f.enum_values,
                    "reference": f.reference_bo_code,
                }
                for f in bo.fields
            ],
            "workflow": None,
        }

        if bo.workflow:
            bo_info["workflow"] = {
                "initial_state": bo.workflow.initial_state,
                "states": [
                    {"code": s.code, "name": s.name, "color": s.color, "is_final": s.is_final}
                    for s in bo.workflow.states
                ],
                "transitions": [
                    {
                        "code": t.code, "name": t.name,
                        "from": t.from_state, "to": t.to_state,
                    }
                    for t in bo.workflow.transitions
                ],
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
    }


@router.get("/suggest")
async def suggest_extensions(db: AsyncSession = Depends(get_db)):
    """AI-friendly endpoint: Analyze current schema and suggest improvements.

    Returns suggestions like:
    - Missing indexes on frequently queried fields
    - BOs without workflows
    - Fields that could benefit from validation
    - Missing references between related BOs
    """
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
