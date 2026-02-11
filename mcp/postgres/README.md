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

권장: `DATABASE_URL` 하나로 설정

- `DATABASE_URL` (권장) 예: `postgresql://user:pass@host:5432/dbname`

호환(alias):

- `DATABASE_URI` - `DATABASE_URL` 대신 사용 가능

대안: 아래 조합으로도 가능

- `PGHOST`, `PGPORT`(기본 5432), `PGDATABASE`, `PGUSER`, `PGPASSWORD`(옵션)

동작 옵션

- `PG_ALLOW_WRITE` (기본 false) - `pg_execute` 활성화: `true`
- `PG_MAX_ROWS` (기본 200) - `pg_query` 기본 최대 행
- `PG_STATEMENT_TIMEOUT_MS` (기본 15000) - statement timeout(ms)
- `PG_POOL_MAX` (기본 5) - 커넥션 풀 max
- `PG_COMMAND_TIMEOUT_S` (기본 10) - 커맨드 타임아웃(초)

## 로컬 실행(개발)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r mcp/postgres/requirements.txt

export DATABASE_URL='postgresql://user:pass@localhost:5432/dbname'
python3 mcp/postgres/server.py
```

## Docker로 실행

빌드:

```bash
docker build -t mcp-postgres:local mcp/postgres
```

실행(중요: MCP는 stdio 기반이라 `-i` 필요):

```bash
docker run --rm -i \
  -e DATABASE_URL='postgresql://user:pass@host:5432/dbname' \
  mcp-postgres:local
```

로컬(호스트) Postgres에 붙는 경우:

- macOS/Windows: `host.docker.internal` 사용

```bash
docker run --rm -i \
  -e DATABASE_URL='postgresql://user:pass@host.docker.internal:5432/dbname' \
  mcp-postgres:local
```

- Linux: `--network=host` 또는 DB를 동일 네트워크에 두고 hostname을 맞춰주세요.

## MCP 클라이언트 설정 예시

클라이언트가 `command`/`args`로 MCP 서버를 실행하는 형태라면(예: 데스크톱 앱/CLI 설정), Docker를 직접 스폰하도록 구성할 수 있습니다.

예시(JSON 컨셉):

```json
{
  "mcpServers": {
    "postgres": {
      "command": "docker",
      "args": [
        "run",
        "--rm",
        "-i",
        "-e",
        "DATABASE_URI",
        "mcp-postgres:local",
        "--access-mode=readonly"
      ],
      "env": {
        "DATABASE_URI": "postgresql://username:password@localhost:5432/dbname"
      }
    }
  }
}
```

쓰기 허용이 필요하면 `--access-mode=unrestricted`를 주거나, `PG_ALLOW_WRITE=true`를 env로 설정하세요.
