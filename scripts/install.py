"""One-command install into a fresh workspace.

    python3 scripts/install.py --check          # verify prerequisites only, change nothing
    python3 scripts/install.py                  # full install
    python3 scripts/install.py --from data      # resume from a step (see STEPS)

Each step is idempotent, so re-running after a failure is safe. Order is NOT arbitrary and the two
constraints that bite are enforced here rather than left to a runbook:

  * `data/ddl.sql` builds tables with `read_files()` FROM THE SEED VOLUME, so the CSVs must be uploaded
    before it runs. Skipping that silently loads whatever was already on the volume.
  * `CREATE OR REPLACE TABLE` DROPS row filters, column masks and comments. Governance must therefore be
    re-applied after ANY table rebuild, or the app comes up ungoverned while looking perfectly healthy.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "app", "backend"))

PY_EXE = sys.executable or "python3"


def sh(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    print(f"\n$ {' '.join(cmd)}")
    return subprocess.run(cmd, cwd=ROOT, **kw)


def must(cmd: list[str]) -> None:
    if sh(cmd).returncode != 0:
        raise SystemExit(f"step failed: {' '.join(cmd)}")


# --------------------------------------------------------------------------- prerequisites
def check() -> int:
    print("Prerequisites\n" + "-" * 60)
    problems: list[str] = []

    try:
        import config
    except Exception as e:
        print(f"  FAIL  configuration: {e}")
        return 1
    print(f"  ok    catalog        {config.FQ}")
    print(f"  ok    warehouse      {config.WAREHOUSE_ID}")
    print(f"  ok    lakebase       {config.LAKEBASE_INSTANCE}/{config.LAKEBASE_SCHEMA}")

    import databricks_client as dbx
    try:
        me = dbx.current_user()
        print(f"  ok    authenticated as {me}")
    except Exception as e:
        print(f"  FAIL  cannot authenticate: {e}")
        return 1

    w = dbx.client()
    # Warehouse must exist and be startable, or every later step fails opaquely.
    try:
        wh = w.warehouses.get(id=config.WAREHOUSE_ID)
        print(f"  ok    warehouse '{wh.name}' state={wh.state}")
    except Exception as e:
        problems.append(f"warehouse {config.WAREHOUSE_ID} not reachable: {str(e)[:90]}")

    try:
        w.catalogs.get(name=config.CATALOG)
        print(f"  ok    catalog '{config.CATALOG}' exists")
    except Exception as e:
        problems.append(f"catalog {config.CATALOG} not reachable: {str(e)[:90]}")

    try:
        inst = w.database.get_database_instance(name=config.LAKEBASE_INSTANCE)
        print(f"  ok    lakebase instance state={inst.state}")
    except Exception as e:
        problems.append(f"lakebase instance {config.LAKEBASE_INSTANCE} not reachable: {str(e)[:90]}")

    try:
        w.serving_endpoints.get(name=config.CHAT_ENDPOINT)
        print(f"  ok    chat endpoint '{config.CHAT_ENDPOINT}'")
    except Exception as e:
        problems.append(f"chat endpoint {config.CHAT_ENDPOINT} not reachable: {str(e)[:90]}")

    if config.VS_ENDPOINT:
        try:
            eps = [e.name for e in w.vector_search_endpoints.list_endpoints()]
            if config.VS_ENDPOINT in eps:
                print(f"  ok    vector search endpoint '{config.VS_ENDPOINT}'")
            else:
                problems.append(f"VS_ENDPOINT '{config.VS_ENDPOINT}' not found. Available: {eps[:5]}")
        except Exception as e:
            problems.append(f"cannot list vector search endpoints: {str(e)[:90]}")
    else:
        print("  skip  vector search (VS_ENDPOINT blank — semantic search will be disabled)")

    for tool in ("databricks", "npm"):
        rc = subprocess.run(["which", tool], capture_output=True).returncode
        print(f"  {'ok  ' if rc == 0 else 'FAIL'}  {tool} on PATH")
        if rc != 0:
            problems.append(f"{tool} is not on PATH")

    print("-" * 60)
    for p in problems:
        print(f"  PROBLEM  {p}")
    print("prerequisites OK" if not problems else f"{len(problems)} problem(s) — fix before installing")
    return 1 if problems else 0


# --------------------------------------------------------------------------- steps
def step_volumes() -> None:
    """Schema and volumes must exist before anything can be written to them."""
    import config
    must([PY_EXE, "scripts/sqlx.py", f"CREATE SCHEMA IF NOT EXISTS {config.FQ}"])
    for vol in (config.VOLUME, "seed", "inbound", "outbound"):
        must([PY_EXE, "scripts/sqlx.py", f"CREATE VOLUME IF NOT EXISTS {config.FQ}.{vol}"])


def step_data() -> None:
    import config
    must([PY_EXE, "data/generate_banking_data.py", "--out", "data/out"])
    seed = f"dbfs:/Volumes/{config.CATALOG}/{config.SCHEMA}/seed"
    # The dbfs: prefix is required — without it the CLI reports "no such directory" for a UC volume.
    for name in sorted(os.listdir(os.path.join(ROOT, "data", "out"))):
        if name.endswith(".csv"):
            must(["databricks", "fs", "cp", f"data/out/{name}", f"{seed}/{name}", "--overwrite"])
    must([PY_EXE, "scripts/sqlx.py", "--file", "data/ddl.sql"])


def step_governance() -> None:
    """MUST follow step_data: CREATE OR REPLACE TABLE drops filters and masks."""
    must([PY_EXE, "scripts/sqlx.py", "--file", "governance/policies.sql"])
    must([PY_EXE, "scripts/sqlx.py", "--file", "governance/action_functions.sql"])


def step_lakebase() -> None:
    must([PY_EXE, "scripts/lakebase_migrate.py"])


def step_genie() -> None:
    must([PY_EXE, "genie/create_genie_agents.py", "--create"])
    print("\n>>> Copy the ids from genie/space_ids.json into .env AND into your bundle variable "
          "overrides, then re-run from --from documents.")


def step_documents() -> None:
    import config
    must([PY_EXE, "data/generate_documents.py"])
    root = f"dbfs:/Volumes/{config.CATALOG}/{config.SCHEMA}/{config.VOLUME}"
    for sub in ("complaints", "agencies", "compliance"):
        must(["databricks", "fs", "cp", f"data/documents/{sub}", f"{root}/{sub}",
              "--recursive", "--overwrite"])
    must([PY_EXE, "scripts/sqlx.py", "--file", "data/documents.sql"])


def step_vector() -> None:
    import config
    if not config.VS_ENDPOINT:
        print("  skipped: VS_ENDPOINT is blank, so semantic search stays disabled.")
        return
    must([PY_EXE, "scripts/build_vector_index.py", "--create"])
    print("  the index embeds asynchronously; `--status` should reach ready=True in a few minutes.")


def step_dashboard() -> None:
    must([PY_EXE, "dashboards/build_dashboard.py", "--deploy"])
    print("\n>>> Copy the printed DASHBOARD_ID into .env and your bundle variable overrides.")


def step_app() -> None:
    must(["npm", "--prefix", "app/frontend", "install"])
    must(["npm", "--prefix", "app/frontend", "run", "build"])
    must(["databricks", "bundle", "deploy", "-t", "dev"])
    print("\n>>> `bundle deploy` creates/updates the app RESOURCE. To ship the code, see README "
          "'Deploy the app'.")


def step_verify() -> None:
    must([PY_EXE, "eval/run_eval.py", "golden"])
    must([PY_EXE, "eval/governance_tests.py"])
    must([PY_EXE, "dashboards/build_dashboard.py", "--validate-sql"])


STEPS = [
    ("volumes", step_volumes, "schema + volumes"),
    ("data", step_data, "generate 268k rows, upload CSVs, build 18 tables"),
    ("governance", step_governance, "row filters, column masks, tags, UC control functions"),
    ("lakebase", step_lakebase, "approval state machine + approver roles"),
    ("genie", step_genie, "create the three Genie Agents"),
    ("documents", step_documents, "generate 713 letters, upload, parse into Delta"),
    ("vector", step_vector, "Vector Search index over the corpus"),
    ("dashboard", step_dashboard, "build + publish the AI/BI dashboard"),
    ("app", step_app, "build the frontend and deploy the bundle"),
    ("verify", step_verify, "goldens, governance assertions, dashboard datasets"),
]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="prerequisites only")
    ap.add_argument("--from", dest="start", default="", choices=[s[0] for s in STEPS] + [""])
    ap.add_argument("--only", default="", help="run a single step")
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()

    if a.list:
        for name, _, desc in STEPS:
            print(f"  {name:<12} {desc}")
        return 0
    if a.check:
        return check()
    if check() != 0:
        return 1

    started = not a.start
    for name, fn, desc in STEPS:
        if a.only and name != a.only:
            continue
        if not a.only:
            started = started or name == a.start
            if not started:
                print(f"\n=== skipping {name} ===")
                continue
        print(f"\n{'=' * 70}\n=== {name}: {desc}\n{'=' * 70}")
        fn()
    print("\ninstall complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
