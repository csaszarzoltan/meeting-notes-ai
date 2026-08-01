"""MeetingNotesAI FastAPI application entry point."""

from fastapi import FastAPI

from meeting_notes_ai import __version__, auth
from meeting_notes_ai.middleware import RateLimitMiddleware
from meeting_notes_ai.routes import (
    admin,
    api_keys,
    batches,
    health,
    hipaa,
    meetings,
    product_app,
    public,
    sharing,
    teams,
    webhooks,
)

app = FastAPI(
    title="MeetingNotesAI",
    version=__version__,
    description="Accessible meeting transcription and review workspace",
)

app.add_middleware(RateLimitMiddleware, exclude_paths={"/api/v1/admin/users/user-001/tier"})

app.include_router(health.router)
app.include_router(admin.router)
app.include_router(api_keys.router)
app.include_router(product_app.router)
app.include_router(meetings.router)
app.include_router(auth.router)
app.include_router(batches.router)
app.include_router(teams.router)
app.include_router(webhooks.router)

# v0.3.0 — Meeting Sharing
app.include_router(sharing.router)
app.include_router(public.router)

# v0.5.0 — HIPAA compliance REST endpoints
app.include_router(hipaa.router)
