"""Action Plane — the canonical action record + state machine over Lakebase.

This is the *one governed plane* every agent in this application acts through. An agent
`propose()`s an action (status `proposed`); a human (or, at L4, policy) drives it
through `approved → executing → executed`, or it `rejected`/`escalated`/`failed`.
Every transition appends an `action_events` row, so the full lineage of who did
what, when, and why is always reconstructable from `action_events`.

State machine (enforced — illegal transitions raise):

    proposed ──approve──▶ approved ──mark_executing──▶ executing ──mark_executed──▶ executed
       │                     │                            │
       ├──reject──▶ rejected │                            └──mark_failed──▶ failed
       │                     │
       └──escalate─┐         └──escalate──▶ escalated
                   ▼
               escalated  (also reachable from approved/executing on a guardrail breach)

`escalated` is reachable from any non-terminal state: a guardrail breach found
at any point pulls the action back to a human gate rather than letting it run.
"""
from __future__ import annotations

import json
from typing import Any

import lakebase

# ----------------------------------------------------------------------------
# State machine
# ----------------------------------------------------------------------------

PROPOSED = "proposed"
APPROVED = "approved"
EXECUTING = "executing"
EXECUTED = "executed"
REJECTED = "rejected"
FAILED = "failed"
ESCALATED = "escalated"

TERMINAL = {EXECUTED, REJECTED, FAILED}

# Legal status transitions. `escalated` is added to every non-terminal source
# below because a guardrail breach can pull any live action to a human gate.
_TRANSITIONS: dict[str, set[str]] = {
    PROPOSED: {APPROVED, REJECTED, ESCALATED},
    APPROVED: {EXECUTING, REJECTED, ESCALATED},
    EXECUTING: {EXECUTED, FAILED, ESCALATED},
    ESCALATED: {APPROVED, REJECTED},
    EXECUTED: set(),
    REJECTED: set(),
    FAILED: set(),
}


class IllegalTransition(Exception):
    """Raised when a requested status transition is not allowed by the machine."""


class ActionNotFound(Exception):
    """Raised when an action_id does not exist."""


def _as_jsonb(value: Any) -> str | None:
    """psycopg adapts a Python str into a jsonb column when the column is jsonb;
    we json.dumps dicts/lists here so callers can pass native objects."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return json.dumps(value)


class ActionPlane:
    """Thin, stateless facade over the Lakebase `actions` + `action_events` tables.

    Methods open their own short-lived connection via the shared `lakebase`
    module, so an instance is cheap and safe to share. All writes record an
    `action_events` row in the *same* call as the `actions` mutation.
    """

    # -- read -----------------------------------------------------------------

    def get(self, action_id: int) -> dict[str, Any]:
        """Return the action row plus its ordered `events` list. Raises if absent."""
        rows = lakebase.query("SELECT * FROM actions WHERE id = %s", (action_id,))
        if not rows:
            raise ActionNotFound(f"action {action_id} not found")
        action = rows[0]
        action["events"] = lakebase.query(
            "SELECT id, action_id, ts, event, actor, detail "
            "FROM action_events WHERE action_id = %s ORDER BY ts, id",
            (action_id,),
        )
        return action

    def list(
        self,
        status: str | None = None,
        agent: str | None = None,
        level: int | None = None,
    ) -> list[dict[str, Any]]:
        """List actions, newest first, optionally filtered by status/agent/level."""
        where: list[str] = []
        params: list[Any] = []
        if status is not None:
            where.append("status = %s")
            params.append(status)
        if agent is not None:
            where.append("agent = %s")
            params.append(agent)
        if level is not None:
            where.append("level = %s")
            params.append(level)
        clause = (" WHERE " + " AND ".join(where)) if where else ""
        return lakebase.query(
            f"SELECT * FROM actions{clause} ORDER BY created_at DESC, id DESC",
            tuple(params) if params else None,
        )

    def ladder_counts(self) -> list[dict[str, Any]]:
        """Counts grouped by maturity level + status — feeds the ladder viz."""
        return lakebase.query(
            "SELECT level, status, COUNT(*) AS count "
            "FROM actions GROUP BY level, status ORDER BY level, status"
        )

    # -- internal -------------------------------------------------------------

    def _event(self, action_id: int, event: str, actor: str, detail: Any = None) -> None:
        lakebase.execute(
            "INSERT INTO action_events (action_id, event, actor, detail) "
            "VALUES (%s, %s, %s, %s)",
            (action_id, event, actor, _as_jsonb(detail)),
        )

    def _require(self, action_id: int) -> dict[str, Any]:
        rows = lakebase.query("SELECT * FROM actions WHERE id = %s", (action_id,))
        if not rows:
            raise ActionNotFound(f"action {action_id} not found")
        return rows[0]

    def _check_transition(self, current: str, target: str) -> None:
        if target not in _TRANSITIONS.get(current, set()):
            raise IllegalTransition(
                f"cannot move action from '{current}' to '{target}'"
            )

    def _cas_or_raise(self, row: Any, action_id: int, target: str) -> None:
        """Compare-and-set guard: each transition UPDATE carries `AND status = <read
        status>`, so a concurrent writer that already moved the row makes the UPDATE
        affect 0 rows (row is None). That means we lost the race on a now-stale state
        — raise rather than silently no-op, so terminal/illegal mutations can't slip
        through between the read and the write."""
        if row is None:
            raise IllegalTransition(
                f"action {action_id} changed under us; '{target}' no longer valid"
            )

    # -- write / state machine ------------------------------------------------

    def propose(
        self,
        agent: str,
        action_type: str,
        subject: str,
        payload: dict[str, Any],
        region: str,
        requested_by: str,
        level: int = 2,
        scheduled_at: Any = None,
        branch_id: str | None = None,
        session_uuid: str | None = None,
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        """Create a new action in status `proposed` + its first `action_events` row.

        `scheduled_at` is stored as a column rather than left in the payload because the RBI
        conduct-hours control keys on it and auditors query it directly.

        `session_uuid` and `trace_id` are the provenance chain: they let an auditor start from an
        action taken against a customer and walk back to the question that prompted it, the SQL that
        was run, the rows that came back and the model call that proposed it. An action nobody can
        trace back to its evidence is not auditable, however complete the approval record looks.

        Returns the inserted action row (including its generated `id`).
        """
        row = lakebase.execute(
            "INSERT INTO actions "
            "(agent, action_type, subject, payload, status, level, region, branch_id, "
            " scheduled_at, session_uuid, trace_id, requested_by) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING *",
            (agent, action_type, subject, _as_jsonb(payload), PROPOSED,
             level, region, branch_id, scheduled_at, session_uuid, trace_id, requested_by),
            returning=True,
        )
        self._event(row["id"], "proposed", requested_by,
                    {"action_type": action_type, "subject": subject, "level": level,
                     "scheduled_at": str(scheduled_at) if scheduled_at else None,
                     "session_uuid": session_uuid, "trace_id": trace_id})
        return row

    def approve(self, action_id: int, approver: str) -> dict[str, Any]:
        """proposed|escalated → approved. Stamps approved_by + decided_at."""
        action = self._require(action_id)
        self._check_transition(action["status"], APPROVED)
        row = lakebase.execute(
            "UPDATE actions SET status = %s, approved_by = %s, decided_at = now() "
            "WHERE id = %s AND status = %s RETURNING *",
            (APPROVED, approver, action_id, action["status"]),
            returning=True,
        )
        self._cas_or_raise(row, action_id, APPROVED)
        self._event(action_id, "approved", approver)
        return row

    def reject(self, action_id: int, approver: str, reason: str) -> dict[str, Any]:
        """proposed|approved|escalated → rejected (terminal). Records the reason."""
        action = self._require(action_id)
        self._check_transition(action["status"], REJECTED)
        row = lakebase.execute(
            "UPDATE actions SET status = %s, approved_by = %s, decided_at = now() "
            "WHERE id = %s AND status = %s RETURNING *",
            (REJECTED, approver, action_id, action["status"]),
            returning=True,
        )
        self._cas_or_raise(row, action_id, REJECTED)
        self._event(action_id, "rejected", approver, {"reason": reason})
        return row

    def mark_executing(self, action_id: int, actor: str = "executor") -> dict[str, Any]:
        """approved → executing. Only an approved action may begin executing."""
        action = self._require(action_id)
        self._check_transition(action["status"], EXECUTING)
        row = lakebase.execute(
            "UPDATE actions SET status = %s WHERE id = %s AND status = %s RETURNING *",
            (EXECUTING, action_id, action["status"]),
            returning=True,
        )
        self._cas_or_raise(row, action_id, EXECUTING)
        self._event(action_id, "executing", actor)
        return row

    def mark_executed(
        self,
        action_id: int,
        result: dict[str, Any] | None = None,
        external_ref: str | None = None,
        actor: str = "executor",
    ) -> dict[str, Any]:
        """executing → executed (terminal). Records result + the external system ref."""
        action = self._require(action_id)
        self._check_transition(action["status"], EXECUTED)
        row = lakebase.execute(
            "UPDATE actions SET status = %s, result = %s, external_ref = %s, "
            "executed_at = now() WHERE id = %s AND status = %s RETURNING *",
            (EXECUTED, _as_jsonb(result), external_ref, action_id, action["status"]),
            returning=True,
        )
        self._cas_or_raise(row, action_id, EXECUTED)
        self._event(action_id, "executed", actor,
                    {"external_ref": external_ref, "result": result})
        return row

    def mark_failed(
        self,
        action_id: int,
        result: dict[str, Any] | None = None,
        actor: str = "executor",
    ) -> dict[str, Any]:
        """executing → failed (terminal). Records the failure detail."""
        action = self._require(action_id)
        self._check_transition(action["status"], FAILED)
        row = lakebase.execute(
            "UPDATE actions SET status = %s, result = %s, executed_at = now() "
            "WHERE id = %s AND status = %s RETURNING *",
            (FAILED, _as_jsonb(result), action_id, action["status"]),
            returning=True,
        )
        self._cas_or_raise(row, action_id, FAILED)
        self._event(action_id, "failed", actor, {"result": result})
        return row

    def escalate(self, action_id: int, reason: str, actor: str = "guardrails") -> dict[str, Any]:
        """any non-terminal → escalated. The guardrail-breach human gate."""
        action = self._require(action_id)
        self._check_transition(action["status"], ESCALATED)
        row = lakebase.execute(
            "UPDATE actions SET status = %s WHERE id = %s AND status = %s RETURNING *",
            (ESCALATED, action_id, action["status"]),
            returning=True,
        )
        self._cas_or_raise(row, action_id, ESCALATED)
        self._event(action_id, "escalated", actor, {"reason": reason})
        return row
