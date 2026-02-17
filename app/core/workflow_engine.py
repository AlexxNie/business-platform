"""Workflow Engine - State Machine fuer Business Objects.

Validiert Transitions und fuehrt State-Changes durch.
"""

import logging
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workflow import WorkflowDefinition, WorkflowState, WorkflowTransition
from app.core.query_engine import get_bo_record, update_bo_record

logger = logging.getLogger(__name__)


class WorkflowError(Exception):
    pass


async def get_available_transitions(
    session: AsyncSession,
    bo_definition_id: int,
    current_state: str,
) -> list[dict]:
    """Get all valid transitions from the current state."""
    result = await session.execute(
        select(WorkflowTransition)
        .join(WorkflowDefinition)
        .where(
            WorkflowDefinition.bo_definition_id == bo_definition_id,
            WorkflowTransition.from_state == current_state,
        )
    )
    transitions = result.scalars().all()
    return [
        {
            "code": t.code,
            "name": t.name,
            "from_state": t.from_state,
            "to_state": t.to_state,
        }
        for t in transitions
    ]


async def execute_transition(
    session: AsyncSession,
    bo_definition_id: int,
    table_name: str,
    record_id: int,
    transition_code: str,
) -> dict:
    """Execute a workflow transition on a record.

    1. Validate current state
    2. Find matching transition
    3. Check conditions (if any)
    4. Update state
    5. Return updated record
    """
    # Get current record
    record = await get_bo_record(session, table_name, record_id)
    if not record:
        raise WorkflowError(f"Record {record_id} not found")

    current_state = record.get("_state")

    # Find transition
    result = await session.execute(
        select(WorkflowTransition)
        .join(WorkflowDefinition)
        .where(
            WorkflowDefinition.bo_definition_id == bo_definition_id,
            WorkflowTransition.code == transition_code,
            WorkflowTransition.from_state == current_state,
        )
    )
    transition = result.scalar_one_or_none()

    if not transition:
        available = await get_available_transitions(session, bo_definition_id, current_state)
        available_codes = [t["code"] for t in available]
        raise WorkflowError(
            f"Transition '{transition_code}' not valid from state '{current_state}'. "
            f"Available: {available_codes}"
        )

    # Execute transition
    updated = await update_bo_record(
        session, table_name, record_id, {"_state": transition.to_state}
    )

    logger.info(
        f"Transition {transition_code}: {current_state} -> {transition.to_state} "
        f"on {table_name}#{record_id}"
    )

    return updated
