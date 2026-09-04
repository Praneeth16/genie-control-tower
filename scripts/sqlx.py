"""Run SQL against the workshop SQL warehouse via the Databricks SDK.

Usage:
    python3 scripts/sqlx.py "SELECT 1"
    python3 scripts/sqlx.py --file path/to/file.sql      # split on ';' at line ends
    echo "SELECT 1" | python3 scripts/sqlx.py -

Configuration comes from the same place the app uses — app/backend/config.py, which loads a `.env` from
the repo root. There are no defaults for anything workspace-specific: a default pointing at the workspace
this was built in would install cleanly elsewhere and then fail on every read.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import time

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import StatementState

# Importing config is what loads .env, and it validates the required names in one place rather than each
# script re-deriving them slightly differently.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "app", "backend"))
import config  # noqa: E402

PROFILE = os.environ.get("DATABRICKS_CONFIG_PROFILE") or None
WAREHOUSE = config.WAREHOUSE_ID

# The Statement Execution API treats every statement as an independent session, so a
# `USE CATALOG` / `USE SCHEMA` in a script does NOT carry to the next statement — unqualified
# names silently resolve against the warehouse default instead. Bind them per request.
CATALOG = config.CATALOG
SCHEMA = config.SCHEMA
VOLUME = config.VOLUME


def render(text: str) -> str:
    """Substitute deployment-specific names into a .sql file.

    Every SQL script in this repo is written against placeholders rather than a literal catalog. That is
    what makes the project installable somewhere other than the workspace it was built in: the catalog
    name appeared in 18 statements of ddl.sql alone, including inside `read_files('/Volumes/...')` paths
    where no `USE CATALOG` can reach it.
    """
    if not CATALOG:
        raise SystemExit(
            "CT_CATALOG is not set. Copy app/.env.example to .env and fill it in, or export the "
            "variables — see README 'Configure'.")
    for key, value in (("${CATALOG}", CATALOG), ("${SCHEMA}", SCHEMA), ("${VOLUME}", VOLUME),
                       ("${FQ}", f"{CATALOG}.{SCHEMA}"),
                       ("${VOLUME_ROOT}", f"/Volumes/{CATALOG}/{SCHEMA}/{VOLUME}"),
                       # Account-group prefix for the entitlement and masking groups, and the salt for the
                       # customer-id pseudonym. The salt MUST be identical everywhere and stable forever:
                       # change it and every pseudonym changes, so joins across anything masked with the
                       # old salt silently return nothing. In production it belongs in a secret scope.
                       ("${GROUP_PREFIX}", config.GROUP_PREFIX),
                       ("${PSEUDONYM_SALT}", config.PSEUDONYM_SALT)):
        text = text.replace(key, value)
    left = re.findall(r"\$\{[A-Z_]+\}", text)
    if left:
        raise SystemExit(f"unsubstituted placeholders remain: {sorted(set(left))}")
    return text

_w: WorkspaceClient | None = None


def client() -> WorkspaceClient:
    global _w
    if _w is None:
        _w = WorkspaceClient(profile=PROFILE) if PROFILE else WorkspaceClient()
    return _w


def run(sql: str, quiet: bool = False, max_rows: int = 40) -> dict:
    """Execute one statement, waiting for terminal state. Returns
    {"state", "error", "columns", "rows", "row_count"}."""
    w = client()
    resp = w.statement_execution.execute_statement(
        warehouse_id=WAREHOUSE, statement=sql, wait_timeout="50s",
        catalog=CATALOG or None, schema=SCHEMA or None,
    )
    # Poll if the server handed back a still-running statement.
    deadline = time.time() + 900
    while resp.status and resp.status.state in (StatementState.PENDING, StatementState.RUNNING):
        if time.time() > deadline:
            break
        time.sleep(2)
        resp = w.statement_execution.get_statement(resp.statement_id)

    state = resp.status.state.value if resp.status and resp.status.state else "UNKNOWN"
    err = ""
    if resp.status and resp.status.error:
        err = resp.status.error.message or ""

    cols, rows = [], []
    if resp.manifest and resp.manifest.schema and resp.manifest.schema.columns:
        cols = [c.name for c in resp.manifest.schema.columns]
    if resp.result and resp.result.data_array:
        rows = resp.result.data_array

    if not quiet:
        head = sql.strip().splitlines()[0][:96]
        mark = "ok  " if state == "SUCCEEDED" else "FAIL"
        print(f"[{mark}] {head}")
        if err:
            print(f"        {err.splitlines()[0][:300]}")
        if cols and rows:
            print("        " + " | ".join(cols))
            for r in rows[:max_rows]:
                print("        " + " | ".join("NULL" if v is None else str(v) for v in r))
            if len(rows) > max_rows:
                print(f"        ... {len(rows) - max_rows} more rows")
    return {"state": state, "error": err, "columns": cols, "rows": rows,
            "row_count": len(rows)}


def split_statements(text: str) -> list[str]:
    """Split a SQL script on semicolons that end a line, tolerating semicolons inside
    string literals and skipping -- comments."""
    out, buf, in_str = [], [], False
    for line in text.splitlines():
        stripped = line.strip()
        if not in_str and (not stripped or stripped.startswith("--")):
            continue
        buf.append(line)
        # Track unescaped single quotes to avoid splitting inside a literal.
        quotes = len(re.findall(r"(?<!\\)'", line))
        if quotes % 2 == 1:
            in_str = not in_str
        if not in_str and stripped.endswith(";"):
            stmt = "\n".join(buf).strip().rstrip(";").strip()
            if stmt:
                out.append(stmt)
            buf = []
    tail = "\n".join(buf).strip().rstrip(";").strip()
    if tail:
        out.append(tail)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("sql", nargs="?", help="SQL text, or - to read stdin")
    ap.add_argument("--file", help="path to a .sql file with ;-separated statements")
    ap.add_argument("--stop-on-error", action="store_true")
    args = ap.parse_args()

    if args.file:
        statements = split_statements(render(open(args.file).read()))
    elif args.sql == "-" or args.sql is None:
        statements = split_statements(render(sys.stdin.read()))
    else:
        statements = [render(args.sql)]

    failed = 0
    for stmt in statements:
        res = run(stmt)
        if res["state"] != "SUCCEEDED":
            failed += 1
            if args.stop_on_error:
                return 1
    if len(statements) > 1:
        print(f"\n{len(statements) - failed}/{len(statements)} statements succeeded")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
