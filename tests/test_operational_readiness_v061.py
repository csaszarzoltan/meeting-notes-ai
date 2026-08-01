"""Acceptance tests for operational and browser security readiness."""

from fastapi.testclient import TestClient

from meeting_notes_ai.main import app


def test_readyz_reports_database_ready():
    with TestClient(app) as client:
        response = client.get("/readyz")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["checks"]["database"] == "up"


def test_browser_responses_include_security_headers():
    with TestClient(app) as client:
        response = client.get("/app")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert response.headers["Permissions-Policy"] == "camera=(), microphone=(), geolocation=()"


def test_api_responses_disable_caching_of_sensitive_data():
    with TestClient(app) as client:
        response = client.get("/api/v1/auth/me")
    assert response.headers["Cache-Control"] == "no-store"
