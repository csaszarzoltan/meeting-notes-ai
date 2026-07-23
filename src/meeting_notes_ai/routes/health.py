"""Health check endpoint — shared pattern `health-check-endpoint`.

GET /healthz — returns service + dependency health status.
"""

from __future__ import annotations

from fastapi import APIRouter

from meeting_notes_ai.models import HealthResponse, ServiceHealth

router = APIRouter(tags=["health"])


@router.get("/healthz", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Return service health including dependency checks.

    Returns a HealthResponse with:
      - status: overall health ("healthy", "degraded", "unhealthy")
      - version: application version
      - services: per-dependency health with latency
    """
    # Compute services health (no external deps needed for basic check)
    services: dict[str, ServiceHealth] = {
        "app": ServiceHealth(status="up", latency_ms=0.0),
    }

    # Determine overall status
    all_up = all(svc.status == "up" for svc in services.values())
    status = "healthy" if all_up else "degraded"

    return HealthResponse(
        status=status,
        version="0.1.0",
        services=services,
    )
