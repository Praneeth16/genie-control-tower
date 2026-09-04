"""Build, create/update and publish the AI/BI dashboard as code.

Why code and not the UI: the dashboard has to be reproducible in a fresh workspace alongside the
Genie spaces, the UC policies and the Lakebase migrations. A dashboard drawn by hand in the browser
is the one asset in this project that could not be rebuilt from the repo.

    python3 dashboards/build_dashboard.py --write     # emit serialized JSON only
    python3 dashboards/build_dashboard.py --deploy    # create-or-update, then publish

Governance choice that matters for the demo: the dashboard is published WITHOUT embedded
credentials. Every viewer's own Unity Catalog row filters and column masks therefore apply to the
dashboard exactly as they apply to the Genie Agents, so the numbers a regional manager sees here
agree with the numbers the agent gives them. Publishing with embedded credentials would run every
tile as the publisher and quietly contradict the whole governance story.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app", "backend"))
# Auth comes from DATABRICKS_CONFIG_PROFILE / DATABRICKS_HOST, set in .env or the shell.

import config  # noqa: E402

FQ = config.FQ
NAME = f"{config.BANK_NAME} Control Tower — Portfolio, Service and Incentive Integrity"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "control_tower.lvdash.json")


# --------------------------------------------------------------------------- spec helpers
def ds(name: str, sql: str, display: str) -> dict:
    return {"name": name, "displayName": display, "queryLines": [l + "\n" for l in sql.strip().splitlines()]}


def _q(dataset: str, fields: list[str]) -> list[dict]:
    return [{"name": "main_query", "query": {
        "datasetName": dataset,
        "fields": [{"name": f, "expression": f"`{f}`"} for f in fields],
        # Every dataset below is ALREADY aggregated in SQL. Left disaggregated=false the widget would
        # re-aggregate and silently average a percentage that was computed as a weighted ratio.
        "disaggregated": True}}]


def chart(name: str, dataset: str, kind: str, x: str, y: str, title: str,
          xlabel: str, ylabel: str, xscale: str = "categorical", color: str | None = None) -> dict:
    enc = {"x": {"fieldName": x, "scale": {"type": xscale}, "displayName": xlabel},
           "y": {"fieldName": y, "scale": {"type": "quantitative"}, "displayName": ylabel}}
    fields = [x, y]
    if color:
        enc["color"] = {"fieldName": color, "scale": {"type": "categorical"}, "displayName": color}
        fields.append(color)
    return {"name": name, "queries": _q(dataset, fields),
            "spec": {"version": 3, "widgetType": kind, "encodings": enc,
                     "frame": {"showTitle": True, "title": title}}}


def counter(name: str, dataset: str, field: str, title: str) -> dict:
    return {"name": name, "queries": _q(dataset, [field]),
            "spec": {"version": 2, "widgetType": "counter",
                     "encodings": {"value": {"fieldName": field, "displayName": title}},
                     "frame": {"showTitle": True, "title": title}}}


def table(name: str, dataset: str, cols: list[tuple[str, str]], title: str) -> dict:
    return {"name": name, "queries": _q(dataset, [c for c, _ in cols]),
            "spec": {"version": 1, "widgetType": "table",
                     "encodings": {"columns": [
                         {"fieldName": c, "displayName": label, "order": i}
                         for i, (c, label) in enumerate(cols)]},
                     "frame": {"showTitle": True, "title": title}}}


def markdown(name: str, md: str) -> dict:
    return {"name": name, "spec": {"version": 1, "widgetType": "text",
                                   "textbox_spec": md, "frame": {"showTitle": False}}}


def place(widget: dict, x: int, y: int, w: int, h: int) -> dict:
    return {"widget": widget, "position": {"x": x, "y": y, "width": w, "height": h}}


# --------------------------------------------------------------------------- datasets
DATASETS = [
    ds("gnpa_region", f"""
SELECT b.region,
       ROUND(100.0 * SUM(CASE WHEN d.is_npa THEN d.outstanding_principal ELSE 0 END)
                   / SUM(d.outstanding_principal), 1) AS gnpa_pct,
       ROUND(SUM(d.outstanding_principal) / 10000000.0, 1) AS exposure_cr
FROM {FQ}.delinquency_monthly d
JOIN {FQ}.branch_master b ON d.branch_id = b.branch_id
WHERE d.snapshot_month = DATE'2026-08-01'
GROUP BY b.region
ORDER BY gnpa_pct DESC""", "GNPA % by region (Aug 2026)"),

    ds("delinq_product", f"""
SELECT product_code,
       ROUND(100.0 * SUM(CASE WHEN dpd_days > 0 THEN 1 ELSE 0 END) / COUNT(*), 1) AS delinquency_pct
FROM {FQ}.delinquency_monthly
WHERE snapshot_month = DATE'2026-08-01'
GROUP BY product_code
ORDER BY delinquency_pct DESC""", "Delinquency % by product (Aug 2026)"),

    ds("mfi_solapur_trend", f"""
SELECT d.snapshot_month,
       ROUND(100.0 * SUM(CASE WHEN d.dpd_days > 0 THEN 1 ELSE 0 END) / COUNT(*), 1) AS delinquency_pct
FROM {FQ}.delinquency_monthly d
JOIN {FQ}.branch_master b ON d.branch_id = b.branch_id
WHERE d.product_code = 'MFI' AND b.city = 'Solapur'
GROUP BY d.snapshot_month
ORDER BY d.snapshot_month""", "Solapur microfinance delinquency trend"),

    ds("conduct_kpis", f"""
SELECT COUNT(*) AS out_of_hours_attempts
FROM {FQ}.collections_activity
WHERE within_rbi_hours = FALSE""", "Out-of-hours contact attempts"),

    ds("uncertified_kpi", f"""
SELECT COUNT(DISTINCT a.agent_id) AS uncertified_agents_contacting
FROM {FQ}.collections_activity a
JOIN {FQ}.recovery_agents r ON a.agent_id = r.agent_id
WHERE r.rbi_conduct_certified = FALSE
  AND a.activity_date >= DATE'2026-01-01'""", "Uncertified agents making contact (2026)"),

    ds("agency_conduct", f"""
SELECT r.agency_name,
       COUNT(*) AS attempts,
       SUM(CASE WHEN a.within_rbi_hours = FALSE THEN 1 ELSE 0 END) AS out_of_hours,
       ROUND(100.0 * SUM(CASE WHEN a.within_rbi_hours = FALSE THEN 1 ELSE 0 END) / COUNT(*), 1) AS out_of_hours_pct
FROM {FQ}.collections_activity a
JOIN {FQ}.recovery_agents r ON a.agent_id = r.agent_id
GROUP BY r.agency_name
ORDER BY out_of_hours_pct DESC""", "Conduct exposure by agency"),

    # The tile the data fix made possible. Complaints used to be assigned to random customers, so there
    # was no relationship between who was chased and who complained — this join returned noise. Now that
    # recovery-conduct complaints are generated from actual recovery pressure, it shows the thing a
    # conduct committee wants: breaches concentrate where EFFORT concentrates. The rate is a flat ~4%
    # everywhere; the exposure is not, and exposure is what gets a bank fined.
    ds("conduct_to_grievance", f"""
WITH contact AS (
  SELECT b.city, COUNT(*) AS attempts,
         SUM(CASE WHEN a.within_rbi_hours = FALSE THEN 1 ELSE 0 END) AS out_of_hours,
         COUNT(DISTINCT a.loan_account_id) AS accounts_contacted
  FROM {FQ}.collections_activity a
  JOIN {FQ}.branch_master b ON a.branch_id = b.branch_id
  GROUP BY b.city),
rec AS (
  SELECT b.city, COUNT(DISTINCT c.complaint_id) AS recovery_complaints
  FROM {FQ}.complaints c
  JOIN {FQ}.complaint_categories cc ON c.category_code = cc.category_code
  JOIN {FQ}.loan_accounts l ON c.customer_id = l.customer_id
  JOIN {FQ}.branch_master b ON l.branch_id = b.branch_id
  WHERE cc.rbi_category = 'Recovery agents'
  GROUP BY b.city)
SELECT contact.city,
       contact.out_of_hours AS out_of_hours_contacts,
       ROUND(100.0 * contact.out_of_hours / contact.attempts, 1) AS out_of_hours_pct,
       COALESCE(rec.recovery_complaints, 0) AS recovery_complaints
FROM contact LEFT JOIN rec ON contact.city = rec.city
ORDER BY out_of_hours_contacts DESC""", "Conduct breaches and the complaints they produce, by city"),

    ds("sla_category", f"""
SELECT rbi_category,
       ROUND(100.0 * SUM(breached_sla) / SUM(complaints_received), 1) AS breach_rate_pct
FROM {FQ}.sla_tracker
WHERE report_month = DATE'2026-08-01'
GROUP BY rbi_category
ORDER BY breach_rate_pct DESC""", "SLA breach % by RBI ground (Aug 2026)"),

    ds("upi_incident", f"""
SELECT txn_date,
       COUNT(*) AS disputes,
       ROUND(100.0 * SUM(CASE WHEN auto_refunded THEN 1 ELSE 0 END) / COUNT(*), 1) AS auto_refund_pct
FROM {FQ}.upi_disputes
WHERE txn_date BETWEEN DATE'2026-06-01' AND DATE'2026-06-30'
GROUP BY txn_date
ORDER BY txn_date""", "June 2026 UPI switch incident"),

    ds("ombudsman_kpi", f"""
SELECT COUNT(*) AS ombudsman_escalations
FROM {FQ}.complaints
WHERE escalated_to_ombudsman = TRUE""", "Ombudsman escalations"),

    ds("open_past_sla_kpi", f"""
SELECT COUNT(*) AS open_past_sla
FROM {FQ}.complaints
WHERE status = 'Open' AND DATEDIFF(DATE'2026-08-31', received_date) > sla_days""",
       "Open complaints past SLA"),

    ds("escalation_category", f"""
SELECT c.rbi_category,
       COUNT(*) AS complaints,
       SUM(CASE WHEN x.escalated_to_ombudsman THEN 1 ELSE 0 END) AS escalated,
       ROUND(100.0 * SUM(CASE WHEN x.escalated_to_ombudsman THEN 1 ELSE 0 END) / COUNT(*), 2) AS escalation_pct
FROM {FQ}.complaints x
JOIN {FQ}.complaint_categories c ON x.category_code = c.category_code
GROUP BY c.rbi_category
ORDER BY escalation_pct DESC""", "Ombudsman escalation rate by ground"),

    ds("clawback_kpi", f"""
SELECT COUNT(DISTINCT rm_id) AS rms_in_clawback_cohort
FROM {FQ}.rm_achievement
WHERE attainment_pct >= 120 AND product_mix_score < 0.50""",
       "RMs over-attaining but failing the quality gate"),

    ds("incentive_paid_kpi", f"""
SELECT ROUND(SUM(incentive_earned) / 100000.0, 1) AS incentive_paid_lakh
FROM {FQ}.rm_achievement
WHERE achievement_month = DATE'2026-08-01'""", "Incentive paid, Aug 2026 (INR lakh)"),

    ds("incentive_mix_band", f"""
SELECT CASE WHEN product_mix_score < 0.50 THEN 'Failed quality gate'
            ELSE 'Cleared quality gate' END AS mix_band,
       ROUND(AVG(incentive_earned), 0) AS avg_incentive,
       COUNT(*) AS rm_months
FROM {FQ}.rm_achievement
WHERE attainment_pct >= 120
GROUP BY 1""", "Average incentive at >=120% attainment, by quality gate"),

    ds("incentive_per_million", f"""
SELECT rm_grade,
       ROUND(1000000.0 * SUM(incentive_earned) / SUM(actual_casa_amount + actual_loan_amount), 2)
         AS incentive_per_million
FROM {FQ}.rm_achievement
WHERE achievement_month >= DATE'2026-03-01'
GROUP BY rm_grade
ORDER BY incentive_per_million DESC""", "Incentive per INR million of business, by grade"),

    ds("clawback_grade", f"""
SELECT rm_grade,
       COUNT(*) AS rm_months,
       SUM(CASE WHEN clawback_flag THEN 1 ELSE 0 END) AS clawback_months,
       ROUND(100.0 * SUM(CASE WHEN clawback_flag THEN 1 ELSE 0 END) / COUNT(*), 1) AS clawback_rate_pct
FROM {FQ}.rm_achievement
GROUP BY rm_grade
ORDER BY clawback_rate_pct DESC""", "Clawback rate by grade"),

    ds("casa_attainment_region", f"""
SELECT a.region,
       ROUND(100.0 * SUM(a.actual_casa_amount) / SUM(t.target_casa_amount), 1) AS casa_attainment_pct
FROM {FQ}.rm_achievement a
JOIN {FQ}.rm_targets t ON a.rm_id = t.rm_id AND a.achievement_month = t.target_month
WHERE a.achievement_month = DATE'2026-08-01'
GROUP BY a.region
ORDER BY casa_attainment_pct DESC""", "CASA attainment % by region (Aug 2026)"),
]

BANNER = (
    f"## {config.BANK_NAME} Control Tower — governed analytics\n"
    "**All data on this dashboard is synthetic.** It is published *without* embedded credentials, so "
    "every tile runs as **you**: the same Unity Catalog row filters and column masks that govern the "
    "Genie Agents govern this page, and the numbers agree with the numbers the agents give you.\n"
)

PAGES = [
    {"name": "collections", "displayName": "Collections & Recovery", "layout": [
        place(markdown("md_col", BANNER), 0, 0, 6, 3),
        place(counter("c_ooh", "conduct_kpis", "out_of_hours_attempts",
                      "Out-of-hours contact attempts"), 0, 3, 3, 3),
        place(counter("c_unc", "uncertified_kpi", "uncertified_agents_contacting",
                      "Uncertified agents contacting (2026)"), 3, 3, 3, 3),
        place(chart("ch_gnpa", "gnpa_region", "bar", "region", "gnpa_pct",
                    "GNPA % by region (Aug 2026)", "Region", "GNPA %"), 0, 6, 3, 6),
        place(chart("ch_delinq", "delinq_product", "bar", "product_code", "delinquency_pct",
                    "Delinquency % by product (Aug 2026)", "Product", "Delinquency %"), 3, 6, 3, 6),
        place(chart("ch_mfi", "mfi_solapur_trend", "line", "snapshot_month", "delinquency_pct",
                    "Solapur microfinance delinquency trend", "Month", "Delinquency %",
                    xscale="temporal"), 0, 12, 6, 6),
        place(table("t_agency", "agency_conduct",
                    [("agency_name", "Agency"), ("attempts", "Attempts"),
                     ("out_of_hours", "Out of hours"), ("out_of_hours_pct", "Out of hours %")],
                    "Conduct exposure by agency"), 0, 18, 3, 6),
        place(table("t_conduct_grv", "conduct_to_grievance",
                    [("city", "City"), ("out_of_hours_contacts", "Out-of-hours contacts"),
                     ("out_of_hours_pct", "Out of hours %"),
                     ("recovery_complaints", "Recovery-agent complaints")],
                    "Conduct breaches and the complaints they produce"), 3, 18, 3, 6),
    ]},
    {"name": "grievance", "displayName": "Service & Grievance", "layout": [
        place(counter("c_omb", "ombudsman_kpi", "ombudsman_escalations",
                      "Ombudsman escalations"), 0, 0, 3, 3),
        place(counter("c_open", "open_past_sla_kpi", "open_past_sla",
                      "Open complaints past SLA"), 3, 0, 3, 3),
        place(chart("ch_sla", "sla_category", "bar", "rbi_category", "breach_rate_pct",
                    "SLA breach % by RBI ground (Aug 2026)", "RBI ground", "Breach %"), 0, 3, 6, 6),
        place(chart("ch_upi_v", "upi_incident", "line", "txn_date", "disputes",
                    "UPI dispute volume, June 2026", "Transaction date", "Disputes",
                    xscale="temporal"), 0, 9, 3, 6),
        place(chart("ch_upi_r", "upi_incident", "line", "txn_date", "auto_refund_pct",
                    "UPI auto-refund %, June 2026 (NPCI 30s reversal)", "Transaction date",
                    "Auto-refund %", xscale="temporal"), 3, 9, 3, 6),
        place(table("t_esc", "escalation_category",
                    [("rbi_category", "RBI ground"), ("complaints", "Complaints"),
                     ("escalated", "Escalated"), ("escalation_pct", "Escalation %")],
                    "Ombudsman escalation rate by ground"), 0, 15, 6, 6),
    ]},
    {"name": "rm", "displayName": "RM Performance & Incentive Integrity", "layout": [
        place(counter("c_claw", "clawback_kpi", "rms_in_clawback_cohort",
                      "RMs over-attaining but failing the quality gate"), 0, 0, 3, 3),
        place(counter("c_inc", "incentive_paid_kpi", "incentive_paid_lakh",
                      "Incentive paid, Aug 2026 (INR lakh)"), 3, 0, 3, 3),
        place(chart("ch_mix", "incentive_mix_band", "bar", "mix_band", "avg_incentive",
                    "Average incentive at >=120% attainment", "Quality gate outcome",
                    "Average incentive (INR)"), 0, 3, 3, 6),
        place(chart("ch_ipm", "incentive_per_million", "bar", "rm_grade", "incentive_per_million",
                    "Incentive per INR million of business, by grade", "Grade",
                    "INR per million"), 3, 3, 3, 6),
        place(chart("ch_casa", "casa_attainment_region", "bar", "region", "casa_attainment_pct",
                    "CASA attainment % by region (Aug 2026)", "Region", "Attainment %"), 0, 9, 3, 6),
        place(table("t_claw", "clawback_grade",
                    [("rm_grade", "Grade"), ("rm_months", "RM-months"),
                     ("clawback_months", "Clawback months"), ("clawback_rate_pct", "Clawback rate %")],
                    "Clawback rate by grade"), 3, 9, 3, 6),
    ]},
]


def serialized() -> str:
    return json.dumps({"datasets": DATASETS, "pages": PAGES}, indent=2)


def _validate_fields(columns: dict[str, list[str]]) -> int:
    """Cross-check every widget against the columns its dataset actually returns.

    This is the check worth automating, because it catches the one dashboard bug the deploy path
    cannot: `lakeview.create` and `publish` both accept a widget whose `fieldName` does not exist.
    The API validates the envelope, not the encodings, so a renamed or typo'd column deploys
    perfectly green and then renders as an empty tile with a small error badge — visible only to
    someone looking at the page. Comparing encodings against the live result schema turns that into
    a build failure instead of a discovery made on stage.
    """
    problems: list[str] = []
    widgets = [e["widget"] for p in PAGES for e in p["layout"]]
    seen_names: set[str] = set()
    for wdg in widgets:
        name = wdg["name"]
        if name in seen_names:
            problems.append(f"{name}: duplicate widget name — the later one silently replaces the earlier")
        seen_names.add(name)

        queries = wdg.get("queries") or []
        if not queries:                       # markdown tiles legitimately have no query
            continue
        q = queries[0]["query"]
        dataset = q["datasetName"]
        if dataset not in columns:
            problems.append(f"{name}: dataset {dataset!r} did not return a schema, cannot verify")
            continue
        available = set(columns[dataset])
        declared = {f["name"] for f in q["fields"]}
        for f in sorted(declared - available):
            problems.append(f"{name}: field {f!r} is not a column of {dataset} {sorted(available)}")

        enc = wdg["spec"].get("encodings") or {}
        referenced: list[str] = []
        for key, val in enc.items():
            if key == "columns":
                referenced += [c["fieldName"] for c in val]
            elif isinstance(val, dict) and "fieldName" in val:
                referenced.append(val["fieldName"])
        for f in referenced:
            if f not in declared:
                problems.append(f"{name}: encoding references {f!r}, which the widget query does not select")
            elif f not in available:
                problems.append(f"{name}: encoding references {f!r}, absent from {dataset}")

    unused = set(columns) - {(wdg.get("queries") or [{}])[0].get("query", {}).get("datasetName")
                             for wdg in widgets if wdg.get("queries")}
    for d in sorted(unused):
        problems.append(f"dataset {d!r} is defined but no widget uses it — it will run cost for nothing")

    for p in problems:
        print(f"  FIELD {p}")
    print(f"{len(widgets)} widgets checked against live dataset schemas: "
          f"{'all field references resolve' if not problems else str(len(problems)) + ' problems'}")
    return len(problems)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--deploy", action="store_true")
    ap.add_argument("--validate-sql", action="store_true")
    a = ap.parse_args()

    body = serialized()
    if a.write or not (a.deploy or a.validate_sql):
        with open(OUT, "w") as f:
            f.write(body)
        print(f"wrote {OUT}  ({len(DATASETS)} datasets, {len(PAGES)} pages, "
              f"{sum(len(p['layout']) for p in PAGES)} widgets)")

    if a.validate_sql:
        import databricks_client as dbx
        bad = 0
        columns: dict[str, list[str]] = {}
        for d in DATASETS:
            sql = "".join(d["queryLines"])
            try:
                out = dbx.run_sql(sql)
                columns[d["name"]] = out["columns"]
                print(f"  ok    {d['name']:<24} {len(out['rows']):>3} rows  {out['columns']}")
                if not out["rows"]:
                    print(f"  EMPTY {d['name']}")
                    bad += 1
            except Exception as e:
                print(f"  FAIL  {d['name']:<24} {type(e).__name__}: {e}"[:200])
                bad += 1
        print(f"\n{len(DATASETS) - bad}/{len(DATASETS)} dataset queries valid")
        bad += _validate_fields(columns)
        if bad:
            return 1

    if a.deploy:
        from databricks.sdk import WorkspaceClient
        from databricks.sdk.service.dashboards import Dashboard
        w = WorkspaceClient()
        existing = None
        # Prefer the id this deployment already published. Matching on display_name alone means any
        # change to BANK_NAME silently CREATES a second dashboard while DASHBOARD_ID keeps pointing at
        # the first, so the app embeds a stale copy and nobody sees an error.
        if config.DASHBOARD_ID:
            try:
                existing = w.lakeview.get(dashboard_id=config.DASHBOARD_ID)
            except Exception:
                existing = None          # id is stale or from another workspace; fall back to name
        if existing is None:
            for d in w.lakeview.list():
                if d.display_name == NAME:
                    existing = d
                    break
        if existing:
            dash = w.lakeview.update(dashboard_id=existing.dashboard_id,
                                     dashboard=Dashboard(display_name=NAME,
                                                         serialized_dashboard=body,
                                                         warehouse_id=config.WAREHOUSE_ID))
            print(f"updated dashboard {dash.dashboard_id}")
        else:
            dash = w.lakeview.create(dashboard=Dashboard(
                display_name=NAME, serialized_dashboard=body,
                warehouse_id=config.WAREHOUSE_ID,
                parent_path=f"/Users/{w.current_user.me().user_name}"))
            print(f"created dashboard {dash.dashboard_id}")
        # embed_credentials=False -> each viewer's own UC row filters and masks apply.
        w.lakeview.publish(dashboard_id=dash.dashboard_id, embed_credentials=False,
                           warehouse_id=config.WAREHOUSE_ID)
        print(f"published (embed_credentials=False)\nDASHBOARD_ID={dash.dashboard_id}")
        print(f"open: {w.config.host}/dashboardsv3/{dash.dashboard_id}/published")
    return 0


if __name__ == "__main__":
    sys.exit(main())
