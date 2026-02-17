"""RelationDefinition = Beziehung zwischen zwei BO-Typen.

Typen:
  one_to_many  -> FK in child table
  many_to_many -> Junction table
  one_to_one   -> FK + UNIQUE
"""

from sqlalchemy import String, Text, Integer, ForeignKey, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base
import datetime


class RelationDefinition(Base):
    __tablename__ = "relation_definitions"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    name: Mapped[str | None] = mapped_column(String(200))
    relation_type: Mapped[str] = mapped_column(String(20))  # one_to_many, many_to_many, one_to_one

    source_bo_id: Mapped[int] = mapped_column(ForeignKey("bo_definitions.id"))
    target_bo_id: Mapped[int] = mapped_column(ForeignKey("bo_definitions.id"))

    # For one_to_many: FK column name in child table
    fk_column: Mapped[str | None] = mapped_column(String(100))
    # For many_to_many: junction table name
    junction_table: Mapped[str | None] = mapped_column(String(200))

    description: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
