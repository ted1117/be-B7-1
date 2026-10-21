# Progress: AI 채팅 책임 분리

Last updated: 2026-10-22

## Goal

- 서비스가 제공자별 상태를 해석하지 않도록 AI 클라이언트와 저장소의 책임을 분리한다.

## Current Status

- Status: Ready for review
- Current focus: 리팩토링 코드 커밋 완료, 관리자 재생성과 실제 AI 호출 및 구조·DB 문서 정리 대기
- Branch: refactor/ai-chat
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

- [x] AI 채팅 모델·클라이언트 계약·저장소·서비스·API 연결 및 테스트 리팩토링 커밋(8bc5cc5)
- [x] 독립 PostgreSQL에서 전체 테스트 562개, 수정 Python 파일 Ruff 검사·포맷 확인 통과
- [x] 사용자 승인으로 로컬 개발 DB를 새 스키마로 초기화하고 빈 테이블·칼럼 확인
- [x] 현재 main의 3e1b0b0에서 refactor/user-uuid 브랜치 생성
- [x] 회원 기본키와 채팅방 소유자 외래키 UUID 전환 및 UUID4 자동 생성
- [x] JWT 발급·검증·복원과 인증 dependency의 UUID 타입 적용
- [x] 관리자 API·응답 스키마·서비스·Repository의 회원 ID 타입 전환
- [x] 관리자 UserRepository에 get_user 추상 메서드 선언 추가 및 UUID 반환 계약 확인
- [x] UUID 코드·테스트(f545ef9)와 문서(601a70a) 분리 커밋
- [x] 사용자별 질문 제한기의 UUID 키 적용 및 기존 동시성·소유권 정책 유지
- [x] UUID 시스템 로그 조회와 기존 정수 로그 호환성 검증
- [x] 기존 테스트의 사용자 데이터 전환 및 UUID 생성·JWT·OpenAPI·관리자 보호 회귀 테스트 추가
- [x] 독립 PostgreSQL DB에서 전체 테스트 498개 통과
- [x] 변경 Python 파일 Ruff 검사·포맷 통과
- [x] DB 형식·인증·초기화·재로그인 안내와 진행 문서 갱신

## In Progress

- [2026-10-22] 사용자 승인으로 로컬 개발 컨테이너 b7-postgres-dev의 b7 DB 앱 테이블 4개를 한 트랜잭션에서 초기화·재생성했다. 전체 행 0개와 chats.provider·model(NOT NULL 문자열), chats.state·chat_logs.response_id(nullable 문자열)를 확인했다. 기존 provider_state JSONB는 제거됐으며 관리자 재생성이 필요하다. 다른 DB와 .env는 변경하지 않았다.
- [2026-10-22] 기존 테스트의 클라이언트 생성자·키워드 인자·AIResponse 반환·클라이언트 목록 주입·state 칼럼 참조를 새 계약에 맞췄다. 모델 필수 칼럼을 테스트 데이터에 반영하고, 이력 조회 실패 시 빈 이력으로 계속 호출하는 API 검증 및 상태 생성·답변 생성의 독립 타임아웃 검증을 보완했다. 독립 PostgreSQL에서 전체 562개 테스트 통과(43.12초), 실패·제외·건너뛰기 없음. 수정 테스트의 Ruff 검사·포맷 및 git diff --check 통과. 이번 단계에서 애플리케이션 코드는 추가 변경하지 않았으며 기존 DB 스키마 반영은 남아 있다.
- [2026-10-22] 앱 시작 시 ai_clients 목록을 생성하고 의존성 주입으로 ChatService에 연결했다. 채팅방 생성 라우터는 서버의 OpenAI 모델 설정을 전달하고 메시지 전송의 별도 클라이언트 인자는 제거했다. 실제 API·독립 PostgreSQL·모의 SDK로 생성·재사용·성공·실패·삭제·자원 정리를 검증했으며 관련 대상 테스트 총 86개와 Ruff 검사 통과. 이전 계약을 사용하는 기존 테스트 수정과 기존 DB 스키마 반영은 남아 있다.
- [2026-10-22] ChatService.send_message의 이력 조회·실패 복구를 _load_history로, 상태 생성·저장을 _prepare_state로 추출했다. 호출·저장 순서와 예외 처리 범위를 유지했으며 기존 서비스·요청 제한기 테스트 22개 및 Ruff 검사·포맷 확인 통과.
- [2026-10-22] ChatService의 OpenAI 직접 참조·isinstance 분기를 제거하고 제공자별 클라이언트 목록을 주입받도록 했다. 채팅방에 제공자·모델을 저장하며 외부 상태는 첫 메시지에서 준비한다. 질문 선커밋, 이력 조회 실패 시 빈 이력 전달, 초기 상태 선저장, 답변·응답 ID·최신 상태의 원자적 저장을 연결했다. 서비스·요청 제한기·Repository·OpenAI 계약 대상 테스트 80개 및 Ruff 검사 통과. 앱 초기화·의존성 주입·라우터와 나머지 기존 테스트의 계약 연결은 후속 작업이다.
- [2026-10-22] ChatRepository의 생성 인자에 provider·model·state를 추가하고 같은 제공자·모델의 빈 방을 재사용하도록 했다. Conversation ID 전용 메서드를 get_state·save_state로 바꾸고 대화 결과와 상태의 원자적 저장을 추가했다. 독립 PostgreSQL에서 대상 테스트 25개 및 Ruff 검사 통과. 서비스의 이전 Repository 호출은 후속 수정 대상이다.
- [2026-10-22] OpenAIClient를 create_state·requires_history·명시적 model/state/history/question 인자와 AIResponse 반환 계약에 맞췄다. 모의 HTTP 테스트 33개 통과. 서비스·앱 초기화 및 기존 테스트의 이전 계약 참조는 후속 작업으로 남아 있다.
- [2026-10-21] ChatLog 모델에 nullable 문자열 response_id를 추가했다. 기존 DB 스키마 반영과 응답 ID 저장 로직 연결은 아직 수행하지 않았다.
- [2026-10-21] Chat 모델의 conversation_id를 제거하고 문자열 provider·model(NOT NULL), state(nullable)를 추가했다. 모델 변경만 진행했으며 기존 참조 수정과 DB 스키마 반영은 아직 수행하지 않았다.
- [ ] 관리자 재생성·실제 AI 대화 확인 및 구조·DB 문서 정리

## Next Steps

1. 로컬 개발 DB에 관리자를 재생성하고 로그인한다.
2. FastAPI와 실제 OpenAI를 연결해 채팅방 생성·연속 질문·문맥 유지를 확인한다.
3. 구조·DB 문서를 최종 코드에 맞추고 배포 대상 DB의 스키마 반영을 준비한다.

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

- Last passing: [2026-10-22] 리팩토링 계약에 맞춘 전체 테스트 562개 통과(43.12초), 실패·제외·건너뛰기 없음. 수정 테스트의 Ruff 검사·포맷과 git diff --check 통과.
- Last passing: 전체 테스트 498개 통과, 실패·제외·건너뛰기 없음
- Last passing: 회원 UUID4 생성·저장·재조회, DB UUID 컬럼·외래키, JWT UUID 복원 및 기존 정수 sub 거절 검증
- Last passing: 관리자 UUID 입력·자기 강등 차단, UUID 로그 및 과거 정수 로그 조회, 소유권·동시성·롤백 검증
- Last passing: 변경 Python 파일 Ruff 검사·포맷 및 git diff --check 통과
- Last passing: get_user 추상 메서드·UUID 타입 선언 확인 및 Ruff 검사·포맷 통과
- Failing: 없음
- Not run: 실제 운영 DB 초기화·배포, 별도 프론트 저장소의 ID 처리 검증 및 외부 OpenAI 실제 호출

## Risks / Open Questions

- create_all은 기존 BIGINT 컬럼을 UUID로 바꾸지 않는다. 배포 전에 승인된 초기화 절차로 기존 정수 ID DB를 새로 생성해야 한다.
- DB 초기화 시 기존 회원·채팅·질문·폐기 토큰이 삭제되며 관리자를 다시 생성해야 한다.
- 기존 숫자 회원 ID JWT는 사용할 수 없다. 프론트의 기존 로그인 상태를 지우고 다시 로그인해야 한다.
- 프론트는 회원 ID를 UUID 문자열로 취급해야 하며 실제 프론트 저장소는 이번 작업에서 수정하거나 검증하지 않았다.
- 과거 정수 ID 시스템 로그는 보존되지만 새 UUID 회원과 매핑하지 않는다.
- .env와 실제 운영 DB는 읽거나 변경하지 않았다. 실제 AI 호출·운영 부하·비용은 이번 검증 범위에 포함하지 않는다.
