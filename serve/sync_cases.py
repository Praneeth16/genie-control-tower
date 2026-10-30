"""Refresh the Lakebase case queue from the governed gold tables. A cycle job task, after the briefs.

    sync_cases.py --catalog <c> --schema <s> --endpoint projects/<p>/branches/production/endpoints/primary

The upsert names ONLY the machine-owned columns (facts, score, drivers, conduct flags, AI brief). Status,
owner, notes and next action date are never in the statement, so no refresh can overwrite what a person
decided. Accounts that have left the delinquent book are marked on_worklist = false rather than deleted:
the case and its history stay.

The writes run inside one transaction with ct.change_source = pipeline_sync, which is how the history
trigger knows a refresh, not a person, made the change.
"""
from __future__ import annotations

import argparse
import json

MACHINE_COLUMNS = ["region", "branch_id", "product_code", "snapshot_month", "dpd_days", "dpd_bucket",
                   "outstanding_principal", "priority_score", "priority_rank", "drivers", "conduct_flags",
                   "recommended_treatment", "ai_explanation", "ai_recommended_action", "ai_prompt_version"]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--catalog", required=True)
    ap.add_argument("--schema", required=True)
    ap.add_argument("--endpoint", required=True)
    ap.add_argument("--pg-schema", default="control_tower")
    ap.add_argument("--dbname", default="databricks_postgres")
    a = ap.parse_args()
    fq = f"{a.catalog}.{a.schema}"

    import psycopg
    from databricks.sdk import WorkspaceClient
    from psycopg import sql
    from pyspark.sql import SparkSession

    spark = SparkSession.builder.getOrCreate()
    # The brief for each account is the most recent one written, whatever prompt version produced it.
    rows = spark.sql(f"""
        SELECT p.loan_account_id, p.region, p.branch_id, p.product_code, p.snapshot_month, p.dpd_days,
               p.dpd_bucket, p.outstanding_principal, p.priority_score, p.priority_rank,
               to_json(p.drivers) AS drivers, to_json(p.conduct_flags) AS conduct_flags,
               p.recommended_treatment, b.explanation AS ai_explanation,
               b.recommended_action AS ai_recommended_action, b.prompt_version AS ai_prompt_version
        FROM {fq}.collections_priority p
        -- Only a brief written from THIS month-end's facts; an older brief would explain last month.
        LEFT JOIN (SELECT * FROM {fq}.collections_case_brief WHERE error IS NULL
                   QUALIFY row_number() OVER (PARTITION BY loan_account_id, snapshot_month ORDER BY briefed_at DESC) = 1) b
          ON b.loan_account_id = p.loan_account_id AND b.snapshot_month = p.snapshot_month""").collect()

    w = WorkspaceClient()
    host = w.postgres.get_endpoint(name=a.endpoint).status.hosts.host
    token = w.postgres.generate_database_credential(endpoint=a.endpoint).token
    user = w.current_user.me().user_name

    cols = ["loan_account_id", *MACHINE_COLUMNS]
    upsert = sql.SQL("""
        INSERT INTO collections_cases ({cols}, on_worklist, refreshed_at)
        VALUES ({vals}, TRUE, now())
        ON CONFLICT (loan_account_id) DO UPDATE SET {sets}, on_worklist = TRUE, refreshed_at = now()
        """).format(
        cols=sql.SQL(", ").join(map(sql.Identifier, cols)),
        vals=sql.SQL(", ").join(sql.Placeholder() * len(cols)),
        sets=sql.SQL(", ").join(sql.SQL("{c} = EXCLUDED.{c}").format(c=sql.Identifier(c)) for c in MACHINE_COLUMNS))

    with psycopg.connect(host=host, port=5432, dbname=a.dbname, user=user, password=token,
                         sslmode="require") as conn:
        with conn.cursor() as cur:
            cur.execute(sql.SQL("SET LOCAL search_path TO {}").format(sql.Identifier(a.pg_schema)))
            cur.execute("SELECT set_config('ct.change_source', 'pipeline_sync', true), "
                        "set_config('ct.changed_by', %s, true)", (f"sync_cases ({user})",))
            cur.execute("SELECT count(*) FROM collections_cases")
            before = cur.fetchone()[0]
            cur.executemany(upsert, [tuple(r[c] for c in cols) for r in rows])
            ids = [r["loan_account_id"] for r in rows]
            cur.execute("UPDATE collections_cases SET on_worklist = FALSE "
                        "WHERE on_worklist AND NOT (loan_account_id = ANY(%s))", (ids,))
            left = cur.rowcount
            cur.execute("SELECT count(*), count(*) FILTER (WHERE on_worklist), "
                        "count(*) FILTER (WHERE status <> 'new') FROM collections_cases")
            total, active, worked = cur.fetchone()
            cur.execute("""SELECT c.case_id, c.loan_account_id, c.region, c.status, c.next_action_date, c.updated_at,
                                  c.on_worklist, c.refreshed_at,
                                  (SELECT count(*) FROM actions a WHERE a.case_id = c.case_id
                                     AND a.status IN ('proposed', 'approved', 'escalated')) AS open_actions,
                                  (SELECT count(*) FROM case_history h WHERE h.case_id = c.case_id
                                     AND h.change_source = 'app') AS officer_changes
                           FROM collections_cases c""")
            status_rows = cur.fetchall()
    publish_case_status(spark, fq, status_rows)
    print(json.dumps({"gold_rows": len(rows), "cases_before": before, "cases_after": total,
                      "on_worklist": active, "left_worklist": left, "cases_worked_by_people": worked}))


def publish_case_status(spark, fq: str, rows: list[tuple]) -> None:
    """Publish what officers have done with each case back to Unity Catalog.

    Lakebase is where people work the cases; Unity Catalog is where the bank asks questions. Without this
    the Genie agents and the CRO's overview could see the worklist but not the work: how many accounts
    have a promise to pay, how many are on hold, how many have an action waiting for approval. Only the
    status columns are published, not the officers' notes or names. The table carries the same region row
    filter as the worklist, and INSERT OVERWRITE keeps the filter in place.
    """
    spark.sql(f"""CREATE TABLE IF NOT EXISTS {fq}.collections_case_status (
        case_id BIGINT COMMENT 'Case id in the Lakebase case queue.',
        loan_account_id STRING COMMENT 'Loan account. Join to collections_priority or loan_accounts.',
        region STRING COMMENT 'Region of the account.',
        status STRING COMMENT 'Status an officer set: new, in_progress, promise_to_pay, on_hold, resolved or closed.',
        next_action_date DATE COMMENT 'Next action date an officer set, if any.',
        last_officer_update TIMESTAMP COMMENT 'When an officer last changed the case. NULL if no officer has touched it.',
        on_worklist BOOLEAN COMMENT 'TRUE while the account is still delinquent and on the worklist.',
        refreshed_at TIMESTAMP COMMENT 'When the pipeline last refreshed the case.',
        open_actions BIGINT COMMENT 'Actions on this case proposed, approved or escalated and not yet closed.',
        officer_changes BIGINT COMMENT 'Number of changes officers have made to this case in the app.')
      WITH ROW FILTER {fq}.region_visible ON (region)
      COMMENT 'What the collections team has done with each worklist case, published from the Lakebase case queue every cycle. Use it for questions about work in progress: promises to pay, holds, cases nobody has touched, actions awaiting approval.'""")
    df = spark.createDataFrame(rows, schema="case_id BIGINT, loan_account_id STRING, region STRING, status STRING, "
                               "next_action_date DATE, last_officer_update TIMESTAMP, on_worklist BOOLEAN, "
                               "refreshed_at TIMESTAMP, open_actions BIGINT, officer_changes BIGINT")
    df.createOrReplaceTempView("case_status_snapshot")
    spark.sql(f"INSERT OVERWRITE {fq}.collections_case_status SELECT * FROM case_status_snapshot")
    print(json.dumps({"published_case_status_rows": len(rows)}))


if __name__ == "__main__":
    # Not sys.exit(main()): serverless job tasks report SystemExit(0) as a failure.
    main()
