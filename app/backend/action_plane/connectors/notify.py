"""NOTIFY connector — Operations notification fan-out

Maps an action payload onto NOTIFY's request shape and posts it through the governed transport in
`_http.py` (Unity Catalog HTTP connection, with a service-principal direct POST as fallback).
"""
from __future__ import annotations

from typing import Any

from . import _http

SYSTEM = "NOTIFY"


def _str(value: Any) -> str | None:
    """Stringify a date/datetime for JSON without importing a serialiser."""
    return None if value is None else str(value)


def message(payload: dict[str, Any]) -> dict[str, Any]:
    """Notify an operations channel."""
    body = {
        "channel": payload.get("channel") or "collections-ops",
        "subject": payload.get("subject"),
        "message": payload.get("message") or payload.get("summary") or payload.get("note"),
    }
    return _http.post(SYSTEM, "/notify/message", {k: v for k, v in body.items() if v is not None})

# The executor dispatches by connector KEY, and each key maps to one function. `send` is the default
# for this system so a route can name "notify" without naming an operation.
send = message
