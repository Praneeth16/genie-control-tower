"""The synthetic unstructured corpus: customer letters and the bank's reference documents.

The point of this corpus is CORROBORATION. The structured tables say recovery-conduct complaints in
Solapur rose during the microfinance stress; these letters say WHY, in the customer's own words. A
demo where the documents are unrelated to the tables shows a retrieval feature; a demo where they
explain the same event shows why a bank would want both in one agent.

Every letter is keyed to a real complaint_id from the clean book (data/generate_banking_data.py), and
is written into the correspondence folder of the month it was received, as the grievance desk's scanner
would drop it. data/landing.py calls this module; it is not run on its own.

A letter carries only what a customer would write: who they are, when, where, and what went wrong.
It used to carry the grievance desk's annotations as well — category code, recorded severity, RBI
ground. Those are the LABELS, so any model reading the letter could copy the answer instead of
reading the complaint, and an accuracy score measured on it would have measured nothing. The labels
stay in the complaints table, which is exactly where the AI triage step is graded against them.
"""
from __future__ import annotations

import hashlib
import random

SEED = 7

SYNTHETIC_BANNER = (
    "*** SYNTHETIC DOCUMENT — generated for a Databricks workshop. Not a real customer "
    "communication. No real customer data is used or reproduced. ***"
)


def _rng(*parts: object) -> random.Random:
    key = f"{SEED}:" + ":".join(str(p) for p in parts)
    return random.Random(int(hashlib.sha256(key.encode()).hexdigest()[:16], 16))


# What the borrower actually complains about. The out-of-hours times are the material fact: they are
# what makes the conduct-hours control the right answer rather than a theoretical one.
# (subject, lines, microfinance_only). Two narratives mention a self-help group or a group meeting, which
# only makes sense for a joint-liability microfinance borrower; picked at random they attached to vehicle
# and home loans, and a banker reading the letter beside the record would notice immediately.
CONDUCT_NARRATIVES = [
    ("late-evening visits", [
        "Two men came to my house at 9:15 pm on a Tuesday and again at 8:40 pm two days later.",
        "They stood outside and called out my name loudly so the neighbours could hear.",
        "I told them my group meeting is on Thursday and I would pay then, but they came back anyway.",
    ], True),
    ("early morning calls", [
        "I received calls at 6:20 am and 6:45 am, before I had left for work.",
        "The caller did not give his name or which agency he was from.",
        "When I asked him to call after 9 am he said the account would be marked wilful default.",
    ], False),
    ("contacting others about my loan", [
        "The agent spoke to my employer's supervisor about my overdue amount.",
        "He also called two women from my self-help group and told them what I owe.",
        "My group has now asked me to leave, which was not necessary.",
    ], True),
    ("pressure after a stated hardship", [
        "I had already informed the branch that our shop was shut for six weeks after the flooding.",
        "The agent visited four times in one week including once after 8 pm.",
        "I have never missed a payment before this year.",
    ], False),
    ("agent would not identify himself", [
        "The person who visited would not show any identity card from the bank or the agency.",
        "He came at 7:50 pm and refused to leave until my husband returned.",
        "We do not know if he was authorised to collect money.",
    ], False),
]

# (agency, primary agent id, term start, term end). The region is NOT listed here: it is read from the
# agent's own record, because a hand-typed region drifted from recovery_agents and the agreement then
# contradicted the table it is supposed to govern.
AGENCIES = [
    ("Apex Field Services", "AG001", "2025-04-01", "2027-03-31"),
    ("Sahyog Associates", "AG012", "2025-07-01", "2027-06-30"),
    ("Trident Collections", "AG024", "2024-10-01", "2026-09-30"),
    ("Nucleus Recovery", "AG019", "2026-01-01", "2028-12-31"),
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


def _header(bank: str, cid: str, date: str, city: str, product: str) -> str:
    return f"""{SYNTHETIC_BANNER}

{bank} — Customer Grievance Intake (scanned letter)
Complaint ID : {cid}
Received     : {date}
Branch city  : {city}
Product held : {product}

To the Grievance Redressal Officer,
"""


def conduct_letter(bank: str, cid: str, date: str, city: str, product: str,
                   body_lines: list[str]) -> str:
    return _header(bank, cid, date, city, product) + f"""
I am writing about the recovery agents who have been contacting me regarding my {product} account.

{chr(10).join('  ' + line for line in body_lines)}

I am willing to pay what I owe. I am asking that the bank instruct its agents to contact me only
during reasonable hours and only about my own account.

I request an acknowledgement of this complaint and the name of the officer handling it.

Yours faithfully,
(name withheld in this synthetic record)
Account holder, {city}
"""


def other_letter(bank: str, cid: str, date: str, city: str, product: str, body: str) -> str:
    return _header(bank, cid, date, city, product) + f"""
{body}

I would like this resolved and a written reply explaining what went wrong.

Yours faithfully,
(name withheld in this synthetic record)
Account holder, {city}
"""


def compliance_note(bank: str) -> str:
    """An INTERNAL policy note, deliberately not a facsimile of an RBI circular.

    Writing a document that looked like real regulatory text would be dishonest and would also put
    fabricated legal wording into a customer's hands. This is framed as what it is: the bank's own
    internal restatement of the requirement, which is the document a collections supervisor would
    actually have on their desk.
    """
    return f"""{SYNTHETIC_BANNER}

{bank} — Internal Compliance Note (SYNTHETIC EXAMPLE)
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


def select_letters(complaints: list[dict]) -> list[dict]:
    """Which complaints arrive as a letter.

    Weighted: every recovery-conduct complaint that is still open or has reached the ombudsman (those
    are the ones a conduct committee reads), then a sample of the rest of the conduct book and of other
    open or escalated cases, then an even spread across every other ground. Each band is capped on its
    own: a single cap filled the corpus with conduct letters, and a corpus of one ground turns semantic
    search into a category filter that SQL already does better.
    """
    def band(c: dict) -> int:
        open_or_esc = c["status"] == "Open" or c["escalated_to_ombudsman"]
        if c["category_code"] == "REC":
            return 0 if open_or_esc else 1
        return 2 if open_or_esc else 3

    picked, seen = [], {}
    for c in sorted(complaints, key=lambda c: (band(c), c["complaint_id"])):
        b = band(c)
        key = (b, c["rbi_category"]) if b == 3 else (b,)
        seen[key] = seen.get(key, 0) + 1
        cap = {0: None, 1: 150, 2: 150, 3: 45}[b]
        if cap is None or seen[key] <= cap:
            picked.append(c)
    return picked


def render_letter(bank: str, c: dict) -> str:
    cid, date, city, product = c["complaint_id"], c["received_date"], c["city"], c["product_code"]
    if c["category_code"] == "REC":
        # Seeded by complaint id, so the same complaint always yields the same letter.
        options = [n for n in CONDUCT_NARRATIVES if product == "MFI" or not n[2]]
        _, lines, _ = options[_rng("pick", cid).randrange(len(options))]
        return conduct_letter(bank, cid, date, city, product, lines)
    body = OTHER_BODIES.get(c["category_code"], OTHER_BODIES["KYC"])
    return other_letter(bank, cid, date, city, product, _rng("body", cid).choice(body))


def reference_documents(bank: str, agent_region: dict[str, str]) -> dict[str, str]:
    """relative path -> text, for the compliance note and the agency agreements."""
    docs = {"compliance/COLL-CONDUCT-NOTE-2026-04.txt": compliance_note(bank)}
    for name, agent_id, start, end in AGENCIES:
        slug = name.lower().replace(" ", "_")
        docs[f"agencies/{slug}_agreement.txt"] = agency_agreement(
            name, agent_id, agent_region[agent_id], start, end)
    return docs
