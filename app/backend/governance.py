"""The governance panel's data — the evidence that the controls are real.

Every function here answers a question a bank's AI CoE will actually ask, and answers it by querying
the platform rather than by describing intent:

  scope()      "What am *I* allowed to see, and how much of the book is that?"
  policies()   "Which row filters, column masks and classifications are actually attached?"
  audit()      "Who asked what, through which surface, and can I prove it?"
  controls()   "Which conduct rules exist, on whose authority, and are they being verified?"

The identity split matters and is deliberate:
  * scope() runs ON BEHALF OF THE USER, because the whole point is to show what that person sees.
  * everything else runs as the app service principal, because a catalogue of the controls must not
    itself be filtered by the caller's scope — otherwise the panel would under-report the controls to
    exactly the people most restricted by them.
"""
from __future__ import annotations

import hashlib
import threading
import time
from typing import Any, Callable

import config
import databricks_client as dbx
import lakebase
from action_plane import guardrails

FQ = config.FQ

# Each panel below is several sequential warehouse queries, which measured 8-13s cold. Catalog
# metadata and audit history do not change second to second, so cache them briefly: the panel becomes
# instant on every view after the first without ever showing data that is meaningfully stale.
# `scope` is deliberately NOT cached across identities — see its cache key.
_CACHE_TTL = 60.0
_cache: dict[str, tuple[float, Any]] = {}
_cache_lock = threading.Lock()


def cached(key: str, produce: Callable[[], Any], ttl: float = _CACHE_TTL) -> Any:
    now = time.monotonic()
    with _cache_lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < ttl:
            return {**hit[1], "cached": True} if isinstance(hit[1], dict) else hit[1]
    value = produce()
    with _cache_lock:
        _cache[key] = (now, value)
    return value


def invalidate() -> None:
    """Drop the cache — called after a kill-switch flip so the panel reflects it immediately."""
    with _cache_lock:
        _cache.clear()

# Tables the row-level policies apply to, with the full row counts captured at generation time. The
# scope panel compares what the CALLER sees against these, which turns "row-level security is
# enabled" into a number the customer can check.
# Verified against the tables on 2026-09-03. If the generator is re-run with a different seed or
# volume these must be re-measured: a wrong total here shows a user "225% visible", which discredits
# the whole panel.
GOVERNED_TABLES = {
    "delinquency_monthly": 108000,
    "collections_activity": 63267,
    "upi_disputes": 26316,
    "complaints": 9660,
    "customer_portfolio": 9000,
    "loan_accounts": 6000,
    "rm_achievement": 3240,
    "recovery_agents": 60,
}


def scope(w=None) -> dict[str, Any]:
    """What the CALLING user is entitled to see. Runs as the caller — that is the point.

    Cached PER IDENTITY. A shared cache here would be a governance bug: the second user to open the
    panel would be shown the first user's entitlements.

    Returns their entitlements, the group memberships the policies key on, and visible-versus-total
    row counts. A user scoped to one region sees the shortfall explicitly rather than being told the
    numbers are bank-wide.
    """
    who = dbx.run_sql("SELECT CURRENT_USER() AS u", w=w)["rows"][0]["u"]
    return cached(f"scope:{who}", lambda: _scope(w))


def _scope(w=None) -> dict[str, Any]:
    entitlements = dbx.run_sql(
        f"""SELECT principal, region, granted_by, CAST(granted_at AS STRING) AS granted_at
            FROM {FQ}.region_entitlement e
            WHERE IS_ACCOUNT_GROUP_MEMBER(e.principal) OR e.principal = CURRENT_USER()
            ORDER BY principal, region""", w=w)["rows"]

    groups = dbx.run_sql(
        f"""SELECT CURRENT_USER() AS identity,
                  IS_ACCOUNT_GROUP_MEMBER('{config.GROUP_PREFIX}_ai_coe')          AS ai_coe,
                  IS_ACCOUNT_GROUP_MEMBER('{config.GROUP_PREFIX}_auditors')        AS auditors,
                  IS_ACCOUNT_GROUP_MEMBER('{config.GROUP_PREFIX}_pii_readers')     AS pii_readers,
                  IS_ACCOUNT_GROUP_MEMBER('{config.GROUP_PREFIX}_collections_ops') AS collections_ops,
                  IS_ACCOUNT_GROUP_MEMBER('{config.GROUP_PREFIX}_grievance_ops')   AS grievance_ops,
                  IS_ACCOUNT_GROUP_MEMBER('{config.GROUP_PREFIX}_rm_managers')     AS rm_managers""",
        w=w)["rows"][0]

    counts_sql = " UNION ALL ".join(
        f"SELECT '{t}' AS table_name, COUNT(*) AS visible FROM {FQ}.{t}"
        for t in GOVERNED_TABLES)
    visible = {r["table_name"]: int(r["visible"])
               for r in dbx.run_sql(counts_sql, w=w)["rows"]}

    tables = [{"table": t, "visible": visible.get(t, 0), "total": total,
               "pct": round(100.0 * visible.get(t, 0) / total, 1) if total else 0.0}
              for t, total in sorted(GOVERNED_TABLES.items())]

    # A masked identifier proves the column mask reached this caller. Taken from a real row so the
    # panel cannot claim masking that is not happening.
    sample = dbx.run_sql(
        f"""SELECT customer_id FROM {FQ}.complaints LIMIT 1""", w=w)["rows"]
    masked_example = sample[0]["customer_id"] if sample else None

    unrestricted = all(t["visible"] >= t["total"] for t in tables)
    return {
        "identity": groups.pop("identity", None),
        "group_memberships": {k: str(v).lower() == "true" for k, v in groups.items()},
        "entitlements": entitlements,
        "tables": tables,
        "unrestricted": unrestricted,
        "masked_customer_id_example": masked_example,
        "note": ("This identity is entitled to the whole book, so the counts match the totals."
                 if unrestricted else
                 "Row filters are narrowing this identity's view; the shortfall below is the filter "
                 "working, not missing data."),
    }


def policies() -> dict[str, Any]:
    return cached("policies", _policies)


def _policies() -> dict[str, Any]:
    """The row filters, column masks and classification tags actually attached in Unity Catalog.

    Read from information_schema, not from our own SQL files: the question is what IS enforced, and a
    file on disk is a claim while the catalog is the fact.
    """
    filters = dbx.run_sql(
        f"""SELECT table_name, filter_name, CAST(target_columns AS STRING) AS on_columns
            FROM {config.CATALOG}.information_schema.row_filters
            WHERE table_schema = '{config.SCHEMA}' ORDER BY table_name""")["rows"]
    masks = dbx.run_sql(
        f"""SELECT table_name, column_name, mask_name
            FROM {config.CATALOG}.information_schema.column_masks
            WHERE table_schema = '{config.SCHEMA}' ORDER BY table_name, column_name""")["rows"]
    col_tags = dbx.run_sql(
        f"""SELECT table_name, column_name, tag_name, tag_value
            FROM {config.CATALOG}.information_schema.column_tags
            WHERE schema_name = '{config.SCHEMA}' ORDER BY table_name, column_name""")["rows"]
    tbl_tags = dbx.run_sql(
        f"""SELECT table_name, tag_name, tag_value
            FROM {config.CATALOG}.information_schema.table_tags
            WHERE schema_name = '{config.SCHEMA}' ORDER BY table_name""")["rows"]
    routines = dbx.run_sql(
        f"""SELECT routine_name, CAST(comment AS STRING) AS comment
            FROM {config.CATALOG}.information_schema.routines
            WHERE specific_schema = '{config.SCHEMA}' ORDER BY routine_name""")["rows"]
    return {"row_filters": filters, "column_masks": masks, "column_tags": col_tags,
            "table_tags": tbl_tags, "functions": routines,
            "summary": {"row_filters": len(filters), "column_masks": len(masks),
                        "tagged_columns": len(col_tags), "tagged_tables": len(tbl_tags),
                        "uc_functions": len(routines)}}


def audit(hours: int = 48, limit: int = 60, caller: str | None = None) -> dict[str, Any]:
    # Keyed on the CALLER, because "your own events first" and "everyone else pseudonymised" are both
    # relative to who is asking. A cache shared across callers would show one person's identity to
    # another.
    return cached(f"audit:{hours}:{limit}:{(caller or '').lower()}",
                  lambda: _audit(hours, limit, caller), ttl=30.0)


def _audit(hours: int, limit: int, caller: str | None = None) -> dict[str, Any]:
    """Recent Genie activity from system.access.audit.

    Tightly filtered on purpose: this is a shared workspace whose audit table holds tens of millions
    of rows per day, so an unbounded scan here would be slow enough to look broken. Note the lag —
    system tables are typically minutes behind, so a question asked seconds ago may not appear yet.
    """
    # THE CALLER'S OWN EVENTS FIRST. This is a shared workspace and colleagues poll Genie constantly,
    # so a plain `ORDER BY event_time DESC` buries the caller's activity under other people's polling —
    # which defeats the point of the panel, which is to let someone confirm that the question they just
    # asked was recorded by the platform independently of this app.
    # The HUMAN caller, not CURRENT_USER(). This query runs as the app service principal, so
    # CURRENT_USER() is the app — and Genie calls made on behalf of a user are attributed in the audit
    # log to that user. Comparing against the app would therefore pseudonymise the caller's OWN events
    # as a stranger's, which is precisely backwards.
    me = (caller or "").lower()
    rows = dbx.run_sql(
        f"""SELECT CAST(event_time AS STRING) AS event_time,
                   user_identity.email AS user_email,
                   action_name,
                   request_params.space_id AS space_id,
                   response.status_code AS status_code
            FROM system.access.audit
            WHERE event_date >= current_date() - INTERVAL {int(hours)} HOURS
              AND service_name = 'aibiGenie'
            ORDER BY (lower(user_identity.email) = :me) DESC, event_time DESC
            LIMIT {int(limit)}""",
        parameters={"me": (me, "STRING")})["rows"]

    # PSEUDONYMISE everyone who is not the caller.
    #
    # This is a shared Databricks workspace, so the raw feed carries colleagues' email addresses and
    # their Genie activity. Putting that on a projector in front of a customer would leak internal
    # identities for no demonstrative benefit — the point of the panel is "the platform records who did
    # what", and a stable pseudonym makes that point exactly as well. The caller sees their own address
    # so they can find themselves in the feed.
    #
    # source_ip_address is dropped entirely: it adds nothing here and is personal data.
    seen: dict[str, str] = {}
    for r in rows:
        email = (r.get("user_email") or "").strip()
        if not email:
            r["user_email"] = "(no identity recorded)"
        elif email.lower() == me:
            r["user_email"] = email
        else:
            if email not in seen:
                # Stable within a response so the same person reads as the same actor down the feed.
                seen[email] = f"other-user-{hashlib.sha256(email.encode()).hexdigest()[:4]}"
            r["user_email"] = seen[email]

    by_action: dict[str, int] = {}
    for r in rows:
        by_action[r["action_name"]] = by_action.get(r["action_name"], 0) + 1
    return {"events": rows, "by_action": by_action, "window_hours": hours,
            "distinct_other_users": len(seen),
            "your_events": sum(1 for r in rows if (r.get("user_email") or "").lower() == me),
            "note": "system.access.audit is the platform's own record, written whether or not this "
                    "app is running. It lags by a few minutes. Your own events are listed first; "
                    "other identities are pseudonymised and source IPs are not shown, because this is "
                    "a shared workspace and the panel's point does not require naming colleagues."}


def controls() -> dict[str, Any]:
    return cached("controls", _controls, ttl=20.0)


def _controls() -> dict[str, Any]:
    """The conduct controls: the policy rows, plus proof the guardrail identity is not blinded."""
    policy_rows = lakebase.query(
        """SELECT action_type, domain, description, max_amount_inr, allowed_regions,
                  requires_approval, approver_role, max_autonomy_level,
                  rbi_conduct_hours, requires_agent_certification, blocked_by_open_grievance,
                  min_dpd_days, max_contacts_per_day, legal_basis
           FROM action_policies ORDER BY domain, action_type""")
    try:
        visibility = guardrails.assert_not_blinded()
    except guardrails.GuardrailsBlinded as e:
        visibility = {"blinded": True, "error": str(e)}
    enabled, why = guardrails.actions_enabled()
    roles = lakebase.query(
        "SELECT principal, array_agg(role ORDER BY role) AS roles FROM approver_roles "
        "GROUP BY principal ORDER BY principal")
    return {"policies": policy_rows, "guardrail_visibility": visibility,
            "kill_switch": {"actions_enabled": enabled, "detail": why},
            "approver_directory": roles}


def set_kill_switch(flag: str, enabled: bool, reason: str, changed_by: str) -> dict[str, Any]:
    """Flip a runtime flag. Stopping the agents is a data change, not a redeploy."""
    if flag not in ("actions_enabled", "autonomy_enabled"):
        raise ValueError(f"unknown flag '{flag}'")
    lakebase.execute(
        "UPDATE runtime_flags SET enabled = %s, reason = %s, changed_by = %s, changed_at = now() "
        "WHERE flag = %s",
        (enabled, reason, changed_by, flag))
    # Invalidate AFTER the write. Clearing first left a window where a concurrent read could repopulate
    # the cache with the OLD state and then show it for the full TTL. Enforcement reads Lakebase
    # directly so this only ever misled the panel, but a governance panel showing the wrong kill-switch
    # state is its own problem.
    invalidate()
    row = lakebase.query(
        "SELECT flag, enabled, reason, changed_by, CAST(changed_at AS TEXT) AS changed_at "
        "FROM runtime_flags WHERE flag = %s", (flag,))
    return row[0] if row else {}


def usage() -> dict[str, Any]:
    """Cost and adoption: what this app has actually asked, and what it cost.

    The question every AI CoE asks second, after 'is it accurate'. Answered from our own session log
    rather than from billing, because per-question attribution is what a budget owner needs and
    billing is aggregated by warehouse.
    """
    turns = lakebase.query(
        """SELECT count(*) AS turns,
                  count(DISTINCT user_email) AS users,
                  round(avg(latency_ms)) AS avg_latency_ms,
                  round(percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_ms)) AS p95_latency_ms,
                  min(created_at)::text AS first_turn,
                  max(created_at)::text AS last_turn
           FROM agent_sessions""")
    by_domain = lakebase.query(
        """SELECT routed_domains, count(*) AS turns, round(avg(latency_ms)) AS avg_latency_ms
           FROM agent_sessions GROUP BY routed_domains ORDER BY turns DESC LIMIT 12""")
    actions = lakebase.query(
        """SELECT action_type, status, count(*) AS n FROM actions
           GROUP BY action_type, status ORDER BY action_type, status""")
    feedback = lakebase.query(
        """SELECT sum(CASE WHEN rating > 0 THEN 1 ELSE 0 END) AS up,
                  sum(CASE WHEN rating < 0 THEN 1 ELSE 0 END) AS down,
                  count(*) AS total FROM agent_feedback""")
    return {"turns": turns[0] if turns else {}, "by_domain": by_domain,
            "actions": actions, "feedback": feedback[0] if feedback else {},
            # Genie is free until 31 Jan 2027; the cost that shows up on the bill is the warehouse
            # under it. Stated here so nobody budgets from the wrong number.
            "note": "Genie Agent messages are not separately billed during the current free period; "
                    "the cost that appears on the bill is the serverless SQL warehouse executing the "
                    "generated queries, plus Model Serving for the router and fuser."}
