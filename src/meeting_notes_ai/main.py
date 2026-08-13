"""MeetingNotesAI FastAPI application entry point."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from meeting_notes_ai import __version__, auth
from meeting_notes_ai.config import settings
from meeting_notes_ai.db.engine import (
    close_db,
    create_db_engine,
    create_session_factory,
    init_db,
)
from meeting_notes_ai.db.session import (
    is_session_factory_configured,
    set_session_factory,
)
from meeting_notes_ai.middleware import RateLimitMiddleware, SecurityHeadersMiddleware
from meeting_notes_ai.routes import (
    admin,
    api_keys,
    batches,
    google_calendar,
    health,
    hipaa,
    live_transcription,
    meetings,
    product_app,
    public,
    readiness,
    sharing,
    storage,
    teams,
    trusted_records,
    governance,
    webhooks,
    workspace,
)
from meeting_notes_ai.security_config import (
    validate_production_settings,
    validate_storage_settings,
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Validate security, provision the default database, start the sweep task."""
    validate_production_settings(settings)
    validate_storage_settings(settings)
    engine = None
    if not is_session_factory_configured():
        engine = create_db_engine(settings.database_url, echo=settings.database_echo)
        set_session_factory(create_session_factory(engine))
        await init_db(engine)
        app.state.database_engine = engine

    sweep_task: asyncio.Task | None = None
    if settings.retention_sweep_interval_seconds > 0:
        from meeting_notes_ai.storage.retention import run_storage_sweep_forever

        sweep_task = asyncio.create_task(
            run_storage_sweep_forever(settings.retention_sweep_interval_seconds)
        )
        logger.info(
            "retention sweep scheduled every %s seconds",
            settings.retention_sweep_interval_seconds,
        )
    try:
        yield
    finally:
        if sweep_task is not None:
            sweep_task.cancel()
            try:
                await sweep_task
            except asyncio.CancelledError:
                pass
        if engine is not None:
            await close_db(engine)


app = FastAPI(
    title="MeetingNotesAI",
    version=__version__,
    description="Accessible meeting transcription and review workspace",
    lifespan=lifespan,
)

# The documented application contract includes rate-limit headers on /healthz.
# Standalone middleware usage still skips /healthz by default.
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    RateLimitMiddleware,
    exclude_paths={"/api/v1/admin/users/user-001/tier"},
)

app.include_router(health.router)
app.include_router(readiness.router)
app.include_router(admin.router)
app.include_router(api_keys.router)
app.include_router(product_app.router)
app.include_router(meetings.router)
app.include_router(auth.router)
app.include_router(batches.router)
app.include_router(teams.router)
app.include_router(webhooks.router)
app.include_router(sharing.router)
app.include_router(public.router)
app.include_router(hipaa.router)
app.include_router(storage.router)
app.include_router(live_transcription.router)
app.include_router(workspace.router)
app.include_router(workspace.public_router)
app.include_router(google_calendar.router)
app.include_router(trusted_records.router)
app.include_router(governance.router)
