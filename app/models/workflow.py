"""Workflow = State Machine fuer Business Objects.

Jeder BO-Typ kann einen Workflow haben mit:
- States (z.B. draft, active, completed)
- Transitions (z.B. draft -> active via "activate")
- Transition-Conditions (optional, z.B. "all required fields filled")
"""

from sqlalchemy import String, Text, Boolean, Integer, ForeignKey, DateTime, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base
import datetime


class WorkflowDefinition(Base):
    __tablename__ = "workflow_definitions"

    id: Mapped[int] = mapped_column(primary_key=True)
    bo_definition_id: Mapped[int] = mapped_column(
        ForeignKey("bo_definitions.id", ondelete="CASCADE"), unique=True
    )
    initial_state: Mapped[str] = mapped_column(String(100))

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relations
    bo_definition: Mapped["BODefinition"] = relationship(back_populates="workflow")
    states: Mapped[list["WorkflowState"]] = relationship(
        back_populates="workflow", cascade="all, delete-orphan",
        order_by="WorkflowState.sort_order"
    )
    transitions: Mapped[list["WorkflowTransition"]] = relationship(
        back_populates="workflow", cascade="all, delete-orphan"
    )


class WorkflowState(Base):
    __tablename__ = "workflow_states"

    id: Mapped[int] = mapped_column(primary_key=True)
    workflow_id: Mapped[int] = mapped_column(
        ForeignKey("workflow_definitions.id", ondelete="CASCADE"), index=True
    )
    code: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(200))
    color: Mapped[str | None] = mapped_column(String(20))  # Hex color for UI
    is_final: Mapped[bool] = mapped_column(Boolean, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    # Relations
    workflow: Mapped["WorkflowDefinition"] = relationship(back_populates="states")


class WorkflowTransition(Base):
    __tablename__ = "workflow_transitions"

    id: Mapped[int] = mapped_column(primary_key=True)
    workflow_id: Mapped[int] = mapped_column(
        ForeignKey("workflow_definitions.id", ondelete="CASCADE"), index=True
    )
    code: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(200))
    from_state: Mapped[str] = mapped_column(String(100))
    to_state: Mapped[str] = mapped_column(String(100))

    # Optional conditions (JSONB for flexibility)
    conditions: Mapped[dict | None] = mapped_column(JSONB)
    # Optional webhook on transition
    webhook_url: Mapped[str | None] = mapped_column(Text)

    # Relations
    workflow: Mapped["WorkflowDefinition"] = relationship(back_populates="transitions")
