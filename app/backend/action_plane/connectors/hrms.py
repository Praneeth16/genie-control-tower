"""HRMS connector — Human Resources Management System

Maps an action payload onto HRMS's request shape and posts it through the governed transport in
`_http.py` (Unity Catalog HTTP connection, with a service-principal direct POST as fallback).
"""
from __future__ import annotations

from typing import Any

from . import _http

SYSTEM = "HRMS"


def _str(value: Any) -> str | None:
    """Stringify a date/datetime for JSON without importing a serialiser."""
    return None if value is None else str(value)


def incentive_hold(payload: dict[str, Any]) -> dict[str, Any]:
    """Place a hold on an incentive payout pending Compensation review."""
    body = {
        "rm_id": payload.get("rm_id") or payload.get("subject"),
        "period": payload.get("period") or payload.get("achievement_month"),
        "amount_inr": payload.get("amount_inr") or payload.get("incentive_earned"),
        "reason": payload.get("reason") or "product-mix quality gate failed; clawback flagged",
    }
    return _http.post(SYSTEM, "/hrms/incentive-hold", {k: v for k, v in body.items() if v is not None})

def coaching_case(payload: dict[str, Any]) -> dict[str, Any]:
    """Open a coaching or product-mix review case for a relationship manager."""
    body = {
        "rm_id": payload.get("rm_id") or payload.get("subject"),
        "topic": payload.get("topic") or "product mix and cross-sell quality",
        "note": payload.get("note") or payload.get("summary"),
    }
    return _http.post(SYSTEM, "/hrms/coaching-case", {k: v for k, v in body.items() if v is not None})

# The executor dispatches by connector KEY, and each key maps to one function. `send` is the default
# for this system so a route can name "hrms" without naming an operation.
send = incentive_hold
