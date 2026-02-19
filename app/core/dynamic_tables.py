"""Dynamic Table Engine - Erzeugt echte PostgreSQL-Tabellen aus BO-Definitionen.

Wenn ein BO-Typ definiert wird (z.B. "Customer"), erstellt diese Engine:
1. CREATE TABLE bo_customer (id, _state, _created_at, _updated_at, + custom fields)
2. Indexes fuer searchable/indexed fields
3. Foreign Keys fuer reference fields
4. CHECK constraints fuer enums

Bei Schema-Aenderungen (Feld hinzufuegen/entfernen):
- ALTER TABLE ADD COLUMN / DROP COLUMN
"""

import logging
import re
from sqlalchemy import (
    MetaData, Table, Column, BigInteger, String, DateTime, Text,
    Index, ForeignKey, UniqueConstraint, inspect, text,
)
from sqlalchemy.sql import func
from sqlalchemy.engine import Engine

from app.core.field_types import get_column_type, get_constraints
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# Regex fuer sichere SQL-Identifier (Tabellen-/Spaltennamen)
_SAFE_IDENTIFIER = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]{0,126}$")


def _assert_safe_identifier(name: str, context: str = "identifier") -> None:
    """Stellt sicher, dass ein Name als SQL-Identifier sicher ist.

    Verhindert SQL-Injection ueber Tabellen-/Spaltennamen.
    """
    if not _SAFE_IDENTIFIER.match(name):
        raise ValueError(
            f"Unsafe {context}: '{name}'. "
            f"Must match ^[a-zA-Z_][a-zA-Z0-9_]{{0,126}}$ (letters, digits, underscore)."
        )


def get_table_name(bo_code: str) -> str:
    """Generate table name from BO code."""
    table_name = f"{settings.bo_table_prefix}{bo_code.lower()}"
    _assert_safe_identifier(table_name, "table name")
    return table_name


def build_columns(fields) -> list[Column]:
    """Build SQLAlchemy columns from FieldDefinitions."""
    columns = []
    for field in fields:
        _assert_safe_identifier(field.code, "column name")
        col_type = get_column_type(field)
        col_kwargs = {
            "nullable": not field.required,
        }

        # Reference -> Foreign Key
        if field.field_type == "reference" and field.reference_bo_code:
            ref_table = get_table_name(field.reference_bo_code)
            col = Column(
                field.code, col_type,
                ForeignKey(f"{ref_table}.id", ondelete="SET NULL"),
                **col_kwargs,
            )
        else:
            col = Column(field.code, col_type, **col_kwargs)

        columns.append(col)
    return columns


def create_bo_table(engine: Engine, bo_definition, fields) -> str:
    """Create a real PostgreSQL table for a BO definition.

    Returns the table name.
    """
    table_name = bo_definition.table_name
    _assert_safe_identifier(table_name, "table name")
    metadata = MetaData()

    # Reflect referenced tables so ForeignKey resolution works
    ref_tables = set()
    for field in fields:
        if field.field_type == "reference" and field.reference_bo_code:
            ref_table = get_table_name(field.reference_bo_code)
            ref_tables.add(ref_table)
    for ref_table in ref_tables:
        if table_exists(engine, ref_table):
            Table(ref_table, metadata, autoload_with=engine)

    # System columns (always present)
    system_columns = [
        Column("id", BigInteger, primary_key=True, autoincrement=True),
        Column("_state", String(100), nullable=True, index=True),
        Column("_created_at", DateTime(timezone=True), server_default=func.now()),
        Column("_updated_at", DateTime(timezone=True), server_default=func.now()),
        Column("_created_by", String(200), nullable=True),
        Column("_notes", Text, nullable=True),
    ]

    # Custom columns from field definitions
    custom_columns = build_columns(fields)

    # Constraints
    all_constraints = []
    for field in fields:
        all_constraints.extend(get_constraints(field, table_name))

    # Unique constraints
    for field in fields:
        if field.unique:
            all_constraints.append(
                UniqueConstraint(field.code, name=f"uq_{table_name}_{field.code}")
            )

    table = Table(
        table_name,
        metadata,
        *system_columns,
        *custom_columns,
        *all_constraints,
    )

    # Indexes for searchable/indexed fields
    for field in fields:
        if field.indexed or field.is_searchable:
            Index(f"ix_{table_name}_{field.code}", table.c[field.code])

    # Create table
    metadata.create_all(engine)
    logger.info(f"Created table: {table_name}")
    return table_name


def add_column(engine: Engine, table_name: str, field) -> None:
    """Add a column to an existing BO table."""
    _assert_safe_identifier(table_name, "table name")
    _assert_safe_identifier(field.code, "column name")

    col_type = get_column_type(field)
    type_str = col_type.compile(dialect=engine.dialect)
    nullable = "NULL" if not field.required else "NOT NULL"

    # Parametrisierter Default-Wert (kein f-String!)
    sql = f'ALTER TABLE "{table_name}" ADD COLUMN "{field.code}" {type_str} {nullable}'

    with engine.begin() as conn:
        if field.default_value is not None:
            # Sicherer parametrisierter Default via SET DEFAULT
            conn.execute(text(sql))
            conn.execute(text(
                f'ALTER TABLE "{table_name}" ALTER COLUMN "{field.code}" SET DEFAULT :default_val'
            ), {"default_val": field.default_value})
        else:
            conn.execute(text(sql))

    logger.info(f"Added column {field.code} to {table_name}")


def drop_column(engine: Engine, table_name: str, column_code: str) -> None:
    """Remove a column from a BO table."""
    _assert_safe_identifier(table_name, "table name")
    _assert_safe_identifier(column_code, "column name")

    with engine.begin() as conn:
        conn.execute(text(f'ALTER TABLE "{table_name}" DROP COLUMN IF EXISTS "{column_code}"'))
    logger.info(f"Dropped column {column_code} from {table_name}")


def drop_bo_table(engine: Engine, table_name: str) -> None:
    """Drop a BO table entirely."""
    _assert_safe_identifier(table_name, "table name")

    with engine.begin() as conn:
        conn.execute(text(f'DROP TABLE IF EXISTS "{table_name}" CASCADE'))
    logger.info(f"Dropped table: {table_name}")


def table_exists(engine: Engine, table_name: str) -> bool:
    """Check if a table exists."""
    insp = inspect(engine)
    return insp.has_table(table_name)


def get_table_columns(engine: Engine, table_name: str) -> list[dict]:
    """Get column info from an existing table."""
    insp = inspect(engine)
    if not insp.has_table(table_name):
        return []
    return [
        {"name": col["name"], "type": str(col["type"]), "nullable": col["nullable"]}
        for col in insp.get_columns(table_name)
    ]
