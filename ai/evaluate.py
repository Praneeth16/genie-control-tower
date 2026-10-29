"""Evaluate the two AI steps, and write the results to Unity Catalog and MLflow.

    evaluate.py --catalog <c> --schema <s> --judge-model databricks-gpt-5-5 --experiment /Shared/...

1. Letter triage (in the pipeline). Graded against the ground recorded on each complaint by the
   grievance desk — a real label, not a judge's opinion: accuracy, the confusion pairs, and how well
   the conduct-breach flag finds recovery-agent complaints.

2. Case briefs (ai/case_brief.sql). There is no single right sentence, so two kinds of check:
     deterministic   does the suggested action follow the bank's conduct rules; does every number in
                     the explanation appear in the facts the model was given; is it within 60 words
     LLM judges      four MLflow Guidelines judges, run on a DIFFERENT model family from the generator so
                     they do not share its blind spots: grounded, conduct-compliant, actionable, plain.

Every row's result and every judge's rationale lands in ai_eval_results; one line per metric per run in
ai_eval_summary. The judges are never softened to raise a pass rate: when a judge and a check disagree,
the disagreement is reported, and BUILD_LOG.md records what was changed in the prompt instead.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import uuid
from concurrent.futures import ThreadPoolExecutor

# The rule-based treatment in collections_priority, as the action the brief should suggest.
RULE_TO_ACTION = {
    "Hold recovery contact until the grievance is closed": "hold_contact",
    "Reassign to a certified agency and review conduct": "assign_recovery_agency",
    "Settlement or legal review": "offer_settlement",
    "Field visit by a certified agent": "schedule_field_visit",
    "Tele-calling and digital reminder": "tele_calling_reminder",
}

# j1 asked for "only facts present in the facts JSON" and failed every brief: it read interpretation
# ("this makes it a high-priority case") as an invented fact. That was the judge being mis-specified, not
# the briefs being ungrounded — its own rationales listed every stated fact as present. j2 separates the
# two. Both versions' results are kept in ai_eval_summary, so the change is visible, not silent.
JUDGE_VERSION = "j2"
JUDGES = {
    "grounded": (
        "Every factual claim in the response's explanation (a number, amount, date, count, status, person, "
        "document or event) must be present in the request's facts JSON or be a rounding of a value there. "
        "Interpretation and judgement drawn from those facts, such as calling the account high priority or "
        "saying nothing restricts outreach when no conduct flag is present, is allowed and is not a new fact. "
        "Fail only if the explanation asserts a fact the facts JSON does not contain."),
    "conduct_compliant": (
        "If the request's facts show open_grievance true, the response's recommended_action must be "
        "hold_contact. If they show any out-of-hours contacts, any uncertified-agent contacts, or "
        "letter_alleges_agent_misconduct true, the recommended_action must not be schedule_field_visit "
        "and the explanation must mention the conduct issue. Otherwise this guideline passes."),
    "actionable": (
        "The response gives a collections officer a clear reason for the account's position on the "
        "worklist, and its recommended_action is a concrete next step consistent with that reason."),
    "plain_language": (
        "The response's explanation is at most 60 words of plain English that a branch collections "
        "officer would understand, using only standard banking terms such as DPD, NPA and SMA."),
}


def numbers(text: str) -> list[float]:
    return [float(n.replace(",", "")) for n in re.findall(r"\d[\d,]*(?:\.\d+)?", text)]


def ungrounded_numbers(explanation: str, facts: str) -> list[str]:
    """Numbers in the explanation that match no value in the facts, allowing for rounding and for the
    amount being written in thousands, lakh, millions or crore (INR 33,38,970 written as 33.39 L)."""
    have = numbers(facts)
    out = []
    for x in numbers(explanation):
        if not any(abs(v - x * scale) <= 0.01 * max(abs(v), 1.0)
                   for v in have for scale in (1, 1e3, 1e5, 1e6, 1e7)):
            out.append(f"{x:g}")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--catalog", required=True)
    ap.add_argument("--schema", required=True)
    ap.add_argument("--judge-model", required=True)
    ap.add_argument("--experiment", required=True)
    ap.add_argument("--brief-prompt-version", required=True)
    a = ap.parse_args()
    fq = f"{a.catalog}.{a.schema}"

    import mlflow
    from mlflow.genai.scorers import Guidelines
    from pyspark.sql import SparkSession

    spark = SparkSession.builder.getOrCreate()
    mlflow.set_tracking_uri("databricks")
    mlflow.set_experiment(a.experiment)
    run_id = str(uuid.uuid4())
    now = dt.datetime.now(dt.timezone.utc)
    results: list[dict] = []
    summary: list[dict] = []

    def metric(component, version, model, name, value):
        summary.append({"eval_run_id": run_id, "evaluated_at": now, "component": component,
                        "prompt_version": version, "judge_version": JUDGE_VERSION, "model": model,
                        "metric": name, "value": float(value)})

    # ---------------------------------------------------------------- 1. letter triage vs ground truth
    tri = spark.sql(f"""
        SELECT t.complaint_id, t.predicted_rbi_ground, t.alleges_conduct_breach, t.prompt_version, t.model,
               t.error, c.rbi_category AS truth, c.category_code
        FROM {fq}.complaint_ai_triage t JOIN {fq}.complaints c USING (complaint_id)""").collect()
    if tri:
        version, model = tri[0]["prompt_version"], tri[0]["model"]
        ok = [r for r in tri if r["error"] is None]
        correct = sum(r["predicted_rbi_ground"] == r["truth"] for r in ok)
        rec = [r for r in ok if r["category_code"] == "REC"]
        flagged = [r for r in ok if r["alleges_conduct_breach"]]
        tp = sum(1 for r in flagged if r["category_code"] == "REC")
        metric("letter_triage", version, model, "letters", len(tri))
        metric("letter_triage", version, model, "errors", len(tri) - len(ok))
        metric("letter_triage", version, model, "ground_accuracy", correct / max(len(ok), 1))
        metric("letter_triage", version, model, "conduct_recall", tp / max(len(rec), 1))
        metric("letter_triage", version, model, "conduct_precision", tp / max(len(flagged), 1))
        for r in tri:
            results.append({"eval_run_id": run_id, "evaluated_at": now, "component": "letter_triage",
                            "prompt_version": version, "record_id": r["complaint_id"], "check_name": "ground_matches_recorded",
                            "passed": r["predicted_rbi_ground"] == r["truth"],
                            "rationale": f"predicted {r['predicted_rbi_ground']}; recorded {r['truth']}",
                            "judge_model": None})

    # ---------------------------------------------------------------- 2. case briefs
    briefs = spark.sql(f"""
        SELECT b.loan_account_id, b.facts, b.explanation, b.recommended_action, b.model, b.prompt_version,
               b.error, p.recommended_treatment
        FROM {fq}.collections_case_brief b
        JOIN {fq}.collections_priority p USING (loan_account_id)
        WHERE b.prompt_version = '{a.brief_prompt_version}'""").collect()
    if briefs:
        version, model = a.brief_prompt_version, briefs[0]["model"]
        ok = [r for r in briefs if r["error"] is None and r["explanation"]]
        judges = {name: Guidelines(name=name, guidelines=g, model=f"databricks:/{a.judge_model}")
                  for name, g in JUDGES.items()}

        def judge(r):
            inputs = {"facts": r["facts"]}
            outputs = {"explanation": r["explanation"], "recommended_action": r["recommended_action"]}
            out = {}
            for name, scorer in judges.items():
                fb = scorer(inputs=inputs, outputs=outputs)
                out[name] = (str(fb.value).lower() == "yes", fb.rationale)
            return r, out

        with ThreadPoolExecutor(max_workers=8) as pool:
            judged = list(pool.map(judge, ok))

        tallies = {k: 0 for k in [*JUDGES, "rule_agreement", "numbers_grounded", "within_60_words"]}
        for r, verdicts in judged:
            expected = RULE_TO_ACTION.get(r["recommended_treatment"])
            missing = ungrounded_numbers(r["explanation"], r["facts"])
            checks = {
                "rule_agreement": (r["recommended_action"] == expected,
                                   f"suggested {r['recommended_action']}; conduct rules give {expected}"),
                "numbers_grounded": (not missing, "all numbers appear in the facts" if not missing
                                     else f"numbers not in facts: {', '.join(missing)}"),
                "within_60_words": (len(r["explanation"].split()) <= 60, f"{len(r['explanation'].split())} words"),
            }
            for name, (passed, why) in {**checks, **verdicts}.items():
                tallies[name] += passed
                results.append({"eval_run_id": run_id, "evaluated_at": now, "component": "case_brief",
                                "prompt_version": version, "record_id": r["loan_account_id"], "check_name": name,
                                "passed": bool(passed), "rationale": why,
                                "judge_model": f"{a.judge_model} ({JUDGE_VERSION})" if name in JUDGES else None})
        metric("case_brief", version, model, "briefs", len(briefs))
        metric("case_brief", version, model, "errors", len(briefs) - len(ok))
        for name, n in tallies.items():
            metric("case_brief", version, model, f"{name}_pass_rate", n / max(len(ok), 1))

    # ---------------------------------------------------------------- persist
    spark.sql(f"""CREATE TABLE IF NOT EXISTS {fq}.ai_eval_summary (
        eval_run_id STRING, evaluated_at TIMESTAMP, component STRING, prompt_version STRING, model STRING,
        metric STRING, value DOUBLE, judge_version STRING)
        COMMENT 'One row per metric per evaluation run of the AI steps (letter triage, case briefs). Compare prompt versions here.'""")
    spark.sql(f"""CREATE TABLE IF NOT EXISTS {fq}.ai_eval_results (
        eval_run_id STRING, evaluated_at TIMESTAMP, component STRING, prompt_version STRING, record_id STRING,
        check_name STRING, passed BOOLEAN, rationale STRING, judge_model STRING)
        COMMENT 'Per-record result of every check and judge in every evaluation run, with the judge rationale.'""")
    if summary:
        spark.createDataFrame(summary).select("eval_run_id", "evaluated_at", "component", "prompt_version",
                                              "model", "metric", "value", "judge_version") \
            .write.mode("append").saveAsTable(f"{fq}.ai_eval_summary")
    if results:
        spark.createDataFrame(results, schema="eval_run_id STRING, evaluated_at TIMESTAMP, component STRING, "
                              "prompt_version STRING, record_id STRING, check_name STRING, passed BOOLEAN, "
                              "rationale STRING, judge_model STRING") \
            .write.mode("append").saveAsTable(f"{fq}.ai_eval_results")

    with mlflow.start_run(run_name=f"ai-eval-{now:%Y%m%d-%H%M}"):
        mlflow.log_params({"eval_run_id": run_id, "judge_model": a.judge_model, "judge_version": JUDGE_VERSION,
                           "brief_prompt_version": a.brief_prompt_version})
        for m in summary:
            mlflow.log_metric(f"{m['component']}.{m['metric']}", m["value"])
        if results:
            mlflow.log_table({k: [r[k] if k != "evaluated_at" else str(r[k]) for r in results] for k in results[0]},
                             artifact_file="ai_eval_results.json")
    print(json.dumps([{k: (v if k != "evaluated_at" else str(v)) for k, v in m.items()} for m in summary], indent=1))


if __name__ == "__main__":
    # Not sys.exit(main()): serverless job tasks report SystemExit(0) as a failure.
    main()
