"""Schema Service - Verwaltet BO-Definitionen und erstellt dynamische Tabellen.

Kern-Logik:
1. BO-Definition in Meta-Tabelle speichern
2. Dynamische Tabelle in PostgreSQL erstellen
3. Bei Aenderungen: ALTER TABLE
"""

import logging
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.module import Module
from app.models.bo_definition import BODefinition
from app.models.field_definition import FieldDefinition
from app.models.workflow import WorkflowDefinition, WorkflowState, WorkflowTransition
from app.core.dynamic_tables import (
    create_bo_table, get_table_name, add_column, drop_column,
    drop_bo_table, table_exists, get_table_columns,
)
from app.core.errors import ConflictError, NotFoundError, ErrorDetail
from app.database import sync_engine

logger = logging.getLogger(__name__)


async def create_bo_definition(session: AsyncSession, data: dict) -> BODefinition:
    """Create a new BO definition and its database table.

    Raises ConflictError if BO already exists (mit Hint auf PUT).
    """
    code = data["code"]
    table_name = get_table_name(code)

    # Check if already exists
    existing = await session.execute(
        select(BODefinition).where(BODefinition.code == code)
    )
    if existing.scalar_one_or_none():
        raise ConflictError(
            f"BO definition '{code}' already exists.",
            details=[ErrorDetail(
                code="DUPLICATE_BO_DEFINITION",
                message=f"A BO definition with code '{code}' already exists.",
                field="code",
                hint=f"Use PUT /api/v1/schema/definitions/{code} to update the existing definition.",
            )],
        )

    # Resolve module
    module_id = None
    if data.get("module_code"):
        module = await session.execute(
            select(Module).where(Module.code == data["module_code"])
        )
        mod = module.scalar_one_or_none()
        if not mod:
            raise NotFoundError(
                f"Module '{data['module_code']}' not found.",
                details=[ErrorDetail(
                    code="MODULE_NOT_FOUND",
                    message=f"Module '{data['module_code']}' does not exist.",
                    field="module_code",
                    hint="Create the module first with PUT /api/v1/schema/modules/{code}",
                )],
            )
        module_id = mod.id

    # Resolve parent BO
    parent_bo_id = None
    if data.get("parent_bo_code"):
        parent = await session.execute(
            select(BODefinition).where(BODefinition.code == data["parent_bo_code"])
        )
        p = parent.scalar_one_or_none()
        if p:
            parent_bo_id = p.id

    # Create BO definition
    bo_def = BODefinition(
        code=code,
        name=data["name"],
        description=data.get("description"),
        module_id=module_id,
        icon=data.get("icon"),
        table_name=table_name,
        parent_bo_id=parent_bo_id,
        display_field=data.get("display_field"),
    )
    session.add(bo_def)
    await session.flush()

    # Create field definitions
    fields = []
    for i, field_data in enumerate(data.get("fields", [])):
        field = FieldDefinition(
            bo_definition_id=bo_def.id,
            code=field_data["code"],
            name=field_data["name"],
            field_type=field_data["field_type"],
            description=field_data.get("description"),
            required=field_data.get("required", False),
            unique=field_data.get("unique", False),
            indexed=field_data.get("indexed", False),
            max_length=field_data.get("max_length"),
            default_value=field_data.get("default_value"),
            enum_values=field_data.get("enum_values"),
            reference_bo_code=field_data.get("reference_bo_code"),
            is_searchable=field_data.get("is_searchable", False),
            sort_order=field_data.get("sort_order", i),
        )
        session.add(field)
        fields.append(field)

    await session.flush()

    # Create workflow if provided
    if data.get("workflow"):
        wf_data = data["workflow"]
        workflow = WorkflowDefinition(
            bo_definition_id=bo_def.id,
            initial_state=wf_data["initial_state"],
        )
        session.add(workflow)
        await session.flush()

        for s in wf_data.get("states", []):
            state = WorkflowState(
                workflow_id=workflow.id,
                code=s["code"],
                name=s["name"],
                color=s.get("color"),
                is_final=s.get("is_final", False),
                sort_order=s.get("sort_order", 0),
            )
            session.add(state)

        for t in wf_data.get("transitions", []):
            trans = WorkflowTransition(
                workflow_id=workflow.id,
                code=t["code"],
                name=t["name"],
                from_state=t["from_state"],
                to_state=t["to_state"],
                conditions=t.get("conditions"),
                webhook_url=t.get("webhook_url"),
            )
            session.add(trans)

    # Create the actual database table
    create_bo_table(sync_engine, bo_def, fields)
    bo_def.table_created = True

    await session.commit()

    # Reload with relations
    result = await session.execute(
        select(BODefinition)
        .options(selectinload(BODefinition.fields))
        .where(BODefinition.id == bo_def.id)
    )
    return result.scalar_one()


async def upsert_bo_definition(session: AsyncSession, code: str, data: dict) -> tuple[BODefinition, bool]:
    """Create or update a BO definition. Returns (bo_def, created).

    Idempotent: If BO exists, updates name/description/icon/module.
    Does NOT recreate the table or re-add existing fields.
    """
    existing = await get_bo_definition(session, code)

    if existing:
        # Update existing BO
        if data.get("name"):
            existing.name = data["name"]
        if "description" in data:
            existing.description = data.get("description")
        if "icon" in data:
            existing.icon = data.get("icon")
        if "display_field" in data:
            existing.display_field = data.get("display_field")

        # Update module assignment
        if data.get("module_code"):
            module = await session.execute(
                select(Module).where(Module.code == data["module_code"])
            )
            mod = module.scalar_one_or_none()
            if mod:
                existing.module_id = mod.id

        # Add new fields that don't exist yet
        existing_field_codes = {f.code for f in existing.fields}
        for i, field_data in enumerate(data.get("fields", [])):
            if field_data["code"] not in existing_field_codes:
                field = FieldDefinition(
                    bo_definition_id=existing.id,
                    code=field_data["code"],
                    name=field_data["name"],
                    field_type=field_data["field_type"],
                    description=field_data.get("description"),
                    required=field_data.get("required", False),
                    unique=field_data.get("unique", False),
                    indexed=field_data.get("indexed", False),
                    max_length=field_data.get("max_length"),
                    default_value=field_data.get("default_value"),
                    enum_values=field_data.get("enum_values"),
                    reference_bo_code=field_data.get("reference_bo_code"),
                    is_searchable=field_data.get("is_searchable", False),
                    sort_order=field_data.get("sort_order", len(existing_field_codes) + i),
                )
                session.add(field)
                await session.flush()
                # ALTER TABLE ADD COLUMN
                if existing.table_created:
                    add_column(sync_engine, existing.table_name, field)

        # Add/update workflow if provided and not existing
        if data.get("workflow") and not existing.workflow:
            wf_data = data["workflow"]
            workflow = WorkflowDefinition(
                bo_definition_id=existing.id,
                initial_state=wf_data["initial_state"],
            )
            session.add(workflow)
            await session.flush()

            for s in wf_data.get("states", []):
                state = WorkflowState(
                    workflow_id=workflow.id,
                    code=s["code"],
                    name=s["name"],
                    color=s.get("color"),
                    is_final=s.get("is_final", False),
                    sort_order=s.get("sort_order", 0),
                )
                session.add(state)

            for t in wf_data.get("transitions", []):
                trans = WorkflowTransition(
                    workflow_id=workflow.id,
                    code=t["code"],
                    name=t["name"],
                    from_state=t["from_state"],
                    to_state=t["to_state"],
                    conditions=t.get("conditions"),
                    webhook_url=t.get("webhook_url"),
                )
                session.add(trans)

        await session.commit()

        # Reload with relations
        result = await session.execute(
            select(BODefinition)
            .options(selectinload(BODefinition.fields))
            .where(BODefinition.id == existing.id)
        )
        return result.scalar_one(), False

    # Create new — delegate to create_bo_definition
    data["code"] = code
    bo_def = await create_bo_definition(session, data)
    return bo_def, True


async def get_bo_definition(session: AsyncSession, code: str) -> BODefinition | None:
    """Get a BO definition by code with all fields and workflow."""
    result = await session.execute(
        select(BODefinition)
        .options(
            selectinload(BODefinition.fields),
            selectinload(BODefinition.workflow).selectinload(WorkflowDefinition.states),
            selectinload(BODefinition.workflow).selectinload(WorkflowDefinition.transitions),
        )
        .where(BODefinition.code == code)
    )
    return result.scalar_one_or_none()


async def list_bo_definitions(session: AsyncSession, module_code: str | None = None) -> list:
    """List all BO definitions."""
    query = select(BODefinition).options(
        selectinload(BODefinition.fields),
        selectinload(BODefinition.workflow),
    )
    if module_code:
        query = query.join(Module).where(Module.code == module_code)
    query = query.order_by(BODefinition.sort_order, BODefinition.code)
    result = await session.execute(query)
    return result.scalars().all()


async def add_field_to_bo(session: AsyncSession, bo_code: str, field_data: dict) -> tuple[FieldDefinition, bool]:
    """Add a new field to an existing BO definition.

    Idempotent: If field with same code and type exists, returns it.
    Returns (field, created).
    """
    bo_def = await get_bo_definition(session, bo_code)
    if not bo_def:
        raise NotFoundError(
            f"BO definition '{bo_code}' not found.",
            details=[ErrorDetail(
                code="BO_NOT_FOUND",
                message=f"BO definition '{bo_code}' does not exist.",
                hint="Create it first with POST/PUT /api/v1/schema/definitions",
            )],
        )

    # Check field exists — idempotent
    for f in bo_def.fields:
        if f.code == field_data["code"]:
            if f.field_type == field_data["field_type"]:
                # Same field, same type → idempotent return
                return f, False
            raise ConflictError(
                f"Field '{field_data['code']}' already exists on '{bo_code}' with type '{f.field_type}'.",
                details=[ErrorDetail(
                    code="DUPLICATE_FIELD",
                    message=f"Field '{field_data['code']}' exists with type '{f.field_type}', "
                            f"but you requested type '{field_data['field_type']}'.",
                    field="code",
                    hint="Remove the existing field first or use the same field_type.",
                )],
            )

    field = FieldDefinition(
        bo_definition_id=bo_def.id,
        code=field_data["code"],
        name=field_data["name"],
        field_type=field_data["field_type"],
        description=field_data.get("description"),
        required=field_data.get("required", False),
        unique=field_data.get("unique", False),
        indexed=field_data.get("indexed", False),
        max_length=field_data.get("max_length"),
        default_value=field_data.get("default_value"),
        enum_values=field_data.get("enum_values"),
        reference_bo_code=field_data.get("reference_bo_code"),
        is_searchable=field_data.get("is_searchable", False),
        sort_order=field_data.get("sort_order", len(bo_def.fields)),
    )
    session.add(field)
    await session.flush()

    # ALTER TABLE
    add_column(sync_engine, bo_def.table_name, field)

    await session.commit()
    return field, True


async def remove_field_from_bo(session: AsyncSession, bo_code: str, field_code: str) -> bool:
    """Remove a field from a BO definition."""
    bo_def = await get_bo_definition(session, bo_code)
    if not bo_def:
        raise NotFoundError(
            f"BO definition '{bo_code}' not found.",
            details=[ErrorDetail(
                code="BO_NOT_FOUND",
                message=f"BO definition '{bo_code}' does not exist.",
            )],
        )

    field = None
    for f in bo_def.fields:
        if f.code == field_code:
            field = f
            break

    if not field:
        raise NotFoundError(
            f"Field '{field_code}' not found on '{bo_code}'.",
            details=[ErrorDetail(
                code="FIELD_NOT_FOUND",
                message=f"Field '{field_code}' does not exist on BO '{bo_code}'.",
                field="field_code",
            )],
        )

    # DROP COLUMN
    drop_column(sync_engine, bo_def.table_name, field_code)

    await session.delete(field)
    await session.commit()
    return True


async def delete_bo_definition(session: AsyncSession, code: str) -> bool:
    """Delete a BO definition and its database table."""
    bo_def = await get_bo_definition(session, code)
    if not bo_def:
        raise NotFoundError(
            f"BO definition '{code}' not found.",
            details=[ErrorDetail(
                code="BO_NOT_FOUND",
                message=f"BO definition '{code}' does not exist.",
            )],
        )

    # Drop the dynamic table
    if bo_def.table_created:
        drop_bo_table(sync_engine, bo_def.table_name)

    await session.delete(bo_def)
    await session.commit()
    return True


async def get_table_info(session: AsyncSession, bo_code: str) -> dict:
    """Get actual database table info for a BO (for TSI-like view)."""
    bo_def = await get_bo_definition(session, bo_code)
    if not bo_def:
        raise NotFoundError(
            f"BO definition '{bo_code}' not found.",
            details=[ErrorDetail(
                code="BO_NOT_FOUND",
                message=f"BO definition '{bo_code}' does not exist.",
            )],
        )

    columns = get_table_columns(sync_engine, bo_def.table_name)
    exists = table_exists(sync_engine, bo_def.table_name)

    return {
        "bo_code": bo_code,
        "table_name": bo_def.table_name,
        "table_exists": exists,
        "columns": columns,
        "field_definitions": len(bo_def.fields),
    }
