"""Who is asking — resolved from the Databricks Apps identity headers, never from the request body.

Apps terminates SSO in front of the app and forwards the signed-in user as headers. Trusting the
body instead would let any caller name themselves as the approver of an action, which would make the
whole separation-of-duties story decorative. So: headers only.

Two different things come out of a request and they must not be confused:
  * `user_email(request)`  — the identity recorded as approver / asker in the audit trail.
  * `user_token(request)`  — the OBO access token used for GOVERNED READS, so Unity Catalog row
                             filters and column masks apply as that person.
"""
from __future__ import annotations

from fastapi import Request

import databricks_client as dbx

# Apps sets these in front of the app. Order matters: the email claim is the one that matches the
# principal Unity Catalog grants are written against.
_EMAIL_HEADERS = (
    "X-Forwarded-Email",
    "X-Forwarded-Preferred-Username",
    "X-Forwarded-User",
)
_TOKEN_HEADER = "X-Forwarded-Access-Token"


def user_email(request: Request, fallback_tag: str = "local-dev") -> str:
    """The authenticated end user. Falls back to the SDK identity (the app service principal) only
    outside Apps, where the headers are absent."""
    for h in _EMAIL_HEADERS:
        value = request.headers.get(h)
        if value:
            return value
    try:
        return dbx.current_user()
    except Exception:
        return f"{fallback_tag}@service"


def user_token(request: Request) -> str | None:
    """The end user's forwarded access token, or None outside Apps."""
    return request.headers.get(_TOKEN_HEADER)


def is_obo(request: Request) -> bool:
    """True when this request carries a real user token, i.e. reads will be governed per user.
    Surfaced in the UI so nobody mistakes a local-dev session for a governed one."""
    return bool(user_token(request))
