"""CORR connector — Customer correspondence and dispatch

Maps an action payload onto CORR's request shape and posts it through the governed transport in
`_http.py` (Unity Catalog HTTP connection, with a service-principal direct POST as fallback).
"""
from __future__ import annotations

from typing import Any

from . import _http

SYSTEM = "CORR"


def _str(value: Any) -> str | None:
    """Stringify a date/datetime for JSON without importing a serialiser."""
    return None if value is None else str(value)


def letter(payload: dict[str, Any]) -> dict[str, Any]:
    """Queue a customer letter for dispatch."""
    body = {
        "customer_id": payload.get("customer_id"),
        "complaint_id": payload.get("complaint_id") or payload.get("subject"),
        "template": payload.get("template") or "grievance_resolution",
        "channel": payload.get("channel") or "post",
        "document_path": payload.get("document_path"),
        "signed_by": payload.get("signed_by") or payload.get("approved_by"),
    }
    return _http.post(SYSTEM, "/correspondence/letter", {k: v for k, v in body.items() if v is not None})

# The executor dispatches by connector KEY, and each key maps to one function. `send` is the default
# for this system so a route can name "correspondence" without naming an operation.
send = letter
