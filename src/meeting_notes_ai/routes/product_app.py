"""Serve the unified, accessible React product workspace."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

router = APIRouter(tags=["product-ui"])
_DIST = Path(__file__).resolve().parents[3] / "frontend" / "dist"
_INDEX = _DIST / "index.html"
_ASSETS = _DIST / "assets"
_CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; media-src 'self' blob:; connect-src 'self' ws: wss:; "
    "object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
)
_PERMISSIONS = "microphone=(self), camera=(), geolocation=()"
_FALLBACK = """<!doctype html><html lang="en"><head><meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>MeetingNotesAI workspace</title></head><body><div id="root"></div>
<p>Build the workspace with <code>cd frontend &amp;&amp; npm ci &amp;&amp;
 npm run build</code>.</p>
</body></html>"""


def _index_html() -> str:
    """Return the built application shell or a developer-friendly fallback."""
    return _INDEX.read_text(encoding="utf-8") if _INDEX.exists() else _FALLBACK


@router.get("/app", response_class=HTMLResponse, include_in_schema=False)
async def product_app() -> HTMLResponse:
    """Serve the single product workspace entry point."""
    return HTMLResponse(
        _index_html(),
        headers={"Content-Security-Policy": _CSP, "Permissions-Policy": _PERMISSIONS},
    )


@router.get("/app/live", include_in_schema=False)
async def legacy_live_app() -> RedirectResponse:
    """Preserve old bookmarks while consolidating the UI into one workspace."""
    return RedirectResponse(url="/app", status_code=307)


@router.get("/app/assets/{path:path}", include_in_schema=False)
async def app_assets(path: str) -> FileResponse:
    """Serve hashed frontend assets with traversal protection."""
    base = _ASSETS.resolve()
    candidate = (base / path).resolve()
    if not str(candidate).startswith(str(base)) or not candidate.is_file():
        raise HTTPException(status_code=404)
    return FileResponse(candidate)


@router.get("/app/live/assets/{path:path}", include_in_schema=False)
async def legacy_live_assets(path: str) -> FileResponse:
    """Serve compatibility assets for cached v0.8 pages."""
    return await app_assets(path)
