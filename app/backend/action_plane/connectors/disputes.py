"""DISP connector — Card and UPI dispute engine

Maps an action payload onto DISP's request shape and posts it through the governed transport in
`_http.py` (Unity Catalog HTTP connection, with a service-principal direct POST as fallback).
"""
from __future__ import annotations

from typing import Any

from . import _http

SYSTEM = "DISP"


def _str(value: Any) -> str | None:
    """Stringify a date/datetime for JSON without importing a serialiser."""
    return None if value is None else str(value)


def provisional_credit(payload: dict[str, Any]) -> dict[str, Any]:
    """Post provisional credit for a disputed transaction."""
    body = {
        "dispute_id": payload.get("dispute_id") or payload.get("subject"),
        "customer_id": payload.get("customer_id"),
        "amount_inr": payload.get("amount_inr"),
        "reason": payload.get("reason") or payload.get("failure_reason"),
    }
    return _http.post(SYSTEM, "/disputes/provisional-credit", {k: v for k, v in body.items() if v is not None})

# The executor dispatches by connector KEY, and each key maps to one function. `send` is the default
# for this system so a route can name "disputes" without naming an operation.
send = provisional_credit
