"""MeetingNotesAI FastAPI application entry point."""

from fastapi import FastAPI

from meeting_notes_ai.routes import health, meetings

app = FastAPI(title="MeetingNotesAI", version="0.1.0")

app.include_router(health.router)
app.include_router(meetings.router)
