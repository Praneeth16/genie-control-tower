"""FOS connector — Field Operations System

Maps an action payload onto FOS's request shape and posts it through the governed transport in
`_http.py` (Unity Catalog HTTP connection, with a service-principal direct POST as fallback).
"""
from __future__ import annotations

from typing import Any

from . import _http

SYSTEM = "FOS"


def _str(value: Any) -> str | None:
    """Stringify a date/datetime for JSON without importing a serialiser."""
    return None if value is None else str(value)


def visit(payload: dict[str, Any]) -> dict[str, Any]:
    """Schedule a recovery agent visit to a borrower's address."""
    body = {
        "loan_account_id": payload.get("loan_account_id") or payload.get("subject"),
        "agent_id": payload.get("agent_id"),
        "scheduled_at": _str(payload.get("scheduled_at")),
        "purpose": payload.get("purpose") or "collection follow-up",
        "dpd_days": payload.get("dpd_days"),
    }
    return _http.post(SYSTEM, "/fos/visit", {k: v for k, v in body.items() if v is not None})

def allocation(payload: dict[str, Any]) -> dict[str, Any]:
    """Allocate a tranche of delinquent accounts to a recovery agency."""
    body = {
        "agency_name": payload.get("agency_name"),
        "agent_id": payload.get("agent_id"),
        "account_count": payload.get("account_count"),
        "portfolio_value_inr": payload.get("amount_inr") or payload.get("portfolio_value_inr"),
        "region": payload.get("region"),
    }
    return _http.post(SYSTEM, "/fos/allocation", {k: v for k, v in body.items() if v is not None})

# The executor dispatches by connector KEY, and each key maps to one function. `send` is the default
# for this system so a route can name "fos" without naming an operation.
send = visit
