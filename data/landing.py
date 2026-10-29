"""Write the bank's data the way its source systems would actually send it, plus the answer key.

generate_banking_data.build_all() is the clean book of record. Nothing downstream ever sees it. What
lands in the `landing` volume instead is what a bank's data team really receives:

  * one folder per source system and entity, one file per month for anything periodic;
  * each system's own field names — the dialer vendor and the field-collection app describe the same
    contact attempt differently, so the pipeline has to conform two sources into one table;
  * NO derived fields. DPD bucket, NPA flag, roll direction, contact hour, the RBI-hours flag, SLA
    breach, attainment and incentive are business rules, so the pipeline computes them;
  * the defects a real feed carries, planted deterministically so every run lands the same counts;
  * a manifest per period, written LAST, with the row count and amount total the sender claims to have
    sent. The pipeline reconciles what landed against it.

The most recent period (2026-08 by default) is written to the `holdback` volume instead, so a demo can
land it live and watch the file-arrival trigger run the whole cycle.

The answer key lists every planted finding with its exact count. The evidence pack checks the pipeline
against it, so "the quarantine caught the bad rows" is a number that either matches or does not.

    python3 data/generate_banking_data.py --landing /Volumes/<c>/<s>/landing \\
        --holdback /Volumes/<c>/<s>/holdback --answer-key evidence/00_answer_key.md
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import os
import shutil

import generate_banking_data as book
import generate_documents as docs

# ---------------------------------------------------------------------------
# Planted findings. Counts are fixed so the answer key, the evidence and the deck always agree.
# ---------------------------------------------------------------------------
UNPARSEABLE_TIMESTAMPS = 30     # dialer rows whose call time cannot be read
ORPHAN_CONTACTS = 40            # dialer rows for loan accounts the bank does not hold
MISSING_LOAN_VISITS = 25        # field-app visits with no loan account
NEGATIVE_DPD = 25               # core-system snapshot rows with days past due of -1
UNKNOWN_CATEGORY = 18           # CRM complaints with a category code that does not exist
RESENT_COMPLAINTS = 15          # CRM complaints sent twice
NON_POSITIVE_UPI = 35           # UPI disputes with an amount of zero or less
CHARGEBACK_BEFORE_TXN = 20      # chargebacks raised before the transaction they dispute
UNKNOWN_PRODUCT_LOANS = 12      # LOS accounts with a product code the bank does not sell
TRUNCATED_PERIOD = "2026-06"    # the dialer file for this month arrives short ...
TRUNCATED_ROWS = 37             # ... by this many rows, while its manifest counts them
DUPLICATE_EVERY = 100           # roughly 1 in this many dialer rows is re-sent in the same file
LATE_EVERY = 200                # roughly 1 in this many dialer rows arrives in the next month's file
MESSY_CODE_EVERY = 40           # roughly 1 in this many codes arrives lower-case with trailing spaces


def _h(*parts: object) -> int:
    """Stable hash-based selection: the same rows are chosen on every run, on every machine."""
    return int(hashlib.sha256(":".join(str(p) for p in parts).encode()).hexdigest()[:12], 16)


def _month(date_iso: str) -> str:
    return date_iso[:7]


def _next_month(period: str) -> str:
    y, m = int(period[:4]), int(period[5:7])
    return f"{y + (m == 12)}-{1 if m == 12 else m + 1:02d}"


def _messy(code: str, *key: object) -> str:
    return f"{code.lower()}  " if _h("messy", *key) % MESSY_CODE_EVERY == 0 else code


class Writer:
    """Collects files per period, then writes data before manifests so a trigger never sees a
    manifest whose files are still being written."""

    def __init__(self, landing: str, holdback: str, hold_period: str):
        self.landing, self.holdback, self.hold_period = landing, holdback, hold_period
        self.periods: dict[str, list[dict]] = {}

    def root(self, period: str) -> str:
        return self.holdback if period == self.hold_period else self.landing

    def _write(self, period: str, rel: str, text: str) -> None:
        path = os.path.join(self.root(period), rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", newline="") as fh:
            fh.write(text)

    def csv(self, period: str, rel: str, cols: list[str], rows: list[tuple],
            amount_field: str | None = None, claimed_extra: list[tuple] = ()) -> None:
        import io
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(cols)
        w.writerows([["" if v is None else v for v in r] for r in rows])
        self._write(period, rel, buf.getvalue())
        self._record(period, rel, cols, list(rows) + list(claimed_extra), amount_field)

    def jsonl(self, period: str, rel: str, cols: list[str], rows: list[tuple],
              amount_field: str | None = None) -> None:
        text = "".join(json.dumps(dict(zip(cols, r))) + "\n" for r in rows)
        self._write(period, rel, text)
        self._record(period, rel, cols, rows, amount_field)

    def text(self, period: str, rel: str, body: str) -> None:
        self._write(period, rel, body)
        self.periods.setdefault(period, []).append({"path": rel, "rows": 1})

    def _record(self, period, rel, cols, rows, amount_field) -> None:
        entry = {"path": rel, "rows": len(rows)}
        if amount_field:
            ix = cols.index(amount_field)
            total = sum(float(r[ix]) for r in rows if r[ix] not in (None, ""))
            entry.update(amount_field=amount_field, amount_total=round(total, 2))
        self.periods.setdefault(period, []).append(entry)

    def manifests(self) -> None:
        for period, files in sorted(self.periods.items()):
            # Correspondence is one file per letter; the manifest counts letters per folder instead of
            # listing hundreds of entries.
            letters = [f for f in files if f["path"].startswith("correspondence/")]
            listed = [f for f in files if not f["path"].startswith("correspondence/")]
            if letters:
                listed.append({"path": f"correspondence/{period}/", "rows": len(letters)})
            body = {"period": period, "sender": "synthetic source systems (data/landing.py)",
                    "files": sorted(listed, key=lambda f: f["path"])}
            self._write(period, f"_manifests/{period}.json", json.dumps(body, indent=1))


def write(landing: str, holdback: str, hold_period: str, bank: str) -> dict:
    tables = {name: (cols, rows) for name, cols, rows in book.build_all()}
    w = Writer(landing, holdback, hold_period)
    key: dict = {}

    def rows_of(name):
        return tables[name][1]

    def cols_of(name):
        return tables[name][0]

    # ---- reference data and slowly changing masters: one snapshot, in the first drop -------------
    ref = "reference"
    for name, folder in [("branch_master", "reference/branch_master"),
                         ("product_master", "reference/product_master"),
                         ("complaint_categories", "reference/complaint_categories"),
                         ("incentive_slabs", "reference/incentive_slabs"),
                         ("recovery_agents", "collections/recovery_agents"),
                         ("relationship_managers", "hrms/relationship_managers"),
                         ("customer_portfolio", "crm/customer_portfolio"),
                         ("product_holdings", "crm/product_holdings"),
                         ("repayment_schedule", "los/repayment_schedule")]:
        w.csv(ref, f"{folder}/{name}.csv", cols_of(name), rows_of(name))

    loan_cols = cols_of("loan_accounts")
    pix = loan_cols.index("product_code")
    loans = []
    for r in rows_of("loan_accounts"):
        r = list(r)
        r[pix] = _messy(r[pix], "loan", r[0])
        loans.append(tuple(r))
    messy_products = sum(1 for r in loans if r[pix] != r[pix].strip().upper())
    for i in range(UNKNOWN_PRODUCT_LOANS):
        extra = list(rows_of("loan_accounts")[i])
        extra[0], extra[pix] = f"LN9{i + 1:05d}", "GLD"
        loans.append(tuple(extra))
    w.csv(ref, "los/loan_accounts/loan_accounts.csv", loan_cols, loans,
          amount_field="outstanding_principal")
    key["loan_messy_codes"] = messy_products
    key["unknown_product_loans"] = UNKNOWN_PRODUCT_LOANS


    # ---- collections core: month-end DPD snapshot, raw facts only ---------------------------------
    dcols = cols_of("delinquency_monthly")
    di = {c: dcols.index(c) for c in dcols}
    by_month: dict[str, list[tuple]] = {}
    for r in rows_of("delinquency_monthly"):
        by_month.setdefault(_month(r[di["snapshot_month"]]), []).append(
            (r[di["snapshot_month"]], r[di["loan_account_id"]], r[di["dpd_days"]],
             r[di["outstanding_principal"]], r[di["overdue_amount"]]))
    neg = 0
    snap_cols = ["snapshot_month", "loan_account_id", "dpd_days", "outstanding_principal",
                 "overdue_amount"]
    for p_i, (period, rows) in enumerate(sorted(by_month.items())):
        rows = list(rows)
        quota = NEGATIVE_DPD // len(by_month) + (1 if p_i < NEGATIVE_DPD % len(by_month) else 0)
        for k in range(quota):
            src = rows[_h("negdpd", period, k) % len(rows)]
            rows.append((src[0], src[1], -1, src[3], 0.0))
            neg += 1
        w.csv(period, f"collections/dpd_snapshot/dpd_snapshot_{period}.csv", snap_cols, rows,
              amount_field="outstanding_principal")
    key["negative_dpd"] = neg

    # ---- contact attempts: dialer vendor (calls and messages) + field app (visits) ----------------
    acols = cols_of("collections_activity")
    ai = {c: acols.index(c) for c in acols}
    dialer: dict[str, list[tuple]] = {}
    field: dict[str, list[tuple]] = {}
    late = dup = 0
    for r in rows_of("collections_activity"):
        aid, date, hour = r[ai["activity_id"]], r[ai["activity_date"]], r[ai["contact_hour"]]
        minute, second = _h("min", aid) % 60, _h("sec", aid) % 60
        period = _month(date)
        if r[ai["channel"]] == "Field Visit":
            ist = dt.datetime.fromisoformat(f"{date}T{hour:02d}:{minute:02d}:{second:02d}")
            epoch = int((ist - dt.timedelta(hours=5, minutes=30)).replace(
                tzinfo=dt.timezone.utc).timestamp())
            field.setdefault(period, []).append(
                (aid, r[ai["loan_account_id"]], epoch, r[ai["agent_id"]], r[ai["outcome"]],
                 r[ai["promise_to_pay_amount"]], r[ai["amount_collected"]]))
            continue
        row = (aid, r[ai["loan_account_id"]], f"{date} {hour:02d}:{minute:02d}:{second:02d}",
               r[ai["agent_id"]], r[ai["channel"]], r[ai["outcome"]],
               r[ai["promise_to_pay_amount"]], r[ai["amount_collected"]])
        # A vendor that batches by upload time, not call time, puts a few late calls in next month's file.
        if period < book.CURRENT_MONTH.isoformat()[:7] and _h("late", aid) % LATE_EVERY == 0:
            period = _next_month(period)
            late += 1
        dialer.setdefault(period, []).append(row)

    dialer_cols = ["call_id", "acct_no", "call_ts_ist", "agent_code", "channel", "disposition",
                   "ptp_amount", "collected_amount"]
    bad_ts = ["2026-13-45 25:00:00", "", "N/A", "31/06/2026 10:00", "2026-02-30 11:61:00"]
    lost = []
    for p_i, (period, rows) in enumerate(sorted(dialer.items())):
        rows = list(rows)
        if period == TRUNCATED_PERIOD:
            # The transfer drops the tail of the file. The manifest was cut before the upload, so it
            # still counts — and totals — every row the vendor meant to send.
            lost, rows = rows[-TRUNCATED_ROWS:], rows[:-TRUNCATED_ROWS]
        resent = [r for r in rows if _h("dup", r[0]) % DUPLICATE_EVERY == 0]
        dup += len(resent)
        rows += resent                                       # the vendor re-sends a block at the end
        n_bad = UNPARSEABLE_TIMESTAMPS // len(dialer) + (1 if p_i < UNPARSEABLE_TIMESTAMPS % len(dialer) else 0)
        n_orphan = ORPHAN_CONTACTS // len(dialer) + (1 if p_i < ORPHAN_CONTACTS % len(dialer) else 0)
        for k in range(n_bad):
            src = rows[_h("badts", period, k) % len(rows)]
            rows.append((f"ACX{period.replace('-', '')}{k:03d}", src[1], bad_ts[k % len(bad_ts)],
                         *src[3:]))
        for k in range(n_orphan):
            src = rows[_h("orphan", period, k) % len(rows)]
            rows.append((f"ACO{period.replace('-', '')}{k:03d}", f"LN8{_h('o', period, k) % 99999:05d}",
                         *src[2:]))
        w.csv(period, f"dialer/contacts/contacts_{period}.csv", dialer_cols, rows,
              amount_field="collected_amount", claimed_extra=lost if period == TRUNCATED_PERIOD else ())
    key["dialer_resent_duplicates"] = dup
    key["unparseable_timestamps"] = UNPARSEABLE_TIMESTAMPS
    key["orphan_contacts"] = ORPHAN_CONTACTS
    key["late_contacts"] = late
    key["truncated_rows"] = TRUNCATED_ROWS

    field_cols = ["visitId", "loanAccount", "visitEpoch", "agentId", "outcome", "promisedAmount",
                  "collectedAmount"]
    for p_i, (period, rows) in enumerate(sorted(field.items())):
        rows = list(rows)
        n = MISSING_LOAN_VISITS // len(field) + (1 if p_i < MISSING_LOAN_VISITS % len(field) else 0)
        for k in range(n):
            src = rows[_h("noloan", period, k) % len(rows)]
            rows.append((f"ACV{period.replace('-', '')}{k:03d}", None, *src[2:]))
        w.jsonl(period, f"field_app/visits/visits_{period}.json", field_cols, rows,
                amount_field="collectedAmount")
    key["missing_loan_visits"] = MISSING_LOAN_VISITS

    # ---- CRM complaints, without the fields the bank derives -----------------------------------------
    ccols = cols_of("complaints")
    ci = {c: ccols.index(c) for c in ccols}
    raw_ccols = [c for c in ccols if c not in ("days_to_resolve", "sla_days", "sla_breached")]
    per: dict[str, list[tuple]] = {}
    messy_cat = 0
    for r in rows_of("complaints"):
        r = list(r)
        cat = _messy(r[ci["category_code"]], "cat", r[ci["complaint_id"]])
        messy_cat += cat != r[ci["category_code"]]
        r[ci["category_code"]] = cat
        per.setdefault(_month(r[ci["received_date"]]), []).append(
            tuple(r[ci[c]] for c in raw_ccols))
    periods = sorted(per)
    originals = {p: len(rows) for p, rows in per.items()}
    for k in range(UNKNOWN_CATEGORY):
        p = periods[_h("gen", k) % len(periods)]
        src = list(per[p][_h("gensrc", k) % len(per[p])])
        src[0], src[raw_ccols.index("category_code")] = f"CMG{k + 1:06d}", "GEN"
        per[p].append(tuple(src))
    for k in range(RESENT_COMPLAINTS):
        p = periods[_h("resend", k) % len(periods)]
        per[p].append(per[p][_h("resendsrc", k) % originals[p]])
    for period, rows in sorted(per.items()):
        w.csv(period, f"crm/complaints/complaints_{period}.csv", raw_ccols, rows)
    key["complaint_messy_codes"] = messy_cat
    key["unknown_category"] = UNKNOWN_CATEGORY
    key["resent_complaints"] = RESENT_COMPLAINTS

    # ---- UPI switch: JSON, the switch's own field names -----------------------------------------------
    ucols = ["disputeId", "txnDate", "raisedDate", "customerRef", "branchCode", "amount", "failureReason",
             "resolutionPath", "autoRefunded", "resolutionSecs", "status", "pspHandle"]
    per = {}
    for r in rows_of("upi_disputes"):
        per.setdefault(_month(r[1]), []).append(tuple(r))
    periods = sorted(per)
    for k in range(NON_POSITIVE_UPI):
        p = periods[_h("upineg", k) % len(periods)]
        src = list(per[p][_h("upisrc", k) % len(per[p])])
        src[0], src[5] = f"UDN{k + 1:06d}", -abs(src[5]) if k % 2 else 0.0
        per[p].append(tuple(src))
    for period, rows in sorted(per.items()):
        w.jsonl(period, f"upi_switch/disputes/disputes_{period}.json", ucols, rows, amount_field="amount")
    key["non_positive_upi"] = NON_POSITIVE_UPI

    # ---- cards: chargebacks, filed by the month they were raised ------------------------------------
    bcols = cols_of("chargebacks")
    per = {}
    for r in rows_of("chargebacks"):
        per.setdefault(_month(r[2]), []).append(tuple(r))
    periods = sorted(per)
    for k in range(CHARGEBACK_BEFORE_TXN):
        p = periods[_h("cbbad", k) % len(periods)]
        src = list(per[p][_h("cbsrc", k) % len(per[p])])
        raised = dt.date.fromisoformat(src[2])
        src[0], src[1] = f"CBX{k + 1:05d}", (raised + dt.timedelta(days=3 + k % 9)).isoformat()
        per[p].append(tuple(src))
    for period, rows in sorted(per.items()):
        w.csv(period, f"cards/chargebacks/chargebacks_{period}.csv", bcols, rows, amount_field="txn_amount")
    key["chargeback_before_txn"] = CHARGEBACK_BEFORE_TXN

    # ---- sales system: monthly targets and actuals; attainment and incentive are derived --------------
    tcols = cols_of("rm_targets")
    per = {}
    for r in rows_of("rm_targets"):
        per.setdefault(_month(r[0]), []).append(tuple(r))
    for period, rows in sorted(per.items()):
        w.csv(period, f"sales/rm_targets/rm_targets_{period}.csv", tcols, rows)
    acols2 = cols_of("rm_achievement")
    raw_acols = [c for c in acols2 if c not in ("attainment_pct", "incentive_earned",
                                                "quality_gate_passed", "clawback_flag")]
    per = {}
    for r in rows_of("rm_achievement"):
        per.setdefault(_month(r[0]), []).append(tuple(r[acols2.index(c)] for c in raw_acols))
    for period, rows in sorted(per.items()):
        w.csv(period, f"sales/rm_achievement/rm_achievement_{period}.csv", raw_acols, rows)

    # ---- correspondence: one scanned letter per sampled complaint -------------------------------------
    cats = {c[0]: c for c in book.COMPLAINT_CATEGORIES}
    city = {b[0]: b[2] for b in book.BRANCHES}
    complaints = [{
        "complaint_id": r[ci["complaint_id"]], "received_date": r[ci["received_date"]],
        "category_code": r[ci["category_code"]], "rbi_category": cats[r[ci["category_code"]]][2],
        "status": r[ci["status"]], "escalated_to_ombudsman": r[ci["escalated_to_ombudsman"]],
        "product_code": r[ci["product_code"]], "city": city[r[ci["branch_id"]]],
    } for r in rows_of("complaints")]
    letters = docs.select_letters(complaints)
    for c in letters:
        period = _month(c["received_date"])
        w.text(period, f"correspondence/{period}/{c['complaint_id']}.txt", docs.render_letter(bank, c))
    key["letters"] = len(letters)
    key["letters_by_ground"] = {}
    for c in letters:
        key["letters_by_ground"][c["rbi_category"]] = key["letters_by_ground"].get(c["rbi_category"], 0) + 1

    agent_region = {r[0]: r[4] for r in rows_of("recovery_agents")}
    for rel, body in docs.reference_documents(bank, agent_region).items():
        w.text(ref, f"reference_docs/{rel}", body)

    w.manifests()

    # ---- what the pipeline should end up with --------------------------------------------------------
    key["expected_gold_rows"] = {
        "loan_accounts": len(rows_of("loan_accounts")),
        "delinquency_monthly": len(rows_of("delinquency_monthly")),
        "collections_activity": len(rows_of("collections_activity")) - TRUNCATED_ROWS,
        "complaints": len(rows_of("complaints")),
        "upi_disputes": len(rows_of("upi_disputes")),
        "chargebacks": len(rows_of("chargebacks")),
        "rm_targets": len(rows_of("rm_targets")),
        "rm_achievement": len(rows_of("rm_achievement")),
        "recovery_agents": len(rows_of("recovery_agents")),
        "customer_portfolio": len(rows_of("customer_portfolio")),
        "product_holdings": len(rows_of("product_holdings")),
        "repayment_schedule": len(rows_of("repayment_schedule")),
        "relationship_managers": len(rows_of("relationship_managers")),
        "branch_master": len(rows_of("branch_master")),
        "product_master": len(rows_of("product_master")),
        "complaint_categories": len(rows_of("complaint_categories")),
        "incentive_slabs": len(rows_of("incentive_slabs")),
    }
    key["periods"] = sorted(p for p in w.periods if p != ref)
    key["hold_period"] = hold_period
    return key


def answer_key_markdown(k: dict) -> str:
    rows = [
        ("F01", "Dialer re-sends a block of calls at the end of the file", k["dialer_resent_duplicates"],
         "same `call_id` twice in one file", "removed by de-duplication in `core_collections_activity`"),
        ("F02", "Call time cannot be read", k["unparseable_timestamps"],
         "`call_ts_ist` blank, `N/A`, or an impossible date", "`quarantine_collections_activity`, reason `unparseable contact timestamp`"),
        ("F03", "Call logged against a loan the bank does not hold", k["orphan_contacts"],
         "`acct_no` starting `LN8`", "`quarantine_orphans`, reason `unknown loan account`"),
        ("F04", "Field visit with no loan account", k["missing_loan_visits"],
         "`loanAccount` null", "`quarantine_collections_activity`, reason `missing loan account`"),
        ("F05", "Negative days past due in the month-end snapshot", k["negative_dpd"],
         "`dpd_days` = -1", "`quarantine_delinquency`, reason `negative days past due`"),
        ("F06", "Complaint with a category the bank does not use", k["unknown_category"],
         "`category_code` = `GEN`", "`quarantine_orphans`, reason `unknown complaint category`"),
        ("F07", "Complaint sent twice", k["resent_complaints"],
         "same `complaint_id` twice", "removed by de-duplication in `core_complaints`"),
        ("F08", "UPI dispute with zero or negative amount", k["non_positive_upi"],
         "`amount` <= 0", "`quarantine_upi_disputes`, reason `non-positive amount`"),
        ("F09", "Chargeback raised before its transaction", k["chargeback_before_txn"],
         "`raised_date` < `txn_date`", "`quarantine_chargebacks`, reason `raised before transaction`"),
        ("F10", "Loan with a product the bank does not sell", k["unknown_product_loans"],
         "`product_code` = `GLD`", "`quarantine_orphans`, reason `unknown product code`"),
        ("F11", f"Dialer file for {TRUNCATED_PERIOD} truncated in transfer", k["truncated_rows"],
         "file has fewer rows than its manifest", f"`recon_completeness` status `BREAK` for `contacts_{TRUNCATED_PERIOD}.csv`"),
        ("F12", "Calls uploaded in the following month's file", k["late_contacts"],
         "call month earlier than file month", "kept, counted by expectation `arrived_in_period` (warn)"),
    ]
    messy = [
        ("Loan product codes lower-case with trailing spaces", k["loan_messy_codes"]),
        ("Complaint category codes lower-case with trailing spaces", k["complaint_messy_codes"]),
    ]
    out = [
        "# 00 — Answer key for the planted findings",
        "",
        "Generated by `data/landing.py` (deterministic, seed 7). Every count below is fixed: the generator "
        "selects rows by hashing their keys, so the same rows are planted on every run. "
        "The pipeline evidence (`01_pipeline_run.md`, `02_data_quality.md`) is checked against this file.",
        "",
        "## Findings the pipeline must catch",
        "",
        "| ID | Finding | Count | How to recognise it | Where it must end up |",
        "|---|---|---:|---|---|",
    ]
    out += [f"| {a} | {b} | {c:,} | {d} | {e} |" for a, b, c, d, e in rows]
    out += [
        "",
        f"F11 note: the {k['truncated_rows']} rows lost in transfer are genuine contacts. They are missing from "
        "gold until the vendor re-sends, which is why the expected `collections_activity` count below is "
        "reduced by the same number.",
        "",
        "## Normal messiness the pipeline must fix (not quarantine)",
        "",
        "| Issue | Rows |",
        "|---|---:|",
    ]
    out += [f"| {a} | {b:,} |" for a, b in messy]
    out += [
        "",
        "## Expected rows in the governed gold tables after the full run (all periods landed)",
        "",
        "| Table | Rows |",
        "|---|---:|",
    ]
    out += [f"| `{t}` | {n:,} |" for t, n in sorted(k["expected_gold_rows"].items())]
    out += [
        "",
        f"## Correspondence\n\n{k['letters']} customer letters, by the RBI ground recorded on the complaint "
        "(the ground truth the AI triage step is graded against):",
        "",
        "| RBI ground | Letters |",
        "|---|---:|",
    ]
    out += [f"| {g} | {n} |" for g, n in sorted(k["letters_by_ground"].items())]
    out += ["", f"Periods: {k['periods'][0]} to {k['periods'][-1]}. Held back for the live demo: "
            f"{k['hold_period']} (written to the `holdback` volume)."]
    return "\n".join(out) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--landing", required=True, help="landing root, e.g. /Volumes/<c>/<s>/landing")
    ap.add_argument("--holdback", required=True, help="where the held-back period is written")
    ap.add_argument("--hold-period", default=book.CURRENT_MONTH.isoformat()[:7])
    ap.add_argument("--bank", default="Demo Retail Bank")
    ap.add_argument("--answer-key", default="", help="also write the answer key markdown here")
    ap.add_argument("--clean", action="store_true",
                    help="empty landing and holdback first (local runs only; never on a live volume)")
    a = ap.parse_args()
    if a.clean:
        for root in (a.landing, a.holdback):
            shutil.rmtree(root, ignore_errors=True)
    k = write(a.landing, a.holdback, a.hold_period, a.bank)
    md = answer_key_markdown(k)
    for path in [a.answer_key, os.path.join(a.landing, "_answer_key", "00_answer_key.md")]:
        if path:
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
            with open(path, "w") as fh:
                fh.write(md)
            # The same counts as data, so the evidence pack can check the pipeline against them.
            with open(os.path.join(os.path.dirname(os.path.abspath(path)), "_answer_key.json"), "w") as fh:
                json.dump(k, fh, indent=1, sort_keys=True)
    print(md)
    return 0
