"""The case queue and the overview: the two screens the Head of Collections and the CRO work from.

Where each answer comes from, and whose rules apply:

  * Governed numbers (KPIs, completeness, quality) are read from the gold tables AS THE SIGNED-IN USER,
    so Unity Catalog row filters and masks decide what each person sees.
  * The case queue lives in Lakebase, because people edit it and Delta is not a row-at-a-time store.
    Lakebase has no Unity Catalog row filters, so the app applies the SAME rule: a caller sees the cases
    in the regions Unity Catalog lets them see, resolved by asking UC as that caller. One policy, two
    enforcement points, and the UC one is the source of truth.
  * Edits change only the human-owned columns, as the signed-in officer, and the history trigger records
    each change against them.
"""
from __future__ import annotations

import datetime as dt
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

import agent
import config
import databricks_client as dbx
import identity
import lakebase

FQ = config.FQ
STATUSES = ("new", "in_progress", "promise_to_pay", "on_hold", "resolved", "closed")


class CaseUpdate(BaseModel):
    status: Optional[str] = None
    owner: Optional[str] = None
    notes: Optional[str] = None
    next_action_date: Optional[dt.date] = None


def _user_client(request: Request):
    return agent._user_genie_client(identity.user_token(request))


def visible_regions(request: Request) -> list[str]:
    """The regions Unity Catalog lets this caller see, asked of UC as the caller. Read through a
    row-filtered table rather than by calling region_visible() directly: the OBO token's restricted SQL
    scope may not invoke the function itself, but the filter applies to the read exactly as it does to
    every other query this person makes."""
    rows = dbx.run_sql(f"SELECT DISTINCT region FROM {FQ}.loan_accounts", w=_user_client(request))["rows"]
    return sorted(r["region"] for r in rows)


def _case(case_id: int, regions: list[str]) -> dict[str, Any]:
    rows = lakebase.query("SELECT * FROM collections_cases WHERE case_id = %s AND region = ANY(%s)",
                          (case_id, regions))
    if not rows:
        # Same answer for "does not exist" and "not yours": the existence of a case outside your
        # entitlement is itself information.
        raise HTTPException(404, f"case {case_id} not found")
    return rows[0]


def build_cases_router() -> APIRouter:
    router = APIRouter(prefix="/api")

    @router.get("/cases")
    def cases(request: Request, status: Optional[str] = None, limit: int = 100):
        regions = visible_regions(request)
        rows = lakebase.query(
            "SELECT case_id, loan_account_id, region, branch_id, product_code, dpd_days, dpd_bucket, "
            "outstanding_principal, priority_score, priority_rank, drivers, conduct_flags, "
            "recommended_treatment, ai_explanation, ai_recommended_action, status, owner, next_action_date, "
            "updated_by, updated_at, refreshed_at "
            "FROM collections_cases WHERE on_worklist AND region = ANY(%s) "
            "AND (%s::text IS NULL OR status = %s) ORDER BY priority_rank LIMIT %s",
            (regions, status, status, max(1, min(limit, 500))))
        counts = lakebase.query(
            "SELECT status, count(*) AS n FROM collections_cases WHERE on_worklist AND region = ANY(%s) "
            "GROUP BY status", (regions,))
        return {"regions": regions, "cases": rows, "by_status": {r["status"]: r["n"] for r in counts},
                "source": "Lakebase collections_cases, refreshed from gold.collections_priority each cycle; "
                          "scoped to the regions Unity Catalog grants you"}

    @router.get("/cases/{case_id}")
    def case(case_id: int, request: Request):
        c = _case(case_id, visible_regions(request))
        history = lakebase.query("SELECT changed_at, changed_by, change_source, field, old_value, new_value "
                                 "FROM case_history WHERE case_id = %s ORDER BY changed_at DESC, history_id DESC",
                                 (case_id,))
        actions = lakebase.query("SELECT id, action_type, status, requested_by, approved_by, rejected_by, created_at "
                                 "FROM actions WHERE case_id = %s ORDER BY created_at DESC", (case_id,))
        return {"case": c, "history": history, "actions": actions}

    @router.patch("/cases/{case_id}")
    def update_case(case_id: int, upd: CaseUpdate, request: Request):
        _case(case_id, visible_regions(request))
        fields = upd.model_dump(exclude_unset=True)
        if not fields:
            raise HTTPException(400, "nothing to update")
        if "status" in fields and fields["status"] not in STATUSES:
            raise HTTPException(400, f"status must be one of {', '.join(STATUSES)}")
        who = identity.user_email(request)
        # Only human-owned columns can be named here; the column list is fixed, never taken from input.
        sets = ", ".join(f"{k} = %s" for k in fields)
        row = lakebase.execute_as(
            who, f"UPDATE collections_cases SET {sets}, updated_by = %s, updated_at = now() "
                 "WHERE case_id = %s RETURNING *",
            (*fields.values(), who, case_id), returning=True)
        return {"case": row}

    @router.get("/overview")
    def overview(request: Request):
        """The CRO's page: headline risk, conduct and completeness, every number read as the caller."""
        w = _user_client(request)
        kpis = dbx.run_sql(f"""
            WITH m AS (SELECT max(snapshot_month) AS m FROM {FQ}.delinquency_monthly),
            cur AS (SELECT d.* FROM {FQ}.delinquency_monthly d JOIN m ON d.snapshot_month = m.m),
            prev AS (SELECT d.* FROM {FQ}.delinquency_monthly d JOIN m ON d.snapshot_month = add_months(m.m, -1))
            SELECT (SELECT max(snapshot_month) FROM cur) AS as_of_month,
                   round(100 * sum(CASE WHEN is_npa THEN outstanding_principal END) / sum(outstanding_principal), 2) AS gnpa_pct,
                   (SELECT round(100 * sum(CASE WHEN is_npa THEN outstanding_principal END) / sum(outstanding_principal), 2) FROM prev) AS gnpa_pct_prev,
                   round(100 * avg(CASE WHEN roll_direction = 'forward' THEN 1 ELSE 0 END), 2) AS roll_forward_pct,
                   round(sum(CASE WHEN dpd_days > 0 THEN outstanding_principal END)) AS delinquent_outstanding_inr,
                   count_if(dpd_days > 0) AS delinquent_accounts
            FROM cur""", w=w)["rows"][0]
        conduct = dbx.run_sql(f"""
            SELECT count_if(NOT within_rbi_hours) AS out_of_hours_contacts,
                   count(*) AS contacts
            FROM {FQ}.collections_activity
            WHERE activity_date > add_months((SELECT max(snapshot_month) FROM {FQ}.delinquency_monthly), -2)""",
                              w=w)["rows"][0]
        worklist = dbx.run_sql(f"""
            SELECT region, count(*) AS accounts, count_if(open_grievance) AS on_hold_grievance,
                   count_if(size(conduct_flags) > 0) AS with_conduct_flags, round(sum(outstanding_principal)) AS outstanding_inr
            FROM {FQ}.collections_priority GROUP BY region ORDER BY region""", w=w)["rows"]
        completeness = dbx.run_sql(f"""
            SELECT status, count(*) AS files, sum(declared_rows) AS declared_rows, sum(landed_rows) AS landed_rows
            FROM {FQ}.recon_completeness GROUP BY status""", w=w)["rows"]
        breaks = dbx.run_sql(f"""SELECT period, path, break_reason FROM {FQ}.recon_completeness
                                 WHERE status = 'BREAK' ORDER BY period""", w=w)["rows"]
        quality = dbx.run_sql(f"""SELECT entity, check_type, reason, row_count FROM {FQ}.data_quality_summary
                                  ORDER BY row_count DESC""", w=w)["rows"]
        ai = dbx.run_sql(f"""
            SELECT component, prompt_version, judge_version, metric, round(value, 3) AS value
            FROM {FQ}.ai_eval_summary
            QUALIFY rank() OVER (PARTITION BY component ORDER BY evaluated_at DESC) = 1
            ORDER BY component, metric""", w=w)["rows"]
        return {"kpis": kpis, "conduct": conduct, "worklist_by_region": worklist,
                "completeness": completeness, "breaks": breaks, "quality": quality, "ai_quality": ai,
                "journey": [
                    {"stage": "Lakeflow", "what": "18 source feeds landed as files, read incrementally, conformed, "
                                                  "quarantined with reasons, reconciled to sender manifests"},
                    {"stage": "Unity Catalog", "what": "row filters and masks on every gold table, entitlements as data"},
                    {"stage": "AI", "what": "letters triaged in the pipeline; worklist briefs; judged by a different model family"},
                    {"stage": "Lakebase", "what": "the case queue people work, with a trigger-written history"},
                    {"stage": "Genie", "what": "three governed agents answering as the signed-in user"},
                    {"stage": "App", "what": "this screen, the worklist, the case, and the approvals"},
                ]}

    return router
