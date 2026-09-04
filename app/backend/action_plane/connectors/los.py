"""LOS connector — Loan origination and servicing

Maps an action payload onto LOS's request shape and posts it through the governed transport in
`_http.py` (Unity Catalog HTTP connection, with a service-principal direct POST as fallback).
"""
from __future__ import annotations

from typing import Any

from . import _http

SYSTEM = "LOS"


def _str(value: Any) -> str | None:
    """Stringify a date/datetime for JSON without importing a serialiser."""
    return None if value is None else str(value)


def settlement(payload: dict[str, Any]) -> dict[str, Any]:
    """Record a one-time settlement or waiver offer."""
    body = {
        "loan_account_id": payload.get("loan_account_id") or payload.get("subject"),
        "settlement_amount_inr": payload.get("amount_inr"),
        "waiver_inr": payload.get("waiver_inr"),
        "valid_until": _str(payload.get("valid_until")),
    }
    return _http.post(SYSTEM, "/los/settlement", {k: v for k, v in body.items() if v is not None})

def ptp(payload: dict[str, Any]) -> dict[str, Any]:
    """Record a promise-to-pay captured from the customer."""
    body = {
        "loan_account_id": payload.get("loan_account_id") or payload.get("subject"),
        "promise_amount_inr": payload.get("amount_inr") or payload.get("promise_to_pay_amount"),
        "promised_date": _str(payload.get("promised_date") or payload.get("due")),
        "captured_by": payload.get("captured_by"),
    }
    return _http.post(SYSTEM, "/los/ptp", {k: v for k, v in body.items() if v is not None})

def fee_reversal(payload: dict[str, Any]) -> dict[str, Any]:
    """Reverse a fee or charge as service redress."""
    body = {
        "loan_account_id": payload.get("loan_account_id") or payload.get("subject"),
        "customer_id": payload.get("customer_id"),
        "amount_inr": payload.get("amount_inr"),
        "fee_type": payload.get("fee_type") or "service charge",
    }
    return _http.post(SYSTEM, "/los/fee-reversal", {k: v for k, v in body.items() if v is not None})

# The executor dispatches by connector KEY, and each key maps to one function. `send` is the default
# for this system so a route can name "los" without naming an operation.
send = settlement
