"""Create (or update) the three Control Tower Genie Agents as config-as-code.

Why a script and not the UI: the field guide makes config-as-code a *design* decision, not a
productionize afterthought. Everything an agent knows — tables, instructions, join specs, example
SQL, measures and benchmarks — lives here in version control, so the agent is reproducible,
reviewable, and promotable between workspaces.

Usage:
    python3 genie/create_genie_agents.py --list
    python3 genie/create_genie_agents.py --create            # create all three
    python3 genie/create_genie_agents.py --create collections
    python3 genie/create_genie_agents.py --update            # replace config on existing agents

Space ids are written to genie/space_ids.json for the app to consume.

Serialized-space quirks discovered by inspecting a live space (do not "clean these up"):
  * every string-ish field is wrapped in a SINGLE-ELEMENT LIST, e.g. "content": ["..."]
  * a join's relationship type rides in a magic trailing comment inside the sql list:
        "--rt=FROM_RELATIONSHIP_TYPE_MANY_TO_ONE--"
  * "version": 2 at the top level
  * ids are server-assigned; omit them on create
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from databricks.sdk import WorkspaceClient

# Importing config loads .env and validates the workspace-bound names in one place, so this script cannot
# drift from what the app itself resolves.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "app", "backend"))
import config  # noqa: E402

# Auth comes from DATABRICKS_CONFIG_PROFILE / DATABRICKS_HOST, set in .env or the shell.
PROFILE = os.environ.get("DATABRICKS_CONFIG_PROFILE") or None
WAREHOUSE_ID = config.WAREHOUSE_ID
CATALOG = config.CATALOG
SCHEMA = config.SCHEMA

HERE = os.path.dirname(os.path.abspath(__file__))
IDS_PATH = os.path.join(HERE, "space_ids.json")

MANY_TO_ONE = "--rt=FROM_RELATIONSHIP_TYPE_MANY_TO_ONE--"
ONE_TO_ONE = "--rt=FROM_RELATIONSHIP_TYPE_ONE_TO_ONE--"


def fq(table: str) -> str:
    return f"{CATALOG}.{SCHEMA}.{table}"


def L(s: str) -> list[str]:
    """Wrap a string in the single-element list the serialized space expects."""
    return [s]


def eid(*parts: object) -> str:
    """A stable element id. The API demands a lowercase 32-hex UUID without hyphens on every
    sample question, instruction, example SQL, join spec, measure and benchmark. Deriving it from
    the content (rather than uuid4) keeps ids stable across re-runs, so an --update is a genuine
    diff instead of replacing every element with a new id."""
    import hashlib
    key = "|".join(str(p) for p in parts)
    return hashlib.md5(key.encode()).hexdigest()


# ===========================================================================
# Agent definitions
# ===========================================================================

COLLECTIONS = {
    "key": "collections",
    "title": "Collections & Recovery",
    "description": (
        "Loan delinquency, DPD buckets, NPA, roll rates, collections effort and recovery "
        "performance across vehicle finance, microfinance and retail lending. Also audits "
        "RBI recovery-agent conduct rules. Amounts in INR. Data 2025-03 to 2026-08. "
        "ALL DATA SYNTHETIC."
    ),
    "tables": {
        "delinquency_monthly": (
            "PRIMARY TABLE for delinquency, DPD, bucket, NPA and roll-rate questions. Grain is one "
            "row per loan account per month, 2025-03 to 2026-08. ALWAYS aggregate; never return raw "
            "account rows unless a specific account is named. Carries denormalised product_code and "
            "branch_id so product/branch filters need no join. Key columns: snapshot_month, "
            "loan_account_id, product_code, branch_id, dpd_days, dpd_bucket, outstanding_principal, "
            "overdue_amount, is_npa, roll_direction."
        ),
        "loan_accounts": (
            "Loan account master, 6,000 accounts. Use outstanding_principal for exposure/book size; "
            "sanctioned_amount is the ORIGINATION amount, never current exposure. Key columns: "
            "loan_account_id, customer_id, product_code, branch_id, disbursed_date, "
            "sanctioned_amount, outstanding_principal, interest_rate, tenure_months, emi_amount, "
            "customer_segment, is_restructured."
        ),
        "collections_activity": (
            "One row per collections CONTACT ATTEMPT, not per account. Carries contact_hour and "
            "within_rbi_hours for RBI conduct auditing: borrower contact is permitted only between "
            "08:00 and 19:00. Key columns: activity_id, activity_date, contact_hour, "
            "loan_account_id, product_code, branch_id, agent_id, channel, outcome, "
            "promise_to_pay_amount, amount_collected, within_rbi_hours."
        ),
        "recovery_agents": (
            "Field recovery agents employed via collection agencies. rbi_conduct_certified must be "
            "TRUE before an agent may be assigned a borrower visit; treat a certification_expiry "
            "earlier than the visit date as uncertified. Key columns: agent_id, agent_name, "
            "agency_name, branch_id, region, rbi_conduct_certified, certification_expiry, "
            "active_flag, complaints_against_ytd."
        ),
        "repayment_schedule": (
            "Per-loan repayment position: next_due_date, emis_paid, emis_pending, last payment and "
            "mandate_type (NACH, Cheque, Cash, UPI Autopay). One row per amortising loan. Use for "
            "'due this week' style questions."
        ),
        "branch_master": (
            "Branch dimension: branch_id, branch_name, city, state, region (North/South/East/West/"
            "Central), zone (Metro/Urban/Semi-Urban/Rural). Join only when the question needs city, "
            "state, region or zone."
        ),
    },
    "instructions": """### Space metadata
You answer questions about loan collections and recovery for an Indian retail and commercial bank.
All amounts are Indian Rupees (INR). All data is synthetic. The data covers 2025-03-01 to
2026-08-01 and the current month is 2026-08-01. When a question says "now", "current", "latest"
or "this month", use snapshot_month = DATE'2026-08-01'.
If the question names NO period at all, use the FULL data window and say so. Do not narrow to the
current month unless the question asks for it — a silently injected period can reverse the answer to
a "which is highest" question, and the user has no way to see that it happened.

### Data foundation
delinquency_monthly is the primary table for anything about delinquency, DPD, buckets, NPA or roll
rates. Its grain is one row per loan account per month, so ALWAYS aggregate; never return raw
account-level rows unless the user explicitly names an account.
loan_accounts holds the current book. Use outstanding_principal for exposure, book size and
portfolio value. Never use sanctioned_amount for current exposure; that is the origination amount.
collections_activity holds one row per contact attempt, not per account.
Both delinquency_monthly and collections_activity already carry product_code and branch_id, so do
not join to loan_accounts merely to filter on product or branch.

### Business terminology
DPD means days past due. DPD of 0 means the account is current.
Buckets are "0-Current", "1-SMA0 (1-30)", "2-SMA1 (31-60)", "3-SMA2 (61-90)", "4-NPA (90+)".
SMA means Special Mention Account. Bucket 2 means '2-SMA1 (31-60)'.
NPA means Non-Performing Asset, dpd_days > 90, available as the is_npa flag.
GNPA percentage means SUM(CASE WHEN is_npa THEN outstanding_principal ELSE 0 END) /
SUM(outstanding_principal) * 100.
Delinquency rate means the share of ACCOUNTS with dpd_days > 0, unless the user says "by value",
in which case weight by outstanding_principal.
Roll-forward rate means the share of accounts with roll_direction = 'forward' in that month.
PTP means promise to pay: rows where outcome = 'Contacted - PTP'.
Recovery rate means SUM(amount_collected) / SUM(overdue_amount) for the same scope and period.
Collections effort means the count of rows in collections_activity, i.e. contact attempts.
Contactability means the share of attempts whose outcome is neither 'Not Reachable' nor
'Wrong Number'.
MFI is the Microfinance Group Loan product (product_code = 'MFI'). CV is the Commercial Vehicle
Loan product (product_code = 'CV'). Vehicle Finance as a segment covers CV, PV and TW.

### RBI conduct rules
RBI permits borrower contact only between 08:00 and 19:00. collections_activity.contact_hour is the
hour in 24-hour clock and within_rbi_hours is TRUE when contact fell inside that window. Questions
about conduct or breaches must use within_rbi_hours = FALSE for out-of-hours contact, and
recovery_agents.rbi_conduct_certified = FALSE for uncertified agents.

### CRITICAL response standards
ALWAYS STATE THE COMPUTED ANSWER IN WORDS, as a number, before anything else. If you want to offer a
breakdown, state the answer first and then offer it. Never reply with only a follow-up question: the
result grid is not the answer a person reads, and a reply that asks "would you prefer this by card
type?" without giving the figure has answered nothing.
When the question names a value that exists LITERALLY in a column, filter on exactly that value. Do
not widen it to related values. "Affluent customers" means customer_segment = 'Affluent', not
Affluent plus Private plus Mass Affluent. If you believe the wider reading is what was meant, give
the exact answer first, then say what the wider figure would be and that it is a different question.
Always state the scope you applied: the month or date range, the product, and the region or branch.
Row-level security is enforced, so different users legitimately see different rows and an unstated
scope is misleading.
Round percentages to one decimal place. Format INR with thousands separators; use crore only above
10,000,000 (1 crore = 10,000,000).
If a result would exceed 200 rows, aggregate further or apply a LIMIT and say so explicitly.
NEVER state a total you did not compute in SQL. Quote only the aggregates the query returned.
When asked WHY something moved, compare the affected slice against a control slice (other branches,
other products, or the prior period) rather than describing the affected slice alone.

### Error handling
If a question needs a column that does not exist in these six tables, say which column is missing
rather than substituting a similar one.
If a question spans customer complaints, RBI ombudsman cases, or relationship-manager incentives,
say it belongs to a different domain agent and do not guess from these tables.""",
    "joins": [
        ("delinquency_monthly", "loan_accounts", "`delinquency_monthly`.`loan_account_id` = `loan_accounts`.`loan_account_id`", MANY_TO_ONE),
        ("collections_activity", "loan_accounts", "`collections_activity`.`loan_account_id` = `loan_accounts`.`loan_account_id`", MANY_TO_ONE),
        ("collections_activity", "recovery_agents", "`collections_activity`.`agent_id` = `recovery_agents`.`agent_id`", MANY_TO_ONE),
        ("repayment_schedule", "loan_accounts", "`repayment_schedule`.`loan_account_id` = `loan_accounts`.`loan_account_id`", ONE_TO_ONE),
        ("loan_accounts", "branch_master", "`loan_accounts`.`branch_id` = `branch_master`.`branch_id`", MANY_TO_ONE),
        ("delinquency_monthly", "branch_master", "`delinquency_monthly`.`branch_id` = `branch_master`.`branch_id`", MANY_TO_ONE),
        ("collections_activity", "branch_master", "`collections_activity`.`branch_id` = `branch_master`.`branch_id`", MANY_TO_ONE),
    ],
    "measures": [
        ("delinquency_rate_pct", "delinquency rate percent",
         "100.0 * SUM(CASE WHEN delinquency_monthly.dpd_days > 0 THEN 1 ELSE 0 END) / COUNT(*)",
         "WHEN_TO_USE: the share of accounts that are delinquent. SCOPE_TABLES: delinquency_monthly. "
         "RISK_IF_MISUSED: this is account-weighted; if the user asks 'by value' use the "
         "outstanding_principal-weighted form instead."),
        ("gnpa_pct", "gross NPA percent",
         "100.0 * SUM(CASE WHEN delinquency_monthly.is_npa THEN delinquency_monthly.outstanding_principal ELSE 0 END) / SUM(delinquency_monthly.outstanding_principal)",
         "WHEN_TO_USE: gross NPA as a share of exposure. SCOPE_TABLES: delinquency_monthly. "
         "RISK_IF_MISUSED: always value-weighted, never account-weighted. Always filter to a single "
         "snapshot_month or the figure double counts across months."),
        ("roll_forward_pct", "roll forward percent",
         "100.0 * SUM(CASE WHEN delinquency_monthly.roll_direction = 'forward' THEN 1 ELSE 0 END) / COUNT(*)",
         "WHEN_TO_USE: bucket deterioration rate month on month. SCOPE_TABLES: delinquency_monthly. "
         "RISK_IF_MISUSED: filter to a specific dpd_bucket when the user asks about a named bucket."),
    ],
    "samples": [
        "What is the delinquency rate by product this month?",
        "Why did microfinance delinquency jump in Solapur?",
        "Which city has the worst commercial vehicle delinquency, and how does it compare with the rest of the book?",
        "What is the GNPA percentage by region?",
        "Show contact attempts that breached RBI permitted hours, by agency.",
        "Which recovery agents are not RBI conduct certified but still made contact this year?",
        "What is the bucket-2 roll-forward rate for microfinance by month?",
    ],
    "examples": [
        ("What is the delinquency rate by product for the latest month?",
         f"""SELECT product_code, COUNT(*) AS accounts,
       SUM(CASE WHEN dpd_days > 0 THEN 1 ELSE 0 END) AS delinquent_accounts,
       ROUND(100.0 * SUM(CASE WHEN dpd_days > 0 THEN 1 ELSE 0 END) / COUNT(*), 1) AS delinquency_pct
FROM {fq('delinquency_monthly')}
WHERE snapshot_month = DATE'2026-08-01'
GROUP BY product_code ORDER BY delinquency_pct DESC"""),
        ("Show the microfinance delinquency trend in Solapur over the last 12 months.",
         f"""SELECT d.snapshot_month, COUNT(*) AS accounts,
       ROUND(100.0 * SUM(CASE WHEN d.dpd_days > 0 THEN 1 ELSE 0 END) / COUNT(*), 1) AS delinquency_pct
FROM {fq('delinquency_monthly')} d
JOIN {fq('branch_master')} b ON d.branch_id = b.branch_id
WHERE d.product_code = 'MFI' AND b.city = 'Solapur' AND d.snapshot_month >= DATE'2025-09-01'
GROUP BY d.snapshot_month ORDER BY d.snapshot_month"""),
        ("Which branches have the worst commercial vehicle delinquency this month versus the whole book?",
         f"""WITH cv AS (
  SELECT d.branch_id, b.city, b.region, COUNT(*) AS accounts,
         SUM(CASE WHEN d.dpd_days > 0 THEN 1 ELSE 0 END) AS delinquent
  FROM {fq('delinquency_monthly')} d
  JOIN {fq('branch_master')} b ON d.branch_id = b.branch_id
  WHERE d.product_code = 'CV' AND d.snapshot_month = DATE'2026-08-01'
  GROUP BY d.branch_id, b.city, b.region)
SELECT city, region, accounts, delinquent,
       ROUND(100.0 * delinquent / accounts, 1) AS delinquency_pct,
       ROUND(100.0 * SUM(delinquent) OVER () / SUM(accounts) OVER (), 1) AS book_delinquency_pct
FROM cv ORDER BY delinquency_pct DESC LIMIT 10"""),
        ("What is the GNPA percentage by region for the latest month?",
         f"""SELECT b.region,
       ROUND(SUM(CASE WHEN d.is_npa THEN d.outstanding_principal ELSE 0 END), 2) AS npa_exposure_inr,
       ROUND(SUM(d.outstanding_principal), 2) AS total_exposure_inr,
       ROUND(100.0 * SUM(CASE WHEN d.is_npa THEN d.outstanding_principal ELSE 0 END)
                   / SUM(d.outstanding_principal), 1) AS gnpa_pct
FROM {fq('delinquency_monthly')} d
JOIN {fq('branch_master')} b ON d.branch_id = b.branch_id
WHERE d.snapshot_month = DATE'2026-08-01'
GROUP BY b.region ORDER BY gnpa_pct DESC"""),
        ("What is the bucket-2 roll-forward rate for microfinance by month?",
         f"""SELECT snapshot_month, COUNT(*) AS accounts_in_bucket,
       SUM(CASE WHEN roll_direction = 'forward' THEN 1 ELSE 0 END) AS rolled_forward,
       ROUND(100.0 * SUM(CASE WHEN roll_direction = 'forward' THEN 1 ELSE 0 END) / COUNT(*), 1) AS roll_forward_pct
FROM {fq('delinquency_monthly')}
WHERE product_code = 'MFI' AND dpd_bucket = '2-SMA1 (31-60)'
GROUP BY snapshot_month ORDER BY snapshot_month"""),
        ("How much collections effort went into Solapur microfinance versus recovery achieved?",
         f"""SELECT DATE_TRUNC('MONTH', a.activity_date) AS activity_month,
       COUNT(*) AS contact_attempts, COUNT(DISTINCT a.loan_account_id) AS accounts_touched,
       SUM(CASE WHEN a.outcome = 'Contacted - PTP' THEN 1 ELSE 0 END) AS ptp_count,
       ROUND(SUM(a.amount_collected), 2) AS collected_inr
FROM {fq('collections_activity')} a
JOIN {fq('branch_master')} b ON a.branch_id = b.branch_id
WHERE a.product_code = 'MFI' AND b.city = 'Solapur' AND a.activity_date >= DATE'2025-09-01'
GROUP BY DATE_TRUNC('MONTH', a.activity_date) ORDER BY activity_month"""),
        ("Show contact attempts that breached RBI permitted hours, by branch and agency.",
         f"""SELECT b.city, r.agency_name, COUNT(*) AS out_of_hours_contacts,
       COUNT(DISTINCT a.agent_id) AS agents_involved,
       MIN(a.contact_hour) AS earliest_hour, MAX(a.contact_hour) AS latest_hour
FROM {fq('collections_activity')} a
JOIN {fq('recovery_agents')} r ON a.agent_id = r.agent_id
JOIN {fq('branch_master')} b ON a.branch_id = b.branch_id
WHERE a.within_rbi_hours = FALSE
GROUP BY b.city, r.agency_name ORDER BY out_of_hours_contacts DESC LIMIT 20"""),
        ("Which recovery agents are not RBI conduct certified but still made contact this year?",
         f"""SELECT r.agent_id, r.agent_name, r.agency_name, r.certification_expiry,
       r.complaints_against_ytd, COUNT(a.activity_id) AS contacts_made
FROM {fq('recovery_agents')} r
JOIN {fq('collections_activity')} a ON a.agent_id = r.agent_id
WHERE r.rbi_conduct_certified = FALSE AND a.activity_date >= DATE'2026-01-01'
GROUP BY r.agent_id, r.agent_name, r.agency_name, r.certification_expiry, r.complaints_against_ytd
ORDER BY contacts_made DESC"""),
    ],
    "benchmarks": [
        ("What is the delinquency rate by product as of 2026-08-01?",
         f"""SELECT product_code, ROUND(100.0 * SUM(CASE WHEN dpd_days > 0 THEN 1 ELSE 0 END) / COUNT(*), 1) AS delinquency_pct
FROM {fq('delinquency_monthly')} WHERE snapshot_month = DATE'2026-08-01'
GROUP BY product_code ORDER BY delinquency_pct DESC"""),
        ("What was the microfinance delinquency percentage in Solapur in May 2026?",
         f"""SELECT ROUND(100.0 * SUM(CASE WHEN d.dpd_days > 0 THEN 1 ELSE 0 END) / COUNT(*), 1) AS delinquency_pct
FROM {fq('delinquency_monthly')} d JOIN {fq('branch_master')} b ON d.branch_id = b.branch_id
WHERE d.product_code = 'MFI' AND b.city = 'Solapur' AND d.snapshot_month = DATE'2026-05-01'"""),
        ("What is the GNPA percentage by region as of 2026-08-01?",
         f"""SELECT b.region, ROUND(100.0 * SUM(CASE WHEN d.is_npa THEN d.outstanding_principal ELSE 0 END) / SUM(d.outstanding_principal), 1) AS gnpa_pct
FROM {fq('delinquency_monthly')} d JOIN {fq('branch_master')} b ON d.branch_id = b.branch_id
WHERE d.snapshot_month = DATE'2026-08-01' GROUP BY b.region ORDER BY gnpa_pct DESC"""),
        ("Which city had the highest commercial vehicle delinquency rate in May 2026?",
         f"""SELECT b.city, ROUND(100.0 * SUM(CASE WHEN d.dpd_days > 0 THEN 1 ELSE 0 END) / COUNT(*), 1) AS delinquency_pct
FROM {fq('delinquency_monthly')} d JOIN {fq('branch_master')} b ON d.branch_id = b.branch_id
WHERE d.product_code = 'CV' AND d.snapshot_month = DATE'2026-05-01'
GROUP BY b.city ORDER BY delinquency_pct DESC LIMIT 1"""),
        ("How many collections contact attempts breached the RBI permitted hours window?",
         f"SELECT COUNT(*) AS out_of_hours_contacts FROM {fq('collections_activity')} WHERE within_rbi_hours = FALSE"),
        ("How many recovery agents are not RBI conduct certified?",
         f"SELECT COUNT(*) AS uncertified_agents FROM {fq('recovery_agents')} WHERE rbi_conduct_certified = FALSE"),
        ("What was the bucket-2 roll-forward percentage for microfinance in May 2026?",
         f"""SELECT ROUND(100.0 * SUM(CASE WHEN roll_direction = 'forward' THEN 1 ELSE 0 END) / COUNT(*), 1) AS roll_forward_pct
FROM {fq('delinquency_monthly')}
WHERE product_code = 'MFI' AND dpd_bucket = '2-SMA1 (31-60)' AND snapshot_month = DATE'2026-05-01'"""),
        ("What was the total amount collected from Solapur microfinance accounts in June 2026?",
         f"""SELECT ROUND(SUM(a.amount_collected), 2) AS collected_inr
FROM {fq('collections_activity')} a JOIN {fq('branch_master')} b ON a.branch_id = b.branch_id
WHERE a.product_code = 'MFI' AND b.city = 'Solapur'
  AND a.activity_date BETWEEN DATE'2026-06-01' AND DATE'2026-06-30'"""),
        ("Which three agencies have the most out-of-hours contact attempts?",
         f"""SELECT r.agency_name, COUNT(*) AS out_of_hours_contacts
FROM {fq('collections_activity')} a JOIN {fq('recovery_agents')} r ON a.agent_id = r.agent_id
WHERE a.within_rbi_hours = FALSE GROUP BY r.agency_name ORDER BY out_of_hours_contacts DESC LIMIT 3"""),
        ("What is the total outstanding principal on microfinance loans as of 2026-08-01?",
         f"""SELECT ROUND(SUM(outstanding_principal), 2) AS exposure_inr
FROM {fq('delinquency_monthly')} WHERE product_code = 'MFI' AND snapshot_month = DATE'2026-08-01'"""),
    ],
}

GRIEVANCE = {
    "key": "grievance",
    "title": "Service & Grievance",
    "description": (
        "Customer complaints, SLA performance against the RBI Integrated Ombudsman Scheme, UPI "
        "transaction disputes and card chargebacks. Amounts in INR. Data 2025-03 to 2026-08. "
        "ALL DATA SYNTHETIC."
    ),
    "tables": {
        "complaints": (
            "PRIMARY TABLE for complaint-level questions: severity, channel, repeat complainants, "
            "ombudsman escalation, complaint text. One row per complaint. Note the UPI complaint "
            "spike on 2026-06-16 to 18, two days after a UPI switch degradation on 2026-06-14/15. "
            "Key columns: complaint_id, received_date, channel, category_code, customer_id, "
            "branch_id, product_code, severity, status, resolved_date, days_to_resolve, sla_days, "
            "sla_breached, escalated_to_ombudsman, repeat_complainant, complaint_text."
        ),
        "sla_tracker": (
            "PRE-AGGREGATED monthly complaint SLA performance by branch and RBI category. PREFER "
            "THIS over raw complaints for trends and breach rates: results stay small so they "
            "cannot be silently truncated. Carries region already. Key columns: report_month, "
            "branch_id, region, rbi_category, complaints_received, complaints_resolved, within_sla, "
            "breached_sla, avg_days_to_resolve, ombudsman_escalations."
        ),
        "complaint_categories": (
            "Category dimension mapping internal codes to RBI Ombudsman grounds with the SLA in "
            "days. Codes: UPI, PAY, CRD, LON, DEP, MIS, REC, ATM, KYC, CHG. Key columns: "
            "category_code, category_name, rbi_category, sla_days."
        ),
        "upi_disputes": (
            "UPI dispute lifecycle, SEPARATE from complaints — do not assume a one-to-one link. "
            "auto_refunded reflects the NPCI rule that timed-out or declined UPI transactions "
            "reverse within 30 seconds. Switch degradation on 2026-06-14/15 produced ~10x volume "
            "and collapsed the auto-refund rate from ~78% to ~35%. Key columns: dispute_id, "
            "txn_date, raised_date, customer_id, branch_id, txn_amount, failure_reason, "
            "resolution_path, auto_refunded, resolution_seconds, status, psp_handle."
        ),
        "chargebacks": (
            "Card chargebacks only, not UPI. Key columns: chargeback_id, txn_date, raised_date, "
            "customer_id, card_type, merchant_category, txn_amount, reason_code, liability, status "
            "(Won/Lost/Open/Withdrawn), days_open, recovered_amount."
        ),
        "branch_master": (
            "Branch dimension: branch_id, branch_name, city, state, region, zone. Join only for "
            "city, state, region or zone."
        ),
    },
    "instructions": """### Space metadata
You answer questions about customer complaints, grievance redressal, UPI disputes and card
chargebacks for an Indian retail bank. All amounts are Indian Rupees (INR). All data is synthetic.
The data covers 2025-03-01 to 2026-08-31 and the current month is 2026-08. When a question says
"now", "current", "latest" or "this month", use August 2026.
If the question names NO period at all, use the FULL data window and say so. Do not narrow to the
current month unless the question asks for it — a silently injected period can reverse the answer to
a "which is highest" question, and the user has no way to see that it happened.

### Data foundation
For complaint TRENDS, SLA BREACH RATES and regulatory roll-ups, PREFER sla_tracker. It is already
aggregated by month, branch and RBI category, so results stay small and cannot be silently
truncated. Use the raw complaints table only when the question needs complaint-level detail such as
severity, channel, repeat complainants, or complaint text.
An open complaint has status = 'Open' with NULL resolved_date and NULL days_to_resolve.
upi_disputes is separate from complaints. A UPI dispute may or may not also become a complaint; do
not assume a one-to-one relationship.
chargebacks covers card disputes only, never UPI.

### Business terminology
SLA breach means the complaint took longer than its category SLA to resolve, or is still open past
that SLA. sla_breached covers BOTH cases and is computed as of 2026-08-31: for a resolved complaint it
compares days_to_resolve against sla_days, and for an open one it ages received_date against sla_days.
So sla_breached is the right column for "how many breached", open or closed, and on open complaints it
agrees exactly with DATEDIFF(DATE'2026-08-31', received_date) > sla_days.
Recompute by ageing ONLY when the question asks as of a DIFFERENT date, and say which date you used.
SLA breach rate means breached_sla / complaints_received from sla_tracker. Use complaints_received,
NOT complaints_resolved: breached_sla counts every breach including complaints still open, and
within_sla + breached_sla = complaints_received, so received is the denominator that reconciles.
complaints_resolved can also be zero for a branch-month, which makes that ratio divide by zero.
sla_tracker is a genuine rollup of complaints, so the two tables agree: summing complaints_received gives
exactly the complaints row count for the same scope. Prefer sla_tracker for month/branch/category
roll-ups and complaints when you need per-complaint detail.
RBI CMS means the RBI Complaint Management System; channel = 'RBI CMS' is a regulatory escalation.
Ombudsman escalation means escalated_to_ombudsman = TRUE — the most serious outcome.
Ageing means days a complaint has been open: DATEDIFF(DATE'2026-08-31', received_date) for open ones.
Auto-refund rate means the share of UPI disputes with auto_refunded = TRUE. A falling rate means
manual investigation load is rising.
Chargeback win rate means Won / (Won + Lost), excluding Open and Withdrawn.
TAT means turnaround time, the same as days_to_resolve.
RBI grounds of complaint are the values in rbi_category: Payment systems, Cards, Loans and
advances, Deposit accounts, Mis-selling, Recovery agents, Levy of charges, Other.
The product a complaint relates to is complaints.product_code. The codes are:
MFI = Microfinance Group Loan (say "microfinance"), CV = Commercial Vehicle Loan, PV = Passenger
Vehicle Loan, TW = Two Wheeler Loan, HL = Home Loan, PL = Personal Loan, BL = Business Loan,
CC = Credit Card. upi_disputes and chargebacks also carry product_code.
A question about complaints FROM a particular product's customers is IN SCOPE: filter on product_code
and, for a city or region, join branch_master. "Are microfinance customers in Solapur complaining
more" is answered here as complaints WHERE product_code = 'MFI' joined to branch_master WHERE
city = 'Solapur'.

### Known incident
A UPI switch degradation occurred on 2026-06-14 and 2026-06-15. On those days UPI dispute volume
was roughly ten times normal and the auto-refund rate fell from about 78 percent to about 35
percent. The resulting complaints arrived two days later, 2026-06-16 to 2026-06-18, and
payment-systems SLA breaches spiked that month. When asked why complaints or breaches rose in June
2026, investigate that chain rather than describing the spike alone.

### CRITICAL response standards
ALWAYS STATE THE COMPUTED ANSWER IN WORDS, as a number, before anything else. If you want to offer a
breakdown, state the answer first and then offer it. Never reply with only a follow-up question: the
result grid is not the answer a person reads, and a reply that asks "would you prefer this by card
type?" without giving the figure has answered nothing.
When the question names a value that exists LITERALLY in a column, filter on exactly that value. Do
not widen it to related values. "Affluent customers" means customer_segment = 'Affluent', not
Affluent plus Private plus Mass Affluent. If you believe the wider reading is what was meant, give
the exact answer first, then say what the wider figure would be and that it is a different question.
Always state the scope: the month or date range, the category, and the branch or region. Row-level
security is enforced, so different users legitimately see different totals.
Round percentages to one decimal place. Format INR with thousands separators.
NEVER quote a total you did not compute in SQL.
When asked WHY, compare the affected slice against a control slice or the prior period.
If a result would exceed 200 rows, aggregate further or LIMIT and say so.

### Error handling
If a question needs a column not present in these six tables, name the missing column rather than
substituting a similar one.
If a question is about loan delinquency, DPD buckets, recovery-agent performance, or
relationship-manager incentives, say it belongs to a different domain agent. But do NOT decline a
question merely because it names a lending product: complaint volume, SLA breach and ombudsman
exposure FOR a product's customers is this agent's own subject. Decline only the delinquency or
recovery METRICS themselves.""",
    "joins": [
        ("complaints", "complaint_categories", "`complaints`.`category_code` = `complaint_categories`.`category_code`", MANY_TO_ONE),
        ("complaints", "branch_master", "`complaints`.`branch_id` = `branch_master`.`branch_id`", MANY_TO_ONE),
        ("sla_tracker", "branch_master", "`sla_tracker`.`branch_id` = `branch_master`.`branch_id`", MANY_TO_ONE),
        ("upi_disputes", "branch_master", "`upi_disputes`.`branch_id` = `branch_master`.`branch_id`", MANY_TO_ONE),
    ],
    "measures": [
        ("sla_breach_pct", "SLA breach percent",
         "100.0 * SUM(sla_tracker.breached_sla) / NULLIF(SUM(sla_tracker.complaints_received), 0)",
         "WHEN_TO_USE: the headline regulatory metric for grievance redressal. SCOPE_TABLES: "
         "sla_tracker. RISK_IF_MISUSED: the denominator is complaints_received, NOT "
         "complaints_resolved. breached_sla counts every breach including complaints still open, so "
         "within_sla + breached_sla = complaints_received and received is the denominator that "
         "reconciles; complaints_resolved is also zero for some branch-months, which divides by zero."),
        ("auto_refund_pct", "UPI auto-refund percent",
         "100.0 * SUM(CASE WHEN upi_disputes.auto_refunded THEN 1 ELSE 0 END) / COUNT(*)",
         "WHEN_TO_USE: UPI dispute automation efficiency. SCOPE_TABLES: upi_disputes. "
         "RISK_IF_MISUSED: do not apply to complaints or chargebacks; auto-refund is UPI-only."),
        ("chargeback_win_pct", "chargeback win percent",
         "100.0 * SUM(CASE WHEN chargebacks.status = 'Won' THEN 1 ELSE 0 END) / NULLIF(SUM(CASE WHEN chargebacks.status IN ('Won','Lost') THEN 1 ELSE 0 END), 0)",
         "WHEN_TO_USE: card dispute outcome quality. SCOPE_TABLES: chargebacks. RISK_IF_MISUSED: "
         "Open and Withdrawn cases must be excluded from the denominator."),
    ],
    "samples": [
        "What is the SLA breach rate by RBI category this month?",
        "Why did payment-systems complaints spike in June 2026?",
        "What happened to UPI disputes on 14 and 15 June 2026?",
        "Which branches have the most open complaints past SLA?",
        "How many complaints escalated to the RBI Ombudsman, by category?",
        "What is the chargeback win rate by merchant category?",
        "How many complaints arrived through the RBI CMS channel?",
    ],
    "examples": [
        ("Are microfinance customers in Solapur complaining more this year?",
         f"""SELECT DATE_TRUNC('MONTH', c.received_date) AS month, COUNT(*) AS complaints,
       SUM(CASE WHEN c.sla_breached THEN 1 ELSE 0 END) AS breached,
       SUM(CASE WHEN c.category_code = 'REC' THEN 1 ELSE 0 END) AS recovery_conduct_complaints,
       SUM(CASE WHEN c.escalated_to_ombudsman THEN 1 ELSE 0 END) AS ombudsman
FROM {fq('complaints')} c
JOIN {fq('branch_master')} b ON c.branch_id = b.branch_id
WHERE c.product_code = 'MFI' AND b.city = 'Solapur'
GROUP BY DATE_TRUNC('MONTH', c.received_date)
ORDER BY month"""),
        ("What is the SLA breach rate by RBI category for the latest month?",
         f"""SELECT rbi_category, SUM(complaints_received) AS received, SUM(complaints_resolved) AS resolved,
       SUM(breached_sla) AS breached,
       ROUND(100.0 * SUM(breached_sla) / NULLIF(SUM(complaints_received), 0), 1) AS breach_pct
FROM {fq('sla_tracker')} WHERE report_month = DATE'2026-08-01'
GROUP BY rbi_category ORDER BY breach_pct DESC"""),
        ("Show the payment-systems SLA breach rate by month over the last year.",
         f"""SELECT report_month, SUM(complaints_resolved) AS resolved, SUM(breached_sla) AS breached,
       ROUND(100.0 * SUM(breached_sla) / NULLIF(SUM(complaints_received), 0), 1) AS breach_pct
FROM {fq('sla_tracker')} WHERE rbi_category = 'Payment systems' AND report_month >= DATE'2025-09-01'
GROUP BY report_month ORDER BY report_month"""),
        ("What happened to UPI disputes in June 2026, day by day?",
         f"""SELECT txn_date, COUNT(*) AS disputes,
       SUM(CASE WHEN auto_refunded THEN 1 ELSE 0 END) AS auto_refunded,
       ROUND(100.0 * SUM(CASE WHEN auto_refunded THEN 1 ELSE 0 END) / COUNT(*), 1) AS auto_refund_pct,
       SUM(CASE WHEN failure_reason = 'Switch degradation' THEN 1 ELSE 0 END) AS switch_degradation
FROM {fq('upi_disputes')} WHERE txn_date BETWEEN DATE'2026-06-01' AND DATE'2026-06-30'
GROUP BY txn_date ORDER BY txn_date"""),
        ("Did the June UPI incident drive a complaint spike, and how long after?",
         f"""SELECT received_date, COUNT(*) AS upi_complaints,
       SUM(CASE WHEN sla_breached THEN 1 ELSE 0 END) AS breached,
       ROUND(AVG(days_to_resolve), 1) AS avg_tat_days
FROM {fq('complaints')} WHERE category_code = 'UPI'
  AND received_date BETWEEN DATE'2026-06-10' AND DATE'2026-06-25'
GROUP BY received_date ORDER BY received_date"""),
        ("Which branches have the most open complaints past SLA right now?",
         f"""SELECT b.city, b.region, COUNT(*) AS open_complaints,
       SUM(CASE WHEN DATEDIFF(DATE'2026-08-31', c.received_date) > c.sla_days THEN 1 ELSE 0 END) AS past_sla,
       ROUND(AVG(DATEDIFF(DATE'2026-08-31', c.received_date)), 1) AS avg_age_days
FROM {fq('complaints')} c JOIN {fq('branch_master')} b ON c.branch_id = b.branch_id
WHERE c.status = 'Open' GROUP BY b.city, b.region ORDER BY past_sla DESC LIMIT 15"""),
        ("How many complaints were escalated to the RBI Ombudsman, by category?",
         f"""SELECT cc.rbi_category, cc.category_name, COUNT(*) AS complaints,
       SUM(CASE WHEN c.escalated_to_ombudsman THEN 1 ELSE 0 END) AS escalations,
       ROUND(100.0 * SUM(CASE WHEN c.escalated_to_ombudsman THEN 1 ELSE 0 END) / COUNT(*), 2) AS escalation_pct
FROM {fq('complaints')} c JOIN {fq('complaint_categories')} cc ON c.category_code = cc.category_code
GROUP BY cc.rbi_category, cc.category_name ORDER BY escalations DESC"""),
        ("What is the chargeback win rate by merchant category?",
         f"""SELECT merchant_category, COUNT(*) AS cases,
       SUM(CASE WHEN status = 'Won' THEN 1 ELSE 0 END) AS won,
       SUM(CASE WHEN status = 'Lost' THEN 1 ELSE 0 END) AS lost,
       ROUND(100.0 * SUM(CASE WHEN status = 'Won' THEN 1 ELSE 0 END)
             / NULLIF(SUM(CASE WHEN status IN ('Won','Lost') THEN 1 ELSE 0 END), 0), 1) AS win_rate_pct
FROM {fq('chargebacks')} GROUP BY merchant_category ORDER BY cases DESC"""),
    ],
    "benchmarks": [
        ("What is the SLA breach rate by RBI category for August 2026?",
         f"""SELECT rbi_category, ROUND(100.0 * SUM(breached_sla) / NULLIF(SUM(complaints_received), 0), 1) AS breach_pct
FROM {fq('sla_tracker')} WHERE report_month = DATE'2026-08-01' GROUP BY rbi_category ORDER BY breach_pct DESC"""),
        ("What was the payment-systems SLA breach percentage in June 2026?",
         f"""SELECT ROUND(100.0 * SUM(breached_sla) / NULLIF(SUM(complaints_received), 0), 1) AS breach_pct
FROM {fq('sla_tracker')} WHERE rbi_category = 'Payment systems' AND report_month = DATE'2026-06-01'"""),
        ("How many UPI disputes were raised on 14 June 2026?",
         f"SELECT COUNT(*) AS disputes FROM {fq('upi_disputes')} WHERE txn_date = DATE'2026-06-14'"),
        ("What was the UPI auto-refund percentage on 15 June 2026?",
         f"""SELECT ROUND(100.0 * SUM(CASE WHEN auto_refunded THEN 1 ELSE 0 END) / COUNT(*), 1) AS auto_refund_pct
FROM {fq('upi_disputes')} WHERE txn_date = DATE'2026-06-15'"""),
        ("How many UPI complaints were received on 17 June 2026?",
         f"SELECT COUNT(*) AS upi_complaints FROM {fq('complaints')} WHERE category_code = 'UPI' AND received_date = DATE'2026-06-17'"),
        ("How many complaints were escalated to the RBI Ombudsman in total?",
         f"SELECT COUNT(*) AS escalations FROM {fq('complaints')} WHERE escalated_to_ombudsman = TRUE"),
        ("What is the overall chargeback win rate?",
         f"""SELECT ROUND(100.0 * SUM(CASE WHEN status = 'Won' THEN 1 ELSE 0 END)
             / NULLIF(SUM(CASE WHEN status IN ('Won','Lost') THEN 1 ELSE 0 END), 0), 1) AS win_rate_pct
FROM {fq('chargebacks')}"""),
        ("How many complaints arrived through the RBI CMS channel?",
         f"SELECT COUNT(*) AS rbi_cms_complaints FROM {fq('complaints')} WHERE channel = 'RBI CMS'"),
        ("Which RBI category has the highest ombudsman escalation percentage?",
         f"""SELECT cc.rbi_category,
       ROUND(100.0 * SUM(CASE WHEN c.escalated_to_ombudsman THEN 1 ELSE 0 END) / COUNT(*), 2) AS escalation_pct
FROM {fq('complaints')} c JOIN {fq('complaint_categories')} cc ON c.category_code = cc.category_code
GROUP BY cc.rbi_category ORDER BY escalation_pct DESC LIMIT 1"""),
        ("How many complaints are still open as of 31 August 2026?",
         f"SELECT COUNT(*) AS open_complaints FROM {fq('complaints')} WHERE status = 'Open'"),
    ],
}

RM = {
    "key": "rm",
    "title": "RM Performance & Incentives",
    "description": (
        "Relationship-manager targets, attainment, incentive earned, product-mix quality, portfolio "
        "composition and cross-sell gaps. The customer calls this RM Buddy. Amounts in INR. "
        "Data 2025-03 to 2026-08. ALL DATA SYNTHETIC."
    ),
    "tables": {
        "rm_achievement": (
            "PRIMARY TABLE for RM performance and incentive questions. Grain is one row per RM per "
            "month. Carries branch_id, region and rm_grade already, so region/branch/grade filters "
            "need no join. A cohort of ~21 RMs over-attains on volume with weak product mix, fails "
            "the quality gate, and carries clawback_flag = TRUE. Key columns: achievement_month, "
            "rm_id, branch_id, region, rm_grade, actual_casa_amount, actual_loan_amount, "
            "actual_cards, actual_insurance, product_mix_score, attainment_pct, incentive_earned, "
            "quality_gate_passed, clawback_flag."
        ),
        "rm_targets": (
            "Monthly RM targets by product line. Same grain as rm_achievement. JOIN ON BOTH "
            "achievement_month = target_month AND rm_id = rm_id; joining on rm_id alone fans out "
            "across 18 months and inflates every total. Key columns: target_month, rm_id, "
            "branch_id, region, rm_grade, target_casa_amount, target_loan_amount, target_cards, "
            "target_insurance, target_product_mix_score."
        ),
        "relationship_managers": (
            "RM dimension, 180 RMs. Join only for rm_name, portfolio_count, date_joined, "
            "active_flag. Key columns: rm_id, rm_name, branch_id, region, zone, rm_grade "
            "(Junior/Mid/Senior/Lead), date_joined, portfolio_count, active_flag."
        ),
        "incentive_slabs": (
            "Incentive slab grid by grade. Joined on a RANGE: rm_grade matches AND attainment_pct "
            ">= attainment_from_pct AND attainment_pct < attainment_to_pct. Key columns: slab_id, "
            "rm_grade, attainment_from_pct, attainment_to_pct, payout_pct_of_target, "
            "quality_gate_required, min_product_mix_score."
        ),
        "customer_portfolio": (
            "Customer master, one row per customer. Key columns: customer_id, rm_id, branch_id, "
            "region, customer_segment (Mass/Mass Affluent/Affluent/Private/MSME), "
            "relationship_start, total_relationship_value, products_held, casa_balance, "
            "risk_rating, nri_flag, churn_risk_score."
        ),
        "product_holdings": (
            "One row per customer-product pair, so counting rows counts HOLDINGS, not customers. "
            "Key columns: holding_id, customer_id, rm_id, product_code, opened_date, "
            "balance_or_limit, is_active, cross_sell_eligible."
        ),
    },
    "instructions": """### Space metadata
You answer questions about relationship-manager performance, targets, attainment and incentive
payouts for an Indian retail bank. All amounts are Indian Rupees (INR). All data is synthetic. The
data covers 2025-03-01 to 2026-08-01 and the current month is 2026-08-01. When a question says
"now", "current", "latest" or "this month", use achievement_month = DATE'2026-08-01'.
If the question names NO period at all, use the FULL data window and say so. Do not narrow to the
current month unless the question asks for it — a silently injected period can reverse the answer to
a "which is highest" question, and the user has no way to see that it happened.

### Data foundation
rm_achievement is the primary table. Grain is one row per RM per month, so always aggregate unless
the user names a single RM.
rm_achievement already carries branch_id, region and rm_grade, so filtering by region, branch or
grade needs NO join to relationship_managers. Join only for rm_name, portfolio_count, date_joined
or active_flag.
rm_targets shares the same grain. Join on BOTH achievement_month = target_month AND rm_id = rm_id.
Never join on rm_id alone or you will fan out across 18 months and inflate every total.
incentive_slabs is joined on a RANGE: rm_grade matches AND attainment_pct >= attainment_from_pct
AND attainment_pct < attainment_to_pct.
customer_portfolio is one row per customer. product_holdings is one row per customer-product pair,
so counting rows there counts holdings, not customers.

### Business terminology
CASA means Current Account and Savings Account balances.
Attainment means attainment_pct, the average of CASA and loan attainment, where 100 means target
met exactly. Target met means attainment_pct >= 100.
Product mix score means product_mix_score, 0 to 1, measuring how evenly volume spreads across
product lines. Below 0.50 means volume is concentrated in one or two products.
Quality gate means the product-mix threshold an RM must clear for a full payout;
quality_gate_passed is FALSE when they missed it.
Clawback means clawback_flag = TRUE: the RM reached a full-payout band but failed the quality gate,
so part of the incentive is recoverable. This is the signal for incentive distortion.
Cross-sell gap means products the customer does not hold. products_held of 1 or 2 with
cross_sell_eligible = TRUE is the prime opportunity.
Churn risk means churn_risk_score, 0 to 1; above 0.7 warrants retention action.
League table means RMs ranked by a measure, usually attainment_pct or incentive_earned.
Incentive per rupee of business means incentive_earned / (actual_casa_amount + actual_loan_amount).

### The finding to surface
Roughly 21 RMs consistently over-attain on CASA and loan volume while selling very little
insurance, dragging product_mix_score below 0.50. They land in a full-payout attainment band but
fail the quality gate, so clawback_flag is TRUE. When asked about incentive fairness, incentive
quality, or who is overpaid, find this cohort: attainment_pct >= 120 AND product_mix_score < 0.50.
Contrast their incentive_earned and actual_insurance against RMs at similar attainment who cleared
the gate.

### CRITICAL response standards
ALWAYS STATE THE COMPUTED ANSWER IN WORDS, as a number, before anything else. If you want to offer a
breakdown, state the answer first and then offer it. Never reply with only a follow-up question: the
result grid is not the answer a person reads, and a reply that asks "would you prefer this by card
type?" without giving the figure has answered nothing.
When the question names a value that exists LITERALLY in a column, filter on exactly that value. Do
not widen it to related values. "Affluent customers" means customer_segment = 'Affluent', not
Affluent plus Private plus Mass Affluent. If you believe the wider reading is what was meant, give
the exact answer first, then say what the wider figure would be and that it is a different question.
Always state the scope: the month or range, the region or branch, and the grade. Row-level security
is enforced, so different users legitimately see different totals.
Round percentages to one decimal place. Round INR to whole rupees with thousands separators.
NEVER quote a total you did not compute in SQL.
When comparing RMs, normalise by grade or by target, because targets scale with grade and raw
volume comparisons across grades mislead.
If a result would exceed 200 rows, aggregate further or LIMIT and say so.

### Error handling
If a question needs a column not in these six tables, name the missing column rather than
substituting a similar one.
If a question is about loan delinquency, collections, complaints or ombudsman cases, say it belongs
to a different domain agent.""",
    "joins": [
        ("rm_achievement", "rm_targets", "`rm_achievement`.`rm_id` = `rm_targets`.`rm_id` AND `rm_achievement`.`achievement_month` = `rm_targets`.`target_month`", ONE_TO_ONE),
        ("rm_achievement", "relationship_managers", "`rm_achievement`.`rm_id` = `relationship_managers`.`rm_id`", MANY_TO_ONE),
        ("customer_portfolio", "relationship_managers", "`customer_portfolio`.`rm_id` = `relationship_managers`.`rm_id`", MANY_TO_ONE),
        ("product_holdings", "customer_portfolio", "`product_holdings`.`customer_id` = `customer_portfolio`.`customer_id`", MANY_TO_ONE),
    ],
    "measures": [
        ("clawback_pct", "clawback rate percent",
         "100.0 * SUM(CASE WHEN rm_achievement.clawback_flag THEN 1 ELSE 0 END) / COUNT(*)",
         "WHEN_TO_USE: share of RM-months where a full payout was earned on volume but the product-"
         "mix quality gate failed. SCOPE_TABLES: rm_achievement. RISK_IF_MISUSED: the denominator is "
         "RM-months, not distinct RMs; say which you used."),
        ("total_incentive_inr", "total incentive paid",
         "SUM(rm_achievement.incentive_earned)",
         "WHEN_TO_USE: incentive cost. SCOPE_TABLES: rm_achievement. RISK_IF_MISUSED: always filter "
         "to a period; unfiltered it sums all 18 months."),
        ("casa_attainment_pct", "CASA attainment percent",
         "100.0 * SUM(rm_achievement.actual_casa_amount) / SUM(rm_targets.target_casa_amount)",
         "WHEN_TO_USE: CASA performance against target. SCOPE_TABLES: rm_achievement, rm_targets. "
         "RISK_IF_MISUSED: requires the two-column join on month AND rm_id; a rm_id-only join "
         "inflates the denominator 18-fold."),
    ],
    "samples": [
        "Who are the top 10 RMs by attainment this month?",
        "Which RMs are paid a full incentive but fail the product-mix quality gate?",
        "Compare incentive earned for high attainers who passed the quality gate against those who failed.",
        "Show attainment against target by region.",
        "Where is the biggest cross-sell gap in the portfolio?",
        "Which affluent customers hold no credit card?",
        "What is the incentive cost per rupee of business by grade?",
    ],
    "examples": [
        ("Who are the top 10 RMs by attainment this month?",
         f"""SELECT a.rm_id, r.rm_name, a.rm_grade, a.region, ROUND(a.attainment_pct, 1) AS attainment_pct,
       ROUND(a.product_mix_score, 3) AS product_mix_score,
       ROUND(a.incentive_earned, 0) AS incentive_inr, a.quality_gate_passed
FROM {fq('rm_achievement')} a JOIN {fq('relationship_managers')} r ON a.rm_id = r.rm_id
WHERE a.achievement_month = DATE'2026-08-01' ORDER BY a.attainment_pct DESC LIMIT 10"""),
        ("Which RMs are being paid a full incentive but failing the product-mix quality gate?",
         f"""SELECT a.rm_id, r.rm_name, a.rm_grade, a.region, a.achievement_month,
       ROUND(a.attainment_pct, 1) AS attainment_pct, ROUND(a.product_mix_score, 3) AS product_mix_score,
       a.actual_insurance, ROUND(a.incentive_earned, 0) AS incentive_inr, a.clawback_flag
FROM {fq('rm_achievement')} a JOIN {fq('relationship_managers')} r ON a.rm_id = r.rm_id
WHERE a.clawback_flag = TRUE AND a.achievement_month >= DATE'2026-06-01'
ORDER BY a.incentive_earned DESC LIMIT 50"""),
        ("Compare incentive earned for high attainers who passed the quality gate against those who failed.",
         f"""SELECT CASE WHEN product_mix_score < 0.50 THEN 'Weak mix (<0.50)' ELSE 'Healthy mix (>=0.50)' END AS mix_band,
       COUNT(*) AS rm_months, COUNT(DISTINCT rm_id) AS distinct_rms,
       ROUND(AVG(attainment_pct), 1) AS avg_attainment_pct,
       ROUND(AVG(actual_insurance), 1) AS avg_insurance_sold,
       ROUND(AVG(incentive_earned), 0) AS avg_incentive_inr
FROM {fq('rm_achievement')} WHERE attainment_pct >= 120
GROUP BY CASE WHEN product_mix_score < 0.50 THEN 'Weak mix (<0.50)' ELSE 'Healthy mix (>=0.50)' END"""),
        ("What incentive slab did each RM land in this month?",
         f"""SELECT a.rm_id, a.rm_grade, ROUND(a.attainment_pct, 1) AS attainment_pct,
       s.attainment_from_pct, s.attainment_to_pct, s.payout_pct_of_target,
       s.quality_gate_required, s.min_product_mix_score,
       ROUND(a.product_mix_score, 3) AS product_mix_score, a.quality_gate_passed,
       ROUND(a.incentive_earned, 0) AS incentive_inr
FROM {fq('rm_achievement')} a JOIN {fq('incentive_slabs')} s
  ON a.rm_grade = s.rm_grade AND a.attainment_pct >= s.attainment_from_pct
 AND a.attainment_pct < s.attainment_to_pct
WHERE a.achievement_month = DATE'2026-08-01' ORDER BY a.attainment_pct DESC LIMIT 50"""),
        ("Show attainment against target by region for the latest month.",
         f"""SELECT a.region, COUNT(*) AS rms,
       ROUND(SUM(t.target_casa_amount), 0) AS target_casa_inr,
       ROUND(SUM(a.actual_casa_amount), 0) AS actual_casa_inr,
       ROUND(100.0 * SUM(a.actual_casa_amount) / SUM(t.target_casa_amount), 1) AS casa_attainment_pct,
       ROUND(100.0 * SUM(a.actual_loan_amount) / SUM(t.target_loan_amount), 1) AS loan_attainment_pct
FROM {fq('rm_achievement')} a JOIN {fq('rm_targets')} t
  ON a.achievement_month = t.target_month AND a.rm_id = t.rm_id
WHERE a.achievement_month = DATE'2026-08-01' GROUP BY a.region ORDER BY casa_attainment_pct DESC"""),
        ("Where is the biggest cross-sell gap in the portfolio?",
         f"""SELECT c.rm_id, r.rm_name, c.region, COUNT(*) AS customers,
       SUM(CASE WHEN c.products_held <= 2 THEN 1 ELSE 0 END) AS thin_relationships,
       ROUND(100.0 * SUM(CASE WHEN c.products_held <= 2 THEN 1 ELSE 0 END) / COUNT(*), 1) AS thin_pct,
       ROUND(SUM(c.total_relationship_value), 0) AS portfolio_value_inr
FROM {fq('customer_portfolio')} c JOIN {fq('relationship_managers')} r ON c.rm_id = r.rm_id
GROUP BY c.rm_id, r.rm_name, c.region ORDER BY thin_relationships DESC LIMIT 20"""),
        ("Which affluent customers hold no credit card and are cross-sell eligible?",
         f"""SELECT c.customer_id, c.rm_id, c.customer_segment, c.products_held,
       ROUND(c.total_relationship_value, 0) AS relationship_value_inr,
       ROUND(c.casa_balance, 0) AS casa_balance_inr, ROUND(c.churn_risk_score, 3) AS churn_risk
FROM {fq('customer_portfolio')} c
WHERE c.customer_segment IN ('Affluent', 'Private', 'Mass Affluent')
  AND NOT EXISTS (SELECT 1 FROM {fq('product_holdings')} h
                  WHERE h.customer_id = c.customer_id AND h.product_code = 'CC' AND h.is_active)
ORDER BY c.total_relationship_value DESC LIMIT 50"""),
    ],
    "benchmarks": [
        ("How many RM-months carry a clawback flag?",
         f"SELECT COUNT(*) AS clawback_rm_months FROM {fq('rm_achievement')} WHERE clawback_flag = TRUE"),
        ("How many distinct RMs have attainment of 120 percent or more with a product mix score below 0.50?",
         f"""SELECT COUNT(DISTINCT rm_id) AS distorted_rms FROM {fq('rm_achievement')}
WHERE attainment_pct >= 120 AND product_mix_score < 0.50"""),
        ("For RMs above 120 percent attainment, what is the average incentive by product-mix band?",
         f"""SELECT CASE WHEN product_mix_score < 0.50 THEN 'Weak mix (<0.50)' ELSE 'Healthy mix (>=0.50)' END AS mix_band,
       ROUND(AVG(incentive_earned), 0) AS avg_incentive_inr
FROM {fq('rm_achievement')} WHERE attainment_pct >= 120
GROUP BY CASE WHEN product_mix_score < 0.50 THEN 'Weak mix (<0.50)' ELSE 'Healthy mix (>=0.50)' END"""),
        ("What is the CASA attainment percentage by region for August 2026?",
         f"""SELECT a.region, ROUND(100.0 * SUM(a.actual_casa_amount) / SUM(t.target_casa_amount), 1) AS casa_attainment_pct
FROM {fq('rm_achievement')} a JOIN {fq('rm_targets')} t
  ON a.achievement_month = t.target_month AND a.rm_id = t.rm_id
WHERE a.achievement_month = DATE'2026-08-01' GROUP BY a.region ORDER BY casa_attainment_pct DESC"""),
        ("Which RM had the highest attainment in August 2026?",
         f"""SELECT rm_id, ROUND(attainment_pct, 1) AS attainment_pct FROM {fq('rm_achievement')}
WHERE achievement_month = DATE'2026-08-01' ORDER BY attainment_pct DESC LIMIT 1"""),
        ("How many customers hold two or fewer products?",
         f"SELECT COUNT(*) AS thin_relationships FROM {fq('customer_portfolio')} WHERE products_held <= 2"),
        ("What was the total incentive paid in August 2026?",
         f"""SELECT ROUND(SUM(incentive_earned), 0) AS total_incentive_inr FROM {fq('rm_achievement')}
WHERE achievement_month = DATE'2026-08-01'"""),
        ("How many affluent-segment customers have no active credit card?",
         f"""SELECT COUNT(*) AS customers FROM {fq('customer_portfolio')} c
WHERE c.customer_segment IN ('Affluent', 'Private', 'Mass Affluent')
  AND NOT EXISTS (SELECT 1 FROM {fq('product_holdings')} h
                  WHERE h.customer_id = c.customer_id AND h.product_code = 'CC' AND h.is_active)"""),
        ("Which RM grade has the highest clawback rate?",
         f"""SELECT rm_grade, ROUND(100.0 * SUM(CASE WHEN clawback_flag THEN 1 ELSE 0 END) / COUNT(*), 1) AS clawback_pct
FROM {fq('rm_achievement')} GROUP BY rm_grade ORDER BY clawback_pct DESC LIMIT 1"""),
        ("What is the incentive cost per million rupees of business by grade since March 2026?",
         f"""SELECT rm_grade, ROUND(1000000.0 * SUM(incentive_earned)
             / SUM(actual_casa_amount + actual_loan_amount), 2) AS incentive_per_million_inr
FROM {fq('rm_achievement')} WHERE achievement_month >= DATE'2026-03-01'
GROUP BY rm_grade ORDER BY incentive_per_million_inr DESC"""),
    ],
}

AGENTS = {a["key"]: a for a in (COLLECTIONS, GRIEVANCE, RM)}


# ===========================================================================
# Serialization
# ===========================================================================

def serialize(spec: dict) -> str:
    """Build the serialized_space JSON string the Genie API expects."""
    k = spec["key"]
    body = {
        "version": 2,
        "config": {
            "sample_questions": sorted(
                ({"id": eid(k, "sample", q), "question": L(q)} for q in spec["samples"]),
                key=lambda e: e["id"]),
        },
        "data_sources": {
            # The API rejects the payload with "data_sources.tables must be sorted by identifier"
            # unless this list is sorted, so sort here rather than relying on dict order.
            "tables": [
                {"identifier": fq(t), "description": L(desc)}
                for t, desc in sorted(spec["tables"].items())
            ],
        },
        "instructions": {
            "text_instructions": [
                {"id": eid(k, "text"), "content": L(spec["instructions"])}
            ],
            "example_question_sqls": sorted(
                ({"id": eid(k, "sql", q), "question": L(q), "sql": L(sq)}
                 for q, sq in spec["examples"]),
                key=lambda e: e["id"]),
            "join_specs": sorted(
                ({
                    "id": eid(k, "join", left, right),
                    "left": {"identifier": fq(left), "alias": left},
                    "right": {"identifier": fq(right), "alias": right},
                    "sql": [cond, rt],
                 }
                 for left, right, cond, rt in spec["joins"]),
                key=lambda e: e["id"]),
            "sql_snippets": {
                "measures": sorted(
                    ({
                        "id": eid(k, "measure", alias),
                        "alias": alias,
                        "sql": L(sql),
                        "display_name": display,
                        "instruction": L(instr),
                     }
                     for alias, display, sql, instr in spec["measures"]),
                    key=lambda e: e["id"]),
            },
        },
        "benchmarks": {
            "questions": sorted(
                ({"id": eid(k, "bench", q),
                  "question": L(q),
                  "answer": [{"format": "SQL", "content": L(sql)}]}
                 for q, sql in spec["benchmarks"]),
                key=lambda e: e["id"]),
        },
    }
    return json.dumps(body)


def load_ids() -> dict:
    if os.path.exists(IDS_PATH):
        return json.load(open(IDS_PATH))
    return {}


def save_ids(ids: dict) -> None:
    with open(IDS_PATH, "w") as fh:
        json.dump(ids, fh, indent=2)
        fh.write("\n")


def create(w: WorkspaceClient, spec: dict, ids: dict) -> None:
    payload = serialize(spec)
    res = w.api_client.do(
        "POST", "/api/2.0/genie/spaces",
        body={
            "warehouse_id": WAREHOUSE_ID,
            "serialized_space": payload,
            "title": spec["title"],
            "description": spec["description"],
        },
    )
    sid = res.get("space_id")
    ids[spec["key"]] = sid
    print(f"  created {spec['key']:<12} {spec['title']:<32} space_id={sid}")


def update(w: WorkspaceClient, spec: dict, ids: dict) -> None:
    sid = ids.get(spec["key"])
    if not sid:
        print(f"  {spec['key']}: no space id recorded, use --create first")
        return
    cur = w.api_client.do("GET", f"/api/2.0/genie/spaces/{sid}")
    w.api_client.do(
        "PATCH", f"/api/2.0/genie/spaces/{sid}",
        body={
            "serialized_space": serialize(spec),
            "title": spec["title"],
            "description": spec["description"],
            "warehouse_id": WAREHOUSE_ID,
            "etag": cur.get("etag"),
        },
    )
    print(f"  updated {spec['key']:<12} space_id={sid}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--create", nargs="*", metavar="KEY",
                    help="create agents (no args = all three)")
    ap.add_argument("--update", nargs="*", metavar="KEY",
                    help="replace config on existing agents")
    ap.add_argument("--list", action="store_true", help="show recorded space ids")
    ap.add_argument("--dump", metavar="KEY", help="print the serialized payload and exit")
    args = ap.parse_args()

    ids = load_ids()

    if args.dump:
        print(json.dumps(json.loads(serialize(AGENTS[args.dump])), indent=2))
        return 0

    if args.list:
        for k, spec in AGENTS.items():
            print(f"  {k:<12} {spec['title']:<32} {ids.get(k, '(not created)')}")
        return 0

    w = (WorkspaceClient(profile=PROFILE) if PROFILE else WorkspaceClient())

    if args.create is not None:
        keys = args.create or list(AGENTS)
        print(f"Creating {len(keys)} Genie agent(s) on warehouse {WAREHOUSE_ID}:")
        for k in keys:
            create(w, AGENTS[k], ids)
        save_ids(ids)
        print(f"\nWrote {IDS_PATH}")

    if args.update is not None:
        keys = args.update or list(AGENTS)
        print(f"Updating {len(keys)} Genie agent(s):")
        for k in keys:
            update(w, AGENTS[k], ids)

    if args.create is None and args.update is None:
        ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
