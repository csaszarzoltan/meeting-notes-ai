from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from meeting_notes_ai.services.share_policy import eligible_snapshot


class Scalar:
    def __init__(self, value):
        self.value = value

    def scalars(self):
        return self

    def first(self):
        return self.value


@pytest.mark.asyncio
async def test_us_003_ac_1_strict_meeting_requires_snapshot():
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[Scalar(None), Scalar(None)])
    meeting = MagicMock(id="m", team_id=None, mode="healthcare")
    with pytest.raises(HTTPException) as exc:
        await eligible_snapshot(db, meeting)
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_us_003_ac_2_general_compatibility_allows_no_snapshot():
    db = AsyncMock()
    db.execute = AsyncMock(return_value=Scalar(None))
    meeting = MagicMock(id="m", team_id=None, mode="general")
    assert await eligible_snapshot(db, meeting) is None
