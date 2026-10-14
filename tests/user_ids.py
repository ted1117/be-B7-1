from uuid import UUID


def user_uuid(value: int) -> UUID:
    """테스트 사용자 번호에 대응하는 고정 UUID4를 반환한다."""
    return UUID(f"00000000-0000-4000-8000-{value:012x}")
