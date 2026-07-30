"""MeetingNotesAI FastAPI application entry point."""

from fastapi import FastAPI

from meeting_notes_ai import auth
from meeting_notes_ai.routes import batches, health, meetings, public, sharing, teams, webhooks

app = FastAPI(title="MeetingNotesAI", version="0.2.0")

app.include_router(health.router)
app.include_router(meetings.router)
app.include_router(auth.router)
app.include_router(batches.router)
app.include_router(teams.router)
app.include_router(webhooks.router)

# v0.3.0 — Meeting Sharing
app.include_router(sharing.router)
app.include_router(public.router)
