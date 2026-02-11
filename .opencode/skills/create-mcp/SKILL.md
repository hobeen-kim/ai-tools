# create-mcp

이 스킬은 이 저장소에 "새 MCP 서버"를 추가할 때, 재현 가능한 형태로 스캐폴딩(코드/도커/문서)을 만드는 절차를 제공합니다.

## 목표

- `mcp/<name>/` 아래에 MCP 서버를 추가한다.
- Docker로 실행 가능해야 한다(`Dockerfile`).
- 설정/실행/클라이언트 연결 방법을 `mcp/<name>/README.md`에 문서화한다.
- 비밀값(API 키/DB 비밀번호 등)은 절대 커밋하지 않고 환경변수로만 받는다.

## 기본 결정(권장 디폴트)

- 언어: Python
- 트랜스포트: stdio (MCP 클라이언트가 프로세스를 스폰하는 방식)
- 모든 MCP는 `EXPOSE` boolean 환경변수를 지원해야 한다. `EXPOSE=true`인 경우 `streamable-http` 트랜스포트로 실행 가능해야 한다.
- 의존성: `mcp`(Python SDK) + 대상 시스템 클라이언트 라이브러리
- 쓰기 작업이 가능한 도구는 기본 비활성화(명시적 env로만 허용)

## 산출물(필수 파일)

아래 파일은 항상 만든다.

- `mcp/<name>/server.py` - MCP 서버 엔트리포인트
- `mcp/<name>/requirements.txt` - Python 의존성
- `mcp/<name>/Dockerfile` - 컨테이너 실행
- `mcp/<name>/README.md` - 실행/세팅/사용 방법

## 절차

### 1) 디렉토리 생성

`mcp/<name>/` 를 생성하고 위의 필수 파일 4개를 만든다.

### 2) server.py 구현

- `FastMCP("<name>")`로 서버를 정의한다.
- `@mcp.tool()`로 도구를 노출한다.
- 연결 정보는 환경변수로만 받는다(예: `DATABASE_URL`).
- 반환값은 JSON 직렬화 가능한 타입으로 변환한다(날짜/decimal/bytes 등).
- 위험한 도구(삭제/DDL/쓰기)는 기본 차단하고, `--access-mode` 또는 `PG_ACCESS_MODE` 같은 명시적 설정으로만 활성화한다.
- `EXPOSE=true`이면 `mcp.run(transport="streamable-http", host=..., port=...)`로 실행하고, 기본은 `mcp.run()`(stdio)로 실행한다.

템플릿(개념):

```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("<name>")

@mcp.tool()
def healthcheck():
    return {"ok": True}

if __name__ == "__main__":
    expose = os.getenv("EXPOSE", "").strip().lower() in {"1", "true", "t", "yes", "y", "on"}
    if expose:
        host = os.getenv("HOST", "0.0.0.0")
        port = int(os.getenv("PORT", "8000"))
        mcp.run(transport="streamable-http", host=host, port=port)
    else:
        mcp.run()
```

### 3) requirements.txt 작성

- `mcp`는 필수
- 대상 시스템 클라이언트(예: Postgres면 `asyncpg`/`psycopg`) 추가

예:

```text
mcp>=0.1.0
asyncpg>=0.29.0
```

### 4) Dockerfile 작성

- 베이스 이미지: `python:3.12-slim` 권장
- `requirements.txt` 설치 후 `server.py` 실행
- stdio 기반이므로 포트 노출은 기본적으로 불필요
- `EXPOSE=true`로 HTTP 트랜스포트를 사용할 계획이면, 런타임에서 `-p <host_port>:<PORT>`로 포트를 매핑한다

템플릿:

```dockerfile
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY server.py /app/server.py
ENTRYPOINT ["python", "/app/server.py"]
```

### 5) README.md 문서화(필수 항목)

- 제공 도구 목록(이름/역할)
- 환경변수 목록(필수/옵션, 기본값)
- 로컬 실행 방법
- Docker 빌드/실행 방법
- "클라이언트가 어떻게 이 서버를 실행하는지" 설정 예시(예: `command: docker`, `args: [run, ...]`)

특히 Docker 실행은 stdio이므로 `docker run -i`가 필요하다는 점을 명시한다.

권한 제어가 필요한 MCP라면, `readonly`/`limited`/`unrestricted`처럼 단계적인 access-mode를 제공하고 README에 정책을 명확히 적는다.

### 6) 검증(최소)

- 문법 체크: `python -m py_compile mcp/<name>/server.py`
- 도커 빌드: `docker build -t mcp-<name>:local mcp/<name>`

## 금지사항

- `.env`/비밀번호/토큰/개인키 등 비밀값을 파일로 추가하거나 커밋하지 않는다.
- 쓰기/파괴적 동작을 디폴트로 켜지 않는다.
- 타입/에러를 숨기기 위한 무의미한 예외 삼키기(`except: pass`)를 하지 않는다.
