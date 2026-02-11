# postgres MCP (Python)

PostgreSQL에 연결해서 스키마/테이블 정보를 조회하거나 SQL을 실행하는 MCP 서버입니다.

## 제공 도구(tools)

- `pg_healthcheck()` - DB 연결 및 버전 확인
- `pg_list_schemas()` - 스키마 목록
- `pg_list_tables(schema="public")` - 테이블/뷰 목록
- `pg_describe_table(schema, table)` - 컬럼/타입/널 가능/기본값
- `pg_query(sql, params?, limit?)` - 결과 행이 있는 쿼리 실행(기본 row limit 적용)
- `pg_execute(sql, params?)` - INSERT/UPDATE/DDL 등 실행 (기본 차단)

## 환경변수(세팅)

권장:

- `DATABASE_URL` 또는 `DATABASE_URI` 예: `postgresql://user:pass@host:5432/dbname`

대안:

- `PGHOST`, `PGPORT`(기본 5432), `PGDATABASE`, `PGUSER`, `PGPASSWORD`(옵션)

동작 옵션

- `PG_ACCESS_MODE` (기본 readonly) - `readonly` | `limited` | `unrestricted`
- `PG_MAX_ROWS` (기본 200) - `pg_query` 기본 최대 행
- `PG_STATEMENT_TIMEOUT_MS` (기본 15000) - statement timeout(ms)
- `PG_POOL_MAX` (기본 5) - 커넥션 풀 max
- `PG_COMMAND_TIMEOUT_S` (기본 10) - 커맨드 타임아웃(초)

Access mode 의미:

- `readonly`: 읽기만 가능(SELECT 계열만 허용). `pg_execute`는 차단.
- `limited`:
  - DML 허용(INSERT/UPDATE/DELETE) 단, UPDATE/DELETE는 WHERE 필수
  - DCL 차단(GRANT/REVOKE 등)
  - DDL은 허용하되 DROP/TRUNCATE 차단
- `unrestricted`: 제한 없음

## 로컬 실행(개발)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r mcp/postgres/requirements.txt

export PGHOST=host.docker.internal
export PGDATABASE=dbname
export PGUSER=username
export PGPASSWORD=password
export PGPORT=5432

python3 mcp/postgres/server.py
```

## Docker로 실행

빌드:

```bash
docker build -t mcp-postgres:local .
```

실행(중요: MCP는 stdio 기반이라 `-i` 필요):

```bash
docker run --rm -i \
  -e DATABASE_URI='postgresql://user:pass@host:5432/dbname' \
  mcp-postgres:local --access-mode=readonly
```

로컬(호스트) Postgres에 붙는 경우:

- macOS/Windows: `host.docker.internal` 사용

```bash
docker run --rm -i \
  -e DATABASE_URI='postgresql://user:pass@host.docker.internal:5432/dbname' \
  mcp-postgres:local --access-mode=readonly
```

- Linux: `--network=host` 또는 DB를 동일 네트워크에 두고 hostname을 맞춰주세요.

## MCP 클라이언트 설정 예시

OpenCode에서는 `opencode.json`/`opencode.jsonc`의 `mcp`에 MCP 서버를 추가합니다.

예시(opencode.jsonc):

```jsonc
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "postgres": {
      "type": "local",
      "command": [
        "docker",
        "run",
        "--rm",
        "-i",
        "--env-file",
        ".env",
        "sksjsksh32/mcp-postgres:latest",
        "--access-mode=limited"
      ],
      "enabled": true,
      "timeout": 10000
    }
  }
}
```

- Docker로 stdio MCP를 띄우는 경우 `-i`가 필요합니다.
- OpenCode의 `mcp.*.environment`는 OS 환경변수를 주입하는 용도이며, `.env`를 자동으로 읽지는 않습니다. `.env`를 쓰려면 위처럼 `docker run --env-file .env`를 사용하세요.
- `--access-mode` 대신 `PG_ACCESS_MODE`를 환경변수로 주입해도 됩니다.

`.env` 예시(커밋 금지):

```bash
# Postgres 연결
DATABASE_URI=postgresql://username:password@host.docker.internal:5432/dbname

# 옵션
PG_ACCESS_MODE=limited
PG_MAX_ROWS=200
PG_STATEMENT_TIMEOUT_MS=15000
PG_POOL_MAX=5
PG_COMMAND_TIMEOUT_S=10

# (선택) HTTP로 노출해서 쓰는 경우에만
# EXPOSE=true
# HOST=0.0.0.0
# PORT=8000
```
