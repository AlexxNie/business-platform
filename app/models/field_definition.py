"""FieldDefinition = Ein Feld innerhalb eines Business Objects.

Unterstützte Typen werden in SQL-Spalten gemappt:
  text     -> VARCHAR / TEXT
  integer  -> INTEGER
  float    -> DOUBLE PRECISION
  boolean  -> BOOLEAN
  date     -> DATE
  datetime -> TIMESTAMP WITH TIME ZONE
  email    -> VARCHAR(320) + CHECK
  url      -> TEXT
  enum     -> VARCHAR + CHECK constraint
  json     -> JSONB
  reference -> INTEGER + FOREIGN KEY
"""

from sqlalchemy import String, Text, Boolean, Integer, ForeignKey, DateTime, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base
import datetime


FIELD_TYPES = [
    "text", "integer", "float", "boolean",
    "date", "datetime", "email", "url",
    "enum", "json", "reference",
]


class FieldDefinition(Base):
    __tablename__ = "field_definitions"

    id: Mapped[int] = mapped_column(primary_key=True)
    bo_definition_id: Mapped[int] = mapped_column(
        ForeignKey("bo_definitions.id", ondelete="CASCADE"), index=True
    )
    code: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(200))
    field_type: Mapped[str] = mapped_column(String(20))  # One of FIELD_TYPES
    description: Mapped[str | None] = mapped_column(Text)

    # Constraints
    required: Mapped[bool] = mapped_column(Boolean, default=False)
    unique: Mapped[bool] = mapped_column(Boolean, default=False)
    indexed: Mapped[bool] = mapped_column(Boolean, default=False)
    max_length: Mapped[int | None] = mapped_column(Integer)
    default_value: Mapped[str | None] = mapped_column(Text)

    # Enum values (for field_type='enum')
    enum_values: Mapped[dict | None] = mapped_column(JSONB)  # ["active", "inactive", ...]

    # Reference config (for field_type='reference')
    reference_bo_code: Mapped[str | None] = mapped_column(String(100))

    # Display
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_searchable: Mapped[bool] = mapped_column(Boolean, default=False)
    is_hidden: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relations
    bo_definition: Mapped["BODefinition"] = relationship(back_populates="fields")

    def __repr__(self) -> str:
        return f"<Field {self.bo_definition_id}.{self.code} ({self.field_type})>"
