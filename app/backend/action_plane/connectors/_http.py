"""Governed HTTP transport shared by every connector.

The PRIMARY path posts to the Mock External Systems app **through the Unity
Catalog HTTP connection** `ct_external_systems`, by running

    SELECT http_request(conn => 'ct_external_systems', method => 'POST',
                        path => '/<endpoint>', json => '<json>').text

on the serverless SQL warehouse via the shared `databricks_client.run_sql`. Every
external call therefore flows through Unity Catalog — that is the governance /
lineage story.

Two failure shapes have to be handled, because `http_request` does not raise on a
bad upstream response — it embeds the failure in the returned `.text`:

  * the SQL statement itself fails (e.g. the connection is missing) → `run_sql`
    raises `RuntimeError`;
  * the SQL succeeds but the column value carries
    `[REMOTE_FUNCTION_HTTP_FAILED_ERROR] ... code 302 ...` — this is what an
    EXPIRED connection bearer token looks like: Databricks Apps SSO 302-redirects
    the unauthenticated request to a login page.

On either auth-shaped failure we refresh the connection's bearer token ONCE (mint
a fresh token from the WorkspaceClient, then
`ALTER CONNECTION ... OPTIONS (host, port, base_path, bearer_token '<fresh>')`)
and retry. `ALTER` must re-state the required `host` option, so we re-state all of
them. (`CREATE OR REPLACE CONNECTION` is rejected on the SQL warehouse surface.)

If the UC-connection path is unavailable entirely, we FALL BACK to a direct HTTPS
POST to the mock app URL under the app service-principal OAuth token
(`WorkspaceClient().config.authenticate()`). Either way the call is governed (UC connection or SP identity) and The path actually used is returned to the caller as `via`.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

import databricks_client as dbx

CONNECTION_NAME = os.environ.get("CT_HTTP_CONNECTION", "ct_external_systems")
# No default: the mock-systems app is deployed per workspace and its URL contains the workspace id.
# Blank means the connectors fall back to recording the action without an outbound call, which is the
# right behaviour for an install that has not deployed the mock systems.
MOCK_APP_URL = os.environ.get("CT_MOCK_SYSTEMS_URL", "").rstrip("/")
# host/port/base_path the connection was created with — re-stated on every ALTER
# because UC requires the full option set, not just the option being changed.
_CONN_HOST = MOCK_APP_URL
_CONN_PORT = os.environ.get("CT_HTTP_PORT", "443")
_CONN_BASE_PATH = os.environ.get("CT_HTTP_BASE_PATH", "/")

# Substrings that mean "the connection's bearer token is no longer accepted".
_AUTH_FAIL_MARKERS = (
    "REMOTE_FUNCTION_HTTP_FAILED_ERROR",
    "code 302",
    "code 401",
    "code 403",
)


class ConnectorError(RuntimeError):
    """An external call could not be completed through any governed path."""


def _sql_quote(value: str) -> str:
    """Escape a string for safe embedding inside a single-quoted SQL literal."""
    return value.replace("\\", "\\\\").replace("'", "''")


def _fresh_bearer_token() -> str:
    """Mint a fresh workspace/SP bearer token from the WorkspaceClient config."""
    auth = dbx.client().config.authenticate()["Authorization"]
    return auth.split(" ", 1)[1]


def _refresh_connection_token() -> None:
    """Rotate the UC connection's bearer token in place.

    ALTER must include the required `host` option, so we re-state the full option
    set the connection was created with and only swap the bearer token.
    """
    token = _sql_quote(_fresh_bearer_token())
    dbx.run_sql(
        f"ALTER CONNECTION {CONNECTION_NAME} OPTIONS ("
        f"host '{_sql_quote(_CONN_HOST)}', port '{_CONN_PORT}', "
        f"base_path '{_sql_quote(_CONN_BASE_PATH)}', bearer_token '{token}')"
    )


def _classify(text: str) -> tuple[str, dict[str, Any] | None]:
    """Classify an http_request response *body text* into one of:
      ("success", parsed_dict)  — valid mock JSON carrying a ref_id
      ("auth_fail", None)       — non-JSON Databricks error envelope w/ 302/401/403
      ("error", None)           — any other non-JSON / unexpected body

    JSON is parsed FIRST. The mock echoes the caller's payload, so a *successful*
    response can legitimately contain the substring "code 302"; we must not treat a
    valid JSON success as an auth failure. Only a body that does NOT parse as the
    mock's JSON (i.e. a Databricks error envelope) is eligible to be an auth failure.
    """
    try:
        parsed = json.loads(text)
    except (ValueError, TypeError):
        parsed = None
    if isinstance(parsed, dict) and "ref_id" in parsed:
        return "success", parsed
    if parsed is None and any(m in text for m in _AUTH_FAIL_MARKERS):
        return "auth_fail", None
    return "error", None


def _request_via_connection(path: str, payload: dict[str, Any]) -> str:
    """Run one governed `http_request` POST and return the response `.text`."""
    body = _sql_quote(json.dumps(payload))
    sql = (
        f"SELECT http_request(conn => '{CONNECTION_NAME}', method => 'POST', "
        f"path => '{path}', json => '{body}').text AS response"
    )
    return dbx.run_sql(sql)["rows"][0]["response"]


def _post_direct(path: str, payload: dict[str, Any]) -> str:
    """Fallback: direct HTTPS POST to the mock app under the SP OAuth token."""
    if not MOCK_APP_URL:
        # Explicit, because the alternative is urllib being handed a relative URL and raising something
        # far less informative three frames down. An install that has not deployed the mock systems has
        # no outbound target, and that is a configuration state rather than a bug.
        raise RuntimeError(
            "CT_MOCK_SYSTEMS_URL is not set, so there is no external system to call. Deploy "
            "mock_systems/ and set the variable, or route through the Unity Catalog HTTP connection.")
    token = _fresh_bearer_token()
    req = urllib.request.Request(
        url=f"{MOCK_APP_URL}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8")


def _parse_ref(text: str) -> dict[str, Any]:
    """Parse a direct-path `{ref_id, status, echo}` response (SP-direct fallback).
    Raises on a non-JSON or error-shaped body so the caller can escalate / fail."""
    kind, parsed = _classify(text)
    if kind == "success":
        return parsed  # type: ignore[return-value]
    if kind == "auth_fail":
        raise ConnectorError(f"governed call failed (auth): {text[:300]}")
    raise ConnectorError(f"unexpected response from mock system: {text[:300]}")


def post(system: str, path: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Send `payload` to the mock app `path` through a governed path.

    Returns {"ref_id", "system", "raw", "via"} where `via` is the governed path
    actually used ("uc_connection" or "sp_direct"). Raises `ConnectorError` if no
    governed path can complete the call.
    """
    # Primary: through the UC HTTP connection (catalog-governed + lineage).
    try:
        kind, parsed = _classify(_request_via_connection(path, payload))
        if kind == "auth_fail":
            # Expired connection token — refresh ONCE and retry through UC.
            _refresh_connection_token()
            kind, parsed = _classify(_request_via_connection(path, payload))
        if kind == "success":
            return {"ref_id": parsed["ref_id"], "system": system, "raw": parsed,
                    "via": "uc_connection"}
        # Parsed but not a success and not auth (or auth persisted after refresh).
        raise ConnectorError(f"governed call did not succeed for {system} {path}")
    except ConnectorError:
        raise
    except Exception as conn_exc:  # UC-connection path unavailable → fall back.
        try:
            parsed = _parse_ref(_post_direct(path, payload))
            return {"ref_id": parsed["ref_id"], "system": system, "raw": parsed,
                    "via": "sp_direct"}
        except Exception as direct_exc:
            raise ConnectorError(
                f"both governed paths failed for {system} {path}: "
                f"uc_connection={conn_exc!r}; sp_direct={direct_exc!r}"
            ) from direct_exc
