# Progress: PostgreSQL 전환

Last updated: 2026-10-14 02:35

## Goal

- 기존 데이터 이관 없이 SQLite 저장소를 PostgreSQL로 전환한다.

## Current Status

- Status: Ready for review
- Current focus: 5단계 완료 및 코드·문서 분리 커밋 완료 — 진행 문서 가독성 정리
- Branch: refactor/postgresql
- Related issue/PR: 없음

## Decisions

- [2026-10-14] PRD 없이 단계별로 진행하며, 기존 데이터 이관 및 마이그레이션 도구 도입은 제외한다.
- [2026-10-14] 기존 Settings를 유지하고 DATABASE_URL을 필수로 받는다. SQLite 전용 초기화·시각 분기·aiosqlite는 제거한다.
- [2026-10-14] 채팅방 생성은 사용자 행의 FOR UPDATE 잠금과 생성·재사용을 같은 트랜잭션에서 처리한다. PostgreSQL 기본 READ COMMITTED 격리를 유지한다.
- [2026-10-14] Compose에 PostgreSQL 16과 DB 전용 볼륨을 추가하고, 백엔드는 DB healthcheck 통과 후 시작한다. DATABASE_URL 및 POSTGRES_PASSWORD는 배포 환경에서 제공한다.
- [2026-10-14] 기존 큰 회원 ID를 보존하도록 회원·채팅방 소유자 ID는 BIGINT로 정의한다. UUID 전환은 추후 별도 리팩토링에서 검토한다.
- [2026-10-14] DB 테스트는 독립 임시 PostgreSQL DB를 생성·정리하고 .env를 읽지 않는다. 없는 PRD에 의존하던 응답 예제는 테스트 데이터로 분리한다.
- [2026-10-14] 코드·테스트·설정 변경과 문서 변경은 별도 커밋으로 나눈다. 진행 문서의 제목·문단·형식은 유지하되 bullet 개수는 내용에 맞게 조정한다.

## Completed

- [x] 1단계: asyncpg 추가 및 DATABASE_URL 필수화
- [x] 2단계: 운영 PRAGMA 제거, PostgreSQL insert 적용, SQLite 테스트 초기화 분리. 임시 PostgreSQL의 테이블·외래키·토큰 폐기 검증 및 관련 테스트 171개 통과
- [x] 3단계: 사용자 행 잠금 추가. PostgreSQL에서 12개 연결의 동시 생성·재사용, 사용자별 잠금 분리 및 실패 후 잠금 해제 검증. 관련 테스트 187개 통과
- [x] 4단계: Compose PostgreSQL 서비스·전용 볼륨·시작 순서 구성. 이미지 빌드·기동·기본 API 및 컨테이너 재생성 후 데이터 보존 확인
- [x] 5단계: 모든 DB 테스트 PostgreSQL 전환, BIGINT·외래키·UTC 시각 대응, SQLite 의존성 제거, 응답 예제 분리 및 설정·운영 문서 갱신
- [x] 최종 검증: 전체 테스트 485개, Ruff·잠금 파일 검사, 최종 이미지 기동·관리자 시드·읽기 전용 SQL 검증 통과
- [x] 5단계 분리 커밋: 코드·테스트·설정 `7252fea`, 문서 `e3f1007`

## In Progress

- [ ] 구현 작업 없음 — 실제 배포 환경 설정 및 운영 검증 대기

## Next Steps

1. 진행 문서 정리 변경을 검토하고 커밋한다.
2. 실제 배포 환경의 PostgreSQL 비밀번호와 DATABASE_URL을 설정한다.
3. 운영 배포 후 health·초기 관리자·인증·질문·데이터 보존을 확인한다.

## Changed Files

- `app/core/config.py`: DATABASE_URL 필수 설정
- `app/core/database.py`, `app/repositories/token_repository.py`: SQLite 초기화 제거 및 PostgreSQL 토큰 저장
- `app/repositories/chat_repository.py`: 사용자 행 잠금으로 빈 채팅방 동시 생성 방지
- `app/models/user.py`, `app/models/chat.py`, `app/core/datetimes.py`: 큰 회원 ID 보존 및 UTC 저장 분기 정리
- `compose.yaml`: PostgreSQL 서비스·전용 볼륨·healthcheck 및 시작 순서 구성
- `pyproject.toml`, `uv.lock`: asyncpg 추가 및 aiosqlite 제거
- `tests/conftest.py`: 운영 설정을 읽지 않는 독립 PostgreSQL 테스트 DB 제공
- `tests/test_auth_api.py`, `tests/test_login_api.py`, `tests/test_admin_api.py`: 인증·관리자 DB 테스트 전환
- `tests/test_chat_api.py`, `tests/test_chat_models.py`, `tests/test_chat_repository.py`: 채팅 API·모델 제약·동시성 테스트 전환
- `tests/test_chat_integration.py`, `tests/test_chat_conversation_integration.py`, `tests/test_chat_delete_integration.py`: AI·Conversation·삭제 통합 테스트 전환
- `tests/test_request_processing.py`: PostgreSQL 기반 health 및 관리자 오류 처리 검증
- `tests/test_chat_schemas.py`, `tests/data/chat-response-examples.json`: PRD 없는 응답 예제 검증
- `.env.example`: PostgreSQL 연결 및 초기화 설정 예제
- `README.md`, `docs/ARCHITECTURE.md`: 기술 스택과 동시 생성 처리 설명 갱신
- `docs/DATABASE.md`, `docs/GETTING_STARTED.md`, `docs/OPERATIONS.md`: 연결·개발·배포·조회·백업 안내 갱신
- `scripts/seed_admin.py`: PostgreSQL 연결을 사용하는 관리자 시드 설명 갱신
- `docs/PROGRESS.md`: 단계별 진행 상태와 검증 결과 기록

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
UV_CACHE_DIR=/private/tmp/b7-postgresql-uv-cache uv remove --offline aiosqlite
aiosqlite 제거 및 uv.lock 갱신 완료
TEST_POSTGRESQL_URL=<임시 PostgreSQL Unix 소켓 주소> uv run --no-sync pytest -q --tb=short
5단계 전체 485개 통과, 실패·제외·건너뛰기 없음; 각 테스트의 독립 임시 DB 생성·정리 완료
Ruff check 및 format --check (이번 변경 Python 파일 16개)
모두 통과
UV_CACHE_DIR=/private/tmp/b7-postgresql-uv-cache uv lock --check --offline
잠금 파일 검증 통과
docker compose up --build --wait --wait-timeout 90 backend (별도 테스트 프로젝트 및 임시 설정)
최종 코드·의존성 이미지 빌드, PostgreSQL·백엔드 healthy 및 health·인증·채팅·로그아웃 검증 통과
docker compose exec -T backend python scripts/seed_admin.py --username stage5_admin --name 관리자 (테스트 전용 비밀번호 환경변수 제공)
관리자 생성 및 재실행 시 중복 생성 없이 종료 확인
docs/DATABASE.md의 읽기 전용 PostgreSQL 조회 명령 4개 실행
모두 통과
임시 PostgreSQL의 test_b7_ DB 개수 확인 및 테스트 Compose down --volumes --rmi local, pg_ctl stop
남은 테스트 DB 0개, 테스트 컨테이너·전용 볼륨·네트워크·이미지 정리 및 임시 서버 종료 완료
git diff --check
통과
```

## Test Status

- Last passing: 전체 테스트 485개 통과, 실패·제외·건너뛰기 없음
- Last passing: 변경 Python 파일 Ruff 검사·포맷 및 uv.lock 검증 통과
- Last passing: 최종 이미지 기동·health·인증·채팅·로그아웃·관리자 시드·읽기 전용 SQL 검증 통과
- Failing: 실행한 검증에서 실패 없음
- Not run: 실제 운영 배포 및 외부 OpenAI 실제 호출 검증; 테스트의 AI 응답은 모의 HTTP·클라이언트 사용

## Risks / Open Questions

- 배포 시 DATABASE_URL과 POSTGRES_PASSWORD를 제공하고 URL의 사용자·DB·비밀번호를 PostgreSQL 설정과 일치시켜야 한다.
- 기본 사용자·DB는 b7, Compose 내부 DB 호스트는 postgres이며 READ COMMITTED 격리를 유지해야 한다.
- 테스트에는 임시 DB 생성·삭제 권한이 있는 TEST_POSTGRESQL_URL이 필요하다. 미설정 시 DB 테스트는 명시적으로 실패한다.
- 원본 .env는 읽거나 수정하지 않았으며 실제 운영 배포는 수행하지 않았다.
- 기존 SQLite 데이터 이관은 제외했다. 실제 OpenAI 호출·운영 부하·비용은 이번 검증 범위에 포함하지 않는다.
