"""Query Engine - Dynamische Abfragen auf BO-Tabellen.

Verwendet run_sync fuer Table-Reflection und raw connection
fuer alle dynamischen Operationen.
"""

from sqlalchemy import MetaData, Table, select, func, text, desc, asc
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import sync_engine

settings = get_settings()

# Filter operators
OPERATORS = {
    "eq": lambda col, val: col == val,
    "ne": lambda col, val: col != val,
    "gt": lambda col, val: col > val,
    "gte": lambda col, val: col >= val,
    "lt": lambda col, val: col < val,
    "lte": lambda col, val: col <= val,
    "contains": lambda col, val: col.ilike(f"%{val}%"),
    "startswith": lambda col, val: col.ilike(f"{val}%"),
    "endswith": lambda col, val: col.ilike(f"%{val}"),
    "in": lambda col, val: col.in_(val.split(",") if isinstance(val, str) else val),
    "isnull": lambda col, val: col.is_(None) if val.lower() == "true" else col.isnot(None),
}

# Cache for reflected tables
_table_cache: dict[str, Table] = {}


def _get_table(table_name: str) -> Table:
    """Reflect a dynamic table (uses sync engine, cached)."""
    if table_name not in _table_cache:
        metadata = MetaData()
        _table_cache[table_name] = Table(table_name, metadata, autoload_with=sync_engine)
    return _table_cache[table_name]


def invalidate_table_cache(table_name: str | None = None):
    """Clear table cache after schema changes."""
    if table_name:
        _table_cache.pop(table_name, None)
    else:
        _table_cache.clear()


def _parse_filters(table: Table, params: dict) -> list:
    filters = []
    skip_keys = {"page", "page_size", "sort", "fields"}
    for key, value in params.items():
        if key in skip_keys:
            continue
        if "__" in key:
            field_name, op = key.rsplit("__", 1)
        else:
            field_name, op = key, "eq"
        if field_name not in table.c:
            continue
        op_func = OPERATORS.get(op)
        if op_func:
            filters.append(op_func(table.c[field_name], value))
    return filters


def _parse_sort(table: Table, sort_str: str | None) -> list:
    if not sort_str:
        return [desc(table.c["_created_at"])]
    order_cols = []
    for part in sort_str.split(","):
        part = part.strip()
        if part.startswith("-"):
            col_name = part[1:]
            direction = desc
        else:
            col_name = part
            direction = asc
        if col_name in table.c:
            order_cols.append(direction(table.c[col_name]))
    return order_cols or [desc(table.c["_created_at"])]


async def query_bo_table(session: AsyncSession, table_name: str, params: dict) -> dict:
    table = _get_table(table_name)
    page = int(params.get("page", 1))
    page_size = min(int(params.get("page_size", 20)), 100)
    offset = (page - 1) * page_size
    filters = _parse_filters(table, params)

    def _run(connection):
        # Count
        count_q = select(func.count()).select_from(table)
        for f in filters:
            count_q = count_q.where(f)
        total = connection.execute(count_q).scalar()

        # Data
        query = select(table)
        for f in filters:
            query = query.where(f)
        for sc in _parse_sort(table, params.get("sort")):
            query = query.order_by(sc)
        query = query.limit(page_size).offset(offset)
        rows = [dict(row._mapping) for row in connection.execute(query)]

        return {"items": rows, "total": total, "page": page,
                "page_size": page_size, "pages": (total + page_size - 1) // page_size}

    conn = await session.connection()
    return await conn.run_sync(_run)


async def get_bo_record(session: AsyncSession, table_name: str, record_id: int) -> dict | None:
    table = _get_table(table_name)

    def _run(connection):
        result = connection.execute(select(table).where(table.c["id"] == record_id))
        row = result.first()
        return dict(row._mapping) if row else None

    conn = await session.connection()
    return await conn.run_sync(_run)


async def insert_bo_record(session: AsyncSession, table_name: str, data: dict) -> dict:
    table = _get_table(table_name)

    def _run(connection):
        result = connection.execute(table.insert().values(**data).returning(table))
        return dict(result.first()._mapping)

    conn = await session.connection()
    result = await conn.run_sync(_run)
    await session.commit()
    return result


async def update_bo_record(session: AsyncSession, table_name: str, record_id: int, data: dict) -> dict | None:
    table = _get_table(table_name)
    from sqlalchemy.sql import func as sqlfunc
    data["_updated_at"] = sqlfunc.now()

    def _run(connection):
        result = connection.execute(
            table.update().where(table.c["id"] == record_id).values(**data).returning(table)
        )
        row = result.first()
        return dict(row._mapping) if row else None

    conn = await session.connection()
    result = await conn.run_sync(_run)
    await session.commit()
    return result


async def delete_bo_record(session: AsyncSession, table_name: str, record_id: int) -> bool:
    table = _get_table(table_name)

    def _run(connection):
        result = connection.execute(table.delete().where(table.c["id"] == record_id))
        return result.rowcount > 0

    conn = await session.connection()
    result = await conn.run_sync(_run)
    await session.commit()
    return result
