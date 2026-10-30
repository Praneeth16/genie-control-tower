"""Apply the Lakebase (Postgres) migrations for the control tower.

    python3 scripts/lakebase_migrate.py --endpoint projects/<p>/branches/production/endpoints/primary \\
        --schema control_tower [--profile <cli-profile>] [--root .]
    ... --check        connect and report current state only

Runs locally or as a setup job task. Auth is a short-lived Lakebase credential minted through the
Databricks SDK for the calling identity; there is no stored Postgres password anywhere in this repo.
Every migration is idempotent and re-applied in order on each run.
"""
from __future__ import annotations

import argparse
import glob
import os
import re

import psycopg
from databricks.sdk import WorkspaceClient
from psycopg.rows import dict_row


def render(sql: str, admin: str, schema: str) -> str:
    """Substitute deployment-specific names. The Postgres schema used to be a literal in the SQL, so the
    app's search_path pointed at one schema while the migration created another — it connected fine and
    found no tables."""
    out = sql.replace("${ADMIN_PRINCIPAL}", admin).replace("${LAKEBASE_SCHEMA}", schema)
    left = re.findall(r"\$\{[A-Z_]+\}", out)
    if left:
        raise SystemExit(f"unsubstituted placeholders in migration: {sorted(set(left))}")
    return out


def connect(w: WorkspaceClient, endpoint: str, dbname: str) -> psycopg.Connection:
    host = w.postgres.get_endpoint(name=endpoint).status.hosts.host
    cred = w.postgres.generate_database_credential(endpoint=endpoint)
    user = w.current_user.me().user_name
    print(f"connecting {user} -> {endpoint} ({host}) db={dbname}")
    return psycopg.connect(host=host, port=5432, dbname=dbname, user=user, password=cred.token,
                           sslmode="require", autocommit=True, row_factory=dict_row)


def report(conn: psycopg.Connection, schema: str) -> None:
    with conn.cursor() as cur:
        cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = %s "
                    "ORDER BY table_name", (schema,))
        tables = [r["table_name"] for r in cur.fetchall()]
        print(f"schema {schema}: {len(tables)} tables")
        for t in tables:
            cur.execute(f'SELECT count(*) AS n FROM "{schema}"."{t}"')
            print(f"  {t:22} {cur.fetchone()['n']:>7} rows")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--endpoint", required=True)
    ap.add_argument("--schema", default="control_tower")
    ap.add_argument("--dbname", default="databricks_postgres")
    ap.add_argument("--profile", default=os.environ.get("DATABRICKS_CONFIG_PROFILE"))
    # Serverless job tasks exec the file, so __file__ is undefined there; the bundle passes its root.
    ap.add_argument("--root", default=".")
    ap.add_argument("--check", action="store_true", help="report state without applying migrations")
    a = ap.parse_args()

    w = WorkspaceClient(profile=a.profile) if a.profile else WorkspaceClient()
    # Whoever runs the install becomes the first Control Tower Administrator and approver.
    admin = w.current_user.me().user_name
    with connect(w, a.endpoint, a.dbname) as conn:
        if not a.check:
            for path in sorted(glob.glob(os.path.join(a.root, "lakebase", "*.sql"))):
                print(f"applying {os.path.basename(path)}")
                with conn.cursor() as cur:
                    # psycopg3 runs a multi-statement script in one call when no parameters are bound.
                    cur.execute(render(open(path).read(), admin, a.schema))
        report(conn, a.schema)


if __name__ == "__main__":
    # Not sys.exit(main()): serverless job tasks report SystemExit(0) as a failure.
    main()
