# 백엔드 운영과 PostgreSQL 배포

백엔드는 PostgreSQL에 회원·채팅·폐기 토큰을 저장합니다. Docker Compose는 PostgreSQL 16과 백엔드를 함께 실행하며, DB는 `postgres_data`, JSONL 로그는 `backend_data` 볼륨에 저장합니다. Railway를 사용할 때는 별도 PostgreSQL 서비스에 연결합니다.

## 환경 변수

로컬·Compose는 루트 `.env` 또는 셸 환경변수, Railway는 Variables에 설정합니다. 변경 후 서버를 재시작하거나 재배포합니다.

| 이름 | 기본값 또는 예시 | 용도와 검증 |
| --- | --- | --- |
| `OPENAI_API_KEY` | 기본값 없음 | 서버 전용 AI API 키. 빈 값 금지 |
| `OPENAI_MODEL` | `gpt-6-luna` | 코드 기본 모델 ID. 빈 값 금지. 운영 계정에서 사용 가능한 ID로 지정 |
| `AI_TIMEOUT_SECONDS` | `30` | 재시도·대기를 포함한 전체 AI 처리 제한 시간. 양의 유한 초 값 |
| `AI_MAX_RETRIES` | `4` | 최초 호출을 제외한 최대 재시도 횟수. 0 이상 정수. 0이면 재시도 비활성화 |
| `AI_MAX_CONCURRENT_REQUESTS` | `3` | 한 프로세스에서 동시에 처리할 전체 질문 수. 양의 정수 |
| `JWT_SECRET_KEY` | 기본값 없음 | HS256 서명 키. 최소 32자. `openssl rand -hex 32`로 생성 |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `300` | 액세스 토큰 유효 시간. 1~1440분 |
| `DATABASE_URL` | 기본값 없음 | `postgresql+asyncpg://사용자:비밀번호@호스트:5432/DB명`. URL 비밀번호의 특수문자는 인코딩하며 실제 DB 설정과 일치시킴 |
| `POSTGRES_USER` | `b7` | Compose DB 사용자 |
| `POSTGRES_DB` | `b7` | Compose DB 이름 |
| `POSTGRES_PASSWORD` | 기본값 없음 | Compose DB 비밀번호. URL에는 인코딩한 동일 비밀번호 사용 |
| `SYSTEM_LOG_PATH` | `logs/system.jsonl` | 이벤트 파일 경로. Railway 예시: `/data/logs/system.jsonl` |
| `CORS_ORIGINS` | 코드에는 로컬 2개와 배포 프론트 2개 등록 | 쉼표로 구분한 실제 프론트 Origin. 환경 변수로 지정하면 기본 목록을 대체 |
| `PORT` | Railway 제공 | 플랫폼이 지정한 서버 포트. 시작 명령에서 사용 |

로컬 예시의 빈 비밀값은 발급·생성해 채웁니다. `.env.example`에 없는 선택 설정도 `.env`에 추가할 수 있습니다.

```dotenv
OPENAI_API_KEY=
OPENAI_MODEL=gpt-6-luna
AI_TIMEOUT_SECONDS=30
AI_MAX_RETRIES=4
AI_MAX_CONCURRENT_REQUESTS=3
JWT_SECRET_KEY=
ACCESS_TOKEN_EXPIRE_MINUTES=300
DATABASE_URL=postgresql+asyncpg://b7:CHANGE_ME@postgres:5432/b7
POSTGRES_USER=b7
POSTGRES_DB=b7
POSTGRES_PASSWORD=CHANGE_ME
SYSTEM_LOG_PATH=logs/system.jsonl
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173,https://www.quackquack-e.duckdns.org,https://b7-1-two.vercel.app
```

모델 사용 권한은 실제 AI 호출로 확인합니다. `/health`는 DB 연결만 검사하며 AI 키·모델 권한·답변 생성을 검사하지 않습니다. 필수값 누락·길이 오류 등 설정 검증 실패는 서버 시작을 막을 수 있습니다.

## Docker Compose 배포

`DATABASE_URL`의 DB 호스트는 Compose 서비스 이름 `postgres`, 포트는 `5432`입니다. `POSTGRES_USER`·`POSTGRES_DB`와 URL의 사용자·DB 이름을 일치시키고 `CHANGE_ME`를 실제 비밀번호로 바꿉니다. Nginx·인증서 구성에 필요한 `DOMAIN`·`LETSENCRYPT_EMAIL`도 설정합니다.

```bash
docker compose config --quiet
docker compose up --build -d
docker compose ps
docker compose exec -T backend python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/health').read().decode())"
```

PostgreSQL healthcheck가 통과해야 백엔드가 시작합니다. DB 포트는 호스트에 공개하지 않습니다. 빈 DB에는 앱 시작 시 테이블을 생성하고, 기존 SQLite 데이터는 이관하지 않습니다. 사용자·관리자는 새로 생성합니다. `READ COMMITTED` 격리를 유지합니다.

`docker compose down`은 볼륨을 유지하지만 `down --volumes`는 DB와 로그를 삭제합니다. 컨테이너 재생성으로 데이터가 사라지지 않는지 확인합니다. `POSTGRES_*` 초기값은 빈 데이터 디렉터리에서만 적용되므로 이미 생성한 DB의 비밀번호 변경은 DB 내부에서도 수행해야 합니다. 로그를 저장하는 `backend_data` 볼륨도 유지합니다.

## Railway 배포

### 저장소와 빌드 연결

1. Railway에 GitHub 저장소 `myy-dev/be-B7-1`을 연결하고 최신 `main` 커밋을 선택합니다.
2. Root Directory는 `app/` 대신 저장소 루트로 지정합니다.
3. Railpack이 루트의 `pyproject.toml`·`uv.lock`으로 Python·uv 의존성을 설치합니다. 필요하면 Variables에 `RAILPACK_PYTHON_VERSION=3.12`를 지정합니다.
4. Settings의 시작 명령을 지정합니다.

```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

앱 경로는 `app.main:app`이며 셸이 `$PORT`를 확장합니다. 배포에서는 `--reload`를 사용하지 않습니다. [시작 명령](https://docs.railway.com/deployments/start-command) · [Railpack Python](https://railpack.com/languages/python)

### PostgreSQL과 Variables

1. PostgreSQL 서비스를 추가하고 백엔드에서 접근 가능한 연결 주소를 준비합니다. 로그 보관이 필요하면 백엔드에 `/data` 볼륨을 연결합니다.
2. Variables에 실제 `OPENAI_API_KEY`·`JWT_SECRET_KEY`·`OPENAI_MODEL`을 입력합니다.
3. 제공된 PostgreSQL 주소의 드라이버를 `postgresql+asyncpg`로 지정하고 DB·로그 설정을 등록합니다.

```dotenv
DATABASE_URL=postgresql+asyncpg://사용자:비밀번호@DB호스트:5432/DB명
SYSTEM_LOG_PATH=/data/logs/system.jsonl
AI_TIMEOUT_SECONDS=30
AI_MAX_RETRIES=4
AI_MAX_CONCURRENT_REQUESTS=3
ACCESS_TOKEN_EXPIRE_MINUTES=300
CORS_ORIGINS=https://www.quackquack-e.duckdns.org,https://b7-1-two.vercel.app
```

PostgreSQL은 별도 DB 서비스에 데이터를 저장합니다. 로그용 `/data`의 볼륨 연결·쓰기 권한을 확인하고 AI 요청 제한을 위해 단일 백엔드 프로세스로 운영합니다. 앱 시작 때 없는 테이블과 로그 디렉터리를 생성합니다.

볼륨은 실행 중에만 마운트되므로 빌드 중 DB를 초기화하지 않습니다. DB 데이터는 PostgreSQL 서비스의 영속 저장소에 두며, 백엔드 볼륨 없는 파일 로그는 배포 교체 시 사라질 수 있습니다. [Railway 볼륨](https://docs.railway.com/volumes)

### 공개 주소와 배포 확인

1. Settings의 Healthcheck Path를 `/health`로 지정합니다.
2. Networking → Generate Domain으로 HTTPS 주소를 생성하거나 기존 주소를 사용합니다.
3. 재배포 후 빌드·실행 로그와 공개 `/health`의 200·`{"status":"ok"}`를 확인합니다.
4. 프론트 `VITE_API_BASE_URL`을 백엔드 Origin으로 설정하고, 백엔드 CORS에 프론트 Origin을 허용합니다. [프론트 설정](https://github.com/myy-dev/fe-B7-1#readme) 참고.
5. 아래 운영 검증을 수행하고 재배포 후 같은 회원·채팅 기록을 재조회합니다.

[Railway FastAPI 가이드](https://docs.railway.com/guides/fastapi) · [DB 전환 시 드라이버·초기화 변경](DATABASE.md)

## 초기 관리자 생성

### 기존 정수 회원 ID에서 UUID로 전환

이번 전환은 기존 회원·채팅 데이터를 초기화하는 방식이며 데이터 마이그레이션은 제공하지 않습니다. `create_all`은 기존 BIGINT 컬럼을 UUID로 바꾸지 않으므로 정수 ID 테이블이 있는 DB는 초기화 후 시작해야 합니다. 초기화하면 회원·채팅·질문 기록·폐기 토큰이 삭제되며 관리자를 새로 생성해야 합니다. 기존 JWT와 프론트 로그인 상태도 버리고 다시 로그인합니다.

Compose의 DB 볼륨만 제거하는 절차는 다음과 같습니다. `<Compose프로젝트이름>_postgres_data`는 현재 PostgreSQL 컨테이너가 사용 중인 실제 볼륨 이름으로 바꿉니다. `backend_data`의 시스템 로그와 인증서 볼륨은 유지합니다.

```bash
docker compose stop backend postgres
docker compose rm -f postgres
docker volume rm "<Compose프로젝트이름>_postgres_data"
docker compose up --build -d postgres backend
```

Docker 소켓 접근 권한이 없는 서버에서는 각 Docker 명령 앞에 `sudo`를 붙입니다. 외부 PostgreSQL은 해당 DB의 기존 앱 테이블을 초기화한 뒤 새 코드로 시작합니다. 아래 관리자 생성 명령은 초기화 완료 후 실행합니다.

초기 관리자는 시드 스크립트로 생성합니다. Compose에서는 다음 명령으로 비밀번호 프롬프트를 열어 생성합니다.

```bash
docker compose exec backend python scripts/seed_admin.py --username admin --name 관리자
```

Railway를 사용할 때는 CLI로 배포 프로젝트·환경·백엔드 서비스에 연결합니다.

```bash
railway login
railway link
railway ssh
```

컨테이너의 저장소 루트에서 실행합니다. 서비스와 같은 `DATABASE_URL`을 사용합니다. 로컬 실행도 지정한 주소의 DB에 생성하므로 대상을 확인합니다. 비밀번호는 명령 인자 대신 프롬프트로 입력합니다.

```bash
python scripts/seed_admin.py --username admin --name 관리자
```

비밀번호는 8자 이상이며 기존 관리자가 있으면 추가 생성하지 않습니다. 프롬프트 사용이 불가능하면 Variables에 시드 전용 `SEED_ADMIN_PASSWORD`를 임시 설정하고 실행 후 즉시 제거합니다.

로그인 후 `/api/v1/auth/me`의 `role=admin`·관리자 조회 200을 확인합니다. 다른 회원은 역할 변경 API로 승격합니다. 비밀번호 변경 API는 없으므로 관리 가능한 비밀번호를 정합니다. [Railway SSH](https://docs.railway.com/cli/ssh)

## 서버 로그와 요청 추적

Uvicorn 실행·접근 로그와 앱 이벤트를 확인합니다. 이벤트는 스트림과 `SYSTEM_LOG_PATH`의 JSONL 파일에 기록됩니다. 아래 로컬 경로는 Railway에서 `/data/logs/system.jsonl`로 바꿉니다.

```bash
tail -n 50 logs/system.jsonl
```

| 영역 | 이벤트 |
| --- | --- |
| 요청 | `request_received`, `request_completed`, `request_failed` |
| 공통 오류 | `api_error` |
| AI 호출 | `ai_call_started`, `ai_call_succeeded`, `ai_call_failed` |
| DB 저장 | `db_save_succeeded`, `db_save_failed` |
| 회원 | `user_signed_up`, `user_logged_in`, `user_login_failed` |

AI 이벤트는 호출 전체의 시작·최종 결과이며 개별 재시도는 기록하지 않습니다. `request_failed`·`ai_call_failed`·`db_save_failed` 또는 상태 코드 500 이상은 `ERROR`, 그 외 로그인 실패는 `WARNING`, 나머지는 `INFO`입니다.

기본 필드는 `timestamp`(UTC)·`level`·`event`·`request_id`·`user_id`·`method`·`path`·`status_code`입니다. 경로에는 쿼리 문자열을 포함하지 않으며 인증 전 사용자 ID는 null입니다. 파일에는 `chat_id`·`result`·`error_code`·`duration_ms`·`exception_type`도 기록합니다. 질문·답변 원문, 비밀번호, 토큰, API 키와 스택 트레이스는 기록하지 않습니다.

응답의 `X-Request-ID` 또는 오류 본문 `request_id`로 요청을 추적합니다.

```bash
rg -F '응답에서 확인한-request-id' logs/system.jsonl
```

관리자 `/api/v1/admin/system-logs`는 이벤트·레벨·기간으로 유효한 줄을 필터링해 최신순으로 기본 필드를 반환합니다. 새 사용자 ID는 파일과 관리자 응답에서 UUID 문자열이며, 과거 정수 사용자 ID 로그도 그대로 조회할 수 있습니다. 기존 `http_status`는 `status_code`로 읽으며 두 값이 있으면 새 필드를 우선합니다. 잘못된 JSON·필드·시각은 조회에서 제외하며 원본 파일은 수정하지 않습니다.

파일 쓰기 오류는 stderr에 표시될 수 있고, 시작 시 경로 생성·파일 열기 실패는 앱 시작을 막을 수 있습니다. 권한·디스크를 확인하고 로그 로테이션·보관 기간은 별도 설정합니다.

## 공통 오류 처리

검증·인증·권한·DB·AI 오류는 `error.code`·`error.message`·`error.request_id` JSON을 반환합니다. 입력 원문·내부 검증 상세·비밀값은 제외합니다. 없는 경로·허용하지 않는 메서드도 같은 형식이며 예상하지 못한 서버 오류와 DB 오류는 구분합니다.

요청별 UUID4를 `X-Request-ID`·오류 본문·저장된 질문에 함께 사용합니다. 입력 검증·질문 저장 실패 시 DB 기록은 없을 수 있습니다. JWT 설정 누락·최소 길이 위반은 앱 시작 때 검증합니다.

회원가입·로그인·로그아웃의 일부 실패 응답은 OpenAPI에 등록되어 있지 않습니다. Swagger의 기본 422 설명과 실제 공통 오류 형식이 다를 수 있습니다.

## AI 재시도와 타임아웃

SDK 재시도는 `max_retries=0`이며 `OpenAIClient`가 직접 재시도합니다. 기본 `AI_MAX_RETRIES=4`는 최초 호출 포함 최대 5회입니다. `AI_TIMEOUT_SECONDS=30`은 Conversation 생성과 답변 호출의 모든 시도·대기를 합한 30초이며 앞뒤 DB 시간은 제외합니다. HTTP 요청·DB 작업을 재전송하지 않습니다.

- 답변 재시도: Conversation을 사용하는 운영 호출은 HTTP 429만, Conversation이 없는 호출은 연결 오류·HTTP 408·409·429·5xx를 전체 시간·횟수 제한 안에서 재시도합니다. Conversation 생성은 재시도하지 않습니다.
- 재시도 제외: `x-should-retry: false`, 인증·권한·모델 찾기 오류, 잘못된 형식·미완료·빈 답변.
- `Retry-After`: 양의 유한 초 값(소수 포함)은 지터 없이 사용합니다. `retry-after-ms`·날짜·잘못된 값(0 이하·NaN·무한대 등)은 사용하지 않고 백오프로 대체합니다.
- 백오프: 1·2·4·8초, 상한 8초에 매번 0.75~1.0배 무작위 지터를 적용합니다.
- 대기가 남은 시간 이상이거나 호출·대기 중 전체 시간을 넘으면 추가 호출 없이 `AI_TIMEOUT`입니다. 비동기 취소 후에도 재시도하지 않습니다.

| 최종 상황 | 응답과 저장 |
| --- | --- |
| 제한 시간 초과·최종 SDK 타임아웃 | `504 AI_TIMEOUT`, 질문 기록 `failed` |
| 인증·권한·모델 찾기 실패 | `503 AI_CONFIGURATION_ERROR`, `failed` |
| 연결·기타 API 상태·JSON 오류·미완료·빈 답변 | `502 AI_UNAVAILABLE`, `failed` |
| 예상하지 못한 AI 예외 | `failed/INTERNAL_ERROR` 저장 후 공통 500 |
| DB 조회·저장 예외 | `500 DB_ERROR`, 롤백·실패 로그. 결과 저장 실패 시 기록이 pending으로 남을 수 있음 |

재시도는 같은 질문·Conversation·최초 요청 ID와 기록 한 행을 유지합니다. 클라이언트의 재전송은 새 요청·새 기록입니다. 중단된 `pending` 자동 복구와 요청 멱등성은 없습니다.

사용자당 질문 하나만 처리하며 추가 질문은 `409 CHAT_BUSY`로 거절합니다. 한 프로세스의 전체 동시 질문이 `AI_MAX_CONCURRENT_REQUESTS`에 도달하면 대기시키지 않고 `503 SERVER_BUSY`를 반환합니다. 제한 상태는 프로세스 메모리에 있으므로 여러 인스턴스 사이에서 공유되지 않습니다.

## 운영 검증

격리된 로컬 테스트입니다. 실제 AI를 호출하는 외부 검증은 별도로 수행합니다.

```bash
export TEST_POSTGRESQL_URL='postgresql+asyncpg://테스트사용자:비밀번호@127.0.0.1:5432/postgres'
uv run pytest
```

테스트 계정은 임시 DB 생성·삭제 권한(`CREATEDB`)이 필요합니다. 테스트마다 `test_b7_` 접두사의 새 DB를 생성하고 종료 후 제거합니다. 운영 DB 주소를 사용하지 않습니다. `.env`는 읽지 않으며 AI·JWT에는 테스트 설정을 사용합니다. `TEST_POSTGRESQL_URL`이 없으면 DB 테스트는 명시적으로 실패합니다. 응답 예제는 `tests/data/chat-response-examples.json`에 보관합니다.

테스트 계정·채팅방으로 가입·로그인·질문·기록 조회, 비로그인·타인 기록·관리자 접근 제한, 로그아웃 후 토큰 차단, 삭제 후 원본 보존을 확인합니다. 재시작·재배포 후 같은 기록을 조회하고, AI·DB 실패 시 오류 응답·저장 상태·요청별 로그와 이후 요청 처리를 확인합니다.

## 데이터와 비밀값 관리

AI·JWT 키는 백엔드 `.env` 또는 Railway Variables에 보관합니다. 브라우저에 공개되는 `VITE_` 변수와 README·예시·PR·캡처에 키·비밀번호·토큰을 넣지 않습니다.

`.env`·환경별 비밀 설정·키 파일·DB·로그는 Git에서 제외합니다. 이미 추적된 파일은 `.gitignore`로 제거되지 않으므로 목록을 확인합니다.

```bash
git ls-files .env '.env.*' '*.pem' '*.key' '*.db' '*.sqlite' '*.sqlite3' '*.jsonl'
```

예시 외 비밀 설정·실데이터가 추적되지 않아야 합니다. 노출된 비밀값은 폐기·재발급하고 재발 방지·Git 이력을 처리합니다.

PostgreSQL은 `pg_dump`로 백업하고 별도 DB에서 복원을 검증합니다. Compose의 기본 DB 백업 예시는 다음과 같습니다. 사용자·DB 이름을 변경했으면 명령도 맞춥니다.

```bash
docker compose exec -T postgres pg_dump -U b7 -d b7 -Fc > b7-backup.dump
```

백업 파일은 실제 데이터를 포함하므로 별도 보관하며 Git에 추가하지 않습니다. 논리 삭제 후에도 대화 원문이 남으므로 보관·물리 삭제 정책은 별도로 정합니다.
