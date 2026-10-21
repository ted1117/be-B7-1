from collections.abc import Mapping
from datetime import UTC, datetime
from time import perf_counter
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError

from app.clients.ai import AIClient
from app.core.chat_request_limiter import ChatRequestLimiter
from app.core.errors import APIError
from app.core.logging import log_event
from app.models.chat import ChatLog
from app.repositories.chat_repository import ChatRepository
from app.schemas.chat import (
    ChatDetailResponse,
    ChatListResponse,
    ChatResponse,
    MessageResponse,
)
from app.schemas.error import ResponseErrorCode


class ChatService:
    def __init__(
        self,
        repository: ChatRepository,
        limiter: ChatRequestLimiter,
        clients: Mapping[str, AIClient],
    ) -> None:
        """저장소, 요청 제한기와 제공자별 클라이언트를 연결한다."""
        self.repository = repository
        self.limiter = limiter
        self.clients = clients

    def _get_client(self, provider: str) -> AIClient:
        """설정된 제공자에 대응하는 클라이언트를 반환한다."""
        try:
            return self.clients[provider]
        except KeyError as exc:
            raise APIError("AI_CONFIGURATION_ERROR") from exc

    async def _load_history(
        self, client: AIClient, chat_id: UUID, user_id: UUID
    ) -> list[tuple[str, str]] | None:
        """필요한 이력을 조회하고 조회 실패 시 빈 이력으로 대체한다."""
        if not client.requires_history:
            return None
        try:
            previous = await self.repository.list_recent_completed(chat_id)
            return [
                (item.question, item.answer)
                for item in previous
                if item.answer is not None
            ]
        except SQLAlchemyError as exc:
            await self.repository.session.rollback()
            log_event(
                "chat_context_load_failed",
                user_id=str(user_id),
                chat_id=chat_id,
                result="failure",
                exception_type=type(exc).__name__,
            )
            return []

    async def _prepare_state(
        self, client: AIClient, chat_id: UUID, user_id: UUID, state: str | None
    ) -> str | None:
        """기존 상태를 재사용하거나 새 상태를 생성·저장한다."""
        if state is not None:
            return state
        state = await client.create_state()
        if state is not None:
            await self.repository.save_state(chat_id, state)
            log_event(
                "db_save_succeeded",
                user_id=str(user_id),
                chat_id=chat_id,
                result="success",
            )
        return state

    async def _save_failed_message(
        self,
        message: ChatLog,
        user_id: UUID,
        chat_id: UUID,
        error_code: ResponseErrorCode,
        started_at: float,
    ) -> None:
        """대화 기록의 실패 상태를 저장한다.

        Args:
            message: 실패로 전환할 대화 기록.
            user_id: 인증된 사용자 ID.
            chat_id: 질문을 보낸 채팅방 ID.
            error_code: 저장할 실패 코드.
            started_at: AI 호출 시작 시각의 성능 측정값.
        """
        log_event(
            "ai_call_failed",
            user_id=str(user_id),
            chat_id=chat_id,
            result="failure",
            error_code=error_code,
            duration_ms=round((perf_counter() - started_at) * 1000, 3),
        )
        message.status = "failed"
        message.error_code = error_code
        message.finished_at = datetime.now(UTC)
        await self.repository.save_message(message)
        log_event(
            "db_save_succeeded",
            user_id=str(user_id),
            chat_id=chat_id,
            result="success",
        )

    async def create_chat(
        self, user_id: UUID, *, provider: str, model: str
    ) -> tuple[ChatResponse, bool]:
        """AI 설정을 저장한 빈 채팅방과 신규 생성 여부를 반환한다.

        외부 상태는 첫 메시지 전송 시 준비한다.

        Args:
            user_id: 인증된 사용자 ID.
            provider: 서버가 선택한 AI 제공자.
            model: 사용할 모델 ID.

        Returns:
            채팅방 응답과 신규 생성 여부.

        Raises:
            APIError: 등록되지 않은 제공자인 경우.
            SQLAlchemyError: 채팅방 저장에 실패한 경우.
        """
        self._get_client(provider)
        chat, created = await self.repository.create(
            user_id, provider=provider, model=model
        )
        if created:
            log_event(
                "db_save_succeeded",
                user_id=str(user_id),
                chat_id=chat.chat_id,
                result="success",
            )
        return ChatResponse.model_validate(chat), created

    async def list_chats(self, user_id: UUID) -> ChatListResponse:
        """사용자의 채팅방 목록을 조회한다."""
        chats = await self.repository.list_by_user(user_id)
        return ChatListResponse(
            items=[ChatResponse.model_validate(chat) for chat in chats]
        )

    async def get_chat(self, chat_id: UUID, user_id: UUID) -> ChatDetailResponse:
        """사용자의 채팅방과 대화 기록을 조회한다."""
        chat = await self.repository.get_by_id_and_user(chat_id, user_id)
        if chat is None:
            raise APIError("CHAT_NOT_FOUND")
        messages = await self.repository.list_messages(chat_id)
        return ChatDetailResponse(
            chat_id=chat.chat_id,
            created_at=chat.created_at,
            messages=[MessageResponse.model_validate(message) for message in messages],
        )

    async def delete_chat(self, chat_id: UUID, user_id: UUID) -> None:
        """사용자의 채팅방을 논리 삭제한다."""
        deleted = await self.repository.soft_delete(chat_id, user_id, datetime.now(UTC))
        if not deleted:
            raise APIError("CHAT_NOT_FOUND")
        log_event(
            "db_save_succeeded",
            user_id=str(user_id),
            chat_id=chat_id,
            result="success",
        )

    async def send_message(
        self,
        chat_id: UUID,
        user_id: UUID,
        request_id: UUID,
        question: str,
    ) -> MessageResponse:
        """질문에 대한 AI 답변을 생성하고 대화 기록을 저장한다.

        Args:
            chat_id: 질문을 보낼 채팅방의 ID.
            user_id: 인증된 사용자 ID.
            request_id: 서버에서 생성한 최초 질문 요청의 ID.
            question: 앞뒤 공백과 빈 입력 검증을 마친 질문.

        Returns:
            질문·답변 저장을 완료한 대화 기록.

        Raises:
            APIError: 소유권 검사·사용자 점유 또는 AI 호출에 실패한 경우.
            Exception: 예상하지 못한 AI 예외가 발생하고 실패 기록 저장 후
                다시 전달되는 경우.
            SQLAlchemyError: 조회·질문·상태·처리 결과 저장에 실패한 경우.
        """
        chat = await self.repository.get_by_id_and_user(chat_id, user_id)
        if chat is None:
            raise APIError("CHAT_NOT_FOUND")
        async with self.limiter.acquire(user_id):
            client = self._get_client(chat.provider)
            model = chat.model
            state = await self.repository.get_state(chat_id)
            history = await self._load_history(client, chat_id, user_id)
            message = ChatLog(
                request_id=request_id,
                chat_id=chat_id,
                question=question,
                model=model,
                status="pending",
            )
            await self.repository.save_message(message)
            log_event(
                "db_save_succeeded",
                user_id=str(user_id),
                chat_id=chat_id,
                result="success",
            )
            started_at = perf_counter()
            log_event("ai_call_started", user_id=str(user_id), chat_id=chat_id)
            try:
                state = await self._prepare_state(client, chat_id, user_id, state)
                result = await client.generate_answer(
                    model=model, state=state, history=history, question=question
                )
            except SQLAlchemyError:
                raise
            except APIError as exc:
                await self._save_failed_message(
                    message, user_id, chat_id, exc.api_code, started_at
                )
                raise
            except Exception:
                await self._save_failed_message(
                    message, user_id, chat_id, "INTERNAL_ERROR", started_at
                )
                raise
            log_event(
                "ai_call_succeeded",
                user_id=str(user_id),
                chat_id=chat_id,
                result="success",
                duration_ms=round((perf_counter() - started_at) * 1000, 3),
            )
            message.answer = result.text
            message.response_id = result.response_id
            message.status = "completed"
            message.finished_at = datetime.now(UTC)
            await self.repository.save_message_and_state(message, result.state)
            log_event(
                "db_save_succeeded",
                user_id=str(user_id),
                chat_id=chat_id,
                result="success",
            )
            return MessageResponse.model_validate(message)
