"""Grant the deployed app's service principal what its controls actually need.

This cannot live in the bundle. `uc_securable` has no SCHEMA level, and the service principal id does not
exist until the app has been created — so schema-wide SELECT and the unrestricted row entitlement have to
be applied afterwards, once the id is known.

Getting this wrong produces the most confusing possible install: the app deploys, health looks fine, and
every guardrail refuses — because the control identity is being row-filtered out of the evidence it exists
to check. It fails closed, which is correct, and it looks like a bug in the guardrails.

    python3 scripts/grant_app_sp.py --app <app-name>
    python3 scripts/grant_app_sp.py --app <app-name> --dry-run
"""
from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "app", "backend"))

import config                      # noqa: E402
import databricks_client as dbx    # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--app", required=True, help="Databricks App name")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    w = dbx.client()
    app = w.apps.get(name=a.app)
    sp = app.service_principal_client_id or app.service_principal_id
    if not sp:
        raise SystemExit(f"app '{a.app}' has no service principal yet — deploy it first")
    print(f"app {a.app} service principal: {sp}\n")

    statements = [
        # Read the governed data. The guardrails verify against these tables as this identity.
        f"GRANT USE CATALOG ON CATALOG {config.CATALOG} TO `{sp}`",
        f"GRANT USE SCHEMA ON SCHEMA {config.FQ} TO `{sp}`",
        f"GRANT SELECT ON SCHEMA {config.FQ} TO `{sp}`",
        # Call the controls. These are the conduct rules; EXECUTE on the functions rather than write
        # access on the tables is what keeps the identity SELECT-only while still able to act.
        f"GRANT EXECUTE ON SCHEMA {config.FQ} TO `{sp}`",
        # Write the generated drafts back to the volume as UNSIGNED documents.
        f"GRANT READ VOLUME, WRITE VOLUME ON VOLUME {config.FQ}.{config.VOLUME} TO `{sp}`",
        f"GRANT READ VOLUME ON VOLUME {config.FQ}.seed TO `{sp}`",
        # The unrestricted entitlement WITHOUT which every guardrail is blinded. This is the row that
        # `assert_not_blinded()` checks the effect of, and the reason it checks on every evaluation.
        f"DELETE FROM {config.FQ}.region_entitlement WHERE principal = '{sp}'",
        f"INSERT INTO {config.FQ}.region_entitlement (principal, region, granted_by, granted_at) "
        f"VALUES ('{sp}', 'ALL', 'install', current_timestamp())",
    ]
    if config.VS_INDEX:
        statements.append(f"GRANT SELECT ON TABLE {config.VS_INDEX} TO `{sp}`")
        statements.append(f"GRANT SELECT ON TABLE {config.FQ}.document_index_source TO `{sp}`")

    failed = 0
    for stmt in statements:
        if a.dry_run:
            print(f"  would run: {stmt}")
            continue
        try:
            dbx.run_sql(stmt)
            print(f"  ok   {stmt[:96]}")
        except Exception as e:
            failed += 1
            print(f"  FAIL {stmt[:96]}\n       {type(e).__name__}: {str(e)[:150]}")

    if a.dry_run:
        return 0
    print(f"\n{len(statements) - failed}/{len(statements)} grants applied")
    if not failed:
        print("Verify with /api/health: `guardrail_blinded` must be false.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
