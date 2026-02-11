# AGENTS.md

This repo is **custom-repo**. This file is the working agreement for humans and automation (CI, bots, AI agents).

## Instruction
- 한국어로 답변한다.
- TODO는 `TODO-Issue.md`에 기록한다.
- 에이전트 리소스 기본 경로는 `.agents` 이다.

## 새로운 Issue 시작
1. GitHub에서 이슈 번호로 Issue를 읽고 `TODO-Issue.md`에 실행 과제를 작성한다. (기존 내용은 무시)
2. Issue type에 따라 필요한 문서/코드 변경을 수행한다.
3. PR/커밋 메시지는 변경 요약 + 이슈 번호를 포함한다.

## 변경 규칙
- 가능한 작은 단위로 커밋한다.
- 테스트/빌드가 필요한 경우 반드시 수행한다.
- 문서 변경이 필요하면 README/관련 문서도 함께 갱신한다.

## 추가 규칙
- 이 저장소는 커스텀 MCP 서버/툴과 에이전트 프롬프트/설정을 모아두는 용도다.
- 새로운 에이전트를 추가할 때는 `.agents/` 아래에 에이전트별 문서(역할, 사용 시점, 금지사항, 예시)를 함께 둔다.
- MCP/에이전트 설정에 비밀값(API 키, 토큰, 개인키 등)은 절대 커밋하지 말고, 환경변수/로컬 시크릿으로 관리한다.
- 에이전트 문서/프롬프트는 재현 가능하게(입력/출력 형식, 성공 기준, 사용 도구 범위) 작성한다.
