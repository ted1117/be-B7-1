import asyncio
import json
from collections.abc import Awaitable, Callable
from unittest.mock import AsyncMock, MagicMock

import httpx2
import pytest
from openai import AsyncOpenAI

from app.clients.ai import DEFAULT_INSTRUCTIONS, AIResponse
from app.clients.openai import OpenAIClient
from app.core.errors import APIError


def _payload() -> dict[str, object]:
    return {
        "id": "resp_test",
        "object": "response",
        "created_at": 1,
        "status": "completed",
        "model": "test-model",
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
    }


def _client(
    monkeypatch: pytest.MonkeyPatch,
    handler: Callable[[httpx2.Request], Awaitable[httpx2.Response]],
    *,
    timeout: float = 30,
) -> OpenAIClient:
    connection = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
    sdk = AsyncOpenAI(api_key="test-only", max_retries=0, http_client=connection)
    monkeypatch.setattr("app.clients.openai.AsyncOpenAI", MagicMock(return_value=sdk))
    return OpenAIClient(api_key="test-only", timeout=timeout, max_retries=4)


@pytest.mark.parametrize("state", [None, "conv_test"])
def test_request_model_state_and_normalized_result(
    monkeypatch: pytest.MonkeyPatch, state: str | None
) -> None:
    """요청별 모델과 상태 전달, 공통 결과 및 Conversation 재사용을 검증한다."""
    requests: list[dict[str, object]] = []

    async def handler(request: httpx2.Request) -> httpx2.Response:
        assert request.url.path == "/v1/responses"
        requests.append(json.loads(request.content))
        return httpx2.Response(200, json=_payload())

    client = _client(monkeypatch, handler)
    assert client.requires_history is False

    async def run() -> None:
        try:
            for model in ["first-model", "second-model"]:
                result = await client.generate_answer(
                    model=model, state=state, history=None, question="현재 질문"
                )
                assert result == AIResponse("답변", state, "resp_test")
        finally:
            await client.close()

    asyncio.run(run())
    assert [body["model"] for body in requests] == ["first-model", "second-model"]
    for body in requests:
        assert body["conversation"] == state
        assert body["input"] == [{"role": "user", "content": "현재 질문"}]
        assert body["instructions"] == DEFAULT_INSTRUCTIONS
        assert body["store"] is (state is not None)
        assert body["context_management"] == (
            [{"type": "compaction", "compact_threshold": 20_000}]
            if state is not None
            else None
        )


@pytest.mark.parametrize("operation", ["create", "answer"])
@pytest.mark.parametrize(
    ("scenario", "expected_code", "calls"),
    [
        ("success", None, 1),
        ("401", "AI_CONFIGURATION_ERROR", 1),
        ("403", "AI_CONFIGURATION_ERROR", 1),
        ("404", "AI_CONFIGURATION_ERROR", 1),
        ("429", "AI_UNAVAILABLE", 5),
        ("500", "AI_UNAVAILABLE", 1),
        ("connection", "AI_UNAVAILABLE", 1),
        ("timeout", "AI_TIMEOUT", 1),
        ("deadline", "AI_TIMEOUT", 1),
        ("malformed", "AI_UNAVAILABLE", 1),
        ("missing_id", "AI_UNAVAILABLE", 1),
        ("blank_id", "AI_UNAVAILABLE", 1),
        ("null_id", "AI_UNAVAILABLE", 1),
        ("numeric_id", "AI_UNAVAILABLE", 1),
    ],
)
def test_state_creation_and_answer_failures(
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
    scenario: str,
    expected_code: str | None,
    calls: int,
) -> None:
    """상태 생성·답변의 ID 검증, 타임아웃과 제한적인 재시도를 검증한다."""
    requests: list[httpx2.Request] = []

    async def handler(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        if scenario == "connection":
            raise httpx2.ConnectError("hidden", request=request)
        if scenario == "timeout":
            raise httpx2.ReadTimeout("hidden", request=request)
        if scenario == "deadline":
            await asyncio.sleep(0.1)
        if scenario == "malformed":
            return httpx2.Response(
                200, content=b"{", headers={"content-type": "application/json"}
            )
        if scenario.isdigit():
            return httpx2.Response(int(scenario), json={"error": {"message": "hidden"}})
        body = (
            {"id": "conv_test", "object": "conversation", "created_at": 1}
            if operation == "create"
            else _payload()
        )
        if scenario == "missing_id":
            del body["id"]
        elif scenario == "blank_id":
            body["id"] = " \t"
        elif scenario == "null_id":
            body["id"] = None
        elif scenario == "numeric_id":
            body["id"] = 123
        return httpx2.Response(200, json=body)

    client = _client(
        monkeypatch, handler, timeout=0.01 if scenario == "deadline" else 30
    )
    if scenario != "deadline":
        monkeypatch.setattr("app.clients.openai.asyncio.sleep", AsyncMock())

    async def run() -> None:
        try:

            async def call() -> str | AIResponse:
                if operation == "create":
                    return await client.create_state()
                return await client.generate_answer(
                    model="test-model", state="conv_test", history=None, question="질문"
                )

            if expected_code is None:
                result = await call()
                assert result == (
                    "conv_test"
                    if operation == "create"
                    else AIResponse("답변", "conv_test", "resp_test")
                )
            else:
                with pytest.raises(APIError) as caught:
                    await call()
                assert caught.value.code == expected_code
        finally:
            await client.close()

    asyncio.run(run())
    assert len(requests) == (1 if operation == "create" else calls)
    assert all(
        request.url.path
        == ("/v1/conversations" if operation == "create" else "/v1/responses")
        for request in requests
    )


@pytest.mark.parametrize(
    "overrides",
    [{"state": " "}, {"model": " "}, {"history": [("이전 질문", "이전 답변")]}],
)
def test_invalid_input_does_not_call_provider(
    monkeypatch: pytest.MonkeyPatch, overrides: dict[str, object]
) -> None:
    """잘못된 모델·상태와 불필요한 이력은 외부 호출 전에 거절한다."""
    handler = AsyncMock()
    client = _client(monkeypatch, handler)
    arguments = dict(
        model="test-model", state="conv_test", history=None, question="질문"
    )
    arguments.update(overrides)

    async def run() -> None:
        try:
            with pytest.raises(APIError) as caught:
                await client.generate_answer(**arguments)
            assert caught.value.code == "AI_CONFIGURATION_ERROR"
        finally:
            await client.close()

    asyncio.run(run())
    handler.assert_not_awaited()
