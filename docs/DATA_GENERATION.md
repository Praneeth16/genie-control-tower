# How the synthetic data is shaped

Every record in this repository is invented. This page shows the code that gives the data its shape, so the delinquency spikes, the conduct patterns and the letter content can be checked at the source rather than inferred from the gold tables. The code lives in three files.

| File | What it does |
|---|---|
| `data/generate_banking_data.py` | Builds the clean book of record in memory: branches, products, customers, loans, monthly delinquency, contact attempts, complaints, disputes, RM targets. Seed 7, so every run is identical. |
| `data/landing.py` | Turns that book into the files each source system would send, in that system's own field names, split by month, with the derived fields removed and twelve defects planted. Writes the manifests last and the answer key. |
| `data/generate_documents.py` | Writes the customer letters and the bank's reference documents from the complaints in memory, with no label lines the model could copy. |

The setup job runs `generate_banking_data.py`, which calls `landing.main()` at the end. The pipeline reads only the files `landing.py` wrote. Nothing in gold is loaded from the clean book.

## The two stress stories

Delinquency is drawn per loan per month from a base rate that depends on the product. Two multipliers sit on top of it. They are the whole reason Solapur microfinance and Indore commercial vehicles stand out.

```python
# data/generate_banking_data.py
MFI_SOLAPUR_STRESS = {
    dt.date(2026, 3, 1): 1.15,
    dt.date(2026, 4, 1): 2.10,
    dt.date(2026, 5, 1): 3.40,   # worst
    dt.date(2026, 6, 1): 2.60,
    dt.date(2026, 7, 1): 1.70,
    dt.date(2026, 8, 1): 1.30,
}
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

def _stress(month, branch_id, product_code):
    mult = 1.0
    if product_code == "MFI" and branch_id in SOLAPUR_BRANCHES:
        mult *= MFI_SOLAPUR_STRESS.get(month, 1.0)
    if product_code == "CV" and branch_id in INDORE_BRANCHES:
        mult *= CV_INDORE_STRESS.get(month, 1.0)
    return mult
```

The multiplier is applied twice. It raises the chance that a loan is delinquent in that month, and it pushes the delinquent loans deeper into the ageing buckets.

```python
p_delinquent = min(0.95, base * _stress(month, bid, product))
...
# Skew: most delinquency is early-bucket, stress pushes it deeper.
sev = rng.random() ** (1.0 / max(1.0, _stress(month, bid, product)))
```

The gold table `delinquency_monthly` shows the result: Solapur microfinance at 11.7% in February and 43.6% in May, Indore commercial vehicles at 26.0% in May. The notebook in `run_output/verify_run.ipynb` asks Genie for the May figure and checks it against ground-truth SQL.

## Conduct patterns

Collections effort rises with the same stress multiplier, so the regions under pressure are also the regions where the most calls are made. About 4% of contacts fall outside the RBI window of 08:00 to 19:00, and about 12% of recovery agents are not conduct certified.

```python
# Effort rises with stress — collections worked harder in Solapur and Indore.
attempts = int(round(rng.randint(1, 4) * _stress(month, bid, product)))
for _ in range(max(1, attempts)):
    ...
    # ~4% of contacts fall outside the RBI-permitted 08:00-19:00 window.
    hour = rng.choice([7, 20, 21]) if rng.random() < 0.04 else rng.randint(9, 18)
```

```python
certified = rng.random() > 0.12          # ~12% uncertified — the guardrail catches these
```

The pipeline does not receive the `within_rbi_hours` flag. The dialer file carries a timestamp string and the field app carries an epoch. The pipeline computes the flag with the Unity Catalog function `is_within_rbi_conduct_hours`, and the gold table `collections_activity` shows 2,499 of 63,230 contacts outside the window.

## Complaints follow the pressure

Complaints are not assigned to customers at random. A borrower who was contacted many times, or whose calls broke the conduct window, is more likely to complain, and a recovery-conduct complaint is attached to the loan and branch that caused it. This is what gives the grievance hold something to hold: loans that are past due, being contacted, and carrying an open complaint at the same time.

```python
# Pressure is scored from the two things a borrower would actually complain about: how many times
# they were contacted, and how many of those calls broke the 08:00-19:00 conduct window.
...
customer = pressured_pick or _customer_id(r)
held = (cust_loan or {}).get(customer)
if cat in ("REC", "LON") and held:
    # Recovery conduct and loan servicing are ABOUT a specific loan. These must match.
    product_code, bid = held
...
# Recovery-conduct cases genuinely run long: they need an agency response, often a
# field verification, and they escalate. That is also what keeps a realistic number of
# them OPEN on the as-of date, which is what the grievance hold needs in order to have
# anything to hold.
if cat == "REC" and pressured_pick:
    pressure *= 2.6
```

## The letters

`generate_documents.py` writes one letter per selected complaint, in the customer's words, with the branch and loan details the complaint carries. Recovery-conduct letters draw from sentences such as "They stood outside and called out my name loudly so the neighbours could hear." The letter carries no category code, severity or RBI ground, so the AI triage has to read the text. The grievance desk's recorded category stays in the CRM extract and is the ground truth the evaluation grades against.

## The twelve planted defects

`landing.py` plants each defect with a hash on the record key, so the count is fixed and the answer key can state it. The dialer feed carries most of them.

```python
# A vendor that batches by upload time, not call time, puts a few late calls in next month's file.
if period < book.CURRENT_MONTH.isoformat()[:7] and _h("late", aid) % LATE_EVERY == 0:
    period = _next_month(period)
    late += 1
...
if period == TRUNCATED_PERIOD:
    # The transfer drops the tail of the file. The manifest was cut before the upload, so it
    # still counts — and totals — every row the vendor meant to send.
    lost, rows = rows[-TRUNCATED_ROWS:], rows[:-TRUNCATED_ROWS]
resent = [r for r in rows if _h("dup", r[0]) % DUPLICATE_EVERY == 0]
dup += len(resent)
rows += resent                                       # the vendor re-sends a block at the end
```

| Id | Defect | Planted | Where the pipeline shows it |
|---|---|---|---|
| F01 | Dialer re-sends a block of calls at the end of the file | 589 | Removed by the dedup in `core_collections_activity`. Row counts match the key. |
| F02 | Call time cannot be read | 30 | `quarantine_collections_activity`, reason "unparseable contact timestamp" |
| F03 | Call logged against a loan the bank does not hold | 40 | `quarantine_orphans`, reason "unknown loan account" |
| F04 | Field visit with no loan account | 25 | `quarantine_collections_activity`, reason "missing loan account" |
| F05 | Negative days past due | 25 | `quarantine_delinquency`, reason "negative days past due" |
| F06 | Complaint with an unknown category | 18 | `quarantine_orphans`, reason "unknown complaint category" |
| F07 | Complaint sent twice | 15 | Dedup in `core_complaints` |
| F08 | UPI dispute with zero or negative amount | 35 | `quarantine_upi_disputes`, reason "non-positive amount" |
| F09 | Chargeback raised before its transaction | 20 | `quarantine_chargebacks`, reason "raised before transaction" |
| F10 | Loan with a product the bank does not sell | 12 | `quarantine_orphans`, reason "unknown product code" |
| F11 | June dialer file truncated in transfer | 37 rows | `recon_completeness` shows the file as BREAK |
| F12 | Calls uploaded in the following month's file | 236 | The `arrived_in_period` expectation warns and keeps them |

The answer key the generator writes is `evidence/00_answer_key.md`. The comparison against what the pipeline caught is `evidence/02_data_quality.md`. Every count matched.

## The held-back month

The generator writes 2026-08 to a separate `holdback` volume. `tools/land_next_period.py` copies it into `landing`, manifest last, and the cycle job starts on file arrival. The run that started this way is run 366295467750773 in `run_output/01_cycle_job_runs.txt`.
