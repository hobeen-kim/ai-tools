# MCP 기본

이 저장소의 `mcp/` 아래에는 OpenCode에서 사용할 MCP(Model Context Protocol) 서버들을 모아둡니다.

## OpenCode에서 MCP 활성화

OpenCode 설정 파일(`opencode.json`/`opencode.jsonc`)의 `mcp`에 서버를 추가합니다.

### Local MCP

로컬 MCP는 OpenCode가 로컬에서 커맨드를 실행해 stdio로 통신하는 방식입니다.

- `type`: 반드시 `"local"`
- `command`: 실행 커맨드/인자 배열
- `environment`: 실행 시 주입할 환경변수 오브젝트(선택)
- `enabled`: 서버 활성화 여부(선택)
- `timeout`: 툴 목록을 가져올 때 타임아웃(ms, 기본 5000)(선택)

예시(opencode.jsonc):

```jsonc
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "my-local-mcp": {
      "type": "local",
      "command": ["npx", "-y", "my-mcp-command"],
      "environment": {
        "MY_ENV": "{env:MY_ENV}"
      },
      "enabled": true,
      "timeout": 10000
    }
  }
}
```

### Remote MCP

원격 MCP는 HTTP로 연결하는 방식입니다.

- `type`: 반드시 `"remote"`
- `url`: MCP 서버 URL
- `headers`: 요청 헤더(선택)
- `oauth`: OAuth 설정(선택)
- `enabled`, `timeout`: 선택

## 주의사항

- MCP 서버의 툴/설명은 모델 컨텍스트에 추가되므로, 많이 켜면 토큰을 빠르게 소모합니다.
- 비밀값(API 키/DB 비밀번호 등)은 파일에 직접 적지 말고 `{env:...}`로 환경변수를 참조하세요.

## MCP 웹 테스트

일부 MCP는 기본(stdio) 외에, HTTP로도 접근할 수 있도록 `EXPOSE` 환경변수를 지원합니다.

### 1) HTTP로 노출(EXPOSE)

- `EXPOSE=true`일 때만 HTTP 트랜스포트로 뜨도록 구현합니다.
- (일반적으로) `HOST`/`PORT`로 바인딩 주소/포트를 제어합니다.

Docker 예시:

```bash
docker run --rm -i \
  -e EXPOSE=true \
  -e HOST=0.0.0.0 \
  -e PORT=8000 \
  -p 8000:8000 \
  <image>
```

### 2) Inspector로 연결(가장 쉬움)

로컬에서 Inspector 실행:

```bash
npx @modelcontextprotocol/inspector
```

브라우저에서 연결:

- Transport: `Streamable HTTP` (UI에 따라 이름이 다를 수 있음)
- URL: `http://localhost:8000/mcp`

Connect 후 Tools 목록에서 `pg_healthcheck`를 실행합니다.

`{"ok": true, "database": "...", "version": "..."}` 형태로 나오면 정상입니다.

### 3) curl로 엔드포인트 확인

서버가 떠 있는지 빠르게 확인:

```bash
curl -i http://localhost:8000/mcp
```

트랜스포트/경로가 안 맞으면(예: 404/405/406) Inspector의 Transport/URL을 서버 구현에 맞게 맞춰야 합니다.
