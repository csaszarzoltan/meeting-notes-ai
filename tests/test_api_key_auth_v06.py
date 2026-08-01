"""Acceptance tests for using generated API keys as credentials."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from meeting_notes_ai.auth import get_current_user
from meeting_notes_ai.routes.api_keys import _hash_api_key


@pytest.mark.asyncio
async def test_x_api_key_authenticates_active_owner():
    plaintext = "abcd1234-secret-material"
    owner = SimpleNamespace(
        id="user-1", email="user@example.com", display_name="User", is_active=True
    )
    record = SimpleNamespace(
        user_id="user-1",
        hashed_key=_hash_api_key(plaintext),
        is_active=True,
        tier="pro",
        user=owner,
        last_used_at=None,
    )
    result = SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [record]))
    db = AsyncMock()
    db.execute.return_value = result

    principal = await get_current_user(
        authorization=None,
        x_api_key=plaintext,
        db=db,
    )

    assert principal["user_id"] == "user-1"
    assert principal["tier"] == "pro"
    assert record.last_used_at is not None
    db.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_invalid_x_api_key_returns_401():
    result = SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: []))
    db = AsyncMock()
    db.execute.return_value = result

    with pytest.raises(Exception) as exc_info:
        await get_current_user(
            authorization=None,
            x_api_key="missing-key",
            db=db,
        )
    assert getattr(exc_info.value, "status_code", None) == 401
