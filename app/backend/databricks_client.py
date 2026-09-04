"""Databricks SDK access — the shared backend module.

Provides:
  - a process-wide WorkspaceClient singleton (auths via the app service principal
    in Databricks Apps, or via the CLI profile `DATABRICKS_CONFIG_PROFILE` locally),
  - `run_sql(...)`  — execute governed Spark SQL on the serverless SQL warehouse and
    return {columns, rows} with rows as list-of-dicts,
  - `chat(...)`     — query a Databricks Model Serving chat endpoint (OpenAI-style messages).

`run_sql` executes as whatever identity the client is bound to. That matters: business reads run
on behalf of the user, but guardrail verification deliberately runs as the app service principal —
see action_plane/guardrails.py for why a control must not be subject to the caller's row filters.
"""
from __future__ import annotations

import os
import threading
from functools import lru_cache
from typing import Any

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.serving import ChatMessage, ChatMessageRole

# Resolved once in config.py so a stale warehouse id cannot be right in one module and wrong in
# another — the failure mode that made this indirection worth adding.
import config

SQL_WAREHOUSE_ID = config.WAREHOUSE_ID
CHAT_ENDPOINT = config.CHAT_ENDPOINT

_lock = threading.Lock()
_client: WorkspaceClient | None = None


def client() -> WorkspaceClient:
    """Return the process-wide WorkspaceClient singleton (thread-safe)."""
    global _client
    if _client is None:
        with _lock:
            if _client is None:
                _client = WorkspaceClient()
    return _client


@lru_cache(maxsize=1)
def current_user() -> str:
    """The identity the SDK is authenticating as (email)."""
    return client().current_user.me().user_name


def run_sql(statement: str, warehouse_id: str | None = None, wait_timeout: str = "50s",
            w: "WorkspaceClient | None" = None,
            parameters: dict[str, tuple[Any, str]] | None = None,
            catalog: str | None = None, schema: str | None = None) -> dict[str, Any]:
    """Execute governed SQL on the serverless warehouse AS `w` (default: the app service principal).

    `w` is not optional decoration — it decides whose Unity Catalog row filters and column masks
    apply. Passing the end user's client keeps a read governed; omitting it runs as the app service
    principal, which sees the whole book. Business reads must always pass the user's client. The only
    caller that deliberately omits it is the guardrail engine, which must not be blinded by the
    caller's own filters.

    `parameters` binds named SQL markers safely: {"loan": ("LN000041", "STRING")} for a statement
    referencing `:loan`. Always use it for any value that came from a model or a request body.

    Returns {"columns": [..], "rows": [{col: val, ...}, ...], "row_count": n}.
    Raises RuntimeError on a non-SUCCEEDED terminal state.
    """
    params = None
    if parameters:
        # Named parameters, not string interpolation. The guardrail engine feeds MODEL-GENERATED
        # values (a loan account id, an agent id) into control queries; concatenating those into SQL
        # would let a crafted payload rewrite the control that is meant to stop it.
        from databricks.sdk.service.sql import StatementParameterListItem
        params = [
            StatementParameterListItem(name=k, value=(None if v is None else str(v)), type=t)
            for k, (v, t) in parameters.items()
        ]

    # Bind catalog and schema PER STATEMENT. The Statement Execution API treats every statement as an
    # independent session, so a `USE CATALOG` never carries over and an unqualified name silently
    # resolves against the warehouse default instead — which is how 18 tables once landed in
    # `default` and how the UC control functions first came back UNRESOLVED_ROUTINE.
    resp = (w or client()).statement_execution.execute_statement(
        warehouse_id=warehouse_id or SQL_WAREHOUSE_ID,
        statement=statement,
        wait_timeout=wait_timeout,
        parameters=params,
        catalog=catalog or config.CATALOG,
        schema=schema or config.SCHEMA,
    )
    state = resp.status.state.value if resp.status and resp.status.state else "UNKNOWN"
    if state != "SUCCEEDED":
        msg = resp.status.error.message if resp.status and resp.status.error else state
        raise RuntimeError(f"SQL execution {state}: {msg}")

    columns: list[str] = []
    if resp.manifest and resp.manifest.schema and resp.manifest.schema.columns:
        columns = [c.name for c in resp.manifest.schema.columns]

    data = (resp.result.data_array if resp.result else None) or []
    rows = [dict(zip(columns, raw)) for raw in data]
    return {"columns": columns, "rows": rows, "row_count": len(rows)}


def chat(messages: list[dict[str, str]], endpoint: str | None = None,
         max_tokens: int = 1024, temperature: float | None = None) -> str:
    """Query a Model Serving chat endpoint. `messages` is OpenAI-style
    [{"role": "system"|"user"|"assistant", "content": str}, ...]. Returns text.

    Note: some endpoints (e.g. databricks-claude-opus-4-8) reject the
    `temperature` parameter, so it is only sent when explicitly provided."""
    role_map = {
        "system": ChatMessageRole.SYSTEM,
        "user": ChatMessageRole.USER,
        "assistant": ChatMessageRole.ASSISTANT,
    }
    chat_messages = [
        ChatMessage(role=role_map[m["role"]], content=m["content"]) for m in messages
    ]
    kwargs = {"name": endpoint or CHAT_ENDPOINT, "messages": chat_messages,
              "max_tokens": max_tokens}
    if temperature is not None:
        kwargs["temperature"] = temperature
    resp = client().serving_endpoints.query(**kwargs)
    return resp.choices[0].message.content
