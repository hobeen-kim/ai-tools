import asyncio
import argparse
import base64
import os
import re
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any, Dict, List, Optional

import asyncpg
from mcp.server.fastmcp import FastMCP


mcp = FastMCP(
    "postgres",
    instructions=(
        "PostgreSQL에 연결해 스키마/테이블 정보를 조회하거나 SQL을 실행합니다. "
        "기본은 읽기 전용이며, access-mode(readonly/limited/unrestricted)로 권한을 제어합니다."
    ),
)


_pool: Optional[asyncpg.Pool] = None
_pool_lock = asyncio.Lock()

_ACCESS_MODE = (os.getenv("PG_ACCESS_MODE") or "readonly").strip().lower()


def _set_access_mode(mode: str) -> None:
    global _ACCESS_MODE
    normalized = (mode or "").strip().lower()
    if normalized not in {"readonly", "limited", "unrestricted"}:
        raise ValueError("access mode must be one of: readonly, limited, unrestricted")
    _ACCESS_MODE = normalized


def _get_access_mode() -> str:
    return _ACCESS_MODE


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


def _strip_sql_for_policy(sql: str) -> str:
    """권한 정책 체크를 위한 보수적 전처리.

    주의: 완전한 SQL 파서가 아니다. 제한 모드에서 안전하게 막기 위한 용도다.
    """

    out: List[str] = []
    i = 0
    n = len(sql)

    while i < n:
        ch = sql[i]

        # Line comments: -- ...\n
        if sql.startswith("--", i):
            i += 2
            while i < n and sql[i] != "\n":
                i += 1
            out.append(" ")
            continue

        # Block comments: /* ... */
        if sql.startswith("/*", i):
            i += 2
            while i + 1 < n and not sql.startswith("*/", i):
                i += 1
            i = min(n, i + 2)
            out.append(" ")
            continue

        # Single-quoted strings: '...'
        if ch == "'":
            i += 1
            while i < n:
                if sql[i] == "'":
                    if i + 1 < n and sql[i + 1] == "'":
                        i += 2
                        continue
                    i += 1
                    break
                i += 1
            out.append(" ")
            continue

        # Double-quoted identifiers: "..."
        if ch == '"':
            i += 1
            while i < n:
                if sql[i] == '"':
                    if i + 1 < n and sql[i + 1] == '"':
                        i += 2
                        continue
                    i += 1
                    break
                i += 1
            out.append(" ")
            continue

        # Dollar-quoted strings: $tag$...$tag$
        if ch == "$":
            m = re.match(r"\$[A-Za-z0-9_]*\$", sql[i:])
            if m:
                tag = m.group(0)
                i += len(tag)
                end = sql.find(tag, i)
                if end == -1:
                    out.append(" ")
                    break
                i = end + len(tag)
                out.append(" ")
                continue

        out.append(ch)
        i += 1

    return "".join(out)


def _ensure_single_statement(sql_for_policy: str) -> str:
    s = sql_for_policy.strip()
    s = s.rstrip(";").strip()
    if ";" in s:
        raise PermissionError("Multiple statements are not allowed.")
    return s


def _require_where_for_update_delete(sql_for_policy_lower: str) -> None:
    lowered = sql_for_policy_lower
    update_idx = lowered.find("update")
    delete_idx = lowered.find("delete")

    def has_word_at(idx: int, word: str) -> bool:
        if idx < 0:
            return False
        before_ok = idx == 0 or not lowered[idx - 1].isalnum()
        after = idx + len(word)
        after_ok = after >= len(lowered) or not lowered[after].isalnum()
        return before_ok and after_ok

    first_kind = None
    first_idx = None
    if has_word_at(update_idx, "update"):
        first_kind, first_idx = "update", update_idx
    if has_word_at(delete_idx, "delete"):
        if first_idx is None or delete_idx < first_idx:
            first_kind, first_idx = "delete", delete_idx

    if first_kind is None or first_idx is None:
        return

    tail = lowered[first_idx:]
    if " where " not in tail and not tail.endswith(" where"):
        raise PermissionError(
            f"{first_kind.upper()} requires a WHERE clause in limited access mode."
        )


def _enforce_access_policy(sql: str, tool_name: str) -> None:
    mode = _get_access_mode()
    if mode == "unrestricted":
        return

    stripped = _strip_sql_for_policy(sql)
    single = _ensure_single_statement(stripped)
    lowered = single.lower()

    if mode == "readonly":
        if tool_name == "pg_execute":
            raise PermissionError("pg_execute is not allowed in readonly access mode.")

        if not re.match(r"^\s*(select|with|explain)\b", lowered):
            raise PermissionError(
                "Only SELECT queries are allowed in readonly access mode."
            )

        if re.search(
            r"\b(insert|update|delete|create|alter|drop|truncate|grant|revoke|call|do)\b",
            lowered,
        ):
            raise PermissionError("Readonly access mode blocks DML/DDL/DCL statements.")

        if re.match(r"^\s*explain\b", lowered) and not re.search(
            r"\b(select|with)\b", lowered
        ):
            raise PermissionError("EXPLAIN is only allowed for SELECT queries.")
        return

    if mode == "limited":
        if re.search(r"\b(grant|revoke)\b", lowered):
            raise PermissionError(
                "DCL (GRANT/REVOKE) is not allowed in limited access mode."
            )

        if re.search(r"\b(drop|truncate)\b", lowered):
            raise PermissionError(
                "DROP/TRUNCATE are not allowed in limited access mode."
            )

        if re.search(r"\balter\s+system\b", lowered):
            raise PermissionError("ALTER SYSTEM is not allowed in limited access mode.")

        _require_where_for_update_delete(lowered)
        return

    raise ValueError(f"Unknown access mode: {mode!r}")


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

    _enforce_access_policy(sql, tool_name="pg_query")

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
    """INSERT/UPDATE/DDL 등 실행 (access-mode에 따라 제한)"""

    _enforce_access_policy(sql, tool_name="pg_execute")

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
        choices=["readonly", "limited", "unrestricted"],
        default=None,
        help="readonly(default), limited, or unrestricted",
    )
    args, _unknown = parser.parse_known_args()

    if args.access_mode:
        _set_access_mode(args.access_mode)

    mcp.run()
