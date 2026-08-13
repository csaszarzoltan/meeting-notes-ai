"""Tamper-evident canonical audit chain and signed ZIP exports."""

import csv
import hashlib
import hmac
import io
import json
import zipfile


def canonical(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def append_event(
    events: list[dict], team_id: str, actor_id: str, event_type: str, payload: dict
) -> dict:
    previous = events[-1]["event_hash"] if events else "0" * 64
    payload_hash = hashlib.sha256(canonical(payload)).hexdigest()
    body = {
        "team_id": team_id,
        "actor_id": actor_id,
        "event_type": event_type,
        "payload_sha256": payload_hash,
        "previous_hash": previous,
    }
    event = {**body, "event_hash": hashlib.sha256(canonical(body)).hexdigest()}
    events.append(event)
    return event


def validate_chain(events: list[dict]) -> dict:
    previous = "0" * 64
    for event in events:
        body = {
            k: event[k]
            for k in ("team_id", "actor_id", "event_type", "payload_sha256", "previous_hash")
        }
        expected = hashlib.sha256(canonical(body)).hexdigest()
        if event["previous_hash"] != previous or not hmac.compare_digest(
            event["event_hash"], expected
        ):
            return {
                "valid": False,
                "count": len(events),
                "first_invalid_event_id": event.get("id") or event["event_hash"],
            }
        previous = event["event_hash"]
    return {
        "valid": True,
        "count": len(events),
        "terminal_hash": previous,
        "first_invalid_event_id": None,
    }


def export_zip(events: list[dict], key: bytes, include_csv: bool = False) -> bytes:
    if len(key) < 32:
        raise ValueError("AUDIT_EXPORT_SIGNING_KEY must be at least 32 bytes")
    valid = validate_chain(events)
    if not valid["valid"]:
        raise ValueError("Audit chain is invalid")
    jsonl = b"".join(canonical(e) + b"\n" for e in events)
    manifest = {
        "count": len(events),
        "terminal_hash": valid["terminal_hash"],
        "events_sha256": hashlib.sha256(jsonl).hexdigest(),
    }
    manifest["signature"] = hmac.new(key, canonical(manifest), hashlib.sha256).hexdigest()
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("events.jsonl", jsonl)
        z.writestr("manifest.json", json.dumps(manifest, indent=2))
        if include_csv:
            text = io.StringIO()
            w = csv.DictWriter(text, fieldnames=list(events[0]) if events else ["event_hash"])
            w.writeheader()
            w.writerows(events)
            z.writestr("events.csv", text.getvalue())
    return out.getvalue()
