"""Run the same governed queries as whoever this job runs as, and print what came back.

One job per persona runs this with run_as set to that persona's service principal, so the evidence
shows the row filters and column masks applied by Unity Catalog to a real identity, not a simulation.
Results are printed (one JSON line, prefixed PROBE_RESULT) rather than written to a table, so the
personas need no write access anywhere.
"""
from __future__ import annotations

import argparse
import json

PROBES = {
    "who_am_i": "SELECT current_user() AS principal",
    "worklist_by_region": """SELECT region, count(*) AS accounts, round(sum(outstanding_principal)) AS outstanding_inr
                             FROM {fq}.collections_priority GROUP BY region ORDER BY region""",
    "loan_book_rows": "SELECT count(*) AS rows FROM {fq}.loan_accounts",
    "customer_ids_sample": """SELECT loan_account_id, customer_id FROM {fq}.loan_accounts
                              WHERE loan_account_id IN ('LN000001', 'LN000004', 'LN000011') ORDER BY 1""",
    "agent_names_sample": "SELECT agent_id, agent_name FROM {fq}.recovery_agents WHERE agent_id IN ('AG001','AG006') ORDER BY 1",
    "complaint_text_sample": """SELECT complaint_id, region, left(complaint_text, 70) AS complaint_text
                                FROM {fq}.complaints WHERE category_code = 'REC' ORDER BY complaint_id LIMIT 2""",
    "letter_text_sample": """SELECT complaint_id, region, left(regexp_replace(document_text, '\\\\s+', ' '), 70) AS text_start
                             FROM {fq}.complaint_documents WHERE document_type = 'customer_letter'
                             ORDER BY complaint_id LIMIT 2""",
    "reference_docs_visible": """SELECT count(*) AS reference_documents FROM {fq}.complaint_documents
                                 WHERE document_type <> 'customer_letter'""",
    "guardrail_visibility": "SELECT {fq}.guardrail_visibility() AS visible",
    # Raw layers carry identifiers and letter text with no filter or mask; no persona may read them.
    "bronze_complaints_access": "SELECT count(*) AS rows FROM {fq}.bronze_complaints",
    "quarantine_access": "SELECT count(*) AS rows FROM {fq}.quarantine_collections_activity",
}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--catalog", required=True)
    ap.add_argument("--schema", required=True)
    ap.add_argument("--persona", required=True)
    a = ap.parse_args()
    from pyspark.sql import SparkSession
    spark = SparkSession.builder.getOrCreate()
    fq = f"{a.catalog}.{a.schema}"
    out = {"persona": a.persona, "probes": {}}
    for name, q in PROBES.items():
        try:
            rows = spark.sql(q.format(fq=fq)).collect()
            out["probes"][name] = [{k: str(v) for k, v in r.asDict().items()} for r in rows]
        except Exception as e:
            # A refusal is a result: record it rather than fail the probe.
            out["probes"][name] = [{"refused": str(e).splitlines()[0][:160]}]
    print("PROBE_RESULT " + json.dumps(out))


if __name__ == "__main__":
    main()
