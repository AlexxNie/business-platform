"""Mapping von BO-Feldtypen auf PostgreSQL-Spaltentypen."""

from sqlalchemy import (
    String, Text, Integer, Float, Boolean, Date, DateTime,
    BigInteger, CheckConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB


# field_type -> (SQLAlchemy Type, default kwargs)
FIELD_TYPE_MAP = {
    "text": lambda f: String(f.max_length) if f.max_length else Text(),
    "integer": lambda f: BigInteger() if f.code.endswith("_id") else Integer(),
    "float": lambda f: Float(),
    "boolean": lambda f: Boolean(),
    "date": lambda f: Date(),
    "datetime": lambda f: DateTime(timezone=True),
    "email": lambda f: String(320),
    "url": lambda f: Text(),
    "enum": lambda f: String(100),
    "json": lambda f: JSONB(),
    "reference": lambda f: BigInteger(),  # FK to another bo_ table
}


def get_column_type(field):
    """Get SQLAlchemy column type for a FieldDefinition."""
    factory = FIELD_TYPE_MAP.get(field.field_type)
    if not factory:
        raise ValueError(f"Unknown field type: {field.field_type}")
    return factory(field)


def get_constraints(field, table_name: str) -> list:
    """Get CHECK constraints for a field."""
    constraints = []

    if field.field_type == "enum" and field.enum_values:
        values = field.enum_values
        if isinstance(values, list) and values:
            quoted = ", ".join(f"'{v}'" for v in values)
            constraints.append(
                CheckConstraint(
                    f'"{field.code}" IN ({quoted})',
                    name=f"ck_{table_name}_{field.code}_enum",
                )
            )

    if field.field_type == "email":
        constraints.append(
            CheckConstraint(
                f'"{field.code}" ~* \'^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Z|a-z]{{2,}}$\'',
                name=f"ck_{table_name}_{field.code}_email",
            )
        )

    return constraints
