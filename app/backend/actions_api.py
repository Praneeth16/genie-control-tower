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
import cases_api
import config
import databricks_client as dbx
from action_plane import (
    ActionNotFound,
    ActionPlane,
    IllegalTransition,
    authorise_approver,
    evaluate,
    holds_required_role,
    execute,
)


class ActReq(BaseModel):
    action_type: str
    subject: str
    payload: dict[str, Any]
    # Ignored when the subject resolves to a governed record: see _subject_scope.
    region: Optional[str] = None
    case_id: Optional[int] = None
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


def _subject_scope(subject: str) -> tuple[Optional[str], Optional[str]]:
    """The region and branch of the record an action is about, read by the SERVER as the guardrail
    identity. The region check used to trust the region in the request body, so a proposal could pass the
    regional sanction by simply claiming a different region."""
    table = {"LN": "loan_accounts WHERE loan_account_id", "CM": "complaints WHERE complaint_id",
             "RM": "relationship_managers WHERE rm_id"}.get(subject[:2].upper())
    if not table:
        return None, None
    rows = dbx.run_sql(f"SELECT region, branch_id FROM {config.FQ}.{table} = :s",
                       parameters={"s": (subject, "STRING")})["rows"]
    return (rows[0]["region"], rows[0]["branch_id"]) if rows else (None, None)


_TARGET_FIELD = {"LN": "loan_account_id", "CM": "complaint_id", "RM": "rm_id"}


def _canonical_payload(subject: str, payload: dict[str, Any]) -> dict[str, Any]:
    """One target per action. The region was resolved from `subject` while the conduct checks and the
    connectors read the payload's own identifier, so an action could be sanctioned for one account and
    carried out on another. A payload naming a different record is refused; a missing one is filled in."""
    field = _TARGET_FIELD.get(subject[:2].upper())
    if not field:
        return payload
    named = payload.get(field)
    if named and str(named).strip().upper() != subject.strip().upper():
        raise HTTPException(400, f"payload {field} {named} does not match the action subject {subject}")
    return {**payload, field: subject}


def _require_visible(request: Request, region: Optional[str]) -> None:
    """The caller must be entitled, in Unity Catalog, to the region of the record an action is about.
    Proposals resolve the record as the guardrail identity, which sees every region, so without this a
    regional head could raise or read actions on another region's accounts."""
    if region and region not in cases_api.visible_regions(request):
        raise HTTPException(404, "action not found")


def build_actions_router(agent_name: str) -> APIRouter:
    """Return an APIRouter exposing the Act→Approve→Execute loop for `agent_name`."""
    router = APIRouter(prefix="/api")
    ap = ActionPlane()

    @router.post("/act")
    def act(req: ActReq, request: Request):
        """Stage an action through the Action Plane + return its guardrail verdict."""
        try:
            # The proposer is the PERSON who asked for the action, whichever agent drafted it. It used to
            # be the agent's name, which made separation of duties decorative: the approver's email never
            # equals an agent name, so whoever asked could approve their own request. Now a person's
            # request needs a different person to approve it.
            region, branch = _subject_scope(req.subject)
            _require_visible(request, region)
            action = ap.propose(
                agent=agent_name,
                action_type=req.action_type,
                subject=req.subject,
                payload=_canonical_payload(req.subject, req.payload),
                region=region or req.region,
                requested_by=_end_user(request, agent_name),
                level=req.level,
                scheduled_at=req.scheduled_at,
                branch_id=branch or req.branch_id,
                session_uuid=req.session_uuid,
                trace_id=req.trace_id,
                case_id=req.case_id,
            )
            # Evaluate immediately and RECORD the verdict, so the reviewer sees the controls before
            # deciding and the trail shows what was known at proposal time.
            verdict = evaluate(action)
            ap._event(action["id"], "guardrail", "proposer",
                      {"passed": verdict["passed"], "breaches": verdict["breaches"],
                       "verified_count": verdict.get("verified_count")})
            return {"action": ap.get(action["id"]), "guardrail": verdict,
                    "approver_role": (verdict.get("policy") or {}).get("approver_role")}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(500, f"propose failed: {e}")

    @router.get("/actions")
    def actions(request: Request, status: Optional[str] = None):
        """List this agent's actions in the caller's regions (newest first), optionally by status."""
        try:
            regions = cases_api.visible_regions(request)
            return {"actions": [a for a in ap.list(status=status, agent=agent_name)
                                if not a.get("region") or a["region"] in regions]}
        except Exception as e:
            raise HTTPException(500, f"list actions failed: {e}")

    @router.get("/actions/{action_id}")
    def get_action(action_id: int, request: Request):
        """Return one action with its full event lineage + guardrail verdict."""
        try:
            action = ap.get(action_id)
            _require_visible(request, action.get("region"))
            return {"action": action, "guardrail": evaluate(action)}
        except HTTPException:
            raise
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
            _require_visible(request, action.get("region"))
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
            _require_visible(request, action.get("region"))
            # The proposer may withdraw (reject) their own action; what matters is the role.
            allowed, reason = holds_required_role(action, approver)
            if not allowed:
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
    def execute_action(action_id: int, request: Request):
        """Execute an approved action through its connector(s); return final action.

        Needs the same role authority as approval. Anyone could execute an approved action before, so an
        approval by the right person could be acted on by the wrong one."""
        try:
            actor = _end_user(request, agent_name)
            action = ap.get(action_id)
            _require_visible(request, action.get("region"))
            allowed, reason = holds_required_role(action, actor)
            if not allowed:
                ap._event(action_id, "execution_refused", actor, {"reason": reason})
                raise HTTPException(403, reason)
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
