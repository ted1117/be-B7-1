from collections.abc import Mapping
from typing import Annotated
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.ai import AIClient
from app.core.chat_request_limiter import ChatRequestLimiter
from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.security import decode_access_token
from app.models.user import User
from app.repositories.admin_db import (
    DbChatLogRepository,
    DbSessionRepository,
    DbUserRepository,
)
from app.repositories.admin_system_log import SystemLogFileRepository
from app.repositories.chat_repository import ChatRepository
from app.repositories.token_repository import TokenRepository
from app.services.admin_service import AdminService
from app.services.chat_service import ChatService


###############################################################################
# 공통: DB 세션, 요청 식별자, 설정
###############################################################################
def get_request_id(request: Request) -> UUID:
    """미들웨어가 생성한 현재 요청의 식별자를 반환한다.

    Args:
        request: 현재 HTTP 요청.

    Returns:
        서버에서 생성한 UUID4 식별자.
    """
    return request.state.request_id


DBSession = Annotated[AsyncSession, Depends(get_db)]
RequestId = Annotated[UUID, Depends(get_request_id)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


###############################################################################
# 회원 인증
###############################################################################
bearer = HTTPBearer(auto_error=False)


# 회원 인증: JWT와 폐기 여부를 검증하고 DB에서 현재 회원을 반환한다.
async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    db: DBSession,
) -> User:
    unauthorized = HTTPException(
        status_code=401,
        detail="로그인이 필요합니다.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise unauthorized
    try:
        user_id = decode_access_token(credentials.credentials)
    except (jwt.InvalidTokenError, ValueError):
        raise unauthorized from None
    # 로그아웃 구현: 폐기된 토큰은 만료 전에도 인증을 거절한다.
    if await TokenRepository(db).is_revoked(credentials.credentials):
        raise unauthorized
    user = await db.get(User, user_id)
    if user is None:
        raise unauthorized
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def get_current_user_id(user: CurrentUser) -> UUID:
    """인증된 회원의 UUID를 반환한다."""
    return user.id


CurrentUserId = Annotated[UUID, Depends(get_current_user_id)]


###############################################################################
# 관리자
###############################################################################
async def require_admin(user: CurrentUser) -> dict:
    """공통 인증을 통과한 회원의 관리자 권한을 확인한다."""
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다.")
    # user_id는 역할 변경 API의 본인 강등 가드가 쓴다.
    return {"role": "admin", "mock": False, "user_id": user.id}


def get_admin_service(db: DBSession) -> AdminService:
    """관리자 조회에 필요한 저장소를 연결해 서비스를 생성한다."""
    settings = get_settings()
    return AdminService(
        users=DbUserRepository(db),
        chat_logs=DbChatLogRepository(db),
        sessions=DbSessionRepository(db),
        system_logs=SystemLogFileRepository(settings.system_log_path),
    )


CurrentAdmin = Annotated[dict, Depends(require_admin)]
AdminServiceDep = Annotated[AdminService, Depends(get_admin_service)]


###############################################################################
# 채팅 공용 자원
###############################################################################
def get_chat_request_limiter(request: Request) -> ChatRequestLimiter:
    """앱 시작 시 생성한 공용 채팅 요청 제한기를 반환한다."""
    return request.app.state.chat_request_limiter


def get_ai_clients(request: Request) -> Mapping[str, AIClient]:
    """앱 시작 시 생성한 제공자별 공용 AI 클라이언트를 반환한다."""
    return request.app.state.ai_clients


ChatRequestLimiterDep = Annotated[ChatRequestLimiter, Depends(get_chat_request_limiter)]
AIClientsDep = Annotated[Mapping[str, AIClient], Depends(get_ai_clients)]


###############################################################################
# 채팅 서비스
###############################################################################
def get_chat_service(
    request: Request,
    user_id: CurrentUserId,
    db: DBSession,
    limiter: ChatRequestLimiterDep,
    clients: AIClientsDep,
) -> ChatService:
    """채팅 서비스를 생성하고 인증된 ID를 요청 로그에 연결한다.

    Args:
        request: 현재 HTTP 요청.
        user_id: 인증 의존성에서 제공한 사용자 ID.
        db: 요청의 비동기 DB 세션.
        limiter: 앱 전체에서 공유하는 채팅 요청 제한기.
        clients: 제공자 이름으로 선택할 공용 AI 클라이언트 목록.

    Returns:
        채팅방과 대화 기록을 처리할 서비스.
    """
    request.state.user_id = user_id
    return ChatService(ChatRepository(db), limiter, clients)


ChatServiceDep = Annotated[ChatService, Depends(get_chat_service)]
