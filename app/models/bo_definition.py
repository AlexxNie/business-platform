"""BODefinition = Blueprint fuer ein Business Object (z.B. Customer, Order, Asset).

Wenn eine BODefinition erstellt wird, generiert die Engine eine echte
PostgreSQL-Tabelle mit dem Prefix 'bo_' + code.
"""

from sqlalchemy import String, Text, Boolean, Integer, ForeignKey, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base
import datetime


class BODefinition(Base):
    __tablename__ = "bo_definitions"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    module_id: Mapped[int | None] = mapped_column(ForeignKey("modules.id"))
    icon: Mapped[str | None] = mapped_column(String(50))

    # Table config
    table_name: Mapped[str] = mapped_column(String(200), unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    table_created: Mapped[bool] = mapped_column(Boolean, default=False)

    # Hierarchy support (BO can be child of another BO type)
    parent_bo_id: Mapped[int | None] = mapped_column(ForeignKey("bo_definitions.id"))

    # Display config
    display_field: Mapped[str | None] = mapped_column(String(100))  # Which field to show as label
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relations
    module: Mapped["Module | None"] = relationship(back_populates="bo_definitions")
    fields: Mapped[list["FieldDefinition"]] = relationship(
        back_populates="bo_definition", cascade="all, delete-orphan",
        order_by="FieldDefinition.sort_order"
    )
    parent_bo: Mapped["BODefinition | None"] = relationship(remote_side="BODefinition.id")
    workflow: Mapped["WorkflowDefinition | None"] = relationship(
        back_populates="bo_definition", uselist=False, cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<BODefinition {self.code}: {self.name}>"
