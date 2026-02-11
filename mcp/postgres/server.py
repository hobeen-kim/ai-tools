import asyncio
import argparse
import base64
import os
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any, Dict, List, Optional

import asyncpg
from mcp.server.fastmcp import FastMCP


mcp = FastMCP(
    "postgres",
    instructions=(
        "PostgreSQL에 연결해 스키마/테이블 정보를 조회하거나 SQL을 실행합니다. "
        "기본은 읽기 전용이며, 쓰기 실행은 환경변수로 명시적으로 허용해야 합니다."
    ),
)


_pool: Optional[asyncpg.Pool] = None
_pool_lock = asyncio.Lock()


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "t", "yes", "y", "on"}


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError as e:
        raise ValueError(f"Invalid int env {name}={value!r}") from e


def _build_dsn() -> str:
    dsn = os.getenv("DATABASE_URL") or os.getenv("DATABASE_URI")
    if dsn:
        return dsn

    host = os.getenv("PGHOST")
    db = os.getenv("PGDATABASE")
    user = os.getenv("PGUSER")
    password = os.getenv("PGPASSWORD")
    port = os.getenv("PGPORT", "5432")

    if not (host and db and user):
        raise RuntimeError(
            "Missing database config. Set DATABASE_URL (or DATABASE_URI), or set PGHOST/PGDATABASE/PGUSER(/PGPASSWORD/PGPORT)."
        )

    auth = user
    if password:
        auth = f"{user}:{password}"
    return f"postgresql://{auth}@{host}:{port}/{db}"


async def _get_pool() -> asyncpg.Pool:
    global _pool

    if _pool is not None:
        return _pool

    async with _pool_lock:
        if _pool is not None:
            return _pool

        dsn = _build_dsn()
        max_conns = _env_int("PG_POOL_MAX", 5)
        command_timeout_s = _env_int("PG_COMMAND_TIMEOUT_S", 10)

        _pool = await asyncpg.create_pool(
            dsn=dsn,
            min_size=1,
            max_size=max_conns,
            command_timeout=command_timeout_s,
        )
        return _pool


def _jsonable(value: Any) -> Any:
    if value is None:
        return None

    if isinstance(value, (str, int, float, bool)):
        return value

    if isinstance(value, Decimal):
        return str(value)

    if isinstance(value, (datetime, date, time)):
        return value.isoformat()

    if isinstance(value, (bytes, bytearray, memoryview)):
        raw = bytes(value)
        return {
            "__type": "bytes_b64",
            "data": base64.b64encode(raw).decode("ascii"),
        }

    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}

    if isinstance(value, (list, tuple, set)):
        return [_jsonable(v) for v in value]

    return str(value)


async def _with_timeout(conn: asyncpg.Connection) -> None:
    statement_timeout_ms = _env_int("PG_STATEMENT_TIMEOUT_MS", 15000)
    await conn.execute(f"SET LOCAL statement_timeout = {statement_timeout_ms}")


@mcp.tool()
async def pg_healthcheck() -> Dict[str, Any]:
    """DB 연결 및 서버 버전 확인"""

    pool = await _get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await _with_timeout(conn)
            version = await conn.fetchval("select version()")
            current_db = await conn.fetchval("select current_database()")
    return {"ok": True, "database": current_db, "version": version}


@mcp.tool()
async def pg_list_schemas() -> List[str]:
    """스키마 목록"""

    sql = """
        select schema_name
        from information_schema.schemata
        order by schema_name
    """.strip()

    pool = await _get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await _with_timeout(conn)
            rows = await conn.fetch(sql)
    return [r["schema_name"] for r in rows]


@mcp.tool()
async def pg_list_tables(schema: str = "public") -> List[Dict[str, Any]]:
    """테이블/뷰 목록"""

    sql = """
        select table_schema, table_name, table_type
        from information_schema.tables
        where table_schema = $1
        order by table_name
    """.strip()

    pool = await _get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await _with_timeout(conn)
            rows = await conn.fetch(sql, schema)

    return [
        {"schema": r["table_schema"], "name": r["table_name"], "type": r["table_type"]}
        for r in rows
    ]


@mcp.tool()
async def pg_describe_table(schema: str, table: str) -> List[Dict[str, Any]]:
    """테이블 컬럼/타입/널 가능/기본값"""

    sql = """
        select
            column_name,
            data_type,
            is_nullable,
            column_default,
            ordinal_position
        from information_schema.columns
        where table_schema = $1 and table_name = $2
        order by ordinal_position
    """.strip()

    pool = await _get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await _with_timeout(conn)
            rows = await conn.fetch(sql, schema, table)

    return [
        {
            "name": r["column_name"],
            "type": r["data_type"],
            "nullable": r["is_nullable"] == "YES",
            "default": _jsonable(r["column_default"]),
            "position": r["ordinal_position"],
        }
        for r in rows
    ]


@mcp.tool()
async def pg_query(
    sql: str, params: Optional[List[Any]] = None, limit: Optional[int] = None
) -> Dict[str, Any]:
    """SELECT 등 결과 행이 있는 쿼리 실행 (기본 row limit 적용)"""

    max_rows = limit if limit is not None else _env_int("PG_MAX_ROWS", 200)
    if max_rows <= 0:
        raise ValueError("limit must be > 0")

    pool = await _get_pool()
    params = params or []

    rows: List[asyncpg.Record] = []
    truncated = False
    async with pool.acquire() as conn:
        async with conn.transaction():
            await _with_timeout(conn)
            cursor = conn.cursor(sql, *params)
            async for record in cursor:
                rows.append(record)
                if len(rows) > max_rows:
                    truncated = True
                    rows = rows[:max_rows]
                    break

    columns: List[str] = []
    if rows:
        columns = list(rows[0].keys())

    json_rows = [_jsonable(dict(r)) for r in rows]
    return {
        "columns": columns,
        "rows": json_rows,
        "row_count": len(rows),
        "truncated": truncated,
    }


@mcp.tool()
async def pg_execute(sql: str, params: Optional[List[Any]] = None) -> Dict[str, Any]:
    """INSERT/UPDATE/DDL 등 실행 (기본은 차단, PG_ALLOW_WRITE=true 필요)"""

    if not _env_bool("PG_ALLOW_WRITE", False):
        raise PermissionError(
            "Writes are disabled. Set PG_ALLOW_WRITE=true to enable pg_execute."
        )

    pool = await _get_pool()
    params = params or []
    async with pool.acquire() as conn:
        async with conn.transaction():
            await _with_timeout(conn)
            status = await conn.execute(sql, *params)
    return {"status": status}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument(
        "--access-mode",
        choices=["readonly", "unrestricted"],
        default=None,
        help="readonly(default) or unrestricted(allows writes)",
    )
    args, _unknown = parser.parse_known_args()

    if args.access_mode == "unrestricted":
        os.environ.setdefault("PG_ALLOW_WRITE", "true")

    mcp.run()
