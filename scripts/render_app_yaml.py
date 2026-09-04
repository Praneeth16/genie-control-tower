"""Render app/app.yaml from the resolved configuration.

Why this exists, learned the hard way: `databricks apps deploy --source-code-path` reads `app.yaml` FROM
THE SOURCE PATH. It does NOT apply `resources.apps.<name>.config` from the bundle. So moving the env block
into databricks.yml for portability left the deployed app with no configuration at all, and it crashed on
import with `CT_CATALOG is not set` — which is at least the failure the config module was written to
produce, rather than a silent misread.

The fix keeps one source of truth without depending on which deploy path is used: `app.yaml.template` is
committed and carries placeholders; `app.yaml` is generated from the same values the app itself resolves,
and is gitignored so no workspace's ids are ever committed.

    python3 scripts/render_app_yaml.py            # write app/app.yaml
    python3 scripts/render_app_yaml.py --check    # verify it is present and current
"""
from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "app", "backend"))

import config  # noqa: E402

TEMPLATE = os.path.join(ROOT, "app", "app.yaml.template")
TARGET = os.path.join(ROOT, "app", "app.yaml")


def values() -> dict[str, str]:
    return {
        "CT_CATALOG": config.CATALOG,
        "CT_SCHEMA": config.SCHEMA,
        "CT_VOLUME": config.VOLUME,
        "DATABRICKS_WAREHOUSE_ID": config.WAREHOUSE_ID,
        "DATABRICKS_CHAT_ENDPOINT": config.CHAT_ENDPOINT,
        "LAKEBASE_INSTANCE": config.LAKEBASE_INSTANCE,
        "LAKEBASE_DBNAME": config.LAKEBASE_DBNAME,
        "LAKEBASE_SCHEMA": config.LAKEBASE_SCHEMA,
        "COLLECTIONS_SPACE_ID": config.SPACE_IDS.get("COLLECTIONS", ""),
        "GRIEVANCE_SPACE_ID": config.SPACE_IDS.get("GRIEVANCE", ""),
        "RM_SPACE_ID": config.SPACE_IDS.get("RM", ""),
        "DASHBOARD_ID": config.DASHBOARD_ID,
        "VS_ENDPOINT": config.VS_ENDPOINT,
        "VS_INDEX": config.VS_INDEX,
        "MLFLOW_EXPERIMENT": config.MLFLOW_EXPERIMENT,
        "CT_HTTP_CONNECTION": os.environ.get("CT_HTTP_CONNECTION",
                                                   "ct_external_systems"),
        "CT_MOCK_SYSTEMS_URL": os.environ.get("CT_MOCK_SYSTEMS_URL", ""),
        "BANK_NAME": config.BANK_NAME,
        "GROUP_PREFIX": config.GROUP_PREFIX,
        "PSEUDONYM_SALT": config.PSEUDONYM_SALT,
    }


def render() -> str:
    body = open(TEMPLATE).read()
    for key, value in values().items():
        body = body.replace(f"${{{key}}}", value)
    left = [t for t in ("${",) if t in body]
    if left:
        import re
        unresolved = sorted(set(re.findall(r"\$\{[A-Z_]+\}", body)))
        # $DATABRICKS_APP_PORT is supplied by the Apps runtime, not by us.
        unresolved = [u for u in unresolved if u != "${DATABRICKS_APP_PORT}"]
        if unresolved:
            raise SystemExit(f"unresolved placeholders in app.yaml.template: {unresolved}")
    return body


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    body = render()
    if a.check:
        if not os.path.exists(TARGET):
            print("app/app.yaml is MISSING — run scripts/render_app_yaml.py before deploying")
            return 1
        current = open(TARGET).read()
        same = current == body
        print("app/app.yaml is current" if same else "app/app.yaml is STALE — re-render before deploying")
        return 0 if same else 1
    with open(TARGET, "w") as fh:
        fh.write(body)
    print(f"wrote {TARGET}")
    for k, v in values().items():
        print(f"  {k:28} {v or '(blank)'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
