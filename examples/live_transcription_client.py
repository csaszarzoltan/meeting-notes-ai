#!/usr/bin/env python3
"""Runnable example client for the MeetingNotesAI live-transcription WebSocket.

Demonstrates the full contract documented in docs/LIVE_TRANSCRIPTION.md:

    1. POST /api/v1/auth/login            -> {access_token}
    2. POST /api/v1/meetings/live/start   -> {meeting_id}          (Bearer)
    3. WS   /api/v1/meetings/live?token=..&meeting_id=..
    4. send binary WebM/Opus chunks       -> receive `partial` frames
    5. send {"type": "finalize"}          -> receive `finalized` frame

Run from the repository root with the project virtualenv (websockets is a
dependency of uvicorn[standard], already pinned in pyproject.toml):

    PYTHONPATH=src .venv/bin/python examples/live_transcription_client.py \
        --email you@example.com --password s3cret --chunks 4

Or against a demo server with deterministic fakes (no OPENAI_API_KEY):

    PYTHONPATH=src .venv/bin/python examples/live_demo_server.py &
    PYTHONPATH=src .venv/bin/python examples/live_transcription_client.py \
        --email demo@example.com --password demo1234 --chunks 4

Exit code 0 on success, 1 on any failure.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from urllib.parse import urlencode

import httpx
import websockets

BASE_URL = "http://127.0.0.1:8000"
WS_URL = "ws://127.0.0.1:8000"


async def login(email: str, password: str) -> str:
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=15) as client:
        resp = await client.post(
            "/api/v1/auth/login", json={"email": email, "password": password}
        )
        resp.raise_for_status()
        return resp.json()["access_token"]


async def start_meeting(token: str) -> str:
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=15) as client:
        resp = await client.post(
            "/api/v1/meetings/live/start", headers={"Authorization": f"Bearer {token}"}
        )
        resp.raise_for_status()
        return resp.json()["meeting_id"]


def make_webm_chunk(sequence: int, filler: bytes = b"opustream") -> bytes:
    """A minimal WebM/Opus-looking frame (magic bytes + payload)."""
    return b"\x1a\x45\xdf\xa3" + bytes([sequence % 256]) + filler


async def stream(meeting_id: str, token: str, chunks: int) -> None:
    query = urlencode({"token": token, "meeting_id": meeting_id})
    uri = f"{WS_URL}/api/v1/meetings/live?{query}"
    async with websockets.connect(uri, max_size=None) as ws:
        # 4. Stream binary chunks; collect partials.
        for i in range(chunks):
            await ws.send(make_webm_chunk(i))
            await asyncio.sleep(0.05)
        # 5. Finalize and read until the finalized frame.
        await ws.send(json.dumps({"type": "finalize"}))
        partial_count = 0
        while True:
            frame = json.loads(await ws.recv())
            if frame.get("type") == "partial":
                partial_count += 1
                print(f"  partial #{frame['sequence']}: {frame['text'][:80]!r}")
            elif frame.get("type") == "finalized":
                print(f"  finalized: {frame['transcript'][:120]!r}")
                print(f"  summary:   {frame['summary'][:120]!r}")
                for item in frame.get("action_items", []):
                    who = f"{item.get('assignee')}: " if item.get("assignee") else ""
                    print(f"  action:    {who}{item['description']}")
                return
            else:
                print(f"  unexpected frame: {frame}")


async def main() -> int:
    parser = argparse.ArgumentParser(description="Live transcription WS example client")
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--chunks", type=int, default=4, help="audio chunks to stream")
    args = parser.parse_args()

    print(f"1. Logging in as {args.email} …")
    token = await login(args.email, args.password)
    print("   ok")
    print("2. Starting a draft live meeting …")
    meeting_id = await start_meeting(token)
    print(f"   ok — meeting_id={meeting_id}")
    print(f"3. Opening WebSocket, streaming {args.chunks} chunks …")
    await stream(meeting_id, token, chunks=args.chunks)
    print("   done")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except Exception as exc:  # noqa: BLE001 — example client reports any failure
        print(f"❌ client failed: {exc}")
        sys.exit(1)
