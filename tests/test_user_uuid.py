import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
import pytest
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.config import get_settings
from app.core.database import Base
from app.core.security import create_access_token, decode_access_token
from app.main import app
from app.models.user import User
from tests.user_ids import user_uuid


def test_user_ids_are_generated_and_stored_as_uuid(
    postgresql_engine: AsyncEngine,
) -> None:
    """회원 ID를 UUID4로 자동 생성하고 독립 세션에서 같은 UUID를 조회한다."""

    async def run() -> None:
        async with postgresql_engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
            columns = await connection.run_sync(
                lambda conn: {
                    table: inspect(conn).get_columns(table)
                    for table in ("users", "chats")
                }
            )
            for table, name in (("users", "id"), ("chats", "user_id")):
                column = next(c for c in columns[table] if c["name"] == name)
                assert str(column["type"]) == "UUID"
        async with AsyncSession(postgresql_engine, expire_on_commit=False) as session:
            users = [
                User(username=f"uuid_user_{n}", password_hash="test-only", name="회원")
                for n in range(2)
            ]
            session.add_all(users)
            await session.commit()
            ids = [user.id for user in users]
            assert len(set(ids)) == 2
            assert all(isinstance(value, UUID) and value.version == 4 for value in ids)
        async with AsyncSession(postgresql_engine) as session:
            for value in ids:
                assert (await session.get(User, value)).id == value

    asyncio.run(run())


def test_jwt_round_trip_returns_uuid() -> None:
    """JWT의 문자열 sub를 검증하고 회원 UUID로 복원한다."""
    value = user_uuid(1)
    token, _ = create_access_token(value)
    claims = jwt.decode(token, get_settings().jwt_secret_key, algorithms=["HS256"])
    assert claims["sub"] == str(value)
    assert decode_access_token(token) == value


@pytest.mark.parametrize("subject", ["1", "-1", "not-a-uuid", "", 1, None])
def test_jwt_rejects_legacy_or_invalid_subject(subject: object) -> None:
    """기존 정수 회원 ID와 잘못된 UUID sub를 가진 서명된 JWT를 거절한다."""
    now = datetime.now(UTC)
    token = jwt.encode(
        {"sub": subject, "iat": now, "exp": now + timedelta(minutes=5)},
        get_settings().jwt_secret_key,
        algorithm="HS256",
    )
    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token(token)


def test_openapi_declares_uuid_user_identifiers() -> None:
    """회원 응답·관리자 경로·조회 조건의 ID를 UUID 문자열로 명시한다."""
    schema = app.openapi()
    for name in (
        "SignupResponse",
        "MyInfoResponse",
        "UserSummary",
        "RoleUpdateResponse",
    ):
        field = schema["components"]["schemas"][name]["properties"]["id"]
        assert field["type"] == "string" and field["format"] == "uuid"
    for path, method in (
        ("/api/v1/admin/users/{user_id}", "get"),
        ("/api/v1/admin/logs", "get"),
        ("/api/v1/admin/sessions", "get"),
    ):
        field = next(
            p["schema"]
            for p in schema["paths"][path][method]["parameters"]
            if p["name"] == "user_id"
        )
        variants = field.get("anyOf", [field])
        assert any(
            v.get("type") == "string" and v.get("format") == "uuid" for v in variants
        )
