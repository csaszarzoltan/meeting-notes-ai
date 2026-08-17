"""Background token refresh worker for PM tool OAuth2 integrations.

Polls PMIntegrationToken rows and refreshes tokens that are about to expire
(within 5 minutes of expiry). Runs as an asyncio task inside the FastAPI
lifespan.

Usage (wired in main.py lifespan)::

    token_refresh_task = asyncio.create_task(run_token_refresh_loop())
    yield
    token_refresh_task.cancel()
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from meeting_notes_ai.db.models import PMIntegrationToken
from meeting_notes_ai.db.session import get_db_session

logger = logging.getLogger(__name__)

_TOKEN_EXPIRY_BUFFER_SECONDS = 5 * 60  # refresh 5 minutes before expiry


async def _refresh_expiring_tokens() -> int:
    """Find and refresh tokens expiring within the buffer window.

    Returns the number of tokens successfully refreshed.
    """
    refreshed_count = 0
    cutoff = datetime.now(timezone.utc) + timedelta(seconds=_TOKEN_EXPIRY_BUFFER_SECONDS)

    async for db in get_db_session():
        result = await db.execute(
            select(PMIntegrationToken).where(
                PMIntegrationToken.is_active.is_(True),
                PMIntegrationToken.token_expires_at.isnot(None),
                PMIntegrationToken.token_expires_at <= cutoff,
            )
        )
        tokens = result.scalars().all()

        if not tokens:
            logger.debug("token_refresh: no expiring tokens found")
            return 0

        logger.info("token_refresh: found %d expiring token(s)", len(tokens))

        for token_row in tokens:
            try:
                # Import here to avoid circular imports at module level
                from meeting_notes_ai.services.oauth2 import refresh_token

                success = await refresh_token(
                    provider=token_row.provider,
                    user_id=token_row.user_id,
                    db=db,
                )
                if success:
                    refreshed_count += 1
                    logger.info(
                        "token_refresh: refreshed token for provider=%s user=%s",
                        token_row.provider,
                        token_row.user_id[:8],
                    )
                else:
                    logger.warning(
                        "token_refresh: refresh FAILED for provider=%s user=%s — "
                        "token marked inactive, re-auth required",
                        token_row.provider,
                        token_row.user_id[:8],
                    )
            except Exception:
                logger.exception(
                    "token_refresh: exception refreshing token for provider=%s user=%s",
                    token_row.provider,
                    token_row.user_id[:8],
                )

        await db.commit()

    return refreshed_count


async def run_token_refresh_loop(interval_seconds: int = 300) -> None:
    """Poll PMIntegrationToken rows; refresh tokens expiring within 5min.

    Every *interval_seconds*:
      1. Query PMIntegrationToken where token_expires_at is within 5 minutes
      2. For each token, call oauth2.refresh_token(provider, user_id)
      3. If refresh fails, mark token as inactive (handled by refresh_token)
      4. Log results
    """
    logger.info("token_refresh: worker started, interval=%ds", interval_seconds)
    while True:
        try:
            count = await _refresh_expiring_tokens()
            if count:
                logger.info("token_refresh: successfully refreshed %d token(s)", count)
        except Exception:
            logger.exception("token_refresh: unexpected error in refresh loop")
        await asyncio.sleep(interval_seconds)
