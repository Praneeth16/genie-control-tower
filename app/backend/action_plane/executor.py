"""Executor — the step where an approved action actually reaches a bank system.

`execute(action_id)` takes an APPROVED action, re-runs every guardrail as a final gate, dispatches it
to the connector(s) for its action type, and drives the state machine
`approved -> executing -> executed | failed | escalated`, appending an `action_events` row at each
transition so the lineage is reconstructable from the events table alone.

Four gates stand between approval and a side effect, in this order:

  1. STATUS — only an approved action may execute.
  2. KILL SWITCH — re-read here, not just at proposal time. An action approved at 11:00 and executed
     at 15:00 must obey the switch as it is at 15:00. This is the whole point of a kill switch: it has
     to stop things that are already in flight.
  3. GUARDRAILS — re-evaluated from scratch. Conditions change between approval and execution: a
     borrower can raise a complaint, an agent's certification can lapse, and an approval given at
     16:00 for a 20:00 visit must still be refused at 20:00. Approval is not a permanent licence.
  4. CONNECTOR ROUTE — the action type must have a route; an unroutable action never half-executes.

On a mid-route connector failure the already-fired connectors are recorded with their external refs
and the action is marked failed with `needs_reconciliation`, because those side effects are real. A
letter that has been dispatched cannot be un-dispatched by rolling back a database row.
"""
from __future__ import annotations

import json
from typing import Any

from . import connectors, guardrails
from .model import APPROVED, ActionPlane

# action_type -> ordered connector keys. A sequence runs in order; the FIRST connector's ref_id
# becomes the action's external_ref, because that is the record an operations team would search for.
#
# Note which actions notify as well as act: a field visit tells the collections-ops channel, and an
# incentive hold tells the RM's management chain. An action a human cannot see happening is not
# governed, however well it is logged.
ROUTING: dict[str, list[str]] = {
    # Collections & recovery
    "schedule_field_visit":     ["fos.visit", "notify.message"],
    "assign_recovery_agency":   ["fos.allocation", "notify.message"],
    "record_ptp":               ["los.ptp"],
    "offer_settlement":         ["los.settlement", "corr.letter"],
    # Service & grievance
    "escalate_to_ombudsman":    ["cms.ombudsman", "notify.message"],
    "issue_provisional_credit": ["disp.provisional_credit", "cms.case"],
    "waive_fee":                ["los.fee_reversal", "cms.case"],
    "dispatch_customer_letter": ["corr.letter", "cms.case"],
    # RM performance
    "hold_incentive_payout":    ["hrms.incentive_hold", "notify.message"],
    "open_coaching_case":       ["hrms.coaching_case"],
}


class UnroutableAction(Exception):
    """Raised when an action_type has no connector route."""


def _payload(action: dict[str, Any]) -> dict[str, Any]:
    raw = action.get("payload")
    if raw is None:
        return {}
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except (ValueError, TypeError):
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return dict(raw) if isinstance(raw, dict) else {}


def _connector_payload(action: dict[str, Any]) -> dict[str, Any]:
    """The payload the connectors see, enriched with the fields they need from the action ROW rather
    than from the model's payload — the subject, the region, the scheduled time, and crucially the
    human who approved it, so the downstream system records a named officer and not 'the agent'."""
    payload = _payload(action)
    payload.setdefault("subject", action.get("subject"))
    payload.setdefault("region", action.get("region"))
    if action.get("scheduled_at") and not payload.get("scheduled_at"):
        payload["scheduled_at"] = str(action["scheduled_at"])
    if action.get("approved_by"):
        payload.setdefault("approved_by", action["approved_by"])
        payload.setdefault("signed_by", action["approved_by"])
    return payload


def execute(action_id: int, ap: ActionPlane | None = None, w=None) -> dict[str, Any]:
    """Execute an approved action through its connector(s). Returns the final action (with events).

    On a guardrail breach the action is escalated and returned; no external call is made.
    """
    ap = ap or ActionPlane()
    action = ap.get(action_id)

    # Gate 1 — status.
    if action["status"] != APPROVED:
        return {"error": "not_approved",
                "message": f"action {action_id} is '{action['status']}', not 'approved'",
                "action": action}

    # Gate 2 — the kill switch, as it is NOW.
    enabled, why = guardrails.actions_enabled()
    if not enabled:
        ap.escalate(action_id, reason=why, actor="kill-switch")
        return ap.get(action_id)

    action_type = action["action_type"]
    route = ROUTING.get(action_type)
    if not route:
        raise UnroutableAction(f"no connector route for action_type '{action_type}'")

    # Gate 3 — guardrails, re-evaluated at execution time.
    verdict = guardrails.evaluate(action, w=w)
    ap._event(action_id, "guardrail", "executor",
              {"passed": verdict["passed"], "breaches": verdict["breaches"],
               "verified_count": verdict.get("verified_count"),
               "payload_count": verdict.get("payload_count")})
    if not verdict["passed"]:
        reason = "; ".join(verdict["breaches"]) or "guardrail breach"
        ap.escalate(action_id, reason=reason, actor="guardrails")
        return ap.get(action_id)

    payload = _connector_payload(action)
    ap.mark_executing(action_id, actor="executor")

    # Run the route connector by connector so a mid-sequence failure cannot erase the record of what
    # already fired. Those side effects are real and mostly irreversible.
    results: list[dict[str, Any]] = []
    for key in route:
        send = connectors.SYSTEMS.get(key)
        if send is None:
            ap.mark_failed(action_id, result={"error": f"unknown connector '{key}'",
                                              "completed_connectors": results},
                           actor="executor")
            return ap.get(action_id)
        try:
            result = send(payload)
        except Exception as exc:
            completed_refs = [r["ref_id"] for r in results]
            partial = bool(results)
            ap._event(action_id, "partial_failure" if partial else "connector_failed",
                      f"connector:{key}",
                      {"failed_connector": key, "error": str(exc)[:400],
                       "completed_refs": completed_refs})
            ap.mark_failed(
                action_id,
                result={"error": str(exc)[:400], "failed_connector": key,
                        "completed_connectors": results, "completed_refs": completed_refs,
                        # An operator has to reconcile by hand: the connectors before this one
                        # already had real effects downstream.
                        "needs_reconciliation": partial},
                actor="executor")
            return ap.get(action_id)
        results.append(result)
        ap._event(action_id, "connector", f"connector:{key}",
                  {"system": result["system"], "external_ref": result["ref_id"],
                   "via": result.get("via"), "raw": result["raw"]})

    ap.mark_executed(action_id, result={"connectors": results, "route": route},
                     external_ref=results[0]["ref_id"] if results else None, actor="executor")
    return ap.get(action_id)
