"""독립 PostgreSQL에서 채팅방 저장·동시성·롤백을 검증한다."""

import asyncio
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.database import Base
from app.core.errors import DatabaseSaveError
from app.models.chat import Chat, ChatLog
from app.models.user import User
from app.repositories.chat_repository import ChatRepository
from tests.user_ids import user_uuid

CHAT_SETTINGS = {"provider": "openai", "model": "test-model"}


@pytest.mark.parametrize("state", [None, "initial-state"])
def test_create_stores_settings_and_reuse_preserves_state(
    repository_sessions: async_sessionmaker[AsyncSession], state: str | None
) -> None:
    """제공자·모델·초기 상태를 저장하고 재사용할 때 기존 상태를 보존한다."""

    async def run() -> None:
        async with repository_sessions() as session:
            repository = ChatRepository(session)
            chat, created = await repository.create(
                user_uuid(1), **CHAT_SETTINGS, state=state
            )
            assert created
            chat_id = chat.chat_id
            reused, created = await repository.create(
                user_uuid(1), **CHAT_SETTINGS, state="unused-state"
            )
            assert not created and reused.chat_id == chat_id

        async with repository_sessions() as session:
            stored = await session.get(Chat, chat_id)
            assert stored is not None
            assert stored.provider == "openai"
            assert stored.model == "test-model"
            assert stored.state == state

    asyncio.run(run())


@pytest.mark.parametrize(
    ("provider", "model"), [("other-provider", "test-model"), ("openai", "other-model")]
)
def test_create_does_not_reuse_different_settings(
    repository_sessions: async_sessionmaker[AsyncSession], provider: str, model: str
) -> None:
    """제공자 또는 모델이 다른 빈 채팅방을 덮어쓰거나 재사용하지 않는다."""

    async def run() -> None:
        async with repository_sessions() as session:
            repository = ChatRepository(session)
            first, _ = await repository.create(user_uuid(1), **CHAT_SETTINGS)
            other, created = await repository.create(
                user_uuid(1), provider=provider, model=model
            )
            assert created and other.chat_id != first.chat_id
            reused, created = await repository.create(user_uuid(1), **CHAT_SETTINGS)
            assert not created and reused.chat_id == first.chat_id

    asyncio.run(run())


def test_state_updates_and_commit_failure_roll_back(
    repository_sessions: async_sessionmaker[AsyncSession],
) -> None:
    """일반 문자열 상태 저장·초기화와 실패 시 기존 상태 보존을 검증한다."""

    async def run() -> None:
        async with repository_sessions() as session:
            repository = ChatRepository(session)
            chat, _ = await repository.create(
                user_uuid(1), **CHAT_SETTINGS, state="initial"
            )
            chat_id = chat.chat_id
            await repository.save_state(chat_id, "updated")
            assert await repository.get_state(chat_id) == "updated"
            failure = OperationalError("test-only", {}, RuntimeError())
            with patch.object(session, "commit", AsyncMock(side_effect=failure)):
                with pytest.raises(DatabaseSaveError) as caught:
                    await repository.save_state(chat_id, "rolled-back")
                assert caught.value.original is failure
            assert not session.in_transaction()
            assert await repository.get_state(chat_id) == "updated"
            await repository.save_state(chat_id, None)
            assert await repository.get_state(chat_id) is None

    asyncio.run(run())


@pytest.mark.parametrize("state", [None, "next-state"])
@pytest.mark.parametrize("fail_commit", [False, True])
def test_message_and_state_commit_together(
    repository_sessions: async_sessionmaker[AsyncSession],
    state: str | None,
    fail_commit: bool,
) -> None:
    """답변·응답 ID·상태를 함께 커밋하고 실패 시 질문의 pending을 보존한다."""

    async def run() -> None:
        async with repository_sessions() as session:
            repository = ChatRepository(session)
            chat, _ = await repository.create(
                user_uuid(1), **CHAT_SETTINGS, state="initial"
            )
            chat_id = chat.chat_id
            request_id = uuid4()
            message = ChatLog(
                request_id=request_id,
                chat_id=chat_id,
                question="질문",
                model="test-model",
            )
            await repository.save_message(message)
            message.answer = "답변"
            message.response_id = "external-response"
            message.status = "completed"
            message.finished_at = datetime.now(UTC)
            if fail_commit:
                failure = OperationalError("test-only", {}, RuntimeError())
                with patch.object(session, "commit", AsyncMock(side_effect=failure)):
                    with pytest.raises(DatabaseSaveError) as caught:
                        await repository.save_message_and_state(message, state)
                    assert caught.value.original is failure
            else:
                assert (
                    await repository.save_message_and_state(message, state) is message
                )
            assert not session.in_transaction()

        async with repository_sessions() as session:
            stored_chat = await session.get(Chat, chat_id)
            stored_message = await session.get(ChatLog, request_id)
            assert stored_chat is not None and stored_message is not None
            assert stored_chat.state == ("initial" if fail_commit else state)
            assert stored_message.question == "질문"
            assert stored_message.status == ("pending" if fail_commit else "completed")
            assert stored_message.answer == (None if fail_commit else "답변")
            assert stored_message.response_id == (
                None if fail_commit else "external-response"
            )
            assert (stored_message.finished_at is None) is fail_commit

    asyncio.run(run())


@pytest.fixture
def repository_sessions(
    postgresql_engine: AsyncEngine,
) -> Iterator[async_sessionmaker[AsyncSession]]:
    """두 사용자를 저장한 독립 PostgreSQL 세션 팩토리를 제공한다.

    Args:
        postgresql_engine: 이번 테스트의 PostgreSQL 엔진.

    Yields:
        요청마다 새 세션을 생성하는 팩토리.
    """
    engine = postgresql_engine
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    async def prepare() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with sessions() as session:
            session.add_all(
                User(
                    id=user_id,
                    username=f"owner_{user_id.hex[-8:]}",
                    password_hash="test-only",
                    name="테스트 회원",
                )
                for user_id in (user_uuid(1), user_uuid(2))
            )
            await session.commit()

    asyncio.run(prepare())
    yield sessions


def test_soft_delete_filters_user_queries_and_keeps_other_chats(
    repository_sessions: async_sessionmaker[AsyncSession],
) -> None:
    """삭제된 방만 사용자 조회에서 사라지고 다른 방과 소유권은 유지된다."""

    async def run() -> None:
        deleted_at = datetime(2026, 10, 9, 3, tzinfo=UTC)
        async with repository_sessions() as session:
            repository = ChatRepository(session)
            deleted, _ = await repository.create(user_uuid(1), **CHAT_SETTINGS)
            assert await repository.soft_delete(
                deleted.chat_id, user_uuid(1), deleted_at
            )
            active, _ = await repository.create(user_uuid(1), **CHAT_SETTINGS)
            other, _ = await repository.create(user_uuid(2), **CHAT_SETTINGS)
            assert not session.in_transaction()
            assert (
                await repository.get_by_id_and_user(deleted.chat_id, user_uuid(1))
                is None
            )
            assert (
                await repository.get_by_id_and_user(active.chat_id, user_uuid(1))
                is active
            )
            assert (
                await repository.get_by_id_and_user(other.chat_id, user_uuid(1)) is None
            )
            assert [
                chat.chat_id for chat in await repository.list_by_user(user_uuid(1))
            ] == [active.chat_id]
            assert [
                chat.chat_id for chat in await repository.list_by_user(user_uuid(2))
            ] == [other.chat_id]

        async with repository_sessions() as session:
            stored = await session.get(Chat, deleted.chat_id)
            assert stored is not None
            assert stored.deleted_at == deleted_at
            assert stored.deleted_at.tzinfo is UTC

    asyncio.run(run())


@pytest.mark.parametrize("case", ["missing", "other_owner", "already_deleted"])
def test_soft_delete_unmatched_rows_do_not_change_data(
    repository_sessions: async_sessionmaker[AsyncSession], case: str
) -> None:
    """없는 방·다른 소유자·재삭제의 갱신은 실패하고 최초 삭제 시각을 유지한다."""

    async def run() -> None:
        deleted_at = datetime(2026, 10, 9, 3, tzinfo=UTC)
        async with repository_sessions() as session:
            repository = ChatRepository(session)
            chat, _ = await repository.create(user_uuid(1), **CHAT_SETTINGS)
            if case == "already_deleted":
                assert await repository.soft_delete(
                    chat.chat_id, user_uuid(1), deleted_at
                )
            assert not await repository.soft_delete(
                uuid4() if case == "missing" else chat.chat_id,
                user_uuid(2) if case == "other_owner" else user_uuid(1),
                deleted_at + timedelta(seconds=1),
            )
            assert not session.in_transaction()

        async with repository_sessions() as session:
            stored = await session.get(Chat, chat.chat_id)
            assert stored is not None
            assert stored.deleted_at == (
                deleted_at if case == "already_deleted" else None
            )

    asyncio.run(run())


@pytest.mark.parametrize("status", ["completed", "failed"])
def test_pending_message_finishes_after_soft_delete(
    repository_sessions: async_sessionmaker[AsyncSession], status: str
) -> None:
    """다른 요청이 방을 삭제해도 진행 중 질문의 성공·실패 저장은 완료된다."""

    async def run() -> None:
        deleted_at = datetime(2026, 10, 9, 3, tzinfo=UTC)
        async with repository_sessions() as processing:
            repository = ChatRepository(processing)
            chat, _ = await repository.create(user_uuid(1), **CHAT_SETTINGS)
            message = ChatLog(
                request_id=uuid4(),
                chat_id=chat.chat_id,
                question="처리 중 질문",
                model="test-model",
            )
            await repository.save_message(message)
            async with repository_sessions() as deleting:
                assert await ChatRepository(deleting).soft_delete(
                    chat.chat_id, user_uuid(1), deleted_at
                )
            message.status = status
            message.answer = "완성 답변" if status == "completed" else None
            message.error_code = "AI_TIMEOUT" if status == "failed" else None
            message.finished_at = deleted_at + timedelta(seconds=1)
            await repository.save_message(message)

        async with repository_sessions() as session:
            repository = ChatRepository(session)
            stored_chat = await session.get(Chat, chat.chat_id)
            assert stored_chat is not None
            assert stored_chat.deleted_at == deleted_at
            assert (
                await repository.get_by_id_and_user(chat.chat_id, user_uuid(1)) is None
            )
            stored_message = await session.get(ChatLog, message.request_id)
            assert stored_message is not None
            assert stored_message.question == "처리 중 질문"
            assert stored_message.status == status
            assert stored_message.answer == message.answer
            assert stored_message.error_code == message.error_code
            assert stored_message.finished_at == message.finished_at

    asyncio.run(run())


def test_soft_delete_commit_failure_rolls_back_and_session_remains_usable(
    repository_sessions: async_sessionmaker[AsyncSession],
) -> None:
    """커밋 실패 뒤 삭제 시각을 롤백하고 같은 세션에서 다시 삭제할 수 있다."""

    async def run() -> None:
        deleted_at = datetime(2026, 10, 9, 3, tzinfo=UTC)
        async with repository_sessions() as session:
            repository = ChatRepository(session)
            chat_id = (await repository.create(user_uuid(1), **CHAT_SETTINGS))[
                0
            ].chat_id
            failure = OperationalError("test-only", {}, RuntimeError())
            with patch.object(session, "commit", AsyncMock(side_effect=failure)):
                with pytest.raises(DatabaseSaveError) as caught:
                    await repository.soft_delete(chat_id, user_uuid(1), deleted_at)
                assert caught.value.original is failure
                assert caught.value.__cause__ is failure
            assert not session.in_transaction()
            chat = await repository.get_by_id_and_user(chat_id, user_uuid(1))
            assert chat is not None
            assert chat.deleted_at is None
            assert await repository.soft_delete(chat_id, user_uuid(1), deleted_at)

    asyncio.run(run())


def test_concurrent_soft_deletes_only_store_one_timestamp(
    repository_sessions: async_sessionmaker[AsyncSession],
) -> None:
    """동시에 두 요청이 삭제해도 한 번만 갱신하고 최초 시각을 유지한다."""

    async def run() -> None:
        async with repository_sessions() as session:
            chat_id = (
                await ChatRepository(session).create(user_uuid(1), **CHAT_SETTINGS)
            )[0].chat_id
        timestamps = [
            datetime(2026, 10, 9, 3, tzinfo=UTC),
            datetime(2026, 10, 9, 4, tzinfo=UTC),
        ]

        async def delete(deleted_at: datetime) -> bool:
            async with repository_sessions() as session:
                return await ChatRepository(session).soft_delete(
                    chat_id, user_uuid(1), deleted_at
                )

        results = await asyncio.gather(*(delete(value) for value in timestamps))
        assert results.count(True) == 1
        async with repository_sessions() as session:
            chat = await session.get(Chat, chat_id)
            assert chat is not None
            assert chat.deleted_at == timestamps[results.index(True)]

    asyncio.run(run())


@pytest.mark.parametrize("existing", [False, True])
def test_concurrent_creates_return_one_empty_chat(
    repository_sessions: async_sessionmaker[AsyncSession], existing: bool
) -> None:
    """독립 연결의 동시 생성에서 한 방만 저장하고 모두 같은 ID를 반환한다."""

    async def run() -> None:
        if existing:
            async with repository_sessions() as session:
                await ChatRepository(session).create(user_uuid(1), **CHAT_SETTINGS)
        start = asyncio.Barrier(12)

        async def create() -> tuple[Chat, bool]:
            async with repository_sessions() as session:
                # 인증 조회가 선행된 요청처럼 읽기 후 생성을 실행한다.
                assert await session.get(User, user_uuid(1)) is not None
                await start.wait()
                return await ChatRepository(session).create(
                    user_uuid(1), **CHAT_SETTINGS
                )

        async with asyncio.timeout(15):
            results = await asyncio.gather(*(create() for _ in range(12)))
        assert len({chat.chat_id for chat, _ in results}) == 1
        assert sum(created for _, created in results) == (0 if existing else 1)
        async with repository_sessions() as session:
            chats = await ChatRepository(session).list_by_user(user_uuid(1))
            assert len(chats) == 1
            assert chats[0].chat_id == results[0][0].chat_id

    asyncio.run(run())


@pytest.mark.parametrize("status", ["pending", "completed", "failed"])
def test_any_question_record_allows_new_empty_chat(
    repository_sessions: async_sessionmaker[AsyncSession], status: str
) -> None:
    """질문 처리 상태와 관계없이 기록이 있는 방은 재사용하지 않는다."""

    async def run() -> None:
        async with repository_sessions() as session:
            repository = ChatRepository(session)
            first, created = await repository.create(user_uuid(1), **CHAT_SETTINGS)
            assert created
            reused, created = await repository.create(user_uuid(1), **CHAT_SETTINGS)
            assert not created and reused.chat_id == first.chat_id
            await repository.save_message(
                ChatLog(
                    request_id=uuid4(),
                    chat_id=first.chat_id,
                    question="질문",
                    model="test-model",
                    status=status,
                    answer="답변" if status == "completed" else None,
                    error_code="AI_TIMEOUT" if status == "failed" else None,
                    finished_at=datetime.now(UTC) if status != "pending" else None,
                )
            )
            second, created = await repository.create(user_uuid(1), **CHAT_SETTINGS)
            assert created and second.chat_id != first.chat_id
            other, created = await repository.create(user_uuid(2), **CHAT_SETTINGS)
            assert created and other.chat_id != second.chat_id
            reused, created = await repository.create(user_uuid(1), **CHAT_SETTINGS)
            assert not created and reused.chat_id == second.chat_id

    asyncio.run(run())


@pytest.mark.parametrize("existing", [False, True])
def test_create_commit_failure_rolls_back_and_session_remains_usable(
    repository_sessions: async_sessionmaker[AsyncSession], existing: bool
) -> None:
    """생성·재사용 커밋 실패 후 기록을 보존하고 같은 세션을 재사용한다."""

    async def run() -> None:
        async with repository_sessions() as session:
            repository = ChatRepository(session)
            if existing:
                await repository.create(user_uuid(1), **CHAT_SETTINGS)
            failure = OperationalError("test-only", {}, RuntimeError())
            with patch.object(session, "commit", AsyncMock(side_effect=failure)):
                with pytest.raises(DatabaseSaveError) as caught:
                    await repository.create(user_uuid(1), **CHAT_SETTINGS)
                assert caught.value.original is failure
                assert caught.value.__cause__ is failure
            assert not session.in_transaction()
            assert len(await repository.list_by_user(user_uuid(1))) == int(existing)
            async with repository_sessions() as other_session:
                async with asyncio.timeout(5):
                    recovered, created = await ChatRepository(other_session).create(
                        user_uuid(1), **CHAT_SETTINGS
                    )
                assert created is not existing
            _, created = await repository.create(user_uuid(1), **CHAT_SETTINGS)
            assert not created
            assert not session.in_transaction()
            assert [
                chat.chat_id for chat in await repository.list_by_user(user_uuid(1))
            ] == [recovered.chat_id]

    asyncio.run(run())


def test_user_lock_waits_only_for_same_user(
    repository_sessions: async_sessionmaker[AsyncSession],
) -> None:
    """같은 사용자의 생성만 기다리고 다른 사용자는 잠금 해제 전에 완료한다."""

    async def run() -> None:
        async with repository_sessions() as holder:
            await holder.scalar(
                select(User.id).where(User.id == user_uuid(1)).with_for_update()
            )
            ready = asyncio.Event()
            blocked_pid = None

            async def create_same_user() -> tuple[Chat, bool]:
                nonlocal blocked_pid
                async with repository_sessions() as session:
                    blocked_pid = await session.scalar(text("SELECT pg_backend_pid()"))
                    ready.set()
                    return await ChatRepository(session).create(
                        user_uuid(1), **CHAT_SETTINGS
                    )

            blocked = asyncio.create_task(create_same_user())
            try:
                async with asyncio.timeout(5):
                    await ready.wait()
                    async with repository_sessions() as observer:
                        while True:
                            waiting = await observer.scalar(
                                text(
                                    "SELECT wait_event_type FROM pg_stat_activity "
                                    "WHERE pid = :pid"
                                ),
                                {"pid": blocked_pid},
                            )
                            if waiting == "Lock":
                                break
                            await observer.rollback()
                            await asyncio.sleep(0.01)
                    async with repository_sessions() as other:
                        chat, created = await ChatRepository(other).create(
                            user_uuid(2), **CHAT_SETTINGS
                        )
                        assert created and chat.user_id == user_uuid(2)
                    assert not blocked.done()
            finally:
                await holder.rollback()
                chat, created = await asyncio.wait_for(blocked, timeout=5)
            assert created and chat.user_id == user_uuid(1)

    asyncio.run(run())
