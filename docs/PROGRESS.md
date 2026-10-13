# Progress: PostgreSQL 전환

Last updated: 2026-10-14 01:53

## Goal

- 기존 데이터 이관 없이 SQLite 저장소를 PostgreSQL로 전환한다.

## Current Status

- Status: In progress
- Current focus: 4단계 완료 — Compose PostgreSQL 서비스 및 연결·볼륨·시작 순서 구성
- Branch: refactor/postgresql
- Related issue/PR: 없음

## Decisions

- [2026-10-14] 사용자 지시에 따라 PRD 없이 단계별로 진행하며, 기존 데이터 이관 및 마이그레이션 도구 도입은 제외한다. 기존 Settings를 유지하고 DATABASE_URL을 필수로 받는다. SQLite 외래키 초기화는 기존 테스트에서만 사용하고 운영 코드에서는 제거한다. 채팅방 생성은 사용자 행의 FOR UPDATE 잠금과 생성·재사용을 같은 트랜잭션에서 처리하며, PostgreSQL 기본 READ COMMITTED 격리를 전제로 한다. 현재 Compose 구성에 PostgreSQL 16을 추가하고 DB 전용 볼륨을 사용하며, 백엔드는 DB healthcheck 통과 후 시작한다. DATABASE_URL 및 POSTGRES_PASSWORD는 배포 환경에서 제공한다.

## Completed

- [x] 1단계: asyncpg 추가 및 DATABASE_URL 필수화. 2단계: 운영 PRAGMA 제거, PostgreSQL insert 적용, tests/conftest.py로 공통 테스트 설정 및 SQLite 초기화 함수 이동, 임시 PostgreSQL 16에서 테이블·외래키·토큰 폐기 검증 및 관련 기존 테스트 171개 통과. 3단계: 사용자 행 잠금 추가, PostgreSQL에서 12개 독립 연결의 빈 방 생성·재사용, 사용자별 잠금 분리 및 실패 후 잠금 해제 검증, 관련 테스트 187개 통과. 4단계: Compose PostgreSQL 서비스·전용 볼륨·시작 순서 적용, 별도 테스트 프로젝트에서 이미지 빌드·빈 DB 테이블 생성·health 및 인증·채팅 기본 동작 검증, 컨테이너 재생성 후 데이터 보존 확인

## In Progress

- [ ] PostgreSQL 전환 전체 작업 진행 중 — 5단계 미착수

## Next Steps

1. 나머지 DB 테스트를 PostgreSQL로 전환한다.
2. PostgreSQL 기준 전체 API 및 동시성 검증을 완료하고 SQLite 의존성을 제거한다.
3. PostgreSQL 연결·배포·초기 관리자 생성·DB 조회 등 운영 문서를 갱신한다.

## Changed Files

- `app/core/config.py`, `pyproject.toml`, `uv.lock`: 1단계 연결 설정 및 드라이버 준비. `app/core/database.py`, `app/repositories/token_repository.py`: 2단계 PostgreSQL 대응. `tests/conftest.py`(루트에서 이동), `tests/test_chat_api.py`, `tests/test_chat_integration.py`, `tests/test_chat_conversation_integration.py`, `tests/test_chat_delete_integration.py`: 기존 SQLite 테스트 초기화 분리 및 시작 처리 검증 조정. `app/repositories/chat_repository.py`, `tests/test_chat_repository.py`: 3단계 사용자 행 잠금 및 격리한 PostgreSQL 회귀 테스트 추가. `compose.yaml`: 4단계 PostgreSQL 서비스·연결 설정·전용 볼륨·healthcheck 및 시작 순서 추가. `docs/PROGRESS.md`: 진행 상태 기록

## Commands Run

```text
UV_CACHE_DIR=/private/tmp/b7-postgresql-uv-cache uv add asyncpg
asyncpg 0.32.0 설치 및 uv.lock 갱신 완료
UV_CACHE_DIR=/private/tmp/b7-postgresql-uv-cache uv run --no-sync python - <<'PY' ... PY
_env_file=None으로 설정 누락 오류, 명시적 URL 및 환경변수 반영, asyncpg 엔진 생성 확인 (DB 연결 없음)
/opt/homebrew/opt/postgresql@16/bin/initdb 및 pg_ctl start
/private/tmp 전용 임시 클러스터와 Unix 소켓으로 PostgreSQL 16 실행
UV_CACHE_DIR=/private/tmp/b7-postgresql-uv-cache uv run --no-sync python - <<'PY' ... PY
_env_file=None과 테스트 설정으로 실제 PostgreSQL 테이블 생성, 외래키 거절, 토큰 반복 폐기, 8개 세션 동시 폐기, 만료 토큰 정리 및 세션 복구 검증 통과
UV_CACHE_DIR=/private/tmp/b7-postgresql-uv-cache uv run --no-sync python - <<'PY' ... pytest.main(...) ... PY
env_file 사용을 비활성화한 관련 기존 SQLite 테스트: repository/API 69개, integration/conversation/delete/login/my_info 102개 통과; tests/conftest.py 이동 후 동일한 171개 재검증 통과
/opt/homebrew/opt/postgresql@16/bin/pg_ctl stop -m fast
임시 PostgreSQL 서버 종료 완료
UV_CACHE_DIR=/private/tmp/b7-postgresql-uv-cache uv run --no-sync python - <<'PY' ... pytest.main(...) ... PY
3단계: TEST_POSTGRESQL_URL로 임시 PostgreSQL 연결, 테스트별 별도 스키마 생성·정리; Repository 및 관련 기존 API 테스트 187개 통과, SQLite 행 잠금 검증 1개 제외
동일한 동시 생성 테스트에서 Select.with_for_update를 테스트 중에만 비활성화
12개 채팅방 중복 생성으로 테스트 실패 확인 — 회귀 검증이 기존 문제를 잡음을 확인
/opt/homebrew/opt/postgresql@16/bin/pg_ctl stop -m fast
3단계 검증 후 임시 PostgreSQL 서버 종료 완료
docker compose config --quiet (별도 테스트 환경변수 파일 및 env_file override 사용)
Compose 구성 검증 통과, 원본 .env 접근 없음
docker compose up --build --wait --wait-timeout 90 backend (별도 b7pg-stage4-gkezqr 프로젝트)
이미지 빌드 및 PostgreSQL·백엔드 healthy 확인
docker compose exec -T backend python - initial < smoke.py
빈 PostgreSQL 테이블 4개 생성, READ COMMITTED, /health 200, 회원가입·로그인·채팅 생성 201 및 재사용 200·로그아웃 검증 통과
docker compose up --force-recreate --always-recreate-deps --wait --wait-timeout 90 backend
테스트 PostgreSQL·백엔드 컨테이너 재생성 후 healthy 확인
docker compose exec -T backend python - recreated < smoke.py
회원·채팅방·폐기 토큰 데이터 보존 및 /health·로그인·채팅방 재사용 확인
docker compose down --volumes --rmi local (별도 테스트 프로젝트만)
테스트 컨테이너·전용 볼륨·네트워크·빌드 이미지 정리 완료
git diff --check
통과
```

## Test Status

- Last passing: 별도 Compose 프로젝트의 이미지 빌드·PostgreSQL 및 백엔드 기동·테이블 생성·health 및 인증·채팅 기본 동작·재생성 후 데이터 보존 검증 통과; 3단계 관련 테스트 187개 통과, SQLite 실행 1개 제외
- Failing: 실행한 검증에서 실패 없음
- Not run: 전체 pytest, PostgreSQL 전체 API 테스트 및 실제 운영 배포

## Risks / Open Questions

- 나머지 SQLite 테스트 및 기존 운영 문서는 5단계에서 변경해야 한다. PostgreSQL Repository 테스트는 TEST_POSTGRESQL_URL이 없으면 제외된다. 배포 시 DATABASE_URL과 POSTGRES_PASSWORD를 제공하고 URL의 사용자·DB·비밀번호를 PostgreSQL 설정과 일치시켜야 한다. 기본 사용자·DB는 b7, Compose 내부 DB 호스트는 postgres이며 READ COMMITTED 격리를 유지해야 한다. 원본 .env는 읽거나 수정하지 않았으며 실제 운영 배포는 수행하지 않았다.
