import asyncio
import os
import sys
from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# 테스트는 운영 설정 파일과 비밀값을 사용하지 않는다.
os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_POSTGRESQL_URL", "postgresql+asyncpg://test:test@127.0.0.1:1/test"
)
os.environ["OPENAI_API_KEY"] = "test-only"
os.environ["JWT_SECRET_KEY"] = "test-only-default-secret-at-least-32-characters"

from app.core.config import Settings  # noqa: E402

Settings.model_config["env_file"] = None


@pytest.fixture
def postgresql_url() -> Iterator[str]:
    """테스트마다 독립 PostgreSQL DB를 생성하고 종료 후 제거한다.

    Yields:
        TEST_POSTGRESQL_URL의 서버에 생성한 임시 DB 연결 주소.
    """
    url = os.environ.get("TEST_POSTGRESQL_URL")
    if not url:
        pytest.fail("DB 테스트에는 TEST_POSTGRESQL_URL 설정이 필요합니다.")
    parsed = make_url(url)
    if parsed.drivername != "postgresql+asyncpg":
        pytest.fail("TEST_POSTGRESQL_URL은 postgresql+asyncpg 주소여야 합니다.")
    name = f"test_b7_{uuid4().hex}"
    admin = create_async_engine(url, poolclass=NullPool, isolation_level="AUTOCOMMIT")

    async def create() -> None:
        async with admin.connect() as connection:
            await connection.execute(text(f'CREATE DATABASE "{name}"'))

    async def cleanup() -> None:
        try:
            async with admin.connect() as connection:
                await connection.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
        finally:
            await admin.dispose()

    asyncio.run(create())
    try:
        yield parsed.set(database=name).render_as_string(hide_password=False)
    finally:
        asyncio.run(cleanup())


@pytest.fixture
def postgresql_engine(postgresql_url: str) -> Iterator[AsyncEngine]:
    """여러 테스트 이벤트 루프에서 사용할 독립 PostgreSQL 엔진을 제공한다.

    Args:
        postgresql_url: 이번 테스트의 임시 DB 연결 주소.

    Yields:
        연결을 재사용하지 않는 PostgreSQL 비동기 엔진.
    """
    engine = create_async_engine(postgresql_url, poolclass=NullPool)
    try:
        yield engine
    finally:
        asyncio.run(engine.dispose())
