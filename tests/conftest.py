import os
import sys
from pathlib import Path

from sqlalchemy.engine.interfaces import DBAPIConnection
from sqlalchemy.pool import ConnectionPoolEntry

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# .env가 없을 때만 키 기본값을 둔다. .env가 있으면 건드리지 않는다.
if not (Path(__file__).resolve().parents[1] / ".env").exists():
    os.environ.setdefault("OPENAI_API_KEY", "test")
    os.environ.setdefault(
        "JWT_SECRET_KEY", "test-only-default-secret-at-least-32-characters"
    )


def _enable_sqlite_foreign_keys(
    connection: DBAPIConnection, connection_record: ConnectionPoolEntry
) -> None:
    """기존 SQLite 테스트 연결에서 외래키 검사를 활성화한다."""
    cursor = connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()
