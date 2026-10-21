import asyncio
from collections.abc import Iterator
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.clients.ai import AIResponse
from app.core.chat_request_limiter import ChatRequestLimiter
from app.core.database import Base
from app.core.errors import APIError
from app.models.chat import Chat, ChatLog
from app.models.user import User
from app.repositories.chat_repository import ChatRepository
from app.services.chat_service import ChatService
from tests.user_ids import user_uuid


@pytest.fixture
def service_sessions(
    postgresql_engine: AsyncEngine,
) -> Iterator[async_sessionmaker[AsyncSession]]:
    """서비스 검증용 독립 DB와 사용자 한 명을 준비한다."""
    sessions = async_sessionmaker(postgresql_engine, expire_on_commit=False)

    async def prepare() -> None:
        async with postgresql_engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with sessions() as session:
            session.add(
                User(
                    id=user_uuid(1),
                    username="service-owner",
                    password_hash="test-only",
                    name="테스트",
                )
            )
            await session.commit()

    asyncio.run(prepare())
    yield sessions


def _client(*, requires_history: bool = False) -> AsyncMock:
    client = AsyncMock()
    client.requires_history = requires_history
    client.create_state.return_value = "initial-state"
    client.generate_answer.return_value = AIResponse(
        "답변", "next-state", "response-id"
    )
    return client


def test_create_stores_settings_and_reuses_empty_room(
    service_sessions: async_sessionmaker[AsyncSession],
) -> None:
    """방 생성·재사용은 설정만 저장하고 외부 상태 생성을 지연한다."""
    client = _client()

    async def run() -> None:
        async with service_sessions() as session:
            service = ChatService(
                ChatRepository(session), ChatRequestLimiter(1), {"test": client}
            )
            room, created = await service.create_chat(
                user_uuid(1), provider="test", model="room-model"
            )
            assert created
            reused, created = await service.create_chat(
                user_uuid(1), provider="test", model="room-model"
            )
            assert not created and reused.chat_id == room.chat_id
            stored = await session.get(Chat, room.chat_id)
            assert stored is not None
            assert (stored.provider, stored.model, stored.state) == (
                "test",
                "room-model",
                None,
            )
        client.create_state.assert_not_awaited()

    asyncio.run(run())


@pytest.mark.parametrize("requires_history", [False, True])
@pytest.mark.parametrize("initial_state", [None, "existing-state"])
def test_question_committed_before_external_calls_and_result_saved(
    service_sessions: async_sessionmaker[AsyncSession],
    requires_history: bool,
    initial_state: str | None,
) -> None:
    """외부 대기 전 질문·초기 상태 커밋과 이력 선택·결과 저장을 검증한다."""
    client = _client(requires_history=requires_history)

    async def run() -> None:
        async with service_sessions() as session:
            repository = ChatRepository(session)
            room, _ = await repository.create(
                user_uuid(1), provider="test", model="room-model", state=initial_state
            )
            await repository.save_message(
                ChatLog(
                    request_id=uuid4(),
                    chat_id=room.chat_id,
                    question="이전 질문",
                    model="room-model",
                    answer="이전 답변",
                    status="completed",
                    finished_at=datetime.now(UTC),
                )
            )
            request_id = uuid4()

            async def check_pending() -> str:
                assert not session.in_transaction()
                async with service_sessions() as observer:
                    pending = await observer.get(ChatLog, request_id)
                    assert pending is not None
                    assert (pending.question, pending.status) == ("새 질문", "pending")
                return "initial-state"

            async def answer(**kwargs: object) -> AIResponse:
                await check_pending()
                expected_state = initial_state or "initial-state"
                assert kwargs == dict(
                    model="room-model",
                    state=expected_state,
                    history=[("이전 질문", "이전 답변")] if requires_history else None,
                    question="새 질문",
                )
                async with service_sessions() as observer:
                    stored = await observer.get(Chat, room.chat_id)
                    assert stored is not None and stored.state == expected_state
                return AIResponse("답변", "next-state", "response-id")

            client.create_state.side_effect = check_pending
            client.generate_answer.side_effect = answer
            service = ChatService(repository, ChatRequestLimiter(1), {"test": client})
            result = await service.send_message(
                room.chat_id, user_uuid(1), request_id, "새 질문"
            )
            assert result.answer == "답변" and result.status == "completed"
            assert client.create_state.await_count == (
                1 if initial_state is None else 0
            )

        async with service_sessions() as session:
            stored = await session.get(ChatLog, request_id)
            assert stored is not None and stored.response_id == "response-id"
            room = await session.get(Chat, room.chat_id)
            assert room is not None and room.state == "next-state"

    asyncio.run(run())


@pytest.mark.parametrize("phase", ["state", "answer"])
@pytest.mark.parametrize("unexpected", [False, True])
def test_external_failure_preserves_question_and_prepared_state(
    service_sessions: async_sessionmaker[AsyncSession], phase: str, unexpected: bool
) -> None:
    """외부 처리 실패 시 질문·실패 코드와 이미 생성한 상태를 보존한다."""
    client = _client()
    failure = RuntimeError("hidden") if unexpected else APIError("AI_TIMEOUT")
    (
        client.create_state if phase == "state" else client.generate_answer
    ).side_effect = failure

    async def run() -> None:
        async with service_sessions() as session:
            repository = ChatRepository(session)
            room, _ = await repository.create(
                user_uuid(1), provider="test", model="room-model"
            )
            request_id = uuid4()
            limiter = ChatRequestLimiter(1)
            service = ChatService(repository, limiter, {"test": client})
            with pytest.raises(type(failure)):
                await service.send_message(
                    room.chat_id, user_uuid(1), request_id, "질문"
                )
            async with limiter.acquire(user_uuid(1)):
                pass

        async with service_sessions() as session:
            stored = await session.get(ChatLog, request_id)
            assert stored is not None and stored.question == "질문"
            assert stored.status == "failed" and stored.answer is None
            assert stored.error_code == (
                "INTERNAL_ERROR" if unexpected else "AI_TIMEOUT"
            )
            assert stored.finished_at is not None
            room = await session.get(Chat, room.chat_id)
            assert room is not None
            assert room.state == (None if phase == "state" else "initial-state")

    asyncio.run(run())


def test_history_failure_continues_with_empty_history(
    service_sessions: async_sessionmaker[AsyncSession],
) -> None:
    """실제 조회 오류의 트랜잭션을 복구하고 빈 이력으로 답변을 생성한다."""
    client = _client(requires_history=True)

    async def run() -> None:
        async with service_sessions() as session:
            repository = ChatRepository(session)
            room, _ = await repository.create(
                user_uuid(1), provider="test", model="room-model", state="existing"
            )

            async def broken_history(chat_id: object) -> None:
                await session.execute(text("SELECT * FROM missing_history_table"))

            service = ChatService(repository, ChatRequestLimiter(1), {"test": client})
            with patch.object(repository, "list_recent_completed", broken_history):
                result = await service.send_message(
                    room.chat_id, user_uuid(1), uuid4(), "질문"
                )
            assert result.status == "completed"
            client.generate_answer.assert_awaited_once_with(
                model="room-model", state="existing", history=[], question="질문"
            )

    asyncio.run(run())


@pytest.mark.parametrize("case", ["missing", "other_owner", "deleted", "provider"])
def test_unavailable_chat_or_provider_does_not_call_ai(
    service_sessions: async_sessionmaker[AsyncSession], case: str
) -> None:
    """권한 없는 방과 미등록 제공자는 외부 호출 전에 거절한다."""
    client = _client()

    async def run() -> None:
        async with service_sessions() as session:
            repository = ChatRepository(session)
            room, _ = await repository.create(
                user_uuid(1), provider="test", model="room-model"
            )
            if case == "deleted":
                await repository.soft_delete(
                    room.chat_id, user_uuid(1), datetime.now(UTC)
                )
            service = ChatService(
                repository,
                ChatRequestLimiter(1),
                {} if case == "provider" else {"test": client},
            )
            with pytest.raises(APIError) as caught:
                await service.send_message(
                    uuid4() if case == "missing" else room.chat_id,
                    user_uuid(2) if case == "other_owner" else user_uuid(1),
                    uuid4(),
                    "질문",
                )
            assert caught.value.code == (
                "AI_CONFIGURATION_ERROR" if case == "provider" else "CHAT_NOT_FOUND"
            )
            client.create_state.assert_not_awaited()
            client.generate_answer.assert_not_awaited()

    asyncio.run(run())
