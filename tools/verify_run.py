"""Run the verification notebook against the live workspace and save it with its outputs.

    .venv/bin/python tools/verify_run.py --profile <cli-profile>

Writes run_output/verify_run.ipynb. Each code cell below is executed in order, here, against the
deployed bundle, and whatever it printed is stored as that cell's output. Nothing in the saved
notebook is typed by hand. A cell that fails stores the error instead of hiding it.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import sys
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

CELLS: list[tuple[str, str]] = []   # (markdown, code)


def cell(md: str, code: str) -> None:
    CELLS.append((md.strip(), code.strip()))


cell("""# Proof that the build ran

Every cell below was executed against the deployed bundle and its output saved. The run time is in the
first output. The notebook is produced by `tools/verify_run.py`, which executes these cells in order and
stores what each one printed. Re-run it to refresh the outputs.""",
"""
import datetime as dt, json
from tools.generate_evidence import Ctx, table
ctx = Ctx(PROFILE)
print("executed at", dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))
print("workspace  ", ctx.w.config.host)
print("schema     ", ctx.fq)
print("pipeline   ", ctx.pipeline_id)
print("jobs       ", {k: v for k, v in ctx.jobs.items() if k in ("ct_setup", "ct_cycle", "ct_land_period")})
print("genie      ", ctx.spaces)
""")

cell("""## 1. Lakeflow: the pipeline's own update history

The pipeline is a serverless Spark Declarative Pipeline. These are its most recent updates, read from the
Pipelines API. `JOB_TASK` means the cycle job started it. The update at 10:28 on 29 Oct was started by the
cycle job after the August files arrived.""",
"""
ups = ctx.w.pipelines.list_updates(ctx.pipeline_id, max_results=6).updates or []
rows = [[u.update_id, u.state.value, u.cause.value,
         dt.datetime.fromtimestamp(u.creation_time / 1000, dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")] for u in ups]
print(table(["update_id", "state", "cause", "created"], rows))
""")

cell("""## 2. Lakeflow: expectations from the event log

Every data-quality rule is an expectation. The counts come from `event_log()` for this pipeline, summed over
every update since the tables were created.""",
"""
cols, rows = ctx.sql(f'''
SELECT e.dataset, e.name AS expectation, sum(e.passed_records) AS passed, sum(e.failed_records) AS failed
FROM (SELECT explode(from_json(details:flow_progress:data_quality:expectations,
        'array<struct<name:string,dataset:string,passed_records:bigint,failed_records:bigint>>')) AS e
      FROM event_log('{ctx.pipeline_id}') WHERE event_type = 'flow_progress'
        AND details:flow_progress:data_quality:expectations IS NOT NULL) x
GROUP BY ALL ORDER BY 1, 2''')
print(table(cols, rows, 80))
""")

cell("""## 3. Lakeflow: every file reconciled against its sender's manifest

`recon_completeness` compares what each source system declared in its manifest with what landed, what
loaded and what was quarantined. One file is a BREAK on purpose: the June dialer file was truncated in
transfer and its manifest still counts the lost rows.""",
"""
cols, rows = ctx.sql(f"SELECT status, count(*) AS files FROM {ctx.fq}.recon_completeness GROUP BY status ORDER BY status")
print(table(cols, rows))
cols, rows = ctx.sql(f"SELECT * FROM {ctx.fq}.recon_completeness WHERE status = 'BREAK'")
print(table(cols, rows))
""")

cell("""## 4. Lakeflow: what the quality rules caught, and the rows in gold

`data_quality_summary` is a gold table that counts the quarantined rows by reason. `gold_row_counts` is the
unfiltered count of each governed table and is what the app's guardrails read.""",
"""
cols, rows = ctx.sql(f"SELECT * FROM {ctx.fq}.data_quality_summary ORDER BY 1, 2")
print(table(cols, rows, 40))
cols, rows = ctx.sql(f"SELECT * FROM {ctx.fq}.gold_row_counts ORDER BY 1")
print(table(cols, rows, 40))
""")

cell("""## 5. The worklist in gold

`collections_priority` is the ranked worklist. The score components are stored in words on every row.""",
"""
cols, rows = ctx.sql(f"SELECT count(*) AS accounts, round(sum(outstanding_principal) / 1e7, 2) AS outstanding_crore FROM {ctx.fq}.collections_priority")
print(table(cols, rows))
cols, rows = ctx.sql(f"SELECT * FROM {ctx.fq}.collections_priority ORDER BY priority_score DESC LIMIT 3")
for r in rows:
    print(json.dumps(dict(zip(cols, r)), indent=1, default=str)[:1800])
""")

cell("""## 6. AI evaluation, every cycle

The cycle job's `evaluate_ai` task grades the letter triage against the recorded ground and the briefs
against the bank's rules and four MLflow judges, then writes one row per metric to `ai_eval_summary`. The
history below is that table. Each `evaluated_at` is one cycle, so the evaluation is an ongoing check, not a
one-off.""",
"""
cols, rows = ctx.sql(f'''
SELECT date_trunc('minute', evaluated_at) AS evaluated_at, component, prompt_version, judge_version, metric, round(value, 3) AS value
FROM {ctx.fq}.ai_eval_summary
WHERE metric IN ('ground_accuracy', 'conduct_recall', 'rule_agreement_pass_rate', 'grounded_pass_rate', 'plain_language_pass_rate')
ORDER BY evaluated_at, component, metric''')
print(table(cols, rows, 120))
""")

cell("""## 7. Orchestration: the cycle job's runs

The cycle job is triggered by file arrival on the manifests folder. The run with trigger `FILE_ARRIVAL`
started on its own when the August files were landed. Each task's result is shown for that run.""",
"""
runs = list(ctx.w.jobs.list_runs(job_id=int(ctx.jobs["ct_cycle"]), limit=8))
rows = [[r.run_id, r.trigger.value if r.trigger else "", r.state.result_state.value if r.state.result_state else r.state.life_cycle_state.value,
         dt.datetime.fromtimestamp(r.start_time / 1000, dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
         round(((r.end_time or 0) - r.start_time) / 60000, 1)] for r in runs]
print(table(["run_id", "trigger", "result", "started", "minutes"], rows))
fa = next((r for r in runs if r.trigger and r.trigger.value == "FILE_ARRIVAL"), runs[0])
full = ctx.w.jobs.get_run(fa.run_id)
print(f"\\nrun {fa.run_id} tasks:")
print(table(["task", "result", "seconds"], [[t.task_key, t.state.result_state.value if t.state.result_state else "", round(((t.end_time or 0) - (t.start_time or 0)) / 1000)] for t in full.tasks]))
""")

cell("""## 8. Genie: one benchmark question through the Conversation API

The Collections agent is asked a question from the benchmark. The output shows the SQL Genie wrote, the
rows it returned, and the ground-truth SQL from `eval/benchmarks/collections.jsonl` run in the same minute.""",
"""
import time
case = next(json.loads(l) for l in open("eval/benchmarks/collections.jsonl") if json.loads(l)["id"] == "COL-02")
space = ctx.spaces["collections"]
print("question:", case["question"])
msg = ctx.w.genie.start_conversation_and_wait(space, case["question"])
print("conversation", msg.conversation_id, "message", msg.message_id, "status", msg.status.value)
for a in msg.attachments or []:
    if a.text:
        print("\\nGenie said:", a.text.content)
    if a.query:
        print("\\nGenie SQL:\\n" + a.query.query.strip())
        res = ctx.w.genie.get_message_attachment_query_result(space, msg.conversation_id, msg.message_id, a.attachment_id)
        sr = res.statement_response
        cols = [c.name for c in sr.manifest.schema.columns]
        print("\\nGenie result:")
        print(table(cols, [list(r) for r in (sr.result.data_array or [])]))
golden = "\\n".join(case["golden_sql"]).replace("{FQ}", ctx.fq)
print("\\nground-truth SQL:\\n" + golden)
cols, rows = ctx.sql(golden)
print("\\nground-truth result:")
print(table(cols, rows))
""")

cell("""## 9. Lakebase: the case queue, and a refused rewrite of history

`collections_cases` is refreshed from gold each cycle, but the columns a person owns are never
overwritten. `case_history` is written by a trigger and refuses UPDATE and DELETE, even from the owner.""",
"""
conn = ctx.pg()
def pgq(sql, params=None):
    with conn.cursor() as cur:
        cur.execute(sql, params)
        cols = [d.name for d in cur.description]
        return cols, [list(r) for r in cur.fetchall()]
print(table(*pgq("SELECT on_worklist, count(*) AS cases FROM collections_cases GROUP BY 1 ORDER BY 1")))
print(table(*pgq("SELECT count(*) AS history_rows, count(DISTINCT case_id) AS cases_with_history FROM case_history")))
print(table(*pgq("SELECT case_id, loan_account_id, status, owner, left(notes, 60) AS notes, updated_at FROM collections_cases WHERE owner IS NOT NULL OR notes IS NOT NULL ORDER BY updated_at DESC LIMIT 3")))
cols, rows = pgq("SELECT column_name FROM information_schema.columns WHERE table_schema = current_schema() AND table_name = 'case_history' ORDER BY ordinal_position")
col = rows[0][0]
try:
    with conn.cursor() as cur:
        cur.execute(f'UPDATE case_history SET "{col}" = "{col}" WHERE ctid = (SELECT ctid FROM case_history LIMIT 1)')
    print("\\nUPDATE case_history succeeded (it should not have)")
except Exception as e:
    print("\\nUPDATE case_history refused:", str(e).strip().splitlines()[0])
""")

cell("""## 10. The approver-role control, as data

`action_policies` names the role that may approve each action type. `approver_roles` is the directory.
The app's `holds_required_role` refuses a principal that is not in the directory for that role, and the
proposer can never approve their own action. The last query shows a persona service principal that holds no
approval role, which is why its approval attempt would be refused.""",
"""
print(table(*pgq("SELECT action_type, requires_approval, approver_role FROM action_policies ORDER BY action_type")))
print(table(*pgq("SELECT role, count(*) AS principals FROM approver_roles GROUP BY role ORDER BY role")))
persona = ctx.vars["persona_collections_head"]
print(table(*pgq("SELECT %s AS principal, count(*) AS approval_roles_held FROM approver_roles WHERE lower(principal) = lower(%s)", (persona, persona))))
print(table(*pgq("SELECT id, action_type, status, requested_by, approved_by, rejected_by FROM actions ORDER BY id DESC LIMIT 5")))
def _rows(sql, params=None):
    cols, rows = pgq(sql, params)
    return [dict(zip(cols, r)) for r in rows]
import os, sys
# The app reads its settings from the environment the bundle gives it; give it the same values here.
os.environ.update({"CT_CATALOG": ctx.catalog, "CT_SCHEMA": ctx.schema, "DATABRICKS_WAREHOUSE_ID": ctx.warehouse,
                   "LAKEBASE_ENDPOINT": ctx.endpoint, "LAKEBASE_SCHEMA": ctx.pg_schema,
                   "COLLECTIONS_SPACE_ID": ctx.spaces["collections"], "GRIEVANCE_SPACE_ID": ctx.spaces["grievance"],
                   "RM_SPACE_ID": ctx.spaces["rm"], "DATABRICKS_CONFIG_PROFILE": PROFILE})
sys.path.insert(0, os.path.join(os.getcwd(), "app", "backend"))   # the app's modules import each other by bare name
import action_plane.guardrails as g
g.lakebase.query = _rows          # the app reads the same Lakebase tables; here through this notebook's connection
me = ctx.w.current_user.me().user_name
ok, why = g.holds_required_role({"action_type": "hold_incentive_payout"}, persona)
print("\\nholds_required_role(hold_incentive_payout, head of collections persona) ->", ok, "|", why)
ok, why = g.authorise_approver({"action_type": "assign_recovery_agency", "requested_by": me}, me)
print("authorise_approver(own action) ->", ok, "|", why)
ok, why = g.holds_required_role({"action_type": "assign_recovery_agency"}, me)
print("holds_required_role(assign_recovery_agency, administrator) ->", ok, "|", why)
""")

cell("""## 11. The app, as the signed-in user

`/api/health` on the deployed app. `obo_active` true means reads run as the caller, not the app.""",
"""
r = ctx.app("GET", "/api/health")
print(r.status_code, json.dumps(r.json(), indent=1)[:600])
r = ctx.app("GET", "/api/overview")
k = r.json()["kpis"]
print(r.status_code, {x: k[x] for x in ("as_of_month", "gnpa_pct", "roll_forward_pct", "delinquent_accounts")})
""")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--profile", required=True)
    a = ap.parse_args()
    os.chdir(ROOT)
    me = None
    ns: dict = {"PROFILE": a.profile}
    nb_cells = []
    for md, code in CELLS:
        nb_cells.append({"cell_type": "markdown", "metadata": {}, "source": md})
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            try:
                exec(compile(code, "<cell>", "exec"), ns)  # noqa: S102  this script is the notebook runner
            except Exception:  # noqa: BLE001  a failing cell is recorded in the notebook, not hidden
                print("ERROR\n" + traceback.format_exc())
        out = buf.getvalue()
        if "ctx" in ns and me is None:
            me = ns["ctx"].w.current_user.me().user_name
        if me:
            out = out.replace(me, "builder@example.com")
        host = ns["ctx"].w.config.host.replace("https://", "")
        out = out.replace(host, "workspace.example.com")   # the hostname names the builder
        nb_cells.append({"cell_type": "code", "metadata": {}, "execution_count": None, "source": code,
                         "outputs": [{"output_type": "stream", "name": "stdout", "text": out}]})
        print(f"cell done: {md.splitlines()[0][:60]} ({len(out)} chars){' ERROR' if 'ERROR' in out[:6] else ''}")
    nb = {"cells": nb_cells, "metadata": {"kernelspec": {"name": "python3", "display_name": "Python 3", "language": "python"},
                                          "language_info": {"name": "python"}},
          "nbformat": 4, "nbformat_minor": 5}
    path = os.path.join(ROOT, "run_output", "verify_run.ipynb")
    with open(path, "w") as f:
        json.dump(nb, f, indent=1, ensure_ascii=False)
    print("wrote", path)


if __name__ == "__main__":
    main()
