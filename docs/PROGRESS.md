# Progress: PostgreSQL 전환

Last updated: 2026-10-14 01:24

## Goal

- 기존 데이터 이관 없이 SQLite 저장소를 PostgreSQL로 전환한다.

## Current Status

- Status: In progress
- Current focus: 1단계 완료 — asyncpg 추가 및 DATABASE_URL 필수 설정
- Branch: refactor/postgresql
- Related issue/PR: 없음

## Decisions

- [2026-10-14] 사용자 지시에 따라 PRD 없이 단계별로 진행하며, 기존 데이터 이관 및 마이그레이션 도구 도입은 제외한다. 기존 Settings를 유지하고 DATABASE_URL을 필수로 받는다.

## Completed

- [x] 1단계: asyncpg 의존성 및 잠금 파일 갱신, SQLite 기본 연결 주소 제거, DATABASE_URL 필수 설정과 PostgreSQL 비동기 엔진 생성 검증

## In Progress

- [ ] PostgreSQL 전환 전체 작업 진행 중 — 2단계 이후 미착수

## Next Steps

1. SQLite 전용 PRAGMA 초기화와 토큰 저장 insert를 PostgreSQL 기준으로 변경한다.
2. 빈 채팅방 생성에 사용자별 DB 잠금을 적용하고 PostgreSQL 연결 및 배포 구성을 정한다.
3. PostgreSQL DB 테스트로 기능과 동시성을 검증하고 운영 문서를 갱신한다.

## Changed Files

- `app/core/config.py`, `pyproject.toml`, `uv.lock`, `docs/PROGRESS.md`: 연결 주소 필수화, asyncpg 추가 및 1단계 진행 상태 기록

## Commands Run

```text
UV_CACHE_DIR=/private/tmp/b7-postgresql-uv-cache uv add asyncpg
asyncpg 0.32.0 설치 및 uv.lock 갱신 완료
UV_CACHE_DIR=/private/tmp/b7-postgresql-uv-cache uv run --no-sync python - <<'PY' ... PY
_env_file=None으로 설정 누락 오류, 명시적 URL 및 환경변수 반영, asyncpg 엔진 생성 확인 (DB 연결 없음)
git diff --check
통과
```

## Test Status

- Last passing: DATABASE_URL 필수 여부, 설정값 반영, PostgreSQL asyncpg 엔진 생성에 대한 독립 검증
- Failing: 실행한 검증에서 실패 없음
- Not run: 전체 pytest 및 실제 PostgreSQL 연결·기능 테스트

## Risks / Open Questions

- SQLite 전용 PRAGMA와 토큰 저장 SQL, Compose의 SQLite 주소 및 기존 SQLite 테스트는 후속 단계에서 변경해야 한다. DATABASE_URL 미설정 시 Settings 생성이 실패한다. PostgreSQL 운영 위치는 미정이다.
