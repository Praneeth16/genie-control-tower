"""Deterministic synthetic banking data for the Control Tower Genie Agent workshop.

ALL DATA IS SYNTHETIC. No real customer data is used, read, or reproduced anywhere.
Entity names, customers, agents and branches are invented. The shape is modelled on a
generic Indian private-sector bank so the demo questions feel real.

Seed is fixed (7) so every run produces identical data — required so benchmark
ground-truth SQL stays valid between runs.

Three domains, each sized for the Genie accuracy sweet spot (5-7 tables per agent):

  COLLECTIONS  loan_accounts, delinquency_daily, collections_activity,
               recovery_agents, repayment_schedule, branch_master
  GRIEVANCE    complaints, complaint_categories, upi_disputes, chargebacks,
               sla_tracker, branch_master
  RM           relationship_managers, rm_targets, rm_achievement,
               customer_portfolio, product_holdings, incentive_slabs

The narrative (what the agents must be able to explain):
  1. A microfinance (BFIL-style) repayment shock in the SOLAPUR district from 2026-04,
     worst in 2026-05, partially recovering by 2026-07. Driven by an external event, so
     collections effort rose while recovery rate fell.
  2. A commercial-vehicle delinquency spike in INDORE from 2026-03, concentrated in
     one product and two branches, with bucket-2 roll-forward climbing.
  3. A UPI switch degradation on 2026-06-14/15 that produced a complaint spike two days
     later and a dispute backlog that breached SLA.
  4. RM incentive distortion: a handful of RMs hit target on volume but their portfolios
     show poor product mix, so incentive paid diverges from portfolio quality.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import random

SEED = 7

# The customer master is 9,000 rows, and EVERY table carrying a customer_id must draw from that same
# range. Four tables drew from a 42,000-wide space instead, so roughly 79% of loan and complaint
# customer references pointed at customers that did not exist. Nothing errored — Spark joins simply
# dropped the rows — but it quietly disabled a governance control: the RBI grievance hold resolves
# loan -> customer -> open complaints, and with both sides scattered across a key space four and a half
# times too large it almost never found a match. It appeared to work only by coincidental id collision.
N_CUSTOMERS = 9000
N_LOANS = 6000


def _customer_id(rng: random.Random) -> str:
    """The only way a customer_id should ever be produced."""
    return f"CU{rng.randint(1, N_CUSTOMERS):06d}"

# ---------------------------------------------------------------------------
# Reference dimensions
# ---------------------------------------------------------------------------

# region, district/city, zone. Solapur and Indore carry the narrative.
BRANCHES = [
    # (branch_id, branch_name, city, state, region, zone)
    ("BR001", "Mumbai Fort", "Mumbai", "Maharashtra", "West", "Metro"),
    ("BR002", "Mumbai Andheri", "Mumbai", "Maharashtra", "West", "Metro"),
    ("BR003", "Pune Camp", "Pune", "Maharashtra", "West", "Urban"),
    ("BR004", "Solapur Main", "Solapur", "Maharashtra", "West", "Semi-Urban"),
    ("BR005", "Solapur Rural", "Solapur", "Maharashtra", "West", "Rural"),
    ("BR006", "Indore Palasia", "Indore", "Madhya Pradesh", "Central", "Urban"),
    ("BR007", "Indore Dewas Naka", "Indore", "Madhya Pradesh", "Central", "Semi-Urban"),
    ("BR008", "Bhopal MP Nagar", "Bhopal", "Madhya Pradesh", "Central", "Urban"),
    ("BR009", "Delhi Connaught Place", "New Delhi", "Delhi", "North", "Metro"),
    ("BR010", "Gurugram Cyber City", "Gurugram", "Haryana", "North", "Metro"),
    ("BR011", "Jaipur MI Road", "Jaipur", "Rajasthan", "North", "Urban"),
    ("BR012", "Chennai T Nagar", "Chennai", "Tamil Nadu", "South", "Metro"),
    ("BR013", "Coimbatore RS Puram", "Coimbatore", "Tamil Nadu", "South", "Urban"),
    ("BR014", "Bengaluru Koramangala", "Bengaluru", "Karnataka", "South", "Metro"),
    ("BR015", "Hyderabad Banjara Hills", "Hyderabad", "Telangana", "South", "Metro"),
    ("BR016", "Kolkata Park Street", "Kolkata", "West Bengal", "East", "Metro"),
    ("BR017", "Guwahati GS Road", "Guwahati", "Assam", "East", "Urban"),
    ("BR018", "Patna Boring Road", "Patna", "Bihar", "East", "Urban"),
]

# product_code, product_name, segment, is_secured
PRODUCTS = [
    ("CV", "Commercial Vehicle Loan", "Vehicle Finance", True),
    ("PV", "Passenger Vehicle Loan", "Vehicle Finance", True),
    ("TW", "Two Wheeler Loan", "Vehicle Finance", True),
    ("MFI", "Microfinance Group Loan", "Microfinance", False),
    ("PL", "Personal Loan", "Retail Unsecured", False),
    ("CC", "Credit Card", "Cards", False),
    ("HL", "Home Loan", "Mortgages", True),
    ("BL", "Business Loan", "Business Banking", False),
]

COMPLAINT_CATEGORIES = [
    # (category_code, category_name, rbi_category, sla_days)
    ("PAY", "Payment / Fund Transfer failure", "Payment systems", 7),
    ("UPI", "UPI transaction dispute", "Payment systems", 7),
    ("CRD", "Credit / Debit card dispute", "Cards", 15),
    ("LON", "Loan account servicing", "Loans and advances", 21),
    ("DEP", "Deposit account servicing", "Deposit accounts", 15),
    ("MIS", "Mis-selling of product", "Mis-selling", 30),
    ("REC", "Recovery agent conduct", "Recovery agents", 21),
    ("ATM", "ATM / cash dispensing", "Payment systems", 7),
    ("KYC", "KYC / documentation", "Other", 15),
    ("CHG", "Unauthorised charges or fees", "Levy of charges", 15),
]

# Indian first/last name pools for synthetic staff and customers.
FIRST = [
    "Aarav", "Vivaan", "Aditya", "Vihaan", "Arjun", "Sai", "Reyansh", "Krishna",
    "Ishaan", "Rohan", "Ananya", "Diya", "Aadhya", "Kiara", "Saanvi", "Anika",
    "Navya", "Riya", "Meera", "Prisha", "Rahul", "Amit", "Priya", "Neha",
    "Sunil", "Kavita", "Manish", "Deepa", "Rajesh", "Sneha",
]
LAST = [
    "Sharma", "Verma", "Patel", "Reddy", "Nair", "Iyer", "Singh", "Gupta",
    "Mehta", "Joshi", "Desai", "Rao", "Kulkarni", "Chatterjee", "Banerjee",
    "Pillai", "Shetty", "Kaur", "Bhat", "Menon",
]


def _rng(*parts: object) -> random.Random:
    """A deterministic RNG derived from the seed plus a key, so any slice of the data
    can be regenerated identically and independently."""
    key = f"{SEED}:" + ":".join(str(p) for p in parts)
    digest = hashlib.sha256(key.encode()).hexdigest()
    return random.Random(int(digest[:16], 16))


def _name(rng: random.Random) -> str:
    return f"{rng.choice(FIRST)} {rng.choice(LAST)}"


def _month_starts(start: dt.date, months: int) -> list[dt.date]:
    out, y, m = [], start.year, start.month
    for _ in range(months):
        out.append(dt.date(y, m, 1))
        m += 1
        if m > 12:
            m, y = 1, y + 1
    return out


# The 18-month window the demo talks about. "Current" month is 2026-08.
START_MONTH = dt.date(2025, 3, 1)
MONTHS = _month_starts(START_MONTH, 18)
CURRENT_MONTH = MONTHS[-1]

# The single as-of date the whole dataset is "current" at. It exists because complaint state was being
# decided at CURRENT_MONTH + 27 days (2026-08-28) while every instruction, benchmark and dashboard asked
# questions as of 2026-08-31. The two disagreed by three days, which is invisible until you ask "how many
# complaints are open past SLA" and the stored sla_breached flag says 10 while ageing says 16. Same
# question, two defensible answers, no way to tell which the agent used.
AS_OF = dt.date(2026, 8, 31)

# ---------------------------------------------------------------------------
# Narrative stress functions — these are what the Genie agents must explain
# ---------------------------------------------------------------------------

# 1. Microfinance shock in Solapur: multiplier on delinquency for MFI in Solapur branches.
MFI_SOLAPUR_STRESS = {
    dt.date(2026, 3, 1): 1.15,
    dt.date(2026, 4, 1): 2.10,
    dt.date(2026, 5, 1): 3.40,   # worst
    dt.date(2026, 6, 1): 2.60,
    dt.date(2026, 7, 1): 1.70,
    dt.date(2026, 8, 1): 1.30,
}

# 2. Commercial vehicle delinquency spike in Indore.
CV_INDORE_STRESS = {
    dt.date(2026, 3, 1): 1.80,
    dt.date(2026, 4, 1): 2.20,
    dt.date(2026, 5, 1): 2.45,   # worst
    dt.date(2026, 6, 1): 2.30,
    dt.date(2026, 7, 1): 1.95,
    dt.date(2026, 8, 1): 1.60,
}

SOLAPUR_BRANCHES = {"BR004", "BR005"}
INDORE_BRANCHES = {"BR006", "BR007"}

# 3. UPI switch degradation window.
UPI_INCIDENT_DAYS = {dt.date(2026, 6, 14), dt.date(2026, 6, 15)}


def _stress(month: dt.date, branch_id: str, product_code: str) -> float:
    """Delinquency multiplier for a month/branch/product from the narrative above."""
    mult = 1.0
    if product_code == "MFI" and branch_id in SOLAPUR_BRANCHES:
        mult *= MFI_SOLAPUR_STRESS.get(month, 1.0)
    if product_code == "CV" and branch_id in INDORE_BRANCHES:
        mult *= CV_INDORE_STRESS.get(month, 1.0)
    return mult


# ---------------------------------------------------------------------------
# Table builders. Each returns (table_name, columns, rows).
# ---------------------------------------------------------------------------

def build_branch_master():
    cols = ["branch_id", "branch_name", "city", "state", "region", "zone",
            "opened_date", "employee_count"]
    rows = []
    for i, (bid, bname, city, state, region, zone) in enumerate(BRANCHES):
        rng = _rng("branch", bid)
        rows.append((
            bid, bname, city, state, region, zone,
            dt.date(2005 + (i % 15), 1 + (i % 12), 1 + (i % 27)).isoformat(),
            rng.randint(8, 45),
        ))
    return "branch_master", cols, rows


def build_product_master():
    cols = ["product_code", "product_name", "segment", "is_secured"]
    return "product_master", cols, [(c, n, s, sec) for c, n, s, sec in PRODUCTS]


def build_recovery_agents():
    """Field recovery agents. Agency-employed, with an RBI conduct training flag and a
    certification expiry — the guardrail demo reads these."""
    cols = ["agent_id", "agent_name", "agency_name", "branch_id", "region",
            "rbi_conduct_certified", "certification_expiry", "active_flag",
            "complaints_against_ytd"]
    agencies = ["Sunrise Recovery Services", "Trident Collections", "Apex Field Services",
                "Sahyog Associates", "Nucleus Recovery"]
    rows = []
    for i in range(60):
        rng = _rng("agent", i)
        bid = BRANCHES[i % len(BRANCHES)][0]
        region = next(b[4] for b in BRANCHES if b[0] == bid)
        certified = rng.random() > 0.12          # ~12% uncertified — the guardrail catches these
        complaints = rng.choices([0, 0, 0, 1, 1, 2, 3, 5], k=1)[0]
        rows.append((
            f"AG{i + 1:03d}", _name(rng), rng.choice(agencies), bid, region,
            certified,
            (dt.date(2026, 1, 1) + dt.timedelta(days=rng.randint(-200, 420))).isoformat(),
            rng.random() > 0.08,
            complaints,
        ))
    return "recovery_agents", cols, rows


def build_loan_accounts():
    """One row per loan account. ~6,000 accounts weighted toward vehicle finance and MFI."""
    cols = ["loan_account_id", "customer_id", "product_code", "branch_id",
            "disbursed_date", "sanctioned_amount", "outstanding_principal",
            "interest_rate", "tenure_months", "emi_amount", "customer_segment",
            "is_restructured"]
    weights = {"CV": 18, "PV": 14, "TW": 16, "MFI": 24, "PL": 10, "CC": 6, "HL": 6, "BL": 6}
    pool = [p for p, w in weights.items() for _ in range(w)]
    rows = []
    for i in range(N_LOANS):
        rng = _rng("loan", i)
        product = pool[rng.randrange(len(pool))]
        # Concentrate MFI in Solapur and CV in Indore so the narrative has somewhere to live.
        if product == "MFI" and rng.random() < 0.30:
            bid = rng.choice(sorted(SOLAPUR_BRANCHES))
        elif product == "CV" and rng.random() < 0.30:
            bid = rng.choice(sorted(INDORE_BRANCHES))
        else:
            bid = BRANCHES[rng.randrange(len(BRANCHES))][0]

        if product == "MFI":
            amount = rng.randrange(20_000, 80_001, 5_000)
            rate, tenure = round(rng.uniform(21.0, 25.5), 2), rng.choice([12, 18, 24])
            segment = "Rural Household"
        elif product == "CV":
            amount = rng.randrange(600_000, 4_500_001, 50_000)
            rate, tenure = round(rng.uniform(11.5, 15.5), 2), rng.choice([36, 48, 60])
            segment = "Small Fleet Operator"
        elif product == "PV":
            amount = rng.randrange(400_000, 2_000_001, 25_000)
            rate, tenure = round(rng.uniform(9.5, 13.0), 2), rng.choice([36, 48, 60, 84])
            segment = "Salaried"
        elif product == "TW":
            amount = rng.randrange(60_000, 200_001, 5_000)
            rate, tenure = round(rng.uniform(14.0, 19.0), 2), rng.choice([18, 24, 36])
            segment = "Self Employed"
        elif product == "HL":
            amount = rng.randrange(2_000_000, 12_000_001, 100_000)
            rate, tenure = round(rng.uniform(8.4, 9.8), 2), rng.choice([120, 180, 240])
            segment = "Salaried"
        elif product == "PL":
            amount = rng.randrange(100_000, 1_500_001, 25_000)
            rate, tenure = round(rng.uniform(12.0, 18.0), 2), rng.choice([12, 24, 36, 48])
            segment = rng.choice(["Salaried", "Self Employed"])
        elif product == "CC":
            amount = rng.randrange(50_000, 800_001, 25_000)
            rate, tenure = round(rng.uniform(36.0, 43.0), 2), 0
            segment = rng.choice(["Salaried", "Self Employed", "Affluent"])
        else:  # BL
            amount = rng.randrange(500_000, 6_000_001, 50_000)
            rate, tenure = round(rng.uniform(13.0, 17.5), 2), rng.choice([24, 36, 48])
            segment = "MSME"

        disbursed = dt.date(2023, 1, 1) + dt.timedelta(days=rng.randint(0, 1150))
        # Outstanding decays with age; MFI amortises fastest.
        age_months = max(0, (CURRENT_MONTH.year - disbursed.year) * 12 + CURRENT_MONTH.month - disbursed.month)
        decay = 0.965 if product == "MFI" else 0.988
        outstanding = round(amount * (decay ** age_months), 2) if tenure else round(amount * rng.uniform(0.15, 0.85), 2)
        emi = round(amount / tenure * (1 + rate / 100 / 2), 2) if tenure else 0.0

        rows.append((
            f"LN{i + 1:06d}", _customer_id(rng), product, bid,
            disbursed.isoformat(), float(amount), float(max(outstanding, 0.0)),
            rate, tenure, emi, segment, rng.random() < 0.03,
        ))
    return "loan_accounts", cols, rows


def build_delinquency_monthly(loans):
    """Month x loan delinquency snapshot with DPD bucket. This is the table the
    collections agent leans on hardest, so it is pre-aggregated-friendly and narrow."""
    cols = ["snapshot_month", "loan_account_id", "product_code", "branch_id",
            "dpd_days", "dpd_bucket", "outstanding_principal", "overdue_amount",
            "is_npa", "roll_direction"]
    by_id = {r[0]: r for r in loans}
    rows = []
    bucket_of = lambda d: (
        "0-Current" if d == 0 else
        "1-SMA0 (1-30)" if d <= 30 else
        "2-SMA1 (31-60)" if d <= 60 else
        "3-SMA2 (61-90)" if d <= 90 else
        "4-NPA (90+)"
    )
    for month in MONTHS:
        for lid, loan in by_id.items():
            product, bid = loan[2], loan[3]
            rng = _rng("delq", month.isoformat(), lid)
            base = {"MFI": 0.13, "CV": 0.11, "TW": 0.12, "PL": 0.09,
                    "CC": 0.08, "BL": 0.07, "PV": 0.05, "HL": 0.02}[product]
            p_delinquent = min(0.95, base * _stress(month, bid, product))
            if rng.random() > p_delinquent:
                dpd = 0
            else:
                # Skew: most delinquency is early-bucket, stress pushes it deeper.
                sev = rng.random() ** (1.0 / max(1.0, _stress(month, bid, product)))
                dpd = int(1 + sev * 150)
            prev = _rng("delq", (month - dt.timedelta(days=1)).replace(day=1).isoformat(), lid)
            prev_dpd = 0 if prev.random() > p_delinquent else int(1 + (prev.random() ** 1.0) * 150)
            roll = "stable" if bucket_of(dpd) == bucket_of(prev_dpd) else (
                "forward" if dpd > prev_dpd else "backward")
            outstanding = loan[6]
            overdue = round(outstanding * min(0.35, dpd / 400.0), 2) if dpd else 0.0
            rows.append((
                month.isoformat(), lid, product, bid, dpd, bucket_of(dpd),
                float(outstanding), overdue, dpd > 90, roll,
            ))
    return "delinquency_monthly", cols, rows


def build_collections_activity(loans):
    """Collections contact attempts. Includes contact hour so the RBI conduct-hours
    guardrail has real data to police, and a small number of deliberate violations."""
    cols = ["activity_id", "activity_date", "contact_hour", "loan_account_id",
            "product_code", "branch_id", "agent_id", "channel", "outcome",
            "promise_to_pay_amount", "amount_collected", "within_rbi_hours"]
    channels = ["Tele-calling", "SMS", "Field Visit", "WhatsApp", "Email", "Legal Notice"]
    outcomes = ["Contacted - PTP", "Contacted - Refused", "Contacted - Disputed",
                "Not Reachable", "Wrong Number", "Paid", "Partial Payment"]
    delinquent = [l for i, l in enumerate(loans) if _rng("actsel", l[0]).random() < 0.22]
    rows = []
    aid = 0
    for month in MONTHS:
        for loan in delinquent:
            lid, product, bid = loan[0], loan[2], loan[3]
            rng = _rng("act", month.isoformat(), lid)
            # Effort rises with stress — collections worked harder in Solapur and Indore.
            attempts = int(round(rng.randint(1, 4) * _stress(month, bid, product)))
            for _ in range(max(1, attempts)):
                aid += 1
                day = rng.randint(1, 28)
                # ~4% of contacts fall outside the RBI-permitted 08:00-19:00 window.
                hour = rng.choice([7, 20, 21]) if rng.random() < 0.04 else rng.randint(9, 18)
                channel = rng.choice(channels)
                outcome = rng.choice(outcomes)
                ptp = round(loan[9] * rng.uniform(0.5, 1.5), 2) if outcome == "Contacted - PTP" else 0.0
                collected = round(loan[9] * rng.uniform(0.3, 1.2), 2) if outcome in ("Paid", "Partial Payment") else 0.0
                rows.append((
                    f"AC{aid:08d}", dt.date(month.year, month.month, day).isoformat(), hour,
                    lid, product, bid,
                    f"AG{rng.randint(1, 60):03d}", channel, outcome,
                    ptp, collected, 8 <= hour <= 19,
                ))
    return "collections_activity", cols, rows


def build_repayment_schedule(loans):
    """Next-due and last-paid per loan — small, wide-ish helper table for the
    collections agent's 'who is due this week' style questions."""
    cols = ["loan_account_id", "product_code", "branch_id", "next_due_date",
            "emi_amount", "emis_paid", "emis_pending", "last_payment_date",
            "last_payment_amount", "mandate_type"]
    rows = []
    for loan in loans:
        lid, product, bid, tenure, emi = loan[0], loan[2], loan[3], loan[8], loan[9]
        if not tenure:
            continue
        rng = _rng("sched", lid)
        paid = rng.randint(0, max(1, tenure - 1))
        rows.append((
            lid, product, bid,
            (CURRENT_MONTH + dt.timedelta(days=rng.randint(1, 40))).isoformat(),
            emi, paid, tenure - paid,
            (CURRENT_MONTH - dt.timedelta(days=rng.randint(1, 90))).isoformat(),
            round(emi * rng.choice([1.0, 1.0, 1.0, 0.5, 2.0]), 2),
            rng.choice(["NACH", "NACH", "NACH", "Cheque", "Cash", "UPI Autopay"]),
        ))
    return "repayment_schedule", cols, rows


def build_complaint_categories():
    cols = ["category_code", "category_name", "rbi_category", "sla_days"]
    return "complaint_categories", cols, list(COMPLAINT_CATEGORIES)


def recovery_pressure(loans, activity_rows, delinquency_rows) -> tuple[list[str], dict[str, dict]]:
    """Customers whose loan is genuinely under recovery pressure, and how hard.

    Why this exists: complaints used to be assigned to customers uniformly at random, so the set of
    people complaining had no relationship to the set of people being chased. That is not how a bank
    works — the RBI keeps "Recovery agents" as its own ground of complaint precisely BECAUSE recovery
    pressure produces grievances — and it left the demo unable to show its own grievance-hold control
    on a realistic account: no loan was simultaneously past due, contacted, and carrying an open
    complaint.

    Pressure is scored from the two things a borrower would actually complain about: how many times
    they were contacted, and how many of those calls broke the 08:00-19:00 conduct window.
    """
    cust_of = {r[0]: r[1] for r in loans}                 # loan_account_id -> customer_id
    dpd_of: dict[str, int] = {}
    for r in delinquency_rows:                            # keep the worst DPD seen per loan
        dpd_of[r[1]] = max(dpd_of.get(r[1], 0), r[4])

    scored: dict[str, dict] = {}
    for r in activity_rows:
        lid, within = r[3], r[11]
        cust = cust_of.get(lid)
        if cust is None:
            continue
        e = scored.setdefault(cust, {"attempts": 0, "out_of_hours": 0, "dpd": dpd_of.get(lid, 0)})
        e["attempts"] += 1
        e["out_of_hours"] += 0 if within else 1
        e["dpd"] = max(e["dpd"], dpd_of.get(lid, 0))

    # Only count someone as "under pressure" if they are actually delinquent AND have been chased.
    pressured = {c: e for c, e in scored.items() if e["dpd"] > 0 and e["attempts"] >= 3}
    # Sorted so sampling is reproducible regardless of dict iteration order.
    return sorted(pressured), pressured


def build_complaints(pressured_ids=None, pressured=None, cust_loan=None):
    """Customer complaints with RBI-category mapping and SLA state. Carries the
    UPI-incident spike two days after the 2026-06-14/15 switch degradation.

    Recovery-conduct and mis-selling complaints are drawn preferentially from customers actually under
    recovery pressure (see recovery_pressure). Everything else stays uniform, because a UPI failure or
    an ATM dispute has nothing to do with whether the customer owes money.""" 
    cols = ["complaint_id", "received_date", "channel", "category_code",
            "customer_id", "branch_id", "product_code", "severity",
            "status", "resolved_date", "days_to_resolve", "sla_days",
            "sla_breached", "escalated_to_ombudsman", "repeat_complainant",
            "complaint_text"]
    channels = ["Branch", "Call Centre", "Email", "Mobile App", "Website",
                "RBI CMS", "Social Media"]
    sla_by_cat = {c[0]: c[3] for c in COMPLAINT_CATEGORIES}
    texts = {
        "UPI": "UPI payment debited but beneficiary did not receive credit.",
        "PAY": "NEFT transfer failed and the amount has not been reversed.",
        "CRD": "Card was charged twice for a single transaction.",
        "LON": "Loan foreclosure statement not provided despite repeated requests.",
        "DEP": "Deposit account debited with charges that were not disclosed.",
        "MIS": "Insurance product was bundled with the loan without consent.",
        "REC": "Recovery agent called late at night and used abusive language.",
        "ATM": "Cash was not dispensed but the account was debited.",
        "KYC": "Re-KYC documents submitted at branch but account remains restricted.",
        "CHG": "Annual maintenance charge levied though the account is salary-linked.",
    }
    rows = []
    cid = 0
    for month in MONTHS:
        # Baseline volume plus a UPI-driven surge in June 2026.
        for day in range(1, 29):
            date = dt.date(month.year, month.month, day)
            rng = _rng("cmp", date.isoformat())
            base = rng.randint(12, 26)
            surge = 0
            if date in {dt.date(2026, 6, 16), dt.date(2026, 6, 17), dt.date(2026, 6, 18)}:
                surge = rng.randint(55, 90)          # the spike two days after the incident
            for k in range(base + surge):
                cid += 1
                r = _rng("cmp2", date.isoformat(), k)
                if surge and k >= base:
                    cat = "UPI"
                else:
                    cat = r.choices([c[0] for c in COMPLAINT_CATEGORIES],
                                    weights=[16, 20, 14, 12, 10, 5, 6, 8, 5, 4], k=1)[0]
                # A complaint about recovery conduct should come from somebody who was actually
                # subjected to recovery conduct. Weighted, not absolute: a borrower in good standing
                # can still complain about an agent who called the wrong number.
                pressured_pick = None
                if pressured_ids:
                    p_from_pool = {"REC": 0.90, "MIS": 0.45, "LON": 0.30}.get(cat, 0.0)
                    if p_from_pool and r.random() < p_from_pool:
                        pressured_pick = pressured_ids[r.randrange(len(pressured_ids))]

                # Resolve WHO is complaining before deciding what about, so the complaint can describe
                # the relationship they actually have. Assigned at random, a recovery-conduct complaint
                # from a microfinance borrower in Solapur came out tagged as a passenger-vehicle loan in
                # Chennai — which is what the call-assist HUD displayed, and what any banker in the room
                # would spot in a second. It also made it impossible to attribute a complaint to the
                # branch whose conduct caused it.
                customer = pressured_pick or _customer_id(r)
                held = (cust_loan or {}).get(customer)
                if cat in ("REC", "LON") and held:
                    # Recovery conduct and loan servicing are ABOUT a specific loan. These must match.
                    product_code, bid = held
                elif cat == "CRD":
                    product_code = "CC"                     # a card dispute is a card, whatever else they hold
                    bid = held[1] if held else BRANCHES[r.randrange(len(BRANCHES))][0]
                else:
                    # A UPI failure or a KYC hold is not loan-specific, so the product stays free. The
                    # BRANCH still follows the customer, otherwise geography is noise and no complaint can
                    # be attributed to a location.
                    product_code = r.choice([p[0] for p in PRODUCTS])
                    bid = held[1] if held else BRANCHES[r.randrange(len(BRANCHES))][0]
                sla = sla_by_cat[cat]
                # Backlog: the surge period resolves slower, so SLA breaches cluster.
                pressure = 2.1 if surge and cat == "UPI" else 1.0
                # Recovery-conduct cases genuinely run long: they need an agency response, often a
                # field verification, and they escalate. That is also what keeps a realistic number of
                # them OPEN on the as-of date, which is what the grievance hold needs in order to have
                # anything to hold.
                if cat == "REC" and pressured_pick:
                    pressure *= 2.6
                ttr = max(1, int(r.gauss(sla * 0.62 * pressure, sla * 0.30)))
                resolved = date + dt.timedelta(days=ttr)
                is_open = resolved > AS_OF
                status = "Open" if is_open else r.choice(
                    ["Resolved", "Resolved", "Resolved", "Closed - No Deficiency"])
                rows.append((
                    f"CM{cid:07d}", date.isoformat(), r.choice(channels), cat,
                    customer, bid,
                    product_code,
                    r.choices(["Low", "Medium", "High", "Critical"], weights=[40, 38, 18, 4], k=1)[0],
                    status,
                    None if is_open else resolved.isoformat(),
                    None if is_open else ttr,
                    sla,
                    (ttr > sla) if not is_open else (AS_OF - date).days > sla,
                    r.random() < (0.12 if (cat == "REC" and pressured_pick) else
                                  0.05 if cat in ("REC", "MIS") else 0.015),
                    r.random() < 0.09,
                    texts[cat],
                ))
    return "complaints", cols, rows


def build_upi_disputes():
    """UPI dispute lifecycle, including the auto-refund path NPCI shortened to 30 seconds."""
    cols = ["dispute_id", "txn_date", "raised_date", "customer_id", "branch_id",
            "txn_amount", "failure_reason", "resolution_path", "auto_refunded",
            "resolution_seconds", "status", "psp_handle"]
    reasons = ["Timeout at beneficiary bank", "Beneficiary bank declined",
               "Insufficient balance", "Invalid VPA", "Switch degradation",
               "Debit success credit pending", "Duplicate submission"]
    psps = ["@indus", "@okaxis", "@ybl", "@paytm", "@apl", "@ibl"]
    rows = []
    did = 0
    for month in MONTHS:
        for day in range(1, 29):
            date = dt.date(month.year, month.month, day)
            rng = _rng("upi", date.isoformat())
            n = rng.randint(30, 70)
            if date in UPI_INCIDENT_DAYS:
                n = rng.randint(420, 620)            # the incident itself
            for k in range(n):
                did += 1
                r = _rng("upi2", date.isoformat(), k)
                incident = date in UPI_INCIDENT_DAYS
                reason = "Switch degradation" if incident and r.random() < 0.72 else r.choice(reasons)
                auto = r.random() < (0.35 if incident else 0.78)
                secs = r.randint(1, 30) if auto else r.randint(3600, 86400 * 9)
                rows.append((
                    f"UD{did:07d}", date.isoformat(),
                    (date + dt.timedelta(days=0 if auto else r.randint(0, 3))).isoformat(),
                    _customer_id(r),
                    BRANCHES[r.randrange(len(BRANCHES))][0],
                    round(r.uniform(50, 45000), 2), reason,
                    "Auto-refund" if auto else r.choice(["Manual investigation", "Chargeback raised", "Merchant recovery"]),
                    auto, secs,
                    "Closed" if auto or r.random() < 0.8 else "Open",
                    r.choice(psps),
                ))
    return "upi_disputes", cols, rows


def build_chargebacks():
    cols = ["chargeback_id", "txn_date", "raised_date", "customer_id", "card_type",
            "merchant_category", "txn_amount", "reason_code", "liability",
            "status", "days_open", "recovered_amount"]
    mccs = ["Airlines", "E-commerce", "Fuel", "Grocery", "Hotels", "Electronics",
            "Gaming", "Subscription", "Travel Agency", "Restaurants"]
    reasons = ["Fraud - card not present", "Fraud - counterfeit", "Goods not received",
               "Duplicate processing", "Credit not processed", "Cancelled recurring",
               "Incorrect amount"]
    rows = []
    for i in range(4200):
        rng = _rng("cb", i)
        txn = dt.date(2025, 3, 1) + dt.timedelta(days=rng.randint(0, 540))
        raised = txn + dt.timedelta(days=rng.randint(1, 45))
        reason = rng.choice(reasons)
        fraud = reason.startswith("Fraud")
        amount = round(rng.uniform(500, 120000), 2)
        status = rng.choices(["Won", "Lost", "Open", "Withdrawn"], weights=[38, 34, 20, 8], k=1)[0]
        rows.append((
            f"CB{i + 1:06d}", txn.isoformat(), raised.isoformat(),
            _customer_id(rng),
            rng.choice(["Credit", "Debit", "Credit", "Prepaid"]),
            rng.choice(mccs), amount, reason,
            "Bank" if fraud and rng.random() < 0.55 else "Merchant",
            status, rng.randint(1, 90),
            round(amount * rng.uniform(0.6, 1.0), 2) if status == "Won" else 0.0,
        ))
    return "chargebacks", cols, rows


def build_sla_tracker(complaint_rows, complaint_cols):
    """Monthly SLA rollup by branch and RBI category, DERIVED FROM complaints.

    It used to be generated independently with its own random numbers, and the two tables disagreed
    violently: the rollup claimed 56,009 complaints received against an actual 9,660, and 1,562
    ombudsman escalations against 239 — a 6.5x overstatement. Both tables are in the same schema and
    both are legitimate things for an agent to reach for, so "how many complaints did we get" had two
    contradictory answers and no way to tell which one you were given. A pre-aggregated table that
    disagrees with its own detail table is worse than not having one, and it is the single fastest way
    to lose an analytics team's trust.

    It still exists for the reason it always did — it keeps common grievance questions off 9,660 raw
    rows, which is the truncation defence — but it is now a genuine rollup. Cells with no complaints are
    absent rather than invented, so the table is smaller than it was and every number in it reconciles.
    """
    cols = ["report_month", "branch_id", "region", "rbi_category",
            "complaints_received", "complaints_resolved", "within_sla",
            "breached_sla", "avg_days_to_resolve", "ombudsman_escalations"]
    ix = {c: i for i, c in enumerate(complaint_cols)}
    region_of = {b[0]: b[4] for b in BRANCHES}
    rbi_of = {c[0]: c[2] for c in COMPLAINT_CATEGORIES}

    agg: dict[tuple[str, str, str], dict] = {}
    for row in complaint_rows:
        received = row[ix["received_date"]]
        month = received[:7] + "-01"
        bid = row[ix["branch_id"]]
        cat = rbi_of[row[ix["category_code"]]]
        e = agg.setdefault((month, bid, cat), {
            "received": 0, "resolved": 0, "breached": 0, "tat_sum": 0, "tat_n": 0, "omb": 0})
        e["received"] += 1
        if row[ix["status"]] != "Open":
            e["resolved"] += 1
            ttr = row[ix["days_to_resolve"]]
            if ttr is not None:
                e["tat_sum"] += int(ttr)
                e["tat_n"] += 1
        if row[ix["sla_breached"]]:
            e["breached"] += 1
        if row[ix["escalated_to_ombudsman"]]:
            e["omb"] += 1

    rows = []
    for (month, bid, cat), e in sorted(agg.items()):
        # breached_sla counts every breach, open or closed, exactly as complaints.sla_breached does.
        # within_sla is therefore received minus breached, not resolved minus breached — otherwise the
        # two columns cannot be added back to the total the detail table reports.
        rows.append((
            month, bid, region_of[bid], cat,
            e["received"], e["resolved"], e["received"] - e["breached"], e["breached"],
            round(e["tat_sum"] / e["tat_n"], 1) if e["tat_n"] else None,
            e["omb"],
        ))
    return "sla_tracker", cols, rows


def build_relationship_managers():
    cols = ["rm_id", "rm_name", "branch_id", "region", "zone", "rm_grade",
            "date_joined", "portfolio_count", "active_flag"]
    rows = []
    for i in range(180):
        rng = _rng("rm", i)
        bid, _, _, _, region, zone = BRANCHES[i % len(BRANCHES)]
        rows.append((
            f"RM{i + 1:04d}", _name(rng), bid, region, zone,
            rng.choices(["Junior", "Mid", "Senior", "Lead"], weights=[30, 40, 22, 8], k=1)[0],
            (dt.date(2018, 1, 1) + dt.timedelta(days=rng.randint(0, 2800))).isoformat(),
            rng.randint(40, 260), rng.random() > 0.05,
        ))
    return "relationship_managers", cols, rows


def build_incentive_slabs():
    """Incentive slab grid. Deliberately volume-weighted so the RM agent can expose the
    distortion: high attainment on volume can pay out while product mix is poor."""
    cols = ["slab_id", "rm_grade", "attainment_from_pct", "attainment_to_pct",
            "payout_pct_of_target", "quality_gate_required", "min_product_mix_score"]
    rows, sid = [], 0
    grid = [(0, 70, 0.0), (70, 90, 0.40), (90, 100, 0.75),
            (100, 120, 1.00), (120, 150, 1.35), (150, 999, 1.60)]
    for grade in ["Junior", "Mid", "Senior", "Lead"]:
        for lo, hi, pay in grid:
            sid += 1
            rows.append((
                f"SL{sid:03d}", grade, lo, hi,
                pay, pay >= 1.0, 0.55 if pay >= 1.0 else 0.0,
            ))
    return "incentive_slabs", cols, rows


def build_rm_targets():
    cols = ["target_month", "rm_id", "branch_id", "region", "rm_grade",
            "target_casa_amount", "target_loan_amount", "target_cards",
            "target_insurance", "target_product_mix_score"]
    rms = build_relationship_managers()[2]
    rows = []
    for month in MONTHS:
        for rm in rms:
            rng = _rng("tgt", month.isoformat(), rm[0])
            grade_mult = {"Junior": 0.7, "Mid": 1.0, "Senior": 1.4, "Lead": 1.9}[rm[5]]
            rows.append((
                month.isoformat(), rm[0], rm[2], rm[3], rm[5],
                round(2_500_000 * grade_mult * rng.uniform(0.85, 1.15), 2),
                round(4_000_000 * grade_mult * rng.uniform(0.85, 1.15), 2),
                int(18 * grade_mult * rng.uniform(0.8, 1.2)),
                int(10 * grade_mult * rng.uniform(0.8, 1.2)),
                0.60,
            ))
    return "rm_targets", cols, rows


def build_rm_achievement():
    """Achievement plus the derived incentive. A deliberate cohort of ~8% of RMs
    over-attains on volume while carrying a weak product mix — that divergence is the
    finding the RM agent should surface."""
    cols = ["achievement_month", "rm_id", "branch_id", "region", "rm_grade",
            "actual_casa_amount", "actual_loan_amount", "actual_cards",
            "actual_insurance", "product_mix_score", "attainment_pct",
            "incentive_earned", "quality_gate_passed", "clawback_flag"]
    targets = {(t[0], t[1]): t for t in build_rm_targets()[2]}
    slabs = build_incentive_slabs()[2]
    rows = []
    for (month_s, rm_id), t in targets.items():
        rng = _rng("ach", month_s, rm_id)
        gaming = _rng("gaming", rm_id).random() < 0.08     # the distorted cohort
        perf = rng.gauss(1.30 if gaming else 0.97, 0.16)
        perf = max(0.35, perf)
        casa = round(t[5] * perf * rng.uniform(0.9, 1.1), 2)
        loan = round(t[6] * perf * rng.uniform(0.9, 1.1), 2)
        cards = int(t[7] * perf * rng.uniform(0.85, 1.15))
        ins = int(t[8] * (0.35 if gaming else perf) * rng.uniform(0.85, 1.15))
        mix = round(rng.uniform(0.28, 0.48) if gaming else rng.uniform(0.52, 0.86), 3)
        attain = round(((casa / t[5]) + (loan / t[6])) / 2 * 100, 2)
        slab = next((s for s in slabs if s[1] == t[4] and s[2] <= attain < s[3]), None)
        payout_pct = slab[4] if slab else 0.0
        gate_needed = bool(slab[5]) if slab else False
        gate_passed = (mix >= (slab[6] if slab else 0.0)) if gate_needed else True
        target_incentive = (t[5] + t[6]) * 0.0015
        earned = round(target_incentive * payout_pct, 2) if gate_passed else round(target_incentive * payout_pct * 0.5, 2)
        rows.append((
            month_s, rm_id, t[2], t[3], t[4], casa, loan, cards, ins, mix,
            attain, earned, gate_passed, (not gate_passed) and payout_pct >= 1.0,
        ))
    return "rm_achievement", cols, rows


def build_customer_portfolio():
    cols = ["customer_id", "rm_id", "branch_id", "region", "customer_segment",
            "relationship_start", "total_relationship_value", "products_held",
            "casa_balance", "risk_rating", "nri_flag", "churn_risk_score"]
    rows = []
    for i in range(N_CUSTOMERS):
        rng = _rng("port", i)
        rm = f"RM{rng.randint(1, 180):04d}"
        bid = BRANCHES[rng.randrange(len(BRANCHES))][0]
        region = next(b[4] for b in BRANCHES if b[0] == bid)
        rows.append((
            f"CU{i + 1:06d}", rm, bid, region,
            rng.choices(["Mass", "Mass Affluent", "Affluent", "Private", "MSME"],
                        weights=[46, 26, 16, 4, 8], k=1)[0],
            (dt.date(2012, 1, 1) + dt.timedelta(days=rng.randint(0, 5000))).isoformat(),
            round(rng.uniform(25_000, 9_000_000), 2),
            rng.randint(1, 7), round(rng.uniform(1_000, 1_800_000), 2),
            rng.choices(["Low", "Medium", "High"], weights=[62, 30, 8], k=1)[0],
            rng.random() < 0.06, round(rng.uniform(0, 1), 3),
        ))
    return "customer_portfolio", cols, rows


def build_product_holdings():
    cols = ["holding_id", "customer_id", "rm_id", "product_code", "opened_date",
            "balance_or_limit", "is_active", "cross_sell_eligible"]
    rows, hid = [], 0
    for i in range(9000):
        rng = _rng("hold", i)
        cust = f"CU{i + 1:06d}"
        rm = f"RM{rng.randint(1, 180):04d}"
        n = rng.randint(1, 5)
        held = rng.sample([p[0] for p in PRODUCTS], k=n)
        for p in held:
            hid += 1
            rows.append((
                f"PH{hid:07d}", cust, rm, p,
                (dt.date(2016, 1, 1) + dt.timedelta(days=rng.randint(0, 3600))).isoformat(),
                round(rng.uniform(5_000, 3_000_000), 2), rng.random() > 0.07,
                rng.random() < 0.42,
            ))
    return "product_holdings", cols, rows


# ---------------------------------------------------------------------------
# Emit
# ---------------------------------------------------------------------------

def build_all():
    branch = build_branch_master()
    product = build_product_master()
    agents = build_recovery_agents()
    loans = build_loan_accounts()
    # Delinquency and collections must be built BEFORE complaints now, because who complains about
    # recovery conduct depends on who was actually subjected to it.
    delinquency = build_delinquency_monthly(loans[2])
    activity = build_collections_activity(loans[2])
    pressured_ids, pressured = recovery_pressure(loans[2], activity[2], delinquency[2])
    # customer_id -> (product_code, branch_id) of the loan they actually hold. First loan wins, and the
    # loan list is built in a fixed order, so this stays reproducible.
    cust_loan: dict[str, tuple[str, str]] = {}
    for row in loans[2]:
        cust_loan.setdefault(row[1], (row[2], row[3]))
    complaints = build_complaints(pressured_ids, pressured, cust_loan)
    tables = [
        branch, product, agents, loans,
        delinquency,
        activity,
        build_repayment_schedule(loans[2]),
        build_complaint_categories(),
        complaints,
        build_upi_disputes(),
        build_chargebacks(),
        build_sla_tracker(complaints[2], complaints[1]),
        build_relationship_managers(),
        build_incentive_slabs(),
        build_rm_targets(),
        build_rm_achievement(),
        build_customer_portfolio(),
        build_product_holdings(),
    ]
    return tables


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="out", help="output directory for CSV files")
    ap.add_argument("--summary-only", action="store_true", help="print row counts, write nothing")
    args = ap.parse_args()

    import csv
    import json
    import os

    tables = build_all()
    if not args.summary_only:
        os.makedirs(args.out, exist_ok=True)

    print(f"{'table':<26} {'rows':>10}  columns")
    print("-" * 78)
    for name, cols, rows in tables:
        print(f"{name:<26} {len(rows):>10,}  {len(cols)}")
        if args.summary_only:
            continue
        path = os.path.join(args.out, f"{name}.csv")
        with open(path, "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(cols)
            w.writerows(rows)
    total = sum(len(r) for _, _, r in tables)
    print("-" * 78)
    print(f"{'TOTAL':<26} {total:>10,}")
    if not args.summary_only:
        # The guardrail engine checks that its identity can see the WHOLE book, which means it needs to
        # know how big the book is. Those counts used to be copied into guardrails.py by hand, which is
        # a landmine: regenerate the data and the control sees fewer rows than its hardcoded constant,
        # concludes it is being row-filtered, and FAILS CLOSED. The app then refuses to serve and looks
        # like a security incident rather than a stale number. Emit the counts as data instead.
        # Written into app/backend/ because that is where it is CONSUMED, and because it has to be a
        # shipped artefact rather than something read back from the warehouse at startup. The whole
        # point of the check is to compare what the guardrail identity can see against an expectation
        # formed independently of it — an expectation queried at runtime would agree with a row filter
        # instead of catching it.
        counts = {name: len(rows) for name, _, rows in tables}
        repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        for manifest in (os.path.join(repo, "data", "row_counts.json"),
                         os.path.join(repo, "app", "backend", "row_counts.json")):
            with open(manifest, "w") as fh:
                json.dump(counts, fh, indent=2, sort_keys=True)
            print(f"Wrote row-count manifest to {manifest}")
        print(f"\nWrote {len(tables)} CSVs to {args.out}/")


if __name__ == "__main__":
    main()
