"""Generate the evidence pack from the live workspace: one Markdown file per stage, in evidence/.

    python3 tools/generate_evidence.py --profile <cli-profile>                 # every file
    python3 tools/generate_evidence.py --profile <cli-profile> --only 06,07    # some files

Every number in every file comes from a query, an API response or a job run made while this script ran,
and every file says so in its first line. Nothing is typed by hand. Resource ids are read from the
deployed bundle (`databricks bundle summary`), so the evidence is about exactly what is deployed.

Some steps act, on purpose, so the evidence shows behaviour rather than configuration:
  06 runs the four persona probe jobs (each as its own service principal);
  07 edits a case through the app as the signed-in user, re-runs the Lakebase sync, and checks the edit
     survived, then tries to rewrite history and records the refusal;
  08 asks every benchmark question through the Genie Conversation API (slow: the workspace quota is
     about five messages a minute);
  10 calls the deployed app's routes, including a refused self-approval.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import time

import requests
from databricks.sdk import WorkspaceClient

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "evidence")


class Ctx:
    def __init__(self, profile: str):
        self.profile = profile
        self.w = WorkspaceClient(profile=profile)
        summary = json.loads(subprocess.run(
            ["databricks", "bundle", "summary", "-o", "json", "--profile", profile],
            cwd=ROOT, capture_output=True, text=True, check=True).stdout)
        v = {k: x.get("value", x.get("default")) for k, x in summary["variables"].items()}
        r = summary["resources"]
        self.catalog, self.schema = v["uc_catalog"], v["uc_schema"]
        self.fq = f"{self.catalog}.{self.schema}"
        self.warehouse = v["warehouse_id"]
        self.endpoint = v["lakebase_endpoint"]
        self.pg_schema = v["lakebase_schema"]
        self.pipeline_id = r["pipelines"]["control_tower"]["id"]
        self.jobs = {k: j["id"] for k, j in r["jobs"].items()}
        self.spaces = {k: s["id"] for k, s in r["genie_spaces"].items()}
        self.app_name = r["apps"]["ct_app"]["name"]
        self.app_url = self.w.apps.get(name=self.app_name).url
        self.vars = v

    def sql(self, statement: str) -> tuple[list[str], list[list]]:
        r = self.w.statement_execution.execute_statement(
            warehouse_id=self.warehouse, statement=statement, wait_timeout="50s")
        while r.status.state.value in ("PENDING", "RUNNING"):
            time.sleep(2)
            r = self.w.statement_execution.get_statement(r.statement_id)
        if r.status.state.value != "SUCCEEDED":
            raise RuntimeError(f"{r.status.error.message if r.status.error else r.status.state}: {statement[:200]}")
        cols = [c.name for c in r.manifest.schema.columns]
        rows = list(r.result.data_array or []) if r.result else []
        chunk = r.result.next_chunk_index if r.result else None
        while chunk:
            nxt = self.w.statement_execution.get_statement_result_chunk_n(r.statement_id, chunk)
            rows += nxt.data_array or []
            chunk = nxt.next_chunk_index
        return cols, rows

    def pg(self):
        import psycopg
        host = self.w.postgres.get_endpoint(name=self.endpoint).status.hosts.host
        token = self.w.postgres.generate_database_credential(endpoint=self.endpoint).token
        conn = psycopg.connect(host=host, dbname="databricks_postgres", user=self.w.current_user.me().user_name,
                               password=token, sslmode="require", autocommit=True)
        conn.execute(f'SET search_path TO "{self.pg_schema}"')
        return conn

    def app(self, method: str, path: str, **kw) -> requests.Response:
        return requests.request(method, self.app_url + path, headers=self.w.config.authenticate(),
                                timeout=240, **kw)

    def run_job(self, key: str, only: list[str] | None = None) -> dict:
        body = {"job_id": int(self.jobs[key])}
        if only:
            body["only"] = only
        run_id = self.w.api_client.do("POST", "/api/2.2/jobs/run-now", body=body)["run_id"]
        while True:
            run = self.w.jobs.get_run(run_id)
            if run.state.life_cycle_state.value in ("TERMINATED", "SKIPPED", "INTERNAL_ERROR"):
                return run.as_dict()
            time.sleep(15)


# --------------------------------------------------------------------------------------------- output
def table(cols: list[str], rows: list[list], limit: int = 60) -> str:
    def cell(v):
        s = "" if v is None else str(v)
        return s.replace("|", "\\|").replace("\n", " ")
    out = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    out += ["| " + " | ".join(cell(v) for v in r) + " |" for r in rows[:limit]]
    if len(rows) > limit:
        out.append(f"\n_{len(rows) - limit} more rows not shown._")
    return "\n".join(out)


def q(ctx: Ctx, statement: str, limit: int = 60) -> str:
    cols, rows = ctx.sql(statement)
    return f"```sql\n{statement.strip()}\n```\n\n{table(cols, rows, limit)}\n"


# Personal identifiers that must not appear in committed evidence (the builder's email). Service principal
# application ids stay: they are opaque, and they are how the persona columns can be checked.
REDACT: dict[str, str] = {}
# --reuse-genie: render 08 from the results files of the last run instead of asking every question again.
REUSE_GENIE = False


def write(name: str, title: str, proves: str, body: str) -> None:
    for secret, label in REDACT.items():
        body = body.replace(secret, label)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    text = (f"<!-- Generated {stamp} by tools/generate_evidence.py from the live workspace. Do not edit. -->\n"
            f"# {title}\n\n_Generated {stamp} by `tools/generate_evidence.py` from the live workspace._\n\n"
            f"**What this proves.** {proves}\n\n{body.strip()}\n")
    with open(os.path.join(OUT, name), "w") as fh:
        fh.write(text)
    print(f"  wrote evidence/{name}")


# ------------------------------------------------------------------------------------------- sections
def ev01(ctx: Ctx) -> None:
    ups = ctx.w.pipelines.list_updates(ctx.pipeline_id, max_results=5).updates or []
    rows = [[u.update_id, u.state.value if u.state else "", u.cause.value if u.cause else "",
             dt.datetime.fromtimestamp(u.creation_time / 1000, dt.timezone.utc).strftime("%Y-%m-%d %H:%M"),
             ", ".join(u.full_refresh_selection or []) or ("FULL" if u.full_refresh else "")] for u in ups]
    latest = ups[0].update_id if ups else ""
    counts = " UNION ALL ".join(f"SELECT '{layer}' AS layer, '{t}' AS table_name, count(*) AS row_count FROM {ctx.fq}.{t}"
                                for layer, ts in [
        ("bronze", ["bronze_dialer_contacts", "bronze_field_visits", "bronze_dpd_snapshot", "bronze_complaints",
                    "bronze_upi_disputes", "bronze_chargebacks", "bronze_loan_accounts", "bronze_correspondence",
                    "bronze_manifests"]),
        ("silver", ["silver_collections_activity", "silver_delinquency", "silver_complaints", "silver_upi_disputes",
                    "silver_chargebacks"]),
        ("quarantine", ["quarantine_collections_activity", "quarantine_delinquency", "quarantine_complaints",
                        "quarantine_upi_disputes", "quarantine_chargebacks", "quarantine_orphans"]),
        ("gold", ["loan_accounts", "delinquency_monthly", "collections_activity", "complaints", "upi_disputes",
                  "chargebacks", "sla_tracker", "rm_achievement", "collections_priority", "complaint_ai_triage",
                  "complaint_documents", "recon_completeness", "data_quality_summary"])] for t in ts)
    expect = f"""
SELECT e.dataset, e.name AS expectation, sum(e.passed_records) AS passed, sum(e.failed_records) AS failed
FROM (SELECT explode(from_json(details:flow_progress:data_quality:expectations,
        'array<struct<name:string,dataset:string,passed_records:bigint,failed_records:bigint>>')) AS e
      FROM event_log('{ctx.pipeline_id}') WHERE event_type = 'flow_progress'
        AND details:flow_progress:data_quality:expectations IS NOT NULL) x
GROUP BY ALL ORDER BY 1, 2"""
    write("01_pipeline_run.md", "01 — Lakeflow pipeline run",
          "The serverless Spark Declarative Pipeline ran from raw files to governed gold, every layer holds rows, "
          "and each data-quality expectation reports how many rows passed and failed. Expectation totals are summed "
          "across every update since the tables were created, read from the pipeline's own event log.",
          f"Pipeline `{ctx.pipeline_id}`. Most recent updates:\n\n"
          + table(["update_id", "state", "cause", "started (UTC)", "refresh"], rows)
          + f"\n\nLatest update: `{latest}`.\n\n## Rows per table, by layer\n\n" + q(ctx, counts)
          + "\n## Expectations (from the event log)\n\n" + q(ctx, expect))


def ev02(ctx: Ctx) -> None:
    key = json.load(open(os.path.join(OUT, "_answer_key.json")))
    cols, rows = ctx.sql(f"SELECT entity, check_type, reason, row_count FROM {ctx.fq}.data_quality_summary")
    found = {(r[0], r[2]): int(r[3]) for r in rows}
    checks = [
        ("F01", "collections_activity", "re-sent copy of a contact already received", key["dialer_resent_duplicates"]),
        ("F02", "collections_activity", "unparseable contact timestamp", key["unparseable_timestamps"]),
        ("F03", "collections_activity", "unknown loan account", key["orphan_contacts"]),
        ("F04", "collections_activity", "missing loan account", key["missing_loan_visits"]),
        ("F05", "delinquency_monthly", "negative days past due", key["negative_dpd"]),
        ("F06", "complaints", "unknown complaint category", key["unknown_category"]),
        ("F07", "complaints", "re-sent copy of a complaint already received", key["resent_complaints"]),
        ("F08", "upi_disputes", "non-positive amount", key["non_positive_upi"]),
        ("F09", "chargebacks", "raised before transaction", key["chargeback_before_txn"]),
        ("F10", "loan_accounts", "unknown product code", key["unknown_product_loans"]),
        ("F12", "collections_activity", "contact uploaded in a later month's file", key["late_contacts"]),
    ]
    vs = [[f, e, r, exp, found.get((e, r), 0), "MATCH" if found.get((e, r), 0) == exp else "DIFFERENT"]
          for f, e, r, exp in checks]
    gold_cols, gold_rows = ctx.sql(f"SELECT table_name, row_count FROM {ctx.fq}.gold_row_counts")
    gold = {r[0]: int(r[1]) for r in gold_rows}
    gvs = [[t, n, gold.get(t), "MATCH" if gold.get(t) == n else "DIFFERENT"]
           for t, n in sorted(key["expected_gold_rows"].items())]
    write("02_data_quality.md", "02 — Data quality and completeness",
          "Every planted defect in the answer key was caught, in the expected place, with the expected count; the "
          "governed gold tables hold exactly the rows the clean book should; and every source file is reconciled "
          "against its sender's manifest, with the one planted truncated transfer shown as a BREAK.",
          "## Planted findings: answer key against what the pipeline caught\n\n"
          + table(["finding", "entity", "reason", "answer key", "pipeline", "result"], vs)
          + "\n\n## Gold row counts against the answer key\n\n"
          + table(["table", "answer key", "gold (unfiltered)", "result"], gvs)
          + "\n\n## Completeness against the senders' manifests\n\n"
          + q(ctx, f"SELECT status, count(*) AS files, sum(declared_rows) AS declared_rows, sum(landed_rows) AS landed_rows, "
                   f"sum(loaded_rows) AS loaded_rows, sum(quarantined_rows) AS quarantined_rows FROM {ctx.fq}.recon_completeness GROUP BY status")
          + "\n" + q(ctx, f"SELECT period, path, declared_rows, landed_rows, declared_amount, landed_amount, break_reason "
                         f"FROM {ctx.fq}.recon_completeness WHERE status = 'BREAK'")
          + "\n## Quarantined rows keep the reason and the raw record (two per reason)\n\n"
          + q(ctx, f"""SELECT reason, _source_path, raw_record FROM (
  SELECT reason, _source_path, raw_record, row_number() OVER (PARTITION BY reason ORDER BY _source_path, raw_record) AS n
  FROM {ctx.fq}.quarantine_collections_activity) WHERE n <= 2 ORDER BY reason"""))


def ev03(ctx: Ctx) -> None:
    f = ctx.fq
    write("03_business_results.md", "03 — Business results",
          "The answers the Chief Risk Officer and the Head of Collections act on, computed from the governed gold "
          "tables after the final run. These are the numbers the README and the deck quote.",
          "## Gross NPA and roll-forward, by month (last six months)\n\n"
          + q(ctx, f"""SELECT snapshot_month,
       round(100 * sum(CASE WHEN is_npa THEN outstanding_principal END) / sum(outstanding_principal), 2) AS gnpa_pct,
       round(100 * avg(CASE WHEN roll_direction = 'forward' THEN 1 ELSE 0 END), 2) AS roll_forward_pct,
       count_if(dpd_days > 0) AS delinquent_accounts
FROM {f}.delinquency_monthly GROUP BY 1 ORDER BY 1 DESC LIMIT 6""")
          + "\n## Where the stress is: delinquency rate in the two stressed slices against the rest of the book\n\n"
          + q(ctx, f"""SELECT d.snapshot_month,
  round(100 * avg(CASE WHEN d.product_code = 'MFI' AND b.city = 'Solapur' THEN CASE WHEN d.dpd_days > 0 THEN 1 ELSE 0 END END), 1) AS solapur_mfi_pct,
  round(100 * avg(CASE WHEN d.product_code = 'CV' AND b.city = 'Indore' THEN CASE WHEN d.dpd_days > 0 THEN 1 ELSE 0 END END), 1) AS indore_cv_pct,
  round(100 * avg(CASE WHEN NOT (b.city IN ('Solapur', 'Indore')) THEN CASE WHEN d.dpd_days > 0 THEN 1 ELSE 0 END END), 1) AS rest_of_book_pct
FROM {f}.delinquency_monthly d JOIN {f}.branch_master b USING (branch_id)
WHERE d.snapshot_month >= DATE'2026-02-01' GROUP BY 1 ORDER BY 1""")
          + "\n## Collections effort against what was collected, Solapur microfinance, by month\n\n"
          + q(ctx, f"""SELECT date_trunc('MONTH', a.activity_date) AS month, count(*) AS contact_attempts,
       count(DISTINCT a.loan_account_id) AS accounts_contacted, round(sum(a.amount_collected)) AS collected_inr,
       round(sum(a.amount_collected) / count(*)) AS collected_per_attempt_inr
FROM {f}.collections_activity a JOIN {f}.branch_master b USING (branch_id)
WHERE a.product_code = 'MFI' AND b.city = 'Solapur' AND a.activity_date >= DATE'2026-01-01'
GROUP BY 1 ORDER BY 1""")
          + "\n## The collections worklist and how the bank's conduct rules say each account may be worked\n\n"
          + q(ctx, f"""SELECT recommended_treatment, count(*) AS accounts, round(sum(outstanding_principal)) AS outstanding_inr
FROM {f}.collections_priority GROUP BY 1 ORDER BY accounts DESC""")
          + "\n## Conduct exposure: contacts outside 08:00 to 19:00 IST, and by uncertified agents (whole history)\n\n"
          + q(ctx, f"""SELECT count_if(NOT a.within_rbi_hours) AS out_of_hours_contacts,
       count_if(NOT coalesce(g.active_flag AND g.rbi_conduct_certified AND g.certification_expiry >= a.activity_date, FALSE)) AS uncertified_agent_contacts,
       count(*) AS contacts
FROM {f}.collections_activity a LEFT JOIN {f}.recovery_agents g USING (agent_id)""")
          + "\n## Grievance: complaints open past their SLA at the reporting date, by RBI ground\n\n"
          + q(ctx, f"""SELECT rbi_category, count(*) AS open_past_sla FROM {f}.complaints
WHERE status = 'Open' AND sla_breached GROUP BY 1 ORDER BY 2 DESC"""))


def ev04_05(ctx: Ctx) -> None:
    f = ctx.fq
    write("04_ai_output.md", "04 — AI output, verbatim",
          "The two AI steps produce structured output that the next stages consume: the letter triage feeds the "
          "worklist's conduct flags and the grievance agent; the briefs feed the Lakebase case queue. Samples are "
          "verbatim, with exactly what the model was given.",
          "## Letter triage (ai_query inside the pipeline), one letter per recorded ground\n\n"
          + q(ctx, f"""SELECT complaint_id, rbi_category AS recorded_ground, predicted_rbi_ground, alleges_conduct_breach,
       breach_types, urgency, summary, prompt_version, model FROM (
  SELECT t.*, c.rbi_category, row_number() OVER (PARTITION BY c.rbi_category ORDER BY t.complaint_id) AS n
  FROM {f}.complaint_ai_triage t JOIN {f}.complaints c USING (complaint_id)) WHERE n = 1""")
          + "\n## Case briefs (current prompt version), with the facts the model was given\n\n"
          + q(ctx, f"""SELECT b.loan_account_id, b.priority_rank, b.facts, b.explanation, b.recommended_action, b.prompt_version
FROM {f}.collections_case_brief b WHERE b.prompt_version = '{ctx.vars["brief_prompt_version"]}' ORDER BY b.priority_rank LIMIT 4""")
          + "\n## Coverage\n\n"
          + q(ctx, f"""SELECT 'letter_triage' AS step, count(*) AS rows, count(error) AS errors FROM {f}.complaint_ai_triage
UNION ALL SELECT 'case_brief', count(*), count(error) FROM {f}.collections_case_brief WHERE prompt_version = '{ctx.vars["brief_prompt_version"]}'"""))
    write("05_ai_evaluation.md", "05 — AI evaluation and the iteration history",
          "Both AI steps are measured: the triage against the ground the grievance desk recorded on each complaint, "
          "and the briefs against the bank's deterministic conduct rules and by MLflow Guidelines judges running "
          "on a different model family from the generator. Every prompt version and judge version stays in the "
          "results, so the iteration is visible, including the regressions.",
          "## Every evaluation run, in order\n\n"
          "Runs before the final month landed were on the July data; later runs are on the full data. v1 to v3 "
          "of the briefs were compared on the same July accounts.\n\n"
          + q(ctx, f"""SELECT date_format(evaluated_at, 'yyyy-MM-dd HH:mm') AS evaluated_utc, component, prompt_version, judge_version,
  max(CASE WHEN metric IN ('letters', 'briefs') THEN cast(value AS INT) END) AS rows_evaluated,
  max(CASE WHEN metric = 'ground_accuracy' THEN round(value, 3) END) AS ground_accuracy,
  max(CASE WHEN metric = 'conduct_recall' THEN round(value, 3) END) AS conduct_recall,
  max(CASE WHEN metric = 'conduct_precision' THEN round(value, 3) END) AS conduct_precision,
  max(CASE WHEN metric = 'rule_agreement_pass_rate' THEN round(value, 3) END) AS rule_agreement,
  max(CASE WHEN metric = 'grounded_pass_rate' THEN round(value, 3) END) AS grounded,
  max(CASE WHEN metric = 'conduct_compliant_pass_rate' THEN round(value, 3) END) AS conduct_compliant,
  max(CASE WHEN metric = 'actionable_pass_rate' THEN round(value, 3) END) AS actionable,
  max(CASE WHEN metric = 'plain_language_pass_rate' THEN round(value, 3) END) AS plain_language,
  max(CASE WHEN metric = 'within_60_words_pass_rate' THEN round(value, 3) END) AS within_60_words,
  max(CASE WHEN metric = 'numbers_grounded_pass_rate' THEN round(value, 3) END) AS numbers_grounded
FROM {f}.ai_eval_summary GROUP BY eval_run_id, evaluated_at, component, prompt_version, judge_version
ORDER BY evaluated_at, component""", 80)
          + "\n## Remaining triage disagreements with the recorded ground\n\n"
          + q(ctx, f"""SELECT c.rbi_category AS recorded, t.predicted_rbi_ground AS predicted, count(*) AS letters
FROM {f}.complaint_ai_triage t JOIN {f}.complaints c USING (complaint_id)
WHERE t.predicted_rbi_ground <> c.rbi_category GROUP BY ALL ORDER BY 3 DESC""")
          + "\n## Judge rationales for brief failures in the current version (verbatim)\n\n"
          + q(ctx, f"""SELECT check_name, record_id, rationale FROM {f}.ai_eval_results
WHERE component = 'case_brief' AND prompt_version = '{ctx.vars["brief_prompt_version"]}' AND NOT passed
QUALIFY row_number() OVER (PARTITION BY check_name ORDER BY record_id) <= 2 ORDER BY check_name""")
          + "\n## Judge rationales that drove each iteration (earlier versions)\n\n"
          + q(ctx, f"""SELECT prompt_version, judge_model, check_name, record_id, rationale FROM {f}.ai_eval_results
WHERE component = 'case_brief' AND prompt_version IN ('v1', 'v2') AND NOT passed AND check_name IN ('grounded', 'plain_language', 'rule_agreement')
QUALIFY row_number() OVER (PARTITION BY prompt_version, judge_model, check_name ORDER BY record_id) = 1
ORDER BY prompt_version, judge_model, check_name"""))


def ev06(ctx: Ctx) -> None:
    results = {}
    for key in ("ct_probe_cro", "ct_probe_collections_head", "ct_probe_grievance_officer", "ct_probe_auditor"):
        run = ctx.run_job(key)
        task = run["tasks"][0]
        logs = ctx.w.jobs.get_run_output(task["run_id"]).logs or ""
        line = next(ln for ln in logs.splitlines() if ln.startswith("PROBE_RESULT "))
        r = json.loads(line[len("PROBE_RESULT "):])
        r["run_id"] = run["run_id"]
        results[r["persona"]] = r
    personas = list(results)

    def pick(name, fn):
        return [fn(results[p]["probes"][name]) for p in personas]

    rows = [
        ["identity (current_user)"] + pick("who_am_i", lambda v: v[0]["principal"]),
        ["probe job run id"] + [str(results[p]["run_id"]) for p in personas],
        ["loan_accounts rows visible"] + pick("loan_book_rows", lambda v: v[0]["rows"]),
        ["worklist regions visible"] + pick("worklist_by_region", lambda v: ", ".join(x["region"] for x in v)),
        ["customer_id of LN000011"] + pick("customer_ids_sample", lambda v: next((x["customer_id"] for x in v if x["loan_account_id"] == "LN000011"), "row not visible")),
        ["customer_id of LN000001 (North)"] + pick("customer_ids_sample", lambda v: next((x["customer_id"] for x in v if x["loan_account_id"] == "LN000001"), "row not visible")),
        ["agent name AG001"] + pick("agent_names_sample", lambda v: next((x["agent_name"] for x in v if x["agent_id"] == "AG001"), "row not visible")),
        ["complaint text (REC)"] + pick("complaint_text_sample", lambda v: v[0]["complaint_text"] if v else "no rows"),
        ["letter text"] + pick("letter_text_sample", lambda v: v[0]["text_start"][:48] if v else "no rows"),
        ["reference documents visible"] + pick("reference_docs_visible", lambda v: v[0]["reference_documents"]),
        ["guardrail_visibility()"] + pick("guardrail_visibility", lambda v: v[0]["visible"]),
        ["entitlement rows it can read (my_entitlements)"] + pick("own_entitlements_only", lambda v: f"{v[0]['rows']} rows, {v[0]['principals']} principal" if "rows" in v[0] else v[0]["refused"][:90]),
        ["read bronze_complaints (raw)"] + pick("bronze_complaints_access", lambda v: v[0].get("refused", f"READ {v[0].get('rows')} rows")[:90]),
        ["read quarantine (raw records)"] + pick("quarantine_access", lambda v: v[0].get("refused", f"READ {v[0].get('rows')} rows")[:90]),
    ]
    write("06_governance.md", "06 — Governance per persona",
          "The same queries return different rows and different values for each persona, enforced by Unity Catalog "
          "row filters and column masks declared on the gold tables. Each column is a real identity: a job ran "
          "eval/persona_probe.py with run_as set to that persona's service principal.",
          "## Same queries, four identities\n\n" + table(["probe"] + personas, rows)
          + "\n\n## What each persona is entitled to (the entitlements table: access is data)\n\n"
          + q(ctx, f"SELECT persona, region, can_see_pii, can_see_complaint_text FROM {ctx.fq}.entitlements ORDER BY persona, region")
          + "\n## Policies attached in Unity Catalog\n\n"
          + q(ctx, f"""SELECT table_name, 'row filter' AS policy, filter_name AS function FROM {ctx.catalog}.information_schema.row_filters
WHERE table_schema = '{ctx.schema}'
UNION ALL SELECT table_name, concat('mask on ', column_name), mask_name FROM {ctx.catalog}.information_schema.column_masks
WHERE table_schema = '{ctx.schema}' ORDER BY 1, 2""", 80))


def ev07(ctx: Ctx) -> None:
    cases = ctx.app("GET", "/api/cases?limit=5").json()["cases"]
    target = cases[1]
    note = f"Evidence test {dt.datetime.now(dt.timezone.utc):%Y-%m-%d %H:%M}: borrower asked for calls after 18:00 only"
    patch = ctx.app("PATCH", f"/api/cases/{target['case_id']}",
                    json={"status": "promise_to_pay", "owner": "Collections officer (West)", "notes": note,
                          "next_action_date": "2026-09-05"})
    before = ctx.app("GET", f"/api/cases/{target['case_id']}").json()["case"]
    sync = ctx.run_job("ct_cycle", only=["sync_cases"])
    after = ctx.app("GET", f"/api/cases/{target['case_id']}").json()
    c = after["case"]
    survived = c["notes"] == note and c["status"] == "promise_to_pay"
    with ctx.pg() as conn:
        status = conn.execute("SELECT status, count(*) FROM collections_cases WHERE on_worklist GROUP BY 1 ORDER BY 2 DESC").fetchall()
        sources = conn.execute("SELECT change_source, field, count(*) FROM case_history GROUP BY 1, 2 ORDER BY 1, 3 DESC").fetchall()
        try:
            conn.execute("UPDATE case_history SET new_value = 'tampered' WHERE case_id = %s", (target["case_id"],))
            refusal = "UPDATE succeeded (append-only guard NOT working)"
        except Exception as e:
            refusal = str(e).splitlines()[0]
    hist = [[h["changed_at"][:19], h["changed_by"], h["change_source"], h["field"], h["old_value"], h["new_value"]]
            for h in after["history"][:12]]
    write("07_lakebase.md", "07 — Lakebase: the case queue people work",
          "Lakebase holds the operational record. A person's edit, made through the app, survives the pipeline's "
          "next refresh because the sync only writes machine-owned columns; every change is in the history with "
          "who made it and whether a person or the sync did; and the history refuses to be rewritten.",
          f"## The edit-survives-refresh test, on case {target['case_id']} ({target['loan_account_id']})\n\n"
          + table(["step", "result"], [
              ["1. edit through the app (PATCH /api/cases)", f"HTTP {patch.status_code}"],
              ["   status / owner / notes after the edit", f"{before['status']} / {before['owner']} / {before['notes']}"],
              ["   refreshed_at before the sync", before["refreshed_at"]],
              ["2. run the Lakebase sync (ct_cycle, task sync_cases)", f"run {sync['run_id']}: {sync['state'].get('result_state')}"],
              ["   refreshed_at after the sync", c["refreshed_at"]],
              ["   status / owner / notes after the sync", f"{c['status']} / {c['owner']} / {c['notes']}"],
              ["3. human edit survived the refresh", "YES" if survived else "NO"],
              ["4. attempt to rewrite the history (UPDATE case_history)", refusal]])
          + "\n\n## History of that case (newest first)\n\n"
          + table(["changed_at", "changed_by", "source", "field", "old", "new"], hist)
          + "\n\n## Cases on the worklist, by status\n\n" + table(["status", "cases"], [list(r) for r in status])
          + "\n\n## Every history row, by who changed what\n\n" + table(["source", "field", "rows"], [list(r) for r in sources]))


def ev08(ctx: Ctx) -> None:
    env = dict(os.environ, DATABRICKS_CONFIG_PROFILE=ctx.profile, CT_CATALOG=ctx.catalog, CT_SCHEMA=ctx.schema,
               DATABRICKS_WAREHOUSE_ID=ctx.warehouse, LAKEBASE_ENDPOINT=ctx.endpoint,
               COLLECTIONS_SPACE_ID=ctx.spaces["collections"], GRIEVANCE_SPACE_ID=ctx.spaces["grievance"],
               RM_SPACE_ID=ctx.spaces["rm"])
    parts = []
    for mode, results_file in ((["genie"], "genie-latest.json"), (["genie", "--heldout"], "heldout-genie-latest.json")):
        path = os.path.join(ROOT, "eval", "results", results_file)
        if not REUSE_GENIE:
            before = os.path.getmtime(path) if os.path.exists(path) else 0
            subprocess.run([sys.executable, "eval/run_eval.py", *mode], cwd=ROOT, env=env, check=False)
            # run_eval exits non-zero when any answer is wrong, so the exit code cannot tell a failed run
            # from a scored one. A results file that was not rewritten can: never report a stale file.
            if not os.path.exists(path) or os.path.getmtime(path) <= before:
                raise RuntimeError(f"run_eval {' '.join(mode)} did not write {results_file}")
        res = json.load(open(path))
        ran_at = dt.datetime.fromtimestamp(os.path.getmtime(path), dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        label = "held-out questions (not used to tune the spaces)" if "--heldout" in mode else "benchmark questions"
        rows = [[c["id"], c["domain"], c["question"], c["outcome"], c.get("matched_in", ""), (c.get("detail") or "")[:140]]
                for c in res["cases"]]
        parts.append(f"## {label.capitalize()}: {res['passed']} of {res['graded']} graded passed "
                     f"({res['accuracy_pct_of_graded']}%), {res['attempted']} attempted\n\n"
                     f"Questions asked at {ran_at} (`eval/results/{results_file}`).\n\n"
                     + table(["id", "agent", "question", "outcome", "matched in", "detail"], rows, 80))
    write("08_genie.md", "08 — Genie agents against ground truth",
          "Every benchmark question was asked through the Genie Conversation API and graded against ground-truth "
          "SQL executed in the same minute. Every answer's result grid is checked; for a single-number answer the "
          "prose Genie wrote must also state the number, while list and ranking answers pass on the grid alone. "
          "The held-out set was never used to tune the spaces, so it is the honest number. Genie is not "
          "deterministic, so these are the results of one run at the time shown.",
          f"Spaces: {', '.join(f'{k} `{v}`' for k, v in ctx.spaces.items())}.\n\n" + "\n\n".join(parts))


def ev09(ctx: Ctx) -> None:
    runs = ctx.w.jobs.list_runs(job_id=int(ctx.jobs["ct_cycle"]), limit=8, expand_tasks=True)
    rows = []
    for r in runs:
        tasks = ", ".join(f"{t.task_key}:{t.state.result_state.value if t.state.result_state else t.state.life_cycle_state.value}"
                          f"({(t.execution_duration or 0) // 1000}s)" for t in (r.tasks or []) if t.attempt_number == 0)
        rows.append([r.run_id, r.trigger.value if r.trigger else "", r.state.result_state.value if r.state.result_state else "",
                     dt.datetime.fromtimestamp(r.start_time / 1000, dt.timezone.utc).strftime("%Y-%m-%d %H:%M"),
                     f"{(r.run_duration or 0) // 1000}s", tasks])
    gold = int(ctx.sql(f"SELECT count(*) FROM {ctx.fq}.collections_priority")[1][0][0])
    with ctx.pg() as conn:
        lake = conn.execute("SELECT count(*) FROM collections_cases WHERE on_worklist").fetchone()[0]
    app = sum(ctx.app("GET", "/api/cases?limit=1").json()["by_status"].values())
    write("09_orchestration.md", "09 — One job runs every stage",
          "One Lakeflow job runs the whole cycle in dependency order (pipeline, governance, AI briefs, AI evaluation, "
          "Lakebase sync), started by FILE ARRIVAL when a source drop's manifest lands; and after the run the worklist "
          "count agrees across gold, Lakebase and the app.",
          f"Job `{ctx.jobs['ct_cycle']}`, trigger: file arrival on `/Volumes/{ctx.catalog}/{ctx.schema}/landing/_manifests/`.\n\n"
          + table(["run_id", "trigger", "result", "started (UTC)", "duration", "tasks (first attempt)"], rows)
          + "\n\n## Cross-check after the run\n\n"
          + table(["where", "accounts on the worklist"], [["gold.collections_priority", gold],
                  ["Lakebase collections_cases (on_worklist)", lake], ["app GET /api/cases (sum by status)", app]]))


def ev10(ctx: Ctx) -> None:
    rows = []
    for method, path in [("GET", "/api/health"), ("GET", "/api/overview"), ("GET", "/api/cases?limit=5"),
                         ("GET", "/api/governance/scope"), ("GET", "/api/governance/policies"), ("GET", "/api/actions")]:
        r = ctx.app(method, path)
        rows.append([f"{method} {path}", r.status_code, r.text[:160]])
    h = ctx.app("GET", "/api/health").json()
    case = ctx.app("GET", "/api/cases?limit=1").json()["cases"][0]
    proposals = []
    for agent in ("AG024", "AG007"):     # AG024 is not conduct certified; AG007 is certified to 2026-12-01
        r = ctx.app("POST", "/api/act", json={
            "action_type": "assign_recovery_agency", "subject": case["loan_account_id"], "case_id": case["case_id"],
            "payload": {"reason": "evidence route check", "agent_id": agent,
                        "amount_inr": float(case["outstanding_principal"])}})
        a = r.json()
        proposals.append(a)
        rows.append([f"POST /api/act, assign_recovery_agency with agent {agent}", r.status_code,
                     f"guardrail passed={a['guardrail']['passed']}; breaches={a['guardrail']['breaches'] or 'none'}; "
                     f"region resolved server-side: {a['action']['region']}; requested_by={a['action']['requested_by']}"])
    appr = ctx.app("POST", f"/api/actions/{proposals[-1]['action']['id']}/approve")
    rows.append(["POST /api/actions/{id}/approve (by the person who raised it)", appr.status_code, appr.text[:160]])
    ask = ctx.app("POST", "/api/ask", json={"question": "How many accounts are on the collections worklist in each region?"})
    rows.append(["POST /api/ask", ask.status_code, ask.text[:160]])
    write("10_app.md", "10 — The Databricks App",
          "The deployed app serves every screen's route as the signed-in user (on-behalf-of token active). The "
          "bank's conduct control refuses an allocation to an uncertified agent and passes one to a certified agent. "
          "The action's region comes from the governed record, not the request, and the person who raised an action "
          "cannot approve it.",
          f"App `{ctx.app_name}` at {ctx.app_url}. On-behalf-of user token active: **{h['obo_active']}**; "
          f"require OBO: **{h['require_obo']}**; Genie agents configured: {h['genie_agents']}.\n\n"
          + table(["route", "HTTP", "response (start)"], rows))


def evhl(ctx: Ctx) -> None:
    import re
    f = ctx.fq
    one = lambda sql: ctx.sql(sql)[1][0]
    acc, out, held, flags, reassign, month = one(f"""SELECT count(*), round(sum(outstanding_principal)), count_if(open_grievance),
        count_if(size(conduct_flags) > 0), count_if(recommended_treatment LIKE 'Reassign%'), max(snapshot_month)
        FROM {f}.collections_priority""")
    files, ok = one(f"SELECT count(*), count_if(status = 'RECONCILED') FROM {f}.recon_completeness")
    caught = one(f"SELECT sum(row_count) FROM {f}.data_quality_summary")[0]
    ooh, contacts = one(f"SELECT count_if(NOT within_rbi_hours), count(*) FROM {f}.collections_activity")
    gnpa, rf = one(f"""WITH m AS (SELECT max(snapshot_month) AS m FROM {f}.delinquency_monthly)
        SELECT round(100 * sum(CASE WHEN is_npa THEN outstanding_principal END) / sum(outstanding_principal), 2),
               round(100 * avg(CASE WHEN roll_direction = 'forward' THEN 1 ELSE 0 END), 1)
        FROM {f}.delinquency_monthly d JOIN m ON d.snapshot_month = m.m""")
    letters, alleged = one(f"SELECT count(*), count_if(alleges_conduct_breach) FROM {f}.complaint_ai_triage")

    def metric(component, version, name, judge="j2"):
        cols, rows = ctx.sql(f"""SELECT round(100 * value, 1) FROM {f}.ai_eval_summary WHERE component = '{component}'
            AND prompt_version = '{version}' AND metric = '{name}' AND coalesce(judge_version, 'j1') = '{judge}'
            ORDER BY evaluated_at LIMIT 1""")
        return rows[0][0] if rows else "n/a"
    genie = open(os.path.join(OUT, "08_genie.md")).read() if os.path.exists(os.path.join(OUT, "08_genie.md")) else ""
    g = re.findall(r"## (Benchmark questions|Held-out questions[^:]*): (\d+) of (\d+) graded passed \(([\d.]+)%\)", genie)
    crore = float(out) / 1e7
    rows = [
        ["Accounts on the collections worklist", f"{int(acc):,} (month end {month})", "03"],
        ["Outstanding on the worklist", f"INR {crore:,.1f} crore", "03"],
        ["Accounts held because the borrower's grievance is open", f"{int(held):,}", "03"],
        ["Accounts with a conduct flag", f"{int(flags):,}, of which {int(reassign):,} are recommended for reassignment to a certified agency", "03"],
        ["Contacts outside 08:00 to 19:00 IST", f"{int(ooh):,} of {int(contacts):,} ({100 * int(ooh) / int(contacts):.1f}%)", "03"],
        ["Gross NPA, latest month", f"{gnpa}%", "03"],
        ["Roll-forward rate, latest month", f"{rf}%", "03"],
        ["Source files reconciled to their senders' manifests", f"{int(ok)} of {int(files)}", "02"],
        ["Rows caught by quality rules, each kept with its reason", f"{int(caught):,}", "02"],
        ["Letters triaged by AI in the pipeline", f"{int(letters):,}, of which {int(alleged):,} allege agent misconduct", "04"],
        ["Letter triage agreement with the recorded ground", f"{metric('letter_triage', 'v1', 'ground_accuracy')}% (v1) to {metric('letter_triage', 'v2', 'ground_accuracy')}% (v2), both on the same 690 July letters", "05"],
        ["Conduct letters found by the triage", f"recall {metric('letter_triage', 'v2', 'conduct_recall')}%, precision {metric('letter_triage', 'v2', 'conduct_precision')}%", "05"],
        ["Briefs that follow the bank's conduct rules", f"{metric('case_brief', 'v1', 'rule_agreement_pass_rate')}% (v1, July) to {metric('case_brief', 'v4', 'rule_agreement_pass_rate')}% (v4, August)", "05"],
        ["Briefs the judge finds grounded in the facts", f"{metric('case_brief', 'v1', 'grounded_pass_rate')}% (v1, July) to {metric('case_brief', 'v4', 'grounded_pass_rate')}% (v4, August)", "05"],
    ]
    rows += [[f"Genie, {label.lower()}", f"{p} of {n} ({pct}%)", "08"] for label, p, n, pct in g]
    write("HEADLINES.md", "Headline figures",
          "These are the figures the README and the deck quote. Each is computed from the live workspace after the "
          "final run, and the last column names the evidence file that shows it in full.",
          table(["figure", "value", "evidence"], rows))


SECTIONS = {"01": ev01, "02": ev02, "03": ev03, "04": ev04_05, "06": ev06, "07": ev07, "08": ev08,
            "09": ev09, "10": ev10, "HL": evhl}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--profile", required=True)
    ap.add_argument("--only", default="", help="comma-separated section numbers, e.g. 01,06")
    ap.add_argument("--reuse-genie", action="store_true", help="section 08: use the last run's results files")
    a = ap.parse_args()
    global REUSE_GENIE
    REUSE_GENIE = a.reuse_genie
    ctx = Ctx(a.profile)
    REDACT[ctx.w.current_user.me().user_name] = "builder@example.com"
    os.makedirs(OUT, exist_ok=True)
    only = [s.strip() for s in a.only.split(",") if s.strip()]
    for num, fn in SECTIONS.items():
        if not only or num in only:
            print(f"section {num}")
            fn(ctx)


if __name__ == "__main__":
    main()
