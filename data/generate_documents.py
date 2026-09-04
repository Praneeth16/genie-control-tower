"""Generate the synthetic unstructured corpus for the volumes lane.

The point of this corpus is CORROBORATION. The structured tables say recovery-conduct complaints in
Solapur rose during the microfinance stress; these letters say WHY, in the customer's own words. A
demo where the documents are unrelated to the tables shows a retrieval feature; a demo where they
explain the same event shows why a bank would want both in one agent.

So every letter is keyed to a REAL complaint_id from the complaints table, and the letters attached to
Solapur microfinance conduct complaints describe out-of-hours contact — the exact behaviour the RBI
conduct-hours guardrail refuses. The structured data, the unstructured data and the control all point
at one story.

Deterministic: the same seed produces the same corpus, so a rehearsed demo does not change under you.

    python3 data/generate_documents.py            # write files to data/documents/
"""
from __future__ import annotations

import hashlib
import argparse
import glob
import os
import random
import sys

SEED = 7
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "documents")

SYNTHETIC_BANNER = (
    "*** SYNTHETIC DOCUMENT — generated for a Databricks workshop. Not a real customer "
    "communication. No real customer data is used or reproduced. ***"
)


def _rng(*parts: object) -> random.Random:
    key = f"{SEED}:" + ":".join(str(p) for p in parts)
    return random.Random(int(hashlib.sha256(key.encode()).hexdigest()[:16], 16))


# Complaints taken from the live table so the corpus joins to the structured data on complaint_id.
# The Solapur microfinance conduct cases are listed first because they carry the narrative.
CONDUCT_CASES = [
    ("CM0007205", "2026-04-23", "Medium",   "Resolved",                 "Solapur", "MFI"),
    ("CM0007800", "2026-05-25", "Critical", "Resolved",                 "Solapur", "MFI"),
    ("CM0008238", "2026-06-17", "Low",      "Closed - No Deficiency",   "Solapur", "MFI"),
    ("CM0009530", "2026-08-21", "Medium",   "Open",                     "Solapur", "MFI"),
    ("CM0002656", "2025-08-01", "Medium",   "Closed - No Deficiency",   "Solapur", "MFI"),
]

# What the borrower actually complains about. The out-of-hours times are the material fact: they are
# what makes the conduct-hours control the right answer rather than a theoretical one.
CONDUCT_NARRATIVES = [
    ("late-evening visits", [
        "Two men came to my house at 9:15 pm on a Tuesday and again at 8:40 pm two days later.",
        "They stood outside and called out my name loudly so the neighbours could hear.",
        "I told them my group meeting is on Thursday and I would pay then, but they came back anyway.",
    ]),
    ("early morning calls", [
        "I received calls at 6:20 am and 6:45 am, before I had left for work.",
        "The caller did not give his name or which agency he was from.",
        "When I asked him to call after 9 am he said the account would be marked wilful default.",
    ]),
    ("contacting others about my loan", [
        "The agent spoke to my employer's supervisor about my overdue amount.",
        "He also called two women from my self-help group and told them what I owe.",
        "My group has now asked me to leave, which was not necessary.",
    ]),
    ("pressure after a stated hardship", [
        "I had already informed the branch that our shop was shut for six weeks after the flooding.",
        "The agent visited four times in one week including once after 8 pm.",
        "I have never missed a payment before this year.",
    ]),
    ("agent would not identify himself", [
        "The person who visited would not show any identity card from the bank or the agency.",
        "He came at 7:50 pm and refused to leave until my husband returned.",
        "We do not know if he was authorised to collect money.",
    ]),
]

OTHER_COMPLAINTS = [
    ("CM0008801", "2026-06-17", "UPI",  "High",   "Resolved", "Pune",      "PL",
     "UPI transfer of INR 12,400 was debited but never credited to the beneficiary. The app showed "
     "failed but the money left my account. I raised it the same day and was told to wait 7 days."),
    ("CM0008812", "2026-06-18", "UPI",  "High",   "Resolved", "Mumbai",    "CC",
     "Three UPI payments failed on 15 June and two were debited twice. I have been charged a late "
     "fee on my card because the payment did not go through."),
    ("CM0009104", "2026-07-14", "CHG",  "Medium", "Resolved", "Indore",    "CV",
     "A processing charge of INR 8,500 was deducted that was never disclosed to me when the vehicle "
     "loan was sanctioned. I was told the fee would be waived."),
    ("CM0009377", "2026-08-05", "MIS",  "High",   "Open",     "Bengaluru", "HL",
     "I was told the insurance policy bundled with my home loan was compulsory. I have since learnt "
     "it is optional and I would like it cancelled and refunded."),
]

AGENCIES = [
    ("Apex Field Services", "AG001", "West", "2025-04-01", "2027-03-31"),
    ("Sahyog Associates", "AG012", "Central", "2025-07-01", "2027-06-30"),
    ("Trident Collections", "AG024", "South", "2024-10-01", "2026-09-30"),
    ("Nucleus Recovery", "AG019", "West", "2026-01-01", "2028-12-31"),
]


# Body text per complaint category, several variants each, keyed by category_code. Variety is not
# decoration: with one body per category a vector index has nothing to discriminate on and "semantic
# search" degrades into a category filter you could have written in SQL.
OTHER_BODIES: dict[str, list[str]] = {
    "UPI": [
        "A UPI transfer of INR 12,400 was debited but never credited to the beneficiary. The app showed "
        "the payment as failed while the money had already left my account.",
        "Three UPI payments failed on the same afternoon and two of them were debited twice. I have been "
        "charged a late fee because the payment did not reach the biller.",
        "My UPI payment stayed in pending for two days and then reversed without any message. Nobody at "
        "the call centre could tell me whether the merchant had been paid.",
    ],
    "PAY": [
        "A NEFT transfer failed and the amount has still not been reversed to my account after nine days.",
        "An IMPS transfer to my daughter's account was debited twice. Only one of the two has been returned.",
        "My standing instruction was executed twice in the same month and the second debit has not been "
        "reversed despite two visits to the branch.",
    ],
    "CRD": [
        "My card was charged twice for a single restaurant transaction and the duplicate has not been "
        "reversed.",
        "There are two transactions on my statement from a merchant I have never used. I reported them "
        "the same day and the amount is still outstanding.",
        "An EMI conversion I never requested was applied to a purchase, and interest is now being charged "
        "on it.",
    ],
    "LON": [
        "I have asked three times for a foreclosure statement on my loan and have not received one. I am "
        "unable to close the account without it.",
        "My loan was fully repaid four months ago and the no-objection certificate has still not been "
        "issued, so I cannot transfer the vehicle.",
        "The EMI was debited a month after I had closed the loan, and the excess has not been refunded.",
    ],
    "DEP": [
        "My savings account was debited with charges that were never disclosed when the account was opened.",
        "A minimum-balance penalty was levied on a salary account that is exempt from it.",
        "My fixed deposit was closed prematurely without my instruction and the interest was recalculated "
        "at a lower rate.",
    ],
    "MIS": [
        "I was told the insurance policy bundled with my loan was compulsory. I have since learnt it is "
        "optional and I would like it cancelled and refunded.",
        "The relationship manager described the product as a guaranteed-return deposit. It is a "
        "market-linked policy and I would not have bought it had that been explained.",
        "A second insurance policy was added to my file at renewal without my signature or consent.",
    ],
    "ATM": [
        "Cash was not dispensed but my account was debited. I raised it at the branch the same evening "
        "and have had no acknowledgement.",
        "The machine dispensed less than the amount requested and the shortfall has not been credited.",
        "My card was retained by the machine and I was told to wait fifteen days for a replacement.",
    ],
    "CHG": [
        "A processing charge was deducted that was never disclosed when the loan was sanctioned. I was "
        "told the fee would be waived.",
        "An annual maintenance charge was levied although the account is salary-linked and exempt.",
        "Cheque-return charges were applied twice for the same instrument.",
    ],
    "KYC": [
        "I submitted my re-KYC documents at the branch and my account remains restricted five weeks later.",
        "My address change has been rejected twice without any reason being given, and I cannot operate "
        "the account normally.",
        "I have been asked for the same documents on three separate visits.",
    ],
    "REC": [
        "The recovery agent's conduct is the subject of this complaint; see the narrative below.",
    ],
}


def complaint_letter(cid: str, date: str, severity: str, status: str, city: str,
                     product: str, body_lines: list[str], subject: str) -> str:
    r = _rng("letter", cid)
    ref = f"CUST-LTR-{cid[-6:]}"
    return f"""{SYNTHETIC_BANNER}

{BANK} — Customer Grievance Intake
Document reference : {ref}
Complaint ID       : {cid}
Received           : {date}
Branch city        : {city}
Product            : {product}
Recorded severity  : {severity}
Status at capture  : {status}
Channel            : Branch walk-in, transcribed by the grievance desk

SUBJECT: {subject}

To the Grievance Redressal Officer,

I am writing about the conduct of the recovery agents who have been contacting me regarding my
{product} account.

{chr(10).join('  ' + line for line in body_lines)}

I am willing to pay what I owe. I am asking that the bank instruct its agents to contact me only
during reasonable hours and only about my own account.

I request an acknowledgement of this complaint and the name of the officer handling it.

Yours faithfully,
(name withheld in this synthetic record)
Account holder, {city}

--- grievance desk annotation ---
Ground of complaint (RBI category) : Recovery agents
Conduct issue alleged             : contact outside permitted hours; disclosure to third parties
Agency named by customer          : {r.choice(['Apex Field Services', 'Sahyog Associates', 'Trident Collections'])}
Field visit log to be reconciled  : yes
"""


def other_letter(cid: str, date: str, cat: str, severity: str, status: str, city: str,
                 product: str, body: str) -> str:
    return f"""{SYNTHETIC_BANNER}

{BANK} — Customer Grievance Intake
Document reference : CUST-LTR-{cid[-6:]}
Complaint ID       : {cid}
Received           : {date}
Branch city        : {city}
Product            : {product}
Category code      : {cat}
Recorded severity  : {severity}
Status at capture  : {status}

SUBJECT: {'Failed UPI transaction not reversed' if cat == 'UPI' else 'Charge levied without disclosure' if cat == 'CHG' else 'Product sold as compulsory'}

To the Grievance Redressal Officer,

{body}

I would like this resolved and a written reply explaining what went wrong.

Yours faithfully,
(name withheld in this synthetic record)
Account holder, {city}
"""


def compliance_note() -> str:
    """An INTERNAL policy note, deliberately not a facsimile of an RBI circular.

    Writing a document that looked like real regulatory text would be dishonest and would also put
    fabricated legal wording into a customer's hands. This is framed as what it is: the bank's own
    internal restatement of the requirement, which is the document a collections supervisor would
    actually have on their desk.
    """
    return f"""{SYNTHETIC_BANNER}

{BANK} — Internal Compliance Note (SYNTHETIC EXAMPLE)
Reference : COLL-CONDUCT-NOTE-2026-04
Issued to : Collections & Recovery, all regions
Subject   : Borrower contact conduct standards for recovery agents

NOTE ON STATUS OF THIS DOCUMENT
This is an internal restatement prepared for a Databricks workshop. It is NOT a reproduction of any
Reserve Bank of India circular and must not be cited as one. The underlying requirements derive from
the RBI Fair Practices Code and the directions on outsourcing of financial services; the bank's
compliance function owns the authoritative text and the exact circular references.

1. PERMITTED CONTACT HOURS
   Recovery agents shall not contact a borrower before 08:00 or after 19:00 local time. This applies
   to telephone calls, messages and physical visits alike. There is no exception for a borrower who
   has previously agreed to be contacted later.

2. AGENT CERTIFICATION
   Only agents who have completed the bank's conduct training and hold a current certification may be
   deployed to contact borrowers. A lapsed certification is treated as no certification. Agency
   allocation is permitted only to agencies whose agents meet this standard.

3. GRIEVANCE HOLD
   Where a borrower has an unresolved complaint on record, recovery contact shall be suspended until
   that complaint is closed. Continuing to apply recovery pressure while the customer's own grievance
   is open is treated as a conduct failure regardless of the amount outstanding.

4. PROPORTIONALITY
   Field visits are reserved for accounts materially past due. Early-stage arrears are to be handled
   by telephone and digital reminders. Repeated contact on the same day is not permitted.

5. THIRD PARTIES
   An agent shall not disclose a borrower's indebtedness to an employer, a self-help group, a
   neighbour or any other third party.

6. IDENTIFICATION
   An agent shall identify himself, name the agency, and produce authorisation on request.

SUPERVISORY EXPECTATION
Each of the above is enforced as a system control, not as guidance. Where a control refuses an
action, the refusal is recorded with the reason and is auditable. Supervisors must not seek to work
around a refusal; if a control is wrong, it is to be corrected in policy.
"""


def agency_agreement(name: str, agent_id: str, region: str, start: str, end: str) -> str:
    r = _rng("agency", name)
    return f"""{SYNTHETIC_BANNER}

RECOVERY AGENCY SERVICE AGREEMENT (SYNTHETIC EXAMPLE)
Agency            : {name}
Primary agent id  : {agent_id}
Region of operation: {region}
Term              : {start} to {end}
Agreement ref     : AGY-{r.randint(10000, 99999)}

SCHEDULE 1 — CONDUCT OBLIGATIONS
  1.1 The Agency shall contact borrowers only between 08:00 and 19:00 local time.
  1.2 Every agent deployed shall hold a current conduct certification issued by the Bank.
  1.3 The Agency shall not contact a borrower whose grievance is recorded as open.
  1.4 The Agency shall not disclose borrower indebtedness to any third party.
  1.5 Contact attempts against a single account shall not exceed one per calendar day.

SCHEDULE 2 — SERVICE LEVELS
  2.1 Allocation acknowledgement       : within 1 working day
  2.2 First contact attempt            : within 3 working days of allocation
  2.3 Field visit report submission    : within 1 working day of the visit
  2.4 Complaint response to the Bank   : within 2 working days

SCHEDULE 3 — CONSEQUENCE OF BREACH
  3.1 A substantiated conduct complaint suspends new allocations to the Agency pending review.
  3.2 Two or more substantiated conduct complaints in a quarter permit termination for cause.
  3.3 The Bank remains responsible to the borrower for the conduct of the Agency at all times.

COMMERCIAL TERMS
  Recovery commission : {r.choice([4.5, 5.0, 5.5, 6.0])}% of amounts collected
  Minimum monthly fee : INR {r.choice([75000, 100000, 125000]):,}
"""


SAMPLE_SQL = """
-- Letters are generated FROM the complaints table, not from a hand-written list.
--
-- They used to be hardcoded, and they drifted badly: a letter describing a Solapur microfinance
-- recovery visit sat beside a record saying Indore, passenger-vehicle loan. The Documents tab shows the
-- letter and the record SIDE BY SIDE, so that contradiction was on screen. This is the third time in this
-- project that duplicating a fact instead of deriving it produced a visible inconsistency.
--
-- The sample is weighted: every recovery-conduct complaint that is still open or has reached the
-- ombudsman (those are the ones a conduct committee reads), then a spread of everything else, so the
-- corpus is large enough for semantic retrieval to be doing real work rather than theatre.
WITH ranked AS (
  SELECT c.complaint_id, c.received_date, c.category_code, cc.rbi_category, cc.category_name,
         c.severity, c.status, c.product_code, b.city, b.region,
         c.escalated_to_ombudsman, c.repeat_complainant, c.sla_breached, c.sla_days,
         CASE
           WHEN c.category_code = 'REC' AND (c.status = 'Open' OR c.escalated_to_ombudsman) THEN 0
           WHEN c.category_code = 'REC' THEN 1
           WHEN c.status = 'Open' OR c.escalated_to_ombudsman THEN 2
           ELSE 3
         END AS priority
  FROM {FQ}.complaints c
  JOIN {FQ}.complaint_categories cc ON c.category_code = cc.category_code
  JOIN {FQ}.branch_master b ON c.branch_id = b.branch_id
),
-- Cap each band separately. A single LIMIT filled the whole corpus with recovery-conduct letters,
-- because there are more of those than the cap, and a corpus of one ground turns "semantic search"
-- into a category filter that SQL already does better.
numbered AS (
  SELECT *, ROW_NUMBER() OVER (PARTITION BY priority ORDER BY complaint_id) AS rn,
         ROW_NUMBER() OVER (PARTITION BY priority, rbi_category ORDER BY complaint_id) AS rn_ground
  FROM ranked
)
SELECT complaint_id, received_date, category_code, rbi_category, category_name, severity, status,
       product_code, city, region, escalated_to_ombudsman, repeat_complainant, sla_breached, sla_days,
       priority
FROM numbered
WHERE (priority = 0)                      -- every open or escalated recovery-conduct case
   OR (priority = 1 AND rn <= 150)        -- a sample of the rest of the conduct book
   OR (priority = 2 AND rn <= 150)        -- open or escalated on other grounds
   OR (priority = 3 AND rn_ground <= 45)  -- a spread across every other ground, evenly
ORDER BY priority, complaint_id
"""


def fetch_complaints() -> list[dict]:
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
    import sqlx
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                    "app", "backend"))
    import config
    fq = config.FQ
    out = sqlx.run(SAMPLE_SQL.replace("{FQ}", fq), quiet=True, max_rows=1000)
    return [dict(zip(out["columns"], row)) for row in out["rows"]]


def _truthy(v) -> bool:
    return str(v).strip().lower() in ("true", "1", "t", "yes")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=0, help="cap the corpus (0 = no cap)")
    args = ap.parse_args()

    os.makedirs(os.path.join(OUT, "complaints"), exist_ok=True)
    os.makedirs(os.path.join(OUT, "compliance"), exist_ok=True)
    os.makedirs(os.path.join(OUT, "agencies"), exist_ok=True)
    # Old hand-written letters would otherwise linger and contradict the data forever.
    for stale in glob.glob(os.path.join(OUT, "complaints", "*.txt")):
        os.remove(stale)

    rows = fetch_complaints()
    if args.limit:
        rows = rows[: args.limit]
    written = conduct = 0

    for row in rows:
        cid = row["complaint_id"]
        date = str(row["received_date"])[:10]
        sev, status = row["severity"], row["status"]
        city, product = row["city"], row["product_code"]
        if row["category_code"] == "REC":
            # Vary the narrative so retrieval has something to discriminate on. Seeded by complaint id,
            # so the same complaint always yields the same letter.
            r = _rng("pick", cid)
            subject, lines = CONDUCT_NARRATIVES[r.randrange(len(CONDUCT_NARRATIVES))]
            text = complaint_letter(cid, date, sev, status, city, product, lines,
                                    f"Conduct of recovery agents — {subject}")
            conduct += 1
        else:
            body = OTHER_BODIES.get(row["category_code"], OTHER_BODIES["KYC"])
            r = _rng("body", cid)
            text = other_letter(cid, date, row["category_code"], sev, status, city, product,
                                r.choice(body))
        # Escalation and SLA state come from the record, so the letter cannot claim otherwise.
        annot = [f"Escalated to RBI Ombudsman         : {'yes' if _truthy(row['escalated_to_ombudsman']) else 'no'}",
                 f"Repeat complainant                 : {'yes' if _truthy(row['repeat_complainant']) else 'no'}",
                 f"SLA (days) for this ground         : {row['sla_days']}",
                 f"SLA breached as at 2026-08-31      : {'yes' if _truthy(row['sla_breached']) else 'no'}",
                 f"RBI ground of complaint            : {row['rbi_category']}"]
        text = text.rstrip() + "\n" + "\n".join(annot) + "\n"
        open(os.path.join(OUT, "complaints", f"{cid}.txt"), "w").write(text)
        written += 1

    open(os.path.join(OUT, "compliance", "COLL-CONDUCT-NOTE-2026-04.txt"), "w").write(compliance_note())
    written += 1
    for (name, agent_id, region, start, end) in AGENCIES:
        slug = name.lower().replace(" ", "_")
        open(os.path.join(OUT, "agencies", f"{slug}_agreement.txt"), "w").write(
            agency_agreement(name, agent_id, region, start, end))
        written += 1

    print(f"wrote {written} documents under {OUT}  ({conduct} recovery-conduct letters)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
