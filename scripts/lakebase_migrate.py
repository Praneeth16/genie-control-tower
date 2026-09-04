"""Apply the Lakebase (Postgres) migrations for the control tower.

    python3 scripts/lakebase_migrate.py               # apply every lakebase/*.sql in order
    python3 scripts/lakebase_migrate.py --check       # connect + report current state only

Auth: a short-lived Lakebase credential minted through the Databricks SDK for the CLI profile's
identity — there is no stored Postgres password anywhere in this repo.
"""
from __future__ import annotations

import argparse
import glob
import os
import sys

import psycopg
from psycopg.rows import dict_row
from databricks.sdk import WorkspaceClient

# Importing config loads .env, so this script and the app can never disagree about which
# instance or schema they are using.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "app", "backend"))
import config  # noqa: E402

PROFILE = os.environ.get("DATABRICKS_CONFIG_PROFILE") or None
INSTANCE = config.LAKEBASE_INSTANCE
# Whoever runs the install becomes the first Control Tower Administrator and approver. Resolved from the
# workspace identity rather than written into the SQL, so a fresh install grants the installer and not
# whoever happened to build this.
ADMIN_PRINCIPAL = os.environ.get("CT_ADMIN_PRINCIPAL", "")


def render(sql: str, admin: str) -> str:
    """Substitute deployment-specific names into a migration.

    The Postgres schema was written into the SQL as a literal, which meant LAKEBASE_SCHEMA configured the
    app's search_path while the migration created a different schema entirely — the app would connect
    successfully and find no tables.
    """
    out = sql.replace("${ADMIN_PRINCIPAL}", admin).replace("${LAKEBASE_SCHEMA}", SCHEMA)
    import re as _re
    left = _re.findall(r"\$\{[A-Z_]+\}", out)
    if left:
        raise SystemExit(f"unsubstituted placeholders in migration: {sorted(set(left))}")
    return out
DBNAME = config.LAKEBASE_DBNAME
SCHEMA = config.LAKEBASE_SCHEMA
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


_admin = ""


def connect() -> psycopg.Connection:
    w = WorkspaceClient(profile=PROFILE) if PROFILE else WorkspaceClient()
    inst = w.database.get_database_instance(name=INSTANCE)
    cred = w.database.generate_database_credential(instance_names=[INSTANCE])
    user = w.current_user.me().user_name
    print(f"connecting {user} -> {INSTANCE} ({inst.read_write_dns}) db={DBNAME}")
    return psycopg.connect(
        host=inst.read_write_dns, port=5432, dbname=DBNAME,
        user=user, password=cred.token, sslmode="require",
        autocommit=True, row_factory=dict_row,
    )


def report(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = %s ORDER BY table_name", (SCHEMA,))
        tables = [r["table_name"] for r in cur.fetchall()]
        print(f"schema {SCHEMA}: {len(tables)} tables -> {', '.join(tables) or '(none)'}")
        for t in ("actions", "action_events", "action_policies", "agent_sessions", "runtime_flags"):
            if t in tables:
                cur.execute(f"SELECT count(*) AS n FROM {SCHEMA}.{t}")
                print(f"  {t:18} {cur.fetchone()['n']:>6} rows")


def main() -> int:
    global _admin
    if not INSTANCE:
        raise SystemExit("LAKEBASE_INSTANCE is not set — see README 'Configure'.")
    w = WorkspaceClient(profile=PROFILE) if PROFILE else WorkspaceClient()
    _admin = ADMIN_PRINCIPAL or w.current_user.me().user_name
    print(f"admin principal / first approver: {_admin}")
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="report state without applying migrations")
    args = ap.parse_args()

    files = sorted(glob.glob(os.path.join(HERE, "lakebase", "*.sql")))
    with connect() as conn:
        if not args.check:
            for path in files:
                sql = render(open(path).read(), _admin)
                print(f"applying {os.path.basename(path)} ...", end=" ", flush=True)
                try:
                    # psycopg3 executes a multi-statement script in one call when no params are bound.
                    with conn.cursor() as cur:
                        cur.execute(sql)
                    print("ok")
                except Exception as e:
                    print("FAIL")
                    print(f"  {e}")
                    return 1
        report(conn)
    return 0


if __name__ == "__main__":
    sys.exit(main())
