# Progress: 회원 ID UUID 전환

Last updated: 2026-10-14 19:42

## Goal

- 회원 ID와 연결된 DB·인증·API·로그·테스트를 정수에서 UUID로 전환한다.

## Current Status

- Status: Ready for review
- Current focus: UUID 전환 구현 및 전체 검증 완료 — 변경 사항 검토와 커밋 대기
- Branch: refactor/user-uuid
- Related issue/PR: 없음

## Decisions

- [2026-10-14] 사용자 확인에 따라 PRD 없이 진행하며 기존 데이터는 초기화 가능한 것으로 한다. 데이터 마이그레이션과 실제 운영 DB 초기화는 수행하지 않는다.
- [2026-10-14] User.id는 UUID4를 자동 생성하고 Chat.user_id도 UUID 외래키로 변경한다.
- [2026-10-14] JWT sub는 UUID 문자열을 사용하고 인증 시 UUID로 복원한다. 기존 정수 ID JWT는 거절하며 전환 후 재로그인이 필요하다.
- [2026-10-14] 회원 응답·관리자 경로·조회 조건은 UUID를 사용한다. 프론트는 ID를 숫자로 변환하지 않고 UUID 문자열로 전달해야 한다.
- [2026-10-14] 사용자별 질문 제한과 빈 채팅방 생성 잠금은 UUID를 사용자 키로 사용하며 기존 처리 정책을 유지한다.
- [2026-10-14] 새 시스템 로그는 UUID 문자열로 반환하며 과거 정수 ID 로그의 읽기 호환성을 유지한다.
- [2026-10-14] 진행 문서의 제목·섹션·형식은 유지하고 bullet 개수는 내용에 맞게 조정한다. 코드와 문서는 별도 커밋 메시지를 추천하며 요청 전에는 커밋하지 않는다.

## Completed

- [x] 현재 main의 3e1b0b0에서 refactor/user-uuid 브랜치 생성
- [x] 회원 기본키와 채팅방 소유자 외래키 UUID 전환 및 UUID4 자동 생성
- [x] JWT 발급·검증·복원과 인증 dependency의 UUID 타입 적용
- [x] 관리자 API·응답 스키마·서비스·Repository의 회원 ID 타입 전환
- [x] 사용자별 질문 제한기의 UUID 키 적용 및 기존 동시성·소유권 정책 유지
- [x] UUID 시스템 로그 조회와 기존 정수 로그 호환성 검증
- [x] 기존 테스트의 사용자 데이터 전환 및 UUID 생성·JWT·OpenAPI·관리자 보호 회귀 테스트 추가
- [x] 독립 PostgreSQL DB에서 전체 테스트 498개 통과
- [x] 변경 Python 파일 Ruff 검사·포맷 통과
- [x] DB 형식·인증·초기화·재로그인 안내와 진행 문서 갱신

## In Progress

- [ ] 구현 완료 — 변경 사항 검토 및 커밋 대기

## Next Steps

1. 코드·테스트와 문서 변경을 검토하고 별도로 커밋한다.
2. 배포 대상의 기존 정수 ID DB를 초기화하고 새 코드로 테이블을 생성한다.
3. 관리자를 새로 생성하고 재로그인·UUID API·프론트 ID 처리·실제 AI 대화를 확인한다.

## Changed Files

- `app/models/user.py`, `app/models/chat.py`: UUID 기본키·외래키 및 회원 UUID4 자동 생성
- `app/core/security.py`, `app/api/dependencies.py`: UUID JWT 검증·복원과 인증 ID 타입
- `app/core/chat_request_limiter.py`: 사용자별 동시 질문 제한기의 UUID 키
- `app/api/v1/endpoints/admin.py`, `app/schemas/auth.py`, `app/schemas/admin.py`: 회원 UUID 응답·경로·조회 조건 및 과거 로그 호환성
- `app/services/chat_service.py`, `app/services/admin_service.py`: 사용자 UUID 타입 연결
- `app/repositories/chat_repository.py`, `app/repositories/admin_db.py`, `app/repositories/admin_repositories.py`: 조회·저장·잠금의 UUID 타입
- `tests/user_ids.py`: 테스트 사용자용 고정 UUID 제공
- `tests/test_user_uuid.py`: UUID 생성·DB 타입·JWT·OpenAPI 검증
- `tests/test_auth_api.py`, `tests/test_login_api.py`, `tests/test_my_info_api.py`: UUID 회원 인증·조회 테스트
- `tests/test_admin_api.py`: UUID 관리자 조회·권한 보호·입력 검증 및 로그 호환성 테스트
- `tests/test_chat_api.py`, `tests/test_chat_models.py`, `tests/test_chat_repository.py`: UUID 소유권·모델 제약·동시성 검증
- `tests/test_chat_integration.py`, `tests/test_chat_conversation_integration.py`, `tests/test_chat_delete_integration.py`: UUID 통합 테스트 데이터
- `tests/test_chat_request_limiter.py`, `tests/test_openapi.py`, `tests/test_request_processing.py`: UUID 제한기·API 명세·관리자 오류 처리 테스트
- `docs/ARCHITECTURE.md`, `docs/DATABASE.md`, `docs/OPERATIONS.md`: UUID 계약·DB 초기화·재로그인·로그 호환성 안내
- `docs/PROGRESS.md`: 현재 작업과 검증 결과 기록

## Commands Run

```text
git switch -c refactor/user-uuid
현재 main에서 브랜치 생성 완료

임시 PostgreSQL 16 서버 시작
운영 DB와 분리된 임시 DB로 검증

TEST_POSTGRESQL_URL=<임시 PostgreSQL 주소> uv run --no-sync pytest -q --tb=short
전체 498개 통과, 실패·제외·건너뛰기 없음

Ruff check 및 format --check (변경 Python 파일)
통과

임시 PostgreSQL의 test_b7_ DB 개수 확인 및 pg_ctl stop
남은 테스트 DB 0개, 이번 작업의 임시 서버 종료 완료

git diff --check
통과
```

## Test Status

- Last passing: 전체 테스트 498개 통과, 실패·제외·건너뛰기 없음
- Last passing: 회원 UUID4 생성·저장·재조회, DB UUID 컬럼·외래키, JWT UUID 복원 및 기존 정수 sub 거절 검증
- Last passing: 관리자 UUID 입력·자기 강등 차단, UUID 로그 및 과거 정수 로그 조회, 소유권·동시성·롤백 검증
- Last passing: 변경 Python 파일 Ruff 검사·포맷 및 git diff --check 통과
- Failing: 없음
- Not run: 실제 운영 DB 초기화·배포, 별도 프론트 저장소의 ID 처리 검증 및 외부 OpenAI 실제 호출

## Risks / Open Questions

- create_all은 기존 BIGINT 컬럼을 UUID로 바꾸지 않는다. 배포 전에 승인된 초기화 절차로 기존 정수 ID DB를 새로 생성해야 한다.
- DB 초기화 시 기존 회원·채팅·질문·폐기 토큰이 삭제되며 관리자를 다시 생성해야 한다.
- 기존 숫자 회원 ID JWT는 사용할 수 없다. 프론트의 기존 로그인 상태를 지우고 다시 로그인해야 한다.
- 프론트는 회원 ID를 UUID 문자열로 취급해야 하며 실제 프론트 저장소는 이번 작업에서 수정하거나 검증하지 않았다.
- 과거 정수 ID 시스템 로그는 보존되지만 새 UUID 회원과 매핑하지 않는다.
- .env와 실제 운영 DB는 읽거나 변경하지 않았다. 실제 AI 호출·운영 부하·비용은 이번 검증 범위에 포함하지 않는다.
