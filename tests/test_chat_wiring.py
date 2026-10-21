import asyncio
import json
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import httpx2
import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from openai import AsyncOpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import app.core.database as database
import app.main as main
from app.api.dependencies import get_ai_clients, get_current_user_id
from app.api.v1.router import api_router
from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.errors import configure_request_processing
from app.models.chat import Chat, ChatLog
from app.models.user import User
from tests.user_ids import user_uuid


@pytest.mark.parametrize("fail_first", [False, True])
def test_lifespan_dependencies_routes_and_persistence(
    postgresql_url: str, monkeypatch: pytest.MonkeyPatch, fail_first: bool
) -> None:
    """실제 API·서비스·DB와 SDK를 연결해 생성·전송·실패·재사용을 검증한다."""
    settings = Settings(
        _env_file=None,
        database_url=postgresql_url,
        openai_api_key="test-only",
        openai_model="server-model",
        ai_max_retries=0,
        jwt_secret_key="test-only-wiring-secret-at-least-32-characters",
    )
    engine = create_async_engine(postgresql_url, poolclass=NullPool)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(main, "settings", settings)
    monkeypatch.setattr(main, "engine", engine)
    monkeypatch.setattr(database, "engine", engine)
    requests: list[httpx2.Request] = []

    async def handler(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        if request.url.path == "/v1/conversations":
            return httpx2.Response(
                200, json={"id": "conv_test", "object": "conversation", "created_at": 1}
            )
        assert request.url.path == "/v1/responses"
        body = json.loads(request.content)
        assert body["model"] == "server-model"
        assert body["conversation"] == "conv_test"
        if fail_first and len(requests) == 2:
            return httpx2.Response(429, json={"error": {"message": "hidden"}})
        return httpx2.Response(
            200,
            json={
                "id": f"resp_{len(requests)}",
                "object": "response",
                "created_at": 1,
                "status": "completed",
                "model": "server-model",
                "output": [
                    {
                        "id": "msg_test",
                        "type": "message",
                        "role": "assistant",
                        "status": "completed",
                        "content": [
                            {
                                "type": "output_text",
                                "text": "답변",
                                "annotations": [],
                            }
                        ],
                    }
                ],
            },
        )

    connection = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
    sdk = AsyncOpenAI(api_key="test-only", max_retries=0, http_client=connection)
    monkeypatch.setattr("app.clients.openai.AsyncOpenAI", MagicMock(return_value=sdk))
    app = FastAPI(lifespan=main.lifespan)
    configure_request_processing(app)
    app.include_router(api_router, prefix="/api/v1")

    async def test_db() -> AsyncGenerator[AsyncSession, None]:
        async with sessions() as session:
            yield session

    app.dependency_overrides[get_db] = test_db
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_current_user_id] = lambda: user_uuid(1)

    async def seed() -> None:
        async with sessions() as session:
            session.add(
                User(
                    id=user_uuid(1),
                    username="wiring-owner",
                    password_hash="test-only",
                    name="테스트",
                )
            )
            await session.commit()

    with TestClient(app) as client:
        asyncio.run(seed())
        created = client.post("/api/v1/chats")
        assert created.status_code == 201
        chat_id = created.json()["chat_id"]
        reused = client.post("/api/v1/chats")
        assert reused.status_code == 200 and reused.json()["chat_id"] == chat_id
        assert requests == []
        url = f"/api/v1/chats/{chat_id}/messages"
        first = client.post(url, json={"question": "첫 질문"})
        assert first.status_code == (502 if fail_first else 201)
        second = client.post(url, json={"question": "다음 질문"})
        assert second.status_code == 201 and second.json()["answer"] == "답변"
        assert client.get(f"/api/v1/chats/{chat_id}").status_code == 200
        assert client.delete(f"/api/v1/chats/{chat_id}").status_code == 204
        assert client.get(f"/api/v1/chats/{chat_id}").status_code == 404
    assert connection.is_closed
    assert [request.url.path for request in requests] == [
        "/v1/conversations",
        "/v1/responses",
        "/v1/responses",
    ]

    async def verify() -> None:
        try:
            async with sessions() as session:
                room = (await session.scalars(select(Chat))).one()
                logs = list(
                    (
                        await session.scalars(
                            select(ChatLog).order_by(ChatLog.created_at)
                        )
                    ).all()
                )
                assert (room.provider, room.model, room.state) == (
                    "openai",
                    "server-model",
                    "conv_test",
                )
                assert [log.status for log in logs] == [
                    "failed" if fail_first else "completed",
                    "completed",
                ]
                assert logs[0].error_code == ("AI_UNAVAILABLE" if fail_first else None)
                assert logs[0].response_id == (None if fail_first else "resp_2")
                assert logs[1].response_id == "resp_3"
        finally:
            await engine.dispose()

    asyncio.run(verify())


@pytest.mark.parametrize(
    "scenario", ["success", "create_error", "body_error", "close_error"]
)
def test_client_registry_and_resource_cleanup(
    monkeypatch: pytest.MonkeyPatch, scenario: str
) -> None:
    """공용 클라이언트 목록 재사용과 초기화·요청·종료 오류의 정리를 검증한다."""
    settings = Settings(
        _env_file=None,
        openai_api_key="test-only",
        jwt_secret_key="test-only-wiring-secret-at-least-32-characters",
    )
    monkeypatch.setattr(main, "settings", settings)
    monkeypatch.setattr(main, "create_db_and_tables", AsyncMock())
    engine = MagicMock()
    engine.dispose = AsyncMock()
    monkeypatch.setattr(main, "engine", engine)
    client = MagicMock()
    client.close = AsyncMock()
    failure = RuntimeError("lifecycle failure")
    constructor = MagicMock(return_value=client)
    if scenario == "create_error":
        constructor.side_effect = failure
    elif scenario == "close_error":
        client.close.side_effect = failure
    monkeypatch.setattr(main, "OpenAIClient", constructor)
    app = FastAPI(lifespan=main.lifespan)

    async def run() -> None:
        async with main.lifespan(app):
            first = Request({"type": "http", "app": app})
            second = Request({"type": "http", "app": app})
            assert get_ai_clients(first) is get_ai_clients(second)
            assert get_ai_clients(first) == {"openai": client}
            if scenario == "body_error":
                raise failure

    if scenario == "success":
        asyncio.run(run())
    else:
        with pytest.raises(RuntimeError) as caught:
            asyncio.run(run())
        assert caught.value is failure
    constructor.assert_called_once_with("test-only", 30, 4)
    engine.dispose.assert_awaited_once()
    assert client.close.await_count == (0 if scenario == "create_error" else 1)
