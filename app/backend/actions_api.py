"""Shared FastAPI routes that wire an app to the Action Plane.

Reused verbatim by every agent app (supervisor / finance-copilot / quote-agent):
each app mounts this router under `/api` so it can drive the full
Act → Approve → Execute → Confirm loop without leaving the app, all through the
one governed Action Plane (`action_plane`).

    from actions_api import build_actions_router
    app.include_router(build_actions_router("supervisor-agent"))

`agent_name` is the app's stable identity stamped on every action it proposes
(also used to scope `GET /api/actions` to this app's own queue). Keep it thin —
all real logic lives in `action_plane`.
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

import identity
from action_plane import (
    ActionNotFound,
    ActionPlane,
    IllegalTransition,
    authorise_approver,
    evaluate,
    execute,
)


class ActReq(BaseModel):
    action_type: str
    subject: str
    payload: dict[str, Any]
    region: Optional[str] = None
    level: int = 2
    # The time the action would take effect. First-class because the RBI conduct-hours control keys
    # on it, and editable in the UI so a reviewer can see the control refuse an out-of-hours slot.
    scheduled_at: Optional[str] = None
    branch_id: Optional[str] = None
    # Provenance: which traced conversation turn produced this proposal.
    session_uuid: Optional[str] = None
    trace_id: Optional[str] = None


class RejectReq(BaseModel):
    reason: str


def _end_user(request: Request, agent_name: str) -> str:
    """The authenticated END USER — headers only. See identity.py for why the body is never trusted."""
    return identity.user_email(request, fallback_tag=agent_name)


def build_actions_router(agent_name: str) -> APIRouter:
    """Return an APIRouter exposing the Act→Approve→Execute loop for `agent_name`."""
    router = APIRouter(prefix="/api")
    ap = ActionPlane()

    @router.post("/act")
    def act(req: ActReq, request: Request):
        """Stage an action through the Action Plane + return its guardrail verdict."""
        try:
            # The AGENT proposes the action (it advised it); the human then APPROVES it. Attributing
            # the proposal to the agent (not the signed-in user) is the correct separation of duties:
            # proposer (agent) != approver (human), so a single signed-in user can approve in the UI
            # without a second identity or an admin panel.
            action = ap.propose(
                agent=agent_name,
                action_type=req.action_type,
                subject=req.subject,
                payload=req.payload,
                region=req.region,
                requested_by=agent_name,
                level=req.level,
                scheduled_at=req.scheduled_at,
                branch_id=req.branch_id,
                session_uuid=req.session_uuid,
                trace_id=req.trace_id,
            )
            # Evaluate immediately and RECORD the verdict, so the reviewer sees the controls before
            # deciding and the trail shows what was known at proposal time.
            verdict = evaluate(action)
            ap._event(action["id"], "guardrail", "proposer",
                      {"passed": verdict["passed"], "breaches": verdict["breaches"],
                       "verified_count": verdict.get("verified_count")})
            return {"action": ap.get(action["id"]), "guardrail": verdict,
                    "approver_role": (verdict.get("policy") or {}).get("approver_role")}
        except Exception as e:
            raise HTTPException(500, f"propose failed: {e}")

    @router.get("/actions")
    def actions(status: Optional[str] = None):
        """List this agent's actions (newest first), optionally filtered by status."""
        try:
            return {"actions": ap.list(status=status, agent=agent_name)}
        except Exception as e:
            raise HTTPException(500, f"list actions failed: {e}")

    @router.get("/actions/{action_id}")
    def get_action(action_id: int):
        """Return one action with its full event lineage + guardrail verdict."""
        try:
            action = ap.get(action_id)
            return {"action": action, "guardrail": evaluate(action)}
        except ActionNotFound as e:
            raise HTTPException(404, str(e))
        except Exception as e:
            raise HTTPException(500, f"get action failed: {e}")

    @router.post("/actions/{action_id}/approve")
    def approve(action_id: int, request: Request):
        """proposed|escalated → approved, then return the action + lineage.

        The approver is the authenticated user (headers), never the request body.
        Separation of duties: the proposer of an action may not approve it."""
        try:
            approver = _end_user(request, agent_name)
            action = ap.get(action_id)
            # BOTH separation of duties AND the named approver role. See authorise_approver.
            allowed, reason = authorise_approver(action, approver)
            if not allowed:
                # Record the refused attempt. A rejected approval is exactly the kind of event an
                # auditor wants to see, and silently 403-ing leaves no trace that it was tried.
                ap._event(action_id, "approval_refused", approver, {"reason": reason})
                raise HTTPException(403, reason)
            ap.approve(action_id, approver=approver)
            ap._event(action_id, "authorised", approver, {"basis": reason})
            return {"action": ap.get(action_id)}
        except HTTPException:
            raise
        except ActionNotFound as e:
            raise HTTPException(404, str(e))
        except IllegalTransition as e:
            raise HTTPException(409, str(e))
        except Exception as e:
            raise HTTPException(500, f"approve failed: {e}")

    @router.post("/actions/{action_id}/reject")
    def reject(action_id: int, req: RejectReq, request: Request):
        """proposed|approved|escalated -> rejected (terminal), with the reason recorded.

        Rejection needs the same role authority as approval: someone who may not approve an action
        must not be able to dispose of it either, or the queue could be quietly emptied by anyone."""
        try:
            approver = _end_user(request, agent_name)
            action = ap.get(action_id)
            allowed, reason = authorise_approver(action, approver)
            if not allowed and "separation of duties" not in reason:
                # The proposer may not APPROVE its own action, but a human rejecting it is fine — the
                # role requirement is what matters here.
                ap._event(action_id, "rejection_refused", approver, {"reason": reason})
                raise HTTPException(403, reason)
            ap.reject(action_id, approver=approver, reason=req.reason)
            return {"action": ap.get(action_id)}
        except HTTPException:
            raise
        except ActionNotFound as e:
            raise HTTPException(404, str(e))
        except IllegalTransition as e:
            raise HTTPException(409, str(e))
        except Exception as e:
            raise HTTPException(500, f"reject failed: {e}")

    @router.post("/actions/{action_id}/execute")
    def execute_action(action_id: int):
        """Execute an approved action through its connector(s); return final action."""
        try:
            result = execute(action_id, ap=ap)
            if isinstance(result, dict) and result.get("error") == "not_approved":
                raise HTTPException(409, result["message"])
            return {"action": result}
        except HTTPException:
            raise
        except ActionNotFound as e:
            raise HTTPException(404, str(e))
        except IllegalTransition as e:
            # Lost the compare-and-set race: a concurrent execute already claimed this action. That is
            # the guard working — exactly one dispatch happens — so report it as a conflict, not as a
            # server error, and do not retry.
            raise HTTPException(409, f"another execution already claimed this action: {e}")
        except Exception as e:
            raise HTTPException(500, f"execute failed: {e}")

    return router
