# AGENTS.md

## 기술 스택
- Python 3.12
- uv
- FastAPI
- SQLAlchemy 2.x
- SQLite

## 문서
기능을 구현하거나 수정하기 전에 아래 문서를 먼저 읽습니다.
- `docs/PROGRESS.md`: 현재 작업 진행 상태를 확인합니다.
- `docs/prd/`: 구현 대상 기능의 PRD만 읽습니다. 관련 없는 PRD는 읽지 않습니다.
  - 구현은 지정된 PRD를 최우선 기준으로 합니다.
  - 여러 PRD가 필요한 경우에만 추가로 읽습니다.
  - 구현 대상 PRD가 명시되지 않은 경우에는 먼저 사용자에게 확인을 요청합니다.

## 작업 원칙
- 요청받지 않은 리팩토링은 수행하지 않습니다.
- 요청 범위를 벗어난 파일은 수정하지 않습니다.
- 기존 코드 스타일과 프로젝트 구조를 우선합니다.
- 큰 구조 변경이 필요한 경우, 먼저 변경 계획을 제시합니다.

## 기능 구현 규칙
- PRD 내용과 사용자의 채팅 지시가 상충되면, 사용자에게 우선순위를 확인합니다.
- PRD에 정의되지 않은 엣지 케이스나 예외 상황을 발견하면, 이를 사용자에게 알리고 PRD 업데이트를 제안합니다.
- 기능 구현이 완료되면 `docs/PROGRESS.md`를 갱신합니다.

## FastAPI 개발 규칙
- 애플리케이션은 Router → Service → Repository 계층으로 분리합니다.
- 비즈니스 로직은 Router가 아닌 Service에서 구현합니다.
- Router는 요청 검증, Service 호출, 응답 처리를 담당합니다.
- 데이터베이스 접근 로직은 Repository에서 구현합니다.
- Router에서 직접 데이터베이스에 접근하지 않습니다.
- Repository에는 비즈니스 로직을 작성하지 않습니다.
- 요청 및 응답 데이터는 Pydantic 모델로 정의합니다.
- FastAPI의 Dependency Injection을 활용하여 의존성을 주입합니다.
- FastAPI dependency는 `Annotated`를 사용하여 선언합니다.
- `Depends()`를 함수 매개변수의 기본값으로 직접 선언하는 방식은 사용하지 않습니다.
- 반복해서 사용하는 dependency는 `Annotated` 타입 별칭으로 정의합니다.

## Router 작성 규칙
- API는 `/api/v1` prefix를 사용합니다.
- 기능별로 `APIRouter`를 분리합니다.
- Router 내부에 복잡한 조건문이나 비즈니스 로직을 작성하지 않습니다.
- HTTP 상태 코드는 요청 결과에 맞게 명시적으로 사용합니다.
- 예상 가능한 오류는 적절한 HTTP 응답으로 변환합니다.

## 데이터베이스
- SQLite와 SQLAlchemy 2.x를 사용합니다.
- SQLAlchemy는 2.x 스타일 API를 사용합니다.
- ORM 모델은 `Mapped`와 `mapped_column()`을 사용하여 선언합니다.
- 조회에는 `select()` 기반 문법을 사용합니다.
- 레거시 `Query` API와 `session.query()`는 사용하지 않습니다.
- 데이터베이스 접근은 Repository 계층에서 수행합니다.
- 트랜잭션이 필요한 작업은 트랜잭션 범위를 명확하게 정의합니다.
- 불필요한 데이터베이스 쿼리가 발생하지 않도록 합니다.

## 스코프
- 수정 금지: `.env`
- 읽기 금지: `.env`
- 요청받지 않은 dependency를 임의로 추가하지 않습니다.

## 코드 스타일
- `pyproject.toml`에 정의된 Ruff 규칙을 따릅니다.
- import 문은 절대 경로를 사용합니다.
- 공개 클래스와 함수에는 Google 스타일 docstring을 작성합니다.
- docstring 본문 설명은 한국어로 작성하되, Google 스타일 섹션 헤더는 `Args:`, `Returns:`, `Raises:`처럼 영어로 작성합니다.
- Router, Service, Repository, 유틸리티 등 일반 Python 코드에는 타입 힌트를 작성합니다.

## 실행
- Python 패키지 추가는 `uv add`를 사용합니다.
- Python 패키지 제거는 `uv remove`를 사용합니다.
- Python 파일 실행은 `uv run python`을 사용합니다.
- FastAPI 관련 명령은 `uv run`을 통해 실행합니다.