"""CMS connector — Complaint Management System

Maps an action payload onto CMS's request shape and posts it through the governed transport in
`_http.py` (Unity Catalog HTTP connection, with a service-principal direct POST as fallback).
"""
from __future__ import annotations

from typing import Any

from . import _http

SYSTEM = "CMS"


def _str(value: Any) -> str | None:
    """Stringify a date/datetime for JSON without importing a serialiser."""
    return None if value is None else str(value)


def case(payload: dict[str, Any]) -> dict[str, Any]:
    """Create or update a grievance case."""
    body = {
        "complaint_id": payload.get("complaint_id") or payload.get("subject"),
        "customer_id": payload.get("customer_id"),
        "action": payload.get("action") or "review",
        "note": payload.get("note") or payload.get("summary"),
    }
    return _http.post(SYSTEM, "/cms/case", {k: v for k, v in body.items() if v is not None})

def ombudsman(payload: dict[str, Any]) -> dict[str, Any]:
    """File a referral under the Integrated Ombudsman Scheme."""
    body = {
        "complaint_id": payload.get("complaint_id") or payload.get("subject"),
        "grounds": payload.get("grounds") or payload.get("rbi_category"),
        "nodal_officer": payload.get("approver_role") or "Principal Nodal Officer",
        "summary": payload.get("summary") or payload.get("note"),
    }
    return _http.post(SYSTEM, "/cms/ombudsman", {k: v for k, v in body.items() if v is not None})

# The executor dispatches by connector KEY, and each key maps to one function. `send` is the default
# for this system so a route can name "cms" without naming an operation.
send = case
