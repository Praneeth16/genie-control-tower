"""Administrative authorisation for the control tower's operator surfaces.

Distinct from the APPROVAL authority in action_plane.guardrails: that decides who may sign off on one
action, this decides who may operate the system itself — stop the agents, read the platform audit feed,
enumerate generated documents.

These are not per-record business data, so a Unity Catalog row filter is the wrong instrument. They are
administrative endpoints, and before this existed any signed-in user could reach them: an ordinary user
could resume actions after an emergency stop, or read every other user's email address and source IP
out of the audit feed.

Fails CLOSED. If the role directory cannot be read, nobody is an administrator.
"""
from __future__ import annotations

from fastapi import HTTPException, Request

import identity
import lakebase

ADMIN_ROLE = "Control Tower Administrator"


def is_admin(principal: str) -> bool:
    try:
        rows = lakebase.query(
            "SELECT 1 FROM approver_roles WHERE lower(principal) = lower(%s) AND role = %s",
            (principal, ADMIN_ROLE))
    except Exception:
        return False
    return bool(rows)


def require_admin(request: Request) -> str:
    """Return the caller if they hold the administrator role, else raise 403."""
    who = identity.user_email(request)
    if not is_admin(who):
        raise HTTPException(
            403,
            f"{who} does not hold the '{ADMIN_ROLE}' role required for this operation. "
            "Administrative surfaces are restricted because they expose other users' activity and "
            "can stop or resume the action plane.")
    return who
